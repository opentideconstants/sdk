/* PK20 / C24 (the part that keeps the signature; D27's needed argument needs
 * a runner change): otc_fetch_update checks path and len before it
 * downloads, so a buffer that is too small downloads nothing, and *updated
 * is true only when the new release is in the cache and path names it. */
#include "otc_test.h"

int main(void)
{
    char *cache = test_tmpdir(), base[512], small[16], path[4096], *v;
    otc_fetch_options fo;
    otc_error err;
    bool updated = true;
    if (!test_server()) { printf("test_fetch_update: skipped (no OTC_TEST_SERVER)\n"); return 0; }
    otc_fetch_options_init(&fo);
    otc_error_init(&err);
    snprintf(base, sizeof base, "%s/good/", test_server());
    fo.cache_dir = cache;
    fo.base_url = base;
    fo.error = &err;
    v = test_join(cache, "v1/releases/20991231.2/.verified");
    CHECK_STATUS(otc_fetch_update(&fo, "20991230", NULL, 64, &updated), OTC_E_INVALID_ARGUMENT);
    CHECK_STATUS(otc_fetch_update(&fo, "20991230", small, sizeof small, &updated), OTC_E_BUFFER_TOO_SMALL);
    CHECK(!updated);
    CHECK(access(v, F_OK) != 0);
    if (access(v, F_OK) == 0) fprintf(stderr, "the release was downloaded although the path cannot be returned\n");
    CHECK_STATUS(otc_fetch_update(&fo, "20991230", path, sizeof path, &updated), OTC_OK);
    CHECK(updated && strstr(path, "OTC_20991231.2.jsonl") != NULL);
    CHECK(access(v, F_OK) == 0);
    CHECK_STATUS(otc_fetch_update(&fo, "20991231.2", path, sizeof path, &updated), OTC_OK);
    CHECK(!updated);
    free(v);
    free(cache);
    return test_done("test_fetch_update");
}
