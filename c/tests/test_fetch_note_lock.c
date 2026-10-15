/* PK04 / C113: note_entry (which records a pointer's version DOI in a cached
 * release's .verified) rewrites .verified only while it holds the release's
 * .lock. While another process holds it (a download or an index build that
 * also writes .verified), the note is skipped, not raced: .verified is still
 * there and unchanged, the other process's lock is left as it was, the call
 * says nothing in its error, and the skip is logged. A lock at least 120 s
 * old (a crashed process) is taken over (CR2 DR3). This test links the
 * library with the normal lock timers, so an alarm stops a regression that
 * waits for the lock (120 s) instead of skipping. */
#include "otc_test.h"
#include "otc_internal.h"

#include <signal.h>

static int g_skip_logged;

static void on_alarm(int sig)
{
    static const char m[] = "test_fetch_note_lock: timed out (the note waits for the lock?)\n";
    (void)sig;
    if (write(2, m, sizeof m - 1) < 0) _exit(1);
    _exit(1);
}

static void log_fn(void *u, int level, const char *msg)
{
    (void)u;
    if (level == 1 && strstr(msg, "is locked by another process")) g_skip_logged++;
}

/* 1 when .verified has needle, 0 when it has not, -1 when it cannot be read (a failure, never "has not") */
static int verified_has(const char *vpath, const char *needle)
{
    char *text = NULL;
    size_t len = 0;
    int r;
    if (otc__read_all(vpath, &text, &len) != OTC_OK) return -1;
    r = strstr(text, needle) != NULL;
    free(text);
    return r;
}

int main(void)
{
    char *cache = test_tmpdir(), base[512], path[4096], *dir, *vpath, *lock, *owner;
    otc_fetch_options fo;
    otc_release_info *info = NULL;
    otc_error err;
    size_t need;
    if (!test_server()) return test_skip("test_fetch_note_lock", "no OTC_TEST_SERVER");
    signal(SIGALRM, on_alarm);
    alarm(30);
    otc_fetch_options_init(&fo);
    otc_error_init(&err);
    snprintf(base, sizeof base, "%s/good/", test_server());
    fo.cache_dir = cache;
    fo.base_url = base;
    fo.error = &err;
    fo.log_fn = log_fn;
    CHECK_STATUS(otc_fetch_release(&fo, "20991231.2", path, sizeof path, &need), OTC_OK);
    dir = test_join(cache, "v1/releases/20991231.2");
    vpath = test_join(dir, ".verified");
    CHECK(verified_has(vpath, "10.5072/zenodo.2") == 0);   /* a pinned download reads no pointer entry */
    lock = test_join(dir, ".lock");
    owner = test_join(lock, "owner.json");
    if (mkdir(lock, 0777) != 0) { perror(lock); return 2; }
    test_write(lock, "owner.json", "{\"pid\":1,\"token\":\"another-process\"}");
    err.status = OTC_E_IO;   /* the call must leave its own result in err */
    CHECK_STATUS(otc_fetch_latest_info(&fo, &info), OTC_OK);
    otc_release_info_free(info);
    info = NULL;
    CHECK(err.status == OTC_OK);
    CHECK(g_skip_logged == 1);
    /* .verified is there and was not rewritten */
    CHECK(verified_has(vpath, "10.5072/zenodo.2") == 0);
    if (verified_has(vpath, "10.5072/zenodo.2") != 0) fprintf(stderr, ".verified was rewritten (or removed) while another process held the lock\n");
    /* the other process's lock is as it was */
    {
        char *text = NULL;
        size_t len = 0;
        CHECK(otc__read_all(owner, &text, &len) == OTC_OK && text && strstr(text, "another-process") != NULL);
        free(text);
    }
    /* a lock left by a crashed process (at least 120 s old) is taken over, and the
     * note is made (spec 5.4 non-blocking takes, CR2 DR3, R2-011) */
    test_write(lock, "owner.json", "{\"pid\":1,\"token\":\"crashed\",\"started_at\":\"2000-01-01T00:00:00Z\"}");
    CHECK_STATUS(otc_fetch_latest_info(&fo, &info), OTC_OK);
    otc_release_info_free(info);
    CHECK(verified_has(vpath, "10.5072/zenodo.2") == 1);
    CHECK(access(lock, F_OK) != 0);
    free(owner);
    free(lock);
    free(vpath);
    free(dir);
    free(cache);
    return test_done("test_fetch_note_lock");
}
