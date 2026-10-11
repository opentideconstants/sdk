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



def test_prediction_roots_in_manifest():
    manifest = json.loads((FIX / "fixtures.json").read_bytes())
    roots = {f["root"]: f for f in manifest["fixtures"]}
    assert roots["predict"]["releases"] == [bf.PREDICT_D] and roots["predict"]["expect"] == "load"
    for name in ("no-astro-table", "unsupported-constituent", "astro-negative-speed", "astro-negative-speed-unused",
                 "astro-short-v0u", "extremes-negative-amplitude", "unknown-adjusted-type"):
        assert roots[f"predict-bad/{name}"]["expect"] == "load", name


@pytest.mark.parametrize("root,release,tolerated", [
    ("predict", bf.PREDICT_D, False),
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


BAD_PATHS = {
    "no-astro-table": None,   # checked by hand below
    "unsupported-constituent": {"/astro_tables/0/constituents/M4"},
    "astro-negative-speed": {"/astro_tables/0/constituents/M2/speed_deg_per_hour"},
    "astro-negative-speed-unused": {"/astro_tables/0/constituents/MN4/speed_deg_per_hour"},
    "astro-short-v0u": {"/astro_tables/0/constituents/M2/v0u_deg"},
    "extremes-negative-amplitude": None,
    "unknown-adjusted-type": None,
}


@pytest.mark.parametrize("name", list(BAD_PATHS))
def test_bad_prediction_fixture_has_one_change(name, doc):
    bad = json.loads((FIX / "predict-bad" / name / f"OTC_{bf.PREDICT_D}.json").read_bytes())
    paths = set(diff_paths(doc, bad))
    if name == "no-astro-table":
        conv = next(i for i, c in enumerate(doc["conventions"]) if c["convention_id"] == bf.CONV_LOCAL)
        assert [t["astro_table_id"] for t in bad["astro_tables"]] == [bf.ASTRO_B]
        assert paths == {f"/conventions/{conv}/astro_table_id"} | {p for p in paths if p.startswith("/astro_tables")}
        assert all(c.get("astro_table_id") in (bf.ASTRO_A, bf.ASTRO_B) for c in bad["conventions"] if c["convention_id"] != bf.CONV_LOCAL)
    elif name == "extremes-negative-amplitude":
        assert paths == {f"/stations/{station_index(doc, 'OTC-P-0005')}/constant_sets/0/constituents/0/amplitude_m"}
        assert bad["stations"][station_index(doc, "OTC-P-0005")]["constant_sets"][0]["constituents"][0]["amplitude_m"] == -1.0
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
    used = {c["name"] for s in doc["stations"] for cs in s["constant_sets"] for c in cs["constituents"]
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
    msl = next(c for st in doc["stations"] for c in st["constant_sets"] if c["set_id"] == "OTC-P-0011/triple-equal")["datum"]["msl_offset_m"]
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
                                          (4, ["up", "down", "up", "down", "up"], 0.95)])
def test_sub_second_slacks(doc, n, kinds, span):
    """Two slacks 0.6 s apart (in two leaves), three within 0.9 s flood-ebb-flood (three leaves), five within 0.95 s.
    Five roots within 0.95 s cannot sit in five leaves of 0.703125 s: they sit 2-1-2, so the two pairs cancel inside
    their leaves (spec 4.6 step 4) and the middle one (index 2) is the only candidate."""
    w, dw = bin_w(doc, "OTC-P-0020/noaa", n)
    c = ts(bf.PW["sub-second-slacks"][n - 2][:19] + "Z") + float(bf.PW["sub-second-slacks"][n - 2][19:-1])
    zs = scan(lambda t, y: w(t), c - 20, c + 20, 0.002)
    near = [z for z in zs if abs(z[0] - c) < 1.0]
    assert [k for _, k in near] == kinds and near[-1][0] - near[0][0] < span
    assert isolated(zs, near, c - 20, c + 20, None)
    leaves = [leaf(r) for r, _ in near]
    if n == 2:
        assert abs(near[1][0] - near[0][0] - 0.6) < 0.02 and len(set(leaves)) == 2
    elif n == 3:
        assert len(set(leaves)) == 3
    else:
        assert leaves[0] == leaves[1] != leaves[2] != leaves[3] == leaves[4]


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
