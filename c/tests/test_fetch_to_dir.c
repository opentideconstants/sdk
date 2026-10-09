/* otc_fetch_to_dir (spec 4.3.2).
 * C55: an existing file that cannot be read is OTC_E_IO, not "exists with a
 *      different SHA-256" (file_exists).
 * C54: "latest" on a network error honours on_network_error (CR D22): with
 *      use_cache it writes the newest cached release (two are cached, so
 *      "newest" is tested); with raise it fails, writes nothing and reports
 *      nothing.
 * CR 4c: formats OTC_FORMATS_DEFAULT is jsonl; formats 0 is invalid_argument,
 *      and nothing is written.
 * Before each call *count is a value no call gives. */
#include "otc_test.h"

#include <dirent.h>

/* the number of entries in dir, apart from . and .. */
static int entries(const char *dir)
{
    DIR *d = opendir(dir);
    struct dirent *e;
    int n = 0;
    if (!d) { perror(dir); exit(2); }
    while ((e = readdir(d)) != NULL)
        if (strcmp(e->d_name, ".") != 0 && strcmp(e->d_name, "..") != 0) n++;
    closedir(d);
    return n;
}

/* 1 when paths[0..n) are exactly dir's OTC_<ds>.jsonl, .meta.json and .sha256 (the default format,
 * in any order) */
static int names_release(char **paths, size_t n, const char *dir, const char *ds)
{
    static const char *const ext[3] = {".jsonl", ".meta.json", ".sha256"};
    size_t i, j;
    if (n != 3) return 0;
    for (j = 0; j < 3; j++) {
        char want[4096];
        int found = 0;
        snprintf(want, sizeof want, "%s/OTC_%s%s", dir, ds, ext[j]);
        for (i = 0; i < n; i++)
            if (paths[i] && !strcmp(paths[i], want)) found++;
        if (found != 1) {
            fprintf(stderr, "the paths do not name %s once\n", want);
            return 0;
        }
    }
    return 1;
}

int main(void)
{
    char *cache = test_tmpdir(), *to = test_tmpdir(), base[512], *paths[8], *p;
    otc_fetch_options fo;
    otc_error err;
    size_t n = 0, i;
    if (!test_server()) return test_skip("test_fetch_to_dir", "no OTC_TEST_SERVER");
    otc_fetch_options_init(&fo);
    otc_error_init(&err);
    snprintf(base, sizeof base, "%s/good/", test_server());
    fo.cache_dir = cache;
    fo.base_url = base;
    fo.error = &err;
    memset(paths, 0, sizeof paths);
    /* CR 4c: formats 0 names no format: invalid_argument, and nothing is written */
    n = 99;
    CHECK_STATUS(otc_fetch_to_dir(&fo, "20991231.2", to, 0, false, paths, 8, &n), OTC_E_INVALID_ARGUMENT);
    CHECK(n == 0 && strstr(err.message, "OTC_FORMATS_DEFAULT") != NULL && strstr(err.message, "unknown") == NULL);
    CHECK(entries(to) == 0);
    for (i = 0; i < 8; i++) CHECK(paths[i] == NULL);
    n = 99;
    CHECK_STATUS(otc_fetch_to_dir(&fo, "20991231.2", to, OTC_FORMATS_DEFAULT, false, paths, 8, &n), OTC_OK);
    CHECK(n == 3 && names_release(paths, n, to, "20991231.2"));
    for (i = 0; i < n && i < 8; i++) otc_free(paths[i]);
    /* C55 */
    p = test_join(to, "OTC_20991231.2.jsonl");
    chmod(p, 0000);
    if (!test_read_perms_ignored()) {
        memset(paths, 0, sizeof paths);
        n = 99;
        CHECK_STATUS(otc_fetch_to_dir(&fo, "20991231.2", to, OTC_FORMATS_DEFAULT, false, paths, 8, &n), OTC_E_IO);
        CHECK(n == 0);
        CHECK(strstr(err.file, "OTC_20991231.2.jsonl") != NULL);
        for (i = 0; i < 8; i++) otc_free(paths[i]);
    } else {
        printf("test_fetch_to_dir: the C55 part is skipped (file permissions do not stop this process)\n");
    }
    chmod(p, 0644);
    free(p);
    /* C54 */
    {
        char *to2 = test_tmpdir(), *to3 = test_tmpdir(), path[4096];
        size_t need;
        /* two releases are cached: an older one, then the latest */
        CHECK_STATUS(otc_fetch_release(&fo, "20991231", path, sizeof path, &need), OTC_OK);
        CHECK_STATUS(otc_fetch_latest(&fo, path, sizeof path, &need), OTC_OK);
        fo.base_url = "http://127.0.0.1:9/";   /* the network is down */
        memset(paths, 0, sizeof paths);
        n = 99;
        CHECK_STATUS(otc_fetch_to_dir(&fo, NULL, to2, OTC_FORMATS_DEFAULT, false, paths, 8, &n), OTC_OK);
        CHECK(n == 3 && names_release(paths, n, to2, "20991231.2"));   /* the newest cached release */
        CHECK(entries(to2) == 3);
        for (i = 0; i < n && i < 8; i++) otc_free(paths[i]);
        fo.on_network_error = OTC_ON_NETWORK_ERROR_RAISE;
        memset(paths, 0, sizeof paths);
        n = 99;
        CHECK_STATUS(otc_fetch_to_dir(&fo, NULL, to3, OTC_FORMATS_DEFAULT, false, paths, 8, &n), OTC_E_NETWORK);
        CHECK(n == 0);
        CHECK(entries(to3) == 0);   /* a failure writes nothing there */
        for (i = 0; i < 8; i++) {
            CHECK(paths[i] == NULL);
            otc_free(paths[i]);
        }
        free(to2);
        free(to3);
    }
    free(cache);
    free(to);
    return test_done("test_fetch_to_dir");
}
