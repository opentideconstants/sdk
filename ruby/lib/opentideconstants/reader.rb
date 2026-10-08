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
        def load(path, mode:, files:, checks:)
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
                load_jsonl(path, meta, mode: mode, files: files, checks: checks)
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

        def load_jsonl(path, meta, mode:, files:, checks:)
            io = File.open(path, "rb")
            lines = Enumerator.new do |y|
                pos = 0
                io.each_line do |line|
                    len = line.bytesize
                    unless line.strip.empty?
                        raw = parse_json(line.force_encoding(Encoding::UTF_8))
                        y << [raw, pos, len]
                    end
                    pos += len
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
