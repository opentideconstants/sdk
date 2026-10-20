"""Group K: the prediction ops, runner features and profiles (prediction spec 5.2, 6.5; slot K2), and api.json
pending_port (the prediction names each SDK does not have yet)."""
from __future__ import annotations

import json
import importlib.util
import re
import sys

import pytest

from _util import CONF, run_driver, write_cases, write_fake_runner

sys.path.insert(0, str(CONF))
import driver  # noqa: E402

API = json.loads((CONF / "api.json").read_text(encoding="utf-8"))
OPEN = {"op": "open", "args": {"file": "${fixtures}/good/OTC_20991231.2.jsonl", "mode": "stream"},
        "expect": {"datestamp": "20991231.2"}}
REQ = ["fs", "stream", "predict"]
PREDICTION_STEPS = {
    "heights": {"station_id": "OTC-T-0001", "start": "2010-01-01T00:00:00Z", "stop": "2010-01-02T00:00:00Z",
                "step_s": 600, "datum": "chart", "set_id": None},
    "heights_at": {"station_id": "OTC-T-0001", "times": ["2010-01-01T00:00:00Z"], "datum": None, "set_id": None},
    "extremes": {"station_id": "OTC-T-0001", "start": "2010-01-01T00:00:00Z", "stop": "2010-01-02T00:00:00Z",
                 "datum": None, "set_id": None},
    "currents": {"station_id": "OTC-T-0001", "start": "2010-01-01T00:00:00Z", "stop": "2010-01-02T00:00:00Z",
                 "step_s": 600, "bin_number": 1, "set_id": None},
    "current_events": {"station_id": "OTC-T-0001", "start": "2010-01-01T00:00:00Z", "stop": "2010-01-02T00:00:00Z",
                       "bin_number": None, "set_id": None},
    "datums": {"station_id": "OTC-T-0001", "set_id": None, "all_sets": True},
    "ranges": {"station_id": "OTC-T-0001", "set_id": None},
    "astro_table": {"id": None},
    "equilibrium_argument": {"id": None, "name": "M2", "at": "2010-01-01T00:00:00Z"},
    "node_factor": {"id": None, "name": "M2", "at": "2010-01-01T00:00:00Z"},
    "equilibrium_for_year": {"id": None, "name": "M2", "year": 2010},
    "node_factor_for_year": {"id": None, "name": "M2", "year": 2010},
    "valid_range": {"id": None},
}


def lint(tmp_path, cases):
    return run_driver("--check-cases", "--cases", str(write_cases(tmp_path, cases)))


# --- ops

@pytest.mark.parametrize("op", sorted(PREDICTION_STEPS))
def test_prediction_op_with_every_argument_is_accepted(tmp_path, op):
    r = lint(tmp_path, [{"id": "p", "requires": REQ, "steps": [OPEN, {"op": op, "args": PREDICTION_STEPS[op],
                                                                     "expect": {"x": 1}}]}])
    assert r.returncode == 0 and "0 problems" in r.stdout, r.stdout[-600:]


def test_to_local_is_accepted_and_needs_the_local_time_features(tmp_path):
    step = {"op": "to_local", "args": {"tz": "Asia/Kolkata"}, "expect": {"x": 1}}
    ok = lint(tmp_path, [{"id": "p", "requires": REQ + ["localtime_module", "localtime"], "steps": [OPEN, step]}])
    assert ok.returncode == 0, ok.stdout[-600:]
    missing = lint(tmp_path, [{"id": "p", "requires": REQ, "steps": [OPEN, step]}])
    assert missing.returncode == 2 and "op to_local uses 'localtime', 'localtime_module'" in missing.stdout, missing.stdout
    # a runner without zone rules takes expect_if_missing (prediction spec 6.5, local-missing-dependency)
    eim = dict(step, expect_if_missing={"localtime": {"error": "local_time_unavailable"}})
    r = lint(tmp_path, [{"id": "p", "requires": REQ + ["localtime_module"], "steps": [OPEN, eim]}])
    assert r.returncode == 0, r.stdout[-600:]


def test_unknown_prediction_argument_is_refused(tmp_path):
    r = lint(tmp_path, [{"id": "p", "requires": REQ, "steps": [
        OPEN, {"op": "heights", "args": {"station_id": "X", "from": "2010-01-01T00:00:00Z"}, "expect": {"x": 1}}]}])
    assert r.returncode == 2 and "op heights has no argument 'from'" in r.stdout, r.stdout


def test_prediction_op_needs_predict_unless_expect_if_missing_covers_it(tmp_path):
    step = {"op": "heights", "args": {"station_id": "X"}, "expect": {"x": 1}}
    r = lint(tmp_path, [{"id": "p", "requires": ["fs", "stream"], "steps": [OPEN, step]}])
    assert r.returncode == 2 and "op heights uses 'predict'" in r.stdout, r.stdout
    nb = dict(step, expect_if_missing={"predict": {"error": "not_built"}})   # not-built/otc_heights (6.5)
    r = lint(tmp_path, [{"id": "p", "requires": ["fs", "stream"], "steps": [OPEN, nb]}])
    assert r.returncode == 0, r.stdout[-600:]


def test_datums_and_ranges_need_no_prediction_feature():
    assert driver.step_needs({"op": "datums", "args": {}}) == set()
    assert driver.step_needs({"op": "ranges", "args": {}}) == set()
    assert driver.step_needs({"op": "valid_range", "args": {}}) == {"predict"}


def test_prediction_errors_come_from_api_json():
    by_op = driver.api_errors(driver.API)
    assert {"no_constants", "extremes_only", "time_out_of_range"} <= by_op["heights"]
    assert "extremes_only" not in by_op["extremes"] and "bin_not_found" in by_op["current_events"]
    assert {"local_time_unavailable", "unknown_time_zone"} <= by_op["to_local"]
    # an astro op gets its table first, so the table check's invalid_argument is allowed for every astro op
    assert "invalid_argument" in by_op["valid_range"] and "unsupported_constituent" in by_op["node_factor"]


def test_check_cases_flags_an_error_api_json_does_not_list_for_a_prediction_op(tmp_path):
    step = {"op": "extremes", "args": {"station_id": "X"}, "expect": {"error": "extremes_only"}}
    r = lint(tmp_path, [{"id": "p", "requires": REQ, "steps": [OPEN, step]}])
    assert r.returncode == 2 and "op extremes expects error \"extremes_only\"" in r.stdout, r.stdout


# --- features and profiles (prediction spec 6.5)

def test_the_four_features_exist():
    assert {"predict", "localtime_module", "localtime", "tzdir_env"} <= set(driver.FEATURES)


@pytest.mark.parametrize("profile,want", [
    ("python", {"predict", "localtime_module", "localtime"}), ("ruby", {"predict", "localtime_module", "localtime"}),
    ("typescript", {"predict", "localtime_module", "localtime"}),
    ("swift", {"predict", "localtime_module", "localtime"}),
    ("typescript-browser", {"predict", "localtime_module", "localtime"}),
    ("c", {"predict", "localtime_module", "localtime", "tzdir_env"}),
    ("c-fetch", {"predict", "localtime_module", "localtime", "tzdir_env"}),
    ("python-no-tz", {"predict", "localtime_module"}), ("ruby-no-tz", {"predict", "localtime_module"}),
    ("c-no-localtime", {"predict"}), ("c-no-predict", set()),
])
def test_profile_prediction_features(profile, want):
    four = {"predict", "localtime_module", "localtime", "tzdir_env"}
    assert set(driver.PROFILES[profile]) & four == want


@pytest.mark.parametrize("profile,base", [("python-no-tz", "python"), ("ruby-no-tz", "ruby"), ("c-no-localtime", "c"),
                                          ("c-no-predict", "c")])
def test_new_profiles_keep_their_base_features(profile, base):
    four = {"predict", "localtime_module", "localtime", "tzdir_env"}
    assert set(driver.PROFILES[profile]) - four == set(driver.PROFILES[base]) - four


def test_new_profiles_are_expected_failure_runners():
    assert {"python-no-tz", "ruby-no-tz", "c-no-localtime", "c-no-predict"} <= driver.XF_RUNNERS


def test_accepted_prediction_profiles_require_native_features():
    base = ["fs", "fetch", "json", "eager", "stream", "https_proxy", "station_bbox"]
    assert "predict" in driver.profile_problem("python", base)
    assert "predict" in driver.profile_problem("python-no-tz", base)
    assert "stream" in driver.profile_problem("python", ["fs", "fetch", "json", "eager", "https_proxy"])
    assert driver.profile_problem("python", base + driver.PREDICT_FEATURES + ["prediction_units"]) is None
    assert driver.profile_problem("swift", driver.LANG_FEATURES + driver.PREDICT_FEATURES + ["prediction_units"]) is None
    assert driver.profile_problem("c-no-predict", ["fs", "stream", "require_checksum"]) is None


@pytest.mark.parametrize("profile,claims,rc", [
    ("python-no-tz", ["fs", "fetch", "json", "eager", "stream", "https_proxy"], 2),
    ("python-no-tz", ["fs", "fetch", "json", "eager", "stream", "https_proxy", "localtime_module"], 2),
    ("c-no-localtime", ["fs", "stream", "require_checksum"], 2),
    ("c-no-predict", ["fs", "stream", "require_checksum"], 0),
])
def test_handshake_with_a_new_profile(tmp_path, profile, claims, rc):
    cases = write_cases(tmp_path, [{"id": "a", "steps": [{"op": "station_count", "expect": {"count": 1}}]}])
    hello = json.dumps({"hello": {"runner": "fake", "features": claims}})
    r = run_driver("--runner", write_fake_runner(tmp_path), "--cases", str(cases), "--profile", profile,
                   env={"FAKE_HELLO": hello})
    if rc == 2:
        assert r.returncode == 2 and "required features" in r.stderr, (r.returncode, r.stderr[-300:])
    else:   # the handshake passes; the one case then fails on the fake runner's empty reply
        assert r.returncode == 1 and "handshake" not in r.stderr and "1 failed" in r.stdout, (r.stdout[-300:], r.stderr[-300:])


# --- api.json pending_port

LANG_PROFILES = {"python": ["python", "python-no-tz"], "ruby": ["ruby", "ruby-no-tz"],
                 "typescript": ["typescript", "typescript-browser"], "c": ["c", "c-fetch", "c-no-localtime"],
                 "swift": ["swift"]}


def test_reserved_phase2_is_gone():
    assert "reserved_phase2" not in API and set(API["pending_port"]) == {"note", *LANG_PROFILES}


@pytest.mark.parametrize("lang", sorted(LANG_PROFILES))
def test_pending_names_are_manifest_names_of_the_language(lang):
    pend = API["pending_port"][lang]
    for o in pend["objects"]:
        assert o in API["objects"], o
    for qn in pend["members"]:
        obj, name = qn.split(".", 1)
        m = [x for x in API["objects"][obj]["members"] if x["name"] == name]
        assert m and lang in m[0].get("languages", [lang]), qn
    for e in pend["enums"]:
        assert e in API["enums"], e
    by_code = {e["code"]: e for e in API["errors"]}
    for c in pend["errors"]:
        assert lang in by_code[c]["languages"] and (by_code[c]["c"] if lang == "c" else by_code[c]["class"]), c
    for s in pend.get("c_structs", []):
        assert lang == "c" and s in API["c_structs"], s


@pytest.mark.parametrize("lang", sorted(LANG_PROFILES))
def test_driver_pending_features_follow_api_pending_port(lang):
    """A port removes its api.json pending names and its driver PENDING_FEATURES together."""
    api_pending = "Release.heights" in API["pending_port"][lang]["members"]
    for profile in LANG_PROFILES[lang]:
        assert ("predict" in driver.PENDING_FEATURES.get(profile, [])) == api_pending, profile


def test_every_prediction_error_is_in_api_json():
    codes = {e["code"]: e for e in API["errors"]}
    want = {"no_constants": [], "quantity_mismatch": [], "unsupported_convention": [], "no_astro_table": [],
            "unsupported_constituent": ["constituent"], "time_out_of_range": ["first_year", "last_year"],
            "datum_unavailable": ["missing"], "bin_not_found": [], "extremes_only": [], "local_time_unavailable": [],
            "unknown_time_zone": ["zone"], "reference_unavailable": ["reference_station_id"]}
    for code, fields in want.items():
        e = codes[code]
        assert e["fields"] == fields and e["c"] == "OTC_E_" + code.upper(), code
        assert e["class"] == "".join(p.capitalize() for p in code.split("_")) + "Error", code


# --- the C API check (c/tools/check_manifest.py) with pending names; it reads only the header, so it runs here

def _c_check():
    spec = importlib.util.spec_from_file_location("check_manifest", CONF.parent / "c" / "tools" / "check_manifest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, (CONF.parent / "c" / "include" / "opentideconstants.h").read_text(encoding="utf-8")


def test_c_check_passes_with_accepted_prediction_names_active():
    cm, header = _c_check()
    assert cm.check(API, header)[0] == []


def test_c_check_allows_a_pending_status_declared_early():
    """CR D24: a port may fix a pending error's status number early; the check and its self-test still pass."""
    cm, header = _c_check()
    pending = json.loads(json.dumps(API))
    pending["pending_port"]["c"]["errors"] = ["no_constants"]
    assert cm.check(pending, header)[0] == []
    assert cm.self_test(pending, header)[0] == []


@pytest.mark.parametrize("decl,name", [("OTC_API otc_status otc_heights(void);", "otc_heights"),
                                       ("OTC_API otc_status otc_tz_open(void);", "otc_tz_open"),
                                       ("typedef struct otc_predict_opts { size_t struct_size; } otc_predict_opts;",
                                        "otc_predict_opts")])
def test_c_check_refuses_a_pending_name_declared(decl, name):
    cm, header = _c_check()
    pending = json.loads(json.dumps(API))
    pending["pending_port"]["c"]["members"] = ["Release.heights", "HeightSeries.to_local"]
    pending["pending_port"]["c"]["c_structs"] = ["otc_predict_opts"]
    bad = header.replace("OTC_API void otc_close(", decl + "\nOTC_API void otc_close(", 1)
    assert any(p.startswith(f"{name}  (pending for C") for p in cm.check(pending, bad)[0])


def test_c_self_test_skips_the_mutations_of_a_ported_name():
    cm, header = _c_check()
    ported = json.loads(json.dumps(API))
    ported["pending_port"]["c"] = {"objects": [], "members": [], "enums": [], "errors": [], "c_structs": []}
    problems, _ = cm.check(ported, header)
    assert problems == []
    dropped = re.sub(r"OTC_API otc_status otc_heights\([^;]*;", "", header)
    assert dropped != header
    assert any("otc_heights  (Release.heights: no OTC_API function)" in p for p in cm.check(ported, dropped)[0])
    failures, skipped = cm.self_test(ported, header)
    assert skipped == len(cm.NEEDS_PENDING) and not any("crashed" in f for f in failures), failures


def test_swift_fractional_registration_keeps_other_runner_filters():
    case = {"id": "predict-heights/fractional-instants@json", "runners": ["python", "ruby", "typescript"]}
    assert not driver.runner_skips(case, "swift", "swift")
    assert driver.runner_skips(case, "c", "c")
    assert driver.runner_skips(dict(case, id="unrelated"), "swift", "swift")


# --- the case-level runners filter (prediction spec 6.5: Python-only and not-C cases)

def test_runners_filter_is_linted(tmp_path):
    step = {"op": "station_count", "expect": {"count": 1}}
    assert lint(tmp_path, [{"id": "a", "runners": ["python"], "steps": [step]}]).returncode == 0
    for bad, msg in ((["pythn"], "unknown runner 'pythn'"), ([], "runners must be a non-empty list"),
                     ("python", "runners must be a non-empty list")):
        r = lint(tmp_path, [{"id": "a", "runners": bad, "steps": [step]}])
        assert r.returncode == 2 and msg in r.stdout + r.stderr, (bad, r.stdout[-400:], r.stderr[-400:])


@pytest.mark.parametrize("hello_runner,profile,runs", [("python", "python", True), ("ruby", "ruby", False),
                                                        ("python", "python-no-tz", True), ("c", "c", False),
                                                        ("null", "none", True)])
def test_runners_filter_skips_other_runners(tmp_path, hello_runner, profile, runs):
    cases = write_cases(tmp_path, [{"id": "a", "runners": ["python"], "steps": [{"op": "station_count",
                                                                                 "expect": {"count": 1}}]}])
    feats = driver.PROFILES[profile]
    hello = json.dumps({"hello": {"runner": hello_runner, "features": feats}})
    r = run_driver("--runner", write_fake_runner(tmp_path), "--cases", str(cases), "--profile", profile,
                   "--no-expected-failures", env={"FAKE_HELLO": hello})
    if runs:   # it runs, and fails on the fake runner's empty reply
        assert r.returncode == 1 and "1 failed" in r.stdout, r.stdout[-300:]
    else:
        assert r.returncode == 1 and "1 skipped" in r.stdout and "no case ran" in r.stdout, r.stdout[-300:]


def test_runners_filter_not_on_cross_cases(tmp_path):
    r = run_driver("--check-cases", "--cases", str(write_cases(tmp_path, [{"id": "a", "runners": ["python"],
               "roles": {"w": ["fs"], "r": ["fs"]}, "steps": [{"op": "station_count", "as": "w", "expect": {"count": 1}}]}])))
    assert r.returncode == 2 and "cannot have runners" in r.stdout, r.stdout[-400:]


# --- localtime implies localtime_module

def test_localtime_covers_localtime_module(tmp_path):
    to_local = {"op": "to_local", "args": {}, "expect": {"x": 1}}
    r = lint(tmp_path, [{"id": "p", "requires": REQ + ["localtime"], "steps": [OPEN, to_local]}])
    assert r.returncode == 0, r.stdout[-600:]
    eim = dict(to_local, expect_if_missing={"localtime": {"error": "local_time_unavailable"}})
    r = lint(tmp_path, [{"id": "p", "requires": REQ, "steps": [OPEN, eim]}])
    assert r.returncode == 0, r.stdout[-600:]
    # localtime_module alone does not cover localtime
    r = lint(tmp_path, [{"id": "p", "requires": REQ + ["localtime_module"], "steps": [OPEN, to_local]}])
    assert r.returncode == 2 and "uses 'localtime'" in r.stdout, r.stdout[-600:]


def test_every_profile_with_localtime_has_localtime_module():
    for name, feats in driver.PROFILES.items():
        assert "localtime" not in feats or "localtime_module" in feats, name


def test_a_runner_claiming_localtime_without_the_module_fails_the_handshake():
    p = driver.profile_problem("none", ["fs", "localtime"])
    assert p and "localtime without localtime_module" in p


# --- tz is the resolved zone (prediction spec 5.3)

def test_tz_is_the_resolved_zone_name():
    for o in ("HeightSeries", "ExtremeList", "CurrentSeries", "CurrentEventList"):
        m = [x for x in API["objects"][o]["members"] if x["name"] == "tz"][0]
        assert 'never the literal "station"' in m["note"] and "otc_station_timezone" in m["c"], o
