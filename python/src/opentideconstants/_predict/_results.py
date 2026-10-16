"""Immutable prediction values; local zone rules are loaded only by to_local."""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Mapping
from .._enums import ExtremeType, CurrentEventType, PredictionMethod
from .._errors import UnknownTimeZoneError, LocalTimeUnavailableError


class _LocalItem:
    __slots__ = ()
    _local: datetime | None

    def local_datetime(self):
        return self._local


class _LocalResult:
    __slots__ = ()

    def to_local(self, tz='station'):
        from ._local import localize
        return localize(self, tz)


@dataclass(frozen=True, slots=True)
class HeightPoint(_LocalItem):
    time: datetime
    height_m: float
    local_time: str | None = field(default=None, kw_only=True)
    utc_offset_s: int | None = field(default=None, kw_only=True)
    _local: datetime | None = field(default=None, repr=False, compare=False, kw_only=True)

@dataclass(frozen=True, slots=True)
class Extreme(_LocalItem):
    time: datetime
    type: ExtremeType
    height_m: float
    local_time: str | None = field(default=None, kw_only=True)
    utc_offset_s: int | None = field(default=None, kw_only=True)
    _local: datetime | None = field(default=None, repr=False, compare=False, kw_only=True)

@dataclass(frozen=True, slots=True)
class CurrentPoint(_LocalItem):
    time: datetime
    velocity_major_ms: float
    velocity_minor_ms: float
    speed_ms: float
    direction_deg: float | None
    local_time: str | None = field(default=None, kw_only=True)
    utc_offset_s: int | None = field(default=None, kw_only=True)
    _local: datetime | None = field(default=None, repr=False, compare=False, kw_only=True)

@dataclass(frozen=True, slots=True)
class CurrentEvent(_LocalItem):
    time: datetime
    type: CurrentEventType
    velocity_ms: float
    direction_deg: float | None
    local_time: str | None = field(default=None, kw_only=True)
    utc_offset_s: int | None = field(default=None, kw_only=True)
    _local: datetime | None = field(default=None, repr=False, compare=False, kw_only=True)


@dataclass(frozen=True, slots=True)
class HeightSeries(_LocalResult):
    items: tuple[HeightPoint, ...]
    station_id: str | None = None
    timezone: str | None = None
    method: PredictionMethod | None = None
    set_id: str | None = None
    convention_id: str | None = None
    astro_table_id: str | None = None
    reference_station_id: str | None = None
    reference_bin: int | None = None
    datum: str | None = None
    datum_name: str | None = None
    datum_kind: str | None = None
    datum_uncertainty_m: float | None = None
    tz: str | None = None
    tz_version: str | None = None
    release: str | None = None
    algorithm: str | None = None
    offset_id: str | None = None
    offset_source: str | None = None
    offset_source_version: str | None = None
    historical_offsets: bool = False
    current_validity: str | None = None
    current_accuracy: str | None = None
    reference_set_id: str | None = None
    reference_source_version: str | None = None
    reference_2020_equivalence: str | None = None
    source_note: str | None = None


@dataclass(frozen=True, slots=True)
class ExtremeList(_LocalResult):
    items: tuple[Extreme, ...]
    station_id: str | None = None
    timezone: str | None = None
    method: PredictionMethod | None = None
    set_id: str | None = None
    convention_id: str | None = None
    astro_table_id: str | None = None
    reference_station_id: str | None = None
    reference_bin: int | None = None
    datum: str | None = None
    datum_name: str | None = None
    datum_kind: str | None = None
    datum_uncertainty_m: float | None = None
    tz: str | None = None
    tz_version: str | None = None
    release: str | None = None
    algorithm: str | None = None
    offset_id: str | None = None
    offset_source: str | None = None
    offset_source_version: str | None = None
    historical_offsets: bool = False
    current_validity: str | None = None
    current_accuracy: str | None = None
    reference_set_id: str | None = None
    reference_source_version: str | None = None
    reference_2020_equivalence: str | None = None
    source_note: str | None = None


@dataclass(frozen=True, slots=True)
class CurrentSeries(_LocalResult):
    items: tuple[CurrentPoint, ...]
    station_id: str | None = None
    timezone: str | None = None
    method: PredictionMethod | None = None
    set_id: str | None = None
    convention_id: str | None = None
    astro_table_id: str | None = None
    reference_station_id: str | None = None
    reference_bin: int | None = None
    datum: str | None = None
    datum_name: str | None = None
    datum_kind: str | None = None
    datum_uncertainty_m: float | None = None
    bin_number: int | None = None
    tz: str | None = None
    tz_version: str | None = None
    release: str | None = None
    algorithm: str | None = None


@dataclass(frozen=True, slots=True)
class CurrentEventList(_LocalResult):
    items: tuple[CurrentEvent, ...]
    station_id: str | None = None
    timezone: str | None = None
    method: PredictionMethod | None = None
    set_id: str | None = None
    convention_id: str | None = None
    astro_table_id: str | None = None
    reference_station_id: str | None = None
    reference_bin: int | None = None
    datum: str | None = None
    datum_name: str | None = None
    datum_kind: str | None = None
    datum_uncertainty_m: float | None = None
    bin_number: int | None = None
    omitted_event_types: tuple[CurrentEventType, ...] | None = None
    tz: str | None = None
    tz_version: str | None = None
    release: str | None = None
    algorithm: str | None = None


@dataclass(frozen=True, slots=True)
class DatumLevel:
    key: str | None
    value_m: float
    above_chart_m: float | None
    kind: str | None
    method: str | None
    source_name: str | None
    epoch: Any
    data_span: Any
    control_station_id: str | None
    control_set_id: str | None
    control_source_id: str | None
    uncertainty_m: float | None
    uncertainty_basis: str | None
    flags: tuple[str, ...]
    fallback: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class DatumInfo:
    set_id: str | None
    zero: str | None
    zero_name: str | None
    chart_datum: str | None
    msl_offset_m: float | None
    levels: tuple[DatumLevel, ...]


@dataclass(frozen=True, slots=True)
class Ranges:
    mn: float | None
    gt: float | None
    dhq: float | None
    dlq: float | None
