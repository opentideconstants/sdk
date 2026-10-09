/* CR2 R2-114, DR21 (spec 5.7): the user and password of a URL never appear in
 * an error message or a log line; they are replaced by "***". Covered: a proxy
 * that is not an http(s) URL (with and without a scheme), a base_url whose
 * request fails (the error and the retry log lines), the cache fallback after
 * that failure (its log line), and a message cut short inside a long userinfo.
 * Every message and log line is printed, so the run shows what a caller sees. */
#include "otc_test.h"

#define SECRET "Pk12S3cretPW"
#define USER "otcpk12user"

static char g_log[16384];

static void collect(void *user, int level, const char *msg)
{
    size_t n = strlen(g_log);
    (void)user;
    printf("log[%d] %s\n", level, msg);
    snprintf(g_log + n, sizeof g_log - n, "%s\n", msg);
}

static void check_clean(const char *what, const char *text)
{
    printf("%s: %s\n", what, text);
    CHECK(strstr(text, SECRET) == NULL);
    CHECK(strstr(text, USER) == NULL);
}

int main(void)
{
    const char *srv = test_server();
    char *cache = test_tmpdir(), path[4096], good[1024], bad[2048];
    otc_fetch_options fo;
    otc_error err;
    size_t need, i;
    if (!srv) {
        printf("test_fetch_credentials: no OTC_TEST_SERVER, skipped\n");
        return 0;
    }
    otc_fetch_options_init(&fo);
    otc_error_init(&err);
    fo.cache_dir = cache;
    fo.error = &err;
    fo.log_fn = collect;

    /* a proxy that is not an http(s) URL */
    fo.proxy = "socks5://" USER ":" SECRET "@proxy.invalid:1080";
    CHECK_STATUS(otc_fetch_latest(&fo, path, sizeof path, &need), OTC_E_INVALID_ARGUMENT);
    check_clean("proxy socks5", err.message);
    CHECK(strstr(err.message, "socks5://***@proxy.invalid:1080") != NULL);
    fo.proxy = USER ":" SECRET "@proxy.invalid:1080";
    CHECK_STATUS(otc_fetch_latest(&fo, path, sizeof path, &need), OTC_E_INVALID_ARGUMENT);
    check_clean("proxy without a scheme", err.message);
    CHECK(strstr(err.message, "***@proxy.invalid:1080") != NULL);
    fo.proxy = NULL;

    /* a base_url whose connection is refused: the error and the retry log lines */
    fo.base_url = "http://" USER ":" SECRET "@127.0.0.1:1/good/";
    fo.on_network_error = OTC_ON_NETWORK_ERROR_RAISE;
    CHECK_STATUS(otc_fetch_latest(&fo, path, sizeof path, &need), OTC_E_NETWORK);
    check_clean("base_url refused", err.message);
    CHECK(strstr(err.message, "http://***@127.0.0.1:1/") != NULL);
    CHECK(strstr(g_log, "retry") != NULL);
    check_clean("log so far", g_log);

    /* the cache fallback after the same failure */
    snprintf(good, sizeof good, "%s/good/", srv);
    fo.base_url = good;
    fo.on_network_error = OTC_ON_NETWORK_ERROR_USE_CACHE;
    CHECK_STATUS(otc_fetch_latest(&fo, path, sizeof path, &need), OTC_OK);
    g_log[0] = '\0';
    fo.base_url = "http://" USER ":" SECRET "@127.0.0.1:1/good/";
    CHECK_STATUS(otc_fetch_latest(&fo, path, sizeof path, &need), OTC_OK);
    CHECK(strstr(g_log, "127.0.0.1:1") != NULL);
    check_clean("log of the fallback", g_log);

    /* a message cut short inside the userinfo: the cut userinfo is not shown */
    strcpy(bad, "ftp://");
    for (i = strlen(bad); i < 1200; i++) bad[i] = 'u';
    strcpy(bad + i, ":" SECRET "@h.invalid/");
    fo.base_url = bad;
    CHECK_STATUS(otc_fetch_latest(&fo, path, sizeof path, &need), OTC_E_INVALID_ARGUMENT);
    check_clean("long userinfo", err.message);
    CHECK(strstr(err.message, "uuuu") == NULL);
    /* the same in the message of a failed request (built before the error is set) and its log lines */
    strcpy(bad, "http://");
    for (i = strlen(bad); i < 1200; i++) bad[i] = 'u';
    strcpy(bad + i, ":" SECRET "@127.0.0.1:1/good/");
    fo.on_network_error = OTC_ON_NETWORK_ERROR_RAISE;
    g_log[0] = '\0';
    CHECK_STATUS(otc_fetch_latest(&fo, path, sizeof path, &need), OTC_E_NETWORK);
    check_clean("long userinfo, refused", err.message);
    CHECK(strstr(err.message, "uuuu") == NULL);
    CHECK(strstr(g_log, "GET http://***") != NULL && strstr(g_log, "uuuu") == NULL);   /* the line is cut in the URL */

    free(cache);
    return test_done("test_fetch_credentials");
}
