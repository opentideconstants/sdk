/* PK08 / B2-4: release.created is returned in UTC, YYYY-MM-DDTHH:MM:SSZ
 * (otc__utc_time), the same as the other SDKs.
 * PK12 / R75 (C part): a Retry-After that is an HTTP-date (RFC 9110 5.6.7,
 * IMF-fixdate) is read (otc__http_date), not ignored.
 * CR2 DR6: impossible calendar fields, hour 24, a leap second, a time out of
 * range in UTC and an HTTP date with the wrong weekday are malformed, never
 * rolled over; a malformed created or record_span is invalid_release, and a
 * malformed provenance.build time is not found (null). */
#include "otc_test.h"
#include "otc_internal.h"

static void want(const char *in, const char *out)
{
    char got[21] = "";
    int ok = otc__utc_time(in, got);
    if (out ? (!ok || strcmp(got, out) != 0) : ok) {
        fprintf(stderr, "%s -> %s (%d), want %s\n", in, ok ? got : "-", ok, out ? out : "not a time");
        g_failures++;
    }
}

/* One release in dir: created as given, and the station's set with the extra
 * set fields (",\"record_span\":..." or ""). The status of otc_open_file. */
static otc_status open_with(const char *dir, const char *created, const char *set_extra, otc_release **rel)
{
    char meta[512], line[1024], *path;
    otc_status st;
    snprintf(meta, sizeof meta,
             "{\"format_version\":\"1.0\",\"release\":{\"datestamp\":\"20990101\",\"created\":\"%s\"},"
             "\"conventions\":[{\"convention_id\":\"c1\"}],\"licences\":[{\"licence_id\":\"l1\"}]}", created);
    snprintf(line, sizeof line,
             "{\"station_id\":\"OTC-X-1\",\"status\":\"active\",\"name\":\"One\",\"lat\":1.0,\"lon\":2.0,"
             "\"type\":\"reference\",\"recommended_set_id\":\"OTC-X-1/s\",\"constant_sets\":[{\"set_id\":\"OTC-X-1/s\","
             "\"source\":\"src\",\"source_type\":\"official\",\"quantity\":\"water_level\",\"qc_status\":\"ok\","
             "\"convention_id\":\"c1\",\"licence_id\":\"l1\",\"constituents\":[{\"name\":\"M2\",\"amplitude_m\":1.0,"
             "\"phase_deg\":10.0}]%s}]}\n", set_extra);
    test_write(dir, "OTC_20990101.meta.json", meta);
    test_write(dir, "OTC_20990101.jsonl", line);
    path = test_join(dir, "OTC_20990101.jsonl");
    *rel = NULL;
    st = otc_open_file(path, NULL, rel);
    free(path);
    return st;
}

static const char *const BAD_TIMES[] = {"2099-02-30T00:00:00Z", "2099-02-31T00:00:00Z", "2097-02-29T00:00:00Z",
                                        "2099-12-31T24:00:00Z", "2099-12-31T23:59:60Z", "0001-01-01T00:00:00+01:00",
                                        "9999-12-31T23:59:59-01:00", "0000-06-01T00:00:00Z"};

static void dr6(char *dir)
{
    size_t i, need;
    char extra[256], buf[64];
    otc_release *rel = NULL;
    for (i = 0; i < sizeof BAD_TIMES / sizeof *BAD_TIMES; i++) {
        want(BAD_TIMES[i], NULL);
        if (open_with(dir, BAD_TIMES[i], "", &rel) != OTC_E_INVALID_RELEASE) {
            fprintf(stderr, "created %s: opened\n", BAD_TIMES[i]);
            g_failures++;
        }
        otc_close(rel);
        snprintf(extra, sizeof extra, ",\"record_span\":{\"start\":\"2090-01-01T00:00:00Z\",\"end\":\"%s\"}", BAD_TIMES[i]);
        if (open_with(dir, "2099-12-31T00:00:00Z", extra, &rel) != OTC_E_INVALID_RELEASE) {
            fprintf(stderr, "record_span.end %s: opened\n", BAD_TIMES[i]);
            g_failures++;
        }
        otc_close(rel);
        /* a malformed build time is not found (null), and the release still opens */
        snprintf(extra, sizeof extra, ",\"provenance\":{\"build\":{\"build_commit\":\"abc\",\"built_at\":\"%s\"}}",
                 BAD_TIMES[i]);
        CHECK_STATUS(open_with(dir, "2099-12-31T00:00:00Z", extra, &rel), OTC_OK);
        if (rel) {
            otc_station_t *st = NULL;
            const otc_set *set = NULL;
            const otc_provenance_build *b = NULL;
            CHECK_STATUS(otc_station(rel, "OTC-X-1", &st), OTC_OK);
            if (st && otc_station_recommended_set(st, &set) == OTC_OK && otc_set_provenance_build(set, &b) == OTC_OK) {
                otc_status bs = otc_provenance_build_built_at(b, buf, sizeof buf, &need);
                if (bs != OTC_E_NOT_FOUND) {
                    fprintf(stderr, "built_at %s: status %d (%s), want not found\n", BAD_TIMES[i], (int)bs,
                            bs == OTC_OK ? buf : "-");
                    g_failures++;
                }
            } else {
                fprintf(stderr, "built_at %s: no build\n", BAD_TIMES[i]);
                g_failures++;
            }
            otc_station_free(st);
        }
        otc_close(rel);
    }
    want("2096-02-29T00:00:00Z", "2096-02-29T00:00:00Z");
    want("0001-01-01T01:00:00+01:00", "0001-01-01T00:00:00Z");
    /* HTTP dates: impossible fields and the wrong weekday are malformed */
    CHECK(otc__http_date("Sat, 30 Feb 2099 00:00:00 GMT") == -1);
    CHECK(otc__http_date("Sun, 31 Feb 2099 00:00:00 GMT") == -1);
    CHECK(otc__http_date("Sun, 29 Feb 2099 00:00:00 GMT") == -1);
    CHECK(otc__http_date("Thu, 31 Dec 2099 24:00:00 GMT") == -1);
    CHECK(otc__http_date("Thu, 31 Dec 2099 23:59:60 GMT") == -1);
    CHECK(otc__http_date("Wed, 31 Dec 2099 23:59:59 GMT") == -1);
    CHECK(otc__http_date("Mon, 31 Feb 2000 00:00:00 GMT") == -1);
    CHECK(otc__http_date("Tue, 29 Feb 2000 00:00:00 GMT") == 951782400LL);
}

int main(void)
{
    char *dir = test_tmpdir(), *path, buf[64];
    otc_release *rel = NULL;
    size_t need;
    dr6(dir);
    want("2099-12-31T02:00:00.5+02:00", "2099-12-31T00:00:00Z");
    want("2099-12-31T00:00:00Z", "2099-12-31T00:00:00Z");
    want("2099-12-31t23:30:00z", "2099-12-31T23:30:00Z");
    want("2099-12-31T23:30:00-01:00", "2100-01-01T00:30:00Z");
    want("2000-03-01T00:30:00+01:00", "2000-02-29T23:30:00Z");
    want("1970-01-01T00:00:00+00:30", "1969-12-31T23:30:00Z");
    want("2099-12-31T00:00:00", "2099-12-31T00:00:00Z");
    want("2099-12-31", NULL);
    want("2099-12-31T00:00:00+0200", NULL);
    want("not a time", NULL);
    CHECK(otc__http_date("Sun, 06 Nov 1994 08:49:37 GMT") == 784111777LL);
    CHECK(otc__http_date("Thu, 01 Jan 1970 00:00:00 GMT") == 0);
    CHECK(otc__http_date("Thu, 31 Dec 2099 23:59:59 GMT") == 4102444799LL);
    CHECK(otc__http_date("Sun, 06 Nov 1994 08:49:37 UTC") == -1);
    CHECK(otc__http_date("120") == -1);
    CHECK(otc__http_date("Sunday, 06-Nov-94 08:49:37 GMT") == -1);
    /* through the API */
    test_write(dir, "OTC_20990101.meta.json",
               "{\"format_version\":\"1.0\",\"release\":{\"datestamp\":\"20990101\",\"created\":\"2099-12-31T02:00:00.5+02:00\"},"
               "\"conventions\":[{\"convention_id\":\"c1\"}],\"licences\":[{\"licence_id\":\"l1\"}]}");
    test_write(dir, "OTC_20990101.jsonl", TEST_STATION("OTC-X-1", "One") "\n");
    path = test_join(dir, "OTC_20990101.jsonl");
    CHECK_STATUS(otc_open_file(path, NULL, &rel), OTC_OK);
    if (rel) {
        CHECK_STATUS(otc_release_created(rel, buf, sizeof buf, &need), OTC_OK);
        CHECK(!strcmp(buf, "2099-12-31T00:00:00Z"));
    }
    otc_close(rel);
    free(path);
    free(dir);
    return test_done("test_time");
}
