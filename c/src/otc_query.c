/* Station queries (SDK spec 4.4, 4.4.1, 6.3). Every query reads the index
 * built at open; only the stations returned are read from the file. */
#include "otc_internal.h"

#define OTC_EARTH_R_KM 6371.0088
#define OTC_DEG2RAD 0.017453292519943295

int otc__filter_match(const otc_filter *f, const otc__entry *e)
{
    if (!f) return 1;
    if (f->country && otc__strcmp_null(e->country, f->country) != 0) return 0;
    if (f->type && strcmp(e->type_s, f->type) != 0) return 0;
    if (f->kind) {
        const char *k = otc_kind_name(e->kind);
        if (!k || strcmp(k, f->kind) != 0) return 0;
    }
    if (f->source) {
        size_t i;
        int hit = 0;
        for (i = 0; i < e->n_sources; i++)
            if (!strcmp(e->sources[i], f->source)) hit = 1;
        if (!hit) return 0;
    }
    if (f->source_type && (!e->has_rec || otc__strcmp_null(e->rec_source_type, f->source_type) != 0)) return 0;
    return 1;
}

static int filter_ok(const otc_filter *f)
{
    return !f || f->struct_size >= sizeof *f;
}

/* ---------------------------------------------------------------- lookups */

static otc_status load_entry(const otc_release *rel, const otc__entry *e, otc_station_t **out)
{
    cJSON *root = NULL;
    otc_status st = otc__read_line(rel, e->offset, e->length, &root);
    if (st != OTC_OK) return st;
    st = otc__station_build(rel, root, e->kind, out);
    return st == OTC_OK ? st : otc__fail(rel, st, "cannot build station %s", e->id);
}

otc_status otc_station(const otc_release *rel, const char *id, otc_station_t **out)
{
    const otc__entry *e;
    if (out) *out = NULL;
    if (!rel || !out || !id) return otc__fail(rel, OTC_E_INVALID_ARGUMENT, "otc_station: NULL argument");
    e = otc__find_entry(rel, id);
    if (!e) return OTC_E_NOT_FOUND;
    return load_entry(rel, e, out);
}

otc_status otc_require_station(const otc_release *rel, const char *id, otc_station_t **out)
{
    otc_status st = otc_station(rel, id, out);
    if (st != OTC_E_NOT_FOUND) return st;
    if (otc__find_tomb(rel, id)) return otc__fail(rel, OTC_E_STATION_REMOVED, "station %s was removed", id);
    return otc__fail(rel, OTC_E_STATION_NOT_FOUND, "no station %s", id);
}

otc_status otc_tombstone(const otc_release *rel, const char *id, otc_tombstone_t **out)
{
    const otc__tomb *t;
    cJSON *root = NULL;
    otc_status st;
    if (out) *out = NULL;
    if (!rel || !out || !id) return otc__fail(rel, OTC_E_INVALID_ARGUMENT, "otc_tombstone: NULL argument");
    t = otc__find_tomb(rel, id);
    if (!t) return OTC_E_NOT_FOUND;
    st = otc__read_line(rel, t->offset, t->length, &root);
    if (st != OTC_OK) return st;
    *out = (otc_tombstone_t *)malloc(sizeof **out);
    if (!*out) { cJSON_Delete(root); return otc__fail(rel, OTC_E_NOMEM, "out of memory"); }
    (*out)->root = root;
    return OTC_OK;
}

void otc_tombstone_free(otc_tombstone_t *t)
{
    if (!t) return;
    cJSON_Delete(t->root);
    free(t);
}

otc_status otc_station_by_alias(const otc_release *rel, const char *system, const char *alias_id,
                                otc_station_t **out)
{
    size_t lo = 0, hi;
    if (out) *out = NULL;
    if (!rel || !out || !system || !alias_id)
        return otc__fail(rel, OTC_E_INVALID_ARGUMENT, "otc_station_by_alias: NULL argument");
    hi = rel->n_alias;
    while (lo < hi) {
        size_t mid = lo + (hi - lo) / 2;
        const otc__alias *a = &rel->alias[mid];
        int c = strcmp(a->system, system);
        if (!c) c = strcmp(a->alias, alias_id);
        if (!c) return otc_station(rel, a->station, out);
        if (c < 0) lo = mid + 1;
        else hi = mid;
    }
    return OTC_E_NOT_FOUND;
}

otc_status otc_stations(const otc_release *rel, const otc_filter *filter, const char **ids, size_t cap,
                        size_t *count)
{
    size_t i, n = 0;
    if (!rel || !count || (!ids && cap) || !filter_ok(filter))
        return otc__fail(rel, OTC_E_INVALID_ARGUMENT, "otc_stations: bad argument");
    for (i = 0; i < rel->n_st; i++) {
        if (!otc__filter_match(filter, &rel->st[i])) continue;
        if (ids && n < cap) ids[n] = rel->st[i].id;
        n++;
    }
    *count = n;
    if (!ids) return OTC_OK;
    return n > cap ? OTC_E_BUFFER_TOO_SMALL : OTC_OK;
}

/* -------------------------------------------------------------- iteration */

struct otc_iter {
    const otc_release *rel;
    otc_filter         filter;
    char              *strs[5];
    size_t             pos;
};

otc_status otc_iter_open(const otc_release *rel, const otc_filter *filter, otc_iter **out)
{
    otc_iter *it;
    if (out) *out = NULL;
    if (!rel || !out || !filter_ok(filter)) return otc__fail(rel, OTC_E_INVALID_ARGUMENT, "otc_iter_open: bad argument");
    it = (otc_iter *)calloc(1, sizeof *it);
    if (!it) return otc__fail(rel, OTC_E_NOMEM, "out of memory");
    it->rel = rel;
    otc_filter_init(&it->filter);
    if (filter) {
        /* copy the strings: the caller's filter need not outlive the call */
        it->filter.country = it->strs[0] = otc__strdup(filter->country);
        it->filter.type = it->strs[1] = otc__strdup(filter->type);
        it->filter.kind = it->strs[2] = otc__strdup(filter->kind);
        it->filter.source = it->strs[3] = otc__strdup(filter->source);
        it->filter.source_type = it->strs[4] = otc__strdup(filter->source_type);
        if ((filter->country && !it->strs[0]) || (filter->type && !it->strs[1]) || (filter->kind && !it->strs[2])
            || (filter->source && !it->strs[3]) || (filter->source_type && !it->strs[4])) {
            otc_iter_close(it);
            return otc__fail(rel, OTC_E_NOMEM, "out of memory");
        }
    }
    *out = it;
    return OTC_OK;
}

otc_status otc_iter_next(otc_iter *it, otc_station_t **out)
{
    if (out) *out = NULL;
    if (!it || !out) return OTC_E_INVALID_ARGUMENT;
    while (it->pos < it->rel->n_st) {
        const otc__entry *e = &it->rel->st[it->pos++];
        if (otc__filter_match(&it->filter, e)) return load_entry(it->rel, e, out);
    }
    return OTC_E_NOT_FOUND;
}

void otc_iter_close(otc_iter *it)
{
    size_t i;
    if (!it) return;
    for (i = 0; i < 5; i++) free(it->strs[i]);
    free(it);
}

/* ----------------------------------------------------------------- search */

typedef struct ranked {
    int               rank;
    const otc__entry *e;
} ranked;

static int ranked_cmp(const void *a, const void *b)
{
    const ranked *x = (const ranked *)a, *y = (const ranked *)b;
    int c;
    if (x->rank != y->rank) return x->rank < y->rank ? -1 : 1;
    c = strcmp(x->e->folded, y->e->folded);
    return c ? c : strcmp(x->e->id, y->e->id);
}

static int name_rank(const char *n, const char *q, int exact)
{
    size_t ql = strlen(q);
    const char *p;
    if (!strcmp(n, q)) return 0;
    if (exact) return -1;
    if (!strncmp(n, q, ql)) return 1;
    if (!n[0]) return -1;
    for (p = strstr(n + 1, q); p; p = strstr(p + 1, q))
        if (p[-1] == ' ') return 2;
    return strstr(n, q) ? 3 : -1;
}

otc_status otc_search(const otc_release *rel, const char *name, const otc_filter *filter, size_t limit,
                      otc_hit *out, size_t cap, size_t *count)
{
    char *q;
    ranked *r;
    size_t i, n = 0, total;
    if (!rel || !name || !count || (!out && cap) || !filter_ok(filter))
        return otc__fail(rel, OTC_E_INVALID_ARGUMENT, "otc_search: bad argument");
    q = otc__fold(name);
    if (!q) return otc__fail(rel, OTC_E_NOMEM, "out of memory");
    if (!q[0]) {
        free(q);
        return otc__fail(rel, OTC_E_INVALID_ARGUMENT, "the search query is empty");
    }
    r = (ranked *)malloc((rel->n_st ? rel->n_st : 1) * sizeof *r);
    if (!r) { free(q); return otc__fail(rel, OTC_E_NOMEM, "out of memory"); }
    for (i = 0; i < rel->n_st; i++) {
        int k;
        if (!otc__filter_match(filter, &rel->st[i])) continue;
        k = name_rank(rel->st[i].folded, q, filter && filter->match_exact);
        if (k < 0) continue;
        r[n].rank = k;
        r[n].e = &rel->st[i];
        n++;
    }
    free(q);
    if (n > 1) qsort(r, n, sizeof *r, ranked_cmp);
    total = (limit && limit < n) ? limit : n;
    for (i = 0; out && i < total && i < cap; i++) {
        out[i].id = r[i].e->id;
        out[i].name = r[i].e->name;
    }
    free(r);
    *count = total;
    if (!out) return OTC_OK;
    return total > cap ? OTC_E_BUFFER_TOO_SMALL : OTC_OK;
}

/* -------------------------------------------------------------------- geo */

static double haversine(double lat1, double lon1, double lat2, double lon2)
{
    double p1 = lat1 * OTC_DEG2RAD, p2 = lat2 * OTC_DEG2RAD;
    double dp = p2 - p1, dl = (lon2 - lon1) * OTC_DEG2RAD;
    double a = sin(dp / 2) * sin(dp / 2) + cos(p1) * cos(p2) * sin(dl / 2) * sin(dl / 2);
    double s = sqrt(a);
    return 2 * OTC_EARTH_R_KM * asin(s < 1.0 ? s : 1.0);
}

static int bad_point(double lat, double lon)
{
    return !(lat >= -90.0 && lat <= 90.0) || !(lon >= -180.0 && lon <= 180.0);
}

static int nearby_cmp(const void *a, const void *b)
{
    const otc_nearby *x = (const otc_nearby *)a, *y = (const otc_nearby *)b;
    if (x->distance_km != y->distance_km) return x->distance_km < y->distance_km ? -1 : 1;
    return strcmp(x->id, y->id);
}

/* All stations within max_km (infinite: all), sorted by distance then id. */
static otc_status geo_scan(const otc_release *rel, double lat, double lon, double max_km, const otc_filter *f,
                           otc_nearby **out, size_t *n_out)
{
    otc_nearby *hits = (otc_nearby *)malloc((rel->n_st ? rel->n_st : 1) * sizeof *hits);
    /* latitude prefilter (spec 6.3): the distance is at least R * |dlat| */
    double band = isinf(max_km) ? 1000.0 : max_km / (OTC_EARTH_R_KM * OTC_DEG2RAD) + 1e-9;
    size_t i, n = 0;
    if (!hits) return OTC_E_NOMEM;
    for (i = 0; i < rel->n_st; i++) {
        const otc__entry *e = &rel->st[i];
        double d;
        if (fabs(e->lat - lat) > band) continue;
        if (!otc__filter_match(f, e)) continue;
        d = haversine(lat, lon, e->lat, e->lon);
        if (d > max_km) continue;
        hits[n].id = e->id;
        hits[n].distance_km = d;
        n++;
    }
    if (n > 1) qsort(hits, n, sizeof *hits, nearby_cmp);
    *out = hits;
    *n_out = n;
    return OTC_OK;
}

otc_status otc_near(const otc_release *rel, double lat, double lon, double radius_km, const otc_filter *filter,
                    size_t limit, otc_nearby *out, size_t cap, size_t *count)
{
    otc_nearby *hits = NULL;
    size_t n = 0, total, i;
    otc_status st;
    if (!rel || !count || (!out && cap) || !filter_ok(filter))
        return otc__fail(rel, OTC_E_INVALID_ARGUMENT, "otc_near: bad argument");
    if (bad_point(lat, lon)) return otc__fail(rel, OTC_E_INVALID_ARGUMENT, "lat or lon out of range");
    if (!(radius_km >= 0)) return otc__fail(rel, OTC_E_INVALID_ARGUMENT, "radius_km must be >= 0");
    st = geo_scan(rel, lat, lon, radius_km, filter, &hits, &n);
    if (st != OTC_OK) return otc__fail(rel, st, "out of memory");
    total = (limit && limit < n) ? limit : n;
    for (i = 0; out && i < total && i < cap; i++) out[i] = hits[i];
    free(hits);
    *count = total;
    if (!out) return OTC_OK;
    return total > cap ? OTC_E_BUFFER_TOO_SMALL : OTC_OK;
}

otc_status otc_nearest(const otc_release *rel, double lat, double lon, double max_km, const otc_filter *filter,
                       otc_nearby *hit)
{
    otc_nearby *hits = NULL;
    size_t n = 0;
    otc_status st;
    if (!rel || !hit || !filter_ok(filter)) return otc__fail(rel, OTC_E_INVALID_ARGUMENT, "otc_nearest: bad argument");
    if (bad_point(lat, lon)) return otc__fail(rel, OTC_E_INVALID_ARGUMENT, "lat or lon out of range");
    if (isnan(max_km)) max_km = INFINITY;
    if (max_km < 0) return otc__fail(rel, OTC_E_INVALID_ARGUMENT, "max_km must be >= 0");
    st = geo_scan(rel, lat, lon, max_km, filter, &hits, &n);
    if (st != OTC_OK) return otc__fail(rel, st, "out of memory");
    if (n == 0) {
        free(hits);
        return OTC_E_NOT_FOUND;
    }
    *hit = hits[0];
    free(hits);
    return OTC_OK;
}

/* ------------------------------------------------------------------ links */

otc_status otc_reference_station(const otc_release *rel, const otc_station_t *st, otc_station_t **out)
{
    const cJSON *off;
    const char *ref;
    if (out) *out = NULL;
    if (!rel || !st || !out) return otc__fail(rel, OTC_E_INVALID_ARGUMENT, "otc_reference_station: NULL argument");
    if (otc_station_type(st) != OTC_STATION_TYPE_SUBORDINATE) return OTC_E_NOT_FOUND;
    off = otc__jget(st->root, "subordinate_offsets");
    ref = otc__jstr(off, "reference_station_id");
    if (!ref) return OTC_E_NOT_FOUND;
    return otc_station(rel, ref, out);
}

otc_status otc_subordinates_of(const otc_release *rel, const otc_station_t *st, const char **ids, size_t cap,
                               size_t *count)
{
    const char *id;
    size_t i, n = 0;
    if (!rel || !st || !count || (!ids && cap))
        return otc__fail(rel, OTC_E_INVALID_ARGUMENT, "otc_subordinates_of: bad argument");
    id = otc__jstr(st->root, "station_id");
    for (i = 0; i < rel->n_st; i++) {
        const otc__entry *e = &rel->st[i];
        if (e->type != OTC_STATION_TYPE_SUBORDINATE || !e->has_offsets || otc__strcmp_null(e->ref_id, id) != 0)
            continue;
        if (ids && n < cap) ids[n] = e->id;
        n++;
    }
    *count = n;
    if (!ids) return OTC_OK;
    return n > cap ? OTC_E_BUFFER_TOO_SMALL : OTC_OK;
}
