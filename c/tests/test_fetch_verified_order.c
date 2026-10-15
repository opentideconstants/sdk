/* PK04 / C103: while a download replaces data files of a cached release, the
 * old .verified must not vouch for them. If the download stops after some
 * renames, the release directory is not trusted until a new .verified is
 * written (spec 5.4: .verified is written last; a reader trusts a directory
 * only when .verified exists). The test checks its premise (the .jsonl was
 * replaced before the .json failed) and that the release recovers once the
 * obstacle is gone. */
#include "otc_test.h"
#include "otc_internal.h"

#define JSONL_SHA "84ba5c138d233be93c031bdec7b243caa72d27bbf6a7b3d0df14aa61fe36fab0"   /* good/OTC_20991231.2.jsonl */

static cJSON *receipt_contract(const char *dir, const char *label, int nfiles, const char *doi)
{
    char *p = test_join(dir, ".verified"), *text = NULL, *canonical = NULL;
    size_t len = 0;
    cJSON *doc, *row;
    CHECK_STATUS(otc__read_all(p, &text, &len), OTC_OK);
    free(p);
    doc = text ? otc__json_parse(text, len) : NULL;
    CHECK(doc != NULL);
    if (!doc) { free(text); return NULL; }
    printf("receipt %s: %s\n", label, text);
    CHECK(cJSON_GetArraySize(doc) == 7);
    CHECK(otc__jstr(doc, "format_version") != NULL);
    CHECK(otc__jstr(doc, "min_reader_version") != NULL);
    CHECK(doi ? otc__jstr(doc, "zenodo_version_doi") && !strcmp(doi, otc__jstr(doc, "zenodo_version_doi"))
              : cJSON_IsNull(cJSON_GetObjectItemCaseSensitive(doc, "zenodo_version_doi")));
    CHECK(cJSON_GetArraySize(otc__jget(doc, "files")) == nfiles);
    cJSON_ArrayForEach(row, otc__jget(doc, "files")) {
        char *file = test_join(dir, row->string), hex[65];
        CHECK(cJSON_GetArraySize(row) == 3);
        CHECK(cJSON_IsString(otc__jget(row, "sha256")));
        CHECK(cJSON_IsString(cJSON_GetObjectItemCaseSensitive(row, "url"))
              || cJSON_IsNull(cJSON_GetObjectItemCaseSensitive(row, "url")));
        CHECK(otc__path_size(file) == otc__jint(row, "size"));
        CHECK_STATUS(otc__sha256_file(file, hex), OTC_OK);
        CHECK(otc__jstr(row, "sha256") && !strcmp(hex, otc__jstr(row, "sha256")));
        free(file);
    }
    CHECK_STATUS(otc__encode_cache_json(doc, &canonical), OTC_OK);
    CHECK(canonical && !strcmp(text, canonical));
    free(canonical);
    free(text);
    return doc;
}

static void two_mode_receipts(const otc_fetch_options *options)
{
    char *cache = test_tmpdir(), *dir = test_join(cache, "v1/releases/20991231.2");
    char path[4096], *meta, *text = NULL, doi[128];
    size_t need;
    otc_fetch_options fo = *options;
    otc_release *rel = NULL;
    cJSON *doc, *row;
    fo.cache_dir = cache;
    CHECK_STATUS(otc_fetch_open(&fo, "latest", NULL, &rel), OTC_OK);
    if (!rel) { free(dir); free(cache); return; }
    CHECK_STATUS(otc_release_zenodo_version_doi(rel, doi, sizeof doi, &need), OTC_OK);
    CHECK(!strcmp(doi, "10.5072/zenodo.2"));
    otc_close(rel);
    doc = receipt_contract(dir, "stream", 2, doi);
    cJSON_Delete(doc);
    fo.formats = OTC_FORMAT_JSON | OTC_FORMAT_JSONL;
    CHECK_STATUS(otc_fetch_open(&fo, "20991231.2", NULL, &rel), OTC_OK);
    if (rel) {
        CHECK_STATUS(otc_release_zenodo_version_doi(rel, doi, sizeof doi, &need), OTC_OK);
        CHECK(!strcmp(doi, "10.5072/zenodo.2"));
        otc_close(rel);
    }
    doc = receipt_contract(dir, "stream-to-eager", 3, "10.5072/zenodo.2");
    if (doc) {
        row = cJSON_GetObjectItemCaseSensitive(otc__jget(doc, "files"), "OTC_20991231.2.json");
        CHECK(row != NULL);
        if (row) {
            CHECK(cJSON_AddStringToObject(row, "private", "must not survive") != NULL);
            cJSON_DeleteItemFromObjectCaseSensitive(row, "url");
        }
        CHECK_STATUS(otc__encode_cache_json(doc, &text), OTC_OK);
        if (text) test_write(dir, ".verified", text);
        free(text);
        cJSON_Delete(doc);
    }
    /* A stream acquisition replaces the missing META and retains verified JSON.
     * Its legacy row must become exactly sha256/size/url with unknown URL null. */
    meta = test_join(dir, "OTC_20991231.2.meta.json");
    CHECK(unlink(meta) == 0);
    free(meta);
    fo.formats = OTC_FORMAT_JSONL;
    CHECK_STATUS(otc_fetch_release(&fo, "20991231.2", path, sizeof path, &need), OTC_OK);
    doc = receipt_contract(dir, "eager-to-stream", 3, "10.5072/zenodo.2");
    row = cJSON_GetObjectItemCaseSensitive(otc__jget(doc, "files"), "OTC_20991231.2.json");
    CHECK(cJSON_IsNull(cJSON_GetObjectItemCaseSensitive(row, "url")));
    cJSON_Delete(doc);
    fo.offline = 1;
    CHECK_STATUS(otc_fetch_open(&fo, "20991231.2", NULL, &rel), OTC_OK);
    if (rel) otc_close(rel);
    printf("two-mode cache: %s\n", cache);
    free(dir);
    free(cache);
}

static void index_contract(otc_fetch_options *fo, const char *dir, const char *jsonl)
{
    otc_release *rel = NULL;
    char *ix = test_join(dir, "index-v1.json"), *text = NULL, *canonical = NULL;
    size_t len = 0;
    cJSON *doc, *entry, *set;
    const char *id;
    otc_station_t *station = NULL;
    CHECK_STATUS(otc_fetch_open(fo, "20991231.2", NULL, &rel), OTC_OK);
    if (!rel) { free(ix); return; }
    otc_close(rel);
    CHECK_STATUS(otc__read_all(ix, &text, &len), OTC_OK);
    doc = text ? otc__json_parse(text, len) : NULL;
    CHECK(doc != NULL);
    if (!doc) { free(text); free(ix); return; }
    CHECK_STATUS(otc__encode_cache_json(doc, &canonical), OTC_OK);
    CHECK(canonical && !strcmp(text, canonical));
    free(canonical);
    free(text);
    cJSON_ArrayForEach(entry, otc__jget(doc, "stations")) {
        CHECK(cJSON_GetObjectItemCaseSensitive(entry, "subordinate_offsets") != NULL);
        CHECK(cJSON_IsArray(cJSON_GetObjectItemCaseSensitive(entry, "current_offsets")));
        cJSON_ArrayForEach(set, otc__jget(entry, "sets")) {
            CHECK(cJSON_GetObjectItemCaseSensitive(set, "fallback") != NULL);
            CHECK(cJSON_IsArray(cJSON_GetObjectItemCaseSensitive(set, "current_bins")));
        }
    }
    entry = cJSON_GetArrayItem(otc__jget(doc, "stations"), 0);
    id = otc__jstr(entry, "station_id");
    CHECK(id != NULL);
    if (id) {
        CHECK(cJSON_ReplaceItemInObject(entry, "name", cJSON_CreateString("tampered name")));
        CHECK_STATUS(otc__encode_cache_json(doc, &canonical), OTC_OK);
        if (canonical) test_write(dir, "index-v1.json", canonical);
        free(canonical);
        CHECK_STATUS(otc_open_file(jsonl, NULL, &rel), OTC_OK);
        if (rel) {
            CHECK(rel->index_used);
            CHECK_STATUS(otc_station(rel, id, &station), OTC_E_INVALID_RELEASE);
            CHECK(station == NULL);
            CHECK(access(ix, F_OK) != 0);
            otc_station_free(station);
            otc_close(rel);
        }
    }
    cJSON_Delete(doc);
    free(ix);
}

int main(void)
{
    char *cache = test_tmpdir(), base[512], path[4096], *dir, *vpath, *jsonl, *text = NULL, *out, hex[65] = "";
    otc_fetch_options fo;
    otc_error err;
    size_t need, len = 0;
    cJSON *v, *rec;
    if (!test_server()) return test_skip("test_fetch_verified_order", "no OTC_TEST_SERVER");
    otc_fetch_options_init(&fo);
    otc_error_init(&err);
    snprintf(base, sizeof base, "%s/good/", test_server());
    fo.cache_dir = cache;
    fo.base_url = base;
    fo.error = &err;
    two_mode_receipts(&fo);
    CHECK_STATUS(otc_fetch_release(&fo, "20991231.2", path, sizeof path, &need), OTC_OK);
    dir = test_join(cache, "v1/releases/20991231.2");
    vpath = test_join(dir, ".verified");
    jsonl = test_join(dir, "OTC_20991231.2.jsonl");
    index_contract(&fo, dir, jsonl);
    /* .verified records an older .jsonl, which is the one on disk (so the download replaces it) ... */
    if (otc__read_all(vpath, &text, &len) != OTC_OK) { perror(vpath); return 2; }
    v = cJSON_Parse(text);
    free(text);
    rec = cJSON_GetObjectItem(cJSON_GetObjectItem(v, "files"), "OTC_20991231.2.jsonl");
    if (!rec || !cJSON_IsString(cJSON_GetObjectItem(rec, "sha256"))
        || strcmp(cJSON_GetObjectItem(rec, "sha256")->valuestring, JSONL_SHA) != 0) {
        fprintf(stderr, "test_fetch_verified_order: .verified has no record of the .jsonl's SHA-256\n");
        return 2;
    }
    if (!cJSON_ReplaceItemInObject(rec, "sha256",
                                   cJSON_CreateString("0000000000000000000000000000000000000000000000000000000000000000"))
        || !(out = cJSON_Print(v))) {
        fprintf(stderr, "test_fetch_verified_order: cannot edit .verified\n");
        return 2;
    }
    cJSON_Delete(v);
    test_write(dir, ".verified", out);
    cJSON_free(out);
    test_write(dir, "OTC_20991231.2.jsonl", "{\"an\":\"older release\"}\n");
    /* ... and the .json cannot be put in place (a directory is in the way) */
    snprintf(path, sizeof path, "%s/OTC_20991231.2.json", dir);
    if (mkdir(path, 0777) != 0) { perror(path); return 2; }
    fo.formats = OTC_FORMAT_JSON;
    err.file[0] = '\0';
    CHECK_STATUS(otc_fetch_release(&fo, "20991231.2", path, sizeof path, &need), OTC_E_CACHE);
    CHECK(strstr(err.file, "OTC_20991231.2.json") != NULL && strstr(err.file, ".jsonl") == NULL);
    if (!strstr(err.file, "OTC_20991231.2.json")) fprintf(stderr, "error: %s (%s)\n", err.message, err.file);
    /* the premise: the .jsonl was renamed into place before the failure */
    CHECK(otc__sha256_file(jsonl, hex) == OTC_OK && !strcmp(hex, JSONL_SHA));
    if (strcmp(hex, JSONL_SHA) != 0) fprintf(stderr, "the .jsonl was not replaced before the failure: the test proves nothing\n");
    CHECK(access(vpath, F_OK) != 0);
    if (access(vpath, F_OK) == 0) fprintf(stderr, "the old .verified still vouches for a replaced .jsonl\n");
    /* recovery: with the obstacle gone, the release downloads and is trusted again */
    snprintf(path, sizeof path, "%s/OTC_20991231.2.json", dir);
    if (rmdir(path) != 0) { perror(path); return 2; }
    CHECK_STATUS(otc_fetch_release(&fo, "20991231.2", path, sizeof path, &need), OTC_OK);
    CHECK(access(vpath, F_OK) == 0);
    free(jsonl);
    free(vpath);
    free(dir);
    free(cache);
    return test_done("test_fetch_verified_order");
}
