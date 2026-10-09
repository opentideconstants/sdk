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
end
