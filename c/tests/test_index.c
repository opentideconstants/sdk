/* PK05 / C2: the stream index (index-v1.json, spec 6.2, CR D4).
 *  - an entry whose line is another station's: the query is invalid_release
 *    (never the wrong station), and index-v1.json is deleted;
 *  - an entry with length 0, or offsets that do not increase: the index is
 *    stale, so the open rebuilds from the .jsonl and the query is right. */
#include "otc_test.h"
#include "otc_internal.h"

static char *g_dir, *g_jsonl;

static void write_index(cJSON *(*tamper)(cJSON *doc))
{
    otc_release *rel = NULL;
    char hex[65], *txt, *ixp;
    cJSON *doc;
    FILE *f;
    if (otc_open_file(g_jsonl, NULL, &rel) != OTC_OK) { fprintf(stderr, "open failed\n"); exit(2); }
    otc__sha256_file(g_jsonl, hex);
    doc = otc__index_doc(rel, hex, "test");
    otc_close(rel);
    if (tamper) doc = tamper(doc);
    txt = cJSON_PrintUnformatted(doc);
    ixp = test_join(g_dir, "index-v1.json");
    f = fopen(ixp, "wb");
    fputs(txt, f);
    fclose(f);
    free(ixp);
    cJSON_free(txt);
    cJSON_Delete(doc);
}

static cJSON *entry(cJSON *doc, int i) { return cJSON_GetArrayItem(cJSON_GetObjectItem(doc, "stations"), i); }

static cJSON *swap_ids(cJSON *doc)
{
    cJSON_ReplaceItemInObject(entry(doc, 0), "station_id", cJSON_CreateString("OTC-X-2"));
    cJSON_ReplaceItemInObject(entry(doc, 1), "station_id", cJSON_CreateString("OTC-X-1"));
    return doc;
}

static cJSON *zero_length(cJSON *doc)
{
    cJSON_ReplaceItemInObject(entry(doc, 0), "length", cJSON_CreateNumber(0));
    return doc;
}

static cJSON *same_offsets(cJSON *doc)
{
    cJSON_ReplaceItemInObject(entry(doc, 1), "offset", cJSON_CreateNumber(0));
    cJSON_ReplaceItemInObject(entry(doc, 1), "length", cJSON_CreateNumber(cJSON_GetObjectItem(entry(doc, 0), "length")->valuedouble));
    return doc;
}

static void check_station(const char *id, const char *want_name, int want_index)
{
    otc_release *rel = NULL;
    otc_station_t *st = NULL;
    char name[64];
    size_t need;
    CHECK_STATUS(otc_open_file(g_jsonl, NULL, &rel), OTC_OK);
    if (!rel) return;
    CHECK(rel->index_used == want_index);
    CHECK_STATUS(otc_station(rel, id, &st), OTC_OK);
    if (st) {
        otc_station_name(st, name, sizeof name, &need);
        CHECK(!strcmp(name, want_name));
    }
    otc_station_free(st);
    otc_close(rel);
}

int main(void)
{
    char sums[512], hex_l[65], hex_m[65], *ixp, *mp;
    otc_release *rel = NULL;
    otc_station_t *st = NULL;
    g_dir = test_tmpdir();
    test_write(g_dir, "OTC_20990101.meta.json", TEST_META("20990101"));
    test_write(g_dir, "OTC_20990101.jsonl", TEST_STATION("OTC-X-1", "First") "\n" TEST_STATION("OTC-X-2", "Second") "\n");
    g_jsonl = test_join(g_dir, "OTC_20990101.jsonl");
    mp = test_join(g_dir, "OTC_20990101.meta.json");
    otc__sha256_file(g_jsonl, hex_l);
    otc__sha256_file(mp, hex_m);
    snprintf(sums, sizeof sums, "%s  OTC_20990101.jsonl\n%s  OTC_20990101.meta.json\n", hex_l, hex_m);
    test_write(g_dir, "OTC_20990101.sha256", sums);
    ixp = test_join(g_dir, "index-v1.json");

    /* a fresh index is used */
    write_index(NULL);
    check_station("OTC-X-1", "First", 1);

    /* swapped ids: invalid_release, never the other station, and the index goes */
    write_index(swap_ids);
    CHECK_STATUS(otc_open_file(g_jsonl, NULL, &rel), OTC_OK);
    if (rel) {
        char msg[512];
        size_t need;
        CHECK(rel->index_used == 1);
        CHECK_STATUS(otc_station(rel, "OTC-X-1", &st), OTC_E_INVALID_RELEASE);
        otc_station_free(st);
        st = NULL;
        otc_last_error(rel, msg, sizeof msg, &need);
        CHECK(strstr(msg, "index-v1.json") != NULL);
        otc_close(rel);
    }
    CHECK(access(ixp, F_OK) != 0);
    check_station("OTC-X-1", "First", 0);

    /* out of bounds: rebuilt, right answers */
    write_index(zero_length);
    check_station("OTC-X-1", "First", 0);
    write_index(same_offsets);
    check_station("OTC-X-2", "Second", 0);

    free(ixp);
    free(mp);
    free(g_jsonl);
    free(g_dir);
    return test_done("test_index");
}
