# /// script
# requires-python = ">=3.10"
# ///
"""Check conformance/name_fold.json against the name normalisation rules (SDK spec §4.4.1).

Run: uv run conformance/tools/test_name_fold.py

It folds names with steps 1 and 2 of §4.4.1, using only the table (never the
runtime's own Unicode functions), and compares them with the expected results.
Exit status 0 = every check passes.
"""
import json
import re
import sys
from pathlib import Path

TABLE = Path(__file__).resolve().parent.parent / "name_fold.json"

# (input, expected folded name)
CASES = [
    ("Tromsø", "tromso"),
    ("Ålesund", "alesund"),
    ("Łeba", "leba"),
    ("Straße", "strasse"),
    ("  San   Francisco ", "san francisco"),
    ("Æbeltoft", "aebeltoft"),
    ("Œuf", "oeuf"),
    ("Đakovo", "dakovo"),
    ("Þórshöfn", "thorshofn"),
    ("Reykjavík", "reykjavik"),
    ("İzmir", "izmir"),
    ("Søndre Havn", "sondre havn"),
    ("Αθήναι", "αθηναι"),
    ("Мурманск", "мурманск"),
    ("Città-di-Castello", "citta-di-castello"),
    ("東京", "東京"),
]


def load_table():
    if not TABLE.exists():
        print(f"no table at {TABLE}; folding with an empty table")
        return {}
    doc = json.loads(TABLE.read_text(encoding="utf-8"))
    return {int(k, 16): v for k, v in doc["map"].items()}


def fold(name, table):
    folded = "".join(table.get(ord(ch), ch) for ch in name)
    return re.sub(r"[ \t\n\r\f\v]+", " ", folded).strip(" ")


def main():
    table = load_table()
    failures = 0
    for raw, expected in CASES:
        got = fold(raw, table)
        ok = got == expected
        failures += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {raw!r:28} -> {got!r:24} expected {expected!r}")
    print(f"{len(CASES) - failures}/{len(CASES)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
