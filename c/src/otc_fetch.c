/*
 * The optional otc_fetch module (SDK spec 4.3, 5, 6.4): downloads releases
 * with libcurl into the cache layout that every SDK on the machine shares
 * (spec 5.4), and writes releases into a folder the app chooses (4.3.2).
 * Built only with -DOTC_WITH_FETCH=ON; otherwise otc_fetch_stub.c is built.
 *
 * Cache: <root>/v1/pointer/{OTC_latest-f1.json,OTC_latest.json,OTC_index.json}(+.etag) and
 * <root>/v1/releases/<D>/{OTC_<D>.sha256,.jsonl,.meta.json,[.json],
 * index-v1.json,.verified}. Every file is written to .tmp-<pid>-<random> in
 * the same directory, fsynced and renamed into place; .verified is last. A
 * .lock/ directory (owner.json inside) only stops duplicate work.
 */
/* fsync, gethostname, nanosleep and gmtime_r are XSI / POSIX 2008 on glibc */
#if !defined(_WIN32) && !defined(_XOPEN_SOURCE)
#define _XOPEN_SOURCE 700
#endif
#if defined(_WIN32) && !defined(_CRT_RAND_S)
#define _CRT_RAND_S   /* rand_s, for the lock token */
#endif
#include "otc_internal.h"
#include "otc_sha256_rename.h"
#include "sha-256.h"

#include <curl/curl.h>
#include <errno.h>
#include <stddef.h>
#include <time.h>

#ifdef _WIN32
#include <direct.h>
#include <io.h>
#include <process.h>
#include <sys/stat.h>
#include <sys/types.h>
#else
#include <dirent.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#endif

#define DEFAULT_BASE_URL "https://data.opentideconstants.org/"
#define LAYOUT "v1"
#define SDK_ID "opentideconstants-c/" OTC_VERSION
#define USER_AGENT SDK_ID " (+https://opentideconstants.org)"
#define CONNECT_TIMEOUT_S 10.0
#define READ_TIMEOUT_S 60.0
#define TIMEOUT_MAX_S 1.0e6
#define ATTEMPTS 3
#define RETRY_AFTER_MAX_S 60.0
/* spec 5.4 Locks; the tests (c/tests/test_fetch_lock.c) build a copy with short timers */
#ifdef OTC_LOCK_POLL_MS
#define LOCK_POLL_MS OTC_LOCK_POLL_MS
#else
#define LOCK_POLL_MS 500
#endif
#ifdef OTC_LOCK_STALE_MS
#define LOCK_STALE_MS OTC_LOCK_STALE_MS
#else
#define LOCK_STALE_MS 120000
#endif
/* how old the lock itself must be to be stale (spec 5.4, CR2 DR3); the tests keep 120 s */
#define LOCK_STALE_AGE_S 120

/* ------------------------------------------------------------- one-time init */

static otc__mutex g_lock;
static unsigned long g_counter;
static int g_curl_ok;

static void init_once_body(void)
{
    otc__mutex_init(&g_lock);
    g_curl_ok = curl_global_init(CURL_GLOBAL_DEFAULT) == CURLE_OK;
}

#ifdef _WIN32
static INIT_ONCE g_once = INIT_ONCE_STATIC_INIT;
static BOOL CALLBACK init_once_cb(PINIT_ONCE o, PVOID p, PVOID *c)
{
    (void)o; (void)p; (void)c;
    init_once_body();
    return TRUE;
}
static void init_once(void) { InitOnceExecuteOnce(&g_once, init_once_cb, NULL, NULL); }
#else
static pthread_once_t g_once = PTHREAD_ONCE_INIT;
static void init_once(void) { pthread_once(&g_once, init_once_body); }
#endif

/* ----------------------------------------------------------------- platform */

static void sleep_ms(long ms)
{
#ifdef _WIN32
    Sleep((DWORD)ms);
#else
    struct timespec ts;
    ts.tv_sec = ms / 1000;
    ts.tv_nsec = (ms % 1000) * 1000000L;
    while (nanosleep(&ts, &ts) != 0 && errno == EINTR) {}
#endif
}

static long get_pid(void)
{
#ifdef _WIN32
    return (long)_getpid();
#else
    return (long)getpid();
#endif
}

#ifdef _WIN32
static wchar_t *widen(const char *s)
{
    int n = MultiByteToWideChar(CP_UTF8, 0, s, -1, NULL, 0);
    wchar_t *w;
    if (n <= 0) return NULL;
    w = (wchar_t *)malloc((size_t)n * sizeof *w);
    if (w && MultiByteToWideChar(CP_UTF8, 0, s, -1, w, n) <= 0) { free(w); w = NULL; }
    return w;
}

static char *narrow(const wchar_t *w)
{
    int n = WideCharToMultiByte(CP_UTF8, 0, w, -1, NULL, 0, NULL, NULL);
    char *s;
    if (n <= 0) return NULL;
    s = (char *)malloc((size_t)n);
    if (s && WideCharToMultiByte(CP_UTF8, 0, w, -1, s, n, NULL, NULL) <= 0) { free(s); s = NULL; }
    return s;
}
#endif

static FILE *fs_fopen(const char *path, const char *mode)
{
#ifdef _WIN32
    wchar_t *w = widen(path), wm[8];
    FILE *f = NULL;
    size_t i;
    for (i = 0; mode[i] && i < 7; i++) wm[i] = (wchar_t)mode[i];
    wm[i] = 0;
    if (w) f = _wfopen(w, wm);
    free(w);
    return f;
#else
    return fopen(path, mode);
#endif
}

/* 1 directory, 2 other file, 0 nothing there */
static int fs_kind(const char *path)
{
#ifdef _WIN32
    wchar_t *w = widen(path);
    DWORD a = w ? GetFileAttributesW(w) : INVALID_FILE_ATTRIBUTES;
    free(w);
    if (a == INVALID_FILE_ATTRIBUTES) return 0;
    return (a & FILE_ATTRIBUTE_DIRECTORY) ? 1 : 2;
#else
    struct stat sb;
    if (stat(path, &sb) != 0) return 0;
    return S_ISDIR(sb.st_mode) ? 1 : 2;
#endif
}

/* 0 created, 1 already exists, -1 error */
static int fs_mkdir(const char *path)
{
#ifdef _WIN32
    wchar_t *w = widen(path);
    int r, e;
    if (!w) return -1;   /* no conversion: an error, never "exists" from a stale errno */
    r = _wmkdir(w);
    e = errno;
    free(w);
    if (r == 0) return 0;
    return e == EEXIST ? 1 : -1;
#else
    if (mkdir(path, 0777) == 0) return 0;
    return errno == EEXIST ? 1 : -1;
#endif
}

static int fs_rmdir(const char *path)
{
#ifdef _WIN32
    wchar_t *w = widen(path);
    int r = w ? _wrmdir(w) : -1;
    free(w);
    return r;
#else
    return rmdir(path);
#endif
}

static int fs_unlink(const char *path)
{
#ifdef _WIN32
    wchar_t *w = widen(path);
    int r = w ? _wunlink(w) : -1;
    free(w);
    return r;
#else
    return unlink(path);
#endif
}

/* rename, replacing the target (MoveFileEx with MOVEFILE_REPLACE_EXISTING on Windows) */
static int fs_rename(const char *from, const char *to)
{
#ifdef _WIN32
    wchar_t *a = widen(from), *b = widen(to);
    BOOL ok = a && b && MoveFileExW(a, b, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH);
    free(a);
    free(b);
    return ok ? 0 : -1;
#else
    return rename(from, to);
#endif
}

/* Flushes a file opened for writing to the disk. */
static int fs_fsync(FILE *f)
{
    if (fflush(f) != 0) return -1;
#ifdef _WIN32
    return _commit(_fileno(f));
#else
    return fsync(fileno(f));
#endif
}

static void free_list(char **v, size_t n)
{
    size_t i;
    for (i = 0; i < n; i++) free(v[i]);
    free(v);
}

/* The names in a directory (not . and ..). */
static otc_status fs_list(const char *dir, char ***out, size_t *n_out)
{
    char **v = NULL;
    size_t n = 0, cap = 0;
#ifdef _WIN32
    char *pat = otc__join(dir, "/*");
    wchar_t *w = pat ? widen(pat) : NULL;
    WIN32_FIND_DATAW fd;
    HANDLE h;
    *out = NULL;
    *n_out = 0;
    free(pat);
    if (!w) return OTC_E_NOMEM;
    h = FindFirstFileW(w, &fd);
    free(w);
    if (h == INVALID_HANDLE_VALUE) return OTC_E_IO;
    do {
        char *name = narrow(fd.cFileName);
        if (!name) continue;
        if (!strcmp(name, ".") || !strcmp(name, "..")) { free(name); continue; }
        if (n == cap) {
            char **nv = (char **)realloc(v, (cap ? cap * 2 : 16) * sizeof *nv);
            if (!nv) { free(name); FindClose(h); free_list(v, n); return OTC_E_NOMEM; }
            v = nv;
            cap = cap ? cap * 2 : 16;
        }
        v[n++] = name;
    } while (FindNextFileW(h, &fd));
    FindClose(h);
#else
    DIR *d = opendir(dir);
    struct dirent *e;
    *out = NULL;
    *n_out = 0;
    if (!d) return errno == ENOMEM ? OTC_E_NOMEM : OTC_E_IO;
    while ((e = readdir(d)) != NULL) {
        char *name;
        if (!strcmp(e->d_name, ".") || !strcmp(e->d_name, "..")) continue;
        name = otc__strdup(e->d_name);
        if (!name) { closedir(d); free_list(v, n); return OTC_E_NOMEM; }
        if (n == cap) {
            char **nv = (char **)realloc(v, (cap ? cap * 2 : 16) * sizeof *nv);
            if (!nv) { free(name); closedir(d); free_list(v, n); return OTC_E_NOMEM; }
            v = nv;
            cap = cap ? cap * 2 : 16;
        }
        v[n++] = name;
    }
    closedir(d);
#endif
    *out = v;
    *n_out = n;
    return OTC_OK;
}

static char *path2(const char *a, const char *b)
{
    size_t la = strlen(a), lb = strlen(b);
    char *p = (char *)malloc(la + lb + 2);
    if (!p) return NULL;
    memcpy(p, a, la);
    p[la] = '/';
    memcpy(p + la + 1, b, lb + 1);
    return p;
}

/* 1 a real directory (not a symlink or junction to one), 2 anything else that
 * exists, 0 nothing there. Unlike fs_kind it never follows a link. */
static int fs_kind_nofollow(const char *path)
{
#ifdef _WIN32
    wchar_t *w = widen(path);
    DWORD a = w ? GetFileAttributesW(w) : INVALID_FILE_ATTRIBUTES;
    free(w);
    if (a == INVALID_FILE_ATTRIBUTES) return 0;
    return (a & FILE_ATTRIBUTE_DIRECTORY) && !(a & FILE_ATTRIBUTE_REPARSE_POINT) ? 1 : 2;
#else
    struct stat sb;
    if (lstat(path, &sb) != 0) return 0;
    return S_ISDIR(sb.st_mode) ? 1 : 2;
#endif
}

/* rm -r that never follows a symlink: a link is removed, not what it points
 * to. 0 when nothing is left at path, -1 when something could not be removed,
 * -2 when memory ran out (something may be left). */
static int fs_rm_rf(const char *path)
{
    int k = fs_kind_nofollow(path), bad = 0;
    if (k == 0) return 0;
    if (k == 1) {
        char **names = NULL;
        size_t n = 0, i;
        otc_status st = fs_list(path, &names, &n);
        if (st != OTC_OK) return st == OTC_E_NOMEM ? -2 : -1;
        for (i = 0; i < n; i++) {
            char *p = path2(path, names[i]);
            int r = p ? fs_rm_rf(p) : -2;
            if (r == -2 || (r && !bad)) bad = r;
            free(p);
        }
        free_list(names, n);
        if (bad == -2) return -2;
        if (fs_rmdir(path) != 0) bad = -1;
    } else {
#ifdef _WIN32
        /* a directory junction or symlink is removed with rmdir, a file with unlink */
        if (fs_unlink(path) != 0 && fs_rmdir(path) != 0) bad = 1;
#else
        if (fs_unlink(path) != 0) bad = 1;
#endif
    }
    return (bad || fs_kind_nofollow(path) != 0) ? -1 : 0;
}

/* mkdir -p; 0 when path is a directory afterwards */
/* 0, or -1 when a directory cannot be created, or -2 when memory runs out. */
static int fs_mkdir_p(const char *path)
{
    char *p = otc__strdup(path);
    size_t i, n;
    int ok;
    size_t start = 1;
    if (!p) return -2;
    n = strlen(p);
    while (n > 1 && (p[n - 1] == '/' || p[n - 1] == '\\')) p[--n] = '\0';
#ifdef _WIN32
    /* a UNC root (\\server\share\...): the server and the share are not directories to create */
    if (n > 2 && (p[0] == '\\' || p[0] == '/') && (p[1] == '\\' || p[1] == '/')) {
        int parts = 0;
        for (start = 2; start < n && parts < 2; start++)
            if (p[start] == '\\' || p[start] == '/') parts++;
    }
#endif
    for (i = start; i < n; i++) {
        if (p[i] == '/' || p[i] == '\\') {
            char c = p[i];
            if (p[i - 1] == ':' || p[i - 1] == '/' || p[i - 1] == '\\') continue; /* C:\ or // */
            p[i] = '\0';
            if (fs_kind(p) != 1 && fs_mkdir(p) < 0 && fs_kind(p) != 1) { free(p); return -1; }
            p[i] = c;
        }
    }
    if (fs_kind(p) != 1) fs_mkdir(p);
    ok = fs_kind(p) == 1;
    free(p);
    return ok ? 0 : -1;
}

/* <dir>/.tmp-<pid>-<12 hex> */
/* <dir>/<prefix><pid>-<random>: prefix ".tmp-" for a new file, ".tmp-bak-" for an original set aside */
static char *tmp_path_p(const char *dir, const char *prefix)
{
    static const char digits[] = "0123456789abcdef";
    char name[64];
    unsigned long long x;
    unsigned long c;
    int i;
    init_once();
    otc__mutex_lock(&g_lock);
    c = ++g_counter;
    otc__mutex_unlock(&g_lock);
    x = (unsigned long long)time(NULL) * 6364136223846793005ULL ^ (unsigned long long)clock() << 20
        ^ (unsigned long long)c * 0x9E3779B97F4A7C15ULL ^ (unsigned long long)(size_t)&x;
    x ^= x >> 33;
    x *= 0xff51afd7ed558ccdULL;
    x ^= x >> 33;
    i = snprintf(name, sizeof name, "%s%ld-", prefix, get_pid());
    if (i < 0 || i > (int)sizeof name - 13) return NULL;
    for (c = 0; c < 12; c++) name[i++] = digits[(x >> (4 * c)) & 15];
    name[i] = '\0';
    return path2(dir, name);
}

static char *tmp_path(const char *dir) { return tmp_path_p(dir, ".tmp-"); }

/* --------------------------------------------------------------------- context */

typedef struct fctx {
    const otc_fetch_options *o;
    otc_error  *err;
    char       *base;      /* <cache root>/v1 */
    char       *base_url;
    int         offline;
    unsigned    formats;
    double      connect_s, read_s;
    int         raise;     /* on_network_error RAISE */
    otc_error   own;       /* the error detail when the caller passed none */
    const otc_open_options *oo;   /* otc_fetch_open's caller options (log_fn, require_checksum), or NULL */
} fctx;

/* The options of an open of a cached file: the caller's (otc_fetch_open), with
 * the error detail going to the fetch context. */
static void cache_open_options(const fctx *c, otc_open_options *oo)
{
    otc_open_options_init(oo);
    if (c->oo) {
        oo->require_checksum = c->oo->require_checksum;
        oo->log_fn = c->oo->log_fn;
        oo->log_user_data = c->oo->log_user_data;
    }
    oo->error = c->err;
}

static void logf_(const fctx *c, int level, const char *fmt, ...)
{
    char msg[1024];
    va_list ap;
    if (!c->o || !c->o->log_fn) return;
    va_start(ap, fmt);
    vsnprintf(msg, sizeof msg, fmt, ap);
    va_end(ap);
    c->o->log_fn(c->o->log_user_data, level, msg);
}

static otc_status fail(fctx *c, otc_status st, const char *file, const char *fmt, ...)
{
    char msg[512];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(msg, sizeof msg, fmt, ap);
    va_end(ap);
    otc__err_set(c->err, st, file, "%s", msg);
    return st;
}

static otc_status fail_checksum(fctx *c, const char *file, const char *expected, const char *actual, const char *what)
{
    fail(c, OTC_E_CHECKSUM, file, "%s: %s", file, what);
    if (c->err) {
        snprintf(c->err->expected_sha256, sizeof c->err->expected_sha256, "%s", expected ? expected : "");
        snprintf(c->err->actual_sha256, sizeof c->err->actual_sha256, "%s", actual ? actual : "");
    }
    logf_(c, 2, "checksum failure: %s", file);
    return OTC_E_CHECKSUM;
}

static const char *env_get(const char *name)
{
    const char *v = getenv(name);
    return v && v[0] ? v : NULL;
}

/* An "on" value of a boolean environment variable (spec 4.2, CR D15): 1, true,
 * yes or on, without regard to case, after trimming spaces and tabs. */
static int env_on(const char *v)
{
    static const char *const ON[] = {"1", "true", "yes", "on", NULL};
    size_t n, i, k;
    if (!v) return 0;
    while (*v == ' ' || *v == '\t') v++;
    n = strlen(v);
    while (n && (v[n - 1] == ' ' || v[n - 1] == '\t')) n--;
    for (k = 0; ON[k]; k++) {
        if (strlen(ON[k]) != n) continue;
        for (i = 0; i < n; i++) {
            char ch = v[i];
            if (ch >= 'A' && ch <= 'Z') ch = (char)(ch + 32);
            if (ch != ON[k][i]) break;
        }
        if (i == n) return 1;
    }
    return 0;
}

static char *default_root(void)
{
    const char *v;
#ifdef _WIN32
    if ((v = env_get("LOCALAPPDATA")) != NULL) return otc__join(v, "/opentideconstants/Cache");
    if ((v = env_get("USERPROFILE")) != NULL) return otc__join(v, "/AppData/Local/opentideconstants/Cache");
    return NULL;
#elif defined(__APPLE__)
    if ((v = env_get("HOME")) != NULL) return otc__join(v, "/Library/Caches/opentideconstants");
    return NULL;
#else
    if ((v = env_get("XDG_CACHE_HOME")) != NULL) return otc__join(v, "/opentideconstants");
    if ((v = env_get("HOME")) != NULL) return otc__join(v, "/.cache/opentideconstants");
    return NULL;
#endif
}

/* 1 for an absolute http:// or https:// URL with a host. */
static int http_url(const char *u)
{
    size_t n = !strncmp(u, "http://", 7) ? 7 : !strncmp(u, "https://", 8) ? 8 : 0;
    return n && u[n] && u[n] != '/' && !strchr(u, ' ');
}

/* 1 when the environment names a home for the default cache root. */
static int default_root_env(void)
{
#ifdef _WIN32
    return env_get("LOCALAPPDATA") || env_get("USERPROFILE");
#elif defined(__APPLE__)
    return env_get("HOME") != NULL;
#else
    return env_get("XDG_CACHE_HOME") || env_get("HOME");
#endif
}

static otc_status ctx_init(fctx *c, const otc_fetch_options *o)
{
    const char *v;
    char *root;
    memset(c, 0, sizeof *c);
    init_once();
    otc_error_init(&c->own);
    c->err = &c->own;
    if (o && o->struct_size < sizeof *o) {
        /* the error field is at the same place in every layout that has it: the caller
         * still learns why (C56) */
        if (o->struct_size >= offsetof(otc_fetch_options, error) + sizeof o->error && otc__err_usable(o->error)) {
            c->err = o->error;
            otc_error_init(c->err);
        }
        return fail(c, OTC_E_INVALID_ARGUMENT, NULL, "otc_fetch_options: struct_size is too small");
    }
    c->o = o;
    if (o && otc__err_usable(o->error)) c->err = o->error;   /* else the detail stays in own: never written past */
    otc_error_init(c->err);
    if (!g_curl_ok) return fail(c, OTC_E_NETWORK, NULL, "curl_global_init failed");
    if (o && o->cache_dir) root = otc__strdup(o->cache_dir);
    else if ((v = env_get("OPENTIDECONSTANTS_CACHE_DIR")) != NULL) root = otc__strdup(v);
    else if (!(root = default_root()) && !default_root_env()) {
        return fail(c, OTC_E_CACHE, NULL, "no cache directory: set cache_dir or OPENTIDECONSTANTS_CACHE_DIR");
    }
    if (!root) return fail(c, OTC_E_NOMEM, NULL, "out of memory");
    c->base = path2(root, LAYOUT);
    free(root);
    v = (o && o->base_url) ? o->base_url : env_get("OPENTIDECONSTANTS_BASE_URL");
    if (!v) v = DEFAULT_BASE_URL;
    /* a base_url is a folder: without its trailing slash the last segment would be
     * dropped when a file name is resolved against it (spec 4.2, 5.2) */
    c->base_url = (v[0] && v[strlen(v) - 1] != '/') ? otc__join(v, "/") : otc__strdup(v);
    if (!c->base || !c->base_url) return fail(c, OTC_E_NOMEM, NULL, "out of memory");
    /* spec 4.2, 5.7 (CR D19): checked here, before any network access; never retried, never a
     * reason to fall back to the cache */
    if (!http_url(c->base_url))
        return fail(c, OTC_E_INVALID_ARGUMENT, NULL, "base_url must be an absolute http or https URL: %s", c->base_url);
    if (o && o->proxy && o->proxy[0] && !http_url(o->proxy))
        return fail(c, OTC_E_INVALID_ARGUMENT, NULL, "proxy must be an absolute http or https URL: %s", o->proxy);
    if (o && o->ca_file) {
        FILE *f = fs_kind(o->ca_file) == 2 ? fs_fopen(o->ca_file, "rb") : NULL;
        if (!f) return fail(c, OTC_E_IO, o->ca_file, "cannot read the ca_file %s", o->ca_file);
        fclose(f);
    }
    c->offline = (o && o->offline) || env_on(env_get("OPENTIDECONSTANTS_OFFLINE"));
    /* formats: OTC_FORMATS_DEFAULT is jsonl; 0 names no format (CR 4c) */
    c->formats = (!o || o->formats == OTC_FORMATS_DEFAULT) ? (unsigned)OTC_FORMAT_JSONL : o->formats;
    if (c->formats == 0)
        return fail(c, OTC_E_INVALID_ARGUMENT, NULL,
                    "formats is empty: name at least one OTC_FORMAT_* bit, or pass OTC_FORMATS_DEFAULT");
    if (c->formats & ~(unsigned)(OTC_FORMAT_JSON | OTC_FORMAT_JSON_GZ | OTC_FORMAT_JSONL))
        return fail(c, OTC_E_INVALID_ARGUMENT, NULL, "formats: only OTC_FORMAT_JSON, OTC_FORMAT_JSON_GZ and OTC_FORMAT_JSONL");
    /* timeout_s: OTC_TIMEOUT_DEFAULT is the defaults; otherwise a number of seconds above 0 and at most
     * TIMEOUT_MAX_S, so that the millisecond options of libcurl stay in a long (CR 4c, C59) */
    if (o && o->timeout_s != OTC_TIMEOUT_DEFAULT && !(o->timeout_s > 0 && o->timeout_s <= TIMEOUT_MAX_S))
        return fail(c, OTC_E_INVALID_ARGUMENT, NULL,
                    "timeout_s must be a number of seconds above 0 and at most %g, or OTC_TIMEOUT_DEFAULT for the defaults",
                    TIMEOUT_MAX_S);
    c->connect_s = (o && o->timeout_s != OTC_TIMEOUT_DEFAULT) ? o->timeout_s : CONNECT_TIMEOUT_S;
    c->read_s = (o && o->timeout_s != OTC_TIMEOUT_DEFAULT) ? o->timeout_s : READ_TIMEOUT_S;
    c->raise = o && o->on_network_error == OTC_ON_NETWORK_ERROR_RAISE;
    return OTC_OK;
}

static void ctx_free(fctx *c)
{
    free(c->base);
    free(c->base_url);
}

/* ------------------------------------------------------------------ datestamps */

/* ^[0-9]{8}(\.[2-9]|\.[1-9][0-9]{1,8})?$ (spec 4.2, CR D18): the counter has at
 * most 9 digits, so a datestamp has at most DS_MAX characters, every cache
 * file name fits NAME_CAP, and ds_cmp's strtoul never saturates. */
#define DS_MAX 18
#define NAME_CAP (4 + DS_MAX + sizeof ".meta.json")   /* "OTC_" + D + the longest suffix */
static int valid_datestamp(const char *s)
{
    return s && otc__valid_datestamp(s, strlen(s));
}

/* the date, then the counter; no counter = counter 1 */
static int ds_cmp(const char *a, const char *b)
{
    int c = strncmp(a, b, 8);
    unsigned long ca, cb;
    if (c) return c;
    ca = a[8] == '.' ? strtoul(a + 9, NULL, 10) : 1;
    cb = b[8] == '.' ? strtoul(b + 9, NULL, 10) : 1;
    return ca < cb ? -1 : ca > cb;
}

static int ds_cmp_desc(const void *x, const void *y)
{
    return ds_cmp(*(const char *const *)y, *(const char *const *)x);
}

/* The major of "MAJOR.MINOR", or -1 when fv is not a valid version (spec 7.4, CR D9). */
static int format_major(const char *fv)
{
    long m;
    if (!otc__version_valid(fv)) return -1;
    m = strtol(fv, NULL, 10);
    return m < 1000000 ? (int)m : -1;
}

/* --------------------------------------------------------------------- URLs */

/* RFC 3986 reference resolution, enough for the pointer's file urls. */
static char *url_resolve(const char *base, const char *ref)
{
    const char *p, *auth, *path_start, *q, *last;
    size_t i;
    for (p = ref; *p && *p != '/' && *p != '?' && *p != '#'; p++) {
        if (*p == ':') return otc__strdup(ref);   /* has a scheme */
    }
    auth = strstr(base, "://");
    if (!auth) return otc__join(base, ref);
    path_start = strchr(auth + 3, '/');
    if (!path_start) path_start = base + strlen(base);
    if (ref[0] == '/' && ref[1] == '/') {
        char *s = otc__strndup(base, (size_t)(auth - base) + 1), *r;
        if (!s) return NULL;
        r = otc__join(s, ref);
        free(s);
        return r;
    }
    if (ref[0] == '/') {
        char *s = otc__strndup(base, (size_t)(path_start - base)), *r;
        if (!s) return NULL;
        r = otc__join(s, ref);
        free(s);
        return r;
    }
    q = path_start;
    for (i = 0; q[i] && q[i] != '?' && q[i] != '#'; i++) {}
    last = NULL;
    for (p = path_start; p < path_start + i; p++)
        if (*p == '/') last = p;
    while (ref[0] == '.' && ref[1] == '/') ref += 2;
    {
        char *s = last ? otc__strndup(base, (size_t)(last - base) + 1) : otc__join(base, "/"), *r;
        if (!s) return NULL;
        r = otc__join(s, ref);
        free(s);
        return r;
    }
}

/* ---------------------------------------------------------------------- HTTP */

typedef struct http_resp {
    long           status;
    char           etag[256];
    double         retry_after;     /* -1: none */
    unsigned char *body;            /* memory mode */
    size_t         len, cap;
    FILE          *sink;            /* file mode */
    struct Sha_256 sha;
    uint8_t        hash[SIZE_OF_SHA_256_HASH];
    uint64_t       size;
    int            write_error;
    char           hex[65];
} http_resp;

static void hex_of(const uint8_t *h, char out[65])
{
    static const char digits[] = "0123456789abcdef";
    size_t i;
    for (i = 0; i < SIZE_OF_SHA_256_HASH; i++) {
        out[2 * i] = digits[h[i] >> 4];
        out[2 * i + 1] = digits[h[i] & 15];
    }
    out[64] = '\0';
}

static size_t on_body(char *data, size_t sz, size_t nm, void *user)
{
    http_resp *r = (http_resp *)user;
    size_t n = sz * nm;
    sha_256_write(&r->sha, data, n);
    r->size += n;
    if (r->sink) {
        if (fwrite(data, 1, n, r->sink) != n) { r->write_error = 1; return 0; }
    } else {
        if (r->len + n + 1 > r->cap) {
            size_t nc = r->cap ? r->cap : 4096;
            unsigned char *nb;
            while (nc < r->len + n + 1) nc *= 2;
            nb = (unsigned char *)realloc(r->body, nc);
            if (!nb) { r->write_error = 2; return 0; }
            r->body = nb;
            r->cap = nc;
        }
        memcpy(r->body + r->len, data, n);
        r->len += n;
        r->body[r->len] = '\0';
    }
    return n;
}

static int hdr_is(const char *line, size_t n, const char *name)
{
    size_t k = strlen(name), i;
    if (n <= k || line[k] != ':') return 0;
    for (i = 0; i < k; i++) {
        char a = line[i], b = name[i];
        if (a >= 'A' && a <= 'Z') a = (char)(a + 32);
        if (a != b) return 0;
    }
    return 1;
}

static size_t on_header(char *line, size_t sz, size_t nm, void *user)
{
    http_resp *r = (http_resp *)user;
    size_t n = sz * nm, k;
    const char *v;
    size_t vl;
    if (n >= 5 && !strncmp(line, "HTTP/", 5)) {   /* a new response (redirect, 100-continue) */
        r->etag[0] = '\0';
        r->retry_after = -1;
        return n;
    }
    if (hdr_is(line, n, "etag")) k = 4;
    else if (hdr_is(line, n, "retry-after")) k = 11;
    else return n;
    v = line + k + 1;
    vl = n - k - 1;
    while (vl && (*v == ' ' || *v == '\t')) { v++; vl--; }
    while (vl && (v[vl - 1] == '\r' || v[vl - 1] == '\n' || v[vl - 1] == ' ')) vl--;
    if (k == 4) {
        if (vl >= sizeof r->etag) vl = sizeof r->etag - 1;
        memcpy(r->etag, v, vl);
        r->etag[vl] = '\0';
    } else {
        char buf[32];
        char *end;
        double d;
        if (vl >= sizeof buf) vl = sizeof buf - 1;
        memcpy(buf, v, vl);
        buf[vl] = '\0';
        d = strtod(buf, &end);
        if (end != buf && *end == '\0' && d >= 0) {
            r->retry_after = d;
        } else {   /* Retry-After may also be an HTTP-date (spec 5.7) */
            int64_t at = otc__http_date(buf), now = (int64_t)time(NULL);
            if (at >= 0) r->retry_after = at > now ? (double)(at - now) : 0.0;
        }
    }
    return n;
}

enum { GET_OK = 0, GET_NOT_MODIFIED, GET_NOT_FOUND };

/* A libcurl failure that another attempt may cure (spec 5.7: "connection
 * errors"). A refused protocol, a bad URL, too many redirects or a TLS
 * certificate failure stay the same, so they are not retried. */
static int transient(CURLcode rc)
{
    switch (rc) {
    case CURLE_COULDNT_RESOLVE_PROXY:
    case CURLE_COULDNT_RESOLVE_HOST:
    case CURLE_COULDNT_CONNECT:
    case CURLE_PARTIAL_FILE:
    case CURLE_OPERATION_TIMEDOUT:
    case CURLE_SSL_CONNECT_ERROR:
    case CURLE_GOT_NOTHING:
    case CURLE_SEND_ERROR:
    case CURLE_RECV_ERROR:
    case CURLE_HTTP2:
    case CURLE_HTTP2_STREAM:
        return 1;
    default:
        return 0;
    }
}

/*
 * GET url with the retries of spec 5.7 (3 attempts on connection errors, 5xx
 * and 429; waits of 1 s and 2 s, or Retry-After up to 60 s). 304 and 404 are
 * results, never retried. With sink_path the decoded body streams into that
 * file (fsynced); otherwise it is kept in r->body. r->hex and r->size
 * describe the decoded body.
 */
/* Appends a header line; 0 when libcurl could not (out of memory): the list so far is
 * kept in *list, and the request must not go out without the header. */
static int add_header(struct curl_slist **list, const char *line)
{
    struct curl_slist *n = curl_slist_append(*list, line);
    if (!n) return 0;
    *list = n;
    return 1;
}

static otc_status http_get(fctx *c, const char *url, const char *if_none_match, int accept_gzip,
                           const char *sink_path, http_resp *r, int *result)
{
    static const double backoff[2] = {1.0, 2.0};
    char ua[512], errbuf[CURL_ERROR_SIZE], inm[300];
    int attempt, https = !strncmp(url, "https://", 8);
    long last_status = 0;
    char last_msg[512];
    /* The proxy option wins. Without it libcurl reads the environment itself (spec
     * 5.7, CR D7): only lower-case http_proxy for http (httpoxy: in CGI a client's
     * Proxy: header arrives as HTTP_PROXY), https_proxy / HTTPS_PROXY, ALL_PROXY and
     * NO_PROXY. So neither CURLOPT_PROXY nor CURLOPT_NOPROXY is set then. */
    const char *proxy = (c->o && c->o->proxy) ? c->o->proxy : NULL;
    const char *ca = (c->o && c->o->ca_file) ? c->o->ca_file : env_get("SSL_CERT_FILE");
    *result = GET_OK;
    if (strncmp(url, "http://", 7) != 0 && !https) {
        fail(c, OTC_E_NETWORK, url, "not an http(s) URL: %s", url);
        return OTC_E_NETWORK;
    }
    if (c->o && c->o->user_agent && c->o->user_agent[0])
        snprintf(ua, sizeof ua, "%s %s", USER_AGENT, c->o->user_agent);
    else
        snprintf(ua, sizeof ua, "%s", USER_AGENT);
    last_msg[0] = '\0';
    for (attempt = 0; attempt < ATTEMPTS; attempt++) {
        CURL *h;
        CURLcode rc;
        struct curl_slist *hdrs = NULL;
        int retry = 0, bad_opt, no_mem = 0;
        free(r->body);
        memset(r, 0, sizeof *r);
        r->retry_after = -1;
        sha_256_init(&r->sha, r->hash);
        if (sink_path) {
            r->sink = fs_fopen(sink_path, "wb");
            if (!r->sink) return fail(c, OTC_E_CACHE, sink_path, "cannot write %s", sink_path);
        }
        h = curl_easy_init();
        if (!h) {
            if (r->sink) fclose(r->sink);
            r->sink = NULL;
            return fail(c, OTC_E_NOMEM, url, "curl_easy_init failed");
        }
        errbuf[0] = '\0';
        bad_opt = curl_easy_setopt(h, CURLOPT_URL, url) != CURLE_OK;
        curl_easy_setopt(h, CURLOPT_USERAGENT, ua);
        curl_easy_setopt(h, CURLOPT_NOSIGNAL, 1L);
        /* redirects (spec 5.7, CR D1): at most 5, only http and https, and never from
         * https to http */
        bad_opt |= curl_easy_setopt(h, CURLOPT_FOLLOWLOCATION, 1L) != CURLE_OK;
        bad_opt |= curl_easy_setopt(h, CURLOPT_MAXREDIRS, 5L) != CURLE_OK;
#if LIBCURL_VERSION_NUM >= 0x075500
        bad_opt |= curl_easy_setopt(h, CURLOPT_PROTOCOLS_STR, "http,https") != CURLE_OK;
        bad_opt |= curl_easy_setopt(h, CURLOPT_REDIR_PROTOCOLS_STR, https ? "https" : "http,https") != CURLE_OK;
#else
        bad_opt |= curl_easy_setopt(h, CURLOPT_PROTOCOLS, (long)(CURLPROTO_HTTP | CURLPROTO_HTTPS)) != CURLE_OK;
        bad_opt |= curl_easy_setopt(h, CURLOPT_REDIR_PROTOCOLS,
                                    https ? (long)CURLPROTO_HTTPS : (long)(CURLPROTO_HTTP | CURLPROTO_HTTPS)) != CURLE_OK;
#endif
        curl_easy_setopt(h, CURLOPT_CONNECTTIMEOUT_MS, (long)(c->connect_s * 1000.0));
        curl_easy_setopt(h, CURLOPT_LOW_SPEED_LIMIT, 1L);
        curl_easy_setopt(h, CURLOPT_LOW_SPEED_TIME, (long)(c->read_s + 0.999));
        curl_easy_setopt(h, CURLOPT_ERRORBUFFER, errbuf);
        curl_easy_setopt(h, CURLOPT_WRITEFUNCTION, on_body);
        curl_easy_setopt(h, CURLOPT_WRITEDATA, r);
        curl_easy_setopt(h, CURLOPT_HEADERFUNCTION, on_header);
        curl_easy_setopt(h, CURLOPT_HEADERDATA, r);
        if (accept_gzip) curl_easy_setopt(h, CURLOPT_ACCEPT_ENCODING, "gzip");
        else no_mem |= !add_header(&hdrs, "Accept-Encoding: identity");
        if (if_none_match && if_none_match[0]) {
            snprintf(inm, sizeof inm, "If-None-Match: %s", if_none_match);
            no_mem |= !add_header(&hdrs, inm);
        }
        if (hdrs) curl_easy_setopt(h, CURLOPT_HTTPHEADER, hdrs);
        if (proxy) {
            bad_opt |= curl_easy_setopt(h, CURLOPT_PROXY, proxy) != CURLE_OK;
            bad_opt |= curl_easy_setopt(h, CURLOPT_NOPROXY, "") != CURLE_OK;
        }
        if (ca) bad_opt |= curl_easy_setopt(h, CURLOPT_CAINFO, ca) != CURLE_OK;
        if (bad_opt || no_mem) {   /* a header, limit or URL that libcurl did not take: no request without it */
            curl_easy_cleanup(h);
            curl_slist_free_all(hdrs);
            if (r->sink) fclose(r->sink);
            r->sink = NULL;
            if (no_mem) return fail(c, OTC_E_NOMEM, url, "out of memory for the request headers (%s)", url);
            return fail(c, OTC_E_NETWORK, url, "libcurl refused an option the request needs (%s)", url);
        }
        rc = curl_easy_perform(h);
        curl_easy_getinfo(h, CURLINFO_RESPONSE_CODE, &r->status);
        curl_easy_cleanup(h);
        curl_slist_free_all(hdrs);
        sha_256_close(&r->sha);
        hex_of(r->hash, r->hex);
        if (r->sink) {
            int bad = rc == CURLE_OK && r->status == 200 && fs_fsync(r->sink) != 0;
            if (fclose(r->sink) != 0) bad = 1;
            r->sink = NULL;
            if (bad) return fail(c, OTC_E_CACHE, sink_path, "cannot write %s", sink_path);
        }
        if (r->write_error == 1) return fail(c, OTC_E_CACHE, sink_path, "cannot write %s", sink_path);
        if (r->write_error == 2) return fail(c, OTC_E_NOMEM, url, "out of memory");
        if (rc != CURLE_OK) {
            snprintf(last_msg, sizeof last_msg, "%s for %s: %s", curl_easy_strerror(rc), url,
                     errbuf[0] ? errbuf : curl_easy_strerror(rc));
            last_status = 0;
            if (!transient(rc)) {   /* spec 5.7: only connection errors are retried */
                fail(c, OTC_E_NETWORK, url, "%s", last_msg);
                return OTC_E_NETWORK;
            }
            retry = 1;
        } else if (r->status == 200) {
            logf_(c, 0, "GET %s -> 200", url);
            return OTC_OK;
        } else if (r->status == 304) {
            logf_(c, 0, "GET %s -> 304", url);
            *result = GET_NOT_MODIFIED;
            return OTC_OK;
        } else if (r->status == 404) {
            logf_(c, 0, "GET %s -> 404", url);
            *result = GET_NOT_FOUND;
            return OTC_OK;
        } else if (r->status == 429 || r->status >= 500) {
            snprintf(last_msg, sizeof last_msg, "HTTP %ld for %s", r->status, url);
            last_status = r->status;
            retry = 1;
        } else {
            fail(c, OTC_E_NETWORK, url, "HTTP %ld for %s", r->status, url);
            if (c->err) c->err->http_status = (int)r->status;
            return OTC_E_NETWORK;
        }
        if (retry && attempt + 1 < ATTEMPTS) {
            double wait = backoff[attempt];
            if (r->retry_after >= 0) {
                double ra = r->retry_after > RETRY_AFTER_MAX_S ? RETRY_AFTER_MAX_S : r->retry_after;
                if (ra > wait) wait = ra;
            }
            logf_(c, 0, "GET %s failed (%s); retry in %.1f s", url, last_msg, wait);
            sleep_ms((long)(wait * 1000.0));
        }
    }
    fail(c, OTC_E_NETWORK, url, "%s", last_msg);
    if (c->err) c->err->http_status = (int)last_status;
    return OTC_E_NETWORK;
}

static void resp_free(http_resp *r)
{
    free(r->body);
    r->body = NULL;
}

/* -------------------------------------------------------------- atomic writes */

/* Writes data to <dir>/.tmp-*, fsyncs it and renames it to path. */
static otc_status write_atomic(fctx *c, const char *dir, const char *path, const void *data, size_t len)
{
    char *tmp = tmp_path(dir);
    FILE *f;
    int bad;
    if (!tmp) return fail(c, OTC_E_NOMEM, path, "out of memory");
    f = fs_fopen(tmp, "wb");
    if (!f) { free(tmp); return fail(c, OTC_E_CACHE, path, "cannot write %s", path); }
    bad = (len && fwrite(data, 1, len, f) != len) || fs_fsync(f) != 0;
    if (fclose(f) != 0) bad = 1;
    if (bad || fs_rename(tmp, path) != 0) {
        fs_unlink(tmp);
        free(tmp);
        return fail(c, OTC_E_CACHE, path, "cannot write %s", path);
    }
    free(tmp);
    return OTC_OK;
}

/* Writes data to <dir>/.tmp-* (fsynced) and returns that path; the caller renames it. */
static otc_status write_tmp(fctx *c, const char *dir, const void *data, size_t len, char **tmp_out)
{
    char *tmp = tmp_path(dir);
    FILE *f;
    int bad;
    *tmp_out = NULL;
    if (!tmp) return fail(c, OTC_E_NOMEM, dir, "out of memory");
    f = fs_fopen(tmp, "wb");
    if (!f) { free(tmp); return fail(c, OTC_E_IO, dir, "cannot write into %s", dir); }
    bad = (len && fwrite(data, 1, len, f) != len) || fs_fsync(f) != 0;
    if (fclose(f) != 0) bad = 1;
    if (bad) {
        fs_unlink(tmp);
        free(tmp);
        return fail(c, OTC_E_IO, dir, "cannot write into %s", dir);
    }
    *tmp_out = tmp;
    return OTC_OK;
}

/* Copies src to <dir>/.tmp-* (fsynced); returns the tmp path and its SHA-256. */
static otc_status copy_to_tmp(fctx *c, const char *src, const char *dir, char **tmp_out, char hex[65])
{
    FILE *in = fs_fopen(src, "rb"), *out;
    char *tmp;
    unsigned char *buf;
    struct Sha_256 sha;
    uint8_t hash[SIZE_OF_SHA_256_HASH];
    size_t n;
    int bad = 0;
    *tmp_out = NULL;
    if (!in) return fail(c, OTC_E_IO, src, "cannot read %s", src);
    tmp = tmp_path(dir);
    buf = (unsigned char *)malloc(65536);
    out = tmp ? fs_fopen(tmp, "wb") : NULL;
    if (!tmp || !buf || !out) {
        int nomem = !tmp || !buf;   /* a path or buffer that could not be allocated is not an I/O error */
        fclose(in);
        if (out) fclose(out);
        free(buf);
        free(tmp);
        if (nomem) return fail(c, OTC_E_NOMEM, dir, "out of memory");
        return fail(c, OTC_E_IO, dir, "cannot write into %s", dir);
    }
    sha_256_init(&sha, hash);
    while ((n = fread(buf, 1, 65536, in)) > 0) {
        sha_256_write(&sha, buf, n);
        if (fwrite(buf, 1, n, out) != n) { bad = 1; break; }
    }
    if (ferror(in)) bad = 1;
    sha_256_close(&sha);
    hex_of(hash, hex);
    fclose(in);
    if (fs_fsync(out) != 0) bad = 1;
    if (fclose(out) != 0) bad = 1;
    free(buf);
    if (bad) {
        fs_unlink(tmp);
        free(tmp);
        return fail(c, OTC_E_IO, dir, "cannot write into %s", dir);
    }
    *tmp_out = tmp;
    return OTC_OK;
}

/* ------------------------------------------------------------------- the lock */

typedef int (*done_fn)(fctx *c, const char *ds);

/* A random token of 128 bits as 32 hex digits (spec 5.4, CR D3). */
static void lock_token(char out[33])
{
    static const char digits[] = "0123456789abcdef";
    unsigned char b[16];
    size_t i;
    int ok = 0;
#ifdef _WIN32
    for (i = 0; i < 16; i += 4) {
        unsigned int r;
        if (rand_s(&r) != 0) break;
        memcpy(b + i, &r, 4);
    }
    ok = i >= 16;
#else
    FILE *f = fopen("/dev/urandom", "rb");
    if (f) {
        ok = fread(b, 1, sizeof b, f) == sizeof b;
        fclose(f);
    }
#endif
    if (!ok) {   /* no OS randomness: the tmp-name mixer (unique per process and call) */
        char *t = tmp_path("x");
        size_t n = t ? strlen(t) : 0;
        for (i = 0; i < 16; i++) b[i] = (unsigned char)(n > i ? t[n - 1 - i] : (unsigned char)(i * 37 + get_pid()));
        free(t);
    }
    for (i = 0; i < 16; i++) {
        out[2 * i] = digits[b[i] >> 4];
        out[2 * i + 1] = digits[b[i] & 15];
    }
    out[32] = '\0';
}

/* Writes <lock>/owner.json with a fresh token (spec 5.4). A failure is logged:
 * the lock still works, but it then cannot be released (lock_release finds no
 * token), so it goes stale. */
static void lock_write_owner(fctx *c, const char *lock, char token[33])
{
    char *owner = path2(lock, "owner.json"), *txt = NULL;
    char host[256] = "", when[32];
    time_t now = time(NULL);
    struct tm tmv;
    cJSON *o = cJSON_CreateObject();
    FILE *f;
    lock_token(token);
#ifdef _WIN32
    {
        DWORD hl = (DWORD)sizeof host;
        if (!GetComputerNameA(host, &hl)) host[0] = '\0';
    }
    gmtime_s(&tmv, &now);
#else
    if (gethostname(host, sizeof host - 1) != 0) host[0] = '\0';
    host[sizeof host - 1] = '\0';
    gmtime_r(&now, &tmv);
#endif
    strftime(when, sizeof when, "%Y-%m-%dT%H:%M:%SZ", &tmv);
    if (o) {
        cJSON_AddNumberToObject(o, "pid", (double)get_pid());
        cJSON_AddStringToObject(o, "host", host);
        cJSON_AddStringToObject(o, "sdk", SDK_ID);
        cJSON_AddStringToObject(o, "started_at", when);
        cJSON_AddStringToObject(o, "token", token);
        txt = cJSON_PrintUnformatted(o);
    }
    f = (owner && txt) ? fs_fopen(owner, "wb") : NULL;
    if (f) {
        int bad = fputs(txt, f) < 0;
        if (fclose(f) != 0) bad = 1;
        if (bad) logf_(c, 2, "cannot write %s", owner);
    } else {
        logf_(c, 2, "cannot write %s", owner ? owner : lock);
    }
    cJSON_free(txt);
    cJSON_Delete(o);
    free(owner);
}

static char *slurp(const char *path);

/* Seconds since 1970 of a proleptic Gregorian UTC date and time (no timegm on Windows). */
static long long utc_seconds(int y, int mo, int d, int h, int mi, int sec)
{
    long long era, yoe, doy, doe;
    y -= mo <= 2;
    era = (y >= 0 ? y : y - 399) / 400;
    yoe = y - era * 400;
    doy = (153 * (mo + (mo > 2 ? -3 : 9)) + 2) / 5 + d - 1;
    doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    return (era * 146097 + doe - 719468) * 86400 + h * 3600 + mi * 60 + sec;
}

/* owner.json started_at, "YYYY-MM-DDTHH:MM:SS[.frac](Z|+00:00)", as seconds since 1970; 0 when it is not one */
static int parse_started_at(const char *s, long long *out)
{
    int v[6], i, k = 0;
    static const int width[6] = {4, 2, 2, 2, 2, 2};
    static const char sep[6] = {'-', '-', 'T', ':', ':', '\0'};
    if (!s) return 0;
    for (i = 0; i < 6; i++) {
        int j;
        v[i] = 0;
        for (j = 0; j < width[i]; j++, k++) {
            if (s[k] < '0' || s[k] > '9') return 0;
            v[i] = v[i] * 10 + (s[k] - '0');
        }
        if (sep[i] && s[k++] != sep[i]) return 0;
    }
    if (s[k] == '.') {
        if (s[++k] < '0' || s[k] > '9') return 0;
        while (s[k] >= '0' && s[k] <= '9') k++;
    }
    if (strcmp(s + k, "Z") != 0 && strcmp(s + k, "+00:00") != 0) return 0;
    if (v[1] < 1 || v[1] > 12 || v[2] < 1 || v[2] > 31 || v[3] > 23 || v[4] > 59 || v[5] > 60) return 0;
    *out = utc_seconds(v[0], v[1], v[2], v[3], v[4], v[5]);
    return 1;
}

/* The mtime of path, seconds since 1970; 0 when it cannot be read. */
static int fs_mtime(const char *path, long long *out)
{
#ifdef _WIN32
    struct _stat64 sb;
    wchar_t *w = widen(path);
    int r = w ? _wstat64(w, &sb) : -1;
    free(w);
    if (r != 0) return 0;
#else
    struct stat sb;
    if (stat(path, &sb) != 0) return 0;
#endif
    *out = (long long)sb.st_mtime;
    return 1;
}

/* A lock is stale when it is at least LOCK_STALE_AGE_S old (spec 5.4, CR2 DR3). Its
 * age comes from owner.json started_at, or from the mtime of the lock directory when
 * owner.json is missing or cannot be read. A lock whose age cannot be read (it is
 * gone, or memory ran out) is never stale. */
static int lock_is_stale(const char *lock)
{
    char *owner = path2(lock, "owner.json"), *t = owner ? slurp(owner) : NULL;
    cJSON *o = t ? otc__json_parse(t, strlen(t)) : NULL;
    long long started = 0;
    int known = parse_started_at(otc__jstr(o, "started_at"), &started);
    cJSON_Delete(o);
    free(t);
    free(owner);
    if (!known && !fs_mtime(lock, &started)) return 0;
    return (long long)time(NULL) - started >= LOCK_STALE_AGE_S;
}

/* One attempt at <dir>/.lock, without waiting: *held = 1 when this call took it. A lock
 * at least 120 s old is stale: it is removed and taken (spec 5.4 non-blocking takes,
 * CR2 DR3); one that cannot be removed is OTC_E_CACHE. */
static otc_status lock_try(fctx *c, const char *dir, int *held, char token[33])
{
    char *lock = path2(dir, ".lock");
    int m, attempt;
    *held = 0;
    if (!lock) return fail(c, OTC_E_NOMEM, dir, "out of memory");
    for (attempt = 0;; attempt++) {
        int rm;
        m = fs_mkdir(lock);
        /* once only: a process that takes it after the removal holds a young lock */
        if (m != 1 || attempt > 0 || !lock_is_stale(lock)) break;
        logf_(c, 2, "removing the stale lock %s", lock);
        if ((rm = fs_rm_rf(lock)) != 0) {
            otc_status st = rm == -2 ? fail(c, OTC_E_NOMEM, lock, "out of memory while removing %s", lock)
                                     : fail(c, OTC_E_CACHE, lock, "cannot remove the stale lock %s", lock);
            free(lock);
            return st;
        }
    }
    if (m == 0) {
        *held = 1;
        lock_write_owner(c, lock, token);
    }
    free(lock);
    return m < 0 ? fail(c, OTC_E_CACHE, dir, "cannot create the lock in %s", dir) : OTC_OK;
}

/* Takes <dir>/.lock (spec 5.4). *held = 0 when done() became true while waiting.
 * token gets the random token written to owner.json; lock_release needs it. */
static otc_status lock_take(fctx *c, const char *dir, const char *ds, done_fn done, int *held, char token[33])
{
    char *lock = path2(dir, ".lock");
    long waited = 0;
    int failed_removals = 0;
    *held = 0;
    if (!lock) return fail(c, OTC_E_NOMEM, dir, "out of memory");
    for (;;) {
        int m = fs_mkdir(lock);
        if (m == 0) { *held = 1; break; }
        if (m < 0) {
            otc_status st = fail(c, OTC_E_CACHE, lock, "cannot create the lock %s", lock);
            free(lock);
            return st;
        }
        if (done && done(c, ds) > 0) break;   /* -1 (out of memory) is not done */
        /* stale only when this waiter has waited and the lock itself is old; the age is
         * read just before the removal (spec 5.4, CR2 DR3) */
        if (waited >= LOCK_STALE_MS && lock_is_stale(lock)) {
            /* spec 5.4 (CR D3): a stale lock that cannot be removed 3 times is a cache error */
            logf_(c, 2, "removing the stale lock %s", lock);
            if (fs_rm_rf(lock) == 0) {
                waited = 0;   /* the wait starts again: a peer may take the lock first (R2-010) */
                continue;
            }
            if (++failed_removals >= 3) {
                otc_status st = fail(c, OTC_E_CACHE, lock, "cannot remove the stale lock %s", lock);
                free(lock);
                return st;
            }
        }
        sleep_ms(LOCK_POLL_MS);
        waited += LOCK_POLL_MS;
    }
    if (*held) lock_write_owner(c, lock, token);
    free(lock);
    return OTC_OK;
}

/* Releases <dir>/.lock only when its owner.json carries this process's token:
 * a lock that another process took over as stale is left alone (spec 5.4, CR D3). */
static void lock_release(fctx *c, const char *dir, const char *token)
{
    char *lock = path2(dir, ".lock"), *owner = lock ? path2(lock, "owner.json") : NULL, *t = owner ? slurp(owner) : NULL;
    cJSON *o = t ? otc__json_parse(t, strlen(t)) : NULL;
    if (owner && !otc__strcmp_null(otc__jstr(o, "token"), token)) {
        fs_unlink(owner);
        fs_rmdir(lock);
    } else {
        logf_(c, 1, "the lock %s now belongs to another process; it is left alone", lock ? lock : dir);
    }
    cJSON_Delete(o);
    free(t);
    free(owner);
    free(lock);
}

/* --------------------------------------------------------------- release info */

static int fi_cmp(const void *a, const void *b)
{
    return strcmp(((const otc_file_info *)a)->name, ((const otc_file_info *)b)->name);
}

static void free_file_infos(otc_file_info *f, size_t n)
{
    size_t i;
    if (!f) return;
    for (i = 0; i < n; i++) {
        free(f[i].name);
        free(f[i].url);
        free(f[i].sha256);
    }
    free(f);
}

/* A pointer or index entry -> ReleaseInfo (files sorted by name, urls absolute). */
static otc_status info_from_entry(fctx *c, const cJSON *e, const char *doc_url, otc_release_info **out)
{
    otc_release_info *ri;
    const cJSON *files = otc__jget(e, "files"), *f;
    const char *ds = otc__jstr(e, "datestamp"), *fv = otc__jstr(e, "format_version");
    const char *mrv = otc__jstr(e, "min_reader_version"), *cdoi = otc__jstr(e, "concept_doi");
    const char *zdoi = otc__jstr(e, "zenodo_version_doi"), *csha = otc__jstr(e, "content_sha256");
    size_t n = 0;
    *out = NULL;
    if (!cJSON_IsObject(e) || !ds || !valid_datestamp(ds) || (files && !cJSON_IsArray(files)))
        return fail(c, OTC_E_INVALID_RELEASE, doc_url, "%s: a release entry without a valid datestamp or files", doc_url);
    if ((otc__jget(e, "format_version") && !otc__version_valid(fv))   /* spec 7.4 (CR D9) */
        || (otc__jget(e, "min_reader_version") && !otc__version_valid(mrv)))
        return fail(c, OTC_E_INVALID_RELEASE, doc_url,
                    "%s: release %s has a format_version or min_reader_version that is not MAJOR.MINOR", doc_url, ds);
    ri = (otc_release_info *)calloc(1, sizeof *ri);
    if (!ri) return fail(c, OTC_E_NOMEM, NULL, "out of memory");
    ri->datestamp = otc__strdup(ds);
    ri->format_version = fv ? otc__strdup(fv) : NULL;
    ri->min_reader_version = mrv ? otc__strdup(mrv) : NULL;
    ri->concept_doi = cdoi ? otc__strdup(cdoi) : NULL;
    ri->zenodo_version_doi = zdoi ? otc__strdup(zdoi) : NULL;
    ri->content_sha256 = csha ? otc__strdup(csha) : NULL;
    ri->files = (otc_file_info *)calloc((size_t)cJSON_GetArraySize(files) + 1, sizeof *ri->files);
    if (!ri->datestamp || (fv && !ri->format_version) || (mrv && !ri->min_reader_version) || (cdoi && !ri->concept_doi)
        || (zdoi && !ri->zenodo_version_doi) || (csha && !ri->content_sha256) || !ri->files) {
        otc_release_info_free(ri);
        return fail(c, OTC_E_NOMEM, NULL, "out of memory");
    }
    cJSON_ArrayForEach(f, files) {
        const char *name = otc__jstr(f, "name"), *u = otc__jstr(f, "url"), *sha = otc__jstr(f, "sha256");
        otc_file_info *fi = &ri->files[n];
        if (!name) {
            ri->n_files = n;
            otc_release_info_free(ri);
            return fail(c, OTC_E_INVALID_RELEASE, doc_url, "%s: a file entry without a name", doc_url);
        }
        if (!sha || otc__jint(f, "size") < 0) {   /* as the schema requires (CR2 DR12) */
            ri->n_files = n;
            otc_release_info_free(ri);
            return fail(c, OTC_E_INVALID_RELEASE, doc_url,
                        "%s: the entry for %s of %s needs a string sha256 and an integer size of 0 or more", doc_url, name, ds);
        }
        fi->name = otc__strdup(name);
        fi->url = url_resolve(doc_url, u ? u : name);
        fi->sha256 = sha ? otc__strdup(sha) : NULL;
        fi->size = otc__jint(f, "size");   /* a whole number in range, else unknown (-1); never a bad cast */
        n++;
        if (!fi->name || !fi->url || (sha && !fi->sha256)) {
            ri->n_files = n;
            otc_release_info_free(ri);
            return fail(c, OTC_E_NOMEM, NULL, "out of memory");
        }
        {
            char *p;
            if (fi->sha256)
                for (p = fi->sha256; *p; p++)
                    if (*p >= 'A' && *p <= 'F') *p = (char)(*p + 32);
        }
    }
    ri->n_files = n;
    if (n > 1) qsort(ri->files, n, sizeof *ri->files, fi_cmp);
    *out = ri;
    return OTC_OK;
}

static const otc_file_info *info_file(const otc_release_info *ri, const char *name)
{
    size_t i;
    if (!ri) return NULL;
    for (i = 0; i < ri->n_files; i++)
        if (!strcmp(ri->files[i].name, name)) return &ri->files[i];
    return NULL;
}

/* -------------------------------------------------------- pointer and index */

static char *pointer_dir(fctx *c) { return path2(c->base, "pointer"); }

/* Reads a whole file; NULL if it is missing (or cannot be read). */
static char *slurp(const char *path)
{
    char *t = NULL;
    if (fs_kind(path) != 2) return NULL;
    if (otc__read_all(path, &t, NULL) != OTC_OK) return NULL;
    return t;
}

/* The same with a status: OTC_OK with *out NULL when the file is missing,
 * OTC_E_NOMEM, or OTC_E_IO when it is there but cannot be read. */
static otc_status slurp_st(const char *path, char **out)
{
    *out = NULL;
    if (fs_kind(path) != 2) return OTC_OK;
    return otc__read_all(path, out, NULL);
}

/* The shape of a pointer (an object with a datestamp and a files array) or
 * of OTC_index.json (an object with a releases array). A wrong value inside a
 * body of the right shape is OTC_E_INVALID_RELEASE later (CR2 DR13). */
static int shape_ok(const char *name, const cJSON *doc)
{
    if (!cJSON_IsObject(doc)) return 0;
    if (!strcmp(name, "OTC_index.json")) return cJSON_IsArray(otc__jget(doc, "releases"));
    return otc__jget(doc, "datestamp") != NULL && cJSON_IsArray(otc__jget(doc, "files"));
}

/*
 * A file that changes (pointer, index): GET with If-None-Match from the
 * stored ETag; 200 stores the body and the ETag atomically. *doc = NULL and
 * OTC_OK on a 404.
 */
static otc_status get_changing(fctx *c, const char *name, cJSON **doc, char **doc_url)
{
    char *dir = pointer_dir(c), *path = dir ? path2(dir, name) : NULL, *etag_path = path ? otc__join(path, ".etag") : NULL;
    char *body = NULL, *etag = NULL, *url = url_resolve(c->base_url, name);
    http_resp r;
    int res;
    otc_status st;
    *doc = NULL;
    *doc_url = NULL;
    memset(&r, 0, sizeof r);
    if (!dir || !path || !etag_path || !url) { st = fail(c, OTC_E_NOMEM, NULL, "out of memory"); goto done; }
    body = slurp(path);
    if (body) {   /* a cached copy that is not JSON of the right shape is never revalidated (a 304 would keep it):
                   * fetch it again */
        cJSON *probe = otc__json_parse(body, strlen(body));
        if (!probe || !shape_ok(name, probe)) {
            logf_(c, 2, "the cached %s is not JSON of the right shape; fetching it again", path);
            free(body);
            body = NULL;
        }
        cJSON_Delete(probe);
    }
    etag = body ? slurp(etag_path) : NULL;
    if (etag) {
        size_t n = strlen(etag);
        while (n && (etag[n - 1] == '\n' || etag[n - 1] == '\r' || etag[n - 1] == ' ')) etag[--n] = '\0';
    }
    st = http_get(c, url, etag, 1, NULL, &r, &res);
    if (st != OTC_OK) goto done;
    if (res == GET_NOT_FOUND) goto done;
    if (res == GET_NOT_MODIFIED && body) {
        logf_(c, 0, "pointer %s: 304", name);
        *doc = otc__json_parse(body, strlen(body));
        if (!*doc) { st = fail(c, OTC_E_INVALID_RELEASE, path, "%s: not JSON", path); goto done; }
    } else {
        /* spec 5.2 step 2 (CR D8): the body is parsed before it is stored, so a
         * captive portal's page never replaces a good cached copy. A 200 that is
         * not JSON stands in for the network: a network error, which the
         * use_cache fallback handles. */
        logf_(c, 0, "pointer %s: 200", name);
        *doc = otc__json_parse(r.body ? (const char *)r.body : "", r.len);
        if (!*doc) {
            st = fail(c, OTC_E_NETWORK, url, "%s: the 200 response is not JSON (a captive portal or proxy page?)", url);
            if (c->err) c->err->http_status = 200;
            goto done;
        }
        if (!shape_ok(name, *doc)) {   /* CR2 DR13: JSON of the wrong shape stands in for the network too */
            st = fail(c, OTC_E_NETWORK, url, "%s: the 200 response is JSON of the wrong shape (a proxy page?)", url);
            if (c->err) c->err->http_status = 200;
            goto done;
        }
        /* the cached copy only saves work: a failure to write it is logged and the call goes on
         * (spec 4.8 cache, 5.2, CR D8); the .etag goes first, so a stale one never pairs with a new body */
        fs_unlink(etag_path);
        if (fs_mkdir_p(dir) != 0
            || write_atomic(c, dir, path, r.body ? (const char *)r.body : "", r.len) != OTC_OK
            || (r.etag[0] && write_atomic(c, dir, etag_path, r.etag, strlen(r.etag)) != OTC_OK)) {
            logf_(c, 2, "cannot write the cached %s (%s); going on without it", path, c->err->message);
            otc_error_init(c->err);
        }
    }
    *doc_url = url;
    url = NULL;
done:
    if (st != OTC_OK) {
        cJSON_Delete(*doc);
        *doc = NULL;
    }
    resp_free(&r);
    free(dir);
    free(path);
    free(etag_path);
    free(body);
    free(etag);
    free(url);
    return st;
}

static int info_desc(const void *a, const void *b)
{
    return ds_cmp((*(otc_release_info *const *)b)->datestamp, (*(otc_release_info *const *)a)->datestamp);
}

static void free_infos(otc_release_info **v, size_t n)
{
    size_t i;
    for (i = 0; i < n; i++) otc_release_info_free(v[i]);
    free(v);
}

/* OTC_index.json -> ReleaseInfo list, newest first. */
static otc_status index_infos(fctx *c, const cJSON *doc, const char *url, otc_release_info ***out, size_t *n_out)
{
    const cJSON *rels = otc__jget(doc, "releases"), *e;
    otc_release_info **v;
    size_t n = 0;
    *out = NULL;
    *n_out = 0;
    if (!cJSON_IsArray(rels)) return fail(c, OTC_E_INVALID_RELEASE, url, "%s: releases is missing", url);
    v = (otc_release_info **)calloc((size_t)cJSON_GetArraySize(rels) + 1, sizeof *v);
    if (!v) return fail(c, OTC_E_NOMEM, NULL, "out of memory");
    cJSON_ArrayForEach(e, rels) {
        otc_status st = info_from_entry(c, e, url, &v[n]);
        if (st != OTC_OK) { free_infos(v, n); return st; }
        n++;
    }
    if (n > 1) qsort(v, n, sizeof *v, info_desc);
    *out = v;
    *n_out = n;
    return OTC_OK;
}

static otc_status fetch_index(fctx *c, otc_release_info ***out, size_t *n)
{
    cJSON *doc = NULL;
    char *url = NULL;
    otc_status st = get_changing(c, "OTC_index.json", &doc, &url);
    *out = NULL;
    *n = 0;
    if (st != OTC_OK) return st;
    if (!doc) return fail(c, OTC_E_RELEASE_NOT_FOUND, NULL, "%sOTC_index.json: 404", c->base_url);
    st = index_infos(c, doc, url, out, n);
    cJSON_Delete(doc);
    free(url);
    return st;
}

/* A release this library reads: a supported format major and a
 * min_reader_version no newer than OTC_FORMAT_VERSION (spec 7.4). An entry
 * without format_version is judged as the cache path judges it: the
 * release's own .meta.json is checked when it is opened. */
static int info_readable(const otc_release_info *ri)
{
    return (!ri->format_version || format_major(ri->format_version) == OTC_FORMAT_MAJOR)
           && otc__readable(NULL, ri->min_reader_version);
}

static void note_entry(fctx *c, const otc_release_info *ri);

/* reader_too_old for a release of a supported major that needs a newer reader (spec 4.8). */
static otc_status fail_too_old(fctx *c, const char *ds, const char *mrv)
{
    return fail(c, OTC_E_READER_TOO_OLD, NULL, "release %s needs a reader for format %s; this SDK reads format %s", ds,
                mrv ? mrv : "?", OTC_FORMAT_VERSION);
}

/*
 * The newest readable release (spec 5.2 steps 2 and 2a, 7.4): the per-major
 * pointer, or OTC_latest.json only when that is a 404. When the pointer names
 * a release this library cannot read, one GET of OTC_index.json gives the
 * newest readable entry (OTC_E_READER_TOO_OLD when a release of a supported
 * major exists but none is readable, else OTC_E_UNSUPPORTED_FORMAT).
 * *read_main (may be NULL) is set when OTC_latest.json was read.
 */
static otc_status latest_info(fctx *c, otc_release_info **out, int *read_main)
{
    char name[64], *url = NULL, *too_old_ds = NULL, *too_old_mrv = NULL;
    cJSON *doc = NULL;
    otc_release_info *ri = NULL, **all = NULL;
    size_t n = 0, i;
    otc_status st;
    *out = NULL;
    if (read_main) *read_main = 0;
    snprintf(name, sizeof name, "OTC_latest-f%d.json", OTC_FORMAT_MAJOR);
    st = get_changing(c, name, &doc, &url);
    if (st == OTC_OK && !doc) {
        if (read_main) *read_main = 1;
        st = get_changing(c, "OTC_latest.json", &doc, &url);
    }
    if (st != OTC_OK) return st;
    if (!doc) return fail(c, OTC_E_RELEASE_NOT_FOUND, NULL, "no latest pointer under %s", c->base_url);
    st = info_from_entry(c, doc, url, &ri);
    cJSON_Delete(doc);
    free(url);
    if (st != OTC_OK) return st;
    if (info_readable(ri)) {
        note_entry(c, ri);
        *out = ri;
        return OTC_OK;
    }
    if (format_major(ri->format_version) == OTC_FORMAT_MAJOR) {
        too_old_ds = otc__strdup(ri->datestamp);
        too_old_mrv = ri->min_reader_version ? otc__strdup(ri->min_reader_version) : NULL;
        logf_(c, 1, "release %s needs a reader for format %s; looking for an older release", ri->datestamp,
              ri->min_reader_version ? ri->min_reader_version : "?");
    } else {
        int m = format_major(ri->format_version);
        if (m > OTC_FORMAT_MAJOR) logf_(c, 2, "a newer format (%d) exists; upgrade opentideconstants to read it", m);
        else logf_(c, 1, "the pointer names release %s of format %s, which this library does not read", ri->datestamp,
                   ri->format_version);
    }
    otc_release_info_free(ri);
    /* step 2a: one GET of the index, only in this case */
    st = fetch_index(c, &all, &n);
    if (st == OTC_E_RELEASE_NOT_FOUND) { st = OTC_OK; n = 0; }
    if (st != OTC_OK) { free(too_old_ds); free(too_old_mrv); return st; }
    for (i = 0; i < n; i++) {
        if (info_readable(all[i])) {
            *out = all[i];
            all[i] = NULL;
            break;
        }
        if (!too_old_ds && format_major(all[i]->format_version) == OTC_FORMAT_MAJOR) {
            too_old_ds = otc__strdup(all[i]->datestamp);
            too_old_mrv = all[i]->min_reader_version ? otc__strdup(all[i]->min_reader_version) : NULL;
        }
    }
    free_infos(all, n);
    if (*out) {
        if (c->err) otc_error_init(c->err);
        note_entry(c, *out);
    } else if (too_old_ds) {
        st = fail_too_old(c, too_old_ds, too_old_mrv);
    } else {
        st = fail(c, OTC_E_UNSUPPORTED_FORMAT, NULL, "no release with the supported format major %d", OTC_FORMAT_MAJOR);
    }
    free(too_old_ds);
    free(too_old_mrv);
    return st;
}

/* --------------------------------------------------------------------- cache */

static char *rel_dir(fctx *c, const char *ds)
{
    char *r = path2(c->base, "releases"), *d;
    if (!r) return NULL;
    d = path2(r, ds);
    free(r);
    return d;
}

static char *rel_file(fctx *c, const char *ds, const char *suffix)
{
    char name[NAME_CAP], *d = rel_dir(c, ds), *p;
    if (!d) return NULL;
    snprintf(name, sizeof name, "OTC_%s%s", ds, suffix);
    p = path2(d, name);
    free(d);
    return p;
}

/* A files row of .verified: an object whose sha256 and url are strings or null
 * and whose size is a non-negative integer or null (CR2 R2-088). */
static int verified_row_ok(const cJSON *row)
{
    const cJSON *sha, *url, *size;
    if (!cJSON_IsObject(row)) return 0;
    sha = otc__jget(row, "sha256");
    url = otc__jget(row, "url");
    size = otc__jget(row, "size");
    if (sha && !cJSON_IsString(sha) && !cJSON_IsNull(sha)) return 0;
    if (url && !cJSON_IsString(url) && !cJSON_IsNull(url)) return 0;
    return !size || cJSON_IsNull(size) ||
           (cJSON_IsNumber(size) && size->valuedouble >= 0 && size->valuedouble < 9007199254740992.0 &&
            size->valuedouble == (double)(int64_t)size->valuedouble);
}

/* A release's .verified record: OTC_OK with *out NULL when it is missing or not a
 * record (the release is then not verified), OTC_E_NOMEM, or OTC_E_IO. A record
 * with a files row that is not a valid row is not a record. */
static otc_status read_verified_st(fctx *c, const char *ds, cJSON **out)
{
    char *d = rel_dir(c, ds), *p = d ? path2(d, ".verified") : NULL, *t = NULL;
    otc_status st = p ? slurp_st(p, &t) : OTC_E_NOMEM;
    cJSON *doc = NULL;
    const cJSON *row;
    /* a parse that ran out of memory is out of memory, never "not verified" */
    if (t && otc__json_parse_st(t, strlen(t), &doc) == OTC_E_NOMEM) st = OTC_E_NOMEM;
    free(d);
    free(p);
    free(t);
    if (doc && !cJSON_IsObject(otc__jget(doc, "files"))) { cJSON_Delete(doc); doc = NULL; }
    if (doc) {
        cJSON_ArrayForEach(row, otc__jget(doc, "files")) {
            if (!verified_row_ok(row)) { cJSON_Delete(doc); doc = NULL; break; }
        }
    }
    *out = doc;
    return st;
}

static cJSON *read_verified(fctx *c, const char *ds)
{
    cJSON *doc = NULL;
    (void)read_verified_st(c, ds, &doc);
    return doc;
}

static void jput(cJSON *o, const char *key, cJSON *item, int *ok);

/*
 * The pointer or index entry for a cached release names its version DOI
 * (spec 4.3): .verified keeps the newest one the SDK has read, so a later
 * open from the cache reports it. A failure to write is logged, not raised.
 */
static void note_entry(fctx *c, const otc_release_info *ri)
{
    cJSON *v = read_verified(c, ri->datestamp);
    const cJSON *old;
    char *d = NULL, *p = NULL, *txt = NULL, token[33] = "";
    int held = 0;
    if (!v) return;
    old = cJSON_GetObjectItemCaseSensitive(v, "zenodo_version_doi");
    if (old && (ri->zenodo_version_doi ? (cJSON_IsString(old) && !strcmp(old->valuestring, ri->zenodo_version_doi))
                                       : cJSON_IsNull(old))) {
        cJSON_Delete(v);
        return;
    }
    cJSON_Delete(v);
    /* the read-modify-write of .verified runs under the release's lock; when another
     * process holds it (a download or index build writes .verified too), the note waits
     * for a later call rather than racing it */
    d = rel_dir(c, ri->datestamp);
    if (!d || lock_try(c, d, &held, token) != OTC_OK || !held) {
        logf_(c, 1, "release %s is locked by another process; its version DOI is noted later", ri->datestamp);
        if (c->err) otc_error_init(c->err);
        free(d);
        return;
    }
    v = read_verified(c, ri->datestamp);   /* again, now under the lock */
    if (v) {
        int ok = 1;
        cJSON_DeleteItemFromObjectCaseSensitive(v, "zenodo_version_doi");
        jput(v, "zenodo_version_doi", ri->zenodo_version_doi ? cJSON_CreateString(ri->zenodo_version_doi) : cJSON_CreateNull(),
             &ok);
        p = path2(d, ".verified");
        txt = p && ok ? cJSON_Print(v) : NULL;
        if (!txt || write_atomic(c, d, p, txt, strlen(txt)) != OTC_OK) {
            logf_(c, 2, "cannot update %s", p ? p : ri->datestamp);
            if (c->err) otc_error_init(c->err);
        }
    }
    lock_release(c, d, token);
    cJSON_free(txt);
    free(p);
    free(d);
    cJSON_Delete(v);
}

/* 1 when the file is there, 0 when not, -1 when memory runs out. */
static int file_there(fctx *c, const char *ds, const char *suffix)
{
    char *p = rel_file(c, ds, suffix);
    int r;
    if (!p) return -1;
    r = fs_kind(p) == 2;
    free(p);
    return r;
}

/* A verified release whose .jsonl and .meta.json are there (and .json when strict and asked for):
 * 1 yes, 0 no, -1 out of memory (never read as "not verified"). */
static int usable_impl(fctx *c, const char *ds, int strict)
{
    static const char *const want[] = {".jsonl", ".meta.json", ".json"};
    cJSON *v = NULL;
    int ok, i, n = (strict && (c->formats & OTC_FORMAT_JSON)) ? 3 : 2;
    if (read_verified_st(c, ds, &v) == OTC_E_NOMEM) return -1;
    ok = v != NULL;
    cJSON_Delete(v);
    for (i = 0; ok > 0 && i < n; i++) ok = file_there(c, ds, want[i]);
    return ok;
}
static int usable_strict(fctx *c, const char *ds) { return usable_impl(c, ds, 1); }
static int usable_loose(fctx *c, const char *ds) { return usable_impl(c, ds, 0); }

/* Datestamps of verified cached releases, newest first. A cache with no
 * releases directory is empty; one that is there but cannot be listed or read
 * is OTC_E_CACHE (or OTC_E_NOMEM), never "empty". */
static otc_status cached_list(fctx *c, char ***out, size_t *n_out)
{
    char *r = path2(c->base, "releases"), **names = NULL;
    size_t n = 0, i, k = 0;
    int kind;
    otc_status st;
    *out = NULL;
    *n_out = 0;
    if (!r) return fail(c, OTC_E_NOMEM, NULL, "out of memory");
    kind = fs_kind(r);
    if (kind == 0) { free(r); return OTC_OK; }
    st = kind == 1 ? fs_list(r, &names, &n) : OTC_E_IO;
    if (st != OTC_OK) {
        st = st == OTC_E_NOMEM ? fail(c, st, r, "out of memory") : fail(c, OTC_E_CACHE, r, "cannot list the cache %s", r);
        free(r);
        return st;
    }
    for (i = 0; i < n; i++) {
        cJSON *v = NULL;
        if (st == OTC_OK && valid_datestamp(names[i])) {
            st = read_verified_st(c, names[i], &v);
            if (st != OTC_OK)
                st = st == OTC_E_NOMEM ? fail(c, st, r, "out of memory")
                                       : fail(c, OTC_E_CACHE, r, "cannot read the .verified record of %s in %s", names[i], r);
        }
        if (v) names[k++] = names[i];
        else free(names[i]);
        cJSON_Delete(v);
    }
    free(r);
    if (st != OTC_OK) { free_list(names, k); return st; }
    if (k > 1) qsort(names, k, sizeof *names, ds_cmp_desc);
    *out = names;
    *n_out = k;
    return OTC_OK;
}

/* The versions of obj (a .verified record, an index entry, or a .meta.json and
 * its release object) are readable. An absent one is taken as readable (the
 * release's own files are checked at open); a present one that is not
 * MAJOR.MINOR, a string or not, is not (spec 7.4, CR D9). */
static int ver_ok(const cJSON *fv_obj, const cJSON *mrv_obj)
{
    const cJSON *fv = otc__jget(fv_obj, "format_version"), *mrv = otc__jget(mrv_obj, "min_reader_version");
    if (fv && format_major(cJSON_IsString(fv) ? fv->valuestring : NULL) != OTC_FORMAT_MAJOR) return 0;
    if (mrv && !cJSON_IsString(mrv)) return 0;
    return otc__readable(NULL, mrv ? mrv->valuestring : NULL);
}

/* A cached release this library reads (spec 5.2 step 1): its format_version
 * and min_reader_version, from .verified, the cached index and its .meta.json. */
static int cached_readable(fctx *c, const char *ds, const cJSON *index)
{
    cJSON *v = read_verified(c, ds), *meta = NULL;
    const cJSON *e;
    char *mp, *t;
    int ok = ver_ok(v, v);
    cJSON_Delete(v);
    cJSON_ArrayForEach(e, otc__jget(index, "releases"))
        if (ok && !otc__strcmp_null(otc__jstr(e, "datestamp"), ds))
            ok = ver_ok(e, e);
    if (!ok) return 0;
    mp = rel_file(c, ds, ".meta.json");
    t = mp ? slurp(mp) : NULL;
    meta = t ? otc__json_parse(t, strlen(t)) : NULL;
    if (meta) ok = ver_ok(meta, otc__jget(meta, "release"));
    cJSON_Delete(meta);
    free(t);
    free(mp);
    return ok;
}

/* The newest cached release that C can open and read (spec 5.2 step 1, 7.4):
 * OTC_OK with *out NULL when there is none; OTC_E_CACHE or OTC_E_NOMEM when
 * the cache cannot be read. */
static otc_status newest_cached(fctx *c, char **out)
{
    char **list = NULL, *dir = pointer_dir(c), *ip = dir ? path2(dir, "OTC_index.json") : NULL;
    char *it = ip ? slurp(ip) : NULL;
    cJSON *index = it ? otc__json_parse(it, strlen(it)) : NULL;
    size_t n = 0, i;
    otc_status st = (dir && ip) ? cached_list(c, &list, &n) : fail(c, OTC_E_NOMEM, NULL, "out of memory");
    *out = NULL;
    free(dir);
    free(ip);
    free(it);
    for (i = 0; st == OTC_OK && i < n && !*out; i++) {
        int u = usable_loose(c, list[i]);
        if (u < 0) { st = fail(c, OTC_E_NOMEM, NULL, "out of memory"); break; }
        if (!u || !cached_readable(c, list[i], index)) continue;
        if (!(*out = otc__strdup(list[i]))) st = fail(c, OTC_E_NOMEM, NULL, "out of memory");
    }
    free_list(list, n);
    cJSON_Delete(index);
    return st;
}

/* release.files from .verified (spec 4.3.1), sorted by name. */
static otc_status files_from_verified(fctx *c, const char *ds, otc_file_info **out, size_t *n_out)
{
    cJSON *v = NULL;
    otc_status vs = read_verified_st(c, ds, &v);
    const cJSON *files = otc__jget(v, "files"), *f;
    otc_file_info *arr;
    size_t n = 0;
    *out = NULL;
    *n_out = 0;
    if (vs == OTC_E_NOMEM) { cJSON_Delete(v); return fail(c, vs, NULL, "out of memory"); }
    if (!v) return fail(c, OTC_E_CACHE, NULL, "release %s has no .verified record", ds);
    arr = (otc_file_info *)calloc((size_t)cJSON_GetArraySize(files) + 1, sizeof *arr);
    if (!arr) { cJSON_Delete(v); return fail(c, OTC_E_NOMEM, NULL, "out of memory"); }
    cJSON_ArrayForEach(f, files) {
        const char *u = otc__jstr(f, "url"), *sha = otc__jstr(f, "sha256");
        arr[n].name = otc__strdup(f->string);
        arr[n].url = u ? otc__strdup(u) : NULL;
        arr[n].sha256 = sha ? otc__strdup(sha) : NULL;
        arr[n].size = otc__jint(f, "size");
        n++;
        if (!arr[n - 1].name || (u && !arr[n - 1].url) || (sha && !arr[n - 1].sha256)) {
            free_file_infos(arr, n);
            cJSON_Delete(v);
            return fail(c, OTC_E_NOMEM, NULL, "out of memory");
        }
    }
    cJSON_Delete(v);
    if (n > 1) qsort(arr, n, sizeof *arr, fi_cmp);
    *out = arr;
    *n_out = n;
    return OTC_OK;
}

/* Opening from the cache compares the sizes with .verified (spec 5.3); otc_open_file hashes against .sha256. */
static otc_status check_cached_sizes(fctx *c, const char *ds)
{
    static const char *const suffixes[] = {".jsonl", ".meta.json", NULL};
    cJSON *v = NULL;
    const cJSON *files;
    size_t i;
    /* out of memory is never "no sizes to compare" */
    otc_status st = read_verified_st(c, ds, &v) == OTC_E_NOMEM ? fail(c, OTC_E_NOMEM, NULL, "out of memory") : OTC_OK;
    files = otc__jget(v, "files");
    for (i = 0; suffixes[i] && st == OTC_OK; i++) {
        char name[NAME_CAP], *p = rel_file(c, ds, suffixes[i]);
        const cJSON *rec;
        snprintf(name, sizeof name, "OTC_%s%s", ds, suffixes[i]);
        rec = otc__jget(files, name);
        if (!p) st = fail(c, OTC_E_NOMEM, NULL, "out of memory");
        else if (otc__jint(rec, "size") >= 0 && otc__path_size(p) != otc__jint(rec, "size"))
            st = fail_checksum(c, p, otc__jstr(rec, "sha256"), "", "the size does not match .verified");
        free(p);
    }
    cJSON_Delete(v);
    return st;
}

/* ------------------------------------------------------------- stream index */

static cJSON *str_or_null(const char *s) { return s ? cJSON_CreateString(s) : cJSON_CreateNull(); }

/* Adds item to o under key; on any failure (item or o NULL, no memory for the key) the item is
 * deleted and *ok cleared, so a record is either whole or not written. */
static void jput(cJSON *o, const char *key, cJSON *item, int *ok)
{
    if (!item || !o || !cJSON_AddItemToObject(o, key, item)) {
        cJSON_Delete(item);
        *ok = 0;
    }
}

/*
 * index-v1.json (spec 6.2). otc_open_file reads it when it is fresh; when the
 * open did not use it (missing or stale), it is written here with an atomic
 * rename. A failure to write it is logged, not raised: it only saves work.
 */
static void write_stream_index(fctx *c, const char *ds, const otc_release *rel)
{
    char *d, *p, *txt = NULL, jn[NAME_CAP];
    const char *sha = NULL;
    cJSON *doc;
    size_t i;
    if (!rel || rel->index_used) return;
    snprintf(jn, sizeof jn, "OTC_%s.jsonl", ds);
    for (i = 0; i < rel->n_files; i++)
        if (!strcmp(rel->files[i].name, jn)) sha = rel->files[i].sha256;
    if (!sha) return;
    d = rel_dir(c, ds);
    p = d ? path2(d, "index-v1.json") : NULL;
    doc = p ? otc__index_doc(rel, sha, SDK_ID) : NULL;
    if (doc) txt = cJSON_PrintUnformatted(doc);
    if (!txt || write_atomic(c, d, p, txt, strlen(txt)) != OTC_OK) {
        logf_(c, 2, "cannot write the stream index %s", p ? p : ds);
        if (c->err) otc_error_init(c->err);
    }
    cJSON_free(txt);
    cJSON_Delete(doc);
    free(p);
    free(d);
}

/* ---------------------------------------------------------- download to cache */

static const char *row_of(char **names, char **digests, size_t n, const char *name)
{
    size_t i;
    for (i = 0; i < n; i++)
        if (!strcmp(names[i], name)) return digests[i];
    return NULL;
}

/* Spec 5.2 step 4.1: the pointer (or index entry) and OTC_{D}.sha256 agree. The
 * .sha256 file's own digest is the pointer's row for it, each data file's row
 * is the pointer's, and the .sha256 lists no file the pointer does not list.
 * sums_hex is the SHA-256 of the .sha256 file. */
static otc_status check_pointer(fctx *c, const otc_release_info *info, char **names, char **digests, size_t n,
                                const char *sums_name, const char *sums_hex)
{
    size_t i;
    const otc_file_info *self;
    if (!info || !info->n_files) return OTC_OK;
    self = info_file(info, sums_name);
    if (self && self->sha256 && strcmp(self->sha256, sums_hex) != 0)
        return fail_checksum(c, sums_name, self->sha256, sums_hex, "the pointer's SHA-256 of the .sha256 file does not match it");
    for (i = 0; i < info->n_files; i++) {
        const char *row = row_of(names, digests, n, info->files[i].name);
        if (row && info->files[i].sha256 && strcmp(row, info->files[i].sha256) != 0)
            return fail_checksum(c, info->files[i].name, row, info->files[i].sha256,
                                 "the pointer and the .sha256 file disagree");
    }
    for (i = 0; i < n; i++)
        if (!info_file(info, names[i]))
            return fail_checksum(c, names[i], digests[i], "", "the .sha256 file lists a file that the pointer does not");
    return OTC_OK;
}

/* Downloads one data file to a tmp file in dir and checks its size and SHA-256. */
static otc_status fetch_file(fctx *c, const char *url, const char *dir, const char *name, const char *expected_sha,
                             int64_t expected_size, char **tmp_out)
{
    char *tmp = tmp_path(dir);
    http_resp r;
    int res;
    otc_status st;
    *tmp_out = NULL;
    memset(&r, 0, sizeof r);
    if (!tmp) return fail(c, OTC_E_NOMEM, NULL, "out of memory");
    st = http_get(c, url, NULL, !otc__ends_with(name, ".gz"), tmp, &r, &res);
    if (st == OTC_OK && res == GET_NOT_FOUND) st = fail(c, OTC_E_RELEASE_NOT_FOUND, url, "%s: 404", url);
    if (st == OTC_OK && ((expected_size >= 0 && (int64_t)r.size != expected_size) || !expected_sha
                         || strcmp(r.hex, expected_sha) != 0))
        st = fail_checksum(c, name, expected_sha, r.hex, "the SHA-256 or size does not match");
    resp_free(&r);
    if (st != OTC_OK) {
        fs_unlink(tmp);
        free(tmp);
        return st;
    }
    logf_(c, 1, "downloaded %s (%lu bytes)", url, (unsigned long)r.size);
    *tmp_out = tmp;
    return OTC_OK;
}

/* Renames the files in place (sha256 first, as the rows they will be read against). */
typedef struct pending {
    char *tmp;
    char *dest;
} pending;

static void pending_free(pending *p, size_t n, int unlink_tmp)
{
    size_t i;
    for (i = 0; i < n; i++) {
        if (unlink_tmp && p[i].tmp) fs_unlink(p[i].tmp);
        free(p[i].tmp);
        free(p[i].dest);
    }
}

static void utc_now(char out[32])
{
    time_t now = time(NULL);
    struct tm tmv;
#ifdef _WIN32
    gmtime_s(&tmv, &now);
#else
    gmtime_r(&now, &tmv);
#endif
    strftime(out, 32, "%Y-%m-%dT%H:%M:%SZ", &tmv);
}

/*
 * Spec 5.2 step 4: the .sha256 list, the pointer check, the data files
 * (.jsonl, .meta.json, and .json when asked) to temporary files with their
 * size and SHA-256 checked, the renames, a test open, the stream index, and
 * .verified last. *rel_out gets the opened release (or NULL).
 */
static otc_status download_to_cache(fctx *c, const char *ds, const otc_release_info *info, otc_release **rel_out)
{
    char *dir = rel_dir(c, ds), *sha_tmp = NULL, *sha_url = NULL, *jsonl_path = NULL;
    char **names = NULL, **digests = NULL, sha_name[NAME_CAP], sums_hex[65];
    size_t n_rows = 0, n_pend = 0, i;
    pending pend[4];
    cJSON *old = NULL, *ver = NULL, *files;
    int held = 0, res;
    char token[33] = "";
    http_resp r;
    otc_status st = OTC_OK;
    otc_release *rel = NULL;
    static const char *const want_all[] = {".jsonl", ".meta.json", ".json", NULL};

    *rel_out = NULL;
    memset(&r, 0, sizeof r);
    memset(pend, 0, sizeof pend);
    if (!dir) return fail(c, OTC_E_NOMEM, NULL, "out of memory");
    if ((res = fs_mkdir_p(dir)) != 0) {
        st = res == -2 ? fail(c, OTC_E_NOMEM, NULL, "out of memory")
                       : fail(c, OTC_E_CACHE, dir, "cannot create the cache directory %s", dir);
        goto out;
    }
    if ((st = lock_take(c, dir, ds, usable_strict, &held, token)) != OTC_OK) goto out;
    if (!held) goto out;
    if ((res = usable_strict(c, ds)) < 0) { st = fail(c, OTC_E_NOMEM, NULL, "out of memory"); goto out; }
    if (res) goto out;   /* another process finished it */

    /* 1. the .sha256 list */
    snprintf(sha_name, sizeof sha_name, "OTC_%s.sha256", ds);
    {   /* the pointer's url for it when the pointer lists it (spec 4.3.1), else base_url */
        const otc_file_info *pf = info_file(info, sha_name);
        sha_url = (pf && pf->url) ? otc__strdup(pf->url) : url_resolve(c->base_url, sha_name);
    }
    sha_tmp = tmp_path(dir);
    if (!sha_url || !sha_tmp) { st = fail(c, OTC_E_NOMEM, NULL, "out of memory"); goto out; }
    st = http_get(c, sha_url, NULL, 1, sha_tmp, &r, &res);
    if (st == OTC_OK && res == GET_NOT_FOUND) st = fail(c, OTC_E_RELEASE_NOT_FOUND, sha_url, "release %s not found (%s)", ds, sha_url);
    memcpy(sums_hex, r.hex, sizeof sums_hex);
    resp_free(&r);
    if (st != OTC_OK) goto out;
    if ((st = otc__sha256_rows(sha_tmp, &names, &digests, &n_rows)) != OTC_OK) {
        if (st == OTC_E_INVALID_RELEASE) st = fail(c, st, sha_name, "%s %s", otc__sha256_rows_what(st), sha_name);
        else st = fail(c, st == OTC_E_NOMEM ? st : OTC_E_CACHE, sha_tmp, "cannot read %s", sha_tmp);
        goto out;
    }
    if (n_rows == 0) {   /* CR2 DR13: a 200 with no "<sha256>  <name>" row (a captive portal) stands in for the network */
        st = fail(c, OTC_E_NETWORK, sha_url, "%s: the 200 response has no \"<sha256>  <name>\" row (a captive portal or proxy page?)",
                  sha_url);
        if (c->err) c->err->http_status = 200;
        goto out;
    }
    if ((st = check_pointer(c, info, names, digests, n_rows, sha_name, sums_hex)) != OTC_OK) goto out;

    /* 2. the data files (a file already there and recorded with the same SHA-256 is kept) */
    old = read_verified(c, ds);
    for (i = 0; want_all[i]; i++) {
        char name[NAME_CAP], *url, *dest;
        const char *row;
        const otc_file_info *pf;
        const cJSON *orec;
        if (i == 2 && !(c->formats & OTC_FORMAT_JSON)) continue;
        snprintf(name, sizeof name, "OTC_%s%s", ds, want_all[i]);
        row = row_of(names, digests, n_rows, name);
        if (!row) { st = fail(c, OTC_E_INVALID_RELEASE, name, "%s is not in the .sha256 file", name); goto out; }
        dest = path2(dir, name);
        if (!dest) { st = fail(c, OTC_E_NOMEM, NULL, "out of memory"); goto out; }
        orec = otc__jget(otc__jget(old, "files"), name);
        if (fs_kind(dest) == 2 && otc__jstr(orec, "sha256") && !strcmp(otc__jstr(orec, "sha256"), row)) {
            free(dest);
            continue;
        }
        pf = info_file(info, name);
        url = (pf && pf->url) ? otc__strdup(pf->url) : url_resolve(c->base_url, name);
        if (!url) { free(dest); st = fail(c, OTC_E_NOMEM, NULL, "out of memory"); goto out; }
        st = fetch_file(c, url, dir, name, row, pf ? pf->size : -1, &pend[n_pend].tmp);
        free(url);
        if (st != OTC_OK) { free(dest); goto out; }
        pend[n_pend++].dest = dest;
    }

    /* 3. renames: the .sha256 first, then the data files. An old .verified goes first, so that
     * it never vouches for a directory whose files are being replaced (spec 5.4: .verified
     * is written last, and a reader trusts a directory only when it exists). */
    if (old) {
        char *vpath = path2(dir, ".verified");
        int gone = vpath && (fs_unlink(vpath) == 0 || fs_kind(vpath) == 0);
        if (!gone) {
            st = fail(c, OTC_E_CACHE, vpath, "cannot remove %s", vpath ? vpath : dir);
            free(vpath);
            goto out;
        }
        free(vpath);
    }
    {
        char *sha_dest = path2(dir, sha_name);
        if (!sha_dest || fs_rename(sha_tmp, sha_dest) != 0) {
            st = fail(c, OTC_E_CACHE, sha_dest, "cannot write %s", sha_dest ? sha_dest : dir);
            free(sha_dest);
            goto out;
        }
        free(sha_dest);
        free(sha_tmp);
        sha_tmp = NULL;
    }
    for (i = 0; i < n_pend; i++) {
        if (fs_rename(pend[i].tmp, pend[i].dest) != 0) {
            st = fail(c, OTC_E_CACHE, pend[i].dest, "cannot write %s", pend[i].dest);
            goto out;
        }
        free(pend[i].tmp);
        pend[i].tmp = NULL;
    }
    logf_(c, 1, "downloaded and verified %s", ds);

    /* 4. a test open (format major, references), the stream index, then .verified */
    jsonl_path = rel_file(c, ds, ".jsonl");
    if (!jsonl_path) { st = fail(c, OTC_E_NOMEM, NULL, "out of memory"); goto out; }
    {
        otc_open_options oo;
        cache_open_options(c, &oo);
        st = otc_open_file(jsonl_path, &oo, &rel);
        if (st != OTC_OK) goto out;
    }
    write_stream_index(c, ds, rel);
    {   /* .verified: every allocation is checked, so a partial record (one with no files, which
         * reads as "not verified" and has the release downloaded again) is never written */
        int ok = 1;
        char now[32], fvbuf[64], *vpath, *txt;
        size_t need;
        ver = cJSON_CreateObject();
        files = cJSON_CreateObject();
        if (!ver || !files) ok = 0;
        if (old && cJSON_IsObject(otc__jget(old, "files"))) {
            const cJSON *f;
            cJSON_ArrayForEach(f, otc__jget(old, "files")) jput(files, f->string, cJSON_Duplicate(f, 1), &ok);
        }
        /* the rows of OTC_{D}.sha256 always (a pointer that lists no files still gives a checked
         * release.files, spec 4.3.1), then the pointer's own rows, which carry the urls */
        for (i = 0; ok && i < n_rows; i++) {
            char *p = path2(dir, names[i]), *u = url_resolve(c->base_url, names[i]);
            int64_t size = p ? otc__path_size(p) : -1;
            const cJSON *prev = otc__jget(otc__jget(files, names[i]), "size");
            cJSON *o = cJSON_CreateObject();
            if (!p || !u) ok = 0;
            jput(o, "sha256", cJSON_CreateString(digests[i]), &ok);
            jput(o, "size", size >= 0 ? cJSON_CreateNumber((double)size)
                            : cJSON_IsNumber(prev) ? cJSON_CreateNumber(prev->valuedouble) : cJSON_CreateNull(), &ok);
            jput(o, "url", info ? cJSON_CreateNull() : str_or_null(u), &ok);
            cJSON_DeleteItemFromObjectCaseSensitive(files, names[i]);
            jput(files, names[i], o, &ok);
            free(p);
            free(u);
        }
        for (i = 0; ok && info && i < info->n_files; i++) {
            const otc_file_info *f = &info->files[i];
            cJSON *o = cJSON_CreateObject();
            jput(o, "sha256", str_or_null(f->sha256), &ok);
            jput(o, "size", f->size >= 0 ? cJSON_CreateNumber((double)f->size) : cJSON_CreateNull(), &ok);
            jput(o, "url", str_or_null(f->url), &ok);
            cJSON_DeleteItemFromObjectCaseSensitive(files, f->name);
            jput(files, f->name, o, &ok);
        }
        jput(ver, "files", files, &ok);   /* ver owns files now (or it is deleted) */
        utc_now(now);
        jput(ver, "verified_at", cJSON_CreateString(now), &ok);
        jput(ver, "by", cJSON_CreateString(SDK_ID), &ok);
        jput(ver, "datestamp", cJSON_CreateString(ds), &ok);
        if (otc_release_format_version(rel, fvbuf, sizeof fvbuf, &need) == OTC_OK)
            jput(ver, "format_version", cJSON_CreateString(fvbuf), &ok);
        if (otc__jstr(rel->release_obj, "min_reader_version"))
            jput(ver, "min_reader_version", cJSON_CreateString(otc__jstr(rel->release_obj, "min_reader_version")), &ok);
        /* the version DOI of the entry used (spec 4.3); a pinned download reads no entry */
        jput(ver, "zenodo_version_doi", str_or_null(info ? info->zenodo_version_doi : NULL), &ok);
        vpath = path2(dir, ".verified");
        txt = ok ? cJSON_Print(ver) : NULL;
        if (!vpath || !txt) st = fail(c, OTC_E_NOMEM, NULL, "out of memory");
        else st = write_atomic(c, dir, vpath, txt, strlen(txt));
        cJSON_free(txt);
        free(vpath);
    }
out:
    if (st != OTC_OK) {
        otc_close(rel);
        rel = NULL;
    }
    pending_free(pend, n_pend, 1);
    if (sha_tmp) fs_unlink(sha_tmp);
    if (held) lock_release(c, dir, token);
    otc__free_rows(names, digests, n_rows);
    cJSON_Delete(old);
    cJSON_Delete(ver);
    free(sha_tmp);
    free(sha_url);
    free(jsonl_path);
    free(dir);
    *rel_out = rel;
    return st;
}

static otc_status ensure_root(fctx *c)
{
    char *r = path2(c->base, "releases");
    otc_status st = OTC_OK;
    int m = r ? fs_mkdir_p(r) : -2;
    if (m == -2) st = fail(c, OTC_E_NOMEM, NULL, "out of memory");
    else if (m != 0) st = fail(c, OTC_E_CACHE, r, "cannot create the cache directory %s", r);
    free(r);
    return st;
}

/* Opens a cached release (its sizes checked against .verified). */
static otc_status open_cached(fctx *c, const char *ds, otc_release **out)
{
    char *p = rel_file(c, ds, ".jsonl");
    otc_open_options oo;
    otc_status st;
    *out = NULL;
    if (!p) return fail(c, OTC_E_NOMEM, NULL, "out of memory");
    if ((st = check_cached_sizes(c, ds)) == OTC_OK) {
        cache_open_options(c, &oo);
        st = otc_open_file(p, &oo, out);
        if (st == OTC_OK) write_stream_index(c, ds, *out);
    }
    free(p);
    return st;
}

/* A cached release that failed its size or SHA-256 check or does not parse
 * (spec 5.2 step 6); a format this library cannot read is not corrupt. */
static int corrupt_status(otc_status st) { return st == OTC_E_CHECKSUM || st == OTC_E_INVALID_RELEASE; }

/*
 * Removes a corrupt cached release (spec 5.2 step 6): .verified first, so it is
 * no longer trusted, then its data files. A failure to delete is logged; it
 * never hides the error that found the release corrupt.
 */
static void heal(fctx *c, const char *ds, const char *why)
{
    char *d = rel_dir(c, ds), *p[3];
    size_t i;
    p[0] = d ? path2(d, ".verified") : NULL;
    p[1] = rel_file(c, ds, ".jsonl");
    p[2] = rel_file(c, ds, ".meta.json");
    logf_(c, 2, "the cached release %s is corrupt (%s); removing it from the cache", ds, why);
    for (i = 0; i < 3; i++) {
        if (!p[i]) logf_(c, 2, "cannot remove a file of the cached release %s: out of memory", ds);
        else if (fs_unlink(p[i]) != 0 && fs_kind(p[i]) != 0) logf_(c, 2, "cannot remove %s", p[i]);
        free(p[i]);
    }
    free(d);
}

/*
 * Opens the newest cached release that C reads (spec 5.2 steps 1, 5 and 6). A
 * candidate that fails its check or does not parse is healed and the next
 * older one is tried; one whose format C cannot read is skipped. OTC_OK with
 * *rel NULL when none loads (the caller reports its own error); OTC_E_CACHE or
 * OTC_E_NOMEM when the cache cannot be read.
 */
static otc_status open_newest_cached(fctx *c, char **ds_out, otc_release **rel)
{
    char **list = NULL, *dir = pointer_dir(c), *ip = dir ? path2(dir, "OTC_index.json") : NULL;
    char *it = ip ? slurp(ip) : NULL;
    cJSON *index = it ? otc__json_parse(it, strlen(it)) : NULL;
    size_t n = 0, i;
    otc_status st = (dir && ip) ? cached_list(c, &list, &n) : fail(c, OTC_E_NOMEM, NULL, "out of memory");
    *ds_out = NULL;
    *rel = NULL;
    free(dir);
    free(ip);
    free(it);
    for (i = 0; st == OTC_OK && i < n && !*rel; i++) {
        otc_status ost;
        if (!usable_loose(c, list[i]) || !cached_readable(c, list[i], index)) continue;
        ost = open_cached(c, list[i], rel);
        if (ost == OTC_OK) {
            if (!(*ds_out = otc__strdup(list[i]))) {
                otc_close(*rel);
                *rel = NULL;
                st = fail(c, OTC_E_NOMEM, NULL, "out of memory");
            }
        } else if (corrupt_status(ost)) {
            heal(c, list[i], c->err->message);
            otc_error_init(c->err);
        } else if (ost == OTC_E_UNSUPPORTED_FORMAT || ost == OTC_E_READER_TOO_OLD) {
            logf_(c, 1, "the cached release %s is not readable: %s", list[i], c->err->message);
            otc_error_init(c->err);
        } else {
            st = ost;
        }
    }
    free_list(list, n);
    cJSON_Delete(index);
    return st;
}

/* Puts a release into the cache if needed and opens it. */
static otc_status ensure_cached(fctx *c, const char *ds, const otc_release_info *info, otc_release **rel,
                                otc_loaded_from *lf)
{
    otc_status st;
    int u = usable_strict(c, ds);
    if (u < 0) return fail(c, OTC_E_NOMEM, NULL, "out of memory");
    if (u) {
        *lf = OTC_LOADED_FROM_CACHE;
        st = open_cached(c, ds, rel);
        if (!corrupt_status(st)) return st;
        /* spec 4.8, 5.2 step 6, 5.3: a cached release that fails its check or does not
         * parse is healed and, online, downloaded again: its .verified goes first, so
         * every file is fetched */
        {
            char *d = rel_dir(c, ds), *v = d ? path2(d, ".verified") : NULL;
            int gone;
            heal(c, ds, c->err->message);
            gone = v && fs_kind(v) == 0;
            free(v);
            free(d);
            if (!gone) return st;
            logf_(c, 2, "downloading the release %s again", ds);
            otc_error_init(c->err);
        }
    }
    st = download_to_cache(c, ds, info, rel);
    if (st == OTC_OK && !*rel) {   /* another process finished it while we waited */
        *lf = OTC_LOADED_FROM_CACHE;
        return open_cached(c, ds, rel);
    }
    *lf = OTC_LOADED_FROM_DOWNLOAD;
    return st;
}

/*
 * Resolves release (NULL / "latest" or a datestamp) to an open release in the
 * cache (spec 5.2). *last_status / last_msg hold the network error behind
 * cache_after_error.
 */
static otc_status resolve(fctx *c, const char *release, otc_release **rel, otc_loaded_from *lf, char **ds_out,
                          otc_status *last_status, char *last_msg, size_t last_len)
{
    otc_status st;
    otc_release_info *info = NULL;
    *rel = NULL;
    *ds_out = NULL;
    *last_status = OTC_OK;
    if (release && strcmp(release, "latest") != 0) {
        if (!valid_datestamp(release))
            return fail(c, OTC_E_INVALID_ARGUMENT, NULL, "release must be 'latest' or a datestamp, not '%s'", release);
        if ((st = ensure_root(c)) != OTC_OK) return st;
        *ds_out = otc__strdup(release);
        if (!*ds_out) return fail(c, OTC_E_NOMEM, NULL, "out of memory");
        if (c->offline) {
            int u = usable_loose(c, release);
            if (u < 0) return fail(c, OTC_E_NOMEM, NULL, "out of memory");
            if (!u)
                return fail(c, OTC_E_OFFLINE_UNAVAILABLE, NULL, "offline, and release %s is not in the cache", release);
            *lf = OTC_LOADED_FROM_CACHE;
            st = open_cached(c, release, rel);
            if (corrupt_status(st)) {   /* spec 5.2 step 6: healed; the error stays the check's */
                otc_error keep = *c->err;
                heal(c, release, keep.message);
                *c->err = keep;
            }
            return st;
        }
        return ensure_cached(c, release, NULL, rel, lf);
    }
    if ((st = ensure_root(c)) != OTC_OK) return st;
    if (c->offline) {
        if ((st = open_newest_cached(c, ds_out, rel)) != OTC_OK) return st;
        if (!*rel) return fail(c, OTC_E_OFFLINE_UNAVAILABLE, NULL, "offline, and no release is in the cache");
        *lf = OTC_LOADED_FROM_CACHE;
        return OTC_OK;
    }
    st = latest_info(c, &info, NULL);
    if (st == OTC_OK) {
        *ds_out = otc__strdup(info->datestamp);
        st = *ds_out ? ensure_cached(c, info->datestamp, info, rel, lf) : fail(c, OTC_E_NOMEM, NULL, "out of memory");
        otc_release_info_free(info);
    }
    if (st == OTC_E_NETWORK && !c->raise) {
        char *ds = NULL;
        otc_release *crel = NULL;
        otc_error net = *c->err;
        otc_status cst;
        otc_error_init(c->err);
        cst = open_newest_cached(c, &ds, &crel);
        if (cst != OTC_OK || !crel) {
            /* no cached release stands in: the error is the network's (spec 5.2 step 6) */
            if (cst != OTC_OK) logf_(c, 2, "the cache cannot stand in: %s", c->err->message);
            *c->err = net;
            free(ds);
            return OTC_E_NETWORK;
        }
        snprintf(last_msg, last_len, "%s", net.message);
        logf_(c, 2, "network error (%s); using the cached release %s", last_msg, ds);
        free(*ds_out);
        *ds_out = ds;
        *rel = crel;
        *last_status = OTC_E_NETWORK;
        *lf = OTC_LOADED_FROM_CACHE_AFTER_ERROR;
        return OTC_OK;
    }
    return st;
}

static otc_status copy_path(fctx *c, const char *p, char *buf, size_t len, size_t *needed)
{
    otc_status st = otc__copy_str(p, buf, len, needed);
    if (st == OTC_E_BUFFER_TOO_SMALL) fail(c, st, p, "the path needs %lu bytes", (unsigned long)strlen(p) + 1);
    return st;
}

static otc_status fetch_path(const otc_fetch_options *opts, const char *release, char *path, size_t len,
                             size_t *needed)
{
    fctx c;
    otc_release *rel = NULL;
    otc_loaded_from lf;
    char *ds = NULL, msg[512], *p;
    otc_status st, last;
    if (path && len) path[0] = '\0';   /* a failed call leaves no path and no size behind */
    if (needed) *needed = 0;
    st = ctx_init(&c, opts);
    if (st == OTC_OK) st = resolve(&c, release, &rel, &lf, &ds, &last, msg, sizeof msg);
    otc_close(rel);
    if (st == OTC_OK) {
        p = rel_file(&c, ds, ".jsonl");
        st = p ? copy_path(&c, p, path, len, needed) : fail(&c, OTC_E_NOMEM, NULL, "out of memory");
        free(p);
    }
    free(ds);
    ctx_free(&c);
    return st;
}

/* ------------------------------------------------------------------ the API */

void otc_fetch_options_init(otc_fetch_options *opts)
{
    if (!opts) return;
    memset(opts, 0, sizeof *opts);
    opts->struct_size = sizeof *opts;
    opts->timeout_s = OTC_TIMEOUT_DEFAULT;
    opts->formats = OTC_FORMATS_DEFAULT;
    opts->on_network_error = OTC_ON_NETWORK_ERROR_USE_CACHE;
}

otc_status otc_fetch_latest(const otc_fetch_options *opts, char *path, size_t len, size_t *needed)
{
    return fetch_path(opts, NULL, path, len, needed);
}

otc_status otc_fetch_release(const otc_fetch_options *opts, const char *datestamp, char *path, size_t len,
                             size_t *needed)
{
    if (!datestamp) {
        fctx c;
        otc_status st;
        if (path && len) path[0] = '\0';
        if (needed) *needed = 0;
        st = ctx_init(&c, opts);
        if (st == OTC_OK) st = fail(&c, OTC_E_INVALID_ARGUMENT, NULL, "datestamp is NULL");
        ctx_free(&c);
        return st;
    }
    return fetch_path(opts, datestamp, path, len, needed);
}

otc_status otc_fetch_open(const otc_fetch_options *fopts, const char *release, const otc_open_options *oopts,
                          otc_release **out)
{
    fctx c;
    otc_release *rel = NULL;
    otc_loaded_from lf = OTC_LOADED_FROM_UNSET;
    char *ds = NULL, msg[512];
    otc_status last = OTC_OK, st;
    otc_error *oerr = (oopts && oopts->struct_size >= sizeof *oopts) ? otc__err_usable(oopts->error) : NULL;
    if (out) *out = NULL;
    st = ctx_init(&c, fopts);
    if (st == OTC_OK && !out) st = fail(&c, OTC_E_INVALID_ARGUMENT, NULL, "out is NULL");
    if (st == OTC_OK && oopts && oopts->struct_size < sizeof *oopts)
        st = fail(&c, OTC_E_INVALID_ARGUMENT, NULL, "otc_open_options: struct_size is too small");
    if (st == OTC_OK) c.oo = oopts;   /* require_checksum and log_fn apply to the open of the cached file (C25) */
    if (st == OTC_OK) st = resolve(&c, release, &rel, &lf, &ds, &last, msg, sizeof msg);
    if (st == OTC_OK) {
        otc_file_info *files = NULL;
        size_t n = 0;
        st = files_from_verified(&c, ds, &files, &n);
        if (st == OTC_OK) {
            cJSON *v = NULL;
            int nomem = read_verified_st(&c, ds, &v) == OTC_E_NOMEM;
            const char *zdoi = otc__jstr(v, "zenodo_version_doi");
            free_file_infos(rel->files, rel->n_files);
            rel->files = files;
            rel->n_files = n;
            free(rel->zenodo_version_doi);
            rel->zenodo_version_doi = zdoi ? otc__strdup(zdoi) : NULL;
            nomem = nomem || (zdoi && !rel->zenodo_version_doi);
            cJSON_Delete(v);
            if (nomem) {
                otc_close(rel);
                rel = NULL;
                st = fail(&c, OTC_E_NOMEM, NULL, "out of memory");
            }
        }
        if (st == OTC_OK) {
            rel->loaded_from = lf;
            if (last != OTC_OK) {
                rel->last_status = last;
                snprintf(rel->last_message, sizeof rel->last_message, "%s", msg);
            }
            if (oopts && oopts->log_fn) {
                char m[256];
                snprintf(m, sizeof m, "opened %s (%s)", ds, otc_loaded_from_name(lf));
                oopts->log_fn(oopts->log_user_data, 1, m);
            }
            *out = rel;
            rel = NULL;
        }
    }
    otc_close(rel);
    if (oerr && oerr != c.err) *oerr = *c.err;
    free(ds);
    ctx_free(&c);
    return st;
}

/* The cached OTC_index.json -> ReleaseInfo list; missing_st / missing_msg when it is not cached. */
static otc_status cached_index(fctx *c, otc_status missing_st, const char *missing_msg, otc_release_info ***v,
                               size_t *n)
{
    char *dir = pointer_dir(c), *p = dir ? path2(dir, "OTC_index.json") : NULL, *t = p ? slurp(p) : NULL;
    char *url = url_resolve(c->base_url, "OTC_index.json");
    cJSON *doc = t ? otc__json_parse(t, strlen(t)) : NULL;
    otc_status st;
    if (!dir || !p || !url) st = fail(c, OTC_E_NOMEM, NULL, "out of memory");
    else if (!t) st = fail(c, missing_st, NULL, "%s", missing_msg);
    else if (!doc) st = fail(c, OTC_E_INVALID_RELEASE, p, "cached OTC_index.json: not JSON");
    else {
        otc_error_init(c->err);
        st = index_infos(c, doc, url, v, n);
    }
    cJSON_Delete(doc);
    free(url);
    free(dir);
    free(p);
    free(t);
    return st;
}

otc_status otc_fetch_releases(const otc_fetch_options *opts, otc_release_info **out, size_t cap, size_t *count)
{
    fctx c;
    otc_release_info **v = NULL;
    size_t n = 0, i;
    otc_status st = ctx_init(&c, opts);
    if (count) *count = 0;
    if (st == OTC_OK && (!count || (cap && !out))) st = fail(&c, OTC_E_INVALID_ARGUMENT, NULL, "count is NULL");
    if (st == OTC_OK) {
        if (c.offline) {
            st = cached_index(&c, OTC_E_OFFLINE_UNAVAILABLE, "offline, and the release index is not in the cache", &v, &n);
        } else {
            st = fetch_index(&c, &v, &n);
            if (st == OTC_E_NETWORK && !c.raise) {
                /* spec 4.3, 5.2 step 5: with use_cache, a network error gives the cached index */
                char msg[512];
                snprintf(msg, sizeof msg, "%s", c.err->message);
                st = cached_index(&c, OTC_E_NETWORK, msg, &v, &n);
                if (st == OTC_OK) logf_(&c, 2, "network error (%s); using the cached release index", msg);
            }
        }
    }
    for (i = 0; st == OTC_OK && i < n; i++) note_entry(&c, v[i]);
    if (st == OTC_OK) {
        *count = n;
        for (i = 0; i < n && i < cap; i++) {
            out[i] = v[i];
            v[i] = NULL;
        }
        if (n > cap) st = OTC_E_BUFFER_TOO_SMALL;
    }
    free_infos(v, n);
    ctx_free(&c);
    return st;
}

otc_status otc_fetch_latest_info(const otc_fetch_options *opts, otc_release_info **info)
{
    fctx c;
    otc_status st = ctx_init(&c, opts);
    if (info) *info = NULL;
    if (st == OTC_OK && !info) st = fail(&c, OTC_E_INVALID_ARGUMENT, NULL, "info is NULL");
    if (st == OTC_OK && c.offline) st = fail(&c, OTC_E_OFFLINE_UNAVAILABLE, NULL, "offline: the latest pointer cannot be read");
    if (st == OTC_OK) st = latest_info(&c, info, NULL);
    ctx_free(&c);
    return st;
}

otc_status otc_fetch_check_for_update(const otc_fetch_options *opts, const char *current, otc_release_info **info,
                                      bool *found)
{
    fctx c;
    otc_release_info *ri = NULL;
    int read_main = 0;
    otc_status st = ctx_init(&c, opts);
    if (info) *info = NULL;
    if (found) *found = false;
    if (st == OTC_OK && (!info || !found || !valid_datestamp(current)))
        st = fail(&c, OTC_E_INVALID_ARGUMENT, NULL, "current must be a datestamp; info and found must not be NULL");
    if (st == OTC_OK && c.offline) st = fail(&c, OTC_E_OFFLINE_UNAVAILABLE, NULL, "offline: the latest pointer cannot be read");
    if (st == OTC_OK) st = latest_info(&c, &ri, &read_main);
    /* spec 7.4 (CR D10): the OTC_latest.json check is made also when the call fails
     * because no release it reads exists, so newer_format_major is set before it fails */
    if ((st == OTC_OK || st == OTC_E_UNSUPPORTED_FORMAT || st == OTC_E_READER_TOO_OLD) && !read_main) {
        otc_error kept = *c.err;
        /* spec 7.4: a conditional GET of OTC_latest.json tells whether a newer
         * format major exists (otc_fetch_newer_format_major reads it back) */
        cJSON *doc = NULL;
        char *url = NULL;
        if (get_changing(&c, "OTC_latest.json", &doc, &url) != OTC_OK)
            logf_(&c, 2, "cannot read OTC_latest.json: %s", c.err->message);
        *c.err = kept;   /* the call's own result stays the one reported */
        cJSON_Delete(doc);
        free(url);
    }
    if (st == OTC_OK || st == OTC_E_UNSUPPORTED_FORMAT || st == OTC_E_READER_TOO_OLD) {
        int major = -1;
        char *dir = pointer_dir(&c), *p = dir ? path2(dir, "OTC_latest.json") : NULL, *t = p ? slurp(p) : NULL;
        cJSON *doc = t ? otc__json_parse(t, strlen(t)) : NULL;
        major = format_major(otc__jstr(doc, "format_version"));
        if (major > OTC_FORMAT_MAJOR)
            logf_(&c, 2, "a newer format (%d) exists; upgrade opentideconstants to read it", major);
        cJSON_Delete(doc);
        free(t);
        free(p);
        free(dir);
    }
    if (st == OTC_OK && ds_cmp(ri->datestamp, current) > 0) {
        *info = ri;
        *found = true;
        ri = NULL;
    }
    otc_release_info_free(ri);
    ctx_free(&c);
    return st;
}

otc_status otc_fetch_newer_format_major(const otc_fetch_options *opts, int *major)
{
    fctx c;
    otc_status st = ctx_init(&c, opts);
    if (major) *major = 0;
    if (st == OTC_OK && !major) st = fail(&c, OTC_E_INVALID_ARGUMENT, NULL, "major is NULL");
    if (st == OTC_OK) {
        char *dir = pointer_dir(&c), *p = dir ? path2(dir, "OTC_latest.json") : NULL, *t = NULL;
        cJSON *doc = NULL;
        int m = -1;
        if (!dir || !p) st = fail(&c, OTC_E_NOMEM, NULL, "out of memory");
        else if (fs_kind(p) != 2)
            st = fail(&c, OTC_E_NOT_FOUND, p, "no newer format major is known: %s is not cached (otc_fetch_check_for_update reads it)", p);
        else if (otc__read_all(p, &t, NULL) != OTC_OK)
            st = fail(&c, OTC_E_IO, p, "cannot read %s", p);
        else if (!(doc = otc__json_parse(t, strlen(t))))
            st = fail(&c, OTC_E_INVALID_RELEASE, p, "%s: not JSON", p);
        else if ((m = format_major(otc__jstr(doc, "format_version"))) < 0)
            st = fail(&c, OTC_E_INVALID_RELEASE, p, "%s: format_version is missing or not MAJOR.MINOR", p);
        else if (m > OTC_FORMAT_MAJOR) *major = m;
        else st = fail(&c, OTC_E_NOT_FOUND, p, "no newer format major: the latest release has format major %d", m);
        cJSON_Delete(doc);
        free(t);
        free(p);
        free(dir);
    }
    ctx_free(&c);
    return st;
}

otc_status otc_fetch_update(const otc_fetch_options *opts, const char *current, char *path, size_t len,
                            size_t *needed, bool *updated)
{
    fctx c;
    otc_release_info *ri = NULL;
    otc_release *rel = NULL;
    otc_loaded_from lf;
    otc_status st = ctx_init(&c, opts);
    size_t need = 0;
    if (updated) *updated = false;
    if (needed) *needed = 0;
    if (path && len) path[0] = '\0';
    /* path NULL with len 0 is a size query (spec 6.4 buffer rules); path NULL with a length is not */
    if (st == OTC_OK && (!updated || !valid_datestamp(current) || (!path && len)))
        st = fail(&c, OTC_E_INVALID_ARGUMENT, NULL, "current must be a datestamp; updated must be set; path NULL needs len 0");
    if (st == OTC_OK && c.offline) st = fail(&c, OTC_E_OFFLINE_UNAVAILABLE, NULL, "offline: the latest pointer cannot be read");
    if (st == OTC_OK) st = ensure_root(&c);
    if (st == OTC_OK) st = latest_info(&c, &ri, NULL);
    if (st == OTC_OK && ds_cmp(ri->datestamp, current) > 0) {
        /* the path is known before the download: a buffer that cannot hold it downloads nothing */
        char *p = rel_file(&c, ri->datestamp, ".jsonl");
        if (!p) st = fail(&c, OTC_E_NOMEM, NULL, "out of memory");
        else if (strlen(p) + 1 > len && path) st = copy_path(&c, p, path, len, &need);   /* as much as fits */
        else if (strlen(p) + 1 > len)   /* a size query (path NULL, len 0) */
            st = fail(&c, OTC_E_BUFFER_TOO_SMALL, p, "the path needs %lu bytes", (unsigned long)strlen(p) + 1);
        if (p && needed) *needed = strlen(p) + 1;
        if (st == OTC_OK) {
            st = ensure_cached(&c, ri->datestamp, ri, &rel, &lf);
            otc_close(rel);
        }
        if (st == OTC_OK) st = copy_path(&c, p, path, len, &need);
        if (st == OTC_OK) {
            *updated = true;   /* the new release is in the cache and path names it */
            logf_(&c, 1, "updated from %s to %s", current, ri->datestamp);
        }
        free(p);
    }
    otc_release_info_free(ri);
    ctx_free(&c);
    return st;
}

/* Returns a malloc'd string list entry. */
static otc_status put_string(fctx *c, char **out, size_t cap, size_t i, const char *s)
{
    if (i >= cap) return OTC_OK;
    out[i] = otc__strdup(s);
    return out[i] ? OTC_OK : fail(c, OTC_E_NOMEM, NULL, "out of memory");
}

otc_status otc_fetch_cached_releases(const otc_fetch_options *opts, char **datestamps, size_t cap, size_t *count)
{
    fctx c;
    char **list = NULL;
    size_t n = 0, i;
    otc_status st = ctx_init(&c, opts);
    if (count) *count = 0;
    if (st == OTC_OK && (!count || (cap && !datestamps))) st = fail(&c, OTC_E_INVALID_ARGUMENT, NULL, "count is NULL");
    if (st == OTC_OK) st = cached_list(&c, &list, &n);
    for (i = 0; st == OTC_OK && i < n; i++) st = put_string(&c, datestamps, cap, i, list[i]);
    if (st == OTC_OK) {
        *count = n;
        if (n > cap) st = OTC_E_BUFFER_TOO_SMALL;
    } else if (datestamps) {   /* a failure hands the caller nothing to free */
        size_t j;
        for (j = 0; j < i && j < cap; j++) {
            free(datestamps[j]);
            datestamps[j] = NULL;
        }
    }
    free_list(list, n);
    ctx_free(&c);
    return st;
}

otc_status otc_fetch_prune(const otc_fetch_options *opts, size_t keep, const char *current, char **removed, size_t cap,
                           size_t *count)
{
    fctx c;
    char **list = NULL;
    size_t n = 0, i, k = 0;
    otc_status st = ctx_init(&c, opts);
    if (count) *count = 0;
    if (st == OTC_OK && (!count || (cap && !removed))) st = fail(&c, OTC_E_INVALID_ARGUMENT, NULL, "count is NULL");
    if (st == OTC_OK) st = cached_list(&c, &list, &n);
    for (i = keep; st == OTC_OK && i < n; i++) {
        char *d, *v, *name = NULL, token[33];
        int held = 0, rm;
        if (current && !strcmp(current, list[i])) continue;
        d = rel_dir(&c, list[i]);
        v = d ? path2(d, ".verified") : NULL;
        /* the name the caller gets is allocated before the delete, so a release is never
         * removed and then left out of the list for want of memory (R2-025) */
        if (d && v && k < cap) name = otc__strdup(list[i]);
        if (!d || !v || (k < cap && !name)) { free(d); free(v); st = fail(&c, OTC_E_NOMEM, NULL, "out of memory"); break; }
        /* a release whose .lock another process holds (a download or an index build) is
         * left alone; with the lock taken, the removal below takes the lock with it */
        if ((st = lock_try(&c, d, &held, token)) != OTC_OK || !held) {
            if (st == OTC_OK) logf_(&c, 1, "not pruning %s: another process holds its lock", list[i]);
            free(name);
            free(d);
            free(v);
            continue;
        }
        /* readers stop trusting it first; a release whose .verified cannot be removed is left whole */
        if (fs_unlink(v) != 0 && fs_kind_nofollow(v) != 0) {
            st = fail(&c, OTC_E_CACHE, d, "cannot remove the cached release %s (%s)", list[i], d);
            lock_release(&c, d, token);
        } else if ((rm = fs_rm_rf(d)) != 0) {
            /* .verified is gone, so the release is no longer listed; the rest is left over */
            st = rm == -2 ? fail(&c, OTC_E_NOMEM, d, "out of memory while removing %s", d)
                          : fail(&c, OTC_E_CACHE, d, "cannot remove the cached release %s (%s)", list[i], d);
            lock_release(&c, d, token);
        } else {
            logf_(&c, 1, "pruned %s", list[i]);
            if (k < cap) removed[k] = name;
            name = NULL;
            k++;
        }
        free(name);
        free(d);
        free(v);
    }
    if (count) *count = k;   /* the releases removed; on a failure, those removed before it */
    if (st == OTC_OK && k > cap) st = OTC_E_BUFFER_TOO_SMALL;
    free_list(list, n);
    ctx_free(&c);
    return st;
}

/* ------------------------------------------------------------- otc_fetch_to_dir */

static otc_status file_sha(const char *path, char hex[65]) { return otc__sha256_file(path, hex); }

static void add_changed(char *buf, size_t cap, const char *path)
{
    size_t used = strlen(buf);
    if (used < cap) snprintf(buf + used, cap - used, "%s%s", used ? ", " : "", path);
}

/* spec 4.3.2 (CR2 DR17): renames staged[i] to dest[i] for every i, all or nothing. Each
 * original that a new file replaces is first renamed aside to <dir>/.tmp-bak-*. If any
 * rename fails, every original is restored and the new files renamed in are removed, so
 * dir is as it was: OTC_E_IO. If a restore fails too, the message lists the paths that
 * changed (an original that is not back stays in its .tmp-bak- file). */
static otc_status rename_all_in(fctx *c, const char *dir, char *const *staged, char *const *dest, size_t n)
{
    char *bak[8], changed[400];
    const char *bad = NULL;
    size_t i, placed = 0;
    otc_status st = OTC_OK;
    memset(bak, 0, sizeof bak);
    changed[0] = '\0';
    for (i = 0; i < n && st == OTC_OK; i++) {
        if (fs_kind_nofollow(dest[i]) != 2) continue;   /* nothing there, or a directory: its rename below fails */
        bak[i] = tmp_path_p(dir, ".tmp-bak-");
        if (!bak[i]) {
            st = fail(c, OTC_E_NOMEM, NULL, "out of memory");
        } else if (fs_rename(dest[i], bak[i]) != 0) {
            free(bak[i]);
            bak[i] = NULL;
            bad = dest[i];
            st = OTC_E_IO;
        }
    }
    for (i = 0; i < n && st == OTC_OK; i++) {
        if (fs_rename(staged[i], dest[i]) != 0) {
            bad = dest[i];
            st = OTC_E_IO;
        } else {
            placed = i + 1;
        }
    }
    if (st == OTC_OK) {
        for (i = 0; i < n; i++) {
            if (bak[i] && fs_unlink(bak[i]) != 0)   /* the new file is in place; only the old copy is left over */
                logf_(c, 2, "download: cannot remove %s (the replaced %s)", bak[i], dest[i]);
            free(bak[i]);
        }
        return OTC_OK;
    }
    for (i = placed; i-- > 0;) {   /* the new files that went in: put the original back, or remove the file */
        if (bak[i] ? fs_rename(bak[i], dest[i]) != 0 : fs_unlink(dest[i]) != 0) {
            logf_(c, 2, "download: cannot restore %s", dest[i]);
            add_changed(changed, sizeof changed, dest[i]);
        }
        free(bak[i]);
        bak[i] = NULL;
    }
    for (i = 0; i < n; i++) {   /* the originals set aside whose new file never went in */
        if (bak[i] && fs_rename(bak[i], dest[i]) != 0) {
            logf_(c, 2, "download: cannot restore %s from %s", dest[i], bak[i]);
            add_changed(changed, sizeof changed, dest[i]);
        }
        free(bak[i]);
    }
    if (st != OTC_E_IO) return st;
    if (changed[0])
        return fail(c, OTC_E_IO, bad, "cannot write %s; these paths changed and could not be restored: %s (an original that "
                    "is not back is in a .tmp-bak- file next to it)", bad, changed);
    return fail(c, OTC_E_IO, bad, "cannot write %s", bad);
}

otc_status otc_fetch_to_dir(const otc_fetch_options *opts, const char *release, const char *dir, unsigned formats,
                            bool overwrite, char **paths, size_t cap, size_t *count)
{
    static const struct { unsigned bit; const char *ext; } FMT[] = {
        {OTC_FORMAT_JSON, ".json"}, {OTC_FORMAT_JSON_GZ, ".json.gz"}, {OTC_FORMAT_JSONL, ".jsonl"}, {0, NULL}};
    fctx c;
    otc_release_info *info = NULL;
    char *ds = NULL, *cdir = NULL, *sha_body = NULL, **names = NULL, **digests = NULL, *todo_name[8], *staged[8], *dests[8];
    char sha_digest[65], targets[8][NAME_CAP];
    const char *target_sha[8];
    size_t n_rows = 0, n_t = 0, n_todo = 0, i, written = 0, sha_len = 0;
    int cached = 0;
    otc_status st = ctx_init(&c, opts);
    if (count) *count = 0;
    memset(todo_name, 0, sizeof todo_name);
    memset(staged, 0, sizeof staged);
    memset(dests, 0, sizeof dests);
    if (st != OTC_OK) goto out;
    if (!count || !dir || (cap && !paths)) { st = fail(&c, OTC_E_INVALID_ARGUMENT, NULL, "dir and count must not be NULL"); goto out; }
    if (formats == OTC_FORMATS_DEFAULT) formats = OTC_FORMAT_JSONL;
    if (formats == 0) {   /* CR 4c: no format named */
        st = fail(&c, OTC_E_INVALID_ARGUMENT, NULL,
                  "formats is empty: name at least one of json, json.gz or jsonl, or pass OTC_FORMATS_DEFAULT");
        goto out;
    }
    if (formats & ~(unsigned)(OTC_FORMAT_JSON | OTC_FORMAT_JSON_GZ | OTC_FORMAT_JSONL)) {
        st = fail(&c, OTC_E_INVALID_ARGUMENT, NULL, "unknown format (use json, json.gz or jsonl)");
        goto out;
    }
    if (release && strcmp(release, "latest") != 0 && !valid_datestamp(release)) {
        st = fail(&c, OTC_E_INVALID_ARGUMENT, NULL, "release must be 'latest' or a datestamp, not '%s'", release);
        goto out;
    }
    /* which release */
    if (!release || !strcmp(release, "latest")) {
        if (c.offline) {
            if ((st = newest_cached(&c, &ds)) != OTC_OK) goto out;
            if (!ds) { st = fail(&c, OTC_E_OFFLINE_UNAVAILABLE, NULL, "offline, and no release is in the cache"); goto out; }
        } else {
            st = latest_info(&c, &info, NULL);
            if (st == OTC_E_NETWORK && !c.raise) {
                /* spec 4.3.2 (CR D22): use_cache writes the newest cached readable release */
                otc_error net = *c.err;
                if (newest_cached(&c, &ds) != OTC_OK || !ds) { *c.err = net; goto out; }
                logf_(&c, 2, "network error (%s); writing the cached release %s", net.message, ds);
                otc_error_init(c.err);
                st = OTC_OK;
            } else if (st != OTC_OK) {
                goto out;
            } else {
                ds = otc__strdup(info->datestamp);
            }
        }
    } else {
        ds = otc__strdup(release);
    }
    if (!ds) { st = fail(&c, OTC_E_NOMEM, NULL, "out of memory"); goto out; }
    /* the .sha256 list: from the cache if the release is verified there, else from the server */
    cdir = rel_dir(&c, ds);
    if (!cdir) { st = fail(&c, OTC_E_NOMEM, NULL, "out of memory"); goto out; }
    {
        cJSON *v = read_verified(&c, ds);
        char *sp = rel_file(&c, ds, ".sha256");
        if (v && sp && fs_kind(sp) == 2) {
            cached = 1;
            if (otc__read_all(sp, &sha_body, &sha_len) != OTC_OK) cached = 0;
        }
        cJSON_Delete(v);
        free(sp);
    }
    if (!cached) {
        char name[NAME_CAP], *url;
        http_resp r;
        int res;
        if (c.offline) { st = fail(&c, OTC_E_OFFLINE_UNAVAILABLE, NULL, "offline, and release %s is not in the cache", ds); goto out; }
        snprintf(name, sizeof name, "OTC_%s.sha256", ds);
        {
            const otc_file_info *pf = info_file(info, name);
            url = (pf && pf->url) ? otc__strdup(pf->url) : url_resolve(c.base_url, name);
        }
        if (!url) { st = fail(&c, OTC_E_NOMEM, NULL, "out of memory"); goto out; }
        memset(&r, 0, sizeof r);
        st = http_get(&c, url, NULL, 1, NULL, &r, &res);
        if (st == OTC_OK && res == GET_NOT_FOUND) st = fail(&c, OTC_E_RELEASE_NOT_FOUND, url, "release %s not found (%s)", ds, url);
        if (st == OTC_OK) {
            sha_len = r.len;
            sha_body = r.body ? (char *)r.body : otc__strdup("");
            r.body = NULL;
            if (!sha_body) st = fail(&c, OTC_E_NOMEM, NULL, "out of memory");
        }
        resp_free(&r);
        free(url);
        if (st != OTC_OK) goto out;
    }
    if ((st = otc__sha256_rows_text(sha_body, &names, &digests, &n_rows)) != OTC_OK) {
        if (st == OTC_E_INVALID_RELEASE) fail(&c, st, NULL, "%s OTC_%s.sha256", otc__sha256_rows_what(st), ds);
        else fail(&c, st, NULL, "out of memory");
        goto out;
    }
    if (!cached && n_rows == 0) {   /* CR2 DR13: a 200 with no "<sha256>  <name>" row stands in for the network */
        st = fail(&c, OTC_E_NETWORK, NULL, "OTC_%s.sha256: the 200 response has no \"<sha256>  <name>\" row (a captive portal or proxy page?)",
                  ds);
        if (c.err) c.err->http_status = 200;
        goto out;
    }
    {
        struct Sha_256 s;
        uint8_t h[SIZE_OF_SHA_256_HASH];
        char sums_name[NAME_CAP];
        sha_256_init(&s, h);
        sha_256_write(&s, sha_body, sha_len);
        sha_256_close(&s);
        hex_of(h, sha_digest);
        snprintf(sums_name, sizeof sums_name, "OTC_%s.sha256", ds);
        if ((st = check_pointer(&c, info, names, digests, n_rows, sums_name, sha_digest)) != OTC_OK) goto out;
    }
    /* the targets: the formats asked for, the .meta.json, then the .sha256 */
    for (i = 0; FMT[i].ext; i++) {
        if (!(formats & FMT[i].bit)) continue;
        snprintf(targets[n_t], sizeof targets[n_t], "OTC_%s%s", ds, FMT[i].ext);
        n_t++;
    }
    snprintf(targets[n_t++], sizeof targets[0], "OTC_%s.meta.json", ds);
    for (i = 0; i < n_t; i++) {
        target_sha[i] = row_of(names, digests, n_rows, targets[i]);
        if (!target_sha[i]) { st = fail(&c, OTC_E_RELEASE_NOT_FOUND, targets[i], "%s is not part of release %s", targets[i], ds); goto out; }
    }
    snprintf(targets[n_t], sizeof targets[0], "OTC_%s.sha256", ds);
    target_sha[n_t++] = sha_digest;
    /* check every existing file before writing any file */
    for (i = 0; i < n_t; i++) {
        char *p = path2(dir, targets[i]), hex[65];
        if (!p) { st = fail(&c, OTC_E_NOMEM, NULL, "out of memory"); goto out; }
        if (fs_kind(p) == 2) {
            otc_status hs = file_sha(p, hex);
            if (hs != OTC_OK) {   /* a file that cannot be read is that error, not "a different SHA-256" */
                st = fail(&c, hs == OTC_E_NOMEM ? hs : OTC_E_IO, p, "cannot read %s", p);
                free(p);
                goto out;
            }
            if (!strcmp(hex, target_sha[i])) { free(p); continue; }
            if (!overwrite) {
                st = fail(&c, OTC_E_FILE_EXISTS, p, "%s exists with a different SHA-256", p);
                free(p);
                goto out;
            }
        }
        free(p);
        todo_name[n_todo++] = targets[i];
    }
    {
        int m = fs_mkdir_p(dir);
        if (m != 0) {
            st = m == -2 ? fail(&c, OTC_E_NOMEM, NULL, "out of memory") : fail(&c, OTC_E_IO, dir, "cannot create %s", dir);
            goto out;
        }
    }
    /* spec 4.3.2 "check, then rename": every file goes to a temporary file in dir first;
     * only when all of them are there and checked are they renamed into place, all or
     * nothing (CR2 DR17), so a failure (network, offline, checksum, a rename) leaves dir
     * as it was */
    for (i = 0; i < n_todo; i++) {
        const char *name = todo_name[i];
        const char *sha = row_of(names, digests, n_rows, name);
        char *src = path2(cdir, name);
        if (!src) { st = fail(&c, OTC_E_NOMEM, NULL, "out of memory"); goto out; }
        if (otc__ends_with(name, ".sha256")) {
            st = write_tmp(&c, dir, sha_body, sha_len, &staged[i]);
        } else if (cached && fs_kind(src) == 2) {
            char hex[65];
            st = copy_to_tmp(&c, src, dir, &staged[i], hex);
            if (st == OTC_OK && strcmp(hex, sha) != 0)
                st = fail_checksum(&c, name, sha, hex, "the cached copy does not match");
        } else if (c.offline) {
            st = fail(&c, OTC_E_OFFLINE_UNAVAILABLE, NULL, "offline, and %s is not in the cache", name);
        } else {
            const otc_file_info *pf = info_file(info, name);
            char *url = (pf && pf->url) ? otc__strdup(pf->url) : url_resolve(c.base_url, name);
            st = url ? fetch_file(&c, url, dir, name, sha, pf ? pf->size : -1, &staged[i])
                     : fail(&c, OTC_E_NOMEM, NULL, "out of memory");
            free(url);
        }
        if (st == OTC_E_CACHE) st = fail(&c, OTC_E_IO, dir, "cannot write into %s", dir);   /* the folder is the caller's */
        free(src);
        if (st != OTC_OK) goto out;
    }
    for (i = 0; i < n_todo; i++) {
        dests[i] = path2(dir, todo_name[i]);
        if (!dests[i]) { st = fail(&c, OTC_E_NOMEM, NULL, "out of memory"); goto out; }
    }
    /* all or nothing (CR2 DR17): a failure here leaves dir as it was */
    if ((st = rename_all_in(&c, dir, staged, dests, n_todo)) != OTC_OK) goto out;
    for (i = 0; i < n_todo; i++) {
        free(staged[i]);
        staged[i] = NULL;
        if (written < cap) paths[written] = dests[i];
        else free(dests[i]);
        dests[i] = NULL;
        written++;
    }
    *count = written;
    if (written > cap) st = OTC_E_BUFFER_TOO_SMALL;
out:
    for (i = 0; i < 8; i++) {   /* a failure leaves no temporary file behind */
        if (staged[i]) fs_unlink(staged[i]);
        free(staged[i]);
        free(dests[i]);
    }
    if (st != OTC_OK && st != OTC_E_BUFFER_TOO_SMALL) {   /* nothing is reported on a failure */
        for (i = 0; i < written && i < cap; i++) {
            free(paths[i]);
            paths[i] = NULL;
        }
    }
    otc__free_rows(names, digests, n_rows);
    otc_release_info_free(info);
    free(sha_body);
    free(cdir);
    free(ds);
    ctx_free(&c);
    return st;
}
