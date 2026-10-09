# Helpers for the unit tests: a small real HTTP server on 127.0.0.1 and
# temporary directories. The tests drive the real client over real sockets.
require "socket"
require "tmpdir"
require "fileutils"
require "json"
require "digest"

module TestSupport
    ROOT = File.expand_path("../..", __dir__)
    FIXTURES = File.join(ROOT, "conformance", "fixtures")

    # A one-thread HTTP/1.1 server. The handler gets the request path and
    # headers and returns [status, headers, body]. Every request is recorded.
    class Server
        attr_reader :requests

        def initialize(&handler)
            @handler = handler
            @requests = []
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
            status, out_headers, body = @handler.call(path, headers)
            body = body.to_s.b
            head = +"HTTP/1.1 #{status} X\r\nConnection: close\r\n"
            out_headers = { "Content-Length" => body.bytesize.to_s }.merge(out_headers || {})
            out_headers.each { |k, v| head << "#{k}: #{v}\r\n" unless v.nil? }
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
