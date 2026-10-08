"""SDK errors (spec §4.8). Every error class is a direct subclass of OpenTideConstantsError."""
from __future__ import annotations


class OpenTideConstantsError(Exception):
    """The base class of every SDK error. ``code`` is the stable error code."""

    code = "error"

    def __init__(self, message: str = "", **fields):
        super().__init__(message)
        for k, v in fields.items():
            setattr(self, k, v)


class NetworkError(OpenTideConstantsError):
    code = "network"

    def __init__(self, message: str = "", *, url: str | None = None, status: int | None = None):
        super().__init__(message, url=url, status=status)


class ReleaseNotFoundError(OpenTideConstantsError):
    code = "release_not_found"


class OfflineError(OpenTideConstantsError):
    code = "offline_unavailable"


class ChecksumError(OpenTideConstantsError):
    code = "checksum_mismatch"

    def __init__(self, message: str = "", *, file: str | None = None, expected: str | None = None,
                 actual: str | None = None):
        super().__init__(message, file=file, expected=expected, actual=actual)


class UnsupportedFormatError(OpenTideConstantsError):
    code = "unsupported_format"


class InvalidReleaseError(OpenTideConstantsError):
    code = "invalid_release"


class StationNotFoundError(OpenTideConstantsError):
    code = "station_not_found"


class StationRemovedError(OpenTideConstantsError):
    code = "station_removed"

    def __init__(self, message: str = "", *, tombstone=None):
        super().__init__(message, tombstone=tombstone)


class PinnedReleaseError(OpenTideConstantsError):
    code = "pinned_release"


class CacheError(OpenTideConstantsError):
    code = "cache"


class FileExistsError(OpenTideConstantsError):  # noqa: A001 - the name is part of the API (spec §4.8)
    code = "file_exists"

    def __init__(self, message: str = "", *, path: str | None = None):
        super().__init__(message, path=path)


class FileError(OpenTideConstantsError):
    code = "io"

    def __init__(self, message: str = "", *, path: str | None = None, cause: BaseException | None = None):
        super().__init__(message, path=path, cause=cause)


class InvalidArgumentError(OpenTideConstantsError):
    code = "invalid_argument"


ERROR_CLASSES = (
    NetworkError, ReleaseNotFoundError, OfflineError, ChecksumError, UnsupportedFormatError, InvalidReleaseError,
    StationNotFoundError, StationRemovedError, PinnedReleaseError, CacheError, FileExistsError, FileError,
    InvalidArgumentError,
)
