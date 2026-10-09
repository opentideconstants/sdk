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
