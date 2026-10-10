/* PK15 / C11: otc_attribution edge cases (spec 4.6, CR D2):
 *  - an unknown (or removed) station id is OTC_E_INVALID_ARGUMENT, never skipped;
 *  - an empty list gives the full-release text, as ids = NULL does;
 *  - a licence with no provider prints its attribution alone, and is never
 *    merged with another such licence. */
#include "otc_test.h"

#define META "{\"format_version\":\"1.0\",\"release\":{\"datestamp\":\"20990101\",\"concept_doi\":\"10.1/x\"}," \
    "\"conventions\":[{\"convention_id\":\"c1\"}],\"licences\":[" \
    "{\"licence_id\":\"a\",\"commercial_use\":true,\"provider\":\"P\",\"attribution\":\"A1\"}," \
    "{\"licence_id\":\"b\",\"commercial_use\":true,\"attribution\":\"Anonymous B\"}," \
    "{\"licence_id\":\"c\",\"commercial_use\":true,\"attribution\":\"Anonymous C\"}," \
    "{\"licence_id\":\"d\",\"commercial_use\":true,\"provider\":\"P\",\"attribution\":\"A2\"}]}"

#define ST(id, lic) "{\"station_id\":\"" id "\",\"status\":\"active\",\"name\":\"N\",\"lat\":1,\"lon\":1,\"type\":\"reference\"," \
    "\"recommended_set_id\":\"" id "/s\",\"constant_sets\":[{\"set_id\":\"" id "/s\",\"source\":\"x\",\"quantity\":\"water_level\"," \
    "\"qc_status\":\"ok\",\"convention_id\":\"c1\",\"licence_id\":\"" lic "\"}]}\n"

int main(void)
{
    char *dir = test_tmpdir(), *path, buf[1024], full[1024];
    otc_release *rel = NULL;
    size_t need;
    const char *one[] = {"OTC-X-2"}, *bad[] = {"OTC-X-1", "OTC-X-9"}, *gone[] = {"OTC-X-3"};
    test_write(dir, "OTC_20990101.meta.json", META);
    test_write(dir, "OTC_20990101.jsonl", ST("OTC-X-1", "a") ST("OTC-X-2", "b")
               "{\"station_id\":\"OTC-X-3\",\"status\":\"removed\",\"name\":\"G\"}\n");
    path = test_join(dir, "OTC_20990101.jsonl");
    CHECK_STATUS(otc_open_file(path, NULL, &rel), OTC_OK);
    if (!rel) return test_done("test_attribution");
    CHECK_STATUS(otc_attribution(rel, NULL, 0, full, sizeof full, &need), OTC_OK);
    CHECK(!strcmp(full, "Tidal constants: OpenTideConstants 20990101, doi:10.1/x, CC BY 4.0. Sources: P: A1; Anonymous B; "
                        "Anonymous C"));
    if (strcmp(full, "Tidal constants: OpenTideConstants 20990101, doi:10.1/x, CC BY 4.0. Sources: P: A1; Anonymous B; Anonymous C"))
        fprintf(stderr, "full: %s\n", full);
    CHECK_STATUS(otc_attribution(rel, one, 0, buf, sizeof buf, &need), OTC_OK);
    CHECK(!strcmp(buf, full));
    CHECK_STATUS(otc_attribution(rel, one, 1, buf, sizeof buf, &need), OTC_OK);
    CHECK(!strcmp(buf, "Tidal constants: OpenTideConstants 20990101, doi:10.1/x, CC BY 4.0. Sources: Anonymous B"));
    CHECK_STATUS(otc_attribution(rel, bad, 2, buf, sizeof buf, &need), OTC_E_INVALID_ARGUMENT);
    CHECK_STATUS(otc_attribution(rel, gone, 1, buf, sizeof buf, &need), OTC_E_INVALID_ARGUMENT);
    otc_close(rel);
    free(path);
    free(dir);
    return test_done("test_attribution");
}
