"""Encoding for SDK-generated cache JSON (canonical behavior B28)."""
from __future__ import annotations

import math


def _number(value: float) -> str:
    if not math.isfinite(value):
        raise ValueError("nonfinite cache JSON number")
    if value == 0:
        return "0"
    absolute = abs(value)
    # Python repr selects the closest shortest binary64 roundtrip, with even ties.
    mantissa, _, exponent = repr(absolute).partition("e")
    whole, _, fraction = mantissa.partition(".")
    digits = (whole + fraction).lstrip("0")
    scale = int(exponent or "0") - len(fraction)
    trimmed = digits.rstrip("0")
    scale += len(digits) - len(trimmed)
    digits = trimmed
    point = len(digits) + scale
    if 1e-6 <= absolute < 1e21:
        if point <= 0:
            text = "0." + "0" * -point + digits
        elif point >= len(digits):
            text = digits + "0" * (point - len(digits))
        else:
            text = digits[:point] + "." + digits[point:]
    else:
        text = digits[0] + ("." + digits[1:] if len(digits) > 1 else "") + "e" + str(point - 1)
    return "-" + text if value < 0 else text


def _encode(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _number(value)
    if isinstance(value, str):
        escaped = []
        for character in value:
            scalar = ord(character)
            if 0xd800 <= scalar <= 0xdfff:
                raise ValueError("unpaired surrogate in cache JSON string")
            if scalar < 32:
                escaped.append(f"\\u{scalar:04x}")
            elif character in ('"', "\\"):
                escaped.append("\\" + character)
            else:
                escaped.append(character)
        return '"' + "".join(escaped) + '"'
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("cache JSON object keys must be strings")
        return "{" + ",".join(_encode(key) + ":" + _encode(value[key]) for key in sorted(value)) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_encode(item) for item in value) + "]"
    raise TypeError(f"unsupported cache JSON value: {type(value).__name__}")


def encode_cache_json(cache_document) -> bytes:
    """Return canonical UTF-8 bytes without changing the supplied document."""
    return _encode(cache_document).encode("utf-8")
