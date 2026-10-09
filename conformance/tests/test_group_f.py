"""Group F: the driver fails closed (review round 1, package PK19): a broken harness is a harness error (exit 2),
never a pass and never a plain runner failure."""
from __future__ import annotations

import json
import re
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


# --- R2-139: a .jsonl that the SDK left missing or corrupt is an SDK failure of assert_index, not a harness error

@pytest.mark.parametrize("jsonl", [None, "not json\n", '{"station_id": 1}\n'])
def test_assert_index_bad_sdk_jsonl_is_a_case_failure(tmp_path, jsonl):
    steps = [{"driver": "write", "path": "${tmp}/cache/index-v1.json", "text": "{}"}]
    if jsonl is not None:
        steps.append({"driver": "write", "path": "${tmp}/cache/OTC_20991231.jsonl", "text": jsonl})
    steps += [{"driver": "assert_index", "path": "${tmp}/cache/index-v1.json", "jsonl": "${tmp}/cache/OTC_20991231.jsonl",
               "datestamp": "20991231"}, OK_STEP]
    cases = write_cases(tmp_path, [{"id": "a", "steps": steps}])
    r = run_driver("--runner", write_fake_runner(tmp_path), "--cases", str(cases), env={"FAKE_REPLY": OK_REPLY})
    assert re.search(r"^FAIL  a  \[step \d+ assert_index\]", r.stdout, re.M), r.stdout[-800:]
    assert "harness error" not in r.stdout and r.returncode == 1, (r.returncode, r.stdout[-800:])


# --- R2-140: --check-cases lints an error matcher other than $any_of against api.json, with no traceback

@pytest.mark.parametrize("error,ok", [({"$regex": "^invalid_"}, True), ({"$regex": "^zzz"}, False),
                                      ({"$any_of": ["invalid_argument", {"$regex": "^zzz"}]}, False),
                                      ({"$any_of": ["invalid_argument", {"$contains": "release"}]}, True),
                                      ({"$type": "string"}, True)])
def test_check_cases_lints_error_matchers(tmp_path, error, ok):
    st = {"op": "station", "args": {"station_id": "x"}, "expect": {"error": error}}
    cases = write_cases(tmp_path, [{"id": "a", "steps": [st]}])
    r = run_driver("--check-cases", "--cases", str(cases))
    assert "Traceback" not in r.stderr, r.stderr[-800:]
    if ok:
        assert r.returncode == 0, (r.returncode, r.stdout[-400:])
    else:
        assert r.returncode == 2 and re.search(r"^PROBLEM a step 0: op station expects error .*api\.json", r.stdout, re.M), \
            (r.returncode, r.stdout[-400:])


# --- R2-141: --check-cases lints tolerance (a non-negative finite number)

@pytest.mark.parametrize("tol", ["x", -1e-6, True, None, [1]])
def test_check_cases_rejects_a_bad_tolerance(tmp_path, tol):
    st = {"op": "station_count", "expect": {"count": 1, "tolerance": tol}}
    cases = write_cases(tmp_path, [{"id": "a", "steps": [st]}])
    r = run_driver("--check-cases", "--cases", str(cases))
    assert r.returncode == 2 and re.search(r"^PROBLEM a step 0: .*tolerance", r.stdout, re.M), (r.returncode, r.stdout[-400:])


def test_check_cases_accepts_a_good_tolerance(tmp_path):
    st = {"op": "station_count", "expect": {"count": 1, "tolerance": 1e-6}}
    cases = write_cases(tmp_path, [{"id": "a", "steps": [st]}])
    r = run_driver("--check-cases", "--cases", str(cases))
    assert r.returncode == 0, (r.returncode, r.stdout[-400:])


# --- R2-167: --check-cases --cross expands inside the guard; ids duplicated across raw, expanded and cross cases are found

def test_check_cases_cross_with_a_bad_matrix_exits_2(tmp_path):
    cases = write_cases(tmp_path, [{"id": "m", "matrix": {"root": "good"}, "steps": []}])   # no release
    r = run_driver("--check-cases", "--cases", str(cases), "--cross", "a=x", "--cross", "b=y")
    assert r.returncode == 2 and "Traceback" not in r.stderr, (r.returncode, r.stdout[-400:], r.stderr[-800:])


def test_check_cases_finds_a_plain_id_that_a_matrix_case_also_expands_to(tmp_path):
    cases = write_cases(tmp_path, [{"id": "m", "matrix": {"root": "good", "release": "20991231.2"}, "steps": [OK_STEP]},
                                   {"id": "m@json", "steps": [OK_STEP]}])
    r = run_driver("--check-cases", "--cases", str(cases))
    assert r.returncode == 2 and re.search(r"^PROBLEM .*duplicate id 'm@json'", r.stdout, re.M), (r.returncode, r.stdout[-400:])


def test_check_cases_finds_an_id_in_both_cases_and_cross(monkeypatch):
    cross = driver.load_cases(driver.CROSS_DIR)
    plain = [dict(cross[0], roles=None, steps=[OK_STEP])]
    plain[0].pop("roles")
    problems = driver.id_problems(plain, cross)
    assert any("duplicate id" in p and cross[0]["id"] in p for p in problems), problems


# --- R2-143, R2-147: a driver step with an unknown or missing field asserts nothing; it is a case-file error, in the
# lint and in a run (a harness error, never a pass and never an SDK FAIL)

@pytest.mark.parametrize("step,word", [
    ({"driver": "assert_requests", "match": "x", "cuont": 0}, "cuont"),                     # typo of count
    ({"driver": "assert_requests", "source": "proxys", "count": 0}, "proxys"),              # no such log
    ({"driver": "assert_requests", "match": "x"}, "count"),                                 # asserts nothing
    ({"driver": "assert_requests", "count": "0"}, "count"),                                 # wrong type
    ({"driver": "assert_files", "dir": "${tmp}", "absnt": ["x"]}, "absnt"),
    ({"driver": "assert_files", "dir": "${tmp}"}, "present"),                               # asserts nothing
    ({"driver": "json_set", "path": "${tmp}/f.json", "pointer": "/a"}, "value"),            # R2-147
    ({"driver": "assert_json", "path": "${tmp}/f.json", "mtach": {"a": 1}}, "mtach"),
    ({"driver": "clear_log", "source": "proxy"}, "source"),
    ({"driver": "restart_runner", "env": {"X": 1}}, "env"),
])
def test_bad_driver_step_fields_are_case_errors(tmp_path, step, word):
    steps = [{"driver": "write", "path": "${tmp}/f.json", "text": '{"a": 1}'}, step, OK_STEP]
    cases = write_cases(tmp_path, [{"id": "a", "steps": steps}, {"id": "b", "steps": [OK_STEP]}])
    r = run_driver("--check-cases", "--cases", str(cases))
    assert r.returncode == 2 and re.search(rf"^PROBLEM a step 1: .*{word}", r.stdout, re.M), (r.returncode, r.stdout[-400:])
    r = run_driver("--runner", write_fake_runner(tmp_path), "--cases", str(cases), env={"FAKE_REPLY": OK_REPLY})
    assert re.search(r"^FAIL  a  \[step 1 \w+\] harness error", r.stdout, re.M) and "PASS  b" in r.stdout, r.stdout[-800:]
    assert r.returncode == 2 and "Traceback" not in r.stderr, (r.returncode, r.stderr[-500:])


# --- R2-142: a case whose rule names a missing fixture is a harness error, even when the SDK step expects a 404

def test_rule_with_a_missing_fixture_fails_the_case_as_a_harness_error(tmp_path):
    rule = {"match": "OTC_latest", "action": "file", "file": "good/no-such-file.json"}
    cases = write_cases(tmp_path, [{"id": "a", "steps": [{"driver": "server_rules", "rules": [rule]}, fetch("/good/OTC_latest.json")]},
                                   {"id": "b", "steps": [OK_STEP]}])
    r = run_driver("--check-cases", "--cases", str(cases))
    assert r.returncode == 2 and re.search(r"^PROBLEM a step 0: .*no-such-file", r.stdout, re.M), r.stdout[-400:]
    r = run_driver("--runner", write_fake_runner(tmp_path), "--cases", str(cases), env={"FAKE_REPLY": OK_REPLY})
    assert re.search(r"^FAIL  a  .*harness error", r.stdout, re.M) and "PASS  b" in r.stdout, r.stdout[-800:]
    assert r.returncode == 2, (r.returncode, r.stdout[-800:])


# --- R2-144: a recording-proxy relay failure (the upstream cannot be reached) is a harness error, not a network error

def test_proxy_relay_failure_is_a_harness_error(tmp_path, monkeypatch):
    srv, proxy = FixtureServer().start(), RecordingProxy().start()
    proxy.aliases[driver.SERVER_ALIAS] = srv.host
    # the fake runner fetches through the proxy (http_proxy); port 1 refuses, so the proxy answers 502
    case = {"id": "t", "env": {"http_proxy": "${proxy}"},
            "steps": [{"op": "latest", "args": {"fetch_url": f"http://{driver.SERVER_ALIAS}:1/good/OTC_latest.json"},
                       "expect": {"count": 1}}]}
    stats = {"steps_compared": 0, "steps_failed": 0, "harness_errors": 0}
    cmd = write_fake_runner(tmp_path).split()
    monkeypatch.setenv("FAKE_REPLY", OK_REPLY)
    try:
        failures, _ = driver.run_case(case, {"main": (cmd, set(driver.FEATURES))}, srv, proxy, False, False, stats)
    finally:
        srv.shutdown()
        proxy.shutdown()
    assert [e["status"] for e in proxy.log.entries()] == [502], proxy.log.entries()
    assert stats["harness_errors"] == 1 and any(f.get("driver") == "proxy" and f.get("harness_error") for f in failures), \
        (failures, stats)


def test_proxy_relay_success_is_not_a_harness_error(tmp_path, monkeypatch):
    srv, proxy = FixtureServer().start(), RecordingProxy().start()
    proxy.aliases[driver.SERVER_ALIAS] = srv.host
    case = {"id": "t", "env": {"http_proxy": "${proxy}"},
            "steps": [{"op": "latest", "args": {"fetch_url": "${server_alias}/good/OTC_latest.json"}, "expect": {"count": 1}}]}
    stats = {"steps_compared": 0, "steps_failed": 0, "harness_errors": 0}
    cmd = write_fake_runner(tmp_path).split()
    monkeypatch.setenv("FAKE_REPLY", OK_REPLY)
    try:
        failures, _ = driver.run_case(case, {"main": (cmd, set(driver.FEATURES))}, srv, proxy, False, False, stats)
    finally:
        srv.shutdown()
        proxy.shutdown()
    assert [e["status"] for e in proxy.log.entries()] == [200], proxy.log.entries()
    assert failures == [] and stats["harness_errors"] == 0, (failures, stats)


# --- R2-145: an explicit --expected-failures path that does not exist is a usage error, not "no entries"

def test_missing_explicit_expected_failures_file_exits_2(tmp_path):
    cases = write_cases(tmp_path, [{"id": "a", "steps": [OK_STEP]}])
    r = run_driver("--runner", write_fake_runner(tmp_path), "--cases", str(cases),
                   "--expected-failures", str(tmp_path / "nope.json"), env={"FAKE_REPLY": OK_REPLY})
    assert r.returncode == 2 and "nope.json" in r.stderr and "Traceback" not in r.stderr, (r.returncode, r.stdout[-300:], r.stderr[-300:])
    assert "PASS  a" not in r.stdout, r.stdout[-300:]


# --- R2-146: an expected-failure entry covers a wrong answer, not a runner crash, a hang or a failure at another step

def _crashing_runner(tmp_path, code):
    p = tmp_path / "crash.py"
    p.write_text("import sys\nprint('{\"hello\": {\"runner\": \"fake\", \"features\": []}}', flush=True)\n"
                 f"sys.stdin.readline()\nsys.exit({code})\n")
    return f"{sys.executable} {p}"


@pytest.mark.parametrize("code", [0, 1])
def test_expected_failure_does_not_cover_a_runner_crash(tmp_path, code):
    cases = write_cases(tmp_path, [{"id": "a", "steps": [OK_STEP]}])
    xf = _xf(tmp_path, [{"case": "a", "runners": ["fake"], "package": "PK00", "reason": "test"}])
    r = run_driver("--runner", _crashing_runner(tmp_path, code), "--cases", str(cases), "--expected-failures", str(xf))
    assert re.search(r"^FAIL  a  .*EOFError", r.stdout, re.M) and r.returncode == 1, (r.returncode, r.stdout[-500:])


def test_expected_failure_does_not_cover_a_timeout(tmp_path):
    p = tmp_path / "hang.py"
    p.write_text("import sys, time\nprint('{\"hello\": {\"runner\": \"fake\", \"features\": []}}', flush=True)\n"
                 "sys.stdin.readline()\nsys.stdin.read()\n")   # no reply: wait for stdin to close
    cases = write_cases(tmp_path, [{"id": "a", "timeout_s": 1, "steps": [OK_STEP]}])
    xf = _xf(tmp_path, [{"case": "a", "runners": ["fake"], "package": "PK00", "reason": "test"}])
    r = run_driver("--runner", f"{sys.executable} {p}", "--cases", str(cases), "--expected-failures", str(xf))
    assert re.search(r"^FAIL  a  .*TimeoutError", r.stdout, re.M) and r.returncode == 1, (r.returncode, r.stdout[-500:])


def test_expected_failure_step_pins_the_failing_step(tmp_path):
    steps = [{"op": "station_count", "expect": {"count": 2}}, {"op": "station_count", "expect": {"count": 1}}]
    cases = write_cases(tmp_path, [{"id": "a", "steps": steps}])
    env = {"FAKE_REPLY": OK_REPLY}   # step 0 fails (count 1, not 2)
    xf = _xf(tmp_path, [{"case": "a", "runners": ["fake"], "package": "PK00", "reason": "test", "step": 0}])
    r = run_driver("--runner", write_fake_runner(tmp_path), "--cases", str(cases), "--expected-failures", str(xf), env=env)
    assert re.search(r"^XFAIL  a", r.stdout, re.M) and r.returncode == 0, (r.returncode, r.stdout[-500:])
    xf = _xf(tmp_path, [{"case": "a", "runners": ["fake"], "package": "PK00", "reason": "test", "step": 1}])
    r = run_driver("--runner", write_fake_runner(tmp_path), "--cases", str(cases), "--expected-failures", str(xf), env=env)
    assert re.search(r"^FAIL  a  \[step 0", r.stdout, re.M) and r.returncode == 1, (r.returncode, r.stdout[-500:])


@pytest.mark.parametrize("step", ["1", -1, True, 1.5])
def test_check_cases_lints_the_expected_failure_step(tmp_path, step):
    cases = write_cases(tmp_path, [{"id": "a", "steps": [OK_STEP]}])
    bad = [{"case": "a", "runners": ["python"], "package": "PK01", "reason": "x", "step": step}]
    r = run_driver("--check-cases", "--cases", str(cases), "--expected-failures", str(_xf(tmp_path, bad)))
    assert r.returncode == 2 and re.search(r"^PROBLEM expected-failures entry 0 .*step", r.stdout, re.M), r.stdout[-400:]
