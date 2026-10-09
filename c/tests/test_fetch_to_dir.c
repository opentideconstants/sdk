/* otc_fetch_to_dir (spec 4.3.2).
 * C55: an existing file that cannot be read is OTC_E_IO, not "exists with a
 *      different SHA-256" (file_exists).
 * C54: "latest" on a network error honours on_network_error (CR D22): with
 *      use_cache it writes the newest cached release; with raise it fails.
 * CR 4c: formats OTC_FORMATS_DEFAULT is jsonl; formats 0 is invalid_argument.
 * CR2 DR17: the renames are all or nothing. A directory where the .meta.json
 *      goes makes its rename fail after the .jsonl (overwrite: its original
 *      is set aside) was renamed in; the original .jsonl comes back, no
 *      temporary file is left, and nothing is reported. */
#include "otc_test.h"

#include <dirent.h>

static int tmp_left(const char *dir)
{
    DIR *d = opendir(dir);
    struct dirent *e;
    int n = 0;
    if (!d) return -1;
    while ((e = readdir(d)) != NULL) if (!strncmp(e->d_name, ".tmp-", 5)) n++;
    closedir(d);
    return n;
}

int main(void)
{
    char *cache = test_tmpdir(), *to = test_tmpdir(), base[512], *paths[8], *p;
    otc_fetch_options fo;
    otc_error err;
    size_t n = 0, i;
    if (!test_server()) { printf("test_fetch_to_dir: skipped (no OTC_TEST_SERVER)\n"); return 0; }
    otc_fetch_options_init(&fo);
    otc_error_init(&err);
    snprintf(base, sizeof base, "%s/good/", test_server());
    fo.cache_dir = cache;
    fo.base_url = base;
    fo.error = &err;
    memset(paths, 0, sizeof paths);
    /* CR 4c: formats 0 names no format: invalid_argument, and nothing is written */
    CHECK_STATUS(otc_fetch_to_dir(&fo, "20991231.2", to, 0, false, paths, 8, &n), OTC_E_INVALID_ARGUMENT);
    CHECK(n == 0 && strstr(err.message, "OTC_FORMATS_DEFAULT") != NULL && strstr(err.message, "unknown") == NULL);
    CHECK_STATUS(otc_fetch_to_dir(&fo, "20991231.2", to, OTC_FORMATS_DEFAULT, false, paths, 8, &n), OTC_OK);
    CHECK(n == 3);
    for (i = 0; i < n && i < 8; i++) otc_free(paths[i]);
    /* C55 */
    p = test_join(to, "OTC_20991231.2.jsonl");
    chmod(p, 0000);
    if (access(p, R_OK) != 0) {
        memset(paths, 0, sizeof paths);
        CHECK_STATUS(otc_fetch_to_dir(&fo, "20991231.2", to, OTC_FORMATS_DEFAULT, false, paths, 8, &n), OTC_E_IO);
        CHECK(strstr(err.file, "OTC_20991231.2.jsonl") != NULL);
        for (i = 0; i < 8; i++) otc_free(paths[i]);
    } else {
        printf("test_fetch_to_dir: the C55 part is skipped (running as root)\n");
    }
    chmod(p, 0644);
    free(p);
    /* C54 */
    {
        char *to2 = test_tmpdir(), *to3 = test_tmpdir(), path[4096];
        size_t need;
        CHECK_STATUS(otc_fetch_latest(&fo, path, sizeof path, &need), OTC_OK);   /* the release is cached */
        fo.base_url = "http://127.0.0.1:9/";   /* the network is down */
        memset(paths, 0, sizeof paths);
        CHECK_STATUS(otc_fetch_to_dir(&fo, NULL, to2, OTC_FORMATS_DEFAULT, false, paths, 8, &n), OTC_OK);
        CHECK(n == 3);
        for (i = 0; i < n && i < 8; i++) otc_free(paths[i]);
        fo.on_network_error = OTC_ON_NETWORK_ERROR_RAISE;
        memset(paths, 0, sizeof paths);
        CHECK_STATUS(otc_fetch_to_dir(&fo, NULL, to3, OTC_FORMATS_DEFAULT, false, paths, 8, &n), OTC_E_NETWORK);
        free(to2);
        free(to3);
    }
    /* CR2 DR17 */
    {
        static const char changed[] = "changed jsonl";
        char *jl = test_join(to, "OTC_20991231.2.jsonl"), *meta = test_join(to, "OTC_20991231.2.meta.json"), got[64];
        FILE *f = fopen(jl, "wb");
        size_t len;
        fo.base_url = base;
        fo.on_network_error = OTC_ON_NETWORK_ERROR_USE_CACHE;
        CHECK(f != NULL);
        if (f) { fputs(changed, f); fclose(f); }
        CHECK(unlink(meta) == 0 && mkdir(meta, 0777) == 0);
        memset(paths, 0, sizeof paths);
        n = 77;
        CHECK_STATUS(otc_fetch_to_dir(&fo, "20991231.2", to, OTC_FORMATS_DEFAULT, true, paths, 8, &n), OTC_E_IO);
        CHECK(n == 0 && paths[0] == NULL);
        CHECK(strstr(err.file, "OTC_20991231.2.meta.json") != NULL);
        f = fopen(jl, "rb");
        len = f ? fread(got, 1, sizeof got - 1, f) : 0;
        if (f) fclose(f);
        got[len] = '\0';
        if (strcmp(got, changed) != 0) fprintf(stderr, "DR17: the original .jsonl was not restored (it has %lu bytes)\n", (unsigned long)len);
        CHECK(strcmp(got, changed) == 0);
        CHECK(tmp_left(to) == 0);
        rmdir(meta);
        free(jl);
        free(meta);
    }
    free(cache);
    free(to);
    return test_done("test_fetch_to_dir");
}
