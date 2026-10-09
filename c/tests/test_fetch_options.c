/* PK07 / C59: a timeout_s that is NaN, negative or infinite is
 * invalid_argument, checked before any network access (spec 4.2, 5.7). 0
 * means the defaults (connect 10 s, read 60 s). */
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
    free(cache);
    return test_done("test_fetch_options");
}
