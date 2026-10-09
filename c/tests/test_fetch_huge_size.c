/* PK12 / C27: a size in the pointer that is not a whole number in range
 * (1e300, -5.5) is never cast to int64_t (undefined behaviour; UBSan
 * reports it). CR2 DR12: such an entry is OTC_E_INVALID_RELEASE at parse. */
#include "otc_test.h"

int main(void)
{
    char *cache = test_tmpdir(), base[512];
    otc_fetch_options fo;
    otc_release_info *info = NULL;
    otc_release *rel = NULL;
    otc_error err;
    if (!test_server()) { printf("test_fetch_huge_size: skipped (no OTC_TEST_SERVER)\n"); return 0; }
    otc_fetch_options_init(&fo);
    otc_error_init(&err);
    snprintf(base, sizeof base, "%s/good/", test_server());
    fo.cache_dir = cache;
    fo.base_url = base;
    fo.error = &err;
    CHECK_STATUS(otc_fetch_latest_info(&fo, &info), OTC_E_INVALID_RELEASE);
    CHECK(info == NULL);
    otc_release_info_free(info);
    CHECK_STATUS(otc_fetch_open(&fo, NULL, NULL, &rel), OTC_E_INVALID_RELEASE);
    CHECK(rel == NULL);
    otc_close(rel);
    free(cache);
    return test_done("test_fetch_huge_size");
}
