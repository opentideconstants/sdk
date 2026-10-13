import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import fsp from 'node:fs/promises';
import { createServer } from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { syncBuiltinESMExports } from 'node:module';
import * as sdk from '../dist/index.js';
import { loadCached, verifyCached } from '../dist/core.js';
import { headerFromMeta, indexJsonl } from '../dist/loader.js';
import * as nodeRuntime from '../dist/node.js';
import { storedIndex, usableIndex } from '../dist/release.js';
import { encodeCacheJson } from '../dist/cache-json.js';

const cache = process.env.OTC_CACHED_STREAM_CACHE;
const historical = process.env.OTC_CACHED_HISTORY_DIR ?? '/Users/jpr5/.local/share/copilotkit/cr/otc-codex-takeover/execution/sdk-core-sync/proofs/T1/historical-targets';
const date = '20261011', stem = `OTC_${date}`;
const hash = bytes => createHash('sha256').update(bytes).digest('hex');

for (const losses of [0, 1, 3]) {
    test(`COMMON-TS-LOCK native public publication with ${losses} ownership losses`, async () => {
        const source = new URL('../../conformance/fixtures/good/', import.meta.url).pathname;
        const originals = Object.fromEntries(['jsonl', 'meta.json', 'sha256'].map(suffix => {
            const name = `OTC_20991231.2.${suffix}`;
            return [name, fs.readFileSync(path.join(source, name))];
        }));
        const root = fs.mkdtempSync(path.join(process.env.OTC_LOCK_PROOF ?? os.tmpdir(), `native-lost-${losses}-`));
        const dir = path.join(root, 'v1/releases/20991231.2');
        const ownerPath = path.join(dir, '.lock/owner.json');
        const verifiedPath = path.join(dir, '.verified');
        const events = [], releases = [], warnings = [];
        let attempts = 0, foreignToken = null, prematurePublication = false;
        const server = createServer((request, response) => {
            const name = request.url.slice(1), bytes = originals[name];
            events.push({ event: 'HTTP', name, sha256: bytes ? hash(bytes) : null });
            if (name.endsWith('.sha256')) {
                attempts++;
                const owner = JSON.parse(fs.readFileSync(ownerPath));
                events.push({ event: 'native-owner', attempt: attempts, token: owner.token });
                if (attempts <= losses) {
                    foreignToken = `${'a'.repeat(31)}${attempts}`;
                    fs.writeFileSync(ownerPath, JSON.stringify({ ...owner, token: foreignToken }));
                    events.push({ event: 'external-token-replaced', attempt: attempts, token: foreignToken });
                    const expectedToken = foreignToken;
                    releases.push(new Promise(resolve => setTimeout(() => {
                        const held = fs.existsSync(ownerPath) ? JSON.parse(fs.readFileSync(ownerPath)) : null;
                        events.push({ event: 'foreign-window', attempt: attempts, token: held?.token ?? null,
                            verified_exists: fs.existsSync(verifiedPath) });
                        if (held?.token === expectedToken) fs.rmSync(path.dirname(ownerPath), { recursive: true });
                        events.push({ event: 'external-owner-released', token: expectedToken });
                        resolve();
                    }, 100)));
                }
            }
            response.writeHead(bytes ? 200 : 404); response.end(bytes ?? 'not found');
        });
        await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
        const rename = fs.renameSync;
        fs.renameSync = function (from, to) {
            if (String(to) === verifiedPath) {
                const held = fs.existsSync(ownerPath) ? JSON.parse(fs.readFileSync(ownerPath)) : null;
                events.push({ event: 'verified-publication', token: held?.token ?? null });
                if (held?.token === foreignToken) prematurePublication = true;
            }
            return rename.call(this, from, to);
        };
        syncBuiltinESMExports();
        let opened, failure;
        try {
            try {
                opened = await sdk.OpenTideConstants.open({ release: '20991231.2', mode: 'stream', cacheDir: root,
                    baseUrl: `http://127.0.0.1:${server.address().port}/`, onNetworkError: 'raise',
                    logger: { warn: message => warnings.push(message) } });
            } catch (error) { failure = error; }
            await Promise.all(releases);
            const receipt = fs.existsSync(verifiedPath) ? JSON.parse(fs.readFileSync(verifiedPath)) : null;
            console.log(JSON.stringify({ surface: 'actual public pinned stream ownership', losses, attempts, events, warnings,
                prematurePublication, error_code: failure?.code ?? null, loaded_from: opened?.loadedFrom ?? null, receipt,
                source_hashes: Object.fromEntries(Object.entries(originals).map(([name, bytes]) => [name, hash(bytes)])) }));
            assert.equal(prematurePublication, false, 'a foreign owner must never authorize this receipt publication');
            for (const event of events.filter(event => event.event === 'foreign-window')) {
                assert.ok(event.token, 'unlock must not delete the external owner token');
                assert.equal(event.verified_exists, false, 'receipt stays absent while foreign ownership is held');
            }
            if (losses === 3) {
                assert.equal(failure?.code, 'cache'); assert.equal(attempts, 3); assert.equal(receipt, null);
            } else {
                assert.equal(failure, undefined); assert.equal(opened.loadedFrom, 'download');
                assert.equal(attempts, losses + 1);
                assert.ok(receipt);
                assert.deepEqual(Object.keys(receipt.files).sort(), ['OTC_20991231.2.jsonl', 'OTC_20991231.2.meta.json']);
                for (const [name, row] of Object.entries(receipt.files)) {
                    assert.equal(row.sha256, hash(originals[name])); assert.equal(row.size, originals[name].length);
                    assert.deepEqual(fs.readFileSync(path.join(dir, name)), originals[name]);
                }
                assert.deepEqual(opened.requireStation('OTC-T-0001').raw,
                    originals['OTC_20991231.2.jsonl'].toString().split('\n').map(line => line ? JSON.parse(line) : null)
                        .find(station => station?.station_id === 'OTC-T-0001'));
            }
            assert.equal(warnings.length, losses);
        } finally {
            fs.renameSync = rename; syncBuiltinESMExports(); opened?.close();
            await Promise.all(releases); await new Promise(resolve => server.close(resolve));
            if (!process.env.OTC_LOCK_PROOF) fs.rmSync(root, { recursive: true, force: true });
        }
    });
}

function fixture(jsonl = fs.readFileSync(path.join(historical, `${stem}.jsonl`)), releaseDate = date, releaseDir = historical) {
    const date = releaseDate, stem = `OTC_${date}`;
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'otc-native-cached-'));
    const dir = path.join(root, 'v1', 'releases', date);
    fs.mkdirSync(dir, { recursive: true });
    const meta = fs.readFileSync(path.join(releaseDir, `${stem}.meta.json`));
    const files = { [`${stem}.meta.json`]: meta, [`${stem}.jsonl`]: jsonl };
    const verified = { datestamp: date, format_version: '1.0', verified_at: '2026-10-11T00:00:00Z', by: 'native-test', files: {} };
    for (const [name, bytes] of Object.entries(files)) {
        fs.writeFileSync(path.join(dir, name), bytes);
        verified.files[name] = { sha256: hash(bytes), size: bytes.length, url: null };
    }
    fs.writeFileSync(path.join(dir, `${stem}.sha256`), Object.entries(files).map(([name, bytes]) => `${hash(bytes)}  ${name}\n`).join(''));
    fs.writeFileSync(path.join(dir, '.verified'), JSON.stringify(verified));
    return { root, dir, meta, jsonl, verified, date, cleanup: () => fs.rmSync(root, { recursive: true, force: true }) };
}

// All successful reads are real native reads. Hooks inject only named I/O failures/short reads.
async function observe(body, hooks = {}) {
    const originals = Object.fromEntries(['openSync', 'readSync', 'closeSync', 'readFileSync'].map(name => [name, fs[name]]));
    const active = new Map(), opened = [], closed = [], reads = [], bodies = [];
    let peak = 0, wholeBody = false;
    fs.openSync = (file, ...args) => {
        hooks.open?.(String(file));
        const fd = originals.openSync(file, ...args);
        active.set(fd, String(file)); opened.push({ fd, file: String(file) }); peak = Math.max(peak, active.size);
        return fd;
    };
    fs.readSync = (fd, buffer, offset, length, position) => {
        const file = active.get(fd);
        const limit = hooks.read?.({ fd, file, length, position }) ?? length;
        const count = originals.readSync(fd, buffer, offset, Math.min(length, limit), position);
        reads.push({ fd, file, length, position, count, wholeBody });
        return count;
    };
    fs.closeSync = fd => {
        const file = active.get(fd);
        originals.closeSync(fd); active.delete(fd); closed.push({ fd, file }); hooks.close?.(file);
    };
    fs.readFileSync = (file, ...args) => {
        bodies.push(String(file)); wholeBody = true;
        try { return originals.readFileSync(file, ...args); }
        finally { wholeBody = false; }
    };
    syncBuiltinESMExports();
    try { return await body({ active, opened, closed, reads, bodies, get peak() { return peak; } }); }
    finally {
        for (const [name, original] of Object.entries(originals)) fs[name] = original;
        syncBuiltinESMExports();
        for (const fd of active.keys()) originals.closeSync(fd);
    }
}

const open = f => sdk.OpenTideConstants.open({ release: f.date, cacheDir: f.root, offline: true, mode: 'stream' });
const diskDir = (f, overrides = {}) => ({
    read: name => nodeRuntime.readIfExists(path.join(f.dir, name)),
    size: name => nodeRuntime.statSize(path.join(f.dir, name)),
    lineReader: name => nodeRuntime.openLineReader(path.join(f.dir, name)),
    writeIndex: bytes => nodeRuntime.writeAtomicSync(path.join(f.dir, 'index-v1.json'), bytes),
    removeIndex: () => nodeRuntime.removeFileSync(path.join(f.dir, 'index-v1.json')),
    ...overrides,
});

function retainIndexSpecimen(f, name) {
    if (!process.env.OTC_INDEX_PROOF) return;
    const dir = path.join(process.env.OTC_INDEX_PROOF, name);
    fs.mkdirSync(dir, { recursive: true });
    for (const file of [`OTC_${f.date}.jsonl`, `OTC_${f.date}.meta.json`, 'index-v1.json']) {
        fs.copyFileSync(path.join(f.dir, file), path.join(dir, file));
    }
}

async function acquisition(body, { missing = null, sourceName = 'good', date = '20991231.2' } = {}) {
    const source = new URL(`../../conformance/fixtures/${sourceName}/`, import.meta.url).pathname;
    const stem = `OTC_${date}`;
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'otc-native-receipt-'));
    const dir = path.join(root, 'v1', 'releases', date);
    const originals = Object.fromEntries(['json', 'json.gz', 'jsonl', 'meta.json', 'sha256'].map(suffix => {
        const name = `${stem}.${suffix}`;
        return [name, fs.readFileSync(path.join(source, name))];
    }));
    if (missing) originals[`${stem}.sha256`] = Buffer.from(originals[`${stem}.sha256`].toString().split('\n').filter(line => !line.endsWith(`  ${stem}.${missing}`)).join('\n'));
    const requests = [], publications = [], lockReads = [];
    const server = createServer((request, response) => {
        requests.push(request.url);
        const bytes = originals[request.url.slice(1)];
        response.writeHead(bytes ? 200 : 404);
        response.end(bytes ?? 'not found');
    });
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    const baseUrl = `http://127.0.0.1:${server.address().port}/`;
    const rename = fs.renameSync, read = fs.readFileSync;
    fs.renameSync = (from, to) => { rename(from, to); publications.push(String(to)); };
    fs.readFileSync = (file, ...args) => {
        if (String(file) === path.join(dir, '.verified')) lockReads.push(fs.existsSync(path.join(dir, '.lock', 'owner.json')));
        return read(file, ...args);
    };
    syncBuiltinESMExports();
    try {
        return await body({ root, dir, date, stem, originals, requests, publications, lockReads,
            open: mode => sdk.OpenTideConstants.open({ release: date, cacheDir: root, baseUrl, mode, onNetworkError: 'raise' }) });
    } finally {
        fs.renameSync = rename; fs.readFileSync = read; syncBuiltinESMExports();
        await new Promise(resolve => server.close(resolve));
        fs.rmSync(root, { recursive: true, force: true });
    }
}

function receiptWitness(f, label) {
    const bytes = fs.readFileSync(path.join(f.dir, '.verified'));
    const receipt = JSON.parse(bytes);
    const sourceHashes = {};
    for (const name of [...Object.keys(receipt.files), `${f.stem}.sha256`]) {
        const cached = fs.readFileSync(path.join(f.dir, name));
        sourceHashes[name] = hash(cached);
        assert.deepEqual(cached, f.originals[name], name);
    }
    console.log(JSON.stringify({ surface: 'native public acquisition', label, receipt_hex: bytes.toString('hex'), sourceHashes,
        requests: f.requests, publications: f.publications.map(file => path.relative(f.dir, file)), lockedReceiptReads: f.lockReads }));
    if (process.env.OTC_RECEIPT_PROOF) {
        const destination = path.join(process.env.OTC_RECEIPT_PROOF, label);
        fs.mkdirSync(destination, { recursive: true });
        for (const name of ['.verified', ...Object.keys(sourceHashes)]) fs.copyFileSync(path.join(f.dir, name), path.join(destination, name));
    }
    assert.deepEqual(Object.keys(receipt).sort(), ['by', 'datestamp', 'files', 'format_version', 'min_reader_version', 'verified_at', 'zenodo_version_doi']);
    assert.deepEqual(bytes, Buffer.from(encodeCacheJson(receipt)));
    assert.ok(!(`${f.stem}.sha256` in receipt.files));
    for (const [name, row] of Object.entries(receipt.files)) {
        assert.deepEqual(Object.keys(row).sort(), ['sha256', 'size', 'url']);
        assert.equal(row.sha256, sourceHashes[name]);
        assert.equal(row.size, f.originals[name].length);
        assert.ok(row.url === null || typeof row.url === 'string');
    }
    const dataPublications = f.publications.filter(file => path.dirname(file) === f.dir);
    assert.equal(path.basename(dataPublications.at(-1)), '.verified', 'receipt publishes after checked data and sidecar');
    assert.ok(f.lockReads.includes(true), 'receipt reread actually reached the acquired native lock');
    return receipt;
}

test('RECEIPT-TS native two-mode exact receipt and public warm reload retain source', async () => {
    await acquisition(async f => {
        const eager = await f.open('eager'); eager.close();
        const first = receiptWitness(f, 'eager');
        assert.deepEqual(Object.keys(first.files), [`${f.stem}.json`]);
        first.zenodo_version_doi = '10.5281/zenodo.known';
        first.files[`${f.stem}.json`].url = null;
        fs.writeFileSync(path.join(f.dir, '.verified'), encodeCacheJson(first));
        const stream = await f.open('stream');
        try {
            const rows = f.originals[`${f.stem}.jsonl`].toString().trimEnd().split('\n').map(line => JSON.parse(line));
            for (const row of rows.filter(row => row.status !== 'removed')) assert.deepEqual(stream.requireStation(row.station_id).raw, row);
        } finally { stream.close(); }
        // The stream index is a later dependency publication, outside the acquisition's receipt ordering.
        f.publications.splice(f.publications.findLastIndex(file => file.endsWith('/.verified')) + 1);
        const merged = receiptWitness(f, 'eager-to-stream');
        assert.equal(merged.zenodo_version_doi, first.zenodo_version_doi);
        assert.equal(merged.files[`${f.stem}.json`].url, null);
        assert.equal(Object.keys(merged.files).length, 3);
        const bytes = fs.readFileSync(path.join(f.dir, '.verified'));
        const warm = await f.open('eager');
        try { assert.equal(warm.loadedFrom, 'cache'); assert.equal(await warm.verify(), true); }
        finally { warm.close(); }
        assert.deepEqual(fs.readFileSync(path.join(f.dir, '.verified')), bytes);
    });
    await acquisition(async f => {
        const stream = await f.open('stream'); stream.close();
        f.publications.splice(f.publications.findLastIndex(file => file.endsWith('/.verified')) + 1);
        receiptWitness(f, 'stream');
        const requestCount = f.requests.length;
        const eager = await f.open('eager');
        try { assert.equal(eager.loadedFrom, 'cache'); assert.equal(await eager.verify(), true); }
        finally { eager.close(); }
        assert.equal(f.requests.length, requestCount, 'stream-to-eager reuses verified stream files');
    });
});

test('RECEIPT-TS native readable higher minor source format is retained in receipt', async () => {
    for (const mode of ['eager', 'stream']) {
        await acquisition(async f => {
            const client = await f.open(mode);
            try { assert.equal(client.release.format_version, '1.1'); }
            finally { client.close(); }
            f.publications.splice(f.publications.findLastIndex(file => file.endsWith('/.verified')) + 1);
            const receipt = receiptWitness(f, `higher-minor-${mode}`);
            assert.equal(receipt.format_version, '1.1');
            assert.equal(receipt.min_reader_version, '1.0');
        }, { sourceName: 'bad/format-minor', date: '20991231' });
    }
});

for (const state of ['malformed', 'absent']) {
    test(`RECEIPT-TS native ${state} locked reread discards untrusted old rows and DOI`, async () => {
        await acquisition(async f => {
            const eager = await f.open('eager'); eager.close();
            const before = JSON.parse(fs.readFileSync(path.join(f.dir, '.verified')));
            before.zenodo_version_doi = '10.5281/zenodo.old';
            fs.writeFileSync(path.join(f.dir, '.verified'), encodeCacheJson(before));
            const mkdir = fsp.mkdir;
            let replaced = false;
            fsp.mkdir = async (...args) => {
                const result = await mkdir(...args);
                if (String(args[0]) === path.join(f.dir, '.lock')) {
                    if (state === 'malformed') fs.writeFileSync(path.join(f.dir, '.verified'), '{broken');
                    else fs.rmSync(path.join(f.dir, '.verified'));
                    replaced = true;
                }
                return result;
            };
            syncBuiltinESMExports();
            try { const stream = await f.open('stream'); stream.close(); }
            finally { fsp.mkdir = mkdir; syncBuiltinESMExports(); }
            assert.equal(replaced, true, 'fault injected only after real release lock mkdir succeeds');
            f.publications.splice(f.publications.findLastIndex(file => file.endsWith('/.verified')) + 1);
            const receipt = receiptWitness(f, `locked-${state}`);
            assert.equal(receipt.zenodo_version_doi, null);
            assert.deepEqual(Object.keys(receipt.files).sort(), [`${f.stem}.jsonl`, `${f.stem}.meta.json`]);
        });
    });
}

for (const missing of ['jsonl', 'meta.json']) {
    test(`RECEIPT-TS native missing ${missing} checksum row refuses before data acquisition`, async () => {
        await acquisition(async f => {
            await assert.rejects(f.open('stream'), error => error.code === 'checksum_mismatch' && error.file === `${f.stem}.${missing}`);
            console.log(JSON.stringify({ surface: 'public stream missing checksum row', missing, requests: f.requests, publications: f.publications }));
            assert.deepEqual(f.requests, [`/${f.stem}.sha256`], 'all required rows bind before any data request');
            assert.equal(fs.existsSync(path.join(f.dir, '.verified')), false);
        }, { missing });
    });
}

test('RECEIPT-TS native stale index is deleted before actual rebuild publication', () => {
    const good = new URL('../../conformance/fixtures/good/', import.meta.url);
    const f = fixture(fs.readFileSync(new URL('OTC_20991231.2.jsonl', good)), '20991231.2', good.pathname);
    try {
        const indexPath = path.join(f.dir, 'index-v1.json');
        fs.writeFileSync(indexPath, '{broken');
        const events = [], native = diskDir(f);
        const rel = loadCached(diskDir(f, {
            removeIndex: () => { events.push('remove'); native.removeIndex(); },
            writeIndex: bytes => { events.push({ action: 'write', staleIndexStillPresent: fs.existsSync(indexPath) }); native.writeIndex(bytes); },
        }), f.verified, f.date, 'stream');
        rel._close();
        console.log(JSON.stringify({ surface: 'core stale index rebuild', events, contract: 'delete stale index before rebuild' }));
        assert.deepEqual(events, ['remove', { action: 'write', staleIndexStillPresent: false }]);
        assert.deepEqual(fs.readFileSync(path.join(f.dir, `OTC_${f.date}.jsonl`)), f.jsonl);
        assert.deepEqual(fs.readFileSync(path.join(f.dir, `OTC_${f.date}.meta.json`)), f.meta);
    } finally { f.cleanup(); }
});

test('INDEX-TS actual current writer projects four offset keys', async () => {
    const predict = new URL('../../conformance/fixtures/predict/', import.meta.url);
    const f = fixture(fs.readFileSync(new URL('OTC_20991231.7.jsonl', predict)), '20991231.7', predict.pathname);
    try {
        const client = await open(f);
        try {
            const index = JSON.parse(fs.readFileSync(path.join(f.dir, 'index-v1.json')));
            retainIndexSpecimen(f, 'current');
            const offsets = index.stations.find(row => row.station_id === 'OTC-P-0050').current_offsets;
            assert.ok(offsets.length > 0);
            for (const row of offsets) assert.deepEqual(Object.keys(row).sort(), ['bin', 'licence_id', 'reference_bin', 'reference_station_id']);
            assert.deepEqual(client.requireStation('OTC-P-0050').raw, JSON.parse(f.jsonl.toString().split('\n').find(line => line.includes('"OTC-P-0050"'))));
        } finally { client.close(); }
    } finally { f.cleanup(); }
});

test('INDEX-TS native original span retains lone terminal CR', async () => {
    const good = new URL('../../conformance/fixtures/good/', import.meta.url);
    const original = fs.readFileSync(new URL('OTC_20991231.2.jsonl', good));
    const jsonl = Buffer.concat([Buffer.from(' \t\v\f\r\n'), original.subarray(0, original.length - 1), Buffer.from('\r')]);
    const f = fixture(jsonl, '20991231.2', good.pathname);
    try {
        const client = await open(f);
        try {
            const index = JSON.parse(fs.readFileSync(path.join(f.dir, 'index-v1.json')));
            retainIndexSpecimen(f, 'lone-cr');
            const last = index.stations.at(-1);
            assert.equal(last.offset + last.length, jsonl.length, 'terminal CR belongs to original body without LF');
            assert.equal(indexJsonl(headerFromMeta(f.meta), jsonl, false).entries.at(-1).length, last.length);
            assert.deepEqual(client.requireStation(index.stations[0].station_id).raw, JSON.parse(original.toString().split('\n')[0]));
        } finally { client.close(); }
    } finally { f.cleanup(); }
});

test('INDEX-TS native represented station name tamper refuses and removes index', async () => {
    const good = new URL('../../conformance/fixtures/good/', import.meta.url);
    const f = fixture(fs.readFileSync(new URL('OTC_20991231.2.jsonl', good)), '20991231.2', good.pathname);
    try {
        const initial = await open(f); initial.close();
        retainIndexSpecimen(f, 'tide');
        const index = JSON.parse(fs.readFileSync(path.join(f.dir, 'index-v1.json')));
        index.stations[0].name = 'represented tamper';
        index.stations[0].name_folded = 'represented tamper';
        fs.writeFileSync(path.join(f.dir, 'index-v1.json'), JSON.stringify(index));
        const client = await open(f);
        try {
            assert.throws(() => client.requireStation(index.stations[0].station_id), error => error.code === 'invalid_release' && error.message.includes('index-v1.json'));
            assert.equal(fs.existsSync(path.join(f.dir, 'index-v1.json')), false);
            assert.ok(fs.existsSync(path.join(f.dir, '.verified')));
        } finally { client.close(); }
    } finally { f.cleanup(); }
});

test('INDEX-TS native represented legacy offset depth tamper refuses', async () => {
    const predict = new URL('../../conformance/fixtures/predict/', import.meta.url);
    const f = fixture(fs.readFileSync(new URL('OTC_20991231.7.jsonl', predict)), '20991231.7', predict.pathname);
    try {
        const specimen = process.env.OTC_INDEX_LEGACY_SPECIMEN;
        const initial = await open(f); initial.close();
        const index = JSON.parse(fs.readFileSync(specimen ?? path.join(f.dir, 'index-v1.json')));
        if (!specimen) {
            // Reader compatibility control for the former native writer's full source-offset profile.
            const sourceRows = f.jsonl.toString().trimEnd().split('\n').map(line => JSON.parse(line));
            for (const entry of index.stations) entry.current_offsets = sourceRows.find(row => row.station_id === entry.station_id).current_offsets ?? [];
        }
        const row = index.stations.find(entry => entry.station_id === 'OTC-P-0050');
        assert.equal(index.jsonl_sha256, hash(f.jsonl), 'retained actual baseline writer has identical source bytes');
        const depth = row.current_offsets[0].depth_m;
        assert.equal(typeof depth, 'number');
        row.current_offsets[0].depth_m += 1;
        fs.writeFileSync(path.join(f.dir, 'index-v1.json'), JSON.stringify(index));
        const client = await open(f);
        try {
            assert.throws(() => client.requireStation('OTC-P-0050'), error => error.code === 'invalid_release' && error.message.includes('index-v1.json'));
            assert.equal(fs.existsSync(path.join(f.dir, 'index-v1.json')), false);
        } finally { client.close(); }
        if (process.env.OTC_INDEX_BOUNDARY) {
            fs.writeFileSync(path.join(f.dir, 'index-v1.json'), '{broken');
            const indexPath = path.join(f.dir, 'index-v1.json');
            const events = [];
            const native = diskDir(f);
            const rel = loadCached(diskDir(f, {
                removeIndex: () => { events.push('remove'); native.removeIndex(); },
                writeIndex: bytes => {
                    events.push({ action: 'write', staleIndexStillPresent: fs.existsSync(indexPath) });
                    native.writeIndex(bytes);
                },
            }), f.verified, f.date, 'stream');
            rel._close();
            console.log(JSON.stringify({ surface: 'core stale index rebuild', events, contract: 'delete stale index before rebuild', status: events[0] === 'remove' ? 'GREEN' : 'RED', dependency: 'read-only js/src/core.ts' }));
        }
    } finally { f.cleanup(); }
});

test('INDEX-TS native represented absent unknown offset null refuses', async () => {
    const predict = new URL('../../conformance/fixtures/predict/', import.meta.url);
    const f = fixture(fs.readFileSync(new URL('OTC_20991231.7.jsonl', predict)), '20991231.7', predict.pathname);
    try {
        const initial = await open(f); initial.close();
        const index = JSON.parse(fs.readFileSync(path.join(f.dir, 'index-v1.json')));
        index.stations.find(row => row.station_id === 'OTC-P-0050').current_offsets[0].future_null = null;
        fs.writeFileSync(path.join(f.dir, 'index-v1.json'), JSON.stringify(index));
        const client = await open(f);
        try {
            assert.throws(() => client.requireStation('OTC-P-0050'), error => error.code === 'invalid_release' && error.message.includes('index-v1.json'));
            assert.equal(fs.existsSync(path.join(f.dir, 'index-v1.json')), false);
        } finally { client.close(); }
    } finally { f.cleanup(); }
});

test('INDEX-TS native cold source name tamper refuses', async () => {
    const good = new URL('../../conformance/fixtures/good/', import.meta.url);
    const f = fixture(fs.readFileSync(new URL('OTC_20991231.2.jsonl', good)), '20991231.2', good.pathname);
    try {
        const client = await open(f);
        try {
            const row = JSON.parse(f.jsonl.toString().split('\n')[0]);
            const token = Buffer.from(JSON.stringify(row.name));
            const at = f.jsonl.indexOf(token);
            assert.ok(at >= 0);
            const changed = Buffer.from(f.jsonl);
            // Alter one ASCII byte in the private copied source, preserving the exact original span and file size.
            const letter = token.findIndex((byte, i) => i > 0 && byte >= 65 && byte <= 122);
            assert.ok(letter > 0);
            changed[at + letter] = token[letter] === 88 ? 89 : 88;
            fs.writeFileSync(path.join(f.dir, 'OTC_20991231.2.jsonl'), changed);
            assert.throws(() => client.requireStation(row.station_id), error => error.code === 'invalid_release' && error.message.includes('index-v1.json'));
            assert.equal(fs.existsSync(path.join(f.dir, 'index-v1.json')), false);
        } finally { client.close(); }
    } finally { f.cleanup(); }
});

test('INDEX-TS native ASCII framing and nonblank byte refusals', async () => {
    const good = new URL('../../conformance/fixtures/good/', import.meta.url);
    const original = fs.readFileSync(new URL('OTC_20991231.2.jsonl', good));
    const framed = Buffer.from(` \t\v\f\r\n${original.toString().replaceAll('\n', '\r\n \t\v\f\r\n')}`);
    const sourceRows = original.toString().trimEnd().split('\n').map(line => JSON.parse(line));
    const f = fixture(framed, '20991231.2', good.pathname);
    try {
        const client = await open(f);
        try {
            const index = JSON.parse(fs.readFileSync(path.join(f.dir, 'index-v1.json')));
            for (const entry of index.stations) {
                assert.equal(framed[entry.offset + entry.length], 13);
                assert.equal(framed[entry.offset + entry.length + 1], 10);
                const value = entry.status === 'active' ? client.requireStation(entry.station_id) : client.tombstone(entry.station_id);
                assert.deepEqual(value.raw, sourceRows.find(row => row.station_id === entry.station_id));
            }
            assert.deepEqual(fs.readFileSync(path.join(f.dir, 'OTC_20991231.2.jsonl')), framed);
        } finally { client.close(); }
    } finally { f.cleanup(); }
    for (const body of [Buffer.from('\u00a0\n'), Buffer.from([0, 10])]) {
        const invalid = fixture(Buffer.concat([original, body]), '20991231.2', good.pathname);
        try { await assert.rejects(open(invalid), error => error.code === 'invalid_release'); }
        finally { invalid.cleanup(); }
    }
});

test('native Node cached stream shared foreign presence profiles', async () => {
    const proof = '/Users/jpr5/.local/share/copilotkit/cr/otc-codex-takeover/execution/sdk-core-sync/proofs/G0/cross-final-deps/native-specimens';
    const good = new URL('../../conformance/fixtures/good/', import.meta.url);
    const date = '20991231.2', stem = `OTC_${date}`;
    const meta = fs.readFileSync(new URL(`${stem}.meta.json`, good));
    const jsonl = fs.readFileSync(new URL(`${stem}.jsonl`, good));
    const header = headerFromMeta(meta);
    const conventions = new Set(header.conventions.map(row => row.convention_id));
    const licences = new Set(header.licences.map(row => row.licence_id));
    const accepts = index => usableIndex(index, date, hash(jsonl), jsonl.length, conventions, licences);
    for (const language of ['ruby', 'c', 'python', 'typescript']) {
        const bytes = fs.readFileSync(path.join(proof, `${language}-index-v1.json`));
        const original = JSON.parse(bytes);
        const root = fs.mkdtempSync(path.join(os.tmpdir(), 'otc-shared-native-'));
        const dir = path.join(root, 'v1/releases', date);
        fs.mkdirSync(dir, { recursive: true });
        try {
            const files = {};
            for (const [name, body] of [[`${stem}.jsonl`, jsonl], [`${stem}.meta.json`, meta]]) {
                fs.writeFileSync(path.join(dir, name), body);
                files[name] = { sha256: hash(body), size: body.length, url: null };
            }
            fs.writeFileSync(path.join(dir, '.verified'), JSON.stringify({ datestamp: date, format_version: '1.0', files }));
            fs.copyFileSync(new URL(`${stem}.sha256`, good), path.join(dir, `${stem}.sha256`));
            fs.writeFileSync(path.join(dir, 'index-v1.json'), bytes);
            await observe(async receipts => {
                const client = await sdk.OpenTideConstants.open({ release: date, cacheDir: root, offline: true, mode: 'stream' });
                try {
                    assert.equal(receipts.reads.filter(row => row.file?.endsWith('.jsonl')).length, 0, `${language}: valid foreign index stays lazy`);
                    assert.deepEqual(fs.readFileSync(path.join(dir, 'index-v1.json')), bytes);
                    assert.throws(() => client.stations({ country: 'ZZ', includeFlagged: true, includeFallback: true }), error => error.code === 'invalid_release' && error.message.includes('index-v1.json'));
                    assert.equal(fs.existsSync(path.join(dir, 'index-v1.json')), false, `${language}: represented country tamper removes the index`);
                    assert.deepEqual(client.requireStation('OTC-T-0001').raw, JSON.parse(jsonl.toString().split('\n')[0]));
                } finally { client.close(); }
                assert.equal(receipts.active.size, 0);
            });
            assert.notEqual(accepts(original), null);
            for (const marker of [null, true, '1', 0, 1.5, 2]) {
                const invalid = structuredClone(original);
                invalid.discovery_index_version = marker;
                assert.equal(accepts(invalid), null, `${language}: invalid present marker ${marker}`);
            }
            const missingKey = structuredClone(original);
            delete missingKey.stations[0].reference_station_id;
            assert.equal(accepts(missingKey), null, 'mandatory missing key is never defaulted');
            if (language === 'ruby') {
                for (const key of ['source_record_id', 'source_version', 'datum']) {
                    const partial = structuredClone(original);
                    delete partial.stations[0].sets[0][key];
                    assert.equal(accepts(partial), null, `partial private ${key}`);
                }
                const mixed = structuredClone(original);
                for (const key of ['source_record_id', 'source_version', 'datum']) delete mixed.stations[0].sets[0][key];
                assert.equal(accepts(mixed), null, 'mixed private profile is stale');
                const stripped = structuredClone(original);
                for (const row of stripped.stations) for (const set of row.sets) for (const key of ['source_record_id', 'source_version', 'datum']) delete set[key];
                assert.notEqual(accepts(stripped), null, 'total private removal is structurally foreign, not authenticated');
                const tampered = structuredClone(original);
                tampered.stations[0].sets[0].source_record_id += ':tampered';
                fs.writeFileSync(path.join(dir, 'index-v1.json'), JSON.stringify(tampered));
                const client = await sdk.OpenTideConstants.open({ release: date, cacheDir: root, offline: true, mode: 'stream' });
                try {
                    assert.throws(() => client.requireStation(tampered.stations[0].station_id), error => error.code === 'invalid_release' && error.message.includes('index-v1.json'));
                    assert.equal(fs.existsSync(path.join(dir, 'index-v1.json')), false);
                    assert.ok(fs.existsSync(path.join(dir, '.verified')));
                } finally { client.close(); }
            }
        } finally { fs.rmSync(root, { recursive: true, force: true }); }
    }
});

test('native Node cached stream shared current offset presence', async () => {
    const predict = new URL('../../conformance/fixtures/predict/', import.meta.url);
    const date = '20991231.7', stem = `OTC_${date}`;
    const f = fixture(fs.readFileSync(new URL(`${stem}.jsonl`, predict)), date, predict.pathname);
    try {
        const initial = await open(f);
        initial.close();
        const full = JSON.parse(fs.readFileSync(path.join(f.dir, 'index-v1.json')));
        // Retain the old complete native offset profile as a reader control after the writer becomes compact.
        const sourceRows = f.jsonl.toString().trimEnd().split('\n').map(line => JSON.parse(line));
        for (const entry of full.stations) entry.current_offsets = sourceRows.find(row => row.station_id === entry.station_id).current_offsets ?? [];
        const header = headerFromMeta(f.meta);
        const conventions = new Set(header.conventions.map(row => row.convention_id));
        const licences = new Set(header.licences.map(row => row.licence_id));
        const accepts = index => usableIndex(index, date, hash(f.jsonl), f.jsonl.length, conventions, licences);
        const adjustments = ['time_adj_max_flood_min', 'time_adj_max_ebb_min', 'time_adj_slack_before_flood_min', 'time_adj_slack_before_ebb_min', 'flood_amp_ratio', 'ebb_amp_ratio'];
        const projected = structuredClone(full);
        for (const entry of projected.stations) for (const row of entry.current_offsets) for (const key of adjustments) delete row[key];
        assert.notEqual(accepts(full), null);
        assert.notEqual(accepts(projected), null);
        for (const shape of [full, projected]) {
            fs.writeFileSync(path.join(f.dir, 'index-v1.json'), JSON.stringify(shape));
            const bytes = fs.readFileSync(path.join(f.dir, 'index-v1.json'));
            await observe(async receipts => {
                const client = await open(f);
                try {
                    assert.equal(receipts.reads.filter(row => row.file?.endsWith('.jsonl')).length, 0);
                    assert.deepEqual(client.requireStation('OTC-P-0050').raw, JSON.parse(f.jsonl.toString().trimEnd().split('\n').find(line => JSON.parse(line).station_id === 'OTC-P-0050')));
                    assert.deepEqual(fs.readFileSync(path.join(f.dir, 'index-v1.json')), bytes);
                } finally { client.close(); }
                assert.equal(receipts.active.size, 0);
            });
        }
        const partial = structuredClone(full);
        delete partial.stations.find(entry => entry.station_id === 'OTC-P-0050').current_offsets[0].ebb_amp_ratio;
        assert.equal(accepts(partial), null);
        const missingBase = structuredClone(projected);
        delete missingBase.stations.find(entry => entry.station_id === 'OTC-P-0050').current_offsets[0].reference_bin;
        assert.equal(accepts(missingBase), null);
        const badBin = structuredClone(projected);
        badBin.stations.find(entry => entry.station_id === 'OTC-P-0050').current_offsets[0].bin = 1.5;
        assert.equal(accepts(badBin), null);
        const tampered = structuredClone(full);
        tampered.stations.find(entry => entry.station_id === 'OTC-P-0050').current_offsets[0].ebb_amp_ratio += 0.1;
        fs.writeFileSync(path.join(f.dir, 'index-v1.json'), JSON.stringify(tampered));
        const client = await open(f);
        try {
            assert.throws(() => client.requireStation('OTC-P-0050'), error => error.code === 'invalid_release' && error.message.includes('index-v1.json'));
            assert.equal(fs.existsSync(path.join(f.dir, 'index-v1.json')), false);
            assert.ok(fs.existsSync(path.join(f.dir, '.verified')));
        } finally { client.close(); }
    } finally { f.cleanup(); }
});

test('native Node cached stream shared base policy hydration stays bounded', async () => {
    const f = fixture();
    try {
        const initial = await open(f);
        const flags = [{}, { includeFlagged: true }, { includeFallback: true }, { includeFlagged: true, includeFallback: true }];
        const expected = flags.map(options => initial.stations(options).map(row => row.station_id));
        initial.close();
        const full = JSON.parse(fs.readFileSync(path.join(f.dir, 'index-v1.json')));
        const base = structuredClone(full);
        delete base.discovery_index_version;
        for (const entry of base.stations) {
            delete entry.subordinate_offsets;
            for (const set of entry.sets) {
                delete set.fallback;
                delete set.current_bins;
            }
        }
        fs.writeFileSync(path.join(f.dir, 'index-v1.json'), JSON.stringify(base));
        const originalIndex = fs.readFileSync(path.join(f.dir, 'index-v1.json'));
        await observe(async receipts => {
            const client = await open(f);
            try {
                const reads = () => receipts.reads.filter(row => row.file?.endsWith('.jsonl'));
                assert.equal(reads().length, 0, 'base metadata stays uncached until a policy query');
                assert.deepEqual(client.stations({ country: 'no-such-country' }), []);
                assert.equal(reads().length, 0, 'unselected stations are not hydrated');
                for (let i = 0; i < flags.length; i++) assert.deepEqual(client.stations(flags[i]).map(row => row.station_id), expected[i]);
                const referenceOffsets = new Set(full.stations.filter(row => full.stations.some(entry => entry.subordinate_offsets?.offset_id && entry.reference_station_id === row.station_id)).map(row => row.offset));
                const policyReads = () => reads().filter(row => !referenceOffsets.has(row.position)).length;
                const after = policyReads();
                client.stations({});
                assert.equal(policyReads(), after, 'compact policy summaries avoid repeat reads; existing source-binding reference checks remain');
                for (const id of ['OTC-28c56e20', 'OTC-541f1a73', 'OTC-a6c00a3f']) {
                    assert.deepEqual(client.requireStation(id).raw, JSON.parse(f.jsonl.toString().trimEnd().split('\n').find(line => JSON.parse(line).station_id === id)));
                }
                assert.ok(!receipts.bodies.includes(path.join(f.dir, `${stem}.jsonl`)), 'no complete source read retained');
                assert.deepEqual(fs.readFileSync(path.join(f.dir, 'index-v1.json')), originalIndex);
                assert.deepEqual(fs.readFileSync(path.join(f.dir, `${stem}.jsonl`)), f.jsonl);
            } finally { client.close(); }
            assert.equal(receipts.active.size, 0);
        });
    } finally { f.cleanup(); }
});

test('native Node cached stream legacy malformed lines stay lazy', async () => {
    const casesRoot = new URL('../../conformance/', import.meta.url);
    const rules = JSON.parse(fs.readFileSync(new URL('cases/rules.json', casesRoot))).cases;
    for (const suffix of ['qc-flags', 'unresolved-convention']) {
        const rule = rules.find(row => row.id === `rules/r2-pk07/index-line-${suffix}`);
        const root = fs.mkdtempSync(path.join(os.tmpdir(), 'otc-legacy-index-'));
        const dir = path.join(root, 'v1/releases/20991231');
        fs.mkdirSync(dir, { recursive: true });
        try {
            for (const file of rule.steps[0].files) {
                const source = new URL(file.replace('${fixtures}/', 'fixtures/'), casesRoot);
                fs.copyFileSync(source, path.join(dir, path.basename(source.pathname)));
            }
            for (const step of rule.steps.filter(step => step.driver === 'write')) {
                fs.writeFileSync(step.path.replace('${cache}', root), step.text);
            }
            const before = fs.readFileSync(path.join(dir, '.verified'));
            await observe(async receipts => {
                const client = await sdk.OpenTideConstants.open({ release: '20991231', cacheDir: root, offline: true, mode: 'stream' });
                try {
                    assert.equal(receipts.reads.filter(row => row.file?.endsWith('.jsonl')).length, 0);
                    const lines = fs.readFileSync(path.join(dir, 'OTC_20991231.jsonl'), 'utf8').trimEnd().split('\n').map(line => JSON.parse(line));
                    assert.deepEqual(client.requireStation('OTC-T-0003').raw, lines.find(line => line.station_id === 'OTC-T-0003'));
                    const badId = rule.steps.find(step => step.op === 'station').args.station_id;
                    assert.throws(() => client.requireStation(badId), error => error.code === 'invalid_release' && error.message.includes('index-v1.json'));
                    assert.equal(fs.existsSync(path.join(dir, 'index-v1.json')), false);
                    assert.deepEqual(fs.readFileSync(path.join(dir, '.verified')), before);
                } finally { client.close(); }
                assert.equal(receipts.active.size, 0);
            });
            await assert.rejects(sdk.OpenTideConstants.open({ release: '20991231', cacheDir: root, offline: true, mode: 'stream' }), error => error.code === 'invalid_release');
        } finally { fs.rmSync(root, { recursive: true, force: true }); }
    }
});

test('native Node cached stream legacy projection keeps expanded offsets strict', async () => {
    const f = fixture();
    try {
        const header = headerFromMeta(f.meta);
        const entries = indexJsonl(header, f.jsonl, false).entries;
        const expanded = storedIndex(entries, date, hash(f.jsonl), f.jsonl.length, 'test');
        const conventions = new Set(header.conventions.map(row => row.convention_id));
        const licences = new Set(header.licences.map(row => row.licence_id));
        const accepts = index => usableIndex(index, date, hash(f.jsonl), f.jsonl.length, conventions, licences);
        const partial = structuredClone(expanded);
        delete partial.stations.find(row => row.station_id === 'OTC-28c56e20').subordinate_offsets;
        assert.equal(accepts(partial), null, 'mixed expanded own-field deletion must stay stale');
        fs.writeFileSync(path.join(f.dir, 'index-v1.json'), JSON.stringify(partial));
        await observe(async receipts => {
            const client = await open(f);
            try {
                assert.ok(receipts.reads.some(row => row.file?.endsWith('.jsonl')), 'partial own-field deletion rebuilds from real lines');
                assert.deepEqual(JSON.parse(fs.readFileSync(path.join(f.dir, 'index-v1.json'))).stations, expanded.stations);
            } finally { client.close(); }
            assert.equal(receipts.active.size, 0);
        });
        const legacy = structuredClone(expanded);
        for (const entry of legacy.stations) delete entry.subordinate_offsets;
        fs.writeFileSync(path.join(f.dir, 'index-v1.json'), JSON.stringify(legacy));
        const before = fs.readFileSync(path.join(f.dir, 'index-v1.json'));
        await observe(async receipts => {
            const client = await open(f);
            try {
                assert.equal(receipts.reads.filter(row => row.file?.endsWith('.jsonl')).length, 0);
                for (const id of ['OTC-28c56e20', 'OTC-541f1a73', entries[0].station_id]) {
                    assert.deepEqual(client.requireStation(id).raw, JSON.parse(f.jsonl.toString().trimEnd().split('\n').find(line => JSON.parse(line).station_id === id)));
                }
                assert.deepEqual(fs.readFileSync(path.join(f.dir, 'index-v1.json')), before, 'projection must not add on-disk keys');
            } finally { client.close(); }
            assert.equal(receipts.active.size, 0);
        });
        const tampered = structuredClone(expanded);
        tampered.stations.find(row => row.station_id === 'OTC-28c56e20').subordinate_offsets.fallback.basis += ' changed';
        assert.notEqual(accepts(tampered), null, 'valid expanded summary still requires a matching full own-offset line');
        fs.writeFileSync(path.join(f.dir, 'index-v1.json'), JSON.stringify(tampered));
        const client = await open(f);
        try {
            assert.throws(() => client.requireStation('OTC-28c56e20'), error => error.code === 'invalid_release' && error.message.includes('index-v1.json'));
            assert.equal(fs.existsSync(path.join(f.dir, 'index-v1.json')), false);
            assert.ok(fs.existsSync(path.join(f.dir, '.verified')));
        } finally { client.close(); }
        const wrongHistoricalValue = structuredClone(expanded);
        wrongHistoricalValue.stations.find(row => row.station_id === 'OTC-28c56e20').subordinate_offsets.time_offset_high_min += 1;
        assert.equal(accepts(wrongHistoricalValue), null, 'source-bound historical numeric validation is unchanged');
        const basis = entries.find(entry => entry.station_id === 'OTC-28c56e20').stored.subordinate_offsets.fallback.basis;
        const changedLine = fixture(Buffer.from(f.jsonl.toString().replace(basis, `B${basis.slice(1)}`)));
        try {
            const originalSummary = structuredClone(expanded);
            originalSummary.jsonl_sha256 = hash(changedLine.jsonl);
            fs.writeFileSync(path.join(changedLine.dir, 'index-v1.json'), JSON.stringify(originalSummary));
            const originalVerified = fs.readFileSync(path.join(changedLine.dir, '.verified'));
            await observe(async receipts => {
                const client = await open(changedLine);
                try {
                    assert.equal(receipts.reads.filter(row => row.file?.endsWith('.jsonl')).length, 0);
                    assert.throws(() => client.requireStation('OTC-28c56e20'), error => error.code === 'invalid_release' && error.message.includes('index-v1.json'));
                    assert.equal(fs.existsSync(path.join(changedLine.dir, 'index-v1.json')), false);
                    assert.deepEqual(fs.readFileSync(path.join(changedLine.dir, '.verified')), originalVerified);
                    assert.deepEqual(fs.readFileSync(path.join(changedLine.dir, `${stem}.jsonl`)), changedLine.jsonl);
                    assert.deepEqual(fs.readFileSync(path.join(changedLine.dir, `${stem}.meta.json`)), changedLine.meta);
                } finally { client.close(); }
                assert.equal(receipts.active.size, 0);
            });
        } finally { changedLine.cleanup(); }
    } finally { f.cleanup(); }
});

test('native Node cached stream absent-invalid-valid index', async () => {
    const f = fixture();
    try {
        const entries = indexJsonl(headerFromMeta(f.meta), f.jsonl, false).entries;
        for (const variant of ['absent', 'invalid', 'valid']) {
            if (variant === 'absent') fs.rmSync(path.join(f.dir, 'index-v1.json'), { force: true });
            if (variant === 'invalid') fs.writeFileSync(path.join(f.dir, 'index-v1.json'), '{broken');
            await observe(async receipts => {
                const client = await open(f);
                try {
                    assert.equal(client.loadedFrom, 'cache');
                    assert.deepEqual(JSON.parse(fs.readFileSync(path.join(f.dir, 'index-v1.json'), 'utf8')).stations,
                        storedIndex(entries, date, hash(f.jsonl), f.jsonl.length, 'test').stations);
                    if (variant === 'absent') retainIndexSpecimen(f, 'history');
                    assert.ok(!receipts.bodies.includes(path.join(f.dir, `${stem}.jsonl`)), 'cached index rebuild must not read whole JSONL');
                    const readers = receipts.opened.filter(row => row.file.endsWith('.jsonl'));
                    assert.equal(readers.length, 1, 'same owned reader scans and serves lazy reads');
                    const before = receipts.reads.filter(row => row.file === readers[0].file).length;
                    assert.equal(before === 0, variant === 'valid', 'valid index skips scanning');
                    assert.ok(receipts.reads.filter(row => row.file?.endsWith('.jsonl')).every(row => row.length <= 65536));
                    assert.deepEqual(client.requireStation(entries[0].station_id).raw, JSON.parse(f.jsonl.toString().split('\n')[0]));
                } finally { client.close(); }
                assert.equal(receipts.active.size, 0);
            }, { read: () => 997 });
        }
        const originals = f.jsonl.toString().trimEnd().split('\n');
        for (const bytes of [Buffer.from(`\r\n${originals.join('\r\n\n')}\r\n\n`), Buffer.from(originals.join('\n'))]) {
            const framed = fixture(bytes);
            try {
                const client = await open(framed);
                try { for (const entry of entries) assert.deepEqual(client.requireStation(entry.station_id).raw, JSON.parse(originals.find(line => JSON.parse(line).station_id === entry.station_id))); }
                finally { client.close(); }
            } finally { framed.cleanup(); }
        }
    } finally { f.cleanup(); }
});

test('native Node cached stream reader lifecycle', async () => {
    const f = fixture();
    try {
        await observe(async receipts => {
            const warnings = [];
            const rel = loadCached(diskDir(f, { writeIndex: () => { throw new Error('write-control'); } }), f.verified, date, 'stream', message => warnings.push(message));
            assert.ok(warnings.some(message => message.includes('write-control')));
            assert.equal(receipts.active.size, 1);
            rel._close(); assert.equal(receipts.active.size, 0);
        });
        await observe(async receipts => {
            const changed = diskDir(f, { lineReader: name => { const reader = nodeRuntime.openLineReader(path.join(f.dir, name)); fs.truncateSync(path.join(f.dir, name), 1); return reader; } });
            assert.throws(() => loadCached(changed, f.verified, date, 'stream'), error => error.code === 'checksum_mismatch' && error.file === `${stem}.jsonl`);
            assert.equal(receipts.active.size, 0, 'truncated scan closes its reader');
        });
        fs.writeFileSync(path.join(f.dir, `${stem}.jsonl`), f.jsonl);
        await observe(async receipts => {
            assert.throws(() => loadCached(diskDir(f), f.verified, date, 'stream'), error => error.code === 'io' && error.path.endsWith('.jsonl') && error.cause.code === 'EIO');
            assert.equal(receipts.active.size, 0, 'failed scan closes its reader');
        }, { read: ({ file }) => { if (file?.endsWith('.jsonl')) throw Object.assign(new Error('native read-control'), { code: 'EIO' }); } });
        const client = await open(f);
        client.close(); assert.throws(() => client.station('OTC-28c56e20'), error => error.code === 'io');
        fs.rmSync(path.join(f.dir, 'index-v1.json'), { force: true });
        for (const bytes of [Buffer.from('{invalid\n'), Buffer.from([0xff, 0x0a])]) {
            const malformed = fixture(bytes);
            try { await observe(async receipts => { assert.throws(() => loadCached(diskDir(malformed), malformed.verified, date, 'stream'), error => error.code === 'invalid_release'); assert.equal(receipts.active.size, 0); }); }
            finally { malformed.cleanup(); }
        }
        const lazy = await open(f);
        try {
            const body = Buffer.from(f.jsonl); body[body.indexOf(Buffer.from('OTC-28c56e20')) + 4] = 0x39;
            fs.writeFileSync(path.join(f.dir, `${stem}.jsonl`), body);
            assert.throws(() => lazy.requireStation('OTC-28c56e20'), error => error.code === 'invalid_release' && error.message.startsWith('index-v1.json does not match'));
            assert.equal(fs.existsSync(path.join(f.dir, 'index-v1.json')), false);
        } finally { lazy.close(); }
    } finally { f.cleanup(); }
});

test('native Node cached stream valid unchanged control', async () => {
    const f = fixture();
    try {
        const entries = indexJsonl(headerFromMeta(f.meta), f.jsonl, false).entries;
        fs.writeFileSync(path.join(f.dir, 'index-v1.json'), JSON.stringify(storedIndex(entries, date, hash(f.jsonl), f.jsonl.length, 'native-test')));
        await observe(async receipts => {
            const client = await open(f);
            try {
                assert.equal(receipts.reads.filter(row => row.file?.endsWith('.jsonl')).length, 0);
                assert.ok(!receipts.bodies.includes(path.join(f.dir, `${stem}.jsonl`)));
                assert.equal(receipts.opened.filter(row => row.file.endsWith('.jsonl')).length, 1);
                assert.deepEqual(client.requireStation(entries[0].station_id).raw, JSON.parse(f.jsonl.toString().split('\n')[0]));
            } finally { client.close(); }
            assert.equal(receipts.active.size, 0);
        });
    } finally { f.cleanup(); }
});

test('native Node cached stream verified five originals', async () => {
    assert.ok(cache, 'exact original full H4 cached directory required');
    const dir = path.join(cache, 'v1', 'releases', date);
    const originals = ['jsonl', 'meta.json', 'csv', 'json', 'json.gz'].map(ext => path.join(dir, `${stem}.${ext}`));
    const marker = fs.readFileSync(path.join(dir, '.verified'));
    const sidecar = fs.readFileSync(path.join(dir, `${stem}.sha256`));
    for (const onOpen of [false, true]) {
        await observe(async receipts => {
            const client = await sdk.OpenTideConstants.open({ release: date, cacheDir: cache, offline: true, mode: 'stream', verifyOnOpen: onOpen });
            try {
                if (!onOpen) {
                    receipts.reads.length = 0; receipts.bodies.length = 0;
                    assert.equal(await client.verify(), true);
                }
                for (const file of originals) {
                    const reads = receipts.reads.filter(row => row.file === file && !row.wholeBody);
                    assert.equal(reads.reduce((sum, row) => sum + row.count, 0), fs.statSync(file).size, `every byte verified: ${file}`);
                    assert.ok(reads.every(row => row.length <= 65536), 'verification uses bounded chunks');
                    assert.ok(!receipts.bodies.includes(file) || onOpen && file.endsWith('.meta.json'), `no whole sibling read: ${file}`);
                }
                assert.ok(receipts.peak <= 2, 'only loaded Release and one hashing reader are open');
                assert.equal(receipts.active.size, 1);
                assert.equal(client.requireStation('OTC-a6c00a3f').name, 'Springmaid Pier, Myrtle beach');
            } finally { client.close(); }
            assert.equal(receipts.active.size, 0);
        });
    }
    assert.deepEqual(fs.readFileSync(path.join(dir, '.verified')), marker);
    assert.deepEqual(fs.readFileSync(path.join(dir, `${stem}.sha256`)), sidecar);
});

test('native Node cached stream cache checksum and errors', async () => {
    const f = fixture();
    const target = path.join(f.dir, `${stem}.jsonl`);
    const shaPath = path.join(f.dir, `${stem}.sha256`);
    try {
        const client = await open(f);
        try {
            const correctSha = fs.readFileSync(shaPath);
            fs.mkdirSync(path.join(f.root, 'v1', 'pointer'), { recursive: true });
            fs.writeFileSync(path.join(f.root, 'v1', 'pointer', 'OTC_latest-f1.json'), JSON.stringify({ datestamp: date, files: [{ name: `${stem}.sha256`, sha256: '0'.repeat(64) }] }));
            await assert.rejects(client.verify(), error => error.code === 'checksum_mismatch' && error.file === shaPath && error.actual === hash(correctSha) && error.expected === '0'.repeat(64));
            assert.ok(fs.existsSync(shaPath), 'pointer mismatch preserves the sidecar');
            fs.rmSync(path.join(f.root, 'v1', 'pointer', 'OTC_latest-f1.json'));
            await observe(async receipts => {
                await assert.rejects(client.verify(), error => error.code === 'cache' && error.message === `cannot read ${target}` && !Object.hasOwn(error, 'path') && error.cause.code === 'EACCES');
                assert.equal(receipts.active.size, 0);
            }, { open: file => { if (file === target) throw Object.assign(new Error('native permission-control'), { code: 'EACCES' }); } });
            await observe(async receipts => {
                await assert.rejects(client.verify(), error => error.code === 'cache' && error.message === `cannot read ${target}` && !Object.hasOwn(error, 'path') && error.cause.code === 'EIO');
                assert.equal(receipts.active.size, 0);
                assert.equal(receipts.closed.filter(row => row.file === target).length, 1);
            }, { read: ({ file }) => { if (file === target) throw Object.assign(new Error('native EIO-control'), { code: 'EIO' }); } });
            assert.deepEqual(fs.readFileSync(target), f.jsonl);
            await observe(async receipts => {
                assert.equal(await client.verify(), true);
                assert.ok(receipts.reads.filter(row => row.file === target).some(row => row.count === 997));
                assert.equal(receipts.active.size, 0);
            }, { read: () => 997 });
            await observe(async receipts => {
                await assert.rejects(client.verify(), error => error.code === 'cache' && error.message === `cannot read ${target}` && error.cause.code === 'EIO');
                assert.equal(receipts.active.size, 0);
                assert.equal(receipts.closed.filter(row => row.file === target).length, 1);
            }, { close: file => { if (file === target) throw Object.assign(new Error('native close-control'), { code: 'EIO' }); } });
            assert.deepEqual(fs.readFileSync(target), f.jsonl);
            fs.rmSync(target);
            await assert.rejects(client.verify(), error => error.code === 'io' && error.path === target);
            fs.writeFileSync(target, f.jsonl);
            const changed = Buffer.from(f.jsonl); changed[0] ^= 1; fs.writeFileSync(target, changed);
            await observe(async receipts => {
                await assert.rejects(client.verify(), error => error.code === 'checksum_mismatch' && error.file === target && error.expected === hash(f.jsonl) && error.actual === hash(changed));
                assert.equal(receipts.active.size, 0, 'hash reader closes before deletion');
                assert.equal(fs.existsSync(target), false);
            });
        } finally { client.close(); }
        fs.writeFileSync(target, f.jsonl);
        const wrong = fs.readFileSync(shaPath, 'utf8').replace(hash(f.jsonl), '0'.repeat(64));
        fs.writeFileSync(shaPath, wrong);
        await observe(async receipts => {
            await assert.rejects(sdk.OpenTideConstants.open({ release: date, cacheDir: f.root, offline: true, mode: 'stream', verifyOnOpen: true }), error => error.code === 'checksum_mismatch');
            assert.equal(receipts.active.size, 0, 'verifyOnOpen failure closes loaded Release');
        });
        // Reader-null/default platform path retains its original whole-body verification contract.
        const bytes = Buffer.from('actual default callback control');
        const sha = Buffer.from(`${hash(bytes)}  ${stem}.json\n`);
        const calls = [];
        const ctx = { mode: 'eager', store: {
            read: async rel => { calls.push(rel); return rel.endsWith('.sha256') ? sha : rel.endsWith('.json') ? bytes : null; },
            list: async () => [`${stem}.json`], describe: rel => rel, remove: async () => assert.fail('unchanged default digest must match'),
        }, platform: { sha256: async value => hash(value) } };
        assert.equal(await verifyCached(ctx, date), true);
        assert.deepEqual(calls, [`releases/${date}/${stem}.sha256`, `releases/${date}/${stem}.json`]);
    } finally { f.cleanup(); }
});

test('native Node cached stream baseline read-close precedence', async () => {
    const f = fixture(), target = path.join(f.dir, `${stem}.jsonl`);
    try {
        const client = await open(f);
        try {
            await observe(async receipts => {
                let failure;
                try { await client.verify(); } catch (error) { failure = error; }
                assert.equal(failure?.code, 'cache');
                assert.equal(failure.message, `cannot read ${target}`);
                assert.equal(failure.cause?.code, 'EBADF');
                assert.equal(receipts.active.size, 0);
                assert.equal(receipts.closed.filter(row => row.file === target).length, 1);
                console.log(JSON.stringify({ surface: 'real native cached public verify read+close fault', code: failure.code, message: failure.message, cause_code: failure.cause?.code, cause_message: failure.cause?.message }));
            }, {
                read: ({ file }) => { if (file === target) throw Object.assign(new Error('primary native read-control'), { code: 'EIO' }); },
                close: file => { if (file === target) throw Object.assign(new Error('secondary native close-control'), { code: 'EBADF' }); },
            });
            assert.deepEqual(fs.readFileSync(target), f.jsonl);
        } finally { client.close(); }
    } finally { f.cleanup(); }
});

test('native Node cached stream strict close and unchanged default', async () => {
    const f = fixture(), target = path.join(f.dir, `${stem}.jsonl`);
    try {
        await observe(async receipts => {
            const reader = nodeRuntime.openLineReader(target);
            reader.close(); reader.close();
            assert.equal(receipts.active.size, 0);
            assert.equal(receipts.closed.filter(row => row.file === target).length, 1);
        }, { close: file => { if (file === target) throw Object.assign(new Error('default close-control'), { code: 'EIO' }); } });
        await observe(async receipts => {
            const reader = nodeRuntime.openLineReader(target);
            assert.equal(typeof reader.closeStrict, 'function', 'actual private native strict close required');
            assert.throws(() => reader.closeStrict(), error => error.code === 'EIO' && error.message === 'strict close-control');
            reader.closeStrict(); reader.close();
            assert.equal(receipts.active.size, 0);
            assert.equal(receipts.closed.filter(row => row.file === target).length, 1);
            assert.throws(() => reader.read(0, 1), error => error.code === 'io');
        }, { close: file => { if (file === target) throw Object.assign(new Error('strict close-control'), { code: 'EIO' }); } });
    } finally { f.cleanup(); }
});

test('native Node cached stream historical default strict values', async () => {
    const reference = process.env.OTC_CACHED_HISTORY_REPORT ?? '/Users/jpr5/.local/share/copilotkit/cr/otc-codex-takeover/baseline-label/NOAA-HISTORICAL-EXECUTION/H4/python-final/policy-312.json';
    const expected = JSON.parse(fs.readFileSync(reference, 'utf8'));
    const f = fixture();
    const original = f.jsonl.toString().trimEnd().split('\n').map(line => JSON.parse(line));
    const start = new Date('2026-10-11T00:00:00Z'), stop = new Date('2026-10-12T00:00:00Z');
    const rows = result => result.items.map(event => ({ time: event.time.toISOString(), type: event.type, height_m: event.height_m }));
    try {
        const client = await open(f);
        try {
            for (const id of ['OTC-28c56e20', 'OTC-541f1a73']) {
                assert.deepEqual(client.requireStation(id).raw, original.find(station => station.station_id === id));
                const source = client.requireStation(id).subordinateOffsets;
                const result = await client.extremes(id, { start, stop, datum: 'chart' });
                const explicit = await client.extremes(id, { start, stop, datum: 'chart', offsetId: source.offset_id });
                assert.deepEqual(rows(result), rows(explicit));
                assert.equal(result.offset_id, source.offset_id); assert.equal(result.set_id, null);
                assert.equal(result.offset_source, 'noaa'); assert.equal(result.offset_source_version, 'annual-tide-tables-2020');
                assert.equal(result.historical_offsets, true); assert.equal(result.current_accuracy, 'unverified');
                assert.equal(result.current_validity, 'unestablished'); assert.equal(result.reference_2020_equivalence, 'disagrees');
                assert.ok(result.reference_set_id.startsWith(source.reference_station_id + '/'));
                for (const cell of expected.numeric_cells.filter(cell => cell.mode === 'eager' && cell.station_id === id)) {
                    const actual = rows(result).find(event => event.type === cell.kind);
                    assert.equal(actual.time, new Date(cell.time).toISOString());
                    assert.ok(Math.abs(actual.height_m - cell.height_m) < 1e-10);
                }
                await assert.rejects(client.heights(id, { start, stop }), error => error.code === 'extremes_only');
                await assert.rejects(client.heightsAt(id, [start]), error => error.code === 'extremes_only');
            }
            const controls = expected.unchanged_controls.filter(control => control.mode === 'eager');
            assert.equal(controls.length, 3);
            for (const control of controls) {
                const actual = rows(await client.extremes(control.station_id, { start, stop, datum: 'chart' }));
                assert.equal(actual.length, control.events.length);
                for (let i = 0; i < actual.length; i++) {
                    assert.equal(actual[i].time, new Date(control.events[i].time).toISOString());
                    assert.equal(actual[i].type, control.events[i].type);
                    assert.ok(Math.abs(actual[i].height_m - control.events[i].height_m) < 1e-10);
                }
            }
        } finally { client.close(); }
        const strict = await sdk.OpenTideConstants.open({ release: date, cacheDir: f.root, offline: true, mode: 'stream', historicalOffsetsPolicy: 'exclude' });
        try {
            for (const id of ['OTC-28c56e20', 'OTC-541f1a73']) {
                assert.deepEqual(strict.requireStation(id).raw, original.find(station => station.station_id === id));
                for (const flags of [{}, { includeFlagged: true }, { includeFallback: true }, { includeFlagged: true, includeFallback: true }]) assert.equal(strict.stations(flags).some(station => station.station_id === id), false);
                await assert.rejects(strict.extremes(id, { start, stop }), error => error.code === 'historical_offsets_excluded');
                await assert.rejects(strict.extremes(id, { start, stop, offsetId: strict.requireStation(id).subordinateOffsets.offset_id }), error => error.code === 'historical_offsets_excluded');
            }
        } finally { strict.close(); }
    } finally { f.cleanup(); }
});
