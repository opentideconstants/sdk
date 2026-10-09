/* PK-R2-23 (R2-256): otc_fetch_open of a cached release, offline, with every
 * allocation made to fail in turn. Each run gives OTC_OK or OTC_E_NOMEM and
 * leaks nothing. A .verified whose read runs out of memory is out of memory,
 * never "not verified" (that would be offline_unavailable, or cache: "no
 * .verified record"), and never "verified with no sizes to compare" (an open
 * that skips the size check). An OK run gives the same release files as the
 * run with no failure. */
#include "otc_test.h"
#include "otc_oom.h"

static size_t file_count(const otc_release *rel) { return rel ? otc_release_file_count(rel) : 0; }

int main(void)
{
    char *cache = test_tmpdir(), base[512];
    otc_fetch_options fo;
    otc_error err;
    otc_release *rel = NULL;
    size_t want_files;
    long k, base_live, injected = 0, bad = 0;
    if (!test_server()) return test_skip("test_fetch_oom_open", "no OTC_TEST_SERVER");
    printf("oom: start\n");
    otc_fetch_options_init(&fo);
    otc_error_init(&err);
    snprintf(base, sizeof base, "%s/good/", test_server());
    fo.cache_dir = cache;
    fo.base_url = base;
    fo.error = &err;
    if (otc_fetch_open(&fo, "20991231.2", NULL, &rel) != OTC_OK) {
        fprintf(stderr, "test_fetch_oom_open: the download gave %s (%s)\n", otc_status_code(err.status), err.message);
        return 2;
    }
    otc_close(rel);
    rel = NULL;
    fo.offline = true;
    /* one offline open outside the counts: lazy state, and the stream index written */
    if (otc_fetch_open(&fo, "20991231.2", NULL, &rel) != OTC_OK) return 2;
    want_files = file_count(rel);
    otc_close(rel);
    rel = NULL;
    CHECK(want_files > 0);

    oom_hook_cjson();
    for (k = 1; k <= OOM_MAX_RUNS; k++) {
        otc_status st;
        base_live = oom_live;
        oom_arm(k);
        st = otc_fetch_open(&fo, "20991231.2", NULL, &rel);
        oom_disarm();
        if (st == OTC_OK) {
            CHECK(rel != NULL);
            if (file_count(rel) != want_files) {
                fprintf(stderr, "open, allocation %ld fails: ok with %lu release files, want %lu\n", k,
                        (unsigned long)file_count(rel), (unsigned long)want_files);
                CHECK(0);
            }
        } else {
            CHECK(rel == NULL);
            if (st != OTC_E_NOMEM) {
                fprintf(stderr, "open, allocation %ld fails%s: %s (%s)\n", k, oom_cjson_failed ? " (cJSON's)" : "",
                        otc_status_code(st), err.message);
                bad++;
            }
        }
        otc_close(rel);
        rel = NULL;
        if (oom_live != base_live) {
            fprintf(stderr, "open, allocation %ld fails: %ld blocks leak\n", k, oom_live - base_live);
            CHECK(0);
        }
        if (!oom_failed) { CHECK_STATUS(st, OTC_OK); break; }
        injected++;
    }
    CHECK(oom_loop_end("open", k, injected));
    if (bad) fprintf(stderr, "%ld runs: a failed allocation gave a status other than out_of_memory\n", bad);
    CHECK(bad == 0);
    printf("oom: %ld runs\n", k);
    free(cache);
    return test_done("test_fetch_oom_open");
}
