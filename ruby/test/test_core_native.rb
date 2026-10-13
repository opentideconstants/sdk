require "minitest/autorun"
require "json"
require "opentideconstants"

class CoreNativeTest < Minitest::Test
    H4 = ENV.fetch("OTC_CORE_NATIVE_JSONL")
    def self.client
        @client ||= OpenTideConstants.new(file: H4, mode: :stream)
    end
    def test_strict_commercial_retains_actual_licence_reading_recommendations
        file = ENV.fetch("OTC_CORE_NATIVE_STRICT_JSON", H4)
        expected = {
            "OTC-013bda9c" => "OTC-013bda9c/ticon-4/crms6304-crms6304-usa-crms/as-published",
            "OTC-11b36fe8" => "OTC-11b36fe8/ticon-4/crms0194-crms0194-usa-crms/as-published",
            "OTC-1279f3e7" => "OTC-1279f3e7/ticon-4/crms0595-crms0595-usa-crms/as-published"
        }
        client = OpenTideConstants.new(file: file, mode: file.end_with?(".jsonl") ? :stream : :eager,
                                      commercial_only: true, commercial_basis: :strict)
        expected.each do |id, set_id|
            station = client.require_station(id)
            assert_equal set_id, station.raw["recommended_set_id"], id
            original = station.constant_set(set_id)
            assert_equal true, original.licence.commercial_use, id
            assert_equal "licence_reading", original.raw.dig("fallback", "reason"), id
            assert_equal set_id, station.recommended_set&.set_id, id
        end
    ensure
        client&.close
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
    def test_stream_index_retains_discovery_summaries_and_reads_full_native_records
        client = self.class.client
        entries = client.release.instance_variable_get(:@entries)
        retained = entries.select do |entry|
            entry.sets.any? { |set| set.key?("constituents") || set.key?("provenance") || set.key?("time_base") || set.key?("dropped_constituents") }
        end
        assert_equal 0, retained.size, "stream entries retain full fit fields: #{retained.first(3).map(&:station_id)}"

        ids = %w[OTC-a6c00a3f OTC-000180a3 OTC-000cb5d3 OTC-00bdf4b5]
        expected = {}
        File.foreach(H4) do |line|
            raw = JSON.parse(line)
            expected[raw["station_id"]] = raw if ids.include?(raw["station_id"])
            break if expected.size == ids.size
        end
        assert_equal ids.sort, expected.keys.sort
        GC.start(full_mark: true, immediate_sweep: true)
        GC.compact if GC.respond_to?(:compact)
        expected.each do |id, raw|
            station = client.require_station(id)
            assert_equal raw, station.raw, id
            assert_equal raw["constant_sets"], station.constant_sets(include_no_constants: true).map(&:raw), id
            assert_equal raw["source_records"], station.source_records.map(&:raw), id
            assert_equal raw["recommended_set_id"], station.recommended_set.set_id, id
        end
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
