require_relative "support"

class PredictNativeTest < Minitest::Test
    include TestSupport
    def native_client
        OpenTideConstants.new(file: fixture("predict", "OTC_20991231.7.json"))
    end
    # Saved NOAA ACT8851/ACT8856 offsets on the existing harmonic fixture.
    # This bounded CI model checks dispatch; full-release numerical parity is
    # checked separately against the untouched producer output.
    MIXED_CURRENT_ROWS = [
        ["OTC-7c4e4c70", "ACT8851",
         [[1, 15, 2, 5, 17, 1.0, 1.1, 272.0, 91.0], [3, -1, -3, -13, -18, 0.8, 0.9, 274.0, 94.0]]],
        ["OTC-14e250fa", "ACT8856",
         [[1, 7, -16, -1, 9, 1.0, 1.1, 295.0, 125.0], [3, -11, 17, -8, -32, 0.8, 0.6, 306.0, 115.0]]]
    ].freeze
    def mixed_current_client(mode:, offsets: true)
        datum_fallback_client(mode: mode) do |document|
            template = station_in(document, "OTC-P-0016")
            document["stations"] = MIXED_CURRENT_ROWS.map do |id, source_id, rows|
                station = Marshal.load(Marshal.dump(template))
                station.merge!("station_id" => id, "name" => source_id, "recommended_set_id" => "#{id}/noaa")
                constants = station["constant_sets"].first
                constants["set_id"] = "#{id}/noaa"
                bin = constants["current_bins"].find { |item| item["bin"] == 2 }
                constants["current_bins"] = [bin]
                if offsets
                    station["current_offsets"] = rows.map do |number, max_flood, slack_ebb, max_ebb, slack_flood, flood_ratio, ebb_ratio, flood_dir, ebb_dir|
                        { "bin" => number, "reference_station_id" => id, "reference_bin" => 2, "licence_id" => "noaa",
                          "time_adj_max_flood_min" => max_flood, "time_adj_slack_before_ebb_min" => slack_ebb,
                          "time_adj_max_ebb_min" => max_ebb, "time_adj_slack_before_flood_min" => slack_flood,
                          "flood_amp_ratio" => flood_ratio, "ebb_amp_ratio" => ebb_ratio,
                          "mean_flood_dir_deg" => flood_dir, "mean_ebb_dir_deg" => ebb_dir }
                    end
                end
                station
            end
        end
    end
    MIXED_CURRENT_ROWS.each do |id, source_id, rows|
        rows.each do |bin, *|
            define_method("test_mixed_current_#{source_id.downcase}_bin_#{bin}") do
                c = nil
                %i[eager stream].each do |mode|
                    c = mixed_current_client(mode: mode)
                    start = Time.new(2027, 1, 1, 0, 0, 0, "-08:00")
                    stop = start + 172_800
                    result = c.current_events(id, start: start, stop: stop, bin_number: bin)
                    assert_equal :offsets, result.method
                    assert_equal bin, result.bin_number
                    assert_equal id, result.reference_station_id
                    assert_equal 2, result.reference_bin
                    assert_equal "#{id}/noaa", result.set_id
                    assert_equal %i[max_ebb max_flood slack_before_ebb slack_before_flood], result.items.map(&:type).uniq.sort
                    entry = c.require_station(id).raw["current_offsets"].find { |item| item["bin"] == bin }
                    harmonic = c.current_events(id, start: start - 7200, stop: stop + 7200, bin_number: 2)
                    expected = harmonic.items.filter_map do |event|
                        time = event.time + entry.fetch("time_adj_#{event.type}_min") * 60
                        next unless time >= start && time < stop
                        ratio = event.type == :max_flood ? entry["flood_amp_ratio"] : entry["ebb_amp_ratio"]
                        direction = case event.type
                                    when :max_flood then entry["mean_flood_dir_deg"]
                                    when :max_ebb then entry["mean_ebb_dir_deg"]
                                    end
                        [time, event.type, event.velocity_ms * ratio, direction]
                    end.sort_by(&:first)
                    assert_equal expected.length, result.items.length
                    expected.zip(result.items).each do |(time, kind, speed, direction), actual|
                        assert_equal time, actual.time
                        assert_equal kind, actual.type
                        assert_in_delta speed, actual.velocity_ms, 1e-9
                        direction.nil? ? assert_nil(actual.direction_deg) : assert_equal(direction, actual.direction_deg)
                    end
                    assert_raises(OpenTideConstants::ExtremesOnlyError) { c.currents(id, start: start, stop: stop, bin_number: bin) }
                    assert_raises(OpenTideConstants::BinNotFoundError) { c.current_events(id, start: start, stop: stop, bin_number: bin, set_id: "#{id}/noaa") }
                    c.close
                end
            ensure
                c&.close
            end
        end
    end
    def test_mixed_current_preserves_harmonic_and_default_bin
        c = control = nil
        %i[eager stream].each do |mode|
            c = mixed_current_client(mode: mode)
            control = mixed_current_client(mode: mode, offsets: false)
            window = { start: Time.new(2027, 1, 1, 0, 0, 0, "-08:00"), stop: Time.new(2027, 1, 3, 0, 0, 0, "-08:00") }
            MIXED_CURRENT_ROWS.each do |id, *|
                %i[current_events currents].each do |operation|
                    expected = control.public_send(operation, id, **window, bin_number: 2)
                    [nil, 2].each do |bin|
                        actual = c.public_send(operation, id, **window, bin_number: bin)
                        assert_equal :harmonic, actual.method
                        assert_equal Marshal.dump(expected), Marshal.dump(actual)
                    end
                end
            end
            c.close
            control.close
        end
    ensure
        c&.close
        control&.close
    end
    def datum_fallback
        {
            "reason" => "datum_gate_failed",
            "basis" => "Computed candidate pending acceptance",
            "otc_finding" => "Datum gate is not established",
            "extension" => { "diagnostics" => ["retained", { "accepted" => false }] }
        }
    end
    def datum_fallback_client(mode: :eager)
        document = JSON.parse(File.read(fixture("predict", "OTC_20991231.7.json")))
        yield document
        directory = tmpdir
        if mode == :stream
            stations = document.delete("stations")
            path = File.join(directory, "OTC_20991231.7.jsonl")
            File.write(File.join(directory, "OTC_20991231.7.meta.json"), JSON.generate(document))
            File.write(path, stations.map { |station| JSON.generate(station) + "\n" }.join)
        else
            path = File.join(directory, "OTC_20991231.7.json")
            File.write(path, JSON.generate(document))
        end
        OpenTideConstants.new(file: path, mode: mode)
    end
    def harmonic_mean_datum
        basis = { "kind" => "computed", "method" => "harmonic_extremes",
                  "epoch" => { "start" => "2020-01-01", "end" => "2038-12-31" }, "fallback" => datum_fallback }
        { "zero" => "harmonic_mean", "named" => { "lat" => -0.4, "hat" => 0.6 },
          "basis" => { "lat" => basis, "hat" => basis } }
    end
    def test_harmonic_mean_named_and_zero_preserve_heights_events_and_unknown_uncertainty
        c = nil
        %i[eager stream].each do |mode|
            c = datum_fallback_client(mode: mode) do |document|
                station_in(document, "OTC-P-0001")["constant_sets"].first["datum"] = harmonic_mean_datum
            end
            times = [Time.utc(2010, 3, 1), Time.utc(2010, 3, 1, 6), Time.utc(2010, 3, 1, 12)]
            options = { set_id: "OTC-P-0001/noaa" }
            mean = c.heights_at("OTC-P-0001", times, datum: "mean_level", **options)
            zero = c.heights_at("OTC-P-0001", times, datum: "zero", **options)
            assert_equal mean.items.map(&:height_m), zero.items.map(&:height_m)
            assert_equal "harmonic_mean", zero.datum_name
            window = { start: times.first, stop: times.first + 86_400, **options }
            events = c.extremes("OTC-P-0001", datum: "mean_level", **window)
            refute_empty events.items
            harmonic_mean_datum.fetch("named").each do |key, level|
                named = c.heights_at("OTC-P-0001", times, datum: key, **options)
                assert_equal key, named.datum_name
                assert_equal "computed", named.datum_kind
                assert_nil named.datum_uncertainty_m
                mean.items.zip(named.items).each { |left, right| assert_in_delta(-level, right.height_m - left.height_m, 1e-12) }
                shifted = c.extremes("OTC-P-0001", datum: key, **window)
                assert_equal events.items.map(&:time), shifted.items.map(&:time)
                events.items.zip(shifted.items).each { |left, right| assert_in_delta(-level, right.height_m - left.height_m, 1e-12) }
                metadata = c.datums("OTC-P-0001", **options).levels.find { |item| item.key == key }
                assert_nil metadata.uncertainty_m
                assert_nil metadata.uncertainty_basis
                assert_equal datum_fallback, metadata.fallback
            end
            info = c.datums("OTC-P-0001", **options)
            assert_equal "harmonic_mean", info.zero
            assert_nil info.msl_offset_m
            assert_nil info.zero_name
            %w[chart msl absent].each { |key| assert_raises(OpenTideConstants::DatumUnavailableError) { c.heights_at("OTC-P-0001", times, datum: key, **options) } }
            c.close
        end
    ensure
        c&.close
    end
    def test_missing_absolute_frame_and_published_reference_still_require_msl_offset
        [nil, "chart_datum"].each do |zero|
            c = datum_fallback_client do |document|
                datum = station_in(document, "OTC-P-0001")["constant_sets"].first["datum"]
                datum.delete("msl_offset_m")
                zero ? datum["zero"] = zero : datum.delete("zero")
            end
            %w[lat zero chart msl].each do |key|
                error = assert_raises(OpenTideConstants::DatumUnavailableError) { c.heights_at("OTC-P-0001", [Time.utc(2010, 3, 1)], datum: key) }
                assert_equal "datum is missing msl_offset_m", error.message
            end
            c.close
        end
        c = datum_fallback_client do |document|
            station_in(document, "OTC-P-0060")["constant_sets"].first["datum"] = harmonic_mean_datum.merge("chart_datum" => "lat")
        end
        error = assert_raises(OpenTideConstants::DatumUnavailableError) { c.extremes("OTC-P-0061", start: Time.utc(2010, 3, 1), stop: Time.utc(2010, 3, 2)) }
        assert_equal "datum is missing msl_offset_m", error.message
    ensure
        c&.close
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
