# Unit tests (ruby -Iruby/lib ruby/test/test_unit.rb). The conformance suite is the main proof.
$LOAD_PATH.unshift(File.expand_path("../lib", __dir__))
require "minitest/autorun"
require "json"
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
        n_sets = c.stations.sum { |s| s.constant_sets(include_no_constants: true).size }
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

# The other unit test files (CI runs this file only).
Dir[File.join(__dir__, "test_*.rb")].sort.each do |f|
    require f unless File.expand_path(f) == File.expand_path(__FILE__)
end
