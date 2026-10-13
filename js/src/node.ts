/** @internal The Node runtime: file system, disk cache, HTTP with proxies (spec 5.4, 5.7). */
import { createHash, randomBytes } from "node:crypto";
import * as fs from "node:fs";
import * as fsp from "node:fs/promises";
import * as http from "node:http";
import * as https from "node:https";
import * as net from "node:net";
import * as os from "node:os";
import * as path from "node:path";
import * as tls from "node:tls";
import * as zlib from "node:zlib";
import type { Duplex } from "node:stream";
import { MessageChannel, receiveMessageOnPort, Worker } from "node:worker_threads";
import { CACHE_LAYOUT_VERSION, SDK_ID } from "./constants.js";
import { CacheError, FileError, InvalidArgumentError, NetworkError, redactUrl } from "./errors.js";
import type { BlockingResult, NodeMod, NodePath } from "./node-api.js";
import type { CacheStore, HttpOptions, HttpResponse, LockOptions, Platform, Unlock } from "./platform.js";

export type { BlockingResult } from "./node-api.js";

export function sha256Sync(bytes: Uint8Array): string {
    return createHash("sha256").update(bytes).digest("hex");
}

function createSha256State(): { update(bytes: Uint8Array): void; digest(): string } {
    const hash = createHash("sha256");
    return { update: (bytes) => { hash.update(bytes); }, digest: () => hash.digest("hex") };
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

/** Write a new file and fsync it. */
function writeFsyncSync(file: string, bytes: Uint8Array): void {
    const fd = fs.openSync(file, "w", 0o644);
    try {
        // writeSync may write less than asked (PK10 T11): loop until every byte is written
        let done = 0;
        while (done < bytes.length) done += fs.writeSync(fd, bytes, done, bytes.length - done);
        fs.fsyncSync(fd);
    } finally {
        fs.closeSync(fd);
    }
}

/** Write a file atomically: temporary file in the same directory, fsync, rename (spec 5.4). */
export function writeAtomicSync(file: string, bytes: Uint8Array): void {
    const tmp = tmpName(path.dirname(file));
    try {
        writeFsyncSync(tmp, bytes);
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
export function openLineReader(file: string): { read: (offset: number, length: number) => Uint8Array; close: () => void; closeStrict: () => void } {
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
        closeStrict() {
            if (fd !== null) {
                try { fs.closeSync(fd); }
                finally { fd = null; }
            }
        },
    };
}

/**
 * @internal The lock times of spec 5.4: how long a waiter waits before a lock may be stale, how old the lock itself
 * must be to be stale (CR2 DR3), and the poll interval. The unit tests shorten the wait.
 */
export const lockTimers = { staleMs: 120_000, staleAgeMs: 120_000, pollMs: 500 };

const STARTED_AT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|\+00:00)$/;

/**
 * @internal Milliseconds since the lock was taken (spec 5.4, CR2 DR3): from owner.json `started_at`, or from the
 * mtime of the lock directory when owner.json is missing or cannot be read. null when the lock is gone or its age
 * cannot be read: such a lock is never stale.
 */
export function lockAgeMs(lockDir: string): number | null {
    let started: number | null = null;
    try {
        const owner: unknown = JSON.parse(fs.readFileSync(path.join(lockDir, "owner.json"), "utf8"));
        const at = typeof owner === "object" && owner !== null ? (owner as { started_at?: unknown }).started_at : undefined;
        const t = typeof at === "string" && STARTED_AT.test(at) ? Date.parse(at) : NaN;
        if (Number.isFinite(t)) started = t;
    } catch { /* missing or unreadable: the mtime below */ }
    if (started === null) {
        try {
            started = fs.statSync(lockDir).mtimeMs;
        } catch {
            return null;
        }
    }
    return Date.now() - started;
}

function lockIsStale(lockDir: string): boolean {
    const age = lockAgeMs(lockDir);
    return age !== null && age >= lockTimers.staleAgeMs;
}

/**
 * @internal Take `<dir>/.lock` without waiting, for prune, which then removes the directory with its lock (spec 5.4
 * non-blocking takes, CR2 DR3). A lock at least 120 s old is stale: it is removed and taken. False when another
 * process holds a younger lock. A stale lock that cannot be removed is a CacheError.
 */
export function tryLockSync(dir: string): boolean {
    const lockDir = path.join(dir, ".lock");
    for (let attempt = 0; attempt < 2; attempt++) {
        try {
            fs.mkdirSync(lockDir);
            return true;
        } catch (e) {
            if (!isErrno(e, "EEXIST")) throw new CacheError(`cannot take the lock ${lockDir}`, { path: lockDir, cause: e });
        }
        // once only: a process that takes it after the removal holds a young lock
        if (attempt > 0 || !lockIsStale(lockDir)) return false;
        try {
            fs.rmSync(lockDir, { recursive: true, force: true });
        } catch (e) {
            throw new CacheError(`cannot remove the stale lock ${lockDir}`, { path: lockDir, cause: e });
        }
    }
    return false;
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
        // a cache file that is there but cannot be read is cache, never absent and not io (spec 5.2 step 6, R2-092)
        const p = this.describe(rel);
        try {
            return fs.readFileSync(p);
        } catch (e) {
            if (isErrno(e, "ENOENT") || isErrno(e, "ENOTDIR")) return null;
            throw new CacheError(`cannot read ${p}`, { path: p, cause: e });
        }
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
        let stolen = false;
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
                const owner = JSON.stringify({ pid: process.pid, host: os.hostname(), sdk: SDK_ID,
                    started_at: new Date().toISOString().replace(/\.\d{3}Z$/, "Z"), token });
                try {
                    writeAtomicSync(ownerFile, new TextEncoder().encode(owner));
                } catch (e) {
                    await fsp.rm(lockDir, { recursive: true, force: true }).catch(() => undefined);
                    throw new CacheError(`cannot write ${ownerFile}`, { path: ownerFile, cause: e });
                }
                let lost = false;
                const owns = async (): Promise<boolean> => {
                    if (lost) return false;
                    let current: unknown = null;
                    try {
                        current = JSON.parse(await fsp.readFile(ownerFile, "utf8"));
                    } catch {
                        return false; // gone or unreadable: another process took the lock as stale; leave it alone
                    }
                    return typeof current === "object" && current !== null && (current as { token?: unknown }).token === token;
                };
                let stopped = false;
                let refreshing: Promise<void> | undefined;
                const warn = (message: string): void => {
                    try { options.warn?.(message); } catch { /* a logger must not break the SDK */ }
                };
                const refresh = async (): Promise<void> => {
                    let current: unknown;
                    try {
                        current = JSON.parse(await fsp.readFile(ownerFile, "utf8"));
                    } catch (e) {
                        if (!isErrno(e, "ENOENT") && !isErrno(e, "ENOTDIR")) {
                            warn(`cannot refresh the lock ${lockDir}: ${e instanceof Error ? e.message : String(e)}`);
                            return;
                        }
                    }
                    if (stopped) return;
                    if (typeof current !== "object" || current === null || (current as { token?: unknown }).token !== token) {
                        lost = true;
                        stopped = true;
                        clearInterval(heartbeat);
                        warn(`the lock ${lockDir} is now held by another process; leaving it`);
                        return;
                    }
                    const now = new Date();
                    try {
                        writeAtomicSync(ownerFile, new TextEncoder().encode(JSON.stringify({ ...current,
                            started_at: now.toISOString().replace(/\.\d{3}Z$/, "Z") })));
                    } catch (e) {
                        warn(`cannot refresh ${ownerFile}: ${e instanceof Error ? e.message : String(e)}`);
                    }
                    // A failed owner rewrite still touches the directory; the next tick retries the rewrite.
                    try {
                        await fsp.utimes(lockDir, now, now);
                    } catch (e) {
                        warn(`cannot touch the lock ${lockDir}: ${e instanceof Error ? e.message : String(e)}`);
                    }
                };
                const heartbeat = setInterval(() => {
                    if (!stopped && !refreshing) refreshing = refresh().finally(() => { refreshing = undefined; });
                }, 30_000);
                heartbeat.unref();
                const unlock: Unlock = async () => {
                    stopped = true;
                    clearInterval(heartbeat);
                    await refreshing;
                    if (!await owns()) return;
                    try {
                        await fsp.rm(ownerFile, { force: true });
                        await fsp.rmdir(lockDir);
                    } catch (e) {
                        throw new CacheError(`cannot release the lock ${lockDir}`, { path: lockDir, cause: e });
                    }
                };
                unlock.owns = owns;
                return unlock;
            }
            // a non-blocking take (the DOI note) applies only the age test, and tries once more after a removal
            if (options.wait === false && (stolen || !lockIsStale(lockDir))) return null;
            if (options.wait !== false && options.done && await options.done()) return async () => undefined;
            // stale only when this waiter has waited and the lock itself is old; the age is read just before the
            // removal (spec 5.4, CR2 DR3)
            if ((options.wait === false || Date.now() - started > lockTimers.staleMs) && lockIsStale(lockDir)) {
                // stale: remove it and take it; 3 failed removals raise cache (CR D3); after a removal the wait restarts
                let removed = true;
                try {
                    await fsp.rm(lockDir, { recursive: true, force: true });
                } catch {
                    removed = false;
                }
                if (removed) {
                    started = Date.now();
                    stolen = true;
                    continue;
                }
                if (++failedSteals >= 3 || options.wait === false) throw new CacheError(`cannot remove the stale lock ${lockDir}`, { path: lockDir });
            }
            await new Promise((r) => setTimeout(r, lockTimers.pollMs));
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
        if (!u) throw new InvalidArgumentError(`proxy must be an absolute http or https URL; got ${redactUrl(explicit)}`);
        return u;
    }
    if (noProxy(target.hostname)) return null;
    const name = target.protocol === "https:" ? "HTTPS_PROXY" : "HTTP_PROXY";
    // httpoxy (CR D7): in a CGI process (REQUEST_METHOD set) HTTP_PROXY may come from a request header; use only
    // the lower-case http_proxy then
    const v = name === "HTTP_PROXY" && env("REQUEST_METHOD") !== null ? env("http_proxy") : envAnyCase(name);
    if (!v) return null;
    const u = httpUrl(v, true);
    if (!u) throw new InvalidArgumentError(`the ${name} environment variable is not a proxy URL: ${redactUrl(v)}`);
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
    // decided by the URL asked for, not the redirect hop: a CDN may send the .gz from a URL with no suffix (CR2 R2-118)
    const keepGz = new URL(url).pathname.endsWith(".gz");
    for (let hop = 0; ; hop++) {
        const res = await nodeGetOnce(current, o, keepGz);
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

let extraCaCerts: readonly string[] | null = null;

/**
 * The CA certificates Node trusts by default: its root store plus NODE_EXTRA_CA_CERTS. Node 23.5+ and 22.15+ give
 * them with tls.getCACertificates("default"). Older Node (22.12) has only tls.rootCertificates, which leaves out
 * NODE_EXTRA_CA_CERTS, so the SDK adds that file itself (CR2 R2-117). Node reads the variable once at start-up and
 * only warns when the file cannot be read, so the SDK reads it once too and skips a file it cannot read.
 */
function defaultCaCerts(): readonly string[] {
    if (typeof tls.getCACertificates === "function") return tls.getCACertificates("default");
    if (extraCaCerts === null) {
        const file = process.env.NODE_EXTRA_CA_CERTS;
        let extra: string[] = [];
        if (file) {
            try {
                extra = [fs.readFileSync(file, "latin1")];
            } catch {
                extra = [];
            }
        }
        extraCaCerts = extra;
    }
    return [...tls.rootCertificates, ...extraCaCerts];
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

function nodeGetOnce(url: string, o: HttpOptions, keepGz: boolean): Promise<HttpResponse> {
    const target = new URL(url);
    const proxy = proxyFor(target, o.proxy);
    const connectMs = (o.timeout ?? 10) * 1000;
    const readMs = (o.timeout ?? 60) * 1000;
    const caPath = o.caFile ?? env("SSL_CERT_FILE");
    // a CA file that cannot be read is io, never a network error to retry (CR D19)
    const caPem = caPath && (target.protocol === "https:" || proxy?.protocol === "https:") ? Buffer.from(readFileOrIo(caPath)) : undefined;
    // the target is verified against caFile alone, as libcurl's CAINFO does
    const ca = target.protocol === "https:" ? caPem : undefined;
    // an https proxy against the default roots plus caFile: a caFile meant for the target must not drop the roots
    // the proxy's certificate chains to, and a private-CA proxy is trusted for http targets too (CR2 R2-117)
    const proxyCa = caPem ? [...defaultCaCerts(), caPem] : undefined;
    // and against its own name: without servername, Node takes the name from the Host header, the target's.
    // An IP gets "" (no SNI; the certificate is then checked against the IP).
    const proxyHost = proxy ? proxy.hostname.replace(/^\[|\]$/g, "") : "";
    const proxyName = net.isIP(proxyHost) ? "" : proxyHost;
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
                if ((enc === "gzip" || enc === "x-gzip") && !keepGz) {
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
                headers: { ...o.headers, Host: target.host, ...proxyAuth(proxy) }, ca: proxyCa, servername: proxyName,
            }, onResponse);
        } else {
            const pmod = proxy.protocol === "https:" ? https : http;
            const c = pmod.request({
                host: proxy.hostname, port: proxy.port || (proxy.protocol === "https:" ? 443 : 80), method: "CONNECT",
                path: `${target.hostname}:${target.port || 443}`, ca: proxyCa, servername: proxyName,
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

/**
 * Write files into a caller's folder, all or nothing (spec 4.3.2, CR2 DR17). Each file goes to a temporary file in
 * `dir` (fsynced); only when all of them are there are they renamed into place, in the order given. Each original that
 * a new file replaces is first renamed aside to a `.tmp-bak-` name in `dir`. If any rename fails, every original is
 * restored and the new files renamed in are removed, so `dir` is as it was: FileError. If a restore fails too, the
 * error lists the paths that changed. Returns the paths written.
 */
export function writeAllInto(dir: string, files: readonly (readonly [string, Uint8Array])[], warn: (message: string) => void): string[] {
    const staged: [string, string][] = [];
    try {
        for (const [name, bytes] of files) {
            const dest = path.join(dir, name);
            const tmp = tmpName(dir);
            staged.push([tmp, dest]);
            try {
                writeFsyncSync(tmp, bytes);
            } catch (e) {
                throw new FileError(`cannot write ${dest}`, { path: dest, cause: e });
            }
        }
        renameAllIn(staged, warn);
        const written = staged.map(([, dest]) => dest);
        staged.length = 0;
        return written;
    } finally {
        for (const [tmp] of staged) {
            try { fs.rmSync(tmp, { force: true }); } catch { /* best effort */ }
        }
    }
}

function renameAllIn(staged: readonly (readonly [string, string])[], warn: (message: string) => void): void {
    const aside = new Map<string, string>(); // destination -> its original, renamed aside
    const placed: string[] = []; // destinations a new file was renamed into
    let dest = "";
    const why = (e: unknown) => (e instanceof Error ? e.message : String(e));
    try {
        for (const [, d] of staged) {
            dest = d;
            let st: fs.Stats | null = null;
            try {
                st = fs.lstatSync(d);
            } catch (e) {
                if (!isErrno(e, "ENOENT")) throw e;
            }
            if (st && !st.isDirectory()) {
                const bak = path.join(path.dirname(d), `.tmp-bak-${process.pid}-${randomBytes(6).toString("hex")}`);
                fs.renameSync(d, bak);
                aside.set(d, bak);
            }
        }
        for (const [tmp, d] of staged) {
            dest = d;
            fs.renameSync(tmp, d);
            placed.push(d);
        }
    } catch (e) {
        const changed: string[] = [];
        for (const p of [...placed].reverse()) {
            try {
                const bak = aside.get(p);
                if (bak === undefined) fs.unlinkSync(p);
                else {
                    fs.renameSync(bak, p);
                    aside.delete(p);
                }
            } catch (x) {
                warn(`download: cannot restore ${p}: ${why(x)}`);
                changed.push(p);
            }
        }
        for (const [p, bak] of aside) {
            if (changed.includes(p)) continue;
            try {
                fs.renameSync(bak, p);
            } catch (x) {
                warn(`download: cannot restore ${p} from ${bak}: ${why(x)}`);
                changed.push(p);
            }
        }
        const more = changed.length === 0 ? ""
            : `; these paths changed and could not be restored: ${changed.join(", ")} (an original that is not back is in a .tmp-bak- file next to it)`;
        throw new FileError(`cannot write ${dest}${more}`, { path: dest, cause: e });
    }
    for (const [p, bak] of aside) {
        try {
            fs.rmSync(bak, { force: true });
        } catch (x) { // the new file is in place; only the old copy is left over
            warn(`download: cannot remove ${bak} (the replaced ${p}): ${why(x)}`);
        }
    }
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
    nodePlatform, nodePath, sha256Sync, createSha256State, gunzipSync, defaultCacheRoot, writeAtomicSync, readIfExists, statSize, readFileOrIo,
    openLineReader, exists, mkdirp, listDir, checkReadable, removeFileSync, removeDirSync, tryLockSync, writeAllInto, runBlocking,
};
