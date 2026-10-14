/* Native selection, ordered prediction and one-link NOAA offsets. */
#include "otc_internal.h"

static double num(const cJSON *raw, const char *key, double fallback)
{
    const cJSON *v = otc__jget(raw, key);
    return cJSON_IsNumber(v) ? v->valuedouble : fallback;
}
static int is(const cJSON *raw, const char *key, const char *value) { return otc__jstr_is(otc__jstr_item(raw, key), value); }
static int predict_usable(const otc_set *set) { return set && (is(set->json, "qc_status", "ok") || is(set->json, "qc_status", "flagged")); }

void otc_predict_opts_init(otc_predict_opts *opts)
{
    if (!opts) return;
    memset(opts, 0, sizeof *opts); opts->struct_size = sizeof *opts; opts->step_s = 600;
}
void otc_prediction_info_init(otc_prediction_info *info)
{
    if (!info) return;
    memset(info, 0, sizeof *info); info->struct_size = sizeof *info; info->datum_uncertainty_m = NAN; info->method = OTC_PREDICTION_METHOD_UNSET;
}
void otc_prediction_info_clear(otc_prediction_info *info)
{
    if (!info || info->struct_size < sizeof *info) return;
    cJSON_Delete(info->_storage); otc_prediction_info_init(info);
}
const char *otc_prediction_method_name(otc_prediction_method value)
{
    switch (value) { case OTC_PREDICTION_METHOD_HARMONIC: return "harmonic"; case OTC_PREDICTION_METHOD_FOLDED_OFFSETS: return "folded_offsets"; case OTC_PREDICTION_METHOD_OFFSETS: return "offsets"; case OTC_PREDICTION_METHOD_OTHER: return "other"; case OTC_PREDICTION_METHOD_UNSET: return NULL; }
    return NULL;
}
const char *otc_extreme_type_name(otc_extreme_type_t value) { return value == OTC_EXTREME_TYPE_HIGH ? "high" : value == OTC_EXTREME_TYPE_LOW ? "low" : value == OTC_EXTREME_TYPE_OTHER ? "other" : NULL; }
const char *otc_current_event_type_name(otc_current_event_type_t value)
{
    switch (value) { case OTC_CURRENT_EVENT_TYPE_MAX_FLOOD: return "max_flood"; case OTC_CURRENT_EVENT_TYPE_MAX_EBB: return "max_ebb"; case OTC_CURRENT_EVENT_TYPE_SLACK_BEFORE_FLOOD: return "slack_before_flood"; case OTC_CURRENT_EVENT_TYPE_SLACK_BEFORE_EBB: return "slack_before_ebb"; case OTC_CURRENT_EVENT_TYPE_OTHER: return "other"; case OTC_CURRENT_EVENT_TYPE_UNSET: return NULL; }
    return NULL;
}

typedef struct context {
    otc_release *rel;
    const otc_station_t *station;
    otc_station_t *reference;
    const otc_set *set;
    const otc_astro_tab *table;
    const cJSON *offsets, *current_bin;
    otc_prediction_method method;
    int64_t bin, reference_bin;
    double sigma, subterm;
    const char *datum_name, *datum_kind;
    double uncertainty;
    otc__sum total, minor;
    uint32_t omitted;
    int has_omitted;
} context;

static void clear_context(context *c)
{
    otc__sum_clear(&c->total); otc__sum_clear(&c->minor); otc_station_free(c->reference);
}
static otc_status unavailable(context *c, const char *missing)
{
    return otc__fail(c->rel, OTC_E_DATUM_UNAVAILABLE, "datum is missing %s", missing ? missing : "(null)");
}
static otc_status datum(context *c, const cJSON *raw, const char *argument, int published, double *term)
{
    const char *requested = argument ? argument : "mean_level", *key;
    const cJSON *named = otc__jget(raw, "named"), *basis, *value;
    double mean = otc__jnum(raw, "msl_offset_m");
    if (!strcmp(requested, "mean_level") && !published) { c->datum_name = "mean_level"; *term = 0; return OTC_OK; }
    if (!isfinite(mean)) return unavailable(c, "msl_offset_m");
    if (!strcmp(requested, "zero") && !published) {
        c->datum_name = otc__jstr(raw, "zero_name");
        if (!c->datum_name) c->datum_name = otc__jstr(raw, "zero");
        if (!c->datum_name) c->datum_name = "unknown";
        *term = mean; return OTC_OK;
    }
    key = !strcmp(requested, "chart") ? otc__jstr(raw, "chart_datum") : requested;
    if (!key) return unavailable(c, "chart_datum");
    value = otc__jget(named, key);
    if (!cJSON_IsNumber(value)) return unavailable(c, key);
    basis = otc__jget(otc__jget(raw, "basis"), key);
    if (published && !is(basis, "kind", "published")) return unavailable(c, "published chart datum");
    c->datum_name = key; c->datum_kind = otc__jstr(basis, "kind"); c->uncertainty = otc__jnum(basis, "uncertainty_m");
    *term = mean - value->valuedouble;
    return OTC_OK;
}
static otc_status subdatum(context *c, const char *argument)
{
    const cJSON *raw = otc__jget(c->offsets, "datum"), *named = otc__jget(raw, "named"), *basis, *value;
    const char *chart = otc__jstr(raw, "chart_datum"), *key = !argument || !strcmp(argument, "chart") ? chart : argument;
    if (!argument || !strcmp(argument, "chart")) c->subterm = 0;
    else {
        value = otc__jget(named, key);
        if (!cJSON_IsNumber(value)) return unavailable(c, argument);
        c->subterm = (chart ? num(named, chart, 0) : 0) - value->valuedouble;
    }
    basis = key ? otc__jget(otc__jget(raw, "basis"), key) : NULL;
    c->datum_name = key; c->datum_kind = otc__jstr(basis, "kind"); c->uncertainty = otc__jnum(basis, "uncertainty_m");
    return OTC_OK;
}
static const cJSON *bin_row(const otc_station_t *station, const cJSON *bins, int64_t requested)
{
    const cJSON *row, *found = NULL;
    int64_t chosen = requested ? requested : otc__jint(station->root, "default_current_bin");
    if (chosen < 1) {
        cJSON_ArrayForEach(row, bins) if (otc__jint(row, "bin") > 0 && (!found || otc__jint(row, "bin") < otc__jint(found, "bin"))) found = row;
        chosen = found ? otc__jint(found, "bin") : 0;
    }
    cJSON_ArrayForEach(row, bins) if (otc__jint(row, "bin") == chosen) return row;
    return NULL;
}
static otc_status select_reference(context *c, const cJSON *offsets, const char *quantity, int64_t bin)
{
    otc_status st;
    size_t i;
    const char *id = otc__jstr(offsets, "reference_station_id");
    st = otc_station(c->rel, id, &c->reference);
    if (st != OTC_OK && st != OTC_E_NOT_FOUND) return st;
    c->set = NULL;
    if (c->reference) for (i = 0; i < c->reference->n_all; i++) {
        const otc_set *s = c->reference->order_all[i];
        if (predict_usable(s) && is(s->json, "quantity", quantity) &&
            ((!strcmp(quantity, "water_level") && is(s->json, "source", "noaa")) ||
             (!strcmp(quantity, "current") && bin_row(c->reference, otc__jget(s->json, "current_bins"), bin)))) { c->set = s; break; }
    }
    if (!c->set) return otc__fail(c->rel, OTC_E_REFERENCE_UNAVAILABLE, "reference %s has no usable set", id ? id : "(null)");
    if (c->rel->commercial_only) {
        const char *own_id = otc__jstr(offsets, "licence_id");
        const otc_licence *own = own_id ? otc__find_licence(c->rel, own_id) : NULL;
        if ((own_id && (!own || !own->commercial_use)) || !c->set->lic || !c->set->lic->commercial_use)
            return otc__fail(c->rel, OTC_E_REFERENCE_UNAVAILABLE, "reference %s has no usable set (commercial_only refuses reference licence %s)", id ? id : "(null)", own_id && (!own || !own->commercial_use) ? own_id : c->set->lic ? c->set->lic->id : "(null)");
    }
    return OTC_OK;
}
static otc_status select_table(context *c)
{
    const otc_convention *conv = c->set->conv;
    const char *id;
    otc_status st;
    if (!conv || !is(conv->json, "v0_model", "schureman_tcd") || !is(conv->json, "nodal_handling", "f_u_at_prediction"))
        return otc__fail(c->rel, OTC_E_UNSUPPORTED_CONVENTION, "unsupported convention %s", conv ? conv->id : "(null)");
    id = otc__jstr(conv->json, "astro_table_id");
    st = otc_astro_table(c->rel, id ? id : "", &c->table);
    if (st == OTC_E_NOT_FOUND) return otc__fail(c->rel, OTC_E_NO_ASTRO_TABLE,
        "release %s has no astro table \"%s\" for convention \"%s\". Format 1.0 requires astro_tables when a convention uses f_u_at_prediction (since the schema revision of site PR #45); this file was written before that revision or is invalid.",
        otc__jstr(c->rel->release_obj, "datestamp"), id ? id : "", conv->id);
    return st;
}
static otc_status current(context *c, const cJSON *row)
{
    otc_status st;
    double azimuth = num(row, "azimuth_deg", 0), flood = otc__jnum(row, "mean_flood_dir_deg");
    c->current_bin = row;
    c->sigma = !isfinite(flood) || cos((azimuth - flood) * OTC__RAD) >= 0 ? 1 : -1;
    st = otc__sum_init(&c->total, c->table, otc__jget(row, "constituents"), "major_amplitude_ms", "major_phase_deg", num(row, "mean_major_ms", 0), 1, 0);
    if (st != OTC_OK) return st;
    return otc__sum_init(&c->minor, c->table, otc__jget(row, "constituents"), "minor_amplitude_ms", "minor_phase_deg", num(row, "mean_minor_ms", 0), 1, 0);
}
static int historical_eligible(context *c)
{
    const cJSON *o = c->offsets, *s = c->set->json, *d = otc__jget(s, "datum");
    const cJSON *binding = otc__jget(otc__jget(o, "provenance"), "reference_binding");
    const char *ref = otc__jstr(o, "reference_station_id"), *sid = otc__jstr(s, "set_id");
    const char *lid = otc__jstr(o, "licence_id");
    const otc_licence *own = lid ? otc__find_licence(c->rel, lid) : NULL;
    if (!otc__historical_valid(o) || !own || !c->set->lic || !ref || !sid || strncmp(sid, ref, strlen(ref)) || sid[strlen(ref)] != '/') return 0;
    if (!is(s, "source", "noaa") || !is(s, "quantity", "water_level") || !is(s, "qc_status", "ok") || (otc__jget(s, "fallback") && !cJSON_IsNull(otc__jget(s, "fallback"))) ||
        !otc__jstr_same(otc__jstr_item(s, "source_record_id"), otc__jstr_item(binding, "noaa_id"))) return 0;
    if (!c->set->conv || !is(c->set->conv->json, "v0_model", "schureman_tcd") || !is(c->set->conv->json, "nodal_handling", "f_u_at_prediction")) return 0;
    if (!is(d, "chart_datum", "mllw") || !isfinite(otc__jnum(d, "msl_offset_m")) || num(otc__jget(d, "named"), "mllw", NAN) != 0 || !is(otc__jget(otc__jget(d, "basis"), "mllw"), "kind", "published")) return 0;
    return !c->rel->commercial_only || (own->commercial_use && c->set->lic->commercial_use);
}

static otc_status build_context(context *c, otc_release *rel, const otc_station_t *station, const otc_predict_opts *opts, const char *quantity, int series)
{
    const cJSON *tide, *currents, *row;
    const char *set_id = opts ? opts->set_id : NULL, *offset_id = opts ? opts->offset_id : NULL, *argument = opts ? opts->datum : NULL;
    int64_t bin = opts ? opts->bin_number : 0;
    otc_status st;
    int historical, ordinary, blocked_better;
    memset(c, 0, sizeof *c); c->rel = rel; c->station = station; c->uncertainty = NAN; c->sigma = 1;
#if !defined(OTC_WITH_PREDICT) || !OTC_WITH_PREDICT
    (void)quantity; (void)series; (void)set_id; (void)offset_id; (void)argument; (void)bin;
    return OTC_E_NOT_BUILT;
#endif
    if (!rel || !station || station->rel != rel || (opts && opts->struct_size < sizeof *opts)) return OTC_E_INVALID_ARGUMENT;
    if (bin < 0 || bin > INT64_C(9007199254740991) || (set_id && offset_id)) return otc__fail(rel, OTC_E_INVALID_ARGUMENT, "invalid prediction selection options");
    c->set = station->rec;
    if (set_id) {
        size_t i;
        c->set = NULL;
        for (i = 0; i < station->n_sets; i++) if (is(station->sets[i].json, "set_id", set_id)) { c->set = &station->sets[i]; break; }
        if (!c->set || (rel->commercial_only && (!c->set->lic || !c->set->lic->commercial_use))) return otc__fail(rel, OTC_E_INVALID_ARGUMENT, "set_id %s is unavailable%s", set_id, rel->commercial_only ? " (commercial_only)" : "");
    }
    ordinary = predict_usable(c->set);
    tide = otc__jget(station->root, "subordinate_offsets");
    currents = otc__jget(station->root, "current_offsets");
    historical = otc__jstr(tide, "offset_id") != NULL;
    if (offset_id) {
        if (!historical || !is(tide, "offset_id", offset_id)) return otc__fail(rel, OTC_E_INVALID_ARGUMENT, "offset_id is not a profile of this station");
        ordinary = 0;
    }
    blocked_better = historical && !offset_id && (ordinary || otc__ordinary_path(rel, otc__find_entry(rel, otc__jstr(station->root, "station_id"))));
    if (!set_id && !ordinary && is(station->root, "type", "subordinate") && ((cJSON_IsObject(tide) && !blocked_better) || cJSON_IsArray(currents))) {
        if (cJSON_IsObject(tide)) {
            double refterm, ht, lt, hh, lh, identity;
            context refcontext;
            int ratio;
            c->offsets = tide;
            if (strcmp(quantity, "water_level")) return otc__fail(rel, OTC_E_QUANTITY_MISMATCH, "tide offsets need water_level");
            ratio = is(tide, "height_adjusted_type", "R");
            if (!ratio && !is(tide, "height_adjusted_type", "A")) return otc__fail(rel, OTC_E_INVALID_ARGUMENT, "height_adjusted_type %s is not R or A", otc__jstr(tide, "height_adjusted_type") ? otc__jstr(tide, "height_adjusted_type") : "(null)");
            if (historical && rel->historical_excluded) return otc__fail(rel, OTC_E_HISTORICAL_OFFSETS_EXCLUDED, "historical_offsets_policy=exclude refuses historical prediction");
            st = select_reference(c, tide, quantity, 0); if (st != OTC_OK) return st;
            if (historical && (blocked_better || !historical_eligible(c))) return otc__fail(rel, OTC_E_NO_CONSTANTS, "historical offsets are ineligible");
            st = select_table(c); if (st != OTC_OK) return st;
            st = otc__sum_init(&c->total, c->table, otc__jget(c->set->json, "constituents"), "amplitude_m", "phase_deg", 0, 1, 0); if (st != OTC_OK) return st;
            refcontext = *c;
            st = datum(&refcontext, otc__jget(c->set->json, "datum"), "chart", 1, &refterm); if (st != OTC_OK) return st;
            st = subdatum(c, argument); if (st != OTC_OK) return st;
            ht = num(tide, "time_offset_high_min", 0); lt = num(tide, "time_offset_low_min", 0);
            identity = ratio ? 1 : 0; hh = num(tide, "height_offset_high", identity); lh = num(tide, "height_offset_low", identity);
            if (ratio && (hh <= 0 || lh <= 0)) return otc__fail(rel, OTC_E_INVALID_ARGUMENT, "height_offset ratio must be positive");
            if (ht == lt && hh == lh) {
                c->method = OTC_PREDICTION_METHOD_FOLDED_OFFSETS;
                otc__sum_clear(&c->total);
                return otc__sum_init(&c->total, c->table, otc__jget(c->set->json, "constituents"), "amplitude_m", "phase_deg", (ratio ? hh : 1) * refterm + (ratio ? 0 : hh) + c->subterm, ratio ? hh : 1, ht / 60.0);
            }
            c->method = OTC_PREDICTION_METHOD_OFFSETS; c->total.mean = refterm;
            return series ? otc__fail(rel, OTC_E_EXTREMES_ONLY, "high and low water offsets differ, so the station has no exact curve") : OTC_OK;
        }
        if (strcmp(quantity, "current")) return otc__fail(rel, OTC_E_QUANTITY_MISMATCH, "current offsets need current");
        row = bin_row(station, currents, bin);
        if (!row) return otc__fail(rel, OTC_E_BIN_NOT_FOUND, "bin_number is not available");
        c->offsets = row; c->reference_bin = otc__jint(row, "reference_bin"); c->bin = otc__jint(row, "bin"); c->method = OTC_PREDICTION_METHOD_OFFSETS;
        st = select_reference(c, row, quantity, c->reference_bin); if (st != OTC_OK) return st;
        st = select_table(c); if (st != OTC_OK) return st;
        row = bin_row(c->reference, otc__jget(c->set->json, "current_bins"), c->reference_bin);
        if (!row) return otc__fail(rel, OTC_E_BIN_NOT_FOUND, "reference bin_number is not available");
        st = current(c, row); if (st != OTC_OK) return st;
        return series ? otc__fail(rel, OTC_E_EXTREMES_ONLY, "subordinate currents provide events only") : OTC_OK;
    }
    if (!ordinary) return otc__fail(rel, OTC_E_NO_CONSTANTS, "no usable constants%s", rel->commercial_only ? " (commercial_only)" : "");
    if (!is(c->set->json, "quantity", quantity)) return otc__fail(rel, OTC_E_QUANTITY_MISMATCH, "%s requires that quantity of constants", quantity);
    st = select_table(c); if (st != OTC_OK) return st;
    if (!strcmp(quantity, "water_level")) {
        st = otc__sum_init(&c->total, c->table, otc__jget(c->set->json, "constituents"), "amplitude_m", "phase_deg", 0, 1, 0);
        return st == OTC_OK ? datum(c, otc__jget(c->set->json, "datum"), argument, 0, &c->total.mean) : st;
    }
    row = bin_row(station, otc__jget(c->set->json, "current_bins"), bin);
    if (!row) return otc__fail(rel, OTC_E_BIN_NOT_FOUND, "bin_number is not available");
    c->bin = otc__jint(row, "bin");
    return current(c, row);
}

static const char *own_string(cJSON *storage, const char *key, const char *value)
{
    cJSON *item;
    if (!value) return NULL;
    item = cJSON_AddStringToObject(storage, key, value);
    return item ? item->valuestring : NULL;
}
static otc_status result_info(context *c, const otc_predict_opts *opts, int tides)
{
    otc_prediction_info *info = opts ? opts->info : NULL;
    cJSON *storage;
    const cJSON *vintage;
    if (!info) return OTC_OK;
    if (info->struct_size < sizeof *info) return OTC_E_INVALID_ARGUMENT;
    storage = cJSON_CreateObject();
    if (!storage) return OTC_E_NOMEM;
    otc_prediction_info_clear(info); info->_storage = storage;
#define COPY(field, value) do { const char *source_ = (value); info->field = own_string(storage, #field, source_); if (source_ && !info->field) { otc_prediction_info_clear(info); return OTC_E_NOMEM; } } while (0)
    COPY(station_id, otc__jstr(c->station->root, "station_id")); COPY(timezone, otc__jstr(c->station->root, "timezone"));
    COPY(set_id, otc__jstr(c->set->json, "set_id")); COPY(convention_id, c->set->conv->id); COPY(astro_table_id, otc__jstr(c->table->raw, "astro_table_id"));
    COPY(reference_station_id, c->reference ? otc__jstr(c->reference->root, "station_id") : NULL);
    COPY(datum, tides && opts ? opts->datum : NULL); COPY(datum_name, c->datum_name); COPY(datum_kind, c->datum_kind);
    COPY(release, otc__jstr(c->rel->release_obj, "datestamp")); COPY(algorithm, "otc-predict-1");
    info->method = c->method; info->reference_bin = c->reference_bin; info->bin_number = c->bin;
    info->datum_uncertainty_m = c->uncertainty; info->omitted_event_types = c->omitted; info->has_omitted_event_types = c->has_omitted != 0;
    if (tides && otc__jstr(c->offsets, "offset_id")) {
        vintage = otc__jget(c->offsets, "vintage");
        info->set_id = NULL; info->historical_offsets = true;
        COPY(offset_id, otc__jstr(c->offsets, "offset_id")); COPY(offset_source, otc__jstr(c->offsets, "source")); COPY(offset_source_version, otc__jstr(c->offsets, "source_version"));
        COPY(current_validity, otc__jstr(vintage, "current_validity")); COPY(current_accuracy, otc__jstr(vintage, "current_accuracy"));
        COPY(reference_set_id, otc__jstr(c->set->json, "set_id")); COPY(reference_source_version, otc__jstr(c->set->json, "source_version")); COPY(reference_2020_equivalence, otc__jstr(vintage, "reference_2020_equivalence"));
        COPY(source_note, "OTC historical-offset calculation using NOAA2020 parameters; retired NOAA profile; current validity unestablished; current accuracy unverified.");
    }
#undef COPY
    return OTC_OK;
}

static void reset_info(const otc_predict_opts *opts)
{
    if (opts && opts->struct_size >= sizeof *opts && opts->info && opts->info->struct_size >= sizeof *opts->info)
        otc_prediction_info_clear(opts->info);
}
int otc__prediction_available(void)
{
#if defined(OTC_WITH_PREDICT) && OTC_WITH_PREDICT
    return 1;
#else
    return 0;
#endif
}

otc_status otc__prediction_window(
otc_release *rel, const otc_predict_opts *opts, int64_t start, int64_t stop, int series)
{
#if !defined(OTC_WITH_PREDICT) || !OTC_WITH_PREDICT
    (void)rel; (void)opts; (void)start; (void)stop; (void)series; return OTC_E_NOT_BUILT;
#endif
    if (opts && opts->struct_size < sizeof *opts) return OTC_E_INVALID_ARGUMENT;
    reset_info(opts);
    if (!otc__year((double)start) || !otc__year((double)stop) || start > stop || (series && opts && opts->step_s <= 0))
        return otc__fail(rel, OTC_E_INVALID_ARGUMENT, "invalid prediction window or step_s");
    return OTC_OK;
}
static otc_status finish(context *c, otc_status st, const otc_predict_opts *opts, int tides)
{
    if (st == OTC_OK || st == OTC_E_BUFFER_TOO_SMALL) {
        otc_status metadata = result_info(c, opts, tides);
        if (metadata != OTC_OK) st = metadata;
    }
    if (st != OTC_OK && st != OTC_E_BUFFER_TOO_SMALL) reset_info(opts);
    clear_context(c);
    return st;
}

static otc_status finish_count(context *c, otc_status st, const otc_predict_opts *opts, int tides, size_t *count)
{
    st = finish(c, st, opts, tides);
    if (st != OTC_OK && st != OTC_E_BUFFER_TOO_SMALL && count) *count = 0;
    return st;
}

otc_status otc_heights_at(otc_release *rel, const otc_station_t *station, const otc_predict_opts *opts, const int64_t *times, size_t n, otc_height_t *out)
{
    context c;
    size_t i;
    otc_status st;
#if !defined(OTC_WITH_PREDICT) || !OTC_WITH_PREDICT
    (void)rel; (void)station; (void)opts; (void)times; (void)n; (void)out; return OTC_E_NOT_BUILT;
#endif
    reset_info(opts);
    if ((n && (!times || !out)) || (opts && opts->struct_size < sizeof *opts)) return OTC_E_INVALID_ARGUMENT;
    for (i = 0; i < n; i++) if (!otc__year((double)times[i])) return OTC_E_INVALID_ARGUMENT;
    st = build_context(&c, rel, station, opts, "water_level", 1);
    if (st != OTC_OK) return finish(&c, st, opts, 1);
    for (i = 0; i < n; i++) {
        out[i].t = times[i]; st = otc__sum_value(&c.total, (double)times[i], 0, 0, &out[i].height_m);
        if (st != OTC_OK) break;
    }
    return finish(&c, st, opts, 1);
}

otc_status otc_heights(otc_release *rel, const otc_station_t *station, const otc_predict_opts *opts, int64_t start, int64_t stop, otc_height_t *out, size_t cap, size_t *count)
{
    context c;
    otc_status st;
    size_t i, n;
    int64_t step = opts ? opts->step_s : 600;
    if (count) *count = 0;
    st = otc__prediction_window(rel, opts, start, stop, 1); if (st != OTC_OK) return st;
    if (!count || (!out && cap)) return OTC_E_INVALID_ARGUMENT;
    st = build_context(&c, rel, station, opts, "water_level", 1); if (st != OTC_OK) return finish_count(&c, st, opts, 1, count);
    n = (size_t)((stop - start) / step + ((stop - start) % step != 0));
    for (i = 0; i < n; i++) {
        double value;
        int64_t t = start + (int64_t)i * step;
        st = otc__sum_value(&c.total, (double)t, 0, 0, &value); if (st != OTC_OK) break;
        if (i < cap) { out[i].t = t; out[i].height_m = value; }
    }
    if (st == OTC_OK) { *count = n; if (cap < n) st = OTC_E_BUFFER_TOO_SMALL; }
    return finish_count(&c, st, opts, 1, count);
}

static int rounded_order(const void *aa, const void *bb)
{
    const otc__event *a = aa, *b = bb;
    double at = floor(a->t + 0.5), bt = floor(b->t + 0.5);
    if (at < bt) return -1;
    if (at > bt) return 1;
    return a->sequence < b->sequence ? -1 : a->sequence > b->sequence;
}
otc_status otc_extremes(otc_release *rel, const otc_station_t *station, const otc_predict_opts *opts, int64_t start, int64_t stop, otc_extreme_t *out, size_t cap, size_t *count)
{
    context c;
    otc__events events;
    otc_status st;
    size_t i, n = 0;
    double margin = 0;
    if (count) *count = 0;
    st = otc__prediction_window(rel, opts, start, stop, 0); if (st != OTC_OK) return st;
    if (!count || (!out && cap)) return OTC_E_INVALID_ARGUMENT;
    st = build_context(&c, rel, station, opts, "water_level", 0); if (st != OTC_OK) return finish_count(&c, st, opts, 1, count);
    if (c.method == OTC_PREDICTION_METHOD_OFFSETS && start != stop)
        margin = fmax(120.0, fmax(fabs(num(c.offsets, "time_offset_high_min", 0)), fabs(num(c.offsets, "time_offset_low_min", 0))) + 60.0) * 60.0;
    st = otc__events_find(&c.total, start - margin, stop + margin, 0, &events);
    if (st == OTC_OK) {
        if (c.method == OTC_PREDICTION_METHOD_OFFSETS) {
            for (i = 0; i < events.n; i++) {
                int high = events.items[i].kind == OTC_EXTREME_TYPE_HIGH;
                events.items[i].t += num(c.offsets, high ? "time_offset_high_min" : "time_offset_low_min", 0) * 60.0;
                if (is(c.offsets, "height_adjusted_type", "R")) events.items[i].value *= num(c.offsets, high ? "height_offset_high" : "height_offset_low", 1);
                else events.items[i].value += num(c.offsets, high ? "height_offset_high" : "height_offset_low", 0);
                events.items[i].value += c.subterm;
            }
            qsort(events.items, events.n, sizeof *events.items, rounded_order);
        }
        for (i = 0; i < events.n; i++) {
            int64_t t = (int64_t)floor(events.items[i].t + 0.5);
            if (t < start || t >= stop) continue;
            if (n < cap) { out[n].t = t; out[n].type = (otc_extreme_type_t)events.items[i].kind; out[n].height_m = events.items[i].value; }
            n++;
        }
        *count = n; if (cap < n) st = OTC_E_BUFFER_TOO_SMALL;
    }
    otc__events_clear(&events);
    return finish_count(&c, st, opts, 1, count);
}

otc_status otc_currents(otc_release *rel, const otc_station_t *station, const otc_predict_opts *opts, int64_t start, int64_t stop, otc_current_t *out, size_t cap, size_t *count)
{
    context c;
    otc_status st;
    size_t i, n;
    int64_t step = opts ? opts->step_s : 600;
    double theta;
    if (count) *count = 0;
    st = otc__prediction_window(rel, opts, start, stop, 1); if (st != OTC_OK) return st;
    if (!count || (!out && cap)) return OTC_E_INVALID_ARGUMENT;
    st = build_context(&c, rel, station, opts, "current", 1); if (st != OTC_OK) return finish_count(&c, st, opts, 0, count);
    theta = num(c.current_bin, "azimuth_deg", 0) * OTC__RAD;
    n = (size_t)((stop - start) / step + ((stop - start) % step != 0));
    for (i = 0; i < n; i++) {
        double major, minor, east, north, speed;
        int64_t t = start + (int64_t)i * step;
        st = otc__sum_value(&c.total, (double)t, 0, 0, &major); if (st != OTC_OK) break;
        st = otc__sum_value(&c.minor, (double)t, 0, 0, &minor); if (st != OTC_OK) break;
        east = major * sin(theta) + minor * sin(theta + 3.14159265358979323846 / 2.0);
        north = major * cos(theta) + minor * cos(theta + 3.14159265358979323846 / 2.0);
        speed = hypot(east, north);
        if (i < cap) {
            out[i].t = t; out[i].velocity_major_ms = c.sigma * major; out[i].velocity_minor_ms = c.sigma * minor;
            out[i].speed_ms = speed; out[i].direction_deg = speed < 1e-9 ? NAN : otc__angle(atan2(east, north) / OTC__RAD);
        }
    }
    if (st == OTC_OK) { *count = n; if (cap < n) st = OTC_E_BUFFER_TOO_SMALL; }
    return finish_count(&c, st, opts, 0, count);
}

typedef otc__current_candidate current_candidate;
static int candidate_order(const void *aa, const void *bb)
{
    const current_candidate *a = aa, *b = bb;
    if (a->event.t < b->event.t) return -1;
    if (a->event.t > b->event.t) return 1;
    return a->event.sequence < b->event.sequence ? -1 : a->event.sequence > b->event.sequence;
}
static int candidate_rounded_order(const void *aa, const void *bb) { return rounded_order(&((const current_candidate *)aa)->event, &((const current_candidate *)bb)->event); }

otc_status otc__current_candidate_assembly(const cJSON *selected_bin, const otc__events *extrema, const otc__events *slack,
    otc__current_candidate **out, size_t *count)
{
    current_candidate *candidates = NULL;
    size_t i, n = 0;
    if (extrema->n > SIZE_MAX - slack->n || extrema->n + slack->n > SIZE_MAX / sizeof *candidates) { return OTC_E_NOMEM; }
    if (extrema->n + slack->n && !(candidates = calloc(extrema->n + slack->n, sizeof *candidates))) { return OTC_E_NOMEM; }
    for (i = 0; i < extrema->n; i++) {
        otc__event e = extrema->items[i];
        if (e.kind == OTC_EXTREME_TYPE_HIGH && e.value > 0) { e.kind = OTC_CURRENT_EVENT_TYPE_MAX_FLOOD; candidates[n].direction = otc__jnum(selected_bin, "mean_flood_dir_deg"); }
        else if (e.kind == OTC_EXTREME_TYPE_LOW && e.value < 0) { e.kind = OTC_CURRENT_EVENT_TYPE_MAX_EBB; candidates[n].direction = otc__jnum(selected_bin, "mean_ebb_dir_deg"); }
        else continue;
        e.sequence = n; candidates[n++].event = e;
    }
    for (i = 0; i < slack->n; i++) { candidates[n].event = slack->items[i]; candidates[n].event.sequence = n; candidates[n++].direction = NAN; }
    qsort(candidates, n, sizeof *candidates, candidate_order);

    *out = candidates; *count = n;
    return OTC_OK;
}

otc_status otc_current_events(otc_release *rel, const otc_station_t *station, const otc_predict_opts *opts, int64_t start, int64_t stop, otc_current_event_t *out, size_t cap, size_t *count)
{
    context c;
    otc__sum total;
    otc__events extrema = {0}, slack = {0};
    current_candidate *candidates = NULL;
    size_t i, n = 0, written = 0;
    otc_status st;
    double margin = 0;
    const char *time_keys[] = {"time_adj_max_flood_min", "time_adj_max_ebb_min", "time_adj_slack_before_flood_min", "time_adj_slack_before_ebb_min"};
    unsigned kept = 15;
    memset(&total, 0, sizeof total);
    if (count) *count = 0;
    st = otc__prediction_window(rel, opts, start, stop, 0); if (st != OTC_OK) return st;
    if (!count || (!out && cap)) return OTC_E_INVALID_ARGUMENT;
    st = build_context(&c, rel, station, opts, "current", 0); if (st != OTC_OK) return finish_count(&c, st, opts, 0, count);
    if (c.method == OTC_PREDICTION_METHOD_OFFSETS) {
        kept = 0; c.has_omitted = 1;
        for (i = 0; i < 4; i++) if (isfinite(otc__jnum(c.offsets, time_keys[i])) && (i >= 2 || isfinite(otc__jnum(c.offsets, i == 0 ? "flood_amp_ratio" : "ebb_amp_ratio")))) {
            kept |= 1u << i; margin = fmax(margin, fabs(otc__jnum(c.offsets, time_keys[i])));
        }
        c.omitted = 15u ^ kept; margin = fmax(120.0, margin + 60.0) * 60.0;
    }
    st = otc__sum_init(&total, c.table, otc__jget(c.current_bin, "constituents"), "major_amplitude_ms", "major_phase_deg", c.sigma * num(c.current_bin, "mean_major_ms", 0), c.sigma, 0);
    if (st != OTC_OK) goto done;
    if (start != stop) {
        st = otc__events_find(&total, start - margin, stop + margin, 0, &extrema); if (st != OTC_OK) goto done;
        st = otc__events_find(&total, start - margin, stop + margin, 1, &slack); if (st != OTC_OK) goto done;
    }
    st = otc__current_candidate_assembly(c.current_bin, &extrema, &slack, &candidates, &n);
    if (st != OTC_OK) goto done;
    if (c.method == OTC_PREDICTION_METHOD_OFFSETS) {
        size_t retained = 0;
        for (i = 0; i < n; i++) {
            int kind = candidates[i].event.kind;
            if (!(kept & (1u << kind))) continue;
            candidates[i].event.t += otc__jnum(c.offsets, time_keys[kind]) * 60.0;
            if (kind < 2) {
                candidates[i].event.value *= otc__jnum(c.offsets, kind == 0 ? "flood_amp_ratio" : "ebb_amp_ratio");
                candidates[i].direction = otc__jnum(c.offsets, kind == 0 ? "mean_flood_dir_deg" : "mean_ebb_dir_deg");
            }
            candidates[i].event.sequence = i; candidates[retained++] = candidates[i];
        }
        n = retained; qsort(candidates, n, sizeof *candidates, candidate_rounded_order);
    }
    for (i = 0; i < n; i++) {
        int64_t t = (int64_t)floor(candidates[i].event.t + 0.5);
        if (t < start || t >= stop) continue;
        if (written < cap) {
            out[written].t = t; out[written].type = (otc_current_event_type_t)candidates[i].event.kind;
            out[written].velocity_ms = candidates[i].event.value; out[written].direction_deg = candidates[i].direction;
        }
        written++;
    }
    *count = written; if (cap < written) st = OTC_E_BUFFER_TOO_SMALL;
done:
    free(candidates); otc__events_clear(&extrema); otc__events_clear(&slack); otc__sum_clear(&total);
    return finish_count(&c, st, opts, 0, count);
}

static int datum_key_order(const void *aa, const void *bb)
{
    return strcmp(((const otc_datum_level *)aa)->key, ((const otc_datum_level *)bb)->key);
}
static double range_difference(const cJSON *named, const cJSON *basis, const char *a, const char *b)
{
    const cJSON *high = otc__jget(basis,a), *low = otc__jget(basis,b);
    const char *kind = otc__jstr(high,"kind");
    double h = otc__jnum(named,a), l = otc__jnum(named,b);
    const cJSON *he = otc__jget(high,"epoch"), *le = otc__jget(low,"epoch");
    if (!isfinite(h) || !isfinite(l) || !kind || !is(low,"kind",kind)) return NAN;
    if ((!he || cJSON_IsNull(he)) && (!le || cJSON_IsNull(le))) return h-l;
    return he && le && cJSON_Compare(he,le,1) ? h-l : NAN;
}

otc_status otc_datums(otc_release *rel, const otc_station_t *station, const char *set_id, otc_datum_info *info, otc_datum_level *out, size_t cap, size_t *count)
{
    const otc_set *set;
    const cJSON *d, *named, *basis, *value;
    otc_datum_level *levels = NULL;
    size_t i=0,n,j;
    const char *flag_names[] = {"time_base_unverified","time_base_disputed","sampling_assumed","truncated_lows","gaps","segment","short_record","no_qualified_control","microtidal","provisional"};
    if (count) *count=0;
    if (info) { memset(info,0,sizeof *info); info->msl_offset_m=info->mn=info->gt=info->dhq=info->dlq=NAN; }
#if !defined(OTC_WITH_PREDICT) || !OTC_WITH_PREDICT
    (void)rel; (void)station; (void)set_id; (void)out; (void)cap; return OTC_E_NOT_BUILT;
#endif
    if (!rel || !station || station->rel!=rel || !info || !count || (!out && cap)) return OTC_E_INVALID_ARGUMENT;
    set=station->rec;
    if (set_id) {
        set=NULL;
        for (i=0;i<station->n_sets;i++) if (is(station->sets[i].json,"set_id",set_id)) { set=&station->sets[i]; break; }
        if (!set || (rel->commercial_only && (!set->lic || !set->lic->commercial_use))) return otc__fail(rel,OTC_E_INVALID_ARGUMENT,"set_id is unavailable%s",rel->commercial_only ? " (commercial_only)" : "");
    }
    if (set) { d=otc__jget(set->json,"datum"); info->set_id=otc__jstr(set->json,"set_id"); }
    else {
        const cJSON *offsets=otc__jget(station->root,"subordinate_offsets");
        if (!cJSON_IsObject(offsets)) return OTC_E_NOT_FOUND;
        d=otc__jget(offsets,"datum");
    }
    info->zero=otc__jstr(d,"zero"); info->zero_name=otc__jstr(d,"zero_name"); info->chart_datum=otc__jstr(d,"chart_datum");
    info->msl_offset_m=otc__jnum(d,"msl_offset_m"); info->has_msl_offset=isfinite(info->msl_offset_m);
    named=otc__jget(d,"named"); basis=otc__jget(d,"basis"); n=(size_t)cJSON_GetArraySize(named);
    if (n && !(levels=calloc(n,sizeof *levels))) return OTC_E_NOMEM;
    i=0;
    cJSON_ArrayForEach(value,named) {
        const cJSON *b=otc__jget(basis,value->string), *epoch=otc__jget(b,"epoch"), *span=otc__jget(b,"data_span"), *control=otc__jget(b,"control"), *flag;
        otc_datum_level *l=&levels[i++];
        l->key=value->string; l->value_m=value->valuedouble;
        l->above_chart_m=info->chart_datum ? l->value_m - otc__jnum(named,info->chart_datum) : NAN; l->has_above_chart=isfinite(l->above_chart_m);
        l->kind=otc__jstr(b,"kind"); l->method=otc__jstr(b,"method"); l->source_name=otc__jstr(b,"source_name");
        l->epoch_start=otc__jstr(epoch,"start"); l->epoch_end=otc__jstr(epoch,"end"); l->epoch_name=otc__jstr(epoch,"name");
        l->data_start=otc__jstr(span,"start"); l->data_end=otc__jstr(span,"end"); l->data_months=otc__jint(span,"months");
        l->control_station_id=otc__jstr(control,"station_id"); l->control_set_id=otc__jstr(control,"set_id"); l->control_source_id=otc__jstr(control,"source_id");
        l->uncertainty_m=otc__jnum(b,"uncertainty_m"); l->has_uncertainty=isfinite(l->uncertainty_m); l->uncertainty_basis=otc__jstr(b,"uncertainty_basis");
        cJSON_ArrayForEach(flag,otc__jget(b,"flags")) for (j=0;j<10;j++) if (otc__jstr_is(flag,flag_names[j])) l->flags |= 1u<<j;
    }
    qsort(levels,n,sizeof *levels,datum_key_order);
    if (out && cap) memcpy(out,levels,(cap<n ? cap : n)*sizeof *levels);
    free(levels);
    info->mn=range_difference(named,basis,"mhw","mlw"); info->gt=range_difference(named,basis,"mhhw","mllw");
    info->dhq=range_difference(named,basis,"mhhw","mhw"); info->dlq=range_difference(named,basis,"mlw","mllw");
    *count=n;
    return cap<n ? OTC_E_BUFFER_TOO_SMALL : OTC_OK;
}

otc_status otc__selected_datum_term(const otc_release *rel, const otc_station_t *station,
                                  const otc_set *set, const char *argument, double *out)
{
    context c;
#if !defined(OTC_WITH_PREDICT) || !OTC_WITH_PREDICT
    (void)rel; (void)station; (void)set; (void)argument; (void)out;
    return OTC_E_NOT_BUILT;
#endif
    if (!rel || !station || !set || !out || station->rel != rel || set->station != station)
        return OTC_E_INVALID_ARGUMENT;
    memset(&c, 0, sizeof c);
    c.rel = (otc_release *)rel; c.station = station; c.set = set; c.uncertainty = NAN;
    return datum(&c, otc__jget(set->json, "datum"), argument, 0, out);
}
