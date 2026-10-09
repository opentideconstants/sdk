/* PK04 / C113: note_entry (which records a pointer's version DOI in a cached
 * release's .verified) rewrites .verified only while it holds the release's
 * .lock. While another process holds it (a download or an index build that
 * also writes .verified), the note is skipped, not raced. A lock at least
 * 120 s old (a crashed process) is taken over (CR2 DR3). */
#include "otc_test.h"

static int verified_has(const char *vpath, const char *needle)
{
    char buf[1 << 15];
    size_t n;
    FILE *f = fopen(vpath, "rb");
    if (!f) return 0;
    n = fread(buf, 1, sizeof buf - 1, f);
    fclose(f);
    buf[n] = '\0';
    return strstr(buf, needle) != NULL;
}

int main(void)
{
    char *cache = test_tmpdir(), base[512], path[4096], *dir, *vpath, *lock;
    otc_fetch_options fo;
    otc_release_info *info = NULL;
    otc_error err;
    size_t need;
    if (!test_server()) { printf("test_fetch_note_lock: skipped (no OTC_TEST_SERVER)\n"); return 0; }
    otc_fetch_options_init(&fo);
    otc_error_init(&err);
    snprintf(base, sizeof base, "%s/good/", test_server());
    fo.cache_dir = cache;
    fo.base_url = base;
    fo.error = &err;
    CHECK_STATUS(otc_fetch_release(&fo, "20991231.2", path, sizeof path, &need), OTC_OK);
    dir = test_join(cache, "v1/releases/20991231.2");
    vpath = test_join(dir, ".verified");
    CHECK(!verified_has(vpath, "10.5072/zenodo.2"));   /* a pinned download reads no pointer entry */
    lock = test_join(dir, ".lock");
    mkdir(lock, 0777);
    test_write(lock, "owner.json", "{\"pid\":1,\"token\":\"another-process\"}");
    CHECK_STATUS(otc_fetch_latest_info(&fo, &info), OTC_OK);
    otc_release_info_free(info);
    info = NULL;
    CHECK(!verified_has(vpath, "10.5072/zenodo.2"));
    if (verified_has(vpath, "10.5072/zenodo.2")) fprintf(stderr, ".verified was rewritten while another process held the lock\n");
    /* a lock left by a crashed process (at least 120 s old) is taken over, and the
     * note is made (spec 5.4 non-blocking takes, CR2 DR3, R2-011) */
    test_write(lock, "owner.json", "{\"pid\":1,\"token\":\"crashed\",\"started_at\":\"2000-01-01T00:00:00Z\"}");
    CHECK_STATUS(otc_fetch_latest_info(&fo, &info), OTC_OK);
    otc_release_info_free(info);
    CHECK(verified_has(vpath, "10.5072/zenodo.2"));
    CHECK(access(lock, F_OK) != 0);
    free(lock);
    free(vpath);
    free(dir);
    free(cache);
    return test_done("test_fetch_note_lock");
}
