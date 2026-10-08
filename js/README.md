# opentideconstants

The JavaScript/TypeScript SDK for [OpenTideConstants](https://opentideconstants.org), an open dataset of tidal harmonic constants with provenance, validation scores and licences.

- No runtime dependencies. Node 22.12 or later, and modern browsers (fetch, WebCrypto, `DecompressionStream`, Cache Storage).
- Downloads a release from `data.opentideconstants.org`, checks its SHA-256, and caches it (`~/.cache/opentideconstants/v1`, shared with the Python, Ruby and C SDKs).
- ESM, with types. CommonJS code can `require("opentideconstants")` (Node's `require` of ES modules).

## Install

```
npm install opentideconstants
```

## Quickstart

```js
import { OpenTideConstants } from "opentideconstants";

const otc = await OpenTideConstants.open();                 // the latest release
const station = otc.stationByAlias("noaa", "9414290");
const m2 = station?.recommendedSet?.constituent("M2");
console.log(m2?.amplitude_m, m2?.phase_deg);                // metres, Greenwich phase lag in degrees
console.log(otc.attribution([station]));                     // the CC BY 4.0 attribution text
otc.close();
```

- Pin a release in production: `OpenTideConstants.open({ release: "20261008" })`. A cached, pinned release opens with no network access.
- Offline: `open({ offline: true })` (or `OPENTIDECONSTANTS_OFFLINE=1`) uses the newest cached release.
- A bundled file (Node): `open({ file: "OTC_20261008.jsonl" })`. Make one with `await otc.download({ release: "20261008", to: "data/" })`.
- Low memory: `open({ mode: "stream" })` reads one station at a time from `.jsonl`.

Method and option names are camelCase; data fields keep the schema's snake_case (`amplitude_m`, `qc_flags`). Errors are subclasses of `OpenTideConstantsError` and carry a stable `code`.

The full guide: https://opentideconstants.org. Code licence: MIT. The data is CC BY 4.0.
