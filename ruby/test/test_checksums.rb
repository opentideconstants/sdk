# Checksum agreement, verify and corrupt-cache recovery (spec §4.3, §4.8, §5.2 step 4, CR D20).
require_relative "support"

class CacheEncodingTest < Minitest::Test
    include TestSupport
    OTC = OpenTideConstants
    D = "20991231.2".freeze

    def golden
        JSON.parse(File.read(File.join(ROOT, "conformance/canonical/cache-golden.json")))
    end

    def value_for(fixture)
        fixture.key?("binary64_hex") ? [fixture.fetch("binary64_hex")].pack("H*").unpack1("G") : fixture.fetch("input")
    end

    def test_verified_writer_emits_approved_finite_bytes
        golden.fetch("cases").each do |fixture|
            cache = OTC::Cache.new(tmpdir)
            cache.write_verified(D, {}, "format_version" => value_for(fixture))
            bytes = File.binread(File.join(cache.release_dir(D), ".verified"))
            document = JSON.parse(bytes.dup) # an older json gem re-tags the string it parses as UTF-8
            assert_equal "opentideconstants-ruby/#{OTC::VERSION}", document.fetch("by")
            assert Time.iso8601(document.fetch("verified_at"))
            expected = '{"by":' + JSON.generate(document.fetch("by")) + ',"datestamp":"' + D +
                       '","files":{},"format_version":' + fixture.fetch("expected") +
                       ',"min_reader_version":null,"verified_at":' + JSON.generate(document.fetch("verified_at")) +
                       ',"zenodo_version_doi":null}'
            assert_equal expected.b, bytes, fixture.fetch("id")
        end
    end

    def test_callable_matches_approved_finite_vectors
        golden.fetch("cases").each do |fixture|
            bytes = OTC::Cache.encode_cache_json(value_for(fixture))
            assert_equal Encoding::UTF_8, bytes.encoding
            assert_equal fixture.fetch("expected"), bytes, fixture.fetch("id")
        end
    end

    def test_callable_refuses_nonfinite_invalid_unicode_and_non_json_values
        [Float::NAN, Float::INFINITY, -Float::INFINITY, "\xed\xa0\x80".b.force_encoding(Encoding::UTF_8),
         "\xed\xbf\xbf".b.force_encoding(Encoding::UTF_8), Object.new, { :key => 1 }].each do |value|
            assert_raises(ArgumentError, EncodingError) { OTC::Cache.encode_cache_json(value) }
        end
    end

    def test_encoding_preserves_input_and_original_pointer_bytes
        document = { "unknown" => { "nested" => [nil, 1e-7, "e\u0301", { "z" => 2, "a" => 1 }] } }
        original = Marshal.dump(document)
        OTC::Cache.encode_cache_json(document)
        assert_equal original, Marshal.dump(document)
        cache = OTC::Cache.new(tmpdir)
        pointer = "{ \"z\": 1, \"a\": 2 }\n"
        etag = 'W/"exact-header"'
        cache.write_pointer("OTC_latest-f1.json", pointer, etag)
        assert_equal pointer, File.binread(File.join(cache.pointer_dir, "OTC_latest-f1.json"))
        assert_equal etag, File.binread(File.join(cache.pointer_dir, "OTC_latest-f1.json.etag"))
    end
end

class ChecksumTest < Minitest::Test
    include TestSupport
    OTC = OpenTideConstants
    D = "20991231.2".freeze

    def good_sha256
        File.read(fixture("good", "OTC_#{D}.sha256"))
    end

    # R46: a malformed .sha256 line is an error that names it, not a line
    # that is silently dropped (which then reads "not listed").
    def test_malformed_sha256_line_is_reported
        dir = tmpdir
        FileUtils.cp(fixture("good", "OTC_#{D}.json"), dir)
        lines = good_sha256.lines
        json_line = lines.index { |l| l.end_with?("  OTC_#{D}.json\n") }
        refute_nil json_line, "the fixture lists OTC_#{D}.json"
        # Only the OTC_D.json line is rewritten (not the .meta.json line).
        bad = lines.each_with_index.map { |l, i| i == json_line ? "SHA256 (OTC_#{D}.json) = #{l.split.first}\n" : l }
        assert_equal 1, bad.zip(lines).count { |a, b| a != b }
        File.write(File.join(dir, "OTC_#{D}.sha256"), bad.join)
        err = assert_raises(OTC::InvalidReleaseError) { OTC.new(file: File.join(dir, "OTC_#{D}.json")) }
        assert_includes err.message, "line #{json_line + 1} "
        assert_includes err.message, "SHA256 ("
        File.write(File.join(dir, "OTC_#{D}.sha256"), good_sha256.sub(/\A\h{64}/, "abc"))
        err = assert_raises(OTC::InvalidReleaseError) { OTC.new(file: File.join(dir, "OTC_#{D}.json")) }
        assert_includes err.message, "line 1 "
        assert_includes err.message, "\"abc  OTC_"
    end

    # R38: the .sha256 file is checked against the pointer before it is
    # parsed, so a substituted file is checksum_mismatch, not a parse error.
    def test_sha256_file_is_checked_against_the_pointer_first
        srv = serve(File.join(FIXTURES, "good"), "OTC_#{D}.sha256" => [200, {}, "#{'0' * 64}  x\n"])
        err = assert_raises(OTC::ChecksumError) { OTC.new(base_url: srv.url("/"), cache_dir: tmpdir, on_network_error: :raise) }
        assert_includes err.message, "does not match the pointer"
    end

    # R25: a file that OTC_{D}.sha256 does not list is a checksum error
    # before it is downloaded.
    def test_unlisted_file_is_not_downloaded
        no_jsonl = good_sha256.lines.reject { |l| l.include?(".jsonl") }.join
        srv = serve(File.join(FIXTURES, "good"), "OTC_#{D}.sha256" => [200, {}, no_jsonl])
        err = assert_raises(OTC::ChecksumError) do
            OTC.new(release: D, base_url: srv.url("/"), cache_dir: tmpdir, mode: :stream)
        end
        # not the "does not match the pointer" error of R38, which is a ChecksumError too
        assert_includes err.message, "OTC_#{D}.jsonl is not listed in OTC_#{D}.sha256"
        refute_includes srv.requests, "/OTC_#{D}.jsonl"
    end

    # R40: download() with a corrupt cached copy deletes it and downloads the
    # file again, instead of failing.
    def test_download_heals_a_corrupt_cached_file
        srv = serve
        cache = tmpdir
        OTC.new(release: D, base_url: srv.url("/"), cache_dir: cache, mode: :stream).close
        cached = File.join(cache, "v1", "releases", D, "OTC_#{D}.jsonl")
        original = File.binread(cached)
        bytes = original.dup
        bytes[100] = bytes[100] == "x" ? "y" : "x"
        File.binwrite(cached, bytes)
        assert_equal original.bytesize, File.size(cached)
        refute_equal original, File.binread(cached)
        before_open = srv.requests.size
        c = OTC.new(release: D, base_url: srv.url("/"), cache_dir: cache, mode: :stream)
        assert_equal original, File.binread(cached), "online open authenticates the source and heals the corrupt cached copy"
        assert_includes srv.requests[before_open..], "/OTC_#{D}.jsonl"
        # Corrupt it again after open to exercise download's own recovery.
        File.binwrite(cached, bytes)
        assert_equal bytes, File.binread(cached), "download starts with a corrupt cached copy"
        before = srv.requests.size
        to = tmpdir
        paths = c.download(D, to: to)
        assert_includes paths, File.join(to, "OTC_#{D}.jsonl")
        assert_equal File.binread(fixture("good", "OTC_#{D}.jsonl")), File.binread(File.join(to, "OTC_#{D}.jsonl"))
        # The corrupt copy is deleted from the cache, and the file is downloaded again.
        # On Windows the open client keeps its handle on the cached copy, so it cannot be removed there.
        refute File.exist?(cached), "the corrupt cached copy is still there" unless Gem.win_platform?
        assert_includes srv.requests[before..], "/OTC_#{D}.jsonl"
        # On every platform: the corrupt copy is never served offline, and once the client is closed the next
        # online open replaces it with the right bytes.
        c.close
        c = nil
        assert_raises(OTC::Error) { OTC.new(release: D, offline: true, cache_dir: cache, mode: :stream, verify_on_open: false).close }
        c = OTC.new(release: D, base_url: srv.url("/"), cache_dir: cache, mode: :stream)
        assert_equal original, File.binread(cached), "the corrupt cached copy was not replaced once the client was closed"
    ensure
        c&.close
    end

    # R2-084: a cached file that fails its check and cannot be deleted (a
    # read-only directory) is still checksum_mismatch; the failed delete is
    # logged, not raised in its place (spec §5.2 step 6, CR2 DR16).
    def test_undeletable_corrupt_file_keeps_the_checksum_error
        posix_only # a read-only directory does not stop a delete as root or on Windows
        srv = serve
        cache = tmpdir
        OTC.new(release: D, base_url: srv.url("/"), cache_dir: cache, mode: :stream).close
        dir = File.join(cache, "v1", "releases", D)
        cached = File.join(dir, "OTC_#{D}.jsonl")
        bytes = File.binread(cached)
        bytes[100] = bytes[100] == "x" ? "y" : "x"
        File.binwrite(cached, bytes)
        File.chmod(0o555, dir)
        log = StringIO.new
        assert_raises(OTC::ChecksumError) do
            OTC.new(release: D, cache_dir: cache, mode: :stream, offline: true, verify_on_open: true, logger: Logger.new(log))
        end
        assert_includes log.string, "cannot remove"
    ensure
        File.chmod(0o755, dir) if dir && File.directory?(dir)
    end

    # R86: verify on a file_unverified client is checksum_mismatch (CR D20).
    def test_verify_without_sha256_is_checksum_mismatch
        dir = tmpdir
        FileUtils.cp(fixture("good", "OTC_#{D}.json"), dir)
        c = OTC.new(file: File.join(dir, "OTC_#{D}.json"))
        assert_equal :file_unverified, c.loaded_from
        err = assert_raises(OTC::ChecksumError) { c.verify }
        assert_includes err.message, "no OTC_#{D}.sha256 next to the file"
    ensure
        c&.close
    end
end

# R79: the bytes that are hashed are the bytes that are loaded. A file
# swapped for another one after the hash must not be used as verified.
class ChecksumSwapTest < Minitest::Test
    include TestSupport
    OTC = OpenTideConstants
    D = "20991231.2".freeze

    # Runs the block with a hook on SHA-256: the moment a hash of path's
    # bytes is complete (any Digest::SHA256 hexdigest, of a String or of an
    # IO), path is replaced by a file with the other bytes (a rename, as
    # another process would replace it). Returns how many times the swap ran,
    # or :blocked when Windows refused to rename over the open file (the
    # library would wrap that Errno::EACCES in a FileError, so it is caught
    # here, where the rename runs).
    def with_swap_after_hash(path, other)
        target = Digest::SHA256.hexdigest(File.binread(path))
        swaps = 0
        blocked = false
        swap = lambda do |hex|
            return unless hex == target && swaps.zero?
            swaps += 1
            tmp = "#{path}.swap"
            File.binwrite(tmp, other)
            begin
                File.rename(tmp, path)
            rescue Errno::EACCES
                # Windows does not rename over a file that is open (the .jsonl
                # is hashed through an open handle).
                raise unless Gem.win_platform?
                blocked = true
                File.delete(tmp)
            end
        end
        hook = Module.new do
            define_method(:hexdigest) do |*args|
                result = super(*args)
                swap.call(result)
                result
            end
        end
        Digest::SHA256.singleton_class.prepend(hook) # Digest::SHA256.hexdigest(bytes)
        Digest::SHA256.prepend(hook)                 # Digest::SHA256.new / .file(p), then #hexdigest
        yield
        blocked ? :blocked : swaps
    ensure
        # A prepended module cannot be taken out again; emptying it undoes the
        # hook. (hook is nil when the code before it raised; keep that error.)
        hook&.send(:remove_method, :hexdigest)
    end

    # What a load gives: the datestamp and every station, as read.
    def content(c)
        [c.release.datestamp, c.stations.map(&:raw)]
    end

    def test_a_file_swapped_after_its_hash_is_not_loaded
        %w[json json.gz jsonl].each do |ext|
            original = fixture("good", "OTC_#{D}.#{ext}")
            # Same release, other bytes: the older release's file under this name.
            other = fixture("good", "OTC_20991231.#{ext}")
            want = OTC.new(file: original).then { |r| content(r).tap { r.close } }
            dir = tmpdir
            %W[OTC_#{D}.#{ext} OTC_#{D}.sha256 OTC_#{D}.meta.json].each { |n| FileUtils.cp(fixture("good", n), dir) }
            path = File.join(dir, "OTC_#{D}.#{ext}")
            c = nil
            swaps = with_swap_after_hash(path, File.binread(other)) do
                c = OTC.new(file: path)
            rescue OTC::ChecksumError
                c = nil # the swapped bytes were refused: also correct
            end
            if swaps == :blocked
                c&.close
                skip "#{ext}: cannot replace an open file on Windows"
            end
            assert_equal 1, swaps, "#{ext}: the file was not swapped after its hash (the hook did not fire)"
            refute_equal File.binread(original), File.binread(path), "#{ext}: the file on disk is not the swapped one"
            next unless c

            got = content(c)
            c.close
            # Positive control: the swapped bytes load to other content, so a load of them is seen.
            refute_equal want[1], OTC.new(file: other).then { |r| content(r)[1].tap { r.close } }
            assert_equal want, got, "#{ext}: loaded the bytes that replaced the hashed file"
        end
    end

    # R3-227: a downloaded file that fails its check says which check
    # failed: its size against the pointer's, or its SHA-256 against the
    # .sha256 row (and a missing row says so, not "mismatch").
    def test_download_check_says_which_check_failed
        jsonl = "OTC_#{D}.jsonl"
        good = File.binread(fixture("good", jsonl))
        want = Digest::SHA256.hexdigest(good)
        ptr = JSON.parse(File.read(fixture("good", "OTC_latest-f1.json")))
        ptr["files"].find { |f| f["name"] == jsonl }["size"] = good.bytesize + 1
        srv = serve(File.join(FIXTURES, "good"), "OTC_latest-f1.json" => [200, {}, JSON.generate(ptr)])
        err = assert_raises(OTC::ChecksumError) { OTC.new(base_url: srv.url("/"), cache_dir: tmpdir, mode: :stream) }
        assert_includes err.message, "#{jsonl}: size #{good.bytesize}, expected #{good.bytesize + 1}"
        refute_includes err.message, "SHA-256"

        bad = good.dup
        bad[-2] = bad[-2] == "}" ? "]" : "}"
        srv = serve(File.join(FIXTURES, "good"), jsonl => [200, {}, bad])
        err = assert_raises(OTC::ChecksumError) { OTC.new(base_url: srv.url("/"), cache_dir: tmpdir, mode: :stream) }
        assert_includes err.message, "#{jsonl}: SHA-256 #{Digest::SHA256.hexdigest(bad)}, expected #{want}"
        refute_includes err.message, "size"

        srv = serve
        c = OTC.new(file: fixture("good", jsonl))
        dir = tmpdir
        err = assert_raises(OTC::ChecksumError) do
            OTC::Downloader.fetch_checked(c, srv.url("/#{jsonl}"), dir, File.join(dir, jsonl), jsonl, nil, nil)
        end
        assert_includes err.message, "#{jsonl}: no expected SHA-256"
        refute_includes err.message, "mismatch"
    ensure
        c&.close
    end
end
