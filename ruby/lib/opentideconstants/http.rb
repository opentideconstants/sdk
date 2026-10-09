require "net/http"
require "openssl"
require "uri"
require "digest"
require "time"

class OpenTideConstants
    # Net::HTTP with the SDK's rules (spec §5.7): timeouts, three attempts with
    # backoff on connection errors, 5xx and 429 (honouring Retry-After up to
    # 60 s), never a retry on 404, proxies from the option or the environment,
    # a custom CA, and the SDK User-Agent. No telemetry, no query parameters.
    class HTTP
        ATTEMPTS = 3
        BACKOFF = [1, 2, 4].freeze
        MAX_RETRY_AFTER = 60
        CONNECT_TIMEOUT = 10
        READ_TIMEOUT = 60
        TIMEOUT_MIN = 0.001 # the range of the timeout option, in every SDK (spec §5.7, CR2 DR19)
        TIMEOUT_MAX = 1e6
        USER_AGENT = "opentideconstants-ruby/#{VERSION} (+https://opentideconstants.org)".freeze
        NETWORK_ERRORS = [SocketError, SystemCallError, IOError, EOFError, Timeout::Error, OpenSSL::SSL::SSLError,
                          Net::ProtocolError, Net::OpenTimeout, Net::ReadTimeout, Net::HTTPBadResponse,
                          Net::HTTPHeaderSyntaxError, Zlib::Error].freeze

        # The result of one GET: status, headers we use, and (for a 200 to a
        # file) the size and SHA-256 of the decoded body.
        Response = Struct.new(:status, :etag, :body, :size, :sha256, keyword_init: true)

        # A local file that a body is written to cannot be written. It is not a
        # network error: it is not retried, and the caller turns it into a
        # cache or io error (spec §4.8). #cause is the system error.
        class SinkError < StandardError; end

        # An absolute http or https URL (spec §4.2 base_url, §5.7 proxy), or
        # InvalidArgumentError (CR D19).
        def self.check_url!(value, name)
            uri = URI(value)
            raise URI::InvalidURIError, "not absolute" unless %w[http https].include?(uri.scheme) && uri.host && !uri.host.empty?
            uri
        rescue URI::Error, ArgumentError => e
            # no user or password in the message (CR2 DR21), also where the URI error quotes the value
            shown = Redact.url(value)
            raise InvalidArgumentError, "#{name} must be an absolute http or https URL, not #{shown.inspect} " \
                                        "(#{value.is_a?(String) ? e.message.gsub(value, shown) : e.message})"
        end

        def initialize(timeout: nil, proxy: nil, ca_file: nil, user_agent: nil, logger: nil, sleeper: nil)
            @open_timeout = timeout || CONNECT_TIMEOUT
            @read_timeout = timeout || READ_TIMEOUT
            @proxy = proxy && HTTP.check_url!(proxy, "proxy")
            # Net::HTTP speaks plain HTTP to every proxy: an https:// proxy would get plaintext. Refuse it here,
            # not at the first request (R2-105). A CONNECT tunnel through an http:// proxy is still TLS end to end.
            if @proxy&.scheme == "https"
                raise InvalidArgumentError, "proxy: Net::HTTP cannot use TLS to a proxy; use an http:// proxy, not #{proxy.inspect}"
            end
            # A ca_file, else SSL_CERT_FILE, that does not exist or cannot be read is io, at construction:
            # never retried, never a reason to fall back to the cache (CR D19, CR2 DR20).
            what = "ca_file"
            if ca_file.nil? && !ENV["SSL_CERT_FILE"].to_s.empty?
                ca_file = ENV["SSL_CERT_FILE"]
                what = "SSL_CERT_FILE"
            end
            if ca_file && !(File.file?(ca_file) && File.readable?(ca_file))
                raise FileError.new("#{what} #{ca_file} does not exist or cannot be read", path: ca_file)
            end
            @ca_file = ca_file
            @user_agent = user_agent ? "#{USER_AGENT} #{user_agent}" : USER_AGENT
            @logger = logger
            @sleeper = sleeper || ->(s) { sleep(s) }
        end

        # GET into memory. Returns a Response (status 200, 304 or 404); raises
        # NetworkError for anything else after the retries.
        def get(url, etag: nil)
            request(url, etag: etag) do |res|
                body = +""
                res.read_body { |chunk| body << chunk }
                Response.new(status: 200, etag: res["etag"], body: body, size: body.bytesize,
                             sha256: Digest::SHA256.hexdigest(body))
            end
        end

        # GET into a file at path (created or truncated). Returns a Response
        # with the size and SHA-256 of the decoded bytes written.
        def get_to_file(url, path)
            request(url) do |res|
                digest = Digest::SHA256.new
                size = 0
                # Only the file operations are local errors; a failure while the
                # body is read stays a network error.
                f = sink(path) { File.open(path, "wb") }
                begin
                    res.read_body do |chunk|
                        sink(path) { f.write(chunk) }
                        digest << chunk
                        size += chunk.bytesize
                    end
                    # the close is a local file operation too: a failure there is not network (R2-102)
                    sink(path) do
                        f.flush
                        f.fsync
                        f.close
                    end
                ensure
                    begin
                        f.close unless f.closed?
                    rescue SystemCallError, IOError
                        nil # the read or write already failed; that error is the one to report
                    end
                end
                Response.new(status: 200, etag: res["etag"], size: size, sha256: digest.hexdigest)
            end
        end

        private

        # Runs one local file operation on path; a system error becomes SinkError.
        def sink(path)
            yield
        rescue SystemCallError, IOError => e
            raise SinkError, "cannot write #{path}: #{e.message}"
        end

        # A certificate that does not verify does not get better on a retry.
        def tls_verify_failure?(e)
            e.is_a?(OpenSSL::SSL::SSLError) && e.message.include?("certificate verify failed")
        end

        REDIRECTS = [301, 302, 303, 307, 308].freeze
        MAX_REDIRECTS = 5

        # Sends the GET with the retries of §5.7, following up to 5 redirects
        # (CR D1). Each attempt is independent: no state is kept on the
        # instance, so one HTTP can serve several threads.
        def request(url, etag: nil, &on_ok)
            uri = URI(url)
            # decided by the URL asked for, not the redirect hop: a CDN may send the .gz
            # from a URL with no suffix (CR2 R2-118)
            keep_gz = uri.path.end_with?(".gz")
            attempt = 0
            redirects = 0
            loop do
                attempt += 1
                wait = nil
                cause = nil
                begin
                    kind, value, retry_wait = once(uri, etag, keep_gz, &on_ok)
                    return value if kind == :ok
                    if kind == :redirect
                        redirects += 1
                        uri = follow(uri, value, url, redirects)
                        attempt = 0
                        next
                    end
                    status = value
                    return Response.new(status: status) if [304, 404].include?(status)
                    err = NetworkError.new("GET #{uri}: HTTP #{status}", url: uri.to_s, status: status)
                    raise err unless status >= 500 || status == 429
                    wait = retry_wait
                rescue NetworkError, SinkError
                    raise
                rescue *NETWORK_ERRORS => e
                    if tls_verify_failure?(e)
                        raise NetworkError.new("GET #{uri}: the server's TLS certificate does not verify (#{e.message}); " \
                                               "check ca_file or SSL_CERT_FILE", url: uri.to_s, status: nil), cause: e
                    end
                    err = NetworkError.new("GET #{uri}: #{e.class}: #{e.message}", url: uri.to_s, status: nil)
                    cause = e
                end
                if attempt >= ATTEMPTS
                    raise err, cause: cause if cause
                    raise err
                end
                wait ||= BACKOFF[attempt - 1]
                @logger&.warn("opentideconstants: #{err.message}; retry in #{wait} s")
                @sleeper.call(wait)
            end
        end

        # The URI a redirect goes to, or NetworkError: a 6th redirect, a
        # missing or bad Location, a scheme other than http or https, no host,
        # or a redirect from https to http (spec §5.7, CR D1).
        def follow(from, location, url, count)
            raise NetworkError.new("GET #{url}: more than #{MAX_REDIRECTS} redirects", url: url, status: nil) if count > MAX_REDIRECTS
            if location.nil? || location.strip.empty?
                raise NetworkError.new("GET #{from}: a redirect with no Location", url: url, status: nil)
            end
            to = from + location.strip
            unless %w[http https].include?(to.scheme)
                raise NetworkError.new("GET #{from}: a redirect to #{to} is not http or https", url: url, status: nil)
            end
            # a Location such as "https:" or "//:8080/x" has no host: Net::HTTP would connect to localhost
            if to.host.nil? || to.host.empty?
                raise NetworkError.new("GET #{from}: a redirect to #{location.strip.inspect} has no host", url: url, status: nil)
            end
            if from.scheme == "https" && to.scheme == "http"
                raise NetworkError.new("GET #{from}: a redirect from https to http (#{to}) is not followed", url: url, status: nil)
            end
            to
        rescue URI::Error => e
            raise NetworkError.new("GET #{from}: a redirect to a bad Location #{location.inspect} (#{e.message})", url: url, status: nil)
        end

        # One request: [:ok, the block's value] for a 200, [:redirect, the
        # Location], or [:status, the code, the Retry-After wait or nil].
        def once(uri, etag, keep_gz)
            http = connection(uri)
            http.start do |conn|
                req = Net::HTTP::Get.new(uri)
                req["User-Agent"] = @user_agent
                req["If-None-Match"] = etag if etag
                # A .gz file is kept as it is sent: its SHA-256 is over the gzip
                # bytes, also when a server adds Content-Encoding: gzip (spec §5.7).
                req["Accept-Encoding"] = "identity" if keep_gz
                conn.request(req) do |res|
                    code = res.code.to_i
                    if code == 200
                        expected = expected_length(uri, res)
                        result = yield(res)
                        check_length!(uri, expected, result.size)
                        return [:ok, result]
                    end
                    res.read_body { |_| } if code != 304
                    return [:redirect, res["location"]] if REDIRECTS.include?(code)
                    return [:status, code, code == 429 || code >= 500 ? retry_after(res["retry-after"]) : nil]
                end
            end
        end

        # The Content-Length of the body as it is read, or nil: there is none,
        # or Net::HTTP decodes a content-encoded body. Content-Length values
        # that differ, or are not numbers, are a bad response (network).
        def expected_length(uri, res)
            values = Array(res.get_fields("content-length")).flat_map { |v| v.split(",") }.map(&:strip)
            return nil if values.empty?
            nums = values.map { |v| Integer(v, 10, exception: false) }
            if nums.include?(nil) || nums.uniq.size > 1
                raise Net::HTTPBadResponse, "#{uri}: Content-Length #{values.join(', ')}"
            end
            enc = res["content-encoding"].to_s.strip.downcase
            return nil if res.decode_content && !(enc.empty? || enc == "identity")
            nums.first
        end

        # Net::HTTP accepts a body that ends before its Content-Length; the
        # SDK treats it as a network error (README suite choices).
        def check_length!(uri, expected, got)
            return if expected.nil? || got == expected
            raise EOFError, "#{uri}: body ended after #{got} of #{expected} bytes"
        end

        # An HTTP date as a Time, or nil. Impossible calendar fields, hour 24,
        # a leap second and the wrong weekday are malformed (CR2 DR6):
        # Time.httpdate would roll them over into another date.
        def http_date(v)
            f = Date._httpdate(v)
            return nil unless f && f[:year] && f[:mon] && f[:mday] && f[:hour] && f[:min] && f[:sec]
            return nil unless Date.valid_date?(f[:year], f[:mon], f[:mday], Date::GREGORIAN)
            return nil unless f[:hour] <= 23 && f[:min] <= 59 && f[:sec] <= 59
            return nil if f[:wday] && f[:wday] != Date.new(f[:year], f[:mon], f[:mday], Date::GREGORIAN).wday
            Time.httpdate(v)
        rescue ArgumentError
            nil
        end

        # Retry-After in seconds (a number, or an HTTP date), at most 60; nil
        # when it is missing or malformed.
        def retry_after(value)
            return nil if value.nil?
            v = value.strip
            s = Integer(v, 10, exception: false)
            if s.nil?
                t = http_date(v)
                return nil if t.nil?
                s = [(t - Time.now).ceil, 0].max
            end
            s >= 0 ? [s, MAX_RETRY_AFTER].min : nil
        end

        def unescape(part)
            part && URI::DEFAULT_PARSER.unescape(part)
        end

        def connection(uri)
            http = if @proxy
                       # The URL's user and password are percent-encoded; the proxy wants them decoded.
                       Net::HTTP.new(uri.host, uri.port, @proxy.host, @proxy.port, unescape(@proxy.user), unescape(@proxy.password))
                   else
                       Net::HTTP.new(uri.host, uri.port) # :ENV proxy: http(s)_proxy and no_proxy
                   end
            http.open_timeout = @open_timeout
            http.read_timeout = @read_timeout
            http.write_timeout = @read_timeout if http.respond_to?(:write_timeout=)
            if uri.scheme == "https"
                http.use_ssl = true
                http.verify_mode = OpenSSL::SSL::VERIFY_PEER
                http.ca_file = @ca_file if @ca_file
            end
            http
        end
    end
end
