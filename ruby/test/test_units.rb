require_relative "support"
require "opentideconstants/canonical"

class PredictionUnitsTest < Minitest::Test
    include TestSupport

    def setup
        @client = OpenTideConstants.new(file: fixture("predict", "OTC_20991231.7.json"))
        first = Time.utc(2010, 3, 1)
        @calls = [
            [:heights, ["OTC-P-0001"], {start: first, stop: first + 86_400}, "feet"],
            [:heights_at, ["OTC-P-0001", [first, first + 600]], {}, "feet"],
            [:extremes, ["OTC-P-0001"], {start: first, stop: first + 86_400}, "feet"],
            [:currents, ["OTC-P-0016"], {start: first, stop: first + 86_400}, "knots"],
            [:current_events, ["OTC-P-0016"], {start: first, stop: first + 86_400}, "knots"]
        ]
    end

    def teardown
        @client.close
    end

    def selected_fields(item)
        case item
        when OpenTideConstants::CurrentPoint
            {velocity_major: :velocity_major_ms, velocity_minor: :velocity_minor_ms, speed: :speed_ms}
        when OpenTideConstants::CurrentEvent
            {velocity: :velocity_ms}
        else
            {height: :height_m}
        end
    end

    def test_five_calls_convert_final_values_preserve_si_and_localization
        @calls.each do |operation, positional, options, units|
            si = @client.public_send(operation, *positional, **options)
            selected = @client.release.public_send(operation, *positional, **options, units: units)
            default = units == "feet" ? "meters" : "m/s"
            explicit = @client.public_send(operation, *positional, **options, units: default)
            assert_equal Marshal.dump(si), Marshal.dump(explicit)
            assert_equal default, si.units
            assert_equal units, selected.units
            assert selected.frozen?
            refute_empty selected.items
            si.items.zip(selected.items).each do |before, after|
                assert_equal before.time, after.time
                assert_equal units, after.units
                assert after.frozen?
                selected_fields(after).each do |value, source|
                    assert_equal before.public_send(source), after.public_send(source)
                    assert_equal before.public_send(source), before.public_send(value)
                    divisor = units == "feet" ? 0.3048 : 1852.0 / 3600.0
                    assert_equal after.public_send(source) / divisor, after.public_send(value)
                end
            end
            assert_native_roundtrip(selected)
            assert_native_roundtrip(selected.items.first)
            begin
                require "tzinfo"
                local = selected.to_local("America/New_York")
                assert_equal units, local.units
                assert_equal selected.items.map(&:units), local.items.map(&:units)
                selected.items.zip(local.items).each do |before, after|
                    selected_fields(after).each_key { |value| assert_equal before.public_send(value), after.public_send(value) }
                end
            rescue LoadError
                assert_raises(OpenTideConstants::LocalTimeUnavailableError) { selected.to_local("America/New_York") }
            end
        end
    end

    def native_fields(value)
        value.instance_variables.reject { |field| field == :@_local }.to_h do |field|
            native = value.instance_variable_get(field)
            encoded = native.is_a?(Time) ? native.iso8601 : native
            encoded = native.map { |item| native_fields(item) } if field == :@items
            [field.to_s.delete_prefix("@"), encoded]
        end
    end

    def assert_native_roundtrip(value)
        name = value.class.name.split("::").last
        types = OpenTideConstants.const_get(:CanonicalTypes, false)
        contract = types::FieldContracts.new(model_type: name, fields: [], native_context: value)
        subject = OpenTideConstants.const_get(:Canonical, false).new
        result = subject.send(:materialize_typed_model, model_type: name,
                              raw_fields: JSON.parse(JSON.generate(native_fields(value))), field_contract: contract, origin: nil)
        assert_equal value.units, result.units
        if value.respond_to?(:items)
            assert_equal value.items, result.items
        else
            selected_fields(value).each_key { |field| assert_equal value.public_send(field), result.public_send(field) }
        end
    end

    def test_invalid_quantity_selectors_use_invalid_argument
        @calls.each do |operation, positional, options, units|
            [nil, :feet, "", units == "feet" ? "knots" : "feet"].each do |invalid|
                error = assert_raises(OpenTideConstants::InvalidArgumentError) do
                    @client.public_send(operation, *positional, **options, units: invalid)
                end
                assert_equal "invalid_argument", error.code
            end
        end
    end

    def test_legacy_and_native_canonical_constructors_preserve_units
        subject = OpenTideConstants.const_get(:Canonical, false).new
        [OpenTideConstants::HeightPoint, OpenTideConstants::Extreme, OpenTideConstants::CurrentPoint,
         OpenTideConstants::CurrentEvent, OpenTideConstants::HeightSeries, OpenTideConstants::ExtremeList,
         OpenTideConstants::CurrentSeries, OpenTideConstants::CurrentEventList].each do |klass|
            default = klass.name.include?("Current") ? "m/s" : "meters"
            units = default == "meters" ? "feet" : "knots"
            assert_equal default, klass.new.units
            types = OpenTideConstants.const_get(:CanonicalTypes, false)
            contract = types::FieldContracts.new(model_type: klass.name.split("::").last, fields: [])
            native = subject.send(:materialize_typed_model, model_type: klass.name.split("::").last,
                                  raw_fields: {"units" => units}, field_contract: contract, origin: nil)
            assert_equal units, native.units
            assert native.frozen?
        end
    end
end
