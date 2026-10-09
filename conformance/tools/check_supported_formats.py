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
  - version is not the package version (pyproject / version.rb / package.json / OTC_VERSION);
  - supported_format_version is not the SDK's declared SUPPORTED_FORMAT_VERSION (C: OTC_FORMAT_VERSION).

An SDK that does not declare SUPPORTED_FORMAT_VERSION yet predates format 1.0: it reads only the format 0.x
drafts (0.5 at most) and does not read release.min_reader_version. For such an SDK the only accepted value is
0.5; the SDK work for format 1.0 declares SUPPORTED_FORMAT_VERSION and moves the file to 1.0 with it.
The declaration is read from the source with a regular expression, so the check needs no toolchain.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VERSION_RE = r"[0-9]+\.[0-9]+"
PRE_10 = "0.5"  # the newest format an SDK with no SUPPORTED_FORMAT_VERSION reads (a 0.x draft)
KEYS = {"language", "version", "supported_format_version"}

# language: (package version: file, regex), (declared supported format version: glob, regex)
LANGUAGES = {
    "python": (("python/src/opentideconstants/_client.py", r'^__version__\s*=\s*"([^"]+)"'),
               ("python/src/opentideconstants/**/*.py", rf'^\s*SUPPORTED_FORMAT_VERSION\s*(?::[^=]+)?=\s*"({VERSION_RE})"')),
    "ruby": (("ruby/lib/opentideconstants/version.rb", r'^\s*VERSION\s*=\s*"([^"]+)"'),
             ("ruby/lib/**/*.rb", rf'^\s*SUPPORTED_FORMAT_VERSION\s*=\s*"({VERSION_RE})"')),
    "js": (("js/package.json", r'^\s*"version"\s*:\s*"([^"]+)"'),
           ("js/src/**/*.ts", rf'^\s*export\s+const\s+SUPPORTED_FORMAT_VERSION\b[^=]*=\s*"({VERSION_RE})"')),
    "c": (("c/include/opentideconstants.h", r'^#define\s+OTC_VERSION\s+"([^"]+)"'),
          ("c/include/*.h", rf'^#define\s+OTC_FORMAT_VERSION\s+"({VERSION_RE})"')),
}


def find_all(pattern_glob, regex):
    hits = []
    for p in sorted(ROOT.glob(pattern_glob)):
        for m in re.finditer(regex, p.read_text(encoding="utf-8"), re.M):
            hits.append((p.relative_to(ROOT).as_posix(), m.group(1)))
    return hits


def check_language(lang):
    (vfile, vre), (dglob, dre) = LANGUAGES[lang]
    path = ROOT / lang / "supported-formats.json"
    if not path.exists():
        return [f"{lang}: {path.relative_to(ROOT)} is missing"], None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as e:
        return [f"{lang}: {path.relative_to(ROOT)} is not JSON: {e}"], None
    if not isinstance(doc, dict) or set(doc) != KEYS:
        return [f"{lang}: {path.relative_to(ROOT)} must be an object with exactly the keys {sorted(KEYS)}"], None
    errs = []
    if doc["language"] != lang:
        errs.append(f"{lang}: language is {doc['language']!r}, not {lang!r} (the tag prefix {lang}-v)")
    versions = find_all(vfile, vre)
    if len(versions) != 1:
        errs.append(f"{lang}: expected one package version in {vfile}, found {len(versions)}")
    elif doc["version"] != versions[0][1]:
        errs.append(f"{lang}: version is {doc['version']!r}, but {vfile} says {versions[0][1]!r}")
    sfv = doc["supported_format_version"]
    if not isinstance(sfv, str) or not re.fullmatch(VERSION_RE, sfv):
        errs.append(f"{lang}: supported_format_version {sfv!r} is not MAJOR.MINOR")
    declared = find_all(dglob, dre)
    values = sorted({v for _, v in declared})
    if len(values) > 1:
        errs.append(f"{lang}: SUPPORTED_FORMAT_VERSION is declared with different values: {declared}")
        return errs, None
    if values:
        if sfv != values[0]:
            errs.append(f"{lang}: supported_format_version is {sfv!r}, but the SDK declares {values[0]!r} ({declared[0][0]})")
        note = f"declared {values[0]} in {declared[0][0]}"
    else:
        if sfv != PRE_10:
            errs.append(f"{lang}: the SDK declares no SUPPORTED_FORMAT_VERSION (it predates format 1.0 and reads "
                        f"{PRE_10} at most), but supported_format_version is {sfv!r}")
        note = f"no SUPPORTED_FORMAT_VERSION declared: an SDK before format 1.0, so {PRE_10}"
    return errs, note


def main():
    problems = []
    for lang in LANGUAGES:
        errs, note = check_language(lang)
        print(f"{'FAIL' if errs else 'PASS'}  {lang:7} {note or ''}")
        problems += errs
    for p in problems:
        print("  " + p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
