# Format-version gates and newer-major signalling (spec §5.2 step 1, §7.4, CR D10, D26).
require_relative "support"

class FormatGateTest < Minitest::Test
    include TestSupport
    OTC = OpenTideConstants

    # R70: newer_format_major is set before check_for_update raises because
    # only newer-major releases exist (CR D10).
    def test_newer_major_is_set_when_check_for_update_raises
        srv = serve(File.join(FIXTURES, "bad", "format-major"))
        c = OTC.new(file: fixture("good", "OTC_20991231.2.jsonl"), base_url: srv.url("/"), cache_dir: tmpdir)
        assert_raises(OTC::UnsupportedFormatError) { c.check_for_update }
        assert_equal 2, c.newer_format_major
    ensure
        c&.close
    end

    # R70: a transient network error keeps the value from before (CR D10).
    def test_newer_major_survives_a_network_error
        over = {}
        srv = serve(File.join(FIXTURES, "good"), over)
        c = OTC.new(base_url: srv.url("/"), cache_dir: tmpdir, on_network_error: :raise)
        major2 = JSON.parse(File.read(fixture("good", "OTC_latest-f1.json"))).merge("format_version" => "2.0")
        over["OTC_latest.json"] = [200, {}, JSON.generate(major2)]
        assert_nil c.check_for_update
        assert_equal 2, c.newer_format_major
        over["OTC_latest.json"] = [503, { "Retry-After" => "0" }, "busy"]
        c.check_for_update
        assert_equal 2, c.newer_format_major
    ensure
        c&.close
    end

    # R72: a pinned eager download records the release's versions in
    # .verified, so offline latest skips a release this SDK cannot read.
    def test_pinned_eager_download_records_versions
        srv = serve(File.join(FIXTURES, "reader"))
        cache = tmpdir
        OTC.new(release: "20991231.2", base_url: srv.url("/"), cache_dir: cache).close
        ver = JSON.parse(File.read(File.join(cache, "v1", "releases", "20991231.2", ".verified")))
        assert_equal ["1.0", "1.0"], ver.values_at("format_version", "min_reader_version")
        assert_raises(OTC::ReaderTooOldError) { OTC.new(release: "20991231.4", base_url: srv.url("/"), cache_dir: cache) }
        ver4 = File.join(cache, "v1", "releases", "20991231.4", ".verified")
        assert_equal "1.99", JSON.parse(File.read(ver4))["min_reader_version"] if File.file?(ver4)
        c = OTC.new(offline: true, cache_dir: cache)
        assert_equal "20991231.2", c.release.datestamp
    ensure
        c&.close
    end
end
