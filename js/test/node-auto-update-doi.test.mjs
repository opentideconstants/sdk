import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createHash } from 'node:crypto';
import { createServer } from 'node:http';
import { once } from 'node:events';
import { setTimeout } from 'node:timers/promises';
import { Worker, isMainThread, parentPort } from 'node:worker_threads';
import { fileURLToPath } from 'node:url';
import { OpenTideConstants } from '../dist/index.js';

const fixtures = fileURLToPath(new URL('../../conformance/fixtures/good/', import.meta.url));
const releases = JSON.parse(fs.readFileSync(path.join(fixtures, 'OTC_index.json'))).releases;
const currentStamp = '20991231.2';
const oldDoi = '10.5072/zenodo.old';
const freshDoi = '10.5072/zenodo.changed';
const hash = bytes => createHash('sha256').update(bytes).digest('hex');

// A separate server thread can answer while the client's real automatic worker blocks the main thread.
if (!isMainThread) {
    let pointer;
    const requests = [];
    const server = createServer((request, response) => {
        const name = request.url.slice(1);
        requests.push({ path: name, doi: pointer?.zenodo_version_doi ?? null });
        const body = name.startsWith('OTC_latest') ? Buffer.from(JSON.stringify(pointer))
            : fs.readFileSync(path.join(fixtures, name));
        response.writeHead(200, { 'Content-Length': body.length });
        response.end(body);
    });
    parentPort.on('message', entry => {
        pointer = entry;
        parentPort.postMessage({ requests: [...requests] });
    });
    server.listen(0, '127.0.0.1', () => parentPort.postMessage({ port: server.address().port }));
}

async function servePointer(worker, datestamp, doi) {
    const entry = structuredClone(releases.find(release => release.datestamp === datestamp));
    if (doi === undefined) delete entry.zenodo_version_doi;
    else entry.zenodo_version_doi = doi;
    const reply = once(worker, 'message');
    worker.postMessage(entry);
    return (await reply)[0].requests;
}

function cachedHashes(dir) {
    return Object.fromEntries(fs.readdirSync(dir).filter(name => !name.startsWith('.'))
        .map(name => [name, hash(fs.readFileSync(path.join(dir, name)))]));
}

async function observeAutomaticDoi(profile) {
    const parent = process.env.OTC_AUTO_DOI_PROOF ?? os.tmpdir();
    fs.mkdirSync(parent, { recursive: true });
    const cache = fs.mkdtempSync(path.join(parent, `${profile.name}-`));
    const initialStamp = profile.initialStamp ?? currentStamp;
    const dir = path.join(cache, 'v1/releases', initialStamp);
    const receiptPath = path.join(dir, '.verified');
    const ownerPath = path.join(dir, '.lock/owner.json');
    const worker = new Worker(new URL(import.meta.url));
    let client;
    try {
        const [{ port }] = await once(worker, 'message');
        await servePointer(worker, initialStamp, oldDoi);
        const options = { cacheDir: cache, baseUrl: `http://127.0.0.1:${port}/`,
            mode: profile.mode ?? 'eager', timeout: 5, onNetworkError: 'raise' };
        client = await OpenTideConstants.open({ ...options, release: 'latest' });
        client.close();
        if (profile.busy) {
            fs.mkdirSync(path.dirname(ownerPath));
            fs.writeFileSync(ownerPath, JSON.stringify({ pid: process.pid,
                started_at: new Date().toISOString().replace(/\.\d{3}Z$/, 'Z'), token: `foreign-${profile.name}` }));
        }
        const reopenOptions = { ...options };
        if (profile.file) delete reopenOptions.onNetworkError;
        client = await OpenTideConstants.open({ ...reopenOptions,
            ...(profile.file ? { file: path.join(fixtures, `OTC_${initialStamp}.json`) } : { release: 'latest' }),
            autoUpdate: true, updateInterval: 0.1 });
        const release = client.release;
        const originalRaw = JSON.stringify(release.requireStation('OTC-T-0001').raw);
        const beforeDoi = release.zenodo_version_doi;
        const receiptBefore = fs.readFileSync(receiptPath);
        const ownerBefore = profile.busy ? fs.readFileSync(ownerPath) : null;
        const dataBefore = cachedHashes(dir);
        const selectedStamp = profile.stamp ?? initialStamp;
        const newer = selectedStamp > initialStamp;
        const requestsBefore = await servePointer(worker, selectedStamp, profile.doi);
        await setTimeout(150);
        // This public Client query, rather than a metadata getter, must trigger the automatic check.
        const station = client.requireStation('OTC-T-0001');
        const afterDoi = release.zenodo_version_doi;
        const afterCitation = release.citation;
        const observedRelease = client.release;
        const requests = (await servePointer(worker, selectedStamp, profile.doi)).slice(requestsBefore.length);
        const receiptAfter = fs.readFileSync(receiptPath);
        const ownerAfter = profile.busy ? fs.readFileSync(ownerPath) : null;
        const fields = receipt => {
            const parsed = JSON.parse(receipt);
            delete parsed.zenodo_version_doi;
            return parsed;
        };
        const expectedDoi = profile.file ? null
            : selectedStamp === initialStamp && profile.doi != null ? profile.doi : oldDoi;
        const assertions = {
            refreshed_doi: afterDoi === expectedDoi,
            refreshed_citation: expectedDoi === null ? !afterCitation.includes('version DOI:')
                : afterCitation.includes(`version DOI: https://doi.org/${expectedDoi}`),
            release_identity: (observedRelease === release) === !newer,
            raw_unchanged: JSON.stringify(release.requireStation('OTC-T-0001').raw) === originalRaw,
            newer_release_metadata: !newer || observedRelease.datestamp === selectedStamp
                && observedRelease.zenodo_version_doi === profile.doi,
            data_unchanged: JSON.stringify(cachedHashes(dir)) === JSON.stringify(dataBefore),
            receipt_provenance_unchanged: JSON.stringify(fields(receiptBefore)) === JSON.stringify(fields(receiptAfter)),
            busy_receipt_unchanged: !profile.busy || receiptBefore.equals(receiptAfter),
            busy_owner_unchanged: !profile.busy || ownerBefore.equals(ownerAfter),
            real_pointer_read: profile.file ? requests.length === 0 : requests.some(row => row.path.startsWith('OTC_latest')),
            successful_query: station.station_id === 'OTC-T-0001' && client.lastError === null,
        };
        const row = { name: profile.name, before_doi: beforeDoi, after_doi: afterDoi, expected_doi: expectedDoi,
            source_stamp: initialStamp, selected_stamp: selectedStamp, assertions, requests,
            receipt_before: JSON.parse(receiptBefore), receipt_after: JSON.parse(receiptAfter),
            owner_before: ownerBefore?.toString() ?? null, owner_after: ownerAfter?.toString() ?? null,
            data_hashes_before: dataBefore, data_hashes_after: cachedHashes(dir) };
        console.log(JSON.stringify(row));
        if (process.env.OTC_AUTO_DOI_PROOF) fs.writeFileSync(path.join(cache, 'proof.json'), JSON.stringify(row, null, 4));
        for (const [name, passed] of Object.entries(assertions)) assert.equal(passed, true, `${profile.name}: ${name}`);
    } finally {
        client?.close();
        await worker.terminate();
        if (!process.env.OTC_AUTO_DOI_PROOF) fs.rmSync(cache, { recursive: true, force: true });
    }
}

if (isMainThread) {
    for (const profile of [
        { name: 'same-stamp-eager-unlocked', doi: freshDoi },
        { name: 'same-stamp-eager-busy', doi: freshDoi, busy: true },
        { name: 'same-stamp-stream-busy', doi: freshDoi, busy: true, mode: 'stream' },
        { name: 'null-doi-preserves-known', doi: null },
        { name: 'missing-doi-preserves-known', doi: undefined },
        { name: 'older-stamp-doi-is-not-current', stamp: '20991231', doi: freshDoi },
        { name: 'newer-stamp-still-swaps-release', initialStamp: '20991231', stamp: currentStamp, doi: freshDoi },
        { name: 'file-release-retains-null-doi', doi: freshDoi, file: true },
    ]) test(profile.name, { timeout: 20_000 }, () => observeAutomaticDoi(profile));
}
