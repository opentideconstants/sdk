#if !defined(_WIN32)
#define _POSIX_C_SOURCE 200809L
#endif
#include "opentideconstants.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(void)
{
    otc_tz *tz = NULL;
    otc_local_t local;
    otc_status st = otc_tz_open("America/New_York", &tz);
    if (st == OTC_E_NOT_BUILT) {
        assert(otc_tz_open(NULL, NULL) == OTC_E_NOT_BUILT);
        assert(otc_tz_local(NULL, 0, NULL) == OTC_E_NOT_BUILT);
        puts("local time stub returns not_built"); return 0;
    }
    assert(st == OTC_OK && tz);
    assert(otc_tz_local(tz, INT64_C(1699162200), &local) == OTC_OK);
    assert(local.t == INT64_C(1699162200) && local.utc_offset_s == -14400);
    assert(!strcmp(local.local_time,"2023-11-05T01:30:00-04:00"));
    assert(otc_tz_local(tz, INT64_C(1699165800), &local) == OTC_OK);
    assert(local.utc_offset_s == -18000 && !strcmp(local.local_time,"2023-11-05T01:30:00-05:00"));
    otc_tz_close(tz);
    assert(otc_tz_open("Europe/Oslo", &tz) == OTC_OK); otc_tz_close(tz);
    assert(otc_tz_open("XYZ3", &tz) == OTC_E_UNKNOWN_TIME_ZONE && !tz);
    assert(otc_tz_open("../UTC", &tz) == OTC_E_UNKNOWN_TIME_ZONE && !tz);
    assert(otc_tz_open("right/UTC", &tz) == OTC_E_UNKNOWN_TIME_ZONE && !tz);
    assert(otc_tz_open("localtime", &tz) == OTC_E_UNKNOWN_TIME_ZONE && !tz);
    assert(otc_tz_local(NULL, 0, &local) == OTC_E_INVALID_ARGUMENT);
#ifndef _WIN32
    {
        const char *old=getenv("TZDIR");
        char *saved=old ? malloc(strlen(old)+1) : NULL;
        if (old) { assert(saved); strcpy(saved,old); }
        assert(setenv("TZDIR","/otc-native-no-such-zoneinfo",1)==0);
        assert(otc_tz_open("UTC",&tz)==OTC_E_LOCAL_TIME_UNAVAILABLE && !tz);
        assert(otc_tz_open("../UTC",&tz)==OTC_E_LOCAL_TIME_UNAVAILABLE && !tz);
        if (saved) { assert(setenv("TZDIR",saved,1)==0); free(saved); }
        else assert(unsetenv("TZDIR")==0);
    }
#endif
    puts("native timezone actual DST fold, symlink, invalid-name and missing-TZDIR controls PASS");

    return 0;
}
