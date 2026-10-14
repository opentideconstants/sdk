import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { createServer } from 'node:http';
import { createHash } from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';
import { Session } from 'node:inspector';
import { Sum, events } from '../dist/predict/harmonic.js';
import { releaseFromJson } from '../dist/loader.js';
import { predictionAstroTable } from '../dist/release.js';
import { select_canonical_error } from '../dist/canonical.js';
import { evaluate_astronomy, find_unrounded_tide_events, evaluate_harmonic_height } from '../dist/canonical.js';
import { InvalidArgumentError } from '../dist/errors.js';

const packageRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const root = path.resolve(packageRoot, '..');
const proof = process.env.OTC_SHAPE_PROOF ?? '/Users/jpr5/.local/share/copilotkit/cr/otc-codex-takeover/execution/sdk-core-sync/canonical-behavior/holistic-reset/implementation-plan/S-TS';
const nodeFixture = await import('../dist/canonical-shape/test/canonical-shape.js').catch(error => ({ loadError: error.message }));
const documentBytes = fs.readFileSync(path.join(root, 'conformance/fixtures/good/OTC_20991231.2.json'));
const predictionSource = fs.readFileSync(path.join(root, 'conformance/fixtures/predict/OTC_20991231.7.json'), 'utf8');
const protocol = JSON.parse(fs.readFileSync(path.join(root, 'conformance/canonical/native-shape.json')));
const sha256 = bytes => createHash('sha256').update(bytes).digest('hex');
const pin = relative => ({ path: relative, sha256: sha256(fs.readFileSync(path.join(root, relative))) });

function m1Server() {
    return createServer((request, response) => {
        const pathname = new URL(request.url, 'http://localhost').pathname;
        if (pathname === '/') { response.setHeader('content-type', 'text/html'); response.end('<!doctype html>'); return; }
        const fixture = pathname.startsWith('/fixture-good/');
        const filename = fixture ? path.resolve(root, 'conformance/fixtures/good', pathname.slice('/fixture-good/'.length)) : path.resolve(packageRoot, `.${pathname}`);
        const directory = fixture ? path.join(root, 'conformance/fixtures/good') : path.join(packageRoot, 'dist');
        if (!filename.startsWith(directory + path.sep) || !fs.existsSync(filename)) { response.writeHead(404); response.end(); return; }
        response.setHeader('content-type', fixture ? 'application/octet-stream' : 'text/javascript');
        response.end(fs.readFileSync(filename));
    });
}

function verifyInvocations(observations) {
    assert.deepEqual(observations.runtime.map(row => row.id), protocol.runtime.map(row => row.id));
    assert.deepEqual(observations.call_actions.map(row => row.id), protocol.call_actions.map(row => row.action.action_id));
    const migrated = new Set(['B01', 'B02', 'B03', 'B04', 'B07', 'B08.raw', 'B24', 'B28', 'B39', 'B41', 'B42', 'B43.roots', 'B44.roots']);
    assert.ok(observations.runtime.every(row => migrated.has(row.id) ? row.refusal === undefined && typeof row.value_json === 'string' : row.refusal === `Private canonical seam ${row.id} is unimplemented`));
    assert.equal(observations.b04_presence_controls.length, 7);
    assert.ok(observations.b04_presence_controls.every(row => row.refusal === undefined && (typeof row.value_json === 'string' || typeof row.error_json === 'string')));
    assert.equal(JSON.parse(observations.b04_presence_controls[0].value_json).member_id, 'Client.close');
    assert.deepEqual(JSON.parse(observations.b04_presence_controls[1].value_json), { member_id: 'Release.station', value: null });
    assert.equal(JSON.parse(observations.b04_presence_controls[2].error_json).code, 'io');
    assert.equal(JSON.parse(observations.b04_presence_controls[3].error_json).structured_fields.message, 'native exception');
    assert.deepEqual(observations.b04_presence_controls.slice(4).map(row => JSON.parse(row.error_json).code), ['network', 'checksum_mismatch', 'cache']);
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
    const observations = await nodeFixture.exerciseShape(documentBytes.toString(), 'typescript_node', predictionSource);
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
        const result = await page.evaluate(async ({ source, predictionSource }) => {
            try {
                const fixture = await import('/dist/canonical-shape/test/canonical-shape.js');
                return { runtime_environment: 'browser', user_agent: navigator.userAgent, observations: await fixture.exerciseShape(source, 'typescript_browser', predictionSource) };
            } catch (error) {
                return { runtime_environment: 'browser', load_error: error.message };
            }
        }, { source: documentBytes.toString(), predictionSource });
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

// Real native leaf values from accepted CC0 documents and original finite oracles.
async function observeM1({ moduleRoot, goodSource, predictSource, astroCase, cacheCase, extendedModels = false, extendedGuards = false, guardInputs = [], historicalInputs, dtoModels = false, baseUrl, cacheDir, pointerSource, foreignTables = false, receiverGuards = false, managedModels = false, streamMetadata, streamSource, primitiveGuards = false, requiredBindings = false, requiredTimes = false }) {
    const [canonical, loader, releaseModule, errors, astro] = await Promise.all([
        import(`${moduleRoot}/canonical.js`), import(`${moduleRoot}/loader.js`),
        import(`${moduleRoot}/release.js`), import(`${moduleRoot}/errors.js`), import(`${moduleRoot}/predict/astro.js`),
    ]);
    const good = loader.releaseFromJson(new TextEncoder().encode(goodSource), []);
    const release = loader.releaseFromJson(new TextEncoder().encode(predictSource), []);
    const station = release.requireStation('OTC-P-0001');
    const constants = station.recommendedSet;
    if (!constants) throw new Error('Authentic recommended native model missing');
    const table = releaseModule.predictionAstroTable(release);
    if (!table) throw new Error('Authentic native AstroTable missing');
    const model = { station, release_view: release, constant_set: constants, convention: constants.convention,
        astro_table: table._raw, required_constituents: constants.raw.constituents, reference_bin: null,
        mean_term: 0, datum_source: constants.raw.datum };
    const header = releaseModule.parseHeader(release._header);
    const span = { offset_bytes: 0, length_bytes: new TextEncoder().encode(JSON.stringify(station.raw)).length };
    const index = releaseModule.indexDoc(station.raw, header, span.offset_bytes, span.length_bytes,
        new Set(header.conventions.map(row => row.convention_id)), new Set(header.licences.map(row => row.licence_id)));
    const nativeOwner = { release, entry: index };
    const origin = Symbol('borrowed actual producing Release');
    const result = [];
    const observation = async (id, call, check) => {
        try { const value = await call(); result.push({ id, passed: check(value), value_json: JSON.stringify(value) }); }
        catch (error) { result.push({ id, passed: false, error_name: error.name, error_code: error.code ?? null, error_message: error.message }); }
    };
    const nativeFailure = async call => {
        try { await call(); return null; }
        catch (error) { return { name: error.name, code: error.code, message: error.message, path: error.path ?? null }; }
    };
    const args = { member_id: 'Client.open', arguments: { offline: false } };
    const node = typeof process === 'object' ? (await import(`${moduleRoot}/node.js`)).nodeApi : null;
    const platform = node ? node.nodePlatform() : (await import(`${moduleRoot}/browser.js`)).browserPlatform();
    const environment = node ? { OPENTIDECONSTANTS_OFFLINE: 'On' } : {};
    const failure = new errors.InvalidArgumentError('file cannot be combined with release, offline or onNetworkError');
    const canonicalFailure = { code: failure.code, structured_fields: { message: failure.message }, cause: null };
    try {
        await observation('B01', () => canonical.validate_operation_arguments('open', args, args), value => value.member_id === 'Client.open' && value.arguments.offline === false);
        if (extendedGuards) {
            const clientModule = await import(`${moduleRoot}/client.js`);
            const guardClient = await clientModule.OpenTideConstants.open({ baseUrl, cacheDir: cacheDir + '-guards', offline: false, format: 'json', autoUpdate: false });
            try {
                for (const { operation, selected } of guardInputs) {
                    const native_receiver = selected.member_id.startsWith('Client.') ? { kind: 'client', owner: guardClient } : selected.member_id.startsWith('Release.') ? { kind: 'release', owner: good } : undefined;
                    await observation(`B01.${operation}`, () => {
                        try { return canonical.validate_operation_arguments(operation, selected, { ...selected, native_receiver }); }
                        catch (error) {
                            if (!node && ['download', 'prune'].includes(operation) && error.code === 'unsupported') return { native_capability_error: error.code };
                            throw error;
                        }
                    }, value => value === selected || !node && value.native_capability_error === 'unsupported');
                }
            } finally { guardClient.close(); }
            for (const member_id of ['Constituent.name', 'Constituent.amplitude_m', 'Constituent.phase_deg']) {
                const selected = { member_id, arguments: {} };
                const contract = { ...selected, native_guard: 'no_arguments', native_profile: typeof process === 'object' ? 'typescript_node' : 'typescript_browser' };
                await observation(`B01.no_arguments.${member_id}`, () => canonical.validate_operation_arguments('constituent', selected, contract), value => value === selected && typeof constants.constituents[0][member_id.split('.')[1]] !== 'undefined');
            }
        }
        await observation('B02', () => canonical.resolve_effective_options({ member_id: 'Client.open', offline: false }, environment, { member_id: 'Client.open', native_context: { platform, node } }), value => value.offline === Boolean(node));
        await observation('B03', () => canonical.select_canonical_error('open', [canonicalFailure], null), value => value.code === 'invalid_argument' && value.structured_fields.message === failure.message);
        await observation('B04', () => canonical.translate_native_binding({ native_profile: typeof process === 'object' ? 'typescript_node' : 'typescript_browser', canonical_result: { presence: 'present_value', binding: { member_id: 'Release.station', value: release.station('missing') } } }), value => value.member_id === 'Release.station' && value.value === null);
        if (requiredBindings) {
            const native_profile = node ? 'typescript_node' : 'typescript_browser';
            const cause = new Error('original native cause');
            // Injected canonical failures exercise real source-native constructors, not acquisition failures.
            const network = new errors.NetworkError('transport fixture failed', { url: 'https://native.invalid/release', status: 503, cause });
            const checksum = new errors.ChecksumError('injected digest disagreement', { file: 'OTC_20991231.2.json', expected: 'a'.repeat(64), actual: 'b'.repeat(64), cause });
            const cache = new errors.CacheError('injected prune failure', { removed: ['20991231.2', '20991231'], cause });
            for (const [expected, structured_fields] of [
                [network, { message: network.message, url: network.url, status: network.status }],
                [checksum, { message: checksum.message, file: checksum.file, expected: checksum.expected, actual: checksum.actual }],
                [cache, { message: cache.message, removed: cache.removed }],
            ]) {
                const input = { native_profile, canonical_error: { code: expected.code, structured_fields, cause } };
                await observation(`B04.required.${expected.code}`, () => {
                    try { canonical.translate_native_binding(input); return { threw: false }; }
                    catch (actual) {
                        return { name: actual.name, code: actual.code, message: actual.message,
                            native_class: actual instanceof expected.constructor, cause_identity: actual.cause === cause,
                            url: actual.url, status: actual.status, file: actual.file, expected: actual.expected, actual: actual.actual,
                            removed: actual.removed, removed_frozen: actual.removed ? Object.isFrozen(actual.removed) : undefined };
                    }
                }, actual => actual.native_class && actual.cause_identity && actual.message === expected.message && actual.code === expected.code
                    && actual.url === expected.url && actual.status === expected.status && actual.file === expected.file
                    && actual.expected === expected.expected && actual.actual === expected.actual
                    && JSON.stringify(actual.removed) === JSON.stringify(expected.removed)
                    && (!expected.removed || actual.removed_frozen));
                await observation(`B04.identity.${expected.code}`, () => {
                    try { canonical.translate_native_binding({ native_profile, canonical_error: { ...input.canonical_error, native_error: expected } }); return false; }
                    catch (actual) { return actual === expected && actual.cause === cause; }
                }, value => value === true);
            }
            const binding = { member_id: 'Release.station', value: station };
            await observation('B04.identity.present_owner', () => canonical.translate_native_binding({ native_profile, canonical_result: { presence: 'present_value', binding } }), value => value === binding && value.value === station && value.value._from(release));
            await observation('B04.presence.void', () => canonical.translate_native_binding({ native_profile, canonical_result: { presence: 'successful_no_value', member_id: 'Client.close' } }), value => value.member_id === 'Client.close' && Object.hasOwn(value, 'value') && value.value === undefined);
            await observation('B04.presence.null', () => canonical.translate_native_binding({ native_profile, canonical_result: { presence: 'present_value', binding: { member_id: 'Release.station', value: null } } }), value => value.value === null);
        }
        if (requiredTimes) {
            for (const [label, times] of [['null', null], ['object', {}], ['omitted', undefined]]) {
                const selected = { member_id: 'Release.heights_at', arguments: { station, times } };
                const expected = await nativeFailure(() => release.heightsAt(station, times));
                await observation(`B39.required.times_${label}`, () => nativeFailure(() => canonical.parse_prediction_window(selected, selected, null, 'utc')), value => JSON.stringify(value) === JSON.stringify(expected));
            }
            const engine = await import(`${moduleRoot}/predict/engine.js`);
            for (const [label, times] of [
                ['empty', []],
                ['fractional_duplicate', [new Date('2000-01-01T00:00:00.499Z'), new Date('2000-01-01T00:00:00.499Z')]],
                ['unordered', [new Date('2000-01-01T00:10:00.999Z'), new Date('2000-01-01T00:00:00.499Z')]],
            ]) {
                const selected = { member_id: 'Release.heights_at', arguments: { station, times } };
                const expected = engine.predictionSeconds(times);
                await observation(`B39.control.times_${label}`, () => canonical.parse_prediction_window(selected, selected, null, 'utc'), value => JSON.stringify(value) === JSON.stringify({ instants: expected }));
            }
            const selected = { member_id: 'Release.heights_at', arguments: { station: null, times: null } };
            const expected = await nativeFailure(() => release.heightsAt(null, null));
            await observation('B39.order.times_before_station', () => nativeFailure(() => canonical.parse_prediction_window(selected, selected, null, 'utc')), value => JSON.stringify(value) === JSON.stringify(expected));
        }
        await observation('B07', () => canonical.materialize_typed_model(station.raw, { model_type: 'Station', fields: ['Station.station_id', 'Station.raw'], native_owner: nativeOwner }, origin, 'Station'), value => value.model_type === 'Station' && value.model.station_id === station.station_id && value.model.raw === station.raw);
        if (primitiveGuards) {
            const start = new Date('2000-01-01T00:00:00Z'), stop = new Date('2000-01-02T00:00:00Z');
            for (const [id, operation, selected, publicCall] of [
                ['window_step', 'heights', { member_id: 'Release.heights', arguments: { station, start, stop, step_s: 0 } }, () => release.heights(station, { start, stop, stepS: 0 })],
                ['time_list', 'heights_at', { member_id: 'Release.heights_at', arguments: { station, times: [null] } }, () => release.heightsAt(station, [null])],
                ['datum_boolean', 'datums', { member_id: 'Release.datums', arguments: { station, all_sets: 1 } }, () => release.datums(station, { allSets: 1 })],
                ['offset_pair', 'heights', { member_id: 'Release.heights', arguments: { station, start, stop, set_id: constants.set_id, offset_id: 'wrong' } }, () => release.heights(station, { start, stop, setId: constants.set_id, offsetId: 'wrong' })],
                ['window_before_station', 'heights', { member_id: 'Release.heights', arguments: { station: 'missing', start, stop, step_s: 0 } }, () => release.heights('missing', { start, stop, stepS: 0 })],
                ['station_before_options', 'heights', { member_id: 'Release.heights', arguments: { station: 'missing', start, stop, set_id: 1 } }, () => release.heights('missing', { start, stop, setId: 1 })],
                ['station_before_boolean', 'datums', { member_id: 'Release.datums', arguments: { station: 'missing', all_sets: 1 } }, () => release.datums('missing', { allSets: 1 })],
            ]) {
                const expected = await nativeFailure(publicCall);
                const context = releaseModule.preparePredictionArguments ? releaseModule.preparePredictionArguments(release, selected) : undefined;
                await observation(`B01.primitive.${id}`, () => nativeFailure(() => canonical.validate_operation_arguments(operation, selected, { ...selected, native_receiver: { kind: 'release', owner: release }, native_prediction_prerequisite: context })), value => JSON.stringify(value) === JSON.stringify(expected));
            }
            const yearSelected = { member_id: 'AstroTable.node_factor_for_year', arguments: { name: 'M2', year: 2000.5 } };
            const yearExpected = await nativeFailure(() => table.nodeFactorForYear('M2', 2000.5));
            const yearContext = astro.prepareAstronomyArguments ? astro.prepareAstronomyArguments(table, yearSelected) : undefined;
            await observation('B01.primitive.astro_integer', () => nativeFailure(() => canonical.validate_operation_arguments('node_factor_for_year', yearSelected, { ...yearSelected, native_receiver: { kind: 'astro_table', owner: table }, native_astronomy_prerequisite: yearContext })), value => JSON.stringify(value) === JSON.stringify(yearExpected));
            for (const [label, selected, publicCall] of [
                ['row_before_integer', { member_id: 'AstroTable.node_factor_for_year', arguments: { name: 'missing', year: 2000.5 } }, () => table.nodeFactorForYear('missing', 2000.5)],
                ['instant_before_row', { member_id: 'AstroTable.node_factor', arguments: { name: 'missing', at: new Date('invalid') } }, () => table.nodeFactor('missing', new Date('invalid'))],
            ]) {
                const expected = await nativeFailure(publicCall), context = astro.prepareAstronomyArguments(table, selected);
                await observation(`B01.order.${label}`, () => nativeFailure(() => canonical.validate_operation_arguments('node_factor', selected, { ...selected, native_receiver: { kind: 'astro_table', owner: table }, native_astronomy_prerequisite: context })), value => JSON.stringify(value) === JSON.stringify(expected));
            }
            const positive = { member_id: 'Release.heights', arguments: { station, start, stop, step_s: 600 } };
            const positiveContext = releaseModule.preparePredictionArguments(release, positive);
            await observation('B01.primitive.positive_identity', () => canonical.validate_operation_arguments('heights', positive, { ...positive, native_receiver: { kind: 'release', owner: release }, native_prediction_prerequisite: positiveContext }), value => value === positive && positive.arguments.station === station);
            const nativeSeries = await release.heightsAt(station, [start]);
            const localSelected = { member_id: 'HeightSeries.to_local', arguments: { tz: 1 } };
            const localExpected = await nativeFailure(() => nativeSeries.toLocal(1));
            await observation('B01.primitive.local_type', () => nativeFailure(() => canonical.validate_operation_arguments('to_local', localSelected, { ...localSelected, native_receiver: { kind: 'result', owner: nativeSeries } })), value => JSON.stringify(value) === JSON.stringify(localExpected));
            for (const [operation, selected, nativeValue] of [
                ['convention', { member_id: 'Release.convention', arguments: { convention_id: good.conventions[0].convention_id } }, good.convention(good.conventions[0].convention_id)],
                ['licence', { member_id: 'Release.licence', arguments: { licence_id: good.licences[0].licence_id } }, good.licence(good.licences[0].licence_id)],
                ['station', { member_id: 'Release.station', arguments: { station_id: 'OTC-T-0001' } }, good.station('OTC-T-0001')],
            ]) await observation(`B01.scalar.${operation}`, () => canonical.validate_operation_arguments(operation, selected, { ...selected, native_receiver: { kind: 'release', owner: good } }), value => value === selected && nativeValue !== null);
            for (const [label, operation, selected, publicCall] of [
                ['foreign_reference', 'reference_station', { member_id: 'Release.reference_station', arguments: { station } }, () => good.referenceStation(station)],
                ['null_subordinates', 'subordinates_of', { member_id: 'Release.subordinates_of', arguments: { station: null } }, () => good.subordinatesOf(null)],
                ['foreign_before_malformed', 'attribution', { member_id: 'Release.attribution', arguments: { stations: [station, null] } }, () => good.attribution([station, null])],
                ['malformed_before_foreign', 'attribution', { member_id: 'Release.attribution', arguments: { stations: [null, station] } }, () => good.attribution([null, station])],
            ]) {
                const expected = await nativeFailure(publicCall);
                const context = releaseModule.prepareOwnerArguments ? releaseModule.prepareOwnerArguments(good, selected) : undefined;
                await observation(`B01.owner.${label}`, () => nativeFailure(() => canonical.validate_operation_arguments(operation, selected, { ...selected, native_receiver: { kind: 'release', owner: good }, native_owner_prerequisite: context })), value => JSON.stringify(value) === JSON.stringify(expected));
            }
        }
        if (extendedModels) {
            await observation('B07.Constituent', () => canonical.materialize_typed_model(constants.raw.constituents[0], { model_type: 'Constituent', fields: ['Constituent.raw'] }, origin, 'Constituent'), value => JSON.stringify(value.model) === JSON.stringify(constants.constituents[0]) && value.model.raw === constants.raw.constituents[0]);
            await observation('B07.ProvenanceBuild', () => canonical.materialize_typed_model(constants.raw.provenance.build, { model_type: 'ProvenanceBuild', fields: ['ProvenanceBuild.build_commit'] }, origin, 'ProvenanceBuild'), value => JSON.stringify(value.model) === JSON.stringify(constants.provenance.build));
            await observation('B07.ConstantSet', () => canonical.materialize_typed_model(constants.raw, { model_type: 'ConstantSet', fields: ['ConstantSet.raw'], native_constant_set: { recommended: constants.isRecommended, convention: constants.convention, licence: constants.licence, validation: constants.validation } }, origin, 'ConstantSet'), value => JSON.stringify(value.model) === JSON.stringify(constants) && value.model.raw === constants.raw);
            const series = await release.heightsAt(station, [new Date('2000-01-01T00:00:00Z')]);
            const extremes = await release.extremes(station, { start: new Date(1433116800000), stop: new Date(1433203200000) });
            const nativeCurrentStation = release.stations().find(row => row.kind === 'current' && row.recommendedSet?.raw.current_bins?.length);
            if (!nativeCurrentStation) throw new Error('Authentic current constructor fixture missing');
            const currentSeries = await release.currents(nativeCurrentStation, { start: new Date('2020-06-01T00:00:00Z'), stop: new Date('2020-06-01T01:00:00Z'), stepS: 600 });
            const currentEvents = await release.currentEvents(nativeCurrentStation, { start: new Date('2020-06-01T00:00:00Z'), stop: new Date('2020-06-02T00:00:00Z') });
            const datumInfo = release.datums(station), ranges = release.ranges(station);
            if (!datumInfo || Array.isArray(datumInfo) || !datumInfo.levels.length || !currentEvents.items.length) throw new Error('Authentic native result constructor fixture missing');
            for (const [model_type, nativeModel] of [['HeightPoint', series.items[0]], ['HeightSeries', series], ['Extreme', extremes.items[0]], ['ExtremeList', extremes],
                ['CurrentPoint', currentSeries.items[0]], ['CurrentSeries', currentSeries], ['CurrentEvent', currentEvents.items[0]], ['CurrentEventList', currentEvents],
                ['DatumInfo', datumInfo], ['DatumLevel', datumInfo.levels[0]], ['Ranges', ranges]]) {
                await observation(`B07.${model_type}`, () => canonical.materialize_typed_model(JSON.parse(JSON.stringify(nativeModel)), { model_type, fields: [], native_result_fields: { model_type, fields: nativeModel } }, origin, model_type), value => value.model !== nativeModel && JSON.stringify(value.model) === JSON.stringify(nativeModel));
            }
            const goodStation = good.requireStation('OTC-T-0001'), goodConstants = goodStation.recommendedSet;
            if (managedModels) {
                const clientModule = await import(`${moduleRoot}/client.js`);
                const options = { baseUrl, cacheDir: cacheDir + '-managed', offline: false, format: 'json', autoUpdate: false };
                const clientFields = await clientModule.prepareClientFields(options);
                const releaseFields = loader.prepareReleaseFromJson(new TextEncoder().encode(goodSource), []);
                const streamFields = loader.prepareReleaseFromJsonl(new TextEncoder().encode(streamMetadata), new TextEncoder().encode(streamSource), { eager: false, files: [] });
                let materializedClient, materializedRelease, materializedStream;
                try {
                    await observation('B07.Client', () => {
                        const value = canonical.materialize_typed_model(options, { model_type: 'Client', fields: [], native_prepared_client: clientFields }, origin, 'Client');
                        materializedClient = value.model;
                        return value;
                    }, value => value.model instanceof clientModule.OpenTideConstants && value.model.release === clientFields.release && value.model.loadedFrom === clientFields.loadedFrom && value.model.lastError === clientFields.extra.lastError && value.model.requireStation(goodStation.station_id)._from(clientFields.release));
                    for (const [label, fields] of [['eager', releaseFields], ['stream', streamFields]]) {
                        await observation(`B07.Release.${label}`, () => {
                            const value = canonical.materialize_typed_model(fields.authenticHeader.raw, { model_type: 'Release', fields: [], native_prepared_release: fields }, origin, 'Release');
                            if (label === 'eager') materializedRelease = value.model; else materializedStream = value.model;
                            return value;
                        }, value => value.model instanceof releaseModule.Release && value.model._header === fields.header && value.model.requireStation(goodStation.station_id)._from(value.model) && !goodStation._from(value.model) && JSON.stringify(value.model.stats) === JSON.stringify(good.stats));
                    }
                    if (materializedRelease && materializedStream && materializedClient) {
                        const held = materializedClient.release;
                        if (held !== clientFields.release) throw new Error('Fresh Client held a foreign Release');
                        materializedRelease._close();
                        if (materializedStream.requireStation(goodStation.station_id).station_id !== goodStation.station_id || good.requireStation(goodStation.station_id).station_id !== goodStation.station_id) throw new Error('Managed close affected independent native owners');
                        materializedClient.close();
                        if (held.datestamp !== clientFields.release.datestamp) throw new Error('Held native metadata changed after close');
                    }
                } finally {
                    if (materializedClient) materializedClient.close(); else clientFields.release._close();
                    if (materializedRelease) materializedRelease._close(); else releaseFields.source.close();
                    if (materializedStream) materializedStream._close(); else streamFields.source.close();
                }
            }
            const nativeSets = good.stations({ includeFlagged: true, includeFallback: true }).flatMap(row => row.constantSets({ includeNoConstants: true }));
            const timedSet = nativeSets.find(row => row.raw.time_base), flaggedSet = nativeSets.find(row => row.raw.qc_flags?.length);
            const validatedStation = good.stations({ includeFlagged: true, includeFallback: true }).find(row => row.raw.validation?.length);
            if (!timedSet || !flaggedSet || !validatedStation) throw new Error('Authentic plain helper model fixtures missing');
            for (const [model_type, raw, expected] of [
                ['TimeBase', timedSet.raw.time_base, timedSet.time_base], ['QcFlag', flaggedSet.raw.qc_flags[0], flaggedSet.qc_flags[0]],
                ['Validation', validatedStation.raw.validation[0], validatedStation.validation[0]],
            ]) await observation(`B07.${model_type}`, () => canonical.materialize_typed_model(raw, { model_type, fields: [] }, origin, model_type), value => JSON.stringify(value.model) === JSON.stringify(expected) && Object.isFrozen(value.model));
            await observation('B07.AstroTable', () => canonical.materialize_typed_model(table._raw, { model_type: 'AstroTable', fields: [] }, origin, 'AstroTable'), value => value.model !== table && value.model._raw === table._raw && value.model.nodeFactor('M2', new Date('2000-01-01T00:00:00Z')) === table.nodeFactor('M2', new Date('2000-01-01T00:00:00Z')));
            if (dtoModels) {
                const clientModule = await import(`${moduleRoot}/client.js`);
                const client = await clientModule.OpenTideConstants.open({ baseUrl, cacheDir, offline: false, format: 'json', autoUpdate: false });
                try {
                    const info = await client.latest(), update = await client.update();
                    const pointer = JSON.parse(pointerSource);
                    const nearby = good.nearest({ lat: goodStation.lat, lon: goodStation.lon });
                    if (!nearby) throw new Error('Authentic native Nearby missing');
                    const stats = good.stats;
                    if (receiverGuards) {
                        const invalidDownload = { member_id: 'Client.download', arguments: { to: null } };
                        for (const { operation, selected } of guardInputs.filter(row => ['download', 'search', 'near'].includes(row.operation))) {
                            await observation(`B01.missing_receiver.${operation}`, () => nativeFailure(() => canonical.validate_operation_arguments(operation, selected, selected)), value => value?.name === 'CanonicalUnimplementedError');
                        }
                        const capabilityExpected = await nativeFailure(() => client.download(invalidDownload.arguments));
                        await observation('B01.native_capability', () => nativeFailure(() => canonical.validate_operation_arguments('download', invalidDownload, { ...invalidDownload, native_receiver: { kind: 'client', owner: client } })), value => JSON.stringify(value) === JSON.stringify(capabilityExpected));
                        const invalidPrune = { member_id: 'Client.prune', arguments: { keep: -1 } };
                        const pruneExpected = await nativeFailure(() => client.prune(invalidPrune.arguments));
                        await observation('B01.prune_validation_before_capability', () => nativeFailure(() => canonical.validate_operation_arguments('prune', invalidPrune, { ...invalidPrune, native_receiver: { kind: 'client', owner: client } })), value => JSON.stringify(value) === JSON.stringify(pruneExpected));
                        client.close();
                        const closedRelease = loader.releaseFromJson(new TextEncoder().encode(goodSource), []);
                        closedRelease._close();
                        for (const [member_id, receiver, nativeValue] of [
                            ['Client.release', { kind: 'client', owner: client }, client.release],
                            ['Release.datestamp', { kind: 'release', owner: closedRelease }, closedRelease.datestamp],
                            ['Release.citation', { kind: 'release', owner: closedRelease }, closedRelease.citation],
                        ]) {
                            const selected = { member_id, arguments: {} };
                            const contract = { ...selected, native_guard: 'no_arguments', native_profile: node ? 'typescript_node' : 'typescript_browser', native_receiver: receiver };
                            await observation(`B01.closed_metadata.${member_id}`, () => canonical.validate_operation_arguments('release_metadata', selected, contract), value => value === selected && nativeValue !== undefined);
                        }
                        for (const [member_id, receiver, publicCall] of [
                            ['Client.latest', { kind: 'client', owner: client }, () => client.latest()],
                            ['Release.station_count', { kind: 'release', owner: closedRelease }, () => closedRelease.stationCount],
                            ['Release.conventions', { kind: 'release', owner: closedRelease }, () => closedRelease.conventions],
                        ]) {
                            const selected = { member_id, arguments: {} };
                            const contract = { ...selected, native_guard: 'no_arguments', native_profile: node ? 'typescript_node' : 'typescript_browser', native_receiver: receiver };
                            const expected = await nativeFailure(publicCall);
                            await observation(`B01.closed_noargs.${member_id}`, () => nativeFailure(() => canonical.validate_operation_arguments('release_metadata', selected, contract)), value => JSON.stringify(value) === JSON.stringify(expected));
                        }
                        for (const [operation, selected, receiver, publicCall] of [
                            ['download', invalidDownload, { kind: 'client', owner: client }, () => client.download(invalidDownload.arguments)],
                            ['prune', { member_id: 'Client.prune', arguments: { keep: -1 } }, { kind: 'client', owner: client }, () => client.prune({ keep: -1 })],
                            ['search', { member_id: 'Release.search', arguments: { name: '' } }, { kind: 'release', owner: closedRelease }, () => closedRelease.search({ name: '' })],
                        ]) {
                            const expected = await nativeFailure(publicCall);
                            await observation(`B01.closed_receiver.${operation}`, () => nativeFailure(() => canonical.validate_operation_arguments(operation, selected, { ...selected, native_receiver: receiver })), value => JSON.stringify(value) === JSON.stringify(expected));
                        }
                    }
                    for (const [model_type, raw, expected, context] of [
                        ['ReleaseInfo', pointer, info, { files: info.files }],
                        ['FileInfo', pointer.files[0], info.files.find(row => row.name === pointer.files[0].name), { href: new URL(pointer.files[0].url, baseUrl + 'OTC_latest.json').href }],
                        ['Nearby', { distance_km: nearby.distance_km }, nearby, { station: nearby.station }],
                        ['UpdateResult', { updated: update.updated, from: update.from, to: update.to }, update, null],
                        ['Stats', stats, stats, null],
                    ]) await observation(`B07.${model_type}`, () => canonical.materialize_typed_model(raw, { model_type, fields: [], native_dto_fields: { model_type, context } }, origin, model_type), value => value.model !== expected && JSON.stringify(value.model) === JSON.stringify(expected));
                } finally { client.close(); }
            }
            const fitted = goodStation.constantSets().find(row => row.raw.dropped_constituents?.length);
            const goodHeader = releaseModule.parseHeader(good._header);
            const removedRaw = JSON.parse(goodSource).stations.find(row => row.status === 'removed');
            const offsetStation = good.stations().find(row => row.raw.subordinate_offsets);
            const tombstone = removedRaw ? good.tombstone(removedRaw.station_id) : null;
            const tombstoneIndex = removedRaw ? releaseModule.indexDoc(removedRaw, goodHeader, 0, 0, new Set(goodHeader.conventions.map(row => row.convention_id)), new Set(goodHeader.licences.map(row => row.licence_id))) : null;
            if (!goodConstants || !fitted || !offsetStation || !tombstone || !tombstoneIndex) throw new Error('Authentic plain native model fixtures missing');
            for (const [model_type, raw, expected, owner] of [
                ['RecordSpan', goodConstants.raw.record_span, goodConstants.record_span],
                ['Datum', constants.raw.datum, constants.datum],
                ['DroppedConstituent', fitted.raw.dropped_constituents[0], fitted.dropped_constituents[0]],
                ['Provenance', constants.raw.provenance, constants.provenance],
                ['Convention', good.conventions[0].raw, good.conventions[0]],
                ['Licence', good.licences[0].raw, good.licences[0]],
                ['Tombstone', removedRaw, tombstone, { release: good, entry: tombstoneIndex }],
                ['SubordinateOffsets', offsetStation.raw.subordinate_offsets, offsetStation.subordinateOffsets],
            ]) await observation(`B07.${model_type}`, () => canonical.materialize_typed_model(raw, { model_type, fields: [], native_owner: owner, native_record_span: model_type === 'RecordSpan' ? { set_id: goodConstants.set_id } : undefined }, origin, model_type), value => JSON.stringify(value.model) === JSON.stringify(expected) && Object.isFrozen(value.model));
            if (historicalInputs) {
                const metadata = new TextEncoder().encode(historicalInputs.metadata);
                const historicalHeader = loader.headerFromMeta(metadata);
                const slices = historicalInputs.slices;
                const documents = slices.map(row => JSON.parse(row.source));
                const entries = releaseModule.indexStations(historicalHeader, documents);
                const json = await import(`${moduleRoot}/json.js`);
                const source = { doc: (_entry, position) => json.deepFreeze(documents[position]), close: () => undefined };
                const historical = new releaseModule.Release(historicalHeader, entries, source, [], true, null);
                try {
                    const sourceStation = historical.requireStation('OTC-000cb5d3');
                    if (!sourceStation.source_records.length) throw new Error('Authentic original SourceRecord fixture missing');
                    const originalSourceRecord = sourceStation.source_records[0];
                    await observation('B07.SourceRecord', () => canonical.materialize_typed_model(originalSourceRecord.raw, { model_type: 'SourceRecord', fields: [], native_release: historical }, origin, 'SourceRecord'), value => value.model !== originalSourceRecord && value.model.raw === originalSourceRecord.raw && JSON.stringify(value.model) === JSON.stringify(originalSourceRecord));
                    for (const slice of slices.filter(row => row.historical)) {
                        const nativeStation = historical.requireStation(slice.station_id), offsets = nativeStation.subordinateOffsets;
                        if (!offsets?.vintage || !offsets.provenance) throw new Error('Original native historical aliases missing');
                        await observation(`B07.Fallback.${slice.station_id}`, () => canonical.materialize_typed_model(nativeStation.raw.subordinate_offsets.fallback, { model_type: 'Fallback', fields: [] }, origin, 'Fallback'), value => JSON.stringify(value.model) === JSON.stringify(offsets.fallback) && Object.isFrozen(value.model));
                        for (const [model_type, raw, value] of [
                            ['HistoricalOffsetVintage', nativeStation.raw.subordinate_offsets.vintage, offsets.vintage],
                            ['HistoricalOffsetProvenance', nativeStation.raw.subordinate_offsets.provenance, offsets.provenance],
                        ]) await observation(`B07.${model_type}.${slice.station_id}`, () => canonical.materialize_typed_model(raw, { model_type, fields: [], native_historical_parent: nativeStation.raw.subordinate_offsets }, origin, model_type), result => result.model === value && result.model === raw && Object.isFrozen(result.model));
                    }
                    const reference = historical.requireStation('OTC-a6c00a3f');
                    if (releaseModule.historicalVintageOf(reference.raw) !== null || releaseModule.historicalProvenanceOf(reference.raw) !== null) throw new Error('Existing absent historical aliases must remain null');
                    const visibleIds = historical.stations().map(row => row.station_id);
                    if (visibleIds.join(',') !== [...visibleIds].sort().join(',') || visibleIds.some(id => !slices.some(row => row.station_id === id))) throw new Error('Native station ordering changed');
                } finally { historical._close(); }
            }
        }
        await observation('B08.raw', () => canonical.retain_raw_source_record(station.raw, typeof process === 'object' ? 'typescript_node' : 'typescript_browser'), value => value === station.raw && Object.isFrozen(value));
        await observation('B24', () => canonical.project_station_index(station.raw, span, { scalar_types: '', models: '', subordinate_offsets: '', scope: '', fallback: '', native_header: header }), value => value.station_id === index.stored.station_id && value.offset === span.offset_bytes && JSON.stringify(value.aliases) === JSON.stringify(index.stored.aliases));
        await observation('B28', () => canonical.encode_cache_json({ variant: 'pointer_or_catalogue', value: cacheCase.input }), value => new TextDecoder().decode(value) === cacheCase.expected);
        const timeArgs = { member_id: 'Release.heights', arguments: { station: station.station_id, start: new Date('2000-01-01T00:00:00Z'), stop: new Date('2000-01-02T00:00:00Z') } };
        await observation('B39', () => canonical.parse_prediction_window(timeArgs, timeArgs, 600, { tz: 'station' }), value => value.start === 946684800 && value.stop === 946771200 && value.step === 600);
        const at = Date.parse(astroCase.args.at) / 1000;
        await observation('B41', () => canonical.evaluate_astronomy(model, at), value => value.utc_year === 2000 && Math.abs(value.constituent_terms[0][2] - (astroCase.expect.value - constants.raw.constituents[0].phase_deg)) < 1e-12);
        const publicHeights = await release.heightsAt(station, [new Date(at * 1000), new Date(at * 1000)], { datum: 'mean_level' });
        await observation('B42', () => canonical.evaluate_harmonic_height(model, [at, at], 'mean_level'), value => JSON.stringify(value) === JSON.stringify(publicHeights.items.map(row => row.height_m)));
        for (const [label, times] of [['empty', []], ['duplicates', [at, at]], ['unordered', [at + 600, at, at]]]) {
            const dates = times.map(value => new Date(value * 1000));
            const selected = { member_id: 'Release.heights_at', arguments: { station, times: dates } };
            await observation(`B39.instants.${label}`, () => canonical.parse_prediction_window(selected, selected, 600, { tz: 'station' }), value => JSON.stringify(value) === JSON.stringify({ instants: times }));
            const expected = await release.heightsAt(station, dates, { datum: 'mean_level' });
            await observation(`B42.values.${label}`, () => canonical.evaluate_harmonic_height(model, times, 'mean_level'), value => JSON.stringify(value) === JSON.stringify(expected.items.map(row => row.height_m)));
        }
        const window = { start: 1433116800, stop: 1433203200, step: null, instants: null };
        await observation('B43.roots', () => canonical.find_unrounded_tide_events(model, window), value => value.length > 0 && value.every(row => Number.isFinite(row.root_seconds)));
        const currentStation = release.stations().find(item => item.kind === 'current' && item.recommendedSet?.raw.current_bins?.length);
        if (!currentStation) throw new Error('Authentic current native owner missing');
        const currentConstants = currentStation.recommendedSet;
        const currentTable = await release.astroTable(currentConstants.convention.raw.astro_table_id);
        if (!currentTable) throw new Error('Authentic selected current astro table missing');
        const currentModel = { ...model, station: currentStation, constant_set: currentConstants, convention: currentConstants.convention, astro_table: currentTable._raw, required_constituents: currentConstants.raw.constituents ?? [] };
        if (foreignTables) {
            const harmonic = await import(`${moduleRoot}/predict/harmonic.js`);
            const seconds = Date.parse('2020-06-01T00:00:00Z') / 1000;
            const narrowStation = release.requireStation('OTC-P-0005'), narrowSet = narrowStation.recommendedSet;
            if (!narrowSet) throw new Error('Authentic M2-only selected set missing');
            const narrowModel = { ...model, station: narrowStation, constant_set: narrowSet, convention: narrowSet.convention, required_constituents: narrowSet.raw.constituents, datum_source: narrowSet.raw.datum };
            const foreignModel = { ...narrowModel, astro_table: currentTable._raw };
            const foreignSum = new harmonic.Sum(currentTable, narrowSet.raw.constituents);
            const refusal = call => {
                try { return { accepted: true, value: call() }; }
                catch (error) { return { accepted: false, error_name: error.name, error_message: error.message }; }
            };
            for (const [id, call] of [
                ['B41.foreign_table', () => canonical.evaluate_astronomy(foreignModel, seconds)],
                ['B42.foreign_table', () => canonical.evaluate_harmonic_height(foreignModel, [seconds], 'mean_level')],
                ['B41.foreign_sum', () => canonical.evaluate_astronomy({ ...narrowModel, native_sum: foreignSum }, seconds)],
            ]) await observation(id, () => refusal(call), value => value.accepted === false && value.error_name === 'CanonicalUnimplementedError');
        }
        if (extendedModels) {
            const engine = await import(`${moduleRoot}/predict/engine.js`);
            const nativeContext = engine.contextFor(currentStation, currentConstants, currentTable);
            const selectedBin = engine.bin(currentStation, currentConstants.raw.current_bins, undefined);
            engine.currentContext(nativeContext, selectedBin);
            const seconds = Date.parse('2020-06-01T00:00:00Z') / 1000 + 0.4369507, expected = nativeContext.total.yearData(2020);
            await observation('B41.current_major', () => canonical.evaluate_astronomy({ ...currentModel, native_sum: nativeContext.total }, seconds), value => JSON.stringify(value.constituent_terms) === JSON.stringify(expected[1]) && value.epoch_hours === (seconds - expected[0]) / 3600);
        }
        const currentWindow = { start: Date.parse('2020-06-01T00:00:00Z') / 1000, stop: Date.parse('2020-06-02T00:00:00Z') / 1000, step: null };
        const currentArgs = { member_id: 'Release.current_events', arguments: { station: currentStation.station_id, start: new Date(currentWindow.start * 1000), stop: new Date(currentWindow.stop * 1000) } };
        const publicCurrent = await release.currentEvents(currentStation, { start: currentArgs.arguments.start, stop: currentArgs.arguments.stop });
        await observation('B44.roots', () => canonical.find_unrounded_current_events(currentModel, currentWindow, currentArgs), value => value.length > 0 && JSON.stringify(value.filter(row => currentWindow.start <= Math.floor(row.root_seconds + 0.5) && Math.floor(row.root_seconds + 0.5) < currentWindow.stop).map(row => [Math.floor(row.root_seconds + 0.5), row.event_type, row.velocity_m_s, row.direction_deg])) === JSON.stringify(publicCurrent.items.map(row => [row.time.getTime() / 1000, row.type, row.velocity_ms, row.direction_deg])));
        return { result, public_control: { good_station_id: good.requireStation('OTC-T-0001').station_id, unchanged_astro: table.equilibriumArgument('M2', new Date(at * 1000)), raw_identity: release.requireStation(station.station_id).raw === station.raw } };
    } finally { good._close(); release._close(); }
}

const m1Inputs = {
    primitiveGuards: process.env.OTC_M1_PRIMITIVE_GUARDS === 'qualified',
    managedModels: process.env.OTC_M1_MANAGED === 'qualified',
    streamMetadata: fs.readFileSync(path.join(root, 'conformance/fixtures/good/OTC_20991231.2.meta.json'), 'utf8'),
    streamSource: fs.readFileSync(path.join(root, 'conformance/fixtures/good/OTC_20991231.2.jsonl'), 'utf8'),
    receiverGuards: process.env.OTC_M1_RECEIVER_GUARDS === 'qualified',
    requiredBindings: process.env.OTC_M1_REQUIRED_BINDINGS === 'qualified',
    requiredTimes: process.env.OTC_M1_REQUIRED_TIMES === 'qualified',
    foreignTables: process.env.OTC_M1_FOREIGN_TABLES === 'qualified',
    dtoModels: process.env.OTC_M1_DTO === 'qualified',
    pointerSource: fs.readFileSync(path.join(root, 'conformance/fixtures/good/OTC_latest.json'), 'utf8'),
    extendedModels: process.env.OTC_M1_MODELS === 'extended',
    extendedGuards: process.env.OTC_M1_GUARDS === 'extended',
    guardInputs: ['search', 'near', 'nearest', 'prune', 'download', 'constant_sets'].map(operation => {
        const file = { search: 'search', near: 'knc', nearest: 'knc', prune: 'cache', download: 'download', constant_sets: 'v1' }[operation];
        const cases = JSON.parse(fs.readFileSync(path.join(root, `conformance/cases/${file}.json`))).cases;
        const step = cases.flatMap(row => row.steps).find(step => step.op === operation);
        const { station_id, ...arguments_ } = step.args;
        const member_id = `${operation === 'prune' || operation === 'download' ? 'Client' : operation === 'constant_sets' ? 'Station' : 'Release'}.${operation}`;
        return { operation, selected: { member_id, arguments: arguments_ } };
    }),
    goodSource: fs.readFileSync(path.join(root, 'conformance/fixtures/good/OTC_20991231.2.json'), 'utf8'),
    predictSource: fs.readFileSync(path.join(root, 'conformance/fixtures/predict/OTC_20991231.7.json'), 'utf8'),
    astroCase: JSON.parse(fs.readFileSync(path.join(root, 'conformance/cases/predict-astro-values.json'))).cases[0].steps.find(step => step.op === 'equilibrium_argument' && step.args.name === 'M2' && step.args.at === '2000-01-01T00:00:00Z'),
    cacheCase: JSON.parse(fs.readFileSync(path.join(root, 'conformance/canonical/cache-golden.json'))).cases[0],
};
if (process.env.OTC_M1_HISTORICAL === 'qualified') {
    const historicalLocatorsPath = process.env.OTC_M1_HISTORICAL_LOCATORS ?? '/Users/jpr5/.local/share/copilotkit/cr/otc-codex-takeover/execution/sdk-core-sync/canonical-behavior/holistic-reset/implementation-plan/M1-PY/fixture-locators/locators.json';
    const historicalLocatorsBytes = fs.readFileSync(historicalLocatorsPath);
    assert.equal(sha256(historicalLocatorsBytes), 'd37d5f7f33d31000025f7eaf841fdaa7d590c96c2fee6346a61f3d89c35c26cb');
    const historicalLocators = JSON.parse(historicalLocatorsBytes);
    const closurePath = '/Users/jpr5/.local/share/copilotkit/cr/otc-codex-takeover/execution/sdk-core-sync/canonical-behavior/holistic-reset/implementation-plan/M1-TS/fixture-locators/locators.json';
    const closureBytes = fs.readFileSync(closurePath);
    assert.equal(sha256(closureBytes), '656aa9fda1e9daba388a71df873dd02df0d37ae421252c0f88fd4eb22a28c0ed');
    const closure = JSON.parse(closureBytes);
    const historicalMetadata = fs.readFileSync(historicalLocators.metadata_path);
    const historicalIndex = fs.readFileSync(historicalLocators.index_path);
    assert.equal(sha256(historicalMetadata), historicalLocators.metadata_sha256);
    assert.equal(sha256(historicalIndex), historicalLocators.index_sha256);
    m1Inputs.historicalInputs = { metadata: historicalMetadata.toString(), index: historicalIndex.toString(), source_path: historicalLocators.locators[0].source_path,
        slices: [...historicalLocators.locators, ...closure.additional_locators].map(row => { const bytes = fs.readFileSync(row.path); assert.equal(sha256(bytes), row.sha256); assert.equal(bytes.length, row.length); return { source: bytes.toString(), station_id: row.station_id, offset: row.offset, length: row.length, historical: row.models?.some(model => model.model === 'HistoricalOffsetVintage') ?? false }; }) };
}

test('M1 original native unrounded survivor phase is source-qualified before extraction', () => {
    const release = releaseFromJson(new TextEncoder().encode(m1Inputs.predictSource), []);
    const constants = release.requireStation('OTC-P-0001').recommendedSet;
    const table = predictionAstroTable(release);
    assert.ok(constants && table);
    const total = new Sum(table, constants.raw.constituents);
    const start = 1433116800;
    const fullPublic = events(total, start, 1433203200);
    const stop = Math.floor(fullPublic[0][0]);
    const phasePath = path.join(packageRoot, 'dist/predict/harmonic.js');
    const line = fs.readFileSync(phasePath, 'utf8').split('\n').findIndex(text => text.includes('return kept.filter'));
    const directory = process.env.OTC_M1_PROOF ?? '/Users/jpr5/.local/share/copilotkit/cr/otc-codex-takeover/execution/sdk-core-sync/canonical-behavior/holistic-reset/implementation-plan/M1-TS';
    fs.mkdirSync(directory, { recursive: true });
    if (process.env.OTC_M1_PHASE !== 'red') {
        const expected = JSON.parse(fs.readFileSync(path.join(directory, 'original-root-phase.json')));
        assert.equal(expected.input_sha256, sha256(Buffer.from(m1Inputs.predictSource)));
        assert.deepEqual(events(total, start, stop), expected.public_events);
        const station = release.requireStation('OTC-P-0001');
        const model = { station, release_view: release, constant_set: constants, convention: constants.convention,
            astro_table: table._raw, required_constituents: constants.raw.constituents, reference_bin: null, mean_term: 0, datum_source: constants.raw.datum };
        const actual = find_unrounded_tide_events(model, { start: expected.start, stop: expected.stop, step: null, instants: null });
        assert.deepEqual(actual.map(row => [row.root_seconds, row.event_type, row.height_m]), expected.kept);
        release._close(); return;
    }
    assert.ok(line >= 0, 'Actual original reporting predicate must exist');
    const session = new Session(); session.connect();
    let kept;
    session.on('Debugger.paused', event => {
        session.post('Debugger.evaluateOnCallFrame', { callFrameId: event.params.callFrames[0].callFrameId, expression: 'JSON.stringify(kept)', returnByValue: true }, (error, response) => {
            assert.ifError(error); kept = JSON.parse(response.result.value);
            session.post('Debugger.resume');
        });
    });
    try {
        session.post('Debugger.enable');
        session.post('Debugger.setBreakpointByUrl', { url: new URL('../dist/predict/harmonic.js', import.meta.url).href, lineNumber: line });
        const publicEvents = events(total, start, stop);
        assert.ok(kept && kept.length > publicEvents.length, 'Genuine padding survivor excluded by existing reporting filter required');
        const expected = { input_sha256: sha256(Buffer.from(m1Inputs.predictSource)), original_module: pin('js/dist/predict/harmonic.js'), start, stop, kept, public_events: publicEvents };
        fs.writeFileSync(path.join(directory, 'original-root-phase.json'), JSON.stringify(expected, null, 2));
        console.log(JSON.stringify({ surface: 'real native debugger pre-filter kept', total: kept.length, reported: publicEvents.length, excluded: kept.filter(row => !publicEvents.some(publicRow => publicRow[0] === row[0])) }));
    } finally { session.disconnect(); release._close(); }
});

test('M1 B41 fractional instant uses the exact original native year-cache terms', () => {
    const release = releaseFromJson(new TextEncoder().encode(m1Inputs.predictSource), []);
    const station = release.requireStation('OTC-P-0001'), constants = station.recommendedSet, table = predictionAstroTable(release);
    assert.ok(constants && table);
    const model = { station, release_view: release, constant_set: constants, convention: constants.convention, astro_table: table._raw,
        required_constituents: constants.raw.constituents, reference_bin: null, mean_term: 0, datum_source: constants.raw.datum };
    const seconds = 1433116800.4369507, total = new Sum(table, constants.raw.constituents);
    const directory = process.env.OTC_M1_PROOF ?? '/Users/jpr5/.local/share/copilotkit/cr/otc-codex-takeover/execution/sdk-core-sync/canonical-behavior/holistic-reset/implementation-plan/M1-TS';
    const phasePath = path.join(directory, 'original-year-phase.json');
    let expected;
    if (process.env.OTC_M1_YEAR_PHASE === 'red') {
        const modulePath = path.join(packageRoot, 'dist/predict/harmonic.js');
        const line = fs.readFileSync(modulePath, 'utf8').split('\n').findIndex(text => text.includes('const [origin, terms] = this.#year(year)'));
        assert.ok(line >= 0);
        const session = new Session(); session.connect();
        session.on('Debugger.paused', event => {
            session.post('Debugger.evaluateOnCallFrame', { callFrameId: event.params.callFrames[0].callFrameId, expression: 'JSON.stringify(this.#year(year))', returnByValue: true }, (error, response) => {
                assert.ifError(error); expected = JSON.parse(response.result.value); session.post('Debugger.resume');
            });
        });
        try {
            session.post('Debugger.enable'); session.post('Debugger.setBreakpointByUrl', { url: new URL('../dist/predict/harmonic.js', import.meta.url).href, lineNumber: line });
            const originalValue = total.value(seconds);
            assert.ok(expected);
            fs.writeFileSync(phasePath, JSON.stringify({ seconds, expected, original_value: originalValue, original_module: pin('js/dist/predict/harmonic.js'), input_sha256: sha256(Buffer.from(m1Inputs.predictSource)) }, null, 2));
        } finally { session.disconnect(); }
    } else expected = JSON.parse(fs.readFileSync(phasePath)).expected;
    try {
        const actual = evaluate_astronomy(model, seconds);
        assert.deepEqual(actual.constituent_terms, expected[1]);
        assert.equal(actual.epoch_hours, (seconds - expected[0]) / 3600);
    } finally { release._close(); }
});

test('M1 actual Node canonical leaves match authenticated original native values', async () => {
    const directory = process.env.OTC_M1_PROOF ?? '/Users/jpr5/.local/share/copilotkit/cr/otc-codex-takeover/execution/sdk-core-sync/canonical-behavior/holistic-reset/implementation-plan/M1-TS';
    const server = m1Server();
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    let observed;
    try {
        observed = await observeM1({ ...m1Inputs, moduleRoot: path.join(packageRoot, 'dist'), baseUrl: `http://127.0.0.1:${server.address().port}/fixture-good/`, cacheDir: fs.mkdtempSync(path.join(directory, 'dto-cache-')) });
    } finally { await new Promise(resolve => server.close(resolve)); }
    fs.mkdirSync(directory, { recursive: true });
    fs.writeFileSync(path.join(directory, `${process.env.OTC_M1_PHASE ?? 'current'}-node.json`), JSON.stringify(observed, null, 2));
    console.log(JSON.stringify(observed));
    assert.deepEqual(observed.result.filter(row => !row.passed), []);
});

test('M1 metadata B03 actual ordered native failure value', () => {
    const nativeFailure = new InvalidArgumentError('file cannot be combined with release, offline or onNetworkError');
    const input = { code: nativeFailure.code, structured_fields: { message: nativeFailure.message }, cause: null };
    const actual = select_canonical_error('open', [input], null);
    assert.strictEqual(actual, input);
    assert.equal(actual.code, 'invalid_argument');
    const directory = process.env.OTC_M1_PROOF ?? '/Users/jpr5/.local/share/copilotkit/cr/otc-codex-takeover/execution/sdk-core-sync/canonical-behavior/holistic-reset/implementation-plan/M1-TS';
    fs.mkdirSync(directory, { recursive: true });
    fs.writeFileSync(path.join(directory, 'b03-fresh-result.json'), JSON.stringify({ id: 'B03', input, actual, source: pin('js/src/canonical.ts'), build: pin('js/dist/canonical.js'), fixture: pin('js/test/canonical-shape.test.mjs'), stdout: JSON.stringify(actual), canonical_output_concept: 'canonical_error', value_preserved_by_identity: actual === input }, null, 2));
    console.log(JSON.stringify(actual));
});

test('M1 B42 copied datum errors preserve the original native fields and order', async () => {
    const release = releaseFromJson(new TextEncoder().encode(m1Inputs.predictSource), []);
    const table = predictionAstroTable(release);
    const cases = JSON.parse(fs.readFileSync(path.join(root, 'conformance/cases/predict-datum.json'))).cases;
    const steps = cases.find(row => row.id === 'predict-datum/unavailable').steps.filter(step => step.op === 'heights_at');
    const observeError = async call => {
        try { await call(); assert.fail('Expected original native datum failure'); }
        catch (error) { assert.equal(error.code, 'datum_unavailable'); return { name: error.name, code: error.code, message: error.message, missing: error.missing }; }
    };
    try {
        assert.ok(table);
        for (const { args } of steps) {
            const station = release.requireStation(args.station_id), constants = station.constantSet(args.set_id);
            assert.ok(constants);
            const times = args.times.map(value => new Date(value));
            const expected = await observeError(() => release.heightsAt(station, times, { setId: args.set_id, datum: args.datum }));
            const model = { station, release_view: release, constant_set: constants, convention: constants.convention,
                astro_table: table._raw, required_constituents: constants.raw.constituents, reference_bin: null, mean_term: 0, datum_source: constants.raw.datum ?? null };
            const actual = await observeError(() => evaluate_harmonic_height(model, times.map(value => Math.floor(value.getTime() / 1000)), args.datum));
            assert.deepEqual(actual, expected);
        }
    } finally { release._close(); }
});

test('M1 actual Chromium canonical leaves match authenticated original native values', async () => {
    const server = m1Server();
    await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
    let browser;
    try {
        browser = await chromium.launch({ headless: true });
        const page = await browser.newPage(); await page.goto(`http://127.0.0.1:${server.address().port}/`);
        const observed = await page.evaluate(({ inputs, code }) => globalThis.eval(`(${code})`)({ ...inputs, moduleRoot: '/dist', baseUrl: location.origin + '/fixture-good/', cacheDir: 'dto-native' }), { inputs: m1Inputs, code: observeM1.toString() });
        const directory = process.env.OTC_M1_PROOF ?? '/Users/jpr5/.local/share/copilotkit/cr/otc-codex-takeover/execution/sdk-core-sync/canonical-behavior/holistic-reset/implementation-plan/M1-TS';
        fs.mkdirSync(directory, { recursive: true });
        fs.writeFileSync(path.join(directory, `${process.env.OTC_M1_PHASE ?? 'current'}-browser.json`), JSON.stringify(observed, null, 2));
        console.log(JSON.stringify(observed));
        assert.deepEqual(observed.result.filter(row => !row.passed), []);
    } finally { await browser?.close(); await new Promise(resolve => server.close(resolve)); }
});
