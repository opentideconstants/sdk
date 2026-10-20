require_relative "support"
require "opentideconstants/canonical"

class BboxTest < Minitest::Test
    BOX = { south: 37.665, west: -122.4659, north: 37.8063, east: -122.3 }.freeze
    FILE = File.join(TestSupport::FIXTURES, "good/OTC_20991231.2.jsonl")

    def each_receiver
        %i[eager stream].each do |mode|
            OpenTideConstants.open(file: FILE, mode: mode) do |client|
                [client, client.release].each { |receiver| yield receiver }
            end
        end
    end

    def test_inclusive_ordered_bounds_filters_and_limit
        each_receiver do |receiver|
            result = receiver.bbox(**BOX)
            assert_equal %w[OTC-T-0001 OTC-T-0003 OTC-T-0004], result.map(&:station_id)
            assert_predicate result, :frozen?
            assert_equal %w[OTC-T-0001 OTC-T-0003 OTC-T-0004], receiver.bbox(**BOX, limit: nil).map(&:station_id)
            assert_equal %w[OTC-T-0003], receiver.bbox(**BOX, type: :subordinate, limit: 1).map(&:station_id)
            assert_equal %w[OTC-T-0001 OTC-T-0002 OTC-T-0003 OTC-T-0004], receiver.bbox(**BOX, include_flagged: true).map(&:station_id)
            station = result.first
            assert_equal [station.station_id], receiver.bbox(south: station.lat, west: station.lon, north: station.lat, east: station.lon).map(&:station_id)
        end
    end

    def test_date_line_and_empty_box
        each_receiver do |receiver|
            assert_equal %w[OTC-T-0007 OTC-T-0008], receiver.bbox(south: -1, west: 179.8, north: 1, east: -179.8).map(&:station_id)
            assert_empty receiver.bbox(south: -46, west: -31, north: -44, east: -29)
        end
    end

    def test_invalid_bounds_filters_and_limit
        invalid = [{ south: -91 }, { north: 91 }, { west: -181 }, { east: 181 },
                   { south: 38 }, { north: Float::NAN }, { west: Float::INFINITY },
                   { east: nil }, { south: "37" }, { limit: 0 }, { limit: 1.5 },
                   { include_flagged: nil }, { country: 3 }, { unknown: true }]
        each_receiver do |receiver|
            invalid.each do |options|
                assert_raises(OpenTideConstants::InvalidArgumentError) { receiver.bbox(**BOX.merge(options)) }
            end
            assert_raises(OpenTideConstants::InvalidArgumentError) { receiver.bbox }
        end
    end

    def test_stream_materializes_only_selected_stations
        OpenTideConstants.open(file: FILE, mode: :stream) do |client|
            release = client.release
            assert_empty release.instance_variable_get(:@station_cache)
            assert_equal %w[OTC-T-0003], release.bbox(**BOX, type: :subordinate, limit: 1).map(&:station_id)
            assert_equal %w[OTC-T-0003], release.instance_variable_get(:@station_cache).keys
        end
    end

    def test_canonical_bbox_argument_validation
        OpenTideConstants.open(file: FILE) do |client|
            canonical = OpenTideConstants.const_get(:Canonical, false).new
            [BOX, BOX.merge(south: 38)].each do |bounds|
                arguments = OpenTideConstants.const_get(:CanonicalTypes, false)::ArgsReleaseBbox.new(member_id: "Release.bbox", **bounds, limit: nil)
                context = canonical.send(:prepare_member_validation_context, arguments: arguments, native_receiver: client.release)
                validate = -> { canonical.send(:validate_operation_arguments, operation: "bbox", arguments: arguments, member_contract: context) }
                if bounds == BOX
                    assert_same arguments, validate.call
                else
                    assert_raises(OpenTideConstants::InvalidArgumentError, &validate)
                end
            end
        end
    end
end
