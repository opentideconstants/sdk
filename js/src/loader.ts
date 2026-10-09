/** @internal Turn release bytes into a Release (spec 6.1, 6.2). No I/O here. */
import { formatMajor, isDatestamp, readerReads, supportedFormat, SUPPORTED_FORMAT_MAJORS, SUPPORTED_FORMAT_VERSION } from "./constants.js";
import { InvalidReleaseError, ReaderTooOldError, UnsupportedFormatError } from "./errors.js";
import { deepFreeze, isObject, type Json, type JsonObject } from "./json.js";
import {
    Release, checkLinks, indexDoc, indexStations, parseHeader, resolveKinds,
    type IndexEntry, type ReleaseHeader, type StationSource,
} from "./release.js";
import type { FileInfo } from "./types.js";

const utf8 = new TextDecoder("utf-8", { fatal: false });

/** @internal */
export function parseJson(bytes: Uint8Array, what: string): unknown {
    try {
        return JSON.parse(utf8.decode(bytes));
    } catch (e) {
        throw new InvalidReleaseError(`${what} is not JSON`, { cause: e });
    }
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
    warn: (message: string) => void = () => undefined): Release {
    const doc = parseJson(bytes, "the release file");
    checkFormat(doc);
    const header = parseHeader(doc);
    const stations = isObject(doc) ? doc["stations"] : undefined;
    if (!Array.isArray(stations)) throw new InvalidReleaseError("stations is missing");
    const entries = indexStations(header, stations);
    const docs = stations.map((s) => deepFreeze(s)) as JsonObject[];
    const source: StationSource = { doc: (_e, i) => docs[i] as JsonObject, close: () => undefined };
    return new Release(header, entries, source, files, true, zenodoVersionDoi, warn);
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
        const body = end > start && bytes[end - 1] === 0x0d ? end - 1 : end;
        const line = bytes.subarray(start, body);
        if (!isBlank(line)) {
            let doc: Json;
            try {
                doc = JSON.parse(utf8.decode(line)) as Json;
            } catch (e) {
                throw new InvalidReleaseError(`line ${lineNo} of the .jsonl file is not JSON`, { cause: e });
            }
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

/** @internal A release from `.jsonl` + `.meta.json`. Eager keeps every document; stream reads lines on demand. */
export function releaseFromJsonl(meta: Uint8Array, jsonl: Uint8Array | null, opts: {
    eager: boolean;
    files: readonly FileInfo[];
    index?: StreamIndex | null;
    reader?: LineReader | null;
    close?: () => void;
    zenodoVersionDoi?: string | null;
    /** Called when a line read through `index` does not match its entry: delete index-v1.json (spec 6.2, CR D4). */
    dropIndex?: () => void;
    /** Where a station with an unknown status is reported, once at load (CR2 DR8). */
    warn?: (message: string) => void;
}): Release {
    const header = headerFromMeta(meta);
    let entries: IndexEntry[];
    let docs: JsonObject[] = [];
    if (opts.index && !opts.eager) {
        entries = opts.index.entries;
    } else {
        if (!jsonl) throw new InvalidReleaseError("the .jsonl file is missing");
        ({ entries, docs } = indexJsonl(header, jsonl, opts.eager));
    }
    let source: StationSource;
    if (opts.eager) {
        source = { doc: (_e, i) => docs[i] as JsonObject, close: () => undefined };
    } else {
        const read: LineReader = opts.reader ?? ((o, l) => (jsonl as Uint8Array).subarray(o, o + l));
        const fromIndex = Boolean(opts.index);
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
                    v = JSON.parse(utf8.decode(bytes));
                } catch (x) {
                    throw bad(`the line of ${e.station_id} at offset ${e.offset} is not JSON`, x);
                }
                if (!isObject(v)) throw bad(`the line of ${e.station_id} is not a JSON object`);
                if (v["station_id"] !== e.station_id) throw bad(`the line at offset ${e.offset} is ${JSON.stringify(v["station_id"])}, not ${e.station_id}`);
                return deepFreeze(v);
            },
            close: opts.close ?? (() => undefined),
        };
    }
    return new Release(header, entries, source, opts.files, opts.eager, opts.zenodoVersionDoi ?? null, opts.warn);
}

/** @internal Parse a `sha256sum` file: name -> digest. */
export function parseSha256(text: string): Map<string, string> {
    const out = new Map<string, string>();
    for (const line of text.split(/\r?\n/)) {
        const m = /^([0-9a-fA-F]{64})\s+\*?(.+?)\s*$/.exec(line);
        if (m && m[1] && m[2]) out.set(m[2], m[1].toLowerCase());
    }
    return out;
}

/** @internal Split `OTC_{D}.{ext}` into its datestamp and extension. */
export function splitReleaseName(name: string): { datestamp: string; ext: string } | null {
    const m = /^OTC_([0-9]{8}(?:\.[0-9]+)?)\.(json|json\.gz|jsonl|meta\.json|sha256)$/.exec(name);
    return m && m[1] && m[2] && isDatestamp(m[1]) ? { datestamp: m[1], ext: m[2] } : null;
}
