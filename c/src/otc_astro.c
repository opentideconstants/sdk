/* Astronomical table validation and UTC table evaluation (prediction 4.2a, 4.3). */
#include "otc_internal.h"
#include <limits.h>

double otc__angle(double value)
{
    double reduced = value - 360.0 * floor(value / 360.0);
    return reduced == 360.0 ? 0.0 : reduced;
}

static otc_status validate(const otc_release *rel, const cJSON *raw, int *first, int *last)
{
    const cJSON *rows, *row, *values, *value, *speed;
    double a = otc__jnum(raw, "first_year"), b = otc__jnum(raw, "last_year");
    const char *id = otc__jstr(raw, "astro_table_id");
    const char *keys[] = {"v0u_deg", "f"};
    size_t k;
    if (!isfinite(a) || !isfinite(b) || floor(a) != a || floor(b) != b || a > b || a < INT_MIN || b > INT_MAX)
        return otc__fail(rel, OTC_E_INVALID_ARGUMENT, "astro table \"%s\" first_year and last_year must be ordered integers", id ? id : "");
    *first = (int)a; *last = (int)b;
    rows = otc__jget(raw, "constituents");
    if (!cJSON_IsObject(rows)) return otc__fail(rel, OTC_E_INVALID_ARGUMENT, "astro table \"%s\" constituents must be an object", id ? id : "");
    cJSON_ArrayForEach(row, rows) {
        if (!cJSON_IsObject(row)) return otc__fail(rel, OTC_E_INVALID_ARGUMENT, "astro table \"%s\" row \"%s\": must be an object", id ? id : "", row->string);
        for (k = 0; k < 2; k++) {
            values = otc__jget(row, keys[k]);
            if (!cJSON_IsArray(values) || (int64_t)cJSON_GetArraySize(values) != (int64_t)*last - *first + 1)
                return otc__fail(rel, OTC_E_INVALID_ARGUMENT, "astro table \"%s\" row \"%s\": %s has an invalid length", id ? id : "", row->string, keys[k]);
            cJSON_ArrayForEach(value, values) if (!cJSON_IsNumber(value) || !isfinite(value->valuedouble))
                return otc__fail(rel, OTC_E_INVALID_ARGUMENT, "astro table \"%s\" row \"%s\": %s must contain numbers", id ? id : "", row->string, keys[k]);
        }
        speed = otc__jget(row, "speed_deg_per_hour");
        if (speed && !cJSON_IsNull(speed) && (!cJSON_IsNumber(speed) || !isfinite(speed->valuedouble) || speed->valuedouble < 0))
            return otc__fail(rel, OTC_E_INVALID_ARGUMENT, "astro table \"%s\" row \"%s\": speed_deg_per_hour must be a nonnegative number", id ? id : "", row->string);
    }
    return OTC_OK;
}

otc_status otc_astro_table(otc_release *rel, const char *id, const otc_astro_tab **out)
{
    const cJSON *tables, *raw;
    otc_astro_tab *tab, *new_tab;
    otc_status st;
    size_t i;
    int first = 0, last = 0;
    if (out) *out = NULL;
#if !defined(OTC_WITH_PREDICT) || !OTC_WITH_PREDICT
    (void)rel; (void)id;
    return OTC_E_NOT_BUILT;
#endif
    if (!rel || !out) return OTC_E_INVALID_ARGUMENT;
    if (!id) for (i = 0; i < rel->n_conv; i++) {
        id = otc__jstr(rel->conv[i].json, "astro_table_id");
        if (id && *id) break;
    }
    if (!id) return OTC_E_NOT_FOUND;
    otc__mutex_lock(&rel->lock);
    for (tab = rel->astro; tab; tab = tab->next) if (otc__jstr_is(otc__jstr_item(tab->raw, "astro_table_id"), id)) {
        *out = tab; otc__mutex_unlock(&rel->lock); return OTC_OK;
    }
    otc__mutex_unlock(&rel->lock);
    tables = otc__jget(rel->meta, "astro_tables");
    raw = NULL;
    cJSON_ArrayForEach(raw, tables) if (otc__jstr_is(otc__jstr_item(raw, "astro_table_id"), id)) break;
    if (!raw) return OTC_E_NOT_FOUND;
    st = validate(rel, raw, &first, &last);
    if (st != OTC_OK) return st;
    new_tab = calloc(1, sizeof *new_tab);
    if (!new_tab) return otc__fail(rel, OTC_E_NOMEM, "cannot allocate astro table");
    new_tab->rel = rel; new_tab->raw = raw; new_tab->first = first; new_tab->last = last;
    otc__mutex_lock(&rel->lock);
    for (tab = rel->astro; tab; tab = tab->next) if (tab->raw == raw) break;
    if (tab) free(new_tab);
    else { new_tab->next = rel->astro; rel->astro = new_tab; tab = new_tab; }
    *out = tab;
    otc__mutex_unlock(&rel->lock);
    return OTC_OK;
}

otc_status otc__astro_row(const otc_astro_tab *tab, const char *name, const cJSON **out)
{
    const cJSON *row;
    if (out) *out = NULL;
    if (!tab || !out) return OTC_E_INVALID_ARGUMENT;
    row = name ? otc__jget(otc__jget(tab->raw, "constituents"), name) : NULL;
    if (!row || !cJSON_IsNumber(otc__jget(row, "speed_deg_per_hour")))
        return otc__fail(tab->rel, OTC_E_UNSUPPORTED_CONSTITUENT, "unsupported constituent %s", name ? name : "(null)");
    *out = row;
    return OTC_OK;
}

otc_status otc__astro_index(const otc_astro_tab *tab, int year, int *out)
{
    if (!tab || !out) return OTC_E_INVALID_ARGUMENT;
    if (year < tab->first || year > tab->last) return otc__fail(tab->rel, OTC_E_TIME_OUT_OF_RANGE, "year %d is outside the astro table (%d to %d)", year, tab->first, tab->last);
    *out = year - tab->first;
    return OTC_OK;
}

otc_status otc_astro_valid_range(const otc_astro_tab *tab, int *first, int *last)
{
    if (first) *first = 0;
    if (last) *last = 0;
#if !defined(OTC_WITH_PREDICT) || !OTC_WITH_PREDICT
    (void)tab; return OTC_E_NOT_BUILT;
#endif
    if (!tab || !first || !last) return OTC_E_INVALID_ARGUMENT;
    *first = tab->first; *last = tab->last;
    return OTC_OK;
}

static otc_status evaluate(const otc_astro_tab *tab, const char *name, int year, int64_t t, int yearly, int node, double *out)
{
    const cJSON *row;
    int index;
    otc_status st;
    if (out) *out = NAN;
#if !defined(OTC_WITH_PREDICT) || !OTC_WITH_PREDICT
    (void)tab; (void)name; (void)year; (void)t; (void)yearly; (void)node;
    return OTC_E_NOT_BUILT;
#endif
    if (!out || !tab) return OTC_E_INVALID_ARGUMENT;
    st = otc__astro_row(tab, name, &row);
    if (st != OTC_OK) return st;
    st = otc__astro_index(tab, year, &index);
    if (st != OTC_OK) return st;
    *out = cJSON_GetArrayItem(otc__jget(row, node ? "f" : "v0u_deg"), index)->valuedouble;
    if (!yearly && !node) *out = otc__angle(*out + otc__jnum(row, "speed_deg_per_hour") * ((t - otc__year_start(year)) / 3600.0));
    return OTC_OK;
}
otc_status otc_astro_equilibrium_argument(const otc_astro_tab *tab, const char *name, int64_t t, double *out) { return evaluate(tab, name, otc__year((double)t), t, 0, 0, out); }
otc_status otc_astro_node_factor(const otc_astro_tab *tab, const char *name, int64_t t, double *out) { return evaluate(tab, name, otc__year((double)t), t, 0, 1, out); }
otc_status otc_astro_equilibrium_for_year(const otc_astro_tab *tab, const char *name, int year, double *out) { return evaluate(tab, name, year, 0, 1, 0, out); }
otc_status otc_astro_node_factor_for_year(const otc_astro_tab *tab, const char *name, int year, double *out) { return evaluate(tab, name, year, 0, 1, 1, out); }
