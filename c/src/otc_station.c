/* Station, set, constituent and validation accessors (SDK spec 4.4-4.7, 6.4).
 * A station owns its parsed line; every pointer handed out is borrowed from it. */
#include "otc_internal.h"

/* --------------------------------------------------------------- building */

static void fill_validation(otc_validation_t *v, const cJSON *row)
{
    const cJSON *prev = otc__jget(row, "previous_release");
    memset(v, 0, sizeof *v);
    v->struct_size = sizeof *v;
    v->set_id = otc__jstr(row, "set_id");
    v->reference_source = otc__jstr(row, "reference_source");
    v->reference_station = otc__jstr(row, "reference_station");
    v->reference_distance_km = otc__jnum(row, "reference_distance_km");
    v->window = otc__jstr(row, "window");
    v->time_mae_min = otc__jnum(row, "time_mae_min");
    v->time_p95_min = otc__jnum(row, "time_p95_min");
    v->time_bias_min = otc__jnum(row, "time_bias_min");
    v->height_mae_m = otc__jnum(row, "height_mae_m");
    v->range_error_m = otc__jnum(row, "range_error_m");
    v->missed_events = otc__jint(row, "missed_events");
    v->extra_events = otc__jint(row, "extra_events");
    if (cJSON_IsObject(prev)) {
        v->has_previous_release = true;
        v->previous_release.time_mae_min = otc__jnum(prev, "time_mae_min");
        v->previous_release.time_p95_min = otc__jnum(prev, "time_p95_min");
        v->previous_release.time_bias_min = otc__jnum(prev, "time_bias_min");
        v->previous_release.height_mae_m = otc__jnum(prev, "height_mae_m");
        v->previous_release.range_error_m = otc__jnum(prev, "range_error_m");
        v->previous_release.missed_events = otc__jint(prev, "missed_events");
        v->previous_release.extra_events = otc__jint(prev, "extra_events");
    }
}

static void copy_fixed(char *dst, size_t cap, const char *src)
{
    size_t n = src ? strlen(src) : 0;
    if (n >= cap) n = cap - 1; /* cannot happen: lengths are checked at open */
    if (n) memcpy(dst, src, n);
    dst[n] = '\0';
}

static void fill_constituent(otc_constituent_t *c, const cJSON *j)
{
    memset(c, 0, sizeof *c);
    c->struct_size = sizeof *c;
    copy_fixed(c->name, sizeof c->name, otc__jstr(j, "name"));
    copy_fixed(c->source_name, sizeof c->source_name, otc__jstr(j, "source_name"));
    copy_fixed(c->doodson, sizeof c->doodson, otc__jstr(j, "doodson"));
    copy_fixed(c->kept_reason, sizeof c->kept_reason, otc__jstr(j, "kept_reason"));
    c->speed_deg_per_hour = otc__jnum(j, "speed_deg_per_hour");
    c->amplitude_m = otc__jnum(j, "amplitude_m");
    c->phase_deg = otc__jnum(j, "phase_deg");
    c->amp_uncertainty_m = otc__jnum(j, "amp_uncertainty_m");
    c->phase_uncertainty_deg = otc__jnum(j, "phase_uncertainty_deg");
}

static int set_ptr_cmp(const void *a, const void *b)
{
    const otc_set *x = *(otc_set *const *)a, *y = *(otc_set *const *)b;
    if (x->recommended != y->recommended) return x->recommended ? -1 : 1;
    return otc__strcmp_null(otc__jstr(x->json, "set_id"), otc__jstr(y->json, "set_id"));
}

/* by window, stable (ties keep file order) */
static void sort_by_window(const otc_validation_t **v, size_t n)
{
    size_t i, j;
    for (i = 1; i < n; i++) {
        const otc_validation_t *x = v[i];
        j = i;
        while (j > 0 && otc__strcmp_null(v[j - 1]->window, x->window) > 0) {
            v[j] = v[j - 1];
            j--;
        }
        v[j] = x;
    }
}

static void free_sets(otc_station_t *st)
{
    size_t i;
    for (i = 0; i < st->n_sets; i++) {
        free(st->sets[i].cons);
        free((void *)st->sets[i].val);
        free(st->sets[i].flags);
        free(st->sets[i].drops);
    }
    free(st->sets);
}

void otc_station_free(otc_station_t *st)
{
    if (!st) return;
    free_sets(st);
    free(st->order_all);
    free(st->order_usable);
    free(st->val);
    cJSON_Delete(st->root);
    free(st);
}

static otc_status build_set(otc_station_t *st, otc_set *s, const cJSON *j, const char *rec_id)
{
    const otc_release *rel = st->rel;
    const cJSON *cons = otc__jget(j, "constituents"), *flags = otc__jget(j, "qc_flags");
    const cJSON *drops = otc__jget(j, "dropped_constituents"), *x;
    const char *set_id = otc__jstr(j, "set_id");
    size_t i;
    s->json = j;
    s->station = st;
    s->conv = otc__find_convention(rel, otc__jstr(j, "convention_id"));
    s->lic = otc__find_licence(rel, otc__jstr(j, "licence_id"));
    s->recommended = rec_id && set_id && !strcmp(rec_id, set_id);
    s->excluded = otc__parse_qc_status(otc__jstr(j, "qc_status")) == OTC_QC_STATUS_EXCLUDED;
    s->n_cons = cJSON_IsArray(cons) ? (size_t)cJSON_GetArraySize(cons) : 0;
    s->cons = (otc_constituent_t *)calloc(s->n_cons ? s->n_cons : 1, sizeof *s->cons);
    if (!s->cons) return OTC_E_NOMEM;
    i = 0;
    if (cJSON_IsArray(cons)) cJSON_ArrayForEach(x, cons) fill_constituent(&s->cons[i++], x);
    s->n_flags = cJSON_IsArray(flags) ? (size_t)cJSON_GetArraySize(flags) : 0;
    s->flags = (otc_qc_flag *)calloc(s->n_flags ? s->n_flags : 1, sizeof *s->flags);
    if (!s->flags) return OTC_E_NOMEM;
    i = 0;
    if (cJSON_IsArray(flags)) cJSON_ArrayForEach(x, flags) s->flags[i++].json = x;
    s->n_drops = cJSON_IsArray(drops) ? (size_t)cJSON_GetArraySize(drops) : 0;
    s->drops = (otc_dropped *)calloc(s->n_drops ? s->n_drops : 1, sizeof *s->drops);
    if (!s->drops) return OTC_E_NOMEM;
    i = 0;
    if (cJSON_IsArray(drops)) cJSON_ArrayForEach(x, drops) s->drops[i++].json = x;
    s->span.json = otc__jget(j, "record_span");
    s->has_span = cJSON_IsObject(s->span.json);
    s->datum.json = otc__jget(j, "datum");
    s->has_datum = cJSON_IsObject(s->datum.json);
    /* the station's validation rows for this set, by window */
    s->val = (const otc_validation_t **)calloc(st->n_val ? st->n_val : 1, sizeof *s->val);
    if (!s->val) return OTC_E_NOMEM;
    for (i = 0; i < st->n_val; i++)
        if (set_id && st->val[i].set_id && !strcmp(st->val[i].set_id, set_id)) s->val[s->n_val++] = &st->val[i];
    sort_by_window(s->val, s->n_val);
    return OTC_OK;
}

otc_status otc__station_build(const otc_release *rel, cJSON *root, otc_kind kind, otc_station_t **out)
{
    otc_station_t *st = (otc_station_t *)calloc(1, sizeof *st);
    const cJSON *sets = otc__jget(root, "constant_sets"), *vals = otc__jget(root, "validation"), *x;
    const char *rec_id = otc__jstr(root, "recommended_set_id");
    size_t i;
    otc_status rc = OTC_OK;
    *out = NULL;
    if (!st) { cJSON_Delete(root); return OTC_E_NOMEM; }
    st->root = root;
    st->rel = rel;
    st->kind = kind;
    st->n_val = cJSON_IsArray(vals) ? (size_t)cJSON_GetArraySize(vals) : 0;
    st->val = (otc_validation_t *)calloc(st->n_val ? st->n_val : 1, sizeof *st->val);
    st->n_sets = cJSON_IsArray(sets) ? (size_t)cJSON_GetArraySize(sets) : 0;
    st->sets = (otc_set *)calloc(st->n_sets ? st->n_sets : 1, sizeof *st->sets);
    st->order_all = (otc_set **)calloc(st->n_sets ? st->n_sets : 1, sizeof *st->order_all);
    st->order_usable = (otc_set **)calloc(st->n_sets ? st->n_sets : 1, sizeof *st->order_usable);
    if (!st->val || !st->sets || !st->order_all || !st->order_usable) { otc_station_free(st); return OTC_E_NOMEM; }
    i = 0;
    if (cJSON_IsArray(vals)) cJSON_ArrayForEach(x, vals) fill_validation(&st->val[i++], x);
    i = 0;
    if (cJSON_IsArray(sets)) {
        cJSON_ArrayForEach(x, sets) {
            if ((rc = build_set(st, &st->sets[i], x, rec_id)) != OTC_OK) break;
            if (st->sets[i].recommended) st->rec = &st->sets[i];
            st->order_all[i] = &st->sets[i];
            i++;
        }
    }
    if (rc != OTC_OK) {
        st->n_sets = i + 1;
        otc_station_free(st);
        return rc;
    }
    st->n_all = st->n_sets;
    if (st->n_all > 1) qsort(st->order_all, st->n_all, sizeof *st->order_all, set_ptr_cmp);
    for (i = 0; i < st->n_all; i++)
        if (!st->order_all[i]->excluded) st->order_usable[st->n_usable++] = st->order_all[i];
    *out = st;
    return OTC_OK;
}

/* --------------------------------------------------------- station fields */

#define ST_STR(NAME, KEY)                                                                      \
    otc_status NAME(const otc_station_t *st, char *buf, size_t len, size_t *needed)            \
    {                                                                                          \
        return st ? otc__copy_str(otc__jstr(st->root, KEY), buf, len, needed) : OTC_E_INVALID_ARGUMENT; \
    }
ST_STR(otc_station_station_id, "station_id")
ST_STR(otc_station_name, "name")
ST_STR(otc_station_country, "country")
ST_STR(otc_station_timezone, "timezone")

double otc_station_lat(const otc_station_t *st) { return st ? otc__jnum(st->root, "lat") : NAN; }
double otc_station_lon(const otc_station_t *st) { return st ? otc__jnum(st->root, "lon") : NAN; }

otc_station_type_t otc_station_type(const otc_station_t *st)
{
    return st ? otc__parse_station_type(otc__jstr(st->root, "type")) : OTC_STATION_TYPE_UNSET;
}

otc_kind otc_station_kind(const otc_station_t *st) { return st ? st->kind : OTC_KIND_UNSET; }

otc_station_status_t otc_station_status(const otc_station_t *st)
{
    return st ? otc__parse_station_status(otc__jstr(st->root, "status")) : OTC_STATION_STATUS_UNSET;
}

bool otc_station_is_reference(const otc_station_t *st) { return otc_station_type(st) == OTC_STATION_TYPE_REFERENCE; }
bool otc_station_is_subordinate(const otc_station_t *st)
{
    return otc_station_type(st) == OTC_STATION_TYPE_SUBORDINATE;
}
bool otc_station_is_tide(const otc_station_t *st) { return otc_station_kind(st) == OTC_KIND_TIDE; }
bool otc_station_is_current(const otc_station_t *st) { return otc_station_kind(st) == OTC_KIND_CURRENT; }

static const cJSON *aliases_of(const otc_station_t *st)
{
    const cJSON *a = st ? otc__jget(st->root, "aliases") : NULL;
    return cJSON_IsObject(a) ? a : NULL;
}

size_t otc_station_alias_system_count(const otc_station_t *st)
{
    const cJSON *a = aliases_of(st);
    return a ? (size_t)cJSON_GetArraySize(a) : 0;
}

otc_status otc_station_alias_system_at(const otc_station_t *st, size_t i, char *buf, size_t len, size_t *needed)
{
    const cJSON *a = aliases_of(st);
    if (!a || i >= (size_t)cJSON_GetArraySize(a)) return OTC_E_INVALID_ARGUMENT;
    return otc__copy_str(cJSON_GetArrayItem(a, (int)i)->string, buf, len, needed);
}

size_t otc_station_alias_count(const otc_station_t *st, const char *system)
{
    const cJSON *v = system ? otc__jget(aliases_of(st), system) : NULL;
    if (cJSON_IsString(v)) return 1;
    return cJSON_IsArray(v) ? (size_t)cJSON_GetArraySize(v) : 0;
}

otc_status otc_station_alias_at(const otc_station_t *st, const char *system, size_t i, char *buf, size_t len,
                                size_t *needed)
{
    const cJSON *v = system ? otc__jget(aliases_of(st), system) : NULL;
    if (cJSON_IsString(v) && i == 0) return otc__copy_str(v->valuestring, buf, len, needed);
    if (cJSON_IsArray(v) && i < (size_t)cJSON_GetArraySize(v)) {
        const cJSON *x = cJSON_GetArrayItem(v, (int)i);
        if (cJSON_IsString(x)) return otc__copy_str(x->valuestring, buf, len, needed);
    }
    return OTC_E_INVALID_ARGUMENT;
}

otc_status otc_station_raw_json(const otc_station_t *st, char *buf, size_t len, size_t *needed)
{
    return st ? otc__copy_json(st->root, buf, len, needed) : OTC_E_INVALID_ARGUMENT;
}

otc_status otc_station_recommended_set(const otc_station_t *st, const otc_set **out)
{
    if (!st || !out) return OTC_E_INVALID_ARGUMENT;
    *out = st->rec;
    return st->rec ? OTC_OK : OTC_E_NOT_FOUND;
}

size_t otc_station_set_count(const otc_station_t *st, bool include_excluded)
{
    if (!st) return 0;
    return include_excluded ? st->n_all : st->n_usable;
}

otc_status otc_station_set_at(const otc_station_t *st, bool include_excluded, size_t i, const otc_set **out)
{
    if (!st || !out || i >= otc_station_set_count(st, include_excluded)) return OTC_E_INVALID_ARGUMENT;
    *out = include_excluded ? st->order_all[i] : st->order_usable[i];
    return OTC_OK;
}

otc_status otc_station_set(const otc_station_t *st, const char *set_id, const otc_set **out)
{
    size_t i;
    if (!st || !out || !set_id) return OTC_E_INVALID_ARGUMENT;
    *out = NULL;
    for (i = 0; i < st->n_sets; i++) {
        const char *id = otc__jstr(st->sets[i].json, "set_id");
        if (id && !strcmp(id, set_id)) { *out = &st->sets[i]; return OTC_OK; }
    }
    return OTC_E_NOT_FOUND;
}

otc_status otc_station_offsets(const otc_station_t *st, otc_offsets_t *out)
{
    const cJSON *off;
    if (!st || !out || out->struct_size < sizeof *out) return OTC_E_INVALID_ARGUMENT;
    off = otc__jget(st->root, "subordinate_offsets");
    if (!cJSON_IsObject(off)) return OTC_E_NOT_FOUND;
    out->reference_station_id = otc__jstr(off, "reference_station_id");
    out->time_offset_high_min = otc__jnum(off, "time_offset_high_min");
    out->time_offset_low_min = otc__jnum(off, "time_offset_low_min");
    out->height_offset_high = otc__jnum(off, "height_offset_high");
    out->height_offset_low = otc__jnum(off, "height_offset_low");
    out->height_adjusted_type = otc__parse_height_adjusted_type(otc__jstr(off, "height_adjusted_type"));
    out->licence_id = otc__jstr(off, "licence_id");
    return OTC_OK;
}

size_t otc_station_validation_count(const otc_station_t *st) { return st ? st->n_val : 0; }

otc_status otc_station_validation_at(const otc_station_t *st, size_t i, const otc_validation_t **out)
{
    if (!st || !out || i >= st->n_val) return OTC_E_INVALID_ARGUMENT;
    *out = &st->val[i];
    return OTC_OK;
}

/* ------------------------------------------------------------- tombstones */

#define TB_STR(NAME, KEY)                                                                      \
    otc_status NAME(const otc_tombstone_t *t, char *buf, size_t len, size_t *needed)           \
    {                                                                                          \
        return t ? otc__copy_str(otc__jstr(t->root, KEY), buf, len, needed) : OTC_E_INVALID_ARGUMENT; \
    }
TB_STR(otc_tombstone_station_id, "station_id")
TB_STR(otc_tombstone_name, "name")
TB_STR(otc_tombstone_removed_in, "removed_in")
TB_STR(otc_tombstone_removed_reason, "removed_reason")

otc_station_status_t otc_tombstone_status(const otc_tombstone_t *t)
{
    return t ? otc__parse_station_status(otc__jstr(t->root, "status")) : OTC_STATION_STATUS_UNSET;
}

otc_status otc_tombstone_raw_json(const otc_tombstone_t *t, char *buf, size_t len, size_t *needed)
{
    return t ? otc__copy_json(t->root, buf, len, needed) : OTC_E_INVALID_ARGUMENT;
}

/* ------------------------------------------------------------------- sets */

#define SET_STR(NAME, KEY)                                                                     \
    otc_status NAME(const otc_set *s, char *buf, size_t len, size_t *needed)                   \
    {                                                                                          \
        return s ? otc__copy_str(otc__jstr(s->json, KEY), buf, len, needed) : OTC_E_INVALID_ARGUMENT; \
    }
SET_STR(otc_set_set_id, "set_id")
SET_STR(otc_set_source, "source")
SET_STR(otc_set_source_record_id, "source_record_id")
SET_STR(otc_set_source_version, "source_version")

otc_source_type otc_set_source_type(const otc_set *s)
{
    return s ? otc__parse_source_type(otc__jstr(s->json, "source_type")) : OTC_SOURCE_TYPE_UNSET;
}
otc_quantity otc_set_quantity(const otc_set *s)
{
    return s ? otc__parse_quantity(otc__jstr(s->json, "quantity")) : OTC_QUANTITY_UNSET;
}
otc_qc_status otc_set_qc_status(const otc_set *s)
{
    return s ? otc__parse_qc_status(otc__jstr(s->json, "qc_status")) : OTC_QC_STATUS_UNSET;
}
bool otc_set_is_recommended(const otc_set *s) { return s && s->recommended; }

otc_status otc_set_raw_json(const otc_set *s, char *buf, size_t len, size_t *needed)
{
    return s ? otc__copy_json(s->json, buf, len, needed) : OTC_E_INVALID_ARGUMENT;
}

otc_status otc_set_record_span(const otc_set *s, const otc_record_span **out)
{
    if (!s || !out) return OTC_E_INVALID_ARGUMENT;
    *out = s->has_span ? &s->span : NULL;
    return s->has_span ? OTC_OK : OTC_E_NOT_FOUND;
}
otc_status otc_record_span_start(const otc_record_span *rs, char *buf, size_t len, size_t *needed)
{
    return rs ? otc__copy_str(otc__jstr(rs->json, "start"), buf, len, needed) : OTC_E_INVALID_ARGUMENT;
}
otc_status otc_record_span_end(const otc_record_span *rs, char *buf, size_t len, size_t *needed)
{
    return rs ? otc__copy_str(otc__jstr(rs->json, "end"), buf, len, needed) : OTC_E_INVALID_ARGUMENT;
}
int64_t otc_record_span_good_samples(const otc_record_span *rs) { return rs ? otc__jint(rs->json, "good_samples") : -1; }

otc_status otc_set_datum(const otc_set *s, const otc_datum **out)
{
    if (!s || !out) return OTC_E_INVALID_ARGUMENT;
    *out = s->has_datum ? &s->datum : NULL;
    return s->has_datum ? OTC_OK : OTC_E_NOT_FOUND;
}
double otc_datum_msl_offset_m(const otc_datum *d) { return d ? otc__jnum(d->json, "msl_offset_m") : NAN; }
size_t otc_datum_named_count(const otc_datum *d)
{
    const cJSON *n = d ? otc__jget(d->json, "named") : NULL;
    return cJSON_IsObject(n) ? (size_t)cJSON_GetArraySize(n) : 0;
}
otc_status otc_datum_named_at(const otc_datum *d, size_t i, char *name, size_t len, size_t *needed, double *value)
{
    const cJSON *n, *x;
    if (!d || !value || i >= otc_datum_named_count(d)) return OTC_E_INVALID_ARGUMENT;
    n = otc__jget(d->json, "named");
    x = cJSON_GetArrayItem(n, (int)i);
    *value = cJSON_IsNumber(x) ? x->valuedouble : NAN;
    return otc__copy_str(x->string, name, len, needed);
}

size_t otc_set_qc_flag_count(const otc_set *s) { return s ? s->n_flags : 0; }
otc_status otc_set_qc_flag_at(const otc_set *s, size_t i, const otc_qc_flag **out)
{
    if (!s || !out || i >= s->n_flags) return OTC_E_INVALID_ARGUMENT;
    *out = &s->flags[i];
    return OTC_OK;
}
otc_qc_flag_kind otc_qc_flag_flag(const otc_qc_flag *f)
{
    return f ? otc__parse_qc_flag(otc__jstr(f->json, "flag")) : OTC_QC_FLAG_UNSET;
}
otc_status otc_qc_flag_verdict(const otc_qc_flag *f, char *buf, size_t len, size_t *needed)
{
    return f ? otc__copy_str(otc__jstr(f->json, "verdict"), buf, len, needed) : OTC_E_INVALID_ARGUMENT;
}
otc_status otc_qc_flag_values_json(const otc_qc_flag *f, char *buf, size_t len, size_t *needed)
{
    return f ? otc__copy_json(otc__jget(f->json, "values"), buf, len, needed) : OTC_E_INVALID_ARGUMENT;
}

size_t otc_set_dropped_count(const otc_set *s) { return s ? s->n_drops : 0; }
otc_status otc_set_dropped_at(const otc_set *s, size_t i, const otc_dropped **out)
{
    if (!s || !out || i >= s->n_drops) return OTC_E_INVALID_ARGUMENT;
    *out = &s->drops[i];
    return OTC_OK;
}
otc_status otc_dropped_name(const otc_dropped *d, char *buf, size_t len, size_t *needed)
{
    return d ? otc__copy_str(otc__jstr(d->json, "name"), buf, len, needed) : OTC_E_INVALID_ARGUMENT;
}
otc_dropped_reason otc_dropped_dropped_reason(const otc_dropped *d)
{
    return d ? otc__parse_dropped_reason(otc__jstr(d->json, "dropped_reason")) : OTC_DROPPED_REASON_UNSET;
}
otc_status otc_dropped_detail(const otc_dropped *d, char *buf, size_t len, size_t *needed)
{
    return d ? otc__copy_str(otc__jstr(d->json, "detail"), buf, len, needed) : OTC_E_INVALID_ARGUMENT;
}

otc_status otc_set_convention(const otc_set *s, const otc_convention **out)
{
    if (!s || !out) return OTC_E_INVALID_ARGUMENT;
    *out = s->conv;
    return s->conv ? OTC_OK : OTC_E_NOT_FOUND;
}
otc_status otc_set_licence(const otc_set *s, const otc_licence **out)
{
    if (!s || !out) return OTC_E_INVALID_ARGUMENT;
    *out = s->lic;
    return s->lic ? OTC_OK : OTC_E_NOT_FOUND;
}

static const cJSON *prov_of(const otc_set *s)
{
    const cJSON *p = otc__jget(s->json, "provenance");
    return cJSON_IsObject(p) ? p : NULL;
}

otc_status otc_set_provenance_field(const otc_set *s, const char *field, char *buf, size_t len, size_t *needed)
{
    const cJSON *v;
    if (!s || !field) return OTC_E_INVALID_ARGUMENT;
    v = otc__jget(prov_of(s), field);
    if (cJSON_IsString(v)) return otc__copy_str(v->valuestring, buf, len, needed);
    return otc__copy_json(v, buf, len, needed);
}

otc_status otc_set_provenance_json(const otc_set *s, char *buf, size_t len, size_t *needed)
{
    const cJSON *p;
    if (!s) return OTC_E_INVALID_ARGUMENT;
    p = prov_of(s);
    if (!p) return otc__copy_str("{}", buf, len, needed); /* a missing provenance reads as {} */
    return otc__copy_json(p, buf, len, needed);
}

#define PROV_STR(NAME, KEY)                                                                    \
    otc_status NAME(const otc_set *s, char *buf, size_t len, size_t *needed)                   \
    {                                                                                          \
        return s ? otc__copy_str(otc__jstr(prov_of(s), KEY), buf, len, needed) : OTC_E_INVALID_ARGUMENT; \
    }
#define PROV_JSON(NAME, KEY)                                                                   \
    otc_status NAME(const otc_set *s, char *buf, size_t len, size_t *needed)                   \
    {                                                                                          \
        return s ? otc__copy_json(otc__jget(prov_of(s), KEY), buf, len, needed) : OTC_E_INVALID_ARGUMENT; \
    }
PROV_STR(otc_set_provenance_build_commit, "build_commit")
PROV_STR(otc_set_provenance_adapter_version, "adapter_version")
PROV_STR(otc_set_provenance_selection_reason, "selection_reason")
PROV_JSON(otc_set_provenance_input_sha256_json, "input_sha256")
PROV_JSON(otc_set_provenance_time_base_json, "time_base")
PROV_JSON(otc_set_provenance_decision_json, "decision")

size_t otc_set_validation_count(const otc_set *s) { return s ? s->n_val : 0; }
otc_status otc_set_validation_at(const otc_set *s, size_t i, const otc_validation_t **out)
{
    if (!s || !out || i >= s->n_val) return OTC_E_INVALID_ARGUMENT;
    *out = s->val[i];
    return OTC_OK;
}

size_t otc_set_constituent_count(const otc_set *s) { return s ? s->n_cons : 0; }
otc_status otc_set_constituent_at(const otc_set *s, size_t i, const otc_constituent_t **out)
{
    if (!s || !out || i >= s->n_cons) return OTC_E_INVALID_ARGUMENT;
    *out = &s->cons[i];
    return OTC_OK;
}
otc_status otc_set_constituent(const otc_set *s, const char *name, const otc_constituent_t **out)
{
    size_t i;
    if (!s || !out || !name) return OTC_E_INVALID_ARGUMENT;
    *out = NULL;
    for (i = 0; i < s->n_cons; i++)
        if (!strcmp(s->cons[i].name, name)) { *out = &s->cons[i]; return OTC_OK; }
    return OTC_E_NOT_FOUND;
}
otc_status otc_constituent_raw_json(const otc_set *s, size_t i, char *buf, size_t len, size_t *needed)
{
    const cJSON *cons;
    if (!s || i >= s->n_cons) return OTC_E_INVALID_ARGUMENT;
    cons = otc__jget(s->json, "constituents");
    return otc__copy_json(cJSON_GetArrayItem(cons, (int)i), buf, len, needed);
}
