/* Internal declarations of the OpenTideConstants C library. Not installed. */
#ifndef OTC_INTERNAL_H
#define OTC_INTERNAL_H

#if !defined(_WIN32) && !defined(_POSIX_C_SOURCE)
#define _POSIX_C_SOURCE 200809L
#endif
/* 64-bit off_t on 32-bit Linux, so pread reaches past 2 GiB of a .jsonl */
#if !defined(_WIN32) && !defined(_FILE_OFFSET_BITS)
#define _FILE_OFFSET_BITS 64
#endif
#if defined(_MSC_VER) && !defined(_CRT_SECURE_NO_WARNINGS)
#define _CRT_SECURE_NO_WARNINGS
#endif
#ifndef CJSON_HIDE_SYMBOLS
#define CJSON_HIDE_SYMBOLS
#endif

#include "opentideconstants.h"
#include "otc_cjson_rename.h"
#include "cJSON.h"

#include <math.h>
#include <stddef.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifdef _WIN32
#include <windows.h>
#else
#include <pthread.h>
#endif

/* ------------------------------------------------------------- fold table */

typedef struct otc_fold_entry {
    uint32_t    cp;
    const char *folded;
} otc_fold_entry;
extern const otc_fold_entry otc__fold_table[];
extern const size_t otc__fold_table_size;

/* Folds and normalises a name (spec 4.4.1). Returns a malloc'd string or NULL (no memory). */
char *otc__fold(const char *s);
/* The same for n bytes that may hold a NUL; *out_len (may be NULL) gets the length. */
char *otc__fold_n(const char *s, size_t n, size_t *out_len);

/* JSON strings with a NUL inside (spec 6.4, CR2 DR33). cJSON decodes \u0000 to a
 * NUL byte but keeps no length, so its strings seem to end at the first NUL.
 * otc__json_parse records the full length of every such string in the node's
 * valuedouble (cJSON does not use it for strings; cJSON_Duplicate copies it),
 * and every string the library reads, compares or copies out goes through the
 * helpers below. */
/* 1 when the JSON text has a \u0000 escape. */
int otc__json_has_nul(const char *text, size_t len);
/* n bytes as a JSON string literal (quotes included; control characters as \u00XX). */
char *otc__json_escape_n(const char *s, size_t n);
/* The full length of a string node (NULs inside included). */
size_t otc__jstr_len(const cJSON *s);
/* The string member key as a node, or NULL when absent or not a string. */
const cJSON *otc__jstr_item(const cJSON *obj, const char *key);
/* 1 when the string node s is the C string str in full (a NUL inside s never matches). */
int otc__jstr_is(const cJSON *s, const char *str);
/* 1 when both are string nodes with the same bytes. */
int otc__jstr_same(const cJSON *a, const cJSON *b);
/* A deep copy of v whose strings keep their full length (cJSON_Duplicate cuts
 * them at a NUL, so the library never calls it directly). NULL: no memory. */
cJSON *otc__json_dup(const cJSON *v);
/* A new node for the string node s, for a document that is only printed: a raw
 * JSON literal when s holds a NUL, else a plain string. NULL: no memory. */
cJSON *otc__json_str_out(const cJSON *s);

/* ---------------------------------------------------------------- platform */

typedef struct otc__file otc__file;
/* OTC_E_IO if the file cannot be opened. */
otc_status otc__file_open(const char *path, otc__file **out);
/* Reads exactly n bytes at off; 0 on success. Safe to call from several threads. */
int otc__file_pread(otc__file *f, void *buf, size_t n, uint64_t off);
int64_t otc__file_size(otc__file *f);
void otc__file_close(otc__file *f);
/* 1 when the n bytes at s are a datestamp: ^[0-9]{8}(\.[2-9]|\.[1-9][0-9]{1,8})?$
 * (spec 4.2; the counter has at most 9 digits, CR D18). */
int otc__valid_datestamp(const char *s, size_t n);
/* An HTTP-date (IMF-fixdate, RFC 9110 5.6.7) as seconds since 1970, or -1. */
int64_t otc__http_date(const char *s);
/* An RFC 3339 time as UTC "YYYY-MM-DDTHH:MM:SSZ" (whole seconds); 0 when s is not one. */
int otc__utc_time(const char *s, char out[21]);
/* The size of a file, or -1 if it does not exist or is not a regular file. */
int64_t otc__path_size(const char *path);
/* Removes a file; 0 on success. */
int otc__remove_file(const char *path);
/* Reads a whole (small) file into a NUL-terminated malloc'd buffer. */
otc_status otc__read_all(const char *path, char **out, size_t *len);

typedef struct otc__mutex {
#ifdef _WIN32
    CRITICAL_SECTION cs;
#else
    pthread_mutex_t m;
#endif
} otc__mutex;
void otc__mutex_init(otc__mutex *m);
void otc__mutex_lock(otc__mutex *m);
void otc__mutex_unlock(otc__mutex *m);
void otc__mutex_destroy(otc__mutex *m);

/* cJSON_Parse* writes a process-wide error slot on every call (cJSON.c,
 * global_error), so concurrent parses race. Every parse in the library goes
 * through this wrapper, which holds one process-wide lock while it parses.
 * text[len] must be '\0'. The whole text must be one JSON value (whitespace
 * around it is fine): anything after the value fails the parse. */
cJSON *otc__json_parse(const char *text, size_t len);
/* otc__json_parse, and why it failed: OTC_OK (*out set), OTC_E_NOMEM (cJSON
 * could not allocate: a real malloc sets errno to ENOMEM) or
 * OTC_E_INVALID_RELEASE (the text is not JSON). *out is NULL on failure. */
otc_status otc__json_parse_st(const char *text, size_t len, cJSON **out);

/* ----------------------------------------------------------------- helpers */

char *otc__strdup(const char *s);
char *otc__strndup(const char *s, size_t n);
otc_status otc__copy_str(const char *src, char *buf, size_t len, size_t *needed);
/* The same for n bytes that may hold a NUL (needed is n + 1). */
otc_status otc__copy_strn(const char *src, size_t n, char *buf, size_t len, size_t *needed);
/* The same for a string node in full (NULL or not a string: OTC_E_NOT_FOUND). */
otc_status otc__copy_jstr(const cJSON *s, char *buf, size_t len, size_t *needed);
/* The string member key of obj, in full. */
otc_status otc__copy_member(const cJSON *obj, const char *key, char *buf, size_t len, size_t *needed);
/* The JSON text of a value, strings with a NUL in full (NULL value: OTC_E_NOT_FOUND). */
otc_status otc__copy_json(const cJSON *v, char *buf, size_t len, size_t *needed);
/* A string member, or NULL when absent or not a string. */
const char *otc__jstr(const cJSON *obj, const char *key);
/* A number member, or NaN. */
double otc__jnum(const cJSON *obj, const char *key);
/* A whole, non-negative number member, or -1 (missing, not a number, or with a fraction). */
int64_t otc__jint(const cJSON *obj, const char *key);
const cJSON *otc__jget(const cJSON *obj, const char *key);
/* An otc_error the library may write: err when its struct_size is the size the
 * library knows, else NULL (spec 6.4: a smaller struct is never written past). */
otc_error *otc__err_usable(otc_error *err);
/* Clears a usable err (otc_error_init for the library's own use); else nothing. */
void otc__err_reset(otc_error *err);
/* Records an error in a usable err; else nothing. */
void otc__err_set(otc_error *err, otc_status st, const char *file, const char *fmt, ...);
int otc__strcmp_null(const char *a, const char *b);
/* Orders two byte strings that may hold a NUL: by their bytes, then the shorter first. */
int otc__bytes_cmp(const char *a, size_t an, const char *b, size_t bn);
int otc__ends_with(const char *s, const char *suffix);
char *otc__join(const char *a, const char *b);

/* SHA-256 of a whole file as 64 lower-case hex digits. */
otc_status otc__sha256_file(const char *path, char hex[65]);
/* The same for an open file (the bytes that will be read), and for bytes in memory. */
otc_status otc__sha256_handle(otc__file *f, char hex[65]);
void otc__sha256_mem(const void *data, size_t len, char hex[65]);
/* The digest of name in a sha256sum file (malloc'd hex), or NULL. *found_file is 0 if the file does not exist. */
otc_status otc__sha256_rows(const char *sha_path, char ***names, char ***digests, size_t *n);
/* The same for the text of a sha256sum file. Not UTF-8, or a name listed twice: OTC_E_INVALID_RELEASE (CR2 DR14).
 * A line that is neither blank (ASCII white space only) nor a row is OTC_E_INVALID_RELEASE too (CR2 DR41). */
otc_status otc__sha256_rows_text(const char *text, char ***names, char ***digests, size_t *n);
/* 1 if a fetched .sha256 body has at least one "<sha256>  <name>" row: a 200 with none is the network (CR2 DR13) */
int otc__sha256_has_row(const char *text);
/* The start of an error message for a status of the two functions above: "cannot read" or what is wrong. */
const char *otc__sha256_rows_what(otc_status st);
void otc__free_rows(char **names, char **digests, size_t n);

/* enum parsing: unknown -> OTHER, NULL -> UNSET */
otc_kind otc__parse_kind(const char *s);
otc_station_type_t otc__parse_station_type(const char *s);
otc_station_status_t otc__parse_station_status(const char *s);
otc_source_type otc__parse_source_type(const char *s);
otc_quantity otc__parse_quantity(const char *s);
otc_qc_status otc__parse_qc_status(const char *s);
otc_removed_reason otc__parse_removed_reason(const char *s);
otc_time_base_code_t otc__parse_time_base_code(const char *s);
/* 1 when v is MAJOR.MINOR: two non-negative integers (at most 9 digits) with no
 * leading zeros, joined by one dot (spec 7.4, CR D9). */
int otc__version_valid(const char *v);
/* Compares two "MAJOR.MINOR" format versions numerically (-1, 0, 1); an
 * unparsable version sorts as 0.0. */
int otc__version_cmp(const char *a, const char *b);
/* 1 when this library reads a release of format_version fv whose
 * release.min_reader_version is mrv (either may be NULL; a malformed one is
 * never readable). */
int otc__readable(const char *fv, const char *mrv);
otc_phase_reference otc__parse_phase_reference(const char *s);
otc_nodal_handling otc__parse_nodal_handling(const char *s);
otc_height_adjusted_type otc__parse_height_adjusted_type(const char *s);
otc_dropped_reason otc__parse_dropped_reason(const char *s);
otc_qc_flag_kind otc__parse_qc_flag(const char *s);

otc_fallback_reason_t otc__parse_fallback_reason(const char *s);
otc_source_role otc__parse_source_role(const char *s);
otc_source_disposition otc__parse_source_disposition(const char *s);
/* ----------------------------------------------------------------- release */

struct otc_convention {
    cJSON      *json;    /* owned by the release's meta document */
    const char *id;
};

struct otc_licence {
    cJSON      *json;
    const char *id;
    bool        commercial_use;   /* the licence's commercial_use (spec 4.6, K-NC DR104) */
};

/* The size of otc_open_options before K-NC added commercial_only: the smallest
 * struct_size the library takes (spec 6.4, K-NC DR106). */
#define OTC__OPEN_OPTIONS_MIN offsetof(otc_open_options, commercial_only)
otc_status otc__open_policy_options(const otc_open_options *opts, otc_error *err);
/* opts->commercial_only when struct_size covers it, else false. */
#define OTC__COMMERCIAL_ONLY(opts)                                                                          \
    ((opts) && (opts)->struct_size >= offsetof(otc_open_options, commercial_only) + sizeof(bool)            \
     && (opts)->commercial_only)

struct otc_file_info {
    char   *name;
    char   *url;
    int64_t size;
    char   *sha256;
};

struct otc_release_info {
    char          *datestamp;
    char          *format_version;
    char          *min_reader_version; /* gates latest (spec 7.4); not an accessor */
    char          *concept_doi;
    char          *zenodo_version_doi;
    char          *content_sha256;
    otc_file_info *files;
    size_t         n_files;
};

typedef struct otc__kv {
    char   *key;
    int64_t n;
} otc__kv;

typedef struct otc__kvlist {
    otc__kv *items;
    size_t   n, cap;
} otc__kvlist;
otc_status otc__kv_add(otc__kvlist *l, const char *key, int64_t n);
void otc__kv_sort(otc__kvlist *l);
void otc__kv_free(otc__kvlist *l);

/* One active station in the stream index (spec 6.2). */
typedef struct otc__entry {
    char              *id;
    char              *name;
    char              *folded;
    size_t             name_len;        /* a schema-valid name may hold a NUL (spec 4.4.1) */
    size_t             folded_len;
    char              *country;
    char              *type_s;          /* the type as the file gives it */
    otc_station_type_t type;
    double             lat, lon;
    otc_kind           kind;            /* resolved after the pass */
    otc_quantity       rec_quantity;
    char              *rec_source_type; /* of the recommended set, or NULL */
    char              *rec_licence;     /* of the recommended set, or NULL */
    int                has_rec;
    int                has_offsets;
    char              *ref_id;          /* subordinate_offsets.reference_station_id */
    char              *off_licence;     /* subordinate_offsets.licence_id */
    /* commercial_only (spec 4.2, K-NC DR106): the effective recommended set, by
     * its position in the line's constant_sets (-1: none), with its source_type
     * and licence; and the licence of the first set in file order from the
     * offsets' source (noaa), water_level, ok or flagged (the reference set of
     * the one-link offsets path), or NULL. Set only when the release has the
     * option. */
    long               eff_pos;
    char              *eff_source_type;
    char              *eff_licence;
    char              *offsets_ref_licence;
    char             **sources;         /* sources of sets with constants (qc_status ok or flagged) */
    size_t             n_sources;
    cJSON             *sets_json; /* owned compact discovery metadata */
    cJSON             *own_offsets;
    cJSON             *current_offsets;
    uint64_t           offset;
    size_t             length;
    uint64_t           view;            /* index_used: the hash of the entry's status, references and sets */
} otc__entry;

typedef struct otc__tomb {
    char    *id;
    uint64_t offset;
    size_t   length;
    uint64_t view;    /* as in otc__entry */
} otc__tomb;

typedef struct otc__alias {
    char  *system;
    char  *alias;
    size_t alias_len; /* an alias id may hold a NUL (CR2 DR33) */
    char  *station;   /* the station_id that owns it */
} otc__alias;

struct otc_release {
    otc__file      *file;
    char           *path;
    cJSON          *meta;
    const cJSON    *release_obj;
    otc_convention *conv;
    size_t          n_conv;
    otc_licence    *lic;
    size_t          n_lic;
    otc__entry     *st;
    size_t          n_st;
    otc__tomb      *tomb;
    size_t          n_tomb;
    otc__alias     *alias;
    size_t          n_alias;
    char          **cnames;
    size_t          n_cnames;
    otc_file_info  *files;
    size_t          n_files;
    char           *zenodo_version_doi; /* set by otc_fetch_open from .verified (spec 4.3) */
    char            created[21];        /* release.created in UTC (spec 4.3); "" when absent or not a time */
    otc_loaded_from loaded_from;
    int             index_used;   /* 1: the stations came from a fresh index-v1.json (spec 6.2) */
    bool            commercial_only;   /* the open option (spec 4.2, K-NC DR106) */
    bool            commercial_upstream;
    bool            historical_excluded;
    otc__kvlist     source_counts;
    otc__kvlist     qc_counts;
    /* the only mutable state after open: the last failure on this handle */
    otc__mutex      lock;
    otc_status      last_status;
    char            last_message[512];
};

/* Records a failure on the handle (not NOT_FOUND / BUFFER_TOO_SMALL) and returns st. */
otc_status otc__fail(const otc_release *rel, otc_status st, const char *fmt, ...);
const otc__entry *otc__find_entry(const otc_release *rel, const char *id);
const otc__tomb *otc__find_tomb(const otc_release *rel, const char *id);
const otc_convention *otc__find_convention(const otc_release *rel, const char *id);
const otc_licence *otc__find_licence(const otc_release *rel, const char *id);
/* The index-v1.json document (spec 6.2) of an open release: one more pass
 * over the .jsonl. NULL when out of memory or the file cannot be read. */
cJSON *otc__index_doc(const otc_release *rel, const char *jsonl_sha256, const char *by);
/* Reads and parses one line of the .jsonl file. */
otc_status otc__read_line(const otc_release *rel, uint64_t offset, size_t length, cJSON **out);
/* Reads the line of station id: invalid_release when the line is another
 * station's (a stale index, spec 6.2 / CR D4; the index file is then deleted).
 * When the stations came from the index, the line must also pass the checks of
 * the full pass and give the status, references and sets whose hash is view
 * (PK-R2-07). */
otc_status otc__read_station_line(const otc_release *rel, const char *id, uint64_t offset, size_t length,
                                  uint64_t view, cJSON **out);
int otc__historical_valid(const cJSON *offsets);
int otc__filter_match(const otc_release *rel, const otc_filter *f, const otc__entry *e);

/* ---------------------------------------------------------------- stations */

struct otc_fallback { const cJSON *json; };
struct otc_source_record { const cJSON *json; const otc_release *rel; };
struct otc_historical_offset_vintage { const cJSON *json; };
struct otc_historical_offset_provenance { const cJSON *json; };
struct otc_qc_flag { const cJSON *json; };
struct otc_time_base_evidence { const cJSON *json; };
struct otc_time_base {
    const cJSON            *json;
    otc_time_base_evidence *ev;
    size_t                  n_ev;
};
struct otc_provenance_build { const cJSON *json; };
struct otc_dropped { const cJSON *json; };
struct otc_record_span { const cJSON *json; };
struct otc_datum { const cJSON *json; };

struct otc_set {
    const cJSON            *json;
    const otc_station_t    *station;
    const otc_convention   *conv;
    const otc_licence      *lic;
    otc_constituent_t      *cons;
    size_t                  n_cons;
    const otc_validation_t **val;
    size_t                  n_val;
    otc_qc_flag            *flags;
    size_t                  n_flags;
    otc_dropped            *drops;
    size_t                  n_drops;
    otc_record_span         span;
    int                     has_span;
    otc_datum               datum;
    int                     has_datum;
    otc_time_base_t         tb;
    int                     has_tb;
    otc_provenance_build    build;
    int                     has_build;
    otc_fallback            fallback;
    bool                    recommended;
    bool                    no_constants;
};

struct otc_station {
    otc_source_record *source_records;
    size_t n_source_records;
    otc_qc_flag *offset_flags;
    size_t n_offset_flags;
    otc_fallback offset_fallback;
    otc_historical_offset_vintage offset_vintage;
    otc_historical_offset_provenance offset_provenance;
    cJSON            *root;
    const otc_release *rel;
    otc_kind          kind;
    otc_set          *sets;
    size_t            n_sets;
    otc_set         **order_all;     /* recommended first, then by set_id */
    size_t            n_all;
    otc_set         **order_usable;  /* the same without no_constants sets */
    size_t            n_usable;
    otc_set          *rec;
    otc_validation_t *val;
    size_t            n_val;
};

struct otc_tombstone {
    cJSON *root;
};

/* Builds a station from its parsed line (takes ownership of root). eff_pos:
 * OTC__REC_FROM_LINE for the line's recommended_set_id, else the position in
 * constant_sets of the set the station gives as recommended (-1: none; the
 * effective recommended set of commercial_only, K-NC DR106). */
#define OTC__REC_FROM_LINE (-2L)
otc_status otc__station_build(const otc_release *rel, cJSON *root, otc_kind kind, long eff_pos, otc_station_t **out);

#endif /* OTC_INTERNAL_H */
