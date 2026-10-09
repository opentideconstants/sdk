/* PK01 / C26: a datestamp counter has at most 9 digits (spec 4.2, CR D18).
 * A longer counter from the caller is invalid_argument; from the server's
 * pointer it is invalid_release. Before the fix the counter had no bound, and
 * the cache file names were cut to fit fixed buffers. */
#include "otc_test.h"

int main(void)
{
    char *cache = test_tmpdir(), path[4096], base[512];
    otc_fetch_options fo;
    otc_error err;
    size_t need = 0;
    otc_fetch_options_init(&fo);
    otc_error_init(&err);
    fo.cache_dir = cache;
    fo.error = &err;
    fo.offline = true; /* the caller's datestamp is checked before any network access */
    CHECK_STATUS(otc_fetch_release(&fo, "20991231.1234567890", path, sizeof path, &need), OTC_E_INVALID_ARGUMENT);
    CHECK_STATUS(otc_fetch_release(&fo, "20991231.123456789", path, sizeof path, &need), OTC_E_OFFLINE_UNAVAILABLE);
    if (test_server()) {
        fo.offline = false;
        snprintf(base, sizeof base, "%s/good/", test_server());
        fo.base_url = base;
        fo.on_network_error = OTC_ON_NETWORK_ERROR_RAISE;
        CHECK_STATUS(otc_fetch_latest(&fo, path, sizeof path, &need), OTC_E_INVALID_RELEASE);
        if (err.status != OTC_E_INVALID_RELEASE) fprintf(stderr, "error: %s\n", err.message);
    } else {
        printf("test_fetch_datestamp: no OTC_TEST_SERVER, the pointer part is skipped\n");
    }
    free(cache);
    return test_done("test_fetch_datestamp");
}
