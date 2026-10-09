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

        # Step 1, the table; step 2, each run of white space (U+0020 and the
        # ASCII tab, line feed, vertical tab, form feed and carriage return
        # that the table leaves) becomes one space, then only U+0020 is
        # trimmed: a NUL, for one, stays (CR D12).
        def fold(name)
            out = +""
            name.each_char { |ch| out << (MAP[ch.ord] || ch) }
            out.gsub(/[ \t\n\v\f\r]+/, " ").gsub(/\A +| +\z/, "")
        end
    end
end
