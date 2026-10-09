"""Unit tests (python -m unittest discover -s python/tests). The conformance suite is the main proof.
With OTC_TEST_INSTALLED=1 they test the installed package instead of python/src."""
import dataclasses
import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if not os.environ.get("OTC_TEST_INSTALLED"):  # set it to test the installed package (a wheel) instead of python/src
    sys.path.insert(0, str(ROOT / "python" / "src"))

import opentideconstants as otc  # noqa: E402
from opentideconstants._cache import datestamp_key  # noqa: E402
from opentideconstants._fold import fold  # noqa: E402
from opentideconstants._release import haversine  # noqa: E402

GOOD = ROOT / "conformance" / "fixtures" / "good"


class FoldTest(unittest.TestCase):
    def test_letters_that_do_not_decompose(self):
        self.assertEqual([fold(x) for x in ["Tromsø", "Ålesund", "Łeba", "Straße"]],
                         ["tromso", "alesund", "leba", "strasse"])

    def test_whitespace(self):
        self.assertEqual(fold("  San \t  FRANCISCO "), "san francisco")

    def test_packaged_table_is_the_suite_table(self):
        pkg = ROOT / "python" / "src" / "opentideconstants" / "name_fold.json"
        self.assertEqual(pkg.read_bytes(), (ROOT / "conformance" / "name_fold.json").read_bytes())


class OrderTest(unittest.TestCase):
    def test_counter_order(self):
        ds = ["20991231.10", "20991231", "20991231.2", "20991230"]
        self.assertEqual(sorted(ds, key=datestamp_key), ["20991230", "20991231", "20991231.2", "20991231.10"])


class ObjectsTest(unittest.TestCase):
    def setUp(self):
        self.c = otc.OpenTideConstants(file=str(GOOD / "OTC_20991231.2.jsonl"))

    def tearDown(self):
        self.c.close()

    def test_frozen(self):
        st = self.c.station("OTC-T-0001")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            st.name = "x"
        with self.assertRaises(TypeError):
            st.raw["name"] = "x"

    def test_enum_equals_string(self):
        st = self.c.station("OTC-T-0019")
        self.assertEqual(st.kind, "current")
        self.assertEqual(str(st.kind), "current")
        self.assertIs(otc.Kind("future-kind"), otc.Kind.OTHER)

    def test_errors_share_the_base(self):
        with self.assertRaises(otc.OpenTideConstantsError) as cm:
            self.c.require_station("OTC-T-0005")
        self.assertEqual(cm.exception.code, "station_removed")
        self.assertEqual(cm.exception.tombstone.station_id, "OTC-T-0005")

    def test_spec_haversine_example(self):
        self.assertAlmostEqual(haversine(0.0, 179.95, 0.0, 179.9), 5.559754011674749, places=9)
        self.assertAlmostEqual(haversine(0.0, 179.95, 0.0, -179.9), 16.679262035030458, places=9)


FIXTURES = ROOT / "conformance" / "fixtures"


class CacheDatestampTest(unittest.TestCase):
    """Datestamps that name cache paths (spec §4.2, §5.4; review PK01 B1-4, P2)."""

    def test_cached_skips_a_name_with_a_trailing_newline(self):
        import tempfile
        from opentideconstants._cache import Cache
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("20991231", "20991230\n"):
                d = Path(tmp) / "v1" / "releases" / name
                d.mkdir(parents=True)
                (d / ".verified").write_text('{"files": {}}', encoding="utf-8")
            self.assertEqual(Cache(Path(tmp)).cached(), ["20991231"])

    def test_bad_datestamp_key_is_an_sdk_error(self):
        for bad in ("2024.x", "../../x", "20991231\n", "20991231.1234567890"):
            with self.assertRaises(otc.InvalidReleaseError):
                datestamp_key(bad)


class Format10Test(unittest.TestCase):
    """Format 1.0 reading (spec §4.5, §4.6, §7.3, §7.4)."""

    def setUp(self):
        self.c = otc.OpenTideConstants(file=str(FIXTURES / "v1" / "OTC_20991231.3.jsonl"))

    def tearDown(self):
        self.c.close()

    def test_supported_versions(self):
        self.assertEqual(otc.SUPPORTED_FORMAT_MAJORS, (1,))
        self.assertEqual(otc.SUPPORTED_FORMAT_VERSION, "1.0")
        pkg = json.loads((ROOT / "python" / "supported-formats.json").read_text(encoding="utf-8"))
        self.assertEqual(pkg["supported_format_version"], otc.SUPPORTED_FORMAT_VERSION)

    def test_supported_formats_json_ships_in_the_package(self):
        """spec §7.4: supported-formats.json is inside every package; read it as package data."""
        from importlib.resources import files
        res = files(otc) / "supported-formats.json"
        if res.is_file():
            doc = json.loads(res.read_text(encoding="utf-8"))
        elif os.environ.get("OTC_TEST_INSTALLED"):
            self.fail("supported-formats.json is not in the installed package")
        else:  # the source tree: the build copies python/supported-formats.json into the package
            doc = json.loads((ROOT / "python" / "supported-formats.json").read_text(encoding="utf-8"))
        self.assertEqual(doc, {"language": "python", "version": otc.__version__,
                               "supported_format_version": otc.SUPPORTED_FORMAT_VERSION})
        self.assertEqual(doc, json.loads((ROOT / "python" / "supported-formats.json").read_text(encoding="utf-8")))

    def test_no_constants_hidden_by_default(self):
        st = self.c.station("OTC-T-0103")
        self.assertEqual([s.set_id for s in st.constant_sets()], ["OTC-T-0103/noaa"])
        self.assertEqual([s.set_id for s in st.constant_sets(include_no_constants=True)],
                         ["OTC-T-0103/noaa", "OTC-T-0103/gesla-fit"])
        self.assertIs(st.constant_set("OTC-T-0103/gesla-fit").qc_status, otc.QcStatus.NO_CONSTANTS)
        self.assertIsNone(self.c.station("OTC-T-0104").recommended_set)

    def test_source_filter_and_stats_skip_no_constants(self):
        ids = [s.station_id for s in self.c.stations(source="gesla-fit")]
        self.assertNotIn("OTC-T-0103", ids)
        self.assertNotIn("OTC-T-0104", ids)
        stats = self.c.release.stats
        self.assertEqual(stats.qc_status["no_constants"], 2)
        total_sets = sum(len(s.constant_sets(include_no_constants=True)) for s in self.c.stations())
        self.assertEqual(sum(stats.qc_status.values()), total_sets)
        self.assertEqual(sum(stats.source.values()), total_sets - 2)

    def test_typed_time_base_and_provenance(self):
        cs = self.c.station("OTC-T-0102").constant_set("OTC-T-0102/gesla-corrected")
        tb = cs.time_base
        self.assertIsInstance(tb, otc.TimeBase)
        self.assertIs(tb.code, otc.TimeBaseCode.CORRECTED)
        self.assertEqual(dict(tb.correction), {"from": "utc_mean_start60", "to": "utc_instant"})
        self.assertEqual(tb.months_dropped, ("2097-02", "2097-03"))
        self.assertIsNone(tb.evidence[0]["detail"])
        self.assertIsNone(self.c.station("OTC-T-0101").constant_set("OTC-T-0101/noaa").time_base)
        b = self.c.station("OTC-T-0101").constant_set("OTC-T-0101/noaa").provenance.build
        self.assertIsInstance(b, otc.ProvenanceBuild)
        self.assertEqual(b.built_at.year, 2099)
        p = self.c.station("OTC-T-0105").recommended_set.provenance
        self.assertEqual(p.carried_from_release, "20991231.2")
        self.assertIs(self.c.station("OTC-T-0105").recommended_set.qc_flags[0].flag, otc.QcFlagName.CARRIED_OVER)

    def test_merged_tombstone_on_the_error(self):
        with self.assertRaises(otc.StationRemovedError) as cm:
            self.c.require_station("OTC-T-0108")
        t = cm.exception.tombstone
        self.assertIs(t.removed_reason, otc.RemovedReason.MERGED)
        self.assertEqual(t.merged_into, "OTC-T-0101")

    def test_file_has_no_version_doi(self):
        self.assertIsNone(self.c.release.zenodo_version_doi)
        self.assertFalse(hasattr(self.c.release, "doi"))

    def test_unknown_qc_status_is_other(self):
        with otc.OpenTideConstants(file=str(FIXTURES / "bad" / "format-minor" / "OTC_20991231.jsonl")) as c:
            sets = c.station("OTC-T-0010").constant_sets(include_no_constants=True)
            self.assertIn(otc.QcStatus.OTHER, [s.qc_status for s in sets])
            self.assertIn("other", c.release.stats.qc_status)

    def test_reader_too_old(self):
        with self.assertRaises(otc.ReaderTooOldError) as cm:
            otc.OpenTideConstants(file=str(FIXTURES / "reader" / "OTC_20991231.4.json"))
        self.assertIn("1.99", str(cm.exception))
        self.assertIn("1.0", str(cm.exception))
        self.assertEqual(cm.exception.code, "reader_too_old")


if __name__ == "__main__":
    unittest.main()
