"""The shared cache layout (spec §5.4): atomic writes, lock directories and datestamp order."""
from __future__ import annotations

import json
import os
import re
import secrets
import shutil
import socket
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from ._errors import CacheError, InvalidReleaseError

LAYOUT = "v1"
# spec §4.2 (CR D18): the counter has at most 9 digits. \Z, not $: $ also matches before a trailing newline.
DATESTAMP_RE = re.compile(r"\A[0-9]{8}(\.[2-9]|\.[1-9][0-9]{1,8})?\Z")
LOCK_POLL_S = 0.5
LOCK_STALE_S = 120.0


def datestamp_key(d: str):
    """Sort key: the date, then the counter; no counter means counter 1 (spec §4.3.1). A string that is not a
    datestamp is InvalidReleaseError (it came from a release, a pointer or an index)."""
    if not isinstance(d, str) or not DATESTAMP_RE.match(d):
        raise InvalidReleaseError(f"not a datestamp: {d!r}")
    date, _, counter = d.partition(".")
    return (date, int(counter) if counter else 1)


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
        except OSError:
            pass
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

    def __init__(self, root: Path):
        self.root = Path(root)
        self.base = self.root / LAYOUT

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
        p = self.release_dir(datestamp) / ".verified"
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return doc if isinstance(doc, dict) and isinstance(doc.get("files"), dict) else None

    def cached(self):
        """Datestamps of verified releases, newest first."""
        d = self.base / "releases"
        try:
            names = [p.name for p in d.iterdir() if DATESTAMP_RE.match(p.name) and (p / ".verified").is_file()]
        except OSError:
            return []
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
            except OSError:
                pass
            raise CacheError(f"cannot remove the cached release {d}: {e}") from e
        try:
            shutil.rmtree(d)
        except OSError as e:
            raise CacheError(f"cannot remove the cached release {d}: {e}") from e
        return True

    def read_pointer(self, name: str):
        d = self.pointer_dir()
        try:
            body = (d / name).read_bytes()
            etag = (d / (name + ".etag")).read_text(encoding="utf-8").strip()
            return body, etag
        except OSError:
            return None, None

    def read_pointer_body(self, name: str):
        try:
            return (self.pointer_dir() / name).read_bytes()
        except OSError:
            return None

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
                if etag:
                    atomic_write(d / (name + ".etag"), etag.encode("utf-8"))
        except OSError as e:
            raise CacheError(f"cannot write {d / name}: {e}") from e

    def drop_pointer(self, name: str) -> None:
        for n in (name + ".etag", name):
            try:
                (self.pointer_dir() / n).unlink()
            except OSError:
                pass


@contextmanager
def lock_dir(directory: Path, sdk: str, done=None, name=".lock"):
    """Take <directory>/.lock (spec §5.4 Locks, CR D3). Yields True when the lock is held, or False when
    ``done()`` became true while waiting (another process finished the work). After 120 s of waiting the lock is
    stale and is removed; failing to remove it 3 times is CacheError. On release the lock is removed only if its
    owner.json still carries this lock's token (another process may have taken it as stale)."""
    lock = directory / name
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
        if waited >= LOCK_STALE_S:
            try:
                shutil.rmtree(lock)  # stale: safe because every write is an atomic rename
            except FileNotFoundError:
                pass
            except OSError as e:
                stale_failures += 1
                if stale_failures >= 3:
                    raise CacheError(f"cannot remove the stale lock {lock}: {e}") from e
                time.sleep(LOCK_POLL_S)
                continue
            waited = 0.0
            continue
        time.sleep(LOCK_POLL_S)
        waited += LOCK_POLL_S
    token = secrets.token_hex(16)
    if held:
        try:
            owner = {"pid": os.getpid(), "host": socket.gethostname(), "sdk": sdk, "token": token,
                     "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            atomic_write(lock / "owner.json", json.dumps(owner).encode("utf-8"))
        except OSError as e:
            try:
                os.rmdir(lock)
            except OSError:
                pass
            raise CacheError(f"cannot write {lock / 'owner.json'}: {e}") from e
    try:
        yield held
    finally:
        if held:
            _release_lock(lock, token)


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
    except OSError:
        pass  # a lock left behind only costs a 120 s wait (spec §5.4)


def try_lock(directory: Path) -> bool:
    """Take <directory>/.lock without waiting; False when another process holds it."""
    try:
        os.mkdir(directory / ".lock")
        return True
    except FileExistsError:
        return False
    except OSError as e:
        raise CacheError(f"cannot create the lock {directory / '.lock'}: {e}") from e
