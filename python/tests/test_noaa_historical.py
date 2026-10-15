"""Real-source NOAA historical baseline and reusable native input helpers."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from dataclasses import replace
import hashlib
import inspect
import json
import os
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from typing import Any

import opentideconstants as otc
from opentideconstants._historical_offsets import historical_offset_eligibility, require_historical_offset
from opentideconstants._models import freeze


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



class NativeHistoricalEligibility(unittest.TestCase):
    """Policy cells derived from the pinned real two-row producer artifact."""

    @classmethod
    def setUpClass(cls):
        candidate = os.environ.get("OTC_NOAA_CANDIDATE")
        release = os.environ.get("OTC_NOAA_NATIVE_RELEASE")
        proof = os.environ.get("OTC_NOAA_PROOF")
        if not candidate or not release or not proof:
            raise unittest.SkipTest("native source candidate/release/proof paths required")
        path = Path(candidate)
        cls.candidate_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        if cls.candidate_sha != "be435a8b5c7ad6ed601ad510559d1f771be74595a2a0f67367210fb75b7dbb63":
            raise AssertionError("actual SF1 source artifact changed")
        cls.document = load_native_inputs(path)
        if load_native_inputs(Path(release)) != cls.document:
            raise AssertionError("native release is not the exact source-derived candidate")
        cls.client = otc.OpenTideConstants(file=Path(release), cache_dir=Path(proof) / "cache-predicate")
        cls.addClassCleanup(cls.client.close)
        cls.profiles = [s["subordinate_offsets"] for s in cls.document["stations"]
                        if s.get("subordinate_offsets", {}).get("offset_id")]
        if len(cls.profiles) != 2:
            raise AssertionError("expected the exact two actual profiles")
        cls.licences = {licence.licence_id: licence for licence in cls.client.release.licences}
        cls.cells = []
        cls.proof = Path(proof)

    @classmethod
    def tearDownClass(cls):
        (cls.proof / f"native-predicate-cells-{sys.version_info.major}{sys.version_info.minor}.json").write_text(json.dumps({
            "candidate_sha256": cls.candidate_sha, "sdk_file": otc.__file__, "sdk_version": otc.__version__,
            "python": sys.version, "cells": cls.cells, "scope": "own-policy primitive; no public prediction GREEN claim"
        }, sort_keys=True, indent=2) + "\n")

    def evaluate(self, offsets, *, expected=True, **options):
        reference = self.client.require_station(offsets["reference_station_id"])
        selected = next(cs for cs in reference.constant_sets(include_no_constants=True)
                        if cs.source == "noaa" and cs.quantity == "water_level")
        arguments: dict[str, Any] = dict(policy="fallback", licences=self.licences, selected_reference=selected,
                         better_path=False)
        arguments.update(options)
        before = deepcopy(offsets)
        actual = historical_offset_eligibility(offsets, **arguments)
        self.assertEqual(actual, expected)
        self.assertEqual(offsets, before)
        self.cells.append({"offset_id": offsets["offset_id"], "options": {
            key: value for key, value in options.items() if key not in ("licences", "selected_reference")},
            "own_qc": offsets["qc_status"], "equivalence": offsets["vintage"]["reference_2020_equivalence"],
            "outcome": actual, "expected": expected})
        if actual:
            chosen = require_historical_offset(offsets, **arguments)
            self.assertEqual(chosen.offset_id, offsets["offset_id"])
            self.assertEqual(chosen.offsets["source_version"], offsets["source_version"])
            self.assertEqual(chosen.offsets, freeze(offsets))
            with self.assertRaises(TypeError):
                chosen.offsets["vintage"]["current_validity"] = "verified"
            self.assertEqual(chosen.offsets["provenance"]["raw_row_text"], offsets["provenance"]["raw_row_text"])
            self.assertIs(chosen.reference, arguments["selected_reference"])
        else:
            with self.assertRaises(otc.NoConstantsError):
                require_historical_offset(offsets, **arguments)

    def test_default_strict_and_explicit_precedence(self):
        for offsets in self.profiles:
            self.evaluate(offsets)
            self.evaluate(offsets, policy="exclude", expected=False)
            self.evaluate(offsets, policy="exclude", selection="explicit", expected=False)
            self.evaluate(offsets, better_path=True, expected=False)
            self.evaluate(offsets, better_path=True, selection="explicit")

    def test_same_native_own_qc_and_vintage_cells(self):
        for offsets in self.profiles:
            self.evaluate(offsets)
            reference = self.client.require_station(offsets["reference_station_id"])
            selected = next(cs for cs in reference.constant_sets(include_no_constants=True)
                            if cs.source == "noaa" and cs.quantity == "water_level")
            for case in ("own_qc_removed", "own_retirement_omitted"):
                changed = deepcopy(offsets)
                if case == "own_qc_removed":
                    changed["qc_status"] = "removed"
                else:
                    changed.pop("vintage")
                with self.assertRaises(otc.InvalidReleaseError):
                    historical_offset_eligibility(changed, policy="fallback", licences=self.licences,
                                                 selected_reference=selected, better_path=False)
                self.cells.append({"offset_id": offsets["offset_id"], "case": case,
                                   "outcome": "InvalidReleaseError", "expected": "refuse malformed own metadata"})

    def test_own_and_reference_licences(self):
        for offsets in self.profiles:
            self.evaluate(offsets, commercial_only=True)
            missing = dict(self.licences)
            missing.pop(offsets["licence_id"])
            with self.assertRaises(otc.InvalidReleaseError):
                historical_offset_eligibility(offsets, policy="fallback", licences=missing,
                                             selected_reference=None, better_path=False)
            restricted = next(licence for licence in self.licences.values() if licence.commercial_use is False)
            changed = deepcopy(offsets)
            changed["licence_id"] = restricted.licence_id
            self.evaluate(changed)
            self.evaluate(changed, commercial_only=True, expected=False)

    def test_reference_qc_datum_and_convention(self):
        for offsets in self.profiles:
            reference = self.client.require_station(offsets["reference_station_id"])
            selected = next(cs for cs in reference.constant_sets(include_no_constants=True)
                            if cs.source == "noaa" and cs.quantity == "water_level")
            self.evaluate(offsets, selected_reference=replace(selected, qc_status="flagged"), expected=False)
            own = self.client.require_station(next(s["station_id"] for s in self.document["stations"]
                if s.get("subordinate_offsets", {}).get("offset_id"))).subordinate_offsets
            assert own is not None
            self.evaluate(offsets, selected_reference=replace(selected, fallback=own.fallback), expected=False)
            self.evaluate(offsets, selected_reference=replace(selected, source_record_id="other-reference"), expected=False)
            self.evaluate(offsets, selected_reference=None, expected=False)
            raw = deepcopy(next(s for s in self.document["stations"]
                                if s["station_id"] == offsets["reference_station_id"])["constant_sets"][0])
            raw["datum"]["basis"]["mllw"]["kind"] = "derived"
            self.evaluate(offsets, selected_reference=replace(selected, raw=freeze(raw)), expected=False)
            self.evaluate(offsets, selected_reference=replace(selected, convention=replace(
                selected.convention, v0_model="unknown")), expected=False)
            restricted = next(licence for licence in self.licences.values() if licence.commercial_use is False)
            self.evaluate(offsets, selected_reference=replace(selected, licence=restricted),
                          commercial_only=True, expected=False)

    def test_equivalence_is_informational(self):
        # Counterfactual contract states exercise policy only; they are not performed book findings.
        for offsets in self.profiles:
            for outcome in ("not_checked", "matched_at_publisher_precision", "disagrees"):
                changed = deepcopy(offsets)
                changed["vintage"]["reference_2020_equivalence"] = outcome
                if outcome != "not_checked":
                    changed["vintage"]["reference_2020_equivalence_sha256"] = self.candidate_sha
                self.evaluate(changed)

    def test_wrong_profile_and_invalid_options(self):
        for offsets in self.profiles:
            changed = deepcopy(offsets)
            changed["offset_id"] = "another-profile"
            with self.assertRaises(otc.InvalidReleaseError):
                historical_offset_eligibility(changed, policy="fallback", licences=self.licences,
                                             selected_reference=None, better_path=False)
            for options in ({"policy": "unknown"}, {"selection": "unknown"}, {"better_path": 1},
                            {"commercial_only": 1}):
                arguments: dict[str, Any] = dict(policy="fallback", licences=self.licences, selected_reference=None, better_path=False)
                arguments.update(options)
                with self.assertRaises(otc.InvalidArgumentError):
                    historical_offset_eligibility(offsets, **arguments)


class NativeHistoricalPublic(unittest.TestCase):
    """Public policy/value calls on the exact source-derived producer specimen."""

    @classmethod
    def setUpClass(cls):
        release = os.environ.get('OTC_NOAA_NATIVE_RELEASE')
        if not release:
            raise unittest.SkipTest('OTC_NOAA_NATIVE_RELEASE is not set: the actual public historical gate needs that private release')
        cls.path = Path(release)
        cls.document = load_native_inputs(cls.path)
        cls.targets = [station for station in cls.document['stations']
                       if station.get('subordinate_offsets', {}).get('offset_id')]
        if len(cls.targets) != 2:
            raise AssertionError('actual two historical profiles required')

    def test_default_explicit_metadata_and_full_curve_refusals(self):
        for mode, suffix in (('eager', '.json'), ('stream', '.jsonl')):
            with self.subTest(mode=mode), otc.OpenTideConstants(file=self.path.with_suffix(suffix), mode=mode) as client:
                self.assertEqual(client.release.historical_offsets_policy, 'fallback')
                for target in self.targets:
                    sid, own = target['station_id'], target['subordinate_offsets']
                    self.assertIn(sid, {station.station_id for station in client.stations()})
                    for caller in (client, client.release):
                        default = caller.extremes(sid, start=START, stop=STOP)
                        explicit = caller.extremes(sid, start=START, stop=STOP, offset_id=own['offset_id'])
                        self.assertEqual(default, explicit)
                        self.assertEqual(default.offset_id, own['offset_id'])
                        self.assertEqual(default.offset_source_version, 'annual-tide-tables-2020')
                        self.assertTrue(default.historical_offsets)
                        self.assertEqual(default.current_validity, 'unestablished')
                        self.assertEqual(default.current_accuracy, 'unverified')
                        self.assertEqual(default.reference_2020_equivalence, 'not_checked')
                        self.assertIn('retired NOAA profile', default.source_note)
                        for options in ({}, {'offset_id': own['offset_id']}):
                            with self.assertRaises(otc.ExtremesOnlyError):
                                caller.heights(sid, start=START, stop=STOP, **options)
                            with self.assertRaises(otc.ExtremesOnlyError):
                                caller.heights_at(sid, [START], **options)

    def test_strict_exclusion_cannot_be_loosened(self):
        for mode, suffix in (('eager', '.json'), ('stream', '.jsonl')):
            with self.subTest(mode=mode), otc.OpenTideConstants(file=self.path.with_suffix(suffix), mode=mode,
                                                               historical_offsets_policy='exclude') as client:
                self.assertEqual(client.release.historical_offsets_policy, 'exclude')
                for target in self.targets:
                    sid = target['station_id']
                    self.assertIsNotNone(client.station(sid))
                    for flagged in (False, True):
                        for fallback in (False, True):
                            self.assertNotIn(sid, {station.station_id for station in client.stations(
                                include_flagged=flagged, include_fallback=fallback)})
                    for caller in (client, client.release):
                        for options in ({}, {'offset_id': target['subordinate_offsets']['offset_id']}):
                            with self.assertRaises(otc.HistoricalOffsetsExcludedError):
                                caller.extremes(sid, start=START, stop=STOP, **options)

    def test_invalid_policy_and_selectors(self):
        for policy in ('unknown', None, True):
            with self.subTest(policy=policy), self.assertRaises(otc.InvalidArgumentError):
                otc.OpenTideConstants(file=self.path, historical_offsets_policy=policy)
        with otc.OpenTideConstants(file=self.path) as client:
            for target in self.targets:
                sid, own = target['station_id'], target['subordinate_offsets']
                for value in (True, 1, 'another-profile'):
                    with self.subTest(value=value), self.assertRaises(otc.InvalidArgumentError):
                        client.extremes(sid, start=START, stop=STOP, offset_id=value)
                with self.assertRaises(otc.InvalidArgumentError):
                    client.extremes(sid, start=START, stop=STOP, set_id='another-set', offset_id=own['offset_id'])


if __name__ == "__main__":
    if "--native" not in sys.argv:
        unittest.main()
    else:
        parser = argparse.ArgumentParser(allow_abbrev=False)
        parser.add_argument("--native", action="store_true")
        for flag in ("release", "shell", "source-inputs", "out"):
            parser.add_argument("--"+flag, type=Path, required=True)
        raise SystemExit(native_baseline(parser.parse_args()))
