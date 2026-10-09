/* CR D10 (C side of T13/R70): when otc_fetch_check_for_update fails because no
 * release it can read exists, it still makes the OTC_latest.json check first,
 * so otc_fetch_newer_format_major reports the newer major. */
#include "otc_test.h"

int main(void)
{
    char *cache = test_tmpdir(), base[512];
    otc_fetch_options fo;
    otc_release_info *info = NULL;
    otc_error err;
    bool found = true;
    int major = 0;
    if (!test_server()) { printf("test_fetch_newer_major_fail: skipped (no OTC_TEST_SERVER)\n"); return 0; }
    otc_fetch_options_init(&fo);
    otc_error_init(&err);
    snprintf(base, sizeof base, "%s/good/", test_server());
    fo.cache_dir = cache;
    fo.base_url = base;
    fo.error = &err;
    CHECK_STATUS(otc_fetch_check_for_update(&fo, "20991230", &info, &found), OTC_E_READER_TOO_OLD);
    CHECK(!found && !info);
    CHECK_STATUS(otc_fetch_newer_format_major(&fo, &major), OTC_OK);
    CHECK(major == 2);
    free(cache);
    return test_done("test_fetch_newer_major_fail");
}
