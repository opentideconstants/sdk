require "json"
require "digest"
require "time"
begin
    require "json_schemer"
rescue LoadError
    warn "INCOMPLETE: json_schemer is required; configure GEM_HOME/GEM_PATH for the validator dependency"
    exit 2
end

module CanonicalCache
    DIRECTORY = File.expand_path(__dir__)
    SCHEMAS = JSON.parse(File.read(File.join(DIRECTORY, "writer-schemas.json")))
    SCENARIOS = JSON.parse(File.read(File.join(DIRECTORY, "scenarios.json")))

    class Incomplete < StandardError; end

    # Independent arithmetic oracle: search 1..17 significant digits using
    # exact rational distances, then apply the approved notation boundaries.
    def self.number(value)
        raise ArgumentError, "nonfinite binary64" unless value.finite?
        return "0" if value.zero?
        negative = value.negative?
        absolute = value.abs
        rational = absolute.to_r
        exponent = Math.log10(absolute).floor
        exponent -= 1 while rational < 10.to_r**exponent
        exponent += 1 while rational >= 10.to_r**(exponent + 1)
        chosen = nil
        scale = nil
        (1..17).each do |digits|
            power = exponent - digits + 1
            unit = 10.to_r**power
            lower = (rational / unit).floor
            candidates = [lower, lower + 1].select do |coefficient|
                Float("#{coefficient}e#{power}") == absolute
            end
            next if candidates.empty?
            chosen = candidates.min_by { |coefficient| [(coefficient * unit - rational).abs, coefficient.odd? ? 1 : 0] }
            scale = power
            break
        end
        raise ArgumentError, "no binary64 roundtrip" unless chosen
        while (chosen % 10).zero?
            chosen /= 10
            scale += 1
        end
        digits = chosen.to_s
        point = digits.length + scale
        text = if absolute >= 1e-6 && absolute < 1e21
            if point <= 0
                "0." + "0" * -point + digits
            elsif point >= digits.length
                digits + "0" * (point - digits.length)
            else
                digits[0, point] + "." + digits[point..]
            end
        else
            digits[0] + (digits.length > 1 ? "." + digits[1..] : "") + "e#{point - 1}"
        end
        negative ? "-#{text}" : text
    end

    def self.encode(value)
        case value
        when Hash
            raise ArgumentError, "non-string object key" unless value.keys.all? { |key| key.is_a?(String) }
            "{" + value.keys.sort_by(&:codepoints).map { |key| encode(key) + ":" + encode(value.fetch(key)) }.join(",") + "}"
        when Array
            "[" + value.map { |item| encode(item) }.join(",") + "]"
        when String
            utf8 = value.encode(Encoding::UTF_8)
            raise ArgumentError, "invalid UTF8 or surrogate" unless utf8.valid_encoding?
            '"' + utf8.codepoints.map do |scalar|
                raise ArgumentError, "unpaired surrogate" if (0xd800..0xdfff).cover?(scalar)
                if scalar < 32
                    "\\u#{scalar.to_s(16).rjust(4, '0')}"
                elsif scalar == 34
                    '\\"'
                elsif scalar == 92
                    '\\\\'
                else
                    scalar.chr(Encoding::UTF_8)
                end
            end.join + '"'
        when Integer then value.to_s
        when Float then number(value)
        when true then "true"
        when false then "false"
        when nil then "null"
        else raise ArgumentError, "unsupported cache JSON value #{value.class}"
        end
    end

    def self.schema_errors(kind, value)
        JSONSchemer.schema(SCHEMAS.fetch(kind)).validate(value).map do |error|
            { "path" => error.fetch("data_pointer"), "type" => error.fetch("type"), "details" => error["details"] }
        end
    end

    def self.read_source(witness, path)
        raise Incomplete, "missing source path" unless path.is_a?(String) && File.file?(path)
        expected = witness.fetch("source_pins").fetch(path)
        raise Incomplete, "wrong source pin: #{path}" unless expected == Digest::SHA256.file(path).hexdigest
        File.binread(path)
    end

    def self.parse(bytes)
        text = bytes.dup.force_encoding(Encoding::UTF_8)
        raise ArgumentError, "invalid UTF8/BOM" unless text.valid_encoding? && !text.start_with?("\ufeff")
        JSON.parse(text, max_nesting: 128, allow_nan: false)
    end

    def self.source_entries(witness)
        bytes = read_source(witness, witness.fetch("source_jsonl"))
        unless witness.fetch("source_pins").fetch(witness.fetch("name_fold")) == "db858f77691b932888c191a9f17cd9fba84f8acb423786d9ca383d2aa47fc092"
            raise Incomplete, "name_fold does not match approved source-reference pin"
        end
        fold = parse(read_source(witness, witness.fetch("name_fold"))).fetch("map")
        entries = []
        offset = 0
        bytes.each_line("\n") do |line|
            body = line.end_with?("\n") ? line.delete_suffix("\n").delete_suffix("\r") : line
            unless body.match?(/\A[ \t\r\n\f\v]*\z/)
                row = parse(body)
                off = row["subordinate_offsets"]
                sets = (row["constant_sets"] || []).map do |set|
                    summary = %w[set_id source source_type quantity qc_status convention_id licence_id].to_h { |key| [key, set[key]] }
                    summary.merge("constituents" => (set["constituents"] || []).map { |item| item.fetch("name") }, "fallback" => set["fallback"], "current_bins" => (set["current_bins"] || []).map { |item| item.fetch("bin") })
                end
                name = row["name"]
                name_folded = if name
                    name.codepoints.map { |point| fold.fetch(point.to_s(16).upcase.rjust(4, "0"), point.chr(Encoding::UTF_8)) }.join.gsub(/[ \t\n\r\f\v]+/, " ").gsub(/\A +| +\z/, "")
                end
                recommended = sets.find { |set| set["set_id"] == row["recommended_set_id"] } if row["recommended_set_id"]
                kind = recommended && { "water_level" => "tide", "current" => "current" }.fetch(recommended["quantity"], "other")
                scalars = %w[station_id name country type lat lon recommended_set_id].to_h { |key| [key, row[key]] }
                entries << scalars.merge(
                    "status" => row["status"] || "active", "name_folded" => name_folded, "kind" => kind,
                    "reference_station_id" => off && off["reference_station_id"], "offsets_licence_id" => off && off["licence_id"],
                    "offset" => offset, "length" => body.bytesize,
                    "aliases" => (row["aliases"] || {}).transform_values { |ids| ids.is_a?(String) ? [ids] : ids },
                    "sets" => sets, "subordinate_offsets" => off,
                    "current_offsets" => (row["current_offsets"] || []).map { |item| %w[bin reference_bin reference_station_id licence_id].to_h { |key| [key, item[key]] } }
                )
            end
            offset += line.bytesize
        end
        active = entries.select { |entry| entry["status"] == "active" }.to_h { |entry| [entry.fetch("station_id"), entry] }
        own = active.transform_values { |entry| entry["kind"] }
        entries.each do |entry|
            next unless entry["status"] == "active" && entry["kind"].nil?
            current = entry
            seen = [entry["station_id"]]
            16.times do
                break unless current["type"] == "subordinate"
                reference = current["reference_station_id"]
                break if seen.include?(reference) || !active.key?(reference)
                seen << reference
                current = active.fetch(reference)
                if own[current["station_id"]]
                    entry["kind"] = own.fetch(current["station_id"])
                    break
                end
            end
        end
        entries
    end

    def self.check(witness)
        SCENARIOS.fetch("witness_protocol").fetch("required").each { |key| witness.fetch(key) }
        kind = witness.fetch("kind")
        raise Incomplete, "unknown cache kind" unless %w[stream_index verified].include?(kind)
        bytes = File.binread(witness.fetch("cache_path"))
        document = parse(bytes)
        bindings = witness.fetch("bindings")
        identity = bindings.fetch("by")
        raise Incomplete, "missing/invalid producer identity binding" unless identity.is_a?(String) && identity.match?(/\Aopentideconstants-(?:python|ruby|js|typescript|c|swift)\/[^\s]+\z/) && document["by"] == identity
        errors = schema_errors(kind, document)
        canonical = encode(document).b
        if canonical != bytes
            position = (0...[canonical.bytesize, bytes.bytesize].min).find { |index| canonical.getbyte(index) != bytes.getbyte(index) } || [canonical.bytesize, bytes.bytesize].min
            errors << { "type" => "encoding", "path" => "", "first_differing_byte" => position, "expected_sha256" => Digest::SHA256.hexdigest(canonical), "actual_sha256" => Digest::SHA256.hexdigest(bytes) }
        end
        meta = parse(read_source(witness, witness.fetch("source_meta")))
        if kind == "stream_index"
            expected = {
                "index_version" => 1, "discovery_index_version" => 1,
                "datestamp" => meta.fetch("release").fetch("datestamp"),
                "jsonl" => File.basename(witness.fetch("source_jsonl")),
                "jsonl_sha256" => witness.fetch("source_pins").fetch(witness.fetch("source_jsonl")),
                "jsonl_size" => File.size(witness.fetch("source_jsonl")), "by" => identity,
                "stations" => source_entries(witness)
            }
            expected.each do |key, value|
                errors << { "type" => "source_projection", "path" => "/#{key}" } unless document[key] == value
            end
        else
            timestamp = bindings.fetch("verified_at")
            raise Incomplete, "wrong verification time binding" unless timestamp.is_a?(String) && Time.iso8601(timestamp) && document["verified_at"] == timestamp
            files = witness.fetch("verified_files")
            raise Incomplete, "missing verified files" unless files.is_a?(Hash) && !files.empty?
            expected_files = files.to_h do |name, row|
                raise Incomplete, "checksum sidecar is not a verified data file" if name.end_with?(".sha256")
                path = row.fetch("path")
                source = read_source(witness, path)
                raise Incomplete, "verified filename differs from source" unless name == File.basename(path)
                url = row.fetch("url")
                raise Incomplete, "invalid URL witness" unless url.nil? || (url.is_a?(String) && url.match?(/\Ahttps?:\/\//))
                [name, { "sha256" => Digest::SHA256.hexdigest(source), "size" => source.bytesize, "url" => url }]
            end
            expected = {
                "datestamp" => meta.fetch("release").fetch("datestamp"), "files" => expected_files,
                "format_version" => meta.fetch("format_version"), "min_reader_version" => meta.fetch("release").fetch("min_reader_version"),
                "zenodo_version_doi" => witness.fetch("zenodo_version_doi"), "verified_at" => timestamp, "by" => identity
            }
            expected.each do |key, value|
                errors << { "type" => "source_projection", "path" => "/#{key}" } unless document[key] == value
            end
        end
        errors
    rescue KeyError, Errno::ENOENT => error
        raise Incomplete, "missing witness input: #{error.message}"
    end

    def self.calibrate
        golden = JSON.parse(File.read(File.join(DIRECTORY, "cache-golden.json")))
        golden.fetch("cases").each do |fixture|
            value = fixture.key?("binary64_hex") ? [fixture.fetch("binary64_hex")].pack("H*").unpack1("G") : fixture.fetch("input")
            raise ArgumentError, "golden mismatch: #{fixture.fetch('id')}" unless encode(value) == fixture.fetch("expected")
        end
        golden.fetch("refusals").each do |fixture|
            refused = false
            begin
                value = fixture.key?("raw_json_hex") ? parse([fixture.fetch("raw_json_hex")].pack("H*")) : [fixture.fetch("binary64_hex")].pack("H*").unpack1("G")
                encode(value)
            rescue ArgumentError, JSON::ParserError, EncodingError
                refused = true
            end
            raise ArgumentError, "refusal accepted: #{fixture.fetch('id')}" unless refused
        end
        golden.fetch("negative_bytes").each do |fixture|
            expected = golden.fetch("cases").find { |item| item.fetch("id") == fixture.fetch("case") }.fetch("expected")
            raw = [fixture.fetch("raw_hex")].pack("H*")
            rejected = false
            begin
                rejected = encode(parse(raw)).b != raw
            rescue ArgumentError, JSON::ParserError, EncodingError
                rejected = true
            end
            raise ArgumentError, "negative bytes accepted: #{fixture.fetch('id')}" unless rejected && raw != expected.b
        end
        { "classification" => "VALIDATOR CALIBRATION ONLY, not native SDK GREEN", "positive_controls" => golden.fetch("cases").length, "refusal_controls" => golden.fetch("refusals").length, "negative_byte_controls" => golden.fetch("negative_bytes").length }
    end
end

if $PROGRAM_NAME == __FILE__
    begin
        if ARGV == ["--calibrate"]
            puts JSON.generate(CanonicalCache.calibrate)
        elsif ARGV.length == 2 && ARGV[0] == "--witness"
            witness = CanonicalCache.parse(File.binread(ARGV[1]))
            errors = CanonicalCache.check(witness)
            puts JSON.pretty_generate({ "classification" => "actual supplied file validation; writer provenance belongs to retained native execution witness", "status" => errors.empty? ? "GREEN" : "RED", "errors" => errors })
            exit(errors.empty? ? 0 : 1)
        else
            raise CanonicalCache::Incomplete, "usage: ruby check_cache.rb --calibrate | --witness <witness.json>"
        end
    rescue CanonicalCache::Incomplete => error
        warn "INCOMPLETE: #{error.message}"
        exit 2
    rescue ArgumentError, JSON::ParserError, EncodingError => error
        warn "RED: #{error.message}"
        exit 1
    end
end
