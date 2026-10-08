# /// script
# requires-python = ">=3.10"
# ///
"""Check the C public header against the API manifest (conformance/api.json).

    uv run c/tools/check_manifest.py      exit 0 when every C name the manifest implies is declared

Rules (api.json "naming.c"): an operation's c names its function(s); a field of
an object with C type T is the accessor T_<field> (a list field may be
T_<singular>_count/_at, an object-valued field T_<field>_json), or a struct
member when c_struct is true; enum values are OTC_<ENUM>_<VALUE> plus
OTC_<ENUM>_OTHER; error codes map to otc_status values. A C type T may be
declared as T or T_t (otc_station is both a type and a function in the spec;
C cannot have both, so the type is otc_station_t).

This checks presence only. C has helpers the manifest does not list
(otc_*_init, otc_*_free, otc_status_code, *_UNSET enum values), so extra names
are not an error here.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def strip_comments(text):
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    return re.sub(r"//[^\n]*", " ", text)


def main():
    api = json.loads((ROOT / "conformance/api.json").read_text())
    header = strip_comments((ROOT / "c/include/opentideconstants.h").read_text())
    idents = set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", header))
    structs = {}
    for m in re.finditer(r"typedef struct (\w+) \{(.*?)\}\s*(\w+);", header, re.S):
        structs[m.group(3)] = set(re.findall(r"\b(\w+)\s*(?:\[[^\]]*\])?\s*;", m.group(2)))
    missing = []

    def need(name, *alts, where=""):
        if not any(n in idents for n in (name,) + alts):
            missing.append(f"{name}  ({where})")

    def base(t):
        return t[:-2] if t.endswith("_t") else t

    for oname, obj in api["objects"].items():
        ctype = obj.get("c")
        if ctype:
            need(ctype, ctype + "_t", where=f"type of {oname}")
        for m in obj.get("members", []):
            c = m.get("c")
            where = f"{oname}.{m['name']}"
            if c and "{object}" in c:
                if ctype:
                    need(base(ctype) + "_raw_json", where=where)
                continue
            if c and "(" not in c:
                for fn in c.split("/"):
                    need(fn, where=where)
                continue
            if c and c.startswith("(C: "):  # a struct member named in the note
                member = c[4:-1].split(".")[-1]
                if member not in structs.get(ctype, set()):
                    missing.append(f"{ctype}.{member}  ({where})")
                continue
            if c or not ctype or m.get("kind") not in ("field", "predicate"):
                continue
            if obj.get("c_struct"):
                if m["name"] not in structs.get(ctype, set()):
                    missing.append(f"{ctype}.{m['name']}  ({where})")
                continue
            acc = f"{base(ctype)}_{m['name']}"
            singular = acc[:-1] if acc.endswith("s") else acc
            need(acc, acc + "_json", acc + "_count", singular + "_count", where=where)
    for ename, values in api["enums"].items():
        prefix = "OTC_" + re.sub(r"[^A-Za-z0-9]+", "_", ename).upper()
        for v in values + ["other"]:
            need(prefix + "_" + re.sub(r"[^A-Za-z0-9]+", "_", v).upper(), where=f"enum {ename}")
    for e in api["errors"]:
        if e.get("c"):
            need(e["c"], where=f"error {e['code']}")
    for cname in ["SUPPORTED_FORMAT_MAJORS"]:
        need(api["constants"][cname]["c"], where=f"constant {cname}")
    for cname in api["constants"].get("c_only", []):
        need(cname, where="constant (C only)")
    for opt in api["client_options"].get("c_only", []):
        if opt["name"] not in structs.get("otc_open_options", set()):
            missing.append(f"otc_open_options.{opt['name']}  (client option, C only)")
    if missing:
        print(f"C header is missing {len(missing)} manifest name(s):")
        for m in missing:
            print("  " + m)
        return 1
    print("C header declares every name the API manifest implies")
    return 0


if __name__ == "__main__":
    sys.exit(main())
