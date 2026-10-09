// Unit tests of pure helpers. The conformance suite (conformance/) is the main test.
import { test } from "node:test";
import assert from "node:assert/strict";
import * as otc from "../dist/index.js";

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
        convention_id: "c1", licence_id: "l1", constituents: ["M2"], ...o });
    const entry = (o) => ({ offset: 0, length: 10, station_id: "S", status: "active", name: "Ålesund", name_folded: "alesund",
        country: null, type: "reference", lat: 1, lon: 2, kind: "tide", aliases: {}, reference_station_id: null,
        offsets_licence_id: null, recommended_set_id: "S/a", sets: [set({})], ...o });
    const doc = (stations) => ({ index_version: 1, datestamp: "20991231", jsonl: "OTC_20991231.jsonl", jsonl_sha256: "ab", jsonl_size: 100, stations });
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
    const h = (o) => ({ format_version: "1.0", release: { datestamp: "20991231" }, conventions: [{ convention_id: "c" }], licences: [{ licence_id: "l" }], ...o });
    assert.ok(parseHeader(h({})));
    assert.throws(() => parseHeader(h({ conventions: [{ convention_id: "c" }, 5] })), isCode("invalid_release"));
    assert.throws(() => parseHeader(h({ licences: [{ licence_id: "l" }, { licence_id: "l" }] })), isCode("invalid_release"));
});

const GOOD = new URL("../../conformance/fixtures/good/", import.meta.url).pathname;

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
    const v = parseVerified(b({ files: { a: { sha256: 7, size: "x", url: 3 } }, datestamp: 5 }), "20991231");
    assert.deepEqual(v.files.a, { sha256: null, size: null, url: null });
    assert.equal(v.datestamp, "20991231");
    assert.throws(() => parseVerified(b({ files: {}, format_version: "1" }), "20991231"), isCode("invalid_release"));
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
        licences: [{ licence_id: "a", provider: null, attribution: "A text" }, { licence_id: "b", provider: null, attribution: "B text" },
            { licence_id: "o", provider: "Offsets Co", attribution: "O text" }],
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
