# /// script
# requires-python = ">=3.10"
# ///
"""Check the C public header against the API manifest (conformance/api.json).

    uv run c/tools/check_manifest.py      exit 0 when the header declares every C name the manifest implies,
                                          declares no extra enum value or status, and no pending name

Rules (api.json "naming.c"): an operation's c names its function(s) (a slash separates several, and each
must be declared); c "f(p)" names the parameter p of the function f; c "(C: T.m)" names the member m of
the struct T; another c in parentheses is a note that says how C covers the member. A field or predicate
with no c, of an object with C type T, is the accessor T_<field>, T_<field>_json, or the list pair
T_<singular>_count and T_<singular>_at, or a struct member when c_struct is true. A method or attribute
with no c, or a member of an object with no C type, is an error unless its languages leave out c. Enum
values are OTC_<ENUM>_<VALUE> plus OTC_<ENUM>_OTHER (and an optional OTC_<ENUM>_UNSET), and the C enum
has no other value. Error codes map to the otc_status values in errors[].c, and otc_status has no other
value than OTC_OK and the pending errors. Every filter is a member of otc_filter. Every constant with a c
is declared, and so is every name in constants.c_only. Every client_options.c_only option is a member of
each options struct its note names. Every c_structs struct is a typedef with its members, and its init
function is declared. A C type T may be declared as T or T_t.

Names in pending_port.c (prediction spec 5, not ported to C yet) are not required and must not be declared:
a pending object's C type and the C functions its members name, a pending member's C function(s), a pending
enum's values and a pending c_structs struct. Exception (CR D24): a pending error's otc_status value may be
declared or not, so that its number can be fixed early (OTC_E_UNSUPPORTED_CONVENTION = 18). Every pending
name must be a manifest name that applies to C.

A name counts as declared only by a declaration of its kind: a function by an OTC_API prototype or a
function-like #define, a constant by #define or an enum value, a type by a typedef. A token in a comment
or a macro body does not count, and neither does a declaration in an #if 0 block (its #else branch
counts). Comments are removed in one pass from left to right that skips string and character literals,
so "// x/*" or "a/*b" does not hide the code after it. C has helpers the manifest does not list (otc_*_init, otc_*_free, otc_status_code), so extra
functions are not an error.

After the check, the script runs its own mutation self-test (each mutation of the manifest or the header
must be caught); --no-self-test skips it.
"""
import argparse
import copy
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FILTER_STRUCT = "otc_filter"
REQUIRED_KEYS = ("objects", "enums", "errors", "constants", "filters", "client_options", "c_structs", "pending_port")
PENDING_KEYS = ("objects", "members", "enums", "errors", "c_structs")


def strip_comments(text):
    """The text with every comment replaced by a space (a block comment keeps its newlines). One pass,
    left to right: a "/*" inside a // comment or a string or character literal opens nothing (R3-310)."""
    out = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
            out.append(" ")
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            end = n if j < 0 else j + 2
            out.append(" " + "\n" * text.count("\n", i, end))
            i = end
        elif c in "\"'":
            j = i + 1
            while j < n and text[j] != c and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            out.append(text[i:j + 1])
            i = j + 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def drop_if0(lines):
    """The lines a compiler can see: the body of an #if 0 is left out, its #else (or #elif) is kept.
    Any other conditional is kept whole (conservative: a name under #ifdef X counts) (R3-312)."""
    keep = []
    stack = []   # one entry per open conditional: True while its current branch is dead
    for line in lines:
        d = re.match(r"\s*#\s*(if|ifdef|ifndef|elif|else|endif)\b(.*)", line)
        outer_dead = any(stack[:-1]) if stack else False
        if d:
            kw, rest = d.groups()
            if kw in ("if", "ifdef", "ifndef"):
                stack.append(any(stack) or (kw == "if" and re.fullmatch(r"\s*\(?\s*0\s*\)?\s*", rest) is not None))
            elif kw in ("elif", "else") and stack:
                stack[-1] = outer_dead
            elif kw == "endif" and stack:
                stack.pop()
            continue
        if not any(stack):
            keep.append(line)
    return keep


def split_top(text, sep):
    """text split at each sep that is not inside (), [] or {}."""
    parts, depth, cur = [], 0, []
    for ch in text:
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return parts


def declarator_name(decl):
    """The name a declarator declares: (*name)(...) for a function pointer, else the last word
    after removing a bit-field width, array bounds and nested aggregate bodies."""
    fp = re.search(r"\(\s*\*\s*(\w+)\s*\)", decl)
    if fp:
        return fp.group(1)
    decl = re.sub(r"\[[^\]]*\]", " ", decl).split(":", 1)[0]
    words = re.findall(r"\w+", decl)
    return words[-1] if words else None


def struct_members(body):
    """The member names of a struct body: nested aggregates, function pointers, comma lists, bit-fields."""
    names = set()
    for decl in split_top(body, ";"):
        head = re.sub(r"\{.*\}", " ", decl, flags=re.S)   # struct { ... } a, b  ->  struct a, b
        for part in split_top(head, ","):
            name = declarator_name(part)
            if name:
                names.add(name)
    return names


def braced(code, start):
    """The index just after the } that closes the { at code[start]."""
    depth = 0
    for i in range(start, len(code)):
        if code[i] == "{":
            depth += 1
        elif code[i] == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    return len(code)


class Header:
    """The declarations of the header, each by its kind."""

    def __init__(self, text):
        text = strip_comments(text).replace("\\\n", " ")
        lines = drop_if0(text.split("\n"))
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
            for p in split_top(m.group(2), ","):
                if re.findall(r"\w+", p) not in ([], ["void"]):
                    params.append(declarator_name(p))
            self.functions[m.group(1)] = params
        # enum and struct definitions: typedef enum|struct [tag] { ... } T;  or  enum|struct tag { ... };
        # with a later typedef enum|struct tag T; (b8-4 H6). The body is matched by brace depth (R3-320).
        tag_types = {}
        for m in re.finditer(r"\btypedef\s+(enum|struct)\s+(\w+)\s+(\w+)\s*;", code):
            tag_types.setdefault((m.group(1), m.group(2)), []).append(m.group(3))
        self.enums = []
        self.structs = {}
        for m in re.finditer(r"\b(typedef\s+)?(enum|struct)\s*(\w*)\s*\{", code):
            end = braced(code, m.end() - 1)
            body = code[m.end():end - 1]
            after = re.match(r"\s*(\w*)\s*;", code[end:])
            if m.group(1):
                names = [after.group(1)] if after and after.group(1) else []
            elif after and not after.group(1) and m.group(3):
                names = tag_types.get((m.group(2), m.group(3)), [])
            else:
                continue   # a nested aggregate, or a definition with a variable
            for name in names:
                if m.group(2) == "enum":
                    vals = [v.group(1) for item in split_top(body, ",")
                            if (v := re.match(r"\s*([A-Za-z_]\w*)", item))]
                    self.enums.append((name, vals))
                else:
                    self.structs[name] = struct_members(body)
        self.enum_values = {v for _, vals in self.enums for v in vals}
        self.types = set(self.structs) | {name for name, _ in self.enums}
        self.types |= set(re.findall(r"\btypedef\s+(?:(?:struct|enum|union)\s+)?\w+\s*\*?\s*(\w+)\s*;", code))
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

    def c_functions(c):
        """The C function names a member's c gives (none for a note or a struct member)."""
        if not c or c.startswith("(") or "{object}" in c:
            return []
        return [re.sub(r"\(\w+\)$", "", fn) for fn in c.split("/")]

    # pending names (pending_port.c): each must be a manifest name that applies to C
    pend = api["pending_port"].get("c")
    if not isinstance(pend, dict):
        problems.append("api.json has no pending_port.c")
        pend = {}
    unknown = sorted(set(pend) - set(PENDING_KEYS))
    if unknown:
        problems.append(f"pending_port.c: unknown key(s) {unknown}")
    pend_objects = set(pend.get("objects", []))
    for o in sorted(pend_objects - set(api["objects"])):
        problems.append(f"pending_port.c: object {o} is not a manifest object")
    pend_members = set()
    for qn in pend.get("members", []):
        oname, _, name = qn.partition(".")
        ms = [m for m in api["objects"].get(oname, {}).get("members", []) if m.get("name") == name]
        if not ms or not for_c(ms[0]):
            problems.append(f"pending_port.c: member {qn} is not a manifest member for C")
        pend_members.add((oname, name))
    pend_enums = set(pend.get("enums", []))
    for e in sorted(pend_enums - set(api["enums"])):
        problems.append(f"pending_port.c: enum {e} is not a manifest enum")
    pend_errors = set(pend.get("errors", []))
    c_codes = {e.get("code") for e in api["errors"] if for_c(e) and e.get("c")}
    for c in sorted(pend_errors - c_codes):
        problems.append(f"pending_port.c: error {c} is not a manifest error with a C status")
    pend_structs = set(pend.get("c_structs", []))
    for st in sorted(pend_structs - (set(api["c_structs"]) - {"note"})):
        problems.append(f"pending_port.c: c_structs {st} is not a manifest c_structs name")

    def need_param(fn, param, where):
        if fn not in h.functions:
            problems.append(f"{fn}  ({where}: no OTC_API function)")
        elif param not in h.functions[fn]:
            problems.append(f"{fn}({param})  ({where}: no such parameter)")

    # objects
    for oname, obj in api["objects"].items():
        if oname in pend_objects:
            continue
        ctype = obj.get("c")
        if ctype:
            need_type(ctype, f"type of {oname}")
        for i, m in enumerate(obj.get("members", [])):
            if not isinstance(m.get("name"), str) or not m["name"]:
                problems.append(f"{oname}: member #{i} has no name  (api.json entry {m})")
                continue
            where = f"{oname}.{m['name']}"
            if not for_c(m) or (oname, m["name"]) in pend_members:
                continue
            c = m.get("c")
            if c and "{object}" in c:
                if ctype:
                    need_function(base(ctype) + "_raw_json", where)
                else:
                    problems.append(f"{where}: {c} needs an object with a C type")
                continue
            if c and c.startswith("(C: "):  # a struct member named in the note
                note = re.fullmatch(r"\(C: (?:(\w+)\.)?(\w+)\)", c)
                if not note:
                    problems.append(f"{where}: c {c!r} is not \"(C: T.m)\" or \"(C: m)\"")
                elif not (note.group(1) or ctype):
                    problems.append(f"{where}: c {c!r} names no struct, and {oname} has no C type")
                else:
                    need_member(note.group(1) or ctype, note.group(2), where)
                continue
            pm = re.fullmatch(r"(\w+)\((\w+)\)", c or "")
            if pm:  # a parameter of a function
                need_param(*pm.groups(), where)
                continue
            if c and c.startswith("("):  # a note that says how C covers it
                continue
            if c:
                for fn in c.split("/"):
                    pm = re.fullmatch(r"(\w+)\((\w+)\)", fn)
                    if pm:
                        need_param(*pm.groups(), where)
                    else:
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
            singulars = [acc]   # aliases -> alias, entries -> entry, flags -> flag
            if acc.endswith("ies"):
                singulars.append(acc[:-3] + "y")
            if acc.endswith("es"):
                singulars.append(acc[:-2])
            if acc.endswith("s"):
                singulars.append(acc[:-1])
            fns = set(h.functions) | h.function_macros
            ok = acc in fns or acc + "_json" in fns or any(s + "_count" in fns and s + "_at" in fns
                                                           for s in singulars)
            if not ok:
                pairs = ", ".join(f"{s}_count/_at" for s in singulars[1:] or singulars)
                problems.append(f"{acc}  ({where}: no accessor {acc}, {acc}_json or {pairs})")

    # filters: members of otc_filter (a filter whose languages leave out c is not)
    for f in api["filters"]:
        if for_c(f):
            need_member(FILTER_STRUCT, f.get("name"), f"filter {f.get('name')}")

    # enums: exactly the manifest's values, plus OTHER and an optional UNSET
    for ename, values in api["enums"].items():
        if ename in pend_enums:
            continue
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
    pending_statuses = set()
    for e in api["errors"]:
        if not for_c(e):
            continue
        if e.get("code") in pend_errors:
            if e.get("c"):
                pending_statuses.add(e["c"])   # CR D24: may be declared, or not
            continue
        c = e.get("c")
        if not c:
            problems.append(f"error {e.get('code')}: its languages include c but it has no c")
            continue
        status_values.add(c)
        if c not in h.enum_values:
            problems.append(f"{c}  (error {e.get('code')}: no otc_status value)")
    status_block = h.enum_of("OTC_OK")[1]
    if not status_block:
        problems.append("OTC_OK  (otc_status: no enum value)")
    extra = sorted(set(status_block) - status_values - pending_statuses - {"OTC_OK"})
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

    # C structs no manifest object maps (c_structs): a typedef with its members, and its init function
    for sname, spec in api["c_structs"].items():
        if sname == "note" or sname in pend_structs:
            continue
        need_type(sname, f"c_structs {sname}")
        for mem in spec.get("members", []):
            need_member(sname, mem, f"c_structs {sname}")
        if spec.get("init"):
            need_function(spec["init"], f"c_structs {sname} init")

    # pending names must not be declared yet (a pending error's status may be, CR D24)
    def absent(name, why):
        if name and h.declared(name):
            problems.append(f"{name}  (pending for C: {why}, must not be declared yet)")

    for oname in sorted(pend_objects):
        obj = api["objects"].get(oname, {})
        if obj.get("c"):
            absent(obj["c"], f"type of {oname}")
            absent(obj["c"] + "_t", f"type of {oname}")
        for m in obj.get("members", []):
            if for_c(m):
                for fn in c_functions(m.get("c")):
                    absent(fn, f"{oname}.{m.get('name')}")
    for oname, name in sorted(pend_members):
        for m in api["objects"].get(oname, {}).get("members", []):
            if m.get("name") == name:
                if not c_functions(m.get("c")):
                    problems.append(f"pending_port.c: member {oname}.{name} has no C function, so nothing checks "
                                    f"that it is not declared")
                for fn in c_functions(m.get("c")):
                    absent(fn, f"{oname}.{name}")
    for ename in sorted(pend_enums):
        prefix = "OTC_" + upper(ename) + "_"
        for v in sorted(v for v in h.enum_values if v.startswith(prefix)):
            problems.append(f"{v}  (pending for C: enum {ename}, must not be declared yet)")
    for sname in sorted(pend_structs):
        absent(sname, f"c_structs {sname}")

    return problems, notes


# ---------------------------------------------------------------- self-test

# The guards raise (not assert), so a mutation whose pattern drifted fails under python -O too.
def _drop_line(pattern):
    def f(text):
        new, n = re.subn(pattern, "", text, count=1, flags=re.M)
        if n != 1:
            raise ValueError(f"mutation pattern not found: {pattern}")
        return new
    return f


def _sub(old, new):
    def f(text):
        if old not in text:
            raise ValueError(f"mutation text not found: {old!r}")
        return text.replace(old, new, 1)
    return f


def _wrap(pattern, before, after):
    """The first line matching pattern, with before and after lines around it."""
    def f(text):
        new, n = re.subn(pattern, lambda m: before + m.group(0) + after, text, count=1, flags=re.M)
        if n != 1:
            raise ValueError(f"mutation pattern not found: {pattern}")
        return new
    return f


def _then(*fs):
    def f(text):
        for g in fs:
            text = g(text)
        return text
    return f


def _append(tail):
    return lambda text: text.rstrip("\n") + "\n" + tail


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
    ("pending-function-declared", _sub("OTC_API void otc_close(", "OTC_API otc_status otc_heights(void);\nOTC_API void otc_close("),
     None, "otc_heights  (pending"),
    ("pending-object-function-declared", _sub("OTC_API void otc_close(", "OTC_API otc_status otc_astro_node_factor(void);\n"
                                              "OTC_API void otc_close("), None, "otc_astro_node_factor  (pending"),
    ("pending-result-function-declared", _sub("OTC_API void otc_close(", "OTC_API otc_status otc_tz_open(void);\n"
                                              "OTC_API void otc_close("), None, "otc_tz_open  (pending"),
    ("pending-object-type-declared", _sub("OTC_API void otc_close(", "typedef struct otc_height_t { int64_t t; } otc_height_t;\n"
                                          "OTC_API void otc_close("), None, "otc_height_t  (pending"),
    ("pending-struct-declared", _sub("OTC_API void otc_close(", "typedef struct otc_predict_opts { size_t struct_size; } "
                                     "otc_predict_opts;\nOTC_API void otc_close("), None, "otc_predict_opts  (pending"),
    ("pending-enum-value-declared", _sub("OTC_API void otc_close(", "typedef enum { OTC_EXTREME_TYPE_HIGH, "
                                         "OTC_EXTREME_TYPE_OTHER } otc_extreme_type_t;\nOTC_API void otc_close("), None,
     "OTC_EXTREME_TYPE_HIGH  (pending"),
    ("pending-status-declared-ok", _sub("OTC_E_READER_TOO_OLD = 19", "OTC_E_READER_TOO_OLD = 19,\n    OTC_E_NO_CONSTANTS = 20"),
     None, None),
    ("pending-member-dropped", None, _api(lambda a: a["pending_port"]["c"]["members"].remove("Release.heights")),
     "otc_heights  (Release.heights: no OTC_API function)"),
    ("pending-object-dropped", None, _api(lambda a: a["pending_port"]["c"]["objects"].remove("HeightPoint")),
     "otc_height_t  (type of HeightPoint: no typedef)"),
    ("pending-enum-dropped", None, _api(lambda a: a["pending_port"]["c"]["enums"].remove("extreme_type")),
     "OTC_EXTREME_TYPE_HIGH  (enum extreme_type: no enum value)"),
    ("pending-error-dropped", None, _api(lambda a: a["pending_port"]["c"]["errors"].remove("no_constants")),
     "OTC_E_NO_CONSTANTS  (error no_constants: no otc_status value)"),
    ("pending-error-dropped-status-present-ok", None, _api(lambda a: a["pending_port"]["c"]["errors"].remove(
        "unsupported_convention")), None),
    ("pending-struct-dropped", None, _api(lambda a: a["pending_port"]["c"]["c_structs"].remove("otc_predict_opts")),
     "otc_predict_opts  (c_structs otc_predict_opts: no typedef)"),
    ("pending-unknown-member", None, _api(lambda a: a["pending_port"]["c"]["members"].append("Release.frobnicate")),
     "pending_port.c: member Release.frobnicate is not a manifest member for C"),
    ("pending-member-not-for-c", None, _api(lambda a: a["pending_port"]["c"]["members"].append("Release.ranges")),
     "pending_port.c: member Release.ranges is not a manifest member for C"),
    ("pending-unknown-error", None, _api(lambda a: a["pending_port"]["c"]["errors"].append("unsupported")),
     "pending_port.c: error unsupported"),
    ("pending-unknown-key", None, _api(lambda a: a["pending_port"]["c"].__setitem__("functions", [])),
     "pending_port.c: unknown key(s)"),
    ("no-pending_port", None, _api(lambda a: a.pop("pending_port")), "api.json has no pending_port"),
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
    # one mutation for each rule that had none (R3-313)
    ("c-only-constant-missing", _drop_line(r"^#define OTC_ABI_VERSION .*$"), None, "OTC_ABI_VERSION  (constant, C only"),
    ("C-note-struct-member-renamed", _sub("    const char *id;\n    double      distance_km;",
                                          "    const char *ident;\n    double      distance_km;"), None,
     "otc_nearby.id  (Nearby.station)"),
    ("raw-json-missing", _drop_line(r"^OTC_API otc_status otc_station_raw_json\(.*$"), None, "otc_station_raw_json  (Station.raw"),
    ("c-struct-member-missing", _drop_line(r"^    double                 time_mae_min;$"), None,
     "otc_validation_t.time_mae_min  (Validation.time_mae_min)"),
    ("object-type-missing", _drop_line(r"^typedef struct otc_release_info otc_release_info;.*$"), None,
     "otc_release_info  (type of ReleaseInfo: no typedef)"),
    # comments and #if 0 (R3-310, R3-312), enum values without the prefix (R3-311)
    ("line-comment-opens-no-block", _then(_sub("OTC_API void otc_close(", "// see data/*.json\n"
                                                "OTC_API otc_status otc_heights(void);\nOTC_API void otc_close("),
                                           _append("/* end */\n")), None, "otc_heights  (pending"),
    ("string-opens-no-block", _then(_sub("OTC_API void otc_close(", '#define OTC_ZZ_URL "a/*b"\n'
                                          "OTC_API otc_status otc_heights(void);\nOTC_API void otc_close("),
                                     _append("/* end */\n")), None, "otc_heights  (pending"),
    ("unprefixed-extra-enum-value", _sub("OTC_ALIAS_SYSTEM_OTHER", "BOGUS_EXTRA, OTC_ALIAS_SYSTEM_OTHER"), None,
     "extra value(s) ['BOGUS_EXTRA']"),
    ("prototype-only-in-if-0", _wrap(r"^OTC_API void otc_close\(.*$", "#if 0\n", "\n#endif"), None,
     "otc_close  (Client.close"),
    ("define-in-else-of-if-0-ok", _wrap(r"^#define OTC_FORMAT_VERSION .*$", "#if 0\n#define OTC_ZZ 1\n#else\n", "\n#endif"),
     None, None),
    # declarator shapes that are declared (R3-320)
    ("nested-aggregate-member-ok", _sub("typedef struct otc_filter {", "typedef struct otc_filter {\n    struct { int a; } zz;"),
     None, None),
    ("comma-declarator-ok", _sub("const char *source_type;", "const char *source_type, *zz_extra;"), None, None),
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
    ap = argparse.ArgumentParser(description="Check the C public header against conformance/api.json.")
    ap.add_argument("--no-self-test", action="store_true", help="skip the mutation self-test")
    a = ap.parse_args(argv)
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
        print("C header declares every name the API manifest implies, and no extra enum value or pending name")
    if not a.no_self_test:
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
