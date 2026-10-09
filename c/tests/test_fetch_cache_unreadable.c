/* PK10 / C51: a cache directory that exists but cannot be listed is a cache
 * error, not "no release is cached". */
#include "otc_test.h"

int main(void)
{
    char *cache = test_tmpdir(), p[4096], path[4096], *ds[4];
    otc_fetch_options fo;
    otc_error err;
    size_t n = 7, need;
    otc_fetch_options_init(&fo);
    otc_error_init(&err);
    fo.cache_dir = cache;
    fo.error = &err;
    fo.offline = true;
    snprintf(p, sizeof p, "%s/v1", cache);
    mkdir(p, 0777);
    snprintf(p, sizeof p, "%s/v1/releases", cache);
    mkdir(p, 0777);
    /* an empty cache is fine */
    CHECK_STATUS(otc_fetch_cached_releases(&fo, ds, 4, &n), OTC_OK);
    CHECK(n == 0);
    CHECK_STATUS(otc_fetch_latest(&fo, path, sizeof path, &need), OTC_E_OFFLINE_UNAVAILABLE);
    /* one that cannot be read is not empty */
    chmod(p, 0000);
    if (test_read_perms_ignored()) {
        chmod(p, 0755);
        free(cache);
        return test_skip("test_fetch_cache_unreadable", "file permissions do not stop this process");
    }
    n = 7;
    CHECK_STATUS(otc_fetch_cached_releases(&fo, ds, 4, &n), OTC_E_CACHE);
    CHECK(n == 0);
    CHECK_STATUS(otc_fetch_prune(&fo, 0, NULL, ds, 4, &n), OTC_E_CACHE);
    CHECK_STATUS(otc_fetch_latest(&fo, path, sizeof path, &need), OTC_E_CACHE);
    chmod(p, 0755);
    free(cache);
    return test_done("test_fetch_cache_unreadable");
}
