# opentideconstants

The JavaScript/TypeScript SDK for [OpenTideConstants](https://opentideconstants.org), an open dataset of tidal harmonic constants with provenance, validation scores and licences.

- Node 22.12 or later is the main, recommended target. No runtime dependencies.
- Downloads a release from `data.opentideconstants.org`, checks its SHA-256, and caches it in a cache folder shared with the Python, Ruby and C SDKs: `~/Library/Caches/opentideconstants` on macOS, `%LOCALAPPDATA%\opentideconstants\Cache` on Windows, and `$XDG_CACHE_HOME/opentideconstants` (default `~/.cache/opentideconstants`) elsewhere. Set another folder with the `cacheDir` option or the `OPENTIDECONSTANTS_CACHE_DIR` environment variable.
- ESM only, with types. CommonJS code can `require("opentideconstants")` on Node 22.12 or later (Node's `require` of ES modules).

## Browsers

The same package runs in a browser. It reads releases and predicts tides and currents using native JavaScript. It fetches releases over CORS (it needs fetch, WebCrypto, `DecompressionStream` and Cache Storage). A browser has no file system, so these are not available there and fail with the `unsupported` error code:

- `cachedReleases()` and `prune()` (the local cache list);
- `autoUpdate`;
- `download()` (it always writes to a folder) and `open({ file })`.

## Install

```
npm install opentideconstants
```

The package is an ES module only. Its `exports` has `types`, `import` and `default`, and no CommonJS build:

- ES modules and TypeScript: `import { OpenTideConstants } from "opentideconstants"`. In TypeScript use `"module": "nodenext"` (or `"bundler"` resolution).
- CommonJS on Node 22.12 or later: `const { OpenTideConstants } = require("opentideconstants")` loads the ES module (Node's `require` of ES modules; Node 22.12 prints an `ExperimentalWarning` for it). TypeScript checks such a `require` with `"module": "nodenext"`; with `"node16"` it reports TS1471, so use `await import("opentideconstants")` there.

## Quickstart

```js
import { OpenTideConstants } from "opentideconstants";

const otc = await OpenTideConstants.open();                 // the latest release
try {
    const station = otc.stationByAlias("noaa", "9414290");  // null when the release has no such station
    if (station) {
        const m2 = station.recommendedSet?.constituent("M2");
        // metres, and the phase lag in degrees against the reference of the set's convention
        console.log(m2?.amplitude_m, m2?.phase_deg, station.recommendedSet?.convention.phase_reference);
        console.log(otc.attribution([station]));             // the CC BY 4.0 attribution text
    }
} finally {
    otc.close();
}
```

- Pin a release in production: `OpenTideConstants.open({ release: "20261008" })`. A cached, pinned release opens with no network access.
- Offline: `open({ offline: true })` (or `OPENTIDECONSTANTS_OFFLINE` set to `1`, `true`, `yes` or `on`) uses the newest cached release, and opens no socket.
- A bundled file (Node): `await otc.download({ release: "20261008", to: "data/" })` writes `OTC_20261008.jsonl`, its `.meta.json` and its `.sha256` into `data/`; open it with `open({ file: "data/OTC_20261008.jsonl" })`. Keep the three files together: the `.meta.json` is needed to read the `.jsonl`, and without the `.sha256` the release opens as `file_unverified`.
- Low memory: `open({ mode: "stream" })` reads one station at a time from `.jsonl`.

Method and option names are camelCase; data fields keep the schema's snake_case (`amplitude_m`, `qc_flags`). Errors are subclasses of `OpenTideConstantsError` and carry a stable `code`.

## Predictions

```js
const otc = await OpenTideConstants.open({ file: "data/OTC_20261011.jsonl" });
try {
    const station = otc.stationByAlias("noaa", "9414290");
    if (station) {
        const result = await otc.extremes(station.station_id, {
            start: new Date("2026-10-11T00:00:00Z"),
            stop: new Date("2026-10-12T00:00:00Z"),
            datum: "chart"
        });
        console.log(result.items, result.toLocal(station.timezone));
    }
} finally {
    otc.close();
}
```

`heights`, `heightsAt`, `extremes`, `currents` and `currentEvents` return promises for immutable results. `datums` and `ranges` are synchronous. `release.astroTable()` returns a promise. Times use UTC `Date` values; fractional seconds are floored. A window includes `start` and excludes `stop`.

Results retain the selected set, convention, astro table, datum and reference identifiers. Historical NOAA offsets also retain their source, vintage and reference labels. Their current accuracy is `unverified`; their current validity is `unestablished`. Unequal tide corrections support extrema only. Open with `historicalOffsetsPolicy: "exclude"` to exclude these offsets from discovery and prediction, including explicit selectors.

`toLocal(zone)` returns a new result. It leaves the UTC instants unchanged and adds wall times and UTC offsets. Node reports its native time-zone database version. Browsers report `null` when that version is unavailable.

`station.source_records` retains source records, provenance, dispositions and licence information, including records that cannot support a prediction. Inspect each record's licence and upstream licence before use. `commercialOnly` enforces the selected data's stated permissions; the SDK does not grant new permissions.

## Development checks

`npm run test:unit` runs the portable reader tests. `npm run test:native` is a separate mandatory acceptance gate that requires the actual release inputs. It fails when inputs are absent. Set `OTC_CORE_NATIVE_JSON`, `OTC_CORE_NATIVE_JSONL`, `OTC_CORE_NATIVE_META`, `OTC_PREDICT_NATIVE_JSON`, `OTC_HISTORY_NATIVE_JSON`, `OTC_HISTORY_NATIVE_JSONL`, `OTC_HISTORY_BROWSER_JSON` and `OTC_HISTORY_REFERENCE_REPORT` to the pinned artifacts. The browser historical input is a lossless subset of the same release. Restricted release artifacts are not bundled or fetched from an invented public URL. CI also checks the bundled immutable prediction vectors.

The full guide: https://opentideconstants.org. Code licence: MIT. Data permissions are recorded per source.
