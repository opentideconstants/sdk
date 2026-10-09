# Conformance fixture releases

Synthetic OpenTideConstants releases for the SDK conformance suite (SDK spec §7.1). Every release is format 1.0, except the releases that test other versions (`bad/format-minor`, `bad/format-major`, `bad/min-reader`, `reader/`'s `20991231.4` and `major/`'s `20991231.3`).

**Licence: CC0-1.0.** All station names, ids, providers and numbers are made up for tests. They are not tidal data. Do not use them to predict tides.

Do not edit these files by hand. Change `conformance/tools/build_fixtures.py`, then run:

```
uv run conformance/tools/build_fixtures.py           # writes every root and fixtures.json
uv run conformance/tools/build_fixtures.py --check   # regenerates, compares byte for byte, validates, checks every bad fixture
```

`--check` downloads `otc-1.0.schema.json` and `otc-index-1.0.schema.json` from the site repository at a pinned commit and checks their SHA-256. Each format 1.0 release is validated against the schema (the `.json`, the `.meta.json` against `#/$defs/meta`, each `.jsonl` line against `#/$defs/station`). A higher-minor release is read tolerantly against 1.0. A release that no 1.0 reader reads (`min_reader_version` 1.99, or format 2.0) must be a valid 1.0 release apart from its two version fields. Every `OTC_index.json` and every pointer is validated against the index schema. `--schema-dir DIR` uses local copies of the two schemas.

## Layout

Each directory is a server root: the fixture HTTP server serves one of them as `base_url`.

| Directory | What it holds | Expected outcome |
|---|---|---|
| `good/` | releases `20991231` and `20991231.2` (two releases on the same day), with `OTC_latest.json`, `OTC_latest-f1.json` and `OTC_index.json` pointing to `20991231.2` | both load |
| `order/` | releases `20991231.2` and `20991231.10`, with the pointers on `20991231.10`: numeric counter order (.10 after .2) differs from string order (§4.3.1). Same content as `good/`'s `20991231.2` apart from the datestamp | both load |
| `v1/` | release `20991231.3` with the annotation stations below; version DOI `10.5072/zenodo.3` and `zenodo_material` in its index entry | loads |
| `reader/` | releases `20991231.2` and `20991231.3` (format 1.0) and `20991231.4` (format and `min_reader_version` `1.99`); the pointers name `20991231.4` | `.4`: `reader_too_old`; `latest` for a 1.0 reader is `.3` (one GET of `OTC_index.json`) |
| `major/` | releases `20991231` and `20991231.2` (format 1.0) and `20991231.3` (format 2.0); `OTC_latest.json` and `OTC_latest-f2.json` name `.3`, `OTC_latest-f1.json` names `.2` | `.3`: `unsupported_format`; `latest` is `.2`; `check_for_update` reports `newer_format_major` 2 |
| `bad/wrong-sha256/` | every station data file differs from its SHA-256 (same size, one byte changed) | `checksum_mismatch` |
| `bad/truncated/` | the `.json`, `.json.gz` and `.jsonl` files are cut to half their size | `checksum_mismatch` |
| `bad/pointer-mismatch/` | the files match `.sha256`, but the pointer and the index give other SHA-256 values | `checksum_mismatch` |
| `bad/format-major/` | `format_version` `2.0` (pointer `OTC_latest-f2.json`, no `-f1`) | `unsupported_format` |
| `bad/format-minor/` | `format_version` `1.1` (`min_reader_version` `1.0`) with unknown fields at every level, an unknown alias system, and a set on `OTC-T-0010` with `qc_status` `excluded` | loads; the unknown fields are in `raw`; the status is `other` |
| `bad/unresolved-convention/` | a set whose `convention_id` does not exist | `invalid_release` |
| `bad/min-reader/` | the only release has `min_reader_version` `1.99` | `reader_too_old` |
| `bad/no-build/` | `OTC-T-0004`'s set has no `provenance.build` (malformed 1.0; valid once it is put back) | loads; `build` is null |
| `bad/min-reader-malformed/`, `bad/format-version-malformed/` | `min_reader_version` `"2"`, `format_version` `"1.x"` (not MAJOR.MINOR; the index entry is valid) | `invalid_release` (D9) |
| `bad/active-and-removed-same-id/`, `bad/duplicate-set-id/`, `bad/duplicate-convention-id/` | an id that is both active and a tombstone; two sets with one `set_id`; two conventions with one id | `invalid_release` (D5) |
| `bad/unresolved-reference-station/`, `bad/unresolved-offsets-licence/` | `subordinate_offsets` naming a station or a licence that does not exist | `invalid_release` |
| `bad/station-id-not-string/`, `bad/lat-string/`, `bad/aliases-not-object/`, `bad/qc-flags-not-array/`, `bad/convention-without-id/`, `bad/created-not-string/`, `bad/source-versions-not-object/` | one value of the wrong type (schema-invalid) | `invalid_release` |
| `bad/gz-differs/` | honest digests, but the `.json.gz` decompresses to other data than the `.json` | `checksum_mismatch` (reference reader only) |
| `bad/jsonl-differs/` | honest digests, but a `.jsonl` line differs from the `.json` station | `invalid_release` (reference reader only) |
| `bad/meta-differs/` | honest digests, but the `.meta.json` differs from the `.json` without stations | `invalid_release` (reference reader only) |
| `bad/size-mismatch/` | the pointer and the index give the `.jsonl` one byte more than its size; every SHA-256 is right | `checksum_mismatch` |
| `bad/sums-extra-file/` | `OTC_20991231.sha256` lists a file that the pointer does not list | `checksum_mismatch` |
| `bad/sha256-file-differs/` | the pointer's SHA-256 of `OTC_20991231.sha256` is not the file's | `checksum_mismatch` |
| `bad/sums-disagree/` | `OTC_20991231.sha256` gives another SHA-256 for the `.jsonl` than the pointer, which the file matches | `checksum_mismatch` |
| `bad/unresolved-licence/` | a set whose `licence_id` does not exist | `invalid_release` |
| `bad/unresolved-recommended/` | a `recommended_set_id` that names no set of the station | `invalid_release` |
| `bad/duplicate-alias/` | two stations with the same `noaa` alias id | `invalid_release` |
| `bad/duplicate-station-id/` | `OTC-T-0020` twice | `invalid_release` |
| `bad/lat-nan/` | a `lat` of `NaN` (not JSON) | `invalid_release` |
| `bad/jsonl-wrong-sha256/` | only the `.jsonl` has one byte changed (same size) | `checksum_mismatch` |
| `bad/index-invalid/` | a good release whose `OTC_index.json` entry has a `content_sha256` that is not a digest | loads; the index fails `otc-index-1.0` |
| `bad/recommended-set-id-number/`, `bad/station-name-number/`, `bad/station-timezone-number/`, `bad/offsets-number-string/`, `bad/validation-number-string/`, `bad/validation-count-fraction/`, `bad/constituent-amplitude-string/`, `bad/datum-msl-string/`, `bad/good-samples-string/`, `bad/set-source-version-number/`, `bad/time-base-correction-string/`, `bad/qc-flag-values-not-object/`, `bad/qc-flag-value-string/`, `bad/evidence-not-objects/`, `bad/evidence-number-string/`, `bad/source-version-number/`, `bad/source-version-null/`, `bad/constant-sets-object/`, `bad/constant-sets-not-objects/`, `bad/constant-sets-null-item/` | one known field of the wrong JSON type (review round 2, PK-R2-05) | `invalid_release` |
| `bad/lat-overflow-literal/`, `bad/lon-overflow-literal/`, `bad/lat-huge-int/`, `bad/constituent-amplitude-inf/`, `bad/constituent-amplitude-huge-int/` | a number that is not finite as a double (`1e400`, an integer of 401 digits) | `invalid_release` |
| `bad/invalid-utf8/`, `bad/lone-surrogate/` | a station name with the byte 0xFF, or with the escape `\ud800` alone (CR D17) | `invalid_release` |
| `bad/constituent-name-twice/`, `bad/duplicate-licence-id/`, `bad/tombstone-twice/` | a constituent name twice in one set (CR2 DR22), a repeated `licence_id`, a repeated tombstone (CR D5) | `invalid_release` |
| `bad/proto-keys/` | format `1.1`: an alias system `__proto__` and `constructor`, and a set source `constructor` | loads; the names work like any other |
| `bad/too-new-broken/` | `min_reader_version` `1.99`, and its data is not valid 1.0 | `reader_too_old` (the version gate comes first) |

The reference reader checks that the files of one release agree (`.json.gz` with `.json`, `.jsonl` and `.meta.json` with `.json`). The SDKs do not (decision D37): each file is checked against `OTC_{D}.sha256`, so a release whose files disagree is a pipeline defect, and only the reference reader has cases for it. Each rule of the reference reader decides the outcome of at least one bad fixture, so turning a rule off fails `--check` (review round 1, B2-T1). Three rules repeat another check and cannot be turned off alone: the SHA-256 of `OTC_{D}.sha256` against the pointer (step 4.2 hashes it again), and the schema checks of the `.meta.json` and the `.jsonl` lines (they must equal the `.json`, which is validated in full). The pointer and too-new-file checks are covered by builder mutants (a wrong per-major pointer, a `.jsonl` that differs in a too-new release).

`fixtures.json` lists the same roots, releases and expected outcomes in machine-readable form.

Each release has `OTC_{D}.json`, `.json.gz`, `.jsonl`, `.meta.json` and `.sha256` (`sha256sum` format, sorted by name; it does not list itself).

## Pointer and index files

`OTC_latest.json` and `OTC_latest-f{MAJOR}.json` hold one entry; `OTC_index.json` holds `{"releases": [entry, ...]}`, newest first. An entry follows `otc-index-1.0.schema.json`:

```json
{"datestamp": "20991231.2", "format_version": "1.0", "min_reader_version": "1.0", "created": "…",
 "concept_doi": "10.5072/zenodo.1", "zenodo_version_doi": "10.5072/zenodo.2", "content_sha256": "…",
 "files": [{"name": "OTC_20991231.2.json", "url": "OTC_20991231.2.json", "size": 123, "sha256": "…"}, …]}
```

`files` lists every release file, the `.sha256` file included. In the fixtures each `url` is relative, so the same files work under any `base_url`. An SDK resolves `url` against the URL of the pointer it read, by the normal rules for relative URLs, so absolute URLs in a real pointer work the same way. `content_sha256` is a stand-in digest: the SDKs only pass it through.

## What the stations cover (`good/`, `order/`)

| Station | Covers |
|---|---|
| `OTC-T-0001` San Francisco | reference station with two sets (official `noaa`, recommended, with every `provenance.build` field; gauge `gesla-fit`, `flagged` with an `unverified` time base); aliases in all seven systems; validation with `previous_release` as an object, as `null` and missing; dropped constituents (`rayleigh` with `not_separable_from`); provenance with a field the typed object does not have (`tcd_sha256`); every optional field |
| `OTC-T-0002` South San Francisco | the recommended carried-over set (`flagged`, `carried_over`, `carried_from_release` `20991230`) and a `no_constants` set (`fit_unusable`, `record_issues`) |
| `OTC-T-0003` Alameda | subordinate, `R` (ratio) offsets only, `recommended_set_id` null, offsets `licence_id` `kartverket` (not the licence of its reference station's recommended set, `noaa`, so its attribution needs both) |
| `OTC-T-0004` Oakland Pier | subordinate, `A` (additive) offsets, with its own set |
| `OTC-T-0005` Old Pier | tombstone (`duplicate` of `OTC-T-0001`) |
| `OTC-T-0006` Tromsø | local-phase convention (UTC+1); a name with ø |
| `OTC-T-0007`, `OTC-T-0008` | latitude 0.0, longitude 179.9 and −179.9 (either side of the antimeridian) |
| `OTC-T-0009` Polar Station | latitude 89.9 |
| `OTC-T-0010` Equator Station | latitude 0.0, longitude 9.0 |
| `OTC-T-0011` Ålesund, `OTC-T-0012` Łeba, `OTC-T-0013` Straße | accented names and letters that do not decompose; time bases `corrected` (with `correction` and `months_dropped`), `disputed` (`flagged`) and `verified` |
| `OTC-T-0014`, `OTC-T-0015` Harbour | two stations with the same name |
| `OTC-T-0016` Harbour Point, `OTC-T-0017` North Harbour, `OTC-T-0018` Seaharbour | prefix, word-start and substring matches for search ranking |
| `OTC-T-0019` Test Current Pass | a current station: a `current` set with `current_bins` and no water-level constituents |
| `OTC-T-0020` Minimal Station | missing optional fields (no aliases, validation, record span, datum, QC flags, time base; provenance with only `build`) |
| `OTC-T-0021` Closing Pier | active in `20991231`, a tombstone (`merged` into `OTC-T-0022`) in `20991231.2` |
| `OTC-T-0022` New Pier | only in `20991231.2` |

The licences are not in `licence_id` order. Every gauge set has a `time_base` and `record_span.good_hours`; the model and official sets have no `time_base`. Release `20991231` has a null `concept_doi`, a build commit and a changelog URL. Release `20991231.2` has the concept DOI `10.5072/zenodo.1` (test prefix `10.5072`), the version DOI `10.5072/zenodo.2` in its index entry, and leaves out the optional build commit and changelog URL.

## The annotation stations (`v1/`, release `20991231.3`)

| Station | Covers |
|---|---|
| `OTC-T-0101` Six Ok Harbour | two `ok` sets: an official set with every `provenance.build` field, a gauge set with a `verified` time base and only `build.build_commit` |
| `OTC-T-0102` Six Flagged Point | an `ok` set with a `corrected` time base and a `flagged` set with an `unverified` time base |
| `OTC-T-0103` Six Mixed Quay | an `ok` official set and a `no_constants` gauge set (`too_short`): `gesla-fit` is not a usable source here |
| `OTC-T-0104` Six Empty Reef | only a `no_constants` set (`fit_unusable`): no recommended set |
| `OTC-T-0105` Six Carried Pier | a `flagged` set carried over from `20991231.2` |
| `OTC-T-0106` Six Jma Port | a JMA set (`owner` `jma`, `redistribution` `redistribute` and the other JMA provenance keys, read through `raw`), with its own licence |
| `OTC-T-0108` | a tombstone, `removed_reason` `merged`, `merged_into` `OTC-T-0101` |

The `reader/` and `major/` releases hold only `OTC-T-0101`.

Roots for the cross-SDK value rules of review round 1 (each loads):

| Root | What it has |
|---|---|
| `values/` | `release.created` with an offset and a fraction (`2099-12-31T02:00:00.5+02:00`), a non-number in `validation.previous_release`, a station name with a NUL inside and one that ends in NUL |
| `values-kept-reason/` | a constituent `kept_reason` of 48 bytes (the schema sets no maxLength) |
| `values-source-name/` | a constituent `source_name` of 31 characters that are 62 UTF-8 bytes |
| `fold/` | station names for the fold rules of D12 (final sigma, h t n k with stroke, eng and kra, the middle dot, NBSP) |
| `nogz/` | a release that publishes `.json`, `.jsonl` and `.meta.json` and no `.json.gz` |
