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
import copy
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
SUITE_VERSION = "1.0"
EARTH_R_KM = 6371.0088
TOL = 1e-6

FIX = "${fixtures}"
SRV = "${server}"
SRV_ALIAS = "${server_alias}"  # the fixture server under a name only the recording proxy resolves
CRED_USER, CRED_PASS = "otcpk12user", "Pk12S3cretPW"  # distinctive credentials for the DR21 redaction cases
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


def status_of(s):
    return "active" if s.get("status") is None else s["status"]


class Rel:
    """One fixture release, indexed the way an SDK indexes it (spec §6.1)."""

    def __init__(self, root, datestamp, commercial_only=False):
        self.commercial_only = commercial_only   # the open option of K-NC DR106 (spec 4.2)
        self.root = root
        self.datestamp = datestamp
        self.doc = load_release(root, datestamp)
        # a line with no status (or null) is an active station (CR2 DR28); any other status is no station and no
        # tombstone (CR2 DR8)
        self.active = sorted([s for s in self.doc["stations"] if status_of(s) == "active"], key=lambda s: s["station_id"])
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

    def commercial(self, licence_id):
        """The licence allows commercial use: its commercial_use is true (spec 4.2, 4.6; K-NC DR104)."""
        return self.licences[licence_id].get("commercial_use") is True

    def effective_set(self, s):
        """The effective recommended set under commercial_only (spec 4.2, K-NC DR106): the release's recommended
        set when its licence is commercial; otherwise the first set in file order with the same typed quantity,
        qc_status ok, and a commercial licence; then the same with flagged; otherwise none. A set with no quantity
        never matches."""
        rs = self.rec_set(s)
        if rs is None or self.commercial(rs["licence_id"]):
            return rs
        q = typed(rs.get("quantity"), QUANTITIES)
        if q is None:
            return None
        for status in ("ok", "flagged"):
            for cs in s.get("constant_sets", []):
                if typed(cs.get("quantity"), QUANTITIES) == q and read_qc(cs) == status and self.commercial(cs["licence_id"]):
                    return cs
        return None

    def eff_set(self, s):
        """The station's recommended set as the SDK gives it: the effective one with commercial_only, else the
        release's (spec 4.5)."""
        return self.effective_set(s) if self.commercial_only else self.rec_set(s)

    def tide_source_licences(self, s):
        """The licences of the station's tide source under commercial_only (spec 4.2, K-NC DR106): its effective
        set; else the one-link offsets path (the reference station's first set in file order from the offsets'
        source, noaa in format 1.0, water_level, ok or flagged), usable only when the offsets' licence and that
        set's licence are commercial; else none (no usable tides)."""
        es = self.effective_set(s)
        if es is not None:
            return {es["licence_id"]}
        off = s.get("subordinate_offsets")
        if not off:
            return set()
        ref = self.by_id.get(off.get("reference_station_id"))
        if ref is None:
            return set()
        refset = next((cs for cs in ref.get("constant_sets", []) if cs.get("source") == OFFSETS_SOURCE
                       and typed(cs.get("quantity"), QUANTITIES) == "water_level" and read_qc(cs) in WITH_CONSTANTS), None)
        if refset is None:
            return set()
        lics = {refset["licence_id"]} | ({off["licence_id"]} if off.get("licence_id") else set())
        return lics if all(self.commercial(x) for x in lics) else set()

    def kind(self, s, seen=()):
        rs = self.rec_set(s)
        if rs is not None:
            return {"water_level": "tide", "current": "current"}.get(rs.get("quantity"), "other")
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


STATION_TYPES = ("reference", "subordinate")
QUANTITIES = ("water_level", "current")
OFFSETS_SOURCE = "noaa"   # the source of every subordinate_offsets in format 1.0 (spec 4.2, K-NC DR106)
SOURCE_TYPES = ("official", "gauge", "model")


def typed(v, known):
    """An enum value as an SDK reads it: null stays null, a value format 1.0 does not have is "other" (spec 7.3)."""
    return None if v is None else v if v in known else "other"


def enc_station(rel, s):
    k = rel.kind(s)
    rs = rel.eff_set(s)
    return {
        "station_id": s["station_id"], "name": s["name"], "country": s["country"],
        "lat": s["lat"], "lon": s["lon"], "type": typed(s["type"], STATION_TYPES), "kind": k,
        "timezone": s.get("timezone"), "aliases": aliases_enc(s), "status": status_of(s),
        "is_reference": s["type"] == "reference", "is_subordinate": s["type"] == "subordinate",
        "is_tide": k == "tide", "is_current": k == "current",
        "recommended_set_id": rs["set_id"] if rs else None,
    }


def enc_tombstone(t):
    return {"station_id": t["station_id"], "name": t.get("name"), "status": t["status"],
            "removed_in": t.get("removed_in"), "removed_reason": t.get("removed_reason"),
            "merged_into": t.get("merged_into"), "detail": t.get("detail")}


def enc_set(rel, s, cs):
    span = cs.get("record_span")
    datum = cs.get("datum")
    return {
        "set_id": cs["set_id"], "source": cs["source"], "source_type": typed(cs["source_type"], SOURCE_TYPES),
        "quantity": typed(cs.get("quantity"), QUANTITIES),
        "source_record_id": cs.get("source_record_id"), "source_version": cs.get("source_version"),
        "record_span": None if span is None else {"start": span.get("start"), "end": span.get("end"), "good_samples": span.get("good_samples")},
        "datum": None if datum is None else {"msl_offset_m": datum.get("msl_offset_m"), "named": dict(datum.get("named") or {})},
        "qc_status": read_qc(cs),
        "qc_flags": [{"flag": f["flag"], "reason": f["reason"], "values": f.get("values")} for f in cs.get("qc_flags") or []],
        "dropped_constituents": [{"name": d["name"], "dropped_reason": d["dropped_reason"], "detail": d.get("detail")} for d in cs.get("dropped_constituents") or []],
        "time_base": enc_time_base(cs.get("time_base")),
        "is_recommended": rel.eff_set(s) is not None and cs["set_id"] == rel.eff_set(s)["set_id"],
        "convention_id": cs["convention_id"], "licence_id": cs["licence_id"],
        "constituent_count": len(cs.get("constituents") or []),
    }


CONSTITUENT_FIELDS = ["name", "source_name", "doodson", "speed_deg_per_hour", "amplitude_m", "phase_deg",
                      "amp_uncertainty_m", "phase_uncertainty_deg", "kept_reason"]
CONVENTION_FIELDS = ["convention_id", "phase_reference", "utc_offset_hours", "v0_model", "nodal_handling",
                     "nodal_formula_ids", "constituent_table_version", "tables_sha256", "canary"]
LICENCE_FIELDS = ["licence_id", "spdx", "provider", "citation", "attribution", "url",
                  "commercial_use", "restriction", "terms_url"]   # the last three: K-NC DR104
PROVENANCE_FIELDS = ["adapter_version", "input_sha256", "selection_reason", "decision", "carried_from_release"]
VALIDATION_FIELDS = ["set_id", "reference_source", "reference_station", "reference_distance_km", "window",
                     "time_mae_min", "time_p95_min", "time_bias_min", "height_mae_m", "range_error_m",
                     "missed_events", "extra_events", "previous_release"]
PREVIOUS_FIELDS = ["time_mae_min", "time_p95_min", "time_bias_min", "height_mae_m", "range_error_m",
                   "missed_events", "extra_events"]
OFFSET_FIELDS = ["reference_station_id", "time_offset_high_min", "time_offset_low_min", "height_offset_high",
                 "height_offset_low", "height_adjusted_type", "licence_id"]


def pick(d, fields):
    return {f: (d.get(f) if d is not None else None) for f in fields}


BUILD_FIELDS = ["build_commit", "built_at", "fetched_at", "run_id", "tool_versions"]


def enc_provenance(p):
    """Provenance (spec 4.6): build (ProvenanceBuild; format 1.0 requires it, so it is null only for malformed
    input), adapter_version, input_sha256, selection_reason, decision and carried_from_release (spec 7.4)."""
    out = pick(p, PROVENANCE_FIELDS)
    out["build"] = None if p.get("build") is None else pick(p["build"], BUILD_FIELDS)
    return out


TIME_BASE_FIELDS = ["code", "reason", "declared", "published", "correction", "months_dropped", "decided_in",
                    "decided_build_commit", "evidence"]
EVIDENCE_FIELDS = ["comparator_kind", "comparator_id", "distance_km", "lag_min", "detail"]


def enc_time_base(t):
    """TimeBase (spec 4.5): the set's time-base annotation, or null when the set has none."""
    if t is None:
        return None
    out = pick(t, TIME_BASE_FIELDS)
    out["correction"] = None if t.get("correction") is None else pick(t["correction"], ["from", "to"])
    out["months_dropped"] = list(t.get("months_dropped") or [])
    out["evidence"] = [pick(e, EVIDENCE_FIELDS) for e in t.get("evidence") or []]
    return out


def enc_validation(v):
    out = pick(v, VALIDATION_FIELDS)
    prev = v.get("previous_release")
    out["previous_release"] = None if prev is None else pick(prev, PREVIOUS_FIELDS)
    return out


def enc_release_meta(rel, version_doi=None):
    """release_metadata. zenodo_version_doi is not in the release document (spec 4.3): it comes from the pointer or
    index entry the SDK read, so it is null for a file and for a pinned download (which reads no pointer)."""
    r = rel.doc["release"]
    return {"datestamp": r["datestamp"], "created": r["created"], "format_version": rel.doc["format_version"],
            "concept_doi": r.get("concept_doi"), "zenodo_version_doi": version_doi,
            "source_versions": r.get("source_versions") or {},
            "build_commit": r.get("build_commit"), "changelog_url": r.get("changelog_url")}


def pointer_entry(root, datestamp):
    idx = json.loads((FIXTURES / root / "OTC_index.json").read_text())
    for e in idx["releases"]:
        if e["datestamp"] == datestamp:
            return e
    raise KeyError(datestamp)


def enc_release_info(root, datestamp, base):
    """ReleaseInfo (spec 3)."""
    e = pointer_entry(root, datestamp)
    return {"datestamp": e["datestamp"], "format_version": e["format_version"], "concept_doi": e["concept_doi"],
            "zenodo_version_doi": e["zenodo_version_doi"], "content_sha256": e["content_sha256"],
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


# Sets with no fitted constants (qc_status no_constants): constant_sets() leaves them out by default and
# include_no_constants: true lists them; the source filter and stats.source do not count them (spec 4.3, 4.4, 4.5).
NOT_USABLE = ("no_constants",)
WITH_CONSTANTS = ("ok", "flagged")
QC_STATUS = ("ok", "flagged", "no_constants")


def read_qc(cs):
    """A qc_status value format 1.0 does not have is an unknown enum value: "other" (spec 7.3, 7.4)."""
    return cs["qc_status"] if cs["qc_status"] in QC_STATUS else "other"


def usable_sources(s):
    """The sources the source filter matches: sets with constants (ok, flagged), the same sets stats.source counts.
    A qc_status 1.0 does not have ("other", spec 7.3) counts for neither."""
    return {cs["source"] for cs in s.get("constant_sets", []) if cs["qc_status"] in WITH_CONSTANTS}


def apply_filters(rel, stations, f):
    out = []
    for s in stations:
        if "country" in f and s["country"] != f["country"]:
            continue
        # the filters compare the typed value: an unknown enum value is "other" (CR2 DR7)
        if "type" in f and typed(s["type"], STATION_TYPES) != f["type"]:
            continue
        if "kind" in f and rel.kind(s) != f["kind"]:
            continue
        if "source" in f and f["source"] not in usable_sources(s):
            continue
        if "source_type" in f:
            rs = rel.eff_set(s)   # the effective recommended set under commercial_only (K-NC DR106)
            if rs is None or typed(rs["source_type"], SOURCE_TYPES) != f["source_type"]:
                continue
        out.append(s)
    return out


def discovery_filters(rel, stations, filters):
    """SDK-QFILT oracle only for the P1b stations/search/geo/knc cases; legacy cases stay frozen."""
    def eligible(cs, licence=None):
        status = cs.get("qc_status")
        if status not in ("ok", "flagged"):
            return False
        fallback = cs.get("fallback")
        if fallback is not None:
            if not filters.get("include_fallback", False):
                return False
        elif status == "flagged" and not filters.get("include_flagged", False):
            return False
        if licence is not None and licence not in rel.licences:
            return False
        if not rel.commercial_only:
            return True
        if fallback is not None and fallback.get("reason") == "licence_reading" and getattr(rel, "commercial_basis", "strict") == "strict":
            return False
        return all(rel.licences[lid].get("commercial_use") is True
                   for lid in [cs["licence_id"]] + ([licence] if licence is not None else []))

    def paths(station):
        yield from (cs for cs in station.get("constant_sets", []) if eligible(cs))
        offsets = station.get("subordinate_offsets") or {}
        ref = rel.by_id.get(offsets.get("reference_station_id"))
        if ref is not None:
            selected = next((cs for cs in ref.get("constant_sets", []) if cs.get("source") == "noaa"
                             and cs.get("quantity") == "water_level" and cs.get("qc_status") in ("ok", "flagged")), None)
            if selected is not None and eligible(selected, offsets.get("licence_id")):
                yield selected
        for offsets in station.get("current_offsets", []):
            ref = rel.by_id.get(offsets.get("reference_station_id"))
            if ref is None:
                continue
            selected = next((cs for cs in ref.get("constant_sets", []) if cs.get("quantity") == "current"
                             and cs.get("qc_status") in ("ok", "flagged")
                             and any(b["bin"] == offsets.get("reference_bin") for b in cs.get("current_bins", []))), None)
            if selected is not None and eligible(selected, offsets.get("licence_id")):
                yield selected

    metadata = {k: v for k, v in filters.items() if k in ("country", "type", "kind")}
    return [st for st in apply_filters(rel, stations, metadata)
            if any(("source" not in filters or cs["source"] == filters["source"])
                   and ("source_type" not in filters or typed(cs["source_type"], SOURCE_TYPES) == filters["source_type"])
                   for cs in paths(st))]


def discovery_case(group, rel, basis=None):
    """Label actual committed fixture constants in a native reader case; producer integration is separate."""
    sid = "OTC-T-0002"
    station = rel.by_id[sid]
    cs = station["constant_sets"][0]
    index = next(i for i, st in enumerate(rel.doc["stations"]) if st["station_id"] == sid)
    label = {"reason": "licence_reading", "basis": "Actual committed synthetic fixture source evidence"}
    path = "${tmp}/filtered/OTC_20991231.2.json"
    options = {} if basis is None else {"commercial_only": True, "commercial_basis": basis}
    steps = [drv("copy", files=[f"{FIX}/good/OTC_20991231.2.json"], to="${tmp}/filtered"),
             drv("json_set", path=path, pointer=f"/stations/{index}/constant_sets/0/fallback", value=label),
             step("open", {"loaded_from": "file_unverified", "datestamp": "20991231.2"}, file=path, **options)]
    ops = {"stations": ("stations", "iter_stations"), "search": ("search",), "geo": ("near", "nearest"),
           "knc": ("stations", "iter_stations", "search", "near", "nearest")}[group]
    for flagged, fallback in ((False, False), (True, False), (False, True), (True, True)):
        admitted = fallback and basis != "strict"
        for op in ops:
            args = {"source": cs["source"], "include_flagged": flagged, "include_fallback": fallback}
            if op == "search":
                args.update(name=station["name"], match="exact", limit=1)
            if op in ("near", "nearest"):
                args.update(lat=station["lat"], lon=station["lon"])
                args["radius_km" if op == "near" else "max_km"] = 0.001
            expect = {"station_ids": [sid] if admitted else []}
            if op == "near":
                expect["distance_km"] = [0.0] if admitted else []
            if op == "nearest":
                expect = {"station_id": sid if admitted else None, "distance_km": 0.0 if admitted else None}
            steps.append(step(op, expect, **args))
    value = enc_set(rel, station, cs)
    value["fallback"] = {k: label.get(k) for k in ("reason", "basis", "otc_finding", "preferred_set_id")}
    steps.append(step("constant_set", {"set": value}, station_id=sid, set_id=cs["set_id"]))
    return case(f"{group}/qfilt-labelled-fallback" + (f"-{basis}" if basis else ""),
                "Independent fallback/flagged discovery opt-ins retain explicit metadata and licence basis", "SDK-QFILT",
                steps, requires=["fs", "json", "eager"], runners=["python"])


def occurrences(text, sub):
    """Every start index of sub in text, overlapping ones included."""
    out, i = [], text.find(sub)
    while i != -1:
        out.append(i)
        i = text.find(sub, i + 1)
    return out


def search(rel, name, limit=None, match=None, query_filters=apply_filters, **f):
    q = fold(name)
    ranked = []
    for s in query_filters(rel, rel.active, f):
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


def near(rel, lat, lon, radius_km, limit=None, query_filters=apply_filters, **f):
    hits = sorted((haversine(lat, lon, s["lat"], s["lon"]), s["station_id"]) for s in query_filters(rel, rel.active, f))
    hits = [h for h in hits if h[0] <= radius_km]
    if limit is not None:
        hits = hits[:limit]
    return {"station_ids": [h[1] for h in hits], "distance_km": [h[0] for h in hits]}


def nearest(rel, lat, lon, max_km=None, query_filters=apply_filters, **f):
    hits = sorted((haversine(lat, lon, s["lat"], s["lon"]), s["station_id"]) for s in query_filters(rel, rel.active, f))
    if max_km is not None:
        hits = [h for h in hits if h[0] <= max_km]
    if not hits:
        return {"station_id": None, "distance_km": None}
    return {"station_id": hits[0][1], "distance_km": hits[0][0]}


def attribution(rel, station_ids=None):
    r = rel.doc["release"]
    if rel.commercial_only:   # K-NC DR106: the commercial licences of the release, or of each station's tide source
        if not station_ids:
            lic_ids = {x for x in rel.licences if rel.commercial(x)}
        else:
            lic_ids = set()
            for sid in station_ids:
                lic_ids |= rel.tide_source_licences(rel.by_id[sid])
    elif not station_ids:   # None or an empty list: every licence in the release (CR D2 c)
        lic_ids = set(rel.licences)
    else:
        lic_ids = set()
        for sid in station_ids:
            s = rel.by_id[sid]
            rs = rel.rec_set(s)
            if rs:
                lic_ids.add(rs["licence_id"])
            # CR2 DR1: walk the reference chain (at most 16 links, the kind rule of §6.2): every offsets licence on
            # the path, and the licence of the first recommended set reached, where the walk stops
            cur, seen, links = s, {s["station_id"]}, 0
            while cur["type"] == "subordinate" and cur.get("subordinate_offsets"):
                off = cur["subordinate_offsets"]
                if off.get("licence_id"):
                    lic_ids.add(off["licence_id"])
                if links == 16:
                    break
                ref = rel.by_id.get(off.get("reference_station_id"))
                if ref is None or ref["station_id"] in seen:
                    break
                links += 1
                seen.add(ref["station_id"])
                if rel.rec_set(ref):
                    lic_ids.add(rel.rec_set(ref)["licence_id"])
                    break
                cur = ref
    parts, seen = [], set()
    for lid in sorted(lic_ids):
        lic = rel.licences[lid]
        if lic.get("provider") is None:   # the attribution alone, never merged (CR D2 b)
            parts.append(lic["attribution"])
            continue
        if lic["provider"] in seen:
            continue
        seen.add(lic["provider"])
        parts.append(f"{lic['provider']}: {lic['attribution']}")
    ident = f"doi:{r['concept_doi']}" if r.get("concept_doi") else f"https://data.opentideconstants.org/OTC_{r['datestamp']}.json"
    head = f"Tidal constants: OpenTideConstants {r['datestamp']}, {ident}, CC BY 4.0."
    if not lic_ids:   # an empty scope: the dataset header alone (K-NC DR106, spec 4.6)
        return head
    text = head + " Sources: " + "; ".join(parts)
    # K-NC DR105: one notice after the Sources list, one entry per non-commercial licence in scope, by licence_id
    nc = [rel.licences[x] for x in sorted(lic_ids) if not rel.commercial(x)]
    if nc:
        text += ". Non-commercial use only: " + "; ".join(
            f"{x['licence_id'] if x.get('provider') is None else x['provider']} ({x['spdx']}, {x['terms_url']})" for x in nc)
    return text


def citation(rel, version_doi=None):
    """The dataset citation (§4.6): the year is the first four digits of the datestamp; the link is the concept DOI
    (or the release URL when it is null); the version DOI is added only when the release has one."""
    r = rel.doc["release"]
    d = r["datestamp"]
    link = f"https://doi.org/{r['concept_doi']}" if r.get("concept_doi") else f"https://data.opentideconstants.org/OTC_{d}.json"
    version = f" (version DOI: https://doi.org/{version_doi})" if version_doi else ""
    return f"OpenTideConstants contributors ({d[:4]}). OpenTideConstants, release {d} [Data set]. {link}{version}"


def stats(rel):
    def count(values):
        out = {}
        for v in values:
            if v is not None:
                out[v] = out.get(v, 0) + 1
        return dict(sorted(out.items()))
    sets = [cs for s in rel.active for cs in s.get("constant_sets", [])]
    return {"type": count(typed(s["type"], STATION_TYPES) for s in rel.active), "kind": count(rel.kind(s) for s in rel.active),
            "country": count(s["country"] for s in rel.active),
            "source": count(cs["source"] for cs in sets if cs["qc_status"] in WITH_CONSTANTS),
            "qc_status": count(read_qc(cs) for cs in sets)}


def sets_in_order(s, include_no_constants=False, rel=None):
    """The recommended set first (with rel: the set the SDK gives as recommended, the effective one under
    commercial_only), then the others by set_id."""
    if rel is None:
        rid = s.get("recommended_set_id")
    else:
        rid = rel.eff_set(s)["set_id"] if rel.eff_set(s) is not None else None
    sets = [cs for cs in s.get("constant_sets", []) if include_no_constants or cs["qc_status"] not in NOT_USABLE]
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


def fallback_case(group, rel):
    """Supplementary Python typed/raw annotation checks; other SDK ports follow after the data freeze."""
    station = copy.deepcopy(rel.by_id["OTC-T-0001"])
    cs = station["constant_sets"][0]
    label = {"reason": "licence_reading", "basis": "Published source constants",
             "otc_finding": "Retained source caveat", "preferred_set_id": station["constant_sets"][1]["set_id"]}
    cs["fallback"] = label
    cs["qc_status"] = "flagged"
    cs["qc_flags"] = [{"flag": "fallback:licence_reading", "reason": label["otc_finding"]}]
    station["recommended_is_fallback"] = True
    path = "${tmp}/labelled/OTC_20991231.2.json"
    steps = [drv("copy", files=[f"{FIX}/good/OTC_20991231.2.json"], to="${tmp}/labelled"),
             drv("json_set", path=path, pointer="/stations/0/constant_sets/0/fallback", value=label),
             drv("json_set", path=path, pointer="/stations/0/constant_sets/0/qc_status", value="flagged"),
             drv("json_set", path=path, pointer="/stations/0/constant_sets/0/qc_flags", value=cs["qc_flags"]),
             drv("json_set", path=path, pointer="/stations/0/recommended_is_fallback", value=True),
             step("open", {"loaded_from": "file_unverified", "datestamp": "20991231.2", "format_version": "1.0"},
                  file=path, mode="eager")]
    sid = station["station_id"]
    if group == "sets":
        value = enc_set(rel, station, cs)
        value["fallback"] = label
        steps += [step("constant_set", {"set": value}, station_id=sid, set_id=cs["set_id"]),
                  step("raw", {"raw": cs}, object="set", station_id=sid, set_id=cs["set_id"])]
    else:
        value = enc_station(rel, station)
        value["recommended_is_fallback"] = True
        steps += [step("station", {"station": value}, station_id=sid),
                  step("raw", {"raw": station}, object="station", station_id=sid)]
    return case(f"{group}/fallback-python", f"Python typed and raw retained fallback {group}",
                "4.4, 4.5, 7.3; FB0", steps, runners=["python"], requires=["fs", "json", "eager"])


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
        out.append(mcase(f"release/attribution-all-{d}", f"attribution with no stations, {d} (concept DOI {'set' if rel.doc['release'].get('concept_doi') else 'null'})", "4.6",
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
    out.append(mcase("release/citation", "citation contains the concept DOI and the datestamp, and no version DOI (a file has none)", "4.6",
                     [step("citation", {"citation": {"$all": [{"$contains": "10.5072/zenodo.1"}, {"$contains": "20991231.2"}]}})]))
    for cr in (R2, R1):
        out.append(mcase(f"release/citation-exact-{cr.datestamp}", f"citation of {cr.datestamp}, exact text (concept DOI {'set' if cr.doc['release'].get('concept_doi') else 'null'}, no version DOI)", "4.6",
                         [step("citation", {"citation": citation(cr)})], release=cr.datestamp))
    # The version DOI (spec 4.3, 4.6) is only in the pointer and index entries, so the SDK has it after a download
    # of latest (and keeps it in .verified); the concept DOI is in the release document.
    G = f"{SRV}/good/"
    vdoi = pointer_entry("good", R2.datestamp)["zenodo_version_doi"]
    open_g = net(step("open", {"loaded_from": "download", "datestamp": R2.datestamp}, base_url=G, cache_dir="${cache}"))
    out.append(case("release/citation-exact-version-doi", "citation after a download of latest whose pointer has a version DOI: concept DOI link plus (version DOI: ...)", "4.6",
                    [open_g, step("citation", {"citation": citation(R2, vdoi)})], requires=["fs"]))
    out.append(case("release/doi-fields-latest", "concept_doi from the release, zenodo_version_doi from the pointer and kept in the cache; the attribution uses only the concept DOI; ReleaseInfo carries both and content_sha256", "3, 4.3, 4.6",
                    [open_g,
                     step("release_metadata", enc_release_meta(R2, vdoi)),
                     step("attribution", {"attribution": attribution(R2)}),
                     net(step("latest", {"release": enc_release_info("good", R2.datestamp, G)})),
                     drv("restart_runner"), drv("server_stop"),
                     net(step("open", {"loaded_from": "cache", "datestamp": R2.datestamp}, release=R2.datestamp, base_url=G, cache_dir="${cache}")),
                     step("release_metadata", {"zenodo_version_doi": vdoi, "concept_doi": R2.doc["release"]["concept_doi"]}),
                     step("citation", {"citation": citation(R2, vdoi)})],
                    requires=["fs"]))
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
                 step("constant_sets", {"set_ids": [c["set_id"] for c in sets_in_order(s, True)]}, station_id=sid, include_no_constants=True),
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
    out.append(mcase("stations/removed-error-tombstone", "station_removed carries the tombstone (Ruby, Python, TypeScript; C has no error object, so the case needs eager)", "4.4, 4.8",
                     [step("require_station", err("station_removed", tombstone=enc_tombstone(rel.tomb_by_id["OTC-T-0005"])), station_id="OTC-T-0005")],
                     requires=["eager"]))
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
    A = Rel("aliases", "20991231.2")
    sa = A.by_id["OTC-T-0171"]
    out.append(mcase("stations/alias-linz", "station_by_alias in two systems that format 1.0 added: linz and dmi (DR29: 16 alias systems)", "4.4",
                     [step("station_by_alias", {"station_id": "OTC-T-0171"}, system="linz", alias_id=sa["aliases"]["linz"]),
                      step("station_by_alias", {"station_id": "OTC-T-0171"}, system="dmi", alias_id=sa["aliases"]["dmi"]),
                      step("station_by_alias", {"station_id": None}, system="linz", alias_id="999NOWHERE"),
                      step("station", {"station": enc_station(A, sa)}, station_id="OTC-T-0171")],
                     root="aliases", release="20991231.2"))
    # listing and filters
    filter_sets = [{}, {"country": "GBR"}, {"country": "NOR"}, {"type": "subordinate"}, {"type": "reference", "country": "USA"},
                   {"kind": "current"}, {"kind": "tide", "country": "USA"}, {"source": "gesla-fit"}, {"source": "noaa"},
                   {"source_type": "model"}, {"source_type": "official"}, {"country": "ZZZ"}, {"kind": "no-such-kind"},
                   {"source": "ticon-fallback"}, {"source_type": "gauge", "country": "USA"}]
    for f in filter_sets:
        ids = [s["station_id"] for s in discovery_filters(rel, rel.active, f)]
        label = "-".join(f"{k}-{v}" for k, v in f.items()) or "all"
        out.append(mcase(f"stations/list-{label}", f"stations and iter_stations with filters {json.dumps(f)}", "4.4",
                         [step("stations", {"station_ids": ids}, **f), step("iter_stations", {"station_ids": ids}, **f)]))
    out.append(mcase("stations/filter-wrong-type", "a filter argument of the wrong type is invalid_argument", "4.4, 4.8",
                     [step("stations", err("invalid_argument"), country=5),
                      step("stations", err("invalid_argument"), type=["reference"])]))
    return out + [fallback_case("stations", rel), discovery_case("stations", rel)]


def group_sets(R2):
    out = []
    rel = R2
    for s in rel.active:
        for cs in s.get("constant_sets", []):
            sid, setid = s["station_id"], cs["set_id"]
            steps = [step("constant_set", {"set": enc_set(rel, s, cs)}, station_id=sid, set_id=setid),
                     step("constituents", {"constituents": [pick(c, CONSTITUENT_FIELDS) for c in cs.get("constituents", [])]}, station_id=sid, set_id=setid),
                     step("provenance", {"provenance": enc_provenance(cs.get("provenance") or {}), "raw": cs.get("provenance") or {}}, station_id=sid, set_id=setid),
                     step("set_validation", {"validation": [enc_validation(v) for v in sorted(
                         [v for v in s.get("validation") or [] if v["set_id"] == setid], key=lambda v: v["window"])]}, station_id=sid, set_id=setid)]
            if cs["constituents"] and (sid == "OTC-T-0001" or cs["qc_status"] != "ok" or sid in ("OTC-T-0006", "OTC-T-0020")):
                first = cs["constituents"][0]
                steps += [step("constituent", {"constituent": pick(first, CONSTITUENT_FIELDS)}, station_id=sid, set_id=setid, name=first["name"]),
                          step("constituent", {"constituent": None}, station_id=sid, set_id=setid, name=first["name"].lower()),
                          step("constituent", {"constituent": None}, station_id=sid, set_id=setid, name="M4")]
            out.append(mcase(f"sets/{setid}", f"constant set {setid}: fields, constituents, provenance, validation", "4.5, 4.6", steps))
    out.append(mcase("sets/unknown", "constant_set() is null for an unknown set id", "4.5",
                     [step("constant_set", {"set": None}, station_id="OTC-T-0001", set_id="OTC-T-0001/no-such-set")]))
    return out + [fallback_case("sets", rel)]


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
        ids = search(rel, q, **kw, query_filters=discovery_filters)
        label = re.sub(r"[^a-z0-9]+", "-", fold(q)).strip("-") or "blank"
        extra = "-".join(f"{k}-{v}" for k, v in kw.items())
        cid = f"search/{i:02d}-{label}" + (f"-{extra}" if extra else "")
        out.append(mcase(cid, f"search name={q!r} {json.dumps(kw) if kw else ''}".strip(), "4.4.1",
                         [step("search", {"station_ids": ids}, name=q, **kw)]))
    out.append(mcase("search/empty-query", "an empty query (also after trimming) is invalid_argument", "4.4.1",
                     [step("search", err("invalid_argument"), name=""), step("search", err("invalid_argument"), name="   ")]))
    return out + [discovery_case("search", rel)]


def group_geo(R2):
    rel = R2
    out = []
    spec_example = near(rel, 0.0, 179.95, 50, query_filters=discovery_filters)
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
                         [step("near", {**near(rel, **kw, query_filters=discovery_filters), "tolerance": TOL}, **kw)]))
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
                         [step("nearest", {**nearest(rel, **kw, query_filters=discovery_filters), "tolerance": TOL}, **kw)]))
    out.append(mcase("geo/invalid-arguments", "lat or lon out of range and a negative radius are invalid_argument", "4.4, 4.8",
                     [step("near", err("invalid_argument"), lat=91.0, lon=0.0, radius_km=10),
                      step("near", err("invalid_argument"), lat=0.0, lon=-180.5, radius_km=10),
                      step("near", err("invalid_argument"), lat=0.0, lon=0.0, radius_km=-1),
                      step("nearest", err("invalid_argument"), lat=-90.5, lon=0.0),
                      step("nearest", err("invalid_argument"), lat=0.0, lon=181.0)]))
    return out + [discovery_case("geo", rel)]


def group_tolerant():
    rel = Rel("bad/format-minor", "20991231")
    s = rel.by_id["OTC-T-0001"]
    cs = s["constant_sets"][0]
    con = rel.conventions[rel.doc["conventions"][0]["convention_id"]]
    lic = rel.doc["licences"][0]
    steps = [step("release_metadata", {"format_version": "1.1", "datestamp": "20991231"}),
             step("station", {"station": enc_station(rel, s)}, station_id="OTC-T-0001"),
             step("raw", {"raw": s}, object="station", station_id="OTC-T-0001"),
             step("raw", {"raw": cs}, object="set", station_id="OTC-T-0001", set_id=cs["set_id"]),
             step("raw", {"raw": cs["constituents"][0]}, object="constituent", station_id="OTC-T-0001", set_id=cs["set_id"], name=cs["constituents"][0]["name"]),
             step("raw", {"raw": con}, object="convention", convention_id=con["convention_id"]),
             step("raw", {"raw": lic}, object="licence", licence_id=lic["licence_id"]),
             step("station_by_alias", {"station_id": "OTC-T-0001"}, system="future_system", alias_id="FS-0001"),
             step("constant_set", {"set": enc_set(rel, s, cs)}, station_id="OTC-T-0001", set_id=cs["set_id"])]
    out = [mcase("tolerant/format-minor", "a higher format minor loads; unknown fields stay in raw; an unknown alias system works", "7.3",
                 steps, root="bad/format-minor", release="20991231", open_expect={"format_version": "1.1"})]
    eq = rel.by_id["OTC-T-0010"]
    legacy = next(c for c in eq["constant_sets"] if c["qc_status"] not in QC_STATUS)
    out.append(mcase("tolerant/unknown-qc-status", "a qc_status 1.0 does not have (excluded, a 0.x leftover) is \"other\": listed by default, counted under other, and not counted as a source", "4.3, 4.5, 7.3",
                     [step("constant_set", {"set": enc_set(rel, eq, legacy)}, station_id="OTC-T-0010", set_id=legacy["set_id"]),
                      step("constant_sets", {"set_ids": [c["set_id"] for c in sets_in_order(eq)]}, station_id="OTC-T-0010"),
                      step("stats", {"stats": stats(rel)}),
                      # the source filter counts the same sets as stats.source: not the "other" set of legacy-fit
                      step("stations", {"station_ids": [x["station_id"] for x in apply_filters(rel, rel.active, {"source": "legacy-fit"})]}, source="legacy-fit")],
                     root="bad/format-minor", release="20991231", open_expect={"format_version": "1.1"}))
    nb = Rel("bad/no-build", "20991231")
    nbs = nb.by_id["OTC-T-0004"]
    out.append(mcase("tolerant/missing-provenance-build", "a set with no provenance.build (malformed 1.0): the release loads and provenance.build is null", "4.6, 7.3",
                     [step("provenance", {"provenance": enc_provenance(nbs["constant_sets"][0]["provenance"]), "raw": nbs["constant_sets"][0]["provenance"]},
                           station_id="OTC-T-0004", set_id=nbs["constant_sets"][0]["set_id"]),
                      step("station_count", {"station_count": len(nb.active)})],
                     root="bad/no-build", release="20991231"))
    good = Rel("good", "20991231.2")
    gs = good.by_id["OTC-T-0020"]
    out.append(mcase("tolerant/raw-good", "raw is the object as the file gives it", "3",
                     [step("raw", {"raw": gs}, object="station", station_id="OTC-T-0020"),
                      step("raw", {"raw": good.tomb_by_id["OTC-T-0005"]}, object="tombstone", station_id="OTC-T-0005")]))
    return out


# --------------------------------------------------------------------------- format 1.0 annotations and versions

V1 = "20991231.3"
R_OLD, R_OK, R_NEW = "20991231.2", "20991231.3", "20991231.4"   # fixtures/reader: R_NEW has min_reader_version 1.99
M_OK, M_NEW = "20991231.2", "20991231.3"                        # fixtures/major: M_NEW has format 2.0
TOO_NEW = "1.99"
# reader_too_old names both versions (spec 4.8): the release's min_reader_version and the SDK's own
# SUPPORTED_FORMAT_VERSION, so the case asks for 1.99 and one other 1.x version.
TOO_OLD_MESSAGE = {"$all": [{"$contains": TOO_NEW}, {"$regex": r"(^|[^0-9.])1\.(?!99([^0-9]|$))[0-9]+([^0-9]|$)"}]}


def set_steps(rel, s, cs):
    """Every runner step that reads one constant set."""
    sid, setid = s["station_id"], cs["set_id"]
    prov = cs.get("provenance") or {}
    return [step("constant_set", {"set": enc_set(rel, s, cs)}, station_id=sid, set_id=setid),
            step("constituents", {"constituents": [pick(c, CONSTITUENT_FIELDS) for c in cs.get("constituents", [])]}, station_id=sid, set_id=setid),
            step("provenance", {"provenance": enc_provenance(prov), "raw": prov}, station_id=sid, set_id=setid)]


def station_steps(rel, s):
    sid = s["station_id"]
    rs = rel.rec_set(s)
    return [step("station", {"station": enc_station(rel, s)}, station_id=sid),
            step("recommended_set", {"set_id": rs["set_id"] if rs else None}, station_id=sid),
            step("constant_sets", {"set_ids": [c["set_id"] for c in sets_in_order(s)]}, station_id=sid),
            step("constant_sets", {"set_ids": [c["set_id"] for c in sets_in_order(s, True)]}, station_id=sid, include_no_constants=True)]


def group_v1():
    """The format 1.0 annotations (fixtures/v1): qc_status ok, flagged and no_constants, a station with only
    no_constants sets, a carried-over set, the time_base codes, provenance.build (spec 4.3, 4.5, 4.6, 7.4)."""
    rel = Rel("v1", V1)
    out = []
    for s in rel.active:
        out.append(mcase(f"v1/stations/{s['station_id']}", f"station {s['station_id']} ({s['name']}): fields, recommended set, constant_sets with and without include_no_constants", "4.5, 7.4",
                         station_steps(rel, s), root="v1", release=V1))
        for cs in s["constant_sets"]:
            out.append(mcase(f"v1/sets/{cs['set_id']}", f"set {cs['set_id']} (qc_status {cs['qc_status']}): fields, time_base, provenance with build and carried_from_release", "4.5, 4.6, 7.4",
                             set_steps(rel, s, cs), root="v1", release=V1))
    for f in [{"source": "gesla-fit"}, {"source": "noaa"}, {"kind": "tide"}, {"source_type": "gauge"}, {}]:
        ids = [s["station_id"] for s in apply_filters(rel, rel.active, f)]
        label = "-".join(f"{k}-{v}" for k, v in f.items()) or "all"
        out.append(mcase(f"v1/list-{label}", f"stations with filters {json.dumps(f)}: a source counts only through a set with constants", "4.4, 7.4",
                         [step("stations", {"station_ids": ids}, **f), step("iter_stations", {"station_ids": ids}, **f)], root="v1", release=V1))
    out.append(mcase("v1/stats", "stats: qc_status counts every set (no_constants under its own key); source counts only ok and flagged sets", "4.3",
                     [step("stats", {"stats": stats(rel)}), step("station_count", {"station_count": len(rel.active)}),
                      step("tombstone_count", {"tombstone_count": len(rel.tombs)})], root="v1", release=V1))
    out.append(mcase("v1/tombstone-merged", "a tombstone with removed_reason merged; require_station on it", "4.4",
                     [step("tombstone", {"tombstone": enc_tombstone(rel.tomb_by_id["OTC-T-0108"])}, station_id="OTC-T-0108"),
                      step("station", {"station": None}, station_id="OTC-T-0108"),
                      step("require_station", err("station_removed"), station_id="OTC-T-0108")], root="v1", release=V1))
    ids = ["OTC-T-0104", "OTC-T-0105", "OTC-T-0101"]
    out.append(mcase("v1/attribution", "attribution: a station with no recommended set adds no licence", "4.6",
                     [step("attribution", {"attribution": attribution(rel)}),
                      step("attribution", {"attribution": attribution(rel, ids)}, station_ids=ids)], root="v1", release=V1))
    return out


def group_format():
    """release.min_reader_version (spec 4.8 reader_too_old, 5.2 steps 1 and 2a, 7.1 format/reader-too-old, 7.4)."""
    out = []
    RD = f"{SRV}/reader/"
    V1R = f"{SRV}/v1/"
    MJ = f"{SRV}/major/"
    RF = f"{FIX}/reader"
    ok_info = enc_release_info("reader", R_OK, RD)
    too_old = err("reader_too_old")
    too_old["error_message"] = TOO_OLD_MESSAGE
    index_once = drv("assert_requests", match=r"/reader/OTC_index\.json$", count=1)
    no_new = drv("assert_requests", match=r"OTC_20991231\.4\.", count=0)
    R_ok = Rel("reader", R_OK)

    def latest(expect, base=RD, **kw):
        return net(step("open", expect, base_url=base, cache_dir="${cache}", **kw))

    out.append(case("format/reader-too-old", "min_reader_version newer than the SDK: a file and a pinned load fail with reader_too_old naming both versions; latest loads the newest readable release", "4.8, 5.2, 7.1, 7.4",
                    [step("open", too_old, file=f"{RF}/OTC_{R_NEW}.jsonl"),
                     net(step("open", too_old, release=R_NEW, base_url=RD, cache_dir="${cache}")),
                     drv("clear_log"),
                     latest({"loaded_from": "download", "datestamp": R_OK, "format_version": "1.0"}),
                     index_once],
                    requires=["fs"]))
    for ext, req, mode in [(".json", ["json", "eager"], "eager"), (".json.gz", ["json", "eager"], "eager"),
                           (".jsonl", ["eager"], "eager"), (".jsonl", ["stream"], "stream")]:
        label = ext.replace(".", "-") + ("-stream" if mode == "stream" else "")
        out.append(case(f"format/reader-too-old-file{label}", f"a {ext} file whose min_reader_version is {TOO_NEW} ({mode}): reader_too_old", "4.8, 7.4",
                        [step("open", too_old, file=f"{RF}/OTC_{R_NEW}{ext}", mode=mode)], requires=["fs"] + req))
    out.append(case("format/reader-too-old-bad-root", "bad/min-reader: a file, a pinned release and latest all fail with reader_too_old (no readable release)", "4.8, 5.2, 7.4",
                    [step("open", too_old, file=f"{FIX}/bad/min-reader/OTC_20991231.jsonl"),
                     net(step("open", err("reader_too_old"), release="20991231", base_url=f"{SRV}/bad/min-reader/", cache_dir="${cache}")),
                     drv("clear_log"),
                     net(step("open", err("reader_too_old"), base_url=f"{SRV}/bad/min-reader/", cache_dir="${cache}")),
                     drv("assert_requests", match=r"/bad/min-reader/OTC_index\.json$", count=1)],
                    requires=["fs"]))
    out.append(case("format/latest-skips-too-new", "latest: the pointer names a release too new for the SDK, so one GET of OTC_index.json picks the newest readable one; its files and version DOI come from that entry", "5.2, 4.3.1, 7.4",
                    [latest({"loaded_from": "download", "datestamp": R_OK}),
                     index_once, no_new,
                     drv("assert_requests", match=r"/reader/OTC_latest-f1\.json$", min=1),
                     step("release_files", {"files": ok_info["files"]}),
                     step("release_metadata", {"datestamp": R_OK, "format_version": "1.0", "zenodo_version_doi": "10.5072/zenodo.3"}),
                     step("station_count", {"station_count": len(R_ok.active)})],
                    requires=["fs"]))
    out.append(case("format/latest-readable-no-index", "latest when the pointer's release is readable: no GET of OTC_index.json (the extra GET is only for a release too new)", "5.2, 7.4",
                    [latest({"loaded_from": "download", "datestamp": V1, "format_version": "1.0"}, base=V1R),
                     drv("assert_requests", match=r"OTC_index\.json$", count=0)],
                    requires=["fs"]))
    out.append(case("format/latest-newer-major", "OTC_latest.json names a format 2.0 release: latest follows OTC_latest-f1.json to the newest 1.x release", "7.4",
                    [latest({"loaded_from": "download", "datestamp": M_OK, "format_version": "1.0"}, base=MJ),
                     drv("assert_requests", match=r"/major/OTC_latest-f1\.json$", min=1),
                     drv("assert_requests", match=r"OTC_20991231\.3\.", count=0)],
                    requires=["fs"]))
    out.append(case("format/check-for-update-newer-major", "check_for_update with a newer major on the server: no update in major 1, newer_format_major 2 (case check-for-update-newer-major)", "7.4",
                    [latest({"loaded_from": "download", "datestamp": M_OK}, base=MJ),
                     drv("clear_log"),
                     net(step("check_for_update", {"release": None})),
                     drv("assert_requests", match=r"/major/OTC_latest\.json$", min=1),
                     net(step("newer_format_major", {"newer_format_major": 2})),
                     drv("assert_requests", match=r"OTC_20991231\.3\.", count=0)],
                    requires=["fs"]))
    out.append(case("format/check-for-update-newer-major-with-update", "check_for_update on an older 1.0 release: it returns the newest 1.x release and also sets newer_format_major 2", "7.4",
                    [net(step("open", {"loaded_from": "download", "datestamp": "20991231"}, release="20991231", base_url=MJ, cache_dir="${cache}")),
                     net(step("check_for_update", {"release": enc_release_info("major", M_OK, MJ)})),
                     net(step("newer_format_major", {"newer_format_major": 2}))],
                    requires=["fs"]))
    out.append(case("format/check-for-update-no-newer-major", "check_for_update when every release has a supported major: newer_format_major null", "7.4",
                    [latest({"loaded_from": "download", "datestamp": R_OK}),
                     net(step("check_for_update", {"release": None})),
                     net(step("newer_format_major", {"newer_format_major": None}))],
                    requires=["fs"]))
    new_dir = f"${{cache}}/v1/releases/{R_NEW}"
    new_entry = pointer_entry("reader", R_NEW)
    planted = [n for n in (f"OTC_{R_NEW}.json", f"OTC_{R_NEW}.jsonl", f"OTC_{R_NEW}.meta.json", f"OTC_{R_NEW}.sha256")]
    verified = {"files": {f["name"]: {"sha256": f["sha256"], "size": f["size"], "url": RD + f["url"]}
                          for f in new_entry["files"] if f["name"] in planted},
                "verified_at": "2099-12-31T20:00:00Z", "by": "opentideconstants-conformance/1.0"}
    out.append(case("format/latest-offline-cached-index", "offline latest when the cache holds a verified release too new for the SDK and the cached index says so: the newest cached readable release, no request", "5.2, 5.5, 7.4",
                    [net(step("open", {"loaded_from": "download", "datestamp": R_OK}, release=R_OK, base_url=RD, cache_dir="${cache}")),
                     net(step("releases", {"releases": {"$len_min": 3}})),
                     drv("copy", files=[f"{RF}/{n}" for n in planted], to=new_dir),
                     drv("write", path=f"{new_dir}/.verified", text=json.dumps(verified, sort_keys=True)),
                     drv("restart_runner"), drv("server_stop"), drv("clear_log"),
                     latest({"loaded_from": "cache", "datestamp": R_OK}, offline=True),
                     drv("assert_requests", source="any", count=0)],
                    requires=["fs"]))
    out.append(case("format/latest-use-cache-after-error", "the pointer fails and the cache holds only a readable release: loaded_from cache_after_error on it", "5.2, 7.4",
                    [latest({"loaded_from": "download", "datestamp": R_OK}), drv("restart_runner"),
                     drv("server_rules", rules=[{"match": r"/reader/OTC_latest(-f1)?\.json$", "action": "status", "status": 500}]),
                     latest({"loaded_from": "cache_after_error", "datestamp": R_OK}),
                     step("last_error", {"code": "network"})],
                    requires=["fs"], timeout_s=90))
    out.append(case("format/latest-index-error", "the pointer's release is too new and OTC_index.json answers 500, with an empty cache: network error", "5.2, 7.4",
                    [drv("server_rules", rules=[{"match": r"/reader/OTC_index\.json$", "action": "status", "status": 500}]),
                     latest(err("network")), no_new],
                    requires=["fs"], timeout_s=90))
    old_pointer = [{"match": r"/reader/OTC_latest(-f1)?\.json$", "action": "json", "file": "reader/OTC_index.json", "pointer": "/releases/2"}]
    out.append(case("format/check-for-update-skips-too-new", "check_for_update and update skip a release too new for the SDK and move to the newest readable one", "4.3, 5.2, 7.4",
                    [drv("server_rules", rules=old_pointer),
                     latest({"loaded_from": "download", "datestamp": R_OLD}),
                     drv("assert_requests", match=r"OTC_index\.json$", count=0),
                     drv("server_rules", rules=[]), drv("clear_log"),
                     net(step("check_for_update", {"release": ok_info})),
                     index_once, drv("clear_log"),
                     net(step("update", {"updated": True, "from": R_OLD, "to": R_OK})),
                     index_once,
                     step("release_metadata", {"datestamp": R_OK}),
                     no_new,
                     net(step("check_for_update", {"release": None})),
                     net(step("update", {"updated": False, "from": R_OK, "to": R_OK}))],
                    requires=["fs"]))
    B = "${tmp}/bundle"
    names = [f"OTC_{R_OK}.jsonl", f"OTC_{R_OK}.meta.json", f"OTC_{R_OK}.sha256"]
    out.append(case("format/download-latest-skips-too-new", "download with no release resolves latest the same way: the newest readable release", "4.3.2, 5.2, 7.4",
                    [net(step("open", {"loaded_from": "download", "datestamp": R_OLD}, release=R_OLD, base_url=RD)),
                     net(step("download", {"paths": names}, to=B), fs=True),
                     drv("assert_files", dir=B, exactly=names), no_new,
                     index_once],
                    requires=[]))
    d2 = "20991231.2"
    out.append(case("format/check-for-update-keeps-newer-major-on-error", "the per-major pointer names the loaded release and OTC_latest.json names format 2: check_for_update finds nothing newer and sets newer_format_major to 2; a later check whose OTC_latest.json answers 500 keeps 2, it does not reset it (D10)", "7.4",
                    [step("open", {"loaded_from": "file", "datestamp": d2}, file=f"{FIX}/good/OTC_{d2}.jsonl",
                          base_url=f"{SRV}/good/", cache_dir="${cache}"),
                     drv("server_rules", rules=[{"match": r"^/good/OTC_latest\.json$", "action": "file", "file": "bad/format-major/OTC_latest.json"}]),
                     net(step("check_for_update", {"release": None})),
                     net(step("newer_format_major", {"newer_format_major": 2})),
                     drv("server_rules", rules=[{"match": r"^/good/OTC_latest\.json$", "action": "status", "status": 500}]),
                     drv("clear_log"),
                     net(step("check_for_update", {"release": None})),
                     drv("assert_requests", source="server", match=r"^/good/OTC_latest\.json$", status=500, min=1),
                     net(step("newer_format_major", {"newer_format_major": 2}))],
                    requires=["fs"], timeout_s=90))
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
                    [step("open", err("io", path={"$contains": "OTC_20991231.9.jsonl"}), file="${tmp}/OTC_20991231.9.jsonl")], requires=["fs"]))
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
    out.append(case("load/format-minor-loads", "bad/format-minor (format 1.1) loads from a file", "7.3",
                    [step("open", {"loaded_from": "file", "datestamp": "20991231", "format_version": "1.1"}, file=f"{FIX}/bad/format-minor/OTC_20991231.jsonl"),
                     step("station_count", {"station_count": len(Rel("bad/format-minor", "20991231").active)})], requires=["fs"]))
    out.append(case("load/verify-file", "verify passes on an intact file and fails with checksum_mismatch after one byte changes", "4.3, 5.3",
                    [drv("copy", files=[f"{G}/OTC_{d}.jsonl", f"{G}/OTC_{d}.meta.json", f"{G}/OTC_{d}.sha256"], to="${tmp}/rel"),
                     step("open", {"loaded_from": "file"}, file=f"${{tmp}}/rel/OTC_{d}.jsonl"),
                     step("verify", {"verified": True}),
                     drv("corrupt", path=f"${{tmp}}/rel/OTC_{d}.jsonl", offset=100),
                     step("verify", err("checksum_mismatch", file={"$contains": f"OTC_{d}.jsonl"}, expected=sha256_rows("good", d)[f"OTC_{d}.jsonl"], actual={"$regex": "^[0-9a-f]{64}$"}))],
                    requires=["fs"]))
    out += local_row_cases()
    for bad in ["2099123", "20991231.1", "20991231.0", "20991231.01", "20991231.", "209912310", "latest2", "2099-12-31"]:
        out.append(case(f"load/invalid-datestamp-{bad}", f"release={bad!r} does not match the datestamp pattern: invalid_argument", "4.2",
                        [net(step("open", err("invalid_argument"), release=bad, base_url=f"{SRV}/good/", cache_dir="${cache}"))],
                        requires=["fs"]))
    # CR2 DR41 (spec 5.3): a line of a .sha256 file that is neither a row ("<64 hex digits>", spaces or tabs, an
    # optional "*", the name) nor blank (only white space) is invalid_release in every SDK, never skipped. The bad line
    # names a file that no other row names, so the error is not the repeated name of DR14
    rows = sha256_rows("good", d)
    good_rows = "".join(f"{h}  {n}\n" for n, h in sorted(rows.items()))
    some = rows[f"OTC_{d}.json"]
    rel_files = [f"{G}/OTC_{d}.jsonl", f"{G}/OTC_{d}.meta.json"]
    for kind, title, line in [("junk", "a line that is not a row", "this is not a row\n"),
                              ("no-name", "a digest with no name", f"{some}\n"),
                              ("short-digest", "a digest of 63 hex digits", f"{some[:63]}  OTC_{d}.extra\n"),
                              ("long-digest", "a digest of 65 hex digits", f"{some}0  OTC_{d}.extra\n"),
                              ("no-separator", "no space between the digest and the name", f"{some}OTC_{d}.extra\n"),
                              ("bad-hex", "a digest with a letter that is not hex", f"{some[:63]}g  OTC_{d}.extra\n")]:
        out.append(case(f"load/sha256-malformed-{kind}", f"the .sha256 next to the file has {title} after its good rows: invalid_release (CR2 DR41)", "5.3, 4.8",
                        [drv("copy", files=rel_files, to="${tmp}/rel"),
                         drv("write", path=f"${{tmp}}/rel/OTC_{d}.sha256", text=good_rows + line),
                         step("open", err("invalid_release"), file=f"${{tmp}}/rel/OTC_{d}.jsonl")], requires=["fs"]))
    crlf = "".join(f"{h} \t*{n}\r\n" for n, h in sorted(rows.items()))
    out.append(case("load/sha256-blank-lines-crlf", "a .sha256 with CRLF line ends, a tab and \"*\" before the name, and blank lines of white space: the rows are read, and the file loads checked (CR2 DR41)", "5.3",
                    [drv("copy", files=rel_files, to="${tmp}/rel"),
                     drv("write", path=f"${{tmp}}/rel/OTC_{d}.sha256", text="\n \t\r\n" + crlf + "\f\v\n\n"),
                     step("open", {"loaded_from": "file", "datestamp": d}, file=f"${{tmp}}/rel/OTC_{d}.jsonl"),
                     step("verify", {"verified": True})], requires=["fs"]))
    # CR2 DR34 (spec 5.3, 4.8): C otc_open_file with require_checksum and no OTC_{D}.sha256 next to the file is
    # checksum_mismatch "no OTC_{D}.sha256 next to the file", the answer of verify (D20); with the .sha256 it loads
    jl_meta = [f"{G}/OTC_{d}.jsonl", f"{G}/OTC_{d}.meta.json"]
    out.append(case("load/require-checksum-missing", "C: require_checksum and no .sha256 next to the file: checksum_mismatch \"no OTC_{D}.sha256 next to the file\"; with the .sha256 the file loads, checked (CR2 DR34)", "5.3, 4.8",
                    [drv("copy", files=jl_meta, to="${tmp}/rel"),
                     step("open", {**err("checksum_mismatch"), "error_message": {"$contains": f"no OTC_{d}.sha256 next to the file"}},
                          file=f"${{tmp}}/rel/OTC_{d}.jsonl", require_checksum=True),
                     step("open", {"loaded_from": "file_unverified", "datestamp": d}, file=f"${{tmp}}/rel/OTC_{d}.jsonl"),
                     drv("copy", files=[f"{G}/OTC_{d}.sha256"], to="${tmp}/rel"),
                     step("open", {"loaded_from": "file", "datestamp": d}, file=f"${{tmp}}/rel/OTC_{d}.jsonl", require_checksum=True)],
                    requires=["fs", "require_checksum"]))
    out.append(case("load/valid-datestamp-not-found", "release 20991231.10 matches the pattern but does not exist: release_not_found", "4.2, 4.8",
                    [net(step("open", err("release_not_found"), release="20991231.10", base_url=f"{SRV}/good/", cache_dir="${cache}"))], requires=["fs"]))
    return out


def local_row_cases():
    """The .sha256 rows of a local open (spec 5.3). CR3 DR73 (orchestrator decision 2026-10-09): whenever an
    OTC_{D}.sha256 is next to the file, every release file the open reads needs a row; a missing row is
    checksum_mismatch "not listed", with file naming it, as for a network open (CR3 DR61). CR3 DR77 (orchestrator
    decision 2026-10-09): a local .json.gz needs the .json.gz row and the .json row, and its decompressed bytes are
    checked against the .json row, at open and in verify."""
    out = []
    G = f"{FIX}/good"
    d = "20991231.2"
    rows = sha256_rows("good", d)

    def sha(drop=(), **swap):
        r = {n: h for n, h in rows.items() if n not in drop}
        r.update({n: h for n, h in swap.items() if n in r})
        return "".join(f"{h}  {n}\n" for n, h in sorted(r.items()))

    def not_listed(name):
        # the name ends the path: OTC_{D}.json must not match OTC_{D}.json.gz
        return {**err("checksum_mismatch", file={"$regex": re.escape(name) + "$"}), "error_message": {"$contains": "not listed"}}

    J, GZ, JL, M = (f"OTC_{d}{e}" for e in (".json", ".json.gz", ".jsonl", ".meta.json"))
    # CR3 DR73: each release file that the open reads, missing from the .sha256 next to it
    for opened, copy, missing, req in [(J, [J], J, ["json"]), (GZ, [GZ], GZ, ["json"]),
                                       (JL, [JL, M], JL, []), (JL, [JL, M], M, [])]:
        kind = missing.replace(f"OTC_{d}", "").replace(".", "-")
        out.append(case(f"load/file-sha256-no-row{opened.replace(f'OTC_{d}', '').replace('.', '-')}{'' if missing == opened else kind}",
                        f"the .sha256 next to the {opened.replace(f'OTC_{d}', '')} file has no {missing} row: checksum_mismatch \"not listed\", file {missing} (CR3 DR73)", "5.3, 4.8",
                        [drv("copy", files=[f"{G}/{n}" for n in copy], to="${tmp}/rel"),
                         drv("write", path=f"${{tmp}}/rel/OTC_{d}.sha256", text=sha(drop=[missing])),
                         step("open", not_listed(missing), file=f"${{tmp}}/rel/{opened}")], requires=["fs"] + req))
    # CR3 DR77: the reviewer's fixture (the .json.gz row, no .json row) and a .json row that the decompressed bytes
    # do not match
    out.append(case("load/file-json-gz-no-json-row", "bad/sha256-no-json-row opened as .json.gz (.json.gz listed, .json not): checksum_mismatch \"not listed\", file OTC_{D}.json (CR3 DR77)", "5.3, 4.8",
                    [step("open", not_listed("OTC_20991231.json"), file=f"{FIX}/bad/sha256-no-json-row/OTC_20991231.json.gz")],
                    requires=["fs", "json"]))
    other = rows[JL]
    out.append(case("load/file-json-gz-json-row-mismatch", "a .json.gz whose own row matches but whose decompressed bytes do not match the .json row: checksum_mismatch, file OTC_{D}.json (CR3 DR77)", "5.3, 4.8",
                    [drv("copy", files=[f"{G}/{GZ}"], to="${tmp}/rel"),
                     drv("write", path=f"${{tmp}}/rel/OTC_{d}.sha256", text=sha(**{J: other})),
                     step("open", err("checksum_mismatch", file={"$regex": re.escape(J) + "$"}, expected=other, actual=rows[J]), file=f"${{tmp}}/rel/{GZ}")],
                    requires=["fs", "json"]))
    out.append(case("load/verify-file-json-gz", "verify on a local .json.gz checks the .json.gz and the decompressed bytes against the .json row: no .json row is \"not listed\", another .json row is checksum_mismatch (CR3 DR77)", "4.3, 5.3",
                    [drv("copy", files=[f"{G}/{GZ}", f"{G}/OTC_{d}.sha256"], to="${tmp}/rel"),
                     step("open", {"loaded_from": "file", "datestamp": d}, file=f"${{tmp}}/rel/{GZ}"),
                     step("verify", {"verified": True}),
                     drv("write", path=f"${{tmp}}/rel/OTC_{d}.sha256", text=sha(drop=[J])),
                     step("verify", not_listed(J)),
                     drv("write", path=f"${{tmp}}/rel/OTC_{d}.sha256", text=sha(**{J: other})),
                     step("verify", err("checksum_mismatch", file={"$regex": re.escape(J) + "$"}, expected=other, actual=rows[J]))],
                    requires=["fs", "json"]))
    # CR2 DR44 over CR3 DR73: a data file the client was loaded from that is gone is io in verify, never checksum
    # "not listed", also when the .sha256 has lost its row too (nothing can be hashed)
    for opened, copy, gone, req in [(JL, [JL, M], [JL], []), (GZ, [GZ], [GZ, J], ["json"])]:
        k = opened.replace(f"OTC_{d}", "").replace(".", "-")
        out.append(case(f"load/verify-file{k}-missing-file-no-row", f"verify on a local {opened.replace(f'OTC_{d}', '')} client after the file is deleted and its .sha256 row removed: io, never \"not listed\" (CR2 DR44, CR3 DR73)", "4.3, 5.3",
                        [drv("copy", files=[f"{G}/{n}" for n in copy] + [f"{G}/OTC_{d}.sha256"], to="${tmp}/rel"),
                         step("open", {"loaded_from": "file", "datestamp": d}, file=f"${{tmp}}/rel/{opened}"),
                         drv("delete", path=f"${{tmp}}/rel/{opened}"),
                         drv("write", path=f"${{tmp}}/rel/OTC_{d}.sha256", text=sha(drop=gone)),
                         step("verify", err("io"))], requires=["fs"] + req))
    return out


def cached_rows(info):
    """release.files of a cached open of a release that one download of latest stored (spec 4.3.1 cache row): the
    .verified rows, that is the pointer's values for only the files stored (CR3 DR100). The default mode is eager
    (the .json), C's is stream (the .jsonl and the .meta.json)."""
    d = info["datestamp"]
    by = {f["name"]: f for f in info["files"]}
    return {"$any_of": [[by[f"OTC_{d}.json"]], [by[f"OTC_{d}.jsonl"], by[f"OTC_{d}.meta.json"]]]}


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
        return net(step("open", expect if expect is not None else {"loaded_from": "download", "datestamp": d2, "format_version": "1.0"}, **args))

    out.append(case("net/latest-download", "open latest: pointer, .sha256, data file; loaded_from download; files from the pointer", "4.2, 4.3.1, 5.2",
                    [open_latest(),
                     drv("assert_requests", match=r"/good/OTC_latest-f1\.json$", min=1),
                     drv("assert_requests", match=r"/good/OTC_latest\.json$", count=0),
                     drv("assert_requests", match=r"/good/OTC_20991231\.2\.sha256$", count=1),
                     drv("assert_requests", has_query=True, count=0),
                     drv("assert_requests", header={"user-agent": UA}, min=1, all=True),
                     step("release_files", {"files": info2["files"]}),
                     step("station_count", {"station_count": 20}),
                     drv("assert_files", dir="${cache}/v1/releases/20991231.2", present=[".verified", "OTC_20991231.2.sha256"], absent=[".lock"], no_tmp=True),
                     drv("assert_files", dir="${cache}/v1/pointer", present=["OTC_latest-f1.json", "OTC_latest-f1.json.etag"], no_tmp=True)],
                    requires=["fs"]))
    out.append(case("net/pointer-500-no-fallback", "the per-major pointer answers 500 and the cache is empty: network error, and no fallback to OTC_latest.json (only a 404 falls back)", "5.2",
                    [drv("server_rules", rules=[{"match": r"/good/OTC_latest-f1\.json$", "action": "status", "status": 500}]),
                     open_latest(err("network", status=500)),
                     drv("assert_requests", match=r"/good/OTC_latest\.json$", count=0)],
                    requires=["fs"], timeout_s=90))
    out.append(case("net/latest-stream", "stream mode downloads .jsonl and .meta.json with Accept-Encoding gzip and builds index-v1.json", "5.2, 5.7, 6.2",
                    [open_latest(mode="stream"),
                     drv("assert_requests", match=r"/good/OTC_20991231\.2\.jsonl$", min=1, header={"accept-encoding": "gzip"}),
                     drv("assert_requests", match=r"/good/OTC_latest-f1\.json$", min=1, header={"accept-encoding": "gzip"}),
                     drv("assert_files", dir="${cache}/v1/releases/20991231.2",
                         present=[".verified", "OTC_20991231.2.jsonl", "OTC_20991231.2.meta.json", "index-v1.json"], no_tmp=True),
                     drv("assert_sha256", path="${cache}/v1/releases/20991231.2/OTC_20991231.2.jsonl", equals=f"{FIX}/good/OTC_20991231.2.jsonl"),
                     step("station", {"station": {"$type": "object"}}, station_id="OTC-T-0006")],
                    requires=["fs", "stream"]))
    out.append(case("net/eager-stores-json", "eager mode stores the release decompressed as .json in the cache", "5.4",
                    [open_latest(mode="eager"),
                     drv("assert_sha256", path="${cache}/v1/releases/20991231.2/OTC_20991231.2.json", equals=f"{FIX}/good/OTC_20991231.2.json"),
                     drv("assert_json", path="${cache}/v1/releases/20991231.2/.verified",
                         match={"files": {"$type": "object"}, "verified_at": {"$type": "string"}, "by": {"$regex": "^opentideconstants-[a-z0-9]+/"}})],
                    requires=["fs", "eager"]))
    out.append(case("net/second-open-uses-cache", "a second client: conditional GET of the pointer (304), no data request, loaded_from cache", "5.2, 5.3, 4.3.1",
                    [open_latest(), drv("restart_runner"), drv("clear_log"),
                     net(step("open", {"loaded_from": "cache", "datestamp": d2}, base_url=G, cache_dir="${cache}")),
                     drv("assert_requests", match=r"/good/OTC_latest-f1\.json$", min=1, status=304, header={"if-none-match": '^"[0-9a-f]{64}"$'}),
                     drv("assert_requests", match=r"/good/OTC_20991231\.2\.", count=0),
                     step("release_files", {"files": cached_rows(info2)})],
                    requires=["fs"]))
    out.append(case("net/pinned-cached-no-network", "a pinned, cached release opens with the server stopped and no socket", "4.2, 5.2, 6.5",
                    [net(step("open", {"loaded_from": "download", "datestamp": d2}, release=d2, base_url=G, cache_dir="${cache}")),
                     drv("restart_runner"), drv("server_stop"), drv("clear_log"),
                     net(step("open", {"loaded_from": "cache", "datestamp": d2}, release=d2, base_url=G, cache_dir="${cache}")),
                     drv("assert_requests", source="any", count=0)],
                    requires=["fs"]))
    # A pinned download reads only OTC_{D}.sha256 (spec 5.2), so release.files is checked against that file
    # alone: its names and digests, for the files the open stored (the .verified rows, CR3 DR100), with their
    # real sizes; url is the true value or null (README "Choices"). The default mode is eager (C: stream).
    sums1 = sha256_rows("good", d1)
    pinned_rows = {"$any_of": [[{"name": n, "url": {"$any_of": [None, G + n]}, "size": (FIXTURES / "good" / n).stat().st_size,
                                 "sha256": sums1[n]} for n in names]
                               for names in ([f"OTC_{d1}.json"], [f"OTC_{d1}.jsonl", f"OTC_{d1}.meta.json"])]}
    out.append(case("net/pinned-download", "a pinned older release downloads; its metadata is that release's; files from its .sha256", "4.2, 4.3.1, 5.2",
                    [net(step("open", {"loaded_from": "download", "datestamp": d1}, release=d1, base_url=G, cache_dir="${cache}")),
                     drv("assert_requests", match=r"OTC_(latest|index)", count=0),
                     step("release_metadata", {"datestamp": d1, "zenodo_version_doi": None, "build_commit": "0123456789abcdef0123456789abcdef01234567"}),
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
                    [drv("server_rules", rules=[{"match": r"/good/OTC_latest-f1\.json$", "action": "status", "status": 429, "headers": {"Retry-After": "2"}, "times": 1}]),
                     open_latest(),
                     drv("assert_requests", match=r"/good/OTC_latest-f1\.json$", count=2, min_gap_s=1.9)],
                    requires=["fs"]))
    out.append(case("net/500-raise", "the pointer always answers 500, on_network_error raise: network error with status 500 after 3 attempts", "4.8, 5.2, 5.7",
                    [drv("server_rules", rules=[{"match": r"/good/OTC_latest(-f1)?\.json$", "action": "status", "status": 500}]),
                     open_latest(err("network", status=500), on_network_error="raise"),
                     drv("assert_requests", match=r"/good/OTC_latest-f1\.json$", count=3)],
                    requires=["fs"], timeout_s=90))
    out.append(case("net/500-no-cache", "the pointer always answers 500 and the cache is empty: network error even with use_cache", "5.2",
                    [drv("server_rules", rules=[{"match": r"/good/OTC_latest(-f1)?\.json$", "action": "status", "status": 500}]),
                     open_latest(err("network"))],
                    requires=["fs"], timeout_s=90))
    out.append(case("net/500-use-cache", "a network error with a cached release: loaded_from cache_after_error and last_error", "4.3, 5.2",
                    [open_latest(), drv("restart_runner"),
                     drv("server_rules", rules=[{"match": r"/good/OTC_latest(-f1)?\.json$", "action": "status", "status": 500}]),
                     open_latest({"loaded_from": "cache_after_error", "datestamp": d2}),
                     step("last_error", {"code": "network"}),
                     step("release_files", {"files": cached_rows(info2)})],
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
    # CR D15 (CR2 G8): the variable is read without regard to case and after a trim, and it wins over offline: false
    out.append(case("net/offline-env-trim-case", "OPENTIDECONSTANTS_OFFLINE=' Yes ' (case and spaces) works like offline: true (CR D15)", "4.2, 5.5",
                    [open_latest(), drv("restart_runner", env={"OPENTIDECONSTANTS_OFFLINE": " Yes "}), drv("server_stop"), drv("clear_log"),
                     open_latest({"loaded_from": "cache", "datestamp": d2}), drv("assert_requests", source="any", count=0)],
                    requires=["fs"]))
    out.append(case("net/offline-env-wins-over-option", "OPENTIDECONSTANTS_OFFLINE=On with offline: false: the variable wins, no socket (CR D15)", "4.2, 5.5",
                    [open_latest(), drv("restart_runner", env={"OPENTIDECONSTANTS_OFFLINE": "On"}), drv("server_stop"), drv("clear_log"),
                     open_latest({"loaded_from": "cache", "datestamp": d2}, offline=False), drv("assert_requests", source="any", count=0)],
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
                    [open_latest({"loaded_from": "download", "datestamp": D10, "format_version": "1.0"}, base_url=O),
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
                    [drv("server_rules", rules=[{"match": r"/good/OTC_latest-f1\.json$", "action": "status", "status": 404}]),
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
                        requires=["fs", "stream"]))
    out.append(case("net/checksum-error-fields", "checksum_mismatch has file, expected and actual", "4.8",
                    [net(step("open", err("checksum_mismatch", file={"$regex": r"OTC_20991231\.(json|json\.gz|jsonl)$"},
                                          expected={"$regex": "^[0-9a-f]{64}$"}, actual={"$regex": "^[0-9a-f]{64}$"}),
                              release=d1, base_url=f"{SRV}/bad/wrong-sha256/", cache_dir="${cache}"))],
                    requires=["fs"]))
    out.append(case("net/format-minor-latest", "latest from bad/format-minor (1.1) loads", "7.3",
                    [net(step("open", {"loaded_from": "download", "datestamp": d1, "format_version": "1.1"}, base_url=f"{SRV}/bad/format-minor/", cache_dir="${cache}"))],
                    requires=["fs"]))
    out.append(case("net/short-body", "a body shorter than its Content-Length (connection closed): network error", "5.7",
                    [drv("server_rules", rules=[{"match": r"\.(json\.gz|jsonl|json)$", "action": "short_body", "delta": 100}]),
                     net(step("open", err("network"), release=d2, base_url=G, cache_dir="${cache}", on_network_error="raise"))],
                    requires=["fs"], timeout_s=90))
    out.append(case("net/truncated-body", "a consistent but truncated response (wrong length for the release): checksum_mismatch", "5.2, 5.3",
                    [drv("server_rules", rules=[{"match": r"/good/OTC_20991231\.2\.(json\.gz|jsonl|json)$", "action": "truncate", "bytes": 1000}]),
                     net(step("open", err("checksum_mismatch"), release=d2, base_url=G, cache_dir="${cache}", on_network_error="raise"))],
                    requires=["fs"]))
    out.append(case("net/listed-file-404", "a data file that OTC_{D}.sha256 lists answers 404: network error with status 404, not release_not_found (D32)", "4.8, 5.2",
                    [drv("server_rules", rules=[{"match": r"/good/OTC_20991231\.2\.(json\.gz|jsonl|json)$", "action": "status", "status": 404}]),
                     net(step("open", err("network", status=404), release=d2, base_url=G, cache_dir="${cache}", on_network_error="raise"))],
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
    # Credentials (spec 5.7, CR2 DR21): the user and password of a URL never appear in an error message. The URLs
    # fail (a socks5 proxy, a closed port 1), so the message is the SDK's own, not a server's.
    no_creds = {"$regex": r"^(?![\s\S]*(" + CRED_USER + "|" + CRED_PASS + "))"}
    out.append(case("net/proxy-credentials-redacted", "a proxy option that is not an http(s) URL: its user and password are not in the message (DR21)", "5.7",
                    [open_latest({"error": "invalid_argument", "error_message": no_creds},
                                 proxy=f"socks5://{CRED_USER}:{CRED_PASS}@proxy.invalid:1080", on_network_error="raise")],
                    requires=["fs"]))
    out.append(case("net/proxy-env-credentials-redacted", "an http_proxy that refuses the connection: its user and password are not in the message (DR21)", "5.7",
                    [drv("restart_runner", env={"HTTP_PROXY": f"http://{CRED_USER}:{CRED_PASS}@127.0.0.1:1",
                                                "http_proxy": f"http://{CRED_USER}:{CRED_PASS}@127.0.0.1:1"}),
                     open_latest({"error": "network", "error_message": no_creds}, base_url=GA, on_network_error="raise")],
                    requires=["fs"], timeout_s=120))
    out.append(case("net/proxy-unreachable-credentials-redacted", "an http proxy that refuses the connection: its user and password are not in the message, nor in the error's url field (DR21, DR21b)", "5.7",
                    [open_latest({"error": "network", "error_message": no_creds, "error_fields": {"url": no_creds}},
                                 proxy=f"http://{CRED_USER}:{CRED_PASS}@127.0.0.1:1", on_network_error="raise")],
                    requires=["fs"], timeout_s=120))
    # CR2 DR21b (orchestrator decision 2026-10-09): the structured url field of the network error (C: otc_error.file)
    # is redacted too, since callers print it: "***@" stands where the user and password were
    redacted_url = {"$all": [no_creds, {"$contains": "://***@127.0.0.1:1/good/"}]}
    out.append(case("net/base-url-credentials-redacted", "a base_url with a user and password that fails: they are not in the message, nor in the error's url field, which has ***@ in their place (DR21, DR21b)", "4.2, 5.7",
                    [open_latest({"error": "network", "error_message": no_creds, "error_fields": {"url": redacted_url}},
                                 base_url=f"http://{CRED_USER}:{CRED_PASS}@127.0.0.1:1/good/", on_network_error="raise")],
                    requires=["fs"], timeout_s=120))
    # releases / latest / check_for_update
    out.append(case("net/releases", "releases(): every release from OTC_index.json, newest first", "4.3",
                    [open_latest(), net(step("releases", {"releases": [info2, info1]}))], requires=["fs"]))
    out.append(case("net/releases-offline-cached-index", "releases() offline uses the cached index", "4.3, 5.5",
                    [open_latest(), net(step("releases", {"releases": [info2, info1]})), drv("restart_runner"), drv("server_stop"), drv("clear_log"),
                     open_latest({"loaded_from": "cache"}, offline=True), net(step("releases", {"releases": [info2, info1]})),
                     drv("assert_requests", source="any", count=0)], requires=["fs"]))
    # api.json erratum (CR2 PK-R2-10, DR16): a cached file that cannot be read is cache, so releases() lists cache
    ci = "${cache}/v1/pointer/OTC_index.json"
    out.append(case("net/releases-offline-index-unreadable", "releases() offline when the cached OTC_index.json cannot be read: cache, not offline_unavailable", "4.3, 4.8, 5.2",
                    [open_latest(), net(step("releases", {"releases": [info2, info1]})), drv("restart_runner"), drv("server_stop"),
                     open_latest({"loaded_from": "cache"}, offline=True), drv("chmod", path=ci, mode="000"),
                     net(step("releases", err("cache"))), drv("chmod", path=ci, mode="644")], requires=["fs"]))
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
                     drv("assert_requests", match=r"/good/OTC_latest-f1\.json$", count=1, status=304)], requires=["fs"]))
    return out


def group_network_cr2_pk11():
    """Error classification (CR2 PK-R2-11): D32, DR20, a redirect with no host, a 304 with no stored copy, and an
    index 404 when the pointer's release is too new (spec 4.2, 4.8, 5.2, 5.7)."""
    out = []
    G = f"{SRV}/good/"
    d2, d1 = "20991231.2", "20991231"
    B = "${tmp}/bundle"

    def open_latest(expect, base=G, **kw):
        return net(step("open", expect, base_url=base, cache_dir="${cache}", **kw))

    # D32: the release exists (its .sha256 lists the file), so a 404 for the file is a server inconsistency:
    # network with status 404, never retried, never release_not_found
    d32_message = {"$contains": "missing on the server"}
    jl404 = err("network", status=404)
    jl404["error_message"] = d32_message
    out.append(case("net/listed-file-404-sent-once", "a data file that OTC_{D}.sha256 lists answers 404: network with status 404, sent once (D32)", "4.8, 5.2",
                    [drv("server_rules", rules=[{"match": rf"^/good/OTC_{re.escape(d2)}\.jsonl$", "action": "status", "status": 404}]),
                     open_latest(jl404, mode="stream", on_network_error="raise"),
                     drv("assert_requests", match=rf"^/good/OTC_{re.escape(d2)}\.jsonl$", count=1)],
                    requires=["fs", "stream"]))
    out.append(case("net/listed-file-404-download", "download of a release whose listed .jsonl answers 404: network with status 404, and nothing is written (D32)", "4.3.2, 4.8",
                    [open_latest({"datestamp": d2}, mode="stream"),
                     drv("server_rules", rules=[{"match": rf"^/good/OTC_{re.escape(d1)}\.jsonl$", "action": "status", "status": 404}]),
                     net(step("download", jl404, release=d1, to=B), fs=True),
                     drv("assert_requests", match=rf"^/good/OTC_{re.escape(d1)}\.jsonl$", count=1),
                     drv("assert_tree", dir=B, allow=[], may_be_missing=True)],
                    requires=["fs", "stream"]))
    # DR20: SSL_CERT_FILE is checked at construction like ca_file: io, no request, no fallback to a cached release
    out.append(case("net/ssl-cert-file-missing", "SSL_CERT_FILE names a missing file, with a cached release and use_cache: io at once, no request, no fallback (DR20)", "4.2, 4.8, 5.7",
                    [open_latest({"datestamp": d2}),
                     drv("restart_runner", env={"SSL_CERT_FILE": "${tmp}/no-such-ca.pem"}), drv("clear_log"),
                     open_latest(err("io")),
                     drv("assert_requests", source="any", count=0)],
                    requires=["fs"]))
    # DR20: a user_agent with a control character is invalid_argument at construction, before any request
    ua_steps = []
    for ua in ["app/1\r\nX-Injected: 1", "app/1\n", "app\u007f1", "app\t1"]:
        ua_steps.append(open_latest(err("invalid_argument"), user_agent=ua))
    out.append(case("net/user-agent-control-char", "user_agent with CR LF, LF, DEL or TAB: invalid_argument at construction, and no request (DR20)", "4.2, 4.8, 5.7",
                    ua_steps + [drv("assert_requests", source="any", count=0)],
                    requires=["fs"]))
    # a redirect Location with no host is not followed: network, and no request to any other host
    out.append(case("net/redirect-no-host", "OTC_{D}.sha256 redirects to a Location with no host (http://): network, not followed", "5.7",
                    [drv("server_rules", rules=[{"match": rf"^/good/OTC_{re.escape(d2)}\.sha256$", "action": "status", "status": 302,
                                                 "headers": {"Location": "http://"}}]),
                     net(step("open", err("network"), release=d2, base_url=G, cache_dir="${cache}", on_network_error="raise")),
                     drv("assert_requests", match=rf"^/good/OTC_{re.escape(d2)}\.sha256$", min=1)],
                    requires=["fs"], timeout_s=90))
    # a 304 to a GET that sent no If-None-Match (no stored copy) is a network error with status 304, never a 200
    out.append(case("net/304-no-cache", "the pointer answers 304 with an empty cache (no If-None-Match sent): network with status 304", "5.2, 4.8",
                    [drv("server_rules", rules=[{"match": r"/good/OTC_latest(-f1)?\.json$", "action": "status", "status": 304}]),
                     open_latest(err("network", status=304), on_network_error="raise")],
                    requires=["fs"], timeout_s=90))
    # the pointer's release is too new and OTC_index.json is a 404: the SDK has no readable release, so the error
    # is reader_too_old for the pointer's release (spec 5.2 step 2a, 7.4), not release_not_found
    RD = f"{SRV}/reader/"
    too_old = err("reader_too_old")
    too_old["error_message"] = TOO_OLD_MESSAGE
    out.append(case("net/index-404-reader-too-old", "the pointer names a release too new for the SDK and OTC_index.json answers 404: reader_too_old, not release_not_found", "5.2, 7.4",
                    [drv("server_rules", rules=[{"match": r"/reader/OTC_index\.json$", "action": "status", "status": 404}]),
                     open_latest(too_old, base=RD, on_network_error="raise"),
                     drv("assert_requests", match=r"OTC_20991231\.4\.", count=0)],
                    requires=["fs"]))
    return out


def group_update():
    out = []
    G = f"{SRV}/good/"
    d2, d1 = "20991231.2", "20991231"
    old_pointer = [{"match": r"/good/OTC_latest(-f1)?\.json$", "action": "json", "file": "good/OTC_index.json", "pointer": "/releases/1"}]
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
    # CR2 DR4: any check that reaches the pointer (manual or automatic) clears last_error; loaded_from does not change
    info2 = enc_release_info("good", d2, G)
    fail_ptr = [{"match": r"/good/OTC_latest(-f1)?\.json$", "action": "status", "status": 500}]
    auto_failed = [open_latest_step(G, auto_update=True, update_interval=1),
                   drv("server_rules", rules=fail_ptr), drv("sleep", s=1.5),
                   step("station", {"station": {"$type": "object"}}, station_id="OTC-T-0001"),
                   step("last_error", {"code": "network"}),
                   drv("server_rules", rules=[])]
    out.append(case("update/last-error-cleared-auto", "an automatic update fails (last_error network); the next automatic check reaches the pointer and finds nothing newer: last_error is null, loaded_from unchanged (CR2 DR4)", "4.3, 5.6",
                    auto_failed + [drv("sleep", s=1.5),
                                   step("station", {"station": {"$type": "object"}}, station_id="OTC-T-0001"),
                                   step("last_error", {"code": None}),
                                   step("loaded_from", {"loaded_from": "download"})],
                    requires=["fs"], timeout_s=120))
    after_error = [open_latest_step(G), drv("restart_runner"), drv("server_rules", rules=fail_ptr),
                   net(step("open", {"loaded_from": "cache_after_error", "datestamp": d2}, base_url=G, cache_dir="${cache}")),
                   step("last_error", {"code": "network"}),
                   drv("server_rules", rules=[])]
    for op, expect in [("latest", {"release": info2}), ("check_for_update", {"release": None}),
                       ("update", {"updated": False, "from": d2, "to": d2})]:
        out.append(case(f"update/last-error-cleared-{op.replace('_', '-')}", f"loaded_from cache_after_error, then {op} reaches the pointer: last_error is null, and loaded_from stays cache_after_error (CR2 DR4)", "4.3",
                        after_error + [net(step(op, expect)),
                                       step("last_error", {"code": None}),
                                       step("loaded_from", {"loaded_from": "cache_after_error"})],
                        requires=["fs"], timeout_s=120))
    out.append(case("update/auto-off", "without auto_update the loaded release never changes", "5.6",
                    [drv("server_rules", rules=old_pointer),
                     net(step("open", {"datestamp": d1}, base_url=G, cache_dir="${cache}", update_interval=1)),
                     drv("server_rules", rules=[]), drv("sleep", s=2.5),
                     step("station", {"station": enc_station(R1, R1.by_id["OTC-T-0021"])}, station_id="OTC-T-0021"),
                     step("release_metadata", {"datestamp": d1})], requires=["fs"]))
    return out


def group_lifecycle(R2):
    """Close (spec 4.2 Close row, CR D21, CR2 DR32). A Release held from before close is closed with the client. Its
    in-memory metadata stays readable; every query and iterator fails with io "the release is closed". C has no
    client object, and otc_close frees the release, so a call after it is undefined: the case needs eager, which C
    does not have."""
    out = []
    closed = {"error": "io", "error_message": {"$contains": "closed"}}
    alias_st = next(s for s in R2.active if s.get("aliases"))
    system, ids = next(iter(alias_st["aliases"].items()))
    alias_id = ids[0] if isinstance(ids, list) else ids
    sub = next(s for s in R2.active if s["type"] == "subordinate" and s.get("subordinate_offsets"))
    ref_id = sub["subordinate_offsets"]["reference_station_id"]
    on = "before"
    queries = [
        step("station", closed, on=on, station_id="OTC-T-0001"),
        step("require_station", closed, on=on, station_id="OTC-T-0001"),
        step("tombstone", closed, on=on, station_id="OTC-T-0005"),
        step("station_by_alias", closed, on=on, system=system, alias_id=alias_id),
        step("stations", closed, on=on),
        step("iter_stations", closed, on=on),
        step("search", closed, on=on, name="a"),
        step("near", closed, on=on, lat=0.0, lon=0.0, radius_km=20000),
        step("nearest", closed, on=on, lat=0.0, lon=0.0),
        step("reference_station", closed, on=on, station_id=sub["station_id"]),
        step("subordinates_of", closed, on=on, station_id=ref_id),
        step("attribution", closed, on=on),
        step("attribution", closed, on=on, station_ids=["OTC-T-0001"]),
        step("stats", closed, on=on),
        step("station_count", closed, on=on),
        step("tombstone_count", closed, on=on),
        step("constituent_names", closed, on=on),
        step("conventions", closed, on=on),
        step("convention", closed, on=on, convention_id="kartverket-utc1-v1"),
        step("licences", closed, on=on),
        step("licence", closed, on=on, licence_id=R2.doc["licences"][0]["licence_id"]),
    ]
    out.append(mcase("lifecycle/after-close", "after close, a Release held from before keeps its metadata (datestamp, created, format_version, citation, files) and every query and iterator is io \"the release is closed\", in eager and stream mode (CR D21, CR2 DR32)", "4.2",
                     [step("hold_release", None, name=on), step("close"),
                      step("release_metadata", enc_release_meta(R2), on=on),
                      step("citation", {"citation": citation(R2)}, on=on),
                      step("release_files", {"files": {"$type": "array"}}, on=on)] + queries,
                     requires=["eager"]))
    return out


def open_latest_no_cache(G, **kw):
    """open latest with no cache_dir (a file-system option): for the cases a runner without fs (a browser) runs.
    The SDK uses its default cache, which the driver puts in the case's temporary directory."""
    return net(step("open", {"loaded_from": "download", "datestamp": "20991231.2"}, base_url=G, **kw))


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
    # spec 5.4 (CR2 DR3): prune takes a release lock without waiting and applies the age test at once
    lk = f"${{cache}}/v1/releases/{d1}/.lock"
    crashed = {"pid": 1, "host": "crashed", "sdk": "conformance", "started_at": "2000-01-01T00:00:00Z", "token": "0" * 32}
    out.append(case("cache/prune-stale-lock", "prune removes a release whose lock is at least 120 s old (a crashed process)", "4.3, 5.4",
                    both + [drv("mkdir", path=lk), drv("write", path=f"{lk}/owner.json", text=json.dumps(crashed)),
                            net(step("prune", {"removed": [d1]}, keep=1)), net(step("cached_releases", {"datestamps": [d2]})),
                            drv("assert_files", dir="${cache}/v1/releases", absent=[d1], present=[d2])], requires=["fs"]))
    out.append(case("cache/prune-fresh-lock", "prune keeps a release whose lock is younger than 120 s (age from the lock's mtime)",
                    "4.3, 5.4",
                    both + [drv("mkdir", path=lk),
                            net(step("prune", {"removed": []}, keep=1)), net(step("cached_releases", {"datestamps": [d2, d1]})),
                            drv("assert_files", dir=f"${{cache}}/v1/releases/{d1}", present=[".lock", ".verified"])],
                    requires=["fs"]))
    out.append(case("cache/prune-invalid", "prune with a negative keep: invalid_argument", "4.3, 4.8",
                    [open_latest_step(G), net(step("prune", err("invalid_argument"), keep=-1))], requires=["fs"]))
    out.append(case("cache/verify", "verify on a cached release passes, and fails after a cached file changes", "4.3, 5.3",
                    [open_latest_step(G, mode="stream"), step("verify", {"verified": True}),
                     drv("corrupt", path="${cache}/v1/releases/20991231.2/OTC_20991231.2.jsonl", offset=50),
                     step("verify", err("checksum_mismatch"))], requires=["fs", "stream"]))
    out.append(case("cache/not-writable", "a cache directory that cannot be created: cache error", "4.8",
                    [drv("write", path="${tmp}/not-a-dir", text="x"),
                     net(step("open", err("cache"), base_url=G, cache_dir="${tmp}/not-a-dir/cache"))], requires=["fs"]))
    # CR2 DR18 (spec 4.3): prune stops at the first release it cannot remove, and the CacheError reports the releases
    # removed before it (C: the output array and count). Newest first: D10 (loaded, kept), d2 (removed), d1 (read-only)
    out.append(case("cache/prune-partial-failure", "prune(keep: 0) removes 20991231.2, then cannot remove 20991231 (read-only): cache error whose removed is [20991231.2]", "4.3, 4.8",
                    [net(step("open", {"datestamp": d2}, release=d2, base_url=G, cache_dir="${cache}")),
                     net(step("open", {"datestamp": d1}, release=d1, base_url=G, cache_dir="${cache}")),
                     net(step("open", {"datestamp": D10}, release=D10, base_url=O, cache_dir="${cache}")),
                     drv("chmod", path=f"${{cache}}/v1/releases/{d1}", mode="555"),
                     net(step("prune", err("cache", removed=[d2]), keep=0)),
                     drv("chmod", path=f"${{cache}}/v1/releases/{d1}", mode="755"),
                     net(step("cached_releases", {"datestamps": [D10, d1]})),
                     drv("assert_files", dir="${cache}/v1/releases", absent=[d2], present=[D10, d1])], requires=["fs"]))
    # CR D33 (spec 4.3): on a client opened with file, cached_releases and prune work on the configured cache (cache_dir,
    # or the default), never on the file's folder
    rel = "${tmp}/rel"
    rel_files = [f"OTC_{d2}.jsonl", f"OTC_{d2}.meta.json", f"OTC_{d2}.sha256"]
    copy_rel = drv("copy", files=[f"{FIX}/good/{n}" for n in rel_files], to=rel)
    out.append(case("cache/file-client-uses-cache-dir", "a client opened with file and cache_dir: cached_releases and prune use cache_dir, not the file's folder", "4.3",
                    both + [copy_rel,
                            step("open", {"loaded_from": "file", "datestamp": d2}, file=f"{rel}/OTC_{d2}.jsonl", cache_dir="${cache}"),
                            net(step("cached_releases", {"datestamps": [d2, d1]})),
                            net(step("prune", {"removed": [d1]}, keep=1)),
                            net(step("cached_releases", {"datestamps": [d2]})),
                            drv("assert_files", dir="${cache}/v1/releases", absent=[d1], present=[d2]),
                            drv("assert_files", dir=rel, exactly=rel_files)], requires=["fs"]))
    out.append(case("cache/file-client-uses-default-cache", "a client opened with file and no cache_dir: cached_releases and prune use the default cache, not the file's folder", "4.3",
                    [net(step("open", {"datestamp": d1}, release=d1, base_url=G)),
                     net(step("open", {"datestamp": d2}, release=d2, base_url=G)),
                     copy_rel,
                     step("open", {"loaded_from": "file", "datestamp": d2}, file=f"{rel}/OTC_{d2}.jsonl"),
                     net(step("cached_releases", {"datestamps": [d2, d1]})),
                     net(step("prune", {"removed": [d1]}, keep=1)),
                     net(step("cached_releases", {"datestamps": [d2]})),
                     drv("assert_files", dir=rel, exactly=rel_files)], requires=["fs"]))
    out.append(case("cache/files-from-verified", "loaded_from cache: release.files comes from .verified", "4.3.1",
                    [open_latest_step(G), drv("restart_runner"), drv("server_stop"),
                     net(step("open", {"loaded_from": "cache", "datestamp": d2}, release=d2, base_url=G, cache_dir="${cache}")),
                     step("release_files", {"files": cached_rows(enc_release_info("good", d2, G))})], requires=["fs"]))
    return out + corrupt_cache_cases() + missing_sha256_cases() + dr100_cases()


def missing_sha256_cases():
    """A cached release whose OTC_{D}.sha256 is gone (CR2 DR34 x DR16, orchestrator decision 2026-10-09). Only C reads
    the cached .sha256 to open a release, and only with require_checksum; the other SDKs open it from .verified. Offline,
    and when the cache stands in for the network, a release that only lacks its checksum list is not corrupt: it is
    kept, never deleted, because it cannot be fetched again. Online, the open heals it and downloads it again."""
    out = []
    G = f"{SRV}/good/"
    d2, d1 = "20991231.2", "20991231"
    r2 = "${cache}/v1/releases/" + d2
    kept = drv("assert_files", dir=r2, present=[".verified", f"OTC_{d2}.jsonl", f"OTC_{d2}.meta.json"], absent=[f"OTC_{d2}.sha256"])
    no_sha = drv("delete", path=f"{r2}/OTC_{d2}.sha256")
    p503 = drv("server_rules", rules=[{"match": r"/good/OTC_latest(-f1)?\.json$", "action": "status", "status": 503}])

    def pin(d, expect=None, **kw):
        return net(step("open", expect or {"datestamp": d}, release=d, base_url=G, cache_dir="${cache}", mode="stream", **kw))

    def latest(expect, **kw):
        return net(step("open", expect, base_url=G, cache_dir="${cache}", mode="stream", **kw))

    no_sum = err("checksum_mismatch")
    out.append(case("cache/no-sha256-offline-kept", "offline, the cached OTC_{D}.sha256 is gone: the pinned and the latest open load the release from the cache (C: unverified), and nothing is deleted", "5.2, 5.3",
                    [pin(d2), drv("restart_runner"), no_sha, drv("server_stop"),
                     pin(d2, {"loaded_from": "cache", "datestamp": d2}, offline=True), kept,
                     latest({"loaded_from": "cache", "datestamp": d2}, offline=True), kept],
                    requires=["fs", "stream"]))
    out.append(case("cache/require-checksum-no-sha256-offline-kept", "offline with require_checksum, the newest cached OTC_{D}.sha256 is gone: the pinned and the latest open fail with checksum_mismatch, and the release is kept (it cannot be fetched again)", "5.2, 5.3",
                    [pin(d1), pin(d2), drv("restart_runner"), no_sha, drv("server_stop"),
                     pin(d2, no_sum, offline=True, require_checksum=True), kept,
                     latest(no_sum, offline=True, require_checksum=True), kept,
                     drv("assert_files", dir="${cache}/v1/releases/" + d1, present=[".verified", f"OTC_{d1}.sha256"])],
                    requires=["fs", "stream", "require_checksum"]))
    out.append(case("cache/require-checksum-no-sha256-network-error-kept", "the pointer answers 503, require_checksum is on and the newest cached OTC_{D}.sha256 is gone: the network error, and the release is kept", "5.2, 5.3",
                    [pin(d2), drv("restart_runner"), no_sha, p503,
                     latest(err("network", status=503), require_checksum=True), kept],
                    requires=["fs", "stream", "require_checksum"], timeout_s=90))
    out.append(case("cache/require-checksum-no-sha256-online-heals", "online with require_checksum, the pinned cached OTC_{D}.sha256 is gone: the release is healed and downloaded again, with its .sha256", "5.2, 5.3",
                    [pin(d2), drv("restart_runner"), no_sha,
                     pin(d2, {"loaded_from": "download", "datestamp": d2}, require_checksum=True),
                     drv("assert_files", dir=r2, present=[".verified", f"OTC_{d2}.sha256", f"OTC_{d2}.jsonl"]),
                     drv("assert_sha256", path=f"{r2}/OTC_{d2}.jsonl", equals=f"{FIX}/good/OTC_{d2}.jsonl")],
                    requires=["fs", "stream", "require_checksum"]))
    return out


def corrupt_cache_cases():
    """A corrupt cached release on the offline and use_cache paths (spec 5.2 step 6, CR2 DR16): it is healed (its
    .verified and the bad file removed), the next older cached release is tried, and when none loads the original
    error is raised. A cached file that cannot be read is cache, never absent."""
    out = []
    G = f"{SRV}/good/"
    d2, d1 = "20991231.2", "20991231"
    r2, r1, rels = "${cache}/v1/releases/" + d2, "${cache}/v1/releases/" + d1, "${cache}/v1/releases"
    jl2 = f"{r2}/OTC_{d2}.jsonl"
    p503 = drv("server_rules", rules=[{"match": r"/good/OTC_latest(-f1)?\.json$", "action": "status", "status": 503}])
    no_d2 = drv("assert_requests", match=r"OTC_20991231\.2\.", count=0)
    healed = drv("assert_files", dir=r2, absent=[".verified", f"OTC_{d2}.jsonl"])

    def pin(d, mode="stream", **kw):
        return net(step("open", {"datestamp": d}, release=d, base_url=G, cache_dir="${cache}", mode=mode, **kw))

    def latest(expect, mode="stream", **kw):
        return net(step("open", expect, base_url=G, cache_dir="${cache}", mode=mode, **kw))

    both = [pin(d1), pin(d2), drv("restart_runner")]
    offline = [drv("server_stop"), drv("clear_log")]
    truncate = drv("write", path=jl2, text="truncated\n")
    out.append(case("cache/newest-corrupt-offline", "offline, the newest cached .jsonl is truncated: it is healed (.verified and the file removed) and the older cached release loads", "5.2",
                    both + [truncate] + offline + [
                        latest({"loaded_from": "cache", "datestamp": d1}, offline=True), healed,
                        net(step("cached_releases", {"datestamps": [d1]})), drv("assert_requests", source="any", count=0)],
                    requires=["fs", "stream"]))
    out.append(case("cache/newest-corrupt-network-error", "the pointer answers 503 and the newest cached .jsonl is truncated: it is healed and the older release loads as cache_after_error, with the network error", "5.2",
                    both + [truncate, p503, drv("clear_log"),
                            latest({"loaded_from": "cache_after_error", "datestamp": d1}),
                            step("last_error", {"code": "network"}), healed, no_d2],
                    requires=["fs", "stream"], timeout_s=90))
    out.append(case("cache/newest-bitrot-verify-on-open-network-error", "the pointer answers 503, the newest cached .jsonl has one byte changed and verify_on_open is on: the older release loads as cache_after_error, and nothing of the corrupt release is downloaded", "5.2, 5.3",
                    both + [drv("corrupt", path=jl2, offset=100), p503, drv("clear_log"),
                            latest({"loaded_from": "cache_after_error", "datestamp": d1}, verify_on_open=True),
                            step("last_error", {"code": "network"}),
                            drv("assert_files", dir=r2, absent=[".verified"]), no_d2],
                    requires=["fs", "stream"], timeout_s=90))
    out.append(case("cache/only-cached-corrupt-offline", "offline, the only cached release is truncated: offline_unavailable, and it is healed", "5.2",
                    [pin(d2), drv("restart_runner"), truncate] + offline + [
                        latest(err("offline_unavailable"), offline=True), healed],
                    requires=["fs", "stream"]))
    out.append(case("cache/only-cached-corrupt-network-error", "the pointer answers 503 and the only cached release is truncated: the network error, and it is healed", "5.2",
                    [pin(d2), drv("restart_runner"), truncate, p503,
                     latest(err("network", status=503)), healed],
                    requires=["fs", "stream"], timeout_s=90))
    out.append(case("cache/newest-unparsable-offline-eager", "offline in eager mode, the newest cached .json has one byte changed so that it does not parse (same size, verify_on_open off): it is healed and the older release loads", "5.2",
                    [pin(d1, "eager"), pin(d2, "eager"), drv("restart_runner"),
                     drv("corrupt", path=f"{r2}/OTC_{d2}.json", offset=0)] + offline + [
                        latest({"loaded_from": "cache", "datestamp": d1}, mode="eager", offline=True),
                        drv("assert_files", dir=r2, absent=[".verified", f"OTC_{d2}.json"])],
                    requires=["fs", "eager"]))
    out.append(case("cache/newest-corrupt-undeletable-offline", "offline, the newest cached .jsonl is truncated and its directory is read-only: the failure to delete it is logged, and the older release loads", "5.2",
                    both + [truncate, drv("chmod", path=r2, mode="555")] + offline + [
                        latest({"loaded_from": "cache", "datestamp": d1}, offline=True)],
                    requires=["fs", "stream"]))
    out.append(case("cache/pinned-wrong-size-heals-online", "a pinned cached release whose .jsonl has the wrong size: the open downloads it again, and the next open uses the cache", "5.2, 5.3",
                    [pin(d2), drv("restart_runner"), truncate,
                     net(step("open", {"loaded_from": "download", "datestamp": d2}, release=d2, base_url=G, cache_dir="${cache}", mode="stream")),
                     drv("assert_sha256", path=jl2, equals=f"{FIX}/good/OTC_{d2}.jsonl"), drv("restart_runner"),
                     net(step("open", {"loaded_from": "cache", "datestamp": d2}, release=d2, base_url=G, cache_dir="${cache}", mode="stream"))],
                    requires=["fs", "stream"]))
    out.append(case("cache/old-verified-bad-version-offline", "offline, the .verified of the older cached release has format_version \"x\": the newest release loads", "5.2",
                    both + [drv("json_set", path=f"{r1}/.verified", pointer="/format_version", value="x")] + offline + [
                        latest({"loaded_from": "cache", "datestamp": d2}, offline=True)],
                    requires=["fs", "stream"]))
    out.append(case("cache/newest-verified-row-not-object-offline", "offline, a files row of the newest .verified is not an object: that release is not trusted, and the older one loads", "5.2, 5.4",
                    both + [drv("json_set", path=f"{r2}/.verified", pointer=f"/files/OTC_{d2}.sha256", value=5)] + offline + [
                        latest({"loaded_from": "cache", "datestamp": d1}, offline=True)],
                    requires=["fs", "stream"]))
    out.append(case("cache/verified-row-not-object-pinned-online", "a files row of a pinned release's .verified is not an object: the release is downloaded again", "5.2, 5.4",
                    [pin(d2), drv("restart_runner"), drv("json_set", path=f"{r2}/.verified", pointer=f"/files/OTC_{d2}.sha256", value=5),
                     net(step("open", {"loaded_from": "download", "datestamp": d2}, release=d2, base_url=G, cache_dir="${cache}", mode="stream"))],
                    requires=["fs", "stream"]))
    out.append(case("cache/releases-dir-unreadable-offline", "offline, the cache's releases directory cannot be read: cache, not offline_unavailable", "5.2",
                    both + [drv("chmod", path=rels, mode="000")] + offline + [latest(err("cache"), offline=True)],
                    requires=["fs", "stream"]))
    out.append(case("cache/verified-unreadable-offline", "offline, the newest .verified cannot be read: cache, not io and not absent", "5.2",
                    both + [drv("chmod", path=f"{r2}/.verified", mode="000")] + offline + [latest(err("cache"), offline=True)],
                    requires=["fs", "stream"]))
    return out


def dr100_cases():
    """The .verified writer rule and the size reader rule (CR3 DR100, CR3 spec review 2 B10 and 3 C4, orchestrator
    decisions 2026-10-09; spec 4.3.1, 5.4). A writer writes a files row only for a file that is present and verified
    in the release directory, with its real size, and never a row for OTC_{D}.sha256. A pinned download lists exactly
    those rows in release.files; a download of latest lists the pointer entry. A row with a null or absent size makes
    .verified malformed: offline the release is not a candidate, online it is downloaded again."""
    out = []
    G = f"{SRV}/good/"
    d2, d1 = "20991231.2", "20991231"
    r2 = "${cache}/v1/releases/" + d2
    shas = sha256_rows("good", d2)
    info2 = enc_release_info("good", d2, G)
    ptr = {f["name"]: f for f in info2["files"]}
    n_json, n_jsonl, n_meta, n_gz, n_sums = (f"OTC_{d2}{x}" for x in (".json", ".jsonl", ".meta.json", ".json.gz", ".sha256"))

    def size(n):
        return (FIXTURES / "good" / n).stat().st_size

    def vrow(n):   # a .verified row: the real size, the .sha256 digest, the true url or null
        return {"sha256": shas[n], "size": size(n), "url": {"$any_of": [None, G + n, ptr[n]["url"]]}}

    def frow(n):   # a release.files row of a pinned download
        return {"name": n, "url": {"$any_of": [None, G + n, ptr[n]["url"]]}, "size": size(n), "sha256": shas[n]}

    def vfiles(*names):
        return drv("assert_json", path=f"{r2}/.verified", match={"files": {n: vrow(n) for n in names}})

    def rfiles(*names):
        return step("release_files", {"files": [frow(n) for n in sorted(names)]})

    def pin(mode, expect="download", **kw):
        return net(step("open", {"loaded_from": expect, "datestamp": d2}, release=d2, base_url=G, cache_dir="${cache}",
                        mode=mode, **kw))

    def latest(mode, expect="download", **kw):
        return net(step("open", {"loaded_from": expect, "datestamp": d2}, base_url=G, cache_dir="${cache}", mode=mode, **kw))

    STREAM, EAGER = [n_jsonl, n_meta], [n_json]
    out.append(case("cache/dr100-pinned-stream-rows", "a pinned stream download: .verified has a row only for the .jsonl and the .meta.json, each with its real size, and no row for the .sha256 file; release.files lists exactly those rows (DR100)", "4.3.1, 5.4",
                    [pin("stream"), vfiles(*STREAM), rfiles(*STREAM)], requires=["fs", "stream"]))
    out.append(case("cache/dr100-pinned-eager-rows", "a pinned eager download: .verified has a row only for the stored .json (not the fetched .json.gz), with its real size; release.files lists exactly that row (DR100)", "4.3.1, 5.4",
                    [pin("eager"), vfiles(*EAGER), rfiles(*EAGER)], requires=["fs", "eager"]))
    out.append(case("cache/dr100-pinned-other-mode-adds", "a pinned stream open adds the .jsonl and the .meta.json to a release cached in eager mode: .verified keeps the .json row and adds the two; release.files lists the three (DR100)", "4.3.1, 5.4",
                    [pin("eager"), drv("restart_runner"), pin("stream"), vfiles(n_json, n_jsonl, n_meta),
                     rfiles(n_json, n_jsonl, n_meta)], requires=["fs", "stream", "eager"]))
    for mode, names in (("stream", STREAM), ("eager", EAGER)):
        out.append(case(f"cache/dr100-latest-{mode}-rows", f"a download of latest in {mode} mode: .verified has a row only for the files it stored (real size, no .sha256 row); release.files is the pointer entry; a later cached open lists the .verified rows (DR100)", "4.3.1, 5.4",
                        [latest(mode), vfiles(*names), step("release_files", {"files": info2["files"]}),
                         drv("restart_runner"), drv("server_stop"),
                         latest(mode, "cache", offline=True), rfiles(*names)], requires=["fs", mode]))
    # update and the automatic update download latest too, so release.files is the pointer entry. C's update gives a
    # path, and the release is opened from the cache (the .verified rows), so these need a client update: eager.
    old_pointer = [{"match": r"/good/OTC_latest(-f1)?\.json$", "action": "json", "file": "good/OTC_index.json", "pointer": "/releases/1"}]
    out.append(case("cache/dr100-update-rows", "update downloads the newer latest: release.files is the pointer entry, and its .verified has a row only for the stored .json (DR100)", "4.3, 4.3.1, 5.4",
                    [drv("server_rules", rules=old_pointer),
                     net(step("open", {"loaded_from": "download", "datestamp": d1}, base_url=G, cache_dir="${cache}", mode="eager")),
                     drv("server_rules", rules=[]),
                     net(step("update", {"updated": True, "from": d1, "to": d2})),
                     step("release_files", {"files": info2["files"]}), vfiles(*EAGER)], requires=["fs", "eager"]))
    out.append(case("cache/dr100-auto-update-rows", "an automatic update downloads the newer latest: release.files is the pointer entry, and its .verified has a row only for the stored .json (DR100)", "4.3.1, 5.4, 5.6",
                    [drv("server_rules", rules=old_pointer),
                     net(step("open", {"datestamp": d1}, base_url=G, cache_dir="${cache}", mode="eager", auto_update=True, update_interval=1)),
                     drv("server_rules", rules=[]), drv("sleep", s=2.5),
                     # the first query after the interval switches the release (as update/auto): OTC-T-0021 is gone in .2
                     step("station", {"station": None}, station_id="OTC-T-0021"),
                     step("release_metadata", {"datestamp": d2}),
                     step("release_files", {"files": info2["files"]}), vfiles(*EAGER)], requires=["fs", "eager"]))
    # an older or other writer left a row for OTC_{D}.sha256, or for a file that is gone: the next writer drops it
    sums_row = {"sha256": hashlib.sha256((FIXTURES / "good" / n_sums).read_bytes()).hexdigest(), "size": size(n_sums), "url": None}
    out.append(case("cache/dr100-sha256-row-dropped", "a .verified that an older writer left with a row for OTC_{D}.sha256: a pinned stream open that adds the .jsonl writes no such row, and release.files does not list it (DR100)", "4.3.1, 5.4",
                    [pin("eager"), drv("json_set", path=f"{r2}/.verified", pointer=f"/files/{n_sums}", value=sums_row),
                     drv("restart_runner"), pin("stream"), vfiles(n_json, n_jsonl, n_meta), rfiles(n_json, n_jsonl, n_meta)],
                    requires=["fs", "stream", "eager"]))
    gz_row = {"sha256": shas[n_gz], "size": size(n_gz), "url": None}
    out.append(case("cache/dr100-absent-file-row-dropped", "a .verified with a row for a file that is not in the release directory (the .json.gz): a pinned stream open that adds the .jsonl writes no row for it (DR100)", "4.3.1, 5.4",
                    [pin("eager"), drv("json_set", path=f"{r2}/.verified", pointer=f"/files/{n_gz}", value=gz_row),
                     drv("restart_runner"), pin("stream"), vfiles(n_json, n_jsonl, n_meta), rfiles(n_json, n_jsonl, n_meta)],
                    requires=["fs", "stream", "eager"]))
    out.append(case("cache/dr100-stale-rows-dropped-stream", "a .verified with a row for OTC_{D}.sha256 and one for a file that is not there (the .json.gz), and the .jsonl gone: the pinned stream open that downloads the .jsonl again writes neither row (DR100)", "4.3.1, 5.4",
                    [pin("stream"), drv("json_set", path=f"{r2}/.verified", pointer=f"/files/{n_sums}", value=sums_row),
                     drv("json_set", path=f"{r2}/.verified", pointer=f"/files/{n_gz}", value=gz_row),
                     drv("delete", path=f"{r2}/{n_jsonl}"), drv("restart_runner"), pin("stream"), vfiles(*STREAM), rfiles(*STREAM)],
                    requires=["fs", "stream"]))
    out.append(case("cache/dr100-null-sha-row-dropped", "a .verified whose row for the stored .json has a null sha256 (that file is not verified): a pinned stream open that adds the .jsonl writes no row for the .json (DR100)", "4.3.1, 5.4",
                    [pin("eager"), drv("json_set", path=f"{r2}/.verified", pointer=f"/files/{n_json}/sha256", value=None),
                     drv("restart_runner"), pin("stream"), vfiles(*STREAM), rfiles(*STREAM)],
                    requires=["fs", "stream", "eager"]))
    # the reader rule: a null or an absent size makes .verified malformed (B10, C4)
    both = [net(step("open", {"datestamp": d1}, release=d1, base_url=G, cache_dir="${cache}", mode="stream")), pin("stream"),
            drv("restart_runner")]
    no_size = {"files": {n_jsonl: {"sha256": shas[n_jsonl], "url": None}, n_meta: {"sha256": shas[n_meta], "size": size(n_meta), "url": None}},
               "datestamp": d2, "verified_at": "2099-12-31T20:00:00Z", "by": "opentideconstants-conformance/1.0"}
    for label, bad in (("null", drv("json_set", path=f"{r2}/.verified", pointer=f"/files/{n_jsonl}/size", value=None)),
                       ("absent", drv("write", path=f"{r2}/.verified", text=json.dumps(no_size, sort_keys=True)))):
        out.append(case(f"cache/dr100-{label}-size-offline", f"offline, a row of the newest .verified has a {label} size: .verified is malformed, so that release is not a candidate (a pinned open is offline_unavailable, cached_releases leaves it out), the older one loads, and nothing is deleted (B10, C4)", "5.4",
                        both + [bad, drv("server_stop"), drv("clear_log"),
                                net(step("open", err("offline_unavailable"), release=d2, base_url=G, cache_dir="${cache}", mode="stream", offline=True)),
                                net(step("open", {"loaded_from": "cache", "datestamp": d1}, base_url=G, cache_dir="${cache}", mode="stream", offline=True)),
                                drv("assert_files", dir=r2, present=[".verified", n_jsonl, n_meta]),
                                drv("assert_requests", source="any", count=0)],
                        requires=["fs", "stream"]))
        out.append(case(f"cache/dr100-{label}-size-pinned-online", f"online, a row of a pinned release's .verified has a {label} size: the release is downloaded again, and the new .verified has real sizes (B10, C4)", "5.2, 5.4",
                        [pin("stream"), drv("restart_runner"), bad, drv("clear_log"), pin("stream"),
                         drv("assert_requests", match=r"/good/OTC_20991231\.2\.jsonl$", min=1), vfiles(*STREAM)],
                        requires=["fs", "stream"]))
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
                    [open_latest_no_cache(G),
                     dl({"paths": default_files}, release=d2, to=B),
                     drv("assert_files", dir=B, exactly=default_files)] + same(default_files) +
                    [step("open", {"loaded_from": "file", "datestamp": d2}, file=f"{B}/OTC_{d2}.jsonl"),
                     step("verify", {"verified": True})], requires=[]))
    out.append(case("download/latest-default", "download with no release resolves latest through the pointer", "4.3.2",
                    [open_latest_no_cache(G), dl({"paths": default_files}, to=B), drv("assert_files", dir=B, exactly=default_files)], requires=[]))
    out.append(case("download/identical", "download-identical: a second download writes nothing and returns an empty list", "4.3.2, 7.1",
                    [open_latest_no_cache(G), dl({"paths": default_files}, release=d2, to=B), dl({"paths": []}, release=d2, to=B),
                     drv("assert_files", dir=B, exactly=default_files)], requires=[]))
    out.append(case("download/mismatch", "download-mismatch: a changed file fails with file_exists and stays; overwrite repairs it", "4.3.2, 7.1",
                    [open_latest_no_cache(G), dl({"paths": default_files}, release=d2, to=B),
                     drv("corrupt", path=f"{B}/OTC_{d2}.jsonl", offset=10),
                     dl(err("file_exists", path={"$contains": f"OTC_{d2}.jsonl"}), release=d2, to=B),
                     drv("assert_sha256", path=f"{B}/OTC_{d2}.jsonl", equals=f"{FIX}/good/OTC_{d2}.jsonl", negate=True),
                     dl({"paths": [f"OTC_{d2}.jsonl"]}, release=d2, to=B, overwrite=True)] + same(default_files), requires=[]))
    out.append(case("download/conflict-changes-nothing", "a conflict is found before any write: a missing file is not written either", "4.3.2",
                    [open_latest_no_cache(G), dl({"paths": default_files}, release=d2, to=B),
                     drv("corrupt", path=f"{B}/OTC_{d2}.jsonl", offset=10), drv("delete", path=f"{B}/OTC_{d2}.meta.json"),
                     dl(err("file_exists"), release=d2, to=B),
                     drv("assert_files", dir=B, exactly=[f"OTC_{d2}.jsonl", f"OTC_{d2}.sha256"])], requires=[]))
    out.append(case("download/from-cache", "download-from-cache: the cache holds the release, the server is stopped, no request", "4.3.2, 7.1",
                    [open_latest_no_cache(G, mode="stream"), drv("server_stop"), drv("clear_log"),
                     dl({"paths": default_files}, release=d2, to=B), drv("assert_requests", source="any", count=0)] + same(default_files), requires=["stream"]))
    out.append(case("download/bad-checksum", "download-bad-checksum: the server sends a file with a wrong SHA-256; checksum_mismatch and the file is not in the folder", "4.3.2, 7.1",
                    [step("open", {"loaded_from": "file"}, file=f"{FIX}/good/OTC_{d2}.jsonl", base_url=f"{SRV}/bad/wrong-sha256/", cache_dir="${cache}"),
                     dl(err("checksum_mismatch"), release=d1, to=B),
                     drv("assert_files", dir=B, absent=[f"OTC_{d1}.jsonl"], no_tmp=True, may_be_missing=True)], requires=["fs"]))
    out.append(case("download/formats", "download every format: json, json.gz, jsonl, plus meta and sha256", "4.3.2",
                    [open_latest_no_cache(G),
                     dl({"paths": sorted([f"OTC_{d2}.json", f"OTC_{d2}.json.gz"] + default_files)}, release=d2, to=B, formats=["json", "json.gz", "jsonl"]),
                     drv("assert_files", dir=B, exactly=sorted([f"OTC_{d2}.json", f"OTC_{d2}.json.gz"] + default_files))] +
                    same([f"OTC_{d2}.json", f"OTC_{d2}.json.gz"]), requires=[]))
    # spec 4.3.2: OTC_{D}.meta.json is always written, also when the formats name no .jsonl
    for fmt, ext in [("json", "json"), ("json.gz", "json.gz")]:
        only = sorted([f"OTC_{d2}.{ext}", f"OTC_{d2}.meta.json", f"OTC_{d2}.sha256"])
        out.append(case(f"download/{fmt.replace('.', '-')}-only-writes-meta", f"download of {fmt} only: writes the {fmt} file, OTC_{{D}}.meta.json and OTC_{{D}}.sha256", "4.3.2",
                        [open_latest_no_cache(G),
                         dl({"paths": only}, release=d2, to=B, formats=[fmt]),
                         drv("assert_files", dir=B, exactly=only, no_tmp=True)] + same(only), requires=[]))
    out.append(case("download/invalid-format", "an unknown format: invalid_argument", "4.3.2",
                    [open_latest_no_cache(G), dl(err("invalid_argument"), release=d2, to=B, formats=["csv"])], requires=[]))
    out.append(case("download/invalid-release", "a bad datestamp: invalid_argument", "4.3.2",
                    [open_latest_no_cache(G), dl(err("invalid_argument"), release="2099", to=B)], requires=[]))
    out.append(case("download/not-found", "a datestamp the server does not have: release_not_found", "4.3.2",
                    [open_latest_no_cache(G), dl(err("release_not_found"), release="20991230", to=B)], requires=[]))
    # CR D22 (spec 4.3.2): download of latest honours on_network_error like opening a client
    ptr500 = drv("server_rules", rules=[{"match": r"/good/OTC_latest(-f1)?\.json$", "action": "status", "status": 500}])
    out.append(case("download/latest-network-error-use-cache", "download of latest when the pointer answers 500, with use_cache and a cached release: writes the newest cached release", "4.3.2, 5.2",
                    [net(step("open", {"loaded_from": "download", "datestamp": d2}, base_url=G, cache_dir="${cache}")), ptr500,
                     dl({"paths": default_files}, to=B), drv("assert_files", dir=B, exactly=default_files, no_tmp=True)] + same(default_files),
                    requires=["fs"], timeout_s=90))
    out.append(case("download/latest-network-error-raise", "download of latest when the pointer answers 500, with on_network_error raise: network error, and nothing is written", "4.3.2, 5.2",
                    [net(step("open", {"loaded_from": "download", "datestamp": d2}, base_url=G, cache_dir="${cache}", on_network_error="raise")), ptr500,
                     dl(err("network"), to=B), drv("assert_files", dir=B, absent=default_files, no_tmp=True, may_be_missing=True)],
                    requires=["fs"], timeout_s=90))
    out.append(case("download/latest-network-error-no-cache", "download of latest when the pointer answers 500 and the cache is empty: network error even with use_cache", "4.3.2, 5.2",
                    [step("open", {"loaded_from": "file"}, file=f"{FIX}/good/OTC_{d2}.jsonl", base_url=G, cache_dir="${cache}"), ptr500,
                     dl(err("network"), to=B), drv("assert_files", dir=B, absent=default_files, no_tmp=True, may_be_missing=True)],
                    requires=["fs"], timeout_s=90))
    # CR2 DR17 (spec 4.3.2): all or nothing. A directory where OTC_{D}.meta.json goes makes its rename fail after the
    # .jsonl (overwrite: true, so its original is set aside) is renamed in; the original .jsonl comes back
    out.append(case("download/rename-failure-restores", "a rename that fails after another file was renamed in: io error, the replaced original is restored, and no temporary file is left", "4.3.2",
                    [open_latest_no_cache(G), dl({"paths": default_files}, release=d2, to=B),
                     drv("corrupt", path=f"{B}/OTC_{d2}.jsonl", offset=10),
                     drv("delete", path=f"{B}/OTC_{d2}.meta.json"), drv("mkdir", path=f"{B}/OTC_{d2}.meta.json"),
                     dl(err("io"), release=d2, to=B, overwrite=True),
                     drv("assert_sha256", path=f"{B}/OTC_{d2}.jsonl", equals=f"{FIX}/good/OTC_{d2}.jsonl", negate=True),
                     drv("assert_files", dir=B, exactly=default_files, no_tmp=True)] +
                    same([f"OTC_{d2}.sha256"]), requires=["fs"]))
    # offline through the environment: offline=True together with file is invalid_argument (CR D31), and the
    # variable is not an option, so it does not conflict (spec 4.2)
    ptr_fail = drv("server_rules", rules=[{"match": r"/good/OTC_latest(-f1)?\.json$", "action": "status", "status": 503}])
    out.append(case("download/latest-network-error-use-cache-stream", "download with no release when the pointer answers 503, with the release cached and on_network_error use_cache (the default): the newest cached readable release is written (D22)", "4.3.2",
                    [open_latest_step(G, mode="stream"), ptr_fail,
                     dl({"paths": default_files}, to=B),
                     drv("assert_files", dir=B, exactly=default_files)] + same(default_files),
                    requires=["fs", "stream"], timeout_s=90))
    out.append(case("download/latest-network-error-raise-stream", "the same with on_network_error raise: network error, and nothing is written (D22)", "4.3.2",
                    [open_latest_step(G, mode="stream", on_network_error="raise"), ptr_fail,
                     dl(err("network"), to=B),
                     drv("assert_files", dir=B, exactly=[], may_be_missing=True)],
                    requires=["fs", "stream"], timeout_s=90))
    out.append(case("download/offline-not-cached", "offline, a release not in the cache: offline_unavailable", "4.3.2",
                    [step("open", {"loaded_from": "file"}, file=f"{FIX}/good/OTC_{d2}.jsonl", base_url=G, cache_dir="${cache}"),
                     dl(err("offline_unavailable"), release=d1, to=B)], requires=["fs"], env={"OPENTIDECONSTANTS_OFFLINE": "1"}))
    return out + download_cached_sha256_cases() + download_no_json_row_cases()


def download_no_json_row_cases():
    """download with formats ["json"] from a release whose .sha256 lists the .json.gz but not the .json:
    checksum_mismatch "not listed", as for an eager open (DR15), and not release_not_found (CR2 DR42, orchestrator
    decision 2026-10-09). Nothing is written."""
    NJ = f"{SRV}/bad/sha256-no-json-row/"
    d = "20991231"
    B = "${tmp}/bundle"
    not_listed = {**err("checksum_mismatch"), "error_message": {"$contains": "not listed"}}
    client = step("open", {"loaded_from": "file"}, file=f"{FIX}/good/OTC_20991231.2.jsonl", base_url=NJ, cache_dir="${cache}")
    nothing = drv("assert_files", dir=B, exactly=[], may_be_missing=True)

    def dl(expect, **kw):
        return net(step("download", expect, **kw), fs=True)

    gz = [f"OTC_{d}.json.gz", f"OTC_{d}.jsonl", f"OTC_{d}.meta.json", f"OTC_{d}.sha256"]
    return [case("download/no-json-row", "download of json from bad/sha256-no-json-row (.json.gz listed, .json not), pinned and latest: checksum_mismatch \"not listed\", nothing is written; json.gz and jsonl download (CR2 DR42)", "4.3.2, 5.3, 4.8",
                 [client, dl(not_listed, release=d, to=B, formats=["json"]), nothing,
                  dl(not_listed, to=B, formats=["json", "jsonl"]), nothing,
                  dl({"paths": gz}, release=d, to=B, formats=["json.gz", "jsonl"]),
                  drv("assert_files", dir=B, exactly=gz, no_tmp=True)],
                 requires=["fs"])]


def download_cached_sha256_cases():
    """download reuses the cached OTC_{D}.sha256 of a verified release only when it can be trusted (CR2 DR40,
    orchestrator decision 2026-10-09): when the pointer lists the .sha256, its digest must equal the pointer's, and a
    cached copy that cannot be read or parsed is fetched again (offline: offline_unavailable)."""
    out = []
    G = f"{SRV}/good/"
    d2 = "20991231.2"
    B = "${tmp}/bundle"
    sp = f"${{cache}}/v1/releases/{d2}/OTC_{d2}.sha256"
    files = [f"OTC_{d2}.jsonl", f"OTC_{d2}.meta.json", f"OTC_{d2}.sha256"]
    rows = sha256_rows("good", d2)
    # well formed, and the rows of the files download writes are right: only the .json row differs from the release
    other = "".join(f"{'0' * 64 if n == f'OTC_{d2}.json' else h}  {n}\n" for n, h in sorted(rows.items()))
    # does not parse: it names a file twice, which is invalid_release in every SDK (CR2 DR14)
    twice = "".join(f"{h}  {n}\n" for n, h in sorted(rows.items())) + f"{rows[f'OTC_{d2}.jsonl']}  OTC_{d2}.jsonl\n"

    def dl(expect, **kw):
        return net(step("download", expect, **kw), fs=True)

    same = [drv("assert_sha256", path=f"{B}/{n}", equals=f"{FIX}/good/{n}") for n in files]
    cached = [open_latest_step(G, mode="stream")]
    # the client that downloads is opened on a file, so its open never reads the cached release (C opens a cached
    # release against its cached .sha256)
    file_client = step("open", {"loaded_from": "file"}, file=f"{FIX}/good/OTC_{d2}.jsonl", base_url=G, cache_dir="${cache}")
    out.append(case("download/cached-sha256-not-the-pointers", "download of latest: the cached OTC_{D}.sha256 is well formed but its digest is not the pointer's: it is fetched again, and the files written are the release's", "4.3.2, 5.2",
                    cached + [drv("write", path=sp, text=other), file_client,
                              dl({"paths": files}, to=B), drv("assert_files", dir=B, exactly=files, no_tmp=True)] + same,
                    requires=["fs", "stream"]))
    out.append(case("download/cached-sha256-malformed", "download of latest and of a pinned release: the cached OTC_{D}.sha256 does not parse (it names a file twice): it is fetched again, and the files written are the release's", "4.3.2, 5.2",
                    cached + [drv("write", path=sp, text=twice), file_client,
                              dl({"paths": files}, to=B), drv("assert_files", dir=B, exactly=files, no_tmp=True)] + same +
                    [dl({"paths": files}, release=d2, to="${tmp}/pinned")] +
                    [drv("assert_sha256", path=f"${{tmp}}/pinned/{n}", equals=f"{FIX}/good/{n}") for n in files],
                    requires=["fs", "stream"]))
    out.append(case("download/cached-sha256-unreadable", "download of latest: the cached OTC_{D}.sha256 cannot be read: it is fetched again, and the files written are the release's", "4.3.2, 5.2",
                    cached + [file_client, drv("chmod", path=sp, mode="000"),
                              dl({"paths": files}, to=B), drv("chmod", path=sp, mode="644"),
                              drv("assert_files", dir=B, exactly=files, no_tmp=True)] + same,
                    requires=["fs", "stream"]))
    out.append(case("download/cached-sha256-malformed-offline", "offline, the cached OTC_{D}.sha256 does not parse (it names a file twice): download cannot fetch it again: offline_unavailable, and nothing is written", "4.3.2, 5.2",
                    cached + [drv("write", path=sp, text=twice), drv("server_stop"),
                              drv("restart_runner", env={"OPENTIDECONSTANTS_OFFLINE": "1"}),
                              step("open", {"loaded_from": "file"}, file=f"{FIX}/good/OTC_{d2}.jsonl", cache_dir="${cache}"),
                              dl(err("offline_unavailable"), release=d2, to=B),
                              drv("assert_files", dir=B, exactly=[], may_be_missing=True)],
                    requires=["fs", "stream"]))
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
    # the writer's .verified rows: the files its pinned stream open stored, with their real sizes (CR3 DR100)
    sums = sha256_rows("good", d)
    stored = [{"name": n, "url": {"$any_of": [None, G + n]}, "size": (FIXTURES / "good" / n).stat().st_size, "sha256": sums[n]}
              for n in (f"OTC_{d}.jsonl", f"OTC_{d}.meta.json")]
    out.append(case("cross/cache-offline-stream", "one SDK fills the cache in stream mode; another opens it offline (server stopped) and gets the same answers, with no request", "5.4, 5.5, 6.2",
                    fill + offline + [
                        as_("reader", step("open", {"loaded_from": "cache", "datestamp": d}, release=d, cache_dir="${cache}", offline=True, mode="stream")),
                        as_("reader", step("verify", {"verified": True})),
                        as_("reader", step("release_files", {"files": stored}))] + queries + [
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
                            drv("assert_json", path=idx, match={f"/stations/{pos}/country": "ZZ"}),
                            drv("copy", files=[idx], to="${tmp}/index-copy")] + offline + [
                        as_("reader", step("open", {"loaded_from": "cache", "datestamp": d}, release=d, cache_dir="${cache}", offline=True, mode="stream")),
                        as_("reader", step("stations", {"station_ids": ["OTC-T-0011"]}, country="ZZ")),
                        as_("reader", step("close")),
                        drv("assert_sha256", path=idx, equals="${tmp}/index-copy/index-v1.json"),
                        no_requests],
                    roles=roles))
    out.append(case("cross/index-stale", "a stale stream index (its jsonl_sha256 does not match) is ignored, rebuilt and rewritten", "6.2",
                    fill + [drv("json_set", path=idx, pointer=f"/stations/{pos}/country", value="ZZ"),
                            drv("json_set", path=idx, pointer="/jsonl_sha256", value="0" * 64),
                            drv("assert_json", path=idx, match={f"/stations/{pos}/country": "ZZ", "/jsonl_sha256": "0" * 64})] + offline + [
                        as_("reader", step("open", {"loaded_from": "cache", "datestamp": d}, release=d, cache_dir="${cache}", offline=True, mode="stream")),
                        as_("reader", step("stations", {"station_ids": []}, country="ZZ")),
                        as_("reader", step("stations", {"station_ids": [x["station_id"] for x in apply_filters(R2, R2.active, {"country": country})]}, country=country)),
                        as_("reader", step("close")),
                        drv("assert_index", path=idx, jsonl=jl, datestamp=d),
                        no_requests],
                    roles=roles))
    out.append(case("cross/index-other-version", "an index with another index_version is stale: rebuilt and rewritten", "6.2",
                    fill + [drv("json_set", path=idx, pointer=f"/stations/{pos}/country", value="ZZ"),
                            drv("json_set", path=idx, pointer="/index_version", value=2),
                            drv("assert_json", path=idx, match={f"/stations/{pos}/country": "ZZ", "/index_version": 2})] + offline + [
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
    out += cross_rules(R2, fill, offline, no_requests, roles, idx, jl, rdir)
    out += cross_r2_pk07(R2, fill, offline, no_requests, roles, idx, jl, rdir)
    return out


def reference_index(jsonl, datestamp):
    """The reference index-v1.json of a .jsonl file (conformance/stream_index.py)."""
    sys.path.insert(0, str(ROOT))
    try:
        import stream_index
    finally:
        sys.path.pop(0)
    return stream_index.build(jsonl, datestamp)


def cross_r2_pk07(R2, fill, offline, no_requests, roles, idx, jl, rdir):
    """Cross-SDK cases of review round 2, package PK-R2-07: the stream index path agrees with the full pass
    (spec 6.2; CR2 DR9, DR10)."""
    out = []
    d = R2.datestamp
    ref = reference_index(FIXTURES / "good" / f"OTC_{d}.jsonl", d)["stations"]
    reader_open = as_("reader", step("open", {"loaded_from": "cache", "datestamp": d}, release=d, cache_dir="${cache}", offline=True, mode="stream"))
    # DR9: an entry that starts at the previous offset + the previous length overlaps nothing in bytes, but it
    # leaves no room for the line end, so it is not the start of a line. Every reader finds the index stale.
    a, b = ref[0], ref[1]
    out.append(case("cross/index-overlap", "an index entry starts at the previous offset + the previous length (no byte for the line end): the index is stale, so it is rebuilt, and the query is right (CR2 DR9)", "6.2",
                    fill + [drv("json_set", path=idx, pointer="/stations/1/offset", value=a["offset"] + a["length"])] + offline + [
                        reader_open,
                        as_("reader", step("station", {"station": enc_station(R2, R2.by_id[b["station_id"]])}, station_id=b["station_id"])),
                        as_("reader", step("close")),
                        drv("assert_index", path=idx, jsonl=jl, datestamp=d), no_requests],
                    roles=roles))
    # DR10: an integer key written as a number with an integral value (12.0) is that integer. The index stays
    # fresh: a marked entry shows in the reader's answers, a line is read through the float offset, and the
    # file is not rewritten.
    jsize = (FIXTURES / "good" / f"OTC_{d}.jsonl").stat().st_size
    pos = [s["station_id"] for s in R2.doc["stations"]].index("OTC-T-0011")
    out.append(case("cross/index-float-ints", "index_version, jsonl_size and an entry's offset and length written as 1.0, 25846.0, ...: the index is fresh, so it is used and not rewritten (CR2 DR10)", "6.2",
                    fill + [drv("json_set", path=idx, pointer="/index_version", value=1.0),
                            drv("json_set", path=idx, pointer="/jsonl_size", value=float(jsize)),
                            drv("json_set", path=idx, pointer="/stations/0/offset", value=float(a["offset"])),
                            drv("json_set", path=idx, pointer="/stations/0/length", value=float(a["length"])),
                            drv("json_set", path=idx, pointer=f"/stations/{pos}/country", value="ZZ"),
                            drv("copy", files=[idx], to="${tmp}/index-copy")] + offline + [
                        reader_open,
                        as_("reader", step("stations", {"station_ids": ["OTC-T-0011"]}, country="ZZ")),
                        as_("reader", step("station", {"station": enc_station(R2, R2.by_id[a["station_id"]])}, station_id=a["station_id"])),
                        as_("reader", step("close")),
                        drv("assert_sha256", path=idx, equals="${tmp}/index-copy/index-v1.json"), no_requests],
                    roles=roles))
    # An entry whose sets disagree with its line (a convention that resolves, but is not the line's; a
    # constituent left out): reading the line is invalid_release naming index-v1.json, which is deleted, and
    # the next open rebuilds it.
    bad_index = {**err("invalid_release"), "error_message": {"$contains": "index-v1.json"}}
    conv = a["sets"][0]["convention_id"]
    other = next(c["convention_id"] for c in R2.doc["conventions"] if c["convention_id"] != conv)
    for label, title, pointer, value in [
            ("index-set-mismatch", f"an entry's sets[0].convention_id is {other}, the line's is {conv}", "/stations/0/sets/0/convention_id", other),
            ("index-constituent-dropped", "an entry's sets[0] leaves out the last constituent name of the line", "/stations/0/sets/0/constituents", a["sets"][0]["constituents"][:-1])]:
        out.append(case(f"cross/{label}", f"{title} (the index is still fresh): reading the line is invalid_release naming index-v1.json, which is deleted; the next open rebuilds it (CR D4)", "6.2",
                        fill + [drv("json_set", path=idx, pointer=pointer, value=value)] + offline + [
                            reader_open,
                            as_("reader", step("station", bad_index, station_id=a["station_id"])),
                            drv("assert_files", dir=rdir, present=[".verified"], absent=["index-v1.json"]),
                            reader_open,
                            as_("reader", step("station", {"station": enc_station(R2, R2.by_id[a["station_id"]])}, station_id=a["station_id"])),
                            as_("reader", step("close")),
                            drv("assert_index", path=idx, jsonl=jl, datestamp=d), no_requests],
                        roles=roles))
    msize = (FIXTURES / "good" / f"OTC_{d}.meta.json").stat().st_size
    out.append(case("cross/verified-float-size", "a .verified whose file sizes are written as 25846.0: the release is cached, and the reader opens it offline (CR2 DR10)", "5.4",
                    fill + [drv("json_set", path=f"{rdir}/.verified", pointer=f"/files/OTC_{d}.jsonl/size", value=float(jsize)),
                            drv("json_set", path=f"{rdir}/.verified", pointer=f"/files/OTC_{d}.meta.json/size", value=float(msize))] + offline + [
                        reader_open,
                        as_("reader", step("station_count", {"station_count": len(R2.active)})),
                        as_("reader", step("cached_releases", {"datestamps": [d]})), no_requests],
                    roles=roles))
    out += cross_r2_pk09(R2, roles, rdir)
    return out


def cross_r2_pk09(R2, roles, rdir):
    """Cross-SDK case of review round 2, package PK-R2-09: a null version DOI never erases a known one (spec 4.3,
    5.4; CR2 DR11)."""
    d = R2.datestamp
    G = f"{SRV}/good/"
    vdoi = pointer_entry("good", d)["zenodo_version_doi"]
    null_doi = drv("server_rules", rules=[{"match": r"/good/OTC_latest(-f1)?\.json$", "action": "json", "file": "good/OTC_latest-f1.json",
                                          "pointer": "", "set": {"/zenodo_version_doi": None}}])
    return [case("cross/verified-doi-null-pointer", "the writer caches latest with its version DOI; then the pointer names the same release with zenodo_version_doi null: the reader keeps the known DOI in the session (open, check_for_update) and in .verified (CR2 DR11)", "4.3, 5.4",
                 [as_("writer", step("open", {"loaded_from": "download", "datestamp": d}, base_url=G, cache_dir="${cache}", mode="stream")),
                  as_("writer", step("release_metadata", {"zenodo_version_doi": vdoi})),
                  as_("writer", step("close")),
                  null_doi,
                  as_("reader", step("open", {"loaded_from": "cache", "datestamp": d}, base_url=G, cache_dir="${cache}", mode="stream")),
                  as_("reader", step("release_metadata", {"zenodo_version_doi": vdoi})),
                  as_("reader", step("check_for_update", {"release": None})),
                  as_("reader", step("release_metadata", {"zenodo_version_doi": vdoi})),
                  as_("reader", step("close")),
                  drv("assert_json", path=f"{rdir}/.verified", match={"zenodo_version_doi": vdoi}),
                  as_("writer", step("open", {"loaded_from": "cache", "datestamp": d}, cache_dir="${cache}", offline=True, mode="stream")),
                  as_("writer", step("release_metadata", {"zenodo_version_doi": vdoi}))],
                 roles=roles)]


def cross_rules(R2, fill, offline, no_requests, roles, idx, jl, rdir):
    """Cross-SDK cases for the rules of review round 1 (PK04, PK05; B1-5, B1-6, B1-2, V4)."""
    out = []
    d = R2.datestamp
    G = f"{SRV}/good/"
    vdoi = pointer_entry("good", d)["zenodo_version_doi"]
    reader_open = as_("reader", step("open", {"loaded_from": "cache", "datestamp": d}, release=d, cache_dir="${cache}", offline=True, mode="stream"))
    ids = [s["station_id"] for s in R2.doc["stations"]]
    out.append(case("cross/index-station-id-swapped", "two index entries trade station ids (the index is still fresh and in bounds): a query for one reads the other's line, which must be invalid_release, never the wrong station (D4)", "6.2",
                    fill + [drv("json_set", path=idx, pointer="/stations/0/station_id", value=ids[1]),
                            drv("json_set", path=idx, pointer="/stations/1/station_id", value=ids[0]),
                            drv("assert_json", path=idx, match={"/stations/0/station_id": ids[1], "/stations/1/station_id": ids[0]})] + offline + [
                        reader_open,
                        as_("reader", step("station", {**err("invalid_release"), "error_message": {"$contains": "index-v1.json"}}, station_id=ids[0])),
                        drv("assert_files", dir=rdir, present=[".verified"], absent=["index-v1.json"]),
                        no_requests],
                    roles=roles))
    jsize = (FIXTURES / "good" / f"OTC_{d}.jsonl").stat().st_size
    last = ids[-1]
    out.append(case("cross/index-offset-past-eof", "an index entry whose offset is past the end of the .jsonl: the index is stale, so it is rebuilt, and the query is right (D4)", "6.2",
                    fill + [drv("json_set", path=idx, pointer=f"/stations/{len(ids) - 1}/offset", value=jsize + 10),
                            drv("assert_json", path=idx, match={f"/stations/{len(ids) - 1}/offset": jsize + 10})] + offline + [
                        reader_open,
                        as_("reader", step("tombstone" if last not in R2.by_id else "station",
                                           {"tombstone": enc_tombstone(R2.tomb_by_id[last])} if last not in R2.by_id else {"station": enc_station(R2, R2.by_id[last])},
                                           station_id=last)),
                        as_("reader", step("close")),
                        drv("assert_index", path=idx, jsonl=jl, datestamp=d), no_requests],
                    roles=roles))
    pos = ids.index("OTC-T-0011")
    out.append(case("cross/index-datestamp-mismatch", "an index whose datestamp is not the release's is stale: it is ignored and rebuilt", "6.2",
                    fill + [drv("json_set", path=idx, pointer=f"/stations/{pos}/country", value="ZZ"),
                            drv("json_set", path=idx, pointer="/datestamp", value="20991230"),
                            drv("assert_json", path=idx, match={f"/stations/{pos}/country": "ZZ", "/datestamp": "20991230"})] + offline + [
                        reader_open,
                        as_("reader", step("stations", {"station_ids": []}, country="ZZ")),
                        as_("reader", step("close")),
                        drv("assert_index", path=idx, jsonl=jl, datestamp=d), no_requests],
                    roles=roles))
    V = f"{SRV}/values/"
    vd = "20991231.2"
    vdir = f"${{cache}}/v1/releases/{vd}"
    # "da" is after the NUL: a reader that cut the name at the NUL ("Me") does not find it (PK-R2-08, R2-149)
    RV = Rel("values", vd)
    out.append(case("cross/index-nul-name", "a station name with a NUL inside: the writer's stream index keeps it, and the reader's search finds the station by the part after the NUL", "6.2, 4.4.1",
                    [as_("writer", step("open", {"loaded_from": "download", "datestamp": vd}, release=vd, base_url=V, cache_dir="${cache}", mode="stream")),
                     as_("writer", step("search", {"station_ids": search(RV, "Me\u0000da")}, name="Me\u0000da")),
                     as_("writer", step("search", {"station_ids": search(RV, "da")}, name="da")),
                     as_("writer", step("close")),
                     drv("assert_index", path=f"{vdir}/index-v1.json", jsonl=f"{vdir}/OTC_{vd}.jsonl", datestamp=vd)] + offline + [
                        as_("reader", step("open", {"loaded_from": "cache", "datestamp": vd}, release=vd, cache_dir="${cache}", offline=True, mode="stream")),
                        as_("reader", step("search", {"station_ids": search(RV, "Me\u0000da")}, name="Me\u0000da")),
                        # past the NUL: a reader that cuts the name at the NUL ("Me") finds nothing (R2-149)
                        as_("reader", step("search", {"station_ids": search(RV, "da")}, name="da")), no_requests],
                    roles=roles))
    # A NUL inside alias ids and set_ids (PK-R2-08, DR33): the writer's index keeps every string in full, the
    # reader uses that fresh index as it is (no rebuild, spec 6.2), and no lookup matches the part before a NUL.
    # Each SDK answers from the .jsonl (the writer), from another SDK's index (the reader) and from its own index
    # (the writer again).
    RN = Rel("values-nul", d)
    N = f"{SRV}/values-nul/"
    s1n = RN.by_id["OTC-T-0001"]

    def nul_case(cid, title, reads):
        def ask(who):
            return [as_(who, step(op, expect, **args)) for op, expect, args in reads]
        return case(cid, title, "6.2, 4.4, 6.4",
                    [as_("writer", step("open", {"loaded_from": "download", "datestamp": d}, release=d, base_url=N, cache_dir="${cache}", mode="stream"))]
                    + ask("writer") + [
                        as_("writer", step("close")),
                        drv("assert_index", path=idx, jsonl=jl, datestamp=d),
                        drv("copy", files=[idx], to="${tmp}/index-copy")] + offline + [
                        as_("reader", step("open", {"loaded_from": "cache", "datestamp": d}, release=d, cache_dir="${cache}", offline=True, mode="stream"))]
                    + ask("reader") + [
                        as_("reader", step("close")),
                        drv("assert_sha256", path=idx, equals="${tmp}/index-copy/index-v1.json"),
                        as_("writer", step("open", {"loaded_from": "cache", "datestamp": d}, release=d, cache_dir="${cache}", offline=True, mode="stream"))]
                    + ask("writer") + [
                        as_("writer", step("close")),
                        drv("assert_sha256", path=idx, equals="${tmp}/index-copy/index-v1.json"), no_requests],
                    roles=roles)
    out.append(nul_case("cross/index-nul-alias", "alias ids with a NUL inside: the station reads them in full, and the part before the NUL finds no station, from the .jsonl and from any SDK's stream index", [
        ("station", {"station": enc_station(RN, s1n)}, {"station_id": "OTC-T-0001"}),
        ("station_by_alias", {"station_id": None}, {"system": "xtide", "alias_id": "San"}),
        ("station_by_alias", {"station_id": None}, {"system": "gesla", "alias_id": "test-gesla"}),
        ("station_by_alias", {"station_id": "OTC-T-0001"}, {"system": "gesla", "alias_id": "test-gesla-0001b"})]))
    out.append(nul_case("cross/index-nul-set-id", "set_ids with a NUL inside (the recommended one too): the sets read them in full, and the part before the NUL is no set, from the .jsonl and from any SDK's stream index", [
        ("recommended_set", {"set_id": RN.rec_set(s1n)["set_id"]}, {"station_id": "OTC-T-0001"}),
        ("constant_set", {"set": None}, {"station_id": "OTC-T-0001", "set_id": "OTC-T-0001/no"}),
        ("constant_set", {"set": None}, {"station_id": "OTC-T-0001", "set_id": "OTC-T-0001/gesla"}),
        ("stations", {"station_ids": [s["station_id"] for s in apply_filters(RN, RN.active, {"source_type": "official"})]}, {"source_type": "official"}),
        ("stations", {"station_ids": [s["station_id"] for s in apply_filters(RN, RN.active, {"kind": "tide", "country": "USA"})]}, {"kind": "tide", "country": "USA"})]))
    latest_writer = [as_("writer", step("open", {"loaded_from": "download", "datestamp": d}, base_url=G, cache_dir="${cache}", mode="stream")),
                     as_("writer", step("release_metadata", {"zenodo_version_doi": vdoi})),
                     as_("writer", step("close"))]
    out.append(case("cross/verified-doi-handoff", "the writer downloads latest (the pointer has a version DOI); the reader opens the cache offline and has the same version DOI (B1-5, D26)", "4.3, 5.4",
                    latest_writer + offline + [
                        as_("reader", step("open", {"loaded_from": "cache", "datestamp": d}, cache_dir="${cache}", offline=True, mode="stream")),
                        as_("reader", step("release_metadata", {"zenodo_version_doi": vdoi})), no_requests],
                    roles=roles))
    out.append(case("cross/verified-doi-preserved", "the reader adds the eager .json to the writer's cached release (a pinned open, no pointer): .verified keeps the version DOI (P12, R73, D26)", "4.3, 5.4",
                    latest_writer + [
                        as_("reader", step("open", {"loaded_from": "cache", "datestamp": d}, release=d, base_url=G, cache_dir="${cache}", mode="eager")),
                        as_("reader", step("close")),
                        drv("assert_json", path=f"{rdir}/.verified", match={"zenodo_version_doi": vdoi}),
                        as_("writer", step("open", {"loaded_from": "cache", "datestamp": d}, cache_dir="${cache}", offline=True, mode="stream")),
                        as_("writer", step("release_metadata", {"zenodo_version_doi": vdoi}))],
                    roles={"writer": ["fs", "fetch", "stream"], "reader": ["fs", "fetch", "eager"]}))
    citation_v = citation(R2, vdoi)
    # a stream-mode writer stores the .jsonl and the .meta.json, and .verified has a row for those only (CR3 DR100)
    stream_rows = {f"OTC_{d}.jsonl": {"$type": "object"}, f"OTC_{d}.meta.json": {"$type": "object"}}
    out.append(case("cross/verified-doi-pinned-writer", "the writer caches a pinned release (no pointer, so no version DOI); the reader opens latest online, gets the cached release (a 304 path or a pointer for the same datestamp) and records the pointer's version DOI in .verified; the writer then has it offline (B1-5, D26, R2-151)", "4.3, 5.4",
                    [as_("writer", step("open", {"loaded_from": "download", "datestamp": d}, release=d, base_url=G, cache_dir="${cache}", mode="stream")),
                     as_("writer", step("close")),
                     as_("reader", step("open", {"loaded_from": "cache", "datestamp": d}, base_url=G, cache_dir="${cache}", mode="stream")),
                     as_("reader", step("release_metadata", {"zenodo_version_doi": vdoi})),
                     as_("reader", step("close")),
                     drv("assert_json", path=f"{rdir}/.verified", match={"zenodo_version_doi": vdoi, "files": stream_rows})] + offline + [
                        as_("writer", step("open", {"loaded_from": "cache", "datestamp": d}, release=d, cache_dir="${cache}", offline=True, mode="stream")),
                        as_("writer", step("verify", {"verified": True})),
                        as_("writer", step("citation", {"citation": citation_v})), no_requests],
                    roles=roles))
    rows = sha256_rows("good", d)
    files_only = {"files": {n: {"sha256": h, "size": (FIXTURES / "good" / n).stat().st_size} for n, h in sorted(rows.items())}}
    out.append(case("cross/verified-keys", "the writer's .verified has the seven keys of D26 (files, verified_at, by, datestamp, format_version, min_reader_version, zenodo_version_doi); a reader opens offline a release whose .verified holds only files (D26, G13)", "5.4",
                    latest_writer + [
                        drv("assert_json", path=f"{rdir}/.verified", match={
                            "files": stream_rows, "verified_at": {"$regex": r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$"},
                            "by": {"$regex": r"^opentideconstants-[a-z]+/\S+$"}, "datestamp": d, "format_version": R2.doc["format_version"],
                            "min_reader_version": R2.doc["release"]["min_reader_version"], "zenodo_version_doi": vdoi}),
                        drv("write", path=f"{rdir}/.verified", text=json.dumps(files_only, indent=1, sort_keys=True) + "\n")] + offline + [
                        reader_open,
                        as_("reader", step("verify", {"verified": True})),
                        as_("reader", step("station_count", {"station_count": len(R2.active)})), no_requests],
                    roles=roles))
    return out


# --------------------------------------------------------------------------- review round 1: cross-SDK rules

# D12 (spec 4.4.1), written out by hand from the rule and not from name_fold.json: each query of the fold root and
# the stations it must find, in rank order. The build checks the table-driven oracle (search) against it, so a fold
# table without a D12 row stops the build instead of being checked against itself (R2-163).
FOLD_D12 = [
    ("hamrun", {}, ["OTC-T-0161"]),                      # Ħamrun: H with stroke -> h
    ("torvik", {}, ["OTC-T-0162"]),                      # Ŧorvik: T with stroke -> t
    ("naliq", {}, ["OTC-T-0163"]),                       # Ŋaliq: eng -> n
    ("kimmik", {}, ["OTC-T-0164"]),                      # ĸimmik: kra -> k
    ("ΠΟΡΟΣ", {"match": "exact"}, ["OTC-T-0165"]),       # Πόρος: final sigma = sigma, accent removed
    ("parallel", {}, ["OTC-T-0166"]),                    # Paral·lel: the middle dot is removed
    ("saint malo", {"match": "exact"}, ["OTC-T-0167"]),  # Saint<NBSP>Malo: NBSP is a space
]


def rules_r2_pk07():
    """PK-R2-07: a line read through a fresh stream index gets the checks of the full pass (spec 6.2, CR D4). A
    cached, verified bad release whose index-v1.json (the reference builder's) is fresh: the open uses the
    index, and the query that reads the bad line is invalid_release naming index-v1.json, which is deleted;
    the next open makes the pass, which fails too."""
    out = []
    d = "20991231"
    rdir = f"${{cache}}/v1/releases/{d}"
    names = [f"OTC_{d}.jsonl", f"OTC_{d}.meta.json", f"OTC_{d}.sha256"]
    bad_index = {**err("invalid_release"), "error_message": {"$contains": "index-v1.json"}}

    def changed_line(root):
        good = (FIXTURES / "good" / f"OTC_{d}.jsonl").read_bytes().splitlines()
        bad = (FIXTURES / root / f"OTC_{d}.jsonl").read_bytes().splitlines()
        return next(i for i, (x, y) in enumerate(zip(good, bad)) if x != y)

    for label, root, sets in [
            ("qc-flags", "bad/qc-flags-not-array", {}),
            # the index names a convention that resolves, the line one that does not
            ("unresolved-convention", "bad/unresolved-convention", {"convention_id": "otc-greenwich-v1"})]:
        idx = reference_index(FIXTURES / root / f"OTC_{d}.jsonl", d)
        i = changed_line(root)
        sid = idx["stations"][i]["station_id"]
        if sets:
            j = next(k for k, cs in enumerate(idx["stations"][i]["sets"])
                     if any(cs[x] != v for x, v in sets.items()))
            idx["stations"][i]["sets"][j].update(sets)
        idx["by"] = "opentideconstants-conformance/1.0"
        verified = {"files": {n: {"sha256": hashlib.sha256((FIXTURES / root / n).read_bytes()).hexdigest(),
                                  "size": (FIXTURES / root / n).stat().st_size, "url": None} for n in names},
                    "verified_at": "2099-12-31T20:00:00Z", "by": "opentideconstants-conformance/1.0"}
        out.append(case(f"rules/r2-pk07/index-line-{label}", f"{root} cached with a fresh index-v1.json: the open uses the index; reading {sid}'s line is invalid_release naming index-v1.json, which is deleted; the next open fails the full pass", "6.2",
                        [drv("copy", files=[f"{FIX}/{root}/{n}" for n in names], to=rdir),
                         drv("write", path=f"{rdir}/.verified", text=json.dumps(verified, sort_keys=True)),
                         drv("write", path=f"{rdir}/index-v1.json", text=json.dumps(idx, ensure_ascii=False)),
                         net(step("open", {"loaded_from": "cache", "datestamp": d}, release=d, cache_dir="${cache}", offline=True, mode="stream")),
                         step("station", bad_index, station_id=sid),
                         drv("assert_files", dir=rdir, present=[".verified"], absent=["index-v1.json"]),
                         step("open", err("invalid_release"), release=d, cache_dir="${cache}", offline=True, mode="stream")],
                        requires=["fs", "fetch", "stream"]))
    # The index is named from the .jsonl file, not from release.datestamp (CR2 DR23: no cross-file check): a
    # verified release whose .meta.json gives another datestamp gets an index for its own file name, which the
    # next open finds fresh and does not rewrite.
    d2 = "20991231.2"
    rdir2 = f"${{cache}}/v1/releases/{d2}"
    meta = json.loads((FIXTURES / "good" / f"OTC_{d2}.meta.json").read_text(encoding="utf-8"))
    meta["release"]["datestamp"] = "20991230"
    meta_text = json.dumps(meta, ensure_ascii=False, indent=1) + "\n"
    jl = (FIXTURES / "good" / f"OTC_{d2}.jsonl").read_bytes()
    digests = {f"OTC_{d2}.jsonl": hashlib.sha256(jl).hexdigest(), f"OTC_{d2}.meta.json": hashlib.sha256(meta_text.encode("utf-8")).hexdigest()}
    sizes = {f"OTC_{d2}.jsonl": len(jl), f"OTC_{d2}.meta.json": len(meta_text.encode("utf-8"))}
    sums = "".join(f"{digests[n]}  {n}\n" for n in sorted(digests))
    verified = {"files": {n: {"sha256": digests[n], "size": sizes[n], "url": None} for n in digests}
                | {f"OTC_{d2}.sha256": {"sha256": hashlib.sha256(sums.encode()).hexdigest(), "size": len(sums), "url": None}},
                "verified_at": "2099-12-31T20:00:00Z", "by": "opentideconstants-conformance/1.0"}
    reopen = net(step("open", {"loaded_from": "cache", "datestamp": "20991230"}, release=d2, cache_dir="${cache}", offline=True, mode="stream"))
    out.append(case("rules/r2-pk07/index-named-from-file", "a cached release whose .meta.json gives release.datestamp 20991230: the stream index the SDK writes names the file's release (20991231.2), and the next open uses it without rewriting it (CR2 DR23)", "6.2",
                    [drv("copy", files=[f"{FIX}/good/OTC_{d2}.jsonl"], to=rdir2),
                     drv("write", path=f"{rdir2}/OTC_{d2}.meta.json", text=meta_text),
                     drv("write", path=f"{rdir2}/OTC_{d2}.sha256", text=sums),
                     drv("write", path=f"{rdir2}/.verified", text=json.dumps(verified, sort_keys=True)),
                     reopen, step("close"),
                     drv("assert_index", path=f"{rdir2}/index-v1.json", jsonl=f"{rdir2}/OTC_{d2}.jsonl", datestamp=d2),
                     drv("copy", files=[f"{rdir2}/index-v1.json"], to="${tmp}/index-copy"),
                     reopen, step("station_count", {"station_count": len(Rel("good", d2).active)}), step("close"),
                     drv("assert_sha256", path=f"{rdir2}/index-v1.json", equals="${tmp}/index-copy/index-v1.json")],
                    requires=["fs", "fetch", "stream"]))
    return out


def group_rules():
    """Cases for the cross-SDK behaviour rules of review round 1 (packages PK01-PK15, decisions D1-D37). Today's SDKs
    fail many of them; conformance/expected-failures.json lists which, per runner (the RED baseline of each lane)."""
    out = []
    G = f"{SRV}/good/"
    d2, d1 = "20991231.2", "20991231"
    good_ptr = FIXTURES / "good" / "OTC_latest-f1.json"
    ptr_etag = '"' + hashlib.sha256(good_ptr.read_bytes()).hexdigest() + '"'
    info2, info1 = enc_release_info("good", d2, G), enc_release_info("good", d1, G)
    vdoi = pointer_entry("good", d2)["zenodo_version_doi"]
    pointer_rule = r"/good/OTC_latest(-f1)?\.json$"
    only_v1 = drv("assert_tree", dir="${cache}", allow=["v1", "v1/**"], may_be_missing=True)

    def latest(expect, base=G, **kw):
        return net(step("open", expect, base_url=base, cache_dir="${cache}", **kw))

    def pinned(d, expect=None, base=G, **kw):
        return net(step("open", expect if expect is not None else {"datestamp": d}, release=d, base_url=base, cache_dir="${cache}", **kw))

    # PK01: a datestamp from the server or from the user must match the datestamp pattern; nothing is written
    # outside <cache>/v1 (spec 4.2, 5.4; D18)
    for label, bad in [("dotdot", "../../x"), ("dashed", "2026-10-08"), ("counter01", "20261008.01"), ("newline", "20261008\n"),
                       ("counter10", "20991231.1234567890")]:   # D18: a counter longer than 9 digits from the server (G10)
        out.append(case(f"rules/pk01/pointer-bad-datestamp-{label}", f"the pointer's datestamp is {bad!r}: invalid_release, and nothing is written outside the cache's v1 directory", "4.2, 5.4",
                        [drv("server_rules", rules=[{"match": pointer_rule, "action": "json", "file": "good/OTC_latest-f1.json", "pointer": "", "set": {"/datestamp": bad}}]),
                         latest(err("invalid_release"), on_network_error="raise"), only_v1],
                        requires=["fs"]))
    out.append(case("rules/pk01/index-bad-datestamp", "an OTC_index.json entry with the datestamp ../../x: releases() is invalid_release, and nothing is written outside v1", "4.2, 4.3, 5.4",
                    [latest({"datestamp": d2}),
                     drv("server_rules", rules=[{"match": r"/good/OTC_index\.json$", "action": "json", "file": "good/OTC_index.json", "pointer": "", "set": {"/releases/0/datestamp": "../../x"}}]),
                     net(step("releases", err("invalid_release"))), only_v1],
                    requires=["fs"]))
    out.append(case("rules/pk01/file-bad-name", "file: a name that is not OTC_<D>.json, .json.gz or .jsonl (OTC_20991231.2.meta.json): invalid_argument (D18)", "4.2",
                    [drv("copy", files=[f"{FIX}/good/OTC_{d2}.meta.json", f"{FIX}/good/OTC_{d2}.sha256"], to="${tmp}/rel"),
                     step("open", err("invalid_argument"), file=f"${{tmp}}/rel/OTC_{d2}.meta.json")],
                    requires=["fs"]))
    out.append(case("rules/pk01/counter-too-long", "release= with a counter longer than 9 digits: invalid_argument (D18)", "4.2",
                    [pinned("20991231.1234567890", err("invalid_argument")),
                     pinned("20991231." + "1" * 40, err("invalid_argument"))],
                    requires=["fs"]))
    # PK02: a 200 pointer that is not JSON is a network error and never replaces the cached pointer (D8)
    out.append(case("rules/pk02/pointer-200-not-json", "the pointer answers 200 with an HTML page and the real ETag: use_cache falls back, the cached pointer is kept, and the next open still works", "5.2",
                    [latest({"datestamp": d2}), drv("restart_runner"),
                     drv("server_rules", rules=[{"match": pointer_rule, "action": "status", "status": 200, "body": "<html>captive portal</html>",
                                                 "headers": {"ETag": ptr_etag, "Content-Type": "text/html"}}]),
                     latest({"loaded_from": "cache_after_error", "datestamp": d2}),
                     step("last_error", {"code": "network"}),
                     drv("assert_sha256", path="${cache}/v1/pointer/OTC_latest-f1.json", equals=f"{FIX}/good/OTC_latest-f1.json"),
                     drv("server_rules", rules=[]), drv("restart_runner"),
                     latest({"loaded_from": {"$any_of": ["cache", "download"]}, "datestamp": d2})],
                    requires=["fs"], timeout_s=90))
    out.append(case("rules/pk02/releases-use-cache", "releases() with use_cache and an index that answers 500: the cached index", "4.3, 5.2",
                    [latest({"datestamp": d2}), net(step("releases", {"releases": [info2, info1]})), drv("restart_runner"),
                     latest({"datestamp": d2}),
                     drv("server_rules", rules=[{"match": r"/good/OTC_index\.json$", "action": "status", "status": 500}]),
                     net(step("releases", {"releases": [info2, info1]}))],
                    requires=["fs"], timeout_s=90))
    # PK03, PK06, PK07: releases each SDK must refuse with invalid_release, in every load path (D5, D9)
    for root in ["min-reader-malformed", "format-version-malformed",
                 "duplicate-station-id", "active-and-removed-same-id", "duplicate-alias", "duplicate-set-id",
                 "unresolved-reference-station", "unresolved-offsets-licence", "duplicate-convention-id", "unresolved-licence",
                 "unresolved-recommended",
                 "station-id-not-string", "lat-string", "lat-nan", "aliases-not-object", "qc-flags-not-array",
                 "convention-without-id", "created-not-string", "source-versions-not-object"]:
        pk = "pk03" if "malformed" in root and root.startswith(("min", "format")) else "pk06" if root.startswith(("duplicate", "active", "unresolved")) else "pk07"
        for ext, req, mode in [(".json", ["json", "eager"], "eager"), (".json.gz", ["json", "eager"], "eager"),
                               (".jsonl", ["eager"], "eager"), (".jsonl", ["stream"], "stream")]:
            label = ext.replace(".", "-") + ("-stream" if mode == "stream" else "")
            out.append(case(f"rules/{pk}/bad-{root}{label}", f"bad/{root} opened as {ext} ({mode}): invalid_release at open", "4.8, 6.1, 7.4",
                            [step("open", err("invalid_release"), file=f"{FIX}/bad/{root}/OTC_20991231{ext}", mode=mode)],
                            requires=["fs"] + req))
    # CR2 PK-R2-04 (DR6): a created or record_span time with impossible calendar fields, hour 24, a leap second, or out
    # of range in UTC is invalid_release in every load path; no SDK rolls it over into another date
    for root in ["created-impossible", "created-leap-second", "created-out-of-range",
                 "record-span-feb-31", "record-span-feb-29", "record-span-hour-24"]:
        for ext, req, mode in [(".json", ["json", "eager"], "eager"), (".json.gz", ["json", "eager"], "eager"),
                               (".jsonl", ["eager"], "eager"), (".jsonl", ["stream"], "stream")]:
            label = ext.replace(".", "-") + ("-stream" if mode == "stream" else "")
            out.append(case(f"rules/r2-pk04/bad-{root}{label}", f"bad/{root} opened as {ext} ({mode}): invalid_release at open (DR6)", "4.6, 7.3",
                            [step("open", err("invalid_release"), file=f"{FIX}/bad/{root}/OTC_20991231{ext}", mode=mode)],
                            requires=["fs"] + req))
    MJ = f"{SRV}/major/"
    out.append(case("rules/pk03/check-for-update-only-newer-major", "check_for_update when every release on the server has a newer major (bad/format-major): unsupported_format, and newer_format_major is 2 all the same (D10)", "7.4",
                    [step("open", {"loaded_from": "file", "datestamp": d2}, file=f"{FIX}/good/OTC_{d2}.jsonl",
                          base_url=f"{SRV}/bad/format-major/", cache_dir="${cache}"),
                     net(step("check_for_update", err("unsupported_format"))),
                     net(step("newer_format_major", {"newer_format_major": 2}))],
                    requires=["fs"]))
    # PK04: prune reports only what it removed
    out.append(case("rules/pk04/prune-reports-only-removed", "prune cannot remove a release directory (read-only): cache error, and the release is still cached", "4.3, 4.8",
                    [pinned(d1), pinned(d2),
                     drv("chmod", path=f"${{cache}}/v1/releases/{d1}", mode="555"),
                     net(step("prune", err("cache"), keep=1)),
                     drv("chmod", path=f"${{cache}}/v1/releases/{d1}", mode="755"),
                     net(step("cached_releases", {"datestamps": [d2, d1]}))],
                    requires=["fs"]))
    # PK07: arguments
    out.append(case("rules/pk07/timeout-zero", "timeout 0: invalid_argument", "4.2, 4.8",
                    [latest(err("invalid_argument"), timeout=0)], requires=["fs"]))
    out.append(case("rules/pk07/timeout-negative", "a negative timeout (-5; -1 is the C default sentinel): invalid_argument (R2-152)", "4.2, 4.8",
                    [latest(err("invalid_argument"), timeout=-5)], requires=["fs"]))
    out.append(case("rules/pk07/timeout-tiny", "timeout below 0.001 s: invalid_argument (CR2 DR19)", "4.8, 5.7",
                    [latest(err("invalid_argument"), timeout=0.0001)], requires=["fs"]))
    out.append(case("rules/pk07/timeout-huge", "timeout above 1e6 s: invalid_argument (CR2 DR19)", "4.8, 5.7",
                    [latest(err("invalid_argument"), timeout=1e7)], requires=["fs"]))
    # CR D31 (spec 4.2): a file client reads no pointer and opens no socket, so these options would be ignored
    for cid, title, extra in (("file-offline", "file with offline true", {"offline": True}),
                              ("file-release", "file with a pinned release", {"release": d2}),
                              ("file-on-network-error", "file with on_network_error raise", {"on_network_error": "raise"})):
        out.append(case(f"rules/pk07/{cid}", f"{title}: invalid_argument (D31)", "4.2",
                        [step("open", err("invalid_argument"), file=f"{FIX}/good/OTC_{d2}.jsonl", cache_dir="${cache}", **extra)],
                        requires=["fs"]))
    # CR T94 (spec 4.2): stream mode reads lines of a .jsonl and its .meta.json; a .json or .json.gz file has no lines
    # to seek to, so a stream client on one fails, and never loads it eagerly in silence
    for cid, ext in (("file-stream-json", ".json"), ("file-stream-json-gz", ".json.gz")):
        out.append(case(f"rules/pk07/{cid}", f"mode stream on a {ext} file: invalid_argument (stream mode needs .jsonl and .meta.json)", "4.2",
                        [step("open", err("invalid_argument"), file=f"{FIX}/good/OTC_{d2}{ext}", mode="stream")],
                        requires=["fs", "json", "stream"]))
    B = "${tmp}/bundle"
    out.append(case("rules/pk07/formats-empty", "download with formats []: invalid_argument", "4.3.2",
                    [open_latest_no_cache(G), net(step("download", err("invalid_argument"), release=d2, to=B, formats=[]), fs=True)], requires=[]))
    R2 = Rel("good", d2)
    out.append(mcase("rules/pk07/kind-other-empty", "the kind filter other matches no station of good/ (no station has an unknown quantity; spec 4.4)", "4.4",
                     [step("stations", {"station_ids": [s["station_id"] for s in apply_filters(R2, R2.active, {"kind": "other"})]}, kind="other"),
                      step("iter_stations", {"station_ids": []}, kind="other")]))
    out.append(mcase("rules/pk07/limit-zero", "search and near with limit 0: invalid_argument (D36: limit is 1 or more, or absent)", "4.4",
                     [step("search", err("invalid_argument"), name="harbour", limit=0),
                      step("near", err("invalid_argument"), lat=50.75, lon=-1.2, radius_km=100, limit=0)]))
    # PK08: one input, one answer
    V = Rel("values", "20991231.2")
    s101 = V.by_id["OTC-T-0101"]
    out.append(mcase("rules/pk08/created-normalised", "release.created with an offset and a fraction is returned in UTC, YYYY-MM-DDTHH:MM:SSZ", "4.3",
                     [step("release_metadata", {"created": "2099-12-31T00:00:00Z"})], root="values", release="20991231.2"))
    out.append(mcase("rules/pk08/previous-release-non-number", "a non-number in validation.previous_release is null; the numbers are kept", "4.6",
                     [step("station_validation", {"validation": [{**enc_validation(s101["validation"][0]),
                                                                  "previous_release": {**pick({}, PREVIOUS_FIELDS), "height_mae_m": 0.02}}]},
                           station_id="OTC-T-0101")], root="values", release="20991231.2"))
    out.append(mcase("rules/pk08/fold-nul", "a NUL in a station name is kept by the fold (only U+0020 is trimmed, D12 e): the name with the NUL matches exactly; a name that ends in NUL is not the name without it", "4.4.1",
                     [step("search", {"station_ids": ["OTC-T-0151"]}, name="Me\u0000da"),
                      step("search", {"station_ids": []}, name="pier", match="exact")], root="values", release="20991231.2"))
    for root, sid, field, value in [("values-kept-reason", "OTC-T-0101", "kept_reason", "snr above 2.0 and stable across the yearly fits"),
                                    ("values-source-name", "OTC-T-0101", "source_name", "Ø" * 31)]:
        rel = Rel(root, "20991231.2")
        cs = rel.by_id[sid]["constant_sets"][0]
        out.append(mcase(f"rules/pk08/{field.replace('_', '-')}-long", f"a constituent {field} of {len(value)} characters ({len(value.encode())} bytes), valid 1.0, loads and is returned in full (D13)", "4.5, 6.4",
                         [step("constituents", {"constituents": [pick(c, CONSTITUENT_FIELDS) for c in cs["constituents"]]}, station_id=sid, set_id=cs["set_id"])],
                         root=root, release="20991231.2"))
    F = Rel("fold", "20991231.2")
    fold_steps = []
    for q, kw, want in FOLD_D12:
        got = search(F, q, **kw)
        if got != want:
            raise SystemExit(f"rules/pk08/fold-d12: search {q!r} with the fold table gives {got}, D12 needs {want} "
                             f"(conformance/name_fold.json lacks a D12 row?)")
        fold_steps.append(step("search", {"station_ids": want}, name=q, **kw))
    out.append(mcase("rules/pk08/fold-d12", "the fold rules of D12: final sigma, h t n k with stroke, eng and kra, the middle dot, NBSP", "4.4.1",
                     fold_steps, root="fold", release="20991231.2"))
    out.append(case("rules/pk08/base-url-no-slash", "a base_url without a trailing slash is the same as with one", "4.2, 5.2",
                    [latest({"datestamp": d2, "loaded_from": "download"}, base=f"{SRV}/good")], requires=["fs"]))
    # PK09: offline means no socket, also for update and the automatic update (D6)
    old_pointer = [{"match": pointer_rule, "action": "json", "file": "good/OTC_index.json", "pointer": "/releases/1"}]
    cached_d1_pointer_d2 = [pinned(d1), net(step("latest", {"release": info2})), drv("restart_runner")]
    out.append(case("rules/pk09/update-offline-no-socket", "offline, with a cached pointer that names an uncached newer release: update is offline_unavailable and opens no socket (D6)", "4.2, 4.3, 5.5",
                    cached_d1_pointer_d2 + [latest({"loaded_from": "cache", "datestamp": d1}, offline=True),
                                            drv("server_stop"), drv("clear_log"),
                                            net(step("update", err("offline_unavailable"))),
                                            drv("assert_requests", source="any", count=0)],
                    requires=["fs"]))
    out.append(case("rules/pk09/auto-update-offline-no-socket", "offline with auto_update: the first query after the interval opens no socket and keeps the release (D6)", "5.5, 5.6",
                    cached_d1_pointer_d2 + [latest({"loaded_from": "cache", "datestamp": d1}, offline=True, auto_update=True, update_interval=1),
                                            drv("server_stop"), drv("clear_log"), drv("sleep", s=2.5),
                                            step("release_metadata", {"datestamp": d1}),
                                            drv("assert_requests", source="any", count=0)],
                    requires=["fs"]))
    # PK10: local IO and configuration errors are not network errors
    out.append(case("rules/pk10/readonly-cache-is-cache-error", "a cache directory in a read-only parent: cache error (not network, no fallback)", "4.8, 5.2",
                    [drv("mkdir", path="${tmp}/ro"), drv("chmod", path="${tmp}/ro", mode="555"),
                     net(step("open", err("cache"), base_url=G, cache_dir="${tmp}/ro/cache"))],
                    requires=["fs"]))
    out.append(case("rules/pk10/readonly-to-is-io", "download into a read-only folder: io error", "4.3.2, 4.8",
                    [latest({"datestamp": d2}), drv("mkdir", path=B), drv("chmod", path=B, mode="555"),
                     net(step("download", err("io"), release=d2, to=B), fs=True)],
                    requires=["fs"]))
    # D19: a missing ca_file is io (never invalid_argument), at construction, never retried, and never a reason to
    # fall back to the cache: a cached release and use_cache (the default) must not hide it (CR2 G11)
    out.append(case("rules/pk10/bad-ca-file-no-retry", "ca_file names a missing file, with a cached release and use_cache: io at once, no request, no fallback (D19)", "4.8, 5.7",
                    [latest({"datestamp": d2}), drv("restart_runner"), drv("clear_log"),
                     latest(err("io"), ca_file="${tmp}/no-such-ca.pem", on_network_error="use_cache"),
                     drv("assert_requests", source="any", count=0)],
                    requires=["fs"]))
    NG = f"{SRV}/nogz/"
    out.append(case("rules/pk10/unpublished-format-is-release-not-found", "download of a format the release does not publish (.json.gz): release_not_found", "4.3.2, 4.8",
                    [latest({"datestamp": d2}, base=NG), net(step("download", err("release_not_found"), release=d2, to=B, formats=["json.gz"]), fs=True)],
                    requires=["fs"]))
    # PK11: verify hashes the files, and checksum rules
    rdir = f"${{cache}}/v1/releases/{d2}"
    # CR2 DR44 (orchestrator decision 2026-10-09): a cached data file that is gone is io in every SDK, never
    # checksum_mismatch (the file cannot be read; nothing was hashed)
    out.append(case("rules/pk11/verify-missing-data-file", "verify after the cached .jsonl is deleted: io, never verified (DR44)", "4.3",
                    [latest({"datestamp": d2}, mode="stream"), drv("delete", path=f"{rdir}/OTC_{d2}.jsonl"),
                     step("verify", err("io"))],
                    requires=["fs", "stream"]))
    out.append(case("rules/pk26/verify-missing-data-file-eager", "verify in eager mode after the cached .json is deleted: io, never verified (DR44)", "4.3",
                    [latest({"datestamp": d2}, mode="eager"), drv("delete", path=f"{rdir}/OTC_{d2}.json"),
                     step("verify", err("io"))],
                    requires=["fs", "eager"]))
    out.append(case("rules/pk11/verify-missing-verified", "verify with .verified deleted and the .jsonl changed: the files are hashed against OTC_{D}.sha256, checksum_mismatch", "4.3",
                    [latest({"datestamp": d2}, mode="stream"), drv("delete", path=f"{rdir}/.verified"),
                     drv("corrupt", path=f"{rdir}/OTC_{d2}.jsonl", offset=100),
                     step("verify", err("checksum_mismatch"))],
                    requires=["fs", "stream"]))
    # PK-R2-25: verify of a cached release compares with the cached OTC_{D}.sha256, so a missing one fails (spec 4.3)
    for m in ["stream", "eager"]:
        out.append(case(f"rules/pk25/verify-cached-missing-sha256-{m}", f"verify on a cached release ({m}) after the cached OTC_{{D}}.sha256 is deleted: checksum_mismatch, never verified", "4.3, 5.3",
                        [latest({"datestamp": d2}, mode=m), drv("delete", path=f"{rdir}/OTC_{d2}.sha256"),
                         step("verify", err("checksum_mismatch"))],
                        requires=["fs", m]))
    # CR2 DR45 (orchestrator decision 2026-10-09): verify on a cached release checks the cached OTC_{D}.sha256
    # against the digest a cached pointer (pointer/OTC_latest-f1.json or OTC_latest.json) lists for it, as download
    # does since DR40; a mismatch is checksum_mismatch, with no request (verify is read-only). The list below has the
    # release's rows in another order: every file still matches it, only its own SHA-256 differs from the pointer's.
    # Eager only: C has no cached verify (otc_verify_file is path-based, spec 4.3), and C runs no eager case.
    rows2 = sha256_rows("good", d2)
    reordered = "".join(f"{h}  {n}\n" for n, h in sorted(rows2.items(), reverse=True))
    sp2 = f"{rdir}/OTC_{d2}.sha256"
    out.append(case("rules/pk26/verify-cached-sha256-not-the-pointers", "verify on a cached release whose OTC_{D}.sha256 still lists every file right but is not the one the cached pointer lists: checksum_mismatch, no request, never verified (DR45)", "4.3, 5.3",
                    [latest({"datestamp": d2}, mode="eager"), drv("write", path=sp2, text=reordered), drv("clear_log"),
                     step("verify", err("checksum_mismatch", file={"$contains": f"OTC_{d2}.sha256"})),
                     drv("assert_requests", source="any", count=0)],
                    requires=["fs", "eager"]))
    # DR45 leaves verify as it was when no cached pointer lists a digest for the release: a pinned open stores no
    # pointer, and the cached pointer of latest (d2) lists nothing for d1
    rdir1 = f"${{cache}}/v1/releases/{d1}"
    reordered1 = "".join(f"{h}  {n}\n" for n, h in sorted(sha256_rows("good", d1).items(), reverse=True))
    out.append(case("rules/pk26/verify-cached-sha256-no-pointer-digest", "verify on cached releases whose OTC_{D}.sha256 is reordered but no cached pointer lists a digest for it (a pinned open; the pointer names another release): verified (DR45)", "4.3, 5.3",
                    [pinned(d2, mode="eager"), drv("write", path=sp2, text=reordered), step("verify", {"verified": True}),
                     latest({"datestamp": d2}, mode="eager"), pinned(d1, mode="eager"),
                     drv("write", path=f"{rdir1}/OTC_{d1}.sha256", text=reordered1), step("verify", {"verified": True})],
                    requires=["fs", "eager"]))
    # DR45: the pointer's digest may be in upper case (pk11 pointer-sha256-uppercase); the comparison ignores case
    upper2 = {f"/files/{i}/sha256": f["sha256"].upper() for i, f in enumerate(pointer_entry("good", d2)["files"])}
    out.append(case("rules/pk26/verify-cached-pointer-sha256-uppercase", "the cached pointer gives the SHA-256 values in upper case: verify on the cached release passes (DR45)", "4.3, 5.3",
                    [drv("server_rules", rules=[{"match": pointer_rule, "action": "json", "file": "good/OTC_latest-f1.json", "pointer": "", "set": upper2}]),
                     latest({"datestamp": d2, "loaded_from": "download"}, mode="eager"), step("verify", {"verified": True})],
                    requires=["fs", "eager"]))
    out.append(case("rules/pk11/verify-unverified-file", "verify on a file opened with no .sha256 next to it (file_unverified): checksum_mismatch (D20)", "4.3",
                    [drv("copy", files=[f"{FIX}/good/OTC_{d2}.jsonl", f"{FIX}/good/OTC_{d2}.meta.json"], to="${tmp}/rel"),
                     step("open", {"loaded_from": "file_unverified"}, file=f"${{tmp}}/rel/OTC_{d2}.jsonl"),
                     step("verify", err("checksum_mismatch"))],
                    requires=["fs"]))
    entry2 = pointer_entry("good", d2)
    upper = {f"/files/{i}/sha256": f["sha256"].upper() for i, f in enumerate(entry2["files"])}
    out.append(case("rules/pk11/pointer-sha256-uppercase", "the pointer gives the SHA-256 values in upper case: the release loads, and a second open uses the cache", "5.2",
                    [drv("server_rules", rules=[{"match": pointer_rule, "action": "json", "file": "good/OTC_latest-f1.json", "pointer": "", "set": upper}]),
                     latest({"datestamp": d2, "loaded_from": "download"}), drv("restart_runner"),
                     latest({"datestamp": d2, "loaded_from": "cache"})],
                    requires=["fs"]))
    for root in ["sha256-file-differs", "sums-disagree", "sums-extra-file", "size-mismatch", "jsonl-wrong-sha256"]:
        out.append(case(f"rules/pk11/bad-{root}-latest", f"latest from bad/{root}: checksum_mismatch (spec 5.2 step 4)", "5.2",
                        [latest(err("checksum_mismatch"), base=f"{SRV}/bad/{root}/", on_network_error="raise", mode="stream")],
                        requires=["fs", "stream"]))
    out.append(case("rules/pk11/corrupt-same-size-heals-online", "a cached .jsonl with one byte changed (same size): verify_on_open finds it, and the open downloads it again", "4.8, 5.3",
                    [pinned(d2, mode="stream"), drv("corrupt", path=f"{rdir}/OTC_{d2}.jsonl", offset=100), drv("restart_runner"),
                     pinned(d2, {"datestamp": d2, "loaded_from": "download"}, mode="stream", verify_on_open=True),
                     drv("assert_sha256", path=f"{rdir}/OTC_{d2}.jsonl", equals=f"{FIX}/good/OTC_{d2}.jsonl")],
                    requires=["fs", "stream"]))
    absolute = {f"/files/{i}/url": f"{SRV}/good/{f['url']}" for i, f in enumerate(entry2["files"])}
    out.append(case("rules/pk11/sha256-absolute-url", "the pointer lists every file with an absolute URL in another directory: the SDK fetches OTC_{D}.sha256 from its listed URL too", "4.3.1, 5.2",
                    [drv("server_rules", rules=[{"match": r"/abs/OTC_latest(-f1)?\.json$", "action": "json", "file": "good/OTC_latest-f1.json", "pointer": "", "set": absolute}]),
                     latest({"datestamp": d2, "loaded_from": "download"}, base=f"{SRV}/abs/"),
                     drv("assert_requests", match=rf"^/good/OTC_{re.escape(d2)}\.sha256$", min=1),
                     drv("assert_requests", match=r"^/abs/OTC_20991231", count=0)],
                    requires=["fs"]))
    out.append(case("rules/pk11/eager-json-without-gz", "eager latest from a release that publishes no .json.gz: it loads", "5.2",
                    [latest({"datestamp": d2, "loaded_from": "download"}, base=NG, mode="eager")],
                    requires=["fs", "eager"]))
    # PK12: redirects (D1: up to 5), httpoxy (D7), Content-Encoding on a .gz file
    def hops(n):
        rules = [{"match": rf"^/good/OTC_{re.escape(d2)}\.sha256$", "action": "status", "status": 302,
                  "headers": {"Location": f"/hop1/OTC_{d2}.sha256"}}]
        for i in range(1, n):
            rules.append({"match": rf"^/hop{i}/", "action": "status", "status": 302, "headers": {"Location": f"/hop{i + 1}/OTC_{d2}.sha256"}})
        rules.append({"match": rf"^/hop{n}/", "action": "file", "file": f"good/OTC_{d2}.sha256"})
        return rules
    out.append(case("rules/pk12/redirect-five-hops", "OTC_{D}.sha256 answers with 5 redirects in a row: the SDK follows them and loads (D1)", "5.7",
                    [drv("server_rules", rules=hops(5)), pinned(d2, {"datestamp": d2, "loaded_from": "download"}, on_network_error="raise")],
                    requires=["fs"]))
    out.append(case("rules/pk12/redirect-six-hops", "6 redirects in a row: network error (D1: at most 5)", "5.7",
                    [drv("server_rules", rules=hops(6)), pinned(d2, err("network"), on_network_error="raise")],
                    requires=["fs"], timeout_s=90))
    sha_rx = rf"^/good/OTC_{re.escape(d2)}\.sha256$"
    out.append(case("rules/pk12/redirect-to-ftp", "OTC_{D}.sha256 redirects to an ftp:// URL: network error (D1: http and https only)", "5.7",
                    [drv("server_rules", rules=[{"match": sha_rx, "action": "status", "status": 302,
                                                 "headers": {"Location": f"ftp://127.0.0.1:1/good/OTC_{d2}.sha256"}}]),
                     pinned(d2, err("network"), on_network_error="raise"),
                     drv("assert_requests", source="server", match=sha_rx, status=302, count=1)],
                    requires=["fs"], timeout_s=90))
    TLS = "${server_tls}/good/"
    out.append(case("rules/pk12/https-pinned-loads", "a pinned release over https, with ca_file the conformance CA: it loads (the control case of the https cases)", "5.7",
                    [pinned(d2, {"datestamp": d2, "loaded_from": "download"}, base=TLS, ca_file="${tls_ca}", on_network_error="raise")],
                    requires=["fs"]))
    out.append(case("rules/pk12/redirect-https-to-http-refused", "over https, OTC_{D}.sha256 redirects to the same file over http: network error, and the http URL is never requested (D1)", "5.7",
                    [drv("server_rules", rules=[{"match": sha_rx, "action": "status", "status": 302, "times": 1,
                                                 "headers": {"Location": f"${{server}}/good/OTC_{d2}.sha256"}}]),
                     pinned(d2, err("network"), base=TLS, ca_file="${tls_ca}", on_network_error="raise"),
                     drv("assert_requests", source="server", match=sha_rx, status=302, count=1),   # the https request got the redirect
                     drv("assert_requests", source="server", match=sha_rx, status=200, count=0)],  # and http was not used
                    requires=["fs"], timeout_s=90))
    # CR2 DR39 (orchestrator decision 2026-10-09): the TLS hop to an https proxy trusts the system roots plus
    # ca_file, so a proxy whose certificate comes from the ca_file's private CA works, for an http target (the https
    # listener serves the fixtures to an absolute-URI GET, as a proxy would). The target hop trusts ca_file alone
    out.append(case("rules/pk24/https-proxy-private-ca", "an https proxy whose certificate comes from the ca_file's CA, and an http base_url: latest loads through it (the proxy hop trusts the system roots plus ca_file, DR39)", "5.7",
                    [latest({"datestamp": d2, "loaded_from": "download"}, base="http://otc-target.invalid/good/",
                            proxy="${server_tls}", ca_file="${tls_ca}", on_network_error="raise"),
                     drv("assert_requests", source="server", match=r"^/good/OTC_latest", status=200, count=1)],
                    requires=["fs", "https_proxy"]))
    out.append(case("rules/pk12/http-proxy-uppercase-cgi", "with REQUEST_METHOD set (a CGI request), upper-case HTTP_PROXY is not used (httpoxy, D7)", "5.7",
                    [drv("restart_runner", env={"REQUEST_METHOD": "GET", "HTTP_PROXY": "${proxy}"}),
                     latest(err("network"), base=f"{SRV_ALIAS}/good/", on_network_error="raise"),
                     drv("assert_requests", source="proxy", count=0)],
                    requires=["fs"], timeout_s=90))
    out.append(case("rules/pk12/gz-with-content-encoding", "the .json.gz is sent with Content-Encoding: gzip (as some CDNs do): the SDK keeps the gzip bytes, checks them, and loads", "5.7",
                    [drv("server_rules", rules=[{"match": rf"^/good/OTC_{re.escape(d2)}\.json\.gz$", "action": "file", "file": f"good/OTC_{d2}.json.gz",
                                                 "headers": {"Content-Encoding": "gzip"}}]),
                     pinned(d2, {"datestamp": d2, "loaded_from": "download"}, mode="eager", on_network_error="raise")],
                    requires=["fs", "eager"]))
    out.append(case("rules/pk12/gz-redirect-content-encoding", "the .json.gz redirects to a URL with no .gz suffix that sends it with Content-Encoding: gzip (a CDN): the SDK still keeps the gzip bytes, checks them, and loads (CR2 R2-118)", "5.7",
                    [drv("server_rules", rules=[{"match": rf"^/good/OTC_{re.escape(d2)}\.json\.gz$", "action": "status", "status": 302,
                                                 "headers": {"Location": "/cdn/blob-1"}},
                                                {"match": r"^/cdn/blob-1$", "action": "file", "file": f"good/OTC_{d2}.json.gz",
                                                 "headers": {"Content-Encoding": "gzip"}}]),
                     pinned(d2, {"datestamp": d2, "loaded_from": "download"}, mode="eager", on_network_error="raise")],
                    requires=["fs", "eager"]))
    # PK13: an automatic update that fails sets last_error and keeps the release
    R1 = Rel("good", d1)
    out.append(case("rules/pk13/auto-update-failure-sets-last-error", "an automatic update whose pointer request fails: the query still answers from the old release, and last_error is network", "4.3, 5.6",
                    [drv("server_rules", rules=old_pointer),
                     latest({"datestamp": d1}, auto_update=True, update_interval=1),
                     drv("server_rules", rules=[{"match": pointer_rule, "action": "status", "status": 500}]), drv("sleep", s=2.5),
                     step("station", {"station": enc_station(R1, R1.by_id["OTC-T-0021"])}, station_id="OTC-T-0021"),
                     step("last_error", {"code": "network"})],
                    requires=["fs"], timeout_s=120))
    # PK14: download writes all the files or none
    out.append(case("rules/pk14/offline-partial-cache-writes-nothing", "offline download of formats the cache does not all hold: offline_unavailable, and nothing is written", "4.3.2",
                    [latest({"datestamp": d2}, mode="stream"), drv("restart_runner"),
                     latest({"loaded_from": "cache", "datestamp": d2}, offline=True),
                     net(step("download", err("offline_unavailable"), release=d2, to=B, formats=["json", "jsonl"]), fs=True),
                     drv("assert_tree", dir=B, allow=[], may_be_missing=True)],
                    requires=["fs", "stream"]))
    out.append(case("rules/pk14/network-fails-second-file-writes-nothing", "the .meta.json answers 500 after the .jsonl came: network error, and nothing is written", "4.3.2",
                    [latest({"datestamp": d2}, on_network_error="raise"),
                     drv("server_rules", rules=[{"match": rf"OTC_{re.escape(d1)}\.meta\.json$", "action": "status", "status": 500}]),
                     net(step("download", err("network"), release=d1, to=B), fs=True),
                     drv("assert_tree", dir=B, allow=[], may_be_missing=True)],
                    requires=["fs"], timeout_s=90))
    # PK15: attribution input (D2)
    out.append(mcase("rules/pk15/attribution-unknown-station", "attribution with an unknown station: invalid_argument (D2 a)", "4.6",
                     [step("attribution", err("invalid_argument"), station_ids=["OTC-T-9999"])]))
    out.append(mcase("rules/pk15/attribution-empty-list", "attribution with an empty list is the full-release text, as with no argument (D2 c)", "4.6",
                     [step("attribution", {"attribution": attribution(R2, [])}, station_ids=[])]))
    # PK-R2-01 (CR2 DR1): the attribution follows the reference chain, not one link
    CH = Rel("chain", "20991231.2")
    chain_steps = [step("attribution", {"attribution": attribution(CH, ids)}, station_ids=ids)
                   for ids in (["OTC-T-0172"], ["OTC-T-0173"], ["OTC-T-0174"], ["OTC-T-0175"], ["OTC-T-0176"],
                               ["OTC-T-0176", "OTC-T-0174"])]
    out.append(mcase("rules/pk15/attribution-chain", "attribution of subordinate stations 1, 2 and 3 links from their reference station: every offsets licence on the path and the first recommended set's licence, where the walk stops (CR2 DR1)", "4.6",
                     chain_steps, root="chain", release="20991231.2"))
    # PK-R2-01 (R2-367, CR D2 b): a licence with a null provider prints its attribution alone, never merged
    NP = Rel("bad/licence-provider-null", "20991231")
    out.append(mcase("rules/pk15/attribution-null-provider", "a licence with a null provider prints {attribution} alone, with no prefix, and is never merged with another such licence (CR D2 b)", "4.6",
                     [step("attribution", {"attribution": attribution(NP)}),
                      step("attribution", {"attribution": attribution(NP, [])}, station_ids=[]),
                      step("attribution", {"attribution": attribution(NP, ["OTC-T-0004"])}, station_ids=["OTC-T-0004"])],
                     root="bad/licence-provider-null", release="20991231"))
    # PK-R2-01 (CR2 DR2): a licence attribution that is not a string, or a provider that is neither a string nor
    # null, is invalid_release at load, in every load path
    for root in ["licence-attribution-null", "licence-attribution-not-string", "licence-provider-not-string"]:
        for ext, req, mode in [(".json", ["json", "eager"], "eager"), (".json.gz", ["json", "eager"], "eager"),
                               (".jsonl", ["eager"], "eager"), (".jsonl", ["stream"], "stream")]:
            label = ext.replace(".", "-") + ("-stream" if mode == "stream" else "")
            out.append(case(f"rules/pk15/bad-{root}{label}", f"bad/{root} opened as {ext} ({mode}): invalid_release at open (CR2 DR2)", "4.6, 4.8",
                            [step("open", err("invalid_release"), file=f"{FIX}/bad/{root}/OTC_20991231{ext}", mode=mode)],
                            requires=["fs"] + req))
    out += r2_pk06_cases(G, d1, d2, info1, info2, pointer_rule, ptr_etag, latest, pinned)
    out += rules_r2_pk05()
    out += rules_r2_pk24()
    out += rules_r2_pk07()
    out += rules_r2_pk09()
    return out


def r2_pk06_cases(G, d1, d2, info1, info2, pointer_rule, ptr_etag, latest, pinned):
    """Review round 2, PK-R2-06: the .sha256 list, the pointer and index entries, and 200 bodies (CR2 DR12-DR15).
    The shape of a 200 body (DR13) is its type: the pointer is an object with a datestamp and a files array, the
    index an object with a releases array, a .sha256 file has at least one '<sha256>  <name>' row. A body of another
    shape is a network error and is never cached; a wrong value inside a body of the right shape is invalid_release."""
    out = []
    P = "rules/r2-pk06"
    kept_ptr = drv("assert_sha256", path="${cache}/v1/pointer/OTC_latest-f1.json", equals=f"{FIX}/good/OTC_latest-f1.json")
    kept_idx = drv("assert_sha256", path="${cache}/v1/pointer/OTC_index.json", equals=f"{FIX}/good/OTC_index.json")
    proxy_json = '{"error": "blocked by the proxy"}'
    html = "<html>captive portal</html>"
    # DR13: a 200 pointer of the wrong shape
    for label, rule in [("object", {"action": "status", "status": 200, "body": proxy_json,
                                    "headers": {"ETag": ptr_etag, "Content-Type": "application/json"}}),
                        ("array", {"action": "status", "status": 200, "body": "[]",
                                   "headers": {"ETag": ptr_etag, "Content-Type": "application/json"}}),
                        ("files-not-array", {"action": "json", "file": "good/OTC_latest-f1.json", "pointer": "",
                                             "set": {"/files": {}}})]:
        out.append(case(f"{P}/pointer-200-wrong-shape-{label}", f"the pointer answers 200 with JSON of the wrong shape ({label}): use_cache falls back with network, the cached pointer is kept, and the next open still works (DR13)", "5.2",
                        [latest({"datestamp": d2}), drv("restart_runner"),
                         drv("server_rules", rules=[{"match": pointer_rule, **rule}]),
                         latest({"loaded_from": "cache_after_error", "datestamp": d2}),
                         step("last_error", {"code": "network"}), kept_ptr,
                         drv("server_rules", rules=[]), drv("restart_runner"),
                         latest({"loaded_from": {"$any_of": ["cache", "download"]}, "datestamp": d2})],
                        requires=["fs"], timeout_s=90))
    out.append(case(f"{P}/pointer-200-wrong-shape-raise", "the pointer answers 200 with JSON of the wrong shape, on_network_error raise and an empty cache: network (DR13)", "5.2",
                    [drv("server_rules", rules=[{"match": pointer_rule, "action": "status", "status": 200, "body": proxy_json,
                                                 "headers": {"Content-Type": "application/json"}}]),
                     latest(err("network"), on_network_error="raise")],
                    requires=["fs"]))
    # DR13 and D8 (G5): a 200 index that is not JSON, or of the wrong shape
    for label, body, ctype in [("not-json", html, "text/html"), ("wrong-shape", proxy_json, "application/json"),
                               ("releases-not-array", '{"releases": {}}', "application/json")]:
        out.append(case(f"{P}/index-200-{label}", f"OTC_index.json answers 200 with a body that is {label.replace('-', ' ')}: releases() with use_cache answers from the cached index, which is kept (D8, DR13)", "4.3, 5.2",
                        [latest({"datestamp": d2}), net(step("releases", {"releases": [info2, info1]})), drv("restart_runner"),
                         latest({"datestamp": d2}),
                         drv("server_rules", rules=[{"match": r"/good/OTC_index\.json$", "action": "status", "status": 200, "body": body,
                                                     "headers": {"Content-Type": ctype}}]),
                         net(step("releases", {"releases": [info2, info1]})), kept_idx],
                        requires=["fs"], timeout_s=90))
        out.append(case(f"{P}/index-200-{label}-raise", f"OTC_index.json answers 200 with a body that is {label.replace('-', ' ')}, on_network_error raise and no cached index: releases() is network (D8, DR13)", "4.3, 5.2",
                        [latest({"datestamp": d2}, on_network_error="raise"),
                         drv("server_rules", rules=[{"match": r"/good/OTC_index\.json$", "action": "status", "status": 200, "body": body,
                                                     "headers": {"Content-Type": ctype}}]),
                         net(step("releases", err("network")))],
                        requires=["fs"]))
    # DR13: a 200 .sha256 with no valid row (checked before its SHA-256 is compared with the pointer's)
    sha_rule = [{"match": rf"/good/OTC_{re.escape(d2)}\.sha256$", "action": "status", "status": 200, "body": html,
                 "headers": {"Content-Type": "text/html"}}]
    out.append(case(f"{P}/sha256-200-html-latest", "the pointer names an uncached release whose OTC_{D}.sha256 answers 200 with an HTML page: use_cache falls back to the cached older release, last_error network (DR13)", "5.2",
                    [pinned(d1), drv("restart_runner"), drv("server_rules", rules=sha_rule),
                     latest({"loaded_from": "cache_after_error", "datestamp": d1}),
                     step("last_error", {"code": "network"})],
                    requires=["fs"], timeout_s=90))
    out.append(case(f"{P}/sha256-200-html-pinned", "a pinned uncached release whose OTC_{D}.sha256 answers 200 with an HTML page: network (DR13)", "5.2",
                    [drv("server_rules", rules=sha_rule), pinned(d2, err("network"), on_network_error="raise")],
                    requires=["fs"]))
    out.append(case(f"{P}/sha256-200-html-download", "download of a release whose OTC_{D}.sha256 answers 200 with an HTML page: network, and nothing is written (DR13)", "4.3.2, 5.2",
                    [step("open", {"loaded_from": "file", "datestamp": d2}, file=f"{FIX}/good/OTC_{d2}.jsonl", base_url=G,
                          cache_dir="${cache}"),
                     drv("server_rules", rules=sha_rule),
                     net(step("download", err("network"), release=d2, to="${tmp}/bundle"), fs=True),
                     drv("assert_tree", dir="${tmp}/bundle", allow=[], may_be_missing=True)],
                    requires=["fs"]))
    # DR12: a pointer or index file entry with no string sha256 or no integer size >= 0
    PF = f"{SRV}/bad/pointer-file-no-sha256/"
    out.append(case(f"{P}/pointer-file-no-sha256-latest", "latest from bad/pointer-file-no-sha256 (the pointer's OTC_{D}.sha256 entry has no sha256): invalid_release (DR12)", "5.3",
                    [latest(err("invalid_release"), base=PF, on_network_error="raise", mode="stream")],
                    requires=["fs", "stream"]))
    out.append(case(f"{P}/pointer-file-no-sha256-releases", "releases() from bad/pointer-file-no-sha256 (an index entry with no sha256): invalid_release (DR12)", "4.3, 5.3",
                    [step("open", {"loaded_from": "file", "datestamp": d2}, file=f"{FIX}/good/OTC_{d2}.jsonl", base_url=PF,
                          cache_dir="${cache}"),
                     net(step("releases", err("invalid_release")))],
                    requires=["fs"]))
    jl = next(i for i, f in enumerate(pointer_entry("good", d2)["files"]) if f["name"].endswith(".jsonl"))
    for label, value in [("size-string", {"size": "25682"}), ("size-negative", {"size": -1}), ("size-null", {"size": None}),
                         ("sha256-null", {"sha256": None}), ("sha256-number", {"sha256": 5})]:
        sets = {f"/files/{jl}/{k}": v for k, v in value.items()}
        out.append(case(f"{P}/pointer-entry-{label}", f"the pointer's .jsonl entry has {label.replace('-', ' ')}: invalid_release, and nothing is downloaded (DR12)", "5.3",
                        [drv("server_rules", rules=[{"match": pointer_rule, "action": "json", "file": "good/OTC_latest-f1.json", "pointer": "", "set": sets}]),
                         latest(err("invalid_release"), on_network_error="raise", mode="stream"),
                         drv("assert_requests", match=r"\.jsonl$", count=0)],
                        requires=["fs", "stream"]))
    out.append(case(f"{P}/index-entry-size-null", "an OTC_index.json entry whose .jsonl has size null: releases() is invalid_release (DR12)", "4.3, 5.3",
                    [latest({"datestamp": d2}),
                     drv("server_rules", rules=[{"match": r"/good/OTC_index\.json$", "action": "json", "file": "good/OTC_index.json", "pointer": "",
                                                 "set": {f"/releases/0/files/{jl}/size": None}}]),
                     net(step("releases", err("invalid_release")))],
                    requires=["fs"]))
    # DR14: a .sha256 that repeats a name, or is not UTF-8
    for root in ["sha256-dup-name", "sha256-invalid-utf8"]:
        out.append(case(f"{P}/{root}-latest", f"latest from bad/{root}: invalid_release (DR14)", "5.3",
                        [latest(err("invalid_release"), base=f"{SRV}/bad/{root}/", on_network_error="raise", mode="stream")],
                        requires=["fs", "stream"]))
        out.append(case(f"{P}/{root}-pinned", f"a pinned download from bad/{root}: invalid_release (DR14)", "5.3",
                        [pinned("20991231", err("invalid_release"), base=f"{SRV}/bad/{root}/", on_network_error="raise", mode="stream")],
                        requires=["fs", "stream"]))
        out.append(case(f"{P}/{root}-file", f"file: bad/{root}'s .jsonl, with its OTC_{{D}}.sha256 next to it: invalid_release (DR14)", "5.3",
                        [step("open", err("invalid_release"), file=f"{FIX}/bad/{root}/OTC_20991231.jsonl", mode="stream")],
                        requires=["fs", "stream"]))
    # DR15: an eager download needs the .json row
    NJ = f"{SRV}/bad/sha256-no-json-row/"
    not_listed = {**err("checksum_mismatch"), "error_message": {"$contains": "not listed"}}
    out.append(case(f"{P}/sha256-no-json-row-eager", "eager latest from bad/sha256-no-json-row (.json.gz listed, .json not): checksum_mismatch \"not listed\" (DR15)", "5.3",
                    [latest(not_listed, base=NJ, on_network_error="raise", mode="eager")],
                    requires=["fs", "eager"]))
    out.append(case(f"{P}/sha256-no-json-row-stream", "stream latest from bad/sha256-no-json-row: it loads (DR15 is for eager mode only)", "5.3",
                    [latest({"datestamp": "20991231", "loaded_from": "download"}, base=NJ, on_network_error="raise", mode="stream")],
                    requires=["fs", "stream"]))
    return out


# Review round 2, PK-R2-05: malformed release content is invalid_release in every SDK and every load path (spec 7.3
# "tolerant is not lax", 4.8, 6.1; CR D5, D17; CR2 DR22). One bad fixture per shape (build_fixtures.py BAD_R2_05).
R2_PK05_BAD = ["recommended-set-id-number", "station-name-number", "station-timezone-number", "offsets-number-string",
               "validation-number-string", "validation-count-fraction", "constituent-amplitude-string", "datum-msl-string",
               "good-samples-string", "set-source-version-number", "time-base-correction-string",
               "qc-flag-values-not-object", "qc-flag-value-string", "evidence-not-objects", "evidence-number-string",
               "source-version-number", "source-version-null", "constant-sets-object", "constant-sets-not-objects",
               "constant-sets-null-item", "lat-overflow-literal", "lon-overflow-literal", "lat-huge-int",
               "constituent-amplitude-inf", "constituent-amplitude-huge-int", "invalid-utf8", "lone-surrogate",
               "constituent-name-twice", "duplicate-licence-id", "tombstone-twice"]


def rules_r2_pk24():
    """Review round 2, PK-R2-24: a station status that is present but not a string is invalid_release in every SDK and
    every load path (CR2 DR43, orchestrator decision 2026-10-09); a null status stays active (CR2 DR28)."""
    out = []
    fixtures = {f["root"]: f for f in json.loads((FIXTURES / "fixtures.json").read_bytes())["fixtures"]}
    for root in ["status-number"]:
        fx = fixtures[f"bad/{root}"]
        if fx["expect"] != {"error": "invalid_release"}:
            raise SystemExit(f"bad/{root}: fixtures.json expects {fx['expect']}, not invalid_release")
        for ext, req, mode in [(".json", ["json", "eager"], "eager"), (".json.gz", ["json", "eager"], "eager"),
                               (".jsonl", ["eager"], "eager"), (".jsonl", ["stream"], "stream")]:
            label = ext.replace(".", "-") + ("-stream" if mode == "stream" else "")
            out.append(case(f"rules/r2-pk24/bad-{root}{label}", f"bad/{root} opened as {ext} ({mode}): invalid_release at open ({fx['defect']})",
                            "4.4, 4.8, 7.3",
                            [step("open", err("invalid_release"), file=f"{FIX}/bad/{root}/OTC_20991231{ext}", mode=mode)],
                            requires=["fs"] + req))
    return out


def rules_r2_pk05():
    out = []
    fixtures = {f["root"]: f for f in json.loads((FIXTURES / "fixtures.json").read_bytes())["fixtures"]}
    for root in R2_PK05_BAD:
        fx = fixtures[f"bad/{root}"]
        if fx["expect"] != {"error": "invalid_release"}:
            raise SystemExit(f"bad/{root}: fixtures.json expects {fx['expect']}, not invalid_release")
        for ext, req, mode in [(".json", ["json", "eager"], "eager"), (".json.gz", ["json", "eager"], "eager"),
                               (".jsonl", ["eager"], "eager"), (".jsonl", ["stream"], "stream")]:
            label = ext.replace(".", "-") + ("-stream" if mode == "stream" else "")
            out.append(case(f"rules/r2-pk05/bad-{root}{label}", f"bad/{root} opened as {ext} ({mode}): invalid_release at open ({fx['defect']})",
                            "4.8, 6.1, 7.3",
                            [step("open", err("invalid_release"), file=f"{FIX}/bad/{root}/OTC_20991231{ext}", mode=mode)],
                            requires=["fs"] + req))
    # Station.aliases with a __proto__ system is not compared here: the Node runner's reply encoder rebuilds objects
    # by assignment and drops that key (a harness defect, reported for PK-R2-16); js/test covers the SDK value.
    P = Rel("bad/proto-keys", "20991231")
    out.append(mcase("rules/r2-pk05/proto-keys", "JavaScript Object.prototype names as data (an alias system __proto__ and constructor, a source constructor): they load, are looked up and are counted like any other name", "4.4, 4.5, 7.3",
                     [step("station_by_alias", {"station_id": "OTC-T-0001"}, system="__proto__", alias_id="PX-0001"),
                      step("station_by_alias", {"station_id": "OTC-T-0002"}, system="constructor", alias_id="CX-0002"),
                      step("stats", {"stats": stats(P)}),
                      step("stations", {"station_ids": [x["station_id"] for x in apply_filters(P, P.active, {"source": "constructor"})]}, source="constructor"),
                      step("stations", {"station_ids": []}, source="toString")],
                     root="bad/proto-keys", release="20991231", open_expect={"format_version": "1.1"}))
    return out


# Review round 2, PK-R2-09: one value for one input in every SDK (orchestrator S3; CR D5; CR2 DR7, DR8, DR11, DR24,
# DR26, DR28). The fixtures are bad/ roots that load (build_fixtures.py, BAD).
def rules_r2_pk09():
    out = []
    # S3: a recommended set with no quantity (null, or no key) gives the kind "other", in every SDK and in the
    # stream index each SDK writes
    Q = Rel("bad/quantity-null", "20991231")
    q_ids = ["OTC-T-0019", "OTC-T-0020"]
    out.append(mcase("rules/r2-pk09/quantity-null", "a recommended set with quantity null or no quantity: the station's kind is other, and stats counts it so (orchestrator S3)", "4.4, 6.2",
                     [step("station", {"station": enc_station(Q, Q.by_id[i])}, station_id=i) for i in q_ids] + [
                      step("stats", {"stats": stats(Q)}),
                      step("constant_set", {"set": enc_set(Q, Q.by_id["OTC-T-0020"], Q.rec_set(Q.by_id["OTC-T-0020"]))},
                           station_id="OTC-T-0020", set_id="OTC-T-0020/noaa")],
                     root="bad/quantity-null", release="20991231"))
    qdir = "${cache}/v1/releases/20991231"
    out.append(case("rules/r2-pk09/quantity-null-index", "the stream index of a release with a quantity-null recommended set gives kind other, as the reference index does (orchestrator S3)", "6.2",
                    [net(step("open", {"loaded_from": "download", "datestamp": "20991231"}, release="20991231", base_url=f"{SRV}/bad/quantity-null/",
                              cache_dir="${cache}", mode="stream")),
                     step("station", {"station": enc_station(Q, Q.by_id["OTC-T-0020"])}, station_id="OTC-T-0020"),
                     step("close"),
                     drv("assert_index", path=f"{qdir}/index-v1.json", jsonl=f"{qdir}/OTC_20991231.jsonl", datestamp="20991231")],
                    requires=["fs", "stream"]))
    # D5: a set_id appears once in the release, also across stations
    for ext, req, mode in [(".json", ["json", "eager"], "eager"), (".json.gz", ["json", "eager"], "eager"),
                           (".jsonl", ["eager"], "eager"), (".jsonl", ["stream"], "stream")]:
        label = ext.replace(".", "-") + ("-stream" if mode == "stream" else "")
        out.append(case(f"rules/r2-pk09/set-id-across-stations{label}", f"two stations have a set with the same set_id, opened as {ext} ({mode}): invalid_release at open (D5)",
                        "6.1, 4.8", [step("open", err("invalid_release"), file=f"{FIX}/bad/set-id-across-stations/OTC_20991231{ext}", mode=mode)],
                        requires=["fs"] + req))
    # CR2 DR26: a blank .jsonl line holds only ASCII whitespace (SP, HT, LF, VT, FF, CR); NBSP and NUL are not blank
    B = Rel("bad/blank-lines", "20991231")
    blank_steps = [step("station_count", {"station_count": len(B.active)}),
                   step("tombstone_count", {"tombstone_count": len(B.tombs)}),
                   step("station", {"station": enc_station(B, B.by_id["OTC-T-0002"])}, station_id="OTC-T-0002"),
                   step("station", {"station": enc_station(B, B.by_id["OTC-T-0006"])}, station_id="OTC-T-0006"),
                   step("station", {"station": enc_station(B, B.by_id["OTC-T-0021"])}, station_id="OTC-T-0021")]
    for req, mode in [(["eager"], "eager"), (["stream"], "stream")]:
        out.append(case(f"rules/r2-pk09/blank-lines-jsonl-{mode}", f"lines of only FF, VT, SP, HT, CR in the .jsonl ({mode}) are blank: skipped, and the stations around them are read (CR2 DR26)", "6.2",
                        [step("open", {"loaded_from": "file", "datestamp": "20991231"}, file=f"{FIX}/bad/blank-lines/OTC_20991231.jsonl", mode=mode)] + blank_steps,
                        requires=["fs"] + req))
        for root, what in [("blank-line-nbsp", "one NBSP (U+00A0)"), ("blank-line-nul", "one NUL byte")]:
            out.append(case(f"rules/r2-pk09/{root}-jsonl-{mode}", f"a .jsonl line of {what} ({mode}) is not blank: invalid_release at open (CR2 DR26)", "6.2, 4.8",
                            [step("open", err("invalid_release"), file=f"{FIX}/bad/{root}/OTC_20991231.jsonl", mode=mode)],
                            requires=["fs"] + req))
    # CR2 DR7: filters and stats use the typed enum value; an unknown value is "other", and the raw string matches nothing
    U = Rel("bad/unknown-enums", "20991231")
    ids = lambda f: [s["station_id"] for s in apply_filters(U, U.active, f)]   # noqa: E731
    u15, u16 = U.by_id["OTC-T-0015"], U.by_id["OTC-T-0016"]
    out.append(mcase("rules/r2-pk09/unknown-enums", "format 1.1 enum values a 1.0 reader does not know (type lighthouse, quantity tidal_stream, source_type satellite): each reads as other; type, kind and source_type \"other\" match them, the raw strings match nothing, stats counts other (CR2 DR7)", "4.4, 4.5, 7.3",
                     [step("station", {"station": enc_station(U, U.by_id["OTC-T-0014"])}, station_id="OTC-T-0014"),
                      step("station", {"station": enc_station(U, u15)}, station_id="OTC-T-0015"),
                      step("stations", {"station_ids": ids({"type": "other"})}, type="other"),
                      step("stations", {"station_ids": []}, type="lighthouse"),
                      step("stations", {"station_ids": ids({"kind": "other"})}, kind="other"),
                      step("stations", {"station_ids": []}, kind="tidal_stream"),
                      step("stations", {"station_ids": ids({"source_type": "other"})}, source_type="other"),
                      step("stations", {"station_ids": []}, source_type="satellite"),
                      step("search", {"station_ids": search(U, "harbour", type="other")}, name="harbour", type="other"),
                      step("stats", {"stats": stats(U)}),
                      step("constant_set", {"set": enc_set(U, u15, U.rec_set(u15))}, station_id="OTC-T-0015", set_id=U.rec_set(u15)["set_id"]),
                      step("constant_set", {"set": enc_set(U, u16, U.rec_set(u16))}, station_id="OTC-T-0016", set_id=U.rec_set(u16)["set_id"])],
                     root="bad/unknown-enums", release="20991231", open_expect={"format_version": "1.1"}))
    # CR2 DR8: a station whose status the SDK does not know is no station and no tombstone, in no query and no count
    S = Rel("bad/unknown-status", "20991231")
    out.append(mcase("rules/r2-pk09/unknown-status", "format 1.1: OTC-T-0016's status is retired, which a 1.0 reader does not know: station, tombstone and every query leave it out, and no count includes it (CR2 DR8)", "4.4, 7.3",
                     [step("station", {"station": None}, station_id="OTC-T-0016"),
                      step("tombstone", {"tombstone": None}, station_id="OTC-T-0016"),
                      step("require_station", err("station_not_found"), station_id="OTC-T-0016"),
                      step("station_count", {"station_count": len(S.active)}),
                      step("tombstone_count", {"tombstone_count": len(S.tombs)}),
                      step("stations", {"station_ids": [s["station_id"] for s in apply_filters(S, S.active, {"country": "GBR"})]}, country="GBR"),
                      step("search", {"station_ids": search(S, "harbour point")}, name="harbour point"),
                      step("near", {**near(S, 50.7, -1.3, 5), "tolerance": TOL}, lat=50.7, lon=-1.3, radius_km=5),
                      step("stats", {"stats": stats(S)})],
                     root="bad/unknown-status", release="20991231", open_expect={"format_version": "1.1"}))
    # CR2 DR28: a station line with no status (or null) is an active station
    N = Rel("bad/no-status", "20991231")
    ns_steps = [step("station", {"station": enc_station(N, N.by_id[i])}, station_id=i) for i in ("OTC-T-0019", "OTC-T-0020")] + [
                step("station_count", {"station_count": len(N.active)}),
                step("stations", {"station_ids": [s["station_id"] for s in apply_filters(N, N.active, {"country": "USA"})]}, country="USA"),
                step("stats", {"stats": stats(N)})]
    out.append(mcase("rules/r2-pk09/no-status", "OTC-T-0020's line has no status and OTC-T-0019's has status null: both are active stations, with status active (CR2 DR28)", "4.4, 6.2",
                     ns_steps, root="bad/no-status", release="20991231"))
    ndir = "${cache}/v1/releases/20991231"
    out.append(case("rules/r2-pk09/no-status-index", "the stream index gives status active for a line with no status, as the reference index does (CR2 DR28)", "6.2",
                    [net(step("open", {"loaded_from": "download", "datestamp": "20991231"}, release="20991231", base_url=f"{SRV}/bad/no-status/",
                              cache_dir="${cache}", mode="stream"))] + ns_steps + [
                     step("close"),
                     drv("assert_index", path=f"{ndir}/index-v1.json", jsonl=f"{ndir}/OTC_20991231.jsonl", datestamp="20991231")],
                    requires=["fs", "stream"]))
    # CR2 DR24: reference_station and subordinates_of with null, an unknown station or a foreign Station are
    # invalid_argument. The runner passes station_id null as null, and with station_on looks the station up in a held
    # release. The held release is good R1 (update keeps it open); its OTC-T-0021 is removed in R2, so it is a Station
    # of another release that is not in this one.
    R2 = Rel("good", "20991231.2")
    G = f"{SRV}/good/"
    subs = sorted(s["station_id"] for s in R2.active if s["type"] == "subordinate"
                  and (s.get("subordinate_offsets") or {}).get("reference_station_id") == "OTC-T-0001")
    link_steps = []
    for op in ("reference_station", "subordinates_of"):
        link_steps += [step(op, err("invalid_argument"), station_id=None),
                       step(op, err("invalid_argument"), station_id="OTC-T-0021", station_on="r1")]
    out.append(case("rules/r2-pk09/links-bad-station", "reference_station and subordinates_of with a null station, or a Station of another release that is not in this one: invalid_argument, as for attribution (CR2 DR24)", "4.4, 4.8",
                    [drv("server_rules", rules=[{"match": r"/good/OTC_latest(-f1)?\.json$", "action": "json", "file": "good/OTC_index.json", "pointer": "/releases/1"}]),
                     net(step("open", {"loaded_from": "download", "datestamp": "20991231"}, base_url=G, cache_dir="${cache}", mode="stream")),
                     step("hold_release", None, name="r1"),
                     drv("server_rules", rules=[]),
                     net(step("update", {"updated": True, "from": "20991231", "to": "20991231.2"})),
                     step("reference_station", {"station_id": "OTC-T-0001"}, station_id="OTC-T-0003"),
                     step("subordinates_of", {"station_ids": subs}, station_id="OTC-T-0001"),
                     step("station", {"station": {"$type": "object"}}, station_id="OTC-T-0021", on="r1")] + link_steps,
                    requires=["fs", "stream"]))
    bdir = "${cache}/v1/releases/20991231"
    out.append(case("rules/r2-pk09/blank-lines-index", "the stream index of a .jsonl with blank lines has one entry per station line, at the offsets of the reference index (CR2 DR26)", "6.2",
                    [net(step("open", {"loaded_from": "download", "datestamp": "20991231"}, release="20991231", base_url=f"{SRV}/bad/blank-lines/",
                              cache_dir="${cache}", mode="stream"))] + blank_steps + [
                     step("close"),
                     drv("assert_index", path=f"{bdir}/index-v1.json", jsonl=f"{bdir}/OTC_20991231.jsonl", datestamp="20991231")],
                    requires=["fs", "stream"]))
    return out


# The exact texts of SDK spec 7.1 (K-NC fixtures and cases), byte for byte. The oracle must give each of them:
# build_cases.py fails when it does not, so the spec and the cases cannot drift apart.
KNC_TEXT = {
    "non-commercial-exact": "Tidal constants: OpenTideConstants 20991231.3, doi:10.5072/zenodo.1, CC BY 4.0. Sources: Example Meteorological Agency: Synthetic test data in the style of JMA.; Example Ocean Service: Synthetic test data in the style of a public-domain US agency.. Non-commercial use only: Example Meteorological Agency (LicenseRef-JMA-Test, https://example.org/jma-test-terms)",
    "all-licences-with-nc": "Tidal constants: OpenTideConstants 20991231.3, doi:10.5072/zenodo.1, CC BY 4.0. Sources: Example Tide Model Group: Example tide model, interpolated by OpenTideConstants tests.; Example Gauge Agency via GESLA: Contains synthetic test data in the style of GESLA-4.; Example Meteorological Agency: Synthetic test data in the style of JMA.; Example Mapping Authority: Synthetic test data, Example Mapping Authority.; Example Ocean Service: Synthetic test data in the style of a public-domain US agency.. Non-commercial use only: Example Meteorological Agency (LicenseRef-JMA-Test, https://example.org/jma-test-terms)",
    "non-commercial-per-licence": "Tidal constants: OpenTideConstants 20991231.2, doi:10.5072/zenodo.1, CC BY 4.0. Sources: Example Mapping Authority: Synthetic test data, Example Mapping Authority.; Example Restricted Agency: Synthetic restricted test data.; Example Ocean Service: Synthetic test data in the style of a public-domain US agency.. Non-commercial use only: Example Restricted Agency (LicenseRef-NC-Test, https://example.org/nc-test-terms); Example Restricted Agency (LicenseRef-NC-Test-2, https://example.org/nc-test-2-terms)",
    "null-provider-1": "Tidal constants: OpenTideConstants 20991231, https://data.opentideconstants.org/OTC_20991231.json, CC BY 4.0. Sources: Anonymous synthetic test data.; Example tide model, interpolated by OpenTideConstants tests.; Example Gauge Agency via GESLA: Contains synthetic test data in the style of GESLA-4.; Example Mapping Authority: Synthetic test data, Example Mapping Authority.; Example Ocean Service: Synthetic test data in the style of a public-domain US agency.. Non-commercial use only: anon (LicenseRef-Anon-Test, https://example.org/anon-terms)",
    "null-provider-2": "Tidal constants: OpenTideConstants 20991231, https://data.opentideconstants.org/OTC_20991231.json, CC BY 4.0. Sources: Example tide model, interpolated by OpenTideConstants tests.; Example Ocean Service: Synthetic test data in the style of a public-domain US agency.",
    "empty-scope-v1": "Tidal constants: OpenTideConstants 20991231.3, doi:10.5072/zenodo.1, CC BY 4.0.",
    "default-off-0188": "Tidal constants: OpenTideConstants 20991231.2, doi:10.5072/zenodo.1, CC BY 4.0. Sources: Example Mapping Authority: Synthetic test data, Example Mapping Authority.; Example Restricted Agency: Synthetic restricted test data.. Non-commercial use only: Example Restricted Agency (LicenseRef-NC-Test, https://example.org/nc-test-terms)",
    "default-off-0189": "Tidal constants: OpenTideConstants 20991231.2, doi:10.5072/zenodo.1, CC BY 4.0. Sources: Example Tide Model Group: Example tide model, interpolated by OpenTideConstants tests.; Example Mapping Authority: Synthetic test data, Example Mapping Authority.; Example Restricted Agency: Synthetic restricted test data.. Non-commercial use only: Example Restricted Agency (LicenseRef-NC-Test, https://example.org/nc-test-terms)",
    "default-off-0190": "Tidal constants: OpenTideConstants 20991231.2, doi:10.5072/zenodo.1, CC BY 4.0. Sources: Example Restricted Agency: Synthetic restricted test data.; Example Ocean Service: Synthetic test data in the style of a public-domain US agency.. Non-commercial use only: Example Restricted Agency (LicenseRef-NC-Test, https://example.org/nc-test-terms)",
    "co-0186": "Tidal constants: OpenTideConstants 20991231.2, doi:10.5072/zenodo.1, CC BY 4.0. Sources: Example Mapping Authority: Synthetic test data, Example Mapping Authority.; Example Ocean Service: Synthetic test data in the style of a public-domain US agency.",
    "co-0190": "Tidal constants: OpenTideConstants 20991231.2, doi:10.5072/zenodo.1, CC BY 4.0. Sources: Example Ocean Service: Synthetic test data in the style of a public-domain US agency.",
    "co-0189": "Tidal constants: OpenTideConstants 20991231.2, doi:10.5072/zenodo.1, CC BY 4.0. Sources: Example Tide Model Group: Example tide model, interpolated by OpenTideConstants tests.",
    "co-all": "Tidal constants: OpenTideConstants 20991231.2, doi:10.5072/zenodo.1, CC BY 4.0. Sources: Example Terms Agency: Synthetic test data, Example Terms Agency.; Example Tide Model Group: Example tide model, interpolated by OpenTideConstants tests.; Example Gauge Agency via GESLA: Contains synthetic test data in the style of GESLA-4.; Example Mapping Authority: Synthetic test data, Example Mapping Authority.; Example Ocean Service: Synthetic test data in the style of a public-domain US agency.",
    "co-empty": "Tidal constants: OpenTideConstants 20991231.2, doi:10.5072/zenodo.1, CC BY 4.0.",
    "co-good-0004": "Tidal constants: OpenTideConstants 20991231.2, doi:10.5072/zenodo.1, CC BY 4.0. Sources: Example Tide Model Group: Example tide model, interpolated by OpenTideConstants tests.",
    "good-0004": "Tidal constants: OpenTideConstants 20991231.2, doi:10.5072/zenodo.1, CC BY 4.0. Sources: Example Tide Model Group: Example tide model, interpolated by OpenTideConstants tests.; Example Ocean Service: Synthetic test data in the style of a public-domain US agency.",
}


def knc_text(key, got):
    """The oracle's text, which must be the spec's exact text for key."""
    if got != KNC_TEXT[key]:
        raise SystemExit(f"K-NC text {key}: the oracle gives\n  {got!r}\nthe spec says\n  {KNC_TEXT[key]!r}")
    return got


def group_knc():
    """K-NC DR104 to DR106 (SDK spec 4.2, 4.6, 7.1 K-NC fixtures and cases): the Licence fields commercial_use,
    restriction and terms_url; the non-commercial notice of attribution; the empty scope; commercial_only."""
    out = []
    V = Rel("v1", V1)
    K = Rel("knc", "20991231.2")
    KC = Rel("knc", "20991231.2", commercial_only=True)
    R2 = Rel("good", "20991231.2")
    G2C = Rel("good", "20991231.2", commercial_only=True)
    NPC = Rel("bad/licence-provider-null-nc", "20991231")
    NP = Rel("bad/licence-provider-null", "20991231")
    CO = {"commercial_only": True}

    def att(rel, ids=None):
        return step("attribution", {"attribution": attribution(rel, ids)}, **({} if ids is None else {"station_ids": ids}))

    def att_text(key, rel, ids=None):
        return step("attribution", {"attribution": knc_text(key, attribution(rel, ids))},
                    **({} if ids is None else {"station_ids": ids}))

    def rec(rel, sid, expect_id):
        got = rel.eff_set(rel.by_id[sid])
        got = got["set_id"] if got else None
        if got != expect_id:
            raise SystemExit(f"K-NC: {sid} recommended set {got!r}, the spec says {expect_id!r}")
        return step("recommended_set", {"set_id": got}, station_id=sid)

    # ---- DR104: the Licence fields
    out.append(mcase("release/licence-fields-nc", "v1: jma has commercial_use false, restriction and terms_url; every other licence true, null, null (K-NC DR104)", "4.6",
                     [step("licences", {"licences": [pick(x, LICENCE_FIELDS) for x in V.doc["licences"]]}),
                      step("licence", {"licence": pick(V.licences["jma"], LICENCE_FIELDS)}, licence_id="jma")],
                     root="v1", release=V1))
    out.append(mcase("release/licence-fields-commercial-with-terms", "knc: c-terms is commercial with restriction and terms_url; nc-test-2 is non-commercial (K-NC DR104)", "4.6",
                     [step("licence", {"licence": pick(K.licences["c-terms"], LICENCE_FIELDS)}, licence_id="c-terms"),
                      step("licence", {"licence": pick(K.licences["nc-test-2"], LICENCE_FIELDS)}, licence_id="nc-test-2"),
                      step("licences", {"licences": [pick(x, LICENCE_FIELDS) for x in K.doc["licences"]]})],
                     root="knc", release="20991231.2"))
    for root in ["licence-commercial-use-missing", "licence-commercial-use-null", "licence-commercial-use-string",
                 "licence-nc-no-restriction", "licence-nc-no-terms-url", "licence-nc-no-spdx",
                 "licence-restriction-not-string", "licence-terms-url-not-string",
                 "licence-restriction-null", "licence-terms-url-null"]:
        for ext, req, mode in [(".json", ["json", "eager"], "eager"), (".json.gz", ["json", "eager"], "eager"),
                               (".jsonl", ["eager"], "eager"), (".jsonl", ["stream"], "stream")]:
            label = ext.replace(".", "-") + ("-stream" if mode == "stream" else "")
            out.append(case(f"release/bad-{root}{label}", f"bad/{root} opened as {ext} ({mode}): invalid_release at open (K-NC DR104)", "4.6, 4.8",
                            [step("open", err("invalid_release"), file=f"{FIX}/bad/{root}/OTC_20991231{ext}", mode=mode)],
                            requires=["fs"] + req))
    # ---- DR105: the non-commercial notice (without the option)
    out.append(mcase("attribution/non-commercial-exact", "v1, stations OTC-T-0106 and OTC-T-0101: the notice names jma once, after the Sources list (K-NC DR105)", "4.6",
                     [att_text("non-commercial-exact", V, ["OTC-T-0106", "OTC-T-0101"])], root="v1", release=V1))
    out.append(mcase("attribution/all-licences-with-nc", "v1, no stations: every licence, then the notice for jma (K-NC DR105)", "4.6",
                     [att_text("all-licences-with-nc", V)], root="v1", release=V1))
    for ids in (None, ["OTC-T-0006", "OTC-T-0010", "OTC-T-0007"]):
        if "Non-commercial" in attribution(R2, ids):
            raise SystemExit("K-NC: the all-commercial control has a notice")
    out.append(mcase("attribution/all-commercial-unchanged", "good 20991231.2, where every licence is commercial: the texts of release/attribution-all-20991231.2 and release/attribution-ordered-by-licence-id, with no notice (K-NC DR105)", "4.6",
                     [att(R2), att(R2, ["OTC-T-0006", "OTC-T-0010", "OTC-T-0007"])]))
    out.append(mcase("attribution/non-commercial-per-licence", "knc, stations OTC-T-0187 and OTC-T-0188: one notice entry per non-commercial licence, also for one provider (K-NC DR105)", "4.6",
                     [att_text("non-commercial-per-licence", K, ["OTC-T-0187", "OTC-T-0188"])], root="knc", release="20991231.2"))
    if attribution(NP, ["OTC-T-0004"]) != KNC_TEXT["null-provider-2"]:
        raise SystemExit("K-NC: null-provider step 2 differs from rules/pk15/attribution-null-provider")
    out.append(mcase("attribution/non-commercial-null-provider", "a non-commercial licence with a null provider: the notice entry is {licence_id} ({spdx}, {terms_url}); a commercial null-provider licence gets no entry (K-NC DR105)", "4.6",
                     [att_text("null-provider-1", NPC), att_text("null-provider-2", NPC, ["OTC-T-0004"])],
                     root="bad/licence-provider-null-nc", release="20991231"))
    out.append(mcase("attribution/empty-scope", "v1, station OTC-T-0104 (a reference station with no recommended set): no licence in scope, the dataset header alone (K-NC DR106, spec 4.6)", "4.6",
                     [att_text("empty-scope-v1", V, ["OTC-T-0104"])], root="v1", release=V1))
    # ---- DR106: commercial_only
    knc = {"root": "knc", "release": "20991231.2"}
    out.append(mcase("commercial-only/default-off", "knc without the option: the release's recommended set, and the CR2 DR1 walk with the notice (K-NC DR106)", "4.2, 4.6",
                     [rec(K, "OTC-T-0181", "OTC-T-0181/x-nc"),
                      att_text("default-off-0188", K, ["OTC-T-0188"]),
                      att_text("default-off-0189", K, ["OTC-T-0189"]),
                      att_text("default-off-0190", K, ["OTC-T-0190"])], **knc))

    def co_case(cid, title, steps, root="knc", release="20991231.2"):
        c = mcase(cid, title, "4.2, 4.4, 4.5, 4.6", steps, root=root, release=release)
        c["matrix"]["open_args"] = dict(CO)
        return c
    out.append(co_case("commercial-only/keep-commercial-recommended", "OTC-T-0184 keeps its recommended set a-flag (commercial), although b-ok is ok; OTC-T-0181 shows that the option is on (K-NC DR106)",
                       [rec(KC, "OTC-T-0184", "OTC-T-0184/a-flag"), rec(KC, "OTC-T-0181", "OTC-T-0181/w-ok")]))
    s181 = KC.by_id["OTC-T-0181"]
    order = [c["set_id"] for c in sets_in_order(s181, rel=KC)]
    if order != [f"OTC-T-0181/{x}" for x in ("w-ok", "v-ok2", "x-nc", "y-flagged", "z-current")]:
        raise SystemExit(f"K-NC: OTC-T-0181 constant_sets {order}")
    out.append(co_case("commercial-only/ok-before-flagged", "OTC-T-0181 gives w-ok: not y-flagged (earlier, flagged), not z-current (another quantity), not v-ok2 (later in file order); constant_sets puts it first and only it is recommended (K-NC DR106)",
                       [rec(KC, "OTC-T-0181", "OTC-T-0181/w-ok"),
                        step("constant_sets", {"set_ids": order}, station_id="OTC-T-0181"),
                        step("station", {"station": enc_station(KC, s181)}, station_id="OTC-T-0181")]
                       + [step("constant_set", {"set": enc_set(KC, s181, cs)}, station_id="OTC-T-0181", set_id=cs["set_id"])
                          for cs in s181["constant_sets"]]))
    out.append(co_case("commercial-only/flagged-fallback", "OTC-T-0182 gives b-flag (commercial, flagged), never the no_constants set a-noc (K-NC DR106)",
                       [rec(KC, "OTC-T-0182", "OTC-T-0182/b-flag")]))
    s183 = KC.by_id["OTC-T-0183"]
    if [c["set_id"] for c in sets_in_order(s183, rel=KC)] != ["OTC-T-0183/a-nc", "OTC-T-0183/c-cur"] or KC.kind(s183) != "tide":
        raise SystemExit("K-NC: OTC-T-0183")
    out.append(co_case("commercial-only/no-commercial-set", "OTC-T-0183 has no recommended set under the option; constant_sets still lists every set; its kind is still tide; stations and search still return it (K-NC DR106)",
                       [rec(KC, "OTC-T-0183", None),
                        step("constant_sets", {"set_ids": [c["set_id"] for c in sets_in_order(s183, rel=KC)]}, station_id="OTC-T-0183"),
                        step("constant_sets", {"set_ids": [c["set_id"] for c in sets_in_order(s183, True, rel=KC)]}, station_id="OTC-T-0183", include_no_constants=True),
                        step("station", {"station": enc_station(KC, s183)}, station_id="OTC-T-0183"),
                        step("stations", {"station_ids": [x["station_id"] for x in discovery_filters(KC, KC.active, {})]}),
                        step("search", {"station_ids": search(KC, "KNC 0183", query_filters=discovery_filters)}, name="KNC 0183")]))
    with_opt = [x["station_id"] for x in discovery_filters(KC, KC.active, {"source_type": "official"})]
    without = [x["station_id"] for x in discovery_filters(K, K.active, {"source_type": "official"})]
    if with_opt != ["OTC-T-0181", "OTC-T-0183", "OTC-T-0185", "OTC-T-0186", "OTC-T-0190"] or \
            without != ["OTC-T-0181", "OTC-T-0182", "OTC-T-0183", "OTC-T-0185", "OTC-T-0186", "OTC-T-0187",
                        "OTC-T-0188", "OTC-T-0189", "OTC-T-0190"]:
        raise SystemExit(f"K-NC: source_type filter {with_opt} / {without}")
    out.append(co_case("commercial-only/source-type-filter", "source_type matches an eligible direct or actual offsets-reference path; commercial discovery excludes non-commercial legs (SDK-QFILT)",
                       [step("stations", {"station_ids": with_opt}, source_type="official"),
                        step("iter_stations", {"station_ids": with_opt}, source_type="official"),
                        {"op": "open", "matrix_open": {"commercial_only": None}},
                        step("stations", {"station_ids": without}, source_type="official")]))
    out.append(co_case("commercial-only/subordinate-tides", "OTC-T-0186: the one-link offsets path (kartverket, noaa); OTC-T-0190: no effective set, so the offsets path (noaa twice, one licence) (K-NC DR106)",
                       [att_text("co-0186", KC, ["OTC-T-0186"]), att_text("co-0190", KC, ["OTC-T-0190"])]))
    out.append(co_case("commercial-only/no-usable-tides", "OTC-T-0187 (non-commercial offsets licence) and OTC-T-0188 (non-commercial reference set) add no licence; OTC-T-0189 uses its own set, not its offsets (K-NC DR106)",
                       [att_text("co-0186", KC, ["OTC-T-0187", "OTC-T-0188", "OTC-T-0186"]),
                        att_text("co-0189", KC, ["OTC-T-0189"])]))
    out.append(co_case("commercial-only/attribution-all", "no stations: every commercial licence of the release, and no notice (K-NC DR106)",
                       [att_text("co-all", KC)]))
    out.append(co_case("commercial-only/empty-scope", "stations with no usable tides: the dataset header alone (K-NC DR106)",
                       [att_text("co-empty", KC, ["OTC-T-0187", "OTC-T-0188"])]))
    steps = [att(R2), att(R2, ["OTC-T-0006", "OTC-T-0010", "OTC-T-0007"]), att(R2, ["OTC-T-0003"])]
    for st in steps:   # the texts without the option, which the option must not change here
        st_args = st.get("args", {}).get("station_ids")
        if attribution(G2C, st_args) != st["expect"]["attribution"]:
            raise SystemExit(f"K-NC: good attribution differs under the option for {st_args}")
    for x in G2C.active:
        if G2C.eff_set(x) is not R2.rec_set(R2.by_id[x["station_id"]]) and (G2C.eff_set(x) or {}).get("set_id") != (R2.rec_set(R2.by_id[x["station_id"]]) or {}).get("set_id"):
            raise SystemExit(f"K-NC: {x['station_id']} changes its recommended set under the option in good")
    if attribution(R2, ["OTC-T-0004"]) != KNC_TEXT["good-0004"]:
        raise SystemExit("K-NC: release/attribution-subordinate-with-own-set differs from the spec text")
    steps += [step("recommended_set", {"set_id": R2.rec_set(x)["set_id"] if R2.rec_set(x) else None}, station_id=x["station_id"])
              for x in R2.active]
    steps.append(att_text("co-good-0004", G2C, ["OTC-T-0004"]))
    out.append(co_case("commercial-only/all-commercial-unchanged", "good 20991231.2 (every licence commercial) under the option: the attribution texts and every recommended set as without it; OTC-T-0004 (a subordinate with its own set) gives only its set's licence (K-NC DR106)",
                       steps, root="good"))
    return out + [discovery_case("knc", R2, "strict"), discovery_case("knc", R2, "as_published_upstream")]


GROUPS = {
    "load": lambda R2, R1: group_load(),
    "release": group_release,
    "stations": group_stations,
    "sets": lambda R2, R1: group_sets(R2),
    "search": lambda R2, R1: group_search(R2),
    "geo": lambda R2, R1: group_geo(R2),
    "tolerant": lambda R2, R1: group_tolerant(),
    "network": lambda R2, R1: group_network() + group_network_cr2_pk11(),
    "update": lambda R2, R1: group_update(),
    "cache": lambda R2, R1: group_cache(),
    "download": lambda R2, R1: group_download(),
    "v1": lambda R2, R1: group_v1(),
    "format": lambda R2, R1: group_format(),
    "rules": lambda R2, R1: group_rules(),
    "lifecycle": lambda R2, R1: group_lifecycle(R2),
    "knc": lambda R2, R1: group_knc(),
}


def build(outdir: Path, crossdir: Path):
    R2, R1 = Rel("good", "20991231.2"), Rel("good", "20991231")
    crossdir.mkdir(parents=True, exist_ok=True)
    cross = group_cross(R2)
    seen = set()
    for c in cross:   # cross ids are unique too, and never the id of a plain case
        if c["id"] in seen:
            raise SystemExit(f"duplicate case id {c['id']}")
        seen.add(c["id"])
    doc = {"suite_version": SUITE_VERSION, "group": "cross",
           "description": "Generated by conformance/tools/build_cases.py from conformance/fixtures; do not edit. "
                          "Run with driver.py --cross NAME=COMMAND (two or more runners).",
           "cases": cross}
    # Bytes, not text: a text-mode write gives CRLF on Windows, and --check
    # compares bytes with the LF files in git.
    (crossdir / "cross.json").write_bytes((json.dumps(doc, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
    outdir.mkdir(parents=True, exist_ok=True)
    for name, fn in GROUPS.items():
        cases = fn(R2, R1)
        for c in cases:
            if c["id"] in seen:
                raise SystemExit(f"duplicate case id {c['id']}")
            seen.add(c["id"])
        doc = {"suite_version": SUITE_VERSION, "group": name,
               "description": "Generated by conformance/tools/build_cases.py from conformance/fixtures; do not edit.",
               "cases": cases}
        (outdir / f"{name}.json").write_bytes((json.dumps(doc, indent=1, ensure_ascii=False) + "\n").encode("utf-8"))
    return len(seen) - len(cross)


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
