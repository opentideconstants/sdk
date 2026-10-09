/* Small helpers for the C library's own tests (c/tests). Each test is one
 * program that exits 0 when every CHECK holds. A test that needs the
 * conformance fixture server runs under c/tests/run_with_server.sh, which
 * sets OTC_TEST_SERVER (http://127.0.0.1:<port>) and OTC_TEST_PROXY. */
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

/* The conformance fixture server's base URL, or NULL (the test is then skipped). */
static const char *test_server(void)
{
    const char *s = getenv("OTC_TEST_SERVER");
    return s && s[0] ? s : NULL;
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
