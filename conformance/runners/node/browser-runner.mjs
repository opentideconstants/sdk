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
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const jsDir = path.resolve(here, "..", "..", "..", "js");
// OTC_BROWSER_SDK_DIR serves another build of the SDK (the self-tests use a fake one); default js/dist.
const distDir = process.env.OTC_BROWSER_SDK_DIR ? path.resolve(process.env.OTC_BROWSER_SDK_DIR) : path.join(jsDir, "dist");
// The driver points HOME at a temporary directory; find Playwright's browsers under the real home.
if (!process.env.PLAYWRIGHT_BROWSERS_PATH) {
    const home = os.userInfo().homedir;
    process.env.PLAYWRIGHT_BROWSERS_PATH = process.platform === "darwin" ? path.join(home, "Library", "Caches", "ms-playwright")
        : process.platform === "win32" ? path.join(home, "AppData", "Local", "ms-playwright") : path.join(home, ".cache", "ms-playwright");
}
const require = createRequire(path.join(jsDir, "package.json"));

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

// A start-up failure fails the handshake: no hello, a line on stderr that says what to do, and exit 3 (as in
// runner.mjs), never an unhandled rejection with exit 1.
let browser = null;
let server = null;
async function failStart(what, e, hint) {
    const detail = e === undefined ? "" : `: ${e && e.stack ? e.stack : e}`;
    process.stderr.write(`cannot start the browser runner: ${what}${detail}${hint ? `\n${hint}` : ""}\n`);
    if (browser) await browser.close().catch(() => {});
    if (server) server.close();
    process.exit(3);
}

let chromium;
try {
    ({ chromium } = require("playwright"));
} catch (e) {
    await failStart("cannot load Playwright", e, "Install the devDependencies: cd js && npm ci");
}
server = await serve();
const origin = `http://127.0.0.1:${server.address().port}`;
try {
    browser = await chromium.launch({ headless: true });
} catch (e) {
    await failStart("cannot launch Chromium", e, "Install it: cd js && npx playwright install chromium");
}
let page;
// An error that escapes in the page (outside the op's promise) fails the step it happened in, or the next one.
const pageErrors = [];
try {
    const context = await browser.newContext();
    page = await context.newPage();
    page.on("console", (m) => process.stderr.write(`[page ${m.type()}] ${m.text()}\n`));
    page.on("pageerror", (e) => {
        process.stderr.write(`[page error] ${e.stack || e}\n`);
        pageErrors.push(String(e && e.stack ? e.stack : e));
    });
    await page.goto(origin + "/");
} catch (e) {
    await failStart(`cannot open the page ${origin}/`, e);
}
// let the page run what an evaluate left pending (timers, rejected promises), so escaped errors are seen
const settle = () => page.evaluate(() => new Promise((r) => setTimeout(() => setTimeout(r, 0), 0)));
let loaded;
try {
    loaded = await page.evaluate(async () => {
        const sdk = await import("/sdk/index.js");
        const { makeRunner } = await import("/ops.mjs");
        if (typeof sdk.OpenTideConstantsError !== "function" || typeof sdk.VERSION !== "string") return null;
        window.__otc = { runner: makeRunner(sdk) };
        // D28: the browser profile must not test a Node-like environment, so a page that can see process fails
        return { version: sdk.VERSION, isNodeVisible: typeof process !== "undefined" };
    });
    await settle();
} catch (e) {
    await failStart(`cannot load the SDK from ${distDir} or ops.mjs in the page`, e, "Build the SDK first: cd js && npm run build");
}
if (loaded === null) {   // no error base class or no version: fail the handshake (exit 3)
    await failStart("cannot load the SDK: it has no OpenTideConstantsError class or no VERSION string");
}
if (pageErrors.length) {   // an error that escaped while the SDK loaded belongs to the handshake, not to step 1
    await failStart("an error escaped in the page while the SDK loaded", pageErrors.splice(0).join("\n"));
}
if (loaded.isNodeVisible) {
    await failStart("the page can see process, so it is not a browser environment (CR D28)");
}
const version = loaded.version;

out({ hello: { runner: "typescript-browser", version, origin, features: ["fetch", "json", "eager", "stream"] } });

let pageGone = null;
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
    if (pageGone) {   // the page and its state are gone: every later step fails too, and the exit status is 1
        out({ ok: false, error: { code: "uncaught:PageGone", message: `the page is gone: ${pageGone}` } });
        continue;
    }
    let reply;
    try {
        reply = await page.evaluate((m) => window.__otc.runner.handle(m), msg);
        // let the page run what the op left pending (timers, rejected promises), then look for escaped errors
        await settle();
    } catch (e) {   // the page crashed or navigated, or the reply could not be passed back: the step fails
        process.stderr.write(`page.evaluate failed: ${e && e.stack ? e.stack : e}\n`);
        pageGone = String(e && e.message ? e.message : e).slice(0, 2000);
        reply = { ok: false, error: { code: `uncaught:${e && e.constructor ? e.constructor.name : typeof e}`, message: pageGone } };
    }
    if (pageErrors.length) {
        reply = { ok: false, error: { code: "uncaught:PageError", message: pageErrors.splice(0).join("\n").slice(0, 2000) } };
    }
    out(reply);
}
const closed = !pageGone && await page.evaluate(() => window.__otc.runner.shutdown()).catch((e) => {
    process.stderr.write(`close failed at shutdown: ${e && e.stack ? e.stack : e}\n`);
    return false;
});
await browser.close();
server.close();
process.exit(closed ? 0 : 1);
