"""Real reader prediction regressions against independently pinned expected output."""
import dataclasses
import datetime as dt
import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if not os.environ.get('OTC_TEST_INSTALLED'):
    sys.path.insert(0, str(ROOT / 'python' / 'src'))
import opentideconstants as otc

UTC = dt.timezone.utc
PREDICT = ROOT / 'conformance' / 'fixtures' / 'predict'


class PredictionTest(unittest.TestCase):
    def setUp(self):
        self.client = otc.OpenTideConstants(file=PREDICT / 'OTC_20991231.7.json')
        self.addCleanup(self.client.close)

    def test_native_height_and_repeat_order(self):
        times = [dt.datetime(2010, 3, 1, tzinfo=UTC)] * 2
        result = self.client.heights_at('OTC-P-0001', times)
        self.assertEqual([p.time for p in result.items], times)
        self.assertEqual(result.method, 'harmonic')
        self.assertEqual(result.datum_name, 'mean_level')
        self.assertAlmostEqual(result.items[0].height_m, result.items[1].height_m, places=12)
        self.assertEqual(result.set_id, 'OTC-P-0001/noaa')

    def test_native_extremes_independent_pin(self):
        expected = json.loads((ROOT / 'conformance/cases/predict-extremes.json').read_text())['cases'][0]['steps'][0]['expect']['prediction']
        result = self.client.extremes('OTC-P-0001', start=dt.datetime(2010, 3, 1, tzinfo=UTC), stop=dt.datetime(2010, 3, 4, tzinfo=UTC))
        self.assertEqual(len(result.items), len(expected['items']))
        for got, want in zip(result.items, expected['items']):
            self.assertEqual(got.time, dt.datetime.fromisoformat(want['time'].replace('Z', '+00:00')))
            self.assertEqual(got.type, want['type'])
            self.assertAlmostEqual(got.height_m, want['height_m'], places=8)

    def test_native_stream_current_same(self):
        kw = dict(start=dt.datetime(2010, 3, 1, tzinfo=UTC), stop=dt.datetime(2010, 3, 1, 1, tzinfo=UTC))
        eager = self.client.currents('OTC-P-0016', start=kw['start'], stop=kw['stop'])
        with otc.OpenTideConstants(file=PREDICT / 'OTC_20991231.7.jsonl', mode='stream') as stream:
            self.assertEqual(eager, stream.release.currents('OTC-P-0016', start=kw['start'], stop=kw['stop']))
        station = self.client.station('OTC-P-0016')
        assert station is not None
        self.assertEqual(eager.bin_number, station.raw['default_current_bin'])
        self.assertGreater(eager.items[0].speed_ms, 0)

    def test_native_aware_time_floor_and_naive_refusal(self):
        with self.assertRaises(otc.InvalidArgumentError):
            self.client.heights_at('OTC-P-0001', [dt.datetime(2010, 3, 1)])
        instant = dt.datetime(2010, 3, 1, microsecond=999999, tzinfo=UTC)
        result = self.client.heights_at('OTC-P-0001', [instant])
        self.assertEqual(result.items[0].time, instant.replace(microsecond=0))

    def test_native_empty_window_checks_without_year_refusal(self):
        t = dt.datetime(2200, 1, 1, tzinfo=UTC)
        self.assertEqual(self.client.extremes('OTC-P-0001', start=t, stop=t).items, ())
        with self.assertRaises(otc.InvalidArgumentError):
            self.client.heights('OTC-P-0001', start=t, stop=t, step_s=True)

    def test_native_astro_missing_row_and_range(self):
        table = self.client.release.astro_table()
        assert table is not None
        self.assertEqual(table.valid_range, (2000, 2030))
        with self.assertRaises(otc.UnsupportedConstituentError) as missing:
            table.equilibrium_for_year('UNDEFINED', 2010)
        self.assertEqual(missing.exception.constituent, 'UNDEFINED')
        with self.assertRaises(otc.TimeOutOfRangeError):
            table.node_factor_for_year('M2', 2200)

    def test_native_local_conversion_is_immutable(self):
        result = self.client.heights_at('OTC-P-0001', [dt.datetime(2010, 3, 1, tzinfo=UTC)])
        try:
            local = result.to_local('UTC')
        except otc.LocalTimeUnavailableError as error:
            self.assertIn('opentideconstants[tz]', str(error))
            with self.assertRaises(dataclasses.FrozenInstanceError):
                setattr(result.items[0], 'height_m', 5)
            with self.assertRaises(otc.UnknownTimeZoneError):
                result.to_local('posix/UTC')
            return
        self.assertEqual(local.items[0].local_time, '2010-03-01T00:00:00+00:00')
        self.assertEqual(local.items[0].local_datetime(), result.items[0].time)
        self.assertIsNone(result.items[0].local_time)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            setattr(local.items[0], 'height_m', 5)
        with self.assertRaises(otc.UnknownTimeZoneError):
            result.to_local('posix/UTC')

    def test_native_closed_release_refuses_prediction(self):
        release = self.client.release
        self.client.close()
        with self.assertRaises(otc.FileError):
            release.astro_table()

    def test_closed_prediction_precedes_argument_faults(self):
        release = self.client.release
        self.client.close()
        naive = dt.datetime(2010, 3, 1)
        for op, arguments in [('heights', {'start': naive, 'stop': naive}),
                              ('extremes', {'start': naive, 'stop': naive}),
                              ('currents', {'start': naive, 'stop': naive}),
                              ('current_events', {'start': naive, 'stop': naive}),
                              ('heights_at', {'times': None})]:
            with self.subTest(op=op), self.assertRaises(otc.FileError):
                getattr(release, op)('OTC-P-0001', **arguments)
