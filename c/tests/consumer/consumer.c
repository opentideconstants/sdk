/* An application that uses an installed libopentideconstants, found through
 * opentideconstants.pc or find_package(opentideconstants). CI builds it
 * against each installed configuration and runs it (c.yml, install job):
 *
 *     consumer <fixture .jsonl> <empty cache folder> <fetch: 0 or 1>
 *
 * It opens the fixture, counts its stations, and lists the cached releases
 * offline: OTC_OK with fetch, OTC_E_NOT_BUILT without. Exit 0 means every
 * check held. */
#include <opentideconstants.h>
#include <stdio.h>
#include <string.h>

int main(int argc, char **argv) {
    if (argc != 4 && argc != 5) {
        fprintf(stderr, "usage: consumer FIXTURE.jsonl CACHE_DIR FETCH(0|1) [PREDICTION_STATION_ID]\n");
        return 2;
    }
    int fetch = strcmp(argv[3], "1") == 0;
    otc_error err;
    otc_error_init(&err);
    otc_open_options o;
    otc_open_options_init(&o);
    o.error = &err;
    otc_release *rel = NULL;
    otc_status s = otc_open_file(argv[1], &o, &rel);
    if (s != OTC_OK) {
        fprintf(stderr, "otc_open_file: %s: %s\n", otc_status_code(s), err.message);
        return 1;
    }
    size_t stations = otc_release_station_count(rel);
    if (argc == 5) {
        otc_station_t *station = NULL;
        otc_predict_opts prediction;
        otc_prediction_info info;
        otc_height_t point;
        const int64_t t = INT64_C(946684800);
        otc_predict_opts_init(&prediction);
        otc_prediction_info_init(&info);
        prediction.info = &info;
        s = otc_require_station(rel, argv[4], &station);
        if (s != OTC_OK) return 1;
        s = otc_heights_at(rel, station, &prediction, &t, 1, &point);
        if (s != OTC_OK || point.t != t || !info.station_id || strcmp(info.station_id,argv[4])) return 1;
        printf("installed public C prediction %s %.17g\n",info.station_id,point.height_m);
        otc_station_free(station);
        otc_prediction_info_clear(&info);
    }
    otc_close(rel);

    if (stations == 0) {
        fprintf(stderr, "the fixture has no stations\n");
        return 1;
    }
    otc_fetch_options f;
    otc_fetch_options_init(&f);
    f.offline = true;
    f.cache_dir = argv[2];
    char *ds[4];
    size_t n = 0;
    s = otc_fetch_cached_releases(&f, ds, 4, &n);
    otc_status want = fetch ? OTC_OK : OTC_E_NOT_BUILT;
    if (s != want) {
        fprintf(stderr, "otc_fetch_cached_releases: %s, expected %s\n", otc_status_code(s), otc_status_code(want));
        return 1;
    }
    printf("version %s stations %zu fetch %s\n", OTC_VERSION, stations, otc_status_code(s));
    return 0;
}
