/** @internal What the SDK needs from its runtime: Node (node.ts) or a browser (browser.ts). */

export interface HttpResponse {
    status: number;
    header(name: string): string | null;
    body: Uint8Array;
}

export interface HttpOptions {
    headers: Record<string, string>;
    /** Seconds; null = connect 10 s, read 60 s. */
    timeout: number | null;
    proxy: string | null;
    caFile: string | null;
}

/** Releases a lock. */
export type Unlock = () => Promise<void>;

export interface LockOptions {
    /** True when the work the lock guards is done (spec 5.4: stop waiting when `.verified` appears). */
    done?: () => Promise<boolean>;
    /** False: do not wait for a held lock (resolve null). Default true. */
    wait?: boolean;
}

/** A cache directory tree (spec 5.4), with paths relative to `<root>/v1`. */
export interface CacheStore {
    /** The absolute path of a cache entry (Node), or a label. */
    describe(rel: string): string;
    mkdirs(rel: string): Promise<void>;
    read(rel: string): Promise<Uint8Array | null>;
    /**
     * Replace an entry in one step, so a reader never sees half of it: on Node a temporary file in the same
     * directory, fsync, rename (spec 5.4); in a browser one Cache Storage put. A failure is CacheError.
     */
    write(rel: string, bytes: Uint8Array): Promise<void>;
    remove(rel: string): Promise<void>;
    removeDir(rel: string): Promise<void>;
    list(rel: string): Promise<string[]>;
    /**
     * Take the lock directory `<rel>/.lock` (spec 5.4 Locks); the result releases it, only if this process still owns
     * it. While it waits, it calls `options.done` every 500 ms and resolves with a no-op release when that returns
     * true (another process finished the work). With `options.wait` false it resolves null at once when the lock is
     * held. A lock it cannot take or a stale lock it cannot remove (3 attempts) is CacheError.
     */
    lock(rel: string, options?: LockOptions): Promise<Unlock | null>;
}

export interface Platform {
    readonly name: "node" | "browser";
    sha256(bytes: Uint8Array): Promise<string>;
    gunzip(bytes: Uint8Array): Promise<Uint8Array>;
    /**
     * One HTTP GET, following redirects (spec 5.7). Transport failures (DNS, connection, timeout, a short body, a
     * refused redirect) throw NetworkError. Node also throws InvalidArgumentError for a proxy that is not a URL and
     * FileError for a CA file it cannot read. A browser sends no request headers (CORS) and uses its own cache.
     */
    get(url: string, options: HttpOptions): Promise<HttpResponse>;
    /** The cache store for a root (null = the platform default). */
    cache(root: string | null): Promise<CacheStore>;
    /** An environment variable, or null (always null in a browser). */
    env(name: string): string | null;
    sleep(seconds: number): Promise<void>;
}

/** @internal True when running on Node (not in a browser). */
export function isNode(): boolean {
    const p = (globalThis as { process?: { versions?: { node?: string } } }).process;
    return typeof p === "object" && p !== null && typeof p.versions?.node === "string";
}
