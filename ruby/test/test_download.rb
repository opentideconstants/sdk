# download() into the caller's folder (spec §4.3.2): all of a release or nothing.
require_relative "support"

class DownloadTest < Minitest::Test
    include TestSupport
    OTC = OpenTideConstants
    D = "20991231.2".freeze

    def test_latest_acquisition_keeps_the_loaded_source_versions_in_both_modes
        src = tmpdir
        FileUtils.cp_r(Dir.glob(File.join(FIXTURES, "good", "*")), src)
        %W[OTC_#{D}.json OTC_#{D}.meta.json].each do |name|
            path = File.join(src, name)
            doc = JSON.parse(File.binread(path))
            doc["format_version"] = "1.7"
            doc["release"]["min_reader_version"] = "0.9"
            File.binwrite(path, JSON.generate(doc))
        end
        Zlib::GzipWriter.open(File.join(src, "OTC_#{D}.json.gz")) do |gz|
            gz.write(File.binread(File.join(src, "OTC_#{D}.json")))
        end
        sha_path = File.join(src, "OTC_#{D}.sha256")
        sums = File.readlines(sha_path).map do |line|
            name = line.split.last
            "#{Digest::SHA256.file(File.join(src, name)).hexdigest}  #{name}\n"
        end
        File.binwrite(sha_path, sums.join)
        pointer_path = File.join(src, "OTC_latest-f1.json")
        pointer = JSON.parse(File.binread(pointer_path))
        pointer["files"].each do |row|
            path = File.join(src, row["name"])
            row["sha256"] = Digest::SHA256.file(path).hexdigest
            row["size"] = File.size(path)
        end
        File.binwrite(pointer_path, JSON.generate(pointer))
        srv = serve(src)
        c = nil
        %i[eager stream].each do |mode|
            cache = tmpdir
            c = OTC.new(base_url: srv.url("/"), cache_dir: cache, mode: mode)
            ver = JSON.parse(File.binread(File.join(cache, "v1", "releases", D, ".verified")))
            assert_equal "1.7", c.release.format_version
            assert_equal "1.7", ver["format_version"]
            assert_equal "0.9", ver["min_reader_version"]
            c.close
        end
    ensure
        c&.close
    end

    # R10: offline with a cache that holds only some of the formats: nothing is written.
    def test_offline_partial_cache_writes_nothing
        srv = serve
        cache = tmpdir
        OTC.new(release: D, base_url: srv.url("/"), cache_dir: cache, mode: :eager).close
        # The premise: the cache holds the .json (and .sha256), not the .jsonl.
        rel = File.join(cache, "v1", "releases", D)
        assert File.file?(File.join(rel, "OTC_#{D}.json"))
        assert File.file?(File.join(rel, "OTC_#{D}.sha256"))
        refute File.exist?(File.join(rel, "OTC_#{D}.jsonl"))
        c = OTC.new(release: D, cache_dir: cache, offline: true)
        to = File.join(tmpdir, "bundle")
        err = assert_raises(OTC::OfflineError) { c.download(D, to: to, formats: %i[json jsonl]) }
        # It failed on the file the cache does not have, not on the release as a whole.
        assert_includes err.message, "OTC_#{D}.jsonl is not cached"
        assert(!File.exist?(to) || Dir.empty?(to), "files were written: #{File.exist?(to) && Dir.children(to)}")
    ensure
        c&.close
    end

    # R10: a network error on a later file: nothing is written.
    def test_network_error_on_a_later_file_writes_nothing
        over = {}
        srv = serve(File.join(FIXTURES, "good"), over)
        c = OTC.new(release: D, base_url: srv.url("/"), cache_dir: tmpdir, mode: :eager)
        over["OTC_#{D}.meta.json"] = [500, { "Retry-After" => "0" }, "busy"]
        to = File.join(tmpdir, "bundle")
        before = srv.requests.size
        assert_raises(OTC::NetworkError) { c.download(D, to: to, formats: %i[json jsonl]) }
        # The .jsonl was fetched (and staged) before the .meta.json failed.
        asked = srv.requests[before..]
        assert_equal "/OTC_#{D}.jsonl", asked.first
        assert_operator asked.index("/OTC_#{D}.jsonl"), :<, asked.index("/OTC_#{D}.meta.json")
        assert(!File.exist?(to) || Dir.empty?(to), "files were written: #{File.exist?(to) && Dir.children(to)}")
    ensure
        c&.close
    end

    # R9: the paths come in a fixed order: the data files as the formats list
    # them, OTC_{D}.meta.json (for jsonl), then OTC_{D}.sha256.
    def test_paths_written_in_order
        srv = serve
        c = OTC.new(release: D, base_url: srv.url("/"), cache_dir: tmpdir, mode: :stream)
        to = tmpdir
        paths = c.download(D, to: to, formats: %i[json jsonl])
        assert_equal %W[OTC_#{D}.json OTC_#{D}.jsonl OTC_#{D}.meta.json OTC_#{D}.sha256], paths.map { |p| File.basename(p) }
        # The folder holds exactly these files (no temporary or other files).
        assert_equal paths.map { |p| File.basename(p) }.sort, Dir.children(to).sort
    ensure
        c&.close
    end

    # ---- CR D22: download of latest honours on_network_error

    def captive_portal(over)
        # a 200 pointer that is not JSON is a network error at once (spec §5.2 step 5), with no retry
        %w[OTC_latest-f1.json OTC_latest.json].each { |n| over[n] = [200, { "Content-Type" => "text/html" }, "<html>portal</html>"] }
    end

    def names(d = D)
        %W[OTC_#{d}.jsonl OTC_#{d}.meta.json OTC_#{d}.sha256]
    end

    # Only the older release is cached, and the server's latest (and its
    # index) name the newer one: the files written can only come from the
    # newest cached release, and the fallback is logged.
    def test_latest_with_a_network_error_writes_the_newest_cached_release
        older = "20991231"
        over = {}
        srv = serve(File.join(FIXTURES, "good"), over)
        log = Log.new
        c = OTC.new(release: older, base_url: srv.url("/"), cache_dir: tmpdir, logger: log)
        assert_equal [older], c.cached_releases, "the premise: only the older release is cached"
        captive_portal(over)
        to = File.join(tmpdir, "bundle")
        paths = c.download(to: to)
        assert_equal names(older), paths.map { |p| File.basename(p) }.sort
        names(older).each { |n| assert_equal File.binread(fixture("good", n)), File.binread(File.join(to, n)) }
        warn_line = log.lines.find { |lvl, m| lvl == :warn && m.include?("writing the cached release #{older}") }
        refute_nil warn_line, "the fallback to the cache was not logged: #{log.lines.inspect}"
        assert_includes warn_line[1], "OTC_latest", "the warning does not name the network failure"
    ensure
        c&.close
    end

    def test_latest_with_a_network_error_and_raise_raises
        over = {}
        srv = serve(File.join(FIXTURES, "good"), over)
        c = OTC.new(base_url: srv.url("/"), cache_dir: tmpdir, on_network_error: :raise)
        captive_portal(over)
        to = File.join(tmpdir, "bundle")
        assert_raises(OTC::NetworkError) { c.download(to: to) }
        refute(File.exist?(to) && !Dir.empty?(to))
    ensure
        c&.close
    end

    def test_latest_with_a_network_error_and_nothing_cached_raises
        over = {}
        srv = serve(File.join(FIXTURES, "good"), over)
        c = OTC.new(file: fixture("good", "OTC_#{D}.jsonl"), base_url: srv.url("/"), cache_dir: tmpdir)
        captive_portal(over)
        to = File.join(tmpdir, "bundle")
        err = assert_raises(OTC::NetworkError) { c.download(to: to) }
        assert_includes err.message, "OTC_latest", "not the pointer failure"
        assert(!File.exist?(to) || Dir.empty?(to), "files were written: #{File.exist?(to) && Dir.children(to)}")
    ensure
        c&.close
    end

    # ---- CR2 DR17: the renames into to are all or nothing

    # Downloads D into a new folder, then changes the .jsonl and the
    # .meta.json there. Returns [client, folder, {name => changed bytes}].
    def changed_bundle(logger: nil)
        srv = serve
        c = OTC.new(release: D, base_url: srv.url("/"), cache_dir: tmpdir, logger: logger)
        to = tmpdir
        c.download(D, to: to)
        before = names.first(2).to_h do |n|
            File.binwrite(File.join(to, n), "changed #{n}")
            [n, File.binread(File.join(to, n))]
        end
        [c, to, before]
    end

    # Runs the block with File.rename failing when failing.call(source
    # basename, destination basename) is true.
    def failing_renames(failing)
        sc = File.singleton_class
        sc.send(:alias_method, :otc_test_real_rename, :rename)
        sc.send(:define_method, :rename) do |a, b|
            raise Errno::EACCES, "injected #{b}" if failing.call(File.basename(a.to_s), File.basename(b.to_s))
            otc_test_real_rename(a, b)
        end
        yield
    ensure
        sc.send(:alias_method, :rename, :otc_test_real_rename)
        sc.send(:remove_method, :otc_test_real_rename)
    end

    def new_file_into(src, dest, name)
        dest == name && src.start_with?(".tmp-") && !src.start_with?(".tmp-bak-")
    end

    def test_a_rename_that_fails_restores_every_original
        c, to, before = changed_bundle
        jsonl, meta = "OTC_#{D}.jsonl", "OTC_#{D}.meta.json"
        placed = []
        failing = lambda do |s, d|
            placed << d if new_file_into(s, d, jsonl)
            new_file_into(s, d, meta)
        end
        e = failing_renames(failing) do
            assert_raises(OTC::FileError) { c.download(D, to: to, overwrite: true) }
        end
        # The premise: the .jsonl was renamed into place before the .meta.json
        # rename failed, so a placed file is what gets restored.
        assert_equal [jsonl], placed, "the .jsonl was not placed before the .meta.json failed"
        assert_equal File.join(to, meta), e.path
        before.each { |n, bytes| assert_equal bytes, File.binread(File.join(to, n)), "#{n} was not restored" }
        assert_equal names, Dir.children(to).sort
    ensure
        c&.close
    end

    # A new file renamed into a slot that had no file before is removed again
    # when a later rename fails.
    def test_a_rename_that_fails_removes_a_new_file_from_an_empty_slot
        c, to, = changed_bundle
        jsonl, meta = "OTC_#{D}.jsonl", "OTC_#{D}.meta.json"
        File.delete(File.join(to, jsonl)) # no original in the .jsonl slot
        placed = []
        failing = lambda do |s, d|
            placed << d if new_file_into(s, d, jsonl)
            new_file_into(s, d, meta)
        end
        failing_renames(failing) do
            assert_raises(OTC::FileError) { c.download(D, to: to, overwrite: true) }
        end
        assert_equal [jsonl], placed, "the .jsonl was not placed before the .meta.json failed"
        refute File.exist?(File.join(to, jsonl)), "the new .jsonl was left in the slot that was empty"
        assert_equal names.reject { |n| n == jsonl }, Dir.children(to).sort
    ensure
        c&.close
    end

    def test_a_restore_that_fails_too_lists_the_paths_that_changed
        log = Log.new
        c, to, before = changed_bundle(logger: log)
        jsonl, meta = "OTC_#{D}.jsonl", "OTC_#{D}.meta.json"
        failing = ->(s, d) { new_file_into(s, d, meta) || (d == jsonl && s.start_with?(".tmp-bak-")) }
        e = failing_renames(failing) do
            assert_raises(OTC::FileError) { c.download(D, to: to, overwrite: true) }
        end
        assert_includes e.message, File.join(to, jsonl)
        assert_includes e.message, ".tmp-bak-", "the message does not say where the original is"
        assert_equal before[meta], File.binread(File.join(to, meta))
        # The caller's original .jsonl is not lost: it is in the one .tmp-bak- file next to it.
        baks = Dir.children(to).select { |n| n.start_with?(".tmp-bak-") }
        assert_equal 1, baks.size, "expected one .tmp-bak- file, got #{Dir.children(to).sort}"
        assert_equal before[jsonl], File.binread(File.join(to, baks.first)), "the original .jsonl is not in #{baks.first}"
        assert(log.lines.any? { |lvl, m| lvl == :warn && m.include?("cannot restore #{File.join(to, jsonl)}") },
               "the failed restore was not logged: #{log.lines.inspect}")
    ensure
        c&.close
    end

    # R3-228: the download doc comment says what download writes (spec
    # §4.3.2): OTC_{D}.meta.json always, whatever the formats, not only for jsonl.
    def test_download_doc_comment_says_meta_json_is_always_written
        src = File.read(File.join(ROOT, "ruby", "lib", "opentideconstants", "client.rb"))
        doc = src[/((?:^ *#.*\n)+) *def download\(/, 1]
        refute_nil doc, "no doc comment above def download"
        text = doc.gsub(/^ *# ?/, "").tr("\n", " ")
        refute_match(/meta\.json for jsonl/, text)
        assert_match(/always OTC_\{D\}\.meta\.json and OTC_\{D\}\.sha256/, text)
        # Positive control: what the comment says is what download writes, for a format with no .jsonl.
        srv = serve
        c = OTC.new(release: D, base_url: srv.url("/"), cache_dir: tmpdir)
        names = c.download(D, to: tmpdir, formats: [:json]).map { |p| File.basename(p) }
        assert_equal %W[OTC_#{D}.json OTC_#{D}.meta.json OTC_#{D}.sha256], names
    ensure
        c&.close
    end
end
