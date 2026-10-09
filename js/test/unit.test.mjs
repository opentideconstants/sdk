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
