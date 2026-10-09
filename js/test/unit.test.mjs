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

test("T36: an index with no releases list, or a file entry with no name, is invalid_release", async () => {
    const { parseIndex } = await import("../dist/core.js");
    const url = "https://example.invalid/OTC_index.json";
    assert.throws(() => parseIndex(enc({}), url), isCode("invalid_release"));
    assert.throws(() => parseIndex(enc({ releases: {} }), url), isCode("invalid_release"));
    const entry = { datestamp: "20991231", format_version: "1.0", files: [{ name: "OTC_20991231.json" }, 5] };
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
