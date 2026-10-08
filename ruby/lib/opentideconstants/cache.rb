require "fileutils"
require "json"
require "securerandom"
require "socket"
require "time"

class OpenTideConstants
    # The on-disk cache shared by every SDK on one machine (spec §5.4):
    #
    #     <root>/v1/pointer/OTC_latest-f0.json (+ .etag), OTC_index.json (+ .etag)
    #     <root>/v1/releases/<D>/OTC_<D>.sha256, data files, .verified, .lock/
    #
    # Every write is a temporary file in the same directory, fsynced and then
    # renamed into place. A release directory is trusted only when .verified
    # exists. The lock directory only stops duplicate work.
    class Cache
        LOCK_POLL_S = 0.5
        LOCK_STALE_S = 120

        attr_reader :root

        def self.default_root
            if (dir = ENV["OPENTIDECONSTANTS_CACHE_DIR"]) && !dir.empty?
                return dir
            end
            if Gem.win_platform?
                base = ENV["LOCALAPPDATA"] || File.join(Dir.home, "AppData", "Local")
                File.join(base, "opentideconstants", "Cache")
            elsif RUBY_PLATFORM.include?("darwin")
                File.join(Dir.home, "Library", "Caches", "opentideconstants")
            else
                base = ENV["XDG_CACHE_HOME"]
                base = File.join(Dir.home, ".cache") if base.nil? || base.empty?
                File.join(base, "opentideconstants")
            end
        end

        def self.datestamp_key(d)
            date, counter = d.split(".", 2)
            [date.to_i, (counter || "1").to_i]
        end

        def initialize(root)
            @root = File.expand_path(root)
            @base = File.join(@root, CACHE_LAYOUT_VERSION)
        end

        def pointer_dir
            File.join(@base, "pointer")
        end

        def releases_dir
            File.join(@base, "releases")
        end

        def release_dir(datestamp)
            File.join(releases_dir, datestamp)
        end

        # Creates a directory, or raises CacheError.
        def ensure_dir(dir)
            FileUtils.mkdir_p(dir)
            dir
        rescue SystemCallError, IOError => e
            raise CacheError, "cannot create the cache directory #{dir}: #{e.message}"
        end

        # A temporary file name in dir, as the spec names it.
        def self.tmp_path(dir)
            File.join(dir, ".tmp-#{Process.pid}-#{SecureRandom.hex(6)}")
        end

        # Writes bytes to path atomically.
        def write_atomic(path, bytes)
            dir = ensure_dir(File.dirname(path))
            tmp = Cache.tmp_path(dir)
            File.open(tmp, "wb") do |f|
                f.write(bytes)
                f.flush
                f.fsync
            end
            File.rename(tmp, path)
        rescue SystemCallError, IOError => e
            FileUtils.rm_f(tmp) if tmp
            raise CacheError, "cannot write #{path}: #{e.message}"
        end

        def rename_into_place(tmp, path)
            File.rename(tmp, path)
        rescue SystemCallError => e
            FileUtils.rm_f(tmp)
            raise CacheError, "cannot rename into #{path}: #{e.message}"
        end

        # ---- pointer files

        def read_pointer(name)
            path = File.join(pointer_dir, name)
            return nil unless File.file?(path)
            etag_path = "#{path}.etag"
            body = File.read(path, mode: "rb").force_encoding(Encoding::UTF_8)
            etag = File.file?(etag_path) ? File.read(etag_path).strip : nil
            [body, etag]
        rescue SystemCallError, IOError
            nil
        end

        def write_pointer(name, body, etag)
            path = File.join(pointer_dir, name)
            write_atomic(path, body)
            if etag
                write_atomic("#{path}.etag", etag)
            else
                FileUtils.rm_f("#{path}.etag")
            end
        end

        # ---- releases

        # The parsed .verified of a release, or nil when the directory is not
        # trusted.
        def verified(datestamp)
            path = File.join(release_dir(datestamp), ".verified")
            return nil unless File.file?(path)
            doc = JSON.parse(File.read(path))
            doc.is_a?(Hash) && doc["files"].is_a?(Hash) ? doc : nil
        rescue JSON::ParserError, SystemCallError, IOError
            nil
        end

        # True when name is in the release directory, listed in .verified and
        # of the size .verified gives.
        def file_ok?(datestamp, name, ver = verified(datestamp))
            return false unless ver
            row = ver["files"][name]
            path = File.join(release_dir(datestamp), name)
            return false unless row.is_a?(Hash) && File.file?(path)
            row["size"].nil? || File.size(path) == row["size"]
        end

        def write_verified(datestamp, files, format_version)
            path = File.join(release_dir(datestamp), ".verified")
            prev = verified(datestamp)
            merged = prev ? prev["files"].dup : {}
            files.each do |name, row|
                old = merged[name] || {}
                merged[name] = { "sha256" => row["sha256"] || old["sha256"], "size" => row["size"] || old["size"],
                                 "url" => row["url"] || old["url"] }
            end
            doc = { "files" => merged.sort.to_h, "verified_at" => Time.now.utc.iso8601,
                    "by" => "opentideconstants-ruby/#{VERSION}" }
            doc["format_version"] = format_version || prev&.dig("format_version")
            write_atomic(path, JSON.pretty_generate(doc) + "\n")
        end

        # Datestamps of trusted release directories, newest first.
        def cached_releases
            return [] unless File.directory?(releases_dir)
            Dir.children(releases_dir)
               .select { |d| d.match?(DATESTAMP_RE) && File.file?(File.join(releases_dir, d, ".verified")) }
               .sort_by { |d| Cache.datestamp_key(d) }.reverse
        rescue SystemCallError
            []
        end

        def remove_release(datestamp)
            FileUtils.rm_rf(release_dir(datestamp))
        rescue SystemCallError => e
            raise CacheError, "cannot remove #{release_dir(datestamp)}: #{e.message}"
        end

        # ---- the lock directory (spec §5.4 Locks)

        # Runs the block while holding <dir>/.lock. Returns early (without the
        # block) when done.call becomes true while waiting.
        def with_lock(dir, done: -> { false })
            ensure_dir(dir)
            lock = File.join(dir, ".lock")
            waited = 0.0
            loop do
                begin
                    Dir.mkdir(lock)
                    break
                rescue Errno::EEXIST
                    return :done if done.call
                    if waited >= LOCK_STALE_S
                        FileUtils.rm_rf(lock)
                        waited = 0.0
                        next
                    end
                    sleep(LOCK_POLL_S)
                    waited += LOCK_POLL_S
                rescue SystemCallError => e
                    raise CacheError, "cannot take the lock #{lock}: #{e.message}"
                end
            end
            begin
                owner = { "pid" => Process.pid, "host" => Socket.gethostname, "sdk" => "opentideconstants-ruby/#{VERSION}",
                          "started_at" => Time.now.utc.iso8601 }
                File.write(File.join(lock, "owner.json"), JSON.generate(owner))
                yield
            ensure
                FileUtils.rm_f(File.join(lock, "owner.json"))
                begin
                    Dir.rmdir(lock)
                rescue SystemCallError
                    nil
                end
            end
        end
    end
end
