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


class _Server:
    """A local HTTP server for unit tests: serves conformance/fixtures/<sub> (always 200, no ETag); `script` maps a
    path to (status, headers, body) for special answers."""

    def __init__(self, sub="good", script=None):
        import functools
        import http.server
        import threading
        script = script or {}
        root = str(FIXTURES / sub)
        self.requests = []
        outer = self

        class H(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                outer.requests.append((self.path, dict(self.headers)))
                if self.path in script:
                    status, headers, body = script[self.path]
                    self.send_response(status)
                    for k, v in headers.items():
                        self.send_header(k, v)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                super().do_GET()

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(H, directory=root))
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class PointerCacheTest(unittest.TestCase):
    """The cached pointer (spec §5.2 step 2 and 5, §5.4; review PK02 P80, P81, P32)."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self.tmp.name) / "cache"

    def tearDown(self):
        for p in self.cache.rglob("*"):
            if p.is_dir():
                p.chmod(0o755)
        self.tmp.cleanup()

    def test_unconditional_304_with_no_cached_pointer_is_not_a_raw_error(self):
        srv = _Server(script={"/OTC_latest-f1.json": (304, {}, b"")})
        try:
            with self.assertRaises(otc.NetworkError):  # a 304 to a request with no If-None-Match is a server fault
                otc.OpenTideConstants(base_url=srv.url, cache_dir=str(self.cache))
        finally:
            srv.close()

    def test_a_pointer_cache_that_cannot_be_written_is_not_fatal(self):
        srv = _Server()
        try:
            otc.OpenTideConstants(base_url=srv.url, cache_dir=str(self.cache)).close()
            (self.cache / "v1" / "pointer").chmod(0o555)
            with otc.OpenTideConstants(base_url=srv.url, cache_dir=str(self.cache)) as c:
                self.assertEqual(c.release.datestamp, "20991231.2")
        finally:
            srv.close()

    def test_body_is_not_replaced_when_the_old_etag_cannot_be_removed(self):
        from opentideconstants._cache import Cache
        c = Cache(self.cache)
        c.write_pointer("OTC_latest-f1.json", b'{"a": 1}', '"e1"')
        d = self.cache / "v1" / "pointer"
        (d / "OTC_latest-f1.json.etag").unlink()
        (d / "OTC_latest-f1.json.etag").mkdir()  # cannot be unlinked as a file
        (d / "OTC_latest-f1.json.etag" / "x").write_text("y")
        try:
            c.write_pointer("OTC_latest-f1.json", b'{"a": 2}', None)
        except otc.CacheError:
            pass
        self.assertEqual((d / "OTC_latest-f1.json").read_bytes(), b'{"a": 1}')


class FormatVersionTest(unittest.TestCase):
    """MAJOR.MINOR is two non-negative integers with no leading zeros (spec §7.4, CR D9, D10; review PK03)."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self.tmp.name) / "cache"

    def tearDown(self):
        for p in self.cache.rglob("*"):
            if p.is_dir():
                p.chmod(0o755)
        self.tmp.cleanup()

    def test_malformed_format_version_is_invalid_release(self):
        from opentideconstants._release import check_format
        for fv in ("1.x", "1.", "+1.0", " 1.0", "1.0.0", "1_0.0", "1.\u00b2", "01.0", "1.00", "1"):
            with self.assertRaises(otc.InvalidReleaseError, msg=fv):
                check_format(fv, "1.0")
        for mrv in ("2", "1.x", "1.0.0", "\u00b9.0"):
            with self.assertRaises(otc.InvalidReleaseError, msg=mrv):
                check_format("1.0", mrv)
        check_format("1.0", "1.0")
        with self.assertRaises(otc.UnsupportedFormatError):
            check_format("2.0", "2.0")

    def test_malformed_pointer_format_version_is_invalid_release(self):
        doc = json.loads((FIXTURES / "good" / "OTC_latest-f1.json").read_text(encoding="utf-8"))
        doc["format_version"] = "1.x"
        srv = _Server(script={"/OTC_latest-f1.json": (200, {}, json.dumps(doc).encode())})
        try:
            with self.assertRaises(otc.InvalidReleaseError):
                otc.OpenTideConstants(base_url=srv.url, cache_dir=str(self.cache), on_network_error="raise")
        finally:
            srv.close()

    def test_cached_release_with_no_recorded_version_is_checked_before_it_is_chosen(self):
        import shutil
        srv = _Server()
        try:
            otc.OpenTideConstants(base_url=srv.url, cache_dir=str(self.cache), mode="stream").close()
        finally:
            srv.close()
        newer = self.cache / "v1" / "releases" / "20991231.3"
        newer.mkdir()
        for ext in (".jsonl", ".meta.json"):
            shutil.copy(FIXTURES / "bad" / "format-major" / f"OTC_20991231{ext}", newer / f"OTC_20991231.3{ext}")
        files = {f"OTC_20991231.3{ext}": {"sha256": None, "size": (newer / f"OTC_20991231.3{ext}").stat().st_size}
                 for ext in (".jsonl", ".meta.json")}
        (newer / ".verified").write_text(json.dumps({"files": files}), encoding="utf-8")
        with otc.OpenTideConstants(cache_dir=str(self.cache), offline=True, mode="stream") as c:
            self.assertEqual(c.release.datestamp, "20991231.2")

    def test_check_for_update_with_a_read_only_pointer_cache(self):
        srv = _Server()
        try:
            with otc.OpenTideConstants(base_url=srv.url, cache_dir=str(self.cache)) as c:
                (self.cache / "v1" / "pointer").chmod(0o555)
                self.assertIsNone(c.check_for_update())
        finally:
            srv.close()


class LockAndPruneTest(unittest.TestCase):
    """Lock liveness, .verified writes and prune safety (spec §4.3, §5.4, CR D3; review PK04)."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cache = self.root / "cache"

    def tearDown(self):
        for p in self.root.rglob("*"):
            if p.is_dir():
                p.chmod(0o755)
        self.root.chmod(0o755)
        self.tmp.cleanup()

    def test_a_stale_lock_that_cannot_be_removed_is_a_cache_error_not_a_hang(self):
        import threading
        from opentideconstants import _cache
        d = self.root / "rel"
        (d / ".lock").mkdir(parents=True)
        (d / ".lock" / "owner.json").write_text("{}")
        (d / ".lock").chmod(0o555)  # owner.json cannot be deleted, so the stale lock cannot be removed
        saved = _cache.LOCK_STALE_S, _cache.LOCK_POLL_S
        _cache.LOCK_STALE_S, _cache.LOCK_POLL_S = 0.05, 0.01
        out = []

        def take():
            try:
                with _cache.lock_dir(d, "test"):
                    out.append("held")
            except Exception as e:  # noqa: BLE001
                out.append(e)
        t = threading.Thread(target=take, daemon=True)
        t.start()
        t.join(5)
        _cache.LOCK_STALE_S, _cache.LOCK_POLL_S = saved
        self.assertFalse(t.is_alive(), "lock_dir loops forever on a stale lock it cannot remove")
        self.assertIsInstance(out[0], otc.CacheError)

    def test_release_leaves_a_lock_that_another_process_took(self):
        from opentideconstants._cache import lock_dir
        d = self.root / "rel"
        d.mkdir()
        with lock_dir(d, "test") as held:
            self.assertTrue(held)
            owner = json.loads((d / ".lock" / "owner.json").read_text())
            self.assertGreaterEqual(len(owner.get("token", "")), 32)
            owner["token"] = "another process"
            (d / ".lock" / "owner.json").write_text(json.dumps(owner))
        self.assertTrue((d / ".lock").is_dir())

    def test_an_index_entry_without_a_doi_keeps_the_known_doi(self):
        srv = _Server()
        try:
            with otc.OpenTideConstants(release="20991231", base_url=srv.url, cache_dir=str(self.cache)) as c:
                vp = self.cache / "v1" / "releases" / "20991231" / ".verified"
                v = json.loads(vp.read_text())
                v["zenodo_version_doi"] = "10.5072/zenodo.9"
                vp.write_text(json.dumps(v))
                c.releases()
                self.assertEqual(json.loads(vp.read_text())["zenodo_version_doi"], "10.5072/zenodo.9")
        finally:
            srv.close()

    def test_prune_skips_a_release_being_downloaded(self):
        srv = _Server()
        try:
            with otc.OpenTideConstants(release="20991231", base_url=srv.url, cache_dir=str(self.cache)):
                pass
            with otc.OpenTideConstants(release="20991231.2", base_url=srv.url, cache_dir=str(self.cache)) as c:
                (self.cache / "v1" / "releases" / "20991231" / ".lock").mkdir()  # another process holds it
                self.assertEqual(c.prune(keep=1), ())
                self.assertTrue((self.cache / "v1" / "releases" / "20991231" / ".verified").is_file())
        finally:
            srv.close()

    def test_prune_keeps_a_release_the_caller_still_holds(self):
        idx = json.loads((FIXTURES / "good" / "OTC_index.json").read_text(encoding="utf-8"))
        script = {"/OTC_latest-f1.json": (200, {}, json.dumps(idx["releases"][1]).encode())}
        srv = _Server(script=script)
        try:
            with otc.OpenTideConstants(base_url=srv.url, cache_dir=str(self.cache), mode="stream") as c:
                old = c.release
                self.assertEqual(old.datestamp, "20991231")
                del script["/OTC_latest-f1.json"]
                self.assertTrue(c.update().updated)
                self.assertEqual(c.prune(keep=0), ())
                self.assertTrue((self.cache / "v1" / "releases" / "20991231" / ".verified").is_file())
                self.assertEqual(old.station("OTC-T-0001").station_id, "OTC-T-0001")
        finally:
            srv.close()


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
