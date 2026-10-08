"""HTTP (spec §5.7): proxies, CA file, connect and read timeouts, retries, gzip, User-Agent.
Standard library only (http.client), so the proxy rules are the same on every platform."""
from __future__ import annotations

import gzip
import hashlib
import http.client
import logging
import os
import socket
import ssl
import time
import zlib
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlsplit
from urllib.request import proxy_bypass_environment

from ._errors import NetworkError

CONNECT_TIMEOUT_S = 10.0
READ_TIMEOUT_S = 60.0
ATTEMPTS = 3
BACKOFF_S = (1.0, 2.0)  # the waits between the 3 attempts (conformance README)
RETRY_AFTER_MAX_S = 60.0
CHUNK = 1 << 16


@dataclass
class Response:
    status: int
    headers: dict
    body: bytes = b""
    sha256: Optional[str] = None
    size: int = 0


class _Retry(Exception):
    def __init__(self, error: NetworkError, retry_after: Optional[float] = None):
        super().__init__(str(error))
        self.error = error
        self.retry_after = retry_after


def _env(*names):
    for n in names:
        v = os.environ.get(n)
        if v:
            return v
    return None


class Http:
    def __init__(self, *, user_agent: str, timeout=None, proxy=None, ca_file=None,
                 logger: Optional[logging.Logger] = None):
        self.user_agent = user_agent
        self.connect_timeout = CONNECT_TIMEOUT_S if timeout is None else float(timeout)
        self.read_timeout = READ_TIMEOUT_S if timeout is None else float(timeout)
        self.proxy = proxy
        self.ca_file = ca_file or os.environ.get("SSL_CERT_FILE")
        self.log = logger or logging.getLogger("opentideconstants")
        self._ctx = None

    # ---- connection

    def _context(self):
        if self._ctx is None:
            self._ctx = ssl.create_default_context(cafile=self.ca_file) if self.ca_file else ssl.create_default_context()
        return self._ctx

    def _proxy_for(self, u) -> Optional[str]:
        if self.proxy:
            return self.proxy
        p = _env("https_proxy", "HTTPS_PROXY") if u.scheme == "https" else _env("http_proxy", "HTTP_PROXY")
        if not p:
            return None
        no = _env("no_proxy", "NO_PROXY")
        if no and u.hostname and proxy_bypass_environment(u.hostname, {"no": no}):
            return None
        return p

    def _connect(self, url: str):
        u = urlsplit(url)
        if u.scheme not in ("http", "https") or not u.hostname:
            raise NetworkError(f"not an http(s) URL: {url}", url=url)
        path = (u.path or "/") + (f"?{u.query}" if u.query else "")
        proxy = self._proxy_for(u)
        port = u.port or (443 if u.scheme == "https" else 80)
        if proxy:
            p = urlsplit(proxy if "://" in proxy else "http://" + proxy)
            ph, pp = p.hostname, p.port or (443 if p.scheme == "https" else 80)
            if u.scheme == "https":
                conn = http.client.HTTPSConnection(ph, pp, timeout=self.connect_timeout, context=self._context())
                conn.set_tunnel(u.hostname, port)
            else:
                conn = http.client.HTTPConnection(ph, pp, timeout=self.connect_timeout)
                path = url
        elif u.scheme == "https":
            conn = http.client.HTTPSConnection(u.hostname, port, timeout=self.connect_timeout, context=self._context())
        else:
            conn = http.client.HTTPConnection(u.hostname, port, timeout=self.connect_timeout)
        conn.connect()
        conn.sock.settimeout(self.read_timeout)
        return conn, path

    # ---- one attempt

    def _once(self, url, headers, sink):
        conn = None
        try:
            conn, path = self._connect(url)
            h = {"User-Agent": self.user_agent, **headers}
            conn.request("GET", path, headers=h)
            resp = conn.getresponse()
            status = resp.status
            rh = {k.lower(): v for k, v in resp.getheaders()}
            if status in (304, 404):
                resp.read()
                return Response(status, rh)
            if status == 429 or status >= 500:
                resp.read()
                ra = rh.get("retry-after")
                try:
                    ra = min(float(ra), RETRY_AFTER_MAX_S) if ra is not None else None
                except ValueError:
                    ra = None
                raise _Retry(NetworkError(f"HTTP {status} for {url}", url=url, status=status), ra)
            if status != 200:
                resp.read()
                raise NetworkError(f"HTTP {status} for {url}", url=url, status=status)
            gz = rh.get("content-encoding", "").lower() == "gzip"
            dec = zlib.decompressobj(16 + zlib.MAX_WBITS) if gz else None
            sha = hashlib.sha256()
            size = 0
            parts = []
            while True:
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                if dec is not None:
                    chunk = dec.decompress(chunk)
                sha.update(chunk)
                size += len(chunk)
                if sink is not None:
                    sink.write(chunk)
                else:
                    parts.append(chunk)
            if dec is not None:
                tail = dec.flush()
                if not dec.eof:
                    raise NetworkError(f"truncated gzip body from {url}", url=url, status=status)
                sha.update(tail)
                size += len(tail)
                if sink is not None:
                    sink.write(tail)
                else:
                    parts.append(tail)
            return Response(status, rh, b"".join(parts), sha.hexdigest(), size)
        except (_Retry, NetworkError):
            raise
        except (http.client.IncompleteRead, http.client.HTTPException, OSError, zlib.error, EOFError) as e:
            err = NetworkError(f"{type(e).__name__} for {url}: {e}", url=url)
            err.__cause__ = e
            raise _Retry(err) from e
        finally:
            if conn is not None:
                conn.close()

    def get(self, url: str, *, headers=None, accept_gzip=False, sink=None) -> Response:
        """GET with retries (3 attempts; waits 1 s and 2 s; Retry-After up to 60 s). 304 and 404 are returned,
        never retried. With ``sink`` (a binary file opened for writing), the decoded body streams into it and
        Response.sha256/size describe it."""
        h = dict(headers or {})
        if accept_gzip:
            h["Accept-Encoding"] = "gzip"
        else:
            h["Accept-Encoding"] = "identity"
        last = None
        for attempt in range(ATTEMPTS):
            if sink is not None:
                sink.seek(0)
                sink.truncate()
            try:
                r = self._once(url, h, sink)
                self.log.debug("GET %s -> %s", url, r.status)
                return r
            except _Retry as e:
                last = e.error
                if attempt + 1 < ATTEMPTS:
                    wait = BACKOFF_S[attempt]
                    if e.retry_after is not None:
                        wait = max(wait, e.retry_after)
                    self.log.debug("GET %s failed (%s); retry in %.1f s", url, e.error, wait)
                    time.sleep(wait)
        raise last


def gunzip(data: bytes) -> bytes:
    return gzip.decompress(data)


__all__ = ["Http", "Response", "gunzip", "socket"]
