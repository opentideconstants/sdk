/** @internal The network and cache flows (spec 5.2 to 5.4), shared by the client and the auto-update worker. */
import { compareDatestamps, SDK_ID, supportedFormat, SUPPORTED_FORMAT_MAJORS } from "./constants.js";
import {
    ChecksumError, InvalidReleaseError, NetworkError, OfflineError, ReleaseNotFoundError, UnsupportedFormatError,
} from "./errors.js";
import { isObject } from "./json.js";
import {
    headerFromMeta, indexJsonl, parseJson, parseSha256, releaseFromJson, releaseFromJsonl, type LineReader, type StreamIndex,
} from "./loader.js";
import type { CacheStore, HttpResponse, Platform } from "./platform.js";
import { storedIndex, usableIndex, type Release } from "./release.js";
import type { FileInfo, Logger, Mode, OnNetworkError } from "./types.js";

export interface Ctx {
    platform: Platform;
    store: CacheStore | null;
    baseUrl: string;
    offline: boolean;
    timeout: number | null;
    proxy: string | null;
    caFile: string | null;
    userAgent: string;
    onNetworkError: OnNetworkError;
    logger: Logger | null;
    mode: Mode;
}

/** A latest-pointer or index entry, with absolute file URLs. */
export interface PointerEntry {
    datestamp: string;
    format_version: string;
    doi: string | null;
    files: FileInfo[];
}

/** The `.verified` record of a cached release (spec 5.4). */
export interface Verified {
    files: Record<string, { sha256: string | null; size: number | null; url: string | null }>;
    verified_at: string;
    by: string;
    datestamp: string;
    format_version: string | null;
}

const enc = new TextEncoder();
const dec = new TextDecoder();

export const relDir = (d: string) => `releases/${d}`;

export function log(ctx: Ctx, level: "debug" | "info" | "warn", message: string): void {
    try {
        ctx.logger?.[level](message);
    } catch {
        /* a logger must not break the SDK */
    }
}

function retryAfter(res: HttpResponse): number | null {
    const v = res.header("retry-after");
    if (!v) return null;
    const n = Number(v);
    if (Number.isFinite(n)) return Math.min(Math.max(n, 0), 60);
    const t = Date.parse(v);
    return Number.isNaN(t) ? null : Math.min(Math.max((t - Date.now()) / 1000, 0), 60);
}

/**
 * One GET with the retry rules of spec 5.7: 3 attempts in all, on connection errors, 5xx and 429,
 * waiting 1 s then 2 s (or Retry-After, up to 60 s). A 404 is never retried. Returns 2xx, 304 and 404.
 */
export async function httpGet(ctx: Ctx, url: string, etag: string | null = null): Promise<HttpResponse> {
    const headers: Record<string, string> = { "User-Agent": ctx.userAgent };
    if (!url.endsWith(".gz")) headers["Accept-Encoding"] = "gzip";
    if (etag) headers["If-None-Match"] = etag;
    const backoff = [1, 2];
    let last: NetworkError | null = null;
    for (let attempt = 0; attempt < 3; attempt++) {
        let wait: number | null = null;
        try {
            const res = await ctx.platform.get(url, { headers, timeout: ctx.timeout, proxy: ctx.proxy, caFile: ctx.caFile });
            if ((res.status >= 200 && res.status < 300) || res.status === 304 || res.status === 404) {
                log(ctx, "debug", `GET ${url} ${res.status}`);
                return res;
            }
            last = new NetworkError(`HTTP ${res.status}: ${url}`, { url, status: res.status });
            if (res.status !== 429 && res.status < 500) throw last;
            wait = retryAfter(res);
        } catch (e) {
            if (!(e instanceof NetworkError)) throw e;
            if (e.status !== null && e.status !== 429 && e.status < 500) throw e;
            last = e;
        }
        if (attempt < 2) await ctx.platform.sleep(wait ?? backoff[attempt] ?? 2);
    }
    throw last ?? new NetworkError(`request failed: ${url}`, { url });
}

function parseEntry(v: unknown, pointerUrl: string): PointerEntry {
    if (!isObject(v) || typeof v["datestamp"] !== "string" || typeof v["format_version"] !== "string") {
        throw new InvalidReleaseError(`the pointer ${pointerUrl} has no datestamp or format_version`);
    }
    const files: FileInfo[] = [];
    for (const f of Array.isArray(v["files"]) ? v["files"] : []) {
        if (!isObject(f) || typeof f["name"] !== "string") continue;
        const u = typeof f["url"] === "string" ? f["url"] : f["name"];
        files.push({
            name: f["name"],
            url: new URL(u, pointerUrl).href,
            size: typeof f["size"] === "number" ? f["size"] : null,
            sha256: typeof f["sha256"] === "string" ? f["sha256"].toLowerCase() : null,
        });
    }
    files.sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
    return { datestamp: v["datestamp"], format_version: v["format_version"], doi: typeof v["doi"] === "string" ? v["doi"] : null, files };
}

/** A GET of a changing file with If-None-Match and the stored ETag; 304 reads the stored copy. Null on 404. */
async function getConditional(ctx: Ctx, name: string): Promise<{ body: Uint8Array; url: string } | null> {
    const url = new URL(name, ctx.baseUrl).href;
    const rel = `pointer/${name}`;
    const store = ctx.store;
    const cached = store ? await store.read(rel) : null;
    const etagBytes = store && cached ? await store.read(`${rel}.etag`) : null;
    const etag = etagBytes ? dec.decode(etagBytes).trim() : null;
    const res = await httpGet(ctx, url, etag);
    if (res.status === 404) return null;
    if (res.status === 304 && cached) {
        log(ctx, "debug", `pointer ${name}: 304, the stored copy is current`);
        return { body: cached, url };
    }
    if (res.status === 304) throw new NetworkError(`unexpected 304: ${url}`, { url, status: 304 });
    if (store) {
        await store.write(rel, res.body);
        const tag = res.header("etag");
        if (tag) await store.write(`${rel}.etag`, enc.encode(tag));
        else await store.remove(`${rel}.etag`);
    }
    log(ctx, "debug", `pointer ${name}: 200`);
    return { body: res.body, url };
}

function newestSupported(entries: PointerEntry[]): PointerEntry | null {
    return entries.filter((e) => supportedFormat(e.format_version)).sort((a, b) => compareDatestamps(b.datestamp, a.datestamp))[0] ?? null;
}

/** Every release in OTC_index.json, newest first. */
export async function getIndex(ctx: Ctx): Promise<PointerEntry[]> {
    const r = await getConditional(ctx, "OTC_index.json");
    if (!r) throw new ReleaseNotFoundError(`no release index at ${new URL("OTC_index.json", ctx.baseUrl).href}`);
    return parseIndex(r.body, r.url);
}

export function parseIndex(body: Uint8Array, url: string): PointerEntry[] {
    const doc = parseJson(body, "OTC_index.json");
    const rels = isObject(doc) && Array.isArray(doc["releases"]) ? doc["releases"] : [];
    return rels.map((e) => parseEntry(e, url)).sort((a, b) => compareDatestamps(b.datestamp, a.datestamp));
}

/** The cached index, for releases() offline. */
export async function cachedIndex(ctx: Ctx): Promise<PointerEntry[] | null> {
    const b = ctx.store ? await ctx.store.read("pointer/OTC_index.json") : null;
    return b ? parseIndex(b, new URL("OTC_index.json", ctx.baseUrl).href) : null;
}

/** The latest release with a supported format major (spec 5.2 steps 1-2, 7.4). */
export async function getPointer(ctx: Ctx): Promise<PointerEntry> {
    const major = Math.max(...SUPPORTED_FORMAT_MAJORS);
    let r = await getConditional(ctx, `OTC_latest-f${major}.json`);
    if (!r) r = await getConditional(ctx, "OTC_latest.json");
    if (!r) throw new ReleaseNotFoundError(`no latest pointer at ${ctx.baseUrl}`);
    const entry = parseEntry(parseJson(r.body, "the latest pointer"), r.url);
    if (supportedFormat(entry.format_version)) return entry;
    log(ctx, "warn", `a newer format (${entry.format_version}) exists; upgrade opentideconstants to read it`);
    const best = newestSupported(await getIndex(ctx));
    if (!best) throw new UnsupportedFormatError(`no release with a supported format major (${SUPPORTED_FORMAT_MAJORS.join(", ")}) at ${ctx.baseUrl}`);
    return best;
}

export async function readVerified(store: CacheStore, d: string): Promise<Verified | null> {
    const b = await store.read(`${relDir(d)}/.verified`);
    if (!b) return null;
    try {
        const v: unknown = JSON.parse(dec.decode(b));
        if (isObject(v) && isObject(v["files"])) return v as unknown as Verified;
    } catch {
        /* a broken .verified is the same as none */
    }
    return null;
}

const names = (d: string) => ({
    json: `OTC_${d}.json`, gz: `OTC_${d}.json.gz`, jsonl: `OTC_${d}.jsonl`, meta: `OTC_${d}.meta.json`, sha: `OTC_${d}.sha256`,
});

/** True if the cached files can be opened in this mode. */
export function usable(mode: Mode, d: string, present: Set<string>): boolean {
    const n = names(d);
    const stream = present.has(n.jsonl) && present.has(n.meta);
    return mode === "stream" ? stream : present.has(n.json) || stream;
}

/** Cached, verified datestamps with a supported format, newest first. */
export async function cachedDatestamps(store: CacheStore): Promise<string[]> {
    const out: string[] = [];
    for (const d of await store.list("releases")) {
        const v = await readVerified(store, d);
        if (v && (v.format_version === null || v.format_version === undefined || supportedFormat(v.format_version))) out.push(d);
    }
    return out.sort((a, b) => compareDatestamps(b, a));
}

/** The newest cached release usable in this mode, or null. */
export async function newestCached(ctx: Ctx): Promise<string | null> {
    if (!ctx.store) return null;
    for (const d of await cachedDatestamps(ctx.store)) {
        if (usable(ctx.mode, d, new Set(await ctx.store.list(relDir(d))))) return d;
    }
    return null;
}

function checkBytes(name: string, actualSha: string, size: number, expectSha: string | null, expectSize: number | null): void {
    if (expectSize !== null && size !== expectSize) {
        throw new ChecksumError(`${name}: size ${size}, expected ${expectSize}`, { file: name, expected: expectSha, actual: actualSha });
    }
    if (expectSha === null || actualSha !== expectSha) {
        throw new ChecksumError(`${name}: SHA-256 ${actualSha}, expected ${expectSha ?? "(not listed)"}`, { file: name, expected: expectSha, actual: actualSha });
    }
}

/** Fetch OTC_{D}.sha256 and check it against the pointer entry. */
export async function fetchSha256(ctx: Ctx, d: string, entry: PointerEntry | null): Promise<{ bytes: Uint8Array; rows: Map<string, string> }> {
    const n = names(d);
    const url = entry?.files.find((f) => f.name === n.sha)?.url ?? new URL(n.sha, ctx.baseUrl).href;
    const res = await httpGet(ctx, url);
    if (res.status === 404) throw new ReleaseNotFoundError(`release ${d} not found at ${ctx.baseUrl}`);
    if (res.status !== 200) throw new NetworkError(`HTTP ${res.status}: ${url}`, { url, status: res.status });
    const rows = parseSha256(dec.decode(res.body));
    if (rows.size === 0) throw new InvalidReleaseError(`${n.sha} lists no files`);
    if (entry) {
        for (const f of entry.files) {
            const listed = rows.get(f.name);
            if (f.sha256 && listed && f.sha256 !== listed) {
                throw new ChecksumError(`the pointer and ${n.sha} disagree on ${f.name}`, { file: f.name, expected: f.sha256, actual: listed });
            }
        }
    }
    return { bytes: res.body, rows };
}

/** Download one release file and check its size and SHA-256 (spec 5.2 step 4). */
export async function fetchChecked(ctx: Ctx, name: string, rows: Map<string, string>, entry: PointerEntry | null): Promise<Uint8Array> {
    const f = entry?.files.find((x) => x.name === name);
    const url = f?.url ?? new URL(name, ctx.baseUrl).href;
    const res = await httpGet(ctx, url);
    if (res.status === 404) throw new ReleaseNotFoundError(`${name} not found at ${url}`);
    if (res.status !== 200) throw new NetworkError(`HTTP ${res.status}: ${url}`, { url, status: res.status });
    checkBytes(name, await ctx.platform.sha256(res.body), res.body.length, rows.get(name) ?? null, f?.size ?? null);
    return res.body;
}

/**
 * Make release D usable from the cache in ctx.mode: download what is missing, check it, write it
 * atomically, then `.verified` (spec 5.2 step 4, 5.4). Returns "cache" if nothing was downloaded.
 */
export async function ensureRelease(ctx: Ctx, d: string, entry: PointerEntry | null): Promise<"cache" | "download"> {
    const store = ctx.store;
    if (!store) throw new OfflineError("no cache");
    const dir = relDir(d);
    const present = new Set(await store.list(dir));
    let verified = await readVerified(store, d);
    if (verified && usable(ctx.mode, d, present)) return "cache";
    if (ctx.offline) throw new OfflineError(`release ${d} is not cached and the client is offline`);
    await store.mkdirs(dir);
    const unlock = await store.lock(dir);
    try {
        const now = new Set(await store.list(dir));
        verified = await readVerified(store, d);
        if (verified && usable(ctx.mode, d, now)) return "cache";
        const n = names(d);
        const { bytes: shaBytes, rows } = await fetchSha256(ctx, d, entry);
        const writes: [string, Uint8Array][] = [];
        if (ctx.mode === "stream") {
            for (const name of [n.jsonl, n.meta]) writes.push([name, await fetchChecked(ctx, name, rows, entry)]);
        } else if (rows.has(n.gz) && rows.has(n.json)) {
            log(ctx, "info", `downloading ${n.gz}`);
            const gz = await fetchChecked(ctx, n.gz, rows, entry);
            let json: Uint8Array;
            try {
                json = await ctx.platform.gunzip(gz);
            } catch (e) {
                throw new ChecksumError(`${n.gz} does not decompress`, { file: n.gz, expected: rows.get(n.gz) ?? null, actual: null, cause: e });
            }
            const size = entry?.files.find((x) => x.name === n.json)?.size ?? null;
            checkBytes(n.json, await ctx.platform.sha256(json), json.length, rows.get(n.json) ?? null, size);
            writes.push([n.json, json]);
        } else if (rows.has(n.json)) {
            writes.push([n.json, await fetchChecked(ctx, n.json, rows, entry)]);
        } else {
            for (const name of [n.jsonl, n.meta]) writes.push([name, await fetchChecked(ctx, name, rows, entry)]);
        }
        const formatVersion = await formatOf(writes, n);
        log(ctx, "info", `verified release ${d}`);
        for (const [name, bytes] of writes) await store.write(`${dir}/${name}`, bytes);
        await store.write(`${dir}/${n.sha}`, shaBytes);
        const files: Verified["files"] = { ...(verified?.files ?? {}) };
        const sizes = new Map(writes.map(([name, b]) => [name, b.length]));
        sizes.set(n.sha, shaBytes.length);
        if (entry) {
            for (const f of entry.files) files[f.name] = { sha256: f.sha256, size: f.size, url: f.url };
        } else {
            for (const [name, sha] of rows) {
                files[name] = { sha256: sha, size: sizes.get(name) ?? files[name]?.size ?? null, url: new URL(name, ctx.baseUrl).href };
            }
        }
        const v: Verified = {
            files, verified_at: new Date().toISOString().replace(/\.\d{3}Z$/, "Z"), by: SDK_ID, datestamp: d,
            format_version: formatVersion ?? entry?.format_version ?? verified?.format_version ?? null,
        };
        await store.write(`${dir}/.verified`, enc.encode(JSON.stringify(v)));
        return "download";
    } finally {
        await unlock();
    }
}

async function formatOf(writes: [string, Uint8Array][], n: ReturnType<typeof names>): Promise<string | null> {
    const meta = writes.find((w) => w[0] === n.meta) ?? writes.find((w) => w[0] === n.json);
    if (!meta) return null;
    const doc = parseJson(meta[1], meta[0]);
    const fv = isObject(doc) ? doc["format_version"] : null;
    if (typeof fv !== "string") throw new InvalidReleaseError(`${meta[0]} has no format_version`);
    if (!supportedFormat(fv)) throw new UnsupportedFormatError(`format ${fv} is not supported; upgrade opentideconstants`);
    return fv;
}

/** A cached release directory, read synchronously (Node: the disk; browser: files read beforehand). */
export interface SyncDir {
    read(name: string): Uint8Array | null;
    size(name: string): number | null;
    lineReader(name: string): { read: LineReader; close: () => void } | null;
    writeIndex(bytes: Uint8Array): void;
}

/** Open a cached, verified release (spec 5.3: sizes are checked against .verified). Synchronous. */
export function loadCached(dir: SyncDir, verified: Verified, d: string, mode: Mode): Release {
    const n = names(d);
    const files: FileInfo[] = Object.entries(verified.files)
        .map(([name, f]) => ({ name, url: f.url ?? null, size: f.size ?? null, sha256: f.sha256 ?? null }))
        .sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
    const sized = (name: string): Uint8Array => {
        const b = dir.read(name);
        if (!b) throw new ChecksumError(`${name} is missing from the cache`, { file: name, expected: verified.files[name]?.sha256 ?? null, actual: null });
        const want = verified.files[name]?.size;
        if (typeof want === "number" && want !== b.length) {
            throw new ChecksumError(`${name}: size ${b.length}, expected ${want}`, { file: name, expected: verified.files[name]?.sha256 ?? null, actual: null });
        }
        return b;
    };
    if (mode === "eager") {
        if (dir.size(n.json) !== null) return releaseFromJson(sized(n.json), files);
        return releaseFromJsonl(sized(n.meta), sized(n.jsonl), { eager: true, files });
    }
    const meta = sized(n.meta);
    const want = verified.files[n.jsonl]?.size;
    const have = dir.size(n.jsonl);
    if (have === null || (typeof want === "number" && want !== have)) {
        throw new ChecksumError(`${n.jsonl}: size ${have}, expected ${want}`, { file: n.jsonl, expected: verified.files[n.jsonl]?.sha256 ?? null, actual: null });
    }
    const jsonlSha = verified.files[n.jsonl]?.sha256 ?? null;
    const header = headerFromMeta(meta);
    let index: StreamIndex | null = null;
    const ib = dir.read("index-v1.json");
    if (ib) {
        try {
            const v: unknown = JSON.parse(dec.decode(ib));
            const entries = usableIndex(v, d, jsonlSha, have, new Set(header.conventions.map((c) => String(c["convention_id"]))),
                new Set(header.licences.map((l) => String(l["licence_id"]))));
            if (entries) index = { entries };
        } catch {
            /* a stale or broken index is rebuilt below */
        }
    }
    let jsonl: Uint8Array | null = null;
    if (!index) {
        jsonl = sized(n.jsonl);
        const { entries } = indexJsonl(header, jsonl, false);
        index = { entries };
        // .verified gives the .jsonl digest the index records; without it there is no index to write
        if (jsonlSha !== null) dir.writeIndex(enc.encode(JSON.stringify(storedIndex(entries, d, jsonlSha, jsonl.length, SDK_ID))));
    }
    const lr = dir.lineReader(n.jsonl);
    if (lr) return releaseFromJsonl(meta, null, { eager: false, files, index, reader: lr.read, close: lr.close });
    const bytes = jsonl ?? sized(n.jsonl);
    return releaseFromJsonl(meta, null, { eager: false, files, index, reader: (o, l) => bytes.subarray(o, o + l) });
}

/** Read a cache directory into a SyncDir (the browser, where storage is async). */
export async function prefetchDir(store: CacheStore, d: string): Promise<SyncDir> {
    const dir = relDir(d);
    const files = new Map<string, Uint8Array>();
    for (const name of await store.list(dir)) {
        const b = await store.read(`${dir}/${name}`);
        if (b) files.set(name, b);
    }
    return {
        read: (name) => files.get(name) ?? null,
        size: (name) => files.get(name)?.length ?? null,
        lineReader: () => null,
        writeIndex: (bytes) => void store.write(`${dir}/index-v1.json`, bytes).catch(() => undefined),
    };
}

/** Re-hash the cached files of release D against .verified (spec 4.3 verify). */
export async function verifyCached(ctx: Ctx, d: string): Promise<true> {
    const store = ctx.store;
    if (!store) throw new OfflineError("no cache");
    const v = await readVerified(store, d);
    if (!v) throw new ChecksumError(`release ${d} has no .verified`, { file: `${relDir(d)}/.verified`, expected: null, actual: null });
    const present = new Set(await store.list(relDir(d)));
    for (const [name, f] of Object.entries(v.files)) {
        if (!present.has(name) || name.endsWith(".sha256")) continue;
        const b = await store.read(`${relDir(d)}/${name}`);
        if (!b) continue;
        const actual = await ctx.platform.sha256(b);
        if (f.sha256 && actual !== f.sha256) {
            throw new ChecksumError(`${name}: SHA-256 ${actual}, expected ${f.sha256}`, { file: store.describe(`${relDir(d)}/${name}`), expected: f.sha256, actual });
        }
    }
    return true;
}

export { names as releaseNames, checkBytes };
