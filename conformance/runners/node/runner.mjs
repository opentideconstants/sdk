#!/usr/bin/env node
// The TypeScript SDK's conformance runner for Node (conformance/README.md "The runner protocol").
//
//   uv run conformance/driver.py --runner "node conformance/runners/node/runner.mjs"
//
// It loads the built package from js/dist (run `npm run build` in js/ first), or the module named
// by --sdk (a path or a package name, for an installed tarball), and calls only its public API.
import { createInterface } from "node:readline";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";
import { makeRunner } from "./ops.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const argv = process.argv.slice(2);
const sdkArg = argv.indexOf("--sdk") >= 0 ? argv[argv.indexOf("--sdk") + 1] : path.join(here, "..", "..", "..", "js", "dist", "index.js");
const sdkSpec = sdkArg.startsWith(".") || path.isAbsolute(sdkArg) ? pathToFileURL(path.resolve(sdkArg)).href : sdkArg;

const out = (obj) => process.stdout.write(JSON.stringify(obj) + "\n");

let sdk;
try {
    sdk = await import(sdkSpec);
} catch (e) {
    process.stderr.write(`cannot load the SDK from ${sdkSpec}: ${e && e.stack ? e.stack : e}\n`);
    process.exit(3);
}

out({ hello: { runner: "typescript", version: sdk.VERSION, features: ["fs", "fetch", "json", "eager", "stream"] } });

const runner = makeRunner(sdk);
const rl = createInterface({ input: process.stdin, crlfDelay: Infinity });
for await (const line of rl) {
    if (!line.trim()) continue;
    const msg = JSON.parse(line); // a malformed request is a driver bug; let it raise
    out(await runner.handle(msg));
}
await runner.shutdown();
process.exit(0);
