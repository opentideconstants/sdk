/* PK03 / C30: a pointer without format_version is judged as in the cache path
 * (the release's own .meta.json is checked at open): it is not "a newer
 * format (-1)", and it costs no extra GET of OTC_index.json. */
#include "otc_test.h"

static int g_bad_log;

static void log_fn(void *u, int level, const char *msg)
{
    (void)u;
    (void)level;
    if (strstr(msg, "(-1)") || strstr(msg, "OTC_index.json")) {
        fprintf(stderr, "log: %s\n", msg);
        g_bad_log++;
    }
}

int main(void)
{
    char *cache = test_tmpdir(), base[512];
    otc_fetch_options fo;
    otc_release_info *info = NULL;
    otc_error err;
    if (!test_server()) { printf("test_fetch_pointer_no_fv: skipped (no OTC_TEST_SERVER)\n"); return 0; }
    otc_fetch_options_init(&fo);
    otc_error_init(&err);
    snprintf(base, sizeof base, "%s/good/", test_server());
    fo.cache_dir = cache;
    fo.base_url = base;
    fo.error = &err;
    fo.log_fn = log_fn;
    CHECK_STATUS(otc_fetch_latest_info(&fo, &info), OTC_OK);
    CHECK(g_bad_log == 0);
    otc_release_info_free(info);
    free(cache);
    return test_done("test_fetch_pointer_no_fv");
}
