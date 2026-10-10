# opentideconstants (Ruby)

The Ruby SDK for [OpenTideConstants](https://opentideconstants.org), an open dataset of tidal harmonic constants. It downloads a release, checks its SHA-256, caches it, and gives you the stations and their constants. Pure Ruby, standard library only, Ruby 3.0 or later.

```ruby
require "opentideconstants"

otc = OpenTideConstants.new                       # the latest release, cached
st  = otc.station_by_alias(:noaa, "9414290")      # nil when no station has this id
m2  = st&.recommended_set&.constituent("M2")      # a station can have no recommended set
puts "#{st.name}: M2 #{m2.amplitude_m} m, #{m2.phase_deg}°" if m2
puts otc.attribution([st]) if st                  # CC BY 4.0 attribution text
otc.close
```

Pin a release in production, and bump the pin in a reviewed change:

```ruby
otc = OpenTideConstants.new(release: "20261008")
```

Other ways to open:

| Option | Use |
|---|---|
| `file: "OTC_20261008.jsonl"` | a local `.json`, `.json.gz` or `.jsonl` (+ `.meta.json`). With `OTC_{D}.sha256` next to it, the files are checked against it and `loaded_from` is `:file`; without it nothing is checked and `loaded_from` is `:file_unverified` (then `verify` fails with `checksum_mismatch`) |
| `offline: true` | never open a socket. Opening the latest release (the default) loads the newest cached release; `latest`, `check_for_update` and `update!` fail with `offline_unavailable` |
| `mode: :stream` | low memory: stations are read from the `.jsonl` file when a query needs them |
| `cache_dir:`, `base_url:`, `timeout:`, `proxy:`, `ca_file:`, `user_agent:`, `on_network_error:`, `auto_update:`, `update_interval:`, `logger:`, `verify_on_open:`, `commercial_only:` | see the SDK spec §4.2 |

Queries: `station`, `require_station`, `tombstone`, `station_by_alias`, `stations(**filters)`, `each_station`, `search(name:)`, `near(lat:, lon:, radius_km:)`, `nearest(lat:, lon:)`, `reference_station`, `subordinates_of`, `attribution`. Release management: `release`, `loaded_from`, `releases`, `latest`, `check_for_update`, `update!`, `download(to:)`, `verify`, `cached_releases`, `prune(keep:)`.

Every error that the SDK raises is a subclass of `OpenTideConstants::Error` and has a stable `code`. A lookup that finds nothing (`station`, `station_by_alias`, `tombstone`, `constituent`) returns `nil`; `require_station` raises instead. Ruby's own errors, such as an `ArgumentError` for an unknown keyword, are not SDK errors.

The gem reads format 1.0 (`OpenTideConstants::SUPPORTED_FORMAT_VERSION`). A pinned release or a file whose `min_reader_version` is newer fails with `reader_too_old`. The latest release skips such a release: opening it, `latest`, `check_for_update` and `update!` all use the newest release that the gem reads. `station.constant_sets` leaves out `no_constants` sets unless you pass `include_no_constants: true`. `release.citation` and `otc.attribution` give the exact text to cite.

Bundle a release with your app:

```ruby
OpenTideConstants.open(release: "20261008", mode: :stream) do |otc|
    otc.download("20261008", to: "vendor/tides")                 # .jsonl, .meta.json, .sha256
end
otc = OpenTideConstants.new(file: "vendor/tides/OTC_20261008.jsonl")   # loaded_from :file (the .sha256 is next to it)
otc.close
```

`download` writes all of the files or none of them, and returns the paths it wrote: the data files and their `.meta.json` and `.sha256`, without the files that were already there with the same content.

The gem passes the language-neutral conformance suite in `conformance/` (runner: `conformance/runners/ruby/runner.rb`).

Code: MIT. Data: CC BY 4.0, with a licence per constant set (`set.licence`).
