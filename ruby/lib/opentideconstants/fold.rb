require "json"

class OpenTideConstants
    # Name normalisation for search (spec §4.4.1). It uses the shared fold table
    # (a copy of conformance/name_fold.json embedded in the gem), not Ruby's own
    # Unicode functions.
    module Fold
        TABLE_PATH = File.expand_path("name_fold.json", __dir__)
        MAP = JSON.parse(File.read(TABLE_PATH, encoding: "UTF-8"))["map"]
                  .to_h { |k, v| [k.to_i(16), v.freeze] }.freeze

        module_function

        def fold(name)
            out = +""
            name.each_char { |ch| out << (MAP[ch.ord] || ch) }
            out.gsub(/[ \t\n\r\f\v]+/, " ").strip
        end
    end
end
