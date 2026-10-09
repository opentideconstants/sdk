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
        File.write(File.join(lock, "owner.json"), JSON.generate("started_at" => "2000-01-01T00:00:00Z")) # old: stale (CR2 DR3)
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
        assert(log.lines.any? { |lvl, m| lvl == :warn && m.include?(".lock") }, log.lines.inspect)
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

    # R23: prune raises cache when a release cannot be removed, and the
    # release stays cached.
    def test_prune_failure_is_a_cache_error
        posix_only
        srv = serve
        cache, c = two_cached(srv)
        old = File.join(cache, "v1", "releases", "20991231")
        FileUtils.chmod(0o555, old)
        assert_raises(OTC::CacheError) { c.prune(keep: 1) }
        FileUtils.chmod(0o755, old)
        assert_equal %w[20991231.2 20991231], c.cached_releases
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
        c.prune(keep: 5)
        refute File.exist?(partial)
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

    # ---- spec §5.4 (CR2 DR3): a lock is stale only when the waiter has
    # waited the stale time and the lock itself is at least 120 s old. These
    # tests shorten the wait; the age stays 120 s, and the lock's age is set
    # by its started_at or its mtime, so the outcome does not depend on timing.

    def held_lock(cache, ds, started_at: nil, mtime: nil)
        dir = cache.ensure_dir(cache.release_dir(ds))
        lock = File.join(dir, ".lock")
        Dir.mkdir(lock)
        File.write(File.join(lock, "owner.json"), JSON.generate("token" => "other", "started_at" => started_at)) if started_at
        File.utime(mtime, mtime, lock) if mtime
        [dir, lock]
    end

    def owner_token(lock)
        JSON.parse(File.read(File.join(lock, "owner.json")))["token"]
    end

    def test_a_waiter_does_not_remove_a_young_lock
        cache = quick_cache
        dir, lock = held_lock(cache, "20991231", started_at: Time.now.utc.iso8601)
        polls = 0
        ran = false
        # done ends the wait after 30 polls: 7.5 times the (shortened) stale wait
        result = cache.with_lock(dir, done: -> { (polls += 1) >= 30 }) { ran = true }
        refute ran, "a waiter took a lock that is only seconds old"
        assert_equal :done, result
        assert_equal "other", owner_token(lock)
    end

    def test_a_waiter_takes_an_old_lock_by_started_at_or_by_mtime
        cache = quick_cache
        [{ started_at: "2000-01-01T00:00:00Z" }, { mtime: Time.at(946_684_800) }].each_with_index do |how, i|
            dir, lock = held_lock(cache, "2099123#{i}", **how)
            token = nil
            cache.with_lock(dir) { token = owner_token(lock) }
            refute_nil token
            refute_equal "other", token
        end
    end

    def test_two_waiters_on_a_crashed_lock_never_hold_it_together
        cache = quick_cache
        dir, = held_lock(cache, "20991231", started_at: "2000-01-01T00:00:00Z")
        first_in = Queue.new
        second_in = Queue.new
        overlap = []
        mutex = Mutex.new
        first = true
        # the second waiter starts once the first holds the lock, so it meets a
        # young lock (two waiters that read the crashed lock's age at the same
        # instant can still both remove it; spec §5.4 accepts that)
        waiters = 2.times.map do |i|
            first_in.pop.tap { |x| first_in << x } if i == 1
            Thread.new do
                cache.with_lock(dir) do
                    am_first = mutex.synchronize { f = first; first = false; f }
                    if am_first
                        first_in << true
                        # the other waiter has waited past the stale time; it must not take this young lock
                        overlap << !second_in.pop(timeout: 1.0).nil?
                    else
                        second_in << true
                    end
                end
            end
        end
        waiters.each { |t| t.join(10) }
        assert_equal [false], overlap, "two waiters held the lock at the same time"
        assert_equal 1, second_in.size, "the second waiter never took the lock"
    end

    # R2-011/R2-013: prune takes the lock without waiting and applies the age
    # test, so the lock of a crashed process does not keep a release forever,
    # also a partial directory that never got a .verified.
    def test_prune_removes_a_partial_directory_with_a_crashed_lock_and_keeps_a_young_one
        srv = serve
        cache, c = two_cached(srv)
        old = File.join(cache, "v1", "releases", "20991230")
        young = File.join(cache, "v1", "releases", "20991229")
        [old, young].each { |d| FileUtils.mkdir_p(File.join(d, ".lock")) }
        File.write(File.join(old, ".lock", "owner.json"), JSON.generate("token" => "x", "started_at" => "2000-01-01T00:00:00Z"))
        c.prune(keep: 5)
        refute File.exist?(old), "prune kept a partial directory whose lock a crashed process left"
        assert File.directory?(File.join(young, ".lock")), "prune removed a partial directory that another process holds"
    ensure
        c&.close
    end

    # R2-016: the DOI note rewrites .verified under the release lock, taken
    # without waiting: it is skipped while another process holds a young
    # lock, and it recovers an old one.
    def test_the_doi_note_takes_the_release_lock
        srv = serve
        cache_dir, c = two_cached(srv)
        c.close
        cache = OTC::Cache.new(cache_dir)
        ver = File.join(cache.release_dir("20991231"), ".verified")
        _, lock = held_lock(cache, "20991231", started_at: Time.now.utc.iso8601)
        before = File.read(ver)
        cache.note_version_doi("20991231", "10.5072/zenodo.77")
        assert_equal before, File.read(ver), "the DOI note rewrote .verified while another process held the lock"
        File.write(File.join(lock, "owner.json"), JSON.generate("token" => "other", "started_at" => "2000-01-01T00:00:00Z"))
        cache.note_version_doi("20991231", "10.5072/zenodo.77")
        assert_equal "10.5072/zenodo.77", JSON.parse(File.read(ver))["zenodo_version_doi"]
        refute File.exist?(lock), "the DOI note did not release the lock it took"
    end
end
