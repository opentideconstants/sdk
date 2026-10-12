require "minitest/autorun"
require "json"
require "opentideconstants"

class CoreNativeTest < Minitest::Test
    H4 = ENV.fetch("OTC_CORE_NATIVE_JSONL")
    def self.client
        @client ||= OpenTideConstants.new(file: H4, mode: :stream)
    end
    def test_historical_native_cells
        ["TEC2869", "TWC0509"].each do |id|
            st = self.class.client.station_by_alias(:xtide, id)
            st ||= self.class.client.stations(include_flagged: true, include_fallback: true).find { |s| s.raw.dig("subordinate_offsets", "provenance", "id_crosswalk", "legacy_id") == id }
            refute_nil st, id
            assert_instance_of OpenTideConstants::HistoricalOffsetVintage, st.subordinate_offsets.vintage
            assert_equal "unverified", st.subordinate_offsets.vintage.current_accuracy
            assert_instance_of OpenTideConstants::HistoricalOffsetProvenance, st.subordinate_offsets.provenance
            assert_equal st.raw.fetch("source_records"), st.source_records.map(&:raw)
        end
    end
    def test_default_discovery_actual_h4
        assert_equal 6715, self.class.client.stations.size
        assert_equal 9528, self.class.client.stations(include_flagged: true).size
        assert_equal 9549, self.class.client.stations(include_fallback: true).size
        assert_equal 10002, self.class.client.stations(include_flagged: true, include_fallback: true).size
        assert_equal 16038, self.class.client.release.station_count
    end
    def test_raw_source_cells
        count = 0
        fit = 0
        history = 0
        rows = 0
        File.foreach(H4) do |line|
            raw = JSON.parse(line)
            st = self.class.client.station(raw.fetch("station_id"))
            next unless st
            assert_equal raw.fetch("source_records"), st.source_records.map(&:raw), st.station_id
            count += st.source_records.size
            st.source_records.each do |r|
                assert_instance_of OpenTideConstants::SourceRecord, r
                assert r.raw.frozen?
                h = r.original_harmonics || {}
                fit += 1 if h["format"] == "utide_json"
                history += 1 if h["format"] == "utide_historical_json"
                rows += (h["rows"] || []).size if r.source == "ticon"
            end
        end
        assert_equal 27372, count
        assert_equal 241900, rows
    end
end

class CoreIndexNativeTest < Minitest::Test
    def historical
        File.foreach(ENV.fetch("OTC_CORE_NATIVE_JSONL")) do |line|
            raw = JSON.parse(line)
            return raw if raw.dig("subordinate_offsets", "offset_id")
        end
        flunk "actual historical source missing"
    end
    def test_actual_index_rejects_own_historical_mutation
        raw = historical
        entry = OpenTideConstants::Reader.index_entry(raw, 0, 1)
        assert_equal raw["subordinate_offsets"], entry["subordinate_offsets"]
        bad = Marshal.load(Marshal.dump(raw))
        bad["subordinate_offsets"]["vintage"]["current_accuracy"] = "fabricated"
        refute_equal OpenTideConstants::Reader.line_view(entry), OpenTideConstants::Reader.line_view(OpenTideConstants::Reader.index_entry(bad, 0, 1))
        refute OpenTideConstants::Reader.index_entry_ok?(entry.reject { |k, _| k == "subordinate_offsets" })
    end
    def test_malformed_own_fields_and_lifetime
        raw = historical
        bad = Marshal.load(Marshal.dump(raw))
        bad["subordinate_offsets"]["qc_status"] = "ok"
        assert_raises(OpenTideConstants::InvalidReleaseError) { OpenTideConstants::Release.check_station!(bad) }
        bad = Marshal.load(Marshal.dump(raw))
        bad["source_records"][0]["provenance"]["input_sha256"] = 3
        assert_raises(OpenTideConstants::InvalidReleaseError) { OpenTideConstants::Release.check_station!(bad) }
        c = OpenTideConstants.new(file: ENV.fetch("OTC_CORE_NATIVE_JSONL"), mode: :stream, historical_offsets_policy: :exclude)
        st = c.station(raw["station_id"])
        assert_raises(FrozenError) { st.source_records[0].raw["source"] = "mutated" }
        assert_raises(FrozenError) { st.subordinate_offsets.vintage.removal_events[0]["name"] = "mutated" }
        c.close
        assert_equal raw["source_records"], st.source_records.map(&:raw)
        assert_raises(OpenTideConstants::FileError) { c.stations }
    end
end
