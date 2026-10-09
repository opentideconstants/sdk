/* PK10 error classification in the core library.
 * C38: otc_require_station for a removed id whose tombstone line cannot be
 *      read reports that failure, not station_removed with "?" fields.
 * C46: otc_station_offsets on a station with no offsets (NOT_FOUND) leaves
 *      no stale values from an earlier call in *out. */
#include "otc_test.h"

#include <math.h>

#define TOMB(id) "{\"station_id\":\"" id "\",\"status\":\"removed\",\"name\":\"Gone\",\"removed_in\":\"20980101\",\"removed_reason\":\"merged\",\"merged_into\":\"OTC-X-1\"}"

int main(void)
{
    char *dir = test_tmpdir(), *path, msg[512];
    otc_release *rel = NULL;
    otc_station_t *st = NULL;
    size_t need;
    FILE *f;
    test_write(dir, "OTC_20990101.meta.json", TEST_META("20990101"));
    test_write(dir, "OTC_20990101.jsonl", TEST_STATION("OTC-X-1", "One") "\n" TOMB("OTC-X-2") "\n");
    path = test_join(dir, "OTC_20990101.jsonl");
    CHECK_STATUS(otc_open_file(path, NULL, &rel), OTC_OK);
    if (!rel) return test_done("test_errors");
    CHECK_STATUS(otc_require_station(rel, "OTC-X-2", &st), OTC_E_STATION_REMOVED);
    otc_last_error(rel, msg, sizeof msg, &need);
    CHECK(strstr(msg, "merged into OTC-X-1") != NULL);
    /* the file changes under the open handle: the tombstone line is no longer JSON */
    f = fopen(path, "r+b");
    fseek(f, -20, SEEK_END);
    fputs("#################\n", f);
    fclose(f);
    CHECK_STATUS(otc_require_station(rel, "OTC-X-2", &st), OTC_E_INVALID_RELEASE);
    otc_last_error(rel, msg, sizeof msg, &need);
    CHECK(strstr(msg, "removed in ?") == NULL && strstr(msg, "not JSON") != NULL);
    if (strstr(msg, "removed in ?")) fprintf(stderr, "message: %s\n", msg);
    otc_close(rel);
    rel = NULL;
    /* C46 */
    test_write(dir, "OTC_20990101.jsonl", TEST_STATION("OTC-X-1", "One") "\n"
               "{\"station_id\":\"OTC-X-2\",\"status\":\"active\",\"name\":\"B\",\"lat\":1,\"lon\":1,\"type\":\"subordinate\","
               "\"subordinate_offsets\":{\"reference_station_id\":\"OTC-X-1\",\"licence_id\":\"l1\",\"time_offset_high_min\":12},"
               "\"constant_sets\":[]}\n");
    CHECK_STATUS(otc_open_file(path, NULL, &rel), OTC_OK);
    if (rel) {
        otc_station_t *sub = NULL, *ref = NULL;
        otc_offsets_t off;
        memset(&off, 0, sizeof off);
        off.struct_size = sizeof off;
        CHECK_STATUS(otc_station(rel, "OTC-X-2", &sub), OTC_OK);
        CHECK_STATUS(otc_station(rel, "OTC-X-1", &ref), OTC_OK);
        CHECK_STATUS(otc_station_offsets(sub, &off), OTC_OK);
        CHECK(off.time_offset_high_min == 12 && off.reference_station_id != NULL);
        CHECK_STATUS(otc_station_offsets(ref, &off), OTC_E_NOT_FOUND);
        CHECK(off.reference_station_id == NULL && off.licence_id == NULL && isnan(off.time_offset_high_min));
        CHECK(off.struct_size == sizeof off);
        otc_station_free(sub);
        otc_station_free(ref);
    }
    otc_close(rel);
    free(path);
    free(dir);
    return test_done("test_errors");
}
