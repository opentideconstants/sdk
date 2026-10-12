"""Real-source NOAA historical baseline and reusable native input helpers."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import inspect
import json
from pathlib import Path
import sys
import unittest

import opentideconstants as otc


START = datetime(2026, 10, 11, tzinfo=timezone.utc)
STOP = START + timedelta(days=1)


def event_rows(result):
    return [{"time": item.time.isoformat(), "type": str(item.type), "height_m": item.height_m}
            for item in result.items]


def error_of(call):
    try:
        value = call()
    except Exception as exc:
        return {"error": type(exc).__name__, "message": str(exc)}
    return {"error": None, "result_type": type(value).__name__}


def load_native_inputs(path: Path):
    return json.loads(path.read_bytes())


def native_baseline(args) -> int:
    strict_constructor = getattr(otc, "OpenTideConstants")
    source = load_native_inputs(args.source_inputs)
    shell = load_native_inputs(args.shell)
    target_ids = source["legacy_shell"]["target_station_ids"]
    shell_targets = {station["station_id"]: station for station in shell["stations"] if station["station_id"] in target_ids}
    result = {"sdk": {"file": otc.__file__, "version": otc.__version__, "python": sys.version},
              "source_manifest_sha256": source["manifest_sha256"], "shell_sha256": hashlib.sha256(args.shell.read_bytes()).hexdigest(),
              "window": {"start": START.isoformat(), "stop": STOP.isoformat()},
              "inventory_native": [], "legacy_policy_native": [], "numeric_cells": [], "unchanged_controls": []}
    print(json.dumps({"stage": "actual-R3-native-open"}), flush=True)
    with otc.OpenTideConstants(file=args.release, cache_dir=args.out.parent / "cache-r3") as actual:
        controls = {}
        for station in shell["stations"]:
            if station["station_id"] in target_ids:
                continue
            noaa = [set_["source_record_id"] for set_ in station.get("constant_sets", []) if set_["source"] == "noaa"]
            if any(identifier in source["control_noaa_ids"] for identifier in noaa):
                sid = station["station_id"]
                controls[sid] = event_rows(actual.extremes(sid, start=START, stop=STOP, datum="chart"))
        for finding in source["findings"]:
            result["inventory_native"].append({"legacy_id": finding["legacy_id"],
                "metadata_lookup": actual.station(finding["legacy_id"]) is not None,
                "default_prediction": error_of(lambda f=finding: actual.extremes(f["legacy_id"], start=START, stop=STOP, datum="chart"))})
    print(json.dumps({"stage": "legacy-source-shell-native-open"}), flush=True)
    args.out.with_name("native-inventory-RED.json").write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    with otc.OpenTideConstants(file=args.shell, cache_dir=args.out.parent / "cache-legacy") as legacy:
        eligible = {station.station_id for station in legacy.iter_stations(kind="tide")}
        for sid, old_events in controls.items():
            new_events = event_rows(legacy.extremes(sid, start=START, stop=STOP, datum="chart"))
            if old_events != new_events:
                raise AssertionError(f"unchanged actual control differed: {sid}")
            result["unchanged_controls"].append({"station_id": sid, "events": old_events, "exactly_unchanged": True})
        for sid, row in zip(target_ids, source["source_rows"]):
            offsets = shell_targets[sid]["subordinate_offsets"]
            reference = event_rows(legacy.extremes(offsets["reference_station_id"], start=START-timedelta(days=1),
                                                  stop=STOP+timedelta(days=1), datum="chart"))
            native = event_rows(legacy.extremes(sid, start=START, stop=STOP, datum="chart"))
            expected = []
            for event in reference:
                high = event["type"] == "high"
                label = "high" if high else "low"
                time = datetime.fromisoformat(event["time"]) + timedelta(minutes=offsets[f"time_offset_{label}_min"])
                if not START <= time < STOP:
                    continue
                adjustment = offsets[f"height_offset_{label}"]
                height = event["height_m"] * adjustment if offsets["height_adjusted_type"] == "R" else event["height_m"] + adjustment
                expected.append({"time": time.isoformat(), "type": event["type"], "height_m": height,
                                 "reference_time": event["time"], "reference_height_m": event["height_m"]})
            expected.sort(key=lambda event: event["time"])
            if len(expected) != len(native):
                raise AssertionError(f"actual transformed/native event counts differ: {sid}")
            for actual_event, expected_event in zip(native, expected):
                delta_s = abs((datetime.fromisoformat(actual_event["time"])-datetime.fromisoformat(expected_event["time"])).total_seconds())
                delta_m = abs(actual_event["height_m"]-expected_event["height_m"])
                if actual_event["type"] != expected_event["type"] or delta_s > 1 or delta_m > 1e-7:
                    raise AssertionError(f"real source arithmetic differs: {sid}: {actual_event}, {expected_event}")
            for kind in ("high", "low"):
                cell = next(event for event in expected if event["type"] == kind)
                native_cell = next(event for event in native if event["type"] == kind)
                result["numeric_cells"].append({"legacy_association_inferred": row["legacy_source_record_id"],
                    "station_id": sid, "kind": kind, "source_numbers": offsets,
                    "independent_expected": cell, "native": native_cell,
                    "current_validity": "unestablished", "current_accuracy": "unverified"})
            for caller, owner in (("client", legacy), ("release", legacy.release)):
                result["legacy_policy_native"].append({"station_id": sid, "legacy_association_inferred": row["legacy_source_record_id"],
                    "caller": caller, "default_discovery_includes": sid in eligible,
                    "default_events": event_rows(owner.extremes(sid, start=START, stop=STOP, datum="chart")),
                    "full_curve": error_of(lambda o=owner: o.heights(sid, start=START, stop=STOP)),
                    "strict_policy_argument": error_of(lambda: strict_constructor(file=args.shell,
                        historical_offsets_policy="exclude", cache_dir=args.out.parent / "cache-strict"))})
    good_red = (len(result["inventory_native"]) == 2 and all(row["default_prediction"]["error"] is not None
                    for row in result["inventory_native"]) and len(result["numeric_cells"]) == 4
                and len(result["unchanged_controls"]) == 3 and all(row["default_discovery_includes"]
                    and row["strict_policy_argument"]["error"] == "TypeError" for row in result["legacy_policy_native"]))
    result["proof"] = "RED missing own historical strict policy" if good_red else "unexpected baseline result"
    result["no_target_GREEN_claim"] = True
    args.out.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(json.dumps({"proof": result["proof"], "numeric_cells": len(result["numeric_cells"]),
                      "unchanged_controls": len(result["unchanged_controls"])}), flush=True)
    return 1 if good_red else 2


class NativeHistoricalBaseline(unittest.TestCase):
    def test_actual_native_historical_policy_is_not_implemented(self):
        self.assertIn("historical_offsets_policy", inspect.signature(otc.OpenTideConstants).parameters,
                      "baseline RED: actual accepted SDK lacks strict own historical policy")


if __name__ == "__main__":
    if "--native" not in sys.argv:
        unittest.main()
    else:
        parser = argparse.ArgumentParser(allow_abbrev=False)
        parser.add_argument("--native", action="store_true")
        for flag in ("release", "shell", "source-inputs", "out"):
            parser.add_argument("--"+flag, type=Path, required=True)
        raise SystemExit(native_baseline(parser.parse_args()))
