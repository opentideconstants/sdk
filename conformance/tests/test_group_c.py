"""Group C: the fixture server, tripwire and proxy."""
from __future__ import annotations

import http.client
import socket
import sys
import time

import pytest

from _util import CONF

sys.path.insert(0, str(CONF))
import server  # noqa: E402
from server import FixtureServer, RecordingProxy  # noqa: E402

PATH = "/good/OTC_latest.json"


@pytest.fixture
def srv():
    s = FixtureServer().start()
    yield s
    s.shutdown()


def _get(conn, path=PATH):
    conn.request("GET", path)
    r = conn.getresponse()
    return r.status, r.read()


def test_stop_closes_keep_alive_connections(srv):
    conn = http.client.HTTPConnection(srv.host, srv.port, timeout=5)
    assert _get(conn)[0] == 200
    srv.log.clear()
    srv.stop()
    time.sleep(0.2)
    with pytest.raises((OSError, http.client.HTTPException)):
        _get(conn)
    assert not [e for e in srv.log.entries() if e["source"] == "server"], srv.log.entries()


def test_tripwire_sees_a_reused_client_after_stop(srv):
    conn = http.client.HTTPConnection(srv.host, srv.port, timeout=5)
    assert _get(conn)[0] == 200
    srv.log.clear()
    srv.stop()
    time.sleep(0.2)
    for _ in range(2):  # a pooled client: the stale socket fails, the retry opens a new one
        try:
            _get(conn)
        except (OSError, http.client.HTTPException):
            conn.close()
    time.sleep(0.2)
    srcs = [e["source"] for e in srv.log.entries()]
    assert "tripwire" in srcs and "server" not in srcs, srcs


def test_request_on_an_open_connection_while_stopped_is_a_tripwire_entry(srv):
    # the handler-level guard: a request that reaches a handler while stopped is not served
    srv.running = False
    try:
        conn = http.client.HTTPConnection(srv.host, srv.port, timeout=5)
        with pytest.raises((OSError, http.client.HTTPException)):
            _get(conn)
    finally:
        srv.running = True
    srcs = [e["source"] for e in srv.log.entries()]
    assert srcs == ["tripwire"], srcs


@pytest.mark.parametrize("rule", [
    {"action": "status", "status": 500},                  # no match
    {"match": "(", "action": "status", "status": 500},    # bad regex
    {"match": "x", "action": "status"},                   # no status
    {"match": "x", "action": "status", "status": "abc"},  # status not an int
    {"match": "x", "action": "file"},                     # no file
    {"match": "x", "action": "json"},                     # no file
    {"match": "x", "action": "truncate"},                 # no bytes
    {"match": "x", "action": "slow", "delay_s": "soon"},
    {"match": "x", "action": "status", "status": 500, "times": "once"},
    "not a rule",
])
def test_bad_rule_fields_raise_valueerror(srv, rule):
    with pytest.raises(ValueError):
        srv.set_rules([rule])


def test_json_rule_with_missing_file_is_404(srv):
    srv.set_rules([{"match": "latest", "action": "json", "file": "good/no-such.json", "pointer": "/x"}])
    conn = http.client.HTTPConnection(srv.host, srv.port, timeout=5)
    assert _get(conn)[0] == 404
    assert [e["status"] for e in srv.log.entries()] == [404]


def test_request_time_rule_error_is_logged_500(srv, capsys):
    srv.set_rules([{"match": "latest", "action": "json", "file": "good/OTC_index.json", "pointer": "/no/such/key"}])
    conn = http.client.HTTPConnection(srv.host, srv.port, timeout=5)
    assert _get(conn)[0] == 500
    e = srv.log.entries()[-1]
    assert e["status"] == 500 and e.get("error"), e
    assert "fixture server" in capsys.readouterr().err


class _BindFails(socket.socket):
    def bind(self, addr):
        raise OSError(98, "Address already in use (test)")


def test_stop_bind_failure_leaves_consistent_state(srv, monkeypatch):
    monkeypatch.setattr(server.socket, "socket", _BindFails)
    with pytest.raises(OSError):
        srv.stop()
    monkeypatch.undo()
    assert not srv.running
    srv.resume()
    assert srv.running
    assert _get(http.client.HTTPConnection(srv.host, srv.port, timeout=5))[0] == 200


def test_resume_bind_failure_leaves_consistent_state(srv, monkeypatch):
    srv.stop()

    def boom(*a, **k):
        raise OSError(98, "Address already in use (test)")
    monkeypatch.setattr(server, "_ThreadingServer", boom)
    with pytest.raises(OSError):
        srv.resume()
    assert not srv.running
    with pytest.raises(OSError):
        srv.resume()  # a second try fails the same way, not with AttributeError
    monkeypatch.undo()
    srv.resume()
    assert srv.running
    srv.shutdown()
    srv.shutdown()


def test_tripwire_does_not_busy_loop_and_logs(srv, capsys):
    srv.stop()
    srv._trip_sock.close()  # accept() now fails at once with EBADF, every time
    c0 = time.process_time()
    time.sleep(1.0)
    used = time.process_time() - c0
    assert used < 0.3, f"tripwire used {used:.2f} s CPU in 1 s"
    assert "tripwire" in capsys.readouterr().err


def test_proxy_records_upstream_failure_reason():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()  # nothing listens here
    proxy = RecordingProxy().start()
    try:
        conn = http.client.HTTPConnection(proxy.host, proxy.port, timeout=10)
        conn.request("GET", f"http://127.0.0.1:{port}/x")
        r = conn.getresponse()
        r.read()
        assert r.status == 502
        e = proxy.log.entries()[-1]
        assert e["status"] == 502 and "Refused" in (e.get("error") or ""), e
    finally:
        proxy.shutdown()


def test_connect_without_port_is_400():
    proxy = RecordingProxy().start()
    try:
        conn = http.client.HTTPConnection(proxy.host, proxy.port, timeout=10)
        conn.request("CONNECT", "example.org")
        r = conn.getresponse()
        assert r.status == 400
    finally:
        proxy.shutdown()
