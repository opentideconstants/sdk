# opentideconstants (Ruby)

The Ruby SDK for [OpenTideConstants](https://opentideconstants.org), an open dataset of tidal harmonic constants. It downloads a release, checks its SHA-256, caches it, and gives you the stations and their constants. Pure Ruby, standard library only, Ruby 3.3 or later.

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
otc.close
```

Other ways to open:

| Option | Use |
|---|---|
| `file: "OTC_20261008.jsonl"` | a local `.json`, `.json.gz` or `.jsonl` (+ `.meta.json`). With `OTC_{D}.sha256` next to it, the files are checked against it and `loaded_from` is `:file`; without it nothing is checked and `loaded_from` is `:file_unverified` (then `verify` fails with `checksum_mismatch`) |
| `offline: true` | never open a socket. Opening the latest release (the default) loads the newest cached release; `latest`, `check_for_update` and `update!` fail with `offline_unavailable` |
| `mode: :stream` | low memory: stations are read from the `.jsonl` file when a query needs them |

The other options:

| Option | Default | Use |
|---|---|---|
| `cache_dir:` | `OPENTIDECONSTANTS_CACHE_DIR`, else the user cache folder (`~/Library/Caches/opentideconstants`, `$XDG_CACHE_HOME/opentideconstants` or `~/.cache/opentideconstants`, `%LOCALAPPDATA%\opentideconstants\Cache`) | where downloaded releases are kept |
| `base_url:` | `OPENTIDECONSTANTS_BASE_URL`, else `https://data.opentideconstants.org/` | where releases are downloaded from (`http` or `https`) |
| `timeout:` | `nil`: 10 s to connect, 60 s to read | seconds for both, from 0.001 to 1000000 |
| `proxy:` | `nil`: the `http_proxy`/`https_proxy` and `no_proxy` variables | an `http://` proxy URL (Net::HTTP cannot use TLS to a proxy); a user and password in it are sent to the proxy |
| `ca_file:` | `nil`: `SSL_CERT_FILE`, else the system roots | a PEM file of the certificates to trust |
| `user_agent:` | `nil` | text added after the gem's own User-Agent |
| `on_network_error:` | `:use_cache` | when the network fails while the latest release is opened: `:use_cache` loads the newest cached release (`loaded_from` is `:cache_after_error`, `last_error` has the error); `:raise` raises it. `download` of the latest release and `releases` follow it too |
| `auto_update:` | `false` | `true` (a client on the latest release only): a query checks for a newer release when `update_interval` has passed, and switches to it; a failure goes to `last_error`, the query still answers |
| `update_interval:` | `86400` | seconds between the automatic checks |
| `logger:` | `nil` | any object with `debug`, `info`, `warn` and `error` (a `Logger`) |
| `verify_on_open:` | `false` | `true`: a cached release is hashed again, from the bytes that are read, and compared with its `.sha256` when it is loaded |
| `commercial_only:` | `false` | `true`: only the constant sets whose licence allows commercial use |

Environment variables: `OPENTIDECONSTANTS_CACHE_DIR` and `OPENTIDECONSTANTS_BASE_URL` are the defaults of `cache_dir` and `base_url` (an option wins over them). `OPENTIDECONSTANTS_OFFLINE` set to `1`, `true`, `yes` or `on` makes every client offline, also one opened with `offline: false`; if a client fails with `offline_unavailable` when you did not ask for offline, check this variable.

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

Native prediction uses `otc-predict-1`. Pass Ruby `Time` values. The SDK floors each instant to a whole UTC second.

```ruby
require "opentideconstants"
OpenTideConstants.open do |otc|
    start = Time.utc(otc.release.datestamp[0, 4].to_i, 10, 11)
    station = otc.station_by_alias(:noaa, "9414290")
    heights = otc.heights(station, start: start, stop: start + 86400, step_s: 600)
    events = otc.extremes(station, start: start, stop: start + 86400)
    datums = otc.datums(station)
end
```

`heights_at` preserves input order and repeated instants. `currents` returns velocities, speed and direction for the selected `bin_number`. `current_events` returns signed peaks and slack events. Results and their items are immutable.

If high and low offsets differ, the station provides extrema only. Curve calls raise `ExtremesOnlyError`. Subordinate current stations also provide events only.

The default `historical_offsets_policy: :fallback` permits eligible NOAA2020 historical profiles when no better contemporary path exists. These results retain the retired source label, unestablished current validity and unverified current accuracy. Select an exact profile with `offset_id:`. Use `historical_offsets_policy: :exclude` to disable historical prediction and discovery. Query flags cannot override that policy.

Discovery excludes flagged and fallback sets by default. Use `include_flagged: true` or `include_fallback: true` for their respective sets. Lookup retains all station metadata. `station.source_records` preserves original source values and provenance in frozen `raw` objects. Original-source licences remain separate from published-set licences. `commercial_basis: :strict` is the default; `:as_published_upstream` selects the approved upstream interpretation.

Install `tzinfo` to use `result.to_local("America/New_York")`. Core prediction does not require it. Local conversion preserves the UTC instant and exposes `local_time`, `utc_offset_s` and `local_time_object`. Without the optional module, conversion raises `LocalTimeUnavailableError`.

Fixture unit tests run through `ruby -Iruby/lib ruby/test/test_unit.rb`. The authenticated actual-source gates run separately through `test_core_native.rb` and `test_noaa_historical.rb`; their artifact environment is mandatory. The full H4 source is not bundled in the gem.
