/* PK02 / C104: a corrupt cached pointer does not stick. When the server
 * answers 304 to the stored ETag but the cached body is not JSON, the
 * library fetches the pointer again without If-None-Match. */
#include "otc_test.h"

int main(void)
{
    char *cache = test_tmpdir(), base[512], *pdir;
    otc_fetch_options fo;
    otc_release_info *info = NULL;
    otc_error err;
    if (!test_server()) { printf("test_fetch_pointer_corrupt: skipped (no OTC_TEST_SERVER)\n"); return 0; }
    otc_fetch_options_init(&fo);
    otc_error_init(&err);
    snprintf(base, sizeof base, "%s/good/", test_server());
    fo.cache_dir = cache;
    fo.base_url = base;
    fo.error = &err;
    CHECK_STATUS(otc_fetch_latest_info(&fo, &info), OTC_OK);
    otc_release_info_free(info);
    info = NULL;
    /* the cached body goes bad; the .etag stays, so the server answers 304 */
    pdir = test_join(cache, "v1/pointer");
    test_write(pdir, "OTC_latest-f1.json", "<html>half-written</html>");
    CHECK_STATUS(otc_fetch_latest_info(&fo, &info), OTC_OK);
    if (err.status != OTC_OK) fprintf(stderr, "error: %s\n", err.message);
    otc_release_info_free(info);
    info = NULL;
    /* and it healed: the next call is a plain 304 again */
    CHECK_STATUS(otc_fetch_latest_info(&fo, &info), OTC_OK);
    otc_release_info_free(info);
    free(pdir);
    free(cache);
    return test_done("test_fetch_pointer_corrupt");
}
