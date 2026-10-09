import { InvalidArgumentError, InvalidReleaseError } from "./errors.js";
import { FOLD_TABLE } from "./fold-table.js";

/** The SDK version. Its MAJOR.MINOR is the conformance suite version it passes (spec 7.2). */
export const VERSION = "0.1.0";
/** The format majors this SDK reads (spec 7.4). */
export const SUPPORTED_FORMAT_MAJORS: readonly number[] = Object.freeze([1]);
/** The newest format version this SDK reads (spec 7.4). A release whose min_reader_version is newer is refused. */
export const SUPPORTED_FORMAT_VERSION = "1.0";
/** The default data host. */
export const DEFAULT_BASE_URL = "https://data.opentideconstants.org/";
/** The cache layout version: the subdirectory of the cache root (spec 5.4). */
export const CACHE_LAYOUT_VERSION = "v1";

/** @internal */
export const USER_AGENT = `opentideconstants-js/${VERSION} (+https://opentideconstants.org)`;
/** @internal */
export const SDK_ID = `opentideconstants-js/${VERSION}`;

/** A datestamp: the date, then an optional counter of 2 or more with at most 9 digits (spec 4.2, CR D18). */
const DATESTAMP_RE = /^[0-9]{8}(\.[2-9]|\.[1-9][0-9]{1,8})?$/;

/** @internal Throws invalid_argument unless `d` is a datestamp. */
export function checkDatestamp(d: unknown, what = "release"): string {
    if (typeof d !== "string" || !DATESTAMP_RE.test(d)) {
        throw new InvalidArgumentError(`${what} must be "latest" or a datestamp like 20261008 or 20261008.2; got ${JSON.stringify(d)}`);
    }
    return d;
}

/** @internal True if `d` is a datestamp. */
export function isDatestamp(d: unknown): d is string {
    return typeof d === "string" && DATESTAMP_RE.test(d);
}

/** @internal Datestamp order: the date, then the counter (no counter = 1). Spec 4.3.1. */
export function compareDatestamps(a: string, b: string): number {
    const [da, ca] = a.split(".");
    const [db, cb] = b.split(".");
    if (da !== db) return (da ?? "") < (db ?? "") ? -1 : 1;
    return (ca ? Number(ca) : 1) - (cb ? Number(cb) : 1);
}

/** MAJOR.MINOR: two non-negative integers with no leading zeros, joined by one dot (spec 7.4, CR D9). */
const VERSION_RE = /^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$/;

/** @internal [major, minor] of a "MAJOR.MINOR" version, or null when it is not one. The only version parser. */
export function majorMinor(v: unknown): [number, number] | null {
    if (typeof v !== "string") return null;
    const m = VERSION_RE.exec(v);
    return m ? [Number(m[1]), Number(m[2])] : null;
}

/** @internal The major of a "MAJOR.MINOR" format version, or NaN. */
export function formatMajor(v: unknown): number {
    return majorMinor(v)?.[0] ?? NaN;
}

/** @internal True if this SDK reads the format version's major. */
export function supportedFormat(v: unknown): boolean {
    return SUPPORTED_FORMAT_MAJORS.includes(formatMajor(v));
}

/**
 * @internal Throws invalid_release when a version string is present (not null or absent) but not MAJOR.MINOR
 * (spec 7.4, CR D9: the SDK fails closed and never guesses a version). `what` names it in the message.
 */
export function checkVersion(v: unknown, what: string): void {
    if (v !== undefined && v !== null && majorMinor(v) === null) {
        throw new InvalidReleaseError(`${what} ${JSON.stringify(v)} is not MAJOR.MINOR`);
    }
}

/**
 * @internal True if this SDK reads a release with this `min_reader_version` (spec 7.4): it is absent, or not
 * newer than SUPPORTED_FORMAT_VERSION. A malformed value is invalid_release (CR D9).
 */
export function readerReads(minReaderVersion: unknown): boolean {
    checkVersion(minReaderVersion, "min_reader_version");
    const want = majorMinor(minReaderVersion);
    const have = majorMinor(SUPPORTED_FORMAT_VERSION) as [number, number];
    if (want === null) return true;
    return want[0] < have[0] || (want[0] === have[0] && want[1] <= have[1]);
}

/** @internal Fold a name through the shared fold table, trim, and collapse whitespace (spec 4.4.1). */
export function foldName(name: string): string {
    let out = "";
    for (const ch of name) {
        const cp = ch.codePointAt(0) as number;
        const f = FOLD_TABLE.get(cp);
        out += f === undefined ? ch : f;
    }
    return out.replace(/[ \t\n\r\f\v]+/g, " ").replace(/^ +| +$/g, "");
}
