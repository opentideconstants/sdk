#include "opentideconstants.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(void)
{
    const char *path = getenv("OTC_CORE_NATIVE_JSONL");
    otc_release *rel = NULL;
    otc_open_options opts;
    otc_error err;
    const char *ids[20000];
    size_t n = 0, i;
    int bad = 0, aberdeen = 0, felipe = 0, otaru = 0, phipi = 0;
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
