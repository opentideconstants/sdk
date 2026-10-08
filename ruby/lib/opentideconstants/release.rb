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

        # A small per-station summary, used by the filters and the indexes.
        Entry = Struct.new(:station_id, :name, :folded, :lat, :lon, :type, :country, :kind, :sources,
                           :rec_source_type, :rec_licence_id, :offsets_licence_id, :reference_id,
                           :pos, :len, :station, keyword_init: true)

        attr_reader :datestamp, :created, :format_version, :doi, :concept_doi, :source_versions,
                    :build_commit, :changelog_url, :files, :conventions, :licences, :constituent_names

        # meta: the release document without its stations. stations: an
        # enumerator of [raw_station, pos, len]. files: [FileInfo]. checks:
        # {path => expected sha256} for #verify. io: the open .jsonl file in
        # stream mode (or nil).
        def initialize(meta:, stations:, mode:, files:, checks:, io: nil)
            @mode = mode
            @io = io
            @io_lock = Mutex.new
            @files = files.sort_by(&:name).freeze
            @checks = checks.freeze
            Util.deep_freeze(meta)
            Release.check_format!(meta)
            rel = meta["release"]
            raise InvalidReleaseError, "release object missing" unless rel.is_a?(Hash) && rel["datestamp"].is_a?(String)
            @datestamp = rel["datestamp"]
            @created = Util.time(rel["created"])
            @format_version = meta["format_version"]
            @doi = rel["doi"]
            @concept_doi = rel["concept_doi"]
            @source_versions = (rel["source_versions"] || {}).freeze
            @build_commit = rel["build_commit"]
            @changelog_url = rel["changelog_url"]
            @conventions = Array(meta["conventions"]).map { |c| Convention.new(c) }.freeze
            @licences = Array(meta["licences"]).map { |l| Licence.new(l) }.freeze
            @convention_by_id = @conventions.to_h { |c| [c.convention_id, c] }.freeze
            @licence_by_id = @licences.to_h { |l| [l.licence_id, l] }.freeze
            load_stations(stations)
            freeze
        end

        # Raises unsupported_format unless the format major is supported (§7.4).
        def self.check_format!(meta)
            raise InvalidReleaseError, "not a release document" unless meta.is_a?(Hash)
            fv = meta["format_version"]
            raise InvalidReleaseError, "format_version missing" unless fv.is_a?(String) && fv =~ /\A(\d+)\.(\d+)\z/
            major = Regexp.last_match(1).to_i
            unless SUPPORTED_FORMAT_MAJORS.include?(major)
                raise UnsupportedFormatError, "format_version #{fv} is not supported (supported majors: #{SUPPORTED_FORMAT_MAJORS.join(', ')})"
            end
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
            count = ->(values) { values.compact.tally.sort.to_h.freeze }
            Stats.new(type: count.call(@entries.map(&:type)), kind: count.call(@entries.map(&:kind)),
                      country: count.call(@entries.map(&:country)), source: count.call(@set_sources),
                      qc_status: count.call(@set_qc))
        end

        def citation
            year = @created ? @created.year : @datestamp[0, 4]
            ident = @doi ? "https://doi.org/#{@doi}" : default_url
            "OpenTideConstants (#{year}). OpenTideConstants tidal constants, release #{@datestamp} " \
                "(format #{@format_version}). CC BY 4.0. #{ident}"
        end

        # The CC BY 4.0 attribution text for what an app shows (spec §4.6).
        def attribution(stations = nil)
            ids = if stations.nil?
                      @licences.map(&:licence_id)
                  else
                      raise InvalidArgumentError, "stations must be an Array of Station" unless stations.is_a?(Array)
                      out = Set.new
                      stations.each do |st|
                          raise InvalidArgumentError, "stations must be an Array of Station" unless st.is_a?(Station)
                          e = @by_id[st.station_id]
                          next unless e
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
                next if lic.nil? || seen.include?(lic.provider)
                seen << lic.provider
                parts << "#{lic.provider}: #{lic.attribution}"
            end
            ident = @doi ? "doi:#{@doi}" : default_url
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
            q = Fold.fold(name)
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
            unless radius_km.is_a?(Numeric) && radius_km.finite? && radius_km >= 0
                raise InvalidArgumentError, "radius_km must be a number >= 0"
            end
            check_limit!(limit)
            hits = distances(lat, lon, filters).select { |d, _| d <= radius_km }
            hits = hits.first(limit) if limit
            hits.map { |d, e| Nearby.new(materialize(e), d) }.freeze
        end

        def nearest(lat: nil, lon: nil, max_km: nil, **filters)
            check_point!(lat, lon)
            unless max_km.nil? || (max_km.is_a?(Numeric) && max_km.finite? && max_km >= 0)
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

        def default_url
            "https://data.opentideconstants.org/OTC_#{@datestamp}.json"
        end

        def check_id!(id)
            raise InvalidArgumentError, "station_id must be a String" unless id.is_a?(String)
        end

        def check_limit!(limit)
            return if limit.nil?
            raise InvalidArgumentError, "limit must be an Integer >= 0" unless limit.is_a?(Integer) && limit >= 0
        end

        def check_point!(lat, lon)
            unless lat.is_a?(Numeric) && lat.finite? && lat >= -90 && lat <= 90
                raise InvalidArgumentError, "lat must be a number in [-90, 90]"
            end
            unless lon.is_a?(Numeric) && lon.finite? && lon >= -180 && lon <= 180
                raise InvalidArgumentError, "lon must be a number in [-180, 180]"
            end
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
            @entries.select do |e|
                (!f.key?(:country) || e.country == f[:country]) &&
                    (!f.key?(:type) || e.type.to_s == f[:type]) &&
                    (!f.key?(:kind) || e.kind.to_s == f[:kind]) &&
                    (!f.key?(:source) || e.sources.include?(f[:source])) &&
                    (!f.key?(:source_type) || e.rec_source_type.to_s == f[:source_type])
            end
        end

        def materialize(e)
            return e.station if e.station
            line = @io_lock.synchronize do
                raise FileError.new("the release is closed", path: @io&.path) if @io.nil? || @io.closed?
                @io.seek(e.pos)
                @io.read(e.len)
            end
            build_station(parse_station(line), e.kind)
        rescue SystemCallError, IOError => err
            raise FileError.new("cannot read station #{e.station_id}: #{err.message}", path: @io&.path)
        end

        def parse_station(line)
            JSON.parse(line)
        rescue JSON::ParserError => err
            raise InvalidReleaseError, "bad station line: #{err.message}"
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
            Station.new(raw, sets: sets, kind: kind, validation: all_validation)
        end

        # Checks every station and builds the indexes. In stream mode no
        # Station is kept.
        def load_stations(stations)
            entries = []
            tombs = []
            raws = {}
            names = Set.new
            @set_sources = []
            @set_qc = []
            stations.each do |raw, pos, len|
                raise InvalidReleaseError, "a station is not an object" unless raw.is_a?(Hash)
                sid = raw["station_id"]
                raise InvalidReleaseError, "a station has no station_id" unless sid.is_a?(String)
                if raw["status"] == "removed"
                    tombs << Tombstone.new(raw)
                    next
                end
                entries << entry_for(raw, pos, len, names)
                raws[sid] = raw if @mode == :eager
            end
            entries.sort_by!(&:station_id)
            @by_id = entries.to_h { |e| [e.station_id, e] }
            entries.each { |e| e.kind = kind_of(e, []) }
            if @mode == :eager
                entries.each { |e| e.station = build_station(raws[e.station_id], e.kind) }
            end
            entries.each(&:freeze)
            @entries = entries.freeze
            @by_id.freeze
            @tombstones = tombs.sort_by(&:station_id).freeze
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
                unless @convention_by_id.key?(cs["convention_id"])
                    raise InvalidReleaseError, "set #{cs['set_id']}: convention #{cs['convention_id'].inspect} does not resolve"
                end
                unless @licence_by_id.key?(cs["licence_id"])
                    raise InvalidReleaseError, "set #{cs['set_id']}: licence #{cs['licence_id'].inspect} does not resolve"
                end
                rec = cs if !rec_id.nil? && cs["set_id"] == rec_id
                sources << cs["source"] unless cs["qc_status"] == "excluded"
                @set_sources << cs["source"]
                @set_qc << Util.enum(cs["qc_status"], ENUMS[:qc_status])
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
                      reference_id: off && off["reference_station_id"], pos: pos, len: len, station: nil)
        end

        def quantity_kind(q)
            case q
            when "water_level" then :tide
            when "current" then :current
            when nil then nil
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

        def index_aliases(sid, aliases)
            @aliases ||= Hash.new { |h, k| h[k] = {} }
            return unless aliases.is_a?(Hash)
            aliases.each do |system, ids|
                (ids.is_a?(Array) ? ids : [ids]).each { |id| @aliases[system.to_s][id] = sid }
            end
        end
    end
end
