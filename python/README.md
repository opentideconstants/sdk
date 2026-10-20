# opentideconstants (Python)

The Python SDK for [OpenTideConstants](https://opentideconstants.org), an open dataset of harmonic tidal
constants. Standard library only; Python 3.10 or later. Code licence: MIT. The data is CC BY 4.0: show the
text of `attribution()` where you show the data.

```
pip install opentideconstants
```

## Quickstart

```python
from opentideconstants import OpenTideConstants

with OpenTideConstants() as otc:                      # the latest release, cached on disk
    # station(), station_by_alias() and nearest() return None when nothing matches; search() returns a tuple
    st = otc.station_by_alias("noaa", "9414290")
    if st is None:
        hits = otc.search(name="san fran", limit=1)
        st = hits[0] if hits else None
    if st is not None and st.recommended_set is not None:
        cs = st.recommended_set
        m2 = cs.constituent("M2")                     # None when the set has no M2
        if m2 is not None:
            # metres and degrees; the phase is a lag in the set's convention (cs.convention.phase_reference,
            # for example greenwich_utc or local)
            print(st.name, m2.amplitude_m, m2.phase_deg, cs.convention.phase_reference)
        print(otc.attribution([st]))
    for hit in otc.near(lat=37.8, lon=-122.4, radius_km=25):
        print(hit.station.station_id, hit.distance_km)
```

In production, pin a release: `OpenTideConstants(release="20261008")`. Offline: `offline=True` (or
`OPENTIDECONSTANTS_OFFLINE=1`). A bundled file: make the bundle with `otc.download("20261008", to="data/")`,
then open it with `OpenTideConstants(file="data/OTC_20261008.jsonl")`. Keep the files that `download` writes
together: a `.jsonl` needs its `OTC_20261008.meta.json` next to it, and `OTC_20261008.sha256` next to it makes
the SDK check the file (`loaded_from` is `file`; without it, `file_unverified`). Low memory: `mode="stream"`.

Every error the SDK raises is a subclass of `OpenTideConstantsError` and has a stable `.code`. A lookup that
finds nothing returns `None` instead of raising, so check the result before you use it. Import the names you
use: `from opentideconstants import *` replaces the built-in FileExistsError in your module with the SDK's
`FileExistsError`, so `except FileExistsError` no longer catches the OS error of `os.mkdir` or `open(path, "x")`.

The SDK passes the shared conformance suite in `conformance/` (see `conformance/README.md`):

```
python3 conformance/driver.py --runner "python3 conformance/runners/python/runner.py"
python3 conformance/runners/python/check_api.py
```

## Prediction units

`heights`, `heights_at`, and `extremes` accept `units="meters"` (the default) or
`units="feet"`. Read each item's `height` for the selected value. `currents` and
`current_events` accept `units="m/s"` (the default) or `units="knots"`. Current
points expose `velocity_major`, `velocity_minor`, and `speed`; current events
expose `velocity`. The same options are available on the client and its `release`.

Every prediction result and item has a read-only `units` label for these selected
values. Existing fields such as `height_m`, `velocity_major_ms`, `speed_ms`, and
`datum_uncertainty_m` remain in SI units. Conversion uses final SI values: divide
heights by `0.3048` for feet and currents by `1852.0 / 3600.0` for knots. Times,
event types, directions, and provenance are unchanged. `to_local()` preserves
the selected units. Unsupported unit strings raise `InvalidArgumentError`.
