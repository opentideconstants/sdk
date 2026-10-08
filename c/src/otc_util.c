/* Helpers: status codes, enum names, strings, JSON access, platform I/O,
 * locks, SHA-256 and the name fold (SDK spec 4.4.1, 4.8, 6.4). */
#include "otc_internal.h"
#include "otc_sha256_rename.h"
#include "sha-256.h"

#ifndef _WIN32
#include <errno.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
#endif

/* ------------------------------------------------------------ status codes */

const char *otc_status_code(otc_status status)
{
    switch (status) {
    case OTC_OK: return "ok";
    case OTC_E_NOT_FOUND: return "not_found";
    case OTC_E_NETWORK: return "network";
    case OTC_E_RELEASE_NOT_FOUND: return "release_not_found";
    case OTC_E_OFFLINE_UNAVAILABLE: return "offline_unavailable";
    case OTC_E_CHECKSUM: return "checksum_mismatch";
    case OTC_E_UNSUPPORTED_FORMAT: return "unsupported_format";
    case OTC_E_INVALID_RELEASE: return "invalid_release";
    case OTC_E_STATION_NOT_FOUND: return "station_not_found";
    case OTC_E_STATION_REMOVED: return "station_removed";
    case OTC_E_PINNED_RELEASE: return "pinned_release";
    case OTC_E_CACHE: return "cache";
    case OTC_E_FILE_EXISTS: return "file_exists";
    case OTC_E_IO: return "io";
    case OTC_E_INVALID_ARGUMENT: return "invalid_argument";
    case OTC_E_BUFFER_TOO_SMALL: return "buffer_too_small";
    case OTC_E_NOMEM: return "out_of_memory";
    case OTC_E_NOT_BUILT: return "not_built";
    case OTC_E_UNSUPPORTED_CONVENTION: return "unsupported_convention";
    }
    return "unknown";
}

void otc_free(void *p) { free(p); }

void otc_error_init(otc_error *err)
{
    if (!err) return;
    memset(err, 0, sizeof *err);
    err->struct_size = sizeof *err;
}

static void copy_trunc(char *dst, size_t cap, const char *src)
{
    size_t n = src ? strlen(src) : 0;
    if (cap == 0) return;
    if (n >= cap) n = cap - 1;
    if (n) memcpy(dst, src, n);
    dst[n] = '\0';
}

void otc__err_set(otc_error *err, otc_status st, const char *file, const char *fmt, ...)
{
    va_list ap;
    if (!err) return;
    err->status = st;
    if (file) copy_trunc(err->file, sizeof err->file, file);
    va_start(ap, fmt);
    vsnprintf(err->message, sizeof err->message, fmt, ap);
    va_end(ap);
}

/* ------------------------------------------------------------------- enums */

typedef struct name_row { int v; const char *s; } name_row;

static int parse_enum(const name_row *rows, int other, const char *s)
{
    size_t i;
    if (!s) return 0;
    for (i = 0; rows[i].s; i++)
        if (!strcmp(rows[i].s, s)) return rows[i].v;
    return other;
}

static const char *enum_name(const name_row *rows, int other, int v)
{
    size_t i;
    if (v == 0) return NULL;
    if (v == other) return "other";
    for (i = 0; rows[i].s; i++)
        if (rows[i].v == v) return rows[i].s;
    return "other";
}

static const name_row KIND[] = {{OTC_KIND_TIDE, "tide"}, {OTC_KIND_CURRENT, "current"}, {0, NULL}};
static const name_row STYPE[] = {{OTC_STATION_TYPE_REFERENCE, "reference"},
                                 {OTC_STATION_TYPE_SUBORDINATE, "subordinate"}, {0, NULL}};
static const name_row SSTATUS[] = {{OTC_STATION_STATUS_ACTIVE, "active"}, {OTC_STATION_STATUS_REMOVED, "removed"},
                                   {0, NULL}};
static const name_row SRCTYPE[] = {{OTC_SOURCE_TYPE_OFFICIAL, "official"}, {OTC_SOURCE_TYPE_GAUGE, "gauge"},
                                   {OTC_SOURCE_TYPE_MODEL, "model"}, {0, NULL}};
static const name_row QTY[] = {{OTC_QUANTITY_WATER_LEVEL, "water_level"}, {OTC_QUANTITY_CURRENT, "current"},
                               {0, NULL}};
static const name_row QCS[] = {{OTC_QC_STATUS_ACCEPTED, "accepted"}, {OTC_QC_STATUS_FALLBACK, "fallback"},
                               {OTC_QC_STATUS_EXCLUDED, "excluded"}, {0, NULL}};
static const name_row LOADED[] = {{OTC_LOADED_FROM_DOWNLOAD, "download"}, {OTC_LOADED_FROM_CACHE, "cache"},
                                  {OTC_LOADED_FROM_CACHE_AFTER_ERROR, "cache_after_error"},
                                  {OTC_LOADED_FROM_FILE, "file"}, {OTC_LOADED_FROM_FILE_UNVERIFIED, "file_unverified"},
                                  {0, NULL}};
static const name_row PHASE[] = {{OTC_PHASE_REFERENCE_GREENWICH_UTC, "greenwich_utc"},
                                 {OTC_PHASE_REFERENCE_LOCAL, "local"}, {0, NULL}};
static const name_row NODAL[] = {{OTC_NODAL_HANDLING_F_U_AT_PREDICTION, "f_u_at_prediction"},
                                 {OTC_NODAL_HANDLING_NONE, "none"}, {0, NULL}};
static const name_row HAT[] = {{OTC_HEIGHT_ADJUSTED_TYPE_R, "R"}, {OTC_HEIGHT_ADJUSTED_TYPE_A, "A"}, {0, NULL}};
static const name_row DROP[] = {{OTC_DROPPED_REASON_RAYLEIGH, "rayleigh"}, {OTC_DROPPED_REASON_NOISE, "noise"},
                                {OTC_DROPPED_REASON_LONG_PERIOD_RULE, "long_period_rule"},
                                {OTC_DROPPED_REASON_NON_TIDAL_RULE, "non_tidal_rule"},
                                {OTC_DROPPED_REASON_CONVENTION, "convention"}, {0, NULL}};
static const name_row QCF[] = {{OTC_QC_FLAG_TIME_BASE, "time_base"}, {OTC_QC_FLAG_BROKEN_RECORD, "broken_record"},
                               {OTC_QC_FLAG_MICROTIDAL, "microtidal"},
                               {OTC_QC_FLAG_NON_TIDAL_SIGNAL, "non_tidal_signal"},
                               {OTC_QC_FLAG_SHORT_RECORD, "short_record"},
                               {OTC_QC_FLAG_SIBLING_DISAGREEMENT, "sibling_disagreement"}, {0, NULL}};

#define ENUM_FUNCS(T, ROWS, OTHER, NAME, PARSE)                                                   \
    const char *NAME(T v) { return enum_name(ROWS, OTHER, (int)v); }                              \
    T PARSE(const char *s) { return (T)parse_enum(ROWS, OTHER, s); }

ENUM_FUNCS(otc_kind, KIND, OTC_KIND_OTHER, otc_kind_name, otc__parse_kind)
ENUM_FUNCS(otc_station_type_t, STYPE, OTC_STATION_TYPE_OTHER, otc_station_type_name, otc__parse_station_type)
ENUM_FUNCS(otc_station_status_t, SSTATUS, OTC_STATION_STATUS_OTHER, otc_station_status_name,
           otc__parse_station_status)
ENUM_FUNCS(otc_source_type, SRCTYPE, OTC_SOURCE_TYPE_OTHER, otc_source_type_name, otc__parse_source_type)
ENUM_FUNCS(otc_quantity, QTY, OTC_QUANTITY_OTHER, otc_quantity_name, otc__parse_quantity)
ENUM_FUNCS(otc_qc_status, QCS, OTC_QC_STATUS_OTHER, otc_qc_status_name, otc__parse_qc_status)
ENUM_FUNCS(otc_phase_reference, PHASE, OTC_PHASE_REFERENCE_OTHER, otc_phase_reference_name,
           otc__parse_phase_reference)
ENUM_FUNCS(otc_nodal_handling, NODAL, OTC_NODAL_HANDLING_OTHER, otc_nodal_handling_name,
           otc__parse_nodal_handling)
ENUM_FUNCS(otc_height_adjusted_type, HAT, OTC_HEIGHT_ADJUSTED_TYPE_OTHER, otc_height_adjusted_type_name,
           otc__parse_height_adjusted_type)
ENUM_FUNCS(otc_qc_flag_kind, QCF, OTC_QC_FLAG_OTHER, otc_qc_flag_kind_name, otc__parse_qc_flag)

const char *otc_loaded_from_name(otc_loaded_from v) { return enum_name(LOADED, OTC_LOADED_FROM_OTHER, (int)v); }

/* "other" is both a schema value and the unknown-value bucket of dropped_reason. */
const char *otc_dropped_reason_name(otc_dropped_reason v)
{
    return enum_name(DROP, OTC_DROPPED_REASON_OTHER, (int)v);
}
otc_dropped_reason otc__parse_dropped_reason(const char *s)
{
    return (otc_dropped_reason)parse_enum(DROP, OTC_DROPPED_REASON_OTHER, s);
}

/* ------------------------------------------------------------- JSON parse */

#ifdef _WIN32
static SRWLOCK g_parse_lock = SRWLOCK_INIT;
cJSON *otc__json_parse(const char *text, size_t len)
{
    cJSON *v;
    AcquireSRWLockExclusive(&g_parse_lock);
    v = cJSON_ParseWithLength(text, len);
    ReleaseSRWLockExclusive(&g_parse_lock);
    return v;
}
#else
static pthread_mutex_t g_parse_lock = PTHREAD_MUTEX_INITIALIZER;
cJSON *otc__json_parse(const char *text, size_t len)
{
    cJSON *v;
    pthread_mutex_lock(&g_parse_lock);
    v = cJSON_ParseWithLength(text, len);
    pthread_mutex_unlock(&g_parse_lock);
    return v;
}
#endif

/* ----------------------------------------------------------------- strings */

char *otc__strndup(const char *s, size_t n)
{
    char *p = (char *)malloc(n + 1);
    if (!p) return NULL;
    if (n) memcpy(p, s, n);
    p[n] = '\0';
    return p;
}

char *otc__strdup(const char *s)
{
    return s ? otc__strndup(s, strlen(s)) : NULL;
}

char *otc__join(const char *a, const char *b)
{
    size_t na = strlen(a), nb = strlen(b);
    char *p = (char *)malloc(na + nb + 1);
    if (!p) return NULL;
    memcpy(p, a, na);
    memcpy(p + na, b, nb + 1);
    return p;
}

int otc__strcmp_null(const char *a, const char *b)
{
    if (!a || !b) return a ? 1 : (b ? -1 : 0);
    return strcmp(a, b);
}

int otc__ends_with(const char *s, const char *suffix)
{
    size_t n = strlen(s), m = strlen(suffix);
    return n >= m && !strcmp(s + n - m, suffix);
}

otc_status otc__copy_str(const char *src, char *buf, size_t len, size_t *needed)
{
    size_t n;
    if (!src) {
        if (buf && len) buf[0] = '\0';
        if (needed) *needed = 0;
        return OTC_E_NOT_FOUND;
    }
    n = strlen(src) + 1;
    if (needed) *needed = n;
    if (!buf && len == 0) return OTC_OK;
    if (!buf) return OTC_E_INVALID_ARGUMENT;
    if (len < n) {
        if (len) {
            memcpy(buf, src, len - 1);
            buf[len - 1] = '\0';
        }
        return OTC_E_BUFFER_TOO_SMALL;
    }
    memcpy(buf, src, n);
    return OTC_OK;
}

otc_status otc__copy_json(const cJSON *v, char *buf, size_t len, size_t *needed)
{
    char *text;
    otc_status st;
    if (!v) return otc__copy_str(NULL, buf, len, needed);
    text = cJSON_PrintUnformatted(v);
    if (!text) return OTC_E_NOMEM;
    st = otc__copy_str(text, buf, len, needed);
    cJSON_free(text);
    return st;
}

const cJSON *otc__jget(const cJSON *obj, const char *key)
{
    const cJSON *v;
    if (!obj || !cJSON_IsObject(obj)) return NULL;
    v = cJSON_GetObjectItemCaseSensitive(obj, key);
    return (v && !cJSON_IsNull(v)) ? v : NULL;
}

const char *otc__jstr(const cJSON *obj, const char *key)
{
    const cJSON *v = otc__jget(obj, key);
    return cJSON_IsString(v) ? v->valuestring : NULL;
}

double otc__jnum(const cJSON *obj, const char *key)
{
    const cJSON *v = otc__jget(obj, key);
    return cJSON_IsNumber(v) ? v->valuedouble : NAN;
}

int64_t otc__jint(const cJSON *obj, const char *key)
{
    const cJSON *v = otc__jget(obj, key);
    if (!cJSON_IsNumber(v) || v->valuedouble < 0 || v->valuedouble > 9.0e18) return -1;
    return (int64_t)v->valuedouble;
}

/* --------------------------------------------------------------- key/count */

otc_status otc__kv_add(otc__kvlist *l, const char *key, int64_t n)
{
    size_t i;
    if (!key) return OTC_OK;
    for (i = 0; i < l->n; i++)
        if (!strcmp(l->items[i].key, key)) { l->items[i].n += n; return OTC_OK; }
    if (l->n == l->cap) {
        size_t cap = l->cap ? l->cap * 2 : 8;
        otc__kv *p = (otc__kv *)realloc(l->items, cap * sizeof *p);
        if (!p) return OTC_E_NOMEM;
        l->items = p;
        l->cap = cap;
    }
    l->items[l->n].key = otc__strdup(key);
    if (!l->items[l->n].key) return OTC_E_NOMEM;
    l->items[l->n].n = n;
    l->n++;
    return OTC_OK;
}

static int kv_cmp(const void *a, const void *b)
{
    return strcmp(((const otc__kv *)a)->key, ((const otc__kv *)b)->key);
}

void otc__kv_sort(otc__kvlist *l)
{
    if (l->n > 1) qsort(l->items, l->n, sizeof *l->items, kv_cmp);
}

void otc__kv_free(otc__kvlist *l)
{
    size_t i;
    for (i = 0; i < l->n; i++) free(l->items[i].key);
    free(l->items);
    l->items = NULL;
    l->n = l->cap = 0;
}

/* ---------------------------------------------------------------- platform */

#ifdef _WIN32
struct otc__file { HANDLE h; };

static wchar_t *widen(const char *s)
{
    int n = MultiByteToWideChar(CP_UTF8, 0, s, -1, NULL, 0);
    wchar_t *w;
    if (n <= 0) return NULL;
    w = (wchar_t *)malloc((size_t)n * sizeof *w);
    if (w && MultiByteToWideChar(CP_UTF8, 0, s, -1, w, n) <= 0) { free(w); w = NULL; }
    return w;
}

otc_status otc__file_open(const char *path, otc__file **out)
{
    wchar_t *w = widen(path);
    HANDLE h;
    otc__file *f;
    *out = NULL;
    if (!w) return OTC_E_IO;
    h = CreateFileW(w, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE, NULL, OPEN_EXISTING,
                    FILE_ATTRIBUTE_NORMAL, NULL);
    free(w);
    if (h == INVALID_HANDLE_VALUE) return OTC_E_IO;
    f = (otc__file *)malloc(sizeof *f);
    if (!f) { CloseHandle(h); return OTC_E_NOMEM; }
    f->h = h;
    *out = f;
    return OTC_OK;
}

int otc__file_pread(otc__file *f, void *buf, size_t n, uint64_t off)
{
    unsigned char *p = (unsigned char *)buf;
    while (n > 0) {
        OVERLAPPED ov;
        DWORD want = n > 0x40000000u ? 0x40000000u : (DWORD)n, got = 0;
        memset(&ov, 0, sizeof ov);
        ov.Offset = (DWORD)(off & 0xFFFFFFFFu);
        ov.OffsetHigh = (DWORD)(off >> 32);
        if (!ReadFile(f->h, p, want, &got, &ov) || got == 0) return -1;
        p += got;
        n -= got;
        off += got;
    }
    return 0;
}

int64_t otc__file_size(otc__file *f)
{
    LARGE_INTEGER sz;
    if (!GetFileSizeEx(f->h, &sz)) return -1;
    return (int64_t)sz.QuadPart;
}

void otc__file_close(otc__file *f)
{
    if (!f) return;
    CloseHandle(f->h);
    free(f);
}

int64_t otc__path_size(const char *path)
{
    WIN32_FILE_ATTRIBUTE_DATA a;
    wchar_t *w = widen(path);
    BOOL ok;
    if (!w) return -1;
    ok = GetFileAttributesExW(w, GetFileExInfoStandard, &a);
    free(w);
    if (!ok || (a.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY)) return -1;
    return ((int64_t)a.nFileSizeHigh << 32) | (int64_t)a.nFileSizeLow;
}

void otc__mutex_init(otc__mutex *m) { InitializeCriticalSection(&m->cs); }
void otc__mutex_lock(otc__mutex *m) { EnterCriticalSection(&m->cs); }
void otc__mutex_unlock(otc__mutex *m) { LeaveCriticalSection(&m->cs); }
void otc__mutex_destroy(otc__mutex *m) { DeleteCriticalSection(&m->cs); }

#else
struct otc__file { int fd; };

otc_status otc__file_open(const char *path, otc__file **out)
{
    int fd;
    otc__file *f;
    struct stat sb;
    *out = NULL;
    do { fd = open(path, O_RDONLY); } while (fd < 0 && errno == EINTR);
    if (fd < 0) return OTC_E_IO;
    if (fstat(fd, &sb) != 0 || !S_ISREG(sb.st_mode)) { close(fd); return OTC_E_IO; }
    f = (otc__file *)malloc(sizeof *f);
    if (!f) { close(fd); return OTC_E_NOMEM; }
    f->fd = fd;
    *out = f;
    return OTC_OK;
}

int otc__file_pread(otc__file *f, void *buf, size_t n, uint64_t off)
{
    unsigned char *p = (unsigned char *)buf;
    while (n > 0) {
        ssize_t got = pread(f->fd, p, n, (off_t)off);
        if (got < 0 && errno == EINTR) continue;
        if (got <= 0) return -1;
        p += got;
        n -= (size_t)got;
        off += (uint64_t)got;
    }
    return 0;
}

int64_t otc__file_size(otc__file *f)
{
    struct stat sb;
    if (fstat(f->fd, &sb) != 0) return -1;
    return (int64_t)sb.st_size;
}

void otc__file_close(otc__file *f)
{
    if (!f) return;
    close(f->fd);
    free(f);
}

int64_t otc__path_size(const char *path)
{
    struct stat sb;
    if (stat(path, &sb) != 0 || !S_ISREG(sb.st_mode)) return -1;
    return (int64_t)sb.st_size;
}

void otc__mutex_init(otc__mutex *m) { pthread_mutex_init(&m->m, NULL); }
void otc__mutex_lock(otc__mutex *m) { pthread_mutex_lock(&m->m); }
void otc__mutex_unlock(otc__mutex *m) { pthread_mutex_unlock(&m->m); }
void otc__mutex_destroy(otc__mutex *m) { pthread_mutex_destroy(&m->m); }
#endif

otc_status otc__read_all(const char *path, char **out, size_t *len)
{
    otc__file *f = NULL;
    otc_status st = otc__file_open(path, &f);
    int64_t size;
    char *buf;
    *out = NULL;
    if (st != OTC_OK) return st;
    size = otc__file_size(f);
    if (size < 0 || (uint64_t)size > (uint64_t)((size_t)-1) - 1) { otc__file_close(f); return OTC_E_IO; }
    buf = (char *)malloc((size_t)size + 1);
    if (!buf) { otc__file_close(f); return OTC_E_NOMEM; }
    if (size > 0 && otc__file_pread(f, buf, (size_t)size, 0) != 0) {
        free(buf);
        otc__file_close(f);
        return OTC_E_IO;
    }
    otc__file_close(f);
    buf[size] = '\0';
    *out = buf;
    if (len) *len = (size_t)size;
    return OTC_OK;
}

/* ----------------------------------------------------------------- SHA-256 */

otc_status otc__sha256_file(const char *path, char hex[65])
{
    static const char digits[] = "0123456789abcdef";
    otc__file *f = NULL;
    struct Sha_256 ctx;
    uint8_t hash[SIZE_OF_SHA_256_HASH];
    unsigned char *buf;
    uint64_t off = 0;
    int64_t size;
    size_t i;
    otc_status st = otc__file_open(path, &f);
    if (st != OTC_OK) return st;
    size = otc__file_size(f);
    buf = (unsigned char *)malloc(65536);
    if (!buf || size < 0) { free(buf); otc__file_close(f); return buf ? OTC_E_IO : OTC_E_NOMEM; }
    sha_256_init(&ctx, hash);
    while (off < (uint64_t)size) {
        size_t n = (uint64_t)size - off > 65536 ? 65536 : (size_t)((uint64_t)size - off);
        if (otc__file_pread(f, buf, n, off) != 0) { free(buf); otc__file_close(f); return OTC_E_IO; }
        sha_256_write(&ctx, buf, n);
        off += n;
    }
    sha_256_close(&ctx);
    free(buf);
    otc__file_close(f);
    for (i = 0; i < SIZE_OF_SHA_256_HASH; i++) {
        hex[2 * i] = digits[hash[i] >> 4];
        hex[2 * i + 1] = digits[hash[i] & 15];
    }
    hex[64] = '\0';
    return OTC_OK;
}

void otc__free_rows(char **names, char **digests, size_t n)
{
    size_t i;
    for (i = 0; i < n; i++) {
        if (names) free(names[i]);
        if (digests) free(digests[i]);
    }
    free(names);
    free(digests);
}

/* Parses a sha256sum file: "<64 hex>  <name>" or "<64 hex> *<name>" per line. */
otc_status otc__sha256_rows(const char *sha_path, char ***names_out, char ***digests_out, size_t *n_out)
{
    char *text = NULL;
    otc_status st = otc__read_all(sha_path, &text, NULL);
    *names_out = NULL;
    *digests_out = NULL;
    *n_out = 0;
    if (st != OTC_OK) return st;
    st = otc__sha256_rows_text(text, names_out, digests_out, n_out);
    free(text);
    return st;
}

otc_status otc__sha256_rows_text(const char *text, char ***names_out, char ***digests_out, size_t *n_out)
{
    const char *p;
    char **names = NULL, **digests = NULL;
    size_t n = 0, cap = 0;
    otc_status st = OTC_OK;
    *names_out = NULL;
    *digests_out = NULL;
    *n_out = 0;
    p = text;
    while (*p) {
        const char *eol = strchr(p, '\n'), *line_end = eol ? eol : p + strlen(p), *q = p, *name;
        size_t hl = 0;
        while (q < line_end && ((*q >= '0' && *q <= '9') || (*q >= 'a' && *q <= 'f') || (*q >= 'A' && *q <= 'F'))) {
            q++;
            hl++;
        }
        if (hl == 64 && q < line_end && (*q == ' ' || *q == '\t')) {
            const char *e = line_end;
            name = q;
            while (name < e && (*name == ' ' || *name == '\t')) name++;
            if (name < e && *name == '*') name++;
            while (e > name && (e[-1] == '\r' || e[-1] == ' ')) e--;
            if (e > name) {
                if (n == cap) {
                    size_t nc = cap ? cap * 2 : 8;
                    char **a = (char **)realloc(names, nc * sizeof *a), **b;
                    if (!a) { st = OTC_E_NOMEM; break; }
                    names = a;
                    b = (char **)realloc(digests, nc * sizeof *b);
                    if (!b) { st = OTC_E_NOMEM; break; }
                    digests = b;
                    cap = nc;
                }
                names[n] = otc__strndup(name, (size_t)(e - name));
                digests[n] = otc__strndup(p, 64);
                if (!names[n] || !digests[n]) { free(names[n]); free(digests[n]); st = OTC_E_NOMEM; break; }
                {
                    size_t i;
                    for (i = 0; i < 64; i++)
                        if (digests[n][i] >= 'A' && digests[n][i] <= 'F') digests[n][i] = (char)(digests[n][i] + 32);
                }
                n++;
            }
        }
        if (!eol) break;
        p = eol + 1;
    }
    if (st != OTC_OK) { otc__free_rows(names, digests, n); return st; }
    *names_out = names;
    *digests_out = digests;
    *n_out = n;
    return OTC_OK;
}

static const char *base_name(const char *path)
{
    const char *a = strrchr(path, '/'), *b = strrchr(path, '\\');
    const char *s = a > b ? a : b;
    return s ? s + 1 : path;
}

/* path minus a known release-file suffix, plus ".sha256" */
static char *sha_path_for(const char *path)
{
    static const char *const suffixes[] = {".meta.json", ".json.gz", ".jsonl", ".json", NULL};
    size_t i, n = strlen(path);
    for (i = 0; suffixes[i]; i++) {
        if (otc__ends_with(path, suffixes[i])) {
            char *base = otc__strndup(path, n - strlen(suffixes[i])), *r;
            if (!base) return NULL;
            r = otc__join(base, ".sha256");
            free(base);
            return r;
        }
    }
    return otc__join(path, ".sha256");
}

otc_status otc_verify_file(const char *path, const char *sha256_path, otc_error *err)
{
    char *own = NULL, **names = NULL, **digests = NULL, hex[65];
    const char *expected = NULL, *name;
    size_t n = 0, i;
    otc_status st;
    if (err) otc_error_init(err);
    if (!path) {
        otc__err_set(err, OTC_E_INVALID_ARGUMENT, NULL, "path is NULL");
        return OTC_E_INVALID_ARGUMENT;
    }
    if (!sha256_path) {
        own = sha_path_for(path);
        if (!own) { otc__err_set(err, OTC_E_NOMEM, path, "out of memory"); return OTC_E_NOMEM; }
        sha256_path = own;
    }
    st = otc__sha256_rows(sha256_path, &names, &digests, &n);
    if (st != OTC_OK) {
        otc__err_set(err, st, sha256_path, "cannot read %s", sha256_path);
        free(own);
        return st;
    }
    name = base_name(path);
    for (i = 0; i < n; i++)
        if (!strcmp(names[i], name)) expected = digests[i];
    st = otc__sha256_file(path, hex);
    if (st != OTC_OK) {
        otc__err_set(err, st, path, "cannot read %s", path);
    } else if (!expected || strcmp(expected, hex) != 0) {
        st = OTC_E_CHECKSUM;
        otc__err_set(err, st, path, "SHA-256 of %s does not match %s", name, sha256_path);
        if (err) {
            copy_trunc(err->expected_sha256, sizeof err->expected_sha256, expected ? expected : "");
            copy_trunc(err->actual_sha256, sizeof err->actual_sha256, hex);
        }
    }
    otc__free_rows(names, digests, n);
    free(own);
    return st;
}

/* -------------------------------------------------------------------- fold */

/* Decodes one UTF-8 sequence; returns its length (1 for an invalid byte, cp = the byte | 0x80000000). */
static size_t utf8_next(const unsigned char *s, uint32_t *cp)
{
    unsigned char c = s[0];
    size_t n, i;
    uint32_t v;
    if (c < 0x80) { *cp = c; return 1; }
    if ((c & 0xE0) == 0xC0) { n = 2; v = c & 0x1F; }
    else if ((c & 0xF0) == 0xE0) { n = 3; v = c & 0x0F; }
    else if ((c & 0xF8) == 0xF0) { n = 4; v = c & 0x07; }
    else { *cp = 0x80000000u | c; return 1; }
    for (i = 1; i < n; i++) {
        if ((s[i] & 0xC0) != 0x80) { *cp = 0x80000000u | c; return 1; }
        v = (v << 6) | (s[i] & 0x3F);
    }
    *cp = v;
    return n;
}

static const char *fold_lookup(uint32_t cp)
{
    size_t lo = 0, hi = otc__fold_table_size;
    while (lo < hi) {
        size_t mid = lo + (hi - lo) / 2;
        if (otc__fold_table[mid].cp == cp) return otc__fold_table[mid].folded;
        if (otc__fold_table[mid].cp < cp) lo = mid + 1;
        else hi = mid;
    }
    return NULL;
}

static int is_ws(char c)
{
    return c == ' ' || c == '\t' || c == '\n' || c == '\r' || c == '\f' || c == '\v';
}

char *otc__fold(const char *s)
{
    const unsigned char *p = (const unsigned char *)s;
    size_t cap = strlen(s) * 4 + 1, n = 0, i, o;
    char *tmp = (char *)malloc(cap), *out;
    int in_ws;
    if (!tmp) return NULL;
    while (*p) {
        uint32_t cp;
        size_t len = utf8_next(p, &cp);
        const char *f = (cp & 0x80000000u) ? NULL : fold_lookup(cp);
        if (f) {
            size_t fl = strlen(f);
            memcpy(tmp + n, f, fl);
            n += fl;
        } else {
            memcpy(tmp + n, p, len);
            n += len;
        }
        p += len;
    }
    tmp[n] = '\0';
    /* collapse whitespace runs to one space, then trim spaces */
    out = (char *)malloc(n + 1);
    if (!out) { free(tmp); return NULL; }
    o = 0;
    in_ws = 0;
    for (i = 0; i < n; i++) {
        if (is_ws(tmp[i])) {
            if (!in_ws) out[o++] = ' ';
            in_ws = 1;
        } else {
            out[o++] = tmp[i];
            in_ws = 0;
        }
    }
    free(tmp);
    while (o > 0 && out[o - 1] == ' ') o--;
    out[o] = '\0';
    i = 0;
    while (out[i] == ' ') i++;
    if (i) memmove(out, out + i, o - i + 1);
    return out;
}
