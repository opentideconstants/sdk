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
    st = otc.station_by_alias("noaa", "9414290")      # or otc.station("OTC-…"), otc.search(name="san fran")
    m2 = st.recommended_set.constituent("M2")
    print(st.name, m2.amplitude_m, m2.phase_deg)      # metres, degrees (Greenwich phase lag)
    for hit in otc.near(lat=37.8, lon=-122.4, radius_km=25):
        print(hit.station.station_id, hit.distance_km)
    print(otc.attribution([st]))
```

In production, pin a release: `OpenTideConstants(release="20261008")`. Offline: `offline=True` (or
`OPENTIDECONSTANTS_OFFLINE=1`). A bundled file: `OpenTideConstants(file="OTC_20261008.jsonl")`; make the
bundle with `otc.download("20261008", to="data/")`. Low memory: `mode="stream"`.

Every error is a subclass of `OpenTideConstantsError` and has a stable `.code`.

The SDK passes the shared conformance suite in `conformance/` (see `conformance/README.md`):

```
python3 conformance/driver.py --runner "python3 conformance/runners/python/runner.py"
python3 conformance/runners/python/check_api.py
```
