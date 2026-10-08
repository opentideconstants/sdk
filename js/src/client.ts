import {
    checkDatestamp, compareDatestamps, DEFAULT_BASE_URL, USER_AGENT,
} from "./constants.js";
import {
    cachedDatestamps, cachedIndex, ensureRelease, fetchChecked, fetchSha256, getIndex, getPointer, loadCached, log,
    newestCached, prefetchDir, readVerified, relDir, releaseNames, verifyCached, checkBytes,
    type Ctx, type PointerEntry, type SyncDir, type Verified,
} from "./core.js";
import {
    ChecksumError, FileError, FileExistsError, InvalidArgumentError, InvalidReleaseError, NetworkError, OfflineError,
    OpenTideConstantsError, PinnedReleaseError, ReleaseNotFoundError, UnsupportedError,
} from "./errors.js";
import { parseSha256, releaseFromJson, releaseFromJsonl, splitReleaseName } from "./loader.js";
import { isNode, type Platform } from "./platform.js";
import type { ConstantSet, Release, Station } from "./release.js";
import type {
    DownloadOptions, Format, LoadedFrom, Mode, NearOptions, NearestOptions, Nearby, OnNetworkError, OpenOptions,
    PruneOptions, ReleaseInfo, SearchOptions, StationFilters, Tombstone, UpdateResult,
} from "./types.js";

type NodeMod = typeof import("./node.js");

const FORMATS: readonly Format[] = ["json", "json.gz", "jsonl"];
const dec = new TextDecoder();

function toInfo(e: PointerEntry): ReleaseInfo {
    return Object.freeze({
        datestamp: e.datestamp, format_version: e.format_version, doi: e.doi,
        files: Object.freeze(e.files.map((f) => Object.freeze({ ...f }))),
    });
}

function optBool(v: unknown, name: string): boolean | null {
    if (v === undefined || v === null) return null;
    if (typeof v !== "boolean") throw new InvalidArgumentError(`${name} must be a boolean`);
    return v;
}

function optNum(v: unknown, name: string): number | null {
    if (v === undefined || v === null) return null;
    if (typeof v !== "number" || !Number.isFinite(v) || v < 0) throw new InvalidArgumentError(`${name} must be a non-negative number`);
    return v;
}

function optStr(v: unknown, name: string): string | null {
    if (v === undefined || v === null) return null;
    if (typeof v !== "string") throw new InvalidArgumentError(`${name} must be a string`);
    return v;
}

interface FileSource {
    path: string;
    dataPaths: string[];
    shaPath: string | null;
}

/** A Node SyncDir over a cache release directory. */
function nodeDir(node: NodeMod, dir: string): SyncDir {
    const p = (name: string) => node.nodePath.join(dir, name);
    return {
        read: (name) => node.readIfExists(p(name)),
        size: (name) => node.statSize(p(name)),
        lineReader: (name) => node.openLineReader(p(name)),
        writeIndex: (bytes) => {
            try { node.writeAtomicSync(p("index-v1.json"), bytes); } catch { /* the index is rebuilt next time */ }
        },
    };
}

/**
 * The OpenTideConstants client: options, the cache, HTTP and the current Release (spec 3, 4.2).
 *
 * ```ts
 * const otc = await OpenTideConstants.open();
 * otc.stationByAlias("noaa", "9414290")?.recommendedSet?.constituent("M2")?.amplitude_m;
 * ```
 */
export class OpenTideConstants {
    #ctx: Ctx;
    #node: NodeMod | null;
    #release: Release;
    #loadedFrom: LoadedFrom;
    #lastError: OpenTideConstantsError | null;
    #pinned: boolean;
    #file: FileSource | null;
    #cacheRoot: string | null;
    #autoUpdate: boolean;
    #interval: number;
    #lastCheck: number;
    #all: Release[];

    private constructor(ctx: Ctx, node: NodeMod | null, release: Release, loadedFrom: LoadedFrom, extra: {
        lastError: OpenTideConstantsError | null; pinned: boolean; file: FileSource | null; cacheRoot: string | null;
        autoUpdate: boolean; interval: number;
    }) {
        this.#ctx = ctx;
        this.#node = node;
        this.#release = release;
        this.#loadedFrom = loadedFrom;
        this.#lastError = extra.lastError;
        this.#pinned = extra.pinned;
        this.#file = extra.file;
        this.#cacheRoot = extra.cacheRoot;
        this.#autoUpdate = extra.autoUpdate;
        this.#interval = extra.interval;
        this.#lastCheck = Date.now();
        this.#all = [release];
    }

    /** Open a release: the latest (default), a pinned datestamp, or a local file (Node). Spec 4.2, 5.2. */
    static async open(options: OpenOptions = {}): Promise<OpenTideConstants> {
        if (options === null || typeof options !== "object") throw new InvalidArgumentError("options must be an object");
        const release = options.release ?? "latest";
        if (release !== "latest") checkDatestamp(release);
        const mode: Mode = options.mode ?? "eager";
        if (mode !== "eager" && mode !== "stream") throw new InvalidArgumentError(`mode must be "eager" or "stream"; got ${JSON.stringify(mode)}`);
        const onNetworkError: OnNetworkError = options.onNetworkError ?? "use_cache";
        if (onNetworkError !== "use_cache" && onNetworkError !== "raise") throw new InvalidArgumentError(`onNetworkError must be "use_cache" or "raise"`);
        const timeout = optNum(options.timeout, "timeout");
        const autoUpdate = optBool(options.autoUpdate, "autoUpdate") ?? false;
        const interval = optNum(options.updateInterval, "updateInterval") ?? 86_400;
        const verifyOnOpen = optBool(options.verifyOnOpen, "verifyOnOpen") ?? false;
        const file = optStr(options.file, "file");
        const suffix = optStr(options.userAgent, "userAgent");

        const node = isNode() ? await import("./node.js") : null;
        const platform: Platform = node ? node.nodePlatform() : (await import("./browser.js")).browserPlatform();
        if (!node && (file !== null || options.cacheDir)) throw new UnsupportedError("file and cacheDir need a file system (Node)");
        if (!node && autoUpdate) throw new UnsupportedError("autoUpdate needs Node (a browser cannot block for the check)");
        const offline = optBool(options.offline, "offline") ?? platform.env("OPENTIDECONSTANTS_OFFLINE") === "1";
        let baseUrl = optStr(options.baseUrl, "baseUrl") ?? platform.env("OPENTIDECONSTANTS_BASE_URL") ?? DEFAULT_BASE_URL;
        if (!baseUrl.endsWith("/")) baseUrl += "/";
        const cacheRoot = node ? optStr(options.cacheDir, "cacheDir") ?? platform.env("OPENTIDECONSTANTS_CACHE_DIR") ?? node.defaultCacheRoot() : null;
        const ctx: Ctx = {
            platform, store: await platform.cache(cacheRoot), baseUrl, offline, timeout,
            proxy: optStr(options.proxy, "proxy"), caFile: optStr(options.caFile, "caFile"),
            userAgent: suffix ? `${USER_AGENT} ${suffix}` : USER_AGENT,
            onNetworkError, logger: options.logger ?? null, mode,
        };
        const extra = { lastError: null as OpenTideConstantsError | null, pinned: release !== "latest", file: null as FileSource | null, cacheRoot, autoUpdate, interval };

        if (file !== null && node) {
            const { rel, from, src } = OpenTideConstants.#openFile(node, file, mode);
            return new OpenTideConstants(ctx, node, rel, from, { ...extra, pinned: true, file: src });
        }
        const store = ctx.store;
        if (!store) throw new OfflineError("no cache");
        await store.mkdirs("releases");
        await store.mkdirs("pointer");

        let d: string;
        let from: LoadedFrom;
        if (release !== "latest") {
            from = await ensureRelease(ctx, release, null);
            d = release;
        } else if (offline) {
            const c = await newestCached(ctx);
            if (!c) throw new OfflineError("offline and no release is cached");
            d = c;
            from = "cache";
        } else {
            try {
                const entry = await getPointer(ctx);
                from = await ensureRelease(ctx, entry.datestamp, entry);
                d = entry.datestamp;
            } catch (e) {
                const c = e instanceof NetworkError && onNetworkError === "use_cache" ? await newestCached(ctx) : null;
                if (!c) throw e;
                log(ctx, "warn", `network error (${e instanceof Error ? e.message : String(e)}); using cached release ${c}`);
                d = c;
                from = "cache_after_error";
                extra.lastError = e as NetworkError;
            }
        }
        const rel = await OpenTideConstants.#loadStored(ctx, node, d);
        if (verifyOnOpen) await verifyCached(ctx, d);
        return new OpenTideConstants(ctx, node, rel, from, extra);
    }

    static async #loadStored(ctx: Ctx, node: NodeMod | null, d: string): Promise<Release> {
        const store = ctx.store;
        if (!store) throw new OfflineError("no cache");
        const v = await readVerified(store, d);
        if (!v) throw new ChecksumError(`release ${d} is not verified in the cache`, { file: store.describe(`${relDir(d)}/.verified`), expected: null, actual: null });
        const dir = node ? nodeDir(node, store.describe(relDir(d))) : await prefetchDir(store, d);
        return loadCached(dir, v, d, ctx.mode);
    }

    /** Open a local file (spec 4.2, 4.3.1). */
    static #openFile(node: NodeMod, file: string, mode: Mode): { rel: Release; from: LoadedFrom; src: FileSource } {
        const path = node.nodePath;
        const full = path.resolve(file);
        if (!node.exists(full)) throw new FileError(`cannot open ${full}: no such file`, { path: full });
        const dir = path.dirname(full);
        const name = path.basename(full);
        const kind = name.endsWith(".json.gz") ? "json.gz" : name.endsWith(".jsonl") ? "jsonl" : name.endsWith(".json") ? "json" : null;
        if (!kind) throw new InvalidArgumentError(`file must be a .json, .json.gz or .jsonl file; got ${name}`);
        const stem = name.slice(0, name.length - (kind === "json.gz" ? 8 : kind === "jsonl" ? 6 : 5));
        const dataNames = kind === "jsonl" ? [name, `${stem}.meta.json`] : [name];
        const parts = splitReleaseName(name);
        const shaPath = parts ? path.join(dir, `OTC_${parts.datestamp}.sha256`) : null;
        const bytes = new Map<string, Uint8Array>();
        for (const n of dataNames) bytes.set(n, node.readFileOrIo(path.join(dir, n)));
        const shaBytes = shaPath ? node.readIfExists(shaPath) : null;
        let files;
        let from: LoadedFrom;
        if (shaBytes) {
            const rows = parseSha256(dec.decode(shaBytes));
            for (const [n, b] of bytes) checkBytes(n, node.sha256Sync(b), b.length, rows.get(n) ?? null, null);
            files = [...rows].map(([n, sha]) => ({ name: n, url: null, size: node.statSize(path.join(dir, n)), sha256: sha }));
            from = "file";
        } else {
            files = dataNames.map((n) => ({ name: n, url: null, size: node.statSize(path.join(dir, n)), sha256: null }));
            from = "file_unverified";
        }
        files.sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));
        const data = bytes.get(name) as Uint8Array;
        let rel: Release;
        if (kind === "jsonl") {
            const meta = bytes.get(`${stem}.meta.json`) as Uint8Array;
            if (mode === "stream") {
                const lr = node.openLineReader(full);
                try {
                    rel = releaseFromJsonl(meta, data, { eager: false, files, reader: lr.read, close: lr.close });
                } catch (e) {
                    lr.close();
                    throw e;
                }
            } else {
                rel = releaseFromJsonl(meta, data, { eager: true, files });
            }
        } else {
            let json = data;
            if (kind === "json.gz") {
                try {
                    json = node.gunzipSync(data);
                } catch (e) {
                    throw new InvalidReleaseError(`${name} does not decompress`, { cause: e });
                }
            }
            rel = releaseFromJson(json, files);
        }
        return { rel, from, src: { path: full, dataPaths: dataNames.map((n) => path.join(dir, n)), shaPath: shaBytes ? shaPath : null } };
    }

    // ------------------------------------------------------------------ automatic update (spec 5.6)

    #current(): Release {
        if (this.#autoUpdate && !this.#pinned && this.#node && Date.now() - this.#lastCheck >= this.#interval * 1000) {
            this.#lastCheck = Date.now();
            this.#autoUpdateNow(this.#node);
        }
        return this.#release;
    }

    #autoUpdateNow(node: NodeMod): void {
        const ctx = this.#ctx;
        const res = node.runBlocking(new URL("./auto-update-worker.js", import.meta.url), {
            baseUrl: ctx.baseUrl, cacheRoot: this.#cacheRoot, timeout: ctx.timeout, proxy: ctx.proxy, caFile: ctx.caFile,
            userAgent: ctx.userAgent, mode: ctx.mode, offline: ctx.offline,
        });
        if (!res.ok || typeof res.datestamp !== "string") {
            log(ctx, "warn", `automatic update check failed: ${res.message ?? "unknown error"}`);
            return;
        }
        const from = this.#release.datestamp;
        if (compareDatestamps(res.datestamp, from) <= 0) return;
        const store = ctx.store;
        if (!store) return;
        try {
            const vb = node.readIfExists(node.nodePath.join(store.describe(relDir(res.datestamp)), ".verified"));
            if (!vb) return;
            const v = JSON.parse(dec.decode(vb)) as Verified;
            const rel = loadCached(nodeDir(node, store.describe(relDir(res.datestamp))), v, res.datestamp, ctx.mode);
            this.#swap(rel, res.how === "download" ? "download" : "cache");
            log(ctx, "info", `updated from ${from} to ${res.datestamp}`);
        } catch (e) {
            log(ctx, "warn", `automatic update failed: ${e instanceof Error ? e.message : String(e)}`);
        }
    }

    #swap(rel: Release, from: LoadedFrom): void {
        this.#release = rel;
        this.#loadedFrom = from;
        this.#lastError = null;
        this.#all.push(rel);
    }

    // ------------------------------------------------------------------ release management (spec 4.3)

    /** The loaded release. */
    get release(): Release {
        return this.#current();
    }

    /** Where the loaded release came from. */
    get loadedFrom(): LoadedFrom {
        return this.#loadedFrom;
    }

    /** The error that made the client fall back to the cache, or null. */
    get lastError(): OpenTideConstantsError | null {
        return this.#lastError;
    }

    /** Every release from OTC_index.json, newest first. */
    async releases(): Promise<readonly ReleaseInfo[]> {
        if (this.#ctx.offline) {
            const idx = await cachedIndex(this.#ctx);
            if (!idx) throw new OfflineError("offline and the release index is not cached");
            return Object.freeze(idx.map(toInfo));
        }
        return Object.freeze((await getIndex(this.#ctx)).map(toInfo));
    }

    /** The latest release (one conditional GET of the pointer). It does not switch to it. */
    async latest(): Promise<ReleaseInfo> {
        if (this.#ctx.offline) throw new OfflineError("offline: latest needs the network");
        return toInfo(await getPointer(this.#ctx));
    }

    /** A release newer than the loaded one, or null. */
    async checkForUpdate(): Promise<ReleaseInfo | null> {
        const info = await this.latest();
        return compareDatestamps(info.datestamp, this.#release.datestamp) > 0 ? info : null;
    }

    /** Download and switch to a newer release. A Release held from before keeps showing the old one. */
    async update(): Promise<UpdateResult> {
        if (this.#pinned) throw new PinnedReleaseError(this.#file ? "the client was opened on a file" : "the client was opened on a pinned release");
        const from = this.#release.datestamp;
        const entry = await getPointer(this.#ctx);
        if (compareDatestamps(entry.datestamp, from) <= 0) return Object.freeze({ updated: false, from, to: from });
        const how = await ensureRelease(this.#ctx, entry.datestamp, entry);
        this.#swap(await OpenTideConstants.#loadStored(this.#ctx, this.#node, entry.datestamp), how);
        log(this.#ctx, "info", `updated from ${from} to ${entry.datestamp}`);
        return Object.freeze({ updated: true, from, to: entry.datestamp });
    }

    /** Write a release into a folder the caller chooses (Node only; spec 4.3.2). Returns the paths written. */
    async download(options: DownloadOptions): Promise<readonly string[]> {
        const node = this.#node;
        if (!node) throw new UnsupportedError("download needs a file system (Node)");
        if (options === null || typeof options !== "object") throw new InvalidArgumentError("download needs an options object with to");
        const to = optStr(options.to, "to");
        if (!to) throw new InvalidArgumentError("to is required");
        const release = options.release ?? "latest";
        if (release !== "latest") checkDatestamp(release);
        const formats = options.formats ?? ["jsonl"];
        if (!Array.isArray(formats) || formats.some((f) => !FORMATS.includes(f))) {
            throw new InvalidArgumentError(`formats must be a list of ${FORMATS.join(", ")}`);
        }
        const overwrite = optBool(options.overwrite, "overwrite") ?? false;
        const ctx = this.#ctx;
        const store = ctx.store;
        if (!store) throw new OfflineError("no cache");

        let d: string;
        let entry: PointerEntry | null = null;
        if (release !== "latest") d = release;
        else if (ctx.offline) {
            const c = (await cachedDatestamps(store))[0];
            if (!c) throw new OfflineError("offline and no release is cached");
            d = c;
        } else {
            entry = await getPointer(ctx);
            d = entry.datestamp;
        }
        const n = releaseNames(d);
        const cdir = store.describe(relDir(d));
        const verified = await readVerified(store, d);
        let shaBytes = verified ? node.readIfExists(node.nodePath.join(cdir, n.sha)) : null;
        let rows: Map<string, string>;
        if (shaBytes) rows = parseSha256(dec.decode(shaBytes));
        else {
            if (ctx.offline) throw new OfflineError(`release ${d} is not cached and the client is offline`);
            ({ bytes: shaBytes, rows } = await fetchSha256(ctx, d, entry));
        }
        const wanted = [...new Set(formats.map((f) => (f === "json" ? n.json : f === "json.gz" ? n.gz : n.jsonl)))];
        wanted.push(n.meta);
        for (const w of wanted) if (!rows.has(w)) throw new ReleaseNotFoundError(`${w} is not part of release ${d}`);
        wanted.push(n.sha);
        node.mkdirp(to);
        const expected = (name: string) => (name === n.sha ? node.sha256Sync(shaBytes as Uint8Array) : rows.get(name) ?? null);
        const todo: string[] = [];
        for (const name of wanted) {
            const existing = node.readIfExists(node.nodePath.join(to, name));
            if (existing === null) todo.push(name);
            else if (node.sha256Sync(existing) !== expected(name)) {
                if (!overwrite) throw new FileExistsError(node.nodePath.join(to, name));
                todo.push(name);
            }
        }
        const data = new Map<string, Uint8Array>();
        for (const name of todo) {
            if (name === n.sha) continue;
            const cached = verified ? node.readIfExists(node.nodePath.join(cdir, name)) : null;
            if (cached && node.sha256Sync(cached) === rows.get(name)) {
                data.set(name, cached);
                continue;
            }
            if (ctx.offline) throw new OfflineError(`${name} is not cached and the client is offline`);
            data.set(name, await fetchChecked(ctx, name, rows, entry));
        }
        const written: string[] = [];
        for (const name of todo) if (name !== n.sha) written.push(node.writeInto(to, name, data.get(name) as Uint8Array));
        if (todo.includes(n.sha)) written.push(node.writeInto(to, n.sha, shaBytes as Uint8Array));
        return Object.freeze(written);
    }

    /** Hash the release files again and compare them with OTC_{D}.sha256 (spec 4.3). */
    async verify(): Promise<true> {
        const f = this.#file;
        if (f && this.#node) {
            const node = this.#node;
            if (!f.shaPath) throw new ChecksumError("no OTC_{D}.sha256 next to the file", { file: f.path, expected: null, actual: null });
            const rows = parseSha256(dec.decode(node.readFileOrIo(f.shaPath)));
            for (const p of f.dataPaths) {
                const actual = node.sha256Sync(node.readFileOrIo(p));
                const exp = rows.get(node.nodePath.basename(p)) ?? null;
                if (actual !== exp) throw new ChecksumError(`${p}: SHA-256 ${actual}, expected ${exp}`, { file: p, expected: exp, actual });
            }
            return true;
        }
        return verifyCached(this.#ctx, this.#release.datestamp);
    }

    /** The cached, verified datestamps, newest first (Node only). */
    cachedReleases(): readonly string[] {
        const node = this.#node;
        const store = this.#ctx.store;
        if (!node || !store) throw new UnsupportedError("cachedReleases needs a file system (Node)");
        const dir = store.describe("releases");
        return Object.freeze(node.listDir(dir)
            .filter((d) => node.exists(node.nodePath.join(dir, d, ".verified")))
            .sort((a, b) => compareDatestamps(b, a)));
    }

    /** Remove cached releases, keeping the newest `keep` and the loaded one. Returns the datestamps removed. */
    prune(options: PruneOptions = {}): readonly string[] {
        const keep = options.keep ?? 3;
        if (typeof keep !== "number" || !Number.isInteger(keep) || keep < 0) throw new InvalidArgumentError("keep must be a non-negative integer");
        const node = this.#node;
        const store = this.#ctx.store;
        if (!node || !store) throw new UnsupportedError("prune needs a file system (Node)");
        const all = this.cachedReleases();
        const loaded = this.#file ? null : this.#release.datestamp;
        const removed = all.slice(keep).filter((d) => d !== loaded);
        for (const d of removed) node.removeDirSync(store.describe(relDir(d)));
        return Object.freeze(removed);
    }

    /** Close the client and every release it loaded (stream mode holds a file handle). */
    close(): void {
        for (const r of this.#all) r._close();
    }

    [Symbol.dispose](): void {
        this.close();
    }

    async [Symbol.asyncDispose](): Promise<void> {
        this.close();
    }

    // ------------------------------------------------------------------ queries, forwarded to the current release

    station(stationId: string): Station | null {
        return this.#current().station(stationId);
    }

    requireStation(stationId: string): Station {
        return this.#current().requireStation(stationId);
    }

    tombstone(stationId: string): Tombstone | null {
        return this.#current().tombstone(stationId);
    }

    stationByAlias(system: string, aliasId: string): Station | null {
        return this.#current().stationByAlias(system, aliasId);
    }

    stations(filters: StationFilters = {}): readonly Station[] {
        return this.#current().stations(filters);
    }

    iterStations(filters: StationFilters = {}): Generator<Station, void, undefined> {
        return this.#current().iterStations(filters);
    }

    search(options: SearchOptions): readonly Station[] {
        return this.#current().search(options);
    }

    near(options: NearOptions): readonly Nearby<Station>[] {
        return this.#current().near(options);
    }

    nearest(options: NearestOptions): Nearby<Station> | null {
        return this.#current().nearest(options);
    }

    referenceStation(station: Station): Station | null {
        return this.#current().referenceStation(station);
    }

    subordinatesOf(station: Station): readonly Station[] {
        return this.#current().subordinatesOf(station);
    }

    attribution(stations?: readonly (Station | null)[] | null): string {
        return this.#current().attribution(stations);
    }
}

export type { ConstantSet };
