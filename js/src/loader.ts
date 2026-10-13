/** @internal Turn release bytes into a Release (spec 6.1, 6.2). No I/O here. */
import { formatMajor, isDatestamp, readerReads, supportedFormat, SUPPORTED_FORMAT_MAJORS, SUPPORTED_FORMAT_VERSION } from "./constants.js";
import { InvalidReleaseError, ReaderTooOldError, UnsupportedFormatError } from "./errors.js";
import { deepFreeze, isObject, type Json, type JsonObject } from "./json.js";
import {
    Release, checkLinks, indexDoc, indexStations, lineView, parseHeader, resolveKinds,
    type IndexEntry, type ReleaseHeader, type StationSource,
} from "./release.js";
import type { FileInfo } from "./types.js";

// fatal: bytes that are not UTF-8 are invalid_release, as in the other SDKs, never U+FFFD (CR2 PK-R2-05)
const utf8 = new TextDecoder("utf-8", { fatal: true });

/** @internal The text of UTF-8 bytes; invalid_release when they are not UTF-8. */
export function decodeUtf8(bytes: Uint8Array, what: string): string {
    try {
        return utf8.decode(bytes);
    } catch (e) {
        throw new InvalidReleaseError(`${what} is not valid UTF-8`, { cause: e });
    }
}

const SURROGATE_ESCAPE = /\\u[dD][89a-fA-F]/;
const LONE_SURROGATE = /[\uD800-\uDFFF]/u;   // with the u flag, a well-formed pair is one code point and never matches

/** True when a string in v (a key or a value, at any depth) has an unpaired UTF-16 surrogate. */
function hasLoneSurrogate(v: unknown): boolean {
    const stack: unknown[] = [v];
    while (stack.length > 0) {
        const x = stack.pop();
        if (typeof x === "string") {
            if (LONE_SURROGATE.test(x)) return true;
        } else if (Array.isArray(x)) {
            stack.push(...x);
        } else if (typeof x === "object" && x !== null) {
            for (const [k, y] of Object.entries(x)) {
                if (LONE_SURROGATE.test(k)) return true;
                stack.push(y);
            }
        }
    }
    return false;
}

/**
 * @internal JSON text to a value. invalid_release when it is not JSON, or when a \u escape makes an unpaired
 * surrogate, which is not valid Unicode (spec 7.3, CR D17). UTF-8 text cannot hold a surrogate, so only a text with
 * such an escape is walked.
 */
export function parseJsonText(text: string, what: string): unknown {
    let v: unknown;
    try {
        v = JSON.parse(text);
    } catch (e) {
        throw new InvalidReleaseError(`${what} is not JSON`, { cause: e });
    }
    if (SURROGATE_ESCAPE.test(text) && hasLoneSurrogate(v)) throw new InvalidReleaseError(`${what}: a string with an unpaired surrogate`);
    return v;
}

/** @internal */
export function parseJson(bytes: Uint8Array, what: string): unknown {
    return parseJsonText(decodeUtf8(bytes, what), what);
}

/**
 * @internal Check a release document's (or `.meta.json`'s) format: unsupported_format for a major this SDK
 * does not read, reader_too_old for a `release.min_reader_version` newer than SUPPORTED_FORMAT_VERSION (spec 7.4).
 */
export function checkFormat(doc: unknown): void {
    if (!isObject(doc)) throw new InvalidReleaseError("the release document is not a JSON object");
    const fv = doc["format_version"];
    if (typeof fv !== "string" || Number.isNaN(formatMajor(fv))) throw new InvalidReleaseError("format_version is missing or not MAJOR.MINOR");
    if (!supportedFormat(fv)) {
        throw new UnsupportedFormatError(`format ${fv} is not supported (this SDK reads majors ${SUPPORTED_FORMAT_MAJORS.join(", ")}); upgrade opentideconstants`);
    }
    const rel = doc["release"];
    const min = isObject(rel) ? rel["min_reader_version"] : undefined;
    if (!readerReads(min)) {
        const d = isObject(rel) && typeof rel["datestamp"] === "string" ? rel["datestamp"] : "?";
        throw readerTooOld(d, String(min));
    }
}

/** @internal The reader_too_old error for release D, which needs a reader for format `min`. */
export function readerTooOld(d: string, min: string): ReaderTooOldError {
    return new ReaderTooOldError(`release ${d} needs a reader for format ${min}; this SDK reads format ${SUPPORTED_FORMAT_VERSION} (upgrade opentideconstants)`);
}

/** @internal A release from the full `.json` document (eager). */
export function releaseFromJson(bytes: Uint8Array, files: readonly FileInfo[], zenodoVersionDoi: string | null = null,
    warn: (message: string) => void = () => undefined, commercialOnly = false, commercialBasis: "strict" | "as_published_upstream" = "strict", historicalPolicy: "fallback" | "exclude" = "fallback"): Release {
    const doc = parseJson(bytes, "the release file");
    checkFormat(doc);
    const header = parseHeader(doc);
    const stations = isObject(doc) ? doc["stations"] : undefined;
    if (!Array.isArray(stations)) throw new InvalidReleaseError("stations is missing");
    const entries = indexStations(header, stations);
    const docs = stations.map((s) => deepFreeze(s)) as JsonObject[];
    const source: StationSource = { doc: (_e, i) => docs[i] as JsonObject, close: () => undefined };
    return new Release(header, entries, source, files, true, zenodoVersionDoi, warn, commercialOnly, commercialBasis, historicalPolicy);
}

/** @internal Parse and check `.meta.json`. */
export function headerFromMeta(bytes: Uint8Array): ReleaseHeader {
    const doc = parseJson(bytes, "the .meta.json file");
    checkFormat(doc);
    return parseHeader(doc);
}

/** @internal A stream index read from index-v1.json (spec 6.2). */
export interface StreamIndex {
    entries: IndexEntry[];
}

/**
 * True when a line holds only ASCII whitespace: SP, HT, LF, VT, FF, CR (spec 6.2, CR2 DR26). NBSP and the other
 * Unicode spaces, and NUL, are not blank, so such a line is read as JSON (and is not JSON).
 */
function isBlank(line: Uint8Array): boolean {
    for (const b of line) if (b !== 0x20 && (b < 0x09 || b > 0x0d)) return false;
    return true;
}

/** @internal Index every line of a `.jsonl` file. Returns the index and, if keep, the parsed documents. */
export function indexJsonl(header: ReleaseHeader, bytes: Uint8Array, keep: boolean): { entries: IndexEntry[]; docs: JsonObject[] } {
    const convs = new Set(header.conventions.map((c) => String(c["convention_id"])));
    const lics = new Set(header.licences.map((l) => String(l["licence_id"])));
    const entries: IndexEntry[] = [];
    const docs: JsonObject[] = [];
    let start = 0;
    let lineNo = 0;
    while (start < bytes.length) {
        let end = bytes.indexOf(0x0a, start);
        if (end === -1) end = bytes.length;
        lineNo++;
        // the length leaves out the line end: \n, or \r\n (spec 6.2)
        const body = end < bytes.length && end > start && bytes[end - 1] === 0x0d ? end - 1 : end;
        const line = bytes.subarray(start, body);
        if (!isBlank(line)) {
            const text = decodeUtf8(line, `line ${lineNo} of the .jsonl file`);
            const doc = parseJsonText(text, `line ${lineNo} of the .jsonl file`) as Json;
            entries.push(indexDoc(doc, header, start, body - start, convs, lics));
            if (keep) docs.push(deepFreeze(doc) as JsonObject);
        }
        start = end + 1;
    }
    checkLinks(entries);
    resolveKinds(entries);
    return { entries, docs };
}

/** @internal Reads one line by offset and length. */
export type LineReader = (offset: number, length: number) => Uint8Array;

/**
 * @internal Index a positional reader while its exact chunks are authenticated by the caller. Validation errors
 * are saved so the caller can check JSONL and META checksums first. I/O failures still escape immediately.
 * Only the unfinished line and station summaries survive each chunk; no complete-file buffer is retained.
 */
export function scanJsonlReader(header: ReleaseHeader | null, read: LineReader, onChunk: (bytes: Uint8Array) => void): {
    entries: IndexEntry[]; bytesRead: number; error: unknown | null;
} {
    const entries: IndexEntry[] = [];
    const convs = new Set(header?.conventions.map((c) => String(c["convention_id"])));
    const lics = new Set(header?.licences.map((l) => String(l["licence_id"])));
    let bytesRead = 0;
    let lineStart = 0;
    let lineNo = 0;
    let fragments: Uint8Array[] = [];
    let pendingLength = 0;
    let error: unknown | null = null;
    const line = (last: Uint8Array, terminated: boolean): void => {
        lineNo++;
        let bytes: Uint8Array;
        if (fragments.length === 0) bytes = last;
        else {
            bytes = new Uint8Array(pendingLength + last.length);
            let offset = 0;
            for (const fragment of fragments) { bytes.set(fragment, offset); offset += fragment.length; }
            bytes.set(last, offset);
        }
        fragments = [];
        pendingLength = 0;
        const length = terminated && bytes.length > 0 && bytes[bytes.length - 1] === 0x0d ? bytes.length - 1 : bytes.length;
        const body = bytes.subarray(0, length);
        if (!isBlank(body) && header) {
            const doc = parseJson(body, `line ${lineNo} of the .jsonl file`) as Json;
            entries.push(indexDoc(doc, header, lineStart, length, convs, lics));
        }
    };
    for (;;) {
        const chunk = read(bytesRead, 65536);
        if (chunk.length === 0) break;
        onChunk(chunk);
        const offset = bytesRead;
        bytesRead += chunk.length;
        if (error !== null || header === null) continue;
        try {
            let start = 0;
            for (;;) {
                const end = chunk.indexOf(0x0a, start);
                if (end < 0) break;
                line(chunk.subarray(start, end), true);
                start = end + 1;
                lineStart = offset + start;
            }
            if (start < chunk.length) {
                const fragment = chunk.subarray(start);
                fragments.push(fragment);
                pendingLength += fragment.length;
            }
        } catch (e) {
            error = e;
            fragments = [];
            pendingLength = 0;
        }
    }
    if (error === null && header !== null) {
        try {
            if (pendingLength > 0) line(new Uint8Array(), false);
            checkLinks(entries);
            resolveKinds(entries);
        } catch (e) { error = e; }
    }
    return { entries, bytesRead, error };
}

// Keep fallback bytes outside the lexical context shared by the returned station source.
// An external positional reader must not retain the buffer used only to build the index.
function bufferLineReader(bytes: Uint8Array): LineReader {
    return (offset, length) => bytes.subarray(offset, offset + length);
}

/** @internal A release from `.jsonl` + `.meta.json`. Eager keeps every document; stream reads lines on demand. */
export function releaseFromJsonl(meta: Uint8Array, jsonl: Uint8Array | null, opts: {
    eager: boolean;
    files: readonly FileInfo[];
    index?: StreamIndex | null;
    /** Fresh entries validated while authenticating the same direct-file bytes; never a cached index. */
    preparedIndex?: StreamIndex | null;
    reader?: LineReader | null;
    close?: () => void;
    zenodoVersionDoi?: string | null;
    /** Called when a line read through `index` does not match its entry: delete index-v1.json (spec 6.2, CR D4). */
    dropIndex?: () => void;
    /** Where a station with an unknown status is reported, once at load (CR2 DR8). */
    warn?: (message: string) => void;
    /** The open option of spec 4.2 (K-NC DR106). */
    commercialOnly?: boolean;
    commercialBasis?: "strict" | "as_published_upstream";
    historicalOffsetsPolicy?: "fallback" | "exclude";
}): Release {
    const header = headerFromMeta(meta);
    let entries: IndexEntry[];
    let docs: JsonObject[] = [];
    if (opts.index && !opts.eager) {
        entries = opts.index.entries;
    } else if (opts.preparedIndex && !opts.eager) {
        entries = opts.preparedIndex.entries;
    } else {
        if (!jsonl) throw new InvalidReleaseError("the .jsonl file is missing");
        ({ entries, docs } = indexJsonl(header, jsonl, opts.eager));
    }
    let source: StationSource;
    if (opts.eager) {
        source = { doc: (_e, i) => docs[i] as JsonObject, close: () => undefined };
    } else {
        const read: LineReader = opts.reader ?? bufferLineReader(jsonl as Uint8Array);
        const fromIndex = Boolean(opts.index);
        const convs = new Set(header.conventions.map((c) => String(c["convention_id"])));
        const lics = new Set(header.licences.map((l) => String(l["licence_id"])));
        // a line read through the index must be the entry's line: whole, JSON, and the same station_id (CR D4)
        const bad = (why: string, cause?: unknown): InvalidReleaseError => {
            const where = fromIndex ? "index-v1.json" : "the .jsonl index";
            if (fromIndex) opts.dropIndex?.();
            return new InvalidReleaseError(`${where} does not match the .jsonl: ${why}`, cause === undefined ? undefined : { cause });
        };
        source = {
            doc: (e) => {
                const bytes = read(e.offset, e.length);
                if (bytes.length !== e.length) throw bad(`the line of ${e.station_id} is ${bytes.length} bytes, not ${e.length}`);
                let v: unknown;
                try {
                    v = parseJson(bytes, `the line of ${e.station_id}`);
                } catch (x) {
                    throw bad(`the line of ${e.station_id} at offset ${e.offset} is not JSON`, x);
                }
                if (!isObject(v)) throw bad(`the line of ${e.station_id} is not a JSON object`);
                if (v["station_id"] !== e.station_id) throw bad(`the line at offset ${e.offset} is ${JSON.stringify(v["station_id"])}, not ${e.station_id}`);
                if (fromIndex) {
                    // the checks of the full pass, and the line gives its entry's status, references and sets (PK-R2-07)
                    let got: IndexEntry;
                    try {
                        got = indexDoc(v, header, e.offset, e.length, convs, lics);
                    } catch (x) {
                        if (x instanceof InvalidReleaseError) throw bad(`the line of ${e.station_id} fails a check: ${x.message}`, x);
                        throw x;
                    }
                    if (lineView(got.stored, e.legacyOffsets, e.indexPresence, v) !== lineView(e.stored, e.legacyOffsets, e.indexPresence)) throw bad(`the line of ${e.station_id} does not give the status, references and sets of its entry`);
                }
                return deepFreeze(v);
            },
            close: opts.close ?? (() => undefined),
        };
    }
    return new Release(header, entries, source, opts.files, opts.eager, opts.zenodoVersionDoi ?? null, opts.warn, opts.commercialOnly ?? false, opts.commercialBasis ?? "strict", opts.historicalOffsetsPolicy ?? "fallback");
}

/**
 * @internal Parse a `sha256sum` file: name -> digest. A file that is not UTF-8, or that names a file twice, is
 * invalid_release, so that row order never decides a check (spec 5.3, CR2 DR14). `what` names the file.
 */
export function parseSha256(bytes: Uint8Array, what = "the .sha256 file"): Map<string, string> {
    let text: string;
    try {
        text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    } catch (e) {
        throw new InvalidReleaseError(`${what} is not UTF-8`, { cause: e });
    }
    const out = new Map<string, string>();
    // lines end at LF (a CR before it is white space); a line holds only ASCII white space, or is a row: 64 hex digits,
    // spaces or tabs, an optional "*", the name without trailing white space. Any other line is invalid_release (CR2 DR41)
    const lines = text.split("\n");
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i] as string;
        if (/^[ \t\r\n\v\f]*$/.test(line)) continue;
        const m = /^([0-9a-fA-F]{64})[ \t]+\*?([^\n]*?[^ \t\r\n\v\f])[ \t\r\n\v\f]*$/.exec(line);
        if (!m || !m[1] || !m[2]) throw new InvalidReleaseError(`${what} line ${i + 1} is not "<sha256>  <name>": ${JSON.stringify(line.slice(0, 100))}`);
        if (out.has(m[2])) throw new InvalidReleaseError(`${what} lists ${m[2]} twice`);
        out.set(m[2], m[1].toLowerCase());
    }
    return out;
}

/** @internal Split `OTC_{D}.{ext}` into its datestamp and extension. */
export function splitReleaseName(name: string): { datestamp: string; ext: string } | null {
    const m = /^OTC_([0-9]{8}(?:\.[0-9]+)?)\.(json|json\.gz|jsonl|meta\.json|sha256)$/.exec(name);
    return m && m[1] && m[2] && isDatestamp(m[1]) ? { datestamp: m[1], ext: m[2] } : null;
}
