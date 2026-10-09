/* PK08 / B2-4: release.created is returned in UTC, YYYY-MM-DDTHH:MM:SSZ
 * (otc__utc_time), the same as the other SDKs. */
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

int main(void)
{
    char *dir = test_tmpdir(), *path, buf[64];
    otc_release *rel = NULL;
    size_t need;
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
