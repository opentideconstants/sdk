"""Group I: the fixture and case builders and their reference reader fail closed (review round 1, package PK19)."""
from __future__ import annotations

import copy
import gzip
import json
import sys

import pytest

from _util import CONF

sys.path.insert(0, str(CONF / "tools"))
sys.path.insert(0, str(CONF))
import build_fixtures as bf  # noqa: E402


# --- K21: gz() handles a committed .json.gz whose deflate stream is corrupt (zlib.error), and says so

def test_gz_with_a_corrupt_committed_file_does_not_crash(tmp_path, capsys):
    data = b'{"x": 1}\n' * 200
    good = gzip.compress(data, compresslevel=9, mtime=0)
    bad = bytearray(good)
    bad[20] ^= 0xFF   # a corrupt deflate body: gzip.decompress raises zlib.error, which is not an OSError
    p = tmp_path / "x.json.gz"
    p.write_bytes(bytes(bad))
    bf._GZ_SEEN.clear()
    out = bf.gz(data, p)
    assert gzip.decompress(out) == data
    assert "x.json.gz" in capsys.readouterr().err


# --- K24: the reference reader reports defects as Fail (an error code), never as a raw exception

def _root(tmp_path, tamper=None, doc=None):
    bf._GZ_SEEN.clear()
    bf.write_root(tmp_path, [doc or bf.release_doc(bf.BASE)], tamper=tamper)
    return tmp_path


def _bad_sums_line(files, sums, entry, reuse):
    return files, sums.replace(b"  ", b" ", 1), entry


def _drop_file(files, sums, entry, reuse):
    files = dict(files)
    del files[f"OTC_{bf.BASE}.jsonl"]
    return files, sums, entry


def _version(v):
    def t(files, sums, entry, reuse):
        doc = bf.release_doc(bf.BASE)
        if v is None:
            del doc["format_version"]
        else:
            doc["format_version"] = v
        files = bf.release_files(doc, None)
        sums = bf.sha256_list(files)
        return files, sums, bf.pointer_entry(bf.release_doc(bf.BASE), files, sums)  # the pointer still says 1.0
    return t


@pytest.mark.parametrize("tamper,code", [(_bad_sums_line, "checksum_mismatch"), (_drop_file, "network"),
                                         (_version(None), "invalid_release"), (_version("1.0.1"), "invalid_release"),
                                         (_version("x"), "invalid_release")])
def test_reference_reader_raises_fail(tmp_path, tamper, code):
    root = _root(tmp_path, tamper)
    with pytest.raises(bf.Fail) as e:
        bf.open_release(root, bf.BASE, None)
    assert e.value.code == code, str(e.value)


import os  # noqa: E402

SCHEMA_DIR = os.environ.get("OTC_SCHEMA_DIR") or os.path.expanduser("~/.local/share/copilotkit/cr/otc-sdk-int/fix/pk19/schemas")


@pytest.fixture(scope="module")
def schemas():
    try:
        return bf.load_schemas(SCHEMA_DIR if os.path.isdir(SCHEMA_DIR) else None)
    except (OSError, SystemExit) as e:
        pytest.skip(f"no pinned schemas: {e}")


# --- K46: a set with no provenance at all is invalid_release; the missing-build repair does not crash on it

def test_set_without_provenance_is_invalid_not_keyerror(schemas):
    doc = bf.release_doc(bf.BASE)
    st = next(s for s in doc["stations"] if s["station_id"] == "OTC-T-0004")
    del st["constant_sets"][0]["provenance"]
    meta = {k: v for k, v in doc.items() if k != "stations"}
    with pytest.raises(bf.Fail) as e:
        bf.validate_release(doc, meta, doc["stations"], schemas, allow_missing_build=True)
    assert e.value.code == "invalid_release"


# --- B2-T2: a missing provenance.build is tolerated by a general rule (spec 4.6), not by the path of one root

def test_missing_build_tolerated_in_any_root(tmp_path, schemas):
    root = _root(tmp_path, doc=bf.no_build_doc())
    got = bf.open_release(root, bf.BASE, schemas)
    assert any("no provenance.build" in x for x in got["unknown_fields"]), got


# --- B2-8: a subordinate current station with only current_offsets is valid 1.0 (schema active_station else.anyOf)

def current_sub_doc():
    doc = bf.release_doc(bf.SECOND)
    doc["stations"].append({
        "station_id": "OTC-T-0023", "status": "active", "name": "Test Current Narrows", "country": "USA", "lat": 47.95,
        "lon": -122.62, "timezone": "America/Los_Angeles", "type": "subordinate", "recommended_set_id": None,
        "default_current_bin": 1, "constant_sets": [],
        "current_offsets": [{"bin": 1, "depth_m": None, "depth_type": "unknown", "reference_station_id": "OTC-T-0019",
                             "reference_bin": 1, "mean_flood_dir_deg": 210.0, "mean_ebb_dir_deg": 40.0,
                             "time_adj_max_flood_min": -15, "time_adj_slack_before_ebb_min": 0, "time_adj_max_ebb_min": 10,
                             "time_adj_slack_before_flood_min": None, "flood_amp_ratio": 1.2, "ebb_amp_ratio": 1.1,
                             "licence_id": "noaa"}]})
    return doc


def test_current_offsets_subordinate_is_valid(schemas):
    doc = current_sub_doc()
    assert bf.cross_ref_errors(doc) == []
    meta = {k: v for k, v in doc.items() if k != "stations"}
    bf.validate_release(doc, meta, doc["stations"], schemas)


def test_current_offsets_references_must_resolve():
    doc = current_sub_doc()
    doc["stations"][-1]["current_offsets"][0]["reference_station_id"] = "OTC-T-9999"
    doc["stations"][-1]["current_offsets"][0]["licence_id"] = "no-such-licence"
    errs = bf.cross_ref_errors(doc)
    assert any("OTC-T-9999" in e for e in errs) and any("no-such-licence" in e for e in errs), errs
