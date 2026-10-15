/* K-NC DR106 (spec 4.2, 6.4): otc_fetch_open takes commercial_only through
 * its oopts and applies it to the open of the cached file: from the knc
 * fixture root, OTC-T-0181's recommended set is x-nc without the option and
 * w-ok with it (the same cached release, opened twice). */
#include "otc_test.h"

static int rec_is(otc_release *rel, const char *sid, const char *want)
{
    otc_station_t *st = NULL;
    const otc_set *set = NULL;
    char id[64];
    size_t need;
    int ok;
    if (otc_station(rel, sid, &st) != OTC_OK) return 0;
    ok = otc_station_recommended_set(st, &set) == OTC_OK && otc_set_set_id(set, id, sizeof id, &need) == OTC_OK
         && !strcmp(id, want);
    otc_station_free(st);
    return ok;
}

int main(void)
{
    char *cache = test_tmpdir(), base[512];
    otc_fetch_options fo;
    otc_open_options oo;
    otc_release *rel = NULL;
    otc_error err;
    if (!test_server()) return test_skip("test_fetch_commercial_only", "no OTC_TEST_SERVER");
    otc_fetch_options_init(&fo);
    otc_open_options_init(&oo);
    otc_error_init(&err);
    snprintf(base, sizeof base, "%s/knc/", test_server());
    fo.cache_dir = cache;
    fo.base_url = base;
    fo.error = &err;
    CHECK_STATUS(otc_fetch_open(&fo, "20991231.2", &oo, &rel), OTC_OK);
    if (rel) CHECK(rec_is(rel, "OTC-T-0181", "OTC-T-0181/x-nc"));
    otc_close(rel);
    rel = NULL;
    oo.commercial_only = true;
    CHECK_STATUS(otc_fetch_open(&fo, "20991231.2", &oo, &rel), OTC_OK);
    if (rel) {
        CHECK(otc_release_loaded_from(rel) == OTC_LOADED_FROM_CACHE);
        CHECK(rec_is(rel, "OTC-T-0181", "OTC-T-0181/w-ok"));
    }
    otc_close(rel);
    free(cache);
    return test_done("test_fetch_commercial_only");
}
