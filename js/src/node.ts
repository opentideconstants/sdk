/** @internal The Node runtime: file system, disk cache, HTTP with proxies (spec 5.4, 5.7). */
import { createHash, randomBytes } from "node:crypto";
import * as fs from "node:fs";
import * as fsp from "node:fs/promises";
import * as http from "node:http";
import * as https from "node:https";
import * as os from "node:os";
import * as path from "node:path";
import * as tls from "node:tls";
import * as zlib from "node:zlib";
import type { Duplex } from "node:stream";
import { MessageChannel, receiveMessageOnPort, Worker } from "node:worker_threads";
import { CACHE_LAYOUT_VERSION, SDK_ID } from "./constants.js";
import { CacheError, FileError, InvalidArgumentError, NetworkError } from "./errors.js";
import type { BlockingResult, NodeMod, NodePath } from "./node-api.js";
import type { CacheStore, HttpOptions, HttpResponse, LockOptions, Platform, Unlock } from "./platform.js";

export type { BlockingResult } from "./node-api.js";

export function sha256Sync(bytes: Uint8Array): string {
    return createHash("sha256").update(bytes).digest("hex");
}

export function gunzipSync(bytes: Uint8Array): Uint8Array {
    return zlib.gunzipSync(bytes);
}

function env(name: string): string | null {
    const v = process.env[name];
    return v === undefined || v === "" ? null : v;
}

function envAnyCase(name: string): string | null {
    return env(name.toUpperCase()) ?? env(name.toLowerCase());
}

/** The default cache root (spec 5.4). */
export function defaultCacheRoot(): string {
    if (process.platform === "darwin") return path.join(os.homedir(), "Library", "Caches", "opentideconstants");
    if (process.platform === "win32") {
        const base = env("LOCALAPPDATA") ?? path.join(os.homedir(), "AppData", "Local");
        return path.join(base, "opentideconstants", "Cache");
    }
    return path.join(env("XDG_CACHE_HOME") ?? path.join(os.homedir(), ".cache"), "opentideconstants");
}

function tmpName(dir: string): string {
    return path.join(dir, `.tmp-${process.pid}-${randomBytes(6).toString("hex")}`);
}

/** Write a file atomically: temporary file in the same directory, fsync, rename (spec 5.4). */
export function writeAtomicSync(file: string, bytes: Uint8Array): void {
    const tmp = tmpName(path.dirname(file));
    try {
        const fd = fs.openSync(tmp, "w", 0o644);
        try {
            // writeSync may write less than asked (PK10 T11): loop until every byte is written
            let done = 0;
            while (done < bytes.length) done += fs.writeSync(fd, bytes, done, bytes.length - done);
            fs.fsyncSync(fd);
        } finally {
            fs.closeSync(fd);
        }
        fs.renameSync(tmp, file);
    } catch (e) {
        try { fs.rmSync(tmp, { force: true }); } catch { /* best effort */ }
        throw e;
    }
}

export function readIfExists(file: string): Uint8Array | null {
    try {
        return fs.readFileSync(file);
    } catch (e) {
        if (isErrno(e, "ENOENT") || isErrno(e, "ENOTDIR")) return null;
        throw new FileError(`cannot read ${file}`, { path: file, cause: e });
    }
}

/** The size of a file, or null when it does not exist. Any other failure is io (PK10 T34). */
export function statSize(file: string): number | null {
    try {
        return fs.statSync(file).size;
    } catch (e) {
        if (isErrno(e, "ENOENT") || isErrno(e, "ENOTDIR")) return null;
        throw new FileError(`cannot read ${file}`, { path: file, cause: e });
    }
}

export function readFileOrIo(file: string): Uint8Array {
    try {
        return fs.readFileSync(file);
    } catch (e) {
        throw new FileError(`cannot read ${file}`, { path: file, cause: e });
    }
}

function isErrno(e: unknown, code: string): boolean {
    return typeof e === "object" && e !== null && (e as { code?: unknown }).code === code;
}

/** A positional line reader over an open file (stream mode, spec 6.2). */
export function openLineReader(file: string): { read: (offset: number, length: number) => Uint8Array; close: () => void } {
    let fd: number | null;
    try {
        fd = fs.openSync(file, "r");
    } catch (e) {
        throw new FileError(`cannot open ${file}`, { path: file, cause: e });
    }
    return {
        read(offset, length) {
            if (fd === null) throw new FileError(`${file} is closed`, { path: file });
            const buf = Buffer.alloc(length);
            let got = 0;
            while (got < length) {
                let n: number;
                try {
                    n = fs.readSync(fd, buf, got, length - got, offset + got);
                } catch (e) {
                    // EIO, EBADF, ESTALE...: a local read failure is io, never a raw Node error (R2-097)
                    throw new FileError(`cannot read ${file}`, { path: file, cause: e });
                }
                if (n === 0) break;
                got += n;
            }
            return buf.subarray(0, got);
        },
        close() {
            if (fd !== null) {
                try { fs.closeSync(fd); } catch { /* already closed */ }
                fd = null;
            }
        },
    };
}

/** How long a waiter waits before it treats a lock as stale (spec 5.4). */
const STALE_LOCK_MS = 120_000;

class NodeCache implements CacheStore {
    readonly base: string;

    constructor(root: string) {
        this.base = path.join(root, CACHE_LAYOUT_VERSION);
    }

    describe(rel: string): string {
        return path.join(this.base, rel);
    }

    async mkdirs(rel: string): Promise<void> {
        const p = this.describe(rel);
        try {
            await fsp.mkdir(p, { recursive: true });
        } catch (e) {
            throw new CacheError(`cannot create the cache directory ${p}`, { path: p, cause: e });
        }
    }

    async read(rel: string): Promise<Uint8Array | null> {
        return readIfExists(this.describe(rel));
    }

    async write(rel: string, bytes: Uint8Array): Promise<void> {
        const p = this.describe(rel);
        try {
            await fsp.mkdir(path.dirname(p), { recursive: true });
            writeAtomicSync(p, bytes);
        } catch (e) {
            throw new CacheError(`cannot write ${p}`, { path: p, cause: e });
        }
    }

    async remove(rel: string): Promise<void> {
        const p = this.describe(rel);
        try {
            await fsp.rm(p, { force: true });
        } catch (e) {
            throw new CacheError(`cannot remove ${p}`, { path: p, cause: e });
        }
    }

    async removeDir(rel: string): Promise<void> {
        const p = this.describe(rel);
        try {
            await fsp.rm(p, { recursive: true, force: true });
        } catch (e) {
            throw new CacheError(`cannot remove ${p}`, { path: p, cause: e });
        }
    }

    async list(rel: string): Promise<string[]> {
        const p = this.describe(rel);
        try {
            return await fsp.readdir(p);
        } catch (e) {
            if (isErrno(e, "ENOENT") || isErrno(e, "ENOTDIR")) return [];
            throw new CacheError(`cannot read the cache directory ${p}`, { path: p, cause: e });
        }
    }

    async lock(rel: string, options: LockOptions = {}): Promise<Unlock | null> {
        const dir = this.describe(rel);
        const lockDir = path.join(dir, ".lock");
        const ownerFile = path.join(lockDir, "owner.json");
        await this.mkdirs(rel);
        let started = Date.now();
        let failedSteals = 0;
        for (;;) {
            let made = false;
            try {
                await fsp.mkdir(lockDir);
                made = true;
            } catch (e) {
                if (!isErrno(e, "EEXIST")) throw new CacheError(`cannot take the lock ${lockDir}`, { path: lockDir, cause: e });
            }
            if (made) {
                // the token proves ownership at release (spec 5.4, CR D3)
                const token = randomBytes(16).toString("hex");
                const owner = JSON.stringify({ pid: process.pid, host: os.hostname(), sdk: SDK_ID, started_at: new Date().toISOString(), token });
                try {
                    writeAtomicSync(ownerFile, new TextEncoder().encode(owner));
                } catch (e) {
                    await fsp.rm(lockDir, { recursive: true, force: true }).catch(() => undefined);
                    throw new CacheError(`cannot write ${ownerFile}`, { path: ownerFile, cause: e });
                }
                return async () => {
                    let current: unknown = null;
                    try {
                        current = JSON.parse(await fsp.readFile(ownerFile, "utf8"));
                    } catch {
                        return; // gone or unreadable: another process took the lock as stale; leave it alone
                    }
                    if (typeof current !== "object" || current === null || (current as { token?: unknown }).token !== token) return;
                    try {
                        await fsp.rm(ownerFile, { force: true });
                        await fsp.rmdir(lockDir);
                    } catch (e) {
                        throw new CacheError(`cannot release the lock ${lockDir}`, { path: lockDir, cause: e });
                    }
                };
            }
            if (options.wait === false) return null;
            if (options.done && await options.done()) return async () => undefined;
            if (Date.now() - started > STALE_LOCK_MS) {
                // stale: remove it and take it; 3 failed removals raise cache (CR D3)
                try {
                    await fsp.rm(lockDir, { recursive: true, force: true });
                } catch { /* checked below */ }
                if (fs.existsSync(lockDir)) {
                    if (++failedSteals >= 3) throw new CacheError(`cannot remove the stale lock ${lockDir}`, { path: lockDir });
                } else {
                    started = Date.now();
                    continue;
                }
            }
            await new Promise((r) => setTimeout(r, 500));
        }
    }
}

/** @internal True when NO_PROXY names this host. */
export function noProxy(host: string): boolean {
    const np = envAnyCase("NO_PROXY");
    if (!np) return false;
    const h = host.toLowerCase().replace(/^\[|\]$/g, "");
    for (let rule of np.split(",").map((s) => s.trim().toLowerCase()).filter(Boolean)) {
        if (rule === "*") return true;
        // strip a port: "[::1]:8080" and "host:8080", but not the colons of a bare IPv6 address (PK12 T89)
        const bracketed = /^\[([^\]]+)\](?::\d+)?$/.exec(rule);
        if (bracketed && bracketed[1]) rule = bracketed[1];
        else if ((rule.match(/:/g) ?? []).length === 1) rule = rule.replace(/:\d+$/, "");
        if (rule.startsWith("*.")) rule = rule.slice(1);
        if (h === rule.replace(/^\./, "") || (rule.startsWith(".") ? h.endsWith(rule) : h.endsWith("." + rule))) return true;
    }
    return false;
}

/**
 * @internal An absolute http or https URL, or null when `v` is not one (CR D19). A proxy from the environment may
 * leave out the scheme (`host:3128`, as curl reads it); `bareHost` allows that.
 */
export function httpUrl(v: string, bareHost = false): URL | null {
    try {
        const u = new URL(bareHost && !v.includes("://") ? `http://${v}` : v);
        return (u.protocol === "http:" || u.protocol === "https:") && u.hostname !== "" ? u : null;
    } catch {
        return null;
    }
}

function proxyFor(target: URL, explicit: string | null): URL | null {
    if (explicit) {
        const u = httpUrl(explicit);
        if (!u) throw new InvalidArgumentError(`proxy must be an absolute http or https URL; got ${explicit}`);
        return u;
    }
    if (noProxy(target.hostname)) return null;
    const name = target.protocol === "https:" ? "HTTPS_PROXY" : "HTTP_PROXY";
    // httpoxy (CR D7): in a CGI process (REQUEST_METHOD set) HTTP_PROXY may come from a request header; use only
    // the lower-case http_proxy then
    const v = name === "HTTP_PROXY" && env("REQUEST_METHOD") !== null ? env("http_proxy") : envAnyCase(name);
    if (!v) return null;
    const u = httpUrl(v, true);
    if (!u) throw new InvalidArgumentError(`the ${name} environment variable is not a proxy URL: ${v}`);
    return u;
}

const REDIRECTS = new Set([301, 302, 303, 307, 308]);
const MAX_REDIRECTS = 5;

/**
 * One GET that follows up to 5 redirects (spec 5.7, CR D1). A 6th redirect, a redirect from https to http and a
 * redirect with no usable Location are network errors.
 */
async function nodeGet(url: string, o: HttpOptions): Promise<HttpResponse> {
    let current = url;
    for (let hop = 0; ; hop++) {
        const res = await nodeGetOnce(current, o);
        if (!REDIRECTS.has(res.status)) return res;
        const loc = res.header("location");
        let next: URL;
        try {
            if (!loc) throw new Error("no Location header");
            next = new URL(loc, current);
        } catch (e) {
            throw new NetworkError(`HTTP ${res.status} with no usable Location: ${current}`, { url: current, status: res.status, cause: e });
        }
        if (next.protocol !== "http:" && next.protocol !== "https:") {
            throw new NetworkError(`redirect to ${next.protocol} refused: ${current}`, { url: current, status: res.status });
        }
        if (new URL(current).protocol === "https:" && next.protocol === "http:") {
            throw new NetworkError(`redirect from https to http refused: ${current} -> ${next.href}`, { url: current, status: res.status });
        }
        if (hop + 1 > MAX_REDIRECTS) throw new NetworkError(`more than ${MAX_REDIRECTS} redirects: ${url}`, { url, status: res.status });
        current = next.href;
    }
}

/** Proxy-Authorization from the user and password of a proxy URL (percent-decoded), or none (PK12 T7). */
function proxyAuth(proxy: URL): Record<string, string> {
    if (!proxy.username && !proxy.password) return {};
    let cred: string;
    try {
        cred = `${decodeURIComponent(proxy.username)}:${decodeURIComponent(proxy.password)}`;
    } catch (e) {
        // a bad %-escape in the user or password: the proxy setting is wrong, never a raw URIError (R2-099)
        throw new InvalidArgumentError(`the proxy's user or password is not valid percent-encoding (${(e as Error).message})`);
    }
    return { "Proxy-Authorization": `Basic ${Buffer.from(cred, "utf8").toString("base64")}` };
}

function nodeGetOnce(url: string, o: HttpOptions): Promise<HttpResponse> {
    const target = new URL(url);
    const proxy = proxyFor(target, o.proxy);
    const connectMs = (o.timeout ?? 10) * 1000;
    const readMs = (o.timeout ?? 60) * 1000;
    const caPath = o.caFile ?? env("SSL_CERT_FILE");
    // a CA file that cannot be read is io, never a network error to retry (CR D19)
    const ca = caPath && target.protocol === "https:" ? Buffer.from(readFileOrIo(caPath)) : undefined;
    const fail = (message: string, cause?: unknown) => new NetworkError(`${message}: ${url}`, { url, cause });

    return new Promise<HttpResponse>((resolve, reject) => {
        let done = false;
        const finish = (err: Error | null, res?: HttpResponse) => {
            if (done) return;
            done = true;
            clearTimeout(connectTimer);
            if (err) reject(err);
            else resolve(res as HttpResponse);
        };
        const connectTimer = setTimeout(() => {
            req?.destroy();
            finish(fail("connect timeout"));
        }, connectMs);
        let req: http.ClientRequest | null = null;

        const onResponse = (res: http.IncomingMessage) => {
            clearTimeout(connectTimer);
            const chunks: Buffer[] = [];
            res.setTimeout(readMs, () => {
                res.destroy();
                finish(fail("read timeout"));
            });
            res.on("data", (c: Buffer) => chunks.push(c));
            res.on("aborted", () => finish(fail("the connection closed before the body was complete")));
            res.on("error", (e) => finish(fail("the response failed", e)));
            res.on("end", () => {
                if (!res.complete) return finish(fail("the connection closed before the body was complete"));
                let body: Uint8Array = Buffer.concat(chunks);
                const enc = (res.headers["content-encoding"] ?? "").toLowerCase();
                // a .gz file sent with Content-Encoding: gzip (some CDNs) is the file itself: keep the bytes (T10)
                if ((enc === "gzip" || enc === "x-gzip") && !target.pathname.endsWith(".gz")) {
                    try {
                        body = zlib.gunzipSync(body);
                    } catch (e) {
                        return finish(fail("the gzip body is broken", e));
                    }
                }
                const headers = res.headers;
                finish(null, {
                    status: res.statusCode ?? 0,
                    header: (n) => {
                        const v = headers[n.toLowerCase()];
                        return v === undefined ? null : Array.isArray(v) ? v.join(", ") : v;
                    },
                    body,
                });
            });
        };
        const onError = (e: Error) => finish(fail("request failed", e));

        const mod = target.protocol === "https:" ? https : http;
        if (!proxy) {
            req = mod.get(target, { headers: o.headers, ca }, onResponse);
        } else if (target.protocol === "http:") {
            // an https:// proxy is reached over TLS; an http:// one in the clear (PK12 T7)
            const pmod = proxy.protocol === "https:" ? https : http;
            req = pmod.get({
                host: proxy.hostname, port: proxy.port || (proxy.protocol === "https:" ? 443 : 80), path: target.href,
                headers: { ...o.headers, Host: target.host, ...proxyAuth(proxy) }, ca,
            }, onResponse);
        } else {
            const pmod = proxy.protocol === "https:" ? https : http;
            const c = pmod.request({
                host: proxy.hostname, port: proxy.port || (proxy.protocol === "https:" ? 443 : 80), method: "CONNECT",
                path: `${target.hostname}:${target.port || 443}`, ca,
                headers: { Host: `${target.hostname}:${target.port || 443}`, ...proxyAuth(proxy) },
            });
            req = c;
            c.on("connect", (res: http.IncomingMessage, socket: Duplex) => {
                if (res.statusCode !== 200) {
                    socket.destroy();
                    return finish(new NetworkError(`the proxy refused CONNECT (${res.statusCode}): ${url}`, { url, status: res.statusCode ?? null }));
                }
                req = https.get(target, {
                    headers: o.headers,
                    createConnection: () => tls.connect({ socket, servername: target.hostname, ca }),
                } as https.RequestOptions, onResponse);
                req.on("error", onError);
            });
            c.end();
        }
        req.on("error", onError);
    });
}

export function nodePlatform(): Platform {
    return {
        name: "node",
        sha256: async (b) => sha256Sync(b),
        gunzip: async (b) => gunzipSync(b),
        get: nodeGet,
        cache: async (root) => new NodeCache(root ?? defaultCacheRoot()),
        env,
        sleep: (s) => new Promise((r) => setTimeout(r, s * 1000)),
    };
}

// ------------------------------------------------------------------ files outside the cache

export const nodePath: NodePath = path;

export function exists(p: string): boolean {
    return fs.existsSync(p);
}

export function mkdirp(dir: string): void {
    try {
        fs.mkdirSync(dir, { recursive: true });
    } catch (e) {
        throw new FileError(`cannot create ${dir}`, { path: dir, cause: e });
    }
}

/** The names in a cache directory, or [] when it does not exist. Any other failure is cache (PK10 T34). */
export function listDir(dir: string): string[] {
    try {
        return fs.readdirSync(dir);
    } catch (e) {
        if (isErrno(e, "ENOENT") || isErrno(e, "ENOTDIR")) return [];
        throw new CacheError(`cannot read the cache directory ${dir}`, { path: dir, cause: e });
    }
}

/** Throws io unless the file can be read (a ca_file, spec 4.2, CR D19). */
export function checkReadable(file: string): void {
    try {
        fs.accessSync(file, fs.constants.R_OK);
        if (!fs.statSync(file).isFile()) throw new Error("not a file");
    } catch (e) {
        throw new FileError(`cannot read ${file}`, { path: file, cause: e });
    }
}

export function removeFileSync(file: string): void {
    fs.rmSync(file, { force: true });
}

/** Remove a directory tree; throws when any of it is left (rmSync can report success on a read-only tree). */
export function removeDirSync(dir: string): void {
    fs.rmSync(dir, { recursive: true, force: true });
    if (fs.existsSync(dir)) throw new Error(`${dir} is still there after the removal`);
}

/** Write into a caller's folder: temporary file, fsync, rename (spec 4.3.2). */
export function writeInto(dir: string, name: string, bytes: Uint8Array): string {
    const p = path.join(dir, name);
    try {
        writeAtomicSync(p, bytes);
    } catch (e) {
        throw new FileError(`cannot write ${p}`, { path: p, cause: e });
    }
    return p;
}

// ------------------------------------------------------------------ blocking helper for autoUpdate (spec 5.6)

/**
 * Run a worker module and block until it answers. The query that triggers an automatic update must
 * already see the new release (spec 5.6), and JavaScript queries are synchronous, so the check runs
 * to completion in a short-lived worker thread while the calling thread waits. (Spec 5.6 says "no thread";
 * a blocking check is not possible in JavaScript without one, so this is the TypeScript deviation.)
 *
 * The worker is started through a bootstrap that always posts an answer and wakes the caller, also when the
 * module fails to load or throws outside its own try (PK13 T1), so the wait ends when the worker ends, not after
 * the timeout. The worker is terminated after the wait; a lock it held is then stale and taken over (spec 5.4).
 */
export function runBlocking(url: URL, data: unknown, timeoutMs = 600_000): BlockingResult {
    const sab = new SharedArrayBuffer(4);
    const flag = new Int32Array(sab);
    const { port1, port2 } = new MessageChannel();
    const boot = `
const { workerData } = require("node:worker_threads");
const { port, sab, url } = workerData;
const flag = new Int32Array(sab);
import(url).catch((e) => {
    // the module failed to load, or failed after it ran (for example a DataCloneError when it posted its result):
    // say what failed, and send the error itself as the cause (CR2 DR5, R2-109)
    const name = e && e.name ? e.name : "Error";
    const message = e && e.message ? e.message : String(e);
    port.postMessage({ ok: false, message: "the update check failed: " + name + ": " + message,
                       cause: { name, message, stack: e && e.stack ? String(e.stack) : undefined } });
}).finally(() => {
    Atomics.store(flag, 0, 1);
    Atomics.notify(flag, 0);
});`;
    const w = new Worker(boot, { eval: true, workerData: { port: port2, sab, data, url: url.href }, transferList: [port2] });
    // an error event after the wait must not become an uncaught exception in the host (PK13 T1)
    w.on("error", () => undefined);
    try {
        Atomics.wait(flag, 0, 0, timeoutMs);
        const msg = receiveMessageOnPort(port1);
        if (!msg) return { ok: false, message: "the update check did not finish" };
        return msg.message as BlockingResult;
    } finally {
        port1.close();
        void w.terminate();
    }
}

/** @internal What client.ts uses, through "#node" (node-api.ts, CR T64). */
export const nodeApi: NodeMod = {
    nodePlatform, nodePath, sha256Sync, gunzipSync, defaultCacheRoot, writeAtomicSync, readIfExists, statSize, readFileOrIo,
    openLineReader, exists, mkdirp, listDir, checkReadable, removeFileSync, removeDirSync, writeInto, runBlocking,
};
