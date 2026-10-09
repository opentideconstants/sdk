/* PK11 / C22: a cached file that fails its check.
 *  - online: the release is downloaded again (and the good file is back);
 *  - after a network error with use_cache: the error is the network's, not
 *    the corrupt cache's checksum_mismatch. */
#include "otc_test.h"

static void corrupt(const char *path)
{
    FILE *f = fopen(path, "r+b");
    int ch;
    if (!f) { perror(path); exit(2); }
    fseek(f, 100, SEEK_SET);
    ch = fgetc(f);
    fseek(f, 100, SEEK_SET);
    fputc(ch == 'x' ? 'y' : 'x', f);
    fclose(f);
}

int main(void)
{
    char *cache = test_tmpdir(), base[512], path[4096], *jsonl;
    otc_fetch_options fo;
    otc_release *rel = NULL;
    otc_error err;
    size_t need;
    if (!test_server()) { printf("test_fetch_heal: skipped (no OTC_TEST_SERVER)\n"); return 0; }
    otc_fetch_options_init(&fo);
    otc_error_init(&err);
    snprintf(base, sizeof base, "%s/good/", test_server());
    fo.cache_dir = cache;
    fo.base_url = base;
    fo.error = &err;
    CHECK_STATUS(otc_fetch_latest(&fo, path, sizeof path, &need), OTC_OK);
    jsonl = test_join(cache, "v1/releases/20991231.2/OTC_20991231.2.jsonl");
    /* the network is down, the cache is corrupt: network error */
    corrupt(jsonl);
    fo.base_url = "http://127.0.0.1:9/";
    CHECK_STATUS(otc_fetch_open(&fo, NULL, NULL, &rel), OTC_E_NETWORK);
    otc_close(rel);
    rel = NULL;
    /* online again: healed */
    fo.base_url = base;
    CHECK_STATUS(otc_fetch_open(&fo, NULL, NULL, &rel), OTC_OK);
    if (rel) CHECK(otc_release_loaded_from(rel) == OTC_LOADED_FROM_DOWNLOAD);
    otc_close(rel);
    CHECK_STATUS(otc_verify_file(jsonl, NULL, &err), OTC_OK);
    free(jsonl);
    free(cache);
    return test_done("test_fetch_heal");
}
