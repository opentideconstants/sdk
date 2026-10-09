/* PK04 / C20, C28, C49: otc_fetch_prune removes only the release directories
 * themselves (a symlink inside is unlinked, never followed), reports only
 * what it removed, and raises OTC_E_CACHE when a removal fails. */
#include "otc_test.h"

#include <errno.h>

static void mkrel(const char *cache, const char *ds)
{
    char p[4096];
    snprintf(p, sizeof p, "%s/v1", cache);
    mkdir(p, 0777);
    snprintf(p, sizeof p, "%s/v1/releases", cache);
    mkdir(p, 0777);
    snprintf(p, sizeof p, "%s/v1/releases/%s", cache, ds);
    if (mkdir(p, 0777) != 0 && errno != EEXIST) { perror(p); exit(2); }
    test_write(p, ".verified", "{\"files\":{}}");
    test_write(p, "OTC_x.jsonl", "{}\n");
}

static int exists(const char *p)
{
    struct stat sb;
    return lstat(p, &sb) == 0;
}

int main(void)
{
    char *cache = test_tmpdir(), *outside = test_tmpdir(), p[4096], *removed[8];
    otc_fetch_options fo;
    otc_error err;
    size_t n = 0, i;
    otc_fetch_options_init(&fo);
    otc_error_init(&err);
    fo.cache_dir = cache;
    fo.error = &err;
    fo.offline = true;

    /* 1. a symlink to a folder outside the cache, inside a release that prune removes */
    mkrel(cache, "20990101");
    mkrel(cache, "20990102");
    test_write(outside, "precious.txt", "keep me\n");
    snprintf(p, sizeof p, "%s/v1/releases/20990101/link", cache);
    if (symlink(outside, p) != 0) { perror("symlink"); return 2; }
    memset(removed, 0, sizeof removed);
    CHECK_STATUS(otc_fetch_prune(&fo, 1, NULL, removed, 8, &n), OTC_OK);
    CHECK(n == 1 && removed[0] && !strcmp(removed[0], "20990101"));
    for (i = 0; i < n && i < 8; i++) otc_free(removed[i]);
    snprintf(p, sizeof p, "%s/precious.txt", outside);
    CHECK(exists(p));
    if (!exists(p)) fprintf(stderr, "prune followed the symlink and deleted %s\n", p);
    snprintf(p, sizeof p, "%s/v1/releases/20990101", cache);
    CHECK(!exists(p));

    /* 2. a release directory that cannot be removed: cache error, not reported as removed */
    mkrel(cache, "20990103");
    snprintf(p, sizeof p, "%s/v1/releases/20990102", cache);
    chmod(p, 0555);
    memset(removed, 0, sizeof removed);
    n = 99;
    CHECK_STATUS(otc_fetch_prune(&fo, 1, NULL, removed, 8, &n), OTC_E_CACHE);
    CHECK(n == 0);
    for (i = 0; i < 8; i++) CHECK(removed[i] == NULL);
    chmod(p, 0755);
    snprintf(p, sizeof p, "%s/v1/releases/20990102/.verified", cache);
    CHECK(exists(p));

    free(cache);
    free(outside);
    return test_done("test_fetch_prune");
}
