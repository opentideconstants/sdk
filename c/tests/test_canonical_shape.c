#include "otc_canonical.h"
#include <assert.h>
#include <stdio.h>
int main(void) {
    {
        otc_cp_operation operation = {0};
        otc_cp_arguments arguments = {0};
        otc_cp_member_contract member_contract = {0};
        otc_cp_validated_arguments validated_arguments = {0};
        otc_status status = otc__canonical_validate_operation_arguments(&operation, &arguments, &member_contract, &validated_arguments);
        assert(status == OTC_E_NOT_BUILT);
        puts("B01 private_unimplemented_refusal");
    }
    {
        otc_cp_explicit_options explicit_options = {0};
        otc_cp_environment environment = {0};
        otc_cp_platform_defaults platform_defaults = {0};
        otc_cp_effective_options effective_options = {0};
        otc_status status = otc__canonical_resolve_effective_options(&explicit_options, &environment, &platform_defaults, &effective_options);
        assert(status == OTC_E_NOT_BUILT);
        puts("B02 private_unimplemented_refusal");
    }
    {
        otc_cp_operation operation = {0};
        otc_cp_ordered_failures ordered_failures = {0};
        otc_cp_cause cause = {0};
        otc_cp_canonical_error canonical_error = {0};
        otc_status status = otc__canonical_select_canonical_error(&operation, &ordered_failures, &cause, &canonical_error);
        assert(status == OTC_E_NOT_BUILT);
        puts("B03 private_unimplemented_refusal");
    }
    {
        otc_cp_canonical_result canonical_result = {0};
        otc_cp_canonical_error canonical_error = {0};
        otc_cp_native_profile native_profile = {0};
        otc_cp_native_result native_result = {0};
        otc_status status = otc__canonical_translate_native_binding(&canonical_result, &canonical_error, &native_profile, &native_result);
        assert(status == OTC_E_NOT_BUILT);
        puts("B04 private_unimplemented_refusal");
    }
    {
        otc_cp_source_bytes source_bytes = {0};
        otc_cp_reader_version reader_version = {0};
        otc_cp_document_kind document_kind = {0};
        otc_cp_parsed_document parsed_document = {0};
        otc_status status = otc__canonical_decode_release_document(&source_bytes, &reader_version, &document_kind, &parsed_document);
        assert(status == OTC_E_NOT_BUILT);
        puts("B05 private_unimplemented_refusal");
    }
    {
        otc_cp_parsed_document parsed_document = {0};
        otc_cp_required_links required_links = {0};
        otc_cp_validated_release_graph validated_release_graph = {0};
        otc_status status = otc__canonical_validate_release_links(&parsed_document, &required_links, &validated_release_graph);
        assert(status == OTC_E_NOT_BUILT);
        puts("B06 private_unimplemented_refusal");
    }
    {
        otc_cp_raw_fields raw_fields = {0};
        otc_cp_field_contract field_contract = {0};
        otc_cp_origin origin = {0};
        otc_cp_model_type model_type = {0};
        otc_cp_typed_model typed_model = {0};
        otc_status status = otc__canonical_materialize_typed_model(&raw_fields, &field_contract, &origin, &model_type, &typed_model);
        assert(status == OTC_E_NOT_BUILT);
        puts("B07 private_unimplemented_refusal");
    }
    {
        otc_cp_access_kind access_kind = {0};
        otc_cp_source_record source_record = {0};
        otc_cp_station station = {0};
        otc_cp_release_origin release_origin = {0};
        otc_cp_native_profile native_profile = {0};
        otc_cp_raw_record_or_valid_station raw_record_or_valid_station = {0};
        otc_status status = otc__canonical_access_raw_record(&access_kind, &source_record, &station, &release_origin, &native_profile, &raw_record_or_valid_station);
        assert(status == OTC_E_NOT_BUILT);
        puts("B08 private_unimplemented_refusal");
    }
    {
        otc_cp_arguments arguments = {0};
        otc_cp_environment environment = {0};
        otc_cp_platform_defaults platform_defaults = {0};
        otc_cp_cache_state cache_state = {0};
        otc_cp_clock clock = {0};
        otc_cp_native_profile native_profile = {0};
        otc_cp_reader_version reader_version = {0};
        otc_cp_client_and_release client_and_release = {0};
        otc_status status = otc__canonical_open_client_release(&arguments, &environment, &platform_defaults, &cache_state, &clock, &native_profile, &reader_version, &client_and_release);
        assert(status == OTC_E_NOT_BUILT);
        puts("B09 private_unimplemented_refusal");
    }
    {
        otc_cp_release_request release_request = {0};
        otc_cp_effective_options effective_options = {0};
        otc_cp_cache_state cache_state = {0};
        otc_cp_clock clock = {0};
        otc_cp_reader_version reader_version = {0};
        otc_cp_loaded_release loaded_release = {0};
        otc_status status = otc__canonical_resolve_release_request(&release_request, &effective_options, &cache_state, &clock, &reader_version, &loaded_release);
        assert(status == OTC_E_NOT_BUILT);
        puts("B10 private_unimplemented_refusal");
    }
    {
        otc_cp_metadata_request metadata_request = {0};
        otc_cp_trusted_cache trusted_cache = {0};
        otc_cp_transport_options transport_options = {0};
        otc_cp_cache_state cache_state = {0};
        otc_cp_clock clock = {0};
        otc_cp_reader_version reader_version = {0};
        otc_cp_validated_metadata validated_metadata = {0};
        otc_status status = otc__canonical_exchange_release_metadata(&metadata_request, &trusted_cache, &transport_options, &cache_state, &clock, &reader_version, &validated_metadata);
        assert(status == OTC_E_NOT_BUILT);
        puts("B11 private_unimplemented_refusal");
    }
    {
        otc_cp_client_state client_state = {0};
        otc_cp_update_request update_request = {0};
        otc_cp_clock clock = {0};
        otc_cp_reader_version reader_version = {0};
        otc_cp_updated_client_state updated_client_state = {0};
        otc_status status = otc__canonical_update_client_release(&client_state, &update_request, &clock, &reader_version, &updated_client_state);
        assert(status == OTC_E_NOT_BUILT);
        puts("B12 private_unimplemented_refusal");
    }
    {
        otc_cp_client_state client_state = {0};
        otc_cp_query_kind query_kind = {0};
        otc_cp_clock clock = {0};
        otc_cp_reader_version reader_version = {0};
        otc_cp_query_client_state query_client_state = {0};
        otc_status status = otc__canonical_refresh_client_if_due(&client_state, &query_kind, &clock, &reader_version, &query_client_state);
        assert(status == OTC_E_NOT_BUILT);
        puts("B13 private_unimplemented_refusal");
    }
    {
        otc_cp_held_release held_release = {0};
        otc_cp_query_arguments query_arguments = {0};
        otc_cp_held_release_result held_release_result = {0};
        otc_status status = otc__canonical_forward_held_release(&held_release, &query_arguments, &held_release_result);
        assert(status == OTC_E_NOT_BUILT);
        puts("B14 private_unimplemented_refusal");
    }
    {
        otc_cp_resource_state resource_state = {0};
        otc_cp_lifetime_action lifetime_action = {0};
        otc_cp_resource_state_or_error resource_state_or_error = {0};
        otc_status status = otc__canonical_enforce_resource_lifetime(&resource_state, &lifetime_action, &resource_state_or_error);
        assert(status == OTC_E_NOT_BUILT);
        puts("B15 private_unimplemented_refusal");
    }
    {
        otc_cp_checksum_bytes checksum_bytes = {0};
        otc_cp_pointer_digests pointer_digests = {0};
        otc_cp_required_files required_files = {0};
        otc_cp_bound_checksums bound_checksums = {0};
        otc_status status = otc__canonical_bind_checksum_manifest(&checksum_bytes, &pointer_digests, &required_files, &bound_checksums);
        assert(status == OTC_E_NOT_BUILT);
        puts("B16 private_unimplemented_refusal");
    }
    {
        otc_cp_acquisition_descriptor acquisition_descriptor = {0};
        otc_cp_effective_options effective_options = {0};
        otc_cp_load_mode load_mode = {0};
        otc_cp_cache_state cache_state = {0};
        otc_cp_clock clock = {0};
        otc_cp_reader_version reader_version = {0};
        otc_cp_loaded_release loaded_release = {0};
        otc_status status = otc__canonical_acquire_release_files(&acquisition_descriptor, &effective_options, &load_mode, &cache_state, &clock, &reader_version, &loaded_release);
        assert(status == OTC_E_NOT_BUILT);
        puts("B17 private_unimplemented_refusal");
    }
    {
        otc_cp_locked_cache_state locked_cache_state = {0};
        otc_cp_verified_file_rows verified_file_rows = {0};
        otc_cp_release_metadata release_metadata = {0};
        otc_cp_merged_receipt merged_receipt = {0};
        otc_status status = otc__canonical_merge_cache_receipt(&locked_cache_state, &verified_file_rows, &release_metadata, &merged_receipt);
        assert(status == OTC_E_NOT_BUILT);
        puts("B18 private_unimplemented_refusal");
    }
    {
        otc_cp_release_candidates release_candidates = {0};
        otc_cp_effective_options effective_options = {0};
        otc_cp_cache_state cache_state = {0};
        otc_cp_clock clock = {0};
        otc_cp_usable_cached_release_or_error usable_cached_release_or_error = {0};
        otc_status status = otc__canonical_select_cached_release(&release_candidates, &effective_options, &cache_state, &clock, &usable_cached_release_or_error);
        assert(status == OTC_E_NOT_BUILT);
        puts("B19 private_unimplemented_refusal");
    }
    {
        otc_cp_release_files release_files = {0};
        otc_cp_trusted_cached_pointer trusted_cached_pointer = {0};
        otc_cp_verification_result verification_result = {0};
        otc_status status = otc__canonical_verify_release_files(&release_files, &trusted_cached_pointer, &verification_result);
        assert(status == OTC_E_NOT_BUILT);
        puts("B20 private_unimplemented_refusal");
    }
    {
        otc_cp_destination destination = {0};
        otc_cp_format_selection format_selection = {0};
        otc_cp_overwrite_policy overwrite_policy = {0};
        otc_cp_release_files release_files = {0};
        otc_cp_checksum_bytes checksum_bytes = {0};
        otc_cp_pointer_digests pointer_digests = {0};
        otc_cp_download_result download_result = {0};
        otc_status status = otc__canonical_publish_download(&destination, &format_selection, &overwrite_policy, &release_files, &checksum_bytes, &pointer_digests, &download_result);
        assert(status == OTC_E_NOT_BUILT);
        puts("B21 private_unimplemented_refusal");
    }
    {
        otc_cp_inventory_action inventory_action = {0};
        otc_cp_cache_state cache_state = {0};
        otc_cp_keep keep = {0};
        otc_cp_current_cache_directory current_cache_directory = {0};
        otc_cp_clock clock = {0};
        otc_cp_cache_inventory_result cache_inventory_result = {0};
        otc_status status = otc__canonical_manage_cache_inventory(&inventory_action, &cache_state, &keep, &current_cache_directory, &clock, &cache_inventory_result);
        assert(status == OTC_E_NOT_BUILT);
        puts("B22 private_unimplemented_refusal");
    }
    {
        otc_cp_io_kind io_kind = {0};
        otc_cp_io_request io_request = {0};
        otc_cp_io_options io_options = {0};
        otc_cp_clock clock = {0};
        otc_cp_io_result io_result = {0};
        otc_status status = otc__canonical_perform_guarded_io(&io_kind, &io_request, &io_options, &clock, &io_result);
        assert(status == OTC_E_NOT_BUILT);
        puts("B23 private_unimplemented_refusal");
    }
    {
        otc_cp_station_source_row station_source_row = {0};
        otc_cp_source_byte_span source_byte_span = {0};
        otc_cp_projection_contract projection_contract = {0};
        otc_cp_station_index_entry station_index_entry = {0};
        otc_status status = otc__canonical_project_station_index(&station_source_row, &source_byte_span, &projection_contract, &station_index_entry);
        assert(status == OTC_E_NOT_BUILT);
        puts("B24 private_unimplemented_refusal");
    }
    {
        otc_cp_source_files source_files = {0};
        otc_cp_supplied_index supplied_index = {0};
        otc_cp_index_presence index_presence = {0};
        otc_cp_reader_version reader_version = {0};
        otc_cp_authenticated_index authenticated_index = {0};
        otc_status status = otc__canonical_authenticate_station_index(&source_files, &supplied_index, &index_presence, &reader_version, &authenticated_index);
        assert(status == OTC_E_NOT_BUILT);
        puts("B25 private_unimplemented_refusal");
    }
    {
        otc_cp_index_entry index_entry = {0};
        otc_cp_station_source_row station_source_row = {0};
        otc_cp_index_presence index_presence = {0};
        otc_cp_compared_station_row compared_station_row = {0};
        otc_status status = otc__canonical_compare_station_source(&index_entry, &station_source_row, &index_presence, &compared_station_row);
        assert(status == OTC_E_NOT_BUILT);
        puts("B26 private_unimplemented_refusal");
    }
    {
        otc_cp_stream_reader stream_reader = {0};
        otc_cp_station_id station_id = {0};
        otc_cp_release_origin release_origin = {0};
        otc_cp_reader_version reader_version = {0};
        otc_cp_station_source_row station_source_row = {0};
        otc_status status = otc__canonical_read_station_lazily(&stream_reader, &station_id, &release_origin, &reader_version, &station_source_row);
        assert(status == OTC_E_NOT_BUILT);
        puts("B27 private_unimplemented_refusal");
    }
    {
        otc_cp_cache_document cache_document = {0};
        otc_cp_cache_bytes cache_bytes = {0};
        otc_status status = otc__canonical_encode_cache_json(&cache_document, &cache_bytes);
        assert(status == OTC_E_NOT_BUILT);
        puts("B28 private_unimplemented_refusal");
    }
    {
        otc_cp_release_view release_view = {0};
        otc_cp_identity_query identity_query = {0};
        otc_cp_reader_version reader_version = {0};
        otc_cp_station_or_tombstone_or_null station_or_tombstone_or_null = {0};
        otc_status status = otc__canonical_lookup_station_identity(&release_view, &identity_query, &reader_version, &station_or_tombstone_or_null);
        assert(status == OTC_E_NOT_BUILT);
        puts("B29 private_unimplemented_refusal");
    }
    {
        otc_cp_station_sets station_sets = {0};
        otc_cp_original_recommendation original_recommendation = {0};
        otc_cp_commercial_only commercial_only = {0};
        otc_cp_effective_recommendation effective_recommendation = {0};
        otc_status status = otc__canonical_select_effective_recommendation(&station_sets, &original_recommendation, &commercial_only, &effective_recommendation);
        assert(status == OTC_E_NOT_BUILT);
        puts("B30 private_unimplemented_refusal");
    }
    {
        otc_cp_candidate_path candidate_path = {0};
        otc_cp_include_flagged include_flagged = {0};
        otc_cp_include_fallback include_fallback = {0};
        otc_cp_quality_admission quality_admission = {0};
        otc_status status = otc__canonical_admit_quality_path(&candidate_path, &include_flagged, &include_fallback, &quality_admission);
        assert(status == OTC_E_NOT_BUILT);
        puts("B31 private_unimplemented_refusal");
    }
    {
        otc_cp_candidate_path candidate_path = {0};
        otc_cp_commercial_only commercial_only = {0};
        otc_cp_commercial_basis commercial_basis = {0};
        otc_cp_commercial_admission commercial_admission = {0};
        otc_status status = otc__canonical_admit_commercial_path(&candidate_path, &commercial_only, &commercial_basis, &commercial_admission);
        assert(status == OTC_E_NOT_BUILT);
        puts("B32 private_unimplemented_refusal");
    }
    {
        otc_cp_station_source_row station_source_row = {0};
        otc_cp_path_request path_request = {0};
        otc_cp_release_view release_view = {0};
        otc_cp_selected_reference_path selected_reference_path = {0};
        otc_status status = otc__canonical_resolve_reference_path(&station_source_row, &path_request, &release_view, &selected_reference_path);
        assert(status == OTC_E_NOT_BUILT);
        puts("B33 private_unimplemented_refusal");
    }
    {
        otc_cp_release_view release_view = {0};
        otc_cp_query_kind query_kind = {0};
        otc_cp_query_options query_options = {0};
        otc_cp_reader_version reader_version = {0};
        otc_cp_ordered_station_results ordered_station_results = {0};
        otc_status status = otc__canonical_execute_discovery_query(&release_view, &query_kind, &query_options, &reader_version, &ordered_station_results);
        assert(status == OTC_E_NOT_BUILT);
        puts("B34 private_unimplemented_refusal");
    }
    {
        otc_cp_summary_kind summary_kind = {0};
        otc_cp_release_view release_view = {0};
        otc_cp_station_sets station_sets = {0};
        otc_cp_summary_options summary_options = {0};
        otc_cp_station_summary station_summary = {0};
        otc_status status = otc__canonical_summarize_station_sets(&summary_kind, &release_view, &station_sets, &summary_options, &station_summary);
        assert(status == OTC_E_NOT_BUILT);
        puts("B35 private_unimplemented_refusal");
    }
    {
        otc_cp_own_offset own_offset = {0};
        otc_cp_reference_path reference_path = {0};
        otc_cp_historical_policy historical_policy = {0};
        otc_cp_selection_kind selection_kind = {0};
        otc_cp_reader_version reader_version = {0};
        otc_cp_historical_admission historical_admission = {0};
        otc_status status = otc__canonical_admit_historical_offset(&own_offset, &reference_path, &historical_policy, &selection_kind, &reader_version, &historical_admission);
        assert(status == OTC_E_NOT_BUILT);
        puts("B36 private_unimplemented_refusal");
    }
    {
        otc_cp_station station = {0};
        otc_cp_release_view release_view = {0};
        otc_cp_commercial_only commercial_only = {0};
        otc_cp_attribution_text attribution_text = {0};
        otc_status status = otc__canonical_format_attribution(&station, &release_view, &commercial_only, &attribution_text);
        assert(status == OTC_E_NOT_BUILT);
        puts("B37 private_unimplemented_refusal");
    }
    {
        otc_cp_published_metadata published_metadata = {0};
        otc_cp_citation_style citation_style = {0};
        otc_cp_citation_text citation_text = {0};
        otc_status status = otc__canonical_format_citation(&published_metadata, &citation_style, &citation_text);
        assert(status == OTC_E_NOT_BUILT);
        puts("B38 private_unimplemented_refusal");
    }
    {
        otc_cp_time_inputs time_inputs = {0};
        otc_cp_window_inputs window_inputs = {0};
        otc_cp_step step = {0};
        otc_cp_local_time_profile local_time_profile = {0};
        otc_cp_prediction_window prediction_window = {0};
        otc_status status = otc__canonical_parse_prediction_window(&time_inputs, &window_inputs, &step, &local_time_profile, &prediction_window);
        assert(status == OTC_E_NOT_BUILT);
        puts("B39 private_unimplemented_refusal");
    }
    {
        otc_cp_station_request station_request = {0};
        otc_cp_release_view release_view = {0};
        otc_cp_selection_options selection_options = {0};
        otc_cp_reader_version reader_version = {0};
        otc_cp_selected_prediction_model selected_prediction_model = {0};
        otc_status status = otc__canonical_select_prediction_model(&station_request, &release_view, &selection_options, &reader_version, &selected_prediction_model);
        assert(status == OTC_E_NOT_BUILT);
        puts("B40 private_unimplemented_refusal");
    }
    {
        otc_cp_selected_prediction_model selected_prediction_model = {0};
        otc_cp_utc_instant utc_instant = {0};
        otc_cp_astronomical_terms astronomical_terms = {0};
        otc_status status = otc__canonical_evaluate_astronomy(&selected_prediction_model, &utc_instant, &astronomical_terms);
        assert(status == OTC_E_NOT_BUILT);
        puts("B41 private_unimplemented_refusal");
    }
    {
        otc_cp_selected_prediction_model selected_prediction_model = {0};
        otc_cp_prediction_instants prediction_instants = {0};
        otc_cp_requested_datum requested_datum = {0};
        otc_cp_height_values height_values = {0};
        otc_status status = otc__canonical_evaluate_harmonic_height(&selected_prediction_model, &prediction_instants, &requested_datum, &height_values);
        assert(status == OTC_E_NOT_BUILT);
        puts("B42 private_unimplemented_refusal");
    }
    {
        otc_cp_selected_prediction_model selected_prediction_model = {0};
        otc_cp_prediction_window prediction_window = {0};
        otc_cp_tide_events tide_events = {0};
        otc_status status = otc__canonical_find_tide_events(&selected_prediction_model, &prediction_window, &tide_events);
        assert(status == OTC_E_NOT_BUILT);
        puts("B43 private_unimplemented_refusal");
    }
    {
        otc_cp_selected_prediction_model selected_prediction_model = {0};
        otc_cp_prediction_window prediction_window = {0};
        otc_cp_current_request current_request = {0};
        otc_cp_current_operation current_operation = {0};
        otc_cp_direct_current_result direct_current_result = {0};
        otc_status status = otc__canonical_evaluate_direct_current(&selected_prediction_model, &prediction_window, &current_request, &current_operation, &direct_current_result);
        assert(status == OTC_E_NOT_BUILT);
        puts("B44 private_unimplemented_refusal");
    }
    {
        otc_cp_own_offset own_offset = {0};
        otc_cp_reference_path reference_path = {0};
        otc_cp_prediction_window prediction_window = {0};
        otc_cp_tide_request tide_request = {0};
        otc_cp_reader_version reader_version = {0};
        otc_cp_offset_tide_result offset_tide_result = {0};
        otc_status status = otc__canonical_evaluate_tide_offset(&own_offset, &reference_path, &prediction_window, &tide_request, &reader_version, &offset_tide_result);
        assert(status == OTC_E_NOT_BUILT);
        puts("B45 private_unimplemented_refusal");
    }
    {
        otc_cp_own_offset own_offset = {0};
        otc_cp_reference_model reference_model = {0};
        otc_cp_prediction_instants prediction_instants = {0};
        otc_cp_requested_datum requested_datum = {0};
        otc_cp_folded_height_values folded_height_values = {0};
        otc_status status = otc__canonical_fold_equal_tide_offset(&own_offset, &reference_model, &prediction_instants, &requested_datum, &folded_height_values);
        assert(status == OTC_E_NOT_BUILT);
        puts("B46 private_unimplemented_refusal");
    }
    {
        otc_cp_own_current_offsets own_current_offsets = {0};
        otc_cp_reference_path reference_path = {0};
        otc_cp_prediction_window prediction_window = {0};
        otc_cp_current_request current_request = {0};
        otc_cp_reader_version reader_version = {0};
        otc_cp_offset_current_result offset_current_result = {0};
        otc_status status = otc__canonical_evaluate_current_offset(&own_current_offsets, &reference_path, &prediction_window, &current_request, &reader_version, &offset_current_result);
        assert(status == OTC_E_NOT_BUILT);
        puts("B47 private_unimplemented_refusal");
    }
    {
        otc_cp_auxiliary_kind auxiliary_kind = {0};
        otc_cp_auxiliary_operation auxiliary_operation = {0};
        otc_cp_source_values source_values = {0};
        otc_cp_result_context result_context = {0};
        otc_cp_local_time_profile local_time_profile = {0};
        otc_cp_result_values result_values = {0};
        otc_cp_utc_result utc_result = {0};
        otc_cp_selection_options selection_options = {0};
        otc_cp_reader_version reader_version = {0};
        otc_cp_auxiliary_member_id auxiliary_member_id = {0};
        otc_cp_auxiliary_result auxiliary_result = {0};
        otc_status status = otc__canonical_dispatch_auxiliary_result(&auxiliary_kind, &auxiliary_operation, &source_values, &result_context, &local_time_profile, &result_values, &utc_result, &selection_options, &reader_version, &auxiliary_member_id, &auxiliary_result);
        assert(status == OTC_E_NOT_BUILT);
        puts("B48 private_unimplemented_refusal");
    }
    {
        otc_cp_source_record source_record = {0};
        otc_cp_native_profile native_profile = {0};
        otc_cp_raw_record raw_record = {0};
        otc_status status = otc__canonical_retain_raw_source_record(&source_record, &native_profile, &raw_record);
        assert(status == OTC_E_NOT_BUILT);
        puts("B08.raw private_unimplemented_refusal");
    }
    {
        otc_cp_station station = {0};
        otc_cp_release_origin release_origin = {0};
        otc_cp_valid_station valid_station = {0};
        otc_status status = otc__canonical_check_station_origin(&station, &release_origin, &valid_station);
        assert(status == OTC_E_NOT_BUILT);
        puts("B08.origin private_unimplemented_refusal");
    }
    {
        otc_cp_lock_request lock_request = {0};
        otc_cp_lock_state lock_state = {0};
        otc_cp_clock clock = {0};
        otc_cp_lock_outcome lock_outcome = {0};
        otc_status status = otc__canonical_manage_cache_lock(&lock_request, &lock_state, &clock, &lock_outcome);
        assert(status == OTC_E_NOT_BUILT);
        puts("B23.lock private_unimplemented_refusal");
    }
    {
        otc_cp_http_request http_request = {0};
        otc_cp_transport_options transport_options = {0};
        otc_cp_http_response http_response = {0};
        otc_status status = otc__canonical_request_http_resource(&http_request, &transport_options, &http_response);
        assert(status == OTC_E_NOT_BUILT);
        puts("B23.http private_unimplemented_refusal");
    }
    {
        otc_cp_release_view release_view = {0};
        otc_cp_release_statistics release_statistics = {0};
        otc_status status = otc__canonical_count_release_statistics(&release_view, &release_statistics);
        assert(status == OTC_E_NOT_BUILT);
        puts("B35.stats private_unimplemented_refusal");
    }
    {
        otc_cp_station_sets station_sets = {0};
        otc_cp_original_recommendation original_recommendation = {0};
        otc_cp_commercial_only commercial_only = {0};
        otc_cp_include_no_constants include_no_constants = {0};
        otc_cp_ordered_constant_sets ordered_constant_sets = {0};
        otc_status status = otc__canonical_order_constant_sets(&station_sets, &original_recommendation, &commercial_only, &include_no_constants, &ordered_constant_sets);
        assert(status == OTC_E_NOT_BUILT);
        puts("B35.sets private_unimplemented_refusal");
    }
    {
        otc_cp_auxiliary_operation auxiliary_operation = {0};
        otc_cp_source_values source_values = {0};
        otc_cp_selection_options selection_options = {0};
        otc_cp_reader_version reader_version = {0};
        otc_cp_auxiliary_member_id auxiliary_member_id = {0};
        otc_cp_auxiliary_model_value auxiliary_model_value = {0};
        otc_status status = otc__canonical_read_auxiliary_model_value(&auxiliary_operation, &source_values, &selection_options, &reader_version, &auxiliary_member_id, &auxiliary_model_value);
        assert(status == OTC_E_NOT_BUILT);
        puts("B48.aux private_unimplemented_refusal");
    }
    {
        otc_cp_result_values result_values = {0};
        otc_cp_result_context result_context = {0};
        otc_cp_prediction_result prediction_result = {0};
        otc_status status = otc__canonical_construct_prediction_result(&result_values, &result_context, &prediction_result);
        assert(status == OTC_E_NOT_BUILT);
        puts("B48.context private_unimplemented_refusal");
    }
    {
        otc_cp_utc_result utc_result = {0};
        otc_cp_local_time_profile local_time_profile = {0};
        otc_cp_local_time_result local_time_result = {0};
        otc_status status = otc__canonical_convert_result_to_local_time(&utc_result, &local_time_profile, &local_time_result);
        assert(status == OTC_E_NOT_BUILT);
        puts("B48.local private_unimplemented_refusal");
    }
    {
        otc_cp_selected_prediction_model selected_prediction_model = {0};
        otc_cp_prediction_window prediction_window = {0};
        otc_cp_unrounded_tide_events unrounded_tide_events = {0};
        otc_status status = otc__canonical_find_unrounded_tide_events(&selected_prediction_model, &prediction_window, &unrounded_tide_events);
        assert(status == OTC_E_NOT_BUILT);
        puts("B43.roots private_unimplemented_refusal");
    }
    {
        otc_cp_selected_prediction_model selected_prediction_model = {0};
        otc_cp_prediction_window prediction_window = {0};
        otc_cp_current_request current_request = {0};
        otc_cp_unrounded_current_events unrounded_current_events = {0};
        otc_status status = otc__canonical_find_unrounded_current_events(&selected_prediction_model, &prediction_window, &current_request, &unrounded_current_events);
        assert(status == OTC_E_NOT_BUILT);
        puts("B44.roots private_unimplemented_refusal");
    }
    {
        otc_cp_acquisition_descriptor acquisition_descriptor = {0};
        otc_cp_effective_options effective_options = {0};
        otc_cp_checksum_bytes checksum_bytes = {0};
        otc_status status = otc__canonical_acquire_checksum_sidecar(&acquisition_descriptor, &effective_options, &checksum_bytes);
        assert(status == OTC_E_NOT_BUILT);
        puts("B17.sidecar private_unimplemented_refusal");
    }
    { /* B08.S1.A1: access_kind = raw_record */
        otc_cp_source_record source_record = {0};
        otc_cp_native_profile native_profile = {0};
        otc_cp_raw_record raw_record = {0};
        otc_status status = otc__canonical_retain_raw_source_record(&source_record, &native_profile, &raw_record);
        assert(status == OTC_E_NOT_BUILT);
        puts("B08.S1.A1 private_unimplemented_refusal");
    }
    { /* B08.S1.A2: access_kind = station_object */
        otc_cp_station station = {0};
        otc_cp_release_origin release_origin = {0};
        otc_cp_valid_station valid_station = {0};
        otc_status status = otc__canonical_check_station_origin(&station, &release_origin, &valid_station);
        assert(status == OTC_E_NOT_BUILT);
        puts("B08.S1.A2 private_unimplemented_refusal");
    }
    { /* B09.S1.A3: always */
        otc_cp_operation operation = {0};
        otc_cp_arguments arguments = {0};
        otc_cp_member_contract member_contract = {0};
        otc_cp_validated_arguments validated_arguments = {0};
        otc_status status = otc__canonical_validate_operation_arguments(&operation, &arguments, &member_contract, &validated_arguments);
        assert(status == OTC_E_NOT_BUILT);
        puts("B09.S1.A3 private_unimplemented_refusal");
    }
    { /* B09.S1.A4: always */
        otc_cp_explicit_options explicit_options = {0};
        otc_cp_environment environment = {0};
        otc_cp_platform_defaults platform_defaults = {0};
        otc_cp_effective_options effective_options = {0};
        otc_status status = otc__canonical_resolve_effective_options(&explicit_options, &environment, &platform_defaults, &effective_options);
        assert(status == OTC_E_NOT_BUILT);
        puts("B09.S1.A4 private_unimplemented_refusal");
    }
    { /* B09.S1.A5: release-request branch */
        otc_cp_release_request release_request = {0};
        otc_cp_effective_options effective_options = {0};
        otc_cp_cache_state cache_state = {0};
        otc_cp_clock clock = {0};
        otc_cp_reader_version reader_version = {0};
        otc_cp_loaded_release loaded_release = {0};
        otc_status status = otc__canonical_resolve_release_request(&release_request, &effective_options, &cache_state, &clock, &reader_version, &loaded_release);
        assert(status == OTC_E_NOT_BUILT);
        puts("B09.S1.A5 private_unimplemented_refusal");
    }
    { /* B09.S2.A4: local checksum sidecar required or supplied */
        otc_cp_checksum_bytes checksum_bytes = {0};
        otc_cp_pointer_digests pointer_digests = {0};
        otc_cp_required_files required_files = {0};
        otc_cp_bound_checksums bound_checksums = {0};
        otc_status status = otc__canonical_bind_checksum_manifest(&checksum_bytes, &pointer_digests, &required_files, &bound_checksums);
        assert(status == OTC_E_NOT_BUILT);
        puts("B09.S2.A4 private_unimplemented_refusal");
    }
    { /* B09.S2.A9: local-file branch */
        otc_cp_source_bytes source_bytes = {0};
        otc_cp_reader_version reader_version = {0};
        otc_cp_document_kind document_kind = {0};
        otc_cp_parsed_document parsed_document = {0};
        otc_status status = otc__canonical_decode_release_document(&source_bytes, &reader_version, &document_kind, &parsed_document);
        assert(status == OTC_E_NOT_BUILT);
        puts("B09.S2.A9 private_unimplemented_refusal");
    }
    { /* B09.S2.A11: local-file branch */
        otc_cp_parsed_document parsed_document = {0};
        otc_cp_required_links required_links = {0};
        otc_cp_validated_release_graph validated_release_graph = {0};
        otc_status status = otc__canonical_validate_release_links(&parsed_document, &required_links, &validated_release_graph);
        assert(status == OTC_E_NOT_BUILT);
        puts("B09.S2.A11 private_unimplemented_refusal");
    }
    { /* B10.S1.A2: pinned cache attempt */
        otc_cp_release_candidates release_candidates = {0};
        otc_cp_effective_options effective_options = {0};
        otc_cp_cache_state cache_state = {0};
        otc_cp_clock clock = {0};
        otc_cp_usable_cached_release_or_error usable_cached_release_or_error = {0};
        otc_status status = otc__canonical_select_cached_release(&release_candidates, &effective_options, &cache_state, &clock, &usable_cached_release_or_error);
        assert(status == OTC_E_NOT_BUILT);
        puts("B10.S1.A2 private_unimplemented_refusal");
    }
    { /* B10.S1.A5: pinned cache missing and online */
        otc_cp_acquisition_descriptor acquisition_descriptor = {0};
        otc_cp_effective_options effective_options = {0};
        otc_cp_load_mode load_mode = {0};
        otc_cp_cache_state cache_state = {0};
        otc_cp_clock clock = {0};
        otc_cp_reader_version reader_version = {0};
        otc_cp_loaded_release loaded_release = {0};
        otc_status status = otc__canonical_acquire_release_files(&acquisition_descriptor, &effective_options, &load_mode, &cache_state, &clock, &reader_version, &loaded_release);
        assert(status == OTC_E_NOT_BUILT);
        puts("B10.S1.A5 private_unimplemented_refusal");
    }
    { /* B10.S2.A1: latest offline */
        otc_cp_release_candidates release_candidates = {0};
        otc_cp_effective_options effective_options = {0};
        otc_cp_cache_state cache_state = {0};
        otc_cp_clock clock = {0};
        otc_cp_usable_cached_release_or_error usable_cached_release_or_error = {0};
        otc_status status = otc__canonical_select_cached_release(&release_candidates, &effective_options, &cache_state, &clock, &usable_cached_release_or_error);
        assert(status == OTC_E_NOT_BUILT);
        puts("B10.S2.A1 private_unimplemented_refusal");
    }
    { /* B10.S3.A4: latest online */
        otc_cp_metadata_request metadata_request = {0};
        otc_cp_trusted_cache trusted_cache = {0};
        otc_cp_transport_options transport_options = {0};
        otc_cp_cache_state cache_state = {0};
        otc_cp_clock clock = {0};
        otc_cp_reader_version reader_version = {0};
        otc_cp_validated_metadata validated_metadata = {0};
        otc_status status = otc__canonical_exchange_release_metadata(&metadata_request, &trusted_cache, &transport_options, &cache_state, &clock, &reader_version, &validated_metadata);
        assert(status == OTC_E_NOT_BUILT);
        puts("B10.S3.A4 private_unimplemented_refusal");
    }
    { /* B10.S3.A6: latest online metadata selected a release */
        otc_cp_acquisition_descriptor acquisition_descriptor = {0};
        otc_cp_effective_options effective_options = {0};
        otc_cp_load_mode load_mode = {0};
        otc_cp_cache_state cache_state = {0};
        otc_cp_clock clock = {0};
        otc_cp_reader_version reader_version = {0};
        otc_cp_loaded_release loaded_release = {0};
        otc_status status = otc__canonical_acquire_release_files(&acquisition_descriptor, &effective_options, &load_mode, &cache_state, &clock, &reader_version, &loaded_release);
        assert(status == OTC_E_NOT_BUILT);
        puts("B10.S3.A6 private_unimplemented_refusal");
    }
    { /* B10.S4.A1: network failure and use_cache */
        otc_cp_release_candidates release_candidates = {0};
        otc_cp_effective_options effective_options = {0};
        otc_cp_cache_state cache_state = {0};
        otc_cp_clock clock = {0};
        otc_cp_usable_cached_release_or_error usable_cached_release_or_error = {0};
        otc_status status = otc__canonical_select_cached_release(&release_candidates, &effective_options, &cache_state, &clock, &usable_cached_release_or_error);
        assert(status == OTC_E_NOT_BUILT);
        puts("B10.S4.A1 private_unimplemented_refusal");
    }
    { /* B11.S2.A2: a network request is permitted */
        otc_cp_http_request http_request = {0};
        otc_cp_transport_options transport_options = {0};
        otc_cp_http_response http_response = {0};
        otc_status status = otc__canonical_request_http_resource(&http_request, &transport_options, &http_response);
        assert(status == OTC_E_NOT_BUILT);
        puts("B11.S2.A2 private_unimplemented_refusal");
    }
    { /* B11.S3.A5: a fresh response or candidate cached body exists */
        otc_cp_source_bytes source_bytes = {0};
        otc_cp_reader_version reader_version = {0};
        otc_cp_document_kind document_kind = {0};
        otc_cp_parsed_document parsed_document = {0};
        otc_status status = otc__canonical_decode_release_document(&source_bytes, &reader_version, &document_kind, &parsed_document);
        assert(status == OTC_E_NOT_BUILT);
        puts("B11.S3.A5 private_unimplemented_refusal");
    }
    { /* B11.S5.A2: publish conditional body/tag */
        otc_cp_lock_request lock_request = {0};
        otc_cp_lock_state lock_state = {0};
        otc_cp_clock clock = {0};
        otc_cp_lock_outcome lock_outcome = {0};
        otc_status status = otc__canonical_manage_cache_lock(&lock_request, &lock_state, &clock, &lock_outcome);
        assert(status == OTC_E_NOT_BUILT);
        puts("B11.S5.A2 private_unimplemented_refusal");
    }
    { /* B11.S5.A4: publish valid metadata body */
        otc_cp_cache_document cache_document = {0};
        otc_cp_cache_bytes cache_bytes = {0};
        otc_status status = otc__canonical_encode_cache_json(&cache_document, &cache_bytes);
        assert(status == OTC_E_NOT_BUILT);
        puts("B11.S5.A4 private_unimplemented_refusal");
    }
    { /* B12.S1.A3: always */
        otc_cp_resource_state resource_state = {0};
        otc_cp_lifetime_action lifetime_action = {0};
        otc_cp_resource_state_or_error resource_state_or_error = {0};
        otc_status status = otc__canonical_enforce_resource_lifetime(&resource_state, &lifetime_action, &resource_state_or_error);
        assert(status == OTC_E_NOT_BUILT);
        puts("B12.S1.A3 private_unimplemented_refusal");
    }
    { /* B12.S1.A7: update restrictions pass */
        otc_cp_metadata_request metadata_request = {0};
        otc_cp_trusted_cache trusted_cache = {0};
        otc_cp_transport_options transport_options = {0};
        otc_cp_cache_state cache_state = {0};
        otc_cp_clock clock = {0};
        otc_cp_reader_version reader_version = {0};
        otc_cp_validated_metadata validated_metadata = {0};
        otc_status status = otc__canonical_exchange_release_metadata(&metadata_request, &trusted_cache, &transport_options, &cache_state, &clock, &reader_version, &validated_metadata);
        assert(status == OTC_E_NOT_BUILT);
        puts("B12.S1.A7 private_unimplemented_refusal");
    }
    { /* B12.S2.A2: a new candidate exists */
        otc_cp_release_request release_request = {0};
        otc_cp_effective_options effective_options = {0};
        otc_cp_cache_state cache_state = {0};
        otc_cp_clock clock = {0};
        otc_cp_reader_version reader_version = {0};
        otc_cp_loaded_release loaded_release = {0};
        otc_status status = otc__canonical_resolve_release_request(&release_request, &effective_options, &cache_state, &clock, &reader_version, &loaded_release);
        assert(status == OTC_E_NOT_BUILT);
        puts("B12.S2.A2 private_unimplemented_refusal");
    }
    { /* B13.S3.A2: eligible open accessor or query */
        otc_cp_client_state client_state = {0};
        otc_cp_update_request update_request = {0};
        otc_cp_clock clock = {0};
        otc_cp_reader_version reader_version = {0};
        otc_cp_updated_client_state updated_client_state = {0};
        otc_status status = otc__canonical_update_client_release(&client_state, &update_request, &clock, &reader_version, &updated_client_state);
        assert(status == OTC_E_NOT_BUILT);
        puts("B13.S3.A2 private_unimplemented_refusal");
    }
    { /* B14.S2.A2: always */
        otc_cp_resource_state resource_state = {0};
        otc_cp_lifetime_action lifetime_action = {0};
        otc_cp_resource_state_or_error resource_state_or_error = {0};
        otc_status status = otc__canonical_enforce_resource_lifetime(&resource_state, &lifetime_action, &resource_state_or_error);
        assert(status == OTC_E_NOT_BUILT);
        puts("B14.S2.A2 private_unimplemented_refusal");
    }
    { /* B17.S1.A2: always */
        otc_cp_lock_request lock_request = {0};
        otc_cp_lock_state lock_state = {0};
        otc_cp_clock clock = {0};
        otc_cp_lock_outcome lock_outcome = {0};
        otc_status status = otc__canonical_manage_cache_lock(&lock_request, &lock_state, &clock, &lock_outcome);
        assert(status == OTC_E_NOT_BUILT);
        puts("B17.S1.A2 private_unimplemented_refusal");
    }
    { /* B17.S1.A3: recheck under owned lock */
        otc_cp_release_candidates release_candidates = {0};
        otc_cp_effective_options effective_options = {0};
        otc_cp_cache_state cache_state = {0};
        otc_cp_clock clock = {0};
        otc_cp_usable_cached_release_or_error usable_cached_release_or_error = {0};
        otc_status status = otc__canonical_select_cached_release(&release_candidates, &effective_options, &cache_state, &clock, &usable_cached_release_or_error);
        assert(status == OTC_E_NOT_BUILT);
        puts("B17.S1.A3 private_unimplemented_refusal");
    }
    { /* B17.S2.A1: always under owned release acquisition lock before data acquisition */
        otc_cp_acquisition_descriptor acquisition_descriptor = {0};
        otc_cp_effective_options effective_options = {0};
        otc_cp_checksum_bytes checksum_bytes = {0};
        otc_status status = otc__canonical_acquire_checksum_sidecar(&acquisition_descriptor, &effective_options, &checksum_bytes);
        assert(status == OTC_E_NOT_BUILT);
        puts("B17.S2.A1 private_unimplemented_refusal");
    }
    { /* B17.S2.A3: before acquisition */
        otc_cp_checksum_bytes checksum_bytes = {0};
        otc_cp_pointer_digests pointer_digests = {0};
        otc_cp_required_files required_files = {0};
        otc_cp_bound_checksums bound_checksums = {0};
        otc_status status = otc__canonical_bind_checksum_manifest(&checksum_bytes, &pointer_digests, &required_files, &bound_checksums);
        assert(status == OTC_E_NOT_BUILT);
        puts("B17.S2.A3 private_unimplemented_refusal");
    }
    { /* B17.S2.A6: a required data file is missing and online */
        otc_cp_http_request http_request = {0};
        otc_cp_transport_options transport_options = {0};
        otc_cp_http_response http_response = {0};
        otc_status status = otc__canonical_request_http_resource(&http_request, &transport_options, &http_response);
        assert(status == OTC_E_NOT_BUILT);
        puts("B17.S2.A6 private_unimplemented_refusal");
    }
    { /* B17.S4.A2: checked data files are published */
        otc_cp_locked_cache_state locked_cache_state = {0};
        otc_cp_verified_file_rows verified_file_rows = {0};
        otc_cp_release_metadata release_metadata = {0};
        otc_cp_merged_receipt merged_receipt = {0};
        otc_status status = otc__canonical_merge_cache_receipt(&locked_cache_state, &verified_file_rows, &release_metadata, &merged_receipt);
        assert(status == OTC_E_NOT_BUILT);
        puts("B17.S4.A2 private_unimplemented_refusal");
    }
    { /* B17.S5.A4: stream mode */
        otc_cp_source_files source_files = {0};
        otc_cp_supplied_index supplied_index = {0};
        otc_cp_index_presence index_presence = {0};
        otc_cp_reader_version reader_version = {0};
        otc_cp_authenticated_index authenticated_index = {0};
        otc_status status = otc__canonical_authenticate_station_index(&source_files, &supplied_index, &index_presence, &reader_version, &authenticated_index);
        assert(status == OTC_E_NOT_BUILT);
        puts("B17.S5.A4 private_unimplemented_refusal");
    }
    { /* B18.S4.A2: publish merged receipt */
        otc_cp_cache_document cache_document = {0};
        otc_cp_cache_bytes cache_bytes = {0};
        otc_status status = otc__canonical_encode_cache_json(&cache_document, &cache_bytes);
        assert(status == OTC_E_NOT_BUILT);
        puts("B18.S4.A2 private_unimplemented_refusal");
    }
    { /* B19.S3.A2: a corrupt candidate is eligible for heal */
        otc_cp_lock_request lock_request = {0};
        otc_cp_lock_state lock_state = {0};
        otc_cp_clock clock = {0};
        otc_cp_lock_outcome lock_outcome = {0};
        otc_status status = otc__canonical_manage_cache_lock(&lock_request, &lock_state, &clock, &lock_outcome);
        assert(status == OTC_E_NOT_BUILT);
        puts("B19.S3.A2 private_unimplemented_refusal");
    }
    { /* B20.S2.A2: checksum binding exists */
        otc_cp_checksum_bytes checksum_bytes = {0};
        otc_cp_pointer_digests pointer_digests = {0};
        otc_cp_required_files required_files = {0};
        otc_cp_bound_checksums bound_checksums = {0};
        otc_status status = otc__canonical_bind_checksum_manifest(&checksum_bytes, &pointer_digests, &required_files, &bound_checksums);
        assert(status == OTC_E_NOT_BUILT);
        puts("B20.S2.A2 private_unimplemented_refusal");
    }
    { /* B21.S2.A1: before download publication */
        otc_cp_checksum_bytes checksum_bytes = {0};
        otc_cp_pointer_digests pointer_digests = {0};
        otc_cp_required_files required_files = {0};
        otc_cp_bound_checksums bound_checksums = {0};
        otc_status status = otc__canonical_bind_checksum_manifest(&checksum_bytes, &pointer_digests, &required_files, &bound_checksums);
        assert(status == OTC_E_NOT_BUILT);
        puts("B21.S2.A1 private_unimplemented_refusal");
    }
    { /* B22.S4.A2: prune deletion or partial sweep */
        otc_cp_lock_request lock_request = {0};
        otc_cp_lock_state lock_state = {0};
        otc_cp_clock clock = {0};
        otc_cp_lock_outcome lock_outcome = {0};
        otc_status status = otc__canonical_manage_cache_lock(&lock_request, &lock_state, &clock, &lock_outcome);
        assert(status == OTC_E_NOT_BUILT);
        puts("B22.S4.A2 private_unimplemented_refusal");
    }
    { /* B23.S1.A5: io_kind = lock */
        otc_cp_lock_request lock_request = {0};
        otc_cp_lock_state lock_state = {0};
        otc_cp_clock clock = {0};
        otc_cp_lock_outcome lock_outcome = {0};
        otc_status status = otc__canonical_manage_cache_lock(&lock_request, &lock_state, &clock, &lock_outcome);
        assert(status == OTC_E_NOT_BUILT);
        puts("B23.S1.A5 private_unimplemented_refusal");
    }
    { /* B23.S1.A7: io_kind = http */
        otc_cp_http_request http_request = {0};
        otc_cp_transport_options transport_options = {0};
        otc_cp_http_response http_response = {0};
        otc_status status = otc__canonical_request_http_resource(&http_request, &transport_options, &http_response);
        assert(status == OTC_E_NOT_BUILT);
        puts("B23.S1.A7 private_unimplemented_refusal");
    }
    { /* B25.S4.A4: stale or absent index requires one source pass */
        otc_cp_station_source_row station_source_row = {0};
        otc_cp_source_byte_span source_byte_span = {0};
        otc_cp_projection_contract projection_contract = {0};
        otc_cp_station_index_entry station_index_entry = {0};
        otc_status status = otc__canonical_project_station_index(&station_source_row, &source_byte_span, &projection_contract, &station_index_entry);
        assert(status == OTC_E_NOT_BUILT);
        puts("B25.S4.A4 private_unimplemented_refusal");
    }
    { /* B25.S4.A6: publish rebuilt index */
        otc_cp_cache_document cache_document = {0};
        otc_cp_cache_bytes cache_bytes = {0};
        otc_status status = otc__canonical_encode_cache_json(&cache_document, &cache_bytes);
        assert(status == OTC_E_NOT_BUILT);
        puts("B25.S4.A6 private_unimplemented_refusal");
    }
    { /* B27.S1.A1: always */
        otc_cp_resource_state resource_state = {0};
        otc_cp_lifetime_action lifetime_action = {0};
        otc_cp_resource_state_or_error resource_state_or_error = {0};
        otc_status status = otc__canonical_enforce_resource_lifetime(&resource_state, &lifetime_action, &resource_state_or_error);
        assert(status == OTC_E_NOT_BUILT);
        puts("B27.S1.A1 private_unimplemented_refusal");
    }
    { /* B27.S4.A3: LRU miss and row was not in the LRU */
        otc_cp_source_bytes source_bytes = {0};
        otc_cp_reader_version reader_version = {0};
        otc_cp_document_kind document_kind = {0};
        otc_cp_parsed_document parsed_document = {0};
        otc_status status = otc__canonical_decode_release_document(&source_bytes, &reader_version, &document_kind, &parsed_document);
        assert(status == OTC_E_NOT_BUILT);
        puts("B27.S4.A3 private_unimplemented_refusal");
    }
    { /* B27.S4.A7: LRU miss and index supplied the positional row */
        otc_cp_index_entry index_entry = {0};
        otc_cp_station_source_row station_source_row = {0};
        otc_cp_index_presence index_presence = {0};
        otc_cp_compared_station_row compared_station_row = {0};
        otc_status status = otc__canonical_compare_station_source(&index_entry, &station_source_row, &index_presence, &compared_station_row);
        assert(status == OTC_E_NOT_BUILT);
        puts("B27.S4.A7 private_unimplemented_refusal");
    }
    { /* B29.S4.A4: stream-backed selected station */
        otc_cp_stream_reader stream_reader = {0};
        otc_cp_station_id station_id = {0};
        otc_cp_release_origin release_origin = {0};
        otc_cp_reader_version reader_version = {0};
        otc_cp_station_source_row station_source_row = {0};
        otc_status status = otc__canonical_read_station_lazily(&stream_reader, &station_id, &release_origin, &reader_version, &station_source_row);
        assert(status == OTC_E_NOT_BUILT);
        puts("B29.S4.A4 private_unimplemented_refusal");
    }
    { /* B29.S4.A8: selected station exists */
        otc_cp_raw_fields raw_fields = {0};
        otc_cp_field_contract field_contract = {0};
        otc_cp_origin origin = {0};
        otc_cp_model_type model_type = {0};
        otc_cp_typed_model typed_model = {0};
        otc_status status = otc__canonical_materialize_typed_model(&raw_fields, &field_contract, &origin, &model_type, &typed_model);
        assert(status == OTC_E_NOT_BUILT);
        puts("B29.S4.A8 private_unimplemented_refusal");
    }
    { /* B34.S1.A1: query entry and each iterator step */
        otc_cp_resource_state resource_state = {0};
        otc_cp_lifetime_action lifetime_action = {0};
        otc_cp_resource_state_or_error resource_state_or_error = {0};
        otc_status status = otc__canonical_enforce_resource_lifetime(&resource_state, &lifetime_action, &resource_state_or_error);
        assert(status == OTC_E_NOT_BUILT);
        puts("B34.S1.A1 private_unimplemented_refusal");
    }
    { /* B34.S2.A4: direct constant-set candidate */
        otc_cp_station_sets station_sets = {0};
        otc_cp_original_recommendation original_recommendation = {0};
        otc_cp_commercial_only commercial_only = {0};
        otc_cp_effective_recommendation effective_recommendation = {0};
        otc_status status = otc__canonical_select_effective_recommendation(&station_sets, &original_recommendation, &commercial_only, &effective_recommendation);
        assert(status == OTC_E_NOT_BUILT);
        puts("B34.S2.A4 private_unimplemented_refusal");
    }
    { /* B34.S2.A6: candidate uses offsets */
        otc_cp_station_source_row station_source_row = {0};
        otc_cp_path_request path_request = {0};
        otc_cp_release_view release_view = {0};
        otc_cp_selected_reference_path selected_reference_path = {0};
        otc_status status = otc__canonical_resolve_reference_path(&station_source_row, &path_request, &release_view, &selected_reference_path);
        assert(status == OTC_E_NOT_BUILT);
        puts("B34.S2.A6 private_unimplemented_refusal");
    }
    { /* B34.S3.A3: a direct candidate with effective recommendation or a resolved offset candidate exists */
        otc_cp_candidate_path candidate_path = {0};
        otc_cp_include_flagged include_flagged = {0};
        otc_cp_include_fallback include_fallback = {0};
        otc_cp_quality_admission quality_admission = {0};
        otc_status status = otc__canonical_admit_quality_path(&candidate_path, &include_flagged, &include_fallback, &quality_admission);
        assert(status == OTC_E_NOT_BUILT);
        puts("B34.S3.A3 private_unimplemented_refusal");
    }
    { /* B34.S3.A4: quality admission passed */
        otc_cp_candidate_path candidate_path = {0};
        otc_cp_commercial_only commercial_only = {0};
        otc_cp_commercial_basis commercial_basis = {0};
        otc_cp_commercial_admission commercial_admission = {0};
        otc_status status = otc__canonical_admit_commercial_path(&candidate_path, &commercial_only, &commercial_basis, &commercial_admission);
        assert(status == OTC_E_NOT_BUILT);
        puts("B34.S3.A4 private_unimplemented_refusal");
    }
    { /* B34.S3.A8: candidate path is historical and earlier gates pass */
        otc_cp_own_offset own_offset = {0};
        otc_cp_reference_path reference_path = {0};
        otc_cp_historical_policy historical_policy = {0};
        otc_cp_selection_kind selection_kind = {0};
        otc_cp_reader_version reader_version = {0};
        otc_cp_historical_admission historical_admission = {0};
        otc_status status = otc__canonical_admit_historical_offset(&own_offset, &reference_path, &historical_policy, &selection_kind, &reader_version, &historical_admission);
        assert(status == OTC_E_NOT_BUILT);
        puts("B34.S3.A8 private_unimplemented_refusal");
    }
    { /* B35.S1.A1: summary_kind = stats */
        otc_cp_release_view release_view = {0};
        otc_cp_release_statistics release_statistics = {0};
        otc_status status = otc__canonical_count_release_statistics(&release_view, &release_statistics);
        assert(status == OTC_E_NOT_BUILT);
        puts("B35.S1.A1 private_unimplemented_refusal");
    }
    { /* B35.S1.A2: summary_kind = constant_sets */
        otc_cp_station_sets station_sets = {0};
        otc_cp_original_recommendation original_recommendation = {0};
        otc_cp_commercial_only commercial_only = {0};
        otc_cp_include_no_constants include_no_constants = {0};
        otc_cp_ordered_constant_sets ordered_constant_sets = {0};
        otc_status status = otc__canonical_order_constant_sets(&station_sets, &original_recommendation, &commercial_only, &include_no_constants, &ordered_constant_sets);
        assert(status == OTC_E_NOT_BUILT);
        puts("B35.S1.A2 private_unimplemented_refusal");
    }
    { /* B36.S7.A2: own-offset and policy gates pass */
        otc_cp_station_request station_request = {0};
        otc_cp_release_view release_view = {0};
        otc_cp_selection_options selection_options = {0};
        otc_cp_reader_version reader_version = {0};
        otc_cp_selected_prediction_model selected_prediction_model = {0};
        otc_status status = otc__canonical_select_prediction_model(&station_request, &release_view, &selection_options, &reader_version, &selected_prediction_model);
        assert(status == OTC_E_NOT_BUILT);
        puts("B36.S7.A2 private_unimplemented_refusal");
    }
    { /* B37.S1.A2: Station argument supplied */
        otc_cp_station station = {0};
        otc_cp_release_origin release_origin = {0};
        otc_cp_valid_station valid_station = {0};
        otc_status status = otc__canonical_check_station_origin(&station, &release_origin, &valid_station);
        assert(status == OTC_E_NOT_BUILT);
        puts("B37.S1.A2 private_unimplemented_refusal");
    }
    { /* B37.S2.A3: commercial direct-source attribution */
        otc_cp_station_sets station_sets = {0};
        otc_cp_original_recommendation original_recommendation = {0};
        otc_cp_commercial_only commercial_only = {0};
        otc_cp_effective_recommendation effective_recommendation = {0};
        otc_status status = otc__canonical_select_effective_recommendation(&station_sets, &original_recommendation, &commercial_only, &effective_recommendation);
        assert(status == OTC_E_NOT_BUILT);
        puts("B37.S2.A3 private_unimplemented_refusal");
    }
    { /* B37.S2.A5: commercial approved offset-source attribution */
        otc_cp_station_source_row station_source_row = {0};
        otc_cp_path_request path_request = {0};
        otc_cp_release_view release_view = {0};
        otc_cp_selected_reference_path selected_reference_path = {0};
        otc_status status = otc__canonical_resolve_reference_path(&station_source_row, &path_request, &release_view, &selected_reference_path);
        assert(status == OTC_E_NOT_BUILT);
        puts("B37.S2.A5 private_unimplemented_refusal");
    }
    { /* B40.S1.A2: Station object supplied */
        otc_cp_station station = {0};
        otc_cp_release_origin release_origin = {0};
        otc_cp_valid_station valid_station = {0};
        otc_status status = otc__canonical_check_station_origin(&station, &release_origin, &valid_station);
        assert(status == OTC_E_NOT_BUILT);
        puts("B40.S1.A2 private_unimplemented_refusal");
    }
    { /* B40.S1.A3: station ID supplied */
        otc_cp_release_view release_view = {0};
        otc_cp_identity_query identity_query = {0};
        otc_cp_reader_version reader_version = {0};
        otc_cp_station_or_tombstone_or_null station_or_tombstone_or_null = {0};
        otc_status status = otc__canonical_lookup_station_identity(&release_view, &identity_query, &reader_version, &station_or_tombstone_or_null);
        assert(status == OTC_E_NOT_BUILT);
        puts("B40.S1.A3 private_unimplemented_refusal");
    }
    { /* B40.S2.A4: no explicit set selected */
        otc_cp_station_sets station_sets = {0};
        otc_cp_original_recommendation original_recommendation = {0};
        otc_cp_commercial_only commercial_only = {0};
        otc_cp_effective_recommendation effective_recommendation = {0};
        otc_status status = otc__canonical_select_effective_recommendation(&station_sets, &original_recommendation, &commercial_only, &effective_recommendation);
        assert(status == OTC_E_NOT_BUILT);
        puts("B40.S2.A4 private_unimplemented_refusal");
    }
    { /* B42.S1.A2: for each instant; never for an empty input */
        otc_cp_selected_prediction_model selected_prediction_model = {0};
        otc_cp_utc_instant utc_instant = {0};
        otc_cp_astronomical_terms astronomical_terms = {0};
        otc_status status = otc__canonical_evaluate_astronomy(&selected_prediction_model, &utc_instant, &astronomical_terms);
        assert(status == OTC_E_NOT_BUILT);
        puts("B42.S1.A2 private_unimplemented_refusal");
    }
    { /* B43.S1.A1: always after model/window checks */
        otc_cp_selected_prediction_model selected_prediction_model = {0};
        otc_cp_prediction_window prediction_window = {0};
        otc_cp_unrounded_tide_events unrounded_tide_events = {0};
        otc_status status = otc__canonical_find_unrounded_tide_events(&selected_prediction_model, &prediction_window, &unrounded_tide_events);
        assert(status == OTC_E_NOT_BUILT);
        puts("B43.S1.A1 private_unimplemented_refusal");
    }
    { /* B44.S1.A1: current_operation = current_events */
        otc_cp_selected_prediction_model selected_prediction_model = {0};
        otc_cp_prediction_window prediction_window = {0};
        otc_cp_current_request current_request = {0};
        otc_cp_unrounded_current_events unrounded_current_events = {0};
        otc_status status = otc__canonical_find_unrounded_current_events(&selected_prediction_model, &prediction_window, &current_request, &unrounded_current_events);
        assert(status == OTC_E_NOT_BUILT);
        puts("B44.S1.A1 private_unimplemented_refusal");
    }
    { /* B45.S2.A3: historical own offset */
        otc_cp_own_offset own_offset = {0};
        otc_cp_reference_path reference_path = {0};
        otc_cp_historical_policy historical_policy = {0};
        otc_cp_selection_kind selection_kind = {0};
        otc_cp_reader_version reader_version = {0};
        otc_cp_historical_admission historical_admission = {0};
        otc_status status = otc__canonical_admit_historical_offset(&own_offset, &reference_path, &historical_policy, &selection_kind, &reader_version, &historical_admission);
        assert(status == OTC_E_NOT_BUILT);
        puts("B45.S2.A3 private_unimplemented_refusal");
    }
    { /* B45.S3.A2: reference exists and admission passes */
        otc_cp_station_request station_request = {0};
        otc_cp_release_view release_view = {0};
        otc_cp_selection_options selection_options = {0};
        otc_cp_reader_version reader_version = {0};
        otc_cp_selected_prediction_model selected_prediction_model = {0};
        otc_status status = otc__canonical_select_prediction_model(&station_request, &release_view, &selection_options, &reader_version, &selected_prediction_model);
        assert(status == OTC_E_NOT_BUILT);
        puts("B45.S3.A2 private_unimplemented_refusal");
    }
    { /* B45.S6.A2: extrema request after reference science, datum and ratio guards pass */
        otc_cp_selected_prediction_model selected_prediction_model = {0};
        otc_cp_prediction_window prediction_window = {0};
        otc_cp_unrounded_tide_events unrounded_tide_events = {0};
        otc_status status = otc__canonical_find_unrounded_tide_events(&selected_prediction_model, &prediction_window, &unrounded_tide_events);
        assert(status == OTC_E_NOT_BUILT);
        puts("B45.S6.A2 private_unimplemented_refusal");
    }
    { /* B45.S7.A3: exact equal offsets and a full-curve request */
        otc_cp_own_offset own_offset = {0};
        otc_cp_reference_model reference_model = {0};
        otc_cp_prediction_instants prediction_instants = {0};
        otc_cp_requested_datum requested_datum = {0};
        otc_cp_folded_height_values folded_height_values = {0};
        otc_status status = otc__canonical_fold_equal_tide_offset(&own_offset, &reference_model, &prediction_instants, &requested_datum, &folded_height_values);
        assert(status == OTC_E_NOT_BUILT);
        puts("B45.S7.A3 private_unimplemented_refusal");
    }
    { /* B46.S3.A2: folded model and valid target instants */
        otc_cp_selected_prediction_model selected_prediction_model = {0};
        otc_cp_prediction_instants prediction_instants = {0};
        otc_cp_requested_datum requested_datum = {0};
        otc_cp_height_values height_values = {0};
        otc_status status = otc__canonical_evaluate_harmonic_height(&selected_prediction_model, &prediction_instants, &requested_datum, &height_values);
        assert(status == OTC_E_NOT_BUILT);
        puts("B46.S3.A2 private_unimplemented_refusal");
    }
    { /* B47.S2.A2: actual reference entry exists */
        otc_cp_station_request station_request = {0};
        otc_cp_release_view release_view = {0};
        otc_cp_selection_options selection_options = {0};
        otc_cp_reader_version reader_version = {0};
        otc_cp_selected_prediction_model selected_prediction_model = {0};
        otc_status status = otc__canonical_select_prediction_model(&station_request, &release_view, &selection_options, &reader_version, &selected_prediction_model);
        assert(status == OTC_E_NOT_BUILT);
        puts("B47.S2.A2 private_unimplemented_refusal");
    }
    { /* B47.S4.A3: current-offset event request after reference science passes */
        otc_cp_selected_prediction_model selected_prediction_model = {0};
        otc_cp_prediction_window prediction_window = {0};
        otc_cp_current_request current_request = {0};
        otc_cp_unrounded_current_events unrounded_current_events = {0};
        otc_status status = otc__canonical_find_unrounded_current_events(&selected_prediction_model, &prediction_window, &current_request, &unrounded_current_events);
        assert(status == OTC_E_NOT_BUILT);
        puts("B47.S4.A3 private_unimplemented_refusal");
    }
    { /* B48.S1.A1: auxiliary_kind = model_access */
        otc_cp_auxiliary_operation auxiliary_operation = {0};
        otc_cp_source_values source_values = {0};
        otc_cp_selection_options selection_options = {0};
        otc_cp_reader_version reader_version = {0};
        otc_cp_auxiliary_member_id auxiliary_member_id = {0};
        otc_cp_auxiliary_model_value auxiliary_model_value = {0};
        otc_status status = otc__canonical_read_auxiliary_model_value(&auxiliary_operation, &source_values, &selection_options, &reader_version, &auxiliary_member_id, &auxiliary_model_value);
        assert(status == OTC_E_NOT_BUILT);
        puts("B48.S1.A1 private_unimplemented_refusal");
    }
    { /* B48.S1.A2: auxiliary_kind = result_context */
        otc_cp_result_values result_values = {0};
        otc_cp_result_context result_context = {0};
        otc_cp_prediction_result prediction_result = {0};
        otc_status status = otc__canonical_construct_prediction_result(&result_values, &result_context, &prediction_result);
        assert(status == OTC_E_NOT_BUILT);
        puts("B48.S1.A2 private_unimplemented_refusal");
    }
    { /* B48.S1.A3: auxiliary_kind = local_time */
        otc_cp_utc_result utc_result = {0};
        otc_cp_local_time_profile local_time_profile = {0};
        otc_cp_local_time_result local_time_result = {0};
        otc_status status = otc__canonical_convert_result_to_local_time(&utc_result, &local_time_profile, &local_time_result);
        assert(status == OTC_E_NOT_BUILT);
        puts("B48.S1.A3 private_unimplemented_refusal");
    }
    { /* B35.sets.S1.A1: always */
        otc_cp_station_sets station_sets = {0};
        otc_cp_original_recommendation original_recommendation = {0};
        otc_cp_commercial_only commercial_only = {0};
        otc_cp_effective_recommendation effective_recommendation = {0};
        otc_status status = otc__canonical_select_effective_recommendation(&station_sets, &original_recommendation, &commercial_only, &effective_recommendation);
        assert(status == OTC_E_NOT_BUILT);
        puts("B35.sets.S1.A1 private_unimplemented_refusal");
    }
    { /* B48.aux.S2.A1: copied auxiliary contract requires model selection */
        otc_cp_station_request station_request = {0};
        otc_cp_release_view release_view = {0};
        otc_cp_selection_options selection_options = {0};
        otc_cp_reader_version reader_version = {0};
        otc_cp_selected_prediction_model selected_prediction_model = {0};
        otc_status status = otc__canonical_select_prediction_model(&station_request, &release_view, &selection_options, &reader_version, &selected_prediction_model);
        assert(status == OTC_E_NOT_BUILT);
        puts("B48.aux.S2.A1 private_unimplemented_refusal");
    }
    { /* B48.aux.S2.A2: auxiliary_operation requires astronomy and successful model selection */
        otc_cp_selected_prediction_model selected_prediction_model = {0};
        otc_cp_utc_instant utc_instant = {0};
        otc_cp_astronomical_terms astronomical_terms = {0};
        otc_status status = otc__canonical_evaluate_astronomy(&selected_prediction_model, &utc_instant, &astronomical_terms);
        assert(status == OTC_E_NOT_BUILT);
        puts("B48.aux.S2.A2 private_unimplemented_refusal");
    }
    { /* B43.roots.S1.A2: for each grid or root-search evaluation instant */
        otc_cp_selected_prediction_model selected_prediction_model = {0};
        otc_cp_utc_instant utc_instant = {0};
        otc_cp_astronomical_terms astronomical_terms = {0};
        otc_status status = otc__canonical_evaluate_astronomy(&selected_prediction_model, &utc_instant, &astronomical_terms);
        assert(status == OTC_E_NOT_BUILT);
        puts("B43.roots.S1.A2 private_unimplemented_refusal");
    }
    { /* B44.roots.S2.A2: for each current evaluation instant */
        otc_cp_selected_prediction_model selected_prediction_model = {0};
        otc_cp_utc_instant utc_instant = {0};
        otc_cp_astronomical_terms astronomical_terms = {0};
        otc_status status = otc__canonical_evaluate_astronomy(&selected_prediction_model, &utc_instant, &astronomical_terms);
        assert(status == OTC_E_NOT_BUILT);
        puts("B44.roots.S2.A2 private_unimplemented_refusal");
    }
    { /* B17.sidecar.S1.A3: descriptor has no usable local checksum bytes and online acquisition is permitted */
        otc_cp_http_request http_request = {0};
        otc_cp_transport_options transport_options = {0};
        otc_cp_http_response http_response = {0};
        otc_status status = otc__canonical_request_http_resource(&http_request, &transport_options, &http_response);
        assert(status == OTC_E_NOT_BUILT);
        puts("B17.sidecar.S1.A3 private_unimplemented_refusal");
    }
    return 0;
}
