"""Astronomical tables and the UTC time rules of prediction sections 4.1–4.3."""
from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any

from .._errors import InvalidArgumentError, UnsupportedConstituentError, TimeOutOfRangeError
from .._models import freeze

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def instant(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise InvalidArgumentError('an instant must be a timezone-aware datetime')
    delta = value.astimezone(timezone.utc) - EPOCH
    return delta.days * 86400 + delta.seconds


def utc(seconds):
    return EPOCH + timedelta(seconds=seconds)


def year_start(year):
    return instant(datetime(year, 1, 1, tzinfo=timezone.utc))


def angle(value):
    reduced = value - 360.0 * math.floor(value / 360.0)
    return 0.0 if reduced == 360.0 else reduced


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def integer(value):
    return number(value) and value == math.floor(value)


@dataclass(frozen=True, slots=True)
class AstroTable:
    _raw: Any = field(repr=False)
    _first: int = field(init=False)
    _last: int = field(init=False)

    def __post_init__(self):
        raw = self._raw
        ident = raw.get('astro_table_id', '')
        def bad(detail):
            raise InvalidArgumentError(f'astro table "{ident}" {detail}')
        first, last = raw.get('first_year'), raw.get('last_year')
        if not integer(first) or not integer(last) or first > last:
            bad('first_year and last_year must be ordered integers')
        first, last = int(first), int(last)
        rows = raw.get('constituents')
        if not isinstance(rows, Mapping):
            bad('constituents must be an object')
        for name, row in rows.items():
            if not isinstance(row, Mapping):
                bad(f'row "{name}": must be an object')
            for key in ('v0u_deg', 'f'):
                values = row.get(key)
                if not isinstance(values, (list, tuple)) or len(values) != last - first + 1 or not all(number(v) for v in values):
                    bad(f'row "{name}": {key} must contain {last - first + 1} numbers')
            speed = row.get('speed_deg_per_hour')
            if speed is not None and (not number(speed) or speed < 0):
                bad(f'row "{name}": speed_deg_per_hour {speed!r} must be a nonnegative number')
        object.__setattr__(self, '_first', first)
        object.__setattr__(self, '_last', last)
        object.__setattr__(self, '_raw', freeze(raw))

    @property
    def valid_range(self):
        return self._first, self._last

    def _index(self, year):
        if not integer(year):
            raise InvalidArgumentError('year must be an integer')
        if not self._first <= year <= self._last:
            raise TimeOutOfRangeError(f'year {year} is outside the astro table', first_year=self._first, last_year=self._last)
        return int(year) - self._first

    def _row(self, name):
        row = self._raw['constituents'].get(name) if isinstance(name, str) else None
        if row is None or row.get('speed_deg_per_hour') is None:
            raise UnsupportedConstituentError(f'unsupported constituent {name}', constituent=name)
        return row

    def equilibrium_argument(self, name, at):
        seconds = instant(at)
        row = self._row(name)
        year = utc(seconds).year
        i = self._index(year)
        return angle(row['v0u_deg'][i] + row['speed_deg_per_hour'] * ((seconds - year_start(year)) / 3600.0))

    def node_factor(self, name, at):
        seconds = instant(at)
        row = self._row(name)
        return row['f'][self._index(utc(seconds).year)]

    def equilibrium_for_year(self, name, year):
        return self._row(name)['v0u_deg'][self._index(year)]

    def node_factor_for_year(self, name, year):
        return self._row(name)['f'][self._index(year)]
