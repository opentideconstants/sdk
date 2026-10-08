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
import gzip
import hashlib
import http.client
import json
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
from server import FixtureServer, RecordingProxy  # noqa: E402

FIXTURES = HERE / "fixtures"
CASES_DIR = HERE / "cases"
DEFAULT_TOL = 1e-9
FEATURES = ["fs", "fetch", "json", "eager", "stream"]
RESERVED_EXPECT = {"error", "error_fields", "tolerance"}

# Open variants for matrix cases: (suffix, file extension or None for the server, mode, features needed)
VARIANTS = [
    ("json", ".json", "eager", ["fs", "json", "eager"]),
    ("json.gz", ".json.gz", "eager", ["fs", "json", "eager"]),
    ("jsonl", ".jsonl", "eager", ["fs", "eager"]),
    ("jsonl-stream", ".jsonl", "stream", ["fs", "stream"]),
    ("server", None, "eager", ["fetch", "eager"]),
]

FILTERS = ["country", "type", "kind", "source", "source_type"]
OPEN_ARGS = ["release", "file", "cache_dir", "offline", "mode", "base_url", "timeout", "proxy", "ca_file", "user_agent",
             "on_network_error", "auto_update", "update_interval", "verify_on_open"]
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
    "nearest": ["lat", "lon", "max_km"] + FILTERS, "reference_station": ["station_id"], "subordinates_of": ["station_id"],
    "station_validation": ["station_id"], "subordinate_offsets": ["station_id"], "recommended_set": ["station_id"],
    "constant_sets": ["station_id", "include_excluded"], "constant_set": ["station_id", "set_id"],
    "constituents": ["station_id", "set_id"], "constituent": ["station_id", "set_id", "name"],
    "provenance": ["station_id", "set_id"], "set_validation": ["station_id", "set_id"],
    "raw": ["object", "station_id", "set_id", "name", "convention_id", "licence_id"],
}
DRIVER_ACTIONS = {"server_rules", "server_stop", "server_start", "clear_log", "assert_requests", "copy", "write", "delete",
                  "corrupt", "assert_files", "assert_sha256", "assert_json", "sleep", "restart_runner", "mkdir"}
PLACEHOLDERS = {"fixtures", "server", "proxy", "tmp", "cache"}


class CaseError(Exception):
    pass


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
        if op == "$regex":
            return [] if isinstance(act, str) and re.search(arg, act) else [f"{path}: {act!r} does not match /{arg}/"]
        if op == "$type":
            return [] if _type_name(act) == arg else [f"{path}: expected a {arg}, got {_type_name(act)}"]
        if op == "$len_min":
            return [] if isinstance(act, (list, str, dict)) and len(act) >= arg else [f"{path}: expected length >= {arg}"]
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


def evaluate(expect, reply):
    """Compare a runner reply with a step expectation; return mismatch messages."""
    tol = expect.get("tolerance", DEFAULT_TOL)
    bad = reply_problems(reply)
    if bad:
        return bad
    if "error" in expect:
        if reply["ok"]:
            return [f"expected error {expect['error']!r}, got a result {json.dumps(reply.get('result'))[:200]}"]
        e = reply["error"]
        out = []
        if e.get("code") != expect["error"]:
            out.append(f"expected error {expect['error']!r}, got error {e.get('code')!r} ({str(e.get('message'))[:200]})")
        fields = e.get("fields") or {}
        for k, v in (expect.get("error_fields") or {}).items():
            out += match(v, fields.get(k, _MISSING), tol, f"error.fields.{k}")
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
            v["steps"] = [{"op": "open", "args": args, "expect": exp}] + v["steps"]
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
        for i, st in enumerate(c.get("steps", [])):
            where = f"{cid} step {i}"
            for s in re.findall(r"\$\{([a-z_]+)\}", json.dumps(st)):
                if s not in PLACEHOLDERS:
                    problems.append(f"{where}: unknown placeholder ${{{s}}}")
            for s in re.findall(r"\$\{fixtures\}/([^\"]+)", json.dumps(st)):
                if not (FIXTURES / s).exists():
                    problems.append(f"{where}: fixture file {s} does not exist")
            if "driver" in st:
                if st["driver"] not in DRIVER_ACTIONS:
                    problems.append(f"{where}: unknown driver action {st['driver']!r}")
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
                if "error" not in exp and not evaluate(exp, {"ok": True, "result": {}}):
                    problems.append(f"{where}: an empty result satisfies this expectation")
            if st.get("expect") is not None:
                compared += 1
            for f in (st.get("expect_if_missing") or {}):
                if f not in FEATURES:
                    problems.append(f"{where}: unknown feature {f!r}")
        if compared == 0 and not c.get("matrix"):
            problems.append(f"{cid}: no runner step with an expectation")
        for f in c.get("requires", []):
            if f not in FEATURES:
                problems.append(f"{cid}: unknown feature {f!r}")
    return problems


# --------------------------------------------------------------------------- runner process

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
            raise EOFError(f"runner exited (status {self.proc.poll()})")
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            raise RunnerError(f"runner printed a line that is not JSON: {line[:200]!r}")

    def send(self, msg):
        self.proc.stdin.write((json.dumps(msg) + "\n").encode())
        self.proc.stdin.flush()

    def close(self):
        try:
            self.proc.stdin.close()
        except OSError:
            pass
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        self.stderr_f.close()


def parse_hello(line):
    """Validate the runner's first line: {"hello": {"runner": str, "features": [str, ...], ...}}."""
    if not isinstance(line, dict) or not isinstance(line.get("hello"), dict):
        raise RunnerError(f"first line is not a hello object: {json.dumps(line)[:200]}")
    hello = line["hello"]
    feats = hello.get("features")
    if not isinstance(feats, list) or not all(isinstance(f, str) for f in feats):
        raise RunnerError(f"hello.features is not a list of strings: {json.dumps(hello)[:200]}")
    return hello


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
    if hdr:
        def ok(e):
            return all(re.search(rx, e["headers"].get(name.lower(), "")) for name, rx in hdr.items())
        if a.get("all"):
            bad = [e for e in entries if not ok(e)]
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


def run_action(st, ctx, srv, proxy):
    """Run a driver action. Returns (problems, restart_env or None)."""
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
            out += match(v, doc.get(k, _MISSING) if isinstance(doc, dict) else _MISSING, DEFAULT_TOL, f"{p.name}.{k}")
        return out, None
    elif kind == "sleep":
        time.sleep(float(a["s"]))
    elif kind == "restart_runner":
        return [], a.get("env", {})
    return [], None


# --------------------------------------------------------------------------- run one case

def run_case(case, runner_cmd, hello_features, srv, proxy, keep_tmp, all_steps, stats):
    tmp = Path(tempfile.mkdtemp(prefix="otc-conf-"))
    ctx = {"fixtures": str(FIXTURES), "server": srv.url, "proxy": proxy.url, "tmp": str(tmp), "cache": str(tmp / "cache")}
    env_extra = {"XDG_CACHE_HOME": str(tmp / "xdg-cache"), "LOCALAPPDATA": str(tmp / "localappdata")}
    env_extra.update(subst(case.get("env", {}), ctx))
    srv.set_rules([])
    srv.log.clear()
    proxy.log.clear()
    stderr_path = tmp / "runner.stderr"
    failures = []
    runner = None
    step_timeout = float(case.get("timeout_s", 60))

    def start():
        r = Runner(runner_cmd, runner_env(env_extra), stderr_path, cwd=str(HERE.parent))
        hello = r.read(60)
        if not isinstance(hello, dict) or "hello" not in hello:
            raise RunnerError(f"first line is not a hello: {json.dumps(hello)[:200]}")
        return r

    cur = {"step": None}
    try:
        runner = start()
        for i, st in enumerate(case["steps"]):
            cur = {"step": i, "driver": st["driver"]} if "driver" in st else {"step": i, "op": st.get("op")}
            if "driver" in st:
                problems, restart_env = run_action(st, ctx, srv, proxy)
                if restart_env is not None:
                    runner.close()
                    env_extra.update(restart_env)
                    runner = start()
                if problems:
                    failures.append({"step": i, "driver": st["driver"], "problems": problems})
                    if not all_steps:
                        break
                continue
            msg = {"case": case["id"], "step": i, "op": st["op"], "args": subst(st.get("args", {}), ctx)}
            if st.get("on"):
                msg["on"] = st["on"]
            expect = st.get("expect")
            last = False
            for feat, alt in (st.get("expect_if_missing") or {}).items():
                if feat not in hello_features:
                    expect, last = alt, True
                    break
            runner.send(msg)
            reply = runner.read(step_timeout)
            if expect is None:
                # an uncompared step still must not fail: a malformed or ok:false reply fails the case
                problems = reply_problems(reply) or (
                    [f"unexpected error {reply['error'].get('code')!r} ({str(reply['error'].get('message'))[:200]})"]
                    if not reply["ok"] else [])
                if problems:
                    stats["steps_failed"] += 1
                    failures.append({"step": i, "op": st["op"], "args": msg["args"], "problems": problems})
                    if not all_steps:
                        break
            else:
                stats["steps_compared"] += 1
                problems = evaluate(subst(expect, ctx), reply)
                if problems:
                    stats["steps_failed"] += 1
                    failures.append({"step": i, "op": st["op"], "args": msg["args"], "problems": problems})
                    if not all_steps:
                        break
            if last:
                break
    except (TimeoutError, EOFError, RunnerError, OSError) as e:
        failures.append({**cur, "problems": [f"{type(e).__name__}: {e}"]})
    except Exception as e:  # a case-file or driver error: fail this case, flag the run, go on
        stats["harness_errors"] += 1
        failures.append({**cur, "harness_error": True, "problems": [f"harness error: {type(e).__name__}: {e}"]})
    finally:
        if runner:
            runner.close()
        if not srv.running:
            srv.resume()
        srv.set_rules([])
        stderr_tail = stderr_path.read_text(errors="replace")[-2000:] if stderr_path.exists() else ""
        if not keep_tmp:
            shutil.rmtree(tmp, ignore_errors=True)
    return failures, stderr_tail


# --------------------------------------------------------------------------- self-test of the server

def selftest():
    srv = FixtureServer().start()
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
        fx = (FIXTURES / "good" / "OTC_latest-f0.json").read_bytes()
        r, body = get("/good/OTC_latest-f0.json")
        tag = r.getheader("ETag")
        check("200 with the file and a SHA-256 ETag", r.status == 200 and body == fx and tag == '"' + hashlib.sha256(fx).hexdigest() + '"')
        check("CORS headers on a GET", r.getheader("Access-Control-Allow-Origin") == "*" and r.getheader("Access-Control-Expose-Headers") == "ETag,Content-Length,Content-Encoding" and r.getheader("Vary") == "Origin")
        r, _ = get("/good/OTC_latest-f0.json", {"If-None-Match": tag})
        check("304 for a matching If-None-Match", r.status == 304 and r.getheader("Access-Control-Allow-Origin") == "*")
        r, _ = get("/good/OTC_latest-f0.json", {"If-None-Match": '"0000"'})
        check("200 for a stale If-None-Match", r.status == 200)
        conn = http.client.HTTPConnection(srv.host, srv.port, timeout=10)
        conn.request("OPTIONS", "/good/OTC_latest-f0.json", headers={"Origin": "https://example.org", "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "if-none-match"})
        r = conn.getresponse(); r.read(); conn.close()
        check("preflight 204 with methods GET, HEAD and if-none-match", r.status == 204 and r.getheader("Access-Control-Allow-Methods") == "GET, HEAD" and r.getheader("Access-Control-Allow-Headers") == "if-none-match")
        jl = (FIXTURES / "good" / "OTC_20991231.2.jsonl").read_bytes()
        r, body = get("/good/OTC_20991231.2.jsonl", {"Accept-Encoding": "gzip"})
        check("gzip when accepted; the decoded body is the file", r.getheader("Content-Encoding") == "gzip" and gzip.decompress(body) == jl)
        r, body = get("/good/OTC_20991231.2.json.gz", {"Accept-Encoding": "gzip"})
        check("a .gz file is sent as is", r.getheader("Content-Encoding") is None and body == (FIXTURES / "good" / "OTC_20991231.2.json.gz").read_bytes())
        r, _ = get("/good/OTC_20991230.sha256")
        check("404 for a missing file", r.status == 404)
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
        r, body = get("/good/OTC_latest-f0.json")
        check("rule: json pointer serves the 20991231 index entry", json.loads(body)["datestamp"] == "20991231")
        srv.set_rules([])
        srv.log.clear(); proxy.log.clear()
        r, body = get("/good/OTC_latest.json", via_proxy=True)
        check("proxy relays and records the request", r.status == 200 and len(proxy.log.entries()) == 1 and len([e for e in srv.log.entries() if e["source"] == "server"]) == 1)
        srv.log.clear()
        srv.stop()
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
    ap.add_argument("--cases", default=str(CASES_DIR))
    ap.add_argument("--only", help="run only case ids matching this regular expression")
    ap.add_argument("--all-steps", action="store_true", help="keep running a case's steps after a failure, to check every step")
    ap.add_argument("--report", help="write a JSON report here")
    ap.add_argument("--keep-tmp", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--check-cases", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        return selftest()
    try:
        raw = load_cases(Path(a.cases))
        cases = expand(raw)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        print(f"case files in {a.cases}: cannot load: {type(e).__name__}: {e}", file=sys.stderr)
        return 2
    if a.only:
        try:
            only = re.compile(a.only)
        except re.error as e:
            print(f"--only {a.only!r}: not a regular expression: {e}", file=sys.stderr)
            return 2
        cases = [c for c in cases if only.search(c["id"])]
    if a.check_cases:
        # non-matrix cases are the same before and after expansion: lint them once
        problems = check_cases(raw) + check_cases([c for c in expand(raw) if "@" in c["id"]])
        for p in problems:
            print("PROBLEM", p)
        print(f"case check: {len(raw)} case definitions, {len(expand(raw))} expanded cases, {len(problems)} problems")
        return 0 if not problems else 2
    if a.list:
        for c in cases:
            print(c["id"])
        print(f"{len(cases)} cases")
        return 0
    if not a.runner:
        ap.error("--runner is required")

    cmd = shlex.split(a.runner)
    srv = FixtureServer().start()
    proxy = RecordingProxy().start()
    probe = Runner(cmd, runner_env({}), os.devnull, cwd=str(HERE.parent))
    try:
        hello = parse_hello(probe.read(60))
    except (TimeoutError, EOFError, RunnerError, OSError) as e:
        print(f"runner failed the handshake: {type(e).__name__}: {e}", file=sys.stderr)
        srv.shutdown()
        proxy.shutdown()
        return 2
    finally:
        probe.close()
    features = set(hello["features"])
    print(f"runner: {hello.get('runner')} {hello.get('version', '')}  features: {sorted(features)}")
    print(f"fixture server {srv.url}  proxy {proxy.url}")
    stats = {"steps_compared": 0, "steps_failed": 0, "harness_errors": 0}
    report = []
    counts = {"PASS": 0, "FAIL": 0, "SKIP": 0}
    t0 = time.monotonic()
    try:
        for c in cases:
            missing = [f for f in c.get("requires", []) if f not in features]
            if missing:
                counts["SKIP"] += 1
                report.append({"id": c["id"], "status": "SKIP", "missing_features": missing})
                if a.verbose:
                    print(f"SKIP  {c['id']}  (runner lacks {missing})")
                continue
            failures, stderr_tail = run_case(c, cmd, features, srv, proxy, a.keep_tmp, a.all_steps, stats)
            status = "FAIL" if failures else "PASS"
            counts[status] += 1
            report.append({"id": c["id"], "status": status, "failures": failures, "stderr": stderr_tail if failures else ""})
            line = f"{status}  {c['id']}"
            if failures:
                first = failures[0]
                where = f"step {first['step']} {first.get('op') or first.get('driver') or ''}".strip()
                line += f"  [{where}] {first['problems'][0]}"
                if len(failures) > 1:
                    line += f"  (+{len(failures) - 1} more failed step(s))"
            print(line[:400], flush=True)
    finally:
        srv.shutdown()
        proxy.shutdown()
    ran = counts["PASS"] + counts["FAIL"]
    print(f"\n{len(cases)} cases: {counts['PASS']} passed, {counts['FAIL']} failed, {counts['SKIP']} skipped "
          f"({ran} ran; {stats['steps_compared']} runner steps compared, {stats['steps_failed']} failed) in {time.monotonic() - t0:.1f} s")
    if a.report:
        Path(a.report).write_text(json.dumps({"runner": hello, "counts": counts, "steps": stats, "cases": report}, indent=1) + "\n")
    if stats["harness_errors"]:
        print(f"{stats['harness_errors']} harness error(s): a case file or the driver is wrong (exit 2)")
        return 2
    if ran == 0:
        print("no case ran: check --only and the features the runner reports (exit 1)")
        return 1
    return 0 if counts["FAIL"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
