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

from ._errors import CacheError

LAYOUT = "v1"
DATESTAMP_RE = re.compile(r"^[0-9]{8}(\.[2-9]|\.[1-9][0-9]+)?$")
LOCK_POLL_S = 0.5
LOCK_STALE_S = 120.0


def datestamp_key(d: str):
    """Sort key: the date, then the counter; no counter means counter 1 (spec §4.3.1)."""
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

    def remove_release(self, datestamp: str) -> None:
        d = self.release_dir(datestamp)
        try:
            (d / ".verified").unlink()
        except OSError:
            pass
        shutil.rmtree(d, ignore_errors=True)

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
        d = self.pointer_dir(create=True)
        try:
            atomic_write(d / name, body)
            if etag:
                atomic_write(d / (name + ".etag"), etag.encode("utf-8"))
            else:
                try:
                    (d / (name + ".etag")).unlink()
                except OSError:
                    pass
        except OSError as e:
            raise CacheError(f"cannot write {d / name}: {e}") from e


@contextmanager
def lock_dir(directory: Path, sdk: str, done=None):
    """Take <directory>/.lock (spec §5.4 Locks). Yields True when the lock is held, or False when
    ``done()`` became true while waiting (another process finished the work)."""
    lock = directory / ".lock"
    waited = 0.0
    held = False
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
            shutil.rmtree(lock, ignore_errors=True)  # stale: safe because every write is an atomic rename
            waited = 0.0
            continue
        time.sleep(LOCK_POLL_S)
        waited += LOCK_POLL_S
    try:
        if held:
            try:
                owner = {"pid": os.getpid(), "host": socket.gethostname(), "sdk": sdk,
                         "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
                (lock / "owner.json").write_text(json.dumps(owner), encoding="utf-8")
            except OSError:
                pass
        yield held
    finally:
        if held:
            try:
                (lock / "owner.json").unlink()
            except OSError:
                pass
            try:
                os.rmdir(lock)
            except OSError:
                pass
