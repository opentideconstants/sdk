"""Explicit selection of preserved subordinate profiles without changing defaults."""
import copy
import dataclasses
import datetime as dt
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
if not os.environ.get('OTC_TEST_INSTALLED'):
    sys.path.insert(0, str(ROOT / 'python' / 'src'))
import opentideconstants as otc
from test_datum_fallback import PREDICT, write_release

START = dt.datetime(2026, 10, 23, tzinfo=ZoneInfo('America/Los_Angeles'))
STOP = START + dt.timedelta(days=1)
TIMES = [START + dt.timedelta(hours=12)]


class SubordinateProfileSelectionTests(unittest.TestCase):
    def model_and_profile(self):
        document = json.loads(PREDICT.read_text(encoding='utf-8'))
        station = next(s for s in document['stations'] if s.get('subordinate_offsets'))
        model = copy.deepcopy(document['stations'][1]['constant_sets'][0])
        model['set_id'] = station['station_id'] + '/own'
        station['constant_sets'] = [model]
        station['recommended_set_id'] = model['set_id']
        return document, station, model

    def test_public_handle_selects_profile_and_preserves_own_model_default(self):
        document, station, model = self.model_and_profile()
        for mode in ('eager', 'stream'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                with otc.OpenTideConstants(file=write_release(directory, document, mode), mode=mode) as client:
                    sid = station['station_id']
                    offsets = client.require_station(sid).subordinate_offsets
                    expected = sid + '/subordinate-offsets/' + offsets.reference_station_id
                    self.assertEqual(offsets.offset_id, expected)
                    before = client.heights_at(sid, TIMES, datum='mean_level')
                    selected = client.extremes(sid, start=START, stop=STOP, datum='chart', offset_id=offsets.offset_id)
                    self.assertTrue(selected.items)
                    self.assertEqual(selected.offset_id, expected)
                    self.assertFalse(selected.historical_offsets)
                    self.assertIsNone(selected.set_id)
                    self.assertEqual(client.heights_at(sid, TIMES, datum='mean_level'), before)
                    self.assertEqual(before.set_id, model['set_id'])
                    self.assertNotIn('offset_id', client.require_station(sid).raw['subordinate_offsets'])
                    with self.assertRaises(otc.InvalidArgumentError):
                        client.extremes(sid, start=START, stop=STOP, offset_id=expected + '/other')
                    with self.assertRaises(otc.InvalidArgumentError):
                        client.extremes(sid, start=START, stop=STOP, set_id=model['set_id'], offset_id=expected)

    @unittest.skipUnless(os.environ.get('OTC_SUBORDINATE_PROFILE_NATIVE'), 'real native evidence not supplied')
    def test_six_actual_lat_hat_cells_against_held_mllw_profile(self):
        with otc.OpenTideConstants(file=os.environ['OTC_SUBORDINATE_PROFILE_NATIVE'], mode='stream') as client:
            reference = client.require_station('OTC-00b96c29')
            reference_set = next(s for s in reference.constant_sets(include_no_constants=True)
                                 if s.source == 'noaa' and s.quantity == 'water_level' and s.qc_status in ('ok', 'flagged'))
            reference_events = client.extremes(reference.station_id, start=START - dt.timedelta(hours=3),
                stop=STOP + dt.timedelta(hours=3), datum='chart', set_id=reference_set.set_id)
            for sid in ('OTC-b70da835', 'OTC-87c602a9', 'OTC-4102b197'):
                station = client.require_station(sid)
                raw = station.raw['subordinate_offsets']
                handle = station.subordinate_offsets.offset_id
                default = client.heights_at(sid, TIMES)
                mean = client.heights_at(sid, TIMES, datum='mean_level')
                self.assertEqual(default.items, mean.items)
                encode = lambda value: value.astimezone(ZoneInfo('America/Los_Angeles')).strftime('%Y-%m-%d %I:%M:%S %p %Z')
                print('CONTROL ' + sid + ' ' + json.dumps({'default': dataclasses.asdict(default),
                    'mean': dataclasses.asdict(mean)}, default=encode, sort_keys=True))
                for key in ('lat', 'hat'):
                    with self.subTest(station=sid, datum=key):
                        named = client.extremes(sid, start=START, stop=STOP, datum=key, offset_id=handle)
                        self.assertIsNotNone(handle)
                        chart = client.extremes(sid, start=START, stop=STOP, datum='chart', offset_id=handle)
                        self.assertTrue(named.items)
                        self.assertEqual([p.time for p in named.items], [p.time for p in chart.items])
                        expected = []
                        for event in reference_events.items:
                            kind = event.type.value
                            time = event.time + dt.timedelta(minutes=raw['time_offset_' + kind + '_min'])
                            if START <= time < STOP:
                                height = event.height_m * raw['height_offset_' + kind]
                                expected.append((time, height))
                        expected.sort(key=lambda pair: pair[0])
                        self.assertEqual([p.time for p in named.items], [p[0] for p in expected])
                        level = raw['datum']['named'][key]
                        for item, chart_item, (_, expected_chart) in zip(named.items, chart.items, expected, strict=True):
                            self.assertAlmostEqual(chart_item.height_m, expected_chart, places=12)
                            self.assertAlmostEqual(chart_item.height_m - item.height_m, level, places=12)
                        basis = raw['datum']['basis'][key]
                        self.assertIn(basis['fallback']['otc_finding'], named.source_note)
                        self.assertEqual(named.datum_uncertainty_m, basis['uncertainty_m'])
                        self.assertEqual(named.offset_id, handle)
                        self.assertFalse(named.historical_offsets)
                        self.assertEqual(client.heights_at(sid, TIMES), default)
                        print(f'GREEN {sid} {key}: {len(named.items)} events; chart-minus-named={level!r} m; reference time/ratio equations exact; default unchanged; UNRELIABLE fallback retained')
