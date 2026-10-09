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
        # The old ETag cannot be removed: that is a cache error, and the body is not replaced.
        with self.assertRaises(otc.CacheError):
            c.write_pointer("OTC_latest-f1.json", b'{"a": 2}', None)
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
        (d / ".lock" / "owner.json").write_text('{"started_at": "2000-01-01T00:00:00Z"}')  # old: stale (CR2 DR3)
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

    # spec §5.4 (CR2 DR3): a lock is stale only when the waiter has waited LOCK_STALE_S and the lock itself is at
    # least 120 s old. These tests shorten the wait; the age stays 120 s, and the lock's age is set by its
    # started_at or its mtime, so the outcome does not depend on timing.
    def _lock(self, started_at=None, mtime=None):
        d = self.root / "rel"
        (d / ".lock").mkdir(parents=True)
        if started_at is not None:
            (d / ".lock" / "owner.json").write_text(json.dumps({"pid": 1, "token": "other", "started_at": started_at}))
        if mtime is not None:
            os.utime(d / ".lock", (mtime, mtime))
        return d

    def _fast_wait(self):
        from opentideconstants import _cache
        saved = _cache.LOCK_STALE_S, _cache.LOCK_POLL_S
        _cache.LOCK_STALE_S, _cache.LOCK_POLL_S = 0.05, 0.01

        def restore():
            _cache.LOCK_STALE_S, _cache.LOCK_POLL_S = saved
        self.addCleanup(restore)
        return _cache

    def test_a_waiter_does_not_remove_a_young_lock(self):
        import time
        _cache = self._fast_wait()
        d = self._lock(started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        polls = []

        def done():  # ends the wait after 30 polls: 6 times the (shortened) stale wait
            polls.append(1)
            return len(polls) >= 30
        with _cache.lock_dir(d, "test", done=done) as held:
            self.assertFalse(held, "a waiter took a lock that is only seconds old")
        self.assertEqual(json.loads((d / ".lock" / "owner.json").read_text())["token"], "other")

    def test_a_waiter_takes_an_old_lock_by_started_at_or_by_mtime(self):
        _cache = self._fast_wait()
        for kind in ("started_at", "mtime"):
            with self.subTest(kind):
                d = self._lock(started_at="2000-01-01T00:00:00Z") if kind == "started_at" else self._lock(mtime=946684800)
                with _cache.lock_dir(d, "test", done=lambda: False) as held:
                    self.assertTrue(held)
                    self.assertNotEqual(json.loads((d / ".lock" / "owner.json").read_text())["token"], "other")
                os.rmdir(d)

    def test_two_waiters_on_a_crashed_lock_never_hold_it_together(self):
        import threading
        _cache = self._fast_wait()
        d = self._lock(started_at="2000-01-01T00:00:00Z")
        first_in, second_in = threading.Event(), threading.Event()
        overlap = []

        def waiter(i):
            with _cache.lock_dir(d, f"t{i}") as held:
                if not first_in.is_set():
                    first_in.set()
                    # the other waiter has waited past the stale time; it must not take this young lock
                    overlap.append(second_in.wait(1.0))
                else:
                    second_in.set()
                self.assertTrue(held)
        # the second waiter starts once the first holds the lock, so it meets a young lock (two waiters that read
        # the crashed lock's age at the same instant can still both remove it; spec §5.4 accepts that)
        ts = [threading.Thread(target=waiter, args=(i,), daemon=True) for i in (1, 2)]
        ts[0].start()
        self.assertTrue(first_in.wait(10))
        ts[1].start()
        for t in ts:
            t.join(10)
        self.assertEqual(overlap, [False], "two waiters held the lock at the same time")
        self.assertTrue(second_in.is_set())

    def test_try_lock_takes_an_old_lock_and_leaves_a_young_one(self):
        from opentideconstants import _cache
        d = self._lock(started_at="2000-01-01T00:00:00Z")
        self.assertTrue(_cache.try_lock(d), "a non-blocking take did not recover a crashed process's lock")
        os.rmdir(d / ".lock")
        (d / ".lock").mkdir()
        self.assertFalse(_cache.try_lock(d))
        self.assertTrue((d / ".lock").is_dir())

    def test_the_doi_note_does_not_wait_for_a_held_lock(self):
        import threading
        import types
        from opentideconstants import _cache
        srv = _Server()
        saved = _cache.LOCK_STALE_S
        _cache.LOCK_STALE_S = 30.0
        self.addCleanup(setattr, _cache, "LOCK_STALE_S", saved)
        try:
            with otc.OpenTideConstants(release="20991231", base_url=srv.url, cache_dir=str(self.cache)) as c:
                rd = self.cache / "v1" / "releases" / "20991231"
                (rd / ".lock").mkdir()  # another process holds it (young)
                before = (rd / ".verified").read_text()
                info = types.SimpleNamespace(datestamp="20991231", zenodo_version_doi="10.5072/zenodo.77")
                t = threading.Thread(target=c._note_entry, args=(info,), daemon=True)
                t.start()
                t.join(5)
                self.assertFalse(t.is_alive(), "the DOI note waits for the release lock")
                self.assertEqual((rd / ".verified").read_text(), before)
        finally:
            srv.close()

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


class StreamIndexTest(unittest.TestCase):
    """The stream index is checked, not trusted (spec §6.2, CR D4, D17; review PK05)."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cache = self.root / "cache"
        srv = _Server()
        try:
            otc.OpenTideConstants(base_url=srv.url, cache_dir=str(self.cache), mode="stream").close()
        finally:
            srv.close()
        self.index = self.cache / "v1" / "releases" / "20991231.2" / "index-v1.json"

    def tearDown(self):
        self.tmp.cleanup()

    def reopen(self):
        return otc.OpenTideConstants(cache_dir=str(self.cache), offline=True, mode="stream")

    def test_index_entry_with_a_null_lat_is_stale(self):
        idx = json.loads(self.index.read_text(encoding="utf-8"))
        idx["stations"][0]["lat"] = None
        self.index.write_text(json.dumps(idx), encoding="utf-8")
        with self.reopen() as c:
            self.assertTrue(len(c.near(lat=37.8, lon=-122.4, radius_km=5000)) > 0)

    def test_deeply_nested_index_is_stale_not_a_recursion_error(self):
        self.index.write_text("[" * 200000 + "]" * 200000, encoding="utf-8")
        with self.reopen() as c:
            self.assertEqual(c.station("OTC-T-0001").station_id, "OTC-T-0001")

    def test_line_that_does_not_match_its_entry_is_invalid_release_and_drops_the_index(self):
        idx = json.loads(self.index.read_text(encoding="utf-8"))
        a, b = idx["stations"][0], idx["stations"][1]
        a["station_id"], b["station_id"] = b["station_id"], a["station_id"]
        idx["stations"][0], idx["stations"][1] = b, a  # keep the entries in offset order
        idx["stations"].sort(key=lambda e: e["offset"])
        self.index.write_text(json.dumps(idx), encoding="utf-8")
        with self.reopen() as c:
            with self.assertRaises(otc.InvalidReleaseError) as cm:
                c.station(a["station_id"])
            self.assertIn("index-v1.json", str(cm.exception))
        self.assertFalse(self.index.exists())
        with self.reopen() as c:
            self.assertEqual(c.station(a["station_id"]).station_id, a["station_id"])

    def test_lone_surrogate_is_invalid_release(self):
        lines = (FIXTURES / "good" / "OTC_20991231.2.jsonl").read_text(encoding="utf-8").splitlines()
        lines[0] = lines[0].replace('"name": "', '"name": "\\ud800', 1).replace('"name":"', '"name":"\\ud800', 1)
        self.assertIn("\\ud800", lines[0])
        d = self.root / "rel"
        d.mkdir()
        (d / "OTC_20991231.2.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        (d / "OTC_20991231.2.meta.json").write_bytes((FIXTURES / "good" / "OTC_20991231.2.meta.json").read_bytes())
        for mode in ("eager", "stream"):
            with self.assertRaises(otc.InvalidReleaseError, msg=mode):
                otc.OpenTideConstants(file=str(d / "OTC_20991231.2.jsonl"), mode=mode).close()


class RepeatedIdsTest(unittest.TestCase):
    """Repeated ids and malformed ids are invalid_release in every load path (spec §6.1, CR D5; review PK06)."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, edit_line0=None, edit_meta=None):
        lines = [json.loads(x) for x in (FIXTURES / "good" / "OTC_20991231.2.jsonl").read_text(encoding="utf-8").splitlines()]
        meta = json.loads((FIXTURES / "good" / "OTC_20991231.2.meta.json").read_text(encoding="utf-8"))
        if edit_line0:
            edit_line0(lines[0])
        if edit_meta:
            edit_meta(meta)
        (self.dir / "OTC_20991231.2.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")
        (self.dir / "OTC_20991231.2.meta.json").write_text(json.dumps(meta), encoding="utf-8")
        return str(self.dir / "OTC_20991231.2.jsonl")

    def assert_invalid(self, path):
        for mode in ("eager", "stream"):
            with self.assertRaises(otc.InvalidReleaseError, msg=mode):
                otc.OpenTideConstants(file=path, mode=mode).close()

    def test_non_string_alias_id(self):
        self.assert_invalid(self.write(lambda d: d["aliases"].__setitem__("noaa", ["9900001", 5])))

    def test_null_set_id(self):
        def edit(d):
            d["recommended_set_id"] = None
            d["constant_sets"][0]["set_id"] = None
        self.assert_invalid(self.write(edit))

    def test_repeated_licence_id(self):
        self.assert_invalid(self.write(edit_meta=lambda m: m["licences"].append(dict(m["licences"][0]))))


class MalformedInputTest(RepeatedIdsTest):
    """Malformed data and bad arguments are SDK errors, raised when they happen (spec §4.8, §7.3; review PK07)."""

    def test_constituent_without_a_name_fails_at_load(self):
        self.assert_invalid(self.write(lambda d: d["constant_sets"][0]["constituents"][0].pop("name")))

    def test_string_months_dropped_fails_at_load(self):
        self.assert_invalid(self.write(
            lambda d: d["constant_sets"][0].__setitem__("time_base", {"code": "verified", "months_dropped": "2097-02"})))

    def test_bool_and_out_of_range_lat_fail_at_load(self):
        self.assert_invalid(self.write(lambda d: d.__setitem__("lat", True)))
        self.assert_invalid(self.write(lambda d: d.__setitem__("lat", 91.0)))
        self.assert_invalid(self.write(lambda d: d.__setitem__("lon", -180.5)))

    def test_rfc3339_times(self):
        from opentideconstants._models import parse_time
        import datetime as dt
        want = dt.datetime(2099, 12, 31, 6, 0, 0, 120000, tzinfo=dt.timezone.utc)
        for v in ("2099-12-31T06:00:00.12Z", "2099-12-31t06:00:00.12z", "2099-12-31T08:00:00.12+02:00",
                  "2099-12-31T06:00:00.1200000Z", "2099-12-31T08:00:00.12+0200"):
            self.assertEqual(parse_time(v), want, v)
        with self.assertRaises(otc.InvalidReleaseError):
            parse_time("31/12/2099")

    def test_bad_provenance_build_time_does_not_fail_the_station(self):
        def edit(d):
            d["constant_sets"][0].setdefault("provenance", {})["build"] = {"built_at": "not a time"}
        with otc.OpenTideConstants(file=self.write(edit)) as c:
            st = c.stations()[0]
            self.assertIsNone(st.constant_sets()[0].provenance.build.built_at)

    def test_huge_int_argument_is_invalid_argument(self):
        with otc.OpenTideConstants(file=str(GOOD / "OTC_20991231.2.jsonl")) as c:
            with self.assertRaises(otc.InvalidArgumentError):
                c.near(lat=10 ** 400, lon=0, radius_km=1)
            with self.assertRaises(otc.InvalidArgumentError):
                c.near(lat=0, lon=0, radius_km=10 ** 400)

    def test_iter_stations_checks_its_arguments_when_called(self):
        with otc.OpenTideConstants(file=str(GOOD / "OTC_20991231.2.jsonl")) as c:
            with self.assertRaises(otc.InvalidArgumentError):
                c.iter_stations(country=5)

    def test_timeout_and_update_interval_must_be_positive_and_finite(self):
        for kw in ({"timeout": 0}, {"timeout": float("nan")}, {"timeout": float("inf")},
                   {"update_interval": float("nan")}, {"update_interval": 0}):
            with self.assertRaises(otc.InvalidArgumentError, msg=kw):
                otc.OpenTideConstants(file=str(GOOD / "OTC_20991231.2.jsonl"), **kw)

    def test_objects_are_hashable(self):
        for mode in ("eager", "stream"):
            with otc.OpenTideConstants(file=str(GOOD / "OTC_20991231.2.jsonl"), mode=mode) as c:
                r = c.release
                objs = [r.stats, *r.conventions, *r.licences, c.tombstone("OTC-T-0005")]
                for st in c.stations():
                    objs.append(st)
                    objs.extend(st.validation)
                    for cs in st.constant_sets(include_no_constants=True):
                        objs += [cs, cs.provenance, cs.provenance.build, cs.time_base, cs.datum, *cs.qc_flags,
                                 *cs.constituents, *cs.validation]
                for o in objs:
                    hash(o)
                self.assertIn(c.station("OTC-T-0001"), {c.station("OTC-T-0001")})


class ValueParityTest(RepeatedIdsTest):
    """Values the four SDKs must report the same way (review PK08)."""

    def test_stats_bucket_unknown_type_as_the_station_reports_it(self):
        with otc.OpenTideConstants(file=self.write(lambda d: d.__setitem__("type", "lighthouse"))) as c:
            st = c.stations()[0]
            self.assertIs(st.type, otc.StationType.OTHER)
            self.assertIn("other", c.release.stats.type)
            self.assertNotIn("lighthouse", c.release.stats.type)


class OfflineTest(unittest.TestCase):
    """Offline means no network check at all (spec §5.5, §5.6, CR D6; review PK09)."""

    def test_auto_update_does_not_run_offline(self):
        import tempfile
        import time
        with tempfile.TemporaryDirectory() as tmp:
            srv = _Server()
            try:
                otc.OpenTideConstants(base_url=srv.url, cache_dir=tmp).close()
            finally:
                srv.close()
            with otc.OpenTideConstants(cache_dir=tmp, offline=True, auto_update=True, update_interval=0.001) as c:
                time.sleep(0.01)
                with self.assertNoLogs("opentideconstants", level="WARNING"):
                    c.station("OTC-T-0001")


class ErrorClassTest(unittest.TestCase):
    """Network vs local IO vs configuration errors (spec §4.8, §5.7, CR D19; review PK10)."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cache = self.root / "cache"

    def tearDown(self):
        for p in self.root.rglob("*"):
            p.chmod(0o755 if p.is_dir() else 0o644)
        self.tmp.cleanup()

    def cached(self):
        srv = _Server()
        try:
            otc.OpenTideConstants(base_url=srv.url, cache_dir=str(self.cache)).close()
        finally:
            srv.close()
        return self.cache / "v1" / "releases" / "20991231.2"

    def test_a_sink_write_error_is_local_io_and_not_retried(self):
        from opentideconstants._http import Http
        srv = _Server()

        class Full:
            def seek(self, n):
                pass

            def truncate(self):
                pass

            def write(self, b):
                raise OSError(28, "No space left on device")
        try:
            with self.assertRaises(OSError) as cm:
                Http(user_agent="t").get(srv.url + "OTC_20991231.2.jsonl", sink=Full())
            self.assertNotIsInstance(cm.exception, otc.OpenTideConstantsError)
            self.assertEqual(len(srv.requests), 1)
        finally:
            srv.close()

    def test_bad_base_url_and_proxy_are_invalid_argument(self):
        for kw in ({"base_url": "data.example.org/"}, {"base_url": "ftp://data.example.org/"},
                   {"proxy": "http://proxy:notaport"}, {"proxy": "proxy.example.org:3128"}):
            with self.assertRaises(otc.InvalidArgumentError, msg=kw):
                otc.OpenTideConstants(cache_dir=str(self.cache), on_network_error="raise", **kw)

    def test_a_certificate_failure_is_not_retried(self):
        import shutil
        import ssl
        import subprocess
        import threading
        import time
        if not shutil.which("openssl"):
            self.skipTest("no openssl")
        key, crt = self.root / "k.pem", self.root / "c.pem"
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-subj", "/CN=127.0.0.1",
                        "-keyout", str(key), "-out", str(crt), "-days", "1"], check=True, capture_output=True)
        srv = _Server()
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(str(crt), str(key))
        srv.httpd.socket = ctx.wrap_socket(srv.httpd.socket, server_side=True, do_handshake_on_connect=False)
        url = srv.url.replace("http://", "https://")
        t0 = time.monotonic()
        try:
            with self.assertRaises(otc.NetworkError):
                otc.OpenTideConstants(base_url=url, cache_dir=str(self.cache), on_network_error="raise")
            self.assertLess(time.monotonic() - t0, 2.5, "a certificate failure was retried")
        finally:
            srv.close()

    def test_corrupt_verified_is_not_trusted(self):
        d = self.cached()
        (d / ".verified").write_text(json.dumps({"files": {"OTC_20991231.2.json": "not an object"}}))
        with self.assertRaises(otc.OfflineError):
            otc.OpenTideConstants(cache_dir=str(self.cache), offline=True)

    def test_unreadable_verified_is_an_io_error_not_absent(self):
        d = self.cached()
        (d / ".verified").chmod(0)
        with self.assertRaises(otc.FileError):
            otc.OpenTideConstants(cache_dir=str(self.cache), offline=True)

    def test_download_with_a_cached_sha256_that_is_not_text(self):
        d = self.cached()
        (d / "OTC_20991231.2.sha256").write_bytes(b"\xff\xfe")
        with otc.OpenTideConstants(cache_dir=str(self.cache), offline=True) as c:
            with self.assertRaises(otc.OpenTideConstantsError):
                c.download("20991231.2", to=str(self.root / "out"))


class ChecksumTest(unittest.TestCase):
    """Checksums, verify() and a corrupt cache (spec §4.3, §4.3.1, §4.8, §5.2; review PK11)."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.cache = Path(self.tmp.name) / "cache"
        self.dir = self.cache / "v1" / "releases" / "20991231.2"

    def tearDown(self):
        self.tmp.cleanup()

    def pointer(self, edit):
        doc = json.loads((FIXTURES / "good" / "OTC_latest-f1.json").read_text(encoding="utf-8"))
        edit(doc)
        return _Server(script={"/OTC_latest-f1.json": (200, {}, json.dumps(doc).encode())})

    def test_upper_case_pointer_sha256_passes_verify_on_open(self):
        def up(doc):
            for f in doc["files"]:
                f["sha256"] = f["sha256"].upper()
        srv = self.pointer(up)
        try:
            otc.OpenTideConstants(base_url=srv.url, cache_dir=str(self.cache)).close()
            with otc.OpenTideConstants(base_url=srv.url, cache_dir=str(self.cache), verify_on_open=True) as c:
                self.assertEqual(c.loaded_from, "cache")
        finally:
            srv.close()

    def test_pointer_without_the_json_digest_still_verifies(self):
        def edit(doc):
            for f in doc["files"]:
                if f["name"] == "OTC_20991231.2.json":
                    f["sha256"] = None
        srv = self.pointer(edit)
        try:
            otc.OpenTideConstants(base_url=srv.url, cache_dir=str(self.cache)).close()
            with otc.OpenTideConstants(base_url=srv.url, cache_dir=str(self.cache), verify_on_open=True) as c:
                self.assertEqual(c.loaded_from, "cache")
                self.assertTrue(c.verify())
        finally:
            srv.close()

    def test_truncated_cached_file_names_both_digests_and_is_removed(self):
        srv = _Server()
        try:
            otc.OpenTideConstants(base_url=srv.url, cache_dir=str(self.cache), mode="stream").close()
        finally:
            srv.close()
        p = self.dir / "OTC_20991231.2.jsonl"
        p.write_bytes(p.read_bytes()[:-10])
        with self.assertRaises(otc.ChecksumError) as cm:
            otc.OpenTideConstants(cache_dir=str(self.cache), offline=True, mode="stream")
        self.assertIsNotNone(cm.exception.expected)
        self.assertIsNotNone(cm.exception.actual)
        self.assertFalse(p.exists())


class HttpTest(unittest.TestCase):
    """HTTP transport (spec §5.7; review PK12)."""

    def test_proxy_credentials_are_sent(self):
        import base64
        from opentideconstants._http import Http
        srv = _Server()
        try:
            proxy = srv.url.replace("http://", "http://us%65r:p%40ss@")
            Http(user_agent="t", proxy=proxy).get("http://data.example.invalid/OTC_x.json")
            self.assertEqual(srv.requests[0][0], "http://data.example.invalid/OTC_x.json")
            self.assertEqual(srv.requests[0][1].get("Proxy-Authorization"),
                             "Basic " + base64.b64encode(b"user:p@ss").decode())
        finally:
            srv.close()

    def test_multi_member_gzip_is_decoded_in_full(self):
        import gzip
        from opentideconstants._http import Http
        body = gzip.compress(b"first ") + gzip.compress(b"second")
        srv = _Server(script={"/x": (200, {"Content-Encoding": "gzip"}, body)})
        try:
            self.assertEqual(Http(user_agent="t").get(srv.url + "x", accept_gzip=True).body, b"first second")
        finally:
            srv.close()

    def test_truncated_gzip_is_retried(self):
        import gzip
        from opentideconstants import _http
        body = gzip.compress(b"x" * 1000)[:-12]
        srv = _Server(script={"/x": (200, {"Content-Encoding": "gzip"}, body)})
        saved = _http.BACKOFF_S
        _http.BACKOFF_S = (0.0, 0.0)
        try:
            with self.assertRaises(otc.NetworkError):
                _http.Http(user_agent="t").get(srv.url + "x", accept_gzip=True)
            self.assertEqual(len(srv.requests), 3)
        finally:
            _http.BACKOFF_S = saved
            srv.close()


class LifecycleTest(unittest.TestCase):
    """close(), swapped-out releases and the automatic update (spec §4.2, §4.3, §5.6, CR D21; review PK13)."""

    def test_queries_after_close_are_io_in_both_modes(self):
        for mode in ("eager", "stream"):
            c = otc.OpenTideConstants(file=str(GOOD / "OTC_20991231.2.jsonl"), mode=mode)
            c.close()
            c.close()  # a second close does nothing
            for call in (lambda: c.station("OTC-T-0001"), lambda: c.stations(), lambda: c.search(name="san"),
                         lambda: c.near(lat=0, lon=0, radius_km=1), lambda: c.attribution(), lambda: c.verify(),
                         lambda: c.cached_releases()):
                with self.assertRaises(otc.FileError, msg=mode) as cm:
                    call()
                self.assertIn("closed", str(cm.exception))

    def test_a_swapped_out_release_is_closed_when_it_is_dropped(self):
        import gc
        import tempfile
        idx = json.loads((FIXTURES / "good" / "OTC_index.json").read_text(encoding="utf-8"))
        script = {"/OTC_latest-f1.json": (200, {}, json.dumps(idx["releases"][1]).encode())}
        srv = _Server(script=script)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                with otc.OpenTideConstants(base_url=srv.url, cache_dir=tmp, mode="stream") as c:
                    fh = c.release._fh
                    del script["/OTC_latest-f1.json"]
                    c.update()
                    gc.collect()
                    self.assertTrue(fh.closed, "the old release's file handle leaks")
        finally:
            srv.close()

    def test_a_read_on_a_handle_closed_under_it_is_io(self):
        # the state a reader sees when close() runs between its closed-check and its read
        c = otc.OpenTideConstants(file=str(GOOD / "OTC_20991231.2.jsonl"), mode="stream")
        c.release._fh.close()
        with self.assertRaises(otc.FileError):
            c.release.station("OTC-T-0001")
        c.close()

    def test_auto_update_does_not_run_after_close_and_non_sdk_errors_do_not_escape(self):
        import time
        c = otc.OpenTideConstants(file=str(GOOD / "OTC_20991231.2.jsonl"))
        c._file = None  # behave as a latest client for the automatic update
        c._auto_update, c._update_interval = True, 0.001

        def boom():
            raise RuntimeError("not an SDK error")
        c._update = boom
        time.sleep(0.01)
        self.assertEqual(c.station("OTC-T-0001").station_id, "OTC-T-0001")
        c.close()
        c._update = lambda: self.fail("auto-update ran after close")
        time.sleep(0.01)
        c._maybe_auto_update()


class DownloadTest(unittest.TestCase):
    """download() writes all of a release or nothing (spec §4.3.2; review PK14)."""

    def test_offline_with_a_partial_cache_writes_nothing(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            srv = _Server()
            try:
                otc.OpenTideConstants(base_url=srv.url, cache_dir=tmp + "/c", mode="stream").close()
            finally:
                srv.close()
            out = Path(tmp) / "out"
            with otc.OpenTideConstants(cache_dir=tmp + "/c", offline=True, mode="stream") as c:
                with self.assertRaises(otc.OfflineError):
                    c.download("20991231.2", to=str(out), formats=["jsonl", "json.gz"])
            self.assertEqual(sorted(p.name for p in out.iterdir()) if out.exists() else [], [])


class DownloadAllOrNothingTest(unittest.TestCase):
    """download(): the network-error fallback of latest (CR D22) and all-or-nothing renames (CR2 DR17; spec §4.3.2)."""

    D = "20991231.2"

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cache = str(self.root / "cache")
        self.out = self.root / "out"
        # a 200 pointer that is not JSON is a network error at once (spec §5.2 step 5), with no retry
        self.script = {"/not-used": (404, {}, b"")}  # not empty: _Server keeps this dict, and fail_pointer adds to it
        self.srv = _Server(script=self.script)

    def tearDown(self):
        self.srv.close()
        self.tmp.cleanup()

    def names(self):
        return [f"OTC_{self.D}.jsonl", f"OTC_{self.D}.meta.json", f"OTC_{self.D}.sha256"]

    def fail_pointer(self):
        for n in ("/OTC_latest-f1.json", "/OTC_latest.json"):
            self.script[n] = (200, {"Content-Type": "text/html"}, b"<html>captive portal</html>")

    def test_latest_with_a_network_error_writes_the_newest_cached_release(self):
        with otc.OpenTideConstants(base_url=self.srv.url, cache_dir=self.cache) as c:
            self.fail_pointer()
            written = c.download(to=str(self.out))
        self.assertEqual(sorted(Path(p).name for p in written), self.names())
        for n in self.names():
            self.assertEqual((self.out / n).read_bytes(), (GOOD / n).read_bytes())

    def test_latest_with_a_network_error_and_raise_raises(self):
        with otc.OpenTideConstants(base_url=self.srv.url, cache_dir=self.cache, on_network_error="raise") as c:
            self.fail_pointer()
            with self.assertRaises(otc.NetworkError):
                c.download(to=str(self.out))
        self.assertFalse(self.out.exists() and any(self.out.iterdir()))

    def test_latest_with_a_network_error_and_no_cached_release_raises(self):
        with otc.OpenTideConstants(file=str(GOOD / f"OTC_{self.D}.jsonl"), base_url=self.srv.url,
                                   cache_dir=self.cache) as c:
            self.fail_pointer()
            with self.assertRaises(otc.NetworkError):
                c.download(to=str(self.out))

    def _replaced_originals(self, c):
        """Download, then change the .jsonl and the .meta.json in `out`; returns their changed bytes."""
        c.download(self.D, to=str(self.out))
        before = {}
        for n in self.names()[:2]:
            (self.out / n).write_bytes(b"changed " + n.encode())
            before[n] = (self.out / n).read_bytes()
        return before

    def test_a_rename_that_fails_restores_every_original(self):
        from unittest import mock
        real = os.replace
        meta = f"OTC_{self.D}.meta.json"

        def replace(src, dst):
            # the new .meta.json cannot be renamed in (the .jsonl went first)
            if Path(dst).name == meta and Path(src).name.startswith(".tmp-") and not Path(src).name.startswith(".tmp-bak-"):
                raise PermissionError(13, "injected", str(dst))
            return real(src, dst)
        with otc.OpenTideConstants(base_url=self.srv.url, cache_dir=self.cache) as c:
            before = self._replaced_originals(c)
            with mock.patch("os.replace", replace), self.assertRaises(otc.FileError) as cm:
                c.download(self.D, to=str(self.out), overwrite=True)
        self.assertEqual(cm.exception.path, str(self.out / meta))
        for n, data in before.items():
            self.assertEqual((self.out / n).read_bytes(), data, f"{n} was not restored")
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), self.names())

    def test_a_restore_that_fails_too_lists_the_paths_that_changed(self):
        from unittest import mock
        real = os.replace
        jsonl, meta = f"OTC_{self.D}.jsonl", f"OTC_{self.D}.meta.json"

        def replace(src, dst):
            s, d = Path(src).name, Path(dst).name
            if d == meta and s.startswith(".tmp-") and not s.startswith(".tmp-bak-"):
                raise PermissionError(13, "injected", str(dst))
            if d == jsonl and s.startswith(".tmp-bak-"):  # the original .jsonl cannot be put back
                raise PermissionError(13, "injected restore", str(dst))
            return real(src, dst)
        with otc.OpenTideConstants(base_url=self.srv.url, cache_dir=self.cache) as c:
            before = self._replaced_originals(c)
            with mock.patch("os.replace", replace), self.assertRaises(otc.FileError) as cm:
                c.download(self.D, to=str(self.out), overwrite=True)
        self.assertIn(str(self.out / jsonl), str(cm.exception))
        self.assertEqual((self.out / meta).read_bytes(), before[meta])


class PrunePartialFailureTest(unittest.TestCase):
    """prune stops at the first release it cannot remove; CacheError.removed lists the ones removed before it
    (CR2 DR18; spec §4.3)."""

    def test_the_cache_error_reports_what_was_removed(self):
        import tempfile
        from unittest import mock
        with tempfile.TemporaryDirectory() as tmp:
            srv = _Server()
            try:
                for d in ("20991231", "20991231.2"):
                    otc.OpenTideConstants(release=d, base_url=srv.url, cache_dir=tmp).close()
                with otc.OpenTideConstants(release="20991231.2", base_url=srv.url, cache_dir=tmp) as c:
                    listed = ["20991231.2", "20991230", "20991231", "20991229"]
                    calls = []

                    def remove(ds):
                        calls.append(ds)
                        if ds == "20991231":
                            raise otc.CacheError("cannot remove 20991231")
                        return True
                    with mock.patch.object(c._cache, "cached", return_value=listed), \
                            mock.patch.object(c._cache, "remove_release", side_effect=remove), \
                            self.assertRaises(otc.CacheError) as cm:
                        c.prune(keep=0)
            finally:
                srv.close()
        self.assertEqual(calls, ["20991230", "20991231"])  # stops at the first failure
        self.assertEqual(list(cm.exception.removed), ["20991230"])


class AttributionTest(RepeatedIdsTest):
    """Attribution edge cases (spec §4.6, CR D2; review PK15)."""

    def test_null_provider_prints_the_attribution_alone_and_is_never_merged(self):
        def edit(m):
            for x in m["licences"][:2]:
                x["provider"] = None
        with otc.OpenTideConstants(file=self.write(edit_meta=edit)) as c:
            text = c.attribution()
            self.assertNotIn("None", text)
            for x in c.release.licences[:2]:
                self.assertIn(x.attribution, text)

    def test_a_station_from_another_release_is_invalid_argument(self):
        with otc.OpenTideConstants(file=str(FIXTURES / "v1" / "OTC_20991231.3.jsonl")) as other:
            foreign = other.stations()[0]
        with otc.OpenTideConstants(file=str(GOOD / "OTC_20991231.2.jsonl")) as c:
            with self.assertRaises(otc.InvalidArgumentError):
                c.attribution([foreign])


class ReadmeTest(unittest.TestCase):
    """The README quickstart runs as written against the fixture server (review PK16 P72)."""

    def test_readme_quickstart_runs(self):
        import re
        import subprocess
        import tempfile
        text = (ROOT / "python" / "README.md").read_text(encoding="utf-8")
        blocks = re.findall(r"```python\n(.*?)```", text, re.S)
        self.assertTrue(blocks)
        env = {k: v for k, v in os.environ.items() if not k.startswith("OPENTIDECONSTANTS_")}
        if not os.environ.get("OTC_TEST_INSTALLED"):
            env["PYTHONPATH"] = str(ROOT / "python" / "src")
        for script in (blocks[0], blocks[0].replace('"san fran"', '"no such place"')):
            srv = _Server()
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    env.update(OPENTIDECONSTANTS_BASE_URL=srv.url, OPENTIDECONSTANTS_CACHE_DIR=tmp)
                    r = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, text=True,
                                       timeout=60)
                    self.assertEqual(r.returncode, 0, r.stderr)
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
