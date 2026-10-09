# Helpers for the unit tests: a small real HTTP server on 127.0.0.1 and
# temporary directories. The tests drive the real client over real sockets.
require "socket"
require "tmpdir"
require "fileutils"
require "json"
require "digest"
require "openssl"
require "logger"
require "stringio"

module TestSupport
    ROOT = File.expand_path("../..", __dir__)
    FIXTURES = File.join(ROOT, "conformance", "fixtures")

    # A one-thread HTTP/1.1 server. The handler gets the request path and
    # headers and returns [status, headers, body]. Every request is recorded.
    class Server
        attr_reader :requests, :headers

        def initialize(&handler)
            @handler = handler
            @requests = []
            @headers = []
            @server = TCPServer.new("127.0.0.1", 0)
            @thread = Thread.new { serve }
        end

        def url(path = "/")
            "http://127.0.0.1:#{@server.addr[1]}#{path}"
        end

        def stop
            @thread.kill
            @server.close
        rescue IOError
            nil
        end

        private

        def serve
            loop do
                sock = @server.accept
                begin
                    handle(sock)
                rescue StandardError
                    nil
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
    # [port, ca_file path, stop lambda]. The handler is as for Server.
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
        tcp = TCPServer.new("127.0.0.1", 0)
        ssl = OpenSSL::SSL::SSLServer.new(tcp, ctx)
        t = Thread.new do
            loop do
                s = begin
                    ssl.accept
                rescue OpenSSL::SSL::SSLError, SystemCallError
                    next
                end
                begin
                    line = s.gets
                    path = line.to_s.split(" ")[1]
                    h = {}
                    while (x = s.gets) && x != "\r\n"
                        k, v = x.split(":", 2)
                        h[k.strip.downcase] = v.to_s.strip
                    end
                    status, hdrs, body = handler.call(path, h)
                    body = body.to_s.b
                    out = +"HTTP/1.1 #{status} X\r\nConnection: close\r\nContent-Length: #{body.bytesize}\r\n"
                    (hdrs || {}).each { |k, v| out << "#{k}: #{v}\r\n" }
                    s.write(out + "\r\n" + body)
                rescue StandardError
                    nil
                ensure
                    s.close rescue nil
                end
            end
        end
        [tcp.addr[1], ca, -> { t.kill; tcp.close rescue nil }]
    end

    def tmpdir
        @tmpdirs ||= []
        d = Dir.mktmpdir("otc-rb-test")
        @tmpdirs << d
        d
    end

    def teardown
        (@tmpdirs || []).each { |d| FileUtils.chmod_R("u+rwx", d) rescue nil; FileUtils.rm_rf(d) }
        (@servers || []).each(&:stop)
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
