# The cache lock, .verified writes and prune (spec §4.3, §5.4, CR D3, D26).
require_relative "support"

class CacheLockTest < Minitest::Test
    include TestSupport
    OTC = OpenTideConstants

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

    def test_mode_acquisition_emits_only_the_three_verified_row_fields
        srv = serve
        cache = tmpdir
        OTC.new(base_url: srv.url("/"), cache_dir: cache).close
        path = File.join(cache, "v1", "releases", "20991231.2", ".verified")
        before = JSON.parse(File.binread(path))
        before["files"].each_value do |row|
            row["private_field"] = "an older writer's field"
            row.delete("url")
        end
        File.binwrite(path, JSON.generate(before))
        OTC.new(release: "20991231.2", base_url: srv.url("/"), cache_dir: cache, mode: :stream).close
        ver = JSON.parse(File.binread(path))
        assert_equal %w[by datestamp files format_version min_reader_version verified_at zenodo_version_doi], ver.keys.sort
        assert_equal 3, ver["files"].size
        ver["files"].each_value { |row| assert_equal %w[sha256 size url], row.keys.sort }
        assert_nil ver["files"]["OTC_20991231.2.json"]["url"]
        assert_equal "10.5072/zenodo.2", ver["zenodo_version_doi"]
    end

    def test_public_doi_note_uses_the_exact_cache_encoder
        srv = serve
        cache = tmpdir
        c = OTC.new(release: "20991231.2", base_url: srv.url("/"), cache_dir: cache, mode: :stream)
        c.releases
        path = File.join(cache, "v1", "releases", "20991231.2", ".verified")
        bytes = File.binread(path)
        ver = JSON.parse(bytes)
        assert_equal "10.5072/zenodo.2", ver["zenodo_version_doi"]
        assert_equal OTC::Cache.encode_cache_json(ver), bytes
    ensure
        c&.close
    end

    def test_held_release_observes_same_stamp_doi_updates
        pointer = JSON.parse(File.read(fixture("good", "OTC_latest-f1.json")))
        doi = "10.5072/zenodo.changed"
        %i[latest check_for_update update! releases].each do |operation|
            over = {}
            srv = serve(File.join(FIXTURES, "good"), over)
            cache = tmpdir
            client = OTC.new(base_url: srv.url("/"), cache_dir: cache, mode: :stream)
            held = client.release
            raw = held.station("OTC-T-0001").raw
            marker_path = File.join(cache, "v1/releases", held.datestamp, ".verified")
            marker = JSON.parse(File.read(marker_path))
            entry = pointer.merge("zenodo_version_doi" => doi)
            over["OTC_latest-f1.json"] = [200, {}, JSON.generate(entry)]
            over["OTC_latest.json"] = [200, {}, JSON.generate(entry)]
            over["OTC_index.json"] = [200, {}, JSON.generate("releases" => [entry])]
            client.public_send(operation)
            assert_equal doi, held.zenodo_version_doi
            assert_equal doi, client.release.zenodo_version_doi
            assert_includes held.citation, "https://doi.org/#{doi}"
            assert_equal raw, held.station("OTC-T-0001").raw
            assert held.frozen?
            assert raw.frozen?
            refute held.respond_to?(:zenodo_version_doi=)
            marker["zenodo_version_doi"] = doi
            assert_equal marker, JSON.parse(File.read(marker_path))
            client.close
            assert_equal doi, held.zenodo_version_doi
        ensure
            client&.close
        end
    end

    def test_empty_version_doi_keeps_metadata_but_omits_citation_suffix
        stamp = "20991231.2"
        expected_raw = JSON.parse(File.binread(fixture("good", "OTC_#{stamp}.json")))["stations"].first
        observations = []
        [["json", :eager], ["jsonl", :eager], ["jsonl", :stream]].each do |format, mode|
            ["", nil, "10.5072/zenodo.2"].each do |doi|
                cache = OTC::Cache.new(tmpdir)
                directory = cache.ensure_dir(cache.release_dir(stamp))
                names = ["OTC_#{stamp}.#{format}", "OTC_#{stamp}.meta.json", "OTC_#{stamp}.sha256"]
                names.each { |name| FileUtils.cp(fixture("good", name), directory) }
                files = names.reject { |name| name.end_with?(".sha256") }.to_h do |name|
                    path = File.join(directory, name)
                    [name, { "sha256" => Digest::SHA256.file(path).hexdigest, "size" => File.size(path), "url" => nil }]
                end
                cache.with_lock(directory) do
                    cache.write_verified(stamp, files, "format_version" => "1.0", "min_reader_version" => "1.0", "zenodo_version_doi" => doi)
                end
                marker_path = File.join(directory, ".verified")
                marker_before = File.binread(marker_path)
                data_pins = names.to_h { |name| [name, Digest::SHA256.file(File.join(directory, name)).hexdigest] }
                client = OTC.new(release: stamp, cache_dir: cache.root, offline: true, mode: mode, verify_on_open: true)
                release = client.release
                base = "OpenTideConstants contributors (2099). OpenTideConstants, release #{stamp} [Data set]. https://doi.org/10.5072/zenodo.1"
                expected = doi.nil? || doi.empty? ? base : "#{base} (version DOI: https://doi.org/#{doi})"
                actual = release.citation
                doi.nil? ? assert_nil(release.zenodo_version_doi) : assert_equal(doi, release.zenodo_version_doi)
                assert_equal expected_raw, client.station(expected_raw.fetch("station_id")).raw
                assert_equal marker_before, File.binread(marker_path)
                assert data_pins.all? { |name, digest| Digest::SHA256.file(File.join(directory, name)).hexdigest == digest }
                client.close
                assert_equal actual, release.citation
                observations << { format: format, mode: mode.to_s, doi: doi, expected_citation: expected, actual_citation: actual, citation_matches: actual == expected, raw_preserved: true, metadata_preserved: true, receipt_preserved: true, data_preserved: true }
            ensure
                client&.close
            end
        end
        if (proof_path = ENV["OTC_EMPTY_DOI_PROOF_PATH"])
            File.write(proof_path, JSON.pretty_generate(observations) + "\n")
        end
        assert_empty observations.reject { |observation| observation[:citation_matches] }
    end

    def test_doi_note_preserves_uppercase_receipt_and_verified_cached_open
        c = nil
        stamp = "20991231.2"
        expected_raw = JSON.parse(File.binread(fixture("good", "OTC_#{stamp}.json")))["stations"].find { |row| row["station_id"] == "OTC-T-0001" }
        [[ :eager, %w[json] ], [ :eager, %w[jsonl meta.json] ], [ :stream, %w[jsonl meta.json] ]].each do |mode, extensions|
            root = tmpdir
            dir = File.join(root, "v1", "releases", stamp)
            FileUtils.mkdir_p(dir)
            payloads = extensions.to_h do |ext|
                name = "OTC_#{stamp}.#{ext}"
                bytes = File.binread(fixture("good", name))
                File.binwrite(File.join(dir, name), bytes)
                [name, bytes]
            end
            rows = payloads.to_h do |name, bytes|
                [name, { "size" => bytes.bytesize, "sha256" => Digest::SHA256.hexdigest(bytes).upcase,
                         "future_file" => { "retain" => true } }]
            end
            receipt = { "datestamp" => stamp, "files" => rows, "by" => "original-producer", "verified_at" => "2026-10-01T00:00:00Z",
                        "zenodo_version_doi" => "10.1/old", "future_receipt" => [7, true] }
            marker = File.join(dir, ".verified")
            File.binwrite(marker, JSON.generate(receipt))
            OTC::Cache.new(root).note_version_doi(stamp, "10.1/new")
            noted_bytes = File.binread(marker)
            assert_equal receipt.merge("zenodo_version_doi" => "10.1/new"), JSON.parse(noted_bytes)

            c = OTC.new(cache_dir: root, release: stamp, mode: mode, offline: true, verify_on_open: true)
            assert_equal :cache, c.loaded_from
            assert_equal expected_raw, c.station("OTC-T-0001").raw
            assert_equal noted_bytes, File.binread(marker)
            payloads.each do |name, bytes|
                assert_equal bytes, File.binread(File.join(dir, name))
                assert_equal rows[name]["sha256"].downcase, c.release.files.find { |file| file.name == name }.sha256
            end
            c.close
            c = nil
        end
    ensure
        c&.close
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

    # CR2 DR18: prune stops at the first release it cannot remove, and the
    # CacheError reports the releases removed before it, newest first.
    def test_prune_failure_reports_what_was_removed
        posix_only
        srv = serve
        cache = tmpdir
        %w[20991231 20991231.2].each { |d| OTC.new(release: d, base_url: srv.url("/"), cache_dir: cache).close }
        # a third release, older than 20991231, that cannot be removed
        old = File.join(cache, "v1", "releases", "20991230")
        FileUtils.cp_r(File.join(cache, "v1", "releases", "20991231"), old)
        verified_path = File.join(old, ".verified")
        File.write(verified_path, JSON.generate(JSON.parse(File.read(verified_path)).merge("datestamp" => "20991230")))
        c = OTC.new(release: "20991231.2", base_url: srv.url("/"), cache_dir: cache)
        FileUtils.chmod(0o555, old)
        e = assert_raises(OTC::CacheError) { c.prune(keep: 0) }
        FileUtils.chmod(0o755, old)
        assert_equal %w[20991231], e.removed
        assert_equal %w[20991231.2 20991230], c.cached_releases
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
        File.utime(Time.now - 180, Time.now - 180, partial)
        assert_equal [], c.prune(keep: 5)
        refute File.exist?(partial)
        assert_equal %w[20991231.2 20991231], c.cached_releases
    ensure
        c&.close
    end

    def test_prune_keeps_young_unlocked_partial_without_refreshing_its_age
        cache = tmpdir
        partial = File.join(cache, "v1", "releases", "20991230")
        FileUtils.mkdir_p(partial)
        payload = File.join(partial, "source-record-original")
        bytes = "source record and provenance retained"
        File.binwrite(payload, bytes)
        at = Time.now - 60
        File.utime(at, at, partial)
        original_mtime = File.mtime(partial)
        c = OTC.new(file: fixture("good", "OTC_20991231.2.json"), cache_dir: cache)
        original_raw = JSON.generate(c.station("OTC-T-0001").raw)

        assert_equal [], c.cached_releases
        assert_equal [], c.prune(keep: 0)
        assert File.directory?(partial), "prune removed a young, unlocked partial directory"
        assert_equal bytes, File.binread(payload)
        assert_equal original_mtime, File.mtime(partial), "prune refreshed a young partial directory's age"
        refute File.exist?(File.join(partial, ".lock"))
        refute File.exist?(File.join(partial, ".verified"))
        assert_equal original_raw, JSON.generate(c.station("OTC-T-0001").raw)
    ensure
        c&.close
    end

    def test_prune_preserves_external_data_behind_partial_release_symlinks
        posix_only
        c = nil
        { "empty-marker" => "{}", "broken-json" => "{broken json", "absent-marker" => nil }.each do |label, marker|
            root = tmpdir
            external = File.join(root, "external-user-data")
            releases = File.join(root, "cache", "v1", "releases")
            FileUtils.mkdir_p([external, releases])
            File.binwrite(File.join(external, "source-record-original"), "external record and provenance #{label}\n")
            File.binwrite(File.join(external, ".verified"), marker) if marker
            link = File.join(releases, "20991231.30")
            File.symlink("../../../external-user-data", link)
            File.utime(Time.now - 300, Time.now - 300, external)
            original_mtime = File.mtime(external)
            originals = Dir.children(external).to_h { |name| [name, File.binread(File.join(external, name))] }
            c = OTC.new(file: fixture("good", "OTC_20991231.2.json"), cache_dir: File.join(root, "cache"))
            original_raw = JSON.generate(c.station("OTC-T-0001").raw)

            assert_equal [], c.prune(keep: 0), label
            assert_equal originals.keys.sort, Dir.children(external).sort, label
            originals.each { |name, bytes| assert_equal bytes, File.binread(File.join(external, name)), label }
            assert_equal original_mtime, File.mtime(external), label
            assert File.symlink?(link), label
            assert_equal "../../../external-user-data", File.readlink(link), label
            refute File.exist?(File.join(external, ".lock")), label
            assert_equal original_raw, JSON.generate(c.station("OTC-T-0001").raw), label
            c.close
            c = nil
        end
    ensure
        c&.close
    end

    # R13-A1: prune protects only the current release directory. On POSIX,
    # an earlier held stream release still reads its removed files.
    def test_prune_removes_an_earlier_held_release_and_keeps_the_current_one
        posix_only
        over = {}
        srv = serve(File.join(FIXTURES, "good"), over)
        old_ptr = JSON.parse(File.read(fixture("good", "OTC_index.json")))["releases"].find { |e| e["datestamp"] == "20991231" }
        over["OTC_latest-f1.json"] = [200, {}, JSON.generate(old_ptr)]
        cache = tmpdir
        c = OTC.new(base_url: srv.url("/"), cache_dir: cache, mode: :stream)
        held = c.release
        assert_equal "20991231", held.datestamp
        original = held.station("OTC-T-0021")
        before = original.raw
        over.delete("OTC_latest-f1.json")
        assert c.update!.updated
        assert_equal %w[20991231], c.prune(keep: 0)
        refute File.exist?(File.join(cache, "v1", "releases", "20991231"))
        assert File.file?(File.join(cache, "v1", "releases", "20991231.2", ".verified"))
        assert_equal %w[20991231.2], c.cached_releases
        assert_nil c.station("OTC-T-0021")
        assert_equal before, held.station("OTC-T-0021").raw
    ensure
        c&.close
    end

    # A file client does not own the cache copy with the same datestamp.
    def test_prune_from_a_file_does_not_protect_a_matching_cache_release
        srv = serve
        cache, cached = two_cached(srv)
        cached.close
        c = OTC.new(file: fixture("good", "OTC_20991231.2.jsonl"), cache_dir: cache, mode: :stream)
        before = c.station("OTC-T-0001").raw
        assert_equal %w[20991231.2 20991231], c.prune(keep: 0)
        assert_equal [], c.cached_releases
        assert File.file?(fixture("good", "OTC_20991231.2.jsonl"))
        assert_equal before, c.station("OTC-T-0001").raw
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

    def test_real_public_stream_wait_refreshes_its_lock
        cache = tmpdir
        lock = File.join(cache, "v1", "releases", "20991231.2", ".lock")
        snapshots = []
        heartbeat_threads = []
        threads = Thread.list
        started = Process.clock_gettime(Process::CLOCK_MONOTONIC)
        body = File.binread(fixture("good", "OTC_20991231.2.jsonl"))
        srv = serve(File.join(FIXTURES, "good"), "OTC_20991231.2.jsonl" => lambda do |_path|
            heartbeat_threads = (Thread.list - threads).select { |thread| Array(thread.backtrace).any? { |line| line.include?("/opentideconstants/cache.rb:") } }
            snapshots << [JSON.parse(File.read(File.join(lock, "owner.json"))), File.mtime(lock)]
            sleep(32)
            snapshots << [JSON.parse(File.read(File.join(lock, "owner.json"))), File.mtime(lock)]
            [200, {}, body]
        end)
        threads = Thread.list
        c = OTC.new(release: "20991231.2", base_url: srv.url("/"), cache_dir: cache, mode: :stream, on_network_error: :raise)
        assert_operator Process.clock_gettime(Process::CLOCK_MONOTONIC) - started, :>=, 32
        assert_equal snapshots[0][0]["token"], snapshots[1][0]["token"]
        refute_equal snapshots[0][0]["started_at"], snapshots[1][0]["started_at"]
        assert_operator snapshots[1][1], :>, snapshots[0][1]
        assert_equal "OTC-T-0001", c.station("OTC-T-0001").station_id
        assert_equal body, File.binread(File.join(File.dirname(lock), "OTC_20991231.2.jsonl"))
        refute File.exist?(lock)
        assert_equal 1, heartbeat_threads.size
        refute heartbeat_threads.any?(&:alive?), "the cache heartbeat survived lock release"
    ensure
        c&.close
    end

    def test_heartbeat_stops_before_exception_release
        cache = quick_cache
        dir = cache.ensure_dir(cache.release_dir("20991231"))
        before = Thread.list
        error = assert_raises(RuntimeError) { cache.with_lock(dir) { raise "held operation failed" } }
        assert_equal "held operation failed", error.message
        refute File.exist?(File.join(dir, ".lock"))
        assert_empty Thread.list - before
    end

    def test_real_heartbeat_failure_is_warned_and_timer_stops
        posix_only
        log = Log.new
        cache = quick_cache(log)
        dir = cache.ensure_dir(cache.release_dir("20991231"))
        lock = File.join(dir, ".lock")
        before = Thread.list
        cache.with_lock(dir) do
            begin
                FileUtils.chmod(0o555, lock)
                sleep(32)
                assert(log.lines.any? { |level, message| level == :warn && message.include?("cannot refresh the lock #{lock}") }, log.lines.inspect)
            ensure
                FileUtils.chmod(0o755, lock)
            end
        end
        refute File.exist?(lock)
        assert_empty Thread.list - before
    end

    def test_real_heartbeat_leaves_a_foreign_owner_unchanged
        log = Log.new
        cache = quick_cache(log)
        dir = cache.ensure_dir(cache.release_dir("20991231"))
        lock = File.join(dir, ".lock")
        path = File.join(lock, "owner.json")
        before = Thread.list
        foreign = nil
        cache.with_lock(dir) do
            foreign = JSON.generate(JSON.parse(File.read(path)).merge("token" => "someone-else"))
            File.write(path, foreign)
            mtime = File.mtime(lock)
            sleep(32)
            assert_equal foreign, File.read(path)
            assert_equal mtime, File.mtime(lock)
        end
        assert_equal foreign, File.read(path)
        assert File.directory?(lock)
        assert_empty Thread.list - before
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
        waiters = []
        2.times do |i|
            # every wait is bounded: a waiter that raises before it pushes fails the test, it does not hang it
            (pop_within(first_in, 10) or flunk("the first waiter never took the lock")).tap { |x| first_in << x } if i == 1
            waiters << Thread.new do
                cache.with_lock(dir) do
                    am_first = mutex.synchronize { f = first; first = false; f }
                    if am_first
                        first_in << true
                        # the other waiter has waited past the stale time; it must not take this young lock
                        overlap << !pop_within(second_in, 1.0).nil?
                    else
                        second_in << true
                    end
                end
            end
        end
        waiters.each { |t| t.join(10) or flunk("a waiter is still waiting after 10 s") }
        assert_equal [false], overlap, "two waiters held the lock at the same time"
        assert_equal 1, second_in.size, "the second waiter never took the lock"
    ensure
        (waiters || []).each { |t| t.kill if t.alive? }
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
        File.utime(Time.now - 180, Time.now - 180, old)
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
