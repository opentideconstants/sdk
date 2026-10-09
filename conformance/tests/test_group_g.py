"""Group G: the fixture server and proxy fail closed (review round 1, package PK19)."""
from __future__ import annotations

import gzip
import http.client
import json
import sys
import time

import pytest

from _util import CONF

sys.path.insert(0, str(CONF))
import server  # noqa: E402
from server import FixtureServer, RecordingProxy  # noqa: E402

JSONL = "/good/OTC_20991231.2.jsonl"


@pytest.fixture
def pair():
    srv, proxy = FixtureServer().start(), RecordingProxy().start()
    yield srv, proxy
    srv.shutdown()
    proxy.shutdown()


def via_proxy(srv, proxy, method, path, timeout=10):
    conn = http.client.HTTPConnection(proxy.host, proxy.port, timeout=timeout)
    conn.request(method, srv.url + path)
    return conn, conn.getresponse()


# --- K2: the proxy relays HEAD lengths, short bodies and slow bodies as the server sent them, and closes upstream

def test_proxy_head_keeps_the_content_length(pair):
    srv, proxy = pair
    size = (CONF / "fixtures" / "good" / "OTC_20991231.2.jsonl").stat().st_size
    conn, r = via_proxy(srv, proxy, "HEAD", JSONL)
    r.read()
    conn.close()
    assert r.getheader("Content-Length") == str(size), r.getheaders()


def test_proxy_relays_a_short_body_as_short(pair):
    srv, proxy = pair
    srv.set_rules([{"match": "jsonl$", "action": "short_body", "delta": 100}])
    conn, r = via_proxy(srv, proxy, "GET", JSONL)
    assert r.status == 200, r.status
    with pytest.raises(http.client.IncompleteRead):
        r.read()
    conn.close()


def test_proxy_streams_a_slow_body(pair):
    srv, proxy = pair
    srv.set_rules([{"match": "jsonl$", "action": "slow", "delay_s": 2}])
    t0 = time.monotonic()
    conn, r = via_proxy(srv, proxy, "GET", JSONL)
    headers_after = time.monotonic() - t0
    r.read()
    conn.close()
    assert headers_after < 1.5, f"the proxy held the headers {headers_after:.2f} s (it buffered the body)"


def test_proxy_closes_the_upstream_connection(pair):
    srv, proxy = pair
    for _ in range(3):
        conn, r = via_proxy(srv, proxy, "GET", "/good/OTC_latest.json")
        r.read()
        conn.close()
    for _ in range(50):
        with srv._conns_lock:
            n = len(srv._conns)
        if n == 0:
            break
        time.sleep(0.05)
    assert n == 0, f"{n} upstream connection(s) left open by the proxy"


# --- K3: the gzip decision follows the file served, not the request path

def _get(srv, path, headers=None):
    conn = http.client.HTTPConnection(srv.host, srv.port, timeout=10)
    conn.request("GET", path, headers=headers or {})
    r = conn.getresponse()
    body = r.read()
    conn.close()
    return r, body


def test_gz_file_served_under_another_name_is_not_gzipped_again(pair):
    srv, _ = pair
    gz = (CONF / "fixtures" / "good" / "OTC_20991231.2.json.gz").read_bytes()
    srv.set_rules([{"match": r"x\.json$", "action": "file", "file": "good/OTC_20991231.2.json.gz"}])
    r, body = _get(srv, "/good/x.json", {"Accept-Encoding": "gzip"})
    assert r.getheader("Content-Encoding") is None and body == gz, r.getheaders()


def test_plain_file_served_under_a_gz_name_is_gzipped(pair):
    srv, _ = pair
    data = (CONF / "fixtures" / "good" / "OTC_20991231.2.json").read_bytes()
    srv.set_rules([{"match": r"x\.json\.gz$", "action": "file", "file": "good/OTC_20991231.2.json"}])
    r, body = _get(srv, "/good/x.json.gz", {"Accept-Encoding": "gzip"})
    assert r.getheader("Content-Encoding") == "gzip" and gzip.decompress(body) == data, r.getheaders()


# --- K8: json_pointer and json_set follow RFC 6901

def test_json_pointer_rfc6901():
    doc = {"": {"a": 1}, "a": {"": 2, "b": [10, 20]}, "c/d": 3, "e~f": 4}
    assert server.json_pointer(doc, "") is doc
    assert server.json_pointer(doc, "/") == {"a": 1}
    assert server.json_pointer(doc, "//a") == 1
    assert server.json_pointer(doc, "/a/") == 2
    assert server.json_pointer(doc, "/a/b/1") == 20
    assert server.json_pointer(doc, "/c~1d") == 3 and server.json_pointer(doc, "/e~0f") == 4
    for bad in ["a", "a/b", "/a/b/01", "/a/b/-", "/a/b/x"]:
        with pytest.raises((ValueError, KeyError, IndexError)):
            server.json_pointer(doc, bad)


def test_json_set_rejects_a_pointer_without_a_leading_slash(tmp_path):
    import driver
    p = tmp_path / "x.json"
    p.write_text(json.dumps({"a": {"b": 1}, "b": 0}))
    problems, _ = driver.run_action({"driver": "json_set", "path": str(p), "pointer": "a/b", "value": 9}, {}, None, None)
    assert problems and json.loads(p.read_text()) == {"a": {"b": 1}, "b": 0}, (problems, p.read_text())
    problems, _ = driver.run_action({"driver": "json_set", "path": str(p), "pointer": "/a/b", "value": 9}, {}, None, None)
    assert not problems and json.loads(p.read_text())["a"]["b"] == 9


# --- K14: validate_rule rejects unknown keys, keys of another action and values out of range

@pytest.mark.parametrize("rule", [
    {"match": "x", "action": "status", "status": 500, "time": 1},          # typo of times
    {"match": "x", "action": "slow", "delay": 3},                          # typo of delay_s
    {"match": "x", "action": "status", "status": 500, "pointer": "/a"},    # pointer is for json rules
    {"match": "x", "action": "status", "status": 500, "times": 0},
    {"match": "x", "action": "status", "status": 500, "times": -1},
    {"match": "x", "action": "slow", "delay_s": -1},
    {"match": "x", "action": "short_body", "delta": -5},
    {"match": "x", "action": "truncate", "bytes": -1},
    {"match": "x", "action": "status", "status": 99},
])
def test_validate_rule_rejects(rule):
    with pytest.raises(ValueError):
        server.validate_rule(0, rule)


# --- K9: a proxy target with a bad port is a logged 400

def test_proxy_bad_port_is_a_logged_400():
    proxy = RecordingProxy().start()
    try:
        conn = http.client.HTTPConnection(proxy.host, proxy.port, timeout=10)
        conn.request("GET", "http://127.0.0.1:99999/x")
        r = conn.getresponse()
        r.read()
        assert r.status == 400, r.status
        assert [e["status"] for e in proxy.log.entries()] == [400], proxy.log.entries()
    finally:
        proxy.shutdown()


# --- K71: running is True before the serving thread starts (a request right after resume() is served)

def test_running_is_set_before_the_thread_starts(monkeypatch):
    srv = FixtureServer()
    seen = []
    real = server.threading.Thread

    class Probe(real):
        def start(self):
            seen.append(srv.running)
            super().start()

    monkeypatch.setattr(server.threading, "Thread", Probe)
    srv.start()
    try:
        assert seen and seen[0] is True, seen
    finally:
        monkeypatch.undo()
        srv.shutdown()


# --- K63: an error after the headers went out is a harness error; no second response, no second log entry

def test_error_after_headers_writes_no_second_response(pair, monkeypatch):
    srv, _ = pair
    srv.set_rules([{"match": "jsonl$", "action": "slow", "delay_s": 0}])

    def boom(_):
        raise RuntimeError("broken after the headers")
    monkeypatch.setattr(server.time, "sleep", boom)
    conn = http.client.HTTPConnection(srv.host, srv.port, timeout=5)
    conn.request("GET", JSONL)
    r = conn.getresponse()
    assert r.status == 200
    with pytest.raises((http.client.IncompleteRead, OSError)):
        r.read()
    conn.close()
    monkeypatch.undo()
    statuses = [e["status"] for e in srv.log.entries()]
    assert statuses == [200], statuses
    assert srv.errors, "the error after the headers was not reported to the driver"


# --- harness support for the review round 1 cases

def test_json_rule_set_patches_the_value(pair):
    srv, _ = pair
    srv.set_rules([{"match": "latest-f1", "action": "json", "file": "good/OTC_latest-f1.json", "pointer": "",
                    "set": {"/datestamp": "../../x", "/files/0/sha256": "AB"}}])
    conn = http.client.HTTPConnection(srv.host, srv.port, timeout=5)
    conn.request("GET", "/good/OTC_latest-f1.json")
    doc = json.loads(conn.getresponse().read())
    assert doc["datestamp"] == "../../x" and doc["files"][0]["sha256"] == "AB", doc
    with pytest.raises(ValueError):
        server.validate_rule(0, {"match": "x", "action": "json", "file": "f", "set": {"no-slash": 1}})


def test_file_rule_headers(pair):
    srv, _ = pair
    srv.set_rules([{"match": r"\.json\.gz$", "action": "file", "file": "good/OTC_20991231.2.json.gz",
                    "headers": {"Content-Encoding": "gzip"}}])
    conn = http.client.HTTPConnection(srv.host, srv.port, timeout=5)
    conn.request("GET", "/good/OTC_20991231.2.json.gz")
    r = conn.getresponse()
    body = r.read()
    assert r.getheader("Content-Encoding") == "gzip" and body == (CONF / "fixtures" / "good" / "OTC_20991231.2.json.gz").read_bytes()
