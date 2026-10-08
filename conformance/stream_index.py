"""The reference builder for the stream index, index-v1.json (SDK spec §6.2).

The driver's `assert_index` step compares an index that an SDK wrote with the
index that this module builds from the same .jsonl file. So this module is the
executable form of the index format in §6.2: every SDK must write exactly these
keys, with these values (only `by` is free). Standard library only.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
INDEX_VERSION = 1
TOP_KEYS = ["index_version", "datestamp", "jsonl", "jsonl_sha256", "jsonl_size", "by", "stations"]
ENTRY_KEYS = ["offset", "length", "station_id", "status", "name", "name_folded", "country", "type", "lat", "lon",
              "kind", "aliases", "reference_station_id", "offsets_licence_id", "recommended_set_id", "sets"]
SET_KEYS = ["set_id", "source", "source_type", "quantity", "qc_status", "convention_id", "licence_id", "constituents"]
MAX_REF_DEPTH = 16

_FOLD = None


def fold(name: str) -> str:
    global _FOLD
    if _FOLD is None:
        doc = json.loads((HERE / "name_fold.json").read_text(encoding="utf-8"))
        _FOLD = {int(k, 16): v for k, v in doc["map"].items()}
    folded = "".join(_FOLD.get(ord(ch), ch) for ch in name)
    return re.sub(r"[ \t\n\r\f\v]+", " ", folded).strip(" ")


def _s(d, k):
    v = d.get(k)
    return v if isinstance(v, str) else None


def _n(d, k):
    v = d.get(k)
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def entry(d: dict, offset: int, length: int) -> dict:
    """The index entry of one line. `kind` is the station's own kind here; resolve_kinds finishes it."""
    off = d.get("subordinate_offsets") if isinstance(d.get("subordinate_offsets"), dict) else {}
    aliases = {}
    for system, ids in (d.get("aliases") or {}).items():
        aliases[system] = [ids] if isinstance(ids, str) else [x for x in ids if isinstance(x, str)]
    sets = []
    rec_id = _s(d, "recommended_set_id")
    kind = None
    for cs in d.get("constant_sets") or []:
        sets.append({k: _s(cs, k) for k in SET_KEYS[:-1]}
                    | {"constituents": [c["name"] for c in cs.get("constituents") or [] if isinstance(c.get("name"), str)]})
        if rec_id is not None and cs.get("set_id") == rec_id:
            kind = {"water_level": "tide", "current": "current"}.get(cs.get("quantity"), "other")
    name = _s(d, "name")
    return {
        "offset": offset, "length": length, "station_id": d["station_id"], "status": d["status"],
        "name": name, "name_folded": fold(name) if name is not None else None,
        "country": _s(d, "country"), "type": _s(d, "type"), "lat": _n(d, "lat"), "lon": _n(d, "lon"),
        "kind": kind, "aliases": aliases,
        "reference_station_id": _s(off, "reference_station_id"), "offsets_licence_id": _s(off, "licence_id"),
        "recommended_set_id": rec_id, "sets": sets,
    }


def resolve_kinds(entries: list) -> None:
    """A station with no recommended set, of type subordinate, takes the kind of its reference station
    (followed through at most 16 links among the active stations; a loop or a dead end gives null)."""
    by_id = {e["station_id"]: e for e in entries if e["status"] == "active"}
    own = {sid: e["kind"] for sid, e in by_id.items()}

    def kind_of(sid, depth):
        e = by_id[sid]
        if own[sid] is not None:
            return own[sid]
        if e["type"] == "subordinate" and e["reference_station_id"] in by_id and depth < MAX_REF_DEPTH \
                and e["reference_station_id"] != sid:
            return kind_of(e["reference_station_id"], depth + 1)
        return None

    for sid, e in by_id.items():
        e["kind"] = kind_of(sid, 0)


def build(jsonl: Path, datestamp: str) -> dict:
    data = jsonl.read_bytes()
    entries = []
    offset = 0
    for line in data.splitlines(keepends=True):
        body = line.rstrip(b"\n").rstrip(b"\r")
        if body.strip():
            entries.append(entry(json.loads(body.decode("utf-8")), offset, len(body)))
        offset += len(line)
    resolve_kinds(entries)
    return {"index_version": INDEX_VERSION, "datestamp": datestamp, "jsonl": f"OTC_{datestamp}.jsonl",
            "jsonl_sha256": hashlib.sha256(data).hexdigest(), "jsonl_size": len(data),
            "by": None, "stations": entries}


def _same(a, b):
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    return type(a) is type(b) and a == b


def compare(actual, expected: dict) -> list:
    """Problems with an index an SDK wrote, against the reference. Exact keys, exact values."""
    if not isinstance(actual, dict):
        return ["the index is not a JSON object"]
    out = []
    if sorted(actual) != sorted(TOP_KEYS):
        out.append(f"top-level keys {sorted(actual)}, expected {sorted(TOP_KEYS)}")
    if not (isinstance(actual.get("by"), str) and re.match(r"^opentideconstants-[a-z]+/\S+$", actual["by"])):
        out.append(f"by is {actual.get('by')!r}, expected opentideconstants-<lang>/<version>")
    for k in TOP_KEYS:
        if k not in ("by", "stations") and not _same(actual.get(k), expected[k]):
            out.append(f"{k} is {actual.get(k)!r}, expected {expected[k]!r}")
    st = actual.get("stations")
    if not isinstance(st, list):
        return out + ["stations is not an array"]
    if len(st) != len(expected["stations"]):
        out.append(f"{len(st)} entries, expected {len(expected['stations'])}")
    for i, (a, e) in enumerate(zip(st, expected["stations"])):
        where = f"stations[{i}] ({e['station_id']})"
        if not isinstance(a, dict):
            out.append(f"{where}: not an object")
            continue
        if sorted(a) != sorted(ENTRY_KEYS):
            out.append(f"{where}: keys {sorted(a)}, expected {sorted(ENTRY_KEYS)}")
        for k in ENTRY_KEYS:
            if k == "sets":
                continue
            if not _same(a.get(k), e[k]):
                out.append(f"{where}: {k} is {a.get(k)!r}, expected {e[k]!r}")
        sa = a.get("sets")
        if not isinstance(sa, list) or len(sa) != len(e["sets"]):
            out.append(f"{where}: sets is {sa!r:.200}, expected {len(e['sets'])} sets")
            continue
        for j, (x, y) in enumerate(zip(sa, e["sets"])):
            if not isinstance(x, dict) or sorted(x) != sorted(SET_KEYS):
                out.append(f"{where}: sets[{j}] keys {sorted(x) if isinstance(x, dict) else x!r}, expected {sorted(SET_KEYS)}")
                continue
            for k in SET_KEYS:
                if not _same(x[k], y[k]):
                    out.append(f"{where}: sets[{j}].{k} is {x[k]!r}, expected {y[k]!r}")
    return out
