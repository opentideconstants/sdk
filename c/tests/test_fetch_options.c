/* PK07 / C59: a timeout_s that is NaN, negative or infinite is
 * invalid_argument, checked before any network access (spec 4.2, 5.7). 0
 * means the defaults (connect 10 s, read 60 s).
 * D19: a ca_file that does not exist is io, and a base_url or proxy that is
 * not an absolute http(s) URL is invalid_argument, at the first call and
 * before any network access (they never fall back to the cache).
 * C56: when struct_size is too small, the caller's error (whose field is
 * there in every layout) still says why. */
#include "otc_test.h"

#include <math.h>

int main(void)
{
    char *cache = test_tmpdir(), path[4096];
    otc_fetch_options fo;
    otc_error err;
    size_t need;
    static const double bad[] = {-1.0, -0.001};
    size_t i;
    otc_fetch_options_init(&fo);
    otc_error_init(&err);
    fo.cache_dir = cache;
    fo.error = &err;
    fo.offline = true;   /* any network access would be a bug here */
    for (i = 0; i < sizeof bad / sizeof bad[0]; i++) {
        fo.timeout_s = bad[i];
        CHECK_STATUS(otc_fetch_latest(&fo, path, sizeof path, &need), OTC_E_INVALID_ARGUMENT);
    }
    fo.timeout_s = NAN;
    CHECK_STATUS(otc_fetch_latest(&fo, path, sizeof path, &need), OTC_E_INVALID_ARGUMENT);
    fo.timeout_s = INFINITY;
    CHECK_STATUS(otc_fetch_latest(&fo, path, sizeof path, &need), OTC_E_INVALID_ARGUMENT);
    fo.timeout_s = 1e300;   /* too large for the millisecond options of libcurl */
    CHECK_STATUS(otc_fetch_latest(&fo, path, sizeof path, &need), OTC_E_INVALID_ARGUMENT);
    fo.timeout_s = 0;
    CHECK_STATUS(otc_fetch_latest(&fo, path, sizeof path, &need), OTC_E_OFFLINE_UNAVAILABLE);
    fo.timeout_s = 2.5;
    CHECK_STATUS(otc_fetch_latest(&fo, path, sizeof path, &need), OTC_E_OFFLINE_UNAVAILABLE);
    /* D19 */
    fo.timeout_s = 0;
    fo.offline = false;
    fo.on_network_error = OTC_ON_NETWORK_ERROR_USE_CACHE;
    fo.base_url = "http://127.0.0.1:9/";   /* nothing listens there: any request would fail as network */
    fo.ca_file = "/no/such/ca.pem";
    CHECK_STATUS(otc_fetch_latest(&fo, path, sizeof path, &need), OTC_E_IO);
    fo.ca_file = NULL;
    fo.base_url = "ftp://127.0.0.1/";
    CHECK_STATUS(otc_fetch_latest(&fo, path, sizeof path, &need), OTC_E_INVALID_ARGUMENT);
    fo.base_url = "127.0.0.1/good/";
    CHECK_STATUS(otc_fetch_latest(&fo, path, sizeof path, &need), OTC_E_INVALID_ARGUMENT);
    fo.base_url = "http://127.0.0.1:9/";
    fo.proxy = "not a url";
    CHECK_STATUS(otc_fetch_latest(&fo, path, sizeof path, &need), OTC_E_INVALID_ARGUMENT);
    /* C56 */
    {
        otc_fetch_options small;
        otc_error e2;
        otc_fetch_options_init(&small);
        memset(&e2, 0x5A, sizeof e2);
        otc_error_init(&e2);
        small.error = &e2;
        small.struct_size = sizeof small - 1;
        CHECK_STATUS(otc_fetch_latest(&small, path, sizeof path, &need), OTC_E_INVALID_ARGUMENT);
        CHECK(e2.status == OTC_E_INVALID_ARGUMENT && strstr(e2.message, "struct_size") != NULL);
    }
    free(cache);
    return test_done("test_fetch_options");
}
