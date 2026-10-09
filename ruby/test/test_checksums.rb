# Checksum agreement, verify and corrupt-cache recovery (spec §4.3, §4.8, §5.2 step 4, CR D20).
require_relative "support"

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
        assert_raises(OTC::ChecksumError) do
            OTC.new(release: D, base_url: srv.url("/"), cache_dir: tmpdir, mode: :stream)
        end
        refute_includes srv.requests, "/OTC_#{D}.jsonl"
    end

    # R40: download() with a corrupt cached copy deletes it and downloads the
    # file again, instead of failing.
    def test_download_heals_a_corrupt_cached_file
        srv = serve
        cache = tmpdir
        OTC.new(release: D, base_url: srv.url("/"), cache_dir: cache, mode: :stream).close
        cached = File.join(cache, "v1", "releases", D, "OTC_#{D}.jsonl")
        bytes = File.binread(cached)
        bytes[100] = bytes[100] == "x" ? "y" : "x"
        File.binwrite(cached, bytes)
        c = OTC.new(release: D, base_url: srv.url("/"), cache_dir: cache, mode: :stream)
        assert_equal bytes, File.binread(cached), "the open left the corrupt cached copy (the precondition)"
        before = srv.requests.size
        to = tmpdir
        paths = c.download(D, to: to)
        assert_includes paths, File.join(to, "OTC_#{D}.jsonl")
        assert_equal File.binread(fixture("good", "OTC_#{D}.jsonl")), File.binread(File.join(to, "OTC_#{D}.jsonl"))
        # The corrupt copy is deleted from the cache, and the file is downloaded again.
        refute File.exist?(cached), "the corrupt cached copy is still there"
        assert_includes srv.requests[before..], "/OTC_#{D}.jsonl"
    ensure
        c&.close
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
    # another process would replace it). Returns how many times the swap ran.
    def with_swap_after_hash(path, other)
        target = Digest::SHA256.hexdigest(File.binread(path))
        swaps = 0
        swap = lambda do |hex|
            return unless hex == target && swaps.zero?
            swaps += 1
            tmp = "#{path}.swap"
            File.binwrite(tmp, other)
            File.rename(tmp, path)
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
        swaps
    ensure
        # A prepended module cannot be taken out again; emptying it undoes the hook.
        hook.send(:remove_method, :hexdigest)
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
            assert_equal 1, swaps, "#{ext}: the file was not swapped after its hash (the hook did not fire)"
            refute_equal File.binread(original), File.binread(path), "#{ext}: the file on disk is not the swapped one"
            next unless c

            got = content(c)
            c.close
            # Positive control: the swapped bytes load to other content, so a load of them is seen.
            refute_equal want[1], OTC.new(file: other).then { |r| content(r)[1].tap { r.close } }
            assert_equal want, got, "#{ext}: loaded the bytes that replaced the hashed file"
        rescue Errno::EACCES
            # Windows does not rename over a file that is open (the .jsonl is
            # hashed through an open handle).
            raise unless Gem.win_platform?
            skip "#{ext}: cannot replace an open file on Windows"
        end
    end
end
