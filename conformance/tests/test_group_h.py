"""Group H: the language runners fail closed (review round 1, package PK19). Each runner is driven over its
protocol with a fake SDK (tests/fake_sdk) that returns what a real SDK might get wrong."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

import pytest

from _util import CONF

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
    hello = json.loads(out[0]) if out else None
    return p.returncode, hello, out[1:], p.stderr


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
    rc, hello, out, err = talk(lang, [OPEN, {"op": "station_count"}, {"op": "station_count"}], mode="inf")
    assert len(out) == 3, (rc, out, err[-500:])
    reply = strict(out[1])
    assert reply["ok"] is False and reply["error"]["code"].startswith("uncaught:"), reply


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
    rc, hello, out, err = talk("ruby", [OPEN, {"op": "require_station", "args": {"station_id": "OTC-T-0005"}}, {"op": "loaded_from"}],
                               mode="error-field-raises")
    assert len(out) == 3, (rc, out, err[-500:])
    reply = strict(out[1])
    assert reply["ok"] is False and reply["error"]["code"].startswith("uncaught:"), reply


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
