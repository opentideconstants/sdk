import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import http, { createServer } from 'node:http';
import { syncBuiltinESMExports } from 'node:module';
import * as sdk from '../dist/index.js';
import * as streamLoader from '../dist/loader.js';
import * as nodeRuntime from '../dist/node.js';
import { checkBytes, syncZenodo } from '../dist/core.js';
import { encodeCacheJson } from '../dist/cache-json.js';

// SC18 is a private forward-format control over the existing knc station. It is not upstream science data.
for (const mode of ['eager', 'stream']) {
    for (const [label, originalQuantity, replacementQuantity, expected] of [
        ['known-same', 'water_level', 'water_level', 'OTC-T-0181/w-ok'],
        ['null', null, 'water_level', null],
        ['distinct-unknown', 'future_quantity_a', 'future_quantity_b', 'OTC-T-0181/w-ok'],
        ['known-different', 'water_level', 'current', null],
    ]) {
        test(`COMMON-TS SC18 public restricted replacement ${mode}/${label}`, async () => {
            const source = fs.readFileSync(new URL('../../conformance/fixtures/knc/OTC_20991231.2.json', import.meta.url));
            const document = JSON.parse(source);
            const original = document.stations.find(station => station.station_id === 'OTC-T-0181');
            assert.ok(original);
            original.constant_sets.find(set => set.set_id === original.recommended_set_id).quantity = originalQuantity;
            for (const set of original.constant_sets) if (set.set_id !== original.recommended_set_id) set.quantity = replacementQuantity;
            const root = fs.mkdtempSync(path.join(process.env.OTC_COMMON_PROOF ?? os.tmpdir(), `common-ts-${mode}-${label}-`));
            const meta = { ...document }; delete meta.stations;
            const input = Buffer.from(mode === 'eager' ? JSON.stringify(document) :
                document.stations.map(station => JSON.stringify(station)).join('\n') + '\n');
            const filename = path.join(root, `OTC_20991231.2.${mode === 'eager' ? 'json' : 'jsonl'}`);
            fs.writeFileSync(filename, input);
            if (mode === 'stream') fs.writeFileSync(path.join(root, 'OTC_20991231.2.meta.json'), JSON.stringify(meta));
            let opened;
            try {
                opened = await sdk.OpenTideConstants.open({ file: filename, mode, commercialOnly: true });
                const station = opened.requireStation(original.station_id);
                const actual = station.recommendedSet?.set_id ?? null;
                console.log(JSON.stringify({ scenario: 'SC18', control: label, mode,
                    source_sha256: nodeRuntime.sha256Sync(source), input_sha256: nodeRuntime.sha256Sync(input),
                    source_path: filename, raw_quantities: station.raw.constant_sets.map(set => set.quantity),
                    typed_quantities: station.constantSets().map(set => set.quantity), actual, expected,
                    ordered_sets: station.constantSets().map(set => set.set_id), loaded_from: opened.loadedFrom }));
                assert.equal(actual, expected);
                assert.deepEqual(station.raw, original);
                assert.equal(station.constantSets().filter(set => set.isRecommended).length, expected === null ? 0 : 1);
                if (expected !== null) assert.equal(station.constantSets()[0].set_id, expected);
            } finally {
                opened?.close();
                if (!process.env.OTC_COMMON_PROOF) fs.rmSync(root, { recursive: true, force: true });
            }
        });
    }
}

test('COMMON-TS SC15 own and foreign identical raw station guards', async () => {
    const fixture = new URL('../../conformance/fixtures/good/OTC_20991231.2.json', import.meta.url).pathname;
    const own = await sdk.OpenTideConstants.open({ file: fixture });
    const foreign = await sdk.OpenTideConstants.open({ file: fixture });
    try {
        const ownStation = own.requireStation('OTC-T-0001');
        const foreignStation = foreign.requireStation('OTC-T-0001');
        assert.deepEqual(ownStation.raw, foreignStation.raw);
        const ownText = own.attribution([ownStation]);
        let refused;
        try { own.attribution([foreignStation]); } catch (error) { refused = error; }
        console.log(JSON.stringify({ scenario: 'SC15', own_attribution: ownText,
            foreign_code: refused?.code, foreign_message: refused?.message, identical_raw: true }));
        assert.equal(refused?.code, 'invalid_argument');
        assert.ok(ownText.includes('OpenTideConstants'));
        assert.deepEqual(ownStation.source_records.map(record => record.raw), ownStation.raw.source_records ?? []);
    } finally { own.close(); foreign.close(); }
});

for (const [label, tag, expectedHeader] of [
    ['unquoted', 'not-an-entity-tag', 'not-an-entity-tag'], ['control', '"bad\u0000tag"', null],
    ['empty', '', null],
    ['trailing-crlf', '"native-strong"\r\n', null],
    ['non-ascii', '"native-\u00ff"', null],
    ['oversize', `"${'a'.repeat(255)}"`, null],
    ['delete-byte', '"native-\u007f"', null],
    ['valid-strong', '"native-strong"', '"native-strong"'], ['valid-weak', 'W/"native-weak"', 'W/"native-weak"'],
    ['valid-opaque', 'W/"native\\opaque-!#$%"', 'W/"native\\opaque-!#$%"'],
    ['valid-interior-space', '"native opaque"', '"native opaque"'],
    ['valid-edge-spaces', ' native opaque ', ' native opaque '],
    ['valid-256-bytes', `"${'a'.repeat(254)}"`, `"${'a'.repeat(254)}"`],
]) {
    test(`COMMON-TS SC03 public cached ETag ${label}`, async () => {
        const source = new URL('../../conformance/fixtures/good/', import.meta.url).pathname;
        const root = fs.mkdtempSync(path.join(process.env.OTC_COMMON_PROOF ?? os.tmpdir(), `common-etag-${label}-`));
        const requests = [];
        const nativeHeaders = [];
        const originalGet = http.get;
        const server = createServer((request, response) => {
            requests.push({ path: request.url, if_none_match: request.headers['if-none-match'] ?? null });
            const filename = path.join(source, request.url.slice(1));
            if (!fs.existsSync(filename)) { response.writeHead(404); response.end(); return; }
            if (request.url === '/OTC_latest-f1.json') response.setHeader('ETag', '"valid-original"');
            if (request.url === '/OTC_latest-f1.json' && expectedHeader !== null && request.headers['if-none-match'] === expectedHeader.trim()) {
                response.writeHead(304); response.end(); return;
            }
            response.end(fs.readFileSync(filename));
        });
        await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
        const options = { cacheDir: root, baseUrl: `http://127.0.0.1:${server.address().port}/` };
        let opened;
        try {
            opened = await sdk.OpenTideConstants.open(options);
            opened.close(); opened = undefined;
            const etag = path.join(root, 'v1/pointer/OTC_latest-f1.json.etag');
            fs.writeFileSync(etag, tag);
            const beforePointer = fs.readFileSync(path.join(root, 'v1/pointer/OTC_latest-f1.json'));
            requests.length = 0;
            http.get = function (...args) {
                const request = originalGet.apply(this, args);
                nativeHeaders.push({ path: request.path, if_none_match: request.getHeader('If-None-Match') ?? null });
                return request;
            };
            syncBuiltinESMExports();
            let error;
            try { opened = await sdk.OpenTideConstants.open({ ...options, onNetworkError: 'raise' }); }
            catch (failure) { error = failure; }
            console.log(JSON.stringify({ scenario: 'SC03', control: label, cached_tag: tag, requests, nativeHeaders,
                code: error?.code ?? null, message: error?.message ?? null,
                actual_datestamp: opened?.release.datestamp ?? null, expected_datestamp: '20991231.2',
                pointer_sha256: nodeRuntime.sha256Sync(fs.readFileSync(path.join(root, 'v1/pointer/OTC_latest-f1.json'))) }));
            assert.equal(error, undefined, 'invalid cached ETag must be ignored before native header construction');
            assert.equal(opened.release.datestamp, '20991231.2');
            assert.equal(nativeHeaders.find(request => request.path === '/OTC_latest-f1.json').if_none_match, expectedHeader);
            assert.equal(requests.find(request => request.path === '/OTC_latest-f1.json').if_none_match, expectedHeader?.trim() ?? null);
            assert.deepEqual(fs.readFileSync(path.join(root, 'v1/pointer/OTC_latest-f1.json')), beforePointer);
            if (expectedHeader !== null) assert.equal(fs.readFileSync(etag, 'utf8'), tag);
        } finally {
            http.get = originalGet; syncBuiltinESMExports();
            opened?.close();
            await new Promise(resolve => server.close(resolve));
            if (!process.env.OTC_COMMON_PROOF) fs.rmSync(root, { recursive: true, force: true });
        }
    });
}

test('COMMON-TS SC03 public ETag body ETag race suppresses the conditional header', async () => {
    const source = new URL('../../conformance/fixtures/good/', import.meta.url).pathname;
    const root = fs.mkdtempSync(path.join(process.env.OTC_COMMON_PROOF ?? os.tmpdir(), 'common-etag-race-'));
    const requests = [];
    const server = createServer((request, response) => {
        requests.push({ path: request.url, if_none_match: request.headers['if-none-match'] ?? null });
        const filename = path.join(source, request.url.slice(1));
        if (!fs.existsSync(filename)) { response.writeHead(404); response.end(); return; }
        if (request.url === '/OTC_latest-f1.json') response.setHeader('ETag', '"valid-original"');
        response.end(fs.readFileSync(filename));
    });
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    const options = { cacheDir: root, baseUrl: `http://127.0.0.1:${server.address().port}/` };
    const originalRead = fs.readFileSync;
    let opened;
    try {
        opened = await sdk.OpenTideConstants.open(options); opened.close(); opened = undefined;
        const bodyPath = path.join(root, 'v1/pointer/OTC_latest-f1.json');
        const etagPath = `${bodyPath}.etag`;
        const events = [];
        fs.readFileSync = function (filename, ...args) {
            const value = originalRead.call(this, filename, ...args);
            if (filename === etagPath) events.push(['etag', value.toString()]);
            if (filename === bodyPath) {
                events.push(['body', nodeRuntime.sha256Sync(value)]);
                fs.writeFileSync(etagPath, '"changed-between-reads"');
            }
            return value;
        };
        syncBuiltinESMExports(); requests.length = 0;
        opened = await sdk.OpenTideConstants.open(options);
        fs.readFileSync = originalRead; syncBuiltinESMExports();
        console.log(JSON.stringify({ scenario: 'SC03', control: 'etag-body-etag-race', events, requests,
            actual_datestamp: opened.release.datestamp }));
        assert.deepEqual(events.slice(0, 3).map(event => event[0]), ['etag', 'body', 'etag']);
        assert.notEqual(events[0][1], events[2][1]);
        assert.equal(requests.find(request => request.path === '/OTC_latest-f1.json').if_none_match, null);
    } finally {
        fs.readFileSync = originalRead; syncBuiltinESMExports();
        opened?.close(); await new Promise(resolve => server.close(resolve));
        if (!process.env.OTC_COMMON_PROOF) fs.rmSync(root, { recursive: true, force: true });
    }
});

test('COMMON-TS SC01 public argument precedence before cache effects', async () => {
    const parent = fs.mkdtempSync(path.join(process.env.OTC_COMMON_PROOF ?? os.tmpdir(), 'common-options-'));
    const cacheDir = path.join(parent, 'must-stay-absent');
    try {
        for (const [options, expectedMessage] of [
            [{ release: 'invalid', mode: 'invalid', timeout: -1, cacheDir }, /datestamp/],
            [{ file: '/missing/OTC_20991231.json', offline: true, timeout: 30, cacheDir }, /file cannot be combined/],
        ]) {
            let error;
            try { await sdk.OpenTideConstants.open(options); } catch (failure) { error = failure; }
            console.log(JSON.stringify({ scenario: 'SC01', options, code: error?.code, message: error?.message,
                cache_exists: fs.existsSync(cacheDir) }));
            assert.equal(error?.code, 'invalid_argument');
            assert.match(error.message, expectedMessage);
            assert.equal(fs.existsSync(cacheDir), false);
        }
    } finally { if (!process.env.OTC_COMMON_PROOF) fs.rmSync(parent, { recursive: true, force: true }); }
});

const file = process.env.OTC_CORE_NATIVE_JSON;
const jsonl = process.env.OTC_CORE_NATIVE_JSONL;
let client, raw;
before(async () => {
    if (process.env.OTC_CORE_NATIVE_HEADER_ONLY === '1') return;
    assert.ok(file && jsonl, 'actual pinned H4 paths required');
    raw = JSON.parse(fs.readFileSync(file, 'utf8'));
    const activeSdk = process.env.OTC_CORE_NATIVE_SDK ? await import(process.env.OTC_CORE_NATIVE_SDK) : sdk;
    client = await activeSdk.OpenTideConstants.open({ file });
});
after(() => client?.close());

// Exercise the actual read-modify-write receipt producer and native atomic disk writer.
// These finite expectations come from the independently accepted B28 foundation.
const cacheGoldens = JSON.parse(fs.readFileSync(new URL('../../conformance/canonical/cache-golden.json', import.meta.url)));
function cacheGoldenInput(vector) {
    return vector.binary64_hex ? Buffer.from(vector.binary64_hex, 'hex').readDoubleBE()
        : vector.raw_json_hex ? JSON.parse(Buffer.from(vector.raw_json_hex, 'hex').toString('utf8')) : vector.input;
}
async function nativeReceiptEncoding(vector, body) {
    const root = fs.mkdtempSync(path.join(process.env.OTC_CACHE_ENCODING_PROOF_ROOT ?? os.tmpdir(), 'otc-cache-encoding-'));
    const platform = nodeRuntime.nodePlatform();
    const store = await platform.cache(root);
    const verified = { extension: cacheGoldenInput(vector), files: {}, verified_at: '2026-10-11T00:00:00Z',
        by: 'native-encoding', datestamp: '20261011', format_version: '1.0', zenodo_version_doi: null };
    const receipt = 'releases/20261011/.verified';
    await store.mkdirs('releases/20261011');
    const original = Buffer.from(JSON.stringify(verified));
    await store.write(receipt, original);
    const warnings = [];
    try {
        await syncZenodo({ platform, store, logger: { warn: message => warnings.push(message) } }, verified,
            { datestamp: '20261011', zenodo_version_doi: '10.5281/zenodo.1' });
        return await body({ bytes: Buffer.from(await store.read(receipt)), original, warnings });
    } finally { fs.rmSync(root, { recursive: true, force: true }); }
}
for (const vector of cacheGoldens.cases) {
    test(`native cache encoding receipt ${vector.id}`, async () => {
        await nativeReceiptEncoding(vector, ({ bytes, warnings }) => {
            const expected = Buffer.from('{"by":"native-encoding","datestamp":"20261011","extension":' + vector.expected
                + ',"files":{},"format_version":"1.0","verified_at":"2026-10-11T00:00:00Z","zenodo_version_doi":"10.5281/zenodo.1"}');
            console.log(JSON.stringify({ cell: vector.id, producer: 'syncZenodo', actual_hex: bytes.toString('hex'),
                expected_hex: expected.toString('hex'), size: bytes.length, warnings }));
            assert.deepEqual(bytes, expected);
            assert.deepEqual(warnings, []);
        });
    });
}
for (const vector of cacheGoldens.refusals.filter(vector => vector.raw_json_hex)) {
    test(`native cache encoding receipt refuses ${vector.id}`, async () => {
        await nativeReceiptEncoding(vector, ({ bytes, original, warnings }) => {
            assert.deepEqual(bytes, original, 'refused generated JSON must preserve the previous receipt');
            assert.equal(warnings.length, 1);
            assert.match(warnings[0], /unpaired surrogate/);
        });
    });
}

test('native cache encoding callable uses FMT exact finite bytes and refuses invalid scalar values', () => {
    for (const vector of cacheGoldens.cases) {
        const input = cacheGoldenInput(vector);
        const bytes = encodeCacheJson(input);
        assert.ok(bytes instanceof Uint8Array);
        assert.deepEqual(Buffer.from(bytes), Buffer.from(vector.expected), vector.id);
    }
    for (const vector of cacheGoldens.refusals) {
        assert.throws(() => encodeCacheJson(cacheGoldenInput(vector)), TypeError, vector.id);
    }
    assert.throws(() => encodeCacheJson({ '\ud800': null }), /unpaired surrogate/);
});

test('native cache encoding actual acquired receipt and stream index conserve source bytes', async () => {
    const source = process.env.OTC_CACHE_ENCODING_SOURCE_DIR ?? new URL('../../conformance/fixtures/good/', import.meta.url).pathname;
    const date = process.env.OTC_CACHE_ENCODING_SOURCE_DIR ? '20261011' : '20991231.2';
    const stem = `OTC_${date}`;
    const originals = Object.fromEntries(['jsonl', 'meta.json', 'sha256'].map(suffix =>
        [`${stem}.${suffix}`, fs.readFileSync(path.join(source, `${stem}.${suffix}`))]));
    const root = fs.mkdtempSync(path.join(process.env.OTC_CACHE_ENCODING_PROOF_ROOT ?? os.tmpdir(), 'otc-cache-acquired-'));
    const requests = [];
    const server = createServer((request, response) => {
        requests.push(request.url);
        const body = originals[request.url.slice(1)];
        response.writeHead(body ? 200 : 404);
        response.end(body ?? 'not found');
    });
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    let opened;
    try {
        const address = server.address();
        opened = await sdk.OpenTideConstants.open({ release: date, baseUrl: `http://127.0.0.1:${address.port}/`,
            cacheDir: root, mode: 'stream' });
        const dir = path.join(root, 'v1', 'releases', date);
        for (const [name, bytes] of Object.entries(originals)) assert.deepEqual(fs.readFileSync(path.join(dir, name)), bytes, name);
        const emitted = {};
        for (const name of ['.verified', 'index-v1.json']) {
            const bytes = fs.readFileSync(path.join(dir, name));
            emitted[name] = bytes.toString('utf8');
            if (process.env.OTC_CACHE_ENCODING_PROOF_ROOT && process.env.OTC_CACHE_ENCODING_PHASE) {
                fs.writeFileSync(path.join(process.env.OTC_CACHE_ENCODING_PROOF_ROOT,
                    `${process.env.OTC_CACHE_ENCODING_PHASE}-generated-${name === '.verified' ? 'verified' : 'index'}.json`), bytes);
            }
            console.log(JSON.stringify({ producer: name === '.verified' ? 'ensureRelease' : 'loadCached',
                bytes_hex: bytes.toString('hex'), size: bytes.length, requests,
                by: JSON.parse(bytes).by, verified_at: JSON.parse(bytes).verified_at ?? null }));
        }
        const originalRows = originals[`${stem}.jsonl`].toString('utf8').trimEnd().split('\n').map(line => JSON.parse(line));
        for (const original of originalRows) assert.deepEqual(opened.requireStation(original.station_id).raw, original);
        assert.ok(Object.values(emitted).every(bytes => bytes.startsWith('{"by":')), 'both native generated documents use canonical key order');
    } finally {
        opened?.close();
        await new Promise(resolve => server.close(resolve));
        fs.rmSync(root, { recursive: true, force: true });
    }
});

test('actual strict commercial recommendations retain permitted published sets independently from discovery', async () => {
    const strictFile = process.env.OTC_CORE_NATIVE_STRICT_JSON ?? file;
    assert.ok(strictFile, 'actual pinned strict recommendation fixture required');
    const document = JSON.parse(fs.readFileSync(strictFile, 'utf8'));
    const ids = ['OTC-013bda9c', 'OTC-11b36fe8', 'OTC-1279f3e7'];
    for (const commercialBasis of ['strict', 'as_published_upstream']) {
        const strictClient = await sdk.OpenTideConstants.open({ file: strictFile, commercialOnly: true, commercialBasis });
        try {
            assert.deepEqual(strictClient.stations({ source: 'ticon-4' }).filter(s => ids.includes(s.station_id)), []);
            assert.deepEqual(strictClient.stations({ source: 'ticon-4', includeFallback: true })
                .filter(s => ids.includes(s.station_id)).map(s => s.station_id), commercialBasis === 'strict' ? [] : ids);
            for (const id of ids) {
                const input = document.stations.find(s => s.station_id === id);
                assert.ok(input, `actual station ${id} required`);
                const station = strictClient.requireStation(id);
                const original = input.constant_sets.find(s => s.set_id === input.recommended_set_id);
                assert.equal(station.recommendedSet?.set_id, input.recommended_set_id, `${commercialBasis}/${id}`);
                assert.equal(station.constantSets()[0].set_id, input.recommended_set_id);
                assert.deepEqual(station.raw, input);
                assert.deepEqual(station.source_records.map(s => s.raw), input.source_records);
                assert.deepEqual(station.recommendedSet.raw, original);
                const licence = document.licences.find(l => l.licence_id === original.licence_id);
                assert.equal(licence.commercial_use, true);
                assert.ok(strictClient.attribution([station]).includes(licence.attribution));
                const times = [new Date('2026-10-11T00:00:00Z')];
                const explicit = await strictClient.heightsAt(station, times, { setId: input.recommended_set_id });
                const implicit = await strictClient.heightsAt(station, times);
                assert.deepEqual(implicit, explicit);
                const refused = input.constant_sets.find(s => document.licences
                    .find(l => l.licence_id === s.licence_id)?.commercial_use === false);
                assert.ok(refused, 'actual noncommercial explicit selection required');
                await assert.rejects(strictClient.heightsAt(station, times, { setId: refused.set_id }),
                    e => e.code === 'invalid_argument' && e.message.includes('commercial_only refuses set_id'));
                console.log(JSON.stringify({ control: 'strict recommendation', commercialBasis, station_id: id,
                    set_id: station.recommendedSet.set_id, height_m: implicit.items[0].height_m }));
            }
        } finally { strictClient.close(); }
    }
});

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

// A bounded real META fixture: no station/source rerun and no invented header values.
for (const mode of ['eager', 'stream']) {
    for (const field of ['release', 'astro_tables', 'constituents', 'complete']) {
        test(`actual META private header ${mode}/${field}`, async () => {
            const metaPath = process.env.OTC_CORE_NATIVE_META ?? jsonl?.replace(/\.jsonl$/, '.meta.json');
            assert.ok(metaPath, 'actual unchanged H4 META path required');
            const metaBytes = fs.readFileSync(metaPath);
            const metadata = JSON.parse(metaBytes.toString('utf8'));
            const loader = await import(process.env.OTC_CORE_NATIVE_HEADER_LOADER ?? '../dist/loader.js');
            const fixture = { ...metadata, stations: [] };
            const release = mode === 'eager'
                ? loader.releaseFromJson(new TextEncoder().encode(JSON.stringify(fixture)), [])
                : loader.releaseFromJsonl(metaBytes, new Uint8Array(), { eager: false, files: [] });
            try {
                assert.ok(release._header, 'native private header hook must retain the original parsed resources');
                if (field === 'complete') {
                    assert.deepEqual(release._header, mode === 'eager' ? fixture : metadata);
                    assert.ok(Object.isFrozen(release._header));
                    assert.throws(() => { release._header.release.build_commit = 'mutation'; }, TypeError);
                } else {
                    assert.deepEqual(release._header[field], metadata[field]);
                    assert.ok(Object.isFrozen(release._header[field]));
                    if (field === 'astro_tables') {
                        assert.ok(metadata.astro_tables.length > 0);
                        for (const table of release._header.astro_tables) {
                            assert.ok(Object.isFrozen(table.constituents));
                        }
                    }
                }
            } finally { release._close(); }
        });
    }
}

test('actual source typed provenance and licence links for at least three original records', () => {
    let checked=0;
    for (const input of raw.stations) {
        const station=client.requireStation(input.station_id);
        assert.ok(Array.isArray(station.source_records), 'native typed source records must be available');
        for (let index=0;index<input.source_records.length;index++) {
            const original=input.source_records[index];
            const source=station.source_records[index];
            assert.deepEqual(source.provenance,original.provenance);
            assert.equal(source.licence_id,original.licence_id);
            const licence=raw.licences.find(l=>l.licence_id===original.licence_id) ?? null;
            assert.equal(source.licence?.licence_id ?? null,licence?.licence_id ?? null);
            assert.deepEqual(source.licence?.raw ?? null,licence);
            assert.equal(source.upstream_licence_id,original.upstream_licence_id ?? null);
            const upstream=raw.licences.find(l=>l.licence_id===original.upstream_licence_id) ?? null;
            assert.equal(source.upstreamLicence?.licence_id ?? null,upstream?.licence_id ?? null);
            assert.deepEqual(source.upstreamLicence?.raw ?? null,upstream);
            checked++;
        }
        if (checked>=3) break;
    }
    assert.ok(checked>=3,'actual fixture must supply at least three source records');
});

// Native file controls use an original H4 document and its unchanged META.
let streamFixture;
function nativeStreamFixture() {
    if (streamFixture) return streamFixture;
    assert.ok(jsonl, 'actual pinned H4 JSONL path required');
    const meta = fs.readFileSync(jsonl.replace(/\.jsonl$/, '.meta.json'));
    const reader = nodeRuntime.openLineReader(jsonl);
    const fragments = [];
    let offset = 0;
    try {
        for (;;) {
            const chunk = reader.read(offset, 65536);
            assert.ok(chunk.length, 'actual H4 first station required');
            const end = chunk.indexOf(10);
            fragments.push(chunk.subarray(0, end < 0 ? chunk.length : end));
            offset += chunk.length;
            if (end >= 0) break;
        }
    } finally { reader.close(); }
    const station = JSON.parse(Buffer.concat(fragments).toString('utf8'));
    streamFixture = { meta, header: streamLoader.headerFromMeta(meta), station };
    return streamFixture;
}

function withNativeStreamFile(bytes, body) {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'otc-native-stream-'));
    const file = path.join(dir, 'OTC_20261011.jsonl');
    fs.writeFileSync(file, bytes);
    const reader = nodeRuntime.openLineReader(file);
    try { return body(reader, file); }
    finally { reader.close(); fs.rmSync(dir, { recursive: true, force: true }); }
}

function scanNativeStream(bytes, header = nativeStreamFixture().header, readTransform) {
    return withNativeStreamFile(bytes, reader => {
        assert.equal(typeof streamLoader.scanJsonlReader, 'function', 'private incremental scanner required');
        assert.equal(typeof nodeRuntime.nodeApi.createSha256State, 'function', 'private incremental SHA required');
        const state = nodeRuntime.nodeApi.createSha256State();
        const reads = [];
        const result = streamLoader.scanJsonlReader(header, (offset, length) => {
            const chunk = readTransform ? readTransform(reader, offset, length) : reader.read(offset, length);
            reads.push({ offset, requested: length, received: chunk.length });
            return chunk;
        }, chunk => state.update(chunk));
        return { ...result, digest: state.digest(), reads };
    });
}

test('native Node direct stream scanner exact chunks, offsets, UTF8, CRLF, blank and final line', () => {
    const { header, station } = nativeStreamFixture();
    const document = { ...station, name: 'é🐬' + station.name };
    const line = Buffer.from(JSON.stringify(document));
    const padding = (65535 - line.indexOf(Buffer.from('é'))) % 65536;
    for (const ending of ['\n', '\r\n', '', '\r']) {
        const bytes = Buffer.concat([Buffer.from(' '.repeat(padding)), line, Buffer.from(ending + '\n \t\v\f\r\n')]);
        const expected = streamLoader.indexJsonl(header, bytes, false);
        const result = scanNativeStream(bytes, header);
        assert.equal(result.error, null);
        assert.deepEqual(result.entries, expected.entries);
        assert.equal(result.bytesRead, bytes.length);
        assert.equal(result.digest, nodeRuntime.sha256Sync(bytes));
        assert.ok(result.reads.length >= 2);
        assert.ok(result.reads.every(r => r.requested === 65536));
        console.log(JSON.stringify({ control: 'chunk-boundary', ending, bytes: result.bytesRead, sha256: result.digest, entries: result.entries.length }));
    }
    const long = Buffer.from(' '.repeat(200000) + JSON.stringify(station));
    assert.deepEqual(scanNativeStream(long).entries, streamLoader.indexJsonl(header, long, false).entries);
    for (const ending of ['', '\r', '\n', '\r\n']) {
        const final = Buffer.from(JSON.stringify(station) + ending);
        const result = scanNativeStream(final);
        assert.equal(result.error, null);
        assert.deepEqual(result.entries, streamLoader.indexJsonl(header, final, false).entries);
        assert.equal(result.digest, nodeRuntime.sha256Sync(final));
    }
    assert.deepEqual(scanNativeStream(Buffer.alloc(0)).entries, []);
});

for (const [label, suffix] of [
    ['malformed', '{broken'], ['invalid UTF8', Buffer.from([0xc3, 0x28])],
    ['lone surrogate', '{"station_id":"\\ud800"}'], ['NUL', '\0'], ['NBSP', '\u00a0'],
]) {
    test(`native Node direct stream scanner deferred ${label} still hashes every native byte`, () => {
        const { header } = nativeStreamFixture();
        const bytes = Buffer.concat([Buffer.from('\n \t\r\n'), Buffer.from(suffix), Buffer.from('\n' + ' '.repeat(150000))]);
        let expected;
        try { streamLoader.indexJsonl(header, bytes, false); } catch (error) { expected = error; }
        assert.ok(expected, 'existing full-byte parser must reject this real-file control');
        const result = scanNativeStream(bytes);
        assert.equal(result.error?.code, expected.code);
        assert.equal(result.error?.message, expected.message);
        assert.equal(result.bytesRead, bytes.length);
        assert.equal(result.digest, nodeRuntime.sha256Sync(bytes));
        console.log(JSON.stringify({ control: label, bytes: result.bytesRead, sha256: result.digest, error: result.error.message }));
    });
}

test('native Node direct stream scanner unresolved reference matches the existing native fixture', () => {
    const fixture = new URL('../../conformance/fixtures/bad/unresolved-reference-station/OTC_20991231.jsonl', import.meta.url);
    const meta = fs.readFileSync(new URL('./OTC_20991231.meta.json', fixture));
    const header = streamLoader.headerFromMeta(meta);
    const bytes = fs.readFileSync(fixture);
    let expected;
    try { streamLoader.indexJsonl(header, bytes, false); } catch (error) { expected = error; }
    assert.ok(expected);
    const result = scanNativeStream(bytes, header);
    assert.equal(result.error?.message, expected.message);
    assert.equal(result.digest, nodeRuntime.sha256Sync(bytes));
});

test('native Node direct stream scanner null header completes exact hashing', () => {
    const bytes = Buffer.from('{broken\n' + ' '.repeat(150000));
    const result = scanNativeStream(bytes, null);
    assert.equal(result.error, null);
    assert.equal(result.bytesRead, bytes.length);
    assert.equal(result.digest, nodeRuntime.sha256Sync(bytes));
});

test('native Node direct stream reader completes short OS reads on the same FD', () => {
    const bytes = Buffer.from(JSON.stringify(nativeStreamFixture().station) + '\n');
    const original = fs.readSync;
    const descriptors = new Set();
    fs.readSync = (fd, buffer, offset, length, position) => {
        descriptors.add(fd);
        return original(fd, buffer, offset, Math.min(17, length), position);
    };
    syncBuiltinESMExports();
    try {
        const result = scanNativeStream(bytes);
        assert.equal(result.error, null);
        assert.equal(result.bytesRead, bytes.length);
        assert.equal(result.digest, nodeRuntime.sha256Sync(bytes));
        assert.equal(descriptors.size, 1);
        console.log(JSON.stringify({ control: 'short OS reads', bytes: result.bytesRead, sha256: result.digest, descriptors: descriptors.size }));
    } finally { fs.readSync = original; syncBuiltinESMExports(); }
});

for (const code of ['EIO', 'EBADF']) {
    test(`native Node direct stream reader ${code} is io and closes the owned FD`, () => {
        const bytes = Buffer.from(JSON.stringify(nativeStreamFixture().station) + '\n');
        const original = fs.readSync;
        let descriptor;
        try {
            withNativeStreamFile(bytes, reader => {
                fs.readSync = fd => { descriptor = fd; throw Object.assign(new Error(code), { code }); };
                syncBuiltinESMExports();
                assert.throws(() => streamLoader.scanJsonlReader(nativeStreamFixture().header, reader.read, () => undefined), e => e.code === 'io' && e.cause?.code === code);
            });
            assert.throws(() => fs.fstatSync(descriptor), e => e.code === 'EBADF');
        } finally { fs.readSync = original; syncBuiltinESMExports(); }
    });
}

test('native Node direct stream reader close error retains existing idempotent semantics', () => {
    const original = fs.closeSync;
    let calls = 0;
    withNativeStreamFile(Buffer.from('{}\n'), reader => {
        fs.closeSync = fd => { original(fd); calls++; throw Object.assign(new Error('close EIO'), { code: 'EIO' }); };
        syncBuiltinESMExports();
        try { reader.close(); reader.close(); }
        finally { fs.closeSync = original; syncBuiltinESMExports(); }
        assert.equal(calls, 1);
        assert.throws(() => reader.read(0, 1), e => e.code === 'io');
    });
});

function authenticateNativeStreamControl({ malformed = false, invalidHeader = false, badJsonl = false, badMeta = false,
    missing = null, truncated = false, wrongSize = false } = {}) {
    const fixture = nativeStreamFixture();
    const bytes = Buffer.from(malformed ? '{broken\n' + ' '.repeat(150000) : JSON.stringify(fixture.station) + '\n');
    const metaDocument = JSON.parse(fixture.meta.toString('utf8'));
    if (invalidHeader) metaDocument.format_version = 'invalid';
    const meta = Buffer.from(JSON.stringify(metaDocument));
    return withNativeStreamFile(bytes, (reader, file) => {
        const metaPath = file.replace(/\.jsonl$/, '.meta.json');
        const shaPath = file.replace(/\.jsonl$/, '.sha256');
        const jsonlName = path.basename(file), metaName = path.basename(metaPath);
        fs.writeFileSync(metaPath, meta);
        const expectedJsonl = badJsonl ? '0'.repeat(64) : nodeRuntime.sha256Sync(bytes);
        const expectedMeta = badMeta ? '0'.repeat(64) : nodeRuntime.sha256Sync(meta);
        fs.writeFileSync(shaPath, (missing === 'jsonl' ? '' : `${expectedJsonl}  ${jsonlName}\n`)
            + (missing === 'meta' ? '' : `${expectedMeta}  ${metaName}\n`));
        if (truncated) fs.truncateSync(file, bytes.length - 3);
        const actualMeta = nodeRuntime.readFileOrIo(metaPath);
        const rows = streamLoader.parseSha256(nodeRuntime.readFileOrIo(shaPath));
        let header = null, headerError = null;
        try { header = streamLoader.headerFromMeta(actualMeta); } catch (error) { headerError = error; }
        const state = nodeRuntime.nodeApi.createSha256State();
        const scan = streamLoader.scanJsonlReader(header, reader.read, chunk => state.update(chunk));
        const digest = state.digest();
        const checks = () => {
            checkBytes(jsonlName, digest, scan.bytesRead, rows.get(jsonlName) ?? null, wrongSize ? bytes.length + 1 : null);
            checkBytes(metaName, nodeRuntime.sha256Sync(actualMeta), actualMeta.length, rows.get(metaName) ?? null, null);
            if (headerError) throw headerError;
            if (scan.error) throw scan.error;
        };
        let error = null;
        try { checks(); } catch (caught) { error = caught; }
        assert.equal(digest, nodeRuntime.sha256Sync(fs.readFileSync(file)), 'hashed bytes must be the actual native file bytes');
        console.log(JSON.stringify({ control: 'authentication boundary', bytes: scan.bytesRead, sha256: digest,
            meta_sha256: nodeRuntime.sha256Sync(actualMeta), error: error && { code: error.code, file: error.file, message: error.message } }));
        return { ...scan, digest, error };
    });
}

for (const [label, options, code, fileSuffix] of [
    ['valid', {}, null, null],
    ['bad JSONL SHA before malformed', { badJsonl: true, malformed: true }, 'checksum_mismatch', '.jsonl'],
    ['META SHA before malformed', { badMeta: true, malformed: true }, 'checksum_mismatch', '.meta.json'],
    ['saved malformed after both SHA', { malformed: true }, 'invalid_release', null],
    ['JSONL SHA before invalid header', { badJsonl: true, invalidHeader: true }, 'checksum_mismatch', '.jsonl'],
    ['META SHA before invalid header', { badMeta: true, invalidHeader: true }, 'checksum_mismatch', '.meta.json'],
    ['saved invalid header after both SHA', { invalidHeader: true }, 'invalid_release', null],
    ['missing JSONL row', { missing: 'jsonl' }, 'checksum_mismatch', '.jsonl'],
    ['missing META row', { missing: 'meta' }, 'checksum_mismatch', '.meta.json'],
    ['premature EOF with original SHA', { truncated: true }, 'checksum_mismatch', '.jsonl'],
    ['actual byte size', { wrongSize: true }, 'checksum_mismatch', '.jsonl'],
]) {
    test(`native Node direct stream authentication ${label}`, () => {
        const result = authenticateNativeStreamControl(options);
        assert.equal(result.error?.code ?? null, code);
        if (fileSuffix) assert.ok(result.error.file.endsWith(fileSuffix));
        if (!code) assert.equal(result.entries.length, 1);
        if (label === 'actual byte size') assert.match(result.error.message, /size .* expected/);
    });
}

test('native Node direct stream public avoids the whole-file JSONL read', async () => {
    const original = fs.readFileSync;
    let wholeFileReads = 0;
    fs.readFileSync = (file, ...args) => {
        if (String(file) === jsonl) wholeFileReads++;
        return original(file, ...args);
    };
    syncBuiltinESMExports();
    let opened;
    try {
        opened = await sdk.OpenTideConstants.open({ file: jsonl, mode: 'stream' });
        assert.equal(wholeFileReads, 0, 'direct stream must not materialize the entire JSONL');
        assert.equal(opened.loadedFrom, 'file');
        assert.equal(opened.requireStation('OTC-a6c00a3f').station_id, 'OTC-a6c00a3f');
    } finally { fs.readFileSync = original; syncBuiltinESMExports(); opened?.close(); }
});

async function withNativePublicStream(options, body) {
    const { meta, station } = nativeStreamFixture();
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'otc-public-stream-'));
    const file = path.join(dir, 'OTC_20261011.jsonl');
    const metaPath = file.replace(/\.jsonl$/, '.meta.json');
    const bytes = Buffer.from(options.malformed ? '{broken\n' + ' '.repeat(150000) : JSON.stringify(station) + '\r\n');
    const metadata = JSON.parse(meta.toString('utf8'));
    if (options.invalidHeader) metadata.format_version = 'invalid';
    const metaBytes = Buffer.from(JSON.stringify(metadata));
    fs.writeFileSync(file, bytes);
    fs.writeFileSync(metaPath, metaBytes);
    if (!options.unverified) {
        const sha = (options.missing === 'jsonl' ? '' : `${options.badJsonl ? '0'.repeat(64) : nodeRuntime.sha256Sync(bytes)}  ${path.basename(file)}\n`)
            + (options.missing === 'meta' ? '' : `${options.badMeta ? '0'.repeat(64) : nodeRuntime.sha256Sync(metaBytes)}  ${path.basename(metaPath)}\n`);
        fs.writeFileSync(file.replace(/\.jsonl$/, '.sha256'), sha);
    }
    if (options.truncated) fs.truncateSync(file, bytes.length - 3);
    try { return await body(file, station, bytes); }
    finally { fs.rmSync(dir, { recursive: true, force: true }); }
}

for (const [label, options, code, suffix] of [
    ['bad JSONL SHA before malformed', { malformed: true, badJsonl: true }, 'checksum_mismatch', '.jsonl'],
    ['META SHA before malformed', { malformed: true, badMeta: true }, 'checksum_mismatch', '.meta.json'],
    ['saved malformed after both SHA', { malformed: true }, 'invalid_release', null],
    ['JSONL SHA before invalid header', { invalidHeader: true, badJsonl: true }, 'checksum_mismatch', '.jsonl'],
    ['META SHA before invalid header', { invalidHeader: true, badMeta: true }, 'checksum_mismatch', '.meta.json'],
    ['saved invalid header after both SHA', { invalidHeader: true }, 'invalid_release', null],
    ['missing JSONL row', { missing: 'jsonl' }, 'checksum_mismatch', '.jsonl'],
    ['missing META row before bad JSONL SHA', { missing: 'meta', badJsonl: true }, 'checksum_mismatch', '.meta.json'],
    ['real truncated file', { truncated: true }, 'checksum_mismatch', '.jsonl'],
    ['EIO', { ioCode: 'EIO' }, 'io', null],
    ['EBADF', { ioCode: 'EBADF' }, 'io', null],
]) {
    test(`native Node direct stream public ${label} closes its sole FD`, async () => {
        await withNativePublicStream(options, async file => {
            const open = fs.openSync, close = fs.closeSync, read = fs.readSync;
            let descriptor, opens = 0, closes = 0;
            fs.openSync = (name, ...args) => {
                const fd = open(name, ...args);
                if (String(name) === file) { descriptor = fd; opens++; }
                return fd;
            };
            fs.closeSync = fd => { if (fd === descriptor) closes++; return close(fd); };
            fs.readSync = (fd, ...args) => {
                if (fd === descriptor && options.ioCode) throw Object.assign(new Error(options.ioCode), { code: options.ioCode });
                return read(fd, ...args);
            };
            syncBuiltinESMExports();
            try {
                await assert.rejects(sdk.OpenTideConstants.open({ file, mode: 'stream' }), e => e.code === code
                    && (!suffix || e.file.endsWith(suffix)) && (!options.ioCode || e.cause?.code === options.ioCode));
                assert.equal(opens, 1);
                assert.equal(closes, 1);
                assert.throws(() => fs.fstatSync(descriptor), e => e.code === 'EBADF');
                console.log(JSON.stringify({ control: 'public authentication/cleanup', label, opens, closes, code }));
            } finally { fs.openSync = open; fs.closeSync = close; fs.readSync = read; syncBuiltinESMExports(); }
        });
    });
}

for (const unverified of [false, true]) {
    test(`native Node direct stream public same FD short reads and lazy station ${unverified ? 'unverified' : 'verified'}`, async () => {
        await withNativePublicStream({ unverified }, async (file, station) => {
            const open = fs.openSync, close = fs.closeSync, read = fs.readSync, readFile = fs.readFileSync;
            let descriptor, opens = 0, closes = 0, wholeReads = 0;
            const positions = [];
            fs.openSync = (name, ...args) => {
                const fd = open(name, ...args);
                if (String(name) === file) { descriptor = fd; opens++; }
                return fd;
            };
            fs.closeSync = fd => { if (fd === descriptor) closes++; return close(fd); };
            fs.readSync = (fd, buffer, offset, length, position) => {
                if (fd === descriptor) { positions.push(position); return read(fd, buffer, offset, Math.min(length, 17), position); }
                return read(fd, buffer, offset, length, position);
            };
            fs.readFileSync = (name, ...args) => { if (String(name) === file) wholeReads++; return readFile(name, ...args); };
            syncBuiltinESMExports();
            let client;
            try {
                client = await sdk.OpenTideConstants.open({ file, mode: 'stream' });
                assert.equal(client.loadedFrom, unverified ? 'file_unverified' : 'file');
                assert.equal(opens, 1);
                assert.equal(closes, 0);
                assert.equal(wholeReads, 0);
                const initialReads = positions.length;
                assert.deepEqual(client.requireStation(station.station_id).raw, station);
                assert.ok(positions.length > initialReads, 'the selected station must be read lazily');
                assert.equal(positions[initialReads], 0, 'lazy station reads reuse original native byte offsets');
                client.close(); client.close();
                assert.equal(closes, 1);
                assert.throws(() => client.requireStation(station.station_id), e => e.code === 'io');
                console.log(JSON.stringify({ control: 'public reader lifecycle', unverified, opens, closes, wholeReads, initialReads, lazyReads: positions.length - initialReads }));
            } finally {
                client?.close(); fs.openSync = open; fs.closeSync = close; fs.readSync = read; fs.readFileSync = readFile; syncBuiltinESMExports();
            }
        });
    });
}

test('native Node direct stream public fresh index keeps fresh error names', async () => {
    await withNativePublicStream({}, async (file, station, bytes) => {
        const client = await sdk.OpenTideConstants.open({ file, mode: 'stream' });
        try {
            fs.writeFileSync(file, Buffer.from(' '.repeat(bytes.length)));
            assert.throws(() => client.requireStation(station.station_id), e => e.code === 'invalid_release'
                && e.message.startsWith('the .jsonl index does not match') && !e.message.includes('index-v1.json'));
        } finally { client.close(); }
    });
});
