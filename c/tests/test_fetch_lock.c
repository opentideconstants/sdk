/* PK04 / C19 and the lock protocol of spec 5.4 (CR D3). Built against a copy
 * of the library with short lock timers (stale after 0.6 s, polls of 50 ms).
 *  1. A stale lock that cannot be removed: OTC_E_CACHE after 3 failed
 *     removals, not an endless wait.
 *  2. A lock taken over by another process while this one downloads: this
 *     one's release leaves the other's lock alone (owner.json token). */
#include "otc_test.h"

#include <pthread.h>
#include <signal.h>

static otc_fetch_options g_fo;
static otc_status g_st;

static void on_alarm(int sig)
{
    (void)sig;
    fprintf(stderr, "test_fetch_lock: timed out (the lock loop never ends)\n");
    _exit(1);
}

static void *fetch_thread(void *arg)
{
    char path[4096];
    size_t need;
    (void)arg;
    g_st = otc_fetch_release(&g_fo, "20991231.2", path, sizeof path, &need);
    return NULL;
}

static char *mkdirs(const char *cache, const char *ds)
{
    char p[4096];
    snprintf(p, sizeof p, "%s/v1", cache);
    mkdir(p, 0777);
    snprintf(p, sizeof p, "%s/v1/releases", cache);
    mkdir(p, 0777);
    snprintf(p, sizeof p, "%s/v1/releases/%s", cache, ds);
    mkdir(p, 0777);
    return test_join(p, ".lock");
}

int main(void)
{
    char *cache = test_tmpdir(), *cache2 = test_tmpdir(), base[512], path[4096], *lock, *owner, buf[256];
    otc_error err;
    size_t need;
    pthread_t t;
    FILE *f;
    if (!test_server()) { printf("test_fetch_lock: skipped (no OTC_TEST_SERVER)\n"); return 0; }
    signal(SIGALRM, on_alarm);
    alarm(30);
    snprintf(base, sizeof base, "%s/good/", test_server());

    /* 1. an unremovable stale lock */
    otc_fetch_options_init(&g_fo);
    otc_error_init(&err);
    g_fo.cache_dir = cache;
    g_fo.base_url = base;
    g_fo.error = &err;
    lock = mkdirs(cache, "20991231.2");
    mkdir(lock, 0777);
    test_write(lock, "owner.json", "{\"pid\":1,\"token\":\"someone-else\"}");
    chmod(lock, 0555);
    CHECK_STATUS(otc_fetch_release(&g_fo, "20991231.2", path, sizeof path, &need), OTC_E_CACHE);
    CHECK(strstr(err.message, "stale lock") != NULL);
    chmod(lock, 0755);
    free(lock);

    /* 2. a lock taken over while the download runs */
    otc_fetch_options_init(&g_fo);
    otc_error_init(&err);
    g_fo.cache_dir = cache2;
    g_fo.base_url = base;
    g_fo.error = &err;
    lock = mkdirs(cache2, "20991231.2");
    owner = test_join(lock, "owner.json");
    pthread_create(&t, NULL, fetch_thread, NULL);
    usleep(1000 * 1000);   /* the .jsonl is slow (2 s): the lock is held now */
    CHECK(access(owner, F_OK) == 0);
    unlink(owner);
    rmdir(lock);
    mkdir(lock, 0777);
    test_write(lock, "owner.json", "{\"pid\":1,\"token\":\"the-other-process\"}");
    pthread_join(t, NULL);
    CHECK_STATUS(g_st, OTC_OK);
    f = fopen(owner, "rb");
    CHECK(f != NULL);
    if (f) {
        size_t n = fread(buf, 1, sizeof buf - 1, f);
        buf[n] = '\0';
        fclose(f);
        CHECK(strstr(buf, "the-other-process") != NULL);
    } else {
        fprintf(stderr, "the first holder's release removed the other process's lock\n");
    }
    free(owner);
    free(lock);
    free(cache);
    free(cache2);
    return test_done("test_fetch_lock");
}
