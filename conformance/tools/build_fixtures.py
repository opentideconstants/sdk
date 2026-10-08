# /// script
# requires-python = ">=3.12"
# dependencies = ["jsonschema==4.25.1"]
# ///
"""Build and check the conformance fixture releases (SDK spec §7.1).

Run: uv run conformance/tools/build_fixtures.py            (writes conformance/fixtures/good, bad, fixtures.json)
     uv run conformance/tools/build_fixtures.py --check    (writes nothing; exit 0 only if all checks pass)

All data is synthetic and CC0-1.0. The station names, ids, providers and numbers
are made up for tests. They are not tidal data.

--check does three things:
  1. Regenerates every fixture in a temporary directory and compares it with
     the committed files, byte for byte.
  2. Good fixtures: each release validates against format 0.2 (the .json against
     the schema, the .meta.json against #/$defs/meta, each .jsonl line against
     #/$defs/station), the cross-references resolve, and the .json, .json.gz,
     .jsonl, .meta.json, .sha256, pointers and index agree.
  3. Bad fixtures: a small reference reader (the rules of spec §5.2, §7.3 and
     §7.4) opens each one, and the outcome must be the one in fixtures.json:
     the error code, or "load" for the higher-minor release.

The schema is format 0.2 from the site repository, pinned by commit and SHA-256.
Pass --schema PATH to use a local copy; it must have the pinned SHA-256.
"""
import argparse
import copy
import gzip
import hashlib
import json
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path

from jsonschema import Draft202012Validator

SCHEMA_COMMIT = "88b6418edeeda065ba3e96ee26368faefcbd7f12"
SCHEMA_URL = f"https://raw.githubusercontent.com/opentideconstants/opentideconstants/{SCHEMA_COMMIT}/src/schema/otc-0.2.schema.json"
SCHEMA_SHA256 = "5645522d5cbc34d21918f274f1b22daae3e3622459fe74ec90c2b7b30f4d6894"
KNOWN_FORMAT = (0, 2)
SUPPORTED_MAJORS = [0]

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
GENERATED = ["good", "order", "bad", "fixtures.json"]

BASE = "20991231"
SECOND = "20991231.2"
# A counter whose string order differs from its numeric order: .10 is newer than .2 (spec 4.3.1)
COUNTER = "20991231.10"
TABLE = "otc-test-1"


# --------------------------------------------------------------------------- data

def constituent(name, amp, phase, **extra):
    speeds = {"M2": 28.9841042, "S2": 30.0, "N2": 28.4397295, "K1": 15.0410686, "O1": 13.9430356,
              "M4": 57.9682084, "SA": 0.0410686}
    c = {"name": name, "speed_deg_per_hour": speeds[name], "amplitude_m": amp, "phase_deg": phase}
    c.update(extra)
    return c


def full_constituents(scale):
    """Constituents with every optional field."""
    doodson = {"M2": "255 555", "S2": "273 555", "N2": "245 655", "K1": "165 555", "O1": "145 555"}
    rows = [("M2", 0.5, 101.25), ("S2", 0.15, 130.5), ("N2", 0.1, 85.0), ("K1", 0.3, 210.75), ("O1", 0.2, 195.0)]
    return [constituent(n, round(a * scale, 4), p, source_name=f"{n} (source)", doodson=doodson[n],
                        amp_uncertainty_m=0.001, phase_uncertainty_deg=0.2, kept_reason="snr")
            for n, a, p in rows]


def simple_constituents(scale, phase_shift=0.0):
    """Constituents with only the required fields."""
    return [constituent("M2", round(0.4 * scale, 4), round((90.0 + phase_shift) % 360, 4)),
            constituent("K1", round(0.1 * scale, 4), round((180.0 + phase_shift) % 360, 4))]


def cset(station_id, suffix, source, source_type, convention_id, licence_id, constituents, *,
         qc_status="accepted", quantity="water_level", provenance=None, **extra):
    s = {
        "set_id": f"{station_id}/{suffix}",
        "source": source,
        "source_type": source_type,
        "quantity": quantity,
        "source_record_id": f"{source}:{station_id[4:]}",
        "source_version": BASE,
        "convention_id": convention_id,
        "licence_id": licence_id,
        "qc_status": qc_status,
        "constituents": constituents,
        "provenance": provenance if provenance is not None else {"adapter_version": "0.0.0-test"},
    }
    s.update(extra)
    return s


def active(station_id, name, country, lat, lon, timezone, sets, *, type_="reference", recommended=None,
           aliases=None, **extra):
    st = {
        "station_id": station_id, "status": "active", "name": name, "country": country,
        "lat": lat, "lon": lon, "timezone": timezone, "type": type_,
        "recommended_set_id": recommended if recommended is not None or type_ == "subordinate" or not sets
        else sets[0]["set_id"],
        "constant_sets": sets,
    }
    if aliases is not None:
        st["aliases"] = aliases
    st.update(extra)
    return st


def gauge_station(station_id, name, country, lat, lon, timezone, scale, **kw):
    return active(station_id, name, country, lat, lon, timezone,
                  [cset(station_id, "gesla-fit", "gesla-fit", "gauge", "otc-greenwich-v1", "gesla-derived",
                        simple_constituents(scale))], **kw)


def model_station(station_id, name, country, lat, lon, timezone, scale):
    return active(station_id, name, country, lat, lon, timezone,
                  [cset(station_id, "eot20", "eot20", "model", "otc-greenwich-v1", "eot20",
                        simple_constituents(scale, phase_shift=lon))])


def release_doc(datestamp):
    conventions = [
        {
            "convention_id": "otc-greenwich-v1",
            "phase_reference": "greenwich_utc",
            "v0_model": "schureman_tcd",
            "nodal_handling": "f_u_at_prediction",
            "nodal_formula_ids": {"M2": "M2", "S2": 0, "N2": "M2", "K1": "K1", "O1": "O1", "M4": "M2^2"},
            "constituent_table_version": TABLE,
            "tables_sha256": hashlib.sha256(TABLE.encode()).hexdigest(),
            "canary": {"status": "not_applicable"},
        },
        {
            "convention_id": "kartverket-utc1-v1",
            "phase_reference": "local",
            "utc_offset_hours": 1,
            "v0_model": "schureman_tcd",
            "nodal_handling": "f_u_at_prediction",
            "constituent_table_version": TABLE,
            "canary": {"status": "pass", "gauges": 3, "median_amp_diff_m": 0.004, "median_phase_diff_deg": 0.8},
        },
        {
            "convention_id": "noaa-greenwich-v1",
            "phase_reference": "greenwich_utc",
            "v0_model": "schureman_tcd",
            "nodal_handling": "f_u_at_prediction",
            "constituent_table_version": TABLE,
        },
    ]
    licences = [
        {"licence_id": "eot20", "spdx": "CC-BY-4.0", "provider": "Example Tide Model Group",
         "attribution": "Example tide model, interpolated by OpenTideConstants tests."},
        {"licence_id": "gesla-derived", "spdx": "CC-BY-4.0", "provider": "Example Gauge Agency via GESLA",
         "citation": "Example Gauge Agency (2099). Example sea level records. Test citation.",
         "attribution": "Contains synthetic test data in the style of GESLA-4.",
         "url": "https://example.org/gesla-test"},
        {"licence_id": "kartverket", "spdx": "CC-BY-4.0", "provider": "Example Mapping Authority",
         "attribution": "Synthetic test data, Example Mapping Authority."},
        {"licence_id": "noaa", "spdx": "LicenseRef-PublicDomain-USGov", "provider": "Example Ocean Service",
         "attribution": "Synthetic test data in the style of a public-domain US agency."},
    ]
    table = [
        {"constituent_table_version": TABLE, "name": "K1", "doodson": "165 555", "speed_deg_per_hour": 15.0410686, "nodal_formula_id": "K1"},
        {"constituent_table_version": TABLE, "name": "M2", "doodson": "255 555", "speed_deg_per_hour": 28.9841042, "nodal_formula_id": "M2"},
        {"constituent_table_version": TABLE, "name": "M4", "doodson": "455 555", "speed_deg_per_hour": 57.9682084, "nodal_formula_id": "M2^2"},
        {"constituent_table_version": TABLE, "name": "N2", "doodson": "245 655", "speed_deg_per_hour": 28.4397295, "nodal_formula_id": "M2"},
        {"constituent_table_version": TABLE, "name": "O1", "doodson": "145 555", "speed_deg_per_hour": 13.9430356, "nodal_formula_id": "O1"},
        {"constituent_table_version": TABLE, "name": "S2", "doodson": "273 555", "speed_deg_per_hour": 30.0, "nodal_formula_id": 0},
        {"constituent_table_version": TABLE, "name": "SA", "doodson": "056 555", "speed_deg_per_hour": 0.0410686},
    ]

    s1 = "OTC-T-0001"
    noaa_set = cset(
        s1, "noaa", "noaa", "official", "noaa-greenwich-v1", "noaa", full_constituents(1.0),
        record_span={"start": "2080-01-01T00:00:00Z", "end": "2098-12-31T23:00:00Z", "good_samples": 166000},
        datum={"msl_offset_m": 0.0, "named": {"MHHW": 0.91, "MLLW": -0.93}},
        provenance={"adapter_version": "0.0.0-test", "build_commit": "0123456",
                    "input_sha256": [hashlib.sha256(b"noaa-input").hexdigest()],
                    "selection_reason": "official constants from the operating agency",
                    "decision": {"tier": "rule", "outcome": "accept", "rule": "D1", "reason": "official"},
                    "harvested_at": "2099-12-30T00:00:00Z"},
    )
    gesla_set = cset(
        s1, "gesla-fit", "gesla-fit", "gauge", "otc-greenwich-v1", "gesla-derived", full_constituents(1.01),
        record_span={"start": "2070-01-01T00:00:00Z", "end": "2098-01-01T00:00:00Z"},
        qc_flags=[{"flag": "time_base", "verdict": "utc_instant", "values": {"lag_min": 0.0}}],
        dropped_constituents=[{"name": "SA", "dropped_reason": "rayleigh"},
                              {"name": "M4", "dropped_reason": "noise", "detail": "snr 1.2 below 2.0"}],
        provenance={"adapter_version": "0.0.0-test", "build_commit": "0123456",
                    "time_base": {"verdict": "utc_instant", "correction": "none", "comparators": ["OTC-T-0001/noaa"]},
                    "selection_reason": "longest clean record",
                    "decision": {"tier": "rule", "outcome": "accept", "rule": "D2", "reason": "within tolerance"},
                    "fit_window_days": 10227, "future_note": {"nested": [1, 2, 3]}},
    )
    validation = [
        {"set_id": f"{s1}/gesla-fit", "reference_source": "noaa", "reference_station": "9900001",
         "reference_distance_km": 0.0, "window": "2099-01", "time_mae_min": 2.5, "time_p95_min": 6.0,
         "time_bias_min": -0.5, "height_mae_m": 0.02, "range_error_m": 0.01, "missed_events": 0,
         "extra_events": 0, "previous_release": None},
        {"set_id": f"{s1}/gesla-fit", "reference_source": "noaa", "window": "2099-02",
         "time_mae_min": 2.25, "height_mae_m": 0.019},
        {"set_id": f"{s1}/noaa", "reference_source": "noaa", "reference_station": "9900001",
         "window": "2099-01", "time_mae_min": 1.0, "time_p95_min": 2.0, "height_mae_m": 0.01,
         "missed_events": 0, "extra_events": 1,
         "previous_release": {"time_mae_min": 1.25, "time_p95_min": 2.5, "height_mae_m": 0.011,
                              "missed_events": 0, "extra_events": 0}},
    ]
    stations = [
        active(s1, "San Francisco", "USA", 37.8063, -122.4659, "America/Los_Angeles", [noaa_set, gesla_set],
               recommended=f"{s1}/noaa",
               aliases={"noaa": "9900001", "gesla": ["test-gesla-0001a", "test-gesla-0001b"], "ticon": ["test-ticon-0001"],
                        "xtide": "San Francisco (test), California", "kartverket": "TSF", "slackwater": "sw-0001",
                        "webcaltides": "wct-0001"},
               validation=validation),
        active("OTC-T-0002", "South San Francisco", "USA", 37.665, -122.38, "America/Los_Angeles",
               [cset("OTC-T-0002", "fallback", "ticon-fallback", "gauge", "otc-greenwich-v1", "gesla-derived",
                     simple_constituents(0.9), qc_status="fallback"),
                cset("OTC-T-0002", "gesla-fit", "gesla-fit", "gauge", "otc-greenwich-v1", "gesla-derived",
                     simple_constituents(3.0), qc_status="excluded",
                     qc_flags=[{"flag": "broken_record", "verdict": "k3_step", "values": {"step_m": 0.4}}])],
               recommended="OTC-T-0002/fallback", aliases={"noaa": "9900002"}),
        active("OTC-T-0003", "Alameda", "USA", 37.772, -122.3, "America/Los_Angeles", [], type_="subordinate",
               aliases={"noaa": "9900003"},
               subordinate_offsets={"reference_station_id": s1, "time_offset_high_min": 12, "time_offset_low_min": 20,
                                    "height_offset_high": 1.05, "height_offset_low": 0.98,
                                    "height_adjusted_type": "R", "licence_id": "noaa"}),
        active("OTC-T-0004", "Oakland Pier", "USA", 37.795, -122.33, "America/Los_Angeles",
               [cset("OTC-T-0004", "noaa", "noaa", "official", "noaa-greenwich-v1", "noaa", simple_constituents(1.02))],
               type_="subordinate", recommended="OTC-T-0004/noaa", aliases={"noaa": "9900004"},
               subordinate_offsets={"reference_station_id": s1, "time_offset_high_min": -5, "time_offset_low_min": 4,
                                    "height_offset_high": 0.12, "height_offset_low": -0.05,
                                    "height_adjusted_type": "A"}),
        {"station_id": "OTC-T-0005", "status": "removed", "name": "Old Pier", "removed_in": BASE,
         "removed_reason": "Duplicate of OTC-T-0001 (test tombstone)."},
        active("OTC-T-0006", "Tromsø", "NOR", 69.6468, 18.9543, "Europe/Oslo",
               [cset("OTC-T-0006", "kartverket", "kartverket", "official", "kartverket-utc1-v1", "kartverket",
                     simple_constituents(1.1))], aliases={"kartverket": "TOS"}),
        model_station("OTC-T-0007", "Antimeridian East", "FJI", 0.0, 179.9, "Pacific/Fiji", 0.6),
        model_station("OTC-T-0008", "Antimeridian West", "KIR", 0.0, -179.9, "Pacific/Tarawa", 0.6),
        model_station("OTC-T-0009", "Polar Station", "SJM", 89.9, 0.0, "Arctic/Longyearbyen", 0.2),
        gauge_station("OTC-T-0010", "Equator Station", "GAB", 0.0, 9.0, "Africa/Libreville", 0.7),
        gauge_station("OTC-T-0011", "Ålesund", "NOR", 62.4722, 6.1517, "Europe/Oslo", 0.8, aliases={"gesla": ["test-gesla-0011"]}),
        gauge_station("OTC-T-0012", "Łeba", "POL", 54.76, 17.556, "Europe/Warsaw", 0.05),
        gauge_station("OTC-T-0013", "Straße", "DEU", 54.0, 10.0, "Europe/Berlin", 0.3),
        gauge_station("OTC-T-0014", "Harbour", "GBR", 50.8, -1.1, "Europe/London", 1.5),
        gauge_station("OTC-T-0015", "Harbour", "IRL", 53.35, -6.2, "Europe/Dublin", 1.4),
        gauge_station("OTC-T-0016", "Harbour Point", "GBR", 50.7, -1.3, "Europe/London", 1.5),
        gauge_station("OTC-T-0017", "North Harbour", "GBR", 55.0, -1.4, "Europe/London", 1.6),
        gauge_station("OTC-T-0018", "Seaharbour", "GBR", 51.0, 1.3, "Europe/London", 1.7),
        active("OTC-T-0019", "Test Current Pass", "USA", 47.9, -122.6, "America/Los_Angeles",
               [cset("OTC-T-0019", "noaa", "noaa", "official", "noaa-greenwich-v1", "noaa",
                     simple_constituents(1.3), quantity="current")], aliases={"noaa": "TEST1901"}),
        active("OTC-T-0020", "Minimal Station", "USA", 21.3, -157.9, "Pacific/Honolulu",
               [cset("OTC-T-0020", "noaa", "noaa", "official", "noaa-greenwich-v1", "noaa",
                     simple_constituents(0.25), provenance={})]),
    ]
    doc = {
        "format_version": "0.2",
        "release": {
            "datestamp": datestamp,
            "created": "2099-12-31T00:00:00Z",
            "doi": None,
            "concept_doi": None,
            "source_versions": {"eot20": "20991231", "gesla": "4.1", "kartverket": "20991231", "noaa": "20991231"},
            "build_commit": "0123456789abcdef0123456789abcdef01234567",
            "changelog_url": f"https://opentideconstants.org/changelog/#{datestamp}",
        },
        "conventions": conventions,
        "licences": licences,
        "constituents": table,
        "stations": stations,
    }
    if datestamp == BASE:
        doc["stations"].append(gauge_station("OTC-T-0021", "Closing Pier", "GBR", 52.0, 1.7, "Europe/London", 1.2))
    else:
        rel = doc["release"]
        rel["created"] = "2099-12-31T12:00:00Z"
        rel["doi"] = "10.5072/zenodo.2"
        rel["concept_doi"] = "10.5072/zenodo.1"
        del rel["build_commit"]
        del rel["changelog_url"]
        doc["stations"].append({"station_id": "OTC-T-0021", "status": "removed", "name": "Closing Pier",
                                "removed_in": SECOND, "removed_reason": "Gauge closed (test tombstone)."})
        doc["stations"].append(gauge_station("OTC-T-0022", "New Pier", "GBR", 52.1, 1.75, "Europe/London", 1.25))
    doc["stations"].sort(key=lambda s: s["station_id"])
    return doc


# --------------------------------------------------------------------------- serialisation

def dumps_data(obj):
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def dumps_pretty(obj):
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=1) + "\n").encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def gz(data, reuse):
    """gzip with no name and mtime 0. Reuse committed bytes when they hold the same content,
    so a different zlib build does not change the committed fixtures."""
    if reuse is not None and reuse.exists():
        old = reuse.read_bytes()
        try:
            if gzip.decompress(old) == data:
                return old
        except (OSError, EOFError):
            pass
    return gzip.compress(data, compresslevel=9, mtime=0)


def release_files(doc, reuse_dir):
    """The data files of one release: name -> bytes (no .sha256)."""
    d = doc["release"]["datestamp"]
    meta = {k: v for k, v in doc.items() if k != "stations"}
    body = dumps_data(doc)
    files = {
        f"OTC_{d}.json": body,
        f"OTC_{d}.json.gz": gz(body, reuse_dir / f"OTC_{d}.json.gz" if reuse_dir else None),
        f"OTC_{d}.jsonl": b"".join(dumps_data(s) for s in doc["stations"]),
        f"OTC_{d}.meta.json": dumps_data(meta),
    }
    return files


def sha256_list(files):
    return "".join(f"{sha(files[n])}  {n}\n" for n in sorted(files)).encode()


def pointer_entry(doc, files, sums):
    d = doc["release"]["datestamp"]
    entries = [{"name": n, "url": n, "size": len(b), "sha256": sha(b)} for n, b in sorted(files.items())]
    entries.append({"name": f"OTC_{d}.sha256", "url": f"OTC_{d}.sha256", "size": len(sums), "sha256": sha(sums)})
    entries.sort(key=lambda e: e["name"])
    rel = doc["release"]
    return {"datestamp": d, "format_version": doc["format_version"], "created": rel["created"],
            "doi": rel.get("doi"), "concept_doi": rel.get("concept_doi"), "files": entries}


def datestamp_key(d):
    date, _, counter = d.partition(".")
    return (date, int(counter) if counter else 1)


def write_root(root, docs, *, reuse_root=None, tamper=None):
    """Write the releases in docs, their .sha256 files, the pointers and the index into root.
    tamper(name, files, sums, entry) may change what is written after the honest values are computed."""
    root.mkdir(parents=True, exist_ok=True)
    entries = []
    for doc in docs:
        files = release_files(doc, reuse_root)
        sums = sha256_list(files)
        entry = pointer_entry(doc, files, sums)
        if tamper:
            files, sums, entry = tamper(files, sums, entry, reuse_root)
        for name, data in files.items():
            (root / name).write_bytes(data)
        (root / f"OTC_{doc['release']['datestamp']}.sha256").write_bytes(sums)
        entries.append(entry)
    entries.sort(key=lambda e: datestamp_key(e["datestamp"]), reverse=True)
    latest = entries[0]
    (root / "OTC_latest.json").write_bytes(dumps_pretty(latest))
    majors = sorted({int(e["format_version"].split(".")[0]) for e in entries})
    for major in majors:
        newest = next(e for e in entries if int(e["format_version"].split(".")[0]) == major)
        (root / f"OTC_latest-f{major}.json").write_bytes(dumps_pretty(newest))
    (root / "OTC_index.json").write_bytes(dumps_pretty({"releases": entries}))


# --------------------------------------------------------------------------- bad fixtures

def corrupt_same_size(files, sums, entry, reuse):
    """Change one byte in every station data file; keep the honest SHA-256 list and pointer."""
    out = dict(files)
    for name in list(out):
        if name.endswith(".json") and not name.endswith(".meta.json"):
            out[name] = out[name].replace(b"San Francisco", b"San Franciscx", 1)
        elif name.endswith(".jsonl"):
            out[name] = out[name].replace(b"San Francisco", b"San Franciscx", 1)
    for name in list(out):
        if name.endswith(".json.gz"):
            plain = out[name[:-3]]
            out[name] = gz(plain, reuse / name if reuse else None)
    return out, sums, entry


def truncate(files, sums, entry, reuse):
    out = dict(files)
    for name in list(out):
        if not name.endswith(".meta.json"):
            out[name] = out[name][: len(out[name]) // 2]
    return out, sums, entry


def pointer_disagrees(files, sums, entry, reuse):
    entry = copy.deepcopy(entry)
    for f in entry["files"]:
        if not f["name"].endswith(".sha256"):
            f["sha256"] = sha(b"pointer-mismatch:" + f["name"].encode())
    return files, sums, entry


def major_doc():
    doc = release_doc(BASE)
    doc["format_version"] = "1.0"
    return doc


def minor_doc():
    doc = release_doc(BASE)
    doc["format_version"] = "0.3"
    doc["future_top_level"] = {"note": "added by format 0.3 (test)"}
    doc["release"]["future_release_field"] = "0.3 release field"
    doc["conventions"][0]["future_convention_field"] = 1
    doc["licences"][0]["future_licence_field"] = True
    st = next(s for s in doc["stations"] if s["station_id"] == "OTC-T-0001")
    st["future_station_field"] = {"depth_m": 12.5}
    st["aliases"]["future_system"] = "FS-0001"
    st["constant_sets"][0]["future_set_field"] = "0.3 set field"
    st["constant_sets"][0]["constituents"][0]["future_constituent_field"] = 0.5
    return doc


def unresolved_doc():
    doc = release_doc(BASE)
    st = next(s for s in doc["stations"] if s["station_id"] == "OTC-T-0010")
    st["constant_sets"][0]["convention_id"] = "no-such-convention"
    return doc


BAD = [
    ("wrong-sha256", "checksum_mismatch", "every station data file differs from its SHA-256 in OTC_20991231.sha256 and the pointer (same size, one byte changed)",
     lambda: [release_doc(BASE)], corrupt_same_size),
    ("truncated", "checksum_mismatch", "the .json, .json.gz and .jsonl files are cut to half their size; the pointer and .sha256 give the full size and hash",
     lambda: [release_doc(BASE)], truncate),
    ("pointer-mismatch", "checksum_mismatch", "the files match OTC_20991231.sha256, but the pointer and index give other SHA-256 values",
     lambda: [release_doc(BASE)], pointer_disagrees),
    ("format-major", "unsupported_format", "format_version 1.0, one major above the supported major 0",
     lambda: [major_doc()], None),
    ("format-minor", "load", "format_version 0.3 with unknown fields (top level, release, convention, licence, station, alias system, set, constituent); it must load and keep them in raw",
     lambda: [minor_doc()], None),
    ("unresolved-convention", "invalid_release", "OTC-T-0010's set has convention_id no-such-convention",
     lambda: [unresolved_doc()], None),
]


def build(out, reuse):
    """Write good/, bad/ and fixtures.json under out. reuse = committed fixtures dir (for .gz bytes) or None."""
    write_root(out / "good", [release_doc(BASE), release_doc(SECOND)],
               reuse_root=(reuse / "good") if reuse else None)
    write_root(out / "order", [release_doc(SECOND), release_doc(COUNTER)],
               reuse_root=(reuse / "order") if reuse else None)
    manifest = {
        "description": "Conformance fixture releases (SDK spec 7.1). Synthetic data, CC0-1.0. Generated by conformance/tools/build_fixtures.py; do not edit.",
        "schema": {"url": SCHEMA_URL, "sha256": SCHEMA_SHA256},
        "supported_format_majors": SUPPORTED_MAJORS,
        "fixtures": [{"root": "good", "releases": [SECOND, BASE], "latest": SECOND, "expect": "load",
                      "defect": None},
                     {"root": "order", "releases": [COUNTER, SECOND], "latest": COUNTER, "expect": "load",
                      "defect": None}],
    }
    for name, expect, defect, docs, tamper in BAD:
        write_root(out / "bad" / name, docs(), reuse_root=(reuse / "bad" / name) if reuse else None, tamper=tamper)
        manifest["fixtures"].append({"root": f"bad/{name}", "releases": [BASE], "latest": BASE,
                                     "expect": expect if expect == "load" else {"error": expect},
                                     "defect": defect})
    (out / "fixtures.json").write_bytes(dumps_pretty(manifest))


# --------------------------------------------------------------------------- reference reader (check only)

class Fail(Exception):
    def __init__(self, code, detail):
        super().__init__(f"{code}: {detail}")
        self.code = code


def load_schema(path):
    data = Path(path).read_bytes() if path else urllib.request.urlopen(SCHEMA_URL, timeout=30).read()
    if sha(data) != SCHEMA_SHA256:
        raise SystemExit(f"schema SHA-256 {sha(data)} is not the pinned {SCHEMA_SHA256}")
    return json.loads(data)


def resolve(schema, node):
    while isinstance(node, dict) and "$ref" in node:
        node = schema["$defs"][node["$ref"].split("/")[-1]]
    return node


def strip_unknown(schema, value, node):
    """Tolerant read (spec 7.3): drop the fields that format 0.2 does not define. Returns (value, dropped paths)."""
    dropped = []

    def walk(v, n, path):
        n = resolve(schema, n)
        if not isinstance(n, dict):
            return v
        if "oneOf" in n and isinstance(v, dict):
            for branch in n["oneOf"]:
                b = resolve(schema, branch)
                if b["properties"]["status"].get("const") == v.get("status"):
                    n = b
                    break
        if isinstance(v, dict):
            props = n.get("properties", {})
            extra = n.get("additionalProperties", True)
            out = {}
            for k, item in v.items():
                if k in props:
                    out[k] = walk(item, props[k], f"{path}.{k}")
                elif extra is False:
                    dropped.append(f"{path}.{k}")
                else:
                    out[k] = walk(item, extra, f"{path}.{k}") if isinstance(extra, dict) else item
            return out
        if isinstance(v, list) and "items" in n:
            return [walk(item, n["items"], f"{path}[{i}]") for i, item in enumerate(v)]
        return v

    return walk(value, schema, "$"), dropped


def cross_ref_errors(doc):
    errs = []
    conv = {c["convention_id"] for c in doc["conventions"]}
    lic = {l["licence_id"] for l in doc["licences"]}
    table = {(c["constituent_table_version"], c["name"]) for c in doc["constituents"]}
    conv_table = {c["convention_id"]: c["constituent_table_version"] for c in doc["conventions"]}
    ids = [s["station_id"] for s in doc["stations"]]
    if len(ids) != len(set(ids)):
        errs.append("duplicate station_id")
    if ids != sorted(ids):
        errs.append("stations not ordered by station_id")
    active_ids = {s["station_id"] for s in doc["stations"] if s["status"] == "active"}
    seen_alias = {}
    set_ids = set()
    for s in doc["stations"]:
        if s["status"] != "active":
            continue
        sid = s["station_id"]
        own = {cs["set_id"] for cs in s["constant_sets"]}
        for cs in s["constant_sets"]:
            if cs["set_id"] in set_ids:
                errs.append(f"duplicate set_id {cs['set_id']}")
            set_ids.add(cs["set_id"])
            if cs["convention_id"] not in conv:
                errs.append(f"{cs['set_id']}: convention_id {cs['convention_id']} does not resolve")
            if cs["licence_id"] not in lic:
                errs.append(f"{cs['set_id']}: licence_id {cs['licence_id']} does not resolve")
            tv = conv_table.get(cs["convention_id"])
            for c in cs["constituents"] + cs.get("dropped_constituents", []):
                if tv and (tv, c["name"]) not in table:
                    errs.append(f"{cs['set_id']}: constituent {c['name']} not in table {tv}")
        rec = s["recommended_set_id"]
        if rec is not None and rec not in own:
            errs.append(f"{sid}: recommended_set_id {rec} does not resolve")
        if rec is None and not (s["type"] == "subordinate" and "subordinate_offsets" in s):
            errs.append(f"{sid}: recommended_set_id is null but the station is not a subordinate with offsets")
        if s["type"] == "subordinate" and "subordinate_offsets" not in s:
            errs.append(f"{sid}: subordinate without subordinate_offsets")
        off = s.get("subordinate_offsets")
        if off:
            if off["reference_station_id"] not in active_ids:
                errs.append(f"{sid}: reference_station_id {off['reference_station_id']} does not resolve")
            if "licence_id" in off and off["licence_id"] not in lic:
                errs.append(f"{sid}: offsets licence_id {off['licence_id']} does not resolve")
        for v in s.get("validation", []):
            if v["set_id"] not in own:
                errs.append(f"{sid}: validation set_id {v['set_id']} does not resolve")
        for system, val in s.get("aliases", {}).items():
            for a in val if isinstance(val, list) else [val]:
                owner = seen_alias.setdefault((system, a), sid)
                if owner != sid:
                    errs.append(f"alias {system}:{a} used by {owner} and {sid}")
    return errs


def open_release(root, datestamp, schema):
    """Reference reader: what an SDK must do with this release. Returns a summary dict or raises Fail."""
    index = json.loads((root / "OTC_index.json").read_bytes())
    entry = next((e for e in index["releases"] if e["datestamp"] == datestamp), None)
    if entry is None:
        raise Fail("release_not_found", datestamp)
    sums_path = root / f"OTC_{datestamp}.sha256"
    sums = {}
    for line in sums_path.read_text(encoding="utf-8").splitlines():
        digest, name = line.split("  ", 1)
        sums[name] = digest
    # Spec 5.2 step 4.1: the pointer and the .sha256 file must agree.
    for f in entry["files"]:
        if f["name"] == sums_path.name:
            if sha(sums_path.read_bytes()) != f["sha256"]:
                raise Fail("checksum_mismatch", f"{f['name']}: pointer and file differ")
            continue
        if sums.get(f["name"]) != f["sha256"]:
            raise Fail("checksum_mismatch", f"{f['name']}: pointer {f['sha256']} vs .sha256 {sums.get(f['name'])}")
    if set(sums) != {f["name"] for f in entry["files"]} - {sums_path.name}:
        raise Fail("checksum_mismatch", "pointer and .sha256 list different files")
    # Step 4.2: size and SHA-256 of every file.
    for f in entry["files"]:
        data = (root / f["name"]).read_bytes()
        if len(data) != f["size"]:
            raise Fail("checksum_mismatch", f"{f['name']}: size {len(data)} vs {f['size']}")
        if sha(data) != f["sha256"]:
            raise Fail("checksum_mismatch", f"{f['name']}: sha256 {sha(data)} vs {f['sha256']}")
    body = (root / f"OTC_{datestamp}.json").read_bytes()
    if gzip.decompress((root / f"OTC_{datestamp}.json.gz").read_bytes()) != body:
        raise Fail("checksum_mismatch", ".json.gz does not decompress to .json")
    try:
        doc = json.loads(body)
        meta = json.loads((root / f"OTC_{datestamp}.meta.json").read_bytes())
        lines = [json.loads(l) for l in (root / f"OTC_{datestamp}.jsonl").read_text(encoding="utf-8").splitlines()]
    except ValueError as e:
        raise Fail("invalid_release", f"not JSON: {e}")
    # Spec 7.4: the major must be supported.
    major, minor = (int(x) for x in str(doc.get("format_version", "")).split("."))
    if major not in SUPPORTED_MAJORS:
        raise Fail("unsupported_format", f"format_version {doc['format_version']}")
    # Spec 7.3: a higher minor is read tolerantly; unknown fields stay in raw.
    dropped = []
    checked = doc
    if (major, minor) > KNOWN_FORMAT:
        checked, dropped = strip_unknown(schema, doc, schema)
        checked["format_version"] = "%d.%d" % KNOWN_FORMAT
    errs = [f"{list(e.path)} {e.message}" for e in Draft202012Validator(schema).iter_errors(checked)]
    errs += cross_ref_errors(checked)
    if errs:
        raise Fail("invalid_release", "; ".join(errs[:5]))
    if (major, minor) <= KNOWN_FORMAT:
        defs = {"$schema": schema["$schema"], "$defs": schema["$defs"]}
        meta_v = Draft202012Validator({**defs, "$ref": "#/$defs/meta"})
        st_v = Draft202012Validator({**defs, "$ref": "#/$defs/station"})
        errs = [f"meta {e.message}" for e in meta_v.iter_errors(meta)]
        errs += [f"jsonl line {i + 1}: {e.message}" for i, l in enumerate(lines) for e in st_v.iter_errors(l)]
        if errs:
            raise Fail("invalid_release", "; ".join(errs[:5]))
    if lines != doc["stations"]:
        raise Fail("invalid_release", ".jsonl lines differ from .json stations")
    if meta != {k: v for k, v in doc.items() if k != "stations"}:
        raise Fail("invalid_release", ".meta.json differs from .json without stations")
    return {"stations": len(doc["stations"]), "format_version": doc["format_version"], "unknown_fields": dropped}


def check_pointers(root, fixture):
    """The pointers and the index agree with each other and name the expected latest release."""
    errs = []
    index = json.loads((root / "OTC_index.json").read_bytes())
    order = [e["datestamp"] for e in index["releases"]]
    if order != fixture["releases"]:
        errs.append(f"index order {order} != {fixture['releases']}")
    if sorted(order, key=datestamp_key, reverse=True) != order:
        errs.append("index not newest first")
    latest = json.loads((root / "OTC_latest.json").read_bytes())
    if latest != index["releases"][0] or latest["datestamp"] != fixture["latest"]:
        errs.append("OTC_latest.json is not the newest index entry")
    major = int(latest["format_version"].split(".")[0])
    per_major = root / f"OTC_latest-f{major}.json"
    if not per_major.exists() or json.loads(per_major.read_bytes()) != latest:
        errs.append(f"{per_major.name} missing or differs from OTC_latest.json")
    return errs


def compare_trees(fresh, committed):
    errs = []
    a = {p.relative_to(fresh).as_posix() for p in fresh.rglob("*") if p.is_file()}
    b = {p.relative_to(committed).as_posix() for p in committed.rglob("*") if p.is_file()
         and p.relative_to(committed).parts[0] in GENERATED}
    for missing in sorted(a - b):
        errs.append(f"not committed: {missing}")
    for extra in sorted(b - a):
        errs.append(f"not generated: {extra}")
    for rel in sorted(a & b):
        if (fresh / rel).read_bytes() != (committed / rel).read_bytes():
            errs.append(f"differs from a fresh generation: {rel}")
    return errs


def check(schema_path):
    schema = load_schema(schema_path)
    Draft202012Validator.check_schema(schema)
    problems = []
    if not (FIXTURES / "fixtures.json").exists():
        print(f"FAIL  no fixtures at {FIXTURES}")
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        build(Path(tmp), FIXTURES)
        diffs = compare_trees(Path(tmp), FIXTURES)
    print(f"{'PASS' if not diffs else 'FAIL'}  regeneration is byte-identical")
    problems += diffs
    manifest = json.loads((FIXTURES / "fixtures.json").read_bytes())
    for fx in manifest["fixtures"]:
        root = FIXTURES / fx["root"]
        errs = check_pointers(root, fx)
        for d in fx["releases"]:
            try:
                got = open_release(root, d, schema)
                outcome, detail = "load", f"{got['stations']} stations, format {got['format_version']}"
                if got["unknown_fields"]:
                    detail += f", unknown fields kept in raw: {', '.join(got['unknown_fields'])}"
            except Fail as e:
                outcome, detail = {"error": e.code}, str(e)
            ok = outcome == fx["expect"]
            if not ok:
                errs.append(f"{d}: expected {fx['expect']}, got {outcome} ({detail})")
            print(f"{'PASS' if ok else 'FAIL'}  {fx['root']:30} {d:11} expect {json.dumps(fx['expect']):32} got {json.dumps(outcome)}  [{detail}]")
        if fx["expect"] == "load" and fx["root"].startswith("bad/"):
            # The higher-minor release must actually carry unknown fields.
            try:
                if not open_release(root, fx["releases"][0], schema)["unknown_fields"]:
                    errs.append("higher-minor fixture has no unknown fields")
            except Fail:
                pass
        problems += [f"{fx['root']}: {e}" for e in errs]
    if problems:
        print(f"{len(problems)} PROBLEMS")
        for p in problems:
            print("  " + p)
        return 1
    print("OK: all fixture checks pass")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="check the committed fixtures; write nothing")
    parser.add_argument("--schema", help="local copy of otc-0.2.schema.json (default: download the pinned copy)")
    args = parser.parse_args()
    if args.check:
        return check(args.schema)
    with tempfile.TemporaryDirectory() as tmp:
        build(Path(tmp), FIXTURES if FIXTURES.exists() else None)
        for name in GENERATED:
            target = FIXTURES / name
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
        FIXTURES.mkdir(parents=True, exist_ok=True)
        for name in GENERATED:
            src = Path(tmp) / name
            (shutil.copytree if src.is_dir() else shutil.copy2)(src, FIXTURES / name)
    print(f"wrote fixtures under {FIXTURES}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
