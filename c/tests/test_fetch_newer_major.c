/* PK03 / C53: otc_fetch_newer_format_major tells "no newer major known" from
 * "the cached OTC_latest.json is corrupt". */
#include "otc_test.h"

int main(void)
{
    char *cache = test_tmpdir(), *pdir;
    otc_fetch_options fo;
    otc_error err;
    int major = -7;
    otc_fetch_options_init(&fo);
    otc_error_init(&err);
    fo.cache_dir = cache;
    fo.error = &err;
    fo.offline = true;
    /* nothing cached: none known, and the error says why */
    CHECK_STATUS(otc_fetch_newer_format_major(&fo, &major), OTC_E_NOT_FOUND);
    CHECK(major == 0);
    CHECK(err.message[0] != '\0');
    /* a cached pointer of the supported major: none */
    pdir = test_join(cache, "v1");
    mkdir(pdir, 0777);
    free(pdir);
    pdir = test_join(cache, "v1/pointer");
    mkdir(pdir, 0777);
    test_write(pdir, "OTC_latest.json", "{\"datestamp\":\"20990101\",\"format_version\":\"1.0\"}");
    CHECK_STATUS(otc_fetch_newer_format_major(&fo, &major), OTC_E_NOT_FOUND);
    /* a newer major */
    test_write(pdir, "OTC_latest.json", "{\"datestamp\":\"20990101\",\"format_version\":\"2.0\"}");
    CHECK_STATUS(otc_fetch_newer_format_major(&fo, &major), OTC_OK);
    CHECK(major == 2);
    /* a corrupt cached pointer is not "none" */
    test_write(pdir, "OTC_latest.json", "<html>");
    CHECK_STATUS(otc_fetch_newer_format_major(&fo, &major), OTC_E_INVALID_RELEASE);
    CHECK(err.message[0] != '\0');
    test_write(pdir, "OTC_latest.json", "{\"datestamp\":\"20990101\",\"format_version\":\"2.x\"}");
    CHECK_STATUS(otc_fetch_newer_format_major(&fo, &major), OTC_E_INVALID_RELEASE);
    free(pdir);
    free(cache);
    return test_done("test_fetch_newer_major");
}
