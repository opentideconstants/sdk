"""One loaded release (spec §3, §4.3 to §4.7, §6). Eager mode parses everything at load; stream mode
keeps an index of the .jsonl lines and reads stations on demand."""
from __future__ import annotations

import gzip
import hashlib
import json
import math
import os
import threading
import zlib
from collections import OrderedDict
from pathlib import Path
from types import MappingProxyType
from typing import Iterator, Optional, Sequence, Tuple

from . import _enums as E
from ._errors import (FileError, InvalidArgumentError, InvalidReleaseError, StationNotFoundError,
                      StationRemovedError, UnsupportedFormatError)
from ._fold import fold
from ._models import (Convention, FileInfo, Licence, Nearby, Station, Stats, Tombstone, build_station, freeze,
                      own_kind, parse_time)

SUPPORTED_FORMAT_MAJORS = (0,)
EARTH_R_KM = 6371.0088
INDEX_VERSION = 1
LRU_SIZE = 256
DATA_URL = "https://data.opentideconstants.org/"


# --------------------------------------------------------------------------- reading files

def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as e:
        raise FileError(f"cannot read {path}: {e}", path=str(path), cause=e) from e


def _json(data: bytes, what: str):
    try:
        return json.loads(data.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        raise InvalidReleaseError(f"{what}: not JSON: {e}") from e


def check_format(fv) -> None:
    if not isinstance(fv, str) or "." not in fv:
        raise InvalidReleaseError(f"format_version missing or not MAJOR.MINOR: {fv!r}")
    try:
        major = int(fv.split(".", 1)[0])
    except ValueError as e:
        raise InvalidReleaseError(f"format_version not MAJOR.MINOR: {fv!r}") from e
    if major not in SUPPORTED_FORMAT_MAJORS:
        raise UnsupportedFormatError(f"format {fv} is not supported (supported majors: {list(SUPPORTED_FORMAT_MAJORS)})")


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
    if isinstance(v, bool) or not isinstance(v, (int, float)) or math.isnan(v):
        raise InvalidArgumentError(f"{name} must be a number")
    if (lo is not None and v < lo) or (hi is not None and v > hi):
        raise InvalidArgumentError(f"{name} out of range: {v}")
    return float(v)


def haversine(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R_KM * math.asin(min(1.0, math.sqrt(a)))


# --------------------------------------------------------------------------- index entries

def _entry(d, offset=None, length=None):
    """The index entry of one station line (spec §6.2, plus the set facts the filters need)."""
    e = {"station_id": d["station_id"], "status": d.get("status")}
    if offset is not None:
        e["offset"], e["length"] = offset, length
    if d.get("status") != "active":
        return e
    off = d.get("subordinate_offsets") or {}
    e.update({
        "name": d.get("name"), "name_folded": fold(d.get("name") or ""), "country": d.get("country"),
        "type": d.get("type"), "kind": own_kind(d), "lat": d.get("lat"), "lon": d.get("lon"),
        "aliases": {k: (list(v) if isinstance(v, list) else [v]) for k, v in (d.get("aliases") or {}).items()},
        "reference_station_id": off.get("reference_station_id"),
        "recommended_set_id": d.get("recommended_set_id"),
        "sets": [{"set_id": s.get("set_id"), "source": s.get("source"), "source_type": s.get("source_type"),
                  "qc_status": s.get("qc_status"), "licence_id": s.get("licence_id"),
                  "constituents": [c.get("name") for c in s.get("constituents") or ()]}
                 for s in d.get("constant_sets") or ()],
        "offsets_licence_id": off.get("licence_id"),
    })
    return e


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
                 "_lock", "_lru", "_jsonl", "_constituent_names", "_stats", "_closed")

    def __init__(self, *, meta, entries, files, mode, stations=None, tombstones=None, jsonl=None):
        self._meta = meta
        rel = meta.get("release")
        if not isinstance(rel, dict) or not isinstance(rel.get("datestamp"), str):
            raise InvalidReleaseError("release.datestamp is missing")
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
    def doi(self):
        return self._release.get("doi")

    @property
    def concept_doi(self):
        return self._release.get("concept_doi")

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
            self._stats = Stats(count(e.get("type") for e in self._entries),
                                count(e.get("kind") for e in self._entries),
                                count(e.get("country") for e in self._entries),
                                count(s.get("source") for s in sets), count(s.get("qc_status") for s in sets))
        return self._stats

    @property
    def citation(self) -> str:
        created = self.created
        year = created.year if created else self.datestamp[:4]
        ident = f"https://doi.org/{self.doi}" if self.doi else f"{DATA_URL}OTC_{self.datestamp}.json"
        return f"OpenTideConstants contributors ({year}). OpenTideConstants, release {self.datestamp} [Data set]. {ident}"

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

    def _read_line(self, e):
        if self._fh is None:
            raise FileError("the release is closed", path=str(self._jsonl))
        try:
            self._fh.seek(e["offset"])
            data = self._fh.read(e["length"])
        except OSError as ex:
            raise FileError(f"cannot read {self._jsonl}: {ex}", path=str(self._jsonl), cause=ex) from ex
        return _json(data, f"{self._jsonl} line of {e['station_id']}")

    def station(self, station_id: str) -> Optional[Station]:
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
        _check_type("system", system, (str,), allow_none=False)
        _check_type("alias_id", alias_id, (str,), allow_none=False)
        sid = self._alias.get(str(system), {}).get(alias_id)
        return None if sid is None else self.station(sid)

    def _filtered(self, country=None, type=None, kind=None, source=None, source_type=None):  # noqa: A002
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
            if source is not None and not any(s.get("source") == source and s.get("qc_status") != "excluded" for s in sets):
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
        """The same stations as stations(), one at a time."""
        entries = self._filtered(country, type, kind, source, source_type)
        for e in entries:
            yield self._station_from_entry(e)

    def search(self, *, name, limit=None, match=None, country=None, type=None, kind=None, source=None,  # noqa: A002
               source_type=None) -> Tuple[Station, ...]:
        _check_type("name", name, (str,), allow_none=False)
        _check_type("limit", limit, (int,))
        if limit is not None and limit < 0:
            raise InvalidArgumentError("limit must not be negative")
        if match is not None and match != "exact":
            raise InvalidArgumentError(f"match must be 'exact', not {match!r}")
        q = fold(name)
        if not q:
            raise InvalidArgumentError("the query is empty")
        ranked = []
        for e in self._filtered(country, type, kind, source, source_type):
            n = e["name_folded"]
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
        _check_type("limit", limit, (int,))
        if limit is not None and limit < 0:
            raise InvalidArgumentError("limit must not be negative")
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
        if stations is None:
            lic_ids = {x.licence_id for x in self._licences}
        else:
            if isinstance(stations, (str, bytes)) or not hasattr(stations, "__iter__"):
                raise InvalidArgumentError("stations must be a list of Station objects")
            lic_ids = set()
            for st in stations:
                if not isinstance(st, Station):
                    raise InvalidArgumentError("stations must be a list of Station objects")
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
            lic = self._lic_by_id.get(lid)
            if lic is None or lic.provider in seen:
                continue
            seen.add(lic.provider)
            parts.append(f"{lic.provider}: {lic.attribution}")
        ident = f"doi:{self.doi}" if self.doi else f"{DATA_URL}OTC_{self.datestamp}.json"
        return (f"Tidal constants: OpenTideConstants {self.datestamp}, {ident}, CC BY 4.0. Sources: "
                + "; ".join(parts))

    def _close(self) -> None:
        self._closed = True
        fh, self._fh = self._fh, None
        if fh is not None:
            fh.close()

    def __repr__(self) -> str:
        return f"<Release {self.datestamp} format {self.format_version} {self._mode}>"


# --------------------------------------------------------------------------- loading

def _check_meta(meta, what):
    if not isinstance(meta, dict):
        raise InvalidReleaseError(f"{what}: not a JSON object")
    check_format(meta.get("format_version"))


def _validate_refs(d, conventions, licences):
    if d.get("status") == "active":
        build_station(d, conventions, licences, None)


def load_document(path: Path, mode: str, files, index_path: Optional[Path] = None) -> Release:
    """Load a release from a data file (.json, .json.gz or .jsonl with its .meta.json)."""
    name = path.name
    if name.endswith(".jsonl"):
        meta = _json(_read_bytes(meta_path_for(path)), str(meta_path_for(path)))
        _check_meta(meta, str(meta_path_for(path)))
        conv = {c.convention_id: c for c in (Convention._parse(c) for c in meta.get("conventions") or ())}
        lic = {x.licence_id: x for x in (Licence._parse(c) for c in meta.get("licences") or ())}
        if mode == "stream":
            entries = _stream_index(path, conv, lic, index_path)
            return Release(meta=meta, entries=entries, files=files, mode="stream", jsonl=path)
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
    try:
        conv = {c.convention_id: c for c in (Convention._parse(c) for c in meta.get("conventions") or ())}
        lic = {x.licence_id: x for x in (Licence._parse(c) for c in meta.get("licences") or ())}
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


def _stream_index(path: Path, conv, lic, index_path: Optional[Path]):
    """Read index-v1.json when it matches the .jsonl, else make one pass and build it (spec §6.2)."""
    size = path.stat().st_size if path.exists() else None
    if size is None:
        raise FileError(f"cannot open {path}", path=str(path))
    if index_path is not None and index_path.exists():
        try:
            idx = json.loads(index_path.read_text(encoding="utf-8"))
            if (idx.get("index_version") == INDEX_VERSION and idx.get("jsonl_size") == size
                    and idx.get("jsonl_sha256") == file_sha256(path)):
                return idx["entries"]
        except (OSError, ValueError, KeyError, AttributeError):
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
        doc = {"index_version": INDEX_VERSION, "jsonl_sha256": h.hexdigest(), "jsonl_size": size,
               "entries": entries}
        try:
            atomic_write(index_path, json.dumps(doc, ensure_ascii=False).encode("utf-8"))
        except OSError:
            pass  # the index only saves work; the release loads without it
    return entries


