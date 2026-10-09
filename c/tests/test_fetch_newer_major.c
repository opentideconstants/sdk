/* PK03 / C53: otc_fetch_newer_format_major tells "no newer major known" from
 * "the cached OTC_latest.json is corrupt". Every call that fails sets *major
 * to 0 (no stale value from an earlier call), and says why in the error. */
#include "otc_test.h"

static otc_fetch_options g_fo;
static otc_error g_err;

/* One call with *major set to a value no call gives; its status, and *major after it. */
static otc_status call(int *major)
{
    *major = -7;
    g_err.message[0] = '\0';
    return otc_fetch_newer_format_major(&g_fo, major);
}

static void mkdir_or_die(const char *p)
{
    if (mkdir(p, 0777) != 0) { perror(p); exit(2); }
}

/* A failing call: the status, *major reset to 0, and a message */
#define CHECK_FAILS(want)                                                                           \
    do {                                                                                            \
        CHECK_STATUS(call(&major), want);                                                           \
        CHECK(major == 0);                                                                          \
        CHECK(g_err.message[0] != '\0');                                                            \
    } while (0)

int main(void)
{
    char *cache = test_tmpdir(), *pdir;
    int major;
    otc_fetch_options_init(&g_fo);
    otc_error_init(&g_err);
    g_fo.cache_dir = cache;
    g_fo.error = &g_err;
    g_fo.offline = true;
    /* nothing cached: none known, and the error says why */
    CHECK_FAILS(OTC_E_NOT_FOUND);
    pdir = test_join(cache, "v1");
    mkdir_or_die(pdir);
    free(pdir);
    pdir = test_join(cache, "v1/pointer");
    mkdir_or_die(pdir);
    /* a newer major */
    test_write(pdir, "OTC_latest.json", "{\"datestamp\":\"20990101\",\"format_version\":\"2.0\"}");
    CHECK_STATUS(call(&major), OTC_OK);
    CHECK(major == 2);
    /* a cached pointer of the supported major, or an older one: none */
    test_write(pdir, "OTC_latest.json", "{\"datestamp\":\"20990101\",\"format_version\":\"1.0\"}");
    CHECK_FAILS(OTC_E_NOT_FOUND);
    test_write(pdir, "OTC_latest.json", "{\"datestamp\":\"20990101\",\"format_version\":\"0.9\"}");
    CHECK_FAILS(OTC_E_NOT_FOUND);
    /* a corrupt cached pointer is not "none": not JSON, a format_version that is not MAJOR.MINOR,
     * one that is missing, null or not a string */
    test_write(pdir, "OTC_latest.json", "<html>");
    CHECK_FAILS(OTC_E_INVALID_RELEASE);
    test_write(pdir, "OTC_latest.json", "{\"datestamp\":\"20990101\",\"format_version\":\"2.x\"}");
    CHECK_FAILS(OTC_E_INVALID_RELEASE);
    test_write(pdir, "OTC_latest.json", "{\"datestamp\":\"20990101\"}");
    CHECK_FAILS(OTC_E_INVALID_RELEASE);
    test_write(pdir, "OTC_latest.json", "{\"datestamp\":\"20990101\",\"format_version\":null}");
    CHECK_FAILS(OTC_E_INVALID_RELEASE);
    test_write(pdir, "OTC_latest.json", "{\"datestamp\":\"20990101\",\"format_version\":2.0}");
    CHECK_FAILS(OTC_E_INVALID_RELEASE);
    free(pdir);
    free(cache);
    return test_done("test_fetch_newer_major");
}
