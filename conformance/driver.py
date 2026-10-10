# /// script
# requires-python = ">=3.10"
# ///
"""Conformance driver (SDK spec §7.1).

Starts the fixture server and the recording proxy, sends each case in
conformance/cases/ to a runner, one step at a time, and compares each reply with
the case's expectation. The protocol, the case format and the result encodings
are in conformance/README.md.

    uv run conformance/driver.py --runner "python3 conformance/runners/null/runner.py"
    uv run conformance/driver.py --runner "..." --only 'search/' --all-steps --report out.json
    uv run conformance/driver.py --check-cases     (lint the case files; no runner)
    uv run conformance/driver.py --selftest        (check the fixture server and proxy; no runner)
    uv run conformance/driver.py --list            (print the expanded case ids)

Exit status: 0 when at least one case ran and every case that ran passed; 1 when
a case failed or no case ran; 2 for a usage error, a case-file error, a runner
that fails the handshake, or a harness error (an exception in the driver while
it ran a case; the case is reported as failed and the run goes on).
"""
from __future__ import annotations

import argparse
import copy
import fnmatch
import gzip
import hashlib
import http.client
import json
import math
import os
import queue
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from server import FixtureServer, RecordingProxy, array_index, json_pointer, pointer_parts, validate_rule  # noqa: E402
import stream_index  # noqa: E402

FIXTURES = HERE / "fixtures"
CASES_DIR = HERE / "cases"
CROSS_DIR = HERE / "cross"
DEFAULT_TOL = 1e-9
FEATURES = ["fs", "fetch", "json", "eager", "stream", "require_checksum", "https_proxy"]
# The features of Python, Ruby and TypeScript on Node. require_checksum is the C open option (otc_open_options), which
# no other SDK has (CR2 DR34). https_proxy: a proxy reached over TLS (CR2 DR39); Ruby's Net::HTTP has none.
LANG_FEATURES = ["fs", "fetch", "json", "eager", "stream"]
RESERVED_EXPECT = {"error", "error_fields", "error_message", "tolerance"}

# Open variants for matrix cases: (suffix, file extension or None for the server, mode, features needed)
VARIANTS = [
    ("json", ".json", "eager", ["fs", "json", "eager"]),
    ("json.gz", ".json.gz", "eager", ["fs", "json", "eager"]),
    ("jsonl", ".jsonl", "eager", ["fs", "eager"]),
    ("jsonl-stream", ".jsonl", "stream", ["fs", "stream"]),
    ("server", None, "eager", ["fs", "fetch", "eager"]),  # the variant passes cache_dir, an fs option
]

FILTERS = ["country", "type", "kind", "source", "source_type"]
OPEN_ARGS = ["release", "file", "cache_dir", "offline", "mode", "base_url", "timeout", "proxy", "ca_file", "user_agent",
             "on_network_error", "auto_update", "update_interval", "verify_on_open",
             "require_checksum",   # require_checksum: C only, so a step that passes it needs that feature (CR2 DR34)
             "commercial_only"]    # K-NC DR106 (C: otc_open_options.commercial_only)
# op -> allowed argument names (README "Operations")
OPS = {
    "open": OPEN_ARGS, "close": [], "hold_release": ["name"], "loaded_from": [], "last_error": [],
    "release_metadata": [], "release_files": [], "releases": [], "latest": [], "check_for_update": [], "update": [],
    "download": ["release", "to", "formats", "overwrite"], "verify": [], "cached_releases": [], "prune": ["keep"],
    "station_count": [], "tombstone_count": [], "stats": [], "constituent_names": [], "conventions": [],
    "convention": ["convention_id"], "licences": [], "licence": ["licence_id"], "citation": [], "attribution": ["station_ids"],
    "station": ["station_id"], "require_station": ["station_id"], "tombstone": ["station_id"],
    "station_by_alias": ["system", "alias_id"], "stations": FILTERS, "iter_stations": FILTERS,
    "search": ["name", "limit", "match"] + FILTERS, "near": ["lat", "lon", "radius_km", "limit"] + FILTERS,
    "nearest": ["lat", "lon", "max_km"] + FILTERS, "reference_station": ["station_id", "station_on"], "subordinates_of": ["station_id", "station_on"],
    "station_validation": ["station_id"], "subordinate_offsets": ["station_id"], "recommended_set": ["station_id"],
    "constant_sets": ["station_id", "include_no_constants"], "constant_set": ["station_id", "set_id"],
    "constituents": ["station_id", "set_id"], "constituent": ["station_id", "set_id", "name"],
    "provenance": ["station_id", "set_id"], "set_validation": ["station_id", "set_id"],
    "newer_format_major": [],
    "raw": ["object", "station_id", "set_id", "name", "convention_id", "licence_id"],
}
PLACEHOLDERS = {"fixtures", "server", "server_alias", "server_tls", "tls_ca", "proxy", "tmp", "cache"}
# The fields of each driver action (README "Driver steps"): {action: (required {field: type}, optional {field: type})}.
# Any other field is a typo, and a typo of an assertion field (count, absent) would make the step assert nothing.
_STR, _LIST, _DICT, _BOOL, _NUM = str, list, dict, bool, (int, float)
_COUNT = "count"   # a non-negative integer
DRIVER_FIELDS = {
    "server_rules": ({"rules": _LIST}, {}), "server_stop": ({}, {}), "server_start": ({}, {}), "clear_log": ({}, {}),
    "assert_requests": ({}, {"source": _STR, "match": _STR, "status": int, "header": _DICT, "all": _BOOL,
                             "has_query": _BOOL, "count": _COUNT, "min": _COUNT, "max": _COUNT, "min_gap_s": _NUM}),
    "copy": ({"files": _LIST, "to": _STR}, {}), "write": ({"path": _STR, "text": _STR}, {}),
    "delete": ({"path": _STR}, {}), "mkdir": ({"path": _STR}, {}), "corrupt": ({"path": _STR}, {"offset": _COUNT}),
    "assert_files": ({"dir": _STR}, {"present": _LIST, "absent": _LIST, "exactly": _LIST, "no_tmp": _BOOL,
                                    "may_be_missing": _BOOL}),
    "assert_sha256": ({"path": _STR, "equals": _STR}, {"negate": _BOOL}),
    "assert_json": ({"path": _STR, "match": _DICT}, {}),
    "sleep": ({"s": _NUM}, {}), "restart_runner": ({}, {"env": _DICT}),
    "assert_index": ({"path": _STR, "jsonl": _STR, "datestamp": _STR}, {}),
    "json_set": ({"path": _STR, "pointer": _STR, "value": object}, {}),
    "chmod": ({"path": _STR, "mode": _STR}, {}),
    "assert_tree": ({"dir": _STR, "allow": _LIST}, {"may_be_missing": _BOOL}),
}
DRIVER_ACTIONS = set(DRIVER_FIELDS)
REQUEST_SOURCES = {"server", "tripwire", "proxy", "any"}
# A host name that never resolves (RFC 2606). Only the recording proxy knows it: it relays it to the
# fixture server. So a request to ${server_alias} succeeds only through the proxy, and no proxy-bypass
# rule for loopback addresses (Ruby's Net::HTTP has one) can hide that an SDK ignored the proxy.
SERVER_ALIAS = "otc-fixture.invalid"
# The features each SDK must claim (spec: Python, Ruby and TypeScript on Node have every feature).
# The profile is the hello's "runner" name, or --profile.
PROFILES = {
    "python": LANG_FEATURES + ["https_proxy"], "ruby": LANG_FEATURES, "typescript": LANG_FEATURES + ["https_proxy"],
    "typescript-browser": ["fetch", "json", "eager", "stream"],
    "c": ["fs", "stream", "require_checksum"], "c-fetch": ["fs", "fetch", "stream", "require_checksum", "https_proxy"],
    "none": [],
}


class CaseError(Exception):
    pass


# --------------------------------------------------------------------------- expected failures

EXPECTED_FAILURES = HERE / "expected-failures.json"
# The runner names an entry may list: the profiles (a hello's "runner"), and "cross" for a --cross run.
XF_RUNNERS = {"python", "ruby", "typescript", "typescript-browser", "c", "c-fetch", "cross"}
# The --cross names the CI and the gates use; a cross entry's case pattern must match one of these expansions.
CROSS_NAMES = ["python", "ruby", "typescript", "c"]


def load_expected_failures(path):
    """The entries of an expected-failures file (README "Expected failures"). ValueError for a malformed file."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    entries = doc.get("entries") if isinstance(doc, dict) else None
    if not isinstance(entries, list):
        raise ValueError(f"{path}: needs an object with an entries list")
    for i, e in enumerate(entries):
        if not (isinstance(e, dict) and isinstance(e.get("case"), str) and e["case"]
                and isinstance(e.get("runners"), list) and e["runners"] and all(isinstance(r, str) for r in e["runners"])):
            raise ValueError(f"{path}: entry {i} needs a case pattern and a non-empty runners list: {json.dumps(e)[:200]}")
    return entries


def expected_failure(entries, case_id, runner):
    """The entry that expects case_id to fail for this runner, or None. case is an exact id or an fnmatch pattern."""
    for e in entries:
        if runner in e["runners"] and case_names(e["case"], case_id):
            return e
    return None


def expected_failure_covers(entry, failures):
    """Whether an entry covers these failures: a wrong answer, never a harness error or a runner that crashed, hung or
    broke the protocol (those are FAIL even for a listed case); with "step", the first failure must be at that step."""
    if not failures or any(f.get("harness_error") or f.get("runner_fault") for f in failures):
        return False
    return "step" not in entry or failures[0].get("step") == entry["step"]


def case_names(pattern, case_id):
    """An exact case id, or an fnmatch pattern (a cross id's [writer>reader] is matched exactly, not as a class)."""
    return case_id == pattern or fnmatch.fnmatchcase(case_id, pattern)


def expected_failure_problems(path, plain_ids, cross_ids):
    """Lint an expected-failures file: known runner names, a package and a reason, and a case pattern that names at
    least one case id (plain ids for the plain runners; cross ids expanded with CROSS_NAMES for "cross")."""
    try:
        entries = load_expected_failures(path)
    except (OSError, ValueError) as e:
        return [f"expected-failures: {e}"]
    out = []
    for i, e in enumerate(entries):
        where = f"expected-failures entry {i} ({e['case']})"
        for r in e["runners"]:
            if r not in XF_RUNNERS:
                out.append(f"{where}: unknown runner {r!r} (one of {sorted(XF_RUNNERS)})")
        for k in ("package", "reason"):
            if not isinstance(e.get(k), str) or not e[k]:
                out.append(f"{where}: needs a {k}")
        if "step" in e and (isinstance(e["step"], bool) or not isinstance(e["step"], int) or e["step"] < 0):
            out.append(f"{where}: step must be a step index (an integer of 0 or more), got {e['step']!r}")
        unknown = sorted(set(e) - {"case", "runners", "package", "reason", "step"})
        if unknown:
            out.append(f"{where}: unknown field(s) {unknown}")
        ids = (cross_ids if "cross" in e["runners"] else []) + (plain_ids if set(e["runners"]) - {"cross"} else [])
        if not any(case_names(e["case"], c) for c in ids):
            out.append(f"{where}: the pattern names no case")
    return out


class RunnerError(Exception):
    """The runner broke the protocol (a line that is not JSON, a bad hello)."""


# --------------------------------------------------------------------------- matching

_MISSING = object()


def _type_name(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, (int, float)):
        return "number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, list):
        return "array"
    if isinstance(v, dict):
        return "object"
    return type(v).__name__


def is_matcher(v):
    return isinstance(v, dict) and len(v) == 1 and next(iter(v)).startswith("$")


def match(exp, act, tol, path="result"):
    """Return a list of mismatch messages (empty = match). Objects must have exactly the expected keys."""
    if act is _MISSING:
        return [f"{path}: missing"]
    if is_matcher(exp):
        (op, arg), = exp.items()
        if op == "$contains":
            return [] if isinstance(act, str) and arg in act else [f"{path}: {act!r} does not contain {arg!r}"]
        if op == "$not_contains":   # a string that does not hold arg (for example a secret in an error message)
            return [] if isinstance(act, str) and arg not in act else [f"{path}: {act!r} contains {arg!r} (or is not a string)"]
        if op == "$regex":
            return [] if isinstance(act, str) and re.search(arg, act) else [f"{path}: {act!r} does not match /{arg}/"]
        if op == "$type":
            return [] if _type_name(act) == arg else [f"{path}: expected a {arg}, got {_type_name(act)}"]
        if op == "$len_min":
            return [] if isinstance(act, (list, str, dict)) and len(act) >= arg else [f"{path}: expected length >= {arg}"]
        if op == "$any_of":
            for m in arg:
                if not match(m, act, tol, path):
                    return []
            return [f"{path}: {json.dumps(act)[:200]} matches none of {json.dumps(arg)[:200]}"]
        if op == "$all":
            out = []
            for m in arg:
                out += match(m, act, tol, path)
            return out
        raise CaseError(f"unknown matcher {op}")
    if isinstance(exp, dict):
        if not isinstance(act, dict):
            return [f"{path}: expected an object, got {_type_name(act)} {json.dumps(act)[:80]}"]
        out = []
        for k in exp:
            out += match(exp[k], act.get(k, _MISSING), tol, f"{path}.{k}")
        extra = sorted(set(act) - set(exp))
        if extra:
            out.append(f"{path}: unexpected keys {extra}")
        return out
    if isinstance(exp, list):
        if not isinstance(act, list):
            return [f"{path}: expected an array, got {_type_name(act)} {json.dumps(act)[:80]}"]
        if len(exp) != len(act):
            return [f"{path}: expected {len(exp)} items, got {len(act)}: {json.dumps(act)[:200]}"]
        out = []
        for i, (e, a) in enumerate(zip(exp, act)):
            out += match(e, a, tol, f"{path}[{i}]")
        return out
    if isinstance(exp, bool) or exp is None or isinstance(exp, str):
        return [] if (type(exp) is type(act) and exp == act) else [f"{path}: expected {json.dumps(exp)}, got {json.dumps(act)}"]
    if isinstance(exp, (int, float)):
        if isinstance(act, bool) or not isinstance(act, (int, float)):
            return [f"{path}: expected the number {exp}, got {json.dumps(act)}"]
        return [] if abs(exp - act) <= tol else [f"{path}: expected {exp!r}, got {act!r} (tolerance {tol})"]
    raise CaseError(f"cannot match {exp!r}")


MATCHERS = {"$contains", "$not_contains", "$regex", "$type", "$len_min", "$all", "$any_of"}
TYPE_NAMES = {"object", "array", "string", "number", "boolean", "null"}


def matcher_problems(v, path):
    """Lint an expected value: every matcher must be a known one with an argument of the right type, and a
    non-matcher object must not have a key that starts with "$" (a typo of a matcher would compare as data)."""
    out = []
    if isinstance(v, list):
        for i, x in enumerate(v):
            out += matcher_problems(x, f"{path}[{i}]")
    elif isinstance(v, dict):
        dollar = [k for k in v if isinstance(k, str) and k.startswith("$")]
        if dollar and len(v) != 1:
            return [f"{path}: an object with a $ key must be one matcher, got keys {sorted(v)}"]
        if not dollar:
            for k, x in v.items():
                out += matcher_problems(x, f"{path}.{k}")
            return out
        (op, arg), = v.items()
        if op not in MATCHERS:
            return [f"{path}: unknown matcher {op}"]
        if op in ("$contains", "$not_contains", "$regex") and not isinstance(arg, str):
            out.append(f"{path}: {op} needs a string")
        elif op == "$regex":
            try:
                re.compile(arg)
            except re.error as e:
                out.append(f"{path}: $regex {arg!r} is not a regular expression: {e}")
        elif op == "$type" and arg not in TYPE_NAMES:
            out.append(f"{path}: $type must be one of {sorted(TYPE_NAMES)}, got {arg!r}")
        elif op == "$len_min" and (isinstance(arg, bool) or not isinstance(arg, int) or arg < 0):
            out.append(f"{path}: $len_min needs a non-negative integer, got {arg!r}")
        elif op in ("$all", "$any_of"):
            if not isinstance(arg, list) or not arg:
                out.append(f"{path}: {op} needs a non-empty list")
            else:
                out += matcher_problems(arg, f"{path}.{op}")
    return out


def reply_problems(reply):
    """Check the shape of a runner reply (README "The runner protocol"); return problems."""
    if not isinstance(reply, dict) or "ok" not in reply:
        return [f"malformed reply {json.dumps(reply)[:200]}"]
    if not isinstance(reply["ok"], bool):
        return [f"malformed reply: ok is not a boolean: {json.dumps(reply)[:200]}"]
    if not reply["ok"]:
        e = reply.get("error")
        if not isinstance(e, dict):
            return [f"malformed reply: error is not an object: {json.dumps(reply)[:200]}"]
        if "fields" in e and e["fields"] is not None and not isinstance(e["fields"], dict):
            return [f"malformed reply: error.fields is not an object: {json.dumps(reply)[:200]}"]
    return []


def expect_shape_problems(expect):
    """An error expectation has only the reserved keys; a result expectation has no error_* keys."""
    if not isinstance(expect, dict):
        return [f"an expectation must be an object, got {_type_name(expect)}"]
    if "error" in expect:
        extra = sorted(set(expect) - RESERVED_EXPECT)
        return [f"an error expectation compares only {sorted(RESERVED_EXPECT)}; it also has {extra}"] if extra else []
    stray = sorted({"error_fields", "error_message"} & set(expect))
    return [f"{stray} need an \"error\" in the same expectation"] if stray else []


def evaluate(expect, reply):
    """Compare a runner reply with a step expectation; return mismatch messages."""
    bad = expect_shape_problems(expect)
    if bad:
        raise CaseError(bad[0])
    tol = expect.get("tolerance", DEFAULT_TOL)
    bad = reply_problems(reply)
    if bad:
        return bad
    if "error" in expect:
        if reply["ok"]:
            return [f"expected error {expect['error']!r}, got a result {json.dumps(reply.get('result'))[:200]}"]
        e = reply["error"]
        out = []
        if is_matcher(expect["error"]):   # several codes allowed (for example {"$any_of": ["io", "checksum_mismatch"]})
            if match(expect["error"], e.get("code", _MISSING), tol, "error.code"):
                out.append(f"expected error {json.dumps(expect['error'])}, got error {e.get('code')!r} ({str(e.get('message'))[:200]})")
        elif e.get("code") != expect["error"]:
            out.append(f"expected error {expect['error']!r}, got error {e.get('code')!r} ({str(e.get('message'))[:200]})")
        fields = e.get("fields") or {}
        for k, v in (expect.get("error_fields") or {}).items():
            out += match(v, fields.get(k, _MISSING), tol, f"error.fields.{k}")
        if "error_message" in expect:
            out += match(expect["error_message"], e.get("message", _MISSING), tol, "error.message")
        return out
    if not reply["ok"]:
        e = reply["error"]
        return [f"expected a result, got error {e.get('code')!r} ({str(e.get('message'))[:200]})"]
    result = reply.get("result")
    if not isinstance(result, dict):
        return [f"result is not an object: {json.dumps(result)[:200]}"]
    out = []
    for k, v in expect.items():
        if k in RESERVED_EXPECT:
            continue
        out += match(v, result.get(k, _MISSING), tol, f"result.{k}")
    return out


# --------------------------------------------------------------------------- cases

def load_cases(cases_dir: Path):
    cases = []
    for f in sorted(cases_dir.glob("*.json")):
        doc = json.loads(f.read_text(encoding="utf-8"))
        for c in doc["cases"]:
            c = dict(c)
            c["_file"] = f.name
            cases.append(c)
    return cases


def expand(cases):
    """Expand matrix cases into one case per open variant."""
    out = []
    for c in cases:
        m = c.get("matrix")
        if not m:
            out.append(c)
            continue
        for suffix, ext, mode, feats in VARIANTS:
            v = copy.deepcopy(c)
            v["id"] = f"{c['id']}@{suffix}"
            v["requires"] = sorted(set(c.get("requires", [])) | set(feats))
            rel = m["release"]
            if ext is None:
                args = {"release": rel, "base_url": f"${{server}}/{m['root']}/", "cache_dir": "${cache}", "mode": mode}
                exp = {"loaded_from": "download", "datestamp": rel}
            else:
                args = {"file": f"${{fixtures}}/{m['root']}/OTC_{rel}{ext}", "mode": mode}
                exp = {"loaded_from": "file", "datestamp": rel}
            exp.update(c.get("open_expect") or {})
            args.update(m.get("open_args") or {})
            # a step {"matrix_open": {...}} opens the case's release again in this variant, with the case's
            # open_args changed by the given ones (a null removes one), for example to compare with an option off
            steps = []
            for st in v["steps"]:
                if isinstance(st, dict) and "matrix_open" in st:
                    again = {**args, **st["matrix_open"]}
                    # the server variant's first open filled the cache: the pinned release now comes from it
                    again_exp = dict(exp, loaded_from="cache") if ext is None else dict(exp)
                    steps.append({"op": "open", "args": {k: x for k, x in again.items() if x is not None},
                                  "expect": again_exp})
                else:
                    steps.append(st)
            v["steps"] = [{"op": "open", "args": args, "expect": exp}] + steps
            out.append(v)
    return out


def subst(value, ctx):
    if isinstance(value, str):
        def rep(m):
            key = m.group(1)
            if key not in ctx:
                raise CaseError(f"unknown placeholder ${{{key}}}")
            return ctx[key]
        return re.sub(r"\$\{([a-z_]+)\}", rep, value)
    if isinstance(value, list):
        return [subst(v, ctx) for v in value]
    if isinstance(value, dict):
        return {subst(k, ctx): subst(v, ctx) for k, v in value.items()}
    return value


def case_timeout(case):
    """The case's timeout_s: a positive number of seconds (default 60)."""
    t = case.get("timeout_s", 60)
    if isinstance(t, bool) or not isinstance(t, (int, float)) or not t > 0:
        raise CaseError(f"timeout_s must be a positive number, got {t!r}")
    return float(t)


def structure_problems(c):
    """The shape of one case, checked before anything else reads it: a malformed case is a case-file error (exit 2)."""
    if not isinstance(c, dict):
        return [f"a case must be an object, got {_type_name(c)}"]
    cid = c.get("id")
    if not isinstance(cid, str) or not cid:
        return [f"{c.get('_file')}: a case needs a non-empty string id, got {cid!r}"]
    steps = c.get("steps")
    if not isinstance(steps, list):
        return [f"{cid}: steps must be a list"]
    out = []
    for i, st in enumerate(steps):
        where = f"{cid} step {i}"
        if not isinstance(st, dict):
            out.append(f"{where}: a step must be an object")
            continue
        if not isinstance(st.get("driver", st.get("op")), str):
            out.append(f"{where}: a step needs a string op or driver")
        if "args" in st and not isinstance(st["args"], dict):
            out.append(f"{where}: args must be an object")
        if "matrix_open" in st and not (st.get("op") == "open" and isinstance(st["matrix_open"], dict) and c.get("matrix")
                                        and "args" not in st and "expect" not in st):
            out.append(f"{where}: matrix_open needs a matrix case, op open, an object, and no args or expect")
        if st.get("expect") is not None and not isinstance(st["expect"], dict):
            out.append(f"{where}: expect must be an object")
        eim = st.get("expect_if_missing")
        if eim is not None and not (isinstance(eim, dict) and all(isinstance(v, dict) for v in eim.values())):
            out.append(f"{where}: expect_if_missing must be an object of expectations")
        who = st.get("as")
        if who is not None and not (isinstance(who, str) or (isinstance(who, list) and who and all(isinstance(r, str) for r in who))):
            out.append(f"{where}: 'as' must be a role name or a list of role names")
        if "on" in st and not isinstance(st["on"], str):
            out.append(f"{where}: 'on' must be a string")
    for k in ("requires",):
        if k in c and not (isinstance(c[k], list) and all(isinstance(f, str) for f in c[k])):
            out.append(f"{cid}: {k} must be a list of strings")
    if "roles" in c and not (isinstance(c["roles"], dict) and all(isinstance(v, list) for v in c["roles"].values())):
        out.append(f"{cid}: roles must be an object of feature lists")
    return out


API = HERE / "api.json"
# Error codes any fetch operation may give without being listed: a C build without otc_fetch answers not_built
# (conformance/README.md "expect_if_missing").
API_ANY_OP_ERRORS = {"not_built"}


def api_errors(api_path):
    """op name -> the error codes api.json lists for it, from the members of the objects a runner op calls."""
    api = json.loads(Path(api_path).read_text(encoding="utf-8"))
    out = {}
    for obj in ("Client", "Release", "Station", "ConstantSet"):
        for m in api["objects"][obj]["members"]:
            if "errors" in m:
                out.setdefault(m["name"], set()).update(m["errors"])
    return out


def api_error_problems(cases, errors_by_op):
    """K77: every error a case expects from an op must be in that operation's api.json errors list. After a close
    step, io is allowed for every op: api.json "after_close" states that rule once for every operation (CR D21)."""
    problems = []
    for c in cases:
        closed = False
        for i, st in enumerate(c.get("steps", [])):
            op = st.get("op")
            closed = closed or op == "close"
            if op not in errors_by_op:
                continue
            exps = [st.get("expect")] + list((st.get("expect_if_missing") or {}).values())
            for exp in exps:
                if isinstance(exp, dict) and "error" in exp:
                    e = exp["error"]
                    codes = e["$any_of"] if isinstance(e, dict) and isinstance(e.get("$any_of"), list) else [e]
                    known = errors_by_op[op] | API_ANY_OP_ERRORS
                    for code in codes:
                        if isinstance(code, str):
                            bad = code not in known and not (closed and code == "io")   # io after a close (CR2 DR32)
                        elif is_matcher(code):   # a matcher ($regex, ...) must match at least one code api.json lists
                            try:
                                bad = all(match(code, k, DEFAULT_TOL, "error") for k in sorted(known))
                            except (CaseError, TypeError, re.error):
                                bad = True       # matcher_problems reports the malformed matcher itself
                        else:
                            bad = True           # a number, null, list or object is never an error code
                        if bad:
                            problems.append(f"{c.get('id')} step {i}: op {op} expects error {json.dumps(code)}, "
                                            f"which matches no code api.json lists for {op} ({sorted(errors_by_op[op])})")
    return problems


FETCH_OPS = {"releases", "latest", "check_for_update", "newer_format_major", "update", "download", "cached_releases", "prune"}


def step_needs(st):
    """The runner features a runner step uses (README "Hello" feature table)."""
    op, a = st.get("op"), st.get("args") or {}
    need = set()
    if op == "open":
        if a.get("mode") in ("eager", "stream"):
            need.add(a["mode"])
        f = a.get("file")
        if isinstance(f, str):
            need.add("fs")
            if f.endswith((".json", ".json.gz")) and not f.endswith(".meta.json"):
                need.add("json")
        elif "base_url" in a or "release" in a or "cache_dir" in a or not a:
            need.add("fetch")   # no file: the release comes from the network module
        if "cache_dir" in a:
            need.add("fs")      # README "Hello": cache_dir is a file-system option
        if "require_checksum" in a:
            need.add("require_checksum")   # the C open option (CR2 DR34)
        if isinstance(a.get("proxy"), str) and a["proxy"].startswith(("https:", "${server_tls}")):
            need.add("https_proxy")        # a proxy reached over TLS (CR2 DR39)
    if op in FETCH_OPS:
        need.add("fetch")
    if op == "download":
        need.add("fs")
    return need


def requires_problems(c):
    """K55/K56: every feature a runner step uses must be in the case's requires (for its role), or be covered by an
    expect_if_missing of that step or an earlier one (a runner without the feature stops there)."""
    out = []
    base = set(c.get("requires", []))
    roles = c.get("roles") or {"main": []}
    covered = {r: base | set(f) for r, f in roles.items()}
    for i, st in enumerate(c.get("steps", [])):
        if "op" not in st or "matrix_open" in st:   # a matrix_open step becomes the variant's open (expand)
            continue
        who = st.get("as", "main") if c.get("roles") else "main"
        eim = set(st.get("expect_if_missing") or {})
        for role in ([who] if isinstance(who, str) else who):
            if role not in covered:
                continue
            lacking = sorted(step_needs(st) - covered[role] - eim)
            if lacking:
                out.append(f"{c.get('id')} step {i}: op {st['op']} uses {', '.join(repr(f) for f in lacking)}, "
                           f"which the case does not require" + (f" for role {role}" if role != "main" else ""))
            covered[role] |= eim
    return out


def tolerance_problems(exp):
    """An expectation's tolerance must be a finite number of 0 or more (a string fails every runner at run time, and a
    negative one fails every number)."""
    if not isinstance(exp, dict) or "tolerance" not in exp:
        return []
    t = exp["tolerance"]
    if isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) or t < 0:
        return [f"tolerance must be a finite number of 0 or more, got {t!r}"]
    return []


def id_problems(expanded, cross):
    """Every case id is unique across the expanded cases/ (plain ids and matrix variants) and cross/: a duplicate makes
    --only and expected-failure patterns name two cases."""
    seen, out = {}, []
    for where, cs in (("cases/", expanded), ("cross/", cross)):
        for c in cs:
            cid = c.get("id")
            if cid in seen:
                out.append(f"duplicate id {cid!r} ({seen[cid]} and {where})")
            else:
                seen[cid] = where
    return out


def _field_ok(v, t):
    if t is object:
        return True
    if t == _COUNT:
        return isinstance(v, int) and not isinstance(v, bool) and v >= 0
    if t is _BOOL:
        return isinstance(v, bool)
    return not isinstance(v, bool) and isinstance(v, t)


def driver_step_problems(st):
    """The fields of one driver step: the known ones only, each of the right type, and enough of them for an
    assertion step to assert something. Returns problems (empty = good)."""
    kind = st.get("driver")
    if kind not in DRIVER_FIELDS:
        return [f"unknown driver action {kind!r}"]
    req, opt = DRIVER_FIELDS[kind]
    out = [f"{kind} needs {k!r}" for k in req if k not in st]
    unknown = sorted(set(st) - {"driver"} - set(req) - set(opt))
    if unknown:
        out.append(f"{kind} has no field(s) {unknown}")
    for k, t in {**opt, **req}.items():
        if k in st and not _field_ok(st[k], t):
            out.append(f"{kind} {k} has the wrong type: {st[k]!r}")
    lists = {"copy": ["files"], "assert_files": ["present", "absent", "exactly"], "assert_tree": ["allow"]}.get(kind, [])
    for k in lists:
        if isinstance(st.get(k), list) and not all(isinstance(x, str) for x in st[k]):
            out.append(f"{kind} {k} must be a list of strings")
    for k in (["env"] if kind == "restart_runner" else ["header"] if kind == "assert_requests" else []):
        if isinstance(st.get(k), dict) and not all(isinstance(x, str) and isinstance(y, str) for x, y in st[k].items()):
            out.append(f"{kind} {k} must be an object of strings")
    if kind == "assert_requests":
        if "source" in st and st["source"] not in REQUEST_SOURCES:
            out.append(f"assert_requests source must be one of {sorted(REQUEST_SOURCES)}, got {st['source']!r}")
        if not any(k in st for k in ("count", "min", "max", "min_gap_s")) and not st.get("all"):
            out.append("assert_requests asserts nothing: it needs count, min, max, min_gap_s or all")
        if st.get("all") and not st.get("header"):
            out.append("assert_requests all: true needs a header")
    if kind == "assert_files" and not any(k in st for k in ("present", "absent", "exactly")) and not st.get("no_tmp"):
        out.append("assert_files asserts nothing: it needs present, absent, exactly or no_tmp")
    if kind == "assert_json" and st.get("match") == {}:
        out.append("assert_json asserts nothing: match is empty")
    if kind == "sleep" and _field_ok(st.get("s"), _NUM) and st["s"] < 0:
        out.append(f"sleep s must be 0 or more, got {st['s']!r}")
    if kind == "chmod" and isinstance(st.get("mode"), str) and not re.fullmatch(r"[0-7]{3,4}", st["mode"]):
        out.append(f"chmod mode must be an octal string such as \"555\", got {st['mode']!r}")
    return out


def check_cases(cases):
    """Lint the case files. Returns a list of problems."""
    problems = []
    ids = set()
    for c in cases:
        cid = c.get("id")
        if not cid or cid in ids:
            problems.append(f"{c.get('_file')}: missing or duplicate id {cid!r}")
        ids.add(cid)
        compared = 0
        problems += requires_problems(c)
        try:
            case_timeout(c)
        except CaseError as e:
            problems.append(f"{cid}: {e}")
        env = c.get("env", {})
        if not isinstance(env, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in env.items()):
            problems.append(f"{cid}: env must be an object of strings")
        for s in re.findall(r"\$\{([a-z_]+)\}", json.dumps(env)):
            if s not in PLACEHOLDERS:
                problems.append(f"{cid}: env: unknown placeholder ${{{s}}}")
        roles = c.get("roles")
        if roles is not None and (not isinstance(roles, dict) or len(roles) < 2
                                  or any(f not in FEATURES for fs in roles.values() for f in fs)):
            problems.append(f"{cid}: roles must name two or more roles, each with a list of features")
        for i, st in enumerate(c.get("steps", [])):
            where = f"{cid} step {i}"
            if roles is not None and st.get("driver") != "restart_runner":
                who = st.get("as") if "driver" not in st else None
                if "driver" not in st and not all(r in roles for r in ([who] if isinstance(who, str) else who or [None])):
                    problems.append(f"{where}: 'as' must name roles of the case, got {who!r}")
            elif roles is not None:
                problems.append(f"{where}: restart_runner is not allowed in a case with roles")
            if roles is None and "as" in st:
                problems.append(f"{where}: 'as' needs the case to have roles")
            for s in re.findall(r"\$\{([a-z_]+)\}", json.dumps(st)):
                if s not in PLACEHOLDERS:
                    problems.append(f"{where}: unknown placeholder ${{{s}}}")
            for s in re.findall(r"\$\{fixtures\}/([^\"]+)", json.dumps(st)):
                if not (FIXTURES / s).exists():
                    problems.append(f"{where}: fixture file {s} does not exist")
            if "driver" in st:
                problems += [f"{where}: {p}" for p in driver_step_problems(st)]
                if st["driver"] == "assert_requests":
                    for name, rx in [("match", st.get("match"))] + list((st.get("header") or {}).items()):
                        try:
                            if rx is not None:
                                re.compile(rx)
                        except (re.error, TypeError) as e:
                            problems.append(f"{where}: assert_requests {name} {rx!r} is not a regular expression: {e}")
                if st["driver"] == "json_set":
                    try:
                        if not pointer_parts(st.get("pointer")):
                            raise ValueError("json_set cannot replace the whole document")
                    except ValueError as e:
                        problems.append(f"{where}: {e}")
                if st["driver"] == "server_rules":
                    for j, rule in enumerate(st.get("rules", [])):
                        try:
                            validate_rule(j, rule)
                        except ValueError as e:
                            problems.append(f"{where}: {e}")
                continue
            op = st.get("op")
            if op not in OPS:
                problems.append(f"{where}: unknown op {op!r}")
                continue
            for a in st.get("args", {}):
                if a not in OPS[op]:
                    problems.append(f"{where}: op {op} has no argument {a!r}")
            for exp in [st.get("expect")] + list((st.get("expect_if_missing") or {}).values()):
                if exp is None:
                    continue
                shape = expect_shape_problems(exp)
                problems += [f"{where}: {p}" for p in shape + matcher_problems(exp, "expect") + tolerance_problems(exp)]
                if not shape and "error" not in exp and not evaluate(exp, {"ok": True, "result": {}}):
                    problems.append(f"{where}: an empty result satisfies this expectation")
            if st.get("expect") is not None:
                compared += 1
            for f in (st.get("expect_if_missing") or {}):
                if f not in FEATURES:
                    problems.append(f"{where}: unknown feature {f!r}")
        for exp in [c.get("open_expect")] if isinstance(c.get("open_expect"), dict) else []:
            problems += [f"{cid} open_expect: {p}" for p in tolerance_problems(exp)]
        if compared == 0 and not c.get("matrix"):
            problems.append(f"{cid}: no runner step with an expectation")
        for f in c.get("requires", []):
            if f not in FEATURES:
                problems.append(f"{cid}: unknown feature {f!r}")
    return problems


# --------------------------------------------------------------------------- runner process

def _not_json(token):
    raise ValueError(f"{token} is not JSON")


class Runner:
    def __init__(self, cmd, env, stderr_path, cwd):
        self.cmd = cmd
        self.stderr_f = open(stderr_path, "ab")
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.stderr_f,
                                     env=env, cwd=cwd)
        self.lines = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        for line in self.proc.stdout:
            self.lines.put(line)
        self.lines.put(None)

    def read(self, timeout):
        try:
            line = self.lines.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError(f"no reply within {timeout} s")
        if line is None:
            try:
                status = self.proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                status = None
            raise EOFError(f"runner closed its stdout (exit status {status})")
        try:
            return json.loads(line, parse_constant=_not_json)
        except ValueError:  # JSONDecodeError, or NaN / Infinity, which are not JSON
            raise RunnerError(f"runner printed a line that is not JSON: {line[:200]!r}")

    def send(self, msg):
        self.proc.stdin.write((json.dumps(msg) + "\n").encode())
        self.proc.stdin.flush()

    def close(self):
        """Close stdin and wait for the runner. Returns its exit status (None if it had to be killed)."""
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        try:
            status = self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
            status = None
        self.stderr_f.close()
        return status


def parse_hello(line):
    """Validate the runner's first line: {"hello": {"runner": str, "features": [str, ...], ...}}."""
    if not isinstance(line, dict) or not isinstance(line.get("hello"), dict):
        raise RunnerError(f"first line is not a hello object: {json.dumps(line)[:200]}")
    hello = line["hello"]
    if "runner" in hello and not isinstance(hello["runner"], str):
        raise RunnerError(f"hello.runner is not a string: {json.dumps(hello)[:200]}")
    feats = hello.get("features")
    if not isinstance(feats, list) or not all(isinstance(f, str) for f in feats):
        raise RunnerError(f"hello.features is not a list of strings: {json.dumps(hello)[:200]}")
    return hello


def isolated_env(tmp: Path):
    """Point every per-user directory an SDK might default to at a fresh directory under tmp."""
    home = tmp / "home"
    home.mkdir(parents=True, exist_ok=True)
    return {"HOME": str(home), "USERPROFILE": str(home), "XDG_CACHE_HOME": str(tmp / "xdg-cache"),
            "LOCALAPPDATA": str(tmp / "localappdata")}


def probe_runner(cmd):
    """Start the runner once and read its hello. Returns (hello, None) or (None, error text with the stderr tail)."""
    d = Path(tempfile.mkdtemp(prefix="otc-probe-"))
    try:
        probe = None
        try:
            probe = Runner(cmd, runner_env(isolated_env(d)), d / "stderr", cwd=str(HERE.parent))
            return parse_hello(probe.read(60)), None
        except (TimeoutError, EOFError, RunnerError, OSError) as e:
            err = f"{type(e).__name__}: {e}"
        finally:
            if probe:
                probe.close()
        tail = (d / "stderr").read_text(errors="replace")[-2000:] if (d / "stderr").exists() else ""
        return None, err + (f"\nrunner stderr:\n{tail}" if tail.strip() else "\n(the runner wrote nothing to stderr)")
    finally:
        shutil.rmtree(d, ignore_errors=True)


def runner_env(extra):
    env = {k: v for k, v in os.environ.items()
           if not k.upper().startswith("OPENTIDECONSTANTS_") and k.upper() not in ("HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "ALL_PROXY")}
    env.update(extra)
    return env


# --------------------------------------------------------------------------- driver actions

def sha256_file(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def act_assert_requests(a, srv, proxy):
    src = a.get("source", "server")
    entries = []
    if src in ("server", "any"):
        entries += [e for e in srv.log.entries() if e["source"] == "server"]
    if src in ("tripwire", "any"):
        entries += [e for e in srv.log.entries() if e["source"] == "tripwire"]
    if src in ("proxy", "any"):
        entries += proxy.log.entries()
    entries.sort(key=lambda e: e["t"])
    if "match" in a:
        rx = re.compile(a["match"])  # compile first: a bad pattern is a case error even when the log is empty
        entries = [e for e in entries if e["path"] and rx.search(e["path"])]
    if "status" in a:
        entries = [e for e in entries if e["status"] == a["status"]]
    if a.get("has_query"):
        entries = [e for e in entries if e["query"] or (e["path"] and "?" in e["path"])]
    problems = []
    hdr = a.get("header") or {}
    # compile first: a bad pattern is a case error even when the log is empty
    hdr_rx = {name: re.compile(rx) for name, rx in hdr.items()}
    if hdr:
        def ok(e):
            return all(rx.search(e["headers"].get(name.lower(), "")) for name, rx in hdr_rx.items())
        if a.get("all"):
            bad = [e for e in entries if not ok(e)]
            if not entries:
                problems.append(f"no request to check the header {hdr} on (all: true needs at least one)")
            if bad:
                problems.append(f"{len(bad)} request(s) fail the header check {hdr}: e.g. {bad[0]['path']} {bad[0]['headers']}")
        else:
            entries = [e for e in entries if ok(e)]
    n = len(entries)
    desc = f"requests(source={src}, match={a.get('match')!r}, status={a.get('status')}, header={hdr or None})"
    if "count" in a and n != a["count"]:
        problems.append(f"{desc}: expected {a['count']}, saw {n}: {[(e['path'], e['status']) for e in entries][:10]}")
    if "min" in a and n < a["min"]:
        problems.append(f"{desc}: expected at least {a['min']}, saw {n}")
    if "max" in a and n > a["max"]:
        problems.append(f"{desc}: expected at most {a['max']}, saw {n}")
    if "min_gap_s" in a:
        gaps = [b["t"] - x["t"] for x, b in zip(entries, entries[1:])]
        if not gaps or min(gaps) < a["min_gap_s"]:
            problems.append(f"{desc}: expected gaps >= {a['min_gap_s']} s, saw {[round(g, 2) for g in gaps]}")
    return problems


def act_assert_files(a):
    d = Path(a["dir"])
    if not d.is_dir():
        if a.get("may_be_missing") and not a.get("present") and not a.get("exactly"):
            return []
        return [f"{d}: not a directory"]
    names = sorted(p.name for p in d.iterdir())
    out = []
    for n in a.get("present", []):
        if n not in names:
            out.append(f"{d}: {n} is missing (have {names})")
    for n in a.get("absent", []):
        if n in names:
            out.append(f"{d}: {n} should not be there")
    if "exactly" in a and names != sorted(a["exactly"]):
        out.append(f"{d}: expected exactly {sorted(a['exactly'])}, have {names}")
    if a.get("no_tmp"):
        tmp = [n for n in names if n.startswith(".tmp-")]
        if tmp:
            out.append(f"{d}: temporary files left: {tmp}")
    return out


def act_assert_tree(a):
    """Every file and directory under dir (relative, with /) must match one of the allow globs (fnmatch)."""
    d = Path(a["dir"])
    if not d.is_dir():
        return [] if a.get("may_be_missing") else [f"{d}: not a directory"]
    bad = sorted(p.relative_to(d).as_posix() for p in d.rglob("*")
                 if not any(fnmatch.fnmatchcase(p.relative_to(d).as_posix(), g) for g in a["allow"]))
    return [f"{d}: paths outside {a['allow']}: {bad[:10]}"] if bad else []


def restore_writable(root):
    """Give the owner write and search permission again under root (after chmod steps), so it can be removed. Top
    down: each directory is fixed before it is listed, so a directory under one with no read bit (000) is reached."""
    p = Path(root)
    try:
        if p.is_symlink():
            return
        p.chmod(p.stat().st_mode | (0o700 if p.is_dir() else 0o600))
        children = list(p.iterdir()) if p.is_dir() else []
    except OSError:
        return
    for c in children:
        restore_writable(c)


def run_action(st, ctx, srv, proxy):
    """Run a driver action. Returns (problems, restart_env or None)."""
    bad = driver_step_problems(st)
    if bad:   # a step that would assert nothing, or a typo: the case file is wrong (a harness error), not the SDK
        raise CaseError(f"driver step: {bad[0]}")
    a = subst(st, ctx)
    kind = a["driver"]
    if kind == "server_rules":
        srv.set_rules(a.get("rules", []))
    elif kind == "server_stop":
        srv.stop()
    elif kind == "server_start":
        srv.resume()
    elif kind == "clear_log":
        srv.log.clear()
        proxy.log.clear()
    elif kind == "assert_requests":
        return act_assert_requests(a, srv, proxy), None
    elif kind == "copy":
        to = Path(a["to"])
        to.mkdir(parents=True, exist_ok=True)
        for f in a["files"]:
            shutil.copy2(f, to / Path(f).name)
    elif kind == "write":
        p = Path(a["path"])
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(a["text"], encoding="utf-8")
    elif kind == "delete":
        Path(a["path"]).unlink()
    elif kind == "mkdir":
        Path(a["path"]).mkdir(parents=True, exist_ok=True)
    elif kind == "corrupt":
        p = Path(a["path"])
        if not p.is_file():
            return [f"corrupt: {p} does not exist"], None
        data = bytearray(p.read_bytes())
        if not data:
            return [f"corrupt: {p} is empty"], None
        i = a.get("offset", 0) % len(data)
        data[i] ^= 0x01
        p.write_bytes(bytes(data))
    elif kind == "assert_files":
        return act_assert_files(a), None
    elif kind == "assert_tree":
        return act_assert_tree(a), None
    elif kind == "chmod":   # POSIX permissions: mode is an octal string such as "555"
        Path(a["path"]).chmod(int(str(a["mode"]), 8))
    elif kind == "assert_sha256":
        p = Path(a["path"])
        if not p.is_file():
            return [f"{p}: missing"], None
        want = a["equals"] if re.fullmatch(r"[0-9a-f]{64}", a["equals"]) else sha256_file(a["equals"])
        same = sha256_file(p) == want
        if same == bool(a.get("negate")):
            return [f"{p}: SHA-256 {'equals' if same else 'differs from'} {a['equals']}"], None
    elif kind == "assert_json":
        p = Path(a["path"])
        if not p.is_file():
            return [f"{p}: missing"], None
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except ValueError as e:
            return [f"{p}: not JSON ({e})"], None
        out = []
        for k, v in a["match"].items():
            if k.startswith("/"):   # an RFC 6901 pointer into the document (for example the value a json_set wrote)
                try:
                    got = json_pointer(doc, k)
                except (KeyError, IndexError, ValueError):
                    got = _MISSING
                out += match(v, got, DEFAULT_TOL, f"{p.name}{k}")
            else:
                out += match(v, doc.get(k, _MISSING) if isinstance(doc, dict) else _MISSING, DEFAULT_TOL, f"{p.name}.{k}")
        return out, None
    elif kind == "sleep":
        time.sleep(float(a["s"]))
    elif kind == "restart_runner":
        return [], a.get("env", {})
    elif kind == "assert_index":
        return act_assert_index(a), None
    elif kind == "json_set":
        p, value = Path(a["path"]), a["value"]   # a missing value is a case-file error (driver_step_problems)
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            return [f"json_set: {p}: cannot read it as JSON ({e})"], None
        try:
            parts = pointer_parts(a["pointer"])
            if not parts:
                raise ValueError("json_set cannot replace the whole document")
            node = json_pointer(doc, "".join("/" + x.replace("~", "~0").replace("/", "~1") for x in parts[:-1]))
            if isinstance(node, list):
                node[array_index(parts[-1], len(node))] = value
            elif isinstance(node, dict):
                node[parts[-1]] = value
            else:
                raise TypeError(type(node).__name__)
        except (KeyError, IndexError, ValueError, TypeError) as e:
            return [f"json_set: {p.name}: the pointer {a['pointer']} does not resolve ({type(e).__name__}: {e})"], None
        p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return [], None


def act_assert_index(a):
    """Compare the index-v1.json an SDK wrote with the reference index built from the same .jsonl (§6.2)."""
    p, jsonl = Path(a["path"]), Path(a["jsonl"])
    if not p.is_file():
        return [f"{p}: missing"]
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as e:
        return [f"{p}: not JSON ({e})"]
    # the .jsonl is the SDK's cache copy: a missing or unreadable one is the SDK's fault (a step failure), not the harness's
    if not jsonl.is_file():
        return [f"{jsonl}: missing"]
    try:
        ref = stream_index.build(jsonl, a["datestamp"])
    except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError) as e:
        return [f"{jsonl}: cannot build the reference index from it ({type(e).__name__}: {e})"]
    return [f"{p.name}: {x}" for x in stream_index.compare(doc, ref)][:20]


# --------------------------------------------------------------------------- run one case

def run_case(case, runners, srv, proxy, keep_tmp, all_steps, stats):
    """Run one case. runners: {role: (command, features)}; a case without roles has the one role "main"."""
    tmp = Path(tempfile.mkdtemp(prefix="otc-conf-"))
    ctx = {"fixtures": str(FIXTURES), "server": srv.url, "server_alias": f"http://{SERVER_ALIAS}:{srv.port}", "proxy": proxy.url, "tmp": str(tmp), "cache": str(tmp / "cache")}
    if srv.tls_url:   # the https listener (start_tls); a case that names it on a server without one is a case error
        ctx.update({"server_tls": srv.tls_url, "tls_ca": srv.tls_ca})
    env_extra = isolated_env(tmp)
    srv.set_rules([])
    srv.log.clear()
    srv.errors.clear()
    srv.trip_errors.clear()
    proxy.log.clear()
    proxy.errors.clear()
    failures = []
    live = {}
    step_timeout = 60.0

    def stderr_path(role):
        return tmp / ("runner.stderr" if role == "main" else f"runner-{role}.stderr")

    def start(role):
        r = Runner(runners[role][0], runner_env(env_extra), stderr_path(role), cwd=str(HERE.parent))
        try:
            parse_hello(r.read(60))
        except BaseException:
            r.close()
            raise
        return r

    def check(i, st, role, msg, reply, expect):
        if expect is None:
            # an uncompared step still must not fail: a malformed or ok:false reply fails the case
            problems = reply_problems(reply) or (
                [f"unexpected error {reply['error'].get('code')!r} ({str(reply['error'].get('message'))[:200]})"]
                if not reply["ok"] else [])
        else:
            stats["steps_compared"] += 1
            problems = evaluate(subst(expect, ctx), reply)
        if problems:
            stats["steps_failed"] += 1
            f = {"step": i, "op": st["op"], "args": msg["args"], "problems": problems}
            if role != "main":
                f["as"] = role
            failures.append(f)
        return bool(problems)

    cur = {"step": None}
    try:
        # case fields: a bad env or timeout_s is a harness error of this case (inside the try, so tmp is removed)
        env_extra.update(subst(case.get("env", {}), ctx))
        step_timeout = case_timeout(case)
        for role in runners:
            live[role] = start(role)
        for i, st in enumerate(case["steps"]):
            cur = {"step": i, "driver": st["driver"]} if "driver" in st else {"step": i, "op": st.get("op")}
            if "driver" in st:
                try:
                    problems, restart_env = run_action(st, ctx, srv, proxy)
                except OSError as e:  # a file the case names is missing, or the server cannot stop: not the SDK
                    raise CaseError(f"driver action {st['driver']}: {type(e).__name__}: {e}") from e
                if restart_env is not None:
                    status = live.pop("main").close()
                    if status != 0:
                        failures.append({"step": i, "driver": "restart_runner", "runner_fault": True,
                                         "problems": [f"the runner exited with status {status} when it was stopped"]})
                        if not all_steps:   # a failed step stops the case, as every other one does
                            break
                    env_extra.update(restart_env)
                    live["main"] = start("main")
                if problems:
                    failures.append({"step": i, "driver": st["driver"], "problems": problems})
                    if not all_steps:
                        break
                continue
            who = st.get("as", "main")
            roles = [who] if isinstance(who, str) else list(who)
            msg = {"case": case["id"], "step": i, "op": st["op"], "args": subst(st.get("args", {}), ctx)}
            if st.get("on"):
                msg["on"] = st["on"]
            plan = []
            for role in roles:
                expect, last = st.get("expect"), False
                for feat, alt in (st.get("expect_if_missing") or {}).items():
                    if feat not in runners[role][1]:
                        expect, last = alt, True
                        break
                plan.append((role, expect, last))
            # every role gets the request before any reply is read, so a step with several roles runs at once
            for role, _, _ in plan:
                cur = {"step": i, "op": st.get("op"), **({"as": role} if role != "main" else {})}
                live[role].send(msg)
            failed = last_step = False
            for role, expect, last in plan:
                cur = {"step": i, "op": st.get("op"), **({"as": role} if role != "main" else {})}
                failed |= check(i, st, role, msg, live[role].read(step_timeout), expect)
                last_step |= last
            if (failed and not all_steps) or last_step:
                break
    except (TimeoutError, EOFError, RunnerError, OSError) as e:   # the runner crashed, hung or broke the protocol
        failures.append({**cur, "runner_fault": True, "problems": [f"{type(e).__name__}: {e}"]})
    except Exception as e:  # a case-file or driver error: fail this case, flag the run, go on
        stats["harness_errors"] += 1
        failures.append({**cur, "harness_error": True, "problems": [f"harness error: {type(e).__name__}: {e}"]})
    finally:
        for role, r in live.items():
            status = r.close()
            if status != 0 and not failures:  # a runner that fails at shutdown (a close() error) fails the case
                failures.append({"step": None, "runner_fault": True, **({"as": role} if role != "main" else {}),
                                 "problems": [f"the runner exited with status {status} at the end of the case"]})
        if srv.errors:  # a server rule that could not be applied: the harness is wrong, not the SDK
            stats["harness_errors"] += 1
            failures.append({"step": None, "driver": "server", "harness_error": True,
                             "problems": [f"harness error: fixture server: {e}" for e in srv.errors[:5]]})
        if proxy.errors:  # the recording proxy could not relay: a 502 the SDK saw is the harness's fault
            stats["harness_errors"] += 1
            failures.append({"step": None, "driver": "proxy", "harness_error": True,
                             "problems": [f"harness error: recording proxy: {e}" for e in proxy.errors[:5]]})
        if srv.trip_errors:  # the tripwire could not accept: "no connection was made" checks would pass vacuously
            stats["harness_errors"] += 1
            failures.append({"step": None, "driver": "tripwire", "harness_error": True,
                             "problems": [f"harness error: the tripwire could not accept connections: {srv.trip_errors[0]}"]})
        try:
            if not srv.running:
                srv.resume()
            srv.set_rules([])
        except OSError as e:  # the server cannot serve again: no later case can run; stop the run (exit 2)
            stats["harness_errors"] += 1
            stats["abort"] = f"the fixture server cannot restart: {type(e).__name__}: {e}"
            failures.append({"step": None, "driver": "server_start", "harness_error": True,
                             "problems": [f"harness error: {stats['abort']}"]})
        tails = []
        for role in runners:
            sp = stderr_path(role)
            t = sp.read_text(errors="replace")[-2000:] if sp.exists() else ""
            if t:
                tails.append(t if role == "main" else f"[{role}]\n{t}")
        stderr_tail = "\n".join(tails)
        if not keep_tmp:
            restore_writable(tmp)   # a chmod step may have left a directory read-only
            shutil.rmtree(tmp, ignore_errors=True)
    return failures, stderr_tail


def expand_cross(cases, hellos):
    """One case per ordered assignment of distinct runners to the case's roles. hellos: {name: (cmd, features)}."""
    import itertools
    out = []
    for c in cases:
        roles = list(c.get("roles") or {})
        if not roles:
            raise ValueError(f"{c.get('id')}: a cross case needs roles")
        need = set(c.get("requires", []))  # the case's own requires applies to every role
        for names in itertools.permutations(hellos, len(roles)):
            if any((set(c["roles"][r]) | need) - hellos[n][1] for r, n in zip(roles, names)):
                continue
            v = copy.deepcopy(c)
            v["id"] = f"{c['id']}[{'>'.join(names)}]"
            v["_runners"] = {r: hellos[n] for r, n in zip(roles, names)}
            out.append(v)
    return out


# --------------------------------------------------------------------------- self-test of the server

def selftest():
    srv = FixtureServer().start().start_tls()
    proxy = RecordingProxy().start()
    results = []

    def check(name, cond, detail=""):
        results.append((name, bool(cond), detail))

    def get(path, headers=None, timeout=10, via_proxy=False):
        if via_proxy:
            conn = http.client.HTTPConnection(proxy.host, proxy.port, timeout=timeout)
            conn.request("GET", srv.url + path, headers=headers or {})
        else:
            conn = http.client.HTTPConnection(srv.host, srv.port, timeout=timeout)
            conn.request("GET", path, headers=headers or {})
        r = conn.getresponse()
        body = r.read()
        conn.close()
        return r, body

    try:
        fx = (FIXTURES / "good" / "OTC_latest-f1.json").read_bytes()
        r, body = get("/good/OTC_latest-f1.json")
        tag = r.getheader("ETag")
        check("200 with the file and a SHA-256 ETag", r.status == 200 and body == fx and tag == '"' + hashlib.sha256(fx).hexdigest() + '"')
        check("CORS headers on a GET", r.getheader("Access-Control-Allow-Origin") == "*" and r.getheader("Access-Control-Expose-Headers") == "ETag,Content-Length,Content-Encoding" and r.getheader("Vary") == "Origin")
        r, _ = get("/good/OTC_latest-f1.json", {"If-None-Match": tag})
        check("304 for a matching If-None-Match", r.status == 304 and r.getheader("Access-Control-Allow-Origin") == "*")
        r, _ = get("/good/OTC_latest-f1.json", {"If-None-Match": '"0000"'})
        check("200 for a stale If-None-Match", r.status == 200)
        conn = http.client.HTTPConnection(srv.host, srv.port, timeout=10)
        conn.request("OPTIONS", "/good/OTC_latest-f1.json", headers={"Origin": "https://example.org", "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "if-none-match"})
        r = conn.getresponse(); r.read(); conn.close()
        check("preflight 204 with methods GET, HEAD and if-none-match", r.status == 204 and r.getheader("Access-Control-Allow-Methods") == "GET, HEAD" and r.getheader("Access-Control-Allow-Headers") == "if-none-match")
        jl = (FIXTURES / "good" / "OTC_20991231.2.jsonl").read_bytes()
        r, body = get("/good/OTC_20991231.2.jsonl", {"Accept-Encoding": "gzip"})
        check("gzip when accepted; the decoded body is the file", r.getheader("Content-Encoding") == "gzip" and gzip.decompress(body) == jl)
        r, body = get("/good/OTC_20991231.2.json.gz", {"Accept-Encoding": "gzip"})
        check("a .gz file is sent as is", r.getheader("Content-Encoding") is None and body == (FIXTURES / "good" / "OTC_20991231.2.json.gz").read_bytes())
        r, _ = get("/good/OTC_20991230.sha256")
        check("404 for a missing file", r.status == 404)
        import ssl
        tls = http.client.HTTPSConnection(srv.host, int(srv.tls_url.rsplit(":", 1)[1]), timeout=10,
                                          context=ssl.create_default_context(cafile=srv.tls_ca))
        tls.request("GET", "/good/OTC_latest-f1.json")
        r = tls.getresponse(); body = r.read(); tls.close()
        check("https: the same file under the throw-away CA", r.status == 200 and body == fx)
        srv.set_rules([{"match": r"sha256$", "action": "status", "status": 500, "times": 1}])
        r1, _ = get("/good/OTC_20991231.2.sha256")
        r2, _ = get("/good/OTC_20991231.2.sha256")
        check("rule: 500 once, then 200", r1.status == 500 and r2.status == 200)
        srv.set_rules([{"match": r"latest", "action": "status", "status": 429, "headers": {"Retry-After": "2"}, "times": 1}])
        r, _ = get("/good/OTC_latest.json")
        check("rule: 429 with Retry-After", r.status == 429 and r.getheader("Retry-After") == "2")
        srv.set_rules([{"match": r"jsonl$", "action": "short_body", "delta": 100}])
        try:
            get("/good/OTC_20991231.2.jsonl")
            check("rule: short body makes the client fail", False, "no error")
        except http.client.IncompleteRead:
            check("rule: short body makes the client fail", True)
        srv.set_rules([{"match": r"jsonl$", "action": "truncate", "bytes": 1000}])
        r, body = get("/good/OTC_20991231.2.jsonl")
        check("rule: truncate gives a consistent 1000-byte body", r.status == 200 and len(body) == 1000 and body == jl[:1000])
        srv.set_rules([{"match": r"jsonl$", "action": "slow", "delay_s": 3}])
        try:
            get("/good/OTC_20991231.2.jsonl", timeout=1)
            check("rule: slow body hits a 1 s timeout", False, "no timeout")
        except TimeoutError:
            check("rule: slow body hits a 1 s timeout", True)
        except OSError as e:
            check("rule: slow body hits a 1 s timeout", "timed out" in str(e), str(e))
        srv.set_rules([{"match": r"OTC_latest", "action": "json", "file": "good/OTC_index.json", "pointer": "/releases/1"}])
        r, body = get("/good/OTC_latest-f1.json")
        check("rule: json pointer serves the 20991231 index entry", json.loads(body)["datestamp"] == "20991231")
        srv.set_rules([])
        srv.log.clear(); proxy.log.clear()
        r, body = get("/good/OTC_latest.json", via_proxy=True)
        check("proxy relays and records the request", r.status == 200 and len(proxy.log.entries()) == 1 and len([e for e in srv.log.entries() if e["source"] == "server"]) == 1)
        srv.log.clear()
        keep = http.client.HTTPConnection(srv.host, srv.port, timeout=5)
        keep.request("GET", "/good/OTC_latest.json")
        keep.getresponse().read()
        srv.stop()
        try:
            keep.request("GET", "/good/OTC_latest.json")
            keep.getresponse().read()
            kept = "response"
        except (OSError, http.client.HTTPException) as e:
            kept = type(e).__name__
        keep.close()
        check("stopped: a kept-alive connection is closed too", kept != "response", kept)
        try:
            get("/good/OTC_latest.json", timeout=2)
            got = "response"
        except (OSError, http.client.HTTPException) as e:
            got = type(e).__name__
        time.sleep(0.2)
        check("stopped: no HTTP, and the tripwire records the connection", got != "response" and any(e["source"] == "tripwire" for e in srv.log.entries()), got)
        srv.resume()
        r, _ = get("/good/OTC_latest.json")
        check("resumed: serves again on the same port", r.status == 200)
        r = get("/good/OTC_latest.json")[0]
        check("every request is logged with method, path, headers and status", any(e["path"] == "/good/OTC_latest.json" and e["status"] == 200 and e["method"] == "GET" and "host" in e["headers"] for e in srv.log.entries()))
    finally:
        srv.shutdown()
        proxy.shutdown()
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not ok else ""))
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"server self-test: {len(results)} checks, {len(results) - failed} passed, {failed} failed")
    return 0 if failed == 0 else 1


# --------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description="OpenTideConstants SDK conformance driver")
    ap.add_argument("--runner", help="the runner command (split with shlex)")
    ap.add_argument("--cross", action="append", metavar="NAME=COMMAND",
                    help="cross-SDK mode: a named runner (give two or more); runs the cases in conformance/cross/ "
                         "once per ordered pair of distinct runners")
    ap.add_argument("--cases", help="the case directory (default conformance/cases, or conformance/cross with --cross)")
    ap.add_argument("--only", help="run only case ids matching this regular expression")
    ap.add_argument("--profile", choices=sorted(PROFILES),
                    help="the features the runner must claim (default: the hello's runner name if it is a profile, else none)")
    ap.add_argument("--all-steps", action="store_true", help="keep running a case's steps after a failure, to check every step")
    ap.add_argument("--report", help="write a JSON report here")
    ap.add_argument("--keep-tmp", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--check-cases", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--expected-failures", default=str(EXPECTED_FAILURES),
                    help="the expected-failures file (default conformance/expected-failures.json)")
    ap.add_argument("--no-expected-failures", action="store_true",
                    help="ignore the expected-failures file: report every failure as FAIL (to see a lane's RED cases)")
    ap.add_argument("--api", default=str(API), help="the API manifest that --check-cases checks error codes against "
                                                     "(default conformance/api.json)")
    a = ap.parse_args()

    if a.selftest:
        return selftest()
    if a.cross and a.runner:
        ap.error("--runner and --cross do not go together")
    # --check-cases with no --cases lints cases/ and cross/ (each once), whatever --cross says
    cases_dir = Path(a.cases) if a.cases else (CROSS_DIR if a.cross and not a.check_cases else CASES_DIR)
    try:
        raw = load_cases(cases_dir)
        raw_cross = load_cases(CROSS_DIR) if a.check_cases and not a.cases else []
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        print(f"case files in {cases_dir}: cannot load: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    malformed = [p for c in raw + (raw_cross if a.check_cases and not a.cases else []) for p in structure_problems(c)]
    if malformed:
        for p in malformed:
            print(("PROBLEM " if a.check_cases else "case file error: ") + p, file=sys.stdout if a.check_cases else sys.stderr)
        print(f"case files in {cases_dir}: {len(malformed)} malformed case(s) (exit 2)", file=sys.stderr)
        return 2
    try:
        expanded = expand(raw) if not a.cross or a.check_cases else None
        cases = raw if a.cross else expanded
    except (KeyError, TypeError, AttributeError) as e:
        print(f"case files in {cases_dir}: cannot expand a matrix case: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    if a.only:
        try:
            only = re.compile(a.only)
        except re.error as e:
            print(f"--only {a.only!r}: not a regular expression: {e}", file=sys.stderr)
            return 2
        if not a.cross:
            cases = [c for c in cases if only.search(c["id"])]
    if a.check_cases:
        # non-matrix cases are the same before and after expansion: lint them once
        problems = check_cases(raw) + check_cases([c for c in expanded if "@" in c["id"]])
        try:
            by_op = api_errors(a.api)
        except (OSError, ValueError, KeyError, TypeError) as e:
            print(f"--api {a.api}: cannot read the API manifest: {type(e).__name__}: {e}", file=sys.stderr)
            return 2
        problems += api_error_problems(raw + raw_cross, by_op)
        if not a.cases or a.expected_failures != str(EXPECTED_FAILURES):
            import itertools
            cross_ids = [f"{c['id']}[{'>'.join(p)}]" for c in raw_cross
                         for p in itertools.permutations(CROSS_NAMES, len(c.get("roles") or {}))]
            problems += expected_failure_problems(a.expected_failures, [c["id"] for c in expanded], cross_ids)
        n_cross = 0
        if not a.cases:
            problems += check_cases(raw_cross)
            problems += [f"{c['id']}: a cross case needs roles" for c in raw_cross if not c.get("roles")]
            problems += [f"{c['id']}: a case in cases/ must not have roles" for c in raw if c.get("roles")]
            problems += id_problems(expanded, raw_cross)
            n_cross = len(raw_cross)
        for p in problems:
            print("PROBLEM", p)
        print(f"case check: {len(raw)} case definitions, {len(expanded)} expanded cases, "
              f"{n_cross} cross-SDK case definitions, {len(problems)} problems")
        return 0 if not problems else 2
    if a.list:
        for c in cases:
            print(c["id"])
        print(f"{len(cases)} cases")
        return 0
    if not a.runner and not a.cross:
        ap.error("--runner (or --cross, two or more times) is required")
    # only the default file may be absent (no entries); a path given on the command line must exist (a typo would
    # silently run with no entries)
    if not a.no_expected_failures and a.expected_failures != str(EXPECTED_FAILURES) and not Path(a.expected_failures).is_file():
        print(f"--expected-failures {a.expected_failures}: no such file", file=sys.stderr)
        return 2
    named = {}
    for spec in (a.cross or []):
        name, sep, command = spec.partition("=")
        if not sep or not name or not command or name in named:
            ap.error(f"--cross {spec!r}: expected a new NAME=COMMAND")
        named[name] = command
    if a.cross and len(named) < 2:
        ap.error("--cross needs two or more runners")
    hellos = {}
    for name, command in (named.items() if a.cross else [("main", a.runner)]):
        try:
            cmd = shlex.split(command)
        except ValueError as e:
            ap.error(f"runner command {command!r}: {e}")
        hello, err = probe_runner(cmd)
        if err:
            print(f"runner {name if a.cross else ''} failed the handshake: {err}".replace("runner  ", "runner "), file=sys.stderr)
            return 2
        features = set(hello["features"])
        profile = a.profile or (hello.get("runner") if hello.get("runner") in PROFILES else "none")
        lacking = sorted(set(PROFILES[profile]) - features)
        if lacking:
            print(f"runner {hello.get('runner')!r} (profile {profile}) does not claim the required features {lacking}; "
                  f"it claims {sorted(features)}", file=sys.stderr)
            return 2
        hellos[name] = (cmd, features, hello, profile)
    if a.cross:
        try:
            cases = expand_cross(cases, {n: (h[0], h[1]) for n, h in hellos.items()})
            if a.only:
                cases = [c for c in cases if only.search(c["id"])]
        except (ValueError, KeyError, TypeError) as e:
            print(f"case files in {cases_dir}: {e}", file=sys.stderr)
            return 2
        hello = {"runner": "cross", "runners": {n: h[2] for n, h in hellos.items()}}
        features = set()
    else:
        cmd, features, hello, profile = hellos["main"]
    xf_entries = []
    if not a.no_expected_failures and Path(a.expected_failures).exists():
        try:
            xf_entries = load_expected_failures(a.expected_failures)
        except (OSError, ValueError) as e:
            print(f"--expected-failures: {e}", file=sys.stderr)
            return 2
    xf_runner = "cross" if a.cross else hello.get("runner")
    srv = FixtureServer().start()
    try:
        srv.start_tls()
    except (OSError, subprocess.SubprocessError) as e:   # no openssl: the https cases could not run; a broken harness
        srv.shutdown()
        print(f"fixture server: cannot start the https listener (the openssl command makes its certificate): "
              f"{type(e).__name__}: {e}", file=sys.stderr)
        return 2
    try:
        proxy = RecordingProxy().start()
    except BaseException:
        srv.shutdown()
        raise
    proxy.aliases[SERVER_ALIAS] = srv.host
    if a.cross:
        for n, h in hellos.items():
            print(f"runner {n}: {h[2].get('runner')} {h[2].get('version', '')}  features: {sorted(h[1])}  profile: {h[3]}")
    else:
        print(f"runner: {hello.get('runner')} {hello.get('version', '')}  features: {sorted(features)}  profile: {profile}")
    print(f"fixture server {srv.url}  https {srv.tls_url}  proxy {proxy.url}")
    stats = {"steps_compared": 0, "steps_failed": 0, "harness_errors": 0}
    report = []
    counts = {"PASS": 0, "FAIL": 0, "SKIP": 0, "XFAIL": 0, "XPASS": 0}
    t0 = time.monotonic()
    try:
        for c in cases:
            missing = [] if a.cross else [f for f in c.get("requires", []) if f not in features]
            if missing:
                counts["SKIP"] += 1
                report.append({"id": c["id"], "status": "SKIP", "missing_features": missing})
                if a.verbose:
                    print(f"SKIP  {c['id']}  (runner lacks {missing})")
                continue
            runners = c.pop("_runners") if a.cross else {"main": (cmd, features)}
            failures, stderr_tail = run_case(c, runners, srv, proxy, a.keep_tmp, a.all_steps, stats)
            status = "FAIL" if failures else "PASS"
            xf = expected_failure(xf_entries, c["id"], xf_runner)
            if xf and not failures:
                status = "XPASS"
            elif xf and expected_failure_covers(xf, failures):   # not a harness error, a crash, or another step
                status = "XFAIL"
            counts[status] += 1
            entry = {"id": c["id"], "status": status, "failures": failures, "stderr": stderr_tail if failures else ""}
            if xf:
                entry["expected_failure"] = {"package": xf.get("package"), "reason": xf.get("reason")}
            report.append(entry)
            line = f"{status}  {c['id']}"
            if status == "XPASS":
                line += f"  (listed in the expected failures for {xf.get('package')}: it passes now; remove the entry)"
            elif failures:
                first = failures[0]
                where = f"step {first['step']} {first.get('op') or first.get('driver') or ''}".strip()
                if first.get("as"):
                    where += f" as {first['as']}"
                line += f"  [{where}] {first['problems'][0]}"
                if len(failures) > 1:
                    line += f"  (+{len(failures) - 1} more failed step(s))"
            print(line[:400], flush=True)
            if stats.get("abort"):
                print(f"run stopped: {stats['abort']}", flush=True)
                break
    finally:
        srv.shutdown()
        proxy.shutdown()
    ran = counts["PASS"] + counts["FAIL"] + counts["XFAIL"] + counts["XPASS"]
    xf_text = f", {counts['XFAIL']} expected failures, {counts['XPASS']} unexpected passes" if xf_entries else ""
    print(f"\n{len(cases)} cases: {counts['PASS']} passed, {counts['FAIL']} failed, {counts['SKIP']} skipped{xf_text} "
          f"({ran} ran; {stats['steps_compared']} runner steps compared, {stats['steps_failed']} failed) in {time.monotonic() - t0:.1f} s")
    if a.report:
        Path(a.report).write_text(json.dumps({"runner": hello, "counts": counts, "steps": stats, "cases": report}, indent=1) + "\n")
    if stats["harness_errors"]:
        print(f"{stats['harness_errors']} harness error(s): a case file or the driver is wrong (exit 2)")
        return 2
    if ran == 0:
        print("no case ran: check --only and the features the runner reports (exit 1)")
        return 1
    return 0 if counts["FAIL"] == 0 and counts["XPASS"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
