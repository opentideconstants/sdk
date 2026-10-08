# /// script
# requires-python = ">=3.10"
# ///
"""Conformance fixture HTTP server, recording proxy and tripwire (SDK spec §7.1).

Python standard library only. The driver imports it; it also runs on its own:

    uv run conformance/server.py [--port 8765] [--proxy-port 8766]

What it does:
- Serves conformance/fixtures/ over HTTP. Each fixture root is a path prefix, so
  base_url http://127.0.0.1:<port>/good/ serves conformance/fixtures/good/.
- Sends a strong ETag (the SHA-256 of the file) and answers 304 to a matching
  If-None-Match.
- Gzips the body when the request accepts gzip and the file is not already .gz
  (as a CDN edge does). The ETag stays the identity ETag.
- Sends the CORS headers of the live data host (measured 2026-10-08 on
  data.opentideconstants.org): Access-Control-Allow-Origin *, Vary Origin,
  Access-Control-Expose-Headers ETag,Content-Length,Content-Encoding; a
  preflight (OPTIONS) gets 204 with Allow-Methods GET, HEAD, Allow-Headers
  if-none-match and Max-Age 86400.
- Applies scripted rules, one list per case (set_rules). Each rule matches the
  URL path with a regular expression and can fire a limited number of times:
    {"match": RE, "action": "status", "status": 500, "headers": {...}, "times": 1}
    {"match": RE, "action": "short_body", "delta": 100}   Content-Length is delta bytes more than the body sent; then the connection closes
    {"match": RE, "action": "truncate", "bytes": N}       a consistent response with only the first N bytes (Content-Length N)
    {"match": RE, "action": "slow", "delay_s": 5}         headers at once, the body after delay_s seconds
    {"match": RE, "action": "file", "file": "good/OTC_20991231.jsonl"}       serve another fixture file
    {"match": RE, "action": "json", "file": "good/OTC_index.json", "pointer": "/releases/1"}   serve one JSON value of a fixture (RFC 6901 pointer)
  Rules are tried in order; the first active match applies. "times" null = always.
- Records every request (method, path, query, headers, status, time) in a log.
- stop() closes the HTTP listener and every open (keep-alive) connection, and
  puts a tripwire on the same port: it accepts any connection, records it, and
  closes it at once. A request that still reaches a handler while stopped is
  also recorded as a tripwire entry and gets no response. So "the server is
  stopped" and "no socket was opened" can both be checked. resume() serves again.
- RecordingProxy is a forward HTTP proxy (absolute-URI requests and CONNECT)
  that records every request it relays. Its aliases map a host name (one that
  does not resolve) to the address it connects to instead.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import http.client
import http.server
import json
import re
import select
import socket
import socketserver
import sys
import threading
import time
import urllib.parse
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent / "fixtures"

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Vary": "Origin",
    "Access-Control-Expose-Headers": "ETag,Content-Length,Content-Encoding",
}
PREFLIGHT_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Vary": "Origin",
    "Access-Control-Allow-Methods": "GET, HEAD",
    "Access-Control-Allow-Headers": "if-none-match",
    "Access-Control-Max-Age": "86400",
}
ACTIONS = {"status", "short_body", "truncate", "slow", "file", "json"}
# action -> required fields and their types; then the optional fields of any rule
_REQUIRED = {"status": {"status": int}, "file": {"file": str}, "json": {"file": str}, "truncate": {"bytes": int}}
_OPTIONAL = {"delta": int, "delay_s": (int, float), "headers": dict, "body": str, "pointer": str, "name": str}


def validate_rule(i, r):
    """Raise ValueError when rule i is not a valid rule (see the module docstring)."""
    if not isinstance(r, dict):
        raise ValueError(f"rule {i}: not an object: {r!r}")
    if r.get("action") not in ACTIONS:
        raise ValueError(f"rule {i}: unknown rule action {r.get('action')!r}")
    if not isinstance(r.get("match"), str):
        raise ValueError(f"rule {i}: match must be a regular expression string, got {r.get('match')!r}")
    try:
        re.compile(r["match"])
    except re.error as e:
        raise ValueError(f"rule {i}: match {r['match']!r} is not a regular expression: {e}") from None
    for k, t in _REQUIRED.get(r["action"], {}).items():
        if k not in r:
            raise ValueError(f"rule {i}: action {r['action']!r} needs {k!r}")
    for k, t in {**_OPTIONAL, **_REQUIRED.get(r["action"], {})}.items():
        if k in r and (isinstance(r[k], bool) or not isinstance(r[k], t)):
            raise ValueError(f"rule {i}: {k} has the wrong type: {r[k]!r}")
    times = r.get("times")
    if times is not None and (isinstance(times, bool) or not isinstance(times, int)):
        raise ValueError(f"rule {i}: times must be an integer or null, got {times!r}")


def json_pointer(doc, pointer):
    if pointer in ("", "/"):
        return doc
    for part in pointer.lstrip("/").split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        doc = doc[int(part)] if isinstance(doc, list) else doc[part]
    return doc


def etag_of(data: bytes) -> str:
    return '"' + hashlib.sha256(data).hexdigest() + '"'


class RequestLog:
    def __init__(self):
        self._lock = threading.Lock()
        self._entries = []

    def add(self, **entry):
        entry.setdefault("t", time.monotonic())
        with self._lock:
            self._entries.append(entry)

    def entries(self):
        with self._lock:
            return list(self._entries)

    def clear(self):
        with self._lock:
            self._entries.clear()


class _ThreadingServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 64


class _FixtureHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "otc-fixture-server/0.1"

    def log_message(self, fmt, *args):  # quiet
        pass

    @property
    def fx(self) -> "FixtureServer":
        return self.server.fixture  # type: ignore[attr-defined]

    def setup(self):
        super().setup()
        self.fx._track(self.connection, True)

    def finish(self):
        try:
            super().finish()
        finally:
            self.fx._track(self.connection, False)

    def _stopped(self):
        """While stopped, a request on a still-open connection is a tripwire hit: record it, answer nothing."""
        if self.fx.running:
            return False
        self.fx.log.add(source="tripwire", method=None, path=None, query="", headers={}, status=None, rule=None, error=None)
        self.close_connection = True
        return True

    def _record(self, status, rule=None, error=None):
        parsed = urllib.parse.urlsplit(self.path)
        self.fx.log.add(source="server", method=self.command, path=urllib.parse.unquote(parsed.path),
                        query=parsed.query, headers={k.lower(): v for k, v in self.headers.items()},
                        status=status, rule=rule, error=error)

    def _send(self, status, body=b"", headers=None, head=False):
        self.send_response(status)
        for k, v in CORS_HEADERS.items():
            self.send_header(k, v)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        if "content-length" not in {k.lower() for k in (headers or {})}:
            self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if not head and body:
            self.wfile.write(body)

    def do_OPTIONS(self):
        if self._stopped():
            return
        self._record(204)
        self.send_response(204)
        for k, v in PREFLIGHT_HEADERS.items():
            self.send_header(k, v)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_HEAD(self):
        self.do_GET(head=True)

    def do_GET(self, head=False):
        if self._stopped():
            return
        path = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
        rule = self.fx.take_rule(path)
        try:
            self._serve(path, rule, head)
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:  # a rule that cannot be applied: log it and answer 500, do not drop the connection
            msg = f"{type(e).__name__}: {e}"
            print(f"fixture server: cannot serve {path} with rule {rule!r}: {msg}", file=sys.stderr, flush=True)
            self._record(500, rule.get("name") if rule else None, error=msg)
            try:
                self.close_connection = True
                self._send(500, f"fixture server error: {msg}\n".encode(), {"Content-Type": "text/plain"}, head)
            except OSError:
                pass

    def _load(self, rel):
        target = (FIXTURES / rel.lstrip("/")).resolve()
        if FIXTURES.resolve() not in target.parents or not target.is_file():
            return None
        return target.read_bytes()

    def _serve(self, path, rule, head):
        action = rule["action"] if rule else None
        if action == "status":
            status = int(rule["status"])
            body = rule.get("body", "").encode()
            self._record(status, rule.get("name"))
            hdrs = dict(rule.get("headers") or {})
            hdrs.setdefault("Content-Type", "text/plain")
            self._send(status, body, hdrs, head)
            return
        served = path  # the name that decides the Content-Type
        if action == "file":
            data = self._load(rule["file"])
            served = rule["file"]
        elif action == "json":
            raw = self._load(rule["file"])
            data = None if raw is None else (
                json.dumps(json_pointer(json.loads(raw), rule.get("pointer", "")), indent=1, sort_keys=True) + "\n").encode()
            served = "x.json"
        else:
            data = self._load(path)
        if data is None:
            self._record(404, rule.get("name") if rule else None)
            self._send(404, b"not found\n", {"Content-Type": "text/plain"}, head)
            return
        tag = etag_of(data)
        inm = self.headers.get("If-None-Match")
        if inm and tag in [t.strip() for t in inm.split(",")] and action not in ("short_body", "truncate", "slow"):
            self._record(304, rule.get("name") if rule else None)
            self.send_response(304)
            for k, v in CORS_HEADERS.items():
                self.send_header(k, v)
            self.send_header("ETag", tag)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        ctype = "application/json" if served.endswith((".json", ".jsonl")) else (
            "application/gzip" if served.endswith(".gz") else "text/plain")
        headers = {"ETag": tag, "Content-Type": ctype}
        body = data
        accept = self.headers.get("Accept-Encoding", "")
        if "gzip" in accept.lower() and not path.endswith(".gz") and action not in ("short_body", "truncate"):
            body = gzip.compress(data, mtime=0)
            headers["Content-Encoding"] = "gzip"
        if action == "short_body":
            delta = int(rule.get("delta", 100))
            self._record(200, rule.get("name"))
            headers["Content-Length"] = str(len(body) + delta)
            headers["Connection"] = "close"
            self.close_connection = True
            self._send(200, body, headers, head)
            return
        if action == "truncate":
            body = body[: int(rule["bytes"])]
        self._record(200, rule.get("name") if rule else None)
        if action == "slow":
            self.send_response(200)
            for k, v in {**CORS_HEADERS, **headers, "Content-Length": str(len(body))}.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.flush()
            time.sleep(float(rule.get("delay_s", 5)))
            if not head:
                self.wfile.write(body)
            return
        self._send(200, body, headers, head)


class FixtureServer:
    """The fixture HTTP server. Use start(), url, set_rules(), log, stop(), resume(), shutdown()."""

    def __init__(self, host="127.0.0.1", port=0):
        self.host = host
        self.port = port
        self.log = RequestLog()
        self._rules = []
        self._rules_lock = threading.Lock()
        self._httpd = None
        self._thread = None
        self._trip_sock = None
        self._trip_thread = None
        self._trip_stop = threading.Event()
        self._conns = set()
        self._conns_lock = threading.Lock()
        self.trip_errors = []
        self.running = False

    @property
    def url(self):
        return f"http://{self.host}:{self.port}"

    # rules
    def set_rules(self, rules):
        for i, r in enumerate(rules or []):
            validate_rule(i, r)
        rules = [dict(r) for r in (rules or [])]
        for r in rules:
            r.setdefault("times", None)
        with self._rules_lock:
            self._rules = rules

    def take_rule(self, path):
        with self._rules_lock:
            for r in self._rules:
                if r["times"] is not None and r["times"] <= 0:
                    continue
                if re.search(r["match"], path):
                    if r["times"] is not None:
                        r["times"] -= 1
                    return dict(r)
        return None

    # lifecycle
    def start(self):
        self._httpd = _ThreadingServer((self.host, self.port), _FixtureHandler)
        self._httpd.fixture = self  # type: ignore[attr-defined]
        self.port = self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        self._thread.start()
        self.running = True
        return self

    def _track(self, conn, add):
        with self._conns_lock:
            (self._conns.add if add else self._conns.discard)(conn)

    def _close_conns(self):
        with self._conns_lock:
            conns = list(self._conns)
        for c in conns:
            try:
                c.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def _close_listener(self):
        self.running = False  # first, so a handler that still gets a request treats it as a tripwire hit
        self._httpd.shutdown()
        self._httpd.server_close()
        self._close_conns()

    def stop(self):
        """Stop serving; a tripwire on the same port records and drops every connection.

        If the tripwire cannot bind, OSError is raised and the server is left stopped with no
        tripwire; resume() then serves again."""
        if not self.running:
            return
        self._close_listener()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.host, self.port))
            sock.listen(64)
        except OSError as e:
            sock.close()
            raise OSError(e.errno, f"fixture server: cannot put the tripwire on port {self.port}: {e.strerror or e}") from e
        sock.settimeout(0.05)
        stop = threading.Event()
        self._trip_sock, self._trip_stop = sock, stop

        def trip():
            backoff, last = 0.05, None
            while not stop.is_set():
                try:
                    conn, _ = sock.accept()
                except socket.timeout:
                    continue
                except OSError as e:
                    if stop.is_set():
                        break
                    self.trip_errors.append(repr(e))
                    if repr(e) != last:  # log each new error once, then back off quietly
                        print(f"fixture server: tripwire accept() on port {self.port} failed: {e}; retrying",
                              file=sys.stderr, flush=True)
                        last = repr(e)
                    stop.wait(backoff)
                    backoff = min(backoff * 2, 1.0)
                    continue
                backoff, last = 0.05, None
                self.log.add(source="tripwire", method=None, path=None, query="", headers={}, status=None, rule=None,
                             error=None)
                try:
                    conn.close()
                except OSError:
                    pass

        self._trip_thread = threading.Thread(target=trip, daemon=True)
        self._trip_thread.start()

    def _stop_tripwire(self):
        self._trip_stop.set()
        if self._trip_thread is not None:
            self._trip_thread.join()
            self._trip_thread = None
        if self._trip_sock is not None:
            self._trip_sock.close()
            self._trip_sock = None

    def resume(self):
        """Serve again on the same port. If the bind fails, OSError is raised and the server stays stopped."""
        if self.running:
            return
        self._stop_tripwire()
        self.start()

    def shutdown(self):
        if self.running:
            self._close_listener()
        self._stop_tripwire()


class _ProxyHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _record(self, status, target, error=None):
        self.server.proxy.log.add(source="proxy", method=self.command, path=target, query="",  # type: ignore[attr-defined]
                                  headers={k.lower(): v for k, v in self.headers.items()}, status=status, rule=None,
                                  error=error)

    def do_CONNECT(self):
        self.close_connection = True  # after a tunnel the connection carries no more HTTP
        host, sep, port = self.path.rpartition(":")
        host = host.strip("[]")
        if not sep or not host or not port.isdigit():
            self._record(400, self.path, error="CONNECT target is not host:port")
            self.send_error(400, "CONNECT target must be host:port")
            return
        host = self.server.proxy.aliases.get(host, host)  # type: ignore[attr-defined]
        try:
            upstream = socket.create_connection((host, int(port)), timeout=10)
        except OSError as e:
            self._record(502, self.path, error=f"{type(e).__name__}: {e}")
            self.send_error(502)
            return
        self._record(200, self.path)
        self.send_response(200, "Connection established")
        self.end_headers()
        conns = [self.connection, upstream]
        try:
            while True:
                r, _, x = select.select(conns, [], conns, 30)
                if x or not r:
                    break
                for s in r:
                    data = s.recv(65536)
                    if not data:
                        return
                    (upstream if s is self.connection else self.connection).sendall(data)
        except OSError:
            pass  # one side went away: the tunnel is over
        finally:
            upstream.close()

    def _relay(self):
        target = self.path
        parts = urllib.parse.urlsplit(target)
        if parts.scheme != "http" or not parts.hostname:
            self._record(400, target)
            self.send_error(400, "absolute http URI required")
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            self._record(400, target, error="bad Content-Length")
            self.send_error(400, "bad Content-Length")
            return
        body = self.rfile.read(length) if length else None
        headers = {k: v for k, v in self.headers.items() if k.lower() not in ("proxy-connection", "connection", "keep-alive")}
        try:
            host = self.server.proxy.aliases.get(parts.hostname, parts.hostname)  # type: ignore[attr-defined]
            conn = http.client.HTTPConnection(host, parts.port or 80, timeout=120)
            conn.request(self.command, urllib.parse.urlunsplit(("", "", parts.path or "/", parts.query, "")), body, headers)
            resp = conn.getresponse()
            data = resp.read()
        except (OSError, http.client.HTTPException) as e:
            self._record(502, target, error=f"{type(e).__name__}: {e}")
            try:
                self.send_error(502)
            except OSError:
                pass
            return
        self._record(resp.status, target)
        self.send_response(resp.status)
        for k, v in resp.getheaders():
            if k.lower() in ("transfer-encoding", "connection", "content-length"):
                continue
            self.send_header(k, v)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    do_GET = _relay
    do_HEAD = _relay
    do_OPTIONS = _relay


class RecordingProxy:
    def __init__(self, host="127.0.0.1", port=0):
        self.host = host
        self.port = port
        self.log = RequestLog()
        self.aliases = {}  # host name -> the address the proxy connects to instead
        self._httpd = None

    @property
    def url(self):
        return f"http://{self.host}:{self.port}"

    def start(self):
        self._httpd = _ThreadingServer((self.host, self.port), _ProxyHandler)
        self._httpd.proxy = self  # type: ignore[attr-defined]
        self.port = self._httpd.server_address[1]
        threading.Thread(target=self._httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
        return self

    def shutdown(self):
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--proxy-port", type=int, default=8766)
    ap.add_argument("--rules", help="a JSON file with a rule list")
    a = ap.parse_args()
    srv = FixtureServer(a.host, a.port).start()
    if a.rules:
        srv.set_rules(json.loads(Path(a.rules).read_text()))
    proxy = RecordingProxy(a.host, a.proxy_port).start()
    print(f"fixture server {srv.url}/  (roots: {', '.join(sorted(p.name for p in FIXTURES.iterdir() if p.is_dir()))})")
    print(f"recording proxy {proxy.url}")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        srv.shutdown()
        proxy.shutdown()


if __name__ == "__main__":
    main()
