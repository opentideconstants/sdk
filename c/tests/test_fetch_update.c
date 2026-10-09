/* PK20 / C24 and CR D27: otc_fetch_update(opts, current, path, len, &needed,
 * &updated). needed gets the path length with its NUL, as for every other
 * string out (spec 4.1); path and len are checked before the download, so a
 * buffer that is too small (or a size query with path NULL and len 0)
 * downloads nothing, and *updated is true only when the new release is in the
 * cache and path names it. */
#include "otc_test.h"

int main(void)
{
    char *cache = test_tmpdir(), base[512], small[16], path[4096], *v;
    otc_fetch_options fo;
    otc_error err;
    bool updated = true;
    size_t needed = 99, size = 0;
    if (!test_server()) { printf("test_fetch_update: skipped (no OTC_TEST_SERVER)\n"); return 0; }
    otc_fetch_options_init(&fo);
    otc_error_init(&err);
    snprintf(base, sizeof base, "%s/good/", test_server());
    fo.cache_dir = cache;
    fo.base_url = base;
    fo.error = &err;
    v = test_join(cache, "v1/releases/20991231.2/.verified");
    CHECK_STATUS(otc_fetch_update(&fo, "20991230", NULL, 64, &needed, &updated), OTC_E_INVALID_ARGUMENT);
    CHECK_STATUS(otc_fetch_update(&fo, "20991230", path, sizeof path, &needed, NULL), OTC_E_INVALID_ARGUMENT);
    /* a size query: path NULL and len 0 report the size and download nothing */
    CHECK_STATUS(otc_fetch_update(&fo, "20991230", NULL, 0, &size, &updated), OTC_E_BUFFER_TOO_SMALL);
    CHECK(!updated);
    CHECK(size > sizeof small);
    CHECK(access(v, F_OK) != 0);
    CHECK_STATUS(otc_fetch_update(&fo, "20991230", small, sizeof small, &needed, &updated), OTC_E_BUFFER_TOO_SMALL);
    CHECK(!updated);
    CHECK(needed == size);
    CHECK(access(v, F_OK) != 0);
    if (access(v, F_OK) == 0) fprintf(stderr, "the release was downloaded although the path cannot be returned\n");
    CHECK_STATUS(otc_fetch_update(&fo, "20991230", path, sizeof path, &needed, &updated), OTC_OK);
    CHECK(updated && strstr(path, "OTC_20991231.2.jsonl") != NULL);
    CHECK(needed == strlen(path) + 1 && needed == size);
    CHECK(access(v, F_OK) == 0);
    /* needed may be NULL, as for every other string out */
    CHECK_STATUS(otc_fetch_update(&fo, "20991230", path, sizeof path, NULL, &updated), OTC_OK);
    CHECK(updated);
    /* no newer release: no path, so needed is 0 */
    CHECK_STATUS(otc_fetch_update(&fo, "20991231.2", path, sizeof path, &needed, &updated), OTC_OK);
    CHECK(!updated && needed == 0 && path[0] == '\0');
    free(v);
    free(cache);
    return test_done("test_fetch_update");
}
