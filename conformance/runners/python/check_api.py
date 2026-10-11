# /// script
# requires-python = ">=3.10"
# ///
"""The Python API manifest check (SDK spec §7.1): compare conformance/api.json with the public surface
of the opentideconstants package. A missing name or an extra name fails (exit 1).

    python3 conformance/runners/python/check_api.py [--installed]

Python rules (api.json "naming"): snake_case; a predicate is a property; optional and non-positional
arguments are keyword-only; the Client is the class OpenTideConstants and its "open" operation is the
constructor. Python-specific mappings used here:
- a field named after a Python keyword gets a trailing underscore (UpdateResult.from -> from_);
- the enum "qc_flag" is the class QcFlagName (QcFlag is the object); other enums are the CamelCase name;
- every enum has one more member, OTHER = "other", for a value a newer format minor adds (spec §7.3);
- base_url defaults to None, which means OPENTIDECONSTANTS_BASE_URL or DEFAULT_BASE_URL (spec §4.2);
- an error class's fields are the keyword-only arguments of its constructor.

A name in api.json pending_port.python (prediction spec 5, not ported to Python yet) is not required and
must not exist: no pending object's class, no pending member on its object (nor on the client, for a member
forwarded to it), no pending enum's class, and no pending error class or code. Every pending name must be a
manifest name that applies to Python. After the check the script runs its own mutation self-test (each
mutation of the package or of the manifest must be caught); --no-self-test skips it.
"""
from __future__ import annotations

import argparse
import copy
import enum
import inspect
import json
import keyword
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
API = HERE.parents[1] / "api.json"
CLASS_NAME = {"Client": "OpenTideConstants"}
ENUM_CLASS = {"qc_flag": "QcFlagName"}
DEFAULT_EXCEPTIONS = {("Client", "open", "base_url")}


def camel(name):
    return "".join(p.capitalize() for p in name.split("_"))


def pyname(name):
    return name + "_" if keyword.iskeyword(name) else name


def norm_default(v):
    return tuple(v) if isinstance(v, list) else v


def public_names(cls):
    names = set()
    for klass in cls.__mro__:
        if klass in (object, Exception, BaseException):
            continue
        for n in vars(klass):
            if not n.startswith("_"):
                names.add(n)
    return names


def init_fields(cls):
    """The keyword-only argument names of an error class's constructor (its detail fields)."""
    try:
        params = inspect.signature(cls.__init__).parameters.values()
    except (TypeError, ValueError):
        return None
    return {p.name for p in params if p.kind == inspect.Parameter.KEYWORD_ONLY}


def pending_names(api, problems):
    """The names api.json pending_port.python lists, as (objects, members, enums, errors): members are
    (object, name) pairs. A pending name that is not a manifest name for Python is a problem."""
    pend = api.get("pending_port", {}).get("python")
    if not isinstance(pend, dict):
        problems.append("api.json has no pending_port.python")
        return set(), set(), set(), set()
    unknown = sorted(set(pend) - {"objects", "members", "enums", "errors"})
    if unknown:
        problems.append(f"pending_port.python: unknown key(s) {unknown}")
    objects = set(pend.get("objects", []))
    members = set()
    for o in sorted(objects - set(api["objects"])):
        problems.append(f"pending_port.python: object {o} is not a manifest object")
    for qn in pend.get("members", []):
        oname, _, name = qn.partition(".")
        ms = [m for m in api["objects"].get(oname, {}).get("members", []) if m.get("name") == name]
        if not ms or "python" not in ms[0].get("languages", ["python"]):
            problems.append(f"pending_port.python: member {qn} is not a manifest member for Python")
        members.add((oname, name))
    enums = set(pend.get("enums", []))
    for e in sorted(enums - set(api["enums"])):
        problems.append(f"pending_port.python: enum {e} is not a manifest enum")
    errors = set(pend.get("errors", []))
    py_codes = {e["code"] for e in api["errors"] if e["class"] and "python" in e["languages"]}
    for c in sorted(errors - py_codes):
        problems.append(f"pending_port.python: error {c} is not a manifest error with a Python class")
    return objects, members, enums, errors


def check(otc, api):
    """The problems of the package otc against the manifest, and the number of public names."""
    problems = []
    expected_all = {"__version__"}
    pend_objects, pend_members, pend_enums, pend_errors = pending_names(api, problems)

    # errors
    base_name = api["error_base_class"]["python"]
    base = getattr(otc, base_name, None)
    expected_all.add(base_name)
    if base is None:
        problems.append(f"missing base error class {base_name}")
    for e in api["errors"]:
        if e["class"] is None or "python" not in e["languages"] or e["code"] in pend_errors:
            continue
        expected_all.add(e["class"])
        cls = getattr(otc, e["class"], None)
        if cls is None:
            problems.append(f"missing error class {e['class']}")
            continue
        if base is not None and cls.__bases__ != (base,):
            problems.append(f"{e['class']} must subclass {base_name} directly and nothing else")
        if getattr(cls, "code", None) != e["code"]:
            problems.append(f"{e['class']}.code is {getattr(cls, 'code', None)!r}, not {e['code']!r}")
        fields = init_fields(cls)
        want_fields = set(e.get("fields", []))
        if fields is None:
            problems.append(f"{e['class']}: cannot read its constructor's signature")
        elif fields != want_fields:
            problems.append(f"{e['class']} fields: missing {sorted(want_fields - fields)}, extra {sorted(fields - want_fields)}")
    names_by_code = {e["code"]: e["class"] for e in api["errors"]
                     if e["class"] and "python" in e["languages"] and e["code"] not in pend_errors}
    for n in dir(otc):
        c = getattr(otc, n)
        if inspect.isclass(c) and base is not None and issubclass(c, base) and c is not base:
            if names_by_code.get(getattr(c, "code", None)) != n:
                problems.append(f"extra error class {n}")

    # enums
    for ename, values in api["enums"].items():
        if ename in pend_enums:
            continue
        cname = ENUM_CLASS.get(ename, camel(ename))
        expected_all.add(cname)
        cls = getattr(otc, cname, None)
        if cls is None or not (inspect.isclass(cls) and issubclass(cls, enum.Enum) and issubclass(cls, str)):
            problems.append(f"missing (str, Enum) class {cname} for enum {ename}")
            continue
        got = {m.value for m in cls}
        want = set(values) | {"other"}
        if got != want:
            problems.append(f"enum {cname}: missing {sorted(want - got)}, extra {sorted(got - want)}")
        bad_str = [m.name for m in cls if str(m) != m.value]
        if bad_str:
            problems.append(f"enum {cname}: __str__ must return the value (not for {bad_str})")

    # constants
    for cname, spec in api["constants"].items():
        if cname == "c_only":
            continue
        expected_all.add(cname)
        if not hasattr(otc, cname):
            problems.append(f"missing constant {cname}")
        elif norm_default(spec["value"]) != norm_default(getattr(otc, cname)):
            problems.append(f"constant {cname} is {getattr(otc, cname)!r}, not {spec['value']!r}")

    # objects
    filters = api["filters"]
    forwarded = [m for m in api["objects"]["Release"]["members"]
                 if m.get("forwarded_to_client") and ("Release", m["name"]) not in pend_members]
    for oname, obj in api["objects"].items():
        if oname in pend_objects:
            continue
        cname = CLASS_NAME.get(oname, oname)
        expected_all.add(cname)
        cls = getattr(otc, cname, None)
        if cls is None:
            problems.append(f"missing class {cname}")
            continue
        members = [m for m in obj["members"] if (oname, m["name"]) not in pend_members]
        if oname == "Client":
            members += forwarded
        want = set()
        for m in members:
            if "languages" in m and "python" not in m["languages"]:
                continue
            if oname == "Client" and m["name"] == "open":
                fn = cls.__init__
            else:
                n = pyname(m["name"])
                want.add(n)
                if not hasattr(cls, n) and n not in getattr(cls, "__dataclass_fields__", {}):
                    problems.append(f"{cname}: missing {m['kind']} {n}")
                    continue
                fn = getattr(cls, n, None)
            kind = m.get("kind")
            if kind == "predicate" and not isinstance(inspect.getattr_static(cls, pyname(m["name"])), property):
                problems.append(f"{cname}.{m['name']}: a predicate must be a property")
            if kind == "attribute" and callable(getattr(cls, pyname(m["name"]), None)) and \
                    not isinstance(inspect.getattr_static(cls, pyname(m["name"])), property):
                problems.append(f"{cname}.{m['name']}: an attribute must be a property or field, not a method")
            if kind != "method":
                continue
            if not callable(fn):
                problems.append(f"{cname}.{m['name']}: must be a method")
                continue
            params = [p for p in inspect.signature(fn).parameters.values() if p.name != "self"]
            args = list(m.get("args") or [])
            if m.get("filters"):
                args += filters
            got_names = [p.name for p in params]
            want_names = [x["name"] for x in args]
            if sorted(got_names) != sorted(want_names):
                problems.append(f"{cname}.{m['name']}: arguments {got_names}, manifest {want_names}")
                continue
            pmap = {p.name: p for p in params}
            for x in args:
                p = pmap[x["name"]]
                want_kind = inspect.Parameter.POSITIONAL_OR_KEYWORD if x.get("positional") else inspect.Parameter.KEYWORD_ONLY
                if p.kind != want_kind:
                    problems.append(f"{cname}.{m['name']}({x['name']}): must be {want_kind.description}")
                required = x.get("required", False)
                if required and p.default is not inspect.Parameter.empty:
                    problems.append(f"{cname}.{m['name']}({x['name']}): must be required")
                if not required:
                    if p.default is inspect.Parameter.empty:
                        problems.append(f"{cname}.{m['name']}({x['name']}): must be optional")
                    elif (oname, m["name"], x["name"]) not in DEFAULT_EXCEPTIONS and \
                            norm_default(p.default) != norm_default(x.get("default")):
                        problems.append(f"{cname}.{m['name']}({x['name']}): default {p.default!r}, manifest {x.get('default')!r}")
        extra = public_names(cls) - want
        if oname == "Client":
            extra -= {"open"}
        if extra:
            problems.append(f"{cname}: extra public names {sorted(extra)}")

    # pending names (pending_port.python) must not exist yet: a pending object's class, a pending member on its
    # object (and on the client, for a member forwarded to it), a pending enum's class, a pending error class or
    # an error class with a pending code
    public_classes = [getattr(otc, n) for n in dir(otc) if not n.startswith("_") and inspect.isclass(getattr(otc, n))]
    for oname in sorted(pend_objects):
        if hasattr(otc, CLASS_NAME.get(oname, oname)):
            problems.append(f"{CLASS_NAME.get(oname, oname)}: pending for Python (pending_port), must not exist yet")
    release_forwarded = {m["name"] for m in api["objects"]["Release"]["members"] if m.get("forwarded_to_client")}
    for oname, name in sorted(pend_members):
        owners = [oname] + (["Client"] if oname == "Release" and name in release_forwarded else [])
        for owner in owners:
            cls = getattr(otc, CLASS_NAME.get(owner, owner), None)
            if cls is not None and pyname(name) in public_names(cls):
                problems.append(f"{CLASS_NAME.get(owner, owner)}.{pyname(name)}: pending for Python (pending_port), "
                                f"must not exist yet")
    for ename in sorted(pend_enums):
        cname = ENUM_CLASS.get(ename, camel(ename))
        if hasattr(otc, cname):
            problems.append(f"{cname}: pending for Python (pending_port), must not exist yet")
    for e in api["errors"]:
        if e["code"] not in pend_errors or not e["class"]:
            continue
        if hasattr(otc, e["class"]):
            problems.append(f"{e['class']}: pending for Python (pending_port), must not exist yet")
        for cls in public_classes:
            if base is not None and issubclass(cls, base) and getattr(cls, "code", None) == e["code"]:
                problems.append(f"{cls.__name__}: has the pending code {e['code']!r}")

    # __all__
    got_all = set(otc.__all__)
    if got_all != expected_all:
        problems.append(f"__all__: missing {sorted(expected_all - got_all)}, extra {sorted(got_all - expected_all)}")

    return problems, len(expected_all)


# ---------------------------------------------------------------- self-test

def _set(obj, name, value):
    """Set obj.name for the duration of a mutation; the undo puts back the old value or deletes it."""
    had = name in vars(obj)
    old = vars(obj).get(name)
    setattr(obj, name, value)

    def undo():
        if had:
            setattr(obj, name, old)
        else:
            delattr(obj, name)
    return undo


def _del(obj, name):
    old = vars(obj)[name]
    delattr(obj, name)
    return lambda: setattr(obj, name, old)


def _error_class(otc, name, code, **kwonly):
    """An error class like the SDK's, with the given constructor keywords."""
    params = ", ".join(f"{k}=None" for k in kwonly)
    ns = {}
    exec(f"def __init__(self, message='', *, {params}):\n    pass" if params else
         "def __init__(self, message=''):\n    pass", ns)
    return type(name, (otc.OpenTideConstantsError,), {"code": code, "__init__": ns["__init__"], "__module__": otc.__name__})


def _prune_keep_4(self, *, keep=4):
    return ()


def _stations_no_source_type(self, *, country=None, type=None, kind=None, source=None):  # noqa: A002
    return ()


def _heights(self, station, *, start, stop, step_s=600, datum=None, set_id=None):
    return ()


def _pending(lang_fn):
    """A manifest mutation of pending_port.python (on a copy)."""
    def f(api):
        api = copy.deepcopy(api)
        lang_fn(api["pending_port"]["python"])
        return api
    return f


MUTATIONS = [
    # (name, apply(otc) -> undo, a substring of the problem it must cause)
    ("pending-op-on-release", lambda o: _set(o.Release, "heights", _heights), "Release.heights: pending"),
    ("pending-op-on-client", lambda o: _set(o.OpenTideConstants, "extremes", _heights),
     "OpenTideConstants.extremes: pending"),
    ("pending-object", lambda o: _set(o, "AstroTable", type("AstroTable", (), {})), "AstroTable: pending"),
    ("pending-enum", lambda o: _set(o, "ExtremeType", type("ExtremeType", (), {})), "ExtremeType: pending"),
    ("pending-error-class", lambda o: _set(o, "UnsupportedConventionError",
                                           _error_class(o, "UnsupportedConventionError", "unsupported_convention")),
     "UnsupportedConventionError: pending"),
    ("pending-error-code", lambda o: _set(o, "NoConstants", _error_class(o, "NoConstants", "no_constants")),
     "NoConstants: has the pending code 'no_constants'"),
    ("wrong-default", lambda o: _set(o.OpenTideConstants, "prune", _prune_keep_4), "prune(keep): default 4"),
    ("unchecked-filter", lambda o: _set(o.Release, "stations", _stations_no_source_type), "Release.stations: arguments"),
    ("no-SUPPORTED_FORMAT_VERSION", lambda o: _del(o, "SUPPORTED_FORMAT_VERSION"), "missing constant SUPPORTED_FORMAT_VERSION"),
    ("error-extra-field", lambda o: _set(o, "CacheError", _error_class(o, "CacheError", "cache", removed=1, path=1)),
     "CacheError fields: missing [], extra ['path']"),
    ("error-missing-field", lambda o: _set(o, "CacheError", _error_class(o, "CacheError", "cache")),
     "CacheError fields: missing ['removed']"),
    ("error-wrong-code", lambda o: _set(o.CacheError, "code", "cache_error"), "CacheError.code is 'cache_error'"),
    ("extra-error-class", lambda o: _set(o, "QuotaError", _error_class(o, "QuotaError", "quota")), "extra error class QuotaError"),
    ("enum-str", lambda o: _set(o.AliasSystem, "__str__", lambda self: self.name if self.value == "linz" else self.value),
     "enum AliasSystem: __str__ must return the value (not for ['LINZ'])"),
    ("extra-public-name", lambda o: _set(o.Station, "elevation", property(lambda self: None)), "Station: extra public names ['elevation']"),
]


API_MUTATIONS = [
    # (name, manifest mutation, a substring of the problem it must cause)
    ("pending-member-dropped", _pending(lambda p: p["members"].remove("Release.heights")), "Release: missing method heights"),
    ("pending-forwarded-dropped", _pending(lambda p: p["members"].remove("Release.extremes")),
     "OpenTideConstants: missing method extremes"),
    ("pending-object-dropped", _pending(lambda p: p["objects"].remove("AstroTable")), "missing class AstroTable"),
    ("pending-enum-dropped", _pending(lambda p: p["enums"].remove("extreme_type")), "missing (str, Enum) class ExtremeType"),
    ("pending-error-dropped", _pending(lambda p: p["errors"].remove("no_constants")), "missing error class NoConstantsError"),
    ("pending-unknown-member", _pending(lambda p: p["members"].append("Release.frobnicate")),
     "pending_port.python: member Release.frobnicate is not a manifest member"),
    ("pending-unknown-object", _pending(lambda p: p["objects"].append("Astro")), "pending_port.python: object Astro"),
    ("pending-unknown-error", _pending(lambda p: p["errors"].append("not_found")), "pending_port.python: error not_found"),
    ("pending-unknown-key", _pending(lambda p: p.__setitem__("functions", [])), "pending_port.python: unknown key(s)"),
]


def self_test(otc, api):
    base, _ = check(otc, api)
    failures = []
    for name, mutate, expect in API_MUTATIONS:
        try:
            got, _ = check(otc, mutate(api))
        except Exception as e:  # a crash is a failure of the checker
            failures.append(f"{name}: the check crashed: {type(e).__name__}: {e}")
            continue
        new = [p for p in got if p not in base]
        if not any(expect in p for p in new):
            failures.append(f"{name}: not caught (wanted a problem with {expect!r}; new problems {new})")
    for name, apply, expect in MUTATIONS:
        undo = apply(otc)
        try:
            got, _ = check(otc, api)
        except Exception as e:  # a crash is a failure of the checker
            failures.append(f"{name}: the check crashed: {type(e).__name__}: {e}")
            continue
        finally:
            undo()
        new = [p for p in got if p not in base]
        if not any(expect in p for p in new):
            failures.append(f"{name}: not caught (wanted a problem with {expect!r}; new problems {new})")
    after, _ = check(otc, api)
    if after != base:
        failures.append(f"a mutation was not undone: {sorted(set(after) ^ set(base))}")
    return failures


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--installed", action="store_true")
    ap.add_argument("--no-self-test", action="store_true")
    a = ap.parse_args()
    if not a.installed:
        sys.path.insert(0, str(HERE.parents[2] / "python" / "src"))
    import opentideconstants as otc

    api = json.loads(API.read_text(encoding="utf-8"))
    problems, n_names = check(otc, api)
    for p in problems:
        print("PROBLEM", p)
    print(f"API manifest check (suite {api['suite_version']}): {n_names} public names, {len(problems)} problems")
    rc = 1 if problems else 0
    if not a.no_self_test:
        failures = self_test(otc, api)
        for f in failures:
            print("SELF-TEST", f)
        n = len(MUTATIONS) + len(API_MUTATIONS)
        print(f"self-test: {n - len(failures)} of {n} mutations caught")
        rc = rc or (1 if failures else 0)
    return rc


if __name__ == "__main__":
    sys.exit(main())
