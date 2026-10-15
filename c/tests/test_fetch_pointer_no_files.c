/* PK11 / C23, CR3 DR100: a pointer that lists no files. A download of latest
 * lists the pointer entry in release.files (spec 4.3.1), so none. The files it
 * stored are still checked: .verified has a row for each of them (the .jsonl
 * and the .meta.json) with the digest of OTC_{D}.sha256 (good/OTC_20991231.2.sha256),
 * and a cached open lists exactly those rows. */
#include "otc_test.h"

static const char *const WANT[2][2] = {
    {"OTC_20991231.2.jsonl", "84ba5c138d233be93c031bdec7b243caa72d27bbf6a7b3d0df14aa61fe36fab0"},
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
        size_t n = otc_release_file_count(rel);
        CHECK(otc_release_loaded_from(rel) == OTC_LOADED_FROM_DOWNLOAD);
        if (n != 0) fprintf(stderr, "release.files has %lu rows, want the pointer entry's 0\n", (unsigned long)n);
        CHECK(n == 0);
    }
    otc_close(rel);
    rel = NULL;
    fo.offline = true;
    CHECK_STATUS(otc_fetch_open(&fo, NULL, NULL, &rel), OTC_OK);
    if (rel) {
        size_t i, j, n = otc_release_file_count(rel);
        int seen[2] = {0, 0};
        CHECK(otc_release_loaded_from(rel) == OTC_LOADED_FROM_CACHE);
        if (n != 2) fprintf(stderr, "the cached release.files has %lu rows, want the 2 stored files\n", (unsigned long)n);
        CHECK(n == 2);
        for (i = 0; i < n; i++) {
            const otc_file_info *fi = NULL;
            char name[128] = "", sha[80] = "";
            size_t need;
            int matched = 0;
            CHECK_STATUS(otc_release_file_at(rel, i, &fi), OTC_OK);
            CHECK_STATUS(otc_file_info_name(fi, name, sizeof name, &need), OTC_OK);
            CHECK_STATUS(otc_file_info_sha256(fi, sha, sizeof sha, &need), OTC_OK);
            for (j = 0; j < 2; j++) {
                if (strcmp(name, WANT[j][0]) != 0) continue;
                matched = 1;
                seen[j]++;
                if (strcmp(sha, WANT[j][1]) != 0) fprintf(stderr, "%s: sha256 %s, want %s\n", name, sha, WANT[j][1]);
                CHECK(!strcmp(sha, WANT[j][1]));
            }
            if (!matched) fprintf(stderr, "release.files has a row %s that this open did not store\n", name);
            CHECK(matched);
        }
        for (j = 0; j < 2; j++) CHECK(seen[j] == 1);
    }
    otc_close(rel);
    free(cache);
    return test_done("test_fetch_pointer_no_files");
}
