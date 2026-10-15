/* PK12 / C27: a size in the pointer that is not a whole number in range
 * (1e300, -5.5) is never cast to int64_t (undefined behaviour; UBSan
 * reports it). CR2 DR12: such an entry is OTC_E_INVALID_RELEASE at parse,
 * for the pointer with both sizes out of range (/good/) and for the one with
 * only the .jsonl's (/wrongbody/, whose .jsonl is another file's bytes: the
 * parse fails first, so nothing is downloaded and checked). */
#include "otc_test.h"

int main(void)
{
    char *cache = test_tmpdir(), *cache2 = test_tmpdir(), base[512];
    otc_fetch_options fo;
    otc_release_info *info = NULL;
    otc_release *rel = NULL;
    otc_error err;
    if (!test_server()) return test_skip("test_fetch_huge_size", "no OTC_TEST_SERVER");
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
    rel = NULL;
    /* one size out of range is enough */
    snprintf(base, sizeof base, "%s/wrongbody/", test_server());
    fo.cache_dir = cache2;
    fo.base_url = base;
    fo.on_network_error = OTC_ON_NETWORK_ERROR_RAISE;
    CHECK_STATUS(otc_fetch_open(&fo, NULL, NULL, &rel), OTC_E_INVALID_RELEASE);
    CHECK(rel == NULL);
    otc_close(rel);
    free(cache2);
    free(cache);
    return test_done("test_fetch_huge_size");
}
