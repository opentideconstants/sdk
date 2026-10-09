# /// script
# requires-python = ">=3.10"
# ///
"""Check each SDK's supported-formats.json (SDK spec §7.4, §8.6).

Run: python conformance/tools/check_supported_formats.py     (exit 0 only if every check passes)

Each language commits one supported-formats.json in its package directory (python/, ruby/, js/, c/):

    {"language": "python", "version": "1.0.0", "supported_format_version": "1.0"}

The publication plan's reader gate reads it from the GitHub release of the tag <language>-v<version>. This
check fails when, for any language:
  - the file is missing, is not a JSON object, or has other keys than these three;
  - language is not the directory's tag prefix (python, ruby, js, c);
  - version is not the package version (python/src/opentideconstants/_client.py __version__, ruby
    version.rb VERSION, the top-level "version" of js/package.json read as JSON, C OTC_VERSION);
  - supported_format_version is not the SDK's declared SUPPORTED_FORMAT_VERSION (C: OTC_FORMAT_VERSION);
  - the SDK declares no SUPPORTED_FORMAT_VERSION, or declares it more than once with different values.
  - a file that the check reads cannot be read (missing, a directory, not UTF-8; a .py file that is not valid
    Python). This is a FAIL line for that language, and the other languages are still checked.

The declaration is read from the source, so the check needs no toolchain. Every declaration counts, in
every source file of the SDK:
  - Python: python/src/**/*.py and *.pyi, parsed with the ast module. Every binding of the name counts: an
    assignment, an annotated assignment with a value or a walrus to the name (or to an attribute of that name)
    gives its value. Any other binding cannot be read, so it fails: an unpacking, augmented, for, with,
    comprehension, except or match target, del, a def, class or parameter of that name, an import alias to it
    (from x import Y as SUPPORTED_FORMAT_VERSION), an import of it from outside the package, and a string-keyed
    write (globals()[...] =, setattr, update(SUPPORTED_FORMAT_VERSION=...), a dict key). A docstring or a
    comment is not a declaration.
  - Ruby: ruby/lib/**/*.rb; a line that starts with the constant (optionally Module::-qualified) and
    assigns it with =, ||= or &&=, and any const_set of the name. Comment lines and =begin/=end blocks
    are not declarations.
  - TypeScript: js/src/**/*.{ts,mts,cts,tsx,js,mjs,cjs}; a line that starts with a const/let/var
    declaration of the name (optionally export/declare), a line that starts with an assignment to it, and
    an export that renames another binding to it ("as SUPPORTED_FORMAT_VERSION"). A JSDoc or block
    comment line starts with "*" or "/*", so it is not a declaration.
  - C: c/include/**/*.h and c/src/**/*.{h,c}; a #define OTC_FORMAT_VERSION line.
A declaration whose value is not a quoted MAJOR.MINOR literal (a computed value, an aliased export, a
const_set) cannot be checked, so it fails.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NAME = "SUPPORTED_FORMAT_VERSION"
VERSION_RE = r"[0-9]+\.[0-9]+"
KEYS = {"language", "version", "supported_format_version"}

RUBY_ASSIGN = re.compile(rf"^\s*(?:(?:::)?[A-Z]\w*::)*(?:::)?{NAME}\s*(?:\|\||&&)?=(?![=~>])\s*([^\n]*)$", re.M)
RUBY_CONST_SET = re.compile(rf"^(?!\s*#).*\bconst_set\b[\s(]*[:'\"]?{NAME}\b[^\n]*$", re.M)
TS_DECL = re.compile(rf"^\s*(?:export\s+)?(?:declare\s+)?(?:const|let|var)\s+{NAME}\b\s*(?::[^=\n]+)?=(?![=>])\s*([^\n]*)$",
                     re.M)
TS_ASSIGN = re.compile(rf"^\s*{NAME}\s*(?:\|\||&&|\?\?)?=(?![=>])\s*([^\n]*)$", re.M)
TS_ALIAS = re.compile(rf"^(?!\s*(?:\*|//|/\*)).*\bas\s+{NAME}\b[^\n]*$", re.M)
C_DEFINE = re.compile(r"^\s*#\s*define\s+OTC_FORMAT_VERSION\b\s*([^\n]*)$", re.M)


def literal(rhs):
    """The version in a declaration's value: a quoted MAJOR.MINOR literal (Ruby may add .freeze, TypeScript
    as const, C a /* comment */), else None."""
    v = re.sub(r"/\*.*?\*/", "", rhs)
    v = re.sub(r"\s*(//.*|#.*)$", "", v.strip()).rstrip(";").strip()
    v = re.sub(r"\s+as\s+const$", "", v)
    v = re.sub(r"\.freeze$", "", v)
    m = re.fullmatch(rf"""(['"])({VERSION_RE})\1""", v)
    return m.group(2) if m else None


def files(globs):
    seen = set()
    for g in globs:
        for p in sorted(ROOT.glob(g)):
            if p.is_file() and p not in seen:
                seen.add(p)
                yield p


def rel(p):
    return p.relative_to(ROOT).as_posix()


class Unreadable(Exception):
    """A file that cannot be read as UTF-8 text (missing, a directory, not UTF-8, no permission)."""


def read(p):
    try:
        return p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise Unreadable(f"cannot read {rel(p)}: {e}") from None


# ---- the package version: (versions found, the file, an error or None)


def version_by_regex(path, regex):
    def get():
        try:
            return [m.group(1) for m in re.finditer(regex, read(ROOT / path), re.M)], path, None
        except Unreadable as e:
            return [], path, str(e)
    return get


def version_from_package_json():
    path = "js/package.json"
    try:
        doc = json.loads(read(ROOT / path))
    except Unreadable as e:
        return [], path, str(e)
    except ValueError as e:
        return [], path, f"{path} is not JSON: {e}"
    v = doc.get("version") if isinstance(doc, dict) else None
    return ([v] if isinstance(v, str) else []), path, None


# ---- the declared SUPPORTED_FORMAT_VERSION: a list of (file, version or None for "cannot read")


PY_READ_CALLS = {"getattr", "hasattr", "get"}  # a call that names the constant as a string but does not bind it


def python_bindings(tree):
    """Every binding of NAME in a module, as (version or None, why). A plain assignment, an annotated assignment
    or a walrus whose target is the name (or an attribute of that name) gives the literal's value. Any other
    binding gives None (cannot read): an unpacking, augmented, for, with, comprehension, except or match target,
    del, a def or class or parameter of that name, an import alias to it, an import of it from outside the
    package, a string-keyed write (globals()[...] =, setattr(..., "NAME", ...), update(NAME=...) or a dict key)."""
    found, seen = [], set()

    def named(t):
        return (isinstance(t, ast.Name) and t.id == NAME) or (isinstance(t, ast.Attribute) and t.attr == NAME)

    def value_of(node, value):
        if isinstance(value, ast.Constant) and isinstance(value.value, str) and re.fullmatch(VERSION_RE, value.value):
            return value.value, None
        return None, f"line {node.lineno}: not a quoted MAJOR.MINOR literal"

    def unreadable(node, what):
        found.append((None, f"line {node.lineno}: {what} binds {NAME}; its value cannot be read"))

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(named(t) for t in node.targets):
            seen.update(id(t) for t in node.targets if named(t))
            found.append(value_of(node, node.value))
        elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)) and named(node.target):
            seen.add(id(node.target))
            if node.value is not None:  # an annotation only (x: str) declares no value
                found.append(value_of(node, node.value))
        elif isinstance(node, ast.AugAssign) and named(node.target):
            seen.add(id(node.target))
            unreadable(node, "an augmented assignment")
    for node in ast.walk(tree):
        if isinstance(node, (ast.Name, ast.Attribute)) and named(node) and isinstance(node.ctx, (ast.Store, ast.Del)) \
                and id(node) not in seen:
            unreadable(node, "a del" if isinstance(node.ctx, ast.Del) else "an unpacking, for, with or comprehension target")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == NAME:
            unreadable(node, "a def or class")
        elif isinstance(node, ast.arg) and node.arg == NAME:
            unreadable(node, "a parameter")
        elif isinstance(node, ast.ExceptHandler) and node.name == NAME:
            unreadable(node, "an except clause")
        elif isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name == NAME \
                or isinstance(node, ast.MatchMapping) and node.rest == NAME:
            unreadable(node, "a match pattern")
        elif isinstance(node, ast.Import):
            for a in node.names:
                if (a.asname or a.name) == NAME:
                    unreadable(node, "an import")
        elif isinstance(node, ast.ImportFrom):
            inside = node.level > 0 or (node.module or "").split(".")[0] == "opentideconstants"
            for a in node.names:
                if a.asname == NAME and a.name != NAME:
                    unreadable(node, "an import alias")
                elif (a.asname or a.name) == NAME and not inside:
                    unreadable(node, f"an import from {node.module}")
        elif isinstance(node, ast.Subscript) and isinstance(node.ctx, (ast.Store, ast.Del)) \
                and isinstance(node.slice, ast.Constant) and node.slice.value == NAME:
            unreadable(node, "a string-keyed write")
        elif isinstance(node, ast.Call):
            func = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", None)
            if any(k.arg == NAME for k in node.keywords) or (
                    func not in PY_READ_CALLS and any(isinstance(a, ast.Constant) and a.value == NAME for a in node.args)):
                unreadable(node, f"a call to {func or 'a function'}")
        elif isinstance(node, ast.Dict) and any(isinstance(k, ast.Constant) and k.value == NAME for k in node.keys):
            unreadable(node, "a dict key")
    return found


def python_declarations():
    out = []
    for p in files(["python/src/**/*.py", "python/src/**/*.pyi"]):
        try:
            tree = ast.parse(p.read_bytes(), filename=str(p))  # bytes: ast honours a PEP 263 coding line
        except OSError as e:
            out.append((rel(p), None, f"cannot read: {e}"))
            continue
        except (SyntaxError, ValueError) as e:  # ValueError: a NUL byte (Python 3.10, 3.11)
            out.append((rel(p), None, f"not valid Python: {e}"))
            continue

        out += [(rel(p), v, why) for v, why in python_bindings(tree)]
    return out


def ruby_declarations():
    out = []
    for p in files(["ruby/lib/**/*.rb"]):
        try:
            text = re.sub(r"^=begin\b.*?^=end\b[^\n]*", "", read(p), flags=re.M | re.S)
        except Unreadable as e:
            out.append((rel(p), None, str(e)))
            continue
        for m in RUBY_ASSIGN.finditer(text):
            out.append((rel(p), literal(m.group(1)), None if literal(m.group(1)) else repr(m.group(0).strip())))
        for m in RUBY_CONST_SET.finditer(text):
            out.append((rel(p), None, repr(m.group(0).strip())))
    return out


def ts_declarations():
    out = []
    exts = ("ts", "mts", "cts", "tsx", "js", "mjs", "cjs")
    for p in files([f"js/src/**/*.{e}" for e in exts]):
        try:
            text = read(p)
        except Unreadable as e:
            out.append((rel(p), None, str(e)))
            continue
        for rx in (TS_DECL, TS_ASSIGN):
            for m in rx.finditer(text):
                out.append((rel(p), literal(m.group(1)), None if literal(m.group(1)) else repr(m.group(0).strip())))
        for m in TS_ALIAS.finditer(text):
            out.append((rel(p), None, repr(m.group(0).strip())))
    return out


def c_declarations():
    out = []
    for p in files(["c/include/**/*.h", "c/src/**/*.h", "c/src/**/*.c"]):
        try:
            text = read(p)
        except Unreadable as e:
            out.append((rel(p), None, str(e)))
            continue
        for m in C_DEFINE.finditer(text):
            out.append((rel(p), literal(m.group(1)), None if literal(m.group(1)) else repr(m.group(0).strip())))
    return out


# language: (package version reader, declaration reader)
LANGUAGES = {
    "python": (version_by_regex("python/src/opentideconstants/_client.py", r'^__version__\s*=\s*"([^"]+)"'),
               python_declarations),
    "ruby": (version_by_regex("ruby/lib/opentideconstants/version.rb", r'^\s*VERSION\s*=\s*"([^"]+)"'),
             ruby_declarations),
    "js": (version_from_package_json, ts_declarations),
    "c": (version_by_regex("c/include/opentideconstants.h", r'^\s*#\s*define\s+OTC_VERSION\s+"([^"]+)"'),
          c_declarations),
}


def check_language(lang):
    get_version, get_declarations = LANGUAGES[lang]
    path = ROOT / lang / "supported-formats.json"
    if not path.exists():
        return [f"{lang}: {path.relative_to(ROOT)} is missing"], None
    try:
        doc = json.loads(read(path))
    except Unreadable as e:
        return [f"{lang}: {e}"], None
    except ValueError as e:
        return [f"{lang}: {path.relative_to(ROOT)} is not JSON: {e}"], None
    if not isinstance(doc, dict) or set(doc) != KEYS:
        return [f"{lang}: {path.relative_to(ROOT)} must be an object with exactly the keys {sorted(KEYS)}"], None
    errs = []
    if doc["language"] != lang:
        errs.append(f"{lang}: language is {doc['language']!r}, not {lang!r} (the tag prefix {lang}-v)")
    versions, vfile, verr = get_version()
    if verr:
        errs.append(f"{lang}: {verr}")
    elif len(versions) != 1:
        errs.append(f"{lang}: expected one package version in {vfile}, found {len(versions)}")
    elif doc["version"] != versions[0]:
        errs.append(f"{lang}: version is {doc['version']!r}, but {vfile} says {versions[0]!r}")
    sfv = doc["supported_format_version"]
    if not isinstance(sfv, str) or not re.fullmatch(VERSION_RE, sfv):
        errs.append(f"{lang}: supported_format_version {sfv!r} is not MAJOR.MINOR")
    declared = get_declarations()
    unparsed = [(f, why) for f, v, why in declared if v is None]
    if unparsed:
        errs.append(f"{lang}: cannot read {NAME} as a quoted MAJOR.MINOR literal: {unparsed}")
        return errs, None
    values = sorted({v for _, v, _ in declared})
    if not values:
        errs.append(f"{lang}: the SDK declares no {NAME} (C: OTC_FORMAT_VERSION); every SDK must declare it")
        return errs, None
    if len(values) > 1:
        errs.append(f"{lang}: {NAME} is declared with different values: {[(f, v) for f, v, _ in declared]}")
        return errs, None
    if sfv != values[0]:
        errs.append(f"{lang}: supported_format_version is {sfv!r}, but the SDK declares {values[0]!r} ({declared[0][0]})")
    return errs, f"declared {values[0]} in {declared[0][0]}"


def main():
    problems = []
    for lang in LANGUAGES:
        try:
            errs, note = check_language(lang)
        except Exception as e:  # noqa: BLE001 - report it as this language's failure and check the others
            errs, note = [f"{lang}: the check itself failed: {type(e).__name__}: {e}"], None
        print(f"{'FAIL' if errs else 'PASS'}  {lang:7} {note or ''}")
        problems += errs
    for p in problems:
        print("  " + p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
