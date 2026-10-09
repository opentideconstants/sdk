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
    case OTC_E_READER_TOO_OLD: return "reader_too_old";
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

otc_error *otc__err_usable(otc_error *err)
{
    return (err && err->struct_size >= sizeof *err) ? err : NULL;
}

void otc__err_reset(otc_error *err)
{
    if (!otc__err_usable(err)) return;   /* a smaller struct (an older caller, or not initialised) is left alone */
    memset(err, 0, sizeof *err);
    err->struct_size = sizeof *err;
}

void otc__err_set(otc_error *err, otc_status st, const char *file, const char *fmt, ...)
{
    va_list ap;
    if (!otc__err_usable(err)) return;
    err->status = st;
    if (file) copy_trunc(err->file, sizeof err->file, file);
    va_start(ap, fmt);
    vsnprintf(err->message, sizeof err->message, fmt, ap);
    va_end(ap);
}

/* ----------------------------------------------------------- format versions */

/* One non-negative integer with no leading zero; returns the end, or NULL. */
static const char *version_part(const char *p)
{
    const char *start = p;
    while (*p >= '0' && *p <= '9') p++;
    if (p == start || p - start > 9 || (p - start > 1 && *start == '0')) return NULL;
    return p;
}

int otc__version_valid(const char *v)
{
    const char *p;
    if (!v || !(p = version_part(v)) || *p != '.') return 0;
    p = version_part(p + 1);
    return p && *p == '\0';
}

static void version_parse(const char *v, long *major, long *minor)
{
    char *end = NULL;
    *major = 0;
    *minor = 0;
    if (!v) return;
    *major = strtol(v, &end, 10);
    if (end == v || *end != '.') { *major = 0; return; }
    v = end + 1;
    *minor = strtol(v, &end, 10);
    if (end == v) { *major = 0; *minor = 0; }
}

int otc__version_cmp(const char *a, const char *b)
{
    long am, an, bm, bn;
    version_parse(a, &am, &an);
    version_parse(b, &bm, &bn);
    if (am != bm) return am < bm ? -1 : 1;
    if (an != bn) return an < bn ? -1 : 1;
    return 0;
}

int otc__readable(const char *fv, const char *mrv)
{
    long major, minor;
    if (fv) {
        if (!otc__version_valid(fv)) return 0;
        version_parse(fv, &major, &minor);
        if (major != OTC_FORMAT_MAJOR) return 0;
    }
    if (mrv && !otc__version_valid(mrv)) return 0;   /* fail closed (spec 7.4, CR D9) */
    return !mrv || otc__version_cmp(mrv, OTC_FORMAT_VERSION) <= 0;
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
static const name_row QCS[] = {{OTC_QC_STATUS_OK, "ok"}, {OTC_QC_STATUS_FLAGGED, "flagged"},
                               {OTC_QC_STATUS_NO_CONSTANTS, "no_constants"}, {0, NULL}};
static const name_row REMOVED[] = {{OTC_REMOVED_REASON_MERGED, "merged"}, {OTC_REMOVED_REASON_DUPLICATE, "duplicate"},
                                   {0, NULL}};
static const name_row TBCODE[] = {{OTC_TIME_BASE_CODE_VERIFIED, "verified"}, {OTC_TIME_BASE_CODE_CORRECTED, "corrected"},
                                  {OTC_TIME_BASE_CODE_UNVERIFIED, "unverified"},
                                  {OTC_TIME_BASE_CODE_DISPUTED, "disputed"}, {0, NULL}};
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
                               {OTC_QC_FLAG_SIBLING_DISAGREEMENT, "sibling_disagreement"},
                               {OTC_QC_FLAG_CARRIED_OVER, "carried_over"}, {0, NULL}};

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
ENUM_FUNCS(otc_removed_reason, REMOVED, OTC_REMOVED_REASON_OTHER, otc_removed_reason_name, otc__parse_removed_reason)
ENUM_FUNCS(otc_time_base_code_t, TBCODE, OTC_TIME_BASE_CODE_OTHER, otc_time_base_code_name,
           otc__parse_time_base_code)
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

/* 1 when s[0..len) is well-formed UTF-8 (Unicode 15, table 3-7): no stray or
 * missing continuation byte, no overlong form, no encoded surrogate, nothing
 * above U+10FFFF. JSON text that is not UTF-8 is invalid_release, as in the
 * other SDKs (CR2 PK-R2-05); cJSON alone passes such bytes through. */
static int utf8_valid(const unsigned char *s, size_t len)
{
    size_t i = 0;
    while (i < len) {
        unsigned char c = s[i];
        size_t n, k;
        unsigned char lo = 0x80, hi = 0xBF;
        if (c < 0x80) {
            i++;
            continue;
        }
        if (c >= 0xC2 && c <= 0xDF) n = 1;
        else if (c >= 0xE0 && c <= 0xEF) {
            n = 2;
            if (c == 0xE0) lo = 0xA0;   /* no overlong form */
            if (c == 0xED) hi = 0x9F;   /* no surrogate */
        } else if (c >= 0xF0 && c <= 0xF4) {
            n = 3;
            if (c == 0xF0) lo = 0x90;   /* no overlong form */
            if (c == 0xF4) hi = 0x8F;   /* nothing above U+10FFFF */
        } else {
            return 0;
        }
        if (len - i <= n) return 0;
        if (s[i + 1] < lo || s[i + 1] > hi) return 0;
        for (k = 2; k <= n; k++)
            if (s[i + k] < 0x80 || s[i + k] > 0xBF) return 0;
        i += n + 1;
    }
    return 1;
}

/* cJSON reports every failure as NULL: a failed allocation in it (malloc sets
 * errno to ENOMEM) is told apart from text that is not JSON by errno. */
static void json_note_lengths(cJSON *v, const char *text, size_t len);

#ifdef _WIN32
static SRWLOCK g_parse_lock = SRWLOCK_INIT;
#define PARSE_LOCK() AcquireSRWLockExclusive(&g_parse_lock)
#define PARSE_UNLOCK() ReleaseSRWLockExclusive(&g_parse_lock)
#else
static pthread_mutex_t g_parse_lock = PTHREAD_MUTEX_INITIALIZER;
#define PARSE_LOCK() pthread_mutex_lock(&g_parse_lock)
#define PARSE_UNLOCK() pthread_mutex_unlock(&g_parse_lock)
#endif

otc_status otc__json_parse_st(const char *text, size_t len, cJSON **out)
{
    cJSON *v;
    int e;
    *out = NULL;
    if (!utf8_valid((const unsigned char *)text, len)) return OTC_E_INVALID_RELEASE;
    PARSE_LOCK();
    errno = 0;
    v = cJSON_ParseWithLengthOpts(text, len + 1, NULL, 1);   /* the whole text: trailing text fails */
    e = errno;
    PARSE_UNLOCK();
    json_note_lengths(v, text, len);   /* the full length of a string with a NUL inside (CR2 DR33) */
    *out = v;
    if (v) return OTC_OK;
    return e == ENOMEM ? OTC_E_NOMEM : OTC_E_INVALID_RELEASE;
}

cJSON *otc__json_parse(const char *text, size_t len)
{
    cJSON *v;
    (void)otc__json_parse_st(text, len, &v);
    return v;
}

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

int otc__bytes_cmp(const char *a, size_t an, const char *b, size_t bn)
{
    int c = memcmp(a, b, an < bn ? an : bn);
    return c ? c : (an > bn) - (an < bn);
}

int otc__ends_with(const char *s, const char *suffix)
{
    size_t n = strlen(s), m = strlen(suffix);
    return n >= m && !strcmp(s + n - m, suffix);
}

otc_status otc__copy_str(const char *src, char *buf, size_t len, size_t *needed)
{
    return otc__copy_strn(src, src ? strlen(src) : 0, buf, len, needed);
}

otc_status otc__copy_strn(const char *src, size_t sn, char *buf, size_t len, size_t *needed)
{
    size_t n;
    if (!src) {
        if (buf && len) buf[0] = '\0';
        if (needed) *needed = 0;
        return OTC_E_NOT_FOUND;
    }
    n = sn + 1;   /* every byte, NULs inside included (CR2 DR33), and the final NUL */
    if (needed) *needed = n;
    if (!buf && len == 0) return OTC_OK;
    if (!buf) return OTC_E_INVALID_ARGUMENT;
    if (len < n) {
        if (len) {
            /* cut on a whole UTF-8 character: never leave the lead bytes of a cut one */
            size_t k = len - 1;
            while (k > 0 && ((unsigned char)src[k] & 0xC0) == 0x80) k--;
            memcpy(buf, src, k);
            memset(buf + k, 0, len - k);   /* the rest of the buffer too: buf[len - 1] is always the NUL */
        }
        return OTC_E_BUFFER_TOO_SMALL;
    }
    memcpy(buf, src, sn);
    buf[sn] = '\0';
    return OTC_OK;
}

otc_status otc__copy_jstr(const cJSON *s, char *buf, size_t len, size_t *needed)
{
    if (!cJSON_IsString(s)) return otc__copy_strn(NULL, 0, buf, len, needed);
    return otc__copy_strn(s->valuestring, otc__jstr_len(s), buf, len, needed);
}

otc_status otc__copy_member(const cJSON *obj, const char *key, char *buf, size_t len, size_t *needed)
{
    return otc__copy_jstr(otc__jstr_item(obj, key), buf, len, needed);
}

/* 1 when a string in v holds a NUL. */
static int json_has_nul_string(const cJSON *v)
{
    const cJSON *c;
    if (cJSON_IsString(v) && otc__jstr_len(v) != strlen(v->valuestring)) return 1;
    for (c = v ? v->child : NULL; c; c = c->next)
        if (json_has_nul_string(c)) return 1;
    return 0;
}

/* copy is cJSON_Duplicate(orig): cJSON copies a string up to its first NUL, so each
 * string of orig with a NUL inside gets its full bytes back in copy (raw = 0), or
 * becomes its raw JSON literal for printing (raw = 1). 0 when out of memory. */
static int json_dup_strings(cJSON *copy, const cJSON *orig, int raw)
{
    const cJSON *o;
    cJSON *c;
    if (cJSON_IsString(orig) && otc__jstr_len(orig) != strlen(orig->valuestring)) {
        size_t n = otc__jstr_len(orig);
        char *lit = raw ? otc__json_escape_n(orig->valuestring, n) : NULL, *bytes;
        size_t size = raw ? (lit ? strlen(lit) + 1 : 0) : n + 1;
        if (raw && !lit) return 0;
        bytes = (char *)cJSON_malloc(size);   /* cJSON_Delete frees it */
        if (!bytes) { free(lit); return 0; }
        memcpy(bytes, raw ? lit : orig->valuestring, size);
        free(lit);
        cJSON_free(copy->valuestring);
        copy->valuestring = bytes;
        if (raw) copy->type = cJSON_Raw;
        return 1;
    }
    for (o = orig->child, c = copy->child; o && c; o = o->next, c = c->next)
        if (!json_dup_strings(c, o, raw)) return 0;
    return 1;
}

cJSON *otc__json_dup(const cJSON *v)
{
    cJSON *copy = v ? cJSON_Duplicate(v, 1) : NULL;
    if (copy && !json_dup_strings(copy, v, 0)) {
        cJSON_Delete(copy);
        return NULL;
    }
    return copy;
}

otc_status otc__copy_json(const cJSON *v, char *buf, size_t len, size_t *needed)
{
    char *text;
    otc_status st;
    if (!v) return otc__copy_str(NULL, buf, len, needed);
    if (json_has_nul_string(v)) {
        /* cJSON prints a string up to its first NUL: print a copy whose such strings are raw literals */
        cJSON *copy = cJSON_Duplicate(v, 1);
        if (!copy || !json_dup_strings(copy, v, 1)) { cJSON_Delete(copy); return OTC_E_NOMEM; }
        text = cJSON_PrintUnformatted(copy);
        cJSON_Delete(copy);
    } else {
        text = cJSON_PrintUnformatted(v);
    }
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
    /* a count is a whole number; a fraction is not cut to one, it reads as missing */
    if (!cJSON_IsNumber(v) || !(v->valuedouble >= 0) || v->valuedouble > 9.0e18 || v->valuedouble != floor(v->valuedouble))
        return -1;
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
#ifndef O_CLOEXEC
#define O_CLOEXEC 0
#endif
    /* close-on-exec: the handle a release keeps does not leak into the app's child processes */
    do { fd = open(path, O_RDONLY | O_CLOEXEC); } while (fd < 0 && errno == EINTR);
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

int otc__remove_file(const char *path)
{
#ifdef _WIN32
    wchar_t *w = widen(path);
    int r = w ? _wremove(w) : -1;
    free(w);
    return r;
#else
    return remove(path);
#endif
}

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

static void to_hex(const uint8_t *hash, char hex[65])
{
    static const char digits[] = "0123456789abcdef";
    size_t i;
    for (i = 0; i < SIZE_OF_SHA_256_HASH; i++) {
        hex[2 * i] = digits[hash[i] >> 4];
        hex[2 * i + 1] = digits[hash[i] & 15];
    }
    hex[64] = '\0';
}

otc_status otc__sha256_handle(otc__file *f, char hex[65])
{
    struct Sha_256 ctx;
    uint8_t hash[SIZE_OF_SHA_256_HASH];
    unsigned char *buf;
    uint64_t off = 0;
    int64_t size = otc__file_size(f);
    if (size < 0) return OTC_E_IO;
    buf = (unsigned char *)malloc(65536);
    if (!buf) return OTC_E_NOMEM;
    sha_256_init(&ctx, hash);
    while (off < (uint64_t)size) {
        size_t n = (uint64_t)size - off > 65536 ? 65536 : (size_t)((uint64_t)size - off);
        if (otc__file_pread(f, buf, n, off) != 0) { free(buf); return OTC_E_IO; }
        sha_256_write(&ctx, buf, n);
        off += n;
    }
    sha_256_close(&ctx);
    free(buf);
    to_hex(hash, hex);
    return OTC_OK;
}

void otc__sha256_mem(const void *data, size_t len, char hex[65])
{
    struct Sha_256 ctx;
    uint8_t hash[SIZE_OF_SHA_256_HASH];
    sha_256_init(&ctx, hash);
    sha_256_write(&ctx, data, len);
    sha_256_close(&ctx);
    to_hex(hash, hex);
}

otc_status otc__sha256_file(const char *path, char hex[65])
{
    otc__file *f = NULL;
    otc_status st = otc__file_open(path, &f);
    if (st != OTC_OK) return st;
    st = otc__sha256_handle(f, hex);
    otc__file_close(f);
    return st;
}

const char *otc__sha256_rows_what(otc_status st)
{
    return st == OTC_E_INVALID_RELEASE ? "a name listed twice, or bytes that are not UTF-8, in" : "cannot read";
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

/* Parses a sha256sum file: "<64 hex>  <name>" or "<64 hex> *<name>" per line.
 * A file with a row that is not UTF-8, or that names a file twice, is
 * OTC_E_INVALID_RELEASE, so that row order never decides a check (spec 5.3,
 * CR2 DR14). */
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
            while (e > name && (e[-1] == '\r' || e[-1] == ' ' || e[-1] == '\t')) e--;
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
                    size_t j;
                    for (j = 0; j < n && strcmp(names[j], names[n]) != 0; j++) {}
                    if (j < n) { free(names[n]); free(digests[n]); st = OTC_E_INVALID_RELEASE; break; }
                }
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
    /* with no row at all the caller decides (a 200 with no row is a network error, CR2 DR13) */
    if (st == OTC_OK && n > 0 && !utf8_valid((const unsigned char *)text, strlen(text))) st = OTC_E_INVALID_RELEASE;
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
    err = otc__err_usable(err);
    otc__err_reset(err);
    if (!path) {
        otc__err_set(err, OTC_E_INVALID_ARGUMENT, NULL, "path is NULL");
        return OTC_E_INVALID_ARGUMENT;
    }
    if (!sha256_path) {
        own = sha_path_for(path);
        if (!own) { otc__err_set(err, OTC_E_NOMEM, path, "out of memory"); return OTC_E_NOMEM; }
        sha256_path = own;
        if (otc__path_size(own) < 0) {   /* file_unverified: nothing to compare with (spec 4.3, CR D20) */
            otc__err_set(err, OTC_E_CHECKSUM, path, "no %s next to %s, so it cannot be verified", base_name(own), path);
            free(own);
            return OTC_E_CHECKSUM;
        }
    }
    st = otc__sha256_rows(sha256_path, &names, &digests, &n);
    if (st != OTC_OK) {
        otc__err_set(err, st, sha256_path, "%s %s", otc__sha256_rows_what(st), sha256_path);
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

/* ------------------------------------------------------------- datestamps */

int otc__valid_datestamp(const char *s, size_t n)
{
    size_t i;
    if (n < 8 || n > 18) return 0;   /* ^[0-9]{8}(\.[2-9]|\.[1-9][0-9]{1,8})?$ (spec 4.2, CR D18) */
    for (i = 0; i < 8; i++)
        if (s[i] < '0' || s[i] > '9') return 0;
    if (n == 8) return 1;
    if (s[8] != '.' || n < 10) return 0;
    for (i = 9; i < n; i++)
        if (s[i] < '0' || s[i] > '9') return 0;
    if (n == 10) return s[9] >= '2';
    return s[9] != '0';
}

/* ------------------------------------------------------------------- times */

static int digits_at(const char *s, int n, int *v)
{
    int i;
    *v = 0;
    for (i = 0; i < n; i++) {
        if (s[i] < '0' || s[i] > '9') return 0;
        *v = *v * 10 + (s[i] - '0');
    }
    return 1;
}

/* Days since 1970-01-01 of a proleptic Gregorian date (H. Hinnant's days_from_civil). */
static long long days_from_civil(long long y, int m, int d)
{
    long long era, yoe, doy, doe;
    y -= m <= 2;
    era = (y >= 0 ? y : y - 399) / 400;
    yoe = y - era * 400;
    doy = (153 * (m + (m > 2 ? -3 : 9)) + 2) / 5 + d - 1;
    doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    return era * 146097 + doe - 719468;
}

static void civil_from_days(long long z, long long *y, int *m, int *d)
{
    long long era, doe, yoe, doy, mp;
    z += 719468;
    era = (z >= 0 ? z : z - 146096) / 146097;
    doe = z - era * 146097;
    yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    *y = yoe + era * 400;
    doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    mp = (5 * doy + 2) / 153;
    *d = (int)(doy - (153 * mp + 2) / 5 + 1);
    *m = (int)(mp < 10 ? mp + 3 : mp - 9);
    *y += *m <= 2;
}

/* The days in a month of the proleptic Gregorian calendar (M 1 to 12). */
static int days_in_month(long long y, int M)
{
    static const int DAYS[] = {31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
    if (M == 2 && ((y % 4 == 0 && y % 100 != 0) || y % 400 == 0)) return 29;
    return DAYS[M - 1];
}

/* CR2 DR6: impossible calendar fields, hour 24 and a leap second :60 are
 * malformed, never rolled over into another date. */
static int fields_valid(long long Y, int M, int D, int h, int mi, int sec)
{
    return M >= 1 && M <= 12 && D >= 1 && D <= days_in_month(Y, M) && h <= 23 && mi <= 59 && sec <= 59;
}

int otc__utc_time(const char *s, char out[21])
{
    int Y, M, D, h, mi, sec, oh = 0, om = 0, sign = 0;
    long long t, days;
    long long y;
    const char *p;
    if (!s || strlen(s) < 19 || !digits_at(s, 4, &Y) || s[4] != '-' || !digits_at(s + 5, 2, &M) || s[7] != '-'
        || !digits_at(s + 8, 2, &D) || (s[10] != 'T' && s[10] != 't' && s[10] != ' ') || !digits_at(s + 11, 2, &h)
        || s[13] != ':' || !digits_at(s + 14, 2, &mi) || s[16] != ':' || !digits_at(s + 17, 2, &sec))
        return 0;
    if (!fields_valid(Y, M, D, h, mi, sec)) return 0;
    p = s + 19;
    if (*p == '.') {   /* a fraction: whole seconds are kept (RFC 3339 §5.6) */
        if (p[1] < '0' || p[1] > '9') return 0;
        for (p++; *p >= '0' && *p <= '9'; p++) {}
    }
    if (*p == 'Z' || *p == 'z') {
        p++;
    } else if (*p == '+' || *p == '-') {
        sign = *p == '-' ? -1 : 1;
        if (!digits_at(p + 1, 2, &oh) || p[3] != ':' || !digits_at(p + 4, 2, &om) || oh > 23 || om > 59) return 0;
        p += 6;
    } else if (*p == '\0') {
        sign = 0;   /* no offset: UTC, as the other SDKs read it */
    } else {
        return 0;
    }
    if (*p != '\0') return 0;
    t = days_from_civil(Y, M, D) * 86400LL + h * 3600LL + mi * 60LL + sec - (long long)sign * (oh * 3600LL + om * 60LL);
    days = t >= 0 ? t / 86400 : -((-t + 86399) / 86400);
    t -= days * 86400;
    civil_from_days(days, &y, &M, &D);
    if (y < 1 || y > 9999) return 0;   /* years 1 to 9999 once the offset is applied (CR2 DR6) */
    {   /* the fields are in range here; gcc cannot see that, so format into room to spare */
        char tmp[64];
        snprintf(tmp, sizeof tmp, "%04d-%02d-%02dT%02d:%02d:%02dZ", (int)y, M, D, (int)(t / 3600), (int)(t / 60 % 60),
                 (int)(t % 60));
        if (strlen(tmp) != 20) return 0;
        memcpy(out, tmp, 21);
    }
    return 1;
}

int64_t otc__http_date(const char *s)
{
    static const char *const MON[] = {"Jan", "Feb", "Mar", "Apr", "May", "Jun",
                                      "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"};
    static const char *const WDAY[] = {"Thu", "Fri", "Sat", "Sun", "Mon", "Tue", "Wed"};   /* 1970-01-01: Thu */
    int D, Y, h, mi, sec, M;
    long long days;
    /* IMF-fixdate: "Sun, 06 Nov 1994 08:49:37 GMT" (RFC 9110 5.6.7) */
    if (!s || strlen(s) != 29 || s[3] != ',' || s[4] != ' ' || !digits_at(s + 5, 2, &D) || s[7] != ' '
        || s[11] != ' ' || !digits_at(s + 12, 4, &Y) || s[16] != ' ' || !digits_at(s + 17, 2, &h) || s[19] != ':'
        || !digits_at(s + 20, 2, &mi) || s[22] != ':' || !digits_at(s + 23, 2, &sec) || strcmp(s + 25, " GMT") != 0)
        return -1;
    for (M = 0; M < 12; M++)
        if (!strncmp(s + 8, MON[M], 3)) break;
    if (M == 12 || !fields_valid(Y, M + 1, D, h, mi, sec)) return -1;   /* CR2 DR6 */
    days = days_from_civil(Y, M + 1, D);
    if (strncmp(s, WDAY[((days % 7) + 7) % 7], 3) != 0) return -1;   /* the weekday must match the date */
    return days * 86400LL + h * 3600LL + mi * 60LL + sec;
}

/* ------------------------------------------- strings with a NUL inside */

/* cJSON ends a decoded string at its first NUL as far as strlen can tell, so a
 * JSON string with \u0000 in it (valid JSON, and schema-valid for a station
 * name, an alias id or a set_id) seems to lose its tail. otc__json_parse walks
 * the text once more beside the tree and records the length of every such
 * string (CR2 DR33). */

static const char *js_ws(const char *p, const char *end)
{
    while (p < end && (*p == ' ' || *p == '\t' || *p == '\n' || *p == '\r')) p++;
    return p;
}

/* p at an opening quote: the position after the closing quote, or NULL. */
static const char *js_skip_string(const char *p, const char *end)
{
    for (p++; p < end; p++) {
        if (*p == '\\') { p++; continue; }
        if (*p == '"') return p + 1;
    }
    return NULL;
}

static int js_hex4(const char *p, const char *end, uint32_t *v)
{
    int i;
    *v = 0;
    if (end - p < 4) return 0;
    for (i = 0; i < 4; i++) {
        char c = p[i];
        *v <<= 4;
        if (c >= '0' && c <= '9') *v |= (uint32_t)(c - '0');
        else if (c >= 'a' && c <= 'f') *v |= (uint32_t)(c - 'a' + 10);
        else if (c >= 'A' && c <= 'F') *v |= (uint32_t)(c - 'A' + 10);
        else return 0;
    }
    return 1;
}

/* The decoded length (UTF-8 bytes) of the JSON string at p (an opening quote), or
 * -1 when it is not one cJSON decodes (cJSON refuses an unpaired surrogate too). */
static long long js_decoded_len(const char *p, const char *end)
{
    long long o = 0;
    for (p++; p < end && *p != '"'; p++) {
        uint32_t cp;
        if (*p != '\\') { o++; continue; }
        if (++p >= end) return -1;
        if (*p != 'u') { o++; continue; }
        if (!js_hex4(p + 1, end, &cp)) return -1;
        p += 4;
        if (cp >= 0xD800 && cp <= 0xDBFF) {
            uint32_t lo;
            if (end - p < 7 || p[1] != '\\' || p[2] != 'u' || !js_hex4(p + 3, end, &lo) || lo < 0xDC00 || lo > 0xDFFF)
                return -1;
            p += 6;
            o += 4;
        } else if (cp >= 0xDC00 && cp <= 0xDFFF) {
            return -1;
        } else {
            o += cp < 0x80 ? 1 : cp < 0x800 ? 2 : 3;
        }
    }
    return p < end ? o : -1;
}

/* 1 when the JSON string token [p, q) has a \u0000 escape. */
static int js_token_has_nul(const char *p, const char *q)
{
    return otc__json_has_nul(p, (size_t)(q - p));
}

/* Walks the value at p beside its parsed node v (cJSON keeps members and items
 * in text order) and records the length of each string with a NUL. Returns the
 * position after the value, or NULL if the two disagree (then nothing more is
 * recorded: the strings keep their strlen length). */
static const char *js_note(cJSON *v, const char *p, const char *end, int depth)
{
    p = js_ws(p, end);
    if (!v || p >= end || depth > 1000) return NULL;
    if (*p == '"') {
        const char *q = js_skip_string(p, end);
        if (!q || !cJSON_IsString(v)) return NULL;
        if (js_token_has_nul(p, q)) {
            long long n = js_decoded_len(p, q);
            if (n < 0) return NULL;
            v->valuedouble = (double)n;
        }
        return q;
    }
    if (*p == '{' || *p == '[') {
        char close = *p == '{' ? '}' : ']';
        cJSON *c = v->child;
        p = js_ws(p + 1, end);
        if (p < end && *p == close) return p + 1;
        for (;;) {
            if (close == '}') {   /* the key */
                if (p >= end || *p != '"' || !(p = js_skip_string(p, end))) return NULL;
                p = js_ws(p, end);
                if (p >= end || *p != ':') return NULL;
                p++;
            }
            if (!c || !(p = js_note(c, p, end, depth + 1))) return NULL;
            c = c->next;
            p = js_ws(p, end);
            if (p < end && *p == ',') { p = js_ws(p + 1, end); continue; }
            return p < end && *p == close ? p + 1 : NULL;
        }
    }
    while (p < end && *p != ',' && *p != '}' && *p != ']' && *p != ' ' && *p != '\t' && *p != '\n' && *p != '\r') p++;
    return p;
}

static void json_note_lengths(cJSON *v, const char *text, size_t len)
{
    if (v && otc__json_has_nul(text, len)) (void)js_note(v, text, text + len, 0);
}

int otc__json_has_nul(const char *text, size_t len)
{
    size_t i;
    for (i = 0; i + 6 <= len; i++) {
        if (text[i] == '\\') {
            if (!memcmp(text + i + 1, "u0000", 5)) return 1;
            i++;   /* the escaped character */
        }
    }
    return 0;
}

size_t otc__jstr_len(const cJSON *s)
{
    /* valuedouble: the length otc__json_parse recorded (0: none, the string has no NUL inside) */
    return s->valuedouble > 0 ? (size_t)s->valuedouble : strlen(s->valuestring);
}

const cJSON *otc__jstr_item(const cJSON *obj, const char *key)
{
    const cJSON *v = otc__jget(obj, key);
    return cJSON_IsString(v) ? v : NULL;
}

int otc__jstr_is(const cJSON *s, const char *str)
{
    size_t n;
    if (!cJSON_IsString(s) || !str) return 0;
    n = otc__jstr_len(s);
    return strlen(str) == n && !memcmp(s->valuestring, str, n);
}

int otc__jstr_same(const cJSON *a, const cJSON *b)
{
    size_t n;
    if (!cJSON_IsString(a) || !cJSON_IsString(b)) return 0;
    n = otc__jstr_len(a);
    return otc__jstr_len(b) == n && !memcmp(a->valuestring, b->valuestring, n);
}

cJSON *otc__json_str_out(const cJSON *s)
{
    char *lit;
    cJSON *v;
    if (!cJSON_IsString(s)) return NULL;
    if (otc__jstr_len(s) == strlen(s->valuestring)) return cJSON_CreateString(s->valuestring);
    lit = otc__json_escape_n(s->valuestring, otc__jstr_len(s));
    v = lit ? cJSON_CreateRaw(lit) : NULL;
    free(lit);
    return v;
}

char *otc__json_escape_n(const char *s, size_t n)
{
    static const char hex[] = "0123456789abcdef";
    size_t i, o = 0;
    char *out = (char *)malloc(n * 6 + 3);
    if (!out) return NULL;
    out[o++] = '"';
    for (i = 0; i < n; i++) {
        unsigned char c = (unsigned char)s[i];
        if (c == '"' || c == '\\') { out[o++] = '\\'; out[o++] = (char)c; }
        else if (c < 0x20) {
            out[o++] = '\\'; out[o++] = 'u'; out[o++] = '0'; out[o++] = '0';
            out[o++] = hex[c >> 4]; out[o++] = hex[c & 15];
        } else out[o++] = (char)c;
    }
    out[o++] = '"';
    out[o] = '\0';
    return out;
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
    return otc__fold_n(s, strlen(s), NULL);
}

char *otc__fold_n(const char *s, size_t sn, size_t *out_len)
{
    const unsigned char *p = (const unsigned char *)s, *pend = p + sn;
    size_t cap = sn * 4 + 1, n = 0, i, o;
    char *tmp = (char *)malloc(cap), *out;
    int in_ws;
    if (!tmp) return NULL;
    while (p < pend) {
        uint32_t cp = 0;
        size_t len = *p ? utf8_next(p, &cp) : 1;   /* a NUL is a character like any other (spec 4.4.1, D12 e) */
        const char *f;
        if (len > (size_t)(pend - p)) len = (size_t)(pend - p);
        f = (!cp || (cp & 0x80000000u)) ? NULL : fold_lookup(cp);
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
    while (i < o && out[i] == ' ') i++;
    if (i) memmove(out, out + i, o - i + 1);
    if (out_len) *out_len = o - i;
    return out;
}
