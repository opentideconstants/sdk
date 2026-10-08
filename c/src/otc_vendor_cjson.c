/* Compiles the vendored cJSON (c/vendor/cjson, unchanged) with every public
 * symbol renamed to otc__cJSON_* (otc_cjson_rename.h). */
#if defined(_MSC_VER) && !defined(_CRT_SECURE_NO_WARNINGS)
#define _CRT_SECURE_NO_WARNINGS
#endif
#ifndef CJSON_HIDE_SYMBOLS
#define CJSON_HIDE_SYMBOLS
#endif
#include "otc_cjson_rename.h"
#include "cJSON.c"
