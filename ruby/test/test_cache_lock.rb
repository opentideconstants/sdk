# The cache lock, .verified writes and prune (spec §4.3, §5.4, CR D3, D26).
require_relative "support"

class CacheLockTest < Minitest::Test
    include TestSupport
    OTC = OpenTideConstants

    def posix_only
        skip "needs POSIX permissions" if Gem.win_platform? || Process.uid.zero?
    end

    def quick_cache(log = nil)
        OTC::Cache.new(tmpdir, logger: log, lock_stale_s: 0.2, lock_poll_s: 0.05)
    end

    # R3: a stale lock that cannot be removed is a cache error after 3
    # attempts, not an endless loop (CR D3).
    def test_unremovable_stale_lock_is_a_cache_error
        posix_only
        cache = quick_cache
        dir = cache.ensure_dir(cache.release_dir("20991231"))
        lock = File.join(dir, ".lock")
        Dir.mkdir(lock)
        File.write(File.join(lock, "owner.json"), "{}")
        FileUtils.chmod(0o555, lock)
        t = Thread.new { cache.with_lock(dir) { :ran } }
        t.report_on_exception = false
        assert_raises(OTC::CacheError) { t.join(10) or flunk("with_lock is still looping on a lock it cannot remove") }
    ensure
        t&.kill
    end

    # R3: the lock carries a token, and the holder releases it only when the
    # token is still its own (another process may have taken it as stale).
    def test_release_leaves_a_lock_that_another_process_took
        cache = OTC::Cache.new(tmpdir)
        dir = cache.ensure_dir(cache.release_dir("20991231"))
        lock = File.join(dir, ".lock")
        cache.with_lock(dir) do
            owner = JSON.parse(File.read(File.join(lock, "owner.json")))
            assert_match(/\A[0-9a-f]{32,}\z/, owner["token"])
            File.write(File.join(lock, "owner.json"), JSON.generate(owner.merge("token" => "someone-else")))
        end
        assert File.directory?(lock), "the holder removed a lock that is no longer its own"
    end

    # R3: a lock that cannot be removed at release is logged, not swallowed.
    def test_release_failure_is_logged
        log = Log.new
        cache = quick_cache(log)
        dir = cache.ensure_dir(cache.release_dir("20991231"))
        cache.with_lock(dir) { File.write(File.join(dir, ".lock", "stray"), "x") }
        # The release-failure warning itself, not another lock warning (stale, or held by another process).
        assert(log.lines.any? { |lvl, m| lvl == :warn && m.include?("cannot release the lock #{File.join(dir, '.lock')}") },
               log.lines.inspect)
        assert File.directory?(File.join(dir, ".lock"))
    end

    # R73 + D26: a download whose entry has no zenodo_version_doi keeps the
    # stored DOI, and .verified has the datestamp.
    def test_entry_without_doi_keeps_the_stored_doi
        over = {}
        srv = serve(File.join(FIXTURES, "good"), over)
        cache = tmpdir
        OTC.new(base_url: srv.url("/"), cache_dir: cache).close
        ver_path = File.join(cache, "v1", "releases", "20991231.2", ".verified")
        assert_equal "10.5072/zenodo.2", JSON.parse(File.read(ver_path))["zenodo_version_doi"]
        no_doi = JSON.parse(File.read(fixture("good", "OTC_latest-f1.json")))
        no_doi.delete("zenodo_version_doi")
        over["OTC_latest-f1.json"] = [200, {}, JSON.generate(no_doi)]
        OTC.new(base_url: srv.url("/"), cache_dir: cache, mode: :stream).close
        ver = JSON.parse(File.read(ver_path))
        assert ver["files"].key?("OTC_20991231.2.jsonl")
        assert_equal "10.5072/zenodo.2", ver["zenodo_version_doi"]
        assert_equal "20991231.2", ver["datestamp"]
    end

    def two_cached(srv)
        cache = tmpdir
        OTC.new(release: "20991231", base_url: srv.url("/"), cache_dir: cache).close
        c = OTC.new(release: "20991231.2", base_url: srv.url("/"), cache_dir: cache)
        [cache, c]
    end

    # R23: prune raises cache when a release cannot be removed. Two ways:
    # its lock cannot be taken (nothing is removed, and it stays cached), and
    # a file in it cannot be removed (its .verified goes first, so it is no
    # longer trusted). The release kept stays cached in both.
    def test_prune_failure_is_a_cache_error
        posix_only
        srv = serve
        cache, c = two_cached(srv)
        old = File.join(cache, "v1", "releases", "20991231")
        begin
            FileUtils.chmod(0o555, old)
            err = assert_raises(OTC::CacheError) { c.prune(keep: 1) }
            assert_match(/cannot take the lock/, err.message)
        ensure
            FileUtils.chmod(0o755, old)
        end
        assert_equal %w[20991231.2 20991231], c.cached_releases

        stuck = File.join(old, "stuck")
        Dir.mkdir(stuck)
        File.write(File.join(stuck, "file"), "x")
        begin
            FileUtils.chmod(0o555, stuck) # the lock can be taken; the file in stuck cannot be removed
            err = assert_raises(OTC::CacheError) { c.prune(keep: 1) }
            assert_match(/cannot remove #{Regexp.escape(old)}/, err.message)
            assert File.file?(File.join(stuck, "file"))
        ensure
            FileUtils.chmod(0o755, stuck)
        end
        assert_equal %w[20991231.2], c.cached_releases
        refute File.exist?(File.join(old, ".lock")), "the failed removal left its lock"
        refute_nil c.station("OTC-T-0001")
    ensure
        c&.close
    end

    # R23b: prune skips a release whose lock another process holds.
    def test_prune_skips_a_locked_release
        srv = serve
        cache, c = two_cached(srv)
        lock = File.join(cache, "v1", "releases", "20991231", ".lock")
        Dir.mkdir(lock)
        File.write(File.join(lock, "owner.json"), JSON.generate("token" => "other", "started_at" => Time.now.utc.iso8601))
        assert_equal [], c.prune(keep: 1)
        assert_includes c.cached_releases, "20991231"
    ensure
        c&.close
    end

    # R16x: prune removes a release directory that never got a .verified (a
    # failed or interrupted download) when no one holds its lock.
    def test_prune_removes_partial_directories
        srv = serve
        cache, c = two_cached(srv)
        partial = File.join(cache, "v1", "releases", "20991230")
        FileUtils.mkdir_p(partial)
        File.write(File.join(partial, ".tmp-1-abc"), "x" * 100)
        assert_equal [], c.prune(keep: 5)
        refute File.exist?(partial)
        assert_equal %w[20991231.2 20991231], c.cached_releases
    ensure
        c&.close
    end

    # R18x: prune never removes a release that the caller still holds from
    # before an update (spec §4.3 update: "stays valid").
    def test_prune_keeps_a_release_held_from_before_an_update
        over = {}
        srv = serve(File.join(FIXTURES, "good"), over)
        old_ptr = JSON.parse(File.read(fixture("good", "OTC_index.json")))["releases"].find { |e| e["datestamp"] == "20991231" }
        over["OTC_latest-f1.json"] = [200, {}, JSON.generate(old_ptr)]
        cache = tmpdir
        c = OTC.new(base_url: srv.url("/"), cache_dir: cache, mode: :stream)
        held = c.release
        assert_equal "20991231", held.datestamp
        over.delete("OTC_latest-f1.json")
        assert c.update!.updated
        assert_equal [], c.prune(keep: 0)
        assert File.file?(File.join(cache, "v1", "releases", "20991231", ".verified"))
        refute_nil held.station("OTC-T-0001")
    ensure
        c&.close
    end
end
