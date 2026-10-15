# The README examples run, against the fixture release (spec §4.2, PK16).
# Each ```ruby block is run with its datestamp and NOAA id swapped for the
# fixture's, OPENTIDECONSTANTS_BASE_URL set to a local server and
# OPENTIDECONSTANTS_CACHE_DIR to a temporary directory.
require_relative "support"
require "stringio"

class ReadmeTest < Minitest::Test
    include TestSupport
    OTC = OpenTideConstants
    README = File.join(TestSupport::ROOT, "ruby", "README.md")

    def blocks
        File.read(README).scan(/^```ruby\n(.*?)^```/m).map(&:first)
    end

    def run_block(code, srv, cache, dir)
        code = code.gsub("20261008", "20991231.2").gsub("9414290", "9900001").gsub("vendor/tides", File.join(dir, "tides"))
        old = ENV.to_h.slice("OPENTIDECONSTANTS_BASE_URL", "OPENTIDECONSTANTS_CACHE_DIR")
        ENV["OPENTIDECONSTANTS_BASE_URL"] = srv.url("/")
        ENV["OPENTIDECONSTANTS_CACHE_DIR"] = cache
        out = StringIO.new
        saved = $stdout
        $stdout = out
        Object.new.instance_eval(code)
        out.string
    ensure
        $stdout = saved if saved
        %w[OPENTIDECONSTANTS_BASE_URL OPENTIDECONSTANTS_CACHE_DIR].each { |k| ENV[k] = old[k] }
    end

    def test_readme_examples_run
        srv = serve
        cache = tmpdir
        dir = tmpdir
        assert_operator blocks.size, :>=, 3
        out = blocks.map { |b| run_block(b, srv, cache, dir) }.join
        assert_match(/M2 [0-9.]+ m/, out)
        assert_includes out, "Tidal constants: OpenTideConstants 20991231.2"
        # Block 3's claim: the file open after download is loaded_from :file, so the .sha256 is next to it.
        %w[jsonl meta.json sha256].each { |x| assert File.file?(File.join(dir, "tides", "OTC_20991231.2.#{x}")), x }
        c = OTC.new(file: File.join(dir, "tides", "OTC_20991231.2.jsonl"))
        assert_equal :file, c.loaded_from
    ensure
        c&.close
    end
end
