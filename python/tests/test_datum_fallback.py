"""Public datum metadata projection, including optional native release proof."""

import copy
import dataclasses
import datetime as dt
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if not os.environ.get("OTC_TEST_INSTALLED"):
    sys.path.insert(0, str(ROOT / "python" / "src"))
import opentideconstants as otc

PREDICT = ROOT / "conformance" / "fixtures" / "predict" / "OTC_20991231.7.json"


def write_release(directory, document, mode, name="OTC_20991231.7"):
    path = Path(directory) / (name + (".json" if mode == "eager" else ".jsonl"))
    document = copy.deepcopy(document)
    if mode == "eager":
        path.write_text(json.dumps(document), encoding="utf-8")
    else:
        stations = document.pop("stations")
        path.write_text(
            "".join(json.dumps(row) + "\n" for row in stations), encoding="utf-8"
        )
        path.with_name(name + ".meta.json").write_text(
            json.dumps(document), encoding="utf-8"
        )
    return path


class DatumFallbackTest(unittest.TestCase):
    def test_public_datums_preserves_complete_frozen_fallback(self):
        original = json.loads(PREDICT.read_text(encoding="utf-8"))
        station = original["stations"][0]
        constants = station["constant_sets"][0]
        key = next(
            key
            for key, basis in constants["datum"]["basis"].items()
            if basis["kind"] == "computed"
        )
        marker = {
            "reason": "datum_gate_failed",
            "basis": "Existing computation",
            "otc_finding": "Acceptance not established",
            "future_evidence": {"notes": ["retained"]},
        }
        constants["datum"].setdefault("basis", {}).setdefault(key, {})["fallback"] = (
            marker
        )
        for mode in ("eager", "stream"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                with otc.OpenTideConstants(
                    file=write_release(directory, original, mode), mode=mode
                ) as client:
                    selected = client.datums(
                        station["station_id"], set_id=constants["set_id"]
                    )
                    level = next(row for row in selected.levels if row.key == key)
                    self.assertEqual(level.fallback, otc._models.freeze(marker))
                    self.assertEqual(level.fallback["reason"], "datum_gate_failed")
                    self.assertEqual(
                        level.fallback["future_evidence"]["notes"], ("retained",)
                    )
                    with self.assertRaises(TypeError):
                        level.fallback["basis"] = "changed"
                    with self.assertRaises(TypeError):
                        level.fallback["future_evidence"]["notes"][0] = "changed"
                    with self.assertRaises(dataclasses.FrozenInstanceError):
                        level.fallback = None
                    all_sets = client.datums(station["station_id"], all_sets=True)
                    self.assertEqual(
                        next(
                            row for row in all_sets if row.set_id == constants["set_id"]
                        ),
                        selected,
                    )

    def test_absent_metadata_and_legacy_constructor_default_to_none(self):
        with otc.OpenTideConstants(file=PREDICT) as client:
            info = client.datums("OTC-P-0001")
            for level in info.levels:
                self.assertIsNone(level.fallback)
            legacy = [
                getattr(info.levels[0], field.name)
                for field in dataclasses.fields(otc.DatumLevel)
                if field.name != "fallback"
            ]
            self.assertIsNone(otc.DatumLevel(*legacy).fallback)

    def test_harmonic_mean_is_explicit_and_keeps_missing_datum_errors(self):
        original = json.loads(PREDICT.read_text(encoding="utf-8"))
        times = [dt.datetime(2026, 10, 11, tzinfo=dt.timezone.utc)]
        for mode in ("eager", "stream"):
            for frame in ("harmonic_mean", "gauge_zero", None):
                document = copy.deepcopy(original)
                constants = document["stations"][0]["constant_sets"][0]
                constants["datum"] = {
                    "named": {"lat": -0.4},
                    "basis": {"lat": {"kind": "computed"}},
                }
                if frame is not None:
                    constants["datum"]["zero"] = frame
                with self.subTest(mode=mode, frame=frame), tempfile.TemporaryDirectory() as directory:
                    with otc.OpenTideConstants(file=write_release(directory, document, mode), mode=mode) as client:
                        sid = document["stations"][0]["station_id"]
                        mean = client.heights_at(sid, times, datum="mean_level")
                        if frame != "harmonic_mean":
                            for request in ("lat", "zero", "msl", "chart"):
                                with self.assertRaises(otc.DatumUnavailableError) as caught:
                                    client.heights_at(sid, times, datum=request)
                                self.assertEqual(caught.exception.missing, "msl_offset_m")
                            continue
                        named = client.heights_at(sid, times, datum="lat")
                        self.assertAlmostEqual(named.items[0].height_m - mean.items[0].height_m, 0.4)
                        self.assertIsNone(named.datum_uncertainty_m)
                        zero = client.heights_at(sid, times, datum="zero")
                        self.assertEqual(zero.items, mean.items)
                        self.assertEqual(zero.datum_name, "harmonic_mean")
                        for request, missing in (("msl", "msl"), ("hat", "hat"), ("chart", "chart_datum")):
                            with self.assertRaises(otc.DatumUnavailableError) as caught:
                                client.heights_at(sid, times, datum=request)
                            self.assertEqual(caught.exception.missing, missing)
                        with self.assertRaises(otc.DatumUnavailableError) as caught:
                            client.extremes(
                                "OTC-P-0035", start=times[0],
                                stop=times[0] + dt.timedelta(days=1),
                            )
                        self.assertEqual(caught.exception.missing, "msl_offset_m")


class NativeDatumFallbackProof(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get("OTC_DATUM_FALLBACK_CONTRACT"), "native contract required"
    )
    def test_three_actual_native_cases(self):
        contract = json.loads(
            Path(os.environ["OTC_DATUM_FALLBACK_CONTRACT"]).read_text(encoding="utf-8")
        )
        self.assertGreaterEqual(len(contract["cases"]), 3)
        labelled = contract["release_fixture"]
        unlabelled = copy.deepcopy(labelled)
        for station in unlabelled["stations"]:
            for constants in station["constant_sets"]:
                for basis in (constants.get("datum") or {}).get("basis", {}).values():
                    basis.pop("fallback", None)
        witnesses = []
        for mode in ("eager", "stream"):
            with tempfile.TemporaryDirectory() as directory:
                actual_path = write_release(directory, labelled, mode, "OTC_20261011")
                control_directory = Path(directory) / "control"
                control_directory.mkdir()
                control_path = write_release(
                    control_directory, unlabelled, mode, "OTC_20261011"
                )
                with (
                    otc.OpenTideConstants(file=actual_path, mode=mode) as actual,
                    otc.OpenTideConstants(file=control_path, mode=mode) as control,
                ):
                    for case in contract["cases"]:
                        sid, set_id = case["station_id"], case["set_id"]
                        with self.subTest(mode=mode, station=sid):
                            info = actual.datums(sid, set_id=set_id)
                            baseline = control.datums(sid, set_id=set_id)
                            station, original_station = (
                                actual.require_station(sid),
                                control.require_station(sid),
                            )
                            ranking = [
                                row.set_id
                                for row in station.constant_sets(
                                    include_no_constants=True
                                )
                            ]
                            self.assertEqual(
                                ranking,
                                [
                                    row.set_id
                                    for row in original_station.constant_sets(
                                        include_no_constants=True
                                    )
                                ],
                            )
                            self.assertEqual(
                                station.recommended_set.set_id,
                                case["recommended_set_id"],
                            )
                            times = [
                                dt.datetime(2026, 10, 11, hour, tzinfo=dt.timezone.utc)
                                for hour in (0, 6, 12)
                            ]
                            prediction = actual.heights_at(sid, times, set_id=set_id)
                            self.assertEqual(
                                prediction,
                                control.heights_at(sid, times, set_id=set_id),
                            )
                            self.assertEqual(
                                actual.datums(sid).set_id, control.datums(sid).set_id
                            )
                            all_sets = actual.datums(sid, all_sets=True)
                            self.assertEqual(
                                next(row for row in all_sets if row.set_id == set_id),
                                info,
                            )
                            self.assertEqual(
                                {row.key: row.value_m for row in info.levels},
                                case["datum"]["named"],
                            )
                            levels = []
                            failures = []
                            for level, old in zip(info.levels, baseline.levels):
                                expected = (
                                    case["datum"]["basis"]
                                    .get(level.key, {})
                                    .get("fallback")
                                )
                                exposed = getattr(level, "fallback", None)
                                fields = {
                                    field.name: getattr(level, field.name)
                                    for field in dataclasses.fields(level)
                                    if field.name != "fallback"
                                }
                                self.assertEqual(
                                    fields,
                                    {name: getattr(old, name) for name in fields},
                                )
                                if expected is None:
                                    self.assertIsNone(exposed)
                                elif exposed != otc._models.freeze(expected):
                                    failures.append(level.key)
                                levels.append(
                                    {
                                        "key": level.key,
                                        "value_m": level.value_m,
                                        "kind": level.kind,
                                        "fallback": dict(exposed)
                                        if exposed is not None
                                        else None,
                                        "expected_fallback": expected,
                                    }
                                )
                            witness = {
                                "mode": mode,
                                "station_id": sid,
                                "set_id": set_id,
                                "levels": levels,
                                "ranking": ranking,
                                "recommended_set_id": station.recommended_set.set_id,
                                "prediction_heights_m": [
                                    row.height_m for row in prediction.items
                                ],
                                "values_fields_predictions_ranking_unchanged": True,
                                "missing_fallback_keys": failures,
                            }
                            witnesses.append(witness)
                            print(json.dumps(witness, sort_keys=True), flush=True)
                            self.assertEqual(
                                failures,
                                [],
                                "public datums() dropped fallback metadata",
                            )
        if os.environ.get("OTC_DATUM_FALLBACK_WITNESS"):
            Path(os.environ["OTC_DATUM_FALLBACK_WITNESS"]).write_text(
                json.dumps(witnesses, indent=2) + "\n"
            )


class NativeHarmonicMeanProof(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get("OTC_HARMONIC_MEAN_CONTRACT"), "native harmonic mean contract required"
    )
    def test_three_actual_named_datums(self):
        contract = json.loads(Path(os.environ["OTC_HARMONIC_MEAN_CONTRACT"]).read_text())
        self.assertEqual(len(contract["cases"]), 3)
        baseline_path = os.environ.get("OTC_HARMONIC_MEAN_BASELINE")
        baseline = json.loads(Path(baseline_path).read_text()) if baseline_path else []
        witnesses, failures = [], []
        times = [dt.datetime(2026, 10, 11, hour, tzinfo=dt.timezone.utc) for hour in (0, 6, 12)]
        for mode in ("eager", "stream"):
            with tempfile.TemporaryDirectory() as directory:
                path = write_release(directory, contract["release_fixture"], mode, "OTC_20261011")
                with otc.OpenTideConstants(file=path, mode=mode) as client:
                    for case in contract["cases"]:
                        sid, set_id = case["station_id"], case["set_id"]
                        mean = client.heights_at(sid, times, set_id=set_id, datum="mean_level")
                        witness = {"mode": mode, "station_id": sid, "set_id": mean.set_id,
                                   "mean_level_m": [p.height_m for p in mean.items], "named": {}}
                        if baseline:
                            old = next(row for row in baseline if row["mode"] == mode and row["station_id"] == sid)
                            self.assertEqual(witness["mean_level_m"], old["mean_level_m"])
                        info = client.datums(sid, set_id=set_id)
                        for key in ("lat", "hat"):
                            try:
                                result = client.heights_at(sid, times, set_id=set_id, datum=key)
                            except otc.DatumUnavailableError as error:
                                witness["named"][key] = {"error": str(error), "missing": error.missing}
                                failures.append((mode, sid, key, str(error)))
                                continue
                            level = next(level for level in info.levels if level.key == key)
                            shifts = [p.height_m - m.height_m for p, m in zip(result.items, mean.items)]
                            for shift in shifts:
                                self.assertAlmostEqual(shift, -level.value_m, places=10)
                            self.assertEqual(result.datum_name, key)
                            self.assertEqual(result.datum_kind, "computed")
                            self.assertIsNone(result.datum_uncertainty_m)
                            self.assertEqual(level.fallback["reason"], "datum_gate_failed")
                            events = client.extremes(sid, start=times[0], stop=times[0] + dt.timedelta(days=1), set_id=set_id, datum=key)
                            mean_events = client.extremes(sid, start=times[0], stop=times[0] + dt.timedelta(days=1), set_id=set_id, datum="mean_level")
                            self.assertEqual([(p.time, p.type) for p in events.items], [(p.time, p.type) for p in mean_events.items])
                            for point, control in zip(events.items, mean_events.items):
                                self.assertAlmostEqual(point.height_m - control.height_m, -level.value_m, places=10)
                            witness["named"][key] = {"height_m": [p.height_m for p in result.items], "shift_m": shifts, "event_count": len(events.items)}
                        if not any("error" in value for value in witness["named"].values()):
                            zero = client.heights_at(sid, times, set_id=set_id, datum="zero")
                            self.assertEqual(zero.items, mean.items)
                            self.assertEqual(zero.datum_name, "harmonic_mean")
                            self.assertEqual(info.zero, "harmonic_mean")
                            self.assertIsNone(info.msl_offset_m)
                            self.assertIsNone(info.zero_name)
                        witnesses.append(witness)
                        print(json.dumps(witness, sort_keys=True), flush=True)
        if os.environ.get("OTC_HARMONIC_MEAN_WITNESS"):
            Path(os.environ["OTC_HARMONIC_MEAN_WITNESS"]).write_text(json.dumps(witnesses, indent=2) + "\n")
        self.assertEqual(failures, [], "actual retained TICON named datums unavailable")
