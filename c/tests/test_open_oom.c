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

int main(void)
{
    char *dir = test_tmpdir(), *path;
    otc_release *rel = NULL;
    long k, base;
    int runs = 0;
    test_write(dir, "OTC_20990101.meta.json", TEST_META("20990101"));
    test_write(dir, "OTC_20990101.jsonl", TEST_STATION("OTC-X-1", "One") "\n" ST2 "\n");
    path = test_join(dir, "OTC_20990101.jsonl");
    printf("oom: start\n");
    /* the open */
    for (k = 1; ; k++) {
        otc_status st;
        base = oom_live;
        oom_arm(k);
        st = otc_open_file(path, NULL, &rel);
        oom_disarm();
        /* a parse that runs out of memory reads as "not JSON" (cJSON does not tell them apart) */
        if (st != OTC_OK && st != OTC_E_NOMEM && st != OTC_E_INVALID_RELEASE) {
            fprintf(stderr, "open, allocation %ld fails: %s\n", k, otc_status_code(st));
            CHECK(0);
        }
        otc_close(rel);
        rel = NULL;
        if (oom_live != base) { fprintf(stderr, "open, allocation %ld fails: %ld blocks leak\n", k, oom_live - base); CHECK(0); }
        runs++;
        if (!oom_failed) { CHECK(st == OTC_OK); break; }
    }
    if (otc_open_file(path, NULL, &rel) != OTC_OK) return 2;
    /* C32: a station */
    for (k = 1; ; k++) {
        otc_station_t *st = NULL;
        otc_status rc;
        base = oom_live;
        oom_arm(k);
        rc = otc_station(rel, "OTC-X-2", &st);
        oom_disarm();
        CHECK(rc == OTC_OK || rc == OTC_E_NOMEM || rc == OTC_E_INVALID_RELEASE);   /* a parse that runs out reads as not JSON */
        CHECK(rc == OTC_OK ? st != NULL : st == NULL);
        otc_station_free(st);
        if (oom_live != base) { fprintf(stderr, "station, allocation %ld fails: %ld blocks leak\n", k, oom_live - base); CHECK(0); }
        runs++;
        if (!oom_failed) { CHECK(rc == OTC_OK); break; }
    }
    otc_close(rel);
    printf("oom: %d runs\n", runs);
    free(path);
    free(dir);
    return test_done("test_open_oom");
}
