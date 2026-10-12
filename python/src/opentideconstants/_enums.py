"""Enumerated values (spec §3). Each enum is ``(str, Enum)`` with the schema's strings, plus OTHER for a
value that a newer format minor adds (spec §7.3)."""
from __future__ import annotations

from enum import Enum


class _StrEnum(str, Enum):
    def __str__(self) -> str:
        return self.value

    @classmethod
    def _missing_(cls, value):
        return cls.OTHER  # an unknown value from a newer minor format reads as "other"


class Kind(_StrEnum):
    TIDE = "tide"
    CURRENT = "current"
    OTHER = "other"


class StationType(_StrEnum):
    REFERENCE = "reference"
    SUBORDINATE = "subordinate"
    OTHER = "other"


class StationStatus(_StrEnum):
    ACTIVE = "active"
    REMOVED = "removed"
    OTHER = "other"


class SourceType(_StrEnum):
    OFFICIAL = "official"
    GAUGE = "gauge"
    MODEL = "model"
    OTHER = "other"


class Quantity(_StrEnum):
    WATER_LEVEL = "water_level"
    CURRENT = "current"
    OTHER = "other"


class RemovedReason(_StrEnum):
    MERGED = "merged"
    DUPLICATE = "duplicate"
    OTHER = "other"


class QcStatus(_StrEnum):
    OK = "ok"
    FLAGGED = "flagged"
    NO_CONSTANTS = "no_constants"
    OTHER = "other"


class TimeBaseCode(_StrEnum):
    VERIFIED = "verified"
    CORRECTED = "corrected"
    UNVERIFIED = "unverified"
    DISPUTED = "disputed"
    OTHER = "other"


class LoadedFrom(_StrEnum):
    DOWNLOAD = "download"
    CACHE = "cache"
    CACHE_AFTER_ERROR = "cache_after_error"
    FILE = "file"
    FILE_UNVERIFIED = "file_unverified"
    OTHER = "other"


class PhaseReference(_StrEnum):
    GREENWICH_UTC = "greenwich_utc"
    LOCAL = "local"
    OTHER = "other"


class NodalHandling(_StrEnum):
    F_U_AT_PREDICTION = "f_u_at_prediction"
    NONE = "none"
    OTHER = "other"


class CanaryStatus(_StrEnum):
    PASS = "pass"
    FAIL = "fail"
    NOT_APPLICABLE = "not_applicable"
    OTHER = "other"


class HeightAdjustedType(_StrEnum):
    R = "R"
    A = "A"
    OTHER = "other"


class DroppedReason(_StrEnum):
    RAYLEIGH = "rayleigh"
    NOISE = "noise"
    LONG_PERIOD_RULE = "long_period_rule"
    NON_TIDAL_RULE = "non_tidal_rule"
    CONVENTION = "convention"
    OTHER = "other"


class QcFlagName(_StrEnum):
    TIME_BASE = "time_base"
    BROKEN_RECORD = "broken_record"
    MICROTIDAL = "microtidal"
    NON_TIDAL_SIGNAL = "non_tidal_signal"
    SHORT_RECORD = "short_record"
    SIBLING_DISAGREEMENT = "sibling_disagreement"
    CARRIED_OVER = "carried_over"
    FALLBACK_TIME_BASE_DISPUTED = "fallback:time_base_disputed"
    FALLBACK_TIME_BASE_UNRESOLVED = "fallback:time_base_unresolved"
    FALLBACK_REFUSED_FIT = "fallback:refused_fit"
    FALLBACK_SHORT_RECORD_UNCALIBRATED = "fallback:short_record_uncalibrated"
    FALLBACK_SHORT_RECORD_LONG_PERIOD = "fallback:short_record_long_period"
    FALLBACK_PUBLISHED_FULL_LIST = "fallback:published_full_list"
    FALLBACK_RELIABILITY_WITHHELD = "fallback:reliability_withheld"
    FALLBACK_LICENCE_READING = "fallback:licence_reading"
    FALLBACK_DATUM_GATE_FAILED = "fallback:datum_gate_failed"
    FALLBACK_NOT_IN_OTC_INPUT = "fallback:not_in_otc_input"
    OTHER = "other"


class FallbackReason(_StrEnum):
    TIME_BASE_DISPUTED = "time_base_disputed"
    TIME_BASE_UNRESOLVED = "time_base_unresolved"
    REFUSED_FIT = "refused_fit"
    SHORT_RECORD_UNCALIBRATED = "short_record_uncalibrated"
    SHORT_RECORD_LONG_PERIOD = "short_record_long_period"
    PUBLISHED_FULL_LIST = "published_full_list"
    RELIABILITY_WITHHELD = "reliability_withheld"
    LICENCE_READING = "licence_reading"
    DATUM_GATE_FAILED = "datum_gate_failed"
    NOT_IN_OTC_INPUT = "not_in_otc_input"
    OTHER = "other"


class DecisionTier(_StrEnum):
    RULE = "rule"
    REVIEW = "review"
    FALLBACK = "fallback"
    OTHER = "other"


class DecisionOutcome(_StrEnum):
    ACCEPT = "accept"
    FALLBACK = "fallback"
    OTHER = "other"


class AliasSystem(_StrEnum):
    NOAA = "noaa"
    GESLA = "gesla"
    TICON = "ticon"
    XTIDE = "xtide"
    KARTVERKET = "kartverket"
    SLACKWATER = "slackwater"
    WEBCALTIDES = "webcaltides"
    LINZ = "linz"
    SHOM = "shom"
    PEGELONLINE = "pegelonline"
    RWS = "rws"
    MI = "mi"
    DMI = "dmi"
    SMHI = "smhi"
    FMI = "fmi"
    UHSLC = "uhslc"
    OTHER = "other"


class Mode(_StrEnum):
    EAGER = "eager"
    STREAM = "stream"
    OTHER = "other"


class OnNetworkError(_StrEnum):
    USE_CACHE = "use_cache"
    RAISE = "raise"
    OTHER = "other"


class Format(_StrEnum):
    JSON = "json"
    JSON_GZ = "json.gz"
    JSONL = "jsonl"
    OTHER = "other"


class Match(_StrEnum):
    EXACT = "exact"
    OTHER = "other"


# manifest enum name -> class (used by the API manifest check)
ENUMS = {
    "kind": Kind, "station_type": StationType, "station_status": StationStatus, "removed_reason": RemovedReason,
    "source_type": SourceType, "quantity": Quantity, "qc_status": QcStatus, "loaded_from": LoadedFrom,
    "phase_reference": PhaseReference, "nodal_handling": NodalHandling, "canary_status": CanaryStatus,
    "height_adjusted_type": HeightAdjustedType, "dropped_reason": DroppedReason, "qc_flag": QcFlagName,
    "fallback_reason": FallbackReason,
    "time_base_code": TimeBaseCode, "decision_tier": DecisionTier, "decision_outcome": DecisionOutcome, "alias_system": AliasSystem, "mode": Mode,
    "on_network_error": OnNetworkError, "format": Format, "match": Match,
}


def enum_or_raw(cls, value):
    """The enum member for a schema value; None stays None."""
    if value is None:
        return None
    if isinstance(value, str):
        return cls(value)
    return cls.OTHER


class ExtremeType(_StrEnum):
    HIGH = "high"
    LOW = "low"
    OTHER = "other"


class CurrentEventType(_StrEnum):
    MAX_FLOOD = "max_flood"
    MAX_EBB = "max_ebb"
    SLACK_BEFORE_FLOOD = "slack_before_flood"
    SLACK_BEFORE_EBB = "slack_before_ebb"
    OTHER = "other"


class PredictionMethod(_StrEnum):
    HARMONIC = "harmonic"
    FOLDED_OFFSETS = "folded_offsets"
    OFFSETS = "offsets"
    OTHER = "other"
