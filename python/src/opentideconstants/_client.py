"""The client (spec §4.2, §4.3, §5): options, cache, HTTP and the current Release."""
from __future__ import annotations

import gzip
import _thread
import hashlib
import json
import logging
import math
import os
import re
import secrets
import threading
import time
import traceback
import weakref
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Sequence, Tuple
from urllib.parse import urljoin

from ._cache import DATESTAMP_RE, Cache, atomic_write, datestamp_key, default_root, ensure_dir, lock_dir, tmp_name
from ._cache_json import encode_cache_json
from ._enums import LoadedFrom
from ._errors import (CacheError, ChecksumError, FileError, FileExistsError, InvalidArgumentError,
                      InvalidReleaseError, NetworkError, OfflineError, OpenTideConstantsError, PinnedReleaseError,
                      ReaderTooOldError, ReleaseNotFoundError, UnsupportedFormatError, redact_credentials)
from ._http import TIMEOUT_MAX_S, TIMEOUT_MIN_S, Http, check_http_url
from ._models import FileInfo, Nearby, ReleaseInfo, Station, Tombstone, UpdateResult
from ._release import (SUPPORTED_FORMAT_MAJORS, SUPPORTED_FORMAT_VERSION, Release, _read_bytes, check_json_sha256,
                       file_sha256, load_document, meta_path_for, readable, version_key)

__version__ = "0.1.0"
SDK = f"opentideconstants-python/{__version__}"
DEFAULT_BASE_URL = "https://data.opentideconstants.org/"
FORMAT_EXT = {"json": ".json", "json.gz": ".json.gz", "jsonl": ".jsonl"}
_MODES = ("eager", "stream")
_ON_ERR = ("use_cache", "raise")


def _validate_offline_pointer(self: "OpenTideConstants"):
    if self._offline:
        raise OfflineError("offline: the latest pointer cannot be read")


def _validate_update_capability(self: "OpenTideConstants"):
    if self._pinned is not None or self._file is not None:
        raise PinnedReleaseError("this client was opened on a pinned release or a file")


def _major(fv) -> Optional[int]:
    k = version_key(fv)
    return None if k is None else k[0]


_SHA256_ROW = re.compile(rb"[0-9a-fA-F]{64}[ \t]+\*?\S")
# A .sha256 line (CR2 DR41): 64 hex digits, spaces or tabs, an optional "*", the name (to the end of the line, without
# trailing white space); or a blank line of ASCII white space only. Any other line is invalid_release.
_SHA256_LINE = re.compile(r"([0-9a-fA-F]{64})[ \t]+\*?(.*?[^ \t\r\n\v\f])[ \t\r\n\v\f]*")
_SHA256_BLANK = re.compile(r"[ \t\r\n\v\f]*")


def _has_sha256_row(data: bytes) -> bool:
    """True if a .sha256 body has at least one '<sha256>  <name>' row. A 200 body with none (a captive portal, a proxy
    page) is a network error, not a bad release (spec §5.2 step 5, CR2 DR13)."""
    return any(_SHA256_ROW.match(line.strip()) for line in data.splitlines())


def _parse_sha256(data: bytes, what: str = ".sha256"):
    """The rows of a .sha256 file: name -> digest. A file that is not UTF-8, or that names a file twice, is
    invalid_release, so that row order never decides a check (spec §5.3, CR2 DR14)."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as e:
        raise InvalidReleaseError(f"{what}: not UTF-8 ({e})") from e
    rows = {}
    # lines end at LF (a CR before it is white space); a line holds only ASCII white space, or is a row (CR2 DR41)
    for n, line in enumerate(text.split("\n"), 1):
        if _SHA256_BLANK.fullmatch(line):
            continue
        m = _SHA256_LINE.fullmatch(line)
        if not m:
            raise InvalidReleaseError(f"{what}: line {n} is not \"<sha256>  <name>\": {line[:100]!r}")
        name = m.group(2)
        if name in rows:
            raise InvalidReleaseError(f"{what}: {name} is listed twice")
        rows[name] = m.group(1).lower()
    return rows


def _need_rows(path: Path, opened, rows, sha_name: str) -> None:
    """A local open, and verify on it, needs a row for every release file it reads, checked before any file is
    hashed (spec §5.3, CR3 DR73); a .json.gz also needs the OTC_{D}.json row (CR3 DR77). A missing row is
    checksum_mismatch "not listed", with file naming it."""
    names = [p.name for p in opened]
    if path.name.endswith(".json.gz"):
        names.append(path.name[:-len(".gz")])
    for n in names:
        if n not in rows:
            raise ChecksumError(f"{n} is not listed in {sha_name}", file=str(path.with_name(n)), expected=None,
                                actual=None)


def _check_pointer_digests(pointer_digests, rows) -> None:
    for n, sha in rows.items():
        present = n in pointer_digests
        digest = pointer_digests.get(n)
        if not present:
            raise ChecksumError(f"{n} is in the .sha256 file but not in the pointer", file=n, expected=None,
                                actual=sha)
        if digest is not None and digest != sha:
            raise ChecksumError(f"{n}: the pointer and the .sha256 file disagree", file=n,
                                expected=sha, actual=digest)


def _require_stream_row(name, rows) -> None:
    if name not in rows:
        raise InvalidReleaseError(f"{name} is not in the .sha256 file")


def _authenticate_cached_files(paths, records, verify, check_file=None) -> None:
    for p in paths:
        rec = records.get(p.name) or {}
        size = rec.get("size")
        try:
            actual_size = p.stat().st_size
        except OSError as e:  # removed or unreadable since it was found: cache, never absent (spec §5.2)
            raise CacheError(f"cannot read {p}: {e}") from e
        if size is not None and actual_size != size:
            raise ChecksumError(f"{p.name}: size {actual_size} does not match {size}", file=str(p),
                                expected=rec.get("sha256"), actual=file_sha256(p))
        if verify:
            (OpenTideConstants._check_file if check_file is None else check_file)(p, rec.get("sha256"))


def _check_cached_manifest_bytes(sha_body, sha_path, digests) -> None:
    actual = hashlib.sha256(sha_body).hexdigest()
    for expected in digests:
        if expected != actual:
            raise ChecksumError(f"{sha_path.name}: SHA-256 {actual}, but the cached pointer lists {expected}",
                                file=str(sha_path), expected=expected, actual=actual)

def _split_file_name(name: str):
    """OTC_<D><ext> -> (D, ext), with D a valid datestamp; else (None, None) (spec §4.2, CR D18)."""
    for ext in (".json.gz", ".jsonl", ".json"):
        if name.startswith("OTC_") and name.endswith(ext) and DATESTAMP_RE.match(name[4:-len(ext)]):
            return name[4:-len(ext)], ext
    return None, None


def _rename_all_in(staged, log) -> Tuple[str, ...]:
    """Rename every checked temporary file into place, all or nothing (spec §4.3.2, CR2 DR17). ``staged`` is a list
    of (temporary file, destination). Each original that a new file replaces is first renamed aside to a
    ``.tmp-bak-`` name in the same folder. If any rename fails, every original is restored and the new files that
    were renamed in are removed, so the folder is as it was; FileError. If a restore fails too, the error lists the
    paths that changed. Returns the destinations."""
    aside = {}  # destination -> its original, renamed aside
    placed = []  # destinations a new file was renamed into
    dest = None
    try:
        for _tmp, dest in staged:
            if os.path.lexists(dest) and not (dest.is_dir() and not dest.is_symlink()):
                bak = dest.parent / f".tmp-bak-{os.getpid()}-{secrets.token_hex(6)}"
                os.replace(dest, bak)
                aside[dest] = bak
        for tmp, dest in staged:
            os.replace(tmp, dest)
            placed.append(dest)
    except OSError as e:
        changed = []
        for p in reversed(placed):
            try:
                if p in aside:
                    os.replace(aside[p], p)
                    del aside[p]
                else:
                    os.unlink(p)
            except OSError as x:
                log.warning("download: cannot restore %s: %s", p, x)
                changed.append(str(p))
        for p, bak in list(aside.items()):
            if str(p) in changed:
                continue
            try:
                os.replace(bak, p)
            except OSError as x:
                log.warning("download: cannot restore %s from %s: %s", p, bak, x)
                changed.append(str(p))
        msg = f"cannot write {dest}: {e}"
        if changed:
            msg += (f"; these paths changed and could not be restored: {', '.join(changed)} (an original that is "
                    f"not back is in a .tmp-bak- file next to it)")
        raise FileError(msg, path=str(dest), cause=e) from e
    for p, bak in aside.items():
        try:
            bak.unlink()
        except OSError as x:  # the new file is in place; only the old copy is left over
            log.warning("download: cannot remove %s (the replaced %s): %s", bak, p, x)
    return tuple(str(d) for _, d in staged)


def _check_user_agent(v) -> None:
    """user_agent is a string with no control characters (C0, DEL, C1) and only latin-1 characters, the ones an HTTP
    header can carry; otherwise invalid_argument at construction (spec §4.2, §5.7, CR2 DR20)."""
    if v is None:
        return
    if not isinstance(v, str):
        raise InvalidArgumentError(f"user_agent must be a string, not {type(v).__name__}")
    bad = next((c for c in v if ord(c) < 0x20 or 0x7F <= ord(c) <= 0x9F or ord(c) > 0xFF), None)
    if bad is not None:
        raise InvalidArgumentError(f"user_agent has a control or non-latin-1 character (U+{ord(bad):04X}): {v!r}")


def _flag(v) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "on")


def _auto_update_error(e: Exception) -> OpenTideConstantsError:
    """The last_error of an automatic update that failed (spec §5.6, CR2 DR5): an SDK error as it is; any other failure
    as an SDK error with the original as its cause: network for a transport failure, io for anything else (no new
    error code)."""
    if isinstance(e, OpenTideConstantsError):
        return e
    import http.client
    import socket
    import ssl
    import urllib.error
    msg = f"automatic update failed: {type(e).__name__}: {redact_credentials(str(e))}"
    if isinstance(e, (ConnectionError, TimeoutError, socket.gaierror, socket.herror, http.client.HTTPException,
                      ssl.SSLError, urllib.error.URLError)):
        err: OpenTideConstantsError = NetworkError(msg)
    else:
        err = FileError(msg, cause=e)
    err.__cause__ = e
    return err


def _validate_constructor_options(*, release="latest", file=None, offline=False, mode="eager",
                                  on_network_error="use_cache", auto_update=False, verify_on_open=False,
                                  commercial_only=False, commercial_basis="strict", historical_offsets_policy="fallback",
                                  timeout=None, update_interval: float | None=86_400):
    _validate_constructor_policy(release=release, offline=offline, mode=mode,
        on_network_error=on_network_error, auto_update=auto_update, verify_on_open=verify_on_open,
        commercial_only=commercial_only, commercial_basis=commercial_basis,
        historical_offsets_policy=historical_offsets_policy)
    _validate_constructor_file_and_timeout(release=release, file=file, offline=offline,
        on_network_error=on_network_error, timeout=timeout, update_interval=update_interval)


def _validate_constructor_policy(*, release, offline, mode, on_network_error, auto_update,
                                 verify_on_open, commercial_only, commercial_basis, historical_offsets_policy):
    if not isinstance(release, str) or (release != "latest" and not DATESTAMP_RE.match(release)):
        raise InvalidArgumentError(f"release must be 'latest' or a datestamp, not {release!r}")
    if mode not in _MODES:
        raise InvalidArgumentError(f"mode must be one of {_MODES}, not {mode!r}")
    if on_network_error not in _ON_ERR:
        raise InvalidArgumentError(f"on_network_error must be one of {_ON_ERR}, not {on_network_error!r}")
    for name, v in (("offline", offline), ("auto_update", auto_update), ("verify_on_open", verify_on_open),
                    ("commercial_only", commercial_only)):
        if not isinstance(v, bool):
            raise InvalidArgumentError(f"{name} must be a boolean")
    if not isinstance(commercial_basis, str) or commercial_basis not in ("strict", "as_published_upstream"):
        raise InvalidArgumentError(f"commercial_basis must be strict or as_published_upstream, not {commercial_basis!r}")
    if not isinstance(historical_offsets_policy, str) or historical_offsets_policy not in ('fallback', 'exclude'):
        raise InvalidArgumentError('historical_offsets_policy must be fallback or exclude')


def _validate_constructor_file_and_timeout(*, release, file, offline, on_network_error, timeout,
                                           update_interval: float | None):
    # A file client reads no pointer and opens no socket, so these options would be silently ignored (CR D31,
    # spec §4.2). The variable OPENTIDECONSTANTS_OFFLINE is not an option and does not conflict.
    if file is not None and (release != "latest" or offline or on_network_error != "use_cache"):
        raise InvalidArgumentError("file cannot be combined with release, offline or on_network_error")
    for name, v in (("timeout", timeout), ("update_interval", update_interval)):
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                              or v <= 0):
            raise InvalidArgumentError(f"{name} must be a positive finite number, not {v!r}")
    # 0.001 to 1e6 s in every SDK (spec §5.7, CR2 DR19): below 1 ms a timeout rounds to "none" in some HTTP clients
    if timeout is not None and not TIMEOUT_MIN_S <= timeout <= TIMEOUT_MAX_S:
        raise InvalidArgumentError(f"timeout must be from {TIMEOUT_MIN_S} to {TIMEOUT_MAX_S:g} seconds, not {timeout!r}")


def _resolve_constructor_defaults(*, offline, base_url, cache_dir, update_interval, environment,
                                 platform_cache_dir):
    """Existing pure defaults, using explicit caller-owned environment/platform values."""
    effective_offline = _constructor_offline(offline, environment)
    base = _constructor_base_url(base_url, environment)
    if cache_dir is None and any(environment.get(name) for name in
            ("OPENTIDECONSTANTS_CACHE_DIR", "LOCALAPPDATA", "XDG_CACHE_HOME")):
        platform_cache_dir = str(default_root(environment))
    root = _constructor_cache_root(cache_dir, platform_cache_dir)
    interval = _constructor_update_interval(update_interval)
    return effective_offline, base, root, interval


def _constructor_offline(offline, environment):
    return offline or _flag(environment.get("OPENTIDECONSTANTS_OFFLINE", ""))


def _constructor_base_url(base_url, environment):
    return base_url or environment.get("OPENTIDECONSTANTS_BASE_URL") or DEFAULT_BASE_URL


def _constructor_cache_root(cache_dir, platform_cache_dir):
    return cache_dir if cache_dir is not None else platform_cache_dir


def _constructor_update_interval(update_interval):
    return float(update_interval if update_interval is not None else 86_400)


def _validate_download_arguments(*, release, formats, overwrite, to):
    if not isinstance(release, str) or (release != "latest" and not DATESTAMP_RE.match(release)):
        raise InvalidArgumentError(f"release must be 'latest' or a datestamp, not {release!r}")
    if isinstance(formats, str) or not isinstance(formats, (list, tuple)) or not formats:
        raise InvalidArgumentError("formats must be a non-empty list")
    for f in formats:
        if f not in FORMAT_EXT:
            raise InvalidArgumentError(f"unknown format {f!r} (use json, json.gz or jsonl)")
    if not isinstance(overwrite, bool):
        raise InvalidArgumentError("overwrite must be a boolean")
    if not isinstance(to, (str, os.PathLike)):
        raise InvalidArgumentError("to must be a path")


def _validate_prune_arguments(keep):
    if isinstance(keep, bool) or not isinstance(keep, int) or keep < 0:
        raise InvalidArgumentError("keep must be a non-negative integer")


def _bind_client_fields_1(_receiver: "OpenTideConstants", *, log):
    _receiver._log = log


def _bind_client_fields_2(_receiver: "OpenTideConstants", *, lock):
    _receiver._lock = lock


def _bind_client_fields_3(_receiver: "OpenTideConstants", *, release, loaded_from, last_error, newer_format_major, closed):
    _receiver._release = release
    _receiver._loaded_from = loaded_from
    _receiver._last_error = last_error
    _receiver._newer_format_major = newer_format_major
    _receiver._closed = closed


def _bind_client_fields_4(_receiver: "OpenTideConstants", *, handed_out):
    _receiver._handed_out = handed_out


def _bind_client_fields_5(_receiver: "OpenTideConstants", *, historical_offsets_policy):
    _receiver._historical_offsets_policy = historical_offsets_policy


def _bind_client_fields_6(_receiver: "OpenTideConstants", *, pinned):
    _receiver._pinned = pinned


def _bind_client_fields_7(_receiver: "OpenTideConstants", *, file):
    _receiver._file = file


def _bind_client_fields_8(_receiver: "OpenTideConstants", *, mode):
    _receiver._mode = mode


def _bind_client_fields_9(_receiver: "OpenTideConstants", *, offline):
    _receiver._offline = offline


def _bind_client_fields_10(_receiver: "OpenTideConstants", *, base_url):
    _receiver._base_url = base_url


def _bind_client_fields_11(_receiver: "OpenTideConstants", *, cache):
    _receiver._cache = cache


def _bind_client_fields_12(_receiver: "OpenTideConstants", *, on_network_error, auto_update):
    _receiver._on_network_error = on_network_error
    _receiver._auto_update = auto_update


def _bind_client_fields_13(_receiver: "OpenTideConstants", *, update_interval):
    _receiver._update_interval = update_interval


def _bind_client_fields_14(_receiver: "OpenTideConstants", *, verify_on_open):
    _receiver._verify_on_open = verify_on_open


def _bind_client_fields_15(_receiver: "OpenTideConstants", *, commercial_only, commercial_basis):
    _receiver._commercial_only = commercial_only
    _receiver._commercial_basis = commercial_basis


def _bind_client_fields_16(_receiver: "OpenTideConstants", *, http):
    _receiver._http = http


def _bind_client_fields_17(_receiver: "OpenTideConstants", *, last_check):
    _receiver._last_check = last_check


class OpenTideConstants:
    """An OpenTideConstants client: ``OpenTideConstants()`` opens the latest release.

    Use ``with OpenTideConstants(...) as otc:`` or call ``close()``. Query methods are forwarded to the
    current Release (``otc.release``)."""

    _log: logging.Logger
    _lock: _thread.RLock
    _release: Release | None
    _loaded_from: LoadedFrom | None
    _last_error: OpenTideConstantsError | None
    _newer_format_major: int | None
    _closed: bool
    _handed_out: weakref.WeakSet[Release]
    _historical_offsets_policy: str
    _pinned: str | None
    _file: Path | None
    _mode: str
    _offline: bool
    _base_url: str
    _cache: Cache
    _on_network_error: str
    _auto_update: bool
    _update_interval: float
    _verify_on_open: bool
    _commercial_only: bool
    _commercial_basis: str
    _http: Http
    _last_check: float

    def __init__(self, *, release: str = "latest", file=None, cache_dir=None, offline: bool = False,
                 mode: str = "eager", base_url: Optional[str] = None, timeout=None, proxy=None, ca_file=None,
                 user_agent: Optional[str] = None, on_network_error: str = "use_cache", auto_update: bool = False,
                 update_interval=86_400, logger: Optional[logging.Logger] = None, verify_on_open: bool = False,
                 commercial_only: bool = False, commercial_basis: str = "strict",
                 historical_offsets_policy: str = "fallback"):
        _bind_client_fields_1(self, log=logger or logging.getLogger("opentideconstants"))
        _bind_client_fields_2(self, lock=threading.RLock())
        _bind_client_fields_3(self, release=None, loaded_from=None, last_error=None, newer_format_major=None, closed=False)
        _bind_client_fields_4(self, handed_out=weakref.WeakSet())
        _validate_constructor_policy(release=release, offline=offline, mode=mode,
                                      on_network_error=on_network_error, auto_update=auto_update,
                                      verify_on_open=verify_on_open, commercial_only=commercial_only,
                                      commercial_basis=commercial_basis, historical_offsets_policy=historical_offsets_policy)
        _bind_client_fields_5(self, historical_offsets_policy=historical_offsets_policy)
        _validate_constructor_file_and_timeout(release=release, file=file, offline=offline,
            on_network_error=on_network_error, timeout=timeout, update_interval=update_interval)
        _bind_client_fields_6(self, pinned=release if release != "latest" else None)
        _bind_client_fields_7(self, file=None if file is None else Path(file))
        _bind_client_fields_8(self, mode=mode)
        _bind_client_fields_9(self, offline=_constructor_offline(offline, os.environ))
        base = _constructor_base_url(base_url, os.environ)
        check_http_url("base_url", base)  # at construction, never retried (CR D19)
        _bind_client_fields_10(self, base_url=base if base.endswith("/") else base + "/")
        root = _constructor_cache_root(cache_dir, default_root() if cache_dir is None else cache_dir)
        _bind_client_fields_11(self, cache=Cache(Path(root), log=self._log))
        _bind_client_fields_12(self, on_network_error=on_network_error, auto_update=auto_update)
        _bind_client_fields_13(self, update_interval=_constructor_update_interval(update_interval))
        _bind_client_fields_14(self, verify_on_open=verify_on_open)
        # select only sets whose licence allows commercial use, in every release this client loads (spec §4.2,
        # K-NC DR106)
        _bind_client_fields_15(self, commercial_only=commercial_only, commercial_basis=commercial_basis)
        ua = f"opentideconstants-python/{__version__} (+https://opentideconstants.org)"
        _check_user_agent(user_agent)
        if user_agent:
            ua += " " + user_agent
        _bind_client_fields_16(self, http=Http(user_agent=ua, timeout=timeout, proxy=proxy, ca_file=ca_file, logger=self._log))
        if self._file is not None:
            self._open_file(self._file)
        elif self._pinned is not None:
            self._open_pinned(self._pinned)
        else:
            self._open_latest()
        _bind_client_fields_17(self, last_check=time.monotonic())

    # ------------------------------------------------------------------ context

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def close(self) -> None:
        """Close the client and every Release it made (stream mode holds a file handle). After close every
        query and release-management call is io "the release is closed" (spec §4.2, CR D21). A second close does
        nothing."""
        with self._lock:
            self._closed = True
            for r in list(self._handed_out):
                r._close()
            if self._release is not None:
                self._release._close()

    def _check_open(self) -> None:
        if self._closed:
            raise FileError("the release is closed")

    # ------------------------------------------------------------------ attributes

    @property
    def release(self) -> Release:
        self._maybe_auto_update()
        return self._release

    @property
    def loaded_from(self) -> LoadedFrom:
        return self._loaded_from

    @property
    def last_error(self) -> Optional[OpenTideConstantsError]:
        return self._last_error

    @property
    def newer_format_major(self) -> Optional[int]:
        """Set by check_for_update: the format major of OTC_latest.json when it is newer than every supported
        major, else None (spec §7.4)."""
        return self._newer_format_major

    # ------------------------------------------------------------------ opening

    def _set(self, rel: Release, loaded_from: str) -> None:
        old = self._release
        self._release = rel
        self._handed_out.add(rel)
        self._loaded_from = LoadedFrom(loaded_from)
        if old is not None and old is not rel:
            pass  # a Release the caller holds stays usable; it is closed with the client only if current

    def _open_file(self, path: Path) -> None:
        name = path.name
        d, ext = _split_file_name(name)
        if ext is None:
            raise InvalidArgumentError(f"file must be named OTC_<datestamp>.json, .json.gz or .jsonl, not {name!r}")
        if self._mode == "stream" and ext != ".jsonl":
            # a .json or .json.gz file has no lines to seek to: never load it eagerly in silence (CR T94, spec §4.2)
            raise InvalidArgumentError("stream mode needs .jsonl and .meta.json")
        if not path.exists():
            raise FileError(f"cannot open {path}: no such file", path=str(path))
        opened = [path] + ([meta_path_for(path)] if ext == ".jsonl" else [])
        for p in opened:
            if not p.exists():
                raise FileError(f"cannot open {p}: no such file", path=str(p))
        sha_path = path.with_name(f"OTC_{d}.sha256")
        json_sha256 = None
        if sha_path.exists():
            rows = _parse_sha256(_read_bytes(sha_path), sha_path.name)
            # every release file the open reads needs a row, before anything is hashed or loaded (spec §5.3, CR3
            # DR73), and a .json.gz also the .json row that its decompressed bytes are checked against (CR3 DR77)
            _need_rows(path, opened, rows, sha_path.name)
            for p in opened:
                self._check_file(p, rows.get(p.name))
            if ext == ".json.gz":
                json_sha256 = rows[f"OTC_{d}.json"]
            files = [FileInfo(n, None, (path.parent / n).stat().st_size if (path.parent / n).exists() else None, rows[n])
                     for n in sorted(rows)]
            lf = "file"
        else:
            files = [FileInfo(p.name, None, p.stat().st_size, None) for p in sorted(opened, key=lambda p: p.name)]
            lf = "file_unverified"
        rel = load_document(path, self._mode, files, commercial_only=self._commercial_only, commercial_basis=self._commercial_basis,
                            historical_offsets_policy=self._historical_offsets_policy, json_sha256=json_sha256)
        rel._opened = tuple(opened)
        self._set(rel, lf)

    @staticmethod
    def _check_file(p: Path, expected: Optional[str]) -> None:
        actual = file_sha256(p)
        if expected is None or actual != expected:
            raise ChecksumError(f"{p.name}: SHA-256 {actual} does not match {expected}", file=str(p),
                                expected=expected, actual=actual)

    def _url(self, name: str) -> str:
        return urljoin(self._base_url, name)

    # ---- the cache

    def _usable(self, datestamp: str, mode: str):
        """The data file to load from a verified cached release, or None."""
        v = self._cache.read_verified(datestamp)
        if v is None:
            return None
        d = self._cache.release_dir(datestamp)
        jsonl, meta, js = d / f"OTC_{datestamp}.jsonl", d / f"OTC_{datestamp}.meta.json", d / f"OTC_{datestamp}.json"
        stream_ok = jsonl.is_file() and meta.is_file()
        if mode == "stream":
            return jsonl if stream_ok else None
        if js.is_file():
            return js
        return jsonl if stream_ok else None

    def _cached_files(self, datestamp: str):
        v = self._cache.read_verified(datestamp) or {"files": {}}
        return [FileInfo(n, f.get("url"), f.get("size"), f.get("sha256")) for n, f in sorted(v["files"].items())]

    def _load_cached(self, datestamp: str, mode: str) -> Release:
        path = self._usable(datestamp, mode)
        if path is None:
            raise OfflineError(f"release {datestamp} is not in the cache")
        v = self._cache.read_verified(datestamp) or {"files": {}}
        d = self._cache.release_dir(datestamp)
        check = [path] + ([meta_path_for(path)] if path.name.endswith(".jsonl") else [])
        _authenticate_cached_files(check, v["files"], self._verify_on_open or mode == "stream", self._check_file)
        rel = load_document(path, mode, self._cached_files(datestamp),
                            index_path=d / "index-v1.json" if mode == "stream" else None,
                            index_sha256=(v["files"].get(path.name) or {}).get("sha256"),
                            commercial_only=self._commercial_only, commercial_basis=self._commercial_basis,
                            historical_offsets_policy=self._historical_offsets_policy)
        rel._zenodo_version_doi = v.get("zenodo_version_doi")
        rel._opened = tuple(check)
        return rel

    def _heal(self, datestamp: str, mode: str, e: Exception) -> None:
        """Remove a cached release that failed its size or SHA-256 check or does not parse (spec §5.2 step 6, §4.8):
        its .verified goes first, so it is no longer trusted, then the bad file (the one the check names, or the data
        files of this mode). A failure to delete is logged; it never hides the original error."""
        self._log.warning("cached release %s is corrupt (%s); it is removed from the cache", datestamp, e)
        d = self._cache.release_dir(datestamp)
        bad = getattr(e, "file", None)
        if bad:
            files = [d / Path(bad).name]  # only ever a file of this release's directory
        else:
            path = d / f"OTC_{datestamp}.json"
            if mode == "stream" or not path.is_file():
                path = d / f"OTC_{datestamp}.jsonl"
                files = [path, meta_path_for(path)]
            else:
                files = [path]
        for p in [d / ".verified"] + files:
            try:
                p.unlink()
            except FileNotFoundError:
                pass
            except OSError as ux:
                self._log.warning("cannot remove %s: %s", p, ux)

    def _load_cached_or_heal(self, datestamp: str, mode: str, info: Optional[ReleaseInfo]):
        """Load a cached release. One that fails its size or SHA-256 check or does not parse is healed (spec §5.2
        step 6), and, online, downloaded again. Returns (Release, loaded_from)."""
        try:
            return self._load_cached(datestamp, mode), "cache"
        except (ChecksumError, InvalidReleaseError) as e:
            self._heal(datestamp, mode, e)
            if self._offline:
                raise
            return self._download_to_cache(datestamp, mode, info), "download"

    def _note_entry(self, info: ReleaseInfo) -> None:
        """Keep the version DOI of a pointer or index entry in the .verified of that cached release (spec §4.3).
        An entry with no DOI does not erase a known one. The read-modify-write runs under the release lock, taken
        without waiting (spec §5.4, CR2 DR3): when another process holds a young lock, the note is skipped."""
        if info.zenodo_version_doi is None:
            return
        v = self._cache.read_verified(info.datestamp)
        if v is None or v.get("zenodo_version_doi") == info.zenodo_version_doi:
            return
        d = self._cache.release_dir(info.datestamp)
        try:
            with lock_dir(d, SDK, wait=False) as held:
                v = self._cache.read_verified(info.datestamp) if held else None
                if v is None or v.get("zenodo_version_doi") == info.zenodo_version_doi:
                    return
                v["zenodo_version_doi"] = info.zenodo_version_doi
                atomic_write(d / ".verified", encode_cache_json(v))
        except (OSError, CacheError) as e:
            self._log.warning("cannot update %s/.verified: %s", info.datestamp, e)

    def _cached_index_entries(self):
        """datestamp -> (format_version, min_reader_version) from the cached OTC_index.json, if any."""
        body = self._cache.read_pointer_body("OTC_index.json")
        try:
            doc = json.loads(body.decode("utf-8")) if body is not None else None
            return {e["datestamp"]: (e.get("format_version"), e.get("min_reader_version"))
                    for e in doc["releases"] if isinstance(e, dict) and isinstance(e.get("datestamp"), str)}
        except (ValueError, UnicodeDecodeError, KeyError, TypeError):
            return {}

    def _cached_candidates(self, mode: str):
        """The verified cached releases this SDK reads, newest first (spec §5.2 step 1): their format major and
        min_reader_version come from .verified or the cached index. A release with no recorded version is a
        candidate too; its own header is read when it is loaded (never guess, CR D9)."""
        index = None
        for ds in self._cache.cached():
            if self._usable(ds, mode) is None:
                continue
            v = self._cache.read_verified(ds) or {}
            fv, mr = v.get("format_version"), v.get("min_reader_version")
            if fv is None or mr is None:
                if index is None:
                    index = self._cached_index_entries()
                ifv, imr = index.get(ds, (None, None))
                fv, mr = fv or ifv, mr or imr
            if fv is not None and not readable(fv, mr):
                continue
            yield ds

    def _newest_cached(self, mode: str):
        """The newest cached release this SDK reads (spec §5.2 step 1), without loading it."""
        for ds in self._cached_candidates(mode):
            return ds
        return None

    def _load_newest_cached(self, mode: str):
        """Load the newest cached release this SDK reads (spec §5.2 steps 1, 5 and 6). A candidate that fails its
        check or does not parse is healed and the next older one is tried; one whose format this SDK cannot read is
        skipped. Returns the Release, or None when no candidate loads (the caller raises its original error)."""
        for ds in self._cached_candidates(mode):
            try:
                return self._load_cached(ds, mode)
            except (UnsupportedFormatError, ReaderTooOldError) as e:
                self._log.info("cached release %s is not readable: %s", ds, e)
            except (ChecksumError, InvalidReleaseError) as e:
                self._heal(ds, mode, e)
        return None

    # ---- pointer and index

    @staticmethod
    def _json_shape_ok(name: str, doc) -> bool:
        """The shape of a pointer (an object with a datestamp and a files array) or of the index (an object with a
        releases array). A wrong value inside a body of the right shape is invalid_release later (CR2 DR13)."""
        if not isinstance(doc, dict):
            return False
        if name == "OTC_index.json":
            return isinstance(doc.get("releases"), list)
        return "datestamp" in doc and isinstance(doc.get("files"), list)

    def _get_json_conditional(self, name: str):
        """GET a changing file (pointer or index) with If-None-Match; returns (doc, url) or None on 404.

        A 200 body is parsed and its shape checked before it is cached, so a body that is not JSON (a captive
        portal), or JSON of the wrong shape, never replaces a good cached copy; it is a network error (spec §5.2
        step 5, CR D8, CR2 DR13). A failure to write the cache is logged, not raised (CR D8)."""
        url = self._url(name)
        body, etag = self._cache.read_pointer(name)
        if etag and not all(0x20 <= ord(c) < 0x7F for c in etag):
            # a stored ETag that is not a valid header value is not sent (the server sends a 200 and a new one)
            self._log.warning("the cached ETag of %s is not a valid header value; not sending it", name)
            etag = None
        cached_doc = None
        if body is not None:
            try:
                cached_doc = json.loads(body.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                cached_doc = None
            if not self._json_shape_ok(name, cached_doc):
                # a broken stored copy is the same as none: no If-None-Match, so a 304 can never select it
                self._log.warning("cached %s is not JSON of the right shape; reading it again", name)
                self._cache.drop_pointer(name)
                body = cached_doc = None
        headers = {"If-None-Match": etag} if body is not None and etag else {}
        r = self._http.get(url, headers=headers, accept_gzip=True)
        if r.status == 304 and not headers:
            raise NetworkError(f"HTTP 304 for {url} with no If-None-Match", url=url, status=304)
        if r.status == 404:
            return None
        if r.status == 304:
            self._log.debug("pointer %s: 304", name)
            return cached_doc, url
        self._log.debug("pointer %s: 200", name)
        try:
            doc = json.loads(r.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            raise NetworkError(f"{url}: the 200 body is not JSON (a captive portal or a proxy page?)", url=url,
                               status=r.status) from e
        if not self._json_shape_ok(name, doc):
            raise NetworkError(f"{url}: the 200 body is JSON of the wrong shape (a proxy page?)", url=url,
                               status=r.status)
        try:
            ensure_dir(self._cache.root)
            self._cache.write_pointer(name, r.body, r.headers.get("etag"))
        except CacheError as e:
            self._log.warning("cannot cache %s: %s", name, e)
        return doc, url

    def _info(self, entry, url, what="the pointer") -> ReleaseInfo:
        ds = entry.get("datestamp") if isinstance(entry, dict) else None
        if not isinstance(ds, str) or not DATESTAMP_RE.match(ds):
            # a server-supplied datestamp names cache paths: never use one that is not a datestamp (spec §4.2, §5.4)
            raise InvalidReleaseError(f"{what}: bad datestamp {ds!r}")
        fv, mrv = entry.get("format_version"), entry.get("min_reader_version")
        if version_key(fv) is None or (mrv is not None and version_key(mrv) is None):
            # never guess a version (spec §7.4, CR D9)
            raise InvalidReleaseError(f"{what}: {ds}: format_version {fv!r} or min_reader_version {mrv!r} "
                                      f"is not MAJOR.MINOR")
        for f in entry.get("files") or ():
            # every file entry has a string sha256 and an integer size >= 0, as the schema requires (CR2 DR12)
            size = f.get("size") if isinstance(f, dict) else None
            if isinstance(f, dict) and (not isinstance(f.get("sha256"), str) or not isinstance(size, int)
                                        or isinstance(size, bool) or size < 0):
                raise InvalidReleaseError(f"{what}: {ds}: the entry for {f.get('name')!r} needs a string sha256 "
                                          f"and an integer size of 0 or more")
        try:
            files = tuple(sorted((FileInfo(f["name"], urljoin(url, f.get("url") or f["name"]), f["size"],
                                           f["sha256"].lower())
                                  for f in entry.get("files") or ()),
                                 key=lambda f: f.name))
            return ReleaseInfo(entry["datestamp"], entry.get("format_version"), entry.get("concept_doi"),
                               entry.get("zenodo_version_doi"), entry.get("content_sha256"), files,
                               entry.get("min_reader_version"))
        except (KeyError, TypeError, AttributeError) as e:
            raise InvalidReleaseError(f"{what}: bad entry: {e!r}") from e

    def _fetch_index(self) -> List[ReleaseInfo]:
        got = self._get_json_conditional("OTC_index.json")
        if got is None:
            raise ReleaseNotFoundError(f"{self._url('OTC_index.json')}: 404")
        doc, url = got
        return self._index_infos(doc, url)

    def _index_infos(self, doc, url):
        try:
            entries = doc["releases"]
        except (KeyError, TypeError) as e:
            raise InvalidReleaseError("OTC_index.json: releases is missing") from e
        if not isinstance(entries, list):
            raise InvalidReleaseError("OTC_index.json: releases is not a list")
        infos = [self._info(e, url, "OTC_index.json") for e in entries]
        return sorted(infos, key=lambda i: datestamp_key(i.datestamp), reverse=True)

    def _latest_info(self) -> ReleaseInfo:
        """The newest release this SDK reads (spec §5.2 steps 2 and 2a, §7.4): GET OTC_latest-f{MAJOR}.json,
        and OTC_latest.json only when that is a 404. When the pointer's release has an unsupported major or a
        min_reader_version that is too new, one GET of OTC_index.json picks the newest readable entry."""
        got = self._get_json_conditional(f"OTC_latest-f{max(SUPPORTED_FORMAT_MAJORS)}.json")
        if got is None:
            got = self._get_json_conditional("OTC_latest.json")
            if got is None:
                raise ReleaseNotFoundError(f"no latest pointer under {self._base_url}")
        doc, url = got
        info = self._info(doc, url)
        # a check that reaches the pointer clears last_error; loaded_from does not change (spec §4.3, CR2 DR4)
        self._last_error = None
        if readable(info.format_version, info._min_reader_version):
            return info
        if _major(info.format_version) not in SUPPORTED_FORMAT_MAJORS:
            self._log.warning("a newer format (%s) exists; upgrade opentideconstants to read it",
                              _major(info.format_version))
        try:
            infos = self._fetch_index()
        except ReleaseNotFoundError:
            infos = []
        for i in infos:
            if readable(i.format_version, i._min_reader_version):
                return i
        too_new = [i for i in [info] + list(infos) if _major(i.format_version) in SUPPORTED_FORMAT_MAJORS]
        if too_new:
            i = too_new[0]
            raise ReaderTooOldError(f"release {i.datestamp} needs a reader for format {i._min_reader_version}; "
                                    f"this SDK reads format {SUPPORTED_FORMAT_VERSION}")
        raise UnsupportedFormatError(f"no release with a supported format major {list(SUPPORTED_FORMAT_MAJORS)}")

    # ---- downloading into the cache (spec §5.2 step 4)

    def _get_sha256_rows(self, datestamp: str, info: Optional[ReleaseInfo] = None):
        """GET OTC_{D}.sha256 from the URL the pointer lists for it (spec §4.3.1), else from base_url, and check it
        against the pointer's own entry for it."""
        name = f"OTC_{datestamp}.sha256"
        listed = {f.name: f for f in info.files} if info is not None else {}
        url = listed[name].url if name in listed and listed[name].url else self._url(name)
        r = self._http.get(url)
        if r.status == 404:
            raise ReleaseNotFoundError(f"release {datestamp} not found ({url})")
        if not _has_sha256_row(r.body):
            # checked before the digest: a captive portal or a proxy page is the network, not a bad release (CR2 DR13)
            raise NetworkError(f"{url}: the 200 body has no '<sha256>  <name>' row (a captive portal or a proxy "
                               f"page?)", url=url, status=r.status)
        ent = listed.get(name)
        if ent is not None and ent.sha256 is not None and r.sha256 != ent.sha256:
            raise ChecksumError(f"{name}: SHA-256 {r.sha256} does not match the pointer's {ent.sha256}", file=name,
                                expected=ent.sha256, actual=r.sha256)
        return r.body, _parse_sha256(r.body, name)

    @staticmethod
    def _check_pointer(info: Optional[ReleaseInfo], rows) -> None:
        """The pointer and the .sha256 file must agree (spec §5.2 step 4.1): the same SHA-256 for every file both
        list, and no file in the .sha256 that the pointer does not list."""
        if info is None:
            return
        _check_pointer_digests({f.name: f.sha256 for f in info.files}, rows)


    def _fetch_file(self, url: str, dest_dir: Path, expected_sha: Optional[str], expected_size, final_name: str,
                    datestamp: str, gz: bool = False):
        """Download url to a temporary file in dest_dir, check size and SHA-256, return the temporary path. The file
        is one that OTC_{datestamp}.sha256 lists, so a 404 is a network error with status 404 (spec §4.8, CR D32)."""
        tmp = tmp_name(dest_dir)
        try:
            with open(tmp, "w+b") as f:
                r = self._http.get(url, accept_gzip=not gz, sink=f)
                if r.status == 404:
                    raise NetworkError(f"{url}: 404; file listed in OTC_{datestamp}.sha256 is missing on the server",
                                       url=url, status=404)
                f.flush()
                os.fsync(f.fileno())
            if (expected_size is not None and r.size != expected_size) or r.sha256 != expected_sha:
                raise ChecksumError(f"{final_name}: SHA-256 {r.sha256} (size {r.size}) does not match {expected_sha}",
                                    file=final_name, expected=expected_sha, actual=r.sha256)
            return tmp
        except BaseException:
            try:
                tmp.unlink()
            except FileNotFoundError:
                pass
            except OSError as e:  # a leftover temporary file is logged, never silent (R3-224)
                self._log.warning("cannot remove %s: %s", tmp, e)
            raise

    def _download_to_cache(self, datestamp: str, mode: str, info: Optional[ReleaseInfo]) -> Release:
        d = self._cache.release_dir(datestamp, create=True)
        with lock_dir(d, SDK, done=lambda: self._usable(datestamp, mode) is not None) as held:
            if not held or self._usable(datestamp, mode) is not None:
                return self._load_cached(datestamp, mode)
            sha_body, rows = self._get_sha256_rows(datestamp, info)
            self._check_pointer(info, rows)
            ptr = {f.name: f for f in info.files} if info is not None else {}
            base = f"OTC_{datestamp}"

            def url_of(n):
                return ptr[n].url if n in ptr and ptr[n].url else self._url(n)

            def size_of(n):
                return ptr[n].size if n in ptr else None

            wanted = []  # (final name, tmp path)
            written = {}
            try:
                if mode == "stream" or (f"{base}.json.gz" not in rows and f"{base}.json" not in rows):
                    for n in (f"{base}.jsonl", f"{base}.meta.json"):
                        _require_stream_row(n, rows)
                        tmp = self._fetch_file(url_of(n), d, rows[n], size_of(n), n, datestamp)
                        wanted.append((n, tmp))
                        written[n] = os.path.getsize(tmp)
                    data_name = f"{base}.jsonl"
                elif f"{base}.json.gz" in rows:
                    gzn, jn = f"{base}.json.gz", f"{base}.json"
                    if jn not in rows:
                        # the decoded .json must have its own row, or it is cached with no digest (CR2 DR15)
                        raise ChecksumError(f"{jn} is not listed in {base}.sha256", file=jn, expected=None, actual=None)
                    tmp_gz = self._fetch_file(url_of(gzn), d, rows[gzn], size_of(gzn), gzn, datestamp, gz=True)
                    wanted.append((gzn, tmp_gz))  # removed in the finally below if anything fails
                    try:
                        raw = gzip.decompress(Path(tmp_gz).read_bytes())
                    except (EOFError, zlib.error, gzip.BadGzipFile) as e:
                        raise InvalidReleaseError(f"{gzn}: not gzip") from e
                    wanted.pop()
                    try:
                        Path(tmp_gz).unlink()
                    except OSError as e:
                        self._log.warning("cannot remove %s: %s", tmp_gz, e)
                    import hashlib
                    actual = hashlib.sha256(raw).hexdigest()
                    if actual != rows[jn]:
                        raise ChecksumError(f"{jn}: SHA-256 {actual} does not match {rows[jn]}", file=jn,
                                            expected=rows[jn], actual=actual)
                    tmp = tmp_name(d)
                    wanted.append((jn, tmp))
                    with open(tmp, "wb") as f:
                        f.write(raw)
                        f.flush()
                        os.fsync(f.fileno())
                    written[jn] = len(raw)
                    data_name = jn
                else:
                    jn = f"{base}.json"
                    tmp = self._fetch_file(url_of(jn), d, rows[jn], size_of(jn), jn, datestamp)
                    wanted.append((jn, tmp))
                    written[jn] = os.path.getsize(tmp)
                    data_name = jn
                atomic_write(d / f"{base}.sha256", sha_body)
                for n, tmp in wanted:
                    os.replace(tmp, d / n)
                wanted = []
            except OSError as e:
                raise CacheError(f"cannot write the cache {d}: {e}") from e
            finally:
                for _, tmp in wanted:
                    try:
                        Path(tmp).unlink()
                    except FileNotFoundError:
                        pass
                    except OSError as e:  # R3-224
                        self._log.warning("cannot remove %s: %s", tmp, e)
            self._log.info("downloaded and verified %s", datestamp)
            # the files table of .verified (spec §5.4, CR3 DR100): a row only for a file that is present and
            # verified in the release directory, with its real size and lowercase SHA-256, and never one for the
            # .sha256 file. The rows of an earlier open in the other mode stay while their files are there.
            old = self._cache.read_verified(datestamp) or {"files": {}}
            files = {n: {"sha256": f["sha256"].lower(), "size": f["size"], "url": f.get("url")}
                     for n, f in (old.get("files") or {}).items()
                     if n != f"{base}.sha256" and f.get("sha256") is not None and (d / n).is_file()}
            for n, size in written.items():
                files[n] = {"sha256": rows[n], "size": size,
                            "url": ptr[n].url if n in ptr else (files.get(n) or {}).get("url")}
            # release.files (spec §4.3.1): the pointer entry for latest, else exactly the .verified rows
            if info is not None:
                files_infos = sorted(info.files, key=lambda f: f.name)
            else:
                files_infos = [FileInfo(n, f.get("url"), f.get("size"), f.get("sha256")) for n, f in sorted(files.items())]
            rel = load_document(d / data_name, mode, files_infos,
                                index_path=d / "index-v1.json" if mode == "stream" else None,
                                index_sha256=(files.get(data_name) or {}).get("sha256"),
                                commercial_only=self._commercial_only, commercial_basis=self._commercial_basis,
                                historical_offsets_policy=self._historical_offsets_policy)
            # a null DOI never erases a known one (CR2 DR11)
            zdoi = info.zenodo_version_doi if info is not None and info.zenodo_version_doi is not None \
                else old.get("zenodo_version_doi")
            rel._zenodo_version_doi = zdoi
            rel._opened = (d / data_name,) + ((d / f"{base}.meta.json",) if data_name.endswith(".jsonl") else ())
            verified = {"files": files, "verified_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "by": SDK, "datestamp": datestamp, "format_version": rel.format_version,
                        "min_reader_version": rel._release.get("min_reader_version"), "zenodo_version_doi": zdoi}
            try:
                atomic_write(d / ".verified", encode_cache_json(verified))
            except OSError as e:
                rel._close()  # the caller never gets it: give its file handle back now (R2-089)
                raise CacheError(f"cannot write {d / '.verified'}: {e}") from e
            return rel

    def _ensure_cache_root(self):
        ensure_dir(self._cache.base / "releases")

    def _open_pinned(self, datestamp: str) -> None:
        self._ensure_cache_root()
        if self._usable(datestamp, self._mode) is not None:
            self._set(*self._load_cached_or_heal(datestamp, self._mode, None))
            return
        if self._offline:
            raise OfflineError(f"offline, and release {datestamp} is not in the cache")
        self._set(self._download_to_cache(datestamp, self._mode, None), "download")

    def _open_latest(self) -> None:
        self._ensure_cache_root()
        if self._offline:
            rel = self._load_newest_cached(self._mode)
            if rel is None:
                raise OfflineError("offline, and no release is in the cache")
            self._set(rel, "cache")
            return
        try:
            info = self._latest_info()
            if self._usable(info.datestamp, self._mode) is not None:
                self._note_entry(info)
                self._set(*self._load_cached_or_heal(info.datestamp, self._mode, info))
                return
            self._set(self._download_to_cache(info.datestamp, self._mode, info), "download")
        except NetworkError as e:
            rel = self._load_newest_cached(self._mode) if self._on_network_error == "use_cache" else None
            if rel is None:
                raise
            self._log.warning("network error (%s); using the cached release %s", e, rel.datestamp)
            self._set(rel, "cache_after_error")
            self._last_error = e

    # ------------------------------------------------------------------ release management

    def releases(self) -> Tuple[ReleaseInfo, ...]:
        """Every release, newest first (OTC_index.json)."""
        self._check_open()
        if self._offline:
            body = self._cache.read_pointer_body("OTC_index.json")
            if body is None:
                raise OfflineError("offline, and the release index is not in the cache")
            try:
                doc = json.loads(body.decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as e:
                raise InvalidReleaseError("cached OTC_index.json: not JSON") from e
            return tuple(self._index_infos(doc, self._url("OTC_index.json")))
        try:
            infos = tuple(self._fetch_index())
        except NetworkError as e:
            body = self._cache.read_pointer_body("OTC_index.json") if self._on_network_error == "use_cache" else None
            if body is None:
                raise
            try:
                doc = json.loads(body.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                raise e from None
            self._log.warning("network error (%s); using the cached release index", e)
            return tuple(self._index_infos(doc, self._url("OTC_index.json")))
        for i in infos:
            self._note_entry(i)
        return infos

    def latest(self) -> ReleaseInfo:
        """The latest release this SDK reads. It reads the latest pointer (OTC_latest-f{MAJOR}.json, or
        OTC_latest.json when that is a 404) with a conditional GET, and OTC_index.json too when the pointer's
        release is not readable by this SDK (spec §5.2 steps 2 and 2a, CR D23). It does not switch releases."""
        self._check_open()
        _validate_offline_pointer(self)
        return self._latest_info()

    def check_for_update(self) -> Optional[ReleaseInfo]:
        """A release newer than the loaded one that this SDK reads, or None. Also sets newer_format_major from
        a conditional GET of OTC_latest.json (spec §7.4)."""
        self._check_open()
        _validate_offline_pointer(self)
        try:
            info = self._latest_info()
        except (UnsupportedFormatError, ReaderTooOldError):
            # only newer-major releases: set newer_format_major first, then raise (CR D10)
            self._newer_format_major = self._check_newer_major()
            raise
        self._newer_format_major = self._check_newer_major()
        if datestamp_key(info.datestamp) > datestamp_key(self._release.datestamp):
            return info
        return None

    def _check_newer_major(self) -> Optional[int]:
        """The format major of OTC_latest.json when it is newer than every supported major, else None. On an
        error the value from before is kept (CR D10): the check only informs, it never fails the call."""
        try:
            got = self._get_json_conditional("OTC_latest.json")
        except OpenTideConstantsError as e:
            self._log.debug("OTC_latest.json: %s", e)
            return self._newer_format_major
        if got is None or not isinstance(got[0], dict):
            return None
        major = _major(got[0].get("format_version"))
        if major is None or major <= max(SUPPORTED_FORMAT_MAJORS):
            return None
        self._log.warning("a newer format (%s) exists; upgrade opentideconstants to read it", major)
        return major

    def update(self) -> UpdateResult:
        """Download a newer release, verify it and swap it in. A Release held from before stays valid."""
        self._check_open()
        with self._lock:
            _validate_update_capability(self)
            return self._update()

    def _update(self) -> UpdateResult:
        cur = self._release.datestamp
        info = self.check_for_update()
        if info is None:
            return UpdateResult(False, cur, cur)
        if self._usable(info.datestamp, self._mode) is not None:
            rel, lf = self._load_cached_or_heal(info.datestamp, self._mode, info)
        else:
            rel, lf = self._download_to_cache(info.datestamp, self._mode, info), "download"
        self._set(rel, lf)
        self._last_error = None
        self._log.info("updated from %s to %s", cur, info.datestamp)
        return UpdateResult(True, cur, info.datestamp)

    def _maybe_auto_update(self) -> None:
        if self._closed or not self._auto_update or self._offline or self._pinned is not None or self._file is not None \
                or self._release is None:
            return  # offline, the automatic update does not check at all (spec §5.6, CR D6)
        now = time.monotonic()
        if now - self._last_check < self._update_interval:
            return
        with self._lock:
            if now - self._last_check < self._update_interval:
                return
            self._last_check = now
            try:
                self._update()
            except Exception as e:  # noqa: BLE001 - an automatic update never breaks the caller's query
                # keep the current release; log the failure with its stack and record it (spec §5.6, CR2 DR5),
                # with the user and password of every URL in it replaced (CR2 DR21)
                self._last_error = _auto_update_error(e)
                self._log.warning("automatic update failed: %s\n%s", redact_credentials(str(self._last_error)),
                                  redact_credentials("".join(traceback.format_exception(type(e), e, e.__traceback__))))

    def verify(self) -> bool:
        """Hash the loaded release's files again in full and compare them with OTC_{D}.sha256 (spec §4.3). A
        missing file is io (CR2 DR44); a missing OTC_{D}.sha256, a missing row or another digest is
        checksum_mismatch. For a cached release, the cached OTC_{D}.sha256 must first have the SHA-256 that a cached
        pointer lists for it, when one lists it (CR2 DR45); verify fetches nothing, so a mismatch is
        checksum_mismatch and the file stays."""
        self._check_open()
        return self._verify_release_files()

    def _verify_release_files(self, bind_manifest=None, trusted_pointer_digests=None) -> bool:
        rel = self._release
        ds = rel.datestamp
        opened = rel._opened
        if not opened:
            raise ChecksumError(f"release {ds}: no files to verify", file=None)
        first = opened[0]
        if self._loaded_from in (LoadedFrom.FILE, LoadedFrom.FILE_UNVERIFIED):
            sha_path = first.with_name(f"OTC_{ds}.sha256")
        else:
            sha_path = self._cache.release_dir(ds) / f"OTC_{ds}.sha256"
        if not sha_path.exists():
            raise ChecksumError(f"no OTC_{ds}.sha256 next to {first}", file=str(first))
        sha_body = _read_bytes(sha_path)
        if self._loaded_from not in (LoadedFrom.FILE, LoadedFrom.FILE_UNVERIFIED):
            _check_cached_manifest_bytes(sha_body, sha_path, self._cached_pointer_sha256(ds))
        rows = (_parse_sha256(sha_body, sha_path.name) if bind_manifest is None else
                bind_manifest(sha_body, sha_path, trusted_pointer_digests or {}))
        local = self._loaded_from in (LoadedFrom.FILE, LoadedFrom.FILE_UNVERIFIED)
        for p in opened:
            if not p.is_file():
                raise FileError(f"cannot read {p}: no such file", path=str(p))
        if local:
            _need_rows(first, opened, rows, sha_path.name)   # spec §5.3, CR3 DR73 and DR77
        for p in opened:
            self._check_file(p, rows.get(p.name))
        if local and first.name.endswith(".json.gz"):
            # the decompressed bytes against the .json row, as at open (CR3 DR77)
            try:
                data = gzip.decompress(_read_bytes(first))
            except (OSError, EOFError, zlib.error) as e:
                raise InvalidReleaseError(f"{first}: not gzip: {e}") from e
            check_json_sha256(first, data, rows[first.name[:-len(".gz")]])
        self._log.info("verified %s", ds)
        return True

    def _cached_pointer_sha256(self, datestamp: str) -> List[str]:
        """The SHA-256 values (lower case) that the cached pointers (OTC_latest-f{MAJOR}.json, OTC_latest.json) give
        for OTC_{D}.sha256. A cached pointer that is not there, cannot be read or does not parse, names another
        release or does not list the .sha256 gives none (CR2 DR45)."""
        out = []
        for name in (f"OTC_latest-f{max(SUPPORTED_FORMAT_MAJORS)}.json", "OTC_latest.json"):
            try:
                body = self._cache.read_pointer_body(name)
                doc = json.loads(body) if body is not None else None
            except (CacheError, ValueError) as e:
                self._log.debug("verify: the cached %s cannot be used (%s)", name, e)
                continue
            if not isinstance(doc, dict) or not isinstance(doc.get("files"), list):
                continue
            for f in doc["files"]:
                if isinstance(f, dict) and f.get("name") == f"OTC_{datestamp}.sha256" and isinstance(f.get("sha256"), str):
                    out.append(f["sha256"].lower())
        return out

    def cached_releases(self) -> Tuple[str, ...]:
        self._check_open()
        return tuple(self._cache.cached())

    def prune(self, *, keep: int = 3) -> Tuple[str, ...]:
        """Remove cached releases beyond the newest ``keep``. Never removes the loaded release. Stops at the first
        release it cannot remove with CacheError, whose ``removed`` lists the releases removed before it."""
        self._check_open()
        _validate_prune_arguments(keep)
        # Protect only the current release loaded by this client (spec §4.3, R13-A1).
        keep_ds = set()
        if self._release is not None and self._file is None:
            keep_ds.add(self._release.datestamp)
        removed = []
        for ds in self._cache.cached()[keep:]:
            if ds in keep_ds:
                continue
            try:
                gone = self._cache.remove_release(ds)
            except CacheError as e:
                # stop at the first failure and report the releases removed before it (spec §4.3, CR2 DR18)
                raise CacheError(str(e), removed=removed) from e
            if gone:
                removed.append(ds)
            else:
                self._log.info("prune: %s is locked by another process; it is kept", ds)
        self._cache.cleanup_partials(keep_ds)
        return tuple(removed)

    def _cached_sha256(self, datestamp: str, info: Optional[ReleaseInfo]):
        """(body, rows) of the cached OTC_{D}.sha256 of a verified release, or None when it cannot be trusted (CR2
        DR40): it cannot be read, it does not parse, or the pointer lists the .sha256 with another digest. The caller
        then fetches it again, as for a release that is not cached."""
        name = f"OTC_{datestamp}.sha256"
        sp = self._cache.release_dir(datestamp) / name
        try:
            body = sp.read_bytes()
            rows = _parse_sha256(body, str(sp))
            if not rows:
                raise InvalidReleaseError(f"{name} lists no files")
        except (OSError, InvalidReleaseError) as e:
            self._log.warning("the cached %s cannot be used (%s); fetching it again", name, e)
            return None
        ent = next((f for f in info.files if f.name == name), None) if info is not None else None
        if ent is not None and ent.sha256 is not None and hashlib.sha256(body).hexdigest() != ent.sha256:
            self._log.warning("the cached %s is not the one the pointer lists; fetching it again", name)
            return None
        return body, rows

    def download(self, release: str = "latest", *, to, formats: Sequence[str] = ("jsonl",),
                 overwrite: bool = False) -> Tuple[str, ...]:
        """Write a verified release into the folder ``to`` (spec §4.3.2): the requested formats plus
        OTC_{D}.meta.json and OTC_{D}.sha256, which are always included. A file that is already there with the
        right SHA-256 is skipped. Returns the paths this call wrote (skipped files are not in it)."""
        self._check_open()
        _validate_download_arguments(release=release, formats=formats, overwrite=overwrite, to=to)
        to = Path(to)
        info = None
        if release == "latest":
            if self._offline:
                ds = self._newest_cached("eager") or self._newest_cached("stream")
                if ds is None:
                    raise OfflineError("offline, and no release is in the cache")
            else:
                try:
                    info = self._latest_info()
                    ds = info.datestamp
                except NetworkError as e:
                    # on_network_error as when a client opens latest (spec §4.3.2, CR D22): use_cache writes the
                    # newest cached readable release; raise, or no usable cached release, raises the network error
                    ds = (self._newest_cached("eager") or self._newest_cached("stream")
                          if self._on_network_error == "use_cache" else None)
                    if ds is None:
                        raise
                    self._log.warning("network error (%s); writing the cached release %s", e, ds)
        else:
            ds = release
        base = f"OTC_{ds}"
        cdir = self._cache.release_dir(ds)
        cached = self._cache.read_verified(ds) is not None and (cdir / f"{base}.sha256").is_file()
        cached_sha = self._cached_sha256(ds, info) if cached else None
        if cached_sha is not None:
            sha_body, rows = cached_sha
        elif self._offline:
            raise OfflineError(f"offline, and release {ds} is not in the cache"
                               + (f" with a usable {base}.sha256" if cached else ""))
        else:
            sha_body, rows = self._get_sha256_rows(ds, info)
        self._check_pointer(info, rows)
        names = [base + FORMAT_EXT[f] for f in dict.fromkeys(formats)] + [f"{base}.meta.json"]
        for n in names:
            if n == f"{base}.json" and n not in rows:
                # the eager data file is always published, so a .sha256 without its row is a bad list, as for an
                # eager open (CR2 DR15, DR42)
                raise ChecksumError(f"{n} is not listed in {base}.sha256", file=n, expected=None, actual=None)
            if n not in rows:
                raise ReleaseNotFoundError(f"{n} is not part of release {ds}")
        sha_digest = hashlib.sha256(sha_body).hexdigest()
        targets = [(n, rows[n]) for n in names] + [(f"{base}.sha256", sha_digest)]
        # check every existing file before writing any file
        todo = []
        for n, sha in targets:
            p = to / n
            if p.exists():
                if file_sha256(p) == sha:
                    continue
                if not overwrite:
                    raise FileExistsError(f"{p} exists with a different SHA-256", path=str(p))
            todo.append((n, sha))
        try:
            to.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise FileError(f"cannot create {to}: {e}", path=str(to), cause=e) from e
        ptr = {f.name: f for f in info.files} if info is not None else {}
        if self._offline:
            missing = [n for n, _ in todo if n != f"{base}.sha256" and not (cached and (cdir / n).is_file())]
            if missing:
                raise OfflineError(f"offline, and {', '.join(missing)} is not in the cache")
        # check, then rename (spec §4.3.2): every file goes to a checked temporary file in `to` first; only when
        # all of them are there are they renamed into place, all or nothing (CR2 DR17), so a failure leaves `to` as
        # it was
        staged = []  # (tmp, dest)
        try:
            for n, sha in todo:
                dest = to / n
                if n == f"{base}.sha256":
                    tmp = tmp_name(to)
                    staged.append((tmp, dest))
                    try:
                        with open(tmp, "wb") as f:
                            f.write(sha_body)
                            f.flush()
                            os.fsync(f.fileno())
                    except OSError as e:
                        raise FileError(f"cannot write {dest}: {e}", path=str(dest), cause=e) from e
                    continue
                src = cdir / n
                if cached and src.is_file():
                    tmp = tmp_name(to)
                    staged.append((tmp, dest))
                    try:
                        with open(src, "rb") as fi, open(tmp, "wb") as fo:
                            while True:
                                chunk = fi.read(1 << 20)
                                if not chunk:
                                    break
                                fo.write(chunk)
                            fo.flush()
                            os.fsync(fo.fileno())
                    except OSError as e:
                        raise FileError(f"cannot write {dest}: {e}", path=str(dest), cause=e) from e
                    actual = file_sha256(tmp)
                    if actual != sha:
                        raise ChecksumError(f"{n}: the cached copy does not match", file=str(dest), expected=sha,
                                            actual=actual)
                else:
                    url = ptr[n].url if n in ptr and ptr[n].url else self._url(n)
                    try:
                        tmp = self._fetch_file(url, to, sha, ptr[n].size if n in ptr else None, str(dest), ds,
                                               gz=n.endswith(".gz"))
                    except OSError as e:  # a write into `to` failed: local io, not network (spec §4.8)
                        raise FileError(f"cannot write {dest}: {e}", path=str(dest), cause=e) from e
                    staged.append((tmp, dest))
            written = _rename_all_in(staged, self._log)  # on a failure, the finally below removes what is left
            staged = []
            return written
        finally:
            for tmp, _ in staged:
                try:
                    tmp.unlink()
                except FileNotFoundError:
                    pass
                except OSError as e:  # R3-224
                    self._log.warning("cannot remove %s: %s", tmp, e)

    # ------------------------------------------------------------------ forwarded queries (spec §4.4)

    def _r(self) -> Release:
        self._check_open()
        self._maybe_auto_update()
        return self._release

    def station(self, station_id: str) -> Optional[Station]:
        return self._r().station(station_id)

    def require_station(self, station_id: str) -> Station:
        return self._r().require_station(station_id)

    def tombstone(self, station_id: str) -> Optional[Tombstone]:
        return self._r().tombstone(station_id)

    def station_by_alias(self, system: str, alias_id: str) -> Optional[Station]:
        return self._r().station_by_alias(system, alias_id)

    def stations(self, *, country=None, type=None, kind=None, source=None,  # noqa: A002
                 source_type=None, include_flagged=False, include_fallback=False):
        return self._r().stations(country=country, type=type, kind=kind, source=source, source_type=source_type, include_flagged=include_flagged, include_fallback=include_fallback)

    def iter_stations(self, *, country=None, type=None, kind=None, source=None,  # noqa: A002
                      source_type=None, include_flagged=False, include_fallback=False):
        return self._r().iter_stations(country=country, type=type, kind=kind, source=source, source_type=source_type, include_flagged=include_flagged, include_fallback=include_fallback)

    def search(self, *, name, limit=None, match=None, country=None, type=None, kind=None, source=None,  # noqa: A002
               source_type=None, include_flagged=False, include_fallback=False):
        return self._r().search(name=name, limit=limit, match=match, country=country, type=type, kind=kind,
                                source=source, source_type=source_type, include_flagged=include_flagged, include_fallback=include_fallback)

    def near(self, *, lat, lon, radius_km, limit=None, country=None, type=None, kind=None, source=None,  # noqa: A002
             source_type=None, include_flagged=False, include_fallback=False) -> Tuple[Nearby, ...]:
        return self._r().near(lat=lat, lon=lon, radius_km=radius_km, limit=limit, country=country, type=type,
                              kind=kind, source=source, source_type=source_type, include_flagged=include_flagged, include_fallback=include_fallback)

    def nearest(self, *, lat, lon, max_km=None, country=None, type=None, kind=None, source=None,  # noqa: A002
                source_type=None, include_flagged=False, include_fallback=False) -> Optional[Nearby]:
        return self._r().nearest(lat=lat, lon=lon, max_km=max_km, country=country, type=type, kind=kind,
                                 source=source, source_type=source_type, include_flagged=include_flagged, include_fallback=include_fallback)

    def heights(self, station, *, start, stop, step_s=600, datum=None, set_id=None, offset_id=None):
        """Heights using otc-predict-1 (prediction spec section 5.2)."""
        return self._r().heights(station, start=start, stop=stop, step_s=step_s, datum=datum, set_id=set_id, offset_id=offset_id)

    def heights_at(self, station, times, *, datum=None, set_id=None, offset_id=None):
        """Heights at using otc-predict-1 (prediction spec section 5.2)."""
        return self._r().heights_at(station, times, datum=datum, set_id=set_id, offset_id=offset_id)

    def extremes(self, station, *, start, stop, datum=None, set_id=None, offset_id=None):
        """Extremes using otc-predict-1 (prediction spec section 5.2)."""
        return self._r().extremes(station, start=start, stop=stop, datum=datum, set_id=set_id, offset_id=offset_id)

    def currents(self, station, *, start, stop, step_s=600, bin_number=None, set_id=None):
        """Currents using otc-predict-1 (prediction spec section 5.2)."""
        return self._r().currents(station, start=start, stop=stop, step_s=step_s, bin_number=bin_number, set_id=set_id)

    def current_events(self, station, *, start, stop, bin_number=None, set_id=None):
        """Current events using otc-predict-1 (prediction spec section 5.2)."""
        return self._r().current_events(station, start=start, stop=stop, bin_number=bin_number, set_id=set_id)

    def datums(self, station, *, set_id=None, all_sets=False):
        """Datums using otc-predict-1 (prediction spec section 5.2)."""
        return self._r().datums(station, set_id=set_id, all_sets=all_sets)

    def ranges(self, station, *, set_id=None):
        """Ranges using otc-predict-1 (prediction spec section 5.2)."""
        return self._r().ranges(station, set_id=set_id)

    def reference_station(self, station: Station) -> Optional[Station]:
        return self._r().reference_station(station)

    def subordinates_of(self, station: Station) -> Tuple[Station, ...]:
        return self._r().subordinates_of(station)

    def attribution(self, stations: Optional[Sequence[Station]] = None) -> str:
        return self._r().attribution(stations)

    def __repr__(self) -> str:
        r = self._release
        return f"<OpenTideConstants {r.datestamp if r else None} loaded_from={self._loaded_from}>"
