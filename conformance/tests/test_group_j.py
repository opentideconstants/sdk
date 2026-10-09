"""Group J: tools/check_supported_formats.py fails closed (review round 2, package PK-R2-17).

Each test copies the real SDK sources into a temporary tree, changes one thing, copies the checker into the tree's
conformance/tools/ (the checker finds its tree from its own path) and runs it. A test that plants a conflicting or
unreadable declaration must see exit 1 and a FAIL line for that language; every run must report all four languages
and print no traceback. CSF_CHECKER=<path> runs the tests against another copy of the checker (for a RED run).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from _util import CONF

REPO = CONF.parent
CHECKER = Path(os.environ.get("CSF_CHECKER") or CONF / "tools" / "check_supported_formats.py")
LANGS = ("python", "ruby", "js", "c")
COPY = ["python/src", "ruby/lib", "js/src", "c/include", "c/src", "js/package.json", "conformance/api.json"] + \
       [f"{lang}/supported-formats.json" for lang in LANGS]


@pytest.fixture(scope="session")
def base_tree(tmp_path_factory):
    base = tmp_path_factory.mktemp("csf-base")
    for rel in COPY:
        src, dst = REPO / rel, base / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
    return base


@pytest.fixture
def tree(base_tree, tmp_path):
    root = tmp_path / "t"
    shutil.copytree(base_tree, root)
    return root


def run(root):
    tool = root / "conformance" / "tools" / "check_supported_formats.py"
    tool.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CHECKER, tool)
    p = subprocess.run([sys.executable, str(tool)], capture_output=True, text=True, timeout=60)
    out = p.stdout + p.stderr
    assert "Traceback" not in out, out
    for lang in LANGS:  # every language is reported, even after another one fails
        assert any(line.split()[1:2] == [lang] for line in p.stdout.splitlines()
                   if line.startswith(("PASS", "FAIL"))), out
    return p.returncode, out


def status(out, lang):
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] in ("PASS", "FAIL") and parts[1] == lang:
            return parts[0]
    return None


def plant(root, rel, text):
    """Add a source file (or append to one) in the temporary tree."""
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8", newline="") as f:
        f.write("\n" + text + "\n")


def assert_fails(root, lang, *needles):
    rc, out = run(root)
    assert rc == 1, out
    assert status(out, lang) == "FAIL", out
    for n in needles:
        assert n in out, out
    for other in LANGS:
        if other != lang:
            assert status(out, other) == "PASS", out
    return out


def test_the_real_tree_passes(tree):
    rc, out = run(tree)
    assert rc == 0, out
    assert all(status(out, lang) == "PASS" for lang in LANGS), out


# --- R2-184 / R2-187: a missing or unreadable file is a FAIL line for its language, and the run goes on

def test_missing_ruby_version_file(tree):
    (tree / "ruby/lib/opentideconstants/version.rb").unlink()
    plant(tree, "ruby/lib/opentideconstants/zz_decl.rb", 'module Opentideconstants\n  SUPPORTED_FORMAT_VERSION = "1.0"\nend')
    assert_fails(tree, "ruby", "version.rb")


def test_missing_package_json(tree):
    (tree / "js/package.json").unlink()
    assert_fails(tree, "js", "js/package.json")


def test_package_json_that_is_not_json_names_the_parse_error(tree):
    p = tree / "js/package.json"
    p.write_text(p.read_text(encoding="utf-8").replace('"version"', '"version": "x",, "v2"', 1), encoding="utf-8")
    out = assert_fails(tree, "js", "js/package.json is not JSON")
    assert "found 0" not in out


def test_undecodable_python_file(tree):
    (tree / "python/src/opentideconstants/zz_bad.py").write_bytes(b"x = '\xff\xfe'\n")
    assert_fails(tree, "python", "zz_bad.py")


def test_nul_byte_in_a_python_file(tree):
    (tree / "python/src/opentideconstants/zz_nul.py").write_bytes(b"x = 1\x00\n")
    assert_fails(tree, "python", "zz_nul.py")


def test_undecodable_ruby_file(tree):
    (tree / "ruby/lib/opentideconstants/zz_bad.rb").write_bytes(b"X = '\xff'\n")
    assert_fails(tree, "ruby", "zz_bad.rb")


def test_undecodable_typescript_file(tree):
    (tree / "js/src/zz_bad.ts").write_bytes(b"const x = '\xff';\n")
    assert_fails(tree, "js", "zz_bad.ts")


def test_undecodable_c_file(tree):
    (tree / "c/src/zz_bad.c").write_bytes(b"static const char *x = \"\xff\";\n")
    assert_fails(tree, "c", "zz_bad.c")


def test_supported_formats_json_that_is_a_directory(tree):
    p = tree / "ruby/supported-formats.json"
    p.unlink()
    p.mkdir()
    assert_fails(tree, "ruby", "supported-formats.json")


def test_c_version_define_with_spaces_after_the_hash(tree):
    h = tree / "c/include/opentideconstants.h"
    h.write_text(h.read_text(encoding="utf-8").replace("#define OTC_VERSION ", "#  define OTC_VERSION ", 1), encoding="utf-8")
    rc, out = run(tree)
    assert rc == 0, out


def test_c_version_define_with_a_different_version_and_spaces_after_the_hash(tree):
    h = tree / "c/include/opentideconstants.h"
    text = h.read_text(encoding="utf-8")
    assert '#define OTC_VERSION "0.1.0"' in text
    h.write_text(text.replace('#define OTC_VERSION "0.1.0"', '#  define OTC_VERSION "0.2.0"', 1), encoding="utf-8")
    assert_fails(tree, "c", "'0.2.0'")


# --- R2-182: every Python binding of the name counts; a binding whose value cannot be read fails

PY_UNREADABLE = {
    "import-from-alias": "from ._zz_other import OTHER as SUPPORTED_FORMAT_VERSION",
    "import-module-alias": "import os as SUPPORTED_FORMAT_VERSION",
    "import-from-outside-the-package": "from os import SUPPORTED_FORMAT_VERSION",
    "nested-tuple-target": 'a, (SUPPORTED_FORMAT_VERSION, b) = 1, ("2.0", 3)',
    "starred-target": 'a, *SUPPORTED_FORMAT_VERSION = 1, "2.0"',
    "list-target": '[SUPPORTED_FORMAT_VERSION] = ["2.0"]',
    "for-target": 'for SUPPORTED_FORMAT_VERSION in ["2.0"]:\n    pass',
    "with-target": 'import contextlib\nwith contextlib.nullcontext("2.0") as SUPPORTED_FORMAT_VERSION:\n    pass',
    "comprehension-target": 'x = [SUPPORTED_FORMAT_VERSION for SUPPORTED_FORMAT_VERSION in ["2.0"]]',
    "except-name": 'try:\n    pass\nexcept Exception as SUPPORTED_FORMAT_VERSION:\n    pass',
    "globals-subscript": 'globals()["SUPPORTED_FORMAT_VERSION"] = "2.0"',
    "globals-update-keyword": 'globals().update(SUPPORTED_FORMAT_VERSION="2.0")',
    "globals-update-dict": 'globals().update({"SUPPORTED_FORMAT_VERSION": "2.0"})',
    "setattr": 'import sys\nsetattr(sys.modules[__name__], "SUPPORTED_FORMAT_VERSION", "2.0")',
    "function-def": "def SUPPORTED_FORMAT_VERSION():\n    return '2.0'",
    "class-def": "class SUPPORTED_FORMAT_VERSION:\n    pass",
    "del": 'del SUPPORTED_FORMAT_VERSION',
    "match-capture": 'match "2.0":\n    case SUPPORTED_FORMAT_VERSION:\n        pass',
    "augmented": 'SUPPORTED_FORMAT_VERSION += ".1"',
}


@pytest.mark.parametrize("form", sorted(PY_UNREADABLE))
def test_python_binding_that_cannot_be_read_fails(tree, form):
    plant(tree, "python/src/opentideconstants/_zz.py", PY_UNREADABLE[form])
    assert_fails(tree, "python", "_zz.py")


@pytest.mark.parametrize("decl", [
    'SUPPORTED_FORMAT_VERSION = "2.0"',
    'A = SUPPORTED_FORMAT_VERSION = "2.0"',
    'SUPPORTED_FORMAT_VERSION: str = "2.0"',
    'import types\nns = types.SimpleNamespace()\nns.SUPPORTED_FORMAT_VERSION = "2.0"',
    'if (SUPPORTED_FORMAT_VERSION := "2.0"):\n    pass',
])
def test_python_literal_declaration_with_another_value_fails(tree, decl):
    plant(tree, "python/src/opentideconstants/_zz.py", decl)
    assert_fails(tree, "python", "different values", "'2.0'")


@pytest.mark.parametrize("src", [
    "from ._release import SUPPORTED_FORMAT_VERSION as SUPPORTED_FORMAT_VERSION",
    "from opentideconstants._release import SUPPORTED_FORMAT_VERSION",
    'A = SUPPORTED_FORMAT_VERSION = "1.0"',
    "SUPPORTED_FORMAT_VERSION: str",
    'import opentideconstants as m\nx = getattr(m, "SUPPORTED_FORMAT_VERSION")',
    '# SUPPORTED_FORMAT_VERSION = "2.0"\n"""SUPPORTED_FORMAT_VERSION = "2.0" in a docstring"""',
])
def test_python_forms_that_are_not_a_conflicting_declaration_pass(tree, src):
    plant(tree, "python/src/opentideconstants/_zz.py", src)
    rc, out = run(tree)
    assert rc == 0, out


# --- R2-183: TypeScript/JavaScript, Ruby and C declarations in any position count. A comment is not parsed out:
# a commented-out declaration still counts, and one whose value cannot be read fails (fail closed).

TS_UNREADABLE = {
    "multi-declarator": 'export const A = 1, SUPPORTED_FORMAT_VERSION = "2.0";',
    "declare-const": 'export declare const SUPPORTED_FORMAT_VERSION: "2.0";',
    "object-property": 'export const cfg = { SUPPORTED_FORMAT_VERSION: "2.0" };',
    "quoted-object-key": 'module.exports = { "SUPPORTED_FORMAT_VERSION": "2.0" };',
    "string-keyed-write": 'exports["SUPPORTED_FORMAT_VERSION"] = "2.0";',
    "define-property": 'Object.defineProperty(exports, "SUPPORTED_FORMAT_VERSION", { value: "2.0" });',
    "object-destructuring": 'const { SUPPORTED_FORMAT_VERSION } = globalThis as any;',
    "multi-line-destructuring": "const {\n  SUPPORTED_FORMAT_VERSION,\n} = globalThis as any;",
    "array-destructuring": 'const [SUPPORTED_FORMAT_VERSION] = ["2.0"];',
    "default-import": 'import SUPPORTED_FORMAT_VERSION from "./zz_other.js";',
    "namespace-import": 'import * as SUPPORTED_FORMAT_VERSION from "./zz_other.js";',
    "import-alias": 'import { OTHER as SUPPORTED_FORMAT_VERSION } from "./zz_other.js";',
    "export-alias": 'export { OTHER as SUPPORTED_FORMAT_VERSION } from "./zz_other.js";',
    "re-export-from-a-package": 'export { SUPPORTED_FORMAT_VERSION } from "some-package";',
    "function": "export function SUPPORTED_FORMAT_VERSION() { return \"2.0\"; }",
    "class-static-field": 'export class C { static SUPPORTED_FORMAT_VERSION = "2.0"; }',
    "for-of": 'for (const SUPPORTED_FORMAT_VERSION of ["2.0"]) { void 0; }',
    "arrow-parameter": 'export const f = ["2.0"].map(SUPPORTED_FORMAT_VERSION => SUPPORTED_FORMAT_VERSION);',
    "arrow-parameters": "export const g = (a: string, SUPPORTED_FORMAT_VERSION: string) => a;",
    "compound-assignment": 'SUPPORTED_FORMAT_VERSION += ".1";',
    "commented-out-declaration": '// export const SUPPORTED_FORMAT_VERSION = "2.0";',
}

TS_CONFLICT = {
    "cjs-exports": 'exports.SUPPORTED_FORMAT_VERSION = "2.0";',
    "cjs-module-exports": 'module.exports.SUPPORTED_FORMAT_VERSION = "2.0";',
    "after-an-inline-block-comment": '/* note */ export const SUPPORTED_FORMAT_VERSION = "2.0";',
    "after-a-block-comment-ends": '/*\n note\n */ export const SUPPORTED_FORMAT_VERSION = "2.0";',
    "inside-a-block-comment-not-starting-with-star": '/*\nexport const SUPPORTED_FORMAT_VERSION = "2.0";\n*/',
    "second-declarator-on-its-own-line": 'export const A = 1,\n  SUPPORTED_FORMAT_VERSION = "2.0";',
    "after-a-semicolon": 'void 0; export const SUPPORTED_FORMAT_VERSION = "2.0";',
}


@pytest.mark.parametrize("form", sorted(TS_UNREADABLE))
def test_typescript_binding_that_cannot_be_read_fails(tree, form):
    plant(tree, "js/src/zz.ts", TS_UNREADABLE[form])
    assert_fails(tree, "js", "zz.ts", "cannot read")


@pytest.mark.parametrize("ext", ["cjs", "mjs", "js"])
def test_javascript_files_are_scanned(tree, ext):
    plant(tree, f"js/src/zz.{ext}", TS_CONFLICT["cjs-exports"])
    assert_fails(tree, "js", "different values", "'2.0'")


@pytest.mark.parametrize("form", sorted(TS_CONFLICT))
def test_typescript_declaration_with_another_value_fails(tree, form):
    plant(tree, "js/src/zz.ts", TS_CONFLICT[form])
    assert_fails(tree, "js", "different values", "'2.0'")


@pytest.mark.parametrize("src", [
    'import { SUPPORTED_FORMAT_VERSION as V } from "./constants.js";\nexport const w = V;',
    'import {\n  SUPPORTED_FORMAT_VERSION, // the newest format\n  VERSION,\n} from "./constants.js";\nvoid VERSION;',
    'import { SUPPORTED_FORMAT_VERSION } from "./constants.js";\nexport { SUPPORTED_FORMAT_VERSION as SFV };',
    'import { SUPPORTED_FORMAT_VERSION } from "./constants.js";\n'
    'export const s = `format ${SUPPORTED_FORMAT_VERSION}`;\n'
    'export const t = (v: string) => v === SUPPORTED_FORMAT_VERSION;\n'
    'export const u = String(SUPPORTED_FORMAT_VERSION).length;\n'
    'export const o = { v: SUPPORTED_FORMAT_VERSION };\n'
    '/*\n newer than SUPPORTED_FORMAT_VERSION (spec 7.4).\n*/',
])
def test_typescript_forms_that_are_not_a_conflicting_declaration_pass(tree, src):
    plant(tree, "js/src/zz.ts", src)
    rc, out = run(tree)
    assert rc == 0, out


RB_UNREADABLE = {
    "multiple-assignment": 'module Opentideconstants\n  A, SUPPORTED_FORMAT_VERSION = "9", "2.0"\nend',
    "multiple-assignment-first": 'module Opentideconstants\n  SUPPORTED_FORMAT_VERSION, B = "2.0", 1\nend',
    "nested-multiple-assignment": 'module Opentideconstants\n  (A, SUPPORTED_FORMAT_VERSION), B = ["1", "2.0"], 3\nend',
    "multi-line-multiple-assignment": 'module Opentideconstants\n  SUPPORTED_FORMAT_VERSION,\n    B = "2.0", 1\nend',
    "const-set": 'Opentideconstants.const_set(:SUPPORTED_FORMAT_VERSION, "2.0")',
    "compound-assignment": 'module Opentideconstants\n  SUPPORTED_FORMAT_VERSION += ".1"\nend',
    "class": "module Opentideconstants\n  class SUPPORTED_FORMAT_VERSION; end\nend",
    "for-target": 'for SUPPORTED_FORMAT_VERSION in ["2.0"]; end',
    "rescue-target": "begin; rescue => SUPPORTED_FORMAT_VERSION; end",
    "commented-out-declaration": '# SUPPORTED_FORMAT_VERSION = "2.0"',
}

RB_CONFLICT = {
    "after-a-semicolon": 'module Opentideconstants; SUPPORTED_FORMAT_VERSION = "2.0"; end',
    "qualified": 'Opentideconstants::SUPPORTED_FORMAT_VERSION = "2.0"',
    "or-assign-after-a-semicolon": 'x = 1; SUPPORTED_FORMAT_VERSION ||= "2.0"',
}


@pytest.mark.parametrize("form", sorted(RB_UNREADABLE))
def test_ruby_binding_that_cannot_be_read_fails(tree, form):
    plant(tree, "ruby/lib/opentideconstants/zz.rb", RB_UNREADABLE[form])
    assert_fails(tree, "ruby", "zz.rb", "cannot read")


@pytest.mark.parametrize("form", sorted(RB_CONFLICT))
def test_ruby_declaration_with_another_value_fails(tree, form):
    plant(tree, "ruby/lib/opentideconstants/zz.rb", RB_CONFLICT[form])
    assert_fails(tree, "ruby", "different values", "'2.0'")


def test_ruby_forms_that_are_not_a_conflicting_declaration_pass(tree):
    plant(tree, "ruby/lib/opentideconstants/zz.rb", "\n".join([
        "module Opentideconstants",
        '  A = "reads format #{SUPPORTED_FORMAT_VERSION}"; B = version_key(SUPPORTED_FORMAT_VERSION) rescue nil',
        "  C = SUPPORTED_FORMAT_VERSION",
        "  D = { SUPPORTED_FORMAT_VERSION => 1 }",
        "  E = (A == SUPPORTED_FORMAT_VERSION) && (A <= SUPPORTED_FORMAT_VERSION)",
        "  # newer than SUPPORTED_FORMAT_VERSION (§7.4).",
        "end",
    ]))
    rc, out = run(tree)
    assert rc == 0, out


C_UNREADABLE = {
    "variable": 'static const char OTC_FORMAT_VERSION[] = "2.0";',
    "commented-out-define": '// #define OTC_FORMAT_VERSION "2.0"',
    "undef": "#undef OTC_FORMAT_VERSION",
}


@pytest.mark.parametrize("form", sorted(C_UNREADABLE))
def test_c_binding_that_cannot_be_read_fails(tree, form):
    plant(tree, "c/src/zz.c", C_UNREADABLE[form])
    assert_fails(tree, "c", "zz.c", "cannot read")


@pytest.mark.parametrize("decl", [
    '#  define OTC_FORMAT_VERSION "2.0"',
    '/* note */ #define OTC_FORMAT_VERSION "2.0"',
])
def test_c_define_with_another_value_fails(tree, decl):
    plant(tree, "c/src/zz.c", decl)
    assert_fails(tree, "c", "different values", "'2.0'")


def test_c_forms_that_are_not_a_conflicting_declaration_pass(tree):
    plant(tree, "c/src/zz.c", "\n".join([
        "#ifndef OTC_FORMAT_VERSION",
        "#error no OTC_FORMAT_VERSION",
        "#endif",
        "#if defined(OTC_FORMAT_VERSION)",
        "static int zz(const char *v) { return strcmp(v, OTC_FORMAT_VERSION) == 0; }",
        "#endif",
    ]))
    rc, out = run(tree)
    assert rc == 0, out
