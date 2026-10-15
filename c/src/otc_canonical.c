#include "otc_canonical.h"
#include "otc_internal.h"
/* Closed source-JSON representation bridge. The existing native parser and
 * cache encoder retain all parsing/escaping/numeric policy. */
static cJSON *canonical_source_json(const otc_cp_JsonValue *value)
{
    cJSON *result = NULL, *child;
    size_t i;
    if (!value) return NULL;
    switch (value->tag) {
    case OTC_CP_JSON_NULL: return cJSON_CreateNull();
    case OTC_CP_JSON_BOOLEAN: return cJSON_CreateBool(value->value.boolean);
    case OTC_CP_JSON_NUMBER: return cJSON_CreateNumber(value->value.number);
    case OTC_CP_JSON_STRING: {
        char *text = otc__json_escape_n(value->value.string.bytes, value->value.string.count);
        if (text) { result = otc__json_parse(text, strlen(text)); free(text); }
        return result;
    }
    case OTC_CP_JSON_ARRAY:
        if (value->value.array.count && !value->value.array.items) return NULL;
        result = cJSON_CreateArray();
        for (i = 0; result && i < value->value.array.count; i++) {
            child = canonical_source_json(&value->value.array.items[i]);
            if (!child || !cJSON_AddItemToArray(result, child)) { cJSON_Delete(child); cJSON_Delete(result); return NULL; }
        }
        return result;
    case OTC_CP_JSON_OBJECT:
        if (value->value.members.count && !value->value.members.entries) return NULL;
        result = cJSON_CreateObject();
        for (i = 0; result && i < value->value.members.count; i++) {
            const otc_cp_JsonPair *pair = &value->value.members.entries[i];
            child = canonical_source_json(pair->value);
            if (!pair->key || !child || !cJSON_AddItemToObject(result, pair->key, child)) { cJSON_Delete(child); cJSON_Delete(result); return NULL; }
        }
        return result;
    }
    return NULL;
}

struct otc_cp_prepared_astronomy { otc__sum sum; };

void otc__canonical_astronomy_clear(otc_cp_astronomical_terms *terms)
{
    if (!terms) return;
    if (terms->native_owner) { otc__sum_clear(&terms->native_owner->sum); free(terms->native_owner); }
    free((otc_cp_astronomical_terms_constituent_terms_item *)terms->constituent_terms.items);
    memset(terms, 0, sizeof *terms);
}

static otc_status canonical_model_table(const otc_cp_selected_prediction_model *model, const otc_astro_tab **out)
{
    const otc_astro_tab *table;
    cJSON *declared;
    if (!model || !model->release_view.value || !model->station.value || !model->constant_set.value || !model->convention.value ||
        model->station.value->rel != model->release_view.value || model->constant_set.value->station != model->station.value ||
        model->constant_set.value->conv != model->convention.value) return OTC_E_INVALID_ARGUMENT;
    table = model->native_table;
    if (!table) {
        declared = canonical_source_json(&model->astro_table);
        if (!declared) return OTC_E_INVALID_ARGUMENT;
        /* Locate the already-loaded, validated table supplied by the model;
         * this does not select or load a table. */
        for (table = model->release_view.value->astro; table; table = table->next)
            if (cJSON_Compare(table->raw, declared, 1)) break;
        cJSON_Delete(declared);
    }
    if (!table || table->rel != model->release_view.value) return OTC_E_NO_ASTRO_TABLE;
    *out = table;
    return OTC_OK;
}

static cJSON *canonical_writer_string(const char *bytes, size_t length, bool supplied_length)
{
    char *encoded; cJSON *value;
    if (!bytes) return NULL;
    encoded = otc__json_escape_n(bytes, supplied_length ? length : strlen(bytes));
    if (!encoded) return NULL;
    value = otc__json_parse(encoded, strlen(encoded)); free(encoded); return value;
}

static cJSON *canonical_track_json(cJSON *owner, cJSON *value)
{
    if (!value) return NULL;
    if (!cJSON_AddItemToArray(owner, value)) { cJSON_Delete(value); return NULL; }
    return value;
}

static otc_status canonical_cache_document(const otc_cp_cache_document *input, cJSON **out)
{
    cJSON *result = NULL, *owner;
    if (!input || !out) return OTC_E_INVALID_ARGUMENT;
    *out = NULL;
    owner = cJSON_CreateArray();
    if (!owner) return OTC_E_NOMEM;
    switch (input->tag) {
    case 0: {
        result = canonical_track_json(owner, cJSON_CreateObject());
        if (!result) goto no_memory;
        if ((input->value.stream_index).has_presence && ((input->value.stream_index).present_fields & UINT64_C(255)) != UINT64_C(255)) goto invalid;
        if (!(input->value.stream_index).has_presence || ((input->value.stream_index).present_fields & (UINT64_C(1) << 0)))         {
            cJSON *child1 = NULL;
            child1 = canonical_track_json(owner, cJSON_CreateNumber(((input->value.stream_index).index_version).value));
            if (!child1) goto no_memory;
            cJSON_DetachItemViaPointer(owner, child1);
            if (!cJSON_AddItemToObject(result, "index_version", child1)) { cJSON_Delete(child1); goto no_memory; }
        }
        if (!(input->value.stream_index).has_presence || ((input->value.stream_index).present_fields & (UINT64_C(1) << 1)))         {
            cJSON *child2 = NULL;
            child2 = canonical_track_json(owner, cJSON_CreateNumber(((input->value.stream_index).discovery_index_version).value));
            if (!child2) goto no_memory;
            cJSON_DetachItemViaPointer(owner, child2);
            if (!cJSON_AddItemToObject(result, "discovery_index_version", child2)) { cJSON_Delete(child2); goto no_memory; }
        }
        if (!(input->value.stream_index).has_presence || ((input->value.stream_index).present_fields & (UINT64_C(1) << 2)))         {
            cJSON *child3 = NULL;
            if (!((input->value.stream_index).datestamp).value) goto invalid;
            child3 = canonical_track_json(owner, canonical_writer_string(((input->value.stream_index).datestamp).value, ((input->value.stream_index).datestamp).byte_count, ((input->value.stream_index).datestamp).has_byte_count));
            if (!child3) goto no_memory;
            cJSON_DetachItemViaPointer(owner, child3);
            if (!cJSON_AddItemToObject(result, "datestamp", child3)) { cJSON_Delete(child3); goto no_memory; }
        }
        if (!(input->value.stream_index).has_presence || ((input->value.stream_index).present_fields & (UINT64_C(1) << 3)))         {
            cJSON *child4 = NULL;
            if (!((input->value.stream_index).jsonl).value) goto invalid;
            child4 = canonical_track_json(owner, canonical_writer_string(((input->value.stream_index).jsonl).value, ((input->value.stream_index).jsonl).byte_count, ((input->value.stream_index).jsonl).has_byte_count));
            if (!child4) goto no_memory;
            cJSON_DetachItemViaPointer(owner, child4);
            if (!cJSON_AddItemToObject(result, "jsonl", child4)) { cJSON_Delete(child4); goto no_memory; }
        }
        if (!(input->value.stream_index).has_presence || ((input->value.stream_index).present_fields & (UINT64_C(1) << 4)))         {
            cJSON *child5 = NULL;
            if (!((input->value.stream_index).jsonl_sha256).value) goto invalid;
            child5 = canonical_track_json(owner, canonical_writer_string(((input->value.stream_index).jsonl_sha256).value, ((input->value.stream_index).jsonl_sha256).byte_count, ((input->value.stream_index).jsonl_sha256).has_byte_count));
            if (!child5) goto no_memory;
            cJSON_DetachItemViaPointer(owner, child5);
            if (!cJSON_AddItemToObject(result, "jsonl_sha256", child5)) { cJSON_Delete(child5); goto no_memory; }
        }
        if (!(input->value.stream_index).has_presence || ((input->value.stream_index).present_fields & (UINT64_C(1) << 5)))         {
            cJSON *child6 = NULL;
            child6 = canonical_track_json(owner, cJSON_CreateNumber(((input->value.stream_index).jsonl_size).value));
            if (!child6) goto no_memory;
            cJSON_DetachItemViaPointer(owner, child6);
            if (!cJSON_AddItemToObject(result, "jsonl_size", child6)) { cJSON_Delete(child6); goto no_memory; }
        }
        if (!(input->value.stream_index).has_presence || ((input->value.stream_index).present_fields & (UINT64_C(1) << 6)))         {
            cJSON *child7 = NULL;
            if (!((input->value.stream_index).by).value) goto invalid;
            child7 = canonical_track_json(owner, canonical_writer_string(((input->value.stream_index).by).value, ((input->value.stream_index).by).byte_count, ((input->value.stream_index).by).has_byte_count));
            if (!child7) goto no_memory;
            cJSON_DetachItemViaPointer(owner, child7);
            if (!cJSON_AddItemToObject(result, "by", child7)) { cJSON_Delete(child7); goto no_memory; }
        }
        if (!(input->value.stream_index).has_presence || ((input->value.stream_index).present_fields & (UINT64_C(1) << 7)))         {
            cJSON *child8 = NULL;
            if (((input->value.stream_index).stations).count && !((input->value.stream_index).stations).items) goto invalid;
            child8 = canonical_track_json(owner, cJSON_CreateArray());
            if (!child8) goto no_memory;
            for (size_t i9 = 0; i9 < ((input->value.stream_index).stations).count; i9++) {
                cJSON *child9 = NULL;
                child9 = canonical_track_json(owner, cJSON_CreateObject());
                if (!child9) goto no_memory;
                if ((((input->value.stream_index).stations).items[i9]).has_presence && ((((input->value.stream_index).stations).items[i9]).present_fields & UINT64_C(262143)) != UINT64_C(262143)) goto invalid;
                if (!(((input->value.stream_index).stations).items[i9]).has_presence || ((((input->value.stream_index).stations).items[i9]).present_fields & (UINT64_C(1) << 0)))                 {
                    cJSON *child10 = NULL;
                    if (!((((input->value.stream_index).stations).items[i9]).station_id).value) goto invalid;
                    child10 = canonical_track_json(owner, canonical_writer_string(((((input->value.stream_index).stations).items[i9]).station_id).value, ((((input->value.stream_index).stations).items[i9]).station_id).byte_count, ((((input->value.stream_index).stations).items[i9]).station_id).has_byte_count));
                    if (!child10) goto no_memory;
                    cJSON_DetachItemViaPointer(owner, child10);
                    if (!cJSON_AddItemToObject(child9, "station_id", child10)) { cJSON_Delete(child10); goto no_memory; }
                }
                if (!(((input->value.stream_index).stations).items[i9]).has_presence || ((((input->value.stream_index).stations).items[i9]).present_fields & (UINT64_C(1) << 1)))                 {
                    cJSON *child11 = NULL;
                    if (!((((input->value.stream_index).stations).items[i9]).status).value) goto invalid;
                    child11 = canonical_track_json(owner, canonical_writer_string(((((input->value.stream_index).stations).items[i9]).status).value, ((((input->value.stream_index).stations).items[i9]).status).byte_count, ((((input->value.stream_index).stations).items[i9]).status).has_byte_count));
                    if (!child11) goto no_memory;
                    cJSON_DetachItemViaPointer(owner, child11);
                    if (!cJSON_AddItemToObject(child9, "status", child11)) { cJSON_Delete(child11); goto no_memory; }
                }
                if (!(((input->value.stream_index).stations).items[i9]).has_presence || ((((input->value.stream_index).stations).items[i9]).present_fields & (UINT64_C(1) << 2)))                 {
                    cJSON *child12 = NULL;
                    switch (((((input->value.stream_index).stations).items[i9]).name).tag) {
                    case 0: {
                        if (!(((((input->value.stream_index).stations).items[i9]).name).value.variant_0).value) goto invalid;
                        child12 = canonical_track_json(owner, canonical_writer_string((((((input->value.stream_index).stations).items[i9]).name).value.variant_0).value, (((((input->value.stream_index).stations).items[i9]).name).value.variant_0).byte_count, (((((input->value.stream_index).stations).items[i9]).name).value.variant_0).has_byte_count));
                        if (!child12) goto no_memory;
                        break;
                    }
                    case 1: {
                        child12 = canonical_track_json(owner, cJSON_CreateNull());
                        if (!child12) goto no_memory;
                        break;
                    }
                    default: goto invalid;
                    }
                    cJSON_DetachItemViaPointer(owner, child12);
                    if (!cJSON_AddItemToObject(child9, "name", child12)) { cJSON_Delete(child12); goto no_memory; }
                }
                if (!(((input->value.stream_index).stations).items[i9]).has_presence || ((((input->value.stream_index).stations).items[i9]).present_fields & (UINT64_C(1) << 3)))                 {
                    cJSON *child13 = NULL;
                    switch (((((input->value.stream_index).stations).items[i9]).name_folded).tag) {
                    case 0: {
                        if (!(((((input->value.stream_index).stations).items[i9]).name_folded).value.variant_0).value) goto invalid;
                        child13 = canonical_track_json(owner, canonical_writer_string((((((input->value.stream_index).stations).items[i9]).name_folded).value.variant_0).value, (((((input->value.stream_index).stations).items[i9]).name_folded).value.variant_0).byte_count, (((((input->value.stream_index).stations).items[i9]).name_folded).value.variant_0).has_byte_count));
                        if (!child13) goto no_memory;
                        break;
                    }
                    case 1: {
                        child13 = canonical_track_json(owner, cJSON_CreateNull());
                        if (!child13) goto no_memory;
                        break;
                    }
                    default: goto invalid;
                    }
                    cJSON_DetachItemViaPointer(owner, child13);
                    if (!cJSON_AddItemToObject(child9, "name_folded", child13)) { cJSON_Delete(child13); goto no_memory; }
                }
                if (!(((input->value.stream_index).stations).items[i9]).has_presence || ((((input->value.stream_index).stations).items[i9]).present_fields & (UINT64_C(1) << 4)))                 {
                    cJSON *child14 = NULL;
                    switch (((((input->value.stream_index).stations).items[i9]).country).tag) {
                    case 0: {
                        if (!(((((input->value.stream_index).stations).items[i9]).country).value.variant_0).value) goto invalid;
                        child14 = canonical_track_json(owner, canonical_writer_string((((((input->value.stream_index).stations).items[i9]).country).value.variant_0).value, (((((input->value.stream_index).stations).items[i9]).country).value.variant_0).byte_count, (((((input->value.stream_index).stations).items[i9]).country).value.variant_0).has_byte_count));
                        if (!child14) goto no_memory;
                        break;
                    }
                    case 1: {
                        child14 = canonical_track_json(owner, cJSON_CreateNull());
                        if (!child14) goto no_memory;
                        break;
                    }
                    default: goto invalid;
                    }
                    cJSON_DetachItemViaPointer(owner, child14);
                    if (!cJSON_AddItemToObject(child9, "country", child14)) { cJSON_Delete(child14); goto no_memory; }
                }
                if (!(((input->value.stream_index).stations).items[i9]).has_presence || ((((input->value.stream_index).stations).items[i9]).present_fields & (UINT64_C(1) << 5)))                 {
                    cJSON *child15 = NULL;
                    switch (((((input->value.stream_index).stations).items[i9]).type).tag) {
                    case 0: {
                        if (!(((((input->value.stream_index).stations).items[i9]).type).value.variant_0).value) goto invalid;
                        child15 = canonical_track_json(owner, canonical_writer_string((((((input->value.stream_index).stations).items[i9]).type).value.variant_0).value, (((((input->value.stream_index).stations).items[i9]).type).value.variant_0).byte_count, (((((input->value.stream_index).stations).items[i9]).type).value.variant_0).has_byte_count));
                        if (!child15) goto no_memory;
                        break;
                    }
                    case 1: {
                        child15 = canonical_track_json(owner, cJSON_CreateNull());
                        if (!child15) goto no_memory;
                        break;
                    }
                    default: goto invalid;
                    }
                    cJSON_DetachItemViaPointer(owner, child15);
                    if (!cJSON_AddItemToObject(child9, "type", child15)) { cJSON_Delete(child15); goto no_memory; }
                }
                if (!(((input->value.stream_index).stations).items[i9]).has_presence || ((((input->value.stream_index).stations).items[i9]).present_fields & (UINT64_C(1) << 6)))                 {
                    cJSON *child16 = NULL;
                    switch (((((input->value.stream_index).stations).items[i9]).kind).tag) {
                    case 0: {
                        if (!(((((input->value.stream_index).stations).items[i9]).kind).value.variant_0).value) goto invalid;
                        child16 = canonical_track_json(owner, canonical_writer_string((((((input->value.stream_index).stations).items[i9]).kind).value.variant_0).value, (((((input->value.stream_index).stations).items[i9]).kind).value.variant_0).byte_count, (((((input->value.stream_index).stations).items[i9]).kind).value.variant_0).has_byte_count));
                        if (!child16) goto no_memory;
                        break;
                    }
                    case 1: {
                        child16 = canonical_track_json(owner, cJSON_CreateNull());
                        if (!child16) goto no_memory;
                        break;
                    }
                    default: goto invalid;
                    }
                    cJSON_DetachItemViaPointer(owner, child16);
                    if (!cJSON_AddItemToObject(child9, "kind", child16)) { cJSON_Delete(child16); goto no_memory; }
                }
                if (!(((input->value.stream_index).stations).items[i9]).has_presence || ((((input->value.stream_index).stations).items[i9]).present_fields & (UINT64_C(1) << 7)))                 {
                    cJSON *child17 = NULL;
                    switch (((((input->value.stream_index).stations).items[i9]).reference_station_id).tag) {
                    case 0: {
                        if (!(((((input->value.stream_index).stations).items[i9]).reference_station_id).value.variant_0).value) goto invalid;
                        child17 = canonical_track_json(owner, canonical_writer_string((((((input->value.stream_index).stations).items[i9]).reference_station_id).value.variant_0).value, (((((input->value.stream_index).stations).items[i9]).reference_station_id).value.variant_0).byte_count, (((((input->value.stream_index).stations).items[i9]).reference_station_id).value.variant_0).has_byte_count));
                        if (!child17) goto no_memory;
                        break;
                    }
                    case 1: {
                        child17 = canonical_track_json(owner, cJSON_CreateNull());
                        if (!child17) goto no_memory;
                        break;
                    }
                    default: goto invalid;
                    }
                    cJSON_DetachItemViaPointer(owner, child17);
                    if (!cJSON_AddItemToObject(child9, "reference_station_id", child17)) { cJSON_Delete(child17); goto no_memory; }
                }
                if (!(((input->value.stream_index).stations).items[i9]).has_presence || ((((input->value.stream_index).stations).items[i9]).present_fields & (UINT64_C(1) << 8)))                 {
                    cJSON *child18 = NULL;
                    switch (((((input->value.stream_index).stations).items[i9]).offsets_licence_id).tag) {
                    case 0: {
                        if (!(((((input->value.stream_index).stations).items[i9]).offsets_licence_id).value.variant_0).value) goto invalid;
                        child18 = canonical_track_json(owner, canonical_writer_string((((((input->value.stream_index).stations).items[i9]).offsets_licence_id).value.variant_0).value, (((((input->value.stream_index).stations).items[i9]).offsets_licence_id).value.variant_0).byte_count, (((((input->value.stream_index).stations).items[i9]).offsets_licence_id).value.variant_0).has_byte_count));
                        if (!child18) goto no_memory;
                        break;
                    }
                    case 1: {
                        child18 = canonical_track_json(owner, cJSON_CreateNull());
                        if (!child18) goto no_memory;
                        break;
                    }
                    default: goto invalid;
                    }
                    cJSON_DetachItemViaPointer(owner, child18);
                    if (!cJSON_AddItemToObject(child9, "offsets_licence_id", child18)) { cJSON_Delete(child18); goto no_memory; }
                }
                if (!(((input->value.stream_index).stations).items[i9]).has_presence || ((((input->value.stream_index).stations).items[i9]).present_fields & (UINT64_C(1) << 9)))                 {
                    cJSON *child19 = NULL;
                    switch (((((input->value.stream_index).stations).items[i9]).recommended_set_id).tag) {
                    case 0: {
                        if (!(((((input->value.stream_index).stations).items[i9]).recommended_set_id).value.variant_0).value) goto invalid;
                        child19 = canonical_track_json(owner, canonical_writer_string((((((input->value.stream_index).stations).items[i9]).recommended_set_id).value.variant_0).value, (((((input->value.stream_index).stations).items[i9]).recommended_set_id).value.variant_0).byte_count, (((((input->value.stream_index).stations).items[i9]).recommended_set_id).value.variant_0).has_byte_count));
                        if (!child19) goto no_memory;
                        break;
                    }
                    case 1: {
                        child19 = canonical_track_json(owner, cJSON_CreateNull());
                        if (!child19) goto no_memory;
                        break;
                    }
                    default: goto invalid;
                    }
                    cJSON_DetachItemViaPointer(owner, child19);
                    if (!cJSON_AddItemToObject(child9, "recommended_set_id", child19)) { cJSON_Delete(child19); goto no_memory; }
                }
                if (!(((input->value.stream_index).stations).items[i9]).has_presence || ((((input->value.stream_index).stations).items[i9]).present_fields & (UINT64_C(1) << 10)))                 {
                    cJSON *child20 = NULL;
                    switch (((((input->value.stream_index).stations).items[i9]).lat).tag) {
                    case 0: {
                        child20 = canonical_track_json(owner, cJSON_CreateNumber((((((input->value.stream_index).stations).items[i9]).lat).value.variant_0).value));
                        if (!child20) goto no_memory;
                        break;
                    }
                    case 1: {
                        child20 = canonical_track_json(owner, cJSON_CreateNull());
                        if (!child20) goto no_memory;
                        break;
                    }
                    default: goto invalid;
                    }
                    cJSON_DetachItemViaPointer(owner, child20);
                    if (!cJSON_AddItemToObject(child9, "lat", child20)) { cJSON_Delete(child20); goto no_memory; }
                }
                if (!(((input->value.stream_index).stations).items[i9]).has_presence || ((((input->value.stream_index).stations).items[i9]).present_fields & (UINT64_C(1) << 11)))                 {
                    cJSON *child21 = NULL;
                    switch (((((input->value.stream_index).stations).items[i9]).lon).tag) {
                    case 0: {
                        child21 = canonical_track_json(owner, cJSON_CreateNumber((((((input->value.stream_index).stations).items[i9]).lon).value.variant_0).value));
                        if (!child21) goto no_memory;
                        break;
                    }
                    case 1: {
                        child21 = canonical_track_json(owner, cJSON_CreateNull());
                        if (!child21) goto no_memory;
                        break;
                    }
                    default: goto invalid;
                    }
                    cJSON_DetachItemViaPointer(owner, child21);
                    if (!cJSON_AddItemToObject(child9, "lon", child21)) { cJSON_Delete(child21); goto no_memory; }
                }
                if (!(((input->value.stream_index).stations).items[i9]).has_presence || ((((input->value.stream_index).stations).items[i9]).present_fields & (UINT64_C(1) << 12)))                 {
                    cJSON *child22 = NULL;
                    child22 = canonical_track_json(owner, cJSON_CreateNumber(((((input->value.stream_index).stations).items[i9]).offset).value));
                    if (!child22) goto no_memory;
                    cJSON_DetachItemViaPointer(owner, child22);
                    if (!cJSON_AddItemToObject(child9, "offset", child22)) { cJSON_Delete(child22); goto no_memory; }
                }
                if (!(((input->value.stream_index).stations).items[i9]).has_presence || ((((input->value.stream_index).stations).items[i9]).present_fields & (UINT64_C(1) << 13)))                 {
                    cJSON *child23 = NULL;
                    child23 = canonical_track_json(owner, cJSON_CreateNumber(((((input->value.stream_index).stations).items[i9]).length).value));
                    if (!child23) goto no_memory;
                    cJSON_DetachItemViaPointer(owner, child23);
                    if (!cJSON_AddItemToObject(child9, "length", child23)) { cJSON_Delete(child23); goto no_memory; }
                }
                if (!(((input->value.stream_index).stations).items[i9]).has_presence || ((((input->value.stream_index).stations).items[i9]).present_fields & (UINT64_C(1) << 14)))                 {
                    cJSON *child24 = NULL;
                    if (((((input->value.stream_index).stations).items[i9]).aliases).count && !((((input->value.stream_index).stations).items[i9]).aliases).entries) goto invalid;
                    child24 = canonical_track_json(owner, cJSON_CreateObject());
                    if (!child24) goto no_memory;
                    for (size_t i25 = 0; i25 < ((((input->value.stream_index).stations).items[i9]).aliases).count; i25++) {
                        cJSON *child25 = NULL;
                        if ((((((input->value.stream_index).stations).items[i9]).aliases).entries[i25].value).count && !(((((input->value.stream_index).stations).items[i9]).aliases).entries[i25].value).items) goto invalid;
                        child25 = canonical_track_json(owner, cJSON_CreateArray());
                        if (!child25) goto no_memory;
                        for (size_t i26 = 0; i26 < (((((input->value.stream_index).stations).items[i9]).aliases).entries[i25].value).count; i26++) {
                            cJSON *child26 = NULL;
                            if (!((((((input->value.stream_index).stations).items[i9]).aliases).entries[i25].value).items[i26]).value) goto invalid;
                            child26 = canonical_track_json(owner, canonical_writer_string(((((((input->value.stream_index).stations).items[i9]).aliases).entries[i25].value).items[i26]).value, ((((((input->value.stream_index).stations).items[i9]).aliases).entries[i25].value).items[i26]).byte_count, ((((((input->value.stream_index).stations).items[i9]).aliases).entries[i25].value).items[i26]).has_byte_count));
                            if (!child26) goto no_memory;
                            cJSON_DetachItemViaPointer(owner, child26);
                            if (!cJSON_AddItemToArray(child25, child26)) { cJSON_Delete(child26); goto no_memory; }
                        }
                        cJSON_DetachItemViaPointer(owner, child25);
                        if (!((((input->value.stream_index).stations).items[i9]).aliases).entries[i25].key.value || !cJSON_AddItemToObject(child24, ((((input->value.stream_index).stations).items[i9]).aliases).entries[i25].key.value, child25)) { cJSON_Delete(child25); goto no_memory; }
                    }
                    cJSON_DetachItemViaPointer(owner, child24);
                    if (!cJSON_AddItemToObject(child9, "aliases", child24)) { cJSON_Delete(child24); goto no_memory; }
                }
                if (!(((input->value.stream_index).stations).items[i9]).has_presence || ((((input->value.stream_index).stations).items[i9]).present_fields & (UINT64_C(1) << 15)))                 {
                    cJSON *child27 = NULL;
                    if (((((input->value.stream_index).stations).items[i9]).sets).count && !((((input->value.stream_index).stations).items[i9]).sets).items) goto invalid;
                    child27 = canonical_track_json(owner, cJSON_CreateArray());
                    if (!child27) goto no_memory;
                    for (size_t i28 = 0; i28 < ((((input->value.stream_index).stations).items[i9]).sets).count; i28++) {
                        cJSON *child28 = NULL;
                        child28 = canonical_track_json(owner, cJSON_CreateObject());
                        if (!child28) goto no_memory;
                        if ((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).has_presence && ((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).present_fields & UINT64_C(1023)) != UINT64_C(1023)) goto invalid;
                        if (!(((((input->value.stream_index).stations).items[i9]).sets).items[i28]).has_presence || ((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).present_fields & (UINT64_C(1) << 0)))                         {
                            cJSON *child29 = NULL;
                            switch (((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).set_id).tag) {
                            case 0: {
                                if (!(((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).set_id).value.variant_0).value) goto invalid;
                                child29 = canonical_track_json(owner, canonical_writer_string((((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).set_id).value.variant_0).value, (((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).set_id).value.variant_0).byte_count, (((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).set_id).value.variant_0).has_byte_count));
                                if (!child29) goto no_memory;
                                break;
                            }
                            case 1: {
                                child29 = canonical_track_json(owner, cJSON_CreateNull());
                                if (!child29) goto no_memory;
                                break;
                            }
                            default: goto invalid;
                            }
                            cJSON_DetachItemViaPointer(owner, child29);
                            if (!cJSON_AddItemToObject(child28, "set_id", child29)) { cJSON_Delete(child29); goto no_memory; }
                        }
                        if (!(((((input->value.stream_index).stations).items[i9]).sets).items[i28]).has_presence || ((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).present_fields & (UINT64_C(1) << 1)))                         {
                            cJSON *child30 = NULL;
                            switch (((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).source).tag) {
                            case 0: {
                                if (!(((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).source).value.variant_0).value) goto invalid;
                                child30 = canonical_track_json(owner, canonical_writer_string((((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).source).value.variant_0).value, (((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).source).value.variant_0).byte_count, (((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).source).value.variant_0).has_byte_count));
                                if (!child30) goto no_memory;
                                break;
                            }
                            case 1: {
                                child30 = canonical_track_json(owner, cJSON_CreateNull());
                                if (!child30) goto no_memory;
                                break;
                            }
                            default: goto invalid;
                            }
                            cJSON_DetachItemViaPointer(owner, child30);
                            if (!cJSON_AddItemToObject(child28, "source", child30)) { cJSON_Delete(child30); goto no_memory; }
                        }
                        if (!(((((input->value.stream_index).stations).items[i9]).sets).items[i28]).has_presence || ((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).present_fields & (UINT64_C(1) << 2)))                         {
                            cJSON *child31 = NULL;
                            switch (((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).source_type).tag) {
                            case 0: {
                                if (!(((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).source_type).value.variant_0).value) goto invalid;
                                child31 = canonical_track_json(owner, canonical_writer_string((((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).source_type).value.variant_0).value, (((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).source_type).value.variant_0).byte_count, (((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).source_type).value.variant_0).has_byte_count));
                                if (!child31) goto no_memory;
                                break;
                            }
                            case 1: {
                                child31 = canonical_track_json(owner, cJSON_CreateNull());
                                if (!child31) goto no_memory;
                                break;
                            }
                            default: goto invalid;
                            }
                            cJSON_DetachItemViaPointer(owner, child31);
                            if (!cJSON_AddItemToObject(child28, "source_type", child31)) { cJSON_Delete(child31); goto no_memory; }
                        }
                        if (!(((((input->value.stream_index).stations).items[i9]).sets).items[i28]).has_presence || ((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).present_fields & (UINT64_C(1) << 3)))                         {
                            cJSON *child32 = NULL;
                            switch (((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).quantity).tag) {
                            case 0: {
                                if (!(((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).quantity).value.variant_0).value) goto invalid;
                                child32 = canonical_track_json(owner, canonical_writer_string((((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).quantity).value.variant_0).value, (((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).quantity).value.variant_0).byte_count, (((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).quantity).value.variant_0).has_byte_count));
                                if (!child32) goto no_memory;
                                break;
                            }
                            case 1: {
                                child32 = canonical_track_json(owner, cJSON_CreateNull());
                                if (!child32) goto no_memory;
                                break;
                            }
                            default: goto invalid;
                            }
                            cJSON_DetachItemViaPointer(owner, child32);
                            if (!cJSON_AddItemToObject(child28, "quantity", child32)) { cJSON_Delete(child32); goto no_memory; }
                        }
                        if (!(((((input->value.stream_index).stations).items[i9]).sets).items[i28]).has_presence || ((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).present_fields & (UINT64_C(1) << 4)))                         {
                            cJSON *child33 = NULL;
                            switch (((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).qc_status).tag) {
                            case 0: {
                                if (!(((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).qc_status).value.variant_0).value) goto invalid;
                                child33 = canonical_track_json(owner, canonical_writer_string((((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).qc_status).value.variant_0).value, (((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).qc_status).value.variant_0).byte_count, (((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).qc_status).value.variant_0).has_byte_count));
                                if (!child33) goto no_memory;
                                break;
                            }
                            case 1: {
                                child33 = canonical_track_json(owner, cJSON_CreateNull());
                                if (!child33) goto no_memory;
                                break;
                            }
                            default: goto invalid;
                            }
                            cJSON_DetachItemViaPointer(owner, child33);
                            if (!cJSON_AddItemToObject(child28, "qc_status", child33)) { cJSON_Delete(child33); goto no_memory; }
                        }
                        if (!(((((input->value.stream_index).stations).items[i9]).sets).items[i28]).has_presence || ((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).present_fields & (UINT64_C(1) << 5)))                         {
                            cJSON *child34 = NULL;
                            switch (((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).convention_id).tag) {
                            case 0: {
                                if (!(((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).convention_id).value.variant_0).value) goto invalid;
                                child34 = canonical_track_json(owner, canonical_writer_string((((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).convention_id).value.variant_0).value, (((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).convention_id).value.variant_0).byte_count, (((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).convention_id).value.variant_0).has_byte_count));
                                if (!child34) goto no_memory;
                                break;
                            }
                            case 1: {
                                child34 = canonical_track_json(owner, cJSON_CreateNull());
                                if (!child34) goto no_memory;
                                break;
                            }
                            default: goto invalid;
                            }
                            cJSON_DetachItemViaPointer(owner, child34);
                            if (!cJSON_AddItemToObject(child28, "convention_id", child34)) { cJSON_Delete(child34); goto no_memory; }
                        }
                        if (!(((((input->value.stream_index).stations).items[i9]).sets).items[i28]).has_presence || ((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).present_fields & (UINT64_C(1) << 6)))                         {
                            cJSON *child35 = NULL;
                            switch (((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).licence_id).tag) {
                            case 0: {
                                if (!(((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).licence_id).value.variant_0).value) goto invalid;
                                child35 = canonical_track_json(owner, canonical_writer_string((((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).licence_id).value.variant_0).value, (((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).licence_id).value.variant_0).byte_count, (((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).licence_id).value.variant_0).has_byte_count));
                                if (!child35) goto no_memory;
                                break;
                            }
                            case 1: {
                                child35 = canonical_track_json(owner, cJSON_CreateNull());
                                if (!child35) goto no_memory;
                                break;
                            }
                            default: goto invalid;
                            }
                            cJSON_DetachItemViaPointer(owner, child35);
                            if (!cJSON_AddItemToObject(child28, "licence_id", child35)) { cJSON_Delete(child35); goto no_memory; }
                        }
                        if (!(((((input->value.stream_index).stations).items[i9]).sets).items[i28]).has_presence || ((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).present_fields & (UINT64_C(1) << 7)))                         {
                            cJSON *child36 = NULL;
                            if (((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).constituents).count && !((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).constituents).items) goto invalid;
                            child36 = canonical_track_json(owner, cJSON_CreateArray());
                            if (!child36) goto no_memory;
                            for (size_t i37 = 0; i37 < ((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).constituents).count; i37++) {
                                cJSON *child37 = NULL;
                                if (!(((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).constituents).items[i37]).value) goto invalid;
                                child37 = canonical_track_json(owner, canonical_writer_string((((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).constituents).items[i37]).value, (((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).constituents).items[i37]).byte_count, (((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).constituents).items[i37]).has_byte_count));
                                if (!child37) goto no_memory;
                                cJSON_DetachItemViaPointer(owner, child37);
                                if (!cJSON_AddItemToArray(child36, child37)) { cJSON_Delete(child37); goto no_memory; }
                            }
                            cJSON_DetachItemViaPointer(owner, child36);
                            if (!cJSON_AddItemToObject(child28, "constituents", child36)) { cJSON_Delete(child36); goto no_memory; }
                        }
                        if (!(((((input->value.stream_index).stations).items[i9]).sets).items[i28]).has_presence || ((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).present_fields & (UINT64_C(1) << 8)))                         {
                            cJSON *child38 = NULL;
                            switch (((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).fallback).tag) {
                            case 0: {
                                child38 = canonical_track_json(owner, cJSON_CreateObject());
                                if (!child38) goto no_memory;
                                if ((((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).fallback).value.variant_0).has_presence && ((((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).fallback).value.variant_0).present_fields & UINT64_C(7)) != UINT64_C(7)) goto invalid;
                                if (!(((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).fallback).value.variant_0).has_presence || ((((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).fallback).value.variant_0).present_fields & (UINT64_C(1) << 0)))                                 {
                                    cJSON *child39 = NULL;
                                    if (!((((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).fallback).value.variant_0).reason).value) goto invalid;
                                    child39 = canonical_track_json(owner, canonical_writer_string(((((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).fallback).value.variant_0).reason).value, ((((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).fallback).value.variant_0).reason).byte_count, ((((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).fallback).value.variant_0).reason).has_byte_count));
                                    if (!child39) goto no_memory;
                                    cJSON_DetachItemViaPointer(owner, child39);
                                    if (!cJSON_AddItemToObject(child38, "reason", child39)) { cJSON_Delete(child39); goto no_memory; }
                                }
                                if (!(((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).fallback).value.variant_0).has_presence || ((((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).fallback).value.variant_0).present_fields & (UINT64_C(1) << 1)))                                 {
                                    cJSON *child40 = NULL;
                                    if (!((((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).fallback).value.variant_0).basis).value) goto invalid;
                                    child40 = canonical_track_json(owner, canonical_writer_string(((((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).fallback).value.variant_0).basis).value, ((((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).fallback).value.variant_0).basis).byte_count, ((((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).fallback).value.variant_0).basis).has_byte_count));
                                    if (!child40) goto no_memory;
                                    cJSON_DetachItemViaPointer(owner, child40);
                                    if (!cJSON_AddItemToObject(child38, "basis", child40)) { cJSON_Delete(child40); goto no_memory; }
                                }
                                if (!(((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).fallback).value.variant_0).has_presence || ((((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).fallback).value.variant_0).present_fields & (UINT64_C(1) << 2)))                                 {
                                    cJSON *child41 = NULL;
                                    if (!((((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).fallback).value.variant_0).otc_finding).value) goto invalid;
                                    child41 = canonical_track_json(owner, canonical_writer_string(((((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).fallback).value.variant_0).otc_finding).value, ((((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).fallback).value.variant_0).otc_finding).byte_count, ((((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).fallback).value.variant_0).otc_finding).has_byte_count));
                                    if (!child41) goto no_memory;
                                    cJSON_DetachItemViaPointer(owner, child41);
                                    if (!cJSON_AddItemToObject(child38, "otc_finding", child41)) { cJSON_Delete(child41); goto no_memory; }
                                }
                                if (!(((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).fallback).value.variant_0).has_presence || ((((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).fallback).value.variant_0).present_fields & (UINT64_C(1) << 3)))                                 {
                                    cJSON *child42 = NULL;
                                    if (!((((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).fallback).value.variant_0).preferred_set_id).value) goto invalid;
                                    child42 = canonical_track_json(owner, canonical_writer_string(((((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).fallback).value.variant_0).preferred_set_id).value, ((((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).fallback).value.variant_0).preferred_set_id).byte_count, ((((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).fallback).value.variant_0).preferred_set_id).has_byte_count));
                                    if (!child42) goto no_memory;
                                    cJSON_DetachItemViaPointer(owner, child42);
                                    if (!cJSON_AddItemToObject(child38, "preferred_set_id", child42)) { cJSON_Delete(child42); goto no_memory; }
                                }
                                if ((((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).fallback).value.variant_0).extensions.count && !(((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).fallback).value.variant_0).extensions.entries) goto invalid;
                                for (size_t extra43=0; extra43<(((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).fallback).value.variant_0).extensions.count; extra43++) {
                                    cJSON *child43=NULL;
                                    const otc_cp_JsonValue_map_entry *entry=&(((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).fallback).value.variant_0).extensions.entries[extra43];
                                    if (!entry->key.value) goto invalid;
                                    if (!strcmp(entry->key.value, "reason")) goto invalid;
                                    if (!strcmp(entry->key.value, "basis")) goto invalid;
                                    if (!strcmp(entry->key.value, "otc_finding")) goto invalid;
                                    if (!strcmp(entry->key.value, "preferred_set_id")) goto invalid;
                                    child43 = canonical_track_json(owner, canonical_source_json(&(entry->value)));
                                    if (!child43) goto no_memory;
                                    cJSON_DetachItemViaPointer(owner, child43);
                                    cJSON_DetachItemViaPointer(owner, child43);
                                    if (!cJSON_AddItemToObject(child38, entry->key.value, child43)) { cJSON_Delete(child43); goto no_memory; }
                                }
                                break;
                            }
                            case 1: {
                                child38 = canonical_track_json(owner, cJSON_CreateNull());
                                if (!child38) goto no_memory;
                                break;
                            }
                            default: goto invalid;
                            }
                            cJSON_DetachItemViaPointer(owner, child38);
                            if (!cJSON_AddItemToObject(child28, "fallback", child38)) { cJSON_Delete(child38); goto no_memory; }
                        }
                        if (!(((((input->value.stream_index).stations).items[i9]).sets).items[i28]).has_presence || ((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).present_fields & (UINT64_C(1) << 9)))                         {
                            cJSON *child44 = NULL;
                            if (((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).current_bins).count && !((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).current_bins).items) goto invalid;
                            child44 = canonical_track_json(owner, cJSON_CreateArray());
                            if (!child44) goto no_memory;
                            for (size_t i45 = 0; i45 < ((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).current_bins).count; i45++) {
                                cJSON *child45 = NULL;
                                child45 = canonical_track_json(owner, cJSON_CreateNumber((((((((input->value.stream_index).stations).items[i9]).sets).items[i28]).current_bins).items[i45]).value));
                                if (!child45) goto no_memory;
                                cJSON_DetachItemViaPointer(owner, child45);
                                if (!cJSON_AddItemToArray(child44, child45)) { cJSON_Delete(child45); goto no_memory; }
                            }
                            cJSON_DetachItemViaPointer(owner, child44);
                            if (!cJSON_AddItemToObject(child28, "current_bins", child44)) { cJSON_Delete(child44); goto no_memory; }
                        }
                        cJSON_DetachItemViaPointer(owner, child28);
                        if (!cJSON_AddItemToArray(child27, child28)) { cJSON_Delete(child28); goto no_memory; }
                    }
                    cJSON_DetachItemViaPointer(owner, child27);
                    if (!cJSON_AddItemToObject(child9, "sets", child27)) { cJSON_Delete(child27); goto no_memory; }
                }
                if (!(((input->value.stream_index).stations).items[i9]).has_presence || ((((input->value.stream_index).stations).items[i9]).present_fields & (UINT64_C(1) << 16)))                 {
                    cJSON *child46 = NULL;
                    switch (((((input->value.stream_index).stations).items[i9]).subordinate_offsets).tag) {
                    case 0: {
                        child46 = canonical_track_json(owner, cJSON_CreateObject());
                        if (!child46) goto no_memory;
                        if ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).has_presence && ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).present_fields & UINT64_C(33)) != UINT64_C(33)) goto invalid;
                        if (!(((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).has_presence || ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).present_fields & (UINT64_C(1) << 0)))                         {
                            cJSON *child47 = NULL;
                            if (!((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).reference_station_id).value) goto invalid;
                            child47 = canonical_track_json(owner, canonical_writer_string(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).reference_station_id).value, ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).reference_station_id).byte_count, ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).reference_station_id).has_byte_count));
                            if (!child47) goto no_memory;
                            cJSON_DetachItemViaPointer(owner, child47);
                            if (!cJSON_AddItemToObject(child46, "reference_station_id", child47)) { cJSON_Delete(child47); goto no_memory; }
                        }
                        if (!(((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).has_presence || ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).present_fields & (UINT64_C(1) << 1)))                         {
                            cJSON *child48 = NULL;
                            child48 = canonical_track_json(owner, cJSON_CreateNumber(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).time_offset_high_min).value));
                            if (!child48) goto no_memory;
                            cJSON_DetachItemViaPointer(owner, child48);
                            if (!cJSON_AddItemToObject(child46, "time_offset_high_min", child48)) { cJSON_Delete(child48); goto no_memory; }
                        }
                        if (!(((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).has_presence || ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).present_fields & (UINT64_C(1) << 2)))                         {
                            cJSON *child49 = NULL;
                            child49 = canonical_track_json(owner, cJSON_CreateNumber(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).time_offset_low_min).value));
                            if (!child49) goto no_memory;
                            cJSON_DetachItemViaPointer(owner, child49);
                            if (!cJSON_AddItemToObject(child46, "time_offset_low_min", child49)) { cJSON_Delete(child49); goto no_memory; }
                        }
                        if (!(((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).has_presence || ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).present_fields & (UINT64_C(1) << 3)))                         {
                            cJSON *child50 = NULL;
                            child50 = canonical_track_json(owner, cJSON_CreateNumber(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).height_offset_high).value));
                            if (!child50) goto no_memory;
                            cJSON_DetachItemViaPointer(owner, child50);
                            if (!cJSON_AddItemToObject(child46, "height_offset_high", child50)) { cJSON_Delete(child50); goto no_memory; }
                        }
                        if (!(((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).has_presence || ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).present_fields & (UINT64_C(1) << 4)))                         {
                            cJSON *child51 = NULL;
                            child51 = canonical_track_json(owner, cJSON_CreateNumber(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).height_offset_low).value));
                            if (!child51) goto no_memory;
                            cJSON_DetachItemViaPointer(owner, child51);
                            if (!cJSON_AddItemToObject(child46, "height_offset_low", child51)) { cJSON_Delete(child51); goto no_memory; }
                        }
                        if (!(((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).has_presence || ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).present_fields & (UINT64_C(1) << 5)))                         {
                            cJSON *child52 = NULL;
                            if (!((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).height_adjusted_type).value) goto invalid;
                            child52 = canonical_track_json(owner, canonical_writer_string(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).height_adjusted_type).value, ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).height_adjusted_type).byte_count, ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).height_adjusted_type).has_byte_count));
                            if (!child52) goto no_memory;
                            cJSON_DetachItemViaPointer(owner, child52);
                            if (!cJSON_AddItemToObject(child46, "height_adjusted_type", child52)) { cJSON_Delete(child52); goto no_memory; }
                        }
                        if (!(((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).has_presence || ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).present_fields & (UINT64_C(1) << 6)))                         {
                            cJSON *child53 = NULL;
                            if (!((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).licence_id).value) goto invalid;
                            child53 = canonical_track_json(owner, canonical_writer_string(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).licence_id).value, ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).licence_id).byte_count, ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).licence_id).has_byte_count));
                            if (!child53) goto no_memory;
                            cJSON_DetachItemViaPointer(owner, child53);
                            if (!cJSON_AddItemToObject(child46, "licence_id", child53)) { cJSON_Delete(child53); goto no_memory; }
                        }
                        if (!(((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).has_presence || ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).present_fields & (UINT64_C(1) << 7)))                         {
                            cJSON *child54 = NULL;
                            if (!((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).datum).value) goto invalid;
                            child54 = canonical_track_json(owner, canonical_writer_string(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).datum).value, ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).datum).byte_count, ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).datum).has_byte_count));
                            if (!child54) goto no_memory;
                            cJSON_DetachItemViaPointer(owner, child54);
                            if (!cJSON_AddItemToObject(child46, "datum", child54)) { cJSON_Delete(child54); goto no_memory; }
                        }
                        if (!(((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).has_presence || ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).present_fields & (UINT64_C(1) << 8)))                         {
                            cJSON *child55 = NULL;
                            if (!((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).offset_id).value) goto invalid;
                            child55 = canonical_track_json(owner, canonical_writer_string(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).offset_id).value, ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).offset_id).byte_count, ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).offset_id).has_byte_count));
                            if (!child55) goto no_memory;
                            cJSON_DetachItemViaPointer(owner, child55);
                            if (!cJSON_AddItemToObject(child46, "offset_id", child55)) { cJSON_Delete(child55); goto no_memory; }
                        }
                        if (!(((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).has_presence || ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).present_fields & (UINT64_C(1) << 9)))                         {
                            cJSON *child56 = NULL;
                            if (!((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).source).value) goto invalid;
                            child56 = canonical_track_json(owner, canonical_writer_string(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).source).value, ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).source).byte_count, ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).source).has_byte_count));
                            if (!child56) goto no_memory;
                            cJSON_DetachItemViaPointer(owner, child56);
                            if (!cJSON_AddItemToObject(child46, "source", child56)) { cJSON_Delete(child56); goto no_memory; }
                        }
                        if (!(((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).has_presence || ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).present_fields & (UINT64_C(1) << 10)))                         {
                            cJSON *child57 = NULL;
                            if (!((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).source_type).value) goto invalid;
                            child57 = canonical_track_json(owner, canonical_writer_string(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).source_type).value, ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).source_type).byte_count, ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).source_type).has_byte_count));
                            if (!child57) goto no_memory;
                            cJSON_DetachItemViaPointer(owner, child57);
                            if (!cJSON_AddItemToObject(child46, "source_type", child57)) { cJSON_Delete(child57); goto no_memory; }
                        }
                        if (!(((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).has_presence || ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).present_fields & (UINT64_C(1) << 11)))                         {
                            cJSON *child58 = NULL;
                            if (!((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).source_version).value) goto invalid;
                            child58 = canonical_track_json(owner, canonical_writer_string(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).source_version).value, ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).source_version).byte_count, ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).source_version).has_byte_count));
                            if (!child58) goto no_memory;
                            cJSON_DetachItemViaPointer(owner, child58);
                            if (!cJSON_AddItemToObject(child46, "source_version", child58)) { cJSON_Delete(child58); goto no_memory; }
                        }
                        if (!(((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).has_presence || ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).present_fields & (UINT64_C(1) << 12)))                         {
                            cJSON *child59 = NULL;
                            if (!((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).source_record_id).value) goto invalid;
                            child59 = canonical_track_json(owner, canonical_writer_string(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).source_record_id).value, ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).source_record_id).byte_count, ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).source_record_id).has_byte_count));
                            if (!child59) goto no_memory;
                            cJSON_DetachItemViaPointer(owner, child59);
                            if (!cJSON_AddItemToObject(child46, "source_record_id", child59)) { cJSON_Delete(child59); goto no_memory; }
                        }
                        if (!(((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).has_presence || ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).present_fields & (UINT64_C(1) << 13)))                         {
                            cJSON *child60 = NULL;
                            if (!((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).qc_status).value) goto invalid;
                            child60 = canonical_track_json(owner, canonical_writer_string(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).qc_status).value, ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).qc_status).byte_count, ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).qc_status).has_byte_count));
                            if (!child60) goto no_memory;
                            cJSON_DetachItemViaPointer(owner, child60);
                            if (!cJSON_AddItemToObject(child46, "qc_status", child60)) { cJSON_Delete(child60); goto no_memory; }
                        }
                        if (!(((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).has_presence || ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).present_fields & (UINT64_C(1) << 14)))                         {
                            cJSON *child61 = NULL;
                            if (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).qc_flags).count && !((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).qc_flags).items) goto invalid;
                            child61 = canonical_track_json(owner, cJSON_CreateArray());
                            if (!child61) goto no_memory;
                            for (size_t i62 = 0; i62 < ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).qc_flags).count; i62++) {
                                cJSON *child62 = NULL;
                                child62 = canonical_track_json(owner, cJSON_CreateObject());
                                if (!child62) goto no_memory;
                                if ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).qc_flags).items[i62]).has_presence && ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).qc_flags).items[i62]).present_fields & UINT64_C(3)) != UINT64_C(3)) goto invalid;
                                if (!(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).qc_flags).items[i62]).has_presence || ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).qc_flags).items[i62]).present_fields & (UINT64_C(1) << 0)))                                 {
                                    cJSON *child63 = NULL;
                                    if (!((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).qc_flags).items[i62]).flag).value) goto invalid;
                                    child63 = canonical_track_json(owner, canonical_writer_string(((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).qc_flags).items[i62]).flag).value, ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).qc_flags).items[i62]).flag).byte_count, ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).qc_flags).items[i62]).flag).has_byte_count));
                                    if (!child63) goto no_memory;
                                    cJSON_DetachItemViaPointer(owner, child63);
                                    if (!cJSON_AddItemToObject(child62, "flag", child63)) { cJSON_Delete(child63); goto no_memory; }
                                }
                                if (!(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).qc_flags).items[i62]).has_presence || ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).qc_flags).items[i62]).present_fields & (UINT64_C(1) << 1)))                                 {
                                    cJSON *child64 = NULL;
                                    if (!((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).qc_flags).items[i62]).reason).value) goto invalid;
                                    child64 = canonical_track_json(owner, canonical_writer_string(((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).qc_flags).items[i62]).reason).value, ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).qc_flags).items[i62]).reason).byte_count, ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).qc_flags).items[i62]).reason).has_byte_count));
                                    if (!child64) goto no_memory;
                                    cJSON_DetachItemViaPointer(owner, child64);
                                    if (!cJSON_AddItemToObject(child62, "reason", child64)) { cJSON_Delete(child64); goto no_memory; }
                                }
                                if (!(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).qc_flags).items[i62]).has_presence || ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).qc_flags).items[i62]).present_fields & (UINT64_C(1) << 2)))                                 {
                                    cJSON *child65 = NULL;
                                    child65 = canonical_track_json(owner, canonical_source_json(&((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).qc_flags).items[i62]).values)));
                                    if (!child65) goto no_memory;
                                    cJSON_DetachItemViaPointer(owner, child65);
                                    if (!cJSON_AddItemToObject(child62, "values", child65)) { cJSON_Delete(child65); goto no_memory; }
                                }
                                if ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).qc_flags).items[i62]).extensions.count && !(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).qc_flags).items[i62]).extensions.entries) goto invalid;
                                for (size_t extra66=0; extra66<(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).qc_flags).items[i62]).extensions.count; extra66++) {
                                    cJSON *child66=NULL;
                                    const otc_cp_JsonValue_map_entry *entry=&(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).qc_flags).items[i62]).extensions.entries[extra66];
                                    if (!entry->key.value) goto invalid;
                                    if (!strcmp(entry->key.value, "flag")) goto invalid;
                                    if (!strcmp(entry->key.value, "reason")) goto invalid;
                                    if (!strcmp(entry->key.value, "values")) goto invalid;
                                    child66 = canonical_track_json(owner, canonical_source_json(&(entry->value)));
                                    if (!child66) goto no_memory;
                                    cJSON_DetachItemViaPointer(owner, child66);
                                    cJSON_DetachItemViaPointer(owner, child66);
                                    if (!cJSON_AddItemToObject(child62, entry->key.value, child66)) { cJSON_Delete(child66); goto no_memory; }
                                }
                                cJSON_DetachItemViaPointer(owner, child62);
                                if (!cJSON_AddItemToArray(child61, child62)) { cJSON_Delete(child62); goto no_memory; }
                            }
                            cJSON_DetachItemViaPointer(owner, child61);
                            if (!cJSON_AddItemToObject(child46, "qc_flags", child61)) { cJSON_Delete(child61); goto no_memory; }
                        }
                        if (!(((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).has_presence || ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).present_fields & (UINT64_C(1) << 15)))                         {
                            cJSON *child67 = NULL;
                            child67 = canonical_track_json(owner, cJSON_CreateObject());
                            if (!child67) goto no_memory;
                            if (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).fallback).has_presence && (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).fallback).present_fields & UINT64_C(7)) != UINT64_C(7)) goto invalid;
                            if (!((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).fallback).has_presence || (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).fallback).present_fields & (UINT64_C(1) << 0)))                             {
                                cJSON *child68 = NULL;
                                if (!(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).fallback).reason).value) goto invalid;
                                child68 = canonical_track_json(owner, canonical_writer_string((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).fallback).reason).value, (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).fallback).reason).byte_count, (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).fallback).reason).has_byte_count));
                                if (!child68) goto no_memory;
                                cJSON_DetachItemViaPointer(owner, child68);
                                if (!cJSON_AddItemToObject(child67, "reason", child68)) { cJSON_Delete(child68); goto no_memory; }
                            }
                            if (!((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).fallback).has_presence || (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).fallback).present_fields & (UINT64_C(1) << 1)))                             {
                                cJSON *child69 = NULL;
                                if (!(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).fallback).basis).value) goto invalid;
                                child69 = canonical_track_json(owner, canonical_writer_string((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).fallback).basis).value, (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).fallback).basis).byte_count, (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).fallback).basis).has_byte_count));
                                if (!child69) goto no_memory;
                                cJSON_DetachItemViaPointer(owner, child69);
                                if (!cJSON_AddItemToObject(child67, "basis", child69)) { cJSON_Delete(child69); goto no_memory; }
                            }
                            if (!((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).fallback).has_presence || (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).fallback).present_fields & (UINT64_C(1) << 2)))                             {
                                cJSON *child70 = NULL;
                                if (!(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).fallback).otc_finding).value) goto invalid;
                                child70 = canonical_track_json(owner, canonical_writer_string((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).fallback).otc_finding).value, (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).fallback).otc_finding).byte_count, (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).fallback).otc_finding).has_byte_count));
                                if (!child70) goto no_memory;
                                cJSON_DetachItemViaPointer(owner, child70);
                                if (!cJSON_AddItemToObject(child67, "otc_finding", child70)) { cJSON_Delete(child70); goto no_memory; }
                            }
                            if (!((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).fallback).has_presence || (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).fallback).present_fields & (UINT64_C(1) << 3)))                             {
                                cJSON *child71 = NULL;
                                if (!(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).fallback).preferred_set_id).value) goto invalid;
                                child71 = canonical_track_json(owner, canonical_writer_string((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).fallback).preferred_set_id).value, (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).fallback).preferred_set_id).byte_count, (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).fallback).preferred_set_id).has_byte_count));
                                if (!child71) goto no_memory;
                                cJSON_DetachItemViaPointer(owner, child71);
                                if (!cJSON_AddItemToObject(child67, "preferred_set_id", child71)) { cJSON_Delete(child71); goto no_memory; }
                            }
                            if (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).fallback).extensions.count && !((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).fallback).extensions.entries) goto invalid;
                            for (size_t extra72=0; extra72<((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).fallback).extensions.count; extra72++) {
                                cJSON *child72=NULL;
                                const otc_cp_JsonValue_map_entry *entry=&((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).fallback).extensions.entries[extra72];
                                if (!entry->key.value) goto invalid;
                                if (!strcmp(entry->key.value, "reason")) goto invalid;
                                if (!strcmp(entry->key.value, "basis")) goto invalid;
                                if (!strcmp(entry->key.value, "otc_finding")) goto invalid;
                                if (!strcmp(entry->key.value, "preferred_set_id")) goto invalid;
                                child72 = canonical_track_json(owner, canonical_source_json(&(entry->value)));
                                if (!child72) goto no_memory;
                                cJSON_DetachItemViaPointer(owner, child72);
                                cJSON_DetachItemViaPointer(owner, child72);
                                if (!cJSON_AddItemToObject(child67, entry->key.value, child72)) { cJSON_Delete(child72); goto no_memory; }
                            }
                            cJSON_DetachItemViaPointer(owner, child67);
                            if (!cJSON_AddItemToObject(child46, "fallback", child67)) { cJSON_Delete(child67); goto no_memory; }
                        }
                        if (!(((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).has_presence || ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).present_fields & (UINT64_C(1) << 16)))                         {
                            cJSON *child73 = NULL;
                            child73 = canonical_track_json(owner, cJSON_CreateObject());
                            if (!child73) goto no_memory;
                            if (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).has_presence && (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).present_fields & UINT64_C(63)) != UINT64_C(63)) goto invalid;
                            if (!((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).has_presence || (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).present_fields & (UINT64_C(1) << 0)))                             {
                                cJSON *child74 = NULL;
                                child74 = canonical_track_json(owner, cJSON_CreateNumber((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).publication_year).value));
                                if (!child74) goto no_memory;
                                cJSON_DetachItemViaPointer(owner, child74);
                                if (!cJSON_AddItemToObject(child73, "publication_year", child74)) { cJSON_Delete(child74); goto no_memory; }
                            }
                            if (!((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).has_presence || (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).present_fields & (UINT64_C(1) << 1)))                             {
                                cJSON *child75 = NULL;
                                if (!(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).source_lifecycle).value) goto invalid;
                                child75 = canonical_track_json(owner, canonical_writer_string((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).source_lifecycle).value, (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).source_lifecycle).byte_count, (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).source_lifecycle).has_byte_count));
                                if (!child75) goto no_memory;
                                cJSON_DetachItemViaPointer(owner, child75);
                                if (!cJSON_AddItemToObject(child73, "source_lifecycle", child75)) { cJSON_Delete(child75); goto no_memory; }
                            }
                            if (!((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).has_presence || (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).present_fields & (UINT64_C(1) << 2)))                             {
                                cJSON *child76 = NULL;
                                if ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).removal_events).count && !(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).removal_events).items) goto invalid;
                                child76 = canonical_track_json(owner, cJSON_CreateArray());
                                if (!child76) goto no_memory;
                                for (size_t i77 = 0; i77 < (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).removal_events).count; i77++) {
                                    cJSON *child77 = NULL;
                                    child77 = canonical_track_json(owner, cJSON_CreateObject());
                                    if (!child77) goto no_memory;
                                    if (((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).removal_events).items[i77]).has_presence && (((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).removal_events).items[i77]).present_fields & UINT64_C(31)) != UINT64_C(31)) goto invalid;
                                    if (!((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).removal_events).items[i77]).has_presence || (((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).removal_events).items[i77]).present_fields & (UINT64_C(1) << 0)))                                     {
                                        cJSON *child78 = NULL;
                                        if (!(((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).removal_events).items[i77]).source_clock_timestamp).value) goto invalid;
                                        child78 = canonical_track_json(owner, canonical_writer_string((((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).removal_events).items[i77]).source_clock_timestamp).value, (((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).removal_events).items[i77]).source_clock_timestamp).byte_count, (((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).removal_events).items[i77]).source_clock_timestamp).has_byte_count));
                                        if (!child78) goto no_memory;
                                        cJSON_DetachItemViaPointer(owner, child78);
                                        if (!cJSON_AddItemToObject(child77, "source_clock_timestamp", child78)) { cJSON_Delete(child78); goto no_memory; }
                                    }
                                    if (!((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).removal_events).items[i77]).has_presence || (((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).removal_events).items[i77]).present_fields & (UINT64_C(1) << 1)))                                     {
                                        cJSON *child79 = NULL;
                                        if (!(((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).removal_events).items[i77]).name).value) goto invalid;
                                        child79 = canonical_track_json(owner, canonical_writer_string((((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).removal_events).items[i77]).name).value, (((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).removal_events).items[i77]).name).byte_count, (((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).removal_events).items[i77]).name).has_byte_count));
                                        if (!child79) goto no_memory;
                                        cJSON_DetachItemViaPointer(owner, child79);
                                        if (!cJSON_AddItemToObject(child77, "name", child79)) { cJSON_Delete(child79); goto no_memory; }
                                    }
                                    if (!((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).removal_events).items[i77]).has_presence || (((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).removal_events).items[i77]).present_fields & (UINT64_C(1) << 2)))                                     {
                                        cJSON *child80 = NULL;
                                        if (!(((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).removal_events).items[i77]).operation).value) goto invalid;
                                        child80 = canonical_track_json(owner, canonical_writer_string((((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).removal_events).items[i77]).operation).value, (((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).removal_events).items[i77]).operation).byte_count, (((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).removal_events).items[i77]).operation).has_byte_count));
                                        if (!child80) goto no_memory;
                                        cJSON_DetachItemViaPointer(owner, child80);
                                        if (!cJSON_AddItemToObject(child77, "operation", child80)) { cJSON_Delete(child80); goto no_memory; }
                                    }
                                    if (!((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).removal_events).items[i77]).has_presence || (((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).removal_events).items[i77]).present_fields & (UINT64_C(1) << 3)))                                     {
                                        cJSON *child81 = NULL;
                                        if (!(((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).removal_events).items[i77]).source_timezone).value) goto invalid;
                                        child81 = canonical_track_json(owner, canonical_writer_string((((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).removal_events).items[i77]).source_timezone).value, (((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).removal_events).items[i77]).source_timezone).byte_count, (((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).removal_events).items[i77]).source_timezone).has_byte_count));
                                        if (!child81) goto no_memory;
                                        cJSON_DetachItemViaPointer(owner, child81);
                                        if (!cJSON_AddItemToObject(child77, "source_timezone", child81)) { cJSON_Delete(child81); goto no_memory; }
                                    }
                                    if (!((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).removal_events).items[i77]).has_presence || (((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).removal_events).items[i77]).present_fields & (UINT64_C(1) << 4)))                                     {
                                        cJSON *child82 = NULL;
                                        if (!(((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).removal_events).items[i77]).evidence_sha256).value) goto invalid;
                                        child82 = canonical_track_json(owner, canonical_writer_string((((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).removal_events).items[i77]).evidence_sha256).value, (((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).removal_events).items[i77]).evidence_sha256).byte_count, (((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).removal_events).items[i77]).evidence_sha256).has_byte_count));
                                        if (!child82) goto no_memory;
                                        cJSON_DetachItemViaPointer(owner, child82);
                                        if (!cJSON_AddItemToObject(child77, "evidence_sha256", child82)) { cJSON_Delete(child82); goto no_memory; }
                                    }
                                    if (((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).removal_events).items[i77]).extensions.count && !((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).removal_events).items[i77]).extensions.entries) goto invalid;
                                    for (size_t extra83=0; extra83<((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).removal_events).items[i77]).extensions.count; extra83++) {
                                        cJSON *child83=NULL;
                                        const otc_cp_JsonValue_map_entry *entry=&((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).removal_events).items[i77]).extensions.entries[extra83];
                                        if (!entry->key.value) goto invalid;
                                        if (!strcmp(entry->key.value, "source_clock_timestamp")) goto invalid;
                                        if (!strcmp(entry->key.value, "name")) goto invalid;
                                        if (!strcmp(entry->key.value, "operation")) goto invalid;
                                        if (!strcmp(entry->key.value, "source_timezone")) goto invalid;
                                        if (!strcmp(entry->key.value, "evidence_sha256")) goto invalid;
                                        child83 = canonical_track_json(owner, canonical_source_json(&(entry->value)));
                                        if (!child83) goto no_memory;
                                        cJSON_DetachItemViaPointer(owner, child83);
                                        cJSON_DetachItemViaPointer(owner, child83);
                                        if (!cJSON_AddItemToObject(child77, entry->key.value, child83)) { cJSON_Delete(child83); goto no_memory; }
                                    }
                                    cJSON_DetachItemViaPointer(owner, child77);
                                    if (!cJSON_AddItemToArray(child76, child77)) { cJSON_Delete(child77); goto no_memory; }
                                }
                                cJSON_DetachItemViaPointer(owner, child76);
                                if (!cJSON_AddItemToObject(child73, "removal_events", child76)) { cJSON_Delete(child76); goto no_memory; }
                            }
                            if (!((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).has_presence || (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).present_fields & (UINT64_C(1) << 3)))                             {
                                cJSON *child84 = NULL;
                                if (!(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).current_validity).value) goto invalid;
                                child84 = canonical_track_json(owner, canonical_writer_string((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).current_validity).value, (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).current_validity).byte_count, (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).current_validity).has_byte_count));
                                if (!child84) goto no_memory;
                                cJSON_DetachItemViaPointer(owner, child84);
                                if (!cJSON_AddItemToObject(child73, "current_validity", child84)) { cJSON_Delete(child84); goto no_memory; }
                            }
                            if (!((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).has_presence || (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).present_fields & (UINT64_C(1) << 4)))                             {
                                cJSON *child85 = NULL;
                                if (!(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).current_accuracy).value) goto invalid;
                                child85 = canonical_track_json(owner, canonical_writer_string((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).current_accuracy).value, (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).current_accuracy).byte_count, (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).current_accuracy).has_byte_count));
                                if (!child85) goto no_memory;
                                cJSON_DetachItemViaPointer(owner, child85);
                                if (!cJSON_AddItemToObject(child73, "current_accuracy", child85)) { cJSON_Delete(child85); goto no_memory; }
                            }
                            if (!((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).has_presence || (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).present_fields & (UINT64_C(1) << 5)))                             {
                                cJSON *child86 = NULL;
                                if (!(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).reference_2020_equivalence).value) goto invalid;
                                child86 = canonical_track_json(owner, canonical_writer_string((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).reference_2020_equivalence).value, (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).reference_2020_equivalence).byte_count, (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).reference_2020_equivalence).has_byte_count));
                                if (!child86) goto no_memory;
                                cJSON_DetachItemViaPointer(owner, child86);
                                if (!cJSON_AddItemToObject(child73, "reference_2020_equivalence", child86)) { cJSON_Delete(child86); goto no_memory; }
                            }
                            if (!((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).has_presence || (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).present_fields & (UINT64_C(1) << 6)))                             {
                                cJSON *child87 = NULL;
                                if (!(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).reference_2020_equivalence_sha256).value) goto invalid;
                                child87 = canonical_track_json(owner, canonical_writer_string((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).reference_2020_equivalence_sha256).value, (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).reference_2020_equivalence_sha256).byte_count, (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).reference_2020_equivalence_sha256).has_byte_count));
                                if (!child87) goto no_memory;
                                cJSON_DetachItemViaPointer(owner, child87);
                                if (!cJSON_AddItemToObject(child73, "reference_2020_equivalence_sha256", child87)) { cJSON_Delete(child87); goto no_memory; }
                            }
                            if (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).extensions.count && !((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).extensions.entries) goto invalid;
                            for (size_t extra88=0; extra88<((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).extensions.count; extra88++) {
                                cJSON *child88=NULL;
                                const otc_cp_JsonValue_map_entry *entry=&((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).vintage).extensions.entries[extra88];
                                if (!entry->key.value) goto invalid;
                                if (!strcmp(entry->key.value, "publication_year")) goto invalid;
                                if (!strcmp(entry->key.value, "source_lifecycle")) goto invalid;
                                if (!strcmp(entry->key.value, "removal_events")) goto invalid;
                                if (!strcmp(entry->key.value, "current_validity")) goto invalid;
                                if (!strcmp(entry->key.value, "current_accuracy")) goto invalid;
                                if (!strcmp(entry->key.value, "reference_2020_equivalence")) goto invalid;
                                if (!strcmp(entry->key.value, "reference_2020_equivalence_sha256")) goto invalid;
                                child88 = canonical_track_json(owner, canonical_source_json(&(entry->value)));
                                if (!child88) goto no_memory;
                                cJSON_DetachItemViaPointer(owner, child88);
                                cJSON_DetachItemViaPointer(owner, child88);
                                if (!cJSON_AddItemToObject(child73, entry->key.value, child88)) { cJSON_Delete(child88); goto no_memory; }
                            }
                            cJSON_DetachItemViaPointer(owner, child73);
                            if (!cJSON_AddItemToObject(child46, "vintage", child73)) { cJSON_Delete(child73); goto no_memory; }
                        }
                        if (!(((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).has_presence || ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).present_fields & (UINT64_C(1) << 17)))                         {
                            cJSON *child89 = NULL;
                            child89 = canonical_track_json(owner, cJSON_CreateObject());
                            if (!child89) goto no_memory;
                            if (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).has_presence && (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).present_fields & UINT64_C(2047)) != UINT64_C(2047)) goto invalid;
                            if (!((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).has_presence || (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).present_fields & (UINT64_C(1) << 0)))                             {
                                cJSON *child90 = NULL;
                                if (!(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).source_manifest_sha256).value) goto invalid;
                                child90 = canonical_track_json(owner, canonical_writer_string((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).source_manifest_sha256).value, (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).source_manifest_sha256).byte_count, (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).source_manifest_sha256).has_byte_count));
                                if (!child90) goto no_memory;
                                cJSON_DetachItemViaPointer(owner, child90);
                                if (!cJSON_AddItemToObject(child89, "source_manifest_sha256", child90)) { cJSON_Delete(child90); goto no_memory; }
                            }
                            if (!((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).has_presence || (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).present_fields & (UINT64_C(1) << 1)))                             {
                                cJSON *child91 = NULL;
                                if ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).input_sha256).count && !(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).input_sha256).items) goto invalid;
                                child91 = canonical_track_json(owner, cJSON_CreateArray());
                                if (!child91) goto no_memory;
                                for (size_t i92 = 0; i92 < (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).input_sha256).count; i92++) {
                                    cJSON *child92 = NULL;
                                    if (!((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).input_sha256).items[i92]).value) goto invalid;
                                    child92 = canonical_track_json(owner, canonical_writer_string(((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).input_sha256).items[i92]).value, ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).input_sha256).items[i92]).byte_count, ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).input_sha256).items[i92]).has_byte_count));
                                    if (!child92) goto no_memory;
                                    cJSON_DetachItemViaPointer(owner, child92);
                                    if (!cJSON_AddItemToArray(child91, child92)) { cJSON_Delete(child92); goto no_memory; }
                                }
                                cJSON_DetachItemViaPointer(owner, child91);
                                if (!cJSON_AddItemToObject(child89, "input_sha256", child91)) { cJSON_Delete(child91); goto no_memory; }
                            }
                            if (!((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).has_presence || (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).present_fields & (UINT64_C(1) << 2)))                             {
                                cJSON *child93 = NULL;
                                if (!(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).book).value) goto invalid;
                                child93 = canonical_track_json(owner, canonical_writer_string((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).book).value, (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).book).byte_count, (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).book).has_byte_count));
                                if (!child93) goto no_memory;
                                cJSON_DetachItemViaPointer(owner, child93);
                                if (!cJSON_AddItemToObject(child89, "book", child93)) { cJSON_Delete(child93); goto no_memory; }
                            }
                            if (!((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).has_presence || (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).present_fields & (UINT64_C(1) << 3)))                             {
                                cJSON *child94 = NULL;
                                child94 = canonical_track_json(owner, cJSON_CreateNumber((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).annual_table_row).value));
                                if (!child94) goto no_memory;
                                cJSON_DetachItemViaPointer(owner, child94);
                                if (!cJSON_AddItemToObject(child89, "annual_table_row", child94)) { cJSON_Delete(child94); goto no_memory; }
                            }
                            if (!((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).has_presence || (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).present_fields & (UINT64_C(1) << 4)))                             {
                                cJSON *child95 = NULL;
                                child95 = canonical_track_json(owner, cJSON_CreateNumber((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).printed_page).value));
                                if (!child95) goto no_memory;
                                cJSON_DetachItemViaPointer(owner, child95);
                                if (!cJSON_AddItemToObject(child89, "printed_page", child95)) { cJSON_Delete(child95); goto no_memory; }
                            }
                            if (!((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).has_presence || (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).present_fields & (UINT64_C(1) << 5)))                             {
                                cJSON *child96 = NULL;
                                child96 = canonical_track_json(owner, cJSON_CreateNumber((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).pdf_page).value));
                                if (!child96) goto no_memory;
                                cJSON_DetachItemViaPointer(owner, child96);
                                if (!cJSON_AddItemToObject(child89, "pdf_page", child96)) { cJSON_Delete(child96); goto no_memory; }
                            }
                            if (!((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).has_presence || (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).present_fields & (UINT64_C(1) << 6)))                             {
                                cJSON *child97 = NULL;
                                if (!(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).raw_row_text).value) goto invalid;
                                child97 = canonical_track_json(owner, canonical_writer_string((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).raw_row_text).value, (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).raw_row_text).byte_count, (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).raw_row_text).has_byte_count));
                                if (!child97) goto no_memory;
                                cJSON_DetachItemViaPointer(owner, child97);
                                if (!cJSON_AddItemToObject(child89, "raw_row_text", child97)) { cJSON_Delete(child97); goto no_memory; }
                            }
                            if (!((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).has_presence || (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).present_fields & (UINT64_C(1) << 7)))                             {
                                cJSON *child98 = NULL;
                                if (!(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).raw_values_json).value) goto invalid;
                                child98 = canonical_track_json(owner, canonical_writer_string((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).raw_values_json).value, (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).raw_values_json).byte_count, (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).raw_values_json).has_byte_count));
                                if (!child98) goto no_memory;
                                cJSON_DetachItemViaPointer(owner, child98);
                                if (!cJSON_AddItemToObject(child89, "raw_values_json", child98)) { cJSON_Delete(child98); goto no_memory; }
                            }
                            if (!((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).has_presence || (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).present_fields & (UINT64_C(1) << 8)))                             {
                                cJSON *child99 = NULL;
                                child99 = canonical_track_json(owner, cJSON_CreateObject());
                                if (!child99) goto no_memory;
                                if ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).id_crosswalk).has_presence && ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).id_crosswalk).present_fields & UINT64_C(15)) != UINT64_C(15)) goto invalid;
                                if (!(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).id_crosswalk).has_presence || ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).id_crosswalk).present_fields & (UINT64_C(1) << 0)))                                 {
                                    cJSON *child100 = NULL;
                                    if (!((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).id_crosswalk).legacy_id).value) goto invalid;
                                    child100 = canonical_track_json(owner, canonical_writer_string(((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).id_crosswalk).legacy_id).value, ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).id_crosswalk).legacy_id).byte_count, ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).id_crosswalk).legacy_id).has_byte_count));
                                    if (!child100) goto no_memory;
                                    cJSON_DetachItemViaPointer(owner, child100);
                                    if (!cJSON_AddItemToObject(child99, "legacy_id", child100)) { cJSON_Delete(child100); goto no_memory; }
                                }
                                if (!(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).id_crosswalk).has_presence || ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).id_crosswalk).present_fields & (UINT64_C(1) << 1)))                                 {
                                    cJSON *child101 = NULL;
                                    if (!((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).id_crosswalk).status).value) goto invalid;
                                    child101 = canonical_track_json(owner, canonical_writer_string(((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).id_crosswalk).status).value, ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).id_crosswalk).status).byte_count, ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).id_crosswalk).status).has_byte_count));
                                    if (!child101) goto no_memory;
                                    cJSON_DetachItemViaPointer(owner, child101);
                                    if (!cJSON_AddItemToObject(child99, "status", child101)) { cJSON_Delete(child101); goto no_memory; }
                                }
                                if (!(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).id_crosswalk).has_presence || ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).id_crosswalk).present_fields & (UINT64_C(1) << 2)))                                 {
                                    cJSON *child102 = NULL;
                                    if (!((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).id_crosswalk).modern_alias_verified).value) goto invalid;
                                    child102 = canonical_track_json(owner, canonical_writer_string(((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).id_crosswalk).modern_alias_verified).value, ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).id_crosswalk).modern_alias_verified).byte_count, ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).id_crosswalk).modern_alias_verified).has_byte_count));
                                    if (!child102) goto no_memory;
                                    cJSON_DetachItemViaPointer(owner, child102);
                                    if (!cJSON_AddItemToObject(child99, "modern_alias_verified", child102)) { cJSON_Delete(child102); goto no_memory; }
                                }
                                if (!(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).id_crosswalk).has_presence || ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).id_crosswalk).present_fields & (UINT64_C(1) << 3)))                                 {
                                    cJSON *child103 = NULL;
                                    if (((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).id_crosswalk).evidence_sha256).count && !((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).id_crosswalk).evidence_sha256).items) goto invalid;
                                    child103 = canonical_track_json(owner, cJSON_CreateArray());
                                    if (!child103) goto no_memory;
                                    for (size_t i104 = 0; i104 < ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).id_crosswalk).evidence_sha256).count; i104++) {
                                        cJSON *child104 = NULL;
                                        if (!(((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).id_crosswalk).evidence_sha256).items[i104]).value) goto invalid;
                                        child104 = canonical_track_json(owner, canonical_writer_string((((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).id_crosswalk).evidence_sha256).items[i104]).value, (((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).id_crosswalk).evidence_sha256).items[i104]).byte_count, (((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).id_crosswalk).evidence_sha256).items[i104]).has_byte_count));
                                        if (!child104) goto no_memory;
                                        cJSON_DetachItemViaPointer(owner, child104);
                                        if (!cJSON_AddItemToArray(child103, child104)) { cJSON_Delete(child104); goto no_memory; }
                                    }
                                    cJSON_DetachItemViaPointer(owner, child103);
                                    if (!cJSON_AddItemToObject(child99, "evidence_sha256", child103)) { cJSON_Delete(child103); goto no_memory; }
                                }
                                if ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).id_crosswalk).extensions.count && !(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).id_crosswalk).extensions.entries) goto invalid;
                                for (size_t extra105=0; extra105<(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).id_crosswalk).extensions.count; extra105++) {
                                    cJSON *child105=NULL;
                                    const otc_cp_JsonValue_map_entry *entry=&(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).id_crosswalk).extensions.entries[extra105];
                                    if (!entry->key.value) goto invalid;
                                    if (!strcmp(entry->key.value, "legacy_id")) goto invalid;
                                    if (!strcmp(entry->key.value, "status")) goto invalid;
                                    if (!strcmp(entry->key.value, "modern_alias_verified")) goto invalid;
                                    if (!strcmp(entry->key.value, "evidence_sha256")) goto invalid;
                                    child105 = canonical_track_json(owner, canonical_source_json(&(entry->value)));
                                    if (!child105) goto no_memory;
                                    cJSON_DetachItemViaPointer(owner, child105);
                                    cJSON_DetachItemViaPointer(owner, child105);
                                    if (!cJSON_AddItemToObject(child99, entry->key.value, child105)) { cJSON_Delete(child105); goto no_memory; }
                                }
                                cJSON_DetachItemViaPointer(owner, child99);
                                if (!cJSON_AddItemToObject(child89, "id_crosswalk", child99)) { cJSON_Delete(child99); goto no_memory; }
                            }
                            if (!((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).has_presence || (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).present_fields & (UINT64_C(1) << 9)))                             {
                                cJSON *child106 = NULL;
                                child106 = canonical_track_json(owner, cJSON_CreateObject());
                                if (!child106) goto no_memory;
                                if ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).reference_binding).has_presence && ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).reference_binding).present_fields & UINT64_C(15)) != UINT64_C(15)) goto invalid;
                                if (!(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).reference_binding).has_presence || ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).reference_binding).present_fields & (UINT64_C(1) << 0)))                                 {
                                    cJSON *child107 = NULL;
                                    if (!((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).reference_binding).noaa_id).value) goto invalid;
                                    child107 = canonical_track_json(owner, canonical_writer_string(((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).reference_binding).noaa_id).value, ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).reference_binding).noaa_id).byte_count, ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).reference_binding).noaa_id).has_byte_count));
                                    if (!child107) goto no_memory;
                                    cJSON_DetachItemViaPointer(owner, child107);
                                    if (!cJSON_AddItemToObject(child106, "noaa_id", child107)) { cJSON_Delete(child107); goto no_memory; }
                                }
                                if (!(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).reference_binding).has_presence || ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).reference_binding).present_fields & (UINT64_C(1) << 1)))                                 {
                                    cJSON *child108 = NULL;
                                    if (!((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).reference_binding).station_id).value) goto invalid;
                                    child108 = canonical_track_json(owner, canonical_writer_string(((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).reference_binding).station_id).value, ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).reference_binding).station_id).byte_count, ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).reference_binding).station_id).has_byte_count));
                                    if (!child108) goto no_memory;
                                    cJSON_DetachItemViaPointer(owner, child108);
                                    if (!cJSON_AddItemToObject(child106, "station_id", child108)) { cJSON_Delete(child108); goto no_memory; }
                                }
                                if (!(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).reference_binding).has_presence || ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).reference_binding).present_fields & (UINT64_C(1) << 2)))                                 {
                                    cJSON *child109 = NULL;
                                    if (!((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).reference_binding).mapping_status).value) goto invalid;
                                    child109 = canonical_track_json(owner, canonical_writer_string(((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).reference_binding).mapping_status).value, ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).reference_binding).mapping_status).byte_count, ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).reference_binding).mapping_status).has_byte_count));
                                    if (!child109) goto no_memory;
                                    cJSON_DetachItemViaPointer(owner, child109);
                                    if (!cJSON_AddItemToObject(child106, "mapping_status", child109)) { cJSON_Delete(child109); goto no_memory; }
                                }
                                if (!(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).reference_binding).has_presence || ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).reference_binding).present_fields & (UINT64_C(1) << 3)))                                 {
                                    cJSON *child110 = NULL;
                                    if (((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).reference_binding).evidence_sha256).count && !((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).reference_binding).evidence_sha256).items) goto invalid;
                                    child110 = canonical_track_json(owner, cJSON_CreateArray());
                                    if (!child110) goto no_memory;
                                    for (size_t i111 = 0; i111 < ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).reference_binding).evidence_sha256).count; i111++) {
                                        cJSON *child111 = NULL;
                                        if (!(((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).reference_binding).evidence_sha256).items[i111]).value) goto invalid;
                                        child111 = canonical_track_json(owner, canonical_writer_string((((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).reference_binding).evidence_sha256).items[i111]).value, (((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).reference_binding).evidence_sha256).items[i111]).byte_count, (((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).reference_binding).evidence_sha256).items[i111]).has_byte_count));
                                        if (!child111) goto no_memory;
                                        cJSON_DetachItemViaPointer(owner, child111);
                                        if (!cJSON_AddItemToArray(child110, child111)) { cJSON_Delete(child111); goto no_memory; }
                                    }
                                    cJSON_DetachItemViaPointer(owner, child110);
                                    if (!cJSON_AddItemToObject(child106, "evidence_sha256", child110)) { cJSON_Delete(child110); goto no_memory; }
                                }
                                if ((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).reference_binding).extensions.count && !(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).reference_binding).extensions.entries) goto invalid;
                                for (size_t extra112=0; extra112<(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).reference_binding).extensions.count; extra112++) {
                                    cJSON *child112=NULL;
                                    const otc_cp_JsonValue_map_entry *entry=&(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).reference_binding).extensions.entries[extra112];
                                    if (!entry->key.value) goto invalid;
                                    if (!strcmp(entry->key.value, "noaa_id")) goto invalid;
                                    if (!strcmp(entry->key.value, "station_id")) goto invalid;
                                    if (!strcmp(entry->key.value, "mapping_status")) goto invalid;
                                    if (!strcmp(entry->key.value, "evidence_sha256")) goto invalid;
                                    child112 = canonical_track_json(owner, canonical_source_json(&(entry->value)));
                                    if (!child112) goto no_memory;
                                    cJSON_DetachItemViaPointer(owner, child112);
                                    cJSON_DetachItemViaPointer(owner, child112);
                                    if (!cJSON_AddItemToObject(child106, entry->key.value, child112)) { cJSON_Delete(child112); goto no_memory; }
                                }
                                cJSON_DetachItemViaPointer(owner, child106);
                                if (!cJSON_AddItemToObject(child89, "reference_binding", child106)) { cJSON_Delete(child106); goto no_memory; }
                            }
                            if (!((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).has_presence || (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).present_fields & (UINT64_C(1) << 10)))                             {
                                cJSON *child113 = NULL;
                                if (!(((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).acceptance_report_sha256).value) goto invalid;
                                child113 = canonical_track_json(owner, canonical_writer_string((((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).acceptance_report_sha256).value, (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).acceptance_report_sha256).byte_count, (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).acceptance_report_sha256).has_byte_count));
                                if (!child113) goto no_memory;
                                cJSON_DetachItemViaPointer(owner, child113);
                                if (!cJSON_AddItemToObject(child89, "acceptance_report_sha256", child113)) { cJSON_Delete(child113); goto no_memory; }
                            }
                            if (((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).extensions.count && !((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).extensions.entries) goto invalid;
                            for (size_t extra114=0; extra114<((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).extensions.count; extra114++) {
                                cJSON *child114=NULL;
                                const otc_cp_JsonValue_map_entry *entry=&((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).provenance).extensions.entries[extra114];
                                if (!entry->key.value) goto invalid;
                                if (!strcmp(entry->key.value, "source_manifest_sha256")) goto invalid;
                                if (!strcmp(entry->key.value, "input_sha256")) goto invalid;
                                if (!strcmp(entry->key.value, "book")) goto invalid;
                                if (!strcmp(entry->key.value, "annual_table_row")) goto invalid;
                                if (!strcmp(entry->key.value, "printed_page")) goto invalid;
                                if (!strcmp(entry->key.value, "pdf_page")) goto invalid;
                                if (!strcmp(entry->key.value, "raw_row_text")) goto invalid;
                                if (!strcmp(entry->key.value, "raw_values_json")) goto invalid;
                                if (!strcmp(entry->key.value, "id_crosswalk")) goto invalid;
                                if (!strcmp(entry->key.value, "reference_binding")) goto invalid;
                                if (!strcmp(entry->key.value, "acceptance_report_sha256")) goto invalid;
                                child114 = canonical_track_json(owner, canonical_source_json(&(entry->value)));
                                if (!child114) goto no_memory;
                                cJSON_DetachItemViaPointer(owner, child114);
                                cJSON_DetachItemViaPointer(owner, child114);
                                if (!cJSON_AddItemToObject(child89, entry->key.value, child114)) { cJSON_Delete(child114); goto no_memory; }
                            }
                            cJSON_DetachItemViaPointer(owner, child89);
                            if (!cJSON_AddItemToObject(child46, "provenance", child89)) { cJSON_Delete(child89); goto no_memory; }
                        }
                        if ((((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).extensions.count && !(((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).extensions.entries) goto invalid;
                        for (size_t extra115=0; extra115<(((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).extensions.count; extra115++) {
                            cJSON *child115=NULL;
                            const otc_cp_JsonValue_map_entry *entry=&(((((input->value.stream_index).stations).items[i9]).subordinate_offsets).value.variant_0).extensions.entries[extra115];
                            if (!entry->key.value) goto invalid;
                            if (!strcmp(entry->key.value, "reference_station_id")) goto invalid;
                            if (!strcmp(entry->key.value, "time_offset_high_min")) goto invalid;
                            if (!strcmp(entry->key.value, "time_offset_low_min")) goto invalid;
                            if (!strcmp(entry->key.value, "height_offset_high")) goto invalid;
                            if (!strcmp(entry->key.value, "height_offset_low")) goto invalid;
                            if (!strcmp(entry->key.value, "height_adjusted_type")) goto invalid;
                            if (!strcmp(entry->key.value, "licence_id")) goto invalid;
                            if (!strcmp(entry->key.value, "datum")) goto invalid;
                            if (!strcmp(entry->key.value, "offset_id")) goto invalid;
                            if (!strcmp(entry->key.value, "source")) goto invalid;
                            if (!strcmp(entry->key.value, "source_type")) goto invalid;
                            if (!strcmp(entry->key.value, "source_version")) goto invalid;
                            if (!strcmp(entry->key.value, "source_record_id")) goto invalid;
                            if (!strcmp(entry->key.value, "qc_status")) goto invalid;
                            if (!strcmp(entry->key.value, "qc_flags")) goto invalid;
                            if (!strcmp(entry->key.value, "fallback")) goto invalid;
                            if (!strcmp(entry->key.value, "vintage")) goto invalid;
                            if (!strcmp(entry->key.value, "provenance")) goto invalid;
                            child115 = canonical_track_json(owner, canonical_source_json(&(entry->value)));
                            if (!child115) goto no_memory;
                            cJSON_DetachItemViaPointer(owner, child115);
                            cJSON_DetachItemViaPointer(owner, child115);
                            if (!cJSON_AddItemToObject(child46, entry->key.value, child115)) { cJSON_Delete(child115); goto no_memory; }
                        }
                        break;
                    }
                    case 1: {
                        child46 = canonical_track_json(owner, cJSON_CreateNull());
                        if (!child46) goto no_memory;
                        break;
                    }
                    default: goto invalid;
                    }
                    cJSON_DetachItemViaPointer(owner, child46);
                    if (!cJSON_AddItemToObject(child9, "subordinate_offsets", child46)) { cJSON_Delete(child46); goto no_memory; }
                }
                if (!(((input->value.stream_index).stations).items[i9]).has_presence || ((((input->value.stream_index).stations).items[i9]).present_fields & (UINT64_C(1) << 17)))                 {
                    cJSON *child116 = NULL;
                    if (((((input->value.stream_index).stations).items[i9]).current_offsets).count && !((((input->value.stream_index).stations).items[i9]).current_offsets).items) goto invalid;
                    child116 = canonical_track_json(owner, cJSON_CreateArray());
                    if (!child116) goto no_memory;
                    for (size_t i117 = 0; i117 < ((((input->value.stream_index).stations).items[i9]).current_offsets).count; i117++) {
                        cJSON *child117 = NULL;
                        child117 = canonical_track_json(owner, cJSON_CreateObject());
                        if (!child117) goto no_memory;
                        if ((((((input->value.stream_index).stations).items[i9]).current_offsets).items[i117]).has_presence && ((((((input->value.stream_index).stations).items[i9]).current_offsets).items[i117]).present_fields & UINT64_C(15)) != UINT64_C(15)) goto invalid;
                        if (!(((((input->value.stream_index).stations).items[i9]).current_offsets).items[i117]).has_presence || ((((((input->value.stream_index).stations).items[i9]).current_offsets).items[i117]).present_fields & (UINT64_C(1) << 0)))                         {
                            cJSON *child118 = NULL;
                            child118 = canonical_track_json(owner, cJSON_CreateNumber(((((((input->value.stream_index).stations).items[i9]).current_offsets).items[i117]).bin).value));
                            if (!child118) goto no_memory;
                            cJSON_DetachItemViaPointer(owner, child118);
                            if (!cJSON_AddItemToObject(child117, "bin", child118)) { cJSON_Delete(child118); goto no_memory; }
                        }
                        if (!(((((input->value.stream_index).stations).items[i9]).current_offsets).items[i117]).has_presence || ((((((input->value.stream_index).stations).items[i9]).current_offsets).items[i117]).present_fields & (UINT64_C(1) << 1)))                         {
                            cJSON *child119 = NULL;
                            child119 = canonical_track_json(owner, cJSON_CreateNumber(((((((input->value.stream_index).stations).items[i9]).current_offsets).items[i117]).reference_bin).value));
                            if (!child119) goto no_memory;
                            cJSON_DetachItemViaPointer(owner, child119);
                            if (!cJSON_AddItemToObject(child117, "reference_bin", child119)) { cJSON_Delete(child119); goto no_memory; }
                        }
                        if (!(((((input->value.stream_index).stations).items[i9]).current_offsets).items[i117]).has_presence || ((((((input->value.stream_index).stations).items[i9]).current_offsets).items[i117]).present_fields & (UINT64_C(1) << 2)))                         {
                            cJSON *child120 = NULL;
                            switch (((((((input->value.stream_index).stations).items[i9]).current_offsets).items[i117]).reference_station_id).tag) {
                            case 0: {
                                if (!(((((((input->value.stream_index).stations).items[i9]).current_offsets).items[i117]).reference_station_id).value.variant_0).value) goto invalid;
                                child120 = canonical_track_json(owner, canonical_writer_string((((((((input->value.stream_index).stations).items[i9]).current_offsets).items[i117]).reference_station_id).value.variant_0).value, (((((((input->value.stream_index).stations).items[i9]).current_offsets).items[i117]).reference_station_id).value.variant_0).byte_count, (((((((input->value.stream_index).stations).items[i9]).current_offsets).items[i117]).reference_station_id).value.variant_0).has_byte_count));
                                if (!child120) goto no_memory;
                                break;
                            }
                            case 1: {
                                child120 = canonical_track_json(owner, cJSON_CreateNull());
                                if (!child120) goto no_memory;
                                break;
                            }
                            default: goto invalid;
                            }
                            cJSON_DetachItemViaPointer(owner, child120);
                            if (!cJSON_AddItemToObject(child117, "reference_station_id", child120)) { cJSON_Delete(child120); goto no_memory; }
                        }
                        if (!(((((input->value.stream_index).stations).items[i9]).current_offsets).items[i117]).has_presence || ((((((input->value.stream_index).stations).items[i9]).current_offsets).items[i117]).present_fields & (UINT64_C(1) << 3)))                         {
                            cJSON *child121 = NULL;
                            switch (((((((input->value.stream_index).stations).items[i9]).current_offsets).items[i117]).licence_id).tag) {
                            case 0: {
                                if (!(((((((input->value.stream_index).stations).items[i9]).current_offsets).items[i117]).licence_id).value.variant_0).value) goto invalid;
                                child121 = canonical_track_json(owner, canonical_writer_string((((((((input->value.stream_index).stations).items[i9]).current_offsets).items[i117]).licence_id).value.variant_0).value, (((((((input->value.stream_index).stations).items[i9]).current_offsets).items[i117]).licence_id).value.variant_0).byte_count, (((((((input->value.stream_index).stations).items[i9]).current_offsets).items[i117]).licence_id).value.variant_0).has_byte_count));
                                if (!child121) goto no_memory;
                                break;
                            }
                            case 1: {
                                child121 = canonical_track_json(owner, cJSON_CreateNull());
                                if (!child121) goto no_memory;
                                break;
                            }
                            default: goto invalid;
                            }
                            cJSON_DetachItemViaPointer(owner, child121);
                            if (!cJSON_AddItemToObject(child117, "licence_id", child121)) { cJSON_Delete(child121); goto no_memory; }
                        }
                        cJSON_DetachItemViaPointer(owner, child117);
                        if (!cJSON_AddItemToArray(child116, child117)) { cJSON_Delete(child117); goto no_memory; }
                    }
                    cJSON_DetachItemViaPointer(owner, child116);
                    if (!cJSON_AddItemToObject(child9, "current_offsets", child116)) { cJSON_Delete(child116); goto no_memory; }
                }
                cJSON_DetachItemViaPointer(owner, child9);
                if (!cJSON_AddItemToArray(child8, child9)) { cJSON_Delete(child9); goto no_memory; }
            }
            cJSON_DetachItemViaPointer(owner, child8);
            if (!cJSON_AddItemToObject(result, "stations", child8)) { cJSON_Delete(child8); goto no_memory; }
        }
        break;
    }
    case 1: {
        result = canonical_track_json(owner, cJSON_CreateObject());
        if (!result) goto no_memory;
        if ((input->value.verified_receipt).has_presence && ((input->value.verified_receipt).present_fields & UINT64_C(127)) != UINT64_C(127)) goto invalid;
        if (!(input->value.verified_receipt).has_presence || ((input->value.verified_receipt).present_fields & (UINT64_C(1) << 0)))         {
            cJSON *child122 = NULL;
            if (!((input->value.verified_receipt).datestamp).value) goto invalid;
            child122 = canonical_track_json(owner, canonical_writer_string(((input->value.verified_receipt).datestamp).value, ((input->value.verified_receipt).datestamp).byte_count, ((input->value.verified_receipt).datestamp).has_byte_count));
            if (!child122) goto no_memory;
            cJSON_DetachItemViaPointer(owner, child122);
            if (!cJSON_AddItemToObject(result, "datestamp", child122)) { cJSON_Delete(child122); goto no_memory; }
        }
        if (!(input->value.verified_receipt).has_presence || ((input->value.verified_receipt).present_fields & (UINT64_C(1) << 1)))         {
            cJSON *child123 = NULL;
            if (((input->value.verified_receipt).files).count && !((input->value.verified_receipt).files).entries) goto invalid;
            child123 = canonical_track_json(owner, cJSON_CreateObject());
            if (!child123) goto no_memory;
            for (size_t i124 = 0; i124 < ((input->value.verified_receipt).files).count; i124++) {
                cJSON *child124 = NULL;
                child124 = canonical_track_json(owner, cJSON_CreateObject());
                if (!child124) goto no_memory;
                if ((((input->value.verified_receipt).files).entries[i124].value).has_presence && ((((input->value.verified_receipt).files).entries[i124].value).present_fields & UINT64_C(0)) != UINT64_C(0)) goto invalid;
                if (!(((input->value.verified_receipt).files).entries[i124].value).has_presence || ((((input->value.verified_receipt).files).entries[i124].value).present_fields & (UINT64_C(1) << 0)))                 {
                    cJSON *child125 = NULL;
                    if (!((((input->value.verified_receipt).files).entries[i124].value).sha256).value) goto invalid;
                    child125 = canonical_track_json(owner, canonical_writer_string(((((input->value.verified_receipt).files).entries[i124].value).sha256).value, ((((input->value.verified_receipt).files).entries[i124].value).sha256).byte_count, ((((input->value.verified_receipt).files).entries[i124].value).sha256).has_byte_count));
                    if (!child125) goto no_memory;
                    cJSON_DetachItemViaPointer(owner, child125);
                    if (!cJSON_AddItemToObject(child124, "sha256", child125)) { cJSON_Delete(child125); goto no_memory; }
                }
                if (!(((input->value.verified_receipt).files).entries[i124].value).has_presence || ((((input->value.verified_receipt).files).entries[i124].value).present_fields & (UINT64_C(1) << 1)))                 {
                    cJSON *child126 = NULL;
                    child126 = canonical_track_json(owner, cJSON_CreateNumber(((((input->value.verified_receipt).files).entries[i124].value).size).value));
                    if (!child126) goto no_memory;
                    cJSON_DetachItemViaPointer(owner, child126);
                    if (!cJSON_AddItemToObject(child124, "size", child126)) { cJSON_Delete(child126); goto no_memory; }
                }
                if (!(((input->value.verified_receipt).files).entries[i124].value).has_presence || ((((input->value.verified_receipt).files).entries[i124].value).present_fields & (UINT64_C(1) << 2)))                 {
                    cJSON *child127 = NULL;
                    switch (((((input->value.verified_receipt).files).entries[i124].value).url).tag) {
                    case 0: {
                        if (!(((((input->value.verified_receipt).files).entries[i124].value).url).value.variant_0).value) goto invalid;
                        child127 = canonical_track_json(owner, canonical_writer_string((((((input->value.verified_receipt).files).entries[i124].value).url).value.variant_0).value, (((((input->value.verified_receipt).files).entries[i124].value).url).value.variant_0).byte_count, (((((input->value.verified_receipt).files).entries[i124].value).url).value.variant_0).has_byte_count));
                        if (!child127) goto no_memory;
                        break;
                    }
                    case 1: {
                        child127 = canonical_track_json(owner, cJSON_CreateNull());
                        if (!child127) goto no_memory;
                        break;
                    }
                    default: goto invalid;
                    }
                    cJSON_DetachItemViaPointer(owner, child127);
                    if (!cJSON_AddItemToObject(child124, "url", child127)) { cJSON_Delete(child127); goto no_memory; }
                }
                cJSON_DetachItemViaPointer(owner, child124);
                if (!((input->value.verified_receipt).files).entries[i124].key.value || !cJSON_AddItemToObject(child123, ((input->value.verified_receipt).files).entries[i124].key.value, child124)) { cJSON_Delete(child124); goto no_memory; }
            }
            cJSON_DetachItemViaPointer(owner, child123);
            if (!cJSON_AddItemToObject(result, "files", child123)) { cJSON_Delete(child123); goto no_memory; }
        }
        if (!(input->value.verified_receipt).has_presence || ((input->value.verified_receipt).present_fields & (UINT64_C(1) << 2)))         {
            cJSON *child128 = NULL;
            if (!((input->value.verified_receipt).format_version).value) goto invalid;
            child128 = canonical_track_json(owner, canonical_writer_string(((input->value.verified_receipt).format_version).value, ((input->value.verified_receipt).format_version).byte_count, ((input->value.verified_receipt).format_version).has_byte_count));
            if (!child128) goto no_memory;
            cJSON_DetachItemViaPointer(owner, child128);
            if (!cJSON_AddItemToObject(result, "format_version", child128)) { cJSON_Delete(child128); goto no_memory; }
        }
        if (!(input->value.verified_receipt).has_presence || ((input->value.verified_receipt).present_fields & (UINT64_C(1) << 3)))         {
            cJSON *child129 = NULL;
            if (!((input->value.verified_receipt).min_reader_version).value) goto invalid;
            child129 = canonical_track_json(owner, canonical_writer_string(((input->value.verified_receipt).min_reader_version).value, ((input->value.verified_receipt).min_reader_version).byte_count, ((input->value.verified_receipt).min_reader_version).has_byte_count));
            if (!child129) goto no_memory;
            cJSON_DetachItemViaPointer(owner, child129);
            if (!cJSON_AddItemToObject(result, "min_reader_version", child129)) { cJSON_Delete(child129); goto no_memory; }
        }
        if (!(input->value.verified_receipt).has_presence || ((input->value.verified_receipt).present_fields & (UINT64_C(1) << 4)))         {
            cJSON *child130 = NULL;
            switch (((input->value.verified_receipt).zenodo_version_doi).tag) {
            case 0: {
                if (!(((input->value.verified_receipt).zenodo_version_doi).value.variant_0).value) goto invalid;
                child130 = canonical_track_json(owner, canonical_writer_string((((input->value.verified_receipt).zenodo_version_doi).value.variant_0).value, (((input->value.verified_receipt).zenodo_version_doi).value.variant_0).byte_count, (((input->value.verified_receipt).zenodo_version_doi).value.variant_0).has_byte_count));
                if (!child130) goto no_memory;
                break;
            }
            case 1: {
                child130 = canonical_track_json(owner, cJSON_CreateNull());
                if (!child130) goto no_memory;
                break;
            }
            default: goto invalid;
            }
            cJSON_DetachItemViaPointer(owner, child130);
            if (!cJSON_AddItemToObject(result, "zenodo_version_doi", child130)) { cJSON_Delete(child130); goto no_memory; }
        }
        if (!(input->value.verified_receipt).has_presence || ((input->value.verified_receipt).present_fields & (UINT64_C(1) << 5)))         {
            cJSON *child131 = NULL;
            if (!((input->value.verified_receipt).verified_at).value) goto invalid;
            child131 = canonical_track_json(owner, canonical_writer_string(((input->value.verified_receipt).verified_at).value, ((input->value.verified_receipt).verified_at).byte_count, ((input->value.verified_receipt).verified_at).has_byte_count));
            if (!child131) goto no_memory;
            cJSON_DetachItemViaPointer(owner, child131);
            if (!cJSON_AddItemToObject(result, "verified_at", child131)) { cJSON_Delete(child131); goto no_memory; }
        }
        if (!(input->value.verified_receipt).has_presence || ((input->value.verified_receipt).present_fields & (UINT64_C(1) << 6)))         {
            cJSON *child132 = NULL;
            if (!((input->value.verified_receipt).by).value) goto invalid;
            child132 = canonical_track_json(owner, canonical_writer_string(((input->value.verified_receipt).by).value, ((input->value.verified_receipt).by).byte_count, ((input->value.verified_receipt).by).has_byte_count));
            if (!child132) goto no_memory;
            cJSON_DetachItemViaPointer(owner, child132);
            if (!cJSON_AddItemToObject(result, "by", child132)) { cJSON_Delete(child132); goto no_memory; }
        }
        break;
    }
    case 2: {
        result = canonical_track_json(owner, canonical_source_json(&(input->value.pointer_or_catalogue)));
        if (!result) goto no_memory;
        break;
    }
    default: goto invalid;
    }
    cJSON_DetachItemViaPointer(owner, result); cJSON_Delete(owner);
    *out = result; return OTC_OK;
invalid:
    cJSON_Delete(owner); return OTC_E_INVALID_ARGUMENT;
no_memory:
    cJSON_Delete(owner); return OTC_E_NOMEM;
}

struct otc_cp_index_allocation { void *data; struct otc_cp_index_allocation *next; };
struct otc_cp_index_owner { cJSON *document; struct otc_cp_index_allocation *allocations; };

static void *canonical_index_alloc(struct otc_cp_index_owner *owner, size_t count, size_t width)
{
    struct otc_cp_index_allocation *entry;
    void *data;
    if (count > SIZE_MAX / width) return NULL;
    entry = malloc(sizeof *entry);
    if (!entry) return NULL;
    data = calloc(count ? count : 1, width);
    if (!data) { free(entry); return NULL; }
    entry->data = data; entry->next = owner->allocations; owner->allocations = entry;
    return data;
}

static void canonical_index_owner_free(struct otc_cp_index_owner *owner)
{
    struct otc_cp_index_allocation *entry, *next;
    if (!owner) return;
    for (entry = owner->allocations; entry; entry = next) { next = entry->next; free(entry->data); free(entry); }
    cJSON_Delete(owner->document); free(owner);
}

void otc__canonical_station_index_clear(otc_cp_station_index_entry *entry)
{
    if (!entry) return;
    canonical_index_owner_free(entry->native_owner); memset(entry, 0, sizeof *entry);
}

static otc_status canonical_native_json(struct otc_cp_index_owner *owner, const cJSON *source, otc_cp_JsonValue *out)
{
    const cJSON *child;
    size_t count, i = 0;
    otc_status status;
    memset(out, 0, sizeof *out);
    if (cJSON_IsString(source)) { out->tag = OTC_CP_JSON_STRING; out->value.string.bytes = source->valuestring; out->value.string.count = otc__jstr_len(source); }
    else if (cJSON_IsNumber(source)) { out->tag = OTC_CP_JSON_NUMBER; out->value.number = source->valuedouble; }
    else if (cJSON_IsBool(source)) { out->tag = OTC_CP_JSON_BOOLEAN; out->value.boolean = cJSON_IsTrue(source); }
    else if (cJSON_IsArray(source)) {
        otc_cp_JsonValue *items;
        out->tag = OTC_CP_JSON_ARRAY; count = (size_t)cJSON_GetArraySize(source);
        items = canonical_index_alloc(owner, count, sizeof *items); if (!items) return OTC_E_NOMEM;
        out->value.array.items = items; out->value.array.count = count;
        cJSON_ArrayForEach(child, source) { status = canonical_native_json(owner, child, &items[i++]); if (status != OTC_OK) return status; }
    } else if (cJSON_IsObject(source)) {
        otc_cp_JsonPair *pairs;
        out->tag = OTC_CP_JSON_OBJECT; count = (size_t)cJSON_GetArraySize(source);
        pairs = canonical_index_alloc(owner, count, sizeof *pairs); if (!pairs) return OTC_E_NOMEM;
        out->value.members.entries = pairs; out->value.members.count = count;
        cJSON_ArrayForEach(child, source) {
            otc_cp_JsonValue *value = canonical_index_alloc(owner, 1, sizeof *value); if (!value) return OTC_E_NOMEM;
            pairs[i].key = child->string; pairs[i++].value = value;
            status = canonical_native_json(owner, child, value); if (status != OTC_OK) return status;
        }
    } else if (!cJSON_IsNull(source)) return OTC_E_INVALID_ARGUMENT;
    return OTC_OK;
}

static const char *const canonical_error_names[] = { "invalid_argument", "network", "release_not_found", "offline_unavailable", "checksum_mismatch", "unsupported_format", "reader_too_old", "invalid_release", "cache", "io", "unsupported", "pinned_release", "buffer_too_small", "file_exists", "not_built", "station_not_found", "station_removed", "no_constants", "quantity_mismatch", "unsupported_convention", "no_astro_table", "unsupported_constituent", "time_out_of_range", "datum_unavailable", "reference_unavailable", "extremes_only", "historical_offsets_excluded", "bin_not_found", "local_time_unavailable", "unknown_time_zone" };

/* An untouched output is not an invented result. No caller owns a result
 * from these private unimplemented entries. Public APIs retain their own
 * partial-output and failure-cleanup contracts. */
static const otc_cp_operation_tag canonical_argument_operations[] = {
    OTC_CP_OPERATION_OPEN,
    OTC_CP_OPERATION_RELEASES,
    OTC_CP_OPERATION_LATEST,
    OTC_CP_OPERATION_CHECK_FOR_UPDATE,
    OTC_CP_OPERATION_UPDATE,
    OTC_CP_OPERATION_DOWNLOAD,
    OTC_CP_OPERATION_VERIFY,
    OTC_CP_OPERATION_CACHED_RELEASES,
    OTC_CP_OPERATION_PRUNE,
    OTC_CP_OPERATION_CLOSE,
    OTC_CP_OPERATION_CONVENTION,
    OTC_CP_OPERATION_LICENCE,
    OTC_CP_OPERATION_STATION,
    OTC_CP_OPERATION_REQUIRE_STATION,
    OTC_CP_OPERATION_TOMBSTONE,
    OTC_CP_OPERATION_STATION_BY_ALIAS,
    OTC_CP_OPERATION_STATIONS,
    OTC_CP_OPERATION_ITER_STATIONS,
    OTC_CP_OPERATION_SEARCH,
    OTC_CP_OPERATION_NEAR,
    OTC_CP_OPERATION_NEAREST,
    OTC_CP_OPERATION_REFERENCE_STATION,
    OTC_CP_OPERATION_SUBORDINATES_OF,
    OTC_CP_OPERATION_ATTRIBUTION,
    OTC_CP_OPERATION_HEIGHTS,
    OTC_CP_OPERATION_HEIGHTS_AT,
    OTC_CP_OPERATION_EXTREMES,
    OTC_CP_OPERATION_CURRENTS,
    OTC_CP_OPERATION_CURRENT_EVENTS,
    OTC_CP_OPERATION_DATUMS,
    OTC_CP_OPERATION_RANGES,
    OTC_CP_OPERATION_ASTRO_TABLE,
    OTC_CP_OPERATION_CONSTANT_SETS,
    OTC_CP_OPERATION_CONSTANT_SET,
    OTC_CP_OPERATION_CONSTITUENT,
    OTC_CP_OPERATION_EQUILIBRIUM_ARGUMENT,
    OTC_CP_OPERATION_NODE_FACTOR,
    OTC_CP_OPERATION_EQUILIBRIUM_FOR_YEAR,
    OTC_CP_OPERATION_NODE_FACTOR_FOR_YEAR,
    OTC_CP_OPERATION_TO_LOCAL,
    OTC_CP_OPERATION_TO_LOCAL,
    OTC_CP_OPERATION_TO_LOCAL,
    OTC_CP_OPERATION_TO_LOCAL,
    OTC_CP_OPERATION_TO_LOCAL,
    OTC_CP_OPERATION_TO_LOCAL,
    OTC_CP_OPERATION_TO_LOCAL,
    OTC_CP_OPERATION_TO_LOCAL
};

otc_status otc__canonical_validate_operation_arguments(const otc_cp_operation *operation, const otc_cp_arguments *arguments, const otc_cp_member_contract *member_contract, otc_cp_validated_arguments *validated_arguments_out)
{
if (!operation || !arguments || !member_contract || !validated_arguments_out)
    return OTC_E_INVALID_ARGUMENT;
if (operation->value < OTC_CP_OPERATION_ASTRO_TABLE || operation->value > OTC_CP_OPERATION_VERIFY)
    return OTC_E_INVALID_ARGUMENT;
if (arguments->tag != member_contract->tag) return OTC_E_INVALID_ARGUMENT;
if ((size_t)arguments->tag >= sizeof canonical_argument_operations / sizeof canonical_argument_operations[0] ||
    canonical_argument_operations[arguments->tag] != operation->value) return OTC_E_INVALID_ARGUMENT;
if (arguments->tag == OTC_CP_SELECTED_ARGUMENTS_CLIENT_OPEN) {
    const otc_cp_args_Client_open *a = &arguments->value.Client_open;
    /* The existing runner's file/open guard precedes acquisition. */
    if (a->file.presence == OTC_CP_PRESENT_VALUE &&
        (a->release.presence == OTC_CP_PRESENT_VALUE ||
         (a->offline.presence == OTC_CP_PRESENT_VALUE && a->offline.value.value)))
        return OTC_E_INVALID_ARGUMENT;
}
if (arguments->tag == OTC_CP_SELECTED_ARGUMENTS_RELEASE_SEARCH ||
    arguments->tag == OTC_CP_SELECTED_ARGUMENTS_RELEASE_NEAR ||
    arguments->tag == OTC_CP_SELECTED_ARGUMENTS_RELEASE_NEAREST) {
    const otc_cp_native_query_arguments *context = member_contract->native_query;
    otc_status status;
    if (!context) return OTC_E_INVALID_ARGUMENT;
    if (arguments->tag == OTC_CP_SELECTED_ARGUMENTS_RELEASE_SEARCH) {
        const otc_cp_args_Release_search *a = &arguments->value.Release_search;
        status = otc__query_search_arguments(context->release,
            a->name.presence == OTC_CP_PRESENT_VALUE ? a->name.value.value : NULL,
            context->filter, a->limit.presence == OTC_CP_PRESENT_VALUE ? (size_t)a->limit.value.value : OTC_NO_LIMIT,
            context->output.search, context->capacity, context->count);
        if (status != OTC_OK) return status;
        if (!context->folded_search_name) return OTC_E_NOMEM;
        status = otc__query_search_folded_arguments(context->release, context->folded_search_name);
    } else if (arguments->tag == OTC_CP_SELECTED_ARGUMENTS_RELEASE_NEAR) {
        const otc_cp_args_Release_near *a = &arguments->value.Release_near;
        if (a->lat.presence != OTC_CP_PRESENT_VALUE || a->lon.presence != OTC_CP_PRESENT_VALUE ||
            a->radius_km.presence != OTC_CP_PRESENT_VALUE) return OTC_E_INVALID_ARGUMENT;
        status = otc__query_near_arguments(context->release, a->lat.value.value, a->lon.value.value, a->radius_km.value.value,
            context->filter, a->limit.presence == OTC_CP_PRESENT_VALUE ? (size_t)a->limit.value.value : OTC_NO_LIMIT,
            context->output.near, context->capacity, context->count);
    } else {
        const otc_cp_args_Release_nearest *a = &arguments->value.Release_nearest;
        double maximum = a->max_km.presence == OTC_CP_PRESENT_VALUE ? a->max_km.value.value : NAN;
        if (a->lat.presence != OTC_CP_PRESENT_VALUE || a->lon.presence != OTC_CP_PRESENT_VALUE) return OTC_E_INVALID_ARGUMENT;
        status = otc__query_nearest_arguments(context->release, a->lat.value.value, a->lon.value.value, &maximum,
            context->filter, context->output.nearest);
    }
    if (status != OTC_OK) return status;
}
*validated_arguments_out = *arguments;
return OTC_OK;

}

otc_status otc__canonical_resolve_effective_options(const otc_cp_explicit_options *explicit_options, const otc_cp_environment *environment, const otc_cp_platform_defaults *platform_defaults, otc_cp_effective_options *effective_options_out)
{
    size_t i;
    const char *offline = NULL, *cache = NULL, *base = NULL;
    if (!explicit_options || !environment || !platform_defaults || !effective_options_out ||
        (environment->count && !environment->entries)) return OTC_E_INVALID_ARGUMENT;
    *effective_options_out = *platform_defaults;
    if (explicit_options->release.presence != OTC_CP_ABSENT) effective_options_out->release = explicit_options->release;
    if (explicit_options->file.presence != OTC_CP_ABSENT) effective_options_out->file = explicit_options->file;
    if (explicit_options->cache_dir.presence != OTC_CP_ABSENT) effective_options_out->cache_dir = explicit_options->cache_dir;
    if (explicit_options->offline.presence != OTC_CP_ABSENT) effective_options_out->offline = explicit_options->offline;
    if (explicit_options->mode.presence != OTC_CP_ABSENT) effective_options_out->mode = explicit_options->mode;
    if (explicit_options->base_url.presence != OTC_CP_ABSENT) effective_options_out->base_url = explicit_options->base_url;
    if (explicit_options->timeout.presence != OTC_CP_ABSENT) effective_options_out->timeout = explicit_options->timeout;
    if (explicit_options->proxy.presence != OTC_CP_ABSENT) effective_options_out->proxy = explicit_options->proxy;
    if (explicit_options->ca_file.presence != OTC_CP_ABSENT) effective_options_out->ca_file = explicit_options->ca_file;
    if (explicit_options->user_agent.presence != OTC_CP_ABSENT) effective_options_out->user_agent = explicit_options->user_agent;
    if (explicit_options->on_network_error.presence != OTC_CP_ABSENT) effective_options_out->on_network_error = explicit_options->on_network_error;
    if (explicit_options->auto_update.presence != OTC_CP_ABSENT) effective_options_out->auto_update = explicit_options->auto_update;
    if (explicit_options->update_interval.presence != OTC_CP_ABSENT) effective_options_out->update_interval = explicit_options->update_interval;
    if (explicit_options->logger.presence != OTC_CP_ABSENT) effective_options_out->logger = explicit_options->logger;
    if (explicit_options->verify_on_open.presence != OTC_CP_ABSENT) effective_options_out->verify_on_open = explicit_options->verify_on_open;
    if (explicit_options->commercial_only.presence != OTC_CP_ABSENT) effective_options_out->commercial_only = explicit_options->commercial_only;
    if (explicit_options->commercial_basis.presence != OTC_CP_ABSENT) effective_options_out->commercial_basis = explicit_options->commercial_basis;
    if (explicit_options->historical_offsets_policy.presence != OTC_CP_ABSENT) effective_options_out->historical_offsets_policy = explicit_options->historical_offsets_policy;
    for (i = 0; i < environment->count; i++) {
        const otc_cp_String_map_entry *e = &environment->entries[i];
        if (!e->key.value) return OTC_E_INVALID_ARGUMENT;
        if (!strcmp(e->key.value, "OPENTIDECONSTANTS_OFFLINE")) offline = e->value.value;
        else if (!strcmp(e->key.value, "OPENTIDECONSTANTS_CACHE_DIR")) cache = e->value.value;
        else if (!strcmp(e->key.value, "OPENTIDECONSTANTS_BASE_URL")) base = e->value.value;
    }
    if (otc__option_env_on(offline)) {
        effective_options_out->offline.presence = OTC_CP_PRESENT_VALUE;
        effective_options_out->offline.value.value = true;
    }
    if (explicit_options->cache_dir.presence == OTC_CP_ABSENT && cache) {
        effective_options_out->cache_dir.presence = OTC_CP_PRESENT_VALUE;
        effective_options_out->cache_dir.value.value = cache;
    }
    if (explicit_options->base_url.presence == OTC_CP_ABSENT && base) {
        effective_options_out->base_url.presence = OTC_CP_PRESENT_VALUE;
        effective_options_out->base_url.value.value = base;
    }
    return OTC_OK;

}

otc_status otc__canonical_select_canonical_error(const otc_cp_operation *operation, const otc_cp_ordered_failures *ordered_failures, const otc_cp_cause *cause, otc_cp_canonical_error *canonical_error_out)
{
    if (!operation || !ordered_failures || !canonical_error_out || !ordered_failures->count || !ordered_failures->items)
        return OTC_E_INVALID_ARGUMENT;
    /* Failure order is already the exact owning operation's observed order. */
    *canonical_error_out = ordered_failures->items[0];
    if (cause) canonical_error_out->cause = *cause;
    return OTC_OK;
}

otc_status otc__canonical_translate_native_binding(const otc_cp_canonical_result *canonical_result, const otc_cp_canonical_error *canonical_error, const otc_cp_native_profile *native_profile, otc_cp_native_result *native_result_out)
{
    otc_status status;
    const char *name;
    if (!native_profile || native_profile->value != OTC_CP_NATIVE_PROFILE_C || !native_result_out)
        return OTC_E_INVALID_ARGUMENT;
    if (canonical_result) *native_result_out = *canonical_result;
    else native_result_out->presence = OTC_CP_ABSENT;
    if (!canonical_error) return canonical_result ? OTC_OK : OTC_E_INVALID_ARGUMENT;
    if (canonical_error->cause.presence == OTC_CP_PRESENT_VALUE &&
        canonical_error->cause.value.presence == OTC_CP_PRESENT_VALUE)
        return canonical_error->cause.value.value.status;
    if ((size_t)canonical_error->code.value >= sizeof canonical_error_names / sizeof canonical_error_names[0])
        return OTC_E_INVALID_ARGUMENT;
    name = canonical_error_names[canonical_error->code.value];
    for (status = OTC_OK; status <= OTC_E_HISTORICAL_OFFSETS_EXCLUDED; status++)
        if (!strcmp(otc_status_code(status), name)) return status;
    return OTC_E_INVALID_ARGUMENT;
}

otc_status otc__canonical_decode_release_document(const otc_cp_source_bytes *source_bytes, const otc_cp_reader_version *reader_version, const otc_cp_document_kind *document_kind, otc_cp_parsed_document *parsed_document_out)
{
    (void)source_bytes;
    (void)reader_version;
    (void)document_kind;
    (void)parsed_document_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_validate_release_links(const otc_cp_parsed_document *parsed_document, const otc_cp_required_links *required_links, otc_cp_validated_release_graph *validated_release_graph_out)
{
    (void)parsed_document;
    (void)required_links;
    (void)validated_release_graph_out;
    return OTC_E_NOT_BUILT;
}

struct otc_cp_native_model_owner {
    cJSON *raw;
    struct otc_cp_index_owner *json_storage;
    union {
        otc_record_span RecordSpan;
        otc_datum Datum;
        otc_dropped DroppedConstituent;
        otc_qc_flag QcFlag;
        otc_provenance_build ProvenanceBuild;
        otc_fallback Fallback;
        otc_historical_offset_vintage HistoricalOffsetVintage;
        otc_historical_offset_provenance HistoricalOffsetProvenance;
        otc_constituent_t Constituent;
        otc_validation_t Validation;
        otc_source_record SourceRecord;
        otc_set ConstantSet;
        otc_time_base_t TimeBase;
        otc_convention Convention;
        otc_licence Licence;
        otc_file_info FileInfo;
        otc_tombstone_t Tombstone;
        otc_astro_tab AstroTable;
    } value;
};

void otc__canonical_model_clear(otc_cp_typed_model *model)
{
    if (!model) return;
    if (model->native_owner) {
        canonical_index_owner_free(model->native_owner->json_storage);
        cJSON_Delete(model->native_owner->raw);
        free(model->native_owner);
    } else if (model->tag == OTC_CP_TYPED_MODEL_RELEASE) {
        otc_close((otc_release *)model->value.Release.value);
    } else if (model->tag == OTC_CP_TYPED_MODEL_STATION) {
        otc_station_free((otc_station_t *)model->value.Station.value);
    } else if (model->tag == OTC_CP_TYPED_MODEL_RELEASEINFO) {
        otc_release_info_free((otc_release_info *)model->value.ReleaseInfo.value);
    } else if (model->tag == OTC_CP_TYPED_MODEL_STATS) {
        otc_stats_free((otc_stats *)model->value.Stats.value);
    }
    memset(model, 0, sizeof *model);
}

static int canonical_prepared_evidence_matches(const cJSON *raw, const otc_time_base_evidence *evidence, size_t count)
{
    const cJSON *rows = otc__jget(raw, "evidence");
    size_t i, expected = cJSON_IsArray(rows) ? (size_t)cJSON_GetArraySize(rows) : 0;
    if (count != expected || (count && !evidence)) return 0;
    for (i = 0; i < count; i++) if (evidence[i].json != cJSON_GetArrayItem(rows, (int)i)) return 0;
    return 1;
}

static int canonical_prepared_source_matches(const otc_station_t *station, const cJSON *raw, int time_base)
{
    const cJSON *row;
    if (!station || !raw) return 0;
    /* Validate the already selected source's producing owner. This does not
     * select a set, resolve references, or construct dependency arrays. */
    cJSON_ArrayForEach(row, otc__jget(station->root, "constant_sets"))
        if ((time_base ? otc__jget(row, "time_base") : row) == raw) return 1;
    return 0;
}

static int canonical_prepared_set_matches(const otc_cp_prepared_constant_set_fields *prepared, const otc_release *release)
{
    const cJSON *raw, *rows;
    size_t i, j;
    int convention_owned = 0, licence_owned = 0;
    if (!prepared || !prepared->producing_station || prepared->producing_station->rel != release ||
        !canonical_prepared_source_matches(prepared->producing_station, prepared->source_set_raw, 0)) return 0;
    raw = prepared->source_set_raw;
    if (prepared->convention) {
        for (i = 0; i < release->n_conv; i++) if (prepared->convention == &release->conv[i]) convention_owned = 1;
        if (!convention_owned || !otc__jstr_same(otc__jstr_item(prepared->convention->json, "convention_id"), otc__jstr_item(raw, "convention_id"))) return 0;
    } else if (otc__jstr(raw, "convention_id")) return 0;
    if (prepared->licence) {
        for (i = 0; i < release->n_lic; i++) if (prepared->licence == &release->lic[i]) licence_owned = 1;
        if (!licence_owned || !otc__jstr_same(otc__jstr_item(prepared->licence->json, "licence_id"), otc__jstr_item(raw, "licence_id"))) return 0;
    } else if (otc__jstr(raw, "licence_id")) return 0;
    rows = otc__jget(raw, "constituents");
    if (prepared->constituent_count != (cJSON_IsArray(rows) ? (size_t)cJSON_GetArraySize(rows) : 0) ||
        (prepared->constituent_count && !prepared->constituents)) return 0;
    for (i = 0; i < prepared->constituent_count; i++) {
        otc_constituent_t expected;
        otc__fill_constituent(&expected, cJSON_GetArrayItem(rows, (int)i));
        if (memcmp(&expected, &prepared->constituents[i], sizeof expected)) return 0;
    }
    rows = otc__jget(raw, "qc_flags");
    if (prepared->qc_flag_count != (cJSON_IsArray(rows) ? (size_t)cJSON_GetArraySize(rows) : 0) || (prepared->qc_flag_count && !prepared->qc_flags)) return 0;
    for (i = 0; i < prepared->qc_flag_count; i++) if (prepared->qc_flags[i].json != cJSON_GetArrayItem(rows, (int)i)) return 0;
    rows = otc__jget(raw, "dropped_constituents");
    if (prepared->dropped_count != (cJSON_IsArray(rows) ? (size_t)cJSON_GetArraySize(rows) : 0) || (prepared->dropped_count && !prepared->dropped)) return 0;
    for (i = 0; i < prepared->dropped_count; i++) if (prepared->dropped[i].json != cJSON_GetArrayItem(rows, (int)i)) return 0;
    if (!canonical_prepared_evidence_matches(otc__jget(raw, "time_base"), prepared->time_base_evidence, prepared->time_base_evidence_count) ||
        (prepared->validation_count && !prepared->validation)) return 0;
    for (i = 0; i < prepared->validation_count; i++) {
        const otc_validation_t *value = prepared->validation[i];
        int owned = 0;
        for (j = 0; j < prepared->producing_station->n_val; j++) if (value == &prepared->producing_station->val[j]) owned = 1;
        if (!owned || !value->set_id || strcmp(value->set_id, otc__jstr(raw, "set_id")) ||
            (i && otc__strcmp_null(prepared->validation[i - 1]->window, value->window) > 0)) return 0;
    }
    return 1;
}

static int canonical_point_number_matches(const cJSON *raw, const char *name, double actual, int nullable)
{
    const cJSON *value = otc__jget(raw, name);
    return isfinite(actual) ? cJSON_IsNumber(value) && value->valuedouble == actual :
        nullable && (!value || cJSON_IsNull(value));
}

static int canonical_prepared_point_matches(const otc_cp_prepared_prediction_point_fields *prepared,
                                           const cJSON *raw, otc_cp_model_type_tag type)
{
    const cJSON *local_time = otc__jget(raw, "local_time"), *offset = otc__jget(raw, "utc_offset_s");
    const char *name;
    if (!prepared || prepared->model_type != type ||
        !canonical_point_number_matches(raw, "time", (double)prepared->time, 0) ||
        (local_time && !cJSON_IsNull(local_time)) || (offset && !cJSON_IsNull(offset))) return 0;
    switch (type) {
    case OTC_CP_MODEL_TYPE_HEIGHTPOINT:
        return canonical_point_number_matches(raw, "height_m", prepared->fields.height.height_m, 0);
    case OTC_CP_MODEL_TYPE_EXTREME:
        name = otc_extreme_type_name(prepared->fields.extreme.type);
        return name && otc__jstr(raw, "type") && otc__jstr_len(otc__jget(raw, "type")) == strlen(name) && !strcmp(name, otc__jstr(raw, "type")) &&
            canonical_point_number_matches(raw, "height_m", prepared->fields.extreme.height_m, 0);
    case OTC_CP_MODEL_TYPE_CURRENTPOINT:
        return canonical_point_number_matches(raw, "velocity_major_ms", prepared->fields.current.velocity_major_ms, 0) &&
            canonical_point_number_matches(raw, "velocity_minor_ms", prepared->fields.current.velocity_minor_ms, 0) &&
            canonical_point_number_matches(raw, "speed_ms", prepared->fields.current.speed_ms, 0) &&
            canonical_point_number_matches(raw, "direction_deg", prepared->fields.current.direction_deg, 1);
    case OTC_CP_MODEL_TYPE_CURRENTEVENT:
        name = otc_current_event_type_name(prepared->fields.event.type);
        return name && otc__jstr(raw, "type") && otc__jstr_len(otc__jget(raw, "type")) == strlen(name) && !strcmp(name, otc__jstr(raw, "type")) &&
            canonical_point_number_matches(raw, "velocity_ms", prepared->fields.event.velocity_ms, 0) &&
            canonical_point_number_matches(raw, "direction_deg", prepared->fields.event.direction_deg, 1);
    default: return 0;
    }
}

static int canonical_prepared_range_matches(const cJSON *raw, const char *key, double value)
{
    const cJSON *number = cJSON_GetObjectItemCaseSensitive(raw, key);
    return isnan(value) ? cJSON_IsNull(number) :
        (isfinite(value) && cJSON_IsNumber(number) && number->valuedouble == value);
}

static const char *const canonical_datum_flags[] = {"time_base_unverified", "time_base_disputed", "sampling_assumed", "truncated_lows", "gaps", "segment", "short_record", "no_qualified_control", "microtidal", "provisional"};

static int canonical_datum_string_matches(const cJSON *raw, const char *key, const char *value)
{
    const cJSON *field = cJSON_GetObjectItemCaseSensitive(raw, key);
    return value ? (cJSON_IsString(field) && !strcmp(field->valuestring, value)) : cJSON_IsNull(field);
}

static int canonical_datum_number_matches(const cJSON *raw, const char *key, bool present, double value)
{
    const cJSON *field = cJSON_GetObjectItemCaseSensitive(raw, key);
    return present ? (cJSON_IsNumber(field) && field->valuedouble == value) : cJSON_IsNull(field);
}

static int canonical_datum_level_matches(const cJSON *raw, const otc_datum_level *level)
{
    const cJSON *epoch, *span, *flags;
    size_t i, count = 0;
    if (!raw || !level || !level->key || !level->kind || !level->method ||
        !canonical_datum_string_matches(raw, "key", level->key) ||
        !canonical_datum_number_matches(raw, "value_m", true, level->value_m) ||
        !canonical_datum_number_matches(raw, "above_chart_m", level->has_above_chart, level->above_chart_m) ||
        !canonical_datum_string_matches(raw, "kind", level->kind) ||
        !canonical_datum_string_matches(raw, "method", level->method) ||
        !canonical_datum_string_matches(raw, "source_name", level->source_name) ||
        !canonical_datum_string_matches(raw, "control_station_id", level->control_station_id) ||
        !canonical_datum_string_matches(raw, "control_set_id", level->control_set_id) ||
        !canonical_datum_string_matches(raw, "control_source_id", level->control_source_id) ||
        !canonical_datum_number_matches(raw, "uncertainty_m", level->has_uncertainty, level->uncertainty_m) ||
        !canonical_datum_string_matches(raw, "uncertainty_basis", level->uncertainty_basis)) return 0;
    epoch = cJSON_GetObjectItemCaseSensitive(raw, "epoch");
    if (level->epoch_start || level->epoch_end || level->epoch_name) {
        if (!cJSON_IsObject(epoch) || !canonical_datum_string_matches(epoch, "start", level->epoch_start) ||
            !canonical_datum_string_matches(epoch, "end", level->epoch_end) ||
            !canonical_datum_string_matches(epoch, "name", level->epoch_name)) return 0;
    } else if (!cJSON_IsNull(epoch)) return 0;
    span = cJSON_GetObjectItemCaseSensitive(raw, "data_span");
    if (level->data_start || level->data_end || level->data_months >= 0) {
        if (!cJSON_IsObject(span) || !canonical_datum_string_matches(span, "start", level->data_start) ||
            !canonical_datum_string_matches(span, "end", level->data_end) ||
            !canonical_datum_number_matches(span, "months", level->data_months >= 0, (double)level->data_months)) return 0;
    } else if (!cJSON_IsNull(span)) return 0;
    flags = otc__jget(raw, "flags");
    if (!cJSON_IsArray(flags) || (level->flags & ~UINT32_C(1023))) return 0;
    for (i = 0; i < 10; i++) if (level->flags & (1u << i)) {
        const cJSON *flag = cJSON_GetArrayItem(flags, (int)count++);
        if (!cJSON_IsString(flag) || strcmp(flag->valuestring, canonical_datum_flags[i])) return 0;
    }
    return count == (size_t)cJSON_GetArraySize(flags);
}

static void canonical_datum_nullable_string(otc_cp_contract_string__nullable *out, const cJSON *raw, const char *key)
{
    out->value.value = otc__jstr(raw, key);
    out->presence = out->value.value ? OTC_CP_PRESENT_VALUE : OTC_CP_PRESENT_NULL;
}

static otc_status canonical_bind_datum_level(struct otc_cp_native_model_owner *owner, const cJSON *raw,
    const otc_datum_level *native, otc_cp_model_DatumLevel *out)
{
    const cJSON *epoch = otc__jget(raw, "epoch"), *span = otc__jget(raw, "data_span"), *flags = otc__jget(raw, "flags");
    otc_cp_contract_string_ *items;
    size_t i, count = (size_t)cJSON_GetArraySize(flags);
    otc_status status;
    out->key.value = otc__jstr(raw, "key"); out->value_m.value = native->value_m;
    out->above_chart_m.presence = native->has_above_chart ? OTC_CP_PRESENT_VALUE : OTC_CP_PRESENT_NULL;
    out->above_chart_m.value.value = native->above_chart_m;
    out->kind.value = otc__jstr(raw, "kind"); out->method.value = otc__jstr(raw, "method");
    canonical_datum_nullable_string(&out->source_name, raw, "source_name");
    canonical_datum_nullable_string(&out->control_station_id, raw, "control_station_id");
    canonical_datum_nullable_string(&out->control_set_id, raw, "control_set_id");
    canonical_datum_nullable_string(&out->control_source_id, raw, "control_source_id");
    canonical_datum_nullable_string(&out->uncertainty_basis, raw, "uncertainty_basis");
    out->uncertainty_m.presence = native->has_uncertainty ? OTC_CP_PRESENT_VALUE : OTC_CP_PRESENT_NULL;
    out->uncertainty_m.value.value = native->uncertainty_m;
    out->epoch.presence = epoch ? OTC_CP_PRESENT_VALUE : OTC_CP_PRESENT_NULL;
    if (epoch) { status = canonical_native_json(owner->json_storage, epoch, &out->epoch.value); if (status != OTC_OK) return status; }
    out->data_span.presence = span ? OTC_CP_PRESENT_VALUE : OTC_CP_PRESENT_NULL;
    if (span) { status = canonical_native_json(owner->json_storage, span, &out->data_span.value); if (status != OTC_OK) return status; }
    items = canonical_index_alloc(owner->json_storage, count, sizeof *items);
    if (!items) return OTC_E_NOMEM;
    for (i = 0; i < count; i++) items[i].value = cJSON_GetArrayItem(flags, (int)i)->valuestring;
    out->flags.items = items; out->flags.count = count;
    return OTC_OK;
}

static int canonical_prepared_datums_match(const otc_cp_prepared_datum_fields *prepared,
    const otc_release *release, const cJSON *raw, otc_cp_model_type_tag type)
{
    const cJSON *levels;
    size_t i;
    if (!prepared || prepared->model_type != type || !prepared->producing_station ||
        prepared->producing_station->rel != release || !prepared->source_raw ||
        !cJSON_Compare(raw, prepared->source_raw, 1) || (prepared->level_count && !prepared->levels)) return 0;
    if (type == OTC_CP_MODEL_TYPE_DATUMLEVEL)
        return prepared->level_count == 1 && canonical_datum_level_matches(raw, prepared->levels);
    if (!canonical_datum_string_matches(raw, "set_id", prepared->info.set_id) ||
        !canonical_datum_string_matches(raw, "zero", prepared->info.zero) ||
        !canonical_datum_string_matches(raw, "zero_name", prepared->info.zero_name) ||
        !canonical_datum_string_matches(raw, "chart_datum", prepared->info.chart_datum) ||
        !canonical_datum_number_matches(raw, "msl_offset_m", prepared->info.has_msl_offset, prepared->info.msl_offset_m)) return 0;
    levels = otc__jget(raw, "levels");
    if (!cJSON_IsArray(levels) || prepared->level_count != (size_t)cJSON_GetArraySize(levels)) return 0;
    for (i = 0; i < prepared->level_count; i++)
        if (!canonical_datum_level_matches(cJSON_GetArrayItem(levels, (int)i), &prepared->levels[i])) return 0;
    return 1;
}

static int canonical_provenance_json_matches(const cJSON *raw, const char *key, const cJSON *prepared)
{
    const cJSON *field = otc__jget(raw, key);
    return prepared ? cJSON_Compare(field, prepared, 1) : !field;
}

static int canonical_offsets_number_matches(const cJSON *raw, const char *key, double value)
{
    double supplied = otc__jnum(raw, key);
    return isnan(value) ? isnan(supplied) : supplied == value;
}

static int canonical_prepared_offsets_match(const otc_cp_prepared_offsets_fields *prepared,
    const otc_release *release, const cJSON *raw)
{
    const otc_offsets_t *fields;
    const cJSON *flags;
    size_t i, count;
    if (!prepared || !prepared->producing_station || prepared->producing_station->rel != release ||
        prepared->source_raw != otc__jget(prepared->producing_station->root, "subordinate_offsets") ||
        !cJSON_Compare(raw, prepared->source_raw, 1)) return 0;
    fields = &prepared->fields;
    if (fields->struct_size < sizeof *fields || !fields->reference_station_id ||
        otc__strcmp_null(otc__jstr(raw, "reference_station_id"), fields->reference_station_id) ||
        otc__strcmp_null(otc__jstr(raw, "licence_id"), fields->licence_id) ||
        otc__strcmp_null(otc__jstr(raw, "offset_id"), fields->offset_id) ||
        otc__strcmp_null(otc__jstr(raw, "source"), fields->source) ||
        otc__strcmp_null(otc__jstr(raw, "source_version"), fields->source_version) ||
        otc__strcmp_null(otc__jstr(raw, "source_record_id"), fields->source_record_id) ||
        !canonical_offsets_number_matches(raw, "time_offset_high_min", fields->time_offset_high_min) ||
        !canonical_offsets_number_matches(raw, "time_offset_low_min", fields->time_offset_low_min) ||
        !canonical_offsets_number_matches(raw, "height_offset_high", fields->height_offset_high) ||
        !canonical_offsets_number_matches(raw, "height_offset_low", fields->height_offset_low) ||
        otc__parse_height_adjusted_type(otc__jstr(raw, "height_adjusted_type")) != fields->height_adjusted_type ||
        otc__parse_source_type(otc__jstr(raw, "source_type")) != fields->source_type ||
        otc__parse_qc_status(otc__jstr(raw, "qc_status")) != fields->qc_status) return 0;
    flags = otc__jget(prepared->source_raw, "qc_flags");
    count = cJSON_IsArray(flags) ? (size_t)cJSON_GetArraySize(flags) : 0;
    if (count != fields->qc_flags_count || (count && !fields->qc_flags)) return 0;
    for (i = 0; i < count; i++) if (fields->qc_flags[i].json != cJSON_GetArrayItem(flags, (int)i)) return 0;
    return (fields->fallback ? fields->fallback->json : NULL) == otc__jget(prepared->source_raw, "fallback") &&
        (fields->vintage ? fields->vintage->json : NULL) == otc__jget(prepared->source_raw, "vintage") &&
        (fields->provenance ? fields->provenance->json : NULL) == otc__jget(prepared->source_raw, "provenance");
}

static otc_cp_contract_enum_height_adjusted_type_tag canonical_offsets_height_type(otc_height_adjusted_type value)
{
    switch (value) {
    case OTC_HEIGHT_ADJUSTED_TYPE_R: return OTC_CP_CONTRACT_ENUM_HEIGHT_ADJUSTED_TYPE_R;
    case OTC_HEIGHT_ADJUSTED_TYPE_A: return OTC_CP_CONTRACT_ENUM_HEIGHT_ADJUSTED_TYPE_A;
    case OTC_HEIGHT_ADJUSTED_TYPE_OTHER: return OTC_CP_CONTRACT_ENUM_HEIGHT_ADJUSTED_TYPE_OTHER;
    default: return OTC_CP_CONTRACT_ENUM_HEIGHT_ADJUSTED_TYPE_UNSET;
    }
}

static otc_cp_contract_enum_source_type_tag canonical_offsets_source_type(otc_source_type value)
{
    switch (value) {
    case OTC_SOURCE_TYPE_OFFICIAL: return OTC_CP_CONTRACT_ENUM_SOURCE_TYPE_OFFICIAL;
    case OTC_SOURCE_TYPE_GAUGE: return OTC_CP_CONTRACT_ENUM_SOURCE_TYPE_GAUGE;
    case OTC_SOURCE_TYPE_MODEL: return OTC_CP_CONTRACT_ENUM_SOURCE_TYPE_MODEL;
    case OTC_SOURCE_TYPE_OTHER: return OTC_CP_CONTRACT_ENUM_SOURCE_TYPE_OTHER;
    default: return OTC_CP_CONTRACT_ENUM_SOURCE_TYPE_UNSET;
    }
}

static otc_cp_contract_enum_qc_status_tag canonical_offsets_qc_status(otc_qc_status value)
{
    switch (value) {
    case OTC_QC_STATUS_OK: return OTC_CP_CONTRACT_ENUM_QC_STATUS_OK;
    case OTC_QC_STATUS_FLAGGED: return OTC_CP_CONTRACT_ENUM_QC_STATUS_FLAGGED;
    case OTC_QC_STATUS_NO_CONSTANTS: return OTC_CP_CONTRACT_ENUM_QC_STATUS_NO_CONSTANTS;
    case OTC_QC_STATUS_OTHER: return OTC_CP_CONTRACT_ENUM_QC_STATUS_OTHER;
    default: return OTC_CP_CONTRACT_ENUM_QC_STATUS_UNSET;
    }
}

static void canonical_offsets_number(otc_cp_contract_number__nullable *out, double value)
{
    out->presence = isnan(value) ? OTC_CP_PRESENT_NULL : OTC_CP_PRESENT_VALUE;
    out->value.value = value;
}

static otc_status canonical_container_string(struct otc_cp_native_model_owner *owner, const char *source, const char **out)
{
    size_t length;
    char *copy;
    *out = NULL;
    if (!source) return OTC_OK;
    length = strlen(source);
    if (length == SIZE_MAX) return OTC_E_NOMEM;
    copy = canonical_index_alloc(owner->json_storage, length + 1, 1);
    if (!copy) return OTC_E_NOMEM;
    memcpy(copy, source, length + 1); *out = copy;
    return OTC_OK;
}

static otc_status canonical_container_nullable_string(struct otc_cp_native_model_owner *owner,
    const char *source, otc_cp_contract_string__nullable *out)
{
    out->presence = source ? OTC_CP_PRESENT_VALUE : OTC_CP_PRESENT_NULL;
    return canonical_container_string(owner, source, &out->value.value);
}

static otc_cp_contract_enum_prediction_method_tag canonical_container_method(otc_prediction_method value)
{
    switch (value) {
    case OTC_PREDICTION_METHOD_HARMONIC: return OTC_CP_CONTRACT_ENUM_PREDICTION_METHOD_HARMONIC;
    case OTC_PREDICTION_METHOD_FOLDED_OFFSETS: return OTC_CP_CONTRACT_ENUM_PREDICTION_METHOD_FOLDED_OFFSETS;
    case OTC_PREDICTION_METHOD_OFFSETS: return OTC_CP_CONTRACT_ENUM_PREDICTION_METHOD_OFFSETS;
    case OTC_PREDICTION_METHOD_OTHER: return OTC_CP_CONTRACT_ENUM_PREDICTION_METHOD_OTHER;
    default: return OTC_CP_CONTRACT_ENUM_PREDICTION_METHOD_UNSET;
    }
}

static otc_cp_contract_enum_extreme_type_tag canonical_container_extreme_type(otc_extreme_type_t value)
{
    switch (value) {
    case OTC_EXTREME_TYPE_HIGH: return OTC_CP_CONTRACT_ENUM_EXTREME_TYPE_HIGH;
    case OTC_EXTREME_TYPE_LOW: return OTC_CP_CONTRACT_ENUM_EXTREME_TYPE_LOW;
    case OTC_EXTREME_TYPE_OTHER: return OTC_CP_CONTRACT_ENUM_EXTREME_TYPE_OTHER;
    default: return OTC_CP_CONTRACT_ENUM_EXTREME_TYPE_UNSET;
    }
}

static otc_cp_contract_enum_current_event_type_tag canonical_container_current_type(otc_current_event_type_t value)
{
    switch (value) {
    case OTC_CURRENT_EVENT_TYPE_MAX_FLOOD: return OTC_CP_CONTRACT_ENUM_CURRENT_EVENT_TYPE_MAX_FLOOD;
    case OTC_CURRENT_EVENT_TYPE_MAX_EBB: return OTC_CP_CONTRACT_ENUM_CURRENT_EVENT_TYPE_MAX_EBB;
    case OTC_CURRENT_EVENT_TYPE_SLACK_BEFORE_FLOOD: return OTC_CP_CONTRACT_ENUM_CURRENT_EVENT_TYPE_SLACK_BEFORE_FLOOD;
    case OTC_CURRENT_EVENT_TYPE_SLACK_BEFORE_EBB: return OTC_CP_CONTRACT_ENUM_CURRENT_EVENT_TYPE_SLACK_BEFORE_EBB;
    case OTC_CURRENT_EVENT_TYPE_OTHER: return OTC_CP_CONTRACT_ENUM_CURRENT_EVENT_TYPE_OTHER;
    default: return OTC_CP_CONTRACT_ENUM_CURRENT_EVENT_TYPE_UNSET;
    }
}

static otc_status canonical_materialize_prediction_container(const otc_cp_raw_fields *raw_fields,
    const otc_cp_origin *origin, otc_cp_model_type_tag type, otc_cp_typed_model *out)
{
    const otc_cp_prepared_prediction_container_fields *prepared = origin->prepared_prediction_container;
    const otc_prediction_info *info;
    struct otc_cp_native_model_owner *owner;
    const void *source_items;
    otc_status status = OTC_OK;
    size_t i;
    if (!raw_fields || raw_fields->tag != OTC_CP_JSON_OBJECT || raw_fields->value.members.count ||
        !prepared || prepared->model_type.value != type || !prepared->info ||
        prepared->info->struct_size < sizeof *prepared->info ||
        (prepared->local.present && (prepared->local.count != prepared->count ||
         (prepared->count && !prepared->local.items) || !prepared->local.zone ||
         (prepared->local.has_version && !prepared->local.version)))) return OTC_E_INVALID_ARGUMENT;
    switch (type) {
    case OTC_CP_MODEL_TYPE_HEIGHTSERIES: source_items = prepared->items.heights; break;
    case OTC_CP_MODEL_TYPE_EXTREMELIST: source_items = prepared->items.extremes; break;
    case OTC_CP_MODEL_TYPE_CURRENTSERIES: source_items = prepared->items.currents; break;
    case OTC_CP_MODEL_TYPE_CURRENTEVENTLIST: source_items = prepared->items.current_events; break;
    default: return OTC_E_NOT_BUILT;
    }
    if (prepared->count && !source_items) return OTC_E_INVALID_ARGUMENT;
    owner = calloc(1, sizeof *owner);
    if (!owner) return OTC_E_NOMEM;
    owner->json_storage = calloc(1, sizeof *owner->json_storage);
    if (!owner->json_storage) { free(owner); return OTC_E_NOMEM; }
    info = prepared->info;
    memset(out, 0, sizeof *out);
    switch (type) {
    case OTC_CP_MODEL_TYPE_HEIGHTSERIES: {
        otc_cp_model_HeightSeries *projected = &out->value.HeightSeries;
        otc_cp_model_HeightPoint *items = canonical_index_alloc(owner->json_storage, prepared->count, sizeof *items);
        const otc_height_t *native = prepared->items.heights;
        if (!items) { status = OTC_E_NOMEM; goto container_failure; }
        out->tag = OTC_CP_TYPED_MODEL_HEIGHTSERIES;
        projected->items.items = items; projected->items.count = prepared->count;
        for (i = 0; i < prepared->count; i++) {
            items[i].time.value = native[i].t;
            items[i].height_m.value = native[i].height_m;
    if (prepared->local.present && prepared->local.items[i].t != native[i].t) { status = OTC_E_INVALID_ARGUMENT; goto container_failure; }
    status = canonical_container_nullable_string(owner, prepared->local.present ? prepared->local.items[i].local_time : NULL, &items[i].local_time);
    if (status != OTC_OK) goto container_failure;
    items[i].utc_offset_s.presence = prepared->local.present ? OTC_CP_PRESENT_VALUE : OTC_CP_PRESENT_NULL;
    if (prepared->local.present) items[i].utc_offset_s.value.value = prepared->local.items[i].utc_offset_s;
}
        status = canonical_container_string(owner, info->station_id, &projected->station_id.value); if (status != OTC_OK) goto container_failure;
        status = canonical_container_string(owner, info->timezone, &projected->timezone.value); if (status != OTC_OK) goto container_failure;
        status = canonical_container_string(owner, info->set_id, &projected->set_id.value); if (status != OTC_OK) goto container_failure;
        status = canonical_container_string(owner, info->convention_id, &projected->convention_id.value); if (status != OTC_OK) goto container_failure;
        status = canonical_container_string(owner, info->astro_table_id, &projected->astro_table_id.value); if (status != OTC_OK) goto container_failure;
        status = canonical_container_string(owner, info->release, &projected->release.value); if (status != OTC_OK) goto container_failure;
        status = canonical_container_string(owner, info->algorithm, &projected->algorithm.value); if (status != OTC_OK) goto container_failure;
        status = canonical_container_nullable_string(owner, info->reference_station_id, &projected->reference_station_id); if (status != OTC_OK) goto container_failure;
        status = canonical_container_nullable_string(owner, info->datum, &projected->datum); if (status != OTC_OK) goto container_failure;
        status = canonical_container_nullable_string(owner, info->datum_name, &projected->datum_name); if (status != OTC_OK) goto container_failure;
        status = canonical_container_nullable_string(owner, info->datum_kind, &projected->datum_kind); if (status != OTC_OK) goto container_failure;
projected->method.value = canonical_container_method(info->method);
projected->reference_bin.presence = info->reference_bin ? OTC_CP_PRESENT_VALUE : OTC_CP_PRESENT_NULL;
projected->reference_bin.value.value = info->reference_bin;
canonical_offsets_number(&projected->datum_uncertainty_m, info->datum_uncertainty_m);
status = canonical_container_nullable_string(owner, prepared->local.present ? prepared->local.zone : NULL, &projected->tz); if (status != OTC_OK) goto container_failure;
status = canonical_container_nullable_string(owner, prepared->local.present && prepared->local.has_version ? prepared->local.version : NULL, &projected->tz_version); if (status != OTC_OK) goto container_failure;
        status = canonical_container_nullable_string(owner, info->offset_id, &projected->offset_id); if (status != OTC_OK) goto container_failure;
        status = canonical_container_nullable_string(owner, info->offset_source, &projected->offset_source); if (status != OTC_OK) goto container_failure;
        status = canonical_container_nullable_string(owner, info->offset_source_version, &projected->offset_source_version); if (status != OTC_OK) goto container_failure;
        status = canonical_container_nullable_string(owner, info->current_validity, &projected->current_validity); if (status != OTC_OK) goto container_failure;
        status = canonical_container_nullable_string(owner, info->current_accuracy, &projected->current_accuracy); if (status != OTC_OK) goto container_failure;
        status = canonical_container_nullable_string(owner, info->reference_set_id, &projected->reference_set_id); if (status != OTC_OK) goto container_failure;
        status = canonical_container_nullable_string(owner, info->reference_source_version, &projected->reference_source_version); if (status != OTC_OK) goto container_failure;
        status = canonical_container_nullable_string(owner, info->reference_2020_equivalence, &projected->reference_2020_equivalence); if (status != OTC_OK) goto container_failure;
        status = canonical_container_nullable_string(owner, info->source_note, &projected->source_note); if (status != OTC_OK) goto container_failure;
        projected->historical_offsets.value = info->historical_offsets;
        break;
    }
    case OTC_CP_MODEL_TYPE_EXTREMELIST: {
        otc_cp_model_ExtremeList *projected = &out->value.ExtremeList;
        otc_cp_model_Extreme *items = canonical_index_alloc(owner->json_storage, prepared->count, sizeof *items);
        const otc_extreme_t *native = prepared->items.extremes;
        if (!items) { status = OTC_E_NOMEM; goto container_failure; }
        out->tag = OTC_CP_TYPED_MODEL_EXTREMELIST;
        projected->items.items = items; projected->items.count = prepared->count;
        for (i = 0; i < prepared->count; i++) {
            items[i].time.value = native[i].t;
            items[i].height_m.value = native[i].height_m;
            items[i].type.value = canonical_container_extreme_type(native[i].type);
    if (prepared->local.present && prepared->local.items[i].t != native[i].t) { status = OTC_E_INVALID_ARGUMENT; goto container_failure; }
    status = canonical_container_nullable_string(owner, prepared->local.present ? prepared->local.items[i].local_time : NULL, &items[i].local_time);
    if (status != OTC_OK) goto container_failure;
    items[i].utc_offset_s.presence = prepared->local.present ? OTC_CP_PRESENT_VALUE : OTC_CP_PRESENT_NULL;
    if (prepared->local.present) items[i].utc_offset_s.value.value = prepared->local.items[i].utc_offset_s;
}
        status = canonical_container_string(owner, info->station_id, &projected->station_id.value); if (status != OTC_OK) goto container_failure;
        status = canonical_container_string(owner, info->timezone, &projected->timezone.value); if (status != OTC_OK) goto container_failure;
        status = canonical_container_string(owner, info->set_id, &projected->set_id.value); if (status != OTC_OK) goto container_failure;
        status = canonical_container_string(owner, info->convention_id, &projected->convention_id.value); if (status != OTC_OK) goto container_failure;
        status = canonical_container_string(owner, info->astro_table_id, &projected->astro_table_id.value); if (status != OTC_OK) goto container_failure;
        status = canonical_container_string(owner, info->release, &projected->release.value); if (status != OTC_OK) goto container_failure;
        status = canonical_container_string(owner, info->algorithm, &projected->algorithm.value); if (status != OTC_OK) goto container_failure;
        status = canonical_container_nullable_string(owner, info->reference_station_id, &projected->reference_station_id); if (status != OTC_OK) goto container_failure;
        status = canonical_container_nullable_string(owner, info->datum, &projected->datum); if (status != OTC_OK) goto container_failure;
        status = canonical_container_nullable_string(owner, info->datum_name, &projected->datum_name); if (status != OTC_OK) goto container_failure;
        status = canonical_container_nullable_string(owner, info->datum_kind, &projected->datum_kind); if (status != OTC_OK) goto container_failure;
projected->method.value = canonical_container_method(info->method);
projected->reference_bin.presence = info->reference_bin ? OTC_CP_PRESENT_VALUE : OTC_CP_PRESENT_NULL;
projected->reference_bin.value.value = info->reference_bin;
canonical_offsets_number(&projected->datum_uncertainty_m, info->datum_uncertainty_m);
status = canonical_container_nullable_string(owner, prepared->local.present ? prepared->local.zone : NULL, &projected->tz); if (status != OTC_OK) goto container_failure;
status = canonical_container_nullable_string(owner, prepared->local.present && prepared->local.has_version ? prepared->local.version : NULL, &projected->tz_version); if (status != OTC_OK) goto container_failure;
        status = canonical_container_nullable_string(owner, info->offset_id, &projected->offset_id); if (status != OTC_OK) goto container_failure;
        status = canonical_container_nullable_string(owner, info->offset_source, &projected->offset_source); if (status != OTC_OK) goto container_failure;
        status = canonical_container_nullable_string(owner, info->offset_source_version, &projected->offset_source_version); if (status != OTC_OK) goto container_failure;
        status = canonical_container_nullable_string(owner, info->current_validity, &projected->current_validity); if (status != OTC_OK) goto container_failure;
        status = canonical_container_nullable_string(owner, info->current_accuracy, &projected->current_accuracy); if (status != OTC_OK) goto container_failure;
        status = canonical_container_nullable_string(owner, info->reference_set_id, &projected->reference_set_id); if (status != OTC_OK) goto container_failure;
        status = canonical_container_nullable_string(owner, info->reference_source_version, &projected->reference_source_version); if (status != OTC_OK) goto container_failure;
        status = canonical_container_nullable_string(owner, info->reference_2020_equivalence, &projected->reference_2020_equivalence); if (status != OTC_OK) goto container_failure;
        status = canonical_container_nullable_string(owner, info->source_note, &projected->source_note); if (status != OTC_OK) goto container_failure;
        projected->historical_offsets.value = info->historical_offsets;
        break;
    }
    case OTC_CP_MODEL_TYPE_CURRENTSERIES: {
        otc_cp_model_CurrentSeries *projected = &out->value.CurrentSeries;
        otc_cp_model_CurrentPoint *items = canonical_index_alloc(owner->json_storage, prepared->count, sizeof *items);
        const otc_current_t *native = prepared->items.currents;
        if (!items) { status = OTC_E_NOMEM; goto container_failure; }
        out->tag = OTC_CP_TYPED_MODEL_CURRENTSERIES;
        projected->items.items = items; projected->items.count = prepared->count;
        for (i = 0; i < prepared->count; i++) {
            items[i].time.value = native[i].t;
            items[i].velocity_major_ms.value = native[i].velocity_major_ms;
            items[i].velocity_minor_ms.value = native[i].velocity_minor_ms;
            items[i].speed_ms.value = native[i].speed_ms;
            canonical_offsets_number(&items[i].direction_deg, native[i].direction_deg);
    if (prepared->local.present && prepared->local.items[i].t != native[i].t) { status = OTC_E_INVALID_ARGUMENT; goto container_failure; }
    status = canonical_container_nullable_string(owner, prepared->local.present ? prepared->local.items[i].local_time : NULL, &items[i].local_time);
    if (status != OTC_OK) goto container_failure;
    items[i].utc_offset_s.presence = prepared->local.present ? OTC_CP_PRESENT_VALUE : OTC_CP_PRESENT_NULL;
    if (prepared->local.present) items[i].utc_offset_s.value.value = prepared->local.items[i].utc_offset_s;
}
        status = canonical_container_string(owner, info->station_id, &projected->station_id.value); if (status != OTC_OK) goto container_failure;
        status = canonical_container_string(owner, info->timezone, &projected->timezone.value); if (status != OTC_OK) goto container_failure;
        status = canonical_container_string(owner, info->set_id, &projected->set_id.value); if (status != OTC_OK) goto container_failure;
        status = canonical_container_string(owner, info->convention_id, &projected->convention_id.value); if (status != OTC_OK) goto container_failure;
        status = canonical_container_string(owner, info->astro_table_id, &projected->astro_table_id.value); if (status != OTC_OK) goto container_failure;
        status = canonical_container_string(owner, info->release, &projected->release.value); if (status != OTC_OK) goto container_failure;
        status = canonical_container_string(owner, info->algorithm, &projected->algorithm.value); if (status != OTC_OK) goto container_failure;
        status = canonical_container_nullable_string(owner, info->reference_station_id, &projected->reference_station_id); if (status != OTC_OK) goto container_failure;
        status = canonical_container_nullable_string(owner, info->datum, &projected->datum); if (status != OTC_OK) goto container_failure;
        status = canonical_container_nullable_string(owner, info->datum_name, &projected->datum_name); if (status != OTC_OK) goto container_failure;
        status = canonical_container_nullable_string(owner, info->datum_kind, &projected->datum_kind); if (status != OTC_OK) goto container_failure;
projected->method.value = canonical_container_method(info->method);
projected->reference_bin.presence = info->reference_bin ? OTC_CP_PRESENT_VALUE : OTC_CP_PRESENT_NULL;
projected->reference_bin.value.value = info->reference_bin;
canonical_offsets_number(&projected->datum_uncertainty_m, info->datum_uncertainty_m);
status = canonical_container_nullable_string(owner, prepared->local.present ? prepared->local.zone : NULL, &projected->tz); if (status != OTC_OK) goto container_failure;
status = canonical_container_nullable_string(owner, prepared->local.present && prepared->local.has_version ? prepared->local.version : NULL, &projected->tz_version); if (status != OTC_OK) goto container_failure;
        projected->bin_number.value = info->bin_number;
        break;
    }
    case OTC_CP_MODEL_TYPE_CURRENTEVENTLIST: {
        otc_cp_model_CurrentEventList *projected = &out->value.CurrentEventList;
        otc_cp_model_CurrentEvent *items = canonical_index_alloc(owner->json_storage, prepared->count, sizeof *items);
        const otc_current_event_t *native = prepared->items.current_events;
        if (!items) { status = OTC_E_NOMEM; goto container_failure; }
        out->tag = OTC_CP_TYPED_MODEL_CURRENTEVENTLIST;
        projected->items.items = items; projected->items.count = prepared->count;
        for (i = 0; i < prepared->count; i++) {
            items[i].time.value = native[i].t;
            items[i].velocity_ms.value = native[i].velocity_ms;
            items[i].type.value = canonical_container_current_type(native[i].type);
            canonical_offsets_number(&items[i].direction_deg, native[i].direction_deg);
    if (prepared->local.present && prepared->local.items[i].t != native[i].t) { status = OTC_E_INVALID_ARGUMENT; goto container_failure; }
    status = canonical_container_nullable_string(owner, prepared->local.present ? prepared->local.items[i].local_time : NULL, &items[i].local_time);
    if (status != OTC_OK) goto container_failure;
    items[i].utc_offset_s.presence = prepared->local.present ? OTC_CP_PRESENT_VALUE : OTC_CP_PRESENT_NULL;
    if (prepared->local.present) items[i].utc_offset_s.value.value = prepared->local.items[i].utc_offset_s;
}
        status = canonical_container_string(owner, info->station_id, &projected->station_id.value); if (status != OTC_OK) goto container_failure;
        status = canonical_container_string(owner, info->timezone, &projected->timezone.value); if (status != OTC_OK) goto container_failure;
        status = canonical_container_string(owner, info->set_id, &projected->set_id.value); if (status != OTC_OK) goto container_failure;
        status = canonical_container_string(owner, info->convention_id, &projected->convention_id.value); if (status != OTC_OK) goto container_failure;
        status = canonical_container_string(owner, info->astro_table_id, &projected->astro_table_id.value); if (status != OTC_OK) goto container_failure;
        status = canonical_container_string(owner, info->release, &projected->release.value); if (status != OTC_OK) goto container_failure;
        status = canonical_container_string(owner, info->algorithm, &projected->algorithm.value); if (status != OTC_OK) goto container_failure;
        status = canonical_container_nullable_string(owner, info->reference_station_id, &projected->reference_station_id); if (status != OTC_OK) goto container_failure;
        status = canonical_container_nullable_string(owner, info->datum, &projected->datum); if (status != OTC_OK) goto container_failure;
        status = canonical_container_nullable_string(owner, info->datum_name, &projected->datum_name); if (status != OTC_OK) goto container_failure;
        status = canonical_container_nullable_string(owner, info->datum_kind, &projected->datum_kind); if (status != OTC_OK) goto container_failure;
projected->method.value = canonical_container_method(info->method);
projected->reference_bin.presence = info->reference_bin ? OTC_CP_PRESENT_VALUE : OTC_CP_PRESENT_NULL;
projected->reference_bin.value.value = info->reference_bin;
canonical_offsets_number(&projected->datum_uncertainty_m, info->datum_uncertainty_m);
status = canonical_container_nullable_string(owner, prepared->local.present ? prepared->local.zone : NULL, &projected->tz); if (status != OTC_OK) goto container_failure;
status = canonical_container_nullable_string(owner, prepared->local.present && prepared->local.has_version ? prepared->local.version : NULL, &projected->tz_version); if (status != OTC_OK) goto container_failure;
        projected->bin_number.value = info->bin_number;
projected->omitted_event_types.presence = info->has_omitted_event_types ? OTC_CP_PRESENT_VALUE : OTC_CP_PRESENT_NULL;
if (info->has_omitted_event_types) {
    otc_cp_contract_enum_current_event_type *types = canonical_index_alloc(owner->json_storage, (size_t)OTC_CURRENT_EVENT_TYPE_OTHER + 1, sizeof *types);
    size_t count = 0, bit;
    if (!types) { status = OTC_E_NOMEM; goto container_failure; }
    for (bit = 0; bit <= OTC_CURRENT_EVENT_TYPE_OTHER; bit++) if (info->omitted_event_types & (UINT32_C(1) << bit))
        types[count++].value = canonical_container_current_type((otc_current_event_type_t)bit);
    projected->omitted_event_types.value.items = types; projected->omitted_event_types.value.count = count;
}
        break;
    }
    default: status = OTC_E_NOT_BUILT; goto container_failure;
    }
    out->native_owner = owner;
    return OTC_OK;
container_failure:
    canonical_index_owner_free(owner->json_storage); free(owner); memset(out, 0, sizeof *out);
    return status;
}

static otc_status canonical_materialize_json_view(const otc_cp_raw_fields *raw_fields,
    otc_cp_model_type_tag type, const otc_cp_origin *origin, otc_cp_typed_model *out)
{
    struct otc_cp_native_model_owner *owner;
    switch (type) {
    case OTC_CP_MODEL_TYPE_RECORDSPAN: case OTC_CP_MODEL_TYPE_DATUM:
    case OTC_CP_MODEL_TYPE_DROPPEDCONSTITUENT: case OTC_CP_MODEL_TYPE_QCFLAG:
    case OTC_CP_MODEL_TYPE_PROVENANCEBUILD: case OTC_CP_MODEL_TYPE_FALLBACK:
    case OTC_CP_MODEL_TYPE_HISTORICALOFFSETVINTAGE: case OTC_CP_MODEL_TYPE_HISTORICALOFFSETPROVENANCE:
    case OTC_CP_MODEL_TYPE_CONSTITUENT: case OTC_CP_MODEL_TYPE_VALIDATION:
    case OTC_CP_MODEL_TYPE_SOURCERECORD:
    case OTC_CP_MODEL_TYPE_CONSTANTSET: case OTC_CP_MODEL_TYPE_TIMEBASE:
    case OTC_CP_MODEL_TYPE_CONVENTION: case OTC_CP_MODEL_TYPE_LICENCE:
    case OTC_CP_MODEL_TYPE_FILEINFO:
    case OTC_CP_MODEL_TYPE_TOMBSTONE: case OTC_CP_MODEL_TYPE_NEARBY:
    case OTC_CP_MODEL_TYPE_RANGES:
    case OTC_CP_MODEL_TYPE_DATUMINFO: case OTC_CP_MODEL_TYPE_DATUMLEVEL:
    case OTC_CP_MODEL_TYPE_PROVENANCE:     case OTC_CP_MODEL_TYPE_ASTROTABLE:
    case OTC_CP_MODEL_TYPE_SUBORDINATEOFFSETS:
    case OTC_CP_MODEL_TYPE_HEIGHTPOINT: case OTC_CP_MODEL_TYPE_EXTREME:
    case OTC_CP_MODEL_TYPE_CURRENTPOINT: case OTC_CP_MODEL_TYPE_CURRENTEVENT:
        break;
    default: return OTC_E_NOT_BUILT;
    }
    owner = calloc(1, sizeof *owner);
    if (!owner) return OTC_E_NOMEM;
    owner->raw = canonical_source_json(raw_fields);
    if (!owner->raw || !cJSON_IsObject(owner->raw)) {
        cJSON_Delete(owner->raw); free(owner); return OTC_E_INVALID_ARGUMENT;
    }
if (type == OTC_CP_MODEL_TYPE_SUBORDINATEOFFSETS &&
    !canonical_prepared_offsets_match(origin->prepared_offsets, origin->producing_release, owner->raw)) {
    cJSON_Delete(owner->raw); free(owner); return OTC_E_INVALID_ARGUMENT;
}
if (type == OTC_CP_MODEL_TYPE_ASTROTABLE) {
    const otc_cp_prepared_astro_fields *prepared = origin->prepared_astro;
    if (!prepared || !prepared->source_raw || !cJSON_Compare(owner->raw, prepared->source_raw, 1) ||
        otc__jnum(owner->raw, "first_year") != prepared->first_year ||
        otc__jnum(owner->raw, "last_year") != prepared->last_year) {
        cJSON_Delete(owner->raw); free(owner); return OTC_E_INVALID_ARGUMENT;
    }
} else if (type == OTC_CP_MODEL_TYPE_PROVENANCE) {
    const otc_cp_prepared_provenance_fields *prepared = origin->prepared_provenance;
    if (!prepared || !prepared->producing_station || prepared->producing_station->rel != origin->producing_release ||
        !prepared->source_raw || !cJSON_Compare(owner->raw, prepared->source_raw, 1) ||
        otc__strcmp_null(otc__jstr(owner->raw, "adapter_version"), prepared->adapter_version) ||
        otc__strcmp_null(otc__jstr(owner->raw, "selection_reason"), prepared->selection_reason) ||
        otc__strcmp_null(otc__jstr(owner->raw, "carried_from_release"), prepared->carried_from_release) ||
        !canonical_provenance_json_matches(owner->raw, "input_sha256", prepared->input_sha256) ||
        !canonical_provenance_json_matches(owner->raw, "decision", prepared->decision) ||
        !canonical_provenance_json_matches(owner->raw, "build", prepared->build) ||
        (prepared->input_sha256 && !cJSON_IsArray(prepared->input_sha256)) ||
        (prepared->decision && !cJSON_IsObject(prepared->decision)) ||
        (prepared->build && !cJSON_IsObject(prepared->build))) {
        cJSON_Delete(owner->raw); free(owner); return OTC_E_INVALID_ARGUMENT;
    }
}
if ((type == OTC_CP_MODEL_TYPE_DATUMINFO || type == OTC_CP_MODEL_TYPE_DATUMLEVEL) &&
    !canonical_prepared_datums_match(origin->prepared_datum, origin->producing_release, owner->raw, type)) {
    cJSON_Delete(owner->raw); free(owner); return OTC_E_INVALID_ARGUMENT;
}
if (type == OTC_CP_MODEL_TYPE_TOMBSTONE || type == OTC_CP_MODEL_TYPE_NEARBY || type == OTC_CP_MODEL_TYPE_RANGES) {
    const otc_cp_prepared_value_fields *prepared = origin->prepared_value;
    if (!prepared || prepared->model_type != type || !prepared->source_raw ||
        !cJSON_Compare(owner->raw, prepared->source_raw, 1) ||
        (type == OTC_CP_MODEL_TYPE_NEARBY &&
         (!prepared->nearby_station || prepared->nearby_station->rel != origin->producing_release ||
          !cJSON_Compare(otc__jget(owner->raw, "station"), prepared->nearby_station->root, 1) ||
          !canonical_prepared_range_matches(owner->raw, "distance_km", prepared->nearby_distance_km))) ||
        (type == OTC_CP_MODEL_TYPE_RANGES &&
         (!canonical_prepared_range_matches(owner->raw, "mn", prepared->range_mn) ||
          !canonical_prepared_range_matches(owner->raw, "gt", prepared->range_gt) ||
          !canonical_prepared_range_matches(owner->raw, "dhq", prepared->range_dhq) ||
          !canonical_prepared_range_matches(owner->raw, "dlq", prepared->range_dlq)))) {
        cJSON_Delete(owner->raw); free(owner); return OTC_E_INVALID_ARGUMENT;
    }
}
if (type == OTC_CP_MODEL_TYPE_CONVENTION || type == OTC_CP_MODEL_TYPE_LICENCE || type == OTC_CP_MODEL_TYPE_FILEINFO) {
    const otc_cp_prepared_metadata_fields *prepared = origin->prepared_metadata;
    const char *identifier;
    if (!prepared || prepared->model_type != type || !prepared->source_raw ||
        !cJSON_Compare(owner->raw, prepared->source_raw, 1)) {
        cJSON_Delete(owner->raw); free(owner); return OTC_E_INVALID_ARGUMENT;
    }
    if (type != OTC_CP_MODEL_TYPE_FILEINFO) {
        identifier = otc__jstr(owner->raw, type == OTC_CP_MODEL_TYPE_CONVENTION ? "convention_id" : "licence_id");
        if (!identifier || !prepared->identifier || strcmp(identifier, prepared->identifier) ||
            (type == OTC_CP_MODEL_TYPE_LICENCE &&
             (!cJSON_IsBool(otc__jget(owner->raw, "commercial_use")) ||
              cJSON_IsTrue(otc__jget(owner->raw, "commercial_use")) != prepared->commercial_use))) {
            cJSON_Delete(owner->raw); free(owner); return OTC_E_INVALID_ARGUMENT;
        }
    } else if (!prepared->file.name ||
               otc__strcmp_null(otc__jstr(owner->raw, "name"), prepared->file.name) ||
               otc__strcmp_null(otc__jstr(owner->raw, "url"), prepared->file.url) ||
               otc__strcmp_null(otc__jstr(owner->raw, "sha256"), prepared->file.sha256) ||
               (prepared->file.size < 0 ? !cJSON_IsNull(otc__jget(owner->raw, "size")) :
                (!cJSON_IsNumber(otc__jget(owner->raw, "size")) ||
                 otc__jget(owner->raw, "size")->valuedouble != (double)prepared->file.size))) {
        cJSON_Delete(owner->raw); free(owner); return OTC_E_INVALID_ARGUMENT;
    }
}
    if ((type == OTC_CP_MODEL_TYPE_HEIGHTPOINT || type == OTC_CP_MODEL_TYPE_EXTREME ||
         type == OTC_CP_MODEL_TYPE_CURRENTPOINT || type == OTC_CP_MODEL_TYPE_CURRENTEVENT) &&
        !canonical_prepared_point_matches(origin->prepared_prediction_point, owner->raw, type)) {
        cJSON_Delete(owner->raw); free(owner); return OTC_E_INVALID_ARGUMENT;
    }
    if (type == OTC_CP_MODEL_TYPE_TIMEBASE) {
        const otc_cp_prepared_time_base_fields *prepared = origin->prepared_time_base;
        if (!prepared || !prepared->producing_station || prepared->producing_station->rel != origin->producing_release ||
            !canonical_prepared_source_matches(prepared->producing_station, prepared->source_time_base_raw, 1) ||
            !cJSON_Compare(owner->raw, prepared->source_time_base_raw, 1) ||
            !canonical_prepared_evidence_matches(prepared->source_time_base_raw, prepared->evidence, prepared->evidence_count)) {
            cJSON_Delete(owner->raw); free(owner); return OTC_E_INVALID_ARGUMENT;
        }
    } else if (type == OTC_CP_MODEL_TYPE_CONSTANTSET &&
        (!canonical_prepared_set_matches(origin->prepared_constant_set, origin->producing_release) ||
         !cJSON_Compare(owner->raw, origin->prepared_constant_set->source_set_raw, 1))) {
        cJSON_Delete(owner->raw); free(owner); return OTC_E_INVALID_ARGUMENT;
    }
    memset(out, 0, sizeof *out);
    switch (type) {
case OTC_CP_MODEL_TYPE_SUBORDINATEOFFSETS: {
        const otc_offsets_t *native = &origin->prepared_offsets->fields;
        otc_cp_model_SubordinateOffsets *projected = &out->value.SubordinateOffsets;
        otc_cp_model_QcFlag *flags;
        otc_qc_flag *native_flags;
        const cJSON *raw_flags = otc__jget(owner->raw, "qc_flags");
        size_t i;
        owner->json_storage = calloc(1, sizeof *owner->json_storage);
        if (!owner->json_storage) { cJSON_Delete(owner->raw); free(owner); return OTC_E_NOMEM; }
        out->tag = OTC_CP_TYPED_MODEL_SUBORDINATEOFFSETS;
        projected->reference_station_id.value = otc__jstr(owner->raw, "reference_station_id");
        canonical_offsets_number(&projected->time_offset_high_min, native->time_offset_high_min);
        canonical_offsets_number(&projected->time_offset_low_min, native->time_offset_low_min);
        canonical_offsets_number(&projected->height_offset_high, native->height_offset_high);
        canonical_offsets_number(&projected->height_offset_low, native->height_offset_low);
        projected->height_adjusted_type.value = canonical_offsets_height_type(native->height_adjusted_type);
        canonical_datum_nullable_string(&projected->licence_id, owner->raw, "licence_id");
        canonical_datum_nullable_string(&projected->offset_id, owner->raw, "offset_id");
        canonical_datum_nullable_string(&projected->source, owner->raw, "source");
        canonical_datum_nullable_string(&projected->source_version, owner->raw, "source_version");
        canonical_datum_nullable_string(&projected->source_record_id, owner->raw, "source_record_id");
        projected->source_type.presence = native->source_type == OTC_SOURCE_TYPE_UNSET ? OTC_CP_PRESENT_NULL : OTC_CP_PRESENT_VALUE;
        projected->source_type.value.value = canonical_offsets_source_type(native->source_type);
        projected->qc_status.presence = native->qc_status == OTC_QC_STATUS_UNSET ? OTC_CP_PRESENT_NULL : OTC_CP_PRESENT_VALUE;
        projected->qc_status.value.value = canonical_offsets_qc_status(native->qc_status);
        flags = canonical_index_alloc(owner->json_storage, native->qc_flags_count, sizeof *flags);
        native_flags = canonical_index_alloc(owner->json_storage, native->qc_flags_count, sizeof *native_flags);
        if (!flags || !native_flags) goto offsets_no_memory;
        for (i = 0; i < native->qc_flags_count; i++) {
            native_flags[i].json = cJSON_GetArrayItem(raw_flags, (int)i);
            flags[i].value = &native_flags[i];
        }
        projected->qc_flags.items = flags; projected->qc_flags.count = native->qc_flags_count;
        projected->fallback.presence = native->fallback ? OTC_CP_PRESENT_VALUE : OTC_CP_PRESENT_NULL;
        if (native->fallback) {
            otc_fallback *value = canonical_index_alloc(owner->json_storage, 1, sizeof *value);
            if (!value) goto offsets_no_memory;
            value->json = (cJSON *)otc__jget(owner->raw, "fallback"); projected->fallback.value.value = value;
        }
        projected->vintage.presence = native->vintage ? OTC_CP_PRESENT_VALUE : OTC_CP_PRESENT_NULL;
        if (native->vintage) {
            otc_historical_offset_vintage *value = canonical_index_alloc(owner->json_storage, 1, sizeof *value);
            if (!value) goto offsets_no_memory;
            value->json = (cJSON *)otc__jget(owner->raw, "vintage"); projected->vintage.value.value = value;
        }
        projected->provenance.presence = native->provenance ? OTC_CP_PRESENT_VALUE : OTC_CP_PRESENT_NULL;
        if (native->provenance) {
            otc_historical_offset_provenance *value = canonical_index_alloc(owner->json_storage, 1, sizeof *value);
            if (!value) goto offsets_no_memory;
            value->json = (cJSON *)otc__jget(owner->raw, "provenance"); projected->provenance.value.value = value;
        }
        break;
offsets_no_memory:
        canonical_index_owner_free(owner->json_storage); cJSON_Delete(owner->raw); free(owner);
        memset(out, 0, sizeof *out); return OTC_E_NOMEM;
    }
    case OTC_CP_MODEL_TYPE_ASTROTABLE:
        owner->value.AstroTable.rel = origin->producing_release;
        owner->value.AstroTable.raw = owner->raw;
        owner->value.AstroTable.first = origin->prepared_astro->first_year;
        owner->value.AstroTable.last = origin->prepared_astro->last_year;
        owner->value.AstroTable.next = NULL;
        out->tag = OTC_CP_TYPED_MODEL_ASTROTABLE;
        out->value.AstroTable.value = &owner->value.AstroTable;
        break;
    case OTC_CP_MODEL_TYPE_PROVENANCE: {
        otc_cp_model_Provenance *projected = &out->value.Provenance;
        const cJSON *input = otc__jget(owner->raw, "input_sha256");
        const cJSON *decision = otc__jget(owner->raw, "decision");
        const cJSON *build = otc__jget(owner->raw, "build");
        otc_status status;
        size_t i;
        owner->json_storage = calloc(1, sizeof *owner->json_storage);
        if (!owner->json_storage) { cJSON_Delete(owner->raw); free(owner); return OTC_E_NOMEM; }
        out->tag = OTC_CP_TYPED_MODEL_PROVENANCE;
        canonical_datum_nullable_string(&projected->adapter_version, owner->raw, "adapter_version");
        canonical_datum_nullable_string(&projected->selection_reason, owner->raw, "selection_reason");
        projected->carried_from_release.value.value = otc__jstr(owner->raw, "carried_from_release");
        projected->carried_from_release.presence = projected->carried_from_release.value.value ? OTC_CP_PRESENT_VALUE : OTC_CP_PRESENT_NULL;
        projected->input_sha256.presence = input ? OTC_CP_PRESENT_VALUE : OTC_CP_PRESENT_NULL;
        if (input) {
            size_t count = (size_t)cJSON_GetArraySize(input);
            otc_cp_contract_string_ *items = canonical_index_alloc(owner->json_storage, count, sizeof *items);
            if (!items) { status = OTC_E_NOMEM; goto provenance_failure; }
            for (i = 0; i < count; i++) {
                const cJSON *item = cJSON_GetArrayItem(input, (int)i);
                if (!cJSON_IsString(item)) { status = OTC_E_INVALID_ARGUMENT; goto provenance_failure; }
                items[i].value = item->valuestring;
            }
            projected->input_sha256.value.items = items; projected->input_sha256.value.count = count;
        }
        projected->decision.presence = decision ? OTC_CP_PRESENT_VALUE : OTC_CP_PRESENT_NULL;
        if (decision) { status = canonical_native_json(owner->json_storage, decision, &projected->decision.value); if (status != OTC_OK) goto provenance_failure; }
        projected->build.presence = build ? OTC_CP_PRESENT_VALUE : OTC_CP_PRESENT_NULL;
        if (build) {
            owner->value.ProvenanceBuild.json = (cJSON *)build;
            projected->build.value.value = &owner->value.ProvenanceBuild;
        }
        status = canonical_native_json(owner->json_storage, owner->raw, &projected->raw);
        if (status != OTC_OK) goto provenance_failure;
        break;
provenance_failure:
        canonical_index_owner_free(owner->json_storage); cJSON_Delete(owner->raw); free(owner);
        memset(out, 0, sizeof *out); return status;
    }
case OTC_CP_MODEL_TYPE_DATUMINFO: case OTC_CP_MODEL_TYPE_DATUMLEVEL: {
    const otc_cp_prepared_datum_fields *prepared = origin->prepared_datum;
    otc_status status = OTC_OK;
    owner->json_storage = calloc(1, sizeof *owner->json_storage);
    if (!owner->json_storage) { cJSON_Delete(owner->raw); free(owner); return OTC_E_NOMEM; }
    if (type == OTC_CP_MODEL_TYPE_DATUMLEVEL) {
        out->tag = OTC_CP_TYPED_MODEL_DATUMLEVEL;
        status = canonical_bind_datum_level(owner, owner->raw, prepared->levels, &out->value.DatumLevel);
    } else {
        otc_cp_model_DatumInfo *projected = &out->value.DatumInfo;
        otc_cp_model_DatumLevel *levels;
        const cJSON *raw_levels = otc__jget(owner->raw, "levels");
        size_t i;
        out->tag = OTC_CP_TYPED_MODEL_DATUMINFO;
        canonical_datum_nullable_string(&projected->set_id, owner->raw, "set_id");
        canonical_datum_nullable_string(&projected->zero, owner->raw, "zero");
        canonical_datum_nullable_string(&projected->zero_name, owner->raw, "zero_name");
        canonical_datum_nullable_string(&projected->chart_datum, owner->raw, "chart_datum");
        projected->msl_offset_m.presence = prepared->info.has_msl_offset ? OTC_CP_PRESENT_VALUE : OTC_CP_PRESENT_NULL;
        projected->msl_offset_m.value.value = prepared->info.msl_offset_m;
        levels = canonical_index_alloc(owner->json_storage, prepared->level_count, sizeof *levels);
        if (!levels) status = OTC_E_NOMEM;
        else {
            projected->levels.items = levels; projected->levels.count = prepared->level_count;
            for (i = 0; i < prepared->level_count && status == OTC_OK; i++)
                status = canonical_bind_datum_level(owner, cJSON_GetArrayItem(raw_levels, (int)i), &prepared->levels[i], &levels[i]);
        }
    }
    if (status != OTC_OK) {
        canonical_index_owner_free(owner->json_storage); cJSON_Delete(owner->raw); free(owner);
        memset(out, 0, sizeof *out); return status;
    }
    break;
}
case OTC_CP_MODEL_TYPE_TOMBSTONE:
    owner->value.Tombstone.root = owner->raw;
    out->tag = OTC_CP_TYPED_MODEL_TOMBSTONE;
    out->value.Tombstone.value = &owner->value.Tombstone;
    break;
case OTC_CP_MODEL_TYPE_NEARBY:
    out->tag = OTC_CP_TYPED_MODEL_NEARBY;
    out->value.Nearby.station.value = origin->prepared_value->nearby_station;
    out->value.Nearby.distance_km.value = origin->prepared_value->nearby_distance_km;
    break;
case OTC_CP_MODEL_TYPE_RANGES: {
    const otc_cp_prepared_value_fields *prepared = origin->prepared_value;
    otc_cp_model_Ranges *ranges = &out->value.Ranges;
    out->tag = OTC_CP_TYPED_MODEL_RANGES;
    ranges->mn.presence = isnan(prepared->range_mn) ? OTC_CP_PRESENT_NULL : OTC_CP_PRESENT_VALUE;
    ranges->mn.value.value = prepared->range_mn;
    ranges->gt.presence = isnan(prepared->range_gt) ? OTC_CP_PRESENT_NULL : OTC_CP_PRESENT_VALUE;
    ranges->gt.value.value = prepared->range_gt;
    ranges->dhq.presence = isnan(prepared->range_dhq) ? OTC_CP_PRESENT_NULL : OTC_CP_PRESENT_VALUE;
    ranges->dhq.value.value = prepared->range_dhq;
    ranges->dlq.presence = isnan(prepared->range_dlq) ? OTC_CP_PRESENT_NULL : OTC_CP_PRESENT_VALUE;
    ranges->dlq.value.value = prepared->range_dlq;
    break;
}
case OTC_CP_MODEL_TYPE_CONVENTION:
    owner->value.Convention.json = owner->raw;
    owner->value.Convention.id = otc__jstr(owner->raw, "convention_id");
    out->tag = OTC_CP_TYPED_MODEL_CONVENTION;
    out->value.Convention.value = &owner->value.Convention;
    break;
case OTC_CP_MODEL_TYPE_LICENCE:
    owner->value.Licence.json = owner->raw;
    owner->value.Licence.id = otc__jstr(owner->raw, "licence_id");
    owner->value.Licence.commercial_use = origin->prepared_metadata->commercial_use;
    out->tag = OTC_CP_TYPED_MODEL_LICENCE;
    out->value.Licence.value = &owner->value.Licence;
    break;
case OTC_CP_MODEL_TYPE_FILEINFO:
    owner->value.FileInfo.name = (char *)otc__jstr(owner->raw, "name");
    owner->value.FileInfo.url = (char *)otc__jstr(owner->raw, "url");
    owner->value.FileInfo.size = origin->prepared_metadata->file.size;
    owner->value.FileInfo.sha256 = (char *)otc__jstr(owner->raw, "sha256");
    out->tag = OTC_CP_TYPED_MODEL_FILEINFO;
    out->value.FileInfo.value = &owner->value.FileInfo;
    break;
    case OTC_CP_MODEL_TYPE_HEIGHTPOINT: {
        const otc_cp_prepared_prediction_point_fields *prepared = origin->prepared_prediction_point;
        out->tag = OTC_CP_TYPED_MODEL_HEIGHTPOINT;
        out->value.HeightPoint.time.value = prepared->time;
        out->value.HeightPoint.height_m.value = prepared->fields.height.height_m;
        out->value.HeightPoint.local_time.presence = OTC_CP_PRESENT_NULL;
        out->value.HeightPoint.utc_offset_s.presence = OTC_CP_PRESENT_NULL;
        break;
    }
    case OTC_CP_MODEL_TYPE_EXTREME: {
        const otc_cp_prepared_prediction_point_fields *prepared = origin->prepared_prediction_point;
        out->tag = OTC_CP_TYPED_MODEL_EXTREME;
        out->value.Extreme.time.value = prepared->time;
        out->value.Extreme.height_m.value = prepared->fields.extreme.height_m;
        out->value.Extreme.type.value = (otc_cp_contract_enum_extreme_type_tag)prepared->fields.extreme.type;
        out->value.Extreme.local_time.presence = OTC_CP_PRESENT_NULL;
        out->value.Extreme.utc_offset_s.presence = OTC_CP_PRESENT_NULL;
        break;
    }
    case OTC_CP_MODEL_TYPE_CURRENTPOINT: {
        const otc_cp_prepared_prediction_point_fields *prepared = origin->prepared_prediction_point;
        out->tag = OTC_CP_TYPED_MODEL_CURRENTPOINT;
        out->value.CurrentPoint.time.value = prepared->time;
        out->value.CurrentPoint.velocity_major_ms.value = prepared->fields.current.velocity_major_ms;
        out->value.CurrentPoint.velocity_minor_ms.value = prepared->fields.current.velocity_minor_ms;
        out->value.CurrentPoint.speed_ms.value = prepared->fields.current.speed_ms;
        out->value.CurrentPoint.direction_deg.presence = isfinite(prepared->fields.current.direction_deg) ? OTC_CP_PRESENT_VALUE : OTC_CP_PRESENT_NULL;
        out->value.CurrentPoint.direction_deg.value.value = prepared->fields.current.direction_deg;
        out->value.CurrentPoint.local_time.presence = OTC_CP_PRESENT_NULL;
        out->value.CurrentPoint.utc_offset_s.presence = OTC_CP_PRESENT_NULL;
        break;
    }
    case OTC_CP_MODEL_TYPE_CURRENTEVENT: {
        const otc_cp_prepared_prediction_point_fields *prepared = origin->prepared_prediction_point;
        out->tag = OTC_CP_TYPED_MODEL_CURRENTEVENT;
        out->value.CurrentEvent.time.value = prepared->time;
        out->value.CurrentEvent.type.value = (otc_cp_contract_enum_current_event_type_tag)prepared->fields.event.type;
        out->value.CurrentEvent.velocity_ms.value = prepared->fields.event.velocity_ms;
        out->value.CurrentEvent.direction_deg.presence = isfinite(prepared->fields.event.direction_deg) ? OTC_CP_PRESENT_VALUE : OTC_CP_PRESENT_NULL;
        out->value.CurrentEvent.direction_deg.value.value = prepared->fields.event.direction_deg;
        out->value.CurrentEvent.local_time.presence = OTC_CP_PRESENT_NULL;
        out->value.CurrentEvent.utc_offset_s.presence = OTC_CP_PRESENT_NULL;
        break;
    }
    case OTC_CP_MODEL_TYPE_RECORDSPAN:
        owner->value.RecordSpan.json = owner->raw;
        out->tag = OTC_CP_TYPED_MODEL_RECORDSPAN; out->value.RecordSpan.value = &owner->value.RecordSpan; break;
    case OTC_CP_MODEL_TYPE_DATUM:
        owner->value.Datum.json = owner->raw;
        out->tag = OTC_CP_TYPED_MODEL_DATUM; out->value.Datum.value = &owner->value.Datum; break;
    case OTC_CP_MODEL_TYPE_DROPPEDCONSTITUENT:
        owner->value.DroppedConstituent.json = owner->raw;
        out->tag = OTC_CP_TYPED_MODEL_DROPPEDCONSTITUENT; out->value.DroppedConstituent.value = &owner->value.DroppedConstituent; break;
    case OTC_CP_MODEL_TYPE_QCFLAG:
        owner->value.QcFlag.json = owner->raw;
        out->tag = OTC_CP_TYPED_MODEL_QCFLAG; out->value.QcFlag.value = &owner->value.QcFlag; break;
    case OTC_CP_MODEL_TYPE_PROVENANCEBUILD:
        owner->value.ProvenanceBuild.json = owner->raw;
        out->tag = OTC_CP_TYPED_MODEL_PROVENANCEBUILD; out->value.ProvenanceBuild.value = &owner->value.ProvenanceBuild; break;
    case OTC_CP_MODEL_TYPE_FALLBACK:
        owner->value.Fallback.json = owner->raw;
        out->tag = OTC_CP_TYPED_MODEL_FALLBACK; out->value.Fallback.value = &owner->value.Fallback; break;
    case OTC_CP_MODEL_TYPE_HISTORICALOFFSETVINTAGE:
        owner->value.HistoricalOffsetVintage.json = owner->raw;
        out->tag = OTC_CP_TYPED_MODEL_HISTORICALOFFSETVINTAGE; out->value.HistoricalOffsetVintage.value = &owner->value.HistoricalOffsetVintage; break;
    case OTC_CP_MODEL_TYPE_HISTORICALOFFSETPROVENANCE:
        owner->value.HistoricalOffsetProvenance.json = owner->raw;
        out->tag = OTC_CP_TYPED_MODEL_HISTORICALOFFSETPROVENANCE; out->value.HistoricalOffsetProvenance.value = &owner->value.HistoricalOffsetProvenance; break;
    case OTC_CP_MODEL_TYPE_CONSTITUENT:
        otc__fill_constituent(&owner->value.Constituent, owner->raw);
        out->tag = OTC_CP_TYPED_MODEL_CONSTITUENT; out->value.Constituent.value = &owner->value.Constituent; break;
    case OTC_CP_MODEL_TYPE_SOURCERECORD:
        owner->value.SourceRecord.json = owner->raw;
        owner->value.SourceRecord.rel = origin->producing_release;
        out->tag = OTC_CP_TYPED_MODEL_SOURCERECORD; out->value.SourceRecord.value = &owner->value.SourceRecord; break;
    case OTC_CP_MODEL_TYPE_TIMEBASE:
        owner->value.TimeBase.json = owner->raw;
        owner->value.TimeBase.ev = origin->prepared_time_base->evidence;
        owner->value.TimeBase.n_ev = origin->prepared_time_base->evidence_count;
        out->tag = OTC_CP_TYPED_MODEL_TIMEBASE; out->value.TimeBase.value = &owner->value.TimeBase; break;
    case OTC_CP_MODEL_TYPE_CONSTANTSET: {
        const otc_cp_prepared_constant_set_fields *prepared = origin->prepared_constant_set;
        otc_set *set = &owner->value.ConstantSet;
        set->json = owner->raw; set->station = prepared->producing_station;
        set->conv = prepared->convention; set->lic = prepared->licence;
        set->cons = prepared->constituents; set->n_cons = prepared->constituent_count;
        set->flags = prepared->qc_flags; set->n_flags = prepared->qc_flag_count;
        set->drops = prepared->dropped; set->n_drops = prepared->dropped_count;
        set->val = prepared->validation; set->n_val = prepared->validation_count;
        set->recommended = prepared->recommended; set->no_constants = prepared->no_constants;
        set->fallback.json = otc__jget(owner->raw, "fallback");
        set->span.json = otc__jget(owner->raw, "record_span"); set->has_span = cJSON_IsObject(set->span.json);
        set->datum.json = otc__jget(owner->raw, "datum"); set->has_datum = cJSON_IsObject(set->datum.json);
        set->tb.json = otc__jget(owner->raw, "time_base"); set->has_tb = cJSON_IsObject(set->tb.json);
        if (set->has_tb) { set->tb.ev = prepared->time_base_evidence; set->tb.n_ev = prepared->time_base_evidence_count; }
        set->build.json = otc__jget(otc__jget(owner->raw, "provenance"), "build"); set->has_build = cJSON_IsObject(set->build.json);
        out->tag = OTC_CP_TYPED_MODEL_CONSTANTSET; out->value.ConstantSet.value = set; break;
    }
    case OTC_CP_MODEL_TYPE_VALIDATION: {
        const otc_validation_t *v = &owner->value.Validation;
        otc_cp_model_Validation *projected = &out->value.Validation;
        otc__fill_validation(&owner->value.Validation, owner->raw);
        out->tag = OTC_CP_TYPED_MODEL_VALIDATION;
        projected->set_id.value = v->set_id;
        projected->reference_source.value = v->reference_source;
        projected->reference_station.presence = v->reference_station ? OTC_CP_PRESENT_VALUE : OTC_CP_PRESENT_NULL;
        projected->reference_station.value.value = v->reference_station;
        projected->reference_distance_km.presence = isfinite(v->reference_distance_km) ? OTC_CP_PRESENT_VALUE : OTC_CP_PRESENT_NULL;
        projected->reference_distance_km.value.value = v->reference_distance_km;
        projected->window.value = v->window;
        projected->time_mae_min.value = v->time_mae_min;
        projected->time_p95_min.presence = isfinite(v->time_p95_min) ? OTC_CP_PRESENT_VALUE : OTC_CP_PRESENT_NULL;
        projected->time_p95_min.value.value = v->time_p95_min;
        projected->time_bias_min.presence = isfinite(v->time_bias_min) ? OTC_CP_PRESENT_VALUE : OTC_CP_PRESENT_NULL;
        projected->time_bias_min.value.value = v->time_bias_min;
        projected->height_mae_m.value = v->height_mae_m;
        projected->range_error_m.presence = isfinite(v->range_error_m) ? OTC_CP_PRESENT_VALUE : OTC_CP_PRESENT_NULL;
        projected->range_error_m.value.value = v->range_error_m;
        projected->missed_events.presence = v->missed_events >= 0 ? OTC_CP_PRESENT_VALUE : OTC_CP_PRESENT_NULL;
        projected->missed_events.value.value = v->missed_events;
        projected->extra_events.presence = v->extra_events >= 0 ? OTC_CP_PRESENT_VALUE : OTC_CP_PRESENT_NULL;
        projected->extra_events.value.value = v->extra_events;
        projected->previous_release.presence = v->has_previous_release ? OTC_CP_PRESENT_VALUE : OTC_CP_PRESENT_NULL;
        if (v->has_previous_release) {
            otc_status status;
            owner->json_storage = calloc(1, sizeof *owner->json_storage);
            if (!owner->json_storage) { cJSON_Delete(owner->raw); free(owner); memset(out, 0, sizeof *out); return OTC_E_NOMEM; }
            status = canonical_native_json(owner->json_storage, otc__jget(owner->raw, "previous_release"), &projected->previous_release.value);
            if (status != OTC_OK) { canonical_index_owner_free(owner->json_storage); cJSON_Delete(owner->raw); free(owner); memset(out, 0, sizeof *out); return status; }
        }
        break;
    }
    default: cJSON_Delete(owner->raw); free(owner); return OTC_E_NOT_BUILT;
    }
    out->native_owner = owner;
    return OTC_OK;
}

/* Station-only correspondence guard. This compares the supplied logical raw
 * fields with the already owned producer root without constructing JSON. */
static int canonical_station_raw_matches(const otc_cp_JsonValue *value, const cJSON *native)
{
    const cJSON *child;
    size_t i;
    if (!value || !native) return 0;
    switch (value->tag) {
    case OTC_CP_JSON_NULL: return cJSON_IsNull(native);
    case OTC_CP_JSON_BOOLEAN: return cJSON_IsBool(native) && value->value.boolean == cJSON_IsTrue(native);
    case OTC_CP_JSON_NUMBER: return cJSON_IsNumber(native) && value->value.number == native->valuedouble;
    case OTC_CP_JSON_STRING:
        return cJSON_IsString(native) && value->value.string.count == otc__jstr_len(native) &&
            (!value->value.string.count || (value->value.string.bytes &&
                !memcmp(value->value.string.bytes, native->valuestring, value->value.string.count)));
    case OTC_CP_JSON_ARRAY:
        if (!cJSON_IsArray(native) || value->value.array.count != (size_t)cJSON_GetArraySize(native) ||
            (value->value.array.count && !value->value.array.items)) return 0;
        child = native->child;
        for (i = 0; i < value->value.array.count; i++, child = child->next)
            if (!canonical_station_raw_matches(&value->value.array.items[i], child)) return 0;
        return 1;
    case OTC_CP_JSON_OBJECT:
        if (!cJSON_IsObject(native) || value->value.members.count != (size_t)cJSON_GetArraySize(native) ||
            (value->value.members.count && !value->value.members.entries)) return 0;
        for (i = 0; i < value->value.members.count; i++) {
            const otc_cp_JsonPair *pair = &value->value.members.entries[i];
            if (!pair->key || !pair->value) return 0;
            for (child = native->child; child; child = child->next)
                if (child->string && !strcmp(child->string, pair->key)) break;
            if (!child || !canonical_station_raw_matches(pair->value, child)) return 0;
        }
        return 1;
    }
    return 0;
}

static int canonical_station_graph_ready(const otc__prepared_station_fields *prepared, const otc_release *release)
{
    const otc_station_t *destination;
    size_t i, j;
    if (!prepared || !prepared->complete || !prepared->destination || !prepared->root || prepared->rel != release ||
        !prepared->source_records || !prepared->offset_flags || !prepared->sets || !prepared->val ||
        !prepared->order_all || !prepared->order_usable || prepared->n_all != prepared->n_sets ||
        prepared->n_usable > prepared->n_all) return 0;
    destination = prepared->destination;
    if (destination->root || destination->rel || destination->sets || destination->val || destination->source_records ||
        destination->offset_flags || destination->order_all || destination->order_usable || destination->rec ||
        destination->n_sets || destination->n_val || destination->n_source_records || destination->n_offset_flags ||
        destination->n_all || destination->n_usable) return 0;
    for (i = 0; i < prepared->n_sets; i++) {
        const otc_set *set = &prepared->sets[i];
        if (set->station != destination || !set->cons || !set->val || !set->flags || !set->drops ||
            (set->has_tb && !set->tb.ev)) return 0;
        for (j = 0; j < set->n_val; j++) {
            size_t k;
            for (k = 0; k < prepared->n_val; k++) if (set->val[j] == &prepared->val[k]) break;
            if (k == prepared->n_val) return 0;
        }
    }
    for (i = 0; i < prepared->n_all; i++) {
        for (j = 0; j < prepared->n_sets; j++) if (prepared->order_all[i] == &prepared->sets[j]) break;
        if (j == prepared->n_sets) return 0;
    }
    for (i = 0; i < prepared->n_usable; i++) {
        for (j = 0; j < prepared->n_sets; j++) if (prepared->order_usable[i] == &prepared->sets[j]) break;
        if (j == prepared->n_sets) return 0;
    }
    if (prepared->rec) {
        for (j = 0; j < prepared->n_sets; j++) if (prepared->rec == &prepared->sets[j]) break;
        if (j == prepared->n_sets) return 0;
    }
    return 1;
}

otc_status otc__canonical_materialize_typed_model(const otc_cp_raw_fields *raw_fields, const otc_cp_field_contract *field_contract, const otc_cp_origin *origin, const otc_cp_model_type *model_type, otc_cp_typed_model *typed_model_out)
{
otc_station_t *station;
otc_status status;
if (raw_fields && field_contract && origin && model_type && typed_model_out &&
    field_contract->model_type.value == model_type->value) {
    if (model_type->value == OTC_CP_MODEL_TYPE_RELEASEINFO) {
        otc_release_info *info;
        if (!origin->prepared_release_info || !origin->prepared_release_info->complete ||
            !canonical_station_raw_matches(raw_fields, origin->prepared_release_info->source_entry))
            return OTC_E_INVALID_ARGUMENT;
        status = otc__release_info_bind_prepared(origin->prepared_release_info, &info);
        if (status != OTC_OK) return status;
        typed_model_out->tag = OTC_CP_TYPED_MODEL_RELEASEINFO;
        typed_model_out->value.ReleaseInfo.value = info;
        typed_model_out->native_owner = NULL;
        return OTC_OK;
    }
    if (model_type->value == OTC_CP_MODEL_TYPE_STATS) {
        otc_stats *stats;
        if (raw_fields->tag != OTC_CP_JSON_OBJECT || raw_fields->value.members.count ||
            !origin->prepared_stats) return OTC_E_INVALID_ARGUMENT;
        status = otc__stats_bind_prepared(origin->prepared_stats, &stats);
        if (status != OTC_OK) return status;
        typed_model_out->tag = OTC_CP_TYPED_MODEL_STATS;
        typed_model_out->value.Stats.value = stats;
        typed_model_out->native_owner = NULL;
        return OTC_OK;
    }
    if (model_type->value == OTC_CP_MODEL_TYPE_UPDATERESULT) {
        const otc__prepared_update_fields *prepared = origin->prepared_update;
        struct otc_cp_native_model_owner *owner;
        otc_cp_model_UpdateResult result = {0};
        if (raw_fields->tag != OTC_CP_JSON_OBJECT || raw_fields->value.members.count || !prepared ||
            !prepared->complete || !prepared->has_from || prepared->has_to != prepared->updated ||
            !memchr(prepared->from, 0, sizeof prepared->from) ||
            (prepared->has_to && !memchr(prepared->to, 0, sizeof prepared->to))) return OTC_E_INVALID_ARGUMENT;
        owner = calloc(1, sizeof *owner);
        if (!owner) return OTC_E_NOMEM;
        owner->json_storage = calloc(1, sizeof *owner->json_storage);
        if (!owner->json_storage) { free(owner); return OTC_E_NOMEM; }
        result.updated.value = prepared->updated;
        result.from.presence = OTC_CP_PRESENT_VALUE;
        status = canonical_container_string(owner, prepared->from, &result.from.value.value);
        result.to.presence = prepared->has_to ? OTC_CP_PRESENT_VALUE : OTC_CP_ABSENT;
        if (status == OTC_OK && prepared->has_to) status = canonical_container_string(owner, prepared->to, &result.to.value.value);
        if (status != OTC_OK) {
            canonical_index_owner_free(owner->json_storage); free(owner); return OTC_E_NOMEM;
        }
        typed_model_out->tag = OTC_CP_TYPED_MODEL_UPDATERESULT;
        typed_model_out->value.UpdateResult = result;
        typed_model_out->native_owner = owner;
        return OTC_OK;
    }
}
if (raw_fields && field_contract && origin && model_type && typed_model_out &&
    model_type->value == OTC_CP_MODEL_TYPE_RELEASE && field_contract->model_type.value == model_type->value) {
    otc_release *release;
    if (!origin->prepared_release || !origin->prepared_release->complete ||
        !canonical_station_raw_matches(raw_fields, origin->prepared_release->meta)) return OTC_E_INVALID_ARGUMENT;
    status = otc__release_bind_prepared_fields(origin->prepared_release, &release);
    if (status != OTC_OK) return status;
    typed_model_out->tag = OTC_CP_TYPED_MODEL_RELEASE;
    typed_model_out->value.Release.value = release;
    typed_model_out->native_owner = NULL;
    return OTC_OK;
}
if (!raw_fields || !field_contract || !origin || !origin->producing_release || !model_type || !typed_model_out ||
    field_contract->model_type.value != model_type->value) return OTC_E_INVALID_ARGUMENT;
if (model_type->value == OTC_CP_MODEL_TYPE_HEIGHTSERIES || model_type->value == OTC_CP_MODEL_TYPE_EXTREMELIST ||
    model_type->value == OTC_CP_MODEL_TYPE_CURRENTSERIES || model_type->value == OTC_CP_MODEL_TYPE_CURRENTEVENTLIST)
    return canonical_materialize_prediction_container(raw_fields, origin, model_type->value, typed_model_out);
if (model_type->value != OTC_CP_MODEL_TYPE_STATION)
    return canonical_materialize_json_view(raw_fields, model_type->value, origin, typed_model_out);
if (!canonical_station_graph_ready(origin->prepared_station, origin->producing_release) ||
    !canonical_station_raw_matches(raw_fields, origin->prepared_station->root)) return OTC_E_INVALID_ARGUMENT;
status = otc__station_bind_prepared_fields(origin->prepared_station, &station);
if (status != OTC_OK) return status;
typed_model_out->tag = OTC_CP_TYPED_MODEL_STATION;
typed_model_out->value.Station.value = station;
typed_model_out->native_owner = NULL;
return OTC_OK;

}

otc_status otc__canonical_access_raw_record(const otc_cp_access_kind *access_kind, const otc_cp_source_record *source_record, const otc_cp_station *station, const otc_cp_release_origin *release_origin, const otc_cp_native_profile *native_profile, otc_cp_raw_record_or_valid_station *raw_record_or_valid_station_out)
{
    (void)access_kind;
    (void)source_record;
    (void)station;
    (void)release_origin;
    (void)native_profile;
    (void)raw_record_or_valid_station_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_open_client_release(const otc_cp_arguments *arguments, const otc_cp_environment *environment, const otc_cp_platform_defaults *platform_defaults, const otc_cp_cache_state *cache_state, const otc_cp_clock *clock, const otc_cp_native_profile *native_profile, const otc_cp_reader_version *reader_version, otc_cp_client_and_release *client_and_release_out)
{
    (void)arguments;
    (void)environment;
    (void)platform_defaults;
    (void)cache_state;
    (void)clock;
    (void)native_profile;
    (void)reader_version;
    (void)client_and_release_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_resolve_release_request(const otc_cp_release_request *release_request, const otc_cp_effective_options *effective_options, const otc_cp_cache_state *cache_state, const otc_cp_clock *clock, const otc_cp_reader_version *reader_version, otc_cp_loaded_release *loaded_release_out)
{
    (void)release_request;
    (void)effective_options;
    (void)cache_state;
    (void)clock;
    (void)reader_version;
    (void)loaded_release_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_exchange_release_metadata(const otc_cp_metadata_request *metadata_request, const otc_cp_trusted_cache *trusted_cache, const otc_cp_transport_options *transport_options, const otc_cp_cache_state *cache_state, const otc_cp_clock *clock, const otc_cp_reader_version *reader_version, otc_cp_validated_metadata *validated_metadata_out)
{
    (void)metadata_request;
    (void)trusted_cache;
    (void)transport_options;
    (void)cache_state;
    (void)clock;
    (void)reader_version;
    (void)validated_metadata_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_update_client_release(const otc_cp_client_state *client_state, const otc_cp_update_request *update_request, const otc_cp_clock *clock, const otc_cp_reader_version *reader_version, otc_cp_updated_client_state *updated_client_state_out)
{
    (void)client_state;
    (void)update_request;
    (void)clock;
    (void)reader_version;
    (void)updated_client_state_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_refresh_client_if_due(const otc_cp_client_state *client_state, const otc_cp_query_kind *query_kind, const otc_cp_clock *clock, const otc_cp_reader_version *reader_version, otc_cp_query_client_state *query_client_state_out)
{
    (void)client_state;
    (void)query_kind;
    (void)clock;
    (void)reader_version;
    (void)query_client_state_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_forward_held_release(const otc_cp_held_release *held_release, const otc_cp_query_arguments *query_arguments, otc_cp_held_release_result *held_release_result_out)
{
    (void)held_release;
    (void)query_arguments;
    (void)held_release_result_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_enforce_resource_lifetime(const otc_cp_resource_state *resource_state, const otc_cp_lifetime_action *lifetime_action, otc_cp_resource_state_or_error *resource_state_or_error_out)
{
    (void)resource_state;
    (void)lifetime_action;
    (void)resource_state_or_error_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_bind_checksum_manifest(const otc_cp_checksum_bytes *checksum_bytes, const otc_cp_pointer_digests *pointer_digests, const otc_cp_required_files *required_files, otc_cp_bound_checksums *bound_checksums_out)
{
    (void)checksum_bytes;
    (void)pointer_digests;
    (void)required_files;
    (void)bound_checksums_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_acquire_release_files(const otc_cp_acquisition_descriptor *acquisition_descriptor, const otc_cp_effective_options *effective_options, const otc_cp_load_mode *load_mode, const otc_cp_cache_state *cache_state, const otc_cp_clock *clock, const otc_cp_reader_version *reader_version, otc_cp_loaded_release *loaded_release_out)
{
    (void)acquisition_descriptor;
    (void)effective_options;
    (void)load_mode;
    (void)cache_state;
    (void)clock;
    (void)reader_version;
    (void)loaded_release_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_merge_cache_receipt(const otc_cp_locked_cache_state *locked_cache_state, const otc_cp_verified_file_rows *verified_file_rows, const otc_cp_release_metadata *release_metadata, otc_cp_merged_receipt *merged_receipt_out)
{
    (void)locked_cache_state;
    (void)verified_file_rows;
    (void)release_metadata;
    (void)merged_receipt_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_select_cached_release(const otc_cp_release_candidates *release_candidates, const otc_cp_effective_options *effective_options, const otc_cp_cache_state *cache_state, const otc_cp_clock *clock, otc_cp_usable_cached_release_or_error *usable_cached_release_or_error_out)
{
    (void)release_candidates;
    (void)effective_options;
    (void)cache_state;
    (void)clock;
    (void)usable_cached_release_or_error_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_verify_release_files(const otc_cp_release_files *release_files, const otc_cp_trusted_cached_pointer *trusted_cached_pointer, otc_cp_verification_result *verification_result_out)
{
    (void)release_files;
    (void)trusted_cached_pointer;
    (void)verification_result_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_publish_download(const otc_cp_destination *destination, const otc_cp_format_selection *format_selection, const otc_cp_overwrite_policy *overwrite_policy, const otc_cp_release_files *release_files, const otc_cp_checksum_bytes *checksum_bytes, const otc_cp_pointer_digests *pointer_digests, otc_cp_download_result *download_result_out)
{
    (void)destination;
    (void)format_selection;
    (void)overwrite_policy;
    (void)release_files;
    (void)checksum_bytes;
    (void)pointer_digests;
    (void)download_result_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_manage_cache_inventory(const otc_cp_inventory_action *inventory_action, const otc_cp_cache_state *cache_state, const otc_cp_keep *keep, const otc_cp_current_cache_directory *current_cache_directory, const otc_cp_clock *clock, otc_cp_cache_inventory_result *cache_inventory_result_out)
{
    (void)inventory_action;
    (void)cache_state;
    (void)keep;
    (void)current_cache_directory;
    (void)clock;
    (void)cache_inventory_result_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_perform_guarded_io(const otc_cp_io_kind *io_kind, const otc_cp_io_request *io_request, const otc_cp_io_options *io_options, const otc_cp_clock *clock, otc_cp_io_result *io_result_out)
{
    (void)io_kind;
    (void)io_request;
    (void)io_options;
    (void)clock;
    (void)io_result_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_project_station_index(const otc_cp_station_source_row *station_source_row, const otc_cp_source_byte_span *source_byte_span, const otc_cp_projection_contract *projection_contract, otc_cp_station_index_entry *station_index_entry_out)
{
struct otc_cp_index_owner *owner;
otc_cp_station_index_entry result = {0};
cJSON *row;
    cJSON *normalized = NULL;
    char *projected_bytes = NULL;
otc_status status;
if (!station_source_row || !source_byte_span || !projection_contract || !projection_contract->release_context || !station_index_entry_out ||
    projection_contract->value != OTC_CP_PROJECTION_CONTRACT_EXACT_COPIED_FIELD_PROJECTION_RULES ||
    source_byte_span->offset_bytes.value < 0 || source_byte_span->length_bytes.value <= 0) return OTC_E_INVALID_ARGUMENT;
row = canonical_source_json(station_source_row);
if (!row) return OTC_E_INVALID_ARGUMENT;
owner = calloc(1, sizeof *owner);
if (!owner) { cJSON_Delete(row); return OTC_E_NOMEM; }
status = otc__project_station_entry(projection_contract->release_context, row, (uint64_t)source_byte_span->offset_bytes.value,
    (size_t)source_byte_span->length_bytes.value, &owner->document);
cJSON_Delete(row);
if (status != OTC_OK) goto failure;
    /* The native projection emits NUL-containing string values as exact
     * JSON literals. Its unchanged encoder/parser recover their typed
     * string representation and byte lengths before field projection. */
    status = otc__encode_cache_json(owner->document, &projected_bytes);
    if (status != OTC_OK) goto failure;
    status = otc__json_parse_st(projected_bytes, strlen(projected_bytes), &normalized);
    free(projected_bytes);
    if (status != OTC_OK) goto failure;
    cJSON_Delete(owner->document); owner->document = normalized;
    if (!cJSON_IsObject(owner->document)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
    (result).has_presence = true;
    {
        const cJSON *field1 = cJSON_GetObjectItemCaseSensitive(owner->document, "station_id");
        if (field1) {
            (result).present_fields |= UINT64_C(1) << 0;
            if (!cJSON_IsString(field1)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
            ((result).station_id).value = (field1)->valuestring;
            ((result).station_id).byte_count = otc__jstr_len(field1);
            ((result).station_id).has_byte_count = true;
        }
    }
    {
        const cJSON *field2 = cJSON_GetObjectItemCaseSensitive(owner->document, "status");
        if (field2) {
            (result).present_fields |= UINT64_C(1) << 1;
            if (!cJSON_IsString(field2)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
            ((result).status).value = (field2)->valuestring;
            ((result).status).byte_count = otc__jstr_len(field2);
            ((result).status).has_byte_count = true;
        }
    }
    {
        const cJSON *field3 = cJSON_GetObjectItemCaseSensitive(owner->document, "name");
        if (field3) {
            (result).present_fields |= UINT64_C(1) << 2;
            if (cJSON_IsString(field3)) {
                ((result).name).tag = 0;
                if (!cJSON_IsString(field3)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                (((result).name).value.variant_0).value = (field3)->valuestring;
                (((result).name).value.variant_0).byte_count = otc__jstr_len(field3);
                (((result).name).value.variant_0).has_byte_count = true;
            }             else if (cJSON_IsNull(field3)) {
                ((result).name).tag = 1;
                (((result).name).value.variant_1).value = 0;
            } else { status = OTC_E_INVALID_ARGUMENT; goto failure; }
        }
    }
    {
        const cJSON *field4 = cJSON_GetObjectItemCaseSensitive(owner->document, "name_folded");
        if (field4) {
            (result).present_fields |= UINT64_C(1) << 3;
            if (cJSON_IsString(field4)) {
                ((result).name_folded).tag = 0;
                if (!cJSON_IsString(field4)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                (((result).name_folded).value.variant_0).value = (field4)->valuestring;
                (((result).name_folded).value.variant_0).byte_count = otc__jstr_len(field4);
                (((result).name_folded).value.variant_0).has_byte_count = true;
            }             else if (cJSON_IsNull(field4)) {
                ((result).name_folded).tag = 1;
                (((result).name_folded).value.variant_1).value = 0;
            } else { status = OTC_E_INVALID_ARGUMENT; goto failure; }
        }
    }
    {
        const cJSON *field5 = cJSON_GetObjectItemCaseSensitive(owner->document, "country");
        if (field5) {
            (result).present_fields |= UINT64_C(1) << 4;
            if (cJSON_IsString(field5)) {
                ((result).country).tag = 0;
                if (!cJSON_IsString(field5)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                (((result).country).value.variant_0).value = (field5)->valuestring;
                (((result).country).value.variant_0).byte_count = otc__jstr_len(field5);
                (((result).country).value.variant_0).has_byte_count = true;
            }             else if (cJSON_IsNull(field5)) {
                ((result).country).tag = 1;
                (((result).country).value.variant_1).value = 0;
            } else { status = OTC_E_INVALID_ARGUMENT; goto failure; }
        }
    }
    {
        const cJSON *field6 = cJSON_GetObjectItemCaseSensitive(owner->document, "type");
        if (field6) {
            (result).present_fields |= UINT64_C(1) << 5;
            if (cJSON_IsString(field6)) {
                ((result).type).tag = 0;
                if (!cJSON_IsString(field6)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                (((result).type).value.variant_0).value = (field6)->valuestring;
                (((result).type).value.variant_0).byte_count = otc__jstr_len(field6);
                (((result).type).value.variant_0).has_byte_count = true;
            }             else if (cJSON_IsNull(field6)) {
                ((result).type).tag = 1;
                (((result).type).value.variant_1).value = 0;
            } else { status = OTC_E_INVALID_ARGUMENT; goto failure; }
        }
    }
    {
        const cJSON *field7 = cJSON_GetObjectItemCaseSensitive(owner->document, "kind");
        if (field7) {
            (result).present_fields |= UINT64_C(1) << 6;
            if (cJSON_IsString(field7)) {
                ((result).kind).tag = 0;
                if (!cJSON_IsString(field7)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                (((result).kind).value.variant_0).value = (field7)->valuestring;
                (((result).kind).value.variant_0).byte_count = otc__jstr_len(field7);
                (((result).kind).value.variant_0).has_byte_count = true;
            }             else if (cJSON_IsNull(field7)) {
                ((result).kind).tag = 1;
                (((result).kind).value.variant_1).value = 0;
            } else { status = OTC_E_INVALID_ARGUMENT; goto failure; }
        }
    }
    {
        const cJSON *field8 = cJSON_GetObjectItemCaseSensitive(owner->document, "reference_station_id");
        if (field8) {
            (result).present_fields |= UINT64_C(1) << 7;
            if (cJSON_IsString(field8)) {
                ((result).reference_station_id).tag = 0;
                if (!cJSON_IsString(field8)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                (((result).reference_station_id).value.variant_0).value = (field8)->valuestring;
                (((result).reference_station_id).value.variant_0).byte_count = otc__jstr_len(field8);
                (((result).reference_station_id).value.variant_0).has_byte_count = true;
            }             else if (cJSON_IsNull(field8)) {
                ((result).reference_station_id).tag = 1;
                (((result).reference_station_id).value.variant_1).value = 0;
            } else { status = OTC_E_INVALID_ARGUMENT; goto failure; }
        }
    }
    {
        const cJSON *field9 = cJSON_GetObjectItemCaseSensitive(owner->document, "offsets_licence_id");
        if (field9) {
            (result).present_fields |= UINT64_C(1) << 8;
            if (cJSON_IsString(field9)) {
                ((result).offsets_licence_id).tag = 0;
                if (!cJSON_IsString(field9)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                (((result).offsets_licence_id).value.variant_0).value = (field9)->valuestring;
                (((result).offsets_licence_id).value.variant_0).byte_count = otc__jstr_len(field9);
                (((result).offsets_licence_id).value.variant_0).has_byte_count = true;
            }             else if (cJSON_IsNull(field9)) {
                ((result).offsets_licence_id).tag = 1;
                (((result).offsets_licence_id).value.variant_1).value = 0;
            } else { status = OTC_E_INVALID_ARGUMENT; goto failure; }
        }
    }
    {
        const cJSON *field10 = cJSON_GetObjectItemCaseSensitive(owner->document, "recommended_set_id");
        if (field10) {
            (result).present_fields |= UINT64_C(1) << 9;
            if (cJSON_IsString(field10)) {
                ((result).recommended_set_id).tag = 0;
                if (!cJSON_IsString(field10)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                (((result).recommended_set_id).value.variant_0).value = (field10)->valuestring;
                (((result).recommended_set_id).value.variant_0).byte_count = otc__jstr_len(field10);
                (((result).recommended_set_id).value.variant_0).has_byte_count = true;
            }             else if (cJSON_IsNull(field10)) {
                ((result).recommended_set_id).tag = 1;
                (((result).recommended_set_id).value.variant_1).value = 0;
            } else { status = OTC_E_INVALID_ARGUMENT; goto failure; }
        }
    }
    {
        const cJSON *field11 = cJSON_GetObjectItemCaseSensitive(owner->document, "lat");
        if (field11) {
            (result).present_fields |= UINT64_C(1) << 10;
            if (cJSON_IsNumber(field11)) {
                ((result).lat).tag = 0;
                if (!cJSON_IsNumber(field11)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                (((result).lat).value.variant_0).value = (double)(field11)->valuedouble;
            }             else if (cJSON_IsNull(field11)) {
                ((result).lat).tag = 1;
                (((result).lat).value.variant_1).value = 0;
            } else { status = OTC_E_INVALID_ARGUMENT; goto failure; }
        }
    }
    {
        const cJSON *field12 = cJSON_GetObjectItemCaseSensitive(owner->document, "lon");
        if (field12) {
            (result).present_fields |= UINT64_C(1) << 11;
            if (cJSON_IsNumber(field12)) {
                ((result).lon).tag = 0;
                if (!cJSON_IsNumber(field12)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                (((result).lon).value.variant_0).value = (double)(field12)->valuedouble;
            }             else if (cJSON_IsNull(field12)) {
                ((result).lon).tag = 1;
                (((result).lon).value.variant_1).value = 0;
            } else { status = OTC_E_INVALID_ARGUMENT; goto failure; }
        }
    }
    {
        const cJSON *field13 = cJSON_GetObjectItemCaseSensitive(owner->document, "offset");
        if (field13) {
            (result).present_fields |= UINT64_C(1) << 12;
            if (!cJSON_IsNumber(field13)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
            ((result).offset).value = (int64_t)(field13)->valuedouble;
        }
    }
    {
        const cJSON *field14 = cJSON_GetObjectItemCaseSensitive(owner->document, "length");
        if (field14) {
            (result).present_fields |= UINT64_C(1) << 13;
            if (!cJSON_IsNumber(field14)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
            ((result).length).value = (int64_t)(field14)->valuedouble;
        }
    }
    {
        const cJSON *field15 = cJSON_GetObjectItemCaseSensitive(owner->document, "aliases");
        if (field15) {
            (result).present_fields |= UINT64_C(1) << 14;
            if (!cJSON_IsObject(field15)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
            {
                size_t i16 = 0, count = (size_t)cJSON_GetArraySize(field15);
                const cJSON *node16;
                otc_cp_station_index_entry_aliases_entry_value_map_entry *items16 = canonical_index_alloc(owner, count, sizeof *items16);
                if (!items16) { status = OTC_E_NOMEM; goto failure; }
                ((result).aliases).entries = items16; ((result).aliases).count = count;
                cJSON_ArrayForEach(node16, field15) {
                    items16[i16].key.value = node16->string;
                    if (!cJSON_IsArray(node16)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                    {
                        size_t i17 = 0, count = (size_t)cJSON_GetArraySize(node16);
                        const cJSON *node17;
                        otc_cp_station_index_entry_aliases_entry_value_item *items17 = canonical_index_alloc(owner, count, sizeof *items17);
                        if (!items17) { status = OTC_E_NOMEM; goto failure; }
                        (items16[i16].value).items = items17; (items16[i16].value).count = count;
                        cJSON_ArrayForEach(node17, node16) {
                            if (!cJSON_IsString(node17)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                            (items17[i17]).value = (node17)->valuestring;
                            (items17[i17]).byte_count = otc__jstr_len(node17);
                            (items17[i17]).has_byte_count = true;
                            i17++;
                        }
                    }
                    i16++;
                }
            }
        }
    }
    {
        const cJSON *field18 = cJSON_GetObjectItemCaseSensitive(owner->document, "sets");
        if (field18) {
            (result).present_fields |= UINT64_C(1) << 15;
            if (!cJSON_IsArray(field18)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
            {
                size_t i19 = 0, count = (size_t)cJSON_GetArraySize(field18);
                const cJSON *node19;
                otc_cp_station_index_entry_sets_item *items19 = canonical_index_alloc(owner, count, sizeof *items19);
                if (!items19) { status = OTC_E_NOMEM; goto failure; }
                ((result).sets).items = items19; ((result).sets).count = count;
                cJSON_ArrayForEach(node19, field18) {
                    if (!cJSON_IsObject(node19)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                    (items19[i19]).has_presence = true;
                    {
                        const cJSON *field20 = cJSON_GetObjectItemCaseSensitive(node19, "set_id");
                        if (field20) {
                            (items19[i19]).present_fields |= UINT64_C(1) << 0;
                            if (cJSON_IsString(field20)) {
                                ((items19[i19]).set_id).tag = 0;
                                if (!cJSON_IsString(field20)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                (((items19[i19]).set_id).value.variant_0).value = (field20)->valuestring;
                                (((items19[i19]).set_id).value.variant_0).byte_count = otc__jstr_len(field20);
                                (((items19[i19]).set_id).value.variant_0).has_byte_count = true;
                            }                             else if (cJSON_IsNull(field20)) {
                                ((items19[i19]).set_id).tag = 1;
                                (((items19[i19]).set_id).value.variant_1).value = 0;
                            } else { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                        }
                    }
                    {
                        const cJSON *field21 = cJSON_GetObjectItemCaseSensitive(node19, "source");
                        if (field21) {
                            (items19[i19]).present_fields |= UINT64_C(1) << 1;
                            if (cJSON_IsString(field21)) {
                                ((items19[i19]).source).tag = 0;
                                if (!cJSON_IsString(field21)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                (((items19[i19]).source).value.variant_0).value = (field21)->valuestring;
                                (((items19[i19]).source).value.variant_0).byte_count = otc__jstr_len(field21);
                                (((items19[i19]).source).value.variant_0).has_byte_count = true;
                            }                             else if (cJSON_IsNull(field21)) {
                                ((items19[i19]).source).tag = 1;
                                (((items19[i19]).source).value.variant_1).value = 0;
                            } else { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                        }
                    }
                    {
                        const cJSON *field22 = cJSON_GetObjectItemCaseSensitive(node19, "source_type");
                        if (field22) {
                            (items19[i19]).present_fields |= UINT64_C(1) << 2;
                            if (cJSON_IsString(field22)) {
                                ((items19[i19]).source_type).tag = 0;
                                if (!cJSON_IsString(field22)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                (((items19[i19]).source_type).value.variant_0).value = (field22)->valuestring;
                                (((items19[i19]).source_type).value.variant_0).byte_count = otc__jstr_len(field22);
                                (((items19[i19]).source_type).value.variant_0).has_byte_count = true;
                            }                             else if (cJSON_IsNull(field22)) {
                                ((items19[i19]).source_type).tag = 1;
                                (((items19[i19]).source_type).value.variant_1).value = 0;
                            } else { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                        }
                    }
                    {
                        const cJSON *field23 = cJSON_GetObjectItemCaseSensitive(node19, "quantity");
                        if (field23) {
                            (items19[i19]).present_fields |= UINT64_C(1) << 3;
                            if (cJSON_IsString(field23)) {
                                ((items19[i19]).quantity).tag = 0;
                                if (!cJSON_IsString(field23)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                (((items19[i19]).quantity).value.variant_0).value = (field23)->valuestring;
                                (((items19[i19]).quantity).value.variant_0).byte_count = otc__jstr_len(field23);
                                (((items19[i19]).quantity).value.variant_0).has_byte_count = true;
                            }                             else if (cJSON_IsNull(field23)) {
                                ((items19[i19]).quantity).tag = 1;
                                (((items19[i19]).quantity).value.variant_1).value = 0;
                            } else { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                        }
                    }
                    {
                        const cJSON *field24 = cJSON_GetObjectItemCaseSensitive(node19, "qc_status");
                        if (field24) {
                            (items19[i19]).present_fields |= UINT64_C(1) << 4;
                            if (cJSON_IsString(field24)) {
                                ((items19[i19]).qc_status).tag = 0;
                                if (!cJSON_IsString(field24)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                (((items19[i19]).qc_status).value.variant_0).value = (field24)->valuestring;
                                (((items19[i19]).qc_status).value.variant_0).byte_count = otc__jstr_len(field24);
                                (((items19[i19]).qc_status).value.variant_0).has_byte_count = true;
                            }                             else if (cJSON_IsNull(field24)) {
                                ((items19[i19]).qc_status).tag = 1;
                                (((items19[i19]).qc_status).value.variant_1).value = 0;
                            } else { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                        }
                    }
                    {
                        const cJSON *field25 = cJSON_GetObjectItemCaseSensitive(node19, "convention_id");
                        if (field25) {
                            (items19[i19]).present_fields |= UINT64_C(1) << 5;
                            if (cJSON_IsString(field25)) {
                                ((items19[i19]).convention_id).tag = 0;
                                if (!cJSON_IsString(field25)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                (((items19[i19]).convention_id).value.variant_0).value = (field25)->valuestring;
                                (((items19[i19]).convention_id).value.variant_0).byte_count = otc__jstr_len(field25);
                                (((items19[i19]).convention_id).value.variant_0).has_byte_count = true;
                            }                             else if (cJSON_IsNull(field25)) {
                                ((items19[i19]).convention_id).tag = 1;
                                (((items19[i19]).convention_id).value.variant_1).value = 0;
                            } else { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                        }
                    }
                    {
                        const cJSON *field26 = cJSON_GetObjectItemCaseSensitive(node19, "licence_id");
                        if (field26) {
                            (items19[i19]).present_fields |= UINT64_C(1) << 6;
                            if (cJSON_IsString(field26)) {
                                ((items19[i19]).licence_id).tag = 0;
                                if (!cJSON_IsString(field26)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                (((items19[i19]).licence_id).value.variant_0).value = (field26)->valuestring;
                                (((items19[i19]).licence_id).value.variant_0).byte_count = otc__jstr_len(field26);
                                (((items19[i19]).licence_id).value.variant_0).has_byte_count = true;
                            }                             else if (cJSON_IsNull(field26)) {
                                ((items19[i19]).licence_id).tag = 1;
                                (((items19[i19]).licence_id).value.variant_1).value = 0;
                            } else { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                        }
                    }
                    {
                        const cJSON *field27 = cJSON_GetObjectItemCaseSensitive(node19, "constituents");
                        if (field27) {
                            (items19[i19]).present_fields |= UINT64_C(1) << 7;
                            if (!cJSON_IsArray(field27)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                            {
                                size_t i28 = 0, count = (size_t)cJSON_GetArraySize(field27);
                                const cJSON *node28;
                                otc_cp_station_index_entry_sets_item_constituents_item *items28 = canonical_index_alloc(owner, count, sizeof *items28);
                                if (!items28) { status = OTC_E_NOMEM; goto failure; }
                                ((items19[i19]).constituents).items = items28; ((items19[i19]).constituents).count = count;
                                cJSON_ArrayForEach(node28, field27) {
                                    if (!cJSON_IsString(node28)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                    (items28[i28]).value = (node28)->valuestring;
                                    (items28[i28]).byte_count = otc__jstr_len(node28);
                                    (items28[i28]).has_byte_count = true;
                                    i28++;
                                }
                            }
                        }
                    }
                    {
                        const cJSON *field29 = cJSON_GetObjectItemCaseSensitive(node19, "fallback");
                        if (field29) {
                            (items19[i19]).present_fields |= UINT64_C(1) << 8;
                            if (cJSON_IsObject(field29)) {
                                ((items19[i19]).fallback).tag = 0;
                                if (!cJSON_IsObject(field29)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                (((items19[i19]).fallback).value.variant_0).has_presence = true;
                                {
                                    const cJSON *field30 = cJSON_GetObjectItemCaseSensitive(field29, "reason");
                                    if (field30) {
                                        (((items19[i19]).fallback).value.variant_0).present_fields |= UINT64_C(1) << 0;
                                        if (!cJSON_IsString(field30)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                        ((((items19[i19]).fallback).value.variant_0).reason).value = (field30)->valuestring;
                                        ((((items19[i19]).fallback).value.variant_0).reason).byte_count = otc__jstr_len(field30);
                                        ((((items19[i19]).fallback).value.variant_0).reason).has_byte_count = true;
                                    }
                                }
                                {
                                    const cJSON *field31 = cJSON_GetObjectItemCaseSensitive(field29, "basis");
                                    if (field31) {
                                        (((items19[i19]).fallback).value.variant_0).present_fields |= UINT64_C(1) << 1;
                                        if (!cJSON_IsString(field31)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                        ((((items19[i19]).fallback).value.variant_0).basis).value = (field31)->valuestring;
                                        ((((items19[i19]).fallback).value.variant_0).basis).byte_count = otc__jstr_len(field31);
                                        ((((items19[i19]).fallback).value.variant_0).basis).has_byte_count = true;
                                    }
                                }
                                {
                                    const cJSON *field32 = cJSON_GetObjectItemCaseSensitive(field29, "otc_finding");
                                    if (field32) {
                                        (((items19[i19]).fallback).value.variant_0).present_fields |= UINT64_C(1) << 2;
                                        if (!cJSON_IsString(field32)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                        ((((items19[i19]).fallback).value.variant_0).otc_finding).value = (field32)->valuestring;
                                        ((((items19[i19]).fallback).value.variant_0).otc_finding).byte_count = otc__jstr_len(field32);
                                        ((((items19[i19]).fallback).value.variant_0).otc_finding).has_byte_count = true;
                                    }
                                }
                                {
                                    const cJSON *field33 = cJSON_GetObjectItemCaseSensitive(field29, "preferred_set_id");
                                    if (field33) {
                                        (((items19[i19]).fallback).value.variant_0).present_fields |= UINT64_C(1) << 3;
                                        if (!cJSON_IsString(field33)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                        ((((items19[i19]).fallback).value.variant_0).preferred_set_id).value = (field33)->valuestring;
                                        ((((items19[i19]).fallback).value.variant_0).preferred_set_id).byte_count = otc__jstr_len(field33);
                                        ((((items19[i19]).fallback).value.variant_0).preferred_set_id).has_byte_count = true;
                                    }
                                }
                                {
                                    const cJSON *extension34;
                                    size_t n = 0, i = 0;
                                    otc_cp_JsonValue_map_entry *entries34;
                                    cJSON_ArrayForEach(extension34, field29) if (strcmp(extension34->string, "reason") && strcmp(extension34->string, "basis") && strcmp(extension34->string, "otc_finding") && strcmp(extension34->string, "preferred_set_id")) n++;
                                    entries34 = canonical_index_alloc(owner, n, sizeof *entries34);
                                    if (!entries34) { status = OTC_E_NOMEM; goto failure; }
                                    (((items19[i19]).fallback).value.variant_0).extensions.entries = entries34; (((items19[i19]).fallback).value.variant_0).extensions.count = n;
                                    cJSON_ArrayForEach(extension34, field29) if (strcmp(extension34->string, "reason") && strcmp(extension34->string, "basis") && strcmp(extension34->string, "otc_finding") && strcmp(extension34->string, "preferred_set_id")) {
                                        entries34[i].key.value = extension34->string;
                                        status = canonical_native_json(owner, extension34, &entries34[i].value);
                                        if (status != OTC_OK) goto failure;
                                        i++;
                                    }
                                }
                            }                             else if (cJSON_IsNull(field29)) {
                                ((items19[i19]).fallback).tag = 1;
                                (((items19[i19]).fallback).value.variant_1).value = 0;
                            } else { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                        }
                    }
                    {
                        const cJSON *field35 = cJSON_GetObjectItemCaseSensitive(node19, "current_bins");
                        if (field35) {
                            (items19[i19]).present_fields |= UINT64_C(1) << 9;
                            if (!cJSON_IsArray(field35)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                            {
                                size_t i36 = 0, count = (size_t)cJSON_GetArraySize(field35);
                                const cJSON *node36;
                                otc_cp_station_index_entry_sets_item_current_bins_item *items36 = canonical_index_alloc(owner, count, sizeof *items36);
                                if (!items36) { status = OTC_E_NOMEM; goto failure; }
                                ((items19[i19]).current_bins).items = items36; ((items19[i19]).current_bins).count = count;
                                cJSON_ArrayForEach(node36, field35) {
                                    if (!cJSON_IsNumber(node36)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                    (items36[i36]).value = (int64_t)(node36)->valuedouble;
                                    i36++;
                                }
                            }
                        }
                    }
                    i19++;
                }
            }
        }
    }
    {
        const cJSON *field37 = cJSON_GetObjectItemCaseSensitive(owner->document, "subordinate_offsets");
        if (field37) {
            (result).present_fields |= UINT64_C(1) << 16;
            if (cJSON_IsObject(field37)) {
                ((result).subordinate_offsets).tag = 0;
                if (!cJSON_IsObject(field37)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                (((result).subordinate_offsets).value.variant_0).has_presence = true;
                {
                    const cJSON *field38 = cJSON_GetObjectItemCaseSensitive(field37, "reference_station_id");
                    if (field38) {
                        (((result).subordinate_offsets).value.variant_0).present_fields |= UINT64_C(1) << 0;
                        if (!cJSON_IsString(field38)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                        ((((result).subordinate_offsets).value.variant_0).reference_station_id).value = (field38)->valuestring;
                        ((((result).subordinate_offsets).value.variant_0).reference_station_id).byte_count = otc__jstr_len(field38);
                        ((((result).subordinate_offsets).value.variant_0).reference_station_id).has_byte_count = true;
                    }
                }
                {
                    const cJSON *field39 = cJSON_GetObjectItemCaseSensitive(field37, "time_offset_high_min");
                    if (field39) {
                        (((result).subordinate_offsets).value.variant_0).present_fields |= UINT64_C(1) << 1;
                        if (!cJSON_IsNumber(field39)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                        ((((result).subordinate_offsets).value.variant_0).time_offset_high_min).value = (double)(field39)->valuedouble;
                    }
                }
                {
                    const cJSON *field40 = cJSON_GetObjectItemCaseSensitive(field37, "time_offset_low_min");
                    if (field40) {
                        (((result).subordinate_offsets).value.variant_0).present_fields |= UINT64_C(1) << 2;
                        if (!cJSON_IsNumber(field40)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                        ((((result).subordinate_offsets).value.variant_0).time_offset_low_min).value = (double)(field40)->valuedouble;
                    }
                }
                {
                    const cJSON *field41 = cJSON_GetObjectItemCaseSensitive(field37, "height_offset_high");
                    if (field41) {
                        (((result).subordinate_offsets).value.variant_0).present_fields |= UINT64_C(1) << 3;
                        if (!cJSON_IsNumber(field41)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                        ((((result).subordinate_offsets).value.variant_0).height_offset_high).value = (double)(field41)->valuedouble;
                    }
                }
                {
                    const cJSON *field42 = cJSON_GetObjectItemCaseSensitive(field37, "height_offset_low");
                    if (field42) {
                        (((result).subordinate_offsets).value.variant_0).present_fields |= UINT64_C(1) << 4;
                        if (!cJSON_IsNumber(field42)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                        ((((result).subordinate_offsets).value.variant_0).height_offset_low).value = (double)(field42)->valuedouble;
                    }
                }
                {
                    const cJSON *field43 = cJSON_GetObjectItemCaseSensitive(field37, "height_adjusted_type");
                    if (field43) {
                        (((result).subordinate_offsets).value.variant_0).present_fields |= UINT64_C(1) << 5;
                        if (!cJSON_IsString(field43)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                        ((((result).subordinate_offsets).value.variant_0).height_adjusted_type).value = (field43)->valuestring;
                        ((((result).subordinate_offsets).value.variant_0).height_adjusted_type).byte_count = otc__jstr_len(field43);
                        ((((result).subordinate_offsets).value.variant_0).height_adjusted_type).has_byte_count = true;
                    }
                }
                {
                    const cJSON *field44 = cJSON_GetObjectItemCaseSensitive(field37, "licence_id");
                    if (field44) {
                        (((result).subordinate_offsets).value.variant_0).present_fields |= UINT64_C(1) << 6;
                        if (!cJSON_IsString(field44)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                        ((((result).subordinate_offsets).value.variant_0).licence_id).value = (field44)->valuestring;
                        ((((result).subordinate_offsets).value.variant_0).licence_id).byte_count = otc__jstr_len(field44);
                        ((((result).subordinate_offsets).value.variant_0).licence_id).has_byte_count = true;
                    }
                }
                {
                    const cJSON *field45 = cJSON_GetObjectItemCaseSensitive(field37, "datum");
                    if (field45) {
                        (((result).subordinate_offsets).value.variant_0).present_fields |= UINT64_C(1) << 7;
                        if (!cJSON_IsString(field45)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                        ((((result).subordinate_offsets).value.variant_0).datum).value = (field45)->valuestring;
                        ((((result).subordinate_offsets).value.variant_0).datum).byte_count = otc__jstr_len(field45);
                        ((((result).subordinate_offsets).value.variant_0).datum).has_byte_count = true;
                    }
                }
                {
                    const cJSON *field46 = cJSON_GetObjectItemCaseSensitive(field37, "offset_id");
                    if (field46) {
                        (((result).subordinate_offsets).value.variant_0).present_fields |= UINT64_C(1) << 8;
                        if (!cJSON_IsString(field46)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                        ((((result).subordinate_offsets).value.variant_0).offset_id).value = (field46)->valuestring;
                        ((((result).subordinate_offsets).value.variant_0).offset_id).byte_count = otc__jstr_len(field46);
                        ((((result).subordinate_offsets).value.variant_0).offset_id).has_byte_count = true;
                    }
                }
                {
                    const cJSON *field47 = cJSON_GetObjectItemCaseSensitive(field37, "source");
                    if (field47) {
                        (((result).subordinate_offsets).value.variant_0).present_fields |= UINT64_C(1) << 9;
                        if (!cJSON_IsString(field47)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                        ((((result).subordinate_offsets).value.variant_0).source).value = (field47)->valuestring;
                        ((((result).subordinate_offsets).value.variant_0).source).byte_count = otc__jstr_len(field47);
                        ((((result).subordinate_offsets).value.variant_0).source).has_byte_count = true;
                    }
                }
                {
                    const cJSON *field48 = cJSON_GetObjectItemCaseSensitive(field37, "source_type");
                    if (field48) {
                        (((result).subordinate_offsets).value.variant_0).present_fields |= UINT64_C(1) << 10;
                        if (!cJSON_IsString(field48)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                        ((((result).subordinate_offsets).value.variant_0).source_type).value = (field48)->valuestring;
                        ((((result).subordinate_offsets).value.variant_0).source_type).byte_count = otc__jstr_len(field48);
                        ((((result).subordinate_offsets).value.variant_0).source_type).has_byte_count = true;
                    }
                }
                {
                    const cJSON *field49 = cJSON_GetObjectItemCaseSensitive(field37, "source_version");
                    if (field49) {
                        (((result).subordinate_offsets).value.variant_0).present_fields |= UINT64_C(1) << 11;
                        if (!cJSON_IsString(field49)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                        ((((result).subordinate_offsets).value.variant_0).source_version).value = (field49)->valuestring;
                        ((((result).subordinate_offsets).value.variant_0).source_version).byte_count = otc__jstr_len(field49);
                        ((((result).subordinate_offsets).value.variant_0).source_version).has_byte_count = true;
                    }
                }
                {
                    const cJSON *field50 = cJSON_GetObjectItemCaseSensitive(field37, "source_record_id");
                    if (field50) {
                        (((result).subordinate_offsets).value.variant_0).present_fields |= UINT64_C(1) << 12;
                        if (!cJSON_IsString(field50)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                        ((((result).subordinate_offsets).value.variant_0).source_record_id).value = (field50)->valuestring;
                        ((((result).subordinate_offsets).value.variant_0).source_record_id).byte_count = otc__jstr_len(field50);
                        ((((result).subordinate_offsets).value.variant_0).source_record_id).has_byte_count = true;
                    }
                }
                {
                    const cJSON *field51 = cJSON_GetObjectItemCaseSensitive(field37, "qc_status");
                    if (field51) {
                        (((result).subordinate_offsets).value.variant_0).present_fields |= UINT64_C(1) << 13;
                        if (!cJSON_IsString(field51)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                        ((((result).subordinate_offsets).value.variant_0).qc_status).value = (field51)->valuestring;
                        ((((result).subordinate_offsets).value.variant_0).qc_status).byte_count = otc__jstr_len(field51);
                        ((((result).subordinate_offsets).value.variant_0).qc_status).has_byte_count = true;
                    }
                }
                {
                    const cJSON *field52 = cJSON_GetObjectItemCaseSensitive(field37, "qc_flags");
                    if (field52) {
                        (((result).subordinate_offsets).value.variant_0).present_fields |= UINT64_C(1) << 14;
                        if (!cJSON_IsArray(field52)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                        {
                            size_t i53 = 0, count = (size_t)cJSON_GetArraySize(field52);
                            const cJSON *node53;
                            otc_cp_station_index_entry_subordinate_offsets_variant_0_qc_flags_item *items53 = canonical_index_alloc(owner, count, sizeof *items53);
                            if (!items53) { status = OTC_E_NOMEM; goto failure; }
                            ((((result).subordinate_offsets).value.variant_0).qc_flags).items = items53; ((((result).subordinate_offsets).value.variant_0).qc_flags).count = count;
                            cJSON_ArrayForEach(node53, field52) {
                                if (!cJSON_IsObject(node53)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                (items53[i53]).has_presence = true;
                                {
                                    const cJSON *field54 = cJSON_GetObjectItemCaseSensitive(node53, "flag");
                                    if (field54) {
                                        (items53[i53]).present_fields |= UINT64_C(1) << 0;
                                        if (!cJSON_IsString(field54)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                        ((items53[i53]).flag).value = (field54)->valuestring;
                                        ((items53[i53]).flag).byte_count = otc__jstr_len(field54);
                                        ((items53[i53]).flag).has_byte_count = true;
                                    }
                                }
                                {
                                    const cJSON *field55 = cJSON_GetObjectItemCaseSensitive(node53, "reason");
                                    if (field55) {
                                        (items53[i53]).present_fields |= UINT64_C(1) << 1;
                                        if (!cJSON_IsString(field55)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                        ((items53[i53]).reason).value = (field55)->valuestring;
                                        ((items53[i53]).reason).byte_count = otc__jstr_len(field55);
                                        ((items53[i53]).reason).has_byte_count = true;
                                    }
                                }
                                {
                                    const cJSON *field56 = cJSON_GetObjectItemCaseSensitive(node53, "values");
                                    if (field56) {
                                        (items53[i53]).present_fields |= UINT64_C(1) << 2;
                                        status = canonical_native_json(owner, field56, &((items53[i53]).values));
                                        if (status != OTC_OK) goto failure;
                                    }
                                }
                                {
                                    const cJSON *extension57;
                                    size_t n = 0, i = 0;
                                    otc_cp_JsonValue_map_entry *entries57;
                                    cJSON_ArrayForEach(extension57, node53) if (strcmp(extension57->string, "flag") && strcmp(extension57->string, "reason") && strcmp(extension57->string, "values")) n++;
                                    entries57 = canonical_index_alloc(owner, n, sizeof *entries57);
                                    if (!entries57) { status = OTC_E_NOMEM; goto failure; }
                                    (items53[i53]).extensions.entries = entries57; (items53[i53]).extensions.count = n;
                                    cJSON_ArrayForEach(extension57, node53) if (strcmp(extension57->string, "flag") && strcmp(extension57->string, "reason") && strcmp(extension57->string, "values")) {
                                        entries57[i].key.value = extension57->string;
                                        status = canonical_native_json(owner, extension57, &entries57[i].value);
                                        if (status != OTC_OK) goto failure;
                                        i++;
                                    }
                                }
                                i53++;
                            }
                        }
                    }
                }
                {
                    const cJSON *field58 = cJSON_GetObjectItemCaseSensitive(field37, "fallback");
                    if (field58) {
                        (((result).subordinate_offsets).value.variant_0).present_fields |= UINT64_C(1) << 15;
                        if (!cJSON_IsObject(field58)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                        ((((result).subordinate_offsets).value.variant_0).fallback).has_presence = true;
                        {
                            const cJSON *field59 = cJSON_GetObjectItemCaseSensitive(field58, "reason");
                            if (field59) {
                                ((((result).subordinate_offsets).value.variant_0).fallback).present_fields |= UINT64_C(1) << 0;
                                if (!cJSON_IsString(field59)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                (((((result).subordinate_offsets).value.variant_0).fallback).reason).value = (field59)->valuestring;
                                (((((result).subordinate_offsets).value.variant_0).fallback).reason).byte_count = otc__jstr_len(field59);
                                (((((result).subordinate_offsets).value.variant_0).fallback).reason).has_byte_count = true;
                            }
                        }
                        {
                            const cJSON *field60 = cJSON_GetObjectItemCaseSensitive(field58, "basis");
                            if (field60) {
                                ((((result).subordinate_offsets).value.variant_0).fallback).present_fields |= UINT64_C(1) << 1;
                                if (!cJSON_IsString(field60)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                (((((result).subordinate_offsets).value.variant_0).fallback).basis).value = (field60)->valuestring;
                                (((((result).subordinate_offsets).value.variant_0).fallback).basis).byte_count = otc__jstr_len(field60);
                                (((((result).subordinate_offsets).value.variant_0).fallback).basis).has_byte_count = true;
                            }
                        }
                        {
                            const cJSON *field61 = cJSON_GetObjectItemCaseSensitive(field58, "otc_finding");
                            if (field61) {
                                ((((result).subordinate_offsets).value.variant_0).fallback).present_fields |= UINT64_C(1) << 2;
                                if (!cJSON_IsString(field61)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                (((((result).subordinate_offsets).value.variant_0).fallback).otc_finding).value = (field61)->valuestring;
                                (((((result).subordinate_offsets).value.variant_0).fallback).otc_finding).byte_count = otc__jstr_len(field61);
                                (((((result).subordinate_offsets).value.variant_0).fallback).otc_finding).has_byte_count = true;
                            }
                        }
                        {
                            const cJSON *field62 = cJSON_GetObjectItemCaseSensitive(field58, "preferred_set_id");
                            if (field62) {
                                ((((result).subordinate_offsets).value.variant_0).fallback).present_fields |= UINT64_C(1) << 3;
                                if (!cJSON_IsString(field62)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                (((((result).subordinate_offsets).value.variant_0).fallback).preferred_set_id).value = (field62)->valuestring;
                                (((((result).subordinate_offsets).value.variant_0).fallback).preferred_set_id).byte_count = otc__jstr_len(field62);
                                (((((result).subordinate_offsets).value.variant_0).fallback).preferred_set_id).has_byte_count = true;
                            }
                        }
                        {
                            const cJSON *extension63;
                            size_t n = 0, i = 0;
                            otc_cp_JsonValue_map_entry *entries63;
                            cJSON_ArrayForEach(extension63, field58) if (strcmp(extension63->string, "reason") && strcmp(extension63->string, "basis") && strcmp(extension63->string, "otc_finding") && strcmp(extension63->string, "preferred_set_id")) n++;
                            entries63 = canonical_index_alloc(owner, n, sizeof *entries63);
                            if (!entries63) { status = OTC_E_NOMEM; goto failure; }
                            ((((result).subordinate_offsets).value.variant_0).fallback).extensions.entries = entries63; ((((result).subordinate_offsets).value.variant_0).fallback).extensions.count = n;
                            cJSON_ArrayForEach(extension63, field58) if (strcmp(extension63->string, "reason") && strcmp(extension63->string, "basis") && strcmp(extension63->string, "otc_finding") && strcmp(extension63->string, "preferred_set_id")) {
                                entries63[i].key.value = extension63->string;
                                status = canonical_native_json(owner, extension63, &entries63[i].value);
                                if (status != OTC_OK) goto failure;
                                i++;
                            }
                        }
                    }
                }
                {
                    const cJSON *field64 = cJSON_GetObjectItemCaseSensitive(field37, "vintage");
                    if (field64) {
                        (((result).subordinate_offsets).value.variant_0).present_fields |= UINT64_C(1) << 16;
                        if (!cJSON_IsObject(field64)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                        ((((result).subordinate_offsets).value.variant_0).vintage).has_presence = true;
                        {
                            const cJSON *field65 = cJSON_GetObjectItemCaseSensitive(field64, "publication_year");
                            if (field65) {
                                ((((result).subordinate_offsets).value.variant_0).vintage).present_fields |= UINT64_C(1) << 0;
                                if (!cJSON_IsNumber(field65)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                (((((result).subordinate_offsets).value.variant_0).vintage).publication_year).value = (int64_t)(field65)->valuedouble;
                            }
                        }
                        {
                            const cJSON *field66 = cJSON_GetObjectItemCaseSensitive(field64, "source_lifecycle");
                            if (field66) {
                                ((((result).subordinate_offsets).value.variant_0).vintage).present_fields |= UINT64_C(1) << 1;
                                if (!cJSON_IsString(field66)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                (((((result).subordinate_offsets).value.variant_0).vintage).source_lifecycle).value = (field66)->valuestring;
                                (((((result).subordinate_offsets).value.variant_0).vintage).source_lifecycle).byte_count = otc__jstr_len(field66);
                                (((((result).subordinate_offsets).value.variant_0).vintage).source_lifecycle).has_byte_count = true;
                            }
                        }
                        {
                            const cJSON *field67 = cJSON_GetObjectItemCaseSensitive(field64, "removal_events");
                            if (field67) {
                                ((((result).subordinate_offsets).value.variant_0).vintage).present_fields |= UINT64_C(1) << 2;
                                if (!cJSON_IsArray(field67)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                {
                                    size_t i68 = 0, count = (size_t)cJSON_GetArraySize(field67);
                                    const cJSON *node68;
                                    otc_cp_station_index_entry_subordinate_offsets_variant_0_vintage_removal_events_item *items68 = canonical_index_alloc(owner, count, sizeof *items68);
                                    if (!items68) { status = OTC_E_NOMEM; goto failure; }
                                    (((((result).subordinate_offsets).value.variant_0).vintage).removal_events).items = items68; (((((result).subordinate_offsets).value.variant_0).vintage).removal_events).count = count;
                                    cJSON_ArrayForEach(node68, field67) {
                                        if (!cJSON_IsObject(node68)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                        (items68[i68]).has_presence = true;
                                        {
                                            const cJSON *field69 = cJSON_GetObjectItemCaseSensitive(node68, "source_clock_timestamp");
                                            if (field69) {
                                                (items68[i68]).present_fields |= UINT64_C(1) << 0;
                                                if (!cJSON_IsString(field69)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                                ((items68[i68]).source_clock_timestamp).value = (field69)->valuestring;
                                                ((items68[i68]).source_clock_timestamp).byte_count = otc__jstr_len(field69);
                                                ((items68[i68]).source_clock_timestamp).has_byte_count = true;
                                            }
                                        }
                                        {
                                            const cJSON *field70 = cJSON_GetObjectItemCaseSensitive(node68, "name");
                                            if (field70) {
                                                (items68[i68]).present_fields |= UINT64_C(1) << 1;
                                                if (!cJSON_IsString(field70)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                                ((items68[i68]).name).value = (field70)->valuestring;
                                                ((items68[i68]).name).byte_count = otc__jstr_len(field70);
                                                ((items68[i68]).name).has_byte_count = true;
                                            }
                                        }
                                        {
                                            const cJSON *field71 = cJSON_GetObjectItemCaseSensitive(node68, "operation");
                                            if (field71) {
                                                (items68[i68]).present_fields |= UINT64_C(1) << 2;
                                                if (!cJSON_IsString(field71)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                                ((items68[i68]).operation).value = (field71)->valuestring;
                                                ((items68[i68]).operation).byte_count = otc__jstr_len(field71);
                                                ((items68[i68]).operation).has_byte_count = true;
                                            }
                                        }
                                        {
                                            const cJSON *field72 = cJSON_GetObjectItemCaseSensitive(node68, "source_timezone");
                                            if (field72) {
                                                (items68[i68]).present_fields |= UINT64_C(1) << 3;
                                                if (!cJSON_IsString(field72)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                                ((items68[i68]).source_timezone).value = (field72)->valuestring;
                                                ((items68[i68]).source_timezone).byte_count = otc__jstr_len(field72);
                                                ((items68[i68]).source_timezone).has_byte_count = true;
                                            }
                                        }
                                        {
                                            const cJSON *field73 = cJSON_GetObjectItemCaseSensitive(node68, "evidence_sha256");
                                            if (field73) {
                                                (items68[i68]).present_fields |= UINT64_C(1) << 4;
                                                if (!cJSON_IsString(field73)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                                ((items68[i68]).evidence_sha256).value = (field73)->valuestring;
                                                ((items68[i68]).evidence_sha256).byte_count = otc__jstr_len(field73);
                                                ((items68[i68]).evidence_sha256).has_byte_count = true;
                                            }
                                        }
                                        {
                                            const cJSON *extension74;
                                            size_t n = 0, i = 0;
                                            otc_cp_JsonValue_map_entry *entries74;
                                            cJSON_ArrayForEach(extension74, node68) if (strcmp(extension74->string, "source_clock_timestamp") && strcmp(extension74->string, "name") && strcmp(extension74->string, "operation") && strcmp(extension74->string, "source_timezone") && strcmp(extension74->string, "evidence_sha256")) n++;
                                            entries74 = canonical_index_alloc(owner, n, sizeof *entries74);
                                            if (!entries74) { status = OTC_E_NOMEM; goto failure; }
                                            (items68[i68]).extensions.entries = entries74; (items68[i68]).extensions.count = n;
                                            cJSON_ArrayForEach(extension74, node68) if (strcmp(extension74->string, "source_clock_timestamp") && strcmp(extension74->string, "name") && strcmp(extension74->string, "operation") && strcmp(extension74->string, "source_timezone") && strcmp(extension74->string, "evidence_sha256")) {
                                                entries74[i].key.value = extension74->string;
                                                status = canonical_native_json(owner, extension74, &entries74[i].value);
                                                if (status != OTC_OK) goto failure;
                                                i++;
                                            }
                                        }
                                        i68++;
                                    }
                                }
                            }
                        }
                        {
                            const cJSON *field75 = cJSON_GetObjectItemCaseSensitive(field64, "current_validity");
                            if (field75) {
                                ((((result).subordinate_offsets).value.variant_0).vintage).present_fields |= UINT64_C(1) << 3;
                                if (!cJSON_IsString(field75)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                (((((result).subordinate_offsets).value.variant_0).vintage).current_validity).value = (field75)->valuestring;
                                (((((result).subordinate_offsets).value.variant_0).vintage).current_validity).byte_count = otc__jstr_len(field75);
                                (((((result).subordinate_offsets).value.variant_0).vintage).current_validity).has_byte_count = true;
                            }
                        }
                        {
                            const cJSON *field76 = cJSON_GetObjectItemCaseSensitive(field64, "current_accuracy");
                            if (field76) {
                                ((((result).subordinate_offsets).value.variant_0).vintage).present_fields |= UINT64_C(1) << 4;
                                if (!cJSON_IsString(field76)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                (((((result).subordinate_offsets).value.variant_0).vintage).current_accuracy).value = (field76)->valuestring;
                                (((((result).subordinate_offsets).value.variant_0).vintage).current_accuracy).byte_count = otc__jstr_len(field76);
                                (((((result).subordinate_offsets).value.variant_0).vintage).current_accuracy).has_byte_count = true;
                            }
                        }
                        {
                            const cJSON *field77 = cJSON_GetObjectItemCaseSensitive(field64, "reference_2020_equivalence");
                            if (field77) {
                                ((((result).subordinate_offsets).value.variant_0).vintage).present_fields |= UINT64_C(1) << 5;
                                if (!cJSON_IsString(field77)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                (((((result).subordinate_offsets).value.variant_0).vintage).reference_2020_equivalence).value = (field77)->valuestring;
                                (((((result).subordinate_offsets).value.variant_0).vintage).reference_2020_equivalence).byte_count = otc__jstr_len(field77);
                                (((((result).subordinate_offsets).value.variant_0).vintage).reference_2020_equivalence).has_byte_count = true;
                            }
                        }
                        {
                            const cJSON *field78 = cJSON_GetObjectItemCaseSensitive(field64, "reference_2020_equivalence_sha256");
                            if (field78) {
                                ((((result).subordinate_offsets).value.variant_0).vintage).present_fields |= UINT64_C(1) << 6;
                                if (!cJSON_IsString(field78)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                (((((result).subordinate_offsets).value.variant_0).vintage).reference_2020_equivalence_sha256).value = (field78)->valuestring;
                                (((((result).subordinate_offsets).value.variant_0).vintage).reference_2020_equivalence_sha256).byte_count = otc__jstr_len(field78);
                                (((((result).subordinate_offsets).value.variant_0).vintage).reference_2020_equivalence_sha256).has_byte_count = true;
                            }
                        }
                        {
                            const cJSON *extension79;
                            size_t n = 0, i = 0;
                            otc_cp_JsonValue_map_entry *entries79;
                            cJSON_ArrayForEach(extension79, field64) if (strcmp(extension79->string, "publication_year") && strcmp(extension79->string, "source_lifecycle") && strcmp(extension79->string, "removal_events") && strcmp(extension79->string, "current_validity") && strcmp(extension79->string, "current_accuracy") && strcmp(extension79->string, "reference_2020_equivalence") && strcmp(extension79->string, "reference_2020_equivalence_sha256")) n++;
                            entries79 = canonical_index_alloc(owner, n, sizeof *entries79);
                            if (!entries79) { status = OTC_E_NOMEM; goto failure; }
                            ((((result).subordinate_offsets).value.variant_0).vintage).extensions.entries = entries79; ((((result).subordinate_offsets).value.variant_0).vintage).extensions.count = n;
                            cJSON_ArrayForEach(extension79, field64) if (strcmp(extension79->string, "publication_year") && strcmp(extension79->string, "source_lifecycle") && strcmp(extension79->string, "removal_events") && strcmp(extension79->string, "current_validity") && strcmp(extension79->string, "current_accuracy") && strcmp(extension79->string, "reference_2020_equivalence") && strcmp(extension79->string, "reference_2020_equivalence_sha256")) {
                                entries79[i].key.value = extension79->string;
                                status = canonical_native_json(owner, extension79, &entries79[i].value);
                                if (status != OTC_OK) goto failure;
                                i++;
                            }
                        }
                    }
                }
                {
                    const cJSON *field80 = cJSON_GetObjectItemCaseSensitive(field37, "provenance");
                    if (field80) {
                        (((result).subordinate_offsets).value.variant_0).present_fields |= UINT64_C(1) << 17;
                        if (!cJSON_IsObject(field80)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                        ((((result).subordinate_offsets).value.variant_0).provenance).has_presence = true;
                        {
                            const cJSON *field81 = cJSON_GetObjectItemCaseSensitive(field80, "source_manifest_sha256");
                            if (field81) {
                                ((((result).subordinate_offsets).value.variant_0).provenance).present_fields |= UINT64_C(1) << 0;
                                if (!cJSON_IsString(field81)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                (((((result).subordinate_offsets).value.variant_0).provenance).source_manifest_sha256).value = (field81)->valuestring;
                                (((((result).subordinate_offsets).value.variant_0).provenance).source_manifest_sha256).byte_count = otc__jstr_len(field81);
                                (((((result).subordinate_offsets).value.variant_0).provenance).source_manifest_sha256).has_byte_count = true;
                            }
                        }
                        {
                            const cJSON *field82 = cJSON_GetObjectItemCaseSensitive(field80, "input_sha256");
                            if (field82) {
                                ((((result).subordinate_offsets).value.variant_0).provenance).present_fields |= UINT64_C(1) << 1;
                                if (!cJSON_IsArray(field82)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                {
                                    size_t i83 = 0, count = (size_t)cJSON_GetArraySize(field82);
                                    const cJSON *node83;
                                    otc_cp_station_index_entry_subordinate_offsets_variant_0_provenance_input_sha256_item *items83 = canonical_index_alloc(owner, count, sizeof *items83);
                                    if (!items83) { status = OTC_E_NOMEM; goto failure; }
                                    (((((result).subordinate_offsets).value.variant_0).provenance).input_sha256).items = items83; (((((result).subordinate_offsets).value.variant_0).provenance).input_sha256).count = count;
                                    cJSON_ArrayForEach(node83, field82) {
                                        if (!cJSON_IsString(node83)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                        (items83[i83]).value = (node83)->valuestring;
                                        (items83[i83]).byte_count = otc__jstr_len(node83);
                                        (items83[i83]).has_byte_count = true;
                                        i83++;
                                    }
                                }
                            }
                        }
                        {
                            const cJSON *field84 = cJSON_GetObjectItemCaseSensitive(field80, "book");
                            if (field84) {
                                ((((result).subordinate_offsets).value.variant_0).provenance).present_fields |= UINT64_C(1) << 2;
                                if (!cJSON_IsString(field84)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                (((((result).subordinate_offsets).value.variant_0).provenance).book).value = (field84)->valuestring;
                                (((((result).subordinate_offsets).value.variant_0).provenance).book).byte_count = otc__jstr_len(field84);
                                (((((result).subordinate_offsets).value.variant_0).provenance).book).has_byte_count = true;
                            }
                        }
                        {
                            const cJSON *field85 = cJSON_GetObjectItemCaseSensitive(field80, "annual_table_row");
                            if (field85) {
                                ((((result).subordinate_offsets).value.variant_0).provenance).present_fields |= UINT64_C(1) << 3;
                                if (!cJSON_IsNumber(field85)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                (((((result).subordinate_offsets).value.variant_0).provenance).annual_table_row).value = (int64_t)(field85)->valuedouble;
                            }
                        }
                        {
                            const cJSON *field86 = cJSON_GetObjectItemCaseSensitive(field80, "printed_page");
                            if (field86) {
                                ((((result).subordinate_offsets).value.variant_0).provenance).present_fields |= UINT64_C(1) << 4;
                                if (!cJSON_IsNumber(field86)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                (((((result).subordinate_offsets).value.variant_0).provenance).printed_page).value = (int64_t)(field86)->valuedouble;
                            }
                        }
                        {
                            const cJSON *field87 = cJSON_GetObjectItemCaseSensitive(field80, "pdf_page");
                            if (field87) {
                                ((((result).subordinate_offsets).value.variant_0).provenance).present_fields |= UINT64_C(1) << 5;
                                if (!cJSON_IsNumber(field87)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                (((((result).subordinate_offsets).value.variant_0).provenance).pdf_page).value = (int64_t)(field87)->valuedouble;
                            }
                        }
                        {
                            const cJSON *field88 = cJSON_GetObjectItemCaseSensitive(field80, "raw_row_text");
                            if (field88) {
                                ((((result).subordinate_offsets).value.variant_0).provenance).present_fields |= UINT64_C(1) << 6;
                                if (!cJSON_IsString(field88)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                (((((result).subordinate_offsets).value.variant_0).provenance).raw_row_text).value = (field88)->valuestring;
                                (((((result).subordinate_offsets).value.variant_0).provenance).raw_row_text).byte_count = otc__jstr_len(field88);
                                (((((result).subordinate_offsets).value.variant_0).provenance).raw_row_text).has_byte_count = true;
                            }
                        }
                        {
                            const cJSON *field89 = cJSON_GetObjectItemCaseSensitive(field80, "raw_values_json");
                            if (field89) {
                                ((((result).subordinate_offsets).value.variant_0).provenance).present_fields |= UINT64_C(1) << 7;
                                if (!cJSON_IsString(field89)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                (((((result).subordinate_offsets).value.variant_0).provenance).raw_values_json).value = (field89)->valuestring;
                                (((((result).subordinate_offsets).value.variant_0).provenance).raw_values_json).byte_count = otc__jstr_len(field89);
                                (((((result).subordinate_offsets).value.variant_0).provenance).raw_values_json).has_byte_count = true;
                            }
                        }
                        {
                            const cJSON *field90 = cJSON_GetObjectItemCaseSensitive(field80, "id_crosswalk");
                            if (field90) {
                                ((((result).subordinate_offsets).value.variant_0).provenance).present_fields |= UINT64_C(1) << 8;
                                if (!cJSON_IsObject(field90)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                (((((result).subordinate_offsets).value.variant_0).provenance).id_crosswalk).has_presence = true;
                                {
                                    const cJSON *field91 = cJSON_GetObjectItemCaseSensitive(field90, "legacy_id");
                                    if (field91) {
                                        (((((result).subordinate_offsets).value.variant_0).provenance).id_crosswalk).present_fields |= UINT64_C(1) << 0;
                                        if (!cJSON_IsString(field91)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                        ((((((result).subordinate_offsets).value.variant_0).provenance).id_crosswalk).legacy_id).value = (field91)->valuestring;
                                        ((((((result).subordinate_offsets).value.variant_0).provenance).id_crosswalk).legacy_id).byte_count = otc__jstr_len(field91);
                                        ((((((result).subordinate_offsets).value.variant_0).provenance).id_crosswalk).legacy_id).has_byte_count = true;
                                    }
                                }
                                {
                                    const cJSON *field92 = cJSON_GetObjectItemCaseSensitive(field90, "status");
                                    if (field92) {
                                        (((((result).subordinate_offsets).value.variant_0).provenance).id_crosswalk).present_fields |= UINT64_C(1) << 1;
                                        if (!cJSON_IsString(field92)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                        ((((((result).subordinate_offsets).value.variant_0).provenance).id_crosswalk).status).value = (field92)->valuestring;
                                        ((((((result).subordinate_offsets).value.variant_0).provenance).id_crosswalk).status).byte_count = otc__jstr_len(field92);
                                        ((((((result).subordinate_offsets).value.variant_0).provenance).id_crosswalk).status).has_byte_count = true;
                                    }
                                }
                                {
                                    const cJSON *field93 = cJSON_GetObjectItemCaseSensitive(field90, "modern_alias_verified");
                                    if (field93) {
                                        (((((result).subordinate_offsets).value.variant_0).provenance).id_crosswalk).present_fields |= UINT64_C(1) << 2;
                                        if (!cJSON_IsString(field93)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                        ((((((result).subordinate_offsets).value.variant_0).provenance).id_crosswalk).modern_alias_verified).value = (field93)->valuestring;
                                        ((((((result).subordinate_offsets).value.variant_0).provenance).id_crosswalk).modern_alias_verified).byte_count = otc__jstr_len(field93);
                                        ((((((result).subordinate_offsets).value.variant_0).provenance).id_crosswalk).modern_alias_verified).has_byte_count = true;
                                    }
                                }
                                {
                                    const cJSON *field94 = cJSON_GetObjectItemCaseSensitive(field90, "evidence_sha256");
                                    if (field94) {
                                        (((((result).subordinate_offsets).value.variant_0).provenance).id_crosswalk).present_fields |= UINT64_C(1) << 3;
                                        if (!cJSON_IsArray(field94)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                        {
                                            size_t i95 = 0, count = (size_t)cJSON_GetArraySize(field94);
                                            const cJSON *node95;
                                            otc_cp_station_index_entry_subordinate_offsets_variant_0_provenance_id_crosswalk_evidence_sha256_item *items95 = canonical_index_alloc(owner, count, sizeof *items95);
                                            if (!items95) { status = OTC_E_NOMEM; goto failure; }
                                            ((((((result).subordinate_offsets).value.variant_0).provenance).id_crosswalk).evidence_sha256).items = items95; ((((((result).subordinate_offsets).value.variant_0).provenance).id_crosswalk).evidence_sha256).count = count;
                                            cJSON_ArrayForEach(node95, field94) {
                                                if (!cJSON_IsString(node95)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                                (items95[i95]).value = (node95)->valuestring;
                                                (items95[i95]).byte_count = otc__jstr_len(node95);
                                                (items95[i95]).has_byte_count = true;
                                                i95++;
                                            }
                                        }
                                    }
                                }
                                {
                                    const cJSON *extension96;
                                    size_t n = 0, i = 0;
                                    otc_cp_JsonValue_map_entry *entries96;
                                    cJSON_ArrayForEach(extension96, field90) if (strcmp(extension96->string, "legacy_id") && strcmp(extension96->string, "status") && strcmp(extension96->string, "modern_alias_verified") && strcmp(extension96->string, "evidence_sha256")) n++;
                                    entries96 = canonical_index_alloc(owner, n, sizeof *entries96);
                                    if (!entries96) { status = OTC_E_NOMEM; goto failure; }
                                    (((((result).subordinate_offsets).value.variant_0).provenance).id_crosswalk).extensions.entries = entries96; (((((result).subordinate_offsets).value.variant_0).provenance).id_crosswalk).extensions.count = n;
                                    cJSON_ArrayForEach(extension96, field90) if (strcmp(extension96->string, "legacy_id") && strcmp(extension96->string, "status") && strcmp(extension96->string, "modern_alias_verified") && strcmp(extension96->string, "evidence_sha256")) {
                                        entries96[i].key.value = extension96->string;
                                        status = canonical_native_json(owner, extension96, &entries96[i].value);
                                        if (status != OTC_OK) goto failure;
                                        i++;
                                    }
                                }
                            }
                        }
                        {
                            const cJSON *field97 = cJSON_GetObjectItemCaseSensitive(field80, "reference_binding");
                            if (field97) {
                                ((((result).subordinate_offsets).value.variant_0).provenance).present_fields |= UINT64_C(1) << 9;
                                if (!cJSON_IsObject(field97)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                (((((result).subordinate_offsets).value.variant_0).provenance).reference_binding).has_presence = true;
                                {
                                    const cJSON *field98 = cJSON_GetObjectItemCaseSensitive(field97, "noaa_id");
                                    if (field98) {
                                        (((((result).subordinate_offsets).value.variant_0).provenance).reference_binding).present_fields |= UINT64_C(1) << 0;
                                        if (!cJSON_IsString(field98)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                        ((((((result).subordinate_offsets).value.variant_0).provenance).reference_binding).noaa_id).value = (field98)->valuestring;
                                        ((((((result).subordinate_offsets).value.variant_0).provenance).reference_binding).noaa_id).byte_count = otc__jstr_len(field98);
                                        ((((((result).subordinate_offsets).value.variant_0).provenance).reference_binding).noaa_id).has_byte_count = true;
                                    }
                                }
                                {
                                    const cJSON *field99 = cJSON_GetObjectItemCaseSensitive(field97, "station_id");
                                    if (field99) {
                                        (((((result).subordinate_offsets).value.variant_0).provenance).reference_binding).present_fields |= UINT64_C(1) << 1;
                                        if (!cJSON_IsString(field99)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                        ((((((result).subordinate_offsets).value.variant_0).provenance).reference_binding).station_id).value = (field99)->valuestring;
                                        ((((((result).subordinate_offsets).value.variant_0).provenance).reference_binding).station_id).byte_count = otc__jstr_len(field99);
                                        ((((((result).subordinate_offsets).value.variant_0).provenance).reference_binding).station_id).has_byte_count = true;
                                    }
                                }
                                {
                                    const cJSON *field100 = cJSON_GetObjectItemCaseSensitive(field97, "mapping_status");
                                    if (field100) {
                                        (((((result).subordinate_offsets).value.variant_0).provenance).reference_binding).present_fields |= UINT64_C(1) << 2;
                                        if (!cJSON_IsString(field100)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                        ((((((result).subordinate_offsets).value.variant_0).provenance).reference_binding).mapping_status).value = (field100)->valuestring;
                                        ((((((result).subordinate_offsets).value.variant_0).provenance).reference_binding).mapping_status).byte_count = otc__jstr_len(field100);
                                        ((((((result).subordinate_offsets).value.variant_0).provenance).reference_binding).mapping_status).has_byte_count = true;
                                    }
                                }
                                {
                                    const cJSON *field101 = cJSON_GetObjectItemCaseSensitive(field97, "evidence_sha256");
                                    if (field101) {
                                        (((((result).subordinate_offsets).value.variant_0).provenance).reference_binding).present_fields |= UINT64_C(1) << 3;
                                        if (!cJSON_IsArray(field101)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                        {
                                            size_t i102 = 0, count = (size_t)cJSON_GetArraySize(field101);
                                            const cJSON *node102;
                                            otc_cp_station_index_entry_subordinate_offsets_variant_0_provenance_reference_binding_evidence_sha256_item *items102 = canonical_index_alloc(owner, count, sizeof *items102);
                                            if (!items102) { status = OTC_E_NOMEM; goto failure; }
                                            ((((((result).subordinate_offsets).value.variant_0).provenance).reference_binding).evidence_sha256).items = items102; ((((((result).subordinate_offsets).value.variant_0).provenance).reference_binding).evidence_sha256).count = count;
                                            cJSON_ArrayForEach(node102, field101) {
                                                if (!cJSON_IsString(node102)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                                (items102[i102]).value = (node102)->valuestring;
                                                (items102[i102]).byte_count = otc__jstr_len(node102);
                                                (items102[i102]).has_byte_count = true;
                                                i102++;
                                            }
                                        }
                                    }
                                }
                                {
                                    const cJSON *extension103;
                                    size_t n = 0, i = 0;
                                    otc_cp_JsonValue_map_entry *entries103;
                                    cJSON_ArrayForEach(extension103, field97) if (strcmp(extension103->string, "noaa_id") && strcmp(extension103->string, "station_id") && strcmp(extension103->string, "mapping_status") && strcmp(extension103->string, "evidence_sha256")) n++;
                                    entries103 = canonical_index_alloc(owner, n, sizeof *entries103);
                                    if (!entries103) { status = OTC_E_NOMEM; goto failure; }
                                    (((((result).subordinate_offsets).value.variant_0).provenance).reference_binding).extensions.entries = entries103; (((((result).subordinate_offsets).value.variant_0).provenance).reference_binding).extensions.count = n;
                                    cJSON_ArrayForEach(extension103, field97) if (strcmp(extension103->string, "noaa_id") && strcmp(extension103->string, "station_id") && strcmp(extension103->string, "mapping_status") && strcmp(extension103->string, "evidence_sha256")) {
                                        entries103[i].key.value = extension103->string;
                                        status = canonical_native_json(owner, extension103, &entries103[i].value);
                                        if (status != OTC_OK) goto failure;
                                        i++;
                                    }
                                }
                            }
                        }
                        {
                            const cJSON *field104 = cJSON_GetObjectItemCaseSensitive(field80, "acceptance_report_sha256");
                            if (field104) {
                                ((((result).subordinate_offsets).value.variant_0).provenance).present_fields |= UINT64_C(1) << 10;
                                if (!cJSON_IsString(field104)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                (((((result).subordinate_offsets).value.variant_0).provenance).acceptance_report_sha256).value = (field104)->valuestring;
                                (((((result).subordinate_offsets).value.variant_0).provenance).acceptance_report_sha256).byte_count = otc__jstr_len(field104);
                                (((((result).subordinate_offsets).value.variant_0).provenance).acceptance_report_sha256).has_byte_count = true;
                            }
                        }
                        {
                            const cJSON *extension105;
                            size_t n = 0, i = 0;
                            otc_cp_JsonValue_map_entry *entries105;
                            cJSON_ArrayForEach(extension105, field80) if (strcmp(extension105->string, "source_manifest_sha256") && strcmp(extension105->string, "input_sha256") && strcmp(extension105->string, "book") && strcmp(extension105->string, "annual_table_row") && strcmp(extension105->string, "printed_page") && strcmp(extension105->string, "pdf_page") && strcmp(extension105->string, "raw_row_text") && strcmp(extension105->string, "raw_values_json") && strcmp(extension105->string, "id_crosswalk") && strcmp(extension105->string, "reference_binding") && strcmp(extension105->string, "acceptance_report_sha256")) n++;
                            entries105 = canonical_index_alloc(owner, n, sizeof *entries105);
                            if (!entries105) { status = OTC_E_NOMEM; goto failure; }
                            ((((result).subordinate_offsets).value.variant_0).provenance).extensions.entries = entries105; ((((result).subordinate_offsets).value.variant_0).provenance).extensions.count = n;
                            cJSON_ArrayForEach(extension105, field80) if (strcmp(extension105->string, "source_manifest_sha256") && strcmp(extension105->string, "input_sha256") && strcmp(extension105->string, "book") && strcmp(extension105->string, "annual_table_row") && strcmp(extension105->string, "printed_page") && strcmp(extension105->string, "pdf_page") && strcmp(extension105->string, "raw_row_text") && strcmp(extension105->string, "raw_values_json") && strcmp(extension105->string, "id_crosswalk") && strcmp(extension105->string, "reference_binding") && strcmp(extension105->string, "acceptance_report_sha256")) {
                                entries105[i].key.value = extension105->string;
                                status = canonical_native_json(owner, extension105, &entries105[i].value);
                                if (status != OTC_OK) goto failure;
                                i++;
                            }
                        }
                    }
                }
                {
                    const cJSON *extension106;
                    size_t n = 0, i = 0;
                    otc_cp_JsonValue_map_entry *entries106;
                    cJSON_ArrayForEach(extension106, field37) if (strcmp(extension106->string, "reference_station_id") && strcmp(extension106->string, "time_offset_high_min") && strcmp(extension106->string, "time_offset_low_min") && strcmp(extension106->string, "height_offset_high") && strcmp(extension106->string, "height_offset_low") && strcmp(extension106->string, "height_adjusted_type") && strcmp(extension106->string, "licence_id") && strcmp(extension106->string, "datum") && strcmp(extension106->string, "offset_id") && strcmp(extension106->string, "source") && strcmp(extension106->string, "source_type") && strcmp(extension106->string, "source_version") && strcmp(extension106->string, "source_record_id") && strcmp(extension106->string, "qc_status") && strcmp(extension106->string, "qc_flags") && strcmp(extension106->string, "fallback") && strcmp(extension106->string, "vintage") && strcmp(extension106->string, "provenance")) n++;
                    entries106 = canonical_index_alloc(owner, n, sizeof *entries106);
                    if (!entries106) { status = OTC_E_NOMEM; goto failure; }
                    (((result).subordinate_offsets).value.variant_0).extensions.entries = entries106; (((result).subordinate_offsets).value.variant_0).extensions.count = n;
                    cJSON_ArrayForEach(extension106, field37) if (strcmp(extension106->string, "reference_station_id") && strcmp(extension106->string, "time_offset_high_min") && strcmp(extension106->string, "time_offset_low_min") && strcmp(extension106->string, "height_offset_high") && strcmp(extension106->string, "height_offset_low") && strcmp(extension106->string, "height_adjusted_type") && strcmp(extension106->string, "licence_id") && strcmp(extension106->string, "datum") && strcmp(extension106->string, "offset_id") && strcmp(extension106->string, "source") && strcmp(extension106->string, "source_type") && strcmp(extension106->string, "source_version") && strcmp(extension106->string, "source_record_id") && strcmp(extension106->string, "qc_status") && strcmp(extension106->string, "qc_flags") && strcmp(extension106->string, "fallback") && strcmp(extension106->string, "vintage") && strcmp(extension106->string, "provenance")) {
                        entries106[i].key.value = extension106->string;
                        status = canonical_native_json(owner, extension106, &entries106[i].value);
                        if (status != OTC_OK) goto failure;
                        i++;
                    }
                }
            }             else if (cJSON_IsNull(field37)) {
                ((result).subordinate_offsets).tag = 1;
                (((result).subordinate_offsets).value.variant_1).value = 0;
            } else { status = OTC_E_INVALID_ARGUMENT; goto failure; }
        }
    }
    {
        const cJSON *field107 = cJSON_GetObjectItemCaseSensitive(owner->document, "current_offsets");
        if (field107) {
            (result).present_fields |= UINT64_C(1) << 17;
            if (!cJSON_IsArray(field107)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
            {
                size_t i108 = 0, count = (size_t)cJSON_GetArraySize(field107);
                const cJSON *node108;
                otc_cp_station_index_entry_current_offsets_item *items108 = canonical_index_alloc(owner, count, sizeof *items108);
                if (!items108) { status = OTC_E_NOMEM; goto failure; }
                ((result).current_offsets).items = items108; ((result).current_offsets).count = count;
                cJSON_ArrayForEach(node108, field107) {
                    if (!cJSON_IsObject(node108)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                    (items108[i108]).has_presence = true;
                    {
                        const cJSON *field109 = cJSON_GetObjectItemCaseSensitive(node108, "bin");
                        if (field109) {
                            (items108[i108]).present_fields |= UINT64_C(1) << 0;
                            if (!cJSON_IsNumber(field109)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                            ((items108[i108]).bin).value = (int64_t)(field109)->valuedouble;
                        }
                    }
                    {
                        const cJSON *field110 = cJSON_GetObjectItemCaseSensitive(node108, "reference_bin");
                        if (field110) {
                            (items108[i108]).present_fields |= UINT64_C(1) << 1;
                            if (!cJSON_IsNumber(field110)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                            ((items108[i108]).reference_bin).value = (int64_t)(field110)->valuedouble;
                        }
                    }
                    {
                        const cJSON *field111 = cJSON_GetObjectItemCaseSensitive(node108, "reference_station_id");
                        if (field111) {
                            (items108[i108]).present_fields |= UINT64_C(1) << 2;
                            if (cJSON_IsString(field111)) {
                                ((items108[i108]).reference_station_id).tag = 0;
                                if (!cJSON_IsString(field111)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                (((items108[i108]).reference_station_id).value.variant_0).value = (field111)->valuestring;
                                (((items108[i108]).reference_station_id).value.variant_0).byte_count = otc__jstr_len(field111);
                                (((items108[i108]).reference_station_id).value.variant_0).has_byte_count = true;
                            }                             else if (cJSON_IsNull(field111)) {
                                ((items108[i108]).reference_station_id).tag = 1;
                                (((items108[i108]).reference_station_id).value.variant_1).value = 0;
                            } else { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                        }
                    }
                    {
                        const cJSON *field112 = cJSON_GetObjectItemCaseSensitive(node108, "licence_id");
                        if (field112) {
                            (items108[i108]).present_fields |= UINT64_C(1) << 3;
                            if (cJSON_IsString(field112)) {
                                ((items108[i108]).licence_id).tag = 0;
                                if (!cJSON_IsString(field112)) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                                (((items108[i108]).licence_id).value.variant_0).value = (field112)->valuestring;
                                (((items108[i108]).licence_id).value.variant_0).byte_count = otc__jstr_len(field112);
                                (((items108[i108]).licence_id).value.variant_0).has_byte_count = true;
                            }                             else if (cJSON_IsNull(field112)) {
                                ((items108[i108]).licence_id).tag = 1;
                                (((items108[i108]).licence_id).value.variant_1).value = 0;
                            } else { status = OTC_E_INVALID_ARGUMENT; goto failure; }
                        }
                    }
                    i108++;
                }
            }
        }
    }
    result.native_owner = owner; *station_index_entry_out = result; return OTC_OK;
failure:
    canonical_index_owner_free(owner); return status;
}

otc_status otc__canonical_authenticate_station_index(const otc_cp_source_files *source_files, const otc_cp_supplied_index *supplied_index, const otc_cp_index_presence *index_presence, const otc_cp_reader_version *reader_version, otc_cp_authenticated_index *authenticated_index_out)
{
    (void)source_files;
    (void)supplied_index;
    (void)index_presence;
    (void)reader_version;
    (void)authenticated_index_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_compare_station_source(const otc_cp_index_entry *index_entry, const otc_cp_station_source_row *station_source_row, const otc_cp_index_presence *index_presence, otc_cp_compared_station_row *compared_station_row_out)
{
    (void)index_entry;
    (void)station_source_row;
    (void)index_presence;
    (void)compared_station_row_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_read_station_lazily(const otc_cp_stream_reader *stream_reader, const otc_cp_station_id *station_id, const otc_cp_release_origin *release_origin, const otc_cp_reader_version *reader_version, otc_cp_station_source_row *station_source_row_out)
{
    (void)stream_reader;
    (void)station_id;
    (void)release_origin;
    (void)reader_version;
    (void)station_source_row_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_encode_cache_json(const otc_cp_cache_document *cache_document, otc_cp_cache_bytes *cache_bytes_out)
{
    cJSON *native_document;
    char *encoded = NULL;
    otc_status status;
    if (!cache_bytes_out) return OTC_E_INVALID_ARGUMENT;
    cache_bytes_out->value = NULL; cache_bytes_out->count = 0;
    if (!cache_document) return OTC_E_INVALID_ARGUMENT;
    status = canonical_cache_document(cache_document, &native_document);
    if (status != OTC_OK) return status;
    status = otc__encode_cache_json(native_document, &encoded);
    cJSON_Delete(native_document);
    if (status == OTC_OK) { cache_bytes_out->value = (const unsigned char *)encoded; cache_bytes_out->count = strlen(encoded); }
    return status;
}

otc_status otc__canonical_lookup_station_identity(const otc_cp_release_view *release_view, const otc_cp_identity_query *identity_query, const otc_cp_reader_version *reader_version, otc_cp_station_or_tombstone_or_null *station_or_tombstone_or_null_out)
{
    (void)release_view;
    (void)identity_query;
    (void)reader_version;
    (void)station_or_tombstone_or_null_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_select_effective_recommendation(const otc_cp_station_sets *station_sets, const otc_cp_original_recommendation *original_recommendation, const otc_cp_commercial_only *commercial_only, otc_cp_effective_recommendation *effective_recommendation_out)
{
    (void)station_sets;
    (void)original_recommendation;
    (void)commercial_only;
    (void)effective_recommendation_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_admit_quality_path(const otc_cp_candidate_path *candidate_path, const otc_cp_include_flagged *include_flagged, const otc_cp_include_fallback *include_fallback, otc_cp_quality_admission *quality_admission_out)
{
    (void)candidate_path;
    (void)include_flagged;
    (void)include_fallback;
    (void)quality_admission_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_admit_commercial_path(const otc_cp_candidate_path *candidate_path, const otc_cp_commercial_only *commercial_only, const otc_cp_commercial_basis *commercial_basis, otc_cp_commercial_admission *commercial_admission_out)
{
    (void)candidate_path;
    (void)commercial_only;
    (void)commercial_basis;
    (void)commercial_admission_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_resolve_reference_path(const otc_cp_station_source_row *station_source_row, const otc_cp_path_request *path_request, const otc_cp_release_view *release_view, otc_cp_selected_reference_path *selected_reference_path_out)
{
    (void)station_source_row;
    (void)path_request;
    (void)release_view;
    (void)selected_reference_path_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_execute_discovery_query(const otc_cp_release_view *release_view, const otc_cp_query_kind *query_kind, const otc_cp_query_options *query_options, const otc_cp_reader_version *reader_version, otc_cp_ordered_station_results *ordered_station_results_out)
{
    (void)release_view;
    (void)query_kind;
    (void)query_options;
    (void)reader_version;
    (void)ordered_station_results_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_summarize_station_sets(const otc_cp_summary_kind *summary_kind, const otc_cp_release_view *release_view, const otc_cp_station_sets *station_sets, const otc_cp_summary_options *summary_options, otc_cp_station_summary *station_summary_out)
{
    (void)summary_kind;
    (void)release_view;
    (void)station_sets;
    (void)summary_options;
    (void)station_summary_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_admit_historical_offset(const otc_cp_own_offset *own_offset, const otc_cp_reference_path *reference_path, const otc_cp_historical_policy *historical_policy, const otc_cp_selection_kind *selection_kind, const otc_cp_reader_version *reader_version, otc_cp_historical_admission *historical_admission_out)
{
    (void)own_offset;
    (void)reference_path;
    (void)historical_policy;
    (void)selection_kind;
    (void)reader_version;
    (void)historical_admission_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_format_attribution(const otc_cp_station *station, const otc_cp_release_view *release_view, const otc_cp_commercial_only *commercial_only, otc_cp_attribution_text *attribution_text_out)
{
    (void)station;
    (void)release_view;
    (void)commercial_only;
    (void)attribution_text_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_format_citation(const otc_cp_published_metadata *published_metadata, const otc_cp_citation_style *citation_style, otc_cp_citation_text *citation_text_out)
{
    (void)published_metadata;
    (void)citation_style;
    (void)citation_text_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_parse_prediction_window(const otc_cp_time_inputs *time_inputs, const otc_cp_window_inputs *window_inputs, const otc_cp_step *step, const otc_cp_local_time_profile *local_time_profile, otc_cp_prediction_window *prediction_window_out)
{
int64_t start, stop;
int series = 0;
otc_status status;
otc_predict_opts options;
(void)local_time_profile;
if (!otc__prediction_available()) return OTC_E_NOT_BUILT;
if (!time_inputs || !window_inputs || !step || !prediction_window_out || time_inputs->tag != window_inputs->tag)
    return OTC_E_INVALID_ARGUMENT;
if (time_inputs->tag == OTC_CP_SELECTED_ARGUMENTS_RELEASE_HEIGHTS_AT) {
    const otc_cp_contract_instant____argument *times = &time_inputs->value.Release_heights_at.times;
    if (times->presence != OTC_CP_PRESENT_VALUE || (times->value.count && !times->value.items))
        return OTC_E_INVALID_ARGUMENT;
    memset(prediction_window_out, 0, sizeof *prediction_window_out);
    prediction_window_out->kind = OTC_CP_PREDICTION_WINDOW_INSTANTS;
    prediction_window_out->instants = times->value;
    return OTC_OK;
}
switch (time_inputs->tag) {
case OTC_CP_SELECTED_ARGUMENTS_RELEASE_EXTREMES:
    start = time_inputs->value.Release_extremes.start.value.value;
    stop = time_inputs->value.Release_extremes.stop.value.value; break;
case OTC_CP_SELECTED_ARGUMENTS_RELEASE_HEIGHTS:
    start = time_inputs->value.Release_heights.start.value.value;
    stop = time_inputs->value.Release_heights.stop.value.value; series = 1; break;
case OTC_CP_SELECTED_ARGUMENTS_RELEASE_CURRENTS:
    start = time_inputs->value.Release_currents.start.value.value;
    stop = time_inputs->value.Release_currents.stop.value.value; series = 1; break;
case OTC_CP_SELECTED_ARGUMENTS_RELEASE_CURRENT_EVENTS:
    start = time_inputs->value.Release_current_events.start.value.value;
    stop = time_inputs->value.Release_current_events.stop.value.value; break;
default: return OTC_E_INVALID_ARGUMENT;
}
otc_predict_opts_init(&options);
if (!isfinite(step->value) || step->value < INT64_MIN || step->value >= (double)INT64_MAX || floor(step->value) != step->value)
    return OTC_E_INVALID_ARGUMENT;
options.step_s = (int64_t)step->value;
status = otc__prediction_window(NULL, &options, start, stop, series);
if (status != OTC_OK) return status;
memset(prediction_window_out, 0, sizeof *prediction_window_out);
prediction_window_out->start.value = (double)start;
prediction_window_out->stop.value = (double)stop;
if (series) { prediction_window_out->step.presence = OTC_CP_PRESENT_VALUE; prediction_window_out->step.value.value = step->value; }
return OTC_OK;

}

otc_status otc__canonical_select_prediction_model(const otc_cp_station_request *station_request, const otc_cp_release_view *release_view, const otc_cp_selection_options *selection_options, const otc_cp_reader_version *reader_version, otc_cp_selected_prediction_model *selected_prediction_model_out)
{
    (void)station_request;
    (void)release_view;
    (void)selection_options;
    (void)reader_version;
    (void)selected_prediction_model_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_evaluate_astronomy(const otc_cp_selected_prediction_model *selected_prediction_model, const otc_cp_utc_instant *utc_instant, otc_cp_astronomical_terms *astronomical_terms_out)
{
const otc_astro_tab *table;
const otc_set *set;
const cJSON *constituents, *bin = NULL;
    cJSON *supplied_constituents;
    otc_cp_JsonValue supplied = {0};
struct otc_cp_prepared_astronomy *owner;
otc_cp_astronomical_terms_constituent_terms_item *terms;
otc_status status;
size_t i;
int year, index;
if (!otc__prediction_available()) return OTC_E_NOT_BUILT;
if (!utc_instant || !astronomical_terms_out || !isfinite(utc_instant->value)) return OTC_E_INVALID_ARGUMENT;
status = canonical_model_table(selected_prediction_model, &table);
if (status != OTC_OK) return status;
set = selected_prediction_model->constant_set.value;
year = otc__year(utc_instant->value);
status = otc__astro_index(table, year, &index);
if (status != OTC_OK) return status;
constituents = otc__jget(set->json, "constituents");
if (selected_prediction_model->reference_bin.presence == OTC_CP_PRESENT_VALUE) {
    const cJSON *candidate;
    cJSON_ArrayForEach(candidate, otc__jget(set->json, "current_bins"))
        if (otc__jint(candidate, "bin") == selected_prediction_model->reference_bin.value.value) { bin = candidate; break; }
    if (!bin) return OTC_E_BIN_NOT_FOUND;
    constituents = otc__jget(bin, "constituents");
}
    supplied.tag = OTC_CP_JSON_ARRAY;
    supplied.value.array.items = selected_prediction_model->required_constituents.items;
    supplied.value.array.count = selected_prediction_model->required_constituents.count;
    supplied_constituents = canonical_source_json(&supplied);
    if (!supplied_constituents) return OTC_E_INVALID_ARGUMENT;
    if (!cJSON_Compare(supplied_constituents, constituents, 1)) { cJSON_Delete(supplied_constituents); return OTC_E_INVALID_ARGUMENT; }
    owner = calloc(1, sizeof *owner);
    if (!owner) { cJSON_Delete(supplied_constituents); return OTC_E_NOMEM; }
    status = otc__sum_init(&owner->sum, table, supplied_constituents, bin ? "major_amplitude_ms" : "amplitude_m",
        bin ? "major_phase_deg" : "phase_deg", selected_prediction_model->mean_term.value,
        selected_prediction_model->harmonic_multiplier.presence == OTC_CP_PRESENT_VALUE ? selected_prediction_model->harmonic_multiplier.value.value : 1, 0);
    cJSON_Delete(supplied_constituents);
if (status == OTC_OK) status = otc__sum_prepare(&owner->sum, year);
if (status != OTC_OK) { otc__sum_clear(&owner->sum); free(owner); return status; }
terms = calloc(owner->sum.n ? owner->sum.n : 1, sizeof *terms);
if (!terms) { otc__sum_clear(&owner->sum); free(owner); return OTC_E_NOMEM; }
for (i = 0; i < owner->sum.n; i++) {
    const otc__term *t = &owner->sum.terms[i];
        terms[i].name = t->row->string;
    terms[i].node_factor = cJSON_GetArrayItem(otc__jget(t->row, "f"), index)->valuedouble;
    terms[i].equilibrium_argument_deg = cJSON_GetArrayItem(otc__jget(t->row, "v0u_deg"), index)->valuedouble;
    terms[i].scaled_amplitude = t->scaled;
    terms[i].argument_deg = t->argument;
    terms[i].omega_radians_per_hour = t->omega;
}
astronomical_terms_out->utc_year.value = year;
astronomical_terms_out->epoch_hours.value = (utc_instant->value - owner->sum.origin) / 3600.0;
astronomical_terms_out->constituent_terms.items = terms;
astronomical_terms_out->constituent_terms.count = owner->sum.n;
astronomical_terms_out->native_owner = owner;
return OTC_OK;

}

otc_status otc__canonical_evaluate_harmonic_height(const otc_cp_selected_prediction_model *selected_prediction_model, const otc_cp_prediction_instants *prediction_instants, const otc_cp_requested_datum *requested_datum, otc_cp_height_values *height_values_out)
{
    otc_cp_astronomical_terms terms = {0};
    otc_cp_contract_HeightPoint_ *points;
    otc_status status;
    double datum_term;
    size_t i;
    if (!otc__prediction_available()) return OTC_E_NOT_BUILT;
    if (!selected_prediction_model || !prediction_instants || !requested_datum || !height_values_out ||
        (prediction_instants->count && !prediction_instants->items)) return OTC_E_INVALID_ARGUMENT;
    status = otc__selected_datum_term(selected_prediction_model->release_view.value, selected_prediction_model->station.value,
        selected_prediction_model->constant_set.value, requested_datum->value, &datum_term);
    if (status != OTC_OK) return status;
    if (prediction_instants->count > SIZE_MAX / sizeof *points) return OTC_E_NOMEM;
    points = calloc(prediction_instants->count ? prediction_instants->count : 1, sizeof *points);
    if (!points) return OTC_E_NOMEM;
    for (i = 0; i < prediction_instants->count; i++) {
        otc_cp_utc_instant instant = { prediction_instants->items[i].value };
        double value;
        if (!isfinite(instant.value) || instant.value < INT64_MIN || instant.value >= (double)INT64_MAX || floor(instant.value) != instant.value) { status = OTC_E_INVALID_ARGUMENT; goto failure; }
        if (!terms.native_owner || terms.utc_year.value != otc__year(instant.value)) {
            otc__canonical_astronomy_clear(&terms);
            status = otc__canonical_evaluate_astronomy(selected_prediction_model, &instant, &terms);
            if (status != OTC_OK) goto failure;
        }
        /* Consume the prepared B41 owner. Its year is already cached, so
         * the unchanged sum evaluator performs no second preparation. */
        status = otc__sum_value(&terms.native_owner->sum, instant.value, (int)terms.utc_year.value, 0, &value);
        if (status != OTC_OK) goto failure;
        points[i].time.value = (int64_t)instant.value;
        points[i].height_m.value = value + datum_term;
    }
    otc__canonical_astronomy_clear(&terms);
    height_values_out->items = points; height_values_out->count = prediction_instants->count;
    return OTC_OK;
failure:
    otc__canonical_astronomy_clear(&terms); free(points); return status;

}

otc_status otc__canonical_find_tide_events(const otc_cp_selected_prediction_model *selected_prediction_model, const otc_cp_prediction_window *prediction_window, otc_cp_tide_events *tide_events_out)
{
    (void)selected_prediction_model;
    (void)prediction_window;
    (void)tide_events_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_evaluate_direct_current(const otc_cp_selected_prediction_model *selected_prediction_model, const otc_cp_prediction_window *prediction_window, const otc_cp_current_request *current_request, const otc_cp_current_operation *current_operation, otc_cp_direct_current_result *direct_current_result_out)
{
    (void)selected_prediction_model;
    (void)prediction_window;
    (void)current_request;
    (void)current_operation;
    (void)direct_current_result_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_evaluate_tide_offset(const otc_cp_own_offset *own_offset, const otc_cp_reference_path *reference_path, const otc_cp_prediction_window *prediction_window, const otc_cp_tide_request *tide_request, const otc_cp_reader_version *reader_version, otc_cp_offset_tide_result *offset_tide_result_out)
{
    (void)own_offset;
    (void)reference_path;
    (void)prediction_window;
    (void)tide_request;
    (void)reader_version;
    (void)offset_tide_result_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_fold_equal_tide_offset(const otc_cp_own_offset *own_offset, const otc_cp_reference_model *reference_model, const otc_cp_prediction_instants *prediction_instants, const otc_cp_requested_datum *requested_datum, otc_cp_folded_height_values *folded_height_values_out)
{
    (void)own_offset;
    (void)reference_model;
    (void)prediction_instants;
    (void)requested_datum;
    (void)folded_height_values_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_evaluate_current_offset(const otc_cp_own_current_offsets *own_current_offsets, const otc_cp_reference_path *reference_path, const otc_cp_prediction_window *prediction_window, const otc_cp_current_request *current_request, const otc_cp_reader_version *reader_version, otc_cp_offset_current_result *offset_current_result_out)
{
    (void)own_current_offsets;
    (void)reference_path;
    (void)prediction_window;
    (void)current_request;
    (void)reader_version;
    (void)offset_current_result_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_dispatch_auxiliary_result(const otc_cp_auxiliary_kind *auxiliary_kind, const otc_cp_auxiliary_operation *auxiliary_operation, const otc_cp_source_values *source_values, const otc_cp_result_context *result_context, const otc_cp_local_time_profile *local_time_profile, const otc_cp_result_values *result_values, const otc_cp_utc_result *utc_result, const otc_cp_selection_options *selection_options, const otc_cp_reader_version *reader_version, const otc_cp_auxiliary_member_id *auxiliary_member_id, otc_cp_auxiliary_result *auxiliary_result_out)
{
    (void)auxiliary_kind;
    (void)auxiliary_operation;
    (void)source_values;
    (void)result_context;
    (void)local_time_profile;
    (void)result_values;
    (void)utc_result;
    (void)selection_options;
    (void)reader_version;
    (void)auxiliary_member_id;
    (void)auxiliary_result_out;
    return OTC_E_NOT_BUILT;
}

struct otc_cp_raw_owner { struct otc_cp_index_owner *storage; };

void otc__canonical_raw_clear(otc_cp_raw_record *record)
{
    if (!record) return;
    if (record->native_owner) {
        canonical_index_owner_free(record->native_owner->storage);
        free(record->native_owner);
    }
    memset(record, 0, sizeof *record);
}

otc_status otc__canonical_retain_raw_source_record(const otc_cp_source_record *source_record, const otc_cp_native_profile *native_profile, otc_cp_raw_record *raw_record_out)
{
    otc_cp_JsonPair *pairs;
    otc_cp_JsonValue input = {0}, result = {0};
    struct otc_cp_raw_owner *owner;
    otc_status status;
    size_t i;
    if (!source_record || !native_profile || native_profile->value != OTC_CP_NATIVE_PROFILE_C || !raw_record_out ||
        (source_record->count && !source_record->entries)) return OTC_E_INVALID_ARGUMENT;
    pairs = calloc(source_record->count ? source_record->count : 1, sizeof *pairs);
    if (!pairs) return OTC_E_NOMEM;
    for (i = 0; i < source_record->count; i++) {
        pairs[i].key = source_record->entries[i].key.value;
        pairs[i].value = &source_record->entries[i].value;
    }
    input.tag = OTC_CP_JSON_OBJECT;
    input.value.members.entries = pairs; input.value.members.count = source_record->count;
    owner = calloc(1, sizeof *owner);
    if (!owner) { free(pairs); return OTC_E_NOMEM; }
    owner->storage = calloc(1, sizeof *owner->storage);
    if (!owner->storage) { free(pairs); free(owner); return OTC_E_NOMEM; }
    owner->storage->document = canonical_source_json(&input);
    free(pairs);
    if (!owner->storage->document) { canonical_index_owner_free(owner->storage); free(owner); return OTC_E_INVALID_ARGUMENT; }
    status = canonical_native_json(owner->storage, owner->storage->document, &result);
    if (status != OTC_OK) { canonical_index_owner_free(owner->storage); free(owner); return status; }
    result.native_owner = owner;
    *raw_record_out = result;
    return OTC_OK;
}

otc_status otc__canonical_check_station_origin(const otc_cp_station *station, const otc_cp_release_origin *release_origin, otc_cp_valid_station *valid_station_out)
{
    (void)station;
    (void)release_origin;
    (void)valid_station_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_manage_cache_lock(const otc_cp_lock_request *lock_request, const otc_cp_lock_state *lock_state, const otc_cp_clock *clock, otc_cp_lock_outcome *lock_outcome_out)
{
    (void)lock_request;
    (void)lock_state;
    (void)clock;
    (void)lock_outcome_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_request_http_resource(const otc_cp_http_request *http_request, const otc_cp_transport_options *transport_options, otc_cp_http_response *http_response_out)
{
    (void)http_request;
    (void)transport_options;
    (void)http_response_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_count_release_statistics(const otc_cp_release_view *release_view, otc_cp_release_statistics *release_statistics_out)
{
    (void)release_view;
    (void)release_statistics_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_order_constant_sets(const otc_cp_station_sets *station_sets, const otc_cp_original_recommendation *original_recommendation, const otc_cp_commercial_only *commercial_only, const otc_cp_include_no_constants *include_no_constants, otc_cp_ordered_constant_sets *ordered_constant_sets_out)
{
    (void)station_sets;
    (void)original_recommendation;
    (void)commercial_only;
    (void)include_no_constants;
    (void)ordered_constant_sets_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_read_auxiliary_model_value(const otc_cp_auxiliary_operation *auxiliary_operation, const otc_cp_source_values *source_values, const otc_cp_selection_options *selection_options, const otc_cp_reader_version *reader_version, const otc_cp_auxiliary_member_id *auxiliary_member_id, otc_cp_auxiliary_model_value *auxiliary_model_value_out)
{
    (void)auxiliary_operation;
    (void)source_values;
    (void)selection_options;
    (void)reader_version;
    (void)auxiliary_member_id;
    (void)auxiliary_model_value_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_construct_prediction_result(const otc_cp_result_values *result_values, const otc_cp_result_context *result_context, otc_cp_prediction_result *prediction_result_out)
{
    (void)result_values;
    (void)result_context;
    (void)prediction_result_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_convert_result_to_local_time(const otc_cp_utc_result *utc_result, const otc_cp_local_time_profile *local_time_profile, otc_cp_local_time_result *local_time_result_out)
{
    (void)utc_result;
    (void)local_time_profile;
    (void)local_time_result_out;
    return OTC_E_NOT_BUILT;
}

otc_status otc__canonical_find_unrounded_tide_events(const otc_cp_selected_prediction_model *selected_prediction_model, const otc_cp_prediction_window *prediction_window, otc_cp_unrounded_tide_events *unrounded_tide_events_out)
{
otc_cp_astronomical_terms terms = {0};
otc_cp_utc_instant instant;
otc__events events = {0};
otc_cp_UnroundedTideEvent *items;
otc_status status;
size_t i;
if (!otc__prediction_available()) return OTC_E_NOT_BUILT;
if (!prediction_window || !unrounded_tide_events_out || prediction_window->kind != OTC_CP_PREDICTION_WINDOW_SPAN) return OTC_E_INVALID_ARGUMENT;
instant.value = prediction_window->start.value;
status = otc__canonical_evaluate_astronomy(selected_prediction_model, &instant, &terms);
if (status != OTC_OK) return status;
status = otc__events_find_unrounded(&terms.native_owner->sum, prediction_window->start.value, prediction_window->stop.value, 0, &events);
otc__canonical_astronomy_clear(&terms);
if (status != OTC_OK) return status;
items = calloc(events.n ? events.n : 1, sizeof *items);
if (!items) { otc__events_clear(&events); return OTC_E_NOMEM; }
for (i = 0; i < events.n; i++) {
    items[i].root_seconds.value = events.items[i].t;
    items[i].event_type.value = (otc_cp_UnroundedTideEvent_event_type_tag)events.items[i].kind;
    items[i].height_m.value = events.items[i].value;
    items[i].reference_order.value = (int64_t)events.items[i].sequence;
}
unrounded_tide_events_out->items = items; unrounded_tide_events_out->count = events.n;
otc__events_clear(&events); return OTC_OK;

}

otc_status otc__canonical_find_unrounded_current_events(const otc_cp_selected_prediction_model *selected_prediction_model, const otc_cp_prediction_window *prediction_window, const otc_cp_current_request *current_request, otc_cp_unrounded_current_events *unrounded_current_events_out)
{
    otc_cp_astronomical_terms terms = {0};
    otc_cp_utc_instant instant;
    otc__events extrema = {0}, slack = {0};
    otc__current_candidate *candidates = NULL;
    otc_cp_UnroundedCurrentEvent *items;
    const cJSON *bin = NULL, *candidate;
    size_t i, count = 0;
    otc_status status;
    if (!otc__prediction_available()) return OTC_E_NOT_BUILT;
    if (!selected_prediction_model || !prediction_window || prediction_window->kind != OTC_CP_PREDICTION_WINDOW_SPAN || !current_request || !unrounded_current_events_out ||
        current_request->tag != OTC_CP_SELECTED_ARGUMENTS_RELEASE_CURRENT_EVENTS ||
        selected_prediction_model->reference_bin.presence != OTC_CP_PRESENT_VALUE) return OTC_E_INVALID_ARGUMENT;
    if (current_request->value.Release_current_events.bin_number.presence == OTC_CP_PRESENT_VALUE &&
        current_request->value.Release_current_events.bin_number.value.value != selected_prediction_model->reference_bin.value.value)
        return OTC_E_INVALID_ARGUMENT;
    instant.value = prediction_window->start.value;
    status = otc__canonical_evaluate_astronomy(selected_prediction_model, &instant, &terms);
    if (status != OTC_OK) return status;
    cJSON_ArrayForEach(candidate, otc__jget(selected_prediction_model->constant_set.value->json, "current_bins"))
        if (otc__jint(candidate, "bin") == selected_prediction_model->reference_bin.value.value) { bin = candidate; break; }
    if (!bin) { status = OTC_E_BIN_NOT_FOUND; goto done; }
    status = otc__events_find_unrounded(&terms.native_owner->sum, prediction_window->start.value, prediction_window->stop.value, 0, &extrema);
    if (status != OTC_OK) goto done;
    status = otc__events_find_unrounded(&terms.native_owner->sum, prediction_window->start.value, prediction_window->stop.value, 1, &slack);
    if (status != OTC_OK) goto done;
    status = otc__current_candidate_assembly(bin, &extrema, &slack, &candidates, &count);
    if (status != OTC_OK) goto done;
    items = calloc(count ? count : 1, sizeof *items);
    if (!items) { status = OTC_E_NOMEM; goto done; }
    for (i = 0; i < count; i++) {
        items[i].root_seconds.value = candidates[i].event.t;
        items[i].event_type.value = (otc_cp_UnroundedCurrentEvent_event_type_tag)candidates[i].event.kind;
        items[i].velocity_m_s.value = candidates[i].event.value;
        items[i].direction_deg.presence = isfinite(candidates[i].direction) ? OTC_CP_PRESENT_VALUE : OTC_CP_PRESENT_NULL;
        items[i].direction_deg.value.value = candidates[i].direction;
        items[i].reference_order.value = (int64_t)candidates[i].event.sequence;
    }
    unrounded_current_events_out->items = items; unrounded_current_events_out->count = count;
done:
    free(candidates); otc__events_clear(&extrema); otc__events_clear(&slack); otc__canonical_astronomy_clear(&terms);
    return status;
}

otc_status otc__canonical_acquire_checksum_sidecar(const otc_cp_acquisition_descriptor *acquisition_descriptor, const otc_cp_effective_options *effective_options, otc_cp_checksum_bytes *checksum_bytes_out)
{
    (void)acquisition_descriptor;
    (void)effective_options;
    (void)checksum_bytes_out;
    return OTC_E_NOT_BUILT;
}
