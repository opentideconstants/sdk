/* PK11 / C23: a pointer that lists no files still gives a release whose
 * release.files (spec 4.3.1) come from OTC_{D}.sha256, so they are checked:
 * .verified keeps a row for every file the .sha256 lists, each with the
 * .sha256's digest (good/OTC_20991231.2.sha256, the four rows below). */
#include "otc_test.h"

static const char *const WANT[4][2] = {
    {"OTC_20991231.2.json", "3d71bd028039dc06ae9941103566a98e256ef39e1dfbfa09c76afd067473105e"},
    {"OTC_20991231.2.json.gz", "0873f8ce01fa88ed2b796eb16f8172dbcde5758671360d8b698be8bc3c62a6bd"},
    {"OTC_20991231.2.jsonl", "759d6bb9e54684e82c3a007d8970e2ac5e3df19a3c2093f74c3fbc1bd69499b1"},
    {"OTC_20991231.2.meta.json", "f1ceca5d49337f6228594b5d26ec4a0c7b60807d9c774c51784bf5d8ffa41350"},
};

int main(void)
{
    char *cache = test_tmpdir(), base[512];
    otc_fetch_options fo;
    otc_release *rel = NULL;
    otc_error err;
    if (!test_server()) return test_skip("test_fetch_pointer_no_files", "no OTC_TEST_SERVER");
    otc_fetch_options_init(&fo);
    otc_error_init(&err);
    snprintf(base, sizeof base, "%s/good/", test_server());
    fo.cache_dir = cache;
    fo.base_url = base;
    fo.error = &err;
    CHECK_STATUS(otc_fetch_open(&fo, NULL, NULL, &rel), OTC_OK);
    if (rel) {
        size_t i, j, n = otc_release_file_count(rel);
        int seen[4] = {0, 0, 0, 0};
        if (n != 4) fprintf(stderr, "release.files has %lu rows, want the .sha256's 4\n", (unsigned long)n);
        CHECK(n == 4);
        for (i = 0; i < n; i++) {
            const otc_file_info *fi = NULL;
            char name[128] = "", sha[80] = "";
            size_t need;
            int matched = 0;
            CHECK_STATUS(otc_release_file_at(rel, i, &fi), OTC_OK);
            CHECK_STATUS(otc_file_info_name(fi, name, sizeof name, &need), OTC_OK);
            CHECK_STATUS(otc_file_info_sha256(fi, sha, sizeof sha, &need), OTC_OK);
            for (j = 0; j < 4; j++) {
                if (strcmp(name, WANT[j][0]) != 0) continue;
                matched = 1;
                seen[j]++;
                if (strcmp(sha, WANT[j][1]) != 0) fprintf(stderr, "%s: sha256 %s, want %s\n", name, sha, WANT[j][1]);
                CHECK(!strcmp(sha, WANT[j][1]));
            }
            if (!matched) fprintf(stderr, "release.files has a row %s that the .sha256 does not list\n", name);
            CHECK(matched);
        }
        for (j = 0; j < 4; j++) CHECK(seen[j] == 1);
    }
    otc_close(rel);
    free(cache);
    return test_done("test_fetch_pointer_no_files");
}
