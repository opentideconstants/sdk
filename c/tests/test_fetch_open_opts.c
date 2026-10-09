/* PK20 / C25: otc_fetch_open passes the caller's open options to the open
 * of the cached file: its log_fn sees that open, and require_checksum
 * applies (spec 4.2, header of otc_fetch_open): with the .sha256 gone, the
 * same open opens from the cache without require_checksum (the control, so
 * the failure is require_checksum's doing), and gives checksum_mismatch with
 * it (DR34). */
#include "otc_test.h"

static int g_file_open_logged;

static void log_fn(void *u, int level, const char *msg)
{
    (void)u;
    (void)level;
    if (strstr(msg, "opened ") && strstr(msg, "OTC_20991231.2.jsonl")) g_file_open_logged++;
}

int main(void)
{
    char *cache = test_tmpdir(), base[512];
    otc_fetch_options fo;
    otc_open_options oo;
    otc_release *rel = NULL;
    otc_error err;
    if (!test_server()) return test_skip("test_fetch_open_opts", "no OTC_TEST_SERVER");
    otc_fetch_options_init(&fo);
    otc_open_options_init(&oo);
    otc_error_init(&err);
    snprintf(base, sizeof base, "%s/good/", test_server());
    fo.cache_dir = cache;
    fo.base_url = base;
    fo.error = &err;
    oo.log_fn = log_fn;
    oo.require_checksum = true;
    CHECK_STATUS(otc_fetch_open(&fo, "20991231.2", &oo, &rel), OTC_OK);
    otc_close(rel);
    rel = NULL;
    CHECK(g_file_open_logged >= 1);
    /* from the cache, require_checksum with the .sha256 removed: checksum_mismatch (DR34) */
    {
        char *sums = test_join(cache, "v1/releases/20991231.2/OTC_20991231.2.sha256");
        if (unlink(sums) != 0) { perror(sums); return 2; }
        free(sums);
    }
    fo.offline = true;
    /* the control first: without require_checksum the same open opens the cached release
     * (after a checksum failure the cached release is healed, CR2 DR16, so it comes first) */
    oo.require_checksum = false;
    CHECK_STATUS(otc_fetch_open(&fo, "20991231.2", &oo, &rel), OTC_OK);
    if (rel) CHECK(otc_release_loaded_from(rel) == OTC_LOADED_FROM_CACHE);
    otc_close(rel);
    rel = NULL;
    oo.require_checksum = true;
    CHECK_STATUS(otc_fetch_open(&fo, "20991231.2", &oo, &rel), OTC_E_CHECKSUM);
    CHECK(strstr(err.message, "require_checksum") != NULL);
    if (!strstr(err.message, "require_checksum")) fprintf(stderr, "error: %s\n", err.message);
    otc_close(rel);
    free(cache);
    return test_done("test_fetch_open_opts");
}
