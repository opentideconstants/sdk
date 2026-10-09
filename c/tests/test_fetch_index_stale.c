/* PK05 / C2 (R2-209): a stale index-v1.json in the cache is rewritten.
 * otc_open_file only reads the index; the fetch layer writes it when an open
 * did not use it (missing or stale, spec 6.2). So after otc_fetch_open over a
 * cached release whose index has an entry of length 0 (stale), the file is a
 * fresh index again: the next otc_open_file uses it and answers right. */
#include "otc_test.h"
#include "otc_internal.h"

static char *read_text(const char *path)
{
    char *text = NULL;
    size_t len = 0;
    if (otc__read_all(path, &text, &len) != OTC_OK) return NULL;
    return text;
}

/* opens the cached .jsonl as a plain file: whether the index was used, and the first station opens */
static int open_plain(const char *jsonl, int *index_used)
{
    otc_release *rel = NULL;
    const char *ids[64] = {NULL};
    size_t n = 0;
    otc_station_t *st = NULL;
    int ok;
    *index_used = -1;
    if (otc_open_file(jsonl, NULL, &rel) != OTC_OK) return 0;
    *index_used = rel->index_used;
    ok = otc_stations(rel, NULL, ids, 64, &n) == OTC_OK && n >= 1 && ids[0] && otc_station(rel, ids[0], &st) == OTC_OK;
    otc_station_free(st);
    otc_close(rel);
    return ok;
}

int main(void)
{
    char *cache = test_tmpdir(), base[512], path[4096], *jsonl, *ixp, *stale_text, *after;
    otc_fetch_options fo;
    otc_release *rel = NULL;
    otc_error err;
    size_t need;
    int used = -1;
    cJSON *doc;
    if (!test_server()) return test_skip("test_fetch_index_stale", "no OTC_TEST_SERVER");
    otc_fetch_options_init(&fo);
    otc_error_init(&err);
    snprintf(base, sizeof base, "%s/good/", test_server());
    fo.cache_dir = cache;
    fo.base_url = base;
    fo.error = &err;
    CHECK_STATUS(otc_fetch_latest(&fo, path, sizeof path, &need), OTC_OK);
    jsonl = test_join(cache, "v1/releases/20991231.2/OTC_20991231.2.jsonl");
    ixp = test_join(cache, "v1/releases/20991231.2/index-v1.json");
    /* the premise: the download wrote a fresh index, which a plain open uses */
    CHECK(open_plain(jsonl, &used) && used == 1);
    /* make it stale: an entry of length 0 */
    stale_text = read_text(ixp);
    if (!stale_text) { fprintf(stderr, "test_fetch_index_stale: no index-v1.json after the download\n"); return 1; }
    doc = cJSON_Parse(stale_text);
    free(stale_text);
    if (!doc || !cJSON_ReplaceItemInObject(cJSON_GetArrayItem(cJSON_GetObjectItem(doc, "stations"), 0), "length",
                                           cJSON_CreateNumber(0))) {
        fprintf(stderr, "test_fetch_index_stale: cannot make the index stale\n");
        return 2;
    }
    stale_text = cJSON_PrintUnformatted(doc);
    cJSON_Delete(doc);
    if (!stale_text) return 2;
    {
        FILE *f = fopen(ixp, "wb");
        if (!f || fputs(stale_text, f) < 0 || fclose(f) != 0) { perror(ixp); return 2; }
    }
    CHECK(open_plain(jsonl, &used) && used == 0);   /* stale: not used */
    /* the fetch open from the cache rebuilds, and writes the index again */
    fo.offline = true;
    CHECK_STATUS(otc_fetch_open(&fo, "20991231.2", NULL, &rel), OTC_OK);
    if (rel) CHECK(rel->index_used == 0);
    otc_close(rel);
    after = read_text(ixp);
    CHECK(after != NULL && strcmp(after, stale_text) != 0);
    CHECK(open_plain(jsonl, &used) && used == 1);   /* fresh again */
    if (used != 1) fprintf(stderr, "after otc_fetch_open, a plain open %s the index\n", used == 0 ? "still rebuilds without" : "fails with");
    free(after);
    cJSON_free(stale_text);
    free(ixp);
    free(jsonl);
    free(cache);
    return test_done("test_fetch_index_stale");
}
