# Error classification: network vs local IO vs configuration (spec §4.8, §5.7, CR D19, D32).
require_relative "support"

class ErrorClassTest < Minitest::Test
    include TestSupport
    OTC = OpenTideConstants
    D = "20991231.2".freeze

    def posix_only
        skip "needs POSIX permissions" if Gem.win_platform? || Process.uid.zero?
    end

    # R2 + R6/R92: download() problems in the caller's folder are io
    # (FileError): a file that cannot be written while its body streams in is
    # not a network error (it was retried and could fall back to the cache).
    def test_download_folder_errors_are_io
        posix_only
        srv = serve
        c = OTC.new(release: D, base_url: srv.url("/"), cache_dir: tmpdir, mode: :stream)
        to = tmpdir
        Dir.mkdir(File.join(to, "OTC_#{D}.jsonl")) # a directory where a file goes
        err = assert_raises(OTC::FileError) { c.download(D, to: to, overwrite: true) }
        assert_equal "io", err.code
        to2 = tmpdir
        FileUtils.chmod(0o555, to2)
        assert_raises(OTC::FileError) { c.download(D, to: to2, formats: [:json]) }
    ensure
        c&.close
    end

    # R39 (CR D32): a data file listed in OTC_{D}.sha256 that the server does
    # not have is a network error with status 404.
    def test_missing_listed_file_is_network_404
        srv = serve(File.join(FIXTURES, "good"), "OTC_#{D}.jsonl" => [404, {}, "gone"])
        err = assert_raises(OTC::NetworkError) do
            OTC.new(release: D, base_url: srv.url("/"), cache_dir: tmpdir, mode: :stream, on_network_error: :raise)
        end
        assert_equal 404, err.status
        assert_includes err.message, "OTC_#{D}.sha256"
    end

    # R26: download of a format the release does not publish is release_not_found.
    def test_unpublished_format_is_release_not_found
        srv = serve(File.join(FIXTURES, "nogz"))
        c = OTC.new(release: D, base_url: srv.url("/"), cache_dir: tmpdir, mode: :stream)
        assert_raises(OTC::ReleaseNotFoundError) { c.download(D, to: tmpdir, formats: [:"json.gz"]) }
    ensure
        c&.close
    end

    # D19 (R34/R35 area): malformed network settings fail at construction.
    def test_network_settings_are_checked_at_construction
        srv = serve
        cache = tmpdir
        assert_raises(OTC::InvalidArgumentError) { OTC.new(base_url: "ftp://x/", cache_dir: cache) }
        assert_raises(OTC::InvalidArgumentError) { OTC.new(base_url: "not a url", cache_dir: cache) }
        assert_raises(OTC::InvalidArgumentError) { OTC.new(base_url: srv.url("/"), cache_dir: cache, proxy: "http://[bad") }
        assert_raises(OTC::InvalidArgumentError) { OTC.new(base_url: srv.url("/"), cache_dir: cache, proxy: "socks5://p:1") }
        err = assert_raises(OTC::FileError) { OTC.new(base_url: srv.url("/"), cache_dir: cache, ca_file: File.join(cache, "none.pem")) }
        assert_equal "io", err.code
        assert_empty srv.requests
    end

    # R34: a TLS certificate failure is not retried, and the message says what to check.
    def test_tls_verify_failure_is_not_retried
        tls = TCPServer.new("127.0.0.1", 0)
        port = tls.addr[1]
        ctx = OpenSSL::SSL::SSLContext.new
        key = OpenSSL::PKey::RSA.new(2048)
        cert = OpenSSL::X509::Certificate.new
        cert.version = 2
        cert.serial = 1
        cert.subject = cert.issuer = OpenSSL::X509::Name.parse("/CN=127.0.0.1")
        cert.public_key = key.public_key
        cert.not_before = Time.now - 60
        cert.not_after = Time.now + 3600
        cert.sign(key, OpenSSL::Digest.new("SHA256"))
        ctx.cert = cert
        ctx.key = key
        ssl = OpenSSL::SSL::SSLServer.new(tls, ctx)
        accepted = 0
        t = Thread.new do
            loop do
                s = ssl.accept rescue nil
                accepted += 1
                s&.close
            end
        end
        log = Log.new
        err = assert_raises(OTC::NetworkError) do
            OTC.new(base_url: "https://127.0.0.1:#{port}/", cache_dir: tmpdir, on_network_error: :raise, logger: log)
        end
        assert_match(/certificate/i, err.message)
        refute(log.lines.any? { |_, m| m.include?("retry") }, "a certificate failure was retried")
    ensure
        t&.kill
        tls&.close
    end

    # R41b: a home directory that cannot be used is a cache error, not a raw ArgumentError.
    # The skip comes before the environment is changed, and the ensure
    # restores only what was saved (a skip must not turn into an error).
    def test_no_home_directory
        skip "POSIX default root" if Gem.win_platform?
        keys = %w[HOME XDG_CACHE_HOME OPENTIDECONSTANTS_CACHE_DIR]
        old = ENV.to_h.slice(*keys)
        begin
            ENV["HOME"] = ""
            ENV.delete("XDG_CACHE_HOME")
            ENV.delete("OPENTIDECONSTANTS_CACHE_DIR")
            assert_raises(OTC::CacheError) { OTC::Cache.default_root }
        ensure
            keys.each { |k| ENV[k] = old[k] }
        end
    end

    # R32: a cache file that exists but cannot be read is an io error, not "not cached".
    def test_unreadable_verified_is_io
        posix_only
        srv = serve
        cache = tmpdir
        OTC.new(release: D, base_url: srv.url("/"), cache_dir: cache).close
        FileUtils.chmod(0o000, File.join(cache, "v1", "releases", D, ".verified"))
        assert_raises(OTC::FileError) { OTC.new(release: D, cache_dir: cache, offline: true) }
    end

    # R29: a release whose .verified goes away between the check and the
    # load (another process pruned it) is treated as not cached, not a NoMethodError.
    def test_verified_removed_between_check_and_load
        srv = serve
        cache = tmpdir
        OTC.new(release: D, base_url: srv.url("/"), cache_dir: cache).close
        ver = File.join(cache, "v1", "releases", D, ".verified")
        c = OTC.new(release: D, base_url: srv.url("/"), cache_dir: cache)
        racy = OTC::Cache.new(cache)
        seen = 0
        racy.define_singleton_method(:verified) do |d|
            doc = super(d)
            seen += 1
            File.delete(ver) if seen == 1 && File.exist?(ver) # pruned right after the check read it
            doc
        end
        c.instance_variable_set(:@cache, racy)
        assert_nil c.send(:load_cached_unless_corrupt, D)
        assert_kind_of OTC::Release, c.send(:fetch_release, D, nil, nil)
    ensure
        c&.close
    end
end
