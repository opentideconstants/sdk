/* PK-R2-23 (R2-253): every failure on a release handle is its last error
 * (spec 4.8), also out of memory and a bad argument. Before each call the
 * handle holds a different, older error (otc_station with a NULL id:
 * invalid_argument, "otc_station: NULL argument"). A call that fails with
 * OTC_E_NOMEM must leave otc_last_error_status at OTC_E_NOMEM, and a call that
 * fails with a bad argument must replace the older message. Every allocation
 * is made to fail in turn. */
#include "otc_test.h"
#include "otc_oom.h"

static otc_release *g_rel;

static void stale(void)
{
    otc_station_t *s = NULL;
    (void)otc_station(g_rel, NULL, &s);
}

static otc_status op_citation(void)
{
    char buf[512];
    size_t need;
    return otc_release_citation(g_rel, buf, sizeof buf, &need);
}

static otc_status op_attribution(void)
{
    char buf[1024];
    size_t need;
    const char *ids[1] = {"OTC-X-1"};
    return otc_attribution(g_rel, ids, 1, buf, sizeof buf, &need);
}

static otc_status op_station(void)
{
    otc_station_t *s = NULL;
    otc_status st = otc_station(g_rel, "OTC-X-1", &s);
    otc_station_free(s);
    return st;
}

static otc_status op_stats(void)
{
    otc_stats *s = NULL;
    otc_status st = otc_release_stats(g_rel, &s);
    otc_stats_free(s);
    return st;
}

static long g_nomem_runs;

static void oom_loop(const char *what, otc_status (*op)(void))
{
    long k, injected = 0, base;
    for (k = 1; k <= OOM_MAX_RUNS; k++) {
        otc_status st;
        stale();
        base = oom_live;
        oom_arm(k);
        st = op();
        oom_disarm();
        if (oom_live != base) { fprintf(stderr, "%s, allocation %ld fails: %ld blocks leak\n", what, k, oom_live - base); CHECK(0); }
        if (!oom_failed) { CHECK_STATUS(st, OTC_OK); break; }
        injected++;
        CHECK(st == OTC_OK || st == OTC_E_NOMEM);
        if (st == OTC_E_NOMEM) {
            g_nomem_runs++;
            if (otc_last_error_status(g_rel) != OTC_E_NOMEM) {
                fprintf(stderr, "%s, allocation %ld fails: out_of_memory, but the last error is still %s\n", what, k,
                        otc_status_code(otc_last_error_status(g_rel)));
                CHECK(0);
            }
        }
    }
    CHECK(oom_loop_end(what, k, injected));
}

int main(void)
{
    char *dir = test_tmpdir(), *path, msg[512];
    size_t need;
    printf("oom: start\n");
    test_write(dir, "OTC_20990101.meta.json", TEST_META("20990101"));
    test_write(dir, "OTC_20990101.jsonl", TEST_STATION("OTC-X-1", "One") "\n");
    path = test_join(dir, "OTC_20990101.jsonl");
    if (otc_open_file(path, NULL, &g_rel) != OTC_OK) return 2;
    oom_hook_cjson();
    oom_loop("citation", op_citation);
    oom_loop("attribution", op_attribution);
    oom_loop("station", op_station);
    oom_loop("stats", op_stats);
    CHECK(g_nomem_runs > 0);

    /* a bad argument with the handle given: ids NULL with a count */
    stale();
    CHECK_STATUS(otc_attribution(g_rel, NULL, 2, msg, sizeof msg, &need), OTC_E_INVALID_ARGUMENT);
    CHECK_STATUS(otc_last_error(g_rel, msg, sizeof msg, &need), OTC_OK);
    if (strstr(msg, "otc_station")) fprintf(stderr, "otc_attribution(ids NULL): the last error is still \"%s\"\n", msg);
    CHECK(strstr(msg, "otc_station") == NULL);

    otc_close(g_rel);
    printf("oom: %ld runs gave out_of_memory\n", g_nomem_runs);
    free(path);
    free(dir);
    return test_done("test_last_error_oom");
}
