# Helpers for the unit tests: a small real HTTP server on 127.0.0.1 and
# temporary directories. The tests drive the real client over real sockets.
# Each test file runs on its own (ruby -Iruby/lib ruby/test/test_x.rb) or
# through test_unit.rb.
$LOAD_PATH.unshift(File.expand_path("../lib", __dir__))
require "minitest/autorun"
require "opentideconstants"
require "socket"
require "tmpdir"
require "fileutils"
require "json"
require "digest"
require "openssl"
require "logger"
require "stringio"
require "time"

module TestSupport
    ROOT = File.expand_path("../..", __dir__)
    FIXTURES = File.join(ROOT, "conformance", "fixtures")

    # A one-thread HTTP/1.1 server (HTTPS when ssl_context is given). The
    # handler gets the request path and headers and returns [status,
    # headers, body]. Every request is recorded. An exception in the handler
    # (any exception, an Errno too) or in the accept loop is recorded in
    # errors, and teardown fails the test with it: a handler that crashes
    # must not look like a network failure. A client that goes away (a
    # socket or TLS error while the request is read or the response is
    # written, or a failed TLS handshake) is not an error.
    class Server
        attr_reader :requests, :headers, :errors

        CLIENT_GONE = [IOError, SystemCallError, OpenSSL::SSL::SSLError].freeze
        # What accept raises for one client that went away during the TCP or
        # TLS handshake. Any other accept error (EMFILE, say) comes back on
        # every retry, so it is recorded and the loop stops.
        HANDSHAKE_GONE = [OpenSSL::SSL::SSLError, Errno::ECONNABORTED, Errno::ECONNRESET, Errno::EPIPE, EOFError].freeze

        def initialize(ssl_context: nil, &handler)
            @handler = handler
            @requests = []
            @headers = []
            @errors = Queue.new
            @tcp = TCPServer.new("127.0.0.1", 0)
            @server = ssl_context ? OpenSSL::SSL::SSLServer.new(@tcp, ssl_context) : @tcp
            @thread = Thread.new { serve }
        end

        def port
            @tcp.addr[1]
        end

        def url(path = "/")
            "http://127.0.0.1:#{port}#{path}"
        end

        def stop
            @thread.kill
            @thread.join
            @server.close
            @tcp.close unless @tcp.closed?
        rescue IOError
            nil
        end

        private

        def serve
            loop do
                sock = begin
                    @server.accept
                rescue *HANDSHAKE_GONE
                    break if @tcp.closed?
                    next # a failed TLS handshake
                rescue Exception => e # rubocop:disable Lint/RescueException
                    break if @tcp.closed?
                    @errors << e
                    break
                end
                begin
                    handle(sock)
                rescue Exception => e # rubocop:disable Lint/RescueException
                    @errors << e
                ensure
                    sock.close unless sock.closed?
                end
            end
        end

        # Only the socket reads and writes treat CLIENT_GONE as a client that
        # went away; the handler runs outside that rescue.
        def handle(sock)
            request = begin
                read_request(sock)
            rescue *CLIENT_GONE
                nil
            end
            return unless request

            path, headers = request
            @requests << path
            @headers << headers
            status, out_headers, body = @handler.call(path, headers)
            body = body.to_s.b
            head = +"HTTP/1.1 #{status} X\r\nConnection: close\r\n"
            out_headers = { "Content-Length" => body.bytesize.to_s }.merge(out_headers || {})
            out_headers.each { |k, v| Array(v).each { |x| head << "#{k}: #{x}\r\n" } unless v.nil? }
            begin
                sock.write(head + "\r\n")
                sock.write(body) unless status == 304
            rescue *CLIENT_GONE
                nil
            end
        end

        def read_request(sock)
            line = sock.gets or return nil
            _, path, = line.split(" ")
            headers = {}
            while (h = sock.gets) && h != "\r\n"
                k, v = h.split(":", 2)
                headers[k.strip.downcase] = v.to_s.strip
            end
            [path, headers]
        end
    end

    # Serves files from a fixture root (or any directory), with an ETag (the
    # quoted SHA-256 of the body) and a 304 for a matching If-None-Match.
    # overrides maps a path suffix to [status, headers, body], or to a lambda
    # that returns one. The query is cut off first, for the overrides and
    # the files alike. A file is served only at /<its name>: a request for
    # any other path (a lost, doubled or extra directory in the client's URL
    # join) is a 404 and is recorded as an error, so the test fails. A
    # request in absolute form (the server used as a proxy) is read by its
    # path.
    def self.file_server(dir, overrides = {})
        s = Server.new do |raw_path, headers|
            path = raw_path.to_s.split("?", 2).first.to_s
            path = path.sub(%r{\Ahttps?://[^/]*}, "") if path.match?(%r{\Ahttps?://})
            name = path[%r{\A/([^/]+)\z}, 1]
            hit = name && overrides.find { |suffix, _| path.end_with?(suffix) }
            if name.nil? || name.start_with?(".")
                s.errors << RuntimeError.new("the client asked for #{raw_path.inspect}, which is not /<a file name> " \
                                             "of the served root")
                [404, {}, "not found"]
            elsif hit
                v = hit[1]
                next v unless v.respond_to?(:call)
                v.arity == 2 ? v.call(path, headers) : v.call(path)
            else
                f = File.join(dir, name)
                if File.file?(f)
                    body = File.binread(f)
                    etag = "\"#{Digest::SHA256.hexdigest(body)}\""
                    headers["if-none-match"] == etag ? [304, { "ETag" => etag }, ""] : [200, { "ETag" => etag }, body]
                else
                    [404, {}, "not found"]
                end
            end
        end
        s
    end

    # A TLS server on 127.0.0.1 with a self-signed certificate; returns
    # [port, ca_file path, stop lambda]. The handler is as for Server, and the
    # server is stopped (and its handler errors checked) in teardown.
    def tls_server(&handler)
        key = OpenSSL::PKey::RSA.new(2048)
        cert = OpenSSL::X509::Certificate.new
        cert.version = 2
        cert.serial = 1
        cert.subject = cert.issuer = OpenSSL::X509::Name.parse("/CN=127.0.0.1")
        cert.public_key = key.public_key
        cert.not_before = Time.now - 60
        cert.not_after = Time.now + 3600
        ef = OpenSSL::X509::ExtensionFactory.new(cert, cert)
        cert.add_extension(ef.create_extension("subjectAltName", "IP:127.0.0.1"))
        cert.add_extension(ef.create_extension("basicConstraints", "CA:TRUE", true))
        cert.sign(key, OpenSSL::Digest.new("SHA256"))
        ca = File.join(tmpdir, "ca.pem")
        File.write(ca, cert.to_pem)
        ctx = OpenSSL::SSL::SSLContext.new
        ctx.cert = cert
        ctx.key = key
        s = Server.new(ssl_context: ctx, &handler)
        (@servers ||= []) << s
        [s.port, ca, -> { s.stop }]
    end

    # A test that needs file permissions to hold (a read-only directory that
    # stops a delete, an unreadable file) skips on Windows and as root, where
    # they do not.
    def posix_only
        skip "needs POSIX permissions" if Gem.win_platform? || Process.uid.zero?
    end

    # Pops from queue, waiting at most seconds; nil when nothing came.
    # Queue#pop(timeout:) needs Ruby 3.2, and the gem supports 3.0.
    def pop_within(queue, seconds)
        deadline = Process.clock_gettime(Process::CLOCK_MONOTONIC) + seconds
        loop do
            return queue.pop(true)
        rescue ThreadError # empty
            return nil if Process.clock_gettime(Process::CLOCK_MONOTONIC) >= deadline
            sleep 0.01
        end
    end

    def tmpdir
        @tmpdirs ||= []
        d = Dir.mktmpdir("otc-rb-test")
        @tmpdirs << d
        d
    end

    # Stops the servers, then fails the test if a handler raised. A temporary
    # directory that cannot be removed is reported, not left in silence.
    # Every server is stopped and every directory removed even when one step
    # fails, and super always runs.
    def teardown
        servers = @servers || []
        errors = []
        servers.each do |s|
            s.stop
        rescue StandardError => e
            errors << e
        end
        (@tmpdirs || []).each do |d|
            begin
                FileUtils.chmod_R("u+rwx", d) if File.exist?(d)
            rescue SystemCallError => e
                warn "teardown: cannot make #{d} writable: #{e.message}"
            end
            FileUtils.rm_rf(d)
            warn "teardown: cannot remove the temporary directory #{d}" if File.exist?(d)
        end
        errors.concat(servers.flat_map { |s| Array.new(s.errors.size) { s.errors.pop } })
        unless errors.empty?
            e = errors.first
            msg = e.message.lines.first.to_s.strip[0, 200]
            flunk "the test server's handler raised #{e.class}: #{msg}\n#{Array(e.backtrace).first(5).join("\n")}"
        end
    ensure
        super
    end

    def serve(dir = File.join(FIXTURES, "good"), overrides = {})
        s = TestSupport.file_server(dir, overrides)
        (@servers ||= []) << s
        s
    end

    def fixture(root, name)
        File.join(FIXTURES, root, name)
    end

    # Writes a copy of good/OTC_<d>.json changed by the block (it gets the
    # parsed document) as OTC_<d>.<ext> (json or jsonl, with its .meta.json)
    # in a new directory, with no .sha256. Returns the path.
    def release_file(ext = "json", d = "20991231.2")
        raise ArgumentError, "release_file writes json or jsonl, not #{ext.inspect}" unless %w[json jsonl].include?(ext)
        doc = JSON.parse(File.read(fixture("good", "OTC_#{d}.json")))
        yield doc
        dir = tmpdir
        if ext == "jsonl"
            stations = doc.delete("stations")
            File.write(File.join(dir, "OTC_#{d}.meta.json"), JSON.generate(doc))
            File.write(File.join(dir, "OTC_#{d}.jsonl"), stations.map { |st| JSON.generate(st) + "\n" }.join)
        else
            File.write(File.join(dir, "OTC_#{d}.json"), JSON.generate(doc))
        end
        File.join(dir, "OTC_#{d}.#{ext}")
    end

    def station_in(doc, id)
        doc["stations"].find { |st| st["station_id"] == id }
    end

    # A logger that keeps its lines.
    class Log
        attr_reader :lines

        def initialize
            @lines = []
        end

        %i[debug info warn error].each do |lvl|
            define_method(lvl) { |msg| @lines << [lvl, msg] }
        end
    end
end
