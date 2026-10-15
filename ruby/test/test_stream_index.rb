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

    def test_dense_foreign_and_sparse_nullable_profiles_stay_lazy_then_refuse_country_tamper
        c = nil
        srv = serve
        cache = tmpdir
        OTC.new(release: D, base_url: srv.url("/"), cache_dir: cache, mode: :stream).close
        built = JSON.parse(File.read(index_path(cache)))
        [false, true].each do |sparse|
            idx = Marshal.load(Marshal.dump(built))
            idx["discovery_index_version"] = 1
            idx["stations"].each do |row|
                row["sets"].each do |cs|
                    %w[source_record_id source_version datum].each { |key| cs.delete(key) }
                    cs.delete("fallback") if sparse && cs["fallback"].nil?
                end
                row.delete("subordinate_offsets") if sparse && row["subordinate_offsets"].nil?
                row.delete("current_offsets") if sparse && row["current_offsets"].empty?
            end
            idx["stations"].find { |row| row["station_id"] == "OTC-T-0011" }["country"] = "ZZ"
            File.write(index_path(cache), JSON.generate(idx))
            sha = Digest::SHA256.file(index_path(cache)).hexdigest
            c = OTC.new(release: D, cache_dir: cache, mode: :stream, offline: true)
            assert_equal sha, Digest::SHA256.file(index_path(cache)).hexdigest
            assert_equal "OTC-T-0001", c.station("OTC-T-0001").station_id
            assert_raises(OTC::InvalidReleaseError) { c.stations(country: "ZZ") }
            refute File.exist?(index_path(cache))
            c.close
        end
    ensure
        c&.close
    end

    def test_present_invalid_marker_and_mixed_private_metadata_rebuild
        c = nil
        srv = serve
        cache = tmpdir
        OTC.new(release: D, base_url: srv.url("/"), cache_dir: cache, mode: :stream).close
        built = JSON.parse(File.read(index_path(cache)))
        mutations = [nil, true, "1", 0, 1.5, 2].map { |value| ->(idx) { idx["discovery_index_version"] = value } }
        mutations << ->(idx) { idx["stations"].first["sets"].first["source_record_id"] = nil }
        mutations << ->(idx) { %w[source_record_id source_version datum].each { |k| idx["stations"].first["sets"].first[k] = nil } }
        mutations << ->(idx) { idx["stations"].first["sets"].first["fallback"] = false }
        mutations << ->(idx) { idx["stations"].first["sets"].first["current_bins"] = nil }
        mutations.each do |mutate|
            idx = Marshal.load(Marshal.dump(built))
            mutate.call(idx)
            File.write(index_path(cache), JSON.generate(idx))
            c = OTC.new(release: D, cache_dir: cache, mode: :stream, offline: true)
            assert_equal built, JSON.parse(File.read(index_path(cache)))
            c.close
        end
    ensure
        c&.close
    end

    def test_foreign_cached_set_and_constituent_tamper_is_refused_lazily
        c = nil
        srv = serve
        cache = tmpdir
        OTC.new(release: D, base_url: srv.url("/"), cache_dir: cache, mode: :stream).close
        built = JSON.parse(File.read(index_path(cache)))
        mutations = [->(cs) { cs["set_id"] = "wrong-set" }, ->(cs) { cs["constituents"].pop }]
        mutations.each do |mutate|
            idx = Marshal.load(Marshal.dump(built))
            idx["stations"].each { |row| row["sets"].each { |cs| %w[source_record_id source_version datum].each { |k| cs.delete(k) } } }
            row = idx["stations"].first
            mutate.call(row["sets"].first)
            row["recommended_set_id"] = row["sets"].first["set_id"]
            File.write(index_path(cache), JSON.generate(idx))
            c = OTC.new(release: D, cache_dir: cache, mode: :stream, offline: true)
            assert File.file?(index_path(cache))
            assert_raises(OTC::InvalidReleaseError) { c.station("OTC-T-0001") }
            refute File.exist?(index_path(cache))
            c.close
        end
    ensure
        c&.close
    end

    def test_integral_float_index_and_nul_alias_are_admitted_then_source_checked
        srv = serve
        cache = tmpdir
        OTC.new(release: D, base_url: srv.url("/"), cache_dir: cache, mode: :stream).close
        idx = JSON.parse(File.read(index_path(cache)))
        idx["index_version"] = 1.0
        idx["discovery_index_version"] = 1.0
        idx["jsonl_size"] = idx["jsonl_size"].to_f
        idx["stations"].each do |row|
            %w[offset length].each { |key| row[key] = row[key].to_f }
        end
        idx["stations"].first["aliases"]["test"] = ["a\0b"]
        File.write(index_path(cache), JSON.generate(idx))
        sha = Digest::SHA256.file(index_path(cache)).hexdigest
        c = OTC.new(release: D, cache_dir: cache, mode: :stream, offline: true)
        assert_equal sha, Digest::SHA256.file(index_path(cache)).hexdigest
        assert_raises(OTC::InvalidReleaseError) { c.station_by_alias("test", "a\0b") }
        refute File.exist?(index_path(cache))
    ensure
        c&.close
    end

    def test_dense_foreign_policy_reads_only_after_a_matching_query
        srv = serve
        cache = tmpdir
        OTC.new(release: D, base_url: srv.url("/"), cache_dir: cache, mode: :stream).close
        tamper_index(cache) do |rows|
            rows.each { |row| row["sets"].each { |cs| %w[source_record_id source_version datum].each { |key| cs.delete(key) } } }
        end
        c = OTC.new(release: D, cache_dir: cache, mode: :stream, offline: true)
        io = c.release.instance_variable_get(:@io)
        reads = 0
        original_read = io.method(:read)
        io.define_singleton_method(:read) do |*args|
            reads += 1
            original_read.call(*args)
        end
        assert_empty c.stations(country: "not-a-country")
        assert_equal 0, reads, "an unmatched query read station lines"
        assert_includes c.stations(country: "USA").map(&:station_id), "OTC-T-0001"
        assert_operator reads, :>, 0, "selected private policy metadata was not read"
        assert c.release.instance_variable_get(:@entries).all? { |entry| entry.station.nil? }
    ensure
        c&.close
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

    def test_missing_source_rows_and_wrong_derived_kinds_rebuild_once
        c = nil
        srv = serve
        cache = tmpdir
        OTC.new(release: D, base_url: srv.url("/"), cache_dir: cache, mode: :stream).close
        built = File.binread(index_path(cache))
        repaired = []
        [->(rows) { rows.reject! { |row| row["station_id"] == "OTC-T-0011" } }, ->(rows) { rows.first["kind"] = "current" }].each do |mutate|
            idx = JSON.parse(built.dup) # an older json gem re-tags the string it parses as UTF-8
            mutate.call(idx["stations"])
            File.write(index_path(cache), JSON.generate(idx))
            c = OTC.new(release: D, cache_dir: cache, mode: :stream, offline: true)
            repaired << [File.binread(index_path(cache)) == built, c.release.station_count]
            c.close
        end
        assert_equal [[true, 20], [true, 20]], repaired
    ensure
        c&.close
    end

    def test_stream_authentication_checks_actual_source_hash_before_index_trust
        srv = serve
        cache = tmpdir
        OTC.new(release: D, base_url: srv.url("/"), cache_dir: cache, mode: :stream).close
        file = File.join(cache, "v1", "releases", D, "OTC_#{D}.jsonl")
        original = File.binread(file)
        File.binwrite(file, original.sub('"country":"USA"', '"country":"ZZZ"'))
        assert_equal original.bytesize, File.size(file)
        assert_raises(OTC::ChecksumError) { OTC.new(release: D, cache_dir: cache, mode: :stream, offline: true) }
    end

    def test_actual_unterminated_cr_and_crlf_body_spans
        c = nil
        ["\r", "\r\n"].each do |ending|
            dir = release_dir_with { |bytes| bytes.delete_suffix("\n") + ending }
            srv = serve(dir)
            cache = tmpdir
            c = OTC.new(release: D, base_url: srv.url("/"), cache_dir: cache, mode: :stream)
            row = JSON.parse(File.read(index_path(cache)))["stations"].last
            bytes = File.binread(File.join(dir, "OTC_#{D}.jsonl"))
            assert_equal bytes.bytesize - (ending == "\r\n" ? 2 : 0), row["offset"] + row["length"]
            c.close
        end
    ensure
        c&.close
    end

    def test_real_stream_lru_evicts_without_changing_raw_or_ownership
        file = release_file("jsonl") do |doc|
            original = doc["stations"].first
            doc["stations"] = 257.times.map do |i|
                row = Marshal.load(Marshal.dump(original))
                row["station_id"] = "LRU-#{i}"
                row["aliases"] = {}
                row["constant_sets"].each { |cs| cs["set_id"] = "LRU-#{i}/#{cs['source']}" }
                row["recommended_set_id"] = row["constant_sets"].first["set_id"]
                row
            end
        end
        c = OTC.new(file: file, mode: :stream)
        io = c.release.instance_variable_get(:@io)
        first = c.station("LRU-0")
        assert_same first, c.station("LRU-0")
        (1..256).each { |i| c.station("LRU-#{i}") }
        cache = c.release.instance_variable_get(:@station_cache)
        assert_equal 256, cache.size
        refute cache.key?("LRU-0")
        again = c.station("LRU-0")
        refute_same first, again
        assert_equal first.raw, again.raw
        assert_same io, c.release.instance_variable_get(:@io)
        c.close
        assert io.closed?
        assert_empty cache
        assert_raises(OTC::FileError) { c.station("LRU-0") }
        assert_equal first.raw, again.raw
    ensure
        c&.close
    end

    def test_derived_kind_stops_after_sixteen_source_links
        file = release_file("jsonl") do |doc|
            parent = doc["stations"].first
            parent["station_id"] = "chain-root"
            parent["aliases"] = {}
            doc["stations"] = [parent]
            17.times do |i|
                doc["stations"] << {
                    "station_id" => "chain-#{i + 1}", "name" => "Chain #{i + 1}", "type" => "subordinate",
                    "lat" => 0, "lon" => 0, "constant_sets" => [], "recommended_set_id" => nil,
                    "subordinate_offsets" => { "reference_station_id" => i.zero? ? "chain-root" : "chain-#{i}", "licence_id" => "noaa" }
                }
            end
        end
        c = OTC.new(file: file, mode: :stream)
        assert_equal :tide, c.station("chain-16").kind
        assert_nil c.station("chain-17").kind
    ensure
        c&.close
    end
end
