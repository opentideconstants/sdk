# /// script
# requires-python = ">=3.10"
# ///
"""Check conformance/name_fold.json against the name normalisation rules (SDK spec §4.4.1).

Run: uv run conformance/tools/test_name_fold.py

It folds names with steps 1 and 2 of §4.4.1, using only the table (never the
runtime's own Unicode functions), and compares them with the expected results.
The cases cover each letter that gen_fold_table.py maps by hand (EXTRA, CR D12)
and the White_Space step (U+00A0, U+0085), which the `fold` fixture root relies on.
Exit status 0 = every check passes; 1 = a case fails; 2 = the table is missing or
not a fold table.
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
    # the letters that do not decompose (gen_fold_table.py EXTRA, CR D12), upper and lower case
    ("Ħal Għargħur", "hal gharghur"),
    ("ŦANA ŧana", "tana tana"),
    ("ŊAMA ŋama", "nama nama"),
    ("ĸangerlussuaq", "kangerlussuaq"),
    ("Diyarbakır", "diyarbakir"),
    ("Viðey Ðalur", "videy dalur"),
    ("ΠΌΡΟΣ Πόρος", "\u03c0\u03bf\u03c1\u03bf\u03c3 \u03c0\u03bf\u03c1\u03bf\u03c3"),  # final sigma folds to sigma
    ("Paral·lel", "parallel"),  # U+00B7 middle dot is removed
    # White_Space other than the ASCII spaces folds to U+0020
    ("Saint\u00a0Malo", "saint malo"),
    ("North\u0085Cape", "north cape"),
]


class BadTable(Exception):
    """The table is missing or is not a fold table."""


def load_table():
    try:
        doc = json.loads(TABLE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise BadTable(f"cannot read the table {TABLE}: {e}") from None
    m = doc.get("map") if isinstance(doc, dict) else None
    if not isinstance(m, dict) or not all(isinstance(v, str) for v in m.values()):
        raise BadTable(f"{TABLE} has no \"map\" object of strings")
    try:
        return {int(k, 16): v for k, v in m.items()}
    except ValueError as e:
        raise BadTable(f"{TABLE} has a key that is not a hex code point: {e}") from None


def fold(name, table):
    folded = "".join(table.get(ord(ch), ch) for ch in name)
    return re.sub(r"[ \t\n\r\f\v]+", " ", folded).strip(" ")


def main():
    try:
        table = load_table()
    except BadTable as e:
        print(e, file=sys.stderr)
        return 2
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
