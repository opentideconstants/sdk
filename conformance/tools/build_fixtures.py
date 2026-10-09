# /// script
# requires-python = ">=3.12"
# dependencies = ["jsonschema==4.25.1", "rfc3339-validator==0.1.4", "rfc3986-validator==0.1.1"]
# ///
"""Build and check the conformance fixture releases (SDK spec §7.1).

Run: uv run conformance/tools/build_fixtures.py            (writes conformance/fixtures/*, fixtures.json)
     uv run conformance/tools/build_fixtures.py --check    (writes nothing; exit 0 only if all checks pass)

All data is synthetic and CC0-1.0. The station names, ids, providers and numbers
are made up for tests. They are not tidal data.

--check does three things:
  1. Regenerates every fixture in a temporary directory and compares it with
     the committed files, byte for byte.
  2. Good fixtures: each release validates against format 1.0 (the .json
     against the schema, the .meta.json against #/$defs/meta, each .jsonl line
     against #/$defs/station), the cross-references resolve, and the .json,
     .json.gz, .jsonl, .meta.json, .sha256, pointers and index agree. Every
     OTC_index.json and pointer validates against otc-index-1.0. A release in
     a format no 1.0 reader reads (1.99, 2.0) must be valid 1.0 apart from its
     two version fields.
  3. Bad fixtures: a small reference reader (the rules of spec §5.2, §7.3 and
     §7.4) opens each one, and the outcome must be the one in fixtures.json:
     the error code, or "load" for the higher-minor release.

The schemas (format 1.0 and the 1.0 index) come from the site repository, pinned
by commit and SHA-256, and a copy of each is kept in conformance/schemas/ (spec
D25), so --check needs no network. --schema-dir DIR reads other local copies, and
--download-schemas fetches them from the site repository; either way each must have
the pinned SHA-256.
"""
import argparse
import copy
import gzip
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.request
import zlib
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

# The schemas use format date-time and uri. jsonschema checks them only with a format checker and the packages
# above; without them every format passes. So the checker is required, and proven to work before any check.
FORMATS = FormatChecker()


def _require_formats():
    probes = [("not-a-date", "date-time"), ("2099-13-45T00:00:00Z", "date-time"), ("not a uri", "uri")]
    broken = [f"{v!r} as {f}" for v, f in probes if FORMATS.conforms(v, f)]
    if broken:
        raise SystemExit("the jsonschema format checker does not check " + ", ".join(broken) +
                         " (install rfc3339-validator and rfc3986-validator; uv run installs them from the script header)")


def validator(schema):
    return Draft202012Validator(schema, format_checker=FORMATS)

# Format 1.0 and its index schema, from the site repository at the merge that published format 1.0,
# pinned by commit and SHA-256.
SCHEMA_COMMIT = "0833df89c988049abe38d0ddd8b482e4f3d425c0"
_RAW = f"https://raw.githubusercontent.com/opentideconstants/opentideconstants/{SCHEMA_COMMIT}/src/schema"
SCHEMAS = {
    "1.0": (f"{_RAW}/otc-1.0.schema.json", "e27d5f6b5886b4366dbb8b7bb83ebb375cce99bdfe93ae32189cf27cf8463845"),
    "index-1.0": (f"{_RAW}/otc-index-1.0.schema.json", "f657ea90f25ac63199fff693e164ab124027a7632f9e277e607d4dd2b3b2badb"),
}
SCHEMA_FILES = {"1.0": "otc-1.0.schema.json", "index-1.0": "otc-index-1.0.schema.json"}
FORMAT = "1.0"
# The reference reader reads format 1.0 (spec 7.4 SUPPORTED_FORMAT_VERSION): it refuses a release whose
# release.min_reader_version is newer, with reader_too_old, and a release of another major.
READER_FORMAT = (1, 0)
SUPPORTED_MAJORS = [1]
# A format version no SDK reads yet, for the min_reader_version fixtures (spec 7.1 case format/reader-too-old).
TOO_NEW = "1.99"
NEXT_MAJOR = "2.0"

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
VENDORED_SCHEMAS = Path(__file__).resolve().parent.parent / "schemas"   # the pinned schemas, kept in the repository
GENERATED = ["good", "order", "v1", "reader", "major", "values", "values-kept-reason", "values-source-name", "fold", "chain", "nogz",
             "bad", "fixtures.json"]

BASE = "20991231"
SECOND = "20991231.2"
# A counter whose string order differs from its numeric order: .10 is newer than .2 (spec 4.3.1)
COUNTER = "20991231.10"
EARLIER = "20991230"   # a release before the fixtures' releases, for carried_from_release
TABLE = "otc-test-1"
ASTRO = "otc-test-astro-1"   # the astro_tables entry every convention uses (all are f_u_at_prediction)
ASTRO_YEARS = (2098, 2101)
COMMIT = "0123456"
BUILD = {"build_commit": COMMIT}


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


def current_bins(scale):
    """One current bin (a current set has current_bins and no water-level constituents)."""
    return [{"bin": 1, "depth_m": 3.0, "depth_type": "below_surface", "azimuth_deg": 40.0,
             "mean_flood_dir_deg": 40.0, "mean_ebb_dir_deg": 220.0,
             "constituents": [{"name": "M2", "speed_deg_per_hour": 28.9841042, "major_amplitude_ms": round(0.9 * scale, 4),
                               "major_phase_deg": 320.0, "minor_amplitude_ms": 0.05, "minor_phase_deg": 50.0},
                              {"name": "K1", "speed_deg_per_hour": 15.0410686, "major_amplitude_ms": round(0.1 * scale, 4),
                               "major_phase_deg": 25.0, "minor_amplitude_ms": 0.0, "minor_phase_deg": 0.0}]}]


def tb(code, declared, published=None, **extra):
    """A time-base annotation (constant_set.time_base)."""
    t = {"code": code, "reason": f"test: time base {code}", "declared": declared,
         "published": published or declared, "decided_in": BASE}
    t.update(extra)
    return t


VERIFIED = tb("verified", "utc_instant", decided_build_commit=COMMIT,
              evidence=[{"comparator_kind": "official_constants", "comparator_id": "noaa:9900001",
                         "distance_km": 0.0, "lag_min": 0.5, "detail": "M2 phase lag against the official constants"}])
CORRECTED = tb("corrected", "utc_mean_start60", "utc_instant", decided_build_commit=COMMIT,
               correction={"from": "utc_mean_start60", "to": "utc_instant"}, months_dropped=["2097-02", "2097-03"],
               evidence=[{"comparator_kind": "official_predictions", "comparator_id": "kartverket:EXF",
                          "distance_km": 3.2, "lag_min": -30.0}])
UNVERIFIED = tb("unverified", "utc_plus_1", decided_in=SECOND,
                evidence=[{"comparator_kind": "dst_selftest", "comparator_id": "OTC-T-0001/gesla-fit",
                           "distance_km": None, "detail": "no daylight-saving signal"}])
DISPUTED = tb("disputed", "utc_instant",
              evidence=[{"comparator_kind": "model", "comparator_id": "eot20", "lag_min": 12.0}])


def span(good_hours, start="2090-01-01T00:00:00Z", end="2098-12-31T23:00:00Z", good_samples=None):
    s = {"start": start, "end": end, "good_hours": good_hours}
    if good_samples is not None:
        s["good_samples"] = good_samples
    return s


def cset(station_id, suffix, source, source_type, convention_id, licence_id, constituents, *,
         qc_status="ok", quantity="water_level", provenance=None, **extra):
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
        "provenance": provenance if provenance is not None else {"adapter_version": "0.0.0-test", "build": dict(BUILD)},
    }
    s.update(extra)
    return s


def gauge_set(station_id, suffix, constituents, *, time_base=VERIFIED, good_hours=70000.0, **kw):
    """A set fitted from a gauge record: it carries a time base and its hours of good data."""
    kw.setdefault("record_span", span(good_hours))
    flags = list(kw.pop("qc_flags", []))
    if time_base["code"] in ("unverified", "disputed"):
        flags.insert(0, {"flag": "time_base", "reason": f"the time base is {time_base['code']}"})
        kw.setdefault("qc_status", "flagged")
    if flags:
        kw["qc_flags"] = flags
    return cset(station_id, suffix, kw.pop("source", "gesla-fit"), "gauge", "otc-greenwich-v1",
                kw.pop("licence_id", "gesla-derived"), constituents, time_base=time_base, **kw)


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


def no_recommended(st):
    st["recommended_set_id"] = None
    return st


def gauge_station(station_id, name, country, lat, lon, timezone, scale, time_base=VERIFIED, **kw):
    return active(station_id, name, country, lat, lon, timezone,
                  [gauge_set(station_id, "gesla-fit", simple_constituents(scale), time_base=time_base)], **kw)


def model_station(station_id, name, country, lat, lon, timezone, scale):
    return active(station_id, name, country, lat, lon, timezone,
                  [cset(station_id, "eot20", "eot20", "model", "otc-greenwich-v1", "eot20",
                        simple_constituents(scale, phase_shift=lon))])


def tombstone(station_id, name, removed_in, reason, into, detail=None):
    t = {"station_id": station_id, "status": "removed", "name": name, "removed_in": removed_in,
         "removed_reason": reason, "merged_into": into}
    if detail is not None:
        t["detail"] = detail
    return t


def astro_tables(table):
    """One synthetic astro table (format 1.0 astro_tables): a row per constituent of the table, the same speeds,
    made-up V0+u and f per year. Its tables_sha256 is the conventions' (the release build checks they agree)."""
    first, last = ASTRO_YEARS
    rows = {}
    for i, c in enumerate(table):
        rows[c["name"]] = {"speed_deg_per_hour": c["speed_deg_per_hour"],
                           "v0u_deg": [round((37.5 * i + 11.25 * y) % 360, 2) for y in range(last - first + 1)],
                           "f": [round(1.0 + 0.01 * ((i + y) % 3 - 1), 4) for y in range(last - first + 1)]}
    return [{"astro_table_id": ASTRO, "v0_model": "schureman_tcd", "tables_sha256": hashlib.sha256(TABLE.encode()).hexdigest(),
             "generator": "synthetic test values (not congen output)", "first_year": first, "last_year": last,
             "constituents": rows}]


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
            "astro_table_id": ASTRO,
            "canary": {"status": "not_applicable"},
        },
        {
            "convention_id": "kartverket-utc1-v1",
            "phase_reference": "local",
            "utc_offset_hours": 1,
            "v0_model": "schureman_tcd",
            "nodal_handling": "f_u_at_prediction",
            "constituent_table_version": TABLE,
            "astro_table_id": ASTRO,
            "canary": {"status": "pass", "gauges": 3, "median_amp_diff_m": 0.004, "median_phase_diff_deg": 0.8},
        },
        {
            "convention_id": "noaa-greenwich-v1",
            "phase_reference": "greenwich_utc",
            "v0_model": "schureman_tcd",
            "nodal_handling": "f_u_at_prediction",
            "constituent_table_version": TABLE,
            "astro_table_id": ASTRO,
        },
    ]
    # Not in licence_id order: release.licences keeps file order, the attribution orders by licence_id (spec 4.6).
    licences = [
        {"licence_id": "noaa", "spdx": "LicenseRef-PublicDomain-USGov", "provider": "Example Ocean Service",
         "attribution": "Synthetic test data in the style of a public-domain US agency.", "commercial_use": True},
        {"licence_id": "kartverket", "spdx": "CC-BY-4.0", "provider": "Example Mapping Authority",
         "attribution": "Synthetic test data, Example Mapping Authority.", "commercial_use": True},
        {"licence_id": "eot20", "spdx": "CC-BY-4.0", "provider": "Example Tide Model Group",
         "attribution": "Example tide model, interpolated by OpenTideConstants tests.", "commercial_use": True},
        {"licence_id": "gesla-derived", "spdx": "CC-BY-4.0", "provider": "Example Gauge Agency via GESLA",
         "citation": "Example Gauge Agency (2099). Example sea level records. Test citation.",
         "attribution": "Contains synthetic test data in the style of GESLA-4.",
         "url": "https://example.org/gesla-test", "commercial_use": True},
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
        provenance={"adapter_version": "0.0.0-test",
                    "input_sha256": [hashlib.sha256(b"noaa-input").hexdigest()],
                    "selection_reason": "official constants from the operating agency",
                    "decision": {"tier": "rule", "outcome": "accept", "rule": "D1", "reason": "official"},
                    "build": {"build_commit": "89abcdef", "built_at": "2099-12-31T06:00:00Z",
                              "fetched_at": "2099-12-30T18:00:00Z", "run_id": "otc-test-run-1",
                              "tool_versions": {"python": "3.12.7", "utide": "0.3.0"}}},
    )
    gesla_set = gauge_set(
        s1, "gesla-fit", full_constituents(1.01), time_base=UNVERIFIED,
        record_span=span(245000.0, start="2070-01-01T00:00:00Z", end="2098-01-01T00:00:00Z"),
        dropped_constituents=[{"name": "SA", "dropped_reason": "rayleigh", "not_separable_from": "M2"},
                              {"name": "M4", "dropped_reason": "noise", "detail": "snr 1.2 below 2.0"}],
        provenance={"adapter_version": "0.0.0-test", "build": dict(BUILD),
                    "tcd_sha256": hashlib.sha256(b"tcd-input").hexdigest(),
                    "selection_reason": "longest clean record",
                    "decision": {"tier": "rule", "outcome": "accept", "rule": "D2", "reason": "within tolerance"}},
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
        # a carried-over set (recommended) and a no_constants set
        active("OTC-T-0002", "South San Francisco", "USA", 37.665, -122.38, "America/Los_Angeles",
               [gauge_set("OTC-T-0002", "fallback", simple_constituents(0.9), source="ticon-fallback",
                          qc_status="flagged",
                          qc_flags=[{"flag": "carried_over", "reason": "the source failed a check in this build"}],
                          provenance={"adapter_version": "0.0.0-test", "build": dict(BUILD), "carried_from_release": EARLIER,
                                      "decision": {"tier": "fallback", "outcome": "fallback", "reason": "source check failed"}}),
                gauge_set("OTC-T-0002", "gesla-fit", [], qc_status="no_constants", no_constants_reason="fit_unusable",
                          good_hours=9000.0,
                          record_issues=[{"issue": "datum_step", "start": "2095-06-01T00:00:00Z", "reason": "a 0.4 m datum step",
                                          "values": {"step_m": 0.4}}],
                          qc_flags=[{"flag": "broken_record", "reason": "no segment gives a usable fit", "values": {"step_m": 0.4}}])],
               recommended="OTC-T-0002/fallback", aliases={"noaa": "9900002"}),
        active("OTC-T-0003", "Alameda", "USA", 37.772, -122.3, "America/Los_Angeles", [], type_="subordinate",
               aliases={"noaa": "9900003"},
               subordinate_offsets={"reference_station_id": s1, "time_offset_high_min": 12, "time_offset_low_min": 20,
                                    "height_offset_high": 1.05, "height_offset_low": 0.98,
                                    "height_adjusted_type": "R", "licence_id": "kartverket"}),
        active("OTC-T-0004", "Oakland Pier", "USA", 37.795, -122.33, "America/Los_Angeles",
               # its own set's licence (eot20) is not its reference station's (noaa): the attribution needs both
               [cset("OTC-T-0004", "noaa", "noaa", "official", "noaa-greenwich-v1", "eot20", simple_constituents(1.02))],
               type_="subordinate", recommended="OTC-T-0004/noaa", aliases={"noaa": "9900004"},
               subordinate_offsets={"reference_station_id": s1, "time_offset_high_min": -5, "time_offset_low_min": 4,
                                    "height_offset_high": 0.12, "height_offset_low": -0.05,
                                    "height_adjusted_type": "A"}),
        tombstone("OTC-T-0005", "Old Pier", BASE, "duplicate", s1, "Duplicate of OTC-T-0001 (test tombstone)."),
        active("OTC-T-0006", "Tromsø", "NOR", 69.6468, 18.9543, "Europe/Oslo",
               [cset("OTC-T-0006", "kartverket", "kartverket", "official", "kartverket-utc1-v1", "kartverket",
                     simple_constituents(1.1))], aliases={"kartverket": "TOS"}),
        model_station("OTC-T-0007", "Antimeridian East", "FJI", 0.0, 179.9, "Pacific/Fiji", 0.6),
        model_station("OTC-T-0008", "Antimeridian West", "KIR", 0.0, -179.9, "Pacific/Tarawa", 0.6),
        model_station("OTC-T-0009", "Polar Station", "SJM", 89.9, 0.0, "Arctic/Longyearbyen", 0.2),
        gauge_station("OTC-T-0010", "Equator Station", "GAB", 0.0, 9.0, "Africa/Libreville", 0.7),
        gauge_station("OTC-T-0011", "Ålesund", "NOR", 62.4722, 6.1517, "Europe/Oslo", 0.8, time_base=CORRECTED,
                      aliases={"gesla": ["test-gesla-0011"]}),
        gauge_station("OTC-T-0012", "Łeba", "POL", 54.76, 17.556, "Europe/Warsaw", 0.05, time_base=DISPUTED),
        gauge_station("OTC-T-0013", "Straße", "DEU", 54.0, 10.0, "Europe/Berlin", 0.3),
        gauge_station("OTC-T-0014", "Harbour", "GBR", 50.8, -1.1, "Europe/London", 1.5),
        gauge_station("OTC-T-0015", "Harbour", "IRL", 53.35, -6.2, "Europe/Dublin", 1.4),
        gauge_station("OTC-T-0016", "Harbour Point", "GBR", 50.7, -1.3, "Europe/London", 1.5),
        gauge_station("OTC-T-0017", "North Harbour", "GBR", 55.0, -1.4, "Europe/London", 1.6),
        gauge_station("OTC-T-0018", "Seaharbour", "GBR", 51.0, 1.3, "Europe/London", 1.7),
        active("OTC-T-0019", "Test Current Pass", "USA", 47.9, -122.6, "America/Los_Angeles",
               [cset("OTC-T-0019", "noaa", "noaa", "official", "noaa-greenwich-v1", "noaa", [],
                     quantity="current", current_bins=current_bins(1.3))], aliases={"noaa": "TEST1901"}),
        active("OTC-T-0020", "Minimal Station", "USA", 21.3, -157.9, "Pacific/Honolulu",
               [cset("OTC-T-0020", "noaa", "noaa", "official", "noaa-greenwich-v1", "noaa",
                     simple_constituents(0.25), provenance={"build": dict(BUILD)})]),
    ]
    doc = {
        "format_version": FORMAT,
        "release": {
            "datestamp": datestamp,
            "created": "2099-12-31T00:00:00Z",
            "min_reader_version": FORMAT,
            "fit_min_good_hours": 360,
            "concept_doi": None,
            "source_versions": {"eot20": "20991231", "gesla": "4.1", "kartverket": "20991231", "noaa": "20991231"},
            "build_commit": "0123456789abcdef0123456789abcdef01234567",
            "changelog_url": f"https://opentideconstants.org/changelog/#{datestamp}",
        },
        "conventions": conventions,
        "licences": licences,
        "constituents": table,
        "astro_tables": astro_tables(table),
        "stations": stations,
    }
    if datestamp == BASE:
        doc["stations"].append(gauge_station("OTC-T-0021", "Closing Pier", "GBR", 52.0, 1.7, "Europe/London", 1.2))
    else:
        rel = doc["release"]
        rel["created"] = "2099-12-31T12:00:00Z"
        rel["concept_doi"] = "10.5072/zenodo.1"
        del rel["build_commit"]
        del rel["changelog_url"]
        # no detail: Tombstone.detail is null
        doc["stations"].append(tombstone("OTC-T-0021", "Closing Pier", SECOND, "merged", "OTC-T-0022"))
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


_GZ_SEEN = {}  # sha256 of content -> committed gzip bytes already reused in this run


def gz(data, reuse):
    """gzip with no name and mtime 0. Reuse committed bytes when they hold the same content,
    so a different zlib build does not change the committed fixtures. A bad root's committed
    .json.gz may not hold the honest content (truncated, or one byte changed), so content
    already reused from another root (good/ is written first) is reused here too."""
    if reuse is not None and reuse.exists():
        old = reuse.read_bytes()
        try:
            if gzip.decompress(old) == data:
                _GZ_SEEN.setdefault(sha(data), old)
                return old
        except (OSError, EOFError, zlib.error) as e:
            # a bad root's committed .json.gz is not honest gzip on purpose (truncated, a byte changed); anywhere else
            # an unreadable committed file is worth a line: it is regenerated, and --check then reports the difference
            if "bad" not in reuse.parts:
                print(f"note: committed {reuse} is not readable gzip ({type(e).__name__}: {e}); compressing afresh",
                      file=sys.stderr)
    seen = _GZ_SEEN.get(sha(data))
    if seen is not None:
        return seen
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


def content_digest(datestamp):
    """content_sha256 of an index entry. The SDKs only pass it through, so a stand-in digest is enough."""
    return sha(f"content:{datestamp}".encode())


def pointer_entry(doc, files, sums, version_dois=None, material=()):
    """One entry of the pointers and the index (otc-index-1.0 release_info)."""
    d = doc["release"]["datestamp"]
    entries = [{"name": n, "url": n, "size": len(b), "sha256": sha(b)} for n, b in sorted(files.items())]
    entries.append({"name": f"OTC_{d}.sha256", "url": f"OTC_{d}.sha256", "size": len(sums), "sha256": sha(sums)})
    entries.sort(key=lambda e: e["name"])
    rel = doc["release"]
    e = {"datestamp": d, "format_version": doc["format_version"], "min_reader_version": rel["min_reader_version"],
         "created": rel["created"], "concept_doi": rel.get("concept_doi"),
         "zenodo_version_doi": (version_dois or {}).get(d), "content_sha256": content_digest(d), "files": entries}
    if d in material:
        e["zenodo_material"] = True  # pipeline only; the SDKs ignore it (spec 5.1)
    return e


def datestamp_key(d):
    date, _, counter = d.partition(".")
    return (date, int(counter) if counter else 1)


def write_root(root, docs, *, reuse_root=None, tamper=None, version_dois=None, material=()):
    """Write the releases in docs, their .sha256 files, the pointers and the index into root.
    tamper(name, files, sums, entry) may change what is written after the honest values are computed."""
    root.mkdir(parents=True, exist_ok=True)
    entries = []
    for doc in docs:
        files = release_files(doc, reuse_root)
        sums = sha256_list(files)
        entry = pointer_entry(doc, files, sums, version_dois, material)
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
    """Change one byte in every station data file, at the same size; keep the honest SHA-256 list and pointer. So
    the hash differs and the size does not (a size check alone cannot catch it). The .json.gz gets one byte of its
    compressed body changed: it is not valid gzip any more, but a reader hashes it before it decompresses it."""
    out = dict(files)
    for name in list(out):
        if name.endswith(".json") and not name.endswith(".meta.json"):
            out[name] = out[name].replace(b"San Francisco", b"San Franciscx", 1)
        elif name.endswith(".jsonl"):
            out[name] = out[name].replace(b"San Francisco", b"San Franciscx", 1)
        elif name.endswith(".json.gz"):
            data = bytearray(out[name])
            data[len(data) // 2] ^= 0x01
            out[name] = bytes(data)
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


def versioned(doc, fmt, min_reader=None):
    """A copy of a release in another format version (with a field that format adds)."""
    doc = copy.deepcopy(doc)
    doc["format_version"] = fmt
    doc["release"]["min_reader_version"] = min_reader or fmt
    doc["future_top_level"] = {"note": f"added by format {fmt} (test)"}
    return doc


def major_doc():
    return versioned(release_doc(BASE), NEXT_MAJOR)


def minor_doc():
    doc = release_doc(BASE)
    doc["format_version"] = "1.1"   # min_reader_version stays 1.0: a 1.0 reader can read it
    doc["future_top_level"] = {"note": "added by format 1.1 (test)"}
    doc["release"]["future_release_field"] = "1.1 release field"
    doc["conventions"][0]["future_convention_field"] = 1
    doc["licences"][0]["future_licence_field"] = True
    st = next(s for s in doc["stations"] if s["station_id"] == "OTC-T-0001")
    st["future_station_field"] = {"depth_m": 12.5}
    st["aliases"]["future_system"] = "FS-0001"
    st["constant_sets"][0]["future_set_field"] = "1.1 set field"
    st["constant_sets"][0]["constituents"][0]["future_constituent_field"] = 0.5
    # a qc_status value format 1.0 does not have (a 0.x leftover): a 1.0 reader reads it as "other" (spec 7.3, 7.4)
    eq = next(s for s in doc["stations"] if s["station_id"] == "OTC-T-0010")
    eq["constant_sets"].append(gauge_set("OTC-T-0010", "legacy", simple_constituents(0.65), source="legacy-fit",
                                         qc_status="excluded", record_issues=[{"issue": "spikes", "reason": "test: spikes"}],
                                         qc_flags=[{"flag": "broken_record", "reason": "test: a 0.x excluded set"}]))
    return doc


def unresolved_doc():
    doc = release_doc(BASE)
    st = next(s for s in doc["stations"] if s["station_id"] == "OTC-T-0010")
    st["constant_sets"][0]["convention_id"] = "no-such-convention"
    return doc


def rehash(files, sums, entry, new_sums=None):
    """The .sha256 list and the pointer entry made honest again for changed files (so a defect is the only one)."""
    sums = new_sums if new_sums is not None else sha256_list(files)
    entry = copy.deepcopy(entry)
    for f in entry["files"]:
        data = sums if f["name"].endswith(".sha256") else files.get(f["name"])
        if data is not None:
            f["size"], f["sha256"] = len(data), sha(data)
    return files, sums, entry


def honest(change):
    """A tamper that changes the files with change(files) and keeps every digest honest."""
    def t(files, sums, entry, reuse):
        files = dict(files)
        change(files)
        return rehash(files, sums, entry)
    return t


def gz_differs(files, sums, entry, reuse):
    """The .json.gz holds other data than the .json. It goes through gz(), like every other .json.gz, so the
    committed bytes are reused when they hold the same tampered data and a different zlib build changes nothing."""
    files = dict(files)
    name = next(n for n in files if n.endswith(".json.gz"))
    files[name] = gz(files[name[:-3]].replace(b"San Francisco", b"San Franciscx", 1), reuse / name if reuse else None)
    return rehash(files, sums, entry)


def _jsonl_differs(files):
    name = next(n for n in files if n.endswith(".jsonl"))
    files[name] = files[name].replace(b"San Francisco", b"San Franciscx", 1)


def _meta_differs(files):
    name = next(n for n in files if n.endswith(".meta.json"))
    files[name] = files[name].replace(b"Example Mapping Authority.", b"Example Mapping Authority!", 1)


def size_mismatch(files, sums, entry, reuse):
    entry = copy.deepcopy(entry)
    next(f for f in entry["files"] if f["name"].endswith(".jsonl"))["size"] += 1
    return files, sums, entry


def sums_extra_file(files, sums, entry, reuse):
    return rehash(files, sums, entry, sums + f"{sha(b'extra')}  OTC_{BASE}.csv\n".encode())


def sha256_file_differs(files, sums, entry, reuse):
    entry = copy.deepcopy(entry)
    next(f for f in entry["files"] if f["name"].endswith(".sha256"))["sha256"] = sha(b"not the .sha256 file")
    return files, sums, entry


def sums_disagree(files, sums, entry, reuse):
    name = next(n for n in files if n.endswith(".jsonl")).encode()
    lines = [(sha(b"wrong digest").encode() + b"  " + name) if l.endswith(b"  " + name) else l for l in sums.splitlines()]
    return rehash(files, sums, entry, b"\n".join(lines) + b"\n")


def index_content_digest_bad(files, sums, entry, reuse):
    entry = copy.deepcopy(entry)
    entry["content_sha256"] = "not a digest"
    return files, sums, entry


def changed_doc(change):
    def make():
        doc = release_doc(BASE)
        change(doc)
        doc["stations"].sort(key=lambda s: str(s["station_id"]))
        return [doc]
    return make


def _station(doc, sid):
    return next(s for s in doc["stations"] if s["station_id"] == sid)


def _licence(doc, lid):
    return next(x for x in doc["licences"] if x["licence_id"] == lid)


def index_honest(files, sums, entry, reuse):
    """Keep the pointer and index entry valid (1.0, a time): the defect is in the release file only."""
    entry = copy.deepcopy(entry)
    entry.update(format_version=FORMAT, min_reader_version=FORMAT, created="2099-12-31T00:00:00Z")
    return files, sums, entry


def _duplicate_set(doc):
    st = _station(doc, "OTC-T-0001")
    st["constant_sets"].append(copy.deepcopy(st["constant_sets"][0]))


def _duplicate_station(doc):
    st = copy.deepcopy(_station(doc, "OTC-T-0020"))
    st["constant_sets"][0]["set_id"] = "OTC-T-0020/noaa-copy"
    st["recommended_set_id"] = "OTC-T-0020/noaa-copy"
    doc["stations"].append(st)


def _jsonl_one_byte(files, sums, entry, reuse):
    files = dict(files)
    name = next(n for n in files if n.endswith(".jsonl"))
    files[name] = files[name].replace(b"San Francisco", b"San Franciscx", 1)
    return files, sums, entry


def _too_new_broken():
    doc = small_doc(BASE)
    doc["stations"][0]["constant_sets"][0]["licence_id"] = "no-such-licence"
    return [versioned(doc, TOO_NEW)]


BAD = [
    ("wrong-sha256", "checksum_mismatch", "every station data file differs from its SHA-256 in OTC_20991231.sha256 and the pointer (same size, one byte changed)",
     lambda: [release_doc(BASE)], corrupt_same_size),
    ("truncated", "checksum_mismatch", "the .json, .json.gz and .jsonl files are cut to half their size; the pointer and .sha256 give the full size and hash",
     lambda: [release_doc(BASE)], truncate),
    ("pointer-mismatch", "checksum_mismatch", "the files match OTC_20991231.sha256, but the pointer and index give other SHA-256 values",
     lambda: [release_doc(BASE)], pointer_disagrees),
    ("format-major", "unsupported_format", f"format_version {NEXT_MAJOR}, one major above the supported major 1",
     lambda: [major_doc()], None),
    ("format-minor", "load", "format_version 1.1 with unknown fields (top level, release, convention, licence, station, alias system, set, constituent); it must load and keep them in raw",
     lambda: [minor_doc()], None),
    ("unresolved-convention", "invalid_release", "OTC-T-0010's set has convention_id no-such-convention",
     lambda: [unresolved_doc()], None),
    ("min-reader", "reader_too_old", f"the only release has min_reader_version {TOO_NEW}, newer than any reader",
     lambda: [versioned(small_doc(BASE), TOO_NEW)], None),
    ("no-build", "load", "OTC-T-0004's set has no provenance.build (malformed: format 1.0 requires it); it must load, with build null",
     lambda: [no_build_doc()], None),
    # Cross-SDK rules of review round 1 (PK03, PK06, PK07): each SDK must refuse these with invalid_release.
    ("min-reader-malformed", "invalid_release", "release.min_reader_version is \"2\" (not MAJOR.MINOR; D9)",
     changed_doc(lambda d: d["release"].update(min_reader_version="2")), index_honest),
    ("format-version-malformed", "invalid_release", "format_version is \"1.x\" (not MAJOR.MINOR; D9)",
     changed_doc(lambda d: d.update(format_version="1.x")), index_honest),
    ("active-and-removed-same-id", "invalid_release", "OTC-T-0020 is both an active station and a tombstone (D5)",
     changed_doc(lambda d: d["stations"].append(tombstone("OTC-T-0020", "Minimal Station", BASE, "duplicate", "OTC-T-0001"))), None),
    ("duplicate-set-id", "invalid_release", "OTC-T-0001 has two sets with the set_id OTC-T-0001/noaa (D5)",
     changed_doc(_duplicate_set), None),
    ("unresolved-reference-station", "invalid_release", "OTC-T-0003's subordinate_offsets.reference_station_id is OTC-T-9999",
     changed_doc(lambda d: _station(d, "OTC-T-0003")["subordinate_offsets"].update(reference_station_id="OTC-T-9999")), None),
    ("unresolved-offsets-licence", "invalid_release", "OTC-T-0003's subordinate_offsets.licence_id is no-such-licence",
     changed_doc(lambda d: _station(d, "OTC-T-0003")["subordinate_offsets"].update(licence_id="no-such-licence")), None),
    ("duplicate-convention-id", "invalid_release", "two conventions with the convention_id noaa-greenwich-v1 (D5)",
     changed_doc(lambda d: d["conventions"].append(copy.deepcopy(d["conventions"][2]))), None),
    ("station-id-not-string", "invalid_release", "OTC-T-0020's station_id is the number 20 (malformed: schema-invalid)",
     changed_doc(lambda d: _station(d, "OTC-T-0020").update(station_id=20)), None),
    ("lat-string", "invalid_release", "OTC-T-0010's lat is the string \"0.0\" (malformed)",
     changed_doc(lambda d: _station(d, "OTC-T-0010").update(lat="0.0")), None),
    ("aliases-not-object", "invalid_release", "OTC-T-0006's aliases is a list (malformed)",
     changed_doc(lambda d: _station(d, "OTC-T-0006").update(aliases=["TOS"])), None),
    ("qc-flags-not-array", "invalid_release", "OTC-T-0002's first set has qc_flags as an object (malformed)",
     changed_doc(lambda d: _station(d, "OTC-T-0002")["constant_sets"][0].update(qc_flags={"flag": "carried_over"})), None),
    ("convention-without-id", "invalid_release", "the first convention has no convention_id (malformed; the .meta.json path reads it too)",
     changed_doc(lambda d: d["conventions"][1].pop("convention_id")), None),
    ("created-not-string", "invalid_release", "release.created is the number 2099 (malformed)",
     changed_doc(lambda d: d["release"].update(created=2099)), index_honest),
    ("source-versions-not-object", "invalid_release", "release.source_versions is a list (malformed)",
     changed_doc(lambda d: d["release"].update(source_versions=["gesla 4.1"])), None),
    # Reference-reader coverage (review round 1, B2-T1): each rule of the reader decides one of these outcomes, so
    # turning a rule off fails --check. The first three are reader-only (D37: SDKs do not cross-check the files of a
    # release; each file is checked against OTC_{D}.sha256).
    ("gz-differs", "checksum_mismatch", "honest digests, but the .json.gz decompresses to other data than the .json (reader only, D37)",
     lambda: [release_doc(BASE)], gz_differs),
    ("jsonl-differs", "invalid_release", "honest digests, but a .jsonl line differs from the .json station (reader only, D37)",
     lambda: [release_doc(BASE)], honest(_jsonl_differs)),
    ("meta-differs", "invalid_release", "honest digests, but the .meta.json differs from the .json without stations (reader only, D37)",
     lambda: [release_doc(BASE)], honest(_meta_differs)),
    ("size-mismatch", "checksum_mismatch", "the pointer and index give the .jsonl one byte more than its size; every SHA-256 is right",
     lambda: [release_doc(BASE)], size_mismatch),
    ("sums-extra-file", "checksum_mismatch", "OTC_20991231.sha256 lists a file the pointer does not list (spec 5.2 step 4.1)",
     lambda: [release_doc(BASE)], sums_extra_file),
    ("sha256-file-differs", "checksum_mismatch", "the pointer's SHA-256 of OTC_20991231.sha256 is not the file's (spec 5.2 step 4.1)",
     lambda: [release_doc(BASE)], sha256_file_differs),
    ("sums-disagree", "checksum_mismatch", "OTC_20991231.sha256 gives another SHA-256 for the .jsonl than the pointer; the file matches the pointer (spec 5.2 step 4.1)",
     lambda: [release_doc(BASE)], sums_disagree),
    ("unresolved-licence", "invalid_release", "OTC-T-0010's set has licence_id no-such-licence",
     changed_doc(lambda d: _station(d, "OTC-T-0010")["constant_sets"][0].update(licence_id="no-such-licence")), None),
    ("unresolved-recommended", "invalid_release", "OTC-T-0010's recommended_set_id names no set of the station",
     changed_doc(lambda d: _station(d, "OTC-T-0010").update(recommended_set_id="OTC-T-0010/no-such-set")), None),
    ("duplicate-alias", "invalid_release", "OTC-T-0002 has the noaa alias 9900001 of OTC-T-0001 (spec 4.4: alias ids are unique in a system)",
     changed_doc(lambda d: _station(d, "OTC-T-0002")["aliases"].update(noaa="9900001")), None),
    ("duplicate-station-id", "invalid_release", "OTC-T-0020 appears twice (the second line's set has another set_id, so the station id is the only duplicate)",
     changed_doc(_duplicate_station), None),
    ("lat-nan", "invalid_release", "OTC-T-0010's lat is NaN, which is not JSON (RFC 8259) though Python's json module writes and reads it",
     changed_doc(lambda d: _station(d, "OTC-T-0010").update(lat=float("nan"))), None),
    ("jsonl-wrong-sha256", "checksum_mismatch", "only the .jsonl has one byte changed (same size); the .json and .json.gz are honest, so only the hash check catches it",
     lambda: [release_doc(BASE)], _jsonl_one_byte),
    ("index-invalid", "load", "the release is good, but its OTC_index.json entry has a content_sha256 that is not a digest (the index fails otc-index-1.0)",
     lambda: [release_doc(BASE)], index_content_digest_bad, {"index_invalid": True}),
    # CR2 DR2: a licence attribution that is not a string, or a provider that is neither a string nor null
    ("licence-attribution-null", "invalid_release", "the eot20 licence's attribution is null (CR2 DR2)",
     changed_doc(lambda d: _licence(d, "eot20").update(attribution=None)), None),
    ("licence-attribution-not-string", "invalid_release", "the eot20 licence's attribution is the number 5 (CR2 DR2)",
     changed_doc(lambda d: _licence(d, "eot20").update(attribution=5)), None),
    ("licence-provider-not-string", "invalid_release", "the eot20 licence's provider is the number 7 (CR2 DR2)",
     changed_doc(lambda d: _licence(d, "eot20").update(provider=7)), None),
    ("too-new-broken", "reader_too_old", f"min_reader_version {TOO_NEW}, and its data is not valid 1.0 (an unresolved licence): the version gate comes first",
     _too_new_broken, None, {"valid_as_1_0": False}),
]


def no_build_doc():
    doc = release_doc(BASE)
    st = next(s for s in doc["stations"] if s["station_id"] == "OTC-T-0004")
    del st["constant_sets"][0]["provenance"]["build"]
    return doc


def restore_station_build(st):
    """One station (a .jsonl line) with every missing provenance.build put back."""
    st = copy.deepcopy(st)
    for cs in st.get("constant_sets", []):
        if isinstance(cs.get("provenance"), dict):   # the same sets the detection picks
            cs["provenance"].setdefault("build", dict(BUILD))
    return st


def restore_build(doc):
    """The repair that makes bad/no-build valid again, so a missing build is its only defect. A .meta.json
    (no stations) comes back unchanged."""
    doc = copy.deepcopy(doc)
    if "stations" in doc:
        doc["stations"] = [restore_station_build(s) for s in doc["stations"]]
    return doc


# --------------------------------------------------------------------------- the format 1.0 annotations (v1/), min_reader_version and majors

V1 = "20991231.3"           # v1/: the release with the annotation stations
READER_OLD = "20991231.2"   # reader/: a 1.0 release
READER_OK = "20991231.3"    # reader/: the newest release a 1.0 reader can read
READER_NEW = "20991231.4"   # reader/: min_reader_version 1.99, the newest release
MAJOR_OK = "20991231.2"     # major/: the newest release of major 1
MAJOR_NEW = "20991231.3"    # major/: format 2.0, the newest release


def v1_stations(datestamp, full=True):
    """The annotation stations. full=False keeps only OTC-T-0101."""
    official = lambda sid, consts, **kw: cset(sid, "noaa", "noaa", "official", "noaa-greenwich-v1", "noaa", consts, **kw)
    s1 = "OTC-T-0101"
    st = [
        # ok sets: provenance.build in full (official) and with only build_commit (gauge, a verified time base)
        active(s1, "Six Ok Harbour", "GBR", 50.9, -1.4, "Europe/London",
               [official(s1, simple_constituents(1.2),
                         provenance={"adapter_version": "0.0.0-test",
                                     "input_sha256": [hashlib.sha256(b"noaa-v1-input").hexdigest()],
                                     "selection_reason": "official constants from the operating agency",
                                     "decision": {"tier": "rule", "outcome": "accept", "rule": "D1", "reason": "official"},
                                     "build": {"build_commit": "89abcdef", "built_at": "2099-12-31T06:00:00Z",
                                               "fetched_at": "2099-12-30T18:00:00Z", "run_id": "otc-test-run-6",
                                               "tool_versions": {"python": "3.12.7", "utide": "0.3.0"}}}),
                gauge_set(s1, "gesla-fit", simple_constituents(1.19))],
               recommended=f"{s1}/noaa", aliases={"noaa": "9900101"}),
    ]
    if full:
        st += [
            # an ok set with a corrected time base, and a flagged set with an unverified one
            active("OTC-T-0102", "Six Flagged Point", "GBR", 50.7, -1.0, "Europe/London",
                   [gauge_set("OTC-T-0102", "gesla-corrected", simple_constituents(1.1), time_base=CORRECTED, good_hours=52000.5),
                    gauge_set("OTC-T-0102", "gesla-fit", simple_constituents(1.05), time_base=UNVERIFIED, good_hours=43800.0)],
                   recommended="OTC-T-0102/gesla-corrected"),
            # an ok set plus a no_constants set (too short) of another source
            active("OTC-T-0103", "Six Mixed Quay", "GBR", 51.2, 1.4, "Europe/London",
                   [official("OTC-T-0103", simple_constituents(1.4)),
                    gauge_set("OTC-T-0103", "gesla-fit", [], qc_status="no_constants", no_constants_reason="too_short",
                              record_span=span(200.0, start="2098-12-01T00:00:00Z"),
                              qc_flags=[{"flag": "short_record", "reason": "200 hours of good data, below 360"}])],
                   recommended="OTC-T-0103/noaa"),
            # every set is no_constants: no recommended set
            no_recommended(active("OTC-T-0104", "Six Empty Reef", "GBR", 52.5, 1.8, "Europe/London",
                   [gauge_set("OTC-T-0104", "gesla-fit", [], qc_status="no_constants", no_constants_reason="fit_unusable",
                              good_hours=9000.0,
                              record_issues=[{"issue": "flatline", "start": "2095-01-01T00:00:00Z", "end": "2098-12-31T23:00:00Z",
                                              "reason": "the sensor reads one value"}],
                              qc_flags=[{"flag": "broken_record", "reason": "no segment gives a usable fit"}])])),
            # a carried-over set (flagged carried_over, gate fallback)
            active("OTC-T-0105", "Six Carried Pier", "GBR", 53.0, 0.5, "Europe/London",
                   [official("OTC-T-0105", simple_constituents(0.95), qc_status="flagged",
                             qc_flags=[{"flag": "carried_over", "reason": "the source failed the coverage check in this build"}],
                             provenance={"adapter_version": "0.0.0-test", "build": dict(BUILD), "carried_from_release": SECOND,
                                         "decision": {"tier": "fallback", "outcome": "fallback", "reason": "source check failed"}})]),
            # a JMA set: the JMA provenance keys, read through raw
            active("OTC-T-0106", "Six Jma Port", "JPN", 35.6, 139.8, "Asia/Tokyo",
                   [cset("OTC-T-0106", "jma", "jma", "official", "otc-greenwich-v1", "jma", simple_constituents(0.9),
                         provenance={"adapter_version": "0.0.0-test", "build": dict(BUILD), "owner": "jma",
                                     "redistribution": "redistribute", "phase_reference_longitude_deg": 135.0,
                                     "jma_station_code": "TK", "analysis_years": {"long_period": "2000-2018", "short_period": None},
                                     "source_constituents_not_published": [{"source_name": "MSF", "reason": "no OTC name (test)"}]})]),
            tombstone("OTC-T-0108", "Six Merged Steps", datestamp, "merged", s1, "Same gauge as OTC-T-0101 (test tombstone)."),
        ]
    return st


def small_doc(datestamp, full=False, concept_doi="10.5072/zenodo.1"):
    """A format 1.0 release with the annotation stations (only OTC-T-0101 unless full)."""
    base = release_doc(BASE)
    rel = {"datestamp": datestamp, "created": "2099-12-31T18:00:00Z", "min_reader_version": FORMAT,
           "fit_min_good_hours": 360, "concept_doi": concept_doi,
           "source_versions": {"eot20": "20991231", "gesla": "4.1", "noaa": "20991231"},
           "build_commit": "89abcdef0123456789abcdef0123456789abcdef",
           "changelog_url": f"https://opentideconstants.org/changelog/#{datestamp}"}
    licences = base["licences"] + ([{"licence_id": "jma", "spdx": "LicenseRef-JMA-Test", "provider": "Example Meteorological Agency",
                                     "attribution": "Synthetic test data in the style of JMA.", "commercial_use": False,
                                     "restriction": "Test: non-commercial use only, by the provider's terms.",
                                     "terms_url": "https://example.org/jma-test-terms"}] if full else [])
    doc = {"format_version": FORMAT, "release": rel, "conventions": base["conventions"], "licences": licences,
           "constituents": base["constituents"], "astro_tables": base["astro_tables"],
           "stations": v1_stations(datestamp, full)}
    doc["stations"].sort(key=lambda s: s["station_id"])
    return doc


VALUES = "20991231.2"
FOLD_D = "20991231.2"


def values_doc():
    """Values the SDKs gave four answers for (review round 1, PK08), in a valid 1.0 release:
    a created time with an offset and a fraction, a validation previous_release with a non-number value, a station
    name with a NUL inside, and one that ends in NUL."""
    doc = small_doc(VALUES)
    doc["release"]["created"] = "2099-12-31T02:00:00.5+02:00"
    s1 = doc["stations"][0]
    s1["validation"] = [{"set_id": f"{s1['station_id']}/noaa", "reference_source": "noaa", "window": "2099-01",
                         "time_mae_min": 1.5, "height_mae_m": 0.01, "previous_release": {"time_mae_min": "n/a", "height_mae_m": 0.02}}]
    doc["stations"] += [gauge_station("OTC-T-0151", "Me\u0000da", "MLT", 35.9, 14.5, "Europe/Malta", 0.4),
                        gauge_station("OTC-T-0152", "Pier\u0000", "MLT", 35.8, 14.4, "Europe/Malta", 0.4)]
    doc["stations"].sort(key=lambda s: s["station_id"])
    return doc


def kept_reason_doc():
    """A constituent kept_reason of 48 bytes (the schema sets no maxLength; PK08 B2-1, D13)."""
    doc = small_doc(VALUES)
    doc["stations"][0]["constant_sets"][0]["constituents"][0]["kept_reason"] = "snr above 2.0 and stable across the yearly fits"
    return doc


def source_name_doc():
    """A constituent source_name of 31 characters that are 62 UTF-8 bytes (maxLength counts characters; PK08 B2-2)."""
    doc = small_doc(VALUES)
    doc["stations"][0]["constant_sets"][0]["constituents"][0]["source_name"] = "\u00d8" * 31
    return doc


FOLD_NAMES = [("OTC-T-0161", "\u0126amrun"), ("OTC-T-0162", "\u0166orvik"), ("OTC-T-0163", "\u014aaliq"),
              ("OTC-T-0164", "\u0138immik"), ("OTC-T-0165", "\u03a0\u03cc\u03c1\u03bf\u03c2"),
              ("OTC-T-0166", "Paral\u00b7lel"), ("OTC-T-0167", "Saint\u00a0Malo")]


def fold_doc():
    """Station names for the fold rules of D12: \u03c2 (final sigma), \u0127, \u0167, \u014b, \u0138, the middle dot and NBSP."""
    doc = small_doc(FOLD_D)
    doc["stations"] += [gauge_station(sid, name, "MLT", 35.0 + i / 10, 14.0, "Europe/Malta", 0.3)
                        for i, (sid, name) in enumerate(FOLD_NAMES)]
    doc["stations"].sort(key=lambda s: s["station_id"])
    return doc


CHAIN_D = "20991231.2"


def chain_doc():
    """Subordinate chains for the attribution (CR2 DR1): offsets-only stations two and three links from their
    reference station, each link with its own offsets licence; a subordinate with its own set on such a chain; and one
    whose reference station is a subordinate with a recommended set, where the walk stops."""
    doc = small_doc(CHAIN_D)
    doc["licences"] = doc["licences"] + [
        {"licence_id": "harbour-a", "spdx": "CC-BY-4.0", "provider": "Example Harbour Board A",
         "attribution": "Offsets: Example Harbour Board A, test data.", "commercial_use": True},
        {"licence_id": "harbour-b", "spdx": "CC-BY-4.0", "provider": "Example Harbour Board B",
         "attribution": "Offsets: Example Harbour Board B, test data.", "commercial_use": True},
        # the provider of harbour-a again: one entry per provider, the first by licence_id
        {"licence_id": "harbour-c", "spdx": "CC-BY-4.0", "provider": "Example Harbour Board A",
         "attribution": "Offsets: Example Harbour Board A, second licence.", "commercial_use": True},
    ]

    def sub(sid, name, lat, ref, licence=None, sets=(), recommended=None):
        off = {"reference_station_id": ref, "time_offset_high_min": 6, "time_offset_low_min": 9,
               "height_offset_high": 1.02, "height_offset_low": 0.97, "height_adjusted_type": "R"}
        if licence:
            off["licence_id"] = licence
        st = active(sid, name, "MLT", lat, 14.6, "Europe/Malta", list(sets), type_="subordinate", subordinate_offsets=off)
        st["recommended_set_id"] = recommended
        return st

    doc["stations"] += [
        gauge_station("OTC-T-0171", "Chain Reference", "MLT", 35.71, 14.6, "Europe/Malta", 0.5),
        sub("OTC-T-0172", "Chain Pier One", 35.72, "OTC-T-0171", "harbour-a"),
        sub("OTC-T-0173", "Chain Pier Two", 35.73, "OTC-T-0172", "harbour-b"),
        sub("OTC-T-0174", "Chain Pier Three", 35.74, "OTC-T-0173", "harbour-c"),
        sub("OTC-T-0175", "Chain Model Pier", 35.75, "OTC-T-0173",
            sets=[cset("OTC-T-0175", "eot20", "eot20", "model", "otc-greenwich-v1", "eot20", simple_constituents(0.5))],
            recommended="OTC-T-0175/eot20"),
        sub("OTC-T-0176", "Chain Outer Pier", 35.76, "OTC-T-0175", "kartverket"),
    ]
    doc["stations"].sort(key=lambda s: s["station_id"])
    return doc


def no_gz(files, sums, entry, reuse):
    """The release publishes .json, .jsonl and .meta.json, and no .json.gz (valid: PK11 B2-6)."""
    files = {n: b for n, b in files.items() if not n.endswith(".json.gz")}
    entry = copy.deepcopy(entry)
    entry["files"] = [f for f in entry["files"] if not f["name"].endswith(".json.gz")]
    return rehash(files, sums, entry)


ROOTS = [
    # (root, docs, version DOIs, zenodo_material, manifest entry)
    ("good", lambda: [release_doc(BASE), release_doc(SECOND)], {SECOND: "10.5072/zenodo.2"}, (),
     {"releases": [SECOND, BASE], "latest": SECOND, "expect": "load", "defect": None}),
    ("order", lambda: [release_doc(SECOND), release_doc(COUNTER)], {}, (),
     {"releases": [COUNTER, SECOND], "latest": COUNTER, "expect": "load", "defect": None}),
    ("v1", lambda: [small_doc(V1, full=True)], {V1: "10.5072/zenodo.3"}, (V1,),
     {"releases": [V1], "latest": V1, "expect": "load", "defect": None,
      "note": "the format 1.0 annotations: ok, flagged and no_constants sets, a station with only no_constants sets, "
              "a carried-over set, each time_base code, provenance.build, a merged tombstone"}),
    ("reader", lambda: [small_doc(READER_OLD), small_doc(READER_OK), versioned(small_doc(READER_NEW), TOO_NEW)],
     {READER_OK: "10.5072/zenodo.3"}, (),
     {"releases": [READER_NEW, READER_OK, READER_OLD], "latest": READER_NEW, "latest_readable": READER_OK,
      "expect": "load", "expect_by_release": {READER_NEW: {"error": "reader_too_old"}}, "defect": None,
      "note": f"the pointers name {READER_NEW} (min_reader_version {TOO_NEW}); a 1.0 reader takes {READER_OK} "
              "from OTC_index.json (spec 5.2 step 2a)"}),
    ("values", lambda: [values_doc()], {VALUES: "10.5072/zenodo.5"}, (),
     {"releases": [VALUES], "latest": VALUES, "expect": "load", "defect": None,
      "note": "created with an offset and a fraction, a non-number in validation.previous_release, station names with a NUL"}),
    ("values-kept-reason", lambda: [kept_reason_doc()], {}, (),
     {"releases": [VALUES], "latest": VALUES, "expect": "load", "defect": None, "note": "a kept_reason of 48 bytes"}),
    ("values-source-name", lambda: [source_name_doc()], {}, (),
     {"releases": [VALUES], "latest": VALUES, "expect": "load", "defect": None, "note": "a source_name of 31 characters, 62 bytes"}),
    ("fold", lambda: [fold_doc()], {}, (),
     {"releases": [FOLD_D], "latest": FOLD_D, "expect": "load", "defect": None, "note": "station names for the D12 fold rules"}),
    ("chain", lambda: [chain_doc()], {}, (),
     {"releases": [CHAIN_D], "latest": CHAIN_D, "expect": "load", "defect": None,
      "note": "subordinate stations two and three links from their reference station, for the attribution (CR2 DR1)"}),
    ("major", lambda: [small_doc(BASE), small_doc(MAJOR_OK), versioned(small_doc(MAJOR_NEW), NEXT_MAJOR)], {}, (),
     {"releases": [MAJOR_NEW, MAJOR_OK, BASE], "latest": MAJOR_NEW, "latest_readable": MAJOR_OK,
      "expect": "load", "expect_by_release": {MAJOR_NEW: {"error": "unsupported_format"}}, "defect": None,
      "note": f"OTC_latest.json names {MAJOR_NEW} (format {NEXT_MAJOR}); OTC_latest-f1.json names {MAJOR_OK}: "
              "check_for_update reports newer_format_major 2 (spec 7.4)"}),
]


def build(out, reuse):
    """Write every root and fixtures.json under out. reuse = committed fixtures dir (for .gz bytes) or None."""
    manifest = {
        "description": "Conformance fixture releases (SDK spec 7.1). Synthetic data, CC0-1.0. Generated by conformance/tools/build_fixtures.py; do not edit.",
        "schemas": {v: {"url": u, "sha256": h} for v, (u, h) in SCHEMAS.items()},
        "supported_format_majors": SUPPORTED_MAJORS,
        "reader_format_version": "%d.%d" % READER_FORMAT,
        "fixtures": [],
    }
    for name, docs, vdois, material, entry in ROOTS:
        write_root(out / name, docs(), reuse_root=(reuse / name) if reuse else None, version_dois=vdois, material=material)
        manifest["fixtures"].append({"root": name, **entry})
    write_root(out / "nogz", [release_doc(SECOND)], reuse_root=(reuse / "nogz") if reuse else None, tamper=no_gz)
    manifest["fixtures"].append({"root": "nogz", "releases": [SECOND], "latest": SECOND, "expect": "load", "defect": None,
                                 "note": "the release publishes no .json.gz"})
    for name, expect, defect, docs, tamper, *extra in BAD:
        write_root(out / "bad" / name, docs(), reuse_root=(reuse / "bad" / name) if reuse else None, tamper=tamper)
        manifest["fixtures"].append({"root": f"bad/{name}", "releases": [BASE], "latest": BASE,
                                     "expect": expect if expect == "load" else {"error": expect},
                                     "defect": defect, **(extra[0] if extra else {})})
    (out / "fixtures.json").write_bytes(dumps_pretty(manifest))


# --------------------------------------------------------------------------- reference reader (check only)

class Fail(Exception):
    def __init__(self, code, detail):
        super().__init__(f"{code}: {detail}")
        self.code = code


def fetch_schema(version, schema_dir=None):
    url, digest = SCHEMAS[version]
    if schema_dir:
        data = (Path(schema_dir) / SCHEMA_FILES[version]).read_bytes()
    else:
        data = urllib.request.urlopen(url, timeout=30).read()
    if sha(data) != digest:
        raise SystemExit(f"schema {version} SHA-256 {sha(data)} is not the pinned {digest}")
    schema = json.loads(data)
    Draft202012Validator.check_schema(schema)
    return schema


def load_schemas(schema_dir=None):
    """Every pinned schema: {"1.0": ..., "index-1.0": ...}."""
    _require_formats()
    return {v: fetch_schema(v, schema_dir) for v in SCHEMAS}


def version_key(v):
    major, minor = (int(x) for x in str(v).split("."))
    return major, minor


def _not_json(token):
    raise ValueError(f"{token} is not JSON")


def strict_json(text):
    """json.loads that refuses NaN and Infinity (they are not JSON, RFC 8259; Python accepts them)."""
    return json.loads(text, parse_constant=_not_json)


def checked_version(v, what):
    """A MAJOR.MINOR version from a release (spec 7.4); anything else is invalid_release (D9), never a raw error."""
    if not isinstance(v, str) or not re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", v):
        raise Fail("invalid_release", f"{what} {v!r} is not MAJOR.MINOR")
    return version_key(v)


def read_file(root, name):
    """A file the release names. A missing one is what an SDK sees as a 404 for a listed file (D32: network)."""
    try:
        return (root / name).read_bytes()
    except FileNotFoundError:
        raise Fail("network", f"{name} is listed but missing") from None


def resolve(schema, node):
    while isinstance(node, dict) and "$ref" in node:
        node = schema["$defs"][node["$ref"].split("/")[-1]]
    return node


def strip_unknown(schema, value, node):
    """Tolerant read (spec 7.3): drop the fields that the schema does not define. Returns (value, dropped paths)."""
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
    for what, key in (("conventions", "convention_id"), ("licences", "licence_id")):
        ids = [x[key] for x in doc[what]]
        if len(ids) != len(set(ids)):
            errs.append(f"duplicate {key} in {what}")
    conv = {c["convention_id"] for c in doc["conventions"]}
    lic = {l["licence_id"] for l in doc["licences"]}
    table = {(c["constituent_table_version"], c["name"]) for c in doc["constituents"]}
    conv_table = {c["convention_id"]: c["constituent_table_version"] for c in doc["conventions"]}
    astro = {t["astro_table_id"]: t for t in doc.get("astro_tables", [])}
    conv_astro = {}
    for c in doc["conventions"]:
        if "astro_table_id" not in c:
            continue
        t = astro.get(c["astro_table_id"])
        if t is None:
            errs.append(f"{c['convention_id']}: astro_table_id {c['astro_table_id']} does not resolve")
            continue
        conv_astro[c["convention_id"]] = t
        if "tables_sha256" in c and c["tables_sha256"] != t["tables_sha256"]:
            errs.append(f"{c['convention_id']}: tables_sha256 differs from astro table {t['astro_table_id']}")
    for t in astro.values():
        n = t["last_year"] - t["first_year"] + 1
        for name, row in t["constituents"].items():
            if len(row["v0u_deg"]) != n or len(row["f"]) != n:
                errs.append(f"astro table {t['astro_table_id']}: {name} does not have {n} yearly entries")
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
            current = [c for b in cs.get("current_bins", []) for c in b.get("constituents", [])]
            for c in cs["constituents"] + cs.get("dropped_constituents", []) + current:
                if tv and (tv, c["name"]) not in table:
                    errs.append(f"{cs['set_id']}: constituent {c['name']} not in table {tv}")
            at = conv_astro.get(cs["convention_id"])
            for c in cs["constituents"]:
                row = at and at["constituents"].get(c["name"])
                if at and row is None:
                    errs.append(f"{cs['set_id']}: constituent {c['name']} not in astro table {at['astro_table_id']}")
                elif row and abs(row["speed_deg_per_hour"] - c["speed_deg_per_hour"]) > 1e-7:
                    errs.append(f"{cs['set_id']}: {c['name']} speed differs from astro table {at['astro_table_id']}")
        rec = s["recommended_set_id"]
        if rec is not None and rec not in own:
            errs.append(f"{sid}: recommended_set_id {rec} does not resolve")
        # The schema's rules (active_station if/then/else): a reference station with a set that has constants names
        # a recommended set; a subordinate has subordinate_offsets, current_offsets or a set, and may have no
        # recommended set (a subordinate current station has only current_offsets, like the site's example.json).
        all_no_constants = bool(s["constant_sets"]) and all(cs["qc_status"] == "no_constants" for cs in s["constant_sets"])
        if rec is None and s["type"] == "reference" and not all_no_constants:
            errs.append(f"{sid}: a reference station with usable sets has no recommended_set_id")
        if rec in own and next(cs for cs in s["constant_sets"] if cs["set_id"] == rec)["qc_status"] in ("no_constants", "excluded"):
            errs.append(f"{sid}: the recommended set {rec} has no usable constants")
        if s["type"] == "subordinate" and not ("subordinate_offsets" in s or "current_offsets" in s or s["constant_sets"]):
            errs.append(f"{sid}: subordinate with no subordinate_offsets, current_offsets or constant set")
        off = s.get("subordinate_offsets")
        if off:
            if off["reference_station_id"] not in active_ids:
                errs.append(f"{sid}: reference_station_id {off['reference_station_id']} does not resolve")
            if "licence_id" in off and off["licence_id"] not in lic:
                errs.append(f"{sid}: offsets licence_id {off['licence_id']} does not resolve")
        for co in s.get("current_offsets", []):
            if co["reference_station_id"] not in active_ids:
                errs.append(f"{sid}: current_offsets reference_station_id {co['reference_station_id']} does not resolve")
            if "licence_id" in co and co["licence_id"] not in lic:
                errs.append(f"{sid}: current_offsets licence_id {co['licence_id']} does not resolve")
        for v in s.get("validation", []):
            if v["set_id"] not in own:
                errs.append(f"{sid}: validation set_id {v['set_id']} does not resolve")
        for system, val in s.get("aliases", {}).items():
            for a in val if isinstance(val, list) else [val]:
                owner = seen_alias.setdefault((system, a), sid)
                if owner != sid:
                    errs.append(f"alias {system}:{a} used by {owner} and {sid}")
    for t in doc["stations"]:
        if t["status"] == "removed" and t.get("merged_into") is not None and t["merged_into"] not in active_ids:
            errs.append(f"{t['station_id']}: merged_into {t['merged_into']} does not resolve")
    return errs


def open_release(root, datestamp, schemas):
    """Reference reader: what an SDK must do with this release. Returns a summary dict or raises Fail."""
    index = json.loads((root / "OTC_index.json").read_bytes())
    entry = next((e for e in index["releases"] if e["datestamp"] == datestamp), None)
    if entry is None:
        raise Fail("release_not_found", datestamp)
    sums_path = root / f"OTC_{datestamp}.sha256"
    sums = {}
    for line in read_file(root, sums_path.name).decode("utf-8", "replace").splitlines():
        m = re.fullmatch(r"([0-9a-f]{64})  (\S.*)", line)
        if not m:
            raise Fail("checksum_mismatch", f"{sums_path.name}: a line that is not '<sha256>  <name>': {line[:80]!r}")
        sums[m.group(2)] = m.group(1)
    # Spec 5.2 step 4.1: the pointer and the .sha256 file must agree.
    for f in entry["files"]:
        if f["name"] == sums_path.name:
            if sha(read_file(root, sums_path.name)) != f["sha256"]:
                raise Fail("checksum_mismatch", f"{f['name']}: pointer and file differ")
            continue
        if sums.get(f["name"]) != f["sha256"]:
            raise Fail("checksum_mismatch", f"{f['name']}: pointer {f['sha256']} vs .sha256 {sums.get(f['name'])}")
    if set(sums) != {f["name"] for f in entry["files"]} - {sums_path.name}:
        raise Fail("checksum_mismatch", "pointer and .sha256 list different files")
    # Step 4.2: size and SHA-256 of every file.
    for f in entry["files"]:
        data = read_file(root, f["name"])
        if len(data) != f["size"]:
            raise Fail("checksum_mismatch", f"{f['name']}: size {len(data)} vs {f['size']}")
        if sha(data) != f["sha256"]:
            raise Fail("checksum_mismatch", f"{f['name']}: sha256 {sha(data)} vs {f['sha256']}")
    body = read_file(root, f"OTC_{datestamp}.json")
    if f"OTC_{datestamp}.json.gz" in {f["name"] for f in entry["files"]}:   # a release need not publish .json.gz
        try:
            unzipped = gzip.decompress(read_file(root, f"OTC_{datestamp}.json.gz"))
        except (OSError, EOFError, zlib.error) as e:
            raise Fail("checksum_mismatch", f".json.gz is not gzip: {type(e).__name__}: {e}") from None
        if unzipped != body:
            raise Fail("checksum_mismatch", ".json.gz does not decompress to .json")
    try:
        doc = strict_json(body)
        meta = strict_json(read_file(root, f"OTC_{datestamp}.meta.json"))
        lines = [strict_json(l) for l in read_file(root, f"OTC_{datestamp}.jsonl").decode("utf-8").splitlines()]
    except ValueError as e:
        raise Fail("invalid_release", f"not JSON: {e}")
    if not isinstance(doc, dict):
        raise Fail("invalid_release", "the release is not a JSON object")
    # Spec 7.4: the major must be supported, and release.min_reader_version must be readable.
    major, minor = checked_version(doc.get("format_version"), "format_version")
    if major not in SUPPORTED_MAJORS:
        raise Fail("unsupported_format", f"format_version {doc['format_version']}")
    min_reader = (doc.get("release") or {}).get("min_reader_version")
    if min_reader is not None and checked_version(min_reader, "release.min_reader_version") > READER_FORMAT:
        raise Fail("reader_too_old", f"release {datestamp} needs a reader for format {min_reader}; "
                                     f"this reader reads format {'%d.%d' % READER_FORMAT}")
    # spec 4.6: a set with no provenance.build is malformed 1.0, but an SDK loads it (build null): a general rule.
    # The tolerance is reported in unknown_fields, so a root outside bad/ that needs it fails --check.
    checked, dropped = validate_release(doc, meta, lines, schemas, allow_missing_build=True)
    if lines != doc["stations"]:
        raise Fail("invalid_release", ".jsonl lines differ from .json stations")
    if meta != {k: v for k, v in doc.items() if k != "stations"}:
        raise Fail("invalid_release", ".meta.json differs from .json without stations")
    return {"stations": len(doc["stations"]), "format_version": doc["format_version"], "unknown_fields": dropped}


def validate_release(doc, meta, lines, schemas, allow_missing_build=False):
    """Validate a release against the schema of its format. A format with no schema of its own is read
    tolerantly (spec 7.3) against the newest schema below it: the unknown fields are dropped (they stay in raw).
    With allow_missing_build a set with no provenance.build is tolerated (spec 4.6): the .json, every .jsonl line
    and the .meta.json are then checked with the build put back, so it is the only defect, and the tolerance is
    listed in the returned paths.
    Returns (the checked document, the dropped paths) or raises Fail."""
    version = version_key(doc["format_version"])
    known = sorted((version_key(v), v) for v in schemas if not v.startswith("index"))
    tolerated = []
    # Spec 4.6: a set with no provenance.build is malformed, but the SDK loads it (build null).
    # only a provenance object without build: a set with no provenance at all is left to the schema (invalid_release)
    missing = [cs["set_id"] for st in doc["stations"] for cs in st.get("constant_sets", [])
               if isinstance(cs.get("provenance"), dict) and "build" not in cs["provenance"]]
    if missing and allow_missing_build:
        tolerated = [f"no provenance.build in {m}" for m in missing]
        doc = restore_build(doc)
        meta = restore_build(meta)
        lines = [restore_station_build(l) for l in lines]
    exact = next((v for k, v in known if k == version), None)
    dropped = []
    if exact is not None:
        schema = schemas[exact]
        checked = doc
    else:
        below = [v for k, v in known if k < version]
        if not below:
            raise Fail("invalid_release", f"no schema for format {doc['format_version']}")
        schema = schemas[below[-1]]
        checked, dropped = strip_unknown(schema, doc, schema)
        checked["format_version"] = below[-1]
        # An enum value the schema does not know is read as "other" (spec 7.3); check the rest of the set as flagged.
        known_qc = schema["$defs"]["constant_set"]["properties"]["qc_status"]["enum"]
        for st in checked["stations"]:
            for cs in st.get("constant_sets", []):
                if cs["qc_status"] not in known_qc:
                    dropped.append(f"{cs['set_id']}: qc_status {cs['qc_status']!r} (read as other)")
                    cs["qc_status"] = "flagged"
    errs = [f"{list(e.path)} {e.message}" for e in validator(schema).iter_errors(checked)]
    if not errs:   # the cross-references assume the types the schema gives
        errs = cross_ref_errors(checked)
    if errs:
        raise Fail("invalid_release", "; ".join(errs[:5]))
    if exact is not None:
        defs = {"$schema": schema["$schema"], "$defs": schema["$defs"]}
        meta_v = validator({**defs, "$ref": "#/$defs/meta"})
        st_v = validator({**defs, "$ref": "#/$defs/station"})
        errs = [f"meta {e.message}" for e in meta_v.iter_errors(meta)]
        errs += [f"jsonl line {i + 1}: {e.message}" for i, l in enumerate(lines) for e in st_v.iter_errors(l)]
        if errs:
            raise Fail("invalid_release", "; ".join(errs[:5]))
    return checked, dropped + tolerated


def as_readable(root, datestamp, schemas):
    """For a release that no 1.0 reader reads (min_reader_version 1.99, or format 2.0): its data must still be a
    valid format 1.0 release once the two version fields say 1.0, so the version is its only defect."""
    def as_10(d):
        d["format_version"] = FORMAT
        d["release"]["min_reader_version"] = FORMAT
        d.pop("future_top_level", None)
        return d

    doc = as_10(json.loads((root / f"OTC_{datestamp}.json").read_bytes()))
    meta = as_10(json.loads((root / f"OTC_{datestamp}.meta.json").read_bytes()))
    lines = [json.loads(l) for l in (root / f"OTC_{datestamp}.jsonl").read_text(encoding="utf-8").splitlines()]
    # the .jsonl and .meta.json of such a release are read too (format/reader-too-old opens the .jsonl): they must
    # agree with the .json, and each is validated on its own
    if lines != doc["stations"]:
        raise Fail("invalid_release", ".jsonl lines differ from .json stations")
    if meta != {k: v for k, v in doc.items() if k != "stations"}:
        raise Fail("invalid_release", ".meta.json differs from .json without stations")
    validate_release(doc, meta, lines, schemas)


def index_errors(root, schemas):
    """OTC_index.json validates against otc-index-1.0, each pointer against its release_info."""
    schema = schemas["index-1.0"]
    errs = [f"OTC_index.json {list(e.path)} {e.message}"
            for e in validator(schema).iter_errors(json.loads((root / "OTC_index.json").read_bytes()))]
    info = validator({"$schema": schema["$schema"], "$defs": schema["$defs"], "$ref": "#/$defs/release_info"})
    for p in sorted(root.glob("OTC_latest*.json")):
        errs += [f"{p.name} {e.message}" for e in info.iter_errors(json.loads(p.read_bytes()))]
    return errs


def readable_latest(root):
    """Spec 5.2 steps 2 and 2a: the pointer's release, or, if it is too new for this reader, the newest index
    entry with a supported major and a readable min_reader_version."""
    pointer = json.loads((root / f"OTC_latest-f{SUPPORTED_MAJORS[-1]}.json").read_bytes())

    def readable(e):
        mr = e.get("min_reader_version")
        return version_key(e["format_version"])[0] in SUPPORTED_MAJORS and (mr is None or version_key(mr) <= READER_FORMAT)

    if readable(pointer):
        return pointer["datestamp"]
    index = json.loads((root / "OTC_index.json").read_bytes())
    return next((e["datestamp"] for e in index["releases"] if readable(e)), None)


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
    # every per-major pointer is the newest index entry of its major (not only the latest release's major)
    majors = sorted({int(e["format_version"].split(".")[0]) for e in index["releases"]})
    for major in majors:
        newest = next(e for e in index["releases"] if int(e["format_version"].split(".")[0]) == major)
        per_major = root / f"OTC_latest-f{major}.json"
        if not per_major.exists() or json.loads(per_major.read_bytes()) != newest:
            errs.append(f"{per_major.name} missing or not the newest index entry of major {major}")
    extra = sorted(p.name for p in root.glob("OTC_latest-f*.json") if p.name not in {f"OTC_latest-f{m}.json" for m in majors})
    if extra:
        errs.append(f"per-major pointers with no release of that major: {extra}")
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


def check(schema_dir=None):
    schemas = load_schemas(schema_dir)
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
        ierrs = index_errors(root, schemas)
        if fx.get("index_invalid"):   # this fixture's index must fail otc-index-1.0
            if not ierrs:
                errs.append("the index should fail otc-index-1.0, and it passes")
            print(f"{'PASS' if ierrs else 'FAIL'}  {fx['root']:30} index fails otc-index-1.0 as it should  [{'; '.join(ierrs)[:120]}]")
        else:
            errs += ierrs
        for d in fx["releases"]:
            expect = (fx.get("expect_by_release") or {}).get(d, fx["expect"])
            try:
                got = open_release(root, d, schemas)
                outcome, detail = "load", f"{got['stations']} stations, format {got['format_version']}"
                if got["unknown_fields"]:
                    detail += f", read tolerantly: {', '.join(got['unknown_fields'])}"
            except Fail as e:
                outcome, detail = {"error": e.code}, str(e)
            ok = outcome == expect
            if not ok:
                errs.append(f"{d}: expected {expect}, got {outcome} ({detail})")
            if outcome in ({"error": "reader_too_old"}, {"error": "unsupported_format"}):
                try:
                    as_readable(root, d, schemas)
                    readable = None
                except Fail as e:
                    readable = e
                if fx.get("valid_as_1_0", True) and readable is not None:
                    ok = False
                    errs.append(f"{d}: not a valid {FORMAT} release apart from its versions: {readable}")
                elif not fx.get("valid_as_1_0", True) and readable is None:
                    ok = False
                    errs.append(f"{d}: should not be a valid {FORMAT} release apart from its versions, and it is")
            print(f"{'PASS' if ok else 'FAIL'}  {fx['root']:30} {d:11} expect {json.dumps(expect):32} got {json.dumps(outcome)}  [{detail}]")
        if "latest_readable" in fx:
            got = readable_latest(root)
            ok = got == fx["latest_readable"]
            if not ok:
                errs.append(f"latest for a {'%d.%d' % READER_FORMAT} reader is {got}, not {fx['latest_readable']}")
            print(f"{'PASS' if ok else 'FAIL'}  {fx['root']:30} latest for a {'%d.%d' % READER_FORMAT} reader is {got}")
        for d in fx["releases"]:
            expect = (fx.get("expect_by_release") or {}).get(d, fx["expect"])
            if expect != "load":
                continue   # an error outcome is checked above
            try:
                got = open_release(root, d, schemas)
            except Fail as e:
                errs.append(f"{d}: does not load: {e}")   # also reported above; never skipped in silence
                continue
            if not fx["root"].startswith("bad/") and got["unknown_fields"]:
                # A root outside bad/ must be plain format 1.0: nothing read tolerantly.
                errs.append(f"{d}: a root outside bad/ read tolerantly: {', '.join(got['unknown_fields'])}")
            if version_key(got["format_version"]) > READER_FORMAT:
                # A release in a higher minor must carry fields this reader does not know, at several levels: only
                # schema paths count ($.-prefixed), not the other tolerances (a qc_status read as other, a missing build).
                schema_paths = [x for x in got["unknown_fields"] if x.startswith("$.")]
                if len(schema_paths) < 2:
                    errs.append(f"{d}: a format {got['format_version']} release with too few unknown fields: {schema_paths}")
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
    parser.add_argument("--schema-dir", default=str(VENDORED_SCHEMAS),
                        help="a directory with copies of the pinned schemas (otc-1.0.schema.json, otc-index-1.0.schema.json); "
                             "default: conformance/schemas")
    parser.add_argument("--download-schemas", action="store_true",
                        help="fetch the pinned schemas from the site repository instead of reading --schema-dir")
    args = parser.parse_args()
    if args.check:
        return check(None if args.download_schemas else args.schema_dir)
    FIXTURES.mkdir(parents=True, exist_ok=True)
    # Build next to the fixtures (the same file system), then swap each generated target in with a rename. If a
    # swap fails part-way, the targets already moved are put back: the fixtures are all new or all old.
    with tempfile.TemporaryDirectory(dir=FIXTURES.parent, prefix=".fixtures-") as tmp:
        new, old = Path(tmp) / "new", Path(tmp) / "old"
        build(new, FIXTURES)
        old.mkdir()
        moved, placed = [], []
        try:
            for name in GENERATED:
                target = FIXTURES / name
                if target.exists():
                    os.replace(target, old / name)
                    moved.append(name)
                os.replace(new / name, target)
                placed.append(name)
        except BaseException:
            for name in placed:
                target = FIXTURES / name
                (shutil.rmtree if target.is_dir() else os.unlink)(target)
            for name in moved:
                os.replace(old / name, FIXTURES / name)
            print(f"could not write the fixtures; the old ones are back under {FIXTURES}", file=sys.stderr)
            raise
    print(f"wrote fixtures under {FIXTURES}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
