# /// script
# requires-python = ">=3.10"
# ///
"""Build and check the language-neutral conformance cases (SDK spec §7.1).

Run: uv run conformance/tools/build_cases.py           (writes conformance/cases/*.json)
     uv run conformance/tools/build_cases.py --check   (writes nothing; exit 0 only if the
                                                        committed cases equal a fresh build)

The expected values come from the fixture releases in conformance/fixtures/ and
from a small oracle in this file that applies the rules of the SDK spec:
§4.3.1 (release.files), §4.4 (filters, ordering), §4.4.1 (fold table and
ranking), §4.5 to §4.7 (sets, constituents, offsets), §4.6 (attribution text),
§6.3 (haversine, R = 6371.0088 km). The result encodings are defined in
conformance/README.md ("Result encodings"). Network, cache, update and
download cases are written out by hand below; their expectations are
behaviours of spec §4.3, §5 and §4.3.2.

Do not edit conformance/cases/*.json by hand.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"
CASES = ROOT / "cases"
CROSS = ROOT / "cross"
FOLD = ROOT / "name_fold.json"
SUITE_VERSION = "0.1"
EARTH_R_KM = 6371.0088
TOL = 1e-6

FIX = "${fixtures}"
SRV = "${server}"
SRV_ALIAS = "${server_alias}"  # the fixture server under a name only the recording proxy resolves
D10 = "20991231.10"            # fixtures/order: newer than 20991231.2 by counter, older by string order

# --------------------------------------------------------------------------- fixtures


def load_release(root, datestamp):
    return json.loads((FIXTURES / root / f"OTC_{datestamp}.json").read_text(encoding="utf-8"))


def sha256_rows(root, datestamp):
    rows = {}
    for line in (FIXTURES / root / f"OTC_{datestamp}.sha256").read_text().splitlines():
        if line.strip():
            digest, name = line.split(None, 1)
            rows[name.strip().lstrip("*")] = digest
    return rows


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Rel:
    """One fixture release, indexed the way an SDK indexes it (spec §6.1)."""

    def __init__(self, root, datestamp):
        self.root = root
        self.datestamp = datestamp
        self.doc = load_release(root, datestamp)
        self.active = sorted([s for s in self.doc["stations"] if s.get("status") == "active"], key=lambda s: s["station_id"])
        self.tombs = sorted([s for s in self.doc["stations"] if s.get("status") == "removed"], key=lambda s: s["station_id"])
        self.by_id = {s["station_id"]: s for s in self.active}
        self.tomb_by_id = {s["station_id"]: s for s in self.tombs}
        self.conventions = {c["convention_id"]: c for c in self.doc["conventions"]}
        self.licences = {l["licence_id"]: l for l in self.doc["licences"]}

    # helpers
    def rec_set(self, s):
        rid = s.get("recommended_set_id")
        for cs in s.get("constant_sets", []):
            if cs["set_id"] == rid:
                return cs
        return None

    def kind(self, s, seen=()):
        rs = self.rec_set(s)
        if rs is not None:
            return {"water_level": "tide", "current": "current"}.get(rs["quantity"], "other")
        if s["type"] == "subordinate" and s.get("subordinate_offsets"):
            ref = self.by_id.get(s["subordinate_offsets"]["reference_station_id"])
            if ref is not None and ref["station_id"] not in seen:
                return self.kind(ref, seen + (s["station_id"],))
        return None


def aliases_enc(s):
    out = {}
    for system, ids in (s.get("aliases") or {}).items():
        out[system] = list(ids) if isinstance(ids, list) else [ids]
    return out


def g(d, k):
    v = d.get(k) if d is not None else None
    return v


# --------------------------------------------------------------------------- encodings (README "Result encodings")


def enc_station(rel, s):
    k = rel.kind(s)
    rs = rel.rec_set(s)
    return {
        "station_id": s["station_id"], "name": s["name"], "country": s["country"],
        "lat": s["lat"], "lon": s["lon"], "type": s["type"], "kind": k,
        "timezone": s.get("timezone"), "aliases": aliases_enc(s), "status": s["status"],
        "is_reference": s["type"] == "reference", "is_subordinate": s["type"] == "subordinate",
        "is_tide": k == "tide", "is_current": k == "current",
        "recommended_set_id": rs["set_id"] if rs else None,
    }


def enc_tombstone(t):
    return {"station_id": t["station_id"], "name": t.get("name"), "status": t["status"],
            "removed_in": t.get("removed_in"), "removed_reason": t.get("removed_reason")}


def enc_set(rel, s, cs):
    span = cs.get("record_span")
    datum = cs.get("datum")
    return {
        "set_id": cs["set_id"], "source": cs["source"], "source_type": cs["source_type"], "quantity": cs["quantity"],
        "source_record_id": cs.get("source_record_id"), "source_version": cs.get("source_version"),
        "record_span": None if span is None else {"start": span.get("start"), "end": span.get("end"), "good_samples": span.get("good_samples")},
        "datum": None if datum is None else {"msl_offset_m": datum.get("msl_offset_m"), "named": dict(datum.get("named") or {})},
        "qc_status": cs["qc_status"],
        "qc_flags": [{"flag": f["flag"], "verdict": f.get("verdict"), "values": f.get("values")} for f in cs.get("qc_flags") or []],
        "dropped_constituents": [{"name": d["name"], "dropped_reason": d["dropped_reason"], "detail": d.get("detail")} for d in cs.get("dropped_constituents") or []],
        "is_recommended": cs["set_id"] == s.get("recommended_set_id"),
        "convention_id": cs["convention_id"], "licence_id": cs["licence_id"],
        "constituent_count": len(cs.get("constituents") or []),
    }


CONSTITUENT_FIELDS = ["name", "source_name", "doodson", "speed_deg_per_hour", "amplitude_m", "phase_deg",
                      "amp_uncertainty_m", "phase_uncertainty_deg", "kept_reason"]
CONVENTION_FIELDS = ["convention_id", "phase_reference", "utc_offset_hours", "v0_model", "nodal_handling",
                     "nodal_formula_ids", "constituent_table_version", "tables_sha256", "canary"]
LICENCE_FIELDS = ["licence_id", "spdx", "provider", "citation", "attribution", "url"]
PROVENANCE_FIELDS = ["build_commit", "adapter_version", "input_sha256", "time_base", "selection_reason", "decision"]
VALIDATION_FIELDS = ["set_id", "reference_source", "reference_station", "reference_distance_km", "window",
                     "time_mae_min", "time_p95_min", "time_bias_min", "height_mae_m", "range_error_m",
                     "missed_events", "extra_events", "previous_release"]
PREVIOUS_FIELDS = ["time_mae_min", "time_p95_min", "time_bias_min", "height_mae_m", "range_error_m",
                   "missed_events", "extra_events"]
OFFSET_FIELDS = ["reference_station_id", "time_offset_high_min", "time_offset_low_min", "height_offset_high",
                 "height_offset_low", "height_adjusted_type", "licence_id"]


def pick(d, fields):
    return {f: (d.get(f) if d is not None else None) for f in fields}


def enc_validation(v):
    out = pick(v, VALIDATION_FIELDS)
    prev = v.get("previous_release")
    out["previous_release"] = None if prev is None else pick(prev, PREVIOUS_FIELDS)
    return out


def enc_release_meta(rel):
    r = rel.doc["release"]
    return {"datestamp": r["datestamp"], "created": r["created"], "format_version": rel.doc["format_version"],
            "doi": r.get("doi"), "concept_doi": r.get("concept_doi"), "source_versions": r.get("source_versions") or {},
            "build_commit": r.get("build_commit"), "changelog_url": r.get("changelog_url")}


def pointer_entry(root, datestamp):
    idx = json.loads((FIXTURES / root / "OTC_index.json").read_text())
    for e in idx["releases"]:
        if e["datestamp"] == datestamp:
            return e
    raise KeyError(datestamp)


def enc_release_info(root, datestamp, base):
    e = pointer_entry(root, datestamp)
    return {"datestamp": e["datestamp"], "format_version": e["format_version"], "doi": e.get("doi"),
            "files": sorted([{"name": f["name"], "url": base + f["url"], "size": f["size"], "sha256": f["sha256"]}
                             for f in e["files"]], key=lambda f: f["name"])}


# --------------------------------------------------------------------------- oracle: queries

def load_fold():
    doc = json.loads(FOLD.read_text(encoding="utf-8"))
    return {int(k, 16): v for k, v in doc["map"].items()}


FOLD_MAP = load_fold()


def fold(name):
    folded = "".join(FOLD_MAP.get(ord(ch), ch) for ch in name)
    return re.sub(r"[ \t\n\r\f\v]+", " ", folded).strip(" ")


def usable_sources(s):
    return {cs["source"] for cs in s.get("constant_sets", []) if cs["qc_status"] != "excluded"}


def apply_filters(rel, stations, f):
    out = []
    for s in stations:
        if "country" in f and s["country"] != f["country"]:
            continue
        if "type" in f and s["type"] != f["type"]:
            continue
        if "kind" in f and rel.kind(s) != f["kind"]:
            continue
        if "source" in f and f["source"] not in usable_sources(s):
            continue
        if "source_type" in f:
            rs = rel.rec_set(s)
            if rs is None or rs["source_type"] != f["source_type"]:
                continue
        out.append(s)
    return out


def occurrences(text, sub):
    """Every start index of sub in text, overlapping ones included."""
    out, i = [], text.find(sub)
    while i != -1:
        out.append(i)
        i = text.find(sub, i + 1)
    return out


def search(rel, name, limit=None, match=None, **f):
    q = fold(name)
    ranked = []
    for s in apply_filters(rel, rel.active, f):
        n = fold(s["name"])
        if n == q:
            r = 0
        elif match == "exact":
            continue
        elif n.startswith(q):
            r = 1
        elif any(n[i - 1] == " " for i in occurrences(n, q) if i > 0):
            r = 2
        elif q in n:
            r = 3
        else:
            continue
        ranked.append((r, n, s["station_id"]))
    ranked.sort()
    ids = [x[2] for x in ranked]
    return ids[:limit] if limit is not None else ids


def haversine(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R_KM * math.asin(min(1.0, math.sqrt(a)))


def near(rel, lat, lon, radius_km, limit=None, **f):
    hits = sorted((haversine(lat, lon, s["lat"], s["lon"]), s["station_id"]) for s in apply_filters(rel, rel.active, f))
    hits = [h for h in hits if h[0] <= radius_km]
    if limit is not None:
        hits = hits[:limit]
    return {"station_ids": [h[1] for h in hits], "distance_km": [h[0] for h in hits]}


def nearest(rel, lat, lon, max_km=None, **f):
    hits = sorted((haversine(lat, lon, s["lat"], s["lon"]), s["station_id"]) for s in apply_filters(rel, rel.active, f))
    if max_km is not None:
        hits = [h for h in hits if h[0] <= max_km]
    if not hits:
        return {"station_id": None, "distance_km": None}
    return {"station_id": hits[0][1], "distance_km": hits[0][0]}


def attribution(rel, station_ids=None):
    r = rel.doc["release"]
    if station_ids is None:
        lic_ids = set(rel.licences)
    else:
        lic_ids = set()
        for sid in station_ids:
            s = rel.by_id[sid]
            rs = rel.rec_set(s)
            if rs:
                lic_ids.add(rs["licence_id"])
            off = s.get("subordinate_offsets")
            if s["type"] == "subordinate" and off:
                if off.get("licence_id"):
                    lic_ids.add(off["licence_id"])
                ref = rel.by_id.get(off["reference_station_id"])
                if ref and rel.rec_set(ref):
                    lic_ids.add(rel.rec_set(ref)["licence_id"])
    parts, seen = [], set()
    for lid in sorted(lic_ids):
        lic = rel.licences[lid]
        if lic["provider"] in seen:
            continue
        seen.add(lic["provider"])
        parts.append(f"{lic['provider']}: {lic['attribution']}")
    ident = f"doi:{r['doi']}" if r.get("doi") else f"https://data.opentideconstants.org/OTC_{r['datestamp']}.json"
    return f"Tidal constants: OpenTideConstants {r['datestamp']}, {ident}, CC BY 4.0. Sources: " + "; ".join(parts)


def citation(rel):
    """The dataset citation (§4.6): the year is the first four digits of the datestamp."""
    r = rel.doc["release"]
    d = r["datestamp"]
    link = f"https://doi.org/{r['doi']}" if r.get("doi") else f"https://data.opentideconstants.org/OTC_{d}.json"
    return f"OpenTideConstants contributors ({d[:4]}). OpenTideConstants, release {d} [Data set]. {link}"


def stats(rel):
    def count(values):
        out = {}
        for v in values:
            if v is not None:
                out[v] = out.get(v, 0) + 1
        return dict(sorted(out.items()))
    sets = [cs for s in rel.active for cs in s.get("constant_sets", [])]
    return {"type": count(s["type"] for s in rel.active), "kind": count(rel.kind(s) for s in rel.active),
            "country": count(s["country"] for s in rel.active), "source": count(cs["source"] for cs in sets),
            "qc_status": count(cs["qc_status"] for cs in sets)}


def sets_in_order(s, include_excluded=False):
    rid = s.get("recommended_set_id")
    sets = [cs for cs in s.get("constant_sets", []) if include_excluded or cs["qc_status"] != "excluded"]
    rec = [cs for cs in sets if cs["set_id"] == rid]
    rest = sorted([cs for cs in sets if cs["set_id"] != rid], key=lambda c: c["set_id"])
    return rec + rest


# --------------------------------------------------------------------------- case helpers

def step(op, expect=None, on=None, **args):
    st = {"op": op}
    if args:
        st["args"] = args
    if on:
        st["on"] = on
    if expect is not None:
        st["expect"] = expect
    return st


def drv(action, **kw):
    return {"driver": action, **kw}


def err(code, **fields):
    e = {"error": code}
    if fields:
        e["error_fields"] = fields
    return e


NOT_BUILT = {"fetch": {"error": "not_built"}}
NOT_BUILT_OR_UNSUPPORTED = {"fetch": {"error": "not_built"}, "fs": {"error": "unsupported"}}


def net(st, fs=False):
    """Mark a runner step that needs the network module; without it the step must fail with not_built."""
    st["expect_if_missing"] = dict(NOT_BUILT_OR_UNSUPPORTED if fs else NOT_BUILT)
    return st


def case(cid, title, spec, steps, **extra):
    c = {"id": cid, "title": title, "spec": spec}
    c.update(extra)
    c["steps"] = steps
    return c


def mcase(cid, title, spec, steps, root="good", release="20991231.2", **extra):
    """A query case run once per open variant (json, json.gz, jsonl eager, jsonl stream)."""
    return case(cid, title, spec, steps, matrix={"root": root, "release": release}, **extra)


# --------------------------------------------------------------------------- groups

def group_release(R2, R1):
    out = []
    for rel in (R2, R1):
        d = rel.datestamp
        out.append(mcase(f"release/metadata-{d}", f"release metadata of {d}", "4.3",
                         [step("release_metadata", enc_release_meta(rel))], release=d))
        out.append(mcase(f"release/counts-{d}", f"station_count and tombstone_count of {d}", "4.3",
                         [step("station_count", {"station_count": len(rel.active)}),
                          step("tombstone_count", {"tombstone_count": len(rel.tombs)})], release=d))
        out.append(mcase(f"release/stats-{d}", f"stats of {d}", "4.3", [step("stats", {"stats": stats(rel)})], release=d))
        out.append(mcase(f"release/attribution-all-{d}", f"attribution with no stations, {d} (DOI {'set' if rel.doc['release'].get('doi') else 'null'})", "4.6",
                         [step("attribution", {"attribution": attribution(rel)})], release=d))
    rel = R2
    names = sorted({c["name"] for s in rel.active for cs in s.get("constant_sets", []) for c in cs.get("constituents", [])})
    out.append(mcase("release/constituent-names", "constituent_names: the sorted union over all sets", "4.5",
                     [step("constituent_names", {"names": names})]))
    out.append(mcase("release/conventions", "conventions in file order, with missing optional fields as null", "4.5",
                     [step("conventions", {"conventions": [pick(c, CONVENTION_FIELDS) for c in rel.doc["conventions"]]})]))
    out.append(mcase("release/convention-lookup", "convention(id), and null for an unknown id", "4.5",
                     [step("convention", {"convention": pick(rel.conventions["kartverket-utc1-v1"], CONVENTION_FIELDS)}, convention_id="kartverket-utc1-v1"),
                      step("convention", {"convention": None}, convention_id="no-such-convention")]))
    out.append(mcase("release/licences", "licences in file order, with missing optional fields as null", "4.6",
                     [step("licences", {"licences": [pick(l, LICENCE_FIELDS) for l in rel.doc["licences"]]})]))
    out.append(mcase("release/licence-lookup", "licence(id), and null for an unknown id", "4.6",
                     [step("licence", {"licence": pick(rel.licences["gesla-derived"], LICENCE_FIELDS)}, licence_id="gesla-derived"),
                      step("licence", {"licence": None}, licence_id="no-such-licence")]))
    out.append(mcase("release/citation", "citation contains the version DOI and the datestamp", "4.6",
                     [step("citation", {"citation": {"$all": [{"$contains": "10.5072/zenodo.2"}, {"$contains": "20991231.2"}]}})]))
    for cr in (R2, R1):
        out.append(mcase(f"release/citation-exact-{cr.datestamp}", f"citation of {cr.datestamp}, exact text (DOI {'set' if cr.doc['release'].get('doi') else 'null'})", "4.6",
                         [step("citation", {"citation": citation(cr)})], release=cr.datestamp))
    for label, ids in [("one-station", ["OTC-T-0006"]),
                       ("ordered-by-licence-id", ["OTC-T-0006", "OTC-T-0010", "OTC-T-0007"]),
                       ("offsets-only-subordinate", ["OTC-T-0003"]),
                       ("subordinate-with-own-set", ["OTC-T-0004"]),
                       ("licence-once", ["OTC-T-0010", "OTC-T-0011", "OTC-T-0002", "OTC-T-0001"])]:
        out.append(mcase(f"release/attribution-{label}", f"attribution for stations {', '.join(ids)}", "4.6",
                         [step("attribution", {"attribution": attribution(rel, ids)}, station_ids=ids)]))
    return out


def group_stations(R2, R1):
    out = []
    rel = R2
    for s in rel.active:
        sid = s["station_id"]
        steps = [step("station", {"station": enc_station(rel, s)}, station_id=sid),
                 step("require_station", {"station": enc_station(rel, s)}, station_id=sid),
                 step("recommended_set", {"set_id": rel.rec_set(s)["set_id"] if rel.rec_set(s) else None}, station_id=sid),
                 step("constant_sets", {"set_ids": [c["set_id"] for c in sets_in_order(s)]}, station_id=sid),
                 step("constant_sets", {"set_ids": [c["set_id"] for c in sets_in_order(s, True)]}, station_id=sid, include_excluded=True),
                 step("subordinate_offsets", {"offsets": pick(s["subordinate_offsets"], OFFSET_FIELDS) if s.get("subordinate_offsets") else None}, station_id=sid),
                 step("station_validation", {"validation": [enc_validation(v) for v in s.get("validation") or []]}, station_id=sid)]
        ref = None
        if s["type"] == "subordinate" and s.get("subordinate_offsets"):
            ref = s["subordinate_offsets"]["reference_station_id"]
        steps.append(step("reference_station", {"station_id": ref}, station_id=sid))
        subs = sorted(x["station_id"] for x in rel.active if x["type"] == "subordinate" and (x.get("subordinate_offsets") or {}).get("reference_station_id") == sid)
        steps.append(step("subordinates_of", {"station_ids": subs}, station_id=sid))
        out.append(mcase(f"stations/{sid}", f"station {sid} ({s['name']}): fields, sets, offsets, validation, links", "3, 4.4, 4.5, 4.7", steps))
    out.append(mcase("stations/unknown-and-removed", "station() is null for an unknown id and for a removed id; tombstone() returns the tombstone", "4.4",
                     [step("station", {"station": None}, station_id="OTC-T-9999"),
                      step("station", {"station": None}, station_id="OTC-T-0005"),
                      step("tombstone", {"tombstone": enc_tombstone(rel.tomb_by_id["OTC-T-0005"])}, station_id="OTC-T-0005"),
                      step("tombstone", {"tombstone": enc_tombstone(rel.tomb_by_id["OTC-T-0021"])}, station_id="OTC-T-0021"),
                      step("tombstone", {"tombstone": None}, station_id="OTC-T-0001"),
                      step("tombstone", {"tombstone": None}, station_id="OTC-T-9999")]))
    out.append(mcase("stations/require-errors", "require_station: station_not_found and station_removed", "4.4, 4.8",
                     [step("require_station", err("station_not_found"), station_id="OTC-T-9999"),
                      step("require_station", err("station_removed"), station_id="OTC-T-0005")]))
    out.append(mcase("stations/active-then-removed", "OTC-T-0021 is active in 20991231 and a tombstone in 20991231.2", "4.4",
                     [step("station", {"station": enc_station(R1, R1.by_id["OTC-T-0021"])}, station_id="OTC-T-0021"),
                      step("tombstone", {"tombstone": None}, station_id="OTC-T-0021")], release="20991231"))
    # aliases
    alias_steps = []
    for s in rel.active:
        for system, ids in aliases_enc(s).items():
            for aid in ids:
                alias_steps.append(step("station_by_alias", {"station_id": s["station_id"]}, system=system, alias_id=aid))
    alias_steps += [step("station_by_alias", {"station_id": None}, system="noaa", alias_id="0000000"),
                    step("station_by_alias", {"station_id": None}, system="no-such-system", alias_id="9900001"),
                    step("station_by_alias", {"station_id": None}, system="ticon", alias_id="9900001")]
    out.append(mcase("stations/aliases", "station_by_alias in every system, each id of a list alias, and misses", "4.4", alias_steps))
    # listing and filters
    filter_sets = [{}, {"country": "GBR"}, {"country": "NOR"}, {"type": "subordinate"}, {"type": "reference", "country": "USA"},
                   {"kind": "current"}, {"kind": "tide", "country": "USA"}, {"source": "gesla-fit"}, {"source": "noaa"},
                   {"source_type": "model"}, {"source_type": "official"}, {"country": "ZZZ"}, {"kind": "no-such-kind"},
                   {"source": "ticon-fallback"}, {"source_type": "gauge", "country": "USA"}]
    for f in filter_sets:
        ids = [s["station_id"] for s in apply_filters(rel, rel.active, f)]
        label = "-".join(f"{k}-{v}" for k, v in f.items()) or "all"
        out.append(mcase(f"stations/list-{label}", f"stations and iter_stations with filters {json.dumps(f)}", "4.4",
                         [step("stations", {"station_ids": ids}, **f), step("iter_stations", {"station_ids": ids}, **f)]))
    out.append(mcase("stations/filter-wrong-type", "a filter argument of the wrong type is invalid_argument", "4.4, 4.8",
                     [step("stations", err("invalid_argument"), country=5),
                      step("stations", err("invalid_argument"), type=["reference"])]))
    return out


def group_sets(R2):
    out = []
    rel = R2
    for s in rel.active:
        for cs in s.get("constant_sets", []):
            sid, setid = s["station_id"], cs["set_id"]
            steps = [step("constant_set", {"set": enc_set(rel, s, cs)}, station_id=sid, set_id=setid),
                     step("constituents", {"constituents": [pick(c, CONSTITUENT_FIELDS) for c in cs.get("constituents", [])]}, station_id=sid, set_id=setid),
                     step("provenance", {"provenance": pick(cs.get("provenance") or {}, PROVENANCE_FIELDS), "raw": cs.get("provenance") or {}}, station_id=sid, set_id=setid),
                     step("set_validation", {"validation": [enc_validation(v) for v in sorted(
                         [v for v in s.get("validation") or [] if v["set_id"] == setid], key=lambda v: v["window"])]}, station_id=sid, set_id=setid)]
            if sid == "OTC-T-0001" or cs["qc_status"] != "accepted" or sid in ("OTC-T-0006", "OTC-T-0019", "OTC-T-0020"):
                first = cs["constituents"][0]
                steps += [step("constituent", {"constituent": pick(first, CONSTITUENT_FIELDS)}, station_id=sid, set_id=setid, name=first["name"]),
                          step("constituent", {"constituent": None}, station_id=sid, set_id=setid, name=first["name"].lower()),
                          step("constituent", {"constituent": None}, station_id=sid, set_id=setid, name="M4")]
            out.append(mcase(f"sets/{setid}", f"constant set {setid}: fields, constituents, provenance, validation", "4.5, 4.6", steps))
    out.append(mcase("sets/unknown", "constant_set() is null for an unknown set id", "4.5",
                     [step("constant_set", {"set": None}, station_id="OTC-T-0001", set_id="OTC-T-0001/no-such-set")]))
    return out


def group_search(R2):
    rel = R2
    out = []
    queries = [
        ("tromso", {}), ("TROMSØ", {}), ("Tromsø", {}), ("alesund", {}), ("ÅLESUND", {}), ("leba", {}), ("Łeba", {}),
        ("strasse", {}), ("STRASSE", {}), ("harbour", {}), ("Harbour", {"limit": 3}), ("harbour", {"match": "exact"}),
        ("harbour", {"country": "GBR"}), ("harbour", {"country": "IRL"}), ("san fran", {}), ("  San   FRANCISCO  ", {}),
        ("san francisco", {"match": "exact"}), ("francisco", {}), ("pier", {}), ("station", {}), ("an", {}),
        ("no such place", {}), ("e", {"limit": 4, "country": "USA"}),
    ]
    for i, (q, kw) in enumerate(queries, 1):
        ids = search(rel, q, **kw)
        label = re.sub(r"[^a-z0-9]+", "-", fold(q)).strip("-") or "blank"
        extra = "-".join(f"{k}-{v}" for k, v in kw.items())
        cid = f"search/{i:02d}-{label}" + (f"-{extra}" if extra else "")
        out.append(mcase(cid, f"search name={q!r} {json.dumps(kw) if kw else ''}".strip(), "4.4.1",
                         [step("search", {"station_ids": ids}, name=q, **kw)]))
    out.append(mcase("search/empty-query", "an empty query (also after trimming) is invalid_argument", "4.4.1",
                     [step("search", err("invalid_argument"), name=""), step("search", err("invalid_argument"), name="   ")]))
    return out


def group_geo(R2):
    rel = R2
    out = []
    spec_example = near(rel, 0.0, 179.95, 50)
    assert spec_example["station_ids"] == ["OTC-T-0007", "OTC-T-0008"]
    assert abs(spec_example["distance_km"][0] - 5.559754011674749) < 1e-9 and abs(spec_example["distance_km"][1] - 16.679262035030458) < 1e-9
    nears = [
        ("antimeridian", dict(lat=0.0, lon=179.95, radius_km=50)),
        ("antimeridian-west", dict(lat=0.0, lon=-179.95, radius_km=50)),
        ("antimeridian-limit", dict(lat=0.0, lon=179.97, radius_km=50, limit=1)),
        ("pole", dict(lat=90.0, lon=0.0, radius_km=20)),
        ("across-pole", dict(lat=89.95, lon=180.0, radius_km=20)),
        ("equator", dict(lat=0.0, lon=9.0, radius_km=1)),
        ("sf-bay", dict(lat=37.8, lon=-122.4, radius_km=30)),
        ("sf-bay-type", dict(lat=37.8, lon=-122.4, radius_km=30, type="subordinate")),
        ("sf-bay-source-type", dict(lat=37.8, lon=-122.4, radius_km=30, source_type="official")),
        ("solent", dict(lat=50.75, lon=-1.2, radius_km=100)),
        ("nothing", dict(lat=-45.0, lon=-30.0, radius_km=100)),
    ]
    for label, kw in nears:
        out.append(mcase(f"geo/near-{label}", f"near {json.dumps(kw)}", "4.4, 6.3",
                         [step("near", {**near(rel, **kw), "tolerance": TOL}, **kw)]))
    nearests = [
        ("plain", dict(lat=37.79, lon=-122.33)),
        ("antimeridian", dict(lat=0.0, lon=179.99)),
        ("antimeridian-west", dict(lat=0.0, lon=-179.99)),
        ("max-km-miss", dict(lat=-45.0, lon=-30.0, max_km=100)),
        ("max-km-hit", dict(lat=37.79, lon=-122.33, max_km=5)),
        ("type", dict(lat=37.79, lon=-122.33, type="reference")),
        ("kind", dict(lat=37.79, lon=-122.33, kind="current")),
    ]
    for label, kw in nearests:
        out.append(mcase(f"geo/nearest-{label}", f"nearest {json.dumps(kw)}", "4.4, 6.3",
                         [step("nearest", {**nearest(rel, **kw), "tolerance": TOL}, **kw)]))
    out.append(mcase("geo/invalid-arguments", "lat or lon out of range and a negative radius are invalid_argument", "4.4, 4.8",
                     [step("near", err("invalid_argument"), lat=91.0, lon=0.0, radius_km=10),
                      step("near", err("invalid_argument"), lat=0.0, lon=-180.5, radius_km=10),
                      step("near", err("invalid_argument"), lat=0.0, lon=0.0, radius_km=-1),
                      step("nearest", err("invalid_argument"), lat=-90.5, lon=0.0),
                      step("nearest", err("invalid_argument"), lat=0.0, lon=181.0)]))
    return out


def group_tolerant():
    rel = Rel("bad/format-minor", "20991231")
    s = rel.by_id["OTC-T-0001"]
    cs = s["constant_sets"][0]
    con = rel.conventions[rel.doc["conventions"][0]["convention_id"]]
    lic = rel.doc["licences"][0]
    steps = [step("release_metadata", {"format_version": "0.3", "datestamp": "20991231"}),
             step("station", {"station": enc_station(rel, s)}, station_id="OTC-T-0001"),
             step("raw", {"raw": s}, object="station", station_id="OTC-T-0001"),
             step("raw", {"raw": cs}, object="set", station_id="OTC-T-0001", set_id=cs["set_id"]),
             step("raw", {"raw": cs["constituents"][0]}, object="constituent", station_id="OTC-T-0001", set_id=cs["set_id"], name=cs["constituents"][0]["name"]),
             step("raw", {"raw": con}, object="convention", convention_id=con["convention_id"]),
             step("raw", {"raw": lic}, object="licence", licence_id=lic["licence_id"]),
             step("station_by_alias", {"station_id": "OTC-T-0001"}, system="future_system", alias_id="FS-0001"),
             step("constant_set", {"set": enc_set(rel, s, cs)}, station_id="OTC-T-0001", set_id=cs["set_id"])]
    out = [mcase("tolerant/format-minor", "a higher format minor loads; unknown fields stay in raw; an unknown alias system works", "7.3",
                 steps, root="bad/format-minor", release="20991231", open_expect={"format_version": "0.3"})]
    good = Rel("good", "20991231.2")
    gs = good.by_id["OTC-T-0020"]
    out.append(mcase("tolerant/raw-good", "raw is the object as the file gives it", "3",
                     [step("raw", {"raw": gs}, object="station", station_id="OTC-T-0020"),
                      step("raw", {"raw": good.tomb_by_id["OTC-T-0005"]}, object="tombstone", station_id="OTC-T-0005")]))
    return out


def file_rows(root, d, present):
    rows = sha256_rows(root, d)
    return [{"name": n, "url": None, "size": (FIXTURES / root / n).stat().st_size if n in present else None, "sha256": rows[n]}
            for n in sorted(rows)]


def group_load():
    out = []
    G = f"{FIX}/good"
    d = "20991231.2"
    exts = [(".json", ["json"]), (".json.gz", ["json"]), (".jsonl", [])]
    # release.files rows (spec §4.3.1)
    out.append(case("load/files-file-sha256-complete", "loaded_from file: release.files lists every name in .sha256 with stat sizes", "4.3.1",
                    [step("open", {"loaded_from": "file", "datestamp": d}, file=f"{G}/OTC_{d}.jsonl"),
                     step("release_files", {"files": file_rows("good", d, set(sha256_rows("good", d)))})], requires=["fs"]))
    out.append(case("load/files-file-sha256-partial", "loaded_from file: a file named in .sha256 but absent has size null", "4.3.1",
                    [drv("copy", files=[f"{G}/OTC_{d}.jsonl", f"{G}/OTC_{d}.meta.json", f"{G}/OTC_{d}.sha256"], to="${tmp}/rel"),
                     step("open", {"loaded_from": "file", "datestamp": d}, file=f"${{tmp}}/rel/OTC_{d}.jsonl"),
                     step("release_files", {"files": file_rows("good", d, {f"OTC_{d}.jsonl", f"OTC_{d}.meta.json"})})], requires=["fs"]))
    for ext, req in [(".json", ["json"]), (".jsonl", [])]:
        names = [f"OTC_{d}{ext}"] + ([f"OTC_{d}.meta.json"] if ext == ".jsonl" else [])
        rows = [{"name": n, "url": None, "size": (FIXTURES / "good" / n).stat().st_size, "sha256": None} for n in sorted(names)]
        out.append(case(f"load/file-unverified{ext.replace('.', '-')}", f"no .sha256 next to the {ext} file: loaded_from file_unverified; files are the files opened", "4.2, 4.3.1",
                        [drv("copy", files=[f"{G}/{n}" for n in names], to="${tmp}/rel"),
                         step("open", {"loaded_from": "file_unverified", "datestamp": d}, file=f"${{tmp}}/rel/OTC_{d}{ext}"),
                         step("release_files", {"files": rows})], requires=["fs"] + req))
    out.append(case("load/file-missing", "opening a missing file is an io error with the path", "4.8",
                    [step("open", err("io", path={"$contains": "OTC_20991231.9.json"}), file="${tmp}/OTC_20991231.9.json")], requires=["fs"]))
    out.append(case("load/file-not-json", "a .json file that is not JSON is invalid_release", "4.8",
                    [drv("write", path=f"${{tmp}}/OTC_{d}.json", text="this is not json\n"),
                     step("open", err("invalid_release"), file=f"${{tmp}}/OTC_{d}.json")], requires=["fs", "json"]))
    out.append(case("load/jsonl-bad-line", "a .jsonl line that is not JSON is invalid_release", "4.8",
                    [drv("copy", files=[f"{G}/OTC_{d}.meta.json"], to="${tmp}"),
                     drv("write", path=f"${{tmp}}/OTC_{d}.jsonl", text="{\"station_id\": \"OTC-T-0001\"\n"),
                     step("open", err("invalid_release"), file=f"${{tmp}}/OTC_{d}.jsonl")], requires=["fs"]))
    for root, code in [("wrong-sha256", "checksum_mismatch"), ("truncated", "checksum_mismatch"),
                       ("format-major", "unsupported_format"), ("unresolved-convention", "invalid_release")]:
        for ext, req in exts:
            out.append(case(f"load/bad-{root}{ext.replace('.', '-')}", f"bad/{root} opened as {ext}: {code}", "4.8, 5.3, 7.4",
                            [step("open", err(code), file=f"{FIX}/bad/{root}/OTC_20991231{ext}")], requires=["fs"] + req))
    out.append(case("load/format-minor-loads", "bad/format-minor (format 0.3) loads from a file", "7.3",
                    [step("open", {"loaded_from": "file", "datestamp": "20991231", "format_version": "0.3"}, file=f"{FIX}/bad/format-minor/OTC_20991231.jsonl"),
                     step("station_count", {"station_count": len(Rel("bad/format-minor", "20991231").active)})], requires=["fs"]))
    out.append(case("load/verify-file", "verify passes on an intact file and fails with checksum_mismatch after one byte changes", "4.3, 5.3",
                    [drv("copy", files=[f"{G}/OTC_{d}.jsonl", f"{G}/OTC_{d}.meta.json", f"{G}/OTC_{d}.sha256"], to="${tmp}/rel"),
                     step("open", {"loaded_from": "file"}, file=f"${{tmp}}/rel/OTC_{d}.jsonl"),
                     step("verify", {"verified": True}),
                     drv("corrupt", path=f"${{tmp}}/rel/OTC_{d}.jsonl", offset=100),
                     step("verify", err("checksum_mismatch", file={"$contains": f"OTC_{d}.jsonl"}, expected=sha256_rows("good", d)[f"OTC_{d}.jsonl"], actual={"$regex": "^[0-9a-f]{64}$"}))],
                    requires=["fs"]))
    for bad in ["2099123", "20991231.1", "20991231.0", "20991231.01", "20991231.", "209912310", "latest2", "2099-12-31"]:
        out.append(case(f"load/invalid-datestamp-{bad}", f"release={bad!r} does not match the datestamp pattern: invalid_argument", "4.2",
                        [net(step("open", err("invalid_argument"), release=bad, base_url=f"{SRV}/good/", cache_dir="${cache}"))],
                        requires=["fs"]))
    out.append(case("load/valid-datestamp-not-found", "release 20991231.10 matches the pattern but does not exist: release_not_found", "4.2, 4.8",
                    [net(step("open", err("release_not_found"), release="20991231.10", base_url=f"{SRV}/good/", cache_dir="${cache}"))], requires=["fs"]))
    return out


def group_network():
    out = []
    G = f"{SRV}/good/"
    d2, d1 = "20991231.2", "20991231"
    info2 = enc_release_info("good", d2, G)
    info1 = enc_release_info("good", d1, G)
    UA = r"^opentideconstants-[a-z0-9]+/[^ ]+ \(\+https://opentideconstants\.org\)$"

    def open_latest(expect=None, **kw):
        args = {"base_url": G, "cache_dir": "${cache}"}
        args.update(kw)
        return net(step("open", expect if expect is not None else {"loaded_from": "download", "datestamp": d2, "format_version": "0.2"}, **args))

    out.append(case("net/latest-download", "open latest: pointer, .sha256, data file; loaded_from download; files from the pointer", "4.2, 4.3.1, 5.2",
                    [open_latest(),
                     drv("assert_requests", match=r"/good/OTC_latest-f0\.json$", min=1),
                     drv("assert_requests", match=r"/good/OTC_20991231\.2\.sha256$", count=1),
                     drv("assert_requests", has_query=True, count=0),
                     drv("assert_requests", header={"user-agent": UA}, min=1, all=True),
                     step("release_files", {"files": info2["files"]}),
                     step("station_count", {"station_count": 20}),
                     drv("assert_files", dir="${cache}/v1/releases/20991231.2", present=[".verified", "OTC_20991231.2.sha256"], absent=[".lock"], no_tmp=True),
                     drv("assert_files", dir="${cache}/v1/pointer", present=["OTC_latest-f0.json", "OTC_latest-f0.json.etag"], no_tmp=True)],
                    requires=["fs"]))
    out.append(case("net/latest-stream", "stream mode downloads .jsonl and .meta.json with Accept-Encoding gzip and builds index-v1.json", "5.2, 5.7, 6.2",
                    [open_latest(mode="stream"),
                     drv("assert_requests", match=r"/good/OTC_20991231\.2\.jsonl$", min=1, header={"accept-encoding": "gzip"}),
                     drv("assert_requests", match=r"/good/OTC_latest-f0\.json$", min=1, header={"accept-encoding": "gzip"}),
                     drv("assert_files", dir="${cache}/v1/releases/20991231.2",
                         present=[".verified", "OTC_20991231.2.jsonl", "OTC_20991231.2.meta.json", "index-v1.json"], no_tmp=True),
                     drv("assert_sha256", path="${cache}/v1/releases/20991231.2/OTC_20991231.2.jsonl", equals=f"{FIX}/good/OTC_20991231.2.jsonl"),
                     step("station", {"station": {"$type": "object"}}, station_id="OTC-T-0006")],
                    requires=["fs"]))
    out.append(case("net/eager-stores-json", "eager mode stores the release decompressed as .json in the cache", "5.4",
                    [open_latest(mode="eager"),
                     drv("assert_sha256", path="${cache}/v1/releases/20991231.2/OTC_20991231.2.json", equals=f"{FIX}/good/OTC_20991231.2.json"),
                     drv("assert_json", path="${cache}/v1/releases/20991231.2/.verified",
                         match={"files": {"$type": "object"}, "verified_at": {"$type": "string"}, "by": {"$regex": "^opentideconstants-[a-z0-9]+/"}})],
                    requires=["fs"]))
    out.append(case("net/second-open-uses-cache", "a second client: conditional GET of the pointer (304), no data request, loaded_from cache", "5.2, 5.3, 4.3.1",
                    [open_latest(), drv("restart_runner"), drv("clear_log"),
                     net(step("open", {"loaded_from": "cache", "datestamp": d2}, base_url=G, cache_dir="${cache}")),
                     drv("assert_requests", match=r"/good/OTC_latest-f0\.json$", min=1, status=304, header={"if-none-match": '^"[0-9a-f]{64}"$'}),
                     drv("assert_requests", match=r"/good/OTC_20991231\.2\.", count=0),
                     step("release_files", {"files": info2["files"]})],
                    requires=["fs"]))
    out.append(case("net/pinned-cached-no-network", "a pinned, cached release opens with the server stopped and no socket", "4.2, 5.2, 6.5",
                    [net(step("open", {"loaded_from": "download", "datestamp": d2}, release=d2, base_url=G, cache_dir="${cache}")),
                     drv("restart_runner"), drv("server_stop"), drv("clear_log"),
                     net(step("open", {"loaded_from": "cache", "datestamp": d2}, release=d2, base_url=G, cache_dir="${cache}")),
                     drv("assert_requests", source="any", count=0)],
                    requires=["fs"]))
    # A pinned download reads only OTC_{D}.sha256 (spec 5.2), so release.files is checked against that file
    # alone: its names and digests; url and size are the true values or null (README "Choices").
    pinned_rows = [{"name": n, "url": {"$any_of": [None, G + n]},
                    "size": {"$any_of": [None, (FIXTURES / "good" / n).stat().st_size]}, "sha256": h}
                   for n, h in sorted(sha256_rows("good", d1).items())]
    out.append(case("net/pinned-download", "a pinned older release downloads; its metadata is that release's; files from its .sha256", "4.2, 4.3.1, 5.2",
                    [net(step("open", {"loaded_from": "download", "datestamp": d1}, release=d1, base_url=G, cache_dir="${cache}")),
                     drv("assert_requests", match=r"OTC_(latest|index)", count=0),
                     step("release_metadata", {"datestamp": d1, "doi": None, "build_commit": "0123456789abcdef0123456789abcdef01234567"}),
                     step("release_files", {"files": pinned_rows})],
                    requires=["fs"]))
    out.append(case("net/pinned-404", "a pinned datestamp that the server does not have: release_not_found, and the 404 is not retried", "4.8, 5.7",
                    [net(step("open", err("release_not_found"), release="20991230", base_url=G, cache_dir="${cache}")),
                     drv("assert_requests", match=r"OTC_20991230\.sha256$", count=1)],
                    requires=["fs"]))
    out.append(case("net/retry-500-then-200", "a 500 then a 200: the SDK retries and loads", "5.7",
                    [drv("server_rules", rules=[{"match": r"/good/OTC_20991231\.2\.sha256$", "action": "status", "status": 500, "times": 1}]),
                     net(step("open", {"loaded_from": "download", "datestamp": d2}, release=d2, base_url=G, cache_dir="${cache}")),
                     drv("assert_requests", match=r"/good/OTC_20991231\.2\.sha256$", count=2)],
                    requires=["fs"]))
    out.append(case("net/retry-429-retry-after", "a 429 with Retry-After: 2, then a 200: the SDK waits at least 2 s and loads", "5.7",
                    [drv("server_rules", rules=[{"match": r"/good/OTC_latest-f0\.json$", "action": "status", "status": 429, "headers": {"Retry-After": "2"}, "times": 1}]),
                     open_latest(),
                     drv("assert_requests", match=r"/good/OTC_latest-f0\.json$", count=2, min_gap_s=1.9)],
                    requires=["fs"]))
    out.append(case("net/500-raise", "the pointer always answers 500, on_network_error raise: network error with status 500 after 3 attempts", "4.8, 5.2, 5.7",
                    [drv("server_rules", rules=[{"match": r"/good/OTC_latest(-f0)?\.json$", "action": "status", "status": 500}]),
                     open_latest(err("network", status=500), on_network_error="raise"),
                     drv("assert_requests", match=r"/good/OTC_latest-f0\.json$", count=3)],
                    requires=["fs"], timeout_s=90))
    out.append(case("net/500-no-cache", "the pointer always answers 500 and the cache is empty: network error even with use_cache", "5.2",
                    [drv("server_rules", rules=[{"match": r"/good/OTC_latest(-f0)?\.json$", "action": "status", "status": 500}]),
                     open_latest(err("network"))],
                    requires=["fs"], timeout_s=90))
    out.append(case("net/500-use-cache", "a network error with a cached release: loaded_from cache_after_error and last_error", "4.3, 5.2",
                    [open_latest(), drv("restart_runner"),
                     drv("server_rules", rules=[{"match": r"/good/OTC_latest(-f0)?\.json$", "action": "status", "status": 500}]),
                     open_latest({"loaded_from": "cache_after_error", "datestamp": d2}),
                     step("last_error", {"code": "network"}),
                     step("release_files", {"files": info2["files"]})],
                    requires=["fs"], timeout_s=90))
    out.append(case("net/last-error-null", "last_error is null after a clean download", "4.3",
                    [open_latest(), step("last_error", {"code": None})], requires=["fs"]))
    out.append(case("net/offline-empty-cache", "offline with an empty cache: offline_unavailable and no socket", "4.8, 5.5",
                    [drv("server_stop"), open_latest(err("offline_unavailable"), offline=True), drv("assert_requests", source="any", count=0)],
                    requires=["fs"]))
    out.append(case("net/offline-cached", "offline with a cached release: loaded_from cache, no socket", "5.2, 5.5",
                    [open_latest(), drv("restart_runner"), drv("server_stop"), drv("clear_log"),
                     open_latest({"loaded_from": "cache", "datestamp": d2}, offline=True), drv("assert_requests", source="any", count=0)],
                    requires=["fs"]))
    out.append(case("net/offline-env", "OPENTIDECONSTANTS_OFFLINE=1 works like offline: true", "4.2, 5.5",
                    [open_latest(), drv("restart_runner", env={"OPENTIDECONSTANTS_OFFLINE": "1"}), drv("server_stop"), drv("clear_log"),
                     open_latest({"loaded_from": "cache", "datestamp": d2}), drv("assert_requests", source="any", count=0)],
                    requires=["fs"]))
    out.append(case("net/offline-pinned-not-cached", "offline, a pinned release that is not cached: offline_unavailable", "5.5",
                    [open_latest(), drv("restart_runner"), drv("server_stop"), drv("clear_log"),
                     net(step("open", err("offline_unavailable"), release=d1, offline=True, base_url=G, cache_dir="${cache}")),
                     drv("assert_requests", source="any", count=0)],
                    requires=["fs"]))
    out.append(case("net/offline-latest-is-newest-cached", "offline latest is the newest cached release (20991231.2 > 20991231)", "5.2, 4.3.1",
                    [net(step("open", {"datestamp": d1}, release=d1, base_url=G, cache_dir="${cache}")),
                     net(step("open", {"datestamp": d2}, release=d2, base_url=G, cache_dir="${cache}")),
                     drv("restart_runner"), drv("server_stop"),
                     open_latest({"loaded_from": "cache", "datestamp": d2}, offline=True)],
                    requires=["fs"]))
    O = f"{SRV}/order/"
    out.append(case("net/offline-latest-counter-order", "offline latest is the newest cached release by counter: 20991231.10 > 20991231.2 (string order says otherwise)", "4.3.1, 5.2",
                    [net(step("open", {"datestamp": D10}, release=D10, base_url=O, cache_dir="${cache}")),
                     net(step("open", {"datestamp": d2}, release=d2, base_url=O, cache_dir="${cache}")),
                     drv("restart_runner"), drv("server_stop"),
                     open_latest({"loaded_from": "cache", "datestamp": D10}, base_url=O, offline=True)],
                    requires=["fs"]))
    out.append(case("net/releases-counter-order", "releases(): 20991231.10 before 20991231.2 (newest first by counter)", "4.3, 4.3.1",
                    [open_latest({"loaded_from": "download", "datestamp": D10, "format_version": "0.2"}, base_url=O),
                     net(step("releases", {"releases": [enc_release_info("order", D10, O), enc_release_info("order", d2, O)]}))],
                    requires=["fs"]))
    out.append(case("net/env-base-url", "OPENTIDECONSTANTS_BASE_URL sets the server", "4.2",
                    [drv("restart_runner", env={"OPENTIDECONSTANTS_BASE_URL": G}),
                     net(step("open", {"loaded_from": "download", "datestamp": d2}, cache_dir="${cache}")),
                     drv("assert_requests", match=r"^/good/", min=2)],
                    requires=["fs"]))
    out.append(case("net/env-cache-dir", "OPENTIDECONSTANTS_CACHE_DIR sets the cache root", "4.2, 5.4",
                    [drv("restart_runner", env={"OPENTIDECONSTANTS_CACHE_DIR": "${tmp}/envcache"}),
                     net(step("open", {"loaded_from": "download", "datestamp": d2}, base_url=G)),
                     drv("assert_files", dir="${tmp}/envcache/v1/releases/20991231.2", present=[".verified"], no_tmp=True)],
                    requires=["fs"]))
    out.append(case("net/pointer-fallback", "no per-major pointer (404): the SDK reads OTC_latest.json", "5.2",
                    [drv("server_rules", rules=[{"match": r"/good/OTC_latest-f0\.json$", "action": "status", "status": 404}]),
                     open_latest(), drv("assert_requests", match=r"/good/OTC_latest\.json$", min=1)],
                    requires=["fs"]))
    for root, code, exp_d in [("wrong-sha256", "checksum_mismatch", d1), ("truncated", "checksum_mismatch", d1),
                              ("pointer-mismatch", "checksum_mismatch", d1), ("format-major", "unsupported_format", d1),
                              ("unresolved-convention", "invalid_release", d1)]:
        extra = []
        if code == "checksum_mismatch":
            extra = [drv("assert_files", dir="${cache}/v1/releases/20991231", absent=[".verified", "OTC_20991231.json", "OTC_20991231.jsonl"], no_tmp=True, may_be_missing=True)]
        out.append(case(f"net/bad-{root}-latest", f"latest from bad/{root}: {code}", "4.8, 5.2, 7.4",
                        [net(step("open", err(code), base_url=f"{SRV}/bad/{root}/", cache_dir="${cache}", on_network_error="raise"))] + extra,
                        requires=["fs"]))
        if root == "pointer-mismatch":
            continue  # a pinned download reads no pointer (spec 5.2), so this root has no pinned case
        out.append(case(f"net/bad-{root}-pinned", f"pinned 20991231 from bad/{root}: {code}", "4.8, 5.2, 7.4",
                        [net(step("open", err(code), release=exp_d, base_url=f"{SRV}/bad/{root}/", cache_dir="${cache}", on_network_error="raise", mode="stream"))] + extra,
                        requires=["fs"]))
    out.append(case("net/checksum-error-fields", "checksum_mismatch has file, expected and actual", "4.8",
                    [net(step("open", err("checksum_mismatch", file={"$regex": r"OTC_20991231\.(json|json\.gz|jsonl)$"},
                                          expected={"$regex": "^[0-9a-f]{64}$"}, actual={"$regex": "^[0-9a-f]{64}$"}),
                              release=d1, base_url=f"{SRV}/bad/wrong-sha256/", cache_dir="${cache}"))],
                    requires=["fs"]))
    out.append(case("net/format-minor-latest", "latest from bad/format-minor (0.3) loads", "7.3",
                    [net(step("open", {"loaded_from": "download", "datestamp": d1, "format_version": "0.3"}, base_url=f"{SRV}/bad/format-minor/", cache_dir="${cache}"))],
                    requires=["fs"]))
    out.append(case("net/short-body", "a body shorter than its Content-Length (connection closed): network error", "5.7",
                    [drv("server_rules", rules=[{"match": r"\.(json\.gz|jsonl|json)$", "action": "short_body", "delta": 100}]),
                     net(step("open", err("network"), release=d2, base_url=G, cache_dir="${cache}", on_network_error="raise"))],
                    requires=["fs"], timeout_s=90))
    out.append(case("net/truncated-body", "a consistent but truncated response (wrong length for the release): checksum_mismatch", "5.2, 5.3",
                    [drv("server_rules", rules=[{"match": r"/good/OTC_20991231\.2\.(json\.gz|jsonl|json)$", "action": "truncate", "bytes": 1000}]),
                     net(step("open", err("checksum_mismatch"), release=d2, base_url=G, cache_dir="${cache}", on_network_error="raise"))],
                    requires=["fs"]))
    out.append(case("net/slow-timeout", "a body slower than the timeout: network error", "5.7",
                    [drv("server_rules", rules=[{"match": r"/good/OTC_20991231\.2\.(json\.gz|jsonl|json)$", "action": "slow", "delay_s": 4}]),
                     net(step("open", err("network"), release=d2, base_url=G, cache_dir="${cache}", on_network_error="raise", timeout=1))],
                    requires=["fs"], timeout_s=120))
    out.append(case("net/user-agent-suffix", "user_agent adds a suffix after one space", "5.7",
                    [open_latest(user_agent="conformance-test/1.0"),
                     drv("assert_requests", header={"user-agent": UA[:-1] + r" conformance-test/1\.0$"}, min=1, all=True)],
                    requires=["fs"]))
    # The proxy cases use ${server_alias}, a name that does not resolve: the request succeeds only through the
    # proxy, whatever the HTTP stack does with loopback addresses (README "Choices").
    GA = f"{SRV_ALIAS}/good/"
    out.append(case("net/proxy-option", "the proxy option sends every request through the proxy", "5.7",
                    [open_latest(base_url=GA, proxy="${proxy}"), drv("assert_requests", source="proxy", min=2),
                     drv("assert_requests", source="server", min=2)], requires=["fs"]))
    out.append(case("net/proxy-env", "HTTP_PROXY / http_proxy send requests through the proxy", "5.7",
                    [drv("restart_runner", env={"HTTP_PROXY": "${proxy}", "http_proxy": "${proxy}"}),
                     open_latest(base_url=GA), drv("assert_requests", source="proxy", min=2),
                     drv("assert_requests", source="server", min=2)], requires=["fs"]))
    out.append(case("net/proxy-env-no-proxy-other-host", "NO_PROXY for another host does not bypass the proxy", "5.7",
                    [drv("restart_runner", env={"HTTP_PROXY": "${proxy}", "http_proxy": "${proxy}", "NO_PROXY": "example.org", "no_proxy": "example.org"}),
                     open_latest(base_url=GA), drv("assert_requests", source="proxy", min=2)], requires=["fs"]))
    out.append(case("net/no-proxy-env", "NO_PROXY bypasses the proxy for the server host", "5.7",
                    [drv("restart_runner", env={"HTTP_PROXY": "${proxy}", "http_proxy": "${proxy}", "NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1"}),
                     open_latest(), drv("assert_requests", source="proxy", count=0), drv("assert_requests", source="server", min=2)],
                    requires=["fs"]))
    # releases / latest / check_for_update
    out.append(case("net/releases", "releases(): every release from OTC_index.json, newest first", "4.3",
                    [open_latest(), net(step("releases", {"releases": [info2, info1]}))], requires=["fs"]))
    out.append(case("net/releases-offline-cached-index", "releases() offline uses the cached index", "4.3, 5.5",
                    [open_latest(), net(step("releases", {"releases": [info2, info1]})), drv("restart_runner"), drv("server_stop"), drv("clear_log"),
                     open_latest({"loaded_from": "cache"}, offline=True), net(step("releases", {"releases": [info2, info1]})),
                     drv("assert_requests", source="any", count=0)], requires=["fs"]))
    out.append(case("net/releases-offline-no-index", "releases() offline with no cached index: offline_unavailable", "4.3",
                    [open_latest(), drv("restart_runner"), drv("server_stop"),
                     open_latest({"loaded_from": "cache"}, offline=True), net(step("releases", err("offline_unavailable")))], requires=["fs"]))
    out.append(case("net/latest-does-not-switch", "latest() returns the newest ReleaseInfo and does not switch the loaded release", "4.3",
                    [net(step("open", {"datestamp": d1}, release=d1, base_url=G, cache_dir="${cache}")),
                     net(step("latest", {"release": info2})),
                     step("release_metadata", {"datestamp": d1})], requires=["fs"]))
    out.append(case("net/check-for-update", "check_for_update: newer release on a pinned older one; null when current", "4.3",
                    [net(step("open", {"datestamp": d1}, release=d1, base_url=G, cache_dir="${cache}")),
                     net(step("check_for_update", {"release": info2})),
                     open_latest(), net(step("check_for_update", {"release": None})),
                     drv("clear_log"), net(step("check_for_update", {"release": None})),
                     drv("assert_requests", match=r"/good/OTC_latest-f0\.json$", count=1, status=304)], requires=["fs"]))
    return out


def group_update():
    out = []
    G = f"{SRV}/good/"
    d2, d1 = "20991231.2", "20991231"
    old_pointer = [{"match": r"/good/OTC_latest(-f0)?\.json$", "action": "json", "file": "good/OTC_index.json", "pointer": "/releases/1"}]
    R1 = Rel("good", d1)
    out.append(case("update/pinned", "update on a pinned client: pinned_release", "4.3, 4.8",
                    [net(step("open", {"datestamp": d1}, release=d1, base_url=G, cache_dir="${cache}")),
                     net(step("update", err("pinned_release")))], requires=["fs"]))
    out.append(case("update/file", "update on a client opened from a file: pinned_release", "4.3, 4.8",
                    [step("open", {"loaded_from": "file"}, file=f"{FIX}/good/OTC_{d2}.jsonl"), net(step("update", err("pinned_release")))], requires=["fs"]))
    out.append(case("update/swap", "update swaps to the newer release; a Release held from before still shows the old one", "4.3, 5.6",
                    [drv("server_rules", rules=old_pointer),
                     net(step("open", {"loaded_from": "download", "datestamp": d1}, base_url=G, cache_dir="${cache}")),
                     step("hold_release", None, name="old"),
                     drv("server_rules", rules=[]),
                     net(step("update", {"updated": True, "from": d1, "to": d2})),
                     step("release_metadata", {"datestamp": d2}),
                     step("station", {"station": None}, station_id="OTC-T-0021"),
                     step("release_metadata", {"datestamp": d1}, on="old"),
                     step("station", {"station": enc_station(R1, R1.by_id["OTC-T-0021"])}, station_id="OTC-T-0021", on="old")], requires=["fs"]))
    out.append(case("update/none", "update when the loaded release is the newest: updated false, from = to", "4.3",
                    [open_latest_step(G), net(step("update", {"updated": False, "from": d2, "to": d2})), step("release_metadata", {"datestamp": d2})], requires=["fs"]))
    out.append(case("update/auto", "auto_update with update_interval 1 s: the first query after the interval switches the release", "5.6",
                    [drv("server_rules", rules=old_pointer),
                     net(step("open", {"datestamp": d1}, base_url=G, cache_dir="${cache}", auto_update=True, update_interval=1)),
                     drv("server_rules", rules=[]), drv("sleep", s=2.5),
                     # the first query must already see the new release: OTC-T-0021 is active in 20991231, removed in .2
                     step("station", {"station": None}, station_id="OTC-T-0021"),
                     step("release_metadata", {"datestamp": d2})], requires=["fs"]))
    out.append(case("update/auto-off", "without auto_update the loaded release never changes", "5.6",
                    [drv("server_rules", rules=old_pointer),
                     net(step("open", {"datestamp": d1}, base_url=G, cache_dir="${cache}", update_interval=1)),
                     drv("server_rules", rules=[]), drv("sleep", s=2.5),
                     step("station", {"station": enc_station(R1, R1.by_id["OTC-T-0021"])}, station_id="OTC-T-0021"),
                     step("release_metadata", {"datestamp": d1})], requires=["fs"]))
    return out


def open_latest_step(G, **kw):
    args = {"base_url": G, "cache_dir": "${cache}"}
    args.update(kw)
    return net(step("open", {"loaded_from": "download", "datestamp": "20991231.2"}, **args))


def group_cache():
    out = []
    G = f"{SRV}/good/"
    d2, d1 = "20991231.2", "20991231"
    both = [net(step("open", {"datestamp": d1}, release=d1, base_url=G, cache_dir="${cache}")),
            net(step("open", {"datestamp": d2}, release=d2, base_url=G, cache_dir="${cache}"))]
    O = f"{SRV}/order/"
    out.append(case("cache/cached-releases-counter-order", "cached_releases orders by counter: 20991231.10 before 20991231.2", "4.3, 4.3.1",
                    [net(step("open", {"datestamp": D10}, release=D10, base_url=O, cache_dir="${cache}")),
                     net(step("open", {"datestamp": d2}, release=d2, base_url=O, cache_dir="${cache}")),
                     net(step("cached_releases", {"datestamps": [D10, d2]}))], requires=["fs"]))
    out.append(case("cache/prune-counter-order", "prune(keep: 1) keeps 20991231.10 (newest by counter) and removes 20991231.2", "4.3, 4.3.1",
                    [net(step("open", {"datestamp": d2}, release=d2, base_url=O, cache_dir="${cache}")),
                     net(step("open", {"datestamp": D10}, release=D10, base_url=O, cache_dir="${cache}")),
                     net(step("prune", {"removed": [d2]}, keep=1)), net(step("cached_releases", {"datestamps": [D10]}))], requires=["fs"]))
    out.append(case("cache/cached-releases", "cached_releases lists the cached datestamps, newest first", "4.3",
                    both + [net(step("cached_releases", {"datestamps": [d2, d1]}))], requires=["fs"]))
    out.append(case("cache/prune", "prune(keep: 1) removes the older release and returns it", "4.3",
                    both + [net(step("prune", {"removed": [d1]}, keep=1)), net(step("cached_releases", {"datestamps": [d2]})),
                            drv("assert_files", dir="${cache}/v1/releases", absent=[d1], present=[d2])], requires=["fs"]))
    out.append(case("cache/prune-keeps-loaded", "prune never removes the loaded release", "4.3",
                    both + [net(step("open", {"loaded_from": "cache", "datestamp": d1}, release=d1, base_url=G, cache_dir="${cache}")),
                            net(step("prune", {"removed": []}, keep=1)), net(step("cached_releases", {"datestamps": [d2, d1]}))], requires=["fs"]))
    out.append(case("cache/prune-invalid", "prune with a negative keep: invalid_argument", "4.3, 4.8",
                    [open_latest_step(G), net(step("prune", err("invalid_argument"), keep=-1))], requires=["fs"]))
    out.append(case("cache/verify", "verify on a cached release passes, and fails after a cached file changes", "4.3, 5.3",
                    [open_latest_step(G, mode="stream"), step("verify", {"verified": True}),
                     drv("corrupt", path="${cache}/v1/releases/20991231.2/OTC_20991231.2.jsonl", offset=50),
                     step("verify", err("checksum_mismatch"))], requires=["fs"]))
    out.append(case("cache/not-writable", "a cache directory that cannot be created: cache error", "4.8",
                    [drv("write", path="${tmp}/not-a-dir", text="x"),
                     net(step("open", err("cache"), base_url=G, cache_dir="${tmp}/not-a-dir/cache"))], requires=["fs"]))
    out.append(case("cache/files-from-verified", "loaded_from cache: release.files comes from .verified", "4.3.1",
                    [open_latest_step(G), drv("restart_runner"), drv("server_stop"),
                     net(step("open", {"loaded_from": "cache", "datestamp": d2}, release=d2, base_url=G, cache_dir="${cache}")),
                     step("release_files", {"files": enc_release_info("good", d2, G)["files"]})], requires=["fs"]))
    return out


def group_download():
    out = []
    G = f"{SRV}/good/"
    d2, d1 = "20991231.2", "20991231"
    B = "${tmp}/bundle"
    default_files = [f"OTC_{d2}.jsonl", f"OTC_{d2}.meta.json", f"OTC_{d2}.sha256"]

    def dl(expect, **kw):
        return net(step("download", expect, **kw), fs=True)

    def same(names):
        return [drv("assert_sha256", path=f"{B}/{n}", equals=f"{FIX}/good/{n}") for n in names]

    out.append(case("download/then-open", "download-then-open: download writes jsonl, meta and sha256; file: on the result is loaded_from file and verify passes", "4.3.2, 7.1",
                    [open_latest_step(G),
                     dl({"paths": default_files}, release=d2, to=B),
                     drv("assert_files", dir=B, exactly=default_files)] + same(default_files) +
                    [step("open", {"loaded_from": "file", "datestamp": d2}, file=f"{B}/OTC_{d2}.jsonl"),
                     step("verify", {"verified": True})], requires=[]))
    out.append(case("download/latest-default", "download with no release resolves latest through the pointer", "4.3.2",
                    [open_latest_step(G), dl({"paths": default_files}, to=B), drv("assert_files", dir=B, exactly=default_files)], requires=[]))
    out.append(case("download/identical", "download-identical: a second download writes nothing and returns an empty list", "4.3.2, 7.1",
                    [open_latest_step(G), dl({"paths": default_files}, release=d2, to=B), dl({"paths": []}, release=d2, to=B),
                     drv("assert_files", dir=B, exactly=default_files)], requires=[]))
    out.append(case("download/mismatch", "download-mismatch: a changed file fails with file_exists and stays; overwrite repairs it", "4.3.2, 7.1",
                    [open_latest_step(G), dl({"paths": default_files}, release=d2, to=B),
                     drv("corrupt", path=f"{B}/OTC_{d2}.jsonl", offset=10),
                     dl(err("file_exists", path={"$contains": f"OTC_{d2}.jsonl"}), release=d2, to=B),
                     drv("assert_sha256", path=f"{B}/OTC_{d2}.jsonl", equals=f"{FIX}/good/OTC_{d2}.jsonl", negate=True),
                     dl({"paths": [f"OTC_{d2}.jsonl"]}, release=d2, to=B, overwrite=True)] + same(default_files), requires=[]))
    out.append(case("download/conflict-changes-nothing", "a conflict is found before any write: a missing file is not written either", "4.3.2",
                    [open_latest_step(G), dl({"paths": default_files}, release=d2, to=B),
                     drv("corrupt", path=f"{B}/OTC_{d2}.jsonl", offset=10), drv("delete", path=f"{B}/OTC_{d2}.meta.json"),
                     dl(err("file_exists"), release=d2, to=B),
                     drv("assert_files", dir=B, exactly=[f"OTC_{d2}.jsonl", f"OTC_{d2}.sha256"])], requires=[]))
    out.append(case("download/from-cache", "download-from-cache: the cache holds the release, the server is stopped, no request", "4.3.2, 7.1",
                    [open_latest_step(G, mode="stream"), drv("server_stop"), drv("clear_log"),
                     dl({"paths": default_files}, release=d2, to=B), drv("assert_requests", source="any", count=0)] + same(default_files), requires=[]))
    out.append(case("download/bad-checksum", "download-bad-checksum: the server sends a file with a wrong SHA-256; checksum_mismatch and the file is not in the folder", "4.3.2, 7.1",
                    [step("open", {"loaded_from": "file"}, file=f"{FIX}/good/OTC_{d2}.jsonl", base_url=f"{SRV}/bad/wrong-sha256/", cache_dir="${cache}"),
                     dl(err("checksum_mismatch"), release=d1, to=B),
                     drv("assert_files", dir=B, absent=[f"OTC_{d1}.jsonl"], no_tmp=True, may_be_missing=True)], requires=["fs"]))
    out.append(case("download/formats", "download every format: json, json.gz, jsonl, plus meta and sha256", "4.3.2",
                    [open_latest_step(G),
                     dl({"paths": sorted([f"OTC_{d2}.json", f"OTC_{d2}.json.gz"] + default_files)}, release=d2, to=B, formats=["json", "json.gz", "jsonl"]),
                     drv("assert_files", dir=B, exactly=sorted([f"OTC_{d2}.json", f"OTC_{d2}.json.gz"] + default_files))] +
                    same([f"OTC_{d2}.json", f"OTC_{d2}.json.gz"]), requires=[]))
    out.append(case("download/invalid-format", "an unknown format: invalid_argument", "4.3.2",
                    [open_latest_step(G), dl(err("invalid_argument"), release=d2, to=B, formats=["csv"])], requires=[]))
    out.append(case("download/invalid-release", "a bad datestamp: invalid_argument", "4.3.2",
                    [open_latest_step(G), dl(err("invalid_argument"), release="2099", to=B)], requires=[]))
    out.append(case("download/not-found", "a datestamp the server does not have: release_not_found", "4.3.2",
                    [open_latest_step(G), dl(err("release_not_found"), release="20991230", to=B)], requires=[]))
    out.append(case("download/offline-not-cached", "offline, a release not in the cache: offline_unavailable", "4.3.2",
                    [step("open", {"loaded_from": "file"}, file=f"{FIX}/good/OTC_{d2}.jsonl", base_url=G, cache_dir="${cache}", offline=True),
                     dl(err("offline_unavailable"), release=d1, to=B)], requires=["fs"]))
    return out


def as_(role, st):
    """A runner step for one role of a cross-SDK case (a list of roles: sent to all of them at once)."""
    return {"as": role, **st}


def group_cross(R2):
    """The cross-SDK cases (spec §5.4, §5.5, §6.2, phase step S4). The driver runs each case once per ordered
    pair of distinct runners (--cross); the writer fills the cache, the reader uses it."""
    out = []
    d = R2.datestamp
    G = f"{SRV}/good/"
    rdir = f"${{cache}}/v1/releases/{d}"
    idx, jl = f"{rdir}/index-v1.json", f"{rdir}/OTC_{d}.jsonl"
    fs_stream = ["fs", "fetch", "stream"]
    roles = {"writer": fs_stream, "reader": fs_stream}
    fill = [as_("writer", step("open", {"loaded_from": "download", "datestamp": d}, release=d, base_url=G, cache_dir="${cache}", mode="stream")),
            as_("writer", step("station_count", {"station_count": len(R2.active)})),
            as_("writer", step("close")),
            drv("assert_files", dir=rdir, present=[".verified", f"OTC_{d}.sha256", f"OTC_{d}.jsonl", f"OTC_{d}.meta.json", "index-v1.json"],
                absent=[".lock"], no_tmp=True),
            drv("assert_index", path=idx, jsonl=jl, datestamp=d)]
    offline = [drv("server_stop"), drv("clear_log")]
    no_requests = drv("assert_requests", source="any", count=0)
    ids3 = ["OTC-T-0006", "OTC-T-0010", "OTC-T-0007"]
    queries = [as_("reader", step("station_count", {"station_count": len(R2.active)})),
               as_("reader", step("tombstone_count", {"tombstone_count": len(R2.tombs)})),
               as_("reader", step("near", {**near(R2, 0.0, 179.95, 50), "tolerance": TOL}, lat=0.0, lon=179.95, radius_km=50)),
               as_("reader", step("search", {"station_ids": search(R2, "tromso")}, name="tromso")),
               as_("reader", step("stations", {"station_ids": [s["station_id"] for s in apply_filters(R2, R2.active, {"kind": "current"})]}, kind="current")),
               as_("reader", step("station", {"station": enc_station(R2, R2.by_id["OTC-T-0003"])}, station_id="OTC-T-0003")),
               as_("reader", step("citation", {"citation": citation(R2)})),
               as_("reader", step("attribution", {"attribution": attribution(R2, ids3)}, station_ids=ids3))]
    out.append(case("cross/cache-offline-stream", "one SDK fills the cache in stream mode; another opens it offline (server stopped) and gets the same answers, with no request", "5.4, 5.5, 6.2",
                    fill + offline + [
                        as_("reader", step("open", {"loaded_from": "cache", "datestamp": d}, release=d, cache_dir="${cache}", offline=True, mode="stream")),
                        as_("reader", step("verify", {"verified": True})),
                        as_("reader", step("release_files", {"files": {"$len_min": 4}}))] + queries + [
                        as_("reader", step("open", {"loaded_from": "cache", "datestamp": d}, cache_dir="${cache}", offline=True, mode="stream")),
                        as_("reader", step("cached_releases", {"datestamps": [d]})),
                        no_requests,
                        drv("assert_index", path=idx, jsonl=jl, datestamp=d)],
                    roles=roles))
    out.append(case("cross/cache-offline-eager", "one SDK fills the cache in stream mode; another opens the cached .jsonl offline in eager mode", "5.4, 5.5, 6.1",
                    fill + offline + [
                        as_("reader", step("open", {"loaded_from": "cache", "datestamp": d}, release=d, cache_dir="${cache}", offline=True, mode="eager"))]
                    + queries + [no_requests],
                    roles={"writer": fs_stream, "reader": ["fs", "fetch", "eager"]}))
    # The reader must use a fresh index that another SDK wrote, not rebuild it: a change to one entry (still
    # fresh: the .jsonl digest and size match) shows in the reader's answers, and the file is not rewritten.
    pos = [s["station_id"] for s in R2.doc["stations"]].index("OTC-T-0011")
    country = R2.by_id["OTC-T-0011"]["country"]
    out.append(case("cross/index-shared", "the reader uses the stream index the writer built (a fresh index is read, not rebuilt)", "6.2",
                    fill + [drv("json_set", path=idx, pointer=f"/stations/{pos}/country", value="ZZ"),
                            drv("copy", files=[idx], to="${tmp}/index-copy")] + offline + [
                        as_("reader", step("open", {"loaded_from": "cache", "datestamp": d}, release=d, cache_dir="${cache}", offline=True, mode="stream")),
                        as_("reader", step("stations", {"station_ids": ["OTC-T-0011"]}, country="ZZ")),
                        as_("reader", step("close")),
                        drv("assert_sha256", path=idx, equals="${tmp}/index-copy/index-v1.json"),
                        no_requests],
                    roles=roles))
    out.append(case("cross/index-stale", "a stale stream index (its jsonl_sha256 does not match) is ignored, rebuilt and rewritten", "6.2",
                    fill + [drv("json_set", path=idx, pointer=f"/stations/{pos}/country", value="ZZ"),
                            drv("json_set", path=idx, pointer="/jsonl_sha256", value="0" * 64)] + offline + [
                        as_("reader", step("open", {"loaded_from": "cache", "datestamp": d}, release=d, cache_dir="${cache}", offline=True, mode="stream")),
                        as_("reader", step("stations", {"station_ids": []}, country="ZZ")),
                        as_("reader", step("stations", {"station_ids": [x["station_id"] for x in apply_filters(R2, R2.active, {"country": country})]}, country=country)),
                        as_("reader", step("close")),
                        drv("assert_index", path=idx, jsonl=jl, datestamp=d),
                        no_requests],
                    roles=roles))
    out.append(case("cross/index-other-version", "an index with another index_version is stale: rebuilt and rewritten", "6.2",
                    fill + [drv("json_set", path=idx, pointer=f"/stations/{pos}/country", value="ZZ"),
                            drv("json_set", path=idx, pointer="/index_version", value=2)] + offline + [
                        as_("reader", step("open", {"loaded_from": "cache", "datestamp": d}, release=d, cache_dir="${cache}", offline=True, mode="stream")),
                        as_("reader", step("stations", {"station_ids": []}, country="ZZ")),
                        as_("reader", step("close")),
                        drv("assert_index", path=idx, jsonl=jl, datestamp=d),
                        no_requests],
                    roles=roles))
    # Two processes (two SDKs) open the same uncached release at once. The data file is slow, so the second one
    # finds the lock (§5.4 Locks), waits for .verified and loads it: one download of each file in all.
    both = ["writer", "reader"]
    out.append(case("cross/lock-contention", "two SDKs open the same uncached release at once: the lock directory stops the second download", "5.4",
                    [drv("server_rules", rules=[{"match": rf"/good/OTC_{re.escape(d)}\.jsonl$", "action": "slow", "delay_s": 2}]),
                     as_(both, step("open", {"loaded_from": {"$any_of": ["download", "cache"]}, "datestamp": d},
                                    release=d, base_url=G, cache_dir="${cache}", mode="stream")),
                     as_(both, step("station_count", {"station_count": len(R2.active)})),
                     drv("assert_requests", source="server", match=rf"/good/OTC_{re.escape(d)}\.jsonl$", status=200, count=1),
                     drv("assert_files", dir=rdir, present=[".verified", "index-v1.json"], absent=[".lock"], no_tmp=True),
                     drv("assert_index", path=idx, jsonl=jl, datestamp=d)],
                    roles=roles, timeout_s=90))
    return out


GROUPS = {
    "load": lambda R2, R1: group_load(),
    "release": group_release,
    "stations": group_stations,
    "sets": lambda R2, R1: group_sets(R2),
    "search": lambda R2, R1: group_search(R2),
    "geo": lambda R2, R1: group_geo(R2),
    "tolerant": lambda R2, R1: group_tolerant(),
    "network": lambda R2, R1: group_network(),
    "update": lambda R2, R1: group_update(),
    "cache": lambda R2, R1: group_cache(),
    "download": lambda R2, R1: group_download(),
}


def build(outdir: Path, crossdir: Path):
    R2, R1 = Rel("good", "20991231.2"), Rel("good", "20991231")
    crossdir.mkdir(parents=True, exist_ok=True)
    cross = group_cross(R2)
    doc = {"suite_version": SUITE_VERSION, "group": "cross",
           "description": "Generated by conformance/tools/build_cases.py from conformance/fixtures; do not edit. "
                          "Run with driver.py --cross NAME=COMMAND (two or more runners).",
           "cases": cross}
    (crossdir / "cross.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    outdir.mkdir(parents=True, exist_ok=True)
    seen = set()
    for name, fn in GROUPS.items():
        cases = fn(R2, R1)
        for c in cases:
            if c["id"] in seen:
                raise SystemExit(f"duplicate case id {c['id']}")
            seen.add(c["id"])
        doc = {"suite_version": SUITE_VERSION, "group": name,
               "description": "Generated by conformance/tools/build_cases.py from conformance/fixtures; do not edit.",
               "cases": cases}
        (outdir / f"{name}.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return len(seen)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="rebuild in a temporary directory and compare with conformance/cases")
    a = ap.parse_args()
    if not a.check:
        n = build(CASES, CROSS)
        print(f"wrote {n} cases to {CASES} and the cross-SDK cases to {CROSS}")
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        n = build(Path(tmp) / "cases", Path(tmp) / "cross")
        fresh = {f"cases/{p.name}": p.read_bytes() for p in (Path(tmp) / "cases").glob("*.json")}
        fresh.update({f"cross/{p.name}": p.read_bytes() for p in (Path(tmp) / "cross").glob("*.json")})
        committed = {f"cases/{p.name}": p.read_bytes() for p in CASES.glob("*.json")}
        committed.update({f"cross/{p.name}": p.read_bytes() for p in CROSS.glob("*.json")})
        bad = sorted(set(fresh) ^ set(committed)) + sorted(k for k in fresh if k in committed and fresh[k] != committed[k])
        if bad:
            print("FAIL: committed cases differ from a fresh build: " + ", ".join(bad))
            return 1
        print(f"OK: {n} cases; committed files equal a fresh build ({len(fresh)} files)")
        return 0


if __name__ == "__main__":
    sys.exit(main())
