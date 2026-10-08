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
- base_url defaults to None, which means OPENTIDECONSTANTS_BASE_URL or DEFAULT_BASE_URL (spec §4.2).
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--installed", action="store_true")
    a = ap.parse_args()
    if not a.installed:
        sys.path.insert(0, str(HERE.parents[2] / "python" / "src"))
    import opentideconstants as otc

    api = json.loads(API.read_text(encoding="utf-8"))
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
    names_by_code = {e["code"]: e["class"] for e in api["errors"] if e["class"]}
    for n in dir(otc):
        c = getattr(otc, n)
        if inspect.isclass(c) and base is not None and issubclass(c, base) and c is not base:
            if n not in names_by_code.values() or c.code not in names_by_code:
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
        if str(next(iter(cls))) != next(iter(cls)).value:
            problems.append(f"enum {cname}: __str__ must return the value")

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

    # reserved phase 2 names must not exist yet
    for op in api["reserved_phase2"]["operations"]:
        for cname in ("OpenTideConstants", "Release"):
            if hasattr(getattr(otc, cname), op["name"]) and op["object"] == "Client":
                problems.append(f"{cname}.{op['name']}: reserved for phase 2")
    if hasattr(otc, "Astro") or hasattr(otc, "predict"):
        problems.append("Astro / predict are reserved for phase 2")

    # __all__
    got_all = set(otc.__all__)
    if got_all != expected_all:
        problems.append(f"__all__: missing {sorted(expected_all - got_all)}, extra {sorted(got_all - expected_all)}")

    for p in problems:
        print("PROBLEM", p)
    print(f"API manifest check (suite {api['suite_version']}): {len(expected_all)} public names, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
