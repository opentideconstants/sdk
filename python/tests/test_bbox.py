"""Public bounding-box discovery through Client and held Release."""
import os
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if not os.environ.get("OTC_TEST_INSTALLED"):
    sys.path.insert(0, str(ROOT / "python" / "src"))

import opentideconstants as otc
from opentideconstants import _canonical, _canonical_types

GOOD = ROOT / "conformance" / "fixtures" / "good" / "OTC_20991231.2.jsonl"
BOX = dict(south=37.665, west=-122.4659, north=37.8063, east=-122.3)


class BboxTests(unittest.TestCase):
    def test_canonical_bbox_validation(self):
        omitted = _canonical_types._OMITTED
        arguments = _canonical_types._BboxArguments(
            member_id="Release.bbox", **BOX, limit=omitted, country=omitted, type=omitted,
            kind=omitted, source=omitted, source_type=omitted,
            include_flagged=omitted, include_fallback=omitted,
        )
        self.assertEqual(_canonical._validate_operation_arguments(
            operation="bbox", arguments=arguments, member_contract=arguments), arguments)
        for change in (dict(south=91), dict(west=float("inf")), dict(limit=0), dict(include_flagged=1)):
            with self.subTest(change=change), self.assertRaises(otc.InvalidArgumentError):
                invalid = replace(arguments, **change)
                _canonical._validate_operation_arguments(
                    operation="bbox", arguments=invalid, member_contract=invalid)

    def test_public_rectangles_filters_and_limit(self):
        for mode in ("eager", "stream"):
            with tempfile.TemporaryDirectory() as cache:
                with otc.OpenTideConstants(file=GOOD, mode=mode, cache_dir=cache) as client:
                    for target in (client, client.release):
                        with self.subTest(mode=mode, receiver=type(target).__name__):
                            self.assertEqual([s.station_id for s in target.bbox(**BOX)],
                                             ["OTC-T-0001", "OTC-T-0003", "OTC-T-0004"])
                            self.assertEqual([s.station_id for s in target.bbox(**BOX, type="subordinate", limit=1)],
                                             ["OTC-T-0003"])
                            self.assertEqual([s.station_id for s in target.bbox(**BOX, include_flagged=True)],
                                             ["OTC-T-0001", "OTC-T-0002", "OTC-T-0003", "OTC-T-0004"])
                            self.assertEqual([s.station_id for s in target.bbox(south=-1, west=179.8, north=1, east=-179.8)],
                                             ["OTC-T-0007", "OTC-T-0008"])
                            self.assertEqual(target.bbox(south=0, west=0, north=0, east=0), ())

    def test_invalid_arguments(self):
        invalid = [dict(south=-91), dict(north=91), dict(west=-181), dict(east=181),
                   dict(south=38), dict(north=float("nan")), dict(east=float("inf")),
                   dict(west=True), dict(limit=0), dict(limit=1.5), dict(country=1)]
        with tempfile.TemporaryDirectory() as cache:
            with otc.OpenTideConstants(file=GOOD, cache_dir=cache) as client:
                for target in (client, client.release):
                    for change in invalid:
                        with self.subTest(change=change, receiver=type(target).__name__):
                            with self.assertRaises(otc.InvalidArgumentError):
                                target.bbox(**{**BOX, **change})

    def test_inclusive_edges_and_selected_materialization(self):
        with tempfile.TemporaryDirectory() as cache:
            with otc.OpenTideConstants(file=GOOD, mode="stream", cache_dir=cache) as client:
                release = client.release
                station = release.require_station("OTC-T-0001")
                self.assertIn(station, release.bbox(south=station.lat, north=station.lat,
                                                    west=station.lon, east=station.lon))
                materialized = []

                def observe(frame, event, arg):
                    if event == "call" and frame.f_code is release._station_from_entry.__func__.__code__:
                        materialized.append(frame.f_locals["e"]["station_id"])

                previous = sys.getprofile()
                try:
                    sys.setprofile(observe)
                    selected = release.bbox(**BOX, limit=1)
                finally:
                    sys.setprofile(previous)
                self.assertEqual([s.station_id for s in selected], ["OTC-T-0001"])
                self.assertEqual(materialized, ["OTC-T-0001"])
