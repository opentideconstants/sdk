import type * as C from './canonical-types.js';

/** A private seam has been constructed, but its wider algorithm remains on the primary body. */
export class CanonicalUnimplementedError extends Error {
    constructor(readonly behavior: string) {
        super(`Private canonical seam ${behavior} is unimplemented`);
        this.name = 'CanonicalUnimplementedError';
    }
}

export function validate_operation_arguments(operation: C.operation, operation_arguments: C.arguments, member_contract: C.member_contract): C.validated_arguments {
    throw new CanonicalUnimplementedError("B01");
}

export function resolve_effective_options(explicit_options: C.explicit_options, environment: C.environment, platform_defaults: C.platform_defaults): C.effective_options {
    throw new CanonicalUnimplementedError("B02");
}

export function select_canonical_error(operation: C.operation, ordered_failures: C.ordered_failures, cause: C.cause): C.canonical_error {
    throw new CanonicalUnimplementedError("B03");
}

export function translate_native_binding(inputs: C.NativeBindingInputs): C.native_result {
    throw new CanonicalUnimplementedError("B04");
}

export function decode_release_document(source_bytes: C.source_bytes, reader_version: C.reader_version, document_kind: C.document_kind): C.parsed_document {
    throw new CanonicalUnimplementedError("B05");
}

export function validate_release_links(parsed_document: C.parsed_document, required_links: C.required_links): C.validated_release_graph {
    throw new CanonicalUnimplementedError("B06");
}

export function materialize_typed_model(raw_fields: C.raw_fields, field_contract: C.field_contract, origin: C.origin, model_type: C.model_type): C.typed_model {
    throw new CanonicalUnimplementedError("B07");
}

export function access_raw_record(access_kind: C.access_kind, source_record: C.source_record, station: C.station, release_origin: C.release_origin, native_profile: C.native_profile): C.raw_record_or_valid_station {
    throw new CanonicalUnimplementedError("B08");
}

export async function open_client_release(operation_arguments: C.arguments, environment: C.environment, platform_defaults: C.platform_defaults, cache_state: C.cache_state, clock: C.clock, native_profile: C.native_profile, reader_version: C.reader_version): Promise<C.client_and_release> {
    throw new CanonicalUnimplementedError("B09");
}

export async function resolve_release_request(release_request: C.release_request, effective_options: C.effective_options, cache_state: C.cache_state, clock: C.clock, reader_version: C.reader_version): Promise<C.loaded_release> {
    throw new CanonicalUnimplementedError("B10");
}

export async function exchange_release_metadata(metadata_request: C.metadata_request, trusted_cache: C.trusted_cache, transport_options: C.transport_options, cache_state: C.cache_state, clock: C.clock, reader_version: C.reader_version): Promise<C.validated_metadata> {
    throw new CanonicalUnimplementedError("B11");
}

export async function update_client_release(client_state: C.client_state, update_request: C.update_request, clock: C.clock, reader_version: C.reader_version): Promise<C.updated_client_state> {
    throw new CanonicalUnimplementedError("B12");
}

export async function refresh_client_if_due(client_state: C.client_state, query_kind: C.query_kind, clock: C.clock, reader_version: C.reader_version): Promise<C.query_client_state> {
    throw new CanonicalUnimplementedError("B13");
}

export function forward_held_release(held_release: C.held_release, query_arguments: C.query_arguments): C.held_release_result {
    throw new CanonicalUnimplementedError("B14");
}

export function enforce_resource_lifetime(resource_state: C.resource_state, lifetime_action: C.lifetime_action): C.resource_state_or_error {
    throw new CanonicalUnimplementedError("B15");
}

export function bind_checksum_manifest(checksum_bytes: C.checksum_bytes, pointer_digests: C.pointer_digests, required_files: C.required_files): C.bound_checksums {
    throw new CanonicalUnimplementedError("B16");
}

export async function acquire_release_files(acquisition_descriptor: C.acquisition_descriptor, effective_options: C.effective_options, load_mode: C.load_mode, cache_state: C.cache_state, clock: C.clock, reader_version: C.reader_version): Promise<C.loaded_release> {
    throw new CanonicalUnimplementedError("B17");
}

export function merge_cache_receipt(locked_cache_state: C.locked_cache_state, verified_file_rows: C.verified_file_rows, release_metadata: C.release_metadata): C.merged_receipt {
    throw new CanonicalUnimplementedError("B18");
}

export async function select_cached_release(release_candidates: C.release_candidates, effective_options: C.effective_options, cache_state: C.cache_state, clock: C.clock): Promise<C.usable_cached_release_or_error> {
    throw new CanonicalUnimplementedError("B19");
}

export async function verify_release_files(release_files: C.release_files, trusted_cached_pointer: C.trusted_cached_pointer): Promise<C.verification_result> {
    throw new CanonicalUnimplementedError("B20");
}

export async function publish_download(destination: C.destination, format_selection: C.format_selection, overwrite_policy: C.overwrite_policy, release_files: C.release_files, checksum_bytes: C.checksum_bytes, pointer_digests: C.pointer_digests): Promise<C.download_result> {
    throw new CanonicalUnimplementedError("B21");
}

export async function manage_cache_inventory(inventory_action: C.inventory_action, cache_state: C.cache_state, keep: C.keep, current_cache_directory: C.current_cache_directory, clock: C.clock): Promise<C.cache_inventory_result> {
    throw new CanonicalUnimplementedError("B22");
}

export async function perform_guarded_io(io_kind: C.io_kind, io_request: C.io_request, io_options: C.io_options, clock: C.clock): Promise<C.io_result> {
    throw new CanonicalUnimplementedError("B23");
}

export function project_station_index(station_source_row: C.station_source_row, source_byte_span: C.source_byte_span, projection_contract: C.projection_contract): C.station_index_entry {
    throw new CanonicalUnimplementedError("B24");
}

export async function authenticate_station_index(source_files: C.source_files, supplied_index: C.supplied_index, index_presence: C.index_presence, reader_version: C.reader_version): Promise<C.authenticated_index> {
    throw new CanonicalUnimplementedError("B25");
}

export function compare_station_source(index_entry: C.index_entry, station_source_row: C.station_source_row, index_presence: C.index_presence): C.compared_station_row {
    throw new CanonicalUnimplementedError("B26");
}

export function read_station_lazily(stream_reader: C.stream_reader, station_id: C.station_id, release_origin: C.release_origin, reader_version: C.reader_version): C.station_source_row {
    throw new CanonicalUnimplementedError("B27");
}

export function encode_cache_json(cache_document: C.cache_document): C.cache_bytes {
    throw new CanonicalUnimplementedError("B28");
}

export function lookup_station_identity(release_view: C.release_view, identity_query: C.identity_query, reader_version: C.reader_version): C.station_or_tombstone_or_null {
    throw new CanonicalUnimplementedError("B29");
}

export function select_effective_recommendation(station_sets: C.station_sets, original_recommendation: C.original_recommendation, commercial_only: C.commercial_only): C.effective_recommendation {
    throw new CanonicalUnimplementedError("B30");
}

export function admit_quality_path(candidate_path: C.candidate_path, include_flagged: C.include_flagged, include_fallback: C.include_fallback): C.quality_admission {
    throw new CanonicalUnimplementedError("B31");
}

export function admit_commercial_path(candidate_path: C.candidate_path, commercial_only: C.commercial_only, commercial_basis: C.commercial_basis): C.commercial_admission {
    throw new CanonicalUnimplementedError("B32");
}

export function resolve_reference_path(station_source_row: C.station_source_row, path_request: C.path_request, release_view: C.release_view): C.selected_reference_path {
    throw new CanonicalUnimplementedError("B33");
}

export function execute_discovery_query(release_view: C.release_view, query_kind: C.query_kind, query_options: C.query_options, reader_version: C.reader_version): C.ordered_station_results {
    throw new CanonicalUnimplementedError("B34");
}

export function summarize_station_sets(summary_kind: C.summary_kind, release_view: C.release_view, station_sets: C.station_sets, summary_options: C.summary_options): C.station_summary {
    throw new CanonicalUnimplementedError("B35");
}

export function admit_historical_offset(own_offset: C.own_offset, reference_path: C.reference_path, historical_policy: C.historical_policy, selection_kind: C.selection_kind, reader_version: C.reader_version): C.historical_admission {
    throw new CanonicalUnimplementedError("B36");
}

export function format_attribution(station: C.station, release_view: C.release_view, commercial_only: C.commercial_only): C.attribution_text {
    throw new CanonicalUnimplementedError("B37");
}

export function format_citation(published_metadata: C.published_metadata, citation_style: C.citation_style): C.citation_text {
    throw new CanonicalUnimplementedError("B38");
}

export function parse_prediction_window(time_inputs: C.time_inputs, window_inputs: C.window_inputs, step: C.step, local_time_profile: C.local_time_profile): C.prediction_window {
    throw new CanonicalUnimplementedError("B39");
}

export function select_prediction_model(station_request: C.station_request, release_view: C.release_view, selection_options: C.selection_options, reader_version: C.reader_version): C.selected_prediction_model {
    throw new CanonicalUnimplementedError("B40");
}

export function evaluate_astronomy(selected_prediction_model: C.selected_prediction_model, utc_instant: C.utc_instant): C.astronomical_terms {
    throw new CanonicalUnimplementedError("B41");
}

export function evaluate_harmonic_height(selected_prediction_model: C.selected_prediction_model, prediction_instants: C.prediction_instants, requested_datum: C.requested_datum): C.height_values {
    throw new CanonicalUnimplementedError("B42");
}

export function find_tide_events(selected_prediction_model: C.selected_prediction_model, prediction_window: C.prediction_window): C.tide_events {
    throw new CanonicalUnimplementedError("B43");
}

export function evaluate_direct_current(selected_prediction_model: C.selected_prediction_model, prediction_window: C.prediction_window, current_request: C.current_request, current_operation: C.current_operation): C.direct_current_result {
    throw new CanonicalUnimplementedError("B44");
}

export function evaluate_tide_offset(own_offset: C.own_offset, reference_path: C.reference_path, prediction_window: C.prediction_window, tide_request: C.tide_request, reader_version: C.reader_version): C.offset_tide_result {
    throw new CanonicalUnimplementedError("B45");
}

export function fold_equal_tide_offset(own_offset: C.own_offset, reference_model: C.reference_model, prediction_instants: C.prediction_instants, requested_datum: C.requested_datum): C.folded_height_values {
    throw new CanonicalUnimplementedError("B46");
}

export function evaluate_current_offset(own_current_offsets: C.own_current_offsets, reference_path: C.reference_path, prediction_window: C.prediction_window, current_request: C.current_request, reader_version: C.reader_version): C.offset_current_result {
    throw new CanonicalUnimplementedError("B47");
}

export function dispatch_auxiliary_result(auxiliary_kind: C.auxiliary_kind, auxiliary_operation: C.auxiliary_operation, source_values: C.source_values, result_context: C.result_context, local_time_profile: C.local_time_profile, result_values: C.result_values, utc_result: C.utc_result, selection_options: C.selection_options, reader_version: C.reader_version, auxiliary_member_id: C.auxiliary_member_id): C.auxiliary_result {
    throw new CanonicalUnimplementedError("B48");
}

export function retain_raw_source_record(source_record: C.source_record, native_profile: C.native_profile): C.raw_record {
    throw new CanonicalUnimplementedError("B08.raw");
}

export function check_station_origin(station: C.station, release_origin: C.release_origin): C.valid_station {
    throw new CanonicalUnimplementedError("B08.origin");
}

export async function manage_cache_lock(lock_request: C.lock_request, lock_state: C.lock_state, clock: C.clock): Promise<C.lock_outcome> {
    throw new CanonicalUnimplementedError("B23.lock");
}

export async function request_http_resource(http_request: C.http_request, transport_options: C.transport_options): Promise<C.http_response> {
    throw new CanonicalUnimplementedError("B23.http");
}

export function count_release_statistics(release_view: C.release_view): C.release_statistics {
    throw new CanonicalUnimplementedError("B35.stats");
}

export function order_constant_sets(station_sets: C.station_sets, original_recommendation: C.original_recommendation, commercial_only: C.commercial_only, include_no_constants: C.include_no_constants): C.ordered_constant_sets {
    throw new CanonicalUnimplementedError("B35.sets");
}

export function read_auxiliary_model_value(auxiliary_operation: C.auxiliary_operation, source_values: C.source_values, selection_options: C.selection_options, reader_version: C.reader_version, auxiliary_member_id: C.auxiliary_member_id): C.auxiliary_model_value {
    throw new CanonicalUnimplementedError("B48.aux");
}

export function construct_prediction_result(result_values: C.result_values, result_context: C.result_context): C.prediction_result {
    throw new CanonicalUnimplementedError("B48.context");
}

export function convert_result_to_local_time(utc_result: C.utc_result, local_time_profile: C.local_time_profile): C.local_time_result {
    throw new CanonicalUnimplementedError("B48.local");
}

export function find_unrounded_tide_events(selected_prediction_model: C.selected_prediction_model, prediction_window: C.prediction_window): C.unrounded_tide_events {
    throw new CanonicalUnimplementedError("B43.roots");
}

export function find_unrounded_current_events(selected_prediction_model: C.selected_prediction_model, prediction_window: C.prediction_window, current_request: C.current_request): C.unrounded_current_events {
    throw new CanonicalUnimplementedError("B44.roots");
}

export async function acquire_checksum_sidecar(acquisition_descriptor: C.acquisition_descriptor, effective_options: C.effective_options): Promise<C.checksum_bytes> {
    throw new CanonicalUnimplementedError("B17.sidecar");
}
