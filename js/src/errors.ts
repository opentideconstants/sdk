/**
 * SDK errors (spec 4.8). Every error class is a direct subclass of {@link OpenTideConstantsError}
 * and of nothing else, and every error has a stable string `code`. A system error that causes an
 * SDK error is kept as `cause`.
 */

export type ErrorCode =
    | "network"
    | "release_not_found"
    | "offline_unavailable"
    | "checksum_mismatch"
    | "unsupported_format"
    | "invalid_release"
    | "station_not_found"
    | "station_removed"
    | "pinned_release"
    | "cache"
    | "file_exists"
    | "unsupported"
    | "io"
    | "invalid_argument";

interface CauseOption {
    cause?: unknown;
}

/** The base class of every SDK error. */
export class OpenTideConstantsError extends Error {
    /** The stable error code (spec 4.8). */
    readonly code: ErrorCode;

    constructor(code: ErrorCode, message: string, options?: CauseOption) {
        super(message, options && options.cause !== undefined ? { cause: options.cause } : undefined);
        this.code = code;
        this.name = new.target.name;
    }
}

/** DNS, TLS, connection or timeout failure, or an HTTP 5xx after the retries. */
export class NetworkError extends OpenTideConstantsError {
    readonly url: string | null;
    readonly status: number | null;

    constructor(message: string, detail: { url?: string | null; status?: number | null } & CauseOption = {}) {
        super("network", message, detail);
        this.url = detail.url ?? null;
        this.status = detail.status ?? null;
    }
}

/** HTTP 404 for a pinned datestamp. */
export class ReleaseNotFoundError extends OpenTideConstantsError {
    constructor(message: string, options?: CauseOption) {
        super("release_not_found", message, options);
    }
}

/** Offline (or no network allowed) and the release is not cached. */
export class OfflineError extends OpenTideConstantsError {
    constructor(message: string, options?: CauseOption) {
        super("offline_unavailable", message, options);
    }
}

/** A SHA-256 or size does not match, or the pointer and the `.sha256` file disagree. */
export class ChecksumError extends OpenTideConstantsError {
    readonly file: string;
    readonly expected: string | null;
    readonly actual: string | null;

    constructor(message: string, detail: { file: string; expected: string | null; actual: string | null } & CauseOption) {
        super("checksum_mismatch", message, detail);
        this.file = detail.file;
        this.expected = detail.expected;
        this.actual = detail.actual;
    }
}

/** The file's `format_version` major is not supported (spec 7.4). */
export class UnsupportedFormatError extends OpenTideConstantsError {
    constructor(message: string, options?: CauseOption) {
        super("unsupported_format", message, options);
    }
}

/** Not JSON, a required field is missing, or a reference does not resolve. */
export class InvalidReleaseError extends OpenTideConstantsError {
    constructor(message: string, options?: CauseOption) {
        super("invalid_release", message, options);
    }
}

/** `requireStation` with an unknown id. */
export class StationNotFoundError extends OpenTideConstantsError {
    readonly stationId: string;

    constructor(stationId: string) {
        super("station_not_found", `no station ${stationId} in this release`);
        this.stationId = stationId;
    }
}

/** `requireStation` with a removed id. The tombstone is attached. */
export class StationRemovedError extends OpenTideConstantsError {
    readonly stationId: string;
    /** The removed station's tombstone (a `Tombstone`). */
    readonly tombstone: unknown;

    constructor(stationId: string, tombstone: unknown, reason: string | null) {
        super("station_removed", `station ${stationId} was removed${reason ? `: ${reason}` : ""}`);
        this.stationId = stationId;
        this.tombstone = tombstone;
    }
}

/** An update on a client opened on a pinned release or a file. */
export class PinnedReleaseError extends OpenTideConstantsError {
    constructor(message: string) {
        super("pinned_release", message);
    }
}

/** The cache cannot be written (permissions, disk full, a failed rename). */
export class CacheError extends OpenTideConstantsError {
    readonly path: string | null;

    constructor(message: string, detail: { path?: string | null } & CauseOption = {}) {
        super("cache", message, detail);
        this.path = detail.path ?? null;
    }
}

/** `download` found a file in `to` with the same name and a different SHA-256. */
export class FileExistsError extends OpenTideConstantsError {
    readonly path: string;

    constructor(path: string) {
        super("file_exists", `${path} exists with a different SHA-256 (pass overwrite: true to replace it)`);
        this.path = path;
    }
}

/** An operation that needs a file system, in a browser. */
export class UnsupportedError extends OpenTideConstantsError {
    constructor(message: string) {
        super("unsupported", message);
    }
}

/** A local file cannot be opened or read. */
export class FileError extends OpenTideConstantsError {
    readonly path: string;

    constructor(message: string, detail: { path: string } & CauseOption) {
        super("io", message, detail);
        this.path = detail.path;
    }
}

/** A bad argument: a bad datestamp, a lat or lon out of range, a negative radius, an empty query. */
export class InvalidArgumentError extends OpenTideConstantsError {
    constructor(message: string) {
        super("invalid_argument", message);
    }
}
