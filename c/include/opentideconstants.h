/*
 * opentideconstants.h - the OpenTideConstants C library (SDK spec section 6.4).
 *
 * MIT licence. Reads an OpenTideConstants release from OTC_{D}.jsonl plus
 * OTC_{D}.meta.json. Links only the C standard library and libm (and the
 * platform thread library for the per-handle error lock).
 *
 * Conventions (spec 4.1, 6.4):
 *   - Every call returns an otc_status. OTC_OK is 0.
 *   - "No value" is OTC_E_NOT_FOUND; an output pointer then stays NULL.
 *   - Strings out: the caller passes buf and len. The function writes at most
 *     len bytes, always NUL-terminates when len > 0, and stores the needed size
 *     (with the NUL) in *needed. A buffer that is too small gives
 *     OTC_E_BUFFER_TOO_SMALL. buf = NULL and len = 0 only report the size.
 *   - Lists out: the caller passes an array and its capacity, and gets the
 *     count back in *count (OTC_E_BUFFER_TOO_SMALL with the needed count).
 *     out = NULL and cap = 0 only report the count.
 *   - Missing numbers are NaN; missing counts are -1; missing enums are
 *     OTC_<ENUM>_UNSET; enum values the library does not know are
 *     OTC_<ENUM>_OTHER.
 *   - Ownership: otc_release and otc_station, otc_tombstone, otc_stats and
 *     otc_iter handles are owned by the caller and freed with their _free /
 *     otc_close / otc_iter_close call. Every other pointer is borrowed: from
 *     the station (sets, constituents, validation rows, flags, strings in
 *     structs) or from the release (conventions, licences, ids in hit lists).
 *   - Threads: a release handle is read-only after otc_open_file and may be
 *     used by several threads at once. A station handle belongs to the thread
 *     that made it.
 */
#ifndef OPENTIDECONSTANTS_H
#define OPENTIDECONSTANTS_H

#include <limits.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define OTC_VERSION "0.1.0"
#define OTC_VERSION_MAJOR 0
#define OTC_VERSION_MINOR 1
#define OTC_VERSION_PATCH 0
/* Changes only with a breaking ABI change (and with the soname major). */
#define OTC_ABI_VERSION 1
/* The format major this library reads (SUPPORTED_FORMAT_MAJORS = [1]). */
#define OTC_FORMAT_MAJOR 1
/* The newest format version this library reads (SUPPORTED_FORMAT_VERSION, spec
 * 7.4). A release whose release.min_reader_version is newer is refused with
 * OTC_E_READER_TOO_OLD. Equals supported_format_version in c/supported-formats.json. */
#define OTC_FORMAT_VERSION "1.0"

/* OTC_API marks the public functions. A build of the library defines
 * OTC_BUILDING (and OTC_SHARED for a shared library): then only these
 * functions are exported (the build hides every other symbol, B4-5). An
 * application needs to define nothing. */
#ifndef OTC_API
#if defined(OTC_BUILDING) && defined(OTC_SHARED) && defined(_WIN32)
#define OTC_API __declspec(dllexport)
#elif defined(OTC_BUILDING) && defined(OTC_SHARED) && (defined(__GNUC__) || defined(__clang__))
#define OTC_API __attribute__((visibility("default")))
#else
#define OTC_API
#endif
#endif

/* ------------------------------------------------------------------ status */

typedef enum otc_status {
    OTC_OK = 0,
    OTC_E_NOT_FOUND = 1,
    OTC_E_NETWORK = 2,
    OTC_E_RELEASE_NOT_FOUND = 3,
    OTC_E_OFFLINE_UNAVAILABLE = 4,
    OTC_E_CHECKSUM = 5,
    OTC_E_UNSUPPORTED_FORMAT = 6,
    OTC_E_INVALID_RELEASE = 7,
    OTC_E_STATION_NOT_FOUND = 8,
    OTC_E_STATION_REMOVED = 9,
    OTC_E_PINNED_RELEASE = 10,
    OTC_E_CACHE = 11,
    OTC_E_FILE_EXISTS = 12,
    OTC_E_IO = 13,
    OTC_E_INVALID_ARGUMENT = 14,
    OTC_E_BUFFER_TOO_SMALL = 15,
    OTC_E_NOMEM = 16,
    OTC_E_NOT_BUILT = 17,
    OTC_E_UNSUPPORTED_CONVENTION = 18, /* phase 2 */
    OTC_E_READER_TOO_OLD = 19          /* release.min_reader_version is newer than OTC_FORMAT_VERSION */
} otc_status;

/* The stable error code of a status ("checksum_mismatch", ...); "ok" for OTC_OK. */
OTC_API const char *otc_status_code(otc_status status);

/* Error detail for calls with no release handle (spec 4.8). The library
 * writes into it only when struct_size is at least the size it knows (set
 * it with otc_error_init()); a smaller struct is left alone, never written
 * past (spec 6.4 ABI). */
typedef struct otc_error {
    size_t     struct_size;        /* set by otc_error_init() */
    otc_status status;
    int        http_status;        /* 0 if no HTTP response */
    char       file[1024];         /* truncated to fit, always NUL-terminated */
    char       expected_sha256[65];
    char       actual_sha256[65];
    char       message[512];       /* truncated to fit, always NUL-terminated */
} otc_error;
OTC_API void otc_error_init(otc_error *err);

/* ------------------------------------------------------------------- enums */

typedef enum otc_kind { OTC_KIND_UNSET = 0, OTC_KIND_TIDE, OTC_KIND_CURRENT, OTC_KIND_OTHER } otc_kind;
typedef enum otc_station_type_t {
    OTC_STATION_TYPE_UNSET = 0, OTC_STATION_TYPE_REFERENCE, OTC_STATION_TYPE_SUBORDINATE, OTC_STATION_TYPE_OTHER
} otc_station_type_t;
typedef enum otc_station_status_t {
    OTC_STATION_STATUS_UNSET = 0, OTC_STATION_STATUS_ACTIVE, OTC_STATION_STATUS_REMOVED, OTC_STATION_STATUS_OTHER
} otc_station_status_t;
typedef enum otc_source_type {
    OTC_SOURCE_TYPE_UNSET = 0, OTC_SOURCE_TYPE_OFFICIAL, OTC_SOURCE_TYPE_GAUGE, OTC_SOURCE_TYPE_MODEL, OTC_SOURCE_TYPE_OTHER
} otc_source_type;
typedef enum otc_quantity {
    OTC_QUANTITY_UNSET = 0, OTC_QUANTITY_WATER_LEVEL, OTC_QUANTITY_CURRENT, OTC_QUANTITY_OTHER
} otc_quantity;
typedef enum otc_qc_status {
    OTC_QC_STATUS_UNSET = 0, OTC_QC_STATUS_OK, OTC_QC_STATUS_FLAGGED, OTC_QC_STATUS_NO_CONSTANTS, OTC_QC_STATUS_OTHER
} otc_qc_status;
typedef enum otc_removed_reason {
    OTC_REMOVED_REASON_UNSET = 0, OTC_REMOVED_REASON_MERGED, OTC_REMOVED_REASON_DUPLICATE, OTC_REMOVED_REASON_OTHER
} otc_removed_reason;
/* The enum that otc_time_base_code() returns (the type gets _t: C cannot have a
 * type and a function with the same name). */
typedef enum otc_time_base_code_t {
    OTC_TIME_BASE_CODE_UNSET = 0, OTC_TIME_BASE_CODE_VERIFIED, OTC_TIME_BASE_CODE_CORRECTED,
    OTC_TIME_BASE_CODE_UNVERIFIED, OTC_TIME_BASE_CODE_DISPUTED, OTC_TIME_BASE_CODE_OTHER
} otc_time_base_code_t;
typedef enum otc_loaded_from {
    OTC_LOADED_FROM_UNSET = 0, OTC_LOADED_FROM_DOWNLOAD, OTC_LOADED_FROM_CACHE, OTC_LOADED_FROM_CACHE_AFTER_ERROR,
    OTC_LOADED_FROM_FILE, OTC_LOADED_FROM_FILE_UNVERIFIED, OTC_LOADED_FROM_OTHER
} otc_loaded_from;
typedef enum otc_phase_reference {
    OTC_PHASE_REFERENCE_UNSET = 0, OTC_PHASE_REFERENCE_GREENWICH_UTC, OTC_PHASE_REFERENCE_LOCAL, OTC_PHASE_REFERENCE_OTHER
} otc_phase_reference;
typedef enum otc_nodal_handling {
    OTC_NODAL_HANDLING_UNSET = 0, OTC_NODAL_HANDLING_F_U_AT_PREDICTION, OTC_NODAL_HANDLING_NONE, OTC_NODAL_HANDLING_OTHER
} otc_nodal_handling;
typedef enum otc_canary_status {
    OTC_CANARY_STATUS_UNSET = 0, OTC_CANARY_STATUS_PASS, OTC_CANARY_STATUS_FAIL, OTC_CANARY_STATUS_NOT_APPLICABLE,
    OTC_CANARY_STATUS_OTHER
} otc_canary_status;
typedef enum otc_height_adjusted_type {
    OTC_HEIGHT_ADJUSTED_TYPE_UNSET = 0, OTC_HEIGHT_ADJUSTED_TYPE_R, OTC_HEIGHT_ADJUSTED_TYPE_A,
    OTC_HEIGHT_ADJUSTED_TYPE_OTHER
} otc_height_adjusted_type;
typedef enum otc_dropped_reason {
    OTC_DROPPED_REASON_UNSET = 0, OTC_DROPPED_REASON_RAYLEIGH, OTC_DROPPED_REASON_NOISE,
    OTC_DROPPED_REASON_LONG_PERIOD_RULE, OTC_DROPPED_REASON_NON_TIDAL_RULE, OTC_DROPPED_REASON_CONVENTION,
    OTC_DROPPED_REASON_OTHER /* both the schema value "other" and an unknown value */
} otc_dropped_reason;
typedef enum otc_qc_flag_kind {
    OTC_QC_FLAG_UNSET = 0, OTC_QC_FLAG_TIME_BASE, OTC_QC_FLAG_BROKEN_RECORD, OTC_QC_FLAG_MICROTIDAL,
    OTC_QC_FLAG_NON_TIDAL_SIGNAL, OTC_QC_FLAG_SHORT_RECORD, OTC_QC_FLAG_SIBLING_DISAGREEMENT, OTC_QC_FLAG_CARRIED_OVER,
    OTC_QC_FLAG_OTHER
} otc_qc_flag_kind;
typedef enum otc_decision_tier {
    OTC_DECISION_TIER_UNSET = 0, OTC_DECISION_TIER_RULE, OTC_DECISION_TIER_REVIEW, OTC_DECISION_TIER_FALLBACK,
    OTC_DECISION_TIER_OTHER
} otc_decision_tier;
typedef enum otc_decision_outcome {
    OTC_DECISION_OUTCOME_UNSET = 0, OTC_DECISION_OUTCOME_ACCEPT, OTC_DECISION_OUTCOME_FALLBACK,
    OTC_DECISION_OUTCOME_OTHER
} otc_decision_outcome;
typedef enum otc_alias_system {
    OTC_ALIAS_SYSTEM_UNSET = 0, OTC_ALIAS_SYSTEM_NOAA, OTC_ALIAS_SYSTEM_GESLA, OTC_ALIAS_SYSTEM_TICON,
    OTC_ALIAS_SYSTEM_XTIDE, OTC_ALIAS_SYSTEM_KARTVERKET, OTC_ALIAS_SYSTEM_SLACKWATER, OTC_ALIAS_SYSTEM_WEBCALTIDES,
    OTC_ALIAS_SYSTEM_LINZ, OTC_ALIAS_SYSTEM_SHOM, OTC_ALIAS_SYSTEM_PEGELONLINE, OTC_ALIAS_SYSTEM_RWS, OTC_ALIAS_SYSTEM_MI,
    OTC_ALIAS_SYSTEM_DMI, OTC_ALIAS_SYSTEM_SMHI, OTC_ALIAS_SYSTEM_FMI, OTC_ALIAS_SYSTEM_UHSLC, OTC_ALIAS_SYSTEM_OTHER
} otc_alias_system;
typedef enum otc_mode { OTC_MODE_UNSET = 0, OTC_MODE_EAGER, OTC_MODE_STREAM, OTC_MODE_OTHER } otc_mode;
typedef enum otc_on_network_error {
    OTC_ON_NETWORK_ERROR_UNSET = 0, OTC_ON_NETWORK_ERROR_USE_CACHE, OTC_ON_NETWORK_ERROR_RAISE,
    OTC_ON_NETWORK_ERROR_OTHER
} otc_on_network_error;
/* Formats are bit flags for otc_fetch_to_dir and otc_fetch_options.formats. */
typedef enum otc_format {
    OTC_FORMAT_JSON = 1, OTC_FORMAT_JSON_GZ = 2, OTC_FORMAT_JSONL = 4, OTC_FORMAT_OTHER = 8
} otc_format;
/* The formats value that means "the default formats" (OTC_FORMAT_JSONL). It
 * has every bit set, so it is never a valid set of OTC_FORMAT_* bits. 0 names
 * no format and is OTC_E_INVALID_ARGUMENT (spec 4.3.2, CR 4c). */
#define OTC_FORMATS_DEFAULT UINT_MAX
typedef enum otc_match { OTC_MATCH_UNSET = 0, OTC_MATCH_EXACT, OTC_MATCH_OTHER } otc_match;

/* The schema string of an enum value ("tide", "water_level", ...); "other"
 * for *_OTHER and NULL for *_UNSET. */
OTC_API const char *otc_kind_name(otc_kind v);
OTC_API const char *otc_station_type_name(otc_station_type_t v);
OTC_API const char *otc_station_status_name(otc_station_status_t v);
OTC_API const char *otc_source_type_name(otc_source_type v);
OTC_API const char *otc_quantity_name(otc_quantity v);
OTC_API const char *otc_qc_status_name(otc_qc_status v);
OTC_API const char *otc_removed_reason_name(otc_removed_reason v);
OTC_API const char *otc_time_base_code_name(otc_time_base_code_t v);
OTC_API const char *otc_loaded_from_name(otc_loaded_from v);
OTC_API const char *otc_phase_reference_name(otc_phase_reference v);
OTC_API const char *otc_nodal_handling_name(otc_nodal_handling v);
OTC_API const char *otc_height_adjusted_type_name(otc_height_adjusted_type v);
OTC_API const char *otc_dropped_reason_name(otc_dropped_reason v);
OTC_API const char *otc_qc_flag_kind_name(otc_qc_flag_kind v);

/* ----------------------------------------------------------------- handles */

typedef struct otc_release otc_release;           /* caller-owned: otc_close */
typedef struct otc_station otc_station_t;         /* caller-owned: otc_station_free */
typedef struct otc_tombstone otc_tombstone_t;     /* caller-owned: otc_tombstone_free */
typedef struct otc_stats otc_stats;               /* caller-owned: otc_stats_free */
typedef struct otc_iter otc_iter;                 /* caller-owned: otc_iter_close */
typedef struct otc_set otc_set;                   /* borrowed from the station */
typedef struct otc_convention otc_convention;     /* borrowed from the release */
typedef struct otc_licence otc_licence;           /* borrowed from the release */
typedef struct otc_file_info otc_file_info;       /* borrowed from the release */
typedef struct otc_qc_flag otc_qc_flag;           /* borrowed from the station */
typedef struct otc_dropped otc_dropped;           /* borrowed from the station */
typedef struct otc_record_span otc_record_span;   /* borrowed from the station */
typedef struct otc_datum otc_datum;               /* borrowed from the station */
typedef struct otc_release_info otc_release_info; /* made by otc_fetch only */
typedef struct otc_time_base otc_time_base_t;     /* borrowed from the station */
typedef struct otc_time_base_evidence otc_time_base_evidence; /* borrowed from the station */
typedef struct otc_provenance_build otc_provenance_build; /* borrowed from the station */
typedef otc_set otc_set_provenance;               /* the provenance accessors take the set */

/* ------------------------------------------------------------ open / close */

typedef void (*otc_log_fn)(void *user_data, int level, const char *message); /* level: 0 debug, 1 info, 2 warn */

typedef struct otc_open_options {
    size_t      struct_size;      /* set by otc_open_options_init() */
    bool        require_checksum; /* a missing OTC_{D}.sha256 next to the file is an error */
    otc_error  *error;            /* detail of a failed open; NULL = not wanted */
    otc_log_fn  log_fn;           /* optional */
    void       *log_user_data;
} otc_open_options;
OTC_API void otc_open_options_init(otc_open_options *opts);

/* Opens OTC_{D}.jsonl (path) with OTC_{D}.meta.json next to it. If
 * OTC_{D}.sha256 is next to it, both files are checked against it
 * (loaded_from file); otherwise loaded_from is file_unverified. A format major
 * other than OTC_FORMAT_MAJOR is OTC_E_UNSUPPORTED_FORMAT; a higher minor loads
 * (spec 7.3). A release.min_reader_version newer than OTC_FORMAT_VERSION is
 * OTC_E_READER_TOO_OLD, with a message that names both versions. opts may be NULL. */
OTC_API otc_status otc_open_file(const char *path, const otc_open_options *opts, otc_release **out);
OTC_API void otc_close(otc_release *rel);

/* The message of the last failure on this handle (spec 4.8). OTC_E_NOT_FOUND if none. */
OTC_API otc_status otc_last_error(const otc_release *rel, char *buf, size_t len, size_t *needed);
/* The status of the last failure on this handle; OTC_OK if none. */
OTC_API otc_status otc_last_error_status(const otc_release *rel);

/* Hashes path again in full and compares it with its row in sha256_path
 * (NULL: the OTC_{D}.sha256 next to path). OTC_E_CHECKSUM on a mismatch, with
 * file, expected_sha256 and actual_sha256 in err; also when sha256_path is
 * NULL and there is no OTC_{D}.sha256 next to path (a file_unverified
 * release, spec 4.3). */
OTC_API otc_status otc_verify_file(const char *path, const char *sha256_path, otc_error *err);

/* --------------------------------------------------------- release metadata */

OTC_API otc_loaded_from otc_release_loaded_from(const otc_release *rel);
OTC_API otc_status otc_release_datestamp(const otc_release *rel, char *buf, size_t len, size_t *needed);
/* release.created in UTC, "YYYY-MM-DDTHH:MM:SSZ" (whole seconds), as the other SDKs give it. */
OTC_API otc_status otc_release_created(const otc_release *rel, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_release_format_version(const otc_release *rel, char *buf, size_t len, size_t *needed);
/* The all-versions (concept) DOI, from the release document; OTC_E_NOT_FOUND when null. */
OTC_API otc_status otc_release_concept_doi(const otc_release *rel, char *buf, size_t len, size_t *needed);
/* The DOI of this release's own Zenodo version (spec 4.3). It is not in the
 * release document: otc_fetch_open takes it from the pointer or index entry
 * for this datestamp, kept in the cache's .verified record. OTC_E_NOT_FOUND
 * when there is none, and always for a release opened with otc_open_file. */
OTC_API otc_status otc_release_zenodo_version_doi(const otc_release *rel, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_release_build_commit(const otc_release *rel, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_release_changelog_url(const otc_release *rel, char *buf, size_t len, size_t *needed);
OTC_API size_t otc_release_source_version_count(const otc_release *rel);
OTC_API otc_status otc_release_source_version_at(const otc_release *rel, size_t i, char *source, size_t source_len,
                                                 size_t *source_needed, char *version, size_t version_len,
                                                 size_t *version_needed);
/* release.files (spec 4.3.1), sorted by name. */
OTC_API size_t otc_release_file_count(const otc_release *rel);
OTC_API otc_status otc_release_file_at(const otc_release *rel, size_t i, const otc_file_info **out);
OTC_API otc_status otc_file_info_name(const otc_file_info *fi, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_file_info_url(const otc_file_info *fi, char *buf, size_t len, size_t *needed);
OTC_API int64_t otc_file_info_size(const otc_file_info *fi); /* -1 if unknown */
OTC_API otc_status otc_file_info_sha256(const otc_file_info *fi, char *buf, size_t len, size_t *needed);

OTC_API size_t otc_release_station_count(const otc_release *rel);   /* active stations */
OTC_API size_t otc_release_tombstone_count(const otc_release *rel);
OTC_API otc_status otc_release_constituent_names(const otc_release *rel, const char **out, size_t cap, size_t *count);
/* The dataset citation (spec 4.6): "OpenTideConstants contributors ({year}).
 * OpenTideConstants, release {D} [Data set]. {link}{version}", where {link} is
 * https://doi.org/{concept_doi} (or https://data.opentideconstants.org/OTC_{D}.json
 * when the concept DOI is null) and {version} is
 * " (version DOI: https://doi.org/{zenodo_version_doi})" when the release has one. */
OTC_API otc_status otc_release_citation(const otc_release *rel, char *buf, size_t len, size_t *needed);
/* The CC BY 4.0 attribution text (spec 4.6): "Tidal constants: OpenTideConstants
 * {D}, doi:{concept_doi}, CC BY 4.0. Sources: {provider}: {attribution}; ...".
 * ids = NULL or n_ids = 0: every licence in the release; else the licences
 * of these stations (the recommended set's, plus for a subordinate station
 * its offsets' licence and its reference station's). An id that is not an
 * active station of the release is OTC_E_INVALID_ARGUMENT. Each provider
 * once, by licence_id; a licence with no provider gives its attribution
 * alone and is never merged. It never carries the version DOI. */
OTC_API otc_status otc_attribution(const otc_release *rel, const char *const *ids, size_t n_ids, char *buf, size_t len,
                                   size_t *needed);

/* Stats (spec 4.3): counts by type, kind and country (active stations), by
 * qc_status (every constant set; a value format 1.0 does not have counts as
 * "other") and by source (only sets with constants: qc_status ok or flagged).
 * Zero counts are left out; keys sorted. */
OTC_API otc_status otc_release_stats(const otc_release *rel, otc_stats **out);
OTC_API void otc_stats_free(otc_stats *stats);
OTC_API size_t otc_stats_type_count(const otc_stats *s);
OTC_API otc_status otc_stats_type_at(const otc_stats *s, size_t i, const char **key, int64_t *n);
OTC_API size_t otc_stats_kind_count(const otc_stats *s);
OTC_API otc_status otc_stats_kind_at(const otc_stats *s, size_t i, const char **key, int64_t *n);
OTC_API size_t otc_stats_country_count(const otc_stats *s);
OTC_API otc_status otc_stats_country_at(const otc_stats *s, size_t i, const char **key, int64_t *n);
OTC_API size_t otc_stats_source_count(const otc_stats *s);
OTC_API otc_status otc_stats_source_at(const otc_stats *s, size_t i, const char **key, int64_t *n);
OTC_API size_t otc_stats_qc_status_count(const otc_stats *s);
OTC_API otc_status otc_stats_qc_status_at(const otc_stats *s, size_t i, const char **key, int64_t *n);

/* ------------------------------------------------- conventions and licences */

OTC_API size_t otc_release_convention_count(const otc_release *rel);
OTC_API otc_status otc_release_convention_at(const otc_release *rel, size_t i, const otc_convention **out);
OTC_API otc_status otc_release_convention(const otc_release *rel, const char *convention_id, const otc_convention **out);
OTC_API otc_status otc_convention_convention_id(const otc_convention *c, char *buf, size_t len, size_t *needed);
OTC_API otc_phase_reference otc_convention_phase_reference(const otc_convention *c);
OTC_API double otc_convention_utc_offset_hours(const otc_convention *c);
OTC_API otc_status otc_convention_v0_model(const otc_convention *c, char *buf, size_t len, size_t *needed);
OTC_API otc_nodal_handling otc_convention_nodal_handling(const otc_convention *c);
OTC_API otc_status otc_convention_nodal_formula_ids_json(const otc_convention *c, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_convention_constituent_table_version(const otc_convention *c, char *buf, size_t len,
                                                            size_t *needed);
OTC_API otc_status otc_convention_tables_sha256(const otc_convention *c, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_convention_canary_json(const otc_convention *c, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_convention_raw_json(const otc_convention *c, char *buf, size_t len, size_t *needed);

OTC_API size_t otc_release_licence_count(const otc_release *rel);
OTC_API otc_status otc_release_licence_at(const otc_release *rel, size_t i, const otc_licence **out);
OTC_API otc_status otc_release_licence(const otc_release *rel, const char *licence_id, const otc_licence **out);
OTC_API otc_status otc_licence_licence_id(const otc_licence *l, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_licence_spdx(const otc_licence *l, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_licence_provider(const otc_licence *l, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_licence_citation(const otc_licence *l, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_licence_attribution(const otc_licence *l, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_licence_url(const otc_licence *l, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_licence_raw_json(const otc_licence *l, char *buf, size_t len, size_t *needed);

/* ---------------------------------------------------------- station queries */

/* Filters (spec 4.4). NULL means "not set". An unknown value gives an empty result. */
typedef struct otc_filter {
    size_t      struct_size;  /* set by otc_filter_init() */
    const char *country;      /* ISO 3166-1 alpha-3 */
    const char *type;         /* "reference" | "subordinate" */
    const char *kind;         /* "tide" | "current" */
    const char *source;       /* the station has a usable set from this source */
    const char *source_type;  /* of the recommended set: "official" | "gauge" | "model" */
    bool        match_exact;  /* otc_search only: exact matches of the folded name */
} otc_filter;
OTC_API void otc_filter_init(otc_filter *filter);

/* The limit of otc_search and otc_near that means "no limit" (spec 4.4, CR D36). */
#define OTC_NO_LIMIT SIZE_MAX

typedef struct otc_hit {      /* otc_search; the strings are borrowed from the release */
    const char *id;
    const char *name;
} otc_hit;

typedef struct otc_nearby {   /* otc_near / otc_nearest; id is borrowed from the release */
    const char *id;
    double      distance_km;
} otc_nearby;

/* An active station by OTC id; the caller frees it with otc_station_free. */
OTC_API otc_status otc_station(const otc_release *rel, const char *id, otc_station_t **out);
/* As otc_station, but OTC_E_STATION_NOT_FOUND or OTC_E_STATION_REMOVED. For a
 * removed id the handle's error (otc_last_error) names the tombstone's
 * removed_in, removed_reason and merged_into; otc_tombstone(rel, id, &t)
 * gives the tombstone itself. */
OTC_API otc_status otc_require_station(const otc_release *rel, const char *id, otc_station_t **out);
OTC_API void otc_station_free(otc_station_t *st);
OTC_API otc_status otc_tombstone(const otc_release *rel, const char *id, otc_tombstone_t **out);
OTC_API void otc_tombstone_free(otc_tombstone_t *t);
OTC_API otc_status otc_station_by_alias(const otc_release *rel, const char *system, const char *alias_id,
                                        otc_station_t **out);
/* Station ids ordered by station_id. filter may be NULL. */
OTC_API otc_status otc_stations(const otc_release *rel, const otc_filter *filter, const char **ids, size_t cap,
                                size_t *count);
OTC_API otc_status otc_iter_open(const otc_release *rel, const otc_filter *filter, otc_iter **out);
/* The next station (caller frees it), or OTC_E_NOT_FOUND at the end. */
OTC_API otc_status otc_iter_next(otc_iter *it, otc_station_t **out);
OTC_API void otc_iter_close(otc_iter *it);
/* limit: the most hits to return, 1 or more, or OTC_NO_LIMIT for all of them;
 * 0 is OTC_E_INVALID_ARGUMENT (spec 4.4, CR D36). */
OTC_API otc_status otc_search(const otc_release *rel, const char *name, const otc_filter *filter, size_t limit,
                              otc_hit *out, size_t cap, size_t *count);
/* limit as for otc_search. */
OTC_API otc_status otc_near(const otc_release *rel, double lat, double lon, double radius_km,
                            const otc_filter *filter, size_t limit, otc_nearby *out, size_t cap, size_t *count);
/* max_km NaN or +infinity means no limit. OTC_E_NOT_FOUND if nothing is in range. */
OTC_API otc_status otc_nearest(const otc_release *rel, double lat, double lon, double max_km,
                               const otc_filter *filter, otc_nearby *hit);
OTC_API otc_status otc_reference_station(const otc_release *rel, const otc_station_t *st, otc_station_t **out);
/* Subordinate station ids ordered by station_id. */
OTC_API otc_status otc_subordinates_of(const otc_release *rel, const otc_station_t *st, const char **ids, size_t cap,
                                       size_t *count);

/* ----------------------------------------------------------- station fields */

OTC_API otc_status otc_station_station_id(const otc_station_t *st, char *buf, size_t len, size_t *needed);
/* The spec 6.4 name; a function-like macro, so it does not rewrite other uses of the name. */
#define otc_station_id(st, buf, len, needed) otc_station_station_id((st), (buf), (len), (needed))
OTC_API otc_status otc_station_name(const otc_station_t *st, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_station_country(const otc_station_t *st, char *buf, size_t len, size_t *needed);
OTC_API double otc_station_lat(const otc_station_t *st);
OTC_API double otc_station_lon(const otc_station_t *st);
OTC_API otc_station_type_t otc_station_type(const otc_station_t *st);
OTC_API otc_kind otc_station_kind(const otc_station_t *st);
OTC_API otc_status otc_station_timezone(const otc_station_t *st, char *buf, size_t len, size_t *needed);
OTC_API otc_station_status_t otc_station_status(const otc_station_t *st);
OTC_API bool otc_station_is_reference(const otc_station_t *st);
OTC_API bool otc_station_is_subordinate(const otc_station_t *st);
OTC_API bool otc_station_is_tide(const otc_station_t *st);
OTC_API bool otc_station_is_current(const otc_station_t *st);
/* Aliases: systems in file order; each system's ids (a single string is a one-item list). */
OTC_API size_t otc_station_alias_system_count(const otc_station_t *st);
OTC_API otc_status otc_station_alias_system_at(const otc_station_t *st, size_t i, char *buf, size_t len, size_t *needed);
OTC_API size_t otc_station_alias_count(const otc_station_t *st, const char *system);
OTC_API otc_status otc_station_alias_at(const otc_station_t *st, const char *system, size_t i, char *buf, size_t len,
                                        size_t *needed);
OTC_API otc_status otc_station_raw_json(const otc_station_t *st, char *buf, size_t len, size_t *needed);

/* Sets (spec 4.5): the recommended set first, then the others by set_id.
 * Without include_no_constants, sets with qc_status no_constants (listed, but
 * with no fitted constants) are left out; every other set is always listed. */
OTC_API otc_status otc_station_recommended_set(const otc_station_t *st, const otc_set **out);
OTC_API size_t otc_station_set_count(const otc_station_t *st, bool include_no_constants);
OTC_API otc_status otc_station_set_at(const otc_station_t *st, bool include_no_constants, size_t i,
                                      const otc_set **out);
OTC_API otc_status otc_station_set(const otc_station_t *st, const char *set_id, const otc_set **out);

/* Subordinate offsets (spec 4.7). Missing numbers are NaN; strings are borrowed from the station. */
typedef struct otc_offsets_t {
    size_t                   struct_size; /* set by the caller to sizeof(otc_offsets_t) */
    const char              *reference_station_id;
    double                   time_offset_high_min;
    double                   time_offset_low_min;
    double                   height_offset_high;
    double                   height_offset_low;
    otc_height_adjusted_type height_adjusted_type;
    const char              *licence_id;      /* NULL if absent */
} otc_offsets_t;
OTC_API otc_status otc_station_offsets(const otc_station_t *st, otc_offsets_t *out);

/* Validation rows (spec 4.6). Missing numbers NaN, missing counts -1, missing strings NULL. */
typedef struct otc_previous_release_t {
    double  time_mae_min;
    double  time_p95_min;
    double  time_bias_min;
    double  height_mae_m;
    double  range_error_m;
    int64_t missed_events;
    int64_t extra_events;
} otc_previous_release_t;
typedef struct otc_validation_t {
    size_t                 struct_size;
    const char            *set_id;
    const char            *reference_source;
    const char            *reference_station;
    double                 reference_distance_km;
    const char            *window;
    double                 time_mae_min;
    double                 time_p95_min;
    double                 time_bias_min;
    double                 height_mae_m;
    double                 range_error_m;
    int64_t                missed_events;
    int64_t                extra_events;
    bool                   has_previous_release;
    otc_previous_release_t previous_release;   /* NaN and -1 throughout when has_previous_release is false */
} otc_validation_t;
/* Every row of the station, in file order. */
OTC_API size_t otc_station_validation_count(const otc_station_t *st);
OTC_API otc_status otc_station_validation_at(const otc_station_t *st, size_t i, const otc_validation_t **out);

/* -------------------------------------------------------------- tombstones */

OTC_API otc_status otc_tombstone_station_id(const otc_tombstone_t *t, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_tombstone_name(const otc_tombstone_t *t, char *buf, size_t len, size_t *needed);
OTC_API otc_station_status_t otc_tombstone_status(const otc_tombstone_t *t);
OTC_API otc_status otc_tombstone_removed_in(const otc_tombstone_t *t, char *buf, size_t len, size_t *needed);
OTC_API otc_removed_reason otc_tombstone_removed_reason(const otc_tombstone_t *t);
/* The OTC station id that holds the removed station's records; OTC_E_NOT_FOUND when null. */
OTC_API otc_status otc_tombstone_merged_into(const otc_tombstone_t *t, char *buf, size_t len, size_t *needed);
/* A one-line note; OTC_E_NOT_FOUND when null. */
OTC_API otc_status otc_tombstone_detail(const otc_tombstone_t *t, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_tombstone_raw_json(const otc_tombstone_t *t, char *buf, size_t len, size_t *needed);

/* ---------------------------------------------------------------- sets */

OTC_API otc_status otc_set_set_id(const otc_set *set, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_set_source(const otc_set *set, char *buf, size_t len, size_t *needed);
OTC_API otc_source_type otc_set_source_type(const otc_set *set);
OTC_API otc_quantity otc_set_quantity(const otc_set *set);
OTC_API otc_status otc_set_source_record_id(const otc_set *set, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_set_source_version(const otc_set *set, char *buf, size_t len, size_t *needed);
OTC_API otc_qc_status otc_set_qc_status(const otc_set *set);
OTC_API bool otc_set_is_recommended(const otc_set *set);
OTC_API otc_status otc_set_raw_json(const otc_set *set, char *buf, size_t len, size_t *needed);

OTC_API otc_status otc_set_record_span(const otc_set *set, const otc_record_span **out);
OTC_API otc_status otc_record_span_start(const otc_record_span *rs, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_record_span_end(const otc_record_span *rs, char *buf, size_t len, size_t *needed);
OTC_API int64_t otc_record_span_good_samples(const otc_record_span *rs); /* -1 if missing */

OTC_API otc_status otc_set_datum(const otc_set *set, const otc_datum **out);
OTC_API double otc_datum_msl_offset_m(const otc_datum *d);
OTC_API size_t otc_datum_named_count(const otc_datum *d);
OTC_API otc_status otc_datum_named_at(const otc_datum *d, size_t i, char *name, size_t len, size_t *needed,
                                      double *value);

OTC_API size_t otc_set_qc_flag_count(const otc_set *set);
OTC_API otc_status otc_set_qc_flag_at(const otc_set *set, size_t i, const otc_qc_flag **out);
OTC_API otc_qc_flag_kind otc_qc_flag_flag(const otc_qc_flag *f);
/* The one-line reason the flag was raised. */
OTC_API otc_status otc_qc_flag_reason(const otc_qc_flag *f, char *buf, size_t len, size_t *needed);
/* {name: number or null} as JSON; OTC_E_NOT_FOUND when the flag has no values. */
OTC_API otc_status otc_qc_flag_values_json(const otc_qc_flag *f, char *buf, size_t len, size_t *needed);

OTC_API size_t otc_set_dropped_count(const otc_set *set);
OTC_API otc_status otc_set_dropped_at(const otc_set *set, size_t i, const otc_dropped **out);
OTC_API otc_status otc_dropped_name(const otc_dropped *d, char *buf, size_t len, size_t *needed);
OTC_API otc_dropped_reason otc_dropped_dropped_reason(const otc_dropped *d);
OTC_API otc_status otc_dropped_detail(const otc_dropped *d, char *buf, size_t len, size_t *needed);

/* The set's time-base annotation (TimeBase, spec 4.5); OTC_E_NOT_FOUND when
 * the set has none (every gauge set has one). Borrowed from the station. */
OTC_API otc_status otc_set_time_base(const otc_set *set, const otc_time_base_t **out);
OTC_API otc_time_base_code_t otc_time_base_code(const otc_time_base_t *tb);
OTC_API otc_status otc_time_base_reason(const otc_time_base_t *tb, char *buf, size_t len, size_t *needed);
/* The declared and the published time base (time-base labels). */
OTC_API otc_status otc_time_base_declared(const otc_time_base_t *tb, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_time_base_published(const otc_time_base_t *tb, char *buf, size_t len, size_t *needed);
/* The correction {from, to} (labels), null unless the code is corrected:
 * OTC_E_NOT_FOUND then. _json gives the object as JSON text. */
OTC_API otc_status otc_time_base_correction_from(const otc_time_base_t *tb, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_time_base_correction_to(const otc_time_base_t *tb, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_time_base_correction_json(const otc_time_base_t *tb, char *buf, size_t len, size_t *needed);
/* The months dropped from the record ("YYYY-MM"), in file order; 0 when none. */
OTC_API size_t otc_time_base_months_dropped_count(const otc_time_base_t *tb);
OTC_API otc_status otc_time_base_months_dropped_at(const otc_time_base_t *tb, size_t i, char *buf, size_t len,
                                                   size_t *needed);
/* The datestamp of the build that decided it, and that build's commit (OTC_E_NOT_FOUND when null). */
OTC_API otc_status otc_time_base_decided_in(const otc_time_base_t *tb, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_time_base_decided_build_commit(const otc_time_base_t *tb, char *buf, size_t len,
                                                      size_t *needed);
/* The evidence rows, in file order; 0 when none. distance_km and lag_min are
 * NaN when absent; detail is OTC_E_NOT_FOUND when absent. */
OTC_API size_t otc_time_base_evidence_count(const otc_time_base_t *tb);
OTC_API otc_status otc_time_base_evidence_at(const otc_time_base_t *tb, size_t i, const otc_time_base_evidence **out);
OTC_API otc_status otc_time_base_evidence_comparator_kind(const otc_time_base_evidence *ev, char *buf, size_t len,
                                                          size_t *needed);
OTC_API otc_status otc_time_base_evidence_comparator_id(const otc_time_base_evidence *ev, char *buf, size_t len,
                                                        size_t *needed);
OTC_API double otc_time_base_evidence_distance_km(const otc_time_base_evidence *ev);
OTC_API double otc_time_base_evidence_lag_min(const otc_time_base_evidence *ev);
OTC_API otc_status otc_time_base_evidence_detail(const otc_time_base_evidence *ev, char *buf, size_t len,
                                                 size_t *needed);

/* Linked objects, resolved at open (a reference that does not resolve fails the open). */
OTC_API otc_status otc_set_convention(const otc_set *set, const otc_convention **out);
OTC_API otc_status otc_set_licence(const otc_set *set, const otc_licence **out);

/* Provenance (spec 4.6): one field (a string field as its text, any other
 * value as JSON), or the whole object as JSON (raw, with any further fields).
 * OTC_E_NOT_FOUND when the set has no provenance object (CR D34). */
OTC_API otc_status otc_set_provenance_field(const otc_set *set, const char *field, char *buf, size_t len,
                                            size_t *needed);
OTC_API otc_status otc_set_provenance_json(const otc_set *set, char *buf, size_t len, size_t *needed);
#define otc_set_provenance_raw_json(set, buf, len, needed) otc_set_provenance_json((set), (buf), (len), (needed))
OTC_API otc_status otc_set_provenance_adapter_version(const otc_set *set, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_set_provenance_input_sha256_json(const otc_set *set, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_set_provenance_selection_reason(const otc_set *set, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_set_provenance_decision_json(const otc_set *set, char *buf, size_t len, size_t *needed);
/* The datestamp of the release the set was carried over from; OTC_E_NOT_FOUND
 * when the set is not carried over. */
OTC_API otc_status otc_set_provenance_carried_from_release(const otc_set *set, char *buf, size_t len,
                                                           size_t *needed);
/* provenance.build (ProvenanceBuild). Format 1.0 writes it for every set, so
 * OTC_E_NOT_FOUND only for malformed input (the open does not fail, spec 7.3).
 * Borrowed from the station. Each field is OTC_E_NOT_FOUND when absent;
 * built_at and fetched_at are ISO 8601 UTC strings. */
OTC_API otc_status otc_set_provenance_build(const otc_set *set, const otc_provenance_build **out);
OTC_API otc_status otc_provenance_build_build_commit(const otc_provenance_build *b, char *buf, size_t len,
                                                     size_t *needed);
OTC_API otc_status otc_provenance_build_built_at(const otc_provenance_build *b, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_provenance_build_fetched_at(const otc_provenance_build *b, char *buf, size_t len,
                                                   size_t *needed);
OTC_API otc_status otc_provenance_build_run_id(const otc_provenance_build *b, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_provenance_build_tool_versions_json(const otc_provenance_build *b, char *buf, size_t len,
                                                           size_t *needed);

/* The station's validation rows for this set, ordered by window. */
OTC_API size_t otc_set_validation_count(const otc_set *set);
OTC_API otc_status otc_set_validation_at(const otc_set *set, size_t i, const otc_validation_t **out);

/* Constituents, in file order. The strings are borrowed from the station and
 * stay valid until it is freed; they have no length limit, and "" means absent
 * (spec 4.5, 6.4, CR D13). */
typedef struct otc_constituent_t {
    size_t      struct_size;
    const char *name;
    const char *source_name;
    const char *doodson;
    double      speed_deg_per_hour;    /* NaN if absent */
    double      amplitude_m;
    double      phase_deg;             /* Greenwich (or convention) phase lag, 0 <= g < 360 */
    double      amp_uncertainty_m;     /* NaN if absent */
    double      phase_uncertainty_deg; /* NaN if absent */
    const char *kept_reason;
} otc_constituent_t;
OTC_API size_t otc_set_constituent_count(const otc_set *set);
OTC_API otc_status otc_set_constituent_at(const otc_set *set, size_t i, const otc_constituent_t **out);
/* By OTC canonical name, case-sensitive. */
OTC_API otc_status otc_set_constituent(const otc_set *set, const char *name, const otc_constituent_t **out);
/* The constituent at index i of the set, as the file gives it. */
OTC_API otc_status otc_constituent_raw_json(const otc_set *set, size_t i, char *buf, size_t len, size_t *needed);

/* ------------------------------------------------- the optional otc_fetch module
 * Declared always. In a build without -DOTC_WITH_FETCH=ON every otc_fetch_*
 * function returns OTC_E_NOT_BUILT and opens no socket.
 *
 * The module downloads releases into the cache layout that every SDK on the
 * machine shares (spec 5.4: <root>/v1/pointer, <root>/v1/releases/<D>/), and
 * returns paths to OTC_{D}.jsonl files there. HTTP is libcurl (spec 5.7).
 *
 * Lists of strings out (otc_fetch_cached_releases, otc_fetch_prune,
 * otc_fetch_to_dir): the caller passes an array of char* and its capacity;
 * each element is a NUL-terminated string allocated by the library, which
 * the caller frees with otc_free(). otc_fetch_releases fills an array of
 * otc_release_info*, each freed with otc_release_info_free().
 * otc_fetch_prune and otc_fetch_to_dir change files: they do their work once,
 * fill up to cap entries and set *count to the full number; if cap is too
 * small they return OTC_E_BUFFER_TOO_SMALL after the work is done. */

typedef struct otc_fetch_options {
    size_t               struct_size;   /* set by otc_fetch_options_init() */
    const char          *cache_dir;     /* NULL: OPENTIDECONSTANTS_CACHE_DIR, else the platform default (spec 5.4) */
    const char          *base_url;      /* NULL: OPENTIDECONSTANTS_BASE_URL, else https://data.opentideconstants.org/;
                                           an absolute http(s) URL, else OTC_E_INVALID_ARGUMENT */
    bool                 offline;       /* also OPENTIDECONSTANTS_OFFLINE = 1, true, yes or on (any case,
                                           trimmed); no socket is ever opened */
    double               timeout_s;     /* OTC_TIMEOUT_DEFAULT (set by init): the defaults (connect 10 s, read
                                           60 s); else both, in seconds, more than 0 and at most 1e6; any other
                                           value (0, a negative number, NaN, more): OTC_E_INVALID_ARGUMENT */
    const char          *proxy;         /* NULL: libcurl reads http_proxy (lower case only, for httpoxy),
                                           https_proxy / HTTPS_PROXY, ALL_PROXY and NO_PROXY (spec 5.7) */
    const char          *ca_file;       /* NULL: SSL_CERT_FILE, else libcurl's default; a file that cannot be
                                           read is OTC_E_IO before any network access */
    const char          *user_agent;    /* a suffix, added after one space */
    otc_on_network_error on_network_error; /* latest only: USE_CACHE (default) or RAISE */
    otc_error           *error;
    otc_log_fn           log_fn;
    void                *log_user_data;
    unsigned             formats;       /* data files kept in the cache: OTC_FORMAT_* bits, or OTC_FORMATS_DEFAULT
                                           (set by init) = OTC_FORMAT_JSONL; 0 or an unknown bit:
                                           OTC_E_INVALID_ARGUMENT.
                                           The .jsonl and .meta.json are always kept (the C library opens them);
                                           OTC_FORMAT_JSON also keeps OTC_{D}.json, as eager mode does. */
} otc_fetch_options;
/* The timeout_s value that means "the defaults" (connect 10 s, read 60 s). A
 * negative number is never a valid timeout, so it cannot mean anything else.
 * An explicit 0 is OTC_E_INVALID_ARGUMENT (spec 5.7, CR 4c). */
#define OTC_TIMEOUT_DEFAULT (-1.0)
/* Zeroes opts, sets struct_size, timeout_s = OTC_TIMEOUT_DEFAULT, formats =
 * OTC_FORMATS_DEFAULT and on_network_error = OTC_ON_NETWORK_ERROR_USE_CACHE. */
OTC_API void otc_fetch_options_init(otc_fetch_options *opts);

/* The path of OTC_{D}.jsonl of the latest release in the cache, downloaded and
 * verified first if needed (spec 5.2). latest is the newest release with a
 * supported format major and a readable min_reader_version: when the pointer
 * names a release too new, OTC_index.json (one more GET, only then) gives the
 * newest readable one (OTC_E_READER_TOO_OLD if none). On a network error with
 * on_network_error USE_CACHE it gives the newest readable cached release. */
OTC_API otc_status otc_fetch_latest(const otc_fetch_options *opts, char *path, size_t len, size_t *needed);
/* The same for a pinned datestamp; no network access when it is cached. */
OTC_API otc_status otc_fetch_release(const otc_fetch_options *opts, const char *datestamp, char *path, size_t len,
                                     size_t *needed);
/* otc_fetch_latest / otc_fetch_release (release NULL or "latest": latest),
 * then otc_open_file on the result. The release handle reports loaded_from
 * download, cache or cache_after_error, release files from the cache's
 * .verified record (spec 4.3.1), and, after cache_after_error, the network
 * error through otc_last_error / otc_last_error_status. oopts may be NULL;
 * errors go to fopts->error (and oopts->error). */
OTC_API otc_status otc_fetch_open(const otc_fetch_options *fopts, const char *release, const otc_open_options *oopts,
                                  otc_release **out);
/* Every release in OTC_index.json, newest first. On a network error with
 * on_network_error USE_CACHE it gives the cached index (spec 4.3, 5.2 step 5);
 * offline, the cached index or OTC_E_OFFLINE_UNAVAILABLE. */
OTC_API otc_status otc_fetch_releases(const otc_fetch_options *opts, otc_release_info **out, size_t cap,
                                      size_t *count);
OTC_API otc_status otc_fetch_latest_info(const otc_fetch_options *opts, otc_release_info **info);
/* *found is true and *info is set when the latest readable release (a
 * supported major and a readable min_reader_version, spec 7.4) is newer than
 * current. It also makes a conditional GET of OTC_latest.json, which
 * otc_fetch_newer_format_major reads. That GET is a side probe: when it fails,
 * the call still answers, the failure goes to log_fn at level 2 with its
 * cause, and otc_fetch_newer_format_major keeps the value from before (spec
 * 7.4). Without a log_fn the probe's failure is not reported. */
OTC_API otc_status otc_fetch_check_for_update(const otc_fetch_options *opts, const char *current,
                                              otc_release_info **info, bool *found);
/* The format major of the newest release on the server when it is newer than
 * every major this library reads (spec 7.4): the value the last
 * otc_fetch_check_for_update on this cache found (it reads the cached
 * OTC_latest.json; no network access). OTC_E_NOT_FOUND when there is none;
 * OTC_E_INVALID_RELEASE when the cached OTC_latest.json is corrupt. */
OTC_API otc_status otc_fetch_newer_format_major(const otc_fetch_options *opts, int *major);
/* If a release newer than current exists, downloads it into the cache, sets
 * *updated and writes the path of its .jsonl; the app then opens it and
 * closes the old handle (C has no automatic update, spec 5.6). needed (may be
 * NULL) gets the path length with its NUL, as for every other string out, or
 * 0 when there is no newer release (CR D27). path and len are checked before
 * the download: a buffer too small for the path, or path NULL with len 0 (a
 * size query), is OTC_E_BUFFER_TOO_SMALL (the error message names the size)
 * and downloads nothing. *updated is true only when the new release is in the
 * cache and path names it. */
OTC_API otc_status otc_fetch_update(const otc_fetch_options *opts, const char *current, char *path, size_t len,
                                    size_t *needed, bool *updated);
/* Writes a verified release into dir (spec 4.3.2). release NULL or "latest":
 * the latest; on a network error with on_network_error USE_CACHE, the newest
 * readable cached release. formats: OTC_FORMAT_* bits, or OTC_FORMATS_DEFAULT
 * for OTC_FORMAT_JSONL; 0 (no format) or an unknown bit is OTC_E_INVALID_ARGUMENT.
 * paths gets the full paths written (a file left alone because it was
 * identical is not listed). Every file is checked before any is renamed into
 * dir, so a failure writes nothing there. */
OTC_API otc_status otc_fetch_to_dir(const otc_fetch_options *opts, const char *release, const char *dir,
                                    unsigned formats, bool overwrite, char **paths, size_t cap, size_t *count);
/* Datestamps of the verified cached releases, newest first. */
OTC_API otc_status otc_fetch_cached_releases(const otc_fetch_options *opts, char **datestamps, size_t cap,
                                             size_t *count);
/* Removes the cached releases after the newest keep, never current (the
 * datestamp of the release the app has open; NULL = none). removed gets the
 * datestamps removed, newest first. A release directory that cannot be removed
 * is OTC_E_CACHE; *count and removed then name the releases removed before the
 * failure. A symlink in the cache is removed, never followed. */
OTC_API otc_status otc_fetch_prune(const otc_fetch_options *opts, size_t keep, const char *current, char **removed,
                                   size_t cap, size_t *count);
/* Frees a string that the library allocated (lists of the otc_fetch module). */
OTC_API void otc_free(void *p);
OTC_API void otc_release_info_free(otc_release_info *info);
OTC_API otc_status otc_release_info_datestamp(const otc_release_info *ri, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_release_info_format_version(const otc_release_info *ri, char *buf, size_t len,
                                                   size_t *needed);
/* The concept DOI, the release's own Zenodo version DOI and the digest of its
 * data-bearing content; each OTC_E_NOT_FOUND when null. */
OTC_API otc_status otc_release_info_concept_doi(const otc_release_info *ri, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_release_info_zenodo_version_doi(const otc_release_info *ri, char *buf, size_t len,
                                                       size_t *needed);
OTC_API otc_status otc_release_info_content_sha256(const otc_release_info *ri, char *buf, size_t len,
                                                   size_t *needed);
OTC_API size_t otc_release_info_file_count(const otc_release_info *ri);
OTC_API otc_status otc_release_info_file_at(const otc_release_info *ri, size_t i, const otc_file_info **out);

#ifdef __cplusplus
}
#endif

#endif /* OPENTIDECONSTANTS_H */
