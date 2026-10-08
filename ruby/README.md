# opentideconstants (Ruby)

The Ruby SDK for [OpenTideConstants](https://opentideconstants.org), an open dataset of tidal harmonic constants. It downloads a release, checks its SHA-256, caches it, and gives you the stations and their constants. Pure Ruby, standard library only, Ruby 3.0 or later.

```ruby
require "opentideconstants"

otc = OpenTideConstants.new                       # the latest release, cached
st  = otc.station_by_alias(:noaa, "9414290")
m2  = st.recommended_set.constituent("M2")
puts "#{st.name}: M2 #{m2.amplitude_m} m, #{m2.phase_deg}°"
puts otc.attribution([st])                        # CC BY 4.0 attribution text
```

Pin a release in production, and bump the pin in a reviewed change:

```ruby
otc = OpenTideConstants.new(release: "20261008")
```

Other ways to open:

| Option | Use |
|---|---|
| `file: "OTC_20261008.jsonl"` | a local `.json`, `.json.gz` or `.jsonl` (+ `.meta.json`); checked against `OTC_{D}.sha256` if it is next to it |
| `offline: true` | never open a socket; `latest` is the newest cached release |
| `mode: :stream` | low memory: stations are read from the `.jsonl` file when a query needs them |
| `cache_dir:`, `base_url:`, `timeout:`, `proxy:`, `ca_file:`, `user_agent:`, `on_network_error:`, `auto_update:`, `update_interval:`, `logger:`, `verify_on_open:` | see the SDK spec §4.2 |

Queries: `station`, `require_station`, `tombstone`, `station_by_alias`, `stations(**filters)`, `each_station`, `search(name:)`, `near(lat:, lon:, radius_km:)`, `nearest(lat:, lon:)`, `reference_station`, `subordinates_of`, `attribution`. Release management: `release`, `loaded_from`, `releases`, `latest`, `check_for_update`, `update!`, `download(to:)`, `verify`, `cached_releases`, `prune(keep:)`.

Every error is a subclass of `OpenTideConstants::Error` and has a stable `code`.

Bundle a release with your app:

```ruby
OpenTideConstants.new.download("20261008", to: "vendor/tides")   # .jsonl, .meta.json, .sha256
OpenTideConstants.new(file: "vendor/tides/OTC_20261008.jsonl")   # loaded_from :file
```

The gem passes the language-neutral conformance suite in `conformance/` (runner: `conformance/runners/ruby/runner.rb`).

Code: MIT. Data: CC BY 4.0, with a licence per constant set (`set.licence`).
