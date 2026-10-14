import type * as prediction from './predict/engine.js';
import type * as C from './canonical-types.js';
import * as X from './errors.js';
import {AstroTable} from './predict/astro.js';
import {DatumInfo,DatumLevel,Ranges} from './predict/results.js';
import type {HeightSeries,ExtremeList,CurrentSeries,CurrentEventList} from './predict/results.js';
import { compareDatestamps, foldName } from "./constants.js";
import {
    FileError, InvalidArgumentError, InvalidReleaseError, StationNotFoundError, StationRemovedError,
} from "./errors.js";
import { arr, deepFreeze, en, isObject, num, obj, str, time, val, type Json, type JsonObject } from "./json.js";
import type {
    SourceRecord, Fallback, HistoricalOffsetVintage, HistoricalOffsetProvenance, ConstantSetsOptions, Constituent, Convention, Datum, DroppedConstituent, FileInfo, HeightAdjustedType, Kind,
    Licence, NearOptions, NearestOptions, Nearby, Other, Provenance, ProvenanceBuild, QcFlag, QcStatus, Quantity,
    RecordSpan, SearchOptions, SourceType, StationFilters, StationStatus, StationType, Stats, SubordinateOffsets,
    TimeBase, TimeBaseEvidence, Tombstone, Validation,
} from "./types.js";

const EARTH_R_KM = 6371.0088;
const QC_STATUSES = ["ok", "flagged", "no_constants"] as const;
/** The qc_status values of a set with constants: only these count as a usable source (spec 4.3, 4.4). */
const WITH_CONSTANTS: ReadonlySet<string> = new Set(["ok", "flagged"]);
const DEG = Math.PI / 180;

// ------------------------------------------------------------------------------------------ index

/** @internal One constant set in a stream index entry (spec 6.2). */
export interface StoredSet {
    set_id: string | null;
    source: string | null;
    source_type: string | null;
    quantity: string | null;
    qc_status: string | null;
    convention_id: string | null;
    licence_id: string | null;
    constituents: string[];
    fallback: JsonObject | null;
    current_bins: number[];
}

/** @internal One entry of index-v1.json, exactly as spec 6.2 gives it (the same in every SDK). */
export interface StoredEntry {
    offset: number;
    length: number;
    station_id: string;
    status: string;
    name: string | null;
    name_folded: string | null;
    country: string | null;
    type: string | null;
    lat: number | null;
    lon: number | null;
    kind: string | null;
    aliases: Record<string, string[]>;
    reference_station_id: string | null;
    offsets_licence_id: string | null;
    recommended_set_id: string | null;
    sets: StoredSet[];
    subordinate_offsets: JsonObject | null;
    current_offsets: JsonObject[];
}

const SET_KEYS = ["set_id", "source", "source_type", "quantity", "qc_status", "convention_id", "licence_id"] as const;
const ENTRY_STR = ["name", "name_folded", "country", "type", "kind", "reference_station_id", "offsets_licence_id", "recommended_set_id"] as const;
const PRIVATE_SET_KEYS = ["source_record_id", "source_version", "datum"] as const;
const CURRENT_BASE_KEYS = ["bin", "reference_bin", "reference_station_id", "licence_id"] as const;
const CURRENT_ADJUSTMENTS = ["time_adj_max_flood_min", "time_adj_max_ebb_min", "time_adj_slack_before_flood_min", "time_adj_slack_before_ebb_min", "flood_amp_ratio", "ebb_amp_ratio"] as const;

/** @internal Admitted field presence, independent of the informational writer name. Never serialized. */
export interface IndexPresence {
    own: "full" | "sparse" | "base";
    offsets: "full" | "projected" | "sparse";
    offsetFields: readonly (readonly string[])[];
    privateSets: boolean;
    bins: boolean;
    baseFallback: boolean;
    fallback: readonly boolean[];
}

/** @internal One line (station or tombstone) of a release, as the SDK keeps it in memory: the stored entry plus derived facts. */
export interface IndexEntry {
    stored: StoredEntry;
    /** Legacy discovery entries omit the own-offset payload; never serialized into index-v1.json. */
    legacyOffsets?: boolean;
    indexPresence?: IndexPresence;
    policyHydrated?: boolean;
    offset: number;
    length: number;
    station_id: string;
    status: string;
    name: string;
    name_folded: string;
    country: string | null;
    type: string | null;
    kind: string | null;
    lat: number | null;
    lon: number | null;
    aliases: Record<string, string[]>;
    reference_station_id: string | null;
    recommended_set_id: string | null;
    recommended_source_type: string | null;
    recommended_licence_id: string | null;
    offsets_licence_id: string | null;
    usable_sources: string[];
    set_sources: string[];
    set_qc_statuses: string[];
    constituent_names: string[];
}

/** @internal The release document without its stations (the `.meta.json` sidecar). */
export interface ReleaseHeader {
    raw: JsonObject;
    format_version: string;
    release: JsonObject;
    conventions: JsonObject[];
    licences: JsonObject[];
}

/** @internal Station documents by index position. */
export interface StationSource {
    doc(entry: IndexEntry, position: number): JsonObject;
    close(): void;
}

/**
 * The load rules of the licence fields (spec 4.6, K-NC DR104): commercial_use is a JSON boolean (absent or null is
 * invalid); restriction and terms_url, when present, are strings (a JSON null is not one, CR3 DR71); a
 * non-commercial licence has both, and an spdx, which the non-commercial notice prints.
 */
function checkLicence(l: JsonObject): void {
    const id = String(l["licence_id"]);
    const cu = l["commercial_use"];
    if (typeof cu !== "boolean") throw new InvalidReleaseError(`licence ${id}: commercial_use must be true or false`);
    for (const k of ["restriction", "terms_url"]) {
        if (Object.hasOwn(l, k) && typeof l[k] !== "string") throw new InvalidReleaseError(`licence ${id}: ${k} must be a string`);
    }
    if (cu) return;
    for (const k of ["restriction", "terms_url", "spdx"]) {
        if (typeof l[k] !== "string") throw new InvalidReleaseError(`licence ${id}: a licence with commercial_use false needs ${k}`);
    }
}

/** @internal Check the release header; throws invalid_release. */
export function parseHeader(doc: unknown): ReleaseHeader {
    if (!isObject(doc)) throw new InvalidReleaseError("the release document is not a JSON object");
    const fv = doc["format_version"];
    const release = doc["release"];
    if (typeof fv !== "string") throw new InvalidReleaseError("format_version is missing");
    if (!isObject(release) || typeof release["datestamp"] !== "string") throw new InvalidReleaseError("release.datestamp is missing");
    const conventions = doc["conventions"];
    const licences = doc["licences"];
    if (!Array.isArray(conventions) || !Array.isArray(licences)) throw new InvalidReleaseError("conventions or licences is missing");
    const created = release["created"];
    if (created !== undefined && created !== null && typeof created !== "string") throw new InvalidReleaseError("release.created is not a string");
    checkedTime(created, "release.created");
    const sv = release["source_versions"];
    if (sv !== undefined && sv !== null && !(isObject(sv) && Object.values(sv).every((x) => typeof x === "string"))) {
        throw new InvalidReleaseError("release.source_versions is not an object of strings");
    }
    if (!conventions.every(isObject) || !licences.every(isObject)) throw new InvalidReleaseError("a convention or licence is not a JSON object");
    const cs = conventions.filter(isObject);
    const ls = licences.filter(isObject);
    if (cs.some((c) => typeof c["convention_id"] !== "string") || ls.some((l) => typeof l["licence_id"] !== "string")) {
        throw new InvalidReleaseError("a convention or licence has no id");
    }
    for (const l of ls) {
        // the attribution text prints both (spec 4.6, CR2 DR2); a null provider is allowed (CR D2 b)
        const provider = l["provider"];
        if (typeof l["attribution"] !== "string" || !(provider === undefined || provider === null || typeof provider === "string")) {
            throw new InvalidReleaseError(`licence ${String(l["licence_id"])}: attribution must be a string and provider a string or null`);
        }
        checkLicence(l);
    }
    for (const [list, key] of [[cs, "convention_id"], [ls, "licence_id"]] as const) {
        const seen = new Set<string>();
        for (const x of list) {
            const id = String(x[key]);
            if (seen.has(id)) throw new InvalidReleaseError(`${key} ${id} appears twice (CR D5)`);
            seen.add(id);
        }
    }
    return deepFreeze({ raw: doc, format_version: fv, release, conventions: cs, licences: ls });
}

/**
 * The JSON type of each known field that the SDK reads (spec 7.3: tolerant is not lax; CR2 PK-R2-05). Absent or
 * null is always allowed here; required fields are checked where they are used. T a string, N a finite number,
 * I a finite number with an integral value, O an object, L a list of objects, S a list of strings, A a list.
 * The same table is in the Python, Ruby and C SDKs.
 */
type FieldType = "B" | "T" | "N" | "I" | "O" | "L" | "S" | "A";
type FieldTypes = Readonly<Record<string, FieldType>>;
const STATION_TYPES: FieldTypes = {
    name: "T", country: "T", timezone: "T", type: "T", recommended_set_id: "T", status: "T",
    recommended_is_fallback: "B", source_records: "L", aliases: "O", constant_sets: "L", validation: "L", subordinate_offsets: "O", current_offsets: "A",
};
const OFFSET_TYPES: FieldTypes = {
    offset_id: "T", source: "T", source_type: "T", source_version: "T", source_record_id: "T",
    qc_status: "T", qc_flags: "L", fallback: "O", vintage: "O", provenance: "O",
    reference_station_id: "T", licence_id: "T", height_adjusted_type: "T",
    time_offset_high_min: "N", time_offset_low_min: "N", height_offset_high: "N", height_offset_low: "N",
};
const VALIDATION_TYPES: FieldTypes = {
    set_id: "T", reference_source: "T", reference_station: "T", window: "T", reference_distance_km: "N",
    time_mae_min: "N", time_p95_min: "N", time_bias_min: "N", height_mae_m: "N", range_error_m: "N",
    missed_events: "I", extra_events: "I", previous_release: "O",
};
const SET_TYPES: FieldTypes = {
    set_id: "T", source: "T", source_type: "T", quantity: "T", source_record_id: "T", source_version: "T",
    convention_id: "T", licence_id: "T", qc_status: "T", constituents: "L", dropped_constituents: "L", qc_flags: "L",
    fallback: "O", record_span: "O", datum: "O", time_base: "O", provenance: "O", current_bins: "A",
};
const SPAN_TYPES: FieldTypes = { good_samples: "I" };
const DATUM_TYPES: FieldTypes = { msl_offset_m: "N", named: "O" };
const CONSTITUENT_TYPES: FieldTypes = {
    name: "T", source_name: "T", doodson: "T", kept_reason: "T", speed_deg_per_hour: "N", amplitude_m: "N",
    phase_deg: "N", amp_uncertainty_m: "N", phase_uncertainty_deg: "N",
};
const QC_FLAG_TYPES: FieldTypes = { flag: "T", reason: "T", values: "O" };
const DROPPED_TYPES: FieldTypes = { name: "T", dropped_reason: "T", detail: "T" };
const TIME_BASE_TYPES: FieldTypes = {
    code: "T", reason: "T", declared: "T", published: "T", decided_in: "T", decided_build_commit: "T",
    correction: "O", months_dropped: "S", evidence: "L",
};
const CORRECTION_TYPES: FieldTypes = { from: "T", to: "T" };
const EVIDENCE_TYPES: FieldTypes = { comparator_kind: "T", comparator_id: "T", detail: "T", distance_km: "N", lag_min: "N" };
const PROVENANCE_TYPES: FieldTypes = {
    adapter_version: "T", carried_from_release: "T", selection_reason: "T", input_sha256: "S", decision: "O",
};

function finite(v: Json | undefined): v is number {
    return typeof v === "number" && Number.isFinite(v);
}

function typeOk(v: Json | undefined, t: FieldType): boolean {
    if (v === undefined || v === null) return true;
    switch (t) {
        case "B": return typeof v === "boolean";
        case "T": return typeof v === "string";
        case "N": return finite(v);
        case "I": return finite(v) && Number.isInteger(v);
        case "O": return isObject(v);
        case "L": return Array.isArray(v) && v.every(isObject);
        case "S": return Array.isArray(v) && v.every((x) => typeof x === "string");
        default: return Array.isArray(v);
    }
}

/** The members of an object, as a list of objects (absent or null: none). Call after its type is checked. */
function objects(o: JsonObject, k: string): JsonObject[] {
    const v = o[k];
    return Array.isArray(v) ? v.filter(isObject) : [];
}

/**
 * A created or record_span time (spec 7.3, CR2 DR6): null when absent, else an RFC 3339 time with real calendar fields
 * in years 1 to 9999 in UTC; anything else is invalid_release, never a rolled-over date or null.
 */
function checkedTime(v: Json | undefined, what: string): Date | null {
    if (v === undefined || v === null) return null;
    const t = time(v);
    if (t === null) throw new InvalidReleaseError(`${what} is not an RFC 3339 time: ${JSON.stringify(v)}`);
    return t;
}

/**
 * Tolerant is not lax (spec 7.3): a known field with the wrong JSON type is invalid_release at load, in every path,
 * instead of a field that is silently dropped or a raw TypeError at query time.
 */
/** @internal The original known-field validation, independent of reference resolution. */
export function checkShape(doc: JsonObject, id: string): void {
    const check = (o: JsonObject, table: FieldTypes, what: string) => {
        for (const [k, t] of Object.entries(table)) {
            if (!typeOk(o[k], t)) throw new InvalidReleaseError(`station ${id}: ${what}${k} has the wrong type`);
        }
    };
    check(doc, STATION_TYPES, "");
    const a = doc["aliases"];
    if (isObject(a)) {
        for (const [system, ids] of Object.entries(a)) {
            if (!(typeof ids === "string" || (Array.isArray(ids) && ids.every((x) => typeof x === "string")))) {
                throw new InvalidReleaseError(`station ${id}: aliases.${system} has the wrong type`);
            }
        }
    }
    const off = obj(doc, "subordinate_offsets");
    if (off) checkHistoricalOffsets(off);
    checkSourceRecords(doc);
    if (off) check(off, OFFSET_TYPES, "subordinate_offsets.");
    for (const v of objects(doc, "validation")) check(v, VALIDATION_TYPES, "validation ");
    for (const cs of objects(doc, "constant_sets")) {
        const where = `set ${typeof cs["set_id"] === "string" ? cs["set_id"] : "?"}: `;
        check(cs, SET_TYPES, where);
        const fallback = obj(cs, "fallback");
        if (fallback) check(fallback, { reason: "T", basis: "T", otc_finding: "T", preferred_set_id: "T" }, `${where}fallback.`);
        if (fallback?.["reason"] === "historical_offsets" || objects(cs, "qc_flags").some(f => f["flag"] === "fallback:historical_offsets")) throw new InvalidReleaseError(`${where}historical_offsets belongs only to subordinate_offsets`);
        for (const [k, table] of [["record_span", SPAN_TYPES], ["datum", DATUM_TYPES], ["time_base", TIME_BASE_TYPES],
            ["provenance", PROVENANCE_TYPES]] as const) {
            const o = obj(cs, k);
            if (o) check(o, table, `${where}${k}.`);
        }
        const span = obj(cs, "record_span");
        for (const k of ["start", "end"]) checkedTime(span?.[k], `record_span.${k} of set ${typeof cs["set_id"] === "string" ? cs["set_id"] : "?"}`);
        const named = obj(obj(cs, "datum"), "named");
        if (named && !Object.values(named).every(finite)) throw new InvalidReleaseError(`station ${id}: ${where}datum.named has a value that is not a number`);
        const names = new Set<string>();
        for (const c of objects(cs, "constituents")) {
            check(c, CONSTITUENT_TYPES, `${where}constituents.`);
            const name = c["name"];
            if (typeof name !== "string") continue;   // a missing name is reported where the set is indexed
            if (names.has(name)) throw new InvalidReleaseError(`station ${id}: ${where}constituent ${name} appears twice (CR2 DR22)`);
            names.add(name);
        }
        for (const x of objects(cs, "dropped_constituents")) check(x, DROPPED_TYPES, `${where}dropped_constituents.`);
        for (const f of objects(cs, "qc_flags")) {
            check(f, QC_FLAG_TYPES, `${where}qc_flags.`);
            const values = obj(f, "values");
            if (values && !Object.values(values).every((x) => x === null || finite(x))) {
                throw new InvalidReleaseError(`station ${id}: ${where}a qc_flags value is not a number or null`);
            }
        }
        const tb = obj(cs, "time_base");
        const corr = obj(tb, "correction");
        if (corr) check(corr, CORRECTION_TYPES, `${where}time_base.correction.`);
        for (const e of tb ? objects(tb, "evidence") : []) check(e, EVIDENCE_TYPES, `${where}time_base.evidence.`);
    }
}

function aliasMap(doc: JsonObject): Record<string, string[]> {
    // fromEntries defines own properties, so a system named __proto__ or constructor is kept as data; an assignment
    // out[system] = ... would set the prototype instead (CR2 PK-R2-05)
    const a = obj(doc, "aliases");
    if (!a) return {};
    return Object.fromEntries(Object.entries(a).flatMap(([system, ids]): [string, string[]][] => {
        if (typeof ids === "string") return [[system, [ids]]];
        return Array.isArray(ids) ? [[system, ids.filter((x): x is string => typeof x === "string")]] : [];
    }));
}

/**
 * @internal Index one station document and check its references (spec 6.1: a reference that does not
 * resolve is invalid_release at load). `kind` of a subordinate with offsets only is resolved later.
 */
export function indexDoc(doc: unknown, header: ReleaseHeader, offset: number, length: number,
    conventions: Set<string>, licences: Set<string>): IndexEntry {
    if (!isObject(doc)) throw new InvalidReleaseError("a station is not a JSON object");
    const id = doc["station_id"];
    // a line with no status (or null) is an active station, as in the stream index (CR2 DR28)
    const status = doc["status"] ?? "active";
    if (typeof id !== "string" || typeof status !== "string") throw new InvalidReleaseError("a station has no station_id, or a status that is not a string");

    checkShape(doc, id);
    const sets = arr(doc, "constant_sets").filter(isObject);
    const recId = str(doc, "recommended_set_id");
    let rec: JsonObject | null = null;
    for (const cs of sets) {
        const conv = str(cs, "convention_id");
        const lic = str(cs, "licence_id");
        if (typeof cs["set_id"] !== "string") throw new InvalidReleaseError(`a constant set of ${id} has no set_id`);
        if (conv === null || !conventions.has(conv)) throw new InvalidReleaseError(`set ${String(cs["set_id"])}: convention_id ${JSON.stringify(conv)} does not resolve`);
        if (lic === null || !licences.has(lic)) throw new InvalidReleaseError(`set ${String(cs["set_id"])}: licence_id ${JSON.stringify(lic)} does not resolve`);
        if (cs["set_id"] === recId) rec = cs;
    }
    if (status === "active") {
        const lat = doc["lat"], lon = doc["lon"];
        if (!finite(lat) || !finite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) {
            throw new InvalidReleaseError(`station ${id}: lat and lon must be numbers in range`);
        }
        if (recId !== null && rec === null) throw new InvalidReleaseError(`station ${id}: recommended_set_id ${recId} does not resolve`);
    }
    const off = obj(doc, "subordinate_offsets");
    const offLic = off ? str(off, "licence_id") : null;
    if (offLic !== null && !licences.has(offLic)) throw new InvalidReleaseError(`station ${id}: subordinate_offsets.licence_id ${offLic} does not resolve`);
    for (const source of objects(doc, "source_records")) {
        for (const key of ["licence_id", "upstream_licence_id"]) {
            const lid = str(source, key);
            if (lid !== null && !licences.has(lid)) throw new InvalidReleaseError(`source record of ${id}: ${key} does not resolve`);
        }
    }
    const kind = rec ? kindOfQuantity(str(rec, "quantity")) : null;
    const name = str(doc, "name");
    return entryFromStored({
        offset, length, station_id: id, status,
        name, name_folded: name === null ? null : foldName(name),
        country: str(doc, "country"), type: str(doc, "type"), lat: num(doc, "lat"), lon: num(doc, "lon"), kind,
        aliases: aliasMap(doc),
        reference_station_id: off ? str(off, "reference_station_id") : null,
        offsets_licence_id: offLic,
        subordinate_offsets: off, current_offsets: objects(doc, "current_offsets"),
        recommended_set_id: recId,
        sets: sets.map((cs) => ({
            set_id: str(cs, "set_id"), source: str(cs, "source"), source_type: str(cs, "source_type"), quantity: str(cs, "quantity"),
            qc_status: str(cs, "qc_status"), convention_id: str(cs, "convention_id"), licence_id: str(cs, "licence_id"),
            fallback: obj(cs, "fallback"), current_bins: objects(cs, "current_bins").map((b) => num(b, "bin")).filter((v): v is number => v !== null),
            constituents: arr(cs, "constituents").filter(isObject).map((c) => str(c, "name")).filter((x): x is string => x !== null),
        })),
    });
}

/**
 * @internal The keys of an index entry that a line read through the index must give as they are (PK-R2-07): the
 * represented station fields, the references and the sets (spec 6.2).
 */
export function lineView(s: StoredEntry, legacyOffsets = false, presence?: IndexPresence, doc?: JsonObject): string {
    const sets = Array.isArray(s.sets) ? s.sets : [];
    if (presence) {
        const rawSets = doc ? objects(doc, "constant_sets") : [];
        const projectedSets = sets.map((cs, i) => {
            const raw = doc ? rawSets.find(raw => raw["set_id"] === cs.set_id) : cs as unknown as JsonObject;
            return [...SET_KEYS.map(k => cs[k]), cs.constituents,
                ...(presence.baseFallback ? [] : [presence.fallback[i] ? cs.fallback : cs.fallback === null ? null : "missing-fallback-mismatch"]),
                ...(presence.bins ? [cs.current_bins] : []),
                ...(presence.privateSets ? PRIVATE_SET_KEYS.map(k => canonicalJson(raw?.[k] ?? null) ?? "null") : [])];
        });
        const offsetKeys = presence.offsets === "projected" ? CURRENT_BASE_KEYS : [...CURRENT_BASE_KEYS, ...CURRENT_ADJUSTMENTS];
        const offsets = s.current_offsets.map((row, i) => (presence.offsetFields[i] ?? offsetKeys).map(k =>
            offsetKeys.some(known => known === k) ? row[k] ?? null : [Object.hasOwn(row, k), row[k] ?? null]));
        return canonicalJson([s.station_id, s.status, s.name, s.name_folded, s.country, s.type, s.lat, s.lon, s.aliases,
            s.recommended_set_id, s.reference_station_id, s.offsets_licence_id,
            projectedSets, ...(presence.own === "base" ? [] : [presence.own === "sparse" && s.subordinate_offsets !== null
                ? "missing-own-offset-mismatch" : s.subordinate_offsets]), offsets]) ?? "null";
    }
    return canonicalJson([s.station_id, s.status, s.name, s.name_folded, s.country, s.type, s.lat, s.lon, s.aliases,
        s.recommended_set_id, s.reference_station_id, s.offsets_licence_id,
        sets.map((cs) => [...SET_KEYS.map((k) => cs[k]), cs.constituents, cs.fallback, cs.current_bins]),
        ...(legacyOffsets ? [] : [s.subordinate_offsets]), s.current_offsets]) ?? "null";
}

/** @internal The in-memory entry of a stored index entry (spec 6.2). */
export function entryFromStored(s: StoredEntry): IndexEntry {
    const rec = s.recommended_set_id === null ? undefined : s.sets.find((cs) => cs.set_id === s.recommended_set_id);
    const names = new Set<string>();
    for (const cs of s.sets) for (const c of cs.constituents) names.add(c);
    const usable = s.sets.filter((cs) => cs.qc_status !== null && WITH_CONSTANTS.has(cs.qc_status));
    return {
        stored: s, offset: s.offset, length: s.length, station_id: s.station_id, status: s.status,
        name: s.name ?? "", name_folded: s.name_folded ?? "",
        country: s.country, type: s.type, kind: s.kind, lat: s.lat, lon: s.lon,
        aliases: s.aliases,
        reference_station_id: s.type === "subordinate" ? s.reference_station_id : null,
        recommended_set_id: rec ? s.recommended_set_id : null,
        recommended_source_type: rec ? rec.source_type : null,
        recommended_licence_id: rec ? rec.licence_id : null,
        offsets_licence_id: s.offsets_licence_id,
        usable_sources: [...new Set(usable.map((cs) => cs.source).filter((x): x is string => x !== null))],
        set_sources: usable.map((cs) => cs.source).filter((x): x is string => x !== null),
        set_qc_statuses: s.sets.map((cs) => en(cs.qc_status, QC_STATUSES)).filter((x): x is QcStatus | Other => x !== null),
        constituent_names: [...names].sort(cmp),
    };
}

/** @internal The index-v1.json document (spec 6.2) for these entries (kinds resolved). */
export function storedIndex(entries: IndexEntry[], datestamp: string, jsonlSha256: string, jsonlSize: number, by: string): JsonObject {
    return {
        discovery_index_version: 1, index_version: 1, datestamp, jsonl: `OTC_${datestamp}.jsonl`, jsonl_sha256: jsonlSha256, jsonl_size: jsonlSize, by,
        stations: entries.map((e) => ({ ...e.stored, kind: e.kind,
            current_offsets: e.stored.current_offsets.map(row => Object.fromEntries(CURRENT_BASE_KEYS.map(k => [k, row[k] ?? null]))),
        })) as unknown as Json[],
    };
}

/**
 * @internal The entries of a fresh index-v1.json, or null when it is stale or cannot be used (spec 6.2).
 * Fresh: index_version 1, this release's .jsonl by name, SHA-256 and size, every entry well formed, every entry in
 * bounds (length > 0, offset + length <= jsonl_size, no two entries overlapping; CR D4, CR2 DR9), and every reference resolving
 * exactly as a pass over the lines would check it (indexDoc). The derived values (name_folded, kind) must be the
 * ones this SDK computes, so an index another writer got wrong is rebuilt, not trusted.
 */
export function usableIndex(v: unknown, datestamp: string, jsonlSha256: string | null, jsonlSize: number | null,
    conventions: Set<string>, licences: Set<string>): IndexEntry[] | null {
    if (!isObject(v) || Object.hasOwn(v, "discovery_index_version") && v["discovery_index_version"] !== 1 || v["index_version"] !== 1 || v["datestamp"] !== datestamp || v["jsonl"] !== `OTC_${datestamp}.jsonl`) return null;
    if (jsonlSha256 === null || v["jsonl_sha256"] !== jsonlSha256 || jsonlSize === null || v["jsonl_size"] !== jsonlSize) return null;
    const stations = v["stations"];
    if (!Array.isArray(stations)) return null;
    // A complete older discovery index lacks this payload everywhere. A partial deletion from an expanded
    // index remains stale, so its full validation cannot be downgraded entry by entry.
    const legacyOffsets = stations.every((e) => isObject(e) && !Object.hasOwn(e, "subordinate_offsets"));
    const allSets = stations.flatMap(e => isObject(e) && Array.isArray(e["sets"]) ? e["sets"] : []);
    if (!allSets.every(isObject)) return null;
    const privateSets = allSets.some(cs => PRIVATE_SET_KEYS.some(k => Object.hasOwn(cs, k)));
    if (privateSets && !allSets.every(cs => PRIVATE_SET_KEYS.every(k => Object.hasOwn(cs, k)))) return null;
    const bins = allSets.some(cs => Object.hasOwn(cs, "current_bins"));
    const baseFallback = !allSets.some(cs => Object.hasOwn(cs, "fallback"));
    if (bins && !allSets.every(cs => Object.hasOwn(cs, "current_bins"))) return null;
    let currentProfile: "full" | "projected" | null = null;
    const strOrNull = (x: unknown) => x === null || typeof x === "string";
    const numOrNull = (x: unknown) => x === null || (typeof x === "number" && Number.isFinite(x));
    const isInt = (x: unknown): x is number => typeof x === "number" && Number.isInteger(x) && x >= 0;
    const out: IndexEntry[] = [];
    let start = 0; // the least offset the next entry may have: after the line before it and its line end (CR2 DR9)
    for (const entry of stations) {
        if (!isObject(entry)) return null;
        const e: JsonObject = {
            ...entry,
            subordinate_offsets: Object.hasOwn(entry, "subordinate_offsets") ? entry["subordinate_offsets"] : null,
            current_offsets: Object.hasOwn(entry, "current_offsets") ? entry["current_offsets"] : [],
        };
        if (!isObject(e) || !isInt(e["offset"]) || !isInt(e["length"]) || typeof e["station_id"] !== "string" || typeof e["status"] !== "string") return null;
        const offset = e["offset"];
        const length = e["length"];
        if (length <= 0 || offset + length > jsonlSize || offset < start) return null;
        start = offset + length + 1;
        if (!ENTRY_STR.every((k) => k in e && strOrNull(e[k])) || !("lat" in e) || !("lon" in e) || !numOrNull(e["lat"]) || !numOrNull(e["lon"])) return null;
        const name = e["name"];
        if (e["name_folded"] !== (typeof name === "string" ? foldName(name) : null)) return null;
        const aliases = e["aliases"];
        if (!isObject(aliases) || !Object.values(aliases).every((ids) => Array.isArray(ids) && ids.every((x) => typeof x === "string"))) return null;
        if (!Object.hasOwn(e, "subordinate_offsets") || !(e["subordinate_offsets"] === null || isObject(e["subordinate_offsets"]))) return null;
        if (!Array.isArray(e["current_offsets"]) || !e["current_offsets"].every(isObject)) return null;
        try { if (isObject(e["subordinate_offsets"])) checkShape({ subordinate_offsets: e["subordinate_offsets"] }, e["station_id"]); } catch { return null; }
        for (const off of e["current_offsets"]) {
            if (!CURRENT_BASE_KEYS.every(k => Object.hasOwn(off, k)) || ![off["bin"], off["reference_bin"]].every(n => typeof n === "number" && Number.isSafeInteger(n) && n > 0)
                || typeof off["reference_station_id"] !== "string" || typeof off["licence_id"] !== "string" || !licences.has(off["licence_id"])) return null;
            const adjustments = CURRENT_ADJUSTMENTS.filter(k => Object.hasOwn(off, k));
            if (adjustments.length !== 0 && adjustments.length !== CURRENT_ADJUSTMENTS.length
                || !adjustments.every(k => off[k] === null || typeof off[k] === "number" && Number.isFinite(off[k]))) return null;
            const profile = adjustments.length === 0 ? "projected" : "full";
            if (currentProfile !== null && currentProfile !== profile) return null;
            currentProfile = profile;
        }
        const sets = e["sets"];
        if (!Array.isArray(sets) || !sets.every(isObject)) return null;
        for (const cs of sets) {
            if (!isObject(cs) || !SET_KEYS.every((k) => k in cs && strOrNull(cs[k]))) return null;
            if (Object.hasOwn(cs, "fallback") && !(cs["fallback"] === null || isObject(cs["fallback"]))) return null;
            if (isObject(cs["fallback"])) {
                try { checkShape({ constant_sets: [{ fallback: cs["fallback"] }] }, e["station_id"]); } catch { return null; }
            }
            if (bins && (!Array.isArray(cs["current_bins"]) || !cs["current_bins"].every((v) => typeof v === "number" && Number.isSafeInteger(v) && v > 0))) return null;
            if (privateSets) {
                if (!strOrNull(cs["source_record_id"]) || !strOrNull(cs["source_version"]) || !(cs["datum"] === null || isObject(cs["datum"]))) return null;
                try { checkShape({ constant_sets: [Object.fromEntries(PRIVATE_SET_KEYS.map(k => [k, cs[k]]))] }, e["station_id"]); } catch { return null; }
            }
            const cons = cs["constituents"];
            if (!Array.isArray(cons) || !cons.every((x) => typeof x === "string")) return null;
            // the same checks as indexDoc, for every status
            if (typeof cs["set_id"] !== "string" || !conventions.has(cs["convention_id"] as string) || !licences.has(cs["licence_id"] as string)) return null;
        }
        if (e["offsets_licence_id"] !== null && !licences.has(e["offsets_licence_id"] as string)) return null;
        if (e["status"] === "active") {
            if (e["recommended_set_id"] !== null && !sets.some((cs) => isObject(cs) && cs["set_id"] === e["recommended_set_id"])) return null;
            if (e["lat"] === null || e["lon"] === null) return null;
        }
        const own = isObject(e["subordinate_offsets"]) ? e["subordinate_offsets"] : null;
        if (!legacyOffsets && isObject(entry) && !Object.hasOwn(entry, "subordinate_offsets")
            && (e["reference_station_id"] !== null || e["offsets_licence_id"] !== null)) return null;
        if (!legacyOffsets && (e["reference_station_id"] !== str(own,"reference_station_id") || e["offsets_licence_id"] !== str(own,"licence_id"))) return null;
        const stored = { ...e, sets: sets.map(cs => ({ ...cs as JsonObject,
            fallback: Object.hasOwn(cs, "fallback") ? (cs as JsonObject)["fallback"] : null,
            current_bins: bins ? (cs as JsonObject)["current_bins"] : [],
        })) } as unknown as StoredEntry;
        const rec = stored.recommended_set_id === null ? undefined : stored.sets.find((cs) => cs.set_id === stored.recommended_set_id);
        // kind is derived, not trusted: from the recommended set here, and from the reference station below
        const indexed = entryFromStored({ ...stored, kind: rec ? kindOfQuantity(rec.quantity) : null });
        if (legacyOffsets) indexed.legacyOffsets = true;
        indexed.indexPresence = Object.freeze({ own: legacyOffsets ? "base" : isObject(entry) && Object.hasOwn(entry, "subordinate_offsets") ? "full" : "sparse",
            offsets: isObject(entry) && Object.hasOwn(entry, "current_offsets") ? currentProfile ?? "full" : "sparse",
            offsetFields: Object.freeze(e["current_offsets"].map(row => Object.freeze(Object.keys(row).sort()))),
            privateSets, bins, baseFallback, fallback: Object.freeze(sets.map(cs => Object.hasOwn(cs, "fallback"))) });
        out.push(indexed);
    }
    checkLinks(out);
    resolveKinds(out);
    const activeIds = new Set(out.filter(e => e.status === "active").map(e => e.station_id));
    if (out.some(e => e.stored.current_offsets.some(off => !activeIds.has(String(off["reference_station_id"]))))) return null;
    const given = stations as unknown as StoredEntry[];
    if (out.some((x, i) => x.status === "active" && x.kind !== (given[i]?.kind ?? null))) return null;
    return out;
}

/** @internal The station kind of a recommended set's quantity (spec 6.2 `kind`). */
export function kindOfQuantity(q: string | null): string | null {
    return q === "water_level" ? "tide" : q === "current" ? "current" : "other";
}

/**
 * @internal The links between stations, checked at load in every path (spec 6.1, CR D5): a station_id appears once
 * across the active stations and the tombstones; a (system, alias id) pair once; a set_id once among the active
 * stations' sets; and an active subordinate's reference_station_id names an active station. Throws invalid_release.
 */
export function checkLinks(entries: readonly IndexEntry[]): void {
    const ids = new Set<string>();
    const active = new Set<string>();
    for (const e of entries) {
        if (ids.has(e.station_id)) throw new InvalidReleaseError(`station_id ${e.station_id} appears twice`);
        ids.add(e.station_id);
        if (e.status === "active") active.add(e.station_id);
    }
    const aliases = new Set<string>();
    const sets = new Set<string>();
    for (const e of entries) {
        if (e.status !== "active") continue;
        for (const [system, list] of Object.entries(e.aliases)) {
            for (const id of list) {
                const k = JSON.stringify([system, id]);
                if (aliases.has(k)) throw new InvalidReleaseError(`the ${system} alias ${id} appears twice (at ${e.station_id})`);
                aliases.add(k);
            }
        }
        for (const cs of e.stored.sets) {
            const id = cs.set_id ?? "";
            if (sets.has(id)) throw new InvalidReleaseError(`set_id ${id} appears twice`);
            sets.add(id);
        }
        const ref = e.stored.reference_station_id;
        if (ref !== null && !active.has(ref)) throw new InvalidReleaseError(`station ${e.station_id}: reference_station_id ${ref} does not resolve`);
    }
}

/** @internal Resolve the kind of subordinate stations with offsets only (from their reference station). */
export function resolveKinds(entries: IndexEntry[]): void {
    const byId = new Map(entries.filter((e) => e.status === "active").map((e) => [e.station_id, e]));
    const kindOf = (e: IndexEntry, seen: Set<string>): string | null => {
        if (e.kind !== null) return e.kind;
        if (e.type === "subordinate" && e.reference_station_id && !seen.has(e.station_id)) {
            const ref = byId.get(e.reference_station_id);
            if (ref) {
                seen.add(e.station_id);
                return kindOf(ref, seen);
            }
        }
        return null;
    };
    for (const e of entries) if (e.status === "active" && e.kind === null) e.kind = kindOf(e, new Set());
}

// ------------------------------------------------------------------------------------------ objects

/** @internal */
export function constituentOf(c: JsonObject): Constituent {
    return Object.freeze({
        name: str(c, "name") ?? "", source_name: str(c, "source_name"), doodson: str(c, "doodson"),
        speed_deg_per_hour: num(c, "speed_deg_per_hour"), amplitude_m: num(c, "amplitude_m"), phase_deg: num(c, "phase_deg"),
        amp_uncertainty_m: num(c, "amp_uncertainty_m"), phase_uncertainty_deg: num(c, "phase_uncertainty_deg"),
        kept_reason: str(c, "kept_reason"), raw: c,
    });
}

/** @internal */
export function timeBaseOf(t: JsonObject): TimeBase {
    const corr = obj(t, "correction");
    return Object.freeze({
        code: en(t["code"], ["verified", "corrected", "unverified", "disputed"] as const),
        reason: str(t, "reason"), declared: str(t, "declared"), published: str(t, "published"),
        correction: corr === null ? null : Object.freeze({ from: str(corr, "from"), to: str(corr, "to") }),
        months_dropped: Object.freeze(arr(t, "months_dropped").filter((m): m is string => typeof m === "string")),
        decided_in: str(t, "decided_in"), decided_build_commit: str(t, "decided_build_commit"),
        evidence: Object.freeze(arr(t, "evidence").filter(isObject).map((e): TimeBaseEvidence => Object.freeze({
            comparator_kind: str(e, "comparator_kind"), comparator_id: str(e, "comparator_id"),
            distance_km: num(e, "distance_km"), lag_min: num(e, "lag_min"), detail: str(e, "detail"),
        }))),
    });
}

/** @internal */
export function buildOf(b: JsonObject): ProvenanceBuild {
    const tv = obj(b, "tool_versions");
    return Object.freeze({
        build_commit: str(b, "build_commit"), built_at: time(b["built_at"]), fetched_at: time(b["fetched_at"]),
        run_id: str(b, "run_id"), tool_versions: tv,
    });
}

function qcValues(v: Json | undefined): Readonly<Record<string, number | null>> | null {
    if (!isObject(v)) return null;
    return Object.freeze(Object.fromEntries(Object.entries(v)
        .filter((e): e is [string, number | null] => e[1] === null || typeof e[1] === "number")));
}

/** @internal */
export function validationOf(v: JsonObject): Validation {
    const p = obj(v, "previous_release");
    return Object.freeze({
        set_id: str(v, "set_id"), reference_source: str(v, "reference_source"), reference_station: str(v, "reference_station"),
        reference_distance_km: num(v, "reference_distance_km"), window: str(v, "window"),
        time_mae_min: num(v, "time_mae_min"), time_p95_min: num(v, "time_p95_min"), time_bias_min: num(v, "time_bias_min"),
        height_mae_m: num(v, "height_mae_m"), range_error_m: num(v, "range_error_m"),
        missed_events: num(v, "missed_events"), extra_events: num(v, "extra_events"),
        previous_release: p === null ? null : Object.freeze({
            time_mae_min: num(p, "time_mae_min"), time_p95_min: num(p, "time_p95_min"), time_bias_min: num(p, "time_bias_min"),
            height_mae_m: num(p, "height_mae_m"), range_error_m: num(p, "range_error_m"),
            missed_events: num(p, "missed_events"), extra_events: num(p, "extra_events"),
        }),
    });
}

/** The constants from one source record. */
export class ConstantSet {
    readonly set_id: string;
    readonly source: string;
    readonly source_type: SourceType | Other | null;
    readonly quantity: Quantity | Other | null;
    readonly source_record_id: string | null;
    readonly source_version: string | null;
    readonly record_span: RecordSpan | null;
    readonly datum: Datum | null;
    readonly fallback: Fallback | null;
    readonly qc_status: QcStatus | Other | null;
    readonly qc_flags: readonly QcFlag[];
    readonly dropped_constituents: readonly DroppedConstituent[];
    /** The time-base annotation of the record, or null (spec 4.5). */
    readonly time_base: TimeBase | null;
    readonly raw: JsonObject;
    readonly #recommended: boolean;
    readonly #convention: Convention;
    readonly #licence: Licence;
    readonly #validation: readonly Validation[];
    #constituents: readonly Constituent[] | null = null;
    #provenance: Provenance | null = null;

    /** @internal */
    constructor(raw: JsonObject, recommended: boolean, convention: Convention, licence: Licence, validation: readonly Validation[]) {
        this.raw = raw;
        this.set_id = str(raw, "set_id") ?? "";
        this.source = str(raw, "source") ?? "";
        this.source_type = en(raw["source_type"], ["official", "gauge", "model"] as const);
        this.quantity = en(raw["quantity"], ["water_level", "current"] as const);
        this.source_record_id = str(raw, "source_record_id");
        this.source_version = str(raw, "source_version");
        const span = obj(raw, "record_span");
        this.record_span = span === null ? null : recordSpanOf(span, this.set_id);
        const datum = obj(raw, "datum");
        this.datum = datum === null ? null : datumOf(datum);
        this.fallback = fallbackOf(obj(raw, "fallback"));
        this.qc_status = en(raw["qc_status"], QC_STATUSES);
        this.qc_flags = Object.freeze(arr(raw, "qc_flags").filter(isObject).map((f): QcFlag => Object.freeze({
            flag: en(f["flag"], ["time_base", "broken_record", "microtidal", "non_tidal_signal", "short_record",
                "sibling_disagreement", "carried_over", "fallback:time_base_disputed", "fallback:time_base_unresolved", "fallback:refused_fit", "fallback:short_record_uncalibrated", "fallback:short_record_long_period", "fallback:published_full_list", "fallback:reliability_withheld", "fallback:licence_reading", "fallback:datum_gate_failed", "fallback:not_in_otc_input", "fallback:historical_offsets"] as const) ?? "other",
            reason: str(f, "reason"), values: qcValues(f["values"]),
        })));
        this.dropped_constituents = Object.freeze(arr(raw, "dropped_constituents").filter(isObject).map(droppedConstituentOf));
        const tb = obj(raw, "time_base");
        this.time_base = tb === null ? null : timeBaseOf(tb);
        this.#recommended = recommended;
        this.#convention = convention;
        this.#licence = licence;
        this.#validation = validation;
        Object.freeze(this);
    }

    /** True for the station's recommended set. */
    get isRecommended(): boolean {
        return this.#recommended;
    }

    get convention(): Convention {
        return this.#convention;
    }

    get licence(): Licence {
        return this.#licence;
    }

    get provenance(): Provenance {
        if (this.#provenance === null) {
            const p = obj(this.raw, "provenance") ?? Object.freeze({});
            this.#provenance = provenanceOf(p);
        }
        return this.#provenance;
    }

    /** The station's validation rows for this set, ordered by window. */
    get validation(): readonly Validation[] {
        return this.#validation;
    }

    /** The constituents that the fit kept, in file order. */
    get constituents(): readonly Constituent[] {
        if (this.#constituents === null) {
            this.#constituents = Object.freeze(arr(this.raw, "constituents").filter(isObject).map(constituentOf));
        }
        return this.#constituents;
    }

    /** One constituent by its OTC canonical name (case-sensitive), or null. */
    constituent(name: string): Constituent | null {
        return this.constituents.find((c) => c.name === name) ?? null;
    }
}

const releaseOrigins = new WeakMap<Release, symbol>();

function originOf(release: Release): symbol {
    let token = releaseOrigins.get(release);
    if (!token) { token = Symbol('producing Release'); releaseOrigins.set(release, token); }
    return token;
}

/** An active station. */
export class Station {
    readonly source_records: readonly SourceRecord[];
    readonly recommended_is_fallback: boolean | null;
    readonly station_id: string;
    readonly name: string;
    readonly country: string | null;
    readonly lat: number;
    readonly lon: number;
    readonly type: StationType | Other | null;
    readonly kind: Kind | Other | null;
    readonly timezone: string | null;
    /** `{system: [ids]}`; single ids in the file become one-item lists. */
    readonly aliases: Readonly<Record<string, readonly string[]>>;
    readonly status: StationStatus | Other;
    readonly raw: JsonObject;
    readonly #sets: readonly ConstantSet[];
    readonly #recommended: ConstantSet | null;
    readonly #validation: readonly Validation[];
    readonly #offsets: SubordinateOffsets | null;
    readonly #origin: symbol;

    /** @internal */
    constructor(raw: JsonObject, entry: IndexEntry, release: Release) {
        this.raw = raw;
        this.#origin = originOf(release);
        this.recommended_is_fallback = typeof raw["recommended_is_fallback"] === "boolean" ? raw["recommended_is_fallback"] : null;
        this.source_records = Object.freeze(objects(raw, "source_records").map((r) => sourceRecordOf(r, release)));
        this.station_id = entry.station_id;
        this.name = str(raw, "name") ?? "";
        this.country = str(raw, "country");
        this.lat = entry.lat ?? NaN;
        this.lon = entry.lon ?? NaN;
        this.type = en(raw["type"], ["reference", "subordinate"] as const);
        this.kind = entry.kind === null ? null : en(entry.kind, ["tide", "current"] as const);
        this.timezone = str(raw, "timezone");
        this.aliases = Object.freeze(Object.fromEntries(Object.entries(entry.aliases).map(([k, v]) => [k, Object.freeze([...v])])));
        this.status = en(entry.status, ["active", "removed"] as const) ?? "other";   // "active" for a line with no status (CR2 DR28)
        this.#validation = Object.freeze(arr(raw, "validation").filter(isObject).map(validationOf));
        // the effective recommended set under commercial_only (spec 4.2, K-NC DR106), else the release's
        const recId = release._recommendedId(entry);
        this.#sets = Object.freeze(arr(raw, "constant_sets").filter(isObject).map((cs) => {
            const setId = str(cs, "set_id");
            const rows = this.#validation.filter((v) => v.set_id === setId)
                .map((v, i) => [v, i] as const)
                .sort((a, b) => cmp(a[0].window ?? "", b[0].window ?? "") || a[1] - b[1]).map((x) => x[0]);
            const conv = release.convention(str(cs, "convention_id") ?? "");
            const lic = release.licence(str(cs, "licence_id") ?? "");
            // load checked both links (indexDoc); a miss here is a broken release, not a null to hide
            if (!conv || !lic) throw new InvalidReleaseError(`set ${String(setId)} of ${entry.station_id}: a convention or licence does not resolve`);
            return new ConstantSet(cs, recId !== null && setId === recId, conv, lic, Object.freeze(rows));
        }));
        this.#recommended = this.#sets.find((s) => s.isRecommended) ?? null;
        const off = obj(raw, "subordinate_offsets");
        this.#offsets = off === null ? null : subordinateOffsetsOf(off);
        Object.freeze(this);
    }

    /** @internal True if this station was read from release `r`. */
    _from(r: Release): boolean {
        return this.#origin === originOf(r);
    }

    get isReference(): boolean {
        return this.type === "reference";
    }

    get isSubordinate(): boolean {
        return this.type === "subordinate";
    }

    get isTide(): boolean {
        return this.kind === "tide";
    }

    get isCurrent(): boolean {
        return this.kind === "current";
    }

    /** The recommended constant set, or null (a subordinate station with offsets only). */
    get recommendedSet(): ConstantSet | null {
        return this.#recommended;
    }

    /**
     * The recommended set first, then the others by set_id. Sets with qc_status no_constants (no fitted
     * constants) are left out unless includeNoConstants is true.
     */
    constantSets(options: ConstantSetsOptions = {}): readonly ConstantSet[] {
        const inc = validateConstantSetsOptions(options);
        const sets = this.#sets.filter((s) => inc || s.qc_status !== "no_constants");
        const rec = sets.filter((s) => s.isRecommended);
        const rest = sets.filter((s) => !s.isRecommended).sort((a, b) => cmp(a.set_id, b.set_id));
        return Object.freeze([...rec, ...rest]);
    }

    /** One constant set by its id, or null. */
    constantSet(setId: string): ConstantSet | null {
        return this.#sets.find((s) => s.set_id === setId) ?? null;
    }

    /** The offsets of a subordinate station, or null. */
    get subordinateOffsets(): SubordinateOffsets | null {
        return this.#offsets;
    }

    /** Every validation row of the station, in file order. */
    get validation(): readonly Validation[] {
        return this.#validation;
    }
}

/** Order by Unicode code point (as Python, Ruby and C compare), not by UTF-16 code unit (PK08 T82). */
function cmp(a: string, b: string): number {
    if (a === b) return 0;
    const n = Math.min(a.length, b.length);
    for (let i = 0; i < n; i++) {
        const x = a.codePointAt(i) as number;
        const y = b.codePointAt(i) as number;
        if (x !== y) return x < y ? -1 : 1;
        if (x > 0xffff) i++;
    }
    return a.length < b.length ? -1 : a.length > b.length ? 1 : 0;
}

/** @internal */
export { cmp as compareCodePoints };

function haversine(lat1: number, lon1: number, lat2: number, lon2: number): number {
    const p1 = lat1 * DEG;
    const p2 = lat2 * DEG;
    const dp = p2 - p1;
    const dl = (lon2 - lon1) * DEG;
    const a = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
    return 2 * EARTH_R_KM * Math.asin(Math.min(1, Math.sqrt(a)));
}

/** @internal */
export function checkNumber(v: unknown, what: string, lo: number, hi: number): number {
    if (typeof v !== "number" || !Number.isFinite(v) || v < lo || v > hi) {
        throw new InvalidArgumentError(`${what} must be a number from ${lo} to ${hi}; got ${JSON.stringify(v)}`);
    }
    return v;
}

/** `limit` is an integer of 1 or more, or absent / null for no limit (spec 4.4, CR D36). */
/** @internal */
export function checkLimit(v: unknown): number | null {
    if (v === undefined || v === null) return null;
    if (typeof v !== "number" || !Number.isInteger(v) || v < 1) throw new InvalidArgumentError(`limit must be an integer of 1 or more, or null; got ${JSON.stringify(v)}`);
    return v;
}

interface CheckedFilters {
    country: string | null;
    type: string | null;
    kind: string | null;
    source: string | null;
    sourceType: string | null;
    includeFlagged: boolean;
    includeFallback: boolean;
}

/** @internal */
export function checkFilters(f: StationFilters | undefined | null): CheckedFilters {
    if (f !== undefined && f !== null && typeof f !== "object") throw new InvalidArgumentError("filters must be an object");
    const out: CheckedFilters = { country: null, type: null, kind: null, source: null, sourceType: null, includeFlagged: false, includeFallback: false };
    for (const k of ["country", "type", "kind", "source", "sourceType"] as const) {
        const v: unknown = f ? f[k] : undefined;
        if (v === undefined || v === null) continue;
        if (typeof v !== "string") throw new InvalidArgumentError(`filter ${k} must be a string; got ${JSON.stringify(v)}`);
        out[k] = v;
    }
    for (const k of ["includeFlagged", "includeFallback"] as const) {
        const v = f?.[k];
        if (v !== undefined && typeof v !== "boolean") throw new InvalidArgumentError(`${k} must be a boolean`);
        out[k] = v ?? false;
    }
    return out;
}

const STATION_TYPE_VALUES = ["reference", "subordinate"] as const;
const KINDS = ["tide", "current"] as const;
const SOURCE_TYPES = ["official", "gauge", "model"] as const;
const QUANTITIES = ["water_level", "current"] as const;

function occurrences(text: string, sub: string): number[] {
    const out: number[] = [];
    let i = text.indexOf(sub);
    while (i !== -1) {
        out.push(i);
        i = text.indexOf(sub, i + 1);
    }
    return out;
}

function countBy(values: Iterable<string | null>): Record<string, number> {
    // a Map: a value such as constructor or __proto__ is counted like any other, never read from Object.prototype
    const out = new Map<string, number>();
    for (const v of values) if (v !== null) out.set(v, (out.get(v) ?? 0) + 1);
    return Object.freeze(Object.fromEntries([...out].sort((a, b) => cmp(a[0], b[0]))));
}

/** The source of every subordinate_offsets in format 1.0 (spec 4.2, K-NC DR106). */
const OFFSETS_SOURCE = "noaa";

const LRU_SIZE = 256;
// The reference links a walk follows (spec 6.2 kind, 4.6 attribution).
const MAX_LINKS = 16;

const PREPARED_RELEASE = Symbol('private prepared Release fields');
const OWNER_ARGUMENTS = Symbol('private authentic ownership prerequisites');
type OwnerArguments = Extract<C.SelectedArguments, { member_id: 'Release.reference_station' | 'Release.subordinates_of' | 'Release.attribution' }>;
/** @internal Authentic ordered native ownership outcomes prepared outside B01. */
export interface PreparedOwnerArguments {
    readonly [OWNER_ARGUMENTS]: true;
    readonly receiver: Release;
    readonly request: OwnerArguments;
    readonly outcomes: ReadonlyArray<{ readonly entry: IndexEntry | null; readonly error: Error | null }>;
    readonly error: Error | null;
}
/** @internal Original array branch; owner/byId phases are distinct native prerequisites. */
export function validateAttributionList(stations: unknown): void {
    if (stations !== null && stations !== undefined && !Array.isArray(stations)) throw new InvalidArgumentError('stations must be a list of Station objects');
}
/** @internal Genuine source-owner preparation, with no attribution/reference query. */
export function prepareOwnerArguments(receiver: Release, request: OwnerArguments): PreparedOwnerArguments {
    return Release[OWNER_ARGUMENTS](receiver, request);
}
/** @internal Complete independently owned graph produced before native materialization. */
export interface PreparedReleaseFields {
    readonly authenticHeader: ReleaseHeader;
    readonly entries: IndexEntry[];
    readonly eager: boolean;
    readonly header: JsonObject;
    readonly commercialOnly: boolean;
    readonly commercialBasis: "strict" | "as_published_upstream";
    readonly historicalPolicy: "fallback" | "exclude";
    readonly source: StationSource;
    readonly lru: number;
    readonly datestamp: string;
    readonly created: Date | null;
    readonly format_version: string;
    readonly concept_doi: string | null;
    readonly zenodo_version_doi: string | null;
    readonly source_versions: Readonly<Record<string, string>>;
    readonly build_commit: string | null;
    readonly changelog_url: string | null;
    readonly files: readonly FileInfo[];
    readonly pos: Map<IndexEntry, number>;
    readonly active: IndexEntry[];
    readonly byId: Map<string, IndexEntry>;
    readonly tombById: Map<string, IndexEntry>;
    readonly alias: Map<string, Map<string, IndexEntry>>;
    readonly subs: Map<string, IndexEntry[]>;
    readonly conventions: readonly Convention[];
    readonly licences: readonly Licence[];
    readonly effective: Map<string, StoredSet | null> | null;
    readonly cache: Map<string, Station | Tombstone>;
}
type PreparedReleaseHeader = ReleaseHeader & { readonly [PREPARED_RELEASE]: PreparedReleaseFields };
function preparedHeader(header: ReleaseHeader): header is PreparedReleaseHeader { return PREPARED_RELEASE in header; }
type ReleasePolicyContext = Pick<PreparedReleaseFields, 'header' | 'source' | 'pos' | 'datestamp' | 'licences'>;

/** @internal Installs genuine private brands; graph preparation is already complete. */
export function releaseFromPrepared(fields: PreparedReleaseFields): Release {
    const header: PreparedReleaseHeader = { ...fields.authenticHeader, [PREPARED_RELEASE]: fields };
    return new Release(header, fields.entries, fields.source, fields.files, fields.eager, fields.zenodo_version_doi);
}

/** @internal Exact existing constructor preparation, including checked lazy policy reads. */
export function prepareReleaseFields(header: ReleaseHeader, entries: IndexEntry[], source: StationSource, files: readonly FileInfo[], eager: boolean,
        zenodoVersionDoi: string | null, warn: (message: string) => void = () => undefined, commercialOnly = false, commercialBasis: "strict" | "as_published_upstream" = "strict", historicalPolicy: "fallback" | "exclude" = "fallback"): PreparedReleaseFields {
    const cache = new Map<string, Station | Tombstone>();
    const prepared_header = header.raw;
    const prepared_commercialOnly = commercialOnly; const prepared_commercialBasis = commercialBasis; const prepared_historicalPolicy = historicalPolicy;
    const prepared_source = source;
    const prepared_lru = eager ? Infinity : LRU_SIZE;
    const r = header.release;
    const prepared_datestamp = str(r, "datestamp") ?? "";
    const prepared_created = checkedTime(r["created"], "release.created");
    const prepared_format_version = header.format_version;
    const prepared_concept_doi = str(r, "concept_doi");
    const prepared_zenodo_version_doi = zenodoVersionDoi;
    const prepared_source_versions = Object.freeze(Object.fromEntries(Object.entries(obj(r, "source_versions") ?? {})
        .filter((e): e is [string, string] => typeof e[1] === "string")));
    const prepared_build_commit = str(r, "build_commit");
    const prepared_changelog_url = str(r, "changelog_url");
    const prepared_files = Object.freeze(files.map((f) => Object.freeze({ ...f })));
    const prepared_pos = new Map(entries.map((e, i) => [e, i]));
    const prepared_active = entries.filter((e) => e.status === "active").sort((a, b) => cmp(a.station_id, b.station_id));
    const prepared_byId = new Map(prepared_active.map((e) => [e.station_id, e]));
    const prepared_tombById = new Map(entries.filter((e) => e.status === "removed").map((e) => [e.station_id, e]));
    for (const e of entries) {
        // a status this SDK does not know (a newer minor's value): not a station, not a tombstone, in no query and no
        // count; said once, at load (CR2 DR8)
        if (e.status !== "active" && e.status !== "removed") {
            warn(`station ${e.station_id} has the status ${JSON.stringify(e.status)}, which this SDK does not know: it is left out of every query`);
        }
    }
    const prepared_alias = new Map<string, Map<string, IndexEntry>>();
    for (const e of prepared_active) {
        for (const [system, ids] of Object.entries(e.aliases)) {
            let m = prepared_alias.get(system);
            if (!m) prepared_alias.set(system, (m = new Map()));
            for (const id of ids) if (!m.has(id)) m.set(id, e);
        }
    }
    const prepared_subs = new Map<string, IndexEntry[]>();
    for (const e of prepared_active) {
        if (e.type === "subordinate" && e.reference_station_id) {
            const l = prepared_subs.get(e.reference_station_id) ?? [];
            l.push(e);
            prepared_subs.set(e.reference_station_id, l);
        }
    }
    const prepared_conventions = Object.freeze(header.conventions.map(conventionOf));
    const prepared_licences = Object.freeze(header.licences.map(licenceOf));
    const policy: ReleasePolicyContext = { header: prepared_header, source: prepared_source, pos: prepared_pos, datestamp: prepared_datestamp, licences: prepared_licences };
    const prepared_effective = commercialOnly ? new Map(prepared_active.map((e) => [e.station_id, releaseEffectiveSet(policy, e)])) : null;

    return { authenticHeader: header, entries, eager, cache, header: prepared_header, commercialOnly: prepared_commercialOnly, commercialBasis: prepared_commercialBasis, historicalPolicy: prepared_historicalPolicy, source: prepared_source, lru: prepared_lru, datestamp: prepared_datestamp, created: prepared_created, format_version: prepared_format_version, concept_doi: prepared_concept_doi, zenodo_version_doi: prepared_zenodo_version_doi, source_versions: prepared_source_versions, build_commit: prepared_build_commit, changelog_url: prepared_changelog_url, files: prepared_files, pos: prepared_pos, active: prepared_active, byId: prepared_byId, tombById: prepared_tombById, alias: prepared_alias, subs: prepared_subs, conventions: prepared_conventions, licences: prepared_licences, effective: prepared_effective };
}

function releaseDoc(context: ReleasePolicyContext, e: IndexEntry): JsonObject {
    const i = context.pos.get(e);
    if (i === undefined) throw new InvalidReleaseError(`station ${e.station_id} is not an entry of release ${context.datestamp}`);
    return context.source.doc(e, i);
}

function releasePolicyEntry(context: ReleasePolicyContext, e: IndexEntry): void {
    const presence = e.indexPresence;
    if (!presence || e.policyHydrated || presence.own !== "base" && presence.bins && presence.fallback.every(Boolean)) return;
    const header = parseHeader(context.header);
    const doc = releaseDoc(context, e);
    const actual = indexDoc(doc, header, e.offset, e.length,
        new Set(header.conventions.map(c => String(c["convention_id"]))),
        new Set(header.licences.map(l => String(l["licence_id"]))));
    e.stored = { ...e.stored, subordinate_offsets: presence.own === "base" ? actual.stored.subordinate_offsets : e.stored.subordinate_offsets,
        sets: e.stored.sets.map((cs, i) => ({ ...cs,
            fallback: presence.fallback[i] ? cs.fallback : actual.stored.sets[i]?.fallback ?? null,
            current_bins: presence.bins ? cs.current_bins : actual.stored.sets[i]?.current_bins ?? [],
        })) };
    e.policyHydrated = true;
}

function releaseCommercial(licences: readonly Licence[], licenceId: string | null): boolean {
    return licenceId !== null && licences.find((l) => l.licence_id === licenceId)?.commercial_use === true;
}

function releaseEffectiveSet(context: ReleasePolicyContext, e: IndexEntry): StoredSet | null {
    releasePolicyEntry(context, e);
    const sets = e.stored.sets;
    const rec = e.recommended_set_id === null ? undefined : sets.find((cs) => cs.set_id === e.recommended_set_id);
    if (!rec) return null;
    if (releaseCommercial(context.licences, rec.licence_id)) return rec;
    const q = en(rec.quantity, QUANTITIES);
    if (q === null) return null;
    for (const status of ["ok", "flagged"]) {
        const hit = sets.find((cs) => cs.qc_status === status && en(cs.quantity, QUANTITIES) === q && releaseCommercial(context.licences, cs.licence_id));
        if (hit) return hit;
    }
    return null;
}

interface SourceReceiver {
    open(): void;
    own(station: Station): Station;
    row(stationId: string): JsonObject;
}
const sourceReceivers = new WeakMap<Release, SourceReceiver>();

/** @internal Borrow the genuine native owner without materializing a public query. */
export function releaseSourceReceiver(owner: Release): SourceReceiver {
    const receiver = sourceReceivers.get(owner);
    if (!receiver) throw new InvalidArgumentError('a native Release owner is required');
    return receiver;
}

/** One loaded release. It is immutable and has every query method. */
export class Release {
    /** @internal Module-private exact ownership preparation bridge; never called inside B01. */
    static [OWNER_ARGUMENTS](receiver: Release, request: OwnerArguments): PreparedOwnerArguments {
        const outcomes: Array<{ entry: IndexEntry | null; error: Error | null }> = [];
        try {
            receiver.#open();
            if (request.member_id === 'Release.attribution') {
                validateAttributionList(request.arguments.stations);
                for (const station of request.arguments.stations ?? []) {
                    try { outcomes.push({ entry: receiver.#attributionEntry(station), error: null }); }
                    catch (error) {
                        if (!(error instanceof Error)) throw error;
                        outcomes.push({ entry: null, error });
                        break;
                    }
                }
            } else {
                outcomes.push({ entry: receiver.#ownEntry(request.arguments.station, request.member_id === 'Release.reference_station' ? 'referenceStation' : 'subordinatesOf'), error: null });
            }
            return { [OWNER_ARGUMENTS]: true, receiver, request, outcomes, error: null };
        } catch (error) {
            if (!(error instanceof Error)) throw error;
            return { [OWNER_ARGUMENTS]: true, receiver, request, outcomes, error };
        }
    }
    readonly datestamp: string;
    readonly created: Date | null;
    readonly format_version: string;
    /** The all-versions (concept) DOI, from the release document, or null. */
    readonly concept_doi: string | null;
    /**
     * The DOI of this release's own Zenodo version, from the pointer or index entry the SDK read for it, or null
     * (always null for a file; spec 4.3).
     */
    readonly zenodo_version_doi: string | null;
    readonly source_versions: Readonly<Record<string, string>>;
    readonly build_commit: string | null;
    readonly changelog_url: string | null;
    /** The release's files (spec 4.3.1). */
    readonly files: readonly FileInfo[];
    readonly #header: JsonObject;
    readonly #commercialOnly: boolean;
    readonly #commercialBasis: "strict" | "as_published_upstream";
    readonly #historicalPolicy: "fallback" | "exclude";
    readonly #source: StationSource;
    readonly #active: IndexEntry[];
    readonly #pos: Map<IndexEntry, number>;
    readonly #byId: Map<string, IndexEntry>;
    readonly #tombById: Map<string, IndexEntry>;
    readonly #alias: Map<string, Map<string, IndexEntry>>;
    readonly #subs: Map<string, IndexEntry[]>;
    readonly #conventions: readonly Convention[];
    readonly #licences: readonly Licence[];
    /** commercial_only (spec 4.2, K-NC DR106): station_id -> its effective recommended set (or null); null without it. */
    readonly #effective: Map<string, StoredSet | null> | null;
    readonly #cache: Map<string, Station | Tombstone>;
    readonly #lru: number;
    #closed = false;

    /** @internal */
    constructor(header: ReleaseHeader, entries: IndexEntry[], source: StationSource, files: readonly FileInfo[], eager: boolean,
        zenodoVersionDoi: string | null, warn: (message: string) => void = () => undefined, commercialOnly = false, commercialBasis: "strict" | "as_published_upstream" = "strict", historicalPolicy: "fallback" | "exclude" = "fallback") {
        const fields = preparedHeader(header) ? header[PREPARED_RELEASE] : prepareReleaseFields(header, entries, source, files, eager, zenodoVersionDoi, warn, commercialOnly, commercialBasis, historicalPolicy);
        this.#header = fields.header;
        this.#commercialOnly = fields.commercialOnly;
        this.#commercialBasis = fields.commercialBasis;
        this.#historicalPolicy = fields.historicalPolicy;
        this.#source = fields.source;
        this.#lru = fields.lru;
        this.datestamp = fields.datestamp;
        this.created = fields.created;
        this.format_version = fields.format_version;
        this.concept_doi = fields.concept_doi;
        this.zenodo_version_doi = fields.zenodo_version_doi;
        this.source_versions = fields.source_versions;
        this.build_commit = fields.build_commit;
        this.changelog_url = fields.changelog_url;
        this.files = fields.files;
        this.#pos = fields.pos;
        this.#active = fields.active;
        this.#byId = fields.byId;
        this.#tombById = fields.tombById;
        this.#alias = fields.alias;
        this.#subs = fields.subs;
        this.#conventions = fields.conventions;
        this.#licences = fields.licences;
        this.#effective = fields.effective;
        this.#cache = fields.cache;
        sourceReceivers.set(this, {
            open: () => this.#open(),
            own: station => { this.#ownEntry(station, 'check_station_origin'); return station; },
            row: stationId => {
                this.#open();
                const entry = this.#byId.get(stationId);
                if (!entry) throw new StationNotFoundError(stationId);
                return this.#station(entry).raw;
            },
        });
        Object.freeze(this);
    }

    /** @internal The untouched release metadata and astronomical resources for the native predictor. */
    get _header(): JsonObject { this.#open(); return this.#header; }

/** @internal */
get _commercialOnly(): boolean { this.#open(); return this.#commercialOnly; }
/** @internal */
_betterHistoricalPath(station: Station): boolean {
    this.#open(); const e=this.#byId.get(station.station_id);
    if(!e)return false;
    const rid=this._recommendedId(e);
    return e.stored.sets.some(cs=>cs.set_id===rid&&cs.qc_status!==null&&WITH_CONSTANTS.has(cs.qc_status))
        ||this.#ordinaryPaths(e,{country:null,type:null,kind:null,source:null,sourceType:null,includeFlagged:false,includeFallback:false}).length>0;
}
async heights(station: Station|string, options: prediction.HeightWindowOptions): Promise<HeightSeries> { this.#open(); return (await import('./predict/engine.js')).heights(this,station,options); }
async heightsAt(station: Station|string, times: readonly Date[], options: prediction.HeightOptions = {}): Promise<HeightSeries> { this.#open(); return (await import('./predict/engine.js')).heightsAt(this,station,times,options); }
async extremes(station: Station|string, options: Omit<prediction.HeightWindowOptions,'stepS'>): Promise<ExtremeList> { this.#open(); return (await import('./predict/engine.js')).extremes(this,station,options); }
async currents(station: Station|string, options: prediction.CurrentWindowOptions): Promise<CurrentSeries> { this.#open(); return (await import('./predict/engine.js')).currents(this,station,options); }
async currentEvents(station: Station|string, options: Omit<prediction.CurrentWindowOptions,'stepS'>): Promise<CurrentEventList> { this.#open(); return (await import('./predict/engine.js')).currentEvents(this,station,options); }
datums(station: Station|string, options: prediction.DatumOptions = {}): DatumInfo|readonly DatumInfo[]|null { this.#open(); return predictionDatums(this,station,options); }
ranges(station: Station|string, options: prediction.RangeOptions = {}): Ranges { this.#open(); return predictionRanges(this,station,options); }
async astroTable(id: string|null = null): Promise<AstroTable|null> { this.#open(); return (await import('./predict/engine.js')).astroTable(this,id); }
get historicalOffsetsPolicy()
: "fallback" | "exclude" { this.#open(); return this.#historicalPolicy; }

    #setEligible(cs: StoredSet, f: CheckedFilters, offsetsLicence: string | null = null): boolean {
        if (cs.qc_status === null || !WITH_CONSTANTS.has(cs.qc_status)) return false;
        if (cs.fallback !== null ? !f.includeFallback : cs.qc_status !== 'ok' && !f.includeFlagged) return false;
        if (this.#commercialOnly) {
            if (this.#commercialBasis === 'strict' && cs.fallback?.['reason'] === 'licence_reading') return false;
            if (!this.#commercial(cs.licence_id) || offsetsLicence !== null && !this.#commercial(offsetsLicence)) return false;
        }
        return true;
    }
    #historicalEligible(e: IndexEntry, paths: readonly StoredSet[]): boolean {
        this.#policyEntry(e);
        const own = e.stored.subordinate_offsets;
        if (!own?.['offset_id'] || this.#historicalPolicy === 'exclude') return false;
        const rid = this._recommendedId(e);
        if (e.stored.sets.some(cs => cs.set_id === rid && cs.qc_status !== null && WITH_CONSTANTS.has(cs.qc_status)) || paths.length > 0) return false;
        const reference = this.#byId.get(str(own,'reference_station_id') ?? '');
        if (reference) this.#policyEntry(reference);
        const cs = reference?.stored.sets.find(cs => cs.source === 'noaa' && cs.quantity === 'water_level' && cs.qc_status !== null && WITH_CONSTANTS.has(cs.qc_status));
        if (!cs || cs.qc_status !== 'ok' || cs.fallback !== null || !cs.set_id?.startsWith(`${reference?.station_id}/`)) return false;
        const raw = objects(this.#doc(reference as IndexEntry),'constant_sets').find(r => r['set_id'] === cs.set_id);
        const binding = obj(obj(own,'provenance'),'reference_binding');
        if (!raw || raw['source_record_id'] !== binding?.['noaa_id']) return false;
        if (this.#commercialOnly && (!this.#commercial(str(own,'licence_id')) || !this.#commercial(cs.licence_id))) return false;
        const convention = this.convention(cs.convention_id ?? '');
        if (!convention || convention.v0_model !== 'schureman_tcd' || convention.nodal_handling !== 'f_u_at_prediction') return false;
        const datum = obj(raw,'datum');
        if (datum?.['chart_datum'] !== 'mllw' || num(datum,'msl_offset_m') === null || obj(datum,'named')?.['mllw'] !== 0 || obj(obj(datum,'basis'),'mllw')?.['kind'] !== 'published') return false;
        try {
            const table=predictionAstroTable(this,str(convention.raw,'astro_table_id') ?? '');
            if(!table)return false;
            for(const constituent of objects(raw,'constituents'))table._row(str(constituent,'name') ?? '');
            return true;
        } catch(error) {if(error instanceof X.OpenTideConstantsError)return false;throw error;}
    }
    #ordinaryPaths(e: IndexEntry, f: CheckedFilters): StoredSet[] {
        this.#policyEntry(e);
        const paths = e.stored.sets.filter(cs => this.#setEligible(cs,f));
        if (!e.stored.subordinate_offsets?.['offset_id']) {
            const reference = this.#byId.get(e.reference_station_id ?? '');
            if (reference) this.#policyEntry(reference);
            const cs = reference?.stored.sets.find(cs => cs.source === 'noaa' && cs.quantity === 'water_level' && cs.qc_status !== null && WITH_CONSTANTS.has(cs.qc_status));
            if (cs && this.#setEligible(cs,f,e.offsets_licence_id)) paths.push(cs);
        }
        for (const off of e.stored.current_offsets) {
            const reference = this.#byId.get(str(off,'reference_station_id') ?? '');
            if (reference) this.#policyEntry(reference);
            const bin = num(off,'bin'), refBin = num(off,'reference_bin');
            if (bin === null || refBin === null || !Number.isSafeInteger(bin) || !Number.isSafeInteger(refBin) || bin < 1 || refBin < 1) continue;
            const cs = reference?.stored.sets.find(cs => cs.quantity === 'current' && cs.qc_status !== null && WITH_CONSTANTS.has(cs.qc_status) && cs.current_bins.includes(refBin));
            if (cs && this.#setEligible(cs,f,str(off,'licence_id'))) paths.push(cs);
        }
        return paths;
    }
    #matches(e: IndexEntry, f: CheckedFilters): boolean {
        if (f.country !== null && e.country !== f.country || f.type !== null && en(e.type,STATION_TYPE_VALUES) !== f.type || f.kind !== null && en(e.kind,KINDS) !== f.kind) return false;
        const paths: (StoredSet | JsonObject)[] = this.#ordinaryPaths(e,f);
        const defaultPaths = this.#ordinaryPaths(e,{...f,includeFlagged:false,includeFallback:false});
        if (this.#historicalEligible(e,defaultPaths) && e.stored.subordinate_offsets) paths.push(e.stored.subordinate_offsets);
        return paths.some(cs => (f.source === null || cs.source === f.source) && (f.sourceType === null || en(cs.source_type,SOURCE_TYPES) === f.sourceType));
    }

    #commercial(licenceId: string | null): boolean {
        return releaseCommercial(this.#licences, licenceId);
    }

    /**
     * The effective recommended set under commercial_only (spec 4.2, K-NC DR106), from the entry's sets in file order:
     * the release's recommended set when its licence allows commercial use; otherwise the first set of the same typed
     * quantity, qc_status ok, with a commercial licence; then the same with flagged; otherwise null. A set with no
     * quantity never matches.
     */
    /** @internal The set_id a Station of this entry gives as recommended (the effective one under commercial_only). */
    _recommendedId(e: IndexEntry): string | null {
        if (this.#effective === null) return e.recommended_set_id;
        return this.#effective.get(e.station_id)?.set_id ?? null;
    }



    /**
     * The licences of a station's tide source under commercial_only (spec 4.2, K-NC DR106): its effective recommended
     * set; else the one-link offsets path (the reference station's first set in file order from the offsets' source,
     * water_level, ok or flagged), usable only when the offsets' licence and that set's licence allow commercial use;
     * else none (no usable tides).
     */
    #tideSourceLicences(e: IndexEntry): string[] {
        const eff = this.#effective?.get(e.station_id) ?? null;
        if (eff !== null) return eff.licence_id === null ? [] : [eff.licence_id];
        const refId = e.stored.reference_station_id;
        if (refId === null && e.offsets_licence_id === null) return [];
        const ref = refId === null ? undefined : this.#byId.get(refId);
        if (!ref) return [];
        const refSet = ref.stored.sets.find((cs) => cs.source === OFFSETS_SOURCE && en(cs.quantity, QUANTITIES) === "water_level"
            && cs.qc_status !== null && WITH_CONSTANTS.has(cs.qc_status));
        if (!refSet || refSet.licence_id === null) return [];
        const out = [refSet.licence_id, ...(e.offsets_licence_id ? [e.offsets_licence_id] : [])];
        return out.every((id) => this.#commercial(id)) ? out : [];
    }

    /** @internal Release the file handle (stream mode). After it every query fails with io (spec 4.2, CR D21). */
    _close(): void {
        if (!this.#closed) {
            this.#closed = true;
            this.#source.close();
        }
    }

    /** @internal A function that releases the file handle without holding this Release (for a FinalizationRegistry). */
    _closer(): () => void {
        const source = this.#source;
        return () => source.close();
    }

    /** Every query on a closed release fails with io, the same in eager and stream mode (CR D21). */
    #open(): void {
        if (this.#closed) throw new FileError("the release is closed", { path: `release ${this.datestamp}` });
    }

    /** The station LRU (stream mode, spec 6.2): a hit becomes the newest entry; past the size, the oldest goes. */
    #cached(key: string): Station | Tombstone | undefined {
        const hit = this.#cache.get(key);
        if (hit !== undefined) {
            this.#cache.delete(key);
            this.#cache.set(key, hit);
        }
        return hit;
    }

    #remember(key: string, v: Station | Tombstone): void {
        this.#cache.set(key, v);
        while (this.#cache.size > this.#lru) {
            const first = this.#cache.keys().next().value;
            if (first === undefined) break;
            this.#cache.delete(first);
        }
    }

    #doc(e: IndexEntry): JsonObject {
        return releaseDoc({ header: this.#header, source: this.#source, pos: this.#pos, datestamp: this.datestamp, licences: this.#licences }, e);
    }

    /** Fill only uncached policy summaries through the existing checked lazy read; no full station is retained. */
    #policyEntry(e: IndexEntry): void {
        releasePolicyEntry({ header: this.#header, source: this.#source, pos: this.#pos, datestamp: this.datestamp, licences: this.#licences }, e);
    }

    #station(e: IndexEntry): Station {
        const hit = this.#cached(e.station_id);
        if (hit instanceof Station) return hit;
        const s = new Station(this.#doc(e), e, this);
        this.#remember(e.station_id, s);
        return s;
    }

    get conventions(): readonly Convention[] {
        this.#open();
        return this.#conventions;
    }

    convention(conventionId: string): Convention | null {
        this.#open();
        return this.#conventions.find((c) => c.convention_id === conventionId) ?? null;
    }

    get licences(): readonly Licence[] {
        this.#open();
        return this.#licences;
    }

    licence(licenceId: string): Licence | null {
        this.#open();
        return this.#licences.find((l) => l.licence_id === licenceId) ?? null;
    }

    /** The constituent names used by any set, sorted. */
    get constituentNames(): readonly string[] {
        this.#open();
        const names = new Set<string>();
        for (const e of this.#active) for (const n of e.constituent_names) names.add(n);
        return Object.freeze([...names].sort(cmp));
    }

    get stats(): Stats {
        this.#open();
        const a = this.#active;
        // the typed values, as the Station reports them (CR2 DR7)
        return statsOf(countBy(a.map((e) => en(e.type, STATION_TYPE_VALUES))), countBy(a.map((e) => en(e.kind, KINDS))),
            countBy(a.map((e) => e.country)), countBy(a.flatMap((e) => e.set_sources)), countBy(a.flatMap((e) => e.set_qc_statuses)));
    }

    /** The number of active stations. */
    get stationCount(): number {
        this.#open();
        return this.#active.length;
    }

    get tombstoneCount(): number {
        this.#open();
        return this.#tombById.size;
    }

    /**
     * The dataset citation (spec 4.6): the year is the first four digits of the datestamp, the link is the concept
     * DOI (or the release URL when there is none), and the version DOI follows when the release has one.
     */
    get citation(): string {
        const year = this.datestamp.slice(0, 4);
        const link = this.concept_doi ? `https://doi.org/${this.concept_doi}` : `https://data.opentideconstants.org/OTC_${this.datestamp}.json`;
        const version = this.zenodo_version_doi ? ` (version DOI: https://doi.org/${this.zenodo_version_doi})` : "";
        return `OpenTideConstants contributors (${year}). OpenTideConstants, release ${this.datestamp} [Data set]. ${link}${version}`;
    }

    /** An active station by its OTC id, or null. */
    station(stationId: string): Station | null {
        this.#open();
        const e = this.#byId.get(stationId);
        return e ? this.#station(e) : null;
    }

    /** An active station by its OTC id; station_not_found or station_removed otherwise. */
    requireStation(stationId: string): Station {
        this.#open();
        const s = this.station(stationId);
        if (s) return s;
        const t = this.tombstone(stationId);
        // the message names the reason as the file gives it, not the enum value ("other" for an unknown one)
        if (t) throw new StationRemovedError(stationId, t, str(t.raw, "removed_reason"));
        throw new StationNotFoundError(stationId);
    }

    /** The tombstone of a removed station, or null. */
    tombstone(stationId: string): Tombstone | null {
        this.#open();
        const e = this.#tombById.get(stationId);
        if (!e) return null;
        const hit = this.#cached(`tomb:${stationId}`);
        if (hit && !(hit instanceof Station)) return hit;
        const raw = this.#doc(e);
        const t: Tombstone = tombstoneOf(raw, e);
        this.#remember(`tomb:${stationId}`, t);
        return t;
    }

    /** A station by an id in another system (noaa, gesla, ticon, xtide, kartverket, slackwater, webcaltides, ...). */
    stationByAlias(system: string, aliasId: string): Station | null {
        this.#open();
        const e = this.#alias.get(system)?.get(aliasId);
        return e ? this.#station(e) : null;
    }

    /** Active stations ordered by station_id. */
    stations(filters: StationFilters = {}): readonly Station[] {
        this.#open();
        return Object.freeze([...this.iterStations(filters)]);
    }

    /**
     * Iterate active stations ordered by station_id. Bad filters fail here, not at the first next(). Each step checks
     * that the release is not closed, also for an iterator made before close (CR2 DR32).
     */
    iterStations(filters: StationFilters = {}): Generator<Station, void, undefined> {
        this.#open();
        const f = checkFilters(filters);
        const active = this.#active;
        const open = () => this.#open();
        const station = (e: IndexEntry) => this.#station(e);
        const thisMatches = (e: IndexEntry, f: CheckedFilters) => this.#matches(e, f);
        return (function* () {
            for (const e of active) {
                open();
                if (thisMatches(e, f)) yield station(e);
            }
            open();
        })();
    }

    /** Name search, accent-insensitive and ranked (spec 4.4.1). */
    search(options: SearchOptions): readonly Station[] {
        this.#open();
        const { f, limit, match, q } = validateSearchOptions(options);
        const ranked: [number, string, IndexEntry][] = [];
        for (const e of this.#active) {
            if (!this.#matches(e, f)) continue;
            const n = e.name_folded;
            let r: number;
            if (n === q) r = 0;
            else if (match === "exact") continue;
            else if (n.startsWith(q)) r = 1;
            else if (occurrences(n, q).some((i) => i > 0 && n[i - 1] === " ")) r = 2;
            else if (n.includes(q)) r = 3;
            else continue;
            ranked.push([r, n, e]);
        }
        ranked.sort((a, b) => a[0] - b[0] || cmp(a[1], b[1]) || cmp(a[2].station_id, b[2].station_id));
        const hits = limit === null ? ranked : ranked.slice(0, limit);
        return Object.freeze(hits.map((h) => this.#station(h[2])));
    }

    #distances(lat: number, lon: number, maxKm: number | null, f: CheckedFilters): [number, IndexEntry][] {
        const band = maxKm === null ? Infinity : maxKm / (EARTH_R_KM * DEG) + 1e-9;
        const hits: [number, IndexEntry][] = [];
        for (const e of this.#active) {
            if (e.lat === null || e.lon === null || Math.abs(e.lat - lat) > band || !this.#matches(e, f)) continue;
            const d = haversine(lat, lon, e.lat, e.lon);
            if (maxKm === null || d <= maxKm) hits.push([d, e]);
        }
        hits.sort((a, b) => a[0] - b[0] || cmp(a[1].station_id, b[1].station_id));
        return hits;
    }

    /** Stations within radiusKm (great-circle), nearest first. */
    near(options: NearOptions): readonly Nearby<Station>[] {
        this.#open();
        const { lat, lon, radius, limit, f } = validateNearOptions(options);
        let hits = this.#distances(lat, lon, radius, f);
        if (limit !== null) hits = hits.slice(0, limit);
        return Object.freeze(hits.map(([d, e]) => nearbyOf(this.#station(e), d)));
    }

    /** The nearest station, within maxKm if given, or null. */
    nearest(options: NearestOptions): Nearby<Station> | null {
        this.#open();
        const { lat, lon, max, f } = validateNearestOptions(options);
        const hits = this.#distances(lat, lon, max, f);
        const h = hits[0];
        return h ? nearbyOf(this.#station(h[1]), h[0]) : null;
    }

    /** The entry of an active Station of this release; null, an unknown station or another release's Station is
     * invalid_argument, as for attribution (CR D2 a, CR2 DR24). */
    #ownEntry(station: unknown, what: string): IndexEntry {
        const e = station instanceof Station && station._from(this) ? this.#byId.get(station.station_id) : undefined;
        if (!e) {
            throw new InvalidArgumentError(`${what} needs a Station of release ${this.datestamp}; got ${station instanceof Station ? `${station.station_id}, which is not one` : JSON.stringify(station)}`);
        }
        return e;
    }

    #attributionEntry(s: unknown): IndexEntry {
        if (!(s instanceof Station) || !s._from(this)) {
            throw new InvalidArgumentError(`attribution needs Stations of release ${this.datestamp}; got ${s instanceof Station ? `${s.station_id} from another release` : JSON.stringify(s)}`);
        }
        const e = this.#byId.get(s.station_id);
        if (!e) throw new InvalidArgumentError(`station ${s.station_id} is not an active station of release ${this.datestamp}`);
        return e;
    }

    /** The reference station of a subordinate station, or null. */
    referenceStation(station: Station): Station | null {
        this.#open();
        const e = this.#ownEntry(station, "referenceStation");
        if (!e.reference_station_id) return null;
        return this.station(e.reference_station_id);
    }

    /** The subordinate stations of a reference station, ordered by station_id. */
    subordinatesOf(station: Station): readonly Station[] {
        this.#open();
        const l = this.#subs.get(this.#ownEntry(station, "subordinatesOf").station_id) ?? [];
        return Object.freeze([...l].sort((a, b) => cmp(a.station_id, b.station_id)).map((e) => this.#station(e)));
    }

    /**
     * The licences of a station's reference chain (spec 4.6, CR2 DR1). The walk follows reference_station_id through
     * at most 16 links (the kind rule of 6.2). It takes the offsets licence of each station on the path, and the
     * licence of the first recommended set it reaches, where it stops. A loop or a missing station ends the walk:
     * the load has checked the links.
     */
    #chainLicences(start: IndexEntry): string[] {
        const out: string[] = [];
        const seen = new Set<string>([start.station_id]);
        let e = start;
        let links = 0;
        while (e.type === "subordinate" && (e.reference_station_id !== null || e.offsets_licence_id !== null)) {
            if (e.offsets_licence_id) out.push(e.offsets_licence_id);
            if (links === MAX_LINKS) break;
            const ref = e.reference_station_id === null ? undefined : this.#byId.get(e.reference_station_id);
            if (!ref || seen.has(ref.station_id)) break;
            links++;
            seen.add(ref.station_id);
            if (ref.recommended_licence_id) {
                out.push(ref.recommended_licence_id);
                break;
            }
            e = ref;
        }
        return out;
    }

    /**
     * The CC BY 4.0 attribution text for the given stations, or for the whole release (spec 4.6). An empty list is the
     * whole release. A station that is not an active Station of this release (null, unknown, removed, from another
     * release) is invalid_argument, never skipped (CR D2).
     */
    attribution(stations?: readonly (Station | null)[] | null): string {
        this.#open();
        let ids: Set<string>;
        const co = this.#effective !== null;
        if (stations === undefined || stations === null || (Array.isArray(stations) && stations.length === 0)) {
            // with commercial_only, only the commercial licences (K-NC DR106)
            ids = new Set(this.#licences.filter((l) => !co || l.commercial_use).map((l) => l.licence_id));
        } else {
            validateAttributionList(stations);
            ids = new Set();
            for (const s of stations) {
                const e = this.#attributionEntry(s);
                if (co) {
                    // the licences of the station's tide source (spec 4.2, 4.6, K-NC DR106)
                    for (const id of this.#tideSourceLicences(e)) ids.add(id);
                    continue;
                }
                if (e.recommended_licence_id) ids.add(e.recommended_licence_id);
                for (const id of this.#chainLicences(e)) ids.add(id);
            }
        }
        const parts: string[] = [];
        const seen = new Set<string>();
        for (const id of [...ids].sort(cmp)) {
            const l = this.licence(id);
            // the load checks every licence reference; a licence missing here is never dropped from the CC BY text
            if (!l) throw new InvalidReleaseError(`licence ${id} does not resolve`);
            if (l.provider === null) {
                // no provider: the attribution alone, never merged with another entry (CR D2)
                parts.push(l.attribution ?? "");
                continue;
            }
            if (seen.has(l.provider)) continue;
            seen.add(l.provider);
            parts.push(`${l.provider}: ${l.attribution ?? ""}`);
        }
        const ident = this.concept_doi ? `doi:${this.concept_doi}` : `https://data.opentideconstants.org/OTC_${this.datestamp}.json`;
        const head = `Tidal constants: OpenTideConstants ${this.datestamp}, ${ident}, CC BY 4.0.`;
        // an empty scope: the dataset header alone (spec 4.6, K-NC DR106)
        if (ids.size === 0) return head;
        let text = `${head} Sources: ${parts.join("; ")}`;
        // the non-commercial notice (spec 4.6, K-NC DR105): once, then one entry per non-commercial licence in scope,
        // by licence_id; a null provider gives the licence_id
        const nc = [...ids].sort(cmp).map((id) => this.licence(id)).filter((l): l is Licence => l !== null && !l.commercial_use);
        if (nc.length > 0) {
            text += `. Non-commercial use only: ${nc.map((l) => `${l.provider ?? l.licence_id} (${l.spdx ?? ""}, ${l.terms_url ?? ""})`).join("; ")}`;
        }
        return text;
    }
}

/** @internal Build the index of an eager document's stations. */
export function indexStations(header: ReleaseHeader, docs: readonly Json[]): IndexEntry[] {
    const convs = new Set(header.conventions.map((c) => str(c, "convention_id") ?? ""));
    const lics = new Set(header.licences.map((l) => str(l, "licence_id") ?? ""));
    const entries = docs.map((d, i) => indexDoc(d, header, i, 0, convs, lics));
    checkLinks(entries);
    resolveKinds(entries);
    return entries;
}

/** @internal Sort datestamps newest first. */
export function newestFirst(ds: Iterable<string>): string[] {
    return [...ds].sort((a, b) => compareDatestamps(b, a));
}

const FALLBACK_REASONS = ["time_base_disputed","time_base_unresolved","refused_fit","short_record_uncalibrated","short_record_long_period","published_full_list","reliability_withheld","licence_reading","datum_gate_failed","not_in_otc_input","historical_offsets"] as const;

const QC_FLAGS = ["time_base","broken_record","microtidal","non_tidal_signal","short_record","sibling_disagreement","carried_over","fallback:time_base_disputed","fallback:time_base_unresolved","fallback:refused_fit","fallback:short_record_uncalibrated","fallback:short_record_long_period","fallback:published_full_list","fallback:reliability_withheld","fallback:licence_reading","fallback:datum_gate_failed","fallback:not_in_otc_input","fallback:historical_offsets"] as const;

const SOURCE_ROLES = ["gauge_station","published_harmonic_record","model","reference"] as const;

const SOURCE_DISPOSITIONS = ["metadata_only","not_fitted","licence_restricted","unavailable","retained"] as const;

const HISTORICAL_PROFILES: Readonly<Record<string, JsonObject>> = {
  "noaa-2020-atlantic-table2-2513": {
    "datum": {
      "basis": {
        "mllw": {
          "kind": "published",
          "method": "source",
          "source_name": "MLLW"
        }
      },
      "chart_datum": "mllw",
      "named": {
        "mllw": 0.0
      },
      "zero": "chart_datum"
    },
    "height_adjusted_type": "R",
    "height_offset_high": 0.84,
    "height_offset_low": 1.0,
    "offset_id": "noaa-2020-atlantic-table2-2513",
    "provenance": {
      "annual_table_row": 2513,
      "book": "atlantic",
      "id_crosswalk": {
        "legacy_id": "TEC2869",
        "modern_alias_verified": false,
        "status": "inferred"
      },
      "pdf_page": 351,
      "printed_page": 345,
      "raw_row_text": "  2513     Lockwoods Folly Inlet . . . . . . . . . . . . . . . . . . . . . . .         33° 55'     78° 14'     +0 04      +0 15     *0.84     *1.00    4.2    4.8     2.3",
      "reference_binding": {
        "mapping_status": "primary_name_position",
        "noaa_id": "8661070",
        "station_id": "OTC-a6c00a3f"
      },
      "source_manifest_sha256": "667eec5b3fd25f99d46f24864766726094961d7db5fa104ca12450f3ecd0fdf7"
    },
    "qc_status": "flagged",
    "reference_station_id": "OTC-a6c00a3f",
    "source": "noaa",
    "source_record_id": "annual-tide-tables-2020/atlantic/Table2/2513",
    "source_type": "official",
    "source_version": "annual-tide-tables-2020",
    "time_offset_high_min": 4,
    "time_offset_low_min": 15,
    "vintage": {
      "current_accuracy": "unverified",
      "current_validity": "unestablished",
      "publication_year": 2020,
      "removal_events": [
        {
          "evidence_sha256": "c100d0fbc5482ec24f5c99d912be73306bd2dea079690f08edc5f58a821bcd61",
          "name": "Lockwoods Folly Inlet (r)",
          "operation": "Removed",
          "source_clock_timestamp": "2026-02-18T14:09:46",
          "source_timezone": null
        }
      ],
      "source_lifecycle": "retired"
    }
  },
  "noaa-2020-pacific-table2-517": {
    "datum": {
      "basis": {
        "mllw": {
          "kind": "published",
          "method": "source",
          "source_name": "MLLW"
        }
      },
      "chart_datum": "mllw",
      "named": {
        "mllw": 0.0
      },
      "zero": "chart_datum"
    },
    "height_adjusted_type": "A",
    "height_offset_high": -0.06096,
    "height_offset_low": 0.0,
    "offset_id": "noaa-2020-pacific-table2-517",
    "provenance": {
      "annual_table_row": 517,
      "book": "pacific",
      "id_crosswalk": {
        "legacy_id": "TWC0509",
        "modern_alias_verified": false,
        "status": "inferred"
      },
      "pdf_page": 302,
      "printed_page": 284,
      "raw_row_text": "   517     San Francisco Bar . . . . . . . . . . . . . . . . . . . . . . . . .         37° 46'     122° 38'     -0 35       -0 31      -0.2        0.0    3.9    5.6     3.0",
      "reference_binding": {
        "mapping_status": "primary_name_position",
        "noaa_id": "9414290",
        "station_id": "OTC-ee4593cd"
      },
      "source_manifest_sha256": "667eec5b3fd25f99d46f24864766726094961d7db5fa104ca12450f3ecd0fdf7"
    },
    "qc_status": "flagged",
    "reference_station_id": "OTC-ee4593cd",
    "source": "noaa",
    "source_record_id": "annual-tide-tables-2020/pacific/Table2/517",
    "source_type": "official",
    "source_version": "annual-tide-tables-2020",
    "time_offset_high_min": -35,
    "time_offset_low_min": -31,
    "vintage": {
      "current_accuracy": "unverified",
      "current_validity": "unestablished",
      "publication_year": 2020,
      "removal_events": [
        {
          "evidence_sha256": "c100d0fbc5482ec24f5c99d912be73306bd2dea079690f08edc5f58a821bcd61",
          "name": "San Francisco Bar (r)",
          "operation": "Removed",
          "source_clock_timestamp": "2026-02-18T14:09:50",
          "source_timezone": null
        },
        {
          "evidence_sha256": "c100d0fbc5482ec24f5c99d912be73306bd2dea079690f08edc5f58a821bcd61",
          "name": "San Francisco Bar",
          "operation": "Removed",
          "source_clock_timestamp": "2026-07-06T11:17:37",
          "source_timezone": null
        }
      ],
      "source_lifecycle": "retired"
    }
  }
};
/** @internal */
export function fallbackOf(d: JsonObject | null): Fallback | null {
    if (!d) return null;
    return Object.freeze({ reason: en(d['reason'], FALLBACK_REASONS) ?? 'other', basis: str(d, 'basis') ?? '',
        otc_finding: str(d, 'otc_finding') ?? '', preferred_set_id: str(d, 'preferred_set_id'), raw: d });
}
/** @internal */
export function qcFlagOf(d: JsonObject): QcFlag {
    return Object.freeze({flag: en(d['flag'], QC_FLAGS) ?? 'other', reason: str(d, 'reason'), values: qcValues(d['values'])});
}
/** @internal */
export function sourceRecordOf(d: JsonObject, release: Release): SourceRecord {
    return Object.freeze({source: str(d,'source') ?? '', source_version: str(d,'source_version') ?? '',
        source_record_id: str(d,'source_record_id') ?? '', role: en(d['role'],SOURCE_ROLES) ?? 'other',
        disposition: en(d['disposition'],SOURCE_DISPOSITIONS) ?? 'other', detail: str(d,'detail') ?? '',
        licence_id: str(d,'licence_id'), upstream_licence_id: str(d,'upstream_licence_id'),
        published_set_ids: Object.freeze(arr(d,'published_set_ids').filter((v): v is string => typeof v === 'string')),
        provenance: obj(d,'provenance') ?? Object.freeze({}), original_metadata: obj(d,'original_metadata') ?? Object.freeze({}),
        original_harmonics: obj(d,'original_harmonics'), licence: release.licence(str(d,'licence_id') ?? ''),
        upstreamLicence: release.licence(str(d,'upstream_licence_id') ?? ''), raw: d });
}
function checkSourceRecords(doc: JsonObject): void {
    const records = doc['source_records'];
    const fail = (field: string): never => { throw new InvalidReleaseError(`station ${String(doc['station_id'])}: invalid source record ${field}`); };
    if (records !== undefined && (!Array.isArray(records) || records.length === 0)) fail('source_records');
    for (const d of objects(doc,'source_records')) {
        for (const k of ['source','source_version','source_record_id','role','disposition','detail']) {
            if (typeof d[k] !== 'string' || !d[k]) fail(k);
        }
        for (const k of ['licence_id','upstream_licence_id']) if (d[k] !== undefined && d[k] !== null && typeof d[k] !== 'string') fail(k);
        if (!Object.hasOwn(d,'licence_id') || !Array.isArray(d['published_set_ids']) || !d['published_set_ids'].every(v => typeof v === 'string')) fail('required fields');
        const p = obj(d,'provenance');
        if (!p || !Array.isArray(p['input_sha256']) || !p['input_sha256'].every(v => typeof v === 'string') || typeof p['inventory_sha256'] !== 'string') fail('provenance');
        if (Object.hasOwn(d,'original_metadata') && !isObject(d['original_metadata'])) fail('original_metadata');
        const h = d['original_harmonics'];
        if (h !== undefined && h !== null) {
            if (!isObject(h)) fail('original_harmonics');
            if (isObject(h)) {
                for (const k of ['format','amplitude_unit','amplitude_unit_basis','phase_unit','phase_convention','amplitude_uncertainty_unit','amplitude_uncertainty_unit_basis']) {
                    if (h[k] !== undefined && h[k] !== null && typeof h[k] !== 'string') fail(k);
                }
                if (h['columns'] !== undefined && h['columns'] !== null && (!Array.isArray(h['columns']) || !h['columns'].every(v => typeof v === 'string'))) fail('columns');
                if (h['rows'] !== undefined && (!Array.isArray(h['rows']) || !h['rows'].every(r => Array.isArray(r) && r.every(c => typeof c === 'string')))) fail('rows');
                for (const annotation of objects(h,'annotations')) {
                    if (annotation['row'] !== undefined && annotation['row'] !== null && !(typeof annotation['row'] === 'number' && Number.isFinite(annotation['row']) && Number.isInteger(annotation['row']))) fail('annotation.row');
                    for (const k of ['reason','detail']) if (annotation[k] !== undefined && annotation[k] !== null && typeof annotation[k] !== 'string') fail(`annotation.${k}`);
                }
                if (h['annotations'] !== undefined && h['annotations'] !== null && (!Array.isArray(h['annotations']) || !h['annotations'].every(isObject))) fail('annotations');
            }
        }
    }
}
/** Source-bound profiles, not a general licence to admit arbitrary historical offsets. */
function checkHistoricalOffsets(d: JsonObject): void {
    const flag = objects(d,'qc_flags').some(f => f['flag'] === 'fallback:historical_offsets');
    if (!Object.hasOwn(d,'offset_id') && obj(d,'fallback')?.['reason'] !== 'historical_offsets' && !flag) return;
    const fail = (key: string): never => { throw new InvalidReleaseError(`invalid historical subordinate_offsets.${key}`); };
    const id = str(d,'offset_id');
    const expected = id === null ? undefined : HISTORICAL_PROFILES[id];
    if (!expected) fail('offset_id');
    const text = (v: Json | undefined) => typeof v === 'string' && v.trim().length > 0;
    const digest = (v: Json | undefined) => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
    const hashes = (v: Json | undefined) => Array.isArray(v) && v.length > 0 && v.every(digest) && new Set(v).size === v.length;
    for (const [key,value] of Object.entries(expected ?? {})) {
        if (key === 'vintage' || key === 'provenance' || key === 'qc_flags' || key === 'fallback') continue;
        if (canonicalJson(d[key]) !== canonicalJson(value)) fail(key);
    }
    if (!text(d['licence_id'])) fail('licence_id');
    const flags = objects(d,'qc_flags');
    if (flags.length !== 1 || flags[0]?.['flag'] !== 'fallback:historical_offsets' || !text(flags[0]?.['reason'])) fail('qc_flags');
    const f = obj(d,'fallback');
    if (!f || f['reason'] !== 'historical_offsets' || !text(f['basis']) || !text(f['otc_finding']) || Object.hasOwn(f,'preferred_set_id')) fail('fallback');
    const v = obj(d,'vintage'), ev = obj(expected,'vintage');
    if (!v || !ev) fail('vintage');
    for (const key of ['publication_year','source_lifecycle','removal_events','current_validity','current_accuracy']) {
        if (canonicalJson(v?.[key]) !== canonicalJson(ev?.[key])) fail(`vintage.${key}`);
    }
    const equivalence = v?.['reference_2020_equivalence'];
    if (!['not_checked','matched_at_publisher_precision','disagrees'].includes(String(equivalence))) fail('reference_2020_equivalence');
    if (equivalence === 'not_checked' ? Object.hasOwn(v ?? {},'reference_2020_equivalence_sha256') : !digest(v?.['reference_2020_equivalence_sha256'])) fail('reference_2020_equivalence_sha256');
    const p = obj(d,'provenance'), ep = obj(expected,'provenance');
    if (!p || !ep) fail('provenance');
    for (const key of ['source_manifest_sha256','book','annual_table_row','printed_page','pdf_page','raw_row_text']) {
        if (p?.[key] !== ep?.[key]) fail(`provenance.${key}`);
    }
    if (!hashes(p?.['input_sha256']) || !digest(p?.['acceptance_report_sha256'])) fail('provenance evidence');
    for (const [key,fields] of [['id_crosswalk',['legacy_id','status','modern_alias_verified']],['reference_binding',['noaa_id','station_id','mapping_status']]] as const) {
        const actual = obj(p,key), baseline = obj(ep,key);
        if (!actual || !baseline || !hashes(actual['evidence_sha256']) || fields.some(k => actual[k] !== baseline[k])) fail(`provenance.${key}`);
    }
    try { if (!text(p?.['raw_values_json']) || !isObject(JSON.parse(String(p?.['raw_values_json'])))) fail('raw_values_json'); }
    catch { fail('raw_values_json'); }
}

function canonicalJson(v: Json | undefined): string | undefined {
    if (isObject(v)) return JSON.stringify(Object.fromEntries(Object.keys(v).sort().map(k => [k, JSON.parse(canonicalJson(v[k]) ?? "null")])));
    if (Array.isArray(v)) return JSON.stringify(v.map(x => JSON.parse(canonicalJson(x) ?? "null")));
    return JSON.stringify(v);
}

const predictionTables=new WeakMap<Release,Map<string,AstroTable>>();
/** @internal Shared astronomical metadata lookup; no computational engine dependency. */
export function predictionAstroTable(release:Release,id:string|null=null):AstroTable|null {
    const metadata=release._header;
    if(id!==null&&typeof id!=='string')throw new X.InvalidArgumentError('astro table id must be a string');
    if(id===null)id=release.conventions.map(c=>str(c.raw,'astro_table_id')).find(v=>v!==null)??null;
    if(id===null)return null;
    let cache=predictionTables.get(release);if(!cache){cache=new Map();predictionTables.set(release,cache);}
    const hit=cache.get(id);if(hit)return hit;
    const raw=objects(metadata,'astro_tables').find(t=>t['astro_table_id']===id);if(!raw)return null;
    const table=new AstroTable(raw);cache.set(id,table);return table;
}
/** @internal Shared station validation for metadata and native prediction. */
export function predictionStation(release:Release,station:Station|string):Station {
    void release._header;
    if(typeof station==='string')return release.requireStation(station);
    if(!(station instanceof Station))throw new X.InvalidArgumentError('station must be a Station or station id');
    const actual=release.station(station.station_id);
    if(!actual||JSON.stringify(actual.raw)!==JSON.stringify(station.raw))throw new X.InvalidArgumentError('station is not from this release');
    return actual;
}
/** @internal Shared option validation for metadata and native prediction. */
export function predictionOptions(setId:string|null|undefined,datum:string|null|undefined=null,binNumber:number|null|undefined=null):void {
    if(setId!==null&&setId!==undefined&&typeof setId!=='string')throw new X.InvalidArgumentError('setId must be a string');
    if(datum!==null&&datum!==undefined&&typeof datum!=='string')throw new X.InvalidArgumentError('datum must be a string');
    if(binNumber!==null&&binNumber!==undefined&&(typeof binNumber!=='number'||!Number.isInteger(binNumber)||binNumber<1||binNumber>Number.MAX_SAFE_INTEGER))throw new X.InvalidArgumentError('binNumber must be an integer from 1 to 2^53 - 1');
}
function datumInfo(setId:string|null,d:JsonObject|null):DatumInfo {
    const named=obj(d,'named')??{},basis=obj(d,'basis'),chartId=str(d,'chart_datum'),chart=chartId===null?null:num(named,chartId),levels:DatumLevel[]=[];
    for(const key of Object.keys(named).sort()){const b=obj(basis,key),control=obj(b,'control'),value=num(named,key) as number;levels.push(new DatumLevel({key,value_m:value,above_chart_m:chart===null?null:value-chart,kind:str(b,'kind'),method:str(b,'method') as string,source_name:str(b,'source_name'),epoch:obj(b,'epoch'),data_span:obj(b,'data_span'),control_station_id:str(control,'station_id'),control_set_id:str(control,'set_id'),control_source_id:str(control,'source_id'),uncertainty_m:num(b,'uncertainty_m'),uncertainty_basis:str(b,'uncertainty_basis'),flags:arr(b,'flags').filter((v):v is string=>typeof v==='string')}));}
    return new DatumInfo({set_id:setId,zero:str(d,'zero'),zero_name:str(d,'zero_name'),chart_datum:chartId,msl_offset_m:num(d,'msl_offset_m'),levels});
}
function predictionDatums(release:Release,input:Station|string,opts:prediction.DatumOptions={}):DatumInfo|readonly DatumInfo[]|null {
    const station=predictionStation(release,input);predictionOptions(opts.setId);const all=validateAllSets(opts.allSets);if(all)return Object.freeze(station.constantSets({includeNoConstants:true}).map(s=>datumInfo(s.set_id,obj(s.raw,'datum'))));const constants=predictionChosen(release,station,opts.setId);if(constants)return datumInfo(constants.set_id,obj(constants.raw,'datum'));const off=obj(station.raw,'subordinate_offsets');return off?datumInfo(null,obj(off,'datum')):null;
}
/** @internal Original default/boolean phase, after station and prediction options. */
export function validateAllSets(value:boolean|undefined):boolean {
    const all=value===undefined?false:value;if(typeof all!=='boolean')throw new X.InvalidArgumentError('allSets must be a boolean');return all;
}
const PREDICTION_ARGUMENTS = Symbol('private authentic prediction prerequisites');
type PredictionArguments = Extract<C.SelectedArguments, { member_id: 'Release.heights' | 'Release.heights_at' | 'Release.extremes' | 'Release.currents' | 'Release.current_events' | 'Release.datums' | 'Release.ranges' }>;
/** @internal Authentic native station prerequisite prepared outside primitive B01. */
export interface PreparedPredictionArguments {
    readonly [PREDICTION_ARGUMENTS]: true;
    readonly receiver: Release;
    readonly request: PredictionArguments;
    readonly station: Station | null;
    readonly error: X.OpenTideConstantsError | null;
}
/** @internal Original native station resolution; no prediction/options/evaluation. */
export function preparePredictionArguments(receiver:Release,request:PredictionArguments):PreparedPredictionArguments {
    try {
        const station=predictionStation(receiver,request.arguments.station);
        return { [PREDICTION_ARGUMENTS]:true,receiver,request,station,error:null };
    } catch(error) {
        if(!(error instanceof X.OpenTideConstantsError))throw error;
        return { [PREDICTION_ARGUMENTS]:true,receiver,request,station:null,error };
    }
}
function predictionRanges(release:Release,input:Station|string,opts:prediction.RangeOptions={}):Ranges {
    const info=predictionDatums(release,input,opts),levels=info instanceof DatumInfo?info.levels:[];
    const difference=(a:string,b:string)=>{const high=levels.find(l=>l.key===a),low=levels.find(l=>l.key===b);if(!high||!low||high.value_m==null||low.value_m==null||high.kind===null||high.kind!==low.kind||JSON.stringify(high.epoch)!==JSON.stringify(low.epoch))return null;return high.value_m-low.value_m;};return new Ranges({mn:difference('mhw','mlw'),gt:difference('mhhw','mllw'),dhq:difference('mhhw','mhw'),dlq:difference('mlw','mllw')});
}
/** @internal Shared set selection for metadata and prediction. */
export function predictionChosen(release:Release,station:Station,setId:string|null|undefined):ConstantSet|null {
    if(setId===null||setId===undefined)return station.recommendedSet;
    const constants=station.constantSet(setId);if(!constants)throw new X.InvalidArgumentError(`setId ${setId} is not a set of ${station.station_id}`);
    if(release._commercialOnly&&!constants.licence.commercial_use)throw new X.InvalidArgumentError(`commercial_only refuses set_id ${setId}`);return constants;
}

/** @internal Exact existing validation-only phase. */
export function validateConstantSetsOptions(options: ConstantSetsOptions = {}) {
    if (options === null || typeof options !== "object") throw new InvalidArgumentError("options must be an object");
    const inc = options.includeNoConstants ?? false;
    if (typeof inc !== "boolean") throw new InvalidArgumentError("includeNoConstants must be a boolean");
    return inc;
}

/** @internal Exact existing validation-only phase. */
export function validateSearchOptions(options: SearchOptions) {
    if (options === null || typeof options !== "object") throw new InvalidArgumentError("search needs an options object with name");
    const f = checkFilters(options);
    const limit = checkLimit(options.limit);
    const match = options.match ?? null;
    if (match !== null && match !== "exact") throw new InvalidArgumentError(`match must be "exact"; got ${JSON.stringify(match)}`);
    if (typeof options.name !== "string") throw new InvalidArgumentError("name must be a string");
    const q = foldName(options.name);
    if (q === "") throw new InvalidArgumentError("the query is empty");
    return { f, limit, match, q };
}

/** @internal Exact existing validation-only phase. */
export function validateNearOptions(options: NearOptions) {
    if (options === null || typeof options !== "object") throw new InvalidArgumentError("near needs an options object");
    const lat = checkNumber(options.lat, "lat", -90, 90);
    const lon = checkNumber(options.lon, "lon", -180, 180);
    const radius = checkNumber(options.radiusKm, "radiusKm", 0, Infinity);
    const limit = checkLimit(options.limit);
    const f = checkFilters(options);
    return { lat, lon, radius, limit, f };
}

/** @internal Exact existing validation-only phase. */
export function validateNearestOptions(options: NearestOptions) {
    if (options === null || typeof options !== "object") throw new InvalidArgumentError("nearest needs an options object");
    const lat = checkNumber(options.lat, "lat", -90, 90);
    const lon = checkNumber(options.lon, "lon", -180, 180);
    const max = options.maxKm === undefined || options.maxKm === null ? null : checkNumber(options.maxKm, "maxKm", 0, Infinity);
    return { lat, lon, max, f: checkFilters(options) };
}

/** @internal Exact existing RecordSpan field phase. */
export function recordSpanOf(span: JsonObject, setId: string): RecordSpan {
    return Object.freeze({
        start: checkedTime(span["start"], `record_span.start of set ${setId}`),
        end: checkedTime(span["end"], `record_span.end of set ${setId}`), good_samples: num(span, "good_samples"),
    });
}

/** @internal Exact existing Nearby fields; query and owner resolution remain with the caller. */
export function nearbyOf(station: Station, distance_km: number): Nearby<Station> {
    return Object.freeze({ station, distance_km });
}

/** @internal Exact existing Stats fields; counts remain with the caller. */
export function statsOf(type: Stats['type'], kind: Stats['kind'], country: Stats['country'], source: Stats['source'], qc_status: Stats['qc_status']): Stats {
    return Object.freeze({ type, kind, country, source, qc_status });
}

/** @internal Exact existing Datum field phase. */
export function datumOf(datum: JsonObject): Datum {
    return Object.freeze({
        msl_offset_m: num(datum, "msl_offset_m"),
        named: Object.freeze(Object.fromEntries(Object.entries(obj(datum, "named") ?? {}).filter((e): e is [string, number] => typeof e[1] === "number"))),
    });
}

/** @internal Exact existing SubordinateOffsets field phase. */
export function subordinateOffsetsOf(off: JsonObject): SubordinateOffsets {
    return Object.freeze({
        offset_id: str(off, "offset_id"), source: str(off, "source"), source_type: en(off["source_type"], SOURCE_TYPES),
        source_version: str(off, "source_version"), source_record_id: str(off, "source_record_id"), qc_status: en(off["qc_status"], QC_STATUSES),
        qc_flags: Object.freeze(objects(off, "qc_flags").map(qcFlagOf)), fallback: fallbackOf(obj(off, "fallback")),
        vintage: historicalVintageOf(off),
        provenance: historicalProvenanceOf(off),
        reference_station_id: str(off, "reference_station_id"),
        time_offset_high_min: num(off, "time_offset_high_min"), time_offset_low_min: num(off, "time_offset_low_min"),
        height_offset_high: num(off, "height_offset_high"), height_offset_low: num(off, "height_offset_low"),
        height_adjusted_type: en(off["height_adjusted_type"], ["R", "A"] as const) as HeightAdjustedType | Other | null,
        licence_id: str(off, "licence_id"),
    });
}

/** @internal Existing retained historical alias; admission belongs to the original caller. */
export function historicalVintageOf(off: JsonObject): HistoricalOffsetVintage | null {
    if (!Object.hasOwn(off, "offset_id")) return null;
    return obj(off, "vintage") as unknown as HistoricalOffsetVintage | null;
}

/** @internal Existing retained historical alias; admission belongs to the original caller. */
export function historicalProvenanceOf(off: JsonObject): HistoricalOffsetProvenance | null {
    if (!Object.hasOwn(off, "offset_id")) return null;
    return obj(off, "provenance") as unknown as HistoricalOffsetProvenance | null;
}

/** @internal Exact existing DroppedConstituent field phase. */
export function droppedConstituentOf(d: JsonObject): DroppedConstituent {
    return Object.freeze({
        name: str(d, "name") ?? "",
        dropped_reason: en(d["dropped_reason"], ["rayleigh", "noise", "long_period_rule", "non_tidal_rule", "convention", "other"] as const) ?? "other",
        detail: val(d, "detail"),
    });
}

/** @internal Exact existing Provenance field phase; cache remains with the owner. */
export function provenanceOf(p: JsonObject): Provenance {
    const b = obj(p, "build");
    return Object.freeze({
        build: b === null ? null : buildOf(b), adapter_version: str(p, "adapter_version"),
        input_sha256: val(p, "input_sha256"), selection_reason: str(p, "selection_reason"),
        decision: val(p, "decision"), carried_from_release: str(p, "carried_from_release"), raw: p,
    });
}

/** @internal Exact existing Convention field phase. */
export function conventionOf(c: JsonObject): Convention {
    return Object.freeze({
        convention_id: str(c, "convention_id") ?? "",
        phase_reference: en(c["phase_reference"], ["greenwich_utc", "local"] as const),
        utc_offset_hours: num(c, "utc_offset_hours"), v0_model: str(c, "v0_model"),
        nodal_handling: en(c["nodal_handling"], ["f_u_at_prediction", "none"] as const),
        nodal_formula_ids: val(c, "nodal_formula_ids"), constituent_table_version: str(c, "constituent_table_version"),
        tables_sha256: str(c, "tables_sha256"), canary: val(c, "canary"), raw: c,
    });
}

/** @internal Exact existing Licence field phase. */
export function licenceOf(l: JsonObject): Licence {
    return Object.freeze({
        licence_id: str(l, "licence_id") ?? "", spdx: str(l, "spdx"), provider: str(l, "provider"),
        citation: str(l, "citation"), attribution: str(l, "attribution"), url: str(l, "url"),
        commercial_use: l["commercial_use"] === true, restriction: str(l, "restriction"), terms_url: str(l, "terms_url"), raw: l,
    });
}

/** @internal Exact existing Tombstone field phase; lookup/cache remain with the owner. */
export function tombstoneOf(raw: JsonObject, e: IndexEntry): Tombstone {
    return Object.freeze({
        station_id: e.station_id, name: str(raw, "name"),
        status: en(raw["status"], ["active", "removed"] as const) ?? "other",
        removed_in: str(raw, "removed_in"),
        removed_reason: en(raw["removed_reason"], ["merged", "duplicate"] as const),
        merged_into: str(raw, "merged_into"), detail: str(raw, "detail"), raw,
    });
}
