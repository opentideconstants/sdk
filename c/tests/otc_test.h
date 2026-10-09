/* Small helpers for the C library's own tests (c/tests). Each test is one
 * program that exits 0 when every CHECK holds, and TEST_SKIP_RC (77, ctest's
 * SKIP_RETURN_CODE) when it skips itself. A test that needs the conformance
 * fixture server runs under c/tests/run_with_server.sh, which sets
 * OTC_TEST_SERVER (http://127.0.0.1:<port>), OTC_TEST_PROXY and
 * OTC_TEST_REQUIRE_SERVER=1. */
#ifndef OTC_TEST_H
#define OTC_TEST_H

#if !defined(_WIN32) && !defined(_XOPEN_SOURCE)
#define _XOPEN_SOURCE 700 /* mkdtemp, setenv */
#endif
#if defined(__APPLE__) && !defined(_DARWIN_C_SOURCE)
#define _DARWIN_C_SOURCE
#endif

#include "opentideconstants.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef _WIN32
#include <sys/stat.h>
#include <unistd.h>
#endif

static int g_failures;

#define CHECK(cond)                                                                                 \
    do {                                                                                            \
        if (!(cond)) {                                                                              \
            fprintf(stderr, "%s:%d: CHECK failed: %s\n", __FILE__, __LINE__, #cond);                \
            g_failures++;                                                                           \
        }                                                                                           \
    } while (0)

#define CHECK_STATUS(got, want)                                                                     \
    do {                                                                                            \
        otc_status got_ = (got), want_ = (want);                                                    \
        if (got_ != want_) {                                                                        \
            fprintf(stderr, "%s:%d: %s gave %s, want %s\n", __FILE__, __LINE__, #got,               \
                    otc_status_code(got_), otc_status_code(want_));                                 \
            g_failures++;                                                                           \
        }                                                                                           \
    } while (0)

static int test_done(const char *name)
{
    if (g_failures) fprintf(stderr, "%s: %d check(s) failed\n", name, g_failures);
    else printf("%s: ok\n", name);
    return g_failures ? 1 : 0;
}

/* A fresh directory under TMPDIR; the caller frees the path. */
static char *test_tmpdir(void)
{
    const char *t = getenv("TMPDIR");
    char *p = (char *)malloc(4096);
    if (!p) exit(2);
    snprintf(p, 4096, "%s/otc-test-XXXXXX", t && t[0] ? t : "/tmp");
    if (!mkdtemp(p)) { perror("mkdtemp"); exit(2); }
    return p;
}

static char *test_join(const char *dir, const char *name)
{
    size_t n = strlen(dir) + strlen(name) + 2;
    char *p = (char *)malloc(n);
    if (!p) exit(2);
    snprintf(p, n, "%s/%s", dir, name);
    return p;
}

static void test_write(const char *dir, const char *name, const char *text)
{
    char *p = test_join(dir, name);
    FILE *f = fopen(p, "wb");
    if (!f || fwrite(text, 1, strlen(text), f) != strlen(text) || fclose(f) != 0) { perror(p); exit(2); }
    free(p);
}

/* The exit status of a test that skips itself; c/CMakeLists.txt registers it as
 * SKIP_RETURN_CODE, so ctest reports "Skipped", not "Passed". */
#define TEST_SKIP_RC 77

/* Prints why NAME is skipped and gives TEST_SKIP_RC: return test_skip(...). */
static int test_skip(const char *name, const char *why)
{
    printf("%s: skipped (%s)\n", name, why);
    fflush(stdout);
    return TEST_SKIP_RC;
}

/* Whether file permissions stop this process, found by trying, not from the uid:
 * root without CAP_DAC_OVERRIDE is stopped, and a user with it is not (and
 * access() answers for the real uid without capabilities, so it cannot tell).
 * The parts of a test that need an unwritable or unreadable directory skip
 * when these give 1. Each probe uses a fresh directory and is done once. */
#ifndef _WIN32
#include <dirent.h>

/* chmod that must work: a probe or test that cannot set the mode is broken */
static void test_chmod(const char *path, mode_t mode)
{
    if (chmod(path, mode) != 0) { perror(path); exit(2); }
}

static void test_probe_done(char *dir, char *file)
{
    test_chmod(dir, 0755);
    if (file) remove(file);
    if (rmdir(dir) != 0) { perror(dir); exit(2); }
    free(file);
    free(dir);
}
#endif

/* 1 when this process can make a file in a 0555 directory. */
static int test_write_perms_ignored(void)
{
#ifdef _WIN32
    return 0;
#else
    static int known = -1;
    char *dir, *file;
    FILE *f;
    if (known >= 0) return known;
    dir = test_tmpdir();
    file = test_join(dir, "probe");
    test_chmod(dir, 0555);
    f = fopen(file, "wb");
    known = f != NULL;
    if (f) fclose(f);
    test_probe_done(dir, file);
    return known;
#endif
}

/* 1 when this process can list a 0000 directory. */
static int test_read_perms_ignored(void)
{
#ifdef _WIN32
    return 0;
#else
    static int known = -1;
    char *dir;
    DIR *d;
    if (known >= 0) return known;
    dir = test_tmpdir();
    test_chmod(dir, 0000);
    d = opendir(dir);
    known = d != NULL;
    if (d) closedir(d);
    test_probe_done(dir, NULL);
    return known;
#endif
}

/* The old name, kept for its callers (a 0555 directory that must stop a
 * removal): it is test_write_perms_ignored and no longer looks at the uid. */
static int test_is_root(void)
{
    return test_write_perms_ignored();
}

/* The conformance fixture server's base URL. Under run_with_server.sh
 * (OTC_TEST_REQUIRE_SERVER set, not "0") a missing or empty OTC_TEST_SERVER is
 * a failure: the program exits 2, so a broken wrapper cannot turn every fetch
 * test into a pass. Run by hand without the wrapper it is NULL. */
static const char *test_server(void)
{
    const char *s = getenv("OTC_TEST_SERVER");
    const char *req = getenv("OTC_TEST_REQUIRE_SERVER");
    if (s && s[0]) return s;
    if (req && req[0] && strcmp(req, "0") != 0) {
        fprintf(stderr, "OTC_TEST_SERVER is empty but OTC_TEST_REQUIRE_SERVER is set: the fixture server address "
                        "is missing, which is a failure, not a skip\n");
        exit(2);
    }
    return NULL;
}

/* A minimal release: format 1.0, one convention, one licence. */
#define TEST_META(ds)                                                                               \
    "{\"format_version\":\"1.0\",\"release\":{\"datestamp\":\"" ds "\",\"created\":\"2099-12-31T00:00:00Z\"},"  \
    "\"conventions\":[{\"convention_id\":\"c1\"}],\"licences\":[{\"licence_id\":\"l1\",\"provider\":\"P\","     \
    "\"attribution\":\"A\"}]}"

#define TEST_STATION(id, name)                                                                      \
    "{\"station_id\":\"" id "\",\"status\":\"active\",\"name\":\"" name "\",\"lat\":1.0,\"lon\":2.0,"         \
    "\"type\":\"reference\",\"recommended_set_id\":\"" id "/s\",\"constant_sets\":[{\"set_id\":\"" id "/s\","  \
    "\"source\":\"src\",\"source_type\":\"official\",\"quantity\":\"water_level\",\"qc_status\":\"ok\","       \
    "\"convention_id\":\"c1\",\"licence_id\":\"l1\",\"constituents\":[{\"name\":\"M2\",\"amplitude_m\":1.0,"   \
    "\"phase_deg\":10.0}]}]}"

#endif /* OTC_TEST_H */
