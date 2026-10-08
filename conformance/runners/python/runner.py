# /// script
# requires-python = ">=3.10"
# ///
"""The Python conformance runner (SDK spec §7.1, conformance/README.md).

It speaks the runner protocol and calls only the public API of the
opentideconstants package.

    uv run conformance/driver.py --runner "python3 conformance/runners/python/runner.py"

By default it imports the package from python/src in this repository. With
--installed it imports the installed package instead (for example from a wheel).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import math
import os
import sys
from enum import Enum
from pathlib import Path

FEATURES = ["fs", "fetch", "json", "eager", "stream"]


def _version():
    try:
        import opentideconstants
        return opentideconstants.__version__
    except Exception:  # the hello must go out even when the SDK does not import
        return "0.0.0"


# --------------------------------------------------------------------------- encodings (README "Result encodings")

def plain(v):
    """Turn an SDK value (enum, datetime, read-only mapping, tuple) into plain JSON."""
    if v is None or isinstance(v, bool):
        return v
    if isinstance(v, Enum):
        return v.value
    if isinstance(v, (int, str)):
        return v
    if isinstance(v, float):
        return None if math.isnan(v) else v
    if isinstance(v, _dt.datetime):
        return v.astimezone(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if hasattr(v, "items"):
        return {str(k): plain(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [plain(x) for x in v]
    raise TypeError(f"cannot encode {type(v).__name__}")


def pick(obj, fields):
    return {f: plain(getattr(obj, f)) for f in fields}


def enc_station(s):
    if s is None:
        return None
    rs = s.recommended_set
    return {
        **pick(s, ["station_id", "name", "country", "lat", "lon", "type", "kind", "timezone", "aliases", "status",
                   "is_reference", "is_subordinate", "is_tide", "is_current"]),
        "recommended_set_id": rs.set_id if rs is not None else None,
    }


def enc_tombstone(t):
    return None if t is None else pick(t, ["station_id", "name", "status", "removed_in", "removed_reason"])


def enc_set(cs):
    if cs is None:
        return None
    span, datum = cs.record_span, cs.datum
    return {
        **pick(cs, ["set_id", "source", "source_type", "quantity", "source_record_id", "source_version", "qc_status"]),
        "record_span": None if span is None else pick(span, ["start", "end", "good_samples"]),
        "datum": None if datum is None else pick(datum, ["msl_offset_m", "named"]),
        "qc_flags": [pick(f, ["flag", "verdict", "values"]) for f in cs.qc_flags],
        "dropped_constituents": [pick(d, ["name", "dropped_reason", "detail"]) for d in cs.dropped_constituents],
        "is_recommended": cs.is_recommended,
        "convention_id": cs.convention.convention_id,
        "licence_id": cs.licence.licence_id,
        "constituent_count": len(cs.constituents),
    }


CONSTITUENT = ["name", "source_name", "doodson", "speed_deg_per_hour", "amplitude_m", "phase_deg",
               "amp_uncertainty_m", "phase_uncertainty_deg", "kept_reason"]
CONVENTION = ["convention_id", "phase_reference", "utc_offset_hours", "v0_model", "nodal_handling",
              "nodal_formula_ids", "constituent_table_version", "tables_sha256", "canary"]
LICENCE = ["licence_id", "spdx", "provider", "citation", "attribution", "url"]
PROVENANCE = ["build_commit", "adapter_version", "input_sha256", "time_base", "selection_reason", "decision"]
VALIDATION = ["set_id", "reference_source", "reference_station", "reference_distance_km", "window",
              "time_mae_min", "time_p95_min", "time_bias_min", "height_mae_m", "range_error_m",
              "missed_events", "extra_events", "previous_release"]
OFFSETS = ["reference_station_id", "time_offset_high_min", "time_offset_low_min", "height_offset_high",
           "height_offset_low", "height_adjusted_type", "licence_id"]
FILE_INFO = ["name", "url", "size", "sha256"]


def enc_files(files):
    return sorted([pick(f, FILE_INFO) for f in files], key=lambda f: f["name"])


def enc_release_info(info):
    if info is None:
        return None
    return {"datestamp": info.datestamp, "format_version": info.format_version, "doi": info.doi,
            "files": enc_files(info.files)}


def enc_validation(rows):
    return [pick(v, VALIDATION) for v in rows]


# --------------------------------------------------------------------------- ops

FILTERS = ("country", "type", "kind", "source", "source_type")


class Runner:
    def __init__(self):
        self.client = None
        self.held = {}

    def _sdk(self):
        import opentideconstants
        return opentideconstants

    def target(self, req):
        on = req.get("on")
        if on:
            return self.held[on]
        if self.client is None:
            raise RuntimeError("no client is open")
        return self.client

    def release(self, req):
        on = req.get("on")
        return self.held[on] if on else self.client.release

    def station(self, req, a):
        return self.target(req).station(a["station_id"])

    def set(self, req, a):
        st = self.station(req, a)
        return None if st is None else st.constant_set(a["set_id"])

    def handle(self, req):
        op, a = req["op"], req.get("args") or {}
        sdk = self._sdk()
        filters = {k: a[k] for k in FILTERS if k in a}
        if op == "open":
            if self.client is not None:
                self.client.close()
                self.client = None
            self.client = sdk.OpenTideConstants(**a)
            r = self.client.release
            return {"loaded_from": plain(self.client.loaded_from), "datestamp": r.datestamp, "format_version": r.format_version}
        if op == "close":
            if self.client is not None:
                self.client.close()
                self.client = None
            return {}
        if op == "hold_release":
            self.held[a["name"]] = self.client.release
            return {}
        c = self.client
        if op == "loaded_from":
            return {"loaded_from": plain(c.loaded_from)}
        if op == "last_error":
            e = c.last_error
            return {"code": None if e is None else e.code}
        if op == "release_metadata":
            r = self.release(req)
            return pick(r, ["datestamp", "created", "format_version", "doi", "concept_doi", "source_versions",
                            "build_commit", "changelog_url"])
        if op == "release_files":
            return {"files": enc_files(self.release(req).files)}
        if op == "releases":
            return {"releases": [enc_release_info(i) for i in c.releases()]}
        if op == "latest":
            return {"release": enc_release_info(c.latest())}
        if op == "check_for_update":
            return {"release": enc_release_info(c.check_for_update())}
        if op == "update":
            u = c.update()
            return {"updated": u.updated, "from": u.from_, "to": u.to}
        if op == "download":
            kw = {k: a[k] for k in ("formats", "overwrite") if k in a}
            pos = [a["release"]] if "release" in a else []
            paths = c.download(*pos, to=a["to"], **kw)
            return {"paths": sorted(os.path.basename(str(p)) for p in paths)}
        if op == "verify":
            return {"verified": c.verify()}
        if op == "cached_releases":
            return {"datestamps": list(c.cached_releases())}
        if op == "prune":
            kw = {"keep": a["keep"]} if "keep" in a else {}
            return {"removed": list(c.prune(**kw))}
        if op in ("station_count", "tombstone_count", "citation"):
            return {op: getattr(self.release(req), op)}
        if op == "stats":
            return {"stats": plain(self.release(req).stats)}
        if op == "constituent_names":
            return {"names": list(self.release(req).constituent_names)}
        if op == "conventions":
            return {"conventions": [pick(x, CONVENTION) for x in self.release(req).conventions]}
        if op == "convention":
            x = self.release(req).convention(a["convention_id"])
            return {"convention": None if x is None else pick(x, CONVENTION)}
        if op == "licences":
            return {"licences": [pick(x, LICENCE) for x in self.release(req).licences]}
        if op == "licence":
            x = self.release(req).licence(a["licence_id"])
            return {"licence": None if x is None else pick(x, LICENCE)}
        if op == "attribution":
            t = self.target(req)
            if "station_ids" in a:
                stations = [t.station(i) for i in a["station_ids"]]
                return {"attribution": t.attribution([s for s in stations if s is not None])}
            return {"attribution": t.attribution()}
        if op in ("station", "require_station"):
            return {"station": enc_station(getattr(self.target(req), op)(a["station_id"]))}
        if op == "tombstone":
            return {"tombstone": enc_tombstone(self.target(req).tombstone(a["station_id"]))}
        if op == "station_by_alias":
            s = self.target(req).station_by_alias(a["system"], a["alias_id"])
            return {"station_id": None if s is None else s.station_id}
        if op == "stations":
            return {"station_ids": [s.station_id for s in self.target(req).stations(**filters)]}
        if op == "iter_stations":
            return {"station_ids": [s.station_id for s in self.target(req).iter_stations(**filters)]}
        if op == "search":
            kw = {k: a[k] for k in ("limit", "match") if k in a}
            return {"station_ids": [s.station_id for s in self.target(req).search(name=a["name"], **kw, **filters)]}
        if op == "near":
            kw = {k: a[k] for k in ("lat", "lon", "radius_km", "limit") if k in a}
            hits = self.target(req).near(**kw, **filters)
            return {"station_ids": [h.station.station_id for h in hits], "distance_km": [h.distance_km for h in hits]}
        if op == "nearest":
            kw = {k: a[k] for k in ("lat", "lon", "max_km") if k in a}
            h = self.target(req).nearest(**kw, **filters)
            return {"station_id": None if h is None else h.station.station_id, "distance_km": None if h is None else h.distance_km}
        if op == "reference_station":
            st = self.station(req, a)
            ref = None if st is None else self.target(req).reference_station(st)
            return {"station_id": None if ref is None else ref.station_id}
        if op == "subordinates_of":
            st = self.station(req, a)
            return {"station_ids": [] if st is None else [s.station_id for s in self.target(req).subordinates_of(st)]}
        if op == "station_validation":
            st = self.station(req, a)
            return {"validation": [] if st is None else enc_validation(st.validation)}
        if op == "subordinate_offsets":
            st = self.station(req, a)
            off = None if st is None else st.subordinate_offsets
            return {"offsets": None if off is None else pick(off, OFFSETS)}
        if op == "recommended_set":
            st = self.station(req, a)
            rs = None if st is None else st.recommended_set
            return {"set_id": None if rs is None else rs.set_id}
        if op == "constant_sets":
            st = self.station(req, a)
            kw = {"include_excluded": a["include_excluded"]} if "include_excluded" in a else {}
            return {"set_ids": [] if st is None else [cs.set_id for cs in st.constant_sets(**kw)]}
        if op == "constant_set":
            return {"set": enc_set(self.set(req, a))}
        if op == "constituents":
            cs = self.set(req, a)
            return {"constituents": [] if cs is None else [pick(x, CONSTITUENT) for x in cs.constituents]}
        if op == "constituent":
            cs = self.set(req, a)
            x = None if cs is None else cs.constituent(a["name"])
            return {"constituent": None if x is None else pick(x, CONSTITUENT)}
        if op == "provenance":
            cs = self.set(req, a)
            if cs is None:
                return {"provenance": None, "raw": None}
            return {"provenance": pick(cs.provenance, PROVENANCE), "raw": plain(cs.provenance.raw)}
        if op == "set_validation":
            cs = self.set(req, a)
            return {"validation": [] if cs is None else enc_validation(cs.validation)}
        if op == "raw":
            obj = a["object"]
            r = self.release(req)
            if obj == "station":
                x = self.station(req, a)
            elif obj == "tombstone":
                x = self.target(req).tombstone(a["station_id"])
            elif obj == "set":
                x = self.set(req, a)
            elif obj == "constituent":
                cs = self.set(req, a)
                x = None if cs is None else cs.constituent(a["name"])
            elif obj == "convention":
                x = r.convention(a["convention_id"])
            elif obj == "licence":
                x = r.licence(a["licence_id"])
            else:
                raise ValueError(f"unknown raw object {obj!r}")
            return {"raw": None if x is None else plain(x.raw)}
        raise ValueError(f"unknown op {op!r}")


ERROR_FIELDS = ("url", "status", "file", "expected", "actual", "path")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--installed", action="store_true", help="import the installed package, not python/src")
    a = ap.parse_args()
    if not a.installed:
        sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "python" / "src"))
    out = sys.stdout
    out.write(json.dumps({"hello": {"runner": "python", "version": _version(), "features": FEATURES}}) + "\n")
    out.flush()
    runner = Runner()
    for line in sys.stdin:
        if not line.strip():
            continue
        req = json.loads(line)
        try:
            reply = {"ok": True, "result": runner.handle(req)}
        except Exception as e:  # noqa: BLE001 - the protocol reports every exception
            base = None
            try:
                base = runner._sdk().OpenTideConstantsError
            except Exception:
                pass
            if base is not None and isinstance(e, base):
                fields = {}
                for f in ERROR_FIELDS:
                    v = getattr(e, f, None)
                    if v is not None:
                        fields[f] = v if isinstance(v, (int, str, float)) else str(v)
                reply = {"ok": False, "error": {"code": e.code, "message": str(e), "fields": fields}}
            else:
                print(f"uncaught {type(e).__name__}: {e}", file=sys.stderr)
                reply = {"ok": False, "error": {"code": f"uncaught:{type(e).__name__}", "message": str(e)}}
        out.write(json.dumps(reply) + "\n")
        out.flush()
    if runner.client is not None:
        runner.client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
