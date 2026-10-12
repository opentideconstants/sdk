# The stream index (spec §6.2, CR D4).
require_relative "support"

class StreamIndexTest < Minitest::Test
    include TestSupport
    OTC = OpenTideConstants
    D = "20991231.2".freeze

    # A copy of fixtures/good whose .jsonl is changed by the block, with a
    # matching .sha256 (the pointer is not read for a pinned release).
    def release_dir_with
        dir = tmpdir
        FileUtils.cp_r(Dir[File.join(FIXTURES, "good", "*")], dir)
        jsonl = File.join(dir, "OTC_#{D}.jsonl")
        File.binwrite(jsonl, yield(File.binread(jsonl)))
        sums = File.read(File.join(dir, "OTC_#{D}.sha256")).lines.map do |l|
            l.end_with?("OTC_#{D}.jsonl\n") ? "#{Digest::SHA256.file(jsonl).hexdigest}  OTC_#{D}.jsonl\n" : l
        end
        File.write(File.join(dir, "OTC_#{D}.sha256"), sums.join)
        dir
    end

    def index_path(cache)
        File.join(cache, "v1", "releases", D, "index-v1.json")
    end

    # R19: a line with no status still gives an index entry that is fresh,
    # so the index is not rebuilt on every open.
    def test_line_without_status_keeps_the_index_fresh
        dir = release_dir_with { |b| b.sub('"status":"active",', "").sub('"status": "active", ', "") }
        refute_equal File.binread(fixture("good", "OTC_#{D}.jsonl")), File.binread(File.join(dir, "OTC_#{D}.jsonl"))
        srv = serve(dir)
        cache = tmpdir
        OTC.new(release: D, base_url: srv.url("/"), cache_dir: cache, mode: :stream).close
        first = File.stat(index_path(cache)).ino
        c = OTC.new(release: D, cache_dir: cache, mode: :stream, offline: true)
        assert_equal first, File.stat(index_path(cache)).ino, "the index was written again"
    ensure
        c&.close
    end

    def tamper_index(cache)
        idx = JSON.parse(File.read(index_path(cache)))
        yield idx["stations"]
        File.write(index_path(cache), JSON.generate(idx))
    end

    def test_complete_legacy_index_stays_lazy_and_reads_full_records
        srv = serve
        cache = tmpdir
        original = OTC.new(release: D, base_url: srv.url("/"), cache_dir: cache, mode: :stream)
        raw = original.station("OTC-T-0001").raw
        original.close
        tamper_index(cache) do |rows|
            rows.each do |row|
                row.delete("subordinate_offsets")
                row["sets"].each { |set| %w[source_record_id source_version datum].each { |key| set.delete(key) } }
            end
        end
        inode = File.stat(index_path(cache)).ino
        c = OTC.new(release: D, cache_dir: cache, mode: :stream, offline: true)
        assert_equal inode, File.stat(index_path(cache)).ino, "legacy index was rebuilt at open"
        assert_equal raw, c.station("OTC-T-0001").raw
        assert_equal 18, c.stations.size
    ensure
        original&.close
        c&.close
    end

    def test_partial_expanded_index_is_stale
        srv = serve
        cache = tmpdir
        OTC.new(release: D, base_url: srv.url("/"), cache_dir: cache, mode: :stream).close
        built = JSON.parse(File.read(index_path(cache)))
        c = nil
        ["subordinate_offsets", "source_record_id", "source_version", "datum"].each do |key|
            tamper_index(cache) do |rows|
                if key == "subordinate_offsets"
                    rows.find { |row| row["sets"].empty? }.delete(key)
                else
                    rows.find { |row| !row["sets"].empty? }["sets"][0].delete(key)
                end
            end
            c = OTC.new(release: D, cache_dir: cache, mode: :stream, offline: true)
            assert_equal built, JSON.parse(File.read(index_path(cache))), key
            c.close
        end
    ensure
        c&.close
    end

    # R42/D4: an entry whose line has another station_id is invalid_release
    # naming index-v1.json, and the index is deleted so the next open rebuilds it.
    def test_line_that_does_not_match_its_entry
        srv = serve
        cache = tmpdir
        OTC.new(release: D, base_url: srv.url("/"), cache_dir: cache, mode: :stream).close
        tamper_index(cache) do |st|
            st[0]["station_id"], st[1]["station_id"] = st[1]["station_id"], st[0]["station_id"]
        end
        c = OTC.new(release: D, cache_dir: cache, mode: :stream, offline: true)
        err = assert_raises(OTC::InvalidReleaseError) { c.station("OTC-T-0001") }
        assert_includes err.message, "index-v1.json"
        refute File.exist?(index_path(cache))
        c.close
        c = OTC.new(release: D, cache_dir: cache, mode: :stream, offline: true)
        assert_equal "OTC-T-0001", c.station("OTC-T-0001").station_id
    ensure
        c&.close
    end

    # R42/D4: an entry out of bounds makes the index stale, so the open
    # rebuilds it (never a raw TypeError at query time).
    def test_out_of_bounds_entries_make_the_index_stale
        [->(st) { st[-1]["offset"] = 10**6 }, ->(st) { st[3]["length"] = 0 },
         ->(st) { st[2]["offset"] = st[1]["offset"] }].each do |tamper|
            srv = serve
            cache = tmpdir
            OTC.new(release: D, base_url: srv.url("/"), cache_dir: cache, mode: :stream).close
            built = JSON.parse(File.read(index_path(cache)))
            tamper_index(cache, &tamper)
            refute_equal built, JSON.parse(File.read(index_path(cache)))
            begin
                c = OTC.new(release: D, cache_dir: cache, mode: :stream, offline: true)
                # Rebuilt at open: the index on disk is the one a fresh build writes.
                assert_equal built, JSON.parse(File.read(index_path(cache))), "the stale index was not rebuilt at open"
                assert_equal 20, c.release.station_count
                assert_equal 18, c.stations.size
                assert(c.stations.all? { |s| s.is_a?(OTC::Station) })
            ensure
                c&.close
            end
        end
    end

    # R3-226 (release.rb): a stream line that cannot be parsed is
    # invalid_release with the reason (the JSON error, the unpaired
    # surrogate), not only "is not a station line".
    def test_a_line_that_does_not_parse_gives_the_reason
        {
            "JSON" => ->(b) { b[0] = "X" },
            "unpaired surrogate" => ->(b) { i = b.index('"name":"') + 8; b[i, 6] = "\\ud800" }
        }.each do |what, tamper|
            srv = serve
            cache = tmpdir
            c = OTC.new(release: D, base_url: srv.url("/"), cache_dir: cache, mode: :stream)
            path = File.join(cache, "v1", "releases", D, "OTC_#{D}.jsonl")
            bytes = File.binread(path)
            assert bytes.start_with?('{"aliases":{"gesla":["test-gesla-0001a"'), "OTC-T-0001 is the first line"
            tampered = bytes.dup
            tamper.call(tampered)
            assert_equal bytes.bytesize, tampered.bytesize
            File.open(path, "r+b") { |f| f.write(tampered) } # the same file the release holds open
            err = assert_raises(OTC::InvalidReleaseError, what) { c.station("OTC-T-0001") }
            assert_includes err.message, "is not a station line: ", what
            if what == "JSON"
                assert_match(/unexpected|expected/i, err.message.split("is not a station line: ", 2).last, what)
            else
                assert_includes err.message, "unpaired surrogate (\\ud800)", what
            end
        ensure
            c&.close
        end
    end
end
