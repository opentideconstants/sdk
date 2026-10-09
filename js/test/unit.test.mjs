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
