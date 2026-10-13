"""The immutable data objects (spec §3, §4.4 to §4.7). Frozen dataclasses with __slots__."""
from __future__ import annotations

import datetime as _dt
import json
import math
import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, NoReturn, Optional, Tuple

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
        # datetime refuses impossible calendar fields, hour 24 and a leap second :60 (CR2 DR6: malformed, never
        # rolled over); astimezone raises OverflowError when the offset moves the time out of years 1 to 9999
        return _dt.datetime(int(y), int(mo), int(d), int(h), int(mi), int(sec), us, tzinfo=tz).astimezone(_dt.timezone.utc)
    except (ValueError, OverflowError) as e:
        raise InvalidReleaseError(f"{what}: not an ISO 8601 time: {v!r}") from e


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
    commercial_use: bool
    restriction: Optional[str]
    terms_url: Optional[str]
    raw: Mapping[str, Any] = field(repr=False, compare=False)

    def __hash__(self):  # CR D16: hashable by id; == still compares the fields
        return hash(self.licence_id)

    @classmethod
    def _parse(cls, d):
        check_licence(d)
        return cls(d["licence_id"], d.get("spdx"), d.get("provider"), d.get("citation"), d.get("attribution"),
                   d.get("url"), d["commercial_use"], d.get("restriction"), d.get("terms_url"), freeze(d))


def check_licence(d):
    """The load rules of the licence fields (spec §4.6, K-NC DR104): commercial_use is a JSON boolean (absent or
    null is invalid); restriction and terms_url, when present, are strings (a JSON null is not one, CR3 DR71); a
    non-commercial licence has both, and an spdx, which the non-commercial notice prints."""
    lid = d.get("licence_id") if isinstance(d, dict) else None
    if not isinstance(d, dict) or not isinstance(d.get("commercial_use"), bool):
        raise InvalidReleaseError(f"licence {lid!r}: commercial_use must be true or false")
    for k in ("restriction", "terms_url"):
        if k in d and not isinstance(d[k], str):
            raise InvalidReleaseError(f"licence {lid!r}: {k} must be a string")
    if d["commercial_use"] is False:
        for k in ("restriction", "terms_url", "spdx"):
            if not isinstance(d.get(k), str):
                raise InvalidReleaseError(f"licence {lid!r}: a licence with commercial_use false needs {k}")


@dataclass(frozen=True, slots=True, eq=False)  # holds frozen mappings: identity equality and hash
class SourceRecord:
    """Original source material and its terms, separate from predictive constituents."""
    source: str
    source_version: str
    source_record_id: str
    role: E.SourceRole
    disposition: E.SourceDisposition
    detail: str
    licence_id: Optional[str]
    upstream_licence_id: Optional[str]
    published_set_ids: Tuple[str, ...]
    provenance: Mapping[str, Any]
    original_metadata: Mapping[str, Any]
    original_harmonics: Optional[Mapping[str, Any]]
    licence: Optional[Licence]
    upstream_licence: Optional[Licence]
    raw: Mapping[str, Any] = field(repr=False, compare=False)

    @classmethod
    def _parse(cls, d, licences):
        references = []
        for key in ('licence_id', 'upstream_licence_id'):
            identifier = d.get(key)
            licence = None if identifier is None else licences.get(identifier)
            if identifier is not None and licence is None:
                raise InvalidReleaseError(f"source record {d['source_record_id']}: {key} {identifier!r} does not resolve")
            references.append(licence)
        provenance = freeze(d['provenance'])
        metadata = freeze(d.get('original_metadata', {}))
        harmonics = freeze(d.get('original_harmonics'))
        raw = freeze(d)
        assert isinstance(provenance, Mapping) and isinstance(metadata, Mapping)
        assert harmonics is None or isinstance(harmonics, Mapping)
        assert isinstance(raw, Mapping)
        return cls(d['source'], d['source_version'], d['source_record_id'], E.SourceRole(d['role']),
                   E.SourceDisposition(d['disposition']), d['detail'], d['licence_id'], d.get('upstream_licence_id'),
                   tuple(d['published_set_ids']), provenance, metadata, harmonics, references[0], references[1], raw)


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


@dataclass(frozen=True, slots=True, eq=False)  # holds a mapping: identity equality and hash
class Fallback:
    """Retained source values with an OTC finding, not an earlier-release carry-over."""
    reason: E.FallbackReason
    basis: str
    otc_finding: str
    preferred_set_id: Optional[str]
    raw: Mapping[str, Any] = field(repr=False, compare=False)

    @classmethod
    def _parse(cls, d):
        if d is None:
            return None
        return cls(E.enum_or_raw(E.FallbackReason, d.get("reason")), d.get("basis"), d.get("otc_finding"),
                   d.get("preferred_set_id"), freeze(d))


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
            prev = MappingProxyType({k: (prev.get(k) if _is_finite(prev.get(k)) else None) for k in _PREVIOUS})
        else:
            prev = None
        return cls(d.get("set_id"), d.get("reference_source"), d.get("reference_station"),
                   d.get("reference_distance_km"), d.get("window"), d.get("time_mae_min"), d.get("time_p95_min"),
                   d.get("time_bias_min"), d.get("height_mae_m"), d.get("range_error_m"), d.get("missed_events"),
                   d.get("extra_events"), prev)


@dataclass(frozen=True, slots=True)
class HistoricalOffsetVintage:
    publication_year: int
    source_lifecycle: str
    removal_events: Tuple[Mapping[str, Any], ...]
    current_validity: str
    current_accuracy: str
    reference_2020_equivalence: str
    reference_2020_equivalence_sha256: Optional[str]

    @classmethod
    def _parse(cls, d):
        return cls(int(d['publication_year']), d['source_lifecycle'],
                   tuple(MappingProxyType({k: freeze(v) for k, v in row.items()}) for row in d['removal_events']),
                   d['current_validity'], d['current_accuracy'], d['reference_2020_equivalence'],
                   d.get('reference_2020_equivalence_sha256'))


@dataclass(frozen=True, slots=True)
class HistoricalOffsetProvenance:
    source_manifest_sha256: str
    input_sha256: Tuple[str, ...]
    book: str
    annual_table_row: int
    printed_page: int
    pdf_page: int
    raw_row_text: str
    raw_values_json: str
    id_crosswalk: Mapping[str, Any]
    reference_binding: Mapping[str, Any]
    acceptance_report_sha256: str

    @classmethod
    def _parse(cls, d):
        return cls(d['source_manifest_sha256'], tuple(d['input_sha256']), d['book'], int(d['annual_table_row']),
                   int(d['printed_page']), int(d['pdf_page']), d['raw_row_text'], d['raw_values_json'],
                   MappingProxyType({k: freeze(v) for k, v in d['id_crosswalk'].items()}),
                   MappingProxyType({k: freeze(v) for k, v in d['reference_binding'].items()}),
                   d['acceptance_report_sha256'])


_HISTORICAL_PROFILES = {
    'noaa-2020-atlantic-table2-2513': ('atlantic', 2513, 345, 351, 'TEC2869', '8661070', 'OTC-a6c00a3f',
                                    'R', 4, 15, 0.84, 1.0,
                                    (("2026-02-18T14:09:46", "Lockwoods Folly Inlet (r)"),),
                                    "  2513     Lockwoods Folly Inlet . . . . . . . . . . . . . . . . . . . . . . .         33° 55'     78° 14'     +0 04      +0 15     *0.84     *1.00    4.2    4.8     2.3"),
    'noaa-2020-pacific-table2-517': ('pacific', 517, 284, 302, 'TWC0509', '9414290', 'OTC-ee4593cd',
                                  'A', -35, -31, -0.06096, 0.0,
                                  (("2026-02-18T14:09:50", "San Francisco Bar (r)"),
                                   ("2026-07-06T11:17:37", "San Francisco Bar")),
                                  "   517     San Francisco Bar . . . . . . . . . . . . . . . . . . . . . . . . .         37° 46'     122° 38'     -0 35       -0 31      -0.2        0.0    3.9    5.6     3.0"),
}
_HISTORICAL_MANIFEST = '667eec5b3fd25f99d46f24864766726094961d7db5fa104ca12450f3ecd0fdf7'
_HISTORICAL_REMOVAL_SHA = 'c100d0fbc5482ec24f5c99d912be73306bd2dea079690f08edc5f58a821bcd61'
_SHA256 = re.compile(r'\A[a-f0-9]{64}\Z')


def _check_historical_offsets(d, what='subordinate_offsets'):
    """Validate the two named own-offset contracts; ordinary offsets retain their existing behavior."""
    if d is None:
        return
    if not isinstance(d, dict):
        raise InvalidReleaseError(f'{what}: not an object')
    _check_types(d, _OFFSET_TYPES, what)
    fallback = d.get('fallback')
    flags = d.get('qc_flags')
    historical = ('offset_id' in d or isinstance(fallback, dict) and fallback.get('reason') == 'historical_offsets'
                  or isinstance(flags, list) and any(isinstance(f, dict) and f.get('flag') == 'fallback:historical_offsets'
                                                    for f in flags))
    if not historical:
        return

    def fail(field) -> NoReturn:
        raise InvalidReleaseError(f'{what}: invalid or missing historical {field}')

    def text(value):
        return isinstance(value, str) and bool(value.strip())

    def digest(value):
        return isinstance(value, str) and _SHA256.fullmatch(value) is not None

    def hashes(value):
        return isinstance(value, list) and bool(value) and all(digest(v) for v in value) and len(set(value)) == len(value)

    profile_id = d.get('offset_id')
    profile = _HISTORICAL_PROFILES.get(profile_id) if isinstance(profile_id, str) else None
    if profile is None:
        fail('offset_id')
    book, row, page, pdf_page, legacy, noaa_id, reference, adjusted, high_t, low_t, high_h, low_h, removals, raw_row = profile
    expected = {'source': 'noaa', 'source_type': 'official', 'source_version': 'annual-tide-tables-2020',
                'source_record_id': f'annual-tide-tables-2020/{book}/Table2/{row}', 'qc_status': 'flagged',
                'reference_station_id': reference, 'height_adjusted_type': adjusted,
                'time_offset_high_min': high_t, 'time_offset_low_min': low_t,
                'height_offset_high': high_h, 'height_offset_low': low_h}
    for key, value in expected.items():
        if d.get(key) != value or isinstance(value, (int, float)) and not _is_finite(d.get(key)):
            fail(key)
    if not text(d.get('licence_id')):
        fail('licence_id')
    if not isinstance(flags, list) or len(flags) != 1 or not isinstance(flags[0], dict) \
            or flags[0].get('flag') != 'fallback:historical_offsets' or not text(flags[0].get('reason')):
        fail('qc_flags')
    if not isinstance(fallback, dict) or fallback.get('reason') != 'historical_offsets' \
            or not all(text(fallback.get(k)) for k in ('basis', 'otc_finding')) or 'preferred_set_id' in fallback:
        fail('fallback')
    datum = d.get('datum')
    required_datum = {'zero': 'chart_datum', 'chart_datum': 'mllw', 'named': {'mllw': 0.0},
                      'basis': {'mllw': {'kind': 'published', 'method': 'source', 'source_name': 'MLLW'}}}
    if not isinstance(datum, dict) or datum != required_datum or not _is_finite(datum['named']['mllw']):
        fail('datum')
    vintage = d.get('vintage')
    if not isinstance(vintage, dict):
        fail('vintage')
    for key, value in {'publication_year': 2020, 'source_lifecycle': 'retired',
                       'current_validity': 'unestablished', 'current_accuracy': 'unverified'}.items():
        if vintage.get(key) != value or key == 'publication_year' and not _is_finite(vintage.get(key)):
            fail(f'vintage.{key}')
    expected_removals = [{'source_clock_timestamp': timestamp, 'name': name, 'operation': 'Removed',
                         'source_timezone': None, 'evidence_sha256': _HISTORICAL_REMOVAL_SHA}
                        for timestamp, name in removals]
    if vintage.get('removal_events') != expected_removals:
        fail('vintage.removal_events')
    equivalence = vintage.get('reference_2020_equivalence')
    if equivalence not in ('not_checked', 'matched_at_publisher_precision', 'disagrees'):
        fail('vintage.reference_2020_equivalence')
    if (equivalence == 'not_checked' and 'reference_2020_equivalence_sha256' in vintage
            or equivalence != 'not_checked' and not digest(vintage.get('reference_2020_equivalence_sha256'))):
        fail('vintage.reference_2020_equivalence_sha256')
    provenance = d.get('provenance')
    if not isinstance(provenance, dict):
        fail('provenance')
    for key, value in {'source_manifest_sha256': _HISTORICAL_MANIFEST, 'book': book, 'annual_table_row': row,
                       'printed_page': page, 'pdf_page': pdf_page, 'raw_row_text': raw_row}.items():
        if provenance.get(key) != value or isinstance(value, int) and not _is_finite(provenance.get(key)):
            fail(f'provenance.{key}')
    if not hashes(provenance.get('input_sha256')) or not digest(provenance.get('acceptance_report_sha256')):
        fail('provenance evidence hashes')
    for key, values in (('id_crosswalk', {'legacy_id': legacy, 'status': 'inferred', 'modern_alias_verified': False}),
                        ('reference_binding', {'noaa_id': noaa_id, 'station_id': reference,
                                               'mapping_status': 'primary_name_position'})):
        nested = provenance.get(key)
        if not isinstance(nested, dict) or not hashes(nested.get('evidence_sha256')) \
                or any(nested.get(k) != v for k, v in values.items()) \
                or key == 'id_crosswalk' and nested.get('modern_alias_verified') is not False:
            fail(f'provenance.{key}')
    raw_values = provenance.get('raw_values_json')
    try:
        if not isinstance(raw_values, str) or not raw_values.strip() or not isinstance(json.loads(raw_values), dict):
            fail('provenance.raw_values_json')
    except (ValueError, TypeError):
        fail('provenance.raw_values_json')


@dataclass(frozen=True, slots=True)
class SubordinateOffsets:
    reference_station_id: str
    time_offset_high_min: Optional[float]
    time_offset_low_min: Optional[float]
    height_offset_high: Optional[float]
    height_offset_low: Optional[float]
    height_adjusted_type: Optional[E.HeightAdjustedType]
    licence_id: Optional[str]
    offset_id: Optional[str] = None
    source: Optional[str] = None
    source_type: Optional[E.SourceType] = None
    source_version: Optional[str] = None
    source_record_id: Optional[str] = None
    qc_status: Optional[E.QcStatus] = None
    qc_flags: Tuple[QcFlag, ...] = ()
    fallback: Optional[Fallback] = None
    vintage: Optional[HistoricalOffsetVintage] = None
    provenance: Optional[HistoricalOffsetProvenance] = None

    @classmethod
    def _parse(cls, d):
        _check_historical_offsets(d)
        return cls(d.get("reference_station_id"), d.get("time_offset_high_min"), d.get("time_offset_low_min"),
                   d.get("height_offset_high"), d.get("height_offset_low"),
                   E.enum_or_raw(E.HeightAdjustedType, d.get("height_adjusted_type")), d.get("licence_id"),
                   d.get('offset_id'), d.get('source'), E.enum_or_raw(E.SourceType, d.get('source_type')),
                   d.get('source_version'), d.get('source_record_id'), E.enum_or_raw(E.QcStatus, d.get('qc_status')),
                   tuple(QcFlag._parse(flag) for flag in d.get('qc_flags') or ()), Fallback._parse(d.get('fallback')),
                   None if d.get('vintage') is None else HistoricalOffsetVintage._parse(d['vintage']),
                   None if d.get('provenance') is None else HistoricalOffsetProvenance._parse(d['provenance']))


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
    fallback: Optional[Fallback] = None

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
    recommended_is_fallback: Optional[bool] = None
    source_records: Tuple[SourceRecord, ...] = ()
    _origin: Optional[object] = field(default=None, init=False, repr=False, compare=False)

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


def _is_finite(v) -> bool:
    """A JSON number whose double value is finite. An integer too large for a double (400 digits) is not."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return False
    try:
        return math.isfinite(float(v))
    except OverflowError:
        return False


# The JSON type of each known field that the SDK reads (spec 7.3: tolerant is not lax; CR2 PK-R2-05). Absent or
# null is always allowed here; required fields are checked where they are used. T a string, N a finite number,
# I a finite number with an integral value, O an object, L a list of objects, S a list of strings, A a list,
# B a boolean.
# The same table is in the Ruby, TypeScript and C SDKs.
_STATION_TYPES = {"name": "T", "country": "T", "timezone": "T", "type": "T", "recommended_set_id": "T", "status": "T",
                  "constant_sets": "L", "validation": "L", "subordinate_offsets": "O", "current_offsets": "A",
                  "recommended_is_fallback": "B", "source_records": "L"}
_OFFSET_TYPES = {"reference_station_id": "T", "licence_id": "T", "height_adjusted_type": "T",
                 "time_offset_high_min": "N", "time_offset_low_min": "N", "height_offset_high": "N", "height_offset_low": "N",
                 "offset_id": "T", "source": "T", "source_type": "T", "source_version": "T", "source_record_id": "T",
                 "qc_status": "T", "qc_flags": "L", "fallback": "O", "vintage": "O", "provenance": "O"}
_VALIDATION_TYPES = {"set_id": "T", "reference_source": "T", "reference_station": "T", "window": "T",
                     "reference_distance_km": "N", "time_mae_min": "N", "time_p95_min": "N", "time_bias_min": "N",
                     "height_mae_m": "N", "range_error_m": "N", "missed_events": "I", "extra_events": "I",
                     "previous_release": "O"}
_SET_TYPES = {"set_id": "T", "source": "T", "source_type": "T", "quantity": "T", "source_record_id": "T",
              "source_version": "T", "convention_id": "T", "licence_id": "T", "qc_status": "T", "constituents": "L",
              "dropped_constituents": "L", "qc_flags": "L", "record_span": "O", "datum": "O", "time_base": "O",
              "provenance": "O", "current_bins": "A", "fallback": "O"}
_FALLBACK_TYPES = {"reason": "T", "basis": "T", "otc_finding": "T", "preferred_set_id": "T"}
_SPAN_TYPES = {"good_samples": "I"}
_DATUM_TYPES = {"msl_offset_m": "N", "named": "O"}
_CONSTITUENT_TYPES = {"name": "T", "source_name": "T", "doodson": "T", "kept_reason": "T", "speed_deg_per_hour": "N",
                      "amplitude_m": "N", "phase_deg": "N", "amp_uncertainty_m": "N", "phase_uncertainty_deg": "N"}
_QC_FLAG_TYPES = {"flag": "T", "reason": "T", "values": "O"}
_DROPPED_TYPES = {"name": "T", "dropped_reason": "T", "detail": "T"}
_TIME_BASE_TYPES = {"code": "T", "reason": "T", "declared": "T", "published": "T", "decided_in": "T",
                    "decided_build_commit": "T", "correction": "O", "months_dropped": "S", "evidence": "L"}
_CORRECTION_TYPES = {"from": "T", "to": "T"}
_EVIDENCE_TYPES = {"comparator_kind": "T", "comparator_id": "T", "detail": "T", "distance_km": "N", "lag_min": "N"}
_PROVENANCE_TYPES = {"adapter_version": "T", "carried_from_release": "T", "selection_reason": "T",
                     "input_sha256": "S", "decision": "O"}
_SOURCE_RECORD_TYPES = {"source": "T", "source_version": "T", "source_record_id": "T", "role": "T",
                        "disposition": "T", "detail": "T", "licence_id": "T", "upstream_licence_id": "T",
                        "published_set_ids": "S", "provenance": "O", "original_metadata": "O", "original_harmonics": "O"}
_SOURCE_PROVENANCE_TYPES = {"input_sha256": "S", "inventory_sha256": "T"}
_ORIGINAL_HARMONIC_TYPES = {"format": "T", "columns": "S", "rows": "A", "annotations": "L",
                           "amplitude_unit": "T", "amplitude_unit_basis": "T", "phase_unit": "T",
                           "phase_convention": "T", "amplitude_uncertainty_unit": "T",
                           "amplitude_uncertainty_unit_basis": "T"}


def _type_ok(v, t) -> bool:
    if v is None:
        return True
    if t == "T":
        return isinstance(v, str)
    if t == "B":
        return isinstance(v, bool)
    if t == "N":
        return _is_finite(v)
    if t == "I":
        return _is_finite(v) and float(v) == int(v)
    if t == "O":
        return isinstance(v, dict)
    if t == "L":
        return isinstance(v, list) and all(isinstance(x, dict) for x in v)
    if t == "S":
        return isinstance(v, list) and all(isinstance(x, str) for x in v)
    return isinstance(v, list)  # "A"


def _check_types(d, table, what):
    for k, t in table.items():
        if not _type_ok(d.get(k), t):
            raise InvalidReleaseError(f"{what}: {k} has the wrong type: {d.get(k)!r:.80}")


def check_station_types(d) -> None:
    """Every known field of an active station line has its JSON type (spec 7.3, §6.1), so a malformed line fails
    the load with invalid_release in eager and stream mode, never a value read as null or a raw error later."""
    sid = d.get("station_id")
    _check_types(d, _STATION_TYPES, f"station {sid}")
    if 'source_records' in d and (not isinstance(d['source_records'], list) or not d['source_records']):
        raise InvalidReleaseError(f"station {sid}: source_records must be a nonempty array")
    for source in d.get('source_records') or ():
        what = f"station {sid}: source record {source.get('source_record_id')}"
        _check_types(source, _SOURCE_RECORD_TYPES, what)
        for key in ('source', 'source_version', 'source_record_id', 'role', 'disposition', 'detail'):
            if not isinstance(source.get(key), str) or not source[key]:
                raise InvalidReleaseError(f"{what}: {key} must be a nonempty string")
        if 'licence_id' not in source or not isinstance(source.get('published_set_ids'), list):
            raise InvalidReleaseError(f"{what}: licence_id and published_set_ids are required")
        if not isinstance(source.get('provenance'), dict):
            raise InvalidReleaseError(f"{what}: provenance must be an object")
        _check_types(source['provenance'], _SOURCE_PROVENANCE_TYPES, f"{what}: provenance")
        if not isinstance(source['provenance'].get('input_sha256'), list) or not isinstance(
                source['provenance'].get('inventory_sha256'), str):
            raise InvalidReleaseError(f"{what}: provenance requires input_sha256 and inventory_sha256")
        if 'original_metadata' in source and not isinstance(source['original_metadata'], dict):
            raise InvalidReleaseError(f"{what}: original_metadata must be an object")
        harmonics = source.get('original_harmonics')
        if harmonics is not None:
            _check_types(harmonics, _ORIGINAL_HARMONIC_TYPES, f"{what}: original_harmonics")
            if 'rows' in harmonics and (not isinstance(harmonics['rows'], list) or not all(
                    isinstance(row, list) and all(isinstance(cell, str) for cell in row) for row in harmonics['rows'])):
                raise InvalidReleaseError(f"{what}: original_harmonics.rows must contain arrays of strings")
            for annotation in harmonics.get('annotations') or ():
                _check_types(annotation, {'row': 'I', 'reason': 'T', 'detail': 'T'}, f"{what}: annotation")
    if d.get("subordinate_offsets") is not None:
        _check_types(d["subordinate_offsets"], _OFFSET_TYPES, f"station {sid}: subordinate_offsets")
    for v in d.get("validation") or ():
        _check_types(v, _VALIDATION_TYPES, f"station {sid}: validation")
    for cs in d.get("constant_sets") or ():
        what = f"station {sid}: set {cs.get('set_id')}"
        _check_types(cs, _SET_TYPES, what)
        if isinstance(cs.get('fallback'), dict) and cs['fallback'].get('reason') == 'historical_offsets' or any(
                flag.get('flag') == 'fallback:historical_offsets' for flag in cs.get('qc_flags') or ()):
            raise InvalidReleaseError(f'{what}: historical_offsets belongs only to subordinate_offsets')
        for k, table in (("record_span", _SPAN_TYPES), ("datum", _DATUM_TYPES), ("time_base", _TIME_BASE_TYPES),
                         ("provenance", _PROVENANCE_TYPES), ("fallback", _FALLBACK_TYPES)):
            if cs.get(k) is not None:
                _check_types(cs[k], table, f"{what}: {k}")
        named = (cs.get("datum") or {}).get("named") or {}
        if not all(_is_finite(x) for x in named.values()):
            raise InvalidReleaseError(f"{what}: datum.named has a value that is not a number")
        for k, table in (("constituents", _CONSTITUENT_TYPES), ("qc_flags", _QC_FLAG_TYPES),
                         ("dropped_constituents", _DROPPED_TYPES)):
            for x in cs.get(k) or ():
                _check_types(x, table, f"{what}: {k}")
        for f in cs.get("qc_flags") or ():
            if not all(x is None or _is_finite(x) for x in (f.get("values") or {}).values()):
                raise InvalidReleaseError(f"{what}: a qc_flags value is not a number or null")
        tb = cs.get("time_base") or {}
        if tb.get("correction") is not None:
            _check_types(tb["correction"], _CORRECTION_TYPES, f"{what}: time_base.correction")
        for e in tb.get("evidence") or ():
            _check_types(e, _EVIDENCE_TYPES, f"{what}: time_base.evidence")


_RELEASE_REC = object()  # build_station: the station's recommended set is the release's


def _build_record_span(span):
    return None if span is None else RecordSpan(parse_time(span.get("start"), "record_span.start"),
        parse_time(span.get("end"), "record_span.end"),
        span.get("good_samples"))


def _build_datum(datum):
    return None if datum is None else Datum(datum.get("msl_offset_m"), freeze(dict(datum.get("named") or {})))


def _build_constant_set(cs, rows, rid, conv, lic):
    span = cs.get("record_span")
    datum = cs.get("datum")
    set_id = cs["set_id"]
    return ConstantSet(
        set_id, cs.get("source"), E.enum_or_raw(E.SourceType, cs.get("source_type")),
        E.enum_or_raw(E.Quantity, cs.get("quantity")), cs.get("source_record_id"), cs.get("source_version"),
        _build_record_span(span), _build_datum(datum),
        E.enum_or_raw(E.QcStatus, cs.get("qc_status")),
        tuple(QcFlag._parse(f) for f in cs.get("qc_flags") or ()),
        tuple(DroppedConstituent._parse(x) for x in cs.get("dropped_constituents") or ()),
        TimeBase._parse(cs.get("time_base")), rid is not None and set_id == rid, conv, lic, Provenance._parse(cs.get("provenance")),
        tuple(sorted((v for v in rows if v.set_id == set_id), key=lambda v: v.window or "")),
        freeze(cs), fallback=Fallback._parse(cs.get("fallback")))


def build_station(d, conventions, licences, kind, recommended=_RELEASE_REC):
    """Build a Station from the parsed JSON of a station line (the caller passes active lines only; the status
    is not checked here). conventions/licences: id -> object. recommended: the set_id (or None) that the Station
    gives as its recommended set, when it is not the release's (the effective recommended set of commercial_only,
    spec §4.2, K-NC DR106). Raises InvalidReleaseError when a reference does not resolve or a field is
    malformed."""
    try:
        check_station_types(d)
        sid = d["station_id"]
        release_rid = d.get("recommended_set_id")
        rid = release_rid if recommended is _RELEASE_REC else recommended
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
            names = [c["name"] for c in cs.get("constituents") or ()]
            if len(set(names)) != len(names):   # spec 6.1 (CR2 DR22)
                raise InvalidReleaseError(f"{cs.get('set_id')}: a constituent name appears twice")
            sets.append(_build_constant_set(cs, rows, rid, conv, lic))
        if release_rid is not None and not any(s.set_id == release_rid for s in sets):
            raise InvalidReleaseError(f"{sid}: recommended_set_id {release_rid!r} does not resolve")
        rec = [s for s in sets if rid is not None and s.set_id == rid]
        ordered = tuple(rec + sorted((s for s in sets if s.set_id != rid), key=lambda s: s.set_id))
        off = d.get("subordinate_offsets")
        if off is not None and off.get("licence_id") is not None and off.get("licence_id") not in licences:
            raise InvalidReleaseError(f"{sid}: subordinate_offsets.licence_id does not resolve")
        aliases = {}
        for system, ids in (d.get("aliases") or {}).items():
            aliases[system] = tuple(ids) if isinstance(ids, list) else (ids,)
        lat, lon = d.get("lat"), d.get("lon")
        if not (_is_finite(lat) and -90 <= lat <= 90 and _is_finite(lon) and -180 <= lon <= 180):
            raise InvalidReleaseError(f"{sid}: lat/lon must be numbers in range, not {lat!r}, {lon!r}")
        return Station(
            sid, d.get("name"), d.get("country"), float(lat), float(lon),
            E.enum_or_raw(E.StationType, d.get("type")), None if kind is None else E.enum_or_raw(E.Kind, kind),
            d.get("timezone"), MappingProxyType(aliases), E.enum_or_raw(E.StationStatus, "active" if d.get("status") is None else d.get("status")),
            None if off is None else SubordinateOffsets._parse(off), rows, rec[0] if rec else None, freeze(d),
            ordered, recommended_is_fallback=d.get("recommended_is_fallback"),
            source_records=tuple(SourceRecord._parse(source, licences) for source in d.get('source_records') or ()))
    except InvalidReleaseError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        raise InvalidReleaseError(f"station {d.get('station_id') if isinstance(d, dict) else d!r}: {e!r}") from e
