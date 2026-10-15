/* PK-R2-23 (R2-252, R2-257): otc_fetch_* with an otc_fetch_options shorter
 * than this header's (an older caller's struct, struct_size says so). The
 * library reads only the fields that struct_size covers: the options are
 * allocated at exactly that size, so a read past it is a heap overflow that
 * ASan reports. A failed otc_fetch_latest / otc_fetch_release leaves no stale
 * path or size behind (*needed 0, path ""). The test runs in both builds:
 * without the otc_fetch module every call is OTC_E_NOT_BUILT; with it, the
 * short struct is OTC_E_INVALID_ARGUMENT before any network access. */
#include "otc_test.h"

#include <stddef.h>

int main(void)
{
    size_t short_size = offsetof(otc_fetch_options, error);   /* ends before error */
    otc_fetch_options *fo = (otc_fetch_options *)malloc(short_size);
    otc_open_options oo;
    otc_error oerr;
    otc_release *rel = (otc_release *)&oo;   /* not NULL: the call must clear it */
    otc_status st, want;
    char path[64];
    size_t needed;
    if (!fo) return 2;
    memset(fo, 0, short_size);
    fo->struct_size = short_size;
    fo->offline = true;

    otc_open_options_init(&oo);
    otc_error_init(&oerr);
    oo.error = &oerr;
    st = otc_fetch_open(fo, "20990101", &oo, &rel);
    CHECK(st == OTC_E_NOT_BUILT || st == OTC_E_INVALID_ARGUMENT);
    CHECK(rel == NULL);
    want = st;
    if (st == OTC_E_NOT_BUILT) CHECK(oerr.status == OTC_E_NOT_BUILT);

    /* the path out of a failed call: no stale size, no stale path */
    needed = 77;
    strcpy(path, "stale");
    CHECK_STATUS(otc_fetch_latest(fo, path, sizeof path, &needed), want);
    CHECK(needed == 0);
    CHECK(path[0] == '\0');
    needed = 77;
    strcpy(path, "stale");
    CHECK_STATUS(otc_fetch_release(fo, "20990101", path, sizeof path, &needed), want);
    CHECK(needed == 0);
    CHECK(path[0] == '\0');
    needed = 77;
    strcpy(path, "stale");
    CHECK_STATUS(otc_fetch_release(fo, NULL, path, sizeof path, &needed), want);
    CHECK(needed == 0);
    CHECK(path[0] == '\0');

    free(fo);
    return test_done("test_stub_opts");
}
