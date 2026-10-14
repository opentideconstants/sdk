import type { Json, JsonObject } from "./json.js";

// Enumerated values: exactly the schema's strings (conformance/api.json "enums"). A field whose value
// this SDK does not know reads as "other" (spec 7.3).
export type Kind = "tide" | "current";
export type StationType = "reference" | "subordinate";
export type StationStatus = "active" | "removed";
export type SourceType = "official" | "gauge" | "model";
export type Quantity = "water_level" | "current";
export type QcStatus = "ok" | "flagged" | "no_constants";
export type RemovedReason = "merged" | "duplicate";
export type TimeBaseCode = "verified" | "corrected" | "unverified" | "disputed";
export type LoadedFrom = "download" | "cache" | "cache_after_error" | "file" | "file_unverified";
export type PhaseReference = "greenwich_utc" | "local";
export type NodalHandling = "f_u_at_prediction" | "none";
export type CanaryStatus = "pass" | "fail" | "not_applicable";
export type HeightAdjustedType = "R" | "A";
export type DroppedReason = "rayleigh" | "noise" | "long_period_rule" | "non_tidal_rule" | "convention" | "other";
export type QcFlagName = "time_base" | "broken_record" | "microtidal" | "non_tidal_signal" | "short_record" | "sibling_disagreement"
    | "carried_over" | "fallback:time_base_disputed" | "fallback:time_base_unresolved" | "fallback:refused_fit" | "fallback:short_record_uncalibrated" | "fallback:short_record_long_period" | "fallback:published_full_list" | "fallback:reliability_withheld" | "fallback:licence_reading" | "fallback:datum_gate_failed" | "fallback:not_in_otc_input" | "fallback:historical_offsets";
export type DecisionTier = "rule" | "review" | "fallback";
export type DecisionOutcome = "accept" | "fallback";
export type AliasSystem = "noaa" | "gesla" | "ticon" | "xtide" | "kartverket" | "slackwater" | "webcaltides" | "linz"
    | "shom" | "pegelonline" | "rws" | "mi" | "dmi" | "smhi" | "fmi" | "uhslc";
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
    /** The all-versions (concept) DOI, or null. */
    readonly concept_doi: string | null;
    /** The DOI of this release's own Zenodo version, or null when it has none. */
    readonly zenodo_version_doi: string | null;
    /** The digest of the release's data-bearing content (passed through). */
    readonly content_sha256: string | null;
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
    readonly removed_reason: RemovedReason | Other | null;
    /** The OTC station id that holds the records of a merged station, or null. */
    readonly merged_into: string | null;
    readonly detail: string | null;
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
    /** true: the licence allows commercial use, on its own terms; false: non-commercial use only (spec 4.6). */
    readonly commercial_use: boolean;
    /** What use is not allowed and why; always set when commercial_use is false. */
    readonly restriction: string | null;
    /** The upstream terms; always set when commercial_use is false. */
    readonly terms_url: string | null;
    readonly raw: JsonObject;
}

/** The build that wrote a constant set (`provenance.build`). */
export interface ProvenanceBuild {
    readonly build_commit: string | null;
    readonly built_at: Date | null;
    readonly fetched_at: Date | null;
    readonly run_id: string | null;
    readonly tool_versions: Readonly<Record<string, Json>> | null;
}

/** Where a constant set came from. `raw` holds every field, the extra ones included. */
export interface Provenance {
    /** The build metadata, or null in malformed input that has none (spec 4.6). */
    readonly build: ProvenanceBuild | null;
    readonly adapter_version: string | null;
    readonly input_sha256: Json;
    readonly selection_reason: string | null;
    readonly decision: Json;
    /** The datestamp a carried-over set comes from, or null. */
    readonly carried_from_release: string | null;
    readonly raw: JsonObject;
}

/** A QC flag of a constant set. */
export interface QcFlag {
    readonly flag: QcFlagName | Other | null;
    /** A one-line reason. */
    readonly reason: string | null;
    /** Named numbers (or null values), or null when the flag has none. */
    readonly values: Readonly<Record<string, number | null>> | null;
}

/** A time-base correction: from one time-base label to another. */
export interface TimeBaseCorrection {
    readonly from: string | null;
    readonly to: string | null;
}

/** One piece of evidence for a time-base decision. */
export interface TimeBaseEvidence {
    readonly comparator_kind: string | null;
    readonly comparator_id: string | null;
    readonly distance_km: number | null;
    readonly lag_min: number | null;
    readonly detail: string | null;
}

/** The time-base annotation of a constant set's record (spec 4.5). */
export interface TimeBase {
    readonly code: TimeBaseCode | Other | null;
    readonly reason: string | null;
    readonly declared: string | null;
    readonly published: string | null;
    /** `{from, to}` when `code` is corrected, else null. */
    readonly correction: TimeBaseCorrection | null;
    /** Months ("YYYY-MM") dropped from the record; empty when none. */
    readonly months_dropped: readonly string[];
    readonly decided_in: string | null;
    readonly decided_build_commit: string | null;
    readonly evidence: readonly TimeBaseEvidence[];
}

/** A constituent that the fit dropped, and why. */
export interface DroppedConstituent {
    readonly name: string | null;
    readonly dropped_reason: DroppedReason | Other | null;
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
    readonly offset_id: string | null;
    readonly source: string | null;
    readonly source_type: SourceType | Other | null;
    readonly source_version: string | null;
    readonly source_record_id: string | null;
    readonly qc_status: QcStatus | Other | null;
    readonly qc_flags: readonly QcFlag[];
    readonly fallback: Fallback | null;
    readonly vintage: HistoricalOffsetVintage | null;
    readonly provenance: HistoricalOffsetProvenance | null;
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
    includeFlagged?: boolean;
    includeFallback?: boolean;
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
    /** List the sets with qc_status no_constants too (default false). */
    includeNoConstants?: boolean | null;
}

/** A logger: an object with debug, info and warn. */
export interface Logger {
    debug(message: string): void;
    info(message: string): void;
    warn(message: string): void;
}

/** Options of `OpenTideConstants.open` (spec 4.2). */
export interface OpenOptions {
    commercialBasis?: "strict" | "as_published_upstream";
    historicalOffsetsPolicy?: "fallback" | "exclude";
    /** "latest" (the default) or a datestamp. */
    release?: string | null;
    /** A local .json, .json.gz or .jsonl file (Node only). */
    file?: string | null;
    cacheDir?: string | null;
    offline?: boolean | null;
    mode?: Mode | null;
    baseUrl?: string | null;
    /** Seconds, for both the connect and the read timeout: 0.001 to 1e6 (spec 5.7). */
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
    /**
     * Select only constant sets whose licence allows commercial use (spec 4.2): the effective recommended set, the
     * sourceType filter and the attribution's tide source. A boolean; left out (or undefined) is false.
     */
    commercialOnly?: boolean;
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

export type SourceRole = "gauge_station" | "published_harmonic_record" | "model" | "reference";

export type SourceDisposition = "metadata_only" | "not_fitted" | "licence_restricted" | "unavailable" | "retained";

export type FallbackReason = "time_base_disputed" | "time_base_unresolved" | "refused_fit" | "short_record_uncalibrated" | "short_record_long_period" | "published_full_list" | "reliability_withheld" | "licence_reading" | "datum_gate_failed" | "not_in_otc_input" | "historical_offsets";

export interface SourceRecord {
    readonly source: string;
    readonly source_version: string;
    readonly source_record_id: string;
    readonly role: SourceRole | Other;
    readonly disposition: SourceDisposition | Other;
    readonly detail: string;
    readonly licence_id: string | null;
    readonly upstream_licence_id: string | null;
    readonly published_set_ids: readonly string[];
    readonly provenance: JsonObject;
    readonly original_metadata: JsonObject;
    readonly original_harmonics: JsonObject | null;
    readonly licence: Licence | null;
    readonly upstreamLicence: Licence | null;
    readonly raw: JsonObject;
}

export interface Fallback {
    readonly reason: FallbackReason | Other;
    readonly basis: string;
    readonly otc_finding: string;
    readonly preferred_set_id: string | null;
    readonly raw: JsonObject;
}

export interface HistoricalOffsetVintage {
    readonly publication_year: number;
    readonly source_lifecycle: string;
    readonly removal_events: readonly JsonObject[];
    readonly current_validity: string;
    readonly current_accuracy: string;
    readonly reference_2020_equivalence: string;
    readonly reference_2020_equivalence_sha256: string | null;
}

export interface HistoricalOffsetProvenance {
    readonly source_manifest_sha256: string;
    readonly input_sha256: readonly string[];
    readonly book: string;
    readonly annual_table_row: number;
    readonly printed_page: number;
    readonly pdf_page: number;
    readonly raw_row_text: string;
    readonly raw_values_json: string;
    readonly id_crosswalk: JsonObject;
    readonly reference_binding: JsonObject;
    readonly acceptance_report_sha256: string;
}

export type ExtremeType = "high" | "low";

export type CurrentEventType = "max_flood" | "max_ebb" | "slack_before_flood" | "slack_before_ebb";

export type PredictionMethod = "harmonic" | "folded_offsets" | "offsets";
