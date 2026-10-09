# /// script
# requires-python = ">=3.10"
# ///
"""Check the C public header against the API manifest (conformance/api.json).

    uv run c/tools/check_manifest.py      exit 0 when the header declares every C name the manifest implies,
                                          declares no extra enum value or status, and no phase 2 name

Rules (api.json "naming.c"): an operation's c names its function(s) (a slash separates several, and each
must be declared); c "f(p)" names the parameter p of the function f; c "(C: T.m)" names the member m of
the struct T; another c in parentheses is a note that says how C covers the member. A field or predicate
with no c, of an object with C type T, is the accessor T_<field>, T_<field>_json, or the list pair
T_<singular>_count and T_<singular>_at, or a struct member when c_struct is true. A method or attribute
with no c, or a member of an object with no C type, is an error unless its languages leave out c. Enum
values are OTC_<ENUM>_<VALUE> plus OTC_<ENUM>_OTHER (and an optional OTC_<ENUM>_UNSET), and the C enum
has no other value. Error codes map to the otc_status values in errors[].c, and otc_status has no other
value than OTC_OK and the phase 2 errors. Every filter is a member of otc_filter. Every constant with a c
is declared, and so is every name in constants.c_only. Every client_options.c_only option is a member of
each options struct its note names. No reserved_phase2 operation is declared (the phase 2 errors may be,
CR D24). A C type T may be declared as T or T_t.

A name counts as declared only by a declaration of its kind: a function by an OTC_API prototype or a
function-like #define, a constant by #define or an enum value, a type by a typedef. A token in a comment
or a macro body does not count. C has helpers the manifest does not list (otc_*_init, otc_*_free, otc_status_code), so extra
functions are not an error.

After the check, the script runs its own mutation self-test (each mutation of the manifest or the header
must be caught); --no-self-test skips it.
"""
import copy
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FILTER_STRUCT = "otc_filter"
REQUIRED_KEYS = ("objects", "enums", "errors", "constants", "filters", "client_options", "reserved_phase2")


def strip_comments(text):
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return re.sub(r"//[^\n]*", " ", text)


class Header:
    """The declarations of the header, each by its kind."""

    def __init__(self, text):
        text = strip_comments(text).replace("\\\n", " ")
        lines = text.split("\n")
        self.macros = set()
        self.function_macros = set()
        for line in lines:
            m = re.match(r"\s*#\s*define\s+(\w+)(\()?", line)
            if m:
                self.macros.add(m.group(1))
                if m.group(2):
                    self.function_macros.add(m.group(1))
        code = "\n".join(line for line in lines if not line.lstrip().startswith("#"))
        self.functions = {}
        for m in re.finditer(r"\bOTC_API\b[^;{}()]*?\b(\w+)\s*\(([^;{}]*?)\)\s*;", code, re.S):
            params = []
            for p in m.group(2).split(","):
                words = re.findall(r"\w+", p)
                if words and words != ["void"]:
                    params.append(words[-1])
            self.functions[m.group(1)] = params
        self.enums = []
        for m in re.finditer(r"\btypedef\s+enum\s*\w*\s*\{(.*?)\}\s*(\w+)\s*;", code, re.S):
            self.enums.append((m.group(2), re.findall(r"\b(OTC_\w+)\b\s*(?:=[^,}]*)?(?:,|$)", m.group(1).strip())))
        self.enum_values = {v for _, vals in self.enums for v in vals}
        self.structs = {}
        for m in re.finditer(r"\btypedef\s+struct\s+\w*\s*\{(.*?)\}\s*(\w+)\s*;", code, re.S):
            self.structs[m.group(2)] = set(re.findall(r"\b(\w+)\s*(?:\[[^\]]*\])?\s*;", m.group(1)))
        self.types = set(self.structs) | {name for name, _ in self.enums}
        self.types |= set(re.findall(r"\btypedef\s+(?:struct\s+)?\w+\s*\*?\s*(\w+)\s*;", code))
        self.types |= set(re.findall(r"\btypedef\s+[^;{}]*?\(\s*\*\s*(\w+)\s*\)", code))

    def declared(self, name):
        return name in self.functions or name in self.macros or name in self.enum_values or name in self.types

    def enum_of(self, value):
        for name, vals in self.enums:
            if value in vals:
                return name, vals
        return None, []


def upper(s):
    return re.sub(r"[^A-Za-z0-9]+", "_", s).upper()


def check(api, header):
    """The problems of the header against the manifest (a list of strings)."""
    h = Header(header)
    problems = []
    notes = []

    for key in REQUIRED_KEYS:
        if key not in api:
            problems.append(f"api.json has no {key}")
    if problems:
        return problems, notes

    def need_function(name, where):
        if name not in h.functions and name not in h.function_macros:
            problems.append(f"{name}  ({where}: no OTC_API function)")

    def need_type(ctype, where):
        if not any(t in h.types for t in (ctype, ctype + "_t")):
            problems.append(f"{ctype}  ({where}: no typedef)")

    def need_member(struct, member, where):
        if struct not in h.structs:
            problems.append(f"{struct}  ({where}: no struct)")
        elif member not in h.structs[struct]:
            problems.append(f"{struct}.{member}  ({where})")

    def base(t):
        return t[:-2] if t.endswith("_t") else t

    def for_c(item):
        langs = item.get("languages")
        return langs is None or "c" in langs

    # objects
    for oname, obj in api["objects"].items():
        ctype = obj.get("c")
        if ctype:
            need_type(ctype, f"type of {oname}")
        for m in obj.get("members", []):
            where = f"{oname}.{m.get('name')}"
            if not for_c(m):
                continue
            c = m.get("c")
            if c and "{object}" in c:
                if ctype:
                    need_function(base(ctype) + "_raw_json", where)
                else:
                    problems.append(f"{where}: {c} needs an object with a C type")
                continue
            if c and c.startswith("(C: "):  # a struct member named in the note
                struct, _, member = c[4:-1].rpartition(".")
                need_member(struct or ctype, member, where)
                continue
            pm = re.fullmatch(r"(\w+)\((\w+)\)", c or "")
            if pm:  # a parameter of a function
                fn, param = pm.groups()
                if fn not in h.functions:
                    problems.append(f"{fn}  ({where}: no OTC_API function)")
                elif param not in h.functions[fn]:
                    problems.append(f"{fn}({param})  ({where}: no such parameter)")
                continue
            if c and c.startswith("("):  # a note that says how C covers it
                continue
            if c:
                for fn in c.split("/"):
                    need_function(fn, where)
                continue
            if not ctype:
                problems.append(f"{where}: no C mapping (the object has no C type; give the member a c, "
                                f"or languages without c)")
                continue
            if m.get("kind") not in ("field", "predicate"):
                problems.append(f"{where}: no C mapping (a {m.get('kind')} needs a c, or languages without c)")
                continue
            if obj.get("c_struct"):
                need_member(ctype, m["name"], where)
                continue
            acc = f"{base(ctype)}_{m['name']}"
            singular = acc[:-1] if acc.endswith("s") else acc
            fns = set(h.functions) | h.function_macros
            ok = acc in fns or acc + "_json" in fns or any(s + "_count" in fns and s + "_at" in fns
                                                           for s in (acc, singular))
            if not ok:
                problems.append(f"{acc}  ({where}: no accessor {acc}, {acc}_json or {singular}_count/_at)")

    # filters: members of otc_filter
    for f in api["filters"]:
        need_member(FILTER_STRUCT, f.get("name"), f"filter {f.get('name')}")

    # enums: exactly the manifest's values, plus OTHER and an optional UNSET
    for ename, values in api["enums"].items():
        prefix = "OTC_" + upper(ename) + "_"
        want = {prefix + upper(v) for v in list(values) + ["other"]}
        for v in sorted(want):
            if v not in h.enum_values:
                problems.append(f"{v}  (enum {ename}: no enum value)")
        blocks = {h.enum_of(v)[0] for v in want if h.enum_of(v)[0]}
        for bname in blocks:
            _, vals = next((n, vs) for n, vs in h.enums if n == bname)
            extra = sorted(set(vals) - want - {prefix + "UNSET"})
            if extra:
                problems.append(f"{bname}: extra value(s) {extra}  (enum {ename})")

    # errors: otc_status values
    status_values = set()
    for e in api["errors"]:
        if not for_c(e):
            continue
        c = e.get("c")
        if not c:
            problems.append(f"error {e.get('code')}: its languages include c but it has no c")
            continue
        status_values.add(c)
        if c not in h.enum_values:
            problems.append(f"{c}  (error {e.get('code')}: no otc_status value)")
    reserved_errors = {e.get("c") for e in api["reserved_phase2"].get("errors", []) if e.get("c")}
    status_block = h.enum_of("OTC_OK")[1]
    if not status_block:
        problems.append("OTC_OK  (otc_status: no enum value)")
    extra = sorted(set(status_block) - status_values - reserved_errors - {"OTC_OK"})
    if extra:
        problems.append(f"otc_status: extra value(s) {extra}")

    # constants
    for cname, spec in api["constants"].items():
        if cname == "c_only":
            continue
        c = spec.get("c") if isinstance(spec, dict) else None
        if not c:
            notes.append(cname)
            continue
        if c not in h.macros and c not in h.enum_values:
            problems.append(f"{c}  (constant {cname}: no #define or enum value)")
    if "c_only" not in api["constants"]:
        problems.append("api.json constants has no c_only")
    for cname in api["constants"].get("c_only", []):
        if cname not in h.macros and cname not in h.enum_values:
            problems.append(f"{cname}  (constant, C only: no #define or enum value)")

    # client options, C only: a member of each options struct the note names
    if "c_only" not in api["client_options"]:
        problems.append("api.json client_options has no c_only")
    for opt in api["client_options"].get("c_only", []):
        structs = sorted(set(re.findall(r"\botc_\w+_options\b", opt.get("note", ""))))
        if not structs:
            problems.append(f"client option {opt.get('name')}: its note names no otc_*_options struct")
        for s in structs:
            need_member(s, opt.get("name"), "client option, C only")

    # phase 2 operations must not be declared yet
    for op in api["reserved_phase2"].get("operations", []):
        for fn in (op.get("c") or "").split("/"):
            if fn and h.declared(fn):
                problems.append(f"{fn}  (reserved for phase 2: must not be declared yet)")

    return problems, notes


# ---------------------------------------------------------------- self-test

def _drop_line(pattern):
    def f(text):
        new, n = re.subn(pattern, "", text, count=1, flags=re.M)
        assert n == 1, pattern
        return new
    return f


def _sub(old, new):
    def f(text):
        assert old in text, old
        return text.replace(old, new, 1)
    return f


def _api(fn):
    def f(api):
        api = copy.deepcopy(api)
        fn(api)
        return api
    return f


def _add_member(obj, member):
    return _api(lambda a: a["objects"][obj]["members"].append(member))


MUTATIONS = [
    # (name, header mutation or None, manifest mutation or None, expected substring, or None = no new problem)
    ("reserved-phase2-declared", _sub("OTC_API void otc_close(", "OTC_API otc_status otc_heights(void);\nOTC_API void otc_close("),
     None, "otc_heights  (reserved"),
    ("no-OTC_FORMAT_VERSION", _drop_line(r"^#define OTC_FORMAT_VERSION .*$"), None, "OTC_FORMAT_VERSION  (constant"),
    ("new-constant-c", None, _api(lambda a: a["constants"].__setitem__("X", {"value": 1, "c": "OTC_X_MISSING"})),
     "OTC_X_MISSING"),
    ("fetch-options-no-error", _drop_line(r"^\s*otc_error\s+\*error;\s*$"), None, "otc_fetch_options.error"),
    ("fetch-only-option-ok", None, _api(lambda a: a["client_options"]["c_only"].append(
        {"name": "cache_dir", "note": "otc_fetch_options only"})), None),
    ("c-only-option-names-no-struct", None, _api(lambda a: a["client_options"]["c_only"].append(
        {"name": "cache_dir", "note": "somewhere"})), "names no otc_*_options struct"),
    ("new-filter", None, _api(lambda a: a["filters"].append({"name": "region"})), "otc_filter.region"),
    ("filter-member-dropped", _drop_line(r"^\s*const char \*source_type;.*$"), None, "otc_filter.source_type"),
    ("method-without-c", None, _add_member("Release", {"name": "frobnicate", "kind": "method", "args": []}),
     "Release.frobnicate: no C mapping"),
    ("attribute-without-c", None, _add_member("Station", {"name": "elevation", "kind": "attribute"}),
     "Station.elevation: no C mapping"),
    ("field-of-object-without-c", None, _add_member("UpdateResult", {"name": "reason", "kind": "field"}),
     "UpdateResult.reason: no C mapping"),
    ("update-param-renamed", _sub("const char *current, char *path, size_t len,\n                                    size_t *needed, bool *updated",
                                  "const char *current, char *path, size_t len,\n                                    size_t *needed, bool *did_update"),
     None, "otc_fetch_update(updated)"),
    ("count-without-at", _drop_line(r"^OTC_API otc_status otc_release_info_file_at\(.*$"), None,
     "otc_release_info_files"),
    ("list-c-half-missing", _drop_line(r"^OTC_API .*\botc_release_convention_at\(.*$"), None, "otc_release_convention_at"),
    ("token-in-macro-body-only", _sub("OTC_API otc_status otc_search(", "#define otc_find otc_search\nOTC_API otc_status otc_search_v2("),
     None, "otc_search  (Release.search"),
    ("token-in-comment-only", _sub("OTC_API otc_status otc_nearest(", "/* otc_nearest */ OTC_API otc_status otc_nearest_v2("),
     None, "otc_nearest  (Release.nearest"),
    ("ts-only-member-ok", None, _add_member("Station", {"name": "to_json", "kind": "method", "languages": ["typescript"]}),
     None),
    ("ts-only-field-ok", None, _add_member("Station", {"name": "ts_extra", "kind": "field", "languages": ["typescript"]}),
     None),
    ("ts-only-error-ok", None, _api(lambda a: a["errors"].append(
        {"code": "browser_only", "class": "BrowserError", "c": None, "fields": [], "languages": ["typescript"]})), None),
    ("c-error-without-c", None, _api(lambda a: a["errors"].append(
        {"code": "new_code", "class": "NewError", "fields": [], "languages": ["c"]})), "error new_code"),
    ("extra-enum-value", _sub("OTC_ALIAS_SYSTEM_OTHER", "OTC_ALIAS_SYSTEM_FOO, OTC_ALIAS_SYSTEM_OTHER"), None,
     "extra value(s) ['OTC_ALIAS_SYSTEM_FOO']"),
    ("missing-enum-value", _sub("OTC_ALIAS_SYSTEM_LINZ, ", ""), None, "OTC_ALIAS_SYSTEM_LINZ"),
    ("extra-status", _sub("OTC_E_READER_TOO_OLD = 19", "OTC_E_READER_TOO_OLD = 19,\n    OTC_E_SURPRISE = 20"), None,
     "otc_status: extra value(s) ['OTC_E_SURPRISE']"),
    ("no-SUPPORTED_FORMAT_MAJORS-c", None, _api(lambda a: a["constants"]["SUPPORTED_FORMAT_MAJORS"].pop("c")), None),
    ("no-constants-c_only", None, _api(lambda a: a["constants"].pop("c_only")), "constants has no c_only"),
    ("no-client_options-c_only", None, _api(lambda a: a["client_options"].pop("c_only")), "client_options has no c_only"),
    ("no-filters", None, _api(lambda a: a.pop("filters")), "api.json has no filters"),
]


def self_test(api, header):
    base, _ = check(api, header)
    failures = []
    for name, hmut, amut, expect in MUTATIONS:
        try:
            got, _ = check(amut(api) if amut else api, hmut(header) if hmut else header)
        except Exception as e:  # a crash is a failure of the checker
            failures.append(f"{name}: the check crashed: {type(e).__name__}: {e}")
            continue
        new = [p for p in got if p not in base]
        if expect is None and new:
            failures.append(f"{name}: false failure {new}")
        elif expect is not None and not any(expect in p for p in new):
            failures.append(f"{name}: not caught (wanted a problem with {expect!r}; new problems {new})")
    return failures


def main(argv):
    api = json.loads((ROOT / "conformance/api.json").read_text(encoding="utf-8"))
    header = (ROOT / "c/include/opentideconstants.h").read_text(encoding="utf-8")
    problems, notes = check(api, header)
    rc = 0
    if notes:
        print(f"constants with no c in api.json (not in C): {', '.join(notes)}")
    if problems:
        print(f"C header does not match the API manifest: {len(problems)} problem(s):")
        for m in problems:
            print("  " + m)
        rc = 1
    else:
        print("C header declares every name the API manifest implies, and no extra enum value or phase 2 name")
    if "--no-self-test" not in argv:
        failures = self_test(api, header)
        if failures:
            print(f"self-test FAILED: {len(failures)} of {len(MUTATIONS)} mutation(s):")
            for f in failures:
                print("  " + f)
            rc = 1
        else:
            print(f"self-test: all {len(MUTATIONS)} mutations caught")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
