require "net/http"
require "openssl"
require "uri"
require "digest"

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
        USER_AGENT = "opentideconstants-ruby/#{VERSION} (+https://opentideconstants.org)".freeze
        NETWORK_ERRORS = [SocketError, SystemCallError, IOError, EOFError, Timeout::Error, OpenSSL::SSL::SSLError,
                          Net::ProtocolError, Net::OpenTimeout, Net::ReadTimeout, Zlib::Error].freeze

        # The result of one GET: status, headers we use, and (for a 200 to a
        # file) the size and SHA-256 of the decoded body.
        Response = Struct.new(:status, :etag, :body, :size, :sha256, keyword_init: true)

        def initialize(timeout: nil, proxy: nil, ca_file: nil, user_agent: nil, logger: nil, sleeper: nil)
            @open_timeout = timeout || CONNECT_TIMEOUT
            @read_timeout = timeout || READ_TIMEOUT
            @proxy = proxy && URI(proxy)
            @ca_file = ca_file || ENV["SSL_CERT_FILE"]
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
                File.open(path, "wb") do |f|
                    res.read_body do |chunk|
                        f.write(chunk)
                        digest << chunk
                        size += chunk.bytesize
                    end
                    f.flush
                    f.fsync
                end
                Response.new(status: 200, etag: res["etag"], size: size, sha256: digest.hexdigest)
            end
        end

        private

        def request(url, etag: nil, &on_ok)
            uri = URI(url)
            attempt = 0
            loop do
                attempt += 1
                wait = nil
                begin
                    result = once(uri, etag, &on_ok)
                    return result unless result.is_a?(Integer)
                    status = result
                    return Response.new(status: status) if [304, 404].include?(status)
                    err = NetworkError.new("GET #{url}: HTTP #{status}", url: url, status: status)
                    raise err unless status >= 500 || status == 429
                    wait = @retry_after
                rescue NetworkError
                    raise
                rescue *NETWORK_ERRORS => e
                    err = NetworkError.new("GET #{url}: #{e.class}: #{e.message}", url: url, status: nil)
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

        # One request. Returns the block's value for a 200, else the status.
        def once(uri, etag)
            @retry_after = nil
            http = connection(uri)
            http.start do |conn|
                req = Net::HTTP::Get.new(uri)
                req["User-Agent"] = @user_agent
                req["If-None-Match"] = etag if etag
                conn.request(req) do |res|
                    code = res.code.to_i
                    if code == 200
                        check_length!(res)
                        return yield(res)
                    end
                    @retry_after = retry_after(res["retry-after"]) if code == 429 || code >= 500
                    res.read_body { |_| } if code != 304
                    return code
                end
            end
        end

        # A body shorter than its Content-Length makes Net::HTTP raise EOFError
        # while it reads; nothing to do here but keep the hook explicit.
        def check_length!(_res); end

        def retry_after(value)
            return nil if value.nil?
            s = Integer(value.strip, exception: false)
            s && s >= 0 ? [s, MAX_RETRY_AFTER].min : nil
        end

        def connection(uri)
            http = if @proxy
                       Net::HTTP.new(uri.host, uri.port, @proxy.host, @proxy.port, @proxy.user, @proxy.password)
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
