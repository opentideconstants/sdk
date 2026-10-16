require_relative "support"

class PredictNativeTest < Minitest::Test
    include TestSupport
    def native_client
        OpenTideConstants.new(file: fixture("predict", "OTC_20991231.7.json"))
    end
    def datum_fallback
        {
            "reason" => "datum_gate_failed",
            "basis" => "Computed candidate pending acceptance",
            "otc_finding" => "Datum gate is not established",
            "extension" => { "diagnostics" => ["retained", { "accepted" => false }] }
        }
    end
    def datum_fallback_client
        document = JSON.parse(File.read(fixture("predict", "OTC_20991231.7.json")))
        yield document
        path = File.join(tmpdir, "OTC_20991231.7.json")
        File.write(path, JSON.generate(document))
        OpenTideConstants.new(file: path)
    end
    def test_datums_preserves_complete_per_level_fallback_on_selected_default_and_all_sets
        c = datum_fallback_client do |document|
            station_in(document, "OTC-P-0001")["constant_sets"].first["datum"]["basis"]["otc_lat"]["fallback"] = datum_fallback
        end
        infos = [c.datums("OTC-P-0001"), c.datums("OTC-P-0001", set_id: "OTC-P-0001/noaa"),
                 c.datums("OTC-P-0001", all_sets: true).find { |info| info.set_id == "OTC-P-0001/noaa" }]
        infos.each do |info|
            computed = info.levels.find { |level| level.key == "otc_lat" }
            assert_respond_to computed, :fallback
            assert_equal datum_fallback, computed.fallback
            assert_equal(-0.41, computed.value_m)
            assert_equal "computed", computed.kind
            assert_nil info.levels.find { |level| level.key == "lat" }.fallback
            assert_raises(FrozenError) { computed.fallback["extension"]["diagnostics"][1]["accepted"] = true }
        end
        assert_empty c.datums("OTC-P-0001", set_id: "OTC-P-0001/gesla-fit").levels
    ensure
        c&.close
    end
    def test_datums_preserves_subordinate_fallback
        c = datum_fallback_client do |document|
            datum = station_in(document, "OTC-P-0061")["subordinate_offsets"]["datum"]
            datum["named"]["otc_lat"] = -0.5
            datum["basis"]["otc_lat"] = { "kind" => "computed", "method" => "harmonic_extremes", "fallback" => datum_fallback }
        end
        info = c.datums("OTC-P-0061")
        assert_nil info.set_id
        assert_respond_to info.levels.find { |level| level.key == "otc_lat" }, :fallback
        assert_equal datum_fallback, info.levels.find { |level| level.key == "otc_lat" }.fallback
        assert_nil info.levels.find { |level| level.key == "mllw" }.fallback
    ensure
        c&.close
    end
    def test_datum_level_fallback_is_optional_and_an_independent_deeply_frozen_copy
        assert_respond_to OpenTideConstants::DatumLevel.new(key: "lat"), :fallback
        assert_nil OpenTideConstants::DatumLevel.new(key: "lat").fallback
        input = datum_fallback
        expected = datum_fallback
        level = OpenTideConstants::DatumLevel.new(key: "otc_lat", fallback: input)
        refute input.frozen?
        input["extension"]["diagnostics"][0].replace("changed")
        input["basis"].replace("changed")
        assert_equal expected, level.fallback
        assert_raises(FrozenError) { level.fallback["basis"].replace("changed") }
        assert_raises(FrozenError) { level.fallback["extension"]["diagnostics"] << "changed" }
    end
    def test_native_time_rounding_immutability_and_metadata
        c = native_client
        t = Time.utc(2010, 3, 1)
        values = c.heights_at("OTC-P-0001", [t + Rational(9, 10), t, t + 600])
        assert_equal [t, t, t + 600], values.items.map(&:time)
        assert_equal :harmonic, values.method
        assert_equal "otc-predict-1", values.algorithm
        assert_raises(FrozenError) { values.items << values.items[0] }
        assert_raises(FrozenError) { values.items[0].instance_variable_set(:@height_m, 42) }
        assert_raises(OpenTideConstants::InvalidArgumentError) { c.heights_at("OTC-P-0001", [3]) }
        assert_raises(OpenTideConstants::InvalidArgumentError) { c.heights("OTC-P-0001", start: t, stop: t + 60, step_s: false) }
        assert_raises(OpenTideConstants::InvalidArgumentError) { c.heights("OTC-P-0001", start: t, stop: t + 60, step_s: nil) }
        assert_raises(OpenTideConstants::QuantityMismatchError) { c.currents("OTC-P-0001", start: t, stop: t + 60) }
        c.close
        assert_equal t, values.items[0].time
        assert_raises(OpenTideConstants::FileError) { c.extremes("OTC-P-0001", start: t, stop: t + 60) }
    ensure
        c&.close
    end
    def test_closed_release_precedes_invalid_prediction_window
        c = native_client
        held = c.release
        c.close
        assert_raises(OpenTideConstants::FileError) { held.heights("OTC-P-0001", start: nil, stop: nil) }
        assert_raises(OpenTideConstants::FileError) { held.heights_at("OTC-P-0001", "bad") }
        assert_raises(OpenTideConstants::FileError) { held.extremes("OTC-P-0001", start: nil, stop: nil) }
        assert_raises(OpenTideConstants::FileError) { held.currents("OTC-P-0001", start: nil, stop: nil) }
        assert_raises(OpenTideConstants::FileError) { held.current_events("OTC-P-0001", start: nil, stop: nil) }
    end
    def test_prediction_refuses_foreign_origin_with_identical_raw
        c = native_client
        other = native_client
        start = Time.utc(2010, 3, 1)
        window = { start: start, stop: start + 3600 }
        {
            heights: ["OTC-P-0001", window],
            extremes: ["OTC-P-0001", window],
            currents: ["OTC-P-0016", window],
            current_events: ["OTC-P-0016", window],
            datums: ["OTC-P-0001", {}]
        }.each do |route, (id, options)|
            owned = c.require_station(id)
            foreign = other.require_station(id)
            assert_equal owned.raw, foreign.raw, route
            error = assert_raises(OpenTideConstants::InvalidArgumentError, route.to_s) do
                c.public_send(route, foreign, **options)
            end
            assert_equal "invalid_argument", error.code, route
            assert_equal Marshal.dump(c.public_send(route, id, **options)),
                         Marshal.dump(c.public_send(route, owned, **options)), route
        end
    ensure
        c&.close
        other&.close
    end
    def test_astro_boundaries_and_missing_terms
        c = native_client
        table = c.release.astro_table
        assert_instance_of OpenTideConstants::AstroTable, table
        assert_equal [2000, 2030], table.valid_range
        assert_raises(OpenTideConstants::TimeOutOfRangeError) { table.node_factor_for_year("M2", 1999) }
        assert_raises(OpenTideConstants::InvalidArgumentError) { table.node_factor_for_year("M2", true) }
        assert_raises(OpenTideConstants::UnsupportedConstituentError) { table.node_factor_for_year("UNKNOWN", 2010) }
        assert table.frozen?
    ensure
        c&.close
    end
    def test_local_zone_bad_name_and_real_optional_conversion
        c = native_client
        result = c.heights_at("OTC-P-0001", [Time.utc(2010, 3, 1)])
        assert_raises(OpenTideConstants::UnknownTimeZoneError) { result.to_local("../UTC") }
        begin
            require "tzinfo"
            local = result.to_local("America/New_York")
            assert_equal result.items[0].time, local.items[0].time
            assert_equal(-18000, local.items[0].utc_offset_s)
            assert_kind_of Time, local.items[0].local_time_object
            assert_nil result.items[0].local_time
        rescue LoadError
            assert_raises(OpenTideConstants::LocalTimeUnavailableError) { result.to_local("UTC") }
        end
    ensure
        c&.close
    end
end
