"""Public datum metadata projection, including optional native release proof."""

import copy
import dataclasses
import datetime as dt
import hashlib
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


def retained_source(constants, candidates):
    return {
        **{key: constants.get(key) for key in ("source", "source_record_id", "source_version")},
        "role": "gauge_station", "disposition": "retained", "detail": "test retained datum",
        "licence_id": constants["licence_id"], "published_set_ids": [constants["set_id"]],
        "provenance": {"input_sha256": [], "inventory_sha256": "0" * 64},
        "retained_datums": candidates,
    }


class DatumFallbackTest(unittest.TestCase):
    def retained_model(self):
        document = json.loads(PREDICT.read_text(encoding="utf-8"))
        station = document["stations"][1]
        constants = station["constant_sets"][0]
        constants.pop("datum", None)
        digest = hashlib.sha256(json.dumps(constants, sort_keys=True, separators=(",", ":"),
                                           ensure_ascii=False).encode()).hexdigest()
        candidate = {
            "kind": "computed", "method": "sdk_harmonic_extremes_event_means_v1",
            "source_record_id": constants["source_record_id"], "set_id": constants["set_id"],
            "units": "m", "values": {"mhw": 0.4},
            "frame": {"kind": "harmonic_mean", "tie_status": "unknown"},
            "input_binding": {"set_id": constants["set_id"], "constant_set_sha256": digest},
            "uncertainty_m": None,
            "reliability": {"status": "accuracy_unverified", "limitations": ["not surveyed"]},
        }
        station["source_records"] = [retained_source(constants, [candidate])]
        return document, station, constants, candidate

    def test_retained_named_height_matches_own_model_without_changing_defaults(self):
        document, station, constants, candidate = self.retained_model()
        times = [dt.datetime(2026, 10, 11, tzinfo=dt.timezone.utc)]
        for mode in ("eager", "stream"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                with otc.OpenTideConstants(file=write_release(directory, document, mode), mode=mode) as client:
                    sid, set_id = station["station_id"], constants["set_id"]
                    mean = client.heights_at(sid, times, datum="mean_level", set_id=set_id)
                    named = client.heights_at(sid, times, datum="mhw", set_id=set_id)
                    self.assertAlmostEqual(named.items[0].height_m, mean.items[0].height_m - 0.4)
                    self.assertEqual(client.heights_at(sid, times, set_id=set_id).items, mean.items)
                    self.assertIn(candidate["method"], named.source_note)
                    self.assertIsNone(named.datum_uncertainty_m)
                    self.assertIn("accuracy_unverified", named.source_note)
                    level = next(level for level in client.datums(sid, set_id=set_id).levels
                                 if level.key == "mhw")
                    self.assertEqual(level.method, candidate["method"])
                    self.assertIn("not surveyed", level.flags)
                    self.assertNotIn("datum", client.require_station(sid).constant_set(set_id).raw)

    def test_retained_height_requires_exact_source_model_frame_and_unique_value(self):
        for fault in ("source", "source_version", "set_id", "hash", "frame", "units", "duplicate"):
            document, station, constants, candidate = self.retained_model()
            if fault in ("source", "source_version"):
                station["source_records"][0][fault] = "different"
            elif fault == "set_id":
                candidate["set_id"] = "another/model"
            elif fault == "hash":
                candidate["input_binding"]["constant_set_sha256"] = "0" * 64
            elif fault == "frame":
                candidate["frame"]["kind"] = "gauge_zero"
            elif fault == "units":
                candidate["units"] = "ft"
            else:
                station["source_records"][0]["retained_datums"].append(copy.deepcopy(candidate))
            for mode in ("eager", "stream"):
                with self.subTest(fault=fault, mode=mode), tempfile.TemporaryDirectory() as directory:
                    with otc.OpenTideConstants(file=write_release(directory, document, mode), mode=mode) as client:
                        self.assertFalse(client.datums(station["station_id"], set_id=constants["set_id"]).levels)
                        with self.assertRaises(otc.DatumUnavailableError):
                            client.heights_at(station["station_id"],
                                [dt.datetime(2026, 10, 11, tzinfo=dt.timezone.utc)],
                                datum="mhw", set_id=constants["set_id"])

    def test_existing_named_datum_takes_precedence(self):
        document, station, constants, candidate = self.retained_model()
        constants["datum"] = {"zero": "harmonic_mean", "named": {"mhw": 0.9},
                              "basis": {"mhw": {"kind": "published", "method": "source"}}}
        candidate["input_binding"]["constant_set_sha256"] = hashlib.sha256(json.dumps(
            constants, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            with otc.OpenTideConstants(file=write_release(directory, document, "eager")) as client:
                level = client.datums(station["station_id"], set_id=constants["set_id"]).levels[0]
                self.assertEqual((level.value_m, level.method), (0.9, "source"))

    def test_other_retained_heights_and_canonical_source_families(self):
        for source, model_source, key in (("noaa", "noaa", "llwlt"), ("ticon", "ticon-4", "tlt"),
                                          ("gesla", "gesla-fit", "nllw"), ("noaa", "noaa", "mhwn"),
                                          ("noaa", "noaa", "mlwn")):
            document, station, constants, candidate = self.retained_model()
            constants["source"] = model_source
            station["source_records"][0]["source"] = source
            candidate["values"] = {key: 0.4, "mn": 0.8, "gt": 1.0, "hwi": 3.0, "lwi": 9.0}
            candidate["input_binding"]["constant_set_sha256"] = hashlib.sha256(json.dumps(
                constants, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
            with self.subTest(source=source, key=key), tempfile.TemporaryDirectory() as directory:
                with otc.OpenTideConstants(file=write_release(directory, document, "stream"), mode="stream") as client:
                    times = [dt.datetime(2026, 10, 11, tzinfo=dt.timezone.utc)]
                    binding = {"set_id": constants["set_id"]}
                    mean = client.heights_at(station["station_id"], times, datum="mean_level", **binding)
                    selected = client.heights_at(station["station_id"], times, datum=key, **binding)
                    self.assertAlmostEqual(mean.items[0].height_m - selected.items[0].height_m, 0.4)
                    self.assertEqual([level.key for level in client.datums(station["station_id"], **binding).levels], [key])

    def test_low_proxy_keeps_labels_and_requires_actual_subordinate_binding(self):
        for fault in (None, "offset", "reference", "source", "body", "label"):
            document = json.loads(PREDICT.read_text(encoding="utf-8"))
            station = next(row for row in document["stations"] if row["station_id"] == "OTC-P-0030")
            reference = document["stations"][0]
            model = reference["constant_sets"][0]
            own_model = dict(model, source_record_id="noaa:P-0030", set_id="fixture-own-source")
            offsets = station["subordinate_offsets"]
            offsets.update(height_offset_high=1.05, height_offset_low=1.05,
                           time_offset_high_min=20, time_offset_low_min=20,
                           datum={"zero": "chart_datum", "zero_name": "MLLW", "chart_datum": "mllw",
                                  "named": {"mllw": 0}, "basis": {}})
            endpoint = "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations/"
            reference_url = endpoint + model["source_record_id"] + "/datums.json?units=metric"
            body = json.dumps({"self": reference_url.split("?")[0], "units": "meters", "epoch": "fixture"})
            reference_proof = {"source": "noaa", "source_record_id": model["source_record_id"],
                               "native_station_id": reference["station_id"], "source_url": reference_url,
                               "response_json": body, "sha256": hashlib.sha256(body.encode()).hexdigest()}
            reference["source_records"] = [retained_source(model, [{"kind": "published", "input_binding": reference_proof}])]
            body = json.dumps({"refStationId": model["source_record_id"], "heightAdjustedType": "R",
                               "heightOffsetHighTide": 1.05, "heightOffsetLowTide": 1.05,
                               "timeOffsetHighTide": 20, "timeOffsetLowTide": 20})
            own_proof = {**{key: own_model[key] for key in ("source", "source_record_id", "source_version")},
                         "source_url": endpoint + own_model["source_record_id"] + "/tidepredoffsets.json",
                         "reference_source_record_id": model["source_record_id"],
                         "response_json": body, "sha256": hashlib.sha256(body.encode()).hexdigest()}
            label = "approximation: MTL used as MSL proxy, subordinate-derived"
            candidate = {"kind": "computed", "method": "noaa_subordinate_mtl_msl_proxy_v1",
                         "source_record_id": own_model["source_record_id"], "units": "m", "values": {"msl": 0.25},
                         "frame": {"kind": "unknown", "name": "NOAA subordinate MLLW"},
                         "basis": {"native_offsets": {key: offsets[key] for key in (
                             "reference_station_id", "height_adjusted_type", "height_offset_high", "height_offset_low",
                             "time_offset_high_min", "time_offset_low_min")}, "reference_epoch": "fixture",
                             "approximation": label, "proxy_of": "derived_mtl", "never_default": True},
                         "input_binding": {"published_offsets": own_proof, "published_reference": reference_proof},
                         "uncertainty_m": None, "reliability": {"status": "low", "limitations": [label]}}
            station["source_records"] = [retained_source(own_model, [candidate])]
            if fault == "offset":
                candidate["basis"]["native_offsets"]["height_offset_high"] = 2
            elif fault == "reference":
                reference_proof["native_station_id"] = station["station_id"]
            elif fault == "source":
                own_proof["source_version"] = "other"
            elif fault == "body":
                own_proof["response_json"] = "{}"
                own_proof["sha256"] = hashlib.sha256(b"{}").hexdigest()
            elif fault == "label":
                candidate["basis"].pop("approximation")
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as directory:
                with otc.OpenTideConstants(file=write_release(directory, document, "stream"), mode="stream") as client:
                    times = [dt.datetime(2026, 10, 11, tzinfo=dt.timezone.utc)]
                    chart = client.heights_at(station["station_id"], times, datum="chart")
                    if fault:
                        with self.assertRaises(otc.DatumUnavailableError):
                            client.heights_at(station["station_id"], times, datum="msl")
                    else:
                        selected = client.heights_at(station["station_id"], times, datum="msl")
                        self.assertAlmostEqual(chart.items[0].height_m - selected.items[0].height_m, 0.25)
                        self.assertIn(label, selected.source_note)
                        self.assertIn("low", selected.source_note)
                        self.assertIsNone(selected.datum_uncertainty_m)

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
    @unittest.skipUnless(os.environ.get("OTC_RETAINED_SELECTOR_NATIVE"), "actual retained native subset required")
    def test_actual_retained_named_prediction_and_proxy_labels(self):
        times = [dt.datetime(2026, 10, 23, 12, tzinfo=dt.timezone(dt.timedelta(hours=-7)))]
        cases = (
            ("OTC-c259b8a5", "OTC-c259b8a5/noaa/9465149", "mhw", -0.5881265027627832),
            ("OTC-17013f42", None, "msl", -1.24581295604024),
            ("OTC-28c56e20", "OTC-28c56e20/fes2022", "mhw", -0.6429366259334746),
        )
        with otc.OpenTideConstants(file=os.environ["OTC_RETAINED_SELECTOR_NATIVE"], mode="stream") as client:
            for sid, set_id, key, expected in cases:
                with self.subTest(station=sid):
                    prediction = client.heights_at(sid, times, datum=key, set_id=set_id)
                    self.assertAlmostEqual(prediction.items[0].height_m, expected, places=12)
                    self.assertEqual(prediction.datum_kind, "computed")
                    self.assertIsNone(prediction.datum_uncertainty_m)
                    self.assertIn("Retained datum method:", prediction.source_note)
                    self.assertTrue(any(level.key == key for info in client.datums(sid, all_sets=True)
                                        for level in info.levels))
            sid = "OTC-a883bf37"
            chart = client.extremes(sid, start=times[0], stop=times[0] + dt.timedelta(days=1), datum="chart")
            proxy = client.extremes(sid, start=times[0], stop=times[0] + dt.timedelta(days=1), datum="msl")
            self.assertEqual(len(proxy.items), len(chart.items))
            self.assertTrue(proxy.items)
            for original, selected in zip(chart.items, proxy.items):
                self.assertEqual(original.time, selected.time)
                self.assertAlmostEqual(original.height_m - selected.height_m, 0.244755, places=12)
            self.assertIn("approximation: MTL used as MSL proxy, subordinate-derived", proxy.source_note)
            self.assertIn("low", proxy.source_note)
            self.assertIsNone(proxy.datum_uncertainty_m)

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
