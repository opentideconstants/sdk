"""Ordered double-precision sums and the specified adaptive event search."""
from __future__ import annotations

import math
from ._astro import angle, utc, year_start

RAD = math.pi / 180.0
EPSILON = 2.0 ** -52


class Sum:
    def __init__(self, table, constituents, *, amplitude='amplitude_m', phase='phase_deg', mean=0.0, multiplier=1.0, shift_hours=0.0):
        self.table = table
        self.mean = mean
        self.terms = []
        self._years = {}
        for constituent in constituents:
            row = table._row(constituent['name'])
            speed = row['speed_deg_per_hour']
            self.terms.append((row, speed, multiplier * constituent.get(amplitude, 0.0), angle(constituent.get(phase, 0.0) + speed * shift_hours)))

    def _year(self, year):
        data = self._years.get(year)
        if data is None:
            index = self.table._index(year)
            origin = year_start(year)
            terms = [(speed, row['f'][index] * amplitude, row['v0u_deg'][index] - phase, speed * RAD) for row, speed, amplitude, phase in self.terms]
            data = origin, terms
            self._years[year] = data
        return data

    def value(self, seconds, year=None, derivative=False):
        origin, terms = self._year(utc(seconds).year if year is None else year)
        delta = (seconds - origin) / 3600.0
        value = 0.0
        for speed, amplitude, argument, omega in terms:
            phase = angle(speed * delta + argument) * RAD
            value += -amplitude * omega * math.sin(phase) if derivative else amplitude * math.cos(phase)
        return value if derivative else value + self.mean

    def bound(self, year, derivative):
        return sum(abs(amplitude) * omega ** (2 if derivative else 1) for _, amplitude, _, omega in self._year(year)[1])

    def error(self, year, a, b, derivative):
        origin, terms = self._year(year)
        delta_max = max(abs(a - origin), abs(b - origin)) / 3600.0
        return 4.0 * EPSILON * sum(abs(amplitude) * (omega if derivative else 1.0) * (abs(omega * delta_max) + 2.0 * math.pi) for _, amplitude, _, omega in terms)


def _survivor(cluster, slack):
    if len(cluster) % 2 == 0:
        return None
    if slack:
        return cluster[2 * ((len(cluster) - 1) // 4)]
    wanted = cluster[0][1]
    candidates = [c for c in cluster if c[1] == wanted]
    return max(candidates, key=lambda c: (c[2], -c[0])) if wanted == 'high' else min(candidates, key=lambda c: (c[2], c[0]))


def events(total, start, stop, *, slack=False):
    """Unrounded roots, alternating signs and values over the half-open reporting window."""
    if start == stop:
        return []
    first = math.floor(start / 360.0) * 360 - 3600
    last = math.ceil((stop + 3600 - first) / 360.0) * 360 + first
    # Check every grid point, including the last point's new year.
    for point in range(first, last + 1, 360):
        total.table._index(utc(point).year)
    derivative = not slack
    roots = []
    for left in range(first, last, 360):
        year = utc(left).year
        bound = total.bound(year, derivative)
        def value(t):
            return total.value(t, year, derivative)
        def subdivide(a, b, fa, fb, depth):
            margin = bound * ((b - a) / 3600.0) * (1.0 + 1e-9) + 2.0 * total.error(year, a, b, derivative) + 1e-12 * max(1.0, bound)
            if abs(fa) + abs(fb) > margin:
                return
            if depth < 9:
                middle = (a + b) / 2.0
                fm = value(middle)
                subdivide(a, middle, fa, fm, depth + 1)
                subdivide(middle, b, fm, fb, depth + 1)
                return
            falling = fa > 0 and fb <= 0
            rising = fa < 0 and fb >= 0
            if not (falling or rising):
                return
            while b - a > 0.01:
                middle = (a + b) / 2.0
                fm = value(middle)
                if (falling and fm > 0) or (rising and fm < 0):
                    a = middle
                else:
                    b = middle
            root = (a + b) / 2.0
            kind = ('slack_before_ebb' if falling else 'slack_before_flood') if slack else ('high' if falling else 'low')
            roots.append((root, kind, 0.0 if slack else total.value(root, year)))
        subdivide(left, left + 360, value(left), value(left + 360), 0)
    # Reconcile each table jump before close-root filtering.
    for new_year in range(utc(first).year + 1, utc(last).year + 1):
        boundary = year_start(new_year)
        if not first < boundary < last:
            continue
        old = total.value(boundary, new_year - 1, derivative)
        new = total.value(boundary, new_year, derivative)
        if old == 0 or new == 0 or (old > 0) == (new > 0):
            continue
        lefts = [c for c in roots if c[0] <= boundary]
        rights = [c for c in roots if c[0] > boundary]
        left = lefts[-1] if lefts else None
        right = rights[0] if rights else None
        if left is not None and right is not None and right[0] - left[0] < 3600:
            if slack:
                loser = right
            else:
                winner = _survivor([left, right, left], False)
                loser = right if winner == left else left
            roots.remove(loser)
        else:
            kind = ('slack_before_flood' if new > 0 else 'slack_before_ebb') if slack else ('high' if old > 0 else 'low')
            roots.append((boundary, kind, 0.0 if slack else total.value(boundary, new_year)))
        roots.sort(key=lambda c: c[0])
    kept = []
    cluster = []
    for candidate in roots:
        if cluster and candidate[0] - cluster[-1][0] >= 1.0:
            survivor = _survivor(cluster, slack)
            if survivor is not None:
                kept.append(survivor)
            cluster = []
        cluster.append(candidate)
    if cluster:
        survivor = _survivor(cluster, slack)
        if survivor is not None:
            kept.append(survivor)
    return [c for c in kept if start <= math.floor(c[0] + 0.5) < stop]
