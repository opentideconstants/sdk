require "minitest/autorun"
require "json"
require "time"
require "tmpdir"
require "opentideconstants"

class NoaaHistoricalNativeTest < Minitest::Test
    INPUT = ENV.fetch("OTC_NOAA_NATIVE_ROOT")
    ORACLE = JSON.parse(File.read(ENV.fetch("OTC_NOAA_NATIVE_ORACLE")))
    START = Time.utc(2026, 10, 11)
    STOP = START + 86400
    def test_private_table_model_mismatch_rejects_native_prediction
        with_private_table_control do |raw|
            raw.fetch("astro_tables").first["v0_model"] = "private_incompatible_model"
        end
    end
    def test_private_declared_table_pin_mismatch_rejects_native_prediction
        with_private_table_control do |raw|
            raw.fetch("conventions").find { |c| c["convention_id"] == "noaa-harcon-gmt" }["tables_sha256"] = "0" * 64
        end
    end
    def test_null_and_matching_optional_table_pins_allow_native_prediction
        [nil, :matching].each do |pin|
            with_private_table_control(reject: false) do |raw|
                convention = raw.fetch("conventions").find { |c| c["convention_id"] == "noaa-harcon-gmt" }
                convention["tables_sha256"] = pin == :matching ? raw.fetch("astro_tables").first.fetch("tables_sha256") : nil
            end
        end
    end
    def with_private_table_control(reject: true)
        # These are labelled private compatibility controls over the real native release.
        raw = JSON.parse(File.read(File.join(INPUT, "OTC_20261011.json")))
        yield raw
        Dir.mktmpdir("otc-private-table-control") do |dir|
            File.write(File.join(dir, "OTC_20261011.json"), JSON.generate(raw))
            File.write(File.join(dir, "OTC_20261011.meta.json"), JSON.generate(raw.reject { |key, _| key == "stations" }))
            File.write(File.join(dir, "OTC_20261011.jsonl"), raw.fetch("stations").map { |row| JSON.generate(row) + "\n" }.join)
            [:eager, :stream].each do |mode|
                path = File.join(dir, "OTC_20261011.#{mode == :eager ? 'json' : 'jsonl'}")
                client = OpenTideConstants.new(file: path, mode: mode)
                begin
                    [client, client.release].each do |caller|
                        %w[OTC-28c56e20 OTC-541f1a73].each do |id|
                            if reject
                                error = assert_raises(OpenTideConstants::UnsupportedConventionError) { caller.extremes(id, start: START, stop: START, datum: "chart") }
                                assert_includes error.message, "noaa-harcon-gmt"
                                assert_includes error.message, raw.fetch("astro_tables").first.fetch("astro_table_id")
                            else
                                result = caller.extremes(id, start: START, stop: START, datum: "chart")
                                assert result.historical_offsets
                                assert_empty result.items
                            end
                        end
                    end
                ensure
                    client.close
                end
            end
        end
    end
    def test_actual_source_arithmetic_labels_and_controls
        [:eager, :stream].each do |mode|
            path = File.join(INPUT, "OTC_20261011.#{mode == :eager ? 'json' : 'jsonl'}")
            c = OpenTideConstants.new(file: path, mode: mode)
            targets = %w[OTC-28c56e20 OTC-541f1a73]
            targets.each do |id|
                station = c.require_station(id)
                off = station.raw.fetch("subordinate_offsets")
                [c, c.release].each do |caller|
                    automatic = caller.extremes(id, start: START, stop: STOP, datum: "chart")
                    explicit = caller.extremes(id, start: START, stop: STOP, offset_id: off["offset_id"])
                    assert_equal automatic.items.map { |p| [p.time, p.type, p.height_m] }, explicit.items.map { |p| [p.time, p.type, p.height_m] }
                    assert automatic.historical_offsets
                    assert_nil automatic.set_id
                    assert_equal "unverified", automatic.current_accuracy
                    assert_equal "unestablished", automatic.current_validity
                    assert_equal "disagrees", automatic.reference_2020_equivalence
                    assert_equal "noaa", automatic.offset_source
                    assert_equal "annual-tide-tables-2020", automatic.offset_source_version
                    assert_equal off["offset_id"], automatic.offset_id
                    assert_equal c.require_station(off["reference_station_id"]).constant_sets.find { |s| s.source == "noaa" }.set_id, automatic.reference_set_id
                    assert automatic.source_note.include?("retired NOAA profile")
                    assert_raises(OpenTideConstants::ExtremesOnlyError) { caller.heights(id, start: START, stop: STOP) }
                    assert_raises(OpenTideConstants::ExtremesOnlyError) { caller.heights_at(id, [START], offset_id: off["offset_id"]) }
                end
                predicted = c.extremes(id, start: START, stop: STOP, datum: "chart")
                reference = c.extremes(off["reference_station_id"], start: START - 86400, stop: STOP + 86400, datum: "chart")
                expected = reference.items.filter_map do |p|
                    shifted = p.time + off["time_offset_#{p.type}_min"] * 60
                    next unless START <= shifted && shifted < STOP
                    adjustment = off["height_offset_#{p.type}"]
                    height = off["height_adjusted_type"] == "R" ? p.height_m * adjustment : p.height_m + adjustment
                    [shifted, p.type, height]
                end.sort_by(&:first)
                assert_equal expected.size, predicted.items.size
                predicted.items.zip(expected).each do |p, e|
                    assert_equal e[0], p.time
                    assert_equal e[1], p.type
                    assert_in_delta e[2], p.height_m, 1e-7
                end
                ORACLE["numeric_cells"].select { |cell| cell["mode"] == mode.to_s && cell["station_id"] == id }.each do |cell|
                    actual = predicted.items.find { |p| p.type.to_s == cell["kind"] }
                    assert_equal Time.iso8601(cell["time"]), actual.time
                    assert_in_delta cell["height_m"], actual.height_m, 1e-7
                end
            end
            ORACLE["unchanged_controls"].select { |row| row["mode"] == mode.to_s }.each do |row|
                actual = c.extremes(row["station_id"], start: START, stop: STOP, datum: "chart")
                assert_equal row["events"].size, actual.items.size
                actual.items.zip(row["events"]).each do |p, e|
                    assert_equal Time.iso8601(e["time"]), p.time
                    assert_equal e["type"], p.type.to_s
                    assert_in_delta e["height_m"], p.height_m, 1e-7
                end
            end
            c.close
            strict = OpenTideConstants.new(file: path, mode: mode, historical_offsets_policy: "exclude")
            targets.each do |id|
                refute_nil strict.station(id)
                [false, true].product([false, true]).each do |flagged, fallback|
                    refute strict.stations(include_flagged: flagged, include_fallback: fallback).any? { |s| s.station_id == id }
                end
                [strict, strict.release].each do |caller|
                    assert_raises(OpenTideConstants::HistoricalOffsetsExcludedError) { caller.extremes(id, start: START, stop: STOP) }
                    offset_id = strict.station(id).subordinate_offsets.offset_id
                    assert_raises(OpenTideConstants::HistoricalOffsetsExcludedError) { caller.extremes(id, start: START, stop: STOP, offset_id: offset_id) }
                end
            end
            strict.close
        end
    end
end
