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
  - Ruby, TypeScript/JavaScript and C have no parser here, so the check reads the text around each
    occurrence of the name and fails closed: an occurrence that has the shape of a binding but is not a
    recognised literal declaration cannot be read, so it fails. Comments are not parsed out, so a
    commented-out declaration still counts (a different or unreadable one fails; reword or delete it).
  - Ruby: ruby/lib/**/*.rb, each statement (a line split at ";"). NAME =, ||= or &&= (optionally
    Module::-qualified) at the start of a statement is a declaration. A multiple assignment (A, NAME = ...),
    an operator assignment, class/module NAME, for NAME, rescue => NAME, a trailing-comma line (a multiple
    assignment across lines) and const_set cannot be read. "#{NAME}" and other reads pass.
  - TypeScript/JavaScript: js/src/**/*.{ts,mts,cts,tsx,js,mjs,cjs}. A const/let/var declaration of the name
    (optionally export/declare) and an assignment to NAME or to x.NAME (exports.NAME, module.exports.NAME) at
    the start of a statement are declarations; a statement starts at a line start or after ";", "{", "}" or
    "*/". Any other binding cannot be read: a second declarator (const A = 1, NAME = ...), declare const
    without a value, an object property or quoted key, a string-keyed write (exports["NAME"] =,
    Object.defineProperty), destructuring, a default, namespace or aliased import, an export that renames
    another binding to the name, an import or re-export of it from a package, a function, class member,
    parameter or for target. An import of the name from a relative module, export { NAME } and "${NAME}" pass.
  - C: c/include/**/*.h and c/src/**/*.{h,c}. #define OTC_FORMAT_VERSION at the start of a line ("#  define"
    and a leading /* comment */ allowed) is a declaration. #undef, a #define that does not start its line
    (a commented-out one) and a variable of that name cannot be read.
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


RUBY_CONST_SET = re.compile(rf"\bconst_set\b[\s(]*[:'\"]?{NAME}\b")
RUBY_DECL_BEFORE = re.compile(r"^\s*(?:(?:::)?[A-Z]\w*::)*(?:::)?$")
RUBY_DECL_AFTER = re.compile(r"^\s*(?:\|\||&&)?=(?![=~>])\s*(.*)$")
RUBY_ASSIGN_OP = re.compile(r"(?<![=!<>])(?:\|\||&&|\*\*|<<|>>|[-+*/%|&^])?=(?![=~>])")
RUBY_BINDER_BEFORE = re.compile(r"(?:\b(?:class|module)\s+(?:(?:::)?[A-Z]\w*::)*(?:::)?|\bfor\s+[^;]*|\brescue\b[^;]*=>\s*)$")

JS_ID = r"[\w$]"
JS_STMT = r"(?:^|[;{}]|\*/)\s*"
JS_DECL_BEFORE = re.compile(JS_STMT + r"(?:export\s+)?(?:declare\s+)?(?:const|let|var)\s+$")
JS_DECL_AFTER = re.compile(r"^\s*(?::[^=\n]+)?=(?![=>])\s*(.*)$")
JS_ASSIGN_AFTER = re.compile(r"^\s*(?:\|\||&&|\?\?)?=(?![=>])\s*(.*)$")
JS_ASSIGN_BEFORE = re.compile(JS_STMT + r"(?:[\w$]+\s*\.\s*)*$")  # NAME = or exports.NAME = at a statement start
JS_OTHER_ASSIGN_AFTER = re.compile(r"^\s*(?:(?:[-+*/%&|^]|\*\*|<<|>>>?)=|=>|\??:(?!:))")  # op=, x =>, property or annotation
JS_BINDER_BEFORE = re.compile(
    r"(?:\b(?:const|let|var|function|class|interface|type|enum|namespace|module|declare|import|as|abstract|static"
    r"|readonly|get|set|accessor)\s*\*?\s*|\bcatch\s*\(\s*|\bfor\s*(?:await\s*)?\(\s*|\b(?:const|let|var)\s*[\[{][^=;]*"
    r"|\bfunction\b[^(]*\([^)]*)$")
JS_METHOD_BEFORE = re.compile(
    r"^\s*(?:(?:static|async|get|set|public|private|protected|readonly|override)\s+)*\*?\s*"
    r"(?!(?:if|while|for|switch|with|return|typeof|await|new|delete|void|yield|throw|case|in|of|do|else|super|this)\b)"
    r"[\w$]+\s*(?:<[^>]*>)?\s*\([^)]*$")
JS_METHOD_AFTER = re.compile(r"^[^)]*\)\s*(?::[^{;=]*)?\{")
JS_PATTERN_AFTER = re.compile(r"^[^;=]*?[\]})]\s*(?:=(?![=>])|=>)")  # [a, NAME] = / {NAME} = / (a, NAME) =>
JS_STRING_KEY = re.compile(
    r"(?:\[\s*['\"`]$|\b(?:defineProperty|defineProperties|set|assign|__defineGetter__|__defineSetter__)\s*\([^)]*['\"`]$)")
JS_SPECIFIERS = re.compile(r"\b(import|export)\s+(?:type\s+)?(?:[\w$]+\s*,\s*)?\{([^{}]*)\}"
                           r"(?:\s*from\s*(['\"])([^'\"\n]*)\3)?", re.S)
JS_SPECIFIER = re.compile(r"(?:type\s+)?([\w$]+)(?:\s+as\s+([\w$]+))?")

C_DEFINE_BEFORE = re.compile(r"^\s*(?:/\*.*?\*/\s*)*#\s*define\s+$")
C_OTHER_BEFORE = re.compile(r"#\s*(?:define|undef)\s+$")
C_ASSIGN_AFTER = re.compile(r"^\s*(?:\[[^\]]*\]\s*)?=(?!=)")


def occurrences(text, name, ident):
    """Each whole-word occurrence of name: (line number, text before it on its line, text after it on its line,
    start offset)."""
    for m in re.finditer(rf"(?<!{ident}){name}(?!{ident})", text):
        ls = text.rfind("\n", 0, m.start()) + 1
        le = text.find("\n", m.end())
        le = len(text) if le < 0 else le
        yield text.count("\n", 0, m.start()) + 1, text[ls:m.start()], text[m.end():le], m.start()


def declared(at, line, rhs):
    """A literal declaration's value, or (None, why) when its value is not a quoted MAJOR.MINOR literal."""
    v = literal(rhs)
    return (at, v, None) if v else (at, None, f"line {line}: not a quoted MAJOR.MINOR literal: {rhs.strip()!r}")


def unreadable(at, line, what, before, after):
    return at, None, f"line {line}: {what}, so its value cannot be read: {(before + NAME + after).strip()!r}"


def ruby_scan(at, text):
    """Ruby: every statement (a line split at ;) that names the constant. NAME = / ||= / &&= with a literal at the
    start of a statement (optionally Module::-qualified) is a declaration. A multiple assignment, an op-assignment,
    class/module NAME, for NAME, rescue => NAME, a trailing-comma line and const_set cannot be read. Comments are
    not parsed out: a commented-out declaration still counts."""
    out = []
    for line, before, after, _ in occurrences(text, NAME, r"[\w]"):
        before = before[before.rfind(";") + 1:]
        after = after.split(";", 1)[0]
        if before.endswith("#{") and after.startswith("}"):
            continue
        if RUBY_DECL_BEFORE.match(before) and (m := RUBY_DECL_AFTER.match(after)):
            out.append(declared(at, line, m.group(1)))
        elif RUBY_ASSIGN_OP.search(after):
            out.append(unreadable(at, line, "a multiple or operator assignment", before, after))
        elif RUBY_BINDER_BEFORE.search(before):
            out.append(unreadable(at, line, "a class, module, for or rescue binding", before, after))
        elif re.fullmatch(r"\s*,\s*", after):
            out.append(unreadable(at, line, "a multiple assignment across lines", before, after))
    for m in RUBY_CONST_SET.finditer(text):
        line = text.count("\n", 0, m.start()) + 1
        out.append((at, None, f"line {line}: const_set, so its value cannot be read"))
    return out


def js_specifier_spans(at, text):
    """The import/export { ... } lists that name the constant: (spans to skip, findings). A plain import from a
    relative module, an import or export of the name under another name, and export { NAME } are reads; an alias
    to the name, an import or re-export of it from a package, and a list entry that does not parse cannot be read."""
    spans, out = [], []
    for m in JS_SPECIFIERS.finditer(text):
        body = m.group(2)
        if not re.search(rf"(?<!{JS_ID}){NAME}(?!{JS_ID})", body):
            continue
        spans.append(m.span(2))
        line = text.count("\n", 0, m.start()) + 1
        source = m.group(4)
        relative = source is not None and source.startswith(("./", "../"))
        for item in body.split(","):
            if not re.search(rf"(?<!{JS_ID}){NAME}(?!{JS_ID})", item):
                continue
            item = re.sub(r"//[^\n]*|/\*.*?\*/", " ", item, flags=re.S).strip()
            s = JS_SPECIFIER.fullmatch(item)
            bound = s and (s.group(2) or s.group(1))
            if not s or (bound == NAME and s.group(1) != NAME):
                out.append((at, None, f"line {line}: {m.group(1)} {{ {item} }} renames another binding to {NAME}, "
                                      "so its value cannot be read"))
            elif bound == NAME and (source is not None or m.group(1) == "import") and not relative:
                out.append((at, None, f"line {line}: {m.group(1)} {{ {item} }} from {source!r}, a module outside the "
                                      "SDK, so its value cannot be read"))
    return spans, out


def js_scan(at, text):
    """TypeScript/JavaScript: every occurrence of the name, read by the text around it on its line. A const/let/var
    declaration of the name, or an assignment to it (or to x.NAME, such as exports.NAME) at the start of a
    statement, with a literal, is a declaration. Any other binding cannot be read (see the module docstring).
    Comments are not parsed out: a commented-out declaration still counts."""
    spans, out = js_specifier_spans(at, text)
    for line, before, after, pos in occurrences(text, NAME, JS_ID):
        if any(a <= pos < b for a, b in spans):
            continue
        if before.endswith(("'", '"', "`")):
            if JS_STRING_KEY.search(before) or re.match(r"""^['"`]\s*(?::|\]\s*(?:[-+*/%&|^?]{0,3})=(?![=>]))""", after):
                out.append(unreadable(at, line, "a string-keyed write", before, after))
            continue
        if re.search(r"\$\{\s*$", before) and re.match(r"^\s*\}", after):
            continue
        if JS_DECL_BEFORE.search(before):
            m = JS_DECL_AFTER.match(after)
            out.append(declared(at, line, m.group(1)) if m else
                       unreadable(at, line, "a declaration with no literal value", before, after))
        elif m := JS_ASSIGN_AFTER.match(after):
            out.append(declared(at, line, m.group(1)) if JS_ASSIGN_BEFORE.search(before) else
                       unreadable(at, line, "an assignment that is not at the start of a statement", before, after))
        elif JS_OTHER_ASSIGN_AFTER.match(after):
            out.append(unreadable(at, line, "an operator assignment, parameter, property or annotation", before, after))
        elif JS_BINDER_BEFORE.search(before) or (JS_METHOD_BEFORE.search(before) and JS_METHOD_AFTER.match(after)):
            out.append(unreadable(at, line, "a declaration, import, parameter or member", before, after))
        elif JS_PATTERN_AFTER.match(after):
            out.append(unreadable(at, line, "a destructuring pattern or parameter list", before, after))
        elif not before.strip() and re.match(r"^\s*(?:,|$)", after):
            out.append(unreadable(at, line, "a list entry across lines", before, after))
    return out


def c_scan(at, text):
    """C: #define OTC_FORMAT_VERSION with a literal (#  define and a leading /* comment */ allowed) is a declaration.
    #undef, a #define that does not start its line (a commented-out one) and a variable of that name cannot be
    read."""
    out = []
    for line, before, after, _ in occurrences(text, "OTC_FORMAT_VERSION", r"\w"):
        if C_DEFINE_BEFORE.match(before):
            out.append(declared(at, line, after))
        elif C_OTHER_BEFORE.search(before) or C_ASSIGN_AFTER.match(after):
            out.append((at, None, f"line {line}: an #undef, a commented-out #define or a variable, so its value cannot "
                                  f"be read: {(before + 'OTC_FORMAT_VERSION' + after).strip()!r}"))
    return out


def scan_files(globs, scan):
    out = []
    for p in files(globs):
        try:
            out += scan(rel(p), read(p))
        except Unreadable as e:
            out.append((rel(p), None, str(e)))
    return out


def ruby_declarations():
    return scan_files(["ruby/lib/**/*.rb"], ruby_scan)


def ts_declarations():
    return scan_files([f"js/src/**/*.{e}" for e in ("ts", "mts", "cts", "tsx", "js", "mjs", "cjs")], js_scan)


def c_declarations():
    return scan_files(["c/include/**/*.h", "c/src/**/*.h", "c/src/**/*.c"], c_scan)


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
