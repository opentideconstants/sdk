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
import { CacheError, FileError, NetworkError } from "./errors.js";
import type { CacheStore, HttpOptions, HttpResponse, Platform } from "./platform.js";

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
            fs.writeSync(fd, bytes);
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

export function statSize(file: string): number | null {
    try {
        return fs.statSync(file).size;
    } catch {
        return null;
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
                const n = fs.readSync(fd, buf, got, length - got, offset + got);
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
        await fsp.rm(this.describe(rel), { force: true });
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
        try {
            return await fsp.readdir(this.describe(rel));
        } catch {
            return [];
        }
    }

    async lock(rel: string): Promise<() => Promise<void>> {
        const dir = this.describe(rel);
        const lockDir = path.join(dir, ".lock");
        await this.mkdirs(rel);
        const started = Date.now();
        for (;;) {
            try {
                await fsp.mkdir(lockDir);
                const owner = JSON.stringify({ pid: process.pid, host: os.hostname(), sdk: SDK_ID, started_at: new Date().toISOString() });
                await fsp.writeFile(path.join(lockDir, "owner.json"), owner).catch(() => undefined);
                return async () => {
                    await fsp.rm(path.join(lockDir, "owner.json"), { force: true }).catch(() => undefined);
                    await fsp.rmdir(lockDir).catch(() => undefined);
                };
            } catch (e) {
                if (!isErrno(e, "EEXIST")) throw new CacheError(`cannot take the lock ${lockDir}`, { path: lockDir, cause: e });
            }
            if (fs.existsSync(path.join(dir, ".verified"))) return async () => undefined;
            if (Date.now() - started > 120_000) {
                await fsp.rm(lockDir, { recursive: true, force: true }).catch(() => undefined);
                continue;
            }
            await new Promise((r) => setTimeout(r, 500));
        }
    }
}

function noProxy(host: string): boolean {
    const np = envAnyCase("NO_PROXY");
    if (!np) return false;
    const h = host.toLowerCase().replace(/^\[|\]$/g, "");
    for (let rule of np.split(",").map((s) => s.trim().toLowerCase()).filter(Boolean)) {
        if (rule === "*") return true;
        rule = rule.replace(/:\d+$/, "");
        if (rule.startsWith("*.")) rule = rule.slice(1);
        if (h === rule.replace(/^\./, "") || (rule.startsWith(".") ? h.endsWith(rule) : h.endsWith("." + rule))) return true;
    }
    return false;
}

function proxyFor(target: URL, explicit: string | null): URL | null {
    if (explicit) return new URL(explicit);
    if (noProxy(target.hostname)) return null;
    const v = target.protocol === "https:" ? envAnyCase("HTTPS_PROXY") : envAnyCase("HTTP_PROXY");
    return v ? new URL(v.includes("://") ? v : `http://${v}`) : null;
}

function nodeGet(url: string, o: HttpOptions): Promise<HttpResponse> {
    const target = new URL(url);
    const proxy = proxyFor(target, o.proxy);
    const connectMs = (o.timeout ?? 10) * 1000;
    const readMs = (o.timeout ?? 60) * 1000;
    const caPath = o.caFile ?? env("SSL_CERT_FILE");
    const ca = caPath && target.protocol === "https:" ? fs.readFileSync(caPath) : undefined;
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
                if (enc === "gzip" || enc === "x-gzip") {
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
            req = http.get({
                host: proxy.hostname, port: proxy.port || 80, path: target.href,
                headers: { ...o.headers, Host: target.host },
            }, onResponse);
        } else {
            const c = http.request({ host: proxy.hostname, port: proxy.port || 80, method: "CONNECT", path: `${target.hostname}:${target.port || 443}`, headers: { Host: `${target.hostname}:${target.port || 443}` } });
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

export const nodePath = path;

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

export function listDir(dir: string): string[] {
    try {
        return fs.readdirSync(dir);
    } catch {
        return [];
    }
}

export function removeDirSync(dir: string): void {
    fs.rmSync(dir, { recursive: true, force: true });
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

export interface BlockingResult {
    ok: boolean;
    datestamp?: string;
    how?: string;
    message?: string;
}

/**
 * Run a worker module and block until it answers. The query that triggers an automatic update must
 * already see the new release (spec 5.6), and JavaScript queries are synchronous, so the check runs
 * to completion in a short-lived worker while the calling thread waits. No thread outlives the call.
 */
export function runBlocking(url: URL, data: unknown, timeoutMs = 600_000): BlockingResult {
    const sab = new SharedArrayBuffer(4);
    const flag = new Int32Array(sab);
    const { port1, port2 } = new MessageChannel();
    const w = new Worker(url, { workerData: { port: port2, sab, data }, transferList: [port2] });
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
