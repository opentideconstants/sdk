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
