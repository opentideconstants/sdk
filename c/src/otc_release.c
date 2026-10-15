/* Opening a release (.jsonl + .meta.json), the stream index, release
 * metadata, conventions, licences, stats, citation and attribution
 * (SDK spec 4.2, 4.3, 4.6, 5.3, 6.2, 6.4, 7.3, 7.4). */
#include "otc_internal.h"

#include <errno.h>
#include <stddef.h>

/* the reference links a walk follows (spec 6.2 kind, 4.6 attribution) */
#define OTC__MAX_LINKS 16

/* --------------------------------------------------------------- options */

void otc_open_options_init(otc_open_options *opts)
{
    if (!opts) return;
    memset(opts, 0, sizeof *opts);
    opts->struct_size = sizeof *opts;
}

void otc_filter_init(otc_filter *filter)
{
    if (!filter) return;
    memset(filter, 0, sizeof *filter);
    filter->struct_size = sizeof *filter;
}

/* ------------------------------------------------------------ last error */

otc_status otc__fail(const otc_release *rel, otc_status st, const char *fmt, ...)
{
    otc_release *r = (otc_release *)rel; /* the error slot is the only mutable state */
    va_list ap;
    if (!r || st == OTC_OK || st == OTC_E_NOT_FOUND || st == OTC_E_BUFFER_TOO_SMALL) return st;
    otc__mutex_lock(&r->lock);
    r->last_status = st;
    va_start(ap, fmt);
    vsnprintf(r->last_message, sizeof r->last_message, fmt, ap);
    va_end(ap);
    otc__mutex_unlock(&r->lock);
    return st;
}

otc_status otc_last_error(const otc_release *rel, char *buf, size_t len, size_t *needed)
{
    otc_release *r = (otc_release *)rel;
    otc_status st;
    if (!r) return OTC_E_INVALID_ARGUMENT;
    otc__mutex_lock(&r->lock);
    st = r->last_status == OTC_OK ? otc__copy_str(NULL, buf, len, needed)
                                  : otc__copy_str(r->last_message, buf, len, needed);
    otc__mutex_unlock(&r->lock);
    return st;
}

otc_status otc_last_error_status(const otc_release *rel)
{
    otc_release *r = (otc_release *)rel;
    otc_status st;
    if (!r) return OTC_E_INVALID_ARGUMENT;
    otc__mutex_lock(&r->lock);
    st = r->last_status;
    otc__mutex_unlock(&r->lock);
    return st;
}

/* ---------------------------------------------------------------- lookups */

static int entry_cmp(const void *a, const void *b)
{
    return strcmp(((const otc__entry *)a)->id, ((const otc__entry *)b)->id);
}

static int tomb_cmp(const void *a, const void *b)
{
    return strcmp(((const otc__tomb *)a)->id, ((const otc__tomb *)b)->id);
}

static int alias_cmp(const void *a, const void *b)
{
    const otc__alias *x = (const otc__alias *)a, *y = (const otc__alias *)b;
    int c = strcmp(x->system, y->system);
    return c ? c : otc__bytes_cmp(x->alias, x->alias_len, y->alias, y->alias_len);
}

const otc__entry *otc__find_entry(const otc_release *rel, const char *id)
{
    otc__entry key;
    if (!rel || !id || !rel->n_st) return NULL;
    key.id = (char *)id;
    return (const otc__entry *)bsearch(&key, rel->st, rel->n_st, sizeof key, entry_cmp);
}

const otc__tomb *otc__find_tomb(const otc_release *rel, const char *id)
{
    otc__tomb key;
    if (!rel || !id || !rel->n_tomb) return NULL;
    key.id = (char *)id;
    return (const otc__tomb *)bsearch(&key, rel->tomb, rel->n_tomb, sizeof key, tomb_cmp);
}

const otc_convention *otc__find_convention(const otc_release *rel, const char *id)
{
    size_t i;
    if (!id) return NULL;
    for (i = 0; i < rel->n_conv; i++)
        if (rel->conv[i].id && !strcmp(rel->conv[i].id, id)) return &rel->conv[i];
    return NULL;
}

const otc_licence *otc__find_licence(const otc_release *rel, const char *id)
{
    size_t i;
    if (!id) return NULL;
    for (i = 0; i < rel->n_lic; i++)
        if (rel->lic[i].id && !strcmp(rel->lic[i].id, id)) return &rel->lic[i];
    return NULL;
}

otc_status otc__read_line(const otc_release *rel, uint64_t offset, size_t length, cJSON **out)
{
    char *buf = (char *)malloc(length + 1);
    cJSON *v;
    otc_status st;
    *out = NULL;
    if (!buf) return otc__fail(rel, OTC_E_NOMEM, "out of memory");
    if (otc__file_pread(rel->file, buf, length, offset) != 0) {
        free(buf);
        return otc__fail(rel, OTC_E_IO, "cannot read %s at offset %lu", rel->path, (unsigned long)offset);
    }
    buf[length] = '\0';
    st = otc__json_parse_st(buf, length, &v);
    free(buf);
    if (st == OTC_E_NOMEM) return otc__fail(rel, st, "out of memory");
    if (!v) return otc__fail(rel, OTC_E_INVALID_RELEASE, "a line of %s is not JSON (it changed after open?)", rel->path);
    *out = v;
    return OTC_OK;
}

static const char *path_base(const char *path);
static const char *line_problem(const otc_release *r, const cJSON *root, char *buf, size_t cap);
static uint64_t line_view(const cJSON *root, unsigned fields);
enum {
    IX_OWN = 1u, IX_CURRENT = 2u, IX_FALLBACK = 4u, IX_BINS = 8u,
    IX_PRIVATE = 16u, IX_CURRENT_FULL = 32u
};

otc_status otc__read_station_line(const otc_release *rel, const char *id, uint64_t offset, size_t length,
                                  uint64_t view, cJSON **out)
{
    otc_status st = otc__read_line(rel, offset, length, out);
    char got[160], wbuf[160];
    const char *base, *why = NULL;
    char *dir, *ix;
    int removed;
    if (st != OTC_OK && !(st == OTC_E_INVALID_RELEASE && rel->index_used)) return st;
    if (st == OTC_OK && otc__jstr(*out, "station_id") && !strcmp(otc__jstr(*out, "station_id"), id)) {
        if (!rel->index_used) return OTC_OK;
        /* PK-R2-07: a line read through the index gets the checks of the full pass, and
         * it gives its entry's status, references and sets */
        why = line_problem(rel, *out, wbuf, sizeof wbuf);
        {
            const otc__entry *entry = otc__find_entry(rel, id);
            unsigned fields = entry ? entry->index_view_fields : rel->index_fields;
            if (!why && line_view(*out, fields) == view) return OTC_OK;
        }
        snprintf(got, sizeof got, "%s", why ? why : "a line that does not give the status, references and sets of its entry");
    } else {
        snprintf(got, sizeof got, "%s", st != OTC_OK ? "not JSON"
                 : otc__jstr(*out, "station_id") ? otc__jstr(*out, "station_id") : "not a station");
    }
    cJSON_Delete(*out);
    *out = NULL;
    if (!rel->index_used)
        return otc__fail(rel, OTC_E_INVALID_RELEASE, "the line at offset %llu of %s is not station %s (it changed after open?)",
                         (unsigned long long)offset, rel->path, id);
    /* spec 6.2 (CR D4): the index does not match the line; delete it so the next open rebuilds it */
    base = path_base(rel->path);
    dir = otc__strndup(rel->path, (size_t)(base - rel->path));
    ix = dir ? otc__join(dir, "index-v1.json") : NULL;
    /* another thread that read the same line may have deleted it first */
    removed = ix && (otc__remove_file(ix) == 0 || errno == ENOENT);
    free(ix);
    free(dir);
    return otc__fail(rel, OTC_E_INVALID_RELEASE,
                     "index-v1.json names the line at offset %llu of %s for station %s, but the line is %s; the "
                     "index is stale%s", (unsigned long long)offset, rel->path, id, got,
                     removed ? " and was deleted (the next open rebuilds it)" : " and could not be deleted");
}

/* ----------------------------------------------------------------- close */

static void free_entry(otc__entry *e)
{
    size_t i;
    free(e->id);
    free(e->name);
    free(e->folded);
    free(e->country);
    free(e->type_s);
    free(e->rec_source_type);
    free(e->rec_licence);
    free(e->ref_id);
    free(e->off_licence);
    free(e->eff_source_type);
    free(e->eff_licence);
    free(e->offsets_ref_licence);
    cJSON_Delete(e->sets_json);
    cJSON_Delete(e->own_offsets);
    cJSON_Delete(e->current_offsets);
    for (i = 0; i < e->n_sources; i++) free(e->sources[i]);
    free(e->sources);
}

static void free_files(otc_file_info *f, size_t n)
{
    size_t i;
    for (i = 0; i < n; i++) {
        free(f[i].name);
        free(f[i].url);
        free(f[i].sha256);
    }
    free(f);
}

static void release_clear_resource_fields(otc_release *rel)
{
    size_t i;
    otc__file_close(rel->file);
    free(rel->path);
    while (rel->astro) { otc_astro_tab *next = rel->astro->next; free(rel->astro); rel->astro = next; }
    cJSON_Delete(rel->meta);
    free(rel->conv);
    free(rel->lic);
    for (i = 0; i < rel->n_st; i++) free_entry(&rel->st[i]);
    free(rel->st);
    for (i = 0; i < rel->n_tomb; i++) free(rel->tomb[i].id);
    free(rel->tomb);
    for (i = 0; i < rel->n_alias; i++) {
        free(rel->alias[i].system);
        free(rel->alias[i].alias);
        free(rel->alias[i].station);
    }
    free(rel->alias);
    for (i = 0; i < rel->n_cnames; i++) free(rel->cnames[i]);
    free(rel->cnames);
    free_files(rel->files, rel->n_files);
    free(rel->zenodo_version_doi);
    otc__kv_free(&rel->source_counts);
    otc__kv_free(&rel->qc_counts);
}

void otc_close(otc_release *rel)
{
    if (!rel) return;
    release_clear_resource_fields(rel);
    otc__mutex_destroy(&rel->lock);
    free(rel);
}
/* ------------------------------------------------------------------ open */

typedef struct builder {
    otc_release *rel;
    otc_error   *err;
    size_t       cap_st, cap_tomb, cap_alias, cap_cn;
    size_t       line_no;
    size_t      *cn_slots;   /* open addressing over rel->cnames: index + 1, 0 = empty */
    size_t       cn_slots_cap;
    char       **set_ids;    /* every set_id of the active stations, checked once across the release */
    size_t       n_set_ids, cap_set_ids;
    char       **unknown;    /* "<station_id> <status>" of each line whose status the library does not know */
    size_t       n_unknown, cap_unknown;
    /* commercial_only (spec 4.2, K-NC DR106), per station line, while its sets are read: the position of the
     * set being read and of the recommended set; for each typed quantity (water_level, current, other) and
     * qc_status (ok, flagged), the first set in file order with a commercial licence (position, source_type,
     * licence_id; borrowed from the line); and the licence of the first noaa water_level set with constants */
    long         set_pos, rec_pos;
    long         cand_pos[3][2];
    const char  *cand_type[3][2], *cand_lic[3][2];
    const char  *ref_lic;
} builder;

/* The source of every subordinate_offsets in format 1.0 (spec 4.2, K-NC DR106). */
#define OTC__OFFSETS_SOURCE "noaa"

/* The row of a typed quantity in builder.cand: water_level 0, current 1, any other value 2; -1 for none (a
 * set with no quantity never matches, spec 4.2). */
static int quantity_row(otc_quantity q)
{
    return q == OTC_QUANTITY_WATER_LEVEL ? 0 : q == OTC_QUANTITY_CURRENT ? 1 : q == OTC_QUANTITY_OTHER ? 2 : -1;
}

static bool licence_commercial(const otc_release *r, const char *id)
{
    const otc_licence *l = id ? otc__find_licence(r, id) : NULL;
    return l && l->commercial_use;
}

#define GROW(ptr, n, cap)                                                        \
    do {                                                                         \
        if ((n) == (cap)) {                                                      \
            size_t nc_ = (cap) ? (cap) * 2 : 16;                                 \
            void *np_ = realloc((ptr), nc_ * sizeof *(ptr));                     \
            if (!np_) return OTC_E_NOMEM;                                        \
            (ptr) = np_;                                                         \
            (cap) = nc_;                                                         \
        }                                                                        \
    } while (0)

static otc_status bad_line(builder *b, const char *what)
{
    otc__err_set(b->err, OTC_E_INVALID_RELEASE, b->rel->path, "%s line %lu: %s", b->rel->path,
                 (unsigned long)b->line_no, what);
    return OTC_E_INVALID_RELEASE;
}

static size_t name_hash(const char *s)
{
    size_t h = (size_t)2166136261u;
    while (*s) h = (h ^ (unsigned char)*s++) * (size_t)16777619u;
    return h;
}

/* Adds a constituent name once. A hash set over rel->cnames keeps this
 * linear in the number of constituents (spec 6.5), not quadratic. */
static otc_status add_cname(builder *b, const char *name)
{
    otc_release *r = b->rel;
    size_t i, mask;
    if (r->n_cnames * 2 >= b->cn_slots_cap) {   /* grow (and fill) the table at half full */
        size_t cap = b->cn_slots_cap ? b->cn_slots_cap * 2 : 64, k;
        size_t *t = (size_t *)calloc(cap, sizeof *t);
        if (!t) return OTC_E_NOMEM;
        for (k = 0; k < r->n_cnames; k++) {
            for (i = name_hash(r->cnames[k]) & (cap - 1); t[i]; i = (i + 1) & (cap - 1)) {}
            t[i] = k + 1;
        }
        free(b->cn_slots);
        b->cn_slots = t;
        b->cn_slots_cap = cap;
    }
    mask = b->cn_slots_cap - 1;
    for (i = name_hash(name) & mask; b->cn_slots[i]; i = (i + 1) & mask)
        if (!strcmp(r->cnames[b->cn_slots[i] - 1], name)) return OTC_OK;
    GROW(r->cnames, r->n_cnames, b->cap_cn);
    r->cnames[r->n_cnames] = otc__strdup(name);
    if (!r->cnames[r->n_cnames]) return OTC_E_NOMEM;
    b->cn_slots[i] = ++r->n_cnames;
    return OTC_OK;
}

/* alias: the id's string node, kept in full (an alias id may hold a NUL, CR2 DR33). */
static otc_status add_alias(builder *b, const char *system, const cJSON *alias, const char *station)
{
    otc_release *r = b->rel;
    GROW(r->alias, r->n_alias, b->cap_alias);
    r->alias[r->n_alias].system = otc__strdup(system);
    r->alias[r->n_alias].alias_len = otc__jstr_len(alias);
    r->alias[r->n_alias].alias = otc__strndup(alias->valuestring, r->alias[r->n_alias].alias_len);
    r->alias[r->n_alias].station = otc__strdup(station);
    r->n_alias++;
    if (!r->alias[r->n_alias - 1].system || !r->alias[r->n_alias - 1].alias || !r->alias[r->n_alias - 1].station)
        return OTC_E_NOMEM;
    return OTC_OK;
}

/* The JSON type of each known field that the SDK reads (spec 7.3: tolerant is
 * not lax; CR2 PK-R2-05). Absent or null is always allowed here; required
 * fields are checked where they are used. T a string, N a finite number, I a
 * finite number with an integral value, O an object, L a list of objects, S a
 * list of strings, A a list. The same table is in the Python, Ruby and
 * TypeScript SDKs. */
typedef struct {
    const char *key;
    char        type;
} field_type;

static const field_type STATION_TYPES[] = {
    {"name", 'T'}, {"country", 'T'}, {"timezone", 'T'}, {"type", 'T'}, {"recommended_set_id", 'T'}, {"status", 'T'},
    {"constant_sets", 'L'}, {"validation", 'L'}, {"subordinate_offsets", 'O'}, {"current_offsets", 'A'}, {"source_records", 'L'}, {"recommended_is_fallback", 'B'}, {NULL, 0}};
static const field_type OFFSET_TYPES[] = {
    {"reference_station_id", 'T'}, {"licence_id", 'T'}, {"height_adjusted_type", 'T'}, {"time_offset_high_min", 'N'},
    {"time_offset_low_min", 'N'}, {"height_offset_high", 'N'}, {"height_offset_low", 'N'}, {"offset_id", 'T'}, {"source", 'T'}, {"source_type", 'T'}, {"source_version", 'T'}, {"source_record_id", 'T'}, {"qc_status", 'T'}, {"qc_flags", 'L'}, {"fallback", 'O'}, {"vintage", 'O'}, {"provenance", 'O'}, {NULL, 0}};
static const field_type VALIDATION_TYPES[] = {
    {"set_id", 'T'}, {"reference_source", 'T'}, {"reference_station", 'T'}, {"window", 'T'},
    {"reference_distance_km", 'N'}, {"time_mae_min", 'N'}, {"time_p95_min", 'N'}, {"time_bias_min", 'N'},
    {"height_mae_m", 'N'}, {"range_error_m", 'N'}, {"missed_events", 'I'}, {"extra_events", 'I'},
    {"previous_release", 'O'}, {NULL, 0}};
static const field_type SET_TYPES[] = {
    {"set_id", 'T'}, {"source", 'T'}, {"source_type", 'T'}, {"quantity", 'T'}, {"source_record_id", 'T'},
    {"source_version", 'T'}, {"convention_id", 'T'}, {"licence_id", 'T'}, {"qc_status", 'T'}, {"constituents", 'L'},
    {"dropped_constituents", 'L'}, {"qc_flags", 'L'}, {"record_span", 'O'}, {"datum", 'O'}, {"time_base", 'O'},
    {"provenance", 'O'}, {"current_bins", 'A'}, {"fallback", 'O'}, {NULL, 0}};
static const field_type SPAN_TYPES[] = {{"good_samples", 'I'}, {NULL, 0}};
static const field_type DATUM_TYPES[] = {{"msl_offset_m", 'N'}, {"named", 'O'}, {NULL, 0}};
static const field_type CONSTITUENT_TYPES[] = {
    {"name", 'T'}, {"source_name", 'T'}, {"doodson", 'T'}, {"kept_reason", 'T'}, {"speed_deg_per_hour", 'N'},
    {"amplitude_m", 'N'}, {"phase_deg", 'N'}, {"amp_uncertainty_m", 'N'}, {"phase_uncertainty_deg", 'N'}, {NULL, 0}};
static const field_type QC_FLAG_TYPES[] = {{"flag", 'T'}, {"reason", 'T'}, {"values", 'O'}, {NULL, 0}};
static const field_type DROPPED_TYPES[] = {{"name", 'T'}, {"dropped_reason", 'T'}, {"detail", 'T'}, {NULL, 0}};
static const field_type TIME_BASE_TYPES[] = {
    {"code", 'T'}, {"reason", 'T'}, {"declared", 'T'}, {"published", 'T'}, {"decided_in", 'T'},
    {"decided_build_commit", 'T'}, {"correction", 'O'}, {"months_dropped", 'S'}, {"evidence", 'L'}, {NULL, 0}};
static const field_type CORRECTION_TYPES[] = {{"from", 'T'}, {"to", 'T'}, {NULL, 0}};
static const field_type EVIDENCE_TYPES[] = {
    {"comparator_kind", 'T'}, {"comparator_id", 'T'}, {"detail", 'T'}, {"distance_km", 'N'}, {"lag_min", 'N'},
    {NULL, 0}};
static const field_type PROVENANCE_TYPES[] = {
    {"adapter_version", 'T'}, {"carried_from_release", 'T'}, {"selection_reason", 'T'}, {"input_sha256", 'S'},
    {"decision", 'O'}, {NULL, 0}};

static int finite_number(const cJSON *v) { return cJSON_IsNumber(v) && isfinite(v->valuedouble); }

static int field_type_ok(const cJSON *v, char type)
{
    const cJSON *x;
    if (!v || cJSON_IsNull(v)) return 1;
    switch (type) {
    case 'B': return cJSON_IsBool(v);
    case 'T': return cJSON_IsString(v);
    case 'N': return finite_number(v);
    case 'I': return finite_number(v) && v->valuedouble == floor(v->valuedouble);
    case 'O': return cJSON_IsObject(v);
    case 'L':
    case 'S':
        if (!cJSON_IsArray(v)) return 0;
        cJSON_ArrayForEach(x, v) {
            if (type == 'L' ? !cJSON_IsObject(x) : !cJSON_IsString(x)) return 0;
        }
        return 1;
    default: return cJSON_IsArray(v);
    }
}

/* The first field of o (an object, or NULL/null for none) with the wrong type, or NULL. */
static const char *wrong_field(const cJSON *o, const field_type *table)
{
    for (; o && cJSON_IsObject(o) && table->key; table++)
        if (!field_type_ok(otc__jget(o, table->key), table->type)) return table->key;
    return NULL;
}

static const field_type FALLBACK_TYPES[] = {{"reason", 'T'}, {"basis", 'T'}, {"otc_finding", 'T'}, {"preferred_set_id", 'T'}, {NULL, 0}};
static const field_type SOURCE_TYPES[] = {{"source", 'T'}, {"source_version", 'T'}, {"source_record_id", 'T'}, {"role", 'T'}, {"disposition", 'T'}, {"detail", 'T'}, {"licence_id", 'T'}, {"upstream_licence_id", 'T'}, {"published_set_ids", 'S'}, {"provenance", 'O'}, {"original_metadata", 'O'}, {"original_harmonics", 'O'}, {NULL, 0}};
static const field_type SOURCE_PROVENANCE_TYPES[] = {{"input_sha256", 'S'}, {"inventory_sha256", 'T'}, {NULL, 0}};
static const field_type HARMONIC_TYPES[] = {{"format", 'T'}, {"columns", 'S'}, {"rows", 'A'}, {"annotations", 'L'}, {"amplitude_unit", 'T'}, {"amplitude_unit_basis", 'T'}, {"phase_unit", 'T'}, {"phase_convention", 'T'}, {"amplitude_uncertainty_unit", 'T'}, {"amplitude_uncertainty_unit_basis", 'T'}, {NULL, 0}};

/* 1 when every member of o (an object, or NULL/null) is a finite number, or also null when null_ok. */
static int numbers_only(const cJSON *o, int null_ok)
{
    const cJSON *x;
    if (!cJSON_IsObject(o)) return 1;
    cJSON_ArrayForEach(x, o) {
        if (!finite_number(x) && !(null_ok && cJSON_IsNull(x))) return 0;
    }
    return 1;
}

/* "<where><key> has the wrong type" in buf */
static const char *wrong_type(char *buf, size_t cap, const char *where, const char *key)
{
    snprintf(buf, cap, "%s%s has the wrong type", where, key);
    return buf;
}

/* Every known field of an active station line has its JSON type (spec 6.1, 7.3), so a malformed line fails the
 * open with OTC_E_INVALID_RELEASE, never a value read as missing. NULL when they do, else what is wrong (in buf, or
 * a constant string). */
static const char *types_problem(const cJSON *root, char *buf, size_t cap)
{
    const cJSON *x, *s, *f, *e, *tb;
    const char *k;
    if ((k = wrong_field(root, STATION_TYPES))) return wrong_type(buf, cap, "", k);
    if ((k = wrong_field(otc__jget(root, "subordinate_offsets"), OFFSET_TYPES)))
        return wrong_type(buf, cap, "subordinate_offsets.", k);
    cJSON_ArrayForEach(s, otc__jget(root, "source_records")) {
        const cJSON *harm = otc__jget(s, "original_harmonics"), *row, *cell;
        if ((k = wrong_field(s, SOURCE_TYPES))) return wrong_type(buf, cap, "source_records.", k);
        if ((k = wrong_field(otc__jget(s, "provenance"), SOURCE_PROVENANCE_TYPES))) return wrong_type(buf, cap, "source provenance.", k);
        if (cJSON_GetObjectItemCaseSensitive(s, "original_metadata") && !cJSON_IsObject(otc__jget(s, "original_metadata"))) return "original_metadata must be an object";
        if ((k = wrong_field(harm, HARMONIC_TYPES))) return wrong_type(buf, cap, "original_harmonics.", k);
        cJSON_ArrayForEach(row, otc__jget(harm, "rows")) {
            if (!cJSON_IsArray(row)) return "original_harmonics.rows must contain arrays of strings";
            cJSON_ArrayForEach(cell, row) if (!cJSON_IsString(cell)) return "original_harmonics.rows must contain strings";
        }
    }
    cJSON_ArrayForEach(x, otc__jget(root, "validation")) {
        if ((k = wrong_field(x, VALIDATION_TYPES))) return wrong_type(buf, cap, "validation.", k);
    }
    cJSON_ArrayForEach(s, otc__jget(root, "constant_sets")) {
        if ((k = wrong_field(s, SET_TYPES))) return wrong_type(buf, cap, "constant set ", k);
        if ((k = wrong_field(otc__jget(s, "record_span"), SPAN_TYPES))) return wrong_type(buf, cap, "record_span.", k);
        if ((k = wrong_field(otc__jget(s, "datum"), DATUM_TYPES))) return wrong_type(buf, cap, "datum.", k);
        if ((k = wrong_field(otc__jget(s, "provenance"), PROVENANCE_TYPES))) return wrong_type(buf, cap, "provenance.", k);
        if ((k = wrong_field(otc__jget(s, "fallback"), FALLBACK_TYPES))) return wrong_type(buf, cap, "fallback.", k);
        tb = otc__jget(s, "time_base");
        if ((k = wrong_field(tb, TIME_BASE_TYPES))) return wrong_type(buf, cap, "time_base.", k);
        if ((k = wrong_field(otc__jget(tb, "correction"), CORRECTION_TYPES)))
            return wrong_type(buf, cap, "time_base.correction.", k);
        cJSON_ArrayForEach(e, otc__jget(tb, "evidence")) {
            if ((k = wrong_field(e, EVIDENCE_TYPES))) return wrong_type(buf, cap, "time_base.evidence.", k);
        }
        if (!numbers_only(otc__jget(otc__jget(s, "datum"), "named"), 0))
            return "datum.named has a value that is not a number";
        cJSON_ArrayForEach(x, otc__jget(s, "constituents")) {
            if ((k = wrong_field(x, CONSTITUENT_TYPES))) return wrong_type(buf, cap, "constituent ", k);
        }
        cJSON_ArrayForEach(x, otc__jget(s, "dropped_constituents")) {
            if ((k = wrong_field(x, DROPPED_TYPES))) return wrong_type(buf, cap, "dropped constituent ", k);
        }
        cJSON_ArrayForEach(f, otc__jget(s, "qc_flags")) {
            if ((k = wrong_field(f, QC_FLAG_TYPES))) return wrong_type(buf, cap, "qc_flags.", k);
            if (!numbers_only(otc__jget(f, "values"), 1)) return "a qc_flags value is not a number or null";
        }
    }
    return NULL;
}

static int str_ptr_cmp(const void *a, const void *b);

/* spec 6.1 (CR2 DR22): a constituent name appears once in a set. Sorted, so a
 * set of n constituents costs n log n, not n * n. */
static otc_status names_once(builder *b, const cJSON *cons)
{
    const cJSON *c;
    const char **names;
    size_t n = 0, i;
    int twice = 0;
    if (!cons || cJSON_GetArraySize(cons) < 2) return OTC_OK;
    names = (const char **)malloc((size_t)cJSON_GetArraySize(cons) * sizeof *names);
    if (!names) return OTC_E_NOMEM;
    cJSON_ArrayForEach(c, cons) names[n++] = otc__jstr(c, "name");
    qsort(names, n, sizeof *names, str_ptr_cmp);
    for (i = 1; i < n && !twice; i++) twice = !strcmp(names[i - 1], names[i]);
    free(names);
    return twice ? bad_line(b, "a constituent name appears twice in a set") : OTC_OK;
}

/* The checks of the full pass on one station line (spec 6.1, 7.3), with no side
 * effect: NULL when the line passes them, else what is wrong (in buf, or a
 * constant string). The pass uses it, and so does a query that reads a line
 * through the stream index (PK-R2-07). */
static const char *line_problem(const otc_release *r, const cJSON *root, char *buf, size_t cap)
{
    const char *id = otc__jstr(root, "station_id"), *status = otc__jstr(root, "status"), *why;
    const cJSON *aliases, *a, *sets, *s, *off, *rec_id;
    int rec_found = 0;
    if (cJSON_IsObject(root) && !otc__jget(root, "status")) status = "active";   /* no status (or null): active (CR2 DR28) */
    if (!cJSON_IsObject(root) || !id || !status) return "not a station object with station_id and status";
    if (strcmp(status, "active") != 0) return NULL;   /* a tombstone, or another status (7.3) */
    aliases = otc__jget(root, "aliases");
    sets = otc__jget(root, "constant_sets");
    off = otc__jget(root, "subordinate_offsets");
    rec_id = otc__jstr_item(root, "recommended_set_id");
    if (!otc__jstr(root, "name") || !cJSON_IsNumber(otc__jget(root, "lat")) || !cJSON_IsNumber(otc__jget(root, "lon"))
        || !otc__jstr(root, "type"))
        return "an active station lacks name, lat, lon or type";
    if (!finite_number(otc__jget(root, "lat")) || !finite_number(otc__jget(root, "lon"))
        || fabs(otc__jget(root, "lat")->valuedouble) > 90 || fabs(otc__jget(root, "lon")->valuedouble) > 180)
        return "lat or lon is not a number in range";
    if ((why = types_problem(root, buf, cap)) != NULL) return why;   /* CR2 PK-R2-05 */
    if ((sets && !cJSON_IsArray(sets)) || (aliases && !cJSON_IsObject(aliases)))
        return "constant_sets is not an array or aliases is not an object";
    /* spec 4.5: a link that does not resolve fails the open (the reference station
     * is checked when every line is in) */
    if (cJSON_IsObject(off) && otc__jstr(off, "licence_id") && !otc__find_licence(r, otc__jstr(off, "licence_id")))
        return "subordinate_offsets.licence_id does not resolve";
    {
        const cJSON *records = cJSON_GetObjectItemCaseSensitive(root, "source_records"), *record;
        static const char *const required[] = {"source", "source_version", "source_record_id", "role", "disposition", "detail", NULL};
        if (records && (!cJSON_IsArray(records) || !cJSON_GetArraySize(records))) return "source_records must be a nonempty array";
        cJSON_ArrayForEach(record, records) {
            size_t ri;
            const cJSON *p = otc__jget(record, "provenance");
            const char *lid = otc__jstr(record, "licence_id"), *up = otc__jstr(record, "upstream_licence_id");
            for (ri = 0; required[ri]; ri++) if (!otc__jstr(record, required[ri]) || !*otc__jstr(record, required[ri])) return "source record lacks required identity";
            if (!cJSON_GetObjectItemCaseSensitive(record, "licence_id") || !cJSON_IsArray(otc__jget(record, "published_set_ids")) || !cJSON_IsObject(p) || !cJSON_IsArray(otc__jget(p, "input_sha256")) || !otc__jstr(p, "inventory_sha256")) return "source record lacks provenance or published ids";
            if ((lid && !otc__find_licence(r, lid)) || (up && !otc__find_licence(r, up))) return "source record licence does not resolve";
        }
    }
    if (cJSON_IsObject(off)) {
        const cJSON *flag; int historical = cJSON_GetObjectItemCaseSensitive(off, "offset_id") != NULL || otc__jstr_is(otc__jstr_item(otc__jget(off, "fallback"), "reason"), "historical_offsets");
        cJSON_ArrayForEach(flag, otc__jget(off, "qc_flags")) if (otc__jstr_is(otc__jstr_item(flag, "flag"), "fallback:historical_offsets")) historical = 1;
        if (historical && !otc__historical_valid(off)) return "invalid historical own-offset profile";
    }
    cJSON_ArrayForEach(s, sets) {
        const cJSON *t, *cons = otc__jget(s, "constituents"), *c;
        const cJSON *sid = otc__jstr_item(s, "set_id");
        for (t = sets->child; sid && t != s; t = t->next)   /* spec 6.1 (CR D5): a set_id once per station */
            if (otc__jstr_same(otc__jstr_item(t, "set_id"), sid)) return "a set_id appears twice in the station";   /* in full (CR2 DR33) */
        if (otc__jstr_is(otc__jstr_item(otc__jget(s, "fallback"), "reason"), "historical_offsets")) return "historical offsets cannot be a constant set";
        if (!cJSON_IsObject(s) || !sid || !otc__jstr(s, "source") || !otc__jstr(s, "qc_status"))
            return "a constant set lacks set_id, source or qc_status";
        if (!otc__find_convention(r, otc__jstr(s, "convention_id"))) return "a constant set's convention_id does not resolve";
        if (!otc__find_licence(r, otc__jstr(s, "licence_id"))) return "a constant set's licence_id does not resolve";
        if (cons && !cJSON_IsArray(cons)) return "constituents is not an array";
        if (otc__jget(s, "qc_flags") && !cJSON_IsArray(otc__jget(s, "qc_flags"))) return "qc_flags is not an array";
        {   /* spec 7.3 (CR2 DR6): a record_span time that is not an RFC 3339 time with real calendar fields */
            const cJSON *span = otc__jget(s, "record_span");
            static const char *const KEYS[] = {"start", "end"};
            size_t k;
            char tm[21];
            for (k = 0; k < 2 && cJSON_IsObject(span); k++) {
                const cJSON *v = otc__jget(span, KEYS[k]);
                if (v && !cJSON_IsNull(v) && !(cJSON_IsString(v) && otc__utc_time(v->valuestring, tm)))
                    return k ? "record_span.end is not an RFC 3339 time" : "record_span.start is not an RFC 3339 time";
            }
        }
        cJSON_ArrayForEach(c, cons) if (!otc__jstr(c, "name")) return "a constituent has no name";
        if (otc__jstr_same(rec_id, sid)) rec_found = 1;   /* in full: a NUL inside never matches less (CR2 DR33) */
    }
    if (rec_id && !rec_found) return "recommended_set_id does not resolve";
    cJSON_ArrayForEach(a, aliases) {
        const cJSON *x;
        if (cJSON_IsArray(a)) {
            cJSON_ArrayForEach(x, a) if (!cJSON_IsString(x)) return "an alias id is not a string";
        } else if (!cJSON_IsString(a)) {
            return "an alias is not a string or a list";
        }
    }
    return NULL;
}

/* Adds what the index needs from one constant set (line_problem checked it). */
static otc_status index_set(builder *b, const cJSON *set, otc__entry *e, const cJSON *rec_id)
{
    otc_release *r = b->rel;
    const char *source = otc__jstr(set, "source");
    const char *qc = otc__jstr(set, "qc_status");
    const char *lic = otc__jstr(set, "licence_id");
    const cJSON *cons = otc__jget(set, "constituents"), *c;
    otc_qc_status qcs;
    otc_status st;
    cJSON_ArrayForEach(c, cons) {
        if ((st = add_cname(b, otc__jstr(c, "name"))) != OTC_OK) return st;
    }
    if ((st = names_once(b, cons)) != OTC_OK) return st;
    /* spec 4.3: qc_status counts every set (a value format 1.0 does not have is
     * "other", 7.3); source counts, and the source filter sees, only sets with
     * constants (ok or flagged) */
    qcs = otc__parse_qc_status(qc);
    if ((st = otc__kv_add(&r->qc_counts, otc_qc_status_name(qcs), 1)) != OTC_OK) return st;
    if (qcs == OTC_QC_STATUS_OK || qcs == OTC_QC_STATUS_FLAGGED) {
        size_t i;
        int seen = 0;
        if ((st = otc__kv_add(&r->source_counts, source, 1)) != OTC_OK) return st;
        for (i = 0; i < e->n_sources; i++)
            if (!strcmp(e->sources[i], source)) seen = 1;
        if (!seen) {
            char **p = (char **)realloc(e->sources, (e->n_sources + 1) * sizeof *p);
            if (!p) return OTC_E_NOMEM;
            e->sources = p;
            if (!(e->sources[e->n_sources] = otc__strdup(source))) return OTC_E_NOMEM;
            e->n_sources++;
        }
    }
    if (r->commercial_only) {
        /* the candidates of the effective recommended set and the offsets' reference set (K-NC DR106) */
        otc_quantity q = otc__parse_quantity(otc__jstr(set, "quantity"));
        int row = quantity_row(q), col = qcs == OTC_QC_STATUS_OK ? 0 : qcs == OTC_QC_STATUS_FLAGGED ? 1 : -1;
        if (row >= 0 && col >= 0 && b->cand_pos[row][col] < 0 && licence_commercial(r, lic)) {
            b->cand_pos[row][col] = b->set_pos;
            b->cand_type[row][col] = otc__jstr(set, "source_type");
            b->cand_lic[row][col] = lic;
        }
        if (!b->ref_lic && col >= 0 && q == OTC_QUANTITY_WATER_LEVEL && source && !strcmp(source, OTC__OFFSETS_SOURCE))
            b->ref_lic = lic;
    }
    /* the first set with the recommended id (a repeated set_id is refused when every line is in) */
    if (!e->has_rec && otc__jstr_same(rec_id, otc__jstr_item(set, "set_id"))) {   /* in full: a NUL inside never matches less */
        e->has_rec = 1;
        b->rec_pos = b->set_pos;
        e->rec_quantity = otc__parse_quantity(otc__jstr(set, "quantity"));
        if (otc__jstr(set, "source_type") && !(e->rec_source_type = otc__strdup(otc__jstr(set, "source_type"))))
            return OTC_E_NOMEM;
        if (!(e->rec_licence = otc__strdup(lic))) return OTC_E_NOMEM;
    }
    return OTC_OK;
}

/* The key a set_id is compared by across the release, in full (CR2 DR33): the id
 * itself, or, for one with a NUL inside, 0xff and then its JSON literal (no valid
 * UTF-8 text has the byte 0xff, so it is no other id's key). NULL: out of memory. */
static char *set_id_key(const cJSON *sid)
{
    size_t n = otc__jstr_len(sid);
    char *lit, *key;
    if (n == strlen(sid->valuestring)) return otc__strdup(sid->valuestring);
    if (!(lit = otc__json_escape_n(sid->valuestring, n))) return NULL;
    key = (char *)malloc(strlen(lit) + 2);
    if (key) {
        key[0] = (char)0xff;
        memcpy(key + 1, lit, strlen(lit) + 1);
    }
    free(lit);
    return key;
}

/* The effective recommended set of a station under commercial_only (spec 4.2, K-NC DR106), from the candidates
 * that index_set kept: the release's recommended set when its licence allows commercial use; otherwise the first
 * set in file order of the same typed quantity, qc_status ok, with a commercial licence; then the same with
 * flagged; otherwise none. Also the licence of the offsets' reference set. */
static otc_status effective_set(builder *b, otc__entry *e)
{
    const char *type = NULL, *lic = NULL;
    e->eff_pos = -1;
    if (e->has_rec && licence_commercial(b->rel, e->rec_licence)) {
        e->eff_pos = b->rec_pos;
        type = e->rec_source_type;
        lic = e->rec_licence;
    } else if (e->has_rec && quantity_row(e->rec_quantity) >= 0) {
        int row = quantity_row(e->rec_quantity), col = b->cand_pos[row][0] >= 0 ? 0 : 1;
        if (b->cand_pos[row][col] >= 0) {
            e->eff_pos = b->cand_pos[row][col];
            type = b->cand_type[row][col];
            lic = b->cand_lic[row][col];
        }
    }
    if (e->eff_pos >= 0) {
        if ((type && !(e->eff_source_type = otc__strdup(type))) || !(e->eff_licence = otc__strdup(lic))) return OTC_E_NOMEM;
    }
    if (b->ref_lic && !(e->offsets_ref_licence = otc__strdup(b->ref_lic))) return OTC_E_NOMEM;
    return OTC_OK;
}

static cJSON *bin_numbers(const cJSON *bins)
{
    const cJSON *b;
    cJSON *out = cJSON_CreateArray();
    if (!out) return NULL;
    cJSON_ArrayForEach(b, bins) {
        double n = cJSON_IsNumber(b) ? b->valuedouble : otc__jnum(b, "bin");
        cJSON *v = isfinite(n) && n == floor(n) ? cJSON_CreateNumber(n) : cJSON_CreateNull();
        if (!v || !cJSON_AddItemToArray(out, v)) { cJSON_Delete(v); cJSON_Delete(out); return NULL; }
    }
    return out;
}
static cJSON *current_summaries(const cJSON *offsets)
{
    const cJSON *co;
    cJSON *out = cJSON_CreateArray();
    if (!out) return NULL;
    cJSON_ArrayForEach(co, offsets) {
        static const char *const keys[] = {"bin", "reference_bin", "reference_station_id", "licence_id", NULL};
        size_t i;
        cJSON *row = cJSON_CreateObject();
        if (!row) { cJSON_Delete(out); return NULL; }
        for (i = 0; keys[i]; i++) {
            const cJSON *v = cJSON_GetObjectItemCaseSensitive(co, keys[i]);
            cJSON *copy = v ? otc__json_dup(v) : cJSON_CreateNull();
            if (!copy || !cJSON_AddItemToObject(row, keys[i], copy)) { cJSON_Delete(copy); cJSON_Delete(row); cJSON_Delete(out); return NULL; }
        }
        if (!cJSON_AddItemToArray(out, row)) { cJSON_Delete(row); cJSON_Delete(out); return NULL; }
    }
    return out;
}

/* Indexes one parsed station line (root is not freed here). */
static otc_status index_parsed(builder *b, const cJSON *root, size_t len, uint64_t offset)
{
    otc_release *r = b->rel;
    const char *id, *status;
    otc_status st = OTC_OK;
    char wbuf[160];
    const char *why = line_problem(r, root, wbuf, sizeof wbuf);
    if (why) return bad_line(b, why);
    id = otc__jstr(root, "station_id");
    status = otc__jstr(root, "status");
    /* a line with no status (or null) is an active station, as in the stream index (CR2 DR28) */
    if (!otc__jget(root, "status")) status = "active";
    if (!strcmp(status, "removed")) {
        GROW(r->tomb, r->n_tomb, b->cap_tomb);
        r->tomb[r->n_tomb].id = otc__strdup(id);
        r->tomb[r->n_tomb].offset = offset;
        r->tomb[r->n_tomb].length = len;
        r->n_tomb++;
        if (!r->tomb[r->n_tomb - 1].id) st = OTC_E_NOMEM;
    } else if (!strcmp(status, "active")) {
        otc__entry *e;
        const cJSON *aliases = otc__jget(root, "aliases"), *a, *sets = otc__jget(root, "constant_sets"), *s;
        const cJSON *off = otc__jget(root, "subordinate_offsets");
        const cJSON *name = otc__jstr_item(root, "name"), *rec_id = otc__jstr_item(root, "recommended_set_id");
        const cJSON *lat = otc__jget(root, "lat"), *lon = otc__jget(root, "lon");
        if (r->n_st == b->cap_st) {
            size_t nc = b->cap_st ? b->cap_st * 2 : 64;
            otc__entry *np = (otc__entry *)realloc(r->st, nc * sizeof *np);
            if (!np) return OTC_E_NOMEM;
            r->st = np;
            b->cap_st = nc;
        }
        e = &r->st[r->n_st++];
        memset(e, 0, sizeof *e);
        e->eff_pos = -1;
        e->sets_json = cJSON_CreateArray();
        if (!e->sets_json) return OTC_E_NOMEM;
        cJSON_ArrayForEach(s, sets) {
            static const char *const keys[] = {"set_id", "source", "source_type", "quantity", "qc_status", "licence_id", "convention_id", "source_record_id", "fallback", "current_bins", NULL};
            cJSON *summary = cJSON_CreateObject();
            size_t ki;
            if (!summary) return OTC_E_NOMEM;
            for (ki = 0; keys[ki]; ki++) {
                const cJSON *val = cJSON_GetObjectItemCaseSensitive(s, keys[ki]);
                cJSON *copy = val ? (!strcmp(keys[ki], "current_bins") ? bin_numbers(val) : otc__json_dup(val)) : NULL;
                if (val && (!copy || !cJSON_AddItemToObject(summary, keys[ki], copy))) { cJSON_Delete(copy); cJSON_Delete(summary); return OTC_E_NOMEM; }
            }
            if (r->index_fields & IX_PRIVATE) {
                static const char *const private_keys[] = {"source_version", "datum", NULL};
                for (ki = 0; private_keys[ki]; ki++) {
                    const cJSON *value = cJSON_GetObjectItemCaseSensitive(s, private_keys[ki]);
                    cJSON *copy = value ? otc__json_dup(value) : NULL;
                    if (value && (!copy || !cJSON_AddItemToObject(summary, private_keys[ki], copy))) { cJSON_Delete(copy); cJSON_Delete(summary); return OTC_E_NOMEM; }
                }
            }
            if (!cJSON_AddItemToArray(e->sets_json, summary)) { cJSON_Delete(summary); return OTC_E_NOMEM; }
        }
        e->own_offsets = off ? otc__json_dup(off) : NULL;
        e->current_offsets = otc__jget(root, "current_offsets") ? current_summaries(otc__jget(root, "current_offsets")) : NULL;
        if ((off && !e->own_offsets) || (otc__jget(root, "current_offsets") && !e->current_offsets)) return OTC_E_NOMEM;
        e->offset = offset;
        e->length = len;
        e->lat = lat->valuedouble;
        e->lon = lon->valuedouble;
        e->type_s = otc__strdup(otc__jstr(root, "type"));
        e->type = otc__parse_station_type(e->type_s);
        e->id = otc__strdup(id);
        e->name_len = otc__jstr_len(name);   /* a schema-valid name may hold a NUL (spec 4.4.1) */
        e->name = otc__strndup(name->valuestring, e->name_len);
        e->folded = e->name ? otc__fold_n(e->name, e->name_len, &e->folded_len) : NULL;
        e->country = otc__strdup(otc__jstr(root, "country"));
        if (!e->id || !e->name || !e->folded || !e->type_s || (otc__jstr(root, "country") && !e->country))
            return OTC_E_NOMEM;
        if (cJSON_IsObject(off)) {
            const char *ref = otc__jstr(off, "reference_station_id"), *ol = otc__jstr(off, "licence_id");
            e->has_offsets = 1;
            e->ref_id = otc__strdup(ref);
            e->off_licence = otc__strdup(ol);
            if ((ref && !e->ref_id) || (ol && !e->off_licence)) return OTC_E_NOMEM;
        }
        {
            int qi, ci;
            b->set_pos = 0;
            b->rec_pos = -1;
            b->ref_lic = NULL;
            for (qi = 0; qi < 3; qi++)
                for (ci = 0; ci < 2; ci++) b->cand_pos[qi][ci] = -1;
        }
        cJSON_ArrayForEach(s, sets) {
            const cJSON *sid = otc__jstr_item(s, "set_id");
            if (sid) {   /* spec 6.1 (CR D5): a set_id once in the release; checked when every line is in */
                GROW(b->set_ids, b->n_set_ids, b->cap_set_ids);
                if (!(b->set_ids[b->n_set_ids] = set_id_key(sid))) return OTC_E_NOMEM;
                b->n_set_ids++;
            }
            if ((st = index_set(b, s, e, rec_id)) != OTC_OK) break;
            b->set_pos++;
        }
        if (st == OTC_OK && r->commercial_only) st = effective_set(b, e);
        if (st == OTC_OK) {
            cJSON_ArrayForEach(a, aliases) {
                if (cJSON_IsString(a)) {
                    st = add_alias(b, a->string, a, id);
                } else {
                    const cJSON *x;
                    cJSON_ArrayForEach(x, a) {
                        if ((st = add_alias(b, a->string, x, id)) != OTC_OK) break;
                    }
                }
                if (st != OTC_OK) break;
            }
        }
    } else {
        /* any other status: a newer minor's value (7.3). Not a station, not a tombstone, in no query and
         * no count; logged once when the open succeeds (CR2 DR8) */
        size_t n = strlen(id) + strlen(status) + 2;
        GROW(b->unknown, b->n_unknown, b->cap_unknown);
        if (!(b->unknown[b->n_unknown] = (char *)malloc(n))) return OTC_E_NOMEM;
        snprintf(b->unknown[b->n_unknown++], n, "%s %s", id, status);
    }
    return st;
}

static otc_status index_line(builder *b, const char *line, size_t len, uint64_t offset)
{
    cJSON *root;
    otc_status st = otc__json_parse_st(line, len, &root);
    if (st == OTC_E_NOMEM) return st;
    if (!root) return bad_line(b, "not JSON");
    if (!cJSON_IsObject(root)) {
        cJSON_Delete(root);
        return bad_line(b, "not a station object with station_id and status");
    }
    st = index_parsed(b, root, len, offset);
    cJSON_Delete(root);
    return st;
}

/* 1 when a line is empty or holds only ASCII whitespace: SP, HT, LF, VT, FF, CR
 * (spec 6.2, CR2 DR26, the reference bytes.strip rule). NUL is not blank. */
static int blank(const char *line, size_t len)
{
    size_t i;
    for (i = 0; i < len; i++)
        if (line[i] != ' ' && (line[i] < '\t' || line[i] > '\r')) return 0;
    return 1;
}

/* Calls fn for every line of the file that is not blank, with its offset and
 * its length without the line end (\n, or \r\n); line[len] is '\0'. *line_no
 * counts every line. */
typedef otc_status (*line_fn)(void *ctx, const char *line, size_t len, uint64_t offset);

static otc_status scan_lines(otc__file *f, size_t *line_no, line_fn fn, void *ctx)
{
    int64_t size = otc__file_size(f);
    size_t chunk = 1u << 16, cap = 1u << 16, n = 0;
    unsigned char *buf = (unsigned char *)malloc(chunk);
    char *line = (char *)malloc(cap);
    uint64_t off = 0, line_start = 0;
    otc_status st = OTC_OK;
    if (!buf || !line) { free(buf); free(line); return OTC_E_NOMEM; }
    if (size < 0) { free(buf); free(line); return OTC_E_IO; }
    while (off < (uint64_t)size && st == OTC_OK) {
        size_t got = (uint64_t)size - off > chunk ? chunk : (size_t)((uint64_t)size - off), i;
        if (otc__file_pread(f, buf, got, off) != 0) { st = OTC_E_IO; break; }
        for (i = 0; i < got && st == OTC_OK; i++) {
            if (buf[i] == '\n') {
                size_t len = n;
                (*line_no)++;
                if (len > 0 && line[len - 1] == '\r') len--;
                line[len] = '\0';
                if (!blank(line, len)) st = fn(ctx, line, len, line_start);
                n = 0;
                line_start = off + i + 1;
            } else {
                if (n + 1 >= cap) {
                    char *nl = (char *)realloc(line, cap * 2);
                    if (!nl) { st = OTC_E_NOMEM; break; }
                    line = nl;
                    cap *= 2;
                }
                line[n++] = (char)buf[i];
            }
        }
        off += got;
    }
    if (st == OTC_OK && n > 0) {
        (*line_no)++;
        line[n] = '\0';
        if (!blank(line, n)) st = fn(ctx, line, n, line_start);
    }
    free(buf);
    free(line);
    return st;
}

static otc_status index_line_cb(void *ctx, const char *line, size_t len, uint64_t offset)
{
    return index_line((builder *)ctx, line, len, offset);
}

/* Reads the .jsonl in sequence and indexes every line (spec 6.2). */
static otc_status index_file(builder *b)
{
    return scan_lines(b->rel->file, &b->line_no, index_line_cb, b);
}

/* ------------------------------------------------- the stream index file (spec 6.2) */

static const char *const SET_KEYS[] = {"set_id", "source", "source_type", "quantity", "qc_status", "convention_id",
                                       "licence_id", NULL};
static const char *const ENTRY_STR[] = {"name", "name_folded", "country", "type", "kind", "reference_station_id",
                                        "offsets_licence_id", "recommended_set_id", NULL};

/* The value of key, JSON null included (otc__jget leaves out null). */
static const cJSON *jraw(const cJSON *o, const char *key) { return cJSON_GetObjectItemCaseSensitive(o, key); }
static int str_or_null_ok(const cJSON *v) { return v && (cJSON_IsNull(v) || cJSON_IsString(v)); }
static int num_or_null_ok(const cJSON *v) { return v && (cJSON_IsNull(v) || cJSON_IsNumber(v)); }
static int whole_ok(const cJSON *v) { return cJSON_IsNumber(v) && v->valuedouble >= 0 && v->valuedouble == floor(v->valuedouble); }

static const char *const CURRENT_ADJUST[] = {
    "time_adj_max_flood_min", "time_adj_max_ebb_min", "time_adj_slack_before_flood_min",
    "time_adj_slack_before_ebb_min", "flood_amp_ratio", "ebb_amp_ratio", NULL
};

/* Recognized extensions are optional, but their presence cannot change profile
 * halfway through a document. Unknown keys and the informational by stay out. */
static int index_profile(const cJSON *doc, unsigned *fields)
{
    const cJSON *e, *s, *v, *co;
    int private_mode = -1, current_mode = -1, any_bins = 0, missing_bins = 0;
    unsigned mask = 0;
    cJSON_ArrayForEach(e, otc__jget(doc, "stations")) {
        v = jraw(e, "subordinate_offsets");
        if (v) {
            if (!cJSON_IsNull(v)) {
                static const char *const required[] = {"reference_station_id", "time_offset_high_min", "time_offset_low_min", "height_offset_high", "height_offset_low", "height_adjusted_type", NULL};
                size_t k;
                mask |= IX_OWN;
                if (!cJSON_IsObject(v) || wrong_field(v, OFFSET_TYPES)) return 0;
                for (k = 0; required[k]; k++) if (!jraw(v, required[k])) return 0;
            }
        }
        v = jraw(e, "current_offsets");
        if (v) {
            mask |= IX_CURRENT;
            if (!cJSON_IsArray(v)) return 0;
            cJSON_ArrayForEach(co, v) {
                size_t k, count = 0;
                const cJSON *bin = jraw(co, "bin"), *rb = jraw(co, "reference_bin");
                if (!cJSON_IsObject(co) || !whole_ok(bin) || bin->valuedouble < 1 || bin->valuedouble > 9007199254740991.0
                    || !whole_ok(rb) || rb->valuedouble < 1 || rb->valuedouble > 9007199254740991.0
                    || !cJSON_IsString(jraw(co, "reference_station_id")) || !str_or_null_ok(jraw(co, "licence_id"))) return 0;
                for (k = 0; CURRENT_ADJUST[k]; k++) {
                    const cJSON *a = jraw(co, CURRENT_ADJUST[k]);
                    if (a) { count++; if (!finite_number(a)) return 0; }
                }
                if (count && count != 6) return 0;
                if (current_mode >= 0 && current_mode != (count == 6)) return 0;
                current_mode = count == 6;
            }
        }
        cJSON_ArrayForEach(s, otc__jget(e, "sets")) {
            int presence = !!jraw(s, "source_record_id") + !!jraw(s, "source_version") + !!jraw(s, "datum");
            if (presence != 0 && presence != 3) return 0;
            if (private_mode >= 0 && private_mode != (presence == 3)) return 0;
            private_mode = presence == 3;
            if (presence == 3 && (!str_or_null_ok(jraw(s, "source_record_id")) || !str_or_null_ok(jraw(s, "source_version"))
                || (!cJSON_IsNull(jraw(s, "datum")) && !cJSON_IsObject(jraw(s, "datum")))
                || wrong_field(otc__jget(s, "datum"), DATUM_TYPES)
                || !numbers_only(otc__jget(otc__jget(s, "datum"), "named"), 0))) return 0;
            v = jraw(s, "fallback");
            if (v) {
                mask |= IX_FALLBACK;
                if (!cJSON_IsNull(v) && (!cJSON_IsObject(v) || wrong_field(v, FALLBACK_TYPES))) return 0;
            }
            v = jraw(s, "current_bins");
            if (v) {
                const cJSON *b;
                any_bins = 1;
                if (!cJSON_IsArray(v)) return 0;
                cJSON_ArrayForEach(b, v) if (!whole_ok(b) || b->valuedouble < 1 || b->valuedouble > 9007199254740991.0) return 0;
            } else missing_bins = 1;
        }
    }
    if (any_bins && missing_bins) return 0;
    if (any_bins) mask |= IX_BINS;
    if (private_mode == 1) mask |= IX_PRIVATE;
    if (current_mode == 1) mask |= IX_CURRENT_FULL;
    if (mask & IX_OWN) cJSON_ArrayForEach(e, otc__jget(doc, "stations")) {
        if (!jraw(e, "subordinate_offsets") && (otc__jstr(e, "reference_station_id") || otc__jstr(e, "offsets_licence_id"))) return 0;
    }
    *fields = mask;
    return 1;
}

/* Every key of an index entry, with its type (spec 6.2). */
static int entry_ok(const cJSON *e, int64_t size)
{
    const cJSON *a, *x, *sets, *cs;
    size_t i;
    if (!cJSON_IsObject(e) || !whole_ok(otc__jget(e, "offset")) || !whole_ok(otc__jget(e, "length"))) return 0;
    /* the bounds check of spec 6.2 (CR D4): length > 0 and offset + length <= jsonl_size (the
     * caller checks that no two entries overlap) */
    if (otc__jget(e, "length")->valuedouble <= 0) return 0;
    if (otc__jget(e, "offset")->valuedouble + otc__jget(e, "length")->valuedouble > (double)size) return 0;
    if (!otc__jstr(e, "station_id") || !otc__jstr(e, "status")) return 0;
    for (i = 0; ENTRY_STR[i]; i++)
        if (!str_or_null_ok(jraw(e, ENTRY_STR[i]))) return 0;
    if (!num_or_null_ok(jraw(e, "lat")) || !num_or_null_ok(jraw(e, "lon"))) return 0;
    a = otc__jget(e, "aliases");
    if (!cJSON_IsObject(a)) return 0;
    cJSON_ArrayForEach(x, a) {
        const cJSON *id;
        if (!cJSON_IsArray(x)) return 0;
        cJSON_ArrayForEach(id, x) if (!cJSON_IsString(id)) return 0;
    }
    sets = otc__jget(e, "sets");
    if (!cJSON_IsArray(sets)) return 0;
    cJSON_ArrayForEach(cs, sets) {
        const cJSON *cons = otc__jget(cs, "constituents"), *n;
        if (!cJSON_IsObject(cs) || !cJSON_IsArray(cons)) return 0;
        for (i = 0; SET_KEYS[i]; i++)
            if (!str_or_null_ok(jraw(cs, SET_KEYS[i]))) return 0;
        cJSON_ArrayForEach(n, cons) if (!cJSON_IsString(n)) return 0;
    }
    return 1;
}

static void put(cJSON *o, const char *key, cJSON *item, int *ok);

static void dup_if_set(cJSON *to, const cJSON *from, const char *key, const char *as, int *ok)
{
    const cJSON *v = otc__jget(from, key);
    if (v && !cJSON_IsNull(v)) put(to, as, otc__json_dup(v), ok);
}

/* The station document the index pass needs, from an index entry; NULL when
 * memory runs out (a partial document, with a field left out, is never given). */
static cJSON *line_from_entry(const cJSON *e)
{
    static const char *const keys[] = {"station_id", "status", "name", "country", "type", "lat", "lon",
                                       "recommended_set_id", "aliases", NULL};
    cJSON *o = cJSON_CreateObject(), *sets = cJSON_CreateArray();
    const cJSON *cs;
    size_t i;
    int ok = 1;
    if (!o || !sets) { cJSON_Delete(o); cJSON_Delete(sets); return NULL; }
    for (i = 0; keys[i]; i++) dup_if_set(o, e, keys[i], keys[i], &ok);
    cJSON_ArrayForEach(cs, otc__jget(e, "sets")) {
        cJSON *s = cJSON_CreateObject(), *cons = cJSON_CreateArray();
        const cJSON *n;
        size_t k;
for (k = 0; SET_KEYS[k]; k++) dup_if_set(s, cs, SET_KEYS[k], SET_KEYS[k], &ok);
{ static const char *const more[] = {"fallback", "source_record_id", "source_version", "datum", NULL};
  for (k = 0; more[k]; k++) { const cJSON *value = jraw(cs, more[k]); if (value) put(s, more[k], otc__json_dup(value), &ok); } }
        if (jraw(cs, "current_bins")) { const cJSON *b; cJSON *bins = cJSON_CreateArray();
          cJSON_ArrayForEach(b, otc__jget(cs, "current_bins")) { cJSON *bin = cJSON_CreateObject(); put(bin, "bin", otc__json_dup(b), &ok); put(bins, NULL, bin, &ok); }
          put(s, "current_bins", bins, &ok); }

        cJSON_ArrayForEach(n, otc__jget(cs, "constituents")) {
            cJSON *c = cJSON_CreateObject();
            if (cJSON_IsString(n)) put(c, "name", otc__json_dup(n), &ok);   /* the copy keeps a NUL's full length */
            put(cons, NULL, c, &ok);
        }
        put(s, "constituents", cons, &ok);
        put(sets, NULL, s, &ok);
    }
    dup_if_set(o, e, "current_offsets", "current_offsets", &ok);
    dup_if_set(o, e, "subordinate_offsets", "subordinate_offsets", &ok);
    put(o, "constant_sets", sets, &ok);
    if (!jraw(e, "subordinate_offsets") && (otc__jstr(e, "reference_station_id") || otc__jstr(e, "offsets_licence_id"))) {
        cJSON *off = cJSON_CreateObject();
        dup_if_set(off, e, "reference_station_id", "reference_station_id", &ok);
        dup_if_set(off, e, "offsets_licence_id", "licence_id", &ok);
        put(o, "subordinate_offsets", off, &ok);
    }
    if (!ok) {
        cJSON_Delete(o);
        return NULL;
    }
    return o;
}

/* FNV-1a over a string or null, with a marker so that null, "" and the
 * boundary between two strings all hash apart. */
static uint64_t view_str(uint64_t h, const char *v)
{
    h = (h ^ (v ? 1u : 0u)) * 1099511628211ull;
    if (v) {
        for (; *v; v++) h = (h ^ (unsigned char)*v) * 1099511628211ull;
        h = (h ^ 0xffu) * 1099511628211ull;
    }
    return h;
}

static uint64_t json_view(const cJSON *value)
{
    const cJSON *child;
    uint64_t h = 1469598103934665603ull;
    char number[32];
    if (!value || cJSON_IsNull(value)) return h;
    if (cJSON_IsString(value)) {
        size_t i, n = otc__jstr_len(value);
        h ^= 1u;
        for (i = 0; i < n; i++) h = (h ^ (unsigned char)value->valuestring[i]) * 1099511628211ull;
        return (h ^ 0xffu) * 1099511628211ull;
    }
    if (cJSON_IsNumber(value)) { snprintf(number, sizeof number, "%.17g", value->valuedouble); return view_str(h ^ 2u, number); }
    if (cJSON_IsBool(value)) return h ^ (cJSON_IsTrue(value) ? 3u : 4u);
    if (cJSON_IsObject(value)) {
        h ^= 5u;
        cJSON_ArrayForEach(child, value) h ^= view_str(json_view(child), child->string);
    } else {
        h ^= 6u;
        cJSON_ArrayForEach(child, value) h = (h ^ json_view(child)) * 1099511628211ull;
    }
    return h;
}

/* The hash of what a line read through the index must give as its entry does
 * (PK-R2-07): station_id, status, recommended_set_id, the two references and
 * every set's keys and constituent names. from_line: root is a .jsonl line;
 * else an index-v1.json entry. */
static uint64_t view_of(const cJSON *root, int from_line, unsigned fields)
{
    uint64_t h = 1469598103934665603ull;
    const cJSON *off = from_line ? otc__jget(root, "subordinate_offsets") : root, *cs, *c;
    size_t k;
    if (from_line && !cJSON_IsObject(off)) off = NULL;
    h = view_str(h, otc__jstr(root, "station_id"));
    h = view_str(h, otc__jstr(root, "status"));
    h = view_str(h, otc__jstr(root, "recommended_set_id"));
    h = view_str(h, otc__jstr(off, "reference_station_id"));
    h = view_str(h, otc__jstr(off, from_line ? "licence_id" : "offsets_licence_id"));
    {
        static const char *const keys[] = {"name", "country", "type", "lat", "lon", NULL};
        const cJSON *alias, *id;
        uint64_t aliases = 0;
        for (k = 0; keys[k]; k++) h = (h ^ json_view(otc__jget(root, keys[k]))) * 1099511628211ull;
        cJSON_ArrayForEach(alias, otc__jget(root, "aliases")) {
            uint64_t row = 1469598103934665603ull;
            /* The writer normalizes a single alias into a one-element array. */
            if (cJSON_IsString(alias)) row = (row ^ json_view(alias)) * 1099511628211ull;
            else cJSON_ArrayForEach(id, alias) row = (row ^ json_view(id)) * 1099511628211ull;
            aliases ^= view_str(row, alias->string);
        }
        h = (h ^ aliases) * 1099511628211ull;
    }
    cJSON_ArrayForEach(cs, otc__jget(root, from_line ? "constant_sets" : "sets")) {
        h = (h ^ 0x5eu) * 1099511628211ull;   /* one set */
        for (k = 0; SET_KEYS[k]; k++) h = view_str(h, otc__jstr(cs, SET_KEYS[k]));
        cJSON_ArrayForEach(c, otc__jget(cs, "constituents")) {
            const char *n = from_line ? otc__jstr(c, "name") : (cJSON_IsString(c) ? c->valuestring : NULL);
            if (n) h = view_str(h, n);
        }
    }
    {
    const cJSON *curr = otc__jget(root, "current_offsets");
    if (fields & IX_OWN) h ^= json_view(otc__jget(root, "subordinate_offsets"));
    if (fields & (IX_OWN | IX_CURRENT | IX_FALLBACK | IX_BINS)) {
        cJSON *summary = current_summaries(curr);
        const cJSON *row;
        h ^= json_view(summary);
        cJSON_Delete(summary);
        if (fields & IX_CURRENT_FULL) cJSON_ArrayForEach(row, curr) {
            for (k = 0; CURRENT_ADJUST[k]; k++) h = (h ^ json_view(jraw(row, CURRENT_ADJUST[k]))) * 1099511628211ull;
        }
    }
    cJSON_ArrayForEach(cs, otc__jget(root, from_line ? "constant_sets" : "sets")) {
        if (fields & IX_FALLBACK) h = (h ^ json_view(otc__jget(cs, "fallback"))) * 1099511628211ull;
        if (fields & IX_BINS) {
            cJSON *bins = bin_numbers(otc__jget(cs, "current_bins"));
            h = (h ^ json_view(bins)) * 1099511628211ull;
            cJSON_Delete(bins);
        }
        if (fields & IX_PRIVATE) {
            static const char *const keys[] = {"source_record_id", "source_version", "datum", NULL};
            for (k = 0; keys[k]; k++) h = (h ^ json_view(jraw(cs, keys[k]))) * 1099511628211ull;
        }
    }
}
    return h;
}

static uint64_t line_view
(const cJSON *root, unsigned fields) { return view_of(root, 1, fields); }

/* Indexes the release from index-v1.json in dir when it is fresh (spec 6.2).
 * OTC_E_NOT_FOUND: no fresh index (nothing was added). Another status: the
 * index looked fresh but an entry could not be used (the caller opens again
 * without it). */
static otc_status index_from_file(builder *b, const char *dir, const char *jsonl_name, const char *sha, int64_t size)
{
    char *path = otc__join(dir, "index-v1.json"), *text = NULL, ds[64];
    size_t len = 0, nl = strlen(jsonl_name);
    cJSON *doc = NULL;
    const cJSON *v, *e;
    otc_status st = OTC_E_NOT_FOUND;
    if (!path) return OTC_E_NOMEM;
    if (!sha || nl < 11 || nl - 10 >= sizeof ds || strncmp(jsonl_name, "OTC_", 4) != 0) goto done;
    memcpy(ds, jsonl_name + 4, nl - 10);
    ds[nl - 10] = '\0';
    if (otc__path_size(path) < 0 || otc__read_all(path, &text, &len) != OTC_OK) goto done;
    /* strings with a NUL keep their full length (CR2 DR33) */
    if (otc__json_parse_st(text, len, &doc) == OTC_E_NOMEM) { st = OTC_E_NOMEM; goto done; }
    v = jraw(doc, "discovery_index_version");
    if (v && (!cJSON_IsNumber(v) || v->valuedouble != 1.0)) goto done;
    v = otc__jget(doc, "index_version");
    if (!cJSON_IsObject(doc) || !cJSON_IsNumber(v) || v->valuedouble != 1.0) goto done;
    if (otc__strcmp_null(otc__jstr(doc, "datestamp"), ds) || otc__strcmp_null(otc__jstr(doc, "jsonl"), jsonl_name)
        || otc__strcmp_null(otc__jstr(doc, "jsonl_sha256"), sha))
        goto done;
    v = otc__jget(doc, "jsonl_size");
    if (!cJSON_IsNumber(v) || v->valuedouble != (double)size || !cJSON_IsArray(otc__jget(doc, "stations"))) goto done;
    if (!index_profile(doc, &b->rel->index_fields)) goto done;
    {
        /* each offset is at least the previous offset + the previous length + 1 (the
         * line end), so that no two entries overlap (spec 6.2, CR2 DR9) */
        double start = 0;
        cJSON_ArrayForEach(e, otc__jget(doc, "stations")) {
            if (!entry_ok(e, size) || otc__jget(e, "offset")->valuedouble < start) goto done;
            start = otc__jget(e, "offset")->valuedouble + otc__jget(e, "length")->valuedouble + 1;
        }
    }
    st = OTC_OK;
    cJSON_ArrayForEach(e, otc__jget(doc, "stations")) {
        cJSON *line = line_from_entry(e);
        size_t n_st = b->rel->n_st, n_tomb = b->rel->n_tomb;
        if (!line) { st = OTC_E_NOMEM; break; }
        b->line_no++;
        st = index_parsed(b, line, (size_t)otc__jget(e, "length")->valuedouble,
                          (uint64_t)otc__jget(e, "offset")->valuedouble);
        cJSON_Delete(line);
        if (st != OTC_OK) break;
        if (b->rel->n_st > n_st) {
            otc__entry *added = &b->rel->st[n_st];
            const cJSON *s;
            added->index_view_fields = b->rel->index_fields | (jraw(e, "subordinate_offsets") ? IX_OWN : 0u);
            added->view = view_of(e, 0, added->index_view_fields);
            added->index_policy_missing = !jraw(e, "subordinate_offsets") || !jraw(e, "current_offsets");
            cJSON_ArrayForEach(s, otc__jget(e, "sets")) if (!jraw(s, "fallback") || !jraw(s, "current_bins")) added->index_policy_missing = true;
        }
        if (b->rel->n_tomb > n_tomb) b->rel->tomb[n_tomb].view = view_of(e, 0, b->rel->index_fields);
    }
done:
    if (st == OTC_E_NOT_FOUND) b->rel->index_fields = 0;
    cJSON_Delete(doc);
    free(text);
    free(path);
    return st;
}

/* The string member k in full (a raw literal when it holds a NUL, CR2 DR33), or null. */
static cJSON *jstr_or_null(const cJSON *o, const char *k)
{
    const cJSON *s = otc__jstr_item(o, k);
    return s ? otc__json_str_out(s) : cJSON_CreateNull();
}

typedef struct ix_ctx {
    const otc_release *rel;
    cJSON             *arr;
    otc_status         st;
} ix_ctx;

/* Adds item to o under key (to the array o when key is NULL). On any failure
 * (item NULL, no memory for the key) the item is deleted and *ok cleared. */
static void put(cJSON *o, const char *key, cJSON *item, int *ok)
{
    if (!item || !o || !(key ? cJSON_AddItemToObject(o, key, item) : cJSON_AddItemToArray(o, item))) {
        cJSON_Delete(item);
        *ok = 0;
    }
}

/* One entry of index-v1.json, from its line (spec 6.2). Any allocation that
 * fails makes the whole index fail (OTC_E_NOMEM): a partial entry is never
 * written. */
otc_status otc__project_station_entry(const otc_release *rel, const cJSON *d, uint64_t offset, size_t len, cJSON **out)
{
    cJSON *o, *sets, *al;
    const cJSON *offs, *cs, *a, *v;
    const cJSON *rec, *name;
    const char *kind = NULL, *status;
    int ok = 1;
    o = cJSON_CreateObject();
    sets = cJSON_CreateArray();
    al = cJSON_CreateObject();
    if (!o || !sets || !al) ok = 0;
    offs = otc__jget(d, "subordinate_offsets");
    if (!cJSON_IsObject(offs)) offs = NULL;
    rec = otc__jstr_item(d, "recommended_set_id");
    name = otc__jstr_item(d, "name");
    put(o, "offset", cJSON_CreateNumber((double)offset), &ok);
    put(o, "length", cJSON_CreateNumber((double)len), &ok);
    put(o, "station_id", jstr_or_null(d, "station_id"), &ok);
    status = otc__jget(d, "status") ? otc__jstr(d, "status") : "active";   /* no status: active (CR2 DR28) */
    put(o, "status", status ? cJSON_CreateString(status) : cJSON_CreateNull(), &ok);
    put(o, "name", name ? otc__json_str_out(name) : cJSON_CreateNull(), &ok);   /* in full: it may hold a NUL */
    {   /* folded in full: a name may hold a NUL (spec 4.4.1); a raw literal then, as for the name */
        size_t fl = 0;
        char *folded = name ? otc__fold_n(name->valuestring, otc__jstr_len(name), &fl) : NULL, *jf = NULL;
        if (name && !folded) ok = 0;
        if (folded && fl != strlen(folded) && !(jf = otc__json_escape_n(folded, fl))) ok = 0;
        put(o, "name_folded", jf ? cJSON_CreateRaw(jf) : folded ? cJSON_CreateString(folded) : cJSON_CreateNull(), &ok);
        free(folded);
        free(jf);
    }
    put(o, "country", jstr_or_null(d, "country"), &ok);
    put(o, "type", jstr_or_null(d, "type"), &ok);
    v = otc__jget(d, "lat");
    put(o, "lat", cJSON_IsNumber(v) ? cJSON_CreateNumber(v->valuedouble) : cJSON_CreateNull(), &ok);
    v = otc__jget(d, "lon");
    put(o, "lon", cJSON_IsNumber(v) ? cJSON_CreateNumber(v->valuedouble) : cJSON_CreateNull(), &ok);
    cJSON_ArrayForEach(cs, otc__jget(d, "constant_sets")) {
        cJSON *s = cJSON_CreateObject(), *cons = cJSON_CreateArray();
        const cJSON *c;
        size_t k;
        for (k = 0; SET_KEYS[k]; k++) put(s, SET_KEYS[k], jstr_or_null(cs, SET_KEYS[k]), &ok);
        v = otc__jget(cs, "fallback");
        put(s, "fallback", v ? otc__json_dup(v) : cJSON_CreateNull(), &ok);
        put(s, "current_bins", bin_numbers(otc__jget(cs, "current_bins")), &ok);

        cJSON_ArrayForEach(c, otc__jget(cs, "constituents"))
            if (otc__jstr_item(c, "name")) put(cons, NULL, otc__json_str_out(otc__jstr_item(c, "name")), &ok);
        put(s, "constituents", cons, &ok);
        put(sets, NULL, s, &ok);
        if (otc__jstr_same(otc__jstr_item(cs, "set_id"), rec)) {
            const char *q = otc__jstr(cs, "quantity");
            kind = !q ? "other" : !strcmp(q, "water_level") ? "tide" : !strcmp(q, "current") ? "current" : "other";
        }
    }
    if (status && !strcmp(status, "active") && otc__jstr(d, "station_id")) {
        const otc__entry *e = otc__find_entry(rel, otc__jstr(d, "station_id"));
        if (e) kind = e->kind == OTC_KIND_UNSET ? NULL : otc_kind_name(e->kind);
    }
    put(o, "kind", kind ? cJSON_CreateString(kind) : cJSON_CreateNull(), &ok);
    cJSON_ArrayForEach(a, otc__jget(d, "aliases")) {
        cJSON *list = cJSON_CreateArray();
        const cJSON *id;
        if (cJSON_IsString(a)) put(list, NULL, otc__json_str_out(a), &ok);
        else cJSON_ArrayForEach(id, a) if (cJSON_IsString(id)) put(list, NULL, otc__json_str_out(id), &ok);
        put(al, a->string, list, &ok);
    }
    put(o, "aliases", al, &ok);
    put(o, "reference_station_id", jstr_or_null(offs, "reference_station_id"), &ok);
    put(o, "offsets_licence_id", jstr_or_null(offs, "licence_id"), &ok);
    put(o, "recommended_set_id", jstr_or_null(d, "recommended_set_id"), &ok);
    put(o, "subordinate_offsets", offs ? otc__json_dup(offs) : cJSON_CreateNull(), &ok);
    put(o, "current_offsets", current_summaries(otc__jget(d, "current_offsets")), &ok);
    put(o, "sets", sets, &ok);
    if (!ok) {
        cJSON_Delete(o);
        return OTC_E_NOMEM;
    }
    *out = o;
    return OTC_OK;
}

static otc_status stored_entry_cb(void *ctx, const char *text, size_t len, uint64_t offset)
{
    ix_ctx *x = (ix_ctx *)ctx;
    cJSON *d, *o = NULL;
    int ok = 1;
    otc_status pst = otc__json_parse_st(text, len, &d);
    if (pst != OTC_OK) return pst;
    pst = otc__project_station_entry(x->rel, d, offset, len, &o);
    cJSON_Delete(d);
    if (pst != OTC_OK) return x->st = pst;
    put(x->arr, NULL, o, &ok);
    return ok ? OTC_OK : (x->st = OTC_E_NOMEM);
}

/* The index-v1.json document; NULL when memory runs out or the file cannot be read. */
cJSON *otc__index_doc(const otc_release *rel, const char *jsonl_sha256, const char *by)
{
    cJSON *doc, *arr;
    const char *jsonl;
    char *ds;
    size_t line_no = 0, n;
    int ok = 1;
    ix_ctx x;
    if (!rel || !rel->file || !rel->path || !jsonl_sha256) return NULL;
    /* the index names the release of the file, OTC_{D}.jsonl, not release.datestamp
     * (spec 6.2, CR2 DR23): that is what index_from_file compares it with */
    jsonl = path_base(rel->path);
    n = strlen(jsonl);
    if (n < 11 || strncmp(jsonl, "OTC_", 4) != 0 || strcmp(jsonl + n - 6, ".jsonl") != 0) return NULL;
    ds = otc__strndup(jsonl + 4, n - 10);
    doc = cJSON_CreateObject();
    arr = cJSON_CreateArray();
    if (!doc || !arr || !ds) { cJSON_Delete(doc); cJSON_Delete(arr); free(ds); return NULL; }
    x.rel = rel;
    x.arr = arr;
    x.st = OTC_OK;
    if (scan_lines(rel->file, &line_no, stored_entry_cb, &x) != OTC_OK || x.st != OTC_OK) {
        cJSON_Delete(doc);
        cJSON_Delete(arr);
        free(ds);
        return NULL;
    }
    put(doc, "discovery_index_version", cJSON_CreateNumber(1), &ok);
    put(doc, "index_version", cJSON_CreateNumber(1), &ok);
    put(doc, "datestamp", cJSON_CreateString(ds), &ok);
    put(doc, "jsonl", cJSON_CreateString(jsonl), &ok);
    put(doc, "jsonl_sha256", cJSON_CreateString(jsonl_sha256), &ok);
    put(doc, "jsonl_size", cJSON_CreateNumber((double)otc__file_size(rel->file)), &ok);
    put(doc, "by", cJSON_CreateString(by), &ok);
    put(doc, "stations", arr, &ok);
    free(ds);
    if (!ok) {
        cJSON_Delete(doc);
        return NULL;
    }
    return doc;
}

static otc_kind resolve_kind(const otc_release *r, const otc__entry *e, size_t depth)
{
    if (e->has_rec) {
        /* any other quantity, also none (null or no key), is OTHER (spec 6.2; orchestrator S3) */
        if (e->rec_quantity == OTC_QUANTITY_WATER_LEVEL) return OTC_KIND_TIDE;
        if (e->rec_quantity == OTC_QUANTITY_CURRENT) return OTC_KIND_CURRENT;
        return OTC_KIND_OTHER;
    }
    if (e->type == OTC_STATION_TYPE_SUBORDINATE && e->has_offsets && depth < OTC__MAX_LINKS) {
        const otc__entry *ref = otc__find_entry(r, e->ref_id);
        if (ref && ref != e) return resolve_kind(r, ref, depth + 1);
    }
    return OTC_KIND_UNSET;
}

static int cname_cmp(const void *a, const void *b)
{
    return strcmp(*(char *const *)a, *(char *const *)b);
}

static int file_cmp(const void *a, const void *b)
{
    return strcmp(((const otc_file_info *)a)->name, ((const otc_file_info *)b)->name);
}

static const char *path_base(const char *path)
{
    const char *a = strrchr(path, '/'), *b = strrchr(path, '\\');
    const char *s = a > b ? a : b;
    return s ? s + 1 : path;
}

/* Checks the meta document: format major, release object, conventions, licences. */
/* text: the bytes of the meta file, read once (and hashed from the same bytes). */
static otc_status load_meta(otc_release *r, const char *meta_path, const char *text, size_t len, otc_error *err)
{
    const char *fv;
    const cJSON *convs, *lics, *c;
    long major;
    size_t i;
    if (otc__json_parse_st(text, len, &r->meta) == OTC_E_NOMEM) {
        otc__err_set(err, OTC_E_NOMEM, meta_path, "out of memory");
        return OTC_E_NOMEM;
    }
    if (!r->meta || !cJSON_IsObject(r->meta)) {
        otc__err_set(err, OTC_E_INVALID_RELEASE, meta_path, "%s is not a JSON object", meta_path);
        return OTC_E_INVALID_RELEASE;
    }
    fv = otc__jstr(r->meta, "format_version");
    if (!fv) {
        otc__err_set(err, OTC_E_INVALID_RELEASE, meta_path, "%s has no format_version", meta_path);
        return OTC_E_INVALID_RELEASE;
    }
    if (!otc__version_valid(fv)) {   /* spec 7.4 (CR D9): fail closed, never guess a version */
        otc__err_set(err, OTC_E_INVALID_RELEASE, meta_path, "format_version \"%s\" is not MAJOR.MINOR", fv);
        return OTC_E_INVALID_RELEASE;
    }
    major = strtol(fv, NULL, 10);
    if (major != OTC_FORMAT_MAJOR) {
        otc__err_set(err, OTC_E_UNSUPPORTED_FORMAT, meta_path, "format %s: this library reads format major %d", fv,
                     OTC_FORMAT_MAJOR);
        return OTC_E_UNSUPPORTED_FORMAT;
    }
    r->release_obj = otc__jget(r->meta, "release");
    if (!cJSON_IsObject(r->release_obj) || !otc__jstr(r->release_obj, "datestamp")) {
        otc__err_set(err, OTC_E_INVALID_RELEASE, meta_path, "%s has no release.datestamp", meta_path);
        return OTC_E_INVALID_RELEASE;
    }
    if (!otc__utc_time(otc__jstr(r->release_obj, "created"), r->created)) r->created[0] = '\0';
    {   /* spec 4.8, 7.3: a field of the wrong type is invalid_release at open, in every SDK */
        const cJSON *created = otc__jget(r->release_obj, "created"), *sv = otc__jget(r->release_obj, "source_versions");
        const cJSON *v;
        int sv_ok = !sv || cJSON_IsObject(sv);
        if (sv && sv_ok) {
            cJSON_ArrayForEach(v, sv) {   /* each value is a string (CR2 PK-R2-05) */
                if (!cJSON_IsString(v)) sv_ok = 0;
            }
        }
        if ((created && !cJSON_IsString(created)) || !sv_ok) {
            otc__err_set(err, OTC_E_INVALID_RELEASE, meta_path, "%s: release.%s has the wrong type", meta_path,
                         created && !cJSON_IsString(created) ? "created" : "source_versions");
            return OTC_E_INVALID_RELEASE;
        }
        /* spec 7.3 (CR2 DR6): a created that is not an RFC 3339 time with real calendar fields */
        if (created && !r->created[0]) {
            otc__err_set(err, OTC_E_INVALID_RELEASE, meta_path, "%s: release.created \"%s\" is not an RFC 3339 time",
                         meta_path, created->valuestring);
            return OTC_E_INVALID_RELEASE;
        }
    }
    {   /* spec 7.4: a release that needs a newer reader is refused, naming both versions; a
         * the required min_reader_version must be MAJOR.MINOR (CR D9) */
        const char *mrv = otc__jstr(r->release_obj, "min_reader_version");
        if (!otc__version_valid(mrv)) {
            otc__err_set(err, OTC_E_INVALID_RELEASE, meta_path, "release.min_reader_version is not MAJOR.MINOR");
            return OTC_E_INVALID_RELEASE;
        }
        if (mrv && !otc__readable(NULL, mrv)) {
            otc__err_set(err, OTC_E_READER_TOO_OLD, meta_path,
                         "release %s needs a reader for format %s; this SDK reads format %s",
                         otc__jstr(r->release_obj, "datestamp"), mrv, OTC_FORMAT_VERSION);
            return OTC_E_READER_TOO_OLD;
        }
    }
    convs = otc__jget(r->meta, "conventions");
    lics = otc__jget(r->meta, "licences");
    if ((convs && !cJSON_IsArray(convs)) || (lics && !cJSON_IsArray(lics))) {
        otc__err_set(err, OTC_E_INVALID_RELEASE, meta_path, "conventions or licences is not an array");
        return OTC_E_INVALID_RELEASE;
    }
    r->n_conv = (size_t)cJSON_GetArraySize(convs);
    r->n_lic = (size_t)cJSON_GetArraySize(lics);
    r->conv = (otc_convention *)calloc(r->n_conv ? r->n_conv : 1, sizeof *r->conv);
    r->lic = (otc_licence *)calloc(r->n_lic ? r->n_lic : 1, sizeof *r->lic);
    if (!r->conv || !r->lic) return OTC_E_NOMEM;
    i = 0;
    cJSON_ArrayForEach(c, convs) {
        r->conv[i].json = (cJSON *)c;
        r->conv[i].id = otc__jstr(c, "convention_id");
        if (!r->conv[i].id) {
            otc__err_set(err, OTC_E_INVALID_RELEASE, meta_path, "a convention has no convention_id");
            return OTC_E_INVALID_RELEASE;
        }
        if (otc__find_convention(r, r->conv[i].id) != &r->conv[i]) {   /* spec 6.1 (CR D5) */
            otc__err_set(err, OTC_E_INVALID_RELEASE, meta_path, "convention_id %s appears twice", r->conv[i].id);
            return OTC_E_INVALID_RELEASE;
        }
        i++;
    }
    i = 0;
    cJSON_ArrayForEach(c, lics) {
        r->lic[i].json = (cJSON *)c;
        r->lic[i].id = otc__jstr(c, "licence_id");
        if (!r->lic[i].id) {
            otc__err_set(err, OTC_E_INVALID_RELEASE, meta_path, "a licence has no licence_id");
            return OTC_E_INVALID_RELEASE;
        }
        if (otc__find_licence(r, r->lic[i].id) != &r->lic[i]) {
            otc__err_set(err, OTC_E_INVALID_RELEASE, meta_path, "licence_id %s appears twice", r->lic[i].id);
            return OTC_E_INVALID_RELEASE;
        }
        {   /* the attribution text prints both (spec 4.6, CR2 DR2); a null provider is allowed (CR D2 b) */
            const cJSON *att = otc__jget(c, "attribution");
            const cJSON *prov = otc__jget(c, "provider");
            if (!cJSON_IsString(att) || (prov && !cJSON_IsNull(prov) && !cJSON_IsString(prov))) {
                otc__err_set(err, OTC_E_INVALID_RELEASE, meta_path,
                             "licence %s: attribution must be a string and provider a string or null", r->lic[i].id);
                return OTC_E_INVALID_RELEASE;
            }
        }
        {   /* the licence fields (spec 4.6, K-NC DR104): commercial_use a JSON boolean; restriction and terms_url,
             * when present, strings (a JSON null is not one, CR3 DR71); a non-commercial licence has both, and an
             * spdx, which the non-commercial notice prints */
            const cJSON *cu = otc__jget(c, "commercial_use");
            static const char *const str_keys[] = {"restriction", "terms_url"};
            static const char *const nc_keys[] = {"restriction", "terms_url", "spdx"};
            size_t k;
            if (!cJSON_IsBool(cu)) {
                otc__err_set(err, OTC_E_INVALID_RELEASE, meta_path, "licence %s: commercial_use must be true or false",
                             r->lic[i].id);
                return OTC_E_INVALID_RELEASE;
            }
            for (k = 0; k < 2; k++) {
                /* not otc__jget, which reads a null as absent: a present null is not a string (CR3 DR71) */
                const cJSON *v = cJSON_GetObjectItemCaseSensitive(c, str_keys[k]);
                if (v && !cJSON_IsString(v)) {
                    otc__err_set(err, OTC_E_INVALID_RELEASE, meta_path, "licence %s: %s must be a string", r->lic[i].id,
                                 str_keys[k]);
                    return OTC_E_INVALID_RELEASE;
                }
            }
            r->lic[i].commercial_use = cJSON_IsTrue(cu);
            for (k = 0; !r->lic[i].commercial_use && k < 3; k++) {
                if (!cJSON_IsString(otc__jget(c, nc_keys[k]))) {
                    otc__err_set(err, OTC_E_INVALID_RELEASE, meta_path,
                                 "licence %s: a licence with commercial_use false needs %s", r->lic[i].id, nc_keys[k]);
                    return OTC_E_INVALID_RELEASE;
                }
            }
        }
        i++;
    }
    return OTC_OK;
}

/* release.files (spec 4.3.1) for a file open. */
static otc_status build_files(otc_release *r, const char *dir, char **names, char **digests, size_t n_rows,
                              const char *jsonl_name, const char *meta_name)
{
    size_t i, n = n_rows ? n_rows : 2;
    r->files = (otc_file_info *)calloc(n, sizeof *r->files);
    if (!r->files) return OTC_E_NOMEM;
    r->n_files = n;
    for (i = 0; i < n; i++) {
        const char *name = n_rows ? names[i] : (i == 0 ? jsonl_name : meta_name);
        char *full = otc__join(dir, name);
        if (!full) return OTC_E_NOMEM;   /* never "size unknown": the size is there, the path is not */
        r->files[i].name = otc__strdup(name);
        r->files[i].sha256 = n_rows ? otc__strdup(digests[i]) : NULL;
        r->files[i].size = otc__path_size(full);
        free(full);
        if (!r->files[i].name || (n_rows && !r->files[i].sha256)) return OTC_E_NOMEM;
    }
    qsort(r->files, n, sizeof *r->files, file_cmp);
    return OTC_OK;
}

/* spec 5.3, CR3 DR73: a .sha256 next to the file must have a row for every release file the open reads, checked
 * before any file is hashed; a missing row is OTC_E_CHECKSUM "not listed", with path the missing file */
static otc_status need_row(const char *path, const char *name, const char *sha_path, char **names, size_t n,
                           otc_error *err)
{
    size_t i;
    for (i = 0; i < n; i++)
        if (!strcmp(names[i], name)) return OTC_OK;
    otc__err_set(err, OTC_E_CHECKSUM, path, "%s is not listed in %s", name, path_base(sha_path));
    return OTC_E_CHECKSUM;
}

/* hex: the SHA-256 of the bytes the library uses (the open handle, or the bytes read). */
static otc_status check_digest(const char *path, const char *name, const char *hex, char **names, char **digests,
                               size_t n, otc_error *err)
{
    const char *expected = NULL;
    size_t i;
    for (i = 0; i < n; i++)
        if (!strcmp(names[i], name)) expected = digests[i];
    if (!expected || strcmp(expected, hex) != 0) {
        otc__err_set(err, OTC_E_CHECKSUM, path, "SHA-256 of %s does not match its .sha256 row", name);
        if (err) {
            size_t el = expected ? strlen(expected) : 0;
            memcpy(err->expected_sha256, expected ? expected : "", el < 64 ? el + 1 : 65);
            err->expected_sha256[64] = '\0';
            memcpy(err->actual_sha256, hex, 65);
        }
        return OTC_E_CHECKSUM;
    }
    return OTC_OK;
}

static otc_status open_impl(const char *path, const otc_open_options *opts, otc_error *err, otc_release *r,
                            int use_index)
{
    char *base = NULL, *meta_path = NULL, *sha_path = NULL, *dir = NULL, *meta_text = NULL;
    char **names = NULL, **digests = NULL;
    size_t n_rows = 0, i, meta_len = 0;
    const char *jsonl_name = path_base(path);
    otc_status st;
    builder b;

    memset(&b, 0, sizeof b);
    if (otc__path_size(path) < 0) {
        otc__err_set(err, OTC_E_IO, path, "cannot open %s", path);
        return OTC_E_IO;
    }
    {   /* the name is OTC_<D>.jsonl (spec 4.2, CR D18) */
        size_t nl = strlen(jsonl_name);
        if (!otc__ends_with(path, ".jsonl") || nl < 4 + 8 + 6 || strncmp(jsonl_name, "OTC_", 4) != 0
            || !otc__valid_datestamp(jsonl_name + 4, nl - 10)) {
            otc__err_set(err, OTC_E_INVALID_ARGUMENT, path, "the C library opens OTC_{D}.jsonl files: %s", path);
            return OTC_E_INVALID_ARGUMENT;
        }
    }
    base = otc__strndup(path, strlen(path) - 6);
    dir = otc__strndup(path, (size_t)(jsonl_name - path));
    meta_path = base ? otc__join(base, ".meta.json") : NULL;
    sha_path = base ? otc__join(base, ".sha256") : NULL;
    r->path = otc__strdup(path);
    if (!base || !dir || !meta_path || !sha_path || !r->path) { st = OTC_E_NOMEM; goto done; }

    if (otc__path_size(path) < 0) {
        otc__err_set(err, OTC_E_IO, path, "cannot open %s", path);
        st = OTC_E_IO;
        goto done;
    }
    if (otc__path_size(meta_path) < 0) {
        otc__err_set(err, OTC_E_IO, meta_path, "cannot open %s", meta_path);
        st = OTC_E_IO;
        goto done;
    }
    /* the .jsonl is opened once and the meta file read once: the bytes that are hashed are
     * the bytes that are used, so a file swapped after the check is never read (C3) */
    st = otc__file_open(path, &r->file);
    if (st != OTC_OK) { otc__err_set(err, st, path, "cannot open %s", path); goto done; }
    st = otc__read_all(meta_path, &meta_text, &meta_len);
    if (st != OTC_OK) { otc__err_set(err, st, meta_path, "cannot read %s", meta_path); goto done; }
    /* checksums first (spec 5.3): a corrupt or truncated file is checksum_mismatch */
    if (otc__path_size(sha_path) >= 0) {
        char hex[65];
        st = otc__sha256_rows(sha_path, &names, &digests, &n_rows);
        if (st != OTC_OK) { otc__err_set(err, st, sha_path, "%s %s", otc__sha256_rows_what(st), sha_path); goto done; }
        if ((st = need_row(path, jsonl_name, sha_path, names, n_rows, err)) != OTC_OK) goto done;
        if ((st = need_row(meta_path, path_base(meta_path), sha_path, names, n_rows, err)) != OTC_OK) goto done;
        if ((st = otc__sha256_handle(r->file, hex)) != OTC_OK) { otc__err_set(err, st, path, "cannot read %s", path); goto done; }
        if ((st = check_digest(path, jsonl_name, hex, names, digests, n_rows, err)) != OTC_OK) goto done;
        otc__sha256_mem(meta_text, meta_len, hex);
        if ((st = check_digest(meta_path, path_base(meta_path), hex, names, digests, n_rows, err)) != OTC_OK) goto done;
        r->loaded_from = OTC_LOADED_FROM_FILE;
    } else if (opts && opts->require_checksum) {
        /* DR34: the same answer as otc_verify_file (D20): nothing to check against is a checksum failure */
        otc__err_set(err, OTC_E_CHECKSUM, path, "require_checksum: no %s next to the file %s", path_base(sha_path), path);
        st = OTC_E_CHECKSUM;
        goto done;
    } else {
        r->loaded_from = OTC_LOADED_FROM_FILE_UNVERIFIED;
    }
    if (opts && opts->struct_size >= sizeof *opts) {
        if (opts->commercial_basis && strcmp(opts->commercial_basis, "strict") && strcmp(opts->commercial_basis, "as_published_upstream")) { st = OTC_E_INVALID_ARGUMENT; goto done; }
        if (opts->historical_offsets_policy && strcmp(opts->historical_offsets_policy, "fallback") && strcmp(opts->historical_offsets_policy, "exclude")) { st = OTC_E_INVALID_ARGUMENT; goto done; }
        r->commercial_upstream = opts->commercial_basis && !strcmp(opts->commercial_basis, "as_published_upstream");
        r->historical_excluded = opts->historical_offsets_policy && !strcmp(opts->historical_offsets_policy, "exclude");
    }
    r->commercial_only = OTC__COMMERCIAL_ONLY(opts);   /* fixed on the handle (spec 4.2, K-NC DR106) */
    if ((st = load_meta(r, meta_path, meta_text, meta_len, err)) != OTC_OK) goto done;
    b.rel = r;
    b.err = err;
    st = OTC_E_NOT_FOUND;
    /* a fresh index-v1.json next to a checked .jsonl saves the pass (spec 6.2) */
    if (use_index && n_rows > 0) {
        const char *sha = NULL;
        for (i = 0; i < n_rows; i++)
            if (!strcmp(names[i], jsonl_name)) sha = digests[i];
        st = index_from_file(&b, dir, jsonl_name, sha, otc__file_size(r->file));
        if (st != OTC_E_NOT_FOUND) r->index_used = 1;
        if (st != OTC_OK && st != OTC_E_NOT_FOUND) goto done; /* the caller opens again without the index */
    }
    if (st == OTC_E_NOT_FOUND) st = index_file(&b);
    if (st != OTC_OK) {
        if (!err || err->status != st) otc__err_set(err, st, path, "cannot index %s", path);
        goto done;
    }
    if (r->n_st > 1) qsort(r->st, r->n_st, sizeof *r->st, entry_cmp);
    for (i = 1; i < r->n_st; i++) {
        if (!strcmp(r->st[i - 1].id, r->st[i].id)) {
            otc__err_set(err, OTC_E_INVALID_RELEASE, path, "station %s appears twice", r->st[i].id);
            st = OTC_E_INVALID_RELEASE;
            goto done;
        }
    }
    if (r->n_tomb > 1) qsort(r->tomb, r->n_tomb, sizeof *r->tomb, tomb_cmp);
    if (r->n_alias > 1) qsort(r->alias, r->n_alias, sizeof *r->alias, alias_cmp);
    /* spec 6.1 (CR D5): an id is used once across the active stations and the
     * tombstones, and a (system, alias id) pair once */
    for (i = 0; i < r->n_tomb; i++) {
        const char *dup = (i > 0 && !strcmp(r->tomb[i - 1].id, r->tomb[i].id)) ? "is removed twice"
                          : otc__find_entry(r, r->tomb[i].id)                    ? "is both active and removed"
                                                                                 : NULL;
        if (dup) {
            otc__err_set(err, OTC_E_INVALID_RELEASE, path, "station %s %s", r->tomb[i].id, dup);
            st = OTC_E_INVALID_RELEASE;
            goto done;
        }
    }
    for (i = 0; i < r->n_st; i++) {
        const otc__entry *e = &r->st[i];
        if (e->ref_id && !otc__find_entry(r, e->ref_id)) {
            otc__err_set(err, OTC_E_INVALID_RELEASE, path,
                         "station %s: subordinate_offsets.reference_station_id %s is not an active station", e->id, e->ref_id);
            st = OTC_E_INVALID_RELEASE;
            goto done;
        }
    }
    for (i = 1; i < r->n_alias; i++) {
        if (!alias_cmp(&r->alias[i - 1], &r->alias[i])) {
            otc__err_set(err, OTC_E_INVALID_RELEASE, path, "the %s alias %s belongs to both %s and %s",
                         r->alias[i].system, r->alias[i].alias, r->alias[i - 1].station, r->alias[i].station);
            st = OTC_E_INVALID_RELEASE;
            goto done;
        }
    }
    if (b.n_set_ids > 1) qsort(b.set_ids, b.n_set_ids, sizeof *b.set_ids, cname_cmp);
    for (i = 1; i < b.n_set_ids; i++) {
        if (!strcmp(b.set_ids[i - 1], b.set_ids[i])) {
            otc__err_set(err, OTC_E_INVALID_RELEASE, path, "the set_id %s appears twice in the release",
                        b.set_ids[i] + (b.set_ids[i][0] == (char)0xff));   /* a key with a NUL: its JSON literal */
            st = OTC_E_INVALID_RELEASE;
            goto done;
        }
    }
    if (r->n_cnames > 1) qsort(r->cnames, r->n_cnames, sizeof *r->cnames, cname_cmp);
    for (i = 0; i < r->n_st; i++) r->st[i].kind = resolve_kind(r, &r->st[i], 0);
    otc__kv_sort(&r->source_counts);
    otc__kv_sort(&r->qc_counts);
    st = build_files(r, dir, names, digests, n_rows, jsonl_name, path_base(meta_path));
    if (st == OTC_OK && opts && opts->log_fn) {
        for (i = 0; i < b.n_unknown; i++) {
            char msg[512];
            const char *sp = strchr(b.unknown[i], ' ');
            snprintf(msg, sizeof msg, "station %.*s has the status \"%s\", which this library does not know: it is left out of every query",
                     (int)(sp - b.unknown[i]), b.unknown[i], sp + 1);
            opts->log_fn(opts->log_user_data, 2, msg);
        }
    }
done:
    free(b.cn_slots);
    for (i = 0; i < b.n_unknown; i++) free(b.unknown[i]);
    free(b.unknown);
    for (i = 0; i < b.n_set_ids; i++) free(b.set_ids[i]);
    free(b.set_ids);
    otc__free_rows(names, digests, n_rows);
    free(meta_text);
    free(base);
    free(dir);
    free(meta_path);
    free(sha_path);
    if (st == OTC_E_NOMEM) otc__err_set(err, st, path, "out of memory");
    return st;
}

/* Private owning preparation view. The original producer remains one body;
 * this unpublished view never owns a mutex or becomes a public handle. */
static void release_export_fields(otc_release *view, otc__prepared_release_fields *prepared)
{
    prepared->file = view->file;
    prepared->path = view->path;
    prepared->meta = view->meta;
    prepared->release_obj = view->release_obj;
    prepared->conv = view->conv;
    prepared->n_conv = view->n_conv;
    prepared->lic = view->lic;
    prepared->n_lic = view->n_lic;
    prepared->st = view->st;
    prepared->n_st = view->n_st;
    prepared->tomb = view->tomb;
    prepared->n_tomb = view->n_tomb;
    prepared->alias = view->alias;
    prepared->n_alias = view->n_alias;
    prepared->cnames = view->cnames;
    prepared->n_cnames = view->n_cnames;
    prepared->files = view->files;
    prepared->n_files = view->n_files;
    prepared->zenodo_version_doi = view->zenodo_version_doi;
    memcpy(prepared->created, view->created, sizeof prepared->created);
    prepared->loaded_from = view->loaded_from;
    prepared->index_used = view->index_used;
    prepared->index_fields = view->index_fields;
    prepared->commercial_only = view->commercial_only;
    prepared->commercial_upstream = view->commercial_upstream;
    prepared->historical_excluded = view->historical_excluded;
    prepared->source_counts = view->source_counts;
    prepared->qc_counts = view->qc_counts;
    prepared->astro = view->astro;
    prepared->last_status = view->last_status;
    memcpy(prepared->last_message, view->last_message, sizeof prepared->last_message);
    memset(view, 0, sizeof *view);
}

otc_status otc__release_prepare_fields(const char *path, const otc_open_options *opts,
    otc_error *err, otc_release *destination, int use_index, otc__prepared_release_fields *prepared)
{
    otc_release view = {0};
    otc_status status;
    if (!path || !destination || !prepared) return OTC_E_INVALID_ARGUMENT;
    memset(prepared, 0, sizeof *prepared);
    prepared->destination = destination;
    status = open_impl(path, opts, err, &view, use_index);
    release_export_fields(&view, prepared);
    prepared->complete = status == OTC_OK;
    return status;
}

static void release_import_fields(otc_release *view, const otc__prepared_release_fields *prepared)
{
    view->file = prepared->file;
    view->path = prepared->path;
    view->meta = prepared->meta;
    view->release_obj = prepared->release_obj;
    view->conv = prepared->conv;
    view->n_conv = prepared->n_conv;
    view->lic = prepared->lic;
    view->n_lic = prepared->n_lic;
    view->st = prepared->st;
    view->n_st = prepared->n_st;
    view->tomb = prepared->tomb;
    view->n_tomb = prepared->n_tomb;
    view->alias = prepared->alias;
    view->n_alias = prepared->n_alias;
    view->cnames = prepared->cnames;
    view->n_cnames = prepared->n_cnames;
    view->files = prepared->files;
    view->n_files = prepared->n_files;
    view->zenodo_version_doi = prepared->zenodo_version_doi;
    memcpy(view->created, prepared->created, sizeof view->created);
    view->loaded_from = prepared->loaded_from;
    view->index_used = prepared->index_used;
    view->index_fields = prepared->index_fields;
    view->commercial_only = prepared->commercial_only;
    view->commercial_upstream = prepared->commercial_upstream;
    view->historical_excluded = prepared->historical_excluded;
    view->source_counts = prepared->source_counts;
    view->qc_counts = prepared->qc_counts;
    view->astro = prepared->astro;
    view->last_status = prepared->last_status;
    memcpy(view->last_message, prepared->last_message, sizeof view->last_message);
}

static int release_destination_blank(const otc_release *view)
{
    const otc_release zero = {0};
    return view && !view->file &&
        !view->path &&
        !view->meta &&
        !view->release_obj &&
        !view->conv &&
        !view->n_conv &&
        !view->lic &&
        !view->n_lic &&
        !view->st &&
        !view->n_st &&
        !view->tomb &&
        !view->n_tomb &&
        !view->alias &&
        !view->n_alias &&
        !view->cnames &&
        !view->n_cnames &&
        !view->files &&
        !view->n_files &&
        !view->zenodo_version_doi &&
        !memcmp(view->created, zero.created, sizeof view->created) &&
        !view->loaded_from &&
        !view->index_used &&
        !view->index_fields &&
        !view->commercial_only &&
        !view->commercial_upstream &&
        !view->historical_excluded &&
        (!view->source_counts.items && !view->source_counts.n && !view->source_counts.cap) &&
        (!view->qc_counts.items && !view->qc_counts.n && !view->qc_counts.cap) &&
        !view->astro &&
        !view->last_status &&
        !memcmp(view->last_message, zero.last_message, sizeof view->last_message);
}

otc_status otc__release_bind_prepared_fields(otc__prepared_release_fields *prepared, otc_release **out)
{
    otc_release *destination;
    if (!prepared || !out || !prepared->complete || !prepared->file || !prepared->meta ||
        !release_destination_blank(prepared->destination)) return OTC_E_INVALID_ARGUMENT;
    destination = prepared->destination;
    release_import_fields(destination, prepared);
    memset(prepared, 0, sizeof *prepared);
    *out = destination;
    return OTC_OK;
}

void otc__release_prepared_clear(otc__prepared_release_fields *prepared)
{
    otc_release view = {0};
    otc_release *destination;
    if (!prepared) return;
    destination = prepared->destination;
    release_import_fields(&view, prepared);
    release_clear_resource_fields(&view);
    memset(prepared, 0, sizeof *prepared);
    otc_close(destination);
}

otc_status otc_open_file(const char *path, const otc_open_options *opts, otc_release **out)
{
    /* the error field is at the same place in every layout that has it (C56) */
    otc_error *err = (opts && opts->struct_size >= offsetof(otc_open_options, error) + sizeof opts->error)
                         ? otc__err_usable(opts->error) : NULL;
    otc_release *r;
    otc__prepared_release_fields prepared = {0};
    otc_status st;
    otc__err_reset(err);
    if (!out || !path) {
        otc__err_set(err, OTC_E_INVALID_ARGUMENT, NULL, "path and out must not be NULL");
        return OTC_E_INVALID_ARGUMENT;
    }
    *out = NULL;
    /* a struct from before K-NC (no commercial_only) is still taken (spec 6.4, K-NC DR106) */
    if (opts && opts->struct_size < OTC__OPEN_OPTIONS_MIN) {
        otc__err_set(err, OTC_E_INVALID_ARGUMENT, NULL, "otc_open_options: struct_size is too small");
        return OTC_E_INVALID_ARGUMENT;
    }
    st = otc__open_policy_options(opts, err);
    if (st != OTC_OK) return st;
    r = (otc_release *)calloc(1, sizeof *r);
    if (!r) {
        otc__err_set(err, OTC_E_NOMEM, path, "out of memory");
        return OTC_E_NOMEM;
    }
    otc__mutex_init(&r->lock);
    st = otc__release_prepare_fields(path, opts, err, r, 1, &prepared);
    if (st != OTC_OK && st != OTC_E_NOMEM && prepared.index_used) {
        /* an index that looked fresh but could not be used: open again with the one pass */
        otc__release_prepared_clear(&prepared);
        r = (otc_release *)calloc(1, sizeof *r);
        if (!r) {
            otc__err_set(err, OTC_E_NOMEM, path, "out of memory");
            return OTC_E_NOMEM;
        }
        otc__mutex_init(&r->lock);
        otc__err_reset(err);
        st = otc__release_prepare_fields(path, opts, err, r, 0, &prepared);
    }
    if (st == OTC_OK) st = otc__release_bind_prepared_fields(&prepared, &r);
    if (st != OTC_OK) {
        otc__release_prepared_clear(&prepared);
        return st;
    }
    if (opts && opts->log_fn) {
        char msg[256];
        snprintf(msg, sizeof msg, "opened %s (%s, %lu stations)", path, otc_loaded_from_name(r->loaded_from),
                 (unsigned long)r->n_st);
        opts->log_fn(opts->log_user_data, 1, msg);
    }
    *out = r;
    return OTC_OK;
}

/* --------------------------------------------------------------- metadata */

otc_loaded_from otc_release_loaded_from(const otc_release *rel)
{
    return rel ? rel->loaded_from : OTC_LOADED_FROM_UNSET;
}

#define REL_STR(NAME, EXPR)                                                                    \
    otc_status NAME(const otc_release *rel, char *buf, size_t len, size_t *needed)             \
    {                                                                                          \
        if (!rel) return OTC_E_INVALID_ARGUMENT;                                               \
        return otc__copy_str(EXPR, buf, len, needed);                                          \
    }

REL_STR(otc_release_datestamp, otc__jstr(rel->release_obj, "datestamp"))
/* release.created in UTC, "YYYY-MM-DDTHH:MM:SSZ", as the other SDKs give it (spec 4.3). A created that
 * is not an RFC 3339 time fails the open (CR2 DR6), so the raw text is never returned. */
REL_STR(otc_release_created, rel->created[0] ? rel->created : NULL)
REL_STR(otc_release_format_version, otc__jstr(rel->meta, "format_version"))
#define REL_MEMBER(NAME, KEY)                                                                  \
    otc_status NAME(const otc_release *rel, char *buf, size_t len, size_t *needed)             \
    {                                                                                          \
        return rel ? otc__copy_member(rel->release_obj, KEY, buf, len, needed) : OTC_E_INVALID_ARGUMENT; \
    }
REL_MEMBER(otc_release_concept_doi, "concept_doi")
REL_STR(otc_release_zenodo_version_doi, rel->zenodo_version_doi)
REL_MEMBER(otc_release_build_commit, "build_commit")
REL_MEMBER(otc_release_changelog_url, "changelog_url")

size_t otc_release_source_version_count(const otc_release *rel)
{
    const cJSON *sv = rel ? otc__jget(rel->release_obj, "source_versions") : NULL;
    return cJSON_IsObject(sv) ? (size_t)cJSON_GetArraySize(sv) : 0;
}

otc_status otc_release_source_version_at(const otc_release *rel, size_t i, char *source, size_t source_len,
                                         size_t *source_needed, char *version, size_t version_len,
                                         size_t *version_needed)
{
    const cJSON *item;
    otc_status a, b;
    if (!rel || i >= otc_release_source_version_count(rel)) return OTC_E_INVALID_ARGUMENT;
    item = cJSON_GetArrayItem(otc__jget(rel->release_obj, "source_versions"), (int)i);
    a = otc__copy_str(item->string, source, source_len, source_needed);
    b = otc__copy_jstr(item, version, version_len, version_needed);   /* a string: checked at open */
    return a != OTC_OK ? a : b;
}

size_t otc_release_file_count(const otc_release *rel) { return rel ? rel->n_files : 0; }

otc_status otc_release_file_at(const otc_release *rel, size_t i, const otc_file_info **out)
{
    if (out) *out = NULL;   /* a failed call leaves no value behind */
    if (!rel || !out || i >= rel->n_files) return OTC_E_INVALID_ARGUMENT;
    *out = &rel->files[i];
    return OTC_OK;
}

otc_status otc_file_info_name(const otc_file_info *fi, char *buf, size_t len, size_t *needed)
{
    return fi ? otc__copy_str(fi->name, buf, len, needed) : OTC_E_INVALID_ARGUMENT;
}
otc_status otc_file_info_url(const otc_file_info *fi, char *buf, size_t len, size_t *needed)
{
    return fi ? otc__copy_str(fi->url, buf, len, needed) : OTC_E_INVALID_ARGUMENT;
}
int64_t otc_file_info_size(const otc_file_info *fi) { return fi ? fi->size : -1; }
otc_status otc_file_info_sha256(const otc_file_info *fi, char *buf, size_t len, size_t *needed)
{
    return fi ? otc__copy_str(fi->sha256, buf, len, needed) : OTC_E_INVALID_ARGUMENT;
}

size_t otc_release_station_count(const otc_release *rel) { return rel ? rel->n_st : 0; }
size_t otc_release_tombstone_count(const otc_release *rel) { return rel ? rel->n_tomb : 0; }

otc_status otc_release_constituent_names(const otc_release *rel, const char **out, size_t cap, size_t *count)
{
    size_t i;
    if (!rel || !count || (!out && cap)) return OTC_E_INVALID_ARGUMENT;
    *count = rel->n_cnames;
    for (i = 0; i < rel->n_cnames && i < cap; i++) out[i] = rel->cnames[i];
    if (!out) return OTC_OK;
    return cap < rel->n_cnames ? OTC_E_BUFFER_TOO_SMALL : OTC_OK;
}

/* Spec 4.6: "OpenTideConstants contributors ({year}). OpenTideConstants, release {D} [Data set]. {link}{version}",
 * where {year} is the first four digits of the datestamp, {link} is https://doi.org/{concept_doi} (the
 * release URL when the concept DOI is null) and {version} is " (version DOI: https://doi.org/{zenodo_version_doi})"
 * when the release has its own Zenodo version, else empty. */
otc_status otc_release_citation(const otc_release *rel, char *buf, size_t len, size_t *needed)
{
    const char *d, *doi, *vdoi;
    char *text;
    size_t cap;
    otc_status st;
    if (!rel) return OTC_E_INVALID_ARGUMENT;
    d = otc__jstr(rel->release_obj, "datestamp");
    doi = otc__jstr(rel->release_obj, "concept_doi");
    vdoi = rel->zenodo_version_doi;
    cap = 256 + 2 * strlen(d) + (doi ? strlen(doi) : 0) + (vdoi ? strlen(vdoi) : 0);
    text = (char *)malloc(cap);
    if (!text) return otc__fail(rel, OTC_E_NOMEM, "out of memory");
    if (doi)
        snprintf(text, cap, "OpenTideConstants contributors (%.4s). OpenTideConstants, release %s [Data set]. "
                 "https://doi.org/%s", d, d, doi);
    else
        snprintf(text, cap, "OpenTideConstants contributors (%.4s). OpenTideConstants, release %s [Data set]. "
                 "https://data.opentideconstants.org/OTC_%s.json", d, d, d);
    if (vdoi) {
        size_t n = strlen(text);
        snprintf(text + n, cap - n, " (version DOI: https://doi.org/%s)", vdoi);
    }
    st = otc__copy_str(text, buf, len, needed);
    free(text);
    return st;
}

static int str_ptr_cmp(const void *a, const void *b)
{
    return strcmp(*(const char *const *)a, *(const char *const *)b);
}

otc_status otc_attribution(const otc_release *rel, const char *const *ids, size_t n_ids, char *buf, size_t len,
                           size_t *needed)
{
    const char **lic = NULL;
    const char **seen_prov = NULL, **seen_att = NULL;
    size_t n_lic = 0, cap, i, n_seen = 0, total, n_nc = 0;
    const char *d, *doi;
    char *head, *text;
    size_t head_cap;
    otc_status st;
    if (!rel || (n_ids && !ids)) return otc__fail(rel, OTC_E_INVALID_ARGUMENT, "otc_attribution: ids is NULL");
    if (n_ids == 0) ids = NULL;   /* spec 4.6 (CR D2): an empty list is every licence of the release */
    for (i = 0; ids && i < n_ids; i++)   /* an unknown or removed id is an error, never skipped (CR D2) */
        if (!ids[i] || !otc__find_entry(rel, ids[i]))
            return otc__fail(rel, OTC_E_INVALID_ARGUMENT, "otc_attribution: %s is not an active station of this release",
                             ids[i] ? ids[i] : "(NULL)");
    /* per station: its own set, every offsets licence of the chain and the set that ends it */
    if (ids && n_ids > ((size_t)-1 - 1) / (OTC__MAX_LINKS + 3)) return OTC_E_NOMEM;
    cap = ids ? n_ids * (OTC__MAX_LINKS + 3) + 1 : rel->n_lic + 1;
    lic = (const char **)calloc(cap, sizeof *lic);
    seen_prov = (const char **)calloc(cap, sizeof *seen_prov);
    seen_att = (const char **)calloc(cap, sizeof *seen_att);
    if (!lic || !seen_prov || !seen_att) {
        free((void *)lic); free((void *)seen_prov); free((void *)seen_att);
        return otc__fail(rel, OTC_E_NOMEM, "out of memory");
    }
    if (!ids) {
        /* with commercial_only, only the commercial licences (K-NC DR106) */
        for (i = 0; i < rel->n_lic; i++)
            if (!rel->commercial_only || rel->lic[i].commercial_use) lic[n_lic++] = rel->lic[i].id;
    } else if (rel->commercial_only) {
        /* the licences of each station's tide source (spec 4.2, 4.6, K-NC DR106): its effective recommended set;
         * else the one-link offsets path (the reference station's first set from the offsets' source), usable
         * only when the offsets' licence and that set's licence allow commercial use; else none */
        for (i = 0; i < n_ids; i++) {
            const otc__entry *e = otc__find_entry(rel, ids[i]), *ref;
            if (e->eff_pos >= 0) {
                lic[n_lic++] = e->eff_licence;
                continue;
            }
            if (!e->has_offsets) continue;
            ref = e->ref_id ? otc__find_entry(rel, e->ref_id) : NULL;
            if (!ref || !ref->offsets_ref_licence || !licence_commercial(rel, ref->offsets_ref_licence)) continue;
            if (e->off_licence && !licence_commercial(rel, e->off_licence)) continue;
            lic[n_lic++] = ref->offsets_ref_licence;
            if (e->off_licence) lic[n_lic++] = e->off_licence;
        }
    } else {
        for (i = 0; i < n_ids; i++) {
            const otc__entry *e = otc__find_entry(rel, ids[i]);
            const otc__entry *path[OTC__MAX_LINKS + 1];
            size_t links = 0;
            if (e->has_rec && e->rec_licence) lic[n_lic++] = e->rec_licence;
            /* spec 4.6 (CR2 DR1): walk the reference chain through at most OTC__MAX_LINKS links (the kind rule of
             * 6.2). Take the offsets licence of each station on the path, and the licence of the first recommended
             * set reached, where the walk stops. A loop or a missing station ends the walk: the load checked the
             * links. */
            path[0] = e;
            while (e->type == OTC_STATION_TYPE_SUBORDINATE && e->has_offsets) {
                const otc__entry *ref;
                size_t k;
                int loop = 0;
                if (e->off_licence) lic[n_lic++] = e->off_licence;
                if (links == OTC__MAX_LINKS) break;
                ref = e->ref_id ? otc__find_entry(rel, e->ref_id) : NULL;
                for (k = 0; ref && k <= links; k++)
                    if (path[k] == ref) loop = 1;
                if (!ref || loop) break;
                path[++links] = ref;
                if (ref->has_rec) {
                    if (ref->rec_licence) lic[n_lic++] = ref->rec_licence;
                    break;
                }
                e = ref;
            }
        }
    }
    if (n_lic > 1) qsort((void *)lic, n_lic, sizeof *lic, str_ptr_cmp);
    d = otc__jstr(rel->release_obj, "datestamp");
    doi = otc__jstr(rel->release_obj, "concept_doi");   /* never the version DOI (spec 4.6) */
    head_cap = 160 + 2 * strlen(d) + (doi ? strlen(doi) : 0);
    head = (char *)malloc(head_cap);
    if (!head) {
        free((void *)lic); free((void *)seen_prov); free((void *)seen_att);
        return otc__fail(rel, OTC_E_NOMEM, "out of memory");
    }
    if (doi) snprintf(head, head_cap, "Tidal constants: OpenTideConstants %s, doi:%s, CC BY 4.0.", d, doi);
    else snprintf(head, head_cap, "Tidal constants: OpenTideConstants %s, https://data.opentideconstants.org/OTC_%s.json, CC BY 4.0.", d, d);
    /* one entry per licence id (sorted), then one per provider */
    total = strlen(head) + strlen(" Sources: ") + 1;
    for (i = 0; i < n_lic; i++) {
        const otc_licence *l = (i > 0 && !strcmp(lic[i], lic[i - 1])) ? NULL : otc__find_licence(rel, lic[i]);
        const char *prov, *att;
        size_t j;
        int dup = 0;
        if (!l) continue;
        if (!l->commercial_use) {   /* its notice entry (K-NC DR105): "{provider or licence_id} ({spdx}, {terms_url})" */
            const char *np = otc__jstr(l->json, "provider");
            const char *sp = otc__jstr(l->json, "spdx"), *tu = otc__jstr(l->json, "terms_url");
            total += strlen(np ? np : l->id) + (sp ? strlen(sp) : 0) + (tu ? strlen(tu) : 0) + 7;   /* "; " " (" ", " ")" */
            n_nc++;
        }
        prov = otc__jstr(l->json, "provider");
        att = otc__jstr(l->json, "attribution");
        /* each provider once; a licence with no provider is its own entry, never merged (CR D2) */
        for (j = 0; prov && j < n_seen; j++)
            if (!otc__strcmp_null(seen_prov[j], prov)) dup = 1;
        if (dup) continue;
        seen_prov[n_seen] = prov;
        seen_att[n_seen++] = att;
        total += (prov ? strlen(prov) + 2 : 0) + (att ? strlen(att) : 0) + 2;
    }
    total += n_nc ? strlen(". Non-commercial use only: ") : 0;
    text = (char *)malloc(total);
    if (!text) {
        free(head); free((void *)lic); free((void *)seen_prov); free((void *)seen_att);
        return otc__fail(rel, OTC_E_NOMEM, "out of memory");
    }
    strcpy(text, head);
    free(head);
    /* an empty scope: the dataset header alone (spec 4.6, K-NC DR106) */
    if (n_lic) strcat(text, " Sources: ");
    for (i = 0; i < n_seen; i++) {
        if (i) strcat(text, "; ");
        if (seen_prov[i]) {   /* "{provider}: {attribution}", or the attribution alone */
            strcat(text, seen_prov[i]);
            strcat(text, ": ");
        }
        strcat(text, seen_att[i] ? seen_att[i] : "");
    }
    /* the non-commercial notice (spec 4.6, K-NC DR105): once, then one entry per non-commercial licence in scope,
     * by licence_id, joined with "; "; a null provider gives the licence_id */
    if (n_nc) {
        size_t k = 0;
        strcat(text, ". Non-commercial use only: ");
        for (i = 0; i < n_lic; i++) {
            const otc_licence *l = (i > 0 && !strcmp(lic[i], lic[i - 1])) ? NULL : otc__find_licence(rel, lic[i]);
            const char *np, *sp, *tu;
            if (!l || l->commercial_use) continue;
            np = otc__jstr(l->json, "provider");
            sp = otc__jstr(l->json, "spdx");
            tu = otc__jstr(l->json, "terms_url");
            if (k++) strcat(text, "; ");
            strcat(text, np ? np : l->id);
            strcat(text, " (");
            strcat(text, sp ? sp : "");
            strcat(text, ", ");
            strcat(text, tu ? tu : "");
            strcat(text, ")");
        }
    }
    st = otc__copy_str(text, buf, len, needed);
    free(text);
    free((void *)lic);
    free((void *)seen_prov);
    free((void *)seen_att);
    return st;
}

/* ------------------------------------------------------------------ stats */

struct otc_stats {
    otc__kvlist type, kind, country, source, qc_status;
};

otc_status otc__release_prepare_stats_fields(const otc_release *rel, otc__prepared_stats_fields *prepared)
{
    otc_stats fields = {0}, *s = &fields;
    otc_stats *destination;
    size_t i;
    otc_status st = OTC_OK;
    if (prepared) memset(prepared, 0, sizeof *prepared);
    if (!rel || !prepared) return otc__fail(rel, OTC_E_INVALID_ARGUMENT, "otc_release_stats: NULL argument");
    destination = (otc_stats *)calloc(1, sizeof *destination);
    if (!destination) return otc__fail(rel, OTC_E_NOMEM, "out of memory");
    prepared->destination = destination;
    for (i = 0; i < rel->n_st && st == OTC_OK; i++) {
        const otc__entry *e = &rel->st[i];
        st = otc__kv_add(&s->type, otc_station_type_name(e->type), 1);   /* typed: unknown is "other" (CR2 DR7) */
        if (st == OTC_OK) st = otc__kv_add(&s->kind, otc_kind_name(e->kind), 1);
        if (st == OTC_OK) st = otc__kv_add(&s->country, e->country, 1);
    }
    for (i = 0; i < rel->source_counts.n && st == OTC_OK; i++)
        st = otc__kv_add(&s->source, rel->source_counts.items[i].key, rel->source_counts.items[i].n);
    for (i = 0; i < rel->qc_counts.n && st == OTC_OK; i++)
        st = otc__kv_add(&s->qc_status, rel->qc_counts.items[i].key, rel->qc_counts.items[i].n);
    if (st != OTC_OK) { prepared->type = s->type; prepared->kind = s->kind; prepared->country = s->country; prepared->source = s->source; prepared->qc_status = s->qc_status; otc__stats_prepared_clear(prepared); return otc__fail(rel, st, "out of memory"); }
    otc__kv_sort(&s->type);
    otc__kv_sort(&s->kind);
    otc__kv_sort(&s->country);
    otc__kv_sort(&s->source);
    otc__kv_sort(&s->qc_status);
    prepared->type = s->type; prepared->kind = s->kind; prepared->country = s->country; prepared->source = s->source; prepared->qc_status = s->qc_status;
    prepared->complete = true;
    return OTC_OK;
}

otc_status otc__stats_bind_prepared(otc__prepared_stats_fields *prepared, otc_stats **out)
{
    otc_stats *destination;
    if (out) *out = NULL;
    if (!prepared || !out || !prepared->complete || !prepared->destination)
        return OTC_E_INVALID_ARGUMENT;
    destination = prepared->destination;
    if (destination->type.items || destination->kind.items || destination->country.items ||
        destination->source.items || destination->qc_status.items) return OTC_E_INVALID_ARGUMENT;
    destination->type = prepared->type; destination->kind = prepared->kind;
    destination->country = prepared->country; destination->source = prepared->source;
    destination->qc_status = prepared->qc_status;
    memset(prepared, 0, sizeof *prepared);
    *out = destination;
    return OTC_OK;
}

void otc__stats_prepared_clear(otc__prepared_stats_fields *prepared)
{
    if (!prepared) return;
    otc__kv_free(&prepared->type); otc__kv_free(&prepared->kind);
    otc__kv_free(&prepared->country); otc__kv_free(&prepared->source); otc__kv_free(&prepared->qc_status);
    free(prepared->destination);
    memset(prepared, 0, sizeof *prepared);
}

otc_status otc_release_stats(const otc_release *rel, otc_stats **out)
{
    otc__prepared_stats_fields prepared = {0};
    otc_status status;
    if (out) *out = NULL;
    if (!rel || !out) return otc__fail(rel, OTC_E_INVALID_ARGUMENT, "otc_release_stats: NULL argument");
    status = otc__release_prepare_stats_fields(rel, &prepared);
    if (status == OTC_OK) status = otc__stats_bind_prepared(&prepared, out);
    otc__stats_prepared_clear(&prepared);
    return status;
}

void otc_stats_free(otc_stats *s)
{
    if (!s) return;
    otc__kv_free(&s->type);
    otc__kv_free(&s->kind);
    otc__kv_free(&s->country);
    otc__kv_free(&s->source);
    otc__kv_free(&s->qc_status);
    free(s);
}

#define STATS_FUNCS(F)                                                                         \
    size_t otc_stats_##F##_count(const otc_stats *s) { return s ? s->F.n : 0; }                \
    otc_status otc_stats_##F##_at(const otc_stats *s, size_t i, const char **key, int64_t *n)   \
    {                                                                                          \
        if (key) *key = NULL;   /* a failed call leaves no value behind */                    \
        if (n) *n = -1;                                                                        \
        if (!s || i >= s->F.n || !key || !n) return OTC_E_INVALID_ARGUMENT;                    \
        *key = s->F.items[i].key;                                                              \
        *n = s->F.items[i].n;                                                                  \
        return OTC_OK;                                                                         \
    }
STATS_FUNCS(type)
STATS_FUNCS(kind)
STATS_FUNCS(country)
STATS_FUNCS(source)
STATS_FUNCS(qc_status)

/* ---------------------------------------------- conventions and licences */

size_t otc_release_convention_count(const otc_release *rel) { return rel ? rel->n_conv : 0; }

otc_status otc_release_convention_at(const otc_release *rel, size_t i, const otc_convention **out)
{
    if (out) *out = NULL;   /* a failed call leaves no value behind */
    if (!rel || !out || i >= rel->n_conv) return OTC_E_INVALID_ARGUMENT;
    *out = &rel->conv[i];
    return OTC_OK;
}

otc_status otc_release_convention(const otc_release *rel, const char *id, const otc_convention **out)
{
    if (out) *out = NULL;   /* a failed call leaves no value behind */
    if (!rel || !out || !id) return OTC_E_INVALID_ARGUMENT;
    *out = otc__find_convention(rel, id);
    return *out ? OTC_OK : OTC_E_NOT_FOUND;
}

#define CONV_STR(NAME, KEY)                                                                    \
    otc_status NAME(const otc_convention *c, char *buf, size_t len, size_t *needed)            \
    {                                                                                          \
        return c ? otc__copy_member(c->json, KEY, buf, len, needed) : OTC_E_INVALID_ARGUMENT; \
    }
#define CONV_JSON(NAME, KEY)                                                                   \
    otc_status NAME(const otc_convention *c, char *buf, size_t len, size_t *needed)            \
    {                                                                                          \
        return c ? otc__copy_json(otc__jget(c->json, KEY), buf, len, needed) : OTC_E_INVALID_ARGUMENT; \
    }
CONV_STR(otc_convention_convention_id, "convention_id")
CONV_STR(otc_convention_v0_model, "v0_model")
CONV_STR(otc_convention_constituent_table_version, "constituent_table_version")
CONV_STR(otc_convention_tables_sha256, "tables_sha256")
CONV_JSON(otc_convention_nodal_formula_ids_json, "nodal_formula_ids")
CONV_JSON(otc_convention_canary_json, "canary")

otc_status otc_convention_raw_json(const otc_convention *c, char *buf, size_t len, size_t *needed)
{
    return c ? otc__copy_json(c->json, buf, len, needed) : OTC_E_INVALID_ARGUMENT;
}

otc_phase_reference otc_convention_phase_reference(const otc_convention *c)
{
    return c ? otc__parse_phase_reference(otc__jstr(c->json, "phase_reference")) : OTC_PHASE_REFERENCE_UNSET;
}

double otc_convention_utc_offset_hours(const otc_convention *c)
{
    return c ? otc__jnum(c->json, "utc_offset_hours") : NAN;
}

otc_nodal_handling otc_convention_nodal_handling(const otc_convention *c)
{
    return c ? otc__parse_nodal_handling(otc__jstr(c->json, "nodal_handling")) : OTC_NODAL_HANDLING_UNSET;
}

size_t otc_release_licence_count(const otc_release *rel) { return rel ? rel->n_lic : 0; }

otc_status otc_release_licence_at(const otc_release *rel, size_t i, const otc_licence **out)
{
    if (out) *out = NULL;   /* a failed call leaves no value behind */
    if (!rel || !out || i >= rel->n_lic) return OTC_E_INVALID_ARGUMENT;
    *out = &rel->lic[i];
    return OTC_OK;
}

otc_status otc_release_licence(const otc_release *rel, const char *id, const otc_licence **out)
{
    if (out) *out = NULL;   /* a failed call leaves no value behind */
    if (!rel || !out || !id) return OTC_E_INVALID_ARGUMENT;
    *out = otc__find_licence(rel, id);
    return *out ? OTC_OK : OTC_E_NOT_FOUND;
}

#define LIC_STR(NAME, KEY)                                                                     \
    otc_status NAME(const otc_licence *l, char *buf, size_t len, size_t *needed)               \
    {                                                                                          \
        return l ? otc__copy_member(l->json, KEY, buf, len, needed) : OTC_E_INVALID_ARGUMENT; \
    }
LIC_STR(otc_licence_licence_id, "licence_id")
LIC_STR(otc_licence_spdx, "spdx")
LIC_STR(otc_licence_provider, "provider")
LIC_STR(otc_licence_citation, "citation")
LIC_STR(otc_licence_attribution, "attribution")
LIC_STR(otc_licence_url, "url")
LIC_STR(otc_licence_restriction, "restriction")
LIC_STR(otc_licence_terms_url, "terms_url")

bool otc_licence_commercial_use(const otc_licence *l)
{
    return l && l->commercial_use;
}

otc_status otc_licence_raw_json(const otc_licence *l, char *buf, size_t len, size_t *needed)
{
    return l ? otc__copy_json(l->json, buf, len, needed) : OTC_E_INVALID_ARGUMENT;
}

/* ---------------------------------------------------------- release info */

otc_status otc__release_info_bind_prepared(otc__prepared_release_info_fields *prepared, otc_release_info **out)
{
    otc_release_info *destination;
    if (out) *out = NULL;
    if (!prepared || !out || !prepared->complete || !prepared->destination || !prepared->datestamp)
        return OTC_E_INVALID_ARGUMENT;
    destination = prepared->destination;
    if (destination->datestamp || destination->format_version || destination->min_reader_version ||
        destination->concept_doi || destination->zenodo_version_doi || destination->content_sha256 ||
        destination->files || destination->n_files) return OTC_E_INVALID_ARGUMENT;
    destination->datestamp = prepared->datestamp; destination->format_version = prepared->format_version;
    destination->min_reader_version = prepared->min_reader_version;
    destination->concept_doi = prepared->concept_doi; destination->zenodo_version_doi = prepared->zenodo_version_doi;
    destination->content_sha256 = prepared->content_sha256; destination->files = prepared->files;
    destination->n_files = prepared->n_files;
    memset(prepared, 0, sizeof *prepared);
    *out = destination;
    return OTC_OK;
}

void otc__release_info_prepared_clear(otc__prepared_release_info_fields *prepared)
{
    if (!prepared) return;
    free(prepared->datestamp); free(prepared->format_version); free(prepared->min_reader_version);
    free(prepared->concept_doi); free(prepared->zenodo_version_doi); free(prepared->content_sha256);
    free_files(prepared->files, prepared->n_files);
    free(prepared->destination);
    memset(prepared, 0, sizeof *prepared);
}

void otc_release_info_free(otc_release_info *ri)
{
    if (!ri) return;
    free(ri->datestamp);
    free(ri->format_version);
    free(ri->min_reader_version);
    free(ri->concept_doi);
    free(ri->zenodo_version_doi);
    free(ri->content_sha256);
    free_files(ri->files, ri->n_files);
    free(ri);
}

otc_status otc_release_info_datestamp(const otc_release_info *ri, char *buf, size_t len, size_t *needed)
{
    return ri ? otc__copy_str(ri->datestamp, buf, len, needed) : OTC_E_INVALID_ARGUMENT;
}
otc_status otc_release_info_format_version(const otc_release_info *ri, char *buf, size_t len, size_t *needed)
{
    return ri ? otc__copy_str(ri->format_version, buf, len, needed) : OTC_E_INVALID_ARGUMENT;
}
otc_status otc_release_info_concept_doi(const otc_release_info *ri, char *buf, size_t len, size_t *needed)
{
    return ri ? otc__copy_str(ri->concept_doi, buf, len, needed) : OTC_E_INVALID_ARGUMENT;
}
otc_status otc_release_info_zenodo_version_doi(const otc_release_info *ri, char *buf, size_t len, size_t *needed)
{
    return ri ? otc__copy_str(ri->zenodo_version_doi, buf, len, needed) : OTC_E_INVALID_ARGUMENT;
}
otc_status otc_release_info_content_sha256(const otc_release_info *ri, char *buf, size_t len, size_t *needed)
{
    return ri ? otc__copy_str(ri->content_sha256, buf, len, needed) : OTC_E_INVALID_ARGUMENT;
}
size_t otc_release_info_file_count(const otc_release_info *ri) { return ri ? ri->n_files : 0; }
otc_status otc_release_info_file_at(const otc_release_info *ri, size_t i, const otc_file_info **out)
{
    if (out) *out = NULL;   /* a failed call leaves no value behind */
    if (!ri || !out || i >= ri->n_files) return OTC_E_INVALID_ARGUMENT;
    *out = &ri->files[i];
    return OTC_OK;
}

otc_status otc_release_historical_offsets_policy(const otc_release *rel, char *buf, size_t len, size_t *needed)
{
    return rel ? otc__copy_str(rel->historical_excluded ? "exclude" : "fallback", buf, len, needed) : OTC_E_INVALID_ARGUMENT;
}
