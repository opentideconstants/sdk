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

    # CR2 DR5: a failure in an automatic update is logged with its backtrace
    # and kept in last_error as an SDK error with the original as its cause:
    # network for a transport failure, else io.
    def auto_update_failing_with(exc)
        log = Log.new
        c = OTC.new(file: fixture("good", "OTC_20991231.2.jsonl"), logger: log)
        c.instance_variable_set(:@file, nil) # behave as a latest client for the automatic update
        c.instance_variable_set(:@auto_update, true)
        c.instance_variable_set(:@update_interval, 0.001)
        c.define_singleton_method(:update!) { raise exc }
        sleep 0.01
        refute_nil c.station("OTC-T-0001")
        [c, log]
    end

    def test_auto_update_non_sdk_failure_is_io_with_cause_and_backtrace
        exc = NoMethodError.new("boom")
        c, log = auto_update_failing_with(exc)
        assert_kind_of OTC::FileError, c.last_error
        assert_same exc, c.last_error.cause
        line = log.lines.find { |lvl, _| lvl == :warn }&.last.to_s
        assert_includes line, "NoMethodError"
        assert_includes line, __FILE__, "the backtrace is not logged"
    ensure
        c&.close
    end

    def test_auto_update_transport_failure_is_network_with_cause
        exc = Errno::ECONNRESET.new("reset by peer")
        c, = auto_update_failing_with(exc)
        assert_kind_of OTC::NetworkError, c.last_error
        assert_same exc, c.last_error.cause
    ensure
        c&.close
    end

    # CR2 DR32: after close the metadata stays readable, and every query and
    # iterator step (also of an iterator made before close) is io.
    def test_after_close_metadata_readable_and_queries_io
        %i[eager stream].each do |mode|
            c = OTC.new(file: fixture("good", "OTC_20991231.2.jsonl"), mode: mode)
            sub = c.station("OTC-T-0003")
            ref = c.reference_station(sub)
            rel = c.release
            it = rel.iter_stations
            it.next
            c.close
            assert_same rel, c.release, "the release attribute stays readable after close"
            assert_equal ["20991231.2", "1.0"], [rel.datestamp, rel.format_version]
            refute_nil rel.created
            assert_includes rel.citation, "20991231.2"
            assert_kind_of Array, rel.files
            calls = {
                station: -> { rel.station("OTC-T-0001") }, tombstone: -> { rel.tombstone("OTC-T-0005") },
                reference_station: -> { rel.reference_station(sub) }, subordinates_of: -> { rel.subordinates_of(ref) },
                stats: -> { rel.stats }, station_count: -> { rel.station_count }, conventions: -> { rel.conventions },
                licences: -> { rel.licences }, constituent_names: -> { rel.constituent_names },
                attribution: -> { rel.attribution }, iter_before_close: -> { it.next },
                iter_after_close: -> { rel.iter_stations.next }
            }
            calls.each do |name, call|
                err = assert_raises(OTC::FileError, "#{mode} #{name}") { call.call }
                assert_includes err.message, "the release is closed"
            end
        end
    end
end
