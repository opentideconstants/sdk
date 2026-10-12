"""The prediction fixtures (K2b-fixtures; prediction spec revision 27, section 6.5).

- the roots exist, validate as the reference reader reads them, and knc keeps its hashes;
- knc-predict is knc plus exactly the listed additions, and each bad prediction fixture is the prediction release with
  exactly its one change;
- the design check: a brute-force scan at 0.01 s (5 s for the counting cases) of h' (or W, W') around each designed
  event, with the fixture's own astro table, confirms each stated design (spec 6.5, 4.6, 4.7).

Run: uv run --with "pytest>=8,<9" --with jsonschema==4.25.1 --with rfc3339-validator==0.1.4 --with rfc3986-validator==0.1.1 \\
     python -m pytest conformance/tests/test_build_fixtures_predict.py
"""
from __future__ import annotations

import copy
import datetime
import hashlib
import json
import math
import sys
from pathlib import Path

import pytest

from _util import CONF

sys.path.insert(0, str(CONF / "tools"))
import build_fixtures as bf  # noqa: E402

FIX = CONF / "fixtures"
LEAF = 360 / 512
STEP = 360


# --------------------------------------------------------------------------- an evaluator of spec 4.3 and 4.4

def ts(iso):
    return int(datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


def year_start(y):
    return int(datetime.datetime(y, 1, 1, tzinfo=datetime.timezone.utc).timestamp())


def year_of(t):
    return datetime.datetime.fromtimestamp(math.floor(t), tz=datetime.timezone.utc).year


def reduce_deg(x):
    r = x - 360.0 * math.floor(x / 360.0)
    return 0.0 if r == 360.0 else r


class Sum:
    """sum_k F_k A_k cos(omega_k Delta + A_k - g_k) over (name, amplitude, phase) terms, with a release's table."""

    def __init__(self, table, terms):
        self.t, self.terms = table, terms

    def _c(self, y):
        i = y - self.t["first_year"]
        assert 0 <= i <= self.t["last_year"] - self.t["first_year"], f"year {y} outside the table"
        for name, amp, ph in self.terms:
            r = self.t["constituents"][name]
            yield r["speed_deg_per_hour"], r["v0u_deg"][i], r["f"][i] * amp, ph

    def h(self, t, y=None):
        y = y or year_of(t)
        d = (t - year_start(y)) / 3600.0
        return sum(fa * math.cos(reduce_deg(w * d + a - g) * math.pi / 180) for w, a, fa, g in self._c(y))

    def dh(self, t, y=None):
        y = y or year_of(t)
        d = (t - year_start(y)) / 3600.0
        return -sum(fa * w * math.pi / 180 * math.sin(reduce_deg(w * d + a - g) * math.pi / 180) for w, a, fa, g in self._c(y))


def scan(f, t0, t1, dt, y=None):
    """Sign changes of f(t, y) on [t0, t1] at step dt, each refined to 1e-6 s: [(r, 'down'|'up')]."""
    out = []
    n = int(round((t1 - t0) / dt))
    prev_t, prev = t0, f(t0, y)
    for k in range(1, n + 1):
        t = t0 + k * dt
        v = f(t, y)
        if (prev > 0 and v <= 0) or (prev < 0 and v >= 0):
            kind = "down" if prev > 0 else "up"
            a, b = prev_t, t
            while b - a > 1e-6:
                m = (a + b) / 2
                fm = f(m, y)
                if (fm > 0 if kind == "down" else fm < 0):
                    a = m
                else:
                    b = m
            out.append(((a + b) / 2, kind))
        prev_t, prev = t, v
    return out


@pytest.fixture(scope="module")
def doc():
    return json.loads((FIX / "predict" / f"OTC_{bf.PREDICT_D}.json").read_bytes())


def table(doc, tid):
    return next(t for t in doc["astro_tables"] if t["astro_table_id"] == tid)


def set_sum(doc, set_id, tid=bf.ASTRO_A):
    st = next(s for s in doc["stations"] if s["station_id"] == set_id.split("/")[0])
    cs = next(c for c in st["constant_sets"] if c["set_id"] == set_id)
    return Sum(table(doc, tid), [(c["name"], c["amplitude_m"], c["phase_deg"]) for c in cs["constituents"]])


def bin_w(doc, set_id, n, tid=bf.ASTRO_A):
    """(W(t, y), W'(t, y)) of a current bin: sigma (mean_major + major sum), spec 4.7."""
    st = next(s for s in doc["stations"] if s["station_id"] == set_id.split("/")[0])
    b = next(b for c in st["constant_sets"] if c["set_id"] == set_id for b in c["current_bins"] if b["bin"] == n)
    s = Sum(table(doc, tid), [(c["name"], c["major_amplitude_ms"], c["major_phase_deg"]) for c in b["constituents"]])
    flood = b.get("mean_flood_dir_deg")
    sigma = 1 if flood is None or math.cos(math.radians(b["azimuth_deg"] - flood)) >= 0 else -1
    mean = b.get("mean_major_ms", 0.0)
    return (lambda t, y=None: sigma * (mean + s.h(t, y))), (lambda t, y=None: sigma * s.dh(t, y))


def in_step(r):
    return r - math.floor(r / STEP) * STEP


def leaf(r):
    return math.floor(r / STEP), int(in_step(r) / LEAF)


def isolated(roots, chosen, t0, t1, f, gap=1.0):
    """No root of f outside the chosen ones within gap s of them (scanned over [t0, t1])."""
    others = [r for r, _ in roots if all(abs(r - c) > 1e-3 for c, _ in chosen)]
    return all(abs(r - c) >= gap for r in others for c, _ in chosen)


# --------------------------------------------------------------------------- roots, hashes, one change each

# knc's files at SDK 2eeb589 (K2b-fixtures' base): knc-predict is a new root, so knc keeps its hashes (spec 6.5).
KNC_SHA256 = "OTC_20991231.2.sha256"


def test_prediction_roots_in_manifest():
    manifest = json.loads((FIX / "fixtures.json").read_bytes())
    roots = {f["root"]: f for f in manifest["fixtures"]}
    assert roots["predict"]["releases"] == [bf.PREDICT_D] and roots["predict"]["expect"] == "load"
    assert roots["knc-predict"]["releases"] == ["20991231.2"] and roots["knc-predict"]["expect"] == "load"
    for name in ("no-astro-table", "unsupported-constituent", "astro-negative-speed", "astro-negative-speed-unused",
                 "astro-short-v0u", "extremes-negative-amplitude", "current-reference-missing", "current-reference-removed",
                 "unknown-adjusted-type"):
        assert roots[f"predict-bad/{name}"]["expect"] == "load", name


@pytest.mark.parametrize("root,release,tolerated", [
    ("predict", bf.PREDICT_D, False), ("knc-predict", "20991231.2", False),
    *[(f"predict-bad/{n}", bf.PREDICT_D, True) for n, _, _ in bf.PREDICT_BAD]])
def test_prediction_roots_load_in_the_reference_reader(root, release, tolerated):
    got = bf.open_release(FIX / root, release, bf.load_schemas(bf.VENDORED_SCHEMAS))
    assert bool(got["unknown_fields"]) == tolerated, got["unknown_fields"]


def test_predict_release_validates_strictly():
    """The prediction release is plain format 1.0 under the pinned schema, with every cross-reference resolved."""
    schemas = bf.load_schemas(bf.VENDORED_SCHEMAS)
    d = bf.predict_doc()
    assert [e.message for e in bf.validator(schemas["1.0"]).iter_errors(d)] == []
    assert bf.cross_ref_errors(d) == [] and bf.time_range_errors(d) == []
    k = bf.knc_predict_doc()
    assert [e.message for e in bf.validator(schemas["1.0"]).iter_errors(k)] == []
    assert bf.cross_ref_errors(k) == []


@pytest.mark.parametrize("name", [n for n, _, _ in bf.PREDICT_BAD if n != "unknown-adjusted-type"])
def test_bad_prediction_fixture_is_invalid_without_the_tolerance(name):
    """Each bad prediction fixture fails the schema or the build's cross-checks (no-astro-table: the schema), so the
    defect is real; the SDKs still load it (their tolerance is the reader's tolerate_prediction)."""
    schemas = bf.load_schemas(bf.VENDORED_SCHEMAS)
    d = next(docs for n, _, docs in bf.PREDICT_BAD if n == name)()[0]
    errs = [e.message for e in bf.validator(schemas["1.0"]).iter_errors(d)] or bf.cross_ref_errors(d)
    assert errs, name
    if name == "no-astro-table":
        assert [e.message for e in bf.validator(schemas["1.0"]).iter_errors(d)], "no-astro-table must fail validation"


def test_knc_keeps_its_hashes():
    """knc's .sha256 list at the base (2eeb589): the committed one is unchanged, and knc_doc still makes it."""
    committed = (FIX / "knc" / KNC_SHA256).read_bytes()
    assert hashlib.sha256(committed).hexdigest() == "fe1de2692dffd5afb5c3387aa089ef9fcc1e159528bb5b8f02310834c6b5cea4"
    assert committed == bf.sha256_list(bf.release_files(bf.knc_doc(), FIX / "knc"))


def diff_paths(a, b, path=""):
    """The JSON paths where a and b differ (a list of strings)."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = []
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append(f"{path}/{k}")
            else:
                out += diff_paths(a[k], b[k], f"{path}/{k}")
        return out
    if isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        return [p for i, (x, y) in enumerate(zip(a, b)) for p in diff_paths(x, y, f"{path}/{i}")]
    return [] if a == b else [path]


def station_index(d, sid):
    return next(i for i, s in enumerate(d["stations"]) if s["station_id"] == sid)


def test_knc_predict_is_knc_plus_the_additions():
    knc = json.loads((FIX / "knc" / "OTC_20991231.2.json").read_bytes())
    kp = json.loads((FIX / "knc-predict" / "OTC_20991231.2.json").read_bytes())
    assert [s["station_id"] for s in kp["stations"]] == [s["station_id"] for s in knc["stations"]] + ["OTC-T-0191", "OTC-T-0192"]
    kp_same = dict(kp, stations=kp["stations"][:-2])
    i = {sid: station_index(knc, sid) for sid in ("OTC-T-0181", "OTC-T-0185", "OTC-T-0186", "OTC-T-0187", "OTC-T-0188",
                                                  "OTC-T-0190")}
    expected = {f"/stations/{i['OTC-T-0181']}/constant_sets/0/datum", f"/stations/{i['OTC-T-0185']}/constant_sets/0/datum"}
    for sid in ("OTC-T-0186", "OTC-T-0187", "OTC-T-0188", "OTC-T-0190"):
        for k in ("time_offset_high_min", "height_offset_high", "height_offset_low"):   # knc's low time offset is 20 already
            expected.add(f"/stations/{i[sid]}/subordinate_offsets/{k}")
    assert set(diff_paths(knc, kp_same)) == expected
    for sid in ("OTC-T-0186", "OTC-T-0187", "OTC-T-0188", "OTC-T-0190"):
        o = kp["stations"][i[sid]]["subordinate_offsets"]
        assert (o["time_offset_high_min"], o["time_offset_low_min"], o["height_offset_high"], o["height_offset_low"],
                o["height_adjusted_type"]) == (20, 20, 0.9, 0.9, "R")
        assert o["licence_id"] == knc["stations"][i[sid]]["subordinate_offsets"]["licence_id"]
    for sid in ("OTC-T-0181", "OTC-T-0185"):
        d = kp["stations"][i[sid]]["constant_sets"][0]["datum"]
        assert d["chart_datum"] == "mllw" and d["basis"]["mllw"]["kind"] == "published"
    for st, licence in zip(kp["stations"][-2:], ("nc-test", "noaa")):
        assert st["type"] == "subordinate" and st["constant_sets"] == [] and "subordinate_offsets" not in st
        (co,) = st["current_offsets"]
        assert (co["bin"], co["reference_station_id"], co["reference_bin"], co["licence_id"]) == (1, "OTC-T-0181", 1, licence)
        assert all(co[k] is not None for k in ("time_adj_max_flood_min", "time_adj_slack_before_ebb_min", "time_adj_max_ebb_min",
                                               "time_adj_slack_before_flood_min", "flood_amp_ratio", "ebb_amp_ratio"))
    z = next(c for c in kp["stations"][i["OTC-T-0181"]]["constant_sets"] if c["set_id"] == "OTC-T-0181/z-current")
    assert [b["bin"] for b in z["current_bins"]] == [1]


BAD_PATHS = {
    "no-astro-table": None,   # checked by hand below
    "unsupported-constituent": {"/astro_tables/0/constituents/M4"},
    "astro-negative-speed": {"/astro_tables/0/constituents/M2/speed_deg_per_hour"},
    "astro-negative-speed-unused": {"/astro_tables/0/constituents/MN4/speed_deg_per_hour"},
    "astro-short-v0u": {"/astro_tables/0/constituents/M2/v0u_deg"},
    "extremes-negative-amplitude": None,
    "unknown-adjusted-type": None,
    "current-reference-missing": None,
    "current-reference-removed": None,
}


@pytest.mark.parametrize("name", list(BAD_PATHS))
def test_bad_prediction_fixture_has_one_change(name, doc):
    bad = json.loads((FIX / "predict-bad" / name / f"OTC_{bf.PREDICT_D}.json").read_bytes())
    paths = set(diff_paths(doc, bad))
    if name == "no-astro-table":
        # exactly: table A removed (the astro_tables list changes length, so the whole list differs), the local
        # convention's astro_table_id removed, and nothing else; table B is unchanged
        conv = next(i for i, c in enumerate(doc["conventions"]) if c["convention_id"] == bf.CONV_LOCAL)
        assert paths == {"/astro_tables", f"/conventions/{conv}/astro_table_id"}
        assert bad["astro_tables"] == [table(doc, bf.ASTRO_B)]
        assert "astro_table_id" not in bad["conventions"][conv]
        assert [c for i, c in enumerate(bad["conventions"]) if i != conv] == [c for i, c in enumerate(doc["conventions"]) if i != conv]
    elif name == "extremes-negative-amplitude":
        assert paths == {f"/stations/{station_index(doc, 'OTC-P-0005')}/constant_sets/0/constituents/0/amplitude_m"}
        assert bad["stations"][station_index(doc, "OTC-P-0005")]["constant_sets"][0]["constituents"][0]["amplitude_m"] == -1.0
    elif name in ("current-reference-missing", "current-reference-removed"):
        assert paths == {f"/stations/{station_index(doc, 'OTC-P-0059')}/current_offsets/0/reference_station_id"}
        ref = bad["stations"][station_index(doc, "OTC-P-0059")]["current_offsets"][0]["reference_station_id"]
        status = {s["station_id"]: s["status"] for s in bad["stations"]}
        assert (ref, status.get(ref)) == (("OTC-P-9999", None) if name == "current-reference-missing" else ("OTC-P-0097", "removed"))
    elif name == "unknown-adjusted-type":
        want = {"/format_version", "/future_top_level", "/release/future_release_field"}
        want |= {f"/stations/{station_index(doc, s)}/subordinate_offsets/height_adjusted_type"
                 for s in ("OTC-P-0030", "OTC-P-0035", "OTC-P-0049")}
        assert paths == want
    else:
        assert paths == BAD_PATHS[name]
    if name == "astro-short-v0u":
        assert len(table(bad, bf.ASTRO_A)["constituents"]["M2"]["v0u_deg"]) == 30


def test_mn4_is_in_no_set(doc):
    """astro-negative-speed's second sub-case puts the negative speed on a row that no set uses."""
    used = {c["name"] for s in doc["stations"] for cs in s.get("constant_sets", []) for c in cs["constituents"]
            + [x for b in cs.get("current_bins", []) for x in b["constituents"]]}
    assert "MN4" in table(doc, bf.ASTRO_A)["constituents"] and "MN4" not in used


# --------------------------------------------------------------------------- the design check

def test_single_constituent_count(doc):
    """extremes-single-constituent: 116 extremes from 2010-03-01 to 2010-03-31 (5 s scan), none within 1 s of an
    edge, none within 10 s of another. extremes-negative-amplitude: the same count, highs and lows swapped."""
    t0, t1 = ts(bf.PW["single"][0]), ts(bf.PW["single"][1])
    s = set_sum(doc, "OTC-P-0005/noaa")
    rs = scan(lambda t, y: s.dh(t), t0, t1, 5.0)
    assert len(rs) == 116
    assert rs[0][0] - t0 > 1 and t1 - rs[-1][0] > 1
    assert min(b[0] - a[0] for a, b in zip(rs, rs[1:])) > 10
    neg = Sum(s.t, [("M2", -1.0, s.terms[0][2])])
    rn = scan(lambda t, y: neg.dh(t), t0, t1, 5.0)
    assert len(rn) == 116 and all(a[1] != b[1] and abs(a[0] - b[0]) < 1e-3 for a, b in zip(rs, rn))


@pytest.mark.parametrize("set_id,key", [("OTC-P-0012/m2-5m", "large-m2"), ("OTC-P-0012/m2-7m5", "large-m2"),
                                        ("OTC-P-0012/k1-40m", "large-k1")])
def test_large_amplitude_windows(doc, set_id, key):
    """The large-amplitude cases: the 5 s sign scan has no root within 1 s of an edge, none within 10 s of another;
    the same counts hold for W' and W of the current bins with the same major amplitudes (OTC-P-0013)."""
    t0, t1 = ts(bf.PW[key][0]), ts(bf.PW[key][1])
    s = set_sum(doc, set_id, bf.ASTRO_B)
    rs = scan(lambda t, y: s.dh(t), t0, t1, 5.0)
    assert rs and rs[0][0] - t0 > 1 and t1 - rs[-1][0] > 1
    assert all(b[0] - a[0] > 10 for a, b in zip(rs, rs[1:]))
    n = {"OTC-P-0012/m2-5m": 1, "OTC-P-0012/m2-7m5": 2, "OTC-P-0012/k1-40m": 3}[set_id]
    w, dw = bin_w(doc, "OTC-P-0013/noaa", n, bf.ASTRO_B)
    assert len(scan(lambda t, y: dw(t), t0, t1, 5.0)) == len(rs)
    zs = scan(lambda t, y: w(t), t0, t1, 5.0)
    assert zs and zs[0][0] - t0 > 1 and t1 - zs[-1][0] > 1 and all(b[0] - a[0] > 10 for a, b in zip(zs, zs[1:]))


def test_close_high_low(doc):
    """A high and a low about 3 minutes apart in one 6-minute step, and nothing else in that step."""
    s = set_sum(doc, "OTC-P-0008/noaa")
    g = ts(bf.PW["close-high-low"][0])
    rs = scan(lambda t, y: s.dh(t), g, g + STEP, 0.01)
    assert [k for _, k in rs] == ["down", "up"] and 170 < rs[1][0] - rs[0][0] < 190
    assert ts(bf.PW["close-high-low"][1]) == g + STEP


def test_close_high_low_high(doc):
    s = set_sum(doc, "OTC-P-0009/noaa")
    g = ts(bf.PW["close-high-low-high"][0])
    rs = scan(lambda t, y: s.dh(t), g, g + STEP, 0.01)
    assert [k for _, k in rs] == ["down", "up", "down"]
    assert all(b[0] - a[0] >= 1 for a, b in zip(rs, rs[1:]))


def test_double_high(doc):
    s = set_sum(doc, "OTC-P-0010/noaa")
    t0, t1 = ts(bf.PW["double-high"][0]), ts(bf.PW["double-high"][1])
    rs = scan(lambda t, y: s.dh(t), t0, t1, 0.01)
    assert [k for _, k in rs] == ["down", "up", "down"]
    assert abs(rs[2][0] - rs[0][0] - 1200) < 30


def sub_second(doc, set_id, centre, kinds, span):
    s = set_sum(doc, set_id)
    c = ts(centre[:19] + "Z") + float(centre[19:-1] or 0)
    rs = scan(lambda t, y: s.dh(t), c - 30, c + 30, 0.01)
    near = [x for x in rs if abs(x[0] - c) < 1.0]
    assert [k for _, k in near] == kinds, near
    assert near[-1][0] - near[0][0] < span
    assert isolated(rs, near, c - 30, c + 30, None)
    assert len({leaf(r) for r, _ in near}) == len(near), "each root in its own minimum leaf"
    return s, near


def test_sub_second_pair(doc):
    """A high and a low 0.8 s apart, in different minimum leaves, on a rising tide: an even cluster."""
    s, near = sub_second(doc, "OTC-P-0011/pair", bf.PW["sub-second-pair"][2], ["down", "up"], 0.9)
    assert abs(near[1][0] - near[0][0] - 0.8) < 0.02
    assert s.dh(near[0][0] - 5) > 0 and s.dh(near[1][0] + 5) > 0


def test_sub_second_triple_second_higher(doc):
    s, near = sub_second(doc, "OTC-P-0011/triple-higher", bf.PW["sub-second-triple-higher"][2], ["down", "up", "down"], 0.9)
    h1, h3 = s.h(near[0][0]), s.h(near[2][0])
    assert h3 - h1 > 1e-10
    # the bisection stops at 0.01 s: the order of the two highs holds anywhere in that bracket
    assert min(s.h(near[2][0] + e) for e in (-0.005, 0.005)) > max(s.h(near[0][0] + e) for e in (-0.005, 0.005))


def test_sub_second_triple_equal(doc):
    """The same shape, scaled down, above a zero 1.0 m below the mean level: the two highs' heights (datum zero) are
    the same double, anywhere in the 0.01 s bisection bracket, so the tie rule decides."""
    s, near = sub_second(doc, "OTC-P-0011/triple-equal", bf.PW["sub-second-triple-equal"][2], ["down", "up", "down"], 0.9)
    msl = next(c for st in doc["stations"] for c in st.get("constant_sets", []) if c["set_id"] == "OTC-P-0011/triple-equal")["datum"]["msl_offset_m"]
    heights = {msl + s.h(r + e) for r in (near[0][0], near[2][0]) for e in (-0.005, 0.0, 0.005)}
    assert len(heights) == 1


def test_year_boundary_step(doc):
    """A high within 6 minutes before 2010-01-01, in the old year's last step, on the same side of T under both years'
    tables (no reconciliation), with a height that differs between the two tables."""
    s = set_sum(doc, "OTC-P-0006/noaa")
    T = year_start(2010)
    old = scan(lambda t, y: s.dh(t, 2009), T - 1800, T + 1800, 0.01)
    new = scan(lambda t, y: s.dh(t, 2010), T - 1800, T + 1800, 0.01)
    assert [k for _, k in old] == ["down"] and T - 360 <= old[0][0] < T
    assert [k for _, k in new] == ["down"] and new[0][0] < T
    assert (s.dh(T, 2009) > 0) == (s.dh(T, 2010) > 0)
    assert abs(s.h(old[0][0], 2009) - s.h(old[0][0], 2010)) > 1e-3


def test_new_year_missed_and_doubled(doc):
    """2010: the high falls after T under the old table and before T under the new one (missed). 2011: at T - 10 min
    under the old table and T + 8 min under the new one, and the new one is higher (doubled; the higher is kept)."""
    s = set_sum(doc, "OTC-P-0007/noaa")
    T = year_start(2010)
    (ro, ko), = scan(lambda t, y: s.dh(t, 2009), T - 3600, T + 3600, 0.01)
    (rn, kn), = scan(lambda t, y: s.dh(t, 2010), T - 3600, T + 3600, 0.01)
    assert ko == kn == "down" and T < ro < T + 1200 and T - 1200 < rn < T
    assert s.dh(T, 2009) > 0 > s.dh(T, 2010)
    T = year_start(2011)
    (ro, ko), = scan(lambda t, y: s.dh(t, 2010), T - 3600, T + 3600, 0.01)
    (rn, kn), = scan(lambda t, y: s.dh(t, 2011), T - 3600, T + 3600, 0.01)
    assert ko == kn == "down" and abs(ro - (T - 600)) < 30 and abs(rn - (T + 480)) < 60
    assert s.dh(T, 2010) < 0 < s.dh(T, 2011)
    assert s.h(rn, 2011) > s.h(ro, 2010) + 1e-3


def test_close_slacks(doc):
    w, dw = bin_w(doc, "OTC-P-0020/noaa", 1)
    g = ts(bf.PW["close-slacks"][0])
    zs = scan(lambda t, y: w(t), g, g + STEP, 0.01)
    assert [k for _, k in zs] == ["up", "down"] and abs(zs[1][0] - zs[0][0] - 120) < 3


@pytest.mark.parametrize("n,kinds,span", [(2, ["up", "down"], 0.7), (3, ["up", "down", "up"], 0.9),
                                          (4, ["up", "down", "up", "down", "up"], 4.0)])
def test_sub_second_slacks(doc, n, kinds, span):
    """Two slacks 0.6 s apart (in two leaves); three within 0.9 s flood-ebb-flood (three leaves); five in one cluster,
    each 0.703125 s to 1 s after the one before, so each is a candidate in its own leaf and the index rule
    2 * floor((n - 1) / 4) picks index 2 (spec 4.7)."""
    w, dw = bin_w(doc, "OTC-P-0020/noaa", n)
    c = ts(bf.PW["sub-second-slacks"][n - 2][:19] + "Z") + float(bf.PW["sub-second-slacks"][n - 2][19:-1])
    zs = scan(lambda t, y: w(t), c - 20, c + 20, 0.002 if n < 4 else 0.01)
    near = [z for z in zs if abs(z[0] - c) < (1.0 if n < 4 else 2.5)]
    assert [k for _, k in near] == kinds and near[-1][0] - near[0][0] < span
    assert isolated(zs, near, c - 20, c + 20, None)
    leaves = [leaf(r) for r, _ in near]
    if n == 2:
        assert abs(near[1][0] - near[0][0] - 0.6) < 0.02 and len(set(leaves)) == 2
    elif n == 3:
        assert len(set(leaves)) == 3
    else:
        gaps = [b[0] - a[0] for a, b in zip(near, near[1:])]
        assert all(LEAF + 0.05 < g < 0.95 for g in gaps), gaps
        assert len(set(leaves)) == 5
        assert all(min(in_step(r) % LEAF, LEAF - in_step(r) % LEAF) > 0.03 for r, _ in near), "no root near a leaf edge"


def test_new_year_slacks(doc):
    """2012: a slack (W rising) after T under the old table and before T under the new one (bin 1, missed); before T
    under the old one and after T under the new one, less than an hour apart (bin 2, doubled)."""
    T = year_start(2012)
    w, _ = bin_w(doc, "OTC-P-0021/noaa", 1)
    (ro, ko), = scan(lambda t, y: w(t, y), T - 3600, T + 3600, 0.05, 2011)
    (rn, kn), = scan(lambda t, y: w(t, y), T - 3600, T + 3600, 0.05, 2012)
    assert ko == kn == "up" and T < ro < T + 1800 and T - 1800 < rn < T
    w, _ = bin_w(doc, "OTC-P-0021/noaa", 2)
    (ro, ko), = scan(lambda t, y: w(t, y), T - 3600, T + 3600, 0.05, 2011)
    (rn, kn), = scan(lambda t, y: w(t, y), T - 3600, T + 3600, 0.05, 2012)
    assert ko == kn == "up" and T - 1800 < ro < T < rn < T + 1800 and rn - ro < 3600


def test_weak_current(doc):
    """current-events-weak: the window has a local maximum of W below zero (not reported) and a strong flood."""
    w, dw = bin_w(doc, "OTC-P-0019/noaa", 1)
    t0, t1 = ts(bf.PW["current-events-weak"][0]), ts(bf.PW["current-events-weak"][1])
    peaks = [(r, k) for r, k in scan(lambda t, y: dw(t), t0, t1, 30.0) if k == "down"]
    assert any(w(r) < 0 for r, _ in peaks) and any(w(r) > 0 for r, _ in peaks)


def test_folded_new_year_table_step(doc):
    """subordinate-folded-new-year: M2's f steps at 2013, so the folded curve's year rule changes the heights."""
    m2 = table(doc, bf.ASTRO_A)["constituents"]["M2"]["f"]
    assert abs(m2[2013 - 2000] - m2[2012 - 2000]) > 0.02


def test_currents_direction_north(doc):
    """currents-direction-north: azimuth 180 and U < 0 at every sample of the case window, so the water flows toward
    north (E = U sin 180 is a tiny number of either sign, N = -U > 0): direction 0.0, never 360.0."""
    st = next(s for s in doc["stations"] if s["station_id"] == "OTC-P-0017")
    b = next(b for b in st["constant_sets"][0]["current_bins"] if b["bin"] == 5)
    s = Sum(table(doc, bf.ASTRO_A), [(c["name"], c["major_amplitude_ms"], c["major_phase_deg"]) for c in b["constituents"]])
    t0, t1 = ts(bf.PW["currents"][0]), ts(bf.PW["currents"][1])
    assert b["azimuth_deg"] == 180.0 and all(c["minor_amplitude_ms"] == 0 for c in b["constituents"]) and "mean_minor_ms" not in b
    assert all(b["mean_major_ms"] + s.h(t) < 0 for t in range(t0, t1, 600))




# --------------------------------------------------------------------------- predict_calls.json

# Every prediction case that spec 6.5 (revision 28) names, spelled as the call ids are without "predict-" and with "/"
# as "-". Each must be exactly one call id: no prefix matching, so a missing case is never covered by a longer one.
SPEC_CASES = """heights-basic heights-at heights-step-alignment heights-empty-window heights-start-after-stop heights-step-zero
heights-year-boundary heights-leap-day heights-naive-datetime datum-mean-level datum-zero datum-named datum-chart
datum-unavailable no-constants quantity-mismatch unsupported-convention unsupported-constituent no-astro-table
time-out-of-range local-phase-convention extremes-basic extremes-window-edges extremes-single-constituent
extremes-large-amplitude current-peaks-large-amplitude slacks-large-amplitude extremes-close-high-low
extremes-close-high-low-high extremes-double-high extremes-sub-second extremes-year-boundary-step extremes-new-year-missed
extremes-new-year-doubled currents-series currents-mean currents-minor-sign currents-flood-sign currents-direction-null
currents-direction-north currents-default-bin currents-explicit-bin bin-not-found bin-number-too-large current-events-basic
current-events-weak current-events-close-slacks current-events-sub-second-slacks current-events-new-year-slack
subordinate-tide-ratio subordinate-tide-additive subordinate-tide-missing-offsets subordinate-tide-order-swap
subordinate-tide-fractional-offset subordinate-series subordinate-reference-no-chart-datum subordinate-current
subordinate-current-null-adjustment subordinate-folded-ratio subordinate-folded-additive subordinate-folded-extremes
subordinate-folded-new-year subordinate-differing-offsets-series subordinate-zero-ratio subordinate-unknown-adjusted-type
subordinate-order-ratio-before-extremes-only subordinate-reference-no-usable-set subordinate-current-reference-no-set
local-station-zone local-named-zone local-unknown-zone local-missing-dependency local-missing-tzdir local-not-built
local-format datums-list datums-all-sets datums-ranges datums-ranges-mixed-kinds datum-otc-key datum-subordinate-named
datum-vertical-zero datum-subordinate-reference-wrong-source datum-subordinate-unpublished-chart astro-values
astro-negative-speed-used-row astro-negative-speed-unused-row astro-negative-speed-short-v0u extremes-negative-amplitude
set-not-found empty-window-out-of-range heights-fractional-instants metadata reference-set-file-order
commercial-only-effective-set commercial-only-explicit-nc-set commercial-only-no-constants commercial-only-offsets-usable
commercial-only-offsets-nc-licence commercial-only-reference-set-nc commercial-only-own-set-wins
commercial-only-current-offsets-nc commercial-only-current-offsets-usable""".split()
# Sub-cases of 6.5 written as cases of their own, and the cases the G-K2b review added (A1-A8), by their call ids.
EXTRA_CASES = {"subordinate-current-reference-no-set-missing", "subordinate-current-reference-removed",
               "current-events-flood-sign", "set-speed", "subordinate-event-datum"}
NOT_BUILT = ["otc_heights", "otc_heights_at", "otc_extremes", "otc_currents", "otc_current_events", "otc_astro_table",
             "otc_astro_equilibrium_argument", "otc_astro_node_factor", "otc_astro_equilibrium_for_year",
             "otc_astro_node_factor_for_year", "otc_astro_valid_range"]
# Revision 28 removed these: a missing or removed subordinate_offsets reference fails to load, so the cases do not exist.
REMOVED = {"subordinate-reference-removed", "datum-subordinate-reference-removed"}
# K2's prediction ops and their arguments (K2 343fbe3, conformance/driver.py OPS): the calls use exactly these.
K2_OPS = {
    "heights": ["station_id", "start", "stop", "step_s", "datum", "set_id"],
    "heights_at": ["station_id", "times", "datum", "set_id"],
    "extremes": ["station_id", "start", "stop", "datum", "set_id"],
    "currents": ["station_id", "start", "stop", "step_s", "bin_number", "set_id"],
    "current_events": ["station_id", "start", "stop", "bin_number", "set_id"],
    "datums": ["station_id", "set_id", "all_sets"], "ranges": ["station_id", "set_id"],
    "astro_table": ["id"], "equilibrium_argument": ["id", "name", "at"], "node_factor": ["id", "name", "at"],
    "equilibrium_for_year": ["id", "name", "year"], "node_factor_for_year": ["id", "name", "year"], "valid_range": ["id"],
    "to_local": ["tz"],
}
PREDICTION_OPS = {"heights", "heights_at", "extremes", "currents", "current_events"}
STRICT_FOR_OP = {"heights": {"predict_strict", "folded_heights"}, "heights_at": {"predict_strict", "folded_heights"},
                 "extremes": {"extremes_strict", "subordinate_extremes_strict", "folded_extremes"},
                 "currents": {"currents_strict"},
                 "current_events": {"current_events_strict", "subordinate_current_events_strict"}}
# Every case id and its steps (op, or driver action), exactly: a removed or added case or sub-case fails here.
SUBCASES = {
    'predict-heights/basic': 'heights',
    'predict-heights/at': 'heights_at',
    'predict-heights/step-alignment': 'heights',
    'predict-heights/empty-window': 'heights',
    'predict-heights/start-after-stop': 'heights',
    'predict-heights/step-zero': 'heights heights',
    'predict-heights/year-boundary': 'heights',
    'predict-heights/leap-day': 'heights_at',
    'predict-heights/naive-datetime': 'heights',
    'predict-heights/fractional-instants': 'heights_at heights_at heights heights',
    'predict-set-not-found': 'heights',
    'predict-local-phase-convention': 'heights heights',
    'predict-set-speed': 'heights_at',
    'predict-datum/mean-level': 'heights_at',
    'predict-datum/zero': 'heights_at',
    'predict-datum/named': 'heights_at',
    'predict-datum/chart': 'heights_at heights_at heights_at',
    'predict-datum/unavailable': 'heights_at heights_at heights_at heights_at heights_at extremes',
    'predict-datum/otc-key': 'heights_at',
    'predict-datum/vertical-zero': 'heights_at datums',
    'predict-no-constants': 'heights heights',
    'predict-quantity-mismatch': 'heights currents',
    'predict-unsupported-convention': 'heights',
    'predict-unsupported-constituent': 'heights extremes',
    'predict-no-astro-table': 'heights heights',
    'predict-time-out-of-range': 'heights_at heights_at extremes extremes heights',
    'predict-empty-window-out-of-range': 'extremes',
    'predict-extremes/basic': 'extremes',
    'predict-extremes/window-edges': 'extremes extremes extremes',
    'predict-extremes/single-constituent': 'extremes',
    'predict-extremes/large-amplitude': 'extremes extremes extremes',
    'predict-current-peaks-large-amplitude': 'current_events current_events current_events',
    'predict-slacks-large-amplitude': 'current_events current_events current_events',
    'predict-extremes/close-high-low': 'extremes',
    'predict-extremes/close-high-low-high': 'extremes',
    'predict-extremes/double-high': 'extremes',
    'predict-extremes/sub-second': 'extremes extremes extremes',
    'predict-extremes/year-boundary-step': 'extremes',
    'predict-extremes/new-year-missed': 'extremes',
    'predict-extremes/new-year-doubled': 'extremes',
    'predict-extremes/negative-amplitude': 'extremes',
    'predict-currents/series': 'currents',
    'predict-currents/mean': 'currents',
    'predict-currents/minor-sign': 'currents',
    'predict-currents/flood-sign': 'currents',
    'predict-currents/direction-null': 'currents',
    'predict-currents/direction-north': 'currents',
    'predict-currents/default-bin': 'currents currents',
    'predict-currents/explicit-bin': 'currents',
    'predict-bin-not-found': 'currents current_events',
    'predict-bin-number-too-large': 'currents currents',
    'predict-current-events/basic': 'current_events',
    'predict-current-events/flood-sign': 'current_events',
    'predict-current-events/weak': 'current_events',
    'predict-current-events/close-slacks': 'current_events',
    'predict-current-events/sub-second-slacks': 'current_events current_events current_events',
    'predict-current-events/new-year-slack': 'current_events current_events',
    'predict-subordinate/tide-ratio': 'extremes',
    'predict-subordinate/tide-additive': 'extremes',
    'predict-subordinate/tide-missing-offsets': 'extremes',
    'predict-subordinate/tide-order-swap': 'extremes extremes',
    'predict-subordinate/tide-fractional-offset': 'extremes extremes',
    'predict-subordinate/series': 'heights heights_at',
    'predict-subordinate/reference-no-chart-datum': 'extremes',
    'predict-subordinate/current': 'current_events current_events currents',
    'predict-subordinate/current-null-adjustment': 'current_events',
    'predict-subordinate/event-datum': 'extremes extremes extremes',
    'predict-subordinate/folded-ratio': 'heights',
    'predict-subordinate/folded-additive': 'heights',
    'predict-subordinate/folded-extremes': 'extremes',
    'predict-subordinate/folded-new-year': 'heights',
    'predict-subordinate/differing-offsets-series': 'heights extremes',
    'predict-subordinate/zero-ratio': 'heights extremes heights extremes heights extremes heights extremes',
    'predict-subordinate/unknown-adjusted-type': 'heights extremes heights extremes heights extremes',
    'predict-subordinate/order-ratio-before-extremes-only': 'heights',
    'predict-subordinate/reference-no-usable-set': 'heights heights_at extremes heights heights_at extremes',
    'predict-subordinate/current-reference-no-set': 'current_events',
    'predict-subordinate/current-reference-no-set-missing': 'current_events',
    'predict-subordinate/current-reference-removed': 'current_events',
    'predict-reference-set-file-order': 'extremes',
    'predict-local/station-zone': 'extremes to_local extremes to_local extremes to_local',
    'predict-local/named-zone': 'extremes to_local extremes to_local',
    'predict-local/unknown-zone': 'extremes to_local to_local to_local to_local to_local to_local to_local extremes to_local',
    'predict-local/missing-dependency': 'extremes to_local',
    'predict-local/missing-tzdir': 'restart_runner extremes to_local',
    'predict-local/not-built': 'extremes to_local',
    'predict-local/format': 'heights to_local heights to_local',
    'predict-datums/list': 'datums',
    'predict-datums/all-sets': 'datums',
    'predict-datums/ranges': 'ranges',
    'predict-datums/ranges-mixed-kinds': 'ranges',
    'predict-datum/subordinate-named': 'heights_at heights_at datums',
    'predict-datum/subordinate-reference-wrong-source': 'extremes',
    'predict-datum/subordinate-unpublished-chart': 'extremes',
    'predict-astro-values': 'astro_table astro_table astro_table equilibrium_argument node_factor equilibrium_argument node_factor equilibrium_argument node_factor equilibrium_argument node_factor equilibrium_argument node_factor equilibrium_argument node_factor equilibrium_for_year node_factor_for_year equilibrium_for_year node_factor_for_year equilibrium_for_year node_factor_for_year equilibrium_argument valid_range valid_range equilibrium_argument node_factor equilibrium_for_year node_factor_for_year equilibrium_argument node_factor equilibrium_for_year node_factor_for_year',
    'predict-astro-negative-speed/used-row': 'heights extremes current_events astro_table',
    'predict-astro-negative-speed/unused-row': 'heights',
    'predict-astro-negative-speed/short-v0u': 'heights',
    'predict-metadata': 'heights heights currents current_events',
    'not-built/otc_heights': 'heights',
    'not-built/otc_heights_at': 'heights_at',
    'not-built/otc_extremes': 'extremes',
    'not-built/otc_currents': 'currents',
    'not-built/otc_current_events': 'current_events',
    'not-built/otc_astro_table': 'astro_table',
    'not-built/otc_astro_equilibrium_argument': 'equilibrium_argument',
    'not-built/otc_astro_node_factor': 'node_factor',
    'not-built/otc_astro_equilibrium_for_year': 'equilibrium_for_year',
    'not-built/otc_astro_node_factor_for_year': 'node_factor_for_year',
    'not-built/otc_astro_valid_range': 'valid_range',
    'predict-commercial-only/effective-set': 'heights open heights',
    'predict-commercial-only/explicit-nc-set': 'heights open heights',
    'predict-commercial-only/no-constants': 'heights',
    'predict-commercial-only/offsets-usable': 'extremes extremes',
    'predict-commercial-only/offsets-nc-licence': 'extremes',
    'predict-commercial-only/reference-set-nc': 'extremes open extremes',
    'predict-commercial-only/own-set-wins': 'heights',
    'predict-commercial-only/current-offsets-nc': 'current_events open current_events',
    'predict-commercial-only/current-offsets-usable': 'current_events',
}


@pytest.fixture(scope="module")
def calls():
    return json.loads((CONF / "tools" / "predict_calls.json").read_bytes())


def spelled(cid):
    return cid.removeprefix("predict-").replace("/", "-")


def test_every_case_and_sub_case(calls):
    got = {c["id"]: " ".join(s.get("op") or s.get("driver") for s in c["steps"]) for c in calls["cases"]}
    assert len(got) == len(calls["cases"])
    assert got == SUBCASES


def test_every_spec_case_is_exactly_one_call(calls):
    spelled_ids = [spelled(c["id"]) for c in calls["cases"] if not c["id"].startswith("not-built/")]
    assert len(spelled_ids) == len(set(spelled_ids))
    missing = [n for n in SPEC_CASES if n not in spelled_ids]
    assert missing == []
    assert sorted(set(spelled_ids) - set(SPEC_CASES)) == sorted(EXTRA_CASES)
    assert {c["id"].removeprefix("not-built/") for c in calls["cases"] if c["id"].startswith("not-built/")} == set(NOT_BUILT)
    assert not set(spelled_ids) & REMOVED


def test_calls_use_k2_interface(calls, doc):
    """Ops and arguments are K2's; a prediction step's expect is K2's {prediction} with every Prediction field; to_local
    takes {tz} after a prediction step and expects the resolved zone; datums, ranges and astro_table use K2's wrappers."""
    zones = {s["station_id"]: s.get("timezone") for s in doc["stations"]}
    for c in calls["cases"]:
        seen_prediction = None
        for i, s in enumerate(c["steps"]):
            if "driver" in s or s["op"] == "open":
                continue
            assert s["op"] in K2_OPS and set(s["args"]) <= set(K2_OPS[s["op"]]), (c["id"], i)
            e = s.get("expect") or {}
            if s["op"] in PREDICTION_OPS:
                seen_prediction = s
                if "error" in e:
                    continue
                assert set(e) == {"prediction"}, (c["id"], i)
                assert set(e["prediction"]) - {"items"} == set(bf.PREDICTION_KEYS), (c["id"], i)
                assert e["prediction"]["tz"] is None and e["prediction"]["release"] == c["release"]
            elif s["op"] == "to_local":
                assert seen_prediction is not None, (c["id"], i, "to_local with no prediction step before it")
                if "error" in e:
                    continue
                want = s["args"].get("tz", "station")
                zone = zones.get(seen_prediction["args"]["station_id"]) if want == "station" else want
                assert e["prediction"]["tz"] == zone != "station", (c["id"], i)
                assert e["prediction"]["tz_version"] == bf.TZ_VERSION
                assert s["strict"] == {"same_as_step": c["steps"].index(seen_prediction)}
                assert s["local"]["zone"] == zone
            elif s["op"] == "datums" and "error" not in e:
                assert set(e) == {"datums"}
            elif s["op"] == "ranges":
                assert set(e) == {"ranges"} and set(e["ranges"]) == {"mn", "gt", "dhq", "dlq"}
            elif s["op"] == "astro_table" and "error" not in e:
                assert set(e) == {"astro_table"} and (e["astro_table"] is None or set(e["astro_table"]) == {"first_year", "last_year"})


def test_strict_entry_matches_its_step(calls):
    """A step's strict entry is the one for its op (astro-negative-speed/used-row once modelled extremes and
    current_events with predict_strict)."""
    for c in calls["cases"]:
        for i, s in enumerate(c["steps"]):
            st = s.get("strict")
            if not st or "same_as_step" in st:
                continue
            assert st["entry"] in STRICT_FOR_OP[s["op"]], (c["id"], i, st["entry"])
            a = st["args"]
            if s["op"] in ("current_events", "currents") and "bin" in a:
                assert a["bin"]["$bin"][0].split("/")[0] == s["args"]["station_id"], (c["id"], i)
            if "start" in s["args"] and "start" in a:
                assert (a["start"], a["stop"]) == (s["args"]["start"], s["args"]["stop"]), (c["id"], i)


def test_local_not_built_order(calls):
    """predict-local/not-built: without the module, not_built; with the module but no zone rules, local_time_unavailable."""
    c = next(c for c in calls["cases"] if c["id"] == "predict-local/not-built")
    eim = c["steps"][-1]["expect_if_missing"]
    assert eim == [["localtime_module", {"error": "not_built"}], ["localtime", {"error": "local_time_unavailable"}]]
    for c in calls["cases"]:   # every expect_if_missing is an ordered list of [feature, expectation] pairs
        for s in c["steps"]:
            if "expect_if_missing" in s:
                assert isinstance(s["expect_if_missing"], list) and all(len(x) == 2 for x in s["expect_if_missing"])


def test_fold_compare_is_machine_readable(calls):
    c = next(c for c in calls["cases"] if c["id"] == "predict-subordinate/folded-extremes")
    (s,) = c["steps"]
    cmp = s["compare"]
    assert (cmp["entry"], cmp["time_s"], cmp["height_m"]) == ("subordinate_extremes_strict", 1, 1e-5)
    assert {k: v for k, v in cmp["args"].items()} == s["strict"]["args"] and s["strict"]["entry"] == "folded_extremes"


def test_calls_resolve(calls):
    manifest = {f["root"]: f for f in json.loads((FIX / "fixtures.json").read_bytes())["fixtures"]}
    for c in calls["cases"]:
        fx = manifest[c["root"]]
        assert c["release"] in fx["releases"], c["id"]
        d = json.loads((FIX / c["root"] / f"OTC_{c['release']}.json").read_bytes())
        st = {s["station_id"]: s for s in d["stations"]}
        sets = {cs["set_id"]: cs for s in d["stations"] for cs in s.get("constant_sets", [])}
        tables = {t["astro_table_id"] for t in d.get("astro_tables", [])}
        assert c["requires"] == [] if c["id"].startswith("not-built/") else "predict" in c["requires"], c["id"]
        if c["root"] == "knc-predict":
            assert c.get("open_args") == {"commercial_only": True}
        for s in c["steps"]:
            if "driver" in s or s["op"] == "open":
                continue
            a = s["args"]
            if "station_id" in a:
                assert a["station_id"] in st, (c["id"], a)
            if a.get("set_id") and "no-such" not in a["set_id"]:
                assert a["set_id"] in sets, (c["id"], a)
            strict = s.get("strict") or {}
            if "entry" not in strict:
                continue
            sa = strict["args"]
            assert sa["astro"] in tables, (c["id"], sa["astro"])
            for v in sa.values():
                if isinstance(v, dict) and "$set" in v:
                    assert v["$set"] in sets, (c["id"], v)
                if isinstance(v, dict) and "$bin" in v:
                    sid, n = v["$bin"]
                    assert any(b["bin"] == n for b in sets[sid]["current_bins"]), (c["id"], v)
                if isinstance(v, dict) and "$offsets" in v:
                    assert "subordinate_offsets" in st[v["$offsets"]], (c["id"], v)
                if isinstance(v, dict) and "$current_offset" in v:
                    sid, n = v["$current_offset"]
                    assert any(o["bin"] == n for o in st[sid]["current_offsets"]), (c["id"], v)
            for tm in sa.get("times", []):
                assert tm.endswith("Z") and "." not in tm, (c["id"], tm)   # the strict mode gets whole seconds


def test_no_case_names_both_knc_roots(calls):
    """No case opens knc and knc-predict in the same cache (both are release 20991231.2, spec 6.5)."""
    for c in calls["cases"]:
        text = json.dumps(c)
        assert not ('"knc"' in text and "knc-predict" in text), c["id"]


def test_bands(calls):
    """Spec 6.3: every event step avoids the four bands (build_fixtures.band_problems), except band 3 in the two exact recorded cases."""
    assert bf.band_problems(calls) == []
    assert set(bf.BAND_EXCEPTIONS) == {"predict-extremes/single-constituent", "predict-extremes/negative-amplitude"}


@pytest.mark.parametrize("cid,root,amplitude", [
    ("predict-extremes/single-constituent", "predict", 1.0),
    ("predict-extremes/negative-amplitude", "predict-bad/extremes-negative-amplitude", -1.0),
])
def test_named_band_declarations_and_native_roots(calls, cid, root, amplitude):
    case = next(c for c in calls["cases"] if c["id"] == cid)
    declaration = case.get("band_exception")
    assert isinstance(declaration, dict)
    assert declaration == bf.BAND_EXCEPTIONS[cid]
    assert declaration["case_id"] == cid and declaration["band"] == 3
    assert declaration["event_time_tolerance_s"] == 1 and declaration["reason"]
    assert declaration["root"] == root and declaration["set_id"] == "OTC-P-0005/noaa"
    assert declaration["astro_table_id"] == bf.ASTRO_A
    assert [declaration["start"], declaration["stop"]] == list(bf.PW["single"])
    source = json.loads((FIX / root / f"OTC_{case["release"]}.json").read_bytes())
    sm = set_sum(source, declaration["set_id"])
    assert sm.terms == [("M2", amplitude, 20.903277)]
    start, stop = map(ts, bf.PW["single"])
    roots = scan(lambda t, y: sm.dh(t), start, stop, 5.0)
    assert len(roots) == 116
    problems = []
    bf._tide_events(sm.t, sm.terms, start, stop, cid, problems)
    assert len(problems) == 4 and all("band 3:" in p for p in problems)
    assert bf.band_problems({"cases": [case]}) == []
    unlisted = copy.deepcopy(case)
    unlisted["id"] += "/unlisted"
    unlisted.pop("band_exception")
    rejected = bf.band_problems({"cases": [unlisted]})
    assert len(rejected) == 4 and all("band 3:" in p for p in rejected)


@pytest.mark.parametrize("fault", ["missing", "band", "tolerance", "root", "window"])
def test_named_band_gate_refuses_inconsistent_declarations(calls, fault):
    case = copy.deepcopy(next(c for c in calls["cases"] if c["id"] == "predict-extremes/single-constituent"))
    if fault == "missing":
        case.pop("band_exception", None)
    elif fault == "window":
        case["steps"][0]["strict"]["args"]["start"] = "2010-03-06T18:08:00Z"
    elif fault == "root":
        case["root"] = "predict-bad/extremes-negative-amplitude"
    else:
        case.setdefault("band_exception", {})["band" if fault == "band" else "event_time_tolerance_s"] = 4 if fault == "band" else 2
    assert any("exception" in p for p in bf.band_problems({"cases": [case]}))


@pytest.mark.parametrize("band", [1, 2, 4])
def test_band3_allowance_keeps_other_native_bands(doc, band):
    # Actual harmonic/table math, without substituting the validator or search functions.
    ta = copy.deepcopy(table(doc, bf.ASTRO_A))
    row = ta["constituents"]["M2"]
    row["f"] = [1.0] * len(row["f"])
    row["v0u_deg"] = [0.0] * len(row["v0u_deg"])
    T = ts("2010-01-01T00:00:00Z")
    if band == 1:
        row["speed_deg_per_hour"] = 360.0 * 3600 / 2
        start, stop = T + 7200, T + 7220
    else:
        start, stop = T - 4000, T + 4000
        if band == 2:
            speed = row["speed_deg_per_hour"]
            old = 2009 - ta["first_year"]
            row["v0u_deg"][old] = (-speed * (T - 1800 - year_start(2009)) / 3600) % 360
            row["v0u_deg"][old + 1] = (-speed * 1800 / 3600) % 360
    problems = []
    bf._tide_events(ta, [("M2", 1.0, 0.0)], start, stop, "native-band-preservation", problems, report=False)
    assert any(f"band {band}:" in p for p in problems), problems
    assert not any("band 3:" in p for p in problems)


def test_ripple_coverage_blocks_complete_scientific_gate(calls):
    coverage = bf.band_coverage(calls["cases"])
    assert calls["band_coverage"] == coverage
    assert coverage["scientific_gate_ready"] is False and coverage["deferred"]
    for entry in coverage["deferred"]:
        assert entry["requires"] == ["KP1-H"] and entry["blocks"] == "K2b-pin scientific gate"
        assert entry["case_id"] not in bf.BAND_EXCEPTIONS
    named = [c for c in calls["cases"] if c["id"] in bf.BAND_EXCEPTIONS]
    assert bf.band_coverage(named) == {"scientific_gate_ready": True, "deferred": []}


def nonexempt_half_second_case(calls):
    case = copy.deepcopy(next(c for c in calls["cases"] if c["id"] == "predict-extremes/single-constituent"))
    case["id"] = "predict-extremes/nonexempt-half-second"
    case.pop("band_exception", None)
    args = case["steps"][0]["strict"]["args"]
    args["start"], args["stop"] = "2010-03-06T18:08:00Z", "2010-03-06T18:10:00Z"
    return case


def test_bands_reject_nonexempt_half_second_event(calls, doc):
    """The real M2 event stays forbidden outside the exact named fixed-window exception."""
    case = nonexempt_half_second_case(calls)
    args = case["steps"][0]["strict"]["args"]
    assert case["id"] not in bf.BAND_EXCEPTIONS
    start, stop = ts(args["start"]), ts(args["stop"])
    sm = set_sum(doc, args["constituents"]["$set"], args["astro"])
    roots = scan(lambda t, y: sm.dh(t), start, stop, 0.01)
    assert len(roots) == 1
    event = roots[0][0]
    assert math.floor(event) == ts("2010-03-06T18:08:53Z")
    assert abs(event - math.floor(event) - 0.5) < bf.ROUND_BAND
    problems = bf.band_problems({"cases": [case]})
    assert len(problems) == 1 and "band 3: event at 2010-03-06T18:08:53Z" in problems[0], problems


def test_band_consumer_accepts_integer_valued_float_year(calls, doc, tmp_path, monkeypatch):
    """JSON integer 2000.0 has the same native band result and values as integer-token 2000."""
    case = nonexempt_half_second_case(calls)
    args = case["steps"][0]["strict"]["args"]
    expected = bf.band_problems({"cases": [case]})
    assert len(expected) == 1 and "band 3" in expected[0]
    floating = copy.deepcopy(doc)
    floating_table = table(floating, args["astro"])
    floating_table["first_year"] = float(floating_table["first_year"])
    schemas = bf.load_schemas(bf.VENDORED_SCHEMAS)
    assert list(bf.validator(schemas["1.0"]).iter_errors(floating)) == []
    path = tmp_path / case["root"] / f"OTC_{case['release']}.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(floating), encoding="utf-8")
    assert isinstance(json.loads(path.read_bytes())["astro_tables"][0]["first_year"], float)
    # Redirect only the actual file root: no validator or event calculation is replaced.
    monkeypatch.setattr(bf, "FIXTURES", tmp_path)
    assert bf.band_problems({"cases": [case]}) == expected
    sm = set_sum(doc, args["constituents"]["$set"], args["astro"])
    value, deriv = bf._bsum(sm.t, sm.terms)
    float_value, float_deriv = bf._bsum(floating_table, sm.terms)
    for instant in (args["start"], args["stop"], "2020-01-01T00:00:00Z"):
        t = ts(instant)
        assert float_value(t, year_of(t)) == value(t, year_of(t))
        assert float_deriv(t, year_of(t)) == deriv(t, year_of(t))


def test_bsum_does_not_truncate_schema_invalid_fractional_year(doc):
    fractional = copy.deepcopy(doc)
    ta = table(fractional, bf.ASTRO_A)
    ta["first_year"] += 0.5
    schemas = bf.load_schemas(bf.VENDORED_SCHEMAS)
    assert list(bf.validator(schemas["1.0"]).iter_errors(fractional))
    sm = set_sum(doc, "OTC-P-0005/noaa")
    value, _ = bf._bsum(ta, sm.terms)
    with pytest.raises(TypeError):
        value(ts("2020-01-01T00:00:00Z"), 2020)


# --------------------------------------------------------------------------- the hand-written outcomes (spec 6.5, S4)

def survivors(f, value, lo, hi, dt, slack=False):
    """The reported candidates of spec 4.6 steps 2-6a (or the slack search of 4.7) of f over [lo, hi], from the
    builder's band model (leaf cancellation is not modelled; every designed root here sits in its own leaf)."""
    problems = []
    out = bf._search(f, value, lo, hi, dt, problems, "test", slack)
    assert problems == [], problems
    return out


def reported(cands, start, stop, kinds):
    out = []
    for r, k, v, y in cands:
        t = math.floor(r + 0.5)
        if start <= t < stop:
            assert abs(r - math.floor(r) - 0.5) >= 0.01, f"an outcome event within 0.01 s of a half second at {r}"
            out.append({"time": datetime.datetime.fromtimestamp(t, tz=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "type": kinds[k]})
    return out


TIDE = {"down": "high", "up": "low"}
SLACK = {"up": "slack_before_flood", "down": "slack_before_ebb"}


def outcome_steps(calls):
    for c in calls["cases"]:
        for i, s in enumerate(c["steps"]):
            if "items" in (s.get("outcome") or {}) and c["root"] == "predict":
                yield c, i, s


def test_outcomes_equal_the_design(calls, doc):
    """Every {items} outcome on the prediction release equals the design scan of its window: the survivors of the
    close-root filter and the New Year reconciliation, rounded, in [start, stop), of the outcome's types."""
    checked = 0
    for c, i, s in outcome_steps(calls):
        a = s["args"]
        start, stop = ts(a["start"]), ts(a["stop"])
        st = next(x for x in doc["stations"] if x["station_id"] == a["station_id"])
        if s["op"] == "extremes":
            cs = next(x for x in st["constant_sets"] if x["set_id"] == (a.get("set_id") or st["recommended_set_id"]))
            sm = Sum(table(doc, bf.ASTRO_A), [(x["name"], x["amplitude_m"], x["phase_deg"]) for x in cs["constituents"]])
            fast = max(table(doc, bf.ASTRO_A)["constituents"][x["name"]]["speed_deg_per_hour"] for x in cs["constituents"])
            dt = min(1.0, 360.0 / fast * 3600 / 100)
            cands = survivors(lambda t, y: sm.dh(t, y), lambda t, y: sm.h(t, y), start - 3600, stop + 3600, dt)
            got = reported(cands, start, stop, TIDE)
        else:
            w, dw = bin_w(doc, st["constant_sets"][0]["set_id"], a["bin_number"])
            b = next(b for b in st["constant_sets"][0]["current_bins"] if b["bin"] == a["bin_number"])
            fast = max(table(doc, bf.ASTRO_A)["constituents"][x["name"]]["speed_deg_per_hour"] for x in b["constituents"])
            dt = min(1.0, 360.0 / fast * 3600 / 100)
            pad = 3600 if fast < 360 else 60   # the ripple windows: the slack zeros are local
            cands = survivors(lambda t, y: w(t, y), lambda t, y: 0.0, start - pad, stop + pad, dt, slack=True)
            got = reported(cands, start, stop, SLACK)
        types = s["outcome"].get("types")
        if types:
            got = [x for x in got if x["type"] in types]
        assert got == s["outcome"]["items"], (c["id"], i, got)
        checked += 1
    assert checked >= 14


def test_counts_equal_the_design(calls, doc):
    by_id = {c["id"]: c for c in calls["cases"]}
    s5 = set_sum(doc, "OTC-P-0005/noaa")
    t0, t1 = ts(bf.PW["single"][0]), ts(bf.PW["single"][1])
    n = len(scan(lambda t, y: s5.dh(t), t0, t1, 5.0))
    assert by_id["predict-extremes/single-constituent"]["steps"][0]["outcome"] == {"count": n} == \
        by_id["predict-extremes/negative-amplitude"]["steps"][0]["outcome"]


# --------------------------------------------------------------------------- the review's added fixtures (A1-A8)

def case_step(calls, cid, i=0):
    return next(c for c in calls["cases"] if c["id"] == cid)["steps"][i]


def test_a1_events_with_sigma_minus_one(calls, doc):
    s = case_step(calls, "predict-current-events/flood-sign")
    st = next(x for x in doc["stations"] if x["station_id"] == s["args"]["station_id"])
    b = next(b for b in st["constant_sets"][0]["current_bins"] if b["bin"] == s["args"]["bin_number"])
    assert math.cos(math.radians(b["azimuth_deg"] - b["mean_flood_dir_deg"])) < 0   # sigma = -1
    assert s["strict"]["entry"] == "current_events_strict"


def test_a2_window_seams(calls, doc):
    """window-edges: an event at start is in, one at stop is out, and two windows meeting at an event report it once."""
    steps = next(c for c in calls["cases"] if c["id"] == "predict-extremes/window-edges")["steps"]
    whole, left, right = (s["outcome"]["items"] for s in steps)
    assert left + right == whole and steps[0]["args"]["start"] == whole[0]["time"] == left[0]["time"]
    assert steps[1]["args"]["stop"] == whole[-1]["time"] == right[0]["time"] == steps[2]["args"]["start"]


def test_a3_reference_event_inside_the_padding(calls, doc):
    """A reference event before start whose shifted time lands in the window: a padding M of 120 min (tides: M must be
    250 + 60 min here) or 0 loses it (spec 4.8 step 2, 4.9 step 2)."""
    s = case_step(calls, "predict-subordinate/tide-order-swap", 1)
    start, stop = ts(s["args"]["start"]), ts(s["args"]["stop"])
    ref = set_sum(doc, "OTC-P-0001/noaa")
    highs = [r for r, k in scan(lambda t, y: ref.dh(t), start - 6 * 3600, start, 1.0) if k == "down"]
    assert any(start - 250 * 60 <= r < start - 120 * 60 and start <= r + 250 * 60 < stop for r in highs)
    s = case_step(calls, "predict-subordinate/current", 1)
    start = ts(s["args"]["start"])
    w, _ = bin_w(doc, "OTC-P-0016/noaa", 1)
    ups = [r for r, k in scan(lambda t, y: w(t), start - 3600, start, 1.0) if k == "up"]
    assert any(r < start <= r + 5.5 * 60 for r in ups)


def test_a4_set_speed_off_the_table(calls, doc):
    st = next(x for x in doc["stations"] if x["station_id"] == bf.P_BASIC)
    m2 = next(c for c in st["constant_sets"][0]["constituents"] if c["name"] == "M2")
    row = table(doc, bf.ASTRO_A)["constituents"]["M2"]["speed_deg_per_hour"]
    assert 0 < abs(m2["speed_deg_per_hour"] - row) <= 1e-7
    s = case_step(calls, "predict-set-speed")
    t = ts(s["args"]["times"][-1])
    a = Sum(table(doc, bf.ASTRO_A), [("M2", m2["amplitude_m"], m2["phase_deg"])])
    alt = json.loads(json.dumps(table(doc, bf.ASTRO_A)))
    alt["constituents"]["M2"]["speed_deg_per_hour"] = m2["speed_deg_per_hour"]
    b = Sum(alt, [("M2", m2["amplitude_m"], m2["phase_deg"])])
    assert abs(a.h(t) - b.h(t)) > 1e-6   # far above the cases' 1e-9 tolerance


def test_a5_a6_chart_datum_above_zero_and_event_path_datum(calls, doc):
    s = case_step(calls, "predict-datum/chart", 1)
    cs = next(c for x in doc["stations"] for c in x.get("constant_sets", []) if c["set_id"] == s["strict"]["args"]["constituents"]["$set"])
    assert cs["datum"]["named"][cs["datum"]["chart_datum"]] != 0 and "error" not in s["expect"]
    assert s["strict"]["args"]["datum_term"] == cs["datum"]["msl_offset_m"] - cs["datum"]["named"]["mllw"]
    steps = next(c for c in calls["cases"] if c["id"] == "predict-subordinate/event-datum")["steps"]
    assert [x["strict"]["entry"] for x in steps] == ["subordinate_extremes_strict"] * 3
    assert [x["args"].get("datum") for x in steps] == [None, "mhhw", "msl"]
    assert steps[0]["strict"]["args"]["chart_datum_term"] == 2.4 - 0.85
    assert [x["strict"]["args"]["datum_shift"] for x in steps] == [0.0, -1.6, -0.8]


def test_a7_fractional_second_offsets(calls, doc):
    """+12.345 and -7.29 min: some event in the window rounds differently when the offset is added to the rounded time."""
    s = case_step(calls, "predict-subordinate/tide-fractional-offset", 1)
    start, stop = ts(s["args"]["start"]), ts(s["args"]["stop"])
    ref = set_sum(doc, "OTC-P-0001/noaa")
    off = {"down": 12.345 * 60, "up": -7.29 * 60}
    rs = scan(lambda t, y: ref.dh(t), start - 3 * 3600, stop + 3 * 3600, 1.0)
    differ = [r for r, k in rs if start <= math.floor(r + off[k] + .5) < stop
              and math.floor(r + off[k] + .5) != math.floor(math.floor(r + .5) + off[k] + .5)]
    assert differ


def test_a8_removed_current_reference(calls, doc):
    s = case_step(calls, "predict-subordinate/current-reference-removed")
    assert s["expect"] == {"error": "reference_unavailable", "error_fields": {"reference_station_id": "OTC-P-0097"}}
    assert next(x for x in doc["stations"] if x["station_id"] == "OTC-P-0097")["status"] == "removed"


# --------------------------------------------------------------------------- the reference reader's speed check (S6)

@pytest.mark.parametrize("where,delta,bad", [("bin", 0.0058958, True), ("bin", 8e-8, False), ("table", 1e-6, True),
                                             ("set", 8e-8, False)])
def test_three_way_speed_check(where, delta, bad):
    """Build check 7 (spec 3.3): a set's water-level or current constituent, its astro-table row and the constituent
    table agree on the speed within 1e-7 deg/h, all three ways."""
    d = json.loads(json.dumps(bf.predict_doc()))
    if where == "bin":
        st = next(s for s in d["stations"] if s["station_id"] == "OTC-P-0013")
        st["constant_sets"][0]["current_bins"][0]["constituents"][0]["speed_deg_per_hour"] += delta
    elif where == "table":
        next(c for c in d["constituents"] if c["name"] == "S2")["speed_deg_per_hour"] += delta
    else:
        st = next(s for s in d["stations"] if s["station_id"] == "OTC-P-0002")
        st["constant_sets"][0]["constituents"][0]["speed_deg_per_hour"] += delta
    errs = [e for e in bf.cross_ref_errors(d) if "speed" in e]
    assert bool(errs) == bad, errs
