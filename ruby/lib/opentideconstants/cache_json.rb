class OpenTideConstants
    # Encoding for generated cache documents only; downloaded bytes stay original.
    module CacheJSON
        def self.encode(value)
            case value
            when Hash
                raise ArgumentError, "non-string cache JSON key" unless value.keys.all? { |key| key.is_a?(String) }
                keys = value.keys.map { |key| [key, utf8(key)] }.sort_by { |_, key| key.codepoints }
                "{" + keys.map { |original, key| encode(key) + ":" + encode(value.fetch(original)) }.join(",") + "}"
            when Array
                "[" + value.map { |item| encode(item) }.join(",") + "]"
            when String
                '"' + utf8(value).codepoints.map do |scalar|
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

        def self.utf8(value)
            text = value.encode(Encoding::UTF_8)
            raise ArgumentError, "invalid UTF8 or surrogate in cache JSON" unless text.valid_encoding?
            text
        end

        def self.number(value)
            raise ArgumentError, "nonfinite cache JSON number" unless value.finite?
            return "0" if value.zero?
            # Ruby's Float#to_s supplies the closest shortest roundtrip decimal.
            # Change only notation and redundant zeroes, without rounding again.
            mantissa, exponent = value.abs.to_s.split("e", 2)
            whole, fraction = mantissa.split(".", 2)
            digits = (whole + (fraction || "")).sub(/\A0+/, "")
            scale = (exponent || "0").to_i - (fraction || "").length
            while digits.end_with?("0")
                digits = digits.chop
                scale += 1
            end
            point = digits.length + scale
            text = if value.abs >= 1e-6 && value.abs < 1e21
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
            value.negative? ? "-#{text}" : text
        end
    end
end
