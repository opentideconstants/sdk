"""One loaded release (spec §3, §4.3 to §4.7, §6). Eager mode parses everything at load; stream mode
keeps an index of the .jsonl lines and reads stations on demand."""
from __future__ import annotations

import gzip
import hashlib
import json
import logging
import math
import os
import re
import threading
import zlib
from collections import OrderedDict
from pathlib import Path
from types import MappingProxyType
from typing import Iterator, List, Optional, Sequence, Tuple

from . import _enums as E
from ._errors import (ChecksumError, FileError, InvalidArgumentError, InvalidReleaseError, ReaderTooOldError,
                      StationNotFoundError, StationRemovedError, UnsupportedFormatError)
from ._fold import fold
from ._cache_json import encode_cache_json
from ._models import (Convention, FileInfo, Licence, Nearby, Station, Stats, Tombstone, _is_finite, build_station,
                      freeze, parse_time, _check_historical_offsets, check_station_types)

SUPPORTED_FORMAT_MAJORS = (1,)
SUPPORTED_FORMAT_VERSION = "1.0"
EARTH_R_KM = 6371.0088
INDEX_VERSION = 1
LRU_SIZE = 256
_MAX_LINKS = 16  # the reference links a walk follows (spec §6.2 kind, §4.6 attribution)
_USABLE = ("ok", "flagged")  # qc_status of a set with constants (spec §4.3); QcStatus members compare equal
DATA_URL = "https://data.opentideconstants.org/"
_log = logging.getLogger("opentideconstants")


# --------------------------------------------------------------------------- reading files

def _validate_attribution_item(st):
    if not isinstance(st, Station):
        raise InvalidArgumentError("stations must be a list of Station objects")


def _validate_attribution_container(stations):
    if stations is not None and (isinstance(stations, (str, bytes)) or not hasattr(stations, "__iter__")):
        raise InvalidArgumentError("stations must be a list of Station objects")


def _validate_station_argument(station, what):
    if not isinstance(station, Station):
        raise InvalidArgumentError(f"{what}: station must be a Station")


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as e:
        raise FileError(f"cannot read {path}: {e}", path=str(path), cause=e) from e


_SURROGATE_ESCAPE = re.compile(rb"\\u[dD][89a-fA-F]")


def _no_lone_surrogate(v, what):
    """A JSON text whose \\u escapes make an unpaired surrogate is not valid Unicode: invalid_release (CR D17)."""
    stack = [v]
    while stack:
        x = stack.pop()
        if isinstance(x, str):
            try:
                x.encode("utf-8")
            except UnicodeEncodeError as e:
                raise InvalidReleaseError(f"{what}: a string with an unpaired surrogate") from e
        elif isinstance(x, dict):
            stack.extend(x.keys())
            stack.extend(x.values())
        elif isinstance(x, list):
            stack.extend(x)


def _json(data: bytes, what: str):
    try:
        v = json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, RecursionError) as e:
        raise InvalidReleaseError(f"{what}: not JSON: {e}") from e
    if _SURROGATE_ESCAPE.search(data):
        _no_lone_surrogate(v, what)
    return v


_VERSION_RE = re.compile(r"\A(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\Z")  # ASCII digits only, no leading zeros


def version_key(v):
    """(MAJOR, MINOR) of a format version string, or None when it is not MAJOR.MINOR (spec §7.4, CR D9)."""
    m = _VERSION_RE.match(v) if isinstance(v, str) else None
    return None if m is None else (int(m.group(1)), int(m.group(2)))


def readable(format_version, min_reader_version) -> bool:
    """True when this SDK reads a release with these versions (spec §7.4): a supported major, and a
    min_reader_version no newer than SUPPORTED_FORMAT_VERSION (a missing one does not block; a malformed one
    does: the SDK never guesses a version, CR D9)."""
    fv = version_key(format_version)
    if fv is None or fv[0] not in SUPPORTED_FORMAT_MAJORS:
        return False
    if min_reader_version is None:
        return True
    mr = version_key(min_reader_version)
    return mr is not None and mr <= version_key(SUPPORTED_FORMAT_VERSION)


def check_format(fv, min_reader_version=None, datestamp=None) -> None:
    """Raise unless this SDK reads a release with these versions. A version that is present but is not
    MAJOR.MINOR is invalid_release (CR D9)."""
    key = version_key(fv)
    if key is None:
        raise InvalidReleaseError(f"format_version missing or not MAJOR.MINOR: {fv!r}")
    if key[0] not in SUPPORTED_FORMAT_MAJORS:
        raise UnsupportedFormatError(f"format {fv} is not supported (supported majors: {list(SUPPORTED_FORMAT_MAJORS)})")
    if min_reader_version is None:
        return
    mr = version_key(min_reader_version)
    if mr is None:
        raise InvalidReleaseError(f"release.min_reader_version is not MAJOR.MINOR: {min_reader_version!r}")
    if mr > version_key(SUPPORTED_FORMAT_VERSION):
        raise ReaderTooOldError(f"release {datestamp or '?'} needs a reader for format {min_reader_version}; "
                                f"this SDK reads format {SUPPORTED_FORMAT_VERSION}")


def meta_path_for(jsonl: Path) -> Path:
    return jsonl.with_name(jsonl.name[: -len(".jsonl")] + ".meta.json")


def _check_type(name, value, types, allow_none=True):
    if value is None and allow_none:
        return
    if isinstance(value, bool) and bool not in types:
        raise InvalidArgumentError(f"{name}: wrong type {type(value).__name__}")
    if not isinstance(value, types):
        raise InvalidArgumentError(f"{name}: wrong type {type(value).__name__}")


def _number(name, v, lo=None, hi=None, allow_none=False):
    if v is None and allow_none:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise InvalidArgumentError(f"{name} must be a number")
    try:
        f = float(v)
    except OverflowError as e:
        raise InvalidArgumentError(f"{name} out of range: {v}") from e
    if math.isnan(f) or (lo is not None and f < lo) or (hi is not None and f > hi):
        raise InvalidArgumentError(f"{name} out of range: {v}")
    return f


def _limit(limit):
    """limit: None for no limit, or an integer of 1 or more (spec §4.4, CR D36)."""
    if limit is None:
        return None
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise InvalidArgumentError(f"limit must be an integer of 1 or more, or None, not {limit!r}")
    return limit


def _typed(cls, v):
    """The value of an enum field as the Station reports it: None, a schema value, or "other" for a value this
    SDK does not know (spec 7.3). Filters and stats use it (CR2 DR7)."""
    m = E.enum_or_raw(cls, v)
    return None if m is None else m.value


_OFFSETS_SOURCE = "noaa"  # the source of every subordinate_offsets in format 1.0 (spec §4.2, K-NC DR106)


def _effective_id(e, lic_by_id):
    """The effective recommended set of a station under commercial_only (spec §4.2, K-NC DR106), from its index
    entry (the sets in file order): the release's recommended set when its licence allows commercial use;
    otherwise the first set in file order of the same typed quantity, qc_status ok, with a commercial licence;
    then the same with flagged; otherwise None. A set with no quantity never matches."""
    rid = e.get("recommended_set_id")
    sets = e.get("sets") or ()
    rec = next((cs for cs in sets if rid is not None and cs["set_id"] == rid), None)
    if rec is None:
        return None
    if lic_by_id[rec["licence_id"]].commercial_use is True:
        return rid
    q = _typed(E.Quantity, rec.get("quantity"))
    if q is None:
        return None
    for status in ("ok", "flagged"):
        for cs in sets:
            if (cs.get("qc_status") == status and _typed(E.Quantity, cs.get("quantity")) == q
                    and lic_by_id[cs["licence_id"]].commercial_use is True):
                return cs["set_id"]
    return None


def _effective_ids(entries, lic_by_id):
    return {e["station_id"]: _effective_id(e, lic_by_id) for e in entries if e.get("status") == "active"}


def haversine(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R_KM * math.asin(min(1.0, math.sqrt(a)))


# --------------------------------------------------------------------------- index entries

_SET_KEYS = ("set_id", "source", "source_type", "quantity", "qc_status", "convention_id", "licence_id")
_ENTRY_STR = ("name", "name_folded", "country", "type", "kind", "reference_station_id", "offsets_licence_id",
              "recommended_set_id")


def _s(d, k):
    v = d.get(k)
    return v if isinstance(v, str) else None


def _n(d, k):
    v = d.get(k)
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _status(d):
    """A line's status: a line with no status (or null) is an active station, as in the stream index (CR2 DR28). A
    status that is there but not a string is invalid_release (schema type string, CR2 DR43)."""
    s = d.get("status")
    if s is None:
        return "active"
    if not isinstance(s, str):
        raise InvalidReleaseError(f"station {d.get('station_id')!r}: status is not a string: {s!r}")
    return s


def _entry(d, offset=None, length=None):
    """The stream index entry of one line (spec §6.2): every key, for active stations and tombstones.
    `kind` is the station's own kind here; _resolve_kinds finishes it."""
    if not isinstance(d.get("station_id"), str):
        raise InvalidReleaseError(f"station_id is not a string: {d.get('station_id')!r}")
    if _status(d) == "active":
        for k, bound in (("lat", 90), ("lon", 180)):
            v = d.get(k)
            if not _is_finite(v) or abs(v) > bound:
                raise InvalidReleaseError(f"station {d['station_id']}: {k} is not a number in range: {v!r}")
    off = d.get("subordinate_offsets")
    _check_historical_offsets(off, f"station {d['station_id']}: subordinate_offsets")
    off = off if isinstance(off, dict) else {}
    rec_id = _s(d, "recommended_set_id")
    sets, kind = [], None
    aliases = d.get("aliases") or {}
    if not isinstance(aliases, dict) or not all(
            isinstance(v, str) or (isinstance(v, list) and all(isinstance(x, str) for x in v)) for v in aliases.values()):
        raise InvalidReleaseError(f"station {d.get('station_id')!r}: aliases must map a system to a string id or "
                                  f"a list of string ids")
    for cs in d.get("constant_sets") or ():
        if _status(d) == "active" and not isinstance(cs.get("set_id"), str):
            raise InvalidReleaseError(f"station {d.get('station_id')!r}: a constant set has no set_id")
        sets.append({**{k: _s(cs, k) for k in _SET_KEYS},
                     "constituents": [c.get("name") for c in cs.get("constituents") or () if isinstance(c.get("name"), str)],
                     "fallback": cs.get("fallback"),
                     "current_bins": [integral(b.get("bin")) for b in cs.get("current_bins") or ()]})
        if rec_id is not None and cs.get("set_id") == rec_id:
            kind = {"water_level": "tide", "current": "current"}.get(cs.get("quantity"), "other")
    name = _s(d, "name")
    return {
        "offset": offset, "length": length, "station_id": d["station_id"], "status": _status(d),
        "name": name, "name_folded": fold(name) if name is not None else None,
        "country": _s(d, "country"), "type": _s(d, "type"), "lat": _n(d, "lat"), "lon": _n(d, "lon"), "kind": kind,
        "aliases": {k: ([v] if isinstance(v, str) else list(v)) for k, v in aliases.items()},
        "reference_station_id": _s(off, "reference_station_id"), "offsets_licence_id": _s(off, "licence_id"),
        "subordinate_offsets": d.get("subordinate_offsets"),
        "recommended_set_id": rec_id, "sets": sets,
        "current_offsets": [{"bin": integral(co.get("bin")), "reference_bin": integral(co.get("reference_bin")),
                             "reference_station_id": _s(co, "reference_station_id"), "licence_id": _s(co, "licence_id")}
                            for co in d.get("current_offsets") or ()],
    }


def integral(v):
    """v as an int when it is a JSON integer or a number with an integral value (12.0), else None (CR2 DR10)."""
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return v
    if isinstance(v, float) and math.isfinite(v) and v.is_integer():
        return int(v)
    return None


_INDEX_PRIVATE_SET_KEYS = ("source_record_id", "source_version", "datum")
_INDEX_CURRENT_ADJUSTMENTS = ("time_adj_max_flood_min", "time_adj_max_ebb_min",
                              "time_adj_slack_before_flood_min", "time_adj_slack_before_ebb_min",
                              "flood_amp_ratio", "ebb_amp_ratio")


def _index_presence(entries):
    """The admitted document's extension profile, independent of its informational writer label."""
    if any(not isinstance(e, dict) or not isinstance(e.get("sets"), list) for e in entries):
        return None
    sets = [cs for e in entries for cs in e["sets"]]
    if any(not isinstance(cs, dict) for cs in sets):
        return None
    private = {tuple(k in cs for k in _INDEX_PRIVATE_SET_KEYS) for cs in sets}
    if private not in (set(), {(False, False, False)}, {(True, True, True)}):
        return None
    bins_base = not any("current_bins" in cs for cs in sets)
    if not bins_base and any("current_bins" not in cs for cs in sets):
        return None
    own_base = not any("subordinate_offsets" in e for e in entries)
    fallback_base = not any("fallback" in cs for cs in sets)
    current_base = not any("current_offsets" in e for e in entries)
    profiles = set()
    for e in entries:
        if "current_offsets" in e and not isinstance(e["current_offsets"], list):
            return None
        for row in e.get("current_offsets", ()):
            if not isinstance(row, dict):
                return None
            count = sum(k in row for k in _INDEX_CURRENT_ADJUSTMENTS)
            if count not in (0, len(_INDEX_CURRENT_ADJUSTMENTS)):
                return None
            profiles.add(count)
    if len(profiles) > 1:
        return None
    return MappingProxyType({"own_base": own_base, "fallback_base": fallback_base, "bins_base": bins_base,
                             "all_base": own_base and fallback_base and bins_base and current_base,
                             "private": bool(sets) and next(iter(private)) == (True, True, True),
                             "full_current": len(_INDEX_CURRENT_ADJUSTMENTS) in profiles})


def _line_view(e, presence=None, raw=None):
    """The represented fields that the actual row must give, using the admitted presence profile."""
    if presence is not None:
        profile, entry_keys, set_keys = presence
        values = []
        for i, cs in enumerate(e.get("sets") or ()):
            original = (raw.get("constant_sets") or ())[i] if raw is not None else cs
            extra = []
            if "fallback" in set_keys[i] or not profile["fallback_base"]:
                extra.append(freeze(original.get("fallback")))
            if "current_bins" in set_keys[i]:
                extra.append(tuple(cs.get("current_bins") or ()))
            if profile["private"]:
                extra.extend(freeze(original.get(k)) for k in _INDEX_PRIVATE_SET_KEYS)
            values.append(tuple(cs.get(k) for k in _SET_KEYS) + (tuple(cs.get("constituents") or ()), *extra))
        own = () if profile["own_base"] and "subordinate_offsets" not in entry_keys else (
            freeze(raw.get("subordinate_offsets") if raw is not None else e.get("subordinate_offsets")),)
        current = ()
        if "current_offsets" in entry_keys or not profile["all_base"]:
            rows = raw.get("current_offsets") or () if raw is not None else e.get("current_offsets") or ()
            fields = ("bin", "reference_bin", "reference_station_id", "licence_id")
            if profile["full_current"]:
                fields += _INDEX_CURRENT_ADJUSTMENTS
            current = (tuple(tuple(freeze(row.get(k)) for k in fields) for row in rows),)
        return (tuple(freeze(e.get(k)) for k in ("name", "name_folded", "country", "type", "lat", "lon", "kind", "aliases")),
                e.get("station_id"), e.get("status"), e.get("recommended_set_id"),
                e.get("reference_station_id"), e.get("offsets_licence_id"), values, own, current)
    return (tuple(freeze(e.get(k)) for k in ("name", "name_folded", "country", "type", "lat", "lon", "kind", "aliases")),
            e.get("station_id"), e.get("status"), e.get("recommended_set_id"), e.get("reference_station_id"),
            e.get("offsets_licence_id"),
            [tuple(cs.get(k) for k in _SET_KEYS) + (tuple(cs.get("constituents") or ()), freeze(cs.get("fallback")),
                                                       tuple(cs.get("current_bins") or ())) for cs in e.get("sets") or ()],
            freeze(e.get("current_offsets")), freeze(e.get("subordinate_offsets")))


def _usable_index(idx, name, sha256, size, conv, lic):
    """The entries of a fresh index-v1.json, or None when it is stale or cannot be used (spec §6.2). An integer
    key may be written as a number with an integral value (CR2 DR10)."""
    def is_int(v):
        return integral(v) is not None

    def is_num(v):
        return v is None or (isinstance(v, (int, float)) and not isinstance(v, bool))

    if not isinstance(idx, dict) or integral(idx.get("index_version")) != INDEX_VERSION \
            or ("discovery_index_version" in idx and integral(idx["discovery_index_version"]) != 1):
        return None
    if idx.get("jsonl") != name or name != f"OTC_{idx.get('datestamp')}.jsonl" or idx.get("jsonl_sha256") != sha256 \
            or not is_int(idx.get("jsonl_size")) or integral(idx["jsonl_size"]) != size or not isinstance(idx.get("stations"), list):
        return None
    profile = _index_presence(idx["stations"])
    if profile is None:
        return None
    out = []
    start = 0  # the least offset the next entry may have
    for e in idx["stations"]:
        if not isinstance(e, dict) or not is_int(e.get("offset")) or not is_int(e.get("length")) \
                or not isinstance(e.get("station_id"), str) or not isinstance(e.get("status"), str) \
                or not all(k in e and (e[k] is None or isinstance(e[k], str)) for k in _ENTRY_STR) \
                or not is_num(e.get("lat", 0)) or not is_num(e.get("lon", 0)) or "lat" not in e or "lon" not in e \
                or not isinstance(e.get("aliases"), dict) or not isinstance(e.get("sets"), list) \
                or ("current_offsets" in e and not isinstance(e["current_offsets"], list)):
            return None
        off = e.get('subordinate_offsets')
        if not (off is None or isinstance(off, dict)):
            return None
        try:
            _check_historical_offsets(off)
        except InvalidReleaseError:
            return None
        if "subordinate_offsets" in e and (e.get('reference_station_id') != (None if off is None else _s(off, 'reference_station_id'))
                or e.get('offsets_licence_id') != (None if off is None else _s(off, 'licence_id'))):
            return None
        if "subordinate_offsets" not in e and not profile["own_base"] \
                and (e["reference_station_id"] is not None or e["offsets_licence_id"] is not None):
            return None
        e = {**e, "offset": integral(e["offset"]), "length": integral(e["length"])}
        if not all(isinstance(v, list) and all(isinstance(x, str) for x in v) for v in e["aliases"].values()):
            return None
        # the bounds check (CR D4): a line inside the file, and after the line before it and its line end, so
        # that no two entries overlap (CR2 DR9)
        if e["length"] <= 0 or e["offset"] < start or e["offset"] + e["length"] > size:
            return None
        start = e["offset"] + e["length"] + 1
        if e["status"] == "active" and (not _is_finite(e["lat"]) or not _is_finite(e["lon"])
                                        or abs(e["lat"]) > 90 or abs(e["lon"]) > 180):
            return None
        for cs in e["sets"]:
            if not isinstance(cs, dict) or not all(k in cs and (cs[k] is None or isinstance(cs[k], str)) for k in _SET_KEYS) \
                    or not isinstance(cs.get("constituents"), list) or not all(isinstance(x, str) for x in cs["constituents"]) \
                    or ("fallback" in cs and not (cs["fallback"] is None or isinstance(cs["fallback"], dict))) \
                    or ("current_bins" in cs and (not isinstance(cs["current_bins"], list)
                        or not all((value := integral(n)) is not None and 1 <= value <= 2**53 - 1
                                   for n in cs["current_bins"]))):
                return None
            if profile["private"] or cs.get("fallback") is not None:
                try:
                    fields = {k: cs[k] for k in _INDEX_PRIVATE_SET_KEYS} if profile["private"] else {}
                    if "fallback" in cs:
                        fields["fallback"] = cs["fallback"]
                    check_station_types({"constant_sets": [fields]})
                except (InvalidReleaseError, TypeError, AttributeError):
                    return None
            if e["status"] == "active" and (cs["convention_id"] not in conv or cs["licence_id"] not in lic):
                return None  # a reference that does not resolve: rebuild, and the pass raises invalid_release
        for co in e.get("current_offsets", ()):
            if not isinstance(co, dict) or not all(k in co for k in ("bin", "reference_bin", "reference_station_id", "licence_id")) \
                    or not all(co[k] is None or integral(co[k]) is not None for k in ("bin", "reference_bin")) \
                    or not all(co[k] is None or isinstance(co[k], str) for k in ("reference_station_id", "licence_id")):
                return None
            if profile["full_current"] and not all(co[k] is None or _is_finite(co[k])
                                                   for k in _INDEX_CURRENT_ADJUSTMENTS):
                return None
        if e["status"] == "active":
            if e["offsets_licence_id"] is not None and e["offsets_licence_id"] not in lic:
                return None
            if e["recommended_set_id"] is not None and e["recommended_set_id"] not in {cs["set_id"] for cs in e["sets"]}:
                return None
        presence = (profile, frozenset(k for k in ("subordinate_offsets", "current_offsets") if k in e),
                    tuple(frozenset(k for k in ("fallback", "current_bins") if k in cs) for cs in e["sets"]))
        e["_index_presence"] = presence
        out.append(e)
    return out


def _check_ids(entries, conventions, licences):
    """Repeated ids and references that do not resolve are invalid_release (spec §6.1, CR D5), the same in eager
    and stream mode: a station_id across active stations and tombstones together, a (system, alias id) pair, a
    set_id, a convention_id, a licence_id; and a reference_station_id that names no active station."""
    def once(values, what):
        seen = set()
        for v in values:
            if v in seen:
                raise InvalidReleaseError(f"{what} {v!r} appears twice")
            seen.add(v)
    once((e["station_id"] for e in entries), "station_id")
    active = [e for e in entries if e.get("status") == "active"]
    once(((sys_, i) for e in active for sys_, ids in (e.get("aliases") or {}).items() for i in ids), "alias")
    once((cs.get("set_id") for e in active for cs in e.get("sets") or ()), "set_id")
    once((c.convention_id for c in conventions), "convention_id")
    once((x.licence_id for x in licences), "licence_id")
    ids = {e["station_id"] for e in active}
    for e in active:
        ref = e.get("reference_station_id")
        if ref is not None and ref not in ids:
            raise InvalidReleaseError(f"station {e['station_id']}: reference_station_id {ref!r} does not resolve")


def _resolve_kinds(entries):
    by_id = {e["station_id"]: e for e in entries if e.get("status") == "active"}
    own_kinds = {}
    for sid, e in by_id.items():
        rec = next((cs for cs in e["sets"] if e["recommended_set_id"] is not None
                    and cs["set_id"] == e["recommended_set_id"]), None)
        own_kinds[sid] = None if rec is None else {"water_level": "tide", "current": "current"}.get(rec["quantity"], "other")

    def kind(e, seen, links=0):
        if own_kinds[e["station_id"]] is not None:
            return own_kinds[e["station_id"]]
        if links < _MAX_LINKS and e.get("type") == "subordinate" and e.get("reference_station_id"):
            ref = by_id.get(e["reference_station_id"])
            if ref is not None and ref["station_id"] not in seen:
                return kind(ref, seen | {e["station_id"]}, links + 1)
        return None

    resolved = {sid: kind(e, frozenset()) for sid, e in by_id.items()}
    for sid, k in resolved.items():
        by_id[sid]["kind"] = k


# --------------------------------------------------------------------------- Release

def _validate_station_filters(country, type, kind, source, source_type, include_flagged, include_fallback):
    for name, v in (("country", country), ("type", type), ("kind", kind), ("source", source),
                    ("source_type", source_type)):
        _check_type(name, v, (str,))
    for name, value in (("include_flagged", include_flagged), ("include_fallback", include_fallback)):
        _check_type(name, value, (bool,), allow_none=False)


def _validate_search_arguments(name, limit, match):
    _check_type("name", name, (str,), allow_none=False)
    limit = _limit(limit)
    if match is not None and match != "exact":
        raise InvalidArgumentError(f"match must be 'exact', not {match!r}")
    q = fold(name)
    if not q:
        raise InvalidArgumentError("the query is empty")
    return q, limit


def _bind_release_fields_1(_receiver: "Release", *, historical_offsets_policy, astro_cache, meta, index_path):
    _receiver._historical_offsets_policy = historical_offsets_policy
    _receiver._astro_cache = astro_cache
    _receiver._meta = meta
    _receiver._index_path = index_path


def _bind_release_fields_2(_receiver: "Release", *, opened):
    _receiver._opened = opened


def _bind_release_fields_3(_receiver: "Release", *, release):
    _receiver._release = release


def _bind_release_fields_4(_receiver: "Release", *, files):
    _receiver._files = files


def _bind_release_fields_5(_receiver: "Release", *, conventions):
    _receiver._conventions = conventions


def _bind_release_fields_6(_receiver: "Release", *, licences):
    _receiver._licences = licences


def _bind_release_fields_7(_receiver: "Release", *, conv_by_id):
    _receiver._conv_by_id = conv_by_id


def _bind_release_fields_8(_receiver: "Release", *, lic_by_id):
    _receiver._lic_by_id = lic_by_id


def _bind_release_fields_9(_receiver: "Release", *, commercial_only, commercial_basis):
    _receiver._commercial_only = commercial_only
    _receiver._commercial_basis = commercial_basis


def _bind_release_fields_10(_receiver: "Release", *, effective):
    _receiver._effective = effective


def _bind_release_fields_11(_receiver: "Release", *, entries):
    _receiver._entries = entries


def _bind_release_fields_12(_receiver: "Release", *, by_id):
    _receiver._by_id = by_id


def _bind_release_fields_13(_receiver: "Release", *, tombs):
    _receiver._tombs = tombs


def _bind_release_fields_14(_receiver: "Release", *, alias, subs):
    _receiver._alias = alias
    _receiver._subs = subs


def _bind_release_fields_15(_receiver: "Release", *, mode):
    _receiver._mode = mode


def _bind_release_fields_16(_receiver: "Release", *, station_origin):
    _receiver._station_origin = station_origin


def _bind_release_fields_17(_receiver: "Release", *, stations):
    _receiver._stations = stations
    if stations is not None:
        for station in stations.values():
            object.__setattr__(station, "_origin", _receiver._station_origin)


def _bind_release_fields_18(_receiver: "Release", *, tomb_objs, fh):
    _receiver._tomb_objs = tomb_objs
    _receiver._fh = fh


def _bind_release_fields_19(_receiver: "Release", *, lock):
    _receiver._lock = lock


def _bind_release_fields_20(_receiver: "Release", *, lru):
    _receiver._lru = lru


def _bind_release_fields_21(_receiver: "Release", *, jsonl, constituent_names, stats, closed, zenodo_version_doi):
    _receiver._jsonl = jsonl
    _receiver._constituent_names = constituent_names
    _receiver._stats = stats
    _receiver._closed = closed
    _receiver._zenodo_version_doi = zenodo_version_doi


class Release:
    """One loaded OTC_{DATESTAMP} release. Immutable; every query method is here."""

    __slots__ = ("_meta", "_release", "_files", "_conventions", "_conv_by_id", "_licences", "_lic_by_id",
                 "_entries", "_by_id", "_tombs", "_alias", "_subs", "_stations", "_tomb_objs", "_mode", "_fh",
                 "_lock", "_lru", "_jsonl", "_constituent_names", "_stats", "_closed", "_zenodo_version_doi",
                 "_index_path", "_opened", "_commercial_only", "_commercial_basis", "_historical_offsets_policy", "_effective", "_astro_cache", "_station_origin", "__weakref__")

    def __init__(self, *, meta, entries, files, mode, stations=None, tombstones=None, jsonl=None, index_path=None,
                 commercial_only=False, commercial_basis="strict", historical_offsets_policy="fallback"):
        if not isinstance(historical_offsets_policy, str) or historical_offsets_policy not in ('fallback', 'exclude'):
            raise InvalidArgumentError('historical_offsets_policy must be fallback or exclude')
        _bind_release_fields_1(self, historical_offsets_policy=historical_offsets_policy, astro_cache={}, meta=meta, index_path=index_path)
        _bind_release_fields_2(self, opened=())
        rel = _validate_release_header(meta)
        _bind_release_fields_3(self, release=rel)
        _bind_release_fields_4(self, files=tuple(files))
        try:
            _bind_release_fields_5(self, conventions=tuple(Convention._parse(c) for c in meta.get("conventions") or ()))
            _bind_release_fields_6(self, licences=tuple(Licence._parse(x) for x in meta.get("licences") or ()))
        except (KeyError, TypeError, AttributeError) as e:
            raise InvalidReleaseError(f"conventions or licences: {e!r}") from e
        for x in self._licences:
            # the attribution text prints both (spec §4.6, CR2 DR2); a null provider is allowed (CR D2 b)
            if not isinstance(x.attribution, str) or not (x.provider is None or isinstance(x.provider, str)):
                raise InvalidReleaseError(f"licence {x.licence_id!r}: attribution must be a string and provider a "
                                          f"string or null")
        _bind_release_fields_7(self, conv_by_id={c.convention_id: c for c in self._conventions})
        _bind_release_fields_8(self, lic_by_id={x.licence_id: x for x in self._licences})
        parse_time(rel.get("created"), "release.created")
        _check_ids(entries, self._conventions, self._licences)
        if not all("_index_presence" in e for e in entries):
            _resolve_kinds(entries)
        # commercial_only (spec §4.2, K-NC DR106): station_id -> the effective recommended set_id (or None)
        _bind_release_fields_9(self, commercial_only=commercial_only, commercial_basis=commercial_basis)
        _bind_release_fields_10(self, effective=_effective_ids(entries, self._lic_by_id) if commercial_only else None)
        active = sorted((e for e in entries if e.get("status") == "active"), key=lambda e: e["station_id"])
        _bind_release_fields_11(self, entries=active)
        _bind_release_fields_12(self, by_id={e["station_id"]: e for e in active})
        _bind_release_fields_13(self, tombs={e["station_id"]: e for e in entries if e.get("status") == "removed"})
        for e in entries:
            if e.get("status") not in ("active", "removed"):
                # a status this SDK does not know (a newer minor's value): not a station, not a tombstone, in no
                # query and no count; said once, at load (CR2 DR8)
                _log.warning("station %s has the status %r, which this SDK does not know: it is left out of every "
                             "query", e["station_id"], e.get("status"))
        _bind_release_fields_14(self, alias={}, subs={})
        for e in active:
            for system, ids in (e.get("aliases") or {}).items():
                for i in ids:
                    self._alias.setdefault(system, {})[i] = e["station_id"]
            if e.get("type") == "subordinate" and e.get("reference_station_id"):
                self._subs.setdefault(e["reference_station_id"], []).append(e["station_id"])
        _bind_release_fields_15(self, mode=mode)
        _bind_release_fields_16(self, station_origin=object())
        _bind_release_fields_17(self, stations=stations)
        _bind_release_fields_18(self, tomb_objs=tombstones, fh=None)
        _bind_release_fields_19(self, lock=threading.Lock())
        _bind_release_fields_20(self, lru=OrderedDict())
        _bind_release_fields_21(self, jsonl=jsonl, constituent_names=None, stats=None, closed=False, zenodo_version_doi=None)
        if mode == "stream":
            try:
                self._fh = open(jsonl, "rb")
            except OSError as e:
                raise FileError(f"cannot open {jsonl}: {e}", path=str(jsonl), cause=e) from e

    # ---- metadata

    @property
    def datestamp(self) -> str:
        return self._release["datestamp"]

    @property
    def created(self):
        return parse_time(self._release.get("created"))

    @property
    def format_version(self) -> str:
        return self._meta.get("format_version")

    @property
    def concept_doi(self):
        """The concept DOI (all versions), from the release document."""
        return self._release.get("concept_doi")

    @property
    def zenodo_version_doi(self):
        """This release's own Zenodo version DOI, from the pointer or index entry the SDK read for it (spec
        §4.3); None when it has none or the SDK read no entry (always None for a file)."""
        return self._zenodo_version_doi

    @property
    def source_versions(self):
        return freeze(dict(self._release.get("source_versions") or {}))

    @property
    def build_commit(self):
        return self._release.get("build_commit")

    @property
    def changelog_url(self):
        return self._release.get("changelog_url")

    @property
    def files(self) -> Tuple[FileInfo, ...]:
        return self._files

    # After close the metadata above (datestamp, created, format_version, citation, files) stays readable; every query
    # below is io "the release is closed" (spec §4.2, CR D21, CR2 DR32).

    @property
    def conventions(self) -> Tuple[Convention, ...]:
        self._check_open()
        return self._conventions

    def convention(self, convention_id: str) -> Optional[Convention]:
        self._check_open()
        return self._conv_by_id.get(convention_id)

    @property
    def licences(self) -> Tuple[Licence, ...]:
        self._check_open()
        return self._licences

    def licence(self, licence_id: str) -> Optional[Licence]:
        self._check_open()
        return self._lic_by_id.get(licence_id)

    @property
    def station_count(self) -> int:
        self._check_open()
        return len(self._entries)

    @property
    def tombstone_count(self) -> int:
        self._check_open()
        return len(self._tombs)

    @property
    def constituent_names(self) -> Tuple[str, ...]:
        self._check_open()
        if self._constituent_names is None:
            names = {n for e in self._entries for s in e.get("sets") or () for n in s.get("constituents") or ()}
            self._constituent_names = tuple(sorted(names))
        return self._constituent_names

    @property
    def stats(self) -> Stats:
        self._check_open()
        if self._stats is None:
            def count(values):
                out = {}
                for v in values:
                    if v is not None:
                        out[v] = out.get(v, 0) + 1
                return MappingProxyType(dict(sorted(out.items())))
            sets = [s for e in self._entries for s in e.get("sets") or ()]
            qc = [E.enum_or_raw(E.QcStatus, s.get("qc_status")) for s in sets]
            self._stats = Stats(count(_typed(E.StationType, e.get("type")) for e in self._entries),
                                count(_typed(E.Kind, e.get("kind")) for e in self._entries),
                                count(e.get("country") for e in self._entries),
                                count(s.get("source") for s, q in zip(sets, qc) if q in _USABLE),
                                count(None if q is None else q.value for q in qc))
        return self._stats

    @property
    def citation(self) -> str:
        """The dataset citation (spec §4.6); the year is the first four digits of the datestamp."""
        cdoi, vdoi = self.concept_doi, self.zenodo_version_doi
        link = f"https://doi.org/{cdoi}" if cdoi else f"{DATA_URL}OTC_{self.datestamp}.json"
        version = f" (version DOI: https://doi.org/{vdoi})" if vdoi else ""
        return (f"OpenTideConstants contributors ({self.datestamp[:4]}). OpenTideConstants, release {self.datestamp} "
                f"[Data set]. {link}{version}")

    # ---- station access

    def _station_from_entry(self, e, read_line=None) -> Station:
        if self._stations is not None:
            return self._stations[e["station_id"]]
        sid = e["station_id"]
        with self._lock:
            st = self._lru.get(sid)
            if st is not None:
                self._lru.move_to_end(sid)
                return st
            d = self._read_line(e) if read_line is None else read_line(e)
        if self._effective is not None:
            st = build_station(d, self._conv_by_id, self._lic_by_id, e.get("kind"), self._effective[sid])
        else:
            st = build_station(d, self._conv_by_id, self._lic_by_id, e.get("kind"))
        object.__setattr__(st, "_origin", self._station_origin)
        with self._lock:
            self._lru[sid] = st
            if len(self._lru) > LRU_SIZE:
                self._lru.popitem(last=False)
        return st

    def _check_open(self) -> None:
        if self._closed:
            raise FileError("the release is closed", path=None if self._jsonl is None else str(self._jsonl))

    def _read_line(self, e, decode=None, compare=None):
        """Called with self._lock held, so close() cannot run in the middle of it."""
        if self._fh is None:
            raise FileError("the release is closed", path=str(self._jsonl))
        try:
            self._fh.seek(e["offset"])
            data = self._fh.read(e["length"])
        except ValueError as ex:  # the handle was closed under the reader
            raise FileError("the release is closed", path=str(self._jsonl), cause=ex) from ex
        except OSError as ex:
            raise FileError(f"cannot read {self._jsonl}: {ex}", path=str(self._jsonl), cause=ex) from ex
        comparing = False
        try:
            if len(data) != e["length"]:
                raise InvalidReleaseError(f"short read of {self._jsonl} at {e['offset']}")
            what = f"{self._jsonl} line of {e['station_id']}"
            d = _json(data, what) if decode is None else decode(data, what)
            if not isinstance(d, dict) or d.get("station_id") != e["station_id"]:
                raise InvalidReleaseError(f"the line at offset {e['offset']} of {self._jsonl} is not "
                                          f"{e['station_id']}")
            if compare is not None:
                comparing = True
                compare(d, e)
            elif self._index_path is not None:
                self._check_line(d, e)
        except InvalidReleaseError as ex:
            if comparing:
                raise
            self._reject_index_mismatch(ex)
        return d

    def _reject_index_mismatch(self, ex):
        # the index does not match the file (CR D4): name it and drop it, so the next open rebuilds it
        if self._index_path is not None:
            try:
                self._index_path.unlink()
            except FileNotFoundError:
                pass
            except OSError as ux:
                _log.warning("cannot delete %s: %s", self._index_path, ux)
            raise InvalidReleaseError(f"{self._index_path.name} does not match the release: {ex}") from ex
        raise ex

    def _check_line(self, d, e):
        """A line read through the stream index gets the checks of the full pass, and it must give its entry's
        represented source fields (spec §6.2, CR D4, PK-R2-07)."""
        try:
            _validate_refs(d, self._conv_by_id, self._lic_by_id)
            got = _entry(d, e["offset"], e["length"])
            if got["kind"] is None and got["type"] == "subordinate":
                current, seen = got, {got["station_id"]}
                for _ in range(_MAX_LINKS):
                    ref = self._by_id.get(current["reference_station_id"])
                    if ref is None or ref["station_id"] in seen:
                        break
                    seen.add(ref["station_id"])
                    rec = next((cs for cs in ref["sets"] if ref["recommended_set_id"] is not None
                                and cs["set_id"] == ref["recommended_set_id"]), None)
                    if rec is not None:
                        got["kind"] = {"water_level": "tide", "current": "current"}.get(rec["quantity"], "other")
                        break
                    if ref["type"] != "subordinate":
                        break
                    current = ref
        except (KeyError, TypeError, AttributeError) as ex:
            raise InvalidReleaseError(f"the line of {e['station_id']}: {ex!r}") from ex
        presence = e.get("_index_presence")
        if len(got.get("sets") or ()) != len(e.get("sets") or ()) \
                or _line_view(got, presence, d) != _line_view(e, presence):
            raise InvalidReleaseError(f"the line of {e['station_id']} does not give the represented fields of its entry")

    def _index_policy_entry(self, e):
        """Uncached policy fields come from the validated actual record, never absence defaults."""
        presence = e.get("_index_presence")
        if presence is None or e.get("_index_policy_hydrated"):
            return e
        _, entry_keys, set_keys = presence
        if len(entry_keys) == 2 and all(len(keys) == 2 for keys in set_keys):
            return e
        with self._lock:
            raw = self._read_line(e)
            actual = _entry(raw, e["offset"], e["length"])
            for key in ("subordinate_offsets", "current_offsets"):
                if key not in entry_keys:
                    e[key] = actual[key]
            for stored, got, keys in zip(e["sets"], actual["sets"], set_keys):
                for key in ("fallback", "current_bins"):
                    if key not in keys:
                        stored[key] = got[key]
            e["_index_policy_hydrated"] = True
        return e

    def station(self, station_id: str) -> Optional[Station]:
        self._check_open()
        _check_type("station_id", station_id, (str,), allow_none=False)
        e = self._by_id.get(station_id)
        return None if e is None else self._station_from_entry(e)

    def require_station(self, station_id: str) -> Station:
        st = self.station(station_id)
        if st is not None:
            return st
        t = self.tombstone(station_id)
        if t is not None:
            raise StationRemovedError(f"station {station_id} was removed in {t.removed_in}", tombstone=t)
        raise StationNotFoundError(f"no station {station_id}")

    def tombstone(self, station_id: str) -> Optional[Tombstone]:
        self._check_open()
        _check_type("station_id", station_id, (str,), allow_none=False)
        e = self._tombs.get(station_id)
        if e is None:
            return None
        if self._tomb_objs is not None:
            return self._tomb_objs[station_id]
        with self._lock:
            d = self._read_line(e)
        return Tombstone._parse(d)

    def station_by_alias(self, system: str, alias_id: str) -> Optional[Station]:
        self._check_open()
        _check_type("system", system, (str,), allow_none=False)
        _check_type("alias_id", alias_id, (str,), allow_none=False)
        sid = self._alias.get(str(system), {}).get(alias_id)
        return None if sid is None else self.station(sid)

    def _set_eligible(self, cs, include_flagged, include_fallback, offsets_licence=None):
        status = cs.get("qc_status")
        if status not in _USABLE:
            return False
        fallback = cs.get("fallback")
        if fallback is not None:
            if not include_fallback:
                return False
        elif status != "ok" and not include_flagged:
            return False
        if offsets_licence is not None and offsets_licence not in self._lic_by_id:
            return False
        if not self._commercial_only:
            return True
        if self._commercial_basis == "strict" and fallback is not None and fallback.get("reason") == "licence_reading":
            return False
        licences = [cs["licence_id"]] + ([offsets_licence] if offsets_licence is not None else [])
        return all(self._lic_by_id[lid].commercial_use is True for lid in licences)

    @property
    def historical_offsets_policy(self):
        self._check_open()
        return self._historical_offsets_policy

    def _better_historical_path(self, e):
        # An ordinary default remains authoritative even when a query excludes its QC/source.
        rid = self._effective.get(e['station_id']) if self._effective is not None else e.get('recommended_set_id')
        if any(cs.get('set_id') == rid and cs.get('qc_status') in _USABLE for cs in e.get('sets') or ()):
            return True
        return any(self._eligible_paths(e, False, False, historical=False))

    def _historical_discovery(self, e):
        from ._historical_offsets import historical_offset_eligibility
        from ._predict._engine import _reference, _context
        from . import _errors as X
        offsets = e['subordinate_offsets']
        if self._historical_offsets_policy == 'exclude' or self._better_historical_path(e):
            return False
        try:
            reference, constants = _reference(self, offsets, 'water_level')
            if not historical_offset_eligibility(offsets, policy=self._historical_offsets_policy,
                    licences=self._lic_by_id, selected_reference=constants, better_path=False,
                    commercial_only=self._commercial_only):
                return False
            # Validate the selected native model/MLLW without switching to another reference set.
            _context(self, reference, 'water_level', constants.set_id, 'chart')
        except (X.NoConstantsError, X.ReferenceUnavailableError, X.InvalidArgumentError, X.UnsupportedConventionError,
                X.NoAstroTableError, X.UnsupportedConstituentError, X.DatumUnavailableError):
            return False
        return True

    def _eligible_paths(self, e, include_flagged, include_fallback, *, historical=True):
        e = self._index_policy_entry(e)
        for cs in e.get("sets") or ():
            if self._set_eligible(cs, include_flagged, include_fallback):
                yield cs
        ref = self._by_id.get(e.get("reference_station_id"))
        if ref is not None:
            ref = self._index_policy_entry(ref)
        own = e.get('subordinate_offsets') or {}
        if own.get('offset_id') is not None:
            if historical and self._historical_discovery(e):
                yield dict(own, quantity='water_level')
        elif ref is not None:
            # Select first usable NOAA water-level set before applying query policy; do not evade its exclusion.
            cs = next((cs for cs in ref["sets"] if cs.get("source") == _OFFSETS_SOURCE
                       and cs.get("qc_status") in _USABLE and _typed(E.Quantity, cs.get("quantity")) == "water_level"), None)
            if cs is not None and self._set_eligible(cs, include_flagged, include_fallback, e.get("offsets_licence_id")):
                yield cs
        for co in e.get("current_offsets") or ():
            ref = self._by_id.get(co.get("reference_station_id"))
            if ref is not None:
                ref = self._index_policy_entry(ref)
            n = co.get("reference_bin")
            own_bin = co.get("bin")
            if ref is None or n is None or not 1 <= n <= 2**53 - 1 \
                    or own_bin is None or not 1 <= own_bin <= 2**53 - 1:
                continue
            cs = next((cs for cs in ref["sets"] if cs.get("qc_status") in _USABLE
                       and _typed(E.Quantity, cs.get("quantity")) == "current" and n in cs.get("current_bins", ())), None)
            if cs is not None and self._set_eligible(cs, include_flagged, include_fallback, co.get("licence_id")):
                yield cs

    def _filtered(self, country=None, type=None, kind=None, source=None, source_type=None,
                  include_flagged=False, include_fallback=False):  # noqa: A002
        self._check_open()
        _validate_station_filters(country, type, kind, source, source_type, include_flagged, include_fallback)
        out = []
        for e in self._entries:
            if country is not None and e.get("country") != country:
                continue
            if type is not None and _typed(E.StationType, e.get("type")) != str(type):
                continue
            if kind is not None and _typed(E.Kind, e.get("kind")) != str(kind):
                continue
            if any((source is None or cs.get("source") == source)
                   and (source_type is None or _typed(E.SourceType, cs.get("source_type")) == str(source_type))
                   for cs in self._eligible_paths(e, include_flagged, include_fallback)):
                out.append(e)
        return out

    def stations(self, *, country=None, type=None, kind=None, source=None,  # noqa: A002
                 source_type=None, include_flagged=False, include_fallback=False) -> Tuple[Station, ...]:
        """Active stations matching every filter, ordered by station_id."""
        return tuple(self._station_from_entry(e) for e in
                     self._filtered(country, type, kind, source, source_type, include_flagged, include_fallback))

    def iter_stations(self, *, country=None, type=None, kind=None, source=None,  # noqa: A002
                      source_type=None, include_flagged=False, include_fallback=False) -> Iterator[Station]:
        """The same stations as stations(), one at a time. The arguments are checked when it is called; each step
        checks that the release is not closed (CR2 DR32)."""
        entries = self._filtered(country, type, kind, source, source_type, include_flagged, include_fallback)

        def steps():
            for e in entries:
                self._check_open()
                yield self._station_from_entry(e)
            self._check_open()
        return steps()

    def search(self, *, name, limit=None, match=None, country=None, type=None, kind=None, source=None,  # noqa: A002
               source_type=None, include_flagged=False, include_fallback=False) -> Tuple[Station, ...]:
        q, limit = _validate_search_arguments(name, limit, match)
        ranked = []
        for e in self._filtered(country, type, kind, source, source_type, include_flagged, include_fallback):
            n = e["name_folded"] or ""
            if n == q:
                r = 0
            elif match is not None:
                continue
            elif n.startswith(q):
                r = 1
            elif (" " + q) in n:
                r = 2
            elif q in n:
                r = 3
            else:
                continue
            ranked.append((r, n, e["station_id"], e))
        ranked.sort(key=lambda x: x[:3])
        if limit is not None:
            ranked = ranked[:limit]
        return tuple(self._station_from_entry(x[3]) for x in ranked)

    def _distances(self, lat, lon, radius_km, filters):
        cands = self._filtered(**filters)
        hits = []
        band = None if radius_km is None else radius_km / EARTH_R_KM  # radians
        if band is not None and band < math.pi:
            maxabs = min(90.0, abs(lat) + math.degrees(band))
            c = math.cos(math.radians(maxabs))
            s_lim = math.sin(band / 2) / c if c > 1e-9 else None
        for e in cands:
            elat, elon = e["lat"], e["lon"]
            if band is not None and band < math.pi:
                if abs(math.radians(elat - lat)) > band + 1e-12:
                    continue
                if s_lim is not None and s_lim < 1:
                    dl = abs(elon - lon) % 360.0
                    dl = min(dl, 360.0 - dl)
                    if math.sin(math.radians(dl) / 2) > s_lim + 1e-12:
                        continue
            d = haversine(lat, lon, elat, elon)
            if radius_km is None or d <= radius_km:
                hits.append((d, e["station_id"], e))
        hits.sort(key=lambda h: (h[0], h[1]))
        return hits

    def near(self, *, lat, lon, radius_km, limit=None, country=None, type=None, kind=None, source=None,  # noqa: A002
             source_type=None, include_flagged=False, include_fallback=False) -> Tuple[Nearby, ...]:
        lat = _number("lat", lat, -90, 90)
        lon = _number("lon", lon, -180, 180)
        radius_km = _number("radius_km", radius_km, 0)
        limit = _limit(limit)
        hits = self._distances(lat, lon, radius_km, dict(country=country, type=type, kind=kind, source=source,
                                                         source_type=source_type, include_flagged=include_flagged, include_fallback=include_fallback))
        if limit is not None:
            hits = hits[:limit]
        return tuple(Nearby(self._station_from_entry(h[2]), h[0]) for h in hits)

    def nearest(self, *, lat, lon, max_km=None, country=None, type=None, kind=None, source=None,  # noqa: A002
                source_type=None, include_flagged=False, include_fallback=False) -> Optional[Nearby]:
        lat = _number("lat", lat, -90, 90)
        lon = _number("lon", lon, -180, 180)
        max_km = _number("max_km", max_km, 0, allow_none=True)
        hits = self._distances(lat, lon, max_km, dict(country=country, type=type, kind=kind, source=source,
                                                      source_type=source_type, include_flagged=include_flagged, include_fallback=include_fallback))
        return Nearby(self._station_from_entry(hits[0][2]), hits[0][0]) if hits else None

    def _own_station(self, station, what):
        """station, checked as attribution checks it (CR D2 a): a Station that is an active station of this
        release; None, an unknown station or another release's Station is invalid_argument (CR2 DR24)."""
        _validate_station_argument(station, what)
        own = self.station(station.station_id)
        if station._origin is not self._station_origin or own is None or (own is not station and own.raw != station.raw):
            raise InvalidArgumentError(f"{what}: station {station.station_id} is not an active station of release "
                                       f"{self.datestamp}")

    def heights(self, station, *, start, stop, step_s=600, datum=None, set_id=None, offset_id=None, units='meters'):
        """Heights using otc-predict-1 (prediction spec section 5.2)."""
        self._check_open()
        if units not in ('meters', 'feet'):
            raise InvalidArgumentError("unsupported prediction units")
        from ._predict._results import _with_units
        from ._predict._engine import heights
        return _with_units(heights(self, station, start=start, stop=stop, step_s=step_s, datum=datum, set_id=set_id, offset_id=offset_id), units)

    def heights_at(self, station, times, *, datum=None, set_id=None, offset_id=None, units='meters'):
        """Heights at using otc-predict-1 (prediction spec section 5.2)."""
        self._check_open()
        if units not in ('meters', 'feet'):
            raise InvalidArgumentError("unsupported prediction units")
        from ._predict._results import _with_units
        from ._predict._engine import heights_at
        return _with_units(heights_at(self, station, times, datum=datum, set_id=set_id, offset_id=offset_id), units)

    def extremes(self, station, *, start, stop, datum=None, set_id=None, offset_id=None, units='meters'):
        """Extremes using otc-predict-1 (prediction spec section 5.2)."""
        self._check_open()
        if units not in ('meters', 'feet'):
            raise InvalidArgumentError("unsupported prediction units")
        from ._predict._results import _with_units
        from ._predict._engine import extremes
        return _with_units(extremes(self, station, start=start, stop=stop, datum=datum, set_id=set_id, offset_id=offset_id), units)

    def currents(self, station, *, start, stop, step_s=600, bin_number=None, set_id=None, units='m/s'):
        """Currents using otc-predict-1 (prediction spec section 5.2)."""
        self._check_open()
        if units not in ('m/s', 'knots'):
            raise InvalidArgumentError("unsupported prediction units")
        from ._predict._results import _with_units
        from ._predict._engine import currents
        return _with_units(currents(self, station, start=start, stop=stop, step_s=step_s, bin_number=bin_number, set_id=set_id), units)

    def current_events(self, station, *, start, stop, bin_number=None, set_id=None, units='m/s'):
        """Current events using otc-predict-1 (prediction spec section 5.2)."""
        self._check_open()
        if units not in ('m/s', 'knots'):
            raise InvalidArgumentError("unsupported prediction units")
        from ._predict._results import _with_units
        from ._predict._engine import current_events
        return _with_units(current_events(self, station, start=start, stop=stop, bin_number=bin_number, set_id=set_id), units)

    def datums(self, station, *, set_id=None, all_sets=False):
        """Datums using otc-predict-1 (prediction spec section 5.2)."""
        self._check_open()
        from ._predict._engine import datums
        return datums(self, station, set_id=set_id, all_sets=all_sets)

    def ranges(self, station, *, set_id=None):
        """Ranges using otc-predict-1 (prediction spec section 5.2)."""
        self._check_open()
        from ._predict._engine import ranges
        return ranges(self, station, set_id=set_id)

    def astro_table(self, id=None):
        self._check_open()
        from ._predict._engine import astro_table
        return astro_table(self, id)

    def reference_station(self, station: Station) -> Optional[Station]:
        self._check_open()
        self._own_station(station, "reference_station")
        off = station.subordinate_offsets
        if not station.is_subordinate or off is None or off.reference_station_id is None:
            return None
        return self.station(off.reference_station_id)

    def subordinates_of(self, station: Station) -> Tuple[Station, ...]:
        self._check_open()
        self._own_station(station, "subordinates_of")
        return tuple(self.station(s) for s in sorted(self._subs.get(station.station_id, ())))

    def attribution(self, stations: Optional[Sequence[Station]] = None) -> str:
        """The CC BY 4.0 attribution text for what an app shows (spec §4.6)."""
        self._check_open()
        _validate_attribution_container(stations)
        stations = None if stations is None else list(stations)
        co = self._commercial_only
        if not stations:  # None or an empty list: every licence in the release (CR D2 c); with commercial_only
            # only the commercial ones (K-NC DR106)
            lic_ids = {x.licence_id for x in self._licences if not co or x.commercial_use is True}
        else:
            lic_ids = set()
            for st in stations:
                _validate_attribution_item(st)
                own = self.station(st.station_id)
                if st._origin is not self._station_origin or own is None or (own is not st and own.raw != st.raw):
                    # unknown, removed or from another release: never skipped silently (CR D2 a)
                    raise InvalidArgumentError(f"station {st.station_id} is not an active station of release "
                                               f"{self.datestamp}")
                if co:  # the licences of the station's tide source (spec §4.2, §4.6, K-NC DR106)
                    lic_ids.update(self._tide_source_licences(self._by_id[st.station_id]))
                    continue
                if st.recommended_set is not None:
                    lic_ids.add(st.recommended_set.licence.licence_id)
                lic_ids.update(self._chain_licences(self._by_id[st.station_id]))
        parts, seen = [], set()
        for lid in sorted(lic_ids):
            lic = self._lic_by_id[lid]  # every licence reference resolves at load
            if lic.provider is None:
                parts.append(f"{lic.attribution}")  # no prefix, never merged (CR D2 b)
                continue
            if lic.provider in seen:
                continue
            seen.add(lic.provider)
            parts.append(f"{lic.provider}: {lic.attribution}")
        ident = f"doi:{self.concept_doi}" if self.concept_doi else f"{DATA_URL}OTC_{self.datestamp}.json"
        head = f"Tidal constants: OpenTideConstants {self.datestamp}, {ident}, CC BY 4.0."
        if not lic_ids:  # an empty scope: the dataset header alone (spec §4.6, K-NC DR106)
            return head
        text = head + " Sources: " + "; ".join(parts)
        # the non-commercial notice (spec §4.6, K-NC DR105): once, then one entry per non-commercial licence in
        # scope, by licence_id; a null provider gives the licence_id
        nc = [self._lic_by_id[lid] for lid in sorted(lic_ids) if self._lic_by_id[lid].commercial_use is not True]
        if nc:
            text += ". Non-commercial use only: " + "; ".join(
                f"{x.licence_id if x.provider is None else x.provider} ({x.spdx}, {x.terms_url})" for x in nc)
        return text

    def _tide_source_licences(self, e) -> List[str]:
        """The licences of a station's tide source under commercial_only (spec §4.2, K-NC DR106): its effective
        recommended set; else the one-link offsets path (the reference station's first set in file order from the
        offsets' source, water_level, ok or flagged), usable only when the offsets' licence and that set's
        licence allow commercial use; else none (no usable tides)."""
        eff = self._effective[e["station_id"]]
        if eff is not None:
            return [next(cs["licence_id"] for cs in e["sets"] if cs["set_id"] == eff)]
        if e["reference_station_id"] is None and e["offsets_licence_id"] is None:
            return []
        ref = self._by_id.get(e["reference_station_id"])
        if ref is None:
            return []
        refset = next((cs for cs in ref["sets"] if cs.get("source") == _OFFSETS_SOURCE and cs.get("qc_status") in _USABLE
                       and _typed(E.Quantity, cs.get("quantity")) == "water_level"), None)
        if refset is None:
            return []
        out = [refset["licence_id"]] + ([e["offsets_licence_id"]] if e["offsets_licence_id"] else [])
        return out if all(self._lic_by_id[x].commercial_use is True for x in out) else []

    def _chain_licences(self, e) -> List[str]:
        """The licences of a station's reference chain (spec §4.6, CR2 DR1): the walk follows reference_station_id
        through at most 16 links (the kind rule of §6.2). It takes the offsets licence of each station on the path,
        and the licence of the first recommended set it reaches, where it stops. A loop or a missing station ends
        the walk: the load has checked the links."""
        out, seen, links = [], {e["station_id"]}, 0
        while e.get("type") == "subordinate" and (e["reference_station_id"] or e["offsets_licence_id"]):
            if e["offsets_licence_id"]:
                out.append(e["offsets_licence_id"])
            if links == _MAX_LINKS:
                break
            ref = self._by_id.get(e["reference_station_id"])
            if ref is None or ref["station_id"] in seen:
                break
            links += 1
            seen.add(ref["station_id"])
            rec = next((cs for cs in ref["sets"] if ref["recommended_set_id"] is not None
                        and cs["set_id"] == ref["recommended_set_id"]), None)
            if rec is not None:
                out.append(rec["licence_id"])
                break
            e = ref
        return out

    def _close(self) -> None:
        with self._lock:
            self._closed = True
            fh, self._fh = self._fh, None
        if fh is not None:
            fh.close()

    def __del__(self):
        # a Release nobody holds any more (for example one an update swapped out) gives its file handle back
        try:
            fh = self._fh
            self._fh = None
            if fh is not None:
                fh.close()
        except Exception:  # noqa: BLE001 - never raise from a finaliser
            pass

    def __repr__(self) -> str:
        return f"<Release {self.datestamp} format {self.format_version} {self._mode}>"


# --------------------------------------------------------------------------- loading

def _check_meta(meta, what):
    if not isinstance(meta, dict):
        raise InvalidReleaseError(f"{what}: not a JSON object")
    rel = meta.get("release")
    if not isinstance(rel, dict):
        rel = {}
    check_format(meta.get("format_version"), rel.get("min_reader_version"), rel.get("datestamp"))
    if not isinstance(rel.get("min_reader_version"), str):
        raise InvalidReleaseError(f"{what}: release.min_reader_version is required")


def _validate_release_header(meta):
    rel = meta.get("release")
    if not isinstance(rel, dict) or not isinstance(rel.get("datestamp"), str):
        raise InvalidReleaseError("release.datestamp is missing")
    sv = rel.get("source_versions")
    if sv is not None and (not isinstance(sv, dict) or not all(isinstance(v, str) for v in sv.values())):
        raise InvalidReleaseError("release.source_versions is not an object of strings")
    return rel


def _refs(meta, what):
    """convention_id -> Convention and licence_id -> Licence; a malformed entry is invalid_release."""
    try:
        convs = [Convention._parse(c) for c in meta.get("conventions") or ()]
        lics = [Licence._parse(x) for x in meta.get("licences") or ()]
    except (KeyError, TypeError, AttributeError) as e:
        raise InvalidReleaseError(f"{what}: a convention or licence is malformed: {e!r}") from e
    if not all(isinstance(c.convention_id, str) for c in convs) or not all(isinstance(x.licence_id, str) for x in lics):
        raise InvalidReleaseError(f"{what}: a convention_id or licence_id is not a string")
    return {c.convention_id: c for c in convs}, {x.licence_id: x for x in lics}


def _validate_refs(d, conventions, licences):
    if _status(d) == "active":
        build_station(d, conventions, licences, None)


def load_document(path: Path, mode: str, files, index_path: Optional[Path] = None,
                  index_sha256: Optional[str] = None, commercial_only: bool = False,
                  json_sha256: Optional[str] = None, commercial_basis: str = "strict",
                  historical_offsets_policy: str = "fallback") -> Release:
    """Load a release from a data file (.json, .json.gz or .jsonl with its .meta.json). commercial_only: the
    open option of spec §4.2 (K-NC DR106). json_sha256: for a .json.gz, the OTC_{D}.json row that the decompressed
    bytes must match (spec §5.3, CR3 DR77)."""
    name = path.name
    if name.endswith(".jsonl"):
        meta = _json(_read_bytes(meta_path_for(path)), str(meta_path_for(path)))
        _check_meta(meta, str(meta_path_for(path)))
        conv, lic = _refs(meta, str(meta_path_for(path)))
        if mode == "stream":
            return _stream_index_with_retry(
                path, conv, lic, index_path, index_sha256,
                lambda entries: Release(meta=meta, entries=entries, files=files, mode="stream", jsonl=path,
                                        index_path=index_path, commercial_only=commercial_only,
                                        commercial_basis=commercial_basis,
                                        historical_offsets_policy=historical_offsets_policy),
            )
        data = _read_bytes(path)
        docs = []
        for i, line in enumerate(data.split(b"\n")):
            if line.strip():
                docs.append(_json(line, f"{path} line {i + 1}"))
        return _eager(meta, docs, files, commercial_only, commercial_basis, historical_offsets_policy)
    data = _read_bytes(path)
    if name.endswith(".gz"):
        try:
            data = gzip.decompress(data)
        except (OSError, EOFError, zlib.error) as e:
            raise InvalidReleaseError(f"{path}: not gzip: {e}") from e
        if json_sha256 is not None:
            check_json_sha256(path, data, json_sha256)
    doc = _json(data, str(path))
    _check_meta(doc, str(path))
    stations = doc.get("stations")
    if not isinstance(stations, list):
        raise InvalidReleaseError(f"{path}: stations is missing")
    meta = {k: v for k, v in doc.items() if k != "stations"}
    if mode == "stream":
        # a .json file has no lines to seek to: keep the parsed stations, as in eager mode
        mode = "eager"
    return _eager(meta, stations, files, commercial_only, commercial_basis, historical_offsets_policy)


def _eager(meta, docs, files, commercial_only=False, commercial_basis="strict", historical_offsets_policy="fallback") -> Release:
    conv, lic = _refs(meta, "the release")
    try:
        entries = [_entry(d) for d in docs]
    except (KeyError, TypeError, AttributeError) as e:
        raise InvalidReleaseError(f"bad station or reference data: {e!r}") from e
    _resolve_kinds(entries)
    kinds = {e["station_id"]: e.get("kind") for e in entries}
    stations, tombs = {}, {}
    for d in docs:
        if _status(d) == "active":
            stations[d["station_id"]] = build_station(d, conv, lic, kinds.get(d["station_id"]))
        elif _status(d) == "removed":
            tombs[d["station_id"]] = Tombstone._parse(d)
    if commercial_only:   # the Stations give the effective recommended set (spec §4.2, K-NC DR106); every
        # licence reference resolved in the pass above
        eff = _effective_ids(entries, lic)
        for d in docs:
            sid = d["station_id"]
            if _status(d) == "active" and eff[sid] != d.get("recommended_set_id"):
                stations[sid] = build_station(d, conv, lic, kinds.get(sid), eff[sid])
    return Release(meta=meta, entries=entries, files=files, mode="eager", stations=stations, tombstones=tombs,
                   commercial_only=commercial_only, commercial_basis=commercial_basis,
                   historical_offsets_policy=historical_offsets_policy)


def check_json_sha256(gz_path: Path, data: bytes, expected: str) -> None:
    """The decompressed bytes of an OTC_{D}.json.gz against the OTC_{D}.json row (spec §5.3, CR3 DR77)."""
    actual = hashlib.sha256(data).hexdigest()
    if actual != expected:
        name = gz_path.name[:-len(".gz")]
        raise ChecksumError(f"{name} (decompressed from {gz_path.name}): SHA-256 {actual} does not match {expected}",
                            file=str(gz_path.with_name(name)), expected=expected, actual=actual)


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    except OSError as e:
        raise FileError(f"cannot read {path}: {e}", path=str(path), cause=e) from e
    return h.hexdigest()


def _stream_index_with_retry(path, conv, lic, index_path, index_sha256, load, **phases):
    for attempt in range(2):
        had_index = index_path is not None and index_path.exists()
        entries = _stream_index(path, conv, lic, index_path, index_sha256, **phases)
        try:
            return load(entries)
        except InvalidReleaseError:
            if attempt or not had_index or index_path is None:
                raise
            try:
                index_path.unlink()
            except FileNotFoundError:
                pass
            phases.pop("supplied", None)


def _stream_index(path: Path, conv, lic, index_path: Optional[Path], index_sha256: Optional[str] = None,
                  project=None, encode=None, supplied=None, index_document=None):
    """Use index-v1.json when it is fresh, else make one pass over the .jsonl and write it (spec §6.2).
    index_sha256: the .jsonl digest from .verified (computed when not given)."""
    size = path.stat().st_size if path.exists() else None
    if size is None:
        raise FileError(f"cannot open {path}", path=str(path))
    if index_path is not None and index_path.exists():
        try:
            idx = json.loads(index_path.read_text(encoding="utf-8")) if supplied is None else supplied
            entries = _usable_index(idx, path.name, index_sha256 or file_sha256(path), size, conv, lic)
            if entries is not None:
                with path.open('rb') as handle:
                    end = 0
                    for entry in entries:
                        handle.seek(end)
                        remaining = entry['offset'] - end
                        while remaining:
                            gap = handle.read(min(remaining, 1 << 16))
                            if not gap or gap.strip(b" \t\r\n\f\v"):
                                break
                            remaining -= len(gap)
                        if remaining:
                            break
                        end = entry['offset'] + entry['length']
                        if entry['status'] != 'active':
                            handle.seek(entry['offset'])
                            raw = _json(handle.read(entry['length']), f"{path}: cached nonactive line")
                            if not isinstance(raw, dict) or raw.get('station_id') != entry['station_id'] \
                                    or _status(raw) != entry['status']:
                                break
                    else:
                        handle.seek(end)
                        if all(not chunk.strip(b" \t\r\n\f\v")
                               for chunk in iter(lambda: handle.read(1 << 16), b"")):
                            if index_document is not None:
                                index_document(idx)
                            return entries
        except (OSError, ValueError, RecursionError):
            pass  # a stale or broken index is rebuilt
        try:
            index_path.unlink()
        except FileNotFoundError:
            pass
    entries = []
    h = hashlib.sha256()
    offset = 0
    try:
        with open(path, "rb") as f:
            for i, line in enumerate(f):
                h.update(line)
                body = line[:-1] if line.endswith(b"\n") else line
                if line.endswith(b"\r\n"):
                    body = body[:-1]
                if body.strip(b" \t\r\n\f\v"):
                    d = _json(body, f"{path} line {i + 1}")
                    if not isinstance(d, dict) or "station_id" not in d:
                        raise InvalidReleaseError(f"{path} line {i + 1}: not a station")
                    _validate_refs(d, conv, lic)
                    try:
                        entries.append(_entry(d, offset, len(body)) if project is None else project(d, offset, len(body)))
                    except (KeyError, TypeError, AttributeError) as e:
                        raise InvalidReleaseError(f"{path} line {i + 1}: {e!r}") from e
                offset += len(line)
    except OSError as e:
        raise FileError(f"cannot read {path}: {e}", path=str(path), cause=e) from e
    _resolve_kinds(entries)
    if index_path is not None or index_document is not None:
        from ._cache import atomic_write
        from ._client import SDK
        doc = {"index_version": INDEX_VERSION, "discovery_index_version": 1, "datestamp": path.name[len("OTC_"):-len(".jsonl")], "jsonl": path.name,
               "jsonl_sha256": h.hexdigest(), "jsonl_size": size, "by": SDK, "stations": entries}
        if index_document is not None:
            index_document(doc)
    if index_path is not None:
        try:
            atomic_write(index_path, encode_cache_json(doc) if encode is None else encode(doc))
        except OSError as e:  # the index only saves work: the release loads without it (spec §6.2)
            _log.warning("cannot write %s: %s", index_path, e)
    return entries


