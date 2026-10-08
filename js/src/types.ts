import type { Json, JsonObject } from "./json.js";

// Enumerated values: exactly the schema's strings (conformance/api.json "enums"). A field whose value
// this SDK does not know reads as "other" (spec 7.3).
export type Kind = "tide" | "current";
export type StationType = "reference" | "subordinate";
export type StationStatus = "active" | "removed";
export type SourceType = "official" | "gauge" | "model";
export type Quantity = "water_level" | "current";
export type QcStatus = "accepted" | "fallback" | "excluded";
export type LoadedFrom = "download" | "cache" | "cache_after_error" | "file" | "file_unverified";
export type PhaseReference = "greenwich_utc" | "local";
export type NodalHandling = "f_u_at_prediction" | "none";
export type CanaryStatus = "pass" | "fail" | "not_applicable";
export type HeightAdjustedType = "R" | "A";
export type DroppedReason = "rayleigh" | "noise" | "long_period_rule" | "non_tidal_rule" | "convention" | "other";
export type QcFlagName = "time_base" | "broken_record" | "microtidal" | "non_tidal_signal" | "short_record" | "sibling_disagreement";
export type DecisionTier = "rule" | "review" | "fallback";
export type DecisionOutcome = "accept" | "fallback";
export type AliasSystem = "noaa" | "gesla" | "ticon" | "xtide" | "kartverket" | "slackwater" | "webcaltides";
export type Mode = "eager" | "stream";
export type OnNetworkError = "use_cache" | "raise";
export type Format = "json" | "json.gz" | "jsonl";
export type Match = "exact";

/** A value of an enum, or "other" for a value that a newer minor format adds. */
export type Other = "other";

/** One file of a release (spec 4.3.1). */
export interface FileInfo {
    readonly name: string;
    readonly url: string | null;
    readonly size: number | null;
    readonly sha256: string | null;
}

/** An entry of the latest pointer or the release index. It has no station data. */
export interface ReleaseInfo {
    readonly datestamp: string;
    readonly format_version: string;
    readonly doi: string | null;
    readonly files: readonly FileInfo[];
}

/** The result of `update()`. */
export interface UpdateResult {
    readonly updated: boolean;
    readonly from: string;
    readonly to: string;
}

/** Counts by type, kind and country (active stations) and by source and qc_status (constant sets). */
export interface Stats {
    readonly type: Readonly<Record<string, number>>;
    readonly kind: Readonly<Record<string, number>>;
    readonly country: Readonly<Record<string, number>>;
    readonly source: Readonly<Record<string, number>>;
    readonly qc_status: Readonly<Record<string, number>>;
}

/** A removed station. */
export interface Tombstone {
    readonly station_id: string;
    readonly name: string | null;
    readonly status: StationStatus | Other;
    readonly removed_in: string | null;
    readonly removed_reason: string | null;
    readonly raw: JsonObject;
}

/** One harmonic term of a constant set. */
export interface Constituent {
    readonly name: string;
    readonly source_name: string | null;
    readonly doodson: string | null;
    readonly speed_deg_per_hour: number | null;
    readonly amplitude_m: number | null;
    /** The Greenwich phase lag g, 0 <= g < 360. */
    readonly phase_deg: number | null;
    readonly amp_uncertainty_m: number | null;
    readonly phase_uncertainty_deg: number | null;
    readonly kept_reason: string | null;
    readonly raw: JsonObject;
}

/** How the source stated its numbers. Published phases are always Greenwich (UTC). */
export interface Convention {
    readonly convention_id: string;
    readonly phase_reference: PhaseReference | Other | null;
    readonly utc_offset_hours: number | null;
    readonly v0_model: string | null;
    readonly nodal_handling: NodalHandling | Other | null;
    readonly nodal_formula_ids: Json;
    readonly constituent_table_version: string | null;
    readonly tables_sha256: string | null;
    readonly canary: Json;
    readonly raw: JsonObject;
}

/** A licence and its attribution. */
export interface Licence {
    readonly licence_id: string;
    readonly spdx: string | null;
    readonly provider: string | null;
    readonly citation: string | null;
    readonly attribution: string | null;
    readonly url: string | null;
    readonly raw: JsonObject;
}

/** Where a constant set came from. `raw` holds every field, the extra ones included. */
export interface Provenance {
    readonly build_commit: string | null;
    readonly adapter_version: string | null;
    readonly input_sha256: Json;
    readonly time_base: Json;
    readonly selection_reason: string | null;
    readonly decision: Json;
    readonly raw: JsonObject;
}

/** A QC flag of a constant set. */
export interface QcFlag {
    readonly flag: QcFlagName | Other;
    readonly verdict: Json;
    readonly values: Json;
}

/** A constituent that the fit dropped, and why. */
export interface DroppedConstituent {
    readonly name: string;
    readonly dropped_reason: DroppedReason | Other;
    readonly detail: Json;
}

/** The previous release's numbers in a validation row. */
export interface PreviousValidation {
    readonly time_mae_min: number | null;
    readonly time_p95_min: number | null;
    readonly time_bias_min: number | null;
    readonly height_mae_m: number | null;
    readonly range_error_m: number | null;
    readonly missed_events: number | null;
    readonly extra_events: number | null;
}

/** The accuracy of one set against an official reference, for one window. */
export interface Validation {
    readonly set_id: string | null;
    readonly reference_source: string | null;
    readonly reference_station: string | null;
    readonly reference_distance_km: number | null;
    readonly window: string | null;
    readonly time_mae_min: number | null;
    readonly time_p95_min: number | null;
    readonly time_bias_min: number | null;
    readonly height_mae_m: number | null;
    readonly range_error_m: number | null;
    readonly missed_events: number | null;
    readonly extra_events: number | null;
    readonly previous_release: PreviousValidation | null;
}

/** The offsets of a subordinate station from its reference station. */
export interface SubordinateOffsets {
    readonly reference_station_id: string | null;
    readonly time_offset_high_min: number | null;
    readonly time_offset_low_min: number | null;
    readonly height_offset_high: number | null;
    readonly height_offset_low: number | null;
    /** R = ratio, A = additive in metres. */
    readonly height_adjusted_type: HeightAdjustedType | Other | null;
    readonly licence_id: string | null;
}

/** The span of the record behind a constant set. */
export interface RecordSpan {
    readonly start: Date | null;
    readonly end: Date | null;
    readonly good_samples: number | null;
}

/** The datum of a constant set: the MSL offset and named datums, in metres. */
export interface Datum {
    readonly msl_offset_m: number | null;
    readonly named: Readonly<Record<string, number>>;
}

/** A station and its great-circle distance. */
export interface Nearby<S = unknown> {
    readonly station: S;
    readonly distance_km: number;
}

/** Station filters (spec 4.4). All are optional and combine with AND. */
export interface StationFilters {
    country?: string | null;
    type?: StationType | null;
    kind?: Kind | null;
    source?: string | null;
    sourceType?: SourceType | null;
}

/** Options of `search`. */
export interface SearchOptions extends StationFilters {
    name: string;
    limit?: number | null;
    match?: Match | null;
}

/** Options of `near`. */
export interface NearOptions extends StationFilters {
    lat: number;
    lon: number;
    radiusKm: number;
    limit?: number | null;
}

/** Options of `nearest`. */
export interface NearestOptions extends StationFilters {
    lat: number;
    lon: number;
    maxKm?: number | null;
}

/** Options of `constantSets`. */
export interface ConstantSetsOptions {
    includeExcluded?: boolean;
}

/** A logger: an object with debug, info and warn. */
export interface Logger {
    debug(message: string): void;
    info(message: string): void;
    warn(message: string): void;
}

/** Options of `OpenTideConstants.open` (spec 4.2). */
export interface OpenOptions {
    /** "latest" (the default) or a datestamp. */
    release?: string | null;
    /** A local .json, .json.gz or .jsonl file (Node only). */
    file?: string | null;
    cacheDir?: string | null;
    offline?: boolean | null;
    mode?: Mode | null;
    baseUrl?: string | null;
    /** Seconds, for both the connect and the read timeout. */
    timeout?: number | null;
    proxy?: string | null;
    caFile?: string | null;
    /** A suffix added to the User-Agent. */
    userAgent?: string | null;
    onNetworkError?: OnNetworkError | null;
    autoUpdate?: boolean | null;
    /** Seconds between automatic update checks. */
    updateInterval?: number | null;
    logger?: Logger | null;
    verifyOnOpen?: boolean | null;
}

/** Options of `download` (spec 4.3.2). */
export interface DownloadOptions {
    /** "latest" (the default) or a datestamp. */
    release?: string | null;
    /** The folder to write into. It is created if needed. */
    to: string;
    formats?: readonly Format[] | null;
    overwrite?: boolean | null;
}

/** Options of `prune`. */
export interface PruneOptions {
    keep?: number | null;
}
