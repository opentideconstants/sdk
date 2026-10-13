"""Private construction seams; all bodies deliberately incomplete."""

from __future__ import annotations
from . import _canonical_types as T


def _validate_operation_arguments(
    *,
    operation: T._COperation,
    arguments: T._CArguments,
    member_contract: T._CMemberContract,
) -> T._CValidatedArguments:
    raise NotImplementedError("B01 construction-only; body incomplete")


def _resolve_effective_options(
    *,
    explicit_options: T._CExplicitOptions,
    environment: T._CEnvironment,
    platform_defaults: T._CPlatformDefaults,
) -> T._CEffectiveOptions:
    raise NotImplementedError("B02 construction-only; body incomplete")


def _select_canonical_error(
    *, operation: T._COperation, ordered_failures: T._COrderedFailures, cause: T._CCause
) -> T._CCanonicalError:
    raise NotImplementedError("B03 construction-only; body incomplete")


def _translate_native_binding(
    *,
    canonical_result: T._CCanonicalResult,
    canonical_error: T._CCanonicalError,
    native_profile: T._CNativeProfile,
) -> T._CNativeResult:
    raise NotImplementedError("B04 construction-only; body incomplete")


def _decode_release_document(
    *,
    source_bytes: T._CSourceBytes,
    reader_version: T._CReaderVersion,
    document_kind: T._CDocumentKind,
) -> T._CParsedDocument:
    raise NotImplementedError("B05 construction-only; body incomplete")


def _validate_release_links(
    *, parsed_document: T._CParsedDocument, required_links: T._CRequiredLinks
) -> T._CValidatedReleaseGraph:
    raise NotImplementedError("B06 construction-only; body incomplete")


def _materialize_typed_model(
    *,
    raw_fields: T._CRawFields,
    field_contract: T._CFieldContract,
    origin: T._COrigin,
    model_type: T._CModelType,
) -> T._CTypedModel:
    raise NotImplementedError("B07 construction-only; body incomplete")


def _access_raw_record(
    *,
    access_kind: T._CAccessKind,
    source_record: T._CSourceRecord,
    station: T._CStation,
    release_origin: T._CReleaseOrigin,
    native_profile: T._CNativeProfile,
) -> T._CRawRecordOrValidStation:
    raise NotImplementedError("B08 construction-only; body incomplete")


def _open_client_release(
    *,
    arguments: T._CArguments,
    environment: T._CEnvironment,
    platform_defaults: T._CPlatformDefaults,
    cache_state: T._CCacheState,
    clock: T._CClock,
    native_profile: T._CNativeProfile,
    reader_version: T._CReaderVersion,
) -> T._CClientAndRelease:
    raise NotImplementedError("B09 construction-only; body incomplete")


def _resolve_release_request(
    *,
    release_request: T._CReleaseRequest,
    effective_options: T._CEffectiveOptions,
    cache_state: T._CCacheState,
    clock: T._CClock,
    reader_version: T._CReaderVersion,
) -> T._CLoadedRelease:
    raise NotImplementedError("B10 construction-only; body incomplete")


def _exchange_release_metadata(
    *,
    metadata_request: T._CMetadataRequest,
    trusted_cache: T._CTrustedCache,
    transport_options: T._CTransportOptions,
    cache_state: T._CCacheState,
    clock: T._CClock,
    reader_version: T._CReaderVersion,
) -> T._CValidatedMetadata:
    raise NotImplementedError("B11 construction-only; body incomplete")


def _update_client_release(
    *,
    client_state: T._CClientState,
    update_request: T._CUpdateRequest,
    clock: T._CClock,
    reader_version: T._CReaderVersion,
) -> T._CUpdatedClientState:
    raise NotImplementedError("B12 construction-only; body incomplete")


def _refresh_client_if_due(
    *,
    client_state: T._CClientState,
    query_kind: T._CQueryKind,
    clock: T._CClock,
    reader_version: T._CReaderVersion,
) -> T._CQueryClientState:
    raise NotImplementedError("B13 construction-only; body incomplete")


def _forward_held_release(
    *, held_release: T._CHeldRelease, query_arguments: T._CQueryArguments
) -> T._CHeldReleaseResult:
    raise NotImplementedError("B14 construction-only; body incomplete")


def _enforce_resource_lifetime(
    *, resource_state: T._CResourceState, lifetime_action: T._CLifetimeAction
) -> T._CResourceStateOrError:
    raise NotImplementedError("B15 construction-only; body incomplete")


def _bind_checksum_manifest(
    *,
    checksum_bytes: T._CChecksumBytes,
    pointer_digests: T._CPointerDigests,
    required_files: T._CRequiredFiles,
) -> T._CBoundChecksums:
    raise NotImplementedError("B16 construction-only; body incomplete")


def _acquire_release_files(
    *,
    acquisition_descriptor: T._CAcquisitionDescriptor,
    effective_options: T._CEffectiveOptions,
    load_mode: T._CLoadMode,
    cache_state: T._CCacheState,
    clock: T._CClock,
    reader_version: T._CReaderVersion,
) -> T._CLoadedRelease:
    raise NotImplementedError("B17 construction-only; body incomplete")


def _merge_cache_receipt(
    *,
    locked_cache_state: T._CLockedCacheState,
    verified_file_rows: T._CVerifiedFileRows,
    release_metadata: T._CReleaseMetadata,
) -> T._CMergedReceipt:
    raise NotImplementedError("B18 construction-only; body incomplete")


def _select_cached_release(
    *,
    release_candidates: T._CReleaseCandidates,
    effective_options: T._CEffectiveOptions,
    cache_state: T._CCacheState,
    clock: T._CClock,
) -> T._CUsableCachedReleaseOrError:
    raise NotImplementedError("B19 construction-only; body incomplete")


def _verify_release_files(
    *, release_files: T._CReleaseFiles, trusted_cached_pointer: T._CTrustedCachedPointer
) -> T._CVerificationResult:
    raise NotImplementedError("B20 construction-only; body incomplete")


def _publish_download(
    *,
    destination: T._CDestination,
    format_selection: T._CFormatSelection,
    overwrite_policy: T._COverwritePolicy,
    release_files: T._CReleaseFiles,
    checksum_bytes: T._CChecksumBytes,
    pointer_digests: T._CPointerDigests,
) -> T._CDownloadResult:
    raise NotImplementedError("B21 construction-only; body incomplete")


def _manage_cache_inventory(
    *,
    inventory_action: T._CInventoryAction,
    cache_state: T._CCacheState,
    keep: T._CKeep,
    current_cache_directory: T._CCurrentCacheDirectory,
    clock: T._CClock,
) -> T._CCacheInventoryResult:
    raise NotImplementedError("B22 construction-only; body incomplete")


def _perform_guarded_io(
    *,
    io_kind: T._CIoKind,
    io_request: T._CIoRequest,
    io_options: T._CIoOptions,
    clock: T._CClock,
) -> T._CIoResult:
    raise NotImplementedError("B23 construction-only; body incomplete")


def _project_station_index(
    *,
    station_source_row: T._CStationSourceRow,
    source_byte_span: T._CSourceByteSpan,
    projection_contract: T._CProjectionContract,
) -> T._CStationIndexEntry:
    raise NotImplementedError("B24 construction-only; body incomplete")


def _authenticate_station_index(
    *,
    source_files: T._CSourceFiles,
    supplied_index: T._CSuppliedIndex,
    index_presence: T._CIndexPresence,
    reader_version: T._CReaderVersion,
) -> T._CAuthenticatedIndex:
    raise NotImplementedError("B25 construction-only; body incomplete")


def _compare_station_source(
    *,
    index_entry: T._CIndexEntry,
    station_source_row: T._CStationSourceRow,
    index_presence: T._CIndexPresence,
) -> T._CComparedStationRow:
    raise NotImplementedError("B26 construction-only; body incomplete")


def _read_station_lazily(
    *,
    stream_reader: T._CStreamReader,
    station_id: T._CStationId,
    release_origin: T._CReleaseOrigin,
    reader_version: T._CReaderVersion,
) -> T._CStationSourceRow:
    raise NotImplementedError("B27 construction-only; body incomplete")


def _encode_cache_json(*, cache_document: T._CCacheDocument) -> T._CCacheBytes:
    raise NotImplementedError("B28 construction-only; body incomplete")


def _lookup_station_identity(
    *,
    release_view: T._CReleaseView,
    identity_query: T._CIdentityQuery,
    reader_version: T._CReaderVersion,
) -> T._CStationOrTombstoneOrNull:
    raise NotImplementedError("B29 construction-only; body incomplete")


def _select_effective_recommendation(
    *,
    station_sets: T._CStationSets,
    original_recommendation: T._COriginalRecommendation,
    commercial_only: T._CCommercialOnly,
) -> T._CEffectiveRecommendation:
    raise NotImplementedError("B30 construction-only; body incomplete")


def _admit_quality_path(
    *,
    candidate_path: T._CCandidatePath,
    include_flagged: T._CIncludeFlagged,
    include_fallback: T._CIncludeFallback,
) -> T._CQualityAdmission:
    raise NotImplementedError("B31 construction-only; body incomplete")


def _admit_commercial_path(
    *,
    candidate_path: T._CCandidatePath,
    commercial_only: T._CCommercialOnly,
    commercial_basis: T._CCommercialBasis,
) -> T._CCommercialAdmission:
    raise NotImplementedError("B32 construction-only; body incomplete")


def _resolve_reference_path(
    *,
    station_source_row: T._CStationSourceRow,
    path_request: T._CPathRequest,
    release_view: T._CReleaseView,
) -> T._CSelectedReferencePath:
    raise NotImplementedError("B33 construction-only; body incomplete")


def _execute_discovery_query(
    *,
    release_view: T._CReleaseView,
    query_kind: T._CQueryKind,
    query_options: T._CQueryOptions,
    reader_version: T._CReaderVersion,
) -> T._COrderedStationResults:
    raise NotImplementedError("B34 construction-only; body incomplete")


def _summarize_station_sets(
    *,
    summary_kind: T._CSummaryKind,
    release_view: T._CReleaseView,
    station_sets: T._CStationSets,
    summary_options: T._CSummaryOptions,
) -> T._CStationSummary:
    raise NotImplementedError("B35 construction-only; body incomplete")


def _admit_historical_offset(
    *,
    own_offset: T._COwnOffset,
    reference_path: T._CReferencePath,
    historical_policy: T._CHistoricalPolicy,
    selection_kind: T._CSelectionKind,
    reader_version: T._CReaderVersion,
) -> T._CHistoricalAdmission:
    raise NotImplementedError("B36 construction-only; body incomplete")


def _format_attribution(
    *,
    station: T._CStation,
    release_view: T._CReleaseView,
    commercial_only: T._CCommercialOnly,
) -> T._CAttributionText:
    raise NotImplementedError("B37 construction-only; body incomplete")


def _format_citation(
    *, published_metadata: T._CPublishedMetadata, citation_style: T._CCitationStyle
) -> T._CCitationText:
    raise NotImplementedError("B38 construction-only; body incomplete")


def _parse_prediction_window(
    *,
    time_inputs: T._CTimeInputs,
    window_inputs: T._CWindowInputs,
    step: T._CStep,
    local_time_profile: T._CLocalTimeProfile,
) -> T._CPredictionWindow:
    raise NotImplementedError("B39 construction-only; body incomplete")


def _select_prediction_model(
    *,
    station_request: T._CStationRequest,
    release_view: T._CReleaseView,
    selection_options: T._CSelectionOptions,
    reader_version: T._CReaderVersion,
) -> T._CSelectedPredictionModel:
    raise NotImplementedError("B40 construction-only; body incomplete")


def _evaluate_astronomy(
    *,
    selected_prediction_model: T._CSelectedPredictionModel,
    utc_instant: T._CUtcInstant,
) -> T._CAstronomicalTerms:
    raise NotImplementedError("B41 construction-only; body incomplete")


def _evaluate_harmonic_height(
    *,
    selected_prediction_model: T._CSelectedPredictionModel,
    prediction_instants: T._CPredictionInstants,
    requested_datum: T._CRequestedDatum,
) -> T._CHeightValues:
    raise NotImplementedError("B42 construction-only; body incomplete")


def _find_tide_events(
    *,
    selected_prediction_model: T._CSelectedPredictionModel,
    prediction_window: T._CPredictionWindow,
) -> T._CTideEvents:
    raise NotImplementedError("B43 construction-only; body incomplete")


def _evaluate_direct_current(
    *,
    selected_prediction_model: T._CSelectedPredictionModel,
    prediction_window: T._CPredictionWindow,
    current_request: T._CCurrentRequest,
    current_operation: T._CCurrentOperation,
) -> T._CDirectCurrentResult:
    raise NotImplementedError("B44 construction-only; body incomplete")


def _evaluate_tide_offset(
    *,
    own_offset: T._COwnOffset,
    reference_path: T._CReferencePath,
    prediction_window: T._CPredictionWindow,
    tide_request: T._CTideRequest,
    reader_version: T._CReaderVersion,
) -> T._COffsetTideResult:
    raise NotImplementedError("B45 construction-only; body incomplete")


def _fold_equal_tide_offset(
    *,
    own_offset: T._COwnOffset,
    reference_model: T._CReferenceModel,
    prediction_instants: T._CPredictionInstants,
    requested_datum: T._CRequestedDatum,
) -> T._CFoldedHeightValues:
    raise NotImplementedError("B46 construction-only; body incomplete")


def _evaluate_current_offset(
    *,
    own_current_offsets: T._COwnCurrentOffsets,
    reference_path: T._CReferencePath,
    prediction_window: T._CPredictionWindow,
    current_request: T._CCurrentRequest,
    reader_version: T._CReaderVersion,
) -> T._COffsetCurrentResult:
    raise NotImplementedError("B47 construction-only; body incomplete")


def _dispatch_auxiliary_result(
    *,
    auxiliary_kind: T._CAuxiliaryKind,
    auxiliary_operation: T._CAuxiliaryOperation,
    source_values: T._CSourceValues,
    result_context: T._CResultContext,
    local_time_profile: T._CLocalTimeProfile,
    result_values: T._CResultValues,
    utc_result: T._CUtcResult,
    selection_options: T._CSelectionOptions,
    reader_version: T._CReaderVersion,
    auxiliary_member_id: T._CAuxiliaryMemberId,
) -> T._CAuxiliaryResult:
    raise NotImplementedError("B48 construction-only; body incomplete")


def _retain_raw_source_record(
    *, source_record: T._CSourceRecord, native_profile: T._CNativeProfile
) -> T._CRawRecord:
    raise NotImplementedError("B08.raw construction-only; body incomplete")


def _check_station_origin(
    *, station: T._CStation, release_origin: T._CReleaseOrigin
) -> T._CValidStation:
    raise NotImplementedError("B08.origin construction-only; body incomplete")


def _manage_cache_lock(
    *, lock_request: T._CLockRequest, lock_state: T._CLockState, clock: T._CClock
) -> T._CLockOutcome:
    raise NotImplementedError("B23.lock construction-only; body incomplete")


def _request_http_resource(
    *, http_request: T._CHttpRequest, transport_options: T._CTransportOptions
) -> T._CHttpResponse:
    raise NotImplementedError("B23.http construction-only; body incomplete")


def _count_release_statistics(
    *, release_view: T._CReleaseView
) -> T._CReleaseStatistics:
    raise NotImplementedError("B35.stats construction-only; body incomplete")


def _order_constant_sets(
    *,
    station_sets: T._CStationSets,
    original_recommendation: T._COriginalRecommendation,
    commercial_only: T._CCommercialOnly,
    include_no_constants: T._CIncludeNoConstants,
) -> T._COrderedConstantSets:
    raise NotImplementedError("B35.sets construction-only; body incomplete")


def _read_auxiliary_model_value(
    *,
    auxiliary_operation: T._CAuxiliaryOperation,
    source_values: T._CSourceValues,
    selection_options: T._CSelectionOptions,
    reader_version: T._CReaderVersion,
    auxiliary_member_id: T._CAuxiliaryMemberId,
) -> T._CAuxiliaryModelValue:
    raise NotImplementedError("B48.aux construction-only; body incomplete")


def _construct_prediction_result(
    *, result_values: T._CResultValues, result_context: T._CResultContext
) -> T._CPredictionResult:
    raise NotImplementedError("B48.context construction-only; body incomplete")


def _convert_result_to_local_time(
    *, utc_result: T._CUtcResult, local_time_profile: T._CLocalTimeProfile
) -> T._CLocalTimeResult:
    raise NotImplementedError("B48.local construction-only; body incomplete")


def _find_unrounded_tide_events(
    *,
    selected_prediction_model: T._CSelectedPredictionModel,
    prediction_window: T._CPredictionWindow,
) -> T._CUnroundedTideEvents:
    raise NotImplementedError("B43.roots construction-only; body incomplete")


def _find_unrounded_current_events(
    *,
    selected_prediction_model: T._CSelectedPredictionModel,
    prediction_window: T._CPredictionWindow,
    current_request: T._CCurrentRequest,
) -> T._CUnroundedCurrentEvents:
    raise NotImplementedError("B44.roots construction-only; body incomplete")


def _acquire_checksum_sidecar(
    *,
    acquisition_descriptor: T._CAcquisitionDescriptor,
    effective_options: T._CEffectiveOptions,
) -> T._CChecksumBytes:
    raise NotImplementedError("B17.sidecar construction-only; body incomplete")
