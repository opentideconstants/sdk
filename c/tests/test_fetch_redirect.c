/* PK12 / C93: otc_fetch follows redirects only to http and https (spec 5.7,
 * CR D1). A tiny HTTP server in this process answers a request for the
 * release with a 302 to ftp://127.0.0.1:<port>/, where a second socket counts
 * connections. Before the fix libcurl followed the redirect and connected
 * there. The refusal is the protocol's: no HTTP status is kept (an unfollowed
 * 302 would leave 302).
 * Its control: a 302 to http (the fixture server's pointer) is followed, so
 * the test cannot pass because no redirect is followed at all.
 * PK10 / C50: the ftp failure is permanent (a protocol the library refuses), so
 * it is not retried: the server sees one request, not three. */
#include "otc_test.h"

#include <arpa/inet.h>
#include <netinet/in.h>
#include <pthread.h>
#include <sys/socket.h>

static int g_http, g_trap, g_http_port, g_trap_port;
static int g_trap_hits, g_requests, g_stop;   /* atomics: the server threads write them */
static char g_fixture[512];                   /* the fixture server's base URL, or "" */

static int listen_any(int *port)
{
    struct sockaddr_in a;
    socklen_t n = sizeof a;
    int s = socket(AF_INET, SOCK_STREAM, 0), one = 1;
    if (s < 0) { perror("socket"); exit(2); }
    memset(&a, 0, sizeof a);
    a.sin_family = AF_INET;
    a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (setsockopt(s, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one) != 0 || bind(s, (struct sockaddr *)&a, sizeof a) != 0
        || listen(s, 8) != 0 || getsockname(s, (struct sockaddr *)&a, &n) != 0) {
        perror("listen");
        exit(2);
    }
    *port = ntohs(a.sin_port);
    return s;
}

/* wakes a thread blocked in accept() on port: a connection it takes, sees g_stop, and ends */
static void wake(int port)
{
    struct sockaddr_in a;
    int s = socket(AF_INET, SOCK_STREAM, 0);
    if (s < 0) return;
    memset(&a, 0, sizeof a);
    a.sin_family = AF_INET;
    a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    a.sin_port = htons((unsigned short)port);
    (void)connect(s, (struct sockaddr *)&a, sizeof a);
    close(s);
}

static void *http_thread(void *arg)
{
    (void)arg;
    for (;;) {
        char buf[4096], resp[1024];
        size_t got = 0;
        ssize_t r;
        int c = accept(g_http, NULL, NULL);
        if (c < 0) return NULL;
        if (__atomic_load_n(&g_stop, __ATOMIC_SEQ_CST)) { close(c); return NULL; }
        /* the whole request head, so that close() does not reset the connection */
        while (got < sizeof buf - 1 && (r = recv(c, buf + got, sizeof buf - 1 - got, 0)) > 0) {
            got += (size_t)r;
            buf[got] = '\0';
            if (strstr(buf, "\r\n\r\n")) break;
        }
        buf[got] = '\0';
        if (got > 0) {
            if (strstr(buf, "OTC_latest-f1.json") && g_fixture[0]) {
                snprintf(resp, sizeof resp,
                         "HTTP/1.1 302 Found\r\nLocation: %sgood/OTC_latest-f1.json\r\n"
                         "Content-Length: 0\r\nConnection: close\r\n\r\n", g_fixture);
            } else {
                __atomic_fetch_add(&g_requests, 1, __ATOMIC_SEQ_CST);
                snprintf(resp, sizeof resp,
                         "HTTP/1.1 302 Found\r\nLocation: ftp://127.0.0.1:%d/OTC_20991231.sha256\r\n"
                         "Content-Length: 0\r\nConnection: close\r\n\r\n", g_trap_port);
            }
            if (send(c, resp, strlen(resp), 0) < 0) perror("send");
        }
        close(c);
    }
}

static void *trap_thread(void *arg)
{
    (void)arg;
    for (;;) {
        int c = accept(g_trap, NULL, NULL);
        if (c < 0) return NULL;
        if (__atomic_load_n(&g_stop, __ATOMIC_SEQ_CST)) { close(c); return NULL; }
        __atomic_fetch_add(&g_trap_hits, 1, __ATOMIC_SEQ_CST);
        close(c);
    }
}

int main(void)
{
    char *cache = test_tmpdir(), *cache2 = test_tmpdir(), base[128], path[4096];
    pthread_t t1, t2;
    otc_fetch_options fo;
    otc_release_info *info = NULL;
    otc_error err;
    size_t need;
    int requests, trap_hits, ran_control = 0;
    if (test_server()) snprintf(g_fixture, sizeof g_fixture, "%s/", test_server());
    g_http = listen_any(&g_http_port);
    g_trap = listen_any(&g_trap_port);
    if (pthread_create(&t1, NULL, http_thread, NULL) != 0 || pthread_create(&t2, NULL, trap_thread, NULL) != 0) {
        fprintf(stderr, "test_fetch_redirect: pthread_create failed\n");
        return 2;
    }
    snprintf(base, sizeof base, "http://127.0.0.1:%d/", g_http_port);
    otc_fetch_options_init(&fo);
    otc_error_init(&err);
    fo.cache_dir = cache;
    fo.base_url = base;
    fo.error = &err;
    CHECK_STATUS(otc_fetch_release(&fo, "20991231", path, sizeof path, &need), OTC_E_NETWORK);
    printf("error: %s (http status %d)\n", err.message, err.http_status);
    CHECK(err.http_status != 302);   /* refused for its protocol, not left as an unfollowed 302 */
    /* the control: a redirect to http is followed (to the fixture server's pointer) */
    if (g_fixture[0]) {
        ran_control = 1;
        otc_error_init(&err);
        fo.cache_dir = cache2;
        CHECK_STATUS(otc_fetch_latest_info(&fo, &info), OTC_OK);
        if (err.status != OTC_OK) fprintf(stderr, "the redirect to http: %s\n", err.message);
        if (info) {
            char ds[32] = "";
            CHECK_STATUS(otc_release_info_datestamp(info, ds, sizeof ds, &need), OTC_OK);
            CHECK(!strcmp(ds, "20991231.2"));
        }
        otc_release_info_free(info);
    }
    /* stop the two server threads, then read what they counted */
    __atomic_store_n(&g_stop, 1, __ATOMIC_SEQ_CST);
    wake(g_http_port);
    wake(g_trap_port);
    pthread_join(t1, NULL);
    pthread_join(t2, NULL);
    close(g_http);
    close(g_trap);
    requests = __atomic_load_n(&g_requests, __ATOMIC_SEQ_CST);
    trap_hits = __atomic_load_n(&g_trap_hits, __ATOMIC_SEQ_CST);
    CHECK(trap_hits == 0);
    CHECK(requests == 1);
    if (requests != 1) fprintf(stderr, "a permanent failure was retried: %d requests\n", requests);
    if (trap_hits) fprintf(stderr, "libcurl followed the redirect to ftp:// (%d connections)\n", trap_hits);
    free(cache);
    free(cache2);
    if (!ran_control && !g_failures) return test_skip("test_fetch_redirect", "no OTC_TEST_SERVER for the http control");
    return test_done("test_fetch_redirect");
}
