# Repeated ids and references at load (spec §6.1, CR D5), in eager and stream mode.
require_relative "support"

class LoadIdsTest < Minitest::Test
    include TestSupport
    OTC = OpenTideConstants

    # The load fails in every path, with the message of the defect the
    # change made (message: a String the error message must include), not
    # with another check that happened to fire.
    def assert_invalid(what, message, &change)
        [["json", :eager], ["jsonl", :eager], ["jsonl", :stream]].each do |ext, mode|
            path = release_file(ext, &change)
            err = assert_raises(OTC::InvalidReleaseError, "#{what} (#{ext}, #{mode})") { OTC.new(file: path, mode: mode).close }
            assert_equal "invalid_release", err.code
            assert_includes err.message, message, "#{what} (#{ext}, #{mode})"
        end
    end

    def tomb(doc)
        doc["stations"].find { |st| st["status"] == "removed" }
    end

    # R11: a tombstone id that appears twice.
    def test_repeated_tombstone_id
        assert_invalid("tombstone twice", "station_id OTC-T-0005 appears twice") { |doc| doc["stations"] << tomb(doc).dup }
    end

    # D5: a repeated licence_id.
    def test_repeated_licence_id
        assert_invalid("licence twice", "licence_id \"noaa\" appears twice") { |doc| doc["licences"] << doc["licences"][0].dup }
    end

    # R16: the same (system, alias id) on two stations was resolved last-wins.
    def test_alias_on_two_stations
        assert_invalid("alias twice", "alias noaa 9900001 appears twice (OTC-T-0001 and OTC-T-0002)") do |doc|
            station_in(doc, "OTC-T-0002")["aliases"] = { "noaa" => station_in(doc, "OTC-T-0001")["aliases"]["noaa"] }
        end
    end

    # R16: an alias id that is not a String could never be found: a bare
    # Integer, and an Integer in a list.
    def test_alias_id_not_a_string
        msg = "station OTC-T-0001: alias noaa must be a String id or a list of them"
        assert_invalid("alias id 5", msg) { |doc| station_in(doc, "OTC-T-0001")["aliases"]["noaa"] = 5 }
        assert_invalid("alias id [5]", msg) { |doc| station_in(doc, "OTC-T-0001")["aliases"]["noaa"] = [5] }
    end

    # R48: a reference_station_id that is not a String, or names no active
    # station, fails the load (not a later InvalidArgumentError).
    def test_reference_station_id_must_resolve
        sub = ->(doc) { doc["stations"].find { |st| st["subordinate_offsets"].is_a?(Hash) && st["subordinate_offsets"]["reference_station_id"] } }
        {
            "reference 42" => [42, "reference_station_id 42 names no active station"],
            "reference to a tombstone" => [nil, "reference_station_id \"OTC-T-0005\" names no active station"],
            "reference to no station" => ["OTC-T-9999", "reference_station_id \"OTC-T-9999\" names no active station"]
        }.each do |what, (ref, msg)|
            assert_invalid(what, "station OTC-T-0003: #{msg}") do |doc|
                sub.call(doc)["subordinate_offsets"]["reference_station_id"] = ref || tomb(doc)["station_id"]
            end
        end
    end
end
