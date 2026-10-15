/** @internal The network and cache flows (spec 5.2 to 5.4), shared by the client and the auto-update worker. */
import { checkVersion, compareDatestamps, formatMajor, isDatestamp, readerReads, SDK_ID, supportedFormat, SUPPORTED_FORMAT_MAJORS } from "./constants.js";
import {
    CacheError, ChecksumError, FileError, InvalidReleaseError, NetworkError, OfflineError, OpenTideConstantsError, redactCredentials, ReleaseNotFoundError,
    UnsupportedFormatError,
} from "./errors.js";
import { daysInMonth, isObject } from "./json.js";
import { encodeCacheJson } from "./cache-json.js";
import {
    checkFormat, headerFromMeta, indexJsonl, parseJson, parseSha256, readerTooOld, releaseFromJson, releaseFromJsonl, prepareReleaseFromJsonl, scanJsonlReader,
    type LineReader, type StreamIndex,
} from "./loader.js";
import type { CacheStore, HttpResponse, Platform, Unlock } from "./platform.js";
import { storedIndex, usableIndex, releaseFromPrepared, type Release, type PreparedReleaseFields } from "./release.js";
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
    /** The open option of spec 4.2 (K-NC DR106), applied to every release the client loads. */
    commercialOnly: boolean;
    commercialBasis?: "strict" | "as_published_upstream";
    historicalOffsetsPolicy?: "fallback" | "exclude";
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
        ctx.logger?.[level](redactCredentials(message)); // no URL user or password in a log line (CR2 DR21)
    } catch {
        /* a logger must not break the SDK */
    }
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const IMF_FIXDATE = /^(Sun|Mon|Tue|Wed|Thu|Fri|Sat), ([0-9]{2}) (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) ([0-9]{4}) ([0-9]{2}):([0-9]{2}):([0-9]{2}) GMT$/;

/**
 * @internal An HTTP date (IMF-fixdate, RFC 9110 5.6.7) in milliseconds since the epoch, or null. Impossible calendar
 * fields, hour 24, a leap second and the wrong weekday are malformed: Date.parse would roll them over (CR2 DR6).
 */
export function httpDate(v: string): number | null {
    const m = IMF_FIXDATE.exec(v);
    if (!m) return null;
    const [d, y, h, mi, s] = [m[2], m[4], m[5], m[6], m[7]].map(Number) as [number, number, number, number, number];
    const mo = MONTHS.indexOf(m[3] as string);
    if (d < 1 || d > daysInMonth(y, mo + 1) || h > 23 || mi > 59 || s > 59) return null;
    const t = new Date(0);
    t.setUTCFullYear(y, mo, d);
    t.setUTCHours(h, mi, s, 0);
    return WEEKDAYS[t.getUTCDay()] === m[1] ? t.getTime() : null;
}

function retryAfter(res: HttpResponse): number | null {
    const v = res.header("retry-after");
    if (!v) return null;
    const n = Number(v);
    if (Number.isFinite(n)) return Math.min(Math.max(n, 0), 60);
    const t = httpDate(v.trim());
    return t === null ? null : Math.min(Math.max((t - Date.now()) / 1000, 0), 60);
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

/** @internal Exact existing parsed file fields; parser owns admission and URL resolution. */
export function fileInfoOf(name: string, url: string, size: number, sha: string): FileInfo {
    return { name, url, size, sha256: sha.toLowerCase() };
}

/**
 * Check one latest-pointer or index entry from the server (spec 4.2, 5.2). A datestamp that is not one (`../x`,
 * `2026-10-08`, a counter `.01` or longer than 9 digits) is invalid_release: it names a cache directory (spec 5.4).
 * `what` names the file in the message ("the pointer" or "OTC_index.json").
 */
/** @internal Existing metadata entry validation, preserving source URL and error context. */
export function parseEntry(v: unknown, url: string, what = "the pointer"): PointerEntry {
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
        files.push(fileInfoOf(f["name"], href, size, sha));
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
        // Shared cache tags are nonempty printable ASCII bytes, preserved without trimming (spec 5.2).
        if (!b || b.length === 0 || b.length > 256 || b.some((byte) => byte < 0x20 || byte >= 0x7f)) return null;
        return dec.decode(b);
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
            const unlock = await store.lock("pointer", { warn: (message) => log(ctx, "warn", message) });
            try {
                await store.remove(`${rel}.etag`);
                await store.write(rel, res.body);
                const tag = res.header("etag");
                if (tag && tag.length <= 256 && /^[\x20-\x7e]+$/.test(tag)) await store.write(`${rel}.etag`, enc.encode(tag));
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

/** @internal Existing catalogue entry validation and source error ordering. */
export function indexEntries(doc: unknown, url: string): PointerEntry[] {
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
    // no index (a 404) means no other release to choose: the error is then about the pointer's release, as in the
    // other SDKs (reader_too_old or unsupported_format), never release_not_found (R2-098)
    let index: PointerEntry[];
    try {
        index = await getIndex(ctx);
    } catch (e) {
        if (!(e instanceof ReleaseNotFoundError)) throw e;
        index = [];
    }
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
 * has no `files` object is the same as none (the release is verified again). Known nullable keys may be absent,
 * but a present wrong type or value makes the receipt malformed. An absent datestamp is D (spec 5.4).
 */
export async function readVerified(store: CacheStore, d: string): Promise<Verified | null> {
    const b = await store.read(`${relDir(d)}/.verified`);
    return b ? parseVerified(b, d) : null;
}

/** The checked `.verified` record from its bytes (see readVerified). */
export function parseVerified(b: Uint8Array, d: string): Verified | null {
    let v: unknown;
    try {
        if (b[0] === 0xef && b[1] === 0xbb && b[2] === 0xbf) return null;
        v = parseJson(b, `${relDir(d)}/.verified`);
    } catch {
        return null;
    }
    if (!isObject(v) || !isObject(v["files"])) return null;
    const pending: { value: unknown; depth: number }[] = [{ value: v, depth: 1 }];
    while (pending.length) {
        const { value, depth } = pending.pop()!;
        if (typeof value === "number" && !Number.isFinite(value)) return null;
        if (typeof value === "object" && value !== null) {
            if (depth > 64) return null;
            for (const child of Object.values(value)) pending.push({ value: child, depth: depth + 1 });
        }
    }
    for (const key of ["datestamp", "format_version", "min_reader_version", "zenodo_version_doi", "verified_at", "by"]) {
        const value = v[key];
        if (value !== undefined && value !== null && typeof value !== "string") return null;
    }
    if (v["datestamp"] !== undefined && v["datestamp"] !== null && v["datestamp"] !== d) return null;
    try {
        checkVersion(v["format_version"], `${relDir(d)}/.verified: format_version`);
        checkVersion(v["min_reader_version"], `${relDir(d)}/.verified: min_reader_version`);
    } catch (e) {
        if (e instanceof InvalidReleaseError) return null;
        throw e;
    }
    const files: Verified["files"] = Object.create(null);
    for (const [name, f] of Object.entries(v["files"])) {
        if (!isObject(f)) return null;
        const sha = f["sha256"];
        const size = f["size"];
        const url = f["url"];
        // a row's size is an integer: a null or absent one makes .verified malformed (spec 5.4, CR3 spec review 2
        // B10 and 3 C4), the same as a size that is not a non-negative integer
        if (!(typeof size === "number" && Number.isSafeInteger(size) && size >= 0)) return null;
        if (sha !== undefined && sha !== null && !(typeof sha === "string" && /^[0-9a-fA-F]{64}$/.test(sha))) return null;
        if (url !== undefined && url !== null && typeof url !== "string") return null;
        files[name] = {
            sha256: typeof sha === "string" && /^[0-9a-fA-F]{64}$/.test(sha) ? sha.toLowerCase() : null,
            size,
            url: typeof url === "string" ? url : null,
        };
    }
    const s = (k: string): string | null | undefined => {
        const x = v[k];
        return typeof x === "string" ? x : x === null ? null : undefined;
    };
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

function cachedFile(name: string, present: boolean, verified?: Verified | null): boolean {
    return present && (verified === undefined ||
        (verified?.files[name]?.sha256 != null && verified.files[name]?.size != null));
}

/** True if the cached files can be opened in this mode. */
export function usable(mode: Mode, d: string, present: Set<string>, verified?: Verified | null): boolean {
    const n = names(d);
    const cached = (name: string) => cachedFile(name, present.has(name), verified);
    const stream = cached(n.jsonl) && cached(n.meta);
    return mode === "stream" ? stream : cached(n.json) || stream;
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
        let v: Verified | null;
        try {
            v = await readVerified(store, d);
        } catch (e) {
            // a .verified with a malformed version is that release's problem: skip it, never the whole list (R2-087)
            if (!(e instanceof InvalidReleaseError)) throw e;
            log(ctx, "warn", `skipping the cached release ${d}: ${e.message}`);
            continue;
        }
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
        if (usable(ctx.mode, d, new Set(await ctx.store.list(relDir(d))), await readVerified(ctx.store, d))) return d;
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
    return { bytes: res.body, rows: await checkSha256(ctx, d, entry, res.body) };
}

/**
 * Check the bytes of OTC_{D}.sha256 against the pointer entry, if any, and return its rows: its own digest and size
 * when the pointer lists it, at least one row, and the same files with the same digests as the pointer (spec 5.2
 * step 4.1). For a fetched copy and for a cached one (CR2 DR40).
 */
export async function checkSha256(ctx: Ctx, d: string, entry: PointerEntry | null, bytes: Uint8Array): Promise<Map<string, string>> {
    const n = names(d);
    if (entry) {
        // OTC_{D}.sha256 is itself listed in the pointer: check it first (spec 5.2 step 4.1, PK11 T78)
        const own = entry.files.find((f) => f.name === n.sha);
        if (own) checkBytes(n.sha, await ctx.platform.sha256(bytes), bytes.length, own.sha256, own.size);
    }
    const rows = parseSha256(bytes, n.sha);
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
    return rows;
}

/** @internal The unchanged mode-specific sidecar admission phase before acquisition. */
export function requireManifestRows(d: string, mode: Mode, rows: ReadonlyMap<string, string>, required?: readonly string[]): void {
    const n = names(d);
    const needed = mode === "stream" ? [n.jsonl, n.meta]
        : rows.has(n.gz) ? [n.gz, n.json] : rows.has(n.json) ? [n.json] : [n.jsonl, n.meta];
    for (const name of required ?? needed) {
        if (name === n.sha) continue;
        if (!rows.has(name)) throw new ChecksumError(`${name} is not listed in ${n.sha}`, { file: name, expected: null, actual: null });
    }
}

/** Download one release file, which the release's .sha256 lists, and check its size and SHA-256 (spec 5.2 step 4). */
export async function fetchChecked(ctx: Ctx, name: string, rows: Map<string, string>, entry: PointerEntry | null): Promise<Uint8Array> {
    const f = entry?.files.find((x) => x.name === name);
    const url = f?.url ?? new URL(name, ctx.baseUrl).href;
    const res = await httpGet(ctx, url);
    if (res.status === 404) {
        // the release exists (its .sha256 lists the file): a server inconsistency, network with status 404 (CR D32)
        const d = /^OTC_([0-9]{8}(?:\.[0-9]+)?)\./.exec(name)?.[1] ?? "{D}";
        throw new NetworkError(`${url}: 404; file listed in OTC_${d}.sha256 is missing on the server`, { url, status: 404 });
    }
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
    if (verified && usable(ctx.mode, d, present, verified)) {
        await syncZenodo(ctx, verified, entry);
        return "cache";
    }
    if (ctx.offline) throw new OfflineError(`release ${d} is not cached and the client is offline`);
    await store.mkdirs(dir);
    let lostAttempts = 0;
    for (;;) {
        // wait for the lock, or until another process has made the release usable in this mode (spec 5.4)
        const unlock = await store.lock(dir, {
            done: async () => {
                const ready = await readVerified(store, d);
                return ready !== null && usable(ctx.mode, d, new Set(await store.list(dir)), ready);
            },
            warn: (message) => log(ctx, "warn", message),
        });
        try {
            const now = new Set(await store.list(dir));
            verified = await readVerified(store, d);
            if (verified && usable(ctx.mode, d, now, verified)) {
                await syncZenodo(ctx, verified, entry, true);
                return "cache";
            }
            const n = names(d);
            const { bytes: shaBytes, rows } = await fetchSha256(ctx, d, entry);
            requireManifestRows(d, ctx.mode, rows);
            const writes: [string, Uint8Array][] = [];
            if (ctx.mode === "stream") {
                for (const name of [n.jsonl, n.meta]) writes.push([name, await fetchChecked(ctx, name, rows, entry)]);
            } else if (rows.has(n.gz) && !rows.has(n.json)) {
                // the decoded .json must have its own row, or it is cached with no digest (CR2 DR15)
                throw new ChecksumError(`${n.json} is not listed in ${n.sha}`, { file: n.json, expected: null, actual: null });
            } else if (rows.has(n.gz)) {
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
            // .verified has a row only for each file that is present and verified in the release directory, with its
            // real size and lowercase SHA-256, and never one for the .sha256 file (spec 5.4, CR3 DR100): the rows of an
            // earlier open in the other mode while their files are there, and the files written now
            const there = new Set(await store.list(dir));
            const files: Verified["files"] = {};
            for (const [name, f] of Object.entries(verified?.files ?? {})) {
                if (name !== n.sha && f.sha256 !== null && there.has(name)) files[name] = f;
            }
            for (const [name, b] of writes) {
                const url = entry?.files.find((x) => x.name === name)?.url ?? new URL(name, ctx.baseUrl).href;
                files[name] = { sha256: (rows.get(name) as string).toLowerCase(), size: b.length, url };
            }
            const v: Verified = {
                files, verified_at: new Date().toISOString().replace(/\.\d{3}Z$/, "Z"), by: SDK_ID, datestamp: d,
                format_version: format?.format_version ?? entry?.format_version ?? verified?.format_version ?? null,
                min_reader_version: format ? format.min_reader_version : entry?.min_reader_version ?? verified?.min_reader_version ?? null,
                // a null DOI never erases a known one (CR2 DR11)
                zenodo_version_doi: entry?.zenodo_version_doi ?? verified?.zenodo_version_doi ?? null,
            };
            if (unlock?.owns && !await unlock.owns()) {
                log(ctx, "warn", `lost the release lock of ${d} before publishing .verified; waiting for its owner`);
                if (++lostAttempts >= 3) throw new CacheError(`lost the release lock of ${d} three times`, { path: store.describe(dir) });
                continue;
            }
            await store.write(`${dir}/.verified`, encodeCacheJson(v));
            return "download";
        } finally {
            await releaseLock(ctx, unlock);
        }
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
    // an entry with no DOI never erases a known one, in the session or in .verified (CR2 DR11)
    if (!store || !entry || entry.zenodo_version_doi === null) return;
    const d = entry.datestamp;
    if ((verified.datestamp ?? d) !== d || (verified.zenodo_version_doi ?? null) === entry.zenodo_version_doi) return;
    let unlock: Unlock | null = null;
    try {
        if (!held) {
            unlock = await store.lock(relDir(d), { wait: false, warn: (message) => log(ctx, "warn", message) });
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
        await store.write(`${relDir(d)}/.verified`, encodeCacheJson({ ...doc, zenodo_version_doi: entry.zenodo_version_doi }));
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
    /** Write index-v1.json. Throws when it cannot; the caller logs that. */
    writeIndex(bytes: Uint8Array): void;
    /** Delete index-v1.json (a line did not match it). Throws when it cannot; the caller logs that. */
    removeIndex(): void;
}

function sizedCacheFile(dir: SyncDir, verified: Verified, name: string): Uint8Array {
    const b = dir.read(name);
    if (!b) throw new ChecksumError(`${name} is missing from the cache`, { file: name, expected: verified.files[name]?.sha256 ?? null, actual: null });
    const want = verified.files[name]?.size;
    if (typeof want === "number" && want !== b.length) {
        throw new ChecksumError(`${name}: size ${b.length}, expected ${want}`, { file: name, expected: verified.files[name]?.sha256 ?? null, actual: null });
    }
    return b;
}

/** @internal Existing release.files projection from the pointer or authenticated receipt. */
export function cachedFileInfos(verified: Verified, pointerFiles: readonly FileInfo[] | null = null): FileInfo[] {
    const byName = (a: FileInfo, b: FileInfo) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0);
    return pointerFiles ? pointerFiles.map((f) => ({ ...f })).sort(byName) : Object.entries(verified.files)
        .map(([name, f]) => ({ name, url: f.url ?? null, size: f.size ?? null, sha256: f.sha256 ?? null }))
        .sort(byName);
}

const openedCachePayloads = new WeakMap<Release, readonly string[]>();

/** @internal The payload names actually selected when this cached release opened. */
export function openedCacheFiles(release: Release): readonly string[] | undefined {
    return openedCachePayloads.get(release);
}

/** Open a cached, verified release (spec 5.3: sizes are checked against .verified). Synchronous. */
export function loadCached(dir: SyncDir, verified: Verified, d: string, mode: Mode, warn: (message: string) => void = () => undefined,
    commercialOnly = false, pointerFiles: readonly FileInfo[] | null = null, commercialBasis: "strict" | "as_published_upstream" = "strict", historicalOffsetsPolicy: "fallback" | "exclude" = "fallback"): Release {
    const n = names(d);
    const zenodo = typeof verified.zenodo_version_doi === "string" ? verified.zenodo_version_doi : null;
    // release.files (spec 4.3.1): the pointer entry after a download of latest, else the .verified rows
    const files = cachedFileInfos(verified, pointerFiles);
    const sized = (name: string) => sizedCacheFile(dir, verified, name);
    const remember = (release: Release, payloads: readonly string[]) => {
        openedCachePayloads.set(release, Object.freeze(payloads));
        return release;
    };
    if (mode === "eager") {
        if (cachedFile(n.json, dir.size(n.json) !== null, verified)) return remember(releaseFromJson(sized(n.json), files, zenodo, warn, commercialOnly, commercialBasis, historicalOffsetsPolicy), [n.json]);
        return remember(releaseFromJsonl(sized(n.meta), sized(n.jsonl), { eager: true, files, zenodoVersionDoi: zenodo, warn, commercialOnly, commercialBasis, historicalOffsetsPolicy }), [n.jsonl, n.meta]);
    }
    const prepared = authenticateCachedStreamIndex(dir, verified, d,
        { files, zenodoVersionDoi: zenodo, commercialOnly, commercialBasis, historicalOffsetsPolicy }, warn);
    try {
        return remember(releaseFromPrepared(prepared.native_prepared_release), [n.jsonl, n.meta]);
    } catch (error) { prepared.close(); throw error; }
}

/** @internal The existing admitted index and its single owned positional reader. */
export interface PreparedStreamIndex extends StreamIndex {
    readonly meta: Uint8Array;
    readonly reader: LineReader;
    readonly close: () => void;
    readonly dropIndex: () => void;
    readonly fromSuppliedIndex: boolean;
}

/** @internal Authenticated source fields prepared before allocating the native Release brand. */
export interface AuthenticatedStreamIndex extends PreparedStreamIndex {
    readonly native_prepared_release: PreparedReleaseFields;
}

/** @internal Retry only an admitted index's initial source-hydration fault, once through the existing full pass. */
export function authenticateCachedStreamIndex(dir: SyncDir, verified: Verified, d: string,
    options: Pick<Parameters<typeof prepareReleaseFromJsonl>[2], 'files' | 'zenodoVersionDoi' | 'commercialOnly' | 'commercialBasis' | 'historicalOffsetsPolicy'>,
    warn: (message: string) => void = () => undefined, suppliedIndexBytes?: Uint8Array | null): AuthenticatedStreamIndex {
    let source = prepareCachedStreamIndex(dir, verified, d, warn, suppliedIndexBytes);
    let indexDerivedFault = false;
    const statusWarnings = new Set<string>();
    const warnStatus = (message: string) => {
        if (statusWarnings.has(message)) return;
        statusWarnings.add(message);
        warn(message);
    };
    const prepare = (current: PreparedStreamIndex): PreparedReleaseFields => prepareReleaseFromJsonl(current.meta, null, {
        ...options, eager: false, index: { entries: current.entries }, reader: current.reader, close: current.close, warn: warnStatus,
        dropIndex: () => { indexDerivedFault = true; current.dropIndex(); },
    });
    try { return { ...source, native_prepared_release: prepare(source) }; }
    catch (error) {
        source.close();
        if (!(error instanceof InvalidReleaseError) || !source.fromSuppliedIndex || !indexDerivedFault) throw error;
    }
    source = prepareCachedStreamIndex(dir, verified, d, warn, null);
    try { return { ...source, native_prepared_release: prepare(source) }; }
    catch (error) { source.close(); throw error; }
}

/** @internal Original cache index admission, deletion, one-pass rebuild and reader ownership. */
export function prepareCachedStreamIndex(dir: SyncDir, verified: Verified, d: string, warn: (message: string) => void = () => undefined,
    suppliedIndexBytes?: Uint8Array | null): PreparedStreamIndex {
    const n = names(d);
    const sized = (name: string) => sizedCacheFile(dir, verified, name);
    const meta = sized(n.meta);
    const want = verified.files[n.jsonl]?.size;
    const have = dir.size(n.jsonl);
    if (have === null || (typeof want === "number" && want !== have)) {
        throw new ChecksumError(`${n.jsonl}: size ${have}, expected ${want}`, { file: n.jsonl, expected: verified.files[n.jsonl]?.sha256 ?? null, actual: null });
    }
    const jsonlSha = verified.files[n.jsonl]?.sha256 ?? null;
    const header = headerFromMeta(meta);
    let index: StreamIndex | null = null;
    const ib = suppliedIndexBytes === undefined ? dir.read("index-v1.json") : suppliedIndexBytes;
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
    const fromSuppliedIndex = index !== null;
    const dropIndex = () => {
        try {
            dir.removeIndex();
        } catch (e) {
            warn(`cannot delete index-v1.json of ${d}: ${e instanceof Error ? e.message : String(e)}`);
        }
    };
    if (ib && !index) dropIndex();
    const lr = dir.lineReader(n.jsonl);
    try {
        let jsonl: Uint8Array | null = null;
        if (!index) {
            let bytesRead: number;
            let entries: StreamIndex["entries"];
            if (lr) {
                const scanned = scanJsonlReader(header, lr.read, () => undefined);
                // The handle may see a file changed after stat; preserve the cached size check before parse errors.
                if (scanned.bytesRead !== have) {
                    throw new ChecksumError(`${n.jsonl}: size ${scanned.bytesRead}, expected ${have}`,
                        { file: n.jsonl, expected: jsonlSha, actual: null });
                }
                if (scanned.error !== null) throw scanned.error;
                entries = scanned.entries;
                bytesRead = scanned.bytesRead;
            } else {
                jsonl = sized(n.jsonl);
                entries = indexJsonl(header, jsonl, false).entries;
                bytesRead = jsonl.length;
            }
            index = { entries };
            // .verified gives the .jsonl digest the index records; without it there is no index to write
            if (jsonlSha !== null) {
                // the index only saves work: a failure to write it is logged, not raised (spec 6.2)
                try {
                    dir.writeIndex(encodeCacheJson(storedIndex(entries, d, jsonlSha, bytesRead, SDK_ID)));
                } catch (e) {
                    warn(`cannot write index-v1.json of ${d}: ${e instanceof Error ? e.message : String(e)}`);
                }
            }
        }
        if (lr) {
            return { entries: index.entries, meta, reader: lr.read, close: lr.close, dropIndex, fromSuppliedIndex };
        }
        const bytes = jsonl ?? sized(n.jsonl);
        return { entries: index.entries, meta, reader: (o, l) => bytes.subarray(o, o + l), close: () => undefined, dropIndex, fromSuppliedIndex };
    } catch (e) {
        lr?.close();
        throw e;
    }
}

/** Read the selected cached format into a SyncDir (the browser, where storage is async). */
export async function prefetchDir(store: CacheStore, d: string, mode: Mode, warn: (message: string) => void = () => undefined, verified?: Verified): Promise<SyncDir> {
    const dir = relDir(d);
    const n = names(d);
    const present = new Set(await store.list(dir));
    // Provenance comes from the pointer or .verified, so unused cached originals need no body read.
    const selected = mode === "stream" ? [n.meta, n.jsonl, "index-v1.json"]
        : cachedFile(n.json, present.has(n.json), verified) ? [n.json] : [n.meta, n.jsonl];
    const files = new Map<string, Uint8Array>();
    for (const name of selected) {
        if (!present.has(name)) continue;
        const b = await store.read(`${dir}/${name}`);
        if (b) files.set(name, b);
    }
    return {
        read: (name) => files.get(name) ?? null,
        size: (name) => files.get(name)?.length ?? null,
        lineReader: () => null,
        writeIndex: (bytes) => void store.write(`${dir}/index-v1.json`, bytes).catch((e: unknown) => warn(`cannot write index-v1.json of ${d}: ${String(e)}`)),
        removeIndex: () => void store.remove(`${dir}/index-v1.json`).catch((e: unknown) => warn(`cannot delete index-v1.json of ${d}: ${String(e)}`)),
    };
}

/**
 * The SHA-256 values that the cached pointers (OTC_latest-f{MAJOR}.json, OTC_latest.json) give for OTC_{D}.sha256,
 * in lower case. A cached pointer that is not there, cannot be read or does not parse, names another release or
 * does not list the .sha256 gives none (CR2 DR45).
 */
async function cachedPointerSha256(ctx: Ctx, d: string): Promise<string[]> {
    const store = ctx.store;
    if (!store) return [];
    const out: string[] = [];
    for (const name of [`OTC_latest-f${Math.max(...SUPPORTED_FORMAT_MAJORS)}.json`, "OTC_latest.json"]) {
        let doc: unknown;
        try {
            const b = await store.read(`pointer/${name}`);
            if (!b) continue;
            doc = JSON.parse(dec.decode(b));
        } catch (e) {
            log(ctx, "debug", `verify: the cached ${name} cannot be used (${e instanceof Error ? e.message : String(e)})`);
            continue;
        }
        if (!isObject(doc) || !Array.isArray(doc["files"])) continue;
        for (const f of doc["files"]) {
            if (isObject(f) && f["name"] === `OTC_${d}.sha256` && typeof f["sha256"] === "string") out.push(f["sha256"].toLowerCase());
        }
    }
    return out;
}

/**
 * Hash the cached files of release D again, in full, and compare them with the cached OTC_{D}.sha256 (spec 4.3
 * verify). The files this mode loads must be there: a missing one is io (CR2 DR44); every listed data file that is
 * there is hashed. A file that does not match is deleted from the cache (spec 4.8 checksum_mismatch), so the next
 * open downloads it again. With `againstPointer` (verify), the cached OTC_{D}.sha256 must first have the SHA-256
 * that a cached pointer lists for it, when one lists it (CR2 DR45); verify fetches nothing, so a mismatch is
 * checksum_mismatch and the file stays.
 */
export async function verifyCached(ctx: Ctx, d: string, againstPointer = false,
    readHash?: (rel: string) => Promise<{ digest: string; bytesRead: number } | null>, openedFiles?: readonly string[]): Promise<true> {
    const store = ctx.store;
    if (!store) throw new OfflineError("no cache");
    const dir = relDir(d);
    const n = names(d);
    // Open authenticates only the selected payloads against their receipt; explicit verify uses the sidecar below.
    if (!againstPointer) {
        const verified = await readVerified(store, d);
        const present = new Set(await store.list(dir));
        if (!verified || !usable(ctx.mode, d, present, verified)) throw new OfflineError(`release ${d} is not cached in this mode`);
        const needed = ctx.mode === "eager" && cachedFile(n.json, present.has(n.json), verified) ? [n.json] : [n.jsonl, n.meta];
        for (const name of needed) {
            const file = store.describe(`${dir}/${name}`);
            let measured: { digest: string; bytesRead: number } | null;
            if (readHash) measured = await readHash(`${dir}/${name}`);
            else {
                const bytes = await store.read(`${dir}/${name}`);
                measured = bytes ? { digest: await ctx.platform.sha256(bytes), bytesRead: bytes.length } : null;
            }
            if (!measured) throw new FileError(`cannot read ${file}: it is missing from the cache`, { path: file });
            const row = verified.files[name];
            checkBytes(name, measured.digest, measured.bytesRead, row.sha256, row.size);
        }
        return true;
    }
    const shaBytes = await store.read(`${dir}/${n.sha}`);
    if (!shaBytes) throw new ChecksumError(`${n.sha} is missing from the cache`, { file: store.describe(`${dir}/${n.sha}`), expected: null, actual: null });
    if (againstPointer) {
        const shaFile = store.describe(`${dir}/${n.sha}`);
        const want = await cachedPointerSha256(ctx, d);
        if (want.length) {
            const actual = await ctx.platform.sha256(shaBytes);
            const expected = want.find((w) => w !== actual);
            if (expected !== undefined) {
                throw new ChecksumError(`${n.sha}: SHA-256 ${actual}, but the cached pointer lists ${expected}`, { file: shaFile, expected, actual });
            }
        }
    }
    const rows = parseSha256(shaBytes, n.sha);
    const present = new Set(await store.list(dir));
    const needed = openedFiles ?? (ctx.mode === "stream" || !present.has(n.json) ? [n.jsonl, n.meta] : [n.json]);
    let checked = 0;
    for (const name of [...new Set([...needed, ...rows.keys()])]) {
        if (name === n.sha) continue;
        const file = store.describe(`${dir}/${name}`);
        const expected = rows.get(name) ?? null;
        let actual: string | null = null;
        if (present.has(name)) {
            if (readHash) actual = (await readHash(`${dir}/${name}`))?.digest ?? null;
            else {
                const b = await store.read(`${dir}/${name}`);
                if (b) actual = await ctx.platform.sha256(b);
            }
        }
        if (actual === null) {
            if (needed.includes(name)) throw new FileError(`cannot read ${file}: it is missing from the cache`, { path: file });
            continue;
        }
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
