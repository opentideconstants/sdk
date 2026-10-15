/* The otc_fetch module in a build without it (no -DOTC_WITH_FETCH=ON):
 * every otc_fetch_* call returns OTC_E_NOT_BUILT and opens no socket
 * (SDK spec 4.3.2, 4.8, 6.4). The real module is c/src/otc_fetch.c (K3d2). */
#include "otc_internal.h"

#include <stddef.h>

void otc_fetch_options_init(otc_fetch_options *opts)
{
    if (!opts) return;
    memset(opts, 0, sizeof *opts);
    opts->struct_size = sizeof *opts;
    opts->timeout_s = OTC_TIMEOUT_DEFAULT;
    opts->formats = OTC_FORMATS_DEFAULT;
    opts->on_network_error = OTC_ON_NETWORK_ERROR_USE_CACHE;
}

/* opts->error, or NULL when the caller's struct (an older, shorter layout) ends before it:
 * a field that struct_size does not cover is never read. */
static otc_error *opts_error(const otc_fetch_options *opts)
{
    if (!opts || opts->struct_size < offsetof(otc_fetch_options, error) + sizeof opts->error) return NULL;
    return opts->error;
}

static otc_status not_built(const otc_fetch_options *opts, const char *fn)
{
    otc_error *err = opts_error(opts);
    if (err) {
        otc__err_reset(err);
        otc__err_set(err, OTC_E_NOT_BUILT, NULL,
                     "%s: this build has no otc_fetch module (configure with -DOTC_WITH_FETCH=ON)", fn);
    }
    return OTC_E_NOT_BUILT;
}

/* A failed call leaves no path and no size behind. */
static void no_path(char *path, size_t len, size_t *needed)
{
    if (path && len) path[0] = '\0';
    if (needed) *needed = 0;
}

otc_status otc_fetch_latest(const otc_fetch_options *opts, char *path, size_t len, size_t *needed)
{
    no_path(path, len, needed);
    return not_built(opts, "otc_fetch_latest");
}

otc_status otc_fetch_release(const otc_fetch_options *opts, const char *datestamp, char *path, size_t len,
                             size_t *needed)
{
    (void)datestamp;
    no_path(path, len, needed);
    return not_built(opts, "otc_fetch_release");
}

otc_status otc_fetch_open(const otc_fetch_options *fopts, const char *release, const otc_open_options *oopts,
                          otc_release **out)
{
    (void)release;
    if (out) *out = NULL;
    if (oopts && oopts->struct_size >= OTC__OPEN_OPTIONS_MIN && oopts->error && oopts->error != opts_error(fopts)) {
        otc__err_reset(oopts->error);
        otc__err_set(oopts->error, OTC_E_NOT_BUILT, NULL,
                     "otc_fetch_open: this build has no otc_fetch module (configure with -DOTC_WITH_FETCH=ON)");
    }
    return not_built(fopts, "otc_fetch_open");
}

otc_status otc_fetch_releases(const otc_fetch_options *opts, otc_release_info **out, size_t cap, size_t *count)
{
    (void)out; (void)cap;
    if (count) *count = 0;
    return not_built(opts, "otc_fetch_releases");
}

otc_status otc_fetch_latest_info(const otc_fetch_options *opts, otc_release_info **info)
{
    if (info) *info = NULL;
    return not_built(opts, "otc_fetch_latest_info");
}

otc_status otc_fetch_check_for_update(const otc_fetch_options *opts, const char *current, otc_release_info **info,
                                      bool *found)
{
    (void)current;
    if (info) *info = NULL;
    if (found) *found = false;
    return not_built(opts, "otc_fetch_check_for_update");
}

otc_status otc_fetch_newer_format_major(const otc_fetch_options *opts, int *major)
{
    if (major) *major = 0;
    return not_built(opts, "otc_fetch_newer_format_major");
}

otc_status otc_fetch_update(const otc_fetch_options *opts, const char *current, char *path, size_t len,
                            size_t *needed, bool *updated)
{
    (void)current;
    no_path(path, len, needed);
    if (updated) *updated = false;
    return not_built(opts, "otc_fetch_update");
}

otc_status otc_fetch_to_dir(const otc_fetch_options *opts, const char *release, const char *dir, unsigned formats,
                            bool overwrite, char **paths, size_t cap, size_t *count)
{
    (void)release; (void)dir; (void)formats; (void)overwrite; (void)paths; (void)cap;
    if (count) *count = 0;
    return not_built(opts, "otc_fetch_to_dir");
}

otc_status otc_fetch_cached_releases(const otc_fetch_options *opts, char **datestamps, size_t cap, size_t *count)
{
    (void)datestamps; (void)cap;
    if (count) *count = 0;
    return not_built(opts, "otc_fetch_cached_releases");
}

otc_status otc_fetch_prune(const otc_fetch_options *opts, size_t keep, const char *current, char **removed, size_t cap,
                           size_t *count)
{
    (void)keep; (void)current; (void)removed; (void)cap;
    if (count) *count = 0;
    return not_built(opts, "otc_fetch_prune");
}
