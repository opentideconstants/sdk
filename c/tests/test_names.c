/* PK20 / C16: the C name aliases of spec 6.4 (otc_station_id,
 * otc_set_provenance_raw_json) are function-like macros: they work as calls,
 * and do not rewrite an application's own identifiers of the same name. */
#include "otc_test.h"

/* a station whose recommended set has provenance */
#define ST2 "{\"station_id\":\"OTC-X-2\",\"status\":\"active\",\"name\":\"Two\",\"lat\":1.0,\"lon\":2.0," \
    "\"type\":\"reference\",\"recommended_set_id\":\"s\",\"constant_sets\":[{\"set_id\":\"s\",\"source\":\"src\"," \
    "\"source_type\":\"official\",\"quantity\":\"water_level\",\"qc_status\":\"ok\",\"convention_id\":\"c1\"," \
    "\"licence_id\":\"l1\",\"provenance\":{\"origin\":\"x\"},\"constituents\":[]}]}"

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
    test_write(dir, "OTC_20990101.jsonl", TEST_STATION("OTC-X-1", "One") "\n" ST2 "\n");
    path = test_join(dir, "OTC_20990101.jsonl");
    CHECK_STATUS(otc_open_file(path, NULL, &rel), OTC_OK);
    if (rel) CHECK_STATUS(otc_station(rel, "OTC-X-1", &st), OTC_OK);
    if (st) {
        const otc_set *set = NULL;
        id[0] = '\0';
        CHECK_STATUS(otc_station_id(st, id, sizeof id, &need), OTC_OK);
        CHECK(!strcmp(id, "OTC-X-1"));
        CHECK_STATUS(otc_station_recommended_set(st, &set), OTC_OK);
        /* this set has no provenance: NOT_FOUND exactly (C43), not just "some error" */
        need = 99;
        CHECK_STATUS(otc_set_provenance_raw_json(set, NULL, 0, &need), OTC_E_NOT_FOUND);
    }
    otc_station_free(st);
    st = NULL;
    /* and one that has it: the alias gives the same text as otc_set_provenance_json */
    if (rel) CHECK_STATUS(otc_station(rel, "OTC-X-2", &st), OTC_OK);
    if (st) {
        const otc_set *set = NULL;
        char a1[64] = "", a2[64] = "";
        size_t n1 = 0, n2 = 0;
        CHECK_STATUS(otc_station_recommended_set(st, &set), OTC_OK);
        CHECK_STATUS(otc_set_provenance_raw_json(set, a1, sizeof a1, &n1), OTC_OK);
        CHECK_STATUS(otc_set_provenance_json(set, a2, sizeof a2, &n2), OTC_OK);
        CHECK(n1 > 0 && n1 == n2 && !strcmp(a1, a2) && strstr(a1, "\"origin\"") != NULL);
    }
    CHECK(a.otc_station_id == 3 && otc_set_provenance_raw_json == 7);
    otc_station_free(st);
    otc_close(rel);
    free(path);
    free(dir);
    return test_done("test_names");
}
