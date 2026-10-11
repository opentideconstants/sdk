# Error classification (CR2 PK-R2-11): every failure leaves the SDK as an SDK
# error with the spec §4.8 code; a local failure is never network, a
# permanent failure is never retried.
require_relative "support"

# While on, a file that File.open opens fails to close (after it is closed), as a close that reports EIO does.
module FailingClose
    class << self
        attr_accessor :on
    end

    def open(*args, **kw, &blk)
        f = super
        if FailingClose.on && f.is_a?(File)
            def f.close
                super
                raise IOError, "close failed (EIO)"
            end
        end
        f
    end
end
File.singleton_class.prepend(FailingClose)

class ErrorClassificationTest < Minitest::Test
    include TestSupport
    OTC = OpenTideConstants
    D = "20991231.2".freeze

    # A TCP listener that only counts the connections it gets.
    def trap_listener
        srv = TCPServer.new("127.0.0.1", 0)
        hits = []
        t = Thread.new do
            loop do
                s = srv.accept
                hits << 1
                s.close
            end
        rescue IOError
            nil
        end
        [srv.addr[1], hits, -> { t.kill; srv.close rescue nil }]
    end

    # R2-100: a redirect Location with no host is not followed: it is a
    # network error at once, never a connection to localhost.
    def test_redirect_with_no_host_is_not_followed
        port, hits, stop = trap_listener
        s = serve(File.join(FIXTURES, "good"), "/x" => [302, { "Location" => "//:#{port}/x" }, ""])
        waits = []
        http = OTC::HTTP.new(sleeper: ->(w) { waits << w })
        err = assert_raises(OTC::NetworkError) { http.get(s.url("/x")) }
        assert_match(/no host/i, err.message)
        assert_empty hits, "a connection was made to localhost"
        assert_empty waits, "a redirect with no host was retried"
    ensure
        stop&.call
    end

    # R2-101: a cached OTC_latest.json that cannot be read must not replace
    # the reader_too_old that check_for_update raises.
    def test_unreadable_cached_generic_pointer_keeps_reader_too_old
        s = serve
        cache = tmpdir
        c = OTC.new(base_url: s.url, cache_dir: cache)
        # the server now has only a release too new for this SDK
        bad = serve(File.join(FIXTURES, "bad", "min-reader"))
        c.instance_variable_set(:@base_url, bad.url)
        p = File.join(cache, "v1", "pointer", "OTC_latest.json")
        File.write(p, "{}")
        File.chmod(0o000, p)
        skip "running as root: a mode 000 file is readable" if File.readable?(p)
        assert_raises(OTC::ReaderTooOldError) { c.check_for_update }
    ensure
        File.chmod(0o644, p) if p && File.exist?(p)
        c&.close
    end

    # R2-102: a failure to close the local file a body is written to is a
    # local error (SinkError), not a network error, and is not retried.
    def test_close_failure_of_the_sink_is_not_network
        s = serve
        waits = []
        http = OTC::HTTP.new(sleeper: ->(w) { waits << w })
        path = File.join(tmpdir, "out")
        FailingClose.on = true
        begin
            assert_raises(OTC::HTTP::SinkError) { http.get_to_file(s.url("/OTC_#{D}.sha256"), path) }
        ensure
            FailingClose.on = false
        end
        assert_empty waits, "a local close failure was retried as network"
    end

    # R2-103: when a bad cached copy cannot be deleted, download still
    # fetches the file instead of failing with the CacheError.
    def test_download_fetches_when_a_bad_cached_copy_cannot_be_deleted
        posix_only # as root or on Windows the read-only directory does not stop the delete
        s = serve
        cache = tmpdir
        log = Log.new
        c = OTC.new(release: D, base_url: s.url, cache_dir: cache, mode: :stream, logger: log)
        dir = File.join(cache, "v1", "releases", D)
        jl = File.join(dir, "OTC_#{D}.jsonl")
        bytes = File.binread(jl)
        bytes.setbyte(100, bytes.getbyte(100) ^ 1)
        File.binwrite(jl, bytes)
        File.chmod(0o555, dir)
        to = File.join(tmpdir, "bundle")
        paths = c.download(D, to: to)
        assert_includes paths, File.join(to, "OTC_#{D}.jsonl")
        assert_equal Digest::SHA256.file(fixture("good", "OTC_#{D}.jsonl")).hexdigest,
                     Digest::SHA256.file(File.join(to, "OTC_#{D}.jsonl")).hexdigest
        # The delete did fail (the bad copy is still cached), and download said so and fetched anyway.
        assert_equal bytes, File.binread(jl), "the bad cached copy was deleted: the CacheError path did not run"
        assert(log.lines.any? { |lvl, m| lvl == :warn && m.include?("downloading OTC_#{D}.jsonl anyway") },
               "the failed delete was not logged: #{log.lines.inspect}")
    ensure
        File.chmod(0o755, dir) if dir && File.directory?(dir)
        c&.close
    end

    # R2-104: close closes every release, also after one close fails, and
    # reports the failure as an SDK error.
    def test_close_closes_every_release_when_one_fails
        s = serve
        cache = tmpdir
        c = OTC.new(release: D, base_url: s.url, cache_dir: cache, mode: :stream)
        oc = OTC.new(release: "20991231", base_url: s.url, cache_dir: cache, mode: :stream)
        other = oc.release
        c.instance_variable_get(:@loaded)[other] = true # a release this client loaded before an update
        ios = [c.release, other].map { |r| r.instance_variable_get(:@io) }
        def (ios[0]).close
            super
            raise IOError, "close failed"
        end
        err = assert_raises(OTC::FileError) { c.close }
        assert_kind_of IOError, err.cause
        assert ios.all?(&:closed?), "a release was left open"
        assert_nil c.close, "a second close did something"
    ensure
        [c, oc].each do |x|
            x&.close
        rescue OTC::FileError, IOError
            nil # the injected close failure, when the test stopped before its own close
        end
    end

    # R2-105: Net::HTTP cannot speak TLS to a proxy; an https:// proxy is
    # refused when the client is made, not used in plaintext.
    def test_https_proxy_is_refused_at_construction
        s = serve
        assert_raises(OTC::InvalidArgumentError) do
            OTC.new(base_url: s.url, cache_dir: tmpdir, proxy: "https://127.0.0.1:9/")
        end
        assert_empty s.requests
    end

    # R2-106: a TLS hostname mismatch does not get better on a retry. (With OpenSSL 1.1+ the handshake reports it
    # as "certificate verify failed (hostname mismatch)", which is not retried; this keeps it that way.)
    def test_tls_hostname_mismatch_is_not_retried
        port, ca, stop = tls_server { |_p, _h| [200, {}, "x"] }
        waits = []
        http = OTC::HTTP.new(ca_file: ca, sleeper: ->(w) { waits << w })
        # Control: the certificate (for 127.0.0.1) is trusted through ca_file, so the only defect below is the name.
        assert_equal 200, http.get("https://127.0.0.1:#{port}/x").status
        err = assert_raises(OTC::NetworkError) { http.get("https://localhost:#{port}/x") }
        assert_match(/hostname/i, err.message, "not the hostname mismatch")
        assert_empty waits, "a hostname mismatch was retried"
    ensure
        stop&.call
    end
end
