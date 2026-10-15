/* PK01 / C26: a datestamp counter has at most 9 digits (spec 4.2, CR D18).
 * A longer counter from the caller is invalid_argument; from the server's
 * pointer it is invalid_release. Both paths are tested at the boundary: 10
 * digits fail, 9 do not. Before the fix the counter had no bound, and the
 * cache file names were cut to fit fixed buffers. */
#include "otc_test.h"

int main(void)
{
    char *cache = test_tmpdir(), path[4096], base[512];
    otc_fetch_options fo;
    otc_release_info *info = NULL;
    otc_error err;
    size_t need = 0;
    otc_fetch_options_init(&fo);
    otc_error_init(&err);
    fo.cache_dir = cache;
    fo.error = &err;
    fo.offline = true; /* the caller's datestamp is checked before any network access */
    CHECK_STATUS(otc_fetch_release(&fo, "20991231.1234567890", path, sizeof path, &need), OTC_E_INVALID_ARGUMENT);
    CHECK_STATUS(otc_fetch_release(&fo, "20991231.123456789", path, sizeof path, &need), OTC_E_OFFLINE_UNAVAILABLE);
    if (!test_server()) return test_skip("test_fetch_datestamp", "no OTC_TEST_SERVER for the pointer part");
    fo.offline = false;
    fo.on_network_error = OTC_ON_NETWORK_ERROR_RAISE;
    /* the pointer names a release whose counter has 10 digits: invalid_release, and the error says so */
    snprintf(base, sizeof base, "%s/d10/", test_server());
    fo.base_url = base;
    CHECK_STATUS(otc_fetch_latest_info(&fo, &info), OTC_E_INVALID_RELEASE);
    CHECK(info == NULL);
    CHECK(err.status == OTC_E_INVALID_RELEASE && strstr(err.message, "datestamp") != NULL);
    if (err.status != OTC_E_INVALID_RELEASE || !strstr(err.message, "datestamp"))
        fprintf(stderr, "error: %s: %s\n", otc_status_code(err.status), err.message);
    otc_release_info_free(info);
    info = NULL;
    CHECK_STATUS(otc_fetch_latest(&fo, path, sizeof path, &need), OTC_E_INVALID_RELEASE);
    CHECK(err.status == OTC_E_INVALID_RELEASE);
    /* its control: 9 digits are read */
    snprintf(base, sizeof base, "%s/d9/", test_server());
    fo.base_url = base;
    CHECK_STATUS(otc_fetch_latest_info(&fo, &info), OTC_OK);
    if (info) {
        char ds[32] = "";
        CHECK_STATUS(otc_release_info_datestamp(info, ds, sizeof ds, &need), OTC_OK);
        CHECK(!strcmp(ds, "20991231.123456789"));
    }
    otc_release_info_free(info);
    free(cache);
    return test_done("test_fetch_datestamp");
}
