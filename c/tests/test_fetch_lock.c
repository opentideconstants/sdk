/* PK04 / C19 and the lock protocol of spec 5.4 (CR D3). Built against a copy
 * of the library with short lock timers (stale after 0.6 s, polls of 50 ms).
 *  1. A stale lock that cannot be removed: OTC_E_CACHE after exactly 3 failed
 *     removals, each made only once the lock is stale (not an endless wait,
 *     and not at once).
 *  2. A live lock (younger than the stale time) is waited on, never removed:
 *     the other process's owner.json is still there while the fetch waits,
 *     and the fetch goes on once that process releases it. The fetch then
 *     releases its own lock (none is left), which is the control for 3.
 *  3. A lock taken over by another process while this one downloads: this
 *     one's release leaves the other's lock alone (owner.json token), and
 *     says so in the log. */
#include "otc_test.h"

#include <pthread.h>
#include <signal.h>
#include <time.h>

static otc_fetch_options g_fo;
static otc_status g_st;
static int g_done;                    /* the fetch thread returned (atomic) */
static int g_removals, g_left_alone;  /* log lines (atomic: the fetch thread logs) */

static void on_alarm(int sig)
{
    static const char m[] = "test_fetch_lock: timed out (the lock loop never ends)\n";
    (void)sig;
    if (write(2, m, sizeof m - 1) < 0) _exit(1);
    _exit(1);
}

static void log_fn(void *u, int level, const char *msg)
{
    (void)u;
    if (level == 2 && strstr(msg, "removing the stale lock")) __atomic_fetch_add(&g_removals, 1, __ATOMIC_SEQ_CST);
    if (level == 1 && strstr(msg, "now belongs to another process")) __atomic_fetch_add(&g_left_alone, 1, __ATOMIC_SEQ_CST);
}

static void *fetch_thread(void *arg)
{
    char path[4096];
    size_t need;
    (void)arg;
    g_st = otc_fetch_release(&g_fo, "20991231.2", path, sizeof path, &need);
    __atomic_store_n(&g_done, 1, __ATOMIC_SEQ_CST);
    return NULL;
}

static void start_fetch(pthread_t *t)
{
    __atomic_store_n(&g_done, 0, __ATOMIC_SEQ_CST);
    if (pthread_create(t, NULL, fetch_thread, NULL) != 0) {
        fprintf(stderr, "test_fetch_lock: pthread_create failed\n");
        exit(2);
    }
}

static void sleep_ms(long ms)
{
    struct timespec ts;
    ts.tv_sec = ms / 1000;
    ts.tv_nsec = (ms % 1000) * 1000000L;
    nanosleep(&ts, NULL);
}

static double now_s(void)
{
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + ts.tv_nsec / 1e9;
}

static char *mkdirs(const char *cache, const char *ds)
{
    char p[4096];
    snprintf(p, sizeof p, "%s/v1", cache);
    mkdir(p, 0777);
    snprintf(p, sizeof p, "%s/v1/releases", cache);
    mkdir(p, 0777);
    snprintf(p, sizeof p, "%s/v1/releases/%s", cache, ds);
    if (mkdir(p, 0777) != 0) { perror(p); exit(2); }
    return test_join(p, ".lock");
}

/* another process's lock: the directory and its owner.json */
static void foreign_lock(const char *lock, const char *token)
{
    char text[128];
    if (mkdir(lock, 0777) != 0) { perror(lock); exit(2); }
    snprintf(text, sizeof text, "{\"pid\":1,\"token\":\"%s\"}", token);
    test_write(lock, "owner.json", text);
}

/* 1 when lock/owner.json holds token */
static int owned_by(const char *lock, const char *token)
{
    char *owner = test_join(lock, "owner.json"), buf[256];
    FILE *f = fopen(owner, "rb");
    size_t n;
    free(owner);
    if (!f) return 0;
    n = fread(buf, 1, sizeof buf - 1, f);
    buf[n] = '\0';
    fclose(f);
    return strstr(buf, token) != NULL;
}

static void drop_lock(const char *lock)
{
    char *owner = test_join(lock, "owner.json");
    if (unlink(owner) != 0 || rmdir(lock) != 0) { perror(lock); exit(2); }
    free(owner);
}

static void options(const char *cache, const char *base, otc_error *err)
{
    otc_fetch_options_init(&g_fo);
    otc_error_init(err);
    g_fo.cache_dir = cache;
    g_fo.base_url = base;
    g_fo.error = err;
    g_fo.log_fn = log_fn;
}

int main(void)
{
    char *cache = test_tmpdir(), *cache2 = test_tmpdir(), *cache3 = test_tmpdir(), base[512], path[4096], *lock, *owner;
    otc_error err;
    size_t need;
    pthread_t t;
    int i;
    if (!test_server()) return test_skip("test_fetch_lock", "no OTC_TEST_SERVER");
    signal(SIGALRM, on_alarm);
    alarm(60);
    snprintf(base, sizeof base, "%s/good/", test_server());

    /* 1. an unremovable stale lock (when permissions do not stop this process, nothing is
     *    unremovable: skipped) */
    options(cache, base, &err);
    lock = mkdirs(cache, "20991231.2");
    foreign_lock(lock, "someone-else");
    test_chmod(lock, 0555);
    if (!test_is_root()) {
        double t0 = now_s(), took;
        __atomic_store_n(&g_removals, 0, __ATOMIC_SEQ_CST);
        CHECK_STATUS(otc_fetch_release(&g_fo, "20991231.2", path, sizeof path, &need), OTC_E_CACHE);
        took = now_s() - t0;
        CHECK(strstr(err.message, "stale lock") != NULL);
        CHECK(__atomic_load_n(&g_removals, __ATOMIC_SEQ_CST) == 3);
        if (__atomic_load_n(&g_removals, __ATOMIC_SEQ_CST) != 3)
            fprintf(stderr, "part 1: %d removals, want 3\n", __atomic_load_n(&g_removals, __ATOMIC_SEQ_CST));
        CHECK(took >= 0.55);   /* the lock is stale after 0.6 s of waiting, not at once */
        if (took < 0.55) fprintf(stderr, "part 1: gave up after %.2f s, before the lock was stale\n", took);
    } else {
        printf("test_fetch_lock: part 1 skipped (file permissions do not stop this process)\n");
    }
    test_chmod(lock, 0755);
    free(lock);

    /* 2. a live lock: waited on while it is younger than the stale time, then taken once it is released */
    options(cache3, base, &err);
    lock = mkdirs(cache3, "20991231.2");
    foreign_lock(lock, "a-live-process");
    start_fetch(&t);
    sleep_ms(300);   /* half the stale time */
    CHECK(owned_by(lock, "a-live-process"));
    CHECK(!__atomic_load_n(&g_done, __ATOMIC_SEQ_CST));
    if (!owned_by(lock, "a-live-process")) fprintf(stderr, "part 2: a live lock was removed after 0.3 s\n");
    drop_lock(lock);
    pthread_join(t, NULL);
    CHECK_STATUS(g_st, OTC_OK);
    CHECK(access(lock, F_OK) != 0);   /* the fetch released its own lock */
    free(lock);

    /* 3. a lock taken over while the download runs (the .jsonl is slow: 2 s) */
    options(cache2, base, &err);
    __atomic_store_n(&g_left_alone, 0, __ATOMIC_SEQ_CST);
    lock = mkdirs(cache2, "20991231.2");
    owner = test_join(lock, "owner.json");
    start_fetch(&t);
    for (i = 0; i < 500 && access(owner, F_OK) != 0; i++) sleep_ms(10);   /* the fetch holds the lock */
    if (access(owner, F_OK) != 0) {
        fprintf(stderr, "part 3: the fetch did not take the lock within 5 s\n");
        pthread_join(t, NULL);
        CHECK(0);
    } else {
        sleep_ms(50);   /* its owner.json is written */
        CHECK(!__atomic_load_n(&g_done, __ATOMIC_SEQ_CST));   /* still downloading */
        drop_lock(lock);
        foreign_lock(lock, "the-other-process");
        pthread_join(t, NULL);
        CHECK_STATUS(g_st, OTC_OK);
        CHECK(owned_by(lock, "the-other-process"));
        if (!owned_by(lock, "the-other-process")) fprintf(stderr, "the first holder's release removed the other process's lock\n");
        CHECK(__atomic_load_n(&g_left_alone, __ATOMIC_SEQ_CST) == 1);   /* its release ran and saw the other token */
    }
    free(owner);
    free(lock);
    free(cache);
    free(cache2);
    free(cache3);
    return test_done("test_fetch_lock");
}
