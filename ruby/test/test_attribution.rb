# Attribution edge cases (spec §4.6, CR D2).
require_relative "support"

class AttributionTest < Minitest::Test
    include TestSupport
    OTC = OpenTideConstants

    # R47 (CR D2 a): a Station from another release is invalid_argument, not skipped.
    def test_station_from_another_release
        %i[eager stream].each do |mode|
            a = OTC.new(file: fixture("good", "OTC_20991231.2.jsonl"), mode: mode)
            b = OTC.new(file: fixture("good", "OTC_20991231.jsonl"), mode: mode)
            foreign = b.station("OTC-T-0001")
            refute_nil foreign
            assert_raises(OTC::InvalidArgumentError, mode.to_s) { a.attribution([foreign]) }
            assert_kind_of String, a.attribution([a.station("OTC-T-0001")])
        ensure
            a&.close
            b&.close
        end
    end

    # CR D2 c: an empty list is the full-release text.
    def test_empty_list
        c = OTC.new(file: fixture("good", "OTC_20991231.2.json"))
        assert_equal c.attribution, c.attribution([])
    ensure
        c&.close
    end

    # CR D2 b: a licence with a null provider prints its attribution alone and
    # is never merged with another.
    def test_null_provider
        path = release_file do |d|
            d["licences"].each { |l| l["provider"] = nil }
        end
        c = OTC.new(file: path)
        text = c.attribution
        assert_includes text, "Sources: "
        sources = text.split("Sources: ", 2)[1].split("; ")
        assert_equal c.release.licences.size, sources.size
        assert_equal c.release.licences.map(&:attribution).sort, sources.sort, "a null provider is printed"
    ensure
        c&.close
    end

    # CR D2 b, mixed: a null-provider licence next to licences that share a
    # provider. The shared ones merge into one segment; the null one stays alone.
    def test_null_provider_next_to_a_shared_provider
        lics = nil
        path = release_file do |d|
            d["licences"].each { |l| l["provider"] = "Shared" }
            d["licences"][0]["provider"] = nil
            lics = d["licences"].sort_by { |l| l["licence_id"] }
        end
        c = OTC.new(file: path)
        null_one = lics.find { |l| l["provider"].nil? }
        first_shared = lics.find { |l| l["provider"] == "Shared" }
        want = lics.select { |l| l.equal?(null_one) || l.equal?(first_shared) }
                   .map { |l| l["provider"] ? "Shared: #{l['attribution']}" : l["attribution"] }
        text = c.attribution
        assert_includes text, "Sources: "
        assert_equal want, text.split("Sources: ", 2)[1].split("; ")
    ensure
        c&.close
    end
end
