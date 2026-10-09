/* PK11 / C22: a cached file that fails its check.
 *  - after a network error with use_cache: the cache is tried (it fails its
 *    check and is healed, CR2 DR16), and the error is the network's, not the
 *    corrupt cache's checksum_mismatch;
 *  - online: a cached release that fails its check is downloaded again (and
 *    the good file is back).
 * The library's own log lines show which path ran. */
#include "otc_test.h"

static int g_fallback_failed, g_redownload;

static void log_fn(void *u, int level, const char *msg)
{
    (void)u;
    if (level == 2 && strstr(msg, "is corrupt (") && strstr(msg, "removing it from the cache")) g_fallback_failed++;
    if (level == 2 && strstr(msg, "downloading the release ") && strstr(msg, " again")) g_redownload++;
}

static void corrupt(const char *path)
{
    FILE *f = fopen(path, "r+b");
    int ch;
    if (!f) { perror(path); exit(2); }
    if (fseek(f, 100, SEEK_SET) != 0 || (ch = fgetc(f)) == EOF || fseek(f, 100, SEEK_SET) != 0
        || fputc(ch == 'x' ? 'y' : 'x', f) == EOF || fclose(f) != 0) {
        perror(path);
        exit(2);
    }
}

int main(void)
{
    char *cache = test_tmpdir(), base[512], path[4096];
    otc_fetch_options fo;
    otc_release *rel = NULL;
    otc_error err;
    size_t need;
    if (!test_server()) return test_skip("test_fetch_heal", "no OTC_TEST_SERVER");
    otc_fetch_options_init(&fo);
    otc_error_init(&err);
    snprintf(base, sizeof base, "%s/good/", test_server());
    fo.cache_dir = cache;
    fo.base_url = base;
    fo.error = &err;
    fo.log_fn = log_fn;
    CHECK_STATUS(otc_fetch_latest(&fo, path, sizeof path, &need), OTC_OK);
    CHECK(strstr(path, "OTC_20991231.2.jsonl") != NULL);
    /* the network is down, the cache is corrupt: the cache is tried, and the error is the network's */
    corrupt(path);
    CHECK(otc_verify_file(path, NULL, &err) == OTC_E_CHECKSUM);   /* the premise */
    fo.base_url = "http://127.0.0.1:9/";
    g_fallback_failed = g_redownload = 0;
    CHECK_STATUS(otc_fetch_open(&fo, NULL, NULL, &rel), OTC_E_NETWORK);
    CHECK(rel == NULL);
    CHECK(g_fallback_failed == 1);
    CHECK(err.status == OTC_E_NETWORK && strstr(err.message, "SHA-256") == NULL);
    if (err.status != OTC_E_NETWORK || strstr(err.message, "SHA-256")) fprintf(stderr, "error: %s\n", err.message);
    otc_close(rel);
    rel = NULL;
    /* online again: the healed release is downloaded, then made corrupt once more */
    fo.base_url = base;
    CHECK_STATUS(otc_fetch_latest(&fo, path, sizeof path, &need), OTC_OK);
    corrupt(path);
    CHECK(otc_verify_file(path, NULL, &err) == OTC_E_CHECKSUM);   /* the premise */
    /* downloaded again because the check failed, and healed */
    g_fallback_failed = g_redownload = 0;
    CHECK_STATUS(otc_fetch_open(&fo, NULL, NULL, &rel), OTC_OK);
    if (rel) CHECK(otc_release_loaded_from(rel) == OTC_LOADED_FROM_DOWNLOAD);
    CHECK(g_redownload == 1);
    otc_close(rel);
    CHECK_STATUS(otc_verify_file(path, NULL, &err), OTC_OK);
    free(cache);
    return test_done("test_fetch_heal");
}
