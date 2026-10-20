"""Prediction units on real readers, immutable results, and native construction."""
import dataclasses
import datetime as dt
import importlib.util
import os
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
if not os.environ.get('OTC_TEST_INSTALLED'):
    sys.path.insert(0, str(ROOT / 'python' / 'src'))
import opentideconstants as otc
from opentideconstants import _canonical, _canonical_types

START = dt.datetime(2010, 3, 1, tzinfo=dt.timezone.utc)
STOP = START + dt.timedelta(days=1)
FIXTURE = ROOT / 'conformance' / 'fixtures' / 'predict' / 'OTC_20991231.7.jsonl'
CALLS = (
    ('heights', 'OTC-P-0001', {'start': START, 'stop': STOP}, 'feet'),
    ('heights_at', 'OTC-P-0001', {'times': [START, START + dt.timedelta(hours=6)]}, 'feet'),
    ('extremes', 'OTC-P-0001', {'start': START, 'stop': STOP}, 'feet'),
    ('extremes', 'OTC-P-0030', {'start': START, 'stop': STOP}, 'feet'),
    ('currents', 'OTC-P-0016', {'start': START, 'stop': STOP}, 'knots'),
    ('current_events', 'OTC-P-0016', {'start': START, 'stop': STOP}, 'knots'),
)


class UnitsTests(unittest.TestCase):
    def assert_presentation(self, original, selected, units):
        default = 'meters' if units == 'feet' else 'm/s'
        factor = 0.3048 if units == 'feet' else 1852.0 / 3600.0
        self.assertEqual(original.units, default)
        self.assertEqual(selected.units, units)
        self.assertEqual(dataclasses.replace(selected, units=default, items=original.items), original)
        for before, after in zip(original.items, selected.items, strict=True):
            self.assertEqual(dataclasses.replace(after, units=default), before)
            self.assertEqual(after.units, units)
            names = {'height': 'height_m'} if units == 'feet' else (
                {'velocity': 'velocity_ms'} if hasattr(after, 'velocity_ms') else
                {'velocity_major': 'velocity_major_ms', 'velocity_minor': 'velocity_minor_ms', 'speed': 'speed_ms'})
            for name, si_name in names.items():
                self.assertEqual(getattr(before, name), getattr(before, si_name))
                self.assertEqual(getattr(after, name), getattr(before, si_name) / factor)
            with self.assertRaises(dataclasses.FrozenInstanceError):
                after.units = default

    def test_five_calls_forward_units_and_preserve_all_si_fields(self):
        for mode in ('eager', 'stream'):
            with otc.OpenTideConstants(file=FIXTURE, mode=mode) as client:
                for target in (client, client.release):
                    for op, station, arguments, units in CALLS:
                        with self.subTest(mode=mode, target=type(target).__name__, op=op, station=station):
                            default = getattr(target, op)(station, **arguments)
                            selected = getattr(target, op)(station, units=units, **arguments)
                            self.assertTrue(default.items)
                            self.assert_presentation(default, selected, units)
                            explicit_si = getattr(target, op)(station, units=default.units, **arguments)
                            self.assertEqual(explicit_si, default)

    def test_invalid_units_use_existing_error_family(self):
        with otc.OpenTideConstants(file=FIXTURE) as client:
            for target in (client, client.release):
                for op, station, arguments, units in CALLS:
                    for invalid in ('feet' if units == 'knots' else 'knots', '', None):
                        with self.subTest(op=op, invalid=invalid):
                            with self.assertRaises(otc.InvalidArgumentError) as raised:
                                getattr(target, op)(station, units=invalid, **arguments)
                            self.assertEqual(raised.exception.code, 'invalid_argument')

    def test_localization_retains_selected_values_and_original(self):
        with otc.OpenTideConstants(file=FIXTURE) as client:
            for op, station, arguments, units in CALLS:
                with self.subTest(op=op, station=station):
                    selected = getattr(client, op)(station, units=units, **arguments)
                    local = selected.to_local('America/New_York')
                    self.assertEqual(local.units, units)
                    for before, after in zip(selected.items, local.items, strict=True):
                        self.assertEqual(dataclasses.replace(after, local_time=None, utc_offset_s=None, _local=None), before)
                        self.assertIsNone(before.local_time)
                        self.assertIsNotNone(after.local_time)

    def test_legacy_constructors_keep_si_defaults_and_signed_values(self):
        point = otc.HeightPoint(START, -0.3048)
        self.assertEqual((point.units, point.height), ('meters', -0.3048))
        self.assertEqual(dataclasses.replace(point, units='feet').height, -1)
        current = otc.CurrentPoint(START, -1852.0 / 3600.0, 0, 1852.0 / 3600.0, 180)
        self.assertEqual((current.units, current.velocity_major), ('m/s', current.velocity_major_ms))
        selected = dataclasses.replace(current, units='knots')
        self.assertEqual((selected.velocity_major, selected.velocity_minor, selected.speed), (-1, 0, 1))
        self.assertEqual(otc.HeightSeries((point,)).units, 'meters')
        self.assertEqual(otc.CurrentSeries((current,)).units, 'm/s')

    def test_native_canonical_construction_retains_units(self):
        with otc.OpenTideConstants(file=FIXTURE) as client:
            for op, station, arguments, units in CALLS:
                result = getattr(client, op)(station, units=units, **arguments)
                for value in (result, result.items[0]):
                    with self.subTest(model=type(value).__name__):
                        raw = {field.name: getattr(value, field.name) for field in dataclasses.fields(value)
                               if field.name not in ('time', '_local', 'items')}
                        native = {'native_items': value.items} if hasattr(value, 'items') else {
                            'native_time': value.time, 'native_local': value._local}
                        contract = getattr(_canonical_types, '_' + type(value).__name__ + 'ModelFields')(
                            raw_fields=raw, **native)
                        actual = _canonical._materialize_typed_model(
                            raw_fields=raw, field_contract=contract, origin=client.release,
                            model_type=type(value).__name__)
                        self.assertEqual(actual, value)

    def test_canonical_argument_records_preserve_units_through_real_calls(self):
        with otc.OpenTideConstants(file=FIXTURE) as client:
            for op, station, arguments, units in CALLS:
                number = {'heights': 14, 'heights_at': 15, 'extremes': 16,
                          'currents': 17, 'current_events': 18}[op]
                names = ['_Arguments' + str(number)]
                if number <= 16:
                    names.append('_Request' + str(number))
                for name in names:
                    with self.subTest(record=name, station=station):
                        cls = getattr(_canonical_types, name)
                        values = {field.name: arguments.get(field.name, _canonical_types._OMITTED)
                                  for field in dataclasses.fields(cls)}
                        values.update(member_id='Release.' + op, station=station)
                        values.pop('units', None)
                        legacy = cls(**values)
                        record = cls(**values, units=units)
                        self.assertIsInstance(legacy.units, _canonical_types._Omitted)
                        validated = _canonical._validate_operation_arguments(
                            operation=op, arguments=record,
                            member_contract=record)
                        kwargs = {field.name: getattr(validated, field.name)
                                  for field in dataclasses.fields(validated)
                                  if field.name not in ('member_id', 'station')
                                  and not isinstance(getattr(validated, field.name), _canonical_types._Omitted)}
                        result = getattr(client.release, op)(station, **kwargs)
                        self.assertEqual(result.units, units)
                        self.assertTrue(all(item.units == units for item in result.items))
                        with self.assertRaises(otc.InvalidArgumentError):
                            _canonical._validate_operation_arguments(
                                operation=op, arguments=dataclasses.replace(record, units='invalid'),
                                member_contract=record)

    def test_runner_projects_units_only_when_requested_and_keeps_local_projection(self):
        spec = importlib.util.spec_from_file_location('units_runner', ROOT / 'conformance/runners/python/runner.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with otc.OpenTideConstants(file=FIXTURE) as client:
            runner = module.Runner()
            runner.client = client
            for op, station, arguments, units in CALLS:
                request = {'op': op, 'args': {'station_id': station, **arguments}}
                default = runner.handle(request)['prediction']
                self.assertNotIn('units', default)
                self.assertNotIn('units', default['items'][0])
                request['args']['units'] = units
                selected = runner.handle(request)['prediction']
                self.assertEqual(selected['units'], units)
                localized = runner.handle({'op': 'to_local', 'args': {'tz': 'America/New_York'}})['prediction']
                self.assertEqual(localized['units'], units)
                self.assertEqual(localized['items'][0]['units'], units)


if __name__ == '__main__':
    unittest.main()
