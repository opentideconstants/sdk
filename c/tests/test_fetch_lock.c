/* PK04 / C19 and the lock protocol of spec 5.4 (CR D3). Built against a copy
 * of the library with short lock timers (stale after 0.6 s, polls of 50 ms).
 *  1. A stale lock that cannot be removed: OTC_E_CACHE after 3 failed
 *     removals, not an endless wait.
 *  2. A lock taken over by another process while this one downloads: this
 *     one's release leaves the other's lock alone (owner.json token).
 *  3. Two takers on a crashed lock (CR2 DR3, R2-010, R2-015): both wait
 *     past the stale time; the first removes the old lock and takes it, and
 *     the second must not remove that young lock (its age is read, and the
 *     wait restarts after a removal). One stale removal, both succeed.
 * The lock's age stays 120 s in the test build: a lock is old because its
 * started_at is from 2000, so the outcome does not depend on timing. */
#include "otc_test.h"

#include <pthread.h>
#include <signal.h>
#include <time.h>

static otc_fetch_options g_fo;
static otc_status g_st;
static pthread_mutex_t g_mu = PTHREAD_MUTEX_INITIALIZER;
static int g_removals;

struct taker {
    otc_fetch_options fo;
    otc_error err;
    otc_status st;
};

static void count_removals(void *user, int level, const char *msg)
{
    (void)user;
    (void)level;
    if (strstr(msg, "removing the stale lock")) {
        pthread_mutex_lock(&g_mu);
        g_removals++;
        pthread_mutex_unlock(&g_mu);
    }
}

static void *take_thread(void *arg)
{
    struct taker *t = arg;
    char path[4096];
    size_t need;
    t->st = otc_fetch_release(&t->fo, "20991231.2", path, sizeof path, &need);
    return NULL;
}

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

    /* 1. an unremovable stale lock (as root nothing is unremovable: skipped) */
    otc_fetch_options_init(&g_fo);
    otc_error_init(&err);
    g_fo.cache_dir = cache;
    g_fo.base_url = base;
    g_fo.error = &err;
    lock = mkdirs(cache, "20991231.2");
    mkdir(lock, 0777);
    test_write(lock, "owner.json", "{\"pid\":1,\"token\":\"someone-else\",\"started_at\":\"2000-01-01T00:00:00Z\"}");
    chmod(lock, 0555);
    if (!test_is_root()) {
        CHECK_STATUS(otc_fetch_release(&g_fo, "20991231.2", path, sizeof path, &need), OTC_E_CACHE);
        CHECK(strstr(err.message, "stale lock") != NULL);
    } else {
        printf("test_fetch_lock: part 1 skipped (running as root)\n");
    }
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
    {   /* the .jsonl is slow (2 s): the lock is held after 1 s */
        struct timespec ts = {1, 0};
        nanosleep(&ts, NULL);
    }
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

    /* 3. two takers on a crashed lock */
    {
        char *cache3 = test_tmpdir();
        struct taker tk[2];
        pthread_t th[2];
        int k;
        lock = mkdirs(cache3, "20991231.2");
        mkdir(lock, 0777);
        test_write(lock, "owner.json", "{\"pid\":1,\"token\":\"crashed\",\"started_at\":\"2000-01-01T00:00:00Z\"}");
        for (k = 0; k < 2; k++) {
            otc_fetch_options_init(&tk[k].fo);
            otc_error_init(&tk[k].err);
            tk[k].fo.cache_dir = cache3;
            tk[k].fo.base_url = base;
            tk[k].fo.error = &tk[k].err;
            tk[k].fo.log_fn = count_removals;
        }
        for (k = 0; k < 2; k++) pthread_create(&th[k], NULL, take_thread, &tk[k]);
        for (k = 0; k < 2; k++) pthread_join(th[k], NULL);
        CHECK_STATUS(tk[0].st, OTC_OK);
        CHECK_STATUS(tk[1].st, OTC_OK);
        CHECK(g_removals == 1);
        if (g_removals != 1) fprintf(stderr, "stale lock removals: %d (the second taker removed the first one's young lock)\n", g_removals);
        free(lock);
        free(cache3);
    }
    free(cache);
    free(cache2);
    return test_done("test_fetch_lock");
}
