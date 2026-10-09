/* CR D8 (C side of P81/R28): a failure to write the cached pointer is logged,
 * and the call goes on: the pointer only saves work (spec 4.8 cache, 5.2). */
#include "otc_test.h"

static int g_logged;

static void log_fn(void *u, int level, const char *msg)
{
    (void)u;
    if (level == 2 && strstr(msg, "OTC_latest-f1.json")) g_logged++;
}

int main(void)
{
    char *cache = test_tmpdir(), base[512], *pdir;
    otc_fetch_options fo;
    otc_release_info *info = NULL;
    otc_error err;
    if (!test_server()) { printf("test_fetch_pointer_readonly: skipped (no OTC_TEST_SERVER)\n"); return 0; }
    otc_fetch_options_init(&fo);
    otc_error_init(&err);
    snprintf(base, sizeof base, "%s/good/", test_server());
    fo.cache_dir = cache;
    fo.base_url = base;
    fo.error = &err;
    fo.log_fn = log_fn;
    pdir = test_join(cache, "v1");
    mkdir(pdir, 0777);
    free(pdir);
    pdir = test_join(cache, "v1/pointer");
    mkdir(pdir, 0555);
    if (access(pdir, W_OK) == 0) {
        printf("test_fetch_pointer_readonly: skipped (running as root)\n");
        free(pdir);
        free(cache);
        return 0;
    }
    CHECK_STATUS(otc_fetch_latest_info(&fo, &info), OTC_OK);
    CHECK(info != NULL);
    CHECK(g_logged >= 1);
    otc_release_info_free(info);
    chmod(pdir, 0755);
    free(pdir);
    free(cache);
    return test_done("test_fetch_pointer_readonly");
}
