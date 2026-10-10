/* K-NC DR104 to DR106 (spec 4.2, 4.6, 6.4): the licence accessors
 * otc_licence_commercial_use, otc_licence_restriction and otc_licence_terms_url
 * (OTC_E_NOT_FOUND when absent); otc_open_options.commercial_only, which makes
 * the effective recommended set the station's recommended set and gives an
 * attribution with no non-commercial licence; and an otc_open_options from
 * before K-NC (struct_size ends before commercial_only), allocated at exactly
 * that size, which opens with commercial_only false (ASan reports a read past
 * its end). */
#include "otc_test.h"

#include <stddef.h>

#define KNC_META "{\"format_version\":\"1.0\",\"release\":{\"datestamp\":\"20990101\",\"concept_doi\":\"10.1/x\"}," \
    "\"conventions\":[{\"convention_id\":\"c1\"}],\"licences\":["                                                  \
    "{\"licence_id\":\"c\",\"spdx\":\"CC-BY-4.0\",\"provider\":\"C Co\",\"attribution\":\"C text\",\"commercial_use\":true}," \
    "{\"licence_id\":\"t\",\"spdx\":\"CC-BY-4.0\",\"provider\":\"T Co\",\"attribution\":\"T text\",\"commercial_use\":true," \
    "\"restriction\":\"Test: credit in the about screen.\",\"terms_url\":\"https://example.org/t\"},"                \
    "{\"licence_id\":\"n\",\"spdx\":\"LicenseRef-N\",\"provider\":\"N Co\",\"attribution\":\"N text\",\"commercial_use\":false," \
    "\"restriction\":\"Test: non-commercial use only.\",\"terms_url\":\"https://example.org/n\"}]}"

#define SET(id, sfx, lic) "{\"set_id\":\"" id "/" sfx "\",\"source\":\"x\",\"source_type\":\"official\",\"quantity\":\"water_level\"," \
    "\"qc_status\":\"ok\",\"convention_id\":\"c1\",\"licence_id\":\"" lic "\"}"

#define KNC_JSONL "{\"station_id\":\"OTC-X-1\",\"status\":\"active\",\"name\":\"N\",\"lat\":1,\"lon\":1,\"type\":\"reference\"," \
    "\"recommended_set_id\":\"OTC-X-1/a-nc\",\"constant_sets\":[" SET("OTC-X-1", "a-nc", "n") "," SET("OTC-X-1", "b-c", "c") "]}\n"

static int rec_is(otc_release *rel, const char *want)
{
    otc_station_t *st = NULL;
    const otc_set *set = NULL;
    char id[64];
    size_t need;
    int ok;
    if (otc_station(rel, "OTC-X-1", &st) != OTC_OK) return 0;
    ok = otc_station_recommended_set(st, &set) == OTC_OK && otc_set_set_id(set, id, sizeof id, &need) == OTC_OK
         && !strcmp(id, want);
    otc_station_free(st);
    return ok;
}

int main(void)
{
    char *dir = test_tmpdir(), *path, buf[512];
    otc_release *rel = NULL;
    const otc_licence *l = NULL;
    otc_open_options oo, *old;
    size_t need, old_size = offsetof(otc_open_options, commercial_only);
    test_write(dir, "OTC_20990101.meta.json", KNC_META);
    test_write(dir, "OTC_20990101.jsonl", KNC_JSONL);
    path = test_join(dir, "OTC_20990101.jsonl");

    /* the accessors, without the option */
    CHECK_STATUS(otc_open_file(path, NULL, &rel), OTC_OK);
    if (!rel) return test_done("test_licence_knc");
    CHECK_STATUS(otc_release_licence(rel, "c", &l), OTC_OK);
    CHECK(otc_licence_commercial_use(l));
    CHECK_STATUS(otc_licence_restriction(l, buf, sizeof buf, &need), OTC_E_NOT_FOUND);
    CHECK_STATUS(otc_licence_terms_url(l, buf, sizeof buf, &need), OTC_E_NOT_FOUND);
    CHECK_STATUS(otc_release_licence(rel, "t", &l), OTC_OK);
    CHECK(otc_licence_commercial_use(l));
    CHECK_STATUS(otc_licence_restriction(l, buf, sizeof buf, &need), OTC_OK);
    CHECK(!strcmp(buf, "Test: credit in the about screen."));
    CHECK_STATUS(otc_licence_terms_url(l, buf, sizeof buf, &need), OTC_OK);
    CHECK(!strcmp(buf, "https://example.org/t"));
    CHECK_STATUS(otc_release_licence(rel, "n", &l), OTC_OK);
    CHECK(!otc_licence_commercial_use(l));
    CHECK_STATUS(otc_licence_restriction(l, buf, sizeof buf, &need), OTC_OK);
    CHECK(!strcmp(buf, "Test: non-commercial use only."));
    CHECK_STATUS(otc_licence_terms_url(l, buf, sizeof buf, &need), OTC_OK);
    CHECK(!strcmp(buf, "https://example.org/n"));
    CHECK(!otc_licence_commercial_use(NULL));
    CHECK(rec_is(rel, "OTC-X-1/a-nc"));
    CHECK_STATUS(otc_attribution(rel, NULL, 0, buf, sizeof buf, &need), OTC_OK);
    CHECK(!strcmp(buf, "Tidal constants: OpenTideConstants 20990101, doi:10.1/x, CC BY 4.0. Sources: C Co: C text; "
                       "N Co: N text; T Co: T text. Non-commercial use only: N Co (LicenseRef-N, https://example.org/n)"));
    if (strstr(buf, "Non-commercial") == NULL) fprintf(stderr, "attribution: %s\n", buf);
    otc_close(rel);
    rel = NULL;

    /* commercial_only: the effective recommended set, and no non-commercial licence in the attribution */
    otc_open_options_init(&oo);
    CHECK(!oo.commercial_only);
    oo.commercial_only = true;
    CHECK_STATUS(otc_open_file(path, &oo, &rel), OTC_OK);
    if (rel) {
        CHECK(rec_is(rel, "OTC-X-1/b-c"));
        CHECK_STATUS(otc_attribution(rel, NULL, 0, buf, sizeof buf, &need), OTC_OK);
        CHECK(!strcmp(buf, "Tidal constants: OpenTideConstants 20990101, doi:10.1/x, CC BY 4.0. Sources: C Co: C text; T Co: T text"));
    }
    otc_close(rel);
    rel = NULL;

    /* a struct from before K-NC: taken, and commercial_only reads as false */
    old = (otc_open_options *)malloc(old_size);
    if (!old) return 2;
    memset(old, 0, old_size);
    old->struct_size = old_size;
    CHECK_STATUS(otc_open_file(path, old, &rel), OTC_OK);
    if (rel) CHECK(rec_is(rel, "OTC-X-1/a-nc"));
    otc_close(rel);
    rel = NULL;
    /* one byte less is too small */
    old->struct_size = old_size - 1;
    CHECK_STATUS(otc_open_file(path, old, &rel), OTC_E_INVALID_ARGUMENT);
    free(old);
    free(path);
    free(dir);
    return test_done("test_licence_knc");
}
