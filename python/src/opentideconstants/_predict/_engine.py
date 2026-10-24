"""Prediction selection, datums, harmonic curves and one-link NOAA offsets."""
from __future__ import annotations

import math
import hashlib
import json
from dataclasses import dataclass
from collections.abc import Sequence
from typing import Any, NoReturn, TypeVar, Callable
from .. import _errors as X
from .._enums import ExtremeType, CurrentEventType, PredictionMethod
from .._models import Station, freeze, _subordinate_offset_id
from ._astro import AstroTable, instant, utc, angle
from ._harmonic import Sum, events, RAD, _unrounded_events
from ._results import HeightPoint, Extreme, CurrentPoint, CurrentEvent, HeightSeries, ExtremeList, CurrentSeries, CurrentEventList, DatumInfo, DatumLevel, Ranges


def _validate_offset_arguments(offset_id, set_id):
    if offset_id is not None and not isinstance(offset_id, str):
        raise X.InvalidArgumentError('offset_id must be a string')
    if offset_id is not None and set_id is not None:
        raise X.InvalidArgumentError('set_id and offset_id are mutually exclusive')


def _validate_all_sets(all_sets):
    if not isinstance(all_sets, bool):
        raise X.InvalidArgumentError('all_sets must be a boolean')


def _validate_astro_table_id(id):
    if id is not None and not isinstance(id, str):
        raise X.InvalidArgumentError('astro table id must be a string')


@dataclass
class _Context:
    station: Any
    constants: Any
    table: Any
    method: str = 'harmonic'
    reference: Any = None
    reference_bin: Any = None
    bin_number: Any = None
    offsets: Any = None
    selected_offset_id: Any = None
    total: Any = None
    minor: Any = None
    current_bin: Any = None
    sigma: float = 1.0
    datum_name: Any = None
    datum_kind: Any = None
    datum_uncertainty: Any = None
    datum_method: Any = None
    datum_flags: tuple[str, ...] = ()
    omitted: Any = None


def astro_table(release, id=None) -> AstroTable | None:
    release._check_open()
    _validate_astro_table_id(id)
    if id is None:
        id = next((c.raw.get('astro_table_id') for c in release.conventions if c.raw.get('astro_table_id')), None)
    if id is None:
        return None
    cached = release._astro_cache.get(id)
    if cached is not None:
        return cached
    raw = next((t for t in release._meta.get('astro_tables') or () if t.get('astro_table_id') == id), None)
    if raw is None:
        return None
    table = AstroTable(raw)
    release._astro_cache[id] = table
    return table


def _station(release, station):
    release._check_open()
    if isinstance(station, str):
        return release.require_station(station)
    if not isinstance(station, Station):
        raise X.InvalidArgumentError('station must be a Station or station id')
    # Resolve through this release, including effective recommendations.
    actual = release.station(station.station_id)
    if actual is None or actual.raw != station.raw:
        raise X.InvalidArgumentError('station is not from this release')
    return actual


def _options(set_id, datum=None, bin_number=None):
    if set_id is not None and not isinstance(set_id, str):
        raise X.InvalidArgumentError('set_id must be a string')
    if datum is not None and not isinstance(datum, str):
        raise X.InvalidArgumentError('datum must be a string')
    if bin_number is not None and (not isinstance(bin_number, int) or isinstance(bin_number, bool) or not 1 <= bin_number <= 2**53 - 1):
        raise X.InvalidArgumentError('bin_number must be an integer from 1 to 2^53 - 1')


_NO_STEP = object()

def _window(start, stop, step_s=_NO_STEP):
    start, stop = instant(start), instant(stop)
    if start > stop:
        raise X.InvalidArgumentError('start must not be after stop')
    if step_s is not _NO_STEP and (not isinstance(step_s, int) or isinstance(step_s, bool) or step_s <= 0):
        raise X.InvalidArgumentError('step_s must be a positive integer')
    return start, stop


def _chosen(release, station, set_id):
    if set_id is None:
        return station.recommended_set
    constants = station.constant_set(set_id)
    if constants is None:
        raise X.InvalidArgumentError(f'set_id {set_id!r} is not a set of {station.station_id}')
    if release._commercial_only and constants.licence.commercial_use is not True:
        raise X.InvalidArgumentError(f'commercial_only refuses set_id {set_id!r}')
    return constants


def _table(release, constants):
    convention = constants.convention
    if convention.v0_model != 'schureman_tcd' or convention.nodal_handling != 'f_u_at_prediction':
        raise X.UnsupportedConventionError(f'unsupported convention {convention.convention_id}')
    ident = convention.raw.get('astro_table_id') or ''
    table = astro_table(release, ident)
    if table is None:
        raise X.NoAstroTableError(f'release {release.datestamp} has no astro table "{ident}" for convention "{convention.convention_id}". Format 1.0 requires astro_tables when a convention uses f_u_at_prediction (since the schema revision of site PR #45); this file was written before that revision or is invalid.')
    if (table._raw.get('v0_model') != convention.v0_model
            or (convention.raw.get('tables_sha256') is not None
                and convention.raw['tables_sha256'] != table._raw.get('tables_sha256'))):
        raise X.UnsupportedConventionError(f'astro table "{ident}" does not match convention "{convention.convention_id}"')
    return table


def _unavailable(missing) -> NoReturn:
    raise X.DatumUnavailableError(f'datum is missing {missing}', missing=missing)


def _published_msl_datums(station, constants, raw):
    """Bind an authenticated publisher table to model mean, with the assumption explicit."""
    if constants is None or constants.quantity != 'water_level':
        return raw
    named, basis = dict(raw.get('named') or {}), dict(raw.get('basis') or {})
    additions = {}
    endpoint = 'https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations/'
    height_keys = {'stnd', 'navd88', 'vivd09', 'msl', 'mhhw', 'mhw', 'mtl', 'dtl',
                   'mlw', 'mllw', 'hat', 'lat', 'mhwn', 'mlwn', 'mhws', 'mlws'}
    for source in station.raw.get('source_records') or ():
        ident = source.get('source_record_id')
        if source.get('source') != 'noaa' or not isinstance(ident, str) or not ident.isdigit():
            continue
        metadata = source.get('original_metadata') or {}
        for candidate in source.get('retained_datums') or ():
            binding, frame = candidate.get('input_binding') or {}, candidate.get('frame') or {}
            proof = candidate.get('basis') or {}
            epoch, digest = proof.get('epoch'), binding.get('sha256')
            if (candidate.get('kind') != 'published' or candidate.get('units') != 'm'
                    or candidate.get('source_record_id') != ident
                    or frame.get('kind') != 'gauge_zero' or frame.get('name') != 'STND'
                    or frame.get('tie_status') != 'source_declared'
                    or not isinstance(epoch, str) or not epoch
                    or not isinstance(digest, str) or len(digest) != 64
                    or any(c not in '0123456789abcdef' for c in digest)
                    or binding.get('source_url') != endpoint + ident + '/datums.json?units=metric'):
                continue
            values, fields = candidate.get('values') or {}, proof.get('source_fields') or {}
            table = values
            response = metadata.get('datums_response_json')
            # Original source provenance describes the older metadata capture;
            # later published tables carry their own acquisition receipt binding.
            if response is None:
                receipt = binding.get('receipt_sha256')
                if (not isinstance(receipt, str) or len(receipt) != 64
                        or any(c not in '0123456789abcdef' for c in receipt)):
                    continue
            if response is not None:
                if (not isinstance(response, str) or hashlib.sha256(response.encode()).hexdigest() != digest
                        or metadata.get('datums_response_sha256') != digest):
                    continue
                try:
                    body = json.loads(response)
                except (ValueError, TypeError):
                    continue
                if (not isinstance(body, dict) or body.get('self') != endpoint + ident + '/datums.json'
                        or body.get('units') != 'meters' or body.get('epoch') != epoch):
                    continue
                table = {row.get('name'): row.get('value') for row in body.get('datums') or ()
                         if isinstance(row, dict)}
            msl = table.get('MSL')
            if (not isinstance(msl, (int, float)) or isinstance(msl, bool) or not math.isfinite(msl)
                    or (response is None and (fields.get('MSL') or {}).get('value') != msl)):
                continue
            try:
                identity = json.loads(metadata.get('identity_binding_json') or '{}')
            except (ValueError, TypeError):
                continue
            model = constants.raw
            same_gauge = (model.get('source') == 'noaa' and model.get('source_record_id') == ident)
            original = identity.get('original_inventory_source_tuple') or {}
            same_gauge = same_gauge or (identity.get('same_gauge_asserted') is True
                and original.get('source') == 'gesla' and model.get('source') == 'gesla-fit'
                and all(original.get(key) == model.get(key) for key in ('source_record_id', 'source_version')))
            flags = ['medium' if same_gauge else 'low',
                     f'bound via published MSL; assumes model mean = agency MSL (epoch {epoch})']
            if not same_gauge:
                flags.append('different-model binding; no same-gauge or surveyed frame tie asserted')
            model_epoch = ((raw.get('basis') or {}).get('msl') or {}).get('epoch')
            if model_epoch != epoch:
                flags.append('model and agency MSL epochs differ or model epoch is unknown')
            mean_in_zero = 0.0 if raw.get('zero') == 'harmonic_mean' else raw.get('msl_offset_m')
            for key, value in values.items():
                name = key.lower()
                field = fields.get(key) or {}
                if (name not in height_keys or name in named
                        or not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value)
                        or field.get('name') != key or field.get('value') != value or table.get(key) != value):
                    continue
                # Keep DatumLevel.value_m and above_chart_m in the selected
                # model's existing zero whenever that zero is established.
                level = value - msl + (mean_in_zero if mean_in_zero is not None else 0.0)
                additions.setdefault(name, []).append((level, {
                    'kind': 'published', 'method': 'published_msl_binding', 'source_name': 'NOAA ' + ident,
                    'epoch': epoch, 'uncertainty_m': None, 'flags': tuple(flags),
                    '_retained': True, '_retained_mean': mean_in_zero is None}))
    for key, candidates in additions.items():
        if len(candidates) == 1:
            named[key], basis[key] = candidates[0]
    return dict(raw, named=named, basis=basis)


def _retained_datum(release, station, constants=None, offsets=None):
    """An effective named view; retained values never alter the release or its defaults."""
    model = constants.raw if constants is not None else {}
    raw = (offsets if offsets is not None else model).get('datum') or {}
    named, basis = dict(raw.get('named') or {}), dict(raw.get('basis') or {})
    additions = {}
    for source in station.raw.get('source_records') or ():
        for candidate in source.get('retained_datums') or ():
            if candidate.get('kind') != 'computed' or candidate.get('units') != 'm':
                continue
            if candidate.get('source_record_id') != source.get('source_record_id'):
                continue
            frame = candidate.get('frame') or {}
            binding = candidate.get('input_binding') or {}
            if offsets is None:
                source_name = {'ticon': 'ticon-4', 'gesla': 'gesla-fit'}.get(source.get('source'), source.get('source'))
                if (not model or frame.get('kind') != 'harmonic_mean' or candidate.get('set_id') != model.get('set_id')
                        or source_name != model.get('source')
                        or any(source.get(key) != model.get(key) for key in
                               ('source_record_id', 'source_version', 'source_model'))):
                    continue
                digest = hashlib.sha256(json.dumps(model, sort_keys=True, separators=(',', ':'),
                                                    ensure_ascii=False, default=dict).encode()).hexdigest()
                if binding.get('set_id') != model.get('set_id') or binding.get('constant_set_sha256') != digest:
                    continue
            else:
                method = candidate.get('method')
                if (method not in ('noaa_subordinate_reference_datums_v1', 'noaa_subordinate_mtl_msl_proxy_v1')
                        or frame.get('kind') != 'unknown' or frame.get('name') != 'NOAA subordinate MLLW'
                        or (offsets.get('datum') or {}).get('zero_name') != 'MLLW'):
                    continue
                native = (candidate.get('basis') or {}).get('native_offsets') or {}
                keys = ('reference_station_id', 'height_adjusted_type', 'height_offset_high',
                        'height_offset_low', 'time_offset_high_min', 'time_offset_low_min')
                if any(key not in native or native[key] != offsets.get(key) for key in keys):
                    continue
                if offsets.get('source_record_id') is not None and any(
                        offsets.get(key) != source.get(key) for key in ('source', 'source_record_id', 'source_version')):
                    continue
                own, reference = binding.get('published_offsets') or {}, binding.get('published_reference') or {}
                if (any(own.get(key) != source.get(key) for key in ('source', 'source_record_id', 'source_version'))
                        or reference.get('native_station_id') != offsets.get('reference_station_id')):
                    continue
                reference_station = release.station(reference['native_station_id'])
                if reference_station is None or not any(
                        record.get('source') == reference.get('source')
                        and record.get('source_record_id') == reference.get('source_record_id')
                        and any(datum.get('kind') == 'published'
                                and (datum.get('input_binding') or {}).get('sha256') == reference.get('sha256')
                                and (datum.get('input_binding') or {}).get('source_url') == reference.get('source_url')
                                for datum in record.get('retained_datums') or ())
                        for record in reference_station.raw.get('source_records') or ()):
                    continue
                if not all(isinstance(proof.get('response_json'), str)
                           and hashlib.sha256(proof['response_json'].encode()).hexdigest() == proof.get('sha256')
                           for proof in (own, reference)):
                    continue
                try:
                    published = json.loads(own['response_json'])
                    reference_body = json.loads(reference['response_json'])
                except (ValueError, TypeError):
                    continue
                endpoint = 'https://api.tidesandcurrents.noaa.gov/mdapi/prod/webapi/stations/'
                if (not isinstance(published, dict) or not isinstance(reference_body, dict)
                        or own.get('source_url') != endpoint + source['source_record_id'] + '/tidepredoffsets.json'
                        or published.get('refStationId') != reference.get('source_record_id')
                        or own.get('reference_source_record_id') != reference.get('source_record_id')
                        or reference_body.get('self') != endpoint + reference['source_record_id'] + '/datums.json'
                        or reference_body.get('units') != 'meters'
                        or (candidate.get('basis') or {}).get('reference_epoch') != reference_body.get('epoch')):
                    continue
                operation = published.get('heightAdjustedType')
                factor = 0.3048 if operation == 'F' else 1.0
                adjustments = (('height_offset_high', 'heightOffsetHighTide', factor),
                               ('height_offset_low', 'heightOffsetLowTide', factor),
                               ('time_offset_high_min', 'timeOffsetHighTide', 1.0),
                               ('time_offset_low_min', 'timeOffsetLowTide', 1.0))
                if (operation not in ('R', 'F') or offsets.get('height_adjusted_type') != ('A' if operation == 'F' else 'R')
                        or any(not isinstance(published.get(field), (int, float))
                               or isinstance(published[field], bool)
                               or not math.isclose(published[field] * scale, offsets[native_key], rel_tol=0, abs_tol=1e-12)
                               for native_key, field, scale in adjustments)):
                    continue
                if method == 'noaa_subordinate_mtl_msl_proxy_v1':
                    proof_basis = candidate.get('basis') or {}
                    if (proof_basis.get('approximation') != 'approximation: MTL used as MSL proxy, subordinate-derived'
                            or proof_basis.get('proxy_of') != 'derived_mtl' or proof_basis.get('never_default') is not True
                            or (candidate.get('reliability') or {}).get('status') != 'low'):
                        continue
            for key, value in (candidate.get('values') or {}).items():
                # Units and the proven computational frame admit named heights;
                # tidal ranges and elapsed intervals are separate quantities.
                if key in ('mn', 'gt', 'dhq', 'dlq', 'hwi', 'lwi'):
                    continue
                if key in named or not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
                    continue
                additions.setdefault(key, []).append((value, candidate))
    for key, candidates in additions.items():
        # An unqualified named request cannot silently choose competing retained estimates.
        if len(candidates) != 1:
            continue
        value, candidate = candidates[0]
        reliability = candidate.get('reliability') or {}
        limitations = tuple(reliability.get('limitations') or ())
        label = (candidate.get('basis') or {}).get('approximation')
        flags = tuple(filter(None, (reliability.get('status'), label))) + limitations
        named[key] = value
        basis[key] = {'kind': candidate['kind'], 'method': candidate.get('method'),
                      'uncertainty_m': candidate.get('uncertainty_m'), 'flags': flags,
                      'data_span': candidate.get('window'), '_retained': True,
                      '_retained_mean': offsets is None}
    effective = dict(raw, named=named, basis=basis)
    return _published_msl_datums(station, constants, effective) if offsets is None else effective


def _datum_metadata(context, key, basis):
    context.datum_name, context.datum_kind, context.datum_uncertainty = key, basis.get('kind'), basis.get('uncertainty_m')
    if basis.get('_retained'):
        context.datum_method = basis.get('method')
        context.datum_flags = tuple(basis.get('flags') or ())


def _datum(raw, datum, context, *, published=False):
    datum = 'mean_level' if datum is None else datum
    if datum == 'mean_level' and not published:
        context.datum_name = datum
        return 0.0
    d = raw or {}
    named, basis = d.get('named') or {}, d.get('basis') or {}
    if not published and datum in named and (basis.get(datum) or {}).get('_retained_mean'):
        _datum_metadata(context, datum, basis[datum])
        return -named[datum]
    harmonic_mean = d.get('zero') == 'harmonic_mean' and not published
    if d.get('msl_offset_m') is None and not harmonic_mean:
        _unavailable('msl_offset_m')
    mean_term = 0.0 if harmonic_mean else d['msl_offset_m']
    if datum == 'zero' and not published:
        context.datum_name = d.get('zero_name') or d.get('zero') or 'unknown'
        return mean_term
    key = d.get('chart_datum') if datum == 'chart' else datum
    if datum == 'chart' and key is None:
        _unavailable('chart_datum')
    if key not in named:
        _unavailable(key)
    b = basis.get(key) or {}
    if published and b.get('kind') != 'published':
        _unavailable('published chart datum')
    _datum_metadata(context, key, b)
    return mean_term - named[key]


def _subdatum(offsets, datum, context):
    d = offsets.get('datum') or {}
    named, basis = d.get('named') or {}, d.get('basis') or {}
    chart = d.get('chart_datum')
    key = chart if datum is None or datum == 'chart' else datum
    if datum is None or datum == 'chart':
        term = 0.0
    elif key in named:
        term = named.get(chart, 0.0) - named[key]
    else:
        _unavailable(datum)
    b = basis.get(key) or {}
    _datum_metadata(context, key, b)
    return term


def _reference(release, offsets, quantity, bin_number=None):
    ident = offsets.get('reference_station_id')
    station = release.station(ident)
    constants = None
    if station is not None:
        constants = next((s for s in station.constant_sets(include_no_constants=True) if s.quantity == quantity and s.qc_status in ('ok', 'flagged') and
                          ((s.source == 'noaa') if quantity == 'water_level' else any(b.get('bin') == bin_number for b in s.raw.get('current_bins') or ()))), None)
    if constants is None:
        raise X.ReferenceUnavailableError(f'reference {ident} has no usable set', reference_station_id=ident)
    if release._commercial_only:
        for licence_id in (offsets.get('licence_id'), constants.licence.licence_id):
            licence = release.licence(licence_id) if licence_id else None
            if licence_id is not None and (licence is None or licence.commercial_use is not True):
                raise X.ReferenceUnavailableError(f'commercial_only refuses reference licence {licence_id}', reference_station_id=ident)
    return station, constants


def _bin(station, bins, requested):
    chosen = requested if requested is not None else station.raw.get('default_current_bin')
    if chosen is None and bins:
        chosen = min(b['bin'] for b in bins)
    row = next((b for b in bins if b.get('bin') == chosen), None)
    if row is None:
        raise X.BinNotFoundError(f'bin_number {chosen} is not available')
    return row


def _current(context, row):
    context.current_bin = row
    azimuth, flood = row.get('azimuth_deg', 0.0), row.get('mean_flood_dir_deg')
    context.sigma = 1.0 if flood is None or math.cos((azimuth - flood) * RAD) >= 0 else -1.0
    context.total = Sum(context.table, row.get('constituents') or (), amplitude='major_amplitude_ms', phase='major_phase_deg', mean=row.get('mean_major_ms', 0.0))
    context.minor = Sum(context.table, row.get('constituents') or (), amplitude='minor_amplitude_ms', phase='minor_phase_deg', mean=row.get('mean_minor_ms', 0.0))


def _context(release, station, quantity, set_id, datum=None, bin_number=None, series=False, offset_id=None):
    station = _station(release, station)
    _options(set_id, datum, bin_number)
    _validate_offset_arguments(offset_id, set_id)
    constants = _chosen(release, station, set_id)
    usable = constants is not None and constants.qc_status in ('ok', 'flagged')
    tide_offsets, current_offsets = station.raw.get('subordinate_offsets'), station.raw.get('current_offsets')
    historical = tide_offsets is not None and tide_offsets.get('offset_id') is not None
    if offset_id is not None:
        if tide_offsets is None or _subordinate_offset_id(station.station_id, tide_offsets) != offset_id:
            raise X.InvalidArgumentError(f'offset_id {offset_id!r} is not a profile of {station.station_id}')
        usable = False  # explicit selection chooses the held profile over an ordinary recommendation
    blocked_better = historical and offset_id is None and release._better_historical_path(release._by_id[station.station_id])
    mixed_current_path = False
    if quantity == 'current' and set_id is None and current_offsets:
        harmonic_bins = (constants.raw.get('current_bins') or ()) if usable and constants.quantity == 'current' else ()
        effective_bin = bin_number if bin_number is not None else station.raw.get('default_current_bin')
        if effective_bin is None:
            effective_bin = min(row['bin'] for row in harmonic_bins or current_offsets)
        mixed_current_path = (not any(row.get('bin') == effective_bin for row in harmonic_bins)
                              and any(row.get('bin') == effective_bin for row in current_offsets))
    if mixed_current_path or (set_id is None and not usable and station.type == 'subordinate' and ((tide_offsets and not blocked_better) or current_offsets)):
        if tide_offsets:
            if quantity != 'water_level':
                raise X.QuantityMismatchError('tide offsets need water_level')
            kind = tide_offsets.get('height_adjusted_type')
            if kind not in ('R', 'A'):
                raise X.InvalidArgumentError(f'height_adjusted_type {kind!r} is not R or A')
            if historical and release.historical_offsets_policy == 'exclude':
                raise X.HistoricalOffsetsExcludedError('historical_offsets_policy=exclude refuses historical prediction')
            reference, constants = _reference(release, tide_offsets, quantity)
            if historical:
                from .._historical_offsets import require_historical_offset
                require_historical_offset(tide_offsets, policy=release.historical_offsets_policy,
                    licences=release._lic_by_id, selected_reference=constants, better_path=blocked_better,
                    selection='explicit' if offset_id is not None else 'auto', commercial_only=release._commercial_only)
            table = _table(release, constants)
            context = _Context(station, constants, table, reference=reference, offsets=tide_offsets,
                               selected_offset_id=offset_id)
            # Validate all constituents before datum checks.
            Sum(table, constants.raw.get('constituents') or ())
            reference_term = _datum(constants.raw.get('datum'), 'chart', _Context(reference, constants, table), published=True)
            subordinate_term = _subdatum(dict(tide_offsets, datum=_retained_datum(
                release, station, offsets=tide_offsets)), datum, context)
            if offset_id is not None and not historical:
                basis = ((tide_offsets.get('datum') or {}).get('basis') or {}).get(context.datum_name) or {}
                fallback = basis.get('fallback') or {}
                if fallback.get('otc_finding'):
                    context.datum_method = basis.get('method')
                    context.datum_flags = (*context.datum_flags, fallback['otc_finding'])
            high_time, low_time = (tide_offsets.get('time_offset_' + k + '_min', 0.0) or 0.0 for k in ('high', 'low'))
            identity = 1.0 if kind == 'R' else 0.0
            high_height, low_height = (identity if tide_offsets.get('height_offset_' + k) is None else tide_offsets['height_offset_' + k] for k in ('high', 'low'))
            if kind == 'R' and (high_height <= 0 or low_height <= 0):
                raise X.InvalidArgumentError('height_offset ratio must be positive')
            if high_time == low_time and high_height == low_height:
                context.method = 'folded_offsets'
                multiplier = high_height if kind == 'R' else 1.0
                add = high_height if kind == 'A' else 0.0
                context.total = Sum(table, constants.raw.get('constituents') or (), mean=multiplier * reference_term + add + subordinate_term, multiplier=multiplier, shift_hours=high_time / 60.0)
            else:
                context.method = 'offsets'
                context.total = Sum(table, constants.raw.get('constituents') or (), mean=reference_term)
                context.offsets = dict(tide_offsets, _subterm=subordinate_term)
                if series:
                    raise X.ExtremesOnlyError('high and low water offsets differ, so the station has no exact curve')
            return context
        if quantity != 'current':
            raise X.QuantityMismatchError('current offsets need current')
        entry = _bin(station, current_offsets, bin_number)
        reference, constants = _reference(release, entry, quantity, entry.get('reference_bin'))
        table = _table(release, constants)
        context = _Context(station, constants, table, method='offsets', reference=reference, reference_bin=entry.get('reference_bin'), bin_number=entry['bin'], offsets=entry)
        row = _bin(reference, constants.raw.get('current_bins') or (), context.reference_bin)
        _current(context, row)
        if series:
            raise X.ExtremesOnlyError('subordinate currents provide events only')
        return context
    if not usable:
        status = constants.raw.get('qc_status') if constants is not None else None
        raise X.NoConstantsError(f'no usable constants: {status!r}' + (' (commercial_only)' if release._commercial_only else ''))
    if constants.quantity != quantity:
        raise X.QuantityMismatchError(f'{quantity} requires that quantity of constants')
    table = _table(release, constants)
    context = _Context(station, constants, table)
    if quantity == 'water_level':
        context.total = Sum(table, constants.raw.get('constituents') or ())
        context.total.mean = _datum(_retained_datum(release, station, constants), datum, context)
    else:
        row = _bin(station, constants.raw.get('current_bins') or (), bin_number)
        context.bin_number = row['bin']
        _current(context, row)
    return context


_ResultT = TypeVar('_ResultT', HeightSeries, ExtremeList, CurrentSeries, CurrentEventList)

def _result(release, context, cls: type[_ResultT], items, datum=None) -> _ResultT:
    fields: dict[str, Any] = dict(items=tuple(items), station_id=context.station.station_id, timezone=context.station.timezone,
                  method=PredictionMethod(context.method), set_id=context.constants.set_id,
                  convention_id=context.constants.convention.convention_id, astro_table_id=context.table._raw['astro_table_id'],
                  reference_station_id=context.reference.station_id if context.reference is not None else None,
                  reference_bin=context.reference_bin, datum=datum, datum_name=context.datum_name,
                  datum_kind=context.datum_kind, datum_uncertainty_m=context.datum_uncertainty,
                  release=release.datestamp, algorithm='otc-predict-1')
    constructor: Callable[..., _ResultT] = cls
    if cls in (CurrentSeries, CurrentEventList):
        fields['bin_number'] = context.bin_number
    if cls in (HeightSeries, ExtremeList) and context.datum_method:
        fields['source_note'] = '; '.join((f'Retained datum method: {context.datum_method}',
                                          *context.datum_flags))
    if cls in (HeightSeries, ExtremeList) and context.selected_offset_id is not None and context.offsets.get('offset_id') is None:
        fields.update(set_id=None, offset_id=context.selected_offset_id,
                      reference_set_id=context.constants.set_id,
                      reference_source_version=context.constants.source_version)
        fields['source_note'] = '; '.join(filter(None, (
            fields.get('source_note'),
            'OTC subordinate-offset calculation; explicitly selected preserved profile; no transfer to own harmonic model.')))
    if cls is CurrentEventList:
        fields['omitted_event_types'] = context.omitted
    if cls in (HeightSeries, ExtremeList) and context.offsets is not None and context.offsets.get('offset_id') is not None:
        offsets = context.offsets
        vintage = offsets['vintage']
        fields.update(set_id=None, offset_id=offsets['offset_id'], offset_source=offsets['source'],
                      offset_source_version=offsets['source_version'], historical_offsets=True,
                      current_validity=vintage['current_validity'], current_accuracy=vintage['current_accuracy'],
                      reference_set_id=context.constants.set_id, reference_source_version=context.constants.source_version,
                      reference_2020_equivalence=vintage['reference_2020_equivalence'],
                      source_note='OTC historical-offset calculation using NOAA2020 parameters; retired NOAA profile; current validity unestablished; current accuracy unverified.')
    return constructor(**fields)


def heights(release, station, *, start, stop, step_s=600, datum=None, set_id=None, offset_id=None) -> HeightSeries:
    start, stop = _window(start, stop, step_s)
    context = _context(release, station, 'water_level', set_id, datum, series=True, offset_id=offset_id)
    return _result(release, context, HeightSeries, (HeightPoint(utc(t), context.total.value(t)) for t in range(start, stop, step_s)), datum)


def heights_at(release, station, times, *, datum=None, set_id=None, offset_id=None) -> HeightSeries:
    if isinstance(times, (str, bytes)) or not isinstance(times, Sequence):
        raise X.InvalidArgumentError('times must be a sequence of aware datetimes')
    seconds = [instant(t) for t in times]
    context = _context(release, station, 'water_level', set_id, datum, series=True, offset_id=offset_id)
    return _result(release, context, HeightSeries, (HeightPoint(utc(t), context.total.value(t)) for t in seconds), datum)


def extremes(release, station, *, start, stop, datum=None, set_id=None, offset_id=None) -> ExtremeList:
    start, stop = _window(start, stop)
    context = _context(release, station, 'water_level', set_id, datum, offset_id=offset_id)
    if context.method == 'offsets' and start != stop:
        offsets = context.offsets
        margin = max(120.0, max(abs(offsets.get('time_offset_high_min') or 0), abs(offsets.get('time_offset_low_min') or 0)) + 60.0) * 60.0
        candidates = events(context.total, start - margin, stop + margin)
        shifted = []
        for root, kind, value in candidates:
            time = root + (offsets.get('time_offset_' + kind + '_min') or 0) * 60.0
            height = offsets.get('height_offset_' + kind)
            if offsets['height_adjusted_type'] == 'R':
                value *= 1.0 if height is None else height
            else:
                value += 0.0 if height is None else height
            shifted.append((time, kind, value + offsets['_subterm']))
        candidates = sorted(shifted, key=lambda c: math.floor(c[0] + 0.5))
    else:
        candidates = events(context.total, start, stop)
    items = [Extreme(utc(math.floor(t + 0.5)), ExtremeType(kind), value) for t, kind, value in candidates if start <= math.floor(t + 0.5) < stop]
    return _result(release, context, ExtremeList, items, datum)


def _unrounded_current_events(context, start, stop, *, event_source=_unrounded_events):
    # W is flood-positive, while U/V retain the geographic axis orientation.
    total = Sum(context.table, context.current_bin.get('constituents') or (), amplitude='major_amplitude_ms', phase='major_phase_deg', multiplier=context.sigma, mean=context.sigma * context.current_bin.get('mean_major_ms', 0.0))
    candidates = []
    for t, kind, value in event_source(total, start, stop):
        if kind == 'high' and value > 0:
            candidates.append((t, 'max_flood', value, context.current_bin.get('mean_flood_dir_deg')))
        elif kind == 'low' and value < 0:
            candidates.append((t, 'max_ebb', value, context.current_bin.get('mean_ebb_dir_deg')))
    candidates.extend((t, kind, 0.0, None) for t, kind, value in event_source(total, start, stop, slack=True))
    return sorted(candidates, key=lambda c: c[0])


def _current_events(context, start, stop):
    return [c for c in _unrounded_current_events(context, start, stop)
            if start <= math.floor(c[0] + 0.5) < stop]


def currents(release, station, *, start, stop, step_s=600, bin_number=None, set_id=None) -> CurrentSeries:
    start, stop = _window(start, stop, step_s)
    context = _context(release, station, 'current', set_id, bin_number=bin_number, series=True)
    theta = context.current_bin.get('azimuth_deg', 0.0) * RAD
    items = []
    for t in range(start, stop, step_s):
        major, minor = context.total.value(t), context.minor.value(t)
        east = major * math.sin(theta) + minor * math.sin(theta + math.pi / 2.0)
        north = major * math.cos(theta) + minor * math.cos(theta + math.pi / 2.0)
        speed = math.hypot(east, north)
        direction = None if speed < 1e-9 else angle(math.atan2(east, north) / RAD)
        items.append(CurrentPoint(utc(t), context.sigma * major, context.sigma * minor, speed, direction))
    return _result(release, context, CurrentSeries, items)


def current_events(release, station, *, start, stop, bin_number=None, set_id=None) -> CurrentEventList:
    start, stop = _window(start, stop)
    context = _context(release, station, 'current', set_id, bin_number=bin_number)
    if context.method == 'offsets':
        entry = context.offsets
        kinds = ('max_flood', 'max_ebb', 'slack_before_flood', 'slack_before_ebb')
        kept = [kind for kind in kinds if entry.get('time_adj_' + kind + '_min') is not None and (kind.startswith('slack') or entry.get('flood_amp_ratio' if kind == 'max_flood' else 'ebb_amp_ratio') is not None)]
        context.omitted = tuple(CurrentEventType(k) for k in kinds if k not in kept)
        margin = max(120.0, max((abs(entry['time_adj_' + kind + '_min']) for kind in kept), default=0.0) + 60.0) * 60.0
        candidates = _current_events(context, start - margin, stop + margin) if start != stop else []
        shifted = []
        for root, kind, value, direction in candidates:
            if kind not in kept:
                continue
            time = root + entry['time_adj_' + kind + '_min'] * 60.0
            if kind in ('max_flood', 'max_ebb'):
                value *= entry['flood_amp_ratio' if kind == 'max_flood' else 'ebb_amp_ratio']
                direction = entry.get('mean_flood_dir_deg' if kind == 'max_flood' else 'mean_ebb_dir_deg')
            shifted.append((time, kind, value, direction))
        candidates = sorted(shifted, key=lambda c: math.floor(c[0] + 0.5))
    else:
        candidates = _current_events(context, start, stop)
    items = [CurrentEvent(utc(math.floor(t + 0.5)), CurrentEventType(kind), value, direction) for t, kind, value, direction in candidates if start <= math.floor(t + 0.5) < stop]
    return _result(release, context, CurrentEventList, items)


def _datum_info(set_id, d):
    d = d or {}
    named, basis = d.get('named') or {}, d.get('basis') or {}
    chart = named.get(d.get('chart_datum'))
    levels = []
    for key in sorted(named):
        b = basis.get(key) or {}
        control = b.get('control') or {}
        levels.append(DatumLevel(key, named[key], None if chart is None else named[key] - chart,
                                b.get('kind'), b.get('method'), b.get('source_name'), freeze(b.get('epoch')),
                                freeze(b.get('data_span')), control.get('station_id'), control.get('set_id'), control.get('source_id'),
                                b.get('uncertainty_m'), b.get('uncertainty_basis'), tuple(b.get('flags') or ()),
                                fallback=b.get('fallback')))
    return DatumInfo(set_id, d.get('zero'), d.get('zero_name'), d.get('chart_datum'), d.get('msl_offset_m'), tuple(levels))


def datums(release, station, set_id=None, all_sets=False) -> DatumInfo | tuple[DatumInfo, ...] | None:
    station = _station(release, station)
    _options(set_id)
    _validate_all_sets(all_sets)
    if all_sets:
        infos = tuple(_datum_info(s.set_id, _retained_datum(release, station, s))
                      for s in station.constant_sets(include_no_constants=True))
        offsets = station.raw.get('subordinate_offsets')
        if offsets:
            effective = _retained_datum(release, station, offsets=offsets)
            if any(b.get('_retained') for b in effective['basis'].values()):
                return infos + (_datum_info(None, effective),)
        return infos
    constants = _chosen(release, station, set_id)
    if constants is not None:
        return _datum_info(constants.set_id, _retained_datum(release, station, constants))
    offsets = station.raw.get('subordinate_offsets')
    return _datum_info(None, _retained_datum(release, station, offsets=offsets)) if offsets else None


def ranges(release, station, set_id=None) -> Ranges:
    info = datums(release, station, set_id)
    levels = {l.key: l for l in info.levels} if isinstance(info, DatumInfo) else {}
    def difference(a, b):
        high, low = levels.get(a), levels.get(b)
        if high is None or low is None or high.value_m is None or low.value_m is None or high.kind is None or high.kind != low.kind or high.epoch != low.epoch:
            return None
        return high.value_m - low.value_m
    return Ranges(difference('mhw', 'mlw'), difference('mhhw', 'mllw'), difference('mhhw', 'mhw'), difference('mlw', 'mllw'))
