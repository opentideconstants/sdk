/* PK07 value checks on the real library.
 * C48: an integer field (missed_events, good_samples ...) with a fraction is
 *      never cut to an integer: the open fails with OTC_E_INVALID_RELEASE, as
 *      in every SDK (CR2 PK-R2-05: a known field of the wrong JSON type).
 * C98: a line of only spaces or tabs is skipped (as the other SDKs do);
 *      text after a line's object is invalid_release, not ignored; white
 *      space after it (CRLF, spaces, tabs) is not text.
 * C34: the kind filter "other" is not a kind value: it matches no station,
 *      also not one whose kind is unknown (spec 4.4).
 * C35: a validation row without previous_release has NaN and -1 there, as
 *      for any missing number and count, not zeros.
 * C13: a string cut to fit a small buffer (BUFFER_TOO_SMALL) ends on a whole
 *      UTF-8 character, never inside one.
 * C43: a set without provenance: otc_set_provenance_json is OTC_E_NOT_FOUND,
 *      as every other accessor of an absent value (CR D34), not "{}".
 * PK-R2-05: a line that is not well-formed UTF-8 fails the open with
 *      OTC_E_INVALID_RELEASE (overlong forms, encoded surrogates, above
 *      U+10FFFF, a cut sequence); a 4-byte character opens.
 * C4:  a recommended set with no quantity gives kind UNSET (null), not OTHER:
 *      OTHER is only for a quantity the library does not know (spec 6.2, 6.4). */
#include "otc_test.h"

#include <math.h>

static otc_release *open_lines(const char *lines, char **dir_out)
{
    char *dir = test_tmpdir(), *path;
    otc_release *rel = NULL;
    otc_status st;
    test_write(dir, "OTC_20990101.meta.json", TEST_META("20990101"));
    test_write(dir, "OTC_20990101.jsonl", lines);
    path = test_join(dir, "OTC_20990101.jsonl");
    st = otc_open_file(path, NULL, &rel);
    CHECK_STATUS(st, OTC_OK);   /* a fixture that does not open fails here; its checks below do not run */
    free(path);
    *dir_out = dir;
    return rel;
}

int main(void)
{
    char *dir;
    otc_release *rel;
    otc_station_t *st = NULL;
    /* C48 */
    {
        char *d2 = test_tmpdir(), *path;
        otc_release *r2 = NULL;
        test_write(d2, "OTC_20990101.meta.json", TEST_META("20990101"));
        test_write(d2, "OTC_20990101.jsonl", "{\"station_id\":\"OTC-X-1\",\"status\":\"active\",\"name\":\"A\",\"lat\":1,"
                   "\"lon\":1,\"type\":\"reference\",\"constant_sets\":[],"
                   "\"validation\":[{\"set_id\":\"s\",\"missed_events\":1.5,\"extra_events\":2}]}\n");
        path = test_join(d2, "OTC_20990101.jsonl");
        CHECK_STATUS(otc_open_file(path, NULL, &r2), OTC_E_INVALID_RELEASE);
        otc_close(r2);
        free(path);
        free(d2);
    }
    rel = open_lines("{\"station_id\":\"OTC-X-1\",\"status\":\"active\",\"name\":\"A\",\"lat\":1,\"lon\":1,\"type\":\"reference\","
                     "\"constant_sets\":[],\"validation\":[{\"set_id\":\"s\",\"extra_events\":2.0}]}\n", &dir);
    CHECK(rel != NULL);
    if (rel) CHECK_STATUS(otc_station(rel, "OTC-X-1", &st), OTC_OK);
    if (st) {
        const otc_validation_t *v = NULL;
        CHECK_STATUS(otc_station_validation_at(st, 0, &v), OTC_OK);
        if (v) {
            CHECK(v->missed_events == -1);   /* absent */
            CHECK(v->extra_events == 2);     /* 2.0: an integral value */
            /* C35 */
            CHECK(!v->has_previous_release);
            CHECK(isnan(v->previous_release.time_mae_min) && isnan(v->previous_release.range_error_m));
            CHECK(v->previous_release.missed_events == -1 && v->previous_release.extra_events == -1);
        }
    }
    otc_station_free(st);
    otc_close(rel);
    free(dir);
    /* C98 */
    rel = open_lines(TEST_STATION("OTC-X-1", "One") "\n \t \n" TEST_STATION("OTC-X-2", "Two") "\n", &dir);
    CHECK(rel != NULL && otc_release_station_count(rel) == 2);
    otc_close(rel);
    free(dir);
    /* white space after a line's object is not text after it: CRLF, spaces and tabs, an empty line */
    rel = open_lines(TEST_STATION("OTC-X-1", "One") "\r\n" TEST_STATION("OTC-X-2", "Two") " \t\n\n"
                     TEST_STATION("OTC-X-3", "Three") " \r\n", &dir);
    CHECK(rel != NULL && otc_release_station_count(rel) == 3);
    otc_close(rel);
    free(dir);
    {
        char *d2 = test_tmpdir(), *path;
        otc_release *r2 = NULL;
        test_write(d2, "OTC_20990101.meta.json", TEST_META("20990101"));
        test_write(d2, "OTC_20990101.jsonl", TEST_STATION("OTC-X-1", "One") " trailing\n");
        path = test_join(d2, "OTC_20990101.jsonl");
        CHECK_STATUS(otc_open_file(path, NULL, &r2), OTC_E_INVALID_RELEASE);
        otc_close(r2);
        test_write(d2, "OTC_20990101.jsonl", TEST_STATION("OTC-X-1", "One") "{}\n");
        CHECK_STATUS(otc_open_file(path, NULL, &r2), OTC_E_INVALID_RELEASE);
        otc_close(r2);
        free(path);
        free(d2);
    }
    /* C34 */
    rel = open_lines("{\"station_id\":\"OTC-X-1\",\"status\":\"active\",\"name\":\"A\",\"lat\":1,\"lon\":1,\"type\":\"reference\","
                     "\"recommended_set_id\":\"s\",\"constant_sets\":[{\"set_id\":\"s\",\"source\":\"a\",\"quantity\":\"salinity\","
                     "\"qc_status\":\"ok\",\"convention_id\":\"c1\",\"licence_id\":\"l1\"}]}\n", &dir);
    CHECK(rel != NULL);
    if (rel) {
        otc_filter f;
        const char *ids[4];
        size_t n = 9;
        otc_filter_init(&f);
        f.kind = "other";
        CHECK_STATUS(otc_stations(rel, &f, ids, 4, &n), OTC_OK);
        CHECK(n == 0);
        f.kind = "tide";
        CHECK_STATUS(otc_stations(rel, &f, ids, 4, &n), OTC_OK);
        CHECK(n == 0);
        f.kind = NULL;
        CHECK_STATUS(otc_stations(rel, &f, ids, 4, &n), OTC_OK);
        CHECK(n == 1);
        /* the premise: this station's kind is OTHER (a quantity the library does not know), so the
         * zero above is the filter's doing, not a kind that is unknown */
        CHECK_STATUS(otc_station(rel, "OTC-X-1", &st), OTC_OK);
        if (st) CHECK(otc_station_kind(st) == OTC_KIND_OTHER);
        otc_station_free(st);
        st = NULL;
    }
    otc_close(rel);
    free(dir);
    /* C4 */
    rel = open_lines("{\"station_id\":\"OTC-X-1\",\"status\":\"active\",\"name\":\"A\",\"lat\":1,\"lon\":1,\"type\":\"reference\","
                     "\"recommended_set_id\":\"s\",\"constant_sets\":[{\"set_id\":\"s\",\"source\":\"a\","
                     "\"qc_status\":\"ok\",\"convention_id\":\"c1\",\"licence_id\":\"l1\"}]}\n", &dir);
    st = NULL;
    CHECK(rel != NULL);
    if (rel) CHECK_STATUS(otc_station(rel, "OTC-X-1", &st), OTC_OK);
    if (st) {
        const otc_set *set = NULL;
        char pj[16];
        size_t pn = 0;
        CHECK(otc_station_kind(st) == OTC_KIND_UNSET);
        /* C43: this set has no provenance */
        CHECK_STATUS(otc_station_recommended_set(st, &set), OTC_OK);
        CHECK_STATUS(otc_set_provenance_json(set, pj, sizeof pj, &pn), OTC_E_NOT_FOUND);
        if (otc_station_kind(st) != OTC_KIND_UNSET) fprintf(stderr, "kind %s\n", otc_kind_name(otc_station_kind(st)));
    }
    otc_station_free(st);
    otc_close(rel);
    free(dir);
    /* C13 */
    rel = open_lines(TEST_STATION("OTC-X-1", "\xc3\x98st") "\n", &dir);
    st = NULL;
    CHECK(rel != NULL);
    if (rel) CHECK_STATUS(otc_station(rel, "OTC-X-1", &st), OTC_OK);
    if (st) {
        char b[4];
        size_t need = 0;
        CHECK_STATUS(otc_station_name(st, b, 2, &need), OTC_E_BUFFER_TOO_SMALL);
        CHECK(need == 5 && b[0] == '\0');
        CHECK_STATUS(otc_station_name(st, b, 4, &need), OTC_E_BUFFER_TOO_SMALL);
        CHECK(!strcmp(b, "\xc3\x98s"));
    }
    otc_station_free(st);
    otc_close(rel);
    free(dir);
    /* PK-R2-05: a line that is not well-formed UTF-8 is invalid_release; a 4-byte character is not */
    {
        static const char *const bad[] = {
            "\xff",                 /* never in UTF-8 */
            "\xc0\xaf",             /* an overlong '/' */
            "\xe0\x80\xaf",         /* an overlong '/', 3 bytes */
            "\xed\xa0\x80",         /* an encoded surrogate U+D800 */
            "\xf4\x90\x80\x80",     /* above U+10FFFF */
            "\xc3",                 /* a lead byte with no continuation */
        };
        char *d2 = test_tmpdir(), *path = test_join(d2, "OTC_20990101.jsonl");
        char line[512];
        size_t i;
        otc_release *r2 = NULL;
        test_write(d2, "OTC_20990101.meta.json", TEST_META("20990101"));
        for (i = 0; i < sizeof bad / sizeof *bad; i++) {
            snprintf(line, sizeof line, TEST_STATION("OTC-X-1", "A%sB") "\n", bad[i]);
            test_write(d2, "OTC_20990101.jsonl", line);
            CHECK_STATUS(otc_open_file(path, NULL, &r2), OTC_E_INVALID_RELEASE);
            otc_close(r2);
            r2 = NULL;
        }
        test_write(d2, "OTC_20990101.jsonl", TEST_STATION("OTC-X-1", "A\xf0\x9f\x8c\x8a\xf4\x8f\xbf\xbf" "B") "\n");
        CHECK_STATUS(otc_open_file(path, NULL, &r2), OTC_OK);
        otc_close(r2);
        free(path);
        free(d2);
    }
    return test_done("test_values");
}
