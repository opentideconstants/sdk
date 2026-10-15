import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { hostname } from 'node:os';
import { createServer } from 'node:http';
import { createHash } from 'node:crypto';
import { OpenTideConstants } from '../dist/index.js';

const fixture = new URL('../../conformance/fixtures/good/', import.meta.url).pathname;
const stamp = '20991231.2';
const oldDoi = '10.5072/zenodo.old';
const newDoi = '10.5072/zenodo.catalog';
const hash = bytes => createHash('sha256').update(bytes).digest('hex');

async function checkCatalog({ mode, format, state }) {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'otc-catalog-doi-'));
    const cacheDir = path.join(root, 'cache');
    const cachedDir = path.join(cacheDir, 'v1/releases', stamp);
    const filesDir = path.join(root, 'files');
    fs.mkdirSync(cachedDir, { recursive: true });
    fs.mkdirSync(filesDir);
    const names = [`OTC_${stamp}.${format}`, ...(format === 'jsonl' ? [`OTC_${stamp}.meta.json`] : [])];
    for (const name of [...names, `OTC_${stamp}.sha256`]) {
        fs.copyFileSync(path.join(fixture, name), path.join(cachedDir, name));
        if (state !== 'file-unverified' || !name.endsWith('.sha256')) {
            fs.copyFileSync(path.join(fixture, name), path.join(filesDir, name));
        }
    }
    const original = {
        datestamp: stamp, format_version: '1.0', zenodo_version_doi: oldDoi,
        files: Object.fromEntries(names.map(name => {
            const bytes = fs.readFileSync(path.join(cachedDir, name));
            return [name, { sha256: hash(bytes), size: bytes.length, url: null }];
        })),
        by: 'original-verifier', verified_at: '2026-10-14T00:00:00Z', unknown_extension: { keep: [1, 'unknown'] },
    };
    const receiptPath = path.join(cachedDir, '.verified');
    const receiptBytes = JSON.stringify(original);
    fs.writeFileSync(receiptPath, receiptBytes);
    const pins = Object.fromEntries([...names, `OTC_${stamp}.sha256`].map(name => [name, hash(fs.readFileSync(path.join(cachedDir, name)))]));
    const requests = [];
    const server = createServer((request, response) => {
        const name = request.url.slice(1);
        requests.push(name);
        const file = path.join(fixture, name);
        if (!fs.existsSync(file)) return response.writeHead(404).end();
        let body = fs.readFileSync(file);
        if (name.startsWith('OTC_latest')) body = JSON.stringify({ ...JSON.parse(body), zenodo_version_doi: oldDoi });
        if (name === 'OTC_index.json') {
            const doc = JSON.parse(body);
            const entry = { ...doc.releases[0], zenodo_version_doi: state === 'null' ? null : newDoi };
            if (state === 'missing') delete entry.zenodo_version_doi;
            if (state === 'different-stamp') entry.datestamp = '20991231.3';
            body = JSON.stringify({ ...doc, releases: [entry] });
        }
        response.writeHead(200, { 'Cache-Control': 'no-store' });
        response.end(body);
    });
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    let client;
    try {
        const fileOrigin = state.startsWith('file-');
        client = await OpenTideConstants.open({ mode, cacheDir,
            ...(fileOrigin ? { file: path.join(filesDir, names[0]) } : {}),
            baseUrl: `http://127.0.0.1:${server.address().port}/` });
        const release = client.release;
        const raw = JSON.stringify(release.requireStation('OTC-T-0001').raw);
        const lockDir = path.join(cachedDir, '.lock');
        const lockOwner = JSON.stringify({ pid: process.pid, host: hostname(), sdk: 'catalog-native-proof',
            token: 'other-live-process', started_at: new Date().toISOString() });
        if (state === 'busy') {
            fs.mkdirSync(lockDir);
            fs.writeFileSync(path.join(lockDir, 'owner.json'), lockOwner);
        }
        const catalog = await client.releases();
        const receipt = JSON.parse(fs.readFileSync(receiptPath));
        const expected = fileOrigin ? null : ['null', 'missing', 'different-stamp'].includes(state) ? oldDoi : newDoi;
        const expectedReceipt = ['busy', 'null', 'missing', 'different-stamp'].includes(state) ? oldDoi : newDoi;
        const observed = { mode, format, state, sessionDoi: client.release.zenodo_version_doi,
            expected, receiptDoi: receipt.zenodo_version_doi, expectedReceipt,
            frozen: Object.isFrozen(release), rawPreserved: JSON.stringify(client.release.requireStation('OTC-T-0001').raw) === raw,
            sourcesPreserved: Object.entries(pins).every(([name, pin]) => hash(fs.readFileSync(path.join(cachedDir, name))) === pin), requests };
        console.log(JSON.stringify(observed));
        assert.ok(requests.includes('OTC_index.json'));
        assert.equal(catalog.length, 1);
        assert.equal(client.release, release);
        assert.ok(observed.frozen && observed.rawPreserved && observed.sourcesPreserved);
        assert.equal(receipt.zenodo_version_doi, expectedReceipt);
        assert.deepEqual({ ...receipt, zenodo_version_doi: null }, { ...original, zenodo_version_doi: null });
        if (state === 'busy') {
            assert.equal(fs.readFileSync(receiptPath, 'utf8'), receiptBytes);
            assert.equal(fs.readFileSync(path.join(lockDir, 'owner.json'), 'utf8'), lockOwner);
        }
        assert.equal(client.release.zenodo_version_doi, expected, 'catalog observation must refresh only the eligible current session');
        assert.equal(client.release.citation.includes(newDoi), expected === newDoi);
    } finally {
        client?.close();
        await new Promise(resolve => server.close(resolve));
        fs.rmSync(root, { recursive: true, force: true });
    }
}

for (const [mode, format] of [['eager', 'json'], ['eager', 'jsonl'], ['stream', 'jsonl']]) {
    for (const state of ['fresh', 'busy', 'null', 'missing', 'different-stamp', 'file-verified', 'file-unverified']) {
        test(`catalog DOI session: ${mode}/${format}/${state}`, () => checkCatalog({ mode, format, state }));
    }
}
