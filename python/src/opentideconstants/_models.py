"""The immutable data objects (spec §3, §4.4 to §4.7). Frozen dataclasses with __slots__."""
from __future__ import annotations

import datetime as _dt
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


def parse_time(v, what="time"):
    if v is None:
        return None
    if not isinstance(v, str):
        raise InvalidReleaseError(f"{what}: not a string: {v!r}")
    s = v[:-1] + "+00:00" if v.endswith("Z") else v
    try:
        t = _dt.datetime.fromisoformat(s)
    except ValueError as e:
        raise InvalidReleaseError(f"{what}: not an ISO 8601 time: {v!r}") from e
    if t.tzinfo is None:
        t = t.replace(tzinfo=_dt.timezone.utc)
    return t.astimezone(_dt.timezone.utc)


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
    doi: Optional[str]
    files: Tuple[FileInfo, ...]


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

    @classmethod
    def _parse(cls, d):
        return cls(d["licence_id"], d.get("spdx"), d.get("provider"), d.get("citation"), d.get("attribution"),
                   d.get("url"), freeze(d))


@dataclass(frozen=True, slots=True)
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


@dataclass(frozen=True, slots=True)
class QcFlag:
    flag: E.QcFlagName
    verdict: Optional[str]
    values: Any

    @classmethod
    def _parse(cls, d):
        return cls(E.enum_or_raw(E.QcFlagName, d.get("flag")), d.get("verdict"), freeze(d.get("values")))


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


@dataclass(frozen=True, slots=True)
class Datum:
    msl_offset_m: Optional[float]
    named: Mapping[str, float]


@dataclass(frozen=True, slots=True)
class Provenance:
    build_commit: Optional[str]
    adapter_version: Optional[str]
    input_sha256: Optional[Tuple[str, ...]]
    time_base: Optional[Mapping[str, Any]]
    selection_reason: Optional[str]
    decision: Optional[Mapping[str, Any]]
    raw: Mapping[str, Any] = field(repr=False, compare=False)

    @classmethod
    def _parse(cls, d):
        d = d or {}
        return cls(d.get("build_commit"), d.get("adapter_version"), freeze(d.get("input_sha256")),
                   freeze(d.get("time_base")), d.get("selection_reason"), freeze(d.get("decision")), freeze(d))


_PREVIOUS = ("time_mae_min", "time_p95_min", "time_bias_min", "height_mae_m", "range_error_m", "missed_events",
             "extra_events")


@dataclass(frozen=True, slots=True)
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
        if prev is not None:
            prev = MappingProxyType({k: prev.get(k) for k in _PREVIOUS})
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
    is_recommended: bool
    convention: Convention
    licence: Licence
    provenance: Provenance
    validation: Tuple[Validation, ...]
    raw: Mapping[str, Any] = field(repr=False, compare=False)
    _constituents: Any = field(default=None, repr=False, compare=False)

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
    removed_reason: Optional[str]
    raw: Mapping[str, Any] = field(repr=False, compare=False)

    @classmethod
    def _parse(cls, d):
        return cls(d["station_id"], d.get("name"), E.enum_or_raw(E.StationStatus, d.get("status")),
                   d.get("removed_in"), d.get("removed_reason"), freeze(d))


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

    def constant_sets(self, *, include_excluded: bool = False) -> Tuple[ConstantSet, ...]:
        """The recommended set first, then the others by set_id. Excluded sets only on request."""
        if not isinstance(include_excluded, bool):
            from ._errors import InvalidArgumentError
            raise InvalidArgumentError("include_excluded must be a boolean")
        return tuple(s for s in self._sets if include_excluded or s.qc_status != E.QcStatus.EXCLUDED)

    def constant_set(self, set_id: str) -> Optional[ConstantSet]:
        for s in self._sets:
            if s.set_id == set_id:
                return s
        return None


@dataclass(frozen=True, slots=True)
class Nearby:
    station: Station
    distance_km: float


@dataclass(frozen=True, slots=True)
class Stats:
    type: Mapping[str, int]
    kind: Mapping[str, int]
    country: Mapping[str, int]
    source: Mapping[str, int]
    qc_status: Mapping[str, int]


# --------------------------------------------------------------------------- building a Station from its JSON


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
                set_id == rid, conv, lic, Provenance._parse(cs.get("provenance")),
                tuple(sorted((v for v in rows if v.set_id == set_id), key=lambda v: v.window or "")),
                freeze(cs)))
        rec = [s for s in sets if s.set_id == rid]
        if rid is not None and not rec:
            raise InvalidReleaseError(f"{sid}: recommended_set_id {rid!r} does not resolve")
        ordered = tuple(rec + sorted((s for s in sets if s.set_id != rid), key=lambda s: s.set_id))
        off = d.get("subordinate_offsets")
        if off is not None and off.get("licence_id") is not None and off.get("licence_id") not in licences:
            raise InvalidReleaseError(f"{sid}: subordinate_offsets.licence_id does not resolve")
        aliases = {}
        for system, ids in (d.get("aliases") or {}).items():
            aliases[system] = tuple(ids) if isinstance(ids, list) else (ids,)
        return Station(
            sid, d.get("name"), d.get("country"), float(d["lat"]), float(d["lon"]),
            E.enum_or_raw(E.StationType, d.get("type")), None if kind is None else E.enum_or_raw(E.Kind, kind),
            d.get("timezone"), MappingProxyType(aliases), E.enum_or_raw(E.StationStatus, d.get("status")),
            None if off is None else SubordinateOffsets._parse(off), rows, rec[0] if rec else None, freeze(d),
            ordered)
    except InvalidReleaseError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        raise InvalidReleaseError(f"station {d.get('station_id') if isinstance(d, dict) else d!r}: {e!r}") from e


def own_kind(d):
    """The station's kind from its own data: the field when the file has it, else the quantity of the
    recommended set. None when only the reference station can tell (subordinate with offsets only)."""
    k = d.get("kind")
    if k is not None:
        return k
    rid = d.get("recommended_set_id")
    for cs in d.get("constant_sets") or ():
        if cs.get("set_id") == rid:
            return {"water_level": "tide", "current": "current"}.get(cs.get("quantity"), "other")
    return None
