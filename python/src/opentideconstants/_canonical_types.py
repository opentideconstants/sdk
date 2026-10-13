"""Closed private construction and prepared receiver types."""

from __future__ import annotations
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
import logging
import _thread
import weakref
from collections import OrderedDict
from typing import BinaryIO
from ._cache import Cache
from ._http import Http
from pathlib import Path
from typing import Literal, TypeAlias, TypedDict, Protocol, runtime_checkable
from . import _enums as E
from ._errors import OpenTideConstantsError
from ._client import OpenTideConstants
from ._release import Release
from ._models import (
    ReleaseInfo,
    FileInfo,
    Station,
    Tombstone,
    ConstantSet,
    Constituent,
    Convention,
    Licence,
    Provenance,
    ProvenanceBuild,
    TimeBase,
    QcFlag,
    DroppedConstituent,
    Validation,
    SubordinateOffsets,
    Nearby,
    UpdateResult,
    RecordSpan,
    Datum,
    Stats,
    Fallback,
    SourceRecord,
    HistoricalOffsetVintage,
    HistoricalOffsetProvenance,
)
from ._predict._astro import AstroTable
from ._predict._harmonic import Sum
from ._predict._engine import _Context
from ._predict._results import (
    HeightPoint,
    Extreme,
    CurrentPoint,
    CurrentEvent,
    HeightSeries,
    ExtremeList,
    CurrentSeries,
    CurrentEventList,
    DatumInfo,
    DatumLevel,
    Ranges,
)

_JsonValue: TypeAlias = (
    None
    | bool
    | int
    | float
    | str
    | Sequence["_JsonValue"]
    | Mapping[str, "_JsonValue"]
)


@dataclass(frozen=True, slots=True)
class _Omitted:
    pass


_OMITTED = _Omitted()


@dataclass(frozen=True, slots=True, eq=False)
class _OpaqueOrigin:
    """Private identity token; no release data retained."""


@dataclass(frozen=True, slots=True)
class _Absent:
    pass


_AuxiliaryMemberId: TypeAlias = Literal[
    "Client.open",
    "Client.release",
    "Client.loaded_from",
    "Client.last_error",
    "Client.releases",
    "Client.latest",
    "Client.check_for_update",
    "Client.newer_format_major",
    "Client.update",
    "Client.download",
    "Client.verify",
    "Client.cached_releases",
    "Client.prune",
    "Release.datestamp",
    "Release.created",
    "Release.format_version",
    "Release.zenodo_version_doi",
    "Release.concept_doi",
    "Release.source_versions",
    "Release.build_commit",
    "Release.changelog_url",
    "Release.files",
    "Release.conventions",
    "Release.convention",
    "Release.licences",
    "Release.licence",
    "Release.constituent_names",
    "Release.stats",
    "Release.station_count",
    "Release.tombstone_count",
    "Release.citation",
    "Release.station",
    "Release.require_station",
    "Release.tombstone",
    "Release.station_by_alias",
    "Release.stations",
    "Release.iter_stations",
    "Release.search",
    "Release.near",
    "Release.nearest",
    "Release.reference_station",
    "Release.subordinates_of",
    "Release.attribution",
    "Release.heights",
    "Release.heights_at",
    "Release.extremes",
    "Release.currents",
    "Release.current_events",
    "Release.datums",
    "Release.ranges",
    "Release.astro_table",
    "Release.historical_offsets_policy",
    "ReleaseInfo.datestamp",
    "ReleaseInfo.format_version",
    "ReleaseInfo.concept_doi",
    "ReleaseInfo.zenodo_version_doi",
    "ReleaseInfo.content_sha256",
    "ReleaseInfo.files",
    "FileInfo.name",
    "FileInfo.url",
    "FileInfo.size",
    "FileInfo.sha256",
    "Station.station_id",
    "Station.name",
    "Station.country",
    "Station.lat",
    "Station.lon",
    "Station.type",
    "Station.kind",
    "Station.timezone",
    "Station.aliases",
    "Station.status",
    "Station.is_reference",
    "Station.is_subordinate",
    "Station.is_tide",
    "Station.is_current",
    "Station.recommended_set",
    "Station.constant_sets",
    "Station.constant_set",
    "Station.subordinate_offsets",
    "Station.validation",
    "Station.raw",
    "Station.recommended_is_fallback",
    "Station.source_records",
    "Tombstone.station_id",
    "Tombstone.name",
    "Tombstone.status",
    "Tombstone.removed_in",
    "Tombstone.removed_reason",
    "Tombstone.merged_into",
    "Tombstone.detail",
    "Tombstone.raw",
    "ConstantSet.set_id",
    "ConstantSet.source",
    "ConstantSet.source_type",
    "ConstantSet.quantity",
    "ConstantSet.source_record_id",
    "ConstantSet.source_version",
    "ConstantSet.record_span",
    "ConstantSet.datum",
    "ConstantSet.qc_status",
    "ConstantSet.qc_flags",
    "ConstantSet.dropped_constituents",
    "ConstantSet.time_base",
    "ConstantSet.is_recommended",
    "ConstantSet.convention",
    "ConstantSet.licence",
    "ConstantSet.provenance",
    "ConstantSet.validation",
    "ConstantSet.constituents",
    "ConstantSet.constituent",
    "ConstantSet.raw",
    "ConstantSet.fallback",
    "Constituent.name",
    "Constituent.source_name",
    "Constituent.doodson",
    "Constituent.speed_deg_per_hour",
    "Constituent.amplitude_m",
    "Constituent.phase_deg",
    "Constituent.amp_uncertainty_m",
    "Constituent.phase_uncertainty_deg",
    "Constituent.kept_reason",
    "Constituent.raw",
    "Convention.convention_id",
    "Convention.phase_reference",
    "Convention.utc_offset_hours",
    "Convention.v0_model",
    "Convention.nodal_handling",
    "Convention.nodal_formula_ids",
    "Convention.constituent_table_version",
    "Convention.tables_sha256",
    "Convention.canary",
    "Convention.raw",
    "Licence.licence_id",
    "Licence.spdx",
    "Licence.provider",
    "Licence.citation",
    "Licence.attribution",
    "Licence.url",
    "Licence.commercial_use",
    "Licence.restriction",
    "Licence.terms_url",
    "Licence.raw",
    "Provenance.adapter_version",
    "Provenance.input_sha256",
    "Provenance.selection_reason",
    "Provenance.decision",
    "Provenance.build",
    "Provenance.carried_from_release",
    "Provenance.raw",
    "ProvenanceBuild.build_commit",
    "ProvenanceBuild.built_at",
    "ProvenanceBuild.fetched_at",
    "ProvenanceBuild.run_id",
    "ProvenanceBuild.tool_versions",
    "TimeBase.code",
    "TimeBase.reason",
    "TimeBase.declared",
    "TimeBase.published",
    "TimeBase.correction",
    "TimeBase.months_dropped",
    "TimeBase.decided_in",
    "TimeBase.decided_build_commit",
    "TimeBase.evidence",
    "QcFlag.flag",
    "QcFlag.reason",
    "QcFlag.values",
    "DroppedConstituent.name",
    "DroppedConstituent.dropped_reason",
    "DroppedConstituent.detail",
    "Validation.set_id",
    "Validation.reference_source",
    "Validation.reference_station",
    "Validation.reference_distance_km",
    "Validation.window",
    "Validation.time_mae_min",
    "Validation.time_p95_min",
    "Validation.time_bias_min",
    "Validation.height_mae_m",
    "Validation.range_error_m",
    "Validation.missed_events",
    "Validation.extra_events",
    "Validation.previous_release",
    "SubordinateOffsets.reference_station_id",
    "SubordinateOffsets.time_offset_high_min",
    "SubordinateOffsets.time_offset_low_min",
    "SubordinateOffsets.height_offset_high",
    "SubordinateOffsets.height_offset_low",
    "SubordinateOffsets.height_adjusted_type",
    "SubordinateOffsets.licence_id",
    "SubordinateOffsets.offset_id",
    "SubordinateOffsets.source",
    "SubordinateOffsets.source_type",
    "SubordinateOffsets.source_version",
    "SubordinateOffsets.source_record_id",
    "SubordinateOffsets.qc_status",
    "SubordinateOffsets.qc_flags",
    "SubordinateOffsets.fallback",
    "SubordinateOffsets.vintage",
    "SubordinateOffsets.provenance",
    "Nearby.station",
    "Nearby.distance_km",
    "UpdateResult.updated",
    "UpdateResult.from",
    "UpdateResult.to",
    "RecordSpan.start",
    "RecordSpan.end",
    "RecordSpan.good_samples",
    "Datum.msl_offset_m",
    "Datum.named",
    "Stats.type",
    "Stats.kind",
    "Stats.country",
    "Stats.source",
    "Stats.qc_status",
    "AstroTable.equilibrium_argument",
    "AstroTable.node_factor",
    "AstroTable.equilibrium_for_year",
    "AstroTable.node_factor_for_year",
    "AstroTable.valid_range",
    "HeightPoint.time",
    "HeightPoint.height_m",
    "HeightPoint.local_time",
    "HeightPoint.utc_offset_s",
    "HeightPoint.local_datetime",
    "HeightPoint.local_time_object",
    "Extreme.time",
    "Extreme.type",
    "Extreme.height_m",
    "Extreme.local_time",
    "Extreme.utc_offset_s",
    "Extreme.local_datetime",
    "Extreme.local_time_object",
    "CurrentPoint.time",
    "CurrentPoint.velocity_major_ms",
    "CurrentPoint.velocity_minor_ms",
    "CurrentPoint.speed_ms",
    "CurrentPoint.direction_deg",
    "CurrentPoint.local_time",
    "CurrentPoint.utc_offset_s",
    "CurrentPoint.local_datetime",
    "CurrentPoint.local_time_object",
    "CurrentEvent.time",
    "CurrentEvent.type",
    "CurrentEvent.velocity_ms",
    "CurrentEvent.direction_deg",
    "CurrentEvent.local_time",
    "CurrentEvent.utc_offset_s",
    "CurrentEvent.local_datetime",
    "CurrentEvent.local_time_object",
    "HeightSeries.items",
    "HeightSeries.station_id",
    "HeightSeries.timezone",
    "HeightSeries.method",
    "HeightSeries.set_id",
    "HeightSeries.convention_id",
    "HeightSeries.astro_table_id",
    "HeightSeries.reference_station_id",
    "HeightSeries.reference_bin",
    "HeightSeries.datum",
    "HeightSeries.datum_name",
    "HeightSeries.datum_kind",
    "HeightSeries.datum_uncertainty_m",
    "HeightSeries.tz",
    "HeightSeries.tz_version",
    "HeightSeries.release",
    "HeightSeries.algorithm",
    "HeightSeries.to_local",
    "HeightSeries.offset_id",
    "HeightSeries.offset_source",
    "HeightSeries.offset_source_version",
    "HeightSeries.historical_offsets",
    "HeightSeries.current_validity",
    "HeightSeries.current_accuracy",
    "HeightSeries.reference_set_id",
    "HeightSeries.reference_source_version",
    "HeightSeries.reference_2020_equivalence",
    "HeightSeries.source_note",
    "ExtremeList.items",
    "ExtremeList.station_id",
    "ExtremeList.timezone",
    "ExtremeList.method",
    "ExtremeList.set_id",
    "ExtremeList.convention_id",
    "ExtremeList.astro_table_id",
    "ExtremeList.reference_station_id",
    "ExtremeList.reference_bin",
    "ExtremeList.datum",
    "ExtremeList.datum_name",
    "ExtremeList.datum_kind",
    "ExtremeList.datum_uncertainty_m",
    "ExtremeList.tz",
    "ExtremeList.tz_version",
    "ExtremeList.release",
    "ExtremeList.algorithm",
    "ExtremeList.to_local",
    "ExtremeList.offset_id",
    "ExtremeList.offset_source",
    "ExtremeList.offset_source_version",
    "ExtremeList.historical_offsets",
    "ExtremeList.current_validity",
    "ExtremeList.current_accuracy",
    "ExtremeList.reference_set_id",
    "ExtremeList.reference_source_version",
    "ExtremeList.reference_2020_equivalence",
    "ExtremeList.source_note",
    "CurrentSeries.items",
    "CurrentSeries.station_id",
    "CurrentSeries.timezone",
    "CurrentSeries.method",
    "CurrentSeries.set_id",
    "CurrentSeries.convention_id",
    "CurrentSeries.astro_table_id",
    "CurrentSeries.reference_station_id",
    "CurrentSeries.reference_bin",
    "CurrentSeries.datum",
    "CurrentSeries.datum_name",
    "CurrentSeries.datum_kind",
    "CurrentSeries.datum_uncertainty_m",
    "CurrentSeries.bin_number",
    "CurrentSeries.tz",
    "CurrentSeries.tz_version",
    "CurrentSeries.release",
    "CurrentSeries.algorithm",
    "CurrentSeries.to_local",
    "CurrentEventList.items",
    "CurrentEventList.station_id",
    "CurrentEventList.timezone",
    "CurrentEventList.method",
    "CurrentEventList.set_id",
    "CurrentEventList.convention_id",
    "CurrentEventList.astro_table_id",
    "CurrentEventList.reference_station_id",
    "CurrentEventList.reference_bin",
    "CurrentEventList.datum",
    "CurrentEventList.datum_name",
    "CurrentEventList.datum_kind",
    "CurrentEventList.datum_uncertainty_m",
    "CurrentEventList.bin_number",
    "CurrentEventList.omitted_event_types",
    "CurrentEventList.tz",
    "CurrentEventList.tz_version",
    "CurrentEventList.release",
    "CurrentEventList.algorithm",
    "CurrentEventList.to_local",
    "DatumInfo.set_id",
    "DatumInfo.zero",
    "DatumInfo.zero_name",
    "DatumInfo.chart_datum",
    "DatumInfo.msl_offset_m",
    "DatumInfo.levels",
    "DatumLevel.key",
    "DatumLevel.value_m",
    "DatumLevel.above_chart_m",
    "DatumLevel.kind",
    "DatumLevel.method",
    "DatumLevel.source_name",
    "DatumLevel.epoch",
    "DatumLevel.data_span",
    "DatumLevel.control_station_id",
    "DatumLevel.control_set_id",
    "DatumLevel.control_source_id",
    "DatumLevel.uncertainty_m",
    "DatumLevel.uncertainty_basis",
    "DatumLevel.flags",
    "Ranges.mn",
    "Ranges.gt",
    "Ranges.dhq",
    "Ranges.dlq",
    "Fallback.reason",
    "Fallback.basis",
    "Fallback.otc_finding",
    "Fallback.preferred_set_id",
    "Fallback.raw",
    "SourceRecord.source",
    "SourceRecord.source_version",
    "SourceRecord.source_record_id",
    "SourceRecord.role",
    "SourceRecord.disposition",
    "SourceRecord.detail",
    "SourceRecord.licence_id",
    "SourceRecord.upstream_licence_id",
    "SourceRecord.published_set_ids",
    "SourceRecord.provenance",
    "SourceRecord.original_metadata",
    "SourceRecord.original_harmonics",
    "SourceRecord.licence",
    "SourceRecord.upstream_licence",
    "SourceRecord.raw",
    "HistoricalOffsetVintage.publication_year",
    "HistoricalOffsetVintage.source_lifecycle",
    "HistoricalOffsetVintage.removal_events",
    "HistoricalOffsetVintage.current_validity",
    "HistoricalOffsetVintage.current_accuracy",
    "HistoricalOffsetVintage.reference_2020_equivalence",
    "HistoricalOffsetVintage.reference_2020_equivalence_sha256",
    "HistoricalOffsetProvenance.source_manifest_sha256",
    "HistoricalOffsetProvenance.input_sha256",
    "HistoricalOffsetProvenance.book",
    "HistoricalOffsetProvenance.annual_table_row",
    "HistoricalOffsetProvenance.printed_page",
    "HistoricalOffsetProvenance.pdf_page",
    "HistoricalOffsetProvenance.raw_row_text",
    "HistoricalOffsetProvenance.raw_values_json",
    "HistoricalOffsetProvenance.id_crosswalk",
    "HistoricalOffsetProvenance.reference_binding",
    "HistoricalOffsetProvenance.acceptance_report_sha256",
]


@dataclass(frozen=True, slots=True)
class _Arguments0:
    member_id: Literal["Client.open"]
    release: str | _Omitted
    file: str | None | _Omitted
    cache_dir: str | None | _Omitted
    offline: bool | _Omitted
    mode: E.Mode | _Omitted
    base_url: str | _Omitted
    timeout: float | None | _Omitted
    proxy: str | None | _Omitted
    ca_file: str | None | _Omitted
    user_agent: str | None | _Omitted
    on_network_error: E.OnNetworkError | _Omitted
    auto_update: bool | _Omitted
    update_interval: float | _Omitted
    logger: logging.Logger | None | _Omitted
    verify_on_open: bool | _Omitted
    commercial_only: bool | _Omitted
    commercial_basis: str | _Omitted
    historical_offsets_policy: str | _Omitted


@dataclass(frozen=True, slots=True)
class _Arguments1:
    member_id: Literal[
        "Client.release",
        "Client.loaded_from",
        "Client.last_error",
        "Client.releases",
        "Client.latest",
        "Client.check_for_update",
        "Client.newer_format_major",
        "Client.update",
        "Client.verify",
        "Client.cached_releases",
        "Client.close",
        "Release.datestamp",
        "Release.created",
        "Release.format_version",
        "Release.zenodo_version_doi",
        "Release.concept_doi",
        "Release.source_versions",
        "Release.build_commit",
        "Release.changelog_url",
        "Release.files",
        "Release.conventions",
        "Release.licences",
        "Release.constituent_names",
        "Release.stats",
        "Release.station_count",
        "Release.tombstone_count",
        "Release.citation",
        "Release.historical_offsets_policy",
        "ReleaseInfo.datestamp",
        "ReleaseInfo.format_version",
        "ReleaseInfo.concept_doi",
        "ReleaseInfo.zenodo_version_doi",
        "ReleaseInfo.content_sha256",
        "ReleaseInfo.files",
        "FileInfo.name",
        "FileInfo.url",
        "FileInfo.size",
        "FileInfo.sha256",
        "Station.station_id",
        "Station.name",
        "Station.country",
        "Station.lat",
        "Station.lon",
        "Station.type",
        "Station.kind",
        "Station.timezone",
        "Station.aliases",
        "Station.status",
        "Station.is_reference",
        "Station.is_subordinate",
        "Station.is_tide",
        "Station.is_current",
        "Station.recommended_set",
        "Station.subordinate_offsets",
        "Station.validation",
        "Station.raw",
        "Station.recommended_is_fallback",
        "Station.source_records",
        "Tombstone.station_id",
        "Tombstone.name",
        "Tombstone.status",
        "Tombstone.removed_in",
        "Tombstone.removed_reason",
        "Tombstone.merged_into",
        "Tombstone.detail",
        "Tombstone.raw",
        "ConstantSet.set_id",
        "ConstantSet.source",
        "ConstantSet.source_type",
        "ConstantSet.quantity",
        "ConstantSet.source_record_id",
        "ConstantSet.source_version",
        "ConstantSet.record_span",
        "ConstantSet.datum",
        "ConstantSet.qc_status",
        "ConstantSet.qc_flags",
        "ConstantSet.dropped_constituents",
        "ConstantSet.time_base",
        "ConstantSet.is_recommended",
        "ConstantSet.convention",
        "ConstantSet.licence",
        "ConstantSet.provenance",
        "ConstantSet.validation",
        "ConstantSet.constituents",
        "ConstantSet.raw",
        "ConstantSet.fallback",
        "Constituent.name",
        "Constituent.source_name",
        "Constituent.doodson",
        "Constituent.speed_deg_per_hour",
        "Constituent.amplitude_m",
        "Constituent.phase_deg",
        "Constituent.amp_uncertainty_m",
        "Constituent.phase_uncertainty_deg",
        "Constituent.kept_reason",
        "Constituent.raw",
        "Convention.convention_id",
        "Convention.phase_reference",
        "Convention.utc_offset_hours",
        "Convention.v0_model",
        "Convention.nodal_handling",
        "Convention.nodal_formula_ids",
        "Convention.constituent_table_version",
        "Convention.tables_sha256",
        "Convention.canary",
        "Convention.raw",
        "Licence.licence_id",
        "Licence.spdx",
        "Licence.provider",
        "Licence.citation",
        "Licence.attribution",
        "Licence.url",
        "Licence.commercial_use",
        "Licence.restriction",
        "Licence.terms_url",
        "Licence.raw",
        "Provenance.adapter_version",
        "Provenance.input_sha256",
        "Provenance.selection_reason",
        "Provenance.decision",
        "Provenance.build",
        "Provenance.carried_from_release",
        "Provenance.raw",
        "ProvenanceBuild.build_commit",
        "ProvenanceBuild.built_at",
        "ProvenanceBuild.fetched_at",
        "ProvenanceBuild.run_id",
        "ProvenanceBuild.tool_versions",
        "TimeBase.code",
        "TimeBase.reason",
        "TimeBase.declared",
        "TimeBase.published",
        "TimeBase.correction",
        "TimeBase.months_dropped",
        "TimeBase.decided_in",
        "TimeBase.decided_build_commit",
        "TimeBase.evidence",
        "QcFlag.flag",
        "QcFlag.reason",
        "QcFlag.values",
        "DroppedConstituent.name",
        "DroppedConstituent.dropped_reason",
        "DroppedConstituent.detail",
        "Validation.set_id",
        "Validation.reference_source",
        "Validation.reference_station",
        "Validation.reference_distance_km",
        "Validation.window",
        "Validation.time_mae_min",
        "Validation.time_p95_min",
        "Validation.time_bias_min",
        "Validation.height_mae_m",
        "Validation.range_error_m",
        "Validation.missed_events",
        "Validation.extra_events",
        "Validation.previous_release",
        "SubordinateOffsets.reference_station_id",
        "SubordinateOffsets.time_offset_high_min",
        "SubordinateOffsets.time_offset_low_min",
        "SubordinateOffsets.height_offset_high",
        "SubordinateOffsets.height_offset_low",
        "SubordinateOffsets.height_adjusted_type",
        "SubordinateOffsets.licence_id",
        "SubordinateOffsets.offset_id",
        "SubordinateOffsets.source",
        "SubordinateOffsets.source_type",
        "SubordinateOffsets.source_version",
        "SubordinateOffsets.source_record_id",
        "SubordinateOffsets.qc_status",
        "SubordinateOffsets.qc_flags",
        "SubordinateOffsets.fallback",
        "SubordinateOffsets.vintage",
        "SubordinateOffsets.provenance",
        "Nearby.station",
        "Nearby.distance_km",
        "UpdateResult.updated",
        "UpdateResult.from",
        "UpdateResult.to",
        "RecordSpan.start",
        "RecordSpan.end",
        "RecordSpan.good_samples",
        "Datum.msl_offset_m",
        "Datum.named",
        "Stats.type",
        "Stats.kind",
        "Stats.country",
        "Stats.source",
        "Stats.qc_status",
        "AstroTable.valid_range",
        "HeightPoint.time",
        "HeightPoint.height_m",
        "HeightPoint.local_time",
        "HeightPoint.utc_offset_s",
        "HeightPoint.local_datetime",
        "HeightPoint.local_time_object",
        "Extreme.time",
        "Extreme.type",
        "Extreme.height_m",
        "Extreme.local_time",
        "Extreme.utc_offset_s",
        "Extreme.local_datetime",
        "Extreme.local_time_object",
        "CurrentPoint.time",
        "CurrentPoint.velocity_major_ms",
        "CurrentPoint.velocity_minor_ms",
        "CurrentPoint.speed_ms",
        "CurrentPoint.direction_deg",
        "CurrentPoint.local_time",
        "CurrentPoint.utc_offset_s",
        "CurrentPoint.local_datetime",
        "CurrentPoint.local_time_object",
        "CurrentEvent.time",
        "CurrentEvent.type",
        "CurrentEvent.velocity_ms",
        "CurrentEvent.direction_deg",
        "CurrentEvent.local_time",
        "CurrentEvent.utc_offset_s",
        "CurrentEvent.local_datetime",
        "CurrentEvent.local_time_object",
        "HeightSeries.items",
        "HeightSeries.station_id",
        "HeightSeries.timezone",
        "HeightSeries.method",
        "HeightSeries.set_id",
        "HeightSeries.convention_id",
        "HeightSeries.astro_table_id",
        "HeightSeries.reference_station_id",
        "HeightSeries.reference_bin",
        "HeightSeries.datum",
        "HeightSeries.datum_name",
        "HeightSeries.datum_kind",
        "HeightSeries.datum_uncertainty_m",
        "HeightSeries.tz",
        "HeightSeries.tz_version",
        "HeightSeries.release",
        "HeightSeries.algorithm",
        "HeightSeries.offset_id",
        "HeightSeries.offset_source",
        "HeightSeries.offset_source_version",
        "HeightSeries.historical_offsets",
        "HeightSeries.current_validity",
        "HeightSeries.current_accuracy",
        "HeightSeries.reference_set_id",
        "HeightSeries.reference_source_version",
        "HeightSeries.reference_2020_equivalence",
        "HeightSeries.source_note",
        "ExtremeList.items",
        "ExtremeList.station_id",
        "ExtremeList.timezone",
        "ExtremeList.method",
        "ExtremeList.set_id",
        "ExtremeList.convention_id",
        "ExtremeList.astro_table_id",
        "ExtremeList.reference_station_id",
        "ExtremeList.reference_bin",
        "ExtremeList.datum",
        "ExtremeList.datum_name",
        "ExtremeList.datum_kind",
        "ExtremeList.datum_uncertainty_m",
        "ExtremeList.tz",
        "ExtremeList.tz_version",
        "ExtremeList.release",
        "ExtremeList.algorithm",
        "ExtremeList.offset_id",
        "ExtremeList.offset_source",
        "ExtremeList.offset_source_version",
        "ExtremeList.historical_offsets",
        "ExtremeList.current_validity",
        "ExtremeList.current_accuracy",
        "ExtremeList.reference_set_id",
        "ExtremeList.reference_source_version",
        "ExtremeList.reference_2020_equivalence",
        "ExtremeList.source_note",
        "CurrentSeries.items",
        "CurrentSeries.station_id",
        "CurrentSeries.timezone",
        "CurrentSeries.method",
        "CurrentSeries.set_id",
        "CurrentSeries.convention_id",
        "CurrentSeries.astro_table_id",
        "CurrentSeries.reference_station_id",
        "CurrentSeries.reference_bin",
        "CurrentSeries.datum",
        "CurrentSeries.datum_name",
        "CurrentSeries.datum_kind",
        "CurrentSeries.datum_uncertainty_m",
        "CurrentSeries.bin_number",
        "CurrentSeries.tz",
        "CurrentSeries.tz_version",
        "CurrentSeries.release",
        "CurrentSeries.algorithm",
        "CurrentEventList.items",
        "CurrentEventList.station_id",
        "CurrentEventList.timezone",
        "CurrentEventList.method",
        "CurrentEventList.set_id",
        "CurrentEventList.convention_id",
        "CurrentEventList.astro_table_id",
        "CurrentEventList.reference_station_id",
        "CurrentEventList.reference_bin",
        "CurrentEventList.datum",
        "CurrentEventList.datum_name",
        "CurrentEventList.datum_kind",
        "CurrentEventList.datum_uncertainty_m",
        "CurrentEventList.bin_number",
        "CurrentEventList.omitted_event_types",
        "CurrentEventList.tz",
        "CurrentEventList.tz_version",
        "CurrentEventList.release",
        "CurrentEventList.algorithm",
        "DatumInfo.set_id",
        "DatumInfo.zero",
        "DatumInfo.zero_name",
        "DatumInfo.chart_datum",
        "DatumInfo.msl_offset_m",
        "DatumInfo.levels",
        "DatumLevel.key",
        "DatumLevel.value_m",
        "DatumLevel.above_chart_m",
        "DatumLevel.kind",
        "DatumLevel.method",
        "DatumLevel.source_name",
        "DatumLevel.epoch",
        "DatumLevel.data_span",
        "DatumLevel.control_station_id",
        "DatumLevel.control_set_id",
        "DatumLevel.control_source_id",
        "DatumLevel.uncertainty_m",
        "DatumLevel.uncertainty_basis",
        "DatumLevel.flags",
        "Ranges.mn",
        "Ranges.gt",
        "Ranges.dhq",
        "Ranges.dlq",
        "Fallback.reason",
        "Fallback.basis",
        "Fallback.otc_finding",
        "Fallback.preferred_set_id",
        "Fallback.raw",
        "SourceRecord.source",
        "SourceRecord.source_version",
        "SourceRecord.source_record_id",
        "SourceRecord.role",
        "SourceRecord.disposition",
        "SourceRecord.detail",
        "SourceRecord.licence_id",
        "SourceRecord.upstream_licence_id",
        "SourceRecord.published_set_ids",
        "SourceRecord.provenance",
        "SourceRecord.original_metadata",
        "SourceRecord.original_harmonics",
        "SourceRecord.licence",
        "SourceRecord.upstream_licence",
        "SourceRecord.raw",
        "HistoricalOffsetVintage.publication_year",
        "HistoricalOffsetVintage.source_lifecycle",
        "HistoricalOffsetVintage.removal_events",
        "HistoricalOffsetVintage.current_validity",
        "HistoricalOffsetVintage.current_accuracy",
        "HistoricalOffsetVintage.reference_2020_equivalence",
        "HistoricalOffsetVintage.reference_2020_equivalence_sha256",
        "HistoricalOffsetProvenance.source_manifest_sha256",
        "HistoricalOffsetProvenance.input_sha256",
        "HistoricalOffsetProvenance.book",
        "HistoricalOffsetProvenance.annual_table_row",
        "HistoricalOffsetProvenance.printed_page",
        "HistoricalOffsetProvenance.pdf_page",
        "HistoricalOffsetProvenance.raw_row_text",
        "HistoricalOffsetProvenance.raw_values_json",
        "HistoricalOffsetProvenance.id_crosswalk",
        "HistoricalOffsetProvenance.reference_binding",
        "HistoricalOffsetProvenance.acceptance_report_sha256",
    ]


@dataclass(frozen=True, slots=True)
class _Arguments2:
    member_id: Literal["Client.download"]
    release: str | _Omitted
    to: str
    formats: tuple[E.Format, ...] | _Omitted
    overwrite: bool | _Omitted


@dataclass(frozen=True, slots=True)
class _Arguments3:
    member_id: Literal["Client.prune"]
    keep: int | _Omitted


@dataclass(frozen=True, slots=True)
class _Arguments4:
    member_id: Literal["Release.convention"]
    convention_id: str


@dataclass(frozen=True, slots=True)
class _Arguments5:
    member_id: Literal["Release.licence"]
    licence_id: str


@dataclass(frozen=True, slots=True)
class _Arguments6:
    member_id: Literal[
        "Release.station", "Release.require_station", "Release.tombstone"
    ]
    station_id: str


@dataclass(frozen=True, slots=True)
class _Arguments7:
    member_id: Literal["Release.station_by_alias"]
    system: E.AliasSystem
    alias_id: str


@dataclass(frozen=True, slots=True)
class _Arguments8:
    member_id: Literal["Release.stations", "Release.iter_stations"]
    country: str | None | _Omitted
    type: E.StationType | None | _Omitted
    kind: E.Kind | None | _Omitted
    source: str | None | _Omitted
    source_type: E.SourceType | None | _Omitted
    include_flagged: bool | _Omitted
    include_fallback: bool | _Omitted


@dataclass(frozen=True, slots=True)
class _Arguments9:
    member_id: Literal["Release.search"]
    name: str
    limit: int | None | _Omitted
    match: E.Match | None | _Omitted
    country: str | None | _Omitted
    type: E.StationType | None | _Omitted
    kind: E.Kind | None | _Omitted
    source: str | None | _Omitted
    source_type: E.SourceType | None | _Omitted
    include_flagged: bool | _Omitted
    include_fallback: bool | _Omitted


@dataclass(frozen=True, slots=True)
class _Arguments10:
    member_id: Literal["Release.near"]
    lat: float
    lon: float
    radius_km: float
    limit: int | None | _Omitted
    country: str | None | _Omitted
    type: E.StationType | None | _Omitted
    kind: E.Kind | None | _Omitted
    source: str | None | _Omitted
    source_type: E.SourceType | None | _Omitted
    include_flagged: bool | _Omitted
    include_fallback: bool | _Omitted


@dataclass(frozen=True, slots=True)
class _Arguments11:
    member_id: Literal["Release.nearest"]
    lat: float
    lon: float
    max_km: float | None | _Omitted
    country: str | None | _Omitted
    type: E.StationType | None | _Omitted
    kind: E.Kind | None | _Omitted
    source: str | None | _Omitted
    source_type: E.SourceType | None | _Omitted
    include_flagged: bool | _Omitted
    include_fallback: bool | _Omitted


@dataclass(frozen=True, slots=True)
class _Arguments12:
    member_id: Literal["Release.reference_station", "Release.subordinates_of"]
    station: Station


@dataclass(frozen=True, slots=True)
class _Arguments13:
    member_id: Literal["Release.attribution"]
    stations: tuple[Station, ...] | None | _Omitted


@dataclass(frozen=True, slots=True)
class _Arguments14:
    member_id: Literal["Release.heights"]
    station: Station | str
    start: datetime
    stop: datetime
    step_s: int | _Omitted
    datum: str | None | _Omitted
    set_id: str | None | _Omitted
    offset_id: str | None | _Omitted


@dataclass(frozen=True, slots=True)
class _Arguments15:
    member_id: Literal["Release.heights_at"]
    station: Station | str
    times: tuple[datetime, ...]
    datum: str | None | _Omitted
    set_id: str | None | _Omitted
    offset_id: str | None | _Omitted


@dataclass(frozen=True, slots=True)
class _Arguments16:
    member_id: Literal["Release.extremes"]
    station: Station | str
    start: datetime
    stop: datetime
    datum: str | None | _Omitted
    set_id: str | None | _Omitted
    offset_id: str | None | _Omitted


@dataclass(frozen=True, slots=True)
class _Arguments17:
    member_id: Literal["Release.currents"]
    station: Station | str
    start: datetime
    stop: datetime
    step_s: int | _Omitted
    bin_number: int | None | _Omitted
    set_id: str | None | _Omitted


@dataclass(frozen=True, slots=True)
class _Arguments18:
    member_id: Literal["Release.current_events"]
    station: Station | str
    start: datetime
    stop: datetime
    bin_number: int | None | _Omitted
    set_id: str | None | _Omitted


@dataclass(frozen=True, slots=True)
class _Arguments19:
    member_id: Literal["Release.datums"]
    station: Station | str
    set_id: str | None | _Omitted
    all_sets: bool | _Omitted


@dataclass(frozen=True, slots=True)
class _Arguments20:
    member_id: Literal["Release.ranges"]
    station: Station | str
    set_id: str | None | _Omitted


@dataclass(frozen=True, slots=True)
class _Arguments21:
    member_id: Literal["Release.astro_table"]
    id: str | None | _Omitted


@dataclass(frozen=True, slots=True)
class _Arguments22:
    member_id: Literal["Station.constant_sets"]
    include_no_constants: bool | _Omitted


@dataclass(frozen=True, slots=True)
class _Arguments23:
    member_id: Literal["Station.constant_set"]
    set_id: str


@dataclass(frozen=True, slots=True)
class _Arguments24:
    member_id: Literal["ConstantSet.constituent"]
    name: str


@dataclass(frozen=True, slots=True)
class _Arguments25:
    member_id: Literal["AstroTable.equilibrium_argument", "AstroTable.node_factor"]
    name: str
    at: datetime


@dataclass(frozen=True, slots=True)
class _Arguments26:
    member_id: Literal[
        "AstroTable.equilibrium_for_year", "AstroTable.node_factor_for_year"
    ]
    name: str
    year: int


@dataclass(frozen=True, slots=True)
class _Arguments27:
    member_id: Literal[
        "HeightSeries.to_local",
        "ExtremeList.to_local",
        "CurrentSeries.to_local",
        "CurrentEventList.to_local",
    ]
    tz: str | _Omitted


_MemberArguments: TypeAlias = (
    _Arguments0
    | _Arguments1
    | _Arguments2
    | _Arguments3
    | _Arguments4
    | _Arguments5
    | _Arguments6
    | _Arguments7
    | _Arguments8
    | _Arguments9
    | _Arguments10
    | _Arguments11
    | _Arguments12
    | _Arguments13
    | _Arguments14
    | _Arguments15
    | _Arguments16
    | _Arguments17
    | _Arguments18
    | _Arguments19
    | _Arguments20
    | _Arguments21
    | _Arguments22
    | _Arguments23
    | _Arguments24
    | _Arguments25
    | _Arguments26
    | _Arguments27
)


@dataclass(frozen=True, slots=True)
class _MemberValue0:
    member_id: Literal["Client.open"]
    value: OpenTideConstants


@dataclass(frozen=True, slots=True)
class _MemberValue1:
    member_id: Literal["Client.release"]
    value: Release


@dataclass(frozen=True, slots=True)
class _MemberValue2:
    member_id: Literal["Client.loaded_from"]
    value: E.LoadedFrom


@dataclass(frozen=True, slots=True)
class _MemberValue3:
    member_id: Literal["Client.last_error"]
    value: OpenTideConstantsError | None


@dataclass(frozen=True, slots=True)
class _MemberValue4:
    member_id: Literal["Client.releases"]
    value: tuple[ReleaseInfo, ...]


@dataclass(frozen=True, slots=True)
class _MemberValue5:
    member_id: Literal["Client.latest"]
    value: ReleaseInfo


@dataclass(frozen=True, slots=True)
class _MemberValue6:
    member_id: Literal["Client.check_for_update"]
    value: ReleaseInfo | None


@dataclass(frozen=True, slots=True)
class _MemberValue7:
    member_id: Literal[
        "Client.newer_format_major",
        "FileInfo.size",
        "Validation.missed_events",
        "Validation.extra_events",
        "RecordSpan.good_samples",
        "HeightPoint.utc_offset_s",
        "Extreme.utc_offset_s",
        "CurrentPoint.utc_offset_s",
        "CurrentEvent.utc_offset_s",
        "HeightSeries.reference_bin",
        "ExtremeList.reference_bin",
        "CurrentSeries.reference_bin",
        "CurrentEventList.reference_bin",
    ]
    value: int | None


@dataclass(frozen=True, slots=True)
class _MemberValue8:
    member_id: Literal["Client.update"]
    value: UpdateResult


@dataclass(frozen=True, slots=True)
class _MemberValue9:
    member_id: Literal[
        "Client.download",
        "Client.cached_releases",
        "Client.prune",
        "Release.constituent_names",
        "TimeBase.months_dropped",
        "DatumLevel.flags",
        "SourceRecord.published_set_ids",
        "HistoricalOffsetProvenance.input_sha256",
    ]
    value: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _MemberValue10:
    member_id: Literal[
        "Client.verify",
        "Station.is_reference",
        "Station.is_subordinate",
        "Station.is_tide",
        "Station.is_current",
        "ConstantSet.is_recommended",
        "Licence.commercial_use",
        "UpdateResult.updated",
        "HeightSeries.historical_offsets",
        "ExtremeList.historical_offsets",
    ]
    value: bool


@dataclass(frozen=True, slots=True)
class _MemberValue11:
    member_id: Literal[
        "Release.datestamp",
        "Release.format_version",
        "Release.citation",
        "Release.attribution",
        "Release.historical_offsets_policy",
        "ReleaseInfo.datestamp",
        "ReleaseInfo.format_version",
        "ReleaseInfo.content_sha256",
        "FileInfo.name",
        "Station.station_id",
        "Station.name",
        "Station.timezone",
        "Tombstone.station_id",
        "Tombstone.removed_in",
        "Tombstone.merged_into",
        "ConstantSet.set_id",
        "ConstantSet.source",
        "ConstantSet.source_record_id",
        "ConstantSet.source_version",
        "Constituent.name",
        "Convention.convention_id",
        "Convention.v0_model",
        "Convention.constituent_table_version",
        "Licence.licence_id",
        "Licence.spdx",
        "Licence.provider",
        "Licence.attribution",
        "ProvenanceBuild.build_commit",
        "TimeBase.reason",
        "TimeBase.declared",
        "TimeBase.published",
        "TimeBase.decided_in",
        "QcFlag.reason",
        "DroppedConstituent.name",
        "Validation.set_id",
        "Validation.reference_source",
        "Validation.window",
        "SubordinateOffsets.reference_station_id",
        "HeightSeries.station_id",
        "HeightSeries.timezone",
        "HeightSeries.set_id",
        "HeightSeries.convention_id",
        "HeightSeries.astro_table_id",
        "HeightSeries.release",
        "HeightSeries.algorithm",
        "ExtremeList.station_id",
        "ExtremeList.timezone",
        "ExtremeList.set_id",
        "ExtremeList.convention_id",
        "ExtremeList.astro_table_id",
        "ExtremeList.release",
        "ExtremeList.algorithm",
        "CurrentSeries.station_id",
        "CurrentSeries.timezone",
        "CurrentSeries.set_id",
        "CurrentSeries.convention_id",
        "CurrentSeries.astro_table_id",
        "CurrentSeries.release",
        "CurrentSeries.algorithm",
        "CurrentEventList.station_id",
        "CurrentEventList.timezone",
        "CurrentEventList.set_id",
        "CurrentEventList.convention_id",
        "CurrentEventList.astro_table_id",
        "CurrentEventList.release",
        "CurrentEventList.algorithm",
        "DatumLevel.key",
        "DatumLevel.kind",
        "DatumLevel.method",
        "Fallback.basis",
        "Fallback.otc_finding",
        "SourceRecord.source",
        "SourceRecord.source_version",
        "SourceRecord.source_record_id",
        "SourceRecord.detail",
        "HistoricalOffsetVintage.source_lifecycle",
        "HistoricalOffsetVintage.current_validity",
        "HistoricalOffsetVintage.current_accuracy",
        "HistoricalOffsetVintage.reference_2020_equivalence",
        "HistoricalOffsetProvenance.source_manifest_sha256",
        "HistoricalOffsetProvenance.book",
        "HistoricalOffsetProvenance.raw_row_text",
        "HistoricalOffsetProvenance.raw_values_json",
        "HistoricalOffsetProvenance.acceptance_report_sha256",
    ]
    value: str


@dataclass(frozen=True, slots=True)
class _MemberValue12:
    member_id: Literal[
        "Release.created",
        "RecordSpan.start",
        "RecordSpan.end",
        "HeightPoint.time",
        "Extreme.time",
        "CurrentPoint.time",
        "CurrentEvent.time",
    ]
    value: datetime


@dataclass(frozen=True, slots=True)
class _MemberValue13:
    member_id: Literal[
        "Release.zenodo_version_doi",
        "Release.concept_doi",
        "Release.build_commit",
        "Release.changelog_url",
        "ReleaseInfo.concept_doi",
        "ReleaseInfo.zenodo_version_doi",
        "FileInfo.url",
        "FileInfo.sha256",
        "Station.country",
        "Tombstone.name",
        "Tombstone.detail",
        "Constituent.source_name",
        "Constituent.doodson",
        "Constituent.kept_reason",
        "Convention.tables_sha256",
        "Licence.citation",
        "Licence.url",
        "Licence.restriction",
        "Licence.terms_url",
        "Provenance.adapter_version",
        "Provenance.selection_reason",
        "Provenance.carried_from_release",
        "ProvenanceBuild.run_id",
        "TimeBase.decided_build_commit",
        "DroppedConstituent.detail",
        "Validation.reference_station",
        "SubordinateOffsets.licence_id",
        "SubordinateOffsets.offset_id",
        "SubordinateOffsets.source",
        "SubordinateOffsets.source_version",
        "SubordinateOffsets.source_record_id",
        "UpdateResult.from",
        "UpdateResult.to",
        "HeightPoint.local_time",
        "Extreme.local_time",
        "CurrentPoint.local_time",
        "CurrentEvent.local_time",
        "HeightSeries.reference_station_id",
        "HeightSeries.datum",
        "HeightSeries.datum_name",
        "HeightSeries.datum_kind",
        "HeightSeries.tz",
        "HeightSeries.tz_version",
        "HeightSeries.offset_id",
        "HeightSeries.offset_source",
        "HeightSeries.offset_source_version",
        "HeightSeries.current_validity",
        "HeightSeries.current_accuracy",
        "HeightSeries.reference_set_id",
        "HeightSeries.reference_source_version",
        "HeightSeries.reference_2020_equivalence",
        "HeightSeries.source_note",
        "ExtremeList.reference_station_id",
        "ExtremeList.datum",
        "ExtremeList.datum_name",
        "ExtremeList.datum_kind",
        "ExtremeList.tz",
        "ExtremeList.tz_version",
        "ExtremeList.offset_id",
        "ExtremeList.offset_source",
        "ExtremeList.offset_source_version",
        "ExtremeList.current_validity",
        "ExtremeList.current_accuracy",
        "ExtremeList.reference_set_id",
        "ExtremeList.reference_source_version",
        "ExtremeList.reference_2020_equivalence",
        "ExtremeList.source_note",
        "CurrentSeries.reference_station_id",
        "CurrentSeries.datum",
        "CurrentSeries.datum_name",
        "CurrentSeries.datum_kind",
        "CurrentSeries.tz",
        "CurrentSeries.tz_version",
        "CurrentEventList.reference_station_id",
        "CurrentEventList.datum",
        "CurrentEventList.datum_name",
        "CurrentEventList.datum_kind",
        "CurrentEventList.tz",
        "CurrentEventList.tz_version",
        "DatumInfo.set_id",
        "DatumInfo.zero",
        "DatumInfo.zero_name",
        "DatumInfo.chart_datum",
        "DatumLevel.source_name",
        "DatumLevel.control_station_id",
        "DatumLevel.control_set_id",
        "DatumLevel.control_source_id",
        "DatumLevel.uncertainty_basis",
        "Fallback.preferred_set_id",
        "SourceRecord.licence_id",
        "SourceRecord.upstream_licence_id",
        "HistoricalOffsetVintage.reference_2020_equivalence_sha256",
    ]
    value: str | None


@dataclass(frozen=True, slots=True)
class _MemberValue14:
    member_id: Literal["Release.source_versions"]
    value: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class _MemberValue15:
    member_id: Literal["Release.files", "ReleaseInfo.files"]
    value: tuple[FileInfo, ...]


@dataclass(frozen=True, slots=True)
class _MemberValue16:
    member_id: Literal["Release.conventions"]
    value: tuple[Convention, ...]


@dataclass(frozen=True, slots=True)
class _MemberValue17:
    member_id: Literal["Release.convention"]
    value: Convention | None


@dataclass(frozen=True, slots=True)
class _MemberValue18:
    member_id: Literal["Release.licences"]
    value: tuple[Licence, ...]


@dataclass(frozen=True, slots=True)
class _MemberValue19:
    member_id: Literal[
        "Release.licence", "SourceRecord.licence", "SourceRecord.upstream_licence"
    ]
    value: Licence | None


@dataclass(frozen=True, slots=True)
class _MemberValue20:
    member_id: Literal["Release.stats"]
    value: Stats


@dataclass(frozen=True, slots=True)
class _MemberValue21:
    member_id: Literal[
        "Release.station_count",
        "Release.tombstone_count",
        "CurrentSeries.bin_number",
        "CurrentEventList.bin_number",
    ]
    value: int


@dataclass(frozen=True, slots=True)
class _MemberValue22:
    member_id: Literal[
        "Release.station", "Release.station_by_alias", "Release.reference_station"
    ]
    value: Station | None


@dataclass(frozen=True, slots=True)
class _MemberValue23:
    member_id: Literal["Release.require_station", "Nearby.station"]
    value: Station


@dataclass(frozen=True, slots=True)
class _MemberValue24:
    member_id: Literal["Release.tombstone"]
    value: Tombstone | None


@dataclass(frozen=True, slots=True)
class _MemberValue25:
    member_id: Literal["Release.stations", "Release.search", "Release.subordinates_of"]
    value: tuple[Station, ...]


@dataclass(frozen=True, slots=True)
class _MemberValue26:
    member_id: Literal["Release.iter_stations"]
    value: Iterator[Station]


@dataclass(frozen=True, slots=True)
class _MemberValue27:
    member_id: Literal["Release.near"]
    value: tuple[Nearby, ...]


@dataclass(frozen=True, slots=True)
class _MemberValue28:
    member_id: Literal["Release.nearest"]
    value: Nearby | None


@dataclass(frozen=True, slots=True)
class _MemberValue29:
    member_id: Literal["Release.heights", "Release.heights_at", "HeightSeries.to_local"]
    value: HeightSeries


@dataclass(frozen=True, slots=True)
class _MemberValue30:
    member_id: Literal["Release.extremes", "ExtremeList.to_local"]
    value: ExtremeList


@dataclass(frozen=True, slots=True)
class _MemberValue31:
    member_id: Literal["Release.currents", "CurrentSeries.to_local"]
    value: CurrentSeries


@dataclass(frozen=True, slots=True)
class _MemberValue32:
    member_id: Literal["Release.current_events", "CurrentEventList.to_local"]
    value: CurrentEventList


@dataclass(frozen=True, slots=True)
class _MemberValue33:
    member_id: Literal["Release.datums"]
    value: DatumInfo | tuple[DatumInfo, ...]


@dataclass(frozen=True, slots=True)
class _MemberValue34:
    member_id: Literal["Release.ranges"]
    value: Ranges


@dataclass(frozen=True, slots=True)
class _MemberValue35:
    member_id: Literal["Release.astro_table"]
    value: AstroTable | None


@dataclass(frozen=True, slots=True)
class _MemberValue36:
    member_id: Literal[
        "Station.lat",
        "Station.lon",
        "Constituent.speed_deg_per_hour",
        "Constituent.amplitude_m",
        "Constituent.phase_deg",
        "Validation.time_mae_min",
        "Validation.height_mae_m",
        "Nearby.distance_km",
        "AstroTable.equilibrium_argument",
        "AstroTable.node_factor",
        "AstroTable.equilibrium_for_year",
        "AstroTable.node_factor_for_year",
        "HeightPoint.height_m",
        "Extreme.height_m",
        "CurrentPoint.velocity_major_ms",
        "CurrentPoint.velocity_minor_ms",
        "CurrentPoint.speed_ms",
        "CurrentEvent.velocity_ms",
        "DatumLevel.value_m",
        "HistoricalOffsetVintage.publication_year",
        "HistoricalOffsetProvenance.annual_table_row",
        "HistoricalOffsetProvenance.printed_page",
        "HistoricalOffsetProvenance.pdf_page",
    ]
    value: float


@dataclass(frozen=True, slots=True)
class _MemberValue37:
    member_id: Literal["Station.type"]
    value: E.StationType


@dataclass(frozen=True, slots=True)
class _MemberValue38:
    member_id: Literal["Station.kind"]
    value: E.Kind | None


@dataclass(frozen=True, slots=True)
class _MemberValue39:
    member_id: Literal["Station.aliases"]
    value: Mapping[str, tuple[str, ...]]


@dataclass(frozen=True, slots=True)
class _MemberValue40:
    member_id: Literal["Station.status", "Tombstone.status"]
    value: E.StationStatus


@dataclass(frozen=True, slots=True)
class _MemberValue41:
    member_id: Literal["Station.recommended_set", "Station.constant_set"]
    value: ConstantSet | None


@dataclass(frozen=True, slots=True)
class _MemberValue42:
    member_id: Literal["Station.constant_sets"]
    value: tuple[ConstantSet, ...]


@dataclass(frozen=True, slots=True)
class _MemberValue43:
    member_id: Literal["Station.subordinate_offsets"]
    value: SubordinateOffsets | None


@dataclass(frozen=True, slots=True)
class _MemberValue44:
    member_id: Literal["Station.validation", "ConstantSet.validation"]
    value: tuple[Validation, ...]


@dataclass(frozen=True, slots=True)
class _MemberValue45:
    member_id: Literal[
        "Station.raw",
        "Tombstone.raw",
        "ConstantSet.raw",
        "Constituent.raw",
        "Convention.raw",
        "Licence.raw",
        "Provenance.raw",
        "Fallback.raw",
        "SourceRecord.provenance",
        "SourceRecord.original_metadata",
        "SourceRecord.raw",
        "HistoricalOffsetProvenance.id_crosswalk",
        "HistoricalOffsetProvenance.reference_binding",
    ]
    value: Mapping[str, _JsonValue]


@dataclass(frozen=True, slots=True)
class _MemberValue46:
    member_id: Literal["Station.recommended_is_fallback"]
    value: bool | None


@dataclass(frozen=True, slots=True)
class _MemberValue47:
    member_id: Literal["Station.source_records"]
    value: tuple[SourceRecord, ...]


@dataclass(frozen=True, slots=True)
class _MemberValue48:
    member_id: Literal["Tombstone.removed_reason"]
    value: E.RemovedReason


@dataclass(frozen=True, slots=True)
class _MemberValue49:
    member_id: Literal["ConstantSet.source_type"]
    value: E.SourceType


@dataclass(frozen=True, slots=True)
class _MemberValue50:
    member_id: Literal["ConstantSet.quantity"]
    value: E.Quantity


@dataclass(frozen=True, slots=True)
class _MemberValue51:
    member_id: Literal["ConstantSet.record_span"]
    value: RecordSpan | None


@dataclass(frozen=True, slots=True)
class _MemberValue52:
    member_id: Literal["ConstantSet.datum"]
    value: Datum | None


@dataclass(frozen=True, slots=True)
class _MemberValue53:
    member_id: Literal["ConstantSet.qc_status"]
    value: E.QcStatus


@dataclass(frozen=True, slots=True)
class _MemberValue54:
    member_id: Literal["ConstantSet.qc_flags", "SubordinateOffsets.qc_flags"]
    value: tuple[QcFlag, ...]


@dataclass(frozen=True, slots=True)
class _MemberValue55:
    member_id: Literal["ConstantSet.dropped_constituents"]
    value: tuple[DroppedConstituent, ...]


@dataclass(frozen=True, slots=True)
class _MemberValue56:
    member_id: Literal["ConstantSet.time_base"]
    value: TimeBase | None


@dataclass(frozen=True, slots=True)
class _MemberValue57:
    member_id: Literal["ConstantSet.convention"]
    value: Convention


@dataclass(frozen=True, slots=True)
class _MemberValue58:
    member_id: Literal["ConstantSet.licence"]
    value: Licence


@dataclass(frozen=True, slots=True)
class _MemberValue59:
    member_id: Literal["ConstantSet.provenance"]
    value: Provenance


@dataclass(frozen=True, slots=True)
class _MemberValue60:
    member_id: Literal["ConstantSet.constituents"]
    value: tuple[Constituent, ...]


@dataclass(frozen=True, slots=True)
class _MemberValue61:
    member_id: Literal["ConstantSet.constituent"]
    value: Constituent | None


@dataclass(frozen=True, slots=True)
class _MemberValue62:
    member_id: Literal["ConstantSet.fallback", "SubordinateOffsets.fallback"]
    value: Fallback | None


@dataclass(frozen=True, slots=True)
class _MemberValue63:
    member_id: Literal[
        "Constituent.amp_uncertainty_m",
        "Constituent.phase_uncertainty_deg",
        "Convention.utc_offset_hours",
        "Validation.reference_distance_km",
        "Validation.time_p95_min",
        "Validation.time_bias_min",
        "Validation.range_error_m",
        "SubordinateOffsets.time_offset_high_min",
        "SubordinateOffsets.time_offset_low_min",
        "SubordinateOffsets.height_offset_high",
        "SubordinateOffsets.height_offset_low",
        "Datum.msl_offset_m",
        "CurrentPoint.direction_deg",
        "CurrentEvent.direction_deg",
        "HeightSeries.datum_uncertainty_m",
        "ExtremeList.datum_uncertainty_m",
        "CurrentSeries.datum_uncertainty_m",
        "CurrentEventList.datum_uncertainty_m",
        "DatumInfo.msl_offset_m",
        "DatumLevel.above_chart_m",
        "DatumLevel.uncertainty_m",
        "Ranges.mn",
        "Ranges.gt",
        "Ranges.dhq",
        "Ranges.dlq",
    ]
    value: float | None


@dataclass(frozen=True, slots=True)
class _MemberValue64:
    member_id: Literal["Convention.phase_reference"]
    value: E.PhaseReference


@dataclass(frozen=True, slots=True)
class _MemberValue65:
    member_id: Literal["Convention.nodal_handling"]
    value: E.NodalHandling


@dataclass(frozen=True, slots=True)
class _MemberValue66:
    member_id: Literal["Convention.nodal_formula_ids"]
    value: Mapping[str, str | int] | None


@dataclass(frozen=True, slots=True)
class _MemberValue67:
    member_id: Literal[
        "Convention.canary",
        "Provenance.decision",
        "TimeBase.correction",
        "Validation.previous_release",
        "DatumLevel.epoch",
        "DatumLevel.data_span",
        "SourceRecord.original_harmonics",
    ]
    value: Mapping[str, _JsonValue] | None


@dataclass(frozen=True, slots=True)
class _MemberValue68:
    member_id: Literal["Provenance.input_sha256"]
    value: tuple[str, ...] | None


@dataclass(frozen=True, slots=True)
class _MemberValue69:
    member_id: Literal["Provenance.build"]
    value: ProvenanceBuild | None


@dataclass(frozen=True, slots=True)
class _MemberValue70:
    member_id: Literal[
        "ProvenanceBuild.built_at",
        "ProvenanceBuild.fetched_at",
        "HeightPoint.local_datetime",
        "HeightPoint.local_time_object",
        "Extreme.local_datetime",
        "Extreme.local_time_object",
        "CurrentPoint.local_datetime",
        "CurrentPoint.local_time_object",
        "CurrentEvent.local_datetime",
        "CurrentEvent.local_time_object",
    ]
    value: datetime | None


@dataclass(frozen=True, slots=True)
class _MemberValue71:
    member_id: Literal["ProvenanceBuild.tool_versions"]
    value: Mapping[str, str] | None


@dataclass(frozen=True, slots=True)
class _MemberValue72:
    member_id: Literal["TimeBase.code"]
    value: E.TimeBaseCode


@dataclass(frozen=True, slots=True)
class _MemberValue73:
    member_id: Literal["TimeBase.evidence", "HistoricalOffsetVintage.removal_events"]
    value: tuple[Mapping[str, _JsonValue], ...]


@dataclass(frozen=True, slots=True)
class _MemberValue74:
    member_id: Literal["QcFlag.flag"]
    value: E.QcFlagName


@dataclass(frozen=True, slots=True)
class _MemberValue75:
    member_id: Literal["QcFlag.values"]
    value: Mapping[str, float | None] | None


@dataclass(frozen=True, slots=True)
class _MemberValue76:
    member_id: Literal["DroppedConstituent.dropped_reason"]
    value: E.DroppedReason


@dataclass(frozen=True, slots=True)
class _MemberValue77:
    member_id: Literal["SubordinateOffsets.height_adjusted_type"]
    value: E.HeightAdjustedType


@dataclass(frozen=True, slots=True)
class _MemberValue78:
    member_id: Literal["SubordinateOffsets.source_type"]
    value: E.SourceType | None


@dataclass(frozen=True, slots=True)
class _MemberValue79:
    member_id: Literal["SubordinateOffsets.qc_status"]
    value: E.QcStatus | None


@dataclass(frozen=True, slots=True)
class _MemberValue80:
    member_id: Literal["SubordinateOffsets.vintage"]
    value: HistoricalOffsetVintage | None


@dataclass(frozen=True, slots=True)
class _MemberValue81:
    member_id: Literal["SubordinateOffsets.provenance"]
    value: HistoricalOffsetProvenance | None


@dataclass(frozen=True, slots=True)
class _MemberValue82:
    member_id: Literal["Datum.named"]
    value: Mapping[str, float] | None


@dataclass(frozen=True, slots=True)
class _MemberValue83:
    member_id: Literal[
        "Stats.type", "Stats.kind", "Stats.country", "Stats.source", "Stats.qc_status"
    ]
    value: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class _MemberValue84:
    member_id: Literal["AstroTable.valid_range"]
    value: tuple[int, int]


@dataclass(frozen=True, slots=True)
class _MemberValue85:
    member_id: Literal["Extreme.type"]
    value: E.ExtremeType


@dataclass(frozen=True, slots=True)
class _MemberValue86:
    member_id: Literal["CurrentEvent.type"]
    value: E.CurrentEventType


@dataclass(frozen=True, slots=True)
class _MemberValue87:
    member_id: Literal["HeightSeries.items"]
    value: tuple[HeightPoint, ...]


@dataclass(frozen=True, slots=True)
class _MemberValue88:
    member_id: Literal[
        "HeightSeries.method",
        "ExtremeList.method",
        "CurrentSeries.method",
        "CurrentEventList.method",
    ]
    value: E.PredictionMethod


@dataclass(frozen=True, slots=True)
class _MemberValue89:
    member_id: Literal["ExtremeList.items"]
    value: tuple[Extreme, ...]


@dataclass(frozen=True, slots=True)
class _MemberValue90:
    member_id: Literal["CurrentSeries.items"]
    value: tuple[CurrentPoint, ...]


@dataclass(frozen=True, slots=True)
class _MemberValue91:
    member_id: Literal["CurrentEventList.items"]
    value: tuple[CurrentEvent, ...]


@dataclass(frozen=True, slots=True)
class _MemberValue92:
    member_id: Literal["CurrentEventList.omitted_event_types"]
    value: tuple[E.CurrentEventType, ...] | None


@dataclass(frozen=True, slots=True)
class _MemberValue93:
    member_id: Literal["DatumInfo.levels"]
    value: tuple[DatumLevel, ...]


@dataclass(frozen=True, slots=True)
class _MemberValue94:
    member_id: Literal["Fallback.reason"]
    value: E.FallbackReason


@dataclass(frozen=True, slots=True)
class _MemberValue95:
    member_id: Literal["SourceRecord.role"]
    value: E.SourceRole


@dataclass(frozen=True, slots=True)
class _MemberValue96:
    member_id: Literal["SourceRecord.disposition"]
    value: E.SourceDisposition


_MemberValue: TypeAlias = (
    _MemberValue0
    | _MemberValue1
    | _MemberValue2
    | _MemberValue3
    | _MemberValue4
    | _MemberValue5
    | _MemberValue6
    | _MemberValue7
    | _MemberValue8
    | _MemberValue9
    | _MemberValue10
    | _MemberValue11
    | _MemberValue12
    | _MemberValue13
    | _MemberValue14
    | _MemberValue15
    | _MemberValue16
    | _MemberValue17
    | _MemberValue18
    | _MemberValue19
    | _MemberValue20
    | _MemberValue21
    | _MemberValue22
    | _MemberValue23
    | _MemberValue24
    | _MemberValue25
    | _MemberValue26
    | _MemberValue27
    | _MemberValue28
    | _MemberValue29
    | _MemberValue30
    | _MemberValue31
    | _MemberValue32
    | _MemberValue33
    | _MemberValue34
    | _MemberValue35
    | _MemberValue36
    | _MemberValue37
    | _MemberValue38
    | _MemberValue39
    | _MemberValue40
    | _MemberValue41
    | _MemberValue42
    | _MemberValue43
    | _MemberValue44
    | _MemberValue45
    | _MemberValue46
    | _MemberValue47
    | _MemberValue48
    | _MemberValue49
    | _MemberValue50
    | _MemberValue51
    | _MemberValue52
    | _MemberValue53
    | _MemberValue54
    | _MemberValue55
    | _MemberValue56
    | _MemberValue57
    | _MemberValue58
    | _MemberValue59
    | _MemberValue60
    | _MemberValue61
    | _MemberValue62
    | _MemberValue63
    | _MemberValue64
    | _MemberValue65
    | _MemberValue66
    | _MemberValue67
    | _MemberValue68
    | _MemberValue69
    | _MemberValue70
    | _MemberValue71
    | _MemberValue72
    | _MemberValue73
    | _MemberValue74
    | _MemberValue75
    | _MemberValue76
    | _MemberValue77
    | _MemberValue78
    | _MemberValue79
    | _MemberValue80
    | _MemberValue81
    | _MemberValue82
    | _MemberValue83
    | _MemberValue84
    | _MemberValue85
    | _MemberValue86
    | _MemberValue87
    | _MemberValue88
    | _MemberValue89
    | _MemberValue90
    | _MemberValue91
    | _MemberValue92
    | _MemberValue93
    | _MemberValue94
    | _MemberValue95
    | _MemberValue96
)


@dataclass(frozen=True, slots=True)
class _SuccessfulNoValue:
    member_id: Literal["Client.close"]


_ResultChannel: TypeAlias = _Absent | _MemberValue | _SuccessfulNoValue


@dataclass(frozen=True, slots=True)
class _AcceptanceDecision:
    accepted: bool
    mandatory_findings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ReleaseDescriptor:
    datestamp: str
    files: tuple[_JsonValue, ...]
    checksum_bytes: bytes | None
    pointer_digests: Mapping[str, str]
    required_file_request: _JsonValue | None
    metadata: _JsonValue


@dataclass(frozen=True, slots=True)
class _AstronomicalTerms:
    utc_year: int
    constituent_terms: tuple[_JsonValue, ...]
    epoch_hours: float


class _SchemafallbackRequired(TypedDict):
    reason: str
    basis: str
    otc_finding: str


class _Schemafallback(_SchemafallbackRequired, total=False):
    preferred_set_id: str


class _AuthenticatedIndexStationsItemSetsItemRequired(TypedDict):
    set_id: str | None
    source: str | None
    source_type: str | None
    quantity: str | None
    qc_status: str | None
    convention_id: str | None
    licence_id: str | None
    constituents: tuple[str, ...]
    fallback: _Schemafallback | None
    current_bins: tuple[int, ...]


class _AuthenticatedIndexStationsItemSetsItem(
    _AuthenticatedIndexStationsItemSetsItemRequired, total=False
):
    pass


class _SchemaqcFlagRequired(TypedDict):
    flag: str
    reason: str


class _SchemaqcFlag(_SchemaqcFlagRequired, total=False):
    values: Mapping[str, _JsonValue]


class _SchemahistoricalOffsetVintageRemovalEventsItemRequired(TypedDict):
    source_clock_timestamp: str
    name: str
    operation: Literal["Removed"]
    source_timezone: Literal[None]
    evidence_sha256: str


class _SchemahistoricalOffsetVintageRemovalEventsItem(
    _SchemahistoricalOffsetVintageRemovalEventsItemRequired, total=False
):
    pass


class _SchemahistoricalOffsetVintageRequired(TypedDict):
    publication_year: Literal[2020]
    source_lifecycle: Literal["retired"]
    removal_events: tuple[_SchemahistoricalOffsetVintageRemovalEventsItem, ...]
    current_validity: Literal["unestablished"]
    current_accuracy: Literal["unverified"]
    reference_2020_equivalence: str


class _SchemahistoricalOffsetVintage(
    _SchemahistoricalOffsetVintageRequired, total=False
):
    reference_2020_equivalence_sha256: str


class _SchemahistoricalOffsetProvenanceIdCrosswalkRequired(TypedDict):
    legacy_id: str
    status: Literal["inferred"]
    modern_alias_verified: Literal[False]
    evidence_sha256: tuple[str, ...]


class _SchemahistoricalOffsetProvenanceIdCrosswalk(
    _SchemahistoricalOffsetProvenanceIdCrosswalkRequired, total=False
):
    pass


class _SchemahistoricalOffsetProvenanceReferenceBindingRequired(TypedDict):
    noaa_id: str
    station_id: str
    mapping_status: Literal["primary_name_position"]
    evidence_sha256: tuple[str, ...]


class _SchemahistoricalOffsetProvenanceReferenceBinding(
    _SchemahistoricalOffsetProvenanceReferenceBindingRequired, total=False
):
    pass


class _SchemahistoricalOffsetProvenanceRequired(TypedDict):
    source_manifest_sha256: Literal[
        "667eec5b3fd25f99d46f24864766726094961d7db5fa104ca12450f3ecd0fdf7"
    ]
    input_sha256: tuple[str, ...]
    book: str
    annual_table_row: int
    printed_page: int
    pdf_page: int
    raw_row_text: str
    raw_values_json: str
    id_crosswalk: _SchemahistoricalOffsetProvenanceIdCrosswalk
    reference_binding: _SchemahistoricalOffsetProvenanceReferenceBinding
    acceptance_report_sha256: str


class _SchemahistoricalOffsetProvenance(
    _SchemahistoricalOffsetProvenanceRequired, total=False
):
    pass


class _SchemasubordinateOffsetsRequired(TypedDict):
    reference_station_id: str
    height_adjusted_type: str


class _SchemasubordinateOffsets(_SchemasubordinateOffsetsRequired, total=False):
    time_offset_high_min: float
    time_offset_low_min: float
    height_offset_high: float
    height_offset_low: float
    licence_id: str
    datum: Mapping[str, _JsonValue]
    offset_id: str
    source: str
    source_type: str
    source_version: str
    source_record_id: str
    qc_status: str
    qc_flags: tuple[_SchemaqcFlag, ...]
    fallback: _Schemafallback
    vintage: _SchemahistoricalOffsetVintage
    provenance: _SchemahistoricalOffsetProvenance


class _AuthenticatedIndexStationsItemCurrentOffsetsItemRequired(TypedDict):
    bin: int
    reference_bin: int
    reference_station_id: str | None
    licence_id: str | None


class _AuthenticatedIndexStationsItemCurrentOffsetsItem(
    _AuthenticatedIndexStationsItemCurrentOffsetsItemRequired, total=False
):
    pass


class _AuthenticatedIndexStationsItemRequired(TypedDict):
    station_id: str
    status: str
    name: str | None
    name_folded: str | None
    country: str | None
    type: str | None
    kind: str | None
    reference_station_id: str | None
    offsets_licence_id: str | None
    recommended_set_id: str | None
    lat: float | None
    lon: float | None
    offset: int
    length: int
    aliases: Mapping[str, tuple[str, ...]]
    sets: tuple[_AuthenticatedIndexStationsItemSetsItem, ...]
    subordinate_offsets: _SchemasubordinateOffsets | None
    current_offsets: tuple[_AuthenticatedIndexStationsItemCurrentOffsetsItem, ...]


class _AuthenticatedIndexStationsItem(
    _AuthenticatedIndexStationsItemRequired, total=False
):
    pass


class _AuthenticatedIndexRequired(TypedDict):
    index_version: Literal[1]
    discovery_index_version: Literal[1]
    datestamp: str
    jsonl: str
    jsonl_sha256: str
    jsonl_size: int
    by: str
    stations: tuple[_AuthenticatedIndexStationsItem, ...]


class _AuthenticatedIndex(_AuthenticatedIndexRequired, total=False):
    pass


class _CacheDocumentVariant0StationsItemSetsItemRequired(TypedDict):
    set_id: str | None
    source: str | None
    source_type: str | None
    quantity: str | None
    qc_status: str | None
    convention_id: str | None
    licence_id: str | None
    constituents: tuple[str, ...]
    fallback: _Schemafallback | None
    current_bins: tuple[int, ...]


class _CacheDocumentVariant0StationsItemSetsItem(
    _CacheDocumentVariant0StationsItemSetsItemRequired, total=False
):
    pass


class _CacheDocumentVariant0StationsItemCurrentOffsetsItemRequired(TypedDict):
    bin: int
    reference_bin: int
    reference_station_id: str | None
    licence_id: str | None


class _CacheDocumentVariant0StationsItemCurrentOffsetsItem(
    _CacheDocumentVariant0StationsItemCurrentOffsetsItemRequired, total=False
):
    pass


class _CacheDocumentVariant0StationsItemRequired(TypedDict):
    station_id: str
    status: str
    name: str | None
    name_folded: str | None
    country: str | None
    type: str | None
    kind: str | None
    reference_station_id: str | None
    offsets_licence_id: str | None
    recommended_set_id: str | None
    lat: float | None
    lon: float | None
    offset: int
    length: int
    aliases: Mapping[str, tuple[str, ...]]
    sets: tuple[_CacheDocumentVariant0StationsItemSetsItem, ...]
    subordinate_offsets: _SchemasubordinateOffsets | None
    current_offsets: tuple[_CacheDocumentVariant0StationsItemCurrentOffsetsItem, ...]


class _CacheDocumentVariant0StationsItem(
    _CacheDocumentVariant0StationsItemRequired, total=False
):
    pass


class _CacheDocumentVariant0Required(TypedDict):
    index_version: Literal[1]
    discovery_index_version: Literal[1]
    datestamp: str
    jsonl: str
    jsonl_sha256: str
    jsonl_size: int
    by: str
    stations: tuple[_CacheDocumentVariant0StationsItem, ...]


class _CacheDocumentVariant0(_CacheDocumentVariant0Required, total=False):
    pass


class _CacheDocumentVariant1FilesValueRequired(TypedDict):
    sha256: str
    size: int
    url: str | None


class _CacheDocumentVariant1FilesValue(
    _CacheDocumentVariant1FilesValueRequired, total=False
):
    pass


class _CacheDocumentVariant1Required(TypedDict):
    datestamp: str
    files: Mapping[str, _CacheDocumentVariant1FilesValue]
    format_version: str
    min_reader_version: str
    zenodo_version_doi: str | None
    verified_at: str
    by: str


class _CacheDocumentVariant1(_CacheDocumentVariant1Required, total=False):
    pass


@dataclass(frozen=True, slots=True)
class _LockState:
    cache_root: Path
    owner: _JsonValue | None
    held_token: str | None


@dataclass(frozen=True, slots=True)
class _CacheState:
    cache_root: Path
    release_candidates: tuple[str, ...]
    pointer_cache: _JsonValue | None
    lock_state: _LockState


@dataclass(frozen=True, slots=True)
class _CandidatePathVariant0:
    station: Station
    constant_set: ConstantSet
    release_view: Release


@dataclass(frozen=True, slots=True)
class _ReferencePath:
    station: Station
    release_view: Release
    constant_set: ConstantSet | None
    own_offset: _JsonValue | None
    reference_bin: int | None


@dataclass(frozen=True, slots=True)
class _CandidatePathVariant1:
    reference_path: _ReferencePath
    own_offset: _JsonValue


@dataclass(frozen=True, slots=True)
class _CandidatePathVariant2:
    reference_path: _ReferencePath
    own_current_offset: _JsonValue


@dataclass(frozen=True, slots=True)
class _CanonicalError:
    code: Literal[
        "invalid_argument",
        "network",
        "release_not_found",
        "offline_unavailable",
        "checksum_mismatch",
        "unsupported_format",
        "reader_too_old",
        "invalid_release",
        "cache",
        "io",
        "unsupported",
        "pinned_release",
        "buffer_too_small",
        "file_exists",
        "not_built",
        "station_not_found",
        "station_removed",
        "no_constants",
        "quantity_mismatch",
        "unsupported_convention",
        "no_astro_table",
        "unsupported_constituent",
        "time_out_of_range",
        "datum_unavailable",
        "reference_unavailable",
        "extremes_only",
        "historical_offsets_excluded",
        "bin_not_found",
        "local_time_unavailable",
        "unknown_time_zone",
    ]
    structured_fields: _JsonValue
    cause: Exception | None


@dataclass(frozen=True, slots=True)
class _EffectiveOptions:
    release: str | _Omitted = _OMITTED
    file: str | None | _Omitted = _OMITTED
    cache_dir: str | None | _Omitted = _OMITTED
    offline: bool | _Omitted = _OMITTED
    mode: E.Mode | _Omitted = _OMITTED
    base_url: str | _Omitted = _OMITTED
    timeout: float | None | _Omitted = _OMITTED
    proxy: str | None | _Omitted = _OMITTED
    ca_file: str | None | _Omitted = _OMITTED
    user_agent: str | None | _Omitted = _OMITTED
    on_network_error: E.OnNetworkError | _Omitted = _OMITTED
    auto_update: bool | _Omitted = _OMITTED
    update_interval: float | _Omitted = _OMITTED
    logger: logging.Logger | None | _Omitted = _OMITTED
    verify_on_open: bool | _Omitted = _OMITTED
    commercial_only: bool | _Omitted = _OMITTED
    commercial_basis: str | _Omitted = _OMITTED
    historical_offsets_policy: str | _Omitted = _OMITTED


@dataclass(frozen=True, slots=True)
class _ConstructorOptions:
    release: str
    file: str | None
    cache_dir: str | None
    offline: bool
    mode: E.Mode
    base_url: str | None
    timeout: float | None
    proxy: str | None
    ca_file: str | None
    user_agent: str | None
    on_network_error: E.OnNetworkError
    auto_update: bool
    update_interval: float | None
    logger: logging.Logger | None
    verify_on_open: bool
    commercial_only: bool
    commercial_basis: str
    historical_offsets_policy: str


@dataclass(frozen=True, slots=True)
class _ClientState:
    current_release: Release
    effective_options: _EffectiveOptions
    cache_state: _CacheState
    last_error: _JsonValue | None
    last_update_check: float | None
    closed: bool


@dataclass(frozen=True, slots=True)
class _ClientAndRelease:
    client_state: _ClientState
    loaded_release: Release


@dataclass(frozen=True, slots=True)
class _CommercialAdmission:
    admitted: bool
    reason: str | None


@dataclass(frozen=True, slots=True)
class _Scenario:
    behavior_ids: tuple[str, ...]
    input: _JsonValue
    expected_output: _JsonValue
    expected_error: _CanonicalError | None
    expected_state: _JsonValue


@dataclass(frozen=True, slots=True)
class _EvidenceBundle:
    scenario: _Scenario
    expected_result: _JsonValue
    actual_profile_results: _JsonValue
    red_output: str
    green_output: str


@dataclass(frozen=True, slots=True)
class _FieldContract:
    member_id: _AuxiliaryMemberId
    native_type: str
    nullable: bool
    required: bool


@dataclass(frozen=True, slots=True)
class _FormatSelection:
    formats: tuple[str, ...]
    required_files: tuple[_JsonValue, ...]


@dataclass(frozen=True, slots=True)
class _HistoricalAdmission:
    admitted: bool
    reason: str | None


@dataclass(frozen=True, slots=True)
class _HttpRequest:
    url: str
    conditional_etag: str | None


@dataclass(frozen=True, slots=True)
class _HttpResponse:
    status_code: int
    body: bytes
    etag: str | None
    request_url: str


@dataclass(frozen=True, slots=True)
class _IdentityQueryVariant1:
    system: str
    id: str


class _IndexEntrySetsItemRequired(TypedDict):
    set_id: str | None
    source: str | None
    source_type: str | None
    quantity: str | None
    qc_status: str | None
    convention_id: str | None
    licence_id: str | None
    constituents: tuple[str, ...]
    fallback: _Schemafallback | None
    current_bins: tuple[int, ...]


class _IndexEntrySetsItem(_IndexEntrySetsItemRequired, total=False):
    pass


class _IndexEntryCurrentOffsetsItemRequired(TypedDict):
    bin: int
    reference_bin: int
    reference_station_id: str | None
    licence_id: str | None


class _IndexEntryCurrentOffsetsItem(_IndexEntryCurrentOffsetsItemRequired, total=False):
    pass


class _IndexEntryRequired(TypedDict):
    station_id: str
    status: str
    name: str | None
    name_folded: str | None
    country: str | None
    type: str | None
    kind: str | None
    reference_station_id: str | None
    offsets_licence_id: str | None
    recommended_set_id: str | None
    lat: float | None
    lon: float | None
    offset: int
    length: int
    aliases: Mapping[str, tuple[str, ...]]
    sets: tuple[_IndexEntrySetsItem, ...]
    subordinate_offsets: _SchemasubordinateOffsets | None
    current_offsets: tuple[_IndexEntryCurrentOffsetsItem, ...]


class _IndexEntry(_IndexEntryRequired, total=False):
    pass


@dataclass(frozen=True, slots=True)
class _TransportOptions:
    offline: bool | _Omitted = _OMITTED
    base_url: str | _Omitted = _OMITTED
    timeout: float | None | _Omitted = _OMITTED
    proxy: str | None | _Omitted = _OMITTED
    ca_file: str | None | _Omitted = _OMITTED
    user_agent: str | None | _Omitted = _OMITTED


@dataclass(frozen=True, slots=True)
class _LockRequest:
    directory: Path
    operation: Literal[
        "take", "nonblocking_take", "release", "delete", "heartbeat", "ownership_check"
    ]
    token: str | None


@dataclass(frozen=True, slots=True)
class _LockOutcome:
    acquired: bool
    token: str | None
    owned: bool


@dataclass(frozen=True, slots=True)
class _LocalTimeProfile:
    tz: str | _Omitted = _OMITTED


class _MergedReceiptFilesValueRequired(TypedDict):
    sha256: str
    size: int
    url: str | None


class _MergedReceiptFilesValue(_MergedReceiptFilesValueRequired, total=False):
    pass


class _MergedReceiptRequired(TypedDict):
    datestamp: str
    files: Mapping[str, _MergedReceiptFilesValue]
    format_version: str
    min_reader_version: str
    zenodo_version_doi: str | None
    verified_at: str
    by: str


class _MergedReceipt(_MergedReceiptRequired, total=False):
    pass


@dataclass(frozen=True, slots=True)
class _MetadataRequest:
    request_url: str
    document_kind: str


@dataclass(frozen=True, slots=True)
class _PredictionWindow:
    start: float
    stop: float
    step: float | None
    instants: _JsonValue | None


@dataclass(frozen=True, slots=True)
class _InstantPredictionWindow:
    instants: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class _ProjectionContract:
    scalar_types: str
    models: str
    subordinate_offsets: str
    scope: str
    fallback: str


@dataclass(frozen=True, slots=True)
class _PublishedMetadata:
    contributors: _JsonValue
    year: int
    concept_doi: str | None
    zenodo_version_doi: str | None
    dataset_url: str


@dataclass(frozen=True, slots=True)
class _QualityAdmission:
    admitted: bool
    reason: str | None


_QueryOptions: TypeAlias = _Arguments8 | _Arguments9 | _Arguments10 | _Arguments11


@dataclass(frozen=True, slots=True)
class _ReaderVersion:
    major: int
    minor: int


@dataclass(frozen=True, slots=True)
class _PredictionModel:
    station: Station
    release_view: Release
    constant_set: ConstantSet
    convention: Convention
    astro_table: _JsonValue
    required_constituents: tuple[_JsonValue, ...]
    reference_bin: int | None
    mean_term: float
    datum_source: _JsonValue | None


@dataclass(frozen=True, slots=True)
class _RequiredLinks:
    conventions: Mapping[str, Convention]
    licences: Mapping[str, Licence]
    station_ids: tuple[str, ...]
    constituent_names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _StreamReader:
    release_view: Release
    file_descriptor: int
    index: _JsonValue
    index_presence: _JsonValue
    station_lru: _JsonValue
    closed: bool


@dataclass(frozen=True, slots=True)
class _ResultContext:
    station_id: str
    set_id: str | None
    reference_station_id: str | None
    bin_number: int | None
    datum: str | None
    release_datestamp: str
    algorithm: str


@dataclass(frozen=True, slots=True)
class _ScenarioComparison:
    accepted: bool
    mandatory_findings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _SelectionOptions:
    datum: str | None | _Omitted = _OMITTED
    set_id: str | None | _Omitted = _OMITTED
    offset_id: str | None | _Omitted = _OMITTED
    bin_number: int | None | _Omitted = _OMITTED
    commercial_only: bool | _Omitted = _OMITTED


@dataclass(frozen=True, slots=True)
class _SourceByteSpan:
    offset_bytes: int
    length_bytes: int


@dataclass(frozen=True, slots=True)
class _SourceFiles:
    jsonl: Path
    meta: Path
    jsonl_sha256: str
    jsonl_size: int
    meta_sha256: str
    meta_size: int


@dataclass(frozen=True, slots=True)
class _AuxiliaryValuesVariant0:
    station_request: Station | str
    release_view: Release
    selection_options: _SelectionOptions
    utc_instant: float | None


@dataclass(frozen=True, slots=True)
class _AuxiliaryValuesVariant1:
    raw_source_value: _JsonValue
    arguments: _JsonValue


class _StationIndexEntrySetsItemRequired(TypedDict):
    set_id: str | None
    source: str | None
    source_type: str | None
    quantity: str | None
    qc_status: str | None
    convention_id: str | None
    licence_id: str | None
    constituents: Sequence[str]
    fallback: _Schemafallback | None
    current_bins: Sequence[int]


class _StationIndexEntrySetsItem(_StationIndexEntrySetsItemRequired, total=False):
    pass


class _StationIndexEntryCurrentOffsetsItemRequired(TypedDict):
    bin: int
    reference_bin: int
    reference_station_id: str | None
    licence_id: str | None


class _StationIndexEntryCurrentOffsetsItem(
    _StationIndexEntryCurrentOffsetsItemRequired, total=False
):
    pass


class _StationIndexEntryRequired(TypedDict):
    station_id: str
    status: str
    name: str | None
    name_folded: str | None
    country: str | None
    type: str | None
    kind: str | None
    reference_station_id: str | None
    offsets_licence_id: str | None
    recommended_set_id: str | None
    lat: float | None
    lon: float | None
    offset: int
    length: int
    aliases: Mapping[str, Sequence[str]]
    sets: Sequence[_StationIndexEntrySetsItem]
    subordinate_offsets: _SchemasubordinateOffsets | None
    current_offsets: Sequence[_StationIndexEntryCurrentOffsetsItem]


class _StationIndexEntry(_StationIndexEntryRequired, total=False):
    pass


@dataclass(frozen=True, slots=True)
class _StationLookupVariant0:
    station: Station


@dataclass(frozen=True, slots=True)
class _StationLookupVariant1:
    tombstone: Tombstone


@dataclass(frozen=True, slots=True)
class _StationLookupVariant2:
    pass


@dataclass(frozen=True, slots=True)
class _SummaryOptions:
    original_recommendation: ConstantSet | None
    commercial_only: bool
    include_no_constants: bool


class _SuppliedIndexStationsItemSetsItemRequired(TypedDict):
    set_id: str | None
    source: str | None
    source_type: str | None
    quantity: str | None
    qc_status: str | None
    convention_id: str | None
    licence_id: str | None
    constituents: tuple[str, ...]
    fallback: _Schemafallback | None
    current_bins: tuple[int, ...]


class _SuppliedIndexStationsItemSetsItem(
    _SuppliedIndexStationsItemSetsItemRequired, total=False
):
    pass


class _SuppliedIndexStationsItemCurrentOffsetsItemRequired(TypedDict):
    bin: int
    reference_bin: int
    reference_station_id: str | None
    licence_id: str | None


class _SuppliedIndexStationsItemCurrentOffsetsItem(
    _SuppliedIndexStationsItemCurrentOffsetsItemRequired, total=False
):
    pass


class _SuppliedIndexStationsItemRequired(TypedDict):
    station_id: str
    status: str
    name: str | None
    name_folded: str | None
    country: str | None
    type: str | None
    kind: str | None
    reference_station_id: str | None
    offsets_licence_id: str | None
    recommended_set_id: str | None
    lat: float | None
    lon: float | None
    offset: int
    length: int
    aliases: Mapping[str, tuple[str, ...]]
    sets: tuple[_SuppliedIndexStationsItemSetsItem, ...]
    subordinate_offsets: _SchemasubordinateOffsets | None
    current_offsets: tuple[_SuppliedIndexStationsItemCurrentOffsetsItem, ...]


class _SuppliedIndexStationsItem(_SuppliedIndexStationsItemRequired, total=False):
    pass


class _SuppliedIndexRequired(TypedDict):
    index_version: Literal[1]
    discovery_index_version: Literal[1]
    datestamp: str
    jsonl: str
    jsonl_sha256: str
    jsonl_size: int
    by: str
    stations: tuple[_SuppliedIndexStationsItem, ...]


class _SuppliedIndex(_SuppliedIndexRequired, total=False):
    pass


@dataclass(frozen=True, slots=True)
class _TrustedCachedPointer:
    digests: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class _UnroundedCurrentEvent:
    root_seconds: float
    event_type: Literal[
        "max_flood", "max_ebb", "slack_before_flood", "slack_before_ebb"
    ]
    velocity_m_s: float
    direction_deg: float | None
    reference_order: int


@dataclass(frozen=True, slots=True)
class _UnroundedTideEvent:
    root_seconds: float
    event_type: Literal["high", "low"]
    height_m: float
    reference_order: int


@dataclass(frozen=True, slots=True)
class _ValidatedMetadata:
    document: _JsonValue
    selected_datestamp: str
    request_url: str
    files: tuple[_JsonValue, ...]


@dataclass(frozen=True, slots=True)
class _PresentError:
    member_id: _AuxiliaryMemberId
    error: _CanonicalError


@runtime_checkable
class _OriginIdentity(Protocol):
    """The genuine native identity token; it retains no producing data."""

    def __hash__(self) -> int: ...


@runtime_checkable
class _StationFieldsOwner(Protocol):
    @property
    def conventions(self) -> Mapping[str, Convention]: ...
    @property
    def licences(self) -> Mapping[str, Licence]: ...
    @property
    def kind(self) -> E.Kind | None: ...
    @property
    def recommendation(self) -> str | None: ...


@runtime_checkable
class _PreparedModel(Protocol):
    """Borrowed native reference selection; no acquisition or selection is replayed."""

    @property
    def native_sum(self) -> Sum: ...
    @property
    def native_table(self) -> AstroTable: ...
    @property
    def native_context(self) -> _Context: ...


@runtime_checkable
class _NativeFailureOwner(Protocol):
    @property
    def native_error(self) -> OpenTideConstantsError: ...


_ErrorChannel: TypeAlias = _Absent | _PresentError


_CAcceptanceDecision: TypeAlias = _AcceptanceDecision


_CAccessKind: TypeAlias = Literal["raw_record", "station_object"]


_CAcquisitionDescriptor: TypeAlias = _ReleaseDescriptor


_CActualProfileResults: TypeAlias = Mapping[str, _JsonValue]


_CArguments: TypeAlias = _MemberArguments


_CAstronomicalTerms: TypeAlias = _AstronomicalTerms


_CAttributionText: TypeAlias = str


_CAuthenticatedIndex: TypeAlias = _AuthenticatedIndex


_CAuxiliaryKind: TypeAlias = Literal["model_access", "result_context", "local_time"]


_CAuxiliaryModelValue: TypeAlias = _MemberValue


_CAuxiliaryOperation: TypeAlias = Literal[
    "astro_table",
    "datums",
    "ranges",
    "constituent",
    "constituents",
    "constituent_names",
    "convention",
    "conventions",
    "licence",
    "licences",
    "provenance",
    "set_validation",
    "station_validation",
    "valid_range",
    "equilibrium_argument",
    "equilibrium_for_year",
    "node_factor",
    "node_factor_for_year",
    "raw",
    "release_files",
    "release_metadata",
    "station_count",
    "tombstone_count",
    "subordinate_offsets",
]


_CAuxiliaryResult: TypeAlias = (
    _MemberValue | HeightSeries | ExtremeList | CurrentSeries | CurrentEventList
)


_CBoundChecksums: TypeAlias = Mapping[str, str]


_CCacheBytes: TypeAlias = bytes


_CCacheDocument: TypeAlias = (
    _CacheDocumentVariant0 | _CacheDocumentVariant1 | _JsonValue
)


_CCacheInventoryResult: TypeAlias = tuple[str, ...]


_CCacheState: TypeAlias = _CacheState


_CCandidatePath: TypeAlias = (
    _CandidatePathVariant0 | _CandidatePathVariant1 | _CandidatePathVariant2
)


_CCanonicalError: TypeAlias = _CanonicalError | _ErrorChannel


_CCanonicalResult: TypeAlias = _ResultChannel


_CCause: TypeAlias = Exception | None


_CChangedBehaviors: TypeAlias = tuple[str, ...]


_CChecksumBytes: TypeAlias = bytes


_CCitationStyle: TypeAlias = str


_CCitationText: TypeAlias = str


_CClientAndRelease: TypeAlias = _ClientAndRelease


_CClientState: TypeAlias = _ClientState


_CClock: TypeAlias = float


_CCommercialAdmission: TypeAlias = _CommercialAdmission


_CCommercialBasis: TypeAlias = Literal["strict", "as_published_upstream"]


_CCommercialOnly: TypeAlias = bool


_CComparedStationRow: TypeAlias = Mapping[str, _JsonValue]


_CCurrentCacheDirectory: TypeAlias = Path


_CCurrentRequest: TypeAlias = _MemberArguments


_CDestination: TypeAlias = Path


_CDirectCurrentResult: TypeAlias = CurrentSeries | CurrentEventList


_CDocumentKind: TypeAlias = Literal[
    "release", "station_row", "pointer", "catalogue", "cache"
]


_CDownloadResult: TypeAlias = tuple[str, ...]


_CEffectiveOptions: TypeAlias = _EffectiveOptions


_CEffectiveRecommendation: TypeAlias = ConstantSet | None


_CEnvironment: TypeAlias = Mapping[str, str]


_CEvidenceBundle: TypeAlias = _EvidenceBundle


_CExpectedResult: TypeAlias = _JsonValue


_CExplicitOptions: TypeAlias = _EffectiveOptions


@runtime_checkable
class _ConstantSetFieldsOwner(Protocol):
    @property
    def rows(self) -> tuple[Validation, ...]: ...
    @property
    def recommendation(self) -> str | None: ...
    @property
    def convention(self) -> Convention: ...
    @property
    def licence(self) -> Licence: ...


@runtime_checkable
class _SourceFieldsOwner(Protocol):
    @property
    def licences(self) -> Mapping[str, Licence]: ...


class _FileInfoRawFields(TypedDict):
    name: str
    url: str | None
    size: int | None
    sha256: str | None


@dataclass(frozen=True, slots=True)
class _FileInfoModelFields:
    raw_fields: _FileInfoRawFields


class _ReleaseInfoRawFields(TypedDict):
    datestamp: str
    format_version: str
    concept_doi: str | None
    zenodo_version_doi: str | None
    content_sha256: str | None


@dataclass(frozen=True, slots=True)
class _ReleaseInfoModelFields:
    raw_fields: _ReleaseInfoRawFields
    native_files: tuple[FileInfo, ...]
    native_min_reader_version: str | None


class _UpdateResultRawFields(TypedDict):
    updated: bool
    from_: str
    to: str


@dataclass(frozen=True, slots=True)
class _UpdateResultModelFields:
    raw_fields: _UpdateResultRawFields


class _NearbyRawFields(TypedDict):
    distance_km: float


@dataclass(frozen=True, slots=True)
class _NearbyModelFields:
    raw_fields: _NearbyRawFields
    native_station: Station


class _StatsRawFields(TypedDict):
    type: Mapping[str, int]
    kind: Mapping[str, int]
    country: Mapping[str, int]
    source: Mapping[str, int]
    qc_status: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class _StatsModelFields:
    raw_fields: _StatsRawFields


class _HeightPointRawFields(TypedDict):
    height_m: float
    local_time: str | None
    utc_offset_s: int | None


@dataclass(frozen=True, slots=True)
class _HeightPointModelFields:
    raw_fields: _HeightPointRawFields
    native_time: datetime
    native_local: datetime | None


class _ExtremeRawFields(TypedDict):
    type: E.ExtremeType
    height_m: float
    local_time: str | None
    utc_offset_s: int | None


@dataclass(frozen=True, slots=True)
class _ExtremeModelFields:
    raw_fields: _ExtremeRawFields
    native_time: datetime
    native_local: datetime | None


class _CurrentPointRawFields(TypedDict):
    velocity_major_ms: float
    velocity_minor_ms: float
    speed_ms: float
    direction_deg: float | None
    local_time: str | None
    utc_offset_s: int | None


@dataclass(frozen=True, slots=True)
class _CurrentPointModelFields:
    raw_fields: _CurrentPointRawFields
    native_time: datetime
    native_local: datetime | None


class _CurrentEventRawFields(TypedDict):
    type: E.CurrentEventType
    velocity_ms: float
    direction_deg: float | None
    local_time: str | None
    utc_offset_s: int | None


@dataclass(frozen=True, slots=True)
class _CurrentEventModelFields:
    raw_fields: _CurrentEventRawFields
    native_time: datetime
    native_local: datetime | None


class _HeightSeriesRawFields(TypedDict):
    station_id: str | None
    timezone: str | None
    method: E.PredictionMethod | None
    set_id: str | None
    convention_id: str | None
    astro_table_id: str | None
    reference_station_id: str | None
    reference_bin: int | None
    datum: str | None
    datum_name: str | None
    datum_kind: str | None
    datum_uncertainty_m: float | None
    tz: str | None
    tz_version: str | None
    release: str | None
    algorithm: str | None
    offset_id: str | None
    offset_source: str | None
    offset_source_version: str | None
    historical_offsets: bool
    current_validity: str | None
    current_accuracy: str | None
    reference_set_id: str | None
    reference_source_version: str | None
    reference_2020_equivalence: str | None
    source_note: str | None


@dataclass(frozen=True, slots=True)
class _HeightSeriesModelFields:
    raw_fields: _HeightSeriesRawFields
    native_items: tuple[HeightPoint, ...]


class _ExtremeListRawFields(TypedDict):
    station_id: str | None
    timezone: str | None
    method: E.PredictionMethod | None
    set_id: str | None
    convention_id: str | None
    astro_table_id: str | None
    reference_station_id: str | None
    reference_bin: int | None
    datum: str | None
    datum_name: str | None
    datum_kind: str | None
    datum_uncertainty_m: float | None
    tz: str | None
    tz_version: str | None
    release: str | None
    algorithm: str | None
    offset_id: str | None
    offset_source: str | None
    offset_source_version: str | None
    historical_offsets: bool
    current_validity: str | None
    current_accuracy: str | None
    reference_set_id: str | None
    reference_source_version: str | None
    reference_2020_equivalence: str | None
    source_note: str | None


@dataclass(frozen=True, slots=True)
class _ExtremeListModelFields:
    raw_fields: _ExtremeListRawFields
    native_items: tuple[Extreme, ...]


class _CurrentSeriesRawFields(TypedDict):
    station_id: str | None
    timezone: str | None
    method: E.PredictionMethod | None
    set_id: str | None
    convention_id: str | None
    astro_table_id: str | None
    reference_station_id: str | None
    reference_bin: int | None
    datum: str | None
    datum_name: str | None
    datum_kind: str | None
    datum_uncertainty_m: float | None
    bin_number: int | None
    tz: str | None
    tz_version: str | None
    release: str | None
    algorithm: str | None


@dataclass(frozen=True, slots=True)
class _CurrentSeriesModelFields:
    raw_fields: _CurrentSeriesRawFields
    native_items: tuple[CurrentPoint, ...]


class _CurrentEventListRawFields(TypedDict):
    station_id: str | None
    timezone: str | None
    method: E.PredictionMethod | None
    set_id: str | None
    convention_id: str | None
    astro_table_id: str | None
    reference_station_id: str | None
    reference_bin: int | None
    datum: str | None
    datum_name: str | None
    datum_kind: str | None
    datum_uncertainty_m: float | None
    bin_number: int | None
    omitted_event_types: tuple[E.CurrentEventType, ...] | None
    tz: str | None
    tz_version: str | None
    release: str | None
    algorithm: str | None


@dataclass(frozen=True, slots=True)
class _CurrentEventListModelFields:
    raw_fields: _CurrentEventListRawFields
    native_items: tuple[CurrentEvent, ...]


class _DatumInfoRawFields(TypedDict):
    set_id: str | None
    zero: str | None
    zero_name: str | None
    chart_datum: str | None
    msl_offset_m: float | None


@dataclass(frozen=True, slots=True)
class _DatumInfoModelFields:
    raw_fields: _DatumInfoRawFields
    native_levels: tuple[DatumLevel, ...]


class _DatumLevelRawFields(TypedDict):
    key: str | None
    value_m: float
    above_chart_m: float | None
    kind: str | None
    method: str | None
    source_name: str | None
    epoch: _JsonValue
    data_span: _JsonValue
    control_station_id: str | None
    control_set_id: str | None
    control_source_id: str | None
    uncertainty_m: float | None
    uncertainty_basis: str | None
    flags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _DatumLevelModelFields:
    raw_fields: _DatumLevelRawFields


class _RangesRawFields(TypedDict):
    mn: float | None
    gt: float | None
    dhq: float | None
    dlq: float | None


@dataclass(frozen=True, slots=True)
class _RangesModelFields:
    raw_fields: _RangesRawFields


class _NativeIndexEntryRequired(TypedDict):
    station_id: str
    status: str
    name: str | None
    name_folded: str | None
    country: str | None
    type: str | None
    kind: str | None
    reference_station_id: str | None
    offsets_licence_id: str | None
    recommended_set_id: str | None
    lat: float | None
    lon: float | None
    offset: int | None
    length: int | None
    aliases: Mapping[str, Sequence[str]]
    sets: Sequence[_StationIndexEntrySetsItem]
    subordinate_offsets: _SchemasubordinateOffsets | None
    current_offsets: Sequence[_StationIndexEntryCurrentOffsetsItem]


class _NativeIndexEntry(_NativeIndexEntryRequired, total=False):
    _index_presence: set[str] | frozenset[str]


class _ClientRawFields(TypedDict):
    _newer_format_major: int | None
    _closed: bool
    _historical_offsets_policy: str
    _pinned: str | None
    _mode: str
    _offline: bool
    _base_url: str
    _on_network_error: str
    _auto_update: bool
    _update_interval: float
    _verify_on_open: bool
    _commercial_only: bool
    _commercial_basis: str


@dataclass(frozen=True, slots=True)
class _ClientModelFields:
    raw_fields: _ClientRawFields
    native_log: logging.Logger
    native_lock: _thread.RLock
    native_release: Release | None
    native_loaded_from: E.LoadedFrom | None
    native_last_error: OpenTideConstantsError | None
    native_handed_out: weakref.WeakSet[Release]
    native_file: Path | None
    native_cache: Cache
    native_http: Http
    native_last_check: float


class _ReleaseRawFields(TypedDict):
    _historical_offsets_policy: str
    _commercial_only: bool
    _commercial_basis: str
    _mode: str
    _closed: bool
    _zenodo_version_doi: str | None


@dataclass(frozen=True, slots=True)
class _ReleaseModelFields:
    raw_fields: _ReleaseRawFields
    native_astro_cache: dict[str, AstroTable]
    native_meta: Mapping[str, _JsonValue]
    native_index_path: Path | None
    native_opened: tuple[Path, ...]
    native_release: Mapping[str, _JsonValue]
    native_files: tuple[FileInfo, ...]
    native_conventions: tuple[Convention, ...]
    native_licences: tuple[Licence, ...]
    native_conv_by_id: dict[str, Convention]
    native_lic_by_id: dict[str, Licence]
    native_effective: dict[str, str | None] | None
    native_entries: list[_NativeIndexEntry]
    native_by_id: dict[str, _NativeIndexEntry]
    native_tombs: dict[str, _NativeIndexEntry]
    native_alias: dict[str, dict[str, str]]
    native_subs: dict[str, list[str]]
    native_station_origin: _OriginIdentity
    native_stations: dict[str, Station] | None
    native_tomb_objs: dict[str, Tombstone] | None
    native_fh: BinaryIO | None
    native_lock: _thread.LockType
    native_lru: OrderedDict[str, Station]
    native_jsonl: Path | None
    native_constituent_names: tuple[str, ...] | None
    native_stats: Stats | None


_CFieldContract: TypeAlias = (
    tuple[_FieldContract, ...]
    | _StationFieldsOwner
    | _ConstantSetFieldsOwner
    | _SourceFieldsOwner
    | _FileInfoModelFields
    | _ReleaseInfoModelFields
    | _UpdateResultModelFields
    | _NearbyModelFields
    | _StatsModelFields
    | _HeightPointModelFields
    | _ExtremeModelFields
    | _CurrentPointModelFields
    | _CurrentEventModelFields
    | _HeightSeriesModelFields
    | _ExtremeListModelFields
    | _CurrentSeriesModelFields
    | _CurrentEventListModelFields
    | _DatumInfoModelFields
    | _DatumLevelModelFields
    | _RangesModelFields
    | _ClientModelFields
    | _ReleaseModelFields
)


_CFoldedHeightValues: TypeAlias = HeightSeries


_CFormatSelection: TypeAlias = _FormatSelection


_CHeightValues: TypeAlias = tuple[float, ...]


_CHeldRelease: TypeAlias = Release


_CHeldReleaseResult: TypeAlias = _MemberValue


_CHistoricalAdmission: TypeAlias = _HistoricalAdmission


_CHistoricalPolicy: TypeAlias = Literal["fallback", "exclude"]


_CHttpRequest: TypeAlias = _HttpRequest


_CHttpResponse: TypeAlias = _HttpResponse


_CIdentityQuery: TypeAlias = str | _IdentityQueryVariant1


_CIncludeFallback: TypeAlias = bool


_CIncludeFlagged: TypeAlias = bool


_CIncludeNoConstants: TypeAlias = bool


_CIndexEntry: TypeAlias = _IndexEntry


_CIndexPresence: TypeAlias = Mapping[str, bool]


_CInventoryAction: TypeAlias = Literal["list", "prune"]


_CIoKind: TypeAlias = Literal["lock", "http"]


_CIoOptions: TypeAlias = _LockState | _TransportOptions


_CIoRequest: TypeAlias = _LockRequest | _HttpRequest


_CIoResult: TypeAlias = _LockOutcome | _HttpResponse


_CKeep: TypeAlias = int


_CLifetimeAction: TypeAlias = str


_CLoadMode: TypeAlias = Literal["eager", "stream"]


_CLoadedRelease: TypeAlias = Release


_CLocalTimeProfile: TypeAlias = _LocalTimeProfile


_CLocalTimeResult: TypeAlias = _MemberValue


_CLockOutcome: TypeAlias = _LockOutcome


_CLockRequest: TypeAlias = _LockRequest


_CLockState: TypeAlias = _LockState


_CLockedCacheState: TypeAlias = _CacheState


@dataclass(frozen=True, slots=True)
class _AstroMemberContract:
    arguments: _Arguments26
    native_table: AstroTable

    @property
    def member_id(
        self,
    ) -> Literal["AstroTable.equilibrium_for_year", "AstroTable.node_factor_for_year"]:
        return self.arguments.member_id


_CMemberContract: TypeAlias = _MemberArguments | _AstroMemberContract


_CMergedReceipt: TypeAlias = _MergedReceipt


_CMetadataRequest: TypeAlias = _MetadataRequest


_CNativeProfile: TypeAlias = Literal[
    "python", "ruby", "typescript_node", "typescript_browser", "c", "swift"
]


_CNativeResult: TypeAlias = (
    OpenTideConstants
    | Release
    | E.LoadedFrom
    | OpenTideConstantsError
    | None
    | tuple[ReleaseInfo, ...]
    | ReleaseInfo
    | ReleaseInfo
    | None
    | int
    | None
    | UpdateResult
    | tuple[str, ...]
    | bool
    | str
    | datetime
    | str
    | None
    | Mapping[str, str]
    | tuple[FileInfo, ...]
    | tuple[Convention, ...]
    | Convention
    | None
    | tuple[Licence, ...]
    | Licence
    | None
    | Stats
    | int
    | Station
    | None
    | Station
    | Tombstone
    | None
    | tuple[Station, ...]
    | Iterator[Station]
    | tuple[Nearby, ...]
    | Nearby
    | None
    | HeightSeries
    | ExtremeList
    | CurrentSeries
    | CurrentEventList
    | DatumInfo
    | tuple[DatumInfo, ...]
    | Ranges
    | AstroTable
    | None
    | float
    | E.StationType
    | E.Kind
    | None
    | Mapping[str, tuple[str, ...]]
    | E.StationStatus
    | ConstantSet
    | None
    | tuple[ConstantSet, ...]
    | SubordinateOffsets
    | None
    | tuple[Validation, ...]
    | Mapping[str, _JsonValue]
    | bool
    | None
    | tuple[SourceRecord, ...]
    | E.RemovedReason
    | E.SourceType
    | E.Quantity
    | RecordSpan
    | None
    | Datum
    | None
    | E.QcStatus
    | tuple[QcFlag, ...]
    | tuple[DroppedConstituent, ...]
    | TimeBase
    | None
    | Convention
    | Licence
    | Provenance
    | tuple[Constituent, ...]
    | Constituent
    | None
    | Fallback
    | None
    | float
    | None
    | E.PhaseReference
    | E.NodalHandling
    | Mapping[str, str | int]
    | None
    | Mapping[str, _JsonValue]
    | None
    | tuple[str, ...]
    | None
    | ProvenanceBuild
    | None
    | datetime
    | None
    | Mapping[str, str]
    | None
    | E.TimeBaseCode
    | tuple[Mapping[str, _JsonValue], ...]
    | E.QcFlagName
    | Mapping[str, float | None]
    | None
    | E.DroppedReason
    | E.HeightAdjustedType
    | E.SourceType
    | None
    | E.QcStatus
    | None
    | HistoricalOffsetVintage
    | None
    | HistoricalOffsetProvenance
    | None
    | Mapping[str, float]
    | None
    | Mapping[str, int]
    | tuple[int, int]
    | E.ExtremeType
    | E.CurrentEventType
    | tuple[HeightPoint, ...]
    | E.PredictionMethod
    | tuple[Extreme, ...]
    | tuple[CurrentPoint, ...]
    | tuple[CurrentEvent, ...]
    | tuple[E.CurrentEventType, ...]
    | None
    | tuple[DatumLevel, ...]
    | E.FallbackReason
    | E.SourceRole
    | E.SourceDisposition
    | None
)


_COffsetCurrentResult: TypeAlias = CurrentEventList


_COffsetTideResult: TypeAlias = HeightSeries | ExtremeList


_COperation: TypeAlias = Literal[
    "astro_table",
    "attribution",
    "cached_releases",
    "check_for_update",
    "citation",
    "close",
    "constant_set",
    "constant_sets",
    "constituent",
    "constituent_names",
    "constituents",
    "convention",
    "conventions",
    "current_events",
    "currents",
    "datums",
    "download",
    "equilibrium_argument",
    "equilibrium_for_year",
    "extremes",
    "heights",
    "heights_at",
    "hold_release",
    "iter_stations",
    "last_error",
    "latest",
    "licence",
    "licences",
    "loaded_from",
    "near",
    "nearest",
    "newer_format_major",
    "node_factor",
    "node_factor_for_year",
    "open",
    "provenance",
    "prune",
    "ranges",
    "raw",
    "recommended_set",
    "reference_station",
    "release_files",
    "release_metadata",
    "releases",
    "require_station",
    "search",
    "set_validation",
    "station",
    "station_by_alias",
    "station_count",
    "station_validation",
    "stations",
    "stats",
    "subordinate_offsets",
    "subordinates_of",
    "to_local",
    "tombstone",
    "tombstone_count",
    "update",
    "valid_range",
    "verify",
]


_COrderedConstantSets: TypeAlias = tuple[ConstantSet, ...]


_COrderedFailures: TypeAlias = tuple[_CanonicalError, ...]


_COrderedStationResults: TypeAlias = tuple[Station, ...]


_COrigin: TypeAlias = _OpaqueOrigin | _OriginIdentity


_COriginalRecommendation: TypeAlias = ConstantSet | None


_COverwritePolicy: TypeAlias = tuple[str, ...]


_COwnCurrentOffsets: TypeAlias = _JsonValue | None


_COwnOffset: TypeAlias = SubordinateOffsets | None


_CParsedDocument: TypeAlias = Mapping[str, _JsonValue] | _JsonValue


_CPathRequest: TypeAlias = str


_CPlatformDefaults: TypeAlias = _EffectiveOptions


_CPointerDigests: TypeAlias = Mapping[str, str]


_CPredictionInstants: TypeAlias = tuple[float, ...]


_CPredictionResult: TypeAlias = (
    HeightSeries | ExtremeList | CurrentSeries | CurrentEventList
)


_CPredictionWindow: TypeAlias = _PredictionWindow | _InstantPredictionWindow


_CProjectionContract: TypeAlias = _ProjectionContract


_CPublishedMetadata: TypeAlias = _PublishedMetadata


_CQualityAdmission: TypeAlias = _QualityAdmission


_CQueryArguments: TypeAlias = _MemberArguments


_CQueryClientState: TypeAlias = _ClientState


_CQueryKind: TypeAlias = Literal[
    "stations", "iter_stations", "search", "near", "nearest"
]


_CQueryOptions: TypeAlias = _QueryOptions


_CRawFields: TypeAlias = (
    Mapping[str, _JsonValue]
    | _FileInfoRawFields
    | _ReleaseInfoRawFields
    | _UpdateResultRawFields
    | _NearbyRawFields
    | _StatsRawFields
    | _HeightPointRawFields
    | _ExtremeRawFields
    | _CurrentPointRawFields
    | _CurrentEventRawFields
    | _HeightSeriesRawFields
    | _ExtremeListRawFields
    | _CurrentSeriesRawFields
    | _CurrentEventListRawFields
    | _DatumInfoRawFields
    | _DatumLevelRawFields
    | _RangesRawFields
    | _ClientRawFields
    | _ReleaseRawFields
)


_CRawRecord: TypeAlias = Mapping[str, _JsonValue]


_CRawRecordOrValidStation: TypeAlias = _JsonValue | Station


_CReaderVersion: TypeAlias = _ReaderVersion


_CReferenceModel: TypeAlias = _PredictionModel


_CReferencePath: TypeAlias = _ReferencePath


_CReleaseCandidates: TypeAlias = tuple[str, ...]


_CReleaseFiles: TypeAlias = tuple[FileInfo, ...]


_CReleaseMetadata: TypeAlias = _JsonValue


_CReleaseOrigin: TypeAlias = _OpaqueOrigin


_CReleaseRequest: TypeAlias = Literal["latest"] | str


_CReleaseStatistics: TypeAlias = Stats


_CReleaseView: TypeAlias = Release


_CRequestedDatum: TypeAlias = str


_CRequiredFiles: TypeAlias = tuple[_JsonValue, ...]


_CRequiredLinks: TypeAlias = _RequiredLinks


_CResourceState: TypeAlias = _ClientState | Release | _StreamReader


_CResourceStateOrError: TypeAlias = _ClientState | Release | _StreamReader


_CResultContext: TypeAlias = _ResultContext


_CResultValues: TypeAlias = _MemberValue


_CReviewReports: TypeAlias = tuple[str, ...]


_CScenario: TypeAlias = _Scenario


_CScenarioComparison: TypeAlias = _ScenarioComparison


_CSelectedPredictionModel: TypeAlias = _PredictionModel


_CSelectedReferencePath: TypeAlias = _ReferencePath


_CSelectionKind: TypeAlias = Literal[
    "discovery", "explicit_prediction", "default_prediction"
]


_CSelectionOptions: TypeAlias = _SelectionOptions


_CSourceByteSpan: TypeAlias = _SourceByteSpan


_CSourceBytes: TypeAlias = bytes


_CSourceFiles: TypeAlias = _SourceFiles


_CSourceRecord: TypeAlias = Mapping[str, _JsonValue]


_CSourceValues: TypeAlias = _AuxiliaryValuesVariant0 | _AuxiliaryValuesVariant1


_CStation: TypeAlias = Station


_CStationId: TypeAlias = str


_CStationIndexEntry: TypeAlias = _StationIndexEntry


_CStationOrTombstoneOrNull: TypeAlias = (
    _StationLookupVariant0 | _StationLookupVariant1 | _StationLookupVariant2
)


_CStationRequest: TypeAlias = Station | str


_CStationSets: TypeAlias = tuple[ConstantSet, ...]


_CStationSourceRow: TypeAlias = Mapping[str, _JsonValue]


_CStationSummary: TypeAlias = Stats | tuple[ConstantSet, ...]


_CStep: TypeAlias = float | _Omitted


_CStreamReader: TypeAlias = _StreamReader


_CSummaryKind: TypeAlias = Literal["stats", "constant_sets"]


_CSummaryOptions: TypeAlias = _SummaryOptions


_CSuppliedIndex: TypeAlias = _SuppliedIndex | None


_CTideEvents: TypeAlias = ExtremeList


_CTideRequest: TypeAlias = _MemberArguments


_CTimeInputs: TypeAlias = _MemberArguments


_CTransportOptions: TypeAlias = _TransportOptions


_CTrustedCache: TypeAlias = _JsonValue | None


_CTrustedCachedPointer: TypeAlias = _TrustedCachedPointer | None


_CTypedModel: TypeAlias = (
    OpenTideConstants
    | Release
    | ReleaseInfo
    | FileInfo
    | Station
    | Tombstone
    | ConstantSet
    | Constituent
    | Convention
    | Licence
    | Provenance
    | ProvenanceBuild
    | TimeBase
    | QcFlag
    | DroppedConstituent
    | Validation
    | SubordinateOffsets
    | Nearby
    | UpdateResult
    | RecordSpan
    | Datum
    | Stats
    | AstroTable
    | HeightPoint
    | Extreme
    | CurrentPoint
    | CurrentEvent
    | HeightSeries
    | ExtremeList
    | CurrentSeries
    | CurrentEventList
    | DatumInfo
    | DatumLevel
    | Ranges
    | Fallback
    | SourceRecord
    | HistoricalOffsetVintage
    | HistoricalOffsetProvenance
)


_CUnroundedCurrentEvents: TypeAlias = tuple[_UnroundedCurrentEvent, ...]


_CUnroundedTideEvents: TypeAlias = tuple[_UnroundedTideEvent, ...]


_CUpdateRequest: TypeAlias = _MetadataRequest


_CUpdatedClientState: TypeAlias = _ClientState


_CUsableCachedReleaseOrError: TypeAlias = Release | _CanonicalError


_CUtcInstant: TypeAlias = float


_CUtcResult: TypeAlias = _MemberValue


_CValidStation: TypeAlias = Station


_CValidatedArguments: TypeAlias = _MemberArguments


_CValidatedMetadata: TypeAlias = _ValidatedMetadata


_CValidatedReleaseGraph: TypeAlias = _JsonValue


_CVerificationResult: TypeAlias = bool


_CVerifiedFileRows: TypeAlias = tuple[_JsonValue, ...]


_CWindowInputs: TypeAlias = _MemberArguments


_CAuxiliaryMemberId: TypeAlias = Literal[
    "Client.open",
    "Client.release",
    "Client.loaded_from",
    "Client.last_error",
    "Client.releases",
    "Client.latest",
    "Client.check_for_update",
    "Client.newer_format_major",
    "Client.update",
    "Client.download",
    "Client.verify",
    "Client.cached_releases",
    "Client.prune",
    "Release.datestamp",
    "Release.created",
    "Release.format_version",
    "Release.zenodo_version_doi",
    "Release.concept_doi",
    "Release.source_versions",
    "Release.build_commit",
    "Release.changelog_url",
    "Release.files",
    "Release.conventions",
    "Release.convention",
    "Release.licences",
    "Release.licence",
    "Release.constituent_names",
    "Release.stats",
    "Release.station_count",
    "Release.tombstone_count",
    "Release.citation",
    "Release.station",
    "Release.require_station",
    "Release.tombstone",
    "Release.station_by_alias",
    "Release.stations",
    "Release.iter_stations",
    "Release.search",
    "Release.near",
    "Release.nearest",
    "Release.reference_station",
    "Release.subordinates_of",
    "Release.attribution",
    "Release.heights",
    "Release.heights_at",
    "Release.extremes",
    "Release.currents",
    "Release.current_events",
    "Release.datums",
    "Release.ranges",
    "Release.astro_table",
    "Release.historical_offsets_policy",
    "ReleaseInfo.datestamp",
    "ReleaseInfo.format_version",
    "ReleaseInfo.concept_doi",
    "ReleaseInfo.zenodo_version_doi",
    "ReleaseInfo.content_sha256",
    "ReleaseInfo.files",
    "FileInfo.name",
    "FileInfo.url",
    "FileInfo.size",
    "FileInfo.sha256",
    "Station.station_id",
    "Station.name",
    "Station.country",
    "Station.lat",
    "Station.lon",
    "Station.type",
    "Station.kind",
    "Station.timezone",
    "Station.aliases",
    "Station.status",
    "Station.is_reference",
    "Station.is_subordinate",
    "Station.is_tide",
    "Station.is_current",
    "Station.recommended_set",
    "Station.constant_sets",
    "Station.constant_set",
    "Station.subordinate_offsets",
    "Station.validation",
    "Station.raw",
    "Station.recommended_is_fallback",
    "Station.source_records",
    "Tombstone.station_id",
    "Tombstone.name",
    "Tombstone.status",
    "Tombstone.removed_in",
    "Tombstone.removed_reason",
    "Tombstone.merged_into",
    "Tombstone.detail",
    "Tombstone.raw",
    "ConstantSet.set_id",
    "ConstantSet.source",
    "ConstantSet.source_type",
    "ConstantSet.quantity",
    "ConstantSet.source_record_id",
    "ConstantSet.source_version",
    "ConstantSet.record_span",
    "ConstantSet.datum",
    "ConstantSet.qc_status",
    "ConstantSet.qc_flags",
    "ConstantSet.dropped_constituents",
    "ConstantSet.time_base",
    "ConstantSet.is_recommended",
    "ConstantSet.convention",
    "ConstantSet.licence",
    "ConstantSet.provenance",
    "ConstantSet.validation",
    "ConstantSet.constituents",
    "ConstantSet.constituent",
    "ConstantSet.raw",
    "ConstantSet.fallback",
    "Constituent.name",
    "Constituent.source_name",
    "Constituent.doodson",
    "Constituent.speed_deg_per_hour",
    "Constituent.amplitude_m",
    "Constituent.phase_deg",
    "Constituent.amp_uncertainty_m",
    "Constituent.phase_uncertainty_deg",
    "Constituent.kept_reason",
    "Constituent.raw",
    "Convention.convention_id",
    "Convention.phase_reference",
    "Convention.utc_offset_hours",
    "Convention.v0_model",
    "Convention.nodal_handling",
    "Convention.nodal_formula_ids",
    "Convention.constituent_table_version",
    "Convention.tables_sha256",
    "Convention.canary",
    "Convention.raw",
    "Licence.licence_id",
    "Licence.spdx",
    "Licence.provider",
    "Licence.citation",
    "Licence.attribution",
    "Licence.url",
    "Licence.commercial_use",
    "Licence.restriction",
    "Licence.terms_url",
    "Licence.raw",
    "Provenance.adapter_version",
    "Provenance.input_sha256",
    "Provenance.selection_reason",
    "Provenance.decision",
    "Provenance.build",
    "Provenance.carried_from_release",
    "Provenance.raw",
    "ProvenanceBuild.build_commit",
    "ProvenanceBuild.built_at",
    "ProvenanceBuild.fetched_at",
    "ProvenanceBuild.run_id",
    "ProvenanceBuild.tool_versions",
    "TimeBase.code",
    "TimeBase.reason",
    "TimeBase.declared",
    "TimeBase.published",
    "TimeBase.correction",
    "TimeBase.months_dropped",
    "TimeBase.decided_in",
    "TimeBase.decided_build_commit",
    "TimeBase.evidence",
    "QcFlag.flag",
    "QcFlag.reason",
    "QcFlag.values",
    "DroppedConstituent.name",
    "DroppedConstituent.dropped_reason",
    "DroppedConstituent.detail",
    "Validation.set_id",
    "Validation.reference_source",
    "Validation.reference_station",
    "Validation.reference_distance_km",
    "Validation.window",
    "Validation.time_mae_min",
    "Validation.time_p95_min",
    "Validation.time_bias_min",
    "Validation.height_mae_m",
    "Validation.range_error_m",
    "Validation.missed_events",
    "Validation.extra_events",
    "Validation.previous_release",
    "SubordinateOffsets.reference_station_id",
    "SubordinateOffsets.time_offset_high_min",
    "SubordinateOffsets.time_offset_low_min",
    "SubordinateOffsets.height_offset_high",
    "SubordinateOffsets.height_offset_low",
    "SubordinateOffsets.height_adjusted_type",
    "SubordinateOffsets.licence_id",
    "SubordinateOffsets.offset_id",
    "SubordinateOffsets.source",
    "SubordinateOffsets.source_type",
    "SubordinateOffsets.source_version",
    "SubordinateOffsets.source_record_id",
    "SubordinateOffsets.qc_status",
    "SubordinateOffsets.qc_flags",
    "SubordinateOffsets.fallback",
    "SubordinateOffsets.vintage",
    "SubordinateOffsets.provenance",
    "Nearby.station",
    "Nearby.distance_km",
    "UpdateResult.updated",
    "UpdateResult.from",
    "UpdateResult.to",
    "RecordSpan.start",
    "RecordSpan.end",
    "RecordSpan.good_samples",
    "Datum.msl_offset_m",
    "Datum.named",
    "Stats.type",
    "Stats.kind",
    "Stats.country",
    "Stats.source",
    "Stats.qc_status",
    "AstroTable.equilibrium_argument",
    "AstroTable.node_factor",
    "AstroTable.equilibrium_for_year",
    "AstroTable.node_factor_for_year",
    "AstroTable.valid_range",
    "HeightPoint.time",
    "HeightPoint.height_m",
    "HeightPoint.local_time",
    "HeightPoint.utc_offset_s",
    "HeightPoint.local_datetime",
    "HeightPoint.local_time_object",
    "Extreme.time",
    "Extreme.type",
    "Extreme.height_m",
    "Extreme.local_time",
    "Extreme.utc_offset_s",
    "Extreme.local_datetime",
    "Extreme.local_time_object",
    "CurrentPoint.time",
    "CurrentPoint.velocity_major_ms",
    "CurrentPoint.velocity_minor_ms",
    "CurrentPoint.speed_ms",
    "CurrentPoint.direction_deg",
    "CurrentPoint.local_time",
    "CurrentPoint.utc_offset_s",
    "CurrentPoint.local_datetime",
    "CurrentPoint.local_time_object",
    "CurrentEvent.time",
    "CurrentEvent.type",
    "CurrentEvent.velocity_ms",
    "CurrentEvent.direction_deg",
    "CurrentEvent.local_time",
    "CurrentEvent.utc_offset_s",
    "CurrentEvent.local_datetime",
    "CurrentEvent.local_time_object",
    "HeightSeries.items",
    "HeightSeries.station_id",
    "HeightSeries.timezone",
    "HeightSeries.method",
    "HeightSeries.set_id",
    "HeightSeries.convention_id",
    "HeightSeries.astro_table_id",
    "HeightSeries.reference_station_id",
    "HeightSeries.reference_bin",
    "HeightSeries.datum",
    "HeightSeries.datum_name",
    "HeightSeries.datum_kind",
    "HeightSeries.datum_uncertainty_m",
    "HeightSeries.tz",
    "HeightSeries.tz_version",
    "HeightSeries.release",
    "HeightSeries.algorithm",
    "HeightSeries.to_local",
    "HeightSeries.offset_id",
    "HeightSeries.offset_source",
    "HeightSeries.offset_source_version",
    "HeightSeries.historical_offsets",
    "HeightSeries.current_validity",
    "HeightSeries.current_accuracy",
    "HeightSeries.reference_set_id",
    "HeightSeries.reference_source_version",
    "HeightSeries.reference_2020_equivalence",
    "HeightSeries.source_note",
    "ExtremeList.items",
    "ExtremeList.station_id",
    "ExtremeList.timezone",
    "ExtremeList.method",
    "ExtremeList.set_id",
    "ExtremeList.convention_id",
    "ExtremeList.astro_table_id",
    "ExtremeList.reference_station_id",
    "ExtremeList.reference_bin",
    "ExtremeList.datum",
    "ExtremeList.datum_name",
    "ExtremeList.datum_kind",
    "ExtremeList.datum_uncertainty_m",
    "ExtremeList.tz",
    "ExtremeList.tz_version",
    "ExtremeList.release",
    "ExtremeList.algorithm",
    "ExtremeList.to_local",
    "ExtremeList.offset_id",
    "ExtremeList.offset_source",
    "ExtremeList.offset_source_version",
    "ExtremeList.historical_offsets",
    "ExtremeList.current_validity",
    "ExtremeList.current_accuracy",
    "ExtremeList.reference_set_id",
    "ExtremeList.reference_source_version",
    "ExtremeList.reference_2020_equivalence",
    "ExtremeList.source_note",
    "CurrentSeries.items",
    "CurrentSeries.station_id",
    "CurrentSeries.timezone",
    "CurrentSeries.method",
    "CurrentSeries.set_id",
    "CurrentSeries.convention_id",
    "CurrentSeries.astro_table_id",
    "CurrentSeries.reference_station_id",
    "CurrentSeries.reference_bin",
    "CurrentSeries.datum",
    "CurrentSeries.datum_name",
    "CurrentSeries.datum_kind",
    "CurrentSeries.datum_uncertainty_m",
    "CurrentSeries.bin_number",
    "CurrentSeries.tz",
    "CurrentSeries.tz_version",
    "CurrentSeries.release",
    "CurrentSeries.algorithm",
    "CurrentSeries.to_local",
    "CurrentEventList.items",
    "CurrentEventList.station_id",
    "CurrentEventList.timezone",
    "CurrentEventList.method",
    "CurrentEventList.set_id",
    "CurrentEventList.convention_id",
    "CurrentEventList.astro_table_id",
    "CurrentEventList.reference_station_id",
    "CurrentEventList.reference_bin",
    "CurrentEventList.datum",
    "CurrentEventList.datum_name",
    "CurrentEventList.datum_kind",
    "CurrentEventList.datum_uncertainty_m",
    "CurrentEventList.bin_number",
    "CurrentEventList.omitted_event_types",
    "CurrentEventList.tz",
    "CurrentEventList.tz_version",
    "CurrentEventList.release",
    "CurrentEventList.algorithm",
    "CurrentEventList.to_local",
    "DatumInfo.set_id",
    "DatumInfo.zero",
    "DatumInfo.zero_name",
    "DatumInfo.chart_datum",
    "DatumInfo.msl_offset_m",
    "DatumInfo.levels",
    "DatumLevel.key",
    "DatumLevel.value_m",
    "DatumLevel.above_chart_m",
    "DatumLevel.kind",
    "DatumLevel.method",
    "DatumLevel.source_name",
    "DatumLevel.epoch",
    "DatumLevel.data_span",
    "DatumLevel.control_station_id",
    "DatumLevel.control_set_id",
    "DatumLevel.control_source_id",
    "DatumLevel.uncertainty_m",
    "DatumLevel.uncertainty_basis",
    "DatumLevel.flags",
    "Ranges.mn",
    "Ranges.gt",
    "Ranges.dhq",
    "Ranges.dlq",
    "Fallback.reason",
    "Fallback.basis",
    "Fallback.otc_finding",
    "Fallback.preferred_set_id",
    "Fallback.raw",
    "SourceRecord.source",
    "SourceRecord.source_version",
    "SourceRecord.source_record_id",
    "SourceRecord.role",
    "SourceRecord.disposition",
    "SourceRecord.detail",
    "SourceRecord.licence_id",
    "SourceRecord.upstream_licence_id",
    "SourceRecord.published_set_ids",
    "SourceRecord.provenance",
    "SourceRecord.original_metadata",
    "SourceRecord.original_harmonics",
    "SourceRecord.licence",
    "SourceRecord.upstream_licence",
    "SourceRecord.raw",
    "HistoricalOffsetVintage.publication_year",
    "HistoricalOffsetVintage.source_lifecycle",
    "HistoricalOffsetVintage.removal_events",
    "HistoricalOffsetVintage.current_validity",
    "HistoricalOffsetVintage.current_accuracy",
    "HistoricalOffsetVintage.reference_2020_equivalence",
    "HistoricalOffsetVintage.reference_2020_equivalence_sha256",
    "HistoricalOffsetProvenance.source_manifest_sha256",
    "HistoricalOffsetProvenance.input_sha256",
    "HistoricalOffsetProvenance.book",
    "HistoricalOffsetProvenance.annual_table_row",
    "HistoricalOffsetProvenance.printed_page",
    "HistoricalOffsetProvenance.pdf_page",
    "HistoricalOffsetProvenance.raw_row_text",
    "HistoricalOffsetProvenance.raw_values_json",
    "HistoricalOffsetProvenance.id_crosswalk",
    "HistoricalOffsetProvenance.reference_binding",
    "HistoricalOffsetProvenance.acceptance_report_sha256",
]


_CModelType: TypeAlias = Literal[
    "Client",
    "Release",
    "ReleaseInfo",
    "FileInfo",
    "Station",
    "Tombstone",
    "ConstantSet",
    "Constituent",
    "Convention",
    "Licence",
    "Provenance",
    "ProvenanceBuild",
    "TimeBase",
    "QcFlag",
    "DroppedConstituent",
    "Validation",
    "SubordinateOffsets",
    "Nearby",
    "UpdateResult",
    "RecordSpan",
    "Datum",
    "Stats",
    "AstroTable",
    "HeightPoint",
    "Extreme",
    "CurrentPoint",
    "CurrentEvent",
    "HeightSeries",
    "ExtremeList",
    "CurrentSeries",
    "CurrentEventList",
    "DatumInfo",
    "DatumLevel",
    "Ranges",
    "Fallback",
    "SourceRecord",
    "HistoricalOffsetVintage",
    "HistoricalOffsetProvenance",
]


_CCurrentOperation: TypeAlias = Literal["currents", "current_events"]
