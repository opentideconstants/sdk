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

// One line per reply: a reply the runner cannot encode becomes an uncaught: reply.
const out = (obj) => {
    let line;
    try {
        line = JSON.stringify(obj);
    } catch (e) {
        line = JSON.stringify({ ok: false, error: { code: `uncaught:${e.constructor.name}`, message: `cannot encode the reply: ${e.message}` } });
    }
    process.stdout.write(line + "\n");
};

let sdk;
try {
    sdk = await import(sdkSpec);
} catch (e) {
    process.stderr.write(`cannot load the SDK from ${sdkSpec}: ${e && e.stack ? e.stack : e}\n`);
    process.exit(3);
}

// The SDK's error base class and version must be there: a runner without them fails the handshake (exit 3).
if (typeof sdk.OpenTideConstantsError !== "function" || typeof sdk.VERSION !== "string") {
    process.stderr.write(`cannot load the SDK from ${sdkSpec}: it has no OpenTideConstantsError class or no VERSION string\n`);
    process.exit(3);
}

out({ hello: { runner: "typescript", version: sdk.VERSION, features: ["fs", "fetch", "json", "eager", "stream"] } });

const runner = makeRunner(sdk);
const rl = createInterface({ input: process.stdin, crlfDelay: Infinity });
for await (const line of rl) {
    if (!line.trim()) continue;
    let msg;
    try {
        msg = JSON.parse(line);
        if (msg === null || typeof msg !== "object" || Array.isArray(msg)) throw new TypeError("a request must be a JSON object");
    } catch (e) { // a request the runner cannot read: an error reply, and the runner goes on
        process.stderr.write(`bad request line: ${e}\n`);
        out({ ok: false, error: { code: `uncaught:${e.constructor.name}`, message: `bad request line: ${e.message}` } });
        continue;
    }
    out(await runner.handle(msg));
}
process.exit((await runner.shutdown()) ? 0 : 1);
