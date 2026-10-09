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
from typing import Iterator, Optional, Sequence, Tuple

from . import _enums as E
from ._errors import (FileError, InvalidArgumentError, InvalidReleaseError, ReaderTooOldError, StationNotFoundError,
                      StationRemovedError, UnsupportedFormatError)
from ._fold import fold
from ._models import (Convention, FileInfo, Licence, Nearby, Station, Stats, Tombstone, build_station, freeze,
                      parse_time)

SUPPORTED_FORMAT_MAJORS = (1,)
SUPPORTED_FORMAT_VERSION = "1.0"
EARTH_R_KM = 6371.0088
INDEX_VERSION = 1
LRU_SIZE = 256
_USABLE = ("ok", "flagged")  # qc_status of a set with constants (spec §4.3); QcStatus members compare equal
DATA_URL = "https://data.opentideconstants.org/"
_log = logging.getLogger("opentideconstants")


# --------------------------------------------------------------------------- reading files

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


def _entry(d, offset=None, length=None):
    """The stream index entry of one line (spec §6.2): every key, for active stations and tombstones.
    `kind` is the station's own kind here; _resolve_kinds finishes it."""
    if not isinstance(d.get("station_id"), str):
        raise InvalidReleaseError(f"station_id is not a string: {d.get('station_id')!r}")
    if d.get("status") == "active":
        for k, bound in (("lat", 90), ("lon", 180)):
            v = d.get(k)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or abs(v) > bound:
                raise InvalidReleaseError(f"station {d['station_id']}: {k} is not a number in range: {v!r}")
    off = d.get("subordinate_offsets")
    off = off if isinstance(off, dict) else {}
    rec_id = _s(d, "recommended_set_id")
    sets, kind = [], None
    aliases = d.get("aliases") or {}
    if not isinstance(aliases, dict) or not all(
            isinstance(v, str) or (isinstance(v, list) and all(isinstance(x, str) for x in v)) for v in aliases.values()):
        raise InvalidReleaseError(f"station {d.get('station_id')!r}: aliases must map a system to a string id or "
                                  f"a list of string ids")
    for cs in d.get("constant_sets") or ():
        if d.get("status") == "active" and not isinstance(cs.get("set_id"), str):
            raise InvalidReleaseError(f"station {d.get('station_id')!r}: a constant set has no set_id")
        sets.append({**{k: _s(cs, k) for k in _SET_KEYS},
                     "constituents": [c.get("name") for c in cs.get("constituents") or () if isinstance(c.get("name"), str)]})
        if rec_id is not None and cs.get("set_id") == rec_id:
            kind = {"water_level": "tide", "current": "current"}.get(cs.get("quantity"), "other")
    name = _s(d, "name")
    return {
        "offset": offset, "length": length, "station_id": d["station_id"], "status": d.get("status"),
        "name": name, "name_folded": fold(name) if name is not None else None,
        "country": _s(d, "country"), "type": _s(d, "type"), "lat": _n(d, "lat"), "lon": _n(d, "lon"), "kind": kind,
        "aliases": {k: ([v] if isinstance(v, str) else list(v)) for k, v in aliases.items()},
        "reference_station_id": _s(off, "reference_station_id"), "offsets_licence_id": _s(off, "licence_id"),
        "recommended_set_id": rec_id, "sets": sets,
    }


def _usable_index(idx, name, sha256, size, conv, lic):
    """The entries of a fresh index-v1.json, or None when it is stale or cannot be used (spec §6.2)."""
    def is_int(v):
        return isinstance(v, int) and not isinstance(v, bool)

    def is_num(v):
        return v is None or (isinstance(v, (int, float)) and not isinstance(v, bool))

    if not isinstance(idx, dict) or not is_int(idx.get("index_version")) or idx["index_version"] != INDEX_VERSION:
        return None
    if idx.get("jsonl") != name or name != f"OTC_{idx.get('datestamp')}.jsonl" or idx.get("jsonl_sha256") != sha256 \
            or not is_int(idx.get("jsonl_size")) or idx["jsonl_size"] != size or not isinstance(idx.get("stations"), list):
        return None
    out = []
    start = 0  # the least offset the next entry may have
    for e in idx["stations"]:
        if not isinstance(e, dict) or not is_int(e.get("offset")) or not is_int(e.get("length")) \
                or not isinstance(e.get("station_id"), str) or not isinstance(e.get("status"), str) \
                or not all(k in e and (e[k] is None or isinstance(e[k], str)) for k in _ENTRY_STR) \
                or not is_num(e.get("lat", 0)) or not is_num(e.get("lon", 0)) or "lat" not in e or "lon" not in e \
                or not isinstance(e.get("aliases"), dict) or not isinstance(e.get("sets"), list):
            return None
        if not all(isinstance(v, list) and all(isinstance(x, str) for x in v) for v in e["aliases"].values()):
            return None
        # the bounds check (CR D4): a line inside the file, and after the line before it and its line end, so
        # that no two entries overlap (CR2 DR9)
        if e["length"] <= 0 or e["offset"] < start or e["offset"] + e["length"] > size:
            return None
        start = e["offset"] + e["length"] + 1
        if e["status"] == "active" and (not isinstance(e["lat"], (int, float)) or not isinstance(e["lon"], (int, float))
                                        or not math.isfinite(e["lat"]) or not math.isfinite(e["lon"])
                                        or abs(e["lat"]) > 90 or abs(e["lon"]) > 180):
            return None
        for cs in e["sets"]:
            if not isinstance(cs, dict) or not all(k in cs and (cs[k] is None or isinstance(cs[k], str)) for k in _SET_KEYS) \
                    or not isinstance(cs.get("constituents"), list) or not all(isinstance(x, str) for x in cs["constituents"]):
                return None
            if e["status"] == "active" and (cs["convention_id"] not in conv or cs["licence_id"] not in lic):
                return None  # a reference that does not resolve: rebuild, and the pass raises invalid_release
        if e["status"] == "active":
            if e["offsets_licence_id"] is not None and e["offsets_licence_id"] not in lic:
                return None
            if e["recommended_set_id"] is not None and e["recommended_set_id"] not in {cs["set_id"] for cs in e["sets"]}:
                return None
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

    def kind(e, seen):
        if e.get("kind") is not None:
            return e["kind"]
        if e.get("type") == "subordinate" and e.get("reference_station_id"):
            ref = by_id.get(e["reference_station_id"])
            if ref is not None and ref["station_id"] not in seen:
                return kind(ref, seen | {e["station_id"]})
        return None

    resolved = {sid: kind(e, frozenset()) for sid, e in by_id.items()}
    for sid, k in resolved.items():
        by_id[sid]["kind"] = k


# --------------------------------------------------------------------------- Release

class Release:
    """One loaded OTC_{DATESTAMP} release. Immutable; every query method is here."""

    __slots__ = ("_meta", "_release", "_files", "_conventions", "_conv_by_id", "_licences", "_lic_by_id",
                 "_entries", "_by_id", "_tombs", "_alias", "_subs", "_stations", "_tomb_objs", "_mode", "_fh",
                 "_lock", "_lru", "_jsonl", "_constituent_names", "_stats", "_closed", "_zenodo_version_doi",
                 "_index_path", "_opened", "__weakref__")

    def __init__(self, *, meta, entries, files, mode, stations=None, tombstones=None, jsonl=None, index_path=None):
        self._meta = meta
        self._index_path = index_path
        self._opened = ()  # the files this release was loaded from (the client sets it; verify hashes them)
        rel = meta.get("release")
        if not isinstance(rel, dict) or not isinstance(rel.get("datestamp"), str):
            raise InvalidReleaseError("release.datestamp is missing")
        if rel.get("source_versions") is not None and not isinstance(rel.get("source_versions"), dict):
            raise InvalidReleaseError("release.source_versions is not an object")
        self._release = rel
        self._files = tuple(files)
        try:
            self._conventions = tuple(Convention._parse(c) for c in meta.get("conventions") or ())
            self._licences = tuple(Licence._parse(x) for x in meta.get("licences") or ())
        except (KeyError, TypeError, AttributeError) as e:
            raise InvalidReleaseError(f"conventions or licences: {e!r}") from e
        self._conv_by_id = {c.convention_id: c for c in self._conventions}
        self._lic_by_id = {x.licence_id: x for x in self._licences}
        parse_time(rel.get("created"), "release.created")
        _check_ids(entries, self._conventions, self._licences)
        _resolve_kinds(entries)
        active = sorted((e for e in entries if e.get("status") == "active"), key=lambda e: e["station_id"])
        self._entries = active
        self._by_id = {e["station_id"]: e for e in active}
        self._tombs = {e["station_id"]: e for e in entries if e.get("status") == "removed"}
        self._alias = {}
        self._subs = {}
        for e in active:
            for system, ids in (e.get("aliases") or {}).items():
                for i in ids:
                    self._alias.setdefault(system, {})[i] = e["station_id"]
            if e.get("type") == "subordinate" and e.get("reference_station_id"):
                self._subs.setdefault(e["reference_station_id"], []).append(e["station_id"])
        self._mode = mode
        self._stations = stations  # eager: id -> Station
        self._tomb_objs = tombstones  # eager: id -> Tombstone
        self._fh = None
        self._lock = threading.Lock()
        self._lru = OrderedDict()
        self._jsonl = jsonl
        self._constituent_names = None
        self._stats = None
        self._closed = False
        self._zenodo_version_doi = None
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

    @property
    def conventions(self) -> Tuple[Convention, ...]:
        return self._conventions

    def convention(self, convention_id: str) -> Optional[Convention]:
        return self._conv_by_id.get(convention_id)

    @property
    def licences(self) -> Tuple[Licence, ...]:
        return self._licences

    def licence(self, licence_id: str) -> Optional[Licence]:
        return self._lic_by_id.get(licence_id)

    @property
    def station_count(self) -> int:
        return len(self._entries)

    @property
    def tombstone_count(self) -> int:
        return len(self._tombs)

    @property
    def constituent_names(self) -> Tuple[str, ...]:
        if self._constituent_names is None:
            names = {n for e in self._entries for s in e.get("sets") or () for n in s.get("constituents") or ()}
            self._constituent_names = tuple(sorted(names))
        return self._constituent_names

    @property
    def stats(self) -> Stats:
        if self._stats is None:
            def count(values):
                out = {}
                for v in values:
                    if v is not None:
                        out[v] = out.get(v, 0) + 1
                return MappingProxyType(dict(sorted(out.items())))
            sets = [s for e in self._entries for s in e.get("sets") or ()]
            qc = [E.enum_or_raw(E.QcStatus, s.get("qc_status")) for s in sets]
            def norm(cls, v):  # bucket a value as the Station reports it (an unknown one is "other")
                m = E.enum_or_raw(cls, v)
                return None if m is None else m.value
            self._stats = Stats(count(norm(E.StationType, e.get("type")) for e in self._entries),
                                count(norm(E.Kind, e.get("kind")) for e in self._entries),
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

    def _station_from_entry(self, e) -> Station:
        if self._stations is not None:
            return self._stations[e["station_id"]]
        sid = e["station_id"]
        with self._lock:
            st = self._lru.get(sid)
            if st is not None:
                self._lru.move_to_end(sid)
                return st
            d = self._read_line(e)
        st = build_station(d, self._conv_by_id, self._lic_by_id, e.get("kind"))
        with self._lock:
            self._lru[sid] = st
            if len(self._lru) > LRU_SIZE:
                self._lru.popitem(last=False)
        return st

    def _check_open(self) -> None:
        if self._closed:
            raise FileError("the release is closed", path=None if self._jsonl is None else str(self._jsonl))

    def _read_line(self, e):
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
        try:
            if len(data) != e["length"]:
                raise InvalidReleaseError(f"short read of {self._jsonl} at {e['offset']}")
            d = _json(data, f"{self._jsonl} line of {e['station_id']}")
            if not isinstance(d, dict) or d.get("station_id") != e["station_id"]:
                raise InvalidReleaseError(f"the line at offset {e['offset']} of {self._jsonl} is not "
                                          f"{e['station_id']}")
        except InvalidReleaseError as ex:
            # the index does not match the file (CR D4): name it and drop it, so the next open rebuilds it
            if self._index_path is not None:
                try:
                    self._index_path.unlink()
                except FileNotFoundError:
                    pass
                except OSError as ux:
                    _log.warning("cannot delete %s: %s", self._index_path, ux)
                raise InvalidReleaseError(f"{self._index_path.name} does not match the release: {ex}") from ex
            raise
        return d

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

    def _filtered(self, country=None, type=None, kind=None, source=None, source_type=None):  # noqa: A002
        self._check_open()
        for name, v in (("country", country), ("type", type), ("kind", kind), ("source", source),
                        ("source_type", source_type)):
            _check_type(name, v, (str,))
        out = []
        for e in self._entries:
            if country is not None and e.get("country") != country:
                continue
            if type is not None and e.get("type") != str(type):
                continue
            if kind is not None and e.get("kind") != str(kind):
                continue
            sets = e.get("sets") or ()
            if source is not None and not any(s.get("source") == source and s.get("qc_status") in _USABLE for s in sets):
                continue
            if source_type is not None:
                rec = [s for s in sets if s.get("set_id") == e.get("recommended_set_id")]
                if not rec or rec[0].get("source_type") != str(source_type):
                    continue
            out.append(e)
        return out

    def stations(self, *, country=None, type=None, kind=None, source=None, source_type=None) -> Tuple[Station, ...]:  # noqa: A002
        """Active stations matching every filter, ordered by station_id."""
        return tuple(self._station_from_entry(e) for e in
                     self._filtered(country, type, kind, source, source_type))

    def iter_stations(self, *, country=None, type=None, kind=None, source=None, source_type=None) -> Iterator[Station]:  # noqa: A002
        """The same stations as stations(), one at a time. The arguments are checked when it is called."""
        entries = self._filtered(country, type, kind, source, source_type)
        return (self._station_from_entry(e) for e in entries)

    def search(self, *, name, limit=None, match=None, country=None, type=None, kind=None, source=None,  # noqa: A002
               source_type=None) -> Tuple[Station, ...]:
        _check_type("name", name, (str,), allow_none=False)
        limit = _limit(limit)
        if match is not None and match != "exact":
            raise InvalidArgumentError(f"match must be 'exact', not {match!r}")
        q = fold(name)
        if not q:
            raise InvalidArgumentError("the query is empty")
        ranked = []
        for e in self._filtered(country, type, kind, source, source_type):
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
             source_type=None) -> Tuple[Nearby, ...]:
        lat = _number("lat", lat, -90, 90)
        lon = _number("lon", lon, -180, 180)
        radius_km = _number("radius_km", radius_km, 0)
        limit = _limit(limit)
        hits = self._distances(lat, lon, radius_km, dict(country=country, type=type, kind=kind, source=source,
                                                         source_type=source_type))
        if limit is not None:
            hits = hits[:limit]
        return tuple(Nearby(self._station_from_entry(h[2]), h[0]) for h in hits)

    def nearest(self, *, lat, lon, max_km=None, country=None, type=None, kind=None, source=None,  # noqa: A002
                source_type=None) -> Optional[Nearby]:
        lat = _number("lat", lat, -90, 90)
        lon = _number("lon", lon, -180, 180)
        max_km = _number("max_km", max_km, 0, allow_none=True)
        hits = self._distances(lat, lon, max_km, dict(country=country, type=type, kind=kind, source=source,
                                                      source_type=source_type))
        return Nearby(self._station_from_entry(hits[0][2]), hits[0][0]) if hits else None

    def reference_station(self, station: Station) -> Optional[Station]:
        if not isinstance(station, Station):
            raise InvalidArgumentError("station must be a Station")
        off = station.subordinate_offsets
        if not station.is_subordinate or off is None or off.reference_station_id is None:
            return None
        return self.station(off.reference_station_id)

    def subordinates_of(self, station: Station) -> Tuple[Station, ...]:
        if not isinstance(station, Station):
            raise InvalidArgumentError("station must be a Station")
        return tuple(self.station(s) for s in sorted(self._subs.get(station.station_id, ())))

    def attribution(self, stations: Optional[Sequence[Station]] = None) -> str:
        """The CC BY 4.0 attribution text for what an app shows (spec §4.6)."""
        self._check_open()
        if stations is not None and (isinstance(stations, (str, bytes)) or not hasattr(stations, "__iter__")):
            raise InvalidArgumentError("stations must be a list of Station objects")
        stations = None if stations is None else list(stations)
        if not stations:  # None or an empty list: every licence in the release (CR D2 c)
            lic_ids = {x.licence_id for x in self._licences}
        else:
            lic_ids = set()
            for st in stations:
                if not isinstance(st, Station):
                    raise InvalidArgumentError("stations must be a list of Station objects")
                own = self.station(st.station_id)
                if own is None or (own is not st and own.raw != st.raw):
                    # unknown, removed or from another release: never skipped silently (CR D2 a)
                    raise InvalidArgumentError(f"station {st.station_id} is not an active station of release "
                                               f"{self.datestamp}")
                if st.recommended_set is not None:
                    lic_ids.add(st.recommended_set.licence.licence_id)
                off = st.subordinate_offsets
                if st.is_subordinate and off is not None:
                    if off.licence_id:
                        lic_ids.add(off.licence_id)
                    ref = self.station(off.reference_station_id) if off.reference_station_id else None
                    if ref is not None and ref.recommended_set is not None:
                        lic_ids.add(ref.recommended_set.licence.licence_id)
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
        return (f"Tidal constants: OpenTideConstants {self.datestamp}, {ident}, CC BY 4.0. Sources: "
                + "; ".join(parts))

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
    rel = meta.get("release") if isinstance(meta.get("release"), dict) else {}
    check_format(meta.get("format_version"), rel.get("min_reader_version"), rel.get("datestamp"))


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
    if d.get("status") == "active":
        build_station(d, conventions, licences, None)


def load_document(path: Path, mode: str, files, index_path: Optional[Path] = None,
                  index_sha256: Optional[str] = None) -> Release:
    """Load a release from a data file (.json, .json.gz or .jsonl with its .meta.json)."""
    name = path.name
    if name.endswith(".jsonl"):
        meta = _json(_read_bytes(meta_path_for(path)), str(meta_path_for(path)))
        _check_meta(meta, str(meta_path_for(path)))
        conv, lic = _refs(meta, str(meta_path_for(path)))
        if mode == "stream":
            entries = _stream_index(path, conv, lic, index_path, index_sha256)
            return Release(meta=meta, entries=entries, files=files, mode="stream", jsonl=path, index_path=index_path)
        data = _read_bytes(path)
        docs = []
        for i, line in enumerate(data.split(b"\n")):
            if line.strip():
                docs.append(_json(line, f"{path} line {i + 1}"))
        return _eager(meta, docs, files)
    data = _read_bytes(path)
    if name.endswith(".gz"):
        try:
            data = gzip.decompress(data)
        except (OSError, EOFError, zlib.error) as e:
            raise InvalidReleaseError(f"{path}: not gzip: {e}") from e
    doc = _json(data, str(path))
    _check_meta(doc, str(path))
    stations = doc.get("stations")
    if not isinstance(stations, list):
        raise InvalidReleaseError(f"{path}: stations is missing")
    meta = {k: v for k, v in doc.items() if k != "stations"}
    if mode == "stream":
        # a .json file has no lines to seek to: keep the parsed stations, as in eager mode
        mode = "eager"
    return _eager(meta, stations, files)


def _eager(meta, docs, files) -> Release:
    conv, lic = _refs(meta, "the release")
    try:
        entries = [_entry(d) for d in docs]
    except (KeyError, TypeError, AttributeError) as e:
        raise InvalidReleaseError(f"bad station or reference data: {e!r}") from e
    _resolve_kinds(entries)
    kinds = {e["station_id"]: e.get("kind") for e in entries}
    stations, tombs = {}, {}
    for d in docs:
        if d.get("status") == "active":
            stations[d["station_id"]] = build_station(d, conv, lic, kinds.get(d["station_id"]))
        elif d.get("status") == "removed":
            tombs[d["station_id"]] = Tombstone._parse(d)
    return Release(meta=meta, entries=entries, files=files, mode="eager", stations=stations, tombstones=tombs)


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    except OSError as e:
        raise FileError(f"cannot read {path}: {e}", path=str(path), cause=e) from e
    return h.hexdigest()


def _stream_index(path: Path, conv, lic, index_path: Optional[Path], index_sha256: Optional[str] = None):
    """Use index-v1.json when it is fresh, else make one pass over the .jsonl and write it (spec §6.2).
    index_sha256: the .jsonl digest from .verified (computed when not given)."""
    size = path.stat().st_size if path.exists() else None
    if size is None:
        raise FileError(f"cannot open {path}", path=str(path))
    if index_path is not None and index_path.exists():
        try:
            idx = json.loads(index_path.read_text(encoding="utf-8"))
            entries = _usable_index(idx, path.name, index_sha256 or file_sha256(path), size, conv, lic)
            if entries is not None:
                return entries
        except (OSError, ValueError, RecursionError):
            pass  # a stale or broken index is rebuilt
    entries = []
    h = hashlib.sha256()
    offset = 0
    try:
        with open(path, "rb") as f:
            for i, line in enumerate(f):
                h.update(line)
                body = line.rstrip(b"\r\n")
                if body.strip():
                    d = _json(body, f"{path} line {i + 1}")
                    if not isinstance(d, dict) or "station_id" not in d:
                        raise InvalidReleaseError(f"{path} line {i + 1}: not a station")
                    _validate_refs(d, conv, lic)
                    try:
                        entries.append(_entry(d, offset, len(body)))
                    except (KeyError, TypeError, AttributeError) as e:
                        raise InvalidReleaseError(f"{path} line {i + 1}: {e!r}") from e
                offset += len(line)
    except OSError as e:
        raise FileError(f"cannot read {path}: {e}", path=str(path), cause=e) from e
    _resolve_kinds(entries)
    if index_path is not None:
        from ._cache import atomic_write
        from ._client import SDK
        doc = {"index_version": INDEX_VERSION, "datestamp": path.name[len("OTC_"):-len(".jsonl")], "jsonl": path.name,
               "jsonl_sha256": h.hexdigest(), "jsonl_size": size, "by": SDK, "stations": entries}
        try:
            atomic_write(index_path, json.dumps(doc, ensure_ascii=False).encode("utf-8"))
        except OSError:
            pass  # the index only saves work; the release loads without it
    return entries


