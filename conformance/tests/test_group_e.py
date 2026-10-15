"""Group E: suite strength (review slot 3): profiles, discriminating cases, proxy honesty, a stronger RED proof."""
from __future__ import annotations

import http.client
import json
import sys

import pytest

from _util import CONF, NULL_RUNNER, run_driver, write_cases, write_fake_runner

sys.path.insert(0, str(CONF))
import driver  # noqa: E402
from server import FixtureServer, RecordingProxy  # noqa: E402

ALMOST_RUNNER = CONF / "runners" / "almost" / "runner.py"
OK_STEP = {"op": "station_count", "expect": {"count": 1}}


def cases_by_id():
    return {c["id"]: c for c in driver.load_cases(driver.CASES_DIR)}


def runner_steps(c):
    return [s for s in c["steps"] if "op" in s]


# --- language profiles (F2)

@pytest.mark.parametrize("name", ["python", "ruby", "typescript"])
def test_profile_runner_must_claim_every_feature(tmp_path, name):
    cases = write_cases(tmp_path, [{"id": "a", "steps": [OK_STEP]}])
    hello = json.dumps({"hello": {"runner": name, "features": ["fs", "fetch", "json", "eager"]}})
    r = run_driver("--runner", write_fake_runner(tmp_path), "--cases", str(cases), env={"FAKE_HELLO": hello})
    assert r.returncode == 2 and "stream" in r.stderr, (r.returncode, r.stderr[-300:])


def test_explicit_profile_applies_to_any_runner(tmp_path):
    cases = write_cases(tmp_path, [{"id": "a", "steps": [OK_STEP]}])
    r = run_driver("--runner", f"{sys.executable} {NULL_RUNNER} --features fs,json", "--cases", str(cases), "--profile", "python")
    assert r.returncode == 2 and "Traceback" not in r.stderr, r.stderr[-300:]
    # the failure names the profile and the features the runner lacks (not just any exit 2)
    assert "profile python" in r.stderr and all(f in r.stderr for f in ("eager", "fetch", "stream")), r.stderr[-300:]


# --- update/auto discriminates (F3)

@pytest.mark.parametrize("cid,expect_null", [("update/auto", True), ("update/auto-off", False)])
def test_update_auto_first_query_discriminates(cid, expect_null):
    c = cases_by_id()[cid]
    i = next(i for i, s in enumerate(c["steps"]) if s.get("driver") == "sleep")
    first = next(s for s in c["steps"][i + 1:] if "op" in s)
    assert first["op"] == "station" and first["args"] == {"station_id": "OTC-T-0021"}, first
    assert (first["expect"]["station"] is None) == expect_null


# --- datestamp counter order (F4)

def test_counter_order_fixture_and_cases():
    assert (CONF / "fixtures" / "order" / "OTC_20991231.10.json").is_file()
    cs = cases_by_id()
    want = ["20991231.10", "20991231.2"]
    assert any(s.get("op") == "cached_releases" and s.get("expect", {}).get("datestamps") == want
               for c in cs.values() for s in c["steps"])
    assert any(s.get("op") == "prune" and s.get("expect", {}).get("removed") == ["20991231.2"]
               for c in cs.values() for s in c["steps"])
    assert any(c["id"].startswith("net/offline-latest") and any(
        s.get("op") == "open" and s.get("args", {}).get("offline") and s["expect"].get("datestamp") == "20991231.10"
        for s in c["steps"]) for c in cs.values())


# --- release.files from .verified is checked by value (F5)

@pytest.mark.parametrize("cid", ["net/second-open-uses-cache", "cache/files-from-verified", "net/500-use-cache"])
def test_cache_rows_check_file_values(cid):
    st = [s for s in runner_steps(cases_by_id()[cid]) if s["op"] == "release_files"]
    assert st, f"{cid} has no release_files step"
    exp = st[-1]["expect"]
    # the rows are the .verified rows: the pointer entry's values, for only the files the download stored (CR3
    # DR100): the .json in the default eager mode, the .jsonl and the .meta.json in C's stream mode
    index = json.loads((CONF / "fixtures" / "good" / "OTC_index.json").read_text(encoding="utf-8"))
    entry = next(e for e in index["releases"] if e["datestamp"] == "20991231.2")
    rows = {f["name"]: {"name": f["name"], "url": "${server}/good/" + f["url"], "size": f["size"], "sha256": f["sha256"]}
            for f in entry["files"]}
    eager = [rows["OTC_20991231.2.json"]]
    stream = [rows["OTC_20991231.2.jsonl"], rows["OTC_20991231.2.meta.json"]]
    assert exp["files"] == {"$any_of": [eager, stream]}, exp
    for ok in (eager, stream):
        assert driver.evaluate(exp, {"ok": True, "result": {"files": ok}}) == []
    # the pointer's whole list (the old writer) and a wrong value both fail
    assert driver.evaluate(exp, {"ok": True, "result": {"files": sorted(rows.values(), key=lambda r: r["name"])}})
    assert driver.evaluate(exp, {"ok": True, "result": {"files": [dict(eager[0], sha256="0" * 64)]}})


# --- a pinned download needs no pointer or index (F6)

def test_pinned_download_files_come_from_sha256_only():
    c = cases_by_id()["net/pinned-download"]
    exp = [s for s in runner_steps(c) if s["op"] == "release_files"][0]["expect"]
    sums = {}
    for line in (CONF / "fixtures" / "good" / "OTC_20991231.sha256").read_text().splitlines():
        digest, name = line.split(None, 1)
        sums[name.strip()] = digest

    def rows(names, url=None, real=True):
        return [{"name": n, "url": url and url + n, "size": (CONF / "fixtures" / "good" / n).stat().st_size if real else None,
                 "sha256": sums[n]} for n in names]

    # the rows of the files the open stored (CR3 DR100), with their real size; url null or the true value
    for names in (["OTC_20991231.json"], ["OTC_20991231.jsonl", "OTC_20991231.meta.json"]):
        assert driver.evaluate(exp, {"ok": True, "result": {"files": rows(names)}}) == []
        assert driver.evaluate(exp, {"ok": True, "result": {"files": rows(names, "${server}/good/")}}) == []
        bad = rows(names)
        bad[0]["sha256"] = "0" * 64
        assert driver.evaluate(exp, {"ok": True, "result": {"files": bad}})
        assert driver.evaluate(exp, {"ok": True, "result": {"files": rows(names, real=False)}})
    # every .sha256 row, sizes null (the old writer): fails
    assert driver.evaluate(exp, {"ok": True, "result": {"files": rows(sorted(sums), real=False)}})


# --- proxy cases do not depend on loopback handling (F10)

def test_proxy_env_cases_use_the_alias_host():
    cs = cases_by_id()
    for cid in ["net/proxy-env", "net/proxy-env-no-proxy-other-host"]:
        opens = [s for s in runner_steps(cs[cid]) if s["op"] == "open"]
        assert opens and opens[0]["args"]["base_url"].startswith("${server_alias}/"), cid


def test_proxy_relays_the_alias_host_to_the_fixture_server():
    srv, proxy = FixtureServer().start(), RecordingProxy().start()
    try:
        proxy.aliases[driver.SERVER_ALIAS] = srv.host
        conn = http.client.HTTPConnection(proxy.host, proxy.port, timeout=10)
        conn.request("GET", f"http://{driver.SERVER_ALIAS}:{srv.port}/good/OTC_latest.json")
        r = conn.getresponse()
        r.read()
        assert r.status == 200
        assert [e["source"] for e in srv.log.entries()] == ["server"]
    finally:
        srv.shutdown()
        proxy.shutdown()


# --- README suite choices (F7, F8, F12)

def test_readme_records_suite_choices():
    readme = (CONF / "README.md").read_text(encoding="utf-8").lower()
    for phrase in ["subordinates_of", "offline_unavailable", "3 attempts", "server_alias", "release.files of a pinned download"]:
        assert phrase in readme, phrase


# --- a stronger RED proof (F13): right on open, wrong after

def test_almost_runner_fails_on_later_steps(tmp_path):
    report = tmp_path / "r.json"
    # Only the matrix variants (an id with "@"): their step 0 is the driver's open. A runner-specific case such as
    # stations/fallback-python opens later, after its own setup steps.
    r = run_driver("--runner", f"{sys.executable} {ALMOST_RUNNER}", "--only", "^stations/[^@]*@", "--all-steps", "--report", str(report),
                   timeout=300)
    assert r.returncode == 1, r.stdout[-500:]
    check_almost_report(json.loads(report.read_text()))


def check_almost_report(doc):
    """Every case is a matrix variant (its step 0 is the driver's open) and failed after the open step: not at the open,
    and at some later step. No case passed or was skipped (a SKIP has no failures list)."""
    assert doc["counts"]["PASS"] == 0 and doc["counts"]["SKIP"] == 0 and doc["counts"]["FAIL"] > 0, doc["counts"]
    for c in doc["cases"]:
        assert c["status"] == "FAIL", (c["id"], c["status"])
        assert "@" in c["id"], (c["id"], "not a matrix variant: its step 0 need not be the open")
        steps = [f["step"] for f in c["failures"]]
        assert 0 not in steps, (c["id"], c["failures"][:1])
        assert any(s and s > 0 for s in steps), c["id"]


GOOD_FAIL = {"id": "x@json", "status": "FAIL", "failures": [{"step": 1}]}


@pytest.mark.parametrize("doc", [
    # the counts say a case was skipped
    {"counts": {"PASS": 0, "FAIL": 1, "SKIP": 1}, "cases": [GOOD_FAIL, {"id": "y@json", "status": "SKIP", "missing_features": ["fs"]}]},
    # consistent counts, but a case's status is SKIP (the per-case check, not the counts, must catch it)
    {"counts": {"PASS": 0, "FAIL": 2, "SKIP": 0}, "cases": [GOOD_FAIL, {"id": "y@json", "status": "SKIP", "failures": [{"step": 1}]}]},
    # a case that failed only at the open step
    {"counts": {"PASS": 0, "FAIL": 2, "SKIP": 0}, "cases": [GOOD_FAIL, {"id": "y@json", "status": "FAIL", "failures": [{"step": 0}]}]},
    # a case that failed at the open and later
    {"counts": {"PASS": 0, "FAIL": 2, "SKIP": 0},
     "cases": [GOOD_FAIL, {"id": "y@json", "status": "FAIL", "failures": [{"step": 0}, {"step": 2}]}]},
    # a case that is not a matrix variant
    {"counts": {"PASS": 0, "FAIL": 2, "SKIP": 0}, "cases": [GOOD_FAIL, {"id": "y", "status": "FAIL", "failures": [{"step": 1}]}]},
])
def test_almost_report_check_rejects(doc):
    with pytest.raises(AssertionError):
        check_almost_report(doc)


def test_almost_report_check_accepts_a_good_report():
    check_almost_report({"counts": {"PASS": 0, "FAIL": 1, "SKIP": 0}, "cases": [GOOD_FAIL]})
