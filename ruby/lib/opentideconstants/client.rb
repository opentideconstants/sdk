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
        @newer_format_major = nil
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
        list = index_entries(fetch_pointer_doc("OTC_index.json", missing: :offline))
        list.each { |e| note_version_doi(e) }
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

    # A release newer than the loaded one, with a supported format major and
    # a readable min_reader_version, or nil (spec §4.3, §5.2 step 2a). It also
    # sets newer_format_major when the server has a release of a newer major.
    def check_for_update
        raise OfflineError, "offline: the latest pointer is not available" if @offline
        entry, url = resolve_latest
        check_newer_major
        info = release_info(entry, url)
        newer?(info.datestamp, @release.datestamp) ? info : nil
    end

    # Downloads and checks the latest release and swaps it in atomically. A
    # Release held from before stays valid.
    def update!
        raise PinnedReleaseError, "the client was opened on a file" if @file
        raise PinnedReleaseError, "the client was opened on release #{@requested}" unless @requested == :latest
        @lock.synchronize do
            from = @release.datestamp
            entry, url = resolve_latest
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

    def cached_meta(d)
        path = File.join(cache.release_dir(d), "OTC_#{d}.meta.json")
        doc = File.file?(path) ? JSON.parse(File.read(path, mode: "rb").force_encoding(Encoding::UTF_8)) : {}
        doc.is_a?(Hash) ? doc : {}
    rescue JSON::ParserError, EncodingError, SystemCallError, IOError
        {}
    end

    # check_for_update: a conditional GET of OTC_latest.json; a release there
    # with a major newer than every supported one sets newer_format_major (spec §7.4).
    def check_newer_major
        @newer_format_major = nil
        entry = fetch_pointer_doc("OTC_latest.json", missing: :nil)
        return if entry.nil?
        key = entry.is_a?(Hash) ? Release.version_key(entry["format_version"]) : nil
        return unless key && key[0] > SUPPORTED_FORMAT_MAJORS.max
        @newer_format_major = key[0]
        log(:warn, "a newer format (#{key[0]}) exists; upgrade opentideconstants to read it")
    rescue NetworkError, InvalidReleaseError => e
        log(:warn, "cannot check OTC_latest.json for a newer format: #{e.message}")
    end

    # Keeps the version DOI of an entry in the .verified of its cached release.
    def note_version_doi(entry)
        d = entry["datestamp"]
        return unless d.is_a?(String) && d.match?(DATESTAMP_RE) && entry.key?("zenodo_version_doi")
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
    # without the ETag. Offline, or after a network error with
    # on_network_error :use_cache, it uses the cached copy. missing: :nil
    # returns nil on a 404; :offline raises OfflineError when offline with no
    # cached copy.
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
            @release = load_cached(d)
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
        raise InvalidReleaseError, "bad datestamp #{d.inspect} in the pointer" unless d.is_a?(String) && d.match?(DATESTAMP_RE)
        if usable_cached?(d)
            note_version_doi(entry)
            return [load_cached(d), :cache]
        end
        [fetch_release(d, entry, url), :download]
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
        doi = ver["zenodo_version_doi"]
        return Reader.load(paths.first, mode: @mode, files: files, checks: checks, zenodo_version_doi: doi) unless @mode == :stream
        index = fresh_stream_index(d, ver, paths.first)
        if index
            begin
                return Reader.load(paths.first, mode: @mode, files: files, checks: checks, index: index, zenodo_version_doi: doi)
            rescue InvalidReleaseError => e
                log(:warn, "the stream index for #{d} cannot be used (#{e.message}); rebuilding it")
            end
        end
        rows = []
        rel = Reader.load(paths.first, mode: @mode, files: files, checks: checks, index_rows: rows, zenodo_version_doi: doi)
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
        info = entry ? %w[format_version min_reader_version zenodo_version_doi].to_h { |k| [k, entry[k]] } : {}
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
        if entry.nil? && @mode == :stream
            # A pinned download reads no pointer: take the versions from the sidecar.
            meta = cached_meta(d)
            info["format_version"] = meta["format_version"]
            info["min_reader_version"] = meta["release"]["min_reader_version"] if meta["release"].is_a?(Hash)
        end
        cache.write_verified(d, verified, info)
    end
end
