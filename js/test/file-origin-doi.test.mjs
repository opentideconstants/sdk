import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createServer } from 'node:http';
import { createHash } from 'node:crypto';
import { OpenTideConstants } from '../dist/index.js';

const fixture = new URL('../../conformance/fixtures/good/', import.meta.url).pathname;
const stamp = '20991231.2';
const doi = '10.5072/zenodo.observed-file';
const hash = bytes => createHash('sha256').update(bytes).digest('hex');

async function checkFileOrigin({ mode, format, verified, operation }) {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'otc-file-doi-'));
    const filesDir = path.join(root, 'files');
    const cachedDir = path.join(root, 'cache/v1/releases', stamp);
    fs.mkdirSync(filesDir, { recursive: true });
    fs.mkdirSync(cachedDir, { recursive: true });
    const names = [`OTC_${stamp}.${format}`, ...(format === 'jsonl' ? [`OTC_${stamp}.meta.json`] : [])];
    for (const name of [...names, ...(verified ? [`OTC_${stamp}.sha256`] : [])]) {
        fs.copyFileSync(path.join(fixture, name), path.join(filesDir, name));
    }
    for (const name of names) fs.copyFileSync(path.join(fixture, name), path.join(cachedDir, name));
    const original = {
        datestamp: stamp, format_version: '1.0', zenodo_version_doi: '10.5072/zenodo.old',
        files: Object.fromEntries(names.map(name => {
            const bytes = fs.readFileSync(path.join(cachedDir, name));
            return [name, { sha256: hash(bytes), size: bytes.length, url: null }];
        })),
        by: 'original-verifier', verified_at: '2026-10-14T00:00:00Z', unknown_extension: { keep: [1, 'unknown'] },
    };
    const receiptPath = path.join(cachedDir, '.verified');
    fs.writeFileSync(receiptPath, JSON.stringify(original));
    const sourcePins = Object.fromEntries(names.map(name => [name, hash(fs.readFileSync(path.join(filesDir, name)))]));
    const requests = [];
    const server = createServer((request, response) => {
        const name = request.url.slice(1);
        requests.push(name);
        const file = path.join(fixture, name);
        if (!fs.existsSync(file)) return response.writeHead(404).end();
        const bytes = fs.readFileSync(file);
        const body = name.startsWith('OTC_latest')
            ? JSON.stringify({ ...JSON.parse(bytes), zenodo_version_doi: doi }) : bytes;
        response.writeHead(200, { 'Cache-Control': 'no-store' });
        response.end(body);
    });
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    let client;
    try {
        client = await OpenTideConstants.open({ file: path.join(filesDir, names[0]), mode,
            cacheDir: path.join(root, 'cache'), baseUrl: `http://127.0.0.1:${server.address().port}/` });
        const release = client.release;
        const raw = release.requireStation('OTC-T-0001').raw;
        assert.equal(release.zenodo_version_doi, null);
        assert.equal(client.loadedFrom, verified ? 'file' : 'file_unverified');
        await client[operation]();
        const receipt = JSON.parse(fs.readFileSync(receiptPath));
        const observed = {
            mode, format, verified, operation, loadedFrom: client.loadedFrom,
            sessionDoi: client.release.zenodo_version_doi, receiptDoi: receipt.zenodo_version_doi,
            frozen: Object.isFrozen(release), enumerable: Object.keys(release).includes('zenodo_version_doi'),
            rawPreserved: JSON.stringify(client.release.requireStation('OTC-T-0001').raw) === JSON.stringify(raw),
            sourcesPreserved: names.every(name => hash(fs.readFileSync(path.join(filesDir, name))) === sourcePins[name]),
            requests,
        };
        console.log(JSON.stringify(observed));
        assert.ok(observed.requests.includes('OTC_latest-f1.json'));
        assert.equal(receipt.zenodo_version_doi, doi, 'a file session still notes a matching cached receipt');
        assert.deepEqual({ ...receipt, zenodo_version_doi: null }, { ...original, zenodo_version_doi: null });
        assert.ok(observed.frozen && observed.enumerable && observed.rawPreserved && observed.sourcesPreserved);
        assert.equal(client.release, release);
        assert.equal(client.release.zenodo_version_doi, null, 'file-origin DOI must stay null after a metadata read');
        assert.ok(!client.release.citation.includes(doi));
    } finally {
        client?.close();
        await new Promise(resolve => server.close(resolve));
        fs.rmSync(root, { recursive: true, force: true });
    }
}

for (const [mode, format] of [['eager', 'json'], ['eager', 'jsonl'], ['stream', 'jsonl']]) {
    for (const verified of [true, false]) {
        for (const operation of ['latest', 'checkForUpdate']) {
            test(`file-origin DOI stays null: ${mode}/${format}/${verified ? 'verified' : 'unverified'}/${operation}`,
                () => checkFileOrigin({ mode, format, verified, operation }));
        }
    }
}
