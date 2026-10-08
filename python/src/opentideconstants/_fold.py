"""Name normalisation with the shared fold table (spec §4.4.1). The table is
conformance/name_fold.json, copied into the package at build time."""
from __future__ import annotations

import json
import re
from importlib import resources

_WS = re.compile(r"[ \t\n\r\f\v]+")


def _load():
    doc = json.loads(resources.files(__package__).joinpath("name_fold.json").read_text(encoding="utf-8"))
    return {int(k, 16): v for k, v in doc["map"].items()}


_MAP = _load()


def fold(name: str) -> str:
    """Fold each code point through the table, then trim and collapse whitespace."""
    folded = "".join(_MAP.get(ord(ch), ch) for ch in name)
    return _WS.sub(" ", folded).strip(" ")
