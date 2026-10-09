/* PK07 / C59: a timeout_s that is NaN, negative or infinite is
 * invalid_argument, checked before any network access (spec 4.2, 5.7).
 * CR 4c: OTC_TIMEOUT_DEFAULT (what otc_fetch_options_init sets) means the
 * defaults (connect 10 s, read 60 s), and an explicit 0 is invalid_argument;
 * OTC_FORMATS_DEFAULT means the default formats, and 0 (no format) is
 * invalid_argument. The messages say what is wrong (not NaN, not unknown bits).
 * D19: a ca_file that does not exist is io, and a base_url or proxy that is
 * not an absolute http(s) URL is invalid_argument, at the first call and
 * before any network access (they never fall back to the cache).
 * D15 (C side of R69): OPENTIDECONSTANTS_OFFLINE is on for 1, true, yes and
 * on, without regard to case and after trimming spaces.
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
    /* CR2 DR19: from 0.001 to 1e6 s; below 1 ms the libcurl options would round to 0, "no limit" */
    static const double bad[] = {-2.0, -0.001, 0.0001, 0.000999, 1.0e6 + 1, 1.0e7};
    size_t i;
    unsetenv("OPENTIDECONSTANTS_OFFLINE");
    otc_fetch_options_init(&fo);
    CHECK(fo.timeout_s == OTC_TIMEOUT_DEFAULT && fo.formats == OTC_FORMATS_DEFAULT);
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
    /* too small for them: 0.1 ms would be CONNECTTIMEOUT_MS 0 (libcurl's 300 s) and no read timeout */
    fo.timeout_s = 0.0001;
    {
        otc_status st = otc_fetch_latest(&fo, path, sizeof path, &need);
        if (st != OTC_E_INVALID_ARGUMENT) fprintf(stderr, "timeout_s 0.0001: %s, want invalid_argument\n", otc_status_code(st));
        PENDING("PK-R2-13", st == OTC_E_INVALID_ARGUMENT);
    }
    /* CR 4c */
    fo.timeout_s = 0;
    CHECK_STATUS(otc_fetch_latest(&fo, path, sizeof path, &need), OTC_E_INVALID_ARGUMENT);
    CHECK(strstr(err.message, "timeout_s") != NULL && strstr(err.message, "OTC_TIMEOUT_DEFAULT") != NULL);
    CHECK(strstr(err.message, "NaN") == NULL && strstr(err.message, "0 (the defaults)") == NULL);
    fo.timeout_s = OTC_TIMEOUT_DEFAULT;
    CHECK_STATUS(otc_fetch_latest(&fo, path, sizeof path, &need), OTC_E_OFFLINE_UNAVAILABLE);
    fo.formats = 0;
    CHECK_STATUS(otc_fetch_latest(&fo, path, sizeof path, &need), OTC_E_INVALID_ARGUMENT);
    CHECK(strstr(err.message, "formats") != NULL && strstr(err.message, "OTC_FORMATS_DEFAULT") != NULL);
    CHECK(strstr(err.message, "unknown") == NULL);
    fo.formats = OTC_FORMAT_OTHER;
    CHECK_STATUS(otc_fetch_latest(&fo, path, sizeof path, &need), OTC_E_INVALID_ARGUMENT);
    fo.formats = OTC_FORMATS_DEFAULT;
    CHECK_STATUS(otc_fetch_latest(&fo, path, sizeof path, &need), OTC_E_OFFLINE_UNAVAILABLE);
    fo.timeout_s = 2.5;
    CHECK_STATUS(otc_fetch_latest(&fo, path, sizeof path, &need), OTC_E_OFFLINE_UNAVAILABLE);
    fo.timeout_s = 0.001;   /* the bounds are valid (CR2 DR19) */
    CHECK_STATUS(otc_fetch_latest(&fo, path, sizeof path, &need), OTC_E_OFFLINE_UNAVAILABLE);
    fo.timeout_s = 1.0e6;
    CHECK_STATUS(otc_fetch_latest(&fo, path, sizeof path, &need), OTC_E_OFFLINE_UNAVAILABLE);
    /* D19 */
    fo.timeout_s = OTC_TIMEOUT_DEFAULT;
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
    /* D15 */
    {
        static const char *const on[] = {"1", "true", "TRUE", " yes ", "On", NULL}, *const off[] = {"0", "no", "", "2", NULL};
        size_t k;
        otc_fetch_options e;
        otc_fetch_options_init(&e);
        e.cache_dir = cache;
        e.base_url = "http://127.0.0.1:9/";
        e.on_network_error = OTC_ON_NETWORK_ERROR_RAISE;
        for (k = 0; on[k]; k++) {
            setenv("OPENTIDECONSTANTS_OFFLINE", on[k], 1);
            CHECK_STATUS(otc_fetch_latest(&e, path, sizeof path, &need), OTC_E_OFFLINE_UNAVAILABLE);
        }
        for (k = 0; off[k]; k++) {
            setenv("OPENTIDECONSTANTS_OFFLINE", off[k], 1);
            CHECK_STATUS(otc_fetch_latest(&e, path, sizeof path, &need), OTC_E_NETWORK);
        }
        unsetenv("OPENTIDECONSTANTS_OFFLINE");
    }
    /* C56 */
    {
        otc_fetch_options small;
        otc_error e2;
        otc_fetch_options_init(&small);
        otc_error_init(&e2);
        small.error = &e2;
        small.struct_size = sizeof small - 1;
        CHECK_STATUS(otc_fetch_latest(&small, path, sizeof path, &need), OTC_E_INVALID_ARGUMENT);
        CHECK(e2.status == OTC_E_INVALID_ARGUMENT && strstr(e2.message, "struct_size") != NULL);
    }
    free(cache);
    return test_done("test_fetch_options");
}
