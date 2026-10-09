/* PK20 / C16: the C name aliases of spec 6.4 (otc_station_id,
 * otc_set_provenance_raw_json) are function-like macros: they work as calls,
 * and do not rewrite an application's own identifiers of the same name. */
#include "otc_test.h"

struct app { int otc_station_id; };   /* an application's field with the alias's name */

int main(void)
{
    char *dir = test_tmpdir(), *path, id[32];
    int otc_set_provenance_raw_json = 7;   /* and a variable */
    struct app a;
    otc_release *rel = NULL;
    otc_station_t *st = NULL;
    size_t need;
    a.otc_station_id = 3;
    test_write(dir, "OTC_20990101.meta.json", TEST_META("20990101"));
    test_write(dir, "OTC_20990101.jsonl", TEST_STATION("OTC-X-1", "One") "\n");
    path = test_join(dir, "OTC_20990101.jsonl");
    CHECK_STATUS(otc_open_file(path, NULL, &rel), OTC_OK);
    if (rel && otc_station(rel, "OTC-X-1", &st) == OTC_OK) {
        const otc_set *set = NULL;
        CHECK_STATUS(otc_station_id(st, id, sizeof id, &need), OTC_OK);
        CHECK(!strcmp(id, "OTC-X-1"));
        CHECK_STATUS(otc_station_recommended_set(st, &set), OTC_OK);
        CHECK(otc_set_provenance_raw_json(set, NULL, 0, &need) != OTC_OK || need > 0);
    }
    CHECK(a.otc_station_id == 3 && otc_set_provenance_raw_json == 7);
    otc_station_free(st);
    otc_close(rel);
    free(path);
    free(dir);
    return test_done("test_names");
}
