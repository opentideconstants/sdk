/* PK-R2-08 (CR2 DR33): strings that hold a NUL (valid JSON, and schema-valid
 * for a station name, an alias id and a set_id).
 *  - every (buf, len, needed) accessor copies the whole string, and needed
 *    counts every byte; otc_hit.name_len is the name's full length (R2-070,
 *    R2-071);
 *  - a lookup by the part before the NUL finds nothing (R2-071);
 *  - two set_ids that differ only after a NUL are two sets (R2-071);
 *  - a name under an escaped "name" key keeps its tail (R2-072). */
#include "otc_test.h"
#include "otc_internal.h"

#define NUL_SET(id)                                                                                 \
    "{\"set_id\":\"" id "\",\"source\":\"src\",\"source_type\":\"official\",\"quantity\":\"water_level\"," \
    "\"qc_status\":\"ok\",\"convention_id\":\"c1\",\"licence_id\":\"l1\",\"constituents\":[{\"name\":\"M2\","  \
    "\"amplitude_m\":1.0,\"phase_deg\":10.0}]}"

/* OTC-X-1: a name, two alias ids and two set_ids with a NUL inside. OTC-X-2:
 * its name under the key "name". */
static const char LINES[] =
    "{\"station_id\":\"OTC-X-1\",\"status\":\"active\",\"name\":\"Me\\u0000da\",\"lat\":1.0,\"lon\":2.0,"
    "\"type\":\"reference\",\"aliases\":{\"xtide\":\"San\\u0000Francisco\",\"gesla\":[\"g\\u00001\",\"g2\"]},"
    "\"recommended_set_id\":\"OTC-X-1/no\\u0000aa\",\"constant_sets\":["
    NUL_SET("OTC-X-1/gesla\\u0000fit") "," NUL_SET("OTC-X-1/no\\u0000aa") "]}\n"
    "{\"station_id\":\"OTC-X-2\",\"status\":\"active\",\"n\\u0061me\":\"Ab\\u0000cd\",\"lat\":1.0,\"lon\":2.0,"
    "\"type\":\"reference\",\"recommended_set_id\":\"OTC-X-2/s\",\"constant_sets\":[" NUL_SET("OTC-X-2/s") "]}\n";

/* Two set_ids that differ only after the NUL: two sets, and the second is the recommended one. */
static const char TWIN_LINES[] =
    "{\"station_id\":\"OTC-X-3\",\"status\":\"active\",\"name\":\"Twin\",\"lat\":1.0,\"lon\":2.0,"
    "\"type\":\"reference\",\"recommended_set_id\":\"OTC-X-3/no\\u0000bb\",\"constant_sets\":["
    NUL_SET("OTC-X-3/no\\u0000aa") "," NUL_SET("OTC-X-3/no\\u0000bb") "]}\n";

static char *g_dir, *g_jsonl;

/* The accessor gives exactly the n bytes of want, then a NUL, and needed n + 1. */
#define CHECK_BYTES(call_buf, call_size, want, n)                                                    \
    do {                                                                                            \
        char b_[64];                                                                                \
        size_t need_ = 0, need2_ = 0;                                                               \
        memset(b_, 'x', sizeof b_);                                                                 \
        CHECK_STATUS(call_size, OTC_OK);                                                            \
        CHECK_STATUS(call_buf, OTC_OK);                                                             \
        CHECK(need_ == (n) + 1);                                                                    \
        CHECK(!memcmp(b_, want, (n)) && b_[(n)] == '\0');                                           \
    } while (0)

static void check_station_one(otc_release *rel)
{
    otc_station_t *st = NULL, *by = NULL;
    const otc_set *set = NULL;
    CHECK_STATUS(otc_station(rel, "OTC-X-1", &st), OTC_OK);
    if (!st) return;
    CHECK_BYTES(otc_station_name(st, b_, sizeof b_, &need_), otc_station_name(st, NULL, 0, &need2_), "Me\0da", 5);
    CHECK_BYTES(otc_station_alias_at(st, "xtide", 0, b_, sizeof b_, &need_),
                otc_station_alias_at(st, "xtide", 0, NULL, 0, &need2_), "San\0Francisco", 13);
    CHECK_BYTES(otc_station_alias_at(st, "gesla", 0, b_, sizeof b_, &need_),
                otc_station_alias_at(st, "gesla", 0, NULL, 0, &need2_), "g\0" "1", 3);
    CHECK_STATUS(otc_station_recommended_set(st, &set), OTC_OK);
    if (set) CHECK_BYTES(otc_set_set_id(set, b_, sizeof b_, &need_), otc_set_set_id(set, NULL, 0, &need2_), "OTC-X-1/no\0aa", 13);
    CHECK(otc_station_set_count(st, true) == 2);
    {   /* the raw JSON keeps the tail too */
        char raw[2048];
        size_t need = 0;
        CHECK_STATUS(otc_station_raw_json(st, raw, sizeof raw, &need), OTC_OK);
        CHECK(need == strlen(raw) + 1);
        CHECK(strstr(raw, "Me\\u0000da") != NULL);
        CHECK(strstr(raw, "San\\u0000Francisco") != NULL);
    }
    /* the part before the NUL is another value */
    set = NULL;
    CHECK_STATUS(otc_station_set(st, "OTC-X-1/no", &set), OTC_E_NOT_FOUND);
    CHECK(set == NULL);
    CHECK_STATUS(otc_station_by_alias(rel, "xtide", "San", &by), OTC_E_NOT_FOUND);
    otc_station_free(by);
    by = NULL;
    CHECK_STATUS(otc_station_by_alias(rel, "gesla", "g", &by), OTC_E_NOT_FOUND);
    otc_station_free(by);
    by = NULL;
    CHECK_STATUS(otc_station_by_alias(rel, "gesla", "g2", &by), OTC_OK);
    otc_station_free(by);
    otc_station_free(st);
}

/* The one hit gives the whole name: otc_hit.name_len counts the bytes after the NUL too. */
static void check_search(otc_release *rel, const char *q, const char *want_id, const char *want_name, size_t name_len)
{
    otc_hit hits[4];
    size_t count = 0;
    CHECK_STATUS(otc_search(rel, q, NULL, 4, hits, 4, &count), OTC_OK);
    CHECK(count == 1);
    if (count == 1) {
        CHECK(!strcmp(hits[0].id, want_id));
        CHECK(hits[0].name_len == name_len);
        CHECK(!memcmp(hits[0].name, want_name, name_len) && hits[0].name[name_len] == '\0');
    }
}

static void check_release(int want_index)
{
    otc_release *rel = NULL;
    otc_station_t *st = NULL;
    CHECK_STATUS(otc_open_file(g_jsonl, NULL, &rel), OTC_OK);
    if (!rel) return;
    CHECK(rel->index_used == want_index);
    check_station_one(rel);
    check_search(rel, "da", "OTC-X-1", "Me\0da", 5);   /* after the NUL */
    check_search(rel, "cd", "OTC-X-2", "Ab\0cd", 5);   /* after the NUL, under the escaped key */
    CHECK_STATUS(otc_station(rel, "OTC-X-2", &st), OTC_OK);
    if (st) CHECK_BYTES(otc_station_name(st, b_, sizeof b_, &need_), otc_station_name(st, NULL, 0, &need2_), "Ab\0cd", 5);
    otc_station_free(st);
    otc_close(rel);
}

int main(void)
{
    char sums[512], hex_l[65], hex_m[65], *ixp, *mp;
    otc_release *rel = NULL;
    g_dir = test_tmpdir();
    test_write(g_dir, "OTC_20990101.meta.json", TEST_META("20990101"));
    test_write(g_dir, "OTC_20990101.jsonl", LINES);
    g_jsonl = test_join(g_dir, "OTC_20990101.jsonl");
    mp = test_join(g_dir, "OTC_20990101.meta.json");
    ixp = test_join(g_dir, "index-v1.json");
    otc__sha256_file(g_jsonl, hex_l);
    otc__sha256_file(mp, hex_m);
    snprintf(sums, sizeof sums, "%s  OTC_20990101.jsonl\n%s  OTC_20990101.meta.json\n", hex_l, hex_m);
    test_write(g_dir, "OTC_20990101.sha256", sums);

    /* from the .jsonl */
    check_release(0);

    {   /* set_ids that differ only after the NUL */
        char *dir2 = test_tmpdir(), *jl2;
        otc_station_t *st = NULL;
        const otc_set *set = NULL;
        test_write(dir2, "OTC_20990101.meta.json", TEST_META("20990101"));
        test_write(dir2, "OTC_20990101.jsonl", TWIN_LINES);
        jl2 = test_join(dir2, "OTC_20990101.jsonl");
        rel = NULL;
        CHECK_STATUS(otc_open_file(jl2, NULL, &rel), OTC_OK);
        if (rel) CHECK_STATUS(otc_station(rel, "OTC-X-3", &st), OTC_OK);
        if (st) {
            CHECK(otc_station_set_count(st, true) == 2);
            CHECK_STATUS(otc_station_recommended_set(st, &set), OTC_OK);
            if (set) CHECK_BYTES(otc_set_set_id(set, b_, sizeof b_, &need_), otc_set_set_id(set, NULL, 0, &need2_),
                                 "OTC-X-3/no\0bb", 13);
            CHECK_STATUS(otc_station_set_at(st, true, 1, &set), OTC_OK);
            if (set) CHECK_BYTES(otc_set_set_id(set, b_, sizeof b_, &need_), otc_set_set_id(set, NULL, 0, &need2_),
                                 "OTC-X-3/no\0aa", 13);
        }
        otc_station_free(st);
        otc_close(rel);
        free(jl2);
        free(dir2);
    }

    free(ixp);
    free(mp);
    free(g_jsonl);
    free(g_dir);
    return test_done("test_nul");
}
