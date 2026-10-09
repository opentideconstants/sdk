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
    # (FileError), and not retried: a file in the way (found when the
    # existing files are checked), a folder where the temporary file cannot
    # be made, and a write that fails while the body streams in (that one
    # was a network error, retried and could fall back to the cache).
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
        err = assert_raises(OTC::FileError) { c.download(D, to: to2, formats: [:json]) }
        assert_equal "io", err.code
        assert_includes err.message, "Permission denied"

        # The disk fills up after the first chunk of OTC_D.json is written.
        to3 = tmpdir
        writes = Hash.new(0)
        full = Module.new do
            define_method(:write) do |*args|
                if path.to_s.start_with?(to3) && File.basename(path.to_s).start_with?(".tmp-")
                    writes[path] += 1
                    raise Errno::ENOSPC, path if writes[path] > 1
                end
                super(*args)
            end
        end
        File.prepend(full)
        before = srv.requests.size
        begin
            err = assert_raises(OTC::FileError) { c.download(D, to: to3, formats: [:json]) }
        ensure
            full.send(:remove_method, :write)
        end
        assert_operator writes.values.max.to_i, :>, 1, "the write did not fail after the first chunk"
        assert_equal "io", err.code
        assert_includes err.message, "No space left on device"
        assert_equal ["/OTC_#{D}.json"], srv.requests[before..], "the failed write was retried"
        assert_empty Dir.children(to3)
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
        # Each connection is counted when it is accepted, before its handshake.
        # The client's error comes from a failed handshake, so when it is
        # raised, every connection it made has been counted.
        connections = Queue.new
        t = Thread.new do
            loop do
                sock = tls.accept
                connections << 1
                ssl = OpenSSL::SSL::SSLSocket.new(sock, ctx)
                begin
                    ssl.accept
                rescue OpenSSL::SSL::SSLError, SystemCallError
                    nil # the client refused the certificate
                ensure
                    sock.close
                end
            end
        end
        log = Log.new
        err = assert_raises(OTC::NetworkError) do
            OTC.new(base_url: "https://127.0.0.1:#{port}/", cache_dir: tmpdir, on_network_error: :raise, logger: log)
        end
        assert_match(/certificate/i, err.message)
        assert_equal 1, connections.size, "a certificate failure was retried"
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

    # R32, CR2 DR16: a cache file that exists but cannot be read is a cache
    # error, not "not cached".
    def test_unreadable_verified_is_cache
        posix_only
        srv = serve
        cache = tmpdir
        OTC.new(release: D, base_url: srv.url("/"), cache_dir: cache).close
        FileUtils.chmod(0o000, File.join(cache, "v1", "releases", D, ".verified"))
        assert_raises(OTC::CacheError) { OTC.new(release: D, cache_dir: cache, offline: true) }
    end

    # R2-091: a releases directory that cannot be listed is a cache error,
    # not an empty cache (offline_unavailable).
    def test_unlistable_releases_dir_is_cache
        posix_only
        srv = serve
        cache = tmpdir
        OTC.new(release: D, base_url: srv.url("/"), cache_dir: cache).close
        rels = File.join(cache, "v1", "releases")
        FileUtils.chmod(0o000, rels)
        assert_raises(OTC::CacheError) { OTC.new(cache_dir: cache, offline: true) }
    ensure
        FileUtils.chmod(0o755, rels) if rels
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
        # The race happened: the check read .verified (and it was then
        # deleted), and the load read it again and found it gone.
        assert_operator seen, :>=, 2
        refute File.exist?(ver)
        before = srv.requests.size
        rel = c.send(:fetch_release, D, nil, nil)
        assert_kind_of OTC::Release, rel
        assert_includes srv.requests[before..], "/OTC_#{D}.sha256", "the release was not downloaded again"
        assert File.file?(ver)
    ensure
        rel&.send(:close)
        c&.close
    end
end
