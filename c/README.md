# OpenTideConstants C SDK

The C SDK reads JSONL releases and their META files. It calculates predictions directly from the release's constants and astronomical tables.

Build the library and runner:

```sh
cmake -S c -B c/build -DCMAKE_BUILD_TYPE=Debug -DOTC_BUILD_TESTS=ON
cmake --build c/build
```

`OTC_WITH_PREDICT` and `OTC_WITH_LOCALTIME` default to `ON`. `OTC_WITH_FETCH` defaults to `OFF` and needs libcurl when enabled.

Disabled modules return `OTC_E_NOT_BUILT`. Windows and FreeBSD use the local-time stub.

Initialize prediction options with `otc_predict_opts_init`. Times use UTC seconds. Windows use `[start, stop)`.

Use `otc_heights`, `otc_heights_at`, `otc_extremes`, `otc_currents`, and `otc_current_events` for predictions. Use `otc_datums` for datum levels and compatible ranges.

An array call reports its full count through `count`. A short buffer returns `OTC_E_BUFFER_TOO_SMALL`. `otc_heights_at` needs one output element per input time.

Initialize optional metadata with `otc_prediction_info_init`. Set `opts.info` to that object. Clear it with `otc_prediction_info_clear` after use.

Metadata owns its strings. They remain valid after the source station and release close. Another prediction clears the previous metadata, including on failure.

Station handles, datum strings, and astronomical table handles retain their existing borrowed lifetimes. Free stations before the release closes. Release handles are invalid after `otc_close`.

Historical results preserve source identifiers, reference identifiers, vintage labels, and the source note. Explicit `offset_id` and `set_id` are mutually exclusive.

The `exclude` policy refuses historical predictions. It retains source metadata. Unequal tide offsets and subordinate current offsets provide events only.

`otc_tz_open` loads a TZif file from `TZDIR` or `/usr/share/zoneinfo`. `otc_tz_local` preserves the UTC instant and returns the wall time and offset.

The time-zone wrapper uses vendored IANA tzcode 2026e. Its twelve external functions use private OTC names. It does not change process `TZ`.

The upstream tzcode files retain their public-domain licence. `vendor/tzcode/source.json` records their exact hashes. The cJSON and SHA-256 licences remain unchanged.

Prepare authenticated portable test input and run the tests:

```sh
ruby c/tests/materialize_vectors.rb c/build/native-vectors
OTC_PREDICT_NATIVE_JSONL="$PWD/c/build/native-vectors/OTC_20261011.jsonl" ctest --test-dir c/build -LE source_acceptance --output-on-failure
```

CI uses the committed 14-station vector release. The utility preserves every original station and metadata value and checks the original checksum.

The separate `source_acceptance` tests require the accepted H4 artifacts. They fail if their input variables are absent.

Run this mandatory local gate before integration:

```sh
OTC_CORE_NATIVE_JSONL=/accepted/H4/OTC_20261011.jsonl OTC_NOAA_NATIVE_JSONL=/accepted/historical-targets/OTC_20261011.jsonl ctest --test-dir c/build -L source_acceptance --output-on-failure
```

Use the sealed C0 conservation receipt and C1 historical receipt for those paths and hashes. Portable CI does not replace source acceptance.

The single-file bundle includes the same native prediction and time-zone code:

```sh
uv run c/tools/amalgamate.py --out c/dist
cc -std=c99 -Ic/dist -c c/dist/opentideconstants.c -o c/dist/otc.o
ruby c/tools/check_exports.sh c/dist/otc.o
```

Set `OTC_WITH_PREDICT=0` or `OTC_WITH_LOCALTIME=0` when compiling a bundle to disable that module.
