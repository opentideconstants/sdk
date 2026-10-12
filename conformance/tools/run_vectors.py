# /// script
# requires-python = ">=3.10"
# ///
"""Run the SHA-pinned Tier A vectors through the existing SDK runner protocol."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shlex
import sys
import tempfile
from pathlib import Path

CONF = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CONF))
import driver  # noqa: E402

BUNDLE = CONF / "vectors" / "1.0"
CHECKSUMS_SHA256 = "d0311757a6514e66f5a55bf057ef52d46b7825807ccbc12ab3cb1281c1f575b2"
TOLERANCES = {"height_m": 1e-5, "time_s": 1, "velocity_ms": 1e-5,
              "direction_deg": 0.01, "direction_min_speed_ms": 0.01}
METADATA = {"station_id", "timezone", "method", "set_id", "convention_id", "astro_table_id",
            "reference_station_id", "reference_bin", "datum", "datum_name", "datum_kind",
            "datum_uncertainty_m", "bin_number", "omitted_event_types", "tz", "tz_version", "release", "algorithm"}
OPS = {"heights_at": 7, "extremes": 30, "current_events": 18, "currents": 5}
TCD_ID = "otc-tcd-20251228-ma2mb2"
TCD_SHA256 = "ab8fa42c6dfce040924b3b035c1a87bef1cc4f10ed17449ae3ea16d0c76516a9"


class VectorError(ValueError):
    pass


def sha256(path):
    if path.is_symlink() or not path.is_file():
        raise VectorError(f"{path}: expected an immutable regular file")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_bundle(bundle):
    """Authenticate producer bytes before consuming any scientific expectation."""
    manifest = bundle / "SHA256SUMS"
    if sha256(manifest) != CHECKSUMS_SHA256:
        raise VectorError(f"{manifest}: SHA-256 mismatch")
    pins = {}
    for line in manifest.read_text().splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (vectors\.json|vectors-release\.json|provenance\.json)", line)
        if not match or match[2] in pins:
            raise VectorError("malformed or duplicate vector checksum")
        pins[match[2]] = match[1]
    if set(pins) != {"vectors.json", "vectors-release.json", "provenance.json"}:
        raise VectorError("incomplete vector checksums")
    for name, wanted in pins.items():
        if sha256(bundle / name) != wanted:
            raise VectorError(f"{bundle / name}: SHA-256 mismatch")
    document = json.loads((bundle / "vectors.json").read_text())
    release = json.loads((bundle / "vectors-release.json").read_text())
    provenance = json.loads((bundle / "provenance.json").read_text())
    rows = document.get("vectors")
    if (document.get("vectors_version") != 1 or document.get("format_version") != "1.0"
            or release.get("format_version") != "1.0" or document.get("complete") is not True
            or document.get("tolerances") != TOLERANCES or not isinstance(rows, list) or len(rows) != 60):
        raise VectorError("expected the complete format-1.0, 60-vector Tier A bundle")
    if document.get("release_sha256") != pins["vectors-release.json"]:
        raise VectorError("vector input release differs from its SHA-256 pin")
    if (provenance.get("artifacts") != {k: pins[k] for k in ("vectors.json", "vectors-release.json")}
            or not re.fullmatch(r"[0-9a-f]{40}", str(provenance.get("code_commit", "")))
            or provenance.get("source_sha256", {}).get("lib/harmonics_strict.rb") != document.get("strict_source_sha256")):
        raise VectorError("vector producer/source provenance differs from the pinned artifact")
    if document.get("astro_table_id") != TCD_ID or document.get("tcd_sha256") != TCD_SHA256:
        raise VectorError("vectors must use the exact own-TCD astro table")
    tables = release.get("astro_tables") or []
    if len(tables) != 1 or tables[0].get("astro_table_id") != TCD_ID or tables[0].get("tables_sha256") != TCD_SHA256:
        raise VectorError("vector release does not contain the own-TCD table")
    stations = {s["station_id"] for s in release["stations"]}
    if len(stations) != 14 or {r["args"]["station_id"] for r in rows} != stations:
        raise VectorError("vectors must cover all 14 input stations")
    if len({r["id"] for r in rows}) != 60 or {op: sum(r["op"] == op for r in rows) for op in OPS} != OPS:
        raise VectorError("missing or duplicate vector operation")
    checks = document.get("checks") or {}
    if (checks.get("problems") != [] or len(checks.get("hand_sums") or []) != 5
            or len(checks.get("bands") or []) != 66
            or any(r.get("pass") is not True for r in checks["hand_sums"] + checks["bands"])
            or any(r.get("bands") != [1, 2, 4] for r in checks["bands"])):
        raise VectorError("independent vector scientific checks are not complete")
    for row in rows:
        prediction = row["expect"]["prediction"]
        if (set(prediction) != METADATA | {"items"} or not prediction["items"]
                or prediction["station_id"] != row["args"]["station_id"]
                or prediction["release"] != release["release"]["datestamp"]
                or prediction["astro_table_id"] != TCD_ID or prediction["algorithm"] != "otc-predict-1"):
            raise VectorError(f"{row['id']}: missing items or exact prediction metadata")
    return document, release, pins


def number(value):
    try:
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    except OverflowError:
        return False


def compare_prediction(row, actual):
    """Metadata, event pairing and types are exact; only §6.1 quantities have tolerances."""
    expected = row["expect"]["prediction"]
    if not isinstance(actual, dict) or set(actual) != set(expected):
        return ["prediction keys differ from the complete expected metadata/items"]
    problems = driver.match({k: expected[k] for k in METADATA}, {k: actual[k] for k in METADATA}, 0, "prediction")
    items = actual["items"]
    if not isinstance(items, list) or len(items) != len(expected["items"]):
        return problems + [f"items: expected exactly {len(expected['items'])} ordered items"]
    events = row["op"] in {"extremes", "current_events"}
    for i, (want, got) in enumerate(zip(expected["items"], items)):
        where = f"items[{i}]"
        if not isinstance(got, dict) or set(got) != set(want):
            problems.append(f"{where}: item keys differ")
            continue
        for key, value in want.items():
            observed = got[key]
            if key == "time":
                problems += driver.match(value, observed, 0, f"result.prediction.items[{i}].time",
                                         event_time_tolerance_s=TOLERANCES["time_s"] if events else 0)
            elif key == "direction_deg":
                if value is None:
                    # §4.7/4.9: zero-speed directions and slack-event directions are null.
                    problems += driver.match(None, observed, 0, f"{where}.direction_deg")
                elif not number(observed) or not 0 <= observed < 360:
                    problems.append(f"{where}.direction_deg: expected a finite angle in [0,360)")
                elif (want.get("speed_ms", abs(want.get("velocity_ms", 0))) >= TOLERANCES["direction_min_speed_ms"]
                      and abs((observed - value + 180) % 360 - 180) > TOLERANCES["direction_deg"]):
                    problems.append(f"{where}.direction_deg: circular angle difference exceeds tolerance")
            elif key == "height_m" or key in {"velocity_major_ms", "velocity_minor_ms", "speed_ms", "velocity_ms"}:
                tolerance = TOLERANCES["height_m" if key == "height_m" else "velocity_ms"]
                if not number(observed) or abs(observed - value) > tolerance:
                    problems.append(f"{where}.{key}: numeric difference exceeds {tolerance}")
            else:
                problems += driver.match(value, observed, 0, f"{where}.{key}")
    return problems


def pending_runners(bundle):
    path = bundle / "expected-failures.json"
    if not path.is_file() or path.is_symlink():
        raise VectorError("missing regular-file vector expected-failures.json")
    entries = json.loads(path.read_text())["entries"]
    names = set()
    for entry in entries:
        if (set(entry) != {"runner", "reason"} or entry["runner"] not in driver.PENDING_FEATURES
                or entry["runner"] in names or not isinstance(entry["reason"], str) or not entry["reason"].strip()):
            raise VectorError("invalid or duplicate pending vector runner")
        names.add(entry["runner"])
    return names


def run_vectors(bundle, document, release, command, no_expected_failures, timeout):
    expected_failures = set() if no_expected_failures else pending_runners(bundle)
    results = []
    with tempfile.TemporaryDirectory(prefix="otc-vectors-") as directory:
        tmp = Path(directory)
        # SDK file readers require OTC_<datestamp>.json. Preserve the producer's
        # pinned artifact name and open an authenticated byte-for-byte copy.
        opened_release = tmp / f"OTC_{release['release']['datestamp']}.json"
        opened_release.write_bytes((bundle / "vectors-release.json").read_bytes())
        if sha256(opened_release) != document["release_sha256"]:
            raise VectorError("vector input changed before the canonical release copy was opened")
        opened_release.with_suffix(".sha256").write_text(f"{document['release_sha256']}  {opened_release.name}\n")
        runner = driver.Runner(shlex.split(command), driver.runner_env(driver.isolated_env(tmp)),
                               tmp / "runner.stderr", cwd=str(CONF.parent))
        try:
            hello = driver.parse_hello(runner.read(timeout))
            name = hello.get("runner", "unknown")
            pending = name in expected_failures
            runner.send({"op": "open", "args": {"file": str(opened_release), "mode": "eager"}})
            opened = runner.read(timeout)
            errors = driver.reply_problems(opened)
            if errors:
                raise VectorError(f"open protocol fault: {errors[0]}")
            open_errors = driver.evaluate({"loaded_from": "file", "datestamp": release["release"]["datestamp"]}, opened)
            for row in document["vectors"]:
                if "predict" not in hello["features"]:
                    problems = ["prediction port is pending: runner hello lacks predict"]
                else:
                    runner.send({"op": row["op"], "args": row["args"]})
                    reply = runner.read(timeout)
                    problems = driver.reply_problems(reply)
                    if problems:
                        raise VectorError(f"{row['id']}: protocol fault: {problems[0]}")
                    if not reply["ok"]:
                        if reply["error"]["code"].startswith("uncaught:"):
                            raise VectorError(f"{row['id']}: runner fault: {reply['error']['code']}")
                        problems = [f"unexpected SDK refusal {reply['error']['code']}"]
                    else:
                        result = reply["result"]
                        problems = compare_prediction(row, result.get("prediction")) if set(result) == {"prediction"} else ["result keys differ"]
                # A pending prediction port cannot hide a broken release reader.
                if open_errors:
                    problems = [f"open: {p}" for p in open_errors] + problems
                    status = "FAIL"
                else:
                    status = ("XFAIL" if problems else "XPASS") if pending else ("FAIL" if problems else "PASS")
                results.append({"id": row["id"], "status": status, "problems": problems})
        finally:
            status = runner.close()
        if status != 0:
            raise VectorError(f"runner failed to exit cleanly: {status}")
    counts = {status: sum(r["status"] == status for r in results) for status in ("PASS", "FAIL", "XFAIL", "XPASS")}
    return {"runner": name, "counts": counts, "vectors": results}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, default=BUNDLE)
    parser.add_argument("--check", action="store_true", help="authenticate the complete immutable input bundle")
    parser.add_argument("--runner", help="existing SDK runner command")
    parser.add_argument("--no-expected-failures", action="store_true", help="show pending ports as real RED")
    parser.add_argument("--timeout", type=float, default=60, help="bounded hello/reply timeout in seconds")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        if not math.isfinite(args.timeout) or args.timeout <= 0 or args.timeout > 600:
            raise VectorError("timeout must be finite and between 0 and 600 seconds")
        document, release, pins = load_bundle(args.bundle)
        if args.check:
            print("OK: 60 vectors, 14 stations; immutable input and provenance SHA-256 pins match")
            return 0
        if not args.runner:
            parser.error("--runner or --check is required")
        report = run_vectors(args.bundle, document, release, args.runner, args.no_expected_failures, args.timeout)
        report["pins"] = pins
        if args.report:
            args.report.write_text(json.dumps(report, indent=2) + "\n")
        print("60 vectors: " + ", ".join(f"{count} {status}" for status, count in report["counts"].items()))
        return 1 if report["counts"]["FAIL"] or report["counts"]["XPASS"] else 0
    except (VectorError, driver.RunnerError, OSError, ValueError, KeyError, TypeError, EOFError, TimeoutError) as e:
        print(f"vector consumer: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
