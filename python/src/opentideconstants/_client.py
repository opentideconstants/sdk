"""The client (spec §4.2, §4.3, §5): options, cache, HTTP and the current Release."""
from __future__ import annotations

import gzip
import json
import logging
import math
import os
import threading
import time
import weakref
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Sequence, Tuple
from urllib.parse import urljoin

from ._cache import DATESTAMP_RE, Cache, atomic_write, datestamp_key, default_root, ensure_dir, lock_dir, tmp_name
from ._enums import LoadedFrom
from ._errors import (CacheError, ChecksumError, FileError, FileExistsError, InvalidArgumentError,
                      InvalidReleaseError, NetworkError, OfflineError, OpenTideConstantsError, PinnedReleaseError,
                      ReaderTooOldError, ReleaseNotFoundError, UnsupportedFormatError)
from ._http import Http, check_http_url
from ._models import FileInfo, Nearby, ReleaseInfo, Station, Tombstone, UpdateResult
from ._release import (SUPPORTED_FORMAT_MAJORS, SUPPORTED_FORMAT_VERSION, Release, file_sha256, load_document,
                       meta_path_for, readable, version_key)

__version__ = "0.1.0"
SDK = f"opentideconstants-python/{__version__}"
DEFAULT_BASE_URL = "https://data.opentideconstants.org/"
FORMAT_EXT = {"json": ".json", "json.gz": ".json.gz", "jsonl": ".jsonl"}
_MODES = ("eager", "stream")
_ON_ERR = ("use_cache", "raise")


def _major(fv) -> Optional[int]:
    k = version_key(fv)
    return None if k is None else k[0]


def _parse_sha256(text: str):
    rows = {}
    for line in text.splitlines():
        if line.strip():
            parts = line.split(None, 1)
            if len(parts) != 2:
                raise InvalidReleaseError(f"bad .sha256 line: {line!r}")
            rows[parts[1].strip().lstrip("*")] = parts[0].lower()
    return rows


def _split_file_name(name: str):
    """OTC_<D><ext> -> (D, ext), with D a valid datestamp; else (None, None) (spec §4.2, CR D18)."""
    for ext in (".json.gz", ".jsonl", ".json"):
        if name.startswith("OTC_") and name.endswith(ext) and DATESTAMP_RE.match(name[4:-len(ext)]):
            return name[4:-len(ext)], ext
    return None, None


def _flag(v) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "on")


class OpenTideConstants:
    """An OpenTideConstants client: ``OpenTideConstants()`` opens the latest release.

    Use ``with OpenTideConstants(...) as otc:`` or call ``close()``. Query methods are forwarded to the
    current Release (``otc.release``)."""

    def __init__(self, *, release: str = "latest", file=None, cache_dir=None, offline: bool = False,
                 mode: str = "eager", base_url: Optional[str] = None, timeout=None, proxy=None, ca_file=None,
                 user_agent: Optional[str] = None, on_network_error: str = "use_cache", auto_update: bool = False,
                 update_interval=86_400, logger: Optional[logging.Logger] = None, verify_on_open: bool = False):
        self._log = logger or logging.getLogger("opentideconstants")
        self._lock = threading.RLock()
        self._release: Optional[Release] = None
        self._loaded_from: Optional[LoadedFrom] = None
        self._last_error: Optional[OpenTideConstantsError] = None
        self._newer_format_major: Optional[int] = None
        self._closed = False
        self._handed_out = weakref.WeakSet()  # Releases this client made that may still be held
        if not isinstance(release, str) or (release != "latest" and not DATESTAMP_RE.match(release)):
            raise InvalidArgumentError(f"release must be 'latest' or a datestamp, not {release!r}")
        if mode not in _MODES:
            raise InvalidArgumentError(f"mode must be one of {_MODES}, not {mode!r}")
        if on_network_error not in _ON_ERR:
            raise InvalidArgumentError(f"on_network_error must be one of {_ON_ERR}, not {on_network_error!r}")
        for name, v in (("offline", offline), ("auto_update", auto_update), ("verify_on_open", verify_on_open)):
            if not isinstance(v, bool):
                raise InvalidArgumentError(f"{name} must be a boolean")
        # A file client reads no pointer and opens no socket, so these options would be silently ignored (CR D31,
        # spec §4.2). The variable OPENTIDECONSTANTS_OFFLINE is not an option and does not conflict.
        if file is not None and (release != "latest" or offline or on_network_error != "use_cache"):
            raise InvalidArgumentError("file cannot be combined with release, offline or on_network_error")
        for name, v in (("timeout", timeout), ("update_interval", update_interval)):
            if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                                  or v <= 0):
                raise InvalidArgumentError(f"{name} must be a positive finite number, not {v!r}")
        self._pinned = release if release != "latest" else None
        self._file = None if file is None else Path(file)
        self._mode = mode
        self._offline = offline or _flag(os.environ.get("OPENTIDECONSTANTS_OFFLINE", ""))
        base = base_url or os.environ.get("OPENTIDECONSTANTS_BASE_URL") or DEFAULT_BASE_URL
        check_http_url("base_url", base)  # at construction, never retried (CR D19)
        self._base_url = base if base.endswith("/") else base + "/"
        root = cache_dir if cache_dir is not None else default_root()
        self._cache = Cache(Path(root))
        self._on_network_error = on_network_error
        self._auto_update = auto_update
        self._update_interval = float(update_interval if update_interval is not None else 86_400)
        self._verify_on_open = verify_on_open
        ua = f"opentideconstants-python/{__version__} (+https://opentideconstants.org)"
        if user_agent:
            ua += " " + user_agent
        self._http = Http(user_agent=ua, timeout=timeout, proxy=proxy, ca_file=ca_file, logger=self._log)
        if self._file is not None:
            self._open_file(self._file)
        elif self._pinned is not None:
            self._open_pinned(self._pinned)
        else:
            self._open_latest()
        self._last_check = time.monotonic()

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
        if sha_path.exists():
            rows = _parse_sha256(self._read_text(sha_path))
            for p in opened:
                self._check_file(p, rows.get(p.name))
            files = [FileInfo(n, None, (path.parent / n).stat().st_size if (path.parent / n).exists() else None, rows[n])
                     for n in sorted(rows)]
            lf = "file"
        else:
            files = [FileInfo(p.name, None, p.stat().st_size, None) for p in sorted(opened, key=lambda p: p.name)]
            lf = "file_unverified"
        rel = load_document(path, self._mode, files)
        rel._opened = tuple(opened)
        self._set(rel, lf)

    @staticmethod
    def _read_text(p: Path) -> str:
        try:
            return p.read_text(encoding="utf-8")
        except OSError as e:
            raise FileError(f"cannot read {p}: {e}", path=str(p), cause=e) from e

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
        for p in check:
            rec = v["files"].get(p.name) or {}
            size = rec.get("size")
            try:
                actual_size = p.stat().st_size
            except OSError as e:  # removed or unreadable since it was found: cache, never absent (spec §5.2)
                raise CacheError(f"cannot read {p}: {e}") from e
            if size is not None and actual_size != size:
                raise ChecksumError(f"{p.name}: size {actual_size} does not match {size}", file=str(p),
                                    expected=rec.get("sha256"), actual=file_sha256(p))
            if self._verify_on_open:
                self._check_file(p, rec.get("sha256"))
        rel = load_document(path, mode, self._cached_files(datestamp),
                            index_path=d / "index-v1.json" if mode == "stream" else None,
                            index_sha256=(v["files"].get(path.name) or {}).get("sha256"))
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
        An entry with no DOI does not erase a known one. The read-modify-write runs under the release lock."""
        if info.zenodo_version_doi is None:
            return
        v = self._cache.read_verified(info.datestamp)
        if v is None or v.get("zenodo_version_doi") == info.zenodo_version_doi:
            return
        d = self._cache.release_dir(info.datestamp)
        try:
            with lock_dir(d, SDK) as held:
                v = self._cache.read_verified(info.datestamp) if held else None
                if v is None or v.get("zenodo_version_doi") == info.zenodo_version_doi:
                    return
                v["zenodo_version_doi"] = info.zenodo_version_doi
                atomic_write(d / ".verified", json.dumps(v, indent=1, sort_keys=True).encode("utf-8"))
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

    def _get_json_conditional(self, name: str):
        """GET a changing file (pointer or index) with If-None-Match; returns (doc, url) or None on 404.

        A 200 body is parsed before it is cached, so a body that is not JSON (a captive portal) never replaces a
        good cached copy; it is a network error (spec §5.2 step 5, CR D8). A failure to write the cache is logged,
        not raised (CR D8)."""
        url = self._url(name)
        body, etag = self._cache.read_pointer(name)
        headers = {"If-None-Match": etag} if body is not None and etag else {}
        r = self._http.get(url, headers=headers, accept_gzip=True)
        if r.status == 304 and not headers:
            raise NetworkError(f"HTTP 304 for {url} with no If-None-Match", url=url, status=304)
        if r.status == 404:
            return None
        if r.status == 304:
            self._log.debug("pointer %s: 304", name)
            try:
                return json.loads(body.decode("utf-8")), url
            except (ValueError, UnicodeDecodeError):
                # the cached copy is broken: drop it and read the file again with no If-None-Match
                self._log.warning("cached %s is not JSON; reading it again", name)
                self._cache.drop_pointer(name)
                return self._get_json_conditional(name)
        self._log.debug("pointer %s: 200", name)
        try:
            doc = json.loads(r.body.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            raise NetworkError(f"{url}: the 200 body is not JSON (a captive portal or a proxy page?)", url=url,
                               status=r.status) from e
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
        try:
            files = tuple(sorted((FileInfo(f["name"], urljoin(url, f.get("url") or f["name"]), f.get("size"),
                                           f["sha256"].lower() if isinstance(f.get("sha256"), str) else None)
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
        ent = listed.get(name)
        if ent is not None and ent.sha256 is not None and r.sha256 != ent.sha256:
            raise ChecksumError(f"{name}: SHA-256 {r.sha256} does not match the pointer's {ent.sha256}", file=name,
                                expected=ent.sha256, actual=r.sha256)
        try:
            return r.body, _parse_sha256(r.body.decode("utf-8"))
        except UnicodeDecodeError as e:
            raise InvalidReleaseError(f"{url}: not text") from e

    @staticmethod
    def _check_pointer(info: Optional[ReleaseInfo], rows) -> None:
        """The pointer and the .sha256 file must agree (spec §5.2 step 4.1): the same SHA-256 for every file both
        list, and no file in the .sha256 that the pointer does not list."""
        if info is None:
            return
        listed = {f.name: f for f in info.files}
        for n, sha in rows.items():
            f = listed.get(n)
            if f is None:
                raise ChecksumError(f"{n} is in the .sha256 file but not in the pointer", file=n, expected=None,
                                    actual=sha)
            if f.sha256 is not None and f.sha256 != sha:
                raise ChecksumError(f"{n}: the pointer and the .sha256 file disagree", file=n,
                                    expected=sha, actual=f.sha256)

    def _fetch_file(self, url: str, dest_dir: Path, expected_sha: Optional[str], expected_size, final_name: str,
                    gz: bool = False):
        """Download url to a temporary file in dest_dir, check size and SHA-256, return the temporary path."""
        tmp = tmp_name(dest_dir)
        try:
            with open(tmp, "w+b") as f:
                r = self._http.get(url, accept_gzip=not gz, sink=f)
                if r.status == 404:
                    raise ReleaseNotFoundError(f"{url}: 404")
                f.flush()
                os.fsync(f.fileno())
            if (expected_size is not None and r.size != expected_size) or r.sha256 != expected_sha:
                raise ChecksumError(f"{final_name}: SHA-256 {r.sha256} (size {r.size}) does not match {expected_sha}",
                                    file=final_name, expected=expected_sha, actual=r.sha256)
            return tmp
        except BaseException:
            try:
                tmp.unlink()
            except OSError:
                pass
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
                        if n not in rows:
                            raise InvalidReleaseError(f"{n} is not in the .sha256 file")
                        tmp = self._fetch_file(url_of(n), d, rows[n], size_of(n), n)
                        wanted.append((n, tmp))
                        written[n] = os.path.getsize(tmp)
                    data_name = f"{base}.jsonl"
                elif f"{base}.json.gz" in rows:
                    gzn, jn = f"{base}.json.gz", f"{base}.json"
                    tmp_gz = self._fetch_file(url_of(gzn), d, rows[gzn], size_of(gzn), gzn, gz=True)
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
                    if jn in rows and actual != rows[jn]:
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
                    tmp = self._fetch_file(url_of(jn), d, rows[jn], size_of(jn), jn)
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
                    except OSError:
                        pass
            self._log.info("downloaded and verified %s", datestamp)
            # the files table of .verified (spec §4.3.1): the pointer's values, or the .sha256 rows
            old = self._cache.read_verified(datestamp) or {"files": {}}
            files = dict(old.get("files") or {})
            # every row of the .sha256 file, then the pointer's values over them (they agree: _check_pointer)
            for n, sha in rows.items():
                prev = files.get(n) or {}
                files[n] = {"sha256": sha, "size": written.get(n, prev.get("size")), "url": prev.get("url")}
            if info is not None:
                for f in info.files:
                    files[f.name] = {"sha256": f.sha256 or (files.get(f.name) or {}).get("sha256"),
                                     "size": f.size if f.size is not None else written.get(f.name), "url": f.url}
            files_infos = [FileInfo(n, f.get("url"), f.get("size"), f.get("sha256")) for n, f in sorted(files.items())]
            rel = load_document(d / data_name, mode, files_infos,
                                index_path=d / "index-v1.json" if mode == "stream" else None,
                                index_sha256=(files.get(data_name) or {}).get("sha256"))
            zdoi = info.zenodo_version_doi if info is not None else old.get("zenodo_version_doi")
            rel._zenodo_version_doi = zdoi
            rel._opened = (d / data_name,) + ((d / f"{base}.meta.json",) if data_name.endswith(".jsonl") else ())
            verified = {"files": files, "verified_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "by": SDK, "datestamp": datestamp, "format_version": rel.format_version,
                        "min_reader_version": rel._release.get("min_reader_version"), "zenodo_version_doi": zdoi}
            try:
                atomic_write(d / ".verified", json.dumps(verified, indent=1, sort_keys=True).encode("utf-8"))
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
        if self._offline:
            raise OfflineError("offline: the latest pointer cannot be read")
        return self._latest_info()

    def check_for_update(self) -> Optional[ReleaseInfo]:
        """A release newer than the loaded one that this SDK reads, or None. Also sets newer_format_major from
        a conditional GET of OTC_latest.json (spec §7.4)."""
        self._check_open()
        if self._offline:
            raise OfflineError("offline: the latest pointer cannot be read")
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
            if self._pinned is not None or self._file is not None:
                raise PinnedReleaseError("this client was opened on a pinned release or a file")
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
            except OpenTideConstantsError as e:
                # keep the current release; record and log the failure (spec §5.6)
                self._last_error = e
                self._log.warning("automatic update failed: %s", e)
            except Exception as e:  # noqa: BLE001 - an automatic update never breaks the caller's query
                self._log.warning("automatic update failed: %s: %s", type(e).__name__, e)

    def verify(self) -> bool:
        """Hash the loaded release's files again in full and compare them with OTC_{D}.sha256 (spec §4.3). A
        missing file is io; a missing OTC_{D}.sha256, a missing row or another digest is checksum_mismatch."""
        self._check_open()
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
        rows = _parse_sha256(self._read_text(sha_path))
        for p in opened:
            if not p.is_file():
                raise FileError(f"cannot read {p}: no such file", path=str(p))
            self._check_file(p, rows.get(p.name))
        self._log.info("verified %s", ds)
        return True

    def cached_releases(self) -> Tuple[str, ...]:
        self._check_open()
        return tuple(self._cache.cached())

    def prune(self, *, keep: int = 3) -> Tuple[str, ...]:
        """Remove cached releases beyond the newest ``keep``. Never removes the loaded release."""
        self._check_open()
        if isinstance(keep, bool) or not isinstance(keep, int) or keep < 0:
            raise InvalidArgumentError("keep must be a non-negative integer")
        # never the loaded release, nor one that the caller still holds from before an update (spec §4.3)
        keep_ds = {r.datestamp for r in list(self._handed_out) if not r._closed}
        if self._release is not None:
            keep_ds.add(self._release.datestamp)
        removed = []
        for ds in self._cache.cached()[keep:]:
            if ds in keep_ds:
                continue
            if self._cache.remove_release(ds):
                removed.append(ds)
            else:
                self._log.info("prune: %s is locked by another process; it is kept", ds)
        return tuple(removed)

    def download(self, release: str = "latest", *, to, formats: Sequence[str] = ("jsonl",),
                 overwrite: bool = False) -> Tuple[str, ...]:
        """Write a verified release into the folder ``to`` (spec §4.3.2): the requested formats plus
        OTC_{D}.meta.json and OTC_{D}.sha256, which are always included. A file that is already there with the
        right SHA-256 is skipped. Returns the paths this call wrote (skipped files are not in it)."""
        self._check_open()
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
        to = Path(to)
        info = None
        if release == "latest":
            if self._offline:
                ds = self._newest_cached("eager") or self._newest_cached("stream")
                if ds is None:
                    raise OfflineError("offline, and no release is in the cache")
            else:
                info = self._latest_info()
                ds = info.datestamp
        else:
            ds = release
        base = f"OTC_{ds}"
        cdir = self._cache.release_dir(ds)
        cached = self._cache.read_verified(ds) is not None and (cdir / f"{base}.sha256").is_file()
        if cached:
            sp = cdir / f"{base}.sha256"
            try:
                sha_body = sp.read_bytes()
                rows = _parse_sha256(sha_body.decode("utf-8"))
            except OSError as e:
                raise FileError(f"cannot read {sp}: {e}", path=str(sp), cause=e) from e
            except UnicodeDecodeError as e:
                raise InvalidReleaseError(f"{sp}: not text") from e
        elif self._offline:
            raise OfflineError(f"offline, and release {ds} is not in the cache")
        else:
            sha_body, rows = self._get_sha256_rows(ds, info)
        self._check_pointer(info, rows)
        names = [base + FORMAT_EXT[f] for f in dict.fromkeys(formats)] + [f"{base}.meta.json"]
        for n in names:
            if n not in rows:
                raise ReleaseNotFoundError(f"{n} is not part of release {ds}")
        import hashlib
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
        # all of them are there are they renamed into place, so a failure leaves nothing new in `to`
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
                        tmp = self._fetch_file(url, to, sha, ptr[n].size if n in ptr else None, str(dest),
                                               gz=n.endswith(".gz"))
                    except OSError as e:  # a write into `to` failed: local io, not network (spec §4.8)
                        raise FileError(f"cannot write {dest}: {e}", path=str(dest), cause=e) from e
                    staged.append((tmp, dest))
            written = []
            for tmp, dest in staged:
                try:
                    os.replace(tmp, dest)
                except OSError as e:
                    raise FileError(f"cannot write {dest}: {e}", path=str(dest), cause=e) from e
                written.append(str(dest))
            staged = []
            return tuple(written)
        finally:
            for tmp, _ in staged:
                try:
                    tmp.unlink()
                except OSError:
                    pass

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

    def stations(self, *, country=None, type=None, kind=None, source=None, source_type=None):  # noqa: A002
        return self._r().stations(country=country, type=type, kind=kind, source=source, source_type=source_type)

    def iter_stations(self, *, country=None, type=None, kind=None, source=None, source_type=None):  # noqa: A002
        return self._r().iter_stations(country=country, type=type, kind=kind, source=source, source_type=source_type)

    def search(self, *, name, limit=None, match=None, country=None, type=None, kind=None, source=None,  # noqa: A002
               source_type=None):
        return self._r().search(name=name, limit=limit, match=match, country=country, type=type, kind=kind,
                                source=source, source_type=source_type)

    def near(self, *, lat, lon, radius_km, limit=None, country=None, type=None, kind=None, source=None,  # noqa: A002
             source_type=None) -> Tuple[Nearby, ...]:
        return self._r().near(lat=lat, lon=lon, radius_km=radius_km, limit=limit, country=country, type=type,
                              kind=kind, source=source, source_type=source_type)

    def nearest(self, *, lat, lon, max_km=None, country=None, type=None, kind=None, source=None,  # noqa: A002
                source_type=None) -> Optional[Nearby]:
        return self._r().nearest(lat=lat, lon=lon, max_km=max_km, country=country, type=type, kind=kind,
                                 source=source, source_type=source_type)

    def reference_station(self, station: Station) -> Optional[Station]:
        return self._r().reference_station(station)

    def subordinates_of(self, station: Station) -> Tuple[Station, ...]:
        return self._r().subordinates_of(station)

    def attribution(self, stations: Optional[Sequence[Station]] = None) -> str:
        return self._r().attribution(stations)

    def __repr__(self) -> str:
        r = self._release
        return f"<OpenTideConstants {r.datestamp if r else None} loaded_from={self._loaded_from}>"
