"""HTTP (spec §5.7): proxies, CA file, connect and read timeouts, retries, gzip, User-Agent.
Standard library only (http.client), so the proxy rules are the same on every platform."""
from __future__ import annotations

import base64
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
from urllib.parse import unquote, urljoin, urlsplit
from urllib.request import proxy_bypass_environment

from ._errors import FileError, InvalidArgumentError, NetworkError, redact_credentials, redact_url

CONNECT_TIMEOUT_S = 10.0
READ_TIMEOUT_S = 60.0
ATTEMPTS = 3
BACKOFF_S = (1.0, 2.0)  # the waits between the 3 attempts (conformance README)
RETRY_AFTER_MAX_S = 60.0
CHUNK = 1 << 16
MAX_REDIRECTS = 5
_REDIRECTS = (301, 302, 303, 307, 308)


@dataclass
class Response:
    status: int
    headers: dict
    body: bytes = b""
    sha256: Optional[str] = None
    size: int = 0


class _SinkError(Exception):
    """A local write to the sink failed: local IO, not a network error, and never retried."""

    def __init__(self, error: OSError):
        super().__init__(str(error))
        self.error = error


def check_http_url(name: str, url) -> None:
    """An absolute http or https URL with a host and a valid port, else InvalidArgumentError (CR D19)."""
    try:
        u = urlsplit(url) if isinstance(url, str) else None
        ok = u is not None and u.scheme in ("http", "https") and bool(u.hostname)
        if ok:
            u.port  # noqa: B018 - raises ValueError for a bad port
    except ValueError:
        ok = False
    if not ok:
        shown = redact_url(url) if isinstance(url, str) else url  # no user or password in the message (CR2 DR21)
        raise InvalidArgumentError(f"{name} must be an absolute http or https URL, not {shown!r}")


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
        if proxy is not None:
            check_http_url("proxy", proxy)
        self.proxy = proxy
        self.log = logger or logging.getLogger("opentideconstants")
        self._ctx = None
        if ca_file is not None:
            # checked at construction, before any network access; never retried (spec §4.2, CR D19)
            try:
                with open(ca_file, "rb"):
                    pass
            except (OSError, TypeError) as e:
                raise FileError(f"cannot read ca_file {ca_file}: {e}", path=str(ca_file),
                                cause=e if isinstance(e, OSError) else None) from e
            try:
                self._ctx = ssl.create_default_context(cafile=ca_file)
            except ssl.SSLError as e:
                raise InvalidArgumentError(f"ca_file {ca_file} is not a PEM certificate file: {e}") from e
        self.ca_file = ca_file or os.environ.get("SSL_CERT_FILE")

    # ---- connection

    def _context(self):
        if self._ctx is None:
            self._ctx = ssl.create_default_context(cafile=self.ca_file) if self.ca_file else ssl.create_default_context()
        return self._ctx

    def _proxy_for(self, u) -> Optional[str]:
        if self.proxy:
            return self.proxy
        if u.scheme == "https":
            p = _env("https_proxy", "HTTPS_PROXY")
        elif os.environ.get("REQUEST_METHOD"):
            # httpoxy (spec §5.7, CR D7): in a CGI process, HTTP_PROXY may come from a client's Proxy: header
            p = _env("http_proxy")
        else:
            p = _env("http_proxy", "HTTP_PROXY")
        if not p:
            return None
        no = _env("no_proxy", "NO_PROXY")
        if no and u.hostname and proxy_bypass_environment(u.hostname, {"no": no}):
            return None
        return p

    def _connect(self, url: str):
        u = urlsplit(url)
        try:
            if u.scheme not in ("http", "https") or not u.hostname:
                raise ValueError("not an http(s) URL")
            port = u.port or (443 if u.scheme == "https" else 80)
            proxy = self._proxy_for(u)
            p = urlsplit(proxy if "://" in proxy else "http://" + proxy) if proxy else None
            if p is not None:
                if p.scheme not in ("http", "https") or not p.hostname:
                    raise ValueError(f"bad proxy {redact_url(proxy)!r}")
                ph, pp = p.hostname, p.port or (443 if p.scheme == "https" else 80)
                if p.scheme == "https" and u.scheme == "https":
                    raise ValueError("an https proxy for an https URL is not supported; use an http proxy")
        except ValueError as e:  # a bad URL, port or proxy: retrying cannot help
            raise NetworkError(f"bad URL {url} (or its proxy): {e}", url=url) from e
        path = (u.path or "/") + (f"?{u.query}" if u.query else "")
        extra = {}
        if proxy:
            auth = _proxy_auth(p)
            if u.scheme == "https":
                # CONNECT through the proxy, then TLS to the server
                conn = http.client.HTTPSConnection(ph, pp, timeout=self.connect_timeout, context=self._context())
                conn.set_tunnel(u.hostname, port, headers=auth)
            else:
                if p.scheme == "https":
                    conn = http.client.HTTPSConnection(ph, pp, timeout=self.connect_timeout, context=self._context())
                else:
                    conn = http.client.HTTPConnection(ph, pp, timeout=self.connect_timeout)
                path = url
                extra = auth
        elif u.scheme == "https":
            conn = http.client.HTTPSConnection(u.hostname, port, timeout=self.connect_timeout, context=self._context())
        else:
            conn = http.client.HTTPConnection(u.hostname, port, timeout=self.connect_timeout)
        conn.connect()
        conn.sock.settimeout(self.read_timeout)
        return conn, path, extra

    # ---- one attempt

    def _once(self, url, headers, sink, decode):
        conn = None
        try:
            conn, path, extra = self._connect(url)
            h = {"User-Agent": self.user_agent, **headers, **extra}
            conn.request("GET", path, headers=h)
            resp = conn.getresponse()
            status = resp.status
            rh = {k.lower(): v for k, v in resp.getheaders()}
            if status in (304, 404) or status in _REDIRECTS:
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
            enc = rh.get("content-encoding", "identity").strip().lower()
            if enc not in ("identity", "gzip", ""):
                raise NetworkError(f"unsupported Content-Encoding {enc!r} from {url}", url=url, status=status)
            # decode only what this SDK asked for: a .json.gz sent with Content-Encoding: gzip stays gzip bytes
            dec = _Gunzip() if enc == "gzip" and decode else None
            sha = hashlib.sha256()
            size = 0
            parts = []
            raw_size = 0
            while True:
                chunk = resp.read(CHUNK)
                if not chunk:
                    break
                raw_size += len(chunk)
                if dec is not None:
                    chunk = dec.decompress(chunk)
                sha.update(chunk)
                size += len(chunk)
                if sink is not None:
                    _write(sink, chunk)
                else:
                    parts.append(chunk)
            clen = rh.get("content-length")
            if clen is not None and clen.isdigit() and int(clen) != raw_size:
                raise http.client.IncompleteRead(b"", int(clen) - raw_size)
            if dec is not None:
                tail = dec.finish()
                if tail is None:
                    raise _Retry(NetworkError(f"truncated gzip body from {url}", url=url, status=status))
                sha.update(tail)
                size += len(tail)
                if sink is not None:
                    _write(sink, tail)
                else:
                    parts.append(tail)
            return Response(status, rh, b"".join(parts), sha.hexdigest(), size)
        except (_Retry, NetworkError, _SinkError):
            raise
        except ssl.SSLCertVerificationError as e:  # TLS: a network error, but retrying cannot help
            raise NetworkError(f"TLS certificate check failed for {url}: {e}", url=url) from e
        except http.client.InvalidURL as e:
            raise NetworkError(f"bad URL {url}: {e}", url=url) from e
        except (http.client.IncompleteRead, http.client.HTTPException, OSError, zlib.error, EOFError) as e:
            err = NetworkError(f"{type(e).__name__} for {url}: {e}", url=url)
            err.__cause__ = e
            raise _Retry(err) from e
        finally:
            if conn is not None:
                conn.close()

    def _follow(self, url, headers, sink, decode):
        """One attempt, following up to 5 redirects (spec §5.7, CR D1). A 6th redirect, or a redirect from https to
        http, is a network error that is not retried."""
        for hop in range(MAX_REDIRECTS + 1):
            r = self._once(url, headers, sink, decode)
            if r.status not in _REDIRECTS:
                return r
            loc = r.headers.get("location")
            if not loc:
                raise NetworkError(f"HTTP {r.status} with no Location for {url}", url=url, status=r.status)
            nxt = urljoin(url, loc)
            if urlsplit(url).scheme == "https" and urlsplit(nxt).scheme != "https":
                raise NetworkError(f"refused a redirect from https to {nxt}", url=url, status=r.status)
            self.log.debug("GET %s -> %s %s", redact_credentials(url), r.status, redact_credentials(nxt))
            url = nxt
        raise NetworkError(f"more than {MAX_REDIRECTS} redirects for {url}", url=url, status=r.status)

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
                r = self._follow(url, h, sink, accept_gzip)
                self.log.debug("GET %s -> %s", redact_credentials(url), r.status)
                return r
            except _SinkError as e:
                raise e.error from None  # a local write failed (ENOSPC, EIO): the caller's io/cache error
            except _Retry as e:
                last = e.error
                if attempt + 1 < ATTEMPTS:
                    wait = BACKOFF_S[attempt]
                    if e.retry_after is not None:
                        wait = max(wait, e.retry_after)
                    self.log.debug("GET %s failed (%s); retry in %.1f s", redact_credentials(url), e.error, wait)
                    time.sleep(wait)
        raise last


class _Gunzip:
    """Decode a gzip body of one or more members (RFC 1952 allows several, one after another)."""

    def __init__(self):
        self._d = zlib.decompressobj(16 + zlib.MAX_WBITS)

    def decompress(self, data: bytes) -> bytes:
        out = []
        while data:
            out.append(self._d.decompress(data))
            if not self._d.eof:
                break
            data = self._d.unused_data
            if data:
                self._d = zlib.decompressobj(16 + zlib.MAX_WBITS)
        return b"".join(out)

    def finish(self):
        """The rest of the output, or None when the last member is cut short."""
        tail = self._d.flush()
        return tail if self._d.eof else None


def _proxy_auth(p) -> dict:
    """Proxy-Authorization for the user:password in a proxy URL (percent-decoded), or no header."""
    if p.username is None:
        return {}
    cred = f"{unquote(p.username)}:{unquote(p.password or '')}".encode("utf-8")
    return {"Proxy-Authorization": "Basic " + base64.b64encode(cred).decode("ascii")}


def _write(sink, data: bytes) -> None:
    try:
        sink.write(data)
    except OSError as e:
        raise _SinkError(e) from e


def gunzip(data: bytes) -> bytes:
    return gzip.decompress(data)

