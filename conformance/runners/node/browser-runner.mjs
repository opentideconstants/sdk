#!/usr/bin/env node
// The TypeScript SDK's conformance runner in a headless browser (profile typescript-browser).
//
//   uv run conformance/driver.py --runner "node conformance/runners/node/browser-runner.mjs"
//
// It serves js/dist and ops.mjs from its own HTTP server on 127.0.0.1 (a different origin from the
// fixture server, so every request the SDK makes is cross-origin and needs the fixture server's CORS
// headers), opens a page in headless Chromium (Playwright, a devDependency of js/), and relays each
// request line to the page. The page runs the same op table as the Node runner, against the public API
// of the SDK's browser build. It has no file system: the hello claims fetch, json, eager and stream.
import { createServer } from "node:http";
import { createReadStream, existsSync, statSync } from "node:fs";
import { createRequire } from "node:module";
import { createInterface } from "node:readline";
import os from "node:os";
import path from "node:path";

const here = path.dirname(new URL(import.meta.url).pathname);
const jsDir = path.resolve(here, "..", "..", "..", "js");
const distDir = path.join(jsDir, "dist");
// The driver points HOME at a temporary directory; find Playwright's browsers under the real home.
if (!process.env.PLAYWRIGHT_BROWSERS_PATH) {
    const home = os.userInfo().homedir;
    process.env.PLAYWRIGHT_BROWSERS_PATH = process.platform === "darwin" ? path.join(home, "Library", "Caches", "ms-playwright")
        : process.platform === "win32" ? path.join(home, "AppData", "Local", "ms-playwright") : path.join(home, ".cache", "ms-playwright");
}
const require = createRequire(path.join(jsDir, "package.json"));
const { chromium } = require("playwright");

const TYPES = { ".js": "text/javascript", ".mjs": "text/javascript", ".html": "text/html", ".json": "application/json" };

function serve() {
    const server = createServer((req, res) => {
        const url = new URL(req.url, "http://localhost");
        let file = null;
        if (url.pathname === "/") {
            res.writeHead(200, { "content-type": "text/html" });
            res.end("<!doctype html><meta charset=utf-8><title>otc conformance</title>");
            return;
        }
        if (url.pathname === "/ops.mjs") file = path.join(here, "ops.mjs");
        else if (url.pathname.startsWith("/sdk/")) file = path.join(distDir, path.normalize(url.pathname.slice(5)));
        if (!file || !file.startsWith(here) && !file.startsWith(distDir) || !existsSync(file) || !statSync(file).isFile()) {
            res.writeHead(404);
            res.end();
            return;
        }
        res.writeHead(200, { "content-type": TYPES[path.extname(file)] ?? "application/octet-stream" });
        createReadStream(file).pipe(res);
    });
    return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server)));
}

const out = (obj) => process.stdout.write(JSON.stringify(obj) + "\n");

const server = await serve();
const origin = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext();
const page = await context.newPage();
page.on("console", (m) => process.stderr.write(`[page ${m.type()}] ${m.text()}\n`));
page.on("pageerror", (e) => process.stderr.write(`[page error] ${e.stack || e}\n`));
await page.goto(origin + "/");
const version = await page.evaluate(async () => {
    const sdk = await import("/sdk/index.js");
    const { makeRunner } = await import("/ops.mjs");
    const runner = makeRunner(sdk);
    window.__otc = { runner, isNodeVisible: typeof process !== "undefined" };
    return sdk.VERSION;
});

out({ hello: { runner: "typescript-browser", version, origin, features: ["fetch", "json", "eager", "stream"] } });

const rl = createInterface({ input: process.stdin, crlfDelay: Infinity });
for await (const line of rl) {
    if (!line.trim()) continue;
    const msg = JSON.parse(line);
    out(await page.evaluate((m) => window.__otc.runner.handle(m), msg));
}
await page.evaluate(() => window.__otc.runner.shutdown()).catch(() => undefined);
await browser.close();
server.close();
process.exit(0);
