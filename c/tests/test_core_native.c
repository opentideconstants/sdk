#include "opentideconstants.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int small_source(const char *path)
{
    otc_release *rel = NULL;
    otc_station_t *station = NULL;
    otc_stats *stats = NULL;
    const otc_set *set = NULL;
    otc_open_options opts;
    otc_error err;
    const char *ids[64];
    char station_id[64] = "null", set_id[64] = "null";
    size_t n = 0;
    otc_status st;
    int bad = 0;
    otc_open_options_init(&opts);
    otc_error_init(&err);
    opts.error = &err;
    st = otc_open_file(path, &opts, &rel);
    if (getenv("OTC_CORE_EXPECT_MISSING_READER")) {
        printf("missing source reader: status=%s release=%s message=%s\n",
               otc_status_code(st), rel ? "published" : "null", err.message);
        bad = st != OTC_E_INVALID_RELEASE || rel != NULL || !strstr(err.message, "min_reader_version");
        otc_close(rel);
        return bad;
    }
    if (st != OTC_OK) { fprintf(stderr, "%s\n", err.message); return 2; }
    st = otc_stations(rel, NULL, ids, 64, &n);
    bad += st != OTC_OK || n == 0 || n > 64;
    st = otc_release_stats(rel, &stats);
    bad += st != OTC_OK || stats == NULL;
    st = otc_station(rel, "OTC-T-0001", &station);
    bad += st != OTC_OK || station == NULL;
    if (station) {
        bad += otc_station_recommended_set(station, &set) != OTC_OK;
        bad += otc_station_station_id(station, station_id, sizeof station_id, NULL) != OTC_OK;
        bad += strcmp(station_id, "OTC-T-0001") != 0;
        bad += !set || otc_set_set_id(set, set_id, sizeof set_id, NULL) != OTC_OK;
        bad += strcmp(set_id, "OTC-T-0001/noaa") != 0;
    }
    printf("small source: discovery=%zu station=%s recommended=%s status=%s\n", n,
           station_id, set_id,
           otc_status_code(st));
    otc_station_free(station);
    otc_stats_free(stats);
    otc_close(rel);
    return bad ? 1 : 0;
}

int main(void)
{
    const char *small = getenv("OTC_CORE_SMALL_JSONL");
    const char *path = getenv("OTC_CORE_NATIVE_JSONL");
    otc_release *rel = NULL;
    otc_open_options opts;
    otc_error err;
    const char *ids[20000];
    size_t n = 0, i;
    int bad = 0, aberdeen = 0, felipe = 0, otaru = 0, phipi = 0;
    if (small) return small_source(small);
    if (!path) { fprintf(stderr, "OTC_CORE_NATIVE_JSONL required\n"); return 2; }
    otc_open_options_init(&opts);
    otc_error_init(&err);
    opts.error = &err;
    if (otc_open_file(path, &opts, &rel) != OTC_OK) { fprintf(stderr, "%s\n", err.message); return 2; }
    if (otc_stations(rel, NULL, ids, 20000, &n) != OTC_OK) return 2;
    for (i = 0; i < n; i++) {
        aberdeen |= !strcmp(ids[i], "OTC-666303b1");
        felipe |= !strcmp(ids[i], "OTC-e00b60ee");
        phipi |= !strcmp(ids[i], "OTC-1f91a5ad");
        otaru |= !strcmp(ids[i], "OTC-03cf7f34");
    }
    printf("default discovery=%zu (expected6715)\n", n);
    printf("Aberdeen labelledfallback default=%d expected0\n", aberdeen);
    printf("SanFelipe withheld default=%d expected0\n", felipe);
    printf("Otaru good contemporary default=%d expected1\n", otaru);
    printf("Phipi metadata retained default=%d expected0\n", phipi);
    bad += phipi;
    { otc_station_t *st = NULL;
      if (otc_station(rel, "OTC-1f91a5ad", &st) != OTC_OK || !st || !otc_station_source_record_count(st)) bad++;
      otc_station_free(st); }
    bad += n != 6715; bad += aberdeen; bad += felipe; bad += !otaru;
    otc_close(rel);
    return bad ? 1 : 0;
}
