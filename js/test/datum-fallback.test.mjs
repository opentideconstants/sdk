import {test, before, after} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import * as sdk from '../dist/index.js';
import {datumTerm} from '../dist/predict/engine.js';

assert.ok(process.env.OTC_DATUM_FALLBACK_CONTRACT, 'actual native datum fallback contract required');
const bytes = fs.readFileSync(process.env.OTC_DATUM_FALLBACK_CONTRACT);
const contract = JSON.parse(bytes);
const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'otc-datum-fallback-'));
let client, original;
before(async () => {
    const file = path.join(directory, 'OTC_20261011.json');
    fs.writeFileSync(file, JSON.stringify(contract.release_fixture));
    client = await sdk.OpenTideConstants.open({file});
    const originalFile = path.join(directory, 'original', 'OTC_20261011.json');
    fs.mkdirSync(path.dirname(originalFile));
    fs.writeFileSync(originalFile, JSON.stringify({...contract.release_fixture, stations: contract.original_stations}));
    original = await sdk.OpenTideConstants.open({file: originalFile});
});
after(() => {
    client?.close();
    original?.close();
    fs.rmSync(directory, {recursive: true, force: true});
});

function checkLevels(info, datum) {
    assert.ok(info instanceof sdk.DatumInfo);
    const named = datum.named ?? {};
    assert.deepEqual(info.levels.map(level => level.key), Object.keys(named).sort());
    for (const level of info.levels) {
        const basis = datum.basis?.[level.key];
        assert.equal(level.value_m, named[level.key]);
        assert.equal(level.above_chart_m, datum.chart_datum ? level.value_m - named[datum.chart_datum] : null);
        assert.equal(level.kind, basis?.kind ?? null);
        assert.equal(level.method, basis?.method ?? null);
        assert.equal(level.source_name, basis?.source_name ?? null);
        assert.deepEqual(level.epoch, basis?.epoch ?? null);
        assert.deepEqual(level.data_span, basis?.data_span ?? null);
        assert.equal(level.control_station_id, basis?.control?.station_id ?? null);
        assert.equal(level.control_set_id, basis?.control?.set_id ?? null);
        assert.equal(level.control_source_id, basis?.control?.source_id ?? null);
        assert.equal(level.uncertainty_m, basis?.uncertainty_m ?? null);
        assert.equal(level.uncertainty_basis, basis?.uncertainty_basis ?? null);
        assert.deepEqual(level.flags, basis?.flags ?? []);
        assert.deepEqual(level.fallback ?? null, basis?.fallback ?? null, `${info.set_id}/${level.key} fallback`);
        if (level.fallback) assert.ok(Object.isFrozen(level.fallback));
    }
}

for (const candidate of contract.cases) {
    test(`public datums preserves native fallback ${candidate.source_record_id}`, async () => {
        const station = client.requireStation(candidate.station_id);
        const priorStation = original.requireStation(candidate.station_id);
        const ranked = station.constantSets({includeNoConstants: true}).map(set => set.set_id);
        assert.deepEqual(ranked, priorStation.constantSets({includeNoConstants: true}).map(set => set.set_id));
        assert.equal(station.recommendedSet.set_id, priorStation.recommendedSet.set_id);
        assert.equal(station.recommendedSet.set_id, candidate.recommended_set_id);
        const times = [new Date('2026-10-11T00:00:00Z'), new Date('2026-10-11T06:00:00Z')];
        const prediction = await client.heightsAt(candidate.station_id, times);
        assert.deepEqual(prediction, await original.heightsAt(candidate.station_id, times));
        const selected = client.datums(candidate.station_id);
        console.log(JSON.stringify({station_id: candidate.station_id, set_id: selected.set_id,
            contract_sha256: createHash('sha256').update(bytes).digest('hex'),
            fallback: selected.levels.filter(level => candidate.datum.basis[level.key]?.fallback)
                .map(level => ({key: level.key, value_m: level.value_m, actual: level.fallback ?? null,
                    expected: candidate.datum.basis[level.key].fallback})),
            ranking_unchanged: true, predictions_unchanged: true}));
        checkLevels(selected, candidate.datum);
        checkLevels(client.datums(candidate.station_id, {setId: candidate.set_id}), candidate.datum);
        const all = client.datums(candidate.station_id, {allSets: true});
        assert.deepEqual(all.map(info => info.set_id), ranked);
        for (const info of all) {
            checkLevels(info, station.raw.constant_sets.find(set => set.set_id === info.set_id).datum ?? {named: {}});
        }
    });
}

function datumFields() {
    return {key: 'lat', value_m: -0.2, above_chart_m: null, kind: 'computed', method: 'harmonic_extremes',
        source_name: null, epoch: null, data_span: null, control_station_id: null, control_set_id: null,
        control_source_id: null, uncertainty_m: null, uncertainty_basis: null, flags: []};
}

test('DatumLevel accepts existing constructor fields and deeply freezes complete fallback JSON', () => {
    assert.equal(new sdk.DatumLevel(datumFields()).fallback, null);
    const fallback = {reason: 'datum_gate_failed', basis: 'native basis', otc_finding: 'native finding',
        future: {evidence: ['preserved', {detail: true}]}};
    const level = new sdk.DatumLevel({...datumFields(), fallback});
    assert.deepEqual(level.fallback, fallback);
    assert.ok(Object.isFrozen(level.fallback));
    assert.ok(Object.isFrozen(level.fallback.future));
    assert.ok(Object.isFrozen(level.fallback.future.evidence));
    assert.ok(Object.isFrozen(level.fallback.future.evidence[1]));
    assert.throws(() => { level.fallback.future.evidence.push('changed'); }, TypeError);
});

test('explicit harmonic mean resolves named and own-zero terms without an absolute tie', () => {
    const raw = {zero: 'harmonic_mean', named: {lat: -2, hat: 3},
        basis: {lat: {kind: 'computed'}, hat: {kind: 'computed'}}};
    for (const [datum, expected] of [['mean_level', 0], ['zero', 0], ['lat', 2], ['hat', -3]]) {
        const context = {};
        assert.equal(datumTerm(raw, datum, context), expected);
        assert.equal(context.datumName, datum === 'zero' ? 'harmonic_mean' : datum);
        if (datum === 'lat' || datum === 'hat') {
            assert.equal(context.datumKind, 'computed');
            assert.equal(context.datumUncertainty, null);
        }
    }
    assert.throws(() => datumTerm(raw, 'chart', {}), error => error.code === 'datum_unavailable' && error.missing === 'chart_datum');
    assert.throws(() => datumTerm(raw, 'missing', {}), error => error.code === 'datum_unavailable' && error.missing === 'missing');
    assert.throws(() => datumTerm(raw, 'lat', {}, true), error => error.code === 'datum_unavailable' && error.missing === 'msl_offset_m');
});

test('absolute and unspecified frames retain their MSL requirement and existing offsets', () => {
    for (const zero of [undefined, 'unknown', 'msl']) {
        const raw = {zero, named: {lat: -2}, basis: {lat: {kind: 'published', uncertainty_m: 0.1}}};
        assert.equal(datumTerm(raw, 'mean_level', {}), 0);
        for (const datum of ['zero', 'lat', 'chart']) {
            assert.throws(() => datumTerm(raw, datum, {}), error => error.code === 'datum_unavailable' && error.missing === 'msl_offset_m');
        }
        const context = {};
        assert.equal(datumTerm({...raw, msl_offset_m: 0.5}, 'lat', context), 2.5);
        assert.equal(context.datumUncertainty, 0.1);
    }
});

test('actual TICON harmonic-mean named heights preserve eager and stream baselines and event times',
    {skip: !process.env.OTC_HARMONIC_MEAN_NATIVE && 'computed native TICON witness release required'}, async () => {
    assert.ok(process.env.OTC_HARMONIC_MEAN_ORIGINAL, 'original native TICON witness release required');
    const document = JSON.parse(fs.readFileSync(process.env.OTC_HARMONIC_MEAN_NATIVE));
    const prior = JSON.parse(fs.readFileSync(process.env.OTC_HARMONIC_MEAN_ORIGINAL));
    const witnesses = [
        ['OTC-666303b1', 'OTC-666303b1/ticon-4/aberdeen-abe-gbr-bodc'],
        ['OTC-215da48c', 'OTC-215da48c/ticon-4/acadia_cove-4170-can-meds/as-published'],
        ['OTC-52fc4ff5', 'OTC-52fc4ff5/ticon-4/aero_trading-9338-can-meds'],
    ];
    const times = [0, 6, 12].map(hour => new Date(Date.UTC(2026, 9, 11, hour)));
    const window = {start: times[0], stop: new Date('2026-10-13T00:00:00Z')};
    for (const mode of ['eager', 'stream']) {
        const file = path.join(directory, `OTC_20261011.${mode === 'eager' ? 'json' : 'jsonl'}`);
        if (mode === 'eager') fs.writeFileSync(file, JSON.stringify(document));
        else {
            fs.writeFileSync(file, document.stations.map(row => JSON.stringify(row) + '\n').join(''));
            fs.writeFileSync(path.join(directory, 'OTC_20261011.meta.json'), JSON.stringify({...document, stations: undefined}));
        }
        const opened = await sdk.OpenTideConstants.open({file, mode});
        const originalFile = path.join(directory, 'ticon-original', 'OTC_20261011.json');
        fs.mkdirSync(path.dirname(originalFile), {recursive: true});
        fs.writeFileSync(originalFile, JSON.stringify(prior));
        const baseline = await sdk.OpenTideConstants.open({file: originalFile});
        try {
            for (const [id, setId] of witnesses) {
                const raw = document.stations.find(row => row.station_id === id).constant_sets.find(set => set.set_id === setId);
                const old = prior.stations.find(row => row.station_id === id).constant_sets.find(set => set.set_id === setId);
                assert.deepEqual(raw.constituents, old.constituents);
                assert.deepEqual(raw.fallback, old.fallback);
                assert.equal(opened.requireStation(id).recommendedSet.set_id, baseline.requireStation(id).recommendedSet.set_id);
                const mean = await opened.heightsAt(id, times, {setId, datum: 'mean_level'});
                assert.deepEqual(mean, await baseline.heightsAt(id, times, {setId, datum: 'mean_level'}));
                checkLevels(opened.datums(id, {setId}), raw.datum);
                const meanEvents = await opened.extremes(id, {...window, setId, datum: 'mean_level'});
                const zero = await opened.heightsAt(id, times, {setId, datum: 'zero'});
                assert.deepEqual(zero.items, mean.items);
                assert.equal(zero.datum_name, 'harmonic_mean');
                for (const datum of ['lat', 'hat']) {
                    const named = await opened.heightsAt(id, times, {setId, datum});
                    assert.equal(named.datum_kind, 'computed');
                    assert.equal(named.datum_uncertainty_m, null);
                    named.items.forEach((point, i) => assert.ok(Math.abs(point.height_m - mean.items[i].height_m + raw.datum.named[datum]) < 1e-12));
                    const events = await opened.extremes(id, {...window, setId, datum});
                    assert.equal(events.items.length, meanEvents.items.length);
                    events.items.forEach((event, i) => {
                        assert.deepEqual(event.time, meanEvents.items[i].time);
                        assert.equal(event.type, meanEvents.items[i].type);
                        assert.ok(Math.abs(event.height_m - meanEvents.items[i].height_m + raw.datum.named[datum]) < 1e-12);
                    });
                }
            }
        } finally {opened.close(); baseline.close();}
    }
});
