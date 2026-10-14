require "fileutils"
require "json"
require "securerandom"
require "socket"
require "time"
require_relative "cache_json"

class OpenTideConstants
    # The on-disk cache shared by every SDK on one machine (spec §5.4):
    #
    #     <root>/v1/pointer/OTC_latest-f1.json (+ .etag), OTC_index.json (+ .etag)
    #     <root>/v1/releases/<D>/OTC_<D>.sha256, data files, .verified, .lock/
    #
    # Every write is a temporary file in the same directory, fsynced and then
    # renamed into place. A release directory is trusted only when .verified
    # is valid. The lock directory stops duplicate work and guards deletion.
    class Cache
        LOCK_POLL_S = 0.5
        LOCK_STALE_S = 120
        # How old the lock itself must be to be stale (spec §5.4, CR2 DR3).
        LOCK_STALE_AGE_S = 120
        STARTED_AT_RE = /\A\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|\+00:00)\z/

        # A stale lock that cannot be removed this many times is a cache error (CR D3).
        LOCK_REMOVE_ATTEMPTS = 3

        attr_reader :root

        def self.encode_cache_json(cache_document)
            CacheJSON.encode(cache_document).encode(Encoding::UTF_8)
        end

        def self.default_root
            if (dir = ENV["OPENTIDECONSTANTS_CACHE_DIR"]) && !dir.empty?
                return dir
            end
            if Gem.win_platform?
                base = ENV["LOCALAPPDATA"]
                base = File.join(home, "AppData", "Local") if base.nil? || base.empty?
                File.join(base, "opentideconstants", "Cache")
            elsif RUBY_PLATFORM.include?("darwin")
                File.join(home, "Library", "Caches", "opentideconstants")
            else
                base = ENV["XDG_CACHE_HOME"]
                base = File.join(home, ".cache") if base.nil? || base.empty?
                File.join(base, "opentideconstants")
            end
        end

        # The home directory for the default cache root, or CacheError when
        # there is none that can be used.
        def self.home
            dir = Dir.home
            raise ArgumentError, "it is #{dir.inspect}" unless dir.is_a?(String) && !dir.empty? && File.absolute_path?(dir)
            dir
        rescue ArgumentError => e
            raise CacheError, "cannot find the home directory for the default cache (#{e.message}); " \
                              "pass cache_dir or set OPENTIDECONSTANTS_CACHE_DIR"
        end

        def self.datestamp_key(d)
            date, counter = d.split(".", 2)
            [date.to_i, (counter || "1").to_i]
        end

        # logger: where lock and cleanup problems that are not raised are
        # logged. lock_stale_s, lock_stale_age_s and lock_poll_s are the §5.4
        # lock times.
        def initialize(root, logger: nil, lock_stale_s: LOCK_STALE_S, lock_poll_s: LOCK_POLL_S,
                       lock_stale_age_s: LOCK_STALE_AGE_S)
            @root = File.expand_path(root)
            @base = File.join(@root, CACHE_LAYOUT_VERSION)
            @logger = logger
            @lock_stale_s = lock_stale_s
            @lock_poll_s = lock_poll_s
            @lock_stale_age_s = lock_stale_age_s
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

        # [body, etag] of a cached pointer or index file, or nil when it is not
        # cached. A file that exists but cannot be read is cache, never absent
        # (spec §5.2 step 6).
        def read_pointer(name)
            path = File.join(pointer_dir, name)
            body = read_file(path)
            return nil unless body
            etag = read_file("#{path}.etag")
            [body.force_encoding(Encoding::UTF_8), etag&.strip]
        end

        # The bytes of a cache file, nil when it is not there, CacheError when
        # it cannot be read (spec §5.2 step 6: cache, never absent).
        def read_file(path)
            File.binread(path)
        rescue Errno::ENOENT, Errno::ENOTDIR
            nil
        rescue SystemCallError, IOError => e
            raise CacheError, "cannot read #{path}: #{e.message}"
        end

        # Writes a pointer or index file and its ETag as a pair, under
        # pointer/.lock (spec §5.4). The old ETag goes first, so a reader
        # between the steps sees a body with no ETag (and asks without one),
        # never a body with another body's ETag.
        def write_pointer(name, body, etag)
            path = File.join(pointer_dir, name)
            with_lock(pointer_dir) do
                remove_file("#{path}.etag")
                write_atomic(path, body)
                write_atomic("#{path}.etag", etag) if etag
            end
        end

        # Deletes a file if it is there; CacheError if it cannot.
        def remove_file(path)
            File.delete(path)
        rescue Errno::ENOENT
            nil
        rescue SystemCallError => e
            raise CacheError, "cannot remove #{path}: #{e.message}"
        end

        # ---- releases

        # The parsed .verified of a release, or nil when the directory is not
        # trusted: no .verified, or one that is not a JSON object whose files
        # rows are objects with a 64-hex or null sha256, a string or null url and an integer
        # size (R2-088); a null or absent size makes it malformed (spec §5.4,
        # CR3 spec review 2 B10 and 3 C4); a size written as 1024.0 is the
        # integer 1024 (CR2 DR10). A .verified that cannot be read is cache.
        def verified(datestamp)
            text = read_file(File.join(release_dir(datestamp), ".verified"))
            return nil unless text
            doc = Reader.parse_json(text.force_encoding(Encoding::UTF_8))
            return nil unless verified_json_value?(doc)
            return nil unless doc.is_a?(Hash) && doc["files"].is_a?(Hash)
            return nil unless doc["datestamp"].nil? || doc["datestamp"] == datestamp
            return nil unless %w[format_version min_reader_version].all? do |key|
                doc[key].nil? || (doc[key].is_a?(String) && doc[key].match?(/\A(0|[1-9]\d*)\.(0|[1-9]\d*)\z/))
            end
            return nil unless %w[zenodo_version_doi verified_at by].all? { |key| doc[key].nil? || doc[key].is_a?(String) }
            doc["files"].each_value { |row| return nil unless verified_row?(row) }
            doc["files"].each_value { |row| row["size"] = Reader.integral(row["size"]) }
            doc
        rescue InvalidReleaseError
            nil
        end

        # The strict-JSON rules apply to unknown receipt extensions too (§7.3).
        # Count containers, including the root, and keep finite untyped integers.
        def verified_json_value?(value, depth = 0)
            return value.finite? if value.is_a?(Numeric)
            children = value.is_a?(Hash) ? value.values : value.is_a?(Array) ? value : nil
            return true unless children
            return false if depth >= 64
            children.all? { |child| verified_json_value?(child, depth + 1) }
        end

        def verified_row?(row)
            return false unless row.is_a?(Hash)
            size = Reader.integral(row["size"])
            (row["sha256"].nil? || (row["sha256"].is_a?(String) && row["sha256"].match?(/\A[0-9a-fA-F]{64}\z/))) &&
                (row["url"].nil? || row["url"].is_a?(String)) && size.is_a?(Integer) && size.between?(0, 2**53 - 1)
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

        # The release-level values .verified keeps next to the files: what the
        # pointer or index entry said (format_version, min_reader_version,
        # zenodo_version_doi). A key that info leaves out keeps its old value.
        # .verified also has the datestamp (spec §5.4, CR D26).
        VERIFIED_INFO = %w[format_version min_reader_version zenodo_version_doi].freeze

        # files: the rows of the files this open stored and verified. A row of
        # the old .verified stays only while its file is in the release
        # directory, and a row for OTC_<D>.sha256 never does (spec §5.4, CR3
        # DR100); every SHA-256 is written in lowercase.
        def write_verified(datestamp, files, info = {})
            dir = release_dir(datestamp)
            path = File.join(dir, ".verified")
            prev = verified(datestamp)
            sums = "OTC_#{datestamp}.sha256"
            merged = (prev ? prev["files"] : {}).select do |name, row|
                name != sums && row["sha256"].is_a?(String) && File.file?(File.join(dir, name))
            end
            merged = merged.transform_values do |row|
                { "sha256" => row["sha256"].downcase, "size" => row["size"], "url" => row["url"] }
            end
            files.each do |name, row|
                old = merged[name] || {}
                merged[name] = { "sha256" => (row["sha256"] || old["sha256"])&.downcase, "size" => row["size"] || old["size"],
                                 "url" => row["url"] || old["url"] }
            end
            doc = { "datestamp" => datestamp, "files" => merged.sort.to_h, "verified_at" => Time.now.utc.iso8601,
                    "by" => "opentideconstants-ruby/#{VERSION}" }
            VERIFIED_INFO.each do |k|
                doc[k] = info.key?(k) ? info[k] : prev&.dig(k)
            end
            write_atomic(path, Cache.encode_cache_json(doc))
        end

        # Stores the version DOI of a pointer or index entry in the .verified
        # of a cached release, when it differs (spec §4.3). Best effort. The
        # read-modify-write runs under the release lock, taken without waiting
        # (spec §5.4, CR2 DR3): while another process holds a young lock (a
        # download writes .verified), the note is skipped.
        def note_version_doi(datestamp, doi)
            same = ->(v) { v.nil? || (v.key?("zenodo_version_doi") && v["zenodo_version_doi"] == doi) }
            return if same.call(verified(datestamp))
            dir = release_dir(datestamp)
            taken = try_lock(dir) do
                ver = verified(datestamp) # again, now under the lock
                next if same.call(ver)
                ver["zenodo_version_doi"] = doi
                write_atomic(File.join(dir, ".verified"), Cache.encode_cache_json(ver))
            end
            log(:debug, "#{dir} is locked by another process; its version DOI is noted later") unless taken
        rescue CacheError, FileError => e
            log(:warn, "cannot note the version DOI of #{datestamp}: #{e.message}")
        end

        # Datestamps of trusted release directories, newest first.
        def cached_releases
            return [] unless File.directory?(releases_dir)
            Dir.children(releases_dir)
               .select { |d| d.match?(DATESTAMP_RE) && verified(d) }
               .sort_by { |d| Cache.datestamp_key(d) }.reverse
        rescue Errno::ENOENT, Errno::ENOTDIR
            []
        rescue SystemCallError => e
            # an unreadable cache is not an empty one (R2-091, spec §5.2 step 6)
            raise CacheError, "cannot list #{releases_dir}: #{e.message}"
        end

        # Datestamp directories with no valid .verified: a download that failed
        # or is still running. These never count toward prune's keep budget.
        def partial_releases
            return [] unless File.directory?(releases_dir)
            Dir.children(releases_dir)
               .select { |d| d.match?(DATESTAMP_RE) && File.directory?(release_dir(d)) && !verified(d) }
        rescue Errno::ENOENT, Errno::ENOTDIR
            []
        rescue SystemCallError => e
            raise CacheError, "cannot list #{releases_dir}: #{e.message}"
        end

        # Removes a release directory (spec §4.3 prune). It takes the release
        # lock without waiting, so a release that another process is
        # downloading into is left alone: then it returns false. .verified
        # goes first, so a directory that cannot be removed in full is no
        # longer trusted, and any failure is a CacheError. True when removed.
        # Partial releases are judged under the lock after a marker re-read;
        # their age uses the pre-take mtime, which taking the lock changes.
        def remove_release(datestamp, partial: false)
            dir = release_dir(datestamp)
            return true unless File.directory?(dir)
            mtime = File.mtime(dir) if partial
            removed = false
            taken = try_lock(dir) do
                if partial
                    if verified(datestamp)
                        log(:info, "prune: #{datestamp} became verified; kept")
                        next
                    end
                    next unless Time.now - mtime > 120
                end
                remove_file(File.join(dir, ".verified"))
                Dir.children(dir).each do |name|
                    next if name == ".lock"
                    FileUtils.rm_r(File.join(dir, name))
                end
                removed = true
            end
            return false unless taken && removed
            begin
                Dir.rmdir(dir)
            rescue Errno::ENOENT, Errno::ENOTEMPTY, Errno::EEXIST
                nil # another process started a download into it after the lock was released
            end
            true
        rescue SystemCallError => e
            raise CacheError, "cannot remove #{dir}: #{e.message}"
        end

        # ---- the lock directory (spec §5.4 Locks)

        # Runs the block while holding <dir>/.lock. Returns early (without the
        # block) with :done when done.call becomes true while waiting. A lock
        # is stale when this waiter has waited the stale time and the lock
        # itself is at least lock_stale_age_s old (CR2 DR3); a stale lock is
        # removed and taken, and the wait starts again. A stale lock that
        # cannot be removed 3 times is a CacheError (CR D3).
        def with_lock(dir, done: -> { false })
            ensure_dir(dir)
            lock = File.join(dir, ".lock")
            waited = 0.0
            failures = 0
            loop do
                begin
                    Dir.mkdir(lock)
                    break
                rescue Errno::EEXIST
                    return :done if done.call
                    if waited >= @lock_stale_s && lock_stale?(lock) # the age is read just before the removal
                        if remove_stale_lock(lock)
                            waited = 0.0
                            next
                        end
                        failures += 1
                        raise CacheError, "cannot remove the stale lock #{lock} after #{failures} attempts" if failures >= LOCK_REMOVE_ATTEMPTS
                    end
                    sleep(@lock_poll_s)
                    waited += @lock_poll_s
                rescue SystemCallError => e
                    raise CacheError, "cannot take the lock #{lock}: #{e.message}"
                end
            end
            hold(lock) { yield }
        end

        # Takes <dir>/.lock without waiting, runs the block and returns true;
        # returns false (without the block) when another process holds a lock
        # younger than lock_stale_age_s. An older lock is stale: it is removed
        # and taken (spec §5.4 non-blocking takes, CR2 DR3). A stale lock that
        # cannot be removed is a CacheError.
        def try_lock(dir)
            lock = File.join(dir, ".lock")
            attempt = 0
            begin
                Dir.mkdir(lock)
            rescue Errno::EEXIST
                return false if attempt.positive? || !lock_stale?(lock)
                raise CacheError, "cannot remove the stale lock #{lock}" unless remove_stale_lock(lock)
                attempt += 1
                retry # once: a process that takes it now holds a young lock
            rescue SystemCallError => e
                raise CacheError, "cannot take the lock #{lock}: #{e.message}"
            end
            hold(lock) { yield }
            true
        end

        # Seconds since the lock was taken (spec §5.4, CR2 DR3): from
        # owner.json started_at, or from the mtime of the lock directory when
        # owner.json is missing or cannot be read. nil when the lock is gone
        # or its age cannot be read: such a lock is never stale.
        def lock_age(lock)
            started = begin
                owner = JSON.parse(File.read(File.join(lock, "owner.json")))
                at = owner.is_a?(Hash) ? owner["started_at"] : nil
                at.is_a?(String) && at.match?(STARTED_AT_RE) ? Time.iso8601(at) : nil
            rescue JSON::ParserError, SystemCallError, IOError, ArgumentError, EncodingError
                nil
            end
            Time.now - (started || File.mtime(lock))
        rescue SystemCallError
            nil
        end

        def lock_stale?(lock)
            age = lock_age(lock)
            !age.nil? && age >= @lock_stale_age_s
        end

        private

        # Writes owner.json with a fresh token, runs the block, and releases
        # the lock only while the token is still ours (spec §5.4 Release).
        def hold(lock)
            token = SecureRandom.hex(16)
            owner_path = File.join(lock, "owner.json")
            begin
                owner = { "pid" => Process.pid, "host" => Socket.gethostname, "sdk" => "opentideconstants-ruby/#{VERSION}",
                          "started_at" => Time.now.utc.iso8601, "token" => token }
                File.write(owner_path, JSON.generate(owner))
            rescue SystemCallError, IOError => e
                release_lock(lock, owner_path, nil)
                raise CacheError, "cannot write #{owner_path}: #{e.message}"
            end
            mutex = Mutex.new
            wake = ConditionVariable.new
            stopped = false
            heartbeat = nil
            identity = nil
            owned = lambda do
                current = JSON.parse(File.read(owner_path))
                stat = File.stat(lock)
                current if current.is_a?(Hash) && current["token"] == token && stat.dev == identity.dev && stat.ino == identity.ino
            end
            begin
                identity = File.stat(lock)
                heartbeat = Thread.new do
                    loop do
                        break if mutex.synchronize { wake.wait(mutex, 30) unless stopped; stopped }
                        tmp = nil
                        begin
                            current = owned.call
                            unless current
                                log(:warn, "the lock #{lock} is no longer ours; stopping its heartbeat")
                                break
                            end
                            tmp = Cache.tmp_path(lock)
                            File.open(tmp, File::WRONLY | File::CREAT | File::EXCL, 0o600) do |file|
                                file.write(JSON.generate(current.merge("started_at" => Time.now.utc.iso8601)))
                                file.flush
                                file.fsync
                            end
                            unless owned.call
                                log(:warn, "the lock #{lock} is no longer ours; stopping its heartbeat")
                                break
                            end
                            File.rename(tmp, owner_path)
                            unless owned.call
                                log(:warn, "the lock #{lock} is no longer ours; stopping its heartbeat")
                                break
                            end
                            now = Time.now
                            File.utime(now, now, lock)
                        rescue Errno::ENOENT, Errno::ENOTDIR
                            log(:warn, "the lock #{lock} is gone; stopping its heartbeat")
                            break
                        rescue JSON::ParserError, SystemCallError, IOError => e
                            log(:warn, "cannot refresh the lock #{lock}: #{e.message}")
                        ensure
                            FileUtils.rm_f(tmp) if tmp
                        end
                    end
                end
                yield
            ensure
                mutex.synchronize { stopped = true; wake.signal }
                heartbeat&.join
                release_lock(lock, owner_path, token)
            end
        end

        # Deletes owner.json and the lock directory, unless another process
        # has taken the lock as stale (its token differs). A failure is logged:
        # the work is done, and a leftover lock only delays others.
        def release_lock(lock, owner_path, token)
            if token
                current = begin
                    JSON.parse(File.read(owner_path))["token"]
                rescue JSON::ParserError, SystemCallError, IOError, TypeError, NoMethodError
                    nil
                end
                if current != token
                    log(:warn, "the lock #{lock} is now held by another process; leaving it")
                    return
                end
            end
            begin
                File.delete(owner_path)
            rescue Errno::ENOENT
                nil
            end
            Dir.rmdir(lock)
        rescue SystemCallError => e
            log(:warn, "cannot release the lock #{lock}: #{e.message}")
        end

        # Removes a stale lock directory; false when it is still there.
        def remove_stale_lock(lock)
            log(:warn, "taking the stale lock #{lock}")
            FileUtils.rm_r(lock)
            true
        rescue Errno::ENOENT
            true
        rescue SystemCallError => e
            log(:warn, "cannot remove the stale lock #{lock}: #{e.message}")
            !File.exist?(lock)
        end

        def log(level, msg)
            @logger&.public_send(level, "opentideconstants: #{msg}")
        end
    end
end
