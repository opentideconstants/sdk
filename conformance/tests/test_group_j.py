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
