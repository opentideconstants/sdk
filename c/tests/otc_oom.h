/* Out-of-memory injection for the C library's own tests. Include it in one
 * test program only (it defines malloc, calloc, realloc and free). The test
 * links the static library, so the library's allocations come here:
 *   oom_arm(k)        the k-th allocation from now fails; oom_disarm() stops it
 *   oom_live          blocks allocated here and not yet freed
 * A test runs an operation with k = 1, 2, ... until no allocation fails, and
 * checks the status and that oom_live is back where it was (no leak).
 * Not used with sanitizers (they replace the allocator themselves). */
#ifndef OTC_OOM_H
#define OTC_OOM_H

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

static long oom_fail_at;   /* the allocation number that fails; 0 = none */
static long oom_count;     /* allocations since oom_arm */
static long oom_live;
static int oom_failed;     /* an injected failure happened */

static void oom_arm(long k)
{
    oom_fail_at = k;
    oom_count = 0;
    oom_failed = 0;
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

#endif /* OTC_OOM_H */
