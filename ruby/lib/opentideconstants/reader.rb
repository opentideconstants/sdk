require "json"
require "zlib"

class OpenTideConstants
    # Reads release files from disk: .json, .json.gz, or .jsonl with its
    # .meta.json sidecar (spec §4.2, §6).
    module Reader
        NAME_RE = /\A(OTC_(\d{8}(?:\.\d+)?))\.(json\.gz|jsonl|json)\z/.freeze

        module_function

        # Splits "…/OTC_D.ext" into [prefix, datestamp, ext]; nil parts when the
        # name does not follow the pattern.
        def parse_name(path)
            base = File.basename(path)
            m = NAME_RE.match(base)
            return [m[1], m[2], m[3]] if m
            ext = base.end_with?(".json.gz") ? "json.gz" : File.extname(base).delete_prefix(".")
            [base.delete_suffix(".#{ext}"), nil, ext]
        end

        # The files a load of this path reads (the data file, plus .meta.json for .jsonl).
        def files_read(path)
            prefix, _, ext = parse_name(path)
            return [path, File.join(File.dirname(path), "#{prefix}.meta.json")] if ext == "jsonl"
            [path]
        end

        # Parses "<sha256>  <name>" lines into {name => sha256}.
        def parse_sha256(text)
            rows = {}
            text.each_line do |line|
                line = line.strip
                next if line.empty?
                digest, name = line.split(/\s+/, 2)
                next if name.nil?
                rows[name.delete_prefix("*").strip] = digest.downcase
            end
            rows
        end

        # Opens a local file given with file: (spec §4.2, §4.3.1).
        def open_file(path, mode:)
            raise InvalidArgumentError, "file must be a String path" unless path.is_a?(String) && !path.empty?
            path = File.expand_path(path)
            prefix, _, ext = parse_name(path)
            unless %w[json json.gz jsonl].include?(ext)
                raise InvalidArgumentError, "file must end in .json, .json.gz or .jsonl"
            end
            read = files_read(path)
            read.each { |p| raise FileError.new("no such file: #{p}", path: p) unless File.file?(p) }
            sha_path = File.join(File.dirname(path), "#{prefix}.sha256")
            if File.file?(sha_path)
                rows = parse_sha256(read_text(sha_path))
                checks = {}
                read.each do |p|
                    name = File.basename(p)
                    expected = rows[name]
                    if expected.nil?
                        raise ChecksumError.new("#{name} is not listed in #{File.basename(sha_path)}", file: p,
                                                expected: nil, actual: Release.sha256_file(p))
                    end
                    checks[p] = expected
                end
                files = rows.keys.sort.map do |name|
                    local = File.join(File.dirname(path), name)
                    FileInfo.new(name: name, url: nil, size: File.file?(local) ? File.size(local) : nil, sha256: rows[name])
                end
                verify_checks(checks)
                [load(path, mode: mode, files: files, checks: checks), :file]
            else
                files = read.map { |p| FileInfo.new(name: File.basename(p), url: nil, size: File.size(p), sha256: nil) }
                [load(path, mode: mode, files: files, checks: {}), :file_unverified]
            end
        end

        def verify_checks(checks)
            checks.each do |p, expected|
                actual = Release.sha256_file(p)
                next if actual == expected
                raise ChecksumError.new("#{File.basename(p)}: SHA-256 mismatch", file: p, expected: expected, actual: actual)
            end
        end

        # Loads a release from a data file whose checks are already done.
        def load(path, mode:, files:, checks:, index: nil, index_rows: nil)
            _, _, ext = parse_name(path)
            case ext
            when "json"
                doc = parse_json(read_text(path))
                eager_from_doc(doc, files: files, checks: checks)
            when "json.gz"
                doc = parse_json(gunzip(path))
                eager_from_doc(doc, files: files, checks: checks)
            when "jsonl"
                meta_path = files_read(path)[1]
                meta = parse_json(read_text(meta_path))
                Release.check_format!(meta)
                load_jsonl(path, meta, mode: mode, files: files, checks: checks, index: index, index_rows: index_rows)
            else
                raise InvalidArgumentError, "unknown release file type: #{path}"
            end
        end

        def eager_from_doc(doc, files:, checks:)
            Release.check_format!(doc)
            stations = doc["stations"]
            raise InvalidReleaseError, "stations missing" unless stations.is_a?(Array)
            meta = doc.reject { |k, _| k == "stations" }
            Release.new(meta: meta, stations: stations.map { |s| [s, nil, nil] }, mode: :eager,
                        files: files, checks: checks)
        end

        # index: the entries of a fresh index-v1.json (spec §6.2); the stations
        # then come from it, and only the tombstone lines are read. Otherwise
        # every line is read, and index_rows (an Array, if given) gets the
        # index entry of each line.
        def load_jsonl(path, meta, mode:, files:, checks:, index: nil, index_rows: nil)
            io = File.open(path, "rb")
            lines = Enumerator.new do |y|
                if index
                    index.each { |e| y << [raw_from_index(e, io), e["offset"], e["length"]] }
                else
                    pos = 0
                    io.each_line do |line|
                        body = line.chomp
                        unless line.strip.empty?
                            raw = parse_json(body.force_encoding(Encoding::UTF_8))
                            index_rows << index_entry(raw, pos, body.bytesize) if index_rows && raw.is_a?(Hash)
                            y << [raw, pos, body.bytesize]
                        end
                        pos += line.bytesize
                    end
                end
            end
            begin
                rel = Release.new(meta: meta, stations: lines, mode: mode, files: files, checks: checks,
                                  io: mode == :stream ? io : nil)
            ensure
                io.close if mode != :stream || rel.nil?
            end
            rel
        rescue SystemCallError, IOError => e
            raise FileError.new("cannot read #{path}: #{e.message}", path: path)
        end

        SET_KEYS = %w[set_id source source_type quantity qc_status convention_id licence_id].freeze
        ENTRY_STR = %w[name name_folded country type kind reference_station_id offsets_licence_id recommended_set_id].freeze

        # The stream index entry of one line (spec §6.2). "kind" is the
        # station's own kind; the client sets the resolved kind.
        def index_entry(raw, pos, len)
            str = ->(h, k) { h.is_a?(Hash) && h[k].is_a?(String) ? h[k] : nil }
            num = ->(k) { raw[k].is_a?(Numeric) ? raw[k] : nil }
            off = raw["subordinate_offsets"].is_a?(Hash) ? raw["subordinate_offsets"] : {}
            rec_id = str.call(raw, "recommended_set_id")
            kind = nil
            sets = (raw["constant_sets"].is_a?(Array) ? raw["constant_sets"] : []).map do |cs|
                cs = {} unless cs.is_a?(Hash)
                if !rec_id.nil? && cs["set_id"] == rec_id
                    kind = { "water_level" => "tide", "current" => "current" }.fetch(cs["quantity"], "other")
                end
                SET_KEYS.to_h { |k| [k, str.call(cs, k)] }.merge(
                    "constituents" => Array(cs["constituents"]).filter_map { |c| c["name"] if c.is_a?(Hash) && c["name"].is_a?(String) }
                )
            end
            name = str.call(raw, "name")
            aliases = (raw["aliases"].is_a?(Hash) ? raw["aliases"] : {}).transform_values do |v|
                v.is_a?(String) ? [v] : Array(v).grep(String)
            end
            { "offset" => pos, "length" => len, "station_id" => raw["station_id"], "status" => raw["status"],
              "name" => name, "name_folded" => name && Fold.fold(name), "country" => str.call(raw, "country"),
              "type" => str.call(raw, "type"), "lat" => num.call("lat"), "lon" => num.call("lon"), "kind" => kind,
              "aliases" => aliases, "reference_station_id" => str.call(off, "reference_station_id"),
              "offsets_licence_id" => str.call(off, "licence_id"), "recommended_set_id" => rec_id, "sets" => sets }
        end

        # True when e has every key of an index entry with the right type (spec §6.2).
        def index_entry_ok?(e)
            return false unless e.is_a?(Hash) && e["offset"].is_a?(Integer) && e["length"].is_a?(Integer)
            return false unless e["station_id"].is_a?(String) && e["status"].is_a?(String)
            return false unless ENTRY_STR.all? { |k| e.key?(k) && (e[k].nil? || e[k].is_a?(String)) }
            return false unless %w[lat lon].all? { |k| e.key?(k) && (e[k].nil? || e[k].is_a?(Numeric)) }
            return false unless e["aliases"].is_a?(Hash) && e["aliases"].values.all? { |v| v.is_a?(Array) && v.all?(String) }
            return false unless e["sets"].is_a?(Array)
            e["sets"].all? do |cs|
                cs.is_a?(Hash) && SET_KEYS.all? { |k| cs.key?(k) && (cs[k].nil? || cs[k].is_a?(String)) } &&
                    cs["constituents"].is_a?(Array) && cs["constituents"].all?(String)
            end
        end

        # The station document a load needs, from an index entry. A tombstone's
        # own line is read (the index does not hold removed_in and removed_reason).
        def raw_from_index(e, io)
            if e["status"] == "removed"
                io.seek(e["offset"])
                return parse_json(io.read(e["length"]).to_s.force_encoding(Encoding::UTF_8))
            end
            raw = e.slice("station_id", "status", "name", "country", "type", "lat", "lon", "recommended_set_id", "aliases")
            raw["constant_sets"] = e["sets"].map do |cs|
                cs.reject { |k, _| k == "constituents" }.merge("constituents" => cs["constituents"].map { |n| { "name" => n } })
            end
            if e["reference_station_id"] || e["offsets_licence_id"]
                raw["subordinate_offsets"] = { "reference_station_id" => e["reference_station_id"],
                                               "licence_id" => e["offsets_licence_id"] }
            end
            raw
        end

        def read_text(path)
            File.read(path, mode: "rb").force_encoding(Encoding::UTF_8)
        rescue SystemCallError, IOError => e
            raise FileError.new("cannot read #{path}: #{e.message}", path: path)
        end

        def gunzip(path)
            Zlib::GzipReader.open(path) { |gz| gz.read }.force_encoding(Encoding::UTF_8)
        rescue Zlib::Error => e
            raise InvalidReleaseError, "bad gzip file #{path}: #{e.message}"
        rescue SystemCallError, IOError => e
            raise FileError.new("cannot read #{path}: #{e.message}", path: path)
        end

        def parse_json(text)
            JSON.parse(text)
        rescue JSON::ParserError, EncodingError => e
            raise InvalidReleaseError, "not valid JSON: #{e.message[0, 200]}"
        end
    end
end
