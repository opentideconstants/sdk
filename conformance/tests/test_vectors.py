"""Tier A: the actual immutable native vector bundle and real runner consumer."""
from __future__ import annotations

import json
import copy
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest

from _util import CONF, NULL_RUNNER

CONSUMER = CONF / "tools" / "run_vectors.py"
BUNDLE = CONF / "vectors" / "1.0"
sys.path.insert(0, str(CONF / "tools"))
import run_vectors as vectors  # noqa: E402


def native_row(op):
    document, _, _ = vectors.load_bundle(BUNDLE)
    return next(r for r in document["vectors"] if r["op"] == op)


def consume(*args):
    return subprocess.run([sys.executable, str(CONSUMER), *args], capture_output=True, text=True, timeout=60)


def test_real_native_bundle_is_nonempty_complete_and_sha_bound():
    r = consume("--check")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "60 vectors" in r.stdout and "14 stations" in r.stdout


def test_one_byte_edit_is_rejected_before_any_runner(tmp_path):
    bundle = tmp_path / "bundle"
    shutil.copytree(BUNDLE, bundle)
    with (bundle / "vectors.json").open("ab") as f:
        f.write(b" ")
    r = consume("--check", "--bundle", str(bundle))
    assert r.returncode == 2 and "SHA-256 mismatch" in r.stderr, r.stdout + r.stderr


def test_real_null_runner_fails_every_vector(tmp_path):
    report = tmp_path / "null.json"
    r = consume("--runner", f"{sys.executable} {NULL_RUNNER}", "--report", str(report))
    assert r.returncode == 1, r.stdout + r.stderr
    doc = json.loads(report.read_text())
    assert doc["counts"] == {"PASS": 0, "FAIL": 60, "XFAIL": 0, "XPASS": 0}


def test_real_sdk_reader_loads_the_exact_vector_release_under_its_canonical_filename(tmp_path):
    report = tmp_path / "python.json"
    runner = CONF / "runners" / "python" / "runner.py"
    r = consume("--runner", f"{sys.executable} {runner}", "--report", str(report))
    doc = json.loads(report.read_text())
    assert all(not p.startswith("open:") for row in doc["vectors"] for p in row["problems"]), r.stdout + r.stderr


def test_all_real_native_rows_compare_without_changed_expectations():
    document, _, _ = vectors.load_bundle(BUNDLE)
    for row in document["vectors"]:
        assert vectors.compare_prediction(row, row["expect"]["prediction"]) == []


@pytest.mark.parametrize("mutation", ["height", "count", "keys", "metadata", "boolean", "nan", "huge_integer"])
def test_real_height_vectors_reject_numeric_and_contract_mutants(mutation):
    row = native_row("heights_at")
    actual = copy.deepcopy(row["expect"]["prediction"])
    if mutation == "height":
        actual["items"][0]["height_m"] += 2e-5
    elif mutation == "count":
        actual["items"].pop()
    elif mutation == "keys":
        actual["items"][0].pop("local_time")
    elif mutation == "metadata":
        actual["algorithm"] = "other"
    elif mutation == "boolean":
        actual["items"][0]["height_m"] = True
    elif mutation == "nan":
        actual["items"][0]["height_m"] = float("nan")
    else:
        actual["items"][0]["height_m"] = 10 ** 400
    assert vectors.compare_prediction(row, actual)


@pytest.mark.parametrize("op", ["extremes", "current_events", "heights_at", "currents"])
def test_real_timestamps_allow_one_second_only_for_events(op):
    row = native_row(op)
    actual = copy.deepcopy(row["expect"]["prediction"])
    item = actual["items"][0]
    instant = datetime.strptime(item["time"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    item["time"] = (instant + timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert bool(vectors.compare_prediction(row, actual)) == (op not in {"extremes", "current_events"})
    item["time"] = (instant + timedelta(seconds=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert vectors.compare_prediction(row, actual)


@pytest.mark.parametrize("field", ["velocity_major_ms", "velocity_minor_ms", "speed_ms", "direction_deg"])
def test_real_current_components_and_direction_keep_tier_a_tolerances(field):
    row = native_row("currents")
    actual = copy.deepcopy(row["expect"]["prediction"])
    actual["items"][0][field] += 2e-5 if field != "direction_deg" else 0.02
    assert vectors.compare_prediction(row, actual)


@pytest.mark.parametrize("mutation", ["order", "type", "fractional", "offset"])
def test_real_event_pairing_and_utc_shape_are_exact(mutation):
    row = native_row("extremes")
    actual = copy.deepcopy(row["expect"]["prediction"])
    items = actual["items"]
    if mutation == "order":
        items[0], items[1] = items[1], items[0]
    elif mutation == "type":
        items[0]["type"] = "other"
    else:
        items[0]["time"] = items[0]["time"].replace("Z", ".1Z" if mutation == "fractional" else "+00:00")
    assert vectors.compare_prediction(row, actual)


@pytest.mark.parametrize("features,mode", [(["eager", "stream"], "eager"), (["stream"], "stream")])
def test_native_vector_input_projection_is_authenticated_and_lossless(tmp_path, features, mode):
    document, release, _ = vectors.load_bundle(BUNDLE)
    assert callable(getattr(vectors, "materialize_release", None)), "missing native stream input projection"
    path, opened_mode = vectors.materialize_release(BUNDLE, document, release, tmp_path, features)
    original = tmp_path / f"OTC_{release['release']['datestamp']}.json"
    assert opened_mode == mode
    assert original.read_bytes() == (BUNDLE / "vectors-release.json").read_bytes()
    assert vectors.sha256(original) == document["release_sha256"]
    if mode == "eager":
        assert path == original
    else:
        assert path == original.with_suffix(".jsonl")
        metadata = json.loads(original.with_suffix(".meta.json").read_text())
        reconstructed = dict(metadata, stations=[json.loads(line) for line in path.read_text().splitlines()])
        assert json.dumps(reconstructed, sort_keys=True) == json.dumps(release, sort_keys=True)
    for line in original.with_suffix(".sha256").read_text().splitlines():
        digest, name = line.split("  ")
        assert vectors.sha256(tmp_path / name) == digest
    expected_names = {original.name} if mode == "eager" else {original.name, path.name, original.with_suffix(".meta.json").name}
    assert {line.split("  ")[1] for line in original.with_suffix(".sha256").read_text().splitlines()} == expected_names


def test_vector_input_copy_refuses_a_source_changed_after_bundle_authentication(tmp_path):
    document, release, _ = vectors.load_bundle(BUNDLE)
    bundle = tmp_path / "bundle"
    shutil.copytree(BUNDLE, bundle)
    with (bundle / "vectors-release.json").open("ab") as file:
        file.write(b" ")
    destination = tmp_path / "opened"
    destination.mkdir()
    assert callable(getattr(vectors, "materialize_release", None)), "missing native stream input projection"
    with pytest.raises(vectors.VectorError, match="vector input changed"):
        vectors.materialize_release(bundle, document, release, destination, ["stream"])
