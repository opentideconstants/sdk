# download() into the caller's folder (spec §4.3.2): all of a release or nothing.
require_relative "support"

class DownloadTest < Minitest::Test
    include TestSupport
    OTC = OpenTideConstants
    D = "20991231.2".freeze

    # R10: offline with a cache that holds only some of the formats: nothing is written.
    def test_offline_partial_cache_writes_nothing
        srv = serve
        cache = tmpdir
        OTC.new(release: D, base_url: srv.url("/"), cache_dir: cache, mode: :eager).close
        # The premise: the cache holds the .json (and .sha256), not the .jsonl.
        rel = File.join(cache, "v1", "releases", D)
        assert File.file?(File.join(rel, "OTC_#{D}.json"))
        assert File.file?(File.join(rel, "OTC_#{D}.sha256"))
        refute File.exist?(File.join(rel, "OTC_#{D}.jsonl"))
        c = OTC.new(release: D, cache_dir: cache, offline: true)
        to = File.join(tmpdir, "bundle")
        err = assert_raises(OTC::OfflineError) { c.download(D, to: to, formats: %i[json jsonl]) }
        # It failed on the file the cache does not have, not on the release as a whole.
        assert_includes err.message, "OTC_#{D}.jsonl is not cached"
        assert(!File.exist?(to) || Dir.empty?(to), "files were written: #{File.exist?(to) && Dir.children(to)}")
    ensure
        c&.close
    end

    # R10: a network error on a later file: nothing is written.
    def test_network_error_on_a_later_file_writes_nothing
        over = {}
        srv = serve(File.join(FIXTURES, "good"), over)
        c = OTC.new(release: D, base_url: srv.url("/"), cache_dir: tmpdir, mode: :eager)
        over["OTC_#{D}.meta.json"] = [500, { "Retry-After" => "0" }, "busy"]
        to = File.join(tmpdir, "bundle")
        before = srv.requests.size
        assert_raises(OTC::NetworkError) { c.download(D, to: to, formats: %i[json jsonl]) }
        # The .jsonl was fetched (and staged) before the .meta.json failed.
        asked = srv.requests[before..]
        assert_equal "/OTC_#{D}.jsonl", asked.first
        assert_operator asked.index("/OTC_#{D}.jsonl"), :<, asked.index("/OTC_#{D}.meta.json")
        assert(!File.exist?(to) || Dir.empty?(to), "files were written: #{File.exist?(to) && Dir.children(to)}")
    ensure
        c&.close
    end

    # R9: the paths come in a fixed order: the data files as the formats list
    # them, then OTC_{D}.sha256.
    def test_paths_written_in_order
        srv = serve
        c = OTC.new(release: D, base_url: srv.url("/"), cache_dir: tmpdir, mode: :stream)
        to = tmpdir
        paths = c.download(D, to: to, formats: %i[json jsonl])
        assert_equal %W[OTC_#{D}.json OTC_#{D}.jsonl OTC_#{D}.meta.json OTC_#{D}.sha256], paths.map { |p| File.basename(p) }
        # The folder holds exactly these files (no temporary or other files).
        assert_equal paths.map { |p| File.basename(p) }.sort, Dir.children(to).sort
    ensure
        c&.close
    end

    # ---- CR D22: download of latest honours on_network_error

    def captive_portal(over)
        # a 200 pointer that is not JSON is a network error at once (spec §5.2 step 5), with no retry
        %w[OTC_latest-f1.json OTC_latest.json].each { |n| over[n] = [200, { "Content-Type" => "text/html" }, "<html>portal</html>"] }
    end

    def names
        %W[OTC_#{D}.jsonl OTC_#{D}.meta.json OTC_#{D}.sha256]
    end

    def test_latest_with_a_network_error_writes_the_newest_cached_release
        over = {}
        srv = serve(File.join(FIXTURES, "good"), over)
        c = OTC.new(base_url: srv.url("/"), cache_dir: tmpdir)
        captive_portal(over)
        to = File.join(tmpdir, "bundle")
        paths = c.download(to: to)
        assert_equal names, paths.map { |p| File.basename(p) }.sort
        names.each { |n| assert_equal File.binread(fixture("good", n)), File.binread(File.join(to, n)) }
    ensure
        c&.close
    end

    def test_latest_with_a_network_error_and_raise_raises
        over = {}
        srv = serve(File.join(FIXTURES, "good"), over)
        c = OTC.new(base_url: srv.url("/"), cache_dir: tmpdir, on_network_error: :raise)
        captive_portal(over)
        to = File.join(tmpdir, "bundle")
        assert_raises(OTC::NetworkError) { c.download(to: to) }
        refute(File.exist?(to) && !Dir.empty?(to))
    ensure
        c&.close
    end

    def test_latest_with_a_network_error_and_nothing_cached_raises
        over = {}
        srv = serve(File.join(FIXTURES, "good"), over)
        c = OTC.new(file: fixture("good", "OTC_#{D}.jsonl"), base_url: srv.url("/"), cache_dir: tmpdir)
        captive_portal(over)
        assert_raises(OTC::NetworkError) { c.download(to: File.join(tmpdir, "bundle")) }
    ensure
        c&.close
    end

    # ---- CR2 DR17: the renames into to are all or nothing

    # Downloads D into a new folder, then changes the .jsonl and the
    # .meta.json there. Returns [client, folder, {name => changed bytes}].
    def changed_bundle
        srv = serve
        c = OTC.new(release: D, base_url: srv.url("/"), cache_dir: tmpdir)
        to = tmpdir
        c.download(D, to: to)
        before = names.first(2).to_h do |n|
            File.binwrite(File.join(to, n), "changed #{n}")
            [n, File.binread(File.join(to, n))]
        end
        [c, to, before]
    end

    # Runs the block with File.rename failing when failing.call(source
    # basename, destination basename) is true.
    def failing_renames(failing)
        sc = File.singleton_class
        sc.send(:alias_method, :otc_test_real_rename, :rename)
        sc.send(:define_method, :rename) do |a, b|
            raise Errno::EACCES, "injected #{b}" if failing.call(File.basename(a.to_s), File.basename(b.to_s))
            otc_test_real_rename(a, b)
        end
        yield
    ensure
        sc.send(:alias_method, :rename, :otc_test_real_rename)
        sc.send(:remove_method, :otc_test_real_rename)
    end

    def new_file_into(src, dest, name)
        dest == name && src.start_with?(".tmp-") && !src.start_with?(".tmp-bak-")
    end

    def test_a_rename_that_fails_restores_every_original
        c, to, before = changed_bundle
        meta = "OTC_#{D}.meta.json"
        e = failing_renames(->(s, d) { new_file_into(s, d, meta) }) do
            assert_raises(OTC::FileError) { c.download(D, to: to, overwrite: true) }
        end
        assert_equal File.join(to, meta), e.path
        before.each { |n, bytes| assert_equal bytes, File.binread(File.join(to, n)), "#{n} was not restored" }
        assert_equal names, Dir.children(to).sort
    ensure
        c&.close
    end

    def test_a_restore_that_fails_too_lists_the_paths_that_changed
        c, to, before = changed_bundle
        jsonl, meta = "OTC_#{D}.jsonl", "OTC_#{D}.meta.json"
        failing = ->(s, d) { new_file_into(s, d, meta) || (d == jsonl && s.start_with?(".tmp-bak-")) }
        e = failing_renames(failing) do
            assert_raises(OTC::FileError) { c.download(D, to: to, overwrite: true) }
        end
        assert_includes e.message, File.join(to, jsonl)
        assert_equal before[meta], File.binread(File.join(to, meta))
    ensure
        c&.close
    end
end
