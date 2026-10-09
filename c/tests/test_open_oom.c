/* PK20 memory safety under out of memory, with every allocation made to
 * fail in turn (no crash, no leak, the right status):
 *  C32: otc_station (otc__station_build's cleanup); also otc_open_file and
 *       the queries. */
#include "otc_test.h"
#include "otc_oom.h"

#define ST2 "{\"station_id\":\"OTC-X-2\",\"status\":\"active\",\"name\":\"Sub\",\"lat\":1,\"lon\":1,\"type\":\"subordinate\"," \
    "\"aliases\":{\"noaa\":[\"1\",\"2\"]},\"subordinate_offsets\":{\"reference_station_id\":\"OTC-X-1\",\"licence_id\":\"l1\"}," \
    "\"recommended_set_id\":\"s\",\"constant_sets\":[{\"set_id\":\"s\",\"source\":\"x\",\"quantity\":\"water_level\"," \
    "\"qc_status\":\"ok\",\"convention_id\":\"c1\",\"licence_id\":\"l1\",\"constituents\":[{\"name\":\"M2\"},{\"name\":\"S2\"}]," \
    "\"qc_flags\":[{\"flag\":\"short_record\"}],\"dropped_constituents\":[{\"name\":\"K2\"}],\"time_base\":{\"code\":\"verified\"," \
    "\"evidence\":[{\"comparator_kind\":\"x\"}]}},{\"set_id\":\"t\",\"source\":\"y\",\"qc_status\":\"no_constants\"," \
    "\"convention_id\":\"c1\",\"licence_id\":\"l1\"}],\"validation\":[{\"set_id\":\"s\",\"window\":\"w\"}]}"

/* An open that gave OTC_OK although an allocation failed: the one case known
 * today is build_files, which reads a failed path join as "size unknown" (-1)
 * and goes on. Gives 1 when a file of rel has size -1. */
static int has_unknown_size(const otc_release *rel)
{
    size_t i;
    for (i = 0; i < otc_release_file_count(rel); i++) {
        const otc_file_info *fi = NULL;
        if (otc_release_file_at(rel, i, &fi) == OTC_OK && otc_file_info_size(fi) == -1) return 1;
    }
    return 0;
}

/* Judges one run whose result is not OK or NOMEM, or is OK although an
 * allocation failed. Only two such results are known library defects (PK-R2-23:
 * a failed allocation must give OTC_E_NOMEM). They are counted, and PENDING at
 * the end; any other is a failure:
 *  - INVALID_RELEASE when the failed allocation was cJSON's (a parse that runs
 *    out of memory reads as "not JSON")
 *  - OK with a file of size -1 (build_files swallows a failed otc__join) */
static long g_cjson_invalid, g_ok_unknown_size;

static void judge(const char *what, long k, otc_status st, const otc_release *rel_ok)
{
    if (st == OTC_E_INVALID_RELEASE && oom_cjson_failed) {
        g_cjson_invalid++;
    } else if (st == OTC_OK && rel_ok && has_unknown_size(rel_ok)) {
        fprintf(stderr, "%s, allocation %ld fails: ok, with a file size read as unknown\n", what, k);
        g_ok_unknown_size++;
    } else {
        fprintf(stderr, "%s, allocation %ld fails: %s (only ok before the failure, or out_of_memory, is right)\n", what,
                k, otc_status_code(st));
        CHECK(0);
    }
}

int main(void)
{
    char *dir = test_tmpdir(), *path;
    otc_release *rel = NULL;
    otc_status ost;
    long k, base, injected;
    int runs = 0;
    test_write(dir, "OTC_20990101.meta.json", TEST_META("20990101"));
    test_write(dir, "OTC_20990101.jsonl", TEST_STATION("OTC-X-1", "One") "\n" ST2 "\n");
    path = test_join(dir, "OTC_20990101.jsonl");
    printf("oom: start\n");
    oom_hook_cjson();
    /* the open */
    for (k = 1, injected = 0; k <= OOM_MAX_RUNS; k++) {
        otc_status st;
        base = oom_live;
        oom_arm(k);
        st = otc_open_file(path, NULL, &rel);
        oom_disarm();
        runs++;
        if (!oom_failed) {
            CHECK_STATUS(st, OTC_OK);
            otc_close(rel);
            rel = NULL;
            break;
        }
        injected++;
        if (st != OTC_E_NOMEM) judge("open", k, st, rel);
        if (st != OTC_OK) CHECK(rel == NULL);
        otc_close(rel);
        rel = NULL;
        if (oom_live != base) { fprintf(stderr, "open, allocation %ld fails: %ld blocks leak\n", k, oom_live - base); CHECK(0); }
    }
    CHECK(oom_loop_end("open", k, injected));
    ost = otc_open_file(path, NULL, &rel);
    if (ost != OTC_OK) {
        fprintf(stderr, "test_open_oom: the open without a failure gave %s\n", otc_status_code(ost));
        return 2;
    }
    /* C32: a station */
    for (k = 1, injected = 0; k <= OOM_MAX_RUNS; k++) {
        otc_station_t *st = NULL;
        otc_status rc;
        base = oom_live;
        oom_arm(k);
        rc = otc_station(rel, "OTC-X-2", &st);
        oom_disarm();
        runs++;
        CHECK(rc == OTC_OK ? st != NULL : st == NULL);
        otc_station_free(st);
        if (oom_live != base) { fprintf(stderr, "station, allocation %ld fails: %ld blocks leak\n", k, oom_live - base); CHECK(0); }
        if (!oom_failed) { CHECK_STATUS(rc, OTC_OK); break; }
        injected++;
        if (rc != OTC_E_NOMEM) judge("station", k, rc, NULL);
    }
    CHECK(oom_loop_end("station", k, injected));
    otc_close(rel);
    printf("oom: %d runs\n", runs);
    if (g_cjson_invalid)
        fprintf(stderr, "%ld runs: a failed cJSON allocation reads as invalid_release, not out_of_memory\n", g_cjson_invalid);
    PENDING("PK-R2-23", g_cjson_invalid == 0);
    PENDING("PK-R2-23", g_ok_unknown_size == 0);
    free(path);
    free(dir);
    return test_done("test_open_oom");
}
