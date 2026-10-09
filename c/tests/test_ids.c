/* PK06: repeated ids fail the open with invalid_release (spec 6.1, CR D5):
 * C36 - a station_id across active stations and tombstones (also two active
 * stations), a repeated
 * tombstone id, a repeated (system, alias id) pair, a repeated convention_id
 * or licence_id; C5 - a repeated set_id in a station or across the release. C39: a link that does
 * not resolve fails the open too (recommended_set_id, the offsets'
 * reference_station_id and licence_id; spec 4.5, CR D5). Each negative has a
 * control: the same fixture without the repeat opens. */
#include "otc_test.h"

#define TOMB(id) "{\"station_id\":\"" id "\",\"status\":\"removed\",\"name\":\"Gone\",\"removed_in\":\"20980101\",\"removed_reason\":\"duplicate\"}"

static otc_status open_lines(const char *meta, const char *lines)
{
    char *dir = test_tmpdir(), *path;
    otc_release *rel = NULL;
    otc_status st;
    test_write(dir, "OTC_20990101.meta.json", meta);
    test_write(dir, "OTC_20990101.jsonl", lines);
    path = test_join(dir, "OTC_20990101.jsonl");
    st = otc_open_file(path, NULL, &rel);
    otc_close(rel);
    free(path);
    free(dir);
    return st;
}

int main(void)
{
    static const char *meta = TEST_META("20990101");
    CHECK_STATUS(open_lines(meta, TEST_STATION("OTC-X-1", "One") "\n" TEST_STATION("OTC-X-2", "Two") "\n" TOMB("OTC-X-3") "\n"),
                 OTC_OK);
    /* C36 */
    CHECK_STATUS(open_lines(meta, TEST_STATION("OTC-X-1", "One") "\n" TEST_STATION("OTC-X-1", "Two") "\n"), OTC_E_INVALID_RELEASE);
    CHECK_STATUS(open_lines(meta, TEST_STATION("OTC-X-1", "One") "\n" TOMB("OTC-X-1") "\n"), OTC_E_INVALID_RELEASE);
    CHECK_STATUS(open_lines(meta, TEST_STATION("OTC-X-1", "One") "\n" TOMB("OTC-X-3") "\n" TOMB("OTC-X-3") "\n"),
                 OTC_E_INVALID_RELEASE);
    CHECK_STATUS(open_lines(meta,
                            "{\"station_id\":\"OTC-X-1\",\"status\":\"active\",\"name\":\"A\",\"lat\":1,\"lon\":1,\"type\":\"reference\","
                            "\"aliases\":{\"noaa\":\"9900001\"},\"constant_sets\":[]}\n"
                            "{\"station_id\":\"OTC-X-2\",\"status\":\"active\",\"name\":\"B\",\"lat\":1,\"lon\":1,\"type\":\"reference\","
                            "\"aliases\":{\"noaa\":[\"9900002\",\"9900001\"]},\"constant_sets\":[]}\n"),
                 OTC_E_INVALID_RELEASE);
    /* its control: the same shapes (a string alias, an array of them) with no pair repeated */
    CHECK_STATUS(open_lines(meta,
                            "{\"station_id\":\"OTC-X-1\",\"status\":\"active\",\"name\":\"A\",\"lat\":1,\"lon\":1,\"type\":\"reference\","
                            "\"aliases\":{\"noaa\":\"9900001\"},\"constant_sets\":[]}\n"
                            "{\"station_id\":\"OTC-X-2\",\"status\":\"active\",\"name\":\"B\",\"lat\":1,\"lon\":1,\"type\":\"reference\","
                            "\"aliases\":{\"noaa\":[\"9900002\",\"9900003\"]},\"constant_sets\":[]}\n"),
                 OTC_OK);
    CHECK_STATUS(open_lines("{\"format_version\":\"1.0\",\"release\":{\"datestamp\":\"20990101\"},"
                            "\"conventions\":[{\"convention_id\":\"c1\"},{\"convention_id\":\"c1\"}],\"licences\":[{\"licence_id\":\"l1\"}]}",
                            TEST_STATION("OTC-X-1", "One") "\n"),
                 OTC_E_INVALID_RELEASE);
    CHECK_STATUS(open_lines("{\"format_version\":\"1.0\",\"release\":{\"datestamp\":\"20990101\"},"
                            "\"conventions\":[{\"convention_id\":\"c1\"}],\"licences\":[{\"licence_id\":\"l1\"},{\"licence_id\":\"l1\"}]}",
                            TEST_STATION("OTC-X-1", "One") "\n"),
                 OTC_E_INVALID_RELEASE);
    /* C5: a repeated set_id in one station (the recommended one, so the index entry would get two) */
    CHECK_STATUS(open_lines(meta,
                            "{\"station_id\":\"OTC-X-1\",\"status\":\"active\",\"name\":\"A\",\"lat\":1,\"lon\":1,\"type\":\"reference\","
                            "\"recommended_set_id\":\"s\",\"constant_sets\":["
                            "{\"set_id\":\"s\",\"source\":\"a\",\"source_type\":\"official\",\"quantity\":\"water_level\",\"qc_status\":\"ok\",\"convention_id\":\"c1\",\"licence_id\":\"l1\"},"
                            "{\"set_id\":\"s\",\"source\":\"b\",\"source_type\":\"model\",\"quantity\":\"water_level\",\"qc_status\":\"ok\",\"convention_id\":\"c1\",\"licence_id\":\"l1\"}]}\n"),
                 OTC_E_INVALID_RELEASE);
    /* its control: the same two sets with different set_ids */
    CHECK_STATUS(open_lines(meta,
                            "{\"station_id\":\"OTC-X-1\",\"status\":\"active\",\"name\":\"A\",\"lat\":1,\"lon\":1,\"type\":\"reference\","
                            "\"recommended_set_id\":\"s\",\"constant_sets\":["
                            "{\"set_id\":\"s\",\"source\":\"a\",\"source_type\":\"official\",\"quantity\":\"water_level\",\"qc_status\":\"ok\",\"convention_id\":\"c1\",\"licence_id\":\"l1\"},"
                            "{\"set_id\":\"t\",\"source\":\"b\",\"source_type\":\"model\",\"quantity\":\"water_level\",\"qc_status\":\"ok\",\"convention_id\":\"c1\",\"licence_id\":\"l1\"}]}\n"),
                 OTC_OK);
    /* C5 (PK-R2-09): a set_id is unique across the release, so two stations cannot share one */
    CHECK_STATUS(open_lines(meta,
                            "{\"station_id\":\"OTC-X-1\",\"status\":\"active\",\"name\":\"A\",\"lat\":1,\"lon\":1,\"type\":\"reference\","
                            "\"recommended_set_id\":\"s\",\"constant_sets\":["
                            "{\"set_id\":\"s\",\"source\":\"a\",\"source_type\":\"official\",\"quantity\":\"water_level\",\"qc_status\":\"ok\",\"convention_id\":\"c1\",\"licence_id\":\"l1\"}]}\n"
                            "{\"station_id\":\"OTC-X-2\",\"status\":\"active\",\"name\":\"B\",\"lat\":1,\"lon\":1,\"type\":\"reference\","
                            "\"recommended_set_id\":\"s\",\"constant_sets\":["
                            "{\"set_id\":\"s\",\"source\":\"b\",\"source_type\":\"model\",\"quantity\":\"water_level\",\"qc_status\":\"ok\",\"convention_id\":\"c1\",\"licence_id\":\"l1\"}]}\n"),
                 OTC_E_INVALID_RELEASE);
    /* C39 */
    CHECK_STATUS(open_lines(meta,
                            "{\"station_id\":\"OTC-X-1\",\"status\":\"active\",\"name\":\"A\",\"lat\":1,\"lon\":1,\"type\":\"reference\","
                            "\"recommended_set_id\":\"nope\",\"constant_sets\":[]}\n"),
                 OTC_E_INVALID_RELEASE);
    CHECK_STATUS(open_lines(meta, TEST_STATION("OTC-X-1", "One") "\n"
                            "{\"station_id\":\"OTC-X-2\",\"status\":\"active\",\"name\":\"B\",\"lat\":1,\"lon\":1,\"type\":\"subordinate\","
                            "\"subordinate_offsets\":{\"reference_station_id\":\"OTC-X-9\",\"licence_id\":\"l1\"},\"constant_sets\":[]}\n"),
                 OTC_E_INVALID_RELEASE);
    CHECK_STATUS(open_lines(meta, TEST_STATION("OTC-X-1", "One") "\n"
                            "{\"station_id\":\"OTC-X-2\",\"status\":\"active\",\"name\":\"B\",\"lat\":1,\"lon\":1,\"type\":\"subordinate\","
                            "\"subordinate_offsets\":{\"reference_station_id\":\"OTC-X-1\",\"licence_id\":\"nope\"},\"constant_sets\":[]}\n"),
                 OTC_E_INVALID_RELEASE);
    CHECK_STATUS(open_lines(meta, TEST_STATION("OTC-X-1", "One") "\n"
                            "{\"station_id\":\"OTC-X-2\",\"status\":\"active\",\"name\":\"B\",\"lat\":1,\"lon\":1,\"type\":\"subordinate\","
                            "\"subordinate_offsets\":{\"reference_station_id\":\"OTC-X-1\",\"licence_id\":\"l1\"},\"constant_sets\":[]}\n"),
                 OTC_OK);
    return test_done("test_ids");
}
