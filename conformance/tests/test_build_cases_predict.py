"""K2b-pin: real authored prediction calls become bound runnable cases."""
from __future__ import annotations

import json
import sys
import copy
from datetime import datetime, timedelta, timezone

import pytest

from _util import CONF

sys.path.insert(0, str(CONF / "tools"))
import build_cases as bc  # noqa: E402
sys.path.insert(0, str(CONF))
import driver  # noqa: E402


def test_missing_independent_expectations_stop_the_real_case_builder(tmp_path, monkeypatch):
    missing = tmp_path / "missing-predict_expected.json"
    monkeypatch.setattr(bc, "PREDICT_EXPECTED", missing, raising=False)
    with pytest.raises(SystemExit, match="predict_expected"):
        bc.build(tmp_path / "cases", tmp_path / "cross")


def test_authored_calls_require_all_119_cases_and_253_steps():
    authored = json.loads((CONF / "tools" / "predict_calls.json").read_text())
    assert len(authored["cases"]) == 119
    assert sum(len(c["steps"]) for c in authored["cases"]) == 253


def named_case(name="single-constituent"):
    return next(c for c in bc.prediction_cases() if c["id"] == f"predict-extremes/{name}")


@pytest.mark.parametrize("name", ["single-constituent", "negative-amplitude"])
def test_real_named_event_comparator_allows_one_second_only(name):
    c = named_case(name)
    expect = c["steps"][0]["expect"]
    reply = {"ok": True, "result": copy.deepcopy(expect)}
    first = reply["result"]["prediction"]["items"][0]
    instant = datetime.strptime(first["time"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    first["time"] = (instant + timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert driver.evaluate(expect, reply)  # Ordinary case comparison stays exact.
    assert driver.evaluate(expect, reply, case=c) == []
    first["time"] = (instant + timedelta(seconds=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert driver.evaluate(expect, reply, case=c)


def test_real_prediction_case_lint_blocks_unproved_science():
    c = named_case()
    c["scientific_gate_ready"] = False
    assert any("scientific gate" in p for p in driver.check_cases(driver.expand([c])))


@pytest.mark.parametrize("mutation", ["empty", "false", "missing_band", "missing_identity"])
def test_real_pinned_deferred_coverage_cannot_be_bypassed(tmp_path, monkeypatch, mutation):
    pin = json.loads(bc.PREDICT_EXPECTED.read_bytes())
    if mutation == "empty":
        pin["band_coverage"]["proved_deferred_steps"] = []
    elif mutation == "false":
        pin["scientific_gate_ready"] = False
    elif mutation == "missing_band":
        pin["band_coverage"]["proved_deferred_steps"][0]["bands"] = [1, 2, 4]
    else:
        pin["band_coverage"]["proved_deferred_steps"].pop()
    path = tmp_path / "predict_expected.json"
    path.write_text(json.dumps(pin))
    monkeypatch.setattr(bc, "PREDICT_EXPECTED", path)
    with pytest.raises(SystemExit, match="scientific gate"):
        bc.build(tmp_path / "cases", tmp_path / "cross")


def test_real_lowered_manifest_preserves_every_authored_control():
    authored = json.loads(bc.PREDICT_CALLS.read_bytes())["cases"]
    lowered = {c["id"]: c for c in bc.prediction_cases()}
    control_keys = {"strict", "outcome", "compare", "local", "same_items_as_step", "swap_of"}
    for c in authored:
        actual = lowered[c["id"]]
        assert actual["matrix"] == {"root": c["root"], "release": c["release"],
                                    **({"open_args": c["open_args"]} if c.get("open_args") else {})}
        for key in ("runners", "band_exception", "note"):
            assert actual.get(key) == c.get(key)
        for i, step in enumerate(c["steps"]):
            ready = actual["steps"][i]
            assert actual["prediction_provenance"]["steps"][i]["authored_controls"] == {
                k: v for k, v in step.items() if k in control_keys}
            for key in ("op", "driver", "args", "env", "matrix_open"):
                assert ready.get(key) == step.get(key)
            if "expect_if_missing" in step:
                assert list(ready["expect_if_missing"].items()) == [tuple(x) for x in step["expect_if_missing"]]
            expectation = copy.deepcopy(ready.get("expect"))
            if expectation and "prediction" in expectation and "items" not in step["expect"]["prediction"]:
                expectation["prediction"].pop("items", None)
            assert expectation == step.get("expect")
    assert len(lowered) == 119
    assert sum(len(c["steps"]) for c in lowered.values()) == 253


@pytest.mark.parametrize("mutation", ["count", "order", "type", "metadata", "height", "fractional_time", "offset_time"])
def test_named_comparator_rejects_every_non_time_relaxation(mutation):
    c = named_case()
    expect = c["steps"][0]["expect"]
    reply = {"ok": True, "result": copy.deepcopy(expect)}
    prediction = reply["result"]["prediction"]
    items = prediction["items"]
    if mutation == "count":
        items.pop()
    elif mutation == "order":
        items[0], items[1] = items[1], items[0]
    elif mutation == "type":
        items[0]["type"] = "low"
    elif mutation == "metadata":
        prediction["release"] = "20991231.6"
    elif mutation == "height":
        items[0]["height_m"] += 1e-6
    elif mutation == "fractional_time":
        items[0]["time"] = items[0]["time"].replace("Z", ".1Z")
    else:
        items[0]["time"] = items[0]["time"].replace("Z", "+00:00")
    assert driver.evaluate(expect, reply, case=c)


@pytest.mark.parametrize("mutation", ["id", "root", "window", "tolerance", "band", "amplitude", "events"])
def test_named_exception_cannot_spread_to_other_subjects(mutation):
    c = named_case()
    if mutation == "id":
        c["id"] = "predict-extremes/basic"
    elif mutation == "root":
        c["matrix"]["root"] = "good"
    elif mutation == "window":
        c["steps"][0]["args"]["start"] = "2010-03-02T00:00:00Z"
    elif mutation == "tolerance":
        c["band_exception"]["event_time_tolerance_s"] = 2
    elif mutation == "band":
        c["band_exception"]["band"] = 4
    elif mutation == "amplitude":
        c["band_exception"]["amplitude_m"] = -1.0
    else:
        c["steps"][0]["expect"]["prediction"]["items"].pop()
    assert driver.check_cases(driver.expand([c]))


def test_units_cases_derive_only_selected_values_from_pinned_si():
    originals = {c["id"]: c for c in bc.prediction_cases()}
    cases = bc.units_cases(list(originals.values()))
    assert {c["id"].split("/", 1)[0] for c in cases} == {
        "units-feet", "units-knots", "units-defaults"}
    operations = set()
    fields = {"height": "height_m", "velocity_major": "velocity_major_ms",
              "velocity_minor": "velocity_minor_ms", "speed": "speed_ms", "velocity": "velocity_ms"}
    for case in cases:
        source = originals[case["units_provenance"]["source_case"]]
        assert case["prediction_provenance"] == source["prediction_provenance"]
        assert case["matrix"] == source["matrix"]
        assert "prediction_units" in case["requires"]
        assert "c" not in case["runners"]
        for step, original in zip(case["steps"], source["steps"], strict=True):
            if "prediction" not in step.get("expect", {}):
                assert step == original
                continue
            if step["op"] != "to_local":
                operations.add(step["op"])
                assert step["args"]["units"] == step["expect"]["prediction"]["units"]
            actual = copy.deepcopy(step["expect"]["prediction"])
            units = actual.pop("units")
            factor = {"meters": 1.0, "feet": 0.3048, "m/s": 1.0, "knots": 1852.0 / 3600.0}[units]
            for item in actual["items"]:
                assert item.pop("units") == units
                for selected, si in fields.items():
                    if si in item:
                        assert item.pop(selected) == item[si] / factor
            assert actual == original["expect"]["prediction"]
    assert operations == {"heights", "heights_at", "extremes", "currents", "current_events"}
    assert driver.check_cases(driver.expand(cases)) == []


def test_units_are_required_in_active_profiles_and_prediction_requests():
    for profile in ("python", "ruby", "typescript", "swift", "typescript-browser", "python-no-tz", "ruby-no-tz"):
        assert "prediction_units" in driver.PROFILES[profile]
        without = set(driver.PROFILES[profile]) - {"prediction_units"}
        assert "prediction_units" in driver.profile_problem(profile, without)
    for profile in ("c", "c-fetch", "c-no-localtime", "c-no-predict"):
        assert "prediction_units" not in driver.PROFILES[profile]
    for op in ("heights", "heights_at", "extremes", "currents", "current_events"):
        assert "units" in driver.OPS[op]
        assert "prediction_units" in driver.step_needs({"op": op, "args": {"units": "feet"}})
        assert "prediction_units" not in driver.step_needs({"op": op})


def test_browser_units_cases_execute_the_same_assertions_without_filesystem():
    originals = bc.units_cases(bc.prediction_cases())
    unchanged = copy.deepcopy(originals)
    cases = bc.units_browser_cases(originals)
    assert originals == unchanged
    assert len(cases) == len(originals) == 12
    assert {c["id"].split("/", 1)[0] for c in cases} == {
        "units-browser-feet", "units-browser-knots", "units-browser-defaults"}
    for case, source in zip(cases, originals, strict=True):
        matrix = source["matrix"]
        assert case["id"] == source["id"].replace("units-", "units-browser-", 1)
        assert "matrix" not in case
        assert case["runners"] == ["typescript-browser"]
        assert set(case["requires"]) <= set(driver.PROFILES["typescript-browser"])
        assert {"fetch", "eager", "prediction_units"} <= set(case["requires"])
        assert case["steps"][0] == {
            "op": "open",
            "args": {"release": matrix["release"], "base_url": f"${{server}}/{matrix['root']}/",
                     "mode": "eager", **matrix.get("open_args", {})},
            "expect": {"datestamp": matrix["release"]}}
        assert case["steps"][1:] == source["steps"]
        assert case["units_provenance"] == source["units_provenance"]
        provenance = copy.deepcopy(case["prediction_provenance"])
        opening = provenance["steps"].pop(0)
        assert opening == {"authored_step": 0, "source": "authored_interface", "authored_controls": {}}
        for row in provenance["steps"]:
            row["authored_step"] -= 1
        assert provenance == source["prediction_provenance"]
        assert case["scientific_gate_ready"] is True
    assert driver.expand(cases) == cases
    assert driver.check_cases(cases) == []


def test_units_manifest_preserves_si_and_excludes_c():
    api = json.loads((CONF / "api.json").read_text())
    for operation in api["objects"]["Release"]["members"]:
        if operation["name"] not in {"heights", "heights_at", "extremes", "currents", "current_events"}:
            continue
        units = next(a for a in operation["args"] if a["name"] == "units")
        assert units["default"] == ("m/s" if operation["name"] in {"currents", "current_events"} else "meters")
        assert set(units["languages"]) == {"python", "ruby", "typescript", "swift"}
    pairs = {"HeightPoint": {"height": "height_m"}, "Extreme": {"height": "height_m"},
             "CurrentPoint": {"velocity_major": "velocity_major_ms", "velocity_minor": "velocity_minor_ms", "speed": "speed_ms"},
             "CurrentEvent": {"velocity": "velocity_ms"}}
    for name in (*pairs, "HeightSeries", "ExtremeList", "CurrentSeries", "CurrentEventList"):
        members = {m["name"]: m for m in api["objects"][name]["members"]}
        for selected in ("units", *pairs.get(name, {})):
            assert set(members[selected]["languages"]) == {"python", "ruby", "typescript", "swift"}
        assert set(pairs.get(name, {}).values()) <= members.keys()
