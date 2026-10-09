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


# --- K13: a tripwire that cannot accept connections fails the case (a "no socket" check would pass vacuously)

def test_tripwire_accept_errors_fail_the_case(tmp_path, monkeypatch):
    srv, proxy = FixtureServer().start(), RecordingProxy().start()
    real_stop = srv.stop

    def broken_stop():
        real_stop()
        srv._trip_sock.close()  # accept() now fails at once: the tripwire records nothing

    monkeypatch.setattr(srv, "stop", broken_stop)
    case = {"id": "t", "steps": [{"driver": "server_stop"}, {"driver": "sleep", "s": 0.3},
                                 {"driver": "assert_requests", "source": "tripwire", "count": 0},
                                 {"op": "station_count", "expect": {"count": 1}}]}
    stats = {"steps_compared": 0, "steps_failed": 0, "harness_errors": 0}
    cmd = write_fake_runner(tmp_path).split()
    monkeypatch.setenv("FAKE_REPLY", OK_REPLY)
    try:
        failures, _ = driver.run_case(case, {"main": (cmd, set(driver.FEATURES))}, srv, proxy, False, False, stats)
    finally:
        srv.shutdown()
        proxy.shutdown()
    assert failures and stats["harness_errors"] == 1, (failures, stats)


# --- K6: an OSError in a driver action (a case-file error) is a harness error, not a runner failure

@pytest.mark.parametrize("step", [
    {"driver": "delete", "path": "${tmp}/no-such-file"},
    {"driver": "copy", "files": ["${tmp}/no-such-file"], "to": "${tmp}/x"},
    {"driver": "assert_sha256", "path": "${tmp}/f", "equals": "${tmp}/no-such-file"},
])
def test_driver_action_oserror_is_a_harness_error(tmp_path, step):
    steps = [{"driver": "write", "path": "${tmp}/f", "text": "x"}, step, OK_STEP]
    cases = write_cases(tmp_path, [{"id": "a", "steps": steps}, {"id": "b", "steps": [OK_STEP]}])
    r = run_driver("--runner", write_fake_runner(tmp_path), "--cases", str(cases), env={"FAKE_REPLY": OK_REPLY})
    assert "FAIL  a  [step 1" in r.stdout and "harness error" in r.stdout and "PASS  b" in r.stdout, r.stdout[-800:]
    assert r.returncode == 2 and "Traceback" not in r.stderr, (r.returncode, r.stderr[-500:])


# --- K62: a bad case env or timeout_s is a harness error for that case; the run goes on; the lint finds it

@pytest.mark.parametrize("extra", [{"env": {"X": "${no_such_placeholder}"}}, {"timeout_s": "soon"}])
def test_bad_env_or_timeout_is_a_case_error(tmp_path, extra):
    cases = write_cases(tmp_path, [{"id": "a", "steps": [OK_STEP], **extra}, {"id": "b", "steps": [OK_STEP]}])
    r = run_driver("--runner", write_fake_runner(tmp_path), "--cases", str(cases), env={"FAKE_REPLY": OK_REPLY})
    assert "Traceback" not in r.stderr, r.stderr[-800:]
    assert "FAIL  a" in r.stdout and "PASS  b" in r.stdout and r.returncode == 2, (r.returncode, r.stdout[-500:])
    r = run_driver("--check-cases", "--cases", str(cases))
    assert r.returncode == 2 and "PROBLEM" in r.stdout and "Traceback" not in r.stderr, r.stdout[-500:]


# --- K4: a server that cannot restart after a case is a harness error, not an exception out of run_case

def test_resume_failure_does_not_escape_run_case(tmp_path, monkeypatch):
    srv, proxy = FixtureServer().start(), RecordingProxy().start()

    def boom():
        raise OSError(98, "Address already in use (test)")

    case = {"id": "t", "steps": [{"driver": "server_stop"}, {"op": "station_count", "expect": {"count": 1}}]}
    stats = {"steps_compared": 0, "steps_failed": 0, "harness_errors": 0}
    cmd = write_fake_runner(tmp_path).split()
    monkeypatch.setenv("FAKE_REPLY", OK_REPLY)
    try:
        monkeypatch.setattr(srv, "resume", boom)
        failures, _ = driver.run_case(case, {"main": (cmd, set(driver.FEATURES))}, srv, proxy, False, False, stats)
    finally:
        monkeypatch.undo()
        srv.shutdown()
        proxy.shutdown()
    assert failures and stats["harness_errors"] == 1 and stats.get("abort"), (failures, stats)


# --- K68: --check-cases rejects an unknown matcher, a bad matcher argument and a mixed $-object

@pytest.mark.parametrize("value", [{"$contain": "x"}, {"$regex": "("}, {"$type": "int"}, {"$len_min": "2"},
                                   {"$all": {"$contains": "x"}}, {"$any_of": "x"}, {"$contains": "x", "other": 1},
                                   [{"$conatins": "x"}]])
def test_check_cases_rejects_bad_matchers(tmp_path, value):
    cases = write_cases(tmp_path, [{"id": "a", "steps": [{"op": "citation", "expect": {"citation": value}}]}])
    r = run_driver("--check-cases", "--cases", str(cases))
    assert r.returncode == 2 and "PROBLEM" in r.stdout and "Traceback" not in r.stderr, (r.returncode, r.stdout[-400:], r.stderr[-400:])


# --- K18: an error expectation with a key that is not error, error_fields, error_message or tolerance

def test_error_expectation_with_result_keys_is_rejected(tmp_path):
    exp = {"error": "not_found", "count": 1}
    cases = write_cases(tmp_path, [{"id": "a", "steps": [{"op": "station_count", "expect": exp}]}])
    r = run_driver("--check-cases", "--cases", str(cases))
    assert r.returncode == 2 and "count" in r.stdout, r.stdout[-400:]
    r = run_driver("--runner", write_fake_runner(tmp_path), "--cases", str(cases),
                   env={"FAKE_REPLY": '{"ok": false, "error": {"code": "not_found"}}'})
    assert "FAIL  a" in r.stdout and r.returncode == 2, (r.returncode, r.stdout[-400:])


# --- K7: header regexes are compiled even when no request is logged; all: true needs at least one request

def test_assert_requests_bad_header_regex_on_empty_log(tmp_path):
    st = {"driver": "assert_requests", "header": {"user-agent": "("}, "count": 0}
    cases = write_cases(tmp_path, [{"id": "a", "steps": [st, OK_STEP]}])
    r = run_driver("--check-cases", "--cases", str(cases))
    assert r.returncode == 2 and "PROBLEM" in r.stdout, r.stdout[-400:]
    r = run_driver("--runner", write_fake_runner(tmp_path), "--cases", str(cases), env={"FAKE_REPLY": OK_REPLY})
    assert "FAIL  a" in r.stdout and r.returncode == 2, (r.returncode, r.stdout[-400:])


def test_assert_requests_all_with_no_request_fails():
    srv, proxy = FixtureServer().start(), RecordingProxy().start()
    try:
        out = driver.act_assert_requests({"header": {"user-agent": "^x"}, "all": True}, srv, proxy)
    finally:
        srv.shutdown()
        proxy.shutdown()
    assert out, "all: true passed with no request to check"


# --- K70: a cross case's own "requires" applies to every runner it assigns

def test_cross_case_requires_applies_to_every_role():
    c = {"id": "x", "requires": ["json"], "roles": {"writer": ["fs"], "reader": ["fs"]}, "steps": []}
    hellos = {"a": (["a"], {"fs", "json"}), "b": (["b"], {"fs"})}
    assert [v["id"] for v in driver.expand_cross([c], hellos)] == []
    hellos["b"] = (["b"], {"fs", "json"})
    assert sorted(v["id"] for v in driver.expand_cross([c], hellos)) == ["x[a>b]", "x[b>a]"]


# --- K1: --check-cases with --cross lints cases/ and cross/ once each, with no false problems

def test_check_cases_with_cross_has_no_false_problems():
    # the same problems with and without --cross (api.json gaps, if any, are K77's and show in both)
    plain = run_driver("--check-cases")
    r = run_driver("--check-cases", "--cross", "a=x", "--cross", "b=y")
    assert "must not have roles" not in r.stdout and "Traceback" not in r.stderr, r.stdout[-600:]
    assert r.returncode == plain.returncode and r.stdout == plain.stdout, (r.stdout[-300:], plain.stdout[-300:])


# --- K16, K69, K67, K15: malformed case content, a bad hello runner name and a bad command give exit 2, no traceback

@pytest.mark.parametrize("cases", [
    [{"id": "a", "steps": [{"op": "citation", "expect": "x"}]}],                                   # expect not an object
    [{"id": "a", "steps": [{"op": "citation", "expect_if_missing": {"fs": ["x"]}}]}],              # not an object
    [{"id": "a", "roles": {"w": ["fs"], "r": ["fs"]}, "steps": [{"op": "citation", "as": [{"x": 1}], "expect": {"citation": "c"}}]}],
    [{"id": "a", "roles": {"w": ["fs"], "r": ["fs"]}, "steps": [{"op": "citation", "as": 5, "expect": {"citation": "c"}}]}],
    [{"steps": [{"op": "citation", "expect": {"citation": "c"}}]}],                                # no id
    [{"id": "a", "steps": "x"}],                                                                   # steps not a list
    [{"id": "a", "steps": ["x"]}],                                                                 # a step not an object
    [{"id": "a", "steps": [{"op": "citation", "args": ["x"], "expect": {"citation": "c"}}]}],     # args not an object
])
def test_malformed_case_content_exits_2(tmp_path, cases):
    d = write_cases(tmp_path, cases)
    r = run_driver("--check-cases", "--cases", str(d))
    assert r.returncode == 2 and "Traceback" not in r.stderr, (r.returncode, r.stdout[-300:], r.stderr[-500:])
    r = run_driver("--runner", write_fake_runner(tmp_path), "--cases", str(d), env={"FAKE_REPLY": OK_REPLY})
    assert r.returncode == 2 and "Traceback" not in r.stderr, (r.returncode, r.stdout[-300:], r.stderr[-500:])


@pytest.mark.parametrize("hello", ['{"hello": {"runner": ["x"], "features": []}}', '{"hello": {"runner": {"a": 1}, "features": []}}'])
def test_unhashable_hello_runner_exits_2(tmp_path, hello):
    cases = write_cases(tmp_path, [{"id": "a", "steps": [OK_STEP]}])
    r = run_driver("--runner", write_fake_runner(tmp_path), "--cases", str(cases), env={"FAKE_HELLO": hello})
    assert r.returncode == 2 and "Traceback" not in r.stderr, (r.returncode, r.stderr[-500:])


@pytest.mark.parametrize("args", [["--runner", "python 'unbalanced"], ["--cross", "a=python 'x", "--cross", "b=y"]])
def test_unbalanced_quote_in_command_exits_2(args):
    r = run_driver(*args)
    assert r.returncode == 2 and "Traceback" not in r.stderr, (r.returncode, r.stderr[-500:])


# --- K77: --check-cases flags an expected error code that the operation's api.json errors list does not have



def _api_with(tmp_path, op, errors):
    api = json.loads((CONF / "api.json").read_text(encoding="utf-8"))
    for obj in api["objects"].values():
        for m in obj.get("members", []):
            if m["name"] == op:
                m["errors"] = errors
    p = tmp_path / "api.json"
    p.write_text(json.dumps(api))
    return p


def test_check_cases_flags_error_not_in_api(tmp_path):
    cases = write_cases(tmp_path, [{"id": "a", "requires": ["fetch"], "steps": [{"op": "check_for_update", "expect": {"error": "reader_too_old"}}]}])
    api = _api_with(tmp_path, "check_for_update", ["network", "offline_unavailable"])
    r = run_driver("--check-cases", "--cases", str(cases), "--api", str(api))
    assert r.returncode == 2 and "reader_too_old" in r.stdout and "check_for_update" in r.stdout, (r.returncode, r.stdout[-400:], r.stderr[-300:])
    api = _api_with(tmp_path, "check_for_update", ["network", "offline_unavailable", "reader_too_old"])
    r = run_driver("--check-cases", "--cases", str(cases), "--api", str(api))
    assert r.returncode == 0, (r.stdout[-400:], r.stderr[-300:])


def test_check_cases_flags_error_in_expect_if_missing(tmp_path):
    st = {"op": "verify", "expect": {"verified": True}, "expect_if_missing": {"fs": {"error": "file_exists"}}}
    cases = write_cases(tmp_path, [{"id": "a", "steps": [st]}])
    r = run_driver("--check-cases", "--cases", str(cases))
    assert r.returncode == 2 and "file_exists" in r.stdout, r.stdout[-400:]


# --- K55, K56: --check-cases finds a step that needs a feature the case does not require (eager, json, fs)

@pytest.mark.parametrize("st,feature", [
    ({"op": "open", "args": {"base_url": "x", "cache_dir": "${cache}", "mode": "eager"}, "expect": {"datestamp": "d"},
      "expect_if_missing": {"fetch": {"error": "not_built"}}}, "eager"),
    ({"op": "open", "args": {"file": "${tmp}/OTC_20991231.json"}, "expect": {"error": "io"}}, "json"),
    ({"op": "open", "args": {"base_url": "x", "cache_dir": "${cache}"}, "expect": {"datestamp": "d"},
      "expect_if_missing": {"fetch": {"error": "not_built"}}}, "fs"),
])
def test_check_cases_finds_missing_requires(tmp_path, st, feature):
    cases = write_cases(tmp_path, [{"id": "a", "requires": [], "steps": [st]}])
    r = run_driver("--check-cases", "--cases", str(cases))
    assert r.returncode == 2 and f"'{feature}'" in r.stdout, (r.returncode, r.stdout[-400:])


def test_expect_if_missing_covers_later_steps(tmp_path):
    steps = [{"op": "download", "args": {"to": "x"}, "expect": {"paths": ["a"]},
              "expect_if_missing": {"fetch": {"error": "not_built"}, "fs": {"error": "unsupported"}}},
             {"op": "open", "args": {"file": "${tmp}/OTC_20991231.jsonl"}, "expect": {"datestamp": "d"}}]
    cases = write_cases(tmp_path, [{"id": "a", "requires": [], "steps": steps}])
    r = run_driver("--check-cases", "--cases", str(cases))
    assert r.returncode == 0, r.stdout[-400:]


# --- expected failures: a listed case that fails is XFAIL (the run passes), one that passes is XPASS (the run fails)

def _xf(tmp_path, entries):
    p = tmp_path / "xf.json"
    p.write_text(json.dumps({"entries": entries}))
    return p


def test_expected_failure_is_xfail_and_the_run_passes(tmp_path):
    cases = write_cases(tmp_path, [{"id": "a", "steps": [OK_STEP]}, {"id": "b", "steps": [OK_STEP]}])
    xf = _xf(tmp_path, [{"case": "a", "runners": ["fake"], "package": "PK00", "reason": "test"}])
    env = {"FAKE_REPLY": '{"ok": true, "result": {"count": 1}}'}
    r = run_driver("--runner", write_fake_runner(tmp_path), "--cases", str(cases), "--expected-failures", str(xf), env=env)
    assert "XPASS  a" in r.stdout and r.returncode == 1, r.stdout[-500:]       # a passes but is listed: strict
    env = {"FAKE_REPLY": '{"ok": true, "result": {"count": 2}}'}
    xf = _xf(tmp_path, [{"case": "*", "runners": ["fake"], "package": "PK00", "reason": "test"}])
    r = run_driver("--runner", write_fake_runner(tmp_path), "--cases", str(cases), "--expected-failures", str(xf), env=env)
    assert "XFAIL  a" in r.stdout and "XFAIL  b" in r.stdout and r.returncode == 0, r.stdout[-500:]
    r = run_driver("--runner", write_fake_runner(tmp_path), "--cases", str(cases), "--expected-failures", str(xf),
                   "--no-expected-failures", env=env)
    assert "FAIL  a" in r.stdout and r.returncode == 1, r.stdout[-500:]


def test_expected_failure_for_another_runner_does_not_apply(tmp_path):
    cases = write_cases(tmp_path, [{"id": "a", "steps": [OK_STEP]}])
    xf = _xf(tmp_path, [{"case": "a", "runners": ["ruby"], "package": "PK00", "reason": "test"}])
    r = run_driver("--runner", write_fake_runner(tmp_path), "--cases", str(cases), "--expected-failures", str(xf),
                   env={"FAKE_REPLY": '{"ok": true, "result": {"count": 2}}'})
    assert "FAIL  a" in r.stdout and "XFAIL" not in r.stdout and r.returncode == 1, r.stdout[-500:]


def test_check_cases_lints_the_expected_failures(tmp_path):
    cases = write_cases(tmp_path, [{"id": "a", "steps": [OK_STEP]}])
    for bad in [[{"case": "no-such-case", "runners": ["python"], "package": "PK01", "reason": "x"}],
                [{"case": "a", "runners": ["pyhton"], "package": "PK01", "reason": "x"}],
                [{"case": "a", "runners": ["python"]}]]:
        r = run_driver("--check-cases", "--cases", str(cases), "--expected-failures", str(_xf(tmp_path, bad)))
        assert r.returncode == 2 and "expected-failures" in r.stdout, r.stdout[-400:]


def test_committed_expected_failures_are_clean():
    r = run_driver("--check-cases")
    bad = [l for l in r.stdout.splitlines() if l.startswith("PROBLEM") and "expected-failures" in l]
    assert not bad and "case check:" in r.stdout, bad[:5] or r.stdout[-400:]


# --- harness support for the review round 1 cases: chmod, assert_tree, an error matcher

def test_chmod_and_assert_tree(tmp_path):
    import stat
    d = tmp_path / "c"
    (d / "v1" / "x").mkdir(parents=True)
    (d / "v1" / "x" / "f").write_text("x")
    assert driver.act_assert_tree({"dir": str(d), "allow": ["v1", "v1/**"]}) == []
    (d / "ESCAPED").mkdir()
    assert driver.act_assert_tree({"dir": str(d), "allow": ["v1", "v1/**"]})
    problems, _ = driver.run_action({"driver": "chmod", "path": str(d / "v1"), "mode": "555"}, {}, None, None)
    assert not problems and stat.S_IMODE((d / "v1").stat().st_mode) == 0o555
    driver.restore_writable(tmp_path)
    assert stat.S_IMODE((d / "v1").stat().st_mode) & 0o200


def test_error_expectation_may_be_a_matcher():
    exp = {"error": {"$any_of": ["io", "checksum_mismatch"]}}
    assert driver.evaluate(exp, {"ok": False, "error": {"code": "io"}}) == []
    assert driver.evaluate(exp, {"ok": False, "error": {"code": "network"}})
    assert driver.evaluate(exp, {"ok": True, "result": {}})


def test_expected_failure_matches_a_cross_id_exactly():
    e = [{"case": "cross/x[python>ruby]", "runners": ["cross"]}]
    assert driver.expected_failure(e, "cross/x[python>ruby]", "cross")
    assert not driver.expected_failure(e, "cross/x[ruby>python]", "cross")
    assert driver.expected_failure([{"case": "rules/pk01/*", "runners": ["python"]}], "rules/pk01/a@json", "python")
