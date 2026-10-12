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
import datetime
import gzip
import hashlib
import json
import math
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

# Format 1.0 and its index schema, from the site repository at the merge of site PR #48 (the analysis source
# type, which revised format 1.0 in place), pinned by commit and SHA-256.
SCHEMA_COMMIT = "23aedbe83161790518d9c3a1eeb9a82b8a9c3f18"
_RAW = f"https://raw.githubusercontent.com/opentideconstants/opentideconstants/{SCHEMA_COMMIT}/src/schema"
SCHEMAS = {
    "1.0": (f"{_RAW}/otc-1.0.schema.json", "36d6c579c33089c40231e0539b5ebe890eba33399b87f8dc8406d49ea1096b1b"),
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
GENERATED = ["good", "order", "v1", "reader", "major", "values", "values-kept-reason", "values-source-name", "values-nul", "fold", "aliases", "chain", "knc", "nogz",
             "bad", "predict", "predict-bad", "knc-predict", "fixtures.json"]

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
        datum={"msl_offset_m": 0.0, "named": {"mhhw": 0.91, "mllw": -0.93},
               "basis": {"mhhw": {"kind": "published", "method": "source"},
                         "mllw": {"kind": "published", "method": "source"}}},
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


def sha256_dup_name(files, sums, entry, reuse):
    """The .jsonl is listed twice: first with a wrong digest, then with the right one. A reader where the last row
    wins passes it; DR14 refuses a repeated name, so that row order never decides a check."""
    name = next(n for n in files if n.endswith(".jsonl")).encode()
    lines = []
    for line in sums.splitlines():
        if line.endswith(b"  " + name):
            lines.append(sha(b"wrong digest").encode() + b"  " + name)
        lines.append(line)
    return rehash(files, sums, entry, b"\n".join(lines) + b"\n")


def sha256_invalid_utf8(files, sums, entry, reuse):
    """A last row whose name has a byte that is not UTF-8 (DR14). Every other row is honest."""
    return rehash(files, sums, entry, sums + sha(b"extra").encode() + b"  OTC_" + BASE.encode() + b".\xff\n")


def sha256_no_json_row(files, sums, entry, reuse):
    """The .sha256 and the pointer list the .json.gz but not the .json (DR15: an eager download needs the .json
    row). The .json file is still published, so only the missing row is the defect."""
    name = next(n for n in files if n.endswith(".json"))
    sums = b"".join(l + b"\n" for l in sums.splitlines() if not l.endswith(b"  " + name.encode()))
    entry = copy.deepcopy(entry)
    entry["files"] = [f for f in entry["files"] if f["name"] != name]
    return rehash(files, sums, entry, sums)


def pointer_file_no_sha256(files, sums, entry, reuse):
    """The pointer and index entry for OTC_{D}.sha256 have no sha256 (schema-invalid; DR12: invalid_release)."""
    files, sums, entry = rehash(files, sums, entry)
    next(f for f in entry["files"] if f["name"].endswith(".sha256")).pop("sha256")
    return files, sums, entry


def index_content_digest_bad(files, sums, entry, reuse):
    entry = copy.deepcopy(entry)
    entry["content_sha256"] = "not a digest"
    return files, sums, entry


def changed_doc(change):
    def make():
        # a JSON round trip: release_doc shares objects such as VERIFIED between stations (and calls), and a change
        # must reach one place only
        doc = json.loads(json.dumps(release_doc(BASE)))
        change(doc)
        doc["stations"].sort(key=lambda s: str(s["station_id"]))
        return [doc]
    return make


def _station(doc, sid):
    return next(s for s in doc["stations"] if s["station_id"] == sid)


def _licence(doc, lid):
    return next(x for x in doc["licences"] if x["licence_id"] == lid)


def _null_providers(doc):
    _licence(doc, "eot20")["provider"] = None
    doc["licences"].append({"licence_id": "anon", "spdx": "CC-BY-4.0", "provider": None,
                            "attribution": "Anonymous synthetic test data.", "commercial_use": True})


def _null_providers_nc(doc):
    _null_providers(doc)
    anon = _licence(doc, "anon")
    anon.clear()
    anon.update({"licence_id": "anon", "spdx": "LicenseRef-Anon-Test", "provider": None,
                                  "attribution": "Anonymous synthetic test data.", "commercial_use": False,
                                  "restriction": "Test: non-commercial use only.",
                                  "terms_url": "https://example.org/anon-terms"})


def _nc_no_spdx(doc):
    lic = _licence(doc, "noaa")
    lic.update(commercial_use=False, restriction="Test: non-commercial use only.", terms_url="https://example.org/noaa-terms")
    lic.pop("spdx")


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


# Review round 2 (PK-R2-05): malformed content that json.dumps cannot write (an overflow literal, invalid UTF-8, a
# lone surrogate escape) is made by changing the bytes of the .json and the .jsonl after they are written. The
# .json.gz is made again from the changed .json and every digest is honest, so the content is the only defect.
SENTINEL_LAT, SENTINEL_LON, SENTINEL_AMP = 1.2345678, 2.3456789, 0.9876543


def raw_bytes(old, new):
    def t(files, sums, entry, reuse):
        files = dict(files)
        for name in list(files):
            if name.endswith(".jsonl") or (name.endswith(".json") and not name.endswith(".meta.json")):
                assert files[name].count(old) == 1, f"{old!r} is not in {name} exactly once"
                files[name] = files[name].replace(old, new)
        for name in list(files):
            if name.endswith(".json.gz"):
                files[name] = gz(files[name[:-3]], reuse / name if reuse else None)
        return rehash(files, sums, entry)
    return t


def _set_of(doc, sid, i=0):
    return _station(doc, sid)["constant_sets"][i]


def _constituent_twice(doc):
    cs = _set_of(doc, "OTC-T-0010")
    cs["constituents"].append(dict(cs["constituents"][0], amplitude_m=0.01))


def _proto_keys(doc):
    """Keys that are Object.prototype members in JavaScript: an alias system __proto__ and constructor (unknown
    systems in 1.0, so the release is format 1.1, read tolerantly), and a set source constructor (a valid source)."""
    doc["format_version"] = "1.1"
    _station(doc, "OTC-T-0001")["aliases"]["__proto__"] = "PX-0001"
    _station(doc, "OTC-T-0002")["aliases"]["constructor"] = "CX-0002"
    _set_of(doc, "OTC-T-0010")["source"] = "constructor"
    _set_of(doc, "OTC-T-0013")["source"] = "constructor"


BAD_R2_05 = [
    # wrong JSON types in known fields (spec 7.3: tolerant is not lax)
    ("recommended-set-id-number", "OTC-T-0010's recommended_set_id is the number 5 (malformed)",
     changed_doc(lambda d: _station(d, "OTC-T-0010").update(recommended_set_id=5)), None),
    ("station-name-number", "OTC-T-0010's name is the number 7 (malformed)",
     changed_doc(lambda d: _station(d, "OTC-T-0010").update(name=7)), None),
    ("station-timezone-number", "OTC-T-0010's timezone is the number 1 (malformed)",
     changed_doc(lambda d: _station(d, "OTC-T-0010").update(timezone=1)), None),
    ("status-number", "OTC-T-0010's status is the number 5: present but not a string (malformed, CR2 DR43)",
     changed_doc(lambda d: _station(d, "OTC-T-0010").update(status=5)), None),
    ("offsets-number-string", "OTC-T-0003's subordinate_offsets.time_offset_high_min is the string \"12\" (malformed)",
     changed_doc(lambda d: _station(d, "OTC-T-0003")["subordinate_offsets"].update(time_offset_high_min="12")), None),
    ("validation-number-string", "OTC-T-0001's first validation row has time_mae_min \"fast\" (malformed)",
     changed_doc(lambda d: _station(d, "OTC-T-0001")["validation"][0].update(time_mae_min="fast")), None),
    ("validation-count-fraction", "OTC-T-0001's first validation row has missed_events 1.5, not an integer (malformed)",
     changed_doc(lambda d: _station(d, "OTC-T-0001")["validation"][0].update(missed_events=1.5)), None),
    ("constituent-amplitude-string", "OTC-T-0010's first constituent has amplitude_m \"0.28\" (malformed)",
     changed_doc(lambda d: _set_of(d, "OTC-T-0010")["constituents"][0].update(amplitude_m="0.28")), None),
    ("datum-msl-string", "OTC-T-0001's noaa set has datum.msl_offset_m \"0.0\" (malformed)",
     changed_doc(lambda d: _set_of(d, "OTC-T-0001")["datum"].update(msl_offset_m="0.0")), None),
    ("good-samples-string", "OTC-T-0001's noaa set has record_span.good_samples \"166000\" (malformed)",
     changed_doc(lambda d: _set_of(d, "OTC-T-0001")["record_span"].update(good_samples="166000")), None),
    ("set-source-version-number", "OTC-T-0010's set has source_version the number 4 (malformed)",
     changed_doc(lambda d: _set_of(d, "OTC-T-0010").update(source_version=4)), None),
    ("time-base-correction-string", "OTC-T-0011's time_base.correction is a string (malformed)",
     changed_doc(lambda d: _set_of(d, "OTC-T-0011")["time_base"].update(correction="utc_mean_start60")), None),
    ("qc-flag-values-not-object", "OTC-T-0002's no_constants set has a qc_flags entry whose values is a list (malformed)",
     changed_doc(lambda d: _set_of(d, "OTC-T-0002", 1)["qc_flags"][0].update(values=[0.4])), None),
    ("qc-flag-value-string", "OTC-T-0002's no_constants set has qc_flags values {\"step_m\": \"0.4\"} (malformed)",
     changed_doc(lambda d: _set_of(d, "OTC-T-0002", 1)["qc_flags"][0].update(values={"step_m": "0.4"})), None),
    ("evidence-not-objects", "OTC-T-0010's time_base.evidence is [1, \"x\"] (malformed)",
     changed_doc(lambda d: _set_of(d, "OTC-T-0010")["time_base"].update(evidence=[1, "x"])), None),
    ("evidence-number-string", "OTC-T-0011's time_base evidence has lag_min \"-30\" (malformed)",
     changed_doc(lambda d: _set_of(d, "OTC-T-0011")["time_base"]["evidence"][0].update(lag_min="-30")), None),
    ("source-version-number", "release.source_versions.gesla is the number 4.1 (malformed)",
     changed_doc(lambda d: d["release"]["source_versions"].update(gesla=4.1)), None),
    ("source-version-null", "release.source_versions.gesla is null (malformed: each value is a string)",
     changed_doc(lambda d: d["release"]["source_versions"].update(gesla=None)), None),
    ("constant-sets-object", "OTC-T-0010's constant_sets is an object (malformed)",
     changed_doc(lambda d: _station(d, "OTC-T-0010").update(constant_sets={}, recommended_set_id=None)), None),
    ("constant-sets-not-objects", "OTC-T-0010's constant_sets is [5] (malformed)",
     changed_doc(lambda d: _station(d, "OTC-T-0010").update(constant_sets=[5], recommended_set_id=None)), None),
    ("constant-sets-null-item", "OTC-T-0010's constant_sets is [null] (malformed)",
     changed_doc(lambda d: _station(d, "OTC-T-0010").update(constant_sets=[None], recommended_set_id=None)), None),
    # numbers that are not finite as a double
    ("lat-overflow-literal", "OTC-T-0010's lat is the literal 1e400 (infinite as a double)",
     changed_doc(lambda d: _station(d, "OTC-T-0010").update(lat=SENTINEL_LAT)), raw_bytes(b"%r" % SENTINEL_LAT, b"1e400")),
    ("lon-overflow-literal", "OTC-T-0010's lon is the literal -1e400 (infinite as a double)",
     changed_doc(lambda d: _station(d, "OTC-T-0010").update(lon=SENTINEL_LON)), raw_bytes(b"%r" % SENTINEL_LON, b"-1e400")),
    ("lat-huge-int", "OTC-T-0010's lat is an integer of 401 digits (infinite as a double)",
     changed_doc(lambda d: _station(d, "OTC-T-0010").update(lat=10 ** 400)), None),
    ("constituent-amplitude-inf", "OTC-T-0010's first constituent has amplitude_m 1e400 (infinite as a double)",
     changed_doc(lambda d: _set_of(d, "OTC-T-0010")["constituents"][0].update(amplitude_m=SENTINEL_AMP)),
     raw_bytes(b"%r" % SENTINEL_AMP, b"1e400")),
    ("constituent-amplitude-huge-int", "OTC-T-0010's first constituent has amplitude_m an integer of 401 digits",
     changed_doc(lambda d: _set_of(d, "OTC-T-0010")["constituents"][0].update(amplitude_m=10 ** 400)), None),
    # text that is not valid Unicode (CR D17)
    ("invalid-utf8", "OTC-T-0010's name has the byte 0xFF (not UTF-8)",
     lambda: [release_doc(BASE)], raw_bytes(b'"Equator Station"', b'"Equator \xffStation"')),
    ("lone-surrogate", "OTC-T-0010's name has the escape \\ud800, an unpaired surrogate (CR D17)",
     lambda: [release_doc(BASE)], raw_bytes(b'"Equator Station"', b'"Equator \\ud800Station"')),
    # repeated ids (CR D5, CR2 DR22)
    ("constituent-name-twice", "OTC-T-0010's set lists the constituent M2 twice (CR2 DR22)",
     changed_doc(_constituent_twice), None),
    ("duplicate-licence-id", "two licences with the licence_id eot20 (D5)",
     changed_doc(lambda d: d["licences"].append(copy.deepcopy(next(x for x in d["licences"] if x["licence_id"] == "eot20")))), None),
    ("tombstone-twice", "the tombstone OTC-T-0005 appears twice (D5)",
     changed_doc(lambda d: d["stations"].append(copy.deepcopy(_station(d, "OTC-T-0005")))), None),
]


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
    # CR D2 b: a licence with a null provider (schema-invalid) loads; the attribution prints its text alone, unmerged
    ("licence-provider-null", "load", "the eot20 licence and a new licence anon have a null provider (malformed 1.0); it must load (CR D2 b)",
     changed_doc(_null_providers), None),
    ("too-new-broken", "reader_too_old", f"min_reader_version {TOO_NEW}, and its data is not valid 1.0 (an unresolved licence): the version gate comes first",
     _too_new_broken, None, {"valid_as_1_0": False}),
    # Cross-SDK rules of review round 2 (PK-R2-06: DR12, DR14, DR15).
    ("sha256-dup-name", "invalid_release", "OTC_20991231.sha256 lists the .jsonl twice, first with a wrong SHA-256, then with the right one (DR14)",
     lambda: [release_doc(BASE)], sha256_dup_name),
    ("sha256-invalid-utf8", "invalid_release", "OTC_20991231.sha256 has a last row whose name has the byte 0xff, which is not UTF-8 (DR14)",
     lambda: [release_doc(BASE)], sha256_invalid_utf8),
    ("sha256-no-json-row", "checksum_mismatch", "OTC_20991231.sha256 and the pointer list the .json.gz but not the .json: an eager download fails with \"not listed\" (DR15)",
     lambda: [release_doc(BASE)], sha256_no_json_row),
    ("pointer-file-no-sha256", "invalid_release", "the pointer and index entry for OTC_20991231.sha256 have no sha256 (schema-invalid, DR12)",
     lambda: [release_doc(BASE)], pointer_file_no_sha256, {"index_invalid": True}),
    # Cross-SDK rules of review round 2 (PK-R2-04, DR6): a time with impossible calendar fields, hour 24, a leap
    # second, or out of range once its offset is applied is malformed, never rolled over; in created or record_span it
    # is invalid_release.
    ("created-impossible", "invalid_release", "release.created is 2099-02-30T00:00:00Z (February has no 30th; DR6)",
     changed_doc(lambda d: d["release"].update(created="2099-02-30T00:00:00Z")), index_honest),
    ("created-leap-second", "invalid_release", "release.created is 2099-12-31T23:59:60Z (a leap second; DR6)",
     changed_doc(lambda d: d["release"].update(created="2099-12-31T23:59:60Z")), index_honest),
    ("created-out-of-range", "invalid_release", "release.created is 0001-01-01T00:00:00+01:00, which is before year 1 in UTC (DR6)",
     changed_doc(lambda d: d["release"].update(created="0001-01-01T00:00:00+01:00")), index_honest),
    ("record-span-feb-31", "invalid_release", "OTC-T-0010's record_span.start is 2090-02-31T00:00:00Z (DR6)",
     changed_doc(lambda d: _station(d, "OTC-T-0010")["constant_sets"][0]["record_span"].update(start="2090-02-31T00:00:00Z")), None),
    ("record-span-feb-29", "invalid_release", "OTC-T-0010's record_span.end is 2097-02-29T12:00:00Z (2097 is not a leap year; DR6)",
     changed_doc(lambda d: _station(d, "OTC-T-0010")["constant_sets"][0]["record_span"].update(end="2097-02-29T12:00:00Z")), None),
    ("record-span-hour-24", "invalid_release", "OTC-T-0010's record_span.end is 2098-12-31T24:00:00Z (hour 24; DR6)",
     changed_doc(lambda d: _station(d, "OTC-T-0010")["constant_sets"][0]["record_span"].update(end="2098-12-31T24:00:00Z")), None),
    ("proto-keys", "load", "format 1.1: an alias system __proto__ and constructor, and a source constructor (JavaScript Object.prototype keys); it must load and keep them",
     changed_doc(_proto_keys), None),
] + [(name, "invalid_release", defect, docs, tamper) for name, defect, docs, tamper in BAD_R2_05] + [
    # K-NC DR104 (SDK spec 4.6 Licence fields): the good release 20991231 with one licence changed, each
    # invalid_release in every form. The reference reader refuses each by the schema ($defs.licence: commercial_use
    # required and boolean; restriction and terms_url strings; both required when commercial_use is false; spdx
    # required on every licence).
    ("licence-commercial-use-missing", "invalid_release", "the noaa licence has no commercial_use (K-NC DR104)",
     changed_doc(lambda d: _licence(d, "noaa").pop("commercial_use")), None),
    ("licence-commercial-use-null", "invalid_release", "the noaa licence's commercial_use is null (K-NC DR104)",
     changed_doc(lambda d: _licence(d, "noaa").update(commercial_use=None)), None),
    ("licence-commercial-use-string", "invalid_release", "the noaa licence's commercial_use is the string \"false\" (K-NC DR104)",
     changed_doc(lambda d: _licence(d, "noaa").update(commercial_use="false")), None),
    ("licence-nc-no-restriction", "invalid_release", "the noaa licence has commercial_use false and terms_url, but no restriction (K-NC DR104)",
     changed_doc(lambda d: _licence(d, "noaa").update(commercial_use=False, terms_url="https://example.org/noaa-terms")), None),
    ("licence-nc-no-terms-url", "invalid_release", "the noaa licence has commercial_use false and restriction, but no terms_url (K-NC DR104)",
     changed_doc(lambda d: _licence(d, "noaa").update(commercial_use=False, restriction="Test: non-commercial use only.")), None),
    ("licence-nc-no-spdx", "invalid_release", "the noaa licence has commercial_use false, restriction and terms_url, but no spdx (K-NC DR104)",
     changed_doc(_nc_no_spdx), None),
    ("licence-restriction-not-string", "invalid_release", "the noaa licence (commercial) has restriction the number 5 (K-NC DR104)",
     changed_doc(lambda d: _licence(d, "noaa").update(restriction=5)), None),
    ("licence-terms-url-not-string", "invalid_release", "the noaa licence (commercial) has terms_url the number 5 (K-NC DR104)",
     changed_doc(lambda d: _licence(d, "noaa").update(terms_url=5)), None),
    ("licence-restriction-null", "invalid_release", "the noaa licence (commercial) has \"restriction\": null (K-NC DR104, CR3 DR71)",
     changed_doc(lambda d: _licence(d, "noaa").update(restriction=None)), None),
    ("licence-terms-url-null", "invalid_release", "the noaa licence (commercial) has \"terms_url\": null (K-NC DR104, CR3 DR71)",
     changed_doc(lambda d: _licence(d, "noaa").update(terms_url=None)), None),
    # K-NC DR105: the licence-provider-null release with anon non-commercial; it loads, as its base does
    ("licence-provider-null-nc", "load", "the licence-provider-null release with the anon licence non-commercial (null provider; K-NC DR105); it must load (CR D2 b)",
     changed_doc(_null_providers_nc), None),
]


# Review round 2, PK-R2-09: values the four SDKs gave different answers for.
def _quantity_null(doc):
    _station(doc, "OTC-T-0020")["constant_sets"][0]["quantity"] = None
    del _station(doc, "OTC-T-0019")["constant_sets"][0]["quantity"]


def _set_id_across_stations(doc):
    st = _station(doc, "OTC-T-0002")
    old, new = "OTC-T-0002/gesla-fit", "OTC-T-0001/gesla-fit"   # not recommended; OTC-T-0001 has a set with this id
    for cs in st["constant_sets"]:
        if cs["set_id"] == old:
            cs["set_id"] = new
    for v in st.get("validation", []):
        if v["set_id"] == old:
            v["set_id"] = new


def _jsonl_lines(extra):
    """A tamper that puts extra lines into the .jsonl: extra maps a line number (0 = before the first station
    line, -1 = at the end, with no line end after it) to the bytes to insert; the digests stay honest."""
    def tamper(files, sums, entry, reuse):
        files = dict(files)
        name = next(n for n in files if n.endswith(".jsonl"))
        lines = files[name].split(b"\n")[:-1]   # each station line ends in \n
        out = b""
        for i, line in enumerate(lines):
            out += extra.get(i, b"") + line + b"\n"
        files[name] = out + extra.get(-1, b"")
        return rehash(files, sums, entry)
    return tamper


# CR2 DR26: a blank .jsonl line holds only ASCII whitespace (SP, HT, LF, VT, FF, CR), the bytes.strip rule
BLANK_ASCII = {1: b"\x0c\n" + b"\x0b\n" + b" \t\x0b\x0c \r\n", 5: b"\r\n", -1: b"\x0c"}


def unknown_enums_doc():
    """Format 1.1 (min_reader_version 1.0) with enum values format 1.0 does not have: a 1.0 reader reads each as
    "other" (spec 7.3), and the filters and stats use that typed value (CR2 DR7)."""
    doc = release_doc(BASE)
    doc["format_version"] = "1.1"
    doc["future_top_level"] = {"note": "added by format 1.1 (test)"}
    doc["release"]["future_release_field"] = "1.1 release field"
    _station(doc, "OTC-T-0014")["type"] = "lighthouse"
    _station(doc, "OTC-T-0015")["constant_sets"][0]["quantity"] = "tidal_stream"
    _station(doc, "OTC-T-0016")["constant_sets"][0]["source_type"] = "satellite"
    return [doc]


def unknown_status_doc():
    """Format 1.1 (min_reader_version 1.0) with a station status format 1.0 does not have (CR2 DR8)."""
    doc = release_doc(BASE)
    doc["format_version"] = "1.1"
    doc["future_top_level"] = {"note": "added by format 1.1 (test)"}
    doc["release"]["future_release_field"] = "1.1 release field"
    _station(doc, "OTC-T-0016")["status"] = "retired"
    return [doc]


def _no_status(doc):
    del _station(doc, "OTC-T-0020")["status"]
    _station(doc, "OTC-T-0019")["status"] = None


BAD += [
    ("unknown-status", "load", "format 1.1: OTC-T-0016's status is retired; a 1.0 reader reads it as other: not a station, not a "
     "tombstone, in no query and no count (CR2 DR8)",
     unknown_status_doc, None),
    ("no-status", "load", "OTC-T-0020's line has no status and OTC-T-0019's has status null (malformed 1.0); both are active "
     "stations (CR2 DR28)",
     changed_doc(_no_status), None),
    ("unknown-enums", "load", "format 1.1: OTC-T-0014's type is lighthouse, OTC-T-0015's recommended set has quantity tidal_stream, "
     "OTC-T-0016's has source_type satellite; each reads as other, and the filters and stats use other (CR2 DR7)",
     unknown_enums_doc, None),
    ("blank-lines", "load", "the .jsonl has lines of only ASCII whitespace (FF, VT, SP HT VT FF SP CR, CR) between station lines "
     "and a last line of one FF with no line end: blank lines, skipped (CR2 DR26)",
     lambda: [release_doc(BASE)], _jsonl_lines(BLANK_ASCII)),
    ("blank-line-nbsp", "invalid_release", "a .jsonl line of one NBSP (U+00A0): not ASCII whitespace, so not blank, and not JSON (CR2 DR26)",
     lambda: [release_doc(BASE)], _jsonl_lines({1: b"\xc2\xa0\n"})),
    ("blank-line-nul", "invalid_release", "a .jsonl line of one NUL byte: not whitespace, so not blank, and not JSON (CR2 DR26)",
     lambda: [release_doc(BASE)], _jsonl_lines({1: b"\x00\n"})),
    ("set-id-across-stations", "invalid_release", "OTC-T-0002's second set has the set_id OTC-T-0001/gesla-fit, a set_id of "
     "OTC-T-0001: a set_id is unique across the release, not only within a station (D5)",
     changed_doc(_set_id_across_stations), None),
    ("quantity-null", "load", "OTC-T-0020's recommended set has quantity null and OTC-T-0019's has no quantity (malformed 1.0); "
     "it must load, and both stations have kind other (orchestrator S3)",
     changed_doc(_quantity_null), None),
]


def no_build_doc():
    doc = release_doc(BASE)
    st = next(s for s in doc["stations"] if s["station_id"] == "OTC-T-0004")
    del st["constant_sets"][0]["provenance"]["build"]
    return doc


def restore_station_build(st):
    """One station (a .jsonl line) with every missing provenance.build put back."""
    st = copy.deepcopy(st)
    for cs in sets_of(st):
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


def nul_doc():
    """A NUL inside alias ids and set_ids, which the schema allows (review round 2, PK-R2-08): OTC-T-0001 of good/'s
    20991231.2 with the xtide alias and the first gesla alias, and both set_ids (so the recommended_set_id and the
    validation rows), holding a NUL. The part before each NUL is another value, which no lookup may match."""
    doc = release_doc(SECOND)
    s1 = next(s for s in doc["stations"] if s["station_id"] == "OTC-T-0001")
    s1["aliases"]["xtide"] = "San\u0000Francisco"
    s1["aliases"]["gesla"][0] = "test-gesla\u00000001a"
    renamed = {"OTC-T-0001/noaa": "OTC-T-0001/no\u0000aa", "OTC-T-0001/gesla-fit": "OTC-T-0001/gesla\u0000fit"}
    for cs in s1["constant_sets"]:
        cs["set_id"] = renamed[cs["set_id"]]
    for v in s1["validation"]:
        v["set_id"] = renamed[v["set_id"]]
    s1["recommended_set_id"] = renamed[s1["recommended_set_id"]]
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


ALIASES_D = "20991231.2"
# a station with aliases in two of the systems that format 1.0 added (DR29: 16 systems): linz and dmi
ALIAS_STATION = ("OTC-T-0171", "Nelson", {"linz": "077NELSON", "dmi": "30017"})


def aliases_doc():
    """A station with a linz and a dmi alias (PK-R2-18, DR29): station_by_alias must find it in both systems."""
    doc = small_doc(ALIASES_D)
    sid, name, aliases = ALIAS_STATION
    doc["stations"].append(gauge_station(sid, name, "NZL", -41.26, 173.28, "Pacific/Auckland", 0.4, aliases=dict(aliases)))
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


KNC_D = "20991231.2"


def knc_doc():
    """The K-NC root (SDK spec 7.1 K-NC fixtures and cases; K-NC DR104 to DR106): the release object, conventions,
    constituents table and astro tables of good 20991231.2, seven licences (two non-commercial, one commercial with
    restriction and terms_url) and ten active stations whose sets are written in the recommendation-rank order of
    the spec 4.2 guarantee, for commercial_only and the non-commercial notice."""
    good = release_doc(SECOND)
    licences = [
        {"licence_id": "noaa", "spdx": "LicenseRef-PublicDomain-USGov", "provider": "Example Ocean Service",
         "attribution": "Synthetic test data in the style of a public-domain US agency.", "commercial_use": True},
        {"licence_id": "kartverket", "spdx": "CC-BY-4.0", "provider": "Example Mapping Authority",
         "attribution": "Synthetic test data, Example Mapping Authority.", "commercial_use": True},
        {"licence_id": "eot20", "spdx": "CC-BY-4.0", "provider": "Example Tide Model Group",
         "attribution": "Example tide model, interpolated by OpenTideConstants tests.", "commercial_use": True},
        {"licence_id": "gesla-derived", "spdx": "CC-BY-4.0", "provider": "Example Gauge Agency via GESLA",
         "attribution": "Contains synthetic test data in the style of GESLA-4.",
         "citation": "Example Gauge Agency (2099). Example sea level records. Test citation.",
         "url": "https://example.org/gesla-test", "commercial_use": True},
        {"licence_id": "nc-test", "spdx": "LicenseRef-NC-Test", "provider": "Example Restricted Agency",
         "attribution": "Synthetic restricted test data.", "commercial_use": False,
         "restriction": "Test: non-commercial use only.", "terms_url": "https://example.org/nc-test-terms"},
        {"licence_id": "nc-test-2", "spdx": "LicenseRef-NC-Test-2", "provider": "Example Restricted Agency",
         "attribution": "Synthetic restricted test data, second licence.", "commercial_use": False,
         "restriction": "Test: non-commercial use only, second licence.", "terms_url": "https://example.org/nc-test-2-terms"},
        {"licence_id": "c-terms", "spdx": "CC-BY-4.0", "provider": "Example Terms Agency",
         "attribution": "Synthetic test data, Example Terms Agency.", "commercial_use": True,
         "restriction": "Test: attribution in the app's about screen.", "terms_url": "https://example.org/c-terms"},
    ]

    def rank_span(g):
        return {"start": "2002-01-01T00:00:00Z", "end": "2020-12-31T23:00:00Z", "good_hours": g}

    def official(sid, suffix, source, licence, g, scale):
        conv = "noaa-greenwich-v1" if source == "noaa" else "otc-greenwich-v1"
        return cset(sid, suffix, source, "official", conv, licence, simple_constituents(scale), record_span=rank_span(g))

    def gauge(sid, suffix, source, licence, g, scale, flagged=False):
        # a flagged set has the time_base flag and annotation of good OTC-T-0001/gesla-fit (not short_record)
        return gauge_set(sid, suffix, simple_constituents(scale), source=source, licence_id=licence,
                         time_base=UNVERIFIED if flagged else VERIFIED, record_span=rank_span(g))

    def no_constants(sid, suffix):
        # as good OTC-T-0002/gesla-fit
        return gauge_set(sid, suffix, [], qc_status="no_constants", no_constants_reason="fit_unusable", good_hours=9000.0,
                         record_issues=[{"issue": "datum_step", "start": "2095-06-01T00:00:00Z", "reason": "a 0.4 m datum step",
                                         "values": {"step_m": 0.4}}],
                         qc_flags=[{"flag": "broken_record", "reason": "no segment gives a usable fit", "values": {"step_m": 0.4}}])

    def current(sid, suffix):
        # as good OTC-T-0019/noaa
        return cset(sid, suffix, "noaa", "official", "noaa-greenwich-v1", "noaa", [], quantity="current",
                    current_bins=current_bins(1.3))

    def model(sid, suffix):
        # as good OTC-T-0007/eot20
        return cset(sid, suffix, "eot20", "model", "otc-greenwich-v1", "eot20", simple_constituents(0.6))

    def station(n, sets, recommended=None, offsets=None):
        sid = f"OTC-T-{n:04d}"
        built = [f(sid) for f in sets]
        kw = {}
        if offsets is not None:
            licence, ref = offsets
            kw["subordinate_offsets"] = {"reference_station_id": ref, "time_offset_high_min": 12, "time_offset_low_min": 20,
                                         "height_offset_high": 1.05, "height_offset_low": 0.98,
                                         "height_adjusted_type": "R", "licence_id": licence}
        st = active(sid, f"KNC {n:04d}", "USA", round(30.0 + (n - 180) * 0.1, 4), -120.0, "America/Los_Angeles", built,
                    type_="subordinate" if offsets is not None else "reference",
                    recommended=None if recommended is None else f"{sid}/{recommended}", **kw)
        if recommended is None:
            st["recommended_set_id"] = None
        return st

    stations = [
        station(181, [lambda s: official(s, "x-nc", "noaa", "nc-test", 150000.0, 1.0),
                      lambda s: gauge(s, "y-flagged", "gesla-fit", "gesla-derived", 140000.0, 0.99, flagged=True),
                      lambda s: gauge(s, "w-ok", "gesla-fit", "gesla-derived", 130000.0, 0.98),
                      lambda s: gauge(s, "v-ok2", "gesla-fit", "gesla-derived", 120000.0, 0.97),
                      lambda s: current(s, "z-current")], recommended="x-nc"),
        station(182, [lambda s: official(s, "c-nc", "nc-agency", "nc-test", 150000.0, 1.0),
                      lambda s: gauge(s, "b-flag", "gesla-fit", "gesla-derived", 140000.0, 0.99, flagged=True),
                      lambda s: no_constants(s, "a-noc")], recommended="c-nc"),
        station(183, [lambda s: official(s, "a-nc", "nc-agency", "nc-test", 150000.0, 1.0),
                      lambda s: no_constants(s, "b-noc"),
                      lambda s: current(s, "c-cur")], recommended="a-nc"),
        station(184, [lambda s: gauge(s, "a-flag", "gesla-fit", "gesla-derived", 150000.0, 1.0, flagged=True),
                      lambda s: gauge(s, "b-ok", "terms-agency", "c-terms", 140000.0, 0.99)], recommended="a-flag"),
        station(185, [lambda s: official(s, "a-noaa", "noaa", "noaa", 150000.0, 1.0)], recommended="a-noaa"),
        station(186, [], offsets=("kartverket", "OTC-T-0185")),
        station(187, [], offsets=("nc-test-2", "OTC-T-0185")),
        station(188, [], offsets=("kartverket", "OTC-T-0181")),
        station(189, [lambda s: model(s, "a-ok")], recommended="a-ok", offsets=("kartverket", "OTC-T-0181")),
        station(190, [lambda s: official(s, "a-nc", "nc-agency", "nc-test", 150000.0, 1.0)], recommended="a-nc",
                offsets=("noaa", "OTC-T-0185")),
    ]
    return {"format_version": FORMAT, "release": good["release"], "conventions": good["conventions"], "licences": licences,
            "constituents": good["constituents"], "astro_tables": good["astro_tables"], "stations": stations}


# --------------------------------------------------------------------------- prediction fixtures (K2b-fixtures)
#
# Prediction spec revision 28, section 6.5: the prediction cases use their own fixture release, root "predict", with
# a made-up astro table A for 2000-2030 and a second one, B, for 2020-2100 used only by the large-amplitude cases;
# the bad prediction fixtures (root "predict-bad/<name>") are copies of it with one change each; "knc-predict" is knc
# with the additions of the commercial_only cases. Every number here is synthetic. The designed stations (close
# roots, New Year) are confirmed by conformance/tests/test_build_fixtures_predict.py, which scans h' (or W) at
# 0.01 s around each designed event with the fixture's own table. No transcendental function is used to build a
# table, so the files are byte-identical on every platform.

PREDICT_D = "20991231.7"
PRED_TABLE = "otc-test-predict-1"             # constituent_table_version of the prediction release
ASTRO_A, ASTRO_A_YEARS = "otc-test-predict-a", (2000, 2030)
ASTRO_B, ASTRO_B_YEARS = "otc-test-predict-b", (2020, 2100)
CONV_G = "predict-greenwich-v1"              # table A
CONV_LOCAL = "predict-local-utc1-v1"         # table A, phases referred to UTC+1 before conversion (local-phase-convention)
CONV_TAMURA = "predict-tamura-v1"            # v0_model tamura_iho2006 (unsupported-convention)
CONV_LARGE = "predict-large-v1"              # table B (the large-amplitude cases)


def _tri(x):
    """A triangle wave of period 1 and range [-1, 1]: a made-up stand-in for the nodal cycle, with no sin or cos."""
    x = x - math.floor(x)
    return 4 * x - 1 if x < 0.5 else 3 - 4 * x


def _hours_in(year):
    return 8784 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 8760


def predict_astro_rows(first, last, rows, jumps=None, fjumps=None):
    """Made-up rows {name: {speed_deg_per_hour, v0u_deg, f}} for first..last. rows: {name: (speed, V0+u of first,
    u amplitude, f amplitude, cycle phase)}. V0+u runs on continuously from one 1 January to the next (speed times
    the hours of the year) plus a made-up u; jumps {(name, year): degrees} adds a step at 1 January of that year (the
    New Year cases); fjumps {(name, year): df} adds df to f from that year on. Rounded like a TCD (0.01, 0.0001)."""
    jumps, fjumps = jumps or {}, fjumps or {}
    out = {}
    for name, (speed, a0, u_amp, f_amp, ph) in rows.items():
        raw = [a0]
        for y in range(first, last):
            du = u_amp * (_tri((y + 1 - 2000) / 18.61 + ph) - _tri((y - 2000) / 18.61 + ph))
            raw.append(raw[-1] + speed * _hours_in(y) + du + jumps.get((name, y + 1), 0.0))
        extra, f = 0.0, []
        for y in range(first, last + 1):
            extra += fjumps.get((name, y), 0.0)
            f.append(round(1.0 + f_amp * _tri((y - 2000) / 18.61 + 0.25 + ph) + extra, 4))
        out[name] = {"speed_deg_per_hour": speed,
                     "v0u_deg": [round(x - 360.0 * math.floor(x / 360.0), 2) % 360.0 for x in raw], "f": f}
    return out


# Table A rows: (speed, V0+u in 2000, u amplitude, f amplitude, cycle phase). MN4 is in no set (astro-negative-speed's
# unused row). The XR* rows are fast made-up constituents for the close-root designs; their f is 1.
PRED_ROWS_A = {
    "M2": (28.9841042, 120.0, 0.5, 0.03, 0.0), "S2": (30.0, 0.0, 0.0, 0.0, 0.0),
    "N2": (28.4397295, 210.0, 0.5, 0.03, 0.1), "K1": (15.0410686, 15.0, 1.0, 0.08, 0.3),
    "O1": (13.9430356, 270.0, 1.0, 0.12, 0.3), "M4": (57.9682084, 240.0, 1.0, 0.06, 0.0),
    "MN4": (57.4238337, 330.0, 1.0, 0.06, 0.1), "M6": (86.9523126, 300.0, 1.5, 0.09, 0.0),
    "XRA": (1800.0, 0.0, 0.0, 0.0, 0.0), "XRB": (4580.0, 0.0, 0.0, 0.0, 0.0), "XRC": (690.0, 0.0, 0.0, 0.0, 0.0),
    "XRD": (64800.0, 0.0, 0.0, 0.0, 0.0), "XRE": (900000.0, 0.0, 0.0, 0.0, 0.0),
    "XRF": (1000000.0, 0.0, 0.0, 0.0, 0.0), "XRG": (740000.0, 0.0, 0.0, 0.0, 0.0),
}
# The table jumps of the New Year cases (spec 6.5): K1 and O1 +5 degrees at 2010 (extremes-new-year-missed), the
# opposite at 2011 (extremes-new-year-doubled), +5 again at 2012 (a slack missed at T) with M2 -3 (a slack doubled);
# M2's f steps by 0.03 at 2013, so the folded curve's year rule shows (subordinate-folded-new-year).
PRED_JUMPS_A = {("K1", 2010): 5.0, ("O1", 2010): 5.0, ("K1", 2011): -4.05, ("O1", 2011): -4.05,
                ("K1", 2012): 5.0, ("O1", 2012): 5.0, ("M2", 2012): -3.0}
PRED_FJUMPS_A = {("M2", 2013): 0.03}
PRED_ROWS_B = {"M2": (28.9841042, 75.0, 0.5, 0.03, 0.0), "K1": (15.0410686, 300.0, 1.0, 0.08, 0.3)}
PRED_DOODSON = {"M2": "255 555", "S2": "273 555", "N2": "245 655", "K1": "165 555", "O1": "145 555", "M4": "455 555",
                "MN4": "445 655", "M6": "655 555"}


def predict_tables():
    a = {"astro_table_id": ASTRO_A, "v0_model": "schureman_tcd", "tables_sha256": sha(ASTRO_A.encode()),
         "generator": "synthetic test values (not congen output)", "first_year": ASTRO_A_YEARS[0],
         "last_year": ASTRO_A_YEARS[1],
         "constituents": predict_astro_rows(*ASTRO_A_YEARS, PRED_ROWS_A, PRED_JUMPS_A, PRED_FJUMPS_A)}
    b = {"astro_table_id": ASTRO_B, "v0_model": "schureman_tcd", "tables_sha256": sha(ASTRO_B.encode()),
         "generator": "synthetic test values (not congen output)", "first_year": ASTRO_B_YEARS[0],
         "last_year": ASTRO_B_YEARS[1], "constituents": predict_astro_rows(*ASTRO_B_YEARS, PRED_ROWS_B)}
    return [a, b]


def _pspeed(name):
    return PRED_ROWS_A[name][0]


def pc(name, amp, phase):
    """A water-level constituent of the prediction release (only the required fields)."""
    return {"name": name, "speed_deg_per_hour": _pspeed(name), "amplitude_m": amp, "phase_deg": phase}


def pcc(name, major, major_phase, minor=0.0, minor_phase=0.0):
    """A current constituent of the prediction release."""
    return {"name": name, "speed_deg_per_hour": _pspeed(name), "major_amplitude_ms": major,
            "major_phase_deg": major_phase, "minor_amplitude_ms": minor, "minor_phase_deg": minor_phase}


def pbin(n, constituents, azimuth=0.0, flood=None, ebb=None, mean_major=None, mean_minor=None, depth=3.0):
    b = {"bin": n, "depth_m": depth, "depth_type": "below_surface", "azimuth_deg": azimuth, "constituents": constituents}
    if flood is not None:
        b["mean_flood_dir_deg"] = flood
    if ebb is not None:
        b["mean_ebb_dir_deg"] = ebb
    if mean_major is not None:
        b["mean_major_ms"] = mean_major
    if mean_minor is not None:
        b["mean_minor_ms"] = mean_minor
    return b


def published(epoch=None, **extra):
    b = {"kind": "published", "method": "source"}
    if epoch is not None:
        b["epoch"] = epoch
    b.update(extra)
    return b


NTDE = {"start": "1983-01-01", "end": "2001-12-31", "name": "NTDE 1983-2001"}
FIRST_REDUCTION = {"kind": "observed", "method": "first_reduction",
                   "epoch": {"start": "2015-01-01", "end": "2016-12-31"},
                   "data_span": {"start": "2015-01-01", "end": "2016-12-31", "months": 24},
                   "uncertainty_m": 0.03, "uncertainty_basis": "calibrated", "flags": ["no_qualified_control"]}


def pgauge(sid, suffix, constituents, **kw):
    """A gauge set (gesla-fit) of the prediction release: as gauge_set, under the prediction convention."""
    return dict(gauge_set(sid, suffix, constituents, **kw), convention_id=CONV_G)


def pset(sid, suffix, constituents, *, source="noaa", source_type="official", convention=CONV_G, licence="noaa",
         quantity="water_level", **extra):
    return cset(sid, suffix, source, source_type, convention, licence, constituents, quantity=quantity, **extra)


def pstation(sid, name, sets, *, tz="America/New_York", recommended: "str | None" = "first", lat=None, type_="reference", **extra):
    """A station of the prediction release. recommended: "first" (its first set), a set_id, or None: no recommended
    set (a subordinate with offsets only, or a reference station whose every set is no_constants; schema rule 6)."""
    n = int(sid[-4:])
    rec = sets[0]["set_id"] if recommended == "first" and sets else recommended
    st = active(sid, name, "USA", lat if lat is not None else round(20.0 + n * 0.01, 4), -70.0, tz, sets,
                type_=type_, recommended=rec, **extra)
    if rec is None:
        st["recommended_set_id"] = None
    return st


def offsets(ref, high_min, low_min, high, low, type_="R", licence="noaa", **extra):
    o = {"reference_station_id": ref, "height_adjusted_type": type_, "licence_id": licence}
    for k, v in (("time_offset_high_min", high_min), ("time_offset_low_min", low_min), ("height_offset_high", high),
                 ("height_offset_low", low)):
        if v is not None:
            o[k] = v
    o.update(extra)
    return o


def subordinate(sid, name, offs, tz="America/New_York"):
    return pstation(sid, name, [], tz=tz, recommended=None, type_="subordinate", subordinate_offsets=offs)


def current_offset(n, ref, ref_bin, **adj):
    o = {"bin": n, "depth_m": 4.0, "depth_type": "below_surface", "reference_station_id": ref, "reference_bin": ref_bin,
         "mean_flood_dir_deg": 45.0, "mean_ebb_dir_deg": 225.0, "time_adj_max_flood_min": 25.0,
         "time_adj_slack_before_ebb_min": -10.0, "time_adj_max_ebb_min": 30.0, "time_adj_slack_before_flood_min": 5.5,
         "flood_amp_ratio": 0.8, "ebb_amp_ratio": 1.1, "licence_id": "noaa"}
    o.update(adj)
    return o


# The designed stations' constants (conformance/tests/test_build_fixtures_predict.py confirms each design).
DESIGN = {
    # extremes-single-constituent: M2 alone, 116 extremes from 2010-03-01 to 2010-03-31
    "single": [("M2", 1.0, 20.903277)],
    # extremes-year-boundary-step: a high 200 s before 2010-01-01, found in the old year's last step
    "year-step": [("M2", 1.0, 333.740149)],
    # extremes-new-year-missed (2010) and extremes-new-year-doubled (2011): K1 and O1
    "new-year": [("K1", 0.8, 352.2128), ("O1", 0.6, 265.731)],
    # extremes-close-high-low: a high and a low 3 min apart in one 6-minute step (2010-04-15 12:00)
    "close-high-low": [("M2", 1.0, 320.346098), ("XRA", 0.00450158158, 0.0)],
    # extremes-close-high-low-high: three extremes in one step (2010-05-03 06:00)
    "close-high-low-high": [("M2", 1.0, 56.066985), ("XRB", 8.77107e-05, 280.476111)],
    # extremes-double-high: two highs 20 min apart, the low between (2010-05-20 18:03)
    "double-high": [("M2", 1.0, 349.390749), ("XRC", 0.00386443, 33.215833)],
    # extremes-sub-second: a high and a low 0.8 s apart on a rising tide (2010-06-07 03:02:21)
    "sub-pair": [("M2", 1.0, 352.105766), ("XRD", 0.00017824434, 295.987498)],
    # a high, a low and a high within 0.9 s, the second high higher (2010-06-20 09:01:10)
    "sub-triple-higher": [("M2", 1.0, 51.88102), ("XRE", 2.06493e-09, 194.125035)],
    # the same with equal heights above the zero (msl_offset_m 1.0; datum zero) (2010-07-03 09:01:10)
    "sub-triple-equal": [("M2", 1e-06, 94.92153), ("XRE", 2.06493e-15, 206.625023)],
}
DESIGN_BINS = {
    # current-events-close-slacks: a weak flood whose W reaches 1.77e-5 m/s, slacks 2 min apart (2010-07-20 12:02:53)
    "close-slacks": ([("M2", 0.5, 128.214673)], -0.497732308964),
    # current-events-sub-second-slacks: two slacks 0.6 s apart (2010-07-30 12:01:10)
    "slack-pair": ([("M2", 0.5, 243.570917)], -0.497749999557724),
    # three slacks within 0.9 s, flood-ebb-flood (2010-08-09 06:01:10)
    "slack-triple": ([("M2", 0.5, 275.853715), ("XRF", 3.60671e-05, 338.472197)], None),
    # five slacks, each 0.82-0.88 s after the one before (one cluster, five leaves), on a flat crossing: M2 and M6 make
    # W = (4/3) F U sin^3, and the ripple XRG crosses it five times (2010-01-20 06:02:21)
    "slack-five": ([("M2", 0.5, 137.10115), ("M6", 0.168170146632, 351.30345), ("XRG", 4.93502e-11, 28.694425)], None),
    # current-events-new-year-slack: missed at 2012-01-01 (K1, O1), doubled (M2)
    "ny-slack-missed": ([("K1", 0.6, 107.276412), ("O1", 0.4, 57.840927)], None),
    "ny-slack-doubled": ([("M2", 0.8, 265.250366)], None),
}


# The windows of the designed cases (and the centres of the sub-second ones), shared with predict_calls.json and with
# conformance/tests/test_build_fixtures_predict.py, which confirms each design over them.
PW = {
    "single": ("2010-03-01T00:00:00Z", "2010-03-31T00:00:00Z"),
    "large-m2": ("2099-12-20T00:00:00Z", "2099-12-25T00:00:00Z"),
    "large-k1": ("2025-12-22T00:00:00Z", "2025-12-23T00:00:00Z"),
    "close-high-low": ("2010-04-15T12:00:00Z", "2010-04-15T12:06:00Z"),
    "close-high-low-high": ("2010-05-03T06:00:00Z", "2010-05-03T06:06:00Z"),
    "double-high": ("2010-05-20T17:03:00Z", "2010-05-20T19:03:00Z"),
    "sub-second-pair": ("2010-06-07T03:02:11Z", "2010-06-07T03:02:31Z", "2010-06-07T03:02:21.44375Z"),
    "sub-second-triple-higher": ("2010-06-20T09:01:00Z", "2010-06-20T09:01:20Z", "2010-06-20T09:01:10.6665Z"),
    "sub-second-triple-equal": ("2010-07-03T09:01:00Z", "2010-07-03T09:01:20Z", "2010-07-03T09:01:10.6665Z"),
    "close-slacks": ("2010-07-20T12:00:00Z", "2010-07-20T12:06:00Z"),
    # the centres of current-events-sub-second-slacks, bins 2, 3 and 4 of OTC-P-0020 (each window is centre +- 10 s)
    "sub-second-slacks": ("2010-07-30T12:01:10.3625Z", "2010-08-09T06:01:10.6625Z", "2010-01-20T06:02:20.975Z"),
    "current-events-weak": ("2010-03-01T00:00:00Z", "2010-03-03T00:00:00Z"),
    "currents": ("2010-03-01T00:00:00Z", "2010-03-02T00:00:00Z"),
}


def _design(key):
    return [pc(n, a, p) for n, a, p in DESIGN[key]]


def _design_bin(n, key):
    terms, mean = DESIGN_BINS[key]
    return pbin(n, [pcc(name, a, p) for name, a, p in terms], azimuth=0.0, flood=0.0, ebb=180.0, mean_major=mean)


P_BASIC = "OTC-P-0001"


def predict_stations():
    S = []
    # M2's set speed is 8e-8 deg/h off the table's (within the 1e-7 the build allows, spec 3.3): an SDK that takes the
    # speed from the set, not the table (spec 4.3), is off by ~2e-6 m in March and more later in the year
    basic_consts = [dict(pc("M2", 0.9, 101.25), speed_deg_per_hour=28.98410428), pc("S2", 0.25, 130.5), pc("N2", 0.18, 85.0), pc("K1", 0.35, 210.75),
                    pc("O1", 0.25, 195.0), pc("M4", 0.04, 20.0)]
    basic_datum = {"msl_offset_m": 1.12, "zero": "chart_datum", "zero_name": "MLLW", "chart_datum": "mllw",
                   "named": {"mhhw": 2.31, "mhw": 2.05, "msl": 1.12, "mtl": 1.1, "mlw": 0.15, "mllw": 0.0, "lat": -0.38,
                             "otc_lat": -0.41},
                   "basis": {"mhhw": published(NTDE), "mhw": published(NTDE), "msl": published(NTDE),
                             "mtl": published(NTDE), "mlw": published(NTDE),
                             "mllw": published(NTDE, uncertainty_m=0.01, uncertainty_basis="source",
                                               control={"source_id": "9990001"}),
                             "lat": published(),
                             "otc_lat": {"kind": "computed", "method": "harmonic_extremes",
                                         "epoch": {"start": "2020-01-01", "end": "2038-12-31", "name": "OTC LAT 2020-2038"},
                                         "uncertainty_m": 0.02, "uncertainty_basis": "calibrated"}}}
    S.append(pstation(P_BASIC, "Prediction Basic", [
        pset(P_BASIC, "noaa", basic_consts, datum=basic_datum),
        pgauge(P_BASIC, "gesla-fit", [pc("M2", 0.88, 102.0), pc("K1", 0.34, 211.5)], datum={"msl_offset_m": 3.4, "zero": "gauge_zero"})]))
    oslo = [pc("M2", 0.6, 300.0), pc("S2", 0.2, 340.0), pc("K1", 0.1, 120.0), pc("O1", 0.05, 80.0)]
    S.append(pstation("OTC-P-0002", "Prediction Oslo", [pset("OTC-P-0002", "noaa", oslo)], tz="Europe/Oslo"))
    S.append(pstation("OTC-P-0003", "Prediction Lord Howe", [pset("OTC-P-0003", "noaa", oslo)], tz="Australia/Lord_Howe"))
    lp = [pc("M2", 0.7, 45.5), pc("S2", 0.2, 80.25), pc("K1", 0.15, 300.0)]
    S.append(pstation("OTC-P-0004", "Prediction Local Phase", [
        pset("OTC-P-0004", "kartverket", lp, source="kartverket", convention=CONV_LOCAL, licence="kartverket"),
        pset("OTC-P-0004", "greenwich", lp)], tz="Europe/Oslo"))
    S.append(pstation("OTC-P-0005", "Prediction Single M2", [pset("OTC-P-0005", "noaa", _design("single"))]))
    S.append(pstation("OTC-P-0006", "Prediction Year Step", [pset("OTC-P-0006", "noaa", _design("year-step"))]))
    S.append(pstation("OTC-P-0007", "Prediction New Year", [pset("OTC-P-0007", "noaa", _design("new-year"))]))
    S.append(pstation("OTC-P-0008", "Prediction Close High Low", [pset("OTC-P-0008", "noaa", _design("close-high-low"))]))
    S.append(pstation("OTC-P-0009", "Prediction Close Triple", [pset("OTC-P-0009", "noaa", _design("close-high-low-high"))]))
    S.append(pstation("OTC-P-0010", "Prediction Double High", [pset("OTC-P-0010", "noaa", _design("double-high"))]))
    S.append(pstation("OTC-P-0011", "Prediction Sub Second", [
        pset("OTC-P-0011", "pair", _design("sub-pair")),
        pset("OTC-P-0011", "triple-higher", _design("sub-triple-higher")),
        pset("OTC-P-0011", "triple-equal", _design("sub-triple-equal"), datum={"msl_offset_m": 1.0, "zero": "unknown"})]))
    S.append(pstation("OTC-P-0012", "Prediction Large Amplitude", [
        pset("OTC-P-0012", "m2-5m", [{"name": "M2", "speed_deg_per_hour": 28.9841042, "amplitude_m": 5.0, "phase_deg": 17.45}],
             convention=CONV_LARGE),
        pset("OTC-P-0012", "m2-7m5", [{"name": "M2", "speed_deg_per_hour": 28.9841042, "amplitude_m": 7.5, "phase_deg": 17.45}],
             convention=CONV_LARGE),
        pset("OTC-P-0012", "k1-40m", [{"name": "K1", "speed_deg_per_hour": 15.0410686, "amplitude_m": 40.0, "phase_deg": 233.0}],
             convention=CONV_LARGE)]))
    big = lambda name, speed, amp, ph: {"name": name, "speed_deg_per_hour": speed, "major_amplitude_ms": amp,
                                        "major_phase_deg": ph, "minor_amplitude_ms": 0.0, "minor_phase_deg": 0.0}
    S.append(pstation("OTC-P-0013", "Prediction Large Amplitude Current", [
        pset("OTC-P-0013", "noaa", [], quantity="current", convention=CONV_LARGE,
             current_bins=[pbin(1, [big("M2", 28.9841042, 5.0, 17.45)]), pbin(2, [big("M2", 28.9841042, 7.5, 17.45)]),
                           pbin(3, [big("K1", 15.0410686, 40.0, 233.0)])])]))
    S.append(pstation("OTC-P-0014", "Prediction No Constants", [
        pgauge("OTC-P-0014", "gesla-fit", [], qc_status="no_constants", no_constants_reason="fit_unusable",
                  good_hours=9000.0,
                  record_issues=[{"issue": "datum_step", "start": "2009-06-01T00:00:00Z", "reason": "a 0.4 m datum step",
                                  "values": {"step_m": 0.4}}],
                  qc_flags=[{"flag": "broken_record", "reason": "no segment gives a usable fit", "values": {"step_m": 0.4}}])],
        recommended=None))
    S.append(pstation("OTC-P-0015", "Prediction Tamura", [pset("OTC-P-0015", "noaa", [pc("M2", 0.5, 10.0)],
                                                                convention=CONV_TAMURA)]))
    basic_bin = lambda n, k: pbin(n, [pcc("M2", round(0.9 * k, 4), 320.0, round(0.05 * k, 4), 50.0),
                                      pcc("S2", round(0.25 * k, 4), 345.0, round(0.02 * k, 4), 80.0),
                                      pcc("K1", round(0.15 * k, 4), 25.0, round(0.01 * k, 4), 110.0),
                                      pcc("O1", round(0.1 * k, 4), 10.0, round(0.005 * k, 4), 95.0)],
                                  azimuth=40.0, flood=40.0, ebb=220.0, mean_major=0.1, mean_minor=-0.02, depth=3.0 * n)
    S.append(pstation("OTC-P-0016", "Prediction Current", [
        pset("OTC-P-0016", "noaa", [], quantity="current", current_bins=[basic_bin(1, 1.0), basic_bin(2, 0.8), basic_bin(3, 0.6)])],
        default_current_bin=2))
    S.append(pstation("OTC-P-0017", "Prediction Current Shapes", [
        pset("OTC-P-0017", "noaa", [], quantity="current", current_bins=[
            pbin(1, [pcc("M2", 0.5, 100.0, 0.08, 10.0)], azimuth=70.0, flood=70.0, ebb=250.0, mean_major=0.35, mean_minor=0.12),
            pbin(2, [pcc("M2", 0.6, 200.0, 0.3, 290.0), pcc("K1", 0.2, 40.0, 0.1, 130.0)], azimuth=120.0, flood=120.0, ebb=300.0),
            pbin(3, [pcc("M2", 0.7, 60.0, 0.1, 150.0)], azimuth=30.0, flood=210.0, ebb=30.0),
            pbin(4, [pcc("M2", 0.0, 0.0, 0.0, 0.0)], azimuth=0.0),
            pbin(5, [pcc("M2", 0.2, 75.0)], azimuth=180.0, flood=0.0, ebb=180.0, mean_major=-0.5)])]))
    S.append(pstation("OTC-P-0018", "Prediction Current Lowest Bin", [
        pset("OTC-P-0018", "noaa", [], quantity="current", current_bins=[
            pbin(3, [pcc("M2", 0.4, 10.0, 0.02, 100.0)], azimuth=90.0, flood=90.0, ebb=270.0),
            pbin(1, [pcc("M2", 0.3, 50.0, 0.01, 140.0)], azimuth=90.0, flood=90.0, ebb=270.0)])]))
    S.append(pstation("OTC-P-0019", "Prediction Weak Current", [
        pset("OTC-P-0019", "noaa", [], quantity="current", current_bins=[
            pbin(1, [pcc("M2", 0.4, 30.0, 0.02, 120.0), pcc("K1", 0.3, 120.0, 0.01, 290.0)], azimuth=0.0, flood=0.0, ebb=180.0,
                 mean_major=-0.3)])]))
    S.append(pstation("OTC-P-0020", "Prediction Slacks", [
        pset("OTC-P-0020", "noaa", [], quantity="current", current_bins=[
            _design_bin(1, "close-slacks"), _design_bin(2, "slack-pair"), _design_bin(3, "slack-triple"),
            _design_bin(4, "slack-five")])]))
    S.append(pstation("OTC-P-0021", "Prediction New Year Slacks", [
        pset("OTC-P-0021", "noaa", [], quantity="current", current_bins=[
            _design_bin(1, "ny-slack-missed"), _design_bin(2, "ny-slack-doubled")])]))
    # subordinate tide stations by NOAA's event method (differing offsets), reference OTC-P-0001
    S.append(subordinate("OTC-P-0030", "Sub Ratio", offsets(P_BASIC, 12, 20, 1.05, 0.98)))
    S.append(subordinate("OTC-P-0031", "Sub Additive", offsets(P_BASIC, -5, 4, 0.12, -0.05, "A")))
    S.append(subordinate("OTC-P-0032", "Sub Missing Offsets", offsets(P_BASIC, 15, None, None, 0.9)))
    S.append(subordinate("OTC-P-0033", "Sub Order Swap", offsets(P_BASIC, 250, -150, 1.0, 1.0)))
    S.append(subordinate("OTC-P-0034", "Sub Fractional", offsets(P_BASIC, 12.5, -7.25, 1.0, 1.0)))
    # folded (equal offsets)
    sub_datum = {"chart_datum": "mllw", "named": {"mhhw": 1.9, "mhw": 1.7, "msl": 0.95, "mllw": 0.0},
                 "basis": {k: published() for k in ("mhhw", "mhw", "msl", "mllw")}}
    S.append(subordinate("OTC-P-0035", "Folded Ratio", offsets(P_BASIC, 37, 37, 0.9, 0.9, datum=sub_datum)))
    S.append(subordinate("OTC-P-0036", "Folded Additive", offsets(P_BASIC, -12, -12, 0.15, 0.15, "A")))
    S.append(subordinate("OTC-P-0037", "Folded New Year", offsets(P_BASIC, 40, 40, 1.1, 1.1)))
    S.append(subordinate("OTC-P-0038", "Zero Ratio Folded", offsets(P_BASIC, 30, 30, 0, 0)))
    S.append(subordinate("OTC-P-0039", "Negative Ratio Folded", offsets(P_BASIC, 30, 30, -0.5, -0.5)))
    S.append(subordinate("OTC-P-0040", "Zero Ratio Differing", offsets(P_BASIC, 10, 20, 0, 0.9)))
    S.append(subordinate("OTC-P-0041", "Negative Ratio Differing", offsets(P_BASIC, 10, 20, -0.5, 0.9)))
    # reference-set-file-order: gesla-fit (recommended), noaa no_constants, noaa flagged, noaa ok
    chart = lambda msl: {"msl_offset_m": msl, "zero": "chart_datum", "zero_name": "MLLW", "chart_datum": "mllw",
                         "named": {"mllw": 0.0, "mhw": round(msl + 0.8, 4)},
                         "basis": {"mllw": published(NTDE), "mhw": published(NTDE)}}
    S.append(pstation("OTC-P-0042", "Reference Order", [
        pgauge("OTC-P-0042", "gesla-fit", [pc("M2", 0.8, 70.0), pc("K1", 0.2, 150.0)]),
        pset("OTC-P-0042", "noaa-a-noc", [], qc_status="no_constants", no_constants_reason="fit_unusable",
             qc_flags=[{"flag": "broken_record", "reason": "test: no usable constants"}],
             record_issues=[{"issue": "spikes", "reason": "test: spikes"}]),
        pset("OTC-P-0042", "noaa-b-flagged", [pc("M2", 0.81, 71.0), pc("K1", 0.21, 151.0)], qc_status="flagged",
             qc_flags=[{"flag": "sibling_disagreement", "reason": "test: disagrees with a nearby station"}],
             datum=chart(0.95)),
        pset("OTC-P-0042", "noaa-c-ok", [pc("M2", 0.82, 72.0), pc("K1", 0.22, 152.0)], datum=chart(0.97))]))
    S.append(subordinate("OTC-P-0043", "Sub Reference Order", offsets("OTC-P-0042", 10, 25, 1.02, 0.97)))
    S.append(pstation("OTC-P-0044", "Reference No Chart", [
        pset("OTC-P-0044", "noaa", [pc("M2", 0.6, 30.0)], datum={"msl_offset_m": 0.9, "named": {"mhhw": 1.8},
                                                               "basis": {"mhhw": published(NTDE)}})]))
    S.append(subordinate("OTC-P-0045", "Sub No Chart", offsets("OTC-P-0044", 10, 25, 1.02, 0.97)))
    S.append(pstation("OTC-P-0046", "Reference Computed Chart", [
        pset("OTC-P-0046", "noaa", [pc("M2", 0.6, 30.0)],
             datum={"msl_offset_m": 1.0, "zero": "chart_datum", "chart_datum": "lat", "named": {"lat": 0.0},
                    "basis": {"lat": {"kind": "computed", "method": "harmonic_extremes",
                                      "epoch": {"start": "2020-01-01", "end": "2038-12-31", "name": "OTC LAT 2020-2038"},
                                      "uncertainty_m": 0.02, "uncertainty_basis": "calibrated"}}})]))
    S.append(subordinate("OTC-P-0047", "Sub Computed Chart", offsets("OTC-P-0046", 10, 25, 1.02, 0.97)))
    S.append(pstation("OTC-P-0048", "Reference Gauge Only", [
        pgauge("OTC-P-0048", "gesla-fit", [pc("M2", 0.6, 30.0)],
                  datum={"msl_offset_m": 2.0, "zero": "gauge_zero", "chart_datum": "mllw", "named": {"mllw": 1.05},
                         "basis": {"mllw": dict(FIRST_REDUCTION)}})]))
    S.append(subordinate("OTC-P-0049", "Sub Wrong Source", offsets("OTC-P-0048", 10, 25, 1.02, 0.97)))
    # subordinate current stations, reference OTC-P-0016 bin 1
    S.append(pstation("OTC-P-0050", "Sub Current", [], recommended=None, type_="subordinate",
                      current_offsets=[current_offset(1, "OTC-P-0016", 1)]))
    S.append(pstation("OTC-P-0051", "Sub Current Null", [], recommended=None, type_="subordinate",
                      current_offsets=[current_offset(1, "OTC-P-0016", 1, time_adj_slack_before_ebb_min=None,
                                                      ebb_amp_ratio=None)]))
    # datums
    S.append(pstation("OTC-P-0052", "Prediction Vertical Zero", [
        pset("OTC-P-0052", "rws", [pc("M2", 0.8, 60.0), pc("M4", 0.1, 200.0)], source="rws",
             datum={"msl_offset_m": 0.08, "zero": "vertical_datum", "zero_name": "NAP", "named": {"nap": 0.0, "mhw": 1.02},
                    "basis": {"nap": published(), "mhw": published()}})], tz="Europe/Amsterdam"))
    du = [pc("M2", 0.5, 120.0)]
    S.append(pstation("OTC-P-0053", "Prediction Datum Unavailable", [
        pset("OTC-P-0053", "no-datum", du),
        pset("OTC-P-0053", "no-msl", du, datum={"chart_datum": "mllw", "named": {"mllw": -0.9}, "basis": {"mllw": published()}}),
        pset("OTC-P-0053", "no-chart", du, datum={"msl_offset_m": 0.9, "named": {"mhw": 1.6}, "basis": {"mhw": published()}})]))
    S.append(pstation("OTC-P-0054", "Prediction Mixed Kinds", [
        pset("OTC-P-0054", "noaa", [pc("M2", 0.7, 40.0)],
             datum={"msl_offset_m": 1.0, "zero": "chart_datum", "zero_name": "MLLW", "chart_datum": "mllw",
                    "named": {"mhhw": 2.0, "mhw": 1.8, "mlw": 0.25, "mllw": 0.0},
                    "basis": {"mhhw": published(NTDE), "mhw": published(NTDE), "mlw": dict(FIRST_REDUCTION),
                              "mllw": dict(FIRST_REDUCTION)}})]))
    # subordinate-reference-no-usable-set (spec rev 28): the reference is active, its only noaa water-level set is
    # no_constants, and its gesla-fit set does not count (the offsets' source is noaa)
    S.append(pstation("OTC-P-0055", "Reference No Usable Set", [
        pgauge("OTC-P-0055", "gesla-fit", [pc("M2", 0.7, 50.0), pc("K1", 0.2, 140.0)]),
        pset("OTC-P-0055", "noaa", [], qc_status="no_constants", no_constants_reason="fit_unusable",
             qc_flags=[{"flag": "broken_record", "reason": "test: no usable constants"}],
             record_issues=[{"issue": "spikes", "reason": "test: spikes"}])]))
    S.append(subordinate("OTC-P-0056", "Sub No Usable Set Folded", offsets("OTC-P-0055", 15, 15, 0.95, 0.95)))
    S.append(subordinate("OTC-P-0057", "Sub No Usable Set Differing", offsets("OTC-P-0055", 10, 25, 1.02, 0.97)))
    # subordinate-current-reference-no-set: the current reference is active with no usable current set
    S.append(pstation("OTC-P-0058", "Reference No Current Set", [
        pset("OTC-P-0058", "noaa", [], quantity="current", qc_status="no_constants", no_constants_reason="fit_unusable",
             qc_flags=[{"flag": "broken_record", "reason": "test: no usable constants"}],
             record_issues=[{"issue": "spikes", "reason": "test: spikes"}])], recommended=None))
    S.append(pstation("OTC-P-0059", "Sub Current No Reference Set", [], recommended=None, type_="subordinate",
                      current_offsets=[current_offset(1, "OTC-P-0058", 1)]))
    # a reference whose zero is not its chart datum (named[chart_datum] = 0.85): chart = msl_offset_m - 0.85 (spec 4.5)
    S.append(pstation("OTC-P-0060", "Reference Gauge Zero", [
        pset("OTC-P-0060", "noaa", [pc("M2", 0.95, 140.0), pc("S2", 0.3, 170.0), pc("K1", 0.3, 230.0), pc("O1", 0.2, 210.0)],
             datum={"msl_offset_m": 2.4, "zero": "gauge_zero", "zero_name": "STND", "chart_datum": "mllw",
                    "named": {"mllw": 0.85, "mhhw": 3.9}, "basis": {"mllw": published(NTDE), "mhhw": published(NTDE)}})]))
    # the event path (differing offsets) on that reference, with the subordinate's own datum (spec 4.8 step 5)
    S.append(subordinate("OTC-P-0061", "Sub Gauge Zero Reference", offsets("OTC-P-0060", 18, 27, 1.04, 0.96, datum={
        "chart_datum": "mllw", "named": {"mllw": 0.0, "mhhw": 1.6, "msl": 0.8},
        "basis": {k: published() for k in ("mllw", "mhhw", "msl")}})))
    # offsets with a fractional second (12.345 min = 740.7 s, -7.29 min = -437.4 s): r + offset is rounded once (4.8 step 3)
    S.append(subordinate("OTC-P-0062", "Sub Fractional Seconds", offsets(P_BASIC, 12.345, -7.29, 1.0, 1.0)))
    # a removed station (the current-reference-removed bad fixture points a current_offsets entry at it)
    S.append(tombstone("OTC-P-0097", "Removed Current Reference", PREDICT_D, "merged", "OTC-P-0016",
                       "Merged into OTC-P-0016 (test tombstone)."))
    return S


def predict_doc():
    tables = predict_tables()
    names = sorted({n for t in tables for n in t["constituents"]})
    sp = {**{n: PRED_ROWS_A[n][0] for n in PRED_ROWS_A}}
    table = [dict({"constituent_table_version": PRED_TABLE, "name": n, "speed_deg_per_hour": sp[n]},
                  **({"doodson": PRED_DOODSON[n]} if n in PRED_DOODSON else {})) for n in names]
    conventions = [
        {"convention_id": CONV_G, "phase_reference": "greenwich_utc", "v0_model": "schureman_tcd",
         "nodal_handling": "f_u_at_prediction", "constituent_table_version": PRED_TABLE,
         "tables_sha256": sha(ASTRO_A.encode()), "astro_table_id": ASTRO_A},
        {"convention_id": CONV_LOCAL, "phase_reference": "local", "utc_offset_hours": 1, "v0_model": "schureman_tcd",
         "nodal_handling": "f_u_at_prediction", "constituent_table_version": PRED_TABLE, "astro_table_id": ASTRO_A},
        {"convention_id": CONV_TAMURA, "phase_reference": "greenwich_utc", "v0_model": "tamura_iho2006",
         "nodal_handling": "f_u_at_prediction", "constituent_table_version": PRED_TABLE, "astro_table_id": ASTRO_A},
        {"convention_id": CONV_LARGE, "phase_reference": "greenwich_utc", "v0_model": "schureman_tcd",
         "nodal_handling": "f_u_at_prediction", "constituent_table_version": PRED_TABLE,
         "tables_sha256": sha(ASTRO_B.encode()), "astro_table_id": ASTRO_B},
    ]
    licences = [
        {"licence_id": "noaa", "spdx": "LicenseRef-PublicDomain-USGov", "provider": "Example Ocean Service",
         "attribution": "Synthetic test data in the style of a public-domain US agency.", "commercial_use": True},
        {"licence_id": "kartverket", "spdx": "CC-BY-4.0", "provider": "Example Mapping Authority",
         "attribution": "Synthetic test data, Example Mapping Authority.", "commercial_use": True},
        {"licence_id": "gesla-derived", "spdx": "CC-BY-4.0", "provider": "Example Gauge Agency via GESLA",
         "attribution": "Contains synthetic test data in the style of GESLA-4.", "commercial_use": True},
    ]
    stations = predict_stations()
    stations.sort(key=lambda s: s["station_id"])
    return {"format_version": FORMAT,
            "release": {"datestamp": PREDICT_D, "created": "2099-12-31T00:00:00Z", "min_reader_version": FORMAT,
                        "fit_min_good_hours": 360, "concept_doi": None,
                        "source_versions": {"gesla": "4.1", "kartverket": "20991231", "noaa": "20991231"}},
            "conventions": conventions, "licences": licences, "constituents": table, "astro_tables": tables,
            "stations": stations}


def _pred_change(change):
    """A copy of the prediction release with one change (a JSON round trip: the builders share objects)."""
    def make():
        doc = json.loads(json.dumps(predict_doc()))
        change(doc)
        return [doc]
    return make


def _pred_table(doc, tid):
    return next(t for t in doc["astro_tables"] if t["astro_table_id"] == tid)


def _no_astro_table(doc):
    doc["astro_tables"] = [t for t in doc["astro_tables"] if t["astro_table_id"] != ASTRO_A]
    next(c for c in doc["conventions"] if c["convention_id"] == CONV_LOCAL).pop("astro_table_id")


def _unknown_adjusted_type(doc):
    doc["format_version"] = "1.1"   # min_reader_version stays 1.0: a value from a newer minor, read as other (SDK spec 7.3)
    doc["future_top_level"] = {"note": "added by format 1.1 (test)"}
    doc["release"]["future_release_field"] = "1.1 release field"
    for sid in ("OTC-P-0035", "OTC-P-0030", "OTC-P-0049"):
        _station(doc, sid)["subordinate_offsets"]["height_adjusted_type"] = "X"


# The bad prediction fixtures (spec 6.5): (name, defect, docs). Each is the prediction release with one change. An
# SDK loads each (it reads astro_tables and the constants only when it predicts, and it is a tolerant reader of range
# faults, spec 4.2a, 6.1); the reference reader loads it with that tolerance listed.
PREDICT_BAD = [
    ("no-astro-table", f"table {ASTRO_A} is not in astro_tables, so {CONV_G} names a table that is absent, and "
     f"{CONV_LOCAL} has no astro_table_id (schema-invalid; it loads, and fails when it predicts: no_astro_table)",
     _pred_change(_no_astro_table)),
    ("unsupported-constituent", f"table {ASTRO_A} has no M4 row; OTC-P-0001/noaa uses M4",
     _pred_change(lambda d: _pred_table(d, ASTRO_A)["constituents"].pop("M4"))),
    ("astro-negative-speed", f"table {ASTRO_A}'s M2 row has speed_deg_per_hour -28.9841042",
     _pred_change(lambda d: _pred_table(d, ASTRO_A)["constituents"]["M2"].update(speed_deg_per_hour=-28.9841042))),
    ("astro-negative-speed-unused", f"table {ASTRO_A}'s MN4 row, which no set uses, has speed_deg_per_hour -57.4238337",
     _pred_change(lambda d: _pred_table(d, ASTRO_A)["constituents"]["MN4"].update(speed_deg_per_hour=-57.4238337))),
    ("astro-short-v0u", f"table {ASTRO_A}'s M2 row has a v0u_deg array one entry short (30 values for 31 years)",
     _pred_change(lambda d: _pred_table(d, ASTRO_A)["constituents"]["M2"]["v0u_deg"].pop())),
    ("extremes-negative-amplitude", "OTC-P-0005's M2 amplitude_m is -1.0 (below the schema's minimum 0)",
     _pred_change(lambda d: _set_of(d, "OTC-P-0005")["constituents"][0].update(amplitude_m=-1.0))),
    ("current-reference-missing", "OTC-P-0059's current_offsets entry names reference station OTC-P-9999, which is not in "
     "the release (a build-check fault; format 1.0 keeps current_offsets raw, so an SDK loads it, spec 4.9 step 1)",
     _pred_change(lambda d: _station(d, "OTC-P-0059")["current_offsets"][0].update(reference_station_id="OTC-P-9999"))),
    ("current-reference-removed", "OTC-P-0059's current_offsets entry names reference station OTC-P-0097, a tombstone (a "
     "build-check fault; format 1.0 keeps current_offsets raw, so an SDK loads it, spec 4.9 step 1)",
     _pred_change(lambda d: _station(d, "OTC-P-0059")["current_offsets"][0].update(reference_station_id="OTC-P-0097"))),
    ("unknown-adjusted-type", "format 1.1: height_adjusted_type X (read as other) at OTC-P-0035 (equal offsets), "
     "OTC-P-0030 (differing offsets) and OTC-P-0049 (whose reference has no noaa set)",
     _pred_change(_unknown_adjusted_type)),
]


KNC_PREDICT_CHART = {"msl_offset_m": 1.0, "zero": "chart_datum", "zero_name": "MLLW", "chart_datum": "mllw",
                     "named": {"mllw": 0.0}, "basis": {"mllw": {"kind": "published", "method": "source"}}}


def knc_predict_doc():
    """knc (release 20991231.2, the same licences, stations and set order) with the additions of spec 6.5's
    commercial_only prediction cases only: a published mllw chart datum on OTC-T-0185/a-noaa and OTC-T-0181/x-nc;
    equal offsets (R, k = 0.9, +20 min) at OTC-T-0186, 0187, 0188 and 0190; and two subordinate current stations
    OTC-T-0191 (entry licence nc-test) and OTC-T-0192 (noaa), bin 1 on OTC-T-0181 bin 1. knc keeps its hashes."""
    doc = json.loads(json.dumps(knc_doc()))
    _set_of(doc, "OTC-T-0185")["datum"] = copy.deepcopy(KNC_PREDICT_CHART)
    _set_of(doc, "OTC-T-0181")["datum"] = copy.deepcopy(KNC_PREDICT_CHART)
    for sid in ("OTC-T-0186", "OTC-T-0187", "OTC-T-0188", "OTC-T-0190"):
        _station(doc, sid)["subordinate_offsets"].update(time_offset_high_min=20, time_offset_low_min=20,
                                                         height_offset_high=0.9, height_offset_low=0.9)
    for n, licence in ((191, "nc-test"), (192, "noaa")):
        sid = f"OTC-T-{n:04d}"
        st = active(sid, f"KNC {n:04d}", "USA", round(30.0 + (n - 180) * 0.1, 4), -120.0, "America/Los_Angeles", [],
                    type_="subordinate")
        st["current_offsets"] = [{"bin": 1, "depth_m": 4.0, "depth_type": "below_surface",
                                  "reference_station_id": "OTC-T-0181", "reference_bin": 1,
                                  "mean_flood_dir_deg": 45.0, "mean_ebb_dir_deg": 225.0,
                                  "time_adj_max_flood_min": 15.0, "time_adj_slack_before_ebb_min": -8.0,
                                  "time_adj_max_ebb_min": 20.0, "time_adj_slack_before_flood_min": 6.0,
                                  "flood_amp_ratio": 0.9, "ebb_amp_ratio": 1.05, "licence_id": licence}]
        doc["stations"].append(st)
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
    ("values-nul", lambda: [nul_doc()], {}, (),
     {"releases": [SECOND], "latest": SECOND, "expect": "load", "defect": None,
      "note": "a NUL inside alias ids, set_ids and the recommended_set_id of OTC-T-0001"}),
    ("fold", lambda: [fold_doc()], {}, (),
     {"releases": [FOLD_D], "latest": FOLD_D, "expect": "load", "defect": None, "note": "station names for the D12 fold rules"}),
    ("aliases", lambda: [aliases_doc()], {}, (),
     {"releases": [ALIASES_D], "latest": ALIASES_D, "expect": "load", "defect": None,
      "note": "a station with aliases in two systems that format 1.0 added (linz, dmi; DR29)"}),
    ("chain", lambda: [chain_doc()], {}, (),
     {"releases": [CHAIN_D], "latest": CHAIN_D, "expect": "load", "defect": None,
      "note": "subordinate stations two and three links from their reference station, for the attribution (CR2 DR1)"}),
    ("knc", lambda: [knc_doc()], {}, (),
     {"releases": [KNC_D], "latest": KNC_D, "expect": "load", "defect": None,
      "note": "non-commercial licences and ten stations whose sets are in recommendation-rank order, for the "
              "non-commercial notice and commercial_only (K-NC DR104 to DR106)"}),
    ("predict", lambda: [predict_doc()], {}, (),
     {"releases": [PREDICT_D], "latest": PREDICT_D, "expect": "load", "defect": None,
      "note": "the prediction release (prediction spec 6.5): astro tables A (2000-2030) and B (2020-2100), the stations "
              "of the prediction cases, including the designed close-root and New Year stations"}),
    ("knc-predict", lambda: [knc_predict_doc()], {}, (),
     {"releases": [KNC_D], "latest": KNC_D, "expect": "load", "defect": None,
      "note": "knc plus the additions of the commercial_only prediction cases (prediction spec 6.5): chart datums on "
              "OTC-T-0185/a-noaa and OTC-T-0181/x-nc, equal offsets at OTC-T-0186/0187/0188/0190, subordinate current "
              "stations OTC-T-0191 and OTC-T-0192. Never opened in the same cache as knc (same release)"}),
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
    for name, defect, docs in PREDICT_BAD:
        write_root(out / "predict-bad" / name, docs(), reuse_root=(reuse / "predict-bad" / name) if reuse else None)
        manifest["fixtures"].append({"root": f"predict-bad/{name}", "releases": [PREDICT_D], "latest": PREDICT_D,
                                     "expect": "load", "defect": defect})
    for name, expect, defect, docs, tamper, *extra in BAD:
        write_root(out / "bad" / name, docs(), reuse_root=(reuse / "bad" / name) if reuse else None, tamper=tamper)
        manifest["fixtures"].append({"root": f"bad/{name}", "releases": [BASE], "latest": BASE,
                                     "expect": expect if expect == "load" else {"error": expect},
                                     "defect": defect, **(extra[0] if extra else {})})
    (out / "fixtures.json").write_bytes(dumps_pretty(manifest))


# --------------------------------------------------------------------------- the prediction calls (K2b-fixtures)
#
# conformance/tools/predict_calls.json: every prediction case of spec 6.5 as calls on the fixture roots above, with
# the hand-written expectations (errors, metadata, local time, datums, commercial_only, the SDK-only cases). Steps
# whose numbers come from the reference engine's strict mode name its entry point and arguments in "strict"; KP1-H's
# case harness (webcaltides scripts/otc/vectors/run_cases.rb) runs them and writes predict_expected.json, and
# K2b-pin merges the two into conformance/cases/predict-*.json. Generated here, so that every set, bin, offsets entry,
# table and datum term a call names is the fixture's own; --check regenerates it and compares.

PREDICT_CALLS = Path(__file__).resolve().parent / "predict_calls.json"
# The 5 s brute-force cross-check of spec 6.1 that a step asks the case harness for: of h' (extremes) or W' and W
# (current events), of W' only (current peaks), or of W only (slacks). None: no cross-check.
CROSSCHECKS = ("scan_5s", "scan_5s_peaks", "scan_5s_slacks")
T_FMT = "%Y-%m-%dT%H:%M:%SZ"


def _t(iso):
    """Whole seconds of an ISO 8601 UTC time, floored (spec 4.1: a fractional instant is floored)."""
    return math.floor(datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


def _iso(t):
    return datetime.datetime.fromtimestamp(t, tz=datetime.timezone.utc).strftime(T_FMT)


class _Release:
    """Lookups on one fixture release, for the calls."""

    def __init__(self, root, doc):
        self.root, self.doc = root, doc
        self.st = {s["station_id"]: s for s in doc["stations"]}
        self.conv = {c["convention_id"]: c for c in doc["conventions"]}

    def set(self, set_id):
        return next(c for c in self.st[set_id.split("/")[0]]["constant_sets"] if c["set_id"] == set_id)

    def table_of(self, cs):
        return self.conv[cs["convention_id"]].get("astro_table_id")

    def recommended(self, sid):
        return self.st[sid]["recommended_set_id"]

    def require_reference_set(self, ref_sid, quantity="water_level", source="noaa", bin_=None):
        """reference_set, for a call that predicts by offsets: a missing set is a builder error, never a None."""
        cs = self.reference_set(ref_sid, quantity, source, bin_)
        if cs is None:
            raise ValueError(f"{self.root}: reference station {ref_sid} has no usable {quantity} set "
                             f"({'bin ' + str(bin_) if bin_ is not None else 'source ' + source}) for a call that predicts")
        return cs

    def reference_set(self, ref_sid, quantity="water_level", source="noaa", bin_=None):
        """Spec 4.8 step 1 / 4.9 step 1: the first set in file order of the reference station with the offsets'
        source (tides) or the reference bin (currents), the quantity, and qc_status ok or flagged."""
        for cs in self.st[ref_sid]["constant_sets"]:
            if cs["quantity"] != quantity or cs["qc_status"] not in ("ok", "flagged"):
                continue
            if bin_ is None and cs["source"] == source:
                return cs
            if bin_ is not None and any(b["bin"] == bin_ for b in cs.get("current_bins", [])):
                return cs
        return None


def _datum_term(cs, datum):
    """The height of the datum term (spec 4.5) and the resolved name: (term, datum_name, level key or None)."""
    d = cs.get("datum") or {}
    if datum in (None, "mean_level"):
        return 0.0, "mean_level", None
    if datum == "zero":
        return d["msl_offset_m"], d.get("zero_name") or d.get("zero") or "unknown", None
    key = d["chart_datum"] if datum == "chart" else datum
    return d["msl_offset_m"] - d["named"][key], key, key


def _equal_offsets(o):
    """The fold test of spec 4.8a, after the absent-offset rule."""
    ident = 1 if o["height_adjusted_type"] == "R" else 0
    return (o.get("time_offset_high_min", 0) == o.get("time_offset_low_min", 0)
            and o.get("height_offset_high", ident) == o.get("height_offset_low", ident))


def _series(start, stop, step):
    a, b = _t(start), _t(stop)
    return [_iso(a + k * step) for k in range((b - a + step - 1) // step)] if b > a else []


PREDICTION_KEYS = ("station_id", "timezone", "method", "set_id", "convention_id", "astro_table_id", "reference_station_id",
                   "reference_bin", "datum", "datum_name", "datum_kind", "datum_uncertainty_m", "bin_number",
                   "omitted_event_types", "tz", "tz_version", "release", "algorithm")
TZ_VERSION = {"$any_of": [{"$regex": "^[0-9]{4}[a-z]$"}, None]}
SLACKS = ["slack_before_flood", "slack_before_ebb"]


def _level_basis(datum_obj, key):
    """(kind, uncertainty_m) of a level's basis, or (None, None) when there is no basis for it."""
    b = ((datum_obj or {}).get("basis") or {}).get(key) or {}
    return b.get("kind"), b.get("uncertainty_m")


def predict_calls():
    P = _Release("predict", predict_doc())
    K = _Release("knc-predict", knc_predict_doc())
    cases = []

    def case(cid, title, spec, steps, root="predict", requires=("predict",), **extra):
        rel = {"predict": P, "knc-predict": K}.get(root)
        c = {"id": cid, "title": title, "spec": spec, "root": root,
             "release": rel.doc["release"]["datestamp"] if rel else PREDICT_D, "requires": list(requires)}
        c.update(extra)
        flat = []
        for s in steps:
            for x in (s if isinstance(s, list) else [s]):
                x = copy.deepcopy(x)
                if (x.get("strict") or {}).get("same_as_step") == -1:   # to_local: the strict items of the step before it
                    x["strict"]["same_as_step"] = len(flat) - 1
                flat.append(x)
        for x in flat:   # expect_if_missing in order: the driver takes the first feature the runner lacks (K2)
            if isinstance(x.get("expect_if_missing"), dict):
                x["expect_if_missing"] = [[f, e] for f, e in x["expect_if_missing"].items()]
        c["steps"] = flat
        release = c["release"]
        for s in flat:   # the Prediction's release is the case's (knc-predict and predict differ)
            pr = (s.get("expect") or {}).get("prediction")
            if isinstance(pr, dict):
                pr["release"] = release
        cases.append(c)

    def args(**kw):
        return {k: v for k, v in kw.items() if v is not None}

    def prediction(R, sid, *, method, cs, datum_arg=None, datum_obj=None, datum_default="mean_level", ref_station=None,
                   ref_bin=None, bin_number=None, omitted=None, current=False):
        """Every field of the Prediction (spec 5.3; K2's README "Prediction"), from the fixture by the spec's rules:
        datum is the argument (null when absent or for currents); datum_name, datum_kind and datum_uncertainty_m are
        the resolved level's (mean_level and zero have no basis); tz and tz_version are null before to_local."""
        name = kind = unc = None
        if not current:
            d = datum_obj or {}
            want = datum_arg if datum_arg is not None else datum_default
            if want == "mean_level":
                name = "mean_level"
            elif want == "zero":
                name = d.get("zero_name") or d.get("zero") or "unknown"
            else:
                key = d.get("chart_datum") if want == "chart" else want
                name = key
                if key is not None:
                    kind, unc = _level_basis(d, key)
        conv = R.conv[cs["convention_id"]]
        return {"station_id": sid, "timezone": R.st[sid]["timezone"], "method": method, "set_id": cs["set_id"],
                "convention_id": cs["convention_id"], "astro_table_id": conv.get("astro_table_id"),
                "reference_station_id": ref_station, "reference_bin": ref_bin, "datum": None if current else datum_arg,
                "datum_name": name, "datum_kind": kind, "datum_uncertainty_m": unc, "bin_number": bin_number,
                "omitted_event_types": omitted, "tz": None, "tz_version": None, "release": R.doc["release"]["datestamp"],
                "algorithm": "otc-predict-1"}

    def checked(pred, expect):
        """A hand-written field in expect must equal the Prediction computed from the fixture (a consistency check)."""
        for k, v in (expect or {}).items():
            if k not in PREDICTION_KEYS:
                raise ValueError(f"unknown Prediction field {k}")
            if pred[k] != v:
                raise ValueError(f"{pred['station_id']}: hand-written {k} {v!r} is not the fixture's {pred[k]!r}")
        return pred

    def step(op, a, pred, strict, items=None, outcome=None, crosscheck=None, extra=None):
        p = dict(pred)
        if items is not None:
            p["items"] = items
        s = {"op": op, "args": a, "expect": {"prediction": p}, "strict": strict}
        if crosscheck is not None:
            if crosscheck not in CROSSCHECKS:
                raise ValueError(f"cross-check {crosscheck!r} is not one of {CROSSCHECKS}")
            if op == "extremes" and crosscheck != "scan_5s":   # extremes have one cross-check: the scan of h'
                raise ValueError(f"extremes: cross-check {crosscheck!r} is not scan_5s")
            s["strict"]["crosscheck"] = crosscheck
        if outcome is not None:
            s["outcome"] = outcome
        s.update(extra or {})
        return s

    # -- harmonic tide steps
    def tide_set(R, sid, set_id, chosen):
        return R.set(chosen or set_id or R.recommended(sid))

    def heights(sid, start, stop, step_s=None, datum=None, set_id=None, R=P, expect=None, chosen=None, items=None, strict=True):
        cs = tide_set(R, sid, set_id, chosen)
        term, _, _ = _datum_term(cs, datum)
        pred = checked(prediction(R, sid, method="harmonic", cs=cs, datum_arg=datum, datum_obj=cs.get("datum")), expect)
        st = {"entry": "predict_strict", "args": {"constituents": {"$set": cs["set_id"]}, "times": _series(start, stop, step_s or 600),
                                                  "datum_term": term, "astro": R.table_of(cs)}} if strict else None
        return step("heights", args(station_id=sid, start=start, stop=stop, step_s=step_s, datum=datum, set_id=set_id), pred, st, items)

    def heights_at(sid, times, datum=None, set_id=None, R=P, expect=None, strict_times=None, extra=None):
        cs = tide_set(R, sid, set_id, None)
        term, _, _ = _datum_term(cs, datum)
        pred = checked(prediction(R, sid, method="harmonic", cs=cs, datum_arg=datum, datum_obj=cs.get("datum")), expect)
        return step("heights_at", args(station_id=sid, times=times, datum=datum, set_id=set_id), pred,
                    {"entry": "predict_strict", "args": {"constituents": {"$set": cs["set_id"]}, "times": strict_times or times,
                                                         "datum_term": term, "astro": R.table_of(cs)}}, extra=extra)

    def extremes(sid, start, stop, datum=None, set_id=None, R=P, expect=None, crosscheck=None, outcome=None, items=None,
                 strict=True, extra=None):
        cs = tide_set(R, sid, set_id, None)
        term, _, _ = _datum_term(cs, datum)
        pred = checked(prediction(R, sid, method="harmonic", cs=cs, datum_arg=datum, datum_obj=cs.get("datum")), expect)
        st = {"entry": "extremes_strict", "args": {"constituents": {"$set": cs["set_id"]}, "start": start, "stop": stop,
                                                   "datum_term": term, "astro": R.table_of(cs)}} if strict else None
        return step("extremes", args(station_id=sid, start=start, stop=stop, datum=datum, set_id=set_id), pred, st, items,
                    outcome, crosscheck, extra)

    def error(op, code, strict=None, fields=None, message=None, **kw):
        e = {"error": code}
        if fields:
            e["error_fields"] = fields
        if message is not None:
            e["error_message"] = message
        return {"op": op, "args": args(**kw), "expect": e, "strict": strict}

    # -- offsets
    def sub_base(R, sid, datum):
        o = R.st[sid]["subordinate_offsets"]
        ref = R.require_reference_set(o["reference_station_id"])
        rd = ref.get("datum")
        if not rd or "msl_offset_m" not in rd or rd.get("chart_datum") not in rd.get("named", {}):
            raise ValueError(f"{R.root}: {ref['set_id']} has no chart datum term, so {sid} cannot predict by offsets")
        c_ref = rd["msl_offset_m"] - rd["named"][rd["chart_datum"]]
        sd = o.get("datum") or {}
        shift = 0.0
        if datum not in (None, "chart"):
            shift = sd.get("named", {}).get(sd.get("chart_datum"), 0.0) - sd["named"][datum]
        base = {"ref_constituents": {"$set": ref["set_id"]}, "chart_datum_term": c_ref, "offsets": {"$offsets": sid},
                "datum_shift": shift, "astro": R.table_of(ref)}
        return o, ref, sd, base

    def sub_tide(op, sid, start, stop=None, step_s=None, datum=None, R=P, expect=None, times=None, compare_event_method=False):
        o, ref, sd, base = sub_base(R, sid, datum)
        folded = _equal_offsets(o)
        pred = checked(prediction(R, sid, method="folded_offsets" if folded else "offsets", cs=ref, datum_arg=datum, datum_obj=sd,
                                  datum_default="chart", ref_station=o["reference_station_id"]), expect)
        extra = None
        if op == "extremes":
            st = {"entry": "folded_extremes" if folded else "subordinate_extremes_strict", "args": dict(base, start=start, stop=stop)}
            a = args(station_id=sid, start=start, stop=stop, datum=datum)
            if compare_event_method:   # spec 4.8a: the folded extremes equal the event method's away from New Year
                extra = {"compare": {"entry": "subordinate_extremes_strict", "args": dict(base, start=start, stop=stop),
                                     "time_s": 1, "height_m": 1e-5}}
        elif op == "heights":
            st = {"entry": "folded_heights", "args": dict(base, times=_series(start, stop, step_s or 600))}
            a = args(station_id=sid, start=start, stop=stop, step_s=step_s, datum=datum)
        else:
            st = {"entry": "folded_heights", "args": dict(base, times=times)}
            a = args(station_id=sid, times=times, datum=datum)
        return step(op, a, pred, st, extra=extra)

    # -- currents
    def cur_bin(R, sid, bin_number, set_id=None):
        st = R.st[sid]
        cs = R.set(set_id or st["recommended_set_id"])
        n = bin_number or st.get("default_current_bin") or min(b["bin"] for b in cs["current_bins"])
        return cs, n

    def currents(sid, start, stop, step_s=None, bin_number=None, R=P, expect=None):
        cs, n = cur_bin(R, sid, bin_number)
        pred = checked(prediction(R, sid, method="harmonic", cs=cs, bin_number=n, current=True), expect)
        return step("currents", args(station_id=sid, start=start, stop=stop, step_s=step_s, bin_number=bin_number), pred,
                    {"entry": "currents_strict", "args": {"bin": {"$bin": [cs["set_id"], n]}, "times": _series(start, stop, step_s or 600),
                                                          "astro": R.table_of(cs)}})

    def current_events(sid, start, stop, bin_number=None, R=P, expect=None, crosscheck=None, outcome=None):
        cs, n = cur_bin(R, sid, bin_number)
        pred = checked(prediction(R, sid, method="harmonic", cs=cs, bin_number=n, current=True), expect)
        return step("current_events", args(station_id=sid, start=start, stop=stop, bin_number=bin_number), pred,
                    {"entry": "current_events_strict", "args": {"bin": {"$bin": [cs["set_id"], n]}, "start": start, "stop": stop,
                                                                "astro": R.table_of(cs)}}, None, outcome, crosscheck)

    def sub_current_events(sid, start, stop, bin_number=None, R=P, expect=None):
        st = R.st[sid]
        co = next(c for c in st["current_offsets"] if c["bin"] == (bin_number or min(x["bin"] for x in st["current_offsets"])))
        ref = R.require_reference_set(co["reference_station_id"], "current", bin_=co["reference_bin"])
        omitted = [t for t, (adj, ratio) in (("max_flood", ("time_adj_max_flood_min", "flood_amp_ratio")),
                                              ("max_ebb", ("time_adj_max_ebb_min", "ebb_amp_ratio")),
                                              ("slack_before_flood", ("time_adj_slack_before_flood_min", None)),
                                              ("slack_before_ebb", ("time_adj_slack_before_ebb_min", None)))
                   if co.get(adj) is None or (ratio and co.get(ratio) is None)]
        pred = checked(prediction(R, sid, method="offsets", cs=ref, ref_station=co["reference_station_id"], ref_bin=co["reference_bin"],
                                  bin_number=co["bin"], omitted=omitted, current=True), expect)
        return step("current_events", args(station_id=sid, start=start, stop=stop, bin_number=bin_number), pred,
                    {"entry": "subordinate_current_events_strict",
                     "args": {"ref_bin": {"$bin": [ref["set_id"], co["reference_bin"]]},
                              "offset": {"$current_offset": [sid, co["bin"]]}, "start": start, "stop": stop,
                              "astro": R.table_of(ref)}})

    def to_local(inner, tz=None, local_items=None, expect_if_missing=None, error=None, error_message=None, R=P):
        """[inner, to_local]: K2's to_local takes {tz} and converts the result of the case's most recent prediction step.
        Its tz is the resolved zone (for "station", the station's timezone, never the literal), its tz_version a
        version string or null. "local.zone" is the zone K2b-pin uses to add local_time and utc_offset_s to the strict
        items of the step before (strict.same_as_step); "local.check" lists hand-written values they must equal."""
        sid = inner["args"]["station_id"]
        zone = tz if tz not in (None, "station") else R.st[sid]["timezone"]
        if error is not None:
            e = {"error": error}
            if error_message is not None:
                e["error_message"] = error_message
            tl = {"op": "to_local", "args": args(tz=tz), "expect": e, "strict": None}
        else:
            pred = dict(inner["expect"]["prediction"], tz=zone, tz_version=TZ_VERSION)
            tl = {"op": "to_local", "args": args(tz=tz), "expect": {"prediction": pred}, "strict": {"same_as_step": -1},
                  "local": {"zone": zone}}
            if local_items:
                tl["local"]["check"] = local_items
        if expect_if_missing:
            tl["expect_if_missing"] = expect_if_missing
        return [inner, tl]

    def tl_error(tz, code, fields=None):
        """A to_local step that fails (on the last prediction step)."""
        e = {"error": code}
        if fields:
            e["error_fields"] = fields
        return {"op": "to_local", "args": {"tz": tz}, "expect": e, "strict": None}

    D = "2010-03-01T"
    B = P_BASIC
    # ------------------------------------------------------------------ heights
    case("predict-heights/basic", "heights at the basic station over one day, every 600 s (the default step)", "4.4, 5.2",
         [heights(B, D + "00:00:00Z", "2010-03-02T00:00:00Z")])
    case("predict-heights/at", "heights_at: one item per instant, in the given order, repeats kept", "4.1, 5.2",
         [heights_at(B, [D + "06:00:00Z", D + "01:00:00Z", D + "06:00:00Z", "2015-07-04T12:34:56Z"])])
    case("predict-heights/step-alignment", "series times are start + k * step_s, not aligned to a grid or the clock", "4.1",
         [heights(B, D + "00:07:13Z", D + "03:07:13Z", 900)])
    case("predict-heights/empty-window", "start == stop gives an empty result", "4.1",
         [heights(B, D + "00:00:00Z", D + "00:00:00Z", items=[], strict=False)])
    case("predict-heights/start-after-stop", "start > stop is invalid_argument", "4.1, 5.4",
         [error("heights", "invalid_argument", station_id=B, start=D + "01:00:00Z", stop=D + "00:00:00Z")])
    case("predict-heights/step-zero", "step_s 0 and -600 are invalid_argument", "5.2, 5.4",
         [error("heights", "invalid_argument", station_id=B, start=D + "00:00:00Z", stop=D + "01:00:00Z", step_s=0),
          error("heights", "invalid_argument", station_id=B, start=D + "00:00:00Z", stop=D + "01:00:00Z", step_s=-600)])
    case("predict-heights/year-boundary", "the step at 2010-01-01T00:00:00Z: each sample uses its own year's tables", "4.3",
         [heights(B, "2009-12-31T22:00:00Z", "2010-01-01T02:00:00Z", 600)])
    case("predict-heights/leap-day", "heights across 29 February 2012 and at the end of the leap year", "4.3",
         [heights_at(B, ["2012-02-28T12:00:00Z", "2012-02-29T12:00:00Z", "2012-03-01T12:00:00Z", "2012-12-31T23:59:59Z"])])
    case("predict-heights/naive-datetime", "a naive datetime (no zone) is invalid_argument (Python only)", "4.1",
         [error("heights", "invalid_argument", station_id=B, start="2010-03-01T00:00:00", stop="2010-03-01T01:00:00")],
         runners=["python", "python-no-tz"])
    case("predict-heights/fractional-instants",
         "an instant at 12:00:00.7 is floored to 12:00:00 and gives the whole-second height (TypeScript, Python, Ruby)", "4.1",
         [heights_at(B, ["2010-03-01T12:00:00.7Z"], strict_times=["2010-03-01T12:00:00Z"], extra={"same_items_as_step": 1}),
          heights_at(B, ["2010-03-01T12:00:00Z"]),
          dict(heights(B, "2010-03-01T12:00:00.7Z", "2010-03-01T12:30:00Z"), same_items_as_step=3),
          heights(B, "2010-03-01T12:00:00Z", "2010-03-01T12:30:00Z")],
         runners=["python", "python-no-tz", "ruby", "ruby-no-tz", "typescript", "typescript-browser"],
         note="steps 0 and 2 have the items of steps 1 and 3 (same_items_as_step); the strict mode gets the floored instants")
    case("predict-set-not-found", "heights with a set_id that is not the station's is invalid_argument naming it", "4.2 step 1",
         [error("heights", "invalid_argument", message={"$contains": "OTC-P-0001/no-such-set"}, station_id=B,
                start=D + "00:00:00Z", stop=D + "01:00:00Z", set_id="OTC-P-0001/no-such-set")])
    case("predict-local-phase-convention",
         "the UTC+1 convention's set predicts the same as a Greenwich set with the same published phases", "3.3, 4.2",
         [heights("OTC-P-0004", D + "00:00:00Z", D + "06:00:00Z", 1800, set_id="OTC-P-0004/kartverket"),
          heights("OTC-P-0004", D + "00:00:00Z", D + "06:00:00Z", 1800, set_id="OTC-P-0004/greenwich")],
         note="both steps have the same expected items (the SDK ignores utc_offset_hours); their convention_id differs")
    case("predict-set-speed", "OTC-P-0001's M2 set speed is 8e-8 deg/h off the table's (within the build's 1e-7): the speed comes "
         "from the table (late in the year the difference is ~1e-5 m)", "4.3, 3.3",
         [heights_at(B, ["2010-03-01T03:00:00Z", "2010-12-31T21:00:00Z", "2010-12-31T23:00:00Z"])])
    # ------------------------------------------------------------------ datums of heights
    case("predict-datum/mean-level", "datum mean_level: h above the set's mean level", "4.5",
         [heights_at(B, [D + "03:00:00Z"], datum="mean_level", expect={"datum": "mean_level", "datum_name": "mean_level",
                                                                     "datum_kind": None, "datum_uncertainty_m": None})])
    case("predict-datum/zero", "datum zero: msl_offset_m + h; datum_name is zero_name", "4.5",
         [heights_at(B, [D + "03:00:00Z"], datum="zero", expect={"datum": "zero", "datum_name": "MLLW", "datum_kind": None})])
    case("predict-datum/named", "datum mhhw (a key of named): msl_offset_m + h - named[mhhw]", "4.5",
         [heights_at(B, [D + "03:00:00Z"], datum="mhhw", expect={"datum": "mhhw", "datum_name": "mhhw", "datum_kind": "published",
                                                               "datum_uncertainty_m": None})])
    case("predict-datum/chart", "datum chart resolves to mllw, with its basis kind and uncertainty; at a set whose zero is not its "
         "chart datum (named[chart_datum] 0.85), chart is msl_offset_m + h - 0.85", "4.5, 5.3",
         [heights_at(B, [D + "03:00:00Z"], datum="chart", expect={"datum": "chart", "datum_name": "mllw", "datum_kind": "published",
                                                                "datum_uncertainty_m": 0.01}),
          heights_at("OTC-P-0060", [D + "03:00:00Z", D + "09:00:00Z"], datum="chart", expect={"datum_name": "mllw"}),
          heights_at("OTC-P-0060", [D + "03:00:00Z"], datum="zero", expect={"datum_name": "STND"})])
    case("predict-datum/unavailable", "each missing need is datum_unavailable, naming what is missing", "4.5, 5.4",
         [error("heights_at", "datum_unavailable", message={"$contains": "msl_offset_m"}, station_id="OTC-P-0053",
                times=[D + "03:00:00Z"], datum="zero", set_id="OTC-P-0053/no-datum"),
          error("heights_at", "datum_unavailable", message={"$contains": "msl_offset_m"}, station_id="OTC-P-0053",
                times=[D + "03:00:00Z"], datum="zero", set_id="OTC-P-0053/no-msl"),
          error("heights_at", "datum_unavailable", message={"$contains": "msl_offset_m"}, station_id="OTC-P-0053",
                times=[D + "03:00:00Z"], datum="chart", set_id="OTC-P-0053/no-msl"),
          error("heights_at", "datum_unavailable", message={"$contains": "chart_datum"}, station_id="OTC-P-0053",
                times=[D + "03:00:00Z"], datum="chart", set_id="OTC-P-0053/no-chart"),
          error("heights_at", "datum_unavailable", message={"$contains": "mllw"}, station_id="OTC-P-0053",
                times=[D + "03:00:00Z"], datum="mllw", set_id="OTC-P-0053/no-chart"),
          error("extremes", "datum_unavailable", message={"$contains": "mllw"}, station_id="OTC-P-0053",
                start=D + "00:00:00Z", stop=D + "12:00:00Z", datum="mllw", set_id="OTC-P-0053/no-chart")])
    case("predict-datum/otc-key", "datum otc_lat (an otc_ key, kind computed)", "4.5; datums spec 7.2",
         [heights_at(B, [D + "03:00:00Z"], datum="otc_lat", expect={"datum_name": "otc_lat", "datum_kind": "computed",
                                                                  "datum_uncertainty_m": 0.02})])
    case("predict-datum/vertical-zero", "datum zero on a set whose zero is vertical_datum NAP: datum_name NAP", "4.5",
         [heights_at("OTC-P-0052", [D + "03:00:00Z"], datum="zero", expect={"datum_name": "NAP"}),
          {"op": "datums", "args": {"station_id": "OTC-P-0052"}, "strict": None,
           "expect": {"datums": None}}])   # filled below with the DatumInfo
    # ------------------------------------------------------------------ errors of choosing the constants
    case("predict-no-constants", "a no_constants set (explicit set_id), and a station with no usable set and no offsets", "4.2 step 2",
         [error("heights", "no_constants", station_id="OTC-P-0042", start=D + "00:00:00Z", stop=D + "01:00:00Z",
                set_id="OTC-P-0042/noaa-a-noc"),
          error("heights", "no_constants", station_id="OTC-P-0014", start=D + "00:00:00Z", stop=D + "01:00:00Z")])
    case("predict-quantity-mismatch", "heights on a current set, currents on a water-level set", "4.2 step 3",
         [error("heights", "quantity_mismatch", station_id="OTC-P-0016", start=D + "00:00:00Z", stop=D + "01:00:00Z"),
          error("currents", "quantity_mismatch", station_id=B, start=D + "00:00:00Z", stop=D + "01:00:00Z")])
    case("predict-unsupported-convention", "v0_model tamura_iho2006 is unsupported_convention", "4.2 step 4",
         [error("heights", "unsupported_convention", station_id="OTC-P-0015", start=D + "00:00:00Z", stop=D + "01:00:00Z")])
    us = lambda op, entry, **kw: error(op, "unsupported_constituent", fields={"constituent": "M4"},
                                       strict={"entry": entry, "args": dict({"constituents": {"$set": "OTC-P-0001/noaa"},
                                                                              "datum_term": 0.0, "astro": ASTRO_A},
                                                                             **({"times": [kw["start"]]} if entry == "predict_strict"
                                                                                else {"start": kw["start"], "stop": kw["stop"]}))}, **kw)
    case("predict-unsupported-constituent", "a constituent of the set with no table row (bad fixture: table A has no M4)", "4.2 step 6",
         [us("heights", "predict_strict", station_id=B, start=D + "00:00:00Z", stop=D + "01:00:00Z"),
          us("extremes", "extremes_strict", station_id=B, start=D + "00:00:00Z", stop=D + "12:00:00Z")],
         root="predict-bad/unsupported-constituent")
    nat = lambda tid, conv: {"$all": [{"$contains": f'has no astro table "{tid}" for convention "{conv}"'},
                                      {"$contains": "site PR #45"}]}
    case("predict-no-astro-table", "the convention names a table that is absent; a convention with no astro_table_id ({id} empty)",
         "4.2 step 5, 5.4",
         [error("heights", "no_astro_table", message=nat(ASTRO_A, CONV_G), station_id=B, start=D + "00:00:00Z", stop=D + "01:00:00Z"),
          error("heights", "no_astro_table", message=nat("", CONV_LOCAL), station_id="OTC-P-0004", start=D + "00:00:00Z",
                stop=D + "01:00:00Z")],
         root="predict-bad/no-astro-table", note="the fixture is invalid under the schema; the SDK loads it and fails only when it predicts")
    oor = {"first_year": 2000, "last_year": 2030}
    st_h = lambda times: {"entry": "predict_strict", "args": {"constituents": {"$set": "OTC-P-0001/noaa"}, "times": times,
                                                              "datum_term": 0.0, "astro": ASTRO_A}}
    st_e = lambda a, b: {"entry": "extremes_strict", "args": {"constituents": {"$set": "OTC-P-0001/noaa"}, "start": a, "stop": b,
                                                              "datum_term": 0.0, "astro": ASTRO_A}}
    case("predict-time-out-of-range",
         "1999-12-31T23:59:59Z and 2031-01-01T00:00:00Z; extremes whose grid padding reaches out of the table (heights with the same stop work)",
         "4.3, 4.6 step 1",
         [error("heights_at", "time_out_of_range", fields=oor, station_id=B, times=["1999-12-31T23:59:59Z"],
                strict=st_h(["1999-12-31T23:59:59Z"])),
          error("heights_at", "time_out_of_range", fields=oor, station_id=B, times=["2031-01-01T00:00:00Z"],
                strict=st_h(["2031-01-01T00:00:00Z"])),
          error("extremes", "time_out_of_range", fields=oor, station_id=B, start="2030-12-31T00:00:00Z", stop="2031-01-01T00:00:00Z",
                strict=st_e("2030-12-31T00:00:00Z", "2031-01-01T00:00:00Z")),
          error("extremes", "time_out_of_range", fields=oor, station_id=B, start="2000-01-01T00:00:00Z", stop="2000-01-02T00:00:00Z",
                strict=st_e("2000-01-01T00:00:00Z", "2000-01-02T00:00:00Z")),
          heights(B, "2030-12-31T22:00:00Z", "2031-01-01T00:00:00Z", 3600)])
    case("predict-empty-window-out-of-range", "extremes with start == stop = 2031-01-01T00:00:00Z: empty, not time_out_of_range", "4.1",
         [extremes(B, "2031-01-01T00:00:00Z", "2031-01-01T00:00:00Z", items=[], strict=False)])
    # ------------------------------------------------------------------ extremes
    case("predict-extremes/basic", "extremes at the basic station over 3 days (cross-checked by a 5 s scan)", "4.6",
         [extremes(B, D + "00:00:00Z", "2010-03-04T00:00:00Z", crosscheck="scan_5s")])
    e1, e2 = "2010-03-10T11:22:50Z", "2010-03-10T18:05:38Z"   # two consecutive reported extremes (low then high? see outcome)
    case("predict-extremes/window-edges", "an event exactly at start is reported; one exactly at stop is not; windows that meet at an "
         "event report it once", "4.6 step 7",
         [extremes(B, e1, _iso(_t(e2) + 1), outcome={"items": [{"time": e1, "type": "high"}, {"time": e2, "type": "low"}]}),
          extremes(B, e1, e2, outcome={"items": [{"time": e1, "type": "high"}]}),
          extremes(B, e2, _iso(_t(e2) + 1), outcome={"items": [{"time": e2, "type": "low"}]})],
         note="steps 1 and 2 meet at 18:05:38: the event there is in step 2 only (the window is [start, stop))")
    case("predict-extremes/single-constituent", "M2 only, 2010-03-01 to 2010-03-31: 116 extremes, equal to a 5 s scan", "4.6 step 3",
         [extremes("OTC-P-0005", *PW["single"], crosscheck="scan_5s", outcome={"count": 116})],
         note="not band-checked (spec 6.3 band 3 vs this fixed window; raised for revision 29): 4 of its 116 events lie within "
              "0.01 s of a half second")
    large = []
    for sid_set, key in (("OTC-P-0012/m2-5m", "large-m2"), ("OTC-P-0012/m2-7m5", "large-m2"), ("OTC-P-0012/k1-40m", "large-k1")):
        large.append(extremes("OTC-P-0012", *PW[key], set_id=sid_set, crosscheck="scan_5s"))
    case("predict-extremes/large-amplitude", "M2 at 5 m and 7.5 m in December 2099, K1 at 40 m on 2025-12-22: counts equal a 5 s scan (pins E)",
         "4.6 step 3", large)
    for cid, title, n in (("current-peaks-large-amplitude", "max_flood and max_ebb of the same amplitudes in m/s: their count equals a 5 s "
                           "scan of W' (scan_5s_peaks compares the max_* events only)", "scan_5s_peaks"),
                          ("slacks-large-amplitude", "the slacks of the same bins: their count equals a 5 s scan of W (scan_5s_slacks "
                           "compares the slack_* events only)", "scan_5s_slacks")):
        case(f"predict-{cid}", title, "4.7",
             [current_events("OTC-P-0013", *PW["large-m2"], bin_number=1, crosscheck=n),
              current_events("OTC-P-0013", *PW["large-m2"], bin_number=2, crosscheck=n),
              current_events("OTC-P-0013", *PW["large-k1"], bin_number=3, crosscheck=n)])
    case("predict-extremes/close-high-low", "a high and a low 3 minutes apart inside one 6-minute step: both reported", "4.6",
         [extremes("OTC-P-0008", *PW["close-high-low"], outcome={"items": [{"time": "2010-04-15T12:01:37Z", "type": "high"},
                                                                          {"time": "2010-04-15T12:04:38Z", "type": "low"}]})])
    case("predict-extremes/close-high-low-high", "three extremes inside one 6-minute step: all reported, in order", "4.6",
         [extremes("OTC-P-0009", *PW["close-high-low-high"], outcome={"items": [{"time": "2010-05-03T06:01:23Z", "type": "high"},
                                                                               {"time": "2010-05-03T06:02:53Z", "type": "low"},
                                                                               {"time": "2010-05-03T06:04:23Z", "type": "high"}]})])
    case("predict-extremes/double-high", "two highs 20 minutes apart with the low between: all three reported", "4.6",
         [extremes("OTC-P-0010", *PW["double-high"], outcome={"items": [{"time": "2010-05-20T17:52:55Z", "type": "high"},
                                                                       {"time": "2010-05-20T18:02:53Z", "type": "low"},
                                                                       {"time": "2010-05-20T18:12:52Z", "type": "high"}]})])
    case("predict-extremes/sub-second", "the close-root filter: an even cluster dropped; one high of a high-low-high kept "
         "(the higher, the second; on equal heights the first)", "4.6 step 6",
         [extremes("OTC-P-0011", *PW["sub-second-pair"][:2], set_id="OTC-P-0011/pair", outcome={"items": []}),
          extremes("OTC-P-0011", *PW["sub-second-triple-higher"][:2], set_id="OTC-P-0011/triple-higher",
                   outcome={"items": [{"time": "2010-06-20T09:01:11Z", "type": "high"}]}),
          extremes("OTC-P-0011", *PW["sub-second-triple-equal"][:2], datum="zero", set_id="OTC-P-0011/triple-equal",
                   outcome={"items": [{"time": "2010-07-03T09:01:10Z", "type": "high"}]})])
    case("predict-extremes/year-boundary-step", "an extremum 200 s before 2010-01-01, found in the old year's step, with the old year's height",
         "4.6 step 2", [extremes("OTC-P-0006", "2009-12-31T23:00:00Z", "2010-01-01T01:00:00Z",
                                 outcome={"items": [{"time": "2009-12-31T23:56:40Z", "type": "high"}]})])
    case("predict-extremes/new-year-missed", "K1 and O1 jump +5 at 2010-01-01: the high missed by both tables is inserted at exactly T, "
         "with the new year's height", "4.6 step 6a",
         [extremes("OTC-P-0007", "2009-12-31T23:30:00Z", "2010-01-01T00:30:00Z",
                   outcome={"items": [{"time": "2010-01-01T00:00:00Z", "type": "high"}]})])
    case("predict-extremes/new-year-doubled", "the opposite jump at 2011-01-01: the high at T - 10 min (old) and T + 8 min (new) "
         "is reported exactly once, the higher (the new year's)", "4.6 step 6a",
         [extremes("OTC-P-0007", "2010-12-31T23:30:00Z", "2011-01-01T00:30:00Z",
                   outcome={"items": [{"time": "2011-01-01T00:08:11Z", "type": "high"}]})])
    case("predict-extremes/negative-amplitude", "M2 at -1.0 m over the single-constituent window: 116 extremes, highs and lows "
         "swapped (SDK only; the strict mode refuses a negative amplitude)", "4.4",
         [extremes("OTC-P-0005", *PW["single"], strict=False, outcome={"count": 116},
                   extra={"swap_of": {"case": "predict-extremes/single-constituent", "step": 0}})],
         root="predict-bad/extremes-negative-amplitude",
         note="swap_of: the items of that step with high and low swapped and each height negated")
    # ------------------------------------------------------------------ currents
    C0 = PW["currents"]
    case("predict-currents/series", "currents at the default bin (2) over one day", "4.7", [currents("OTC-P-0016", *C0)])
    case("predict-currents/mean", "the bin's mean_major_ms and mean_minor_ms are added", "4.7",
         [currents("OTC-P-0017", *C0, bin_number=1)])
    case("predict-currents/minor-sign", "a strong minor axis: V positive 90 degrees clockwise of the major axis (s = +1)", "4.7",
         [currents("OTC-P-0017", *C0, bin_number=2)])
    case("predict-currents/flood-sign", "sigma = -1 (flood opposite the azimuth): both components flip, direction is unchanged", "4.7",
         [currents("OTC-P-0017", *C0, bin_number=3)])
    case("predict-currents/direction-null", "zero speed: direction_deg is null", "4.7",
         [currents("OTC-P-0017", *C0, step_s=3600, bin_number=4)])
    case("predict-currents/direction-north", "azimuth 180 flowing toward north: direction_deg 0.0, never 360.0", "4.7",
         [currents("OTC-P-0017", *C0, step_s=3600, bin_number=5)])
    case("predict-currents/default-bin", "no bin_number: default_current_bin, else the lowest bin number in the set", "4.7",
         [currents("OTC-P-0016", C0[0], "2010-03-01T03:00:00Z"), currents("OTC-P-0018", C0[0], "2010-03-01T03:00:00Z")])
    case("predict-currents/explicit-bin", "bin_number 3", "4.7", [currents("OTC-P-0016", C0[0], "2010-03-01T03:00:00Z", bin_number=3)])
    case("predict-bin-not-found", "a bin that is not in the set, and one that is not in the current_offsets", "4.7, 4.9",
         [error("currents", "bin_not_found", station_id="OTC-P-0016", start=C0[0], stop="2010-03-01T01:00:00Z", bin_number=9),
          error("current_events", "bin_not_found", station_id="OTC-P-0050", start=C0[0], stop="2010-03-01T12:00:00Z", bin_number=9)])
    case("predict-bin-number-too-large", "bin_number 2^53 is invalid_argument in every SDK; 2^53 - 1 on a set without it is bin_not_found",
         "5.2", [error("currents", "invalid_argument", station_id="OTC-P-0016", start=C0[0], stop="2010-03-01T01:00:00Z",
                       bin_number=9007199254740992),
                 error("currents", "bin_not_found", station_id="OTC-P-0016", start=C0[0], stop="2010-03-01T01:00:00Z",
                       bin_number=9007199254740991)])
    case("predict-current-events/basic", "events of the default bin over 2 days (cross-checked by a 5 s scan of W' and W)", "4.7",
         [current_events("OTC-P-0016", "2010-03-01T00:00:00Z", "2010-03-03T00:00:00Z", crosscheck="scan_5s")])
    case("predict-current-events/flood-sign", "events on a bin with sigma = -1 (flood opposite the azimuth): W = -U, so max_flood "
         "and max_ebb and the two slack types are those of -U", "4.7",
         [current_events("OTC-P-0017", "2010-03-01T00:00:00Z", "2010-03-03T00:00:00Z", bin_number=3, crosscheck="scan_5s")])
    case("predict-current-events/weak", "a local maximum of W below zero is not reported", "4.7",
         [current_events("OTC-P-0019", *PW["current-events-weak"])])
    case("predict-current-events/close-slacks", "two slacks inside one 6-minute step, 2 minutes apart: both reported", "4.7",
         [current_events("OTC-P-0020", *PW["close-slacks"], bin_number=1,
                         outcome={"types": SLACKS, "items": [{"time": "2010-07-20T12:01:53Z", "type": "slack_before_flood"},
                                                             {"time": "2010-07-20T12:03:53Z", "type": "slack_before_ebb"}]})])
    ss = []
    for i, (n, out) in enumerate(((2, []), (3, [{"time": "2010-08-09T06:01:10Z", "type": "slack_before_flood"}]),
                                  (4, [{"time": "2010-01-20T06:02:21Z", "type": "slack_before_flood"}]))):
        c = _t(PW["sub-second-slacks"][i][:19] + "Z")
        ss.append(current_events("OTC-P-0020", _iso(c - 10), _iso(c + 10), bin_number=n, outcome={"types": SLACKS, "items": out}))
    case("predict-current-events/sub-second-slacks", "two slacks 0.6 s apart (even: none); three within 0.9 s flood-ebb-flood "
         "(index 0 kept, a slack_before_flood); five, each less than 1 s after the one before, in five leaves (index 2 kept)", "4.7", ss,
         note="the outcomes compare the slack_* events only: step 0's weak flood between its two slacks is a max_flood of "
              "W = 4.4e-10 m/s, reported; the other two windows' max_* events come from the ripple's cluster and are the strict mode's")
    case("predict-current-events/new-year-slack", "2012-01-01: a slack missed at T is inserted at exactly T (bin 1); a doubled one "
         "keeps L, the old year's (bin 2)", "4.7",
         [current_events("OTC-P-0021", "2011-12-31T23:30:00Z", "2012-01-01T00:30:00Z", bin_number=1,
                         outcome={"items": [{"time": "2012-01-01T00:00:00Z", "type": "slack_before_flood"}]}),
          current_events("OTC-P-0021", "2011-12-31T23:30:00Z", "2012-01-01T00:30:00Z", bin_number=2,
                         outcome={"items": [{"time": "2011-12-31T23:57:00Z", "type": "slack_before_flood"}]})])
    # ------------------------------------------------------------------ subordinate tides
    W2 = (D + "00:00:00Z", "2010-03-03T00:00:00Z")
    case("predict-subordinate/tide-ratio", "R, differing offsets: NOAA's event method", "4.8", [sub_tide("extremes", "OTC-P-0030", *W2)])
    case("predict-subordinate/tide-additive", "A, differing offsets", "4.8", [sub_tide("extremes", "OTC-P-0031", *W2)])
    case("predict-subordinate/tide-missing-offsets", "an absent time offset is 0, an absent height offset the identity", "4.8 step 3",
         [sub_tide("extremes", "OTC-P-0032", *W2)])
    case("predict-subordinate/tide-order-swap", "shifted events that swap order are ordered by time; a reference high 178 min before "
         "start (inside the padding M = 250 + 60 min) lands inside the window", "4.8 steps 2, 4",
         [sub_tide("extremes", "OTC-P-0033", *W2), sub_tide("extremes", "OTC-P-0033", "2010-03-01T08:00:00Z", "2010-03-02T08:00:00Z")],
         note="step 1: the reference high at 05:01:52 shifts +250 min to 09:11:52; a padding of 120 min (or none) loses it")
    case("predict-subordinate/tide-fractional-offset", "+12.5 and -7.25 min give whole-second times, floor(t + 0.5); +12.345 and "
         "-7.29 min (740.7 s, -437.4 s) are added to the unrounded r, then rounded once", "4.8 step 3",
         [sub_tide("extremes", "OTC-P-0034", *W2), sub_tide("extremes", "OTC-P-0062", *W2)])
    xo = lambda sid: error("heights", "extremes_only", message={"$contains": "offsets differ"}, station_id=sid,
                           start=W2[0], stop="2010-03-01T06:00:00Z")
    case("predict-subordinate/series", "heights at a station with differing offsets: extremes_only", "4.8a, 5.4",
         [xo("OTC-P-0031"), error("heights_at", "extremes_only", station_id="OTC-P-0031", times=[W2[0]])])
    case("predict-subordinate/reference-no-chart-datum", "the reference's noaa set has no chart datum: datum_unavailable", "4.8 step 2",
         [error("extremes", "datum_unavailable", station_id="OTC-P-0045", start=W2[0], stop=W2[1])])
    case("predict-subordinate/current", "a subordinate current station: events by offsets (a reference slack 5 min 20 s before start "
         "lands inside the window); currents is extremes_only", "4.9",
         [sub_current_events("OTC-P-0050", *W2), sub_current_events("OTC-P-0050", "2010-03-01T09:00:00Z", "2010-03-02T09:00:00Z"),
          error("currents", "extremes_only", station_id="OTC-P-0050", start=W2[0], stop="2010-03-01T06:00:00Z")],
         note="step 1: the reference slack_before_flood at 08:54:40 shifts +5.5 min to 09:00:10")
    case("predict-subordinate/current-null-adjustment", "a null adjustment or ratio drops that event type (omitted_event_types)", "4.9 step 4",
         [sub_current_events("OTC-P-0051", *W2)])
    case("predict-subordinate/event-datum", "the event path on a reference whose chart datum is 0.85 above its zero, with the "
         "subordinate's own datum: chart (the default), mhhw and msl", "4.8 steps 2, 5",
         [sub_tide("extremes", "OTC-P-0061", *W2), sub_tide("extremes", "OTC-P-0061", *W2, datum="mhhw"),
          sub_tide("extremes", "OTC-P-0061", *W2, datum="msl")])
    case("predict-subordinate/folded-ratio", "equal offsets, R 0.9, +37 min: heights by folding, method folded_offsets", "4.8a",
         [sub_tide("heights", "OTC-P-0035", W2[0], "2010-03-02T00:00:00Z")])
    case("predict-subordinate/folded-additive", "equal offsets, A +0.15 m, -12 min", "4.8a",
         [sub_tide("heights", "OTC-P-0036", W2[0], "2010-03-02T00:00:00Z")])
    case("predict-subordinate/folded-extremes", "the folded station's extremes, equal to the event method's away from New Year "
         "(times within 1 s, heights within 1e-5 m: the step's compare)", "4.8a",
         [sub_tide("extremes", "OTC-P-0035", *W2, compare_event_method=True)])
    case("predict-subordinate/folded-new-year", "a window across 2013-01-01 with +40 min: the folded curve uses year Y(t)'s tables", "4.8a",
         [sub_tide("heights", "OTC-P-0037", "2012-12-31T22:00:00Z", "2013-01-01T02:00:00Z")])
    case("predict-subordinate/differing-offsets-series", "differing offsets: heights fails with extremes_only (the offsets differ); extremes works",
         "4.8a", [xo("OTC-P-0030"), sub_tide("extremes", "OTC-P-0030", W2[0], "2010-03-02T00:00:00Z")])
    zr = lambda op, sid, sub: error(op, "invalid_argument", station_id=sid, start=W2[0], stop="2010-03-02T00:00:00Z",
                                    strict={"entry": "folded_heights" if op == "heights" else
                                            ("folded_extremes" if sub == "fold" else "subordinate_extremes_strict"),
                                            "args": dict({"ref_constituents": {"$set": "OTC-P-0001/noaa"}, "chart_datum_term": 1.12,
                                                          "offsets": {"$offsets": sid}, "datum_shift": 0.0, "astro": ASTRO_A},
                                                         **({"times": [W2[0]]} if op == "heights" else {"start": W2[0], "stop": "2010-03-02T00:00:00Z"}))})
    case("predict-subordinate/zero-ratio", "R ratio 0 and -0.5, equal and differing offsets: heights and extremes are invalid_argument",
         "4.8 step 3", [zr(op, sid, kind) for sid, kind in (("OTC-P-0038", "fold"), ("OTC-P-0039", "fold"),
                                                            ("OTC-P-0040", "event"), ("OTC-P-0041", "event"))
                        for op in ("heights", "extremes")])
    xt = lambda op, sid: error(op, "invalid_argument", message={"$contains": "X"}, station_id=sid, start=W2[0], stop="2010-03-02T00:00:00Z")
    case("predict-subordinate/unknown-adjusted-type", "height_adjusted_type X (read as other): invalid_argument naming X, equal and "
         "differing offsets; with a failing reference too, still invalid_argument (the type check comes first)", "4.8 step 6",
         [xt(op, sid) for sid in ("OTC-P-0035", "OTC-P-0030", "OTC-P-0049") for op in ("heights", "extremes")],
         root="predict-bad/unknown-adjusted-type",
         note="OTC-P-0049's reference has no noaa set (reference_unavailable without the X)")
    case("predict-subordinate/order-ratio-before-extremes-only", "differing offsets and an R ratio of 0: heights is invalid_argument, "
         "not extremes_only", "4.8 step 6", [zr("heights", "OTC-P-0040", "event")])
    nus = lambda op, sid, **kw: error(op, "reference_unavailable", fields={"reference_station_id": "OTC-P-0055"}, station_id=sid, **kw)
    case("predict-subordinate/reference-no-usable-set", "the reference is active, but its only noaa water-level set is no_constants "
         "(its gesla-fit set does not count): heights, heights_at and extremes are reference_unavailable, at an equal-offsets and a "
         "differing-offsets station (the reference checks come before extremes_only)", "4.8 step 1, step 6",
         [nus(op, sid, **kw) for sid in ("OTC-P-0056", "OTC-P-0057")
          for op, kw in (("heights", {"start": W2[0], "stop": "2010-03-01T06:00:00Z"}), ("heights_at", {"times": [W2[0]]}),
                         ("extremes", {"start": W2[0], "stop": W2[1]}))])
    case("predict-subordinate/current-reference-no-set", "a current_offsets reference that is active with no usable current set: "
         "current_events is reference_unavailable", "4.9 step 1",
         [error("current_events", "reference_unavailable", fields={"reference_station_id": "OTC-P-0058"}, station_id="OTC-P-0059",
                start=W2[0], stop=W2[1])])
    case("predict-subordinate/current-reference-no-set-missing", "a current_offsets reference that is not in the release (it loads: "
         "current_offsets are raw in 1.0): current_events is reference_unavailable", "4.9 step 1",
         [error("current_events", "reference_unavailable", fields={"reference_station_id": "OTC-P-9999"}, station_id="OTC-P-0059",
                start=W2[0], stop=W2[1])], root="predict-bad/current-reference-missing")
    case("predict-subordinate/current-reference-removed", "a current_offsets reference that is a removed station (a tombstone; it "
         "loads): current_events is reference_unavailable", "4.9 step 1",
         [error("current_events", "reference_unavailable", fields={"reference_station_id": "OTC-P-0097"}, station_id="OTC-P-0059",
                start=W2[0], stop=W2[1])], root="predict-bad/current-reference-removed")
    case("predict-reference-set-file-order", "the reference set is the first usable noaa water-level set in file order (the flagged one), "
         "not the recommended gesla-fit set, the no_constants set or the later ok set", "4.8 step 1",
         [sub_tide("extremes", "OTC-P-0043", *W2, expect={"set_id": "OTC-P-0042/noaa-b-flagged"})])
    # ------------------------------------------------------------------ local time
    LH = "local_time_unavailable"
    small = extremes(B, "2024-01-10T00:00:00Z", "2024-01-10T12:00:00Z")
    case("predict-local/station-zone", "to_local() on extremes at America/New_York, Europe/Oslo and Australia/Lord_Howe stations, across "
         "a daylight-saving change; tz is the station's zone, resolved", "4.1, 5.3",
         [to_local(extremes(B, "2021-03-13T12:00:00Z", "2021-03-15T00:00:00Z")),
          to_local(extremes("OTC-P-0002", "2022-10-29T12:00:00Z", "2022-10-31T00:00:00Z")),
          to_local(extremes("OTC-P-0003", "2023-04-01T00:00:00Z", "2023-04-02T12:00:00Z"))],
         requires=("predict", "localtime"))
    case("predict-local/named-zone", "to_local(Asia/Kolkata) and to_local(Pacific/Chatham) (+5:30; +13:45 and +12:45)", "4.1",
         [to_local(extremes(B, "2024-01-10T00:00:00Z", "2024-01-11T00:00:00Z"), "Asia/Kolkata"),
          to_local(extremes(B, "2024-04-06T00:00:00Z", "2024-04-07T12:00:00Z"), "Pacific/Chatham")],
         requires=("predict", "localtime"))
    case("predict-local/unknown-zone", "unknown_time_zone for Mars/Olympus, XYZ3, posix/, right/, posixrules, localtime and Factory", "4.1",
         [small] + [tl_error(z, "unknown_time_zone", {"zone": z}) for z in
                    ("Mars/Olympus", "XYZ3", "posix/Europe/Oslo", "right/Europe/Oslo", "posixrules", "localtime", "Factory")]
         + [to_local(extremes("OTC-P-0002", "2024-01-10T00:00:00Z", "2024-01-10T12:00:00Z"), "Europe/Oslo")],
         requires=("predict", "localtime"),
         note="the last step: Europe/Oslo, a link to Europe/Berlin in tzdata 2026e, is accepted (in C a symbolic link)")
    case("predict-local/missing-dependency", "without the optional dependency, to_local is local_time_unavailable", "4.1, 5.4",
         [to_local(small, expect_if_missing={"localtime": {"error": LH}})],
         requires=("predict", "localtime_module"))
    case("predict-local/missing-tzdir", "C: TZDIR set to a path that does not exist: local_time_unavailable naming the directory", "4.1",
         [{"driver": "restart_runner", "env": {"TZDIR": "${tmp}/no-such-zoneinfo"}},
          to_local(small, error=LH, error_message={"$contains": "no-such-zoneinfo"})],
         requires=("predict", "localtime", "tzdir_env"))
    case("predict-local/not-built", "C without the local-time module: not_built; with the module but no zone rules: "
         "local_time_unavailable", "4.1, 5.1",
         [to_local(small, expect_if_missing={"localtime_module": {"error": "not_built"}, "localtime": {"error": LH}})])
    fmt_utc = heights(B, "2022-06-01T22:00:00Z", "2022-06-02T02:00:00Z", 3600)
    fmt_osl = heights("OTC-P-0002", "2023-03-25T22:00:00Z", "2023-03-26T03:00:00Z", 3600)
    case("predict-local/format", "UTC ends in +00:00, not Z; local midnight is hour 00, not 24 (Europe/Oslo across its spring change)", "4.1",
         [to_local(fmt_utc, "UTC", local_items=[
             {"time": "2022-06-01T22:00:00Z", "local_time": "2022-06-01T22:00:00+00:00", "utc_offset_s": 0},
             {"time": "2022-06-01T23:00:00Z", "local_time": "2022-06-01T23:00:00+00:00", "utc_offset_s": 0},
             {"time": "2022-06-02T00:00:00Z", "local_time": "2022-06-02T00:00:00+00:00", "utc_offset_s": 0},
             {"time": "2022-06-02T01:00:00Z", "local_time": "2022-06-02T01:00:00+00:00", "utc_offset_s": 0}]),
          to_local(fmt_osl, None, local_items=[
              {"time": "2023-03-25T22:00:00Z", "local_time": "2023-03-25T23:00:00+01:00", "utc_offset_s": 3600},
              {"time": "2023-03-25T23:00:00Z", "local_time": "2023-03-26T00:00:00+01:00", "utc_offset_s": 3600},
              {"time": "2023-03-26T00:00:00Z", "local_time": "2023-03-26T01:00:00+01:00", "utc_offset_s": 3600},
              {"time": "2023-03-26T01:00:00Z", "local_time": "2023-03-26T03:00:00+02:00", "utc_offset_s": 7200},
              {"time": "2023-03-26T02:00:00Z", "local_time": "2023-03-26T04:00:00+02:00", "utc_offset_s": 7200}])],
         requires=("predict", "localtime"))
    # ------------------------------------------------------------------ datums (the datums spec's DT8 cases)
    def level(datum_obj, key):
        d = datum_obj
        b = d["basis"][key]
        cd = d.get("chart_datum")
        ctl = b.get("control") or {}
        ep = b.get("epoch")
        return {"key": key, "value_m": d["named"][key],
                "above_chart_m": d["named"][key] - d["named"][cd] if cd else None,
                "kind": b["kind"], "method": b["method"], "source_name": b.get("source_name"),
                "epoch": None if ep is None else {"start": ep["start"], "end": ep["end"], "name": ep.get("name")},
                "data_span": b.get("data_span"), "control_station_id": ctl.get("station_id"), "control_set_id": ctl.get("set_id"),
                "control_source_id": ctl.get("source_id"), "uncertainty_m": b.get("uncertainty_m"),
                "uncertainty_basis": b.get("uncertainty_basis"), "flags": b.get("flags", [])}

    def info(set_id, d):
        d = d or {}
        return {"set_id": set_id, "zero": d.get("zero"), "zero_name": d.get("zero_name"), "chart_datum": d.get("chart_datum"),
                "msl_offset_m": d.get("msl_offset_m"), "levels": [level(d, k) for k in sorted(d.get("named", {}))]}

    def ranges(cs):
        d = cs["datum"]

        def rng(a, b):
            ba, bb = d["basis"].get(a), d["basis"].get(b)
            if not ba or not bb or ba["kind"] != bb["kind"] or ba.get("epoch") != bb.get("epoch"):
                return None
            return d["named"][a] - d["named"][b]
        return {"mn": rng("mhw", "mlw"), "gt": rng("mhhw", "mllw"), "dhq": rng("mhhw", "mhw"), "dlq": rng("mlw", "mllw")}

    vz = next(c for c in cases if c["id"] == "predict-datum/vertical-zero")
    vz["steps"][1]["expect"] = {"datums": info("OTC-P-0052/rws", P.set("OTC-P-0052/rws").get("datum"))}
    bset = P.set("OTC-P-0001/noaa")
    case("predict-datums/list", "datums(): the recommended set's levels in key order, with their basis", "datums spec 7.1",
         [{"op": "datums", "args": {"station_id": B}, "expect": {"datums": info(bset["set_id"], bset.get("datum"))}, "strict": None}])
    case("predict-datums/all-sets", "datums(all_sets: true): one DatumInfo per set, in file order", "datums spec 7.1",
         [{"op": "datums", "args": {"station_id": B, "all_sets": True},
           "expect": {"datums": [info(cs["set_id"], cs.get("datum")) for cs in P.st[B]["constant_sets"]]}, "strict": None}])
    case("predict-datums/ranges", "ranges(): MN, GT, DHQ, DLQ from levels of the same kind and epoch", "datums spec 7.1",
         [{"op": "ranges", "args": {"station_id": B}, "expect": {"ranges": ranges(bset)}, "strict": None}])
    case("predict-datums/ranges-mixed-kinds", "a range from levels of different kinds or epochs is refused (null)", "datums spec 7.1",
         [{"op": "ranges", "args": {"station_id": "OTC-P-0054"}, "expect": {"ranges": ranges(P.set("OTC-P-0054/noaa"))}, "strict": None}])
    sdat = P.st["OTC-P-0035"]["subordinate_offsets"]["datum"]
    case("predict-datum/subordinate-named", "datum mhhw at a folded subordinate: above chart + named[chart_datum] - named[mhhw]; "
         "datums() returns subordinate_offsets.datum", "4.8 step 5; datums spec 7.1",
         [sub_tide("heights_at", "OTC-P-0035", None, datum="mhhw", times=["2010-03-01T03:00:00Z"],
                   expect={"datum": "mhhw", "datum_name": "mhhw", "datum_kind": "published"}),
          error("heights_at", "datum_unavailable", station_id="OTC-P-0035", times=["2010-03-01T03:00:00Z"], datum="lat"),
          {"op": "datums", "args": {"station_id": "OTC-P-0035"}, "strict": None, "expect": {"datums": info(None, sdat)}}])
    case("predict-datum/subordinate-reference-wrong-source", "the reference has only a gesla-fit set (with an observed mllw): "
         "reference_unavailable", "4.8 step 1; datums spec DT8",
         [error("extremes", "reference_unavailable", fields={"reference_station_id": "OTC-P-0048"}, station_id="OTC-P-0049",
                start=W2[0], stop=W2[1])])
    case("predict-datum/subordinate-unpublished-chart", "the reference's noaa set has a computed (not published) chart datum: "
         "datum_unavailable", "4.8 step 2; datums spec DT8",
         [error("extremes", "datum_unavailable", station_id="OTC-P-0047", start=W2[0], stop=W2[1])])
    # ------------------------------------------------------------------ astro tables
    ta = P.doc["astro_tables"][0]

    def eq_arg(name, at):
        t = _t(at)
        y = datetime.datetime.fromtimestamp(t, tz=datetime.timezone.utc).year
        i = y - ta["first_year"]
        r = ta["constituents"][name]
        x = r["v0u_deg"][i] + r["speed_deg_per_hour"] * ((t - _t(f"{y}-01-01T00:00:00Z")) / 3600.0)
        x = x - 360.0 * math.floor(x / 360.0)
        return 0.0 if x == 360.0 else x

    def nf(name, at):
        y = int(at[:4])
        return ta["constituents"][name]["f"][y - ta["first_year"]]

    ast = []
    tbl = lambda t: {"first_year": t["first_year"], "last_year": t["last_year"]}   # the AstroTable accessors (spec 5.2)
    ast.append({"op": "astro_table", "args": {}, "expect": {"astro_table": tbl(ta)}, "strict": None})
    ast.append({"op": "astro_table", "args": {"id": ASTRO_B}, "expect": {"astro_table": tbl(P.doc["astro_tables"][1])}, "strict": None})
    ast.append({"op": "astro_table", "args": {"id": "no-such-table"}, "expect": {"astro_table": None}, "strict": None})
    for at in ("2000-01-01T00:00:00Z", "2015-06-01T12:34:56Z", "2030-12-31T23:59:59Z"):
        for name in ("M2", "K1"):
            ast.append({"op": "equilibrium_argument", "args": {"name": name, "at": at}, "expect": {"value": eq_arg(name, at)}, "strict": None})
            ast.append({"op": "node_factor", "args": {"name": name, "at": at}, "expect": {"value": nf(name, at)}, "strict": None})
    for y in (2000, 2015, 2030):
        ast.append({"op": "equilibrium_for_year", "args": {"name": "M2", "year": y},
                    "expect": {"value": ta["constituents"]["M2"]["v0u_deg"][y - 2000]}, "strict": None})
        ast.append({"op": "node_factor_for_year", "args": {"name": "M2", "year": y},
                    "expect": {"value": ta["constituents"]["M2"]["f"][y - 2000]}, "strict": None})
    ast.append({"op": "equilibrium_argument", "args": {"id": ASTRO_B, "name": "K1", "at": "2099-12-31T23:59:59Z"},
                "expect": {"value": None}, "strict": None})   # replaced below with table B's value
    ast.append({"op": "valid_range", "args": {}, "expect": {"first_year": 2000, "last_year": 2030}, "strict": None})
    ast.append({"op": "valid_range", "args": {"id": ASTRO_B}, "expect": {"first_year": 2020, "last_year": 2100}, "strict": None})
    for op, a in (("equilibrium_argument", {"at": "2015-06-01T00:00:00Z"}), ("node_factor", {"at": "2015-06-01T00:00:00Z"}),
                  ("equilibrium_for_year", {"year": 2015}), ("node_factor_for_year", {"year": 2015})):
        ast.append(error(op, "unsupported_constituent", fields={"constituent": "ZZ9"}, name="ZZ9", **a))
    for op, a in (("equilibrium_argument", {"at": "1999-12-31T23:59:59Z"}), ("node_factor", {"at": "2031-01-01T00:00:00Z"}),
                  ("equilibrium_for_year", {"year": 1999}), ("node_factor_for_year", {"year": 2031})):
        ast.append(error(op, "time_out_of_range", fields=oor, name="M2", **a))
    tb = P.doc["astro_tables"][1]
    kb = tb["constituents"]["K1"]
    xb = kb["v0u_deg"][2099 - tb["first_year"]] + kb["speed_deg_per_hour"] * ((_t("2099-12-31T23:59:59Z") - _t("2099-01-01T00:00:00Z")) / 3600.0)
    xb = xb - 360.0 * math.floor(xb / 360.0)
    next(a for a in ast if a["args"].get("id") == ASTRO_B and a["op"] == "equilibrium_argument")["expect"]["value"] = 0.0 if xb == 360.0 else xb
    case("predict-astro-values", "every Astro function inside the range and at its edges, on table A and table B; no row: "
         "unsupported_constituent; out of range: time_out_of_range", "5.2", ast,
         note="the values are the table's, by the formulas of 5.2 (hand-written)")
    neg_msg = lambda row: {"$all": [{"$contains": ASTRO_A}, {"$contains": row}]}
    p5 = {"$set": "OTC-P-0005/noaa"}
    case("predict-astro-negative-speed/used-row", "M2's row speed is negative: heights, extremes, current_events and astro_table are "
         "invalid_argument naming the table and the row", "4.2a",
         [error("heights", "invalid_argument", message=neg_msg("M2"), station_id="OTC-P-0005", start=D + "00:00:00Z", stop=D + "01:00:00Z",
                strict={"entry": "predict_strict", "args": {"constituents": p5, "times": [D + "00:00:00Z"], "datum_term": 0.0,
                                                            "astro": ASTRO_A}}),
          error("extremes", "invalid_argument", message=neg_msg("M2"), station_id="OTC-P-0005", start=D + "00:00:00Z", stop=D + "12:00:00Z",
                strict={"entry": "extremes_strict", "args": {"constituents": p5, "start": D + "00:00:00Z", "stop": D + "12:00:00Z",
                                                             "datum_term": 0.0, "astro": ASTRO_A}}),
          error("current_events", "invalid_argument", message=neg_msg("M2"), station_id="OTC-P-0016", start=D + "00:00:00Z",
                stop=D + "12:00:00Z", bin_number=1,
                strict={"entry": "current_events_strict", "args": {"bin": {"$bin": ["OTC-P-0016/noaa", 1]}, "start": D + "00:00:00Z",
                                                                   "stop": D + "12:00:00Z", "astro": ASTRO_A}}),
          error("astro_table", "invalid_argument", message=neg_msg("M2"))], root="predict-bad/astro-negative-speed")
    case("predict-astro-negative-speed/unused-row", "a negative speed on a row that no set uses: heights on a set without it still fails",
         "4.2a", [error("heights", "invalid_argument", message=neg_msg("MN4"), station_id="OTC-P-0005", start=D + "00:00:00Z",
                        stop=D + "01:00:00Z", strict={"entry": "predict_strict", "args": {"constituents": p5, "times": [D + "00:00:00Z"],
                                                                                          "datum_term": 0.0, "astro": ASTRO_A}})],
         root="predict-bad/astro-negative-speed-unused")
    case("predict-astro-negative-speed/short-v0u", "a v0u_deg array one entry short: invalid_argument", "4.2a",
         [error("heights", "invalid_argument", message={"$contains": ASTRO_A}, station_id="OTC-P-0005", start=D + "00:00:00Z",
                stop=D + "01:00:00Z", strict={"entry": "predict_strict", "args": {"constituents": p5, "times": [D + "00:00:00Z"],
                                                                                  "datum_term": 0.0, "astro": ASTRO_A}})],
         root="predict-bad/astro-short-v0u")
    # ------------------------------------------------------------------ metadata
    ALG = {"release": PREDICT_D, "algorithm": "otc-predict-1"}
    case("predict-metadata", "every result field of 5.3: harmonic heights, folded heights, currents and subordinate current events", "5.3",
         [heights(B, D + "00:00:00Z", D + "01:00:00Z", datum="chart", expect=dict(
             station_id=B, timezone="America/New_York", method="harmonic", set_id="OTC-P-0001/noaa", convention_id=CONV_G,
             astro_table_id=ASTRO_A, reference_station_id=None, reference_bin=None, datum="chart", datum_name="mllw",
             datum_kind="published", datum_uncertainty_m=0.01, bin_number=None, omitted_event_types=None, tz=None, tz_version=None, **ALG)),
          sub_tide("heights", "OTC-P-0035", D + "00:00:00Z", D + "01:00:00Z", expect=dict(
              station_id="OTC-P-0035", timezone="America/New_York", method="folded_offsets", set_id="OTC-P-0001/noaa",
              convention_id=CONV_G, astro_table_id=ASTRO_A, reference_station_id=B, reference_bin=None, datum=None, datum_name="mllw",
              datum_kind="published", datum_uncertainty_m=None, bin_number=None, omitted_event_types=None, **ALG)),
          currents("OTC-P-0016", D + "00:00:00Z", D + "01:00:00Z", expect=dict(
              station_id="OTC-P-0016", method="harmonic", set_id="OTC-P-0016/noaa", convention_id=CONV_G, astro_table_id=ASTRO_A,
              reference_station_id=None, reference_bin=None, datum=None, datum_name=None, datum_kind=None, datum_uncertainty_m=None,
              bin_number=2, omitted_event_types=None, **ALG)),
          sub_current_events("OTC-P-0051", D + "00:00:00Z", "2010-03-02T00:00:00Z", expect=dict(
              station_id="OTC-P-0051", method="offsets", set_id="OTC-P-0016/noaa", reference_station_id="OTC-P-0016", reference_bin=1,
              bin_number=1, omitted_event_types=["max_ebb", "slack_before_ebb"], datum=None, datum_name=None, **ALG))])
    # ------------------------------------------------------------------ not built (C without otc_predict)
    nb = {"predict": {"error": "not_built"}}
    for fn, st in (("otc_heights", heights(B, D + "00:00:00Z", D + "01:00:00Z")),
                   ("otc_heights_at", heights_at(B, [D + "00:00:00Z"])),
                   ("otc_extremes", extremes(B, D + "00:00:00Z", D + "12:00:00Z")),
                   ("otc_currents", currents("OTC-P-0016", D + "00:00:00Z", D + "01:00:00Z")),
                   ("otc_current_events", current_events("OTC-P-0016", D + "00:00:00Z", D + "12:00:00Z")),
                   ("otc_astro_table", ast[0]), ("otc_astro_equilibrium_argument", ast[3]), ("otc_astro_node_factor", ast[4]),
                   ("otc_astro_equilibrium_for_year", next(a for a in ast if a["op"] == "equilibrium_for_year")),
                   ("otc_astro_node_factor_for_year", next(a for a in ast if a["op"] == "node_factor_for_year")),
                   ("otc_astro_valid_range", next(a for a in ast if a["op"] == "valid_range"))):
        case(f"not-built/{fn}", f"C built without otc_predict: {fn} returns not_built", "5.1",
             [dict(st, expect_if_missing=nb)], requires=())
    # ------------------------------------------------------------------ commercial_only (knc-predict)
    K9 = ("2099-03-01T00:00:00Z", "2099-03-03T00:00:00Z")
    without = {"op": "open", "matrix_open": {"commercial_only": None}, "strict": None}
    case("predict-commercial-only/effective-set", "heights at OTC-T-0181 use the effective set w-ok; without the option, x-nc", "4.2 step 1",
         [heights("OTC-T-0181", *K9, R=K, chosen="OTC-T-0181/w-ok", expect={"set_id": "OTC-T-0181/w-ok"}),
          without, heights("OTC-T-0181", *K9, R=K, expect={"set_id": "OTC-T-0181/x-nc"})],
         root="knc-predict", open_args={"commercial_only": True})
    case("predict-commercial-only/explicit-nc-set", "set_id OTC-T-0181/x-nc with the option is invalid_argument naming commercial_only; "
         "without it, it predicts", "4.2 step 1",
         [error("heights", "invalid_argument", message={"$contains": "commercial_only"}, station_id="OTC-T-0181", start=K9[0],
                stop=K9[1], set_id="OTC-T-0181/x-nc"),
          without, heights("OTC-T-0181", *K9, R=K, set_id="OTC-T-0181/x-nc")],
         root="knc-predict", open_args={"commercial_only": True})
    case("predict-commercial-only/no-constants", "heights at OTC-T-0183 is no_constants naming commercial_only", "4.2 step 2",
         [error("heights", "no_constants", message={"$contains": "commercial_only"}, station_id="OTC-T-0183", start=K9[0], stop=K9[1])],
         root="knc-predict", open_args={"commercial_only": True})
    case("predict-commercial-only/offsets-usable", "extremes at OTC-T-0186 and OTC-T-0190 predict by folded offsets from OTC-T-0185/a-noaa",
         "4.2, 4.8a", [sub_tide("extremes", "OTC-T-0186", *K9, R=K), sub_tide("extremes", "OTC-T-0190", *K9, R=K)],
         root="knc-predict", open_args={"commercial_only": True})
    case("predict-commercial-only/offsets-nc-licence", "extremes at OTC-T-0187 (offsets licence nc-test-2) is reference_unavailable",
         "4.2, 4.8", [error("extremes", "reference_unavailable", message={"$contains": "nc-test-2"},
                            fields={"reference_station_id": "OTC-T-0185"}, station_id="OTC-T-0187", start=K9[0], stop=K9[1])],
         root="knc-predict", open_args={"commercial_only": True})
    case("predict-commercial-only/reference-set-nc", "extremes at OTC-T-0188: the reference set is x-nc (first noaa set in file order), "
         "so reference_unavailable naming nc-test; without the option it predicts from x-nc", "4.2, 4.8 step 1",
         [error("extremes", "reference_unavailable", message={"$contains": "nc-test"}, fields={"reference_station_id": "OTC-T-0181"},
                station_id="OTC-T-0188", start=K9[0], stop=K9[1]),
          without, sub_tide("extremes", "OTC-T-0188", *K9, R=K, expect={"set_id": "OTC-T-0181/x-nc"})],
         root="knc-predict", open_args={"commercial_only": True})
    case("predict-commercial-only/own-set-wins", "heights at OTC-T-0189 use its own set a-ok; its offsets are not used", "4.2",
         [heights("OTC-T-0189", *K9, R=K, expect={"set_id": "OTC-T-0189/a-ok"})],
         root="knc-predict", open_args={"commercial_only": True})
    case("predict-commercial-only/current-offsets-nc", "current_events at OTC-T-0191 (entry licence nc-test) is reference_unavailable; "
         "without the option it predicts from OTC-T-0181/z-current", "4.9 step 1",
         [error("current_events", "reference_unavailable", message={"$contains": "nc-test"},
                fields={"reference_station_id": "OTC-T-0181"}, station_id="OTC-T-0191", start=K9[0], stop=K9[1], bin_number=1),
          without, sub_current_events("OTC-T-0191", *K9, bin_number=1, R=K)],
         root="knc-predict", open_args={"commercial_only": True})
    case("predict-commercial-only/current-offsets-usable", "current_events at OTC-T-0192 predict by offsets from OTC-T-0181/z-current",
         "4.9", [sub_current_events("OTC-T-0192", *K9, bin_number=1, R=K)],
         root="knc-predict", open_args={"commercial_only": True})
    return {"calls_version": 1,
            "description": "Every prediction case of the prediction spec (revision 28) section 6.5 as calls on the fixture roots, "
                           "with the hand-written expectations. Generated by conformance/tools/build_fixtures.py; do not edit. "
                           "Steps with \"strict\" take their numbers from the reference engine's strict mode (KP1-H writes "
                           "predict_expected.json); K2b-pin merges both into conformance/cases/predict-*.json.",
            "interface": CALLS_INTERFACE, "cases": cases}


CALLS_INTERFACE = {
    "k2": "The ops, their arguments and their results are K2's (conformance/driver.py OPS and conformance/README.md "
          "\"Operations\" and \"Result encodings\" at K2 343fbe3): prediction results are {prediction: Prediction}, datums "
          "{datums: DatumInfo or [DatumInfo]}, ranges {ranges: Ranges}, astro_table {astro_table: {first_year, last_year} or "
          "null}, the astro functions {value}, valid_range {first_year, last_year}. The case-level runners filter and "
          "\"localtime implies localtime_module\" are K2's too.",
    "case": "{id, title, spec, root, release, requires, steps, runners?, open_args?, note?}. root is a fixture root (fixtures.json); "
            "requires are runner features; runners (K2's case-level filter) are the only runners or profiles that run the case; "
            "open_args are matrix.open_args.",
    "expect_if_missing": "An ordered list of [feature, expectation] pairs: K2's driver takes the first feature the runner "
                         "lacks, so K2b-pin writes them as an object in this order (predict-local/not-built: localtime_module "
                         "before localtime, since a runner without the module lacks both).",
    "step": "{op, args, expect?, expect_if_missing?, strict, outcome?, compare?, local?, same_items_as_step?, swap_of?} or a "
            "driver step ({driver: restart_runner, env}) or {op: open, matrix_open}. expect is what the driver compares, in "
            "K2's encoding: a prediction step's expect.prediction holds every Prediction field except items, which K2b-pin "
            "takes from the strict mode (each item with local_time and utc_offset_s null unless to_local), or items when they "
            "are written here (an empty window). An expect with error and a non-null strict is a modelled refusal: the case "
            "harness checks that the strict mode raises the same code.",
    "outcome": "Hand-written outcomes the spec fixes exactly, which K2b-pin checks against the strict items before it pins "
               "them: {count: n} (the number of items), or {items: [{time, type}]} (exactly these, in order), optionally "
               "with types: [...] (compare only the items of those types).",
    "compare": "{entry, args, time_s, height_m}: a second strict computation the step's items must equal within these "
               "tolerances (subordinate-folded-extremes: the event method of 4.8, spec 4.8a).",
    "to_local": "A to_local step converts the result of the case's most recent prediction step (K2): args {tz} (absent = the "
                "station's zone). Its expect.prediction has tz, the resolved zone name, and tz_version, a version or null. "
                "strict.same_as_step names the step whose strict items it converts; local.zone is the zone K2b-pin uses to "
                "add local_time and utc_offset_s; local.check lists hand-written values they must equal.",
    "same_items_as_step": "The step's items equal that step's (heights-fractional-instants: the floored instants).",
    "swap_of": "{case, step}: the items are that step's with high and low swapped and each height negated "
               "(extremes-negative-amplitude; the strict mode refuses a negative amplitude).",
    "times": "RFC 3339 UTC strings YYYY-MM-DDTHH:MM:SS(.fff)Z; a naive datetime has no Z (Python only). Result times are whole "
             "seconds YYYY-MM-DDTHH:MM:SSZ.",
    "prediction_fields": "station_id, timezone, method, set_id, convention_id, astro_table_id, reference_station_id, reference_bin, "
                         "datum, datum_name, datum_kind, datum_uncertainty_m, bin_number, omitted_event_types, tz, tz_version, "
                         "release, algorithm. Readings of 5.3 for revision 29: datum is the argument, null when absent; datum_name "
                         "is the resolved level's key (mean_level by default for a harmonic tide; for offsets the subordinate "
                         "datum's chart_datum key, null when it has none); datum_kind and datum_uncertainty_m are that level's "
                         "basis kind and uncertainty, null for mean_level, zero, or no basis; omitted_event_types is null except at "
                         "a subordinate current station.",
    "strict": {
        "entries": "webcaltides lib/harmonics_strict.rb (237446c) Engine methods: predict_strict(constituents, times, datum_term:), "
                   "extremes_strict(constituents, start, stop, datum_term:), currents_strict(bin, times), current_events_strict(bin, "
                   "start, stop), subordinate_extremes_strict(ref_constituents, chart_datum_term, offsets, start, stop, datum_shift:), "
                   "subordinate_current_events_strict(ref_bin, offset, start, stop); and two compositions: folded_heights = "
                   "subordinate_folded_strict(ref_constituents, chart_datum_term, offsets, datum_shift:) then predict_strict on its "
                   "constituents and datum_term at times; folded_extremes = the same then extremes_strict over start, stop. "
                   "{same_as_step: i}: the strict items of step i (to_local).",
        "references": "{$set: set_id} is that set's constituents; {$bin: [set_id, bin]} that bin object; {$offsets: station_id} "
                      "the station's subordinate_offsets; {$current_offset: [station_id, bin]} that current_offsets entry; astro is "
                      "the astro_tables entry with that id, passed as astro: Strict::AstroTable.from_h(entry). All in the case's root.",
        "crosscheck": "scan_5s (extremes: all events against the sign changes of h'; current events: the max_* events against "
                      "W' and the slack_* events against W), scan_5s_peaks (the max_* events only, against W'), scan_5s_slacks "
                      "(the slack_* events only, against W): the 5 s brute-force count of spec 6.1 that must equal the count",
    },
}


# --------------------------------------------------------------------------- the 6.3 bands (K2b-fixtures)
#
# Prediction spec 6.3 "Fixtures near a threshold": the conformance fixtures avoid four bands, and the case builder
# checks every fixture against them. band_problems() does that for every event step of predict_calls.json: it finds
# the roots of h' (extremes), W' and W (current events) over each step's padded grid with a sign scan refined by
# bisection, groups them as spec 4.6 step 6 does, and checks
#   1. no two consecutive roots of one search are 0.99 to 1.01 s apart (the close-root filter);
#   2. no same-type pair across a New Year is 3599 to 3601 s apart (step 6a);
#   3. no reported root, and no shifted time r + offset of 4.8 step 3 / 4.9 step 3, is within ROUND_BAND of a half
#      second (step 7; the spec's band is 0.01 s, and a bisection stops within 0.005 s of the root);
#   4. h' (or W', W) is not within 1e-9 of zero at a New Year instant (the sign test of step 6a).
# The scan uses math.sin and math.cos, so it checks; it never writes a fixture. A step on a designed close-root station
# (a set or bin with a made-up row faster than RIPPLE_SPEED) is left to conformance/tests/test_build_fixtures_predict.py,
# whose 0.01 s design scans check the same bands for those events: a scan of its padded grid here would take minutes.

ROUND_BAND = 0.01   # spec 6.3: within 0.01 s of a half second
# Cases the bands cannot be met for, each with the reason; --check prints them and refuses any other band problem.
# extremes-single-constituent: M2 alone over the fixed 30 days gives 116 extremes whose fractional seconds step by
# about 0.08 s, so the largest gap between them is 0.0136 s and no phase keeps every one 0.01 s from a half second.
# Raised for the prediction spec (revision 29); not decided here.
BAND_EXCEPTIONS = {"predict-extremes/single-constituent": "spec 6.3 band 3 vs 6.5's fixed M2-only 30-day window (revision 29)"}
RIPPLE_SPEED = 360.0   # degrees per hour: a period under an hour


def _ripple(table, names):
    return any(table["constituents"][n]["speed_deg_per_hour"] > RIPPLE_SPEED for n in names)


def _bsum(table, terms):
    """terms [(name, amplitude, phase)] -> (value(t, y), derivative(t, y)) per spec 4.4, with year y's tables."""
    first = table["first_year"]
    rows = table["constituents"]

    def coeffs(y):
        i = y - first
        if isinstance(i, float) and i.is_integer():  # JSON Schema integer also permits a number such as 2000.0
            i = int(i)
        if not 0 <= i <= table["last_year"] - first:
            raise ValueError(f"year {y} outside astro table {table['astro_table_id']}")
        return [(rows[n]["speed_deg_per_hour"], rows[n]["v0u_deg"][i], rows[n]["f"][i] * a, g) for n, a, g in terms]

    cache = {}

    def get(y):
        if y not in cache:
            cache[y] = (_t(f"{y}-01-01T00:00:00Z"), coeffs(y))
        return cache[y]

    def value(t, y):
        y0, c = get(y)
        d = (t - y0) / 3600.0
        return sum(fa * math.cos(((w * d + a - g) % 360.0) * math.pi / 180) for w, a, fa, g in c)

    def deriv(t, y):
        y0, c = get(y)
        d = (t - y0) / 3600.0
        return -sum(fa * w * math.pi / 180 * math.sin(((w * d + a - g) % 360.0) * math.pi / 180) for w, a, fa, g in c)
    return value, deriv


def _year(t):
    return datetime.datetime.fromtimestamp(math.floor(t), tz=datetime.timezone.utc).year


def _scan_roots(f, a, b, dt, y):
    """Sign changes of f(t, y) on [a, b], refined to 1e-6 s (a double near 1.3e9 s has steps of 2.4e-7 s, so the
    bisection also stops when the midpoint no longer moves): [(r, 'down'|'up')]."""
    out = []
    n = max(1, int(math.ceil((b - a) / dt)))
    pt, pv = a, f(a, y)
    for k in range(1, n + 1):
        t = min(b, a + k * dt)
        v = f(t, y)
        if (pv > 0 and v <= 0) or (pv < 0 and v >= 0):
            kind = "down" if pv > 0 else "up"
            lo, hi = pt, t
            while hi - lo > 1e-6:
                m = (lo + hi) / 2
                if m <= lo or m >= hi:
                    break
                fm = f(m, y)
                if (fm > 0) if kind == "down" else (fm < 0):
                    lo = m
                else:
                    hi = m
            out.append(((lo + hi) / 2, kind))
        pt, pv = t, v
    return out


def _search(f, value, lo, hi, dt, problems, label, slack=False):
    """The candidates of one search (spec 4.6 steps 1-6a, 4.7) over [lo, hi], year by year, with bands 1, 2 and 4.
    Returns the survivors [(r, kind, value)] (leaf cancellation is not modelled: a conservative superset)."""
    cands = []
    edges = [lo] + [_t(f"{y}-01-01T00:00:00Z") for y in range(_year(lo) + 1, _year(hi) + 1)] + [hi]
    for a, b in zip(edges, edges[1:]):
        y = _year(a)
        cands += [(r, k, value(r, y), y) for r, k in _scan_roots(f, a, b, dt, y) if r < b or b == hi]
    cands.sort()
    for T in edges[1:-1]:   # 6a
        y = _year(T) - 1
        so, sn = f(T, y), f(T, y + 1)
        if abs(so) < 1e-9 or abs(sn) < 1e-9:
            problems.append(f"{label}: band 4: the search function is within 1e-9 of zero at New Year {_iso(T)}")
            continue
        if (so > 0) == (sn > 0):
            continue
        li = max((i for i, c in enumerate(cands) if c[0] <= T), default=None)
        ri = li + 1 if li is not None else 0
        L, R = (cands[li] if li is not None else None), (cands[ri] if ri < len(cands) else None)
        if L and R and 3599 <= R[0] - L[0] <= 3601:
            problems.append(f"{label}: band 2: a same-type pair {R[0] - L[0]:.3f} s apart across {_iso(T)}")
        if L and R and R[0] - L[0] < 3600:
            if slack:
                del cands[ri]
            else:
                keep_l = not ((R[2] > L[2]) if L[1] == "down" else (R[2] < L[2]))
                del cands[ri if keep_l else li]
        else:
            kind = ("up" if sn > 0 else "down") if slack else ("down" if so > 0 else "up")
            cands.insert(ri, (float(T), kind, value(T, y + 1), y + 1))
    for x, z in zip(cands, cands[1:]):
        if 0.99 <= z[0] - x[0] <= 1.01:
            problems.append(f"{label}: band 1: roots {z[0] - x[0]:.4f} s apart at {_iso(math.floor(x[0]))}")
    out, i = [], 0
    while i < len(cands):
        j = i
        while j + 1 < len(cands) and cands[j + 1][0] - cands[j][0] < 1.0:
            j += 1
        cl = cands[i:j + 1]
        if len(cl) % 2:
            if slack:
                out.append(cl[2 * ((len(cl) - 1) // 4)])
            else:
                same = [c for c in cl if c[1] == cl[0][1]]
                best = same[0]
                for c in same[1:]:
                    if (c[2] > best[2]) if c[1] == "down" else (c[2] < best[2]):
                        best = c
                out.append(best)
        i = j + 1
    return out


def _round_ok(t, label, problems, what="event"):
    frac = t - math.floor(t)
    if abs(frac - 0.5) < ROUND_BAND:
        problems.append(f"{label}: band 3: {what} at {_iso(math.floor(t))} + {frac:.4f} s is within {ROUND_BAND} s of a half second")


def _grid(start, stop):
    g0 = math.floor(start / 360) * 360 - 3600
    gn = g0 + math.ceil((stop + 3600 - g0) / 360) * 360
    return g0, gn


def _dt(table, names):
    fastest = max(table["constituents"][n]["speed_deg_per_hour"] for n in names)
    return min(5.0, 360.0 / fastest * 3600 / 50) if fastest > 0 else 5.0


def _tide_events(table, terms, start, stop, label, problems, report=True):
    value, deriv = _bsum(table, terms)
    g0, gn = _grid(start, stop)
    surv = _search(deriv, value, g0, gn, _dt(table, [n for n, _, _ in terms]), problems, label)
    if report:
        for r, k, v, y in surv:
            if start <= math.floor(r + 0.5) < stop:
                _round_ok(r, label, problems)
    return surv


def _current_events(table, b, start, stop, label, problems, report=True):
    terms = [(c["name"], c["major_amplitude_ms"], c["major_phase_deg"]) for c in b["constituents"]]
    value, deriv = _bsum(table, terms)
    flood = b.get("mean_flood_dir_deg")
    sigma = 1 if flood is None or math.cos(math.radians(b["azimuth_deg"] - flood)) >= 0 else -1
    mean = b.get("mean_major_ms", 0.0)
    w = lambda t, y: sigma * (mean + value(t, y))
    dw = lambda t, y: sigma * deriv(t, y)
    g0, gn = _grid(start, stop)
    dt = _dt(table, [n for n, _, _ in terms])
    peaks = [(r, "max_flood" if k == "down" else "max_ebb", v) for r, k, v, _ in
             _search(dw, w, g0, gn, dt, problems, label + " (peaks)") if (k == "down" and v > 0) or (k == "up" and v < 0)]
    slacks = [(r, "slack_before_flood" if k == "up" else "slack_before_ebb", 0.0) for r, k, _, _ in
              _search(w, lambda t, y: 0.0, g0, gn, dt, problems, label + " (slacks)", slack=True)]
    ev = sorted(peaks + slacks)
    if report:
        for r, k, _ in ev:
            if start <= math.floor(r + 0.5) < stop:
                _round_ok(r, label, problems)
    return ev


def band_problems(calls):
    """Every event step of the calls against the four bands of spec 6.3 (see above). Returns the problems."""
    docs = {}
    problems = []
    for c in calls["cases"]:
        if c["id"] in BAND_EXCEPTIONS:
            continue
        root = c["root"]
        if root not in docs:
            p = FIXTURES / root / f"OTC_{c['release']}.json"
            if not p.exists():
                continue
            docs[root] = json.loads(p.read_bytes())
        d = docs[root]
        tables = {t["astro_table_id"]: t for t in d.get("astro_tables", [])}
        st = {s["station_id"]: s for s in d["stations"]}
        sets = {cs["set_id"]: cs for s in d["stations"] for cs in s.get("constant_sets", [])}
        for i, s in enumerate(c["steps"]):
            strict = s.get("strict") or {}
            e, a = strict.get("entry"), strict.get("args") or {}
            if not e or (s.get("expect") or {}).get("error") or "start" not in a:
                continue
            label = f"{c['id']} step {i}"
            start, stop = _t(a["start"]), _t(a["stop"])
            if start == stop:
                continue
            table = tables.get(a.get("astro"))
            if table is None:
                continue
            terms = lambda ref: [(x["name"], x["amplitude_m"], x["phase_deg"]) for x in sets[ref]["constituents"]]
            used = [x["name"] for v in a.values() if isinstance(v, dict)
                    for x in (sets[v["$set"]]["constituents"] if "$set" in v else
                              next(b for b in sets[v["$bin"][0]]["current_bins"] if b["bin"] == v["$bin"][1])["constituents"]
                              if "$bin" in v else [])]
            if _ripple(table, used):
                continue
            if e == "extremes_strict":
                _tide_events(table, terms(a["constituents"]["$set"]), start, stop, label, problems)
            elif e == "current_events_strict":
                sid, n = a["bin"]["$bin"]
                _current_events(table, next(b for b in sets[sid]["current_bins"] if b["bin"] == n), start, stop, label, problems)
            elif e in ("subordinate_extremes_strict", "folded_extremes"):
                o = st[a["offsets"]["$offsets"]]["subordinate_offsets"]
                ident = 1 if o["height_adjusted_type"] == "R" else 0
                th, tl = o.get("time_offset_high_min", 0), o.get("time_offset_low_min", 0)
                ref = terms(a["ref_constituents"]["$set"])
                if e == "folded_extremes":
                    m = o.get("height_offset_high", ident) if o["height_adjusted_type"] == "R" else 1.0
                    rows = table["constituents"]
                    fold = [(n, m * amp, (g + rows[n]["speed_deg_per_hour"] * th / 60.0) % 360.0) for n, amp, g in ref]
                    _tide_events(table, fold, start, stop, label, problems)
                    continue
                pad = max(max(abs(th), abs(tl)) * 60 + 3600, 7200)
                for r, k, v, y in _tide_events(table, ref, start - pad, stop + pad, label + " (reference)", problems, report=False):
                    t = r + (th if k == "down" else tl) * 60
                    if start <= math.floor(t + 0.5) < stop:
                        _round_ok(t, label, problems, "shifted time")
            elif e == "subordinate_current_events_strict":
                sid, n = a["ref_bin"]["$bin"]
                osid, on = a["offset"]["$current_offset"]
                co = next(x for x in st[osid]["current_offsets"] if x["bin"] == on)
                adj = {"max_flood": ("time_adj_max_flood_min", "flood_amp_ratio"), "max_ebb": ("time_adj_max_ebb_min", "ebb_amp_ratio"),
                       "slack_before_flood": ("time_adj_slack_before_flood_min", None),
                       "slack_before_ebb": ("time_adj_slack_before_ebb_min", None)}
                kept = {k: co[x] for k, (x, ratio) in adj.items() if co.get(x) is not None and (ratio is None or co.get(ratio) is not None)}
                pad = max(max((abs(v) for v in kept.values()), default=0) * 60 + 3600, 7200)
                b = next(b for b in sets[sid]["current_bins"] if b["bin"] == n)
                for r, k, _ in _current_events(table, b, start - pad, stop + pad, label + " (reference)", problems, report=False):
                    if k in kept:
                        t = r + kept[k] * 60
                        if start <= math.floor(t + 0.5) < stop:
                            _round_ok(t, label, problems, "shifted time")
    return problems


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


def _finite_float(token):
    v = float(token)
    if not math.isfinite(v):
        raise ValueError(f"{token[:40]} is not a finite number")
    return v


def _finite_int(token):
    v = int(token)
    try:
        float(v)
    except OverflowError:
        raise ValueError(f"{token[:40]}... is not a finite number") from None
    return v


def _no_lone_surrogate(v):
    """A string with an unpaired surrogate (a \\ud800 escape alone) is not valid Unicode (CR D17)."""
    stack = [v]
    while stack:
        x = stack.pop()
        if isinstance(x, str):
            try:
                x.encode("utf-8")
            except UnicodeEncodeError:
                raise ValueError("a string with an unpaired surrogate") from None
        elif isinstance(x, dict):
            stack.extend(x.keys())
            stack.extend(x.values())
        elif isinstance(x, list):
            stack.extend(x)
    return v


def strict_json(text):
    """json.loads that refuses NaN and Infinity (they are not JSON, RFC 8259; Python accepts them), a number that
    is not finite as a double (1e400, an integer of 400 digits), and an unpaired surrogate (CR D17)."""
    return _no_lone_surrogate(json.loads(text, parse_constant=_not_json, parse_float=_finite_float, parse_int=_finite_int))


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


def time_range_errors(doc):
    """CR2 DR6: created and record_span times (already RFC 3339 by the schema) must stay in years 1 to 9999 once the
    offset is applied; the format checker does not check that."""
    times = [("release.created", doc["release"].get("created"))]
    for st in doc["stations"]:
        for cs in st.get("constant_sets", []):
            span = cs.get("record_span") or {}
            times += [(f"{cs['set_id']} record_span.{k}", span.get(k)) for k in ("start", "end")]
    errs = []
    for what, v in times:
        if isinstance(v, str):
            try:
                datetime.datetime.fromisoformat(v.replace("z", "Z")).astimezone(datetime.timezone.utc)
            except (ValueError, OverflowError):
                errs.append(f"{what} {v!r} is out of range in UTC")
    return errs


def cross_ref_errors(doc):
    errs = []
    for what, key in (("conventions", "convention_id"), ("licences", "licence_id")):
        ids = [x[key] for x in doc[what]]
        if len(ids) != len(set(ids)):
            errs.append(f"duplicate {key} in {what}")
    conv = {c["convention_id"] for c in doc["conventions"]}
    lic = {l["licence_id"] for l in doc["licences"]}
    table = {(c["constituent_table_version"], c["name"]) for c in doc["constituents"]}
    table_speed = {(c["constituent_table_version"], c["name"]): c["speed_deg_per_hour"] for c in doc["constituents"]}
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
            datum = cs.get("datum") or {}
            if set(datum.get("named", {})) != set(datum.get("basis", {})):
                errs.append(f"{cs['set_id']}: datum.basis and datum.named have different keys (build check 9)")
            names = [c["name"] for c in cs["constituents"]]
            if len(names) != len(set(names)):
                errs.append(f"{cs['set_id']}: a constituent name appears twice (CR2 DR22)")
            tv = conv_table.get(cs["convention_id"])
            current = [c for b in cs.get("current_bins", []) for c in b.get("constituents", [])]
            for c in cs["constituents"] + cs.get("dropped_constituents", []) + current:
                if tv and (tv, c["name"]) not in table:
                    errs.append(f"{cs['set_id']}: constituent {c['name']} not in table {tv}")
            at = conv_astro.get(cs["convention_id"])
            # build check 7 (spec 3.3): every constituent of the set, water level and current alike, has a row in its
            # convention's astro table, and the set's speed, the row's speed and the constituent table's speed agree
            # within 1e-7 deg/h, all three ways
            for c in cs["constituents"] + current:
                row = at["constituents"].get(c["name"]) if at else None
                if at and row is None:
                    errs.append(f"{cs['set_id']}: constituent {c['name']} not in astro table {at['astro_table_id']}")
                    continue
                legs = [("the set", c["speed_deg_per_hour"])]
                if row:
                    legs.append((f"astro table {at['astro_table_id']}", row["speed_deg_per_hour"]))
                if tv and (tv, c["name"]) in table_speed:
                    legs.append((f"constituent table {tv}", table_speed[(tv, c["name"])]))
                for (wa, a), (wb, b) in zip(legs, legs[1:] + legs[:1]):
                    if len(legs) > 1 and abs(a - b) > 1e-7:
                        errs.append(f"{cs['set_id']}: {c['name']} speed of {wa} ({a}) differs from {wb} ({b}) by more than 1e-7")
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
    # CR2 DR12: every file entry has a string sha256 and a non-negative integer size (the index schema requires both)
    for f in entry["files"]:
        size = f.get("size")
        if not isinstance(f.get("sha256"), str) or not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise Fail("invalid_release", f"{f.get('name')}: the entry needs a string sha256 and a size >= 0")
    sums_path = root / f"OTC_{datestamp}.sha256"
    sums = {}
    try:
        text = read_file(root, sums_path.name).decode("utf-8")
    except UnicodeDecodeError as e:   # CR2 DR14
        raise Fail("invalid_release", f"{sums_path.name}: not UTF-8: {e}") from None
    for line in text.splitlines():
        m = re.fullmatch(r"([0-9a-f]{64})  (\S.*)", line)
        if not m:
            raise Fail("checksum_mismatch", f"{sums_path.name}: a line that is not '<sha256>  <name>': {line[:80]!r}")
        if m.group(2) in sums:   # CR2 DR14: row order never decides a check
            raise Fail("invalid_release", f"{sums_path.name}: {m.group(2)} is listed twice")
        sums[m.group(2)] = m.group(1)
    # CR2 DR15: an eager download needs the .json row
    if f"OTC_{datestamp}.json.gz" in sums and f"OTC_{datestamp}.json" not in sums:
        raise Fail("checksum_mismatch", f"OTC_{datestamp}.json: not listed in {sums_path.name}")
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
        # one station per line; a line of only ASCII whitespace (bytes.strip) is blank and skipped (spec 6.2, CR2 DR26)
        lines = [strict_json(l.decode("utf-8")) for l in read_file(root, f"OTC_{datestamp}.jsonl").split(b"\n") if l.strip()]
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


def _restore_provider(doc):
    """The repair that makes a null licence provider valid again (CR D2 b): a copy with the provider a string."""
    doc = copy.deepcopy(doc)
    for x in doc.get("licences") or ():
        if isinstance(x, dict) and "provider" in x and x["provider"] is None:
            x["provider"] = "(null provider)"
    return doc


def sets_of(st):
    """The constant sets of a station that are objects (the schema reports the rest)."""
    sets = st.get("constant_sets") if isinstance(st, dict) else None
    return [cs for cs in sets if isinstance(cs, dict)] if isinstance(sets, list) else []


def tolerate_values(doc):
    """The values an SDK reads from a malformed 1.0 station, put right in a copy so that each is the only defect
    (review round 2, PK-R2-09). A set with no quantity (null or absent) gives the station the kind "other"
    (orchestrator S3); it is checked as a water_level set, or a current set when it has current_bins. A station
    line with no status (or null) is an active station (CR2 DR28).
    Returns (the copy, the tolerances)."""
    notes = []
    doc = copy.deepcopy(doc)
    for st in doc.get("stations") or []:
        if isinstance(st, dict) and st.get("status") is None:
            notes.append(f"{st.get('station_id')}: no status (read as active, CR2 DR28)")
            st["status"] = "active"
        if not isinstance(st, dict) or not isinstance(st.get("constant_sets"), list):
            continue
        for cs in st["constant_sets"]:
            if isinstance(cs, dict) and cs.get("quantity") is None:
                notes.append(f"{cs.get('set_id')}: no quantity (kind other, S3)")
                cs["quantity"] = "current" if "current_bins" in cs else "water_level"
    return doc, notes


def tolerate_prediction(doc, meta, lines):
    """What an SDK does not check when it loads a release, because it reads astro_tables and the constants only when
    it predicts (prediction spec 4.2 steps 5 and 6, 4.2a; 6.1: the SDKs are tolerant readers of range faults): a
    convention whose astro table is absent or not named, an astro-table row with a negative speed or an array of the
    wrong length, a constituent with no table row, a negative amplitude, and a current_offsets reference station that
    is not in the release (current_offsets are raw in 1.0, spec 4.9 step 1). Each is put right in a copy, so that it is
    the only defect, and listed (the bad prediction fixtures, root predict-bad). Returns (doc, meta, lines, notes)."""
    notes = []
    doc = copy.deepcopy(doc)
    tables = doc.get("astro_tables") if isinstance(doc.get("astro_tables"), list) else []
    by_id = {t.get("astro_table_id"): t for t in tables if isinstance(t, dict)}
    convs = [c for c in doc.get("conventions") or () if isinstance(c, dict)]
    for c in convs:
        if c.get("nodal_handling") == "f_u_at_prediction" and c.get("astro_table_id") not in by_id:
            notes.append(f"convention {c.get('convention_id')}: astro table {c.get('astro_table_id')!r} is absent "
                         "(found when it predicts: no_astro_table)")
            c["nodal_handling"] = "none"
            c.pop("astro_table_id", None)
    for t in by_id.values():
        rows = t.get("constituents")
        if not isinstance(rows, dict):
            continue   # not an object: the schema reports it
        first, last = t.get("first_year"), t.get("last_year")
        n = last - first + 1 if isinstance(first, int) and isinstance(last, int) else None
        for name, row in rows.items():
            if not isinstance(row, dict):
                continue
            sp = row.get("speed_deg_per_hour")
            if isinstance(sp, (int, float)) and not isinstance(sp, bool) and sp < 0:
                notes.append(f"astro table {t.get('astro_table_id')}: {name} speed {sp} is negative (found when it predicts)")
                row["speed_deg_per_hour"] = -sp
            for key in ("v0u_deg", "f"):
                arr = row.get(key)
                if n is not None and isinstance(arr, list) and arr and len(arr) != n:
                    notes.append(f"astro table {t.get('astro_table_id')}: {name} has {len(arr)} {key} values for {n} years "
                                 "(found when it predicts)")
                    row[key] = (arr + [arr[-1]] * n)[:n]
    conv_table = {c.get("convention_id"): by_id.get(c.get("astro_table_id")) for c in convs}
    speeds = {c.get("name"): c.get("speed_deg_per_hour") for c in doc.get("constituents") or () if isinstance(c, dict)}

    def fix_station(st, note):
        for cs in sets_of(st):
            table = conv_table.get(cs.get("convention_id"))
            consts = cs.get("constituents")
            for c in consts if isinstance(consts, list) else ():
                if not isinstance(c, dict):
                    continue
                amp = c.get("amplitude_m")
                if isinstance(amp, (int, float)) and not isinstance(amp, bool) and amp < 0:
                    if note:
                        notes.append(f"{cs.get('set_id')}: {c.get('name')} amplitude_m {amp} is negative (a range fault an SDK reads)")
                    c["amplitude_m"] = -amp
                rows = table.get("constituents") if isinstance(table, dict) else None
                if (isinstance(table, dict) and isinstance(rows, dict) and c.get("name") not in rows
                        and isinstance(speeds.get(c.get("name")), (int, float))):
                    if note:
                        notes.append(f"{cs.get('set_id')}: {c.get('name')} has no row in astro table "
                                     f"{table.get('astro_table_id')} (found when it predicts: unsupported_constituent)")
                    k = table["last_year"] - table["first_year"] + 1
                    rows[c["name"]] = {"speed_deg_per_hour": speeds[c["name"]], "v0u_deg": [0.0] * k, "f": [1.0] * k}
        return st

    active_ids = {st.get("station_id") for st in doc.get("stations") or () if isinstance(st, dict) and st.get("status") == "active"}

    def fix_current_refs(st, note):
        for co in st.get("current_offsets") if isinstance(st.get("current_offsets"), list) else ():
            if isinstance(co, dict) and isinstance(co.get("reference_station_id"), str) and co["reference_station_id"] not in active_ids:
                if note:
                    notes.append(f"{st.get('station_id')}: current_offsets reference {co['reference_station_id']} is not in the "
                                 "release (current_offsets are raw in 1.0; found when it predicts: reference_unavailable)")
                co["reference_station_id"] = st["station_id"]
        return st

    for st in doc.get("stations") or ():
        if isinstance(st, dict):
            fix_station(st, True)
            fix_current_refs(st, True)
    lines = [fix_current_refs(l, False) if isinstance(l, dict) else l for l in lines]
    lines = [fix_station(copy.deepcopy(l), False) if isinstance(l, dict) else l for l in lines]
    if notes and isinstance(meta, dict):
        meta = dict(meta, conventions=doc["conventions"])
        if "astro_tables" in doc:
            meta["astro_tables"] = doc["astro_tables"]
    return doc, meta, lines, notes


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
    if allow_missing_build:   # the general read rules of the SDKs: each is put right in a copy, and listed
        doc, tolerated = tolerate_values(doc)
        lines = [tolerate_values({"stations": [l]})[0]["stations"][0] if isinstance(l, dict) else l for l in lines]
        doc, meta, lines, notes = tolerate_prediction(doc, meta, lines)
        tolerated += notes
    # Spec 4.6: a set with no provenance.build is malformed, but the SDK loads it (build null).
    # only a provenance object without build: a set with no provenance at all is left to the schema (invalid_release)
    missing = [cs["set_id"] for st in doc["stations"] for cs in sets_of(st)
               if isinstance(cs.get("provenance"), dict) and "build" not in cs["provenance"]]
    if missing and allow_missing_build:
        tolerated += [f"no provenance.build in {m}" for m in missing]
        doc = restore_build(doc)
        meta = restore_build(meta)
        lines = [restore_station_build(l) for l in lines]
    # CR D2 b: a licence with a null provider is malformed, but the SDK loads it (the attribution prints its text
    # alone). The release is checked with a provider put back, so it is the only defect, and the tolerance is listed.
    nulls = [x.get("licence_id") for x in doc.get("licences") or () if isinstance(x, dict) and "provider" in x and x["provider"] is None]
    if nulls:
        tolerated += [f"licence {n}: provider null" for n in nulls]
        doc, meta = _restore_provider(doc), _restore_provider(meta)
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
        # A station whose status the schema does not have is read as "other": it is no station and no tombstone, so
        # it is not checked (CR2 DR8)
        known_status = schema["$defs"]["station"]["properties"]["status"]["enum"]
        for st in [x for x in checked["stations"] if x.get("status") not in known_status]:
            dropped.append(f"{st['station_id']}: status {st.get('status')!r} (read as other, listed nowhere)")
            checked["stations"].remove(st)
        # The same for a station type, a quantity and a source_type (CR2 DR7): checked with a known value in place
        known_type = schema["$defs"]["active_station"]["properties"]["type"]["enum"]
        set_enums = schema["$defs"]["constant_set"]["properties"]
        for st in checked["stations"]:
            if st.get("status") == "active" and st.get("type") not in known_type:
                dropped.append(f"{st['station_id']}: type {st.get('type')!r} (read as other)")
                st["type"] = "subordinate" if "subordinate_offsets" in st else "reference"
            off = st.get("subordinate_offsets")
            known_adj = schema["$defs"]["subordinate_offsets"]["properties"]["height_adjusted_type"]["enum"]
            if isinstance(off, dict) and off.get("height_adjusted_type") not in known_adj:
                dropped.append(f"{st['station_id']}: height_adjusted_type {off.get('height_adjusted_type')!r} (read as other)")
                off["height_adjusted_type"] = known_adj[0]
            for cs in st.get("constant_sets", []):
                if cs.get("quantity") is not None and cs["quantity"] not in set_enums["quantity"]["enum"]:
                    dropped.append(f"{cs['set_id']}: quantity {cs['quantity']!r} (read as other)")
                    cs["quantity"] = "current" if "current_bins" in cs else "water_level"
                if cs.get("source_type") not in set_enums["source_type"]["enum"]:
                    dropped.append(f"{cs['set_id']}: source_type {cs.get('source_type')!r} (read as other)")
                    cs["source_type"] = "gauge" if "time_base" in cs else "model"
    errs = [f"{list(e.path)} {e.message}" for e in validator(schema).iter_errors(checked)]
    if not errs:   # the cross-references assume the types the schema gives
        errs = cross_ref_errors(checked) + time_range_errors(checked)
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
    # an entry of the fixtures directory that the builder does not write (a root added by hand, a stray file) fails too
    for p in sorted(committed.iterdir()):
        if p.name not in GENERATED and p.name != "README.md":
            errs.append(f"not generated (an unlisted entry of {committed.name}/): {p.name}")
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
    calls_ok = PREDICT_CALLS.exists() and PREDICT_CALLS.read_bytes() == dumps_pretty(predict_calls())
    print(f"{'PASS' if calls_ok else 'FAIL'}  {PREDICT_CALLS.name} is current")
    if not calls_ok:
        problems.append(f"{PREDICT_CALLS.name}: missing or differs from a fresh generation")
    if PREDICT_CALLS.exists():
        bands = band_problems(json.loads(PREDICT_CALLS.read_bytes()))
        print(f"{'PASS' if not bands else 'FAIL'}  the prediction windows avoid the four bands of spec 6.3")
        for cid, why in BAND_EXCEPTIONS.items():
            print(f"KNOWN {cid}: not band-checked: {why}")
        problems += bands
    manifest = json.loads((FIXTURES / "fixtures.json").read_bytes())
    for fx in manifest["fixtures"]:
        root = FIXTURES / fx["root"]
        if not (root / "OTC_index.json").is_file():
            # a listed root that is missing (deleted, or never written): one FAIL line, not a traceback
            print(f"FAIL  {fx['root']:30} is listed in fixtures.json but {root.relative_to(FIXTURES.parent)}/OTC_index.json is missing")
            problems.append(f"{fx['root']}: missing (listed in fixtures.json)")
            continue
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
            if not fx["root"].startswith(("bad/", "predict-bad/")) and got["unknown_fields"]:
                # A root outside bad/ and predict-bad/ must be plain format 1.0: nothing read tolerantly.
                errs.append(f"{d}: a root outside bad/ read tolerantly: {', '.join(got['unknown_fields'])}")
            if fx["root"].startswith("predict-bad/") and not got["unknown_fields"]:
                # each bad prediction fixture has a defect that only prediction finds: the reader must have tolerated it
                errs.append(f"{d}: a bad prediction fixture read with no tolerance: its defect is not there")
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
    PREDICT_CALLS.write_bytes(dumps_pretty(predict_calls()))
    print(f"wrote fixtures under {FIXTURES} and {PREDICT_CALLS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
