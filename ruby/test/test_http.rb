# The HTTP rules (spec §5.7, CR D1): redirects, gzip, Content-Length,
# Retry-After and proxy credentials.
require_relative "support"
require "base64"
require "zlib"
require "stringio"

class HttpTest < Minitest::Test
    include TestSupport
    OTC = OpenTideConstants
    D = "20991231.2".freeze

    # R81 (CR D1): an https request that redirects to http is not followed.
    def test_https_to_http_redirect_is_refused
        plain = serve
        port, ca, stop = tls_server do |path, _h|
            [302, { "Location" => plain.url(path) }, ""]
        end
        err = assert_raises(OTC::NetworkError) do
            OTC.new(base_url: "https://127.0.0.1:#{port}/", cache_dir: tmpdir, ca_file: ca, on_network_error: :raise)
        end
        assert_match(/redirect from https to http/i, err.message)
        assert_empty plain.requests
    ensure
        stop&.call
    end

    # R81 (CR D1): https to https redirects are followed.
    def test_https_redirects_are_followed
        port = nil
        good = File.join(FIXTURES, "good")
        port, ca, stop = tls_server do |path, _h|
            if path.start_with?("/hop/")
                f = File.join(good, File.basename(path))
                File.file?(f) ? [200, {}, File.binread(f)] : [404, {}, ""]
            else
                [301, { "Location" => "https://127.0.0.1:#{port}/hop#{path}" }, ""]
            end
        end
        c = OTC.new(base_url: "https://127.0.0.1:#{port}/", cache_dir: tmpdir, ca_file: ca, on_network_error: :raise)
        assert_equal D, c.release.datestamp
    ensure
        c&.close
        stop&.call
    end

    def multi_member(bytes)
        half = bytes.bytesize / 2
        [bytes.byteslice(0, half), bytes.byteslice(half..)].map do |part|
            io = StringIO.new(+"".b)
            gz = Zlib::GzipWriter.new(io)
            gz.write(part)
            gz.close
            io.string
        end.join
    end

    # R20: a .json.gz made of more than one gzip member is read in full, both
    # opened as a file and downloaded into the cache.
    def test_multi_member_gzip
        dir = tmpdir
        FileUtils.cp_r(Dir[File.join(FIXTURES, "good", "*")], dir)
        gz = File.join(dir, "OTC_#{D}.json.gz")
        File.binwrite(gz, multi_member(File.binread(File.join(dir, "OTC_#{D}.json"))))
        sums = File.read(File.join(dir, "OTC_#{D}.sha256")).lines.map do |l|
            l.end_with?("OTC_#{D}.json.gz\n") ? "#{Digest::SHA256.file(gz).hexdigest}  OTC_#{D}.json.gz\n" : l
        end
        File.write(File.join(dir, "OTC_#{D}.sha256"), sums.join)
        c = OTC.new(file: gz)
        assert_equal 20, c.release.station_count
        c.close
        srv = serve(dir)
        c = OTC.new(release: D, base_url: srv.url("/"), cache_dir: tmpdir, mode: :eager)
        assert_equal 20, c.release.station_count
    ensure
        c&.close
    end

    # R75: two Content-Length headers that differ are a network error.
    def test_conflicting_content_length_headers
        body = File.binread(fixture("good", "OTC_#{D}.sha256"))
        srv = serve(File.join(FIXTURES, "good"), "OTC_#{D}.sha256" => [200, { "Content-Length" => [body.bytesize.to_s, (body.bytesize + 50).to_s] }, body])
        http = OTC::HTTP.new(sleeper: ->(_s) {})
        assert_raises(OTC::NetworkError) { http.get(srv.url("/OTC_#{D}.sha256")) }
    end

    # R75: a Retry-After given as an HTTP date is honoured.
    def test_retry_after_http_date
        hits = 0
        srv = serve(File.join(FIXTURES, "good"), "OTC_#{D}.sha256" => lambda { |_p|
            hits += 1
            hits == 1 ? [503, { "Retry-After" => (Time.now + 30).httpdate }, ""] : [200, {}, "x"]
        })
        waits = []
        http = OTC::HTTP.new(sleeper: ->(s) { waits << s })
        assert_equal 200, http.get(srv.url("/OTC_#{D}.sha256")).status
        assert_equal 1, waits.size
        assert_operator waits[0], :>=, 25
        assert_operator waits[0], :<=, 30
    end

    # R35b: proxy credentials in the URL are percent-decoded before they are sent.
    def test_proxy_credentials_are_decoded
        proxy = serve(File.join(FIXTURES, "good"))
        http = OTC::HTTP.new(proxy: "http://us%40er:p%3Ass@127.0.0.1:#{proxy.url[/:(\d+)\//, 1]}", sleeper: ->(_s) {})
        http.get("http://example.invalid/OTC_latest-f1.json")
        auth = proxy.headers.last["proxy-authorization"]
        refute_nil auth
        assert_equal "us@er:p:ss", Base64.decode64(auth.split(" ", 2)[1])
    end
end
