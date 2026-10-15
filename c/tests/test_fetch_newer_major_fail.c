/* CR D10 (C side of T13/R70): when otc_fetch_check_for_update fails because no
 * release it can read exists, it still makes the OTC_latest.json check first,
 * so otc_fetch_newer_format_major reports the newer major. The call's own
 * error detail (READER_TOO_OLD) survives that check, and the newer format is
 * logged at level 2. */
#include "otc_test.h"

static int g_newer_logged;

static void log_fn(void *u, int level, const char *msg)
{
    (void)u;
    if (level == 2 && strstr(msg, "a newer format (2) exists")) g_newer_logged++;
}

int main(void)
{
    char *cache = test_tmpdir(), base[512];
    otc_fetch_options fo;
    otc_release_info *info = NULL;
    otc_error err;
    bool found = true;
    int major = 0;
    if (!test_server()) return test_skip("test_fetch_newer_major_fail", "no OTC_TEST_SERVER");
    otc_fetch_options_init(&fo);
    otc_error_init(&err);
    snprintf(base, sizeof base, "%s/good/", test_server());
    fo.cache_dir = cache;
    fo.base_url = base;
    fo.error = &err;
    fo.log_fn = log_fn;
    CHECK_STATUS(otc_fetch_check_for_update(&fo, "20991230", &info, &found), OTC_E_READER_TOO_OLD);
    CHECK(!found && !info);
    /* the error is still the call's own, not the OTC_latest.json check's */
    CHECK(err.status == OTC_E_READER_TOO_OLD && strstr(err.message, "needs a reader") != NULL);
    if (err.status != OTC_E_READER_TOO_OLD || !strstr(err.message, "needs a reader"))
        fprintf(stderr, "error after the check: %s: %s\n", otc_status_code(err.status), err.message);
    CHECK(g_newer_logged == 1);
    CHECK_STATUS(otc_fetch_newer_format_major(&fo, &major), OTC_OK);
    CHECK(major == 2);
    free(cache);
    return test_done("test_fetch_newer_major_fail");
}
