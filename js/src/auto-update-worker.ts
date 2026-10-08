/** @internal The automatic update check, run by node.runBlocking (spec 5.6). */
import { workerData } from "node:worker_threads";
import type { MessagePort } from "node:worker_threads";
import { ensureRelease, getPointer, type Ctx } from "./core.js";
import { nodePlatform } from "./node.js";
import type { Mode } from "./types.js";

interface Data {
    baseUrl: string;
    cacheRoot: string | null;
    timeout: number | null;
    proxy: string | null;
    caFile: string | null;
    userAgent: string;
    mode: Mode;
    offline: boolean;
}

const { port, sab, data } = workerData as { port: MessagePort; sab: SharedArrayBuffer; data: Data };
const flag = new Int32Array(sab);
let result: { ok: boolean; datestamp?: string; how?: string; message?: string };
try {
    const platform = nodePlatform();
    const ctx: Ctx = {
        platform, store: await platform.cache(data.cacheRoot), baseUrl: data.baseUrl, offline: data.offline,
        timeout: data.timeout, proxy: data.proxy, caFile: data.caFile, userAgent: data.userAgent,
        onNetworkError: "raise", logger: null, mode: data.mode,
    };
    const entry = await getPointer(ctx);
    const how = await ensureRelease(ctx, entry.datestamp, entry);
    result = { ok: true, datestamp: entry.datestamp, how };
} catch (e) {
    result = { ok: false, message: e instanceof Error ? e.message : String(e) };
}
port.postMessage(result);
Atomics.store(flag, 0, 1);
Atomics.notify(flag, 0);
