/** @internal The browser runtime: fetch, WebCrypto, DecompressionStream and Cache Storage (spec 5.4, 8.4). */
import { CacheError, NetworkError, UnsupportedError } from "./errors.js";
import type { CacheStore, HttpOptions, HttpResponse, Platform, Unlock } from "./platform.js";

const CACHE_NAME = "opentideconstants-v1";
const KEY_BASE = "https://opentideconstants-cache.invalid/v1/";

function hex(buf: ArrayBuffer): string {
    return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function copy(b: Uint8Array): Uint8Array<ArrayBuffer> {
    const out = new Uint8Array(new ArrayBuffer(b.byteLength));
    out.set(b);
    return out;
}

class BrowserCache implements CacheStore {
    readonly #name: string;

    constructor(name: string) {
        this.#name = name;
    }

    async #open(): Promise<Cache> {
        // no Cache Storage (an insecure context, an old browser) is unsupported, not a raw ReferenceError (PK10 T30)
        if (typeof caches === "undefined") throw new UnsupportedError("this browser has no Cache Storage (it needs a secure context)");
        try {
            return await caches.open(this.#name);
        } catch (e) {
            throw new CacheError(`cannot open the Cache Storage cache ${this.#name}`, { path: this.#name, cause: e });
        }
    }

    /** Run one Cache Storage step; a failure (QuotaExceededError, SecurityError) is a cache error (PK10 T30). */
    async #do<T>(rel: string, what: string, f: (c: Cache) => Promise<T>): Promise<T> {
        const c = await this.#open();
        try {
            return await f(c);
        } catch (e) {
            throw new CacheError(`cannot ${what} ${this.describe(rel)}`, { path: this.describe(rel), cause: e });
        }
    }

    describe(rel: string): string {
        return `cache-storage:${this.#name}/${rel}`;
    }

    async mkdirs(): Promise<void> {
        await this.#open();
    }

    async read(rel: string): Promise<Uint8Array | null> {
        return this.#do(rel, "read", async (c) => {
            const r = await c.match(KEY_BASE + rel);
            return r ? new Uint8Array(await r.arrayBuffer()) : null;
        });
    }

    async write(rel: string, bytes: Uint8Array): Promise<void> {
        // Cache.put replaces an entry in one step, so a reader never sees half a file.
        await this.#do(rel, "write", (c) => c.put(KEY_BASE + rel, new Response(copy(bytes))));
    }

    async remove(rel: string): Promise<void> {
        await this.#do(rel, "remove", (c) => c.delete(KEY_BASE + rel));
    }

    async removeDir(rel: string): Promise<void> {
        const prefix = KEY_BASE + rel.replace(/\/?$/, "/");
        await this.#do(rel, "remove", async (c) => {
            for (const k of await c.keys()) if (k.url.startsWith(prefix)) await c.delete(k);
        });
    }

    async list(rel: string): Promise<string[]> {
        const prefix = KEY_BASE + rel.replace(/\/?$/, "/");
        return this.#do(rel, "list", async (c) => {
            const names = new Set<string>();
            for (const k of await c.keys()) {
                if (k.url.startsWith(prefix)) {
                    const first = k.url.slice(prefix.length).split("/")[0];
                    if (first) names.add(decodeURIComponent(first));
                }
            }
            return [...names];
        });
    }

    // Cache Storage has no lock directory; every put is atomic, and duplicate work is the worst case (spec 5.4).
    async lock(): Promise<Unlock | null> {
        return async () => undefined;
    }
}

async function browserGet(url: string, o: HttpOptions): Promise<HttpResponse> {
    const ctl = new AbortController();
    const ms = (o.timeout ?? 60) * 1000;
    let timer = setTimeout(() => ctl.abort(), (o.timeout ?? 10) * 1000);
    try {
        // No request header is sent (PK12 T8): a browser sets User-Agent and Accept-Encoding itself, and
        // If-None-Match is not CORS-safelisted, so it would force a preflight; the ETag is not readable either
        // unless the server exposes it. The browser's HTTP cache makes the request conditional instead
        // ("no-cache": revalidate every time), and answers a 304 with the stored body as a 200.
        void o.headers;
        const res = await fetch(url, { signal: ctl.signal, cache: "no-cache" });
        clearTimeout(timer);
        timer = setTimeout(() => ctl.abort(), ms);
        const body = new Uint8Array(await res.arrayBuffer());
        return { status: res.status, header: (n) => res.headers.get(n), body };
    } catch (e) {
        throw new NetworkError(`request failed: ${url}`, { url, cause: e });
    } finally {
        clearTimeout(timer);
    }
}

export function browserPlatform(): Platform {
    return {
        name: "browser",
        sha256: async (b) => hex(await crypto.subtle.digest("SHA-256", copy(b))),
        async gunzip(b) {
            // no DecompressionStream is a missing feature, not a corrupt file (PK10 T31)
            if (typeof DecompressionStream === "undefined") throw new UnsupportedError("this browser has no DecompressionStream for .json.gz");
            const stream = new Blob([copy(b)]).stream().pipeThrough(new DecompressionStream("gzip"));
            return new Uint8Array(await new Response(stream).arrayBuffer());
        },
        get: browserGet,
        cache: async (root) => new BrowserCache(root ?? CACHE_NAME),
        env: () => null,
        sleep: (s) => new Promise((r) => setTimeout(r, s * 1000)),
    };
}
