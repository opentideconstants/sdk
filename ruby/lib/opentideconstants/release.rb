require "json"
require "zlib"
require "digest"
require "set"

class OpenTideConstants
    # One loaded OTC_{DATESTAMP} release (spec §3, §4.3–§4.7). Immutable: an
    # update of the client swaps in a new Release and leaves this one as it is.
    #
    # In eager mode every station is built at load. In stream mode the release
    # keeps a small index (one entry per station, with the byte offset of its
    # line in the .jsonl file) and builds a Station when a query needs it.
    class Release
        EARTH_RADIUS_KM = 6371.0088
        FILTER_KEYS = %i[country type kind source source_type include_flagged include_fallback].freeze
        # The qc_status values of a set with constants.
        USABLE_QC = %i[ok flagged].freeze
        # The reference links a walk follows (spec §6.2 kind, §4.6 attribution).
        MAX_LINKS = 16

        # A small per-station summary, used by the filters and the indexes.
        # eff_*: the recommended set the Stations give (the effective one under
        # commercial_only, spec §4.2, K-NC DR106); offsets_ref_licence_id: the
        # licence of the station's first set in file order from the offsets'
        # source (noaa), water_level, ok or flagged (the reference set of the
        # one-link offsets path), or nil.
        Entry = Struct.new(:station_id, :name, :folded, :lat, :lon, :type, :country, :kind, :sources,
                           :rec_source_type, :rec_licence_id, :offsets_licence_id, :reference_id,
                           :eff_id, :eff_source_type, :eff_licence_id, :offsets_ref_licence_id,
                           :aliases, :pos, :len, :station, :view, :sets, :offsets, :current_offsets, keyword_init: true)
        # The source of every subordinate_offsets in format 1.0 (spec §4.2, K-NC DR106).
        OFFSETS_SOURCE = "noaa"

        # The metadata: readable after close too (CR2 DR32). Every other
        # method is a query, and after close it is io "the release is
        # closed" (spec §4.2, CR D21).
        attr_reader :datestamp, :created, :format_version, :concept_doi, :zenodo_version_doi, :source_versions,
                    :build_commit, :changelog_url, :files

        # meta: the release document without its stations. stations: an
        # enumerator of [raw_station, pos, len, view]; view (Reader.line_view)
        # when the station came from index-v1.json, else nil. files: [FileInfo]. checks:
        # {path => expected sha256} for #verify. io: the open .jsonl file in
        # stream mode (or nil). zenodo_version_doi: from the pointer or index
        # entry of this datestamp (the release document does not hold it).
        # on_bad_index: called (with the message) when a line read through the
        # stream index is not the station its entry names (spec §6.2, CR D4).
        # logger: where a station with an unknown status is reported, once at
        # load (CR2 DR8).
        # commercial_only: the open option of spec §4.2 (K-NC DR106).
        def initialize(meta:, stations:, mode:, files:, checks:, io: nil, zenodo_version_doi: nil, on_bad_index: nil,
                       logger: nil, commercial_only: false, commercial_basis: :strict, historical_offsets_policy: :fallback)
            @mode = mode
            @commercial_only = commercial_only
            @commercial_basis = commercial_basis.to_s
            @historical_offsets_policy = historical_offsets_policy.to_s
            @meta = meta
            @logger = logger
            @io = io
            @on_bad_index = on_bad_index
            @io_lock = Mutex.new
            @station_cache = {}
            @station_cache_lock = Mutex.new
            @state = { closed: false } # not frozen with the Release: close sets it
            @files = files.sort_by(&:name).freeze
            @checks = checks.freeze
            Util.deep_freeze(meta)
            Release.check_format!(meta)
            rel = meta["release"]
            raise InvalidReleaseError, "release object missing" unless rel.is_a?(Hash) && rel["datestamp"].is_a?(String)
            @datestamp = rel["datestamp"]
            @created = Util.time(rel["created"])
            sv = rel["source_versions"]
            unless sv.nil? || (sv.is_a?(Hash) && sv.values.all?(String))
                raise InvalidReleaseError, "release.source_versions is not an object of strings"
            end
            %w[conventions licences].each do |k|
                list = meta[k]
                next if list.nil?
                id = k == "conventions" ? "convention_id" : "licence_id"
                unless list.is_a?(Array) && list.all? { |x| x.is_a?(Hash) && x[id].is_a?(String) }
                    raise InvalidReleaseError, "#{k} must be a list of objects with a #{id}"
                end
            end
            # The attribution text prints both (spec §4.6, CR2 DR2); a null
            # provider is allowed (CR D2 b).
            Array(meta["licences"]).each do |l|
                Licence.check!(l)
                next if l["attribution"].is_a?(String) && (l["provider"].nil? || l["provider"].is_a?(String))
                raise InvalidReleaseError,
                      "licence #{l['licence_id']}: attribution must be a string and provider a string or null"
            end
            @format_version = meta["format_version"]
            @concept_doi = rel["concept_doi"]
            @zenodo_version_doi = zenodo_version_doi
            @source_versions = (rel["source_versions"] || {}).freeze
            @build_commit = rel["build_commit"]
            @changelog_url = rel["changelog_url"]
            @conventions = Array(meta["conventions"]).map { |c| Convention.new(c) }.freeze
            @licences = Array(meta["licences"]).map { |l| Licence.new(l) }.freeze
            Release.no_repeats!(@conventions.map(&:convention_id), "convention_id")
            Release.no_repeats!(@licences.map(&:licence_id), "licence_id")
            @convention_by_id = @conventions.to_h { |c| [c.convention_id, c] }.freeze
            @licence_by_id = @licences.to_h { |l| [l.licence_id, l] }.freeze
            load_stations(stations)
            freeze
        end

        # Raises unsupported_format unless the format major is supported, and
        # reader_too_old when release.min_reader_version is newer than
        # SUPPORTED_FORMAT_VERSION (§7.4).
        def self.check_format!(meta)
            raise InvalidReleaseError, "not a release document" unless meta.is_a?(Hash)
            fv = meta["format_version"]
            raise InvalidReleaseError, "format_version missing" unless Release.version_key(fv)
            unless Release.supported_major?(fv)
                raise UnsupportedFormatError, "format_version #{fv} is not supported (supported majors: #{SUPPORTED_FORMAT_MAJORS.join(', ')})"
            end
            rel = meta["release"]
            mrv = rel.is_a?(Hash) ? rel["min_reader_version"] : nil
            return if mrv.nil?
            raise InvalidReleaseError, "bad release.min_reader_version #{mrv.inspect}" unless Release.version_key(mrv)
            return if Release.readable_version?(mrv)
            d = rel["datestamp"]
            raise ReaderTooOldError, "release #{d} needs a reader for format #{mrv}; this SDK reads format #{SUPPORTED_FORMAT_VERSION}"
        end

        # invalid_release when a value appears twice (spec §6.1, CR D5).
        def self.no_repeats!(values, what)
            seen = Set.new
            values.each do |v|
                raise InvalidReleaseError, "#{what} #{v.inspect} appears twice" unless seen.add?(v)
            end
        end

        # [major, minor] of a "MAJOR.MINOR" format version, or nil.
        def self.version_key(v)
            m = /\A(\d+)\.(\d+)\z/.match(v.to_s) if v.is_a?(String)
            m && [m[1].to_i, m[2].to_i]
        end

        def self.supported_major?(format_version)
            key = version_key(format_version)
            !key.nil? && SUPPORTED_FORMAT_MAJORS.include?(key[0])
        end

        # True when this SDK reads a release whose min_reader_version is v.
        def self.readable_version?(v)
            key = version_key(v)
            !key.nil? && (key <=> version_key(SUPPORTED_FORMAT_VERSION)) <= 0
        end

        # ---- release-level values

        def historical_offsets_policy
            check_open!
            @historical_offsets_policy.to_sym
        end

        def conventions
            check_open!
            @conventions
        end

        def licences
            check_open!
            @licences
        end

        def constituent_names
            check_open!
            @constituent_names
        end

        def convention(convention_id)
            check_open!
            @convention_by_id[convention_id]
        end

        def licence(licence_id)
            check_open!
            @licence_by_id[licence_id]
        end

        def station_count
            check_open!
            @entries.size
        end

        def tombstone_count
            check_open!
            @tombstones.size
        end

        def stats
            check_open!
            count = ->(values) { values.compact.tally.sort_by { |k, _| k.to_s }.to_h.freeze }
            Stats.new(type: count.call(@entries.map(&:type)), kind: count.call(@entries.map(&:kind)),
                      country: count.call(@entries.map(&:country)), source: count.call(@set_sources),
                      qc_status: count.call(@set_qc))
        end

        # The dataset citation (spec §4.6); the year is the first four digits
        # of the datestamp. It links the concept DOI, and adds the version DOI
        # when the release has its own Zenodo version.
        def citation
            link = @concept_doi ? "https://doi.org/#{@concept_doi}" : default_url
            version = @zenodo_version_doi ? " (version DOI: https://doi.org/#{@zenodo_version_doi})" : ""
            "OpenTideConstants contributors (#{@datestamp[0, 4]}). OpenTideConstants, release #{@datestamp} [Data set]. #{link}#{version}"
        end

        # The CC BY 4.0 attribution text for what an app shows (spec §4.6). With
        # no stations, or an empty list, every licence in the release. A
        # Station that is not one of this release's is invalid_argument, never
        # skipped (CR D2). A licence with no provider prints its attribution
        # alone and is never merged with another.
        def attribution(stations = nil)
            check_open!
            raise InvalidArgumentError, "stations must be an Array of Station" unless stations.nil? || stations.is_a?(Array)
            co = @commercial_only
            ids = if stations.nil? || stations.empty?
                      # with commercial_only, only the commercial licences (K-NC DR106)
                      @licences.select { |l| !co || l.commercial_use == true }.map(&:licence_id)
                  else
                      out = Set.new
                      stations.each do |st|
                          e = validate_attribution_station_owner(st)
                          if co # the licences of the station's tide source (spec §4.2, §4.6, K-NC DR106)
                              out.merge(tide_source_licences(e))
                              next
                          end
                          out << e.rec_licence_id if e.rec_licence_id
                          out.merge(chain_licences(e))
                      end
                      out.to_a
                  end
            seen = Set.new
            parts = []
            ids.uniq.sort.each do |lid|
                lic = @licence_by_id[lid]
                next if lic.nil?
                if lic.provider.nil?
                    parts << lic.attribution.to_s
                    next
                end
                next if seen.include?(lic.provider)
                seen << lic.provider
                parts << "#{lic.provider}: #{lic.attribution}"
            end
            ident = @concept_doi ? "doi:#{@concept_doi}" : default_url
            head = "Tidal constants: OpenTideConstants #{@datestamp}, #{ident}, CC BY 4.0."
            # An empty scope: the dataset header alone (spec §4.6, K-NC DR106).
            return head if ids.empty?
            text = "#{head} Sources: " + parts.join("; ")
            # The non-commercial notice (spec §4.6, K-NC DR105): once, then one
            # entry per non-commercial licence in scope, by licence_id; a nil
            # provider gives the licence_id.
            nc = ids.uniq.sort.map { |lid| @licence_by_id[lid] }.reject { |l| l.nil? || l.commercial_use == true }
            unless nc.empty?
                text += ". Non-commercial use only: " +
                        nc.map { |l| "#{l.provider.nil? ? l.licence_id : l.provider} (#{l.spdx}, #{l.terms_url})" }.join("; ")
            end
            text
        end

        # The licences of a station's tide source under commercial_only (spec
        # §4.2, K-NC DR106): its effective recommended set; else the one-link
        # offsets path (the reference station's first set from the offsets'
        # source), usable only when the offsets' licence and that set's licence
        # allow commercial use; else none (no usable tides).
        def tide_source_licences(e)
            return [e.eff_licence_id] if e.eff_id
            return [] if e.reference_id.nil? && e.offsets_licence_id.nil?
            ref = @by_id[e.reference_id]
            return [] if ref.nil? || ref.offsets_ref_licence_id.nil?
            out = [ref.offsets_ref_licence_id]
            out << e.offsets_licence_id if e.offsets_licence_id
            out.all? { |lid| @licence_by_id[lid].commercial_use == true } ? out : []
        end
        private :tide_source_licences

        # Original pure argument phases; query/discovery bodies stay on Release.
        module QueryArguments
            private

            def validate_alias_arguments(system, alias_id)
                unless (system.is_a?(String) || system.is_a?(Symbol)) && alias_id.is_a?(String)
                    raise InvalidArgumentError, "system must be a String or Symbol and alias_id a String"
                end
            end

            def validate_search_arguments(name, limit, match)
                raise InvalidArgumentError, "name must be a String" unless name.is_a?(String)
                check_limit!(limit)
                unless match.nil? || match.to_s == "exact"
                    raise InvalidArgumentError, "match must be nil or :exact"
                end
                q = Fold.fold(utf8_query(name))
                raise InvalidArgumentError, "the query is empty" if q.empty?
                q
            end

            def validate_near_arguments(lat, lon, radius_km, limit)
                check_point!(lat, lon)
                unless real?(radius_km) && radius_km >= 0
                    raise InvalidArgumentError, "radius_km must be a number >= 0"
                end
                check_limit!(limit)
            end

            def validate_nearest_arguments(lat, lon, max_km)
                check_point!(lat, lon)
                unless max_km.nil? || (real?(max_km) && max_km >= 0)
                    raise InvalidArgumentError, "max_km must be nil or a number >= 0"
                end
            end

            def validate_filter_arguments(filters)
                unknown = filters.keys - FILTER_KEYS
                raise InvalidArgumentError, "unknown filter #{unknown.first}" unless unknown.empty?
                f = {}
                filters.each do |k, v|
                    if %i[include_flagged include_fallback].include?(k)
                        raise InvalidArgumentError, "#{k} must be true or false" unless v == true || v == false
                        f[k] = v
                        next
                    end
                    next if v.nil?
                    raise InvalidArgumentError, "filter #{k} must be a String or Symbol" unless v.is_a?(String) || v.is_a?(Symbol)
                    f[k] = v.to_s
                end

                f
            end

            def check_id!(id)
                raise InvalidArgumentError, "station_id must be a String" unless id.is_a?(String)
            end

            def check_limit!(limit)
                return if limit.nil?
                raise InvalidArgumentError, "limit must be nil or an Integer >= 1" unless limit.is_a?(Integer) && limit >= 1
            end

            def real?(v)
                Release.real?(v)
            end

            def check_point!(lat, lon)
                raise InvalidArgumentError, "lat must be a number in [-90, 90]" unless real?(lat) && lat >= -90 && lat <= 90
                raise InvalidArgumentError, "lon must be a number in [-180, 180]" unless real?(lon) && lon >= -180 && lon <= 180
            end

            def utf8_query(name)
                q = name.encoding == Encoding::UTF_8 ? name : name.encode(Encoding::UTF_8)
                raise InvalidArgumentError, "name is not valid UTF-8" unless q.valid_encoding?
                q
            rescue EncodingError
                raise InvalidArgumentError, "name cannot be converted to UTF-8"
            end

        end
        include QueryArguments
        private_constant :QueryArguments

        # ---- station queries (spec §4.4)

        def station(station_id)
            check_open!
            check_id!(station_id)
            e = @by_id[station_id]
            e && materialize(e)
        end

        def require_station(station_id)
            check_open!
            check_id!(station_id)
            e = @by_id[station_id]
            return materialize(e) if e
            t = @tomb_by_id[station_id]
            raise StationRemovedError.new("station #{station_id} was removed in #{t.removed_in}", tombstone: t) if t
            raise StationNotFoundError, "no station #{station_id}"
        end

        def tombstone(station_id)
            check_open!
            check_id!(station_id)
            @tomb_by_id[station_id]
        end

        def station_by_alias(system, alias_id)
            check_open!
            validate_alias_arguments(system, alias_id)
            sid = @aliases.dig(system.to_s, alias_id)
            sid && station(sid)
        end

        def stations(**filters)
            check_open!
            filter(filters).map { |e| materialize(e) }.freeze
        end

        # Each step checks that the release is not closed, also for an
        # enumerator made before close (CR2 DR32).
        def iter_stations(**filters)
            check_open!
            list = filter(filters)
            return enum_for(:iter_stations, **filters) unless block_given?
            list.each do |e|
                check_open!
                yield materialize(e)
            end
            check_open!
            self
        end
        alias each_station iter_stations

        def search(name: nil, limit: nil, match: nil, **filters)
            check_open!
            q = validate_search_arguments(name, limit, match)
            exact = !match.nil?
            ranked = []
            filter(filters).each do |e|
                n = e.folded
                rank = if n == q then 0
                       elsif exact then nil
                       elsif n.start_with?(q) then 1
                       elsif word_start?(n, q) then 2
                       elsif n.include?(q) then 3
                       end
                ranked << [rank, n, e.station_id, e] if rank
            end
            ranked.sort_by! { |r| r[0, 3] }
            ranked = ranked.first(limit) if limit
            ranked.map { |r| materialize(r[3]) }.freeze
        end

        def near(lat: nil, lon: nil, radius_km: nil, limit: nil, **filters)
            check_open!
            validate_near_arguments(lat, lon, radius_km, limit)
            hits = distances(lat, lon, filters).select { |d, _| d <= radius_km }
            hits = hits.first(limit) if limit
            hits.map { |d, e| Nearby.new(materialize(e), d) }.freeze
        end

        def nearest(lat: nil, lon: nil, max_km: nil, **filters)
            check_open!
            validate_nearest_arguments(lat, lon, max_km)
            d, e = distances(lat, lon, filters).first
            return nil if e.nil? || (max_km && d > max_km)
            Nearby.new(materialize(e), d)
        end

        def reference_station(station)
            check_open!
            own_station!(station, "reference_station")
            off = station.subordinate_offsets
            off && off.reference_station_id && station(off.reference_station_id)
        end

        def subordinates_of(station)
            check_open!
            own_station!(station, "subordinates_of")
            (@subordinates[station.station_id] || []).map { |e| materialize(e) }.freeze
        end

        def inspect
            "#<OpenTideConstants::Release #{@datestamp} format #{@format_version} #{@entries.size} stations (#{@mode})>"
        end

        def self.sha256_file(path)
            Digest::SHA256.file(path).hexdigest
        rescue SystemCallError => e
            raise FileError.new("cannot read #{path}: #{e.message}", path: path)
        end

        private

        # Used by OpenTideConstants#verify and #close (not public on Release:
        # the API manifest has them on the client only).
        # Hashes the release files again and compares them with rows, the
        # {name => sha256} of OTC_{D}.sha256 that the client reads again
        # (spec §4.3). A file with no row is checksum_mismatch.
        def verify(rows)
            raise ChecksumError.new("release #{@datestamp}: no files to verify", file: nil, expected: nil, actual: nil) if @checks.empty?
            @checks.each_key do |path|
                expected = rows[File.basename(path)]
                actual = Release.sha256_file(path)
                next if actual == expected
                what = expected ? "SHA-256 mismatch" : "not listed in OTC_#{@datestamp}.sha256"
                raise ChecksumError.new("#{File.basename(path)}: #{what}", file: path, expected: expected, actual: actual)
            end
            # A .json.gz: its decompressed bytes against the .json row, as at
            # open (spec §5.3, CR3 DR77).
            @checks.each_key do |path|
                next unless path.end_with?(".json.gz")
                Reader.need_rows!(path, [path], rows, "OTC_#{@datestamp}.sha256")
                Reader.check_json_bytes!(path, Reader.gunzip(path), rows[File.basename(path).delete_suffix(".gz")])
            end
            true
        end

        # The paths of the data files this release was opened from.
        def opened_paths
            @checks.keys
        end

        def close
            @io_lock.synchronize do
                @state[:closed] = true
                @io.close if @io && !@io.closed?
            end
            @station_cache_lock.synchronize { @station_cache.clear }
            nil
        end

        def check_open!
            raise FileError.new("the release is closed", path: @io&.path) if @state[:closed]
        end

        # The resolved kind of each active station, {station_id => "tide" | "current" | "other" | nil},
        # for the stream index (spec §6.2). Used by the client.
        def index_kinds
            @entries.to_h { |e| [e.station_id, e.kind&.to_s] }
        end

        def default_url
            "https://data.opentideconstants.org/OTC_#{@datestamp}.json"
        end

        # A Station that is an active station of this release, as attribution
        # checks it (CR D2 a); nil, an unknown station or another release's
        # Station is invalid_argument (CR2 DR24).
        def own_station!(station, what)
            raise InvalidArgumentError, "#{what}: station must be a Station" unless station.is_a?(Station)
            return if @by_id.key?(station.station_id) && station.instance_variable_get(:@origin).equal?(self)
            raise InvalidArgumentError, "#{what}: station #{station.station_id} is not a station of release #{@datestamp}"
        end

        def validate_attribution_station_owner(station)
            raise InvalidArgumentError, "stations must be an Array of Station" unless station.is_a?(Station)
            entry = @by_id[station.station_id]
            unless entry && station.instance_variable_get(:@origin).equal?(self)
                raise InvalidArgumentError, "station #{station.station_id} is not a station of release #{@datestamp}"
            end
            entry
        end


        # limit: nil for no limit, else an Integer of 1 or more (spec §4.4, CR D36).

        # A finite real number (not a Complex, NaN or infinity).

        # A real number that is finite as a double: an Integer too large for a
        # double (400 digits) is not.
        def self.real?(v)
            v.is_a?(Numeric) && v.real? && v.to_f.finite?
        end


        # The query as a valid UTF-8 String; invalid_argument when it is not one.

        def word_start?(n, q)
            i = n.index(q)
            while i
                return true if i.positive? && n[i - 1] == " "
                i = n.index(q, i + 1)
            end
            false
        end

        def distances(lat, lon, filters)
            filter(filters).map { |e| [haversine(lat, lon, e.lat, e.lon), e] }
                           .sort_by { |d, e| [d, e.station_id] }
        end

        def haversine(lat1, lon1, lat2, lon2)
            rad = Math::PI / 180
            p1 = lat1 * rad
            p2 = lat2 * rad
            dp = p2 - p1
            dl = (lon2 - lon1) * rad
            a = Math.sin(dp / 2)**2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2)**2
            2 * EARTH_RADIUS_KM * Math.asin([1.0, Math.sqrt(a)].min)
        end

        def filter(filters)
            f = validate_filter_arguments(filters)

            # A field that is null matches no filter value, also not "".
            same = ->(value, want) { !value.nil? && value.to_s == want }
            @entries.select do |e|
                (!f.key?(:country) || same.call(e.country, f[:country])) &&
                    (!f.key?(:type) || same.call(e.type, f[:type])) &&
                    (!f.key?(:kind) || same.call(e.kind, f[:kind])) &&
                    eligible_paths(e, f.fetch(:include_flagged, false), f.fetch(:include_fallback, false)).any? do |cs|
                        (!f.key?(:source) || same.call(cs["source"], f[:source])) &&
                            (!f.key?(:source_type) || same.call(Util.enum(cs["source_type"], ENUMS[:source_type]), f[:source_type]))
                    end
            end
        end

        def materialize(e)
            check_open!
            return e.station if e.station
            cached = @station_cache_lock.synchronize do
                station = @station_cache.delete(e.station_id)
                @station_cache[e.station_id] = station if station
                station
            end
            return cached if cached
            line = @io_lock.synchronize do
                raise FileError.new("the release is closed", path: @io&.path) if @io.nil? || @io.closed?
                @io.seek(e.pos)
                @io.read(e.len)
            end
            raw, why = line && line.bytesize == e.len ? parse_station(line) : nil
            unless raw.is_a?(Hash) && raw["station_id"] == e.station_id
                bad_line!(e, raw.is_a?(Hash) ? "is #{raw['station_id'].inspect}" : ["is not a station line", why].compact.join(": "))
            end
            check_line!(raw, e) if e.view
            effective = e.eff_id
            if @commercial_only && Reader.policy_uncached?(e.view)
                sets = raw["constant_sets"] || []
                effective = effective_set(sets.find { |cs| cs["set_id"] == raw["recommended_set_id"] }, sets)&.fetch("set_id")
            end
            station = build_station(raw, e.kind, effective)
            @io_lock.synchronize do
                check_open!
                @station_cache_lock.synchronize do
                    @station_cache[e.station_id] = station
                    @station_cache.shift while @station_cache.size > 256
                end
            end
            station
        rescue SystemCallError, IOError => err
            raise FileError.new("cannot read station #{e.station_id}: #{err.message}", path: @io&.path)
        end

        # A line that is not the station its entry names: invalid_release. When
        # the entry came from index-v1.json, the client deletes that index so
        # the next open rebuilds it (spec §6.2, CR D4).
        def bad_line!(e, what)
            source = @on_bad_index ? "index-v1.json" : "the .jsonl"
            msg = "#{source}: the line at byte #{e.pos} for #{e.station_id} #{what}"
            @on_bad_index&.call(msg)
            raise InvalidReleaseError, msg
        end

        # A line read through the stream index gets the checks of the full
        # pass, and every represented source field must match the entry
        # (spec §6.2, CR D4, PK-R2-07); otherwise bad_line!.
        def check_line!(raw, e)
            begin
                Release.check_station!(raw)
                aliases = raw["aliases"]
                unless aliases.nil? || (aliases.is_a?(Hash) && aliases.values.all? { |v| v.is_a?(String) || (v.is_a?(Array) && v.all?(String)) })
                    raise InvalidReleaseError, "station #{e.station_id}: aliases must map a system to a String id or a list of them"
                end
            rescue InvalidReleaseError => err
                bad_line!(e, "fails a check: #{err.message}")
            end
            summary = Reader.index_entry(raw, e.pos, e.len)
            if summary["kind"].nil? && e.kind && raw["type"] == "subordinate" && e.reference_id
                summary["kind"] = materialize(@by_id.fetch(e.reference_id)).kind&.to_s
            end
            return if Reader.line_view(summary, presence: e.view["presence"]) == e.view
            bad_line!(e, "does not give the represented source fields of its entry")
        end

        # [the parsed line, nil], or [nil, why it does not parse] (R3-226: the
        # reason goes into the invalid_release message).
        def parse_station(line)
            line = line.force_encoding(Encoding::UTF_8)
            Util.no_lone_surrogate!(line)
            [JSON.parse(line), nil]
        rescue JSON::ParserError, EncodingError, InvalidReleaseError => err
            [nil, err.message[0, 200]]
        end

        # rec_id: the set the Station gives as recommended (the effective one
        # under commercial_only, K-NC DR106).
        def build_station(raw, kind, rec_id)
            all_validation = Array(raw["validation"]).map { |v| Validation.new(v) }
            sets = Array(raw["constant_sets"]).map do |cs|
                set_validation = all_validation.each_with_index.select { |v, _| v.set_id == cs["set_id"] }
                                               .sort_by { |v, i| [v.window.to_s, i] }.map(&:first)
                ConstantSet.new(cs, convention: @convention_by_id.fetch(cs["convention_id"]),
                                    licence: @licence_by_id.fetch(cs["licence_id"]),
                                    validation: set_validation, recommended: !rec_id.nil? && cs["set_id"] == rec_id)
            end
            Station.new(raw, sets: sets, kind: kind, validation: all_validation, origin: self, licences: @licence_by_id)
        end

        # Checks every station and builds the indexes. In stream mode no
        # Station is kept.
        def bind_eager_station_owners(entries, raws)
            if @mode == :eager
                entries.each { |e| e.station = build_station(raws[e.station_id], e.kind, e.eff_id) }
            end
            entries.each(&:freeze)
        end

        def bind_prepared_release_fields(prepared)
            @mode = prepared.mode
            @commercial_only = prepared.commercial_only
            @commercial_basis = prepared.commercial_basis
            @historical_offsets_policy = prepared.historical_offsets_policy
            @meta = prepared.meta
            @logger = prepared.logger
            @io = prepared.io
            @on_bad_index = prepared.on_bad_index
            @io_lock = prepared.io_lock
            @station_cache = prepared.station_cache
            @station_cache_lock = prepared.station_cache_lock
            @state = prepared.state
            @files = prepared.files
            @checks = prepared.checks
            @datestamp = prepared.datestamp
            @created = prepared.created
            @format_version = prepared.format_version
            @concept_doi = prepared.concept_doi
            @zenodo_version_doi = prepared.zenodo_version_doi
            @source_versions = prepared.source_versions
            @build_commit = prepared.build_commit
            @changelog_url = prepared.changelog_url
            @conventions = prepared.conventions
            @licences = prepared.licences
            @convention_by_id = prepared.convention_by_id
            @licence_by_id = prepared.licence_by_id
            @set_ids = prepared.set_ids
            @set_sources = prepared.set_sources
            @set_qc = prepared.set_qc
            @aliases = prepared.aliases
            @by_id = prepared.by_id
            @entries = prepared.entries
            @tombstones = prepared.tombstones
            @tomb_pos = prepared.tomb_pos
            @tomb_by_id = prepared.tomb_by_id
            @constituent_names = prepared.constituent_names
            @subordinates = prepared.subordinates
        end

        def load_stations(stations)
            entries = []
            tombs = []
            tomb_pos = []
            raws = {}
            names = Set.new
            ids = Set.new
            @set_ids = Set.new
            @set_sources = []
            @set_qc = []
            stations.each do |raw, pos, len, view|
                raise InvalidReleaseError, "a station is not an object" unless raw.is_a?(Hash)
                sid = raw["station_id"]
                raise InvalidReleaseError, "a station has no station_id" unless sid.is_a?(String)
                # One id across the active stations and the tombstones together (CR D5).
                raise InvalidReleaseError, "station_id #{sid} appears twice" unless ids.add?(sid)
                # A line with no status (or null) is an active station, as in the stream index (CR2 DR28).
                status = raw["status"].nil? ? "active" : raw["status"]
                # A status that is there but not a String is malformed (schema type string, CR2 DR43).
                raise InvalidReleaseError, "station #{sid}: status is not a string: #{status.inspect[0, 100]}" unless status.is_a?(String)
                if status == "removed"
                    Release.check_tombstone!(raw)
                    tombs << Tombstone.new(raw)
                    tomb_pos << [tombs.last, pos, len]
                    next
                end
                unless status == "active"
                    # A status this SDK does not know (a newer minor's value): not a
                    # station, not a tombstone, in no query and no count; said once,
                    # at load (CR2 DR8).
                    @logger&.warn("opentideconstants: station #{sid} has the status #{status.inspect}, which this SDK " \
                                  "does not know: it is left out of every query")
                    next
                end
                Release.check_station!(raw)
                entries << entry_for(raw, pos, len, names)
                entries.last.view = view
                raws[sid] = raw if @mode == :eager
            end
            entries.sort_by!(&:station_id)
            @by_id = entries.to_h { |e| [e.station_id, e] }
            entries.each do |e|
                next if e.reference_id.nil? || (e.reference_id.is_a?(String) && @by_id.key?(e.reference_id))
                raise InvalidReleaseError, "station #{e.station_id}: reference_station_id #{e.reference_id.inspect} " \
                                           "names no active station"
            end
            @set_ids = nil
            kinds = entries.to_h { |e| [e.station_id, kind_of(e, [])] }
            entries.each { |e| e.kind = kinds.fetch(e.station_id) }
            entries.each do |e|
                next unless e.view && e.view["kind"] != e.kind&.to_s
                raise InvalidReleaseError, "index-v1.json: station #{e.station_id} has the wrong derived kind"
            end
            bind_eager_station_owners(entries, raws)
            @entries = entries.freeze
            @by_id.freeze
            @tombstones = tombs.sort_by(&:station_id).freeze
            @tomb_pos = tomb_pos.freeze
            @tomb_by_id = @tombstones.to_h { |t| [t.station_id, t] }.freeze
            @constituent_names = names.to_a.sort.freeze
            @set_sources.freeze
            @set_qc.freeze
            subs = Hash.new { |h, k| h[k] = [] }
            entries.each { |e| subs[e.reference_id] << e if e.type == :subordinate && e.reference_id }
            @subordinates = subs.transform_values(&:freeze).freeze
            @aliases = (@aliases || {}).to_a.to_h { |k, v| [k, v.freeze] }.freeze
        end

        def entry_for(raw, pos, len, names)
            sid = raw["station_id"]
            %w[name lat lon type].each do |k|
                raise InvalidReleaseError, "station #{sid}: #{k} missing" if raw[k].nil?
            end
            rec_id = raw["recommended_set_id"]
            sets = raw["constant_sets"] || []
            raise InvalidReleaseError, "station #{sid}: constant_sets is not an array" unless sets.is_a?(Array)
            rec = nil
            sources = Set.new
            sets.each do |cs|
                raise InvalidReleaseError, "station #{sid}: a set is not an object" unless cs.is_a?(Hash)
                raise InvalidReleaseError, "set_id #{cs['set_id'].inspect} appears twice" unless @set_ids.add?(cs["set_id"])
                unless @convention_by_id.key?(cs["convention_id"])
                    raise InvalidReleaseError, "set #{cs['set_id']}: convention #{cs['convention_id'].inspect} does not resolve"
                end
                unless @licence_by_id.key?(cs["licence_id"])
                    raise InvalidReleaseError, "set #{cs['set_id']}: licence #{cs['licence_id'].inspect} does not resolve"
                end
                rec = cs if !rec_id.nil? && cs["set_id"] == rec_id
                qc = Util.enum(cs["qc_status"], ENUMS[:qc_status])
                # Only a set with constants (ok or flagged) is a usable source (spec §4.3, §4.4).
                if USABLE_QC.include?(qc)
                    sources << cs["source"]
                    @set_sources << cs["source"]
                end
                @set_qc << qc
                Array(cs["constituents"]).each { |c| names << c["name"] if c.is_a?(Hash) && c["name"] }
            end
            raise InvalidReleaseError, "station #{sid}: recommended set #{rec_id} does not exist" if rec_id && rec.nil?
            off = raw["subordinate_offsets"]
            off = nil unless off.is_a?(Hash)
            if off && off["licence_id"] && !@licence_by_id.key?(off["licence_id"])
                raise InvalidReleaseError, "station #{sid}: offsets licence #{off['licence_id'].inspect} does not resolve"
            end
            index_aliases(sid, raw["aliases"])
            Array(raw["source_records"]).each { |r| SourceRecord.new(r, licences: @licence_by_id) }
            eff = @commercial_only ? effective_set(rec, sets) : rec
            # Keep the reader's discovery fields, not the full fits. The names
            # were collected above; materialize reads the complete line on demand.
            summaries = Reader.index_entry(raw, pos, len).fetch("sets")
            summaries.each { |cs| cs.delete("constituents") }
            Entry.new(station_id: sid, name: raw["name"], folded: Fold.fold(raw["name"].to_s), lat: raw["lat"],
                      lon: raw["lon"], type: Util.enum(raw["type"], ENUMS[:station_type]), country: raw["country"],
                      kind: rec && quantity_kind(rec["quantity"]), sources: sources.freeze,
                      rec_source_type: rec && Util.enum(rec["source_type"], ENUMS[:source_type]),
                      rec_licence_id: rec && rec["licence_id"], offsets_licence_id: off && off["licence_id"],
                      reference_id: off && off["reference_station_id"],
                      eff_id: eff && eff["set_id"], eff_licence_id: eff && eff["licence_id"],
                      eff_source_type: eff && Util.enum(eff["source_type"], ENUMS[:source_type]),
                      offsets_ref_licence_id: sets.find { |cs| offsets_reference_set?(cs) }&.fetch("licence_id"),
                      aliases: (raw["aliases"].is_a?(Hash) ? raw["aliases"].transform_values { |v| Array(v) } : {}),
                      sets: summaries, offsets: off, current_offsets: raw["current_offsets"] || [],
                      pos: pos, len: len, station: nil)
        end

        # The effective recommended set under commercial_only (spec §4.2, K-NC
        # DR106): the release's recommended set when its licence allows
        # commercial use; otherwise the first set in file order of the same
        # typed quantity, qc_status ok, with a commercial licence; then the same
        # with flagged; otherwise nil. A set with no quantity never matches.
        def commercial_set?(cs)
            return false if @commercial_basis == "strict" && cs.dig("fallback", "reason") == "licence_reading"
            @licence_by_id[cs["licence_id"]]&.commercial_use == true
        end

        def set_eligible?(cs, flagged, fallback, offsets_licence = nil)
            return false unless cs && %w[ok flagged].include?(cs["qc_status"])
            if cs["fallback"]
                return false unless fallback
            else
                return false if cs["qc_status"] != "ok" && !flagged
            end
            return false if offsets_licence && !@licence_by_id.key?(offsets_licence)
            return true unless @commercial_only
            commercial_set?(cs) && (!offsets_licence || @licence_by_id[offsets_licence].commercial_use == true)
        end

        # Missing cache policy is resolved from the selected record, not from defaults.
        # Keep this temporary summary local; the stream entry retains no full fit.
        def policy_entry(e)
            return e unless e && Reader.policy_uncached?(e.view)
            raw = materialize(e).raw
            summary = Reader.index_entry(raw, e.pos, e.len)
            candidate = e.dup
            candidate.sets = summary["sets"].map { |cs| cs.reject { |k, _| k == "constituents" } }
            candidate.offsets = raw["subordinate_offsets"]
            candidate.current_offsets = raw["current_offsets"] || []
            sets = raw["constant_sets"] || []
            rec = sets.find { |cs| cs["set_id"] == raw["recommended_set_id"] }
            candidate.eff_id = (@commercial_only ? effective_set(rec, sets) : rec)&.fetch("set_id")
            candidate.freeze
        end

        def eligible_paths(e, flagged, fallback, historical: true)
            e = policy_entry(e)
            paths = e.sets.select { |cs| set_eligible?(cs, flagged, fallback) }
            ref = policy_entry(@by_id[e.reference_id])
            off = e.offsets || {}
            if off["offset_id"]
                paths << off if historical && historical_discovery?(e)
            elsif ref
                cs = ref.sets.find { |v| offsets_reference_set?(v) }
                paths << cs if set_eligible?(cs, flagged, fallback, e.offsets_licence_id)
            end
            e.current_offsets.each do |co|
                parent = policy_entry(@by_id[co["reference_station_id"]])
                n = co["reference_bin"]
                own = co["bin"]
                next unless parent && [n, own].all? { |i| i.is_a?(Numeric) && i == i.to_i && i.between?(1, 2**53 - 1) }
                cs = parent.sets.find { |v| v["quantity"] == "current" && %w[ok flagged].include?(v["qc_status"]) && Array(v["current_bins"]).any? { |b| (b.is_a?(Hash) ? b["bin"] : b) == n } }
                paths << cs if set_eligible?(cs, flagged, fallback, co["licence_id"])
            end
            paths
        end

        def historical_discovery?(e)
            return false if @historical_offsets_policy == "exclude"
            return false if e.sets.any? { |cs| cs["set_id"] == e.eff_id && %w[ok flagged].include?(cs["qc_status"]) }
            return false unless eligible_paths(e, false, false, historical: false).empty?
            off = e.offsets
            ref = policy_entry(@by_id[off["reference_station_id"]])
            return false unless ref
            cs = ref.sets.find { |v| offsets_reference_set?(v) }
            binding = off.dig("provenance", "reference_binding")
            return false unless cs && cs["qc_status"] == "ok" && cs["fallback"].nil? && cs["source_record_id"] == binding["noaa_id"]
            return false if @commercial_only && (!commercial_set?(cs) || @licence_by_id[off["licence_id"]]&.commercial_use != true)
            conv = @convention_by_id[cs["convention_id"]]
            return false unless conv && conv.v0_model == "schureman_tcd" && conv.nodal_handling == :f_u_at_prediction
            datum = cs["datum"] || {}
            return false unless datum["chart_datum"] == "mllw" && datum["msl_offset_m"] && datum.dig("named", "mllw") == 0.0 && datum.dig("basis", "mllw", "kind") == "published"
            constants = materialize(ref).constant_set(cs["set_id"])
            begin
                table = Predict.table_for(self, constants)
                Array(constants.raw["constituents"]).each { |row| table.send(:row_for, row["name"]) }
            rescue NoAstroTableError, UnsupportedConventionError, UnsupportedConstituentError, InvalidArgumentError
                return false
            end
            true
        end

        def effective_set(rec, sets)
            return rec if rec.nil? || @licence_by_id[rec["licence_id"]]&.commercial_use == true
            q = Util.enum(rec["quantity"], ENUMS[:quantity])
            return nil if q.nil?
            %i[ok flagged].each do |status|
                found = sets.find do |cs|
                    Util.enum(cs["qc_status"], ENUMS[:qc_status]) == status && Util.enum(cs["quantity"], ENUMS[:quantity]) == q &&
                        @licence_by_id[cs["licence_id"]]&.commercial_use == true
                end
                return found if found
            end
            nil
        end

        # A set that the one-link offsets path takes as its reference set
        # (spec §4.2, K-NC DR106): from the offsets' source, water_level, ok or
        # flagged.
        def offsets_reference_set?(cs)
            cs["source"] == OFFSETS_SOURCE && Util.enum(cs["quantity"], ENUMS[:quantity]) == :water_level &&
                USABLE_QC.include?(Util.enum(cs["qc_status"], ENUMS[:qc_status]))
        end

        # The JSON type of each known field that the SDK reads (spec §7.3:
        # tolerant is not lax; CR2 PK-R2-05). Absent or null is always allowed
        # here; required fields are checked where they are used. :t a String,
        # :n a finite number, :i a finite number with an integral value, :o an
        # object, :l a list of objects, :s a list of Strings, :a a list. The
        # same table is in the Python, TypeScript and C SDKs.
        STATION_TYPES = { "name" => :t, "country" => :t, "timezone" => :t, "type" => :t, "recommended_set_id" => :t,
                          "status" => :t, "constant_sets" => :l, "validation" => :l, "subordinate_offsets" => :o,
                          "current_offsets" => :a, "source_records" => :l, "recommended_is_fallback" => :b }.freeze
        OFFSET_TYPES = { "reference_station_id" => :t, "licence_id" => :t, "height_adjusted_type" => :t,
                         "time_offset_high_min" => :n, "time_offset_low_min" => :n, "height_offset_high" => :n,
                         "height_offset_low" => :n, "offset_id" => :t, "source" => :t, "source_type" => :t,
                         "source_version" => :t, "source_record_id" => :t, "qc_status" => :t, "qc_flags" => :l,
                         "fallback" => :o, "vintage" => :o, "provenance" => :o }.freeze
        VALIDATION_TYPES = { "set_id" => :t, "reference_source" => :t, "reference_station" => :t, "window" => :t,
                             "reference_distance_km" => :n, "time_mae_min" => :n, "time_p95_min" => :n,
                             "time_bias_min" => :n, "height_mae_m" => :n, "range_error_m" => :n,
                             "missed_events" => :i, "extra_events" => :i, "previous_release" => :o }.freeze
        SET_TYPES = { "set_id" => :t, "source" => :t, "source_type" => :t, "quantity" => :t, "source_record_id" => :t,
                      "source_version" => :t, "convention_id" => :t, "licence_id" => :t, "qc_status" => :t,
                      "constituents" => :l, "dropped_constituents" => :l, "qc_flags" => :l, "record_span" => :o,
                      "datum" => :o, "time_base" => :o, "provenance" => :o, "current_bins" => :a, "fallback" => :o }.freeze
        SPAN_TYPES = { "good_samples" => :i }.freeze
        DATUM_TYPES = { "msl_offset_m" => :n, "named" => :o }.freeze
        CONSTITUENT_TYPES = { "name" => :t, "source_name" => :t, "doodson" => :t, "kept_reason" => :t,
                              "speed_deg_per_hour" => :n, "amplitude_m" => :n, "phase_deg" => :n,
                              "amp_uncertainty_m" => :n, "phase_uncertainty_deg" => :n }.freeze
        QC_FLAG_TYPES = { "flag" => :t, "reason" => :t, "values" => :o }.freeze
        DROPPED_TYPES = { "name" => :t, "dropped_reason" => :t, "detail" => :t }.freeze
        TIME_BASE_TYPES = { "code" => :t, "reason" => :t, "declared" => :t, "published" => :t, "decided_in" => :t,
                            "decided_build_commit" => :t, "correction" => :o, "months_dropped" => :s,
                            "evidence" => :l }.freeze
        CORRECTION_TYPES = { "from" => :t, "to" => :t }.freeze
        EVIDENCE_TYPES = { "comparator_kind" => :t, "comparator_id" => :t, "detail" => :t, "distance_km" => :n,
                           "lag_min" => :n }.freeze
        PROVENANCE_TYPES = { "adapter_version" => :t, "carried_from_release" => :t, "selection_reason" => :t,
                             "input_sha256" => :s, "decision" => :o }.freeze

        # The shape checks of a tombstone line: its fields are strings or null.
        def self.check_tombstone!(raw)
            %w[name removed_in removed_reason merged_into detail].each do |k|
                next if raw[k].nil? || raw[k].is_a?(String)
                raise InvalidReleaseError, "tombstone #{raw['station_id']}: #{k} is not a string"
            end
        end

        def self.type_ok?(v, type)
            return true if v.nil?
            case type
            when :b then v == true || v == false
            when :t then v.is_a?(String)
            when :n then real?(v)
            when :i then real?(v) && v == v.to_i
            when :o then v.is_a?(Hash)
            when :l then v.is_a?(Array) && v.all?(Hash)
            when :s then v.is_a?(Array) && v.all?(String)
            else v.is_a?(Array)
            end
        end

        def self.check_types!(obj, table, what)
            table.each do |k, type|
                raise InvalidReleaseError, "#{what}: #{k} has the wrong type" unless type_ok?(obj[k], type)
            end
        end

        # The shape checks of an active station line (spec §6.1, §7.3): every
        # field that the SDK reads has the type of the format, also the nested
        # ones, so a malformed station fails the load with invalid_release in
        # eager and stream mode alike, never a raw error at the first query.
        HISTORICAL_PROFILES = Util.deep_freeze({"noaa-2020-atlantic-table2-2513"=>{"source"=>"noaa", "source_type"=>"official", "source_version"=>"annual-tide-tables-2020", "source_record_id"=>"annual-tide-tables-2020/atlantic/Table2/2513", "qc_status"=>"flagged", "reference_station_id"=>"OTC-a6c00a3f", "height_adjusted_type"=>"R", "time_offset_high_min"=>4, "time_offset_low_min"=>15, "height_offset_high"=>0.84, "height_offset_low"=>1.0, "datum"=>{"basis"=>{"mllw"=>{"kind"=>"published", "method"=>"source", "source_name"=>"MLLW"}}, "chart_datum"=>"mllw", "named"=>{"mllw"=>0.0}, "zero"=>"chart_datum"}, "vintage"=>{"publication_year"=>2020, "source_lifecycle"=>"retired", "current_validity"=>"unestablished", "current_accuracy"=>"unverified", "removal_events"=>[{"evidence_sha256"=>"c100d0fbc5482ec24f5c99d912be73306bd2dea079690f08edc5f58a821bcd61", "name"=>"Lockwoods Folly Inlet (r)", "operation"=>"Removed", "source_clock_timestamp"=>"2026-02-18T14:09:46", "source_timezone"=>nil}]}, "provenance"=>{"source_manifest_sha256"=>"667eec5b3fd25f99d46f24864766726094961d7db5fa104ca12450f3ecd0fdf7", "book"=>"atlantic", "annual_table_row"=>2513, "printed_page"=>345, "pdf_page"=>351, "raw_row_text"=>"  2513     Lockwoods Folly Inlet . . . . . . . . . . . . . . . . . . . . . . .         33° 55'     78° 14'     +0 04      +0 15     *0.84     *1.00    4.2    4.8     2.3", "id_crosswalk"=>{"evidence_sha256"=>["a411769769c0ada0966c4fb7cd8f107637631790377fd474460efd0c1551c6d1", "c100d0fbc5482ec24f5c99d912be73306bd2dea079690f08edc5f58a821bcd61"], "legacy_id"=>"TEC2869", "modern_alias_verified"=>false, "status"=>"inferred"}, "reference_binding"=>{"evidence_sha256"=>["a411769769c0ada0966c4fb7cd8f107637631790377fd474460efd0c1551c6d1", "c100d0fbc5482ec24f5c99d912be73306bd2dea079690f08edc5f58a821bcd61"], "mapping_status"=>"primary_name_position", "noaa_id"=>"8661070", "station_id"=>"OTC-a6c00a3f"}}}, "noaa-2020-pacific-table2-517"=>{"source"=>"noaa", "source_type"=>"official", "source_version"=>"annual-tide-tables-2020", "source_record_id"=>"annual-tide-tables-2020/pacific/Table2/517", "qc_status"=>"flagged", "reference_station_id"=>"OTC-ee4593cd", "height_adjusted_type"=>"A", "time_offset_high_min"=>-35, "time_offset_low_min"=>-31, "height_offset_high"=>-0.06096, "height_offset_low"=>0.0, "datum"=>{"basis"=>{"mllw"=>{"kind"=>"published", "method"=>"source", "source_name"=>"MLLW"}}, "chart_datum"=>"mllw", "named"=>{"mllw"=>0.0}, "zero"=>"chart_datum"}, "vintage"=>{"publication_year"=>2020, "source_lifecycle"=>"retired", "current_validity"=>"unestablished", "current_accuracy"=>"unverified", "removal_events"=>[{"evidence_sha256"=>"c100d0fbc5482ec24f5c99d912be73306bd2dea079690f08edc5f58a821bcd61", "name"=>"San Francisco Bar (r)", "operation"=>"Removed", "source_clock_timestamp"=>"2026-02-18T14:09:50", "source_timezone"=>nil}, {"evidence_sha256"=>"c100d0fbc5482ec24f5c99d912be73306bd2dea079690f08edc5f58a821bcd61", "name"=>"San Francisco Bar", "operation"=>"Removed", "source_clock_timestamp"=>"2026-07-06T11:17:37", "source_timezone"=>nil}]}, "provenance"=>{"source_manifest_sha256"=>"667eec5b3fd25f99d46f24864766726094961d7db5fa104ca12450f3ecd0fdf7", "book"=>"pacific", "annual_table_row"=>517, "printed_page"=>284, "pdf_page"=>302, "raw_row_text"=>"   517     San Francisco Bar . . . . . . . . . . . . . . . . . . . . . . . . .         37° 46'     122° 38'     -0 35       -0 31      -0.2        0.0    3.9    5.6     3.0", "id_crosswalk"=>{"evidence_sha256"=>["5164fe5fca308a44dfe9a5968191f0b0d69e3b6242cefde977577063fa037e64", "c100d0fbc5482ec24f5c99d912be73306bd2dea079690f08edc5f58a821bcd61"], "legacy_id"=>"TWC0509", "modern_alias_verified"=>false, "status"=>"inferred"}, "reference_binding"=>{"evidence_sha256"=>["5164fe5fca308a44dfe9a5968191f0b0d69e3b6242cefde977577063fa037e64", "c100d0fbc5482ec24f5c99d912be73306bd2dea079690f08edc5f58a821bcd61"], "mapping_status"=>"primary_name_position", "noaa_id"=>"9414290", "station_id"=>"OTC-ee4593cd"}}}})
        def self.check_historical_offsets!(off, what)
            return unless off
            raise InvalidReleaseError, "#{what}: subordinate_offsets must be an object" unless off.is_a?(Hash)
            check_types!(off, OFFSET_TYPES, "#{what}: subordinate_offsets")
            historical = off.key?("offset_id") || off.dig("fallback", "reason") == "historical_offsets" || Array(off["qc_flags"]).any? { |f| f.is_a?(Hash) && f["flag"] == "fallback:historical_offsets" }
            return unless historical
            fail_field = ->(key) { raise InvalidReleaseError, "#{what}: invalid or missing historical #{key}" }
            expected = HISTORICAL_PROFILES[off["offset_id"]]
            fail_field.call("offset_id") unless expected
            expected.each do |key, value|
                next if %w[vintage provenance].include?(key)
                fail_field.call(key) unless off[key] == value
            end
            text = ->(value) { value.is_a?(String) && !value.strip.empty? }
            digest = ->(value) { value.is_a?(String) && value.match?(/\A[a-f0-9]{64}\z/) }
            hashes = ->(values) { values.is_a?(Array) && !values.empty? && values.uniq.size == values.size && values.all? { |v| digest.call(v) } }
            fail_field.call("licence_id") unless text.call(off["licence_id"])
            flags = off["qc_flags"]
            fail_field.call("qc_flags") unless flags.is_a?(Array) && flags.size == 1 && flags[0].is_a?(Hash) && flags[0]["flag"] == "fallback:historical_offsets" && text.call(flags[0]["reason"])
            fallback = off["fallback"]
            fail_field.call("fallback") unless fallback.is_a?(Hash) && fallback["reason"] == "historical_offsets" && %w[basis otc_finding].all? { |k| text.call(fallback[k]) } && !fallback.key?("preferred_set_id")
            vintage = off["vintage"]
            fail_field.call("vintage") unless vintage.is_a?(Hash)
            expected["vintage"].each { |key, value| fail_field.call("vintage.#{key}") unless vintage[key] == value }
            equivalence = vintage["reference_2020_equivalence"]
            fail_field.call("reference_2020_equivalence") unless %w[not_checked matched_at_publisher_precision disagrees].include?(equivalence)
            if equivalence == "not_checked"
                fail_field.call("reference_2020_equivalence_sha256") if vintage.key?("reference_2020_equivalence_sha256")
            else
                fail_field.call("reference_2020_equivalence_sha256") unless digest.call(vintage["reference_2020_equivalence_sha256"])
            end
            prov = off["provenance"]
            fail_field.call("provenance") unless prov.is_a?(Hash)
            expected["provenance"].each do |key, value|
                next if %w[id_crosswalk reference_binding].include?(key)
                fail_field.call("provenance.#{key}") unless prov[key] == value
            end
            fail_field.call("provenance hashes") unless hashes.call(prov["input_sha256"]) && digest.call(prov["acceptance_report_sha256"])
            %w[id_crosswalk reference_binding].each do |key|
                nested = prov[key]
                fail_field.call(key) unless nested.is_a?(Hash) && hashes.call(nested["evidence_sha256"])
                expected["provenance"][key].each do |k,v|
                    next if k == "evidence_sha256"
                    fail_field.call("#{key}.#{k}") unless nested[k] == v
                end
            end
            begin
                fail_field.call("raw_values_json") unless text.call(prov["raw_values_json"]) && JSON.parse(prov["raw_values_json"]).is_a?(Hash)
            rescue JSON::ParserError
                fail_field.call("raw_values_json")
            end
        end

        def self.check_source_records!(raw, what)
            return unless raw.key?("source_records")
            records = raw["source_records"]
            raise InvalidReleaseError, "#{what}: source_records must be a nonempty array" unless records.is_a?(Array) && !records.empty?
            records.each do |r|
                raise InvalidReleaseError, "#{what}: source record is not an object" unless r.is_a?(Hash)
                check_types!(r, {"source"=>:t,"source_version"=>:t,"source_record_id"=>:t,"role"=>:t,"disposition"=>:t,"detail"=>:t,"licence_id"=>:t,"upstream_licence_id"=>:t,"published_set_ids"=>:s,"provenance"=>:o,"original_metadata"=>:o,"original_harmonics"=>:o}, what)
                %w[source source_version source_record_id role disposition detail].each do |k|
                    raise InvalidReleaseError, "#{what}: source record #{k} must be nonempty" unless r[k].is_a?(String) && !r[k].empty?
                end
                unless r.key?("licence_id") && r["published_set_ids"].is_a?(Array) && r["provenance"].is_a?(Hash)
                    raise InvalidReleaseError, "#{what}: source record missing licence/published_set_ids/provenance"
                end
                check_types!(r["provenance"], {"input_sha256"=>:s,"inventory_sha256"=>:t}, what)
                unless r["provenance"]["input_sha256"].is_a?(Array) && r["provenance"]["inventory_sha256"].is_a?(String)
                    raise InvalidReleaseError, "#{what}: source record provenance missing input_sha256/inventory_sha256"
                end
                if r.key?("original_metadata") && !r["original_metadata"].is_a?(Hash)
                    raise InvalidReleaseError, "#{what}: original_metadata must be an object"
                end
                h=r["original_harmonics"]
                next unless h
                check_types!(h, {"format"=>:t,"columns"=>:s,"rows"=>:a,"annotations"=>:l,"amplitude_unit"=>:t,"amplitude_unit_basis"=>:t,"phase_unit"=>:t,"phase_convention"=>:t,"amplitude_uncertainty_unit"=>:t,"amplitude_uncertainty_unit_basis"=>:t}, what)
                if h.key?("rows") && !(h["rows"].is_a?(Array) && h["rows"].all? { |row| row.is_a?(Array) && row.all?(String) })
                    raise InvalidReleaseError, "#{what}: original_harmonics rows must contain arrays of strings"
                end
                Array(h["annotations"]).each { |a| check_types!(a, {"row"=>:i,"reason"=>:t,"detail"=>:t}, what) }
            end
        end

        def self.check_station!(raw)
            sid = raw["station_id"]
            what = "station #{sid}"
            raise InvalidReleaseError, "#{what}: name is not a string" unless raw["name"].is_a?(String)
            check_types!(raw, STATION_TYPES, what)
            check_source_records!(raw, what)
            check_historical_offsets!(raw["subordinate_offsets"], what)
            unless real?(raw["lat"]) && raw["lat"].between?(-90, 90)
                raise InvalidReleaseError, "#{what}: lat is not a number in [-90, 90]"
            end
            unless real?(raw["lon"]) && raw["lon"].between?(-180, 180)
                raise InvalidReleaseError, "#{what}: lon is not a number in [-180, 180]"
            end
            check_types!(raw["subordinate_offsets"], OFFSET_TYPES, "#{what}: subordinate_offsets") if raw["subordinate_offsets"]
            Array(raw["validation"]).each { |v| check_types!(v, VALIDATION_TYPES, "#{what}: validation") }
            Array(raw["constant_sets"]).each { |cs| check_set!(cs, what) }
        end

        def self.check_set!(cs, station)
            raise InvalidReleaseError, "#{station}: a set has no set_id" unless cs["set_id"].is_a?(String)
            what = "#{station}: set #{cs['set_id']}"
            check_types!(cs, SET_TYPES, what)
            check_types!(cs["fallback"], {"reason" => :t, "basis" => :t, "otc_finding" => :t, "preferred_set_id" => :t}, what) if cs["fallback"]
            { "record_span" => SPAN_TYPES, "datum" => DATUM_TYPES, "time_base" => TIME_BASE_TYPES,
              "provenance" => PROVENANCE_TYPES }.each do |k, table|
                check_types!(cs[k], table, "#{what}: #{k}") if cs[k]
            end
            names = Set.new
            Array(cs["constituents"]).each do |c|
                raise InvalidReleaseError, "#{what}: a constituent has no name" unless c["name"].is_a?(String)
                check_types!(c, CONSTITUENT_TYPES, "#{what}: constituents")
                # spec §6.1 (CR2 DR22): a name once per set
                raise InvalidReleaseError, "#{what}: constituent #{c['name']} appears twice" unless names.add?(c["name"])
            end
            Array(cs["dropped_constituents"]).each { |x| check_types!(x, DROPPED_TYPES, "#{what}: dropped_constituents") }
            Array(cs["qc_flags"]).each do |f|
                check_types!(f, QC_FLAG_TYPES, "#{what}: qc_flags")
                unless (f["values"] || {}).values.all? { |x| x.nil? || real?(x) }
                    raise InvalidReleaseError, "#{what}: a qc_flags value is not a number or null"
                end
            end
            span = cs["record_span"]
            if span
                Util.time(span["start"])
                Util.time(span["end"])
            end
            named = (cs["datum"] || {})["named"] || {}
            raise InvalidReleaseError, "#{what}: datum.named has a value that is not a number" unless named.values.all? { |x| real?(x) }
            tb = cs["time_base"] || {}
            check_types!(tb["correction"], CORRECTION_TYPES, "#{what}: time_base.correction") if tb["correction"]
            Array(tb["evidence"]).each { |e| check_types!(e, EVIDENCE_TYPES, "#{what}: time_base.evidence") }
        end

        def quantity_kind(q)
            case q
            when "water_level" then :tide
            when "current" then :current
            else :other
            end
        end

        # The licences of a station's reference chain (spec §4.6, CR2 DR1).
        # The walk follows reference_station_id through at most 16 links
        # (the kind rule of §6.2). It takes the offsets licence of each
        # station on the path, and the licence of the first recommended set
        # it reaches, where it stops. A loop or a missing station ends the
        # walk: the load has checked the links.
        def chain_licences(e)
            out = []
            seen = Set[e.station_id]
            links = 0
            while e.type == :subordinate && (e.reference_id || e.offsets_licence_id)
                out << e.offsets_licence_id if e.offsets_licence_id
                break if links == MAX_LINKS
                ref = @by_id[e.reference_id]
                break if ref.nil? || seen.include?(ref.station_id)
                links += 1
                seen << ref.station_id
                if ref.rec_licence_id
                    out << ref.rec_licence_id
                    break
                end
                e = ref
            end
            out
        end

        # A station's kind comes from its recommended set, or from its
        # reference station if it is subordinate with offsets only.
        def kind_of(e, seen)
            return e.kind if e.kind
            return nil if seen.size >= MAX_LINKS
            return nil unless e.type == :subordinate && e.reference_id
            ref = @by_id[e.reference_id]
            return nil if ref.nil? || seen.include?(ref.station_id)
            kind_of(ref, seen + [e.station_id])
        end

        # Indexes a station's aliases. They map a system to a String id or an
        # Array of String ids, and a (system, id) pair names one station only
        # (spec §4.4, CR D5); anything else is invalid_release.
        def index_aliases(sid, aliases)
            @aliases ||= Hash.new { |h, k| h[k] = {} }
            return if aliases.nil?
            raise InvalidReleaseError, "station #{sid}: aliases is not an object" unless aliases.is_a?(Hash)
            aliases.each do |system, ids|
                list = ids.is_a?(Array) ? ids : [ids]
                unless list.all?(String)
                    raise InvalidReleaseError, "station #{sid}: alias #{system} must be a String id or a list of them"
                end
                list.each do |id|
                    other = @aliases[system.to_s][id]
                    raise InvalidReleaseError, "alias #{system} #{id} appears twice (#{other} and #{sid})" if other
                    @aliases[system.to_s][id] = sid
                end
            end
        end
    end
end
