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

#ifdef _WIN32
#include <windows.h>
#else
#include <pthread.h>
#endif

#ifndef OTC_RUNNER_FETCH
#define OTC_RUNNER_FETCH 0
#endif

/* ------------------------------------------------------------------ state */

#define MAX_HELD 16
static otc_release *g_current;
static char *g_current_path;
static struct { char *name; otc_release *rel; char *path; } g_held[MAX_HELD];
static size_t g_n_held;

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

static cJSON *j_parse_or_null(char *text)
{
    cJSON *v = NULL;
    if (text) {
        v = cJSON_Parse(text);
        free(text);
    }
    return v ? v : cJSON_CreateNull();
}

/*
 * A string accessor called the way an app calls it: first into a small
 * buffer (which checks OTC_E_BUFFER_TOO_SMALL and NUL termination), then
 * into a buffer of the reported size. Returns a malloc'd string, or NULL for
 * "no value" (OTC_E_NOT_FOUND). *bad is set on any other status.
 */
#define DEF_STR(NAME, FN, T)                                                      \
    static char *NAME(const T *o, int *bad)                                       \
    {                                                                             \
        char small[4];                                                            \
        size_t need = 0, need2 = 0;                                               \
        char *buf;                                                                \
        otc_status rc = FN(o, small, sizeof small, &need);                        \
        if (rc == OTC_E_NOT_FOUND) return NULL;                                   \
        if (rc == OTC_OK) {                                                       \
            if (strlen(small) + 1 != need) { *bad = 1; return NULL; }             \
            return xstrdup(small);                                                \
        }                                                                         \
        if (rc != OTC_E_BUFFER_TOO_SMALL || need <= sizeof small                  \
            || small[sizeof small - 1] != '\0') { *bad = 1; return NULL; }        \
        if (FN(o, NULL, 0, &need2) != OTC_OK || need2 != need) {                 \
            *bad = 1; return NULL;                                                \
        }                                                                         \
        buf = (char *)malloc(need);                                               \
        if (!buf) { *bad = 1; return NULL; }                                      \
        if (FN(o, buf, need, &need2) != OTC_OK || strlen(buf) + 1 != need) {      \
            free(buf); *bad = 1; return NULL;                                     \
        }                                                                         \
        return buf;                                                               \
    }

DEF_STR(s_rel_datestamp, otc_release_datestamp, otc_release)
DEF_STR(s_rel_created, otc_release_created, otc_release)
DEF_STR(s_rel_format_version, otc_release_format_version, otc_release)
DEF_STR(s_rel_doi, otc_release_doi, otc_release)
DEF_STR(s_rel_concept_doi, otc_release_concept_doi, otc_release)
DEF_STR(s_rel_build_commit, otc_release_build_commit, otc_release)
DEF_STR(s_rel_changelog_url, otc_release_changelog_url, otc_release)
DEF_STR(s_rel_citation, otc_release_citation, otc_release)
DEF_STR(s_fi_name, otc_file_info_name, otc_file_info)
DEF_STR(s_fi_url, otc_file_info_url, otc_file_info)
DEF_STR(s_fi_sha256, otc_file_info_sha256, otc_file_info)
DEF_STR(s_conv_id, otc_convention_convention_id, otc_convention)
DEF_STR(s_conv_v0, otc_convention_v0_model, otc_convention)
DEF_STR(s_conv_nodal_ids, otc_convention_nodal_formula_ids_json, otc_convention)
DEF_STR(s_conv_table_version, otc_convention_constituent_table_version, otc_convention)
DEF_STR(s_conv_tables_sha, otc_convention_tables_sha256, otc_convention)
DEF_STR(s_conv_canary, otc_convention_canary_json, otc_convention)
DEF_STR(s_conv_raw, otc_convention_raw_json, otc_convention)
DEF_STR(s_lic_id, otc_licence_licence_id, otc_licence)
DEF_STR(s_lic_spdx, otc_licence_spdx, otc_licence)
DEF_STR(s_lic_provider, otc_licence_provider, otc_licence)
DEF_STR(s_lic_citation, otc_licence_citation, otc_licence)
DEF_STR(s_lic_attribution, otc_licence_attribution, otc_licence)
DEF_STR(s_lic_url, otc_licence_url, otc_licence)
DEF_STR(s_lic_raw, otc_licence_raw_json, otc_licence)
DEF_STR(s_st_id, otc_station_station_id, otc_station_t)
DEF_STR(s_st_name, otc_station_name, otc_station_t)
DEF_STR(s_st_country, otc_station_country, otc_station_t)
DEF_STR(s_st_timezone, otc_station_timezone, otc_station_t)
DEF_STR(s_st_raw, otc_station_raw_json, otc_station_t)
DEF_STR(s_tb_id, otc_tombstone_station_id, otc_tombstone_t)
DEF_STR(s_tb_name, otc_tombstone_name, otc_tombstone_t)
DEF_STR(s_tb_removed_in, otc_tombstone_removed_in, otc_tombstone_t)
DEF_STR(s_tb_removed_reason, otc_tombstone_removed_reason, otc_tombstone_t)
DEF_STR(s_tb_raw, otc_tombstone_raw_json, otc_tombstone_t)
DEF_STR(s_set_id, otc_set_set_id, otc_set)
DEF_STR(s_set_source, otc_set_source, otc_set)
DEF_STR(s_set_record_id, otc_set_source_record_id, otc_set)
DEF_STR(s_set_version, otc_set_source_version, otc_set)
DEF_STR(s_set_raw, otc_set_raw_json, otc_set)
DEF_STR(s_set_prov_json, otc_set_provenance_json, otc_set)
DEF_STR(s_prov_build_commit, otc_set_provenance_build_commit, otc_set)
DEF_STR(s_prov_adapter_version, otc_set_provenance_adapter_version, otc_set)
DEF_STR(s_prov_input_sha256, otc_set_provenance_input_sha256_json, otc_set)
DEF_STR(s_prov_time_base, otc_set_provenance_time_base_json, otc_set)
DEF_STR(s_prov_selection_reason, otc_set_provenance_selection_reason, otc_set)
DEF_STR(s_prov_decision, otc_set_provenance_decision_json, otc_set)
DEF_STR(s_span_start, otc_record_span_start, otc_record_span)
DEF_STR(s_span_end, otc_record_span_end, otc_record_span)
DEF_STR(s_flag_verdict, otc_qc_flag_verdict, otc_qc_flag)
DEF_STR(s_flag_values, otc_qc_flag_values_json, otc_qc_flag)
DEF_STR(s_drop_name, otc_dropped_name, otc_dropped)
DEF_STR(s_drop_detail, otc_dropped_detail, otc_dropped)

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
    cJSON_AddItemToObject(o, "station_id", j_take(s_st_id(st, bad)));
    cJSON_AddItemToObject(o, "name", j_take(s_st_name(st, bad)));
    cJSON_AddItemToObject(o, "country", j_take(s_st_country(st, bad)));
    cJSON_AddItemToObject(o, "lat", j_num(otc_station_lat(st)));
    cJSON_AddItemToObject(o, "lon", j_num(otc_station_lon(st)));
    cJSON_AddItemToObject(o, "type", j_enum(otc_station_type_name(otc_station_type(st))));
    cJSON_AddItemToObject(o, "kind", j_enum(otc_kind_name(otc_station_kind(st))));
    cJSON_AddItemToObject(o, "timezone", j_take(s_st_timezone(st, bad)));
    ns = otc_station_alias_system_count(st);
    for (i = 0; i < ns; i++) {
        char sys[256], id[1024];
        size_t need, n;
        cJSON *arr = cJSON_CreateArray();
        if (otc_station_alias_system_at(st, i, sys, sizeof sys, &need) != OTC_OK) { *bad = 1; break; }
        n = otc_station_alias_count(st, sys);
        for (j = 0; j < n; j++) {
            if (otc_station_alias_at(st, sys, j, id, sizeof id, &need) != OTC_OK) { *bad = 1; break; }
            cJSON_AddItemToArray(arr, cJSON_CreateString(id));
        }
        cJSON_AddItemToObject(aliases, sys, arr);
    }
    cJSON_AddItemToObject(o, "aliases", aliases);
    cJSON_AddItemToObject(o, "status", j_enum(otc_station_status_name(otc_station_status(st))));
    cJSON_AddBoolToObject(o, "is_reference", otc_station_is_reference(st));
    cJSON_AddBoolToObject(o, "is_subordinate", otc_station_is_subordinate(st));
    cJSON_AddBoolToObject(o, "is_tide", otc_station_is_tide(st));
    cJSON_AddBoolToObject(o, "is_current", otc_station_is_current(st));
    if (otc_station_recommended_set(st, &rec) == OTC_OK)
        cJSON_AddItemToObject(o, "recommended_set_id", j_take(s_set_id(rec, bad)));
    else
        cJSON_AddNullToObject(o, "recommended_set_id");
    return o;
}

static cJSON *enc_tombstone(const otc_tombstone_t *t, int *bad)
{
    cJSON *o = cJSON_CreateObject();
    cJSON_AddItemToObject(o, "station_id", j_take(s_tb_id(t, bad)));
    cJSON_AddItemToObject(o, "name", j_take(s_tb_name(t, bad)));
    cJSON_AddItemToObject(o, "status", j_enum(otc_station_status_name(otc_tombstone_status(t))));
    cJSON_AddItemToObject(o, "removed_in", j_take(s_tb_removed_in(t, bad)));
    cJSON_AddItemToObject(o, "removed_reason", j_take(s_tb_removed_reason(t, bad)));
    return o;
}

static cJSON *enc_set(const otc_set *set, int *bad)
{
    cJSON *o = cJSON_CreateObject(), *flags = cJSON_CreateArray(), *drops = cJSON_CreateArray();
    const otc_record_span *rs = NULL;
    const otc_datum *dt = NULL;
    const otc_convention *conv = NULL;
    const otc_licence *lic = NULL;
    size_t i, n;
    cJSON_AddItemToObject(o, "set_id", j_take(s_set_id(set, bad)));
    cJSON_AddItemToObject(o, "source", j_take(s_set_source(set, bad)));
    cJSON_AddItemToObject(o, "source_type", j_enum(otc_source_type_name(otc_set_source_type(set))));
    cJSON_AddItemToObject(o, "quantity", j_enum(otc_quantity_name(otc_set_quantity(set))));
    cJSON_AddItemToObject(o, "source_record_id", j_take(s_set_record_id(set, bad)));
    cJSON_AddItemToObject(o, "source_version", j_take(s_set_version(set, bad)));
    if (otc_set_record_span(set, &rs) == OTC_OK) {
        cJSON *s = cJSON_CreateObject();
        cJSON_AddItemToObject(s, "start", j_take(s_span_start(rs, bad)));
        cJSON_AddItemToObject(s, "end", j_take(s_span_end(rs, bad)));
        cJSON_AddItemToObject(s, "good_samples", j_count(otc_record_span_good_samples(rs)));
        cJSON_AddItemToObject(o, "record_span", s);
    } else {
        cJSON_AddNullToObject(o, "record_span");
    }
    if (otc_set_datum(set, &dt) == OTC_OK) {
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
        cJSON_AddItemToObject(fo, "verdict", j_take(s_flag_verdict(f, bad)));
        cJSON_AddItemToObject(fo, "values", j_parse_or_null(s_flag_values(f, bad)));
        cJSON_AddItemToArray(flags, fo);
    }
    cJSON_AddItemToObject(o, "qc_flags", flags);
    n = otc_set_dropped_count(set);
    for (i = 0; i < n; i++) {
        const otc_dropped *d = NULL;
        cJSON *dobj = cJSON_CreateObject();
        if (otc_set_dropped_at(set, i, &d) != OTC_OK) { *bad = 1; cJSON_Delete(dobj); break; }
        cJSON_AddItemToObject(dobj, "name", j_take(s_drop_name(d, bad)));
        cJSON_AddItemToObject(dobj, "dropped_reason", j_enum(otc_dropped_reason_name(otc_dropped_dropped_reason(d))));
        cJSON_AddItemToObject(dobj, "detail", j_take(s_drop_detail(d, bad)));
        cJSON_AddItemToArray(drops, dobj);
    }
    cJSON_AddItemToObject(o, "dropped_constituents", drops);
    cJSON_AddBoolToObject(o, "is_recommended", otc_set_is_recommended(set));
    if (otc_set_convention(set, &conv) == OTC_OK) cJSON_AddItemToObject(o, "convention_id", j_take(s_conv_id(conv, bad)));
    else cJSON_AddNullToObject(o, "convention_id");
    if (otc_set_licence(set, &lic) == OTC_OK) cJSON_AddItemToObject(o, "licence_id", j_take(s_lic_id(lic, bad)));
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
    cJSON_AddItemToObject(o, "convention_id", j_take(s_conv_id(c, bad)));
    cJSON_AddItemToObject(o, "phase_reference", j_enum(otc_phase_reference_name(otc_convention_phase_reference(c))));
    cJSON_AddItemToObject(o, "utc_offset_hours", j_num(otc_convention_utc_offset_hours(c)));
    cJSON_AddItemToObject(o, "v0_model", j_take(s_conv_v0(c, bad)));
    cJSON_AddItemToObject(o, "nodal_handling", j_enum(otc_nodal_handling_name(otc_convention_nodal_handling(c))));
    cJSON_AddItemToObject(o, "nodal_formula_ids", j_parse_or_null(s_conv_nodal_ids(c, bad)));
    cJSON_AddItemToObject(o, "constituent_table_version", j_take(s_conv_table_version(c, bad)));
    cJSON_AddItemToObject(o, "tables_sha256", j_take(s_conv_tables_sha(c, bad)));
    cJSON_AddItemToObject(o, "canary", j_parse_or_null(s_conv_canary(c, bad)));
    return o;
}

static cJSON *enc_licence(const otc_licence *l, int *bad)
{
    cJSON *o = cJSON_CreateObject();
    cJSON_AddItemToObject(o, "licence_id", j_take(s_lic_id(l, bad)));
    cJSON_AddItemToObject(o, "spdx", j_take(s_lic_spdx(l, bad)));
    cJSON_AddItemToObject(o, "provider", j_take(s_lic_provider(l, bad)));
    cJSON_AddItemToObject(o, "citation", j_take(s_lic_citation(l, bad)));
    cJSON_AddItemToObject(o, "attribution", j_take(s_lic_attribution(l, bad)));
    cJSON_AddItemToObject(o, "url", j_take(s_lic_url(l, bad)));
    return o;
}

static cJSON *enc_file_info(const otc_file_info *fi, int *bad)
{
    cJSON *o = cJSON_CreateObject();
    cJSON_AddItemToObject(o, "name", j_take(s_fi_name(fi, bad)));
    cJSON_AddItemToObject(o, "url", j_take(s_fi_url(fi, bad)));
    cJSON_AddItemToObject(o, "size", j_count(otc_file_info_size(fi)));
    cJSON_AddItemToObject(o, "sha256", j_take(s_fi_sha256(fi, bad)));
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

static size_t arg_limit(args *a, const char *name)
{
    double v = arg_num(a, name, 0.0);
    if (v < 0 || v != floor(v)) { a->bad = 1; return 0; }
    return (size_t)v;
}

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
            ITEMS = (TYPE *)calloc(cap_ ? cap_ : 1, sizeof(TYPE));                \
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

static const otc_set *find_set(request *q, const otc_station_t *st)
{
    const char *set_id = arg_str(&q->a, "set_id");
    const otc_set *set = NULL;
    if (!st || !set_id) return NULL;
    if (otc_station_set(st, set_id, &set) != OTC_OK) return NULL;
    return set;
}

static void op_open(request *q, reply *r)
{
    const char *file = arg_str(&q->a, "file");
    otc_error err;
    otc_status rc;
    if (q->a.bad) { set_error(r, "invalid_argument", "file must be a string"); return; }
    close_current();
    otc_error_init(&err);
    if (file) {
        otc_open_options opts;
        otc_release *rel = NULL;
        otc_open_options_init(&opts);
        opts.error = &err;
        rc = otc_open_file(file, &opts, &rel);
        if (rc != OTC_OK) { set_error_struct(r, rc, &err); return; }
        g_current = rel;
        g_current_path = xstrdup(file);
    } else {
        /* No file: the release comes from the otc_fetch module (download or cache). */
        otc_fetch_options fo;
        const char *release = arg_str(&q->a, "release");
        char path[4096];
        size_t need = 0;
        otc_fetch_options_init(&fo);
        fo.error = &err;
        fo.base_url = arg_str(&q->a, "base_url");
        fo.cache_dir = arg_str(&q->a, "cache_dir");
        fo.offline = arg_bool(&q->a, "offline", false);
        fo.proxy = arg_str(&q->a, "proxy");
        fo.ca_file = arg_str(&q->a, "ca_file");
        fo.user_agent = arg_str(&q->a, "user_agent");
        fo.timeout_s = arg_num(&q->a, "timeout", 0.0);
        if (release && strcmp(release, "latest") != 0)
            rc = otc_fetch_release(&fo, release, path, sizeof path, &need);
        else
            rc = otc_fetch_latest(&fo, path, sizeof path, &need);
        if (rc != OTC_OK) { set_error_struct(r, rc, &err); return; }
        rc = otc_open_file(path, NULL, &g_current);
        if (rc != OTC_OK) { set_status(r, rc, "otc_open_file"); return; }
        g_current_path = xstrdup(path);
    }
    {
        int bad = 0;
        cJSON *o = cJSON_CreateObject();
        cJSON_AddItemToObject(o, "loaded_from", j_enum(otc_loaded_from_name(otc_release_loaded_from(g_current))));
        cJSON_AddItemToObject(o, "datestamp", j_take(s_rel_datestamp(g_current, &bad)));
        cJSON_AddItemToObject(o, "format_version", j_take(s_rel_format_version(g_current, &bad)));
        r->result = o;
        if (bad) set_error(r, "uncaught:BufferProtocol", "a string accessor broke the buffer rules");
    }
}

static void op_verify(request *q, reply *r)
{
    size_t i, n = otc_release_file_count(q->rel);
    char dir[4096];
    const char *slash1 = strrchr(q->path, '/'), *slash2 = strrchr(q->path, '\\');
    const char *slash = slash1 > slash2 ? slash1 : slash2;
    size_t dlen = slash ? (size_t)(slash - q->path + 1) : 0;
    if (dlen >= sizeof dir) { set_error(r, "io", "path too long"); return; }
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
        snprintf(full, sizeof full, "%s%s", dir, name);
        otc_error_init(&err);
        rc = otc_verify_file(full, NULL, &err);
        if (rc != OTC_OK) { set_error_struct(r, rc, &err); return; }
    }
    r->result = cJSON_CreateObject();
    cJSON_AddTrueToObject(r->result, "verified");
}

static void stats_map(cJSON *o, const char *key, const otc_stats *s,
                      size_t (*count_fn)(const otc_stats *),
                      otc_status (*at_fn)(const otc_stats *, size_t, const char **, int64_t *))
{
    cJSON *m = cJSON_CreateObject();
    size_t i, n = count_fn(s);
    for (i = 0; i < n; i++) {
        const char *k = NULL;
        int64_t c = 0;
        if (at_fn(s, i, &k, &c) == OTC_OK) cJSON_AddNumberToObject(m, k, (double)c);
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
        /* client.last_error is the error behind loaded_from cache_after_error. */
        if (otc_release_loaded_from(R) == OTC_LOADED_FROM_CACHE_AFTER_ERROR)
            cJSON_AddStringToObject(o, "code", otc_status_code(otc_last_error_status(R)));
        else
            cJSON_AddNullToObject(o, "code");
    } else if (!strcmp(op, "release_metadata")) {
        cJSON *sv = cJSON_CreateObject();
        size_t i, n = otc_release_source_version_count(R);
        cJSON_AddItemToObject(o, "datestamp", j_take(s_rel_datestamp(R, &bad)));
        cJSON_AddItemToObject(o, "created", j_take(s_rel_created(R, &bad)));
        cJSON_AddItemToObject(o, "format_version", j_take(s_rel_format_version(R, &bad)));
        cJSON_AddItemToObject(o, "doi", j_take(s_rel_doi(R, &bad)));
        cJSON_AddItemToObject(o, "concept_doi", j_take(s_rel_concept_doi(R, &bad)));
        for (i = 0; i < n; i++) {
            char k[256], v[256];
            size_t nk, nv;
            if (otc_release_source_version_at(R, i, k, sizeof k, &nk, v, sizeof v, &nv) != OTC_OK) { bad = 1; break; }
            cJSON_AddStringToObject(sv, k, v);
        }
        cJSON_AddItemToObject(o, "source_versions", sv);
        cJSON_AddItemToObject(o, "build_commit", j_take(s_rel_build_commit(R, &bad)));
        cJSON_AddItemToObject(o, "changelog_url", j_take(s_rel_changelog_url(R, &bad)));
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
        stats_map(so, "type", s, otc_stats_type_count, otc_stats_type_at);
        stats_map(so, "kind", s, otc_stats_kind_count, otc_stats_kind_at);
        stats_map(so, "country", s, otc_stats_country_count, otc_stats_country_at);
        stats_map(so, "source", s, otc_stats_source_count, otc_stats_source_at);
        stats_map(so, "qc_status", s, otc_stats_qc_status_count, otc_stats_qc_status_at);
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
        if (!q->a.bad && id && otc_release_convention(R, id, &c) == OTC_OK)
            cJSON_AddItemToObject(o, "convention", enc_convention(c, &bad));
        else
            cJSON_AddNullToObject(o, "convention");
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
        if (!q->a.bad && id && otc_release_licence(R, id, &l) == OTC_OK)
            cJSON_AddItemToObject(o, "licence", enc_licence(l, &bad));
        else
            cJSON_AddNullToObject(o, "licence");
    } else if (!strcmp(op, "citation")) {
        cJSON_AddItemToObject(o, "citation", j_take(s_rel_citation(R, &bad)));
    } else if (!strcmp(op, "attribution")) {
        const cJSON *ids = q->a.obj ? cJSON_GetObjectItemCaseSensitive(q->a.obj, "station_ids") : NULL;
        const char **idv = NULL;
        size_t n = 0, need = 0;
        char *buf;
        if (ids && !cJSON_IsNull(ids)) {
            const cJSON *it;
            if (!cJSON_IsArray(ids)) { set_error(r, "invalid_argument", "station_ids"); return; }
            idv = (const char **)calloc((size_t)cJSON_GetArraySize(ids) + 1, sizeof *idv);
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
            set_status(r, rc, op);
            return;
        }
    } else if (!strcmp(op, "tombstone")) {
        otc_tombstone_t *t = NULL;
        const char *id = arg_str(&q->a, "station_id");
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
            cJSON_AddItemToObject(o, "station_id", j_take(s_st_id(st, &bad)));
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
            cJSON_AddItemToArray(arr, j_take(s_st_id(st, &bad)));
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
        const char *name = arg_str(&q->a, "name"), *match = arg_str(&q->a, "match");
        cJSON *arr;
        arg_filter(&q->a, &f);
        limit = arg_limit(&q->a, "limit");
        if (match) {
            if (!strcmp(match, "exact")) f.match_exact = true;
            else q->a.bad = 1;
        }
        if (q->a.bad || !name) { set_error(r, "invalid_argument", "search arguments"); return; }
        LIST_CALL(rc, otc_hit, hits, count, otc_search(R, name, &f, limit, NULL, 0, &count),
                  otc_search(R, name, &f, limit, hits, cap_, &count));
        if (rc != OTC_OK) { free(hits); set_status(r, rc, op); return; }
        arr = cJSON_CreateArray();
        for (i = 0; i < count; i++) cJSON_AddItemToArray(arr, cJSON_CreateString(hits[i].id));
        free(hits);
        cJSON_AddItemToObject(o, "station_ids", arr);
    } else if (!strcmp(op, "near")) {
        otc_filter f;
        otc_nearby *hits = NULL;
        size_t count = 0, i, limit;
        double lat = arg_num(&q->a, "lat", NAN), lon = arg_num(&q->a, "lon", NAN);
        double radius = arg_num(&q->a, "radius_km", NAN);
        cJSON *ids, *dist;
        arg_filter(&q->a, &f);
        limit = arg_limit(&q->a, "limit");
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
        if (!strcmp(op, "reference_station")) {
            otc_station_t *ref = NULL;
            if (st && otc_reference_station(R, st, &ref) == OTC_OK) {
                cJSON_AddItemToObject(o, "station_id", j_take(s_st_id(ref, &bad)));
                otc_station_free(ref);
            } else {
                cJSON_AddNullToObject(o, "station_id");
            }
        } else if (!strcmp(op, "subordinates_of")) {
            const char **ids = NULL;
            size_t count = 0;
            if (st) {
                LIST_CALL(rc, const char *, ids, count, otc_subordinates_of(R, st, NULL, 0, &count),
                          otc_subordinates_of(R, st, ids, cap_, &count));
                if (rc != OTC_OK) bad = 1;
            }
            cJSON_AddItemToObject(o, "station_ids", ids_array(ids, count));
            free((void *)ids);
        } else if (!strcmp(op, "station_validation")) {
            cJSON *arr = cJSON_CreateArray();
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
            if (st && otc_station_offsets(st, &off) == OTC_OK) {
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
            if (st && otc_station_recommended_set(st, &set) == OTC_OK)
                cJSON_AddItemToObject(o, "set_id", j_take(s_set_id(set, &bad)));
            else
                cJSON_AddNullToObject(o, "set_id");
        } else if (!strcmp(op, "constant_sets")) {
            bool inc = arg_bool(&q->a, "include_excluded", false);
            cJSON *arr = cJSON_CreateArray();
            size_t i, n = st ? otc_station_set_count(st, inc) : 0;
            if (q->a.bad) { cJSON_Delete(arr); otc_station_free(st); set_error(r, "invalid_argument", "include_excluded"); return; }
            for (i = 0; i < n; i++) {
                const otc_set *set = NULL;
                if (otc_station_set_at(st, inc, i, &set) != OTC_OK) { bad = 1; break; }
                cJSON_AddItemToArray(arr, j_take(s_set_id(set, &bad)));
            }
            cJSON_AddItemToObject(o, "set_ids", arr);
        } else if (!strcmp(op, "constant_set")) {
            const otc_set *set = find_set(q, st);
            if (set) cJSON_AddItemToObject(o, "set", enc_set(set, &bad));
            else cJSON_AddNullToObject(o, "set");
        } else if (!strcmp(op, "constituents")) {
            const otc_set *set = find_set(q, st);
            cJSON *arr = cJSON_CreateArray();
            size_t i, n = set ? otc_set_constituent_count(set) : 0;
            for (i = 0; i < n; i++) {
                const otc_constituent_t *c = NULL;
                if (otc_set_constituent_at(set, i, &c) != OTC_OK) { bad = 1; break; }
                cJSON_AddItemToArray(arr, enc_constituent(c));
            }
            cJSON_AddItemToObject(o, "constituents", arr);
        } else if (!strcmp(op, "constituent")) {
            const otc_set *set = find_set(q, st);
            const char *name = arg_str(&q->a, "name");
            const otc_constituent_t *c = NULL;
            if (set && name && otc_set_constituent(set, name, &c) == OTC_OK)
                cJSON_AddItemToObject(o, "constituent", enc_constituent(c));
            else
                cJSON_AddNullToObject(o, "constituent");
        } else if (!strcmp(op, "provenance")) {
            const otc_set *set = find_set(q, st);
            if (set) {
                cJSON *p = cJSON_CreateObject();
                cJSON_AddItemToObject(p, "build_commit", j_take(s_prov_build_commit(set, &bad)));
                cJSON_AddItemToObject(p, "adapter_version", j_take(s_prov_adapter_version(set, &bad)));
                cJSON_AddItemToObject(p, "input_sha256", j_parse_or_null(s_prov_input_sha256(set, &bad)));
                cJSON_AddItemToObject(p, "time_base", j_parse_or_null(s_prov_time_base(set, &bad)));
                cJSON_AddItemToObject(p, "selection_reason", j_take(s_prov_selection_reason(set, &bad)));
                cJSON_AddItemToObject(p, "decision", j_parse_or_null(s_prov_decision(set, &bad)));
                cJSON_AddItemToObject(o, "provenance", p);
                cJSON_AddItemToObject(o, "raw", j_parse_or_null(s_set_prov_json(set, &bad)));
            } else {
                cJSON_AddNullToObject(o, "provenance");
                cJSON_AddNullToObject(o, "raw");
            }
        } else if (!strcmp(op, "set_validation")) {
            const otc_set *set = find_set(q, st);
            cJSON *arr = cJSON_CreateArray();
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
                if (st) raw = j_parse_or_null(s_st_raw(st, &bad));
            } else if (!strcmp(obj, "tombstone")) {
                otc_tombstone_t *t = NULL;
                const char *id = arg_str(&q->a, "station_id");
                if (id && otc_tombstone(R, id, &t) == OTC_OK) {
                    raw = j_parse_or_null(s_tb_raw(t, &bad));
                    otc_tombstone_free(t);
                }
            } else if (!strcmp(obj, "set")) {
                const otc_set *set = find_set(q, st);
                if (set) raw = j_parse_or_null(s_set_raw(set, &bad));
            } else if (!strcmp(obj, "constituent")) {
                const otc_set *set = find_set(q, st);
                const char *name = arg_str(&q->a, "name");
                size_t i, n = set ? otc_set_constituent_count(set) : 0;
                for (i = 0; i < n && name; i++) {
                    const otc_constituent_t *c = NULL;
                    if (otc_set_constituent_at(set, i, &c) == OTC_OK && !strcmp(c->name, name)) {
                        size_t need = 0;
                        char *buf;
                        if (otc_constituent_raw_json(set, i, NULL, 0, &need) != OTC_OK) { bad = 1; break; }
                        buf = (char *)malloc(need);
                        if (buf && otc_constituent_raw_json(set, i, buf, need, &need) == OTC_OK) raw = j_parse_or_null(buf);
                        else { free(buf); bad = 1; }
                        break;
                    }
                }
            } else if (!strcmp(obj, "convention")) {
                const otc_convention *c = NULL;
                const char *id = arg_str(&q->a, "convention_id");
                if (id && otc_release_convention(R, id, &c) == OTC_OK) raw = j_parse_or_null(s_conv_raw(c, &bad));
            } else if (!strcmp(obj, "licence")) {
                const otc_licence *l = NULL;
                const char *id = arg_str(&q->a, "licence_id");
                if (id && otc_release_licence(R, id, &l) == OTC_OK) raw = j_parse_or_null(s_lic_raw(l, &bad));
            }
            cJSON_AddItemToObject(o, "raw", raw ? raw : cJSON_CreateNull());
        } else {
            otc_station_free(st);
            set_error(r, "uncaught:UnknownOp", op);
            return;
        }
        otc_station_free(st);
    }
    if (bad) set_error(r, "uncaught:BufferProtocol", "an accessor broke the buffer or list rules");
}

/* Ops of the fetch module: in a build without otc_fetch they return OTC_E_NOT_BUILT. */
static void op_fetch(request *q, reply *r)
{
    otc_fetch_options fo;
    otc_error err;
    otc_status rc;
    char ds[64];
    size_t need = 0, count = 0;
    otc_fetch_options_init(&fo);
    otc_error_init(&err);
    fo.error = &err;
    if (otc_release_datestamp(q->rel, ds, sizeof ds, &need) != OTC_OK) ds[0] = '\0';
    if (!strcmp(q->op, "releases")) rc = otc_fetch_releases(&fo, NULL, 0, &count);
    else if (!strcmp(q->op, "latest")) { otc_release_info *ri = NULL; rc = otc_fetch_latest_info(&fo, &ri); otc_release_info_free(ri); }
    else if (!strcmp(q->op, "check_for_update")) { otc_release_info *ri = NULL; bool found = false; rc = otc_fetch_check_for_update(&fo, ds, &ri, &found); otc_release_info_free(ri); }
    else if (!strcmp(q->op, "update")) { char p[4096]; bool updated = false; rc = otc_fetch_update(&fo, ds, p, sizeof p, &updated); }
    else if (!strcmp(q->op, "download")) {
        const char *to = arg_str(&q->a, "to"), *release = arg_str(&q->a, "release");
        rc = otc_fetch_to_dir(&fo, release, to, 0, arg_bool(&q->a, "overwrite", false), NULL, 0, &count);
    }
    else if (!strcmp(q->op, "cached_releases")) rc = otc_fetch_cached_releases(&fo, NULL, 0, &count);
    else rc = otc_fetch_prune(&fo, (size_t)arg_num(&q->a, "keep", 3), NULL, 0, &count);
    if (rc != OTC_OK) { set_error_struct(r, rc, &err); return; }
    set_error(r, "uncaught:NotImplemented", "the runner has no encoding for a fetch result yet (K3d2)");
}

static int is_fetch_op(const char *op)
{
    static const char *const ops[] = {"releases", "latest", "check_for_update", "update", "download",
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
    request *q;
    char *out;
} thread_job;

#ifdef _WIN32
static DWORD WINAPI thread_main(LPVOID p)
{
    thread_job *j = (thread_job *)p;
    j->out = run_query(j->q);
    return 0;
}
#else
static void *thread_main(void *p)
{
    thread_job *j = (thread_job *)p;
    j->out = run_query(j->q);
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
    if (!jobs || !th) { free(jobs); free(th); return run_query(q); }
    for (i = 0; i < n; i++) {
        jobs[i].q = q;
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
    for (i = 0; i < started; i++) {
        if (!first) first = jobs[i].out;
        else if (!jobs[i].out || strcmp(first, jobs[i].out) != 0) same = 0;
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

static char *read_line(FILE *f)
{
    size_t cap = 4096, n = 0;
    char *buf = (char *)malloc(cap);
    int c;
    if (!buf) return NULL;
    while ((c = fgetc(f)) != EOF) {
        if (c == '\n') break;
        if (n + 1 >= cap) {
            char *nb = (char *)realloc(buf, cap * 2);
            if (!nb) { free(buf); return NULL; }
            buf = nb;
            cap *= 2;
        }
        buf[n++] = (char)c;
    }
    if (c == EOF && n == 0) { free(buf); return NULL; }
    buf[n] = '\0';
    return buf;
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
        if (!name || !g_current || g_n_held >= MAX_HELD) set_error(&r, "invalid_argument", "hold_release");
        else {
            g_held[g_n_held].name = xstrdup(name);
            g_held[g_n_held].rel = g_current;
            g_held[g_n_held].path = xstrdup(g_current_path);
            g_n_held++;
        }
        out = render(&r);
    } else if (threads > 1 && q.rel) {
        out = run_threaded(&q, threads);
    } else {
        out = run_query(&q);
    }
    (void)has_arg;
    cJSON_Delete(req);
    return out;
}

int main(void)
{
    char *line;
    const char *t = getenv("OTC_RUNNER_THREADS");
    int threads = t ? atoi(t) : 1;
    size_t i;
    printf("{\"hello\": {\"runner\": \"%s\", \"version\": \"%s\", \"features\": [%s]}}\n",
           OTC_RUNNER_FETCH ? "c-fetch" : "c", OTC_VERSION,
           OTC_RUNNER_FETCH ? "\"fs\", \"fetch\", \"stream\"" : "\"fs\", \"stream\"");
    fflush(stdout);
    while ((line = read_line(stdin)) != NULL) {
        char *out;
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
    return 0;
}
