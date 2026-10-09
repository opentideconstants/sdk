/* PK03 / C52: in otc_fetch_check_for_update the conditional GET of
 * OTC_latest.json is a side probe. When it fails, the call still answers,
 * the failure is logged at level 2 with its cause, and the newer-major value
 * from before is kept (spec 7.4, CR D10). */
#include "otc_test.h"

static int g_warned;

static void log_fn(void *u, int level, const char *msg)
{
    (void)u;
    if (level == 2 && strstr(msg, "OTC_latest.json") && strstr(msg, "500")) g_warned++;
}

int main(void)
{
    char *cache = test_tmpdir(), base[512], *pdir;
    otc_fetch_options fo;
    otc_release_info *info = NULL;
    otc_error err;
    bool found = true;
    int major = 0;
    if (!test_server()) { printf("test_fetch_check_probe: skipped (no OTC_TEST_SERVER)\n"); return 0; }
    otc_fetch_options_init(&fo);
    otc_error_init(&err);
    snprintf(base, sizeof base, "%s/good/", test_server());
    fo.cache_dir = cache;
    fo.base_url = base;
    fo.error = &err;
    fo.log_fn = log_fn;
    /* a value from before: the cached OTC_latest.json names format 2 */
    pdir = test_join(cache, "v1");
    mkdir(pdir, 0777);
    free(pdir);
    pdir = test_join(cache, "v1/pointer");
    mkdir(pdir, 0777);
    test_write(pdir, "OTC_latest.json", "{\"datestamp\":\"21000101\",\"format_version\":\"2.0\"}");
    CHECK_STATUS(otc_fetch_check_for_update(&fo, "20991231", &info, &found), OTC_OK);
    CHECK(found && info);
    CHECK(g_warned == 1);
    CHECK(err.status == OTC_OK);
    CHECK_STATUS(otc_fetch_newer_format_major(&fo, &major), OTC_OK);
    CHECK(major == 2);
    otc_release_info_free(info);
    free(pdir);
    free(cache);
    return test_done("test_fetch_check_probe");
}
