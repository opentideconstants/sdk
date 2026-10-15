// Unit tests of pure helpers. The conformance suite (conformance/) is the main test.
import { test } from "node:test";
import assert from "node:assert/strict";
import * as otc from "../dist/index.js";
import { Session } from "node:inspector";
import { createHash } from "node:crypto";
import { releaseFromJsonl } from "../dist/loader.js";
import { parseVerified } from "../dist/core.js";

test("datestamps order by date, then counter", async () => {
    const { compareDatestamps } = await import("../dist/constants.js");
    const ds = ["20261009", "20261008.10", "20261008", "20261008.2"].sort(compareDatestamps);
    assert.deepEqual(ds, ["20261008", "20261008.2", "20261008.10", "20261009"]);
});

test("names fold through the shared table", async () => {
    const { foldName } = await import("../dist/constants.js");
    assert.equal(foldName("  Tromsø   ÅLESUND "), "tromso alesund");
    assert.equal(foldName("Łeba Straße"), "leba strasse");
});

test("a bad datestamp is invalid_argument before any network access", async () => {
    await assert.rejects(otc.OpenTideConstants.open({ release: "20261008.1", offline: true }),
        (e) => e instanceof otc.OpenTideConstantsError && e.code === "invalid_argument");
});

test("every error class is a direct subclass of the base", () => {
    for (const name of ["NetworkError", "ChecksumError", "FileExistsError", "UnsupportedError", "InvalidArgumentError"]) {
        assert.equal(Object.getPrototypeOf(otc[name]), otc.OpenTideConstantsError, name);
    }
});

test("min_reader_version gate: this SDK reads format 1.0 and refuses anything newer", async () => {
    const { readerReads } = await import("../dist/constants.js");
    assert.equal(otc.SUPPORTED_FORMAT_VERSION, "1.0");
    assert.deepEqual([...otc.SUPPORTED_FORMAT_MAJORS], [1]);
    for (const v of ["1.0", "0.9", null, undefined]) assert.equal(readerReads(v), true, String(v));
    for (const v of ["1.1", "1.99", "2.0", "1.10"]) assert.equal(readerReads(v), false, v);
});

test("reader_too_old is its own error class with the code reader_too_old", () => {
    const e = new otc.ReaderTooOldError("x");
    assert.equal(Object.getPrototypeOf(otc.ReaderTooOldError), otc.OpenTideConstantsError);
    assert.equal(e.code, "reader_too_old");
});

const enc = (v) => new TextEncoder().encode(JSON.stringify(v));
const isCode = (code) => (e) => e instanceof otc.OpenTideConstantsError && e.code === code;

test("T36: an index with no releases list, or a file entry with no name, sha256 or size, is invalid_release", async () => {
    const { parseIndex } = await import("../dist/core.js");
    const url = "https://example.invalid/OTC_index.json";
    assert.throws(() => parseIndex(enc({}), url), isCode("invalid_release"));
    assert.throws(() => parseIndex(enc({ releases: {} }), url), isCode("invalid_release"));
    const file = { name: "OTC_20991231.json", sha256: "a".repeat(64), size: 1 };
    const entry = { datestamp: "20991231", format_version: "1.0", files: [file, 5] };
    // CR2 DR12: a string sha256 and an integer size of 0 or more
    for (const bad of [{ sha256: null }, { sha256: 5 }, { size: null }, { size: "1" }, { size: -1 }, { size: 1.5 }]) {
        assert.throws(() => parseIndex(enc({ releases: [{ ...entry, files: [{ ...file, ...bad }] }] }), url), isCode("invalid_release"));
    }
    assert.throws(() => parseIndex(enc({ releases: [entry] }), url), (e) => isCode("invalid_release")(e) && /OTC_index\.json/.test(e.message));
    assert.throws(() => parseIndex(enc({ releases: [{ ...entry, files: "x" }] }), url), isCode("invalid_release"));
    assert.equal(parseIndex(enc({ releases: [{ ...entry, files: [entry.files[0]] }] }), url)[0].files.length, 1);
});

/** A fake cache store that records its calls (keys are paths relative to <root>/v1). */
function fakeStore(files = new Map()) {
    const calls = [];
    return {
        calls, files,
        describe: (rel) => `fake:${rel}`,
        async mkdirs(rel) { calls.push(["mkdirs", rel]); },
        async read(rel) { calls.push(["read", rel]); return files.get(rel) ?? null; },
        async write(rel, b) { calls.push(["write", rel]); files.set(rel, b); },
        async remove(rel) { calls.push(["remove", rel]); files.delete(rel); },
        async removeDir(rel) { calls.push(["removeDir", rel]); },
        async list() { return []; },
        async lock(rel) { calls.push(["lock", rel]); return async () => { calls.push(["unlock", rel]); }; },
    };
}

function fakeCtx(store, responses) {
    const seen = [];
    return {
        seen,
        ctx: {
            platform: {
                name: "node", sha256: async () => "", gunzip: async (b) => b, env: () => null, sleep: async () => undefined,
                cache: async () => store,
                async get(url, o) {
                    seen.push({ url, headers: o.headers });
                    const r = responses.shift();
                    if (!r) throw new Error(`no response for ${url}`);
                    return { status: r.status, header: (n) => (r.headers ?? {})[n.toLowerCase()] ?? null, body: enc(r.body ?? null) };
                },
            },
            store, baseUrl: "https://example.invalid/", offline: false, timeout: null, proxy: null, caFile: null,
            userAgent: "test", onNetworkError: "use_cache", logger: null, mode: "eager",
        },
    };
}

test("T103: a 200 pointer body and its ETag are written under pointer/.lock, the old ETag removed first", async () => {
    const { getIndex } = await import("../dist/core.js");
    const store = fakeStore();
    const { ctx } = fakeCtx(store, [{ status: 200, body: { releases: [] }, headers: { etag: '"e2"' } }]);
    await getIndex(ctx);
    const w = store.calls.filter((c) => c[0] !== "read");
    assert.deepEqual(w, [["lock", "pointer"], ["remove", "pointer/OTC_index.json.etag"], ["write", "pointer/OTC_index.json"],
        ["write", "pointer/OTC_index.json.etag"], ["unlock", "pointer"]]);
});

test("T79: a 200 pointer body that is not JSON is a network error and the stored copy stays", async () => {
    const { getIndex } = await import("../dist/core.js");
    const good = enc({ releases: [] });
    const store = fakeStore(new Map([["pointer/OTC_index.json", good]]));
    const { ctx } = fakeCtx(store, [{ status: 200, body: "<html>", headers: { etag: '"x"' } }]);
    ctx.platform.get = async () => ({ status: 200, header: () => '"x"', body: new TextEncoder().encode("<html>") });
    await assert.rejects(getIndex(ctx), isCode("network"));
    assert.equal(store.files.get("pointer/OTC_index.json"), good);
    assert.equal(store.calls.some((c) => c[0] === "write"), false);
});

test("T45/D9: a malformed version string is invalid_release, in a release and in an index entry", async () => {
    const { readerReads, formatMajor } = await import("../dist/constants.js");
    const { parseIndex } = await import("../dist/core.js");
    for (const v of ["2", "1.x", "01.0", "1.0.0", " 1.0", "+1.0"]) assert.throws(() => readerReads(v), isCode("invalid_release"), v);
    assert.ok(Number.isNaN(formatMajor("01.0")));
    const url = "https://example.invalid/OTC_index.json";
    const e = { datestamp: "20991231", format_version: "1.0", files: [] };
    assert.throws(() => parseIndex(enc({ releases: [{ ...e, min_reader_version: "2" }] }), url), isCode("invalid_release"));
    assert.throws(() => parseIndex(enc({ releases: [{ ...e, format_version: "1." }] }), url), isCode("invalid_release"));
});

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

const tmpdir = () => fs.mkdtempSync(path.join(os.tmpdir(), "otc-unit-"));

test("T6: a held release lock with a .verified that is not usable in this mode is waited for, not skipped", async () => {
    const { nodePlatform } = await import("../dist/node.js");
    const root = tmpdir();
    const store = await nodePlatform().cache(root);
    const dir = path.join(root, "v1", "releases", "20991231");
    fs.mkdirSync(path.join(dir, ".lock"), { recursive: true });
    fs.writeFileSync(path.join(dir, ".verified"), "{\"files\":{}}");
    let settled = false;
    const p = store.lock("releases/20991231", { done: async () => false }).then((u) => { settled = true; return u; });
    await new Promise((r) => setTimeout(r, 1200));
    assert.equal(settled, false, "lock() returned while another process held .lock");
    fs.rmSync(path.join(dir, ".lock"), { recursive: true });
    const unlock = await p;
    assert.ok(fs.existsSync(path.join(dir, ".lock", "owner.json")));
    await unlock();
    assert.equal(fs.existsSync(path.join(dir, ".lock")), false);
});

test("T5/D3: owner.json carries a token, and a release whose lock was taken over leaves the new lock alone", async () => {
    const { nodePlatform } = await import("../dist/node.js");
    const root = tmpdir();
    const store = await nodePlatform().cache(root);
    const unlock = await store.lock("pointer");
    const owner = path.join(root, "v1", "pointer", ".lock", "owner.json");
    const o = JSON.parse(fs.readFileSync(owner, "utf8"));
    assert.match(String(o.token), /^[0-9a-f]{32,}$/);
    fs.writeFileSync(owner, JSON.stringify({ ...o, token: "another-process" }));
    await unlock();
    assert.ok(fs.existsSync(owner), "the lock of another owner was removed");
});

// spec 5.4 (CR2 DR3): a lock is stale only when the waiter has waited lockTimers.staleMs and the lock itself is at
// least 120 s old. These tests shorten the wait; the age stays 120 s, and the lock's age is set by its started_at or
// its mtime, so the outcome does not depend on timing.
async function fastLocks(t) {
    const { lockTimers } = await import("../dist/node.js");
    const saved = { ...lockTimers };
    Object.assign(lockTimers, { staleMs: 50, pollMs: 10 });
    t.after(() => Object.assign(lockTimers, saved));
}

function heldLock(root, ds, { startedAt, mtime } = {}) {
    const dir = path.join(root, "v1", "releases", ds);
    const lock = path.join(dir, ".lock");
    fs.mkdirSync(lock, { recursive: true });
    if (startedAt) fs.writeFileSync(path.join(lock, "owner.json"), JSON.stringify({ pid: 1, token: "other", started_at: startedAt }));
    if (mtime !== undefined) fs.utimesSync(lock, mtime, mtime);
    return lock;
}

const tokenOf = (lock) => JSON.parse(fs.readFileSync(path.join(lock, "owner.json"), "utf8")).token;

test("DR3: a waiter does not remove a lock that is only seconds old", async (t) => {
    await fastLocks(t);
    const { nodePlatform } = await import("../dist/node.js");
    const root = tmpdir();
    const store = await nodePlatform().cache(root);
    const lock = heldLock(root, "20991231", { startedAt: new Date().toISOString() });
    let polls = 0;
    // done ends the wait after 30 polls: 6 times the (shortened) stale wait
    const unlock = await store.lock("releases/20991231", { done: async () => ++polls >= 30 });
    await unlock();
    assert.ok(fs.existsSync(path.join(lock, "owner.json")), "a waiter removed a lock that is only seconds old");
    assert.equal(tokenOf(lock), "other", "a waiter took a lock that is only seconds old");
});

test("DR3: a waiter takes an old lock, by started_at or by mtime", async (t) => {
    await fastLocks(t);
    const { nodePlatform } = await import("../dist/node.js");
    const root = tmpdir();
    const store = await nodePlatform().cache(root);
    for (const [ds, how] of [["20991231", { startedAt: "2000-01-01T00:00:00Z" }], ["20991230", { mtime: 946684800 }]]) {
        const lock = heldLock(root, ds, how);
        const unlock = await store.lock(`releases/${ds}`, { done: async () => false });
        assert.notEqual(tokenOf(lock), "other");
        await unlock();
    }
});

test("DR3: two waiters on a crashed lock never hold it together", async (t) => {
    await fastLocks(t);
    const { nodePlatform } = await import("../dist/node.js");
    const root = tmpdir();
    const store = await nodePlatform().cache(root);
    heldLock(root, "20991231", { startedAt: "2000-01-01T00:00:00Z" });
    let inside = 0;
    let overlap = false;
    let firstIn;
    const held = new Promise((r) => { firstIn = r; });
    const one = async () => {
        const unlock = await store.lock("releases/20991231");
        firstIn();
        if (++inside > 1) overlap = true;
        // hold it for a while: the other waiter has waited past the stale time and must not take this young lock
        await new Promise((r) => setTimeout(r, 500));
        inside--;
        await unlock();
    };
    // the second waiter starts once the first holds the lock, so it meets a young lock (two waiters that read the
    // crashed lock's age at the same instant can still both remove it; spec 5.4 accepts that)
    const a = one();
    await held;
    await Promise.all([a, one()]);
    assert.equal(overlap, false, "two waiters held the lock at the same time");
});

test("DR3: the DOI note recovers a crashed lock and skips a young one", async () => {
    const { nodePlatform } = await import("../dist/node.js");
    const { syncZenodo } = await import("../dist/core.js");
    const root = tmpdir();
    const store = await nodePlatform().cache(root);
    const v = { files: {}, verified_at: "x", by: "x", datestamp: "20991231", format_version: "1.0", zenodo_version_doi: "10.1/old" };
    const vp = path.join(root, "v1", "releases", "20991231", ".verified");
    const lock = heldLock(root, "20991231");
    fs.writeFileSync(vp, JSON.stringify(v));
    const { ctx } = fakeCtx(store, []);
    const entry = { datestamp: "20991231", format_version: "1.0", zenodo_version_doi: "10.1/new", files: [] };
    await syncZenodo(ctx, v, entry);
    assert.equal(JSON.parse(fs.readFileSync(vp, "utf8")).zenodo_version_doi, "10.1/old", "the note rewrote .verified under a young lock");
    fs.writeFileSync(path.join(lock, "owner.json"), JSON.stringify({ token: "other", started_at: "2000-01-01T00:00:00Z" }));
    await syncZenodo(ctx, v, entry);
    assert.equal(JSON.parse(fs.readFileSync(vp, "utf8")).zenodo_version_doi, "10.1/new", "the note never recovers a crashed lock");
    assert.equal(fs.existsSync(lock), false, "the note did not release the lock it took");
});

test("T104: syncZenodo does not rewrite .verified while another process holds the release lock", async () => {
    const { syncZenodo } = await import("../dist/core.js");
    const v = { files: {}, verified_at: "x", by: "x", datestamp: "20991231", format_version: "1.0", zenodo_version_doi: "10.1/old" };
    const store = fakeStore(new Map([["releases/20991231/.verified", enc(v)]]));
    store.lock = async (rel, o) => { store.calls.push(["lock", rel, o?.wait]); return null; };
    const { ctx } = fakeCtx(store, []);
    await syncZenodo(ctx, v, { datestamp: "20991231", format_version: "1.0", zenodo_version_doi: "10.1/new", files: [] });
    assert.equal(store.calls.some((c) => c[0] === "write"), false);
});

test("T15: prune(null) is not a raw TypeError, and prune on a read-only release is a cache error", async () => {
    const root = tmpdir();
    const fixtures = new URL("../../conformance/fixtures/good/", import.meta.url).pathname;
    const c = await otc.OpenTideConstants.open({ file: path.join(fixtures, "OTC_20991231.2.jsonl"), cacheDir: root });
    try {
        assert.deepEqual([...c.prune(null)], []);
        for (const d of ["20991231", "20991231.2"]) {
            const dir = path.join(root, "v1", "releases", d);
            fs.mkdirSync(dir, { recursive: true });
            fs.writeFileSync(path.join(dir, ".verified"), "{\"files\":{}}");
        }
        fs.chmodSync(path.join(root, "v1", "releases", "20991231"), 0o555);
        assert.throws(() => c.prune({ keep: 1 }), isCode("cache"));
        fs.chmodSync(path.join(root, "v1", "releases", "20991231"), 0o755);
    } finally {
        c.close();
    }
});

test("T41/T18/T95/D4: usableIndex rejects out-of-bounds, unordered, wrongly folded, wrongly kinded and unresolved entries", async () => {
    const { usableIndex } = await import("../dist/release.js");
    const set = (o) => ({ set_id: "S/a", source: "x", source_type: "gauge", quantity: "water_level", qc_status: "ok",
        fallback: null, current_bins: [], convention_id: "c1", licence_id: "l1", constituents: ["M2"], ...o });
    const entry = (o) => ({ offset: 0, length: 10, station_id: "S", status: "active", name: "Ålesund", name_folded: "alesund",
        country: null, type: "reference", lat: 1, lon: 2, kind: "tide", aliases: {}, reference_station_id: null,
        offsets_licence_id: null, recommended_set_id: "S/a", sets: [set({})], current_offsets: [], subordinate_offsets: null, ...o });
    const doc = (stations) => ({ discovery_index_version: 1, index_version: 1, datestamp: "20991231", jsonl: "OTC_20991231.jsonl", jsonl_sha256: "ab", jsonl_size: 100, stations });
    const use = (stations) => usableIndex(doc(stations), "20991231", "ab", 100, new Set(["c1"]), new Set(["l1"]));
    assert.ok(use([entry({})]), "the good index is usable");
    assert.equal(use([entry({ offset: 95 })]), null, "offset + length past jsonl_size");
    assert.equal(use([entry({ length: 0 })]), null, "length 0");
    assert.equal(use([entry({ offset: 20 }), entry({ station_id: "T", offset: 10 })]), null, "offsets not increasing");
    assert.equal(use([entry({ name_folded: "x" })]), null, "name_folded is not the fold of name");
    assert.equal(use([entry({ kind: "current" })]), null, "kind is not the kind of the recommended set");
    assert.equal(use([entry({ status: "removed", sets: [set({ convention_id: "nope" })] })]), null, "a tombstone's set reference");
    assert.equal(use([entry({ sets: [set({ set_id: null })], recommended_set_id: null, kind: null })]), null, "set_id null");
    assert.equal(use([entry({ offsets_licence_id: "nope" })]), null, "offsets licence");
});

test("T46: a convention or licence that is not an object, and a repeated licence_id, are invalid_release", async () => {
    const { parseHeader } = await import("../dist/release.js");
    const h = (o) => ({ format_version: "1.0", release: { datestamp: "20991231" }, conventions: [{ convention_id: "c" }], licences: [{ licence_id: "l", attribution: "L", commercial_use: true }], ...o });
    assert.ok(parseHeader(h({})));
    assert.throws(() => parseHeader(h({ conventions: [{ convention_id: "c" }, 5] })), isCode("invalid_release"));
    assert.throws(() => parseHeader(h({ licences: [{ licence_id: "l", attribution: "L", commercial_use: true }, { licence_id: "l", attribution: "L", commercial_use: true }] })), isCode("invalid_release"));
});

test("CR2 DR2: a licence attribution that is not a string, or a provider that is neither a string nor null, is invalid_release", async () => {
    const { parseHeader } = await import("../dist/release.js");
    const h = (l) => ({ format_version: "1.0", release: { datestamp: "20991231" }, conventions: [], licences: [{ licence_id: "l", commercial_use: true, ...l }] });
    assert.ok(parseHeader(h({ provider: "P", attribution: "A" })));
    assert.ok(parseHeader(h({ provider: null, attribution: "A" })), "a null provider is allowed (CR D2 b)");
    for (const l of [{ provider: "P", attribution: null }, { provider: "P" }, { provider: "P", attribution: 5 }, { provider: 7, attribution: "A" }]) {
        assert.throws(() => parseHeader(h(l)), isCode("invalid_release"), JSON.stringify(l));
    }
});

test("R2-008: attribution never drops a licence it cannot find: invalid_release, not a shorter CC BY text", async () => {
    const { parseHeader, indexStations, Release } = await import("../dist/release.js");
    const doc = {
        format_version: "1.0", release: { datestamp: "20991231" }, conventions: [{ convention_id: "c" }],
        licences: [{ licence_id: "a", provider: "A", attribution: "A text", commercial_use: true }, { licence_id: "o", provider: "O", attribution: "O text", commercial_use: true }],
        stations: [
            { station_id: "R", status: "active", type: "reference", lat: 0, lon: 0, recommended_set_id: "R/s",
                constant_sets: [{ set_id: "R/s", source: "x", quantity: "water_level", qc_status: "ok", convention_id: "c", licence_id: "a", constituents: [] }] },
            { station_id: "S", status: "active", type: "subordinate", lat: 0, lon: 0, recommended_set_id: null,
                subordinate_offsets: { reference_station_id: "R", licence_id: "o" } },
        ],
    };
    const entries = indexStations(parseHeader(doc), doc.stations);
    // a header that lost licence o after the entries were checked against it: the guard, not reachable from data
    const header = parseHeader({ ...doc, licences: [doc.licences[0]] });
    const r = new Release(header, entries, { doc: (_e, i) => doc.stations[i], close: () => undefined }, [], true, null);
    assert.match(r.attribution(), /Sources: A: A text$/);
    assert.throws(() => r.attribution([r.station("S")]), isCode("invalid_release"));
});

const GOOD = new URL("../../conformance/fixtures/good/", import.meta.url).pathname;

function readFixtureLine(offset, length) {
    const fd = fs.openSync(path.join(GOOD, "OTC_20991231.2.jsonl"), "r");
    try {
        const bytes = new Uint8Array(length);
        const count = fs.readSync(fd, bytes, 0, length, offset);
        return bytes.subarray(0, count);
    } finally {
        fs.closeSync(fd);
    }
}

function retainedFixture(reader) {
    const jsonl = Uint8Array.from(fs.readFileSync(path.join(GOOD, "OTC_20991231.2.jsonl")));
    const meta = fs.readFileSync(path.join(GOOD, "OTC_20991231.2.meta.json"));
    return {
        bytes: new WeakRef(jsonl),
        release: releaseFromJsonl(meta, jsonl, { eager: false, files: [], reader }),
    };
}

async function collectInspectorGarbage() {
    const session = new Session();
    session.connect();
    try {
        await new Promise(setImmediate);
        await new Promise((resolve, reject) => {
            session.post("HeapProfiler.collectGarbage", (error) => error ? reject(error) : resolve());
        });
    } finally {
        session.disconnect();
    }
}

for (const [name, reader, retained] of [["positional file reader", readFixtureLine, false], ["byte-backed browser fallback", null, true]]) {
    test(`stream ${name} retains only its required input bytes`, async () => {
        const { release, bytes } = retainedFixture(reader);
        await collectInspectorGarbage();
        assert.equal(bytes.deref() !== undefined, retained, "whole JSONL input retention");
        const documents = fs.readFileSync(path.join(GOOD, "OTC_20991231.2.jsonl"), "utf8").trim().split("\n").map(JSON.parse);
        for (const document of documents) {
            const station = document.status === "removed" ? release.tombstone(document.station_id) : release.station(document.station_id);
            assert.deepEqual(station.raw, document, "on-demand record and provenance remain complete after GC");
        }
    });
}

test("T21: iterStations checks its filters when called, not at the first next()", async () => {
    const c = await otc.OpenTideConstants.open({ file: path.join(GOOD, "OTC_20991231.2.jsonl"), cacheDir: tmpdir() });
    try {
        assert.throws(() => c.iterStations({ country: 5 }), isCode("invalid_argument"));
    } finally {
        c.close();
    }
});

test("T20: time() reads RFC 3339 only, never a local time", async () => {
    const { time } = await import("../dist/json.js");
    assert.equal(time("2099-12-31T12:00:00+02:00").toISOString(), "2099-12-31T10:00:00.000Z");
    assert.equal(time("2099-12-31t12:00:00z").toISOString(), "2099-12-31T12:00:00.000Z");
    for (const v of ["2099-12-31T12:00:00", "2099-12-31", "Dec 31 2099", "2099-12-31T12:00Z"]) assert.equal(time(v), null, v);
});

test("T12: updateInterval 0 is invalid_argument", async () => {
    await assert.rejects(otc.OpenTideConstants.open({ file: path.join(GOOD, "OTC_20991231.2.jsonl"), cacheDir: tmpdir(), updateInterval: 0 }),
        isCode("invalid_argument"));
});

test("T82: names order by code point, not UTF-16 code unit", async () => {
    const { compareCodePoints } = await import("../dist/release.js");
    assert.ok(compareCodePoints("￿", "\u{10000}") < 0);
    assert.deepEqual(["\u{10000}", "￿", "a"].sort(compareCodePoints), ["a", "￿", "\u{10000}"]);
});

test("T22: the station_removed message gives the removed_reason as the file gives it", async () => {
    const { releaseFromJson } = await import("../dist/loader.js");
    const doc = { format_version: "1.0", release: { datestamp: "20991231" }, conventions: [], licences: [],
        stations: [{ station_id: "X", status: "removed", removed_reason: "renumbered" }] };
    const r = releaseFromJson(enc(doc), []);
    assert.throws(() => r.requireStation("X"), (e) => isCode("station_removed")(e) && /renumbered/.test(e.message));
});

test("T9/D19: a malformed proxy or baseUrl is invalid_argument, a missing caFile is io, before any network access", async () => {
    const o = { cacheDir: tmpdir(), baseUrl: "http://127.0.0.1:9/" };
    await assert.rejects(otc.OpenTideConstants.open({ ...o, proxy: "not a url" }), isCode("invalid_argument"));
    await assert.rejects(otc.OpenTideConstants.open({ ...o, proxy: "ftp://proxy:21" }), isCode("invalid_argument"));
    await assert.rejects(otc.OpenTideConstants.open({ ...o, baseUrl: "data.example/" }), isCode("invalid_argument"));
    await assert.rejects(otc.OpenTideConstants.open({ ...o, caFile: path.join(tmpdir(), "none.pem") }), isCode("io"));
});

test("T81: .verified is checked key by key, not cast", async () => {
    const { parseVerified } = await import("../dist/core.js");
    const b = (v) => new TextEncoder().encode(JSON.stringify(v));
    assert.equal(parseVerified(b({ files: { a: 5 } }), "20991231"), null);
    // a size that is not an integer, null or absent makes .verified malformed (spec 5.4, B10, C4)
    assert.equal(parseVerified(b({ files: { a: { sha256: null, size: "x", url: null } } }), "20991231"), null);
    assert.equal(parseVerified(b({ files: { a: { sha256: null, size: null, url: null } } }), "20991231"), null);
    assert.equal(parseVerified(b({ files: { a: { sha256: null, url: null } } }), "20991231"), null);
    const v = parseVerified(b({ files: { a: { sha256: 7, size: 3, url: 3 } }, datestamp: 5 }), "20991231");
    assert.equal(v, null);
    assert.equal(parseVerified(b({ files: {}, format_version: "1" }), "20991231"), null);
    // Isolate the URL guard: every other row field and the directory datestamp are valid.
    for (const [url, valid] of [[3, false], ["https://example.invalid/a", true], [null, true], [undefined, true]]) {
        const receipt = parseVerified(b({ files: { a: { sha256: "a".repeat(64), size: 3, url } }, datestamp: "20991231" }), "20991231");
        if (valid) {
            assert.ok(receipt);
            assert.equal(receipt.files.a.url, url ?? null);
        } else assert.equal(receipt, null);
    }
});

test("T81: receipt normalization and JSON roundtrip preserve every file key", () => {
    const files = {
        ["__proto__"]: { sha256: "A".repeat(64), size: 1, url: null },
        constructor: { sha256: null, size: 0, url: null },
        "ordinary.json": { sha256: "c".repeat(64), size: 3, url: "https://example.invalid/ordinary.json" },
    };
    const receipt = parseVerified(enc({ files }), "20991231");
    assert.ok(receipt);
    const expected = { ...files, ["__proto__"]: { ...files.__proto__, sha256: "a".repeat(64) } };
    assert.deepEqual(Object.keys(receipt.files).sort(), Object.keys(expected).sort());
    assert.deepEqual(JSON.parse(JSON.stringify(receipt)).files, expected);
});

test("T81: cached releases require the receipt datestamp to match its directory", async () => {
    const root = tmpdir();
    let client;
    try {
        // Both receipts have valid field types and files. Only one directory disagrees with its datestamp.
        for (const directoryStamp of ["20991231", "20991230"]) {
            const directory = path.join(root, "v1", "releases", directoryStamp);
            fs.mkdirSync(directory, { recursive: true });
            fs.writeFileSync(path.join(directory, ".verified"), JSON.stringify({ files: {}, datestamp: "20991230" }));
        }
        client = await otc.OpenTideConstants.open({ file: path.join(GOOD, "OTC_20991231.2.json"), cacheDir: root });
        assert.deepEqual(client.cachedReleases(), ["20991230"]);
    } finally {
        client?.close();
        fs.rmSync(root, { recursive: true, force: true });
    }
});

test("T81: a null or missing digest excludes a cached file without removing its release", async () => {
    for (const [mode, suffixes, missingHash, alternative] of [
        ["eager", ["json"], false, false], ["eager", ["json"], true, false],
        ["stream", ["jsonl", "meta.json"], false, false], ["stream", ["jsonl", "meta.json"], true, false],
        ["eager", ["json", "jsonl", "meta.json"], false, true], ["eager", ["json", "jsonl", "meta.json"], true, true],
    ]) {
        const root = tmpdir();
        const directory = path.join(root, "v1", "releases", "20991231.2");
        let client;
        try {
            fs.mkdirSync(directory, { recursive: true });
            const files = Object.fromEntries(suffixes.map(suffix => {
                const name = `OTC_20991231.2.${suffix}`;
                const body = alternative && suffix === "json" ? Buffer.from("{") : fs.readFileSync(path.join(GOOD, name));
                fs.writeFileSync(path.join(directory, name), body);
                const row = { size: body.length, sha256: createHash("sha256").update(body).digest("hex"), url: null };
                if (suffix === (mode === "eager" ? "json" : "jsonl")) {
                    if (missingHash) delete row.sha256;
                    else row.sha256 = null;
                }
                return [name, row];
            }));
            const marker = JSON.stringify({ files, datestamp: "20991231.2", format_version: "1.0", min_reader_version: "0.1" });
            fs.writeFileSync(path.join(directory, ".verified"), marker);
            if (alternative) {
                client = await otc.OpenTideConstants.open({ release: "20991231.2", cacheDir: root, mode, offline: true });
                assert.deepEqual(client.requireStation("OTC-T-0001").raw,
                    JSON.parse(fs.readFileSync(path.join(GOOD, "OTC_20991231.2.json"))).stations[0]);
            } else {
                for (const options of [{ release: "20991231.2" }, {}]) {
                    await assert.rejects(otc.OpenTideConstants.open({ ...options, cacheDir: root, mode, offline: true }), isCode("offline_unavailable"));
                }
            }
            assert.equal(fs.readFileSync(path.join(directory, ".verified"), "utf8"), marker);
            for (const name of Object.keys(files)) assert.ok(fs.existsSync(path.join(directory, name)));
        } finally {
            client?.close();
            fs.rmSync(root, { recursive: true, force: true });
        }
    }
});

test("T81: verifyOnOpen authenticates receipt-only cached payloads without a checksum sidecar", async (t) => {
    for (const [mode, suffixes] of [["eager", ["json"]], ["eager", ["jsonl", "meta.json"]], ["stream", ["jsonl", "meta.json"]]]) {
        await t.test(`${mode}/${suffixes[0]}`, async () => {
            const root = tmpdir();
            const directory = path.join(root, "v1", "releases", "20991231.2");
            let client;
            try {
                fs.mkdirSync(directory, { recursive: true });
                const files = Object.fromEntries(suffixes.map(suffix => {
                    const name = `OTC_20991231.2.${suffix}`;
                    const bytes = fs.readFileSync(path.join(GOOD, name));
                    fs.writeFileSync(path.join(directory, name), bytes);
                    return [name, { size: bytes.length, sha256: createHash("sha256").update(bytes).digest("hex"), url: null }];
                }));
                const marker = JSON.stringify({ files, datestamp: "20991231.2", format_version: "1.0", min_reader_version: "0.1" });
                fs.writeFileSync(path.join(directory, ".verified"), marker);
                const options = { release: "20991231.2", cacheDir: root, mode, offline: true, verifyOnOpen: true };
                client = await otc.OpenTideConstants.open(options);
                assert.deepEqual(client.requireStation("OTC-T-0001").raw,
                    JSON.parse(fs.readFileSync(path.join(GOOD, "OTC_20991231.2.json"))).stations[0]);
                assert.equal(fs.readFileSync(path.join(directory, ".verified"), "utf8"), marker);
                for (const name of Object.keys(files)) assert.ok(fs.existsSync(path.join(directory, name)));
                await assert.rejects(client.verify(), isCode("checksum_mismatch"));
                client.close();
                client = null;

                const payload = path.join(directory, `OTC_20991231.2.${suffixes[0]}`);
                const original = fs.readFileSync(payload);
                const tampered = Buffer.from(original.toString("utf8").replace("San Francisco", "Bad Francisco"));
                assert.notDeepEqual(tampered, original);
                assert.equal(tampered.length, original.length, "size checks must not detect this tamper");
                fs.writeFileSync(payload, tampered);
                assert.equal(fs.readFileSync(path.join(directory, ".verified"), "utf8"), marker);
                assert.equal(fs.existsSync(path.join(directory, "OTC_20991231.2.sha256")), false);
                await assert.rejects(async () => { client = await otc.OpenTideConstants.open(options); }, isCode("checksum_mismatch"));
            } finally {
                client?.close();
                fs.rmSync(root, { recursive: true, force: true });
            }
        });
    }
});

test("T81: explicit verify still requires the payload representation selected at open", async () => {
    for (const [selected, suffixes, removed] of [
        ["jsonl", ["jsonl", "meta.json"], ["jsonl"]], ["jsonl", ["jsonl", "meta.json"], ["meta.json"]],
        ["jsonl", ["jsonl", "meta.json"], ["jsonl", "meta.json"]], ["json", ["json"], ["json"]],
    ]) {
        const root = tmpdir();
        const directory = path.join(root, "v1", "releases", "20991231.2");
        let client;
        try {
            fs.mkdirSync(directory, { recursive: true });
            for (const suffix of ["json", "jsonl", "meta.json", "sha256"]) {
                fs.copyFileSync(path.join(GOOD, `OTC_20991231.2.${suffix}`), path.join(directory, `OTC_20991231.2.${suffix}`));
            }
            const files = Object.fromEntries(suffixes.map(suffix => {
                const name = `OTC_20991231.2.${suffix}`;
                const bytes = fs.readFileSync(path.join(directory, name));
                return [name, { size: bytes.length, sha256: createHash("sha256").update(bytes).digest("hex"), url: null }];
            }));
            fs.writeFileSync(path.join(directory, ".verified"), JSON.stringify({ files, datestamp: "20991231.2", format_version: "1.0", min_reader_version: "0.1" }));
            client = await otc.OpenTideConstants.open({ release: "20991231.2", cacheDir: root, mode: "eager", offline: true });
            assert.equal(await client.verify(), true, selected);
            for (const suffix of removed) fs.unlinkSync(path.join(directory, `OTC_20991231.2.${suffix}`));
            await assert.rejects(client.verify(), isCode("io"));
        } finally {
            client?.close();
            fs.rmSync(root, { recursive: true, force: true });
        }
    }
});

test("DR59: a non-string build run_id is invalid_release in each native file mode", async () => {
    const root = tmpdir();
    try {
        const doc = JSON.parse(fs.readFileSync(path.join(GOOD, "OTC_20991231.2.json")));
        doc.stations[0].constant_sets[0].provenance.build.run_id = 17;
        const prefix = path.join(root, "OTC_20991231.2");
        fs.writeFileSync(`${prefix}.json`, JSON.stringify(doc));
        fs.writeFileSync(`${prefix}.jsonl`, doc.stations.map(station => JSON.stringify(station) + "\n").join(""));
        const meta = { ...doc };
        delete meta.stations;
        fs.writeFileSync(`${prefix}.meta.json`, JSON.stringify(meta));
        for (const [extension, mode] of [["json", "eager"], ["jsonl", "eager"], ["jsonl", "stream"]]) {
            await assert.rejects(otc.OpenTideConstants.open({ file: `${prefix}.${extension}`, mode }), isCode("invalid_release"));
        }
    } finally {
        fs.rmSync(root, { recursive: true, force: true });
    }
});

test("DR59: build tool_versions must be a nullable map of strings in each native file mode", async () => {
    for (const value of [false, { engine: 17 }, { engine: null }]) {
        const root = tmpdir();
        try {
            const doc = JSON.parse(fs.readFileSync(path.join(GOOD, "OTC_20991231.2.json")));
            doc.stations[0].constant_sets[0].provenance.build.tool_versions = value;
            const prefix = path.join(root, "OTC_20991231.2");
            fs.writeFileSync(`${prefix}.json`, JSON.stringify(doc));
            fs.writeFileSync(`${prefix}.jsonl`, doc.stations.map(station => JSON.stringify(station) + "\n").join(""));
            const meta = { ...doc };
            delete meta.stations;
            fs.writeFileSync(`${prefix}.meta.json`, JSON.stringify(meta));
            for (const [extension, mode] of [["json", "eager"], ["jsonl", "eager"], ["jsonl", "stream"]]) {
                await assert.rejects(otc.OpenTideConstants.open({ file: `${prefix}.${extension}`, mode }), isCode("invalid_release"));
            }
        } finally {
            fs.rmSync(root, { recursive: true, force: true });
        }
    }
});

test("T34: a cache directory that cannot be read is a cache error, not an empty cache", { skip: process.getuid?.() === 0 }, async () => {
    const { listDir } = await import("../dist/node.js");
    const d = tmpdir();
    fs.chmodSync(d, 0o000);
    try {
        assert.throws(() => listDir(d), isCode("cache"));
    } finally {
        fs.chmodSync(d, 0o755);
    }
    assert.deepEqual(listDir(path.join(d, "missing")), []);
});

test("T30/T31: no Cache Storage and no DecompressionStream are unsupported, not raw errors or a corrupt file", async () => {
    const { browserPlatform } = await import("../dist/browser.js");
    const p = browserPlatform();
    const store = await p.cache(null);
    await assert.rejects(store.read("pointer/OTC_index.json"), isCode("unsupported"));
    const saved = globalThis.DecompressionStream;
    delete globalThis.DecompressionStream;
    try {
        await assert.rejects(p.gunzip(new Uint8Array([31, 139])), isCode("unsupported"));
    } finally {
        globalThis.DecompressionStream = saved;
    }
});

import * as http from "node:http";

test("T7: a proxy's user and password (percent-decoded) are sent as Proxy-Authorization", async () => {
    const { nodePlatform } = await import("../dist/node.js");
    let seen = null;
    const srv = http.createServer((req, res) => { seen = req.headers["proxy-authorization"] ?? null; res.end("{}"); });
    await new Promise((r) => srv.listen(0, "127.0.0.1", r));
    try {
        const port = srv.address().port;
        const res = await nodePlatform().get("http://example.invalid/OTC_latest.json",
            { headers: {}, timeout: 5, proxy: `http://us%40er:p%3Ass@127.0.0.1:${port}`, caFile: null });
        assert.equal(res.status, 200);
        assert.equal(seen, `Basic ${Buffer.from("us@er:p:ss").toString("base64")}`);
    } finally {
        srv.close();
    }
});

test("T89: NO_PROXY keeps bare IPv6 addresses whole, and strips the port of [v6]:port and host:port", async () => {
    const { noProxy } = await import("../dist/node.js");
    const saved = process.env.NO_PROXY;
    try {
        process.env.NO_PROXY = "::1, [fe80::2]:8080, example.org:443";
        assert.equal(noProxy("[::1]"), true);
        assert.equal(noProxy("[fe80::2]"), true);
        assert.equal(noProxy("example.org"), true);
        assert.equal(noProxy("[::]"), false);
    } finally {
        if (saved === undefined) delete process.env.NO_PROXY; else process.env.NO_PROXY = saved;
    }
});

test("T44/D21: after close, queries and release calls are io in eager and stream mode; close again does nothing", async () => {
    for (const mode of ["eager", "stream"]) {
        const c = await otc.OpenTideConstants.open({ file: path.join(GOOD, "OTC_20991231.2.jsonl"), cacheDir: tmpdir(), mode });
        const held = c.release;
        c.close();
        c.close();
        assert.throws(() => c.station("OTC-T-0001"), isCode("io"), mode);
        assert.throws(() => held.stations(), isCode("io"), mode);
        assert.throws(() => c.cachedReleases(), isCode("io"), mode);
        await assert.rejects(c.verify(), isCode("io"), mode);
    }
});

test("T1: an automatic update worker that cannot start answers at once, not after the timeout", async () => {
    const { runBlocking } = await import("../dist/node.js");
    const t0 = Date.now();
    const r = runBlocking(new URL("./no-such-worker.js", import.meta.url), {}, 20_000);
    assert.equal(r.ok, false);
    assert.ok(Date.now() - t0 < 10_000, `waited ${Date.now() - t0} ms`);
});

test("T23/D2: attribution prints a provider-less licence alone, counts a subordinate's offsets licence, refuses a foreign Station", async () => {
    const { releaseFromJson } = await import("../dist/loader.js");
    const set = (sid, lic) => ({ set_id: sid, source: "x", quantity: "water_level", qc_status: "ok", convention_id: "c", licence_id: lic, constituents: [] });
    const doc = {
        format_version: "1.0", release: { datestamp: "20991231" }, conventions: [{ convention_id: "c" }],
        licences: [{ licence_id: "a", provider: null, attribution: "A text", commercial_use: true }, { licence_id: "b", provider: null, attribution: "B text", commercial_use: true },
            { licence_id: "o", provider: "Offsets Co", attribution: "O text", commercial_use: true }],
        stations: [
            { station_id: "R", status: "active", type: "reference", lat: 0, lon: 0, recommended_set_id: "R/s", constant_sets: [set("R/s", "a")] },
            { station_id: "S", status: "active", type: "subordinate", lat: 0, lon: 0, recommended_set_id: null,
                subordinate_offsets: { reference_station_id: null, licence_id: "o" } },
            { station_id: "T", status: "active", type: "reference", lat: 0, lon: 0, recommended_set_id: "T/s", constant_sets: [set("T/s", "b")] },
        ],
    };
    const r = releaseFromJson(enc(doc), []);
    const text = r.attribution([r.station("R"), r.station("T"), r.station("S")]);
    assert.match(text, /Sources: A text; B text; Offsets Co: O text$/);
    const other = releaseFromJson(enc(doc), []);
    assert.throws(() => r.attribution([other.station("R")]), isCode("invalid_argument"));
});

test("CR2 DR8/DR28: an unknown status is logged once at load and is in no query; a line with no status is active", async () => {
    const fixtures = new URL("../../conformance/fixtures/bad/", import.meta.url).pathname;
    const lines = [];
    const logger = { debug() {}, info() {}, warn: (m) => lines.push(m) };
    const c = await otc.OpenTideConstants.open({ file: path.join(fixtures, "unknown-status", "OTC_20991231.jsonl"), mode: "stream", logger });
    try {
        const hits = lines.filter((m) => m.includes("OTC-T-0016"));
        assert.equal(hits.length, 1, JSON.stringify(lines));
        assert.match(hits[0], /"retired"/);
        assert.equal(c.station("OTC-T-0016"), null);
        assert.equal(c.tombstone("OTC-T-0016"), null);
    } finally {
        await c.close();
    }
    const n = await otc.OpenTideConstants.open({ file: path.join(fixtures, "no-status", "OTC_20991231.jsonl") });
    try {
        assert.equal(n.station("OTC-T-0020").status, "active");
        assert.equal(n.station("OTC-T-0019").status, "active");
    } finally {
        await n.close();
    }
});

test("D15: OPENTIDECONSTANTS_OFFLINE reads 1, true, yes and on (any case, trimmed) as offline", async () => {
    const saved = process.env.OPENTIDECONSTANTS_OFFLINE;
    try {
        for (const v of [" TRUE ", "yes", "On", "1"]) {
            process.env.OPENTIDECONSTANTS_OFFLINE = v;
            await assert.rejects(otc.OpenTideConstants.open({ cacheDir: tmpdir(), baseUrl: "http://127.0.0.1:9/" }), isCode("offline_unavailable"), v);
        }
    } finally {
        if (saved === undefined) delete process.env.OPENTIDECONSTANTS_OFFLINE; else process.env.OPENTIDECONSTANTS_OFFLINE = saved;
    }
});

test("T65: ESM only: exports has types, import and default, and no CommonJS condition names the ES module", async () => {
    const { readFileSync, existsSync } = await import("node:fs");
    const pkgUrl = new URL("../package.json", import.meta.url);
    const pkg = JSON.parse(readFileSync(pkgUrl, "utf8"));
    assert.equal(pkg.type, "module");
    const root = pkg.exports["."];
    assert.deepEqual(Object.keys(root), ["types", "import", "default"]);
    for (const k of ["require", "node-addons", "module-sync"]) assert.equal(root[k], undefined, k);
    for (const target of Object.values(root)) assert.ok(existsSync(new URL(target, pkgUrl)), target);
});

test("T65: require() of the package (Node 22.12 or later, require of an ES module) gives the same module as import", async () => {
    const { createRequire } = await import("node:module");
    const req = createRequire(import.meta.url);
    const viaRequire = req("opentideconstants");
    const viaImport = await import("opentideconstants");
    assert.equal(viaRequire.OpenTideConstants, viaImport.OpenTideConstants);
    assert.equal(viaRequire.VERSION, otc.VERSION);
});

// ---- PK-R2-03: download of latest on a network error (CR D22), all-or-nothing renames (CR2 DR17), and prune's
// partial failure (CR2 DR18)

import fsCjs from "node:fs";
import { syncBuiltinESMExports } from "node:module";

/** A server for conformance/fixtures/good; `script` maps a file name to [status, headers, body]. */
function fixtureServer(script = {}) {
    const srv = http.createServer((req, res) => {
        const name = decodeURIComponent(req.url.split("?")[0]).replace(/^\/+/, "");
        if (script[name]) {
            const [status, headers, body] = script[name];
            res.writeHead(status, headers);
            res.end(body);
            return;
        }
        let body = null;
        try { body = fs.readFileSync(path.join(GOOD, path.basename(name))); } catch { /* a 404 */ }
        res.writeHead(body ? 200 : 404);
        res.end(body ?? "");
    });
    return new Promise((resolve) => srv.listen(0, "127.0.0.1", () => resolve({
        url: `http://127.0.0.1:${srv.address().port}/`,
        close: () => new Promise((done) => { srv.closeAllConnections(); srv.close(done); }),
    })));
}

// a 200 pointer that is not JSON is a network error at once (spec 5.2 step 5), with no retry
const captivePortal = (script) => {
    for (const n of ["OTC_latest-f1.json", "OTC_latest.json"]) script[n] = [200, { "Content-Type": "text/html" }, "<html>portal</html>"];
};
const D2 = "20991231.2";
const BUNDLE = [`OTC_${D2}.jsonl`, `OTC_${D2}.meta.json`, `OTC_${D2}.sha256`];

test("D22: download of latest with a network error and use_cache writes the newest cached release", async () => {
    const script = {};
    const srv = await fixtureServer(script);
    const c = await otc.OpenTideConstants.open({ baseUrl: srv.url, cacheDir: tmpdir() });
    try {
        captivePortal(script);
        const to = path.join(tmpdir(), "bundle");
        const written = await c.download({ to });
        assert.deepEqual(written.map((p) => path.basename(p)).sort(), BUNDLE);
        for (const n of BUNDLE) assert.deepEqual(fs.readFileSync(path.join(to, n)), fs.readFileSync(path.join(GOOD, n)), n);
    } finally {
        c.close();
        await srv.close();
    }
});

test("D22: download of latest with a network error raises with onNetworkError raise, or with nothing cached", async () => {
    const script = {};
    const srv = await fixtureServer(script);
    const raising = await otc.OpenTideConstants.open({ baseUrl: srv.url, cacheDir: tmpdir(), onNetworkError: "raise" });
    const nothing = await otc.OpenTideConstants.open({ file: path.join(GOOD, `OTC_${D2}.jsonl`), baseUrl: srv.url, cacheDir: tmpdir() });
    try {
        captivePortal(script);
        for (const c of [raising, nothing]) {
            const to = path.join(tmpdir(), "bundle");
            await assert.rejects(c.download({ to }), isCode("network"));
            assert.ok(!fs.existsSync(to) || fs.readdirSync(to).length === 0);
        }
    } finally {
        raising.close();
        nothing.close();
        await srv.close();
    }
});

/** Runs fn with fs.renameSync failing when failing(source basename, destination basename) is true. */
async function failingRenames(failing, fn) {
    const real = fsCjs.renameSync;
    fsCjs.renameSync = (a, b) => {
        if (failing(path.basename(String(a)), path.basename(String(b)))) throw Object.assign(new Error(`injected ${b}`), { code: "EACCES" });
        return real(a, b);
    };
    syncBuiltinESMExports();
    try {
        return await fn();
    } finally {
        fsCjs.renameSync = real;
        syncBuiltinESMExports();
    }
}
const newFileInto = (s, d, name) => d === name && s.startsWith(".tmp-") && !s.startsWith(".tmp-bak-");

/** Downloads D2 into a new folder and changes its .jsonl and .meta.json; returns [client, server, folder, changed bytes]. */
async function changedBundle() {
    const srv = await fixtureServer();
    const c = await otc.OpenTideConstants.open({ release: D2, baseUrl: srv.url, cacheDir: tmpdir() });
    const to = tmpdir();
    await c.download({ release: D2, to });
    const before = {};
    for (const n of BUNDLE.slice(0, 2)) {
        fs.writeFileSync(path.join(to, n), `changed ${n}`);
        before[n] = fs.readFileSync(path.join(to, n));
    }
    return [c, srv, to, before];
}

test("DR17: a rename that fails restores every original that a new file replaced", async () => {
    const [c, srv, to, before] = await changedBundle();
    try {
        const meta = `OTC_${D2}.meta.json`;
        let err = null;
        await failingRenames((s, d) => newFileInto(s, d, meta), async () => {
            await c.download({ release: D2, to, overwrite: true }).catch((e) => { err = e; });
        });
        assert.ok(isCode("io")(err), `expected an io error, got ${err}`);
        assert.equal(err.path, path.join(to, meta));
        for (const [n, bytes] of Object.entries(before)) assert.deepEqual(fs.readFileSync(path.join(to, n)), bytes, `${n} was not restored`);
        assert.deepEqual(fs.readdirSync(to).sort(), BUNDLE);
    } finally {
        c.close();
        await srv.close();
    }
});

test("DR17: a restore that fails too is listed in the error", async () => {
    const [c, srv, to, before] = await changedBundle();
    try {
        const jsonl = `OTC_${D2}.jsonl`, meta = `OTC_${D2}.meta.json`;
        let err = null;
        await failingRenames((s, d) => newFileInto(s, d, meta) || (d === jsonl && s.startsWith(".tmp-bak-")), async () => {
            await c.download({ release: D2, to, overwrite: true }).catch((e) => { err = e; });
        });
        assert.ok(isCode("io")(err), `expected an io error, got ${err}`);
        assert.ok(err.message.includes(path.join(to, jsonl)), err.message);
        assert.deepEqual(fs.readFileSync(path.join(to, meta)), before[meta]);
    } finally {
        c.close();
        await srv.close();
    }
});

test("DR18: prune stops at the first failure and the cache error lists what it removed", async () => {
    const root = tmpdir();
    const c = await otc.OpenTideConstants.open({ file: path.join(GOOD, `OTC_${D2}.jsonl`), cacheDir: root });
    try {
        for (const d of ["20991230", "20991231", D2]) {
            const dir = path.join(root, "v1", "releases", d);
            fs.mkdirSync(dir, { recursive: true });
            fs.writeFileSync(path.join(dir, ".verified"), "{\"files\":{}}");
        }
        const ro = path.join(root, "v1", "releases", "20991231");
        fs.chmodSync(ro, 0o555);
        let err = null;
        try {
            c.prune({ keep: 0 });
        } catch (e) {
            err = e;
        } finally {
            fs.chmodSync(ro, 0o755);
        }
        assert.ok(isCode("cache")(err), `expected a cache error, got ${err}`);
        assert.deepEqual([...err.removed], [D2]);
        assert.deepEqual([...c.cachedReleases()], ["20991231", "20991230"]);
    } finally {
        c.close();
    }
});

test("R2-085 (CR2 DR16): update() heals a cached release whose file has the wrong size and downloads it again", async () => {
    const index = JSON.parse(fs.readFileSync(path.join(GOOD, "OTC_index.json"), "utf8"));
    let pointer = JSON.stringify(index.releases.find((e) => e.datestamp === "20991231"));
    const srv = http.createServer((req, res) => {
        const name = decodeURIComponent(new URL(req.url, "http://x").pathname.slice(1));
        if (name === "OTC_latest-f1.json") return res.end(pointer);
        try {
            res.end(fs.readFileSync(path.join(GOOD, path.basename(name))));
        } catch {
            res.statusCode = 404;
            res.end();
        }
    });
    await new Promise((r) => srv.listen(0, "127.0.0.1", r));
    const cacheDir = tmpdir();
    const o = { baseUrl: `http://127.0.0.1:${srv.address().port}/`, cacheDir, mode: "stream" };
    try {
        (await otc.OpenTideConstants.open({ ...o, release: "20991231.2" })).close();
        const jsonl = path.join(cacheDir, "v1", "releases", "20991231.2", "OTC_20991231.2.jsonl");
        fs.writeFileSync(jsonl, "truncated\n");
        const c = await otc.OpenTideConstants.open(o);
        assert.equal(c.release.datestamp, "20991231");
        pointer = fs.readFileSync(path.join(GOOD, "OTC_latest-f1.json"), "utf8");
        const r = await c.update();
        assert.deepEqual({ ...r }, { updated: true, from: "20991231", to: "20991231.2" });
        assert.equal(c.loadedFrom, "download");
        assert.equal(fs.statSync(jsonl).size, fs.statSync(path.join(GOOD, "OTC_20991231.2.jsonl")).size);
        c.close();
    } finally {
        srv.close();
    }
});

test("R2-087 (CR2 DR16): one .verified with a malformed version fails neither the offline open nor releases()", async () => {
    const srv = http.createServer((req, res) => {
        try {
            res.end(fs.readFileSync(path.join(GOOD, path.basename(decodeURIComponent(new URL(req.url, "http://x").pathname)))));
        } catch {
            res.statusCode = 404;
            res.end();
        }
    });
    await new Promise((r) => srv.listen(0, "127.0.0.1", r));
    const cacheDir = tmpdir();
    const o = { baseUrl: `http://127.0.0.1:${srv.address().port}/`, cacheDir, mode: "stream" };
    try {
        for (const release of ["20991231", "20991231.2"]) (await otc.OpenTideConstants.open({ ...o, release })).close();
        const vp = path.join(cacheDir, "v1", "releases", "20991231", ".verified");
        fs.writeFileSync(vp, JSON.stringify({ ...JSON.parse(fs.readFileSync(vp, "utf8")), format_version: "x" }));
        const off = await otc.OpenTideConstants.open({ ...o, offline: true });
        assert.equal(off.release.datestamp, "20991231.2");
        off.close();
        const c = await otc.OpenTideConstants.open(o);
        assert.ok((await c.releases()).length >= 2);
        c.close();
    } finally {
        srv.close();
    }
});

// CR2 DR6: impossible calendar fields, hour 24, a leap second and a time out of range in UTC are malformed (null),
// never rolled over into another date.
const BAD_TIMES = ["2099-02-30T00:00:00Z", "2099-02-31T00:00:00Z", "2097-02-29T00:00:00Z", "2099-12-31T24:00:00Z",
    "2099-12-31T23:59:60Z", "0001-01-01T00:00:00+01:00", "9999-12-31T23:59:59-01:00"];

test("an impossible or out-of-range RFC 3339 time is null, not rolled over (CR2 DR6)", async () => {
    const { time } = await import("../dist/json.js");
    for (const v of BAD_TIMES) assert.equal(time(v), null, `${v} -> ${time(v)?.toISOString()}`);
    assert.equal(time("2096-02-29T00:00:00Z")?.toISOString(), "2096-02-29T00:00:00.000Z");
    assert.equal(time("0001-01-01T01:00:00+01:00")?.toISOString(), "0001-01-01T00:00:00.000Z");
});

test("Retry-After with an impossible HTTP date or the wrong weekday is ignored (CR2 DR6)", async () => {
    const { httpGet } = await import("../dist/core.js");
    const run = async (date) => {
        const waits = [];
        let hits = 0;
        const platform = {
            get: async () => (++hits === 1
                ? { status: 503, header: (n) => (n.toLowerCase() === "retry-after" ? date : null), body: new Uint8Array() }
                : { status: 200, header: () => null, body: new Uint8Array() }),
            sleep: async (s) => { waits.push(s); },
        };
        const ctx = { platform, store: null, baseUrl: "http://x/", offline: false, timeout: null, proxy: null, caFile: null,
            userAgent: "t", onNetworkError: "raise", logger: null, mode: "eager" };
        await httpGet(ctx, "http://127.0.0.1:9/OTC_20991231.sha256");
        return waits;
    };
    for (const date of ["Sat, 30 Feb 2099 00:00:00 GMT", "Sun, 31 Feb 2099 00:00:00 GMT", "Sun, 29 Feb 2099 00:00:00 GMT",
        "Thu, 31 Dec 2099 24:00:00 GMT", "Thu, 31 Dec 2099 23:59:60 GMT", "Wed, 31 Dec 2099 23:59:59 GMT"]) {
        assert.deepEqual(await run(date), [1], date);
    }
    assert.deepEqual(await run("Thu, 31 Dec 2099 23:59:59 GMT"), [60]);
});

test("a release whose created or record_span time is impossible is invalid_release (CR2 DR6)", async () => {
    const fx = new URL("../../conformance/fixtures/bad/", import.meta.url);
    for (const root of ["created-impossible", "record-span-hour-24"]) {
        const file = new URL(`${root}/OTC_20991231.json`, fx).pathname;
        await assert.rejects(otc.OpenTideConstants.open({ file }), (e) => e.code === "invalid_release", root);
    }
});

test("PK-R2-05: Object.prototype names are data: an alias system __proto__ and a source constructor", async () => {
    const dir = new URL("../../conformance/fixtures/bad/proto-keys/", import.meta.url).pathname;
    for (const name of ["OTC_20991231.json", "OTC_20991231.jsonl"]) {
        const c = await otc.OpenTideConstants.open({ file: path.join(dir, name), cacheDir: tmpdir() });
        const rel = c.release;
        const s1 = rel.station("OTC-T-0001");
        assert.ok(Object.prototype.hasOwnProperty.call(s1.aliases, "__proto__"), name);
        assert.deepEqual(s1.aliases["__proto__"], ["PX-0001"]);
        assert.equal(Object.getPrototypeOf(s1.aliases), Object.prototype);
        assert.equal(rel.stationByAlias("__proto__", "PX-0001")?.station_id, "OTC-T-0001");
        assert.deepEqual(rel.station("OTC-T-0002").aliases["constructor"], ["CX-0002"]);
        assert.equal(rel.stats.source["constructor"], 2);
        assert.ok(Object.values(rel.stats.source).every((n) => typeof n === "number"));
        await c.close();
    }
});

test("PK-R2-07 / CR D4: a line read through the index that does not match its entry is invalid_release naming index-v1.json, and the index is dropped", async () => {
    const { headerFromMeta, indexJsonl, releaseFromJsonl } = await import("../dist/loader.js");
    const meta = fs.readFileSync(path.join(GOOD, "OTC_20991231.2.meta.json"));
    const jsonl = fs.readFileSync(path.join(GOOD, "OTC_20991231.2.jsonl"));
    const open = (mutate) => {
        const { entries } = indexJsonl(headerFromMeta(meta), jsonl, false);
        const e = entries.find((x) => x.station_id === "OTC-T-0001");
        e.stored = mutate(JSON.parse(JSON.stringify(e.stored)));
        let dropped = 0;
        const rel = releaseFromJsonl(meta, null, { eager: false, files: [], index: { entries }, reader: (o, l) => jsonl.subarray(o, o + l), dropIndex: () => { dropped++; } });
        return { rel, dropped: () => dropped };
    };
    const ok = open((s) => s);
    assert.equal(ok.rel.station("OTC-T-0001").station_id, "OTC-T-0001");
    assert.equal(ok.dropped(), 0);
    for (const [what, mutate] of [
        ["a set's convention", (s) => { s.sets[0].convention_id = "otc-greenwich-v1"; return s; }],
        ["a constituent left out", (s) => { s.sets[0].constituents.pop(); return s; }],
        ["the recommended set", (s) => { s.recommended_set_id = s.sets[1].set_id; return s; }],
    ]) {
        const r = open(mutate);
        assert.throws(() => r.rel.station("OTC-T-0001"), (e) => isCode("invalid_release")(e) && e.message.includes("index-v1.json"), what);
        assert.equal(r.dropped(), 1, what);
    }
});

test("CR2 DR9 / DR10: usableIndex rejects an entry with no byte for the previous line end, and reads 12.0 as 12", async () => {
    const { usableIndex } = await import("../dist/release.js");
    const entry = (o) => ({ offset: 0, length: 10, station_id: "S", status: "removed", name: null, name_folded: null,
        country: null, type: null, lat: null, lon: null, kind: null, aliases: {}, reference_station_id: null,
        offsets_licence_id: null, recommended_set_id: null, sets: [], current_offsets: [], subordinate_offsets: null, ...o });
    const doc = (stations, o) => ({ discovery_index_version: 1, index_version: 1, datestamp: "20991231", jsonl: "OTC_20991231.jsonl", jsonl_sha256: "ab", jsonl_size: 100, stations, ...o });
    const use = (stations, o = {}) => usableIndex(doc(stations, o), "20991231", "ab", 100, new Set(), new Set());
    assert.ok(use([entry({}), entry({ station_id: "T", offset: 11 })]), "the next line starts after the line end");
    assert.equal(use([entry({}), entry({ station_id: "T", offset: 10 })]), null, "no byte for the line end");
    assert.equal(use([entry({ length: 50 }), entry({ station_id: "T", offset: 10 })]), null, "overlapping entries");
    assert.ok(use([entry({ offset: 0.0, length: 10.0 })], { index_version: 1.0, jsonl_size: 100.0 }), "integral floats");
});

test("PK-R2-07 / spec 6.2: a failure to write the index is logged, not raised", async () => {
    const { loadCached } = await import("../dist/core.js");
    const d = "20991231.2";
    const read = (n) => { try { return fs.readFileSync(path.join(GOOD, n)); } catch { return null; } };
    const files = Object.fromEntries([`OTC_${d}.jsonl`, `OTC_${d}.meta.json`].map((n) => [n, { sha256: "ab", size: read(n).length, url: null }]));
    const warnings = [];
    const dir = {
        read: (n) => (n === "index-v1.json" ? null : read(n)),
        size: (n) => read(n)?.length ?? null,
        lineReader: () => null,
        writeIndex: () => { throw new Error("EROFS: read-only file system"); },
        removeIndex: () => undefined,
    };
    const rel = loadCached(dir, { files, verified_at: "x", by: "x", datestamp: d, format_version: null }, d, "stream", (m) => warnings.push(m));
    assert.equal(rel.station("OTC-T-0001").station_id, "OTC-T-0001");
    assert.ok(warnings.some((m) => m.includes("index-v1.json") && m.includes("EROFS")), JSON.stringify(warnings));
});

/** A local server for conformance/fixtures/good; over maps a file name to [status, body]; onRequest sees each name. */
async function serveGood(over = {}, onRequest = () => undefined) {
    const srv = http.createServer((req, res) => {
        const name = decodeURIComponent(new URL(req.url, "http://x").pathname.slice(1));
        onRequest(name);
        if (name in over) {
            res.writeHead(over[name][0]);
            res.end(over[name][1]);
            return;
        }
        let body = null;
        try { body = fs.readFileSync(path.join(GOOD, name)); } catch { /* 404 */ }
        res.writeHead(body ? 200 : 404);
        res.end(body ?? "");
    });
    await new Promise((r) => srv.listen(0, "127.0.0.1", r));
    return { srv, url: `http://127.0.0.1:${srv.address().port}/` };
}

const olderPointer = () => JSON.stringify(JSON.parse(fs.readFileSync(path.join(GOOD, "OTC_index.json"), "utf8")).releases.find((e) => e.datestamp === "20991231"));

test("R2-125/CR2 DR5: an update worker that cannot start never escapes a query: lastError is io with the cause, logged with its stack", async () => {
    const { srv, url } = await serveGood();
    const lines = [];
    const logger = { debug() {}, info() {}, warn: (m) => lines.push(m) };
    const c = await otc.OpenTideConstants.open({ baseUrl: url, cacheDir: tmpdir(), autoUpdate: true, updateInterval: 0.001, logger });
    const saved = globalThis.SharedArrayBuffer;
    try {
        await new Promise((r) => setTimeout(r, 20));
        globalThis.SharedArrayBuffer = class { constructor() { throw new TypeError("no SharedArrayBuffer here"); } };
        assert.equal(c.station("OTC-T-0001").station_id, "OTC-T-0001");
        assert.ok(c.lastError instanceof otc.FileError, String(c.lastError));
        assert.equal(c.lastError.cause?.message, "no SharedArrayBuffer here");
        assert.ok(lines.some((l) => l.includes("no SharedArrayBuffer here") && /\n\s+at /.test(l)), lines.join("\n---\n"));
    } finally {
        globalThis.SharedArrayBuffer = saved;
        c.close();
        srv.close();
    }
});

test("CR2 DR32: after close, metadata and client.release stay readable; queries and an iterator made before close are io", async () => {
    for (const mode of ["eager", "stream"]) {
        const c = await otc.OpenTideConstants.open({ file: path.join(GOOD, "OTC_20991231.2.jsonl"), cacheDir: tmpdir(), mode });
        const rel = c.release;
        const sub = c.station("OTC-T-0003");
        const ref = c.referenceStation(sub);
        const it = c.iterStations();
        it.next();
        c.close();
        assert.equal(c.release, rel, `${mode}: client.release after close`);
        assert.deepEqual([rel.datestamp, rel.format_version], ["20991231.2", "1.0"]);
        assert.ok(rel.created);
        assert.match(rel.citation, /20991231\.2/);
        assert.ok(Array.isArray(rel.files));
        assert.throws(() => it.next(), isCode("io"), `${mode}: an iterator made before close`);
        assert.throws(() => rel.referenceStation(sub), isCode("io"), mode);
        assert.throws(() => rel.subordinatesOf(ref), isCode("io"), mode);
        assert.throws(() => rel.stats, isCode("io"), mode);
    }
});

test("R2-128: a close while update() waits for the network wins: update is io and no release is swapped in", async () => {
    const over = { "OTC_latest-f1.json": [200, olderPointer()] };
    const { srv, url } = await serveGood(over);
    try {
        const c = await otc.OpenTideConstants.open({ baseUrl: url, cacheDir: tmpdir(), mode: "stream" });
        const old = c.release;
        delete over["OTC_latest-f1.json"];
        const p = c.update();
        c.close();
        await assert.rejects(p, isCode("io"));
        assert.equal(c.release, old, "update swapped in a release after close");
    } finally {
        srv.close();
    }
});

test("R2-128: a close while update() downloads the new release wins: update is io and the new release is not swapped in", async () => {
    let c = null;
    const over = { "OTC_latest-f1.json": [200, olderPointer()] };
    const { srv, url } = await serveGood(over, (name) => { if (name === "OTC_20991231.2.sha256") c?.close(); });
    try {
        c = await otc.OpenTideConstants.open({ baseUrl: url, cacheDir: tmpdir(), mode: "stream" });
        const old = c.release;
        delete over["OTC_latest-f1.json"];
        await assert.rejects(c.update(), isCode("io"));
        assert.equal(c.release, old, "update swapped in a release after close");
    } finally {
        srv.close();
    }
});

test("DR21: the user and password of a URL are not in an error message or a log line", async () => {
    const SECRET = "Pk12S3cretPW";
    const clean = (s) => {
        assert.ok(!s.includes(SECRET), s);
        assert.ok(!s.includes("otcuser"), s);
        assert.ok(s.includes("***@"), s);
    };
    for (const proxy of [`socks5://otcuser:${SECRET}@proxy.invalid:1080`]) {
        await assert.rejects(otc.OpenTideConstants.open({ proxy, offline: false, cacheDir: "/nonexistent-dr21", onNetworkError: "raise" }),
            (e) => { assert.equal(e.code, "invalid_argument"); clean(e.message); return true; });
    }
    const { nodePlatform } = await import("../dist/node.js");
    const saved = process.env.http_proxy;
    process.env.http_proxy = `otcuser:${SECRET}@proxy invalid`; // an environment proxy with no scheme
    try {
        await assert.rejects(nodePlatform().get("http://example.invalid/OTC_latest.json", { headers: {}, timeout: 5, proxy: null, caFile: null }),
            (e) => { assert.equal(e.code, "invalid_argument"); clean(e.message); return true; });
    } finally {
        if (saved === undefined) delete process.env.http_proxy; else process.env.http_proxy = saved;
    }
    const e = new otc.CacheError(`cannot read https://u:${SECRET}@h.example/x and ftp://a@b/c`);
    assert.equal(e.message, "cannot read https://***@h.example/x and ftp://***@b/c");
    const { log } = await import("../dist/core.js");
    const lines = [];
    log({ logger: { debug: (m) => lines.push(m), info: (m) => lines.push(m), warn: (m) => lines.push(m) } }, "debug",
        `GET http://otcuser:${SECRET}@127.0.0.1:1/good/OTC_latest-f1.json 200`);
    assert.equal(lines.length, 1);
    clean(lines[0]);
});

test("CR2 DR19: a timeout outside 0.001 to 1e6 s is invalid_argument, before any network access", async () => {
    // a server that answers late: before the fix a 1e7 s timer overflowed setTimeout and fired after 1 ms
    let requests = 0;
    const srv = http.createServer((req, res) => { requests++; setTimeout(() => { res.statusCode = 404; res.end(); }, 300); });
    await new Promise((r) => srv.listen(0, "127.0.0.1", r));
    try {
        const baseUrl = `http://127.0.0.1:${srv.address().port}/`;
        for (const timeout of [0.0001, 0.000999, 1e6 + 1, 1e7, 2 ** 31]) {
            await assert.rejects(otc.OpenTideConstants.open({ baseUrl, cacheDir: tmpdir(), timeout, onNetworkError: "raise" }),
                isCode("invalid_argument"), String(timeout));
        }
        assert.equal(requests, 0);
        for (const timeout of [0.001, 1e6]) {
            const c = await otc.OpenTideConstants.open({ file: path.join(GOOD, "OTC_20991231.2.jsonl"), cacheDir: tmpdir(), timeout });
            c.close();
        }
    } finally {
        srv.close();
    }
});

test("R2-118: a .gz that redirects to a URL with no suffix, sent with Content-Encoding: gzip, keeps its gzip bytes", async () => {
    const { nodePlatform } = await import("../dist/node.js");
    const { gzipSync } = await import("node:zlib");
    const gz = gzipSync(Buffer.from('{"x":1}\n'));
    const srv = http.createServer((req, res) => {
        if (req.url === "/OTC_20991231.json.gz") {
            res.writeHead(302, { Location: "/cdn/blob-1" });
            res.end();
        } else {
            res.writeHead(200, { "Content-Encoding": "gzip", "Content-Length": gz.length });
            res.end(gz);
        }
    });
    await new Promise((r) => srv.listen(0, "127.0.0.1", r));
    try {
        const base = `http://127.0.0.1:${srv.address().port}`;
        const res = await nodePlatform().get(`${base}/OTC_20991231.json.gz`, { headers: {}, timeout: 5, proxy: null, caFile: null });
        assert.equal(res.status, 200);
        assert.deepEqual(Buffer.from(res.body), gz);
        // a suffix-less URL asked for directly is still decoded
        const plain = await nodePlatform().get(`${base}/cdn/blob-1`, { headers: {}, timeout: 5, proxy: null, caFile: null });
        assert.equal(Buffer.from(plain.body).toString(), '{"x":1}\n');
    } finally {
        srv.close();
    }
});

test("R2-119: the automatic update interval runs on a monotonic clock, so a wall clock stepped back does not stop checks", async () => {
    // the check blocks this thread (Atomics.wait), so the server runs in another process
    const { spawn } = await import("node:child_process");
    const server = `
        const http = require("node:http"), fs = require("node:fs"), path = require("node:path");
        let pointer = 0;
        const srv = http.createServer((req, res) => {
            const name = path.basename(new URL(req.url, "http://x").pathname);
            if (name === "count") return res.end(String(pointer));
            if (name.startsWith("OTC_latest")) pointer++;
            fs.readFile(path.join(${JSON.stringify(GOOD)}, name), (err, data) => {
                if (err) { res.statusCode = 404; res.end(); } else res.end(data);
            });
        });
        srv.listen(0, "127.0.0.1", () => console.log(srv.address().port));`;
    const child = spawn(process.execPath, ["-e", server], { stdio: ["ignore", "pipe", "inherit"] });
    const realNow = Date.now;
    let c = null;
    try {
        const port = await new Promise((r) => child.stdout.once("data", (d) => r(String(d).trim())));
        const base = `http://127.0.0.1:${port}/`;
        const count = async () => Number(await (await fetch(`${base}count`)).text());
        c = await otc.OpenTideConstants.open({ baseUrl: base, cacheDir: tmpdir(), autoUpdate: true, updateInterval: 0.2 });
        const before = await count();
        const stepped = realNow() - 3_600_000;   // the wall clock is stepped back one hour (NTP, a VM resume)
        Date.now = () => stepped;
        await new Promise((r) => setTimeout(r, 300));
        c.station("OTC-T-0001");   // a query after the interval runs the check
        const after = await count();
        assert.ok(after > before, `no update check after the interval (pointer requests ${before} -> ${after})`);
    } finally {
        Date.now = realNow;
        c?.close();
        child.kill();
    }
});

test("R2-117: an https proxy is verified against the default roots plus caFile, for https and http targets", async () => {
    // test/tls: two throwaway CAs (100 years). proxy-ca stands for a CA the system trusts (NODE_EXTRA_CA_CERTS in the
    // child); target-ca is the caFile, a private CA. NODE_EXTRA_CA_CERTS is read at start-up, so the GET runs in a child.
    const https = await import("node:https");
    const net = await import("node:net");
    const { spawn } = await import("node:child_process");
    const TLS = new URL("./tls/", import.meta.url).pathname;
    const pem = (n) => fs.readFileSync(path.join(TLS, n));
    const target = https.createServer({ key: pem("target.key"), cert: pem("target.pem") }, (req, res) => res.end("target"));
    const proxyWith = (name) => https.createServer({ key: pem(`${name}.key`), cert: pem(`${name}.pem`) }, (req, res) => res.end("via-proxy"))
        .on("connect", (req, sock, head) => {
            const [h, p] = req.url.split(":");
            const up = net.connect(Number(p), h, () => {
                sock.write("HTTP/1.1 200 Connection Established\r\n\r\n");
                up.write(head);
                up.pipe(sock);
                sock.pipe(up);
            });
            up.on("error", () => sock.destroy());
            sock.on("error", () => up.destroy());
        });
    const publicProxy = proxyWith("proxy");    // a proxy with a certificate from a system-trusted CA
    const privateProxy = proxyWith("target");  // a proxy with a certificate from the caFile's private CA
    const servers = [target, publicProxy, privateProxy];
    await Promise.all(servers.map((s) => new Promise((r) => s.listen(0, "127.0.0.1", r))));
    const port = (s) => s.address().port;
    const get = (url, proxy) => new Promise((resolve) => {
        const script = `
            const { nodePlatform } = await import(${JSON.stringify(new URL("../dist/node.js", import.meta.url).href)});
            try {
                const r = await nodePlatform().get(${JSON.stringify(url)}, { headers: {}, timeout: 5, proxy: ${JSON.stringify(proxy)}, caFile: ${JSON.stringify(path.join(TLS, "target-ca.pem"))} });
                console.log(r.status + " " + new TextDecoder().decode(r.body));
            } catch (e) { console.log("error " + e.code + ": " + (e.cause?.code ?? e.message)); }`;
        const child = spawn(process.execPath, ["--input-type=module", "-e", script],
            { env: { ...process.env, NODE_EXTRA_CA_CERTS: path.join(TLS, "proxy-ca.pem") }, stdio: ["ignore", "pipe", "ignore"] });
        let out = "";
        child.stdout.on("data", (d) => { out += d; });
        child.on("close", () => resolve(out.trim()));
    });
    try {
        // an https target through a public https proxy: caFile is for the target, not for the proxy
        // (localhost, not 127.0.0.1: the tunnelled TLS sends the host as SNI, which Node refuses for an IP)
        assert.equal(await get(`https://localhost:${port(target)}/x`, `https://127.0.0.1:${port(publicProxy)}`), "200 target");
        // an http target through an https proxy whose CA is the caFile
        assert.equal(await get(`http://example.invalid/x`, `https://127.0.0.1:${port(privateProxy)}`), "200 via-proxy");
    } finally {
        servers.forEach((s) => { s.closeAllConnections(); s.close(); });
    }
});

// ---- CR2 PK-R2-11: every failure leaves the SDK as an SDK error with the spec 4.8 code

/** A local server that answers 404 to everything and counts the requests. */
async function counting404() {
    const s = { requests: 0 };
    s.srv = http.createServer((req, res) => { s.requests++; res.statusCode = 404; res.end(); });
    await new Promise((r) => s.srv.listen(0, "127.0.0.1", r));
    s.url = `http://127.0.0.1:${s.srv.address().port}/`;
    return s;
}

test("DR20: a userAgent with a control or non-latin-1 character is invalid_argument at open, before any request", async () => {
    const s = await counting404();
    try {
        for (const ua of ["app\r\nX: 1", "app\u00851", "app€1", "app\u{1F30A}"]) {
            const cacheDir = fs.mkdtempSync(path.join(os.tmpdir(), "otc-ua-"));
            await assert.rejects(otc.OpenTideConstants.open({ baseUrl: s.url, cacheDir, userAgent: ua }), isCode("invalid_argument"), JSON.stringify(ua));
        }
        assert.equal(s.requests, 0);
    } finally {
        s.srv.close();
    }
});

test("R2-097: a read error in stream mode (EISDIR, EIO, EBADF) is io, not a raw Node error", async () => {
    const { openLineReader } = await import("../dist/node.js");
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "otc-read-"));
    const r = openLineReader(dir); // a directory opens for reading; every read fails with EISDIR
    try {
        assert.throws(() => r.read(0, 10), (e) => isCode("io")(e) && e.cause?.code === "EISDIR");
    } finally {
        r.close();
    }
});

test("R2-099: proxy credentials that are not valid percent-encoding are invalid_argument, not a raw URIError", async () => {
    const s = await counting404();
    const proxy = `http://u:p%ZZ@127.0.0.1:${s.srv.address().port}/`;
    try {
        const cacheDir = fs.mkdtempSync(path.join(os.tmpdir(), "otc-px-"));
        await assert.rejects(otc.OpenTideConstants.open({ baseUrl: s.url, cacheDir, proxy }), isCode("invalid_argument"));
        const { nodePlatform } = await import("../dist/node.js");
        await assert.rejects(nodePlatform().get("http://example.invalid/x", { headers: {}, timeout: 5, proxy, caFile: null }),
            isCode("invalid_argument"));
        assert.equal(s.requests, 0);
    } finally {
        s.srv.close();
    }
});

test("R2-109 (DR5): a worker failure with no SDK code is io with its cause, never network; ChecksumError keeps expected and actual", async () => {
    const { errorFromWorker } = await import("../dist/client.js");
    assert.equal(typeof errorFromWorker, "function");
    const raw = errorFromWorker({ ok: false, message: "x is not a function", cause: { name: "TypeError", message: "x is not a function", stack: "TypeError: x\n    at f" } });
    assert.equal(raw.code, "io");
    assert.equal(raw.cause?.name, "TypeError");
    assert.match(String(raw.cause?.stack), /at f/);
    const sum = errorFromWorker({ ok: false, code: "checksum_mismatch", message: "m", path: "OTC_x.jsonl", expected: "aa", actual: "bb" });
    assert.deepEqual([sum.code, sum.file, sum.expected, sum.actual], ["checksum_mismatch", "OTC_x.jsonl", "aa", "bb"]);
    const net = errorFromWorker({ ok: false, code: "network", message: "m", url: "http://x/", status: 503 });
    assert.deepEqual([net.code, net.url, net.status], ["network", "http://x/", 503]);
});

test("R2-109: a worker that fails after it ran (a DataCloneError) is not labelled as failing to start, and keeps the cause", async () => {
    const { runBlocking } = await import("../dist/node.js");
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "otc-worker-"));
    const mod = path.join(dir, "w.mjs");
    fs.writeFileSync(mod, 'import { workerData } from "node:worker_threads";\nworkerData.port.postMessage({ ok: false, f() {} });\n');
    const res = runBlocking(new URL(`file://${mod}`), {}, 30_000);
    assert.equal(res.ok, false);
    assert.doesNotMatch(String(res.message), /failed to start/);
    assert.equal(res.cause?.name, "DataCloneError");
});

test("K-NC DR106: commercialOnly is a boolean; undefined is false; anything else, null included, is invalid_argument", async () => {
    const file = path.join(new URL("../../conformance/fixtures/knc/", import.meta.url).pathname, "OTC_20991231.2.jsonl");
    for (const v of [1, 0, "true", null, [true]]) {
        await assert.rejects(otc.OpenTideConstants.open({ file, commercialOnly: v }), isCode("invalid_argument"), JSON.stringify(v));
    }
    for (const [v, want] of [[true, "OTC-T-0181/w-ok"], [false, "OTC-T-0181/x-nc"], [undefined, "OTC-T-0181/x-nc"]]) {
        const c = await otc.OpenTideConstants.open({ file, commercialOnly: v });
        assert.equal(c.station("OTC-T-0181").recommendedSet.set_id, want);
        await c.close();
    }
});
