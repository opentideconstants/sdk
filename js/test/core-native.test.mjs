import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { syncBuiltinESMExports } from 'node:module';
import * as sdk from '../dist/index.js';
import * as streamLoader from '../dist/loader.js';
import * as nodeRuntime from '../dist/node.js';
import { checkBytes } from '../dist/core.js';

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
