/* PK12 / C27: a size in the pointer that is not a whole number in range
 * (1e300, -5.5) is read as unknown, not cast to int64_t (undefined
 * behaviour; UBSan reports it). The files are still checked by SHA-256. */
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
    CHECK_STATUS(otc_fetch_latest_info(&fo, &info), OTC_OK);
    if (info) {
        size_t i;
        for (i = 0; i < otc_release_info_file_count(info); i++) {
            const otc_file_info *fi = NULL;
            otc_release_info_file_at(info, i, &fi);
            CHECK(otc_file_info_size(fi) >= -1);
        }
    }
    otc_release_info_free(info);
    CHECK_STATUS(otc_fetch_open(&fo, NULL, NULL, &rel), OTC_OK);
    otc_close(rel);
    free(cache);
    return test_done("test_fetch_huge_size");
}
