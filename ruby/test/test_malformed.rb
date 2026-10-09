# Malformed input and bad arguments surface as SDK errors, at load and in
# every load path (spec §4.8, §7.3, CR D31, D36).
require_relative "support"

class MalformedDataTest < Minitest::Test
    include TestSupport
    OTC = OpenTideConstants

    PATHS = [["json", :eager], ["jsonl", :eager], ["jsonl", :stream]].freeze

    def assert_invalid(what, &change)
        PATHS.each do |ext, mode|
            path = release_file(ext, &change)
            err = assert_raises(OTC::InvalidReleaseError, "#{what} (#{ext}, #{mode})") { OTC.new(file: path, mode: mode).close }
            assert_equal "invalid_release", err.code
        end
    end

    def set_of(doc, id = "OTC-T-0001")
        station_in(doc, id)["constant_sets"][0]
    end

    # R18 + R43: nested elements of the wrong type fail the load in every
    # mode (stream mode too, not at the first query).
    def test_nested_elements_of_the_wrong_type
        {
            "qc_flags a string" => ->(d) { set_of(d)["qc_flags"] = "time_base" },
            "a qc_flag a string" => ->(d) { set_of(d)["qc_flags"] = ["time_base"] },
            "dropped a string" => ->(d) { set_of(d)["dropped_constituents"] = "M4" },
            "constituents an object" => ->(d) { set_of(d)["constituents"] = { "name" => "M2" } },
            "a constituent with no name" => ->(d) { set_of(d)["constituents"] = [{ "amplitude_m" => 1 }] },
            "validation a string" => ->(d) { station_in(d, "OTC-T-0001")["validation"] = "good" },
            "datum.named a list" => ->(d) { set_of(d)["datum"] = { "msl_offset_m" => 0, "named" => [1] } },
            "months_dropped a string" => lambda { |d|
                st = d["stations"].find { |s| s["constant_sets"].any? { |cs| cs["time_base"].is_a?(Hash) } }
                st["constant_sets"].find { |cs| cs["time_base"].is_a?(Hash) }["time_base"]["months_dropped"] = "2020-01"
            },
            "set_id missing" => ->(d) { set_of(d).delete("set_id") },
            "country a number" => ->(d) { station_in(d, "OTC-T-0001")["country"] = 840 },
            "name a number" => ->(d) { station_in(d, "OTC-T-0001")["name"] = 7 },
            "lon out of range" => ->(d) { station_in(d, "OTC-T-0001")["lon"] = 200 },
            "provenance a string" => ->(d) { set_of(d)["provenance"] = "pipeline" },
            "a convention not an object" => ->(d) { d["conventions"] << "x" }
        }.each { |what, change| assert_invalid(what, &change) }
    end

    # R12: a time that is not a String is invalid_release, not a raw TypeError.
    def test_time_not_a_string
        assert_invalid("created 5") { |d| d["release"]["created"] = 5 }
        assert_invalid("record_span.start 5") { |d| set_of(d)["record_span"] = { "start" => 5, "end" => nil } }
    end

    # R44: a malformed provenance.build time does not fail the station (spec
    # §4.6: the build data is information only); it reads as nil.
    def test_bad_build_time_is_nil
        path = release_file { |d| set_of(d)["provenance"]["build"]["built_at"] = "yesterday" }
        c = OTC.new(file: path)
        assert_nil c.station("OTC-T-0001").constant_sets(include_no_constants: true)[0].provenance.build.built_at
    ensure
        c&.close
    end

    # A JSON string that is not valid UTF-8 fails the load (CR D17 rule: not valid Unicode).
    def test_invalid_utf8_name
        PATHS.each do |ext, mode|
            path = release_file(ext) { |d| station_in(d, "OTC-T-0001")["name"] = "MARK" }
            File.binwrite(path, File.binread(path).sub("MARK", "M\xFFK".b)) if ext == "json"
            File.binwrite(path, File.binread(path).sub("MARK", "M\xFFK".b)) if ext == "jsonl"
            assert_raises(OTC::InvalidReleaseError, "#{ext} #{mode}") { OTC.new(file: path, mode: mode).close }
        end
    end
end

class BadArgumentTest < Minitest::Test
    include TestSupport
    OTC = OpenTideConstants

    def client
        @client ||= OTC.new(file: fixture("good", "OTC_20991231.2.json"))
    end

    def teardown
        @client&.close
        super
    end

    # R4: a base_url that is not a String is invalid_argument.
    def test_base_url_not_a_string
        assert_raises(OTC::InvalidArgumentError) { OTC.new(base_url: 5, cache_dir: tmpdir, offline: true) }
    end

    # R36 (CR D31): file cannot be combined with release or on_network_error.
    # (offline: true stays allowed until the suite's download/offline-not-cached
    # case, which combines it with file, is changed.)
    def test_file_with_conflicting_options
        f = fixture("good", "OTC_20991231.2.json")
        [{ release: "20991231.2" }, { on_network_error: :raise }].each do |opt|
            assert_raises(OTC::InvalidArgumentError, opt.inspect) { OTC.new(file: f, **opt) }
        end
    end

    # R21: a Complex number is a bad argument, not a NoMethodError.
    def test_complex_numbers
        assert_raises(OTC::InvalidArgumentError) { client.near(lat: Complex(1, 1), lon: 0, radius_km: 10) }
        assert_raises(OTC::InvalidArgumentError) { client.near(lat: 1, lon: 0, radius_km: Complex(1, 1)) }
        assert_raises(OTC::InvalidArgumentError) { client.nearest(lat: 1, lon: 0, max_km: Complex(1, 0)) }
    end

    # R17: a query that is not valid UTF-8, or not UTF-8 at all, is handled.
    def test_query_encodings
        assert_raises(OTC::InvalidArgumentError) { client.search(name: "M\xFFK".dup.force_encoding("UTF-8")) }
        latin = "Troms\xF8".dup.force_encoding("ISO-8859-1")
        assert_equal ["OTC-T-0006"], client.search(name: "Tromsø").map(&:station_id)
        assert_equal ["OTC-T-0006"], client.search(name: latin).map(&:station_id)
    end

    # R91: an empty filter value matches nothing, not the stations whose field is null.
    # The release has an active station with each field null (type cannot be null).
    def test_empty_filter_value
        null = {
            country: ->(s) { s.country.nil? },
            kind: ->(s) { s.kind.nil? },
            source: ->(s) { s.constant_sets.any? { |cs| cs.source.nil? } },
            source_type: ->(s) { s.recommended_set && s.recommended_set.source_type.nil? }
        }
        MalformedDataTest::PATHS.each do |ext, mode|
            path = release_file(ext) do |d|
                st = station_in(d, "OTC-T-0001")
                st["country"] = nil
                st["constant_sets"].each { |cs| cs["source"] = cs["source_type"] = nil }
                station_in(d, "OTC-T-0002")["recommended_set_id"] = nil # no recommended set: kind is null
            end
            c = OTC.new(file: path, mode: mode)
            null.each { |k, test| assert(c.stations.any?(&test), "#{ext} #{mode}: no station with a null #{k}") }
            %i[country type kind source source_type].each do |k|
                assert_equal [], c.stations(k => "").map(&:station_id), "#{k} (#{ext}, #{mode})"
            end
        ensure
            c&.close
        end
    end

    # D36: limit must be 1 or more.
    def test_limit_zero
        assert_raises(OTC::InvalidArgumentError) { client.search(name: "a", limit: 0) }
        assert_raises(OTC::InvalidArgumentError) { client.near(lat: 0, lon: 0, radius_km: 1, limit: 0) }
    end

    # R22: stats works when values are of mixed types (an unknown type is :other).
    def test_stats_with_unknown_values
        path = release_file { |d| station_in(d, "OTC-T-0001")["type"] = "weird" }
        c = OTC.new(file: path)
        assert_equal 1, c.release.stats.type[:other]
    ensure
        c&.close
    end
end
