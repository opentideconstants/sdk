require "fileutils"
require "digest"
require "zlib"

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
            rows = Reader.parse_sha256(bytes.dup.force_encoding(Encoding::UTF_8))
            if pf && pf["sha256"] && pf["sha256"] != res.sha256
                raise ChecksumError.new("#{name} does not match the pointer", file: name, expected: pf["sha256"], actual: res.sha256)
            end
            if entry
                Array(entry["files"]).each do |f|
                    next if f["name"] == name || f["sha256"].nil?
                    listed = rows[f["name"]]
                    next if listed == f["sha256"]
                    raise ChecksumError.new("the pointer and #{name} disagree on #{f['name']}", file: f["name"],
                                            expected: f["sha256"], actual: listed)
                end
            end
            [rows, bytes]
        end

        # Downloads url to a temporary file in dir and checks its size and
        # SHA-256; then renames it to final (or leaves it at keep_tmp).
        # Returns the size. A bad file is deleted.
        def self.fetch_checked(client, url, dir, final, name, expected_sha, expected_size, keep_tmp: nil)
            tmp = keep_tmp || Cache.tmp_path(dir)
            begin
                res = client.send(:http).get_to_file(url, tmp)
                if res.status == 404
                    raise ReleaseNotFoundError, "#{url}: HTTP 404"
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
        rescue SystemCallError => e
            raise CacheError, "cannot write #{final || tmp}: #{e.message}"
        end

        # Decompresses gz into a temporary file in dir, checks the SHA-256 of
        # the result and renames it to final. Returns its size.
        def self.gunzip_checked(gz, dir, final, name, expected_sha)
            tmp = Cache.tmp_path(dir)
            digest = Digest::SHA256.new
            size = 0
            begin
                File.open(tmp, "wb") do |out|
                    Zlib::GzipReader.open(gz) do |zr|
                        while (chunk = zr.read(1 << 16))
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
                raise ChecksumError.new("#{n} is not listed in #{sha_name}", file: n, expected: nil, actual: nil) unless rows[n]
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
            written = []
            todo.each do |n|
                path = File.join(@to, n)
                if n == sha_name
                    write_bytes(path, sha_bytes)
                elsif ver && cache.file_ok?(d, n, ver) && cached_sha_ok?(cache, d, n, rows[n])
                    copy_checked(File.join(cache.release_dir(d), n), path, n, rows[n])
                elsif n.end_with?(".json") && !n.end_with?(".meta.json") && ver && cache.file_ok?(d, "#{n}.gz", ver)
                    gunzip_into(File.join(cache.release_dir(d), "#{n}.gz"), path, n, rows[n])
                else
                    raise OfflineError, "offline and #{n} is not cached" if @client.send(:offline)
                    pf = pointer_files[n]
                    url = pf && pf["url"] ? @client.send(:resolve, pointer_url, pf["url"]) : @client.send(:base_url) + n
                    Downloader.fetch_checked(@client, url, @to, path, n, rows[n], pf && pf["size"])
                end
                written << path
            end
            # OTC_{D}.sha256 goes into place last.
            written.sort_by { |p| File.basename(p) == sha_name ? 1 : 0 }
        end

        private

        def resolve_release
            if @release == :latest
                if @client.send(:offline)
                    d = @client.send(:cache).cached_releases.first
                    raise OfflineError, "offline and no release is cached" unless d
                    return [d, nil, nil]
                end
                entry, url = @client.send(:fetch_latest_pointer)
                @client.send(:check_major!, entry["format_version"])
                return [entry["datestamp"], entry, url]
            end
            [@release, nil, nil]
        end

        def sha_rows(d, ver, entry, pointer_url)
            path = File.join(@client.send(:cache).release_dir(d), "OTC_#{d}.sha256")
            if ver && File.file?(path)
                bytes = File.binread(path)
                return [Reader.parse_sha256(bytes.dup.force_encoding(Encoding::UTF_8)), bytes]
            end
            raise OfflineError, "offline and release #{d} is not cached" if @client.send(:offline)
            Downloader.fetch_sha256(@client, d, entry, pointer_url)
        end

        def cached_sha_ok?(cache, d, n, sha)
            row = cache.verified(d)["files"][n]
            row && row["sha256"] == sha
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
                File.open(tmp, "rb", &:fsync)
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
            Downloader.gunzip_checked(gz, @to, dest, name, sha)
        end
    end
end
