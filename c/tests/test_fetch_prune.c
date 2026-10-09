/* PK04 / C20, C28, C49: otc_fetch_prune removes only the release directories
 * themselves (a symlink inside is unlinked, never followed), reports only
 * what it removed, raises OTC_E_CACHE when a removal fails (naming the
 * releases removed before it, and leaving no lock behind), and leaves a
 * release alone while another process holds its .lock. */
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
    char *cache = test_tmpdir(), *outside = test_tmpdir(), p[4200], stuck[4000], *removed[8];
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

    /* 2. a release that cannot be removed whole (C49): its lock is taken and its .verified goes, so
     *    the removal itself fails (a 0555 subdirectory holding a file). A newer candidate before it
     *    in the order is removed first: OTC_E_CACHE, and *count and removed name only that one.
     *    (When permissions do not stop this process, the subdirectory can be emptied: skipped.) */
    mkrel(cache, "20990103");
    mkrel(cache, "20990104");
    snprintf(stuck, sizeof stuck, "%s/v1/releases/20990102/stuck", cache);
    if (mkdir(stuck, 0777) != 0) { perror(stuck); return 2; }
    test_write(stuck, "file", "x\n");
    if (!test_write_perms_ignored()) {
        test_chmod(stuck, 0555);
        memset(removed, 0, sizeof removed);
        n = 99;
        err.message[0] = '\0';
        CHECK_STATUS(otc_fetch_prune(&fo, 1, NULL, removed, 8, &n), OTC_E_CACHE);
        CHECK(n == 1 && removed[0] && !strcmp(removed[0], "20990103"));
        for (i = 1; i < 8; i++) CHECK(removed[i] == NULL);
        for (i = 0; i < 8; i++) otc_free(removed[i]);
        /* the failure is the removal's, not the lock's */
        CHECK(strstr(err.message, "cannot remove the cached release 20990102") != NULL);
        if (!strstr(err.message, "cannot remove the cached release 20990102")) fprintf(stderr, "message: %s\n", err.message);
        snprintf(p, sizeof p, "%s/v1/releases/20990103", cache);
        CHECK(!exists(p));
        snprintf(p, sizeof p, "%s/v1/releases/20990102/.verified", cache);
        CHECK(!exists(p));   /* readers stopped trusting it first: it is no longer listed */
        snprintf(p, sizeof p, "%s/v1/releases/20990102/.lock", cache);
        CHECK(!exists(p));   /* and no lock is left behind */
        snprintf(p, sizeof p, "%s/v1/releases/20990104/.verified", cache);
        CHECK(exists(p));    /* the newest is kept */
        test_chmod(stuck, 0755);
    } else {
        printf("test_fetch_prune: part 2 skipped (file permissions do not stop this process)\n");
    }
    snprintf(p, sizeof p, "%s/file", stuck);
    if (unlink(p) != 0 || rmdir(stuck) != 0) { perror(stuck); return 2; }

    /* 3. a release whose .lock is held (a download or index build runs) is left alone; once the
     *    lock is gone, the same prune removes it (so the first result is the lock's doing) */
    mkrel(cache, "20990102");
    snprintf(p, sizeof p, "%s/v1/releases/20990102/.lock", cache);
    if (mkdir(p, 0777) != 0) { perror(p); return 2; }
    memset(removed, 0, sizeof removed);
    n = 99;
    CHECK_STATUS(otc_fetch_prune(&fo, 1, NULL, removed, 8, &n), OTC_OK);
    CHECK(n == 0 && removed[0] == NULL);
    snprintf(p, sizeof p, "%s/v1/releases/20990102/.verified", cache);
    CHECK(exists(p));
    snprintf(p, sizeof p, "%s/v1/releases/20990102/.lock", cache);
    CHECK(exists(p));   /* the other process's lock is left as it was */
    if (rmdir(p) != 0) { perror(p); return 2; }
    memset(removed, 0, sizeof removed);
    n = 99;
    CHECK_STATUS(otc_fetch_prune(&fo, 1, NULL, removed, 8, &n), OTC_OK);
    CHECK(n == 1 && removed[0] && !strcmp(removed[0], "20990102"));
    for (i = 0; i < 8; i++) otc_free(removed[i]);
    free(cache);
    free(outside);
    return test_done("test_fetch_prune");
}
