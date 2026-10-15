#include "opentideconstants.h"
#include <assert.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(void)
{
    otc_release *rel = NULL;
    otc_station_t *station = NULL;
    otc_predict_opts opts;
    otc_prediction_info prediction;
    otc_height_t h[3];
    otc_datum_info info;
    otc_datum_level *levels;
    size_t n = 0, i;
    int64_t times[] = {INT64_C(946684800), INT64_C(946684799), INT64_C(946684800)};
    const char *path = getenv("OTC_PREDICT_NATIVE_JSONL");
    if (!path) { fputs("OTC_PREDICT_NATIVE_JSONL is required\n",stderr); return 1; }
    assert(otc_open_file(path,NULL,&rel) == OTC_OK);
    assert(otc_require_station(rel,"OTC-V-NOAA-1820000",&station) == OTC_OK);
    otc_predict_opts_init(&opts); otc_prediction_info_init(&prediction); opts.info=&prediction;
    {
        otc_status first=otc_heights_at(rel,station,&opts,times,3,h);
        if (first==OTC_E_NOT_BUILT) {
            const otc_astro_tab *table=NULL;
            assert(otc_heights_at(NULL,NULL,NULL,NULL,1,NULL)==OTC_E_NOT_BUILT);
            assert(otc_heights(NULL,NULL,NULL,1,0,NULL,0,&n)==OTC_E_NOT_BUILT && n==0);
            assert(otc_extremes(NULL,NULL,NULL,1,0,NULL,0,&n)==OTC_E_NOT_BUILT);
            assert(otc_currents(NULL,NULL,NULL,1,0,NULL,0,&n)==OTC_E_NOT_BUILT);
            assert(otc_current_events(NULL,NULL,NULL,1,0,NULL,0,&n)==OTC_E_NOT_BUILT);
            assert(otc_datums(NULL,NULL,NULL,&info,NULL,0,&n)==OTC_E_NOT_BUILT);
            assert(otc_astro_table(NULL,NULL,&table)==OTC_E_NOT_BUILT && !table);
            otc_station_free(station); otc_close(rel); otc_prediction_info_clear(&prediction);
            puts("native disabled prediction public APIs return not_built before invalid-argument checks");
            return 0;
        }
        assert(first==OTC_OK);
    }

    assert(h[0].t == times[0] && h[1].t == times[1] && h[2].height_m == h[0].height_m);
    assert(fabs(h[0].height_m - 0.2713156) < 1e-6);
    assert(!strcmp(prediction.station_id,"OTC-V-NOAA-1820000"));
    assert(otc_heights(rel,station,&opts,0,0,NULL,0,&n) == OTC_OK && n==0);
    opts.step_s=0; n=99;
    assert(otc_heights(rel,station,&opts,0,1,NULL,0,&n) == OTC_E_INVALID_ARGUMENT && n==0);
    assert(prediction.station_id == NULL && prediction._storage == NULL);
    otc_predict_opts_init(&opts); opts.info=&prediction;
    assert(otc_heights_at(rel,station,&opts,times,3,h) == OTC_OK);
    assert(otc_datums(rel,station,NULL,&info,NULL,0,&n) == OTC_E_BUFFER_TOO_SMALL);
    assert(n > 0);
    levels=calloc(n,sizeof *levels); assert(levels);
    assert(otc_datums(rel,station,NULL,&info,levels,n,&n) == OTC_OK);
    for (i=1;i<n;i++) assert(strcmp(levels[i-1].key,levels[i].key)<0);
    assert(info.has_msl_offset);
    free(levels);
    otc_station_free(station); otc_close(rel);
    /* Owned prediction metadata remains readable after both source owners close. */
    assert(!strcmp(prediction.station_id,"OTC-V-NOAA-1820000"));
    otc_prediction_info_clear(&prediction);
    puts("native prediction actual ordered-repeat/value/empty/error/datum/metadata-lifetime controls PASS");
    return 0;
}
