/* PK04 / C28: otc_fetch_cached_releases and otc_fetch_prune under out of
 * memory. Every allocation is made to fail in turn. Each call gives OTC_OK or
 * OTC_E_NOMEM. A failed call hands the caller nothing it must free
 * (cached_releases), or exactly the entries it reports (prune: *count names
 * the releases removed, each one by name, and every release it removed is
 * named), and nothing leaks. The run with no failure gives the whole answer.
 * Known library defects are PENDING, each only in the form it has today:
 *  PK-R2-23  a .verified whose parse ran out of memory (a cJSON allocation)
 *            reads as "not verified", so the call gives OK with fewer releases
 *  PK-R2-03  prune removes a release and then cannot allocate its name: it is
 *            counted, but its slot is NULL (R2-025) */
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

static long g_unverified, g_holes;

int main(void)
{
    char cache[4096];
    const char *tmp = getenv("TMPDIR");
    long k, base, injected;
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
    {   /* and one prune, so the C library's own lazy state (glibc reads the time zone once,
         * for the lock's owner.json) is in place before the counts start */
        char *w[4] = {0};
        size_t wn = 0, wi;
        mkrel(cache, "20980101");
        (void)otc_fetch_prune(&fo, 3, NULL, w, 4, &wn);
        for (wi = 0; wi < 4; wi++) otc_free(w[wi]);
    }

    oom_hook_cjson();
    for (k = 1, injected = 0; k <= OOM_MAX_RUNS; k++) {
        char *out[8];
        size_t n = 77, i;
        otc_status st;
        memset(out, 0, sizeof out);
        base = oom_live;
        oom_arm(k);
        st = otc_fetch_cached_releases(&fo, out, 8, &n);
        oom_disarm();
        if (oom_failed) injected++;
        if (st == OTC_OK) {
            CHECK(n <= 3);
            for (i = 0; i < 8; i++) CHECK(i < n ? out[i] != NULL : out[i] == NULL);
            for (i = 0; i < n && i < 8; i++)
                if (out[i]) CHECK(!strcmp(out[i], i == 0 ? "20990103" : i == 1 ? "20990102" : "20990101") || n < 3);
            if (!oom_failed) {
                CHECK(n == 3);
            } else if (n < 3) {
                if (oom_cjson_failed) g_unverified++;
                else {
                    fprintf(stderr, "cached_releases, allocation %ld fails: ok with %lu of 3 releases\n", k, (unsigned long)n);
                    CHECK(0);
                }
            }
        } else {
            if (st != OTC_E_NOMEM) fprintf(stderr, "cached_releases, allocation %ld fails: %s (%s)\n", k, otc_status_code(st), err.message);
            CHECK(oom_failed);
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
    CHECK(oom_loop_end("cached_releases", k, injected));

    /* keep 1: 20990103 stays, 20990102 and 20990101 go */
    for (k = 1, injected = 0; k <= OOM_MAX_RUNS; k++) {
        static const char *const cand[2] = {"20990101", "20990102"};
        char *out[8], p[4200];
        size_t n = 77, i, j, holes = 0, removed = 0, unreported = 0;
        otc_status st;
        mkrel(cache, "20990101");
        mkrel(cache, "20990102");
        mkrel(cache, "20990103");
        memset(out, 0, sizeof out);
        err.message[0] = '\0';
        base = oom_live;
        oom_arm(k);
        st = otc_fetch_prune(&fo, 1, NULL, out, 8, &n);
        oom_disarm();
        if (oom_failed) injected++;
        if (st != OTC_OK && st != OTC_E_NOMEM) fprintf(stderr, "prune, allocation %ld fails: %s (%s)\n", k, otc_status_code(st), err.message);
        CHECK(st == OTC_OK || st == OTC_E_NOMEM);
        CHECK(st == OTC_OK || oom_failed);
        CHECK(n <= 2);   /* two candidates; also: *count was written (it was 77) */
        for (i = n < 8 ? n : 8; i < 8; i++) CHECK(out[i] == NULL);
        /* every release reported as removed is a candidate, is named once, and is gone */
        for (i = 0; i < n && i < 8; i++) {
            if (!out[i]) { holes++; continue; }
            CHECK(!strcmp(out[i], cand[0]) || !strcmp(out[i], cand[1]));
            for (j = 0; j < i; j++) CHECK(!out[j] || strcmp(out[i], out[j]) != 0);
            snprintf(p, sizeof p, "%s/v1/releases/%s", cache, out[i]);
            CHECK(access(p, F_OK) != 0);
        }
        /* and every candidate that is gone was reported */
        for (j = 0; j < 2; j++) {
            int reported = 0;
            snprintf(p, sizeof p, "%s/v1/releases/%s", cache, cand[j]);
            for (i = 0; i < n && i < 8; i++) if (out[i] && !strcmp(out[i], cand[j])) reported = 1;
            if (access(p, F_OK) != 0) {
                removed++;
                if (!reported) unreported++;
            }
        }
        snprintf(p, sizeof p, "%s/v1/releases/20990103", cache);
        CHECK(access(p, F_OK) == 0);   /* the newest is kept */
        if (unreported || holes) {
            /* today's form only: each removed release that is not named is a NULL slot in the count */
            if (unreported == holes) g_holes++;
            else {
                fprintf(stderr, "prune, allocation %ld fails: %lu removed and not named, %lu NULL slots, count %lu\n", k,
                        (unsigned long)unreported, (unsigned long)holes, (unsigned long)n);
                CHECK(0);
            }
        }
        if (!oom_failed) {
            CHECK_STATUS(st, OTC_OK);
            CHECK(n == 2 && removed == 2);
        } else if (st == OTC_OK && removed < 2) {
            if (oom_cjson_failed) g_unverified++;
            else {
                fprintf(stderr, "prune, allocation %ld fails: ok with %lu of 2 releases removed\n", k, (unsigned long)removed);
                CHECK(0);
            }
        }
        for (i = 0; i < 8; i++) otc_free(out[i]);
        if (oom_live != base) fprintf(stderr, "prune, allocation %ld fails: %ld blocks leak\n", k, oom_live - base);
        CHECK(oom_live == base);
        runs++;
        if (!oom_failed) break;
    }
    CHECK(oom_loop_end("prune", k, injected));
    if (g_unverified)
        fprintf(stderr, "%ld runs: a .verified whose parse ran out of memory read as not verified (ok, fewer releases)\n",
                g_unverified);
    if (g_holes) fprintf(stderr, "%ld runs: prune removed a release and did not name it\n", g_holes);
    PENDING("PK-R2-23", g_unverified == 0);
    PENDING("PK-R2-03", g_holes == 0);
    printf("oom: %d runs\n", runs);
    return test_done("test_fetch_oom_lists");
}
