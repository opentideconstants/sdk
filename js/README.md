# opentideconstants

The JavaScript/TypeScript SDK for [OpenTideConstants](https://opentideconstants.org), an open dataset of tidal harmonic constants with provenance, validation scores and licences.

- Node 22.12 or later is the main, recommended target. No runtime dependencies.
- Downloads a release from `data.opentideconstants.org`, checks its SHA-256, and caches it in a cache folder shared with the Python, Ruby and C SDKs: `~/Library/Caches/opentideconstants` on macOS, `%LOCALAPPDATA%\opentideconstants\Cache` on Windows, and `$XDG_CACHE_HOME/opentideconstants` (default `~/.cache/opentideconstants`) elsewhere. Set another folder with the `cacheDir` option or the `OPENTIDECONSTANTS_CACHE_DIR` environment variable.
- ESM only, with types. CommonJS code can `require("opentideconstants")` on Node 22.12 or later (Node's `require` of ES modules).

## Browsers

The same package runs in a browser, for read-only use: it fetches releases over CORS and reads them (it needs fetch, WebCrypto, `DecompressionStream` and Cache Storage). A browser has no file system, so these are not available there and fail with the `unsupported` error code:

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

The full guide: https://opentideconstants.org. Code licence: MIT. The data is CC BY 4.0.
