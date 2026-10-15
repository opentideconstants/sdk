/* PK05 / C2: the stream index (index-v1.json, spec 6.2, CR D4).
 *  - an entry whose line is another station's: the query is invalid_release
 *    (never the wrong station), and index-v1.json is deleted;
 *  - an entry with length 0, or offsets that do not increase: the index is
 *    stale, so the open rebuilds from the .jsonl and the query is right, on
 *    this open and the next (otc_open_file only reads the index: the fetch
 *    layer rewrites a stale one, test_fetch_index_stale).
 * Each helper step that sets a case up must work (else exit 2), so a case
 * cannot pass because its index was never written as meant. */
#include "otc_test.h"
#include "otc_internal.h"

static char *g_dir, *g_jsonl;

/* The finite B28 oracle is approved independently of the SDK. Exercise the
 * same native emitter used by this generated-index writer, not a fake. */
static char *encode_cache_document(const cJSON *document)
{
    char *bytes = NULL;
    (void)otc__encode_cache_json(document, &bytes);
    return bytes;
}

static void cache_regression(void)
{
    static const char input[] = "{\"z\\n\":\"x\\u0000y\",\"a\":[0.000001,1e21,-0.0]}";
    cJSON *document = otc__json_parse(input, sizeof input - 1);
    cJSON *invalid = cJSON_CreateString("\xed\xa0\x80");
    cJSON *raw = cJSON_CreateRaw("\"x\\u0000y\"");
    char before[128], after[128], *bytes = NULL;
    size_t needed;
    CHECK(document != NULL && invalid != NULL && raw != NULL);
    CHECK_STATUS(otc__copy_json(document, before, sizeof before, &needed), OTC_OK);
    CHECK_STATUS(otc__encode_cache_json(document, &bytes), OTC_OK);
    CHECK(bytes && !strcmp(bytes, "{\"a\":[0.000001,1e21,0],\"z\\u000a\":\"x\\u0000y\"}"));
    free(bytes);
    CHECK_STATUS(otc__copy_json(document, after, sizeof after, &needed), OTC_OK);
    CHECK(!strcmp(before, after));   /* encoding never mutates the source tree/raw accessor */
    CHECK_STATUS(otc__encode_cache_json(invalid, &bytes), OTC_E_INVALID_ARGUMENT);
    CHECK(bytes == NULL);
    CHECK_STATUS(otc__encode_cache_json(raw, &bytes), OTC_OK);
    CHECK(bytes && !strcmp(bytes, "\"x\\u0000y\""));
    free(bytes);
    CHECK_STATUS(otc__encode_cache_json(NULL, &bytes), OTC_E_INVALID_ARGUMENT);
    CHECK(bytes == NULL);
    CHECK_STATUS(otc__encode_cache_json(document, NULL), OTC_E_INVALID_ARGUMENT);
    cJSON_Delete(document);
    cJSON_Delete(invalid);
    cJSON_Delete(raw);
}

static int cache_goldens(const char *path)
{
    char *text;
    size_t length;
    cJSON *golden, *row;
    CHECK_STATUS(otc__read_all(path, &text, &length), OTC_OK);
    golden = otc__json_parse(text, length);
    free(text);
    CHECK(golden != NULL);
    if (!golden) return test_done("test_index cache goldens");
    cJSON_ArrayForEach(row, cJSON_GetObjectItemCaseSensitive(golden, "cases")) {
        cJSON *input = cJSON_GetObjectItemCaseSensitive(row, "input");
        cJSON *owned = NULL;
        const char *bits = otc__jstr(row, "binary64_hex");
        const char *expected = otc__jstr(row, "expected");
        char *bytes;
        if (bits) {
            uint64_t word = (uint64_t)strtoull(bits, NULL, 16);
            double number;
            memcpy(&number, &word, sizeof number);
            owned = input = cJSON_CreateNumber(number);
        }
        bytes = encode_cache_document(input);
        printf("CASE %s expected=%s actual=%s\n", otc__jstr(row, "id"), expected,
               bytes ? bytes : "<refused>");
        CHECK(bytes && !strcmp(bytes, expected));
        free(bytes);
        cJSON_Delete(owned);
    }
    cJSON_ArrayForEach(row, cJSON_GetObjectItemCaseSensitive(golden, "refusals")) {
        const char *bits = otc__jstr(row, "binary64_hex");
        const char *hex = otc__jstr(row, "raw_json_hex");
        cJSON *input = NULL;
        char *bytes = NULL;
        if (bits) {
            uint64_t word = (uint64_t)strtoull(bits, NULL, 16);
            double number;
            memcpy(&number, &word, sizeof number);
            input = cJSON_CreateNumber(number);
        } else if (hex) {
            size_t i, n = strlen(hex) / 2;
            char raw[64];
            CHECK(n < sizeof raw);
            for (i = 0; i < n; i++) {
                char pair[3] = {hex[i * 2], hex[i * 2 + 1], 0};
                raw[i] = (char)strtoul(pair, NULL, 16);
            }
            raw[n] = 0;
            input = otc__json_parse(raw, n);
        }
        if (input) bytes = encode_cache_document(input);
        printf("REFUSAL %s actual=%s\n", otc__jstr(row, "id"), bytes ? bytes : "<refused>");
        CHECK(bytes == NULL);
        free(bytes);
        cJSON_Delete(input);
    }
    cJSON_Delete(golden);
    return test_done("test_index cache goldens");
}

static void die(const char *what)
{
    fprintf(stderr, "test_index: %s\n", what);
    exit(2);
}

static void sha256_or_die(const char *path, char hex[65])
{
    hex[0] = '\0';
    if (otc__sha256_file(path, hex) != OTC_OK || strlen(hex) != 64) die("otc__sha256_file failed");
}

static void write_index(cJSON *(*tamper)(cJSON *doc))
{
    otc_release *rel = NULL;
    char hex[65], *txt, *ixp;
    cJSON *doc;
    FILE *f;
    if (otc_open_file(g_jsonl, NULL, &rel) != OTC_OK) die("open failed");
    sha256_or_die(g_jsonl, hex);
    doc = otc__index_doc(rel, hex, "test");
    otc_close(rel);
    if (!doc) die("otc__index_doc gave NULL");
    if (tamper) doc = tamper(doc);
    txt = encode_cache_document(doc);
    if (!txt) die("encode_cache_document gave NULL");
    ixp = test_join(g_dir, "index-v1.json");
    f = fopen(ixp, "wb");
    if (!f) die("cannot create index-v1.json");
    if (fputs(txt, f) < 0) die("cannot write index-v1.json");
    if (fclose(f) != 0) die("cannot close index-v1.json");
    free(ixp);
    free(txt);
    cJSON_Delete(doc);
}

static cJSON *entry(cJSON *doc, int i)
{
    cJSON *e = cJSON_GetArrayItem(cJSON_GetObjectItem(doc, "stations"), i);
    if (!e) die("the index document has no such station entry");
    return e;
}

/* An entry's number KEY; the index document must have it. */
static double number(cJSON *e, const char *key)
{
    cJSON *v = cJSON_GetObjectItem(e, key);
    if (!cJSON_IsNumber(v)) die("an index entry has no such number");
    return v->valuedouble;
}

/* Replaces e's KEY, which must be there. */
static void replace(cJSON *e, const char *key, cJSON *v)
{
    if (!v || !cJSON_ReplaceItemInObject(e, key, v)) die("cannot replace an index entry's value");
}

static cJSON *swap_ids(cJSON *doc)
{
    replace(entry(doc, 0), "station_id", cJSON_CreateString("OTC-X-2"));
    replace(entry(doc, 1), "station_id", cJSON_CreateString("OTC-X-1"));
    return doc;
}

static cJSON *zero_length(cJSON *doc)
{
    replace(entry(doc, 0), "length", cJSON_CreateNumber(0));
    return doc;
}

static cJSON *same_offsets(cJSON *doc)
{
    replace(entry(doc, 1), "offset", cJSON_CreateNumber(0));
    replace(entry(doc, 1), "length", cJSON_CreateNumber(number(entry(doc, 0), "length")));
    return doc;
}

static cJSON *no_optional_marker(cJSON *doc)
{
    cJSON_DeleteItemFromObjectCaseSensitive(doc, "discovery_index_version");
    return doc;
}

static cJSON *invalid_optional_marker(cJSON *doc)
{
    replace(doc, "discovery_index_version", cJSON_CreateNull());
    return doc;
}

static cJSON *base_projection(cJSON *doc)
{
    cJSON *e, *s;
    no_optional_marker(doc);
    cJSON_ArrayForEach(e, cJSON_GetObjectItemCaseSensitive(doc, "stations")) {
        cJSON_DeleteItemFromObjectCaseSensitive(e, "subordinate_offsets");
        cJSON_DeleteItemFromObjectCaseSensitive(e, "current_offsets");
        cJSON_ArrayForEach(s, cJSON_GetObjectItemCaseSensitive(e, "sets")) {
            cJSON_DeleteItemFromObjectCaseSensitive(s, "fallback");
            cJSON_DeleteItemFromObjectCaseSensitive(s, "current_bins");
        }
    }
    return doc;
}

static void check_station(const char *id, const char *want_name, int want_index)
{
    otc_release *rel = NULL;
    otc_station_t *st = NULL;
    char name[64] = "";
    size_t need;
    CHECK_STATUS(otc_open_file(g_jsonl, NULL, &rel), OTC_OK);
    if (!rel) return;
    CHECK(rel->index_used == want_index);
    CHECK_STATUS(otc_station(rel, id, &st), OTC_OK);
    if (st) {
        CHECK_STATUS(otc_station_name(st, name, sizeof name, &need), OTC_OK);
        CHECK(!strcmp(name, want_name));
    }
    otc_station_free(st);
    otc_close(rel);
}

int main(void)
{
    char sums[512], hex_l[65], hex_m[65], *ixp, *mp;
    otc_release *rel = NULL;
    otc_station_t *st = NULL;
    const char *native = getenv("OTC_INDEX_NATIVE_JSONL");
    const char *golden = getenv("OTC_CACHE_GOLDEN");
    if (golden) return cache_goldens(golden);
    cache_regression();
    if (native) {
        cJSON *document;
        char hex[65], *text;
        CHECK_STATUS(otc_open_file(native, NULL, &rel), OTC_OK);
        if (!rel) return test_done("test_index native writer");
        sha256_or_die(native, hex);
        document = otc__index_doc(rel, hex, "native C regression");
        if (!document) die("actual native index writer failed");
        text = encode_cache_document(document);
        if (!text) die("actual native index serialization failed");
        puts(text);
        free(text);
        cJSON_Delete(document);
        otc_close(rel);
        return test_done("test_index native writer");
    }
    g_dir = test_tmpdir();
    test_write(g_dir, "OTC_20990101.meta.json", TEST_META("20990101"));
    test_write(g_dir, "OTC_20990101.jsonl", TEST_STATION("OTC-X-1", "First") "\n" TEST_STATION("OTC-X-2", "Second") "\n");
    g_jsonl = test_join(g_dir, "OTC_20990101.jsonl");
    mp = test_join(g_dir, "OTC_20990101.meta.json");
    sha256_or_die(g_jsonl, hex_l);
    sha256_or_die(mp, hex_m);
    snprintf(sums, sizeof sums, "%s  OTC_20990101.jsonl\n%s  OTC_20990101.meta.json\n", hex_l, hex_m);
    test_write(g_dir, "OTC_20990101.sha256", sums);
    ixp = test_join(g_dir, "index-v1.json");

    /* a fresh index is used */
    write_index(NULL);
    check_station("OTC-X-1", "First", 1);
    write_index(no_optional_marker);
    check_station("OTC-X-1", "First", 1);
    write_index(invalid_optional_marker);
    check_station("OTC-X-1", "First", 0);
    write_index(base_projection);
    check_station("OTC-X-1", "First", 1);

    /* swapped ids: invalid_release, never the other station, and the index goes */
    write_index(swap_ids);
    CHECK_STATUS(otc_open_file(g_jsonl, NULL, &rel), OTC_OK);
    if (rel) {
        char msg[512] = "";
        size_t need;
        CHECK(rel->index_used == 1);
        CHECK_STATUS(otc_station(rel, "OTC-X-1", &st), OTC_E_INVALID_RELEASE);
        otc_station_free(st);
        st = NULL;
        CHECK_STATUS(otc_last_error(rel, msg, sizeof msg, &need), OTC_OK);
        CHECK(strstr(msg, "index-v1.json") != NULL);
        otc_close(rel);
    }
    CHECK(access(ixp, F_OK) != 0);
    check_station("OTC-X-1", "First", 0);

    /* out of bounds: rebuilt, right answers */
    write_index(zero_length);
    check_station("OTC-X-1", "First", 0);
    check_station("OTC-X-1", "First", 0);   /* and the next open does not trust it either */
    write_index(same_offsets);
    check_station("OTC-X-2", "Second", 0);
    check_station("OTC-X-2", "Second", 0);

    free(ixp);
    free(mp);
    free(g_jsonl);
    free(g_dir);
    return test_done("test_index");
}
