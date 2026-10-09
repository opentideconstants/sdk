/* Out-of-memory injection for the C library's own tests. Include it in one
 * test program only (it defines malloc, calloc, realloc and free). The test
 * links the static library, so the library's allocations come here:
 *   oom_arm(k)        the k-th allocation from now fails; oom_disarm() stops it
 *   oom_live          blocks allocated here and not yet freed
 * A test runs an operation with k = 1, 2, ... until no allocation fails, and
 * checks the status and that oom_live is back where it was (no leak). Every
 * loop stops at OOM_MAX_RUNS (a run count no operation here comes near: one
 * that does is a failure, not a hang), and oom_loop_end checks that the loop
 * injected at least one failure (else the hooks did not see the library's
 * allocations and the loop tested nothing).
 *   oom_hook_cjson()  routes cJSON's allocations through a wrapper, so that
 *                     oom_cjson_failed tells whether the failed allocation was
 *                     one of cJSON's (whose parse then reads as "not JSON")
 * Not used with sanitizers (they replace the allocator themselves). The hooks
 * see only allocations made through these four names: on macOS the C library's
 * own allocations (fopen, opendir) go to libsystem_malloc directly and never
 * fail here; on glibc they do. */
#ifndef OTC_OOM_H
#define OTC_OOM_H

#include <errno.h>
#include <stddef.h>
#include <string.h>

#if defined(__APPLE__)
#include <malloc/malloc.h>
#define REAL_MALLOC(n) malloc_zone_malloc(malloc_default_zone(), (n))
#define REAL_CALLOC(a, b) malloc_zone_calloc(malloc_default_zone(), (a), (b))
#define REAL_REALLOC(p, n) malloc_zone_realloc(malloc_default_zone(), (p), (n))
#define REAL_FREE(p) malloc_zone_free(malloc_default_zone(), (p))
#elif defined(__GLIBC__)
extern void *__libc_malloc(size_t);
extern void *__libc_calloc(size_t, size_t);
extern void *__libc_realloc(void *, size_t);
extern void __libc_free(void *);
#define REAL_MALLOC(n) __libc_malloc(n)
#define REAL_CALLOC(a, b) __libc_calloc((a), (b))
#define REAL_REALLOC(p, n) __libc_realloc((p), (n))
#define REAL_FREE(p) __libc_free(p)
#else
#error "otc_oom.h supports macOS and glibc"
#endif

#include "otc_cjson_rename.h"
#include "cJSON.h"

#define OOM_MAX_RUNS 10000L

static long oom_fail_at;   /* the allocation number that fails; 0 = none */
static long oom_count;     /* allocations since oom_arm */
static long oom_live;
static int oom_failed;     /* an injected failure happened */
static int oom_cjson_failed; /* and it was an allocation of cJSON's (oom_hook_cjson) */

static void oom_arm(long k)
{
    oom_fail_at = k;
    oom_count = 0;
    oom_failed = 0;
    oom_cjson_failed = 0;
}

/* Stops the injection; oom_failed still tells whether a failure happened. */
static void oom_disarm(void)
{
    oom_fail_at = 0;
}

static int oom_should_fail(void)
{
    if (!oom_fail_at) return 0;
    if (++oom_count != oom_fail_at) return 0;
    oom_failed = 1;
    errno = ENOMEM;   /* as a real malloc does: the C library's own callers (opendir, fopen) read it */
    return 1;
}

void *malloc(size_t n)
{
    void *p;
    if (oom_should_fail()) return NULL;
    p = REAL_MALLOC(n ? n : 1);
    if (p) oom_live++;
    return p;
}

void *calloc(size_t a, size_t b)
{
    void *p;
    if (oom_should_fail()) return NULL;
    p = REAL_CALLOC(a ? a : 1, b ? b : 1);
    if (p) oom_live++;
    return p;
}

void *realloc(void *q, size_t n)
{
    void *p;
    if (!q) return malloc(n);
    if (oom_should_fail()) return NULL;
    p = REAL_REALLOC(q, n ? n : 1);
    return p;
}

void free(void *p)
{
    if (!p) return;
    oom_live--;
    REAL_FREE(p);
}

static void *oom_cjson_malloc(size_t n)
{
    void *p = malloc(n);
    if (!p && oom_failed) oom_cjson_failed = 1;
    return p;
}

static void oom_cjson_free(void *p)
{
    free(p);
}

static void oom_hook_cjson(void)
{
    cJSON_Hooks h;
    h.malloc_fn = oom_cjson_malloc;
    h.free_fn = oom_cjson_free;
    cJSON_InitHooks(&h);
}

/* After a loop over k: it ended by itself (below OOM_MAX_RUNS) and its first
 * run, k = 1, injected a failure. Gives 1 when both hold. */
static int oom_loop_end(const char *what, long k, long injected)
{
    if (k > OOM_MAX_RUNS) {
        fprintf(stderr, "%s: still failing allocations after %ld runs: the loop is cut off\n", what, OOM_MAX_RUNS);
        return 0;
    }
    if (injected < 1) {
        fprintf(stderr, "%s: no allocation was made to fail, so nothing was tested (do the hooks see the library?)\n",
                what);
        return 0;
    }
    return 1;
}

#endif /* OTC_OOM_H */
