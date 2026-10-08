require "fileutils"
require "monitor"
require "json"
require "uri"
require "zlib"
require "digest"

class OpenTideConstants
    FORMATS = %w[json json.gz jsonl].freeze
    MODES = %w[eager stream].freeze
    ON_NETWORK_ERROR = %w[use_cache raise].freeze

    # The release the client has loaded.
    attr_reader :release
    # Where the release came from: :download, :cache, :cache_after_error, :file or :file_unverified.
    attr_reader :loaded_from
    # The error behind loaded_from :cache_after_error, or nil.
    attr_reader :last_error

    # Opens a client and yields it, closing it afterwards. Without a block it
    # is the same as new.
    def self.open(**options)
        client = new(**options)
        return client unless block_given?
        begin
            yield client
        ensure
            client.close
        end
    end

    # Opens the latest release (the default), a pinned release
    # (release: "20261008") or a local file (file: "…/OTC_20261008.jsonl").
    # See spec §4.2 for the options.
    def initialize(release: :latest, file: nil, cache_dir: nil, offline: false, mode: :eager, base_url: nil,
                   timeout: nil, proxy: nil, ca_file: nil, user_agent: nil, on_network_error: :use_cache,
                   auto_update: false, update_interval: 86_400, logger: nil, verify_on_open: false)
        @requested = check_release_arg(release)
        @mode = check_enum(mode, MODES, "mode").to_sym
        @on_network_error = check_enum(on_network_error, ON_NETWORK_ERROR, "on_network_error").to_sym
        @offline = check_bool(offline, "offline") || ENV["OPENTIDECONSTANTS_OFFLINE"] == "1"
        @auto_update = check_bool(auto_update, "auto_update")
        @verify_on_open = check_bool(verify_on_open, "verify_on_open")
        unless update_interval.is_a?(Numeric) && update_interval.positive?
            raise InvalidArgumentError, "update_interval must be a number of seconds > 0"
        end
        @update_interval = update_interval
        unless timeout.nil? || (timeout.is_a?(Numeric) && timeout.positive?)
            raise InvalidArgumentError, "timeout must be nil or a number of seconds > 0"
        end
        %i[proxy ca_file user_agent].zip([proxy, ca_file, user_agent]).each do |name, v|
            raise InvalidArgumentError, "#{name} must be a String" unless v.nil? || v.is_a?(String)
        end
        base_url ||= ENV["OPENTIDECONSTANTS_BASE_URL"]
        base_url = DEFAULT_BASE_URL if base_url.nil? || base_url.empty?
        raise InvalidArgumentError, "base_url must be a String" unless base_url.is_a?(String)
        @base_url = base_url.end_with?("/") ? base_url : "#{base_url}/"
        raise InvalidArgumentError, "cache_dir must be a String" unless cache_dir.nil? || cache_dir.is_a?(String)
        @cache_dir = cache_dir
        @logger = logger
        @http = HTTP.new(timeout: timeout, proxy: proxy, ca_file: ca_file, user_agent: user_agent, logger: logger)
        @lock = Monitor.new
        @last_error = nil
        @file = file
        if file
            @release, @loaded_from = Reader.open_file(file, mode: @mode)
        elsif @requested == :latest
            open_latest
        else
            open_pinned(@requested)
        end
        @last_check = monotonic
        log(:info, "loaded #{@release.datestamp} (#{@loaded_from})")
    end

    # ---- release management (spec §4.3)

    # Every release, newest first, from OTC_index.json.
    def releases
        body = fetch_pointer_file("OTC_index.json", missing: :offline)
        doc = parse_pointer(body)
        list = doc.is_a?(Hash) && doc["releases"].is_a?(Array) ? doc["releases"] : []
        list.map { |e| release_info(e, @base_url + "OTC_index.json") }
            .sort_by { |i| Cache.datestamp_key(i.datestamp) }.reverse.freeze
    end

    # The latest release (one conditional GET of the pointer). It does not
    # switch to it.
    def latest
        raise OfflineError, "offline: the latest pointer is not available" if @offline
        entry, url = fetch_latest_pointer
        release_info(entry, url)
    end

    # A release newer than the loaded one with a supported format major, or nil.
    def check_for_update
        info = latest
        return nil unless supported_major?(info.format_version)
        newer?(info.datestamp, @release.datestamp) ? info : nil
    end

    # Downloads and checks the latest release and swaps it in atomically. A
    # Release held from before stays valid.
    def update!
        raise PinnedReleaseError, "the client was opened on a file" if @file
        raise PinnedReleaseError, "the client was opened on release #{@requested}" unless @requested == :latest
        @lock.synchronize do
            from = @release.datestamp
            entry, url = fetch_latest_pointer
            check_major!(entry["format_version"])
            unless newer?(entry["datestamp"], from)
                @last_check = monotonic
                return UpdateResult.new(false, from, from)
            end
            rel, how = load_from_entry(entry, url)
            @release = rel
            @loaded_from = how
            @last_error = nil
            @last_check = monotonic
            log(:info, "updated from #{from} to #{rel.datestamp}")
            UpdateResult.new(true, from, rel.datestamp)
        end
    end

    # Writes a release into a folder the caller chooses (spec §4.3.2). Returns
    # the paths written.
    def download(release = :latest, to:, formats: [:jsonl], overwrite: false)
        want = check_release_arg(release)
        raise InvalidArgumentError, "to must be a String path" unless to.is_a?(String) && !to.empty?
        raise InvalidArgumentError, "formats must be an Array" unless formats.is_a?(Array) && !formats.empty?
        formats = formats.map { |f| check_enum(f, FORMATS, "format") }.uniq
        check_bool(overwrite, "overwrite")
        Downloader.new(self, want, File.expand_path(to), formats, overwrite).run
    end

    # Hashes the loaded files again and compares them with OTC_{D}.sha256.
    def verify
        @release.send(:verify)
    end

    # Datestamps in the cache, newest first.
    def cached_releases
        cache.cached_releases
    end

    # Removes all but the newest keep releases from the cache (never the
    # loaded one). Returns the datestamps removed, newest first.
    def prune(keep: 3)
        raise InvalidArgumentError, "keep must be an Integer >= 0" unless keep.is_a?(Integer) && keep >= 0
        all = cache.cached_releases
        removed = all.drop(keep).reject { |d| d == @release.datestamp && @loaded_from != :file && @loaded_from != :file_unverified }
        removed.each { |d| cache.remove_release(d) }
        removed
    end

    def close
        @release&.send(:close)
        nil
    end

    # ---- queries, forwarded to the current release (spec §4.4–§4.7)

    %i[station require_station tombstone station_by_alias stations iter_stations each_station search near nearest
       reference_station subordinates_of attribution].each do |name|
        define_method(name) do |*args, **kw, &blk|
            maybe_auto_update
            @release.public_send(name, *args, **kw, &blk)
        end
    end

    def inspect
        "#<OpenTideConstants #{@release&.datestamp} (#{@loaded_from})>"
    end

    # ---- internals shared with Downloader (private: Downloader calls them with send)

    attr_reader :http, :base_url, :offline

    def cache
        @cache ||= Cache.new(@cache_dir || Cache.default_root)
    end

    # The latest pointer: [entry, url]. OTC_latest-f0.json, then
    # OTC_latest.json on a 404 only.
    def fetch_latest_pointer
        names = SUPPORTED_FORMAT_MAJORS.sort.reverse.map { |m| "OTC_latest-f#{m}.json" } + ["OTC_latest.json"]
        names.each do |name|
            body = fetch_pointer_file(name, missing: :nil)
            next if body.nil?
            entry = parse_pointer(body)
            raise InvalidReleaseError, "#{name} is not a release entry" unless entry.is_a?(Hash) && entry["datestamp"].is_a?(String)
            return [entry, @base_url + name]
        end
        raise ReleaseNotFoundError, "no latest pointer at #{@base_url}"
    end

    def check_major!(format_version)
        return if supported_major?(format_version)
        raise UnsupportedFormatError, "the latest release has format #{format_version}, not supported by this SDK"
    end

    def release_info(entry, pointer_url)
        files = Array(entry["files"]).map do |f|
            FileInfo.new(name: f["name"], url: f["url"] && resolve(pointer_url, f["url"]), size: f["size"], sha256: f["sha256"])
        end.sort_by(&:name)
        ReleaseInfo.new(entry, files)
    end

    def resolve(base, ref)
        URI.join(base, ref).to_s
    rescue URI::Error
        ref
    end

    def log(level, msg)
        @logger&.public_send(level, "opentideconstants: #{msg}")
    end

    private :http, :base_url, :offline, :cache, :fetch_latest_pointer, :check_major!, :release_info, :resolve, :log

    private

    def monotonic
        Process.clock_gettime(Process::CLOCK_MONOTONIC)
    end

    def maybe_auto_update
        return unless @auto_update && @requested == :latest && @file.nil? && !@offline
        return if monotonic - @last_check < @update_interval
        begin
            update!
        rescue Error => e
            @last_check = monotonic
            log(:warn, "automatic update failed: #{e.message}")
        end
    end

    def check_release_arg(release)
        return :latest if release == :latest || release == "latest"
        unless release.is_a?(String) && release.match?(DATESTAMP_RE)
            raise InvalidArgumentError, "release must be :latest or a datestamp like 20261008 or 20261008.2, not #{release.inspect}"
        end
        release
    end

    def check_enum(value, allowed, name)
        v = value.is_a?(Symbol) ? value.to_s : value
        raise InvalidArgumentError, "#{name} must be one of #{allowed.join(', ')}, not #{value.inspect}" unless allowed.include?(v)
        v
    end

    def check_bool(value, name)
        raise InvalidArgumentError, "#{name} must be true or false" unless value == true || value == false
        value
    end

    def supported_major?(format_version)
        m = /\A(\d+)\./.match(format_version.to_s)
        m && SUPPORTED_FORMAT_MAJORS.include?(m[1].to_i)
    end

    def newer?(a, b)
        (Cache.datestamp_key(a) <=> Cache.datestamp_key(b)) == 1
    end

    def parse_pointer(body)
        JSON.parse(body)
    rescue JSON::ParserError => e
        raise InvalidReleaseError, "bad pointer file: #{e.message[0, 200]}"
    end

    # GETs a pointer or index file with If-None-Match and stores it. Offline,
    # or after a network error with on_network_error :use_cache, it uses the
    # cached copy. missing: :nil returns nil on a 404; :offline raises
    # OfflineError when offline with no cached copy.
    def fetch_pointer_file(name, missing:)
        cached = cache.read_pointer(name)
        if @offline
            return cached[0] if cached
            raise OfflineError, "offline and #{name} is not cached"
        end
        res = @http.get(@base_url + name, etag: cached && cached[1])
        case res.status
        when 304
            return cached[0] if cached
            res = @http.get(@base_url + name)
        when 404
            return nil if missing == :nil
            raise ReleaseNotFoundError, "#{@base_url}#{name}: HTTP 404"
        end
        if res.status == 200
            cache.ensure_dir(cache.pointer_dir)
            cache.write_pointer(name, res.body, res.etag)
            return res.body
        end
        raise NetworkError.new("#{@base_url}#{name}: HTTP #{res.status}", url: @base_url + name, status: res.status)
    rescue NetworkError => e
        raise unless missing == :offline && @on_network_error == :use_cache && cached
        @last_error = e
        log(:warn, "#{e.message}; using the cached #{name}")
        cached[0]
    end

    # spec §5.2
    def open_latest
        if @offline
            d = newest_cached
            raise OfflineError, "offline and no release is cached in #{cache.root}" unless d
            @release = load_cached(d)
            @loaded_from = :cache
            return
        end
        cache.ensure_dir(cache.releases_dir)
        begin
            entry, url = fetch_latest_pointer
            check_major!(entry["format_version"])
            @release, @loaded_from = load_from_entry(entry, url)
        rescue NetworkError => e
            d = @on_network_error == :use_cache ? newest_cached : nil
            raise unless d
            log(:warn, "#{e.message}; using the cached release #{d}")
            @release = load_cached(d)
            @loaded_from = :cache_after_error
            @last_error = e
        end
    end

    def open_pinned(d)
        if usable_cached?(d)
            @release = load_cached(d)
            @loaded_from = :cache
            return
        end
        raise OfflineError, "offline and release #{d} is not cached" if @offline
        cache.ensure_dir(cache.releases_dir)
        @release = fetch_release(d, nil, nil)
        @loaded_from = :download
    end

    # [release, loaded_from] for a pointer entry: the cache when it has it.
    def load_from_entry(entry, url)
        d = entry["datestamp"]
        raise InvalidReleaseError, "bad datestamp #{d.inspect} in the pointer" unless d.match?(DATESTAMP_RE)
        return [load_cached(d), :cache] if usable_cached?(d)
        [fetch_release(d, entry, url), :download]
    end

    # The newest cached release with a supported format major.
    def newest_cached
        cache.cached_releases.find do |d|
            ver = cache.verified(d)
            (ver["format_version"].nil? || supported_major?(ver["format_version"])) && usable_cached?(d)
        end
    end

    # The data files a load in this mode reads, in order of preference.
    def wanted_files(d)
        json = ["OTC_#{d}.json"]
        jsonl = ["OTC_#{d}.jsonl", "OTC_#{d}.meta.json"]
        @mode == :stream ? [jsonl] : [json, jsonl]
    end

    def usable_cached?(d)
        ver = cache.verified(d)
        return false unless ver
        wanted_files(d).any? { |names| names.all? { |n| cache.file_ok?(d, n, ver) } }
    end

    def load_cached(d)
        ver = cache.verified(d)
        names = wanted_files(d).find { |ns| ns.all? { |n| cache.file_ok?(d, n, ver) } }
        dir = cache.release_dir(d)
        paths = names.map { |n| File.join(dir, n) }
        checks = paths.to_h { |p| [p, ver["files"][File.basename(p)]["sha256"]] }
        Reader.verify_checks(checks) if @verify_on_open
        files = ver["files"].map do |name, row|
            FileInfo.new(name: name, url: row["url"], size: row["size"], sha256: row["sha256"])
        end
        return Reader.load(paths.first, mode: @mode, files: files, checks: checks) unless @mode == :stream
        index = fresh_stream_index(d, ver, paths.first)
        if index
            begin
                return Reader.load(paths.first, mode: @mode, files: files, checks: checks, index: index)
            rescue InvalidReleaseError => e
                log(:warn, "the stream index for #{d} cannot be used (#{e.message}); rebuilding it")
            end
        end
        rows = []
        rel = Reader.load(paths.first, mode: @mode, files: files, checks: checks, index_rows: rows)
        write_stream_index(d, rel, rows, ver, paths.first)
        rel
    end

    # The entries of index-v1.json when it is fresh for release d (spec §6.2), else nil.
    def fresh_stream_index(d, ver, jsonl_path)
        path = File.join(cache.release_dir(d), "index-v1.json")
        return nil unless File.file?(path)
        idx = JSON.parse(File.read(path, mode: "rb").force_encoding(Encoding::UTF_8))
        jsonl = "OTC_#{d}.jsonl"
        return nil unless idx.is_a?(Hash) && idx["index_version"].is_a?(Integer) && idx["index_version"] == 1
        return nil unless idx["datestamp"] == d && idx["jsonl"] == jsonl
        return nil unless idx["jsonl_sha256"].is_a?(String) && idx["jsonl_sha256"] == ver["files"].dig(jsonl, "sha256")
        return nil unless idx["jsonl_size"].is_a?(Integer) && idx["jsonl_size"] == File.size(jsonl_path)
        return nil unless idx["stations"].is_a?(Array) && idx["stations"].all? { |e| Reader.index_entry_ok?(e) }
        idx["stations"]
    rescue JSON::ParserError, EncodingError, SystemCallError, IOError
        nil
    end

    # Writes index-v1.json (spec §6.2): rows are the entries of every line,
    # from the pass that loaded rel. A failure to write it is logged, not
    # raised: the index only saves work.
    def write_stream_index(d, rel, rows, ver, jsonl_path)
        jsonl = "OTC_#{d}.jsonl"
        sha = ver["files"].dig(jsonl, "sha256")
        return unless sha.is_a?(String)
        kinds = rel.send(:index_kinds)
        rows.each { |r| r["kind"] = kinds[r["station_id"]] if r["status"] == "active" && kinds.key?(r["station_id"]) }
        doc = { "index_version" => 1, "datestamp" => d, "jsonl" => jsonl, "jsonl_sha256" => sha,
                "jsonl_size" => File.size(jsonl_path), "by" => "opentideconstants-ruby/#{VERSION}", "stations" => rows }
        cache.write_atomic(File.join(cache.release_dir(d), "index-v1.json"), JSON.generate(doc) + "\n")
    rescue CacheError, SystemCallError, IOError => e
        log(:warn, "cannot write the stream index for #{d}: #{e.message}")
    end

    # Downloads, checks and caches release d (spec §5.2 step 4), then loads it.
    def fetch_release(d, entry, pointer_url)
        dir = cache.ensure_dir(cache.release_dir(d))
        result = cache.with_lock(dir, done: -> { usable_cached?(d) }) do
            return load_cached(d) if usable_cached?(d)
            download_into_cache(d, entry, pointer_url)
        end
        return load_cached(d) if result == :done
        load_cached(d)
    end

    def download_into_cache(d, entry, pointer_url)
        dir = cache.release_dir(d)
        rows, sha_bytes = Downloader.fetch_sha256(self, d, entry, pointer_url)
        pointer_files = entry ? Array(entry["files"]).to_h { |f| [f["name"], f] } : {}
        url_of = lambda do |name|
            f = pointer_files[name]
            f && f["url"] ? resolve(pointer_url, f["url"]) : @base_url + name
        end
        sha_name = "OTC_#{d}.sha256"
        verified = {}
        rows.each do |name, sha|
            pf = pointer_files[name]
            verified[name] = { "sha256" => sha, "size" => pf && pf["size"], "url" => url_of.call(name) }
        end
        # The .sha256 file is in release.files only when the pointer lists it
        # (a pinned download reads no pointer: README, suite choices).
        if pointer_files[sha_name]
            verified[sha_name] = { "sha256" => Digest::SHA256.hexdigest(sha_bytes), "size" => sha_bytes.bytesize,
                                   "url" => url_of.call(sha_name) }
        end
        cache.write_atomic(File.join(dir, sha_name), sha_bytes)
        format_version = entry && entry["format_version"]
        if @mode == :stream
            %W[OTC_#{d}.jsonl OTC_#{d}.meta.json].each do |name|
                size = Downloader.fetch_checked(self, url_of.call(name), dir, File.join(dir, name), name, rows[name],
                                                pointer_files.dig(name, "size"))
                verified[name]["size"] = size
            end
        else
            gz = "OTC_#{d}.json.gz"
            json = "OTC_#{d}.json"
            tmp_gz = Cache.tmp_path(dir)
            begin
                Downloader.fetch_checked(self, url_of.call(gz), dir, nil, gz, rows[gz], pointer_files.dig(gz, "size"),
                                         keep_tmp: tmp_gz)
                size = Downloader.gunzip_checked(tmp_gz, dir, File.join(dir, json), json, rows[json])
                verified[json]["size"] = size
                verified[gz]["size"] ||= File.size(tmp_gz) if verified[gz]
            ensure
                FileUtils.rm_f(tmp_gz)
            end
        end
        if format_version.nil?
            format_version = begin
                if @mode == :stream
                    JSON.parse(File.read(File.join(dir, "OTC_#{d}.meta.json")))["format_version"]
                end
            rescue StandardError
                nil
            end
        end
        cache.write_verified(d, verified, format_version)
    end
end
