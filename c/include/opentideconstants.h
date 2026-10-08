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
/* The format major this library reads (SUPPORTED_FORMAT_MAJORS = [0]). */
#define OTC_FORMAT_MAJOR 0

#ifndef OTC_API
#define OTC_API
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
    OTC_E_UNSUPPORTED_CONVENTION = 18 /* phase 2 */
} otc_status;

/* The stable error code of a status ("checksum_mismatch", ...); "ok" for OTC_OK. */
OTC_API const char *otc_status_code(otc_status status);

/* Error detail for calls with no release handle (spec 4.8). */
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
    OTC_QC_STATUS_UNSET = 0, OTC_QC_STATUS_ACCEPTED, OTC_QC_STATUS_FALLBACK, OTC_QC_STATUS_EXCLUDED, OTC_QC_STATUS_OTHER
} otc_qc_status;
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
    OTC_QC_FLAG_NON_TIDAL_SIGNAL, OTC_QC_FLAG_SHORT_RECORD, OTC_QC_FLAG_SIBLING_DISAGREEMENT, OTC_QC_FLAG_OTHER
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
    OTC_ALIAS_SYSTEM_OTHER
} otc_alias_system;
typedef enum otc_mode { OTC_MODE_UNSET = 0, OTC_MODE_EAGER, OTC_MODE_STREAM, OTC_MODE_OTHER } otc_mode;
typedef enum otc_on_network_error {
    OTC_ON_NETWORK_ERROR_UNSET = 0, OTC_ON_NETWORK_ERROR_USE_CACHE, OTC_ON_NETWORK_ERROR_RAISE,
    OTC_ON_NETWORK_ERROR_OTHER
} otc_on_network_error;
/* Formats are bit flags for otc_fetch_to_dir; 0 means the default (jsonl). */
typedef enum otc_format {
    OTC_FORMAT_JSON = 1, OTC_FORMAT_JSON_GZ = 2, OTC_FORMAT_JSONL = 4, OTC_FORMAT_OTHER = 8
} otc_format;
typedef enum otc_match { OTC_MATCH_UNSET = 0, OTC_MATCH_EXACT, OTC_MATCH_OTHER } otc_match;

/* The schema string of an enum value ("tide", "water_level", ...); "other"
 * for *_OTHER and NULL for *_UNSET. */
OTC_API const char *otc_kind_name(otc_kind v);
OTC_API const char *otc_station_type_name(otc_station_type_t v);
OTC_API const char *otc_station_status_name(otc_station_status_t v);
OTC_API const char *otc_source_type_name(otc_source_type v);
OTC_API const char *otc_quantity_name(otc_quantity v);
OTC_API const char *otc_qc_status_name(otc_qc_status v);
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
 * (loaded_from file); otherwise loaded_from is file_unverified. opts may be NULL. */
OTC_API otc_status otc_open_file(const char *path, const otc_open_options *opts, otc_release **out);
OTC_API void otc_close(otc_release *rel);

/* The message of the last failure on this handle (spec 4.8). OTC_E_NOT_FOUND if none. */
OTC_API otc_status otc_last_error(const otc_release *rel, char *buf, size_t len, size_t *needed);
/* The status of the last failure on this handle; OTC_OK if none. */
OTC_API otc_status otc_last_error_status(const otc_release *rel);

/* Hashes path again in full and compares it with its row in sha256_path
 * (NULL: the OTC_{D}.sha256 next to path). OTC_E_CHECKSUM on a mismatch, with
 * file, expected_sha256 and actual_sha256 in err. */
OTC_API otc_status otc_verify_file(const char *path, const char *sha256_path, otc_error *err);

/* --------------------------------------------------------- release metadata */

OTC_API otc_loaded_from otc_release_loaded_from(const otc_release *rel);
OTC_API otc_status otc_release_datestamp(const otc_release *rel, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_release_created(const otc_release *rel, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_release_format_version(const otc_release *rel, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_release_doi(const otc_release *rel, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_release_concept_doi(const otc_release *rel, char *buf, size_t len, size_t *needed);
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
OTC_API otc_status otc_release_citation(const otc_release *rel, char *buf, size_t len, size_t *needed);
/* ids = NULL: every licence in the release; else the licences of these stations (spec 4.6). */
OTC_API otc_status otc_attribution(const otc_release *rel, const char *const *ids, size_t n_ids, char *buf, size_t len,
                                   size_t *needed);

/* Stats: counts by type, kind and country (active stations) and by source and
 * qc_status (constant sets); zero counts are left out; keys sorted. */
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
/* As otc_station, but OTC_E_STATION_NOT_FOUND or OTC_E_STATION_REMOVED. */
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
/* limit 0 means no limit. */
OTC_API otc_status otc_search(const otc_release *rel, const char *name, const otc_filter *filter, size_t limit,
                              otc_hit *out, size_t cap, size_t *count);
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
#define otc_station_id otc_station_station_id
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

/* Sets: the recommended set first, then the others by set_id; without
 * include_excluded, sets with qc_status excluded are left out. */
OTC_API otc_status otc_station_recommended_set(const otc_station_t *st, const otc_set **out);
OTC_API size_t otc_station_set_count(const otc_station_t *st, bool include_excluded);
OTC_API otc_status otc_station_set_at(const otc_station_t *st, bool include_excluded, size_t i, const otc_set **out);
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
    otc_previous_release_t previous_release;
} otc_validation_t;
/* Every row of the station, in file order. */
OTC_API size_t otc_station_validation_count(const otc_station_t *st);
OTC_API otc_status otc_station_validation_at(const otc_station_t *st, size_t i, const otc_validation_t **out);

/* -------------------------------------------------------------- tombstones */

OTC_API otc_status otc_tombstone_station_id(const otc_tombstone_t *t, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_tombstone_name(const otc_tombstone_t *t, char *buf, size_t len, size_t *needed);
OTC_API otc_station_status_t otc_tombstone_status(const otc_tombstone_t *t);
OTC_API otc_status otc_tombstone_removed_in(const otc_tombstone_t *t, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_tombstone_removed_reason(const otc_tombstone_t *t, char *buf, size_t len, size_t *needed);
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
OTC_API otc_status otc_qc_flag_verdict(const otc_qc_flag *f, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_qc_flag_values_json(const otc_qc_flag *f, char *buf, size_t len, size_t *needed);

OTC_API size_t otc_set_dropped_count(const otc_set *set);
OTC_API otc_status otc_set_dropped_at(const otc_set *set, size_t i, const otc_dropped **out);
OTC_API otc_status otc_dropped_name(const otc_dropped *d, char *buf, size_t len, size_t *needed);
OTC_API otc_dropped_reason otc_dropped_dropped_reason(const otc_dropped *d);
OTC_API otc_status otc_dropped_detail(const otc_dropped *d, char *buf, size_t len, size_t *needed);

/* Linked objects, resolved at open (a reference that does not resolve fails the open). */
OTC_API otc_status otc_set_convention(const otc_set *set, const otc_convention **out);
OTC_API otc_status otc_set_licence(const otc_set *set, const otc_licence **out);

/* Provenance: one field (a string field as its text, any other value as JSON), or the whole object as JSON. */
OTC_API otc_status otc_set_provenance_field(const otc_set *set, const char *field, char *buf, size_t len,
                                            size_t *needed);
OTC_API otc_status otc_set_provenance_json(const otc_set *set, char *buf, size_t len, size_t *needed);
#define otc_set_provenance_raw_json otc_set_provenance_json
OTC_API otc_status otc_set_provenance_build_commit(const otc_set *set, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_set_provenance_adapter_version(const otc_set *set, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_set_provenance_input_sha256_json(const otc_set *set, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_set_provenance_time_base_json(const otc_set *set, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_set_provenance_selection_reason(const otc_set *set, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_set_provenance_decision_json(const otc_set *set, char *buf, size_t len, size_t *needed);

/* The station's validation rows for this set, ordered by window. */
OTC_API size_t otc_set_validation_count(const otc_set *set);
OTC_API otc_status otc_set_validation_at(const otc_set *set, size_t i, const otc_validation_t **out);

/* Constituents, in file order. Strings in fixed arrays: "" means absent. */
typedef struct otc_constituent_t {
    size_t struct_size;
    char   name[16];
    char   source_name[32];
    char   doodson[8];
    double speed_deg_per_hour;    /* NaN if absent */
    double amplitude_m;
    double phase_deg;             /* Greenwich (or convention) phase lag, 0 <= g < 360 */
    double amp_uncertainty_m;     /* NaN if absent */
    double phase_uncertainty_deg; /* NaN if absent */
    char   kept_reason[32];
} otc_constituent_t;
OTC_API size_t otc_set_constituent_count(const otc_set *set);
OTC_API otc_status otc_set_constituent_at(const otc_set *set, size_t i, const otc_constituent_t **out);
/* By OTC canonical name, case-sensitive. */
OTC_API otc_status otc_set_constituent(const otc_set *set, const char *name, const otc_constituent_t **out);
/* The constituent at index i of the set, as the file gives it. */
OTC_API otc_status otc_constituent_raw_json(const otc_set *set, size_t i, char *buf, size_t len, size_t *needed);

/* ------------------------------------------------- the optional otc_fetch module
 * Declared always. In a build without -DOTC_WITH_FETCH=ON every otc_fetch_*
 * function returns OTC_E_NOT_BUILT and opens no socket. */

typedef struct otc_fetch_options {
    size_t               struct_size;   /* set by otc_fetch_options_init() */
    const char          *cache_dir;     /* NULL: the platform default (spec 5.4) */
    const char          *base_url;      /* NULL: https://data.opentideconstants.org/ */
    bool                 offline;
    double               timeout_s;     /* 0: the defaults (connect 10 s, read 60 s) */
    const char          *proxy;
    const char          *ca_file;
    const char          *user_agent;    /* a suffix */
    otc_on_network_error on_network_error;
    otc_error           *error;
    otc_log_fn           log_fn;
    void                *log_user_data;
} otc_fetch_options;
OTC_API void otc_fetch_options_init(otc_fetch_options *opts);

OTC_API otc_status otc_fetch_latest(const otc_fetch_options *opts, char *path, size_t len, size_t *needed);
OTC_API otc_status otc_fetch_release(const otc_fetch_options *opts, const char *datestamp, char *path, size_t len,
                                     size_t *needed);
OTC_API otc_status otc_fetch_releases(const otc_fetch_options *opts, otc_release_info **out, size_t cap,
                                      size_t *count);
OTC_API otc_status otc_fetch_latest_info(const otc_fetch_options *opts, otc_release_info **info);
OTC_API otc_status otc_fetch_check_for_update(const otc_fetch_options *opts, const char *current,
                                              otc_release_info **info, bool *found);
OTC_API otc_status otc_fetch_update(const otc_fetch_options *opts, const char *current, char *path, size_t len,
                                    bool *updated);
OTC_API otc_status otc_fetch_to_dir(const otc_fetch_options *opts, const char *release, const char *dir,
                                    unsigned formats, bool overwrite, char **paths, size_t cap, size_t *count);
OTC_API otc_status otc_fetch_cached_releases(const otc_fetch_options *opts, char **datestamps, size_t cap,
                                             size_t *count);
OTC_API otc_status otc_fetch_prune(const otc_fetch_options *opts, size_t keep, char **removed, size_t cap,
                                   size_t *count);
OTC_API void otc_release_info_free(otc_release_info *info);
OTC_API otc_status otc_release_info_datestamp(const otc_release_info *ri, char *buf, size_t len, size_t *needed);
OTC_API otc_status otc_release_info_format_version(const otc_release_info *ri, char *buf, size_t len,
                                                   size_t *needed);
OTC_API otc_status otc_release_info_doi(const otc_release_info *ri, char *buf, size_t len, size_t *needed);
OTC_API size_t otc_release_info_file_count(const otc_release_info *ri);
OTC_API otc_status otc_release_info_file_at(const otc_release_info *ri, size_t i, const otc_file_info **out);

#ifdef __cplusplus
}
#endif

#endif /* OPENTIDECONSTANTS_H */
