/* PK07 value checks on the real library.
 * C48: an integer field (missed_events, good_samples ...) with a fraction is
 *      not cut to an integer: it reads as missing (-1). */
#include "otc_test.h"

static otc_release *open_lines(const char *lines, char **dir_out)
{
    char *dir = test_tmpdir(), *path;
    otc_release *rel = NULL;
    otc_status st;
    test_write(dir, "OTC_20990101.meta.json", TEST_META("20990101"));
    test_write(dir, "OTC_20990101.jsonl", lines);
    path = test_join(dir, "OTC_20990101.jsonl");
    st = otc_open_file(path, NULL, &rel);
    if (st != OTC_OK) fprintf(stderr, "open: %s\n", otc_status_code(st));
    free(path);
    *dir_out = dir;
    return rel;
}

int main(void)
{
    char *dir;
    otc_release *rel;
    otc_station_t *st = NULL;
    /* C48 */
    rel = open_lines("{\"station_id\":\"OTC-X-1\",\"status\":\"active\",\"name\":\"A\",\"lat\":1,\"lon\":1,\"type\":\"reference\","
                     "\"constant_sets\":[],\"validation\":[{\"set_id\":\"s\",\"missed_events\":1.5,\"extra_events\":2}]}\n", &dir);
    CHECK(rel != NULL);
    if (rel && otc_station(rel, "OTC-X-1", &st) == OTC_OK) {
        const otc_validation_t *v = NULL;
        CHECK_STATUS(otc_station_validation_at(st, 0, &v), OTC_OK);
        if (v) {
            CHECK(v->missed_events == -1);
            CHECK(v->extra_events == 2);
            if (v->missed_events != -1) fprintf(stderr, "missed_events 1.5 read as %lld\n", (long long)v->missed_events);
        }
    }
    otc_station_free(st);
    otc_close(rel);
    free(dir);
    return test_done("test_values");
}
