/* Internal declarations of the OpenTideConstants C library. Not installed. */
#ifndef OTC_INTERNAL_H
#define OTC_INTERNAL_H

#if !defined(_WIN32) && !defined(_POSIX_C_SOURCE)
#define _POSIX_C_SOURCE 200809L
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

/* ---------------------------------------------------------------- platform */

typedef struct otc__file otc__file;
/* OTC_E_IO if the file cannot be opened. */
otc_status otc__file_open(const char *path, otc__file **out);
/* Reads exactly n bytes at off; 0 on success. Safe to call from several threads. */
int otc__file_pread(otc__file *f, void *buf, size_t n, uint64_t off);
int64_t otc__file_size(otc__file *f);
void otc__file_close(otc__file *f);
/* The size of a file, or -1 if it does not exist or is not a regular file. */
int64_t otc__path_size(const char *path);
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
 * through this wrapper, which holds one process-wide lock while it parses. */
cJSON *otc__json_parse(const char *text, size_t len);

/* ----------------------------------------------------------------- helpers */

char *otc__strdup(const char *s);
char *otc__strndup(const char *s, size_t n);
otc_status otc__copy_str(const char *src, char *buf, size_t len, size_t *needed);
/* The JSON text of a value (NULL value: OTC_E_NOT_FOUND). */
otc_status otc__copy_json(const cJSON *v, char *buf, size_t len, size_t *needed);
/* A string member, or NULL when absent or not a string. */
const char *otc__jstr(const cJSON *obj, const char *key);
/* A number member, or NaN. */
double otc__jnum(const cJSON *obj, const char *key);
/* An integer member, or -1. */
int64_t otc__jint(const cJSON *obj, const char *key);
const cJSON *otc__jget(const cJSON *obj, const char *key);
void otc__err_set(otc_error *err, otc_status st, const char *file, const char *fmt, ...);
int otc__strcmp_null(const char *a, const char *b);
int otc__ends_with(const char *s, const char *suffix);
char *otc__join(const char *a, const char *b);

/* SHA-256 of a whole file as 64 lower-case hex digits. */
otc_status otc__sha256_file(const char *path, char hex[65]);
/* The digest of name in a sha256sum file (malloc'd hex), or NULL. *found_file is 0 if the file does not exist. */
otc_status otc__sha256_rows(const char *sha_path, char ***names, char ***digests, size_t *n);
/* The same for the text of a sha256sum file. */
otc_status otc__sha256_rows_text(const char *text, char ***names, char ***digests, size_t *n);
void otc__free_rows(char **names, char **digests, size_t n);

/* enum parsing: unknown -> OTHER, NULL -> UNSET */
otc_kind otc__parse_kind(const char *s);
otc_station_type_t otc__parse_station_type(const char *s);
otc_station_status_t otc__parse_station_status(const char *s);
otc_source_type otc__parse_source_type(const char *s);
otc_quantity otc__parse_quantity(const char *s);
otc_qc_status otc__parse_qc_status(const char *s);
otc_phase_reference otc__parse_phase_reference(const char *s);
otc_nodal_handling otc__parse_nodal_handling(const char *s);
otc_height_adjusted_type otc__parse_height_adjusted_type(const char *s);
otc_dropped_reason otc__parse_dropped_reason(const char *s);
otc_qc_flag_kind otc__parse_qc_flag(const char *s);

/* ----------------------------------------------------------------- release */

struct otc_convention {
    cJSON      *json;    /* owned by the release's meta document */
    const char *id;
};

struct otc_licence {
    cJSON      *json;
    const char *id;
};

struct otc_file_info {
    char   *name;
    char   *url;
    int64_t size;
    char   *sha256;
};

struct otc_release_info {
    char          *datestamp;
    char          *format_version;
    char          *doi;
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
    char             **sources;         /* sources of usable (not excluded) sets */
    size_t             n_sources;
    uint64_t           offset;
    size_t             length;
} otc__entry;

typedef struct otc__tomb {
    char    *id;
    uint64_t offset;
    size_t   length;
} otc__tomb;

typedef struct otc__alias {
    char  *system;
    char  *alias;
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
    otc_loaded_from loaded_from;
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
/* Reads and parses one line of the .jsonl file. */
otc_status otc__read_line(const otc_release *rel, uint64_t offset, size_t length, cJSON **out);
int otc__filter_match(const otc_filter *f, const otc__entry *e);

/* ---------------------------------------------------------------- stations */

struct otc_qc_flag { const cJSON *json; };
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
    bool                    recommended;
    bool                    excluded;
};

struct otc_station {
    cJSON            *root;
    const otc_release *rel;
    otc_kind          kind;
    otc_set          *sets;
    size_t            n_sets;
    otc_set         **order_all;     /* recommended first, then by set_id */
    size_t            n_all;
    otc_set         **order_usable;  /* the same without excluded sets */
    size_t            n_usable;
    otc_set          *rec;
    otc_validation_t *val;
    size_t            n_val;
};

struct otc_tombstone {
    cJSON *root;
};

/* Builds a station from its parsed line (takes ownership of root). */
otc_status otc__station_build(const otc_release *rel, cJSON *root, otc_kind kind, otc_station_t **out);

#endif /* OTC_INTERNAL_H */
