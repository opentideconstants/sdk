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
