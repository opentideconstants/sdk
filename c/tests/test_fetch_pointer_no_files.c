/* PK11 / C23: a pointer that lists no files still gives a release whose
 * release.files (spec 4.3.1) come from OTC_{D}.sha256, so they are checked:
 * .verified keeps a row for every file the .sha256 lists. */
#include "otc_test.h"

int main(void)
{
    char *cache = test_tmpdir(), base[512];
    otc_fetch_options fo;
    otc_release *rel = NULL;
    otc_error err;
    if (!test_server()) { printf("test_fetch_pointer_no_files: skipped (no OTC_TEST_SERVER)\n"); return 0; }
    otc_fetch_options_init(&fo);
    otc_error_init(&err);
    snprintf(base, sizeof base, "%s/good/", test_server());
    fo.cache_dir = cache;
    fo.base_url = base;
    fo.error = &err;
    CHECK_STATUS(otc_fetch_open(&fo, NULL, NULL, &rel), OTC_OK);
    if (rel) {
        size_t i, n = otc_release_file_count(rel);
        int jsonl = 0;
        CHECK(n == 4);
        for (i = 0; i < n; i++) {
            const otc_file_info *fi = NULL;
            char name[128], sha[80];
            size_t need;
            otc_release_file_at(rel, i, &fi);
            otc_file_info_name(fi, name, sizeof name, &need);
            CHECK_STATUS(otc_file_info_sha256(fi, sha, sizeof sha, &need), OTC_OK);
            if (!strcmp(name, "OTC_20991231.2.jsonl")) jsonl = 1;
        }
        CHECK(jsonl);
        if (n != 4) fprintf(stderr, "release.files has %lu rows\n", (unsigned long)n);
    }
    otc_close(rel);
    free(cache);
    return test_done("test_fetch_pointer_no_files");
}
