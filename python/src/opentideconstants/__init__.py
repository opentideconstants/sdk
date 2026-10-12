"""OpenTideConstants: harmonic tidal constants for every station, from one open dataset.

    from opentideconstants import OpenTideConstants

    with OpenTideConstants() as otc:
        st = otc.station_by_alias("noaa", "9414290")     # None when no station has this alias
        if st is not None and st.recommended_set is not None:
            m2 = st.recommended_set.constituent("M2")   # None when the set has no M2

Import the names you use. ``from opentideconstants import *`` replaces the built-in FileExistsError in your
module with this package's FileExistsError (an error the API names, spec §4.8), so ``except FileExistsError``
no longer catches the OS error of ``os.mkdir`` or ``open(path, "x")``.

See https://opentideconstants.org. Code licence: MIT. Data licence: CC BY 4.0.
"""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ._predict._astro import AstroTable
    from ._predict._results import (HeightSeries, ExtremeList, CurrentSeries, CurrentEventList, HeightPoint, Extreme,
                                   CurrentPoint, CurrentEvent, DatumInfo, DatumLevel, Ranges)

from ._client import DEFAULT_BASE_URL, OpenTideConstants, __version__
from ._enums import (AliasSystem, CanaryStatus, DecisionOutcome, DecisionTier, DroppedReason, FallbackReason, Format,
                     HeightAdjustedType, Kind, LoadedFrom, Match, Mode, NodalHandling, OnNetworkError,
                     PhaseReference, QcFlagName, QcStatus, Quantity, RemovedReason, SourceType, StationStatus,
                     StationType, TimeBaseCode, SourceRole, SourceDisposition)
from ._errors import (CacheError, ChecksumError, FileError, FileExistsError, InvalidArgumentError,
                      InvalidReleaseError, NetworkError, OfflineError, OpenTideConstantsError, PinnedReleaseError,
                      ReaderTooOldError, ReleaseNotFoundError, StationNotFoundError, StationRemovedError, UnsupportedFormatError)
from ._models import (ConstantSet, Constituent, Convention, Datum, DroppedConstituent, Fallback, FileInfo, Licence, Nearby,
                      Provenance, ProvenanceBuild, QcFlag, RecordSpan, ReleaseInfo, Station, Stats, SubordinateOffsets,
                      TimeBase, Tombstone, UpdateResult, Validation, SourceRecord,
                      HistoricalOffsetVintage, HistoricalOffsetProvenance)
from ._release import SUPPORTED_FORMAT_MAJORS, SUPPORTED_FORMAT_VERSION, Release

CACHE_LAYOUT_VERSION = "v1"

__all__ = [
    # client and release
    "OpenTideConstants", "Release",
    # objects
    "ReleaseInfo", "FileInfo", "Station", "Tombstone", "ConstantSet", "Constituent", "Convention", "Licence",
    "Provenance", "ProvenanceBuild", "TimeBase", "QcFlag", "DroppedConstituent", "Validation",
    "SubordinateOffsets", "Nearby", "UpdateResult",
    "RecordSpan", "Datum", "Stats", "Fallback", "SourceRecord",
    "HistoricalOffsetVintage", "HistoricalOffsetProvenance",
    # enums
    "Kind", "StationType", "StationStatus", "RemovedReason", "SourceType", "Quantity", "QcStatus", "LoadedFrom",
    "PhaseReference",
    "NodalHandling", "CanaryStatus", "HeightAdjustedType", "DroppedReason", "QcFlagName", "TimeBaseCode",
    "DecisionTier",
    "DecisionOutcome", "AliasSystem", "Mode", "OnNetworkError", "Format", "Match", "FallbackReason",
    "SourceRole", "SourceDisposition",
    # errors
    "OpenTideConstantsError", "NetworkError", "ReleaseNotFoundError", "OfflineError", "ChecksumError",
    "UnsupportedFormatError", "ReaderTooOldError", "InvalidReleaseError", "StationNotFoundError",
    "StationRemovedError",
    "PinnedReleaseError", "CacheError", "FileExistsError", "FileError", "InvalidArgumentError",
    # prediction
    "AstroTable", "HeightSeries", "ExtremeList", "CurrentSeries", "CurrentEventList", "HeightPoint", "Extreme",
    "CurrentPoint", "CurrentEvent", "DatumInfo", "DatumLevel", "Ranges", "ExtremeType", "CurrentEventType",
    "PredictionMethod", "NoConstantsError", "QuantityMismatchError", "UnsupportedConventionError",
    "NoAstroTableError", "UnsupportedConstituentError", "TimeOutOfRangeError", "DatumUnavailableError",
    "BinNotFoundError", "ExtremesOnlyError", "LocalTimeUnavailableError", "UnknownTimeZoneError",
    "ReferenceUnavailableError",
    "HistoricalOffsetsExcludedError",
    # constants
    "SUPPORTED_FORMAT_MAJORS", "SUPPORTED_FORMAT_VERSION", "DEFAULT_BASE_URL", "CACHE_LAYOUT_VERSION", "__version__",
]

from ._errors import (NoConstantsError, QuantityMismatchError, UnsupportedConventionError, NoAstroTableError, UnsupportedConstituentError, TimeOutOfRangeError, DatumUnavailableError, BinNotFoundError, ExtremesOnlyError, LocalTimeUnavailableError, UnknownTimeZoneError, ReferenceUnavailableError, HistoricalOffsetsExcludedError)
from ._enums import ExtremeType, CurrentEventType, PredictionMethod

_PREDICTION_TYPES = ["AstroTable", "HeightSeries", "ExtremeList", "CurrentSeries", "CurrentEventList", "HeightPoint", "Extreme", "CurrentPoint", "CurrentEvent", "DatumInfo", "DatumLevel", "Ranges"]

def __getattr__(name):
    if name in _PREDICTION_TYPES:
        if name == 'AstroTable':
            from ._predict._astro import AstroTable
            value = AstroTable
        else:
            from ._predict import _results
            value = getattr(_results, name)
        globals()[name] = value
        return value
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')

def __dir__():
    return sorted(set(globals()) | set(_PREDICTION_TYPES))
