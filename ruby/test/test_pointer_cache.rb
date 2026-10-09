# The cached pointer and index, their ETags, and what counts for the
# use_cache fallback (spec §5.2 steps 2 and 5, §5.4, CR D8).
require_relative "support"

class PointerCacheTest < Minitest::Test
    include TestSupport
    OTC = OpenTideConstants
    HTML = [200, { "ETag" => "\"portal\"", "Content-Type" => "text/html" }, "<html>captive portal</html>"].freeze

    def pointer_path(cache)
        File.join(cache, "v1", "pointer", "OTC_latest-f1.json")
    end

    # R95: a 200 pointer whose body is not JSON is a network error and is not cached.
    def test_pointer_200_not_json_is_not_cached
        over = {}
        srv = serve(File.join(FIXTURES, "good"), over)
        cache = tmpdir
        c = OTC.new(base_url: srv.url("/"), cache_dir: cache)
        before = File.binread(pointer_path(cache))
        over["OTC_latest-f1.json"] = HTML
        err = assert_raises(OTC::NetworkError) { c.latest }
        assert_equal "network", err.code
        assert_equal before, File.binread(pointer_path(cache))
        refute_equal "\"portal\"", File.read("#{pointer_path(cache)}.etag").strip
    ensure
        c&.close
    end

    # R95/R27: with use_cache, an HTML pointer at open falls back to the cached release.
    def test_open_with_html_pointer_falls_back_to_the_cache
        over = {}
        srv = serve(File.join(FIXTURES, "good"), over)
        cache = tmpdir
        OTC.new(base_url: srv.url("/"), cache_dir: cache).close
        over["OTC_latest-f1.json"] = HTML
        c = OTC.new(base_url: srv.url("/"), cache_dir: cache)
        assert_equal [:cache_after_error, "20991231.2", "network"], [c.loaded_from, c.release.datestamp, c.last_error.code]
    ensure
        c&.close
    end

    # A cached pointer that is not JSON is not used: the next request asks
    # without its ETag, so a 304 cannot serve it again (C104 in Ruby).
    def test_corrupt_cached_pointer_is_refetched
        srv = serve
        cache = tmpdir
        OTC.new(base_url: srv.url("/"), cache_dir: cache).close
        File.binwrite(pointer_path(cache), "<html>")
        etag = File.read("#{pointer_path(cache)}.etag").strip
        srv304 = serve(File.join(FIXTURES, "good"), "OTC_latest-f1.json" => lambda { |_p, h|
            h["if-none-match"] == etag ? [304, { "ETag" => etag }, ""] : [200, { "ETag" => etag }, File.binread(fixture("good", "OTC_latest-f1.json"))]
        })
        c = OTC.new(base_url: srv304.url("/"), cache_dir: cache)
        assert_equal "20991231.2", c.latest.datestamp
        assert_equal File.binread(fixture("good", "OTC_latest-f1.json")), File.binread(pointer_path(cache))
    ensure
        c&.close
    end

    # R8: a 304 with no cached copy is asked again, and that answer's status
    # is handled like any other (a 404 goes on to OTC_latest.json).
    def test_304_without_cache_then_404_falls_through_to_the_generic_pointer
        hits = Hash.new(0)
        srv = serve(File.join(FIXTURES, "good"), "OTC_latest-f1.json" => lambda { |_p|
            hits[:f1] += 1
            hits[:f1] == 1 ? [304, {}, ""] : [404, {}, "no"]
        })
        c = OTC.new(base_url: srv.url("/"), cache_dir: tmpdir, on_network_error: :raise)
        assert_equal "20991231.2", c.release.datestamp
        assert_includes srv.requests, "/OTC_latest.json"
    ensure
        c&.close
    end

    # R28: a pointer cache that cannot be written is logged, not raised.
    def test_unwritable_pointer_cache_is_logged
        skip "needs POSIX permissions" if Gem.win_platform? || Process.uid.zero?
        srv = serve
        cache = tmpdir
        OTC.new(base_url: srv.url("/"), cache_dir: cache).close
        File.delete("#{pointer_path(cache)}.etag") # the next GET is a 200
        FileUtils.chmod(0o555, File.dirname(pointer_path(cache)))
        log = Log.new
        c = OTC.new(base_url: srv.url("/"), cache_dir: cache, logger: log)
        assert_equal "20991231.2", c.latest.datestamp
        assert(log.lines.any? { |lvl, m| lvl == :warn && m.include?("OTC_latest-f1.json") })
    ensure
        c&.close
    end

    # R96: a stale .etag that cannot be removed is an error, not a body paired
    # with an old ETag.
    def test_stale_etag_that_cannot_be_removed_is_a_cache_error
        cache = OTC::Cache.new(tmpdir)
        cache.write_pointer("OTC_index.json", "{}", "\"a\"")
        etag = File.join(cache.pointer_dir, "OTC_index.json.etag")
        File.delete(etag)
        Dir.mkdir(etag)
        File.write(File.join(etag, "x"), "x")
        assert_raises(OTC::CacheError) { cache.write_pointer("OTC_index.json", "{\"releases\":[]}", nil) }
    end

    # R96: the body and its ETag are written as a pair under pointer/.lock, so
    # concurrent writers never leave one writer's body with another's ETag.
    def test_concurrent_pointer_writes_keep_body_and_etag_paired
        cache = OTC::Cache.new(tmpdir)
        path = File.join(cache.pointer_dir, "OTC_index.json")
        mismatched = 0
        20.times do
            %w[a b c].map do |tag|
                Thread.new { cache.write_pointer("OTC_index.json", "{\"t\":\"#{tag}\"}", "\"#{tag}\"") }
            end.each(&:join)
            mismatched += 1 if JSON.parse(File.read(path))["t"] != File.read("#{path}.etag").delete('"')
        end
        assert_equal 0, mismatched
    end

    # R37: releases() falling back to the cached index does not set last_error
    # (it is the error behind loaded_from :cache_after_error).
    def test_releases_fallback_leaves_last_error_alone
        over = {}
        srv = serve(File.join(FIXTURES, "good"), over)
        c = OTC.new(base_url: srv.url("/"), cache_dir: tmpdir)
        c.releases
        over["OTC_index.json"] = [500, {}, "boom"]
        assert_equal 2, c.releases.size
        assert_equal :download, c.loaded_from
        assert_nil c.last_error
    ensure
        c&.close
    end
end
