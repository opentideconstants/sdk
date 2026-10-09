/* PK12 / C27: a size in the pointer that is not a whole number in range
 * (1e300, -5.5) is read as unknown (-1), not cast to int64_t (undefined
 * behaviour; UBSan reports it); the other sizes are read as they are. The
 * files are still checked by SHA-256: a .jsonl of unknown size whose bytes
 * are another file's fails its check (the /wrongbody/ rules). */
#include "otc_test.h"

/* the pointer's rows (good/OTC_latest-f1.json), by name, and the size each must read as */
static const struct { const char *name; long long size; } WANT[5] = {
    {"OTC_20991231.2.json", 29814},
    {"OTC_20991231.2.json.gz", 4474},
    {"OTC_20991231.2.jsonl", -1},        /* 1e300 */
    {"OTC_20991231.2.meta.json", -1},    /* -5.5 */
    {"OTC_20991231.2.sha256", 353},
};

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
    CHECK_STATUS(otc_fetch_latest_info(&fo, &info), OTC_OK);
    if (info) {
        size_t i, j, n = otc_release_info_file_count(info);
        int seen[5] = {0, 0, 0, 0, 0};
        CHECK(n == 5);
        for (i = 0; i < n; i++) {
            const otc_file_info *fi = NULL;
            char name[128] = "";
            size_t need;
            CHECK_STATUS(otc_release_info_file_at(info, i, &fi), OTC_OK);
            CHECK_STATUS(otc_file_info_name(fi, name, sizeof name, &need), OTC_OK);
            for (j = 0; j < 5; j++) {
                if (strcmp(name, WANT[j].name) != 0) continue;
                seen[j]++;
                if (otc_file_info_size(fi) != WANT[j].size)
                    fprintf(stderr, "%s: size %lld, want %lld\n", name, (long long)otc_file_info_size(fi), WANT[j].size);
                CHECK(otc_file_info_size(fi) == WANT[j].size);
            }
        }
        for (j = 0; j < 5; j++) CHECK(seen[j] == 1);
    }
    otc_release_info_free(info);
    CHECK_STATUS(otc_fetch_open(&fo, NULL, NULL, &rel), OTC_OK);
    otc_close(rel);
    rel = NULL;
    /* the size is unknown, so only the SHA-256 can catch the wrong bytes */
    snprintf(base, sizeof base, "%s/wrongbody/", test_server());
    fo.cache_dir = cache2;
    fo.base_url = base;
    fo.on_network_error = OTC_ON_NETWORK_ERROR_RAISE;
    CHECK_STATUS(otc_fetch_open(&fo, NULL, NULL, &rel), OTC_E_CHECKSUM);
    CHECK(rel == NULL);
    otc_close(rel);
    free(cache2);
    free(cache);
    return test_done("test_fetch_huge_size");
}
