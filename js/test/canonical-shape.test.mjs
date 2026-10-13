import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createServer } from 'node:http';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const packageRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const root = path.resolve(packageRoot, '..');
const proof = process.env.OTC_SHAPE_PROOF ?? '/Users/jpr5/.local/share/copilotkit/cr/otc-codex-takeover/execution/sdk-core-sync/canonical-behavior/holistic-reset/implementation-plan/S-TS';
const nodeFixture = await import('../dist/canonical-shape/test/canonical-shape.js').catch(error => ({ loadError: error.message }));
const documentBytes = fs.readFileSync(path.join(root, 'conformance/fixtures/good/OTC_20991231.2.json'));
const protocol = JSON.parse(fs.readFileSync(path.join(root, 'conformance/canonical/native-shape.json')));
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
const pin = relative => ({ path: relative, sha256: sha256(fs.readFileSync(path.join(root, relative))) });

function verifyInvocations(observations) {
    assert.deepEqual(observations.runtime.map(row => row.id), protocol.runtime.map(row => row.id));
    assert.deepEqual(observations.call_actions.map(row => row.id), protocol.call_actions.map(row => row.action.action_id));
    assert.ok(observations.runtime.every(row => row.refusal === `Private canonical seam ${row.id} is unimplemented`));
    assert.equal(observations.b04_presence_controls.length, 4);
    assert.ok(observations.b04_presence_controls.every(row => row.refusal === 'Private canonical seam B04 is unimplemented'));
    assert.equal(observations.control.raw_preserved, true);
    assert.equal(observations.control.public_route_unchanged, true);
}

function writeEvidence(profile, observations, runtimeEnvironment) {
    const evidenceDir = path.join(packageRoot, 'dist/canonical-shape/evidence');
    fs.mkdirSync(evidenceDir, { recursive: true });
    fs.mkdirSync(proof, { recursive: true });
    const relative = `js/dist/canonical-shape/evidence/${profile}-invocations.json`;
    fs.writeFileSync(path.join(root, relative), JSON.stringify({ profile, runtimeEnvironment, document_sha256: sha256(documentBytes), observations }, null, 2));
    fs.copyFileSync(path.join(root, relative), path.join(proof, `${profile}-invocations.json`));
    return pin(relative);
}

test('private canonical TypeScript Node entries load and invoke on the actual candidate', async () => {
    assert.equal(nodeFixture.loadError, undefined, `Required private native seam is absent: ${nodeFixture.loadError}`);
    const observations = await nodeFixture.exerciseShape(documentBytes.toString(), 'typescript_node');
    verifyInvocations(observations);
    writeEvidence('typescript_node', observations, 'node');
    console.log(JSON.stringify({ native_profile: 'typescript_node', runtime: 60, ordered_call_actions: 78, construction_only: true }));
});

test('private canonical TypeScript browser entries load and invoke in Chromium', async () => {
    const server = createServer((request, response) => {
        const requested = new URL(request.url, 'http://localhost').pathname;
        if (requested === '/') {
            response.writeHead(200, { 'content-type': 'text/html' });
            response.end('<!doctype html><title>Private native shape</title>');
            return;
        }
        const filename = path.resolve(packageRoot, `.${requested}`);
        if (!filename.startsWith(path.join(packageRoot, 'dist') + path.sep) || !fs.existsSync(filename)) {
            response.writeHead(404); response.end(); return;
        }
        response.writeHead(200, { 'content-type': 'text/javascript' });
        response.end(fs.readFileSync(filename));
    });
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    let browser;
    try {
        browser = await chromium.launch({ headless: true });
        const page = await browser.newPage();
        await page.goto(`http://127.0.0.1:${server.address().port}/`);
        const result = await page.evaluate(async source => {
            try {
                const fixture = await import('/dist/canonical-shape/test/canonical-shape.js');
                return { runtime_environment: 'browser', user_agent: navigator.userAgent, observations: await fixture.exerciseShape(source, 'typescript_browser') };
            } catch (error) {
                return { runtime_environment: 'browser', load_error: error.message };
            }
        }, documentBytes.toString());
        assert.equal(result.load_error, undefined, `Required private browser seam is absent: ${result.load_error}`);
        assert.equal(result.runtime_environment, 'browser');
        assert.match(result.user_agent, /Chrome/);
        verifyInvocations(result.observations);
        writeEvidence('typescript_browser', result.observations, 'browser');
        console.log(JSON.stringify({ native_profile: 'typescript_browser', runtime: 60, ordered_call_actions: 78, runtime_environment: 'browser', user_agent: result.user_agent, construction_only: true }));
    } finally {
        await browser?.close();
        await new Promise(resolve => server.close(resolve));
    }
});
