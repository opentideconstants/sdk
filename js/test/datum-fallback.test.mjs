import {test, before, after} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import * as sdk from '../dist/index.js';

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
