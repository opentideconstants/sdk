"""SDK errors (spec §4.8). Every error class is a direct subclass of OpenTideConstantsError."""
from __future__ import annotations

import re

# The userinfo of a URL in free text: "scheme://" then everything up to the last "@" of the authority (spec §5.7,
# CR2 DR21). The authority ends at "/", "?", "#", white space or a quote, so a quoted repr() is handled too.
_USERINFO = re.compile(r"([A-Za-z][A-Za-z0-9+.\-]*://)[^/?#\s'\"<>]*@")


def redact_credentials(text: str) -> str:
    """``text`` with the user and password of every URL in it replaced by ``***`` (spec §5.7, CR2 DR21)."""
    return _USERINFO.sub(r"\1***@", text)


def redact_url(url) -> str:
    """One URL (a proxy may have no scheme) with its user and password replaced by ``***``, for a message."""
    s = str(url)
    if "://" not in s:
        head, at, tail = s.rpartition("@")
        return f"***@{tail}" if at and "/" not in head else s
    return redact_credentials(s)


class OpenTideConstantsError(Exception):
    """The base class of every SDK error. ``code`` is the stable error code. A URL in the message never carries
    its user and password (spec §5.7, CR2 DR21)."""

    code = "error"

    def __init__(self, message: str = "", **fields):
        super().__init__(redact_credentials(message) if isinstance(message, str) else message)
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


class ReaderTooOldError(OpenTideConstantsError):
    code = "reader_too_old"


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
    """The cache cannot be written. ``removed`` lists the datestamps that ``prune`` removed before the failure,
    newest first; it is empty for every other operation (spec §4.3, CR2 DR18)."""

    code = "cache"

    def __init__(self, message: str = "", *, removed: list[str] | None = None):
        super().__init__(message, removed=list(removed or []))


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
    NetworkError, ReleaseNotFoundError, OfflineError, ChecksumError, UnsupportedFormatError, ReaderTooOldError,
    InvalidReleaseError, StationNotFoundError, StationRemovedError, PinnedReleaseError, CacheError, FileExistsError,
    FileError, InvalidArgumentError,
)
