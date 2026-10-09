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
    # (or in the server code) is recorded in errors, and teardown fails the
    # test with it: a handler that crashes must not look like a network
    # failure. A client that goes away (a socket or TLS error) is not an error.
    class Server
        attr_reader :requests, :headers, :errors

        CLIENT_GONE = [IOError, SystemCallError, OpenSSL::SSL::SSLError].freeze

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
                rescue *CLIENT_GONE
                    raise if @tcp.closed?
                    next # a failed TLS handshake
                end
                begin
                    handle(sock)
                rescue *CLIENT_GONE
                    nil
                rescue Exception => e # rubocop:disable Lint/RescueException
                    @errors << e
                ensure
                    sock.close unless sock.closed?
                end
            end
        end

        def handle(sock)
            line = sock.gets or return
            _, path, = line.split(" ")
            headers = {}
            while (h = sock.gets) && h != "\r\n"
                k, v = h.split(":", 2)
                headers[k.strip.downcase] = v.to_s.strip
            end
            @requests << path
            @headers << headers
            status, out_headers, body = @handler.call(path, headers)
            body = body.to_s.b
            head = +"HTTP/1.1 #{status} X\r\nConnection: close\r\n"
            out_headers = { "Content-Length" => body.bytesize.to_s }.merge(out_headers || {})
            out_headers.each { |k, v| Array(v).each { |x| head << "#{k}: #{x}\r\n" } unless v.nil? }
            sock.write(head + "\r\n")
            sock.write(body) unless status == 304
        end
    end

    # Serves files from a fixture root (or any directory), with an ETag (the
    # quoted SHA-256 of the body) and a 304 for a matching If-None-Match.
    # overrides maps a path suffix to [status, headers, body], or to a lambda
    # that returns one.
    def self.file_server(dir, overrides = {})
        Server.new do |path, headers|
            hit = overrides.find { |suffix, _| path.end_with?(suffix) }
            if hit
                v = hit[1]
                next v unless v.respond_to?(:call)
                v.arity == 2 ? v.call(path, headers) : v.call(path)
            else
                f = File.join(dir, File.basename(path.split("?").first))
                if File.file?(f)
                    body = File.binread(f)
                    etag = "\"#{Digest::SHA256.hexdigest(body)}\""
                    headers["if-none-match"] == etag ? [304, { "ETag" => etag }, ""] : [200, { "ETag" => etag }, body]
                else
                    [404, {}, "not found"]
                end
            end
        end
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

    def tmpdir
        @tmpdirs ||= []
        d = Dir.mktmpdir("otc-rb-test")
        @tmpdirs << d
        d
    end

    # Stops the servers, then fails the test if a handler raised. A temporary
    # directory that cannot be removed is reported, not left in silence.
    def teardown
        servers = @servers || []
        servers.each(&:stop)
        (@tmpdirs || []).each do |d|
            begin
                FileUtils.chmod_R("u+rwx", d) if File.exist?(d)
            rescue SystemCallError => e
                warn "teardown: cannot make #{d} writable: #{e.message}"
            end
            FileUtils.rm_rf(d)
            warn "teardown: cannot remove the temporary directory #{d}" if File.exist?(d)
        end
        errors = servers.flat_map { |s| Array.new(s.errors.size) { s.errors.pop } }
        unless errors.empty?
            e = errors.first
            msg = e.message.lines.first.to_s.strip[0, 200]
            flunk "the test server's handler raised #{e.class}: #{msg}\n#{Array(e.backtrace).first(5).join("\n")}"
        end
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
