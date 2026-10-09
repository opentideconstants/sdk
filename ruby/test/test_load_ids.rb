# Repeated ids and references at load (spec §6.1, CR D5), in eager and stream mode.
require_relative "support"

class LoadIdsTest < Minitest::Test
    include TestSupport
    OTC = OpenTideConstants

    def assert_invalid(what, &change)
        [["json", :eager], ["jsonl", :eager], ["jsonl", :stream]].each do |ext, mode|
            path = release_file(ext, &change)
            err = assert_raises(OTC::InvalidReleaseError, "#{what} (#{ext}, #{mode})") { OTC.new(file: path, mode: mode).close }
            assert_equal "invalid_release", err.code
        end
    end

    def tomb(doc)
        doc["stations"].find { |st| st["status"] == "removed" }
    end

    # R11: a tombstone id that appears twice.
    def test_repeated_tombstone_id
        assert_invalid("tombstone twice") { |doc| doc["stations"] << tomb(doc).dup }
    end

    # D5: a repeated licence_id.
    def test_repeated_licence_id
        assert_invalid("licence twice") { |doc| doc["licences"] << doc["licences"][0].dup }
    end

    # R16: the same (system, alias id) on two stations was resolved last-wins.
    def test_alias_on_two_stations
        assert_invalid("alias twice") do |doc|
            station_in(doc, "OTC-T-0002")["aliases"] = { "noaa" => station_in(doc, "OTC-T-0001")["aliases"]["noaa"] }
        end
    end

    # R16: an alias id that is not a String could never be found.
    def test_alias_id_not_a_string
        assert_invalid("alias id 5") { |doc| station_in(doc, "OTC-T-0001")["aliases"]["noaa"] = [5] }
    end

    # R48: a reference_station_id that is not a String, or names no active
    # station, fails the load (not a later InvalidArgumentError).
    def test_reference_station_id_must_resolve
        sub = ->(doc) { doc["stations"].find { |st| st["subordinate_offsets"].is_a?(Hash) && st["subordinate_offsets"]["reference_station_id"] } }
        assert_invalid("reference 42") { |doc| sub.call(doc)["subordinate_offsets"]["reference_station_id"] = 42 }
        assert_invalid("reference to a tombstone") { |doc| sub.call(doc)["subordinate_offsets"]["reference_station_id"] = tomb(doc)["station_id"] }
    end
end
