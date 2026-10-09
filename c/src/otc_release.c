/* Opening a release (.jsonl + .meta.json), the stream index, release
 * metadata, conventions, licences, stats, citation and attribution
 * (SDK spec 4.2, 4.3, 4.6, 5.3, 6.2, 6.4, 7.3, 7.4). */
#include "otc_internal.h"

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
    return c ? c : strcmp(x->alias, y->alias);
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

otc_status otc__read_station_line(const otc_release *rel, const char *id, uint64_t offset, size_t length, cJSON **out)
{
    otc_status st = otc__read_line(rel, offset, length, out);
    char got[96];
    if (st != OTC_OK) return st;
    if (otc__jstr(*out, "station_id") && !strcmp(otc__jstr(*out, "station_id"), id)) return OTC_OK;
    snprintf(got, sizeof got, "%s", otc__jstr(*out, "station_id") ? otc__jstr(*out, "station_id") : "not a station");
    cJSON_Delete(*out);
    *out = NULL;
    if (rel->index_used) {
        /* spec 6.2 (CR D4): the index named the wrong line; delete it so the next open rebuilds it */
        const char *base = path_base(rel->path);
        char *dir = otc__strndup(rel->path, (size_t)(base - rel->path)), *ix = dir ? otc__join(dir, "index-v1.json") : NULL;
        int removed = ix && otc__remove_file(ix) == 0;
        free(ix);
        free(dir);
        return otc__fail(rel, OTC_E_INVALID_RELEASE,
                         "index-v1.json names the line at offset %llu of %s for station %s, but the line is %s; the "
                         "index is stale%s", (unsigned long long)offset, rel->path, id, got,
                         removed ? " and was deleted (the next open rebuilds it)" : " and could not be deleted");
    }
    return otc__fail(rel, OTC_E_INVALID_RELEASE, "the line at offset %llu of %s is not station %s (it changed after open?)",
                     (unsigned long long)offset, rel->path, id);
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

void otc_close(otc_release *rel)
{
    size_t i;
    if (!rel) return;
    otc__file_close(rel->file);
    free(rel->path);
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
} builder;

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

static otc_status add_alias(builder *b, const char *system, const char *alias, const char *station)
{
    otc_release *r = b->rel;
    GROW(r->alias, r->n_alias, b->cap_alias);
    r->alias[r->n_alias].system = otc__strdup(system);
    r->alias[r->n_alias].alias = otc__strdup(alias);
    r->alias[r->n_alias].station = otc__strdup(station);
    r->n_alias++;
    if (!r->alias[r->n_alias - 1].system || !r->alias[r->n_alias - 1].alias || !r->alias[r->n_alias - 1].station)
        return OTC_E_NOMEM;
    return OTC_OK;
}

/* Checks one constant set and adds what the index needs from it. */
static otc_status index_set(builder *b, const cJSON *set, otc__entry *e, const char *rec_id)
{
    otc_release *r = b->rel;
    const char *set_id = otc__jstr(set, "set_id"), *source = otc__jstr(set, "source");
    const char *qc = otc__jstr(set, "qc_status");
    const char *conv = otc__jstr(set, "convention_id"), *lic = otc__jstr(set, "licence_id");
    const cJSON *cons = otc__jget(set, "constituents"), *c;
    otc_qc_status qcs;
    otc_status st;
    if (!cJSON_IsObject(set) || !set_id || !source || !qc) return bad_line(b, "a constant set lacks set_id, source or qc_status");
    if (!otc__find_convention(r, conv)) return bad_line(b, "a constant set's convention_id does not resolve");
    if (!otc__find_licence(r, lic)) return bad_line(b, "a constant set's licence_id does not resolve");
    if (cons && !cJSON_IsArray(cons)) return bad_line(b, "constituents is not an array");
    if (otc__jget(set, "qc_flags") && !cJSON_IsArray(otc__jget(set, "qc_flags")))
        return bad_line(b, "qc_flags is not an array");
    cJSON_ArrayForEach(c, cons) {
        const char *name = otc__jstr(c, "name");
        if (!name) return bad_line(b, "a constituent has no name");
        if ((st = add_cname(b, name)) != OTC_OK) return st;
    }
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
    if (rec_id && !strcmp(rec_id, set_id)) {
        e->has_rec = 1;
        e->rec_quantity = otc__parse_quantity(otc__jstr(set, "quantity"));
        if (otc__jstr(set, "source_type") && !(e->rec_source_type = otc__strdup(otc__jstr(set, "source_type"))))
            return OTC_E_NOMEM;
        if (!(e->rec_licence = otc__strdup(lic))) return OTC_E_NOMEM;
    }
    return OTC_OK;
}

/* Indexes one parsed station line (root is not freed here). raw / raw_len: the
 * line's JSON text when it may hold a name with a NUL (else NULL). */
static otc_status index_parsed(builder *b, const cJSON *root, size_t len, uint64_t offset, const char *raw,
                               size_t raw_len)
{
    otc_release *r = b->rel;
    const char *id, *status;
    otc_status st = OTC_OK;
    id = otc__jstr(root, "station_id");
    status = otc__jstr(root, "status");
    if (!cJSON_IsObject(root) || !id || !status) return bad_line(b, "not a station object with station_id and status");
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
        const char *name = otc__jstr(root, "name"), *rec_id = otc__jstr(root, "recommended_set_id");
        const cJSON *lat = otc__jget(root, "lat"), *lon = otc__jget(root, "lon");
        if (!name || !cJSON_IsNumber(lat) || !cJSON_IsNumber(lon) || !otc__jstr(root, "type"))
            return bad_line(b, "an active station lacks name, lat, lon or type");
        if ((sets && !cJSON_IsArray(sets)) || (aliases && !cJSON_IsObject(aliases)))
            return bad_line(b, "constant_sets is not an array or aliases is not an object");
        if (r->n_st == b->cap_st) {
            size_t nc = b->cap_st ? b->cap_st * 2 : 64;
            otc__entry *np = (otc__entry *)realloc(r->st, nc * sizeof *np);
            if (!np) return OTC_E_NOMEM;
            r->st = np;
            b->cap_st = nc;
        }
        e = &r->st[r->n_st++];
        memset(e, 0, sizeof *e);
        e->offset = offset;
        e->length = len;
        e->lat = lat->valuedouble;
        e->lon = lon->valuedouble;
        e->type_s = otc__strdup(otc__jstr(root, "type"));
        e->type = otc__parse_station_type(e->type_s);
        e->id = otc__strdup(id);
        e->name_len = strlen(name);
        if (raw && otc__json_has_nul(raw, raw_len)) {
            /* cJSON ends the name at a NUL; the full name comes from the text */
            int got = otc__json_member_string(raw, raw_len, "name", &e->name, &e->name_len);
            if (got < 0) return OTC_E_NOMEM;
            if (got == 0) e->name_len = strlen(name);
        }
        if (!e->name) e->name = otc__strdup(name);
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
            /* spec 4.5: a link that does not resolve fails the open (the reference station
             * is checked when every line is in) */
            if (ol && !otc__find_licence(r, ol)) return bad_line(b, "subordinate_offsets.licence_id does not resolve");
        }
        cJSON_ArrayForEach(s, sets) {
            const cJSON *t;
            const char *sid = otc__jstr(s, "set_id");
            for (t = sets->child; sid && t != s; t = t->next) {   /* spec 6.1 (CR D5): a set_id once per station */
                if (!otc__strcmp_null(otc__jstr(t, "set_id"), sid)) {
                    st = bad_line(b, "a set_id appears twice in the station");
                    break;
                }
            }
            if (st != OTC_OK || (st = index_set(b, s, e, rec_id)) != OTC_OK) break;
        }
        if (st == OTC_OK && rec_id && !e->has_rec) st = bad_line(b, "recommended_set_id does not resolve");
        if (st == OTC_OK) {
            cJSON_ArrayForEach(a, aliases) {
                if (cJSON_IsString(a)) {
                    st = add_alias(b, a->string, a->valuestring, id);
                } else if (cJSON_IsArray(a)) {
                    const cJSON *x;
                    cJSON_ArrayForEach(x, a) {
                        if (!cJSON_IsString(x)) { st = bad_line(b, "an alias id is not a string"); break; }
                        if ((st = add_alias(b, a->string, x->valuestring, id)) != OTC_OK) break;
                    }
                } else {
                    st = bad_line(b, "an alias is not a string or a list");
                }
                if (st != OTC_OK) break;
            }
        }
    }
    /* any other status: a newer minor's value; the station is not listed (7.3) */
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
    st = index_parsed(b, root, len, offset, line, len);
    cJSON_Delete(root);
    return st;
}

/* 1 when a line is empty or only spaces and tabs (the other SDKs skip such lines too). */
static int blank(const char *line, size_t len)
{
    size_t i;
    for (i = 0; i < len; i++)
        if (line[i] != ' ' && line[i] != '\t') return 0;
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
                while (len > 0 && line[len - 1] == '\r') len--;
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
        while (n > 0 && line[n - 1] == '\r') n--;
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

/* Every key of an index entry, with its type (spec 6.2). */
static int entry_ok(const cJSON *e, int64_t size)
{
    const cJSON *a, *x, *sets, *cs;
    size_t i;
    if (!cJSON_IsObject(e) || !whole_ok(otc__jget(e, "offset")) || !whole_ok(otc__jget(e, "length"))) return 0;
    /* the bounds check of spec 6.2 (CR D4): length > 0 and offset + length <= jsonl_size (the
     * caller checks that the offsets increase) */
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
    if (v && !cJSON_IsNull(v)) put(to, as, cJSON_Duplicate(v, 1), ok);
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
        cJSON_ArrayForEach(n, otc__jget(cs, "constituents")) {
            cJSON *c = cJSON_CreateObject();
            if (cJSON_IsString(n)) put(c, "name", cJSON_CreateString(n->valuestring), &ok);
            put(cons, NULL, c, &ok);
        }
        put(s, "constituents", cons, &ok);
        put(sets, NULL, s, &ok);
    }
    put(o, "constant_sets", sets, &ok);
    if (otc__jstr(e, "reference_station_id") || otc__jstr(e, "offsets_licence_id")) {
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
    /* a name with a NUL does not survive cJSON: such an index is read from the .jsonl instead */
    if (otc__json_has_nul(text, len)) goto done;
    if (otc__json_parse_st(text, len, &doc) == OTC_E_NOMEM) { st = OTC_E_NOMEM; goto done; }
    v = otc__jget(doc, "index_version");
    if (!cJSON_IsObject(doc) || !cJSON_IsNumber(v) || v->valuedouble != 1.0) goto done;
    if (otc__strcmp_null(otc__jstr(doc, "datestamp"), ds) || otc__strcmp_null(otc__jstr(doc, "jsonl"), jsonl_name)
        || otc__strcmp_null(otc__jstr(doc, "jsonl_sha256"), sha))
        goto done;
    v = otc__jget(doc, "jsonl_size");
    if (!cJSON_IsNumber(v) || v->valuedouble != (double)size || !cJSON_IsArray(otc__jget(doc, "stations"))) goto done;
    {
        double prev = -1;
        cJSON_ArrayForEach(e, otc__jget(doc, "stations")) {
            if (!entry_ok(e, size) || otc__jget(e, "offset")->valuedouble <= prev) goto done;
            prev = otc__jget(e, "offset")->valuedouble;
        }
    }
    st = OTC_OK;
    cJSON_ArrayForEach(e, otc__jget(doc, "stations")) {
        cJSON *line = line_from_entry(e);
        if (!line) { st = OTC_E_NOMEM; break; }
        b->line_no++;
        st = index_parsed(b, line, (size_t)otc__jget(e, "length")->valuedouble,
                          (uint64_t)otc__jget(e, "offset")->valuedouble, NULL, 0);
        cJSON_Delete(line);
        if (st != OTC_OK) break;
    }
done:
    cJSON_Delete(doc);
    free(text);
    free(path);
    return st;
}

static cJSON *jstr_or_null(const cJSON *o, const char *k)
{
    const char *s = otc__jstr(o, k);
    return s ? cJSON_CreateString(s) : cJSON_CreateNull();
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
static otc_status stored_entry_cb(void *ctx, const char *text, size_t len, uint64_t offset)
{
    ix_ctx *x = (ix_ctx *)ctx;
    cJSON *d, *o, *sets, *al;
    const cJSON *offs, *cs, *a, *v;
    const char *rec, *name, *kind = NULL;
    int ok = 1;
    otc_status pst = otc__json_parse_st(text, len, &d);
    if (pst != OTC_OK) return pst;
    o = cJSON_CreateObject();
    sets = cJSON_CreateArray();
    al = cJSON_CreateObject();
    if (!o || !sets || !al) ok = 0;
    offs = otc__jget(d, "subordinate_offsets");
    if (!cJSON_IsObject(offs)) offs = NULL;
    rec = otc__jstr(d, "recommended_set_id");
    name = otc__jstr(d, "name");
    put(o, "offset", cJSON_CreateNumber((double)offset), &ok);
    put(o, "length", cJSON_CreateNumber((double)len), &ok);
    put(o, "station_id", jstr_or_null(d, "station_id"), &ok);
    put(o, "status", jstr_or_null(d, "status"), &ok);
    if (name && otc__json_has_nul(text, len)) {
        /* a name with a NUL (schema-valid): written from the text, in full, as raw JSON */
        char *full = NULL, *fold = NULL, *jn = NULL, *jf = NULL;
        size_t fl = 0, ffl = 0;
        int r = otc__json_member_string(text, len, "name", &full, &fl);
        if (r > 0) fold = otc__fold_n(full, fl, &ffl);
        if (r > 0 && fold) {
            jn = otc__json_escape_n(full, fl);
            jf = otc__json_escape_n(fold, ffl);
        }
        if (r < 0 || (r > 0 && (!fold || !jn || !jf))) ok = 0;
        put(o, "name", jn ? cJSON_CreateRaw(jn) : jstr_or_null(d, "name"), &ok);
        put(o, "name_folded", jf ? cJSON_CreateRaw(jf) : cJSON_CreateNull(), &ok);
        free(full);
        free(fold);
        free(jn);
        free(jf);
    } else {
        char *folded = name ? otc__fold(name) : NULL;
        if (name && !folded) ok = 0;
        put(o, "name", jstr_or_null(d, "name"), &ok);
        put(o, "name_folded", folded ? cJSON_CreateString(folded) : cJSON_CreateNull(), &ok);
        free(folded);
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
        cJSON_ArrayForEach(c, otc__jget(cs, "constituents"))
            if (otc__jstr(c, "name")) put(cons, NULL, cJSON_CreateString(otc__jstr(c, "name")), &ok);
        put(s, "constituents", cons, &ok);
        put(sets, NULL, s, &ok);
        if (rec && !otc__strcmp_null(otc__jstr(cs, "set_id"), rec)) {
            const char *q = otc__jstr(cs, "quantity");
            kind = !q ? NULL : !strcmp(q, "water_level") ? "tide" : !strcmp(q, "current") ? "current" : "other";
        }
    }
    if (otc__jstr(d, "status") && !strcmp(otc__jstr(d, "status"), "active") && otc__jstr(d, "station_id")) {
        const otc__entry *e = otc__find_entry(x->rel, otc__jstr(d, "station_id"));
        if (e) kind = e->kind == OTC_KIND_UNSET ? NULL : otc_kind_name(e->kind);
    }
    put(o, "kind", kind ? cJSON_CreateString(kind) : cJSON_CreateNull(), &ok);
    cJSON_ArrayForEach(a, otc__jget(d, "aliases")) {
        cJSON *list = cJSON_CreateArray();
        const cJSON *id;
        if (cJSON_IsString(a)) put(list, NULL, cJSON_CreateString(a->valuestring), &ok);
        else cJSON_ArrayForEach(id, a) if (cJSON_IsString(id)) put(list, NULL, cJSON_CreateString(id->valuestring), &ok);
        put(al, a->string, list, &ok);
    }
    put(o, "aliases", al, &ok);
    put(o, "reference_station_id", jstr_or_null(offs, "reference_station_id"), &ok);
    put(o, "offsets_licence_id", jstr_or_null(offs, "licence_id"), &ok);
    put(o, "recommended_set_id", jstr_or_null(d, "recommended_set_id"), &ok);
    put(o, "sets", sets, &ok);
    cJSON_Delete(d);
    if (!ok) {
        cJSON_Delete(o);
        return x->st = OTC_E_NOMEM;
    }
    put(x->arr, NULL, o, &ok);
    return ok ? OTC_OK : (x->st = OTC_E_NOMEM);
}

/* The index-v1.json document; NULL when memory runs out or the file cannot be read. */
cJSON *otc__index_doc(const otc_release *rel, const char *jsonl_sha256, const char *by)
{
    cJSON *doc, *arr;
    const char *ds;
    char jsonl[80];
    size_t line_no = 0;
    int ok = 1;
    ix_ctx x;
    if (!rel || !rel->file || !jsonl_sha256) return NULL;
    ds = otc__jstr(rel->release_obj, "datestamp");
    doc = cJSON_CreateObject();
    arr = cJSON_CreateArray();
    if (!doc || !arr || !ds) { cJSON_Delete(doc); cJSON_Delete(arr); return NULL; }
    x.rel = rel;
    x.arr = arr;
    x.st = OTC_OK;
    if (scan_lines(rel->file, &line_no, stored_entry_cb, &x) != OTC_OK || x.st != OTC_OK) {
        cJSON_Delete(doc);
        cJSON_Delete(arr);
        return NULL;
    }
    snprintf(jsonl, sizeof jsonl, "OTC_%s.jsonl", ds);
    put(doc, "index_version", cJSON_CreateNumber(1), &ok);
    put(doc, "datestamp", cJSON_CreateString(ds), &ok);
    put(doc, "jsonl", cJSON_CreateString(jsonl), &ok);
    put(doc, "jsonl_sha256", cJSON_CreateString(jsonl_sha256), &ok);
    put(doc, "jsonl_size", cJSON_CreateNumber((double)otc__file_size(rel->file)), &ok);
    put(doc, "by", cJSON_CreateString(by), &ok);
    put(doc, "stations", arr, &ok);
    if (!ok) {
        cJSON_Delete(doc);
        return NULL;
    }
    return doc;
}

static otc_kind resolve_kind(const otc_release *r, const otc__entry *e, size_t depth)
{
    if (e->has_rec) {
        /* OTHER only for a quantity the library does not know; no quantity is no kind (spec 6.2) */
        if (e->rec_quantity == OTC_QUANTITY_WATER_LEVEL) return OTC_KIND_TIDE;
        if (e->rec_quantity == OTC_QUANTITY_CURRENT) return OTC_KIND_CURRENT;
        return e->rec_quantity == OTC_QUANTITY_UNSET ? OTC_KIND_UNSET : OTC_KIND_OTHER;
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
        if ((created && !cJSON_IsString(created)) || (sv && !cJSON_IsObject(sv))) {
            otc__err_set(err, OTC_E_INVALID_RELEASE, meta_path, "%s: release.%s has the wrong type", meta_path,
                         created && !cJSON_IsString(created) ? "created" : "source_versions");
            return OTC_E_INVALID_RELEASE;
        }
    }
    {   /* spec 7.4: a release that needs a newer reader is refused, naming both versions; a
         * min_reader_version that is present but not MAJOR.MINOR is invalid_release (CR D9) */
        const char *mrv = otc__jstr(r->release_obj, "min_reader_version");
        if (otc__jget(r->release_obj, "min_reader_version") && !otc__version_valid(mrv)) {
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
    if (r->n_cnames > 1) qsort(r->cnames, r->n_cnames, sizeof *r->cnames, cname_cmp);
    for (i = 0; i < r->n_st; i++) r->st[i].kind = resolve_kind(r, &r->st[i], 0);
    otc__kv_sort(&r->source_counts);
    otc__kv_sort(&r->qc_counts);
    st = build_files(r, dir, names, digests, n_rows, jsonl_name, path_base(meta_path));
done:
    free(b.cn_slots);
    otc__free_rows(names, digests, n_rows);
    free(meta_text);
    free(base);
    free(dir);
    free(meta_path);
    free(sha_path);
    if (st == OTC_E_NOMEM) otc__err_set(err, st, path, "out of memory");
    return st;
}

otc_status otc_open_file(const char *path, const otc_open_options *opts, otc_release **out)
{
    /* the error field is at the same place in every layout that has it (C56) */
    otc_error *err = (opts && opts->struct_size >= offsetof(otc_open_options, error) + sizeof opts->error)
                         ? otc__err_usable(opts->error) : NULL;
    otc_release *r;
    otc_status st;
    otc__err_reset(err);
    if (!out || !path) {
        otc__err_set(err, OTC_E_INVALID_ARGUMENT, NULL, "path and out must not be NULL");
        return OTC_E_INVALID_ARGUMENT;
    }
    *out = NULL;
    if (opts && opts->struct_size < sizeof *opts) {
        otc__err_set(err, OTC_E_INVALID_ARGUMENT, NULL, "otc_open_options: struct_size is too small");
        return OTC_E_INVALID_ARGUMENT;
    }
    r = (otc_release *)calloc(1, sizeof *r);
    if (!r) {
        otc__err_set(err, OTC_E_NOMEM, path, "out of memory");
        return OTC_E_NOMEM;
    }
    otc__mutex_init(&r->lock);
    st = open_impl(path, opts, err, r, 1);
    if (st != OTC_OK && st != OTC_E_NOMEM && r->index_used) {
        /* an index that looked fresh but could not be used: open again with the one pass */
        otc_close(r);
        r = (otc_release *)calloc(1, sizeof *r);
        if (!r) {
            otc__err_set(err, OTC_E_NOMEM, path, "out of memory");
            return OTC_E_NOMEM;
        }
        otc__mutex_init(&r->lock);
        otc__err_reset(err);
        st = open_impl(path, opts, err, r, 0);
    }
    if (st != OTC_OK) {
        otc_close(r);
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
/* release.created in UTC, "YYYY-MM-DDTHH:MM:SSZ", as the other SDKs give it (spec 4.3); a value that
 * is not an RFC 3339 time is returned as the file has it */
REL_STR(otc_release_created, rel->created[0] ? rel->created : otc__jstr(rel->release_obj, "created"))
REL_STR(otc_release_format_version, otc__jstr(rel->meta, "format_version"))
REL_STR(otc_release_concept_doi, otc__jstr(rel->release_obj, "concept_doi"))
REL_STR(otc_release_zenodo_version_doi, rel->zenodo_version_doi)
REL_STR(otc_release_build_commit, otc__jstr(rel->release_obj, "build_commit"))
REL_STR(otc_release_changelog_url, otc__jstr(rel->release_obj, "changelog_url"))

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
    b = cJSON_IsString(item) ? otc__copy_str(item->valuestring, version, version_len, version_needed)
                             : otc__copy_json(item, version, version_len, version_needed);
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
    size_t n_lic = 0, cap, i, n_seen = 0, total;
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
        for (i = 0; i < rel->n_lic; i++) lic[n_lic++] = rel->lic[i].id;
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
    if (doi) snprintf(head, head_cap, "Tidal constants: OpenTideConstants %s, doi:%s, CC BY 4.0. Sources: ", d, doi);
    else snprintf(head, head_cap, "Tidal constants: OpenTideConstants %s, https://data.opentideconstants.org/OTC_%s.json, CC BY 4.0. Sources: ", d, d);
    /* one entry per licence id (sorted), then one per provider */
    total = strlen(head) + 1;
    for (i = 0; i < n_lic; i++) {
        const otc_licence *l = (i > 0 && !strcmp(lic[i], lic[i - 1])) ? NULL : otc__find_licence(rel, lic[i]);
        const char *prov, *att;
        size_t j;
        int dup = 0;
        if (!l) continue;
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
    text = (char *)malloc(total);
    if (!text) {
        free(head); free((void *)lic); free((void *)seen_prov); free((void *)seen_att);
        return otc__fail(rel, OTC_E_NOMEM, "out of memory");
    }
    strcpy(text, head);
    free(head);
    for (i = 0; i < n_seen; i++) {
        if (i) strcat(text, "; ");
        if (seen_prov[i]) {   /* "{provider}: {attribution}", or the attribution alone */
            strcat(text, seen_prov[i]);
            strcat(text, ": ");
        }
        strcat(text, seen_att[i] ? seen_att[i] : "");
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

otc_status otc_release_stats(const otc_release *rel, otc_stats **out)
{
    otc_stats *s;
    size_t i;
    otc_status st = OTC_OK;
    if (out) *out = NULL;
    if (!rel || !out) return otc__fail(rel, OTC_E_INVALID_ARGUMENT, "otc_release_stats: NULL argument");
    s = (otc_stats *)calloc(1, sizeof *s);
    if (!s) return otc__fail(rel, OTC_E_NOMEM, "out of memory");
    for (i = 0; i < rel->n_st && st == OTC_OK; i++) {
        const otc__entry *e = &rel->st[i];
        st = otc__kv_add(&s->type, e->type_s, 1);
        if (st == OTC_OK) st = otc__kv_add(&s->kind, otc_kind_name(e->kind), 1);
        if (st == OTC_OK) st = otc__kv_add(&s->country, e->country, 1);
    }
    for (i = 0; i < rel->source_counts.n && st == OTC_OK; i++)
        st = otc__kv_add(&s->source, rel->source_counts.items[i].key, rel->source_counts.items[i].n);
    for (i = 0; i < rel->qc_counts.n && st == OTC_OK; i++)
        st = otc__kv_add(&s->qc_status, rel->qc_counts.items[i].key, rel->qc_counts.items[i].n);
    if (st != OTC_OK) { otc_stats_free(s); return otc__fail(rel, st, "out of memory"); }
    otc__kv_sort(&s->type);
    otc__kv_sort(&s->kind);
    otc__kv_sort(&s->country);
    otc__kv_sort(&s->source);
    otc__kv_sort(&s->qc_status);
    *out = s;
    return OTC_OK;
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
        return c ? otc__copy_str(otc__jstr(c->json, KEY), buf, len, needed) : OTC_E_INVALID_ARGUMENT; \
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
        return l ? otc__copy_str(otc__jstr(l->json, KEY), buf, len, needed) : OTC_E_INVALID_ARGUMENT; \
    }
LIC_STR(otc_licence_licence_id, "licence_id")
LIC_STR(otc_licence_spdx, "spdx")
LIC_STR(otc_licence_provider, "provider")
LIC_STR(otc_licence_citation, "citation")
LIC_STR(otc_licence_attribution, "attribution")
LIC_STR(otc_licence_url, "url")

otc_status otc_licence_raw_json(const otc_licence *l, char *buf, size_t len, size_t *needed)
{
    return l ? otc__copy_json(l->json, buf, len, needed) : OTC_E_INVALID_ARGUMENT;
}

/* ---------------------------------------------------------- release info */

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
