require "json"
require "zlib"
require "digest"
require "stringio"

class OpenTideConstants
    # Reads release files from disk: .json, .json.gz, or .jsonl with its
    # .meta.json sidecar (spec §4.2, §6).
    module Reader
        # OTC_<D>.<ext>, with <D> a valid datestamp (DATESTAMP_RE).
        NAME_RE = /\A(OTC_([0-9]{8}(?:\.[2-9]|\.[1-9][0-9]{1,8})?))\.(json\.gz|jsonl|json)\z/.freeze

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

        # One sha256sum line: 64 hex digits, spaces or tabs, an optional "*",
        # the name without trailing white space (CR2 DR41, the same grammar in
        # every SDK). A blank line holds ASCII white space only.
        SHA256_LINE = /\A(\h{64})[ \t]+\*?(.*?[^ \t\r\n\v\f])[ \t\r\n\v\f]*\z/.freeze
        SHA256_BLANK = /\A[ \t\r\n\v\f]*\z/.freeze

        # Parses "<sha256>  <name>" lines into {name => sha256} (lower case).
        # A line in any other form is invalid_release (source names the file).
        # So is a file that is not UTF-8 or that names a file twice, so that
        # row order never decides a check (CR2 DR14).
        def parse_sha256(text, source = "the .sha256 file")
            text = text.dup.force_encoding(Encoding::UTF_8)
            raise InvalidReleaseError, "#{source} is not UTF-8" unless text.valid_encoding?
            rows = {}
            text.split("\n", -1).each.with_index(1) do |line, n|
                next if line.match?(SHA256_BLANK)
                m = SHA256_LINE.match(line)
                raise InvalidReleaseError, "#{source} line #{n} is not \"<sha256>  <name>\": #{line[0, 100].inspect}" unless m
                raise InvalidReleaseError, "#{source} lists #{m[2]} twice (line #{n})" if rows.key?(m[2])
                rows[m[2]] = m[1].downcase
            end
            rows
        end

        # Opens a local file given with file: (spec §4.2, §4.3.1).
        def open_file(path, mode:, logger: nil, commercial_only: false, commercial_basis: :strict, historical_offsets_policy: :fallback)
            raise InvalidArgumentError, "file must be a String path" unless path.is_a?(String) && !path.empty?
            path = File.expand_path(path)
            prefix, d, ext = parse_name(path)
            unless d
                raise InvalidArgumentError, "file must be named OTC_<datestamp>.json, .json.gz or .jsonl, " \
                                            "not #{File.basename(path).inspect}"
            end
            # A .json or .json.gz file has no lines to seek to: never load it
            # eagerly in silence (CR T94, spec §4.2).
            raise InvalidArgumentError, "stream mode needs .jsonl and .meta.json" if mode == :stream && ext != "jsonl"
            read = files_read(path)
            read.each { |p| raise FileError.new("no such file: #{p}", path: p) unless File.file?(p) }
            sha_path = File.join(File.dirname(path), "#{prefix}.sha256")
            if File.file?(sha_path)
                rows = parse_sha256(read_text(sha_path), File.basename(sha_path))
                # Every release file the open reads needs a row, checked
                # before any file is hashed (spec §5.3, CR3 DR73); a
                # .json.gz also needs the .json row that its decompressed
                # bytes are checked against (CR3 DR77).
                need_rows!(path, read, rows, File.basename(sha_path))
                checks = read.to_h { |p| [p, rows[File.basename(p)]] }
                files = rows.keys.sort.map do |name|
                    local = File.join(File.dirname(path), name)
                    FileInfo.new(name: name, url: nil, size: File.file?(local) ? File.size(local) : nil, sha256: rows[name])
                end
                json_sha256 = ext == "json.gz" ? rows["#{prefix}.json"] : nil
                [load(path, mode: mode, files: files, checks: checks, verify: true, logger: logger,
                      commercial_only: commercial_only, commercial_basis: commercial_basis, historical_offsets_policy: historical_offsets_policy, json_sha256: json_sha256), :file]
            else
                files = read.map { |p| FileInfo.new(name: File.basename(p), url: nil, size: File.size(p), sha256: nil) }
                [load(path, mode: mode, files: files, checks: {}, logger: logger, commercial_only: commercial_only, commercial_basis: commercial_basis, historical_offsets_policy: historical_offsets_policy),
                 :file_unverified]
            end
        end

        # Raises ChecksumError "not listed" for the first release file that a
        # local open of path (or verify on it) reads and that rows lacks: the
        # files read, and for a .json.gz also the .json (spec §5.3, CR3 DR73,
        # DR77). The file named is the one missing.
        def need_rows!(path, read, rows, sha_name)
            names = read.map { |p| File.basename(p) }
            names << File.basename(path).delete_suffix(".gz") if path.end_with?(".json.gz")
            names.each do |name|
                next if rows.key?(name)
                raise ChecksumError.new("#{name} is not listed in #{sha_name}", file: File.join(File.dirname(path), name),
                                        expected: nil, actual: nil)
            end
        end

        # Raises ChecksumError unless the decompressed bytes of a .json.gz
        # (gz_path) have the SHA-256 of its .json row (spec §5.3, CR3 DR77).
        def check_json_bytes!(gz_path, text, expected)
            actual = Digest::SHA256.hexdigest(text.b)
            return if actual == expected
            json_path = gz_path.delete_suffix(".gz")
            raise ChecksumError.new("#{File.basename(json_path)} (decompressed from #{File.basename(gz_path)}): SHA-256 mismatch",
                                    file: json_path, expected: expected, actual: actual)
        end

        # Raises ChecksumError unless the SHA-256 of bytes (read from path) is expected.
        def check_bytes!(path, bytes, expected)
            actual = Digest::SHA256.hexdigest(bytes)
            return if actual == expected
            raise ChecksumError.new("#{File.basename(path)}: SHA-256 mismatch", file: path, expected: expected, actual: actual)
        end

        # Loads a release from a data file. With verify: true each file is
        # hashed from the same bytes (or the same open file) that the load
        # then reads, against checks {path => sha256}, so a file swapped
        # after its hash is never used.
        # logger: where a station with an unknown status is reported (CR2 DR8).
        # commercial_only: the open option of spec §4.2 (K-NC DR106).
        # json_sha256: for a .json.gz, the .json row that the decompressed
        # bytes must match (spec §5.3, CR3 DR77).
        def load(path, mode:, files:, checks:, index: nil, index_rows: nil, zenodo_version_doi: nil, verify: false,
                 on_bad_index: nil, logger: nil, commercial_only: false, commercial_basis: :strict, historical_offsets_policy: :fallback, json_sha256: nil)
            _, _, ext = parse_name(path)
            expect = ->(p) { verify ? checks[p] : nil }
            case ext
            when "json"
                doc = parse_json(read_text(path, expect.call(path)))
                eager_from_doc(doc, files: files, checks: checks, zenodo_version_doi: zenodo_version_doi, logger: logger,
                                    commercial_only: commercial_only, commercial_basis: commercial_basis, historical_offsets_policy: historical_offsets_policy)
            when "json.gz"
                text = gunzip(path, expect.call(path))
                check_json_bytes!(path, text, json_sha256) if json_sha256
                doc = parse_json(text)
                eager_from_doc(doc, files: files, checks: checks, zenodo_version_doi: zenodo_version_doi, logger: logger,
                                    commercial_only: commercial_only, commercial_basis: commercial_basis, historical_offsets_policy: historical_offsets_policy)
            when "jsonl"
                meta_path = files_read(path)[1]
                meta = parse_json(read_text(meta_path, expect.call(meta_path)))
                Release.check_format!(meta)
                load_jsonl(path, meta, mode: mode, files: files, checks: checks, index: index, index_rows: index_rows,
                                       zenodo_version_doi: zenodo_version_doi, expected_sha256: expect.call(path),
                                       on_bad_index: on_bad_index, logger: logger, commercial_only: commercial_only, commercial_basis: commercial_basis, historical_offsets_policy: historical_offsets_policy)
            else
                raise InvalidArgumentError, "unknown release file type: #{path}"
            end
        end

        def eager_from_doc(doc, files:, checks:, zenodo_version_doi: nil, logger: nil, commercial_only: false, commercial_basis: :strict, historical_offsets_policy: :fallback)
            Release.check_format!(doc)
            stations = doc["stations"]
            raise InvalidReleaseError, "stations missing" unless stations.is_a?(Array)
            meta = doc.reject { |k, _| k == "stations" }
            Release.new(meta: meta, stations: stations.map { |s| [s, nil, nil] }, mode: :eager,
                        files: files, checks: checks, zenodo_version_doi: zenodo_version_doi, logger: logger,
                        commercial_only: commercial_only, commercial_basis: commercial_basis, historical_offsets_policy: historical_offsets_policy)
        end

        # index: the entries of a fresh index-v1.json (spec §6.2); the stations
        # then come from it, and only the tombstone lines are read. Otherwise
        # every line is read, and index_rows (an Array, if given) gets the
        # index entry of each line.
        def load_jsonl(path, meta, mode:, files:, checks:, index: nil, index_rows: nil, zenodo_version_doi: nil,
                       expected_sha256: nil, on_bad_index: nil, logger: nil, commercial_only: false, commercial_basis: :strict, historical_offsets_policy: :fallback)
            io = File.open(path, "rb")
            if expected_sha256
                digest = Digest::SHA256.new
                while (chunk = io.read(1 << 16))
                    digest << chunk
                end
                io.rewind
                actual = digest.hexdigest
                unless actual == expected_sha256
                    io.close
                    raise ChecksumError.new("#{File.basename(path)}: SHA-256 mismatch", file: path, expected: expected_sha256,
                                                                                         actual: actual)
                end
            end
            lines = Enumerator.new do |y|
                if index
                    index.each { |e| y << [raw_from_index(e, io), e["offset"], e["length"], line_view(e)] }
                else
                    pos = 0
                    io.each_line do |line|
                        body = line.chomp
                        unless blank?(line)
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
                                  io: mode == :stream ? io : nil, zenodo_version_doi: zenodo_version_doi,
                                  on_bad_index: index && on_bad_index, logger: logger, commercial_only: commercial_only, commercial_basis: commercial_basis, historical_offsets_policy: historical_offsets_policy)
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
                    "fallback" => cs["fallback"], "current_bins" => Array(cs["current_bins"]).map { |b| b.is_a?(Hash) ? b["bin"] : b },
                    "source_record_id" => cs["source_record_id"], "source_version" => cs["source_version"], "datum" => cs["datum"],
                    "constituents" => Array(cs["constituents"]).filter_map { |c| c["name"] if c.is_a?(Hash) && c["name"].is_a?(String) }
                )
            end
            name = str.call(raw, "name")
            aliases = (raw["aliases"].is_a?(Hash) ? raw["aliases"] : {}).transform_values do |v|
                v.is_a?(String) ? [v] : Array(v).grep(String)
            end
            # A line with no status is an active station to the load, so its entry says so (a nil
            # status would make the index stale on every open).
            status = raw["status"].is_a?(String) ? raw["status"] : "active"
            { "offset" => pos, "length" => len, "station_id" => raw["station_id"], "status" => status,
              "name" => name, "name_folded" => name && Fold.fold(name), "country" => str.call(raw, "country"),
              "type" => str.call(raw, "type"), "lat" => num.call("lat"), "lon" => num.call("lon"), "kind" => kind,
              "aliases" => aliases, "reference_station_id" => str.call(off, "reference_station_id"),
              "offsets_licence_id" => str.call(off, "licence_id"), "recommended_set_id" => rec_id, "sets" => sets,
              "subordinate_offsets" => raw["subordinate_offsets"], "current_offsets" => raw.fetch("current_offsets", []) }
        end

        # The keys of an index entry that a line read through the index must
        # give as they are (PK-R2-07): the status, the references and the
        # sets. The other keys are used as the index gives them (spec §6.2).
        def line_view(e, legacy: !e.key?("subordinate_offsets"))
            sets = e["sets"].is_a?(Array) ? e["sets"] : []
            view = [e["station_id"], e["status"], e["recommended_set_id"], e["reference_station_id"], e["offsets_licence_id"],
                    sets.map do |cs|
                        fields = SET_KEYS.map { |k| cs[k] } + [cs["constituents"], cs["fallback"], cs["current_bins"]]
                        fields += [cs["source_record_id"], cs["source_version"], cs["datum"]] unless legacy
                        fields
                    end]
            view << e["subordinate_offsets"] unless legacy
            view << e["current_offsets"]
        end

        # v as an Integer when it is a JSON integer or a number with an
        # integral value (12.0); any other value as it is (CR2 DR10).
        def integral(v)
            v.is_a?(Float) && v.finite? && v == v.floor ? v.to_i : v
        end

        # True when e has every key of an index entry with the right type (spec §6.2).
        def index_entry_ok?(e, legacy: false)
            return false unless e.is_a?(Hash) && e["offset"].is_a?(Integer) && e["length"].is_a?(Integer)
            return false unless e["station_id"].is_a?(String) && e["status"].is_a?(String)
            return false unless ENTRY_STR.all? { |k| e.key?(k) && (e[k].nil? || e[k].is_a?(String)) }
            return false unless %w[lat lon].all? { |k| e.key?(k) && (e[k].nil? || e[k].is_a?(Numeric)) }
            return false unless e["aliases"].is_a?(Hash) && e["aliases"].values.all? { |v| v.is_a?(Array) && v.all?(String) }
            return false unless legacy || (e.key?("subordinate_offsets") && (e["subordinate_offsets"].nil? || e["subordinate_offsets"].is_a?(Hash)))
            return false unless e["current_offsets"].is_a?(Array) && e["current_offsets"].all?(Hash)
            return false unless e["sets"].is_a?(Array)
            e["sets"].all? do |cs|
                cs.is_a?(Hash) && SET_KEYS.all? { |k| cs.key?(k) && (cs[k].nil? || cs[k].is_a?(String)) } &&
                    cs.key?("fallback") && (cs["fallback"].nil? || cs["fallback"].is_a?(Hash)) &&
                    cs["current_bins"].is_a?(Array) && cs["current_bins"].all? { |b| b.is_a?(Numeric) && b.finite? && b == b.to_i && b.between?(1, 2**53 - 1) } &&
                    (legacy || %w[source_record_id source_version datum].all? { |k| cs.key?(k) }) &&
                    cs["constituents"].is_a?(Array) && cs["constituents"].all?(String)
            end
        end

        # The station document a load needs, from an index entry. A tombstone's
        # own line is read (the index does not hold removed_in and removed_reason).
        def raw_from_index(e, io)
            if e["status"] == "removed"
                io.seek(e["offset"])
                raw = parse_json(io.read(e["length"]).to_s.force_encoding(Encoding::UTF_8))
                unless raw.is_a?(Hash) && raw["station_id"] == e["station_id"]
                    raise InvalidReleaseError, "index-v1.json: the line at #{e['offset']} is not #{e['station_id']}"
                end
                unless line_view(index_entry(raw, e["offset"], e["length"]), legacy: !e.key?("subordinate_offsets")) == line_view(e)
                    raise InvalidReleaseError, "index-v1.json: the line at #{e['offset']} does not give the entry of #{e['station_id']}"
                end
                return raw
            end
            raw = e.slice("station_id", "status", "name", "country", "type", "lat", "lon", "recommended_set_id", "aliases")
            raw["constant_sets"] = e["sets"].map do |cs|
                cs.reject { |k, _| k == "constituents" }.merge("constituents" => cs["constituents"].map { |n| { "name" => n } })
            end
            raw["subordinate_offsets"] = if e.key?("subordinate_offsets")
                e["subordinate_offsets"]
            elsif e["reference_station_id"] || e["offsets_licence_id"]
                { "reference_station_id" => e["reference_station_id"], "licence_id" => e["offsets_licence_id"] }
            end
            raw["current_offsets"] = e["current_offsets"]
            raw
        end

        # The bytes of path as UTF-8; checked against expected_sha256 when given.
        def read_text(path, expected_sha256 = nil)
            bytes = File.binread(path)
            check_bytes!(path, bytes, expected_sha256) if expected_sha256
            bytes.force_encoding(Encoding::UTF_8)
        rescue SystemCallError, IOError => e
            raise FileError.new("cannot read #{path}: #{e.message}", path: path)
        end

        # The decompressed text of a .gz file; the compressed bytes are
        # checked against expected_sha256 when given.
        def gunzip(path, expected_sha256 = nil)
            bytes = File.binread(path)
            check_bytes!(path, bytes, expected_sha256) if expected_sha256
            # zcat reads every gzip member, not only the first.
            Zlib::GzipReader.zcat(StringIO.new(bytes)).force_encoding(Encoding::UTF_8)
        rescue Zlib::Error => e
            raise InvalidReleaseError, "bad gzip file #{path}: #{e.message}"
        rescue SystemCallError, IOError => e
            raise FileError.new("cannot read #{path}: #{e.message}", path: path)
        end

        # True when a .jsonl line holds only ASCII whitespace: SP, HT, LF, VT, FF,
        # CR (spec 6.2, CR2 DR26). String#strip also drops NUL, which is not blank.
        def blank?(line)
            line.b.match?(/\A[ \t\n\v\f\r]*\z/n)
        end

        def parse_json(text)
            raise InvalidReleaseError, "not valid UTF-8" unless text.valid_encoding?
            Util.no_lone_surrogate!(text)
            JSON.parse(text)
        rescue JSON::ParserError, EncodingError => e
            raise InvalidReleaseError, "not valid JSON: #{e.message[0, 200]}"
        end
    end
end
