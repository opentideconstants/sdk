/* The otc_fetch module in a build without it (no -DOTC_WITH_FETCH=ON):
 * every otc_fetch_* call returns OTC_E_NOT_BUILT and opens no socket
 * (SDK spec 4.3.2, 4.8, 6.4). The real module is c/src/otc_fetch.c (K3d2). */
#include "otc_internal.h"

void otc_fetch_options_init(otc_fetch_options *opts)
{
    if (!opts) return;
    memset(opts, 0, sizeof *opts);
    opts->struct_size = sizeof *opts;
    opts->on_network_error = OTC_ON_NETWORK_ERROR_USE_CACHE;
}

static otc_status not_built(const otc_fetch_options *opts, const char *fn)
{
    if (opts && opts->struct_size >= sizeof *opts && opts->error) {
        otc_error_init(opts->error);
        otc__err_set(opts->error, OTC_E_NOT_BUILT, NULL,
                     "%s: this build has no otc_fetch module (configure with -DOTC_WITH_FETCH=ON)", fn);
    }
    return OTC_E_NOT_BUILT;
}

otc_status otc_fetch_latest(const otc_fetch_options *opts, char *path, size_t len, size_t *needed)
{
    (void)path; (void)len; (void)needed;
    return not_built(opts, "otc_fetch_latest");
}

otc_status otc_fetch_release(const otc_fetch_options *opts, const char *datestamp, char *path, size_t len,
                             size_t *needed)
{
    (void)datestamp; (void)path; (void)len; (void)needed;
    return not_built(opts, "otc_fetch_release");
}

otc_status otc_fetch_open(const otc_fetch_options *fopts, const char *release, const otc_open_options *oopts,
                          otc_release **out)
{
    (void)release;
    if (out) *out = NULL;
    if (oopts && oopts->struct_size >= sizeof *oopts && oopts->error && (!fopts || oopts->error != fopts->error)) {
        otc_error_init(oopts->error);
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

otc_status otc_fetch_update(const otc_fetch_options *opts, const char *current, char *path, size_t len,
                            bool *updated)
{
    (void)current; (void)path; (void)len;
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
