/* PK05 / C8: otc__index_doc (the index-v1.json document) under out of memory.
 * Every allocation is made to fail in turn: the result is NULL or a complete
 * document (every entry with every key), never a partial one, and nothing
 * leaks. */
#include "otc_test.h"
#include "otc_internal.h"
#include "otc_oom.h"

static const char *const KEYS[] = {"offset", "length", "station_id", "status", "name", "name_folded", "country", "type",
                                   "lat", "lon", "kind", "aliases", "reference_station_id", "offsets_licence_id",
                                   "recommended_set_id", "sets", NULL};

static int complete(const cJSON *doc)
{
    const cJSON *st = cJSON_GetObjectItem(doc, "stations"), *e;
    int n = 0;
    size_t i;
    if (!cJSON_IsArray(st) || !cJSON_GetObjectItem(doc, "jsonl_sha256") || !cJSON_GetObjectItem(doc, "by")) return 0;
    cJSON_ArrayForEach(e, st) {
        const cJSON *sets = cJSON_GetObjectItem(e, "sets");
        for (i = 0; KEYS[i]; i++) if (!cJSON_GetObjectItem(e, KEYS[i])) return 0;
        if (cJSON_GetArraySize(sets) != 1 || !cJSON_GetObjectItem(cJSON_GetArrayItem(sets, 0), "constituents")) return 0;
        n++;
    }
    return n == 2;
}

int main(void)
{
    char *dir = test_tmpdir(), *jsonl;
    otc_release *rel = NULL;
    long k, base;
    int runs = 0;
    test_write(dir, "OTC_20990101.meta.json", TEST_META("20990101"));
    test_write(dir, "OTC_20990101.jsonl", TEST_STATION("OTC-X-1", "First") "\n" TEST_STATION("OTC-X-2", "Me\\u0000da") "\n");
    jsonl = test_join(dir, "OTC_20990101.jsonl");
    printf("oom: start\n");
    if (otc_open_file(jsonl, NULL, &rel) != OTC_OK) return 2;
    for (k = 1; ; k++) {
        cJSON *doc;
        base = oom_live;
        oom_arm(k);
        doc = otc__index_doc(rel, "0000000000000000000000000000000000000000000000000000000000000000", "test");
        oom_disarm();
        if (doc && !complete(doc)) {
            fprintf(stderr, "allocation %ld fails: a partial index document is returned\n", k);
            CHECK(0);
        }
        cJSON_Delete(doc);
        if (oom_live != base) { fprintf(stderr, "allocation %ld fails: %ld blocks leak\n", k, oom_live - base); CHECK(0); }
        runs++;
        if (!oom_failed) { CHECK(doc != NULL); break; }
    }
    otc_close(rel);
    printf("oom: %d runs\n", runs);
    free(jsonl);
    free(dir);
    return test_done("test_index_oom");
}
