/* PK-R2-23 (R2-255): a failed call leaves no value from an earlier call in its
 * output (header: "an output pointer then stays NULL"). Each output starts as
 * a stale, non-NULL value; after a call that fails (INVALID_ARGUMENT for an
 * index past the end or a NULL argument, NOT_FOUND for no value) it is NULL
 * (otc_nearest: hit->id NULL and distance_km NaN). Also: otc_set_constituent
 * with "" finds nothing, even when a constituent's name is "" (in a
 * constituent_t, "" means absent: it is no name to look up). */
#include "otc_test.h"

#include <math.h>

#define ST1 "{\"station_id\":\"OTC-X-1\",\"status\":\"active\",\"name\":\"One\",\"lat\":1,\"lon\":1,\"type\":\"reference\"," \
    "\"recommended_set_id\":\"s\",\"constant_sets\":[{\"set_id\":\"s\",\"source\":\"x\",\"quantity\":\"water_level\"," \
    "\"qc_status\":\"ok\",\"convention_id\":\"c1\",\"licence_id\":\"l1\",\"constituents\":[{\"name\":\"M2\"},{\"name\":\"\",\"amplitude_m\":1}]," \
    "\"qc_flags\":[{\"flag\":\"short_record\"}],\"dropped_constituents\":[{\"name\":\"K2\"}],\"time_base\":{\"code\":\"verified\"," \
    "\"evidence\":[{\"comparator_kind\":\"x\"}]}}],\"validation\":[{\"set_id\":\"s\",\"window\":\"w\"}]}"

static int g_stale_obj;
#define STALE ((const void *)&g_stale_obj)

int main(void)
{
    char *dir = test_tmpdir(), *path;
    otc_release *rel = NULL;
    otc_station_t *st = NULL;
    const otc_set *set = NULL, *so;
    const otc_constituent_t *co;
    const otc_validation_t *vo;
    const otc_qc_flag *fo;
    const otc_dropped *dro;
    const otc_time_base_t *tb = NULL;
    const otc_time_base_evidence *eo;
    const otc_file_info *fio;
    const otc_convention *cvo;
    const otc_licence *lo;
    otc_stats *stats = NULL;
    const char *key;
    int64_t n;
    otc_nearby hit;
    otc_open_options oo;
    otc_error err;

    test_write(dir, "OTC_20990101.meta.json", TEST_META("20990101"));
    test_write(dir, "OTC_20990101.jsonl", ST1 "\n");
    path = test_join(dir, "OTC_20990101.jsonl");
    otc_open_options_init(&oo);
    otc_error_init(&err);
    oo.error = &err;
    if (otc_open_file(path, &oo, &rel) != OTC_OK) {
        fprintf(stderr, "test_outputs_cleared: the open gave %s (%s)\n", otc_status_code(err.status), err.message);
        return 2;
    }
    CHECK_STATUS(otc_station(rel, "OTC-X-1", &st), OTC_OK);
    if (!st) return 2;
    CHECK_STATUS(otc_station_recommended_set(st, &set), OTC_OK);
    if (!set) return 2;

    /* the station's sets */
    so = STALE;
    CHECK_STATUS(otc_station_set_at(st, true, 99, &so), OTC_E_INVALID_ARGUMENT);
    CHECK(so == NULL);
    so = STALE;
    CHECK_STATUS(otc_station_set(st, NULL, &so), OTC_E_INVALID_ARGUMENT);
    CHECK(so == NULL);
    so = STALE;
    CHECK_STATUS(otc_station_set(st, "nope", &so), OTC_E_NOT_FOUND);
    CHECK(so == NULL);
    vo = STALE;
    CHECK_STATUS(otc_station_validation_at(st, 99, &vo), OTC_E_INVALID_ARGUMENT);
    CHECK(vo == NULL);

    /* a set's rows */
    vo = STALE;
    CHECK_STATUS(otc_set_validation_at(set, 99, &vo), OTC_E_INVALID_ARGUMENT);
    CHECK(vo == NULL);
    co = STALE;
    CHECK_STATUS(otc_set_constituent_at(set, 99, &co), OTC_E_INVALID_ARGUMENT);
    CHECK(co == NULL);
    co = STALE;
    CHECK_STATUS(otc_set_constituent(set, NULL, &co), OTC_E_INVALID_ARGUMENT);
    CHECK(co == NULL);
    fo = STALE;
    CHECK_STATUS(otc_set_qc_flag_at(set, 99, &fo), OTC_E_INVALID_ARGUMENT);
    CHECK(fo == NULL);
    dro = STALE;
    CHECK_STATUS(otc_set_dropped_at(set, 99, &dro), OTC_E_INVALID_ARGUMENT);
    CHECK(dro == NULL);
    CHECK_STATUS(otc_set_time_base(set, &tb), OTC_OK);
    if (tb) {
        eo = STALE;
        CHECK_STATUS(otc_time_base_evidence_at(tb, 99, &eo), OTC_E_INVALID_ARGUMENT);
        CHECK(eo == NULL);
    }

    /* "" is no name: the constituent named "" is not found by it */
    CHECK(otc_set_constituent_count(set) == 2);
    co = STALE;
    CHECK_STATUS(otc_set_constituent(set, "", &co), OTC_E_NOT_FOUND);
    CHECK(co == NULL);
    co = NULL;
    CHECK_STATUS(otc_set_constituent(set, "M2", &co), OTC_OK);   /* the control */
    CHECK(co != NULL);

    /* the release's lists */
    fio = STALE;
    CHECK_STATUS(otc_release_file_at(rel, 99, &fio), OTC_E_INVALID_ARGUMENT);
    CHECK(fio == NULL);
    cvo = STALE;
    CHECK_STATUS(otc_release_convention_at(rel, 99, &cvo), OTC_E_INVALID_ARGUMENT);
    CHECK(cvo == NULL);
    cvo = STALE;
    CHECK_STATUS(otc_release_convention(rel, NULL, &cvo), OTC_E_INVALID_ARGUMENT);
    CHECK(cvo == NULL);
    lo = STALE;
    CHECK_STATUS(otc_release_licence_at(rel, 99, &lo), OTC_E_INVALID_ARGUMENT);
    CHECK(lo == NULL);
    lo = STALE;
    CHECK_STATUS(otc_release_licence(rel, NULL, &lo), OTC_E_INVALID_ARGUMENT);
    CHECK(lo == NULL);
    CHECK_STATUS(otc_release_stats(rel, &stats), OTC_OK);
    if (stats) {
        key = STALE;
        n = 77;
        CHECK_STATUS(otc_stats_type_at(stats, 99, &key, &n), OTC_E_INVALID_ARGUMENT);
        CHECK(key == NULL);
        CHECK(n == -1);
        otc_stats_free(stats);
    }

    /* otc_nearest: no station within 1 km of (50, 50) */
    hit.id = STALE;
    hit.distance_km = 3.0;
    CHECK_STATUS(otc_nearest(rel, 50.0, 50.0, 1.0, NULL, &hit), OTC_E_NOT_FOUND);
    CHECK(hit.id == NULL);
    CHECK(isnan(hit.distance_km));
    hit.id = STALE;
    hit.distance_km = 3.0;
    CHECK_STATUS(otc_nearest(rel, 99.0, 50.0, 1.0, NULL, &hit), OTC_E_INVALID_ARGUMENT);
    CHECK(hit.id == NULL);
    CHECK(isnan(hit.distance_km));
    CHECK_STATUS(otc_nearest(rel, 1.0, 1.0, 1.0, NULL, &hit), OTC_OK);   /* the control */
    CHECK(hit.id && !strcmp(hit.id, "OTC-X-1"));

    otc_station_free(st);
    otc_close(rel);
    free(path);
    free(dir);
    return test_done("test_outputs_cleared");
}
