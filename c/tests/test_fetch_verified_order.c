/* PK04 / C103: while a download replaces data files of a cached release, the
 * old .verified must not vouch for them. If the download stops after some
 * renames, the release directory is not trusted until a new .verified is
 * written (spec 5.4: .verified is written last; a reader trusts a directory
 * only when .verified exists). */
#include "otc_test.h"

int main(void)
{
    char *cache = test_tmpdir(), base[512], path[4096], *dir, *vpath, *text = NULL, *at;
    otc_fetch_options fo;
    otc_error err;
    size_t need, n;
    FILE *f;
    if (!test_server()) { printf("test_fetch_verified_order: skipped (no OTC_TEST_SERVER)\n"); return 0; }
    otc_fetch_options_init(&fo);
    otc_error_init(&err);
    snprintf(base, sizeof base, "%s/good/", test_server());
    fo.cache_dir = cache;
    fo.base_url = base;
    fo.error = &err;
    CHECK_STATUS(otc_fetch_release(&fo, "20991231.2", path, sizeof path, &need), OTC_OK);
    dir = test_join(cache, "v1/releases/20991231.2");
    vpath = test_join(dir, ".verified");
    /* .verified records an older .jsonl (so the download replaces it) ... */
    f = fopen(vpath, "rb");
    if (!f) { perror(vpath); return 2; }
    text = (char *)calloc(1, 1 << 16);
    n = fread(text, 1, (1 << 16) - 1, f);
    fclose(f);
    text[n] = '\0';
    at = strstr(text, "\"OTC_20991231.2.jsonl\"");
    at = at ? strstr(at, "\"sha256\"") : NULL;
    at = at ? strchr(at + 8, '"') : NULL;
    if (!at) { fprintf(stderr, "unexpected .verified: %s\n", text); return 2; }
    memset(at + 1, '0', 64);
    test_write(dir, ".verified", text);
    /* ... and the .json cannot be put in place (a directory is in the way) */
    snprintf(path, sizeof path, "%s/OTC_20991231.2.json", dir);
    mkdir(path, 0777);
    fo.formats = OTC_FORMAT_JSON;
    CHECK_STATUS(otc_fetch_release(&fo, "20991231.2", path, sizeof path, &need), OTC_E_CACHE);
    CHECK(access(vpath, F_OK) != 0);
    if (access(vpath, F_OK) == 0) fprintf(stderr, "the old .verified still vouches for a replaced .jsonl\n");
    free(text);
    free(vpath);
    free(dir);
    free(cache);
    return test_done("test_fetch_verified_order");
}
