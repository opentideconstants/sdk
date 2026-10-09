"""Group F: the driver fails closed (review round 1, package PK19): a broken harness is a harness error (exit 2),
never a pass and never a plain runner failure."""
from __future__ import annotations

import json
import sys

import pytest

from _util import CONF, NULL_RUNNER, run_driver, write_cases, write_fake_runner

sys.path.insert(0, str(CONF))
import driver  # noqa: E402
from server import FixtureServer, RecordingProxy  # noqa: E402

OK_STEP = {"op": "station_count", "expect": {"count": 1}}
OK_REPLY = '{"ok": true, "result": {"count": 1}}'


def fetch(path):
    return {"op": "latest", "args": {"fetch_url": "${server}" + path}, "expect": {"count": 1}}


# --- K12: a server rule that cannot be applied fails the case as a harness error

def test_server_rule_error_is_a_harness_error(tmp_path):
    bad_rule = {"match": "OTC_latest", "action": "json", "file": "good/OTC_index.json", "pointer": "/no/such/key"}
    cases = write_cases(tmp_path, [{"id": "a", "steps": [{"driver": "server_rules", "rules": [bad_rule]},
                                                         fetch("/good/OTC_latest.json")]},
                                   {"id": "b", "steps": [OK_STEP]}])
    r = run_driver("--runner", write_fake_runner(tmp_path), "--cases", str(cases), env={"FAKE_REPLY": OK_REPLY})
    assert "FAIL  a" in r.stdout and "PASS  b" in r.stdout, r.stdout[-800:]
    assert r.returncode == 2, (r.returncode, r.stdout[-800:])
