/** @internal The network and cache flows (spec 5.2 to 5.4), shared by the client and the auto-update worker. */
import { checkVersion, compareDatestamps, formatMajor, isDatestamp, readerReads, SDK_ID, supportedFormat, SUPPORTED_FORMAT_MAJORS } from "./constants.js";
import {
    ChecksumError, InvalidReleaseError, NetworkError, OfflineError, OpenTideConstantsError, ReleaseNotFoundError,
    UnsupportedFormatError,
} from "./errors.js";
import { isObject } from "./json.js";
import {
    checkFormat, headerFromMeta, indexJsonl, parseJson, parseSha256, readerTooOld, releaseFromJson, releaseFromJsonl,
    type LineReader, type StreamIndex,
} from "./loader.js";
import type { CacheStore, HttpResponse, Platform, Unlock } from "./platform.js";
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
    min_reader_version: string | null;
    concept_doi: string | null;
    zenodo_version_doi: string | null;
    content_sha256: string | null;
    files: FileInfo[];
}

/** The `.verified` record of a cached release (spec 5.4). */
export interface Verified {
    files: Record<string, { sha256: string | null; size: number | null; url: string | null }>;
    verified_at: string;
    by: string;
    datestamp: string;
    format_version: string | null;
    /** The release's min_reader_version (absent in a record another writer made). */
    min_reader_version?: string | null;
    /** The version DOI of the newest pointer or index entry read for this datestamp (spec 4.3). */
    zenodo_version_doi?: string | null;
}

const enc = new TextEncoder();
const dec = new TextDecoder();

/** The cache directory of release D (spec 5.4). D is checked again here, so no path leaves `<root>/v1/releases`. */
export function relDir(d: string): string {
    if (!isDatestamp(d)) throw new InvalidReleaseError(`bad datestamp ${JSON.stringify(d)}`);
    return `releases/${d}`;
}

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
    // a .gz file is fetched as it is: no transfer encoding on top (spec 5.7)
    headers["Accept-Encoding"] = new URL(url).pathname.endsWith(".gz") ? "identity" : "gzip";
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

/**
 * Check one latest-pointer or index entry from the server (spec 4.2, 5.2). A datestamp that is not one (`../x`,
 * `2026-10-08`, a counter `.01` or longer than 9 digits) is invalid_release: it names a cache directory (spec 5.4).
 * `what` names the file in the message ("the pointer" or "OTC_index.json").
 */
function parseEntry(v: unknown, url: string, what = "the pointer"): PointerEntry {
    if (!isObject(v) || typeof v["datestamp"] !== "string" || typeof v["format_version"] !== "string") {
        throw new InvalidReleaseError(`${what} ${url}: an entry has no datestamp or format_version`);
    }
    const d = v["datestamp"];
    checkVersion(v["format_version"], `${what} ${url}: format_version of ${d}`);
    checkVersion(v["min_reader_version"], `${what} ${url}: min_reader_version of ${d}`);
    if (!isDatestamp(d)) throw new InvalidReleaseError(`${what} ${url}: bad datestamp ${JSON.stringify(d)}`);
    const rawFiles = v["files"] ?? [];
    if (!Array.isArray(rawFiles)) throw new InvalidReleaseError(`${what} ${url}: files of ${d} is not a list`);
    const files: FileInfo[] = [];
    for (const f of rawFiles) {
        if (!isObject(f) || typeof f["name"] !== "string") throw new InvalidReleaseError(`${what} ${url}: a file of ${d} has no name`);
        const u = typeof f["url"] === "string" ? f["url"] : f["name"];
        let href: string;
        try {
            href = new URL(u, url).href;
        } catch (e) {
            throw new InvalidReleaseError(`${what} ${url}: the url of ${f["name"]} is not a URL`, { cause: e });
        }
        const size = f["size"], sha = f["sha256"];
        if (typeof sha !== "string" || typeof size !== "number" || !Number.isInteger(size) || size < 0) {
            // as the schema requires (CR2 DR12): never a null that a later merge copies over the measured values
            throw new InvalidReleaseError(`${what} ${url}: the entry for ${f["name"]} of ${d} needs a string sha256 and an integer size of 0 or more`);
        }
        files.push({ name: f["name"], url: href, size, sha256: sha.toLowerCase() });
    }
    files.sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
    const s = (k: string) => (typeof v[k] === "string" ? (v[k] as string) : null);
    return {
        datestamp: d, format_version: v["format_version"], min_reader_version: s("min_reader_version"),
        concept_doi: s("concept_doi"), zenodo_version_doi: s("zenodo_version_doi"), content_sha256: s("content_sha256"), files,
    };
}

/** True if this SDK reads the entry's release: a supported major and a readable min_reader_version (spec 7.4). */
export function readable(e: { format_version: string | null; min_reader_version?: string | null }): boolean {
    return (e.format_version === null || supportedFormat(e.format_version)) && readerReads(e.min_reader_version ?? null);
}

/**
 * The shape of a pointer (an object with a datestamp and a files array) or of OTC_index.json (an object with a
 * releases array). A wrong value inside a body of the right shape is invalid_release later (CR2 DR13).
 */
function shapeOk(name: string, doc: unknown): boolean {
    if (!isObject(doc)) return false;
    if (name === "OTC_index.json") return Array.isArray(doc["releases"]);
    return "datestamp" in doc && Array.isArray(doc["files"]);
}

/**
 * A GET of a changing file (the pointer or OTC_index.json) with If-None-Match and the stored ETag; 304 reads the
 * stored copy. Null on 404. The body must be JSON of the right shape before it is stored: a 200 that is not JSON (a
 * captive portal, a proxy error page), or is JSON of the wrong shape, is a network error (spec 5.2 step 5, CR D8,
 * CR2 DR13), and the good stored copy stays. The body and its
 * ETag are written under pointer/.lock, the ETag removed first and written last, so no body is paired with
 * another body's ETag (spec 5.4). A failure to store them is logged, not raised (CR D8).
 */
async function getConditional(ctx: Ctx, name: string): Promise<{ body: Uint8Array; url: string; doc: unknown } | null> {
    const url = new URL(name, ctx.baseUrl).href;
    const rel = `pointer/${name}`;
    const store = ctx.store;
    const readEtag = async () => {
        const b = store ? await store.read(`${rel}.etag`) : null;
        return b ? dec.decode(b).trim() : null;
    };
    let etag = await readEtag();
    let cached = store ? await store.read(rel) : null;
    let cachedDoc: unknown = undefined;
    if (cached) {
        try {
            cachedDoc = JSON.parse(dec.decode(cached));
        } catch {
            cachedDoc = undefined;
        }
        // a broken stored copy is the same as none: no If-None-Match, so the server sends a 200
        if (!shapeOk(name, cachedDoc)) cached = null;
    }
    // the ETag is read before and after the body; a writer in between means they may not pair, so send none
    if (!cached || (await readEtag()) !== etag) etag = null;
    const res = await httpGet(ctx, url, etag);
    if (res.status === 404) return null;
    if (res.status === 304 && cached) {
        log(ctx, "debug", `pointer ${name}: 304, the stored copy is current`);
        return { body: cached, url, doc: cachedDoc };
    }
    if (res.status === 304) throw new NetworkError(`unexpected 304 with no stored copy: ${url}`, { url, status: 304 });
    let doc: unknown;
    try {
        doc = JSON.parse(dec.decode(res.body));
    } catch (e) {
        throw new NetworkError(`${url}: the 200 response is not JSON (a captive portal or a proxy page?)`, { url, status: res.status, cause: e });
    }
    if (!shapeOk(name, doc)) {
        throw new NetworkError(`${url}: the 200 response is JSON of the wrong shape (a proxy page?)`, { url, status: res.status });
    }
    if (store) {
        try {
            const unlock = await store.lock("pointer");
            try {
                await store.remove(`${rel}.etag`);
                await store.write(rel, res.body);
                const tag = res.header("etag");
                if (tag) await store.write(`${rel}.etag`, enc.encode(tag));
            } finally {
                await releaseLock(ctx, unlock);
            }
        } catch (e) {
            log(ctx, "warn", `cannot store ${name} in the cache: ${e instanceof Error ? e.message : String(e)}`);
        }
    }
    log(ctx, "debug", `pointer ${name}: 200`);
    return { body: res.body, url, doc };
}

function newestReadable(entries: PointerEntry[]): PointerEntry | null {
    return entries.filter(readable).sort((a, b) => compareDatestamps(b.datestamp, a.datestamp))[0] ?? null;
}

/** Every release in OTC_index.json, newest first. */
export async function getIndex(ctx: Ctx): Promise<PointerEntry[]> {
    const r = await getConditional(ctx, "OTC_index.json");
    if (!r) throw new ReleaseNotFoundError(`no release index at ${new URL("OTC_index.json", ctx.baseUrl).href}`);
    return indexEntries(r.doc, r.url);
}

export function parseIndex(body: Uint8Array, url: string): PointerEntry[] {
    return indexEntries(parseJson(body, "OTC_index.json"), url);
}

function indexEntries(doc: unknown, url: string): PointerEntry[] {
    const rels = isObject(doc) ? doc["releases"] : undefined;
    if (!Array.isArray(rels)) throw new InvalidReleaseError(`OTC_index.json ${url}: releases is missing or not a list`);
    return rels.map((e) => parseEntry(e, url, "OTC_index.json")).sort((a, b) => compareDatestamps(b.datestamp, a.datestamp));
}

/** The cached index, for releases() offline. */
export async function cachedIndex(ctx: Ctx): Promise<PointerEntry[] | null> {
    const b = ctx.store ? await ctx.store.read("pointer/OTC_index.json") : null;
    return b ? parseIndex(b, new URL("OTC_index.json", ctx.baseUrl).href) : null;
}

/** The result of reading the latest pointer: the entry to use, and whether OTC_latest.json was the pointer read. */
export interface PointerRead {
    entry: PointerEntry;
    /** The parsed OTC_latest.json entry, when the per-major pointer was 404 and the SDK fell back to it. */
    generic: PointerEntry | null;
}

/**
 * The latest release this SDK reads (spec 5.2 steps 2 and 2a, 7.4): GET OTC_latest-f{MAJOR}.json, and only on a
 * 404 OTC_latest.json. When the pointer's release has an unsupported major or a min_reader_version newer than
 * this SDK reads, one GET of OTC_index.json picks the newest readable release. None: reader_too_old when a
 * release of a supported major exists, otherwise unsupported_format.
 */
export async function readPointer(ctx: Ctx): Promise<PointerRead> {
    const major = Math.max(...SUPPORTED_FORMAT_MAJORS);
    let generic = false;
    let r = await getConditional(ctx, `OTC_latest-f${major}.json`);
    if (!r) {
        generic = true;
        r = await getConditional(ctx, "OTC_latest.json");
    }
    if (!r) throw new ReleaseNotFoundError(`no latest pointer at ${ctx.baseUrl}`);
    const entry = parseEntry(r.doc, r.url);
    const out = (e: PointerEntry): PointerRead => ({ entry: e, generic: generic ? entry : null });
    if (readable(entry)) return out(entry);
    if (!supportedFormat(entry.format_version)) {
        log(ctx, "warn", `a newer format (${formatMajor(entry.format_version)}) exists; upgrade opentideconstants to read it`);
    } else {
        log(ctx, "warn", `release ${entry.datestamp} needs a reader for format ${entry.min_reader_version}; looking for the newest release this SDK reads`);
    }
    const index = await getIndex(ctx);
    const best = newestReadable(index);
    if (best) return out(best);
    const tooNew = [entry, ...index].filter((e) => supportedFormat(e.format_version))
        .sort((a, b) => compareDatestamps(b.datestamp, a.datestamp))[0];
    if (tooNew) throw readerTooOld(tooNew.datestamp, String(tooNew.min_reader_version));
    throw new UnsupportedFormatError(`no release with a supported format major (${SUPPORTED_FORMAT_MAJORS.join(", ")}) at ${ctx.baseUrl}`);
}

/** The latest release this SDK reads (see readPointer). */
export async function getPointer(ctx: Ctx): Promise<PointerEntry> {
    return (await readPointer(ctx)).entry;
}

/** @internal The newest format major named by OTC_latest.json (one conditional GET), or null on a 404. */
export async function genericPointerMajor(ctx: Ctx): Promise<number | null> {
    const r = await getConditional(ctx, "OTC_latest.json");
    if (!r) return null;
    const major = formatMajor(parseEntry(r.doc, r.url, "OTC_latest.json").format_version);
    return Number.isNaN(major) ? null : major;
}

/**
 * The `.verified` record of release D, checked key by key (spec 5.4, CR D26; PK10 T81): a record that is not JSON or
 * has no `files` object is the same as none (the release is verified again). A key with the wrong type is the same
 * as an absent key, and an absent datestamp is D. A version string that is present but not MAJOR.MINOR is
 * invalid_release (CR D9).
 */
export async function readVerified(store: CacheStore, d: string): Promise<Verified | null> {
    const b = await store.read(`${relDir(d)}/.verified`);
    return b ? parseVerified(b, d) : null;
}

/** The checked `.verified` record from its bytes (see readVerified). */
export function parseVerified(b: Uint8Array, d: string): Verified | null {
    let v: unknown;
    try {
        v = JSON.parse(dec.decode(b));
    } catch {
        return null;
    }
    if (!isObject(v) || !isObject(v["files"])) return null;
    const files: Verified["files"] = {};
    for (const [name, f] of Object.entries(v["files"])) {
        if (!isObject(f)) return null;
        const sha = f["sha256"];
        const size = f["size"];
        const url = f["url"];
        files[name] = {
            sha256: typeof sha === "string" && /^[0-9a-fA-F]{64}$/.test(sha) ? sha.toLowerCase() : null,
            size: typeof size === "number" && Number.isInteger(size) && size >= 0 ? size : null,
            url: typeof url === "string" ? url : null,
        };
    }
    const s = (k: string): string | null | undefined => {
        const x = v[k];
        return typeof x === "string" ? x : x === null ? null : undefined;
    };
    checkVersion(v["format_version"], `${relDir(d)}/.verified: format_version`);
    checkVersion(v["min_reader_version"], `${relDir(d)}/.verified: min_reader_version`);
    const out: Verified = {
        files, verified_at: s("verified_at") ?? "", by: s("by") ?? "", datestamp: d, format_version: s("format_version") ?? null,
    };
    const mrv = s("min_reader_version");
    if (mrv !== undefined) out.min_reader_version = mrv;
    const doi = s("zenodo_version_doi");
    if (doi !== undefined) out.zenodo_version_doi = doi;
    return out;
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

/**
 * Cached, verified datestamps that this SDK reads, newest first (spec 5.2 step 1): a supported format major and a
 * readable min_reader_version, from `.verified` or, when it does not say, from the cached OTC_index.json.
 */
export async function cachedDatestamps(ctx: Ctx): Promise<string[]> {
    const store = ctx.store;
    if (!store) return [];
    let index: Map<string, PointerEntry> | null = null;
    const out: string[] = [];
    for (const d of await store.list("releases")) {
        if (!isDatestamp(d)) continue;
        const v = await readVerified(store, d);
        if (!v) continue;
        if (!readable({ format_version: v.format_version ?? null, min_reader_version: v.min_reader_version ?? null })) continue;
        if (v.format_version === null || v.format_version === undefined || v.min_reader_version === undefined) {
            index ??= new Map(((await cachedIndex(ctx).catch(() => null)) ?? []).map((e) => [e.datestamp, e]));
            const e = index.get(d);
            if (e && !readable(e)) continue;
        }
        out.push(d);
    }
    return out.sort((a, b) => compareDatestamps(b, a));
}

/** The newest cached release usable in this mode, or null. */
export async function newestCached(ctx: Ctx): Promise<string | null> {
    if (!ctx.store) return null;
    for (const d of await cachedDatestamps(ctx)) {
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

/** True if a .sha256 body has at least one "<sha256>  <name>" row (CR2 DR13). Read as latin1, so any byte is a char. */
function hasSha256Row(body: Uint8Array): boolean {
    return new TextDecoder("latin1").decode(body).split(/\r?\n/).some((l) => /^\s*[0-9a-fA-F]{64}[ \t]+\*?\S/.test(l));
}

/** Fetch OTC_{D}.sha256 and check it against the pointer entry. */
export async function fetchSha256(ctx: Ctx, d: string, entry: PointerEntry | null): Promise<{ bytes: Uint8Array; rows: Map<string, string> }> {
    const n = names(d);
    const url = entry?.files.find((f) => f.name === n.sha)?.url ?? new URL(n.sha, ctx.baseUrl).href;
    const res = await httpGet(ctx, url);
    if (res.status === 404) throw new ReleaseNotFoundError(`release ${d} not found at ${ctx.baseUrl}`);
    if (res.status !== 200) throw new NetworkError(`HTTP ${res.status}: ${url}`, { url, status: res.status });
    if (!hasSha256Row(res.body)) {
        // checked before the digest: a captive portal or a proxy page is the network, not a bad release (CR2 DR13)
        throw new NetworkError(`${url}: the 200 response has no "<sha256>  <name>" row (a captive portal or a proxy page?)`, { url, status: res.status });
    }
    if (entry) {
        // OTC_{D}.sha256 is itself listed in the pointer: check it first (spec 5.2 step 4.1, PK11 T78)
        const own = entry.files.find((f) => f.name === n.sha);
        if (own) checkBytes(n.sha, await ctx.platform.sha256(res.body), res.body.length, own.sha256, own.size);
    }
    const rows = parseSha256(res.body, n.sha);
    if (rows.size === 0) throw new InvalidReleaseError(`${n.sha} lists no files`);
    if (entry) {
        // the pointer and OTC_{D}.sha256 list the same files with the same digests (spec 5.2 step 4.1)
        for (const f of entry.files) {
            if (f.name === n.sha) continue;
            const listed = rows.get(f.name);
            if (f.sha256 && listed && f.sha256 !== listed) {
                throw new ChecksumError(`the pointer and ${n.sha} disagree on ${f.name}`, { file: f.name, expected: f.sha256, actual: listed });
            }
        }
        const named = new Set(entry.files.map((f) => f.name));
        for (const [name, sha] of rows) {
            if (!named.has(name)) throw new ChecksumError(`${n.sha} lists ${name}, which the pointer does not`, { file: name, expected: null, actual: sha });
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
    if (verified && usable(ctx.mode, d, present)) {
        await syncZenodo(ctx, verified, entry);
        return "cache";
    }
    if (ctx.offline) throw new OfflineError(`release ${d} is not cached and the client is offline`);
    await store.mkdirs(dir);
    // wait for the lock, or until another process has made the release usable in this mode (spec 5.4)
    const unlock = await store.lock(dir, {
        done: async () => (await readVerified(store, d)) !== null && usable(ctx.mode, d, new Set(await store.list(dir))),
    });
    try {
        const now = new Set(await store.list(dir));
        verified = await readVerified(store, d);
        if (verified && usable(ctx.mode, d, now)) {
            await syncZenodo(ctx, verified, entry, true);
            return "cache";
        }
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
                if (e instanceof OpenTideConstantsError) throw e; // for example, no DecompressionStream (PK10 T31)
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
        const format = formatOf(writes, n);
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
            format_version: format?.format_version ?? entry?.format_version ?? verified?.format_version ?? null,
            min_reader_version: format ? format.min_reader_version : entry?.min_reader_version ?? verified?.min_reader_version ?? null,
            zenodo_version_doi: entry ? entry.zenodo_version_doi : verified?.zenodo_version_doi ?? null,
        };
        await store.write(`${dir}/.verified`, enc.encode(JSON.stringify(v)));
        return "download";
    } finally {
        await releaseLock(ctx, unlock);
    }
}

/** Release a lock; a failure leaves a stale lock that a later waiter removes, so it is logged, not raised. */
async function releaseLock(ctx: Ctx, unlock: Unlock | null): Promise<void> {
    try {
        await unlock?.();
    } catch (e) {
        log(ctx, "warn", e instanceof Error ? e.message : String(e));
    }
}

/**
 * The format of the downloaded release, checked before it goes into the cache: unsupported_format or
 * reader_too_old (spec 7.4).
 */
function formatOf(writes: [string, Uint8Array][], n: ReturnType<typeof names>): { format_version: string; min_reader_version: string | null } | null {
    const meta = writes.find((w) => w[0] === n.meta) ?? writes.find((w) => w[0] === n.json);
    if (!meta) return null;
    const doc = parseJson(meta[1], meta[0]);
    const fv = isObject(doc) ? doc["format_version"] : null;
    if (typeof fv !== "string") throw new InvalidReleaseError(`${meta[0]} has no format_version`);
    checkFormat(doc);
    const rel = isObject(doc) ? doc["release"] : null;
    const min = isObject(rel) && typeof rel["min_reader_version"] === "string" ? rel["min_reader_version"] : null;
    return { format_version: fv, min_reader_version: min };
}

/**
 * Store the version DOI of an entry the SDK read for a cached release in its `.verified`, when it changed
 * (spec 4.3: the newest pointer or index entry for that datestamp). The write is a read-modify-write of `.verified`,
 * so it runs under the release lock and re-reads `.verified` there; `held` says the caller holds the lock already.
 * When another process holds the lock, or a write fails, it is skipped and logged: the next read syncs it.
 */
export async function syncZenodo(ctx: Ctx, verified: Verified, entry: PointerEntry | null, held = false): Promise<void> {
    const store = ctx.store;
    if (!store || !entry) return;
    const d = entry.datestamp;
    if ((verified.datestamp ?? d) !== d || (verified.zenodo_version_doi ?? null) === entry.zenodo_version_doi) return;
    let unlock: Unlock | null = null;
    try {
        if (!held) {
            unlock = await store.lock(relDir(d), { wait: false });
            if (!unlock) {
                log(ctx, "debug", `the .verified of ${d} is locked; its version DOI is updated next time`);
                return;
            }
        }
        const now = await readVerified(store, d);
        if (!now || (now.zenodo_version_doi ?? null) === entry.zenodo_version_doi) return;
        // change only this key; keys this SDK does not know (another SDK wrote them) stay as they are
        const raw = await store.read(`${relDir(d)}/.verified`);
        const doc: unknown = raw ? JSON.parse(dec.decode(raw)) : null;
        if (!isObject(doc)) return;
        await store.write(`${relDir(d)}/.verified`, enc.encode(JSON.stringify({ ...doc, zenodo_version_doi: entry.zenodo_version_doi })));
    } catch (e) {
        log(ctx, "warn", `cannot update the .verified of ${d}: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
        await releaseLock(ctx, unlock);
    }
}

/** A cached release directory, read synchronously (Node: the disk; browser: files read beforehand). */
export interface SyncDir {
    read(name: string): Uint8Array | null;
    size(name: string): number | null;
    lineReader(name: string): { read: LineReader; close: () => void } | null;
    writeIndex(bytes: Uint8Array): void;
    /** Delete index-v1.json (a line did not match it). Throws when it cannot; the caller logs that. */
    removeIndex(): void;
}

/** Open a cached, verified release (spec 5.3: sizes are checked against .verified). Synchronous. */
export function loadCached(dir: SyncDir, verified: Verified, d: string, mode: Mode, warn: (message: string) => void = () => undefined): Release {
    const n = names(d);
    const zenodo = typeof verified.zenodo_version_doi === "string" ? verified.zenodo_version_doi : null;
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
        if (dir.size(n.json) !== null) return releaseFromJson(sized(n.json), files, zenodo);
        return releaseFromJsonl(sized(n.meta), sized(n.jsonl), { eager: true, files, zenodoVersionDoi: zenodo });
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
    const dropIndex = () => {
        try {
            dir.removeIndex();
        } catch (e) {
            warn(`cannot delete index-v1.json of ${d}: ${e instanceof Error ? e.message : String(e)}`);
        }
    };
    const lr = dir.lineReader(n.jsonl);
    if (lr) {
        try {
            return releaseFromJsonl(meta, null, { eager: false, files, index, reader: lr.read, close: lr.close, zenodoVersionDoi: zenodo, dropIndex });
        } catch (e) {
            lr.close();
            throw e;
        }
    }
    const bytes = jsonl ?? sized(n.jsonl);
    return releaseFromJsonl(meta, null, { eager: false, files, index, reader: (o, l) => bytes.subarray(o, o + l), zenodoVersionDoi: zenodo, dropIndex });
}

/** Read a cache directory into a SyncDir (the browser, where storage is async). */
export async function prefetchDir(store: CacheStore, d: string, warn: (message: string) => void = () => undefined): Promise<SyncDir> {
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
        removeIndex: () => void store.remove(`${dir}/index-v1.json`).catch((e: unknown) => warn(`cannot delete index-v1.json of ${d}: ${String(e)}`)),
    };
}

/**
 * Hash the cached files of release D again, in full, and compare them with the cached OTC_{D}.sha256 (spec 4.3
 * verify). The files this mode loads must be there; every listed data file that is there is hashed. A file that
 * does not match is deleted from the cache (spec 4.8 checksum_mismatch), so the next open downloads it again.
 */
export async function verifyCached(ctx: Ctx, d: string): Promise<true> {
    const store = ctx.store;
    if (!store) throw new OfflineError("no cache");
    const dir = relDir(d);
    const n = names(d);
    const shaBytes = await store.read(`${dir}/${n.sha}`);
    if (!shaBytes) throw new ChecksumError(`${n.sha} is missing from the cache`, { file: store.describe(`${dir}/${n.sha}`), expected: null, actual: null });
    const rows = parseSha256(shaBytes, n.sha);
    const present = new Set(await store.list(dir));
    const needed = ctx.mode === "stream" || !present.has(n.json) ? [n.jsonl, n.meta] : [n.json];
    let checked = 0;
    for (const name of [...new Set([...needed, ...rows.keys()])]) {
        if (name === n.sha) continue;
        const file = store.describe(`${dir}/${name}`);
        const expected = rows.get(name) ?? null;
        const b = present.has(name) ? await store.read(`${dir}/${name}`) : null;
        if (!b) {
            if (needed.includes(name)) throw new ChecksumError(`${name} is missing from the cache`, { file, expected, actual: null });
            continue;
        }
        const actual = await ctx.platform.sha256(b);
        if (actual !== expected) {
            await store.remove(`${dir}/${name}`).catch((e: unknown) => log(ctx, "warn", `cannot delete ${file}: ${String(e)}`));
            throw new ChecksumError(`${name}: SHA-256 ${actual}, expected ${expected ?? "(not listed)"}`, { file, expected, actual });
        }
        checked++;
    }
    if (checked === 0) throw new ChecksumError(`no file of release ${d} was checked`, { file: store.describe(dir), expected: null, actual: null });
    return true;
}

export { names as releaseNames, checkBytes };
