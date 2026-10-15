/* R2-108: when curl_global_init fails, only the calls that need the network fail,
 * with OTC_E_NETWORK. An offline call, and a call that only reads the cache, give
 * their own answer: before, every otc_fetch_* call failed with OTC_E_NETWORK.
 *
 * This program defines curl_global_init itself. The library is linked statically
 * (CMakeLists.txt), so the library's call binds to this definition, which fails as
 * a real libcurl does when it cannot initialise (CURLE_FAILED_INIT). */
#include "otc_test.h"

int curl_global_init(long flags);
int curl_global_init(long flags)
{
    (void)flags;
    return 2;   /* CURLE_FAILED_INIT */
}

int main(void)
{
    char *cache = test_tmpdir(), path[4096], base[1024], *ds[4];
    otc_fetch_options fo;
    otc_error err;
    size_t need = 0, n = 99;
    otc_fetch_options_init(&fo);
    otc_error_init(&err);
    fo.cache_dir = cache;
    fo.error = &err;
    /* offline, with an empty cache: offline_unavailable, as with a working libcurl */
    fo.offline = true;
    CHECK_STATUS(otc_fetch_latest(&fo, path, sizeof path, &need), OTC_E_OFFLINE_UNAVAILABLE);
    /* a call that only reads the cache */
    CHECK_STATUS(otc_fetch_cached_releases(&fo, ds, 4, &n), OTC_OK);
    CHECK(n == 0);
    /* a call that needs the network: network, and the message says why */
    fo.offline = false;
    if (!test_server()) return test_done("test_fetch_curl_init_fail");
    snprintf(base, sizeof base, "%s/good/", test_server());
    fo.base_url = base;
    fo.on_network_error = OTC_ON_NETWORK_ERROR_RAISE;
    CHECK_STATUS(otc_fetch_latest(&fo, path, sizeof path, &need), OTC_E_NETWORK);
    CHECK(strstr(err.message, "curl_global_init") != NULL);
    free(cache);
    return test_done("test_fetch_curl_init_fail");
}
