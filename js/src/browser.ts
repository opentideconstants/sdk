/** @internal The browser runtime: fetch, WebCrypto, DecompressionStream and Cache Storage (spec 5.4, 8.4). */
import { NetworkError } from "./errors.js";
import type { CacheStore, HttpOptions, HttpResponse, Platform } from "./platform.js";

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

    #open(): Promise<Cache> {
        return caches.open(this.#name);
    }

    describe(rel: string): string {
        return `cache-storage:${this.#name}/${rel}`;
    }

    async mkdirs(): Promise<void> {
        await this.#open();
    }

    async read(rel: string): Promise<Uint8Array | null> {
        const r = await (await this.#open()).match(KEY_BASE + rel);
        return r ? new Uint8Array(await r.arrayBuffer()) : null;
    }

    async write(rel: string, bytes: Uint8Array): Promise<void> {
        // Cache.put replaces an entry in one step, so a reader never sees half a file.
        await (await this.#open()).put(KEY_BASE + rel, new Response(copy(bytes)));
    }

    async remove(rel: string): Promise<void> {
        await (await this.#open()).delete(KEY_BASE + rel);
    }

    async removeDir(rel: string): Promise<void> {
        const c = await this.#open();
        const prefix = KEY_BASE + rel.replace(/\/?$/, "/");
        for (const k of await c.keys()) if (k.url.startsWith(prefix)) await c.delete(k);
    }

    async list(rel: string): Promise<string[]> {
        const c = await this.#open();
        const prefix = KEY_BASE + rel.replace(/\/?$/, "/");
        const names = new Set<string>();
        for (const k of await c.keys()) {
            if (k.url.startsWith(prefix)) {
                const first = k.url.slice(prefix.length).split("/")[0];
                if (first) names.add(decodeURIComponent(first));
            }
        }
        return [...names];
    }

    async lock(): Promise<() => Promise<void>> {
        return async () => undefined;
    }
}

async function browserGet(url: string, o: HttpOptions): Promise<HttpResponse> {
    const ctl = new AbortController();
    const ms = (o.timeout ?? 60) * 1000;
    let timer = setTimeout(() => ctl.abort(), (o.timeout ?? 10) * 1000);
    try {
        // A browser sets User-Agent and Accept-Encoding itself; only If-None-Match is sent (CORS-safe).
        const headers: Record<string, string> = {};
        for (const [k, v] of Object.entries(o.headers)) if (k.toLowerCase() === "if-none-match") headers[k] = v;
        const res = await fetch(url, { headers, signal: ctl.signal, cache: "no-store" });
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
            const stream = new Blob([copy(b)]).stream().pipeThrough(new DecompressionStream("gzip"));
            return new Uint8Array(await new Response(stream).arrayBuffer());
        },
        get: browserGet,
        cache: async (root) => new BrowserCache(root ?? CACHE_NAME),
        env: () => null,
        sleep: (s) => new Promise((r) => setTimeout(r, s * 1000)),
    };
}
