"""Quickstart: open the latest release, find a station, read its M2 constants and the attribution.

    python quickstart.py                    # https://data.opentideconstants.org/
    OPENTIDECONSTANTS_BASE_URL=http://127.0.0.1:8765/good/ python quickstart.py   # the conformance fixture server
"""
from opentideconstants import OpenTideConstants

with OpenTideConstants() as otc:
    print("release", otc.release.datestamp, "format", otc.release.format_version, "from", otc.loaded_from)
    print("stations", otc.release.station_count)
    st = otc.station_by_alias("noaa", "9414290") or otc.search(name="san francisco", limit=1)[0]
    print("station", st.station_id, st.name, st.lat, st.lon)
    m2 = st.recommended_set.constituent("M2")
    print("M2", m2.amplitude_m, "m", m2.phase_deg, "deg")
    for hit in otc.near(lat=st.lat, lon=st.lon, radius_km=25, limit=3):
        print("near", hit.station.station_id, round(hit.distance_km, 3), "km")
    print(otc.attribution([st]))
