/*
 * The C conformance runner (conformance/README.md, "The runner protocol").
 *
 * It calls only the public API in opentideconstants.h. It uses its own copy of
 * cJSON for the protocol (the library renames its internal copy, so the two do
 * not clash).
 *
 * Multi-thread mode (SDK spec 6.4: "The conformance runner runs a C case in
 * several threads"): with OTC_RUNNER_THREADS=N (N > 1) every query op runs in
 * N threads at once on the same release handle, and the runner checks that
 * all N replies are byte-identical before it sends one of them. A difference
 * is reported as the error "uncaught:ThreadMismatch", which fails the case.
 */
#if !defined(_WIN32) && !defined(_POSIX_C_SOURCE)
#define _POSIX_C_SOURCE 200809L
#endif
#ifdef _MSC_VER
#define _CRT_SECURE_NO_WARNINGS
#endif

#include "opentideconstants.h"
#include "cJSON.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#ifdef _WIN32
#include <windows.h>
#else
#include <pthread.h>
#endif

#ifndef OTC_RUNNER_FETCH
#define OTC_RUNNER_FETCH 0
#endif

/* ------------------------------------------------------------ test faults */

/*
 * OTC_RUNNER_FAULT (self-tests only, conformance/tests/test_group_h.py): a comma-separated list of faults the
 * runner plants in its own code, to show that a library failure it cannot otherwise provoke still fails the step.
 * Unset in every conformance run.
 */
static const char *g_fault;

static int fault(const char *name)
{
    const char *p = g_fault;
    size_t n = strlen(name);
    while (p && *p) {
        if (!strncmp(p, name, n) && (p[n] == ',' || p[n] == '\0')) return 1;
        p = strchr(p, ',');
        if (p) p++;
    }
    return 0;
}

/* ------------------------------------------------------------------ state */

#define MAX_HELD 16
static otc_release *g_current;
static char *g_current_path;
static struct { char *name; otc_release *rel; char *path; } g_held[MAX_HELD];
static size_t g_n_held;

/*
 * The client options of the last open (C has no client object, so the
 * runner keeps them, as an app would, and passes them to every otc_fetch_*
 * call). pinned: opened on a datestamp or a file, so update is
 * pinned_release (spec 4.3). auto_update: C has no automatic update (spec
 * 5.6); the runner, as the app, calls otc_fetch_update at most once per
 * update_interval, before the first query after the interval.
 */
static struct {
    char    *cache_dir, *base_url, *proxy, *ca_file, *user_agent;
    bool     offline;
    bool     require_checksum;           /* otc_open_options.require_checksum, for every open (CR2 DR34) */
    char    *commercial_basis, *historical_offsets_policy;
    bool     commercial_only;            /* otc_open_options.commercial_only, for every open (K-NC DR106) */
    double   timeout_s;
    otc_on_network_error on_network_error;
    unsigned formats;
    int      pinned;
    int      auto_update;
    double   update_interval;
    double   last_check;
    otc_status auto_update_status;   /* the failure of the last automatic update (C69), OTC_OK if none */
    int      auto_update_nomove;     /* it said "updated" but named no newer release: last_error is uncaught */
    int      pointer_reached;        /* a check reached the latest pointer since the open: last_error is null (CR2 DR4) */
} g_client = {.timeout_s = OTC_TIMEOUT_DEFAULT, .formats = OTC_FORMATS_DEFAULT};   /* no client yet: the defaults */

static double now_s(void)
{
#ifdef _WIN32
    return (double)GetTickCount64() / 1000.0;
#else
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec / 1e9;
#endif
}

static void client_free(void)
{
    free(g_client.commercial_basis);
    free(g_client.historical_offsets_policy);
    free(g_client.cache_dir);
    free(g_client.base_url);
    free(g_client.proxy);
    free(g_client.ca_file);
    free(g_client.user_agent);
    memset(&g_client, 0, sizeof g_client);
    g_client.timeout_s = OTC_TIMEOUT_DEFAULT;   /* 0 is not "the defaults" in C (CR 4c) */
    g_client.formats = OTC_FORMATS_DEFAULT;
}

static int is_held(const otc_release *rel)
{
    size_t i;
    for (i = 0; i < g_n_held; i++)
        if (g_held[i].rel == rel) return 1;
    return 0;
}

static void close_current(void)
{
    if (g_current && !is_held(g_current)) otc_close(g_current);
    free(g_current_path);
    g_current = NULL;
    g_current_path = NULL;
}

static char *xstrdup(const char *s)
{
    size_t n = strlen(s) + 1;
    char *p = (char *)malloc(n);
    if (p) memcpy(p, s, n);
    return p;
}

/* ---------------------------------------------------------------- replies */

typedef struct reply {
    cJSON *result;      /* ok reply */
    const char *code;   /* error reply */
    char message[600];
    cJSON *fields;
} reply;

static void set_error(reply *r, const char *code, const char *message)
{
    if (r->result) { cJSON_Delete(r->result); r->result = NULL; }
    r->code = code;
    snprintf(r->message, sizeof r->message, "%s", message ? message : code);
}

static void set_status(reply *r, otc_status st, const char *what)
{
    set_error(r, otc_status_code(st), what);
}

/* Error fields from an otc_error (README: "C fills them from otc_error"). */
static void set_error_struct(reply *r, otc_status st, const otc_error *err)
{
    set_status(r, st, err->message[0] ? err->message : otc_status_code(st));
    r->fields = cJSON_CreateObject();
    if (st == OTC_E_IO || st == OTC_E_FILE_EXISTS) {
        cJSON_AddStringToObject(r->fields, "path", err->file);
    } else if (st == OTC_E_CHECKSUM) {
        cJSON_AddStringToObject(r->fields, "file", err->file);
        cJSON_AddStringToObject(r->fields, "expected", err->expected_sha256);
        cJSON_AddStringToObject(r->fields, "actual", err->actual_sha256);
    } else if (st == OTC_E_NETWORK) {
        cJSON_AddStringToObject(r->fields, "url", err->file);
        if (err->http_status) cJSON_AddNumberToObject(r->fields, "status", err->http_status);
        else cJSON_AddNullToObject(r->fields, "status");
    }
}

static char *render(reply *r)
{
    cJSON *o = cJSON_CreateObject();
    char *s;
    if (r->code) {
        cJSON *e = cJSON_CreateObject();
        cJSON_AddFalseToObject(o, "ok");
        cJSON_AddStringToObject(e, "code", r->code);
        cJSON_AddStringToObject(e, "message", r->message);
        if (r->fields) { cJSON_AddItemToObject(e, "fields", r->fields); r->fields = NULL; }
        cJSON_AddItemToObject(o, "error", e);
        if (r->result) cJSON_Delete(r->result);
    } else {
        cJSON_AddTrueToObject(o, "ok");
        cJSON_AddItemToObject(o, "result", r->result ? r->result : cJSON_CreateObject());
    }
    r->result = NULL;
    if (r->fields) cJSON_Delete(r->fields);
    r->fields = NULL;
    s = cJSON_PrintUnformatted(o);
    cJSON_Delete(o);
    return s;
}

/* ----------------------------------------------------- value conversions */

static cJSON *j_num(double v) { return isnan(v) ? cJSON_CreateNull() : cJSON_CreateNumber(v); }
static cJSON *j_count(int64_t v) { return v < 0 ? cJSON_CreateNull() : cJSON_CreateNumber((double)v); }
static cJSON *j_cstr(const char *s) { return s ? cJSON_CreateString(s) : cJSON_CreateNull(); }
static cJSON *j_fixed(const char *s) { return s[0] ? cJSON_CreateString(s) : cJSON_CreateNull(); }
static cJSON *j_enum(const char *name) { return name ? cJSON_CreateString(name) : cJSON_CreateNull(); }

/* cJSON_Parse writes a process-wide error slot, so parses from the worker
 * threads are serialised (the library does the same for its own copy). */
#ifdef _WIN32
static SRWLOCK g_parse_lock = SRWLOCK_INIT;
#define PARSE_LOCK() AcquireSRWLockExclusive(&g_parse_lock)
#define PARSE_UNLOCK() ReleaseSRWLockExclusive(&g_parse_lock)
#else
static pthread_mutex_t g_parse_lock = PTHREAD_MUTEX_INITIALIZER;
#define PARSE_LOCK() pthread_mutex_lock(&g_parse_lock)
#define PARSE_UNLOCK() pthread_mutex_unlock(&g_parse_lock)
#endif

static cJSON *j_parse_or_null(char *text, int *bad)
{
    cJSON *v = NULL;
    if (text && fault("json") && text[0]) text[0] = 'x';   /* the library returned text that is not JSON */
    if (text) {
        PARSE_LOCK();
        v = cJSON_Parse(text);
        PARSE_UNLOCK();
        if (v && strstr(text, "\\u0000")) {
            /* this cJSON would cut a string at its NUL: the text (valid JSON) goes out as it is */
            cJSON_Delete(v);
            v = cJSON_CreateRaw(text);
        }
        free(text);
        if (!v) *bad = 1;   /* the library gave text that is not JSON: a failure, never a null value */
    }
    return v ? v : cJSON_CreateNull();
}

/* A JSON string of n bytes that may hold a NUL (spec 6.4, CR2 DR33). The
 * runner's cJSON prints a string up to its first NUL, so such a string goes
 * out as a raw JSON literal with \u0000 in it. */
static cJSON *j_strn(const char *s, size_t n)
{
    static const char hex[] = "0123456789abcdef";
    char *lit;
    size_t i, o = 0;
    cJSON *v;
    if (!memchr(s, 0, n)) return cJSON_CreateString(s);
    lit = (char *)malloc(n * 6 + 3);
    if (!lit) return NULL;
    lit[o++] = '"';
    for (i = 0; i < n; i++) {
        unsigned char c = (unsigned char)s[i];
        if (c == '"' || c == '\\') { lit[o++] = '\\'; lit[o++] = (char)c; }
        else if (c < 0x20) {
            lit[o++] = '\\'; lit[o++] = 'u'; lit[o++] = '0'; lit[o++] = '0';
            lit[o++] = hex[c >> 4]; lit[o++] = hex[c & 15];
        } else lit[o++] = (char)c;
    }
    lit[o++] = '"';
    lit[o] = '\0';
    v = cJSON_CreateRaw(lit);
    free(lit);
    return v;
}

/* A string of n bytes as a JSON value (null for "no value"); frees s. */
static cJSON *j_take_n(char *s, size_t n)
{
    cJSON *v = s ? j_strn(s, n) : cJSON_CreateNull();
    free(s);
    return v;
}

/*
 * A string accessor called the way an app calls it: first into a sbuf
 * buffer (which checks OTC_E_BUFFER_TOO_SMALL and NUL termination), then
 * into a buffer of the reported size. Returns a malloc'd string, or NULL for
 * "no value" (OTC_E_NOT_FOUND); *n (may be NULL) gets its length, needed - 1,
 * which counts a NUL inside (CR2 DR33). *bad is set on any other status.
 *  - DEF_STR(NAME, ...): NAME gives the string as a JSON value (null for no value);
 *  - DEF_TEXT(NAME, ...): NAME gives JSON text the library printed, which has
 *    no NUL byte inside (a NUL in a string is the escape \u0000).
 */
#define DEF_BYTES(NAME, FN, T)                                                    \
    static char *NAME##_bytes(const T *o, size_t *n, int *bad)                    \
    {                                                                             \
        char sbuf[4];                                                            \
        size_t need = 0, need2 = 0;                                               \
        char *buf;                                                                \
        otc_status rc = FN(o, sbuf, sizeof sbuf, &need);                        \
        if (rc == OTC_E_NOT_FOUND) return NULL;                                   \
        if (rc == OTC_OK) {                                                       \
            if (need == 0 || need > sizeof sbuf || sbuf[need - 1] != '\0') {      \
                *bad = 1; return NULL;                                            \
            }                                                                     \
            buf = (char *)malloc(need);                                           \
            if (!buf) { *bad = 1; return NULL; }                                  \
            memcpy(buf, sbuf, need);                                              \
            if (n) *n = need - 1;                                                 \
            return buf;                                                           \
        }                                                                         \
        if (rc != OTC_E_BUFFER_TOO_SMALL || need <= sizeof sbuf                  \
            || sbuf[sizeof sbuf - 1] != '\0') { *bad = 1; return NULL; }        \
        if (FN(o, NULL, 0, &need2) != OTC_OK || need2 != need) {                 \
            *bad = 1; return NULL;                                                \
        }                                                                         \
        buf = (char *)malloc(need);                                               \
        if (!buf) { *bad = 1; return NULL; }                                      \
        if (FN(o, buf, need, &need2) != OTC_OK || need2 != need                  \
            || buf[need - 1] != '\0') {                                          \
            free(buf); *bad = 1; return NULL;                                     \
        }                                                                         \
        if (n) *n = need - 1;                                                     \
        return buf;                                                               \
    }
#define DEF_STR(NAME, FN, T)                                                      \
    DEF_BYTES(NAME, FN, T)                                                        \
    static cJSON *NAME(const T *o, int *bad)                                      \
    {                                                                             \
        size_t n = 0;                                                             \
        char *s = NAME##_bytes(o, &n, bad);                                       \
        return j_take_n(s, n);                                                    \
    }
#define DEF_TEXT(NAME, FN, T)                                                     \
    DEF_BYTES(NAME, FN, T)                                                        \
    static char *NAME(const T *o, int *bad)                                       \
    {                                                                             \
        size_t n = 0;                                                             \
        char *s = NAME##_bytes(o, &n, bad);                                       \
        if (s && strlen(s) != n) { free(s); *bad = 1; return NULL; }             \
        return s;                                                                 \
    }

DEF_STR(s_rel_datestamp, otc_release_datestamp, otc_release)
DEF_STR(s_rel_created, otc_release_created, otc_release)
DEF_STR(s_rel_format_version, otc_release_format_version, otc_release)
DEF_STR(s_rel_concept_doi, otc_release_concept_doi, otc_release)
DEF_STR(s_rel_zenodo_version_doi, otc_release_zenodo_version_doi, otc_release)
DEF_STR(s_rel_build_commit, otc_release_build_commit, otc_release)
DEF_STR(s_rel_changelog_url, otc_release_changelog_url, otc_release)
DEF_STR(s_rel_citation, otc_release_citation, otc_release)
DEF_STR(s_fi_name, otc_file_info_name, otc_file_info)
DEF_STR(s_fi_url, otc_file_info_url, otc_file_info)
DEF_STR(s_fi_sha256, otc_file_info_sha256, otc_file_info)
DEF_STR(s_conv_id, otc_convention_convention_id, otc_convention)
DEF_STR(s_conv_v0, otc_convention_v0_model, otc_convention)
DEF_TEXT(s_conv_nodal_ids, otc_convention_nodal_formula_ids_json, otc_convention)
DEF_STR(s_conv_table_version, otc_convention_constituent_table_version, otc_convention)
DEF_STR(s_conv_tables_sha, otc_convention_tables_sha256, otc_convention)
DEF_TEXT(s_conv_canary, otc_convention_canary_json, otc_convention)
DEF_TEXT(s_conv_raw, otc_convention_raw_json, otc_convention)
DEF_STR(s_lic_id, otc_licence_licence_id, otc_licence)
DEF_STR(s_lic_spdx, otc_licence_spdx, otc_licence)
DEF_STR(s_lic_provider, otc_licence_provider, otc_licence)
DEF_STR(s_lic_citation, otc_licence_citation, otc_licence)
DEF_STR(s_lic_attribution, otc_licence_attribution, otc_licence)
DEF_STR(s_lic_url, otc_licence_url, otc_licence)
DEF_STR(s_lic_restriction, otc_licence_restriction, otc_licence)
DEF_STR(s_lic_terms_url, otc_licence_terms_url, otc_licence)
DEF_TEXT(s_lic_raw, otc_licence_raw_json, otc_licence)
DEF_STR(s_st_id, otc_station_station_id, otc_station_t)
DEF_STR(s_st_name, otc_station_name, otc_station_t)
DEF_STR(s_st_country, otc_station_country, otc_station_t)
DEF_STR(s_st_timezone, otc_station_timezone, otc_station_t)
DEF_TEXT(s_st_raw, otc_station_raw_json, otc_station_t)
DEF_STR(s_tb_id, otc_tombstone_station_id, otc_tombstone_t)
DEF_STR(s_tb_name, otc_tombstone_name, otc_tombstone_t)
DEF_STR(s_tb_removed_in, otc_tombstone_removed_in, otc_tombstone_t)
DEF_STR(s_tb_merged_into, otc_tombstone_merged_into, otc_tombstone_t)
DEF_STR(s_tb_detail, otc_tombstone_detail, otc_tombstone_t)
DEF_TEXT(s_tb_raw, otc_tombstone_raw_json, otc_tombstone_t)
DEF_STR(s_set_id, otc_set_set_id, otc_set)
DEF_STR(s_set_source, otc_set_source, otc_set)
DEF_STR(s_set_record_id, otc_set_source_record_id, otc_set)
DEF_STR(s_set_version, otc_set_source_version, otc_set)
DEF_TEXT(s_set_raw, otc_set_raw_json, otc_set)
DEF_TEXT(s_set_prov_json, otc_set_provenance_json, otc_set)
DEF_STR(s_prov_adapter_version, otc_set_provenance_adapter_version, otc_set)
DEF_TEXT(s_prov_input_sha256, otc_set_provenance_input_sha256_json, otc_set)
DEF_STR(s_prov_selection_reason, otc_set_provenance_selection_reason, otc_set)
DEF_TEXT(s_prov_decision, otc_set_provenance_decision_json, otc_set)
DEF_STR(s_prov_carried, otc_set_provenance_carried_from_release, otc_set)
DEF_STR(s_build_commit, otc_provenance_build_build_commit, otc_provenance_build)
DEF_STR(s_build_built_at, otc_provenance_build_built_at, otc_provenance_build)
DEF_STR(s_build_fetched_at, otc_provenance_build_fetched_at, otc_provenance_build)
DEF_STR(s_build_run_id, otc_provenance_build_run_id, otc_provenance_build)
DEF_TEXT(s_build_tool_versions, otc_provenance_build_tool_versions_json, otc_provenance_build)
DEF_STR(s_tbase_reason, otc_time_base_reason, otc_time_base_t)
DEF_STR(s_tbase_declared, otc_time_base_declared, otc_time_base_t)
DEF_STR(s_tbase_published, otc_time_base_published, otc_time_base_t)
DEF_TEXT(s_tbase_corr_from, otc_time_base_correction_from, otc_time_base_t)
DEF_TEXT(s_tbase_corr_to, otc_time_base_correction_to, otc_time_base_t)
DEF_STR(s_tbase_decided_in, otc_time_base_decided_in, otc_time_base_t)
DEF_STR(s_tbase_decided_commit, otc_time_base_decided_build_commit, otc_time_base_t)
DEF_STR(s_ev_kind, otc_time_base_evidence_comparator_kind, otc_time_base_evidence)
DEF_STR(s_ev_id, otc_time_base_evidence_comparator_id, otc_time_base_evidence)
DEF_STR(s_ev_detail, otc_time_base_evidence_detail, otc_time_base_evidence)
DEF_STR(s_ri_datestamp, otc_release_info_datestamp, otc_release_info)
DEF_STR(s_ri_format_version, otc_release_info_format_version, otc_release_info)
DEF_STR(s_ri_concept_doi, otc_release_info_concept_doi, otc_release_info)
DEF_STR(s_ri_zenodo_version_doi, otc_release_info_zenodo_version_doi, otc_release_info)
DEF_STR(s_ri_content_sha256, otc_release_info_content_sha256, otc_release_info)
DEF_STR(s_span_start, otc_record_span_start, otc_record_span)
DEF_STR(s_span_end, otc_record_span_end, otc_record_span)
DEF_STR(s_flag_reason, otc_qc_flag_reason, otc_qc_flag)
DEF_TEXT(s_flag_values, otc_qc_flag_values_json, otc_qc_flag)
DEF_STR(s_drop_name, otc_dropped_name, otc_dropped)
DEF_STR(s_drop_detail, otc_dropped_detail, otc_dropped)

/* A lookup's status: OTC_OK gives the value, OTC_E_NOT_FOUND is "no value" (null), and any other status is a
 * library failure that sets *bad, never a null value. */
static int found(otc_status rc, int *bad)
{
    if (rc == OTC_OK) return 1;
    if (rc != OTC_E_NOT_FOUND) *bad = 1;
    return 0;
}

/* A string as a JSON value (null for "no value"). */
static cJSON *j_take(char *s)
{
    cJSON *v = s ? cJSON_CreateString(s) : cJSON_CreateNull();
    free(s);
    return v;
}

/* ----------------------------------------------------------- encodings */

static cJSON *enc_validation(const otc_validation_t *v)
{
    cJSON *o = cJSON_CreateObject();
    cJSON_AddItemToObject(o, "set_id", j_cstr(v->set_id));
    cJSON_AddItemToObject(o, "reference_source", j_cstr(v->reference_source));
    cJSON_AddItemToObject(o, "reference_station", j_cstr(v->reference_station));
    cJSON_AddItemToObject(o, "reference_distance_km", j_num(v->reference_distance_km));
    cJSON_AddItemToObject(o, "window", j_cstr(v->window));
    cJSON_AddItemToObject(o, "time_mae_min", j_num(v->time_mae_min));
    cJSON_AddItemToObject(o, "time_p95_min", j_num(v->time_p95_min));
    cJSON_AddItemToObject(o, "time_bias_min", j_num(v->time_bias_min));
    cJSON_AddItemToObject(o, "height_mae_m", j_num(v->height_mae_m));
    cJSON_AddItemToObject(o, "range_error_m", j_num(v->range_error_m));
    cJSON_AddItemToObject(o, "missed_events", j_count(v->missed_events));
    cJSON_AddItemToObject(o, "extra_events", j_count(v->extra_events));
    if (v->has_previous_release) {
        const otc_previous_release_t *p = &v->previous_release;
        cJSON *q = cJSON_CreateObject();
        cJSON_AddItemToObject(q, "time_mae_min", j_num(p->time_mae_min));
        cJSON_AddItemToObject(q, "time_p95_min", j_num(p->time_p95_min));
        cJSON_AddItemToObject(q, "time_bias_min", j_num(p->time_bias_min));
        cJSON_AddItemToObject(q, "height_mae_m", j_num(p->height_mae_m));
        cJSON_AddItemToObject(q, "range_error_m", j_num(p->range_error_m));
        cJSON_AddItemToObject(q, "missed_events", j_count(p->missed_events));
        cJSON_AddItemToObject(q, "extra_events", j_count(p->extra_events));
        cJSON_AddItemToObject(o, "previous_release", q);
    } else {
        cJSON_AddNullToObject(o, "previous_release");
    }
    return o;
}

static cJSON *enc_station(const otc_station_t *st, int *bad)
{
    cJSON *o = cJSON_CreateObject(), *aliases = cJSON_CreateObject();
    const otc_set *rec = NULL;
    size_t i, j, ns;
    cJSON_AddItemToObject(o, "station_id", s_st_id(st, bad));
    cJSON_AddItemToObject(o, "name", s_st_name(st, bad));
    cJSON_AddItemToObject(o, "country", s_st_country(st, bad));
    cJSON_AddItemToObject(o, "lat", j_num(otc_station_lat(st)));
    cJSON_AddItemToObject(o, "lon", j_num(otc_station_lon(st)));
    cJSON_AddItemToObject(o, "type", j_enum(otc_station_type_name(otc_station_type(st))));
    cJSON_AddItemToObject(o, "kind", j_enum(otc_kind_name(otc_station_kind(st))));
    cJSON_AddItemToObject(o, "timezone", s_st_timezone(st, bad));
    ns = otc_station_alias_system_count(st);
    for (i = 0; i < ns; i++) {
        char sys[256], id[1024];
        size_t need, n;
        cJSON *arr = cJSON_CreateArray();
        if (otc_station_alias_system_at(st, i, sys, sizeof sys, &need) != OTC_OK) { cJSON_Delete(arr); *bad = 1; break; }
        n = otc_station_alias_count(st, sys);
        for (j = 0; j < n; j++) {
            if (otc_station_alias_at(st, sys, j, id, sizeof id, &need) != OTC_OK || !need) { *bad = 1; break; }
            cJSON_AddItemToArray(arr, j_strn(id, need - 1));   /* an alias id may hold a NUL */
        }
        cJSON_AddItemToObject(aliases, sys, arr);
    }
    cJSON_AddItemToObject(o, "aliases", aliases);
    cJSON_AddItemToObject(o, "status", j_enum(otc_station_status_name(otc_station_status(st))));
    cJSON_AddBoolToObject(o, "is_reference", otc_station_is_reference(st));
    cJSON_AddBoolToObject(o, "is_subordinate", otc_station_is_subordinate(st));
    cJSON_AddBoolToObject(o, "is_tide", otc_station_is_tide(st));
    cJSON_AddBoolToObject(o, "is_current", otc_station_is_current(st));
    if (found(otc_station_recommended_set(st, &rec), bad))
        cJSON_AddItemToObject(o, "recommended_set_id", s_set_id(rec, bad));
    else
        cJSON_AddNullToObject(o, "recommended_set_id");
    return o;
}

static cJSON *enc_tombstone(const otc_tombstone_t *t, int *bad)
{
    cJSON *o = cJSON_CreateObject();
    cJSON_AddItemToObject(o, "station_id", s_tb_id(t, bad));
    cJSON_AddItemToObject(o, "name", s_tb_name(t, bad));
    cJSON_AddItemToObject(o, "status", j_enum(otc_station_status_name(otc_tombstone_status(t))));
    cJSON_AddItemToObject(o, "removed_in", s_tb_removed_in(t, bad));
    cJSON_AddItemToObject(o, "removed_reason", j_enum(otc_removed_reason_name(otc_tombstone_removed_reason(t))));
    cJSON_AddItemToObject(o, "merged_into", s_tb_merged_into(t, bad));
    cJSON_AddItemToObject(o, "detail", s_tb_detail(t, bad));
    return o;
}

/* months_dropped[i], called the way an app calls it (a size query, then the copy). */
static char *s_tbase_month(const otc_time_base_t *tb, size_t i, int *bad)
{
    size_t need = 0, need2 = 0;
    char *buf;
    if (otc_time_base_months_dropped_at(tb, i, NULL, 0, &need) != OTC_OK || !need) { *bad = 1; return NULL; }
    buf = (char *)malloc(need);
    if (!buf) { *bad = 1; return NULL; }
    if (otc_time_base_months_dropped_at(tb, i, buf, need, &need2) != OTC_OK || strlen(buf) + 1 != need) {
        free(buf);
        *bad = 1;
        return NULL;
    }
    return buf;
}

static cJSON *enc_time_base(const otc_time_base_t *tb, int *bad)
{
    cJSON *o = cJSON_CreateObject(), *months = cJSON_CreateArray(), *evs = cJSON_CreateArray();
    char *from, *to;
    size_t i, n;
    cJSON_AddItemToObject(o, "code", j_enum(otc_time_base_code_name(otc_time_base_code(tb))));
    cJSON_AddItemToObject(o, "reason", s_tbase_reason(tb, bad));
    cJSON_AddItemToObject(o, "declared", s_tbase_declared(tb, bad));
    cJSON_AddItemToObject(o, "published", s_tbase_published(tb, bad));
    from = s_tbase_corr_from(tb, bad);
    to = s_tbase_corr_to(tb, bad);
    if (from || to) {
        cJSON *c = cJSON_CreateObject();
        cJSON_AddItemToObject(c, "from", j_take(from));
        cJSON_AddItemToObject(c, "to", j_take(to));
        cJSON_AddItemToObject(o, "correction", c);
    } else {
        cJSON_AddNullToObject(o, "correction");
    }
    n = otc_time_base_months_dropped_count(tb);
    for (i = 0; i < n; i++) cJSON_AddItemToArray(months, j_take(s_tbase_month(tb, i, bad)));
    cJSON_AddItemToObject(o, "months_dropped", months);
    cJSON_AddItemToObject(o, "decided_in", s_tbase_decided_in(tb, bad));
    cJSON_AddItemToObject(o, "decided_build_commit", s_tbase_decided_commit(tb, bad));
    n = otc_time_base_evidence_count(tb);
    for (i = 0; i < n; i++) {
        const otc_time_base_evidence *ev = NULL;
        cJSON *e;
        if (otc_time_base_evidence_at(tb, i, &ev) != OTC_OK) { *bad = 1; break; }
        e = cJSON_CreateObject();
        cJSON_AddItemToObject(e, "comparator_kind", s_ev_kind(ev, bad));
        cJSON_AddItemToObject(e, "comparator_id", s_ev_id(ev, bad));
        cJSON_AddItemToObject(e, "distance_km", j_num(otc_time_base_evidence_distance_km(ev)));
        cJSON_AddItemToObject(e, "lag_min", j_num(otc_time_base_evidence_lag_min(ev)));
        cJSON_AddItemToObject(e, "detail", s_ev_detail(ev, bad));
        cJSON_AddItemToArray(evs, e);
    }
    cJSON_AddItemToObject(o, "evidence", evs);
    return o;
}

static cJSON *enc_set(const otc_set *set, int *bad)
{
    cJSON *o = cJSON_CreateObject(), *flags = cJSON_CreateArray(), *drops = cJSON_CreateArray();
    const otc_record_span *rs = NULL;
    const otc_datum *dt = NULL;
    const otc_convention *conv = NULL;
    const otc_licence *lic = NULL;
    const otc_time_base_t *tb = NULL;
    size_t i, n;
    cJSON_AddItemToObject(o, "set_id", s_set_id(set, bad));
    cJSON_AddItemToObject(o, "source", s_set_source(set, bad));
    cJSON_AddItemToObject(o, "source_type", j_enum(otc_source_type_name(otc_set_source_type(set))));
    cJSON_AddItemToObject(o, "quantity", j_enum(otc_quantity_name(otc_set_quantity(set))));
    cJSON_AddItemToObject(o, "source_record_id", s_set_record_id(set, bad));
    cJSON_AddItemToObject(o, "source_version", s_set_version(set, bad));
    if (found(otc_set_record_span(set, &rs), bad)) {
        cJSON *s = cJSON_CreateObject();
        cJSON_AddItemToObject(s, "start", s_span_start(rs, bad));
        cJSON_AddItemToObject(s, "end", s_span_end(rs, bad));
        cJSON_AddItemToObject(s, "good_samples", j_count(otc_record_span_good_samples(rs)));
        cJSON_AddItemToObject(o, "record_span", s);
    } else {
        cJSON_AddNullToObject(o, "record_span");
    }
    if (found(otc_set_datum(set, &dt), bad)) {
        cJSON *d = cJSON_CreateObject(), *named = cJSON_CreateObject();
        cJSON_AddItemToObject(d, "msl_offset_m", j_num(otc_datum_msl_offset_m(dt)));
        n = otc_datum_named_count(dt);
        for (i = 0; i < n; i++) {
            char name[256];
            size_t need;
            double v;
            if (otc_datum_named_at(dt, i, name, sizeof name, &need, &v) != OTC_OK) { *bad = 1; break; }
            cJSON_AddItemToObject(named, name, j_num(v));
        }
        cJSON_AddItemToObject(d, "named", named);
        cJSON_AddItemToObject(o, "datum", d);
    } else {
        cJSON_AddNullToObject(o, "datum");
    }
    cJSON_AddItemToObject(o, "qc_status", j_enum(otc_qc_status_name(otc_set_qc_status(set))));
    n = otc_set_qc_flag_count(set);
    for (i = 0; i < n; i++) {
        const otc_qc_flag *f = NULL;
        cJSON *fo = cJSON_CreateObject();
        if (otc_set_qc_flag_at(set, i, &f) != OTC_OK) { *bad = 1; cJSON_Delete(fo); break; }
        cJSON_AddItemToObject(fo, "flag", j_enum(otc_qc_flag_kind_name(otc_qc_flag_flag(f))));
        cJSON_AddItemToObject(fo, "reason", s_flag_reason(f, bad));
        cJSON_AddItemToObject(fo, "values", j_parse_or_null(s_flag_values(f, bad), bad));
        cJSON_AddItemToArray(flags, fo);
    }
    cJSON_AddItemToObject(o, "qc_flags", flags);
    n = otc_set_dropped_count(set);
    for (i = 0; i < n; i++) {
        const otc_dropped *d = NULL;
        cJSON *dobj = cJSON_CreateObject();
        if (otc_set_dropped_at(set, i, &d) != OTC_OK) { *bad = 1; cJSON_Delete(dobj); break; }
        cJSON_AddItemToObject(dobj, "name", s_drop_name(d, bad));
        cJSON_AddItemToObject(dobj, "dropped_reason", j_enum(otc_dropped_reason_name(otc_dropped_dropped_reason(d))));
        cJSON_AddItemToObject(dobj, "detail", s_drop_detail(d, bad));
        cJSON_AddItemToArray(drops, dobj);
    }
    cJSON_AddItemToObject(o, "dropped_constituents", drops);
    if (found(otc_set_time_base(set, &tb), bad)) cJSON_AddItemToObject(o, "time_base", enc_time_base(tb, bad));
    else cJSON_AddNullToObject(o, "time_base");
    cJSON_AddBoolToObject(o, "is_recommended", otc_set_is_recommended(set));
    if (found(otc_set_convention(set, &conv), bad)) cJSON_AddItemToObject(o, "convention_id", s_conv_id(conv, bad));
    else cJSON_AddNullToObject(o, "convention_id");
    if (found(otc_set_licence(set, &lic), bad)) cJSON_AddItemToObject(o, "licence_id", s_lic_id(lic, bad));
    else cJSON_AddNullToObject(o, "licence_id");
    cJSON_AddNumberToObject(o, "constituent_count", (double)otc_set_constituent_count(set));
    return o;
}

static cJSON *enc_constituent(const otc_constituent_t *c)
{
    cJSON *o = cJSON_CreateObject();
    cJSON_AddItemToObject(o, "name", j_fixed(c->name));
    cJSON_AddItemToObject(o, "source_name", j_fixed(c->source_name));
    cJSON_AddItemToObject(o, "doodson", j_fixed(c->doodson));
    cJSON_AddItemToObject(o, "speed_deg_per_hour", j_num(c->speed_deg_per_hour));
    cJSON_AddItemToObject(o, "amplitude_m", j_num(c->amplitude_m));
    cJSON_AddItemToObject(o, "phase_deg", j_num(c->phase_deg));
    cJSON_AddItemToObject(o, "amp_uncertainty_m", j_num(c->amp_uncertainty_m));
    cJSON_AddItemToObject(o, "phase_uncertainty_deg", j_num(c->phase_uncertainty_deg));
    cJSON_AddItemToObject(o, "kept_reason", j_fixed(c->kept_reason));
    return o;
}

static cJSON *enc_convention(const otc_convention *c, int *bad)
{
    cJSON *o = cJSON_CreateObject();
    cJSON_AddItemToObject(o, "convention_id", s_conv_id(c, bad));
    cJSON_AddItemToObject(o, "phase_reference", j_enum(otc_phase_reference_name(otc_convention_phase_reference(c))));
    cJSON_AddItemToObject(o, "utc_offset_hours", j_num(otc_convention_utc_offset_hours(c)));
    cJSON_AddItemToObject(o, "v0_model", s_conv_v0(c, bad));
    cJSON_AddItemToObject(o, "nodal_handling", j_enum(otc_nodal_handling_name(otc_convention_nodal_handling(c))));
    cJSON_AddItemToObject(o, "nodal_formula_ids", j_parse_or_null(s_conv_nodal_ids(c, bad), bad));
    cJSON_AddItemToObject(o, "constituent_table_version", s_conv_table_version(c, bad));
    cJSON_AddItemToObject(o, "tables_sha256", s_conv_tables_sha(c, bad));
    cJSON_AddItemToObject(o, "canary", j_parse_or_null(s_conv_canary(c, bad), bad));
    return o;
}

static cJSON *enc_licence(const otc_licence *l, int *bad)
{
    cJSON *o = cJSON_CreateObject();
    cJSON_AddItemToObject(o, "licence_id", s_lic_id(l, bad));
    cJSON_AddItemToObject(o, "spdx", s_lic_spdx(l, bad));
    cJSON_AddItemToObject(o, "provider", s_lic_provider(l, bad));
    cJSON_AddItemToObject(o, "citation", s_lic_citation(l, bad));
    cJSON_AddItemToObject(o, "attribution", s_lic_attribution(l, bad));
    cJSON_AddItemToObject(o, "url", s_lic_url(l, bad));
    cJSON_AddItemToObject(o, "commercial_use", cJSON_CreateBool(otc_licence_commercial_use(l)));
    cJSON_AddItemToObject(o, "restriction", s_lic_restriction(l, bad));
    cJSON_AddItemToObject(o, "terms_url", s_lic_terms_url(l, bad));
    return o;
}

static cJSON *enc_file_info(const otc_file_info *fi, int *bad)
{
    cJSON *o = cJSON_CreateObject();
    cJSON_AddItemToObject(o, "name", s_fi_name(fi, bad));
    cJSON_AddItemToObject(o, "url", s_fi_url(fi, bad));
    cJSON_AddItemToObject(o, "size", j_count(otc_file_info_size(fi)));
    cJSON_AddItemToObject(o, "sha256", s_fi_sha256(fi, bad));
    return o;
}

/* ------------------------------------------------------------- arguments */

typedef struct args {
    const cJSON *obj;
    int bad;          /* a value of the wrong type */
} args;

static int has_arg(const args *a, const char *name)
{
    return a->obj && cJSON_GetObjectItemCaseSensitive(a->obj, name) != NULL;
}

/* A string argument: absent or null -> NULL; another type sets bad. */
static const char *arg_str(args *a, const char *name)
{
    const cJSON *v = a->obj ? cJSON_GetObjectItemCaseSensitive(a->obj, name) : NULL;
    if (!v || cJSON_IsNull(v)) return NULL;
    if (!cJSON_IsString(v)) { a->bad = 1; return NULL; }
    return v->valuestring;
}

static double arg_num(args *a, const char *name, double dflt)
{
    const cJSON *v = a->obj ? cJSON_GetObjectItemCaseSensitive(a->obj, name) : NULL;
    if (!v || cJSON_IsNull(v)) return dflt;
    if (!cJSON_IsNumber(v)) { a->bad = 1; return dflt; }
    return v->valuedouble;
}

/*
 * A limit argument. Absent or null is "no limit". An explicit 0 is a value the SDK must judge (spec 4.4, D36: limit
 * must be 1 or more), so it is passed on as 0 only when the API has a separate no-limit value (OTC_NO_LIMIT);
 * without one, 0 means "no limit" to the library, and the runner must not hide the difference: *zero is set and
 * the op answers uncaught:LimitZero.
 */
static size_t arg_limit(args *a, const char *name, int *zero)
{
    const cJSON *v = a->obj ? cJSON_GetObjectItemCaseSensitive(a->obj, name) : NULL;
    double d;
#ifdef OTC_NO_LIMIT
    const size_t none = OTC_NO_LIMIT;
#else
    const size_t none = 0;
#endif
    *zero = 0;
    if (!v || cJSON_IsNull(v)) return none;
    d = arg_num(a, name, 0.0);
    if (a->bad || d < 0 || d != floor(d)) { a->bad = 1; return none; }
#ifndef OTC_NO_LIMIT
    if (d == 0) { *zero = 1; return none; }
#endif
    /* a limit larger than any size_t (1e30, say) asks for every hit; the cast would be undefined behaviour */
    if (d >= (double)SIZE_MAX) return SIZE_MAX;
    return (size_t)d;
}

#define LIMIT_ZERO_MESSAGE "limit 0: this C API has no separate no-limit value, so the runner cannot pass 0 (D36)"

static bool arg_bool(args *a, const char *name, bool dflt)
{
    const cJSON *v = a->obj ? cJSON_GetObjectItemCaseSensitive(a->obj, name) : NULL;
    if (!v || cJSON_IsNull(v)) return dflt;
    if (!cJSON_IsBool(v)) { a->bad = 1; return dflt; }
    return cJSON_IsTrue(v) ? true : false;
}

static void arg_filter(args *a, otc_filter *f)
{
    otc_filter_init(f);
    f->country = arg_str(a, "country");
    f->type = arg_str(a, "type");
    f->kind = arg_str(a, "kind");
    f->source = arg_str(a, "source");
    f->source_type = arg_str(a, "source_type");
    {
        const cJSON *v = a->obj ? cJSON_GetObjectItemCaseSensitive(a->obj, "include_flagged") : NULL;
        const cJSON *w = a->obj ? cJSON_GetObjectItemCaseSensitive(a->obj, "include_fallback") : NULL;
        if ((v && !cJSON_IsBool(v)) || (w && !cJSON_IsBool(w))) a->bad = 1;
    }
    f->include_flagged = arg_bool(a, "include_flagged", false);
    f->include_fallback = arg_bool(a, "include_fallback", false);
}

/* ------------------------------------------------------------------- ops */

typedef struct request {
    const char *op;
    args a;
    otc_release *rel;   /* the current or the held release */
    const char *path;   /* the path it was opened from */
} request;

static cJSON *ids_array(const char **ids, size_t n)
{
    cJSON *arr = cJSON_CreateArray();
    size_t i;
    for (i = 0; i < n; i++) cJSON_AddItemToArray(arr, cJSON_CreateString(ids[i]));
    return arr;
}

/* Calls a list function twice: first for the count (NULL, 0), then for the items. */
#define LIST_CALL(RC, TYPE, ITEMS, COUNT, CALL_NULL, CALL_BUF)                   \
    do {                                                                          \
        size_t cap_ = 0;                                                          \
        TYPE *ITEMS##_tmp = NULL;                                                 \
        (void)ITEMS##_tmp;                                                        \
        RC = CALL_NULL;                                                           \
        if (RC == OTC_OK || RC == OTC_E_BUFFER_TOO_SMALL) {                       \
            cap_ = COUNT;                                                         \
            ITEMS = fault("list-nomem") ? NULL : (TYPE *)calloc(cap_ ? cap_ : 1, sizeof(TYPE)); \
            RC = ITEMS ? CALL_BUF : OTC_E_NOMEM;                                  \
        }                                                                         \
    } while (0)

static void with_station(request *q, reply *r, otc_station_t **st, const char **id_out)
{
    const char *id = arg_str(&q->a, "station_id");
    otc_status rc;
    *st = NULL;
    if (id_out) *id_out = id;
    if (q->a.bad || !id) return;
    rc = otc_station(q->rel, id, st);
    if (rc != OTC_OK && rc != OTC_E_NOT_FOUND) set_status(r, rc, "otc_station");
}

/* The set named by set_id, or NULL when there is none (NOT_FOUND); any other status sets *bad. */
static const otc_set *find_set(request *q, const otc_station_t *st, int *bad)
{
    const char *set_id = arg_str(&q->a, "set_id");
    const otc_set *set = NULL;
    otc_status rc;
    if (!st || !set_id) return NULL;
    rc = fault("lookup") ? OTC_E_IO : otc_station_set(st, set_id, &set);
    if (rc == OTC_E_NOT_FOUND) return NULL;
    if (rc != OTC_OK) { *bad = 1; return NULL; }
    return set;
}

static char *dup_or_null(const char *v) { return v ? xstrdup(v) : NULL; }
static void fetch_options(otc_fetch_options *fo, otc_error *err);

/* The path of a release that otc_fetch_open just opened from the cache:
 * otc_fetch_release on a cached datestamp makes no network access. When the
 * runner cannot get it, the result is NO_PATH followed by the reason (the
 * library's code and message), which verify reports; a path never starts
 * with NO_PATH. ds is NULL when the datestamp itself could not be read (st). */
#define NO_PATH '\n'
static char *current_jsonl_path(const char *ds, otc_status st)
{
    otc_fetch_options fo;
    otc_error err;
    char path[4096], why[700];
    size_t need = 0;
    otc_status rc;
    fetch_options(&fo, &err);
    fo.offline = true;
    if (!ds) {
        snprintf(why, sizeof why, "%cotc_release_datestamp: %s", NO_PATH, otc_status_code(st));
    } else if ((rc = otc_fetch_release(&fo, ds, path, sizeof path, &need)) != OTC_OK) {
        snprintf(why, sizeof why, "%cotc_fetch_release(%s): %s: %.500s", NO_PATH, ds, otc_status_code(rc), err.message);
    } else {
        return xstrdup(path);
    }
    fprintf(stderr, "the runner has no path for the release: %s\n", why + 1);
    return xstrdup(why);
}

static void fetch_options(otc_fetch_options *fo, otc_error *err)
{
    otc_fetch_options_init(fo);
    otc_error_init(err);
    fo->error = err;
    fo->cache_dir = g_client.cache_dir;
    fo->base_url = g_client.base_url;
    fo->offline = g_client.offline;
    fo->proxy = g_client.proxy;
    fo->ca_file = g_client.ca_file;
    fo->user_agent = g_client.user_agent;
    fo->timeout_s = g_client.timeout_s;
    fo->on_network_error = g_client.on_network_error;
    fo->formats = g_client.formats;
}

/* The open options of every open (otc_open_file, and the open of the cached file in otc_fetch_open): the client's
 * require_checksum (CR2 DR34). err is the caller's error struct; it is not reset here. */
static void open_options(otc_open_options *oo, otc_error *err)
{
    otc_open_options_init(oo);
    oo->error = err;
    oo->require_checksum = g_client.require_checksum;
    oo->commercial_only = g_client.commercial_only;
    oo->commercial_basis = g_client.commercial_basis;
    oo->historical_offsets_policy = g_client.historical_offsets_policy;
}

static void op_open(request *q, reply *r)
{
    const char *file = arg_str(&q->a, "file"), *release = arg_str(&q->a, "release");
    const char *mode = arg_str(&q->a, "mode"), *one = arg_str(&q->a, "on_network_error");
    otc_error err;
    otc_status rc;
    if (q->a.bad) { set_error(r, "invalid_argument", "file and release must be strings"); return; }
    /* an enum the C API cannot hold (README "Argument rules"): invalid_argument, never a silent default */
    if (mode && strcmp(mode, "eager") && strcmp(mode, "stream")) {
        set_error(r, "invalid_argument", "mode must be eager or stream");
        return;
    }
    if (one && strcmp(one, "raise") && strcmp(one, "use_cache")) {
        set_error(r, "invalid_argument", "on_network_error must be raise or use_cache");
        return;
    }
    /* C has no client object: otc_open_file takes no fetch options. The runner models the client, so it applies the
     * rule of spec 4.2 (CR D31) itself: a file client cannot take release, offline or on_network_error */
    if (file && ((release && strcmp(release, "latest")) || arg_bool(&q->a, "offline", false) || (one && strcmp(one, "use_cache")))) {
        set_error(r, "invalid_argument", "file cannot be combined with release, offline or on_network_error");
        return;
    }
    {   /* every option is read and checked before anything changes: a rejected open keeps the open release and the
         * client options, as in the other SDKs */
        const char *cache_dir = arg_str(&q->a, "cache_dir"), *base_url = arg_str(&q->a, "base_url");
        const char *proxy = arg_str(&q->a, "proxy"), *ca_file = arg_str(&q->a, "ca_file");
        const char *user_agent = arg_str(&q->a, "user_agent");
        bool offline = arg_bool(&q->a, "offline", false), auto_update = arg_bool(&q->a, "auto_update", false);
        bool require_checksum = arg_bool(&q->a, "require_checksum", false);
        bool commercial_only = arg_bool(&q->a, "commercial_only", false);
        const char *commercial_basis = arg_str(&q->a, "commercial_basis"), *history_policy = arg_str(&q->a, "historical_offsets_policy");
        /* absent or null: OTC_TIMEOUT_DEFAULT (the defaults); an explicit value, 0 included, goes to the library as it
         * is, so the library judges it (CR 4c). The sentinel itself has no other spelling: a case that gives it fails
         * loudly */
        double timeout_s = arg_num(&q->a, "timeout", OTC_TIMEOUT_DEFAULT);
        double update_interval = arg_num(&q->a, "update_interval", 86400.0);
        if (q->a.bad) { set_error(r, "invalid_argument", "an open option has the wrong type"); return; }
        if (q->a.obj && cJSON_IsNumber(cJSON_GetObjectItemCaseSensitive(q->a.obj, "timeout")) &&
            timeout_s == OTC_TIMEOUT_DEFAULT) {
            set_error(r, "uncaught:TimeoutSentinel", "timeout equals OTC_TIMEOUT_DEFAULT, which C reads as the defaults");
            return;
        }
        close_current();
        client_free();
        g_client.cache_dir = dup_or_null(cache_dir);
        g_client.base_url = dup_or_null(base_url);
        g_client.proxy = dup_or_null(proxy);
        g_client.ca_file = dup_or_null(ca_file);
        g_client.user_agent = dup_or_null(user_agent);
        g_client.offline = offline;
        g_client.require_checksum = require_checksum;
        g_client.commercial_only = commercial_only;
        g_client.commercial_basis = dup_or_null(commercial_basis);
        g_client.historical_offsets_policy = dup_or_null(history_policy);
        g_client.timeout_s = timeout_s;
        g_client.on_network_error = one && !strcmp(one, "raise") ? OTC_ON_NETWORK_ERROR_RAISE : OTC_ON_NETWORK_ERROR_USE_CACHE;
        /* C always reads the .jsonl; eager mode also keeps OTC_{D}.json in the cache, as the other SDKs do */
        g_client.formats = mode && !strcmp(mode, "eager") ? (unsigned)(OTC_FORMAT_JSON | OTC_FORMAT_JSONL) : OTC_FORMATS_DEFAULT;
        g_client.pinned = file != NULL || (release && strcmp(release, "latest") != 0);
        g_client.auto_update = auto_update;
        g_client.update_interval = update_interval;
        g_client.last_check = now_s();
    }
    otc_error_init(&err);
    if (file) {
        otc_open_options opts;
        otc_release *rel = NULL;
        open_options(&opts, &err);
        rc = otc_open_file(file, &opts, &rel);
        if (rc != OTC_OK) { set_error_struct(r, rc, &err); return; }
        g_current = rel;
        g_current_path = xstrdup(file);
    } else {
        /* No file: the release comes from the otc_fetch module (download or cache). */
        otc_fetch_options fo;
        otc_open_options oo;
        char path[4096];
        size_t need = 0;
        fetch_options(&fo, &err);
        open_options(&oo, &err);
        rc = otc_fetch_open(&fo, release, &oo, &g_current);
        if (rc != OTC_OK) { set_error_struct(r, rc, &err); return; }
        rc = otc_release_datestamp(g_current, path, sizeof path, &need);
        g_current_path = current_jsonl_path(rc == OTC_OK ? path : NULL, rc);
    }
    {
        int bad = 0;
        cJSON *o = cJSON_CreateObject();
        cJSON_AddItemToObject(o, "loaded_from", j_enum(otc_loaded_from_name(otc_release_loaded_from(g_current))));
        cJSON_AddItemToObject(o, "datestamp", s_rel_datestamp(g_current, &bad));
        cJSON_AddItemToObject(o, "format_version", s_rel_format_version(g_current, &bad));
        r->result = o;
        if (bad) set_error(r, "uncaught:BufferProtocol", "a string accessor broke the buffer rules");
    }
}

static const char *base_of(const char *p);

static void op_verify(request *q, reply *r)
{
    size_t i, n = otc_release_file_count(q->rel);
    char dir[4096];
    const char *slash1, *slash2, *slash;
    size_t dlen;
    int opened_hashed = 0;   /* the file the release was opened from must be one of the files hashed */
    otc_error oerr;
    otc_status orc;
    /* no path: the runner does not know where the release is; it must not answer verified with nothing hashed */
    if (!q->path || !q->path[0] || q->path[0] == NO_PATH) {
        char msg[sizeof r->message];
        snprintf(msg, sizeof msg, "verify: the runner has no path for this release (%.500s)",
                 q->path && q->path[0] ? q->path + 1 : "no reason recorded");
        set_error(r, "uncaught:NoPath", msg);
        return;
    }
    slash1 = strrchr(q->path, '/');
    slash2 = strrchr(q->path, '\\');
    slash = slash1 > slash2 ? slash1 : slash2;
    dlen = slash ? (size_t)(slash - q->path + 1) : 0;
    if (dlen >= sizeof dir) { set_error(r, "uncaught:PathTooLong", "path too long"); return; }
    memcpy(dir, q->path, dlen);
    dir[dlen] = '\0';
    for (i = 0; i < n; i++) {
        const otc_file_info *fi = NULL;
        char name[1024], full[8192];
        size_t need;
        otc_error err;
        otc_status rc;
        if (otc_release_file_at(q->rel, i, &fi) != OTC_OK) { set_error(r, "uncaught:FileList", "file_at"); return; }
        if (otc_file_info_size(fi) < 0) continue;   /* not present next to the opened file */
        if (otc_file_info_sha256(fi, NULL, 0, &need) == OTC_E_NOT_FOUND) continue;
        if (otc_file_info_name(fi, name, sizeof name, &need) != OTC_OK) { set_error(r, "uncaught:FileName", "name"); return; }
        {   /* the .sha256 list is what the files are checked against (a cached release lists it too) */
            size_t nl = strlen(name);
            if (nl > 7 && !strcmp(name + nl - 7, ".sha256")) continue;
        }
        snprintf(full, sizeof full, "%s%s", dir, name);
        {   /* only the files that are there (a cached release lists every file of the release), except the two the
             * release was read from: the opened file and its .meta.json must be there, so a missing one fails */
            const char *base = base_of(q->path), *dot = strrchr(base, '.');
            size_t stem = dot && !strcmp(dot, ".jsonl") ? (size_t)(dot - base) : 0;
            int required = !strcmp(name, base) || (stem && !strncmp(name, base, stem) && !strcmp(name + stem, ".meta.json"));
            FILE *f = fopen(full, "rb");
            if (f) fclose(f);
            else if (!required) continue;
        }
        otc_error_init(&err);
        rc = otc_verify_file(full, NULL, &err);
        if (rc != OTC_OK) { set_error_struct(r, rc, &err); return; }
        if (!strcmp(full, q->path)) opened_hashed = 1;
    }
    if (!opened_hashed) {
        /* the opened file was not hashed: it is gone (the library reports that), or no checksum lists it */
        otc_error_init(&oerr);
        orc = otc_verify_file(q->path, NULL, &oerr);
        if (orc != OTC_OK) { set_error_struct(r, orc, &oerr); return; }
        set_error(r, "uncaught:NothingVerified", "verify: no checksum covers the file the release was opened from");
        return;
    }
    r->result = cJSON_CreateObject();
    cJSON_AddTrueToObject(r->result, "verified");
}

/* One Stats map. An entry the library fails to give sets *bad: a smaller map would pass as wrong stats. */
static void stats_map(cJSON *o, const char *key, const otc_stats *s,
                      size_t (*count_fn)(const otc_stats *),
                      otc_status (*at_fn)(const otc_stats *, size_t, const char **, int64_t *), int *bad)
{
    cJSON *m = cJSON_CreateObject();
    size_t i, n = count_fn(s);
    for (i = 0; i < n; i++) {
        const char *k = NULL;
        int64_t c = 0;
        if (at_fn(s, i, &k, &c) != OTC_OK || !k) { *bad = 1; break; }
        cJSON_AddNumberToObject(m, k, (double)c);
    }
    cJSON_AddItemToObject(o, key, m);
}

static void op_query(request *q, reply *r)
{
    const char *op = q->op;
    otc_release *R = q->rel;
    int bad = 0;
    otc_status rc;
    cJSON *o = cJSON_CreateObject();
    r->result = o;

    if (!strcmp(op, "loaded_from")) {
        cJSON_AddItemToObject(o, "loaded_from", j_enum(otc_loaded_from_name(otc_release_loaded_from(R))));
    } else if (!strcmp(op, "last_error")) {
        /* client.last_error: the failure of the last automatic update (C69), else the error behind loaded_from
         * cache_after_error. */
        if (g_client.auto_update_nomove) {
            set_error(r, "uncaught:UpdateNoMove", "the automatic update reported an update that names no newer release");
            return;
        }
        if (g_client.auto_update_status != OTC_OK)
            cJSON_AddStringToObject(o, "code", otc_status_code(g_client.auto_update_status));
        else if (otc_release_loaded_from(R) == OTC_LOADED_FROM_CACHE_AFTER_ERROR && !g_client.pointer_reached)
            cJSON_AddStringToObject(o, "code", otc_status_code(otc_last_error_status(R)));
        else
            cJSON_AddNullToObject(o, "code");
    } else if (!strcmp(op, "release_metadata")) {
        cJSON *sv = cJSON_CreateObject();
        size_t i, n = otc_release_source_version_count(R);
        cJSON_AddItemToObject(o, "datestamp", s_rel_datestamp(R, &bad));
        cJSON_AddItemToObject(o, "created", s_rel_created(R, &bad));
        cJSON_AddItemToObject(o, "format_version", s_rel_format_version(R, &bad));
        cJSON_AddItemToObject(o, "concept_doi", s_rel_concept_doi(R, &bad));
        cJSON_AddItemToObject(o, "zenodo_version_doi", s_rel_zenodo_version_doi(R, &bad));
        for (i = 0; i < n; i++) {
            char k[256], v[256];
            size_t nk, nv;
            if (otc_release_source_version_at(R, i, k, sizeof k, &nk, v, sizeof v, &nv) != OTC_OK) { bad = 1; break; }
            cJSON_AddStringToObject(sv, k, v);
        }
        cJSON_AddItemToObject(o, "source_versions", sv);
        cJSON_AddItemToObject(o, "build_commit", s_rel_build_commit(R, &bad));
        cJSON_AddItemToObject(o, "changelog_url", s_rel_changelog_url(R, &bad));
    } else if (!strcmp(op, "release_files")) {
        cJSON *arr = cJSON_CreateArray();
        size_t i, n = otc_release_file_count(R);
        for (i = 0; i < n; i++) {
            const otc_file_info *fi = NULL;
            if (otc_release_file_at(R, i, &fi) != OTC_OK) { bad = 1; break; }
            cJSON_AddItemToArray(arr, enc_file_info(fi, &bad));
        }
        cJSON_AddItemToObject(o, "files", arr);
    } else if (!strcmp(op, "station_count")) {
        cJSON_AddNumberToObject(o, "station_count", (double)otc_release_station_count(R));
    } else if (!strcmp(op, "tombstone_count")) {
        cJSON_AddNumberToObject(o, "tombstone_count", (double)otc_release_tombstone_count(R));
    } else if (!strcmp(op, "stats")) {
        otc_stats *s = NULL;
        cJSON *so;
        rc = otc_release_stats(R, &s);
        if (rc != OTC_OK) { set_status(r, rc, "otc_release_stats"); return; }
        so = cJSON_CreateObject();
        stats_map(so, "type", s, otc_stats_type_count, otc_stats_type_at, &bad);
        stats_map(so, "kind", s, otc_stats_kind_count, otc_stats_kind_at, &bad);
        stats_map(so, "country", s, otc_stats_country_count, otc_stats_country_at, &bad);
        stats_map(so, "source", s, otc_stats_source_count, otc_stats_source_at, &bad);
        stats_map(so, "qc_status", s, otc_stats_qc_status_count, otc_stats_qc_status_at, &bad);
        otc_stats_free(s);
        cJSON_AddItemToObject(o, "stats", so);
    } else if (!strcmp(op, "constituent_names")) {
        const char **names = NULL;
        size_t count = 0;
        LIST_CALL(rc, const char *, names, count, otc_release_constituent_names(R, NULL, 0, &count),
                  otc_release_constituent_names(R, names, cap_, &count));
        if (rc != OTC_OK) { free((void *)names); set_status(r, rc, "constituent_names"); return; }
        cJSON_AddItemToObject(o, "names", ids_array(names, count));
        free((void *)names);
    } else if (!strcmp(op, "conventions")) {
        cJSON *arr = cJSON_CreateArray();
        size_t i, n = otc_release_convention_count(R);
        for (i = 0; i < n; i++) {
            const otc_convention *c = NULL;
            if (otc_release_convention_at(R, i, &c) != OTC_OK) { bad = 1; break; }
            cJSON_AddItemToArray(arr, enc_convention(c, &bad));
        }
        cJSON_AddItemToObject(o, "conventions", arr);
    } else if (!strcmp(op, "convention")) {
        const char *id = arg_str(&q->a, "convention_id");
        const otc_convention *c = NULL;
        rc = q->a.bad || !id ? OTC_E_NOT_FOUND : fault("lookup") ? OTC_E_IO : otc_release_convention(R, id, &c);
        if (rc == OTC_OK) cJSON_AddItemToObject(o, "convention", enc_convention(c, &bad));
        else if (rc == OTC_E_NOT_FOUND) cJSON_AddNullToObject(o, "convention");
        else bad = 1;
    } else if (!strcmp(op, "licences")) {
        cJSON *arr = cJSON_CreateArray();
        size_t i, n = otc_release_licence_count(R);
        for (i = 0; i < n; i++) {
            const otc_licence *l = NULL;
            if (otc_release_licence_at(R, i, &l) != OTC_OK) { bad = 1; break; }
            cJSON_AddItemToArray(arr, enc_licence(l, &bad));
        }
        cJSON_AddItemToObject(o, "licences", arr);
    } else if (!strcmp(op, "licence")) {
        const char *id = arg_str(&q->a, "licence_id");
        const otc_licence *l = NULL;
        rc = q->a.bad || !id ? OTC_E_NOT_FOUND : otc_release_licence(R, id, &l);
        if (rc == OTC_OK) cJSON_AddItemToObject(o, "licence", enc_licence(l, &bad));
        else if (rc == OTC_E_NOT_FOUND) cJSON_AddNullToObject(o, "licence");
        else bad = 1;
    } else if (!strcmp(op, "citation")) {
        cJSON_AddItemToObject(o, "citation", s_rel_citation(R, &bad));
    } else if (!strcmp(op, "attribution")) {
        const cJSON *ids = q->a.obj ? cJSON_GetObjectItemCaseSensitive(q->a.obj, "station_ids") : NULL;
        const char **idv = NULL;
        size_t n = 0, need = 0;
        char *buf;
        if (ids && !cJSON_IsNull(ids)) {
            const cJSON *it;
            if (!cJSON_IsArray(ids)) { set_error(r, "invalid_argument", "station_ids"); return; }
            idv = (const char **)calloc((size_t)cJSON_GetArraySize(ids) + 1, sizeof *idv);
            if (!idv) { set_error(r, "uncaught:NoMemory", "attribution: no memory for the station ids"); return; }
            cJSON_ArrayForEach(it, ids) {
                if (!cJSON_IsString(it)) { free((void *)idv); set_error(r, "invalid_argument", "station_ids"); return; }
                idv[n++] = it->valuestring;
            }
        }
        rc = otc_attribution(R, idv, n, NULL, 0, &need);
        buf = rc == OTC_OK ? (char *)malloc(need) : NULL;
        if (buf) rc = otc_attribution(R, idv, n, buf, need, &need);
        free((void *)idv);
        if (rc != OTC_OK || !buf) { free(buf); set_status(r, rc ? rc : OTC_E_NOMEM, "otc_attribution"); return; }
        cJSON_AddStringToObject(o, "attribution", buf);
        free(buf);
    } else if (!strcmp(op, "station") || !strcmp(op, "require_station")) {
        otc_station_t *st = NULL;
        const char *id = arg_str(&q->a, "station_id");
        if (q->a.bad) { set_error(r, "invalid_argument", "station_id"); return; }
        rc = !strcmp(op, "station") ? otc_station(R, id, &st) : otc_require_station(R, id, &st);
        if (rc == OTC_OK) {
            cJSON_AddItemToObject(o, "station", enc_station(st, &bad));
            otc_station_free(st);
        } else if (rc == OTC_E_NOT_FOUND) {
            cJSON_AddNullToObject(o, "station");
        } else {
            char msg[512];
            size_t need = 0;
            otc_tombstone_t *t = NULL;
            if (otc_last_error(R, msg, sizeof msg, &need) != OTC_OK) snprintf(msg, sizeof msg, "%s", op);
            set_status(r, rc, msg);
            /* station_removed carries the tombstone (spec 4.4): the handle's error names it, otc_tombstone gives it */
            if (rc == OTC_E_STATION_REMOVED && id && otc_tombstone(R, id, &t) == OTC_OK) {
                r->fields = cJSON_CreateObject();
                cJSON_AddItemToObject(r->fields, "tombstone", enc_tombstone(t, &bad));
                otc_tombstone_free(t);
                /* a tombstone the runner could not encode: the code changes too, so a code-only check fails */
                if (bad) set_error(r, "uncaught:BufferProtocol", "the tombstone of station_removed could not be encoded");
            }
            return;
        }
    } else if (!strcmp(op, "tombstone")) {
        otc_tombstone_t *t = NULL;
        const char *id = arg_str(&q->a, "station_id");
        /* a station_id of the wrong type is the runner's invalid_argument (README "Argument rules"), never the
         * library's answer for the NULL that arg_str gives */
        if (q->a.bad) { set_error(r, "invalid_argument", "station_id"); return; }
        rc = otc_tombstone(R, id, &t);
        if (rc == OTC_OK) {
            cJSON_AddItemToObject(o, "tombstone", enc_tombstone(t, &bad));
            otc_tombstone_free(t);
        } else if (rc == OTC_E_NOT_FOUND) {
            cJSON_AddNullToObject(o, "tombstone");
        } else {
            set_status(r, rc, op);
            return;
        }
    } else if (!strcmp(op, "station_by_alias")) {
        otc_station_t *st = NULL;
        const char *system = arg_str(&q->a, "system"), *alias = arg_str(&q->a, "alias_id");
        if (q->a.bad) { set_error(r, "invalid_argument", "system/alias_id"); return; }
        rc = otc_station_by_alias(R, system, alias, &st);
        if (rc == OTC_OK) {
            cJSON_AddItemToObject(o, "station_id", s_st_id(st, &bad));
            otc_station_free(st);
        } else if (rc == OTC_E_NOT_FOUND) {
            cJSON_AddNullToObject(o, "station_id");
        } else {
            set_status(r, rc, op);
            return;
        }
    } else if (!strcmp(op, "stations")) {
        otc_filter f;
        const char **ids = NULL;
        size_t count = 0;
        arg_filter(&q->a, &f);
        if (q->a.bad) { set_error(r, "invalid_argument", "a filter argument has the wrong type"); return; }
        LIST_CALL(rc, const char *, ids, count, otc_stations(R, &f, NULL, 0, &count),
                  otc_stations(R, &f, ids, cap_, &count));
        if (rc != OTC_OK) { free((void *)ids); set_status(r, rc, op); return; }
        cJSON_AddItemToObject(o, "station_ids", ids_array(ids, count));
        free((void *)ids);
    } else if (!strcmp(op, "iter_stations")) {
        otc_filter f;
        otc_iter *it = NULL;
        otc_station_t *st = NULL;
        cJSON *arr;
        arg_filter(&q->a, &f);
        if (q->a.bad) { set_error(r, "invalid_argument", "a filter argument has the wrong type"); return; }
        rc = otc_iter_open(R, &f, &it);
        if (rc != OTC_OK) { set_status(r, rc, op); return; }
        arr = cJSON_CreateArray();
        while ((rc = otc_iter_next(it, &st)) == OTC_OK) {
            cJSON_AddItemToArray(arr, s_st_id(st, &bad));
            otc_station_free(st);
            st = NULL;
        }
        otc_iter_close(it);
        if (rc != OTC_E_NOT_FOUND) { cJSON_Delete(arr); set_status(r, rc, op); return; }
        cJSON_AddItemToObject(o, "station_ids", arr);
    } else if (!strcmp(op, "search")) {
        otc_filter f;
        otc_hit *hits = NULL;
        size_t count = 0, i, limit;
        int zero = 0;
        const char *name = arg_str(&q->a, "name"), *match = arg_str(&q->a, "match");
        cJSON *arr;
        arg_filter(&q->a, &f);
        limit = arg_limit(&q->a, "limit", &zero);
        if (zero) { set_error(r, "uncaught:LimitZero", LIMIT_ZERO_MESSAGE); return; }
        if (match) {
            if (!strcmp(match, "exact")) f.match_exact = true;
            else q->a.bad = 1;
        }
        if (q->a.bad || !name) { set_error(r, "invalid_argument", "search arguments"); return; }
        LIST_CALL(rc, otc_hit, hits, count, otc_search(R, name, &f, limit, NULL, 0, &count),
                  otc_search(R, name, &f, limit, hits, cap_, &count));
        if (rc != OTC_OK) { free(hits); set_status(r, rc, op); return; }
        arr = cJSON_CreateArray();
        for (i = 0; i < count; i++) {
            /* name_len is the whole name, NULs inside included (CR2 DR33): the NUL comes right after it */
            if (!hits[i].name || hits[i].name[hits[i].name_len] != '\0' || strlen(hits[i].name) > hits[i].name_len) bad = 1;
            cJSON_AddItemToArray(arr, cJSON_CreateString(hits[i].id));
        }
        free(hits);
        cJSON_AddItemToObject(o, "station_ids", arr);
    } else if (!strcmp(op, "near")) {
        otc_filter f;
        otc_nearby *hits = NULL;
        size_t count = 0, i, limit;
        double lat = arg_num(&q->a, "lat", NAN), lon = arg_num(&q->a, "lon", NAN);
        double radius = arg_num(&q->a, "radius_km", NAN);
        cJSON *ids, *dist;
        int zero = 0;
        arg_filter(&q->a, &f);
        limit = arg_limit(&q->a, "limit", &zero);
        if (zero) { set_error(r, "uncaught:LimitZero", LIMIT_ZERO_MESSAGE); return; }
        if (q->a.bad) { set_error(r, "invalid_argument", "near arguments"); return; }
        LIST_CALL(rc, otc_nearby, hits, count, otc_near(R, lat, lon, radius, &f, limit, NULL, 0, &count),
                  otc_near(R, lat, lon, radius, &f, limit, hits, cap_, &count));
        if (rc != OTC_OK) { free(hits); set_status(r, rc, op); return; }
        ids = cJSON_CreateArray();
        dist = cJSON_CreateArray();
        for (i = 0; i < count; i++) {
            cJSON_AddItemToArray(ids, cJSON_CreateString(hits[i].id));
            cJSON_AddItemToArray(dist, cJSON_CreateNumber(hits[i].distance_km));
        }
        free(hits);
        cJSON_AddItemToObject(o, "station_ids", ids);
        cJSON_AddItemToObject(o, "distance_km", dist);
    } else if (!strcmp(op, "nearest")) {
        otc_filter f;
        otc_nearby hit;
        double lat = arg_num(&q->a, "lat", NAN), lon = arg_num(&q->a, "lon", NAN);
        double max_km = arg_num(&q->a, "max_km", NAN);
        arg_filter(&q->a, &f);
        if (q->a.bad) { set_error(r, "invalid_argument", "nearest arguments"); return; }
        rc = otc_nearest(R, lat, lon, max_km, &f, &hit);
        if (rc == OTC_OK) {
            cJSON_AddStringToObject(o, "station_id", hit.id);
            cJSON_AddNumberToObject(o, "distance_km", hit.distance_km);
        } else if (rc == OTC_E_NOT_FOUND) {
            cJSON_AddNullToObject(o, "station_id");
            cJSON_AddNullToObject(o, "distance_km");
        } else {
            set_status(r, rc, op);
            return;
        }
    } else {
        /* Ops on one station (and maybe one of its sets). */
        otc_station_t *st = NULL;
        with_station(q, r, &st, NULL);
        if (r->code) return;
        if (q->a.bad) { otc_station_free(st); set_error(r, "invalid_argument", "station_id"); return; }
        int passed = 0;   /* the station goes to the library even when it is NULL or foreign (CR2 DR24) */
        if (!strcmp(op, "reference_station") || !strcmp(op, "subordinates_of")) {
            /* station_id null is passed as NULL, and station_on looks the station up in a held release */
            const cJSON *sid = q->a.obj ? cJSON_GetObjectItemCaseSensitive(q->a.obj, "station_id") : NULL;
            const char *on = arg_str(&q->a, "station_on");
            passed = (sid && cJSON_IsNull(sid)) || on;
            if (on) {
                size_t k;
                const char *id = arg_str(&q->a, "station_id");
                otc_station_free(st);
                st = NULL;
                for (k = 0; k < g_n_held; k++) {
                    if (!strcmp(g_held[k].name, on)) {
                        rc = id ? otc_station(g_held[k].rel, id, &st) : OTC_OK;
                        if (rc != OTC_OK && rc != OTC_E_NOT_FOUND) { set_status(r, rc, "otc_station"); return; }
                    }
                }
            }
        }
        if (!strcmp(op, "reference_station")) {
            otc_station_t *ref = NULL;
            rc = (!st && !passed) ? OTC_E_NOT_FOUND : fault("lookup") ? OTC_E_IO : otc_reference_station(R, st, &ref);
            if (rc == OTC_OK) {
                cJSON_AddItemToObject(o, "station_id", s_st_id(ref, &bad));
                otc_station_free(ref);
            } else if (rc == OTC_E_INVALID_ARGUMENT) {
                otc_station_free(st);
                set_status(r, rc, "otc_reference_station");
                return;
            } else {
                if (rc != OTC_E_NOT_FOUND) bad = 1;
                cJSON_AddNullToObject(o, "station_id");
            }
        } else if (!strcmp(op, "subordinates_of")) {
            const char **ids = NULL;
            size_t count = 0;
            if (st || passed) {
                LIST_CALL(rc, const char *, ids, count, otc_subordinates_of(R, st, NULL, 0, &count),
                          otc_subordinates_of(R, st, ids, cap_, &count));
                if (rc != OTC_OK) {   /* ids may be NULL with a count: never read them */
                    free((void *)ids);
                    otc_station_free(st);
                    set_status(r, rc, "otc_subordinates_of");
                    return;
                }
            }
            cJSON_AddItemToObject(o, "station_ids", (st || passed) ? ids_array(ids, count) : cJSON_CreateNull());
            free((void *)ids);
        } else if (!strcmp(op, "station_validation")) {
            cJSON *arr = st ? cJSON_CreateArray() : cJSON_CreateNull();
            size_t i, n = st ? otc_station_validation_count(st) : 0;
            for (i = 0; i < n; i++) {
                const otc_validation_t *v = NULL;
                if (otc_station_validation_at(st, i, &v) != OTC_OK) { bad = 1; break; }
                cJSON_AddItemToArray(arr, enc_validation(v));
            }
            cJSON_AddItemToObject(o, "validation", arr);
        } else if (!strcmp(op, "subordinate_offsets")) {
            otc_offsets_t off;
            memset(&off, 0, sizeof off);
            off.struct_size = sizeof off;
            rc = !st ? OTC_E_NOT_FOUND : fault("lookup") ? OTC_E_IO : otc_station_offsets(st, &off);
            if (rc != OTC_OK && rc != OTC_E_NOT_FOUND) bad = 1;
            if (rc == OTC_OK) {
                cJSON *x = cJSON_CreateObject();
                cJSON_AddItemToObject(x, "reference_station_id", j_cstr(off.reference_station_id));
                cJSON_AddItemToObject(x, "time_offset_high_min", j_num(off.time_offset_high_min));
                cJSON_AddItemToObject(x, "time_offset_low_min", j_num(off.time_offset_low_min));
                cJSON_AddItemToObject(x, "height_offset_high", j_num(off.height_offset_high));
                cJSON_AddItemToObject(x, "height_offset_low", j_num(off.height_offset_low));
                cJSON_AddItemToObject(x, "height_adjusted_type",
                                      j_enum(otc_height_adjusted_type_name(off.height_adjusted_type)));
                cJSON_AddItemToObject(x, "licence_id", j_cstr(off.licence_id));
                cJSON_AddItemToObject(o, "offsets", x);
            } else {
                cJSON_AddNullToObject(o, "offsets");
            }
        } else if (!strcmp(op, "recommended_set")) {
            const otc_set *set = NULL;
            rc = !st ? OTC_E_NOT_FOUND : fault("lookup") ? OTC_E_IO : otc_station_recommended_set(st, &set);
            if (rc == OTC_OK) cJSON_AddItemToObject(o, "set_id", s_set_id(set, &bad));
            else {
                if (rc != OTC_E_NOT_FOUND) bad = 1;
                cJSON_AddNullToObject(o, "set_id");
            }
        } else if (!strcmp(op, "constant_sets")) {
            bool inc = arg_bool(&q->a, "include_no_constants", false);
            cJSON *arr = st ? cJSON_CreateArray() : cJSON_CreateNull();
            size_t i, n = st ? otc_station_set_count(st, inc) : 0;
            if (q->a.bad) { cJSON_Delete(arr); otc_station_free(st); set_error(r, "invalid_argument", "include_no_constants"); return; }
            for (i = 0; i < n; i++) {
                const otc_set *set = NULL;
                if (otc_station_set_at(st, inc, i, &set) != OTC_OK) { bad = 1; break; }
                cJSON_AddItemToArray(arr, s_set_id(set, &bad));
            }
            cJSON_AddItemToObject(o, "set_ids", arr);
        } else if (!strcmp(op, "constant_set")) {
            const otc_set *set = find_set(q, st, &bad);
            if (set) cJSON_AddItemToObject(o, "set", enc_set(set, &bad));
            else cJSON_AddNullToObject(o, "set");
        } else if (!strcmp(op, "constituents")) {
            const otc_set *set = find_set(q, st, &bad);
            cJSON *arr = set ? cJSON_CreateArray() : cJSON_CreateNull();
            size_t i, n = set ? otc_set_constituent_count(set) : 0;
            for (i = 0; i < n; i++) {
                const otc_constituent_t *c = NULL;
                if (otc_set_constituent_at(set, i, &c) != OTC_OK) { bad = 1; break; }
                cJSON_AddItemToArray(arr, enc_constituent(c));
            }
            cJSON_AddItemToObject(o, "constituents", arr);
        } else if (!strcmp(op, "constituent")) {
            const otc_set *set = find_set(q, st, &bad);
            const char *name = arg_str(&q->a, "name");
            const otc_constituent_t *c = NULL;
            if (set && name && found(otc_set_constituent(set, name, &c), &bad))
                cJSON_AddItemToObject(o, "constituent", enc_constituent(c));
            else
                cJSON_AddNullToObject(o, "constituent");
        } else if (!strcmp(op, "provenance")) {
            const otc_set *set = find_set(q, st, &bad);
            if (set) {
                cJSON *p = cJSON_CreateObject();
                const otc_provenance_build *b = NULL;
                if (found(otc_set_provenance_build(set, &b), &bad)) {
                    cJSON *bo = cJSON_CreateObject();
                    cJSON_AddItemToObject(bo, "build_commit", s_build_commit(b, &bad));
                    cJSON_AddItemToObject(bo, "built_at", s_build_built_at(b, &bad));
                    cJSON_AddItemToObject(bo, "fetched_at", s_build_fetched_at(b, &bad));
                    cJSON_AddItemToObject(bo, "run_id", s_build_run_id(b, &bad));
                    cJSON_AddItemToObject(bo, "tool_versions", j_parse_or_null(s_build_tool_versions(b, &bad), &bad));
                    cJSON_AddItemToObject(p, "build", bo);
                } else {
                    cJSON_AddNullToObject(p, "build");
                }
                cJSON_AddItemToObject(p, "carried_from_release", s_prov_carried(set, &bad));
                cJSON_AddItemToObject(p, "adapter_version", s_prov_adapter_version(set, &bad));
                cJSON_AddItemToObject(p, "input_sha256", j_parse_or_null(s_prov_input_sha256(set, &bad), &bad));
                cJSON_AddItemToObject(p, "selection_reason", s_prov_selection_reason(set, &bad));
                cJSON_AddItemToObject(p, "decision", j_parse_or_null(s_prov_decision(set, &bad), &bad));
                cJSON_AddItemToObject(o, "provenance", p);
                cJSON_AddItemToObject(o, "raw", j_parse_or_null(s_set_prov_json(set, &bad), &bad));
            } else {
                cJSON_AddNullToObject(o, "provenance");
                cJSON_AddNullToObject(o, "raw");
            }
        } else if (!strcmp(op, "set_validation")) {
            const otc_set *set = find_set(q, st, &bad);
            cJSON *arr = set ? cJSON_CreateArray() : cJSON_CreateNull();
            size_t i, n = set ? otc_set_validation_count(set) : 0;
            for (i = 0; i < n; i++) {
                const otc_validation_t *v = NULL;
                if (otc_set_validation_at(set, i, &v) != OTC_OK) { bad = 1; break; }
                cJSON_AddItemToArray(arr, enc_validation(v));
            }
            cJSON_AddItemToObject(o, "validation", arr);
        } else if (!strcmp(op, "raw")) {
            const char *obj = arg_str(&q->a, "object");
            cJSON *raw = NULL;
            if (!obj) {
                otc_station_free(st);
                set_error(r, "invalid_argument", "object");
                return;
            } else if (!strcmp(obj, "station")) {
                if (st) raw = j_parse_or_null(s_st_raw(st, &bad), &bad);
            } else if (!strcmp(obj, "tombstone")) {
                otc_tombstone_t *t = NULL;
                const char *id = arg_str(&q->a, "station_id");
                if (id && found(otc_tombstone(R, id, &t), &bad)) {
                    raw = j_parse_or_null(s_tb_raw(t, &bad), &bad);
                    otc_tombstone_free(t);
                }
            } else if (!strcmp(obj, "set")) {
                const otc_set *set = find_set(q, st, &bad);
                if (set) raw = j_parse_or_null(s_set_raw(set, &bad), &bad);
            } else if (!strcmp(obj, "constituent")) {
                const otc_set *set = find_set(q, st, &bad);
                const char *name = arg_str(&q->a, "name");
                size_t i, n = set ? otc_set_constituent_count(set) : 0;
                for (i = 0; i < n && name; i++) {
                    const otc_constituent_t *c = NULL;
                    if (otc_set_constituent_at(set, i, &c) != OTC_OK) { bad = 1; break; }
                    if (!strcmp(c->name, name)) {
                        size_t need = 0;
                        char *buf;
                        if (otc_constituent_raw_json(set, i, NULL, 0, &need) != OTC_OK) { bad = 1; break; }
                        buf = (char *)malloc(need);
                        if (buf && otc_constituent_raw_json(set, i, buf, need, &need) == OTC_OK) raw = j_parse_or_null(buf, &bad);
                        else { free(buf); bad = 1; }
                        break;
                    }
                }
            } else if (!strcmp(obj, "convention")) {
                const otc_convention *c = NULL;
                const char *id = arg_str(&q->a, "convention_id");
                if (id && found(otc_release_convention(R, id, &c), &bad)) raw = j_parse_or_null(s_conv_raw(c, &bad), &bad);
            } else if (!strcmp(obj, "licence")) {
                const otc_licence *l = NULL;
                const char *id = arg_str(&q->a, "licence_id");
                if (id && found(otc_release_licence(R, id, &l), &bad)) raw = j_parse_or_null(s_lic_raw(l, &bad), &bad);
            } else {   /* README "raw": station, tombstone, set, constituent, convention or licence */
                otc_station_free(st);
                set_error(r, "uncaught:UnknownRawObject", obj);
                return;
            }
            cJSON_AddItemToObject(o, "raw", raw ? raw : cJSON_CreateNull());
        } else {
            otc_station_free(st);
            set_error(r, "uncaught:UnknownOp", op);
            return;
        }
        otc_station_free(st);
    }
    /* an argument read after the first check (set_id, name, ...) with the wrong type: never a null result */
    if (q->a.bad && !r->code) { set_error(r, "invalid_argument", "an argument has the wrong type"); return; }
    if (bad) set_error(r, "uncaught:BufferProtocol", "an accessor broke the buffer or list rules");
}

static cJSON *enc_release_info(const otc_release_info *ri, int *bad)
{
    cJSON *o = cJSON_CreateObject(), *files = cJSON_CreateArray();
    size_t i, n = otc_release_info_file_count(ri);
    cJSON_AddItemToObject(o, "datestamp", s_ri_datestamp(ri, bad));
    cJSON_AddItemToObject(o, "format_version", s_ri_format_version(ri, bad));
    cJSON_AddItemToObject(o, "concept_doi", s_ri_concept_doi(ri, bad));
    cJSON_AddItemToObject(o, "zenodo_version_doi", s_ri_zenodo_version_doi(ri, bad));
    cJSON_AddItemToObject(o, "content_sha256", s_ri_content_sha256(ri, bad));
    for (i = 0; i < n; i++) {
        const otc_file_info *fi = NULL;
        if (otc_release_info_file_at(ri, i, &fi) != OTC_OK) { *bad = 1; break; }
        cJSON_AddItemToArray(files, enc_file_info(fi, bad));
    }
    cJSON_AddItemToObject(o, "files", files);
    return o;
}

static const char *base_of(const char *p)
{
    const char *a = strrchr(p, '/'), *b = strrchr(p, '\\');
    const char *x = a > b ? a : b;
    return x ? x + 1 : p;
}

static int str_cmp(const void *a, const void *b) { return strcmp(*(const char *const *)a, *(const char *const *)b); }

/* A list of library strings as a JSON array (sorted when asked), freed with otc_free. */
static cJSON *take_strings(char **v, size_t n, int basenames, int sort)
{
    cJSON *arr = cJSON_CreateArray();
    size_t i;
    if (sort && n > 1) qsort(v, n, sizeof *v, str_cmp);
    for (i = 0; i < n; i++) {
        cJSON_AddItemToArray(arr, cJSON_CreateString(basenames ? base_of(v[i]) : v[i]));
        otc_free(v[i]);
    }
    return arr;
}

/*
 * The list calls of the fetch module hand over the entries they filled even when they fail (BUFFER_TOO_SMALL, and
 * prune's OTC_E_CACHE). The runner's arrays start zeroed, and every entry it was given is freed, so nothing leaks.
 */
static void free_strings(char **v, size_t cap)
{
    size_t i;
    for (i = 0; v && i < cap; i++)
        if (v[i]) { otc_free(v[i]); v[i] = NULL; }
}

static void free_infos(otc_release_info **v, size_t cap)
{
    size_t i;
    for (i = 0; v && i < cap; i++)
        if (v[i]) { otc_release_info_free(v[i]); v[i] = NULL; }
}

/* A read-only string list (cached_releases): BUFFER_TOO_SMALL is the runner's buffer, so it asks again with room for
 * *count entries. *v (malloc'd, cap *cap) holds the entries; the caller frees it. */
static otc_status list_strings(const otc_fetch_options *fo, char ***v, size_t *cap, size_t *count)
{
    otc_status rc;
    *cap = 256;
    for (;;) {
        *v = (char **)calloc(*cap, sizeof **v);
        if (!*v) return OTC_E_NOMEM;
        *count = 0;
        rc = otc_fetch_cached_releases(fo, *v, *cap, count);
        if (rc != OTC_E_BUFFER_TOO_SMALL || *count <= *cap) return rc;
        free_strings(*v, *cap);
        free(*v);
        *cap = *count;
    }
}

/* Swaps the current release for datestamp ds (a Release held from before stays open). */
static otc_status swap_to(const char *ds, otc_error *err)
{
    otc_fetch_options fo;
    otc_open_options oo;
    otc_release *rel = NULL;
    otc_status rc;
    char *path;
    fetch_options(&fo, err);   /* the caller's error struct: the detail of a failed open reaches the reply */
    open_options(&oo, err);
    rc = otc_fetch_open(&fo, fault("swap") ? "20000101" : ds, &oo, &rel);   /* fault: the open fails */
    if (rc != OTC_OK) return rc;
    path = current_jsonl_path(ds, OTC_OK);
    if (g_current && !is_held(g_current)) otc_close(g_current);
    free(g_current_path);
    g_current = rel;
    g_current_path = path;
    return OTC_OK;
}

/* A check (latest, check_for_update, update, an automatic update) reached the latest pointer: the client's
 * last_error is null from now on, and loaded_from does not change (spec 4.3, CR2 DR4). */
static void pointer_reached(void)
{
    g_client.auto_update_status = OTC_OK;
    g_client.auto_update_nomove = 0;
    g_client.pointer_reached = 1;
}

/* otc_fetch_update, then the new release replaces the current one (spec 4.3 "update"). *nomove is set when the
 * library says it updated but the runner cannot find a new datestamp in the path it got (never "updated" then). */
static otc_status do_update(const char *from, int *updated, char *to, size_t to_len, otc_error *err, int *nomove)
{
    otc_fetch_options fo;
    char path[4096];
    bool up = false;
    otc_status rc;
    fetch_options(&fo, err);
    *updated = 0;
    *nomove = 0;
    snprintf(to, to_len, "%s", from);
    rc = otc_fetch_update(&fo, from, path, sizeof path, NULL, &up);
    if (rc != OTC_OK || !up) return rc;
    if (fault("update-path")) snprintf(path, sizeof path, "%s", "/no/such/file.bin");   /* fault: an odd path */
    {   /* the datestamp of the new file: OTC_{D}.jsonl */
        const char *b = base_of(path);
        size_t n = strlen(b);
        if (n > 10 && !strncmp(b, "OTC_", 4) && !strcmp(b + n - 6, ".jsonl")) snprintf(to, to_len, "%.*s", (int)(n - 10), b + 4);
    }
    if (!strcmp(to, from)) {
        /* the path is cut to fit the message (gcc's -Wformat-truncation: path can be longer than the message) */
        snprintf(err->message, sizeof err->message, "otc_fetch_update reported an update to %.256s, which names no newer release",
                 path);
        *nomove = 1;
        return OTC_OK;
    }
    rc = swap_to(to, err);
    if (rc == OTC_OK) {
        *updated = 1;
        g_client.auto_update_status = OTC_OK;   /* the current release is the new one: no failure to report */
        g_client.auto_update_nomove = 0;
    }
    return rc;
}

/* The fetch module's ops (spec 4.3). In a build without otc_fetch they return OTC_E_NOT_BUILT. */
static void op_fetch(request *q, reply *r)
{
    otc_fetch_options fo;
    otc_error err;
    otc_status rc;
    char ds[64];
    size_t need = 0, count = 0;
    int bad = 0;
    fetch_options(&fo, &err);
    if (otc_release_datestamp(q->rel, ds, sizeof ds, &need) != OTC_OK) ds[0] = '\0';
    r->result = cJSON_CreateObject();
    if (!strcmp(q->op, "newer_format_major")) {
        /* spec 7.4: the major that the last otc_fetch_check_for_update found, or null */
        int major = 0;
        rc = otc_fetch_newer_format_major(&fo, &major);
        if (rc == OTC_OK) cJSON_AddNumberToObject(r->result, "newer_format_major", major);
        else if (rc == OTC_E_NOT_FOUND) cJSON_AddNullToObject(r->result, "newer_format_major");
        else set_error_struct(r, rc, &err);
        return;
    }
    if (!strcmp(q->op, "releases")) {
        /* read-only: BUFFER_TOO_SMALL is the runner's buffer, never the SDK's answer, so it asks again with room for
         * every release; the entries handed over with BUFFER_TOO_SMALL are freed first */
        otc_release_info **v = NULL;
        cJSON *arr = cJSON_CreateArray();
        size_t i, cap = 256;
        for (;;) {
            v = (otc_release_info **)calloc(cap, sizeof *v);
            if (!v) { rc = OTC_E_NOMEM; break; }
            count = 0;
            rc = otc_fetch_releases(&fo, v, cap, &count);
            if (rc != OTC_E_BUFFER_TOO_SMALL || count <= cap) break;
            free_infos(v, cap);
            free(v);
            v = NULL;
            cap = count;
        }
        for (i = 0; rc == OTC_OK && i < count; i++) cJSON_AddItemToArray(arr, enc_release_info(v[i], &bad));
        free_infos(v, cap);
        free(v);
        cJSON_AddItemToObject(r->result, "releases", arr);
        if (rc == OTC_E_NOMEM || rc == OTC_E_BUFFER_TOO_SMALL) {   /* no memory, or a too-small answer that fits */
            set_error(r, rc == OTC_E_NOMEM ? "uncaught:NoMemory" : "uncaught:BufferProtocol", "releases: the list call");
            return;
        }
    } else if (!strcmp(q->op, "latest") || !strcmp(q->op, "check_for_update")) {
        otc_release_info *ri = NULL;
        bool found = true;
        if (!strcmp(q->op, "latest")) rc = otc_fetch_latest_info(&fo, &ri);
        else rc = otc_fetch_check_for_update(&fo, ds, &ri, &found);
        if (rc == OTC_OK) pointer_reached();
        cJSON_AddItemToObject(r->result, "release", rc == OTC_OK && found && ri ? enc_release_info(ri, &bad) : cJSON_CreateNull());
        otc_release_info_free(ri);
    } else if (!strcmp(q->op, "update")) {
        char to[64];
        int updated = 0;
        if (g_client.pinned && OTC_RUNNER_FETCH) {   /* without the module: otc_fetch_update says not_built */
            set_error(r, "pinned_release", "update: the client was opened on a pinned release or a file");
            return;
        }
        int nomove = 0;
        rc = do_update(ds, &updated, to, sizeof to, &err, &nomove);
        if (nomove) { set_error(r, "uncaught:UpdateNoMove", err.message); return; }
        cJSON_AddBoolToObject(r->result, "updated", updated);
        cJSON_AddStringToObject(r->result, "from", ds);
        cJSON_AddStringToObject(r->result, "to", to);
        if (rc == OTC_OK) {
            g_client.last_check = now_s();
            pointer_reached();
        }
    } else if (!strcmp(q->op, "download")) {
        const char *to = arg_str(&q->a, "to"), *release = arg_str(&q->a, "release");
        const cJSON *fmts = q->a.obj ? cJSON_GetObjectItemCaseSensitive(q->a.obj, "formats") : NULL, *f;
        /* absent or null: OTC_FORMATS_DEFAULT; a list, [] included, goes to the library as its bits, so [] is 0 and the
         * library judges it (CR 4c) */
        unsigned formats = OTC_FORMATS_DEFAULT;
        char *paths[16] = {0};
        bool overwrite = arg_bool(&q->a, "overwrite", false);
        if (fmts && !cJSON_IsNull(fmts)) {
            formats = 0;
            if (!cJSON_IsArray(fmts)) q->a.bad = 1;
            cJSON_ArrayForEach(f, fmts) {
                if (!cJSON_IsString(f)) q->a.bad = 1;
                else if (!strcmp(f->valuestring, "json")) formats |= OTC_FORMAT_JSON;
                else if (!strcmp(f->valuestring, "json.gz")) formats |= OTC_FORMAT_JSON_GZ;
                else if (!strcmp(f->valuestring, "jsonl")) formats |= OTC_FORMAT_JSONL;
                else formats |= OTC_FORMAT_OTHER;   /* the library rejects it: invalid_argument */
            }
        }
        if (q->a.bad) { set_error(r, "invalid_argument", "download: an argument has the wrong type"); return; }
        rc = otc_fetch_to_dir(&fo, release, to, formats, overwrite, paths, 16, &count);
        if (rc == OTC_OK) cJSON_AddItemToObject(r->result, "paths", take_strings(paths, count, 1, 1));
        else free_strings(paths, 16);
        if (rc == OTC_E_BUFFER_TOO_SMALL) {   /* the files are written and the call cannot be repeated: a runner failure */
            set_error(r, "uncaught:ListTooSmall", "download: the runner's list of 16 paths is too small");
            return;
        }
    } else if (!strcmp(q->op, "cached_releases")) {
        char **v = NULL;
        size_t cap = 0;
        rc = list_strings(&fo, &v, &cap, &count);
        if (rc == OTC_OK) cJSON_AddItemToObject(r->result, "datestamps", take_strings(v, count, 0, 0));
        else free_strings(v, cap);
        free(v);
        if (rc == OTC_E_NOMEM || rc == OTC_E_BUFFER_TOO_SMALL) {
            set_error(r, rc == OTC_E_NOMEM ? "uncaught:NoMemory" : "uncaught:BufferProtocol", "cached_releases: the list call");
            return;
        }
    } else {
        char *v[256] = {0};
        double keep = arg_num(&q->a, "keep", 3);
        if (q->a.bad || keep < 0 || keep != floor(keep)) {
            /* size_t keep cannot be negative or fractional: the type is wrong for C (README, Argument rules) */
            set_error(r, "invalid_argument", "prune: keep must be a non-negative integer");
            return;
        }
        rc = otc_fetch_prune(&fo, (size_t)keep, ds[0] ? ds : NULL, v, 256, &count);
        if (rc == OTC_OK) cJSON_AddItemToObject(r->result, "removed", take_strings(v, count, 0, 0));
        else if (rc == OTC_E_CACHE) {
            /* CR2 DR18: a failed prune reports the releases removed before the failure in the array and count */
            size_t n = count < 256 ? count : 256, i;
            set_error_struct(r, rc, &err);
            cJSON_AddItemToObject(r->fields, "removed", take_strings(v, n, 0, 0));
            for (i = 0; i < n; i++) v[i] = NULL;   /* taken (and freed) above */
            free_strings(v, 256);
            return;
        }
        else free_strings(v, 256);
        if (rc == OTC_E_BUFFER_TOO_SMALL) {   /* the releases are removed and the call cannot be repeated */
            set_error(r, "uncaught:ListTooSmall", "prune: the runner's list of 256 datestamps is too small");
            return;
        }
    }
    if (rc != OTC_OK) { set_error_struct(r, rc, &err); return; }
    if (bad) set_error(r, "uncaught:BufferProtocol", "an accessor broke the buffer or list rules");
}

/* auto_update (spec 5.6), as the app does it in C: before the first query after the interval. */
static void maybe_auto_update(void)
{
    char ds[64], to[64];
    size_t need;
    int updated, nomove = 0;
    otc_error err;
    otc_status rc;
    double now;
    if (!g_client.auto_update || g_client.pinned || !g_current) return;
    now = now_s();
    if (now - g_client.last_check < g_client.update_interval) return;
    g_client.last_check = now;
    rc = otc_release_datestamp(g_current, ds, sizeof ds, &need);
    if (rc != OTC_OK) {
        /* the check cannot run: never a silent skip; the failure is the client's last_error, as below */
        g_client.auto_update_status = rc;
        fprintf(stderr, "automatic update failed: otc_release_datestamp: %s\n", otc_status_code(rc));
        return;
    }
    rc = do_update(ds, &updated, to, sizeof to, &err, &nomove);
    /* offline (the option or OPENTIDECONSTANTS_OFFLINE, which the library reads) the check does not run (spec 5.6) */
    if (rc == OTC_E_OFFLINE_UNAVAILABLE) return;
    if (rc == OTC_OK && !nomove) pointer_reached();
    if (rc != OTC_OK || nomove) {
        /* keep the current release; the failure is the client's last_error, as in the other SDKs (C69) */
        if (nomove) g_client.auto_update_nomove = 1;
        else g_client.auto_update_status = rc;
        fprintf(stderr, "automatic update failed: %s\n", err.message);
    }
}

static int is_fetch_op(const char *op)
{
    static const char *const ops[] = {"releases", "latest", "check_for_update", "newer_format_major", "update", "download",
                                      "cached_releases", "prune", NULL};
    size_t i;
    for (i = 0; ops[i]; i++)
        if (!strcmp(ops[i], op)) return 1;
    return 0;
}

/* Runs one op on the request's release; returns the reply line (malloc'd). */
static char *run_query(request *q)
{
    reply r;
    memset(&r, 0, sizeof r);
    if (!q->rel) set_error(&r, "uncaught:NoRelease", "no release is open");
    else if (is_fetch_op(q->op)) op_fetch(q, &r);
    else if (!strcmp(q->op, "verify")) op_verify(q, &r);
    else op_query(q, &r);
    return render(&r);
}

/* ---------------------------------------------------------------- threads */

typedef struct thread_job {
    request q;      /* each thread has its own copy (args.bad is written per call) */
    char *out;
    int index;
} thread_job;

static void thread_run(thread_job *j)
{
    j->out = run_query(&j->q);
    if (j->index == 0 && fault("thread0-null")) { cJSON_free(j->out); j->out = NULL; }   /* a thread with no reply */
}

#ifdef _WIN32
static DWORD WINAPI thread_main(LPVOID p)
{
    thread_run((thread_job *)p);
    return 0;
}
#else
static void *thread_main(void *p)
{
    thread_run((thread_job *)p);
    return NULL;
}
#endif

static char *run_threaded(request *q, int n)
{
    thread_job *jobs = (thread_job *)calloc((size_t)n, sizeof *jobs);
    char *first = NULL;
    int i, same = 1, started = 0;
#ifdef _WIN32
    HANDLE *th = (HANDLE *)calloc((size_t)n, sizeof *th);
#else
    pthread_t *th = (pthread_t *)calloc((size_t)n, sizeof *th);
#endif
    if (!jobs || !th) {   /* never a quiet single-thread run: the multi-thread check (spec 6.4) would not happen */
        reply r;
        free(jobs);
        free(th);
        memset(&r, 0, sizeof r);
        set_error(&r, "uncaught:ThreadStart", "out of memory for the thread jobs");
        return render(&r);
    }
    for (i = 0; i < n; i++) {
        jobs[i].q = *q;
        jobs[i].index = i;
#ifdef _WIN32
        th[i] = CreateThread(NULL, 0, thread_main, &jobs[i], 0, NULL);
        if (!th[i]) break;
#else
        if (pthread_create(&th[i], NULL, thread_main, &jobs[i]) != 0) break;
#endif
        started++;
    }
    for (i = 0; i < started; i++) {
#ifdef _WIN32
        WaitForSingleObject(th[i], INFINITE);
        CloseHandle(th[i]);
#else
        pthread_join(th[i], NULL);
#endif
    }
    for (i = 0; i < started; i++) {   /* every thread must give a reply, and all must be the same */
        if (!jobs[i].out) same = 0;
        else if (!first) first = jobs[i].out;
        else if (strcmp(first, jobs[i].out) != 0) same = 0;
    }
    for (i = 0; i < started; i++)
        if (jobs[i].out != first) cJSON_free(jobs[i].out);
    free(jobs);
    free(th);
    if (started != n || !same) {
        reply r;
        memset(&r, 0, sizeof r);
        set_error(&r, started != n ? "uncaught:ThreadStart" : "uncaught:ThreadMismatch",
                  "the threads did not all give the same reply");
        cJSON_free(first);
        return render(&r);
    }
    return first;
}

/* ------------------------------------------------------------------ main */

/* One request line into *out (malloc'd). Returns 1 for a line, 0 at the end of input, and -1 when there is no memory
 * for the line: the rest of the line is read and dropped, so the caller can still answer it (never a clean EOF). */
static int read_line(FILE *f, char **out)
{
    size_t cap = 4096, n = 0;
    char *buf = (char *)malloc(cap);
    int c = 0, nomem = !buf;
    *out = NULL;
    while ((c = fgetc(f)) != EOF) {
        if (c == '\n') break;
        if (nomem) continue;
        if (n + 1 >= cap) {
            char *nb = (char *)realloc(buf, cap * 2);
            if (!nb) { free(buf); buf = NULL; nomem = 1; continue; }
            buf = nb;
            cap *= 2;
        }
        buf[n++] = (char)c;
    }
    if (nomem) return -1;
    if (c == EOF && n == 0) { free(buf); return 0; }
    buf[n] = '\0';
    *out = buf;
    return 1;
}

static char *handle(const char *line, int threads)
{
    cJSON *req = cJSON_Parse(line);
    const cJSON *op, *on;
    request q;
    reply r;
    char *out;
    memset(&r, 0, sizeof r);
    memset(&q, 0, sizeof q);
    if (!req) {
        set_error(&r, "uncaught:BadRequest", "the request is not JSON");
        return render(&r);
    }
    op = cJSON_GetObjectItemCaseSensitive(req, "op");
    on = cJSON_GetObjectItemCaseSensitive(req, "on");
    q.op = cJSON_IsString(op) ? op->valuestring : "";
    q.a.obj = cJSON_GetObjectItemCaseSensitive(req, "args");
    q.rel = g_current;
    q.path = g_current_path;
    if (cJSON_IsString(on)) {
        size_t i;
        q.rel = NULL;
        for (i = 0; i < g_n_held; i++)
            if (!strcmp(g_held[i].name, on->valuestring)) { q.rel = g_held[i].rel; q.path = g_held[i].path; }
    }
    if (!strcmp(q.op, "open")) {
        op_open(&q, &r);
        out = render(&r);
    } else if (!strcmp(q.op, "close")) {
        close_current();
        out = render(&r);
    } else if (!strcmp(q.op, "hold_release")) {
        const char *name = arg_str(&q.a, "name");
        /* runner failures, not SDK error codes: a case must not pass on them */
        if (!g_current) set_error(&r, "uncaught:NoRelease", "hold_release: no release is open");
        else if (!name) set_error(&r, "uncaught:BadRequest", "hold_release needs a name");
        else if (g_n_held >= MAX_HELD) set_error(&r, "uncaught:TooManyHeld", "hold_release: too many held releases");
        else {
            g_held[g_n_held].name = xstrdup(name);
            g_held[g_n_held].rel = g_current;
            g_held[g_n_held].path = xstrdup(g_current_path);
            g_n_held++;
        }
        out = render(&r);
    } else {
        if (!cJSON_IsString(on)) {
            maybe_auto_update();
            q.rel = g_current;
            q.path = g_current_path;
        }
        /* fetch ops change the cache or the current release: one thread */
        if (threads > 1 && q.rel && !is_fetch_op(q.op)) out = run_threaded(&q, threads);
        else out = run_query(&q);
    }
    (void)has_arg;
    cJSON_Delete(req);
    return out;
}

int main(void)
{
    char *line;
    int got;
    const char *t = getenv("OTC_RUNNER_THREADS");
    int threads = t ? atoi(t) : 1;
    size_t i;
    g_fault = getenv("OTC_RUNNER_FAULT");
    printf("{\"hello\": {\"runner\": \"%s\", \"version\": \"%s\", \"features\": [%s]}}\n",
           OTC_RUNNER_FETCH ? "c-fetch" : "c", OTC_VERSION,
           OTC_RUNNER_FETCH ? "\"fs\", \"fetch\", \"stream\", \"require_checksum\", \"https_proxy\""
                            : "\"fs\", \"stream\", \"require_checksum\"");
    fflush(stdout);
    while ((got = read_line(stdin, &line)) != 0) {
        char *out;
        if (got < 0) {   /* no memory for the line: it still gets a reply, and the runner goes on */
            fputs("{\"ok\": false, \"error\": {\"code\": \"uncaught:NoMemory\", \"message\": \"no memory for the request line\"}}\n",
                  stdout);
            fflush(stdout);
            continue;
        }
        if (!line[0]) { free(line); continue; }
        out = handle(line, threads);
        free(line);
        fputs(out ? out : "{\"ok\": false, \"error\": {\"code\": \"uncaught:NoMemory\", \"message\": \"\"}}", stdout);
        fputc('\n', stdout);
        fflush(stdout);
        cJSON_free(out);
    }
    close_current();
    for (i = 0; i < g_n_held; i++) {
        size_t j;
        int dup = 0;
        for (j = 0; j < i; j++) if (g_held[j].rel == g_held[i].rel) dup = 1;
        if (!dup) otc_close(g_held[i].rel);
        free(g_held[i].name);
        free(g_held[i].path);
    }
    client_free();
    return 0;
}
