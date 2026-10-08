# Conformance fixture releases

Synthetic OpenTideConstants releases for the SDK conformance suite (SDK spec §7.1).

**Licence: CC0-1.0.** All station names, ids, providers and numbers are made up for tests. They are not tidal data. Do not use them to predict tides.

Do not edit these files by hand. Change `conformance/tools/build_fixtures.py`, then run:

```
uv run conformance/tools/build_fixtures.py           # writes good/, order/, bad/ and fixtures.json
uv run conformance/tools/build_fixtures.py --check   # regenerates, compares byte for byte, validates, checks every bad fixture
```

`--check` downloads format 0.2 of the schema from the site repository at a pinned commit and checks its SHA-256. `--schema PATH` uses a local copy instead.

## Layout

Each directory is a server root: the fixture HTTP server serves one of them as `base_url`.

| Directory | What it holds | Expected outcome |
|---|---|---|
| `good/` | releases `20991231` and `20991231.2` (two releases on the same day), with `OTC_latest.json`, `OTC_latest-f0.json` and `OTC_index.json` pointing to `20991231.2` | both load |
| `order/` | releases `20991231.2` and `20991231.10`, with the pointers on `20991231.10`: numeric counter order (.10 after .2) differs from string order (§4.3.1). Same content as `good/`'s `20991231.2` apart from the datestamp | both load |
| `bad/wrong-sha256/` | every station data file differs from its SHA-256 (same size, one byte changed) | `checksum_mismatch` |
| `bad/truncated/` | the `.json`, `.json.gz` and `.jsonl` files are cut to half their size | `checksum_mismatch` |
| `bad/pointer-mismatch/` | the files match `.sha256`, but the pointer and the index give other SHA-256 values | `checksum_mismatch` |
| `bad/format-major/` | `format_version` `1.0` (pointer `OTC_latest-f1.json`, no `-f0`) | `unsupported_format` |
| `bad/format-minor/` | `format_version` `0.3` with unknown fields at every level and an unknown alias system | loads; the unknown fields are in `raw` |
| `bad/unresolved-convention/` | a set whose `convention_id` does not exist | `invalid_release` |

`fixtures.json` lists the same roots, releases and expected outcomes in machine-readable form.

Each release has `OTC_{D}.json`, `.json.gz`, `.jsonl`, `.meta.json` and `.sha256` (`sha256sum` format, sorted by name; it does not list itself).

## Pointer and index files

`OTC_latest.json` and `OTC_latest-f{MAJOR}.json` hold one entry; `OTC_index.json` holds `{"releases": [entry, ...]}`, newest first. An entry is:

```json
{"datestamp": "20991231.2", "format_version": "0.2", "created": "…", "doi": "10.5072/zenodo.2", "concept_doi": "10.5072/zenodo.1",
 "files": [{"name": "OTC_20991231.2.json", "url": "OTC_20991231.2.json", "size": 123, "sha256": "…"}, …]}
```

`files` lists every release file, the `.sha256` file included. In the fixtures each `url` is relative, so the same files work under any `base_url`. An SDK resolves `url` against the URL of the pointer it read, by the normal rules for relative URLs, so absolute URLs in a real pointer work the same way.

## What the stations cover

| Station | Covers |
|---|---|
| `OTC-T-0001` San Francisco | reference station with two sets (official `noaa`, recommended; gauge `gesla-fit`); aliases in all seven systems; validation with `previous_release` as an object, as `null` and missing; dropped constituents; provenance with extra fields; every optional field |
| `OTC-T-0002` South San Francisco | an `excluded` set and the recommended `fallback` set |
| `OTC-T-0003` Alameda | subordinate, `R` (ratio) offsets only, `recommended_set_id` null, offsets `licence_id` |
| `OTC-T-0004` Oakland Pier | subordinate, `A` (additive) offsets, with its own set |
| `OTC-T-0005` Old Pier | tombstone |
| `OTC-T-0006` Tromsø | local-phase convention (UTC+1); a name with ø |
| `OTC-T-0007`, `OTC-T-0008` | latitude 0.0, longitude 179.9 and −179.9 (either side of the antimeridian) |
| `OTC-T-0009` Polar Station | latitude 89.9 |
| `OTC-T-0010` Equator Station | latitude 0.0, longitude 9.0 |
| `OTC-T-0011` Ålesund, `OTC-T-0012` Łeba, `OTC-T-0013` Straße | accented names and letters that do not decompose |
| `OTC-T-0014`, `OTC-T-0015` Harbour | two stations with the same name |
| `OTC-T-0016` Harbour Point, `OTC-T-0017` North Harbour, `OTC-T-0018` Seaharbour | prefix, word-start and substring matches for search ranking |
| `OTC-T-0019` Test Current Pass | a current station (`quantity: current`) |
| `OTC-T-0020` Minimal Station | missing optional fields (no aliases, validation, record span, datum, QC flags; empty provenance) |
| `OTC-T-0021` Closing Pier | active in `20991231`, a tombstone in `20991231.2` |
| `OTC-T-0022` New Pier | only in `20991231.2` |

Release `20991231` has a null DOI, a build commit and a changelog URL. Release `20991231.2` has a DOI (test prefix `10.5072`) and leaves out the optional build commit and changelog URL.
