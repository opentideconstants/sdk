"""The shared cache layout (spec §5.4): atomic writes, lock directories and datestamp order."""
from __future__ import annotations

import calendar
import datetime
import json
import logging
import os
import re
import secrets
import shutil
import socket
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from ._cache_json import encode_cache_json
from ._errors import CacheError, InvalidReleaseError
from ._release import integral

_log = logging.getLogger("opentideconstants")

LAYOUT = "v1"
# spec §4.2 (CR D18): the counter has at most 9 digits. \Z, not $: $ also matches before a trailing newline.
DATESTAMP_RE = re.compile(r"\A[0-9]{8}(\.[2-9]|\.[1-9][0-9]{1,8})?\Z")
LOCK_POLL_S = 0.5
LOCK_STALE_S = 120.0      # how long a waiter waits before it may treat a lock as stale (spec §5.4)
LOCK_STALE_AGE_S = 120.0  # how old the lock itself must be to be stale (spec §5.4, CR2 DR3)
_STARTED_AT_RE = re.compile(r"\A([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(\.[0-9]+)?(Z|\+00:00)\Z")


def datestamp_key(d: str):
    """Sort key: the date, then the counter; no counter means counter 1 (spec §4.3.1). A string that is not a
    datestamp is InvalidReleaseError (it came from a release, a pointer or an index)."""
    if not isinstance(d, str) or not DATESTAMP_RE.match(d):
        raise InvalidReleaseError(f"not a datestamp: {d!r}")
    date, _, counter = d.partition(".")
    return (date, int(counter) if counter else 1)


def _opt(v, t) -> bool:
    return v is None or isinstance(v, t)


def default_root() -> Path:
    env = os.environ.get("OPENTIDECONSTANTS_CACHE_DIR")
    if env:
        return Path(env)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "opentideconstants" / "Cache"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "opentideconstants"
    xdg = os.environ.get("XDG_CACHE_HOME")
    return Path(xdg) / "opentideconstants" if xdg else Path.home() / ".cache" / "opentideconstants"


def tmp_name(directory: Path) -> Path:
    return directory / f".tmp-{os.getpid()}-{secrets.token_hex(6)}"


def _fsync(f) -> None:
    f.flush()
    os.fsync(f.fileno())


def atomic_write(path: Path, data: bytes) -> None:
    """Write to a temporary file in the same directory, fsync it, then rename it into place."""
    tmp = tmp_name(path.parent)
    try:
        with open(tmp, "wb") as f:
            f.write(data)
            _fsync(f)
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        except OSError as e:  # a leftover temporary file is logged, never silent (R3-224)
            _log.warning("cannot remove %s: %s", tmp, e)
        raise


def ensure_dir(path: Path) -> Path:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise CacheError(f"cannot create the cache directory {path}: {e}") from e
    if not path.is_dir():
        raise CacheError(f"the cache path {path} is not a directory")
    return path


class Cache:
    """<root>/v1/{pointer,releases}."""

    def __init__(self, root: Path, log: logging.Logger | None = None):
        self.root = Path(root)
        self.base = self.root / LAYOUT
        self._log = log or _log

    def pointer_dir(self, create=False) -> Path:
        p = self.base / "pointer"
        return ensure_dir(p) if create else p

    def release_dir(self, datestamp: str, create=False) -> Path:
        if not isinstance(datestamp, str) or not DATESTAMP_RE.match(datestamp):
            # never build a path from a string that is not a datestamp (spec §5.4: nothing outside the cache)
            raise InvalidReleaseError(f"not a datestamp: {datestamp!r}")
        p = self.base / "releases" / datestamp
        return ensure_dir(p) if create else p

    def read_verified(self, datestamp: str):
        """The .verified object, or None when it is absent or not a usable record (then the release is not
        trusted). A .verified that exists but cannot be read is CacheError, not "not cached" (spec §5.2 step 6)."""
        p = self.release_dir(datestamp) / ".verified"
        try:
            text = p.read_text(encoding="utf-8")
        except (FileNotFoundError, NotADirectoryError):
            return None
        except OSError as e:
            raise CacheError(f"cannot read {p}: {e}") from e
        except UnicodeDecodeError:
            return None
        try:
            doc = json.loads(text)
        except (ValueError, RecursionError):
            return None
        if not isinstance(doc, dict) or not isinstance(doc.get("files"), dict):
            return None
        for rec in doc["files"].values():
            # a null or absent size makes .verified malformed (spec 5.4, CR3 spec review 2 B10 and 3 C4)
            if not isinstance(rec, dict) or not _opt(rec.get("sha256"), str) or not _opt(rec.get("url"), str) \
                    or integral(rec.get("size")) is None:
                return None
            rec["size"] = integral(rec["size"])  # 1024.0 is the integer 1024 (CR2 DR10)
        for k in ("zenodo_version_doi", "format_version", "min_reader_version", "datestamp"):
            if not _opt(doc.get(k), str):
                return None
        return doc

    def cached(self):
        """Datestamps of verified releases, newest first."""
        d = self.base / "releases"
        try:
            names = [p.name for p in d.iterdir() if DATESTAMP_RE.match(p.name) and (p / ".verified").is_file()]
        except (FileNotFoundError, NotADirectoryError):
            return []
        except OSError as e:
            raise CacheError(f"cannot list {d}: {e}") from e
        return sorted(names, key=datestamp_key, reverse=True)

    def remove_release(self, datestamp: str) -> bool:
        """Remove a cached release; False when another process holds its lock (it is downloading). CacheError
        when it cannot be removed. .verified goes first, so a half-removed directory is never trusted."""
        d = self.release_dir(datestamp)
        if not try_lock(d):
            return False
        try:
            (d / ".verified").unlink()
        except FileNotFoundError:
            pass
        except OSError as e:
            try:
                os.rmdir(d / ".lock")
            except OSError as x:  # a lock left behind costs the next process a 120 s wait (R3-224)
                self._log.warning("cannot remove %s: %s", d / ".lock", x)
            raise CacheError(f"cannot remove the cached release {d}: {e}") from e
        try:
            shutil.rmtree(d)
        except OSError as e:
            raise CacheError(f"cannot remove the cached release {d}: {e}") from e
        return True

    def read_pointer(self, name: str):
        """The cached body and ETag of a pointer or index file, or (None, None) when either is not there. A file
        that is there but cannot be read is CacheError, never "absent" (spec §5.2 step 6)."""
        d = self.pointer_dir()
        p = d / (name + ".etag")
        try:
            first = p.read_bytes()
            body = self.read_pointer_body(name)
            second = p.read_bytes()
            if (body is None or first != second or not 1 <= len(first) <= 256
                    or any(b < 0x20 or b >= 0x7F for b in first)):
                return None, None
            return body, first.decode("ascii")
        except (FileNotFoundError, NotADirectoryError):
            return None, None
        except OSError as e:
            raise CacheError(f"cannot read {p}: {e}") from e

    def read_pointer_body(self, name: str):
        """The cached body of a pointer or index file, or None when it is not there (CacheError when it cannot be
        read)."""
        p = self.pointer_dir() / name
        try:
            return p.read_bytes()
        except (FileNotFoundError, NotADirectoryError):
            return None
        except OSError as e:
            raise CacheError(f"cannot read {p}: {e}") from e

    def write_pointer(self, name: str, body: bytes, etag) -> None:
        """Store a pointer or index body and its ETag. The old ETag is removed first, so a body is never paired
        with an ETag of another body (a crash in between leaves no ETag: the next GET is unconditional). A lock
        on the pointer directory keeps two writers of this SDK from interleaving."""
        d = self.pointer_dir(create=True)
        try:
            with lock_dir(d, "opentideconstants-python"):
                try:
                    (d / (name + ".etag")).unlink()
                except FileNotFoundError:
                    pass
                atomic_write(d / name, body)
                if etag and len(etag) <= 256 and all(0x20 <= ord(c) < 0x7F for c in etag):
                    atomic_write(d / (name + ".etag"), etag.encode("ascii"))
        except OSError as e:
            raise CacheError(f"cannot write {d / name}: {e}") from e

    def drop_pointer(self, name: str) -> None:
        for n in (name + ".etag", name):
            p = self.pointer_dir() / n
            try:
                p.unlink()
            except (FileNotFoundError, NotADirectoryError):
                pass
            except OSError as e:  # the broken copy stays: say why (R3-224)
                self._log.warning("cannot remove %s: %s", p, e)


@contextmanager
def lock_dir(directory: Path, sdk: str, done=None, name=".lock", wait=True):
    """Take <directory>/.lock (spec §5.4 Locks, CR D3, CR2 DR3). Yields True when the lock is held, or False when
    ``done()`` became true while waiting (another process finished the work), or, with ``wait=False``, when the lock
    is held and is not stale. A lock is stale when this waiter has waited LOCK_STALE_S and the lock itself is at
    least LOCK_STALE_AGE_S old; a non-blocking take applies only the age test. A stale lock is removed; failing
    to remove it 3 times is CacheError. After a removal the wait starts again. On release the lock is removed only
    if its owner.json still carries this lock's token (another process may have taken it as stale)."""
    lock = directory / name
    stopped = threading.Event()
    heartbeat = None
    waited = 0.0
    held = False
    stale_failures = 0
    while True:
        try:
            os.mkdir(lock)
            held = True
            break
        except FileExistsError:
            pass
        except OSError as e:
            raise CacheError(f"cannot create the lock {lock}: {e}") from e
        if done is not None and done():
            break
        if (not wait or waited >= LOCK_STALE_S) and lock_is_stale(lock):  # the age is read just before the removal
            try:
                shutil.rmtree(lock)  # stale: safe because every write is an atomic rename
            except FileNotFoundError:
                pass
            except OSError as e:
                stale_failures += 1
                if stale_failures >= 3 or not wait:
                    raise CacheError(f"cannot remove the stale lock {lock}: {e}") from e
                time.sleep(LOCK_POLL_S)
                continue
            waited = 0.0
            if not wait:  # one more try only: a process that takes it now holds a young lock
                try:
                    os.mkdir(lock)
                    held = True
                except FileExistsError:
                    pass
                except OSError as e:
                    raise CacheError(f"cannot create the lock {lock}: {e}") from e
                break
            continue
        if not wait:
            break
        time.sleep(LOCK_POLL_S)
        waited += LOCK_POLL_S
    token = secrets.token_hex(16)
    if held:
        try:
            owner = {"pid": os.getpid(), "host": socket.gethostname(), "sdk": sdk, "token": token,
                     "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            atomic_write(lock / "owner.json", encode_cache_json(owner))
        except OSError as e:
            try:
                os.rmdir(lock)
            except OSError:
                pass
            raise CacheError(f"cannot write {lock / 'owner.json'}: {e}") from e
    try:
        if held:
            def refresh():
                while not stopped.wait(30):
                    try:
                        if not _refresh_lock(lock, token):
                            return
                    except (OSError, ValueError) as e:
                        _log.warning("cannot refresh %s: %s", lock, e)

            heartbeat = threading.Thread(target=refresh, name="opentideconstants-lock-heartbeat", daemon=True)
            heartbeat.start()
        yield held
    finally:
        stopped.set()
        if heartbeat is not None and heartbeat.ident is not None:
            heartbeat.join()
        if held:
            _release_lock(lock, token)


def _refresh_lock(lock: Path, token: str) -> bool:
    owner = json.loads((lock / "owner.json").read_text(encoding="utf-8"))
    if not isinstance(owner, dict) or owner.get("token") != token:
        return False
    owner["started_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    tmp = tmp_name(lock)
    try:
        with open(tmp, "wb") as f:
            f.write(encode_cache_json(owner))
            _fsync(f)
        current = json.loads((lock / "owner.json").read_text(encoding="utf-8"))
        if not isinstance(current, dict) or current.get("token") != token:
            return False
        os.replace(tmp, lock / "owner.json")
        os.utime(lock, None)
        return True
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        except OSError as e:
            _log.warning("cannot remove %s: %s", tmp, e)


def lock_age(lock: Path):
    """Seconds since the lock was taken (spec §5.4, CR2 DR3): from owner.json ``started_at``, or from the mtime of
    the lock directory when owner.json is missing or cannot be read. None when the lock is gone or its age cannot
    be read: such a lock is never treated as stale."""
    started = None
    try:
        owner = json.loads((lock / "owner.json").read_text(encoding="utf-8"))
        m = _STARTED_AT_RE.match(owner.get("started_at", "")) if isinstance(owner, dict) and \
            isinstance(owner.get("started_at"), str) else None
        if m:
            started = calendar.timegm(datetime.datetime(*(int(m.group(i)) for i in range(1, 7))).timetuple())
    except (OSError, ValueError, UnicodeDecodeError, OverflowError):
        started = None
    if started is None:
        try:
            started = os.stat(lock).st_mtime
        except OSError:
            return None
    return time.time() - started


def lock_is_stale(lock: Path) -> bool:
    age = lock_age(lock)
    return age is not None and age >= LOCK_STALE_AGE_S


def _release_lock(lock: Path, token: str) -> None:
    try:
        owner = json.loads((lock / "owner.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return  # gone or rewritten: another process took the lock as stale
    if not isinstance(owner, dict) or owner.get("token") != token:
        return
    try:
        (lock / "owner.json").unlink()
        os.rmdir(lock)
    except OSError as e:  # a lock left behind only costs a 120 s wait (spec §5.4), but it is logged (R3-224)
        _log.warning("cannot remove %s: %s", lock, e)


def try_lock(directory: Path) -> bool:
    """Take <directory>/.lock without waiting (spec §5.4 non-blocking take, CR2 DR3): a lock at least 120 s old
    is stale and is removed and taken; False when another process holds a younger one. The caller removes the
    whole directory, the lock with it, so no owner.json is written."""
    lock = directory / ".lock"
    for attempt in range(2):
        try:
            os.mkdir(lock)
            return True
        except FileExistsError:
            pass
        except OSError as e:
            raise CacheError(f"cannot create the lock {lock}: {e}") from e
        if attempt or not lock_is_stale(lock):
            return False
        try:
            shutil.rmtree(lock)
        except FileNotFoundError:
            pass
        except OSError as e:
            raise CacheError(f"cannot remove the stale lock {lock}: {e}") from e
    return False
