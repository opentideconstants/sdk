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
    # The error behind loaded_from :cache_after_error, or the error of the
    # last automatic update that failed (spec §5.6); nil after an update
    # succeeds, or when there is none.
    attr_reader :last_error
    # The format major of a release on the server that this SDK cannot read
    # (newer than every supported major), as check_for_update last saw it; or nil.
    attr_reader :newer_format_major

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
        # A file client reads no pointer and opens no socket, so these options
        # would be silently ignored (CR D31, spec §4.2). The variable
        # OPENTIDECONSTANTS_OFFLINE is not an option and does not conflict.
        if file && (release != :latest || offline != false || on_network_error != :use_cache)
            raise InvalidArgumentError, "file cannot be combined with release, offline or on_network_error"
        end
        @requested = check_release_arg(release)
        @mode = check_enum(mode, MODES, "mode").to_sym
        @on_network_error = check_enum(on_network_error, ON_NETWORK_ERROR, "on_network_error").to_sym
        # The variable turns offline on with 1, true, yes or on, and then wins over offline: false (CR D15).
        @offline = check_bool(offline, "offline") || %w[1 true yes on].include?(ENV["OPENTIDECONSTANTS_OFFLINE"].to_s.strip.downcase)
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
        raise InvalidArgumentError, "base_url must be nil or a String" unless base_url.nil? || base_url.is_a?(String)
        base_url ||= ENV["OPENTIDECONSTANTS_BASE_URL"]
        base_url = DEFAULT_BASE_URL if base_url.nil? || base_url.empty?
        HTTP.check_url!(base_url, "base_url")
        @base_url = base_url.end_with?("/") ? base_url : "#{base_url}/"
        raise InvalidArgumentError, "cache_dir must be a String" unless cache_dir.nil? || cache_dir.is_a?(String)
        @cache_dir = cache_dir
        @logger = logger
        @http = HTTP.new(timeout: timeout, proxy: proxy, ca_file: ca_file, user_agent: user_agent, logger: logger)
        @lock = Monitor.new
        @closed = false
        @last_error = nil
        @newer_format_major = nil
        @file = file
        @loaded = ObjectSpace::WeakMap.new # every Release this client loaded, while a caller holds it
        if file
            @release, @loaded_from = Reader.open_file(file, mode: @mode, logger: @logger)
        elsif @requested == :latest
            open_latest
        else
            open_pinned(@requested)
        end
        @last_check = monotonic
        @loaded[@release] = true
        log(:info, "loaded #{@release.datestamp} (#{@loaded_from})")
    end

    # ---- release management (spec §4.3)

    # Every release, newest first, from OTC_index.json.
    def releases
        check_open!
        list = index_entries(fetch_pointer_doc("OTC_index.json", missing: :offline))
        list.each { |e| note_version_doi(e) }
        list.map { |e| release_info(e, @base_url + "OTC_index.json") }
            .sort_by { |i| Cache.datestamp_key(i.datestamp) }.reverse.freeze
    end

    # The newest release this gem reads: the latest pointer (a conditional
    # GET), and OTC_index.json too when the pointer's release is not readable
    # (spec §4.3, §5.2 step 2a, CR D23). It does not switch to it.
    def latest
        check_open!
        raise OfflineError, "offline: the latest pointer is not available" if @offline
        entry, url = resolve_latest
        release_info(entry, url)
    end

    # A release newer than the loaded one, with a supported format major and
    # a readable min_reader_version, or nil (spec §4.3, §5.2 step 2a). It also
    # sets newer_format_major when the server has a release of a newer major,
    # also when it then raises because only such releases exist (CR D10).
    def check_for_update
        check_open!
        raise OfflineError, "offline: the latest pointer is not available" if @offline
        begin
            entry, url = resolve_latest
        rescue UnsupportedFormatError, ReaderTooOldError
            check_newer_major
            raise
        end
        check_newer_major
        info = release_info(entry, url)
        newer?(info.datestamp, @release.datestamp) ? info : nil
    end

    # Downloads and checks the latest release and swaps it in atomically. A
    # Release held from before stays valid.
    def update!
        check_open!
        raise PinnedReleaseError, "the client was opened on a file" if @file
        raise PinnedReleaseError, "the client was opened on release #{@requested}" unless @requested == :latest
        # update is defined against the pointer, so offline it cannot run, and
        # it does not switch to a newer cached release either (CR D6).
        raise OfflineError, "offline: update needs the latest pointer" if @offline
        @lock.synchronize do
            from = @release.datestamp
            entry, url = resolve_latest
            unless newer?(entry["datestamp"], from)
                @last_check = monotonic
                return UpdateResult.new(false, from, from)
            end
            rel, how = load_from_entry(entry, url)
            @loaded[rel] = true
            @release = rel
            @loaded_from = how
            @last_error = nil
            @last_check = monotonic
            log(:info, "updated from #{from} to #{rel.datestamp}")
            UpdateResult.new(true, from, rel.datestamp)
        end
    end

    # Writes a release into a folder the caller chooses (spec §4.3.2): the
    # data files of formats, with OTC_{D}.meta.json for jsonl, and always
    # OTC_{D}.sha256; all of them or none. Returns the paths written, in that
    # order with the .sha256 last; a file already there with the same content
    # is left alone and is not in the list.
    def download(release = :latest, to:, formats: [:jsonl], overwrite: false)
        check_open!
        want = check_release_arg(release)
        raise InvalidArgumentError, "to must be a String path" unless to.is_a?(String) && !to.empty?
        raise InvalidArgumentError, "formats must be an Array" unless formats.is_a?(Array) && !formats.empty?
        formats = formats.map { |f| check_enum(f, FORMATS, "format") }.uniq
        check_bool(overwrite, "overwrite")
        Downloader.new(self, want, File.expand_path(to), formats, overwrite).run
    end

    # Hashes the loaded files again and compares them with OTC_{D}.sha256.
    # A client on a file with no .sha256 next to it has nothing to compare
    # with: checksum_mismatch (CR D20).
    def verify
        check_open!
        if @loaded_from == :file_unverified
            raise ChecksumError.new("no OTC_#{@release.datestamp}.sha256 next to the file", file: @file, expected: nil, actual: nil)
        end
        @release.send(:verify)
    end

    # Datestamps in the cache, newest first.
    def cached_releases
        check_open!
        cache.cached_releases
    end

    # Removes all but the newest keep releases from the cache. It never
    # removes the loaded release, a release this client loaded before an
    # update that the caller still holds, or a release that another process
    # holds the lock of. It also removes release directories that never got
    # a .verified (failed downloads) and that no one holds. Returns the
    # datestamps removed, newest first; CacheError when one cannot be removed.
    def prune(keep: 3)
        check_open!
        raise InvalidArgumentError, "keep must be an Integer >= 0" unless keep.is_a?(Integer) && keep >= 0
        protect = held_datestamps
        removed = cache.cached_releases.drop(keep).reject { |d| protect.include?(d) }.select do |d|
            cache.remove_release(d).tap { |ok| log(:info, "prune: #{d} is locked by another process; kept") unless ok }
        end
        cache.partial_releases.each do |d|
            next if protect.include?(d)
            log(:info, "prune: removed the incomplete release directory #{d}") if cache.remove_release(d)
        end
        removed
    end

    # Closes the client and every Release it loaded (stream mode holds a file
    # handle per release). After close every query and call is io "the
    # release is closed" (CR D21). A second close does nothing.
    def close
        @lock.synchronize do
            return nil if @closed
            @closed = true
            ([@release] + @loaded.keys).compact.uniq.each { |r| r.send(:close) }
        end
        nil
    end

    # ---- queries, forwarded to the current release (spec §4.4–§4.7)

    %i[station require_station tombstone station_by_alias stations iter_stations each_station search near nearest
       reference_station subordinates_of attribution].each do |name|
        define_method(name) do |*args, **kw, &blk|
            check_open!
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
        @cache ||= Cache.new(@cache_dir || Cache.default_root, logger: @logger)
    end

    # The latest pointer: [entry, url]. OTC_latest-f1.json, then
    # OTC_latest.json on a 404 only.
    def fetch_latest_pointer
        names = SUPPORTED_FORMAT_MAJORS.sort.reverse.map { |m| "OTC_latest-f#{m}.json" } + ["OTC_latest.json"]
        names.each do |name|
            doc = fetch_pointer_doc(name, missing: :nil)
            next if doc.nil?
            return [check_entry!(doc, name), @base_url + name]
        end
        raise ReleaseNotFoundError, "no latest pointer at #{@base_url}"
    end

    # The newest release this SDK reads: [entry, url] (spec §5.2 steps 2 and
    # 2a, §7.4). The pointer's release when it is readable; otherwise one GET
    # of OTC_index.json and its newest readable entry. None: reader_too_old
    # when a release of a supported major exists, else unsupported_format.
    def resolve_latest
        entry, url = fetch_latest_pointer
        return [entry, url] if readable_entry?(entry)
        index_url = @base_url + "OTC_index.json"
        doc = fetch_pointer_doc("OTC_index.json", missing: :nil)
        list = doc ? index_entries(doc) : []
        pick = list.select { |e| readable_entry?(e) }.max_by { |e| Cache.datestamp_key(e["datestamp"]) }
        return [pick, index_url] if pick
        too_new = ([entry] + list).find { |e| Release.supported_major?(e["format_version"]) }
        if too_new
            raise ReaderTooOldError, "release #{too_new['datestamp']} needs a reader for format " \
                                     "#{too_new['min_reader_version']}; this SDK reads format #{SUPPORTED_FORMAT_VERSION}"
        end
        raise UnsupportedFormatError, "the latest release has format #{entry['format_version']}, not supported by this " \
                                      "SDK (supported majors: #{SUPPORTED_FORMAT_MAJORS.join(', ')})"
    end

    # The newest cached release this SDK reads, or nil. With usable: true,
    # only one this client's mode can load.
    def newest_cached(usable: true)
        index = cached_index
        cache.cached_releases.find do |d|
            cached_readable?(d, cache.verified(d), index[d]) && (!usable || usable_cached?(d))
        end
    end

    def release_info(entry, pointer_url)
        files = Array(entry["files"]).map do |f|
            FileInfo.new(name: f["name"], url: f["url"] && resolve(pointer_url, f["url"]), size: f["size"], sha256: f["sha256"])
        end.sort_by(&:name)
        ReleaseInfo.new(entry, files)
    end

    # The absolute URL of a files[] url (spec §4.3.1). A url that is not a
    # URL is invalid_release.
    def resolve(base, ref)
        URI.join(base, ref).to_s
    rescue URI::Error, TypeError => e
        raise InvalidReleaseError, "bad url #{ref.inspect} in a release entry: #{e.message}"
    end

    def log(level, msg)
        @logger&.public_send(level, "opentideconstants: #{msg}")
    end

    private :http, :base_url, :offline, :cache, :fetch_latest_pointer, :resolve_latest, :newest_cached, :release_info,
            :resolve, :log

    private

    def monotonic
        Process.clock_gettime(Process::CLOCK_MONOTONIC)
    end

    # The datestamps prune must keep: the loaded release and every release
    # this client loaded that is still reachable (a caller may hold it,
    # spec §4.3 update). A client on a file keeps no cached release.
    def held_datestamps
        return [] if @file
        ([@release] + @loaded.keys).compact.map(&:datestamp).uniq
    end

    def check_open!
        raise FileError.new("the release is closed", path: @file) if @closed
    end

    # The automatic update (spec §5.6): at most once per update_interval, in
    # the first query after it. A failure keeps the current release, is
    # logged and is kept in last_error; it never breaks the query.
    def maybe_auto_update
        return unless @auto_update && @requested == :latest && @file.nil? && !@offline && !@closed
        return if monotonic - @last_check < @update_interval
        begin
            update!
        rescue Error => e
            @last_check = monotonic
            @last_error = e
            log(:warn, "automatic update failed: #{e.message}")
        rescue StandardError => e
            @last_check = monotonic
            @last_error = Error.new("automatic update failed: #{e.class}: #{e.message}")
            log(:warn, @last_error.message)
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

    # True when this SDK reads the release of a pointer or index entry.
    def readable_entry?(entry)
        return false unless entry.is_a?(Hash) && Release.supported_major?(entry["format_version"])
        mrv = entry["min_reader_version"]
        mrv.nil? || Release.readable_version?(mrv)
    end

    # The checked entries of OTC_index.json; invalid_release when releases
    # is missing or an entry is malformed.
    def index_entries(doc)
        raise InvalidReleaseError, "OTC_index.json has no releases list" unless doc.is_a?(Hash) && doc["releases"].is_a?(Array)
        doc["releases"].map { |e| check_entry!(e, "OTC_index.json") }
    end

    # Checks a pointer or index entry from the server (spec §4.2, §5.2): an
    # object with a valid datestamp, and files (if any) whose elements are
    # objects with a String name and, if given, a String url and sha256 and
    # an Integer size. Returns the entry.
    def check_entry!(entry, source)
        raise InvalidReleaseError, "#{source}: an entry is not an object" unless entry.is_a?(Hash)
        d = entry["datestamp"]
        raise InvalidReleaseError, "#{source}: bad datestamp #{d.inspect}" unless d.is_a?(String) && d.match?(DATESTAMP_RE)
        files = entry["files"]
        return entry if files.nil?
        raise InvalidReleaseError, "#{source}: files of #{d} is not a list" unless files.is_a?(Array)
        files.each do |f|
            next if f.is_a?(Hash) && f["name"].is_a?(String) && [f["url"], f["sha256"]].all? { |v| v.nil? || v.is_a?(String) } &&
                    (f["size"].nil? || f["size"].is_a?(Integer))
            raise InvalidReleaseError, "#{source}: a files entry of #{d} is malformed: #{f.inspect[0, 120]}"
        end
        entry
    end

    # The entries of the cached OTC_index.json by datestamp ({} if none).
    def cached_index
        cached = cached_pointer("OTC_index.json")
        return {} unless cached
        index_entries(cached[0]).to_h { |e| [e["datestamp"], e] }
    rescue InvalidReleaseError
        {}
    end

    # Whether a cached release is readable, by its .verified, else the cached
    # index entry, else its .meta.json. Unknown counts as readable (the load
    # then checks it).
    def cached_readable?(d, ver, index_entry)
        fv = ver&.dig("format_version") || index_entry&.dig("format_version")
        mrv = ver&.dig("min_reader_version") || index_entry&.dig("min_reader_version")
        if fv.nil? || mrv.nil?
            meta = cached_meta(d)
            fv ||= meta["format_version"]
            mrv ||= meta["release"].is_a?(Hash) ? meta["release"]["min_reader_version"] : nil
        end
        (fv.nil? || Release.supported_major?(fv)) && (mrv.nil? || Release.readable_version?(mrv))
    end

    # The format_version and release of a .json release file, as a Hash
    # ({} when it cannot be read; the load then checks it).
    def release_versions(path)
        doc = JSON.parse(File.read(path, mode: "rb").force_encoding(Encoding::UTF_8))
        doc.is_a?(Hash) ? doc.slice("format_version", "release") : {}
    rescue JSON::ParserError, EncodingError, SystemCallError, IOError
        {}
    end

    # The cached .meta.json of release d ({} when it is not there or not a
    # JSON object; FileError when it cannot be read).
    def cached_meta(d)
        text = cache.read_file(File.join(cache.release_dir(d), "OTC_#{d}.meta.json"))
        doc = text ? JSON.parse(text.force_encoding(Encoding::UTF_8)) : {}
        doc.is_a?(Hash) ? doc : {}
    rescue JSON::ParserError, EncodingError
        {}
    end

    # check_for_update: a conditional GET of OTC_latest.json; a release there
    # with a major newer than every supported one sets newer_format_major,
    # else it is nil (spec §7.4). When the check fails (a network error, a
    # malformed entry), the value from before stays (CR D10).
    def check_newer_major
        entry = fetch_pointer_doc("OTC_latest.json", missing: :nil)
        if entry.nil?
            @newer_format_major = nil
            return
        end
        key = entry.is_a?(Hash) ? Release.version_key(entry["format_version"]) : nil
        raise InvalidReleaseError, "OTC_latest.json: bad format_version #{entry.is_a?(Hash) ? entry['format_version'].inspect : nil}" unless key
        if key[0] > SUPPORTED_FORMAT_MAJORS.max
            @newer_format_major = key[0]
            log(:warn, "a newer format (#{key[0]}) exists; upgrade opentideconstants to read it")
        else
            @newer_format_major = nil
        end
    rescue NetworkError, InvalidReleaseError => e
        log(:warn, "cannot check OTC_latest.json for a newer format: #{e.message}")
    end

    # Keeps the version DOI of an entry in the .verified of its cached release.
    # An entry whose DOI is null never erases a known one (CR2 DR11).
    def note_version_doi(entry)
        d = entry["datestamp"]
        return unless d.is_a?(String) && d.match?(DATESTAMP_RE) && !entry["zenodo_version_doi"].nil?
        cache.note_version_doi(d, entry["zenodo_version_doi"])
    end

    def newer?(a, b)
        (Cache.datestamp_key(a) <=> Cache.datestamp_key(b)) == 1
    end

    # GETs a pointer or index file with If-None-Match and returns it parsed
    # (spec §5.2 step 2). A 200 is parsed before it is cached: a body that is
    # not JSON (a captive portal or a proxy error page) is a network error
    # (CR D8) and leaves the cached copy alone. A failure to cache it is
    # logged, not raised. A 304 with no usable cached copy is asked again
    # without the ETag. Offline it uses the cached copy, or raises
    # OfflineError. missing: :nil returns nil on a 404 (the latest pointers
    # and the index lookup of §5.2 step 2a; a network error is raised, and the
    # caller's open falls back to a cached release). missing: :offline is for
    # releases: a 404 is release_not_found, and after a network error with
    # on_network_error :use_cache it uses the cached copy.
    def fetch_pointer_doc(name, missing:)
        url = @base_url + name
        cached = cached_pointer(name)
        if @offline
            return cached[0] if cached
            raise OfflineError, "offline and #{name} is not cached"
        end
        res = @http.get(url, etag: cached && cached[1])
        res = @http.get(url) if res.status == 304 && cached.nil?
        case res.status
        when 304
            raise NetworkError.new("#{url}: HTTP 304 to a request without If-None-Match", url: url, status: 304) unless cached
            log(:debug, "#{name}: 304, the cached copy is current")
            cached[0]
        when 200
            doc = parse_pointer_body(url, res.body)
            store_pointer(name, res.body, res.etag)
            log(:debug, "#{name}: 200")
            doc
        when 404
            return nil if missing == :nil
            raise ReleaseNotFoundError, "#{url}: HTTP 404"
        else
            raise NetworkError.new("#{url}: HTTP #{res.status}", url: url, status: res.status)
        end
    rescue NetworkError => e
        raise unless missing == :offline && @on_network_error == :use_cache && cached
        log(:warn, "#{e.message}; using the cached #{name}")
        cached[0]
    end

    # The cached copy of a pointer or index file as [doc, etag], or nil. A
    # copy that is not JSON counts as none, so its ETag is not sent.
    def cached_pointer(name)
        cached = cache.read_pointer(name)
        cached && [JSON.parse(cached[0]), cached[1]]
    rescue JSON::ParserError, EncodingError
        log(:warn, "the cached #{name} is not JSON; ignoring it")
        nil
    end

    # A 200 pointer or index body that is not JSON is a network error (CR D8).
    def parse_pointer_body(url, body)
        JSON.parse(body.dup.force_encoding(Encoding::UTF_8))
    rescue JSON::ParserError, EncodingError => e
        raise NetworkError.new("#{url}: HTTP 200 with a body that is not JSON (#{e.message[0, 100]})", url: url, status: 200)
    end

    # Stores a pointer or index file and its ETag. The cached copy only saves
    # work, so a failure is logged, not raised (spec §5.2, CR D8).
    def store_pointer(name, body, etag)
        cache.write_pointer(name, body, etag)
    rescue CacheError => e
        log(:warn, "cannot cache #{name}: #{e.message}")
    end

    # spec §5.2
    def open_latest
        if @offline
            d = newest_cached
            raise OfflineError, "offline and no release is cached in #{cache.root}" unless d
            @release = load_cached(d) or raise CacheError, "release #{d} left the cache while it was opened"
            @loaded_from = :cache
            return
        end
        cache.ensure_dir(cache.releases_dir)
        begin
            entry, url = resolve_latest
            @release, @loaded_from = load_from_entry(entry, url)
        rescue NetworkError => e
            d = @on_network_error == :use_cache ? newest_cached : nil
            raise unless d
            log(:warn, "#{e.message}; using the cached release #{d}")
            @release = load_cached(d) or raise e
            @loaded_from = :cache_after_error
            @last_error = e
        end
    end

    def open_pinned(d)
        if (rel = load_cached_unless_corrupt(d))
            @release = rel
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
        raise InvalidReleaseError, "bad datestamp #{d.inspect} in the pointer" unless d.is_a?(String) && d.match?(DATESTAMP_RE)
        if (rel = load_cached_unless_corrupt(d))
            note_version_doi(entry)
            return [rel, :cache]
        end
        [fetch_release(d, entry, url), :download]
    end

    # The cached release d when it is usable, else nil. A cached file that
    # fails verify_on_open is deleted (load_cached does it), and then, when
    # online, nil, so the caller downloads it again (spec §4.8).
    def load_cached_unless_corrupt(d)
        return nil unless usable_cached?(d)
        load_cached(d)
    rescue ChecksumError => e
        raise if @offline
        log(:warn, "#{e.message}; downloading #{d} again")
        nil
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

    # Loads cached release d, or nil when it is no longer usable (another
    # process removed it after the caller checked it).
    def load_cached(d)
        ver = cache.verified(d)
        names = ver && wanted_files(d).find { |ns| ns.all? { |n| cache.file_ok?(d, n, ver) } }
        return nil unless names
        dir = cache.release_dir(d)
        paths = names.map { |n| File.join(dir, n) }
        checks = paths.to_h { |p| [p, ver["files"][File.basename(p)]["sha256"]] }
        files = ver["files"].map do |name, row|
            FileInfo.new(name: name, url: row["url"], size: row["size"], sha256: row["sha256"])
        end
        # With verify_on_open the load hashes each file from the bytes it reads (spec §5.3).
        opts = { mode: @mode, files: files, checks: checks, zenodo_version_doi: ver["zenodo_version_doi"], verify: @verify_on_open,
                 logger: @logger }
        return Reader.load(paths.first, **opts) unless @mode == :stream
        index = fresh_stream_index(d, ver, paths.first)
        if index
            begin
                return Reader.load(paths.first, index: index, on_bad_index: ->(msg) { drop_stream_index(d, msg) }, **opts)
            rescue InvalidReleaseError => e
                log(:warn, "the stream index for #{d} cannot be used (#{e.message}); rebuilding it")
            end
        end
        rows = []
        rel = Reader.load(paths.first, index_rows: rows, **opts)
        write_stream_index(d, rel, rows, ver, paths.first)
        rel
    rescue ChecksumError => e
        # A cached file that fails its check is deleted (spec §4.8 checksum_mismatch).
        log(:warn, "#{e.message}; deleting the cached #{File.basename(e.file.to_s)}")
        cache.remove_file(e.file) if e.file
        raise
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
        return nil unless index_in_bounds?(idx["stations"], idx["jsonl_size"])
        idx["stations"]
    rescue JSON::ParserError, EncodingError, SystemCallError, IOError
        nil
    end

    # The bounds check of a fresh index (spec §6.2, CR D4): each length > 0,
    # offset + length <= the .jsonl size, and offsets strictly increasing.
    def index_in_bounds?(entries, size)
        last = -1
        entries.all? do |e|
            ok = e["length"].positive? && e["offset"] > last && e["offset"] + e["length"] <= size
            last = e["offset"]
            ok
        end
    end

    # Deletes the stream index of release d after a line did not match its
    # entry (spec §6.2, CR D4); the next open rebuilds it.
    def drop_stream_index(d, msg)
        log(:warn, "#{msg}; deleting index-v1.json of #{d}")
        cache.remove_file(File.join(cache.release_dir(d), "index-v1.json"))
    rescue CacheError => e
        log(:warn, e.message)
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
            next if usable_cached?(d)
            download_into_cache(d, entry, pointer_url)
        end
        load_cached(d) or raise CacheError, "release #{d} left the cache while it was opened"
    end

    def download_into_cache(d, entry, pointer_url)
        dir = cache.release_dir(d)
        rows, sha_bytes = Downloader.fetch_sha256(self, d, entry, pointer_url)
        pointer_files = entry ? Array(entry["files"]).to_h { |f| [f["name"], f] } : {}
        # Eager mode reads the .json, from .json.gz when the release has one.
        gz = "OTC_#{d}.json.gz"
        json = "OTC_#{d}.json"
        need = @mode == :stream ? %W[OTC_#{d}.jsonl OTC_#{d}.meta.json] : [rows[gz] ? gz : json, json]
        need.uniq.each do |name|
            # Check the list before any download (a file it does not list cannot be checked).
            raise ChecksumError.new("#{name} is not listed in OTC_#{d}.sha256", file: name, expected: nil, actual: nil) unless rows[name]
        end
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
        # Only the keys the entry has: a missing or null zenodo_version_doi keeps the stored one (CR2 DR11).
        info = entry ? entry.slice(*Cache::VERIFIED_INFO) : {}
        info.delete("zenodo_version_doi") if info["zenodo_version_doi"].nil?
        if @mode == :stream
            %W[OTC_#{d}.jsonl OTC_#{d}.meta.json].each do |name|
                size = Downloader.fetch_checked(self, url_of.call(name), dir, File.join(dir, name), name, rows[name],
                                                pointer_files.dig(name, "size"))
                verified[name]["size"] = size
            end
        elsif !rows[gz]
            size = Downloader.fetch_checked(self, url_of.call(json), dir, File.join(dir, json), json, rows[json],
                                            pointer_files.dig(json, "size"))
            verified[json]["size"] = size
        else
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
        if entry.nil?
            # A pinned download reads no pointer: take the versions from the
            # release's own file (the sidecar, or the .json in eager mode).
            meta = @mode == :stream ? cached_meta(d) : release_versions(File.join(dir, "OTC_#{d}.json"))
            info["format_version"] = meta["format_version"]
            info["min_reader_version"] = meta["release"]["min_reader_version"] if meta["release"].is_a?(Hash)
        end
        cache.write_verified(d, verified, info)
    end
end
