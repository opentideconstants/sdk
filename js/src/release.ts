import { compareDatestamps, foldName } from "./constants.js";
import {
    InvalidArgumentError, InvalidReleaseError, StationNotFoundError, StationRemovedError,
} from "./errors.js";
import { arr, deepFreeze, en, isObject, num, obj, str, time, val, type Json, type JsonObject } from "./json.js";
import type {
    ConstantSetsOptions, Constituent, Convention, Datum, DroppedConstituent, FileInfo, HeightAdjustedType, Kind,
    Licence, NearOptions, NearestOptions, Nearby, Other, Provenance, QcFlag, QcStatus, Quantity, RecordSpan,
    SearchOptions, SourceType, StationFilters, StationStatus, StationType, Stats, SubordinateOffsets, Tombstone,
    Validation,
} from "./types.js";

const EARTH_R_KM = 6371.0088;
const DEG = Math.PI / 180;

// ------------------------------------------------------------------------------------------ index

/** @internal One line (station or tombstone) of a release, as the stream index holds it (spec 6.2). */
export interface IndexEntry {
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
    const cs = conventions.filter(isObject);
    const ls = licences.filter(isObject);
    if (cs.some((c) => typeof c["convention_id"] !== "string") || ls.some((l) => typeof l["licence_id"] !== "string")) {
        throw new InvalidReleaseError("a convention or licence has no id");
    }
    return deepFreeze({ format_version: fv, release, conventions: cs, licences: ls });
}

function aliasMap(doc: JsonObject): Record<string, string[]> {
    const out: Record<string, string[]> = {};
    const a = obj(doc, "aliases");
    if (!a) return out;
    for (const [system, ids] of Object.entries(a)) {
        if (typeof ids === "string") out[system] = [ids];
        else if (Array.isArray(ids)) out[system] = ids.filter((x): x is string => typeof x === "string");
    }
    return out;
}

/**
 * @internal Index one station document and check its references (spec 6.1: a reference that does not
 * resolve is invalid_release at load). `kind` of a subordinate with offsets only is resolved later.
 */
export function indexDoc(doc: unknown, header: ReleaseHeader, offset: number, length: number,
    conventions: Set<string>, licences: Set<string>): IndexEntry {
    if (!isObject(doc)) throw new InvalidReleaseError("a station is not a JSON object");
    const id = doc["station_id"];
    const status = doc["status"];
    if (typeof id !== "string" || typeof status !== "string") throw new InvalidReleaseError("a station has no station_id or status");
    void header;
    const sets = arr(doc, "constant_sets").filter(isObject);
    const recId = str(doc, "recommended_set_id");
    let rec: JsonObject | null = null;
    const names = new Set<string>();
    for (const cs of sets) {
        const conv = str(cs, "convention_id");
        const lic = str(cs, "licence_id");
        if (typeof cs["set_id"] !== "string") throw new InvalidReleaseError(`a constant set of ${id} has no set_id`);
        if (conv === null || !conventions.has(conv)) throw new InvalidReleaseError(`set ${String(cs["set_id"])}: convention_id ${JSON.stringify(conv)} does not resolve`);
        if (lic === null || !licences.has(lic)) throw new InvalidReleaseError(`set ${String(cs["set_id"])}: licence_id ${JSON.stringify(lic)} does not resolve`);
        if (cs["set_id"] === recId) rec = cs;
        for (const c of arr(cs, "constituents")) if (isObject(c) && typeof c["name"] === "string") names.add(c["name"]);
    }
    if (status === "active") {
        if (typeof doc["lat"] !== "number" || typeof doc["lon"] !== "number") throw new InvalidReleaseError(`station ${id} has no lat or lon`);
        if (recId !== null && rec === null) throw new InvalidReleaseError(`station ${id}: recommended_set_id ${recId} does not resolve`);
    }
    const off = obj(doc, "subordinate_offsets");
    const type = str(doc, "type");
    let kind: string | null = null;
    if (rec) {
        const q = str(rec, "quantity");
        kind = q === "water_level" ? "tide" : q === "current" ? "current" : "other";
    }
    return {
        offset, length, station_id: id, status,
        name: str(doc, "name") ?? "", name_folded: foldName(str(doc, "name") ?? ""),
        country: str(doc, "country"), type, kind, lat: num(doc, "lat"), lon: num(doc, "lon"),
        aliases: aliasMap(doc),
        reference_station_id: type === "subordinate" && off ? str(off, "reference_station_id") : null,
        recommended_set_id: rec ? recId : null,
        recommended_source_type: rec ? str(rec, "source_type") : null,
        recommended_licence_id: rec ? str(rec, "licence_id") : null,
        offsets_licence_id: off ? str(off, "licence_id") : null,
        usable_sources: [...new Set(sets.filter((cs) => cs["qc_status"] !== "excluded").map((cs) => str(cs, "source")).filter((s): s is string => s !== null))],
        set_sources: sets.map((cs) => str(cs, "source") ?? ""),
        set_qc_statuses: sets.map((cs) => str(cs, "qc_status") ?? ""),
        constituent_names: [...names].sort(),
    };
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
        this.record_span = span === null ? null : Object.freeze({ start: time(span["start"]), end: time(span["end"]), good_samples: num(span, "good_samples") });
        const datum = obj(raw, "datum");
        this.datum = datum === null ? null : Object.freeze({
            msl_offset_m: num(datum, "msl_offset_m"),
            named: Object.freeze(Object.fromEntries(Object.entries(obj(datum, "named") ?? {}).filter((e): e is [string, number] => typeof e[1] === "number"))),
        });
        this.qc_status = en(raw["qc_status"], ["accepted", "fallback", "excluded"] as const);
        this.qc_flags = Object.freeze(arr(raw, "qc_flags").filter(isObject).map((f) => Object.freeze({
            flag: en(f["flag"], ["time_base", "broken_record", "microtidal", "non_tidal_signal", "short_record", "sibling_disagreement"] as const) ?? "other",
            verdict: val(f, "verdict"), values: val(f, "values"),
        })));
        this.dropped_constituents = Object.freeze(arr(raw, "dropped_constituents").filter(isObject).map((d) => Object.freeze({
            name: str(d, "name") ?? "",
            dropped_reason: en(d["dropped_reason"], ["rayleigh", "noise", "long_period_rule", "non_tidal_rule", "convention", "other"] as const) ?? "other",
            detail: val(d, "detail"),
        })));
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
            this.#provenance = Object.freeze({
                build_commit: str(p, "build_commit"), adapter_version: str(p, "adapter_version"),
                input_sha256: val(p, "input_sha256"), time_base: val(p, "time_base"),
                selection_reason: str(p, "selection_reason"), decision: val(p, "decision"), raw: p,
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

    /** @internal */
    constructor(raw: JsonObject, entry: IndexEntry, release: Release) {
        this.raw = raw;
        this.station_id = entry.station_id;
        this.name = str(raw, "name") ?? "";
        this.country = str(raw, "country");
        this.lat = entry.lat ?? NaN;
        this.lon = entry.lon ?? NaN;
        this.type = en(raw["type"], ["reference", "subordinate"] as const);
        this.kind = entry.kind === null ? null : en(entry.kind, ["tide", "current"] as const);
        this.timezone = str(raw, "timezone");
        this.aliases = Object.freeze(Object.fromEntries(Object.entries(entry.aliases).map(([k, v]) => [k, Object.freeze([...v])])));
        this.status = en(raw["status"], ["active", "removed"] as const) ?? "other";
        this.#validation = Object.freeze(arr(raw, "validation").filter(isObject).map(validationOf));
        const recId = entry.recommended_set_id;
        this.#sets = Object.freeze(arr(raw, "constant_sets").filter(isObject).map((cs) => {
            const setId = str(cs, "set_id");
            const rows = this.#validation.filter((v) => v.set_id === setId)
                .map((v, i) => [v, i] as const)
                .sort((a, b) => cmp(a[0].window ?? "", b[0].window ?? "") || a[1] - b[1]).map((x) => x[0]);
            return new ConstantSet(cs, setId === recId, release.convention(str(cs, "convention_id") ?? "") as Convention,
                release.licence(str(cs, "licence_id") ?? "") as Licence, Object.freeze(rows));
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

    /** The recommended set first, then the others by set_id. Excluded sets are left out unless asked for. */
    constantSets(options: ConstantSetsOptions = {}): readonly ConstantSet[] {
        const inc = options.includeExcluded ?? false;
        if (typeof inc !== "boolean") throw new InvalidArgumentError("includeExcluded must be a boolean");
        const sets = this.#sets.filter((s) => inc || s.qc_status !== "excluded");
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

function cmp(a: string, b: string): number {
    return a < b ? -1 : a > b ? 1 : 0;
}

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

function checkLimit(v: unknown): number | null {
    if (v === undefined || v === null) return null;
    if (typeof v !== "number" || !Number.isInteger(v) || v < 0) throw new InvalidArgumentError(`limit must be a non-negative integer; got ${JSON.stringify(v)}`);
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

function matches(e: IndexEntry, f: CheckedFilters): boolean {
    if (f.country !== null && e.country !== f.country) return false;
    if (f.type !== null && e.type !== f.type) return false;
    if (f.kind !== null && e.kind !== f.kind) return false;
    if (f.source !== null && !e.usable_sources.includes(f.source)) return false;
    if (f.sourceType !== null && e.recommended_source_type !== f.sourceType) return false;
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
    const out: Record<string, number> = {};
    for (const v of values) if (v !== null) out[v] = (out[v] ?? 0) + 1;
    return Object.freeze(Object.fromEntries(Object.entries(out).sort((a, b) => cmp(a[0], b[0]))));
}

const LRU_SIZE = 256;

/** One loaded release. It is immutable and has every query method. */
export class Release {
    readonly datestamp: string;
    readonly created: Date | null;
    readonly format_version: string;
    readonly doi: string | null;
    readonly concept_doi: string | null;
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
    constructor(header: ReleaseHeader, entries: IndexEntry[], source: StationSource, files: readonly FileInfo[], eager: boolean) {
        this.#source = source;
        this.#lru = eager ? Infinity : LRU_SIZE;
        const r = header.release;
        this.datestamp = str(r, "datestamp") ?? "";
        this.created = time(r["created"]);
        this.format_version = header.format_version;
        this.doi = str(r, "doi");
        this.concept_doi = str(r, "concept_doi");
        this.source_versions = Object.freeze(Object.fromEntries(Object.entries(obj(r, "source_versions") ?? {})
            .filter((e): e is [string, string] => typeof e[1] === "string")));
        this.build_commit = str(r, "build_commit");
        this.changelog_url = str(r, "changelog_url");
        this.files = Object.freeze(files.map((f) => Object.freeze({ ...f })));
        this.#pos = new Map(entries.map((e, i) => [e, i]));
        this.#active = entries.filter((e) => e.status === "active").sort((a, b) => cmp(a.station_id, b.station_id));
        this.#byId = new Map(this.#active.map((e) => [e.station_id, e]));
        this.#tombById = new Map(entries.filter((e) => e.status === "removed").map((e) => [e.station_id, e]));
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

    /** @internal Release the file handle (stream mode). */
    _close(): void {
        if (!this.#closed) {
            this.#closed = true;
            this.#source.close();
        }
    }

    #doc(e: IndexEntry): JsonObject {
        return this.#source.doc(e, this.#pos.get(e) ?? 0);
    }

    #station(e: IndexEntry): Station {
        const hit = this.#cache.get(e.station_id);
        if (hit instanceof Station) {
            this.#cache.delete(e.station_id);
            this.#cache.set(e.station_id, hit);
            return hit;
        }
        const s = new Station(this.#doc(e), e, this);
        this.#cache.set(e.station_id, s);
        if (this.#cache.size > this.#lru) {
            const first = this.#cache.keys().next().value;
            if (first !== undefined) this.#cache.delete(first);
        }
        return s;
    }

    get conventions(): readonly Convention[] {
        return this.#conventions;
    }

    convention(conventionId: string): Convention | null {
        return this.#conventions.find((c) => c.convention_id === conventionId) ?? null;
    }

    get licences(): readonly Licence[] {
        return this.#licences;
    }

    licence(licenceId: string): Licence | null {
        return this.#licences.find((l) => l.licence_id === licenceId) ?? null;
    }

    /** The constituent names used by any set, sorted. */
    get constituentNames(): readonly string[] {
        const names = new Set<string>();
        for (const e of this.#active) for (const n of e.constituent_names) names.add(n);
        return Object.freeze([...names].sort(cmp));
    }

    get stats(): Stats {
        const a = this.#active;
        return Object.freeze({
            type: countBy(a.map((e) => e.type)), kind: countBy(a.map((e) => e.kind)), country: countBy(a.map((e) => e.country)),
            source: countBy(a.flatMap((e) => e.set_sources)), qc_status: countBy(a.flatMap((e) => e.set_qc_statuses)),
        });
    }

    /** The number of active stations. */
    get stationCount(): number {
        return this.#active.length;
    }

    get tombstoneCount(): number {
        return this.#tombById.size;
    }

    /** The dataset citation, with the version DOI. */
    get citation(): string {
        const year = this.created ? this.created.getUTCFullYear() : this.datestamp.slice(0, 4);
        const where = this.doi ? `https://doi.org/${this.doi}` : `https://data.opentideconstants.org/OTC_${this.datestamp}.json`;
        return `OpenTideConstants contributors (${year}). OpenTideConstants, release ${this.datestamp} [Data set]. ${where}`;
    }

    /** An active station by its OTC id, or null. */
    station(stationId: string): Station | null {
        const e = this.#byId.get(stationId);
        return e ? this.#station(e) : null;
    }

    /** An active station by its OTC id; station_not_found or station_removed otherwise. */
    requireStation(stationId: string): Station {
        const s = this.station(stationId);
        if (s) return s;
        const t = this.tombstone(stationId);
        if (t) throw new StationRemovedError(stationId, t, t.removed_reason);
        throw new StationNotFoundError(stationId);
    }

    /** The tombstone of a removed station, or null. */
    tombstone(stationId: string): Tombstone | null {
        const e = this.#tombById.get(stationId);
        if (!e) return null;
        const hit = this.#cache.get(`tomb:${stationId}`);
        if (hit && !(hit instanceof Station)) return hit;
        const raw = this.#doc(e);
        const t: Tombstone = Object.freeze({
            station_id: e.station_id, name: str(raw, "name"),
            status: en(raw["status"], ["active", "removed"] as const) ?? "other",
            removed_in: str(raw, "removed_in"), removed_reason: str(raw, "removed_reason"), raw,
        });
        this.#cache.set(`tomb:${stationId}`, t);
        return t;
    }

    /** A station by an id in another system (noaa, gesla, ticon, xtide, kartverket, slackwater, webcaltides, ...). */
    stationByAlias(system: string, aliasId: string): Station | null {
        const e = this.#alias.get(system)?.get(aliasId);
        return e ? this.#station(e) : null;
    }

    /** Active stations ordered by station_id. */
    stations(filters: StationFilters = {}): readonly Station[] {
        return Object.freeze([...this.iterStations(filters)]);
    }

    /** Iterate active stations ordered by station_id. */
    *iterStations(filters: StationFilters = {}): Generator<Station, void, undefined> {
        const f = checkFilters(filters);
        for (const e of this.#active) if (matches(e, f)) yield this.#station(e);
    }

    /** Name search, accent-insensitive and ranked (spec 4.4.1). */
    search(options: SearchOptions): readonly Station[] {
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
        if (options === null || typeof options !== "object") throw new InvalidArgumentError("nearest needs an options object");
        const lat = checkNumber(options.lat, "lat", -90, 90);
        const lon = checkNumber(options.lon, "lon", -180, 180);
        const max = options.maxKm === undefined || options.maxKm === null ? null : checkNumber(options.maxKm, "maxKm", 0, Infinity);
        const hits = this.#distances(lat, lon, max, checkFilters(options));
        const h = hits[0];
        return h ? Object.freeze({ station: this.#station(h[1]), distance_km: h[0] }) : null;
    }

    /** The reference station of a subordinate station, or null. */
    referenceStation(station: Station): Station | null {
        const e = station ? this.#byId.get(station.station_id) : undefined;
        if (!e || !e.reference_station_id) return null;
        return this.station(e.reference_station_id);
    }

    /** The subordinate stations of a reference station, ordered by station_id. */
    subordinatesOf(station: Station): readonly Station[] {
        const l = station ? this.#subs.get(station.station_id) ?? [] : [];
        return Object.freeze([...l].sort((a, b) => cmp(a.station_id, b.station_id)).map((e) => this.#station(e)));
    }

    /** The CC BY 4.0 attribution text for the given stations, or for the whole release (spec 4.6). */
    attribution(stations?: readonly (Station | null)[] | null): string {
        let ids: Set<string>;
        if (stations === undefined || stations === null) {
            ids = new Set(this.#licences.map((l) => l.licence_id));
        } else {
            if (!Array.isArray(stations)) throw new InvalidArgumentError("stations must be a list of Station objects");
            ids = new Set();
            for (const s of stations) {
                const e = s ? this.#byId.get(s.station_id) : undefined;
                if (!e) continue;
                if (e.recommended_licence_id) ids.add(e.recommended_licence_id);
                if (e.type === "subordinate" && e.reference_station_id !== null) {
                    if (e.offsets_licence_id) ids.add(e.offsets_licence_id);
                    const ref = this.#byId.get(e.reference_station_id);
                    if (ref && ref.recommended_licence_id) ids.add(ref.recommended_licence_id);
                }
            }
        }
        const parts: string[] = [];
        const seen = new Set<string>();
        for (const id of [...ids].sort(cmp)) {
            const l = this.licence(id);
            if (!l || seen.has(l.provider ?? "")) continue;
            seen.add(l.provider ?? "");
            parts.push(`${l.provider ?? ""}: ${l.attribution ?? ""}`);
        }
        const ident = this.doi ? `doi:${this.doi}` : `https://data.opentideconstants.org/OTC_${this.datestamp}.json`;
        return `Tidal constants: OpenTideConstants ${this.datestamp}, ${ident}, CC BY 4.0. Sources: ${parts.join("; ")}`;
    }
}

/** @internal Build the index of an eager document's stations. */
export function indexStations(header: ReleaseHeader, docs: readonly Json[]): IndexEntry[] {
    const convs = new Set(header.conventions.map((c) => str(c, "convention_id") ?? ""));
    const lics = new Set(header.licences.map((l) => str(l, "licence_id") ?? ""));
    const entries = docs.map((d, i) => indexDoc(d, header, i, 0, convs, lics));
    resolveKinds(entries);
    return entries;
}

/** @internal Sort datestamps newest first. */
export function newestFirst(ds: Iterable<string>): string[] {
    return [...ds].sort((a, b) => compareDatestamps(b, a));
}
