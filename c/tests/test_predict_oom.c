#include "otc_test.h"
#include "otc_oom.h"
#include <stdint.h>
int main(void)
{
    const char *path=getenv("OTC_PREDICT_NATIVE_JSONL");
    otc_release *rel=NULL;
    otc_station_t *station=NULL;
    otc_predict_opts opts;
    otc_prediction_info info;
    otc_extreme_t events[32];
    size_t count;
    long k,injected=0,live;
    if (!path) { fputs("OTC_PREDICT_NATIVE_JSONL is required\n",stderr); return 1; }
    oom_hook_cjson();
    CHECK_STATUS(otc_open_file(path,NULL,&rel),OTC_OK);
    CHECK_STATUS(otc_require_station(rel,"OTC-V-NOAA-1820000",&station),OTC_OK);
    otc_predict_opts_init(&opts); otc_prediction_info_init(&info); opts.info=&info;
    {
        otc_status first=otc_extremes(rel,station,&opts,INT64_C(1267401600),INT64_C(1267488000),events,32,&count);
        if (first==OTC_E_NOT_BUILT) { otc_station_free(station); otc_close(rel); puts("prediction OOM gate inapplicable: native module not_built"); return 0; }
        CHECK_STATUS(first,OTC_OK);
    }

    otc_prediction_info_clear(&info); live=oom_live;
    for (k=1;k<=OOM_MAX_RUNS;k++) {
        otc_status st;
        oom_arm(k);
        st=otc_extremes(rel,station,&opts,INT64_C(1267401600),INT64_C(1267488000),events,32,&count);
        oom_disarm();
        if (oom_failed) { injected++; CHECK_STATUS(st,OTC_E_NOMEM); CHECK(count==0); CHECK(info.station_id==NULL && info._storage==NULL); }
        else CHECK_STATUS(st,OTC_OK);
        otc_prediction_info_clear(&info);
        CHECK(oom_live==live);
        if (!oom_failed) break;
    }
    CHECK(oom_loop_end("native prediction",k,injected));
    otc_station_free(station); otc_close(rel);
    printf("native prediction OOM: %ld failed allocation positions, no leaked ownership, cleared metadata/count\n",injected);
    return g_failures ? 1 : 0;
}
