/*
 * The optional otc_fetch module (SDK spec 4.3, 5, 6.4): downloads releases
 * with libcurl into the cache layout that every SDK on the machine shares
 * (spec 5.4), and writes releases into a folder the app chooses (4.3.2).
 * Built only with -DOTC_WITH_FETCH=ON; otherwise otc_fetch_stub.c is built.
 *
 * Cache: <root>/v1/pointer/{OTC_latest-f0.json,OTC_index.json}(+.etag) and
 * <root>/v1/releases/<D>/{OTC_<D>.sha256,.jsonl,.meta.json,[.json],
 * index-v1.json,.verified}. Every file is written to .tmp-<pid>-<random> in
 * the same directory, fsynced and renamed into place; .verified is last. A
 * .lock/ directory (owner.json inside) only stops duplicate work.
 */
/* fsync, gethostname, nanosleep and gmtime_r are XSI / POSIX 2008 on glibc */
#if !defined(_WIN32) && !defined(_XOPEN_SOURCE)
#define _XOPEN_SOURCE 700
#endif
#include "otc_internal.h"
#include "otc_sha256_rename.h"
#include "sha-256.h"

#include <curl/curl.h>
#include <errno.h>
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
#define ATTEMPTS 3
#define RETRY_AFTER_MAX_S 60.0
#define LOCK_POLL_MS 500
#define LOCK_STALE_MS 120000

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
    int r = w ? _wmkdir(w) : -1;
    int e = errno;
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
    if (!d) return OTC_E_IO;
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

/* rm -r */
static void fs_rm_rf(const char *path)
{
    if (fs_kind(path) == 1) {
        char **names = NULL;
        size_t n = 0, i;
        if (fs_list(path, &names, &n) == OTC_OK) {
            for (i = 0; i < n; i++) {
                char *p = path2(path, names[i]);
                if (p) fs_rm_rf(p);
                free(p);
            }
            free_list(names, n);
        }
        fs_rmdir(path);
    } else {
        fs_unlink(path);
    }
}

/* mkdir -p; 0 when path is a directory afterwards */
static int fs_mkdir_p(const char *path)
{
    char *p = otc__strdup(path);
    size_t i, n;
    int ok;
    if (!p) return -1;
    n = strlen(p);
    while (n > 1 && (p[n - 1] == '/' || p[n - 1] == '\\')) p[--n] = '\0';
    for (i = 1; i < n; i++) {
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
static char *tmp_path(const char *dir)
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
    i = snprintf(name, sizeof name, ".tmp-%ld-", get_pid());
    if (i < 0) return NULL;
    for (c = 0; c < 12; c++) name[i++] = digits[(x >> (4 * c)) & 15];
    name[i] = '\0';
    return path2(dir, name);
}

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
} fctx;

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

static otc_status ctx_init(fctx *c, const otc_fetch_options *o)
{
    const char *v;
    char *root;
    memset(c, 0, sizeof *c);
    init_once();
    otc_error_init(&c->own);
    c->err = &c->own;
    if (o && o->struct_size < sizeof *o) return fail(c, OTC_E_INVALID_ARGUMENT, NULL, "otc_fetch_options: struct_size is too small");
    c->o = o;
    if (o && o->error) c->err = o->error;
    otc_error_init(c->err);
    if (!g_curl_ok) return fail(c, OTC_E_NETWORK, NULL, "curl_global_init failed");
    if (o && o->cache_dir) root = otc__strdup(o->cache_dir);
    else if ((v = env_get("OPENTIDECONSTANTS_CACHE_DIR")) != NULL) root = otc__strdup(v);
    else root = default_root();
    if (!root) return fail(c, OTC_E_CACHE, NULL, "no cache directory: set cache_dir or OPENTIDECONSTANTS_CACHE_DIR");
    c->base = path2(root, LAYOUT);
    free(root);
    v = (o && o->base_url) ? o->base_url : env_get("OPENTIDECONSTANTS_BASE_URL");
    c->base_url = otc__strdup(v ? v : DEFAULT_BASE_URL);
    if (!c->base || !c->base_url) return fail(c, OTC_E_NOMEM, NULL, "out of memory");
    v = env_get("OPENTIDECONSTANTS_OFFLINE");
    c->offline = (o && o->offline) || (v && !strcmp(v, "1"));
    c->formats = (o && o->formats) ? o->formats : (unsigned)OTC_FORMAT_JSONL;
    if (c->formats & ~(unsigned)(OTC_FORMAT_JSON | OTC_FORMAT_JSON_GZ | OTC_FORMAT_JSONL))
        return fail(c, OTC_E_INVALID_ARGUMENT, NULL, "formats: unknown bits");
    c->connect_s = (o && o->timeout_s > 0) ? o->timeout_s : CONNECT_TIMEOUT_S;
    c->read_s = (o && o->timeout_s > 0) ? o->timeout_s : READ_TIMEOUT_S;
    c->raise = o && o->on_network_error == OTC_ON_NETWORK_ERROR_RAISE;
    return OTC_OK;
}

static void ctx_free(fctx *c)
{
    free(c->base);
    free(c->base_url);
}

/* ------------------------------------------------------------------ datestamps */

/* ^[0-9]{8}(\.[2-9]|\.[1-9][0-9]+)?$ */
static int valid_datestamp(const char *s)
{
    size_t i, n;
    if (!s) return 0;
    n = strlen(s);
    if (n < 8) return 0;
    for (i = 0; i < 8; i++)
        if (s[i] < '0' || s[i] > '9') return 0;
    if (n == 8) return 1;
    if (s[8] != '.' || n < 10) return 0;
    for (i = 9; i < n; i++)
        if (s[i] < '0' || s[i] > '9') return 0;
    if (n == 10) return s[9] >= '2';
    return s[9] != '0';
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

/* The major of "MAJOR.MINOR", or -1. */
static int format_major(const char *fv)
{
    char *end;
    long m;
    if (!fv || !strchr(fv, '.') || fv[0] < '0' || fv[0] > '9') return -1;
    m = strtol(fv, &end, 10);
    return (*end == '.' && m >= 0 && m < 1000000) ? (int)m : -1;
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
        if (end != buf && d >= 0) r->retry_after = d;
    }
    return n;
}

static const char *proxy_env(int https)
{
    const char *v = https ? env_get("https_proxy") : env_get("http_proxy");
    if (!v) v = https ? env_get("HTTPS_PROXY") : env_get("HTTP_PROXY");
    return v;
}

enum { GET_OK = 0, GET_NOT_MODIFIED, GET_NOT_FOUND };

/*
 * GET url with the retries of spec 5.7 (3 attempts on connection errors, 5xx
 * and 429; waits of 1 s and 2 s, or Retry-After up to 60 s). 304 and 404 are
 * results, never retried. With sink_path the decoded body streams into that
 * file (fsynced); otherwise it is kept in r->body. r->hex and r->size
 * describe the decoded body.
 */
static otc_status http_get(fctx *c, const char *url, const char *if_none_match, int accept_gzip,
                           const char *sink_path, http_resp *r, int *result)
{
    static const double backoff[2] = {1.0, 2.0};
    char ua[512], errbuf[CURL_ERROR_SIZE], inm[300];
    int attempt, https = !strncmp(url, "https://", 8);
    long last_status = 0;
    char last_msg[512];
    const char *proxy = (c->o && c->o->proxy) ? c->o->proxy : proxy_env(https);
    const char *noproxy = (c->o && c->o->proxy) ? "" : (env_get("no_proxy") ? env_get("no_proxy") : env_get("NO_PROXY"));
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
        int retry = 0;
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
        curl_easy_setopt(h, CURLOPT_URL, url);
        curl_easy_setopt(h, CURLOPT_USERAGENT, ua);
        curl_easy_setopt(h, CURLOPT_NOSIGNAL, 1L);
        curl_easy_setopt(h, CURLOPT_FOLLOWLOCATION, 1L);
        curl_easy_setopt(h, CURLOPT_MAXREDIRS, 5L);
        curl_easy_setopt(h, CURLOPT_CONNECTTIMEOUT_MS, (long)(c->connect_s * 1000.0));
        curl_easy_setopt(h, CURLOPT_LOW_SPEED_LIMIT, 1L);
        curl_easy_setopt(h, CURLOPT_LOW_SPEED_TIME, (long)(c->read_s + 0.999));
        curl_easy_setopt(h, CURLOPT_ERRORBUFFER, errbuf);
        curl_easy_setopt(h, CURLOPT_WRITEFUNCTION, on_body);
        curl_easy_setopt(h, CURLOPT_WRITEDATA, r);
        curl_easy_setopt(h, CURLOPT_HEADERFUNCTION, on_header);
        curl_easy_setopt(h, CURLOPT_HEADERDATA, r);
        if (accept_gzip) curl_easy_setopt(h, CURLOPT_ACCEPT_ENCODING, "gzip");
        else hdrs = curl_slist_append(hdrs, "Accept-Encoding: identity");
        if (if_none_match && if_none_match[0]) {
            snprintf(inm, sizeof inm, "If-None-Match: %s", if_none_match);
            hdrs = curl_slist_append(hdrs, inm);
        }
        if (hdrs) curl_easy_setopt(h, CURLOPT_HTTPHEADER, hdrs);
        if (proxy) curl_easy_setopt(h, CURLOPT_PROXY, proxy);
        else curl_easy_setopt(h, CURLOPT_PROXY, "");
        if (noproxy) curl_easy_setopt(h, CURLOPT_NOPROXY, noproxy);
        if (ca) curl_easy_setopt(h, CURLOPT_CAINFO, ca);
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
        fclose(in);
        if (out) fclose(out);
        free(buf);
        free(tmp);
        return fail(c, buf ? OTC_E_IO : OTC_E_NOMEM, dir, "cannot write into %s", dir);
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

/* Takes <dir>/.lock (spec 5.4). *held = 0 when done() became true while waiting. */
static otc_status lock_take(fctx *c, const char *dir, const char *ds, done_fn done, int *held)
{
    char *lock = path2(dir, ".lock");
    long waited = 0;
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
        if (done && done(c, ds)) break;
        if (waited >= LOCK_STALE_MS) {
            logf_(c, 2, "removing the stale lock %s", lock);
            fs_rm_rf(lock);
            waited = 0;
            continue;
        }
        sleep_ms(LOCK_POLL_MS);
        waited += LOCK_POLL_MS;
    }
    if (*held) {
        char *owner = path2(lock, "owner.json");
        FILE *f = owner ? fs_fopen(owner, "wb") : NULL;
        if (f) {
            char host[256] = "";
            char when[32];
            time_t now = time(NULL);
            struct tm tmv;
#ifdef _WIN32
            DWORD hl = (DWORD)sizeof host;
            if (!GetComputerNameA(host, &hl)) host[0] = '\0';
            gmtime_s(&tmv, &now);
#else
            if (gethostname(host, sizeof host - 1) != 0) host[0] = '\0';
            host[sizeof host - 1] = '\0';
            gmtime_r(&now, &tmv);
#endif
            strftime(when, sizeof when, "%Y-%m-%dT%H:%M:%SZ", &tmv);
            {
                cJSON *o = cJSON_CreateObject();
                char *txt;
                cJSON_AddNumberToObject(o, "pid", (double)get_pid());
                cJSON_AddStringToObject(o, "host", host);
                cJSON_AddStringToObject(o, "sdk", SDK_ID);
                cJSON_AddStringToObject(o, "started_at", when);
                txt = cJSON_PrintUnformatted(o);
                if (txt) fputs(txt, f);
                cJSON_free(txt);
                cJSON_Delete(o);
            }
            fclose(f);
        }
        free(owner);
    }
    free(lock);
    return OTC_OK;
}

static void lock_release(const char *dir)
{
    char *lock = path2(dir, ".lock"), *owner = lock ? path2(lock, "owner.json") : NULL;
    if (owner) fs_unlink(owner);
    if (lock) fs_rmdir(lock);
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
    const char *ds = otc__jstr(e, "datestamp"), *fv = otc__jstr(e, "format_version"), *doi = otc__jstr(e, "doi");
    size_t n = 0;
    *out = NULL;
    if (!cJSON_IsObject(e) || !ds || !valid_datestamp(ds) || (files && !cJSON_IsArray(files)))
        return fail(c, OTC_E_INVALID_RELEASE, doc_url, "%s: a release entry without a valid datestamp or files", doc_url);
    ri = (otc_release_info *)calloc(1, sizeof *ri);
    if (!ri) return fail(c, OTC_E_NOMEM, NULL, "out of memory");
    ri->datestamp = otc__strdup(ds);
    ri->format_version = fv ? otc__strdup(fv) : NULL;
    ri->doi = doi ? otc__strdup(doi) : NULL;
    ri->files = (otc_file_info *)calloc((size_t)cJSON_GetArraySize(files) + 1, sizeof *ri->files);
    if (!ri->datestamp || (fv && !ri->format_version) || (doi && !ri->doi) || !ri->files) {
        otc_release_info_free(ri);
        return fail(c, OTC_E_NOMEM, NULL, "out of memory");
    }
    cJSON_ArrayForEach(f, files) {
        const char *name = otc__jstr(f, "name"), *u = otc__jstr(f, "url"), *sha = otc__jstr(f, "sha256");
        const cJSON *size = otc__jget(f, "size");
        otc_file_info *fi = &ri->files[n];
        if (!name) {
            ri->n_files = n;
            otc_release_info_free(ri);
            return fail(c, OTC_E_INVALID_RELEASE, doc_url, "%s: a file entry without a name", doc_url);
        }
        fi->name = otc__strdup(name);
        fi->url = url_resolve(doc_url, u ? u : name);
        fi->sha256 = sha ? otc__strdup(sha) : NULL;
        fi->size = cJSON_IsNumber(size) ? (int64_t)size->valuedouble : -1;
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

/* Reads a whole file; NULL if it is missing. */
static char *slurp(const char *path)
{
    char *t = NULL;
    if (fs_kind(path) != 2) return NULL;
    if (otc__read_all(path, &t, NULL) != OTC_OK) return NULL;
    return t;
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
    } else {
        logf_(c, 0, "pointer %s: 200", name);
        free(body);
        body = r.body ? (char *)r.body : otc__strdup("");
        r.body = NULL;
        if (!body) { st = fail(c, OTC_E_NOMEM, NULL, "out of memory"); goto done; }
        if (fs_mkdir_p(dir) != 0) { st = fail(c, OTC_E_CACHE, dir, "cannot create the cache directory %s", dir); goto done; }
        if ((st = write_atomic(c, dir, path, body, strlen(body))) != OTC_OK) goto done;
        if (r.etag[0]) st = write_atomic(c, dir, etag_path, r.etag, strlen(r.etag));
        else fs_unlink(etag_path);
        if (st != OTC_OK) goto done;
    }
    *doc = otc__json_parse(body, strlen(body));
    if (!*doc) { st = fail(c, OTC_E_INVALID_RELEASE, url, "%s: not JSON", url); goto done; }
    *doc_url = url;
    url = NULL;
done:
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

/* The newest release with a supported format major (spec 5.2 step 2, 7.4). */
static otc_status latest_info(fctx *c, otc_release_info **out)
{
    char name[64];
    cJSON *doc = NULL;
    char *url = NULL;
    otc_release_info *ri = NULL, **all = NULL;
    size_t n = 0, i;
    otc_status st;
    *out = NULL;
    snprintf(name, sizeof name, "OTC_latest-f%d.json", OTC_FORMAT_MAJOR);
    st = get_changing(c, name, &doc, &url);
    if (st == OTC_OK && !doc) st = get_changing(c, "OTC_latest.json", &doc, &url);
    if (st != OTC_OK) return st;
    if (!doc) return fail(c, OTC_E_RELEASE_NOT_FOUND, NULL, "no latest pointer under %s", c->base_url);
    st = info_from_entry(c, doc, url, &ri);
    cJSON_Delete(doc);
    free(url);
    if (st != OTC_OK) return st;
    if (format_major(ri->format_version) == OTC_FORMAT_MAJOR) { *out = ri; return OTC_OK; }
    logf_(c, 2, "a newer format (%s) exists; upgrade the library to read it", ri->format_version ? ri->format_version : "?");
    otc_release_info_free(ri);
    st = fetch_index(c, &all, &n);
    if (st == OTC_E_RELEASE_NOT_FOUND) { st = OTC_OK; n = 0; }
    if (st != OTC_OK) return st;
    for (i = 0; i < n; i++) {
        if (format_major(all[i]->format_version) == OTC_FORMAT_MAJOR) {
            *out = all[i];
            all[i] = NULL;
            break;
        }
    }
    free_infos(all, n);
    if (!*out) return fail(c, OTC_E_UNSUPPORTED_FORMAT, NULL, "no release with the supported format major %d", OTC_FORMAT_MAJOR);
    if (c->err) otc_error_init(c->err);
    return OTC_OK;
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
    char name[64], *d = rel_dir(c, ds), *p;
    if (!d) return NULL;
    snprintf(name, sizeof name, "OTC_%s%s", ds, suffix);
    p = path2(d, name);
    free(d);
    return p;
}

static cJSON *read_verified(fctx *c, const char *ds)
{
    char *d = rel_dir(c, ds), *p = d ? path2(d, ".verified") : NULL, *t = p ? slurp(p) : NULL;
    cJSON *doc = t ? otc__json_parse(t, strlen(t)) : NULL;
    free(d);
    free(p);
    free(t);
    if (doc && !cJSON_IsObject(otc__jget(doc, "files"))) { cJSON_Delete(doc); doc = NULL; }
    return doc;
}

static int file_there(fctx *c, const char *ds, const char *suffix)
{
    char *p = rel_file(c, ds, suffix);
    int r = p && fs_kind(p) == 2;
    free(p);
    return r;
}

/* A verified release whose .jsonl and .meta.json are there (and .json when strict and asked for). */
static int usable_impl(fctx *c, const char *ds, int strict)
{
    cJSON *v = read_verified(c, ds);
    int ok = v && file_there(c, ds, ".jsonl") && file_there(c, ds, ".meta.json");
    if (ok && strict && (c->formats & OTC_FORMAT_JSON)) ok = file_there(c, ds, ".json");
    cJSON_Delete(v);
    return ok;
}
static int usable_strict(fctx *c, const char *ds) { return usable_impl(c, ds, 1); }
static int usable_loose(fctx *c, const char *ds) { return usable_impl(c, ds, 0); }

/* Datestamps of verified cached releases, newest first. */
static otc_status cached_list(fctx *c, char ***out, size_t *n_out)
{
    char *r = path2(c->base, "releases"), **names = NULL;
    size_t n = 0, i, k = 0;
    *out = NULL;
    *n_out = 0;
    if (!r) return fail(c, OTC_E_NOMEM, NULL, "out of memory");
    if (fs_kind(r) != 1 || fs_list(r, &names, &n) != OTC_OK) { free(r); return OTC_OK; }
    free(r);
    for (i = 0; i < n; i++) {
        cJSON *v = valid_datestamp(names[i]) ? read_verified(c, names[i]) : NULL;
        if (v) names[k++] = names[i];
        else free(names[i]);
        cJSON_Delete(v);
    }
    if (k > 1) qsort(names, k, sizeof *names, ds_cmp_desc);
    *out = names;
    *n_out = k;
    return OTC_OK;
}

/* The newest cached release that C can open, with a supported format major. */
static char *newest_cached(fctx *c)
{
    char **list = NULL, *best = NULL;
    size_t n = 0, i;
    if (cached_list(c, &list, &n) != OTC_OK) return NULL;
    for (i = 0; i < n && !best; i++) {
        cJSON *v;
        const char *fv;
        if (!usable_loose(c, list[i])) continue;
        v = read_verified(c, list[i]);
        fv = otc__jstr(v, "format_version");
        if (!fv || format_major(fv) == OTC_FORMAT_MAJOR) best = otc__strdup(list[i]);
        cJSON_Delete(v);
    }
    free_list(list, n);
    return best;
}

/* release.files from .verified (spec 4.3.1), sorted by name. */
static otc_status files_from_verified(fctx *c, const char *ds, otc_file_info **out, size_t *n_out)
{
    cJSON *v = read_verified(c, ds);
    const cJSON *files = otc__jget(v, "files"), *f;
    otc_file_info *arr;
    size_t n = 0;
    *out = NULL;
    *n_out = 0;
    if (!v) return fail(c, OTC_E_CACHE, NULL, "release %s has no .verified record", ds);
    arr = (otc_file_info *)calloc((size_t)cJSON_GetArraySize(files) + 1, sizeof *arr);
    if (!arr) { cJSON_Delete(v); return fail(c, OTC_E_NOMEM, NULL, "out of memory"); }
    cJSON_ArrayForEach(f, files) {
        const char *u = otc__jstr(f, "url"), *sha = otc__jstr(f, "sha256");
        const cJSON *size = otc__jget(f, "size");
        arr[n].name = otc__strdup(f->string);
        arr[n].url = u ? otc__strdup(u) : NULL;
        arr[n].sha256 = sha ? otc__strdup(sha) : NULL;
        arr[n].size = cJSON_IsNumber(size) ? (int64_t)size->valuedouble : -1;
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
    cJSON *v = read_verified(c, ds);
    const cJSON *files = otc__jget(v, "files");
    size_t i;
    otc_status st = OTC_OK;
    for (i = 0; suffixes[i] && st == OTC_OK; i++) {
        char name[64], *p = rel_file(c, ds, suffixes[i]);
        const cJSON *rec, *size;
        snprintf(name, sizeof name, "OTC_%s%s", ds, suffixes[i]);
        rec = otc__jget(files, name);
        size = otc__jget(rec, "size");
        if (p && cJSON_IsNumber(size) && otc__path_size(p) != (int64_t)size->valuedouble)
            st = fail_checksum(c, p, otc__jstr(rec, "sha256"), "", "the size does not match .verified");
        free(p);
    }
    cJSON_Delete(v);
    return st;
}

/* ------------------------------------------------------------- stream index */

typedef struct ix_item {
    uint64_t offset;
    cJSON   *json;
} ix_item;

static int ix_cmp(const void *a, const void *b)
{
    uint64_t x = ((const ix_item *)a)->offset, y = ((const ix_item *)b)->offset;
    return x < y ? -1 : x > y;
}

static cJSON *num_or_null(double v) { return isnan(v) ? cJSON_CreateNull() : cJSON_CreateNumber(v); }
static cJSON *str_or_null(const char *s) { return s ? cJSON_CreateString(s) : cJSON_CreateNull(); }

/*
 * index-v1.json (spec 6.2): one entry per line of the .jsonl, in file order,
 * with its byte offset and length, station_id, status, folded name, country,
 * type, kind, lat, lon, aliases and reference_station_id. The C library
 * builds its index in memory at every open and does not read this file; it
 * writes it for the other SDKs, only when it is missing or its jsonl_sha256
 * is stale. A failure to write it is logged, not raised.
 */
static void write_stream_index(fctx *c, const char *ds, const otc_release *rel, const char *jsonl_sha)
{
    char *d = rel_dir(c, ds), *p = d ? path2(d, "index-v1.json") : NULL, *old = p ? slurp(p) : NULL, *txt = NULL;
    char jsonl[64];
    ix_item *items = NULL;
    cJSON **aliases = NULL, *doc = NULL, *arr;
    size_t i, n = 0;
    if (!d || !p || !jsonl_sha) goto done;
    if (old) {
        cJSON *o = otc__json_parse(old, strlen(old));
        int fresh = o && otc__jstr(o, "jsonl_sha256") && !strcmp(otc__jstr(o, "jsonl_sha256"), jsonl_sha);
        cJSON_Delete(o);
        if (fresh) goto done;
    }
    items = (ix_item *)calloc(rel->n_st + rel->n_tomb + 1, sizeof *items);
    aliases = (cJSON **)calloc(rel->n_st + 1, sizeof *aliases);
    if (!items || !aliases) goto done;
    for (i = 0; i < rel->n_st; i++) aliases[i] = cJSON_CreateObject();
    for (i = 0; i < rel->n_alias; i++) {
        const otc__entry *e = otc__find_entry(rel, rel->alias[i].station);
        cJSON *obj, *list;
        if (!e) continue;
        obj = aliases[e - rel->st];
        list = cJSON_GetObjectItemCaseSensitive(obj, rel->alias[i].system);
        if (!list) {
            list = cJSON_CreateArray();
            cJSON_AddItemToObject(obj, rel->alias[i].system, list);
        }
        cJSON_AddItemToArray(list, cJSON_CreateString(rel->alias[i].alias));
    }
    for (i = 0; i < rel->n_st; i++) {
        const otc__entry *e = &rel->st[i];
        cJSON *o = cJSON_CreateObject();
        cJSON_AddStringToObject(o, "station_id", e->id);
        cJSON_AddStringToObject(o, "status", "active");
        cJSON_AddNumberToObject(o, "offset", (double)e->offset);
        cJSON_AddNumberToObject(o, "length", (double)e->length);
        cJSON_AddItemToObject(o, "name_folded", str_or_null(e->folded));
        cJSON_AddItemToObject(o, "country", str_or_null(e->country));
        cJSON_AddItemToObject(o, "type", str_or_null(e->type_s));
        cJSON_AddItemToObject(o, "kind", str_or_null(otc_kind_name(e->kind)));
        cJSON_AddItemToObject(o, "lat", num_or_null(e->lat));
        cJSON_AddItemToObject(o, "lon", num_or_null(e->lon));
        cJSON_AddItemToObject(o, "aliases", aliases[i]);
        aliases[i] = NULL;
        cJSON_AddItemToObject(o, "reference_station_id", str_or_null(e->ref_id));
        items[n].offset = e->offset;
        items[n++].json = o;
    }
    for (i = 0; i < rel->n_tomb; i++) {
        cJSON *o = cJSON_CreateObject();
        cJSON_AddStringToObject(o, "station_id", rel->tomb[i].id);
        cJSON_AddStringToObject(o, "status", "removed");
        cJSON_AddNumberToObject(o, "offset", (double)rel->tomb[i].offset);
        cJSON_AddNumberToObject(o, "length", (double)rel->tomb[i].length);
        items[n].offset = rel->tomb[i].offset;
        items[n++].json = o;
    }
    if (n > 1) qsort(items, n, sizeof *items, ix_cmp);
    doc = cJSON_CreateObject();
    snprintf(jsonl, sizeof jsonl, "OTC_%s.jsonl", ds);
    cJSON_AddNumberToObject(doc, "index_version", 1);
    cJSON_AddStringToObject(doc, "datestamp", ds);
    cJSON_AddStringToObject(doc, "jsonl", jsonl);
    cJSON_AddStringToObject(doc, "jsonl_sha256", jsonl_sha);
    cJSON_AddStringToObject(doc, "by", SDK_ID);
    arr = cJSON_CreateArray();
    for (i = 0; i < n; i++) cJSON_AddItemToArray(arr, items[i].json);
    n = 0;
    cJSON_AddItemToObject(doc, "stations", arr);
    txt = cJSON_PrintUnformatted(doc);
    if (!txt || write_atomic(c, d, p, txt, strlen(txt)) != OTC_OK) {
        logf_(c, 2, "cannot write the stream index %s", p);
        if (c->err) otc_error_init(c->err);
    }
done:
    if (items)
        for (i = 0; i < n; i++) cJSON_Delete(items[i].json);
    if (aliases)
        for (i = 0; i < rel->n_st; i++) cJSON_Delete(aliases[i]);
    free(items);
    free(aliases);
    cJSON_Delete(doc);
    cJSON_free(txt);
    free(d);
    free(p);
    free(old);
}

/* ---------------------------------------------------------- download to cache */

static const char *row_of(char **names, char **digests, size_t n, const char *name)
{
    size_t i;
    for (i = 0; i < n; i++)
        if (!strcmp(names[i], name)) return digests[i];
    return NULL;
}

static otc_status check_pointer(fctx *c, const otc_release_info *info, char **names, char **digests, size_t n)
{
    size_t i;
    if (!info) return OTC_OK;
    for (i = 0; i < info->n_files; i++) {
        const char *row = row_of(names, digests, n, info->files[i].name);
        if (row && info->files[i].sha256 && strcmp(row, info->files[i].sha256) != 0)
            return fail_checksum(c, info->files[i].name, row, info->files[i].sha256,
                                 "the pointer and the .sha256 file disagree");
    }
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
    char **names = NULL, **digests = NULL, sha_name[64];
    size_t n_rows = 0, n_pend = 0, i;
    pending pend[4];
    cJSON *old = NULL, *ver = NULL, *files;
    int held = 0, res;
    http_resp r;
    otc_status st = OTC_OK;
    otc_release *rel = NULL;
    static const char *const want_all[] = {".jsonl", ".meta.json", ".json", NULL};

    *rel_out = NULL;
    memset(&r, 0, sizeof r);
    memset(pend, 0, sizeof pend);
    if (!dir) return fail(c, OTC_E_NOMEM, NULL, "out of memory");
    if (fs_mkdir_p(dir) != 0) { st = fail(c, OTC_E_CACHE, dir, "cannot create the cache directory %s", dir); goto out; }
    if ((st = lock_take(c, dir, ds, usable_strict, &held)) != OTC_OK) goto out;
    if (!held || usable_strict(c, ds)) goto out;   /* another process finished it */

    /* 1. the .sha256 list */
    snprintf(sha_name, sizeof sha_name, "OTC_%s.sha256", ds);
    sha_url = url_resolve(c->base_url, sha_name);
    sha_tmp = tmp_path(dir);
    if (!sha_url || !sha_tmp) { st = fail(c, OTC_E_NOMEM, NULL, "out of memory"); goto out; }
    st = http_get(c, sha_url, NULL, 1, sha_tmp, &r, &res);
    if (st == OTC_OK && res == GET_NOT_FOUND) st = fail(c, OTC_E_RELEASE_NOT_FOUND, sha_url, "release %s not found (%s)", ds, sha_url);
    resp_free(&r);
    if (st != OTC_OK) goto out;
    if ((st = otc__sha256_rows(sha_tmp, &names, &digests, &n_rows)) != OTC_OK) {
        st = fail(c, st == OTC_E_NOMEM ? st : OTC_E_CACHE, sha_tmp, "cannot read %s", sha_tmp);
        goto out;
    }
    if ((st = check_pointer(c, info, names, digests, n_rows)) != OTC_OK) goto out;

    /* 2. the data files (a file already there and recorded with the same SHA-256 is kept) */
    old = read_verified(c, ds);
    for (i = 0; want_all[i]; i++) {
        char name[64], *url, *dest;
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

    /* 3. renames: the .sha256 first, then the data files */
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
        otc_open_options_init(&oo);
        oo.error = c->err;
        st = otc_open_file(jsonl_path, &oo, &rel);
        if (st != OTC_OK) goto out;
    }
    {
        char jn[64];
        snprintf(jn, sizeof jn, "OTC_%s.jsonl", ds);
        write_stream_index(c, ds, rel, row_of(names, digests, n_rows, jn));
    }
    ver = cJSON_CreateObject();
    files = cJSON_CreateObject();
    if (old && cJSON_IsObject(otc__jget(old, "files"))) {
        const cJSON *f;
        cJSON_ArrayForEach(f, otc__jget(old, "files")) cJSON_AddItemToObject(files, f->string, cJSON_Duplicate(f, 1));
    }
    if (info) {
        for (i = 0; i < info->n_files; i++) {
            const otc_file_info *f = &info->files[i];
            cJSON *o = cJSON_CreateObject();
            cJSON_AddItemToObject(o, "sha256", str_or_null(f->sha256));
            cJSON_AddItemToObject(o, "size", f->size >= 0 ? cJSON_CreateNumber((double)f->size) : cJSON_CreateNull());
            cJSON_AddItemToObject(o, "url", str_or_null(f->url));
            cJSON_DeleteItemFromObjectCaseSensitive(files, f->name);
            cJSON_AddItemToObject(files, f->name, o);
        }
    } else {
        for (i = 0; i < n_rows; i++) {
            char *p = path2(dir, names[i]), *u = url_resolve(c->base_url, names[i]);
            int64_t size = p ? otc__path_size(p) : -1;
            const cJSON *prev = otc__jget(otc__jget(files, names[i]), "size");
            cJSON *o = cJSON_CreateObject();
            cJSON_AddStringToObject(o, "sha256", digests[i]);
            if (size >= 0) cJSON_AddNumberToObject(o, "size", (double)size);
            else if (cJSON_IsNumber(prev)) cJSON_AddNumberToObject(o, "size", prev->valuedouble);
            else cJSON_AddNullToObject(o, "size");
            cJSON_AddItemToObject(o, "url", str_or_null(u));
            cJSON_DeleteItemFromObjectCaseSensitive(files, names[i]);
            cJSON_AddItemToObject(files, names[i], o);
            free(p);
            free(u);
        }
    }
    cJSON_AddItemToObject(ver, "files", files);
    {
        char now[32], fvbuf[64], *vpath = path2(dir, ".verified"), *txt;
        size_t need;
        utc_now(now);
        cJSON_AddStringToObject(ver, "verified_at", now);
        cJSON_AddStringToObject(ver, "by", SDK_ID);
        cJSON_AddStringToObject(ver, "datestamp", ds);
        if (otc_release_format_version(rel, fvbuf, sizeof fvbuf, &need) == OTC_OK)
            cJSON_AddStringToObject(ver, "format_version", fvbuf);
        txt = cJSON_Print(ver);
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
    if (held) lock_release(dir);
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
    if (!r) return fail(c, OTC_E_NOMEM, NULL, "out of memory");
    if (fs_mkdir_p(r) != 0) st = fail(c, OTC_E_CACHE, r, "cannot create the cache directory %s", r);
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
        otc_open_options_init(&oo);
        oo.error = c->err;
        st = otc_open_file(p, &oo, out);
    }
    free(p);
    return st;
}

/* Puts a release into the cache if needed and opens it. */
static otc_status ensure_cached(fctx *c, const char *ds, const otc_release_info *info, otc_release **rel,
                                otc_loaded_from *lf)
{
    otc_status st;
    if (usable_strict(c, ds)) {
        *lf = OTC_LOADED_FROM_CACHE;
        return open_cached(c, ds, rel);
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
        if (usable_strict(c, release) || (c->offline && usable_loose(c, release))) {
            *lf = OTC_LOADED_FROM_CACHE;
            return open_cached(c, release, rel);
        }
        if (c->offline)
            return fail(c, OTC_E_OFFLINE_UNAVAILABLE, NULL, "offline, and release %s is not in the cache", release);
        return ensure_cached(c, release, NULL, rel, lf);
    }
    if ((st = ensure_root(c)) != OTC_OK) return st;
    if (c->offline) {
        *ds_out = newest_cached(c);
        if (!*ds_out) return fail(c, OTC_E_OFFLINE_UNAVAILABLE, NULL, "offline, and no release is in the cache");
        *lf = OTC_LOADED_FROM_CACHE;
        return open_cached(c, *ds_out, rel);
    }
    st = latest_info(c, &info);
    if (st == OTC_OK) {
        *ds_out = otc__strdup(info->datestamp);
        st = *ds_out ? ensure_cached(c, info->datestamp, info, rel, lf) : fail(c, OTC_E_NOMEM, NULL, "out of memory");
        otc_release_info_free(info);
    }
    if (st == OTC_E_NETWORK && !c->raise) {
        char *ds = newest_cached(c);
        if (ds) {
            snprintf(last_msg, last_len, "%s", c->err->message);
            logf_(c, 2, "network error (%s); using the cached release %s", last_msg, ds);
            free(*ds_out);
            *ds_out = ds;
            *last_status = OTC_E_NETWORK;
            *lf = OTC_LOADED_FROM_CACHE_AFTER_ERROR;
            otc_error_init(c->err);
            return open_cached(c, ds, rel);
        }
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
    otc_status st = ctx_init(&c, opts), last;
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
        otc_status st = ctx_init(&c, opts);
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
    otc_error *oerr = (oopts && oopts->struct_size >= sizeof *oopts) ? oopts->error : NULL;
    if (out) *out = NULL;
    st = ctx_init(&c, fopts);
    if (st == OTC_OK && !out) st = fail(&c, OTC_E_INVALID_ARGUMENT, NULL, "out is NULL");
    if (st == OTC_OK && oopts && oopts->struct_size < sizeof *oopts)
        st = fail(&c, OTC_E_INVALID_ARGUMENT, NULL, "otc_open_options: struct_size is too small");
    if (st == OTC_OK) st = resolve(&c, release, &rel, &lf, &ds, &last, msg, sizeof msg);
    if (st == OTC_OK) {
        otc_file_info *files = NULL;
        size_t n = 0;
        st = files_from_verified(&c, ds, &files, &n);
        if (st == OTC_OK) {
            free_file_infos(rel->files, rel->n_files);
            rel->files = files;
            rel->n_files = n;
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
            char *dir = pointer_dir(&c), *p = dir ? path2(dir, "OTC_index.json") : NULL, *t = p ? slurp(p) : NULL;
            char *url = url_resolve(c.base_url, "OTC_index.json");
            cJSON *doc = t ? otc__json_parse(t, strlen(t)) : NULL;
            if (!t) st = fail(&c, OTC_E_OFFLINE_UNAVAILABLE, NULL, "offline, and the release index is not in the cache");
            else if (!doc) st = fail(&c, OTC_E_INVALID_RELEASE, p, "cached OTC_index.json: not JSON");
            else if (!url) st = fail(&c, OTC_E_NOMEM, NULL, "out of memory");
            else st = index_infos(&c, doc, url, &v, &n);
            cJSON_Delete(doc);
            free(url);
            free(dir);
            free(p);
            free(t);
        } else {
            st = fetch_index(&c, &v, &n);
        }
    }
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
    if (st == OTC_OK) st = latest_info(&c, info);
    ctx_free(&c);
    return st;
}

otc_status otc_fetch_check_for_update(const otc_fetch_options *opts, const char *current, otc_release_info **info,
                                      bool *found)
{
    fctx c;
    otc_release_info *ri = NULL;
    otc_status st = ctx_init(&c, opts);
    if (info) *info = NULL;
    if (found) *found = false;
    if (st == OTC_OK && (!info || !found || !valid_datestamp(current)))
        st = fail(&c, OTC_E_INVALID_ARGUMENT, NULL, "current must be a datestamp; info and found must not be NULL");
    if (st == OTC_OK && c.offline) st = fail(&c, OTC_E_OFFLINE_UNAVAILABLE, NULL, "offline: the latest pointer cannot be read");
    if (st == OTC_OK) st = latest_info(&c, &ri);
    if (st == OTC_OK && ds_cmp(ri->datestamp, current) > 0) {
        *info = ri;
        *found = true;
        ri = NULL;
    }
    otc_release_info_free(ri);
    ctx_free(&c);
    return st;
}

otc_status otc_fetch_update(const otc_fetch_options *opts, const char *current, char *path, size_t len,
                            bool *updated)
{
    fctx c;
    otc_release_info *ri = NULL;
    otc_release *rel = NULL;
    otc_loaded_from lf;
    otc_status st = ctx_init(&c, opts);
    if (updated) *updated = false;
    if (path && len) path[0] = '\0';
    if (st == OTC_OK && (!updated || !valid_datestamp(current)))
        st = fail(&c, OTC_E_INVALID_ARGUMENT, NULL, "current must be a datestamp; updated must not be NULL");
    if (st == OTC_OK && c.offline) st = fail(&c, OTC_E_OFFLINE_UNAVAILABLE, NULL, "offline: the latest pointer cannot be read");
    if (st == OTC_OK) st = ensure_root(&c);
    if (st == OTC_OK) st = latest_info(&c, &ri);
    if (st == OTC_OK && ds_cmp(ri->datestamp, current) > 0) {
        st = ensure_cached(&c, ri->datestamp, ri, &rel, &lf);
        otc_close(rel);
        if (st == OTC_OK) {
            char *p = rel_file(&c, ri->datestamp, ".jsonl");
            size_t need;
            st = p ? copy_path(&c, p, path, len, &need) : fail(&c, OTC_E_NOMEM, NULL, "out of memory");
            free(p);
            if (st == OTC_OK) {
                *updated = true;
                logf_(&c, 1, "updated from %s to %s", current, ri->datestamp);
            }
        }
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
        char *d, *v;
        if (current && !strcmp(current, list[i])) continue;
        d = rel_dir(&c, list[i]);
        v = d ? path2(d, ".verified") : NULL;
        if (!d || !v) { free(d); free(v); st = fail(&c, OTC_E_NOMEM, NULL, "out of memory"); break; }
        fs_unlink(v);              /* readers stop trusting it first */
        fs_rm_rf(d);
        free(d);
        free(v);
        logf_(&c, 1, "pruned %s", list[i]);
        st = put_string(&c, removed, cap, k++, list[i]);
    }
    if (st == OTC_OK) {
        *count = k;
        if (k > cap) st = OTC_E_BUFFER_TOO_SMALL;
    }
    free_list(list, n);
    ctx_free(&c);
    return st;
}

/* ------------------------------------------------------------- otc_fetch_to_dir */

static otc_status file_sha(const char *path, char hex[65]) { return otc__sha256_file(path, hex); }

otc_status otc_fetch_to_dir(const otc_fetch_options *opts, const char *release, const char *dir, unsigned formats,
                            bool overwrite, char **paths, size_t cap, size_t *count)
{
    static const struct { unsigned bit; const char *ext; } FMT[] = {
        {OTC_FORMAT_JSON, ".json"}, {OTC_FORMAT_JSON_GZ, ".json.gz"}, {OTC_FORMAT_JSONL, ".jsonl"}, {0, NULL}};
    fctx c;
    otc_release_info *info = NULL;
    char *ds = NULL, *cdir = NULL, *sha_body = NULL, **names = NULL, **digests = NULL, *todo_name[8];
    char sha_digest[65], targets[8][64];
    const char *target_sha[8];
    size_t n_rows = 0, n_t = 0, n_todo = 0, i, written = 0, sha_len = 0;
    int cached = 0;
    otc_status st = ctx_init(&c, opts);
    if (count) *count = 0;
    memset(todo_name, 0, sizeof todo_name);
    if (st != OTC_OK) goto out;
    if (!count || !dir || (cap && !paths)) { st = fail(&c, OTC_E_INVALID_ARGUMENT, NULL, "dir and count must not be NULL"); goto out; }
    if (formats == 0) formats = OTC_FORMAT_JSONL;
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
            ds = newest_cached(&c);
            if (!ds) { st = fail(&c, OTC_E_OFFLINE_UNAVAILABLE, NULL, "offline, and no release is in the cache"); goto out; }
        } else {
            if ((st = latest_info(&c, &info)) != OTC_OK) goto out;
            ds = otc__strdup(info->datestamp);
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
        char name[64], *url;
        http_resp r;
        int res;
        if (c.offline) { st = fail(&c, OTC_E_OFFLINE_UNAVAILABLE, NULL, "offline, and release %s is not in the cache", ds); goto out; }
        snprintf(name, sizeof name, "OTC_%s.sha256", ds);
        url = url_resolve(c.base_url, name);
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
    if ((st = otc__sha256_rows_text(sha_body, &names, &digests, &n_rows)) != OTC_OK) { fail(&c, st, NULL, "out of memory"); goto out; }
    if ((st = check_pointer(&c, info, names, digests, n_rows)) != OTC_OK) goto out;
    {
        struct Sha_256 s;
        uint8_t h[SIZE_OF_SHA_256_HASH];
        sha_256_init(&s, h);
        sha_256_write(&s, sha_body, sha_len);
        sha_256_close(&s);
        hex_of(h, sha_digest);
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
            if (file_sha(p, hex) == OTC_OK && !strcmp(hex, target_sha[i])) { free(p); continue; }
            if (!overwrite) {
                st = fail(&c, OTC_E_FILE_EXISTS, p, "%s exists with a different SHA-256", p);
                free(p);
                goto out;
            }
        }
        free(p);
        todo_name[n_todo++] = targets[i];
    }
    if (fs_mkdir_p(dir) != 0) { st = fail(&c, OTC_E_IO, dir, "cannot create %s", dir); goto out; }
    for (i = 0; i < n_todo; i++) {
        const char *name = todo_name[i];
        const char *sha = row_of(names, digests, n_rows, name);
        char *dest = path2(dir, name), *src = path2(cdir, name), *tmp = NULL;
        if (!dest || !src) { free(dest); free(src); st = fail(&c, OTC_E_NOMEM, NULL, "out of memory"); goto out; }
        if (otc__ends_with(name, ".sha256")) {
            st = write_atomic(&c, dir, dest, sha_body, sha_len);
            if (st != OTC_OK) {
                st = fail(&c, OTC_E_IO, dest, "cannot write %s", dest);
                free(dest);
                free(src);
                goto out;
            }
        } else {
            if (cached && fs_kind(src) == 2) {
                char hex[65];
                st = copy_to_tmp(&c, src, dir, &tmp, hex);
                if (st == OTC_OK && strcmp(hex, sha) != 0) {
                    fs_unlink(tmp);
                    st = fail_checksum(&c, dest, sha, hex, "the cached copy does not match");
                }
            } else if (c.offline) {
                st = fail(&c, OTC_E_OFFLINE_UNAVAILABLE, NULL, "offline, and %s is not in the cache", name);
            } else {
                const otc_file_info *pf = info_file(info, name);
                char *url = (pf && pf->url) ? otc__strdup(pf->url) : url_resolve(c.base_url, name);
                st = url ? fetch_file(&c, url, dir, name, sha, pf ? pf->size : -1, &tmp)
                         : fail(&c, OTC_E_NOMEM, NULL, "out of memory");
                if (st == OTC_E_CACHE) st = fail(&c, OTC_E_IO, dest, "cannot write %s", dest);
                free(url);
            }
            if (st == OTC_OK && fs_rename(tmp, dest) != 0) {
                fs_unlink(tmp);
                st = fail(&c, OTC_E_IO, dest, "cannot write %s", dest);
            }
            free(tmp);
            if (st != OTC_OK) { free(dest); free(src); goto out; }
        }
        free(src);
        if (written < cap) paths[written] = dest;
        else free(dest);
        written++;
    }
    *count = written;
    if (written > cap) st = OTC_E_BUFFER_TOO_SMALL;
out:
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
