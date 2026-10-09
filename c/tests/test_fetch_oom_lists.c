/* PK04 / C28: otc_fetch_cached_releases and otc_fetch_prune under out of
 * memory. Every allocation is made to fail in turn. A failed call hands the
 * caller nothing it must free (cached_releases), or exactly the entries it
 * reports (prune: *count names the releases removed), and nothing leaks. */
#include "otc_test.h"
#include "otc_oom.h"

#include <errno.h>

static void mkrel(const char *cache, const char *ds)
{
    char p[4096], v[4200];
    FILE *f;
    snprintf(p, sizeof p, "%s/v1", cache);
    mkdir(p, 0777);
    snprintf(p, sizeof p, "%s/v1/releases", cache);
    mkdir(p, 0777);
    snprintf(p, sizeof p, "%s/v1/releases/%s", cache, ds);
    if (mkdir(p, 0777) != 0 && errno != EEXIST) { perror(p); exit(2); }
    snprintf(v, sizeof v, "%s/.verified", p);
    f = fopen(v, "wb");
    if (!f) { perror(v); exit(2); }
    fputs("{\"files\":{}}", f);
    fclose(f);
}

int main(void)
{
    char cache[4096];
    const char *tmp = getenv("TMPDIR");
    long k, base;
    int runs = 0;
    otc_fetch_options fo;
    otc_error err;
    snprintf(cache, sizeof cache, "%s/otc-oom-XXXXXX", tmp && tmp[0] ? tmp : "/tmp");
    if (!mkdtemp(cache)) return 2;
    printf("oom: start\n");   /* stdout's buffer is allocated before the counts start */
    otc_fetch_options_init(&fo);
    otc_error_init(&err);
    fo.cache_dir = cache;
    fo.error = &err;
    fo.offline = true;
    mkrel(cache, "20990101");
    mkrel(cache, "20990102");
    mkrel(cache, "20990103");
    (void)otc_fetch_cached_releases(&fo, NULL, 0, &(size_t){0});   /* one-time init outside the counts */

    for (k = 1; ; k++) {
        char *out[8];
        size_t n = 77, i;
        otc_status st;
        memset(out, 0, sizeof out);
        base = oom_live;
        oom_arm(k);
        st = otc_fetch_cached_releases(&fo, out, 8, &n);
        oom_disarm();
        if (st == OTC_OK) {
            /* a .verified whose parse ran out of memory reads as "not verified" (cJSON does
             * not tell the two apart), so a run with a failure may list fewer */
            CHECK(oom_failed ? n <= 3 : n == 3);
        } else {
            if (st != OTC_E_NOMEM) fprintf(stderr, "cached_releases, allocation %ld fails: %s (%s)\n", k, otc_status_code(st), err.message);
            CHECK(st == OTC_E_NOMEM);
            CHECK(n == 0);
            for (i = 0; i < 8; i++) {
                if (out[i]) fprintf(stderr, "cached_releases, allocation %ld fails: out[%lu] is set, count %lu\n", k,
                                    (unsigned long)i, (unsigned long)n);
                CHECK(out[i] == NULL);
            }
        }
        for (i = 0; i < 8; i++) otc_free(out[i]);
        if (oom_live != base) fprintf(stderr, "cached_releases, allocation %ld fails: %ld blocks leak\n", k, oom_live - base);
        CHECK(oom_live == base);
        runs++;
        if (!oom_failed) break;
    }

    for (k = 1; ; k++) {
        char *out[8], p[4200];
        size_t n = 77, i, set = 0;
        otc_status st;
        mkrel(cache, "20990101");
        mkrel(cache, "20990102");
        mkrel(cache, "20990103");
        memset(out, 0, sizeof out);
        base = oom_live;
        oom_arm(k);
        st = otc_fetch_prune(&fo, 1, NULL, out, 8, &n);
        oom_disarm();
        if (st != OTC_OK && st != OTC_E_NOMEM) fprintf(stderr, "prune, allocation %ld fails: %s (%s)\n", k, otc_status_code(st), err.message);
        CHECK(st == OTC_OK || st == OTC_E_NOMEM);
        for (i = 0; i < 8; i++) if (out[i]) set++;
        CHECK(set <= n);
        /* every release reported as removed is gone */
        for (i = 0; i < n && i < 8; i++) {
            if (!out[i]) continue;
            snprintf(p, sizeof p, "%s/v1/releases/%s", cache, out[i]);
            CHECK(access(p, F_OK) != 0);
        }
        for (i = 0; i < 8; i++) otc_free(out[i]);
        if (oom_live != base) fprintf(stderr, "prune, allocation %ld fails: %ld blocks leak\n", k, oom_live - base);
        CHECK(oom_live == base);
        runs++;
        if (!oom_failed) break;
    }
    printf("oom: %d runs\n", runs);
    return test_done("test_fetch_oom_lists");
}
