"""A fake opentideconstants package for the runner self-tests (see ../../README.md)."""
import os

MODE = os.environ.get("FAKE_SDK_MODE", "")
if MODE == "import-fails":
    raise ImportError("fake: the SDK does not import")
if MODE != "no-version":
    __version__ = "9.9.9-fake"


class _Error(Exception):
    code = "fake"

    def __init__(self, msg, code="fake", tombstone=None):
        super().__init__(msg)
        self.code = code
        self.tombstone = tombstone


if MODE != "no-error-class":
    OpenTideConstantsError = _Error


class _Tomb:
    station_id = "OTC-T-0005"
    name = "Old Pier"
    status = "removed"
    removed_in = "20991231"
    removed_reason = "duplicate"
    merged_into = "OTC-T-0001"
    # no detail: the runner cannot encode this tombstone


class _Release:
    datestamp = "20991231.2"
    format_version = "1.0"

    @property
    def station_count(self):
        return {"inf": float("inf"), "nan": float("nan"), "object": object()}.get(MODE, 20)

    @property
    def tombstone_count(self):
        if MODE == "raise":
            raise RuntimeError("not an SDK error")
        return 1

    def require_station(self, station_id):
        raise _Error("removed", code="station_removed", tombstone=_Tomb())

    def station(self, station_id):
        return None


class OpenTideConstants:
    def __init__(self, **kw):
        self.release = _Release()
        self.loaded_from = "file"
        self.last_error = None

    def station(self, station_id):
        return self.release.station(station_id)

    def require_station(self, station_id):
        return self.release.require_station(station_id)

    def subordinates_of(self, st):
        return []

    def close(self):
        if MODE == "close-raises":
            raise RuntimeError("close failed")
