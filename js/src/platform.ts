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

/** A cache directory tree (spec 5.4), with paths relative to `<root>/v1`. */
export interface CacheStore {
    /** The absolute path of a cache entry (Node), or a label. */
    describe(rel: string): string;
    mkdirs(rel: string): Promise<void>;
    read(rel: string): Promise<Uint8Array | null>;
    /** Write to a temporary file in the same directory, fsync, rename into place. */
    write(rel: string, bytes: Uint8Array): Promise<void>;
    remove(rel: string): Promise<void>;
    removeDir(rel: string): Promise<void>;
    list(rel: string): Promise<string[]>;
    /** Take the lock directory `<rel>/.lock`; the result releases it. Resolves early if `<rel>/.verified` appears. */
    lock(rel: string): Promise<() => Promise<void>>;
}

export interface Platform {
    readonly name: "node" | "browser";
    sha256(bytes: Uint8Array): Promise<string>;
    gunzip(bytes: Uint8Array): Promise<Uint8Array>;
    /** One HTTP GET. Transport failures (DNS, connection, timeout, a short body) throw NetworkError. */
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
