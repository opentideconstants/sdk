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
        FILTER_KEYS = %i[country type kind source source_type].freeze
        # The qc_status values of a set with constants.
        USABLE_QC = %i[ok flagged].freeze

        # A small per-station summary, used by the filters and the indexes.
        Entry = Struct.new(:station_id, :name, :folded, :lat, :lon, :type, :country, :kind, :sources,
                           :rec_source_type, :rec_licence_id, :offsets_licence_id, :reference_id,
                           :aliases, :pos, :len, :station, keyword_init: true)

        attr_reader :datestamp, :created, :format_version, :concept_doi, :zenodo_version_doi, :source_versions,
                    :build_commit, :changelog_url, :files, :conventions, :licences, :constituent_names

        # meta: the release document without its stations. stations: an
        # enumerator of [raw_station, pos, len]. files: [FileInfo]. checks:
        # {path => expected sha256} for #verify. io: the open .jsonl file in
        # stream mode (or nil). zenodo_version_doi: from the pointer or index
        # entry of this datestamp (the release document does not hold it).
        # on_bad_index: called (with the message) when a line read through the
        # stream index is not the station its entry names (spec §6.2, CR D4).
        def initialize(meta:, stations:, mode:, files:, checks:, io: nil, zenodo_version_doi: nil, on_bad_index: nil)
            @mode = mode
            @io = io
            @on_bad_index = on_bad_index
            @io_lock = Mutex.new
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

        def convention(convention_id)
            @convention_by_id[convention_id]
        end

        def licence(licence_id)
            @licence_by_id[licence_id]
        end

        def station_count
            @entries.size
        end

        def tombstone_count
            @tombstones.size
        end

        def stats
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
            raise InvalidArgumentError, "stations must be an Array of Station" unless stations.nil? || stations.is_a?(Array)
            ids = if stations.nil? || stations.empty?
                      @licences.map(&:licence_id)
                  else
                      out = Set.new
                      stations.each do |st|
                          raise InvalidArgumentError, "stations must be an Array of Station" unless st.is_a?(Station)
                          e = @by_id[st.station_id]
                          unless e && st.instance_variable_get(:@origin).equal?(self)
                              raise InvalidArgumentError, "station #{st.station_id} is not a station of release #{@datestamp}"
                          end
                          out << e.rec_licence_id if e.rec_licence_id
                          if e.type == :subordinate
                              out << e.offsets_licence_id if e.offsets_licence_id
                              ref = e.reference_id && @by_id[e.reference_id]
                              out << ref.rec_licence_id if ref && ref.rec_licence_id
                          end
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
            "Tidal constants: OpenTideConstants #{@datestamp}, #{ident}, CC BY 4.0. Sources: " + parts.join("; ")
        end

        # ---- station queries (spec §4.4)

        def station(station_id)
            check_id!(station_id)
            e = @by_id[station_id]
            e && materialize(e)
        end

        def require_station(station_id)
            check_id!(station_id)
            e = @by_id[station_id]
            return materialize(e) if e
            t = @tomb_by_id[station_id]
            raise StationRemovedError.new("station #{station_id} was removed in #{t.removed_in}", tombstone: t) if t
            raise StationNotFoundError, "no station #{station_id}"
        end

        def tombstone(station_id)
            check_id!(station_id)
            @tomb_by_id[station_id]
        end

        def station_by_alias(system, alias_id)
            unless (system.is_a?(String) || system.is_a?(Symbol)) && alias_id.is_a?(String)
                raise InvalidArgumentError, "system must be a String or Symbol and alias_id a String"
            end
            sid = @aliases.dig(system.to_s, alias_id)
            sid && station(sid)
        end

        def stations(**filters)
            filter(filters).map { |e| materialize(e) }.freeze
        end

        def iter_stations(**filters)
            list = filter(filters)
            return enum_for(:iter_stations, **filters) unless block_given?
            list.each { |e| yield materialize(e) }
            self
        end
        alias each_station iter_stations

        def search(name: nil, limit: nil, match: nil, **filters)
            raise InvalidArgumentError, "name must be a String" unless name.is_a?(String)
            check_limit!(limit)
            unless match.nil? || match.to_s == "exact"
                raise InvalidArgumentError, "match must be nil or :exact"
            end
            q = Fold.fold(utf8_query(name))
            raise InvalidArgumentError, "the query is empty" if q.empty?
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
            check_point!(lat, lon)
            unless real?(radius_km) && radius_km >= 0
                raise InvalidArgumentError, "radius_km must be a number >= 0"
            end
            check_limit!(limit)
            hits = distances(lat, lon, filters).select { |d, _| d <= radius_km }
            hits = hits.first(limit) if limit
            hits.map { |d, e| Nearby.new(materialize(e), d) }.freeze
        end

        def nearest(lat: nil, lon: nil, max_km: nil, **filters)
            check_point!(lat, lon)
            unless max_km.nil? || (real?(max_km) && max_km >= 0)
                raise InvalidArgumentError, "max_km must be nil or a number >= 0"
            end
            d, e = distances(lat, lon, filters).first
            return nil if e.nil? || (max_km && d > max_km)
            Nearby.new(materialize(e), d)
        end

        def reference_station(station)
            raise InvalidArgumentError, "station must be a Station" unless station.is_a?(Station)
            off = station.subordinate_offsets
            off && off.reference_station_id && station(off.reference_station_id)
        end

        def subordinates_of(station)
            raise InvalidArgumentError, "station must be a Station" unless station.is_a?(Station)
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
        # Hashes the release files again and compares them with OTC_{D}.sha256.
        def verify
            @checks.each do |path, expected|
                actual = Release.sha256_file(path)
                next if actual == expected
                raise ChecksumError.new("#{File.basename(path)}: SHA-256 mismatch", file: path, expected: expected, actual: actual)
            end
            true
        end

        def close
            @io_lock.synchronize { @io.close if @io && !@io.closed? }
            nil
        end

        # The resolved kind of each active station, {station_id => "tide" | "current" | "other" | nil},
        # for the stream index (spec §6.2). Used by the client.
        def index_kinds
            @entries.to_h { |e| [e.station_id, e.kind&.to_s] }
        end

        def default_url
            "https://data.opentideconstants.org/OTC_#{@datestamp}.json"
        end

        def check_id!(id)
            raise InvalidArgumentError, "station_id must be a String" unless id.is_a?(String)
        end

        # limit: nil for no limit, else an Integer of 1 or more (spec §4.4, CR D36).
        def check_limit!(limit)
            return if limit.nil?
            raise InvalidArgumentError, "limit must be nil or an Integer >= 1" unless limit.is_a?(Integer) && limit >= 1
        end

        # A finite real number (not a Complex, NaN or infinity).
        def real?(v)
            Release.real?(v)
        end

        # A real number that is finite as a double: an Integer too large for a
        # double (400 digits) is not.
        def self.real?(v)
            v.is_a?(Numeric) && v.real? && v.to_f.finite?
        end

        def check_point!(lat, lon)
            raise InvalidArgumentError, "lat must be a number in [-90, 90]" unless real?(lat) && lat >= -90 && lat <= 90
            raise InvalidArgumentError, "lon must be a number in [-180, 180]" unless real?(lon) && lon >= -180 && lon <= 180
        end

        # The query as a valid UTF-8 String; invalid_argument when it is not one.
        def utf8_query(name)
            q = name.encoding == Encoding::UTF_8 ? name : name.encode(Encoding::UTF_8)
            raise InvalidArgumentError, "name is not valid UTF-8" unless q.valid_encoding?
            q
        rescue EncodingError
            raise InvalidArgumentError, "name cannot be converted to UTF-8"
        end

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
            unknown = filters.keys - FILTER_KEYS
            raise InvalidArgumentError, "unknown filter #{unknown.first}" unless unknown.empty?
            f = {}
            filters.each do |k, v|
                next if v.nil?
                raise InvalidArgumentError, "filter #{k} must be a String or Symbol" unless v.is_a?(String) || v.is_a?(Symbol)
                f[k] = v.to_s
            end
            return @entries if f.empty?
            # A field that is null matches no filter value, also not "".
            same = ->(value, want) { !value.nil? && value.to_s == want }
            @entries.select do |e|
                (!f.key?(:country) || same.call(e.country, f[:country])) &&
                    (!f.key?(:type) || same.call(e.type, f[:type])) &&
                    (!f.key?(:kind) || same.call(e.kind, f[:kind])) &&
                    (!f.key?(:source) || e.sources.include?(f[:source])) &&
                    (!f.key?(:source_type) || same.call(e.rec_source_type, f[:source_type]))
            end
        end

        def materialize(e)
            return e.station if e.station
            line = @io_lock.synchronize do
                raise FileError.new("the release is closed", path: @io&.path) if @io.nil? || @io.closed?
                @io.seek(e.pos)
                @io.read(e.len)
            end
            raw = line && line.bytesize == e.len ? parse_station(line) : nil
            unless raw.is_a?(Hash) && raw["station_id"] == e.station_id
                bad_line!(e, raw.is_a?(Hash) ? "is #{raw['station_id'].inspect}" : "is not a station line")
            end
            build_station(raw, e.kind)
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

        def parse_station(line)
            JSON.parse(line.force_encoding(Encoding::UTF_8))
        rescue JSON::ParserError, EncodingError
            nil
        end

        def build_station(raw, kind)
            rec_id = raw["recommended_set_id"]
            all_validation = Array(raw["validation"]).map { |v| Validation.new(v) }
            sets = Array(raw["constant_sets"]).map do |cs|
                set_validation = all_validation.each_with_index.select { |v, _| v.set_id == cs["set_id"] }
                                               .sort_by { |v, i| [v.window.to_s, i] }.map(&:first)
                ConstantSet.new(cs, convention: @convention_by_id.fetch(cs["convention_id"]),
                                    licence: @licence_by_id.fetch(cs["licence_id"]),
                                    validation: set_validation, recommended: !rec_id.nil? && cs["set_id"] == rec_id)
            end
            Station.new(raw, sets: sets, kind: kind, validation: all_validation, origin: self)
        end

        # Checks every station and builds the indexes. In stream mode no
        # Station is kept.
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
            stations.each do |raw, pos, len|
                raise InvalidReleaseError, "a station is not an object" unless raw.is_a?(Hash)
                sid = raw["station_id"]
                raise InvalidReleaseError, "a station has no station_id" unless sid.is_a?(String)
                # One id across the active stations and the tombstones together (CR D5).
                raise InvalidReleaseError, "station_id #{sid} appears twice" unless ids.add?(sid)
                if raw["status"] == "removed"
                    Release.check_tombstone!(raw)
                    tombs << Tombstone.new(raw)
                    tomb_pos << [tombs.last, pos, len]
                    next
                end
                Release.check_station!(raw)
                entries << entry_for(raw, pos, len, names)
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
            entries.each { |e| e.kind = kind_of(e, []) }
            if @mode == :eager
                entries.each { |e| e.station = build_station(raws[e.station_id], e.kind) }
            end
            entries.each(&:freeze)
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
            Entry.new(station_id: sid, name: raw["name"], folded: Fold.fold(raw["name"].to_s), lat: raw["lat"],
                      lon: raw["lon"], type: Util.enum(raw["type"], ENUMS[:station_type]), country: raw["country"],
                      kind: rec && quantity_kind(rec["quantity"]), sources: sources.freeze,
                      rec_source_type: rec && Util.enum(rec["source_type"], ENUMS[:source_type]),
                      rec_licence_id: rec && rec["licence_id"], offsets_licence_id: off && off["licence_id"],
                      reference_id: off && off["reference_station_id"],
                      aliases: (raw["aliases"].is_a?(Hash) ? raw["aliases"].transform_values { |v| Array(v) } : {}),
                      pos: pos, len: len, station: nil)
        end

        # The JSON type of each known field that the SDK reads (spec §7.3:
        # tolerant is not lax; CR2 PK-R2-05). Absent or null is always allowed
        # here; required fields are checked where they are used. :t a String,
        # :n a finite number, :i a finite number with an integral value, :o an
        # object, :l a list of objects, :s a list of Strings, :a a list. The
        # same table is in the Python, TypeScript and C SDKs.
        STATION_TYPES = { "name" => :t, "country" => :t, "timezone" => :t, "type" => :t, "recommended_set_id" => :t,
                          "status" => :t, "constant_sets" => :l, "validation" => :l, "subordinate_offsets" => :o,
                          "current_offsets" => :a }.freeze
        OFFSET_TYPES = { "reference_station_id" => :t, "licence_id" => :t, "height_adjusted_type" => :t,
                         "time_offset_high_min" => :n, "time_offset_low_min" => :n, "height_offset_high" => :n,
                         "height_offset_low" => :n }.freeze
        VALIDATION_TYPES = { "set_id" => :t, "reference_source" => :t, "reference_station" => :t, "window" => :t,
                             "reference_distance_km" => :n, "time_mae_min" => :n, "time_p95_min" => :n,
                             "time_bias_min" => :n, "height_mae_m" => :n, "range_error_m" => :n,
                             "missed_events" => :i, "extra_events" => :i, "previous_release" => :o }.freeze
        SET_TYPES = { "set_id" => :t, "source" => :t, "source_type" => :t, "quantity" => :t, "source_record_id" => :t,
                      "source_version" => :t, "convention_id" => :t, "licence_id" => :t, "qc_status" => :t,
                      "constituents" => :l, "dropped_constituents" => :l, "qc_flags" => :l, "record_span" => :o,
                      "datum" => :o, "time_base" => :o, "provenance" => :o, "current_bins" => :a }.freeze
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
        def self.check_station!(raw)
            sid = raw["station_id"]
            what = "station #{sid}"
            raise InvalidReleaseError, "#{what}: name is not a string" unless raw["name"].is_a?(String)
            check_types!(raw, STATION_TYPES, what)
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

        # A station's kind comes from its recommended set, or from its
        # reference station if it is subordinate with offsets only.
        def kind_of(e, seen)
            return e.kind if e.kind
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
