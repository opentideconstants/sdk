"""Real reader prediction regressions against independently pinned expected output."""
import dataclasses
import copy
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if not os.environ.get('OTC_TEST_INSTALLED'):
    sys.path.insert(0, str(ROOT / 'python' / 'src'))
import opentideconstants as otc
from test_unit import code_qualname  # noqa: E402

UTC = dt.timezone.utc
PREDICT = ROOT / 'conformance' / 'fixtures' / 'predict'


class HistoricalPredictionGuardTest(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('OTC_PRED_HISTORICAL'), 'bounded real historical source required')
    def test_selected_reference_table_model_hash_and_required_rows(self):
        original = json.loads(Path(os.environ['OTC_PRED_HISTORICAL']).read_bytes())
        start = dt.datetime(2026, 10, 11, tzinfo=UTC)
        stop = start + dt.timedelta(days=1)
        witnesses = []
        for mode in ('eager', 'stream'):
            for fault in ('valid', 'matching_hash', 'null_hash', 'wrong_table_model', 'wrong_hash',
                          'missing_table', 'missing_required_row', 'invalid_table_before_model', 'wrong_binding'):
                document = copy.deepcopy(original)
                target = next(row for row in document['stations']
                              if (row.get('subordinate_offsets') or {}).get('offset_id'))
                reference = next(row for row in document['stations']
                                 if row['station_id'] == target['subordinate_offsets']['reference_station_id'])
                constants = next(row for row in reference['constant_sets']
                                 if row['source'] == 'noaa' and row['quantity'] == 'water_level')
                convention = next(row for row in document['conventions']
                                  if row['convention_id'] == constants['convention_id'])
                table = next(row for row in document['astro_tables']
                             if row['astro_table_id'] == convention['astro_table_id'])
                if fault == 'matching_hash':
                    convention['tables_sha256'] = table['tables_sha256']
                elif fault == 'null_hash':
                    convention['tables_sha256'] = None
                elif fault == 'wrong_table_model':
                    table['v0_model'] = 'private-unsupported-model'
                elif fault == 'wrong_hash':
                    convention['tables_sha256'] = '0' * 64
                elif fault == 'missing_table':
                    document['astro_tables'] = [row for row in document['astro_tables'] if row is not table]
                elif fault == 'missing_required_row':
                    table['constituents'].pop(constants['constituents'][0]['name'])
                elif fault == 'invalid_table_before_model':
                    table['v0_model'] = 'private-unsupported-model'
                    table['constituents'][constants['constituents'][0]['name']]['f'] = []
                elif fault == 'wrong_binding':
                    other = next(row for row in document['stations']
                                 if (row.get('subordinate_offsets') or {}).get('offset_id')
                                 and row['subordinate_offsets']['reference_station_id']
                                 != target['subordinate_offsets']['reference_station_id'])
                    constants['source_record_id'] = (
                        other['subordinate_offsets']['provenance']['reference_binding']['noaa_id'])
                with self.subTest(mode=mode, fault=fault), tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / ('OTC_20261011.json' if mode == 'eager' else 'OTC_20261011.jsonl')
                    if mode == 'eager':
                        path.write_text(json.dumps(document))
                    else:
                        stations = document.pop('stations')
                        path.write_text(''.join(json.dumps(row) + '\n' for row in stations))
                        path.with_name('OTC_20261011.meta.json').write_text(json.dumps(document))
                    with otc.OpenTideConstants(file=path, mode=mode) as client:
                        sid = target['station_id']
                        self.assertEqual(client.require_station(sid).raw['subordinate_offsets'],
                                         otc._models.freeze(target['subordinate_offsets']))
                        if fault in ('valid', 'matching_hash', 'null_hash'):
                            actual = client.extremes(sid, start=start, stop=stop)
                            self.assertTrue(actual.historical_offsets)
                            self.assertEqual(actual.reference_2020_equivalence,
                                target['subordinate_offsets']['vintage']['reference_2020_equivalence'])
                            witnesses.append({'mode': mode, 'fault': fault, 'outcome': 'prediction',
                                              'events': len(actual.items), 'offset_id': actual.offset_id})
                        else:
                            expected = {'wrong_table_model': otc.UnsupportedConventionError,
                                        'wrong_hash': otc.UnsupportedConventionError,
                                        'missing_table': otc.NoAstroTableError,
                                        'missing_required_row': otc.UnsupportedConstituentError,
                                        'invalid_table_before_model': otc.InvalidArgumentError,
                                        'wrong_binding': otc.NoConstantsError}[fault]
                            with self.assertRaises(expected):
                                client.extremes(sid, start=start, stop=stop)
                            self.assertNotIn(sid, {row.station_id for row in client.stations()})
                            witnesses.append({'mode': mode, 'fault': fault, 'outcome': expected.code})
        if os.environ.get('OTC_PRED_GUARDS'):
            Path(os.environ['OTC_PRED_GUARDS']).write_text(json.dumps(witnesses, indent=2) + '\n')


class PredictionTest(unittest.TestCase):
    def setUp(self):
        self.client = otc.OpenTideConstants(file=PREDICT / 'OTC_20991231.7.json')
        self.addCleanup(self.client.close)

    def test_mixed_current_bins_select_offsets_and_preserve_harmonics(self):
        document = json.loads((PREDICT / 'OTC_20991231.7.json').read_bytes())
        template = next(row for row in document['stations'] if row['station_id'] == 'OTC-P-0016')
        # Exact NOAA ACT8851/ACT8856 offset tuples, paired with the existing
        # synthetic harmonic fixture. Full source predictions have separate real-data proof.
        targets = {
            'OTC-7c4e4c70': [(1, 15, 2, 5, 17, 1.0, 1.1, 272, 91),
                             (3, -1, -3, -13, -18, 0.8, 0.9, 274, 94)],
            'OTC-14e250fa': [(1, 7, -16, -1, 9, 1.0, 1.1, 295, 125),
                             (3, -11, 17, -8, -32, 0.8, 0.6, 306, 115)],
        }
        stations = []
        for sid, values in targets.items():
            station = copy.deepcopy(template)
            station['station_id'] = sid
            station['recommended_set_id'] = sid + '/noaa'
            constants = station['constant_sets'][0]
            constants['set_id'] = station['recommended_set_id']
            constants['current_bins'] = [row for row in constants['current_bins'] if row['bin'] == 2]
            station['current_offsets'] = [dict(zip(
                ('bin', 'time_adj_max_flood_min', 'time_adj_slack_before_ebb_min',
                 'time_adj_max_ebb_min', 'time_adj_slack_before_flood_min',
                 'flood_amp_ratio', 'ebb_amp_ratio', 'mean_flood_dir_deg', 'mean_ebb_dir_deg'), value),
                reference_station_id=sid, reference_bin=2, licence_id='noaa') for value in values]
            # A matching offset must never displace an available harmonic bin.
            station['current_offsets'].append(dict(station['current_offsets'][0], bin=2))
            stations.append(station)
        document['stations'] = stations
        start = dt.datetime(2010, 3, 1, tzinfo=UTC)
        stop = start + dt.timedelta(days=2)
        for mode in ('eager', 'stream'):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / ('OTC_20991231.7.json' if mode == 'eager' else 'OTC_20991231.7.jsonl')
                if mode == 'eager':
                    path.write_text(json.dumps(document))
                else:
                    path.write_text(''.join(json.dumps(row) + '\n' for row in stations))
                    path.with_name('OTC_20991231.7.meta.json').write_text(json.dumps(
                        {key: value for key, value in document.items() if key != 'stations'}))
                with otc.OpenTideConstants(file=path, mode=mode) as client:
                    for sid in targets:
                        for operation in ('current_events', 'currents'):
                            harmonic = getattr(client, operation)(sid, start=start, stop=stop, bin_number=2)
                            default = getattr(client, operation)(sid, start=start, stop=stop)
                            original = getattr(self.client, operation)('OTC-P-0016', start=start, stop=stop, bin_number=2)
                            self.assertEqual(harmonic.method, 'harmonic')
                            self.assertEqual(harmonic, default)
                            self.assertEqual(harmonic.items, original.items)
                        reference = client.current_events(sid, start=start - dt.timedelta(hours=1),
                            stop=stop + dt.timedelta(hours=1), bin_number=2)
                        for bin_number in (1, 3):
                            with self.subTest(mode=mode, station=sid, bin_number=bin_number):
                                result = client.current_events(sid, start=start, stop=stop, bin_number=bin_number)
                                self.assertEqual(result.method, 'offsets')
                                self.assertEqual(result.reference_station_id, sid)
                                self.assertEqual(result.reference_bin, 2)
                                self.assertEqual(result.bin_number, bin_number)
                                self.assertEqual(result.set_id, sid + '/noaa')
                                offset = next(row for row in client.require_station(sid).raw['current_offsets']
                                              if row['bin'] == bin_number)
                                expected = []
                                for item in reference.items:
                                    shifted = item.time + dt.timedelta(minutes=offset['time_adj_' + item.type + '_min'])
                                    if not start <= shifted < stop:
                                        continue
                                    flood = item.type == 'max_flood'
                                    peak = item.type in ('max_flood', 'max_ebb')
                                    expected.append((shifted, item.type,
                                        item.velocity_ms * offset['flood_amp_ratio' if flood else 'ebb_amp_ratio'] if peak else 0.0,
                                        offset['mean_flood_dir_deg' if flood else 'mean_ebb_dir_deg'] if peak else None))
                                expected.sort()
                                self.assertTrue(result.items)
                                self.assertEqual({item.type for item in result.items},
                                    {'max_flood', 'max_ebb', 'slack_before_flood', 'slack_before_ebb'})
                                self.assertEqual(len(result.items), len(expected))
                                for actual, wanted in zip(result.items, expected):
                                    self.assertEqual((actual.time, actual.type, actual.direction_deg),
                                                     (wanted[0], wanted[1], wanted[3]))
                                    self.assertAlmostEqual(actual.velocity_ms, wanted[2], places=9)
                                with self.assertRaises(otc.ExtremesOnlyError):
                                    client.currents(sid, start=start, stop=stop, bin_number=bin_number)
                                with self.assertRaises(otc.BinNotFoundError):
                                    client.current_events(sid, start=start, stop=stop,
                                        bin_number=bin_number, set_id=sid + '/noaa')

    def test_native_height_and_repeat_order(self):
        times = [dt.datetime(2010, 3, 1, tzinfo=UTC)] * 2
        result = self.client.heights_at('OTC-P-0001', times)
        self.assertEqual([p.time for p in result.items], times)
        self.assertEqual(result.method, 'harmonic')
        self.assertEqual(result.datum_name, 'mean_level')
        self.assertAlmostEqual(result.items[0].height_m, result.items[1].height_m, places=12)
        self.assertEqual(result.set_id, 'OTC-P-0001/noaa')

    def test_native_named_prediction_phase_values_and_local_fold_gap(self):
        events = []
        route = ['none']
        counts = {}
        root = Path(otc.__file__).resolve().parent  # python/src, or the installed package (OTC_TEST_INSTALLED)
        selected = {'_window', '_context', '_chosen', '_table', '_reference', '_datum', '_subdatum',
                    '_result', '_current', '_current_events', 'heights', 'heights_at', 'extremes',
                    'currents', 'current_events', 'events', 'instant', 'datums', 'ranges', 'astro_table',
                    'equilibrium_argument', 'node_factor', 'equilibrium_for_year', 'node_factor_for_year',
                    'localize', 'to_local', 'value', '_year', '__init__'}

        def summary(value):
            if value is None or isinstance(value, (str, int, float, bool)):
                return value
            if isinstance(value, dt.datetime):
                return value.isoformat()
            if hasattr(value, 'station_id'):
                return {'type': type(value).__name__, 'station_id': value.station_id}
            if hasattr(value, 'set_id'):
                return {'type': type(value).__name__, 'set_id': value.set_id}
            if isinstance(value, (tuple, list)):
                return {'type': type(value).__name__, 'length': len(value), 'first': str(value[0]) if value else None}
            return {'type': type(value).__name__}

        def profile(frame, event, value):
            filename = Path(frame.f_code.co_filename)
            name = frame.f_code.co_name
            if event not in ('call', 'return') or name not in selected or not filename.is_relative_to(root):
                return
            key = (route[0], code_qualname(frame.f_code), event)
            counts[key] = counts.get(key, 0) + 1
            if counts[key] > 4:
                return
            context = frame.f_locals.get('context')
            entry = {'route': route[0], 'event': event, 'file': str(filename.relative_to(ROOT) if filename.is_relative_to(ROOT) else filename.relative_to(root.parent)),
                     'symbol': code_qualname(frame.f_code), 'line': frame.f_code.co_firstlineno,
                     'inputs': {key: summary(frame.f_locals[key]) for key in
                                ('station', 'start', 'stop', 'step_s', 'quantity', 'set_id', 'datum',
                                 'bin_number', 'offset_id', 'series', 'name', 'at', 'year') if key in frame.f_locals},
                     'result': summary(value) if event == 'return' else None}
            if context is not None:
                entry['context'] = {key: summary(getattr(context, key)) for key in
                                    ('station', 'constants', 'method', 'reference', 'reference_bin',
                                     'bin_number', 'datum_name', 'datum_kind')}
            events.append(entry)

        start = dt.datetime(2010, 3, 1, tzinfo=UTC)
        stop = start + dt.timedelta(days=1)
        results = {}
        previous = sys.getprofile()
        try:
            sys.setprofile(profile)
            for mode in ('eager', 'stream'):
                suffix = '.json' if mode == 'eager' else '.jsonl'
                with otc.OpenTideConstants(file=PREDICT / ('OTC_20991231.7' + suffix), mode=mode) as client:
                    for family, op, sid, arguments in [
                            ('height', 'heights', 'OTC-P-0001', {'step_s': 3600}),
                            ('tide-events', 'extremes', 'OTC-P-0001', {}),
                            ('current', 'currents', 'OTC-P-0016', {'step_s': 3600}),
                            ('current-events', 'current_events', 'OTC-P-0016', {}),
                            ('tide-offset', 'extremes', 'OTC-P-0030', {}),
                            ('folded-offset', 'heights', 'OTC-P-0035', {'step_s': 3600}),
                            ('current-offset', 'current_events', 'OTC-P-0051', {})]:
                        route[0] = mode + '-' + family
                        result = getattr(client, op)(sid, start=start, stop=stop, **arguments)
                        self.assertEqual(result.station_id, sid)
                        self.assertEqual(result.release, '20991231.7')
                        self.assertEqual(result.algorithm, 'otc-predict-1')
                        self.assertGreater(len(result.items), 0)
                        results[route[0]] = dataclasses.asdict(result)
                    route[0] = mode + '-empty-window'
                    future = dt.datetime(2200, 1, 1, tzinfo=UTC)
                    empty = client.heights('OTC-P-0001', start=future, stop=future)
                    self.assertEqual(empty.items, ())
                    self.assertEqual(counts.get((route[0], 'Sum.value', 'call'), 0), 0)
                    route[0] = mode + '-auxiliary'
                    info = client.datums('OTC-P-0001')
                    ranges = client.ranges('OTC-P-0001')
                    table = client.release.astro_table()
                    self.assertIsNotNone(info)
                    self.assertIsInstance(ranges, otc.Ranges)
                    self.assertIsNotNone(table)
                    self.assertIsInstance(table.equilibrium_argument('M2', start), float)
                    self.assertGreater(table.node_factor('M2', start), 0)
                    self.assertIsInstance(table.equilibrium_for_year('M2', 2010), float)
                    self.assertGreater(table.node_factor_for_year('M2', 2010), 0)
                    self.assertEqual(table.valid_range, (2000, 2030))
                    for phase, times in [('fold', [dt.datetime(2010, 10, 31, hour, 30, tzinfo=UTC) for hour in (0, 1)]),
                                         ('gap', [dt.datetime(2010, 3, 28, hour, 30, tzinfo=UTC) for hour in (0, 1)])]:
                        route[0] = mode + '-local-' + phase
                        utc_result = client.heights_at('OTC-P-0001', times)
                        local = utc_result.to_local('Europe/Oslo')
                        self.assertEqual([row.time for row in local.items], times)
                        self.assertEqual(local.release, utc_result.release)
                        self.assertTrue(all(row.local_time is None for row in utc_result.items))
                        if phase == 'fold':
                            self.assertEqual([row.utc_offset_s for row in local.items], [7200, 3600])
                            self.assertEqual([row.local_datetime().fold for row in local.items], [0, 1])
                        else:
                            self.assertEqual([row.local_datetime().hour for row in local.items], [1, 3])
                        results[route[0]] = dataclasses.asdict(local)
        finally:
            sys.setprofile(previous)
        for family in ('height', 'tide-events', 'current', 'current-events', 'tide-offset', 'folded-offset', 'current-offset'):
            self.assertEqual(results['eager-' + family], results['stream-' + family])
        for mode in ('eager', 'stream'):
            calls = [event['symbol'] for event in events if event['route'] == mode + '-height' and event['event'] == 'call']
            self.assertLess(calls.index('_window'), calls.index('_context'))
            self.assertLess(calls.index('_context'), calls.index('_result'))
            self.assertIn('_table', calls)
        if os.environ.get('OTC_PRED_TRACE'):
            Path(os.environ['OTC_PRED_TRACE']).write_text(json.dumps({'events': events, 'results': results,
                'counts': [{'route': key[0], 'symbol': key[1], 'event': key[2], 'count': value}
                           for key, value in counts.items()]}, default=str, indent=2) + '\n')

    def test_native_extremes_independent_pin(self):
        expected = json.loads((ROOT / 'conformance/cases/predict-extremes.json').read_text(encoding='utf-8'))['cases'][0]['steps'][0]['expect']['prediction']
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

    def test_real_runner_fractional_instants_across_python_versions(self):
        runner = [sys.executable, str(ROOT / 'conformance/runners/python/runner.py')]
        if os.environ.get('OTC_TEST_INSTALLED'):
            runner.append('--installed')
        requests = [{'op': 'open', 'args': {'file': str(PREDICT / 'OTC_20991231.7.json')}},
                    {'op': 'heights_at', 'args': {'station_id': 'OTC-P-0001',
                     'times': ['2010-03-01T12:00:00.7Z', '2010-03-01T12:00:00.7000001+00:00']}},
                    {'op': 'heights_at', 'args': {'station_id': 'OTC-P-0001',
                     'times': ['2010-03-01T12:00:00.7']}}]
        process = subprocess.run(runner, input=''.join(json.dumps(row) + '\n' for row in requests),
                                 capture_output=True, text=True, check=True)
        replies = [json.loads(line) for line in process.stdout.splitlines()][1:]
        self.assertIn('result', replies[1], replies[1])
        points = replies[1]['result']['prediction']['items']
        self.assertEqual(points[0], points[1])
        self.assertEqual(points[0]['time'], '2010-03-01T12:00:00Z')
        self.assertEqual(replies[2]['error']['code'], 'invalid_argument')

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
