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


class QcStatus(_StrEnum):
    ACCEPTED = "accepted"
    FALLBACK = "fallback"
    EXCLUDED = "excluded"
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
    "kind": Kind, "station_type": StationType, "station_status": StationStatus, "source_type": SourceType,
    "quantity": Quantity, "qc_status": QcStatus, "loaded_from": LoadedFrom, "phase_reference": PhaseReference,
    "nodal_handling": NodalHandling, "canary_status": CanaryStatus, "height_adjusted_type": HeightAdjustedType,
    "dropped_reason": DroppedReason, "qc_flag": QcFlagName, "decision_tier": DecisionTier,
    "decision_outcome": DecisionOutcome, "alias_system": AliasSystem, "mode": Mode,
    "on_network_error": OnNetworkError, "format": Format, "match": Match,
}


def enum_or_raw(cls, value):
    """The enum member for a schema value; None stays None."""
    if value is None:
        return None
    if isinstance(value, str):
        return cls(value)
    return cls.OTHER
