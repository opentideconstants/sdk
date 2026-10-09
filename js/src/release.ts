import { compareDatestamps, foldName } from "./constants.js";
import {
    FileError, InvalidArgumentError, InvalidReleaseError, StationNotFoundError, StationRemovedError,
} from "./errors.js";
import { arr, deepFreeze, en, isObject, num, obj, str, time, val, type Json, type JsonObject } from "./json.js";
import type {
    ConstantSetsOptions, Constituent, Convention, Datum, DroppedConstituent, FileInfo, HeightAdjustedType, Kind,
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
}

const SET_KEYS = ["set_id", "source", "source_type", "quantity", "qc_status", "convention_id", "licence_id"] as const;
const ENTRY_STR = ["name", "name_folded", "country", "type", "kind", "reference_station_id", "offsets_licence_id", "recommended_set_id"] as const;

/** @internal One line (station or tombstone) of a release, as the SDK keeps it in memory: the stored entry plus derived facts. */
export interface IndexEntry {
    stored: StoredEntry;
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
    }
    for (const [list, key] of [[cs, "convention_id"], [ls, "licence_id"]] as const) {
        const seen = new Set<string>();
        for (const x of list) {
            const id = String(x[key]);
            if (seen.has(id)) throw new InvalidReleaseError(`${key} ${id} appears twice (CR D5)`);
            seen.add(id);
        }
    }
    return deepFreeze({ format_version: fv, release, conventions: cs, licences: ls });
}

/**
 * The JSON type of each known field that the SDK reads (spec 7.3: tolerant is not lax; CR2 PK-R2-05). Absent or
 * null is always allowed here; required fields are checked where they are used. T a string, N a finite number,
 * I a finite number with an integral value, O an object, L a list of objects, S a list of strings, A a list.
 * The same table is in the Python, Ruby and C SDKs.
 */
type FieldType = "T" | "N" | "I" | "O" | "L" | "S" | "A";
type FieldTypes = Readonly<Record<string, FieldType>>;
const STATION_TYPES: FieldTypes = {
    name: "T", country: "T", timezone: "T", type: "T", recommended_set_id: "T", status: "T",
    aliases: "O", constant_sets: "L", validation: "L", subordinate_offsets: "O", current_offsets: "A",
};
const OFFSET_TYPES: FieldTypes = {
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
    record_span: "O", datum: "O", time_base: "O", provenance: "O", current_bins: "A",
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
function checkShape(doc: JsonObject, id: string): void {
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
    if (off) check(off, OFFSET_TYPES, "subordinate_offsets.");
    for (const v of objects(doc, "validation")) check(v, VALIDATION_TYPES, "validation ");
    for (const cs of objects(doc, "constant_sets")) {
        const where = `set ${typeof cs["set_id"] === "string" ? cs["set_id"] : "?"}: `;
        check(cs, SET_TYPES, where);
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
    void header;
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
    const kind = rec ? kindOfQuantity(str(rec, "quantity")) : null;
    const name = str(doc, "name");
    return entryFromStored({
        offset, length, station_id: id, status,
        name, name_folded: name === null ? null : foldName(name),
        country: str(doc, "country"), type: str(doc, "type"), lat: num(doc, "lat"), lon: num(doc, "lon"), kind,
        aliases: aliasMap(doc),
        reference_station_id: off ? str(off, "reference_station_id") : null,
        offsets_licence_id: offLic,
        recommended_set_id: recId,
        sets: sets.map((cs) => ({
            set_id: str(cs, "set_id"), source: str(cs, "source"), source_type: str(cs, "source_type"), quantity: str(cs, "quantity"),
            qc_status: str(cs, "qc_status"), convention_id: str(cs, "convention_id"), licence_id: str(cs, "licence_id"),
            constituents: arr(cs, "constituents").filter(isObject).map((c) => str(c, "name")).filter((x): x is string => x !== null),
        })),
    });
}

/**
 * @internal The keys of an index entry that a line read through the index must give as they are (PK-R2-07): the
 * status, the references and the sets. The other keys are used as the index gives them (spec 6.2).
 */
export function lineView(s: StoredEntry): string {
    const sets = Array.isArray(s.sets) ? s.sets : [];
    return JSON.stringify([s.station_id, s.status, s.recommended_set_id, s.reference_station_id, s.offsets_licence_id,
        sets.map((cs) => [...SET_KEYS.map((k) => cs[k]), cs.constituents])]);
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
        index_version: 1, datestamp, jsonl: `OTC_${datestamp}.jsonl`, jsonl_sha256: jsonlSha256, jsonl_size: jsonlSize, by,
        stations: entries.map((e) => ({ ...e.stored, kind: e.kind })) as unknown as Json[],
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
    if (!isObject(v) || v["index_version"] !== 1 || v["datestamp"] !== datestamp || v["jsonl"] !== `OTC_${datestamp}.jsonl`) return null;
    if (jsonlSha256 === null || v["jsonl_sha256"] !== jsonlSha256 || jsonlSize === null || v["jsonl_size"] !== jsonlSize) return null;
    const stations = v["stations"];
    if (!Array.isArray(stations)) return null;
    const strOrNull = (x: unknown) => x === null || typeof x === "string";
    const numOrNull = (x: unknown) => x === null || (typeof x === "number" && Number.isFinite(x));
    const isInt = (x: unknown): x is number => typeof x === "number" && Number.isInteger(x) && x >= 0;
    const out: IndexEntry[] = [];
    let start = 0; // the least offset the next entry may have: after the line before it and its line end (CR2 DR9)
    for (const e of stations) {
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
        const sets = e["sets"];
        if (!Array.isArray(sets)) return null;
        for (const cs of sets) {
            if (!isObject(cs) || !SET_KEYS.every((k) => k in cs && strOrNull(cs[k]))) return null;
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
        const stored = e as unknown as StoredEntry;
        const rec = stored.recommended_set_id === null ? undefined : stored.sets.find((cs) => cs.set_id === stored.recommended_set_id);
        // kind is derived, not trusted: from the recommended set here, and from the reference station below
        out.push(entryFromStored({ ...stored, kind: rec ? kindOfQuantity(rec.quantity) : null }));
    }
    checkLinks(out);
    resolveKinds(out);
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

function constituentOf(c: JsonObject): Constituent {
    return Object.freeze({
        name: str(c, "name") ?? "", source_name: str(c, "source_name"), doodson: str(c, "doodson"),
        speed_deg_per_hour: num(c, "speed_deg_per_hour"), amplitude_m: num(c, "amplitude_m"), phase_deg: num(c, "phase_deg"),
        amp_uncertainty_m: num(c, "amp_uncertainty_m"), phase_uncertainty_deg: num(c, "phase_uncertainty_deg"),
        kept_reason: str(c, "kept_reason"), raw: c,
    });
}

function timeBaseOf(t: JsonObject): TimeBase {
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

function buildOf(b: JsonObject): ProvenanceBuild {
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

function validationOf(v: JsonObject): Validation {
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
        this.record_span = span === null ? null : Object.freeze({
            start: checkedTime(span["start"], `record_span.start of set ${this.set_id}`),
            end: checkedTime(span["end"], `record_span.end of set ${this.set_id}`), good_samples: num(span, "good_samples"),
        });
        const datum = obj(raw, "datum");
        this.datum = datum === null ? null : Object.freeze({
            msl_offset_m: num(datum, "msl_offset_m"),
            named: Object.freeze(Object.fromEntries(Object.entries(obj(datum, "named") ?? {}).filter((e): e is [string, number] => typeof e[1] === "number"))),
        });
        this.qc_status = en(raw["qc_status"], QC_STATUSES);
        this.qc_flags = Object.freeze(arr(raw, "qc_flags").filter(isObject).map((f): QcFlag => Object.freeze({
            flag: en(f["flag"], ["time_base", "broken_record", "microtidal", "non_tidal_signal", "short_record",
                "sibling_disagreement", "carried_over"] as const) ?? "other",
            reason: str(f, "reason"), values: qcValues(f["values"]),
        })));
        this.dropped_constituents = Object.freeze(arr(raw, "dropped_constituents").filter(isObject).map((d) => Object.freeze({
            name: str(d, "name") ?? "",
            dropped_reason: en(d["dropped_reason"], ["rayleigh", "noise", "long_period_rule", "non_tidal_rule", "convention", "other"] as const) ?? "other",
            detail: val(d, "detail"),
        })));
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
            const b = obj(p, "build");
            this.#provenance = Object.freeze({
                build: b === null ? null : buildOf(b), adapter_version: str(p, "adapter_version"),
                input_sha256: val(p, "input_sha256"), selection_reason: str(p, "selection_reason"),
                decision: val(p, "decision"), carried_from_release: str(p, "carried_from_release"), raw: p,
            });
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

/** An active station. */
export class Station {
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
    readonly #release: Release;

    /** @internal */
    constructor(raw: JsonObject, entry: IndexEntry, release: Release) {
        this.raw = raw;
        this.#release = release;
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
        const recId = entry.recommended_set_id;
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
        this.#offsets = off === null ? null : Object.freeze({
            reference_station_id: str(off, "reference_station_id"),
            time_offset_high_min: num(off, "time_offset_high_min"), time_offset_low_min: num(off, "time_offset_low_min"),
            height_offset_high: num(off, "height_offset_high"), height_offset_low: num(off, "height_offset_low"),
            height_adjusted_type: en(off["height_adjusted_type"], ["R", "A"] as const) as HeightAdjustedType | Other | null,
            licence_id: str(off, "licence_id"),
        });
        Object.freeze(this);
    }

    /** @internal True if this station was read from release `r`. */
    _from(r: Release): boolean {
        return this.#release === r;
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
        if (options === null || typeof options !== "object") throw new InvalidArgumentError("options must be an object");
        const inc = options.includeNoConstants ?? false;
        if (typeof inc !== "boolean") throw new InvalidArgumentError("includeNoConstants must be a boolean");
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

function checkNumber(v: unknown, what: string, lo: number, hi: number): number {
    if (typeof v !== "number" || !Number.isFinite(v) || v < lo || v > hi) {
        throw new InvalidArgumentError(`${what} must be a number from ${lo} to ${hi}; got ${JSON.stringify(v)}`);
    }
    return v;
}

/** `limit` is an integer of 1 or more, or absent / null for no limit (spec 4.4, CR D36). */
function checkLimit(v: unknown): number | null {
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
}

function checkFilters(f: StationFilters | undefined | null): CheckedFilters {
    if (f !== undefined && f !== null && typeof f !== "object") throw new InvalidArgumentError("filters must be an object");
    const out: CheckedFilters = { country: null, type: null, kind: null, source: null, sourceType: null };
    for (const k of ["country", "type", "kind", "source", "sourceType"] as const) {
        const v: unknown = f ? f[k] : undefined;
        if (v === undefined || v === null) continue;
        if (typeof v !== "string") throw new InvalidArgumentError(`filter ${k} must be a string; got ${JSON.stringify(v)}`);
        out[k] = v;
    }
    return out;
}

const STATION_TYPE_VALUES = ["reference", "subordinate"] as const;
const KINDS = ["tide", "current"] as const;
const SOURCE_TYPES = ["official", "gauge", "model"] as const;

/** An enum filter compares the typed value: an unknown value in the data is "other", so "other" matches it and its
 * raw string matches nothing (spec 4.4, CR2 DR7). */
function matches(e: IndexEntry, f: CheckedFilters): boolean {
    if (f.country !== null && e.country !== f.country) return false;
    if (f.type !== null && en(e.type, STATION_TYPE_VALUES) !== f.type) return false;
    if (f.kind !== null && en(e.kind, KINDS) !== f.kind) return false;
    if (f.source !== null && !e.usable_sources.includes(f.source)) return false;
    if (f.sourceType !== null && en(e.recommended_source_type, SOURCE_TYPES) !== f.sourceType) return false;
    return true;
}

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

const LRU_SIZE = 256;
// The reference links a walk follows (spec 6.2 kind, 4.6 attribution).
const MAX_LINKS = 16;

/** One loaded release. It is immutable and has every query method. */
export class Release {
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
    readonly #source: StationSource;
    readonly #active: IndexEntry[];
    readonly #pos: Map<IndexEntry, number>;
    readonly #byId: Map<string, IndexEntry>;
    readonly #tombById: Map<string, IndexEntry>;
    readonly #alias: Map<string, Map<string, IndexEntry>>;
    readonly #subs: Map<string, IndexEntry[]>;
    readonly #conventions: readonly Convention[];
    readonly #licences: readonly Licence[];
    readonly #cache = new Map<string, Station | Tombstone>();
    readonly #lru: number;
    #closed = false;

    /** @internal */
    constructor(header: ReleaseHeader, entries: IndexEntry[], source: StationSource, files: readonly FileInfo[], eager: boolean,
        zenodoVersionDoi: string | null, warn: (message: string) => void = () => undefined) {
        this.#source = source;
        this.#lru = eager ? Infinity : LRU_SIZE;
        const r = header.release;
        this.datestamp = str(r, "datestamp") ?? "";
        this.created = checkedTime(r["created"], "release.created");
        this.format_version = header.format_version;
        this.concept_doi = str(r, "concept_doi");
        this.zenodo_version_doi = zenodoVersionDoi;
        this.source_versions = Object.freeze(Object.fromEntries(Object.entries(obj(r, "source_versions") ?? {})
            .filter((e): e is [string, string] => typeof e[1] === "string")));
        this.build_commit = str(r, "build_commit");
        this.changelog_url = str(r, "changelog_url");
        this.files = Object.freeze(files.map((f) => Object.freeze({ ...f })));
        this.#pos = new Map(entries.map((e, i) => [e, i]));
        this.#active = entries.filter((e) => e.status === "active").sort((a, b) => cmp(a.station_id, b.station_id));
        this.#byId = new Map(this.#active.map((e) => [e.station_id, e]));
        this.#tombById = new Map(entries.filter((e) => e.status === "removed").map((e) => [e.station_id, e]));
        for (const e of entries) {
            // a status this SDK does not know (a newer minor's value): not a station, not a tombstone, in no query and no
            // count; said once, at load (CR2 DR8)
            if (e.status !== "active" && e.status !== "removed") {
                warn(`station ${e.station_id} has the status ${JSON.stringify(e.status)}, which this SDK does not know: it is left out of every query`);
            }
        }
        this.#alias = new Map();
        for (const e of this.#active) {
            for (const [system, ids] of Object.entries(e.aliases)) {
                let m = this.#alias.get(system);
                if (!m) this.#alias.set(system, (m = new Map()));
                for (const id of ids) if (!m.has(id)) m.set(id, e);
            }
        }
        this.#subs = new Map();
        for (const e of this.#active) {
            if (e.type === "subordinate" && e.reference_station_id) {
                const l = this.#subs.get(e.reference_station_id) ?? [];
                l.push(e);
                this.#subs.set(e.reference_station_id, l);
            }
        }
        this.#conventions = Object.freeze(header.conventions.map((c) => Object.freeze({
            convention_id: str(c, "convention_id") ?? "",
            phase_reference: en(c["phase_reference"], ["greenwich_utc", "local"] as const),
            utc_offset_hours: num(c, "utc_offset_hours"), v0_model: str(c, "v0_model"),
            nodal_handling: en(c["nodal_handling"], ["f_u_at_prediction", "none"] as const),
            nodal_formula_ids: val(c, "nodal_formula_ids"), constituent_table_version: str(c, "constituent_table_version"),
            tables_sha256: str(c, "tables_sha256"), canary: val(c, "canary"), raw: c,
        })));
        this.#licences = Object.freeze(header.licences.map((l) => Object.freeze({
            licence_id: str(l, "licence_id") ?? "", spdx: str(l, "spdx"), provider: str(l, "provider"),
            citation: str(l, "citation"), attribution: str(l, "attribution"), url: str(l, "url"), raw: l,
        })));
        Object.freeze(this);
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
        const i = this.#pos.get(e);
        if (i === undefined) throw new InvalidReleaseError(`station ${e.station_id} is not an entry of release ${this.datestamp}`);
        return this.#source.doc(e, i);
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
        return Object.freeze({
            // the typed values, as the Station reports them (CR2 DR7)
            type: countBy(a.map((e) => en(e.type, STATION_TYPE_VALUES))), kind: countBy(a.map((e) => en(e.kind, KINDS))),
            country: countBy(a.map((e) => e.country)),
            source: countBy(a.flatMap((e) => e.set_sources)), qc_status: countBy(a.flatMap((e) => e.set_qc_statuses)),
        });
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
        const t: Tombstone = Object.freeze({
            station_id: e.station_id, name: str(raw, "name"),
            status: en(raw["status"], ["active", "removed"] as const) ?? "other",
            removed_in: str(raw, "removed_in"),
            removed_reason: en(raw["removed_reason"], ["merged", "duplicate"] as const),
            merged_into: str(raw, "merged_into"), detail: str(raw, "detail"), raw,
        });
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

    /** Iterate active stations ordered by station_id. Bad filters fail here, not at the first next(). */
    iterStations(filters: StationFilters = {}): Generator<Station, void, undefined> {
        this.#open();
        const f = checkFilters(filters);
        const active = this.#active;
        const station = (e: IndexEntry) => this.#station(e);
        return (function* () {
            for (const e of active) if (matches(e, f)) yield station(e);
        })();
    }

    /** Name search, accent-insensitive and ranked (spec 4.4.1). */
    search(options: SearchOptions): readonly Station[] {
        this.#open();
        if (options === null || typeof options !== "object") throw new InvalidArgumentError("search needs an options object with name");
        const f = checkFilters(options);
        const limit = checkLimit(options.limit);
        const match = options.match ?? null;
        if (match !== null && match !== "exact") throw new InvalidArgumentError(`match must be "exact"; got ${JSON.stringify(match)}`);
        if (typeof options.name !== "string") throw new InvalidArgumentError("name must be a string");
        const q = foldName(options.name);
        if (q === "") throw new InvalidArgumentError("the query is empty");
        const ranked: [number, string, IndexEntry][] = [];
        for (const e of this.#active) {
            if (!matches(e, f)) continue;
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
            if (e.lat === null || e.lon === null || Math.abs(e.lat - lat) > band || !matches(e, f)) continue;
            const d = haversine(lat, lon, e.lat, e.lon);
            if (maxKm === null || d <= maxKm) hits.push([d, e]);
        }
        hits.sort((a, b) => a[0] - b[0] || cmp(a[1].station_id, b[1].station_id));
        return hits;
    }

    /** Stations within radiusKm (great-circle), nearest first. */
    near(options: NearOptions): readonly Nearby<Station>[] {
        this.#open();
        if (options === null || typeof options !== "object") throw new InvalidArgumentError("near needs an options object");
        const lat = checkNumber(options.lat, "lat", -90, 90);
        const lon = checkNumber(options.lon, "lon", -180, 180);
        const radius = checkNumber(options.radiusKm, "radiusKm", 0, Infinity);
        const limit = checkLimit(options.limit);
        const f = checkFilters(options);
        let hits = this.#distances(lat, lon, radius, f);
        if (limit !== null) hits = hits.slice(0, limit);
        return Object.freeze(hits.map(([d, e]) => Object.freeze({ station: this.#station(e), distance_km: d })));
    }

    /** The nearest station, within maxKm if given, or null. */
    nearest(options: NearestOptions): Nearby<Station> | null {
        this.#open();
        if (options === null || typeof options !== "object") throw new InvalidArgumentError("nearest needs an options object");
        const lat = checkNumber(options.lat, "lat", -90, 90);
        const lon = checkNumber(options.lon, "lon", -180, 180);
        const max = options.maxKm === undefined || options.maxKm === null ? null : checkNumber(options.maxKm, "maxKm", 0, Infinity);
        const hits = this.#distances(lat, lon, max, checkFilters(options));
        const h = hits[0];
        return h ? Object.freeze({ station: this.#station(h[1]), distance_km: h[0] }) : null;
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
        if (stations === undefined || stations === null || (Array.isArray(stations) && stations.length === 0)) {
            ids = new Set(this.#licences.map((l) => l.licence_id));
        } else {
            if (!Array.isArray(stations)) throw new InvalidArgumentError("stations must be a list of Station objects");
            ids = new Set();
            for (const s of stations) {
                if (!(s instanceof Station) || !s._from(this)) {
                    throw new InvalidArgumentError(`attribution needs Stations of release ${this.datestamp}; got ${s instanceof Station ? `${s.station_id} from another release` : JSON.stringify(s)}`);
                }
                const e = this.#byId.get(s.station_id);
                if (!e) throw new InvalidArgumentError(`station ${s.station_id} is not an active station of release ${this.datestamp}`);
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
        return `Tidal constants: OpenTideConstants ${this.datestamp}, ${ident}, CC BY 4.0. Sources: ${parts.join("; ")}`;
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
