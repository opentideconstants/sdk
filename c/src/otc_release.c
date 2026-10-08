/* Opening a release (.jsonl + .meta.json), the stream index, release
 * metadata, conventions, licences, stats, citation and attribution
 * (SDK spec 4.2, 4.3, 4.6, 5.3, 6.2, 6.4, 7.3, 7.4). */
#include "otc_internal.h"

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
    *out = NULL;
    if (!buf) return OTC_E_NOMEM;
    if (otc__file_pread(rel->file, buf, length, offset) != 0) {
        free(buf);
        return otc__fail(rel, OTC_E_IO, "cannot read %s at offset %lu", rel->path, (unsigned long)offset);
    }
    buf[length] = '\0';
    v = otc__json_parse(buf, length);
    free(buf);
    if (!v) return otc__fail(rel, OTC_E_INVALID_RELEASE, "a line of %s is not JSON (it changed after open?)", rel->path);
    *out = v;
    return OTC_OK;
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
    /* the reference ids, to resolve kind after the pass */
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

static otc_status add_cname(builder *b, const char *name)
{
    otc_release *r = b->rel;
    size_t i;
    for (i = 0; i < r->n_cnames; i++)
        if (!strcmp(r->cnames[i], name)) return OTC_OK;
    GROW(r->cnames, r->n_cnames, b->cap_cn);
    r->cnames[r->n_cnames] = otc__strdup(name);
    if (!r->cnames[r->n_cnames]) return OTC_E_NOMEM;
    r->n_cnames++;
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

static int fits(const char *s, size_t cap)
{
    return !s || strlen(s) < cap;
}

/* Checks one constant set and adds what the index needs from it. */
static otc_status index_set(builder *b, const cJSON *set, otc__entry *e, const char *rec_id)
{
    otc_release *r = b->rel;
    const char *set_id = otc__jstr(set, "set_id"), *source = otc__jstr(set, "source");
    const char *qc = otc__jstr(set, "qc_status");
    const char *conv = otc__jstr(set, "convention_id"), *lic = otc__jstr(set, "licence_id");
    const cJSON *cons = otc__jget(set, "constituents"), *c;
    otc_status st;
    if (!cJSON_IsObject(set) || !set_id || !source || !qc) return bad_line(b, "a constant set lacks set_id, source or qc_status");
    if (!otc__find_convention(r, conv)) return bad_line(b, "a constant set's convention_id does not resolve");
    if (!otc__find_licence(r, lic)) return bad_line(b, "a constant set's licence_id does not resolve");
    if (cons && !cJSON_IsArray(cons)) return bad_line(b, "constituents is not an array");
    cJSON_ArrayForEach(c, cons) {
        const char *name = otc__jstr(c, "name");
        if (!name) return bad_line(b, "a constituent has no name");
        if (!fits(name, 16) || !fits(otc__jstr(c, "source_name"), 32) || !fits(otc__jstr(c, "doodson"), 8)
            || !fits(otc__jstr(c, "kept_reason"), 32))
            return bad_line(b, "a constituent string is longer than its schema maxLength");
        if ((st = add_cname(b, name)) != OTC_OK) return st;
    }
    if ((st = otc__kv_add(&r->source_counts, source, 1)) != OTC_OK) return st;
    if ((st = otc__kv_add(&r->qc_counts, qc, 1)) != OTC_OK) return st;
    if (strcmp(qc, "excluded") != 0) {
        size_t i;
        int seen = 0;
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

/* Indexes one parsed station line (root is not freed here). */
static otc_status index_parsed(builder *b, const cJSON *root, size_t len, uint64_t offset)
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
        e->name = otc__strdup(name);
        e->folded = otc__fold(name);
        e->country = otc__strdup(otc__jstr(root, "country"));
        if (!e->id || !e->name || !e->folded || !e->type_s || (otc__jstr(root, "country") && !e->country))
            return OTC_E_NOMEM;
        if (cJSON_IsObject(off)) {
            e->has_offsets = 1;
            e->ref_id = otc__strdup(otc__jstr(off, "reference_station_id"));
            e->off_licence = otc__strdup(otc__jstr(off, "licence_id"));
        }
        cJSON_ArrayForEach(s, sets) {
            if ((st = index_set(b, s, e, rec_id)) != OTC_OK) break;
        }
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
    cJSON *root = otc__json_parse(line, len);
    otc_status st;
    if (!root) return bad_line(b, "not JSON");
    if (!cJSON_IsObject(root)) {
        cJSON_Delete(root);
        return bad_line(b, "not a station object with station_id and status");
    }
    st = index_parsed(b, root, len, offset);
    cJSON_Delete(root);
    return st;
}

/* Calls fn for every line of the file that is not empty, with its offset and
 * its length without the line end (\n, or \r\n). *line_no counts every line. */
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
                if (len > 0) st = fn(ctx, line, len, line_start);
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
        if (n > 0) st = fn(ctx, line, n, line_start);
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

static void dup_if_set(cJSON *to, const cJSON *from, const char *key, const char *as)
{
    const cJSON *v = otc__jget(from, key);
    if (v && !cJSON_IsNull(v)) cJSON_AddItemToObject(to, as, cJSON_Duplicate(v, 1));
}

/* The station document the index pass needs, from an index entry. */
static cJSON *line_from_entry(const cJSON *e)
{
    static const char *const keys[] = {"station_id", "status", "name", "country", "type", "lat", "lon",
                                       "recommended_set_id", "aliases", NULL};
    cJSON *o = cJSON_CreateObject(), *sets = cJSON_CreateArray();
    const cJSON *cs;
    size_t i;
    if (!o || !sets) { cJSON_Delete(o); cJSON_Delete(sets); return NULL; }
    for (i = 0; keys[i]; i++) dup_if_set(o, e, keys[i], keys[i]);
    cJSON_ArrayForEach(cs, otc__jget(e, "sets")) {
        cJSON *s = cJSON_CreateObject(), *cons = cJSON_CreateArray();
        const cJSON *n;
        size_t k;
        for (k = 0; SET_KEYS[k]; k++) dup_if_set(s, cs, SET_KEYS[k], SET_KEYS[k]);
        cJSON_ArrayForEach(n, otc__jget(cs, "constituents")) {
            cJSON *c = cJSON_CreateObject();
            cJSON_AddStringToObject(c, "name", n->valuestring);
            cJSON_AddItemToArray(cons, c);
        }
        cJSON_AddItemToObject(s, "constituents", cons);
        cJSON_AddItemToArray(sets, s);
    }
    cJSON_AddItemToObject(o, "constant_sets", sets);
    if (otc__jstr(e, "reference_station_id") || otc__jstr(e, "offsets_licence_id")) {
        cJSON *off = cJSON_CreateObject();
        dup_if_set(off, e, "reference_station_id", "reference_station_id");
        dup_if_set(off, e, "offsets_licence_id", "licence_id");
        cJSON_AddItemToObject(o, "subordinate_offsets", off);
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
    doc = otc__json_parse(text, len);
    v = otc__jget(doc, "index_version");
    if (!cJSON_IsObject(doc) || !cJSON_IsNumber(v) || v->valuedouble != 1.0) goto done;
    if (otc__strcmp_null(otc__jstr(doc, "datestamp"), ds) || otc__strcmp_null(otc__jstr(doc, "jsonl"), jsonl_name)
        || otc__strcmp_null(otc__jstr(doc, "jsonl_sha256"), sha))
        goto done;
    v = otc__jget(doc, "jsonl_size");
    if (!cJSON_IsNumber(v) || v->valuedouble != (double)size || !cJSON_IsArray(otc__jget(doc, "stations"))) goto done;
    cJSON_ArrayForEach(e, otc__jget(doc, "stations")) if (!entry_ok(e, size)) goto done;
    st = OTC_OK;
    cJSON_ArrayForEach(e, otc__jget(doc, "stations")) {
        cJSON *line = line_from_entry(e);
        if (!line) { st = OTC_E_NOMEM; break; }
        b->line_no++;
        st = index_parsed(b, line, (size_t)otc__jget(e, "length")->valuedouble,
                          (uint64_t)otc__jget(e, "offset")->valuedouble);
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

/* One entry of index-v1.json, from its line (spec 6.2). */
static otc_status stored_entry_cb(void *ctx, const char *text, size_t len, uint64_t offset)
{
    ix_ctx *x = (ix_ctx *)ctx;
    cJSON *d = otc__json_parse(text, len), *o, *sets, *al;
    const cJSON *offs, *cs, *a, *v;
    const char *rec, *name, *kind = NULL;
    char *folded;
    if (!d) return OTC_E_INVALID_RELEASE;
    o = cJSON_CreateObject();
    sets = cJSON_CreateArray();
    al = cJSON_CreateObject();
    offs = otc__jget(d, "subordinate_offsets");
    if (!cJSON_IsObject(offs)) offs = NULL;
    rec = otc__jstr(d, "recommended_set_id");
    name = otc__jstr(d, "name");
    folded = name ? otc__fold(name) : NULL;
    cJSON_AddNumberToObject(o, "offset", (double)offset);
    cJSON_AddNumberToObject(o, "length", (double)len);
    cJSON_AddItemToObject(o, "station_id", jstr_or_null(d, "station_id"));
    cJSON_AddItemToObject(o, "status", jstr_or_null(d, "status"));
    cJSON_AddItemToObject(o, "name", jstr_or_null(d, "name"));
    cJSON_AddItemToObject(o, "name_folded", folded ? cJSON_CreateString(folded) : cJSON_CreateNull());
    free(folded);
    cJSON_AddItemToObject(o, "country", jstr_or_null(d, "country"));
    cJSON_AddItemToObject(o, "type", jstr_or_null(d, "type"));
    v = otc__jget(d, "lat");
    cJSON_AddItemToObject(o, "lat", cJSON_IsNumber(v) ? cJSON_CreateNumber(v->valuedouble) : cJSON_CreateNull());
    v = otc__jget(d, "lon");
    cJSON_AddItemToObject(o, "lon", cJSON_IsNumber(v) ? cJSON_CreateNumber(v->valuedouble) : cJSON_CreateNull());
    cJSON_ArrayForEach(cs, otc__jget(d, "constant_sets")) {
        cJSON *s = cJSON_CreateObject(), *cons = cJSON_CreateArray();
        const cJSON *c;
        size_t k;
        for (k = 0; SET_KEYS[k]; k++) cJSON_AddItemToObject(s, SET_KEYS[k], jstr_or_null(cs, SET_KEYS[k]));
        cJSON_ArrayForEach(c, otc__jget(cs, "constituents"))
            if (otc__jstr(c, "name")) cJSON_AddItemToArray(cons, cJSON_CreateString(otc__jstr(c, "name")));
        cJSON_AddItemToObject(s, "constituents", cons);
        cJSON_AddItemToArray(sets, s);
        if (rec && !otc__strcmp_null(otc__jstr(cs, "set_id"), rec)) {
            const char *q = otc__jstr(cs, "quantity");
            kind = q && !strcmp(q, "water_level") ? "tide" : q && !strcmp(q, "current") ? "current" : "other";
        }
    }
    if (otc__jstr(d, "status") && !strcmp(otc__jstr(d, "status"), "active") && otc__jstr(d, "station_id")) {
        const otc__entry *e = otc__find_entry(x->rel, otc__jstr(d, "station_id"));
        if (e) kind = e->kind == OTC_KIND_UNSET ? NULL : otc_kind_name(e->kind);
    }
    cJSON_AddItemToObject(o, "kind", kind ? cJSON_CreateString(kind) : cJSON_CreateNull());
    cJSON_ArrayForEach(a, otc__jget(d, "aliases")) {
        cJSON *list = cJSON_CreateArray();
        const cJSON *id;
        if (cJSON_IsString(a)) cJSON_AddItemToArray(list, cJSON_CreateString(a->valuestring));
        else cJSON_ArrayForEach(id, a) if (cJSON_IsString(id)) cJSON_AddItemToArray(list, cJSON_CreateString(id->valuestring));
        cJSON_AddItemToObject(al, a->string, list);
    }
    cJSON_AddItemToObject(o, "aliases", al);
    cJSON_AddItemToObject(o, "reference_station_id", jstr_or_null(offs, "reference_station_id"));
    cJSON_AddItemToObject(o, "offsets_licence_id", jstr_or_null(offs, "licence_id"));
    cJSON_AddItemToObject(o, "recommended_set_id", jstr_or_null(d, "recommended_set_id"));
    cJSON_AddItemToObject(o, "sets", sets);
    cJSON_AddItemToArray(x->arr, o);
    cJSON_Delete(d);
    return OTC_OK;
}

cJSON *otc__index_doc(const otc_release *rel, const char *jsonl_sha256, const char *by)
{
    cJSON *doc, *arr;
    const char *ds;
    char jsonl[80];
    size_t line_no = 0;
    ix_ctx x;
    if (!rel || !rel->file || !jsonl_sha256) return NULL;
    ds = otc__jstr(rel->release_obj, "datestamp");
    doc = cJSON_CreateObject();
    arr = cJSON_CreateArray();
    if (!doc || !arr || !ds) { cJSON_Delete(doc); cJSON_Delete(arr); return NULL; }
    x.rel = rel;
    x.arr = arr;
    x.st = OTC_OK;
    if (scan_lines(rel->file, &line_no, stored_entry_cb, &x) != OTC_OK) {
        cJSON_Delete(doc);
        cJSON_Delete(arr);
        return NULL;
    }
    snprintf(jsonl, sizeof jsonl, "OTC_%s.jsonl", ds);
    cJSON_AddNumberToObject(doc, "index_version", 1);
    cJSON_AddStringToObject(doc, "datestamp", ds);
    cJSON_AddStringToObject(doc, "jsonl", jsonl);
    cJSON_AddStringToObject(doc, "jsonl_sha256", jsonl_sha256);
    cJSON_AddNumberToObject(doc, "jsonl_size", (double)otc__file_size(rel->file));
    cJSON_AddStringToObject(doc, "by", by);
    cJSON_AddItemToObject(doc, "stations", arr);
    return doc;
}

static otc_kind resolve_kind(const otc_release *r, const otc__entry *e, size_t depth)
{
    if (e->has_rec) {
        if (e->rec_quantity == OTC_QUANTITY_WATER_LEVEL) return OTC_KIND_TIDE;
        if (e->rec_quantity == OTC_QUANTITY_CURRENT) return OTC_KIND_CURRENT;
        return OTC_KIND_OTHER;
    }
    if (e->type == OTC_STATION_TYPE_SUBORDINATE && e->has_offsets && depth < 16) {
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
static otc_status load_meta(otc_release *r, const char *meta_path, otc_error *err)
{
    char *text = NULL;
    size_t len = 0;
    const char *fv, *dot;
    const cJSON *convs, *lics, *c;
    long major;
    char *end;
    size_t i;
    otc_status st = otc__read_all(meta_path, &text, &len);
    if (st != OTC_OK) {
        otc__err_set(err, st, meta_path, "cannot read %s", meta_path);
        return st;
    }
    r->meta = otc__json_parse(text, len);
    free(text);
    if (!r->meta || !cJSON_IsObject(r->meta)) {
        otc__err_set(err, OTC_E_INVALID_RELEASE, meta_path, "%s is not a JSON object", meta_path);
        return OTC_E_INVALID_RELEASE;
    }
    fv = otc__jstr(r->meta, "format_version");
    if (!fv) {
        otc__err_set(err, OTC_E_INVALID_RELEASE, meta_path, "%s has no format_version", meta_path);
        return OTC_E_INVALID_RELEASE;
    }
    major = strtol(fv, &end, 10);
    dot = strchr(fv, '.');
    if (end == fv || !dot || end != dot) {
        otc__err_set(err, OTC_E_INVALID_RELEASE, meta_path, "format_version %s is not MAJOR.MINOR", fv);
        return OTC_E_INVALID_RELEASE;
    }
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
        r->files[i].name = otc__strdup(name);
        r->files[i].sha256 = n_rows ? otc__strdup(digests[i]) : NULL;
        r->files[i].size = full ? otc__path_size(full) : -1;
        free(full);
        if (!r->files[i].name || (n_rows && !r->files[i].sha256)) return OTC_E_NOMEM;
    }
    qsort(r->files, n, sizeof *r->files, file_cmp);
    return OTC_OK;
}

static otc_status check_digest(const char *path, const char *name, char **names, char **digests, size_t n,
                               otc_error *err)
{
    char hex[65];
    const char *expected = NULL;
    size_t i;
    otc_status st;
    for (i = 0; i < n; i++)
        if (!strcmp(names[i], name)) expected = digests[i];
    st = otc__sha256_file(path, hex);
    if (st != OTC_OK) {
        otc__err_set(err, st, path, "cannot read %s", path);
        return st;
    }
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
    char *base = NULL, *meta_path = NULL, *sha_path = NULL, *dir = NULL;
    char **names = NULL, **digests = NULL;
    size_t n_rows = 0, i;
    const char *jsonl_name = path_base(path);
    otc_status st;
    builder b;

    if (otc__path_size(path) < 0) {
        otc__err_set(err, OTC_E_IO, path, "cannot open %s", path);
        return OTC_E_IO;
    }
    if (!otc__ends_with(path, ".jsonl")) {
        otc__err_set(err, OTC_E_INVALID_ARGUMENT, path, "the C library opens OTC_{D}.jsonl files: %s", path);
        return OTC_E_INVALID_ARGUMENT;
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
    /* checksums first (spec 5.3): a corrupt or truncated file is checksum_mismatch */
    if (otc__path_size(sha_path) >= 0) {
        st = otc__sha256_rows(sha_path, &names, &digests, &n_rows);
        if (st != OTC_OK) { otc__err_set(err, st, sha_path, "cannot read %s", sha_path); goto done; }
        if ((st = check_digest(path, jsonl_name, names, digests, n_rows, err)) != OTC_OK) goto done;
        if ((st = check_digest(meta_path, path_base(meta_path), names, digests, n_rows, err)) != OTC_OK) goto done;
        r->loaded_from = OTC_LOADED_FROM_FILE;
    } else if (opts && opts->require_checksum) {
        otc__err_set(err, OTC_E_IO, sha_path, "require_checksum: %s does not exist", sha_path);
        st = OTC_E_IO;
        goto done;
    } else {
        r->loaded_from = OTC_LOADED_FROM_FILE_UNVERIFIED;
    }
    if ((st = load_meta(r, meta_path, err)) != OTC_OK) goto done;

    st = otc__file_open(path, &r->file);
    if (st != OTC_OK) { otc__err_set(err, st, path, "cannot open %s", path); goto done; }
    memset(&b, 0, sizeof b);
    b.rel = r;
    b.err = err;
    st = OTC_E_NOT_FOUND;
    /* a fresh index-v1.json next to a checked .jsonl saves the pass (spec 6.2) */
    if (use_index && n_rows > 0) {
        const char *sha = NULL;
        for (i = 0; i < n_rows; i++)
            if (!strcmp(names[i], jsonl_name)) sha = digests[i];
        st = index_from_file(&b, dir, jsonl_name, sha, otc__path_size(path));
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
    if (r->n_cnames > 1) qsort(r->cnames, r->n_cnames, sizeof *r->cnames, cname_cmp);
    for (i = 0; i < r->n_st; i++) r->st[i].kind = resolve_kind(r, &r->st[i], 0);
    otc__kv_sort(&r->source_counts);
    otc__kv_sort(&r->qc_counts);
    st = build_files(r, dir, names, digests, n_rows, jsonl_name, path_base(meta_path));
done:
    otc__free_rows(names, digests, n_rows);
    free(base);
    free(dir);
    free(meta_path);
    free(sha_path);
    if (st == OTC_E_NOMEM) otc__err_set(err, st, path, "out of memory");
    return st;
}

otc_status otc_open_file(const char *path, const otc_open_options *opts, otc_release **out)
{
    otc_error *err = (opts && opts->struct_size >= sizeof *opts) ? opts->error : NULL;
    otc_release *r;
    otc_status st;
    if (err) otc_error_init(err);
    if (!out || !path) {
        otc__err_set(err, OTC_E_INVALID_ARGUMENT, NULL, "path and out must not be NULL");
        return OTC_E_INVALID_ARGUMENT;
    }
    *out = NULL;
    if (opts && opts->struct_size < sizeof *opts) {
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
        if (err) otc_error_init(err);
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
REL_STR(otc_release_created, otc__jstr(rel->release_obj, "created"))
REL_STR(otc_release_format_version, otc__jstr(rel->meta, "format_version"))
REL_STR(otc_release_doi, otc__jstr(rel->release_obj, "doi"))
REL_STR(otc_release_concept_doi, otc__jstr(rel->release_obj, "concept_doi"))
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

/* Spec 4.6: "OpenTideConstants contributors ({year}). OpenTideConstants, release {D} [Data set]. {link}",
 * where {year} is the first four digits of the datestamp and {link} is https://doi.org/{doi}, or the
 * release URL when the DOI is null. */
otc_status otc_release_citation(const otc_release *rel, char *buf, size_t len, size_t *needed)
{
    const char *d, *doi;
    char text[1024];
    if (!rel) return OTC_E_INVALID_ARGUMENT;
    d = otc__jstr(rel->release_obj, "datestamp");
    doi = otc__jstr(rel->release_obj, "doi");
    if (doi)
        snprintf(text, sizeof text, "OpenTideConstants contributors (%.4s). OpenTideConstants, release %s [Data set]. "
                 "https://doi.org/%s", d, d, doi);
    else
        snprintf(text, sizeof text, "OpenTideConstants contributors (%.4s). OpenTideConstants, release %s [Data set]. "
                 "https://data.opentideconstants.org/OTC_%s.json", d, d, d);
    return otc__copy_str(text, buf, len, needed);
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
    char head[512], *text;
    otc_status st;
    if (!rel || (n_ids && !ids)) return OTC_E_INVALID_ARGUMENT;
    cap = ids ? n_ids * 3 + 1 : rel->n_lic + 1;
    lic = (const char **)calloc(cap, sizeof *lic);
    seen_prov = (const char **)calloc(cap, sizeof *seen_prov);
    seen_att = (const char **)calloc(cap, sizeof *seen_att);
    if (!lic || !seen_prov || !seen_att) {
        free((void *)lic); free((void *)seen_prov); free((void *)seen_att);
        return OTC_E_NOMEM;
    }
    if (!ids) {
        for (i = 0; i < rel->n_lic; i++) lic[n_lic++] = rel->lic[i].id;
    } else {
        for (i = 0; i < n_ids; i++) {
            const otc__entry *e = otc__find_entry(rel, ids[i]);
            if (!e) continue;
            if (e->has_rec && e->rec_licence) lic[n_lic++] = e->rec_licence;
            if (e->type == OTC_STATION_TYPE_SUBORDINATE && e->has_offsets) {
                const otc__entry *ref = otc__find_entry(rel, e->ref_id);
                if (e->off_licence) lic[n_lic++] = e->off_licence;
                if (ref && ref->has_rec && ref->rec_licence) lic[n_lic++] = ref->rec_licence;
            }
        }
    }
    if (n_lic > 1) qsort((void *)lic, n_lic, sizeof *lic, str_ptr_cmp);
    d = otc__jstr(rel->release_obj, "datestamp");
    doi = otc__jstr(rel->release_obj, "doi");
    if (doi) snprintf(head, sizeof head, "Tidal constants: OpenTideConstants %s, doi:%s, CC BY 4.0. Sources: ", d, doi);
    else snprintf(head, sizeof head, "Tidal constants: OpenTideConstants %s, https://data.opentideconstants.org/OTC_%s.json, CC BY 4.0. Sources: ", d, d);
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
        for (j = 0; j < n_seen; j++)
            if (!otc__strcmp_null(seen_prov[j], prov)) dup = 1;
        if (dup) continue;
        seen_prov[n_seen] = prov;
        seen_att[n_seen++] = att;
        total += (prov ? strlen(prov) : 0) + 2 + (att ? strlen(att) : 0) + 2;
    }
    text = (char *)malloc(total);
    if (!text) { free((void *)lic); free((void *)seen_prov); free((void *)seen_att); return OTC_E_NOMEM; }
    strcpy(text, head);
    for (i = 0; i < n_seen; i++) {
        if (i) strcat(text, "; ");
        strcat(text, seen_prov[i] ? seen_prov[i] : "");
        strcat(text, ": ");
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
    if (!rel || !out) return OTC_E_INVALID_ARGUMENT;
    *out = NULL;
    s = (otc_stats *)calloc(1, sizeof *s);
    if (!s) return OTC_E_NOMEM;
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
    if (st != OTC_OK) { otc_stats_free(s); return st; }
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
    if (!rel || !out || i >= rel->n_conv) return OTC_E_INVALID_ARGUMENT;
    *out = &rel->conv[i];
    return OTC_OK;
}

otc_status otc_release_convention(const otc_release *rel, const char *id, const otc_convention **out)
{
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
    if (!rel || !out || i >= rel->n_lic) return OTC_E_INVALID_ARGUMENT;
    *out = &rel->lic[i];
    return OTC_OK;
}

otc_status otc_release_licence(const otc_release *rel, const char *id, const otc_licence **out)
{
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
    free(ri->doi);
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
otc_status otc_release_info_doi(const otc_release_info *ri, char *buf, size_t len, size_t *needed)
{
    return ri ? otc__copy_str(ri->doi, buf, len, needed) : OTC_E_INVALID_ARGUMENT;
}
size_t otc_release_info_file_count(const otc_release_info *ri) { return ri ? ri->n_files : 0; }
otc_status otc_release_info_file_at(const otc_release_info *ri, size_t i, const otc_file_info **out)
{
    if (!ri || !out || i >= ri->n_files) return OTC_E_INVALID_ARGUMENT;
    *out = &ri->files[i];
    return OTC_OK;
}
