#include "opentideconstants.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <math.h>
#include <string.h>
typedef struct cell { const char *id; const char *kind; int64_t t; double height; } cell;
/* Values pinned to H4/python-final/policy-312.json; no new scientific oracle. */
static const cell cells[] = {
    {"OTC-28c56e20","high",INT64_C(1791677021),1.4722200607392313},
    {"OTC-28c56e20","low",INT64_C(1791700343),0.09409250997439655},
    {"OTC-541f1a73","high",INT64_C(1791702328),1.4875246967720928},
    {"OTC-541f1a73","low",INT64_C(1791678751),0.03778895345957567},
    {"OTC-e813b80c","high",INT64_C(1791691329),3.098915409849229},
    {"OTC-e813b80c","low",INT64_C(1791713029),0.09279280821900682},
    {"OTC-e813b80c","high",INT64_C(1791735330),3.2494189979066745},
    {"OTC-e813b80c","low",INT64_C(1791757919),-0.0861064681480046},
    {"OTC-bb22c37b","high",INT64_C(1791677256),3.472833558363307},
    {"OTC-bb22c37b","low",INT64_C(1791701120),0.0054853054081767105},
    {"OTC-bb22c37b","high",INT64_C(1791725107),3.27820914798804},
    {"OTC-bb22c37b","low",INT64_C(1791745095),1.3804951209001965},
    {"OTC-ee4593cd","low",INT64_C(1791680611),0.03778895345957567},
    {"OTC-ee4593cd","high",INT64_C(1791704428),1.5484846967720927},
    {"OTC-ee4593cd","low",INT64_C(1791723266),0.5306789624390935},
    {"OTC-ee4593cd","high",INT64_C(1791746289),1.854425831615762},
};
int main(void)
{
    const char *path = getenv("OTC_NOAA_NATIVE_JSONL");
    const char *ids[] = {"OTC-28c56e20","OTC-541f1a73"};
    otc_release *rel=NULL;
    otc_station_t *station=NULL;
    otc_predict_opts opts;
    otc_prediction_info info;
    otc_extreme_t points[16], explicit_points[16];
    size_t i,j,n=0,m=0;
    const int64_t start=INT64_C(1791676800),stop=INT64_C(1791763200);
    if (!path) { fputs("OTC_NOAA_NATIVE_JSONL is required\n",stderr); return 1; }
    assert(otc_open_file(path,NULL,&rel)==OTC_OK);
    otc_predict_opts_init(&opts); otc_prediction_info_init(&info); opts.info=&info; opts.datum="chart";
    {
        otc_status built=otc_extremes(rel,NULL,NULL,0,0,NULL,0,&n);
        if (built==OTC_E_NOT_BUILT) { otc_close(rel); otc_prediction_info_clear(&info); puts("historical arithmetic module disabled: native not_built"); return 0; }
    }
    for (i=0;i<sizeof cells/sizeof cells[0];i++) {

        assert(otc_require_station(rel,cells[i].id,&station)==OTC_OK);
        assert(otc_extremes(rel,station,&opts,start,stop,points,16,&n)==OTC_OK);
        for (j=0;j<n;j++) if (points[j].t==cells[i].t && !strcmp(otc_extreme_type_name(points[j].type),cells[i].kind)) break;
        assert(j<n && fabs(points[j].height_m-cells[i].height)<1e-7);
        printf("actual %s %s %lld %.17g PASS\n",cells[i].id,cells[i].kind,(long long)points[j].t,points[j].height_m);
        otc_station_free(station); station=NULL;
    }
    for (i=0;i<2;i++) {
        otc_offsets_t offsets;
        assert(otc_require_station(rel,ids[i],&station)==OTC_OK);
        assert(otc_station_offsets(station,&offsets)==OTC_OK);
        assert(otc_extremes(rel,station,&opts,start,stop,points,16,&n)==OTC_OK);
        assert(info.historical_offsets && !info.set_id && info.reference_set_id);
        assert(!strcmp(info.current_validity,"unestablished") && !strcmp(info.current_accuracy,"unverified"));
        assert(!strcmp(info.reference_2020_equivalence,"disagrees") && !strcmp(info.offset_source,"noaa"));
        assert(strstr(info.source_note,"retired NOAA profile"));
        opts.offset_id=offsets.offset_id; opts.datum=NULL;
        assert(otc_extremes(rel,station,&opts,start,stop,explicit_points,16,&m)==OTC_OK && n==m);
        for (j=0;j<n;j++) assert(points[j].t==explicit_points[j].t && points[j].type==explicit_points[j].type && points[j].height_m==explicit_points[j].height_m);
        assert(otc_heights(rel,station,&opts,start,stop,NULL,0,&m)==OTC_E_EXTREMES_ONLY);
        assert(info.station_id==NULL);
        opts.offset_id=NULL; opts.datum="chart";
        otc_station_free(station); station=NULL;
    }
    otc_prediction_info_clear(&info); otc_close(rel); rel=NULL;
    {
        otc_open_options open;
        otc_filter filter;
        otc_open_options_init(&open); open.historical_offsets_policy="exclude";
        assert(otc_open_file(path,&open,&rel)==OTC_OK);
        for (i=0;i<2;i++) {
            otc_offsets_t offsets;
            unsigned combination;
            assert(otc_require_station(rel,ids[i],&station)==OTC_OK);
            assert(otc_station_offsets(station,&offsets)==OTC_OK);
            for (combination=0;combination<4;combination++) {
                const char *found[16];
                otc_filter_init(&filter); filter.include_flagged=(combination&1)!=0; filter.include_fallback=(combination&2)!=0;
                assert(otc_stations(rel,&filter,found,16,&n)==OTC_OK);
                for (j=0;j<n;j++) assert(strcmp(found[j],ids[i]));
                assert(otc_extremes(rel,station,&opts,start,stop,points,16,&n)==OTC_E_HISTORICAL_OFFSETS_EXCLUDED);
                opts.offset_id=offsets.offset_id;
                assert(otc_extremes(rel,station,&opts,start,stop,points,16,&n)==OTC_E_HISTORICAL_OFFSETS_EXCLUDED);
                opts.offset_id=NULL;
            }
            otc_station_free(station); station=NULL;
        }
        otc_close(rel);
    }
    puts("native four historical arithmetic cells, three unchanged contexts, default=explicit labels/full-curve refusals/strict four flags PASS");
    return 0;
}
