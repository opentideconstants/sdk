/* PK07 value checks on the real library.
 * C48: an integer field (missed_events, good_samples ...) with a fraction is
 *      not cut to an integer: it reads as missing (-1).
 * C98: a line of only ASCII whitespace (SP, HT, VT, FF, CR) is skipped, as
 *      in the other SDKs (CR2 DR26); a NUL line is not blank;
 *      text after a line's object is invalid_release, not ignored.
 * C34: the kind filter "other" matches a station whose kind is unknown, and
 *      the raw quantity matches nothing (spec 4.4, CR2 DR7).
 * C35: a validation row without previous_release has NaN and -1 there, as
 *      for any missing number and count, not zeros.
 * C13: a string cut to fit a small buffer (BUFFER_TOO_SMALL) ends on a whole
 *      UTF-8 character, never inside one.
 * C43: a set without provenance: otc_set_provenance_json is OTC_E_NOT_FOUND,
 *      as every other accessor of an absent value (CR D34), not "{}".
 * DR8: a line whose status the library does not know is in no query and no
 *      count, and the open logs it once at level 2 (CR2 DR8).
 * DR28: a line with no status (or null) is an active station (CR2 DR28).
 * C4:  a recommended set with no quantity gives kind OTHER, as in every SDK and
 *      the reference stream index (spec 6.2; orchestrator S3, PK-R2-09). */
#include "otc_test.h"

#include <math.h>

static int n_warn_retired;

static void count_log(void *user, int level, const char *msg)
{
    (void)user;
    if (level == 2 && strstr(msg, "OTC-X-2") && strstr(msg, "\"retired\"")) n_warn_retired++;
}

static otc_release *open_lines(const char *lines, char **dir_out)
{
    char *dir = test_tmpdir(), *path;
    otc_release *rel = NULL;
    otc_status st;
    test_write(dir, "OTC_20990101.meta.json", TEST_META("20990101"));
    test_write(dir, "OTC_20990101.jsonl", lines);
    path = test_join(dir, "OTC_20990101.jsonl");
    st = otc_open_file(path, NULL, &rel);
    if (st != OTC_OK) fprintf(stderr, "open: %s\n", otc_status_code(st));
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
    rel = open_lines("{\"station_id\":\"OTC-X-1\",\"status\":\"active\",\"name\":\"A\",\"lat\":1,\"lon\":1,\"type\":\"reference\","
                     "\"constant_sets\":[],\"validation\":[{\"set_id\":\"s\",\"missed_events\":1.5,\"extra_events\":2}]}\n", &dir);
    CHECK(rel != NULL);
    if (rel && otc_station(rel, "OTC-X-1", &st) == OTC_OK) {
        const otc_validation_t *v = NULL;
        CHECK_STATUS(otc_station_validation_at(st, 0, &v), OTC_OK);
        if (v) {
            CHECK(v->missed_events == -1);
            CHECK(v->extra_events == 2);
            /* C35 */
            CHECK(!v->has_previous_release);
            CHECK(isnan(v->previous_release.time_mae_min) && isnan(v->previous_release.range_error_m));
            CHECK(v->previous_release.missed_events == -1 && v->previous_release.extra_events == -1);
            if (v->missed_events != -1) fprintf(stderr, "missed_events 1.5 read as %lld\n", (long long)v->missed_events);
        }
    }
    otc_station_free(st);
    otc_close(rel);
    free(dir);
    /* C98 */
    rel = open_lines(TEST_STATION("OTC-X-1", "One") "\n \t \n\f\n\v\n \t\v\f \r\n" TEST_STATION("OTC-X-2", "Two") "\n\f", &dir);
    CHECK(rel != NULL && otc_release_station_count(rel) == 2);
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
    if (rel) {
        otc_filter f;
        const char *ids[4];
        size_t n = 9;
        otc_filter_init(&f);
        f.kind = "other";
        CHECK_STATUS(otc_stations(rel, &f, ids, 4, &n), OTC_OK);
        CHECK(n == 1);
        f.kind = "salinity";
        CHECK_STATUS(otc_stations(rel, &f, ids, 4, &n), OTC_OK);
        CHECK(n == 0);
        f.kind = "tide";
        CHECK_STATUS(otc_stations(rel, &f, ids, 4, &n), OTC_OK);
        CHECK(n == 0);
        f.kind = NULL;
        CHECK_STATUS(otc_stations(rel, &f, ids, 4, &n), OTC_OK);
        CHECK(n == 1);
    }
    otc_close(rel);
    free(dir);
    /* C4 */
    rel = open_lines("{\"station_id\":\"OTC-X-1\",\"status\":\"active\",\"name\":\"A\",\"lat\":1,\"lon\":1,\"type\":\"reference\","
                     "\"recommended_set_id\":\"s\",\"constant_sets\":[{\"set_id\":\"s\",\"source\":\"a\","
                     "\"qc_status\":\"ok\",\"convention_id\":\"c1\",\"licence_id\":\"l1\"}]}\n", &dir);
    st = NULL;
    if (rel && otc_station(rel, "OTC-X-1", &st) == OTC_OK) {
        const otc_set *set = NULL;
        char pj[16];
        size_t pn = 0;
        CHECK(otc_station_kind(st) == OTC_KIND_OTHER);
        /* C43: this set has no provenance */
        CHECK_STATUS(otc_station_recommended_set(st, &set), OTC_OK);
        CHECK_STATUS(otc_set_provenance_json(set, pj, sizeof pj, &pn), OTC_E_NOT_FOUND);
        if (otc_station_kind(st) != OTC_KIND_OTHER) fprintf(stderr, "kind %s\n", otc_kind_name(otc_station_kind(st)));
    }
    otc_station_free(st);
    otc_close(rel);
    free(dir);
    /* C13 */
    rel = open_lines(TEST_STATION("OTC-X-1", "\xc3\x98st") "\n", &dir);
    st = NULL;
    if (rel && otc_station(rel, "OTC-X-1", &st) == OTC_OK) {
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
    /* DR8, DR28 */
    {
        char *d2 = test_tmpdir(), *path;
        otc_release *r2 = NULL;
        otc_open_options o;
        otc_station_t *s2 = NULL;
        otc_open_options_init(&o);
        o.log_fn = count_log;
        test_write(d2, "OTC_20990101.meta.json", TEST_META("20990101"));
        test_write(d2, "OTC_20990101.jsonl",
                   "{\"station_id\":\"OTC-X-1\",\"name\":\"A\",\"lat\":1,\"lon\":1,\"type\":\"reference\",\"constant_sets\":[]}\n"
                   "{\"station_id\":\"OTC-X-2\",\"status\":\"retired\",\"name\":\"B\",\"lat\":1,\"lon\":1,\"type\":\"reference\",\"constant_sets\":[]}\n"
                   "{\"station_id\":\"OTC-X-3\",\"status\":null,\"name\":\"C\",\"lat\":1,\"lon\":1,\"type\":\"reference\",\"constant_sets\":[]}\n");
        path = test_join(d2, "OTC_20990101.jsonl");
        CHECK_STATUS(otc_open_file(path, &o, &r2), OTC_OK);
        CHECK(n_warn_retired == 1);
        if (r2) {
            otc_tombstone_t *t = NULL;
            CHECK(otc_release_station_count(r2) == 2 && otc_release_tombstone_count(r2) == 0);
            CHECK_STATUS(otc_station(r2, "OTC-X-2", &s2), OTC_E_NOT_FOUND);
            CHECK_STATUS(otc_tombstone(r2, "OTC-X-2", &t), OTC_E_NOT_FOUND);
            CHECK_STATUS(otc_station(r2, "OTC-X-1", &s2), OTC_OK);
            CHECK(otc_station_status(s2) == OTC_STATION_STATUS_ACTIVE);
            otc_station_free(s2);
            s2 = NULL;
            CHECK_STATUS(otc_station(r2, "OTC-X-3", &s2), OTC_OK);
            CHECK(otc_station_status(s2) == OTC_STATION_STATUS_ACTIVE);
            otc_station_free(s2);
            otc_tombstone_free(t);
        }
        otc_close(r2);
        free(path);
        free(d2);
    }
    return test_done("test_values");
}
