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

No phase 2 name may exist yet: no reserved operation on the client, the Release or any public class, no
Astro, and no reserved error class or code. After the check the script runs its own mutation self-test
(each mutation of the package must be caught); --no-self-test skips it.
"""
from __future__ import annotations

import argparse
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


def check(otc, api):
    """The problems of the package otc against the manifest, and the number of public names."""
    problems = []
    expected_all = {"__version__"}

    # errors
    base_name = api["error_base_class"]["python"]
    base = getattr(otc, base_name, None)
    expected_all.add(base_name)
    if base is None:
        problems.append(f"missing base error class {base_name}")
    for e in api["errors"]:
        if e["class"] is None or "python" not in e["languages"]:
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
    names_by_code = {e["code"]: e["class"] for e in api["errors"] if e["class"] and "python" in e["languages"]}
    for n in dir(otc):
        c = getattr(otc, n)
        if inspect.isclass(c) and base is not None and issubclass(c, base) and c is not base:
            if names_by_code.get(getattr(c, "code", None)) != n:
                problems.append(f"extra error class {n}")

    # enums
    for ename, values in api["enums"].items():
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
    forwarded = [m for m in api["objects"]["Release"]["members"] if m.get("forwarded_to_client")]
    for oname, obj in api["objects"].items():
        cname = CLASS_NAME.get(oname, oname)
        expected_all.add(cname)
        cls = getattr(otc, cname, None)
        if cls is None:
            problems.append(f"missing class {cname}")
            continue
        members = list(obj["members"])
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

    # reserved phase 2 names must not exist yet: not on the client, the Release or any public class (an
    # operation of the Client is forwarded from the Release), not as a module attribute, and no class of
    # another reserved object (Astro)
    public_classes = [getattr(otc, n) for n in dir(otc) if not n.startswith("_") and inspect.isclass(getattr(otc, n))]
    for op in api["reserved_phase2"]["operations"]:
        if op["object"] != "Client" and hasattr(otc, op["object"]):
            problems.append(f"{op['object']}: reserved for phase 2")
        if hasattr(otc, op["name"]):
            problems.append(f"{op['name']}: reserved for phase 2")
        for cls in public_classes:
            if op["name"] in public_names(cls):
                problems.append(f"{cls.__name__}.{op['name']}: reserved for phase 2")
    if hasattr(otc, "predict"):
        problems.append("predict is reserved for phase 2")
    for e in api["reserved_phase2"].get("errors", []):
        if hasattr(otc, e["class"]):
            problems.append(f"{e['class']}: reserved for phase 2")
        for cls in public_classes:
            if base is not None and issubclass(cls, base) and getattr(cls, "code", None) == e["code"]:
                problems.append(f"{cls.__name__}: has the phase 2 code {e['code']!r}")

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


def _heights(self, station, from_, to, step_s, datum):
    return ()


MUTATIONS = [
    # (name, apply(otc) -> undo, a substring of the problem it must cause)
    ("reserved-op-on-release", lambda o: _set(o.Release, "heights", _heights), "Release.heights: reserved"),
    ("reserved-op-on-station", lambda o: _set(o.Station, "extremes", _heights), "Station.extremes: reserved"),
    ("reserved-module-function", lambda o: _set(o, "node_factor", lambda *a: None), "node_factor: reserved"),
    ("reserved-astro-object", lambda o: _set(o, "Astro", type("Astro", (), {})), "Astro: reserved"),
    ("reserved-error-class", lambda o: _set(o, "UnsupportedConventionError",
                                            _error_class(o, "UnsupportedConventionError", "unsupported_convention")),
     "UnsupportedConventionError: reserved"),
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


def self_test(otc, api):
    base, _ = check(otc, api)
    failures = []
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
        print(f"self-test: {len(MUTATIONS) - len(failures)} of {len(MUTATIONS)} mutations caught")
        rc = rc or (1 if failures else 0)
    return rc


if __name__ == "__main__":
    sys.exit(main())
