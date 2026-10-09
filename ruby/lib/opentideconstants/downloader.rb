require "fileutils"
require "digest"
require "zlib"
require "securerandom"

class OpenTideConstants
    # Fetching and checking release files (spec §5.2 step 4) and
    # OpenTideConstants#download (spec §4.3.2). Internal.
    class Downloader
        # GETs OTC_{D}.sha256 and checks it against the pointer entry, if any.
        # Returns [{name => sha256}, bytes].
        def self.fetch_sha256(client, d, entry, pointer_url)
            name = "OTC_#{d}.sha256"
            pf = entry && Array(entry["files"]).find { |f| f["name"] == name }
            url = pf && pf["url"] ? client.send(:resolve, pointer_url, pf["url"]) : client.send(:base_url) + name
            res = client.send(:http).get(url)
            raise ReleaseNotFoundError, "release #{d} not found (#{url}: HTTP 404)" if res.status == 404
            raise NetworkError.new("#{url}: HTTP #{res.status}", url: url, status: res.status) unless res.status == 200
            bytes = res.body
            # The file itself is checked against the pointer before it is parsed.
            if pf && pf["sha256"] && pf["sha256"].downcase != res.sha256
                raise ChecksumError.new("#{name} does not match the pointer", file: name, expected: pf["sha256"], actual: res.sha256)
            end
            rows = Reader.parse_sha256(bytes.dup.force_encoding(Encoding::UTF_8), name)
            check_agreement(entry, name, rows) if entry
            [rows, bytes]
        end

        # The pointer (or index) entry and OTC_{D}.sha256 must give the same
        # SHA-256 for every file (compared without regard to case), and the
        # same files (spec §5.2 step 4.1).
        def self.check_agreement(entry, sha_name, rows)
            listed = Array(entry["files"]).reject { |f| f["name"] == sha_name }
            listed.each do |f|
                next if f["sha256"].nil?
                got = rows[f["name"]]
                next if got == f["sha256"].downcase
                raise ChecksumError.new("the pointer and #{sha_name} disagree on #{f['name']}", file: f["name"],
                                        expected: f["sha256"].downcase, actual: got)
            end
            return if listed.none? { |f| f["sha256"] }
            extra = rows.keys - listed.map { |f| f["name"] }
            return if extra.empty?
            raise ChecksumError.new("#{sha_name} lists #{extra.first}, which the pointer does not", file: extra.first,
                                    expected: nil, actual: rows[extra.first])
        end

        # Downloads url to a temporary file in dir and checks its size and
        # SHA-256; then renames it to final (or leaves it at keep_tmp).
        # Returns the size. A bad file is deleted.
        # error_class: CacheError for the cache, FileError for the caller's
        # folder (spec §4.8): what a local write failure is.
        def self.fetch_checked(client, url, dir, final, name, expected_sha, expected_size, keep_tmp: nil,
                               error_class: CacheError)
            tmp = keep_tmp || Cache.tmp_path(dir)
            begin
                res = client.send(:http).get_to_file(url, tmp)
                if res.status == 404
                    # The release exists (its .sha256 lists the file): a server inconsistency (CR D32).
                    raise NetworkError.new("#{url}: HTTP 404 for a file that OTC_#{name[/\AOTC_([^.]+(?:\.[0-9]+)?)\./, 1]}.sha256 " \
                                           "lists; it is missing on the server", url: url, status: 404)
                elsif res.status != 200
                    raise NetworkError.new("#{url}: HTTP #{res.status}", url: url, status: res.status)
                end
                if expected_sha.nil? || res.sha256 != expected_sha || (expected_size && res.size != expected_size)
                    raise ChecksumError.new("#{name}: SHA-256 or size mismatch (#{res.size} bytes)",
                                            file: final || File.join(dir, name), expected: expected_sha, actual: res.sha256)
                end
                File.rename(tmp, final) if final
                res.size
            rescue Exception # rubocop:disable Lint/RescueException
                FileUtils.rm_f(tmp)
                raise
            end
        rescue SystemCallError, HTTP::SinkError => e
            raise local_error(error_class, "cannot write #{final || tmp}: #{e.message}", final || tmp)
        end

        def self.local_error(error_class, msg, path)
            error_class == FileError ? FileError.new(msg, path: path) : error_class.new(msg)
        end

        # Decompresses gz into a temporary file in dir, checks the SHA-256 of
        # the result and renames it to final. Returns its size.
        def self.gunzip_checked(gz, dir, final, name, expected_sha, error_class: CacheError)
            tmp = Cache.tmp_path(dir)
            digest = Digest::SHA256.new
            size = 0
            begin
                File.open(tmp, "wb") do |out|
                    File.open(gz, "rb") do |zin|
                        # zcat reads every gzip member, not only the first.
                        Zlib::GzipReader.zcat(zin) do |chunk|
                            out.write(chunk)
                            digest << chunk
                            size += chunk.bytesize
                        end
                    end
                    out.flush
                    out.fsync
                end
                actual = digest.hexdigest
                if expected_sha.nil? || actual != expected_sha
                    raise ChecksumError.new("#{name}: SHA-256 mismatch after decompression", file: final,
                                            expected: expected_sha, actual: actual)
                end
                File.rename(tmp, final)
                size
            rescue Zlib::Error => e
                FileUtils.rm_f(tmp)
                raise ChecksumError.new("#{name}: bad gzip data (#{e.message})", file: gz, expected: expected_sha, actual: nil)
            rescue SystemCallError, IOError => e
                FileUtils.rm_f(tmp)
                raise local_error(error_class, "cannot decompress #{gz} into #{final}: #{e.message}", final)
            rescue Exception # rubocop:disable Lint/RescueException
                FileUtils.rm_f(tmp)
                raise
            end
        end

        def initialize(client, release, to, formats, overwrite)
            @client = client
            @release = release
            @to = to
            @formats = formats
            @overwrite = overwrite
        end

        def run
            d, entry, pointer_url = resolve_release
            cache = @client.send(:cache)
            ver = cache.verified(d)
            rows, sha_bytes = sha_rows(d, ver, entry, pointer_url)
            names = []
            names << "OTC_#{d}.json" if @formats.include?("json")
            names << "OTC_#{d}.json.gz" if @formats.include?("json.gz")
            names += ["OTC_#{d}.jsonl", "OTC_#{d}.meta.json"] if @formats.include?("jsonl")
            sha_name = "OTC_#{d}.sha256"
            sha_digest = Digest::SHA256.hexdigest(sha_bytes)
            names.each do |n|
                # A format that the release does not publish (spec §4.8 release_not_found).
                raise ReleaseNotFoundError, "release #{d} does not publish #{n} (#{sha_name} does not list it)" unless rows[n]
            end

            # Check every existing file before writing any file.
            begin
                FileUtils.mkdir_p(@to)
            rescue SystemCallError => e
                raise FileError.new("cannot create #{@to}: #{e.message}", path: @to)
            end
            todo = []
            (names + [sha_name]).each do |n|
                path = File.join(@to, n)
                want = n == sha_name ? sha_digest : rows[n]
                if File.exist?(path)
                    have = Release.sha256_file(path)
                    next if have == want
                    raise FileExistsError.new("#{path} exists with other content", path: path) unless @overwrite
                end
                todo << n
            end

            pointer_files = entry ? Array(entry["files"]).to_h { |f| [f["name"], f] } : {}
            # Every file is made and checked as a temporary file in to first;
            # only when all of them are there are they renamed into place, all
            # or nothing (CR2 DR17), so a failure (offline, a network error, a
            # bad checksum, a failed rename) leaves to as it was.
            staged = [] # [temporary file, final path], in the order of todo
            begin
                todo.each do |n|
                    tmp = Cache.tmp_path(@to)
                    staged << [tmp, File.join(@to, n)]
                    fetch = lambda do
                        raise OfflineError, "offline and #{n} is not cached" if @client.send(:offline)
                        pf = pointer_files[n]
                        url = pf && pf["url"] ? @client.send(:resolve, pointer_url, pf["url"]) : @client.send(:base_url) + n
                        Downloader.fetch_checked(@client, url, @to, tmp, n, rows[n], pf && pf["size"], error_class: FileError)
                    end
                    if n == sha_name
                        write_bytes(tmp, sha_bytes)
                    elsif ver && cache.file_ok?(d, n, ver) && cached_sha_ok?(cache, d, n, rows[n])
                        from_cache(cache, File.join(cache.release_dir(d), n), fetch) { |src| copy_checked(src, tmp, n, rows[n]) }
                    elsif n.end_with?(".json") && !n.end_with?(".meta.json") && ver && cache.file_ok?(d, "#{n}.gz", ver)
                        from_cache(cache, File.join(cache.release_dir(d), "#{n}.gz"), fetch) { |src| gunzip_into(src, tmp, n, rows[n]) }
                    else
                        fetch.call
                    end
                end
                # OTC_{D}.sha256 is last in todo, so it goes into place last.
                rename_all_in(staged)
            ensure
                staged.each { |tmp, _| FileUtils.rm_f(tmp) }
            end
            staged.map(&:last)
        end

        private

        # Renames each [temporary file, final path] into place, all or nothing
        # (spec §4.3.2, CR2 DR17). Each original that a new file replaces is
        # first renamed aside to a .tmp-bak- name in to. If any rename fails,
        # every original is restored and the new files renamed in are removed,
        # so to is as it was: FileError. If a restore fails too, the error
        # lists the paths that changed.
        def rename_all_in(staged)
            aside = {} # final path => its original, renamed aside
            placed = [] # final paths a new file was renamed into
            final = nil
            begin
                staged.each do |_, f|
                    final = f
                    next unless File.symlink?(f) || (File.exist?(f) && !File.directory?(f))
                    bak = File.join(File.dirname(f), ".tmp-bak-#{Process.pid}-#{SecureRandom.hex(6)}")
                    File.rename(f, bak)
                    aside[f] = bak
                end
                staged.each do |tmp, f|
                    final = f
                    File.rename(tmp, f)
                    placed << f
                end
            rescue SystemCallError => e
                changed = restore(placed, aside)
                msg = "cannot rename into #{final}: #{e.message}"
                unless changed.empty?
                    msg += "; these paths changed and could not be restored: #{changed.join(', ')} " \
                           "(an original that is not back is in a .tmp-bak- file next to it)"
                end
                raise FileError.new(msg, path: final)
            end
            aside.each do |f, bak|
                File.delete(bak)
            rescue SystemCallError => e # the new file is in place; only the old copy is left over
                @client.send(:log, :warn, "download: cannot remove #{bak} (the replaced #{f}): #{e.message}")
            end
        end

        # Undoes rename_all_in after a failure. Returns the paths that could
        # not be restored.
        def restore(placed, aside)
            changed = []
            placed.reverse_each do |f|
                if aside.key?(f)
                    File.rename(aside.delete(f), f)
                else
                    File.delete(f)
                end
            rescue SystemCallError => e
                @client.send(:log, :warn, "download: cannot restore #{f}: #{e.message}")
                changed << f
            end
            aside.each do |f, bak|
                next if changed.include?(f)
                File.rename(bak, f)
            rescue SystemCallError => e
                @client.send(:log, :warn, "download: cannot restore #{f} from #{bak}: #{e.message}")
                changed << f
            end
            changed
        end

        def resolve_release
            if @release == :latest
                if @client.send(:offline)
                    d = @client.send(:newest_cached, usable: false)
                    raise OfflineError, "offline and no readable release is cached" unless d
                    return [d, nil, nil]
                end
                # The newest release this SDK reads, as for opening latest (spec §4.3.2, §5.2 step 2a).
                begin
                    entry, url = @client.send(:resolve_latest)
                rescue NetworkError => e
                    # on_network_error as when a client opens latest (spec
                    # §4.3.2, CR D22): use_cache writes the newest cached
                    # readable release; raise, or nothing usable cached,
                    # raises the network error.
                    d = @client.send(:on_network_error) == :use_cache ? @client.send(:newest_cached, usable: false) : nil
                    raise unless d
                    @client.send(:log, :warn, "#{e.message}; writing the cached release #{d}")
                    return [d, nil, nil]
                end
                d = entry["datestamp"]
                raise InvalidReleaseError, "bad datestamp #{d.inspect} in the pointer" unless d.is_a?(String) && d.match?(DATESTAMP_RE)
                return [d, entry, url]
            end
            [@release, nil, nil]
        end

        def sha_rows(d, ver, entry, pointer_url)
            path = File.join(@client.send(:cache).release_dir(d), "OTC_#{d}.sha256")
            if ver && File.file?(path)
                bytes = File.binread(path)
                return [Reader.parse_sha256(bytes.dup.force_encoding(Encoding::UTF_8), File.basename(path)), bytes]
            end
            raise OfflineError, "offline and release #{d} is not cached" if @client.send(:offline)
            Downloader.fetch_sha256(@client, d, entry, pointer_url)
        end

        # Copies a file from the cache with the block. A cached copy that fails
        # its check is deleted from the cache (spec §4.8 checksum_mismatch) and
        # the file is downloaded instead (fetch).
        def from_cache(cache, src, fetch)
            yield src
        rescue ChecksumError => e
            @client.send(:log, :warn, "#{e.message}; deleting the cached #{File.basename(src)} and downloading it again")
            cache.remove_file(src)
            fetch.call
        end

        def cached_sha_ok?(cache, d, n, sha)
            row = cache.verified(d)&.dig("files", n)
            row.is_a?(Hash) && row["sha256"] == sha
        end

        def write_bytes(path, bytes)
            tmp = Cache.tmp_path(@to)
            File.open(tmp, "wb") do |f|
                f.write(bytes)
                f.flush
                f.fsync
            end
            File.rename(tmp, path)
        rescue SystemCallError, IOError => e
            FileUtils.rm_f(tmp)
            raise FileError.new("cannot write #{path}: #{e.message}", path: path)
        end

        def copy_checked(src, dest, name, sha)
            tmp = Cache.tmp_path(@to)
            begin
                FileUtils.cp(src, tmp)
                File.open(tmp, "r+b", &:fsync) # Windows: fsync needs a handle open for writing
                actual = Release.sha256_file(tmp)
                raise ChecksumError.new("#{name}: SHA-256 mismatch", file: dest, expected: sha, actual: actual) if actual != sha
                File.rename(tmp, dest)
            rescue SystemCallError, IOError => e
                raise FileError.new("cannot write #{dest}: #{e.message}", path: dest)
            ensure
                FileUtils.rm_f(tmp)
            end
        end

        def gunzip_into(gz, dest, name, sha)
            Downloader.gunzip_checked(gz, @to, dest, name, sha, error_class: FileError)
        end
    end
end
