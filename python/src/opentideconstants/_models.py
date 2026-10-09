"""The immutable data objects (spec §3, §4.4 to §4.7). Frozen dataclasses with __slots__."""
from __future__ import annotations

import datetime as _dt
import math
import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Optional, Tuple

from . import _enums as E
from ._errors import InvalidReleaseError

_EMPTY: Mapping[str, Any] = MappingProxyType({})


def freeze(v):
    """A read-only copy of parsed JSON: dicts become read-only mappings, lists become tuples."""
    if isinstance(v, dict):
        return MappingProxyType({k: freeze(x) for k, x in v.items()})
    if isinstance(v, list):
        return tuple(freeze(x) for x in v)
    return v


_TIME_RE = re.compile(r"\A([0-9]{4})-([0-9]{2})-([0-9]{2})[Tt ]([0-9]{2}):([0-9]{2}):([0-9]{2})(\.[0-9]+)?"
                      r"([Zz]|[+-][0-9]{2}:?[0-9]{2})?\Z")


def parse_time(v, what="time"):
    """An RFC 3339 time (any number of fraction digits, upper- or lower-case T and Z, also +HHMM), the same on
    every Python version. No offset means UTC. Anything else is InvalidReleaseError."""
    if v is None:
        return None
    if not isinstance(v, str):
        raise InvalidReleaseError(f"{what}: not a string: {v!r}")
    m = _TIME_RE.match(v)
    try:
        if m is None:
            raise ValueError("not RFC 3339")
        y, mo, d, h, mi, sec, frac, off = m.groups()
        us = int((frac[1:] + "000000")[:6]) if frac else 0
        tz = _dt.timezone.utc
        if off and off not in ("Z", "z"):
            sign = -1 if off[0] == "-" else 1
            hh, mm = int(off[1:3]), int(off[-2:])
            if hh > 23 or mm > 59:
                raise ValueError("bad offset")
            tz = _dt.timezone(sign * _dt.timedelta(hours=hh, minutes=mm))
        t = _dt.datetime(int(y), int(mo), int(d), int(h), int(mi), int(sec), us, tzinfo=tz)
    except ValueError as e:
        raise InvalidReleaseError(f"{what}: not an ISO 8601 time: {v!r}") from e
    return t.astimezone(_dt.timezone.utc)


def _time_or_none(v, what):
    """A build-only time (provenance.build): a malformed one is None, not a failed station (spec §4.6)."""
    try:
        return parse_time(v, what)
    except InvalidReleaseError:
        return None


def _num(v):
    return float("nan") if v is None else v


@dataclass(frozen=True, slots=True)
class FileInfo:
    name: str
    url: Optional[str]
    size: Optional[int]
    sha256: Optional[str]


@dataclass(frozen=True, slots=True)
class ReleaseInfo:
    datestamp: str
    format_version: str
    concept_doi: Optional[str]
    zenodo_version_doi: Optional[str]
    content_sha256: Optional[str]
    files: Tuple[FileInfo, ...]
    _min_reader_version: Optional[str] = field(default=None, repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class UpdateResult:
    updated: bool
    from_: str
    to: str


@dataclass(frozen=True, slots=True)
class Convention:
    convention_id: str
    phase_reference: Optional[E.PhaseReference]
    utc_offset_hours: Optional[float]
    v0_model: Optional[str]
    nodal_handling: Optional[E.NodalHandling]
    nodal_formula_ids: Optional[Mapping[str, Any]]
    constituent_table_version: Optional[str]
    tables_sha256: Optional[str]
    canary: Optional[Mapping[str, Any]]
    raw: Mapping[str, Any] = field(repr=False, compare=False)

    def __hash__(self):  # CR D16: hashable by id; == still compares the fields
        return hash(self.convention_id)

    @classmethod
    def _parse(cls, d):
        return cls(d["convention_id"], E.enum_or_raw(E.PhaseReference, d.get("phase_reference")),
                   d.get("utc_offset_hours"), d.get("v0_model"), E.enum_or_raw(E.NodalHandling, d.get("nodal_handling")),
                   freeze(d.get("nodal_formula_ids")), d.get("constituent_table_version"), d.get("tables_sha256"),
                   freeze(d.get("canary")), freeze(d))


@dataclass(frozen=True, slots=True)
class Licence:
    licence_id: str
    spdx: Optional[str]
    provider: Optional[str]
    citation: Optional[str]
    attribution: Optional[str]
    url: Optional[str]
    raw: Mapping[str, Any] = field(repr=False, compare=False)

    def __hash__(self):  # CR D16: hashable by id; == still compares the fields
        return hash(self.licence_id)

    @classmethod
    def _parse(cls, d):
        return cls(d["licence_id"], d.get("spdx"), d.get("provider"), d.get("citation"), d.get("attribution"),
                   d.get("url"), freeze(d))


@dataclass(frozen=True, slots=True, eq=False)  # holds a mapping: identity equality and hash (CR D16)
class Constituent:
    name: str
    source_name: Optional[str]
    doodson: Optional[str]
    speed_deg_per_hour: Optional[float]
    amplitude_m: float
    phase_deg: float
    amp_uncertainty_m: Optional[float]
    phase_uncertainty_deg: Optional[float]
    kept_reason: Optional[str]
    raw: Mapping[str, Any] = field(repr=False, compare=False)

    @classmethod
    def _parse(cls, d):
        return cls(d["name"], d.get("source_name"), d.get("doodson"), d.get("speed_deg_per_hour"), d.get("amplitude_m"),
                   d.get("phase_deg"), d.get("amp_uncertainty_m"), d.get("phase_uncertainty_deg"), d.get("kept_reason"),
                   freeze(d))


@dataclass(frozen=True, slots=True, eq=False)  # holds a mapping: identity equality and hash (CR D16)
class QcFlag:
    flag: E.QcFlagName
    reason: Optional[str]
    values: Optional[Mapping[str, Optional[float]]]

    @classmethod
    def _parse(cls, d):
        return cls(E.enum_or_raw(E.QcFlagName, d.get("flag")), d.get("reason"), freeze(d.get("values")))


@dataclass(frozen=True, slots=True)
class DroppedConstituent:
    name: str
    dropped_reason: E.DroppedReason
    detail: Optional[str]

    @classmethod
    def _parse(cls, d):
        return cls(d.get("name"), E.enum_or_raw(E.DroppedReason, d.get("dropped_reason")), d.get("detail"))


@dataclass(frozen=True, slots=True)
class RecordSpan:
    start: Optional[_dt.datetime]
    end: Optional[_dt.datetime]
    good_samples: Optional[int]


@dataclass(frozen=True, slots=True, eq=False)  # holds a mapping: identity equality and hash (CR D16)
class Datum:
    msl_offset_m: Optional[float]
    named: Mapping[str, float]


@dataclass(frozen=True, slots=True, eq=False)  # holds a mapping: identity equality and hash (CR D16)
class ProvenanceBuild:
    """The build-only fields of a set's provenance (``provenance.build``)."""
    build_commit: Optional[str]
    built_at: Optional[_dt.datetime]
    fetched_at: Optional[_dt.datetime]
    run_id: Optional[str]
    tool_versions: Optional[Mapping[str, str]]

    @classmethod
    def _parse(cls, d):
        if not isinstance(d, dict):
            return None  # format 1.0 requires it; a malformed set still loads (spec §7.3)
        return cls(d.get("build_commit"), _time_or_none(d.get("built_at"), "provenance.build.built_at"),
                   _time_or_none(d.get("fetched_at"), "provenance.build.fetched_at"), d.get("run_id"),
                   freeze(d.get("tool_versions")))


@dataclass(frozen=True, slots=True, eq=False)  # holds a mapping: identity equality and hash (CR D16)
class Provenance:
    build: Optional[ProvenanceBuild]
    adapter_version: Optional[str]
    input_sha256: Optional[Tuple[str, ...]]
    carried_from_release: Optional[str]
    selection_reason: Optional[str]
    decision: Optional[Mapping[str, Any]]
    raw: Mapping[str, Any] = field(repr=False, compare=False)

    @classmethod
    def _parse(cls, d):
        d = d or {}
        return cls(ProvenanceBuild._parse(d.get("build")), d.get("adapter_version"), freeze(d.get("input_sha256")),
                   d.get("carried_from_release"), d.get("selection_reason"), freeze(d.get("decision")), freeze(d))


_EVIDENCE = ("comparator_kind", "comparator_id", "distance_km", "lag_min", "detail")


@dataclass(frozen=True, slots=True, eq=False)  # holds a mapping: identity equality and hash (CR D16)
class TimeBase:
    """The time-base annotation of the record behind a set (spec §4.5)."""
    code: E.TimeBaseCode
    reason: Optional[str]
    declared: Optional[str]
    published: Optional[str]
    correction: Optional[Mapping[str, Optional[str]]]
    months_dropped: Tuple[str, ...]
    decided_in: Optional[str]
    decided_build_commit: Optional[str]
    evidence: Tuple[Mapping[str, Any], ...]

    @classmethod
    def _parse(cls, d):
        if not isinstance(d, dict):
            return None
        corr = d.get("correction")
        if isinstance(corr, dict):
            corr = MappingProxyType({"from": corr.get("from"), "to": corr.get("to")})
        else:
            corr = None
        evidence = tuple(MappingProxyType({k: freeze(e.get(k)) for k in _EVIDENCE})
                         for e in d.get("evidence") or () if isinstance(e, dict))
        months = d.get("months_dropped") or []
        if not isinstance(months, list) or not all(isinstance(x, str) for x in months):
            raise InvalidReleaseError(f"time_base.months_dropped is not a list of strings: {months!r}")
        return cls(E.enum_or_raw(E.TimeBaseCode, d.get("code")), d.get("reason"), d.get("declared"),
                   d.get("published"), corr, tuple(months), d.get("decided_in"),
                   d.get("decided_build_commit"), evidence)


_PREVIOUS = ("time_mae_min", "time_p95_min", "time_bias_min", "height_mae_m", "range_error_m", "missed_events",
             "extra_events")


@dataclass(frozen=True, slots=True, eq=False)  # holds a mapping: identity equality and hash (CR D16)
class Validation:
    set_id: str
    reference_source: Optional[str]
    reference_station: Optional[str]
    reference_distance_km: Optional[float]
    window: Optional[str]
    time_mae_min: Optional[float]
    time_p95_min: Optional[float]
    time_bias_min: Optional[float]
    height_mae_m: Optional[float]
    range_error_m: Optional[float]
    missed_events: Optional[int]
    extra_events: Optional[int]
    previous_release: Optional[Mapping[str, Any]]

    @classmethod
    def _parse(cls, d):
        prev = d.get("previous_release")
        if isinstance(prev, dict):
            # a value that is not a number is null, as in the other SDKs (spec §4.6)
            prev = MappingProxyType({k: (prev.get(k) if _finite(prev.get(k)) else None) for k in _PREVIOUS})
        else:
            prev = None
        return cls(d.get("set_id"), d.get("reference_source"), d.get("reference_station"),
                   d.get("reference_distance_km"), d.get("window"), d.get("time_mae_min"), d.get("time_p95_min"),
                   d.get("time_bias_min"), d.get("height_mae_m"), d.get("range_error_m"), d.get("missed_events"),
                   d.get("extra_events"), prev)


@dataclass(frozen=True, slots=True)
class SubordinateOffsets:
    reference_station_id: str
    time_offset_high_min: Optional[float]
    time_offset_low_min: Optional[float]
    height_offset_high: Optional[float]
    height_offset_low: Optional[float]
    height_adjusted_type: Optional[E.HeightAdjustedType]
    licence_id: Optional[str]

    @classmethod
    def _parse(cls, d):
        return cls(d.get("reference_station_id"), d.get("time_offset_high_min"), d.get("time_offset_low_min"),
                   d.get("height_offset_high"), d.get("height_offset_low"),
                   E.enum_or_raw(E.HeightAdjustedType, d.get("height_adjusted_type")), d.get("licence_id"))


@dataclass(frozen=True, slots=True)
class ConstantSet:
    set_id: str
    source: str
    source_type: E.SourceType
    quantity: E.Quantity
    source_record_id: Optional[str]
    source_version: Optional[str]
    record_span: Optional[RecordSpan]
    datum: Optional[Datum]
    qc_status: E.QcStatus
    qc_flags: Tuple[QcFlag, ...]
    dropped_constituents: Tuple[DroppedConstituent, ...]
    time_base: Optional[TimeBase]
    _is_recommended: bool
    convention: Convention
    licence: Licence
    provenance: Provenance
    validation: Tuple[Validation, ...]
    raw: Mapping[str, Any] = field(repr=False, compare=False)
    _constituents: Any = field(default=None, repr=False, compare=False)

    def __hash__(self):  # CR D16: hashable by id; == still compares the fields
        return hash(self.set_id)

    @property
    def is_recommended(self) -> bool:
        return self._is_recommended

    @property
    def constituents(self) -> Tuple[Constituent, ...]:
        """The constituents the fit kept, in file order. Built on first use (spec §6.1)."""
        c = self._constituents
        if c is None:
            c = tuple(Constituent._parse(x) for x in (self.raw.get("constituents") or ()))
            object.__setattr__(self, "_constituents", c)
        return c

    def constituent(self, name: str) -> Optional[Constituent]:
        for c in self.constituents:
            if c.name == name:
                return c
        return None


@dataclass(frozen=True, slots=True)
class Tombstone:
    station_id: str
    name: Optional[str]
    status: E.StationStatus
    removed_in: Optional[str]
    removed_reason: Optional[E.RemovedReason]
    merged_into: Optional[str]
    detail: Optional[str]
    raw: Mapping[str, Any] = field(repr=False, compare=False)

    def __hash__(self):  # CR D16: hashable by id; == still compares the fields
        return hash(self.station_id)

    @classmethod
    def _parse(cls, d):
        return cls(d["station_id"], d.get("name"), E.enum_or_raw(E.StationStatus, d.get("status")),
                   d.get("removed_in"), E.enum_or_raw(E.RemovedReason, d.get("removed_reason")),
                   d.get("merged_into"), d.get("detail"), freeze(d))


@dataclass(frozen=True, slots=True)
class Station:
    station_id: str
    name: str
    country: Optional[str]
    lat: float
    lon: float
    type: E.StationType
    kind: Optional[E.Kind]
    timezone: Optional[str]
    aliases: Mapping[str, Tuple[str, ...]]
    status: E.StationStatus
    subordinate_offsets: Optional[SubordinateOffsets]
    validation: Tuple[Validation, ...]
    recommended_set: Optional[ConstantSet]
    raw: Mapping[str, Any] = field(repr=False, compare=False)
    _sets: Tuple[ConstantSet, ...] = field(default=(), repr=False, compare=False)

    def __hash__(self):  # CR D16: hashable by id; == still compares the fields
        return hash(self.station_id)

    @property
    def is_reference(self) -> bool:
        return self.type == E.StationType.REFERENCE

    @property
    def is_subordinate(self) -> bool:
        return self.type == E.StationType.SUBORDINATE

    @property
    def is_tide(self) -> bool:
        return self.kind == E.Kind.TIDE

    @property
    def is_current(self) -> bool:
        return self.kind == E.Kind.CURRENT

    def constant_sets(self, *, include_no_constants: bool = False) -> Tuple[ConstantSet, ...]:
        """The recommended set first, then the others by set_id. Sets with qc_status no_constants (listed, but
        with no fitted constants) only with include_no_constants=True."""
        if not isinstance(include_no_constants, bool):
            from ._errors import InvalidArgumentError
            raise InvalidArgumentError("include_no_constants must be a boolean")
        return tuple(s for s in self._sets if include_no_constants or s.qc_status != E.QcStatus.NO_CONSTANTS)

    def constant_set(self, set_id: str) -> Optional[ConstantSet]:
        for s in self._sets:
            if s.set_id == set_id:
                return s
        return None


@dataclass(frozen=True, slots=True)
class Nearby:
    station: Station
    distance_km: float


@dataclass(frozen=True, slots=True, eq=False)  # holds a mapping: identity equality and hash (CR D16)
class Stats:
    type: Mapping[str, int]
    kind: Mapping[str, int]
    country: Mapping[str, int]
    source: Mapping[str, int]
    qc_status: Mapping[str, int]


# --------------------------------------------------------------------------- building a Station from its JSON


def _finite(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def build_station(d, conventions, licences, kind):
    """Build an active Station from its parsed JSON. conventions/licences: id -> object. Raises
    InvalidReleaseError when a reference does not resolve."""
    try:
        sid = d["station_id"]
        rid = d.get("recommended_set_id")
        rows = tuple(Validation._parse(v) for v in (d.get("validation") or ()))
        sets = []
        for cs in d.get("constant_sets") or ():
            conv = conventions.get(cs.get("convention_id"))
            if conv is None:
                raise InvalidReleaseError(f"{cs.get('set_id')}: convention_id {cs.get('convention_id')!r} does not resolve")
            lic = licences.get(cs.get("licence_id"))
            if lic is None:
                raise InvalidReleaseError(f"{cs.get('set_id')}: licence_id {cs.get('licence_id')!r} does not resolve")
            if not all(isinstance(c, dict) and isinstance(c.get("name"), str) for c in cs.get("constituents") or ()):
                raise InvalidReleaseError(f"{cs.get('set_id')}: a constituent has no name")
            span = cs.get("record_span")
            datum = cs.get("datum")
            set_id = cs["set_id"]
            sets.append(ConstantSet(
                set_id, cs.get("source"), E.enum_or_raw(E.SourceType, cs.get("source_type")),
                E.enum_or_raw(E.Quantity, cs.get("quantity")), cs.get("source_record_id"), cs.get("source_version"),
                None if span is None else RecordSpan(parse_time(span.get("start"), "record_span.start"),
                                                     parse_time(span.get("end"), "record_span.end"),
                                                     span.get("good_samples")),
                None if datum is None else Datum(datum.get("msl_offset_m"), freeze(dict(datum.get("named") or {}))),
                E.enum_or_raw(E.QcStatus, cs.get("qc_status")),
                tuple(QcFlag._parse(f) for f in cs.get("qc_flags") or ()),
                tuple(DroppedConstituent._parse(x) for x in cs.get("dropped_constituents") or ()),
                TimeBase._parse(cs.get("time_base")), rid is not None and set_id == rid, conv, lic, Provenance._parse(cs.get("provenance")),
                tuple(sorted((v for v in rows if v.set_id == set_id), key=lambda v: v.window or "")),
                freeze(cs)))
        rec = [s for s in sets if rid is not None and s.set_id == rid]
        if rid is not None and not rec:
            raise InvalidReleaseError(f"{sid}: recommended_set_id {rid!r} does not resolve")
        ordered = tuple(rec + sorted((s for s in sets if s.set_id != rid), key=lambda s: s.set_id))
        off = d.get("subordinate_offsets")
        if off is not None and off.get("licence_id") is not None and off.get("licence_id") not in licences:
            raise InvalidReleaseError(f"{sid}: subordinate_offsets.licence_id does not resolve")
        aliases = {}
        for system, ids in (d.get("aliases") or {}).items():
            aliases[system] = tuple(ids) if isinstance(ids, list) else (ids,)
        lat, lon = d.get("lat"), d.get("lon")
        if not (_finite(lat) and -90 <= lat <= 90 and _finite(lon) and -180 <= lon <= 180):
            raise InvalidReleaseError(f"{sid}: lat/lon must be numbers in range, not {lat!r}, {lon!r}")
        return Station(
            sid, d.get("name"), d.get("country"), float(lat), float(lon),
            E.enum_or_raw(E.StationType, d.get("type")), None if kind is None else E.enum_or_raw(E.Kind, kind),
            d.get("timezone"), MappingProxyType(aliases), E.enum_or_raw(E.StationStatus, d.get("status")),
            None if off is None else SubordinateOffsets._parse(off), rows, rec[0] if rec else None, freeze(d),
            ordered)
    except InvalidReleaseError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        raise InvalidReleaseError(f"station {d.get('station_id') if isinstance(d, dict) else d!r}: {e!r}") from e
