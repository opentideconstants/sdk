"""Group A: driver exit status and crash safety."""
from __future__ import annotations

import json
import sys

import pytest

from _util import CONF, NULL_RUNNER, run_driver, write_cases, write_fake_runner

sys.path.insert(0, str(CONF))
import driver  # noqa: E402

OK_STEP = {"op": "station_count", "expect": {"count": 1}}


def test_nothing_ran_is_not_success():
    r = run_driver("--runner", f"{sys.executable} {NULL_RUNNER}", "--only", "no-such-case-id$")
    assert r.returncode != 0, r.stdout[-500:]


def test_all_skipped_is_not_success(tmp_path):
    cases = write_cases(tmp_path, [{"id": "needs-fs", "requires": ["fs"], "steps": [OK_STEP]}])
    r = run_driver("--runner", f"{sys.executable} {NULL_RUNNER} --features none", "--cases", str(cases))
    assert r.returncode != 0, r.stdout[-500:]


def test_hello_without_features_list_exits_2(tmp_path):
    cases = write_cases(tmp_path, [{"id": "a", "steps": [OK_STEP]}])
    r = run_driver("--runner", write_fake_runner(tmp_path), "--cases", str(cases),
                   env={"FAKE_HELLO": '{"hello": {"runner": "fake"}}'})
    assert r.returncode == 2, (r.returncode, r.stdout[-300:], r.stderr[-300:])
    assert "Traceback" not in r.stderr


@pytest.mark.parametrize("reply", [
    {"ok": False, "error": "boom"},
    {"ok": False, "error": ["x"]},
    {"ok": False, "error": {"code": "not_found", "fields": "nope"}},
])
def test_non_object_error_or_fields_is_a_mismatch(reply):
    out = driver.evaluate({"error": "not_found", "error_fields": {"station_id": "x"}}, reply)
    assert out
    out = driver.evaluate({"count": 1}, reply)
    assert out


@pytest.mark.parametrize("ok", ["false", 1, 0, None, "true"])
def test_ok_must_be_boolean(ok):
    assert driver.evaluate({"count": 1}, {"ok": ok, "result": {"count": 1}})
    assert driver.evaluate({"error": "x"}, {"ok": ok, "error": {"code": "x"}})


def test_malformed_error_reply_does_not_abort_run(tmp_path):
    cases = write_cases(tmp_path, [{"id": "a", "steps": [{"op": "station", "args": {"station_id": "x"}, "expect": {"error": "not_found"}}]},
                                   {"id": "b", "steps": [OK_STEP]}])
    r = run_driver("--runner", write_fake_runner(tmp_path), "--cases", str(cases),
                   env={"FAKE_REPLY": '{"ok": false, "error": "boom"}'})
    assert "Traceback" not in r.stderr, r.stderr[-800:]
    assert "FAIL  a" in r.stdout and "FAIL  b" in r.stdout
    assert r.returncode == 1


@pytest.mark.parametrize("step", [
    {"driver": "assert_requests", "match": "(", "count": 0},          # re.error
    {"driver": "copy", "files": []},                                   # KeyError: to
    {"driver": "sleep", "s": [1]},                                     # TypeError
    {"driver": "server_rules", "rules": [{"action": "status", "status": 500}]},  # missing match
])
def test_harness_error_is_case_failure_and_exit_2(tmp_path, step):
    cases = write_cases(tmp_path, [{"id": "bad", "steps": [step, OK_STEP]}, {"id": "next", "steps": [OK_STEP]}])
    r = run_driver("--runner", f"{sys.executable} {NULL_RUNNER}", "--cases", str(cases))
    assert "Traceback" not in r.stderr, r.stderr[-800:]
    assert "FAIL  bad" in r.stdout and "[step 0" in r.stdout, r.stdout[-800:]
    assert "FAIL  next" in r.stdout
    assert r.returncode == 2


def test_corrupt_empty_file_is_failure_not_crash(tmp_path):
    cases = write_cases(tmp_path, [{"id": "c", "steps": [
        {"driver": "write", "path": "${tmp}/empty", "text": ""},
        {"driver": "corrupt", "path": "${tmp}/empty"}, OK_STEP]}])
    r = run_driver("--runner", f"{sys.executable} {NULL_RUNNER}", "--cases", str(cases))
    assert "Traceback" not in r.stderr, r.stderr[-800:]
    assert "FAIL  c" in r.stdout and "empty" in r.stdout, r.stdout[-500:]
    assert r.returncode == 1


def test_bad_case_file_exits_2(tmp_path):
    d = tmp_path / "cases"
    d.mkdir()
    (d / "x.json").write_text("{not json")
    r = run_driver("--runner", f"{sys.executable} {NULL_RUNNER}", "--cases", str(d))
    assert r.returncode == 2 and "Traceback" not in r.stderr, r.stderr[-500:]
    (d / "x.json").write_text('{"nocases": []}')
    r = run_driver("--check-cases", "--cases", str(d))
    assert r.returncode == 2 and "Traceback" not in r.stderr, r.stderr[-500:]


def test_bad_only_regex_exits_2():
    r = run_driver("--runner", f"{sys.executable} {NULL_RUNNER}", "--only", "(")
    assert r.returncode == 2 and "Traceback" not in r.stderr, r.stderr[-500:]


@pytest.mark.parametrize("reply", [
    '{"ok": false, "error": {"code": "uncaught:KeyError", "message": "x"}}',
    '{"ok": false, "error": {"code": "io_error", "message": "x"}}',
    '"not an object"',
])
def test_step_without_expect_fails_on_bad_reply(tmp_path, reply):
    cases = write_cases(tmp_path, [{"id": "a", "steps": [{"op": "close"}, {"op": "station_count", "expect": {"error": "io_error"}}]}])
    r = run_driver("--runner", write_fake_runner(tmp_path), "--cases", str(cases), env={"FAKE_REPLY": reply})
    assert "FAIL  a  [step 0 close]" in r.stdout, r.stdout[-500:]
