/** @internal Turn release bytes into a Release (spec 6.1, 6.2). No I/O here. */
import { formatMajor, supportedFormat, SUPPORTED_FORMAT_MAJORS } from "./constants.js";
import { InvalidReleaseError, UnsupportedFormatError } from "./errors.js";
import { deepFreeze, isObject, type Json, type JsonObject } from "./json.js";
import {
    Release, indexDoc, indexStations, parseHeader, resolveKinds,
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

function checkFormat(doc: unknown): void {
    if (!isObject(doc)) throw new InvalidReleaseError("the release document is not a JSON object");
    const fv = doc["format_version"];
    if (typeof fv !== "string" || Number.isNaN(formatMajor(fv))) throw new InvalidReleaseError("format_version is missing or not MAJOR.MINOR");
    if (!supportedFormat(fv)) {
        throw new UnsupportedFormatError(`format ${fv} is not supported (this SDK reads majors ${SUPPORTED_FORMAT_MAJORS.join(", ")}); upgrade opentideconstants`);
    }
}

/** @internal A release from the full `.json` document (eager). */
export function releaseFromJson(bytes: Uint8Array, files: readonly FileInfo[]): Release {
    const doc = parseJson(bytes, "the release file");
    checkFormat(doc);
    const header = parseHeader(doc);
    const stations = isObject(doc) ? doc["stations"] : undefined;
    if (!Array.isArray(stations)) throw new InvalidReleaseError("stations is missing");
    const entries = indexStations(header, stations);
    const docs = stations.map((s) => deepFreeze(s)) as JsonObject[];
    const source: StationSource = { doc: (_e, i) => docs[i] as JsonObject, close: () => undefined };
    return new Release(header, entries, source, files, true);
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
        if (utf8.decode(line).trim() !== "") {
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
        source = {
            doc: (e) => {
                const v: unknown = JSON.parse(utf8.decode(read(e.offset, e.length)));
                if (!isObject(v)) throw new InvalidReleaseError(`the line of ${e.station_id} is not a JSON object`);
                return deepFreeze(v);
            },
            close: opts.close ?? (() => undefined),
        };
    }
    return new Release(header, entries, source, opts.files, opts.eager);
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
    return m && m[1] && m[2] ? { datestamp: m[1], ext: m[2] } : null;
}
