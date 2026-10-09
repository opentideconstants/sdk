# Client lifecycle and the automatic update (spec §4.2 Close, §4.3, §5.6, CR D21).
require_relative "support"

class LifecycleTest < Minitest::Test
    include TestSupport
    OTC = OpenTideConstants

    def older_pointer
        JSON.generate(JSON.parse(File.read(fixture("good", "OTC_index.json")))["releases"].find { |e| e["datestamp"] == "20991231" })
    end

    # R24: an automatic update that fails sets last_error, and the query
    # still answers; a non-SDK error in it never escapes the query.
    def test_auto_update_failure_is_recorded_and_contained
        over = { "OTC_latest-f1.json" => [200, {}, older_pointer] }
        srv = serve(File.join(FIXTURES, "good"), over)
        c = OTC.new(base_url: srv.url("/"), cache_dir: tmpdir, auto_update: true, update_interval: 0.01)
        over["OTC_latest-f1.json"] = [404, {}, ""]
        over["OTC_latest.json"] = [404, {}, ""]
        sleep 0.05
        refute_nil c.station("OTC-T-0001")
        assert_equal "release_not_found", c.last_error&.code
        c.define_singleton_method(:update!) { raise NoMethodError, "boom" }
        sleep 0.05
        refute_nil c.station("OTC-T-0001")
        assert_kind_of OTC::Error, c.last_error
    ensure
        c&.close
    end

    # R5: close also closes a stream Release that an update swapped out.
    def test_close_closes_swapped_out_releases
        over = { "OTC_latest-f1.json" => [200, {}, older_pointer] }
        srv = serve(File.join(FIXTURES, "good"), over)
        c = OTC.new(base_url: srv.url("/"), cache_dir: tmpdir, mode: :stream)
        old = c.release
        over.delete("OTC_latest-f1.json")
        assert c.update!.updated
        refute_nil old.station("OTC-T-0001") # still valid while the client is open
        c.close
        assert old.instance_variable_get(:@io).closed?, "the swapped-out release still holds its file"
    end

    # D21: after close every query and call is io "the release is closed",
    # in eager and stream mode; close again does nothing.
    def test_calls_after_close
        %i[eager stream].each do |mode|
            c = OTC.new(file: fixture("good", "OTC_20991231.2.jsonl"), mode: mode)
            c.close
            c.close
            [-> { c.station("OTC-T-0001") }, -> { c.search(name: "pier") }, -> { c.verify },
             -> { c.cached_releases }, -> { c.attribution }].each do |call|
                err = assert_raises(OTC::FileError, mode.to_s) { call.call }
                assert_includes err.message, "the release is closed"
            end
        end
    end
end
