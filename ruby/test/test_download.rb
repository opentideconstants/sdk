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
        c = OTC.new(release: D, cache_dir: cache, offline: true)
        to = File.join(tmpdir, "bundle")
        assert_raises(OTC::OfflineError) { c.download(D, to: to, formats: %i[json jsonl]) }
        assert_empty Dir.children(to)
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
        assert_raises(OTC::NetworkError) { c.download(D, to: to, formats: %i[json jsonl]) }
        assert_empty Dir.children(to)
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
        assert(Dir.children(to).none? { |n| n.start_with?(".tmp-") })
    ensure
        c&.close
    end
end
