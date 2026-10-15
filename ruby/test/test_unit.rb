# Unit tests (ruby -Iruby/lib ruby/test/test_unit.rb). The conformance suite is the main proof.
$LOAD_PATH.unshift(File.expand_path("../lib", __dir__))
require "minitest/autorun"
require "json"
require "tmpdir"
require "fileutils"
require "zlib"
require "digest"
require "opentideconstants"

ROOT = File.expand_path("../..", __dir__)
FIXTURES = File.join(ROOT, "conformance", "fixtures")

class FoldTest < Minitest::Test
    def test_letters_that_do_not_decompose
        assert_equal %w[tromso alesund leba strasse],
                     %w[Tromsø Ålesund Łeba Straße].map { |x| OpenTideConstants::Fold.fold(x) }
    end

    def test_packaged_table_is_the_suite_table
        pkg = File.join(ROOT, "ruby", "lib", "opentideconstants", "name_fold.json")
        assert_equal File.binread(File.join(ROOT, "conformance", "name_fold.json")), File.binread(pkg)
    end
end

class VersionTest < Minitest::Test
    R = OpenTideConstants::Release

    def test_supported_format
        assert_equal [1], OpenTideConstants::SUPPORTED_FORMAT_MAJORS
        assert_equal "1.0", OpenTideConstants::SUPPORTED_FORMAT_VERSION
        sf = JSON.parse(File.read(File.join(ROOT, "ruby", "supported-formats.json")))
        assert_equal OpenTideConstants::SUPPORTED_FORMAT_VERSION, sf["supported_format_version"]
        assert_equal OpenTideConstants::VERSION, sf["version"]
        assert_equal "ruby", sf["language"]
    end

    def test_readable_versions
        assert R.readable_version?("1.0")
        refute R.readable_version?("1.1")
        refute R.readable_version?("1.99")
        refute R.readable_version?("2.0")
        assert R.supported_major?("1.7")
        refute R.supported_major?("0.5")
        refute R.supported_major?("2.0")
        assert_nil R.version_key("1")
    end

    def test_counter_order
        ds = %w[20991231.10 20991231 20991231.2 20991230]
        assert_equal %w[20991230 20991231 20991231.2 20991231.10], ds.sort_by { |d| OpenTideConstants::Cache.datestamp_key(d) }
    end
end

class FormatOneTest < Minitest::Test
    def test_build_run_id_requires_a_string_when_present
        source = File.join(FIXTURES, "good/OTC_20991231.2.json")
        source_pin = Digest::SHA256.file(source).hexdigest
        base = JSON.parse(File.binread(source))
        observations = []
        { "number" => 17, "boolean" => true, "array" => [], "object" => {}, "missing" => :missing, "null" => nil, "empty" => "", "string" => "native-run" }.each do |name, value|
            doc = Marshal.load(Marshal.dump(base))
            station_raw = doc.fetch("stations").first
            set_raw = station_raw.fetch("constant_sets").first
            build_raw = set_raw.fetch("provenance").fetch("build")
            value == :missing ? build_raw.delete("run_id") : build_raw["run_id"] = value
            invalid = %w[number boolean array object].include?(name)
            Dir.mktmpdir("otc-run-id") do |directory|
                prefix = File.join(directory, "OTC_20991231.2")
                File.write(prefix + ".json", JSON.generate(doc))
                Zlib::GzipWriter.open(prefix + ".json.gz") { |gzip| gzip.write(JSON.generate(doc)) }
                File.write(prefix + ".jsonl", doc.fetch("stations").map { |station| JSON.generate(station) + "\n" }.join)
                File.write(prefix + ".meta.json", JSON.generate(doc.reject { |key, _row| key == "stations" }))
                [["json", :eager], ["json.gz", :eager], ["jsonl", :eager], ["jsonl", :stream]].each do |format, mode|
                    path = prefix + "." + format
                    before = Digest::SHA256.file(path).hexdigest
                    row = { case: name, format: format, mode: mode.to_s, expected_invalid: invalid }
                    begin
                        client = OpenTideConstants.new(file: path, mode: mode)
                        station = client.station(station_raw.fetch("station_id"))
                        set = station.constant_set(set_raw.fetch("set_id"))
                        actual = set.provenance.build.run_id
                        row[:actual_value] = actual
                        assert_equal station_raw, station.raw
                        assert_equal set_raw, set.raw
                        expected = value == :missing ? nil : value
                        expected.nil? ? assert_nil(actual) : assert_equal(expected, actual)
                        row[:pass] = !invalid
                    rescue OpenTideConstants::Error => error
                        row[:error_code] = error.code
                        row[:pass] = invalid && error.code == "invalid_release"
                    ensure
                        client&.close
                    end
                    assert_equal before, Digest::SHA256.file(path).hexdigest
                    observations << row
                end
            end
        end
        assert_equal source_pin, Digest::SHA256.file(source).hexdigest
        if (path = ENV["OTC_RUN_ID_PROOF_PATH"])
            File.write(path, JSON.pretty_generate(observations) + "\n")
        end
        assert_empty observations.reject { |row| row[:pass] }
    end

    def test_unknown_source_type_filter_uses_typed_enum_and_preserves_raw
        path = File.join(FIXTURES, "bad/unknown-enums/OTC_20991231.json")
        raw = JSON.parse(File.read(path)).fetch("stations").find { |station| station["station_id"] == "OTC-T-0016" }
        c = OpenTideConstants.new(file: path)
        assert_equal ["OTC-T-0016"], c.stations(source_type: :other).map(&:station_id)
        assert_empty c.stations(source_type: "satellite")
        station = c.station("OTC-T-0016")
        assert_equal :other, station.recommended_set.source_type
        assert_equal raw, station.raw
        assert_equal "satellite", station.recommended_set.raw["source_type"]
    ensure
        c&.close
    end

    def open(root, d, ext = "jsonl", mode: :eager)
        OpenTideConstants.new(file: File.join(FIXTURES, root, "OTC_#{d}.#{ext}"), mode: mode)
    end

    def test_reader_too_old_names_both_versions
        %w[json json.gz jsonl].each do |ext|
            err = assert_raises(OpenTideConstants::ReaderTooOldError) { open("reader", "20991231.4", ext) }
            assert_equal "reader_too_old", err.code
            assert_includes err.message, "1.99"
            assert_includes err.message, "format 1.0"
            assert_kind_of OpenTideConstants::Error, err
        end
    end

    def test_no_constants_hidden_by_default
        c = open("v1", "20991231.3")
        st = c.station("OTC-T-0103")
        all = st.constant_sets(include_no_constants: true)
        assert_equal all.size - 1, st.constant_sets.size
        assert(st.constant_sets.none? { |s| s.qc_status == :no_constants })
        assert_raises(OpenTideConstants::InvalidArgumentError) { st.constant_sets(include_no_constants: "yes") }
        assert_nil c.station("OTC-T-0104").recommended_set
    ensure
        c&.close
    end

    def test_stats_sources_count_usable_sets_only
        c = open("v1", "20991231.3")
        stats = c.release.stats
        doc = JSON.parse(File.read(File.join(FIXTURES, "v1", "OTC_20991231.3.json")))
        n_sets = doc.fetch("stations").sum { |s| Array(s["constant_sets"]).size }
        assert_equal n_sets, stats.qc_status.values.sum
        assert stats.qc_status.fetch(:no_constants).positive?
        assert_equal n_sets - stats.qc_status.fetch(:no_constants), stats.source.values.sum
    ensure
        c&.close
    end

    def test_unknown_qc_status_is_other
        c = open("bad/format-minor", "20991231")
        set = c.station("OTC-T-0010").constant_sets.find { |s| s.qc_status == :other }
        refute_nil set
        assert_equal "excluded", set.raw["qc_status"]
    ensure
        c&.close
    end

    # CR2 DR8: a station whose status the SDK does not know is in no query, and one warning names it.
    def test_unknown_status_is_logged_once_at_load
        lines = []
        logger = Object.new
        logger.define_singleton_method(:warn) { |m| lines << m }
        %i[debug info error].each { |lv| logger.define_singleton_method(lv) { |_m| nil } }
        c = OpenTideConstants.new(file: File.join(FIXTURES, "bad/unknown-status/OTC_20991231.jsonl"), mode: :stream, logger: logger)
        hits = lines.grep(/OTC-T-0016/)
        assert_equal 1, hits.size, lines.inspect
        assert_includes hits.first, '"retired"'
        assert_nil c.station("OTC-T-0016")
        assert_nil c.tombstone("OTC-T-0016")
    ensure
        c&.close
    end

    # CR2 DR28: a line with no status (or null) is an active station.
    def test_no_status_is_active
        c = open("bad/no-status", "20991231")
        assert_equal :active, c.station("OTC-T-0020").status
        assert_equal :active, c.station("OTC-T-0019").status
    ensure
        c&.close
    end

    def test_typed_annotations
        c = open("good", "20991231.2")
        tb = c.station("OTC-T-0011").constant_sets.map(&:time_base).compact.first
        assert_equal :corrected, tb.code
        assert_equal({ "from" => "utc_mean_start60", "to" => "utc_instant" }, tb.correction)
        assert_equal %w[comparator_kind comparator_id distance_km lag_min detail], tb.evidence.first.keys
        assert tb.frozen? && tb.evidence.frozen?
        noaa = c.station("OTC-T-0001").constant_set("OTC-T-0001/noaa")
        assert_nil noaa.time_base
        b = noaa.provenance.build
        assert_kind_of OpenTideConstants::ProvenanceBuild, b
        assert_equal Time.utc(2099, 12, 31, 6), b.built_at
        flag = c.station("OTC-T-0001").constant_set("OTC-T-0001/gesla-fit").qc_flags.first
        assert_equal [:time_base, "the time base is unverified", nil], [flag.flag, flag.reason, flag.values]
    ensure
        c&.close
    end

    def test_station_removed_carries_the_tombstone
        c = open("good", "20991231.2")
        err = assert_raises(OpenTideConstants::StationRemovedError) { c.require_station("OTC-T-0021") }
        t = err.tombstone
        assert_equal [:merged, "OTC-T-0022", nil], [t.removed_reason, t.merged_into, t.detail]
    ensure
        c&.close
    end

    def test_citation_and_attribution_use_the_concept_doi
        c = open("good", "20991231.2")
        assert_nil c.release.zenodo_version_doi
        assert_equal "OpenTideConstants contributors (2099). OpenTideConstants, release 20991231.2 [Data set]. " \
                     "https://doi.org/10.5072/zenodo.1", c.release.citation
        assert c.attribution.start_with?("Tidal constants: OpenTideConstants 20991231.2, doi:10.5072/zenodo.1, CC BY 4.0.")
        c.close
        c = open("good", "20991231")
        assert c.release.citation.end_with?("[Data set]. https://data.opentideconstants.org/OTC_20991231.json")
    ensure
        c&.close
    end
end

# PK-R2-05 (CR D17): an unpaired surrogate escape is invalid_release whatever
# the json gem does with it (json 2.6.3 reads "\ud800S" as "?" and loads).
class LoneSurrogateTest < Minitest::Test
    def check(text)
        OpenTideConstants::Util.no_lone_surrogate!(text)
    end

    def test_lone_surrogates_are_refused
        [%q({"a":"x\ud800y"}), %q({"a":"\uDBFF"}), %q({"a":"\udc00"}), %q({"a":"\ud800\u0041"}),
         %q({"a":"\ud800\ud800\udc00"}), %q({"\ud800":1}), %q({"a":"\\\\\\ud800"})].each do |t|
            assert_raises(OpenTideConstants::InvalidReleaseError, t) { check(t) }
        end
    end

    def test_pairs_and_escaped_backslashes_are_fine
        [%q({"a":"\ud83c\udf0a"}), %q({"a":"\\\\ud800"}), %q({"a":"\\\\\\\\ud800"}), %q({"a":"\u00e9 plain"}),
         %q({"a":"no escapes"})].each do |t|
            assert_nil check(t), t
        end
    end
end

# CR2 DR19 (spec §5.7): the timeout is 0.001 to 1e6 seconds in every SDK.
class TimeoutRangeTest < Minitest::Test
    FILE = File.join(FIXTURES, "good", "OTC_20991231.2.jsonl")

    def test_timeout_outside_the_range_is_invalid_argument
        [0, -1, 0.0001, 0.000999, 1e6 + 1, 1e7, Float::NAN, Float::INFINITY, Complex(1, 0)].each do |t|
            assert_raises(OpenTideConstants::InvalidArgumentError, t.inspect) do
                OpenTideConstants.new(file: FILE, timeout: t)
            end
        end
    end

    def test_timeout_at_the_bounds_is_accepted
        [0.001, 1e6, 1, 30].each do |t|
            OpenTideConstants.new(file: FILE, timeout: t).close
        end
    end
end

# The other unit test files (CI runs this file only).
Dir[File.join(__dir__, "test_*.rb")].sort.each do |f|
    # Actual H4 source proofs run explicitly with their authenticated artifact environment.
    next if %w[test_core_native.rb test_noaa_historical.rb].include?(File.basename(f))
    require f unless File.expand_path(f) == File.expand_path(__FILE__)
end

# The user and password of a URL never appear in an error message or a log
# line (spec §5.7, CR2 DR21).
class CredentialsRedactedTest < Minitest::Test
    require "logger"
    require "stringio"
    require "tmpdir"

    SECRET = "Pk12S3cretPW".freeze

    def assert_redacted(text)
        refute_includes text, SECRET
        refute_includes text, "otcuser"
        assert_includes text, "***@"
    end

    def test_bad_proxy_option_message
        ["socks5://otcuser:#{SECRET}@proxy.invalid:1080", "otcuser:#{SECRET}@proxy invalid"].each do |proxy|
            e = Dir.mktmpdir do |dir|
                assert_raises(OpenTideConstants::InvalidArgumentError) do
                    OpenTideConstants.new(proxy: proxy, cache_dir: dir)
                end
            end
            assert_redacted(e.message)
        end
    end

    def test_refused_base_url_message_and_log
        buf = StringIO.new
        e = assert_raises(OpenTideConstants::NetworkError) do
            OpenTideConstants::HTTP.new(logger: Logger.new(buf), sleeper: ->(_) {})
                                   .get("http://otcuser:#{SECRET}@127.0.0.1:1/OTC_x.json")
        end
        assert_redacted(e.message)
        assert_includes buf.string, "retry"
        assert_redacted(buf.string)
    end

    def test_any_error_message_is_redacted
        e = OpenTideConstants::CacheError.new("cannot read https://u:#{SECRET}@h.example/x and ftp://a@b/c")
        assert_equal "cannot read https://***@h.example/x and ftp://***@b/c", e.message
    end
end

# K-NC DR106 (spec §4.2): commercial_only must be true or false; any other
# value, nil included, is invalid_argument.
class CommercialOnlyTest < Minitest::Test
    KNC = File.join(FIXTURES, "knc", "OTC_20991231.2.jsonl")

    def test_commercial_only_must_be_true_or_false
        [1, 0, "true", nil, :true, [true]].each do |v|
            assert_raises(OpenTideConstants::InvalidArgumentError, v.inspect) do
                OpenTideConstants.new(file: KNC, commercial_only: v)
            end
        end
        c = OpenTideConstants.new(file: KNC, commercial_only: true)
        assert_equal "OTC-T-0181/w-ok", c.station("OTC-T-0181").recommended_set.set_id
        c.close
        c = OpenTideConstants.new(file: KNC, commercial_only: false)
        assert_equal "OTC-T-0181/x-nc", c.station("OTC-T-0181").recommended_set.set_id
        c.close
    end
end
