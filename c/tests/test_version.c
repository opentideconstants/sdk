/* PK03: a format_version (C10) or min_reader_version (C1) that is present
 * but is not MAJOR.MINOR (two non-negative integers with no leading zeros,
 * joined by one dot) fails the open with OTC_E_INVALID_RELEASE (spec 7.4,
 * CR D9); so does a format_version that is not a string, or is absent. */
#include "otc_test.h"

/* fv_json NULL: no format_version key at all */
static otc_status open_with(const char *fv_json, const char *mrv_json)
{
    char *dir = test_tmpdir(), meta[1024], *path;
    otc_release *rel = NULL;
    otc_status st;
    snprintf(meta, sizeof meta,
             "{%s%s%s\"release\":{\"datestamp\":\"20990101\"%s%s},"
             "\"conventions\":[{\"convention_id\":\"c1\"}],\"licences\":[{\"licence_id\":\"l1\",\"commercial_use\":true,\"attribution\":\"A\"}]}",
             fv_json ? "\"format_version\":" : "", fv_json ? fv_json : "", fv_json ? "," : "", mrv_json ? ",\"min_reader_version\":" : "", mrv_json ? mrv_json : "");
    test_write(dir, "OTC_20990101.meta.json", meta);
    test_write(dir, "OTC_20990101.jsonl", TEST_STATION("OTC-X-1", "Somewhere") "\n");
    path = test_join(dir, "OTC_20990101.jsonl");
    st = otc_open_file(path, NULL, &rel);
    otc_close(rel);
    free(path);
    free(dir);
    return st;
}

int main(void)
{
    static const char *const bad_fv[] = {"\"1.\"", "\"1.x\"", "\" 1.0\"", "\"+1.0\"", "\"1.0.0\"", "\"01.0\"",
                                         "\"1.00\"", "\"1\"", "\"1.-1\"", "\"1.0 \"", NULL};
    size_t i;
    CHECK_STATUS(open_with("\"1.0\"", NULL), OTC_E_INVALID_RELEASE);
    CHECK_STATUS(open_with("\"1.7\"", NULL), OTC_E_INVALID_RELEASE);
    CHECK_STATUS(open_with("\"1.7\"", "\"1.0\""), OTC_OK);
    CHECK_STATUS(open_with("\"2.0\"", NULL), OTC_E_UNSUPPORTED_FORMAT);
    /* a format_version that is not a string, or is absent, is no version either */
    CHECK_STATUS(open_with("1.0", NULL), OTC_E_INVALID_RELEASE);
    CHECK_STATUS(open_with("1", NULL), OTC_E_INVALID_RELEASE);
    CHECK_STATUS(open_with("null", NULL), OTC_E_INVALID_RELEASE);
    CHECK_STATUS(open_with("[\"1.0\"]", NULL), OTC_E_INVALID_RELEASE);
    CHECK_STATUS(open_with(NULL, NULL), OTC_E_INVALID_RELEASE);
    for (i = 0; bad_fv[i]; i++) {
        otc_status st = open_with(bad_fv[i], NULL);
        if (st != OTC_E_INVALID_RELEASE) fprintf(stderr, "format_version %s: %s\n", bad_fv[i], otc_status_code(st));
        CHECK(st == OTC_E_INVALID_RELEASE);
    }
    /* min_reader_version: present, so it must be a valid version (a number or a malformed string fails closed) */
    CHECK_STATUS(open_with("\"1.0\"", "\"1.0\""), OTC_OK);
    CHECK_STATUS(open_with("\"1.0\"", "\"1.1\""), OTC_E_READER_TOO_OLD);
    CHECK_STATUS(open_with("\"1.0\"", "null"), OTC_E_INVALID_RELEASE);
    for (i = 0; bad_fv[i]; i++) {
        otc_status st = open_with("\"1.0\"", bad_fv[i]);
        if (st != OTC_E_INVALID_RELEASE) fprintf(stderr, "min_reader_version %s: %s\n", bad_fv[i], otc_status_code(st));
        CHECK(st == OTC_E_INVALID_RELEASE);
    }
    CHECK_STATUS(open_with("\"1.0\"", "2"), OTC_E_INVALID_RELEASE);
    CHECK_STATUS(open_with("\"1.0\"", "\"2\""), OTC_E_INVALID_RELEASE);
    /* D18: a file name that is not OTC_<D>.jsonl is invalid_argument */
    {
        static const char *const bad_names[] = {"release.jsonl", "OTC_2099.jsonl", "OTC_20990101.01.jsonl",
                                                "OTC_20990101.1234567890.jsonl", "otc_20990101.jsonl", NULL};
        char *dir = test_tmpdir();
        size_t k;
        for (k = 0; bad_names[k]; k++) {
            char base[64], meta[80], *path;
            otc_release *rel = NULL;
            otc_status st;
            snprintf(base, sizeof base, "%.*s", (int)(strlen(bad_names[k]) - 6), bad_names[k]);
            snprintf(meta, sizeof meta, "%s.meta.json", base);
            test_write(dir, meta, TEST_META("20990101"));
            test_write(dir, bad_names[k], TEST_STATION("OTC-X-1", "One") "\n");
            path = test_join(dir, bad_names[k]);
            st = otc_open_file(path, NULL, &rel);
            if (st != OTC_E_INVALID_ARGUMENT) fprintf(stderr, "%s: %s\n", bad_names[k], otc_status_code(st));
            CHECK(st == OTC_E_INVALID_ARGUMENT);
            otc_close(rel);
            free(path);
        }
        free(dir);
    }
    return test_done("test_version");
}
