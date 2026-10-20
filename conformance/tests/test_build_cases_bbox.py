"""Shared bbox contract and fixture expectations, before language implementations."""
from __future__ import annotations

import json
import sys

from _util import CONF

sys.path.insert(0, str(CONF / "tools"))
import build_cases as bc  # noqa: E402
sys.path.insert(0, str(CONF))
import driver  # noqa: E402


ACTIVE = {"python", "ruby", "typescript", "swift", "typescript-browser", "python-no-tz", "ruby-no-tz"}


def bbox_cases():
    assert "bbox" in bc.GROUPS, "the bbox case family is missing"
    return bc.GROUPS["bbox"](bc.Rel("good", "20991231.2"), None)


def test_bbox_api_contract_and_required_capability():
    api = json.loads((CONF / "api.json").read_text())
    members = {m["name"]: m for m in api["objects"]["Release"]["members"]}
    assert "bbox" in members, "Release.bbox is missing from the public API"
    member = members["bbox"]
    assert set(member["languages"]) == {"python", "ruby", "typescript", "swift"}
    assert member["filters"] and member["forwarded_to_client"]
    assert member["returns"] == "Station[]" and member["swift_returns"] == "[Station]"
    assert [a["name"] for a in member["args"]] == ["south", "west", "north", "east", "limit"]
    assert all(a["required"] and not a["positional"] and a["type"] == "number" for a in member["args"][:4])
    assert set(driver.OPS["bbox"]) == {"south", "west", "north", "east", "limit", *driver.FILTERS}
    assert "station_bbox" in driver.FEATURES
    for profile in ACTIVE:
        assert "station_bbox" in driver.PROFILES[profile]
        assert "station_bbox" not in driver.PENDING_FEATURES.get(profile, [])
        missing = set(driver.PROFILES[profile]) - {"station_bbox"}
        assert "station_bbox" in driver.profile_problem(profile, missing)
    assert all("station_bbox" not in features for profile, features in driver.PROFILES.items() if profile.startswith("c"))


def test_bbox_expected_ids_and_public_receivers():
    cases = {c["id"]: c for c in bbox_cases()}
    expected = {
        "rectangle": ["OTC-T-0001", "OTC-T-0003", "OTC-T-0004"],
        "filtered-limit": ["OTC-T-0003"],
        "include-flagged": ["OTC-T-0001", "OTC-T-0002", "OTC-T-0003", "OTC-T-0004"],
        "antimeridian": ["OTC-T-0007", "OTC-T-0008"],
        "empty": [],
    }
    for name, ids in expected.items():
        case = cases[f"bbox/{name}"]
        queries = [st for st in case["steps"] if st.get("op") == "bbox"]
        assert {st.get("on", "client") for st in queries} == {"client", "held"}
        assert all(st["expect"] == {"station_ids": ids} for st in queries)
        assert case["requires"] == ["station_bbox"]
        assert set(case["runners"]) == ACTIVE - {"typescript-browser"}
    invalid = [st for st in cases["bbox/invalid-arguments"]["steps"] if st.get("op") == "bbox"]
    assert invalid and all(st["expect"] == {"error": "invalid_argument"} for st in invalid)
    assert driver.check_cases(driver.expand(list(cases.values()))) == []


def test_bbox_browser_cases_are_applicable_over_http_in_both_modes():
    assert "bbox-browser" in bc.GROUPS, "browser bbox cases are missing"
    cases = bc.GROUPS["bbox-browser"](bc.Rel("good", "20991231.2"), None)
    assert len(cases) == 2 * len(bbox_cases())
    assert {c["steps"][0]["args"]["mode"] for c in cases} == {"eager", "stream"}
    for c in driver.expand(cases):
        assert not driver.runner_skips(c, "typescript-browser", "typescript-browser")
        assert set(c["requires"]) <= set(driver.PROFILES["typescript-browser"])
        assert "fs" not in c["requires"] and "matrix" not in c
        assert c["steps"][0]["args"]["base_url"] == "${server}/good/"
        assert all("cache_dir" not in st.get("args", {}) and "file" not in st.get("args", {}) for st in c["steps"])
        assert any(st.get("op") == "bbox" for st in c["steps"])
    assert driver.check_cases(cases) == []


def test_bbox_generation_is_reproducible_and_preserves_existing_cases(tmp_path):
    assert {"bbox", "bbox-browser"} <= bc.GROUPS.keys(), "bbox generation is missing"
    cases, cross = tmp_path / "cases", tmp_path / "cross"
    bc.build(cases, cross)
    for source in (CONF / "cases").glob("*.json"):
        assert (cases / source.name).read_bytes() == source.read_bytes(), source.name
    assert (cross / "cross.json").read_bytes() == (CONF / "cross" / "cross.json").read_bytes()
    assert {p.name for p in cases.glob("bbox*.json")} == {"bbox.json", "bbox-browser.json"}
