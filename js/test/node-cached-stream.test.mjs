import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { syncBuiltinESMExports } from 'node:module';
import * as sdk from '../dist/index.js';
import { loadCached, verifyCached } from '../dist/core.js';
import { headerFromMeta, indexJsonl } from '../dist/loader.js';
import * as nodeRuntime from '../dist/node.js';
import { storedIndex } from '../dist/release.js';

const cache = process.env.OTC_CACHED_STREAM_CACHE;
const historical = process.env.OTC_CACHED_HISTORY_DIR ?? '/Users/jpr5/.local/share/copilotkit/cr/otc-codex-takeover/execution/sdk-core-sync/proofs/T1/historical-targets';
const date = '20261011', stem = `OTC_${date}`;
const hash = bytes => createHash('sha256').update(bytes).digest('hex');

function fixture(jsonl = fs.readFileSync(path.join(historical, `${stem}.jsonl`))) {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'otc-native-cached-'));
    const dir = path.join(root, 'v1', 'releases', date);
    fs.mkdirSync(dir, { recursive: true });
    const meta = fs.readFileSync(path.join(historical, `${stem}.meta.json`));
    const files = { [`${stem}.meta.json`]: meta, [`${stem}.jsonl`]: jsonl };
    const verified = { datestamp: date, format_version: '1.0', verified_at: '2026-10-11T00:00:00Z', by: 'native-test', files: {} };
    for (const [name, bytes] of Object.entries(files)) {
        fs.writeFileSync(path.join(dir, name), bytes);
        verified.files[name] = { sha256: hash(bytes), size: bytes.length, url: null };
    }
    fs.writeFileSync(path.join(dir, `${stem}.sha256`), Object.entries(files).map(([name, bytes]) => `${hash(bytes)}  ${name}\n`).join(''));
    fs.writeFileSync(path.join(dir, '.verified'), JSON.stringify(verified));
    return { root, dir, meta, jsonl, verified, cleanup: () => fs.rmSync(root, { recursive: true, force: true }) };
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

const open = f => sdk.OpenTideConstants.open({ release: date, cacheDir: f.root, offline: true, mode: 'stream' });
const diskDir = (f, overrides = {}) => ({
    read: name => nodeRuntime.readIfExists(path.join(f.dir, name)),
    size: name => nodeRuntime.statSize(path.join(f.dir, name)),
    lineReader: name => nodeRuntime.openLineReader(path.join(f.dir, name)),
    writeIndex: bytes => nodeRuntime.writeAtomicSync(path.join(f.dir, 'index-v1.json'), bytes),
    removeIndex: () => nodeRuntime.removeFileSync(path.join(f.dir, 'index-v1.json')),
    ...overrides,
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
