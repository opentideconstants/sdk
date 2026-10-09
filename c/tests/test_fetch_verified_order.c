/* PK04 / C103: while a download replaces data files of a cached release, the
 * old .verified must not vouch for them. If the download stops after some
 * renames, the release directory is not trusted until a new .verified is
 * written (spec 5.4: .verified is written last; a reader trusts a directory
 * only when .verified exists). The test checks its premise (the .jsonl was
 * replaced before the .json failed) and that the release recovers once the
 * obstacle is gone. */
#include "otc_test.h"
#include "otc_internal.h"

#define JSONL_SHA "759d6bb9e54684e82c3a007d8970e2ac5e3df19a3c2093f74c3fbc1bd69499b1"   /* good/OTC_20991231.2.jsonl */

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
    CHECK_STATUS(otc_fetch_release(&fo, "20991231.2", path, sizeof path, &need), OTC_OK);
    dir = test_join(cache, "v1/releases/20991231.2");
    vpath = test_join(dir, ".verified");
    jsonl = test_join(dir, "OTC_20991231.2.jsonl");
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
