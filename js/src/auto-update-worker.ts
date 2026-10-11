/** @internal The automatic update check, run by node.runBlocking (spec 5.6). */
import { workerData } from "node:worker_threads";
import type { MessagePort } from "node:worker_threads";
import { ensureRelease, getPointer, type Ctx } from "./core.js";
import { ChecksumError, FileError, NetworkError, OpenTideConstantsError } from "./errors.js";
import { nodePlatform, type BlockingResult } from "./node.js";
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

const { port, data } = workerData as { port: MessagePort; data: Data };
let result: BlockingResult;
try {
    const platform = nodePlatform();
    const ctx: Ctx = {
        platform, store: await platform.cache(data.cacheRoot), baseUrl: data.baseUrl, offline: data.offline,
        timeout: data.timeout, proxy: data.proxy, caFile: data.caFile, userAgent: data.userAgent,
        onNetworkError: "raise", logger: null, mode: data.mode,
        commercialOnly: false,   // the check downloads only; the client loads the release with its own option
    };
    if (ctx.offline) throw new Error("offline: the automatic update check does not run");
    const entry = await getPointer(ctx);
    const how = await ensureRelease(ctx, entry.datestamp, entry);
    result = { ok: true, datestamp: entry.datestamp, how, files: entry.files };
} catch (e) {
    result = { ok: false, message: e instanceof Error ? e.message : String(e) };
    if (e instanceof OpenTideConstantsError) {
        result.code = e.code;
        if (e instanceof NetworkError) Object.assign(result, { url: e.url, status: e.status });
        if (e instanceof FileError) result.path = e.path;
        if (e instanceof ChecksumError) Object.assign(result, { path: e.file, expected: e.expected, actual: e.actual });
    }
    // the original failure goes with the result, so the client keeps it as the cause (CR2 DR5)
    const c = e instanceof OpenTideConstantsError && e.cause instanceof Error ? e.cause : e;
    if (c instanceof Error) result.cause = { name: c.name, message: c.message, stack: c.stack };
}
// the bootstrap (node.runBlocking) wakes the caller when this module has finished
port.postMessage(result);
