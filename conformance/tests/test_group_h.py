"""Group H: the language runners fail closed (review round 1, package PK19). Each runner is driven over its
protocol with a fake SDK (tests/fake_sdk) that returns what a real SDK might get wrong."""
from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import sys
import threading

import pytest

from _util import CONF

sys.path.insert(0, str(CONF))

FAKE = CONF / "tests" / "fake_sdk"
RUNNERS = CONF / "runners"


def runner_cmd(lang):
    if lang == "python":
        return [sys.executable, str(RUNNERS / "python" / "runner.py"), "--installed"], {"PYTHONPATH": str(FAKE / "python")}
    if lang == "ruby":
        if not shutil.which("ruby"):
            pytest.skip("no ruby")
        return ["ruby", "-I", str(FAKE / "ruby"), str(RUNNERS / "ruby" / "runner.rb")], {"OTC_RUBY_USE_INSTALLED": "1"}
    if lang == "node":
        if not shutil.which("node"):
            pytest.skip("no node")
        return ["node", str(RUNNERS / "node" / "runner.mjs"), "--sdk", str(FAKE / "node" / "index.js")], {}
    if lang in ("c", "c-fetch"):
        exe = CONF.parent / "c" / ("build" if lang == "c" else "build-fetch") / "otc_runner"
        if not exe.exists():
            pytest.skip(f"no {exe} (build the C runner first)")
        return [str(exe)], {}
    raise ValueError(lang)


def talk(lang, lines, mode="", timeout=30):
    """Start a runner, send the lines (dicts are JSON-encoded, strings go as they are), and return
    (exit status, the parsed hello, the reply lines as text, stderr)."""
    cmd, env = runner_cmd(lang)
    e = dict(os.environ, FAKE_SDK_MODE=mode, **env)
    data = "".join((json.dumps(x) if isinstance(x, dict) else x) + "\n" for x in lines)
    p = subprocess.run(cmd, input=data, capture_output=True, text=True, env=e, timeout=timeout, cwd=str(CONF.parent))
    out = p.stdout.splitlines()
    try:
        hello = json.loads(out[0]) if out else None
    except ValueError:
        raise AssertionError(f"the runner's first line is not JSON: {out[0][:200]!r} (exit {p.returncode}; "
                             f"stderr {p.stderr[-300:]!r})") from None
    return p.returncode, hello, out[1:], p.stderr


def opened(lang, lines, mode="", n=None):
    """talk(), then check that the runner answered every line and that the first one (an open) succeeded, so a later
    error reply is about the condition under test, not "no client is open" (R2-154). Returns the parsed replies."""
    rc, hello, out, err = talk(lang, lines, mode=mode)
    ctx = (rc, out, err[-500:])
    assert hello and len(out) == (n or len(lines)), ctx
    replies = [strict(x) for x in out]
    assert replies[0]["ok"] is True, ctx
    return replies


def uncaught(reply):
    """An error reply for a non-SDK failure, and not the one a runner gives when no client is open."""
    return (reply["ok"] is False and reply["error"]["code"].startswith("uncaught:")
            and "no client" not in str(reply["error"].get("message")).lower())


def strict(line):
    """Parse a reply as strict JSON (no NaN or Infinity)."""
    def bad(c):
        raise ValueError(f"not JSON: {c}")
    return json.loads(line, parse_constant=bad)


OPEN = {"op": "open", "args": {"file": "x"}}
LANGS = ["python", "ruby", "node"]


# --- a request line that is not JSON gets an error reply, and the runner goes on

@pytest.mark.parametrize("lang", LANGS)
def test_bad_request_line_gets_an_error_reply(lang):
    rc, hello, out, err = talk(lang, ["{not json", OPEN, {"op": "station_count"}])
    assert hello and len(out) == 3, (rc, out, err[-500:])
    first = strict(out[0])
    assert first["ok"] is False and first["error"]["code"].startswith("uncaught:"), first
    assert strict(out[2]) == {"ok": True, "result": {"station_count": 20}}, out


# --- a non-finite number from the SDK is an error reply, never Infinity (not JSON) or a silent null; NaN is null

@pytest.mark.parametrize("lang", LANGS)
def test_infinity_is_an_error_reply(lang):
    replies = opened(lang, [OPEN, {"op": "station_count"}, {"op": "station_count"}], mode="inf")
    assert uncaught(replies[1]) and uncaught(replies[2]), replies   # each step is an error reply; the runner goes on


@pytest.mark.parametrize("lang", LANGS)
def test_nan_is_null(lang):
    rc, hello, out, err = talk(lang, [OPEN, {"op": "station_count"}], mode="nan")
    assert len(out) == 2 and strict(out[1]) == {"ok": True, "result": {"station_count": None}}, (rc, out, err[-500:])


def test_driver_rejects_non_json_numbers_from_a_runner(tmp_path):
    from _util import run_driver, write_cases, write_fake_runner
    cases = write_cases(tmp_path, [{"id": "a", "steps": [{"op": "station_count", "expect": {"count": 1}}]}])
    r = run_driver("--runner", write_fake_runner(tmp_path), "--cases", str(cases),
                   env={"FAKE_REPLY": '{"ok": true, "result": {"count": Infinity}}'})
    assert "FAIL  a" in r.stdout and "not JSON" in r.stdout, r.stdout[-500:]


# --- a value the runner cannot encode, or an error while it encodes an SDK error, is an error reply

@pytest.mark.parametrize("lang,mode", [("python", "object"), ("ruby", "object"), ("node", "bigint")])
def test_unencodable_value_is_an_error_reply(lang, mode):
    rc, hello, out, err = talk(lang, [OPEN, {"op": "station_count"}, {"op": "loaded_from"}], mode=mode)
    assert len(out) == 3, (rc, out, err[-500:])
    reply = strict(out[1])
    assert reply["ok"] is False and reply["error"]["code"].startswith("uncaught:"), reply
    assert strict(out[2])["ok"] is True


def test_ruby_error_encoding_failure_is_an_error_reply():
    replies = opened("ruby", [OPEN, {"op": "require_station", "args": {"station_id": "OTC-T-0005"}}, {"op": "loaded_from"}],
                     mode="error-field-raises")
    assert uncaught(replies[1]) and replies[2]["ok"] is True, replies


# --- an op with no open client is an error reply (no crash, no empty success)

NO_CLIENT_OPS = [{"op": "station_count"}, {"op": "hold_release", "args": {"name": "x"}}, {"op": "loaded_from"},
                 {"op": "last_error"}, {"op": "verify"}, {"op": "cached_releases"}, {"op": "update"},
                 {"op": "station", "args": {"station_id": "OTC-T-0001"}}, {"op": "release_files"}]


@pytest.mark.parametrize("lang", LANGS + ["c", "c-fetch"])
def test_ops_with_no_client_are_error_replies(lang):
    rc, hello, out, err = talk(lang, NO_CLIENT_OPS)
    assert len(out) == len(NO_CLIENT_OPS), (rc, out, err[-500:])
    for req, line in zip(NO_CLIENT_OPS, out):
        reply = strict(line)
        assert reply["ok"] is False and reply["error"]["code"].startswith("uncaught:"), (req, reply)


# --- C61: the C runner's verify never answers verified: true when it hashed nothing

def _copy_release(tmp_path):
    d = "20991231.2"
    for ext in (".jsonl", ".meta.json", ".sha256"):
        shutil.copy(CONF / "fixtures" / "good" / f"OTC_{d}{ext}", tmp_path / f"OTC_{d}{ext}")
    return tmp_path / f"OTC_{d}.jsonl"


class CRunner:
    """A C runner process driven one request at a time. Every read has a deadline (a runner that hangs fails the test,
    it does not block pytest), and close() kills a runner that does not exit (R2-156)."""

    def __init__(self, lang, env=None, timeout=30):
        cmd, e = runner_cmd(lang)
        self.timeout = timeout
        self.p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                                  env=dict(os.environ, **e, **(env or {})), cwd=str(CONF.parent))
        self.lines = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()
        try:
            self._read("the hello")
        except BaseException:
            self.close()
            raise

    def _pump(self):
        for line in self.p.stdout:
            self.lines.put(line)
        self.lines.put("")

    def _read(self, what):
        try:
            line = self.lines.get(timeout=self.timeout)
        except queue.Empty:
            raise AssertionError(f"the runner gave no reply to {what} within {self.timeout} s") from None
        assert line, f"the runner died on {what}"
        return line

    def __call__(self, op, **args):
        self.p.stdin.write(json.dumps({"op": op, "args": args}) + "\n")
        self.p.stdin.flush()
        return strict(self._read(f"{op} {args}"))

    def close(self):
        try:
            self.p.stdin.close()
        except OSError:
            pass
        try:
            return self.p.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.p.kill()
            self.p.wait()
            return None


def c_runner_opened(lang, path, env=None, **open_args):
    """A C runner with the release at path open; the runner is closed if the open fails."""
    r = CRunner(lang, env)
    try:
        opened_ = r("open", file=str(path), **open_args)
        assert opened_["ok"], opened_
    except BaseException:
        r.close()
        raise
    return r


@pytest.mark.parametrize("lang", ["c", "c-fetch"])
def test_c_verify_with_no_file_left_is_not_verified(tmp_path, lang):
    path = _copy_release(tmp_path)
    r = c_runner_opened(lang, path, mode="stream")
    try:
        assert r("verify") == {"ok": True, "result": {"verified": True}}  # the files are there
        for f in tmp_path.iterdir():
            f.unlink()
        reply = r("verify")
    finally:
        r.close()
    assert reply.get("ok") is False, reply


@pytest.fixture
def c_good(tmp_path):
    r = c_runner_opened("c", _copy_release(tmp_path), mode="stream")
    try:
        yield r
    finally:
        r.close()


# --- C110: an explicit limit 0 is not the same as no limit (D36: limit 0 is invalid_argument)

def test_c_limit_zero_is_not_no_limit(c_good):
    every = c_good("search", name="harbour")
    assert every["ok"] and len(every["result"]["station_ids"]) > 1, every
    zero = c_good("search", name="harbour", limit=0)
    assert zero != every and zero["ok"] is False, zero
    zero = c_good("near", lat=50.75, lon=-1.2, radius_km=500, limit=0)
    assert zero["ok"] is False, zero


# --- C65: an unknown mode or on_network_error string is invalid_argument, not a silent default

@pytest.mark.parametrize("args", [{"mode": "streem"}, {"on_network_error": "rase"}])
def test_c_unknown_enum_option_is_invalid_argument(tmp_path, args):
    path = _copy_release(tmp_path)
    r = CRunner("c")
    try:
        reply = r("open", file=str(path), **args)
    finally:
        r.close()
    assert reply["ok"] is False and reply["error"]["code"] == "invalid_argument", reply


# --- C111: a wrong-typed argument is invalid_argument wherever it is read; raw rejects an unknown object

@pytest.mark.parametrize("op,args", [("constant_set", {"station_id": "OTC-T-0001", "set_id": 5}),
                                     ("tombstone", {"station_id": 5}),
                                     ("constituent", {"station_id": "OTC-T-0001", "set_id": "OTC-T-0001/noaa", "name": 5}),
                                     ("constant_sets", {"station_id": "OTC-T-0001", "include_no_constants": "yes"})])
def test_c_wrong_typed_argument_is_invalid_argument(c_good, op, args):
    reply = c_good(op, **args)
    assert reply["ok"] is False and reply["error"]["code"] == "invalid_argument", reply


def test_c_raw_unknown_object_is_a_runner_failure(c_good):
    reply = c_good("raw", object="no-such-object", station_id="OTC-T-0001")
    assert reply["ok"] is False and reply["error"]["code"].startswith("uncaught:"), reply


# --- C runner failures that only a planted fault provokes (OTC_RUNNER_FAULT)

def c_good_with(tmp_path, fault, threads=None):
    env = {"OTC_RUNNER_FAULT": fault}
    if threads:
        env["OTC_RUNNER_THREADS"] = str(threads)
    return c_runner_opened("c", _copy_release(tmp_path), env, mode="stream")


def test_c_failed_list_call_is_an_error_not_a_crash(tmp_path):  # C112
    r = c_good_with(tmp_path, "list-nomem")
    try:
        reply = r("subordinates_of", station_id="OTC-T-0001")
    finally:
        r.close()
    assert reply["ok"] is False, reply


@pytest.mark.parametrize("op,args,fault", [
    ("conventions", {}, "json"),
    ("provenance", {"station_id": "OTC-T-0001", "set_id": "OTC-T-0001/noaa"}, "json"),
    ("convention", {"convention_id": "otc-greenwich-v1"}, "lookup"),
    ("reference_station", {"station_id": "OTC-T-0003"}, "lookup"),
    ("recommended_set", {"station_id": "OTC-T-0001"}, "lookup"),
    ("subordinate_offsets", {"station_id": "OTC-T-0003"}, "lookup"),
    ("constant_set", {"station_id": "OTC-T-0001", "set_id": "OTC-T-0001/noaa"}, "lookup"),
])
def test_c_library_failure_is_not_a_null_value(tmp_path, op, args, fault):  # C63
    r = c_good_with(tmp_path, fault)
    try:
        reply = r(op, **args)
    finally:
        r.close()
    assert reply["ok"] is False and reply["error"]["code"].startswith("uncaught:"), reply


def test_c_null_reply_from_a_thread_is_a_mismatch(tmp_path):  # C68
    r = c_good_with(tmp_path, "thread0-null", threads=2)
    try:
        reply = r("station_count")
    finally:
        r.close()
    # only ThreadMismatch: NoMemory is what main prints when a regression returns thread 0's NULL reply (R2-155)
    assert reply["ok"] is False and reply["error"]["code"] == "uncaught:ThreadMismatch", reply


@pytest.fixture
def fixture_server():
    from server import FixtureServer
    srv = FixtureServer().start()
    yield srv
    srv.shutdown()


def c_fetch_on_old_release(tmp_path, srv, fault):
    """A c-fetch runner opened (latest) on 20991231 while the server has 20991231.2."""
    srv.set_rules([{"match": r"/good/OTC_latest(-f1)?\.json$", "action": "json", "file": "good/OTC_index.json", "pointer": "/releases/1"}])
    r = CRunner("c-fetch", {"OTC_RUNNER_FAULT": fault})
    try:
        got = r("open", base_url=f"{srv.url}/good/", cache_dir=str(tmp_path / "cache"))
        assert got["ok"] and got["result"]["datestamp"] == "20991231", got
    except BaseException:
        r.close()
        raise
    srv.set_rules([])
    return r


def test_c_update_keeps_the_error_detail_of_the_swap(tmp_path, fixture_server):  # C62
    r = c_fetch_on_old_release(tmp_path, fixture_server, "swap")
    try:
        reply = r("update")
    finally:
        r.close()
    assert reply["ok"] is False, reply
    assert reply["error"]["message"] != reply["error"]["code"] and "20000101" in reply["error"]["message"], reply


def test_c_update_without_a_move_is_not_updated(tmp_path, fixture_server):  # C64
    r = c_fetch_on_old_release(tmp_path, fixture_server, "update-path")
    try:
        reply = r("update")
    finally:
        r.close()
    assert not (reply.get("ok") and reply["result"]["updated"] and reply["result"]["from"] == reply["result"]["to"]), reply
    assert reply["ok"] is False and reply["error"]["code"].startswith("uncaught:"), reply


# --- T52 (and R55, P66): a close() error when the runner shuts down is reported: stderr and a non-zero exit

@pytest.mark.parametrize("lang", LANGS)
def test_close_error_at_shutdown_is_reported(lang):
    rc, hello, out, err = talk(lang, [OPEN], mode="close-raises")
    assert len(out) == 1 and strict(out[0])["ok"] is True, (out, err[-300:])
    assert rc != 0 and "close failed" in err and "Traceback" not in err, (rc, err[-500:])


def test_driver_fails_a_case_whose_runner_exits_non_zero(tmp_path):
    from _util import run_driver, write_cases
    script = tmp_path / "r.py"
    script.write_text("import sys\nprint('{\"hello\": {\"runner\": \"x\", \"features\": []}}', flush=True)\n"
                      "for l in sys.stdin:\n    print('{\"ok\": true, \"result\": {\"count\": 1}}', flush=True)\nsys.exit(1)\n")
    cases = write_cases(tmp_path, [{"id": "a", "steps": [{"op": "station_count", "expect": {"count": 1}}]}])
    r = run_driver("--runner", f"{sys.executable} {script}", "--cases", str(cases))
    assert "FAIL  a" in r.stdout and "exited with status 1" in r.stdout and r.returncode == 1, r.stdout[-500:]


# --- T55: a field the SDK leaves out (undefined) fails the step; it never becomes null or an absent key

@pytest.mark.parametrize("field,op", [("recommendedSet", "station"), ("timezone", "station"), ("isCurrent", "station"),
                                      ("previous_release", "station_validation")])
def test_node_missing_field_is_an_error(field, op):
    replies = opened("node", [OPEN, {"op": op, "args": {"station_id": "OTC-T-0001"}}], mode=f"station-without-{field}")
    assert uncaught(replies[1]), replies


def test_node_full_station_encodes():
    reply = opened("node", [OPEN, {"op": "station", "args": {"station_id": "OTC-T-0001"}}], mode="station-without-nothing")[1]
    assert reply["ok"] is True and reply["result"]["station"]["recommended_set_id"] is None, reply


# --- T56: a list op whose station or set is not found answers null, not [] (a broken lookup must not match [])

LIST_OPS = [("subordinates_of", {"station_id": "OTC-T-9999"}, "station_ids"),
            ("station_validation", {"station_id": "OTC-T-9999"}, "validation"),
            ("constant_sets", {"station_id": "OTC-T-9999"}, "set_ids"),
            ("constituents", {"station_id": "OTC-T-0001", "set_id": "OTC-T-0001/none"}, "constituents"),
            ("set_validation", {"station_id": "OTC-T-0001", "set_id": "OTC-T-0001/none"}, "validation")]


def _real_runner(lang):
    if lang == "python":
        return [sys.executable, str(RUNNERS / "python" / "runner.py")], {}
    if lang == "ruby":
        if not shutil.which("ruby"):
            pytest.skip("no ruby")
        return ["ruby", str(RUNNERS / "ruby" / "runner.rb")], {}
    if lang == "node":
        if not (CONF.parent / "js" / "dist" / "index.js").exists():
            pytest.skip("js/dist is not built")
        return ["node", str(RUNNERS / "node" / "runner.mjs")], {}
    return runner_cmd(lang)


@pytest.mark.parametrize("lang", ["python", "ruby", "node", "c"])
def test_missing_parent_gives_null_not_empty_list(tmp_path, lang):
    if lang == "python" and sys.version_info < (3, 10):
        pytest.skip("the Python SDK needs 3.10")
    path = _copy_release(tmp_path)
    cmd, env = _real_runner(lang)
    lines = [{"op": "open", "args": {"file": str(path), "mode": "stream"}}] + [{"op": op, "args": a} for op, a, _ in LIST_OPS]
    data = "".join(json.dumps(x) + "\n" for x in lines)
    p = subprocess.run(cmd, input=data, capture_output=True, text=True, env=dict(os.environ, **env), timeout=60, cwd=str(CONF.parent))
    out = [strict(x) for x in p.stdout.splitlines()[1:]]
    assert len(out) == len(lines) and out[0]["ok"], (p.stdout[-500:], p.stderr[-500:])
    for (op, a, key), reply in zip(LIST_OPS, out[1:]):
        assert reply == {"ok": True, "result": {key: None}}, (op, reply)


# --- T57: a station_removed error whose tombstone the runner cannot encode is an uncaught: reply, not station_removed

@pytest.mark.parametrize("lang", LANGS)
def test_unencodable_tombstone_changes_the_code(lang):
    replies = opened(lang, [OPEN, {"op": "require_station", "args": {"station_id": "OTC-T-0005"}}])
    assert uncaught(replies[1]), replies


# --- R2-160: a non-SDK exception that the SDK raises during a query is an uncaught: reply naming it; the runner goes on

@pytest.mark.parametrize("lang", LANGS)
def test_non_sdk_exception_from_the_sdk_is_an_uncaught_reply(lang):
    replies = opened(lang, [OPEN, {"op": "tombstone_count"}, {"op": "loaded_from"}], mode="raise")
    assert uncaught(replies[1]) and "not an SDK error" in replies[1]["error"]["message"], replies
    assert replies[2] == {"ok": True, "result": {"loaded_from": "file"}}, replies


def test_tombstone_count_without_the_raise_mode_is_a_value():
    for lang in LANGS:
        assert opened(lang, [OPEN, {"op": "tombstone_count"}])[1] == {"ok": True, "result": {"tombstone_count": 1}}, lang


# --- R57: a stats field the SDK returns as nil is a failure, not {}

def test_ruby_nil_stats_field_is_an_error():
    replies = opened("ruby", [OPEN, {"op": "stats"}], mode="stats-nil")
    assert uncaught(replies[1]), replies


# --- R88 (and P61): a runner whose SDK has no error base class or no version fails the handshake

@pytest.mark.parametrize("lang,mode", [("python", "no-error-class"), ("python", "no-version"), ("python", "import-fails"),
                                       ("ruby", "no-error-class"), ("ruby", "no-version"),
                                       ("node", "no-error-class"), ("node", "no-version")])
def test_runner_without_sdk_error_class_or_version_fails_the_handshake(lang, mode):
    rc, hello, out, err = talk(lang, [OPEN], mode=mode)
    assert hello is None and rc != 0 and err.strip(), (rc, hello, out, err[-300:])


# --- T62: an error that escapes in the browser page (pageerror) fails the step it happened in

def test_browser_pageerror_fails_the_step():
    if not (CONF.parent / "js" / "node_modules" / "playwright").exists():
        pytest.skip("no Playwright in js/node_modules")
    lines = [{"op": "open", "args": {"base_url": "http://127.0.0.1:9/"}}, {"op": "station_count"}, {"op": "loaded_from"}]
    p = subprocess.run(["node", str(RUNNERS / "node" / "browser-runner.mjs")],
                       input="".join(json.dumps(x) + "\n" for x in lines), capture_output=True, text=True, timeout=120,
                       env=dict(os.environ, OTC_BROWSER_SDK_DIR=str(FAKE / "browser-pageerror")), cwd=str(CONF.parent))
    out = [strict(x) for x in p.stdout.splitlines()[1:]]
    assert len(out) == 3 and out[0]["ok"], (p.stdout[-500:], p.stderr[-500:])
    assert out[1]["ok"] is False and out[1]["error"]["code"] == "uncaught:PageError", out[1]
    assert out[2]["ok"] is True, out[2]
