"""OpenTideConstants: harmonic tidal constants for every station, from one open dataset.

    from opentideconstants import OpenTideConstants

    with OpenTideConstants() as otc:
        st = otc.station_by_alias("noaa", "9414290")
        m2 = st.recommended_set.constituent("M2")

See https://opentideconstants.org. Code licence: MIT. Data licence: CC BY 4.0.
"""
from ._client import DEFAULT_BASE_URL, OpenTideConstants, __version__
from ._enums import (AliasSystem, CanaryStatus, DecisionOutcome, DecisionTier, DroppedReason, Format,
                     HeightAdjustedType, Kind, LoadedFrom, Match, Mode, NodalHandling, OnNetworkError,
                     PhaseReference, QcFlagName, QcStatus, Quantity, SourceType, StationStatus, StationType)
from ._errors import (CacheError, ChecksumError, FileError, FileExistsError, InvalidArgumentError,
                      InvalidReleaseError, NetworkError, OfflineError, OpenTideConstantsError, PinnedReleaseError,
                      ReleaseNotFoundError, StationNotFoundError, StationRemovedError, UnsupportedFormatError)
from ._models import (ConstantSet, Constituent, Convention, Datum, DroppedConstituent, FileInfo, Licence, Nearby,
                      Provenance, QcFlag, RecordSpan, ReleaseInfo, Station, Stats, SubordinateOffsets, Tombstone,
                      UpdateResult, Validation)
from ._release import SUPPORTED_FORMAT_MAJORS, Release

CACHE_LAYOUT_VERSION = "v1"

__all__ = [
    # client and release
    "OpenTideConstants", "Release",
    # objects
    "ReleaseInfo", "FileInfo", "Station", "Tombstone", "ConstantSet", "Constituent", "Convention", "Licence",
    "Provenance", "QcFlag", "DroppedConstituent", "Validation", "SubordinateOffsets", "Nearby", "UpdateResult",
    "RecordSpan", "Datum", "Stats",
    # enums
    "Kind", "StationType", "StationStatus", "SourceType", "Quantity", "QcStatus", "LoadedFrom", "PhaseReference",
    "NodalHandling", "CanaryStatus", "HeightAdjustedType", "DroppedReason", "QcFlagName", "DecisionTier",
    "DecisionOutcome", "AliasSystem", "Mode", "OnNetworkError", "Format", "Match",
    # errors
    "OpenTideConstantsError", "NetworkError", "ReleaseNotFoundError", "OfflineError", "ChecksumError",
    "UnsupportedFormatError", "InvalidReleaseError", "StationNotFoundError", "StationRemovedError",
    "PinnedReleaseError", "CacheError", "FileExistsError", "FileError", "InvalidArgumentError",
    # constants
    "SUPPORTED_FORMAT_MAJORS", "DEFAULT_BASE_URL", "CACHE_LAYOUT_VERSION", "__version__",
]
