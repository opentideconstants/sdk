"""Observed heights require an authenticated original and the exact current own model."""
import copy
import datetime as dt
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from test_datum_fallback import PREDICT, retained_source, write_release
import opentideconstants as otc


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


def observed_document():
    document = json.loads(PREDICT.read_text(encoding="utf-8"))
    station = document["stations"][1]
    model = station["constant_sets"][0]
    convention = dict(document["conventions"][0], convention_id="otc-greenwich-schureman-v1")
    document["conventions"].append(convention)
    model.update(source="gesla-fit", source_version="4.1", convention_id=convention["convention_id"],
                 datum={"msl_offset_m": 1.25},
                 time_base={"code": "verified", "declared": "utc_instant", "published": "utc_instant", "reason": "fixture"},
                 provenance={"input_sha256": ["3" * 64], "tcd_sha256": convention["tables_sha256"]})
    original = {"kind": "observed", "method": "first_reduction", "source_record_id": model["source_record_id"],
                "set_id": model["set_id"], "units": "m", "values": {"mhhw": 2.0, "mllw": 0.25},
                "frame": {"kind": "gauge_zero", "name": "Unspecified", "tie_status": "unknown"},
                "window": {"start": "2026-01-01", "end": "2026-01-31"},
                "basis": {"counted_months": ["2026-01"]}, "uncertainty_m": None,
                "reliability": {"status": "limited", "limitations": ["station_accuracy_uncalibrated"]},
                "input_binding": {"station_id": station["station_id"], "set_id": model["set_id"],
                    "source_record_id": model["source_record_id"], "member_sha256": "3" * 64,
                    "fit_sha256": "4" * 64, "tcd_sha256": "5" * 64,
                    "original_zero": {"msl_offset_m": 1.25, "zero": None, "zero_name": None},
                    "time_base": model["time_base"], "fit_segment": model.get("fit_segment")}}
    bound = copy.deepcopy(original)
    bound["input_binding"].update(constant_set_sha256=digest(model),
                                  model_tcd_sha256=convention["tables_sha256"],
                                  source_candidate_sha256=digest(original))
    source = retained_source(model, [original, bound])
    source["source"] = "gesla"
    station["source_records"] = [source]
    return document, station, model, original, bound


class ObservedDatumBindingTest(unittest.TestCase):
    def test_exact_binding_converts_gauge_values_using_existing_own_zero(self):
        document, station, model, original, bound = observed_document()
        times = [dt.datetime(2026, 10, 23, tzinfo=dt.timezone.utc)]
        for mode in ("eager", "stream"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                with otc.OpenTideConstants(file=write_release(directory, document, mode), mode=mode) as client:
                    args = {"set_id": model["set_id"]}
                    mean = client.heights_at(station["station_id"], times, datum="mean_level", **args)
                    for key, value in original["values"].items():
                        chosen = client.heights_at(station["station_id"], times, datum=key, **args)
                        self.assertAlmostEqual(chosen.items[0].height_m, mean.items[0].height_m + 1.25 - value)
                        self.assertEqual(chosen.datum_kind, "observed")
                        self.assertIsNone(chosen.datum_uncertainty_m)
                        note = chosen.source_note
                        assert isinstance(note, str)
                        self.assertIn("gauge_zero", note)
                        self.assertIn("2026-01", note)
                        feet = client.heights_at(station["station_id"], times, datum=key, units="feet", **args)
                        self.assertEqual(feet.items[0].height_m, chosen.items[0].height_m)
                        self.assertAlmostEqual(feet.items[0].height, chosen.items[0].height_m / 0.3048)
                    self.assertEqual(client.heights_at(station["station_id"], times, **args).items, mean.items)
                    self.assertEqual(client.require_station(station["station_id"]).raw["source_records"][0]["retained_datums"][0], otc._models.freeze(original))

    def test_binding_does_not_accept_a_zero_match_without_all_exported_anchors(self):
        for fault in ("model", "member", "fit", "tcd", "original", "source", "zero", "clock", "window", "missing_original"):
            document, station, model, original, bound = observed_document()
            proof = bound["input_binding"]
            if fault == "model":
                proof["constant_set_sha256"] = "0" * 64
            elif fault == "member":
                proof["member_sha256"] = "0" * 64
            elif fault == "fit":
                proof["fit_sha256"] = None
            elif fault == "tcd":
                proof["model_tcd_sha256"] = "0" * 64
            elif fault == "original":
                proof["source_candidate_sha256"] = "0" * 64
            elif fault == "source":
                station["source_records"][0]["source_record_id"] = "other"
            elif fault == "zero":
                proof["original_zero"]["msl_offset_m"] = 2.0
            elif fault == "clock":
                proof["time_base"] = {"code": "unknown"}
            elif fault == "window":
                bound["window"]["end"] = "2026-02-28"
            else:
                station["source_records"][0]["retained_datums"].remove(original)
            if fault in ("member", "fit", "zero", "clock"):
                original["input_binding"] = {key: copy.deepcopy(value) for key, value in proof.items()
                    if key not in ("constant_set_sha256", "model_tcd_sha256", "source_candidate_sha256")}
                proof["source_candidate_sha256"] = digest(original)
            elif fault == "window":
                original["window"] = copy.deepcopy(bound["window"])
                proof["source_candidate_sha256"] = digest(original)
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as directory:
                with otc.OpenTideConstants(file=write_release(directory, document, "stream"), mode="stream") as client:
                    with self.assertRaises(otc.DatumUnavailableError):
                        client.heights_at(station["station_id"], [dt.datetime(2026, 10, 23, tzinfo=dt.timezone.utc)],
                                          datum="mhhw", set_id=model["set_id"])

    def test_existing_named_value_keeps_precedence(self):
        document, station, model, original, bound = observed_document()
        model["datum"].update(named={"mhhw": 0.75}, basis={"mhhw": {"kind": "published", "method": "source"}})
        bound["input_binding"]["constant_set_sha256"] = digest(model)
        times = [dt.datetime(2026, 10, 23, tzinfo=dt.timezone.utc)]
        with tempfile.TemporaryDirectory() as directory:
            with otc.OpenTideConstants(file=write_release(directory, document, "eager")) as client:
                args = {"set_id": model["set_id"]}
                mean = client.heights_at(station["station_id"], times, datum="mean_level", **args)
                named = client.heights_at(station["station_id"], times, datum="mhhw", **args)
                self.assertAlmostEqual(named.items[0].height_m, mean.items[0].height_m + 0.5)
                self.assertEqual(named.datum_kind, "published")

    def test_existing_retained_computed_value_keeps_precedence(self):
        document, station, model, original, bound = observed_document()
        computed = {"kind": "computed", "method": "sdk_harmonic_extremes_event_means_v1",
                    "source_record_id": model["source_record_id"], "set_id": model["set_id"],
                    "values": {"mhhw": 0.4}, "units": "m", "frame": {"kind": "harmonic_mean"},
                    "window": original["window"], "uncertainty_m": None,
                    "input_binding": {"set_id": model["set_id"], "constant_set_sha256": digest(model)}}
        station["source_records"][0]["retained_datums"].append(computed)
        times = [dt.datetime(2026, 10, 23, tzinfo=dt.timezone.utc)]
        with tempfile.TemporaryDirectory() as directory:
            with otc.OpenTideConstants(file=write_release(directory, document, "eager")) as client:
                args = {"set_id": model["set_id"]}
                mean = client.heights_at(station["station_id"], times, datum="mean_level", **args)
                named = client.heights_at(station["station_id"], times, datum="mhhw", **args)
                self.assertAlmostEqual(named.items[0].height_m, mean.items[0].height_m - 0.4)
                self.assertEqual(named.datum_kind, "computed")

    @unittest.skipUnless(os.environ.get("OTC_OBSERVED_BINDING_NATIVE"), "authenticated observed pilot required")
    def test_actual_own_zero_units_labels_and_metadata(self):
        path = Path(os.environ["OTC_OBSERVED_BINDING_NATIVE"])
        stations = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        times = [dt.datetime(2026, 10, 23, 12, tzinfo=dt.timezone(dt.timedelta(hours=-7)))]
        with otc.OpenTideConstants(file=path, mode="stream") as client:
            count = 0
            for station in stations:
                for source in station["source_records"]:
                    for candidate in source.get("retained_datums", ()):
                        if "source_candidate_sha256" not in candidate.get("input_binding", {}):
                            continue
                        args = {"set_id": candidate["set_id"]}
                        model = next(row for row in station["constant_sets"] if row["set_id"] == candidate["set_id"])
                        mean = client.heights_at(station["station_id"], times, datum="mean_level", **args)
                        info = client.datums(station["station_id"], **args)
                        assert isinstance(info, otc.DatumInfo)
                        for key in ("mhhw", "mllw"):
                            with self.subTest(station=station["station_id"], key=key):
                                meters = client.heights_at(station["station_id"], times, datum=key, **args)
                                feet = client.heights_at(station["station_id"], times, datum=key, units="feet", **args)
                                expected = mean.items[0].height_m + model["datum"]["msl_offset_m"] - candidate["values"][key]
                                self.assertAlmostEqual(meters.items[0].height_m, expected, places=12)
                                self.assertAlmostEqual(feet.items[0].height, expected / 0.3048, places=12)
                                self.assertEqual(meters.datum_kind, "observed")
                                self.assertIsNone(meters.datum_uncertainty_m)
                                note = meters.source_note
                                assert isinstance(note, str)
                                self.assertIn("gauge_zero", note)
                                self.assertIn(candidate["window"]["start"], note)
                                level = next(row for row in info.levels if row.key == key)
                                self.assertEqual(level.method, "first_reduction")
                                self.assertEqual(level.data_span, otc._models.freeze(candidate["window"]))
                                self.assertIsNone(level.uncertainty_m)
                                count += 1
            self.assertGreaterEqual(count, 6)
