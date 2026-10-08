"""The client (spec §4.2, §4.3, §5): options, cache, HTTP and the current Release."""
from __future__ import annotations

import gzip
import json
import logging
import os
import threading
import time
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Sequence, Tuple
from urllib.parse import urljoin

from ._cache import DATESTAMP_RE, Cache, atomic_write, datestamp_key, default_root, ensure_dir, lock_dir, tmp_name
from ._enums import LoadedFrom
from ._errors import (CacheError, ChecksumError, FileError, FileExistsError, InvalidArgumentError,
                      InvalidReleaseError, NetworkError, OfflineError, OpenTideConstantsError, PinnedReleaseError,
                      ReleaseNotFoundError, UnsupportedFormatError)
from ._http import Http
from ._models import FileInfo, Nearby, ReleaseInfo, Station, Tombstone, UpdateResult
from ._release import SUPPORTED_FORMAT_MAJORS, Release, file_sha256, load_document, meta_path_for

__version__ = "0.1.0"
SDK = f"opentideconstants-python/{__version__}"
DEFAULT_BASE_URL = "https://data.opentideconstants.org/"
FORMAT_EXT = {"json": ".json", "json.gz": ".json.gz", "jsonl": ".jsonl"}
_MODES = ("eager", "stream")
_ON_ERR = ("use_cache", "raise")


def _major(fv) -> Optional[int]:
    try:
        return int(str(fv).split(".", 1)[0])
    except ValueError:
        return None


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
    """OTC_<D><ext> -> (D, ext) or (None, None)."""
    for ext in (".json.gz", ".jsonl", ".json"):
        if name.startswith("OTC_") and name.endswith(ext):
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
        self._closed = False
        if not isinstance(release, str) or (release != "latest" and not DATESTAMP_RE.match(release)):
            raise InvalidArgumentError(f"release must be 'latest' or a datestamp, not {release!r}")
        if mode not in _MODES:
            raise InvalidArgumentError(f"mode must be one of {_MODES}, not {mode!r}")
        if on_network_error not in _ON_ERR:
            raise InvalidArgumentError(f"on_network_error must be one of {_ON_ERR}, not {on_network_error!r}")
        for name, v in (("offline", offline), ("auto_update", auto_update), ("verify_on_open", verify_on_open)):
            if not isinstance(v, bool):
                raise InvalidArgumentError(f"{name} must be a boolean")
        for name, v in (("timeout", timeout), ("update_interval", update_interval)):
            if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0):
                raise InvalidArgumentError(f"{name} must be a non-negative number")
        self._pinned = release if release != "latest" else None
        self._file = None if file is None else Path(file)
        self._mode = mode
        self._offline = offline or _flag(os.environ.get("OPENTIDECONSTANTS_OFFLINE", ""))
        base = base_url or os.environ.get("OPENTIDECONSTANTS_BASE_URL") or DEFAULT_BASE_URL
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
        self._opened_files: Tuple[Path, ...] = ()
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
        """Close the client (stream mode holds a file handle)."""
        with self._lock:
            self._closed = True
            if self._release is not None:
                self._release.close()

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

    # ------------------------------------------------------------------ opening

    def _set(self, rel: Release, loaded_from: str) -> None:
        old = self._release
        self._release = rel
        self._loaded_from = LoadedFrom(loaded_from)
        if old is not None and old is not rel:
            pass  # a Release the caller holds stays usable; it is closed with the client only if current

    def _open_file(self, path: Path) -> None:
        name = path.name
        d, ext = _split_file_name(name)
        if ext is None:
            if name.endswith(".jsonl"):
                ext = ".jsonl"
            elif name.endswith(".json.gz"):
                ext = ".json.gz"
            else:
                ext = ".json"
        if not path.exists():
            raise FileError(f"cannot open {path}: no such file", path=str(path))
        opened = [path] + ([meta_path_for(path)] if ext == ".jsonl" else [])
        for p in opened:
            if not p.exists():
                raise FileError(f"cannot open {p}: no such file", path=str(p))
        sha_path = path.with_name(f"OTC_{d}.sha256") if d is not None else None
        if sha_path is not None and sha_path.exists():
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
        self._opened_files = tuple(opened)
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
            if size is not None and p.stat().st_size != size:
                raise ChecksumError(f"{p.name}: size {p.stat().st_size} does not match {size}", file=str(p),
                                    expected=rec.get("sha256"), actual=None)
            if self._verify_on_open:
                self._check_file(p, rec.get("sha256"))
        return load_document(path, mode, self._cached_files(datestamp),
                             index_path=d / "index-v1.json" if mode == "stream" else None)

    def _newest_cached(self, mode: str):
        for ds in self._cache.cached():
            path = self._usable(ds, mode)
            if path is None:
                continue
            v = self._cache.read_verified(ds) or {}
            fv = v.get("format_version")
            if fv is not None and _major(fv) not in SUPPORTED_FORMAT_MAJORS:
                continue
            return ds
        return None

    # ---- pointer and index

    def _get_json_conditional(self, name: str):
        """GET a changing file (pointer or index) with If-None-Match; returns (doc, url) or None on 404."""
        url = self._url(name)
        body, etag = self._cache.read_pointer(name)
        headers = {"If-None-Match": etag} if body is not None and etag else {}
        r = self._http.get(url, headers=headers, accept_gzip=True)
        if r.status == 404:
            return None
        if r.status == 304:
            self._log.debug("pointer %s: 304", name)
        else:
            self._log.debug("pointer %s: 200", name)
            body = r.body
            ensure_dir(self._cache.root)
            self._cache.write_pointer(name, body, r.headers.get("etag"))
        try:
            return json.loads(body.decode("utf-8")), url
        except (ValueError, UnicodeDecodeError) as e:
            raise InvalidReleaseError(f"{name}: not JSON") from e

    def _info(self, entry, url) -> ReleaseInfo:
        try:
            files = tuple(sorted((FileInfo(f["name"], urljoin(url, f.get("url") or f["name"]), f.get("size"),
                                           f.get("sha256")) for f in entry.get("files") or ()),
                                 key=lambda f: f.name))
            return ReleaseInfo(entry["datestamp"], entry.get("format_version"), entry.get("doi"), files)
        except (KeyError, TypeError, AttributeError) as e:
            raise InvalidReleaseError(f"bad pointer entry: {e!r}") from e

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
        infos = [self._info(e, url) for e in entries]
        return sorted(infos, key=lambda i: datestamp_key(i.datestamp), reverse=True)

    def _latest_info(self) -> ReleaseInfo:
        """The newest release with a supported format major (spec §5.2 step 2, §7.4)."""
        got = None
        for major in SUPPORTED_FORMAT_MAJORS:
            got = self._get_json_conditional(f"OTC_latest-f{major}.json")
            if got is not None:
                break
        if got is None:
            got = self._get_json_conditional("OTC_latest.json")
            if got is None:
                raise ReleaseNotFoundError(f"no latest pointer under {self._base_url}")
        doc, url = got
        info = self._info(doc, url)
        if _major(info.format_version) in SUPPORTED_FORMAT_MAJORS:
            return info
        self._log.warning("a newer format (%s) exists; upgrade opentideconstants to read it", info.format_version)
        try:
            infos = self._fetch_index()
        except ReleaseNotFoundError:
            infos = []
        for i in infos:
            if _major(i.format_version) in SUPPORTED_FORMAT_MAJORS:
                return i
        raise UnsupportedFormatError(f"no release with a supported format major {list(SUPPORTED_FORMAT_MAJORS)}")

    # ---- downloading into the cache (spec §5.2 step 4)

    def _get_sha256_rows(self, datestamp: str):
        url = self._url(f"OTC_{datestamp}.sha256")
        r = self._http.get(url)
        if r.status == 404:
            raise ReleaseNotFoundError(f"release {datestamp} not found ({url})")
        try:
            return r.body, _parse_sha256(r.body.decode("utf-8"))
        except UnicodeDecodeError as e:
            raise InvalidReleaseError(f"{url}: not text") from e

    @staticmethod
    def _check_pointer(info: Optional[ReleaseInfo], rows) -> None:
        if info is None:
            return
        for f in info.files:
            if f.name in rows and f.sha256 is not None and f.sha256.lower() != rows[f.name]:
                raise ChecksumError(f"{f.name}: the pointer and the .sha256 file disagree", file=f.name,
                                    expected=rows[f.name], actual=f.sha256)

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
            sha_body, rows = self._get_sha256_rows(datestamp)
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
                    try:
                        raw = gzip.decompress(Path(tmp_gz).read_bytes())
                    except (OSError, EOFError, zlib.error) as e:
                        raise InvalidReleaseError(f"{gzn}: not gzip") from e
                    finally:
                        Path(tmp_gz).unlink()
                    import hashlib
                    actual = hashlib.sha256(raw).hexdigest()
                    if jn in rows and actual != rows[jn]:
                        raise ChecksumError(f"{jn}: SHA-256 {actual} does not match {rows[jn]}", file=jn,
                                            expected=rows[jn], actual=actual)
                    tmp = tmp_name(d)
                    with open(tmp, "wb") as f:
                        f.write(raw)
                        f.flush()
                        os.fsync(f.fileno())
                    wanted.append((jn, tmp))
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
            if info is not None:
                for f in info.files:
                    files[f.name] = {"sha256": f.sha256, "size": f.size, "url": f.url}
            else:
                for n, sha in rows.items():
                    prev = files.get(n) or {}
                    files[n] = {"sha256": sha, "size": written.get(n, prev.get("size")), "url": self._url(n)}
            files_infos = [FileInfo(n, f.get("url"), f.get("size"), f.get("sha256")) for n, f in sorted(files.items())]
            rel = load_document(d / data_name, mode, files_infos,
                                index_path=d / "index-v1.json" if mode == "stream" else None)
            verified = {"files": files, "verified_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "by": SDK, "datestamp": datestamp, "format_version": rel.format_version}
            try:
                atomic_write(d / ".verified", json.dumps(verified, indent=1, sort_keys=True).encode("utf-8"))
            except OSError as e:
                raise CacheError(f"cannot write {d / '.verified'}: {e}") from e
            return rel

    def _ensure_cache_root(self):
        ensure_dir(self._cache.base / "releases")

    def _open_pinned(self, datestamp: str) -> None:
        self._ensure_cache_root()
        if self._usable(datestamp, self._mode) is not None:
            self._set(self._load_cached(datestamp, self._mode), "cache")
            return
        if self._offline:
            raise OfflineError(f"offline, and release {datestamp} is not in the cache")
        self._set(self._download_to_cache(datestamp, self._mode, None), "download")

    def _open_latest(self) -> None:
        self._ensure_cache_root()
        if self._offline:
            ds = self._newest_cached(self._mode)
            if ds is None:
                raise OfflineError("offline, and no release is in the cache")
            self._set(self._load_cached(ds, self._mode), "cache")
            return
        try:
            info = self._latest_info()
            if self._usable(info.datestamp, self._mode) is not None:
                self._set(self._load_cached(info.datestamp, self._mode), "cache")
                return
            self._set(self._download_to_cache(info.datestamp, self._mode, info), "download")
        except NetworkError as e:
            ds = self._newest_cached(self._mode) if self._on_network_error == "use_cache" else None
            if ds is None:
                raise
            self._log.warning("network error (%s); using the cached release %s", e, ds)
            self._set(self._load_cached(ds, self._mode), "cache_after_error")
            self._last_error = e

    # ------------------------------------------------------------------ release management

    def releases(self) -> Tuple[ReleaseInfo, ...]:
        """Every release, newest first (OTC_index.json)."""
        if self._offline:
            body = self._cache.read_pointer_body("OTC_index.json")
            if body is None:
                raise OfflineError("offline, and the release index is not in the cache")
            try:
                doc = json.loads(body.decode("utf-8"))
            except (ValueError, UnicodeDecodeError) as e:
                raise InvalidReleaseError("cached OTC_index.json: not JSON") from e
            return tuple(self._index_infos(doc, self._url("OTC_index.json")))
        return tuple(self._fetch_index())

    def latest(self) -> ReleaseInfo:
        """The latest release (one conditional GET of the pointer). It does not switch releases."""
        if self._offline:
            raise OfflineError("offline: the latest pointer cannot be read")
        return self._latest_info()

    def check_for_update(self) -> Optional[ReleaseInfo]:
        info = self.latest()
        if datestamp_key(info.datestamp) > datestamp_key(self._release.datestamp):
            return info
        return None

    def update(self) -> UpdateResult:
        """Download a newer release, verify it and swap it in. A Release held from before stays valid."""
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
            rel, lf = self._load_cached(info.datestamp, self._mode), "cache"
        else:
            rel, lf = self._download_to_cache(info.datestamp, self._mode, info), "download"
        self._set(rel, lf)
        self._last_error = None
        self._log.info("updated from %s to %s", cur, info.datestamp)
        return UpdateResult(True, cur, info.datestamp)

    def _maybe_auto_update(self) -> None:
        if not self._auto_update or self._pinned is not None or self._file is not None or self._release is None:
            return
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
                self._log.warning("automatic update failed: %s", e)

    def verify(self) -> bool:
        """Hash the loaded release's files again and compare them with OTC_{D}.sha256."""
        rel = self._release
        ds = rel.datestamp
        if self._loaded_from in (LoadedFrom.FILE, LoadedFrom.FILE_UNVERIFIED):
            if not self._opened_files:
                return True
            first = self._opened_files[0]
            sha_path = first.with_name(f"OTC_{ds}.sha256")
            if not sha_path.exists():
                raise ChecksumError(f"no OTC_{ds}.sha256 next to {first}", file=str(first))
            rows = _parse_sha256(self._read_text(sha_path))
            for p in self._opened_files:
                self._check_file(p, rows.get(p.name))
            return True
        d = self._cache.release_dir(ds)
        sha_path = d / f"OTC_{ds}.sha256"
        rows = _parse_sha256(self._read_text(sha_path)) if sha_path.exists() else {}
        v = self._cache.read_verified(ds) or {"files": {}}
        for n, rec in v["files"].items():
            p = d / n
            if p.is_file():
                self._check_file(p, rows.get(n) or rec.get("sha256"))
        return True

    def cached_releases(self) -> Tuple[str, ...]:
        return tuple(self._cache.cached())

    def prune(self, *, keep: int = 3) -> Tuple[str, ...]:
        """Remove cached releases beyond the newest ``keep``. Never removes the loaded release."""
        if isinstance(keep, bool) or not isinstance(keep, int) or keep < 0:
            raise InvalidArgumentError("keep must be a non-negative integer")
        loaded = self._release.datestamp if self._release is not None else None
        removed = []
        for ds in self._cache.cached()[keep:]:
            if ds == loaded:
                continue
            self._cache.remove_release(ds)
            removed.append(ds)
        return tuple(removed)

    def download(self, release: str = "latest", *, to, formats: Sequence[str] = ("jsonl",),
                 overwrite: bool = False) -> Tuple[str, ...]:
        """Write a verified release into the folder ``to`` (spec §4.3.2). Returns the paths written."""
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
            sha_body = (cdir / f"{base}.sha256").read_bytes()
            rows = _parse_sha256(sha_body.decode("utf-8"))
        elif self._offline:
            raise OfflineError(f"offline, and release {ds} is not in the cache")
        else:
            sha_body, rows = self._get_sha256_rows(ds)
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
        written = []
        ptr = {f.name: f for f in info.files} if info is not None else {}
        for n, sha in todo:
            dest = to / n
            if n == f"{base}.sha256":
                tmp = tmp_name(to)
                try:
                    with open(tmp, "wb") as f:
                        f.write(sha_body)
                        f.flush()
                        os.fsync(f.fileno())
                    os.replace(tmp, dest)
                except OSError as e:
                    try:
                        tmp.unlink()
                    except OSError:
                        pass
                    raise FileError(f"cannot write {dest}: {e}", path=str(dest), cause=e) from e
                written.append(str(dest))
                continue
            src = cdir / n
            if cached and src.is_file():
                tmp = tmp_name(to)
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
                    try:
                        tmp.unlink()
                    except OSError:
                        pass
                    raise FileError(f"cannot write {dest}: {e}", path=str(dest), cause=e) from e
                actual = file_sha256(tmp)
                if actual != sha:
                    tmp.unlink()
                    raise ChecksumError(f"{n}: the cached copy does not match", file=str(dest), expected=sha,
                                        actual=actual)
            else:
                if self._offline:
                    raise OfflineError(f"offline, and {n} is not in the cache")
                url = ptr[n].url if n in ptr and ptr[n].url else self._url(n)
                tmp = self._fetch_file(url, to, sha, ptr[n].size if n in ptr else None, str(dest),
                                       gz=n.endswith(".gz"))
            os.replace(tmp, dest)
            written.append(str(dest))
        return tuple(written)

    # ------------------------------------------------------------------ forwarded queries (spec §4.4)

    def _r(self) -> Release:
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
