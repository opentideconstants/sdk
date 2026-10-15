/* PK02 / C104: a corrupt cached pointer does not stick. When the server
 * answers 304 to the stored ETag but the cached body is not JSON, the
 * library fetches the pointer again without If-None-Match (a 200), and
 * stores the good body: the next call revalidates it with a plain 304, and
 * no longer finds a body that is not JSON. */
#include "otc_test.h"
#include "otc_internal.h"

static int g_not_json, g_304, g_200;

static void log_fn(void *u, int level, const char *msg)
{
    (void)u;
    if (level == 2 && strstr(msg, "OTC_latest-f1.json is not JSON of the right shape; fetching it again")) g_not_json++;
    if (strstr(msg, "pointer OTC_latest-f1.json: 304")) g_304++;
    if (strstr(msg, "pointer OTC_latest-f1.json: 200")) g_200++;
}

/* One otc_fetch_latest_info call; the counts are those of this call. */
static void call(otc_fetch_options *fo, otc_error *err, const char *what)
{
    otc_release_info *info = NULL;
    g_not_json = g_304 = g_200 = 0;
    CHECK_STATUS(otc_fetch_latest_info(fo, &info), OTC_OK);
    CHECK(info != NULL && err->status == OTC_OK);
    if (err->status != OTC_OK) fprintf(stderr, "%s: error: %s\n", what, err->message);
    otc_release_info_free(info);
}

/* 1 when the cached pointer body is a JSON object */
static int cached_is_json(const char *pdir)
{
    char *p = test_join(pdir, "OTC_latest-f1.json"), *text = NULL;
    size_t len = 0;
    cJSON *doc = NULL;
    int ok;
    if (otc__read_all(p, &text, &len) == OTC_OK) doc = cJSON_Parse(text);
    ok = cJSON_IsObject(doc);
    cJSON_Delete(doc);
    free(text);
    free(p);
    return ok;
}

int main(void)
{
    char *cache = test_tmpdir(), base[512], *pdir;
    otc_fetch_options fo;
    otc_error err;
    if (!test_server()) return test_skip("test_fetch_pointer_corrupt", "no OTC_TEST_SERVER");
    otc_fetch_options_init(&fo);
    otc_error_init(&err);
    snprintf(base, sizeof base, "%s/good/", test_server());
    fo.cache_dir = cache;
    fo.base_url = base;
    fo.error = &err;
    fo.log_fn = log_fn;
    pdir = test_join(cache, "v1/pointer");
    call(&fo, &err, "first call");
    CHECK(g_200 == 1 && cached_is_json(pdir));
    /* the premise: with the cache as it is, the server answers 304 to the stored ETag */
    call(&fo, &err, "second call");
    CHECK(g_304 == 1 && g_200 == 0);
    /* the cached body goes bad; the .etag stays, so a revalidation would get 304 */
    test_write(pdir, "OTC_latest-f1.json", "<html>half-written</html>");
    call(&fo, &err, "call with the corrupt cache");
    CHECK(g_not_json == 1 && g_200 == 1 && g_304 == 0);   /* seen, and fetched again in full */
    CHECK(cached_is_json(pdir));                           /* and the good body is stored */
    /* and it healed: the next call is a plain 304 again */
    call(&fo, &err, "call after the heal");
    CHECK(g_not_json == 0 && g_304 == 1 && g_200 == 0);
    if (g_not_json || g_304 != 1) fprintf(stderr, "after the heal: %d not-JSON warnings, %d 304s, %d 200s\n", g_not_json, g_304, g_200);
    free(pdir);
    free(cache);
    return test_done("test_fetch_pointer_corrupt");
}
