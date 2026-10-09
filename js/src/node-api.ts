/**
 * @internal What client.ts uses from the Node runtime (node.ts), typed without Node's own types. Code that a browser
 * reaches imports only this, so the browser typecheck (tsconfig.browser.json, no Node types) covers it (CR T64).
 * node.ts gives an object of this type; in a browser build "#node" resolves to no-node.ts, which gives null.
 */
import type { Platform } from "./platform.js";

/** The part of node:path that client.ts uses. */
export interface NodePath {
    resolve(...paths: string[]): string;
    dirname(path: string): string;
    basename(path: string): string;
    join(...paths: string[]): string;
}

export interface BlockingResult {
    ok: boolean;
    datestamp?: string;
    how?: string;
    message?: string;
    /** The SDK error code of a failure (spec 4.8), and its url, status and path when it has them. */
    code?: string;
    url?: string | null;
    status?: number | null;
    path?: string | null;
    /** A ChecksumError's expected and actual SHA-256. */
    expected?: string | null;
    actual?: string | null;
    /** The original failure (name, message, stack), so the client keeps it as the cause (CR2 DR5). */
    cause?: { name: string; message: string; stack?: string };
}

export interface NodeMod {
    nodePlatform(): Platform;
    nodePath: NodePath;
    sha256Sync(bytes: Uint8Array): string;
    gunzipSync(bytes: Uint8Array): Uint8Array;
    defaultCacheRoot(): string;
    writeAtomicSync(file: string, bytes: Uint8Array): void;
    readIfExists(file: string): Uint8Array | null;
    statSize(file: string): number | null;
    readFileOrIo(file: string): Uint8Array;
    openLineReader(file: string): { read: (offset: number, length: number) => Uint8Array; close: () => void };
    exists(p: string): boolean;
    mkdirp(dir: string): void;
    listDir(dir: string): string[];
    checkReadable(file: string): void;
    removeFileSync(file: string): void;
    removeDirSync(dir: string): void;
    /** Take `<dir>/.lock` without waiting (spec 5.4, CR2 DR3); false when another process holds a young lock. */
    tryLockSync(dir: string): boolean;
    writeAllInto(dir: string, files: readonly (readonly [string, Uint8Array])[], warn: (message: string) => void): string[];
    runBlocking(url: URL, data: unknown, timeoutMs?: number): BlockingResult;
}
