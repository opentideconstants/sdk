/* PK12 / C93: otc_fetch follows redirects only to http and https (spec 5.7,
 * CR D1). A tiny HTTP server in this process answers every request with a
 * 302 to ftp://127.0.0.1:<port>/, where a second socket counts connections.
 * Before the fix libcurl followed the redirect and connected there.
 * PK10 / C50: that failure is permanent (a protocol the library refuses), so
 * it is not retried: the server sees one request, not three. */
#include "otc_test.h"

#include <arpa/inet.h>
#include <netinet/in.h>
#include <pthread.h>
#include <sys/socket.h>

static int g_http, g_trap, g_trap_port, g_trap_hits, g_requests;

static int listen_any(int *port)
{
    struct sockaddr_in a;
    socklen_t n = sizeof a;
    int s = socket(AF_INET, SOCK_STREAM, 0), one = 1;
    memset(&a, 0, sizeof a);
    a.sin_family = AF_INET;
    a.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    setsockopt(s, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
    if (s < 0 || bind(s, (struct sockaddr *)&a, sizeof a) != 0 || listen(s, 8) != 0
        || getsockname(s, (struct sockaddr *)&a, &n) != 0) {
        perror("listen");
        exit(2);
    }
    *port = ntohs(a.sin_port);
    return s;
}

static void *http_thread(void *arg)
{
    (void)arg;
    for (;;) {
        char buf[4096], resp[512];
        int c = accept(g_http, NULL, NULL);
        if (c < 0) return NULL;
        if (recv(c, buf, sizeof buf, 0) > 0) {
            __sync_fetch_and_add(&g_requests, 1);
            snprintf(resp, sizeof resp,
                     "HTTP/1.1 302 Found\r\nLocation: ftp://127.0.0.1:%d/OTC_20991231.sha256\r\n"
                     "Content-Length: 0\r\nConnection: close\r\n\r\n", g_trap_port);
            send(c, resp, strlen(resp), 0);
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
        __sync_fetch_and_add(&g_trap_hits, 1);
        close(c);
    }
}

int main(void)
{
    char *cache = test_tmpdir(), base[128], path[4096];
    int http_port;
    pthread_t t1, t2;
    otc_fetch_options fo;
    otc_error err;
    size_t need;
    g_http = listen_any(&http_port);
    g_trap = listen_any(&g_trap_port);
    pthread_create(&t1, NULL, http_thread, NULL);
    pthread_create(&t2, NULL, trap_thread, NULL);
    snprintf(base, sizeof base, "http://127.0.0.1:%d/", http_port);
    otc_fetch_options_init(&fo);
    otc_error_init(&err);
    fo.cache_dir = cache;
    fo.base_url = base;
    fo.error = &err;
    fo.on_network_error = OTC_ON_NETWORK_ERROR_RAISE;
    CHECK_STATUS(otc_fetch_release(&fo, "20991231", path, sizeof path, &need), OTC_E_NETWORK);
    printf("error: %s\n", err.message);
    CHECK(g_trap_hits == 0);
    CHECK(g_requests == 1);
    if (g_requests != 1) fprintf(stderr, "a permanent failure was retried: %d requests\n", g_requests);
    if (g_trap_hits) fprintf(stderr, "libcurl followed the redirect to ftp:// (%d connections)\n", g_trap_hits);
    /* stop the two server threads (shutdown wakes accept), so nothing is left running */
    shutdown(g_http, SHUT_RDWR);
    shutdown(g_trap, SHUT_RDWR);
    close(g_http);
    close(g_trap);
    pthread_join(t1, NULL);
    pthread_join(t2, NULL);
    free(cache);
    return test_done("test_fetch_redirect");
}
