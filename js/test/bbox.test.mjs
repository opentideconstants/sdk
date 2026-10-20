import { test } from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

// The same public consumer runs against the build and installed ESM/CJS packages.
const packagePath = process.env.OTC_BBOX_PACKAGE;
const sdk = process.env.OTC_BBOX_CJS
    ? createRequire(import.meta.url)(packagePath ?? "../dist/index.js")
    : await import(packagePath ?? "../dist/index.js");
const file = process.env.OTC_BBOX_NATIVE_JSONL
    ?? fileURLToPath(new URL("../../conformance/fixtures/good/OTC_20991231.2.jsonl", import.meta.url));
const oracle = process.env.OTC_BBOX_ORACLE
    ? JSON.parse(fs.readFileSync(process.env.OTC_BBOX_ORACLE, "utf8")) : null;
const rectangle = { south: 37.665, west: -122.4659, north: 37.8063, east: -122.3 };
const camelOptions = (args) => Object.fromEntries(Object.entries(args).map(([key, value]) =>
    [key.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase()), value]));
const fields = (station) => Object.fromEntries(["station_id", "name", "lat", "lon"].map((key) => [key, station[key]]));
const fixtureCases = [
    ["inclusive rectangle", rectangle, ["OTC-T-0001", "OTC-T-0003", "OTC-T-0004"]],
    ["filter before limit", { ...rectangle, type: "subordinate", limit: 1 }, ["OTC-T-0003"]],
    ["flagged opt-in", { ...rectangle, includeFlagged: true }, ["OTC-T-0001", "OTC-T-0002", "OTC-T-0003", "OTC-T-0004"]],
    ["null limit", { ...rectangle, limit: null }, ["OTC-T-0001", "OTC-T-0003", "OTC-T-0004"]],
    ["date line", { south: -1, west: 179.8, north: 1, east: -179.8 }, ["OTC-T-0007", "OTC-T-0008"]],
    ["empty rectangle", { south: 0, west: 0, north: 1, east: 1 }, []],
];

for (const mode of ["eager", "stream"]) test(`public bbox (${mode})`, async (t) => {
    const client = await sdk.OpenTideConstants.open({ file, mode });
    try {
        if (oracle) {
            for (const entry of oracle.filter((entry) => entry.mode === mode)) {
                await t.test(`${entry.case} variant ${entry.variant} ${entry.receiver}`, () => {
                    const target = entry.receiver === "Client" ? client : client.release;
                    const result = target.bbox(camelOptions(entry.request.args));
                    assert.deepEqual(result.map((station) => station.station_id), entry.expected_station_ids);
                    assert.deepEqual(result.map(fields), entry.expected_stations);
                    assert.ok(Object.isFrozen(result));
                });
            }
        } else {
            for (const [receiver, target] of [["Client", client], ["Release", client.release]]) {
                for (const [name, options, ids] of fixtureCases) {
                    await t.test(`${receiver} ${name}`, () => {
                        const result = target.bbox(options);
                        assert.deepEqual(result.map((station) => station.station_id), ids);
                        assert.ok(result.every((station) => station instanceof sdk.Station));
                        assert.ok(Object.isFrozen(result));
                    });
                }
                await t.test(`${receiver} invalid bounds and discovery options`, () => {
                    for (const options of [
                        undefined, null, {}, { ...rectangle, south: -91 }, { ...rectangle, north: 91 },
                        { ...rectangle, west: -181 }, { ...rectangle, east: 181 },
                        { ...rectangle, south: 40 }, { ...rectangle, east: NaN },
                        { ...rectangle, north: Infinity }, { ...rectangle, west: "-122" },
                        { ...rectangle, limit: 0 }, { ...rectangle, limit: 1.5 },
                        { ...rectangle, type: 42 }, { ...rectangle, includeFlagged: "yes" },
                    ]) assert.throws(() => target.bbox(options), (error) => error.code === "invalid_argument");
                });
            }
        }
    } finally {
        await client.close();
    }
});
