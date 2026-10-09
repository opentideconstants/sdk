/* PK03 / C30: a pointer without format_version (the key absent, /nofv/, or
 * null, /good/) is judged as in the cache path (the release's own .meta.json
 * is checked at open): it is not "a newer format (-1)", it costs no extra GET
 * of OTC_index.json, and its release is the answer (with no format_version).
 * The "no GET" check reads the library's debug lines "GET <url> -> ...": the
 * test first sees the pointer's own GET there (its positive control), so the
 * zero cannot come from a log that says nothing. */
#include "otc_test.h"

static int g_bad_log, g_pointer_get;

static void log_fn(void *u, int level, const char *msg)
{
    (void)u;
    (void)level;
    if (strstr(msg, "(-1)") || strstr(msg, "OTC_index.json")) {
        fprintf(stderr, "log: %s\n", msg);
        g_bad_log++;
    }
    if (!strncmp(msg, "GET ", 4) && strstr(msg, "OTC_latest-f1.json")) g_pointer_get++;
}

static void check_pointer(const char *prefix, int open_it)
{
    char *cache = test_tmpdir(), base[512];
    otc_fetch_options fo;
    otc_release_info *info = NULL;
    otc_release *rel = NULL;
    otc_error err;
    otc_fetch_options_init(&fo);
    otc_error_init(&err);
    snprintf(base, sizeof base, "%s/%s/", test_server(), prefix);
    fo.cache_dir = cache;
    fo.base_url = base;
    fo.error = &err;
    fo.log_fn = log_fn;
    g_bad_log = g_pointer_get = 0;
    CHECK_STATUS(otc_fetch_latest_info(&fo, &info), OTC_OK);
    CHECK(g_pointer_get >= 1);   /* the GET lines are seen ... */
    CHECK(g_bad_log == 0);       /* ... and none is the index's, nor a "(-1)" */
    if (g_pointer_get < 1) fprintf(stderr, "%s: no \"GET ...OTC_latest-f1.json\" line was logged\n", prefix);
    CHECK(info != NULL);
    if (info) {
        char ds[32] = "", fv[16];
        size_t need;
        CHECK_STATUS(otc_release_info_datestamp(info, ds, sizeof ds, &need), OTC_OK);
        CHECK(!strcmp(ds, "20991231.2"));
        CHECK_STATUS(otc_release_info_format_version(info, fv, sizeof fv, &need), OTC_E_NOT_FOUND);
    }
    otc_release_info_free(info);
    if (open_it) {   /* the release's own .meta.json says its format: the open works */
        CHECK_STATUS(otc_fetch_open(&fo, NULL, NULL, &rel), OTC_OK);
        CHECK(g_bad_log == 0);
        otc_close(rel);
    }
    free(cache);
}

int main(void)
{
    if (!test_server()) return test_skip("test_fetch_pointer_no_fv", "no OTC_TEST_SERVER");
    check_pointer("good", 1);    /* "format_version": null */
    check_pointer("nofv", 0);    /* no format_version key (its files are not served under /nofv/) */
    return test_done("test_fetch_pointer_no_fv");
}
