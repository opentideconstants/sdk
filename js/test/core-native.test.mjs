import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import * as sdk from '../dist/index.js';

const file = process.env.OTC_CORE_NATIVE_JSON;
const jsonl = process.env.OTC_CORE_NATIVE_JSONL;
let client, raw;
before(async () => {
    assert.ok(file && jsonl, 'actual pinned H4 paths required');
    raw = JSON.parse(fs.readFileSync(file, 'utf8'));
    client = await sdk.OpenTideConstants.open({ file });
});
after(() => client?.close());

for (const id of ['OTC-28c56e20', 'OTC-541f1a73']) {
    test(`actual H4 ${id} historical typed labels and original source`, () => {
        const original = raw.stations.find(s => s.station_id === id);
        // The second target is resolved by its actual legacy alias, never invented.
        const input = original ?? raw.stations.find(s => s.subordinate_offsets?.offset_id === 'noaa-2020-pacific-table2-517');
        const station = client.requireStation(input.station_id);
        assert.deepEqual(station.raw, input);
        assert.equal(station.subordinateOffsets.offset_id, input.subordinate_offsets.offset_id);
        assert.deepEqual(station.subordinateOffsets.vintage, input.subordinate_offsets.vintage);
        assert.deepEqual(station.source_records.map(s => s.raw), input.source_records);
        assert.ok(Object.isFrozen(station.source_records[0].raw.provenance));
    });
}

test('actual H4 quality discovery counts preserve lookup and full sources', () => {
    assert.equal(client.release.stationCount, 16038);
    assert.equal(client.stations().length, 6715);
    assert.equal(client.stations({includeFlagged: true}).length, 9528);
    assert.equal(client.stations({includeFallback: true}).length, 9549);
    assert.equal(client.stations({includeFlagged: true, includeFallback: true}).length, 10002);
    const ids = new Set(client.stations().map(s => s.station_id));
    for (const input of raw.stations.filter(s => s.constant_sets?.some(cs => cs.fallback)).slice(0, 3)) {
        assert.equal(ids.has(input.station_id), false, input.station_id);
        assert.deepEqual(client.requireStation(input.station_id).source_records.map(s => s.raw), input.source_records);
    }
});

test('actual H4 every source/raw original harmonic document conserved', () => {
    let count = 0, fits = 0, histories = 0, cells = 0;
    for (const input of raw.stations) {
        const station = client.requireStation(input.station_id);
        assert.deepEqual(station.raw, input);
        assert.deepEqual(station.source_records.map(s => s.raw), input.source_records);
        for (const source of station.source_records) {
            count++;
            const harmonics = source.original_harmonics;
            if (harmonics?.format === 'ticon-4-csv') cells += harmonics.rows.flat().length;
            if (source.original_metadata.original_fit_json) fits++;
            if (source.original_metadata.historical_original_fit_documents_json) histories += JSON.parse(source.original_metadata.historical_original_fit_documents_json).length;
        }
    }
    assert.equal(count, 27372);
    assert.equal(fits, 1543);
    assert.equal(histories, 9);
    assert.equal(cells, 4354200);
    console.log(JSON.stringify({count, fits, histories, cells}));
});

test('actual historical profile malformed own fields refused, flags are boolean, strict retains metadata', async () => {
    const { releaseFromJson } = await import('../dist/loader.js');
    const input = raw.stations.find(s => s.station_id === 'OTC-28c56e20');
    const reference = raw.stations.find(s => s.station_id === input.subordinate_offsets.reference_station_id);
    const document = { ...raw, stations: [input, reference] };
    const load = d => releaseFromJson(new TextEncoder().encode(JSON.stringify(d)), []);
    for (const [key,value] of [['time_offset_high_min',99],['qc_status','ok'],['offset_id','unknown'],['source',false]]) {
        const changed = structuredClone(document);
        changed.stations[0].subordinate_offsets[key]=value;
        assert.throws(() => load(changed), e => e.code==='invalid_release', key);
    }
    const missing=structuredClone(document);
    delete missing.stations[0].subordinate_offsets.vintage;
    assert.throws(() => load(missing), e => e.code==='invalid_release');
    for (const value of [null,1,'true']) assert.throws(()=>client.stations({includeFlagged:value}),e=>e.code==='invalid_argument');
    const strict=releaseFromJson(new TextEncoder().encode(JSON.stringify(document)), [], null, () => undefined, false, 'strict', 'exclude');
    assert.ok(strict.station(input.station_id));
    assert.equal(strict.stations().some(s=>s.station_id===input.station_id),false);
    strict._close();
});

test('actual full H4 stream keeps every source and the same four discovery policies', async () => {
    const stream=await sdk.OpenTideConstants.open({file:jsonl,mode:'stream'});
    try {
        assert.equal(stream.stations().length,6715);
        assert.equal(stream.stations({includeFlagged:true}).length,9528);
        assert.equal(stream.stations({includeFallback:true}).length,9549);
        assert.equal(stream.stations({includeFlagged:true,includeFallback:true}).length,10002);
        let records=0;
        for (const input of raw.stations) {
            const station=stream.requireStation(input.station_id);
            assert.deepEqual(station.raw,input);
            assert.deepEqual(station.source_records.map(r=>r.raw),input.source_records);
            records+=station.source_records.length;
        }
        assert.equal(records,27372);
    } finally { stream.close(); }
});
