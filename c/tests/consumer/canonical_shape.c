/* Public ABI control: only installed public declarations, no internal models. */
#include <opentideconstants.h>
#include <stdio.h>
#include <string.h>

static int require(int condition, const char *message)
{
    if (!condition) fprintf(stderr, "%s\n", message);
    return condition;
}

int main(int argc, char **argv)
{
    otc_release *release = NULL;
    char datestamp[4] = "old";
    const char *names[1] = {NULL};
    size_t needed = 0, count = 0;
    otc_fetch_options fetch;
    otc_predict_opts predict;
    otc_height_t point = {0, 0};
    otc_status status;
    otc_error error;
    otc_open_options open_options;
    int ok = 1;
    if (argc != 2) return 2;
    otc_error_init(&error);
    otc_open_options_init(&open_options);
    open_options.error = &error;
    status = otc_open_file(argv[1], &open_options, &release);
    if (status != OTC_OK) fprintf(stderr, "%s: %s\n", otc_status_code(status), error.message);
    if (!require(status == OTC_OK && release != NULL, "actual public fixture open")) return 1;
    status = otc_release_datestamp(release, datestamp, sizeof(datestamp), &needed);
    ok &= require(status == OTC_E_BUFFER_TOO_SMALL && needed == 11 && strcmp(datestamp, "209") == 0,
        "public string partial output and needed preserved");
    status = otc_release_constituent_names(release, names, 1, &count);
    ok &= require(status == OTC_E_BUFFER_TOO_SMALL && names[0] != NULL && count > 1,
        "public array partial output and count preserved");
    otc_close(release);
    otc_fetch_options_init(&fetch);
    fetch.struct_size = 0; /* guarded before any acquisition */
    memcpy(datestamp, "old", 4);
    needed = 77;
    status = otc_fetch_latest(&fetch, datestamp, sizeof(datestamp), &needed);
    ok &= require((status == OTC_E_NOT_BUILT || status == OTC_E_INVALID_ARGUMENT) &&
        datestamp[0] == '\0' && needed == 0, "actual fetch per-API failure clear");
#ifdef OTC_SHAPE_FETCH
    ok &= require(status == (OTC_SHAPE_FETCH ? OTC_E_INVALID_ARGUMENT : OTC_E_NOT_BUILT),
        "actual fetch capability selection");
#endif
    otc_predict_opts_init(&predict);
    count = 77;
    status = otc_heights(NULL, NULL, &predict, 0, 1, &point, 1, &count);
    ok &= require((status == OTC_E_NOT_BUILT || status == OTC_E_INVALID_ARGUMENT) && count == 0,
        "actual prediction per-API failure clear");
#ifdef OTC_SHAPE_PREDICT
    ok &= require(status == (OTC_SHAPE_PREDICT ? OTC_E_INVALID_ARGUMENT : OTC_E_NOT_BUILT),
        "actual prediction capability selection");
#endif
    puts("public opaque consumer: partial outputs, exact failure clear, native module capability controls");
    return ok ? 0 : 1;
}
