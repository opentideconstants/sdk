"""Published table MSL binding, including opt-in real native value proofs."""

import copy
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
from test_datum_fallback import PREDICT, write_release

TIMES = [dt.datetime(2026, 10, 11, tzinfo=dt.timezone.utc)]
ASSUMPTION = "bound via published MSL; assumes model mean = agency MSL (epoch 1983-2001)"


def published_model():
    document = json.loads(PREDICT.read_text(encoding="utf-8"))
    station = document["stations"][1]
    model = station["constant_sets"][0]
    model.pop("datum", None)
    digest = "1" * 64
    url = "https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations/9751388/datums.json?units=metric"
    candidate = {
        "kind": "published", "method": "source", "source_record_id": "9751388",
        "units": "m", "values": {"MSL": 9.091, "VIVD09": 9.079},
        "frame": {"kind": "gauge_zero", "name": "STND", "tie_status": "source_declared"},
        "basis": {"epoch": "1983-2001", "source_fields": {
            "MSL": {"name": "MSL", "value": 9.091},
            "VIVD09": {"name": "VIVD09", "value": 9.079}}},
        "input_binding": {"sha256": digest, "receipt_sha256": "3" * 64, "source_url": url}, "uncertainty_m": None,
    }
    source = {
        "source": "noaa", "source_record_id": "9751388", "source_version": "20261008",
        "licence_id": model["licence_id"], "role": "gauge_station", "disposition": "metadata_only",
        "published_set_ids": [], "detail": "Published NOAA table in its own STND frame",
        "provenance": {"input_sha256": [digest], "inventory_sha256": "2" * 64},
        "original_metadata": {}, "retained_datums": [candidate],
    }
    station["source_records"] = [source]
    return document, station, model, source, candidate


class PublishedMslBindingTests(unittest.TestCase):
    def test_published_same_table_shift_and_labels_without_changing_defaults(self):
        document, station, model, source, candidate = published_model()
        for mode in ("eager", "stream"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                with otc.OpenTideConstants(file=write_release(directory, document, mode), mode=mode) as client:
                    sid, set_id = station["station_id"], model["set_id"]
                    mean = client.heights_at(sid, TIMES, datum="mean_level", set_id=set_id)
                    selected = client.heights_at(sid, TIMES, datum="vivd09", set_id=set_id)
                    self.assertAlmostEqual(selected.items[0].height_m, mean.items[0].height_m + 9.091 - 9.079)
                    self.assertEqual(client.heights_at(sid, TIMES, set_id=set_id).items, mean.items)
                    self.assertIn(ASSUMPTION, selected.source_note)
                    self.assertIn("low", selected.source_note)
                    self.assertIsNone(selected.datum_uncertainty_m)
                    self.assertEqual(selected.datum_kind, "published")
                    level = next(l for l in client.datums(sid, set_id=set_id).levels if l.key == "vivd09")
                    self.assertEqual(level.method, "published_msl_binding")
                    self.assertIn(ASSUMPTION, level.flags)
                    self.assertNotIn("datum", client.require_station(sid).constant_set(set_id).raw)

    def test_binding_rejects_missing_or_mismatched_publisher_evidence(self):
        for fault in ("msl", "units", "epoch", "source", "url", "digest", "receipt", "field", "duplicate", "range"):
            document, station, model, source, candidate = published_model()
            if fault == "msl":
                candidate["values"].pop("MSL")
            elif fault == "units":
                candidate["units"] = "ft"
            elif fault == "epoch":
                candidate["basis"].pop("epoch")
            elif fault == "source":
                candidate["source_record_id"] = "other"
            elif fault == "url":
                candidate["input_binding"]["source_url"] = "https://example.org/datums.json"
            elif fault == "digest":
                candidate["input_binding"]["sha256"] = "not a digest"
            elif fault == "receipt":
                candidate["input_binding"].pop("receipt_sha256")
            elif fault == "field":
                candidate["basis"]["source_fields"]["VIVD09"]["value"] = 100
            elif fault == "duplicate":
                source["retained_datums"].append(copy.deepcopy(candidate))
            else:
                candidate["values"] = {"MSL": 9.091, "GT": 0.2}
                candidate["basis"]["source_fields"]["GT"] = {"name": "GT", "value": 0.2}
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as directory:
                with otc.OpenTideConstants(file=write_release(directory, document, "eager")) as client:
                    with self.assertRaises(otc.DatumUnavailableError):
                        client.heights_at(station["station_id"], TIMES, datum="gt" if fault == "range" else "vivd09",
                                          set_id=model["set_id"])

    def test_existing_named_level_and_chart_keep_precedence(self):
        document, station, model, source, candidate = published_model()
        model["datum"] = {"zero": "harmonic_mean", "chart_datum": "vivd09", "named": {"vivd09": 0.7},
                          "basis": {"vivd09": {"kind": "published", "method": "source"}}}
        with tempfile.TemporaryDirectory() as directory:
            with otc.OpenTideConstants(file=write_release(directory, document, "eager")) as client:
                sid, set_id = station["station_id"], model["set_id"]
                mean = client.heights_at(sid, TIMES, datum="mean_level", set_id=set_id)
                for datum in ("chart", "vivd09"):
                    selected = client.heights_at(sid, TIMES, datum=datum, set_id=set_id)
                    self.assertAlmostEqual(selected.items[0].height_m, mean.items[0].height_m - 0.7)
                    self.assertIsNone(selected.source_note)

    @unittest.skipUnless(os.environ.get("OTC_PUBLISHED_MSL_NATIVE"), "real native evidence not supplied")
    def test_actual_level_metadata_uses_selected_model_zero(self):
        with otc.OpenTideConstants(file=os.environ["OTC_PUBLISHED_MSL_NATIVE"], mode="stream") as client:
            for sid, key, shift in (("OTC-db485c70", "stnd", 14.034),
                                    ("OTC-db485c70", "navd88", 14.034 - 12.929),
                                    ("OTC-b42287c3", "stnd", 0.05)):
                with self.subTest(station=sid, key=key):
                    info = client.datums(sid)
                    level = next(l for l in info.levels if l.key == key)
                    self.assertAlmostEqual(level.value_m, info.msl_offset_m - shift, places=12)
                    chart = next(l for l in info.levels if l.key == info.chart_datum)
                    self.assertAlmostEqual(level.above_chart_m, info.msl_offset_m - shift - chart.value_m, places=12)

    @unittest.skipUnless(os.environ.get("OTC_PUBLISHED_MSL_NATIVE"), "real native evidence not supplied")
    def test_three_actual_publisher_places_and_units(self):
        cases = (("OTC-db485c70", "stnd", 14.034),
                 ("OTC-b42287c3", "stnd", 0.05),
                 ("OTC-e48e302c", "vivd09", 9.091 - 9.079))
        with otc.OpenTideConstants(file=os.environ["OTC_PUBLISHED_MSL_NATIVE"], mode="stream") as client:
            for sid, key, shift in cases:
                with self.subTest(station=sid, key=key):
                    mean = client.heights_at(sid, TIMES, datum="mean_level")
                    default = client.heights_at(sid, TIMES)
                    selected = client.heights_at(sid, TIMES, datum=key)
                    feet = client.heights_at(sid, TIMES, datum=key, units="feet")
                    self.assertEqual(default.items, mean.items)
                    self.assertAlmostEqual(selected.items[0].height_m, mean.items[0].height_m + shift, places=12)
                    self.assertEqual(feet.items[0].height_m, selected.items[0].height_m)
                    self.assertAlmostEqual(feet.items[0].height, selected.items[0].height_m / 0.3048)
                    self.assertIn(ASSUMPTION, selected.source_note)
                    self.assertIsNone(selected.datum_uncertainty_m)
                    print(f"GREEN {sid} {key}: mean={mean.items[0].height_m!r} + shift={shift!r} = {selected.items[0].height_m!r} m; feet={feet.items[0].height!r}; default unchanged; {selected.source_note}")
