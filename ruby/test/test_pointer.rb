# Pointer and index entries from the server, and local file names (spec §4.2, §4.3, §5.2).
require_relative "support"

class PointerEntryTest < Minitest::Test
    include TestSupport
    OTC = OpenTideConstants

    def pointer(**changes)
        doc = JSON.parse(File.read(fixture("good", "OTC_latest-f1.json")))
        changes.each { |k, v| doc[k.to_s] = v }
        [200, {}, JSON.generate(doc)]
    end

    def client_on(srv)
        OTC.new(base_url: srv.url("/"), cache_dir: tmpdir, on_network_error: :raise)
    end

    # R30: a malformed datestamp in the pointer is invalid_release, not "no update".
    def test_bad_pointer_datestamp_is_invalid_release
        over = {}
        srv = serve(File.join(FIXTURES, "good"), over)
        c = client_on(srv)
        ["latest", "2026-10-08", "20261008.01", "20261008\n", "../../x", "20261008.1234567890"].each do |bad|
            over["OTC_latest-f1.json"] = pointer(datestamp: bad)
            %i[latest check_for_update update!].each do |op|
                err = assert_raises(OTC::InvalidReleaseError, "#{op} with #{bad.inspect}") { c.public_send(op) }
                assert_equal "invalid_release", err.code
            end
        end
    ensure
        c&.close
    end

    # R31: a files[] element that is not an object, or a url that is not a
    # String or not a URL, is invalid_release (not a raw TypeError or a guess).
    def test_bad_pointer_files_are_invalid_release
        over = {}
        srv = serve(File.join(FIXTURES, "good"), over)
        c = client_on(srv)
        good_files = JSON.parse(File.read(fixture("good", "OTC_latest-f1.json")))["files"]
        # files that is not a list is the wrong shape: a network error (CR2 DR13)
        over["OTC_latest-f1.json"] = pointer(files: "not a list")
        assert_equal "network", assert_raises(OTC::NetworkError) { c.latest }.code
        bads = [
            ["OTC_20991231.2.json"],
            [5],
            [good_files[0].merge("url" => 42)],
            [good_files[0].merge("url" => "http://[bad")],
            [good_files[0].merge("name" => nil)]
        ]
        bads.each do |files|
            over["OTC_latest-f1.json"] = pointer(files: files)
            err = assert_raises(OTC::InvalidReleaseError, "files #{files.inspect}") { c.latest }
            assert_equal "invalid_release", err.code
        end
    ensure
        c&.close
    end

    def test_index_without_releases_is_network_a_bad_entry_invalid_release
        over = {}
        srv = serve(File.join(FIXTURES, "good"), over)
        c = client_on(srv)
        # no releases list is the wrong shape: a network error (CR2 DR13); a bad entry is invalid_release
        [{}, { "releases" => "x" }].each do |doc|
            over["OTC_index.json"] = [200, {}, JSON.generate(doc)]
            err = assert_raises(OTC::NetworkError, doc.inspect) { c.releases }
            assert_equal "network", err.code
        end
        over["OTC_index.json"] = [200, {}, JSON.generate({ "releases" => [5] })]
        err = assert_raises(OTC::InvalidReleaseError) { c.releases }
        assert_equal "invalid_release", err.code
    ensure
        c&.close
    end

    # R85: a file name whose datestamp is not valid is invalid_argument.
    def test_file_name_with_a_bad_counter_is_invalid_argument
        dir = tmpdir
        %w[OTC_20991231.01.json OTC_20991231.1.json OTC_20991231.0.json OTC_20991231.1234567890.json
           OTC_2099123.json OTC_20991231.2.meta.json].each do |name|
            FileUtils.cp(fixture("good", "OTC_20991231.json"), File.join(dir, name))
            err = assert_raises(OTC::InvalidArgumentError, name) { OTC.new(file: File.join(dir, name)) }
            assert_equal "invalid_argument", err.code
        end
    end

    # R85: the datestamp regex has the 9-digit counter bound (CR D18).
    def test_datestamp_counter_bound
        assert "20991231.123456789".match?(OTC::DATESTAMP_RE)
        refute "20991231.1234567890".match?(OTC::DATESTAMP_RE)
        refute "20991231.01".match?(OTC::DATESTAMP_RE)
        refute "20991231.1".match?(OTC::DATESTAMP_RE)
        refute "20991231\n".match?(OTC::DATESTAMP_RE)
    end

    # R60: latest skips a release this gem cannot read, as opening latest does
    # (spec §4.3 latest, §5.2 step 2a, CR D23).
    def test_latest_skips_an_unreadable_release
        srv = serve(File.join(FIXTURES, "reader"))
        c = OTC.new(base_url: srv.url("/"), cache_dir: tmpdir)
        # 20991231.4 needs a reader for format 1.99; .3 is the newest this gem reads.
        assert_equal "20991231.3", c.release.datestamp
        assert_equal "20991231.3", c.latest.datestamp
    ensure
        c&.close
    end
end
