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
        bad = good_sha256.lines.map { |l| l.include?(".json\n") || l.end_with?(".json") ? "SHA256 (OTC_#{D}.json) = #{l.split.first}\n" : l }.join
        File.write(File.join(dir, "OTC_#{D}.sha256"), bad)
        err = assert_raises(OTC::InvalidReleaseError) { OTC.new(file: File.join(dir, "OTC_#{D}.json")) }
        assert_includes err.message, "SHA256 ("
        File.write(File.join(dir, "OTC_#{D}.sha256"), good_sha256.sub(/\A\h{64}/, "abc"))
        assert_raises(OTC::InvalidReleaseError) { OTC.new(file: File.join(dir, "OTC_#{D}.json")) }
    end

    # R38: the .sha256 file is checked against the pointer before it is
    # parsed, so a substituted file is checksum_mismatch, not a parse error.
    def test_sha256_file_is_checked_against_the_pointer_first
        srv = serve(File.join(FIXTURES, "good"), "OTC_#{D}.sha256" => [200, {}, "SHA256 (x) = y\n"])
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
        to = tmpdir
        paths = c.download(D, to: to)
        assert_includes paths, File.join(to, "OTC_#{D}.jsonl")
        assert_equal File.binread(fixture("good", "OTC_#{D}.jsonl")), File.binread(File.join(to, "OTC_#{D}.jsonl"))
        refute_equal bytes, File.binread(cached) if File.file?(cached)
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

    # Swaps the file at path for other bytes right after it is hashed (the
    # window between the hash and the read).
    def with_swap_after_hash(path, other)
        hook = Module.new do
            define_method(:sha256_file) do |p|
                result = super(p)
                File.binwrite(p, other) if p == path
                result
            end
            define_method(:file) do |p|
                result = super(p)
                File.binwrite(p, other) if p == path
                result
            end
        end
        OTC::Release.singleton_class.prepend(hook)
        Digest::SHA256.singleton_class.prepend(hook)
        yield
    ensure
        # A prepended module cannot be taken out again; emptying it undoes the hook.
        hook.send(:remove_method, :sha256_file)
        hook.send(:remove_method, :file)
    end

    def test_a_file_swapped_after_its_hash_is_not_loaded
        %w[json json.gz jsonl].each do |ext|
            dir = tmpdir
            %W[OTC_20991231.2.#{ext} OTC_20991231.2.sha256 OTC_20991231.2.meta.json].each { |n| FileUtils.cp(fixture("good", n), dir) }
            path = File.join(dir, "OTC_20991231.2.#{ext}")
            # Same release, other bytes: the older release's file under this name.
            other = File.binread(fixture("good", "OTC_20991231.#{ext}"))
            c = nil
            with_swap_after_hash(path, other) do
                c = OTC.new(file: path)
            rescue OTC::ChecksumError, OTC::Error
                c = nil
            end
            assert(c.nil? || c.release.datestamp == "20991231.2", "#{ext}: loaded swapped bytes as #{c&.release&.datestamp}")
            c&.close
        end
    end
end
