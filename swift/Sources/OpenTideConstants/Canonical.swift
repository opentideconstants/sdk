import Foundation

internal enum CanonicalUnimplemented: Error, Equatable {
    case behavior(String)
}

// These isolated entries refuse before effects. They are inactive from public routes.
internal enum Canonical {
    // B01 validate_operation_arguments — body INCOMPLETE.
    internal static func validateOperationArguments(operation: CanonicalOperation, arguments: CanonicalArguments, memberContract: CanonicalMemberContract) throws -> CanonicalValidatedArguments {
        throw CanonicalUnimplemented.behavior("B01")
    }

    // B02 resolve_effective_options — body INCOMPLETE.
    internal static func resolveEffectiveOptions(explicitOptions: CanonicalExplicitOptions, environment: CanonicalEnvironment, platformDefaults: CanonicalPlatformDefaults) throws -> CanonicalEffectiveOptions {
        throw CanonicalUnimplemented.behavior("B02")
    }

    // B03 select_canonical_error — body INCOMPLETE.
    internal static func selectCanonicalError(operation: CanonicalOperation, orderedFailures: CanonicalOrderedFailures, cause: CanonicalCause) throws -> CanonicalCanonicalError {
        throw CanonicalUnimplemented.behavior("B03")
    }

    // B04 translate_native_binding — body INCOMPLETE.
    internal static func translateNativeBinding(canonicalResult: CanonicalCanonicalResult?, canonicalError: CanonicalCanonicalError?, nativeProfile: CanonicalNativeProfile) throws -> CanonicalNativeResult {
        throw CanonicalUnimplemented.behavior("B04")
    }

    // B05 decode_release_document — body INCOMPLETE.
    internal static func decodeReleaseDocument(sourceBytes: CanonicalSourceBytes, readerVersion: CanonicalReaderVersion, documentKind: CanonicalDocumentKind) throws -> CanonicalParsedDocument {
        throw CanonicalUnimplemented.behavior("B05")
    }

    // B06 validate_release_links — body INCOMPLETE.
    internal static func validateReleaseLinks(parsedDocument: CanonicalParsedDocument, requiredLinks: CanonicalRequiredLinks) throws -> CanonicalValidatedReleaseGraph {
        throw CanonicalUnimplemented.behavior("B06")
    }

    // B07 materialize_typed_model — body INCOMPLETE.
    internal static func materializeTypedModel(rawFields: CanonicalRawFields, fieldContract: CanonicalFieldContract, origin: CanonicalOrigin, modelType: CanonicalModelType) throws -> CanonicalTypedModel {
        throw CanonicalUnimplemented.behavior("B07")
    }

    // B08 access_raw_record — body INCOMPLETE.
    internal static func accessRawRecord(accessKind: CanonicalAccessKind, sourceRecord: CanonicalSourceRecord, station: CanonicalStation, releaseOrigin: CanonicalReleaseOrigin, nativeProfile: CanonicalNativeProfile) throws -> CanonicalRawRecordOrValidStation {
        throw CanonicalUnimplemented.behavior("B08")
    }

    // B09 open_client_release — body INCOMPLETE.
    internal static func openClientRelease(arguments: CanonicalArguments, environment: CanonicalEnvironment, platformDefaults: CanonicalPlatformDefaults, cacheState: CanonicalCacheState, clock: CanonicalClock, nativeProfile: CanonicalNativeProfile, readerVersion: CanonicalReaderVersion) async throws -> CanonicalClientAndRelease {
        throw CanonicalUnimplemented.behavior("B09")
    }

    // B10 resolve_release_request — body INCOMPLETE.
    internal static func resolveReleaseRequest(releaseRequest: CanonicalReleaseRequest, effectiveOptions: CanonicalEffectiveOptions, cacheState: CanonicalCacheState, clock: CanonicalClock, readerVersion: CanonicalReaderVersion) async throws -> CanonicalLoadedRelease {
        throw CanonicalUnimplemented.behavior("B10")
    }

    // B11 exchange_release_metadata — body INCOMPLETE.
    internal static func exchangeReleaseMetadata(metadataRequest: CanonicalMetadataRequest, trustedCache: CanonicalTrustedCache, transportOptions: CanonicalTransportOptions, cacheState: CanonicalCacheState, clock: CanonicalClock, readerVersion: CanonicalReaderVersion) async throws -> CanonicalValidatedMetadata {
        throw CanonicalUnimplemented.behavior("B11")
    }

    // B12 update_client_release — body INCOMPLETE.
    internal static func updateClientRelease(clientState: CanonicalClientState, updateRequest: CanonicalUpdateRequest, clock: CanonicalClock, readerVersion: CanonicalReaderVersion) async throws -> CanonicalUpdatedClientState {
        throw CanonicalUnimplemented.behavior("B12")
    }

    // B13 refresh_client_if_due — body INCOMPLETE.
    internal static func refreshClientIfDue(clientState: CanonicalClientState, queryKind: CanonicalQueryKind, clock: CanonicalClock, readerVersion: CanonicalReaderVersion) async throws -> CanonicalQueryClientState {
        throw CanonicalUnimplemented.behavior("B13")
    }

    // B14 forward_held_release — body INCOMPLETE.
    internal static func forwardHeldRelease(heldRelease: CanonicalHeldRelease, queryArguments: CanonicalQueryArguments) throws -> CanonicalHeldReleaseResult {
        throw CanonicalUnimplemented.behavior("B14")
    }

    // B15 enforce_resource_lifetime — body INCOMPLETE.
    internal static func enforceResourceLifetime(resourceState: CanonicalResourceState, lifetimeAction: CanonicalLifetimeAction) throws -> CanonicalResourceStateOrError {
        throw CanonicalUnimplemented.behavior("B15")
    }

    // B16 bind_checksum_manifest — body INCOMPLETE.
    internal static func bindChecksumManifest(checksumBytes: CanonicalChecksumBytes, pointerDigests: CanonicalPointerDigests, requiredFiles: CanonicalRequiredFiles) throws -> CanonicalBoundChecksums {
        throw CanonicalUnimplemented.behavior("B16")
    }

    // B17 acquire_release_files — body INCOMPLETE.
    internal static func acquireReleaseFiles(acquisitionDescriptor: CanonicalAcquisitionDescriptor, effectiveOptions: CanonicalEffectiveOptions, loadMode: CanonicalLoadMode, cacheState: CanonicalCacheState, clock: CanonicalClock, readerVersion: CanonicalReaderVersion) async throws -> CanonicalLoadedRelease {
        throw CanonicalUnimplemented.behavior("B17")
    }

    // B18 merge_cache_receipt — body INCOMPLETE.
    internal static func mergeCacheReceipt(lockedCacheState: CanonicalLockedCacheState, verifiedFileRows: CanonicalVerifiedFileRows, releaseMetadata: CanonicalReleaseMetadata) throws -> CanonicalMergedReceipt {
        throw CanonicalUnimplemented.behavior("B18")
    }

    // B19 select_cached_release — body INCOMPLETE.
    internal static func selectCachedRelease(releaseCandidates: CanonicalReleaseCandidates, effectiveOptions: CanonicalEffectiveOptions, cacheState: CanonicalCacheState, clock: CanonicalClock) throws -> CanonicalUsableCachedReleaseOrError {
        throw CanonicalUnimplemented.behavior("B19")
    }

    // B20 verify_release_files — body INCOMPLETE.
    internal static func verifyReleaseFiles(releaseFiles: CanonicalReleaseFiles, trustedCachedPointer: CanonicalTrustedCachedPointer) throws -> CanonicalVerificationResult {
        throw CanonicalUnimplemented.behavior("B20")
    }

    // B21 publish_download — body INCOMPLETE.
    internal static func publishDownload(destination: CanonicalDestination, formatSelection: CanonicalFormatSelection, overwritePolicy: CanonicalOverwritePolicy, releaseFiles: CanonicalReleaseFiles, checksumBytes: CanonicalChecksumBytes, pointerDigests: CanonicalPointerDigests) throws -> CanonicalDownloadResult {
        throw CanonicalUnimplemented.behavior("B21")
    }

    // B22 manage_cache_inventory — body INCOMPLETE.
    internal static func manageCacheInventory(inventoryAction: CanonicalInventoryAction, cacheState: CanonicalCacheState, keep: CanonicalKeep, currentCacheDirectory: CanonicalCurrentCacheDirectory, clock: CanonicalClock) async throws -> CanonicalCacheInventoryResult {
        throw CanonicalUnimplemented.behavior("B22")
    }

    // B23 perform_guarded_io — body INCOMPLETE.
    internal static func performGuardedIo(ioKind: CanonicalIoKind, ioRequest: CanonicalIoRequest, ioOptions: CanonicalIoOptions, clock: CanonicalClock) async throws -> CanonicalIoResult {
        throw CanonicalUnimplemented.behavior("B23")
    }

    // B24 project_station_index — body INCOMPLETE.
    internal static func projectStationIndex(stationSourceRow: CanonicalStationSourceRow, sourceByteSpan: CanonicalSourceByteSpan, projectionContract: CanonicalProjectionContract) throws -> CanonicalStationIndexEntry {
        throw CanonicalUnimplemented.behavior("B24")
    }

    // B25 authenticate_station_index — body INCOMPLETE.
    internal static func authenticateStationIndex(sourceFiles: CanonicalSourceFiles, suppliedIndex: CanonicalSuppliedIndex, indexPresence: CanonicalIndexPresence, readerVersion: CanonicalReaderVersion) throws -> CanonicalAuthenticatedIndex {
        throw CanonicalUnimplemented.behavior("B25")
    }

    // B26 compare_station_source — body INCOMPLETE.
    internal static func compareStationSource(indexEntry: CanonicalIndexEntry, stationSourceRow: CanonicalStationSourceRow, indexPresence: CanonicalIndexPresence) throws -> CanonicalComparedStationRow {
        throw CanonicalUnimplemented.behavior("B26")
    }

    // B27 read_station_lazily — body INCOMPLETE.
    internal static func readStationLazily(streamReader: CanonicalStreamReader, stationId: CanonicalStationId, releaseOrigin: CanonicalReleaseOrigin, readerVersion: CanonicalReaderVersion) throws -> CanonicalStationSourceRow {
        throw CanonicalUnimplemented.behavior("B27")
    }

    // B28 encode_cache_json — body INCOMPLETE.
    internal static func encodeCacheJson(cacheDocument: CanonicalCacheDocument) throws -> CanonicalCacheBytes {
        throw CanonicalUnimplemented.behavior("B28")
    }

    // B29 lookup_station_identity — body INCOMPLETE.
    internal static func lookupStationIdentity(releaseView: CanonicalReleaseView, identityQuery: CanonicalIdentityQuery, readerVersion: CanonicalReaderVersion) throws -> CanonicalStationOrTombstoneOrNull {
        throw CanonicalUnimplemented.behavior("B29")
    }

    // B30 select_effective_recommendation — body INCOMPLETE.
    internal static func selectEffectiveRecommendation(stationSets: CanonicalStationSets, originalRecommendation: CanonicalOriginalRecommendation, commercialOnly: CanonicalCommercialOnly) throws -> CanonicalEffectiveRecommendation {
        throw CanonicalUnimplemented.behavior("B30")
    }

    // B31 admit_quality_path — body INCOMPLETE.
    internal static func admitQualityPath(candidatePath: CanonicalCandidatePath, includeFlagged: CanonicalIncludeFlagged, includeFallback: CanonicalIncludeFallback) throws -> CanonicalQualityAdmission {
        throw CanonicalUnimplemented.behavior("B31")
    }

    // B32 admit_commercial_path — body INCOMPLETE.
    internal static func admitCommercialPath(candidatePath: CanonicalCandidatePath, commercialOnly: CanonicalCommercialOnly, commercialBasis: CanonicalCommercialBasis) throws -> CanonicalCommercialAdmission {
        throw CanonicalUnimplemented.behavior("B32")
    }

    // B33 resolve_reference_path — body INCOMPLETE.
    internal static func resolveReferencePath(stationSourceRow: CanonicalStationSourceRow, pathRequest: CanonicalPathRequest, releaseView: CanonicalReleaseView) throws -> CanonicalSelectedReferencePath {
        throw CanonicalUnimplemented.behavior("B33")
    }

    // B34 execute_discovery_query — body INCOMPLETE.
    internal static func executeDiscoveryQuery(releaseView: CanonicalReleaseView, queryKind: CanonicalQueryKind, queryOptions: CanonicalQueryOptions, readerVersion: CanonicalReaderVersion) throws -> CanonicalOrderedStationResults {
        throw CanonicalUnimplemented.behavior("B34")
    }

    // B35 summarize_station_sets — body INCOMPLETE.
    internal static func summarizeStationSets(summaryKind: CanonicalSummaryKind, releaseView: CanonicalReleaseView, stationSets: CanonicalStationSets, summaryOptions: CanonicalSummaryOptions) throws -> CanonicalStationSummary {
        throw CanonicalUnimplemented.behavior("B35")
    }

    // B36 admit_historical_offset — body INCOMPLETE.
    internal static func admitHistoricalOffset(ownOffset: CanonicalOwnOffset, referencePath: CanonicalReferencePath, historicalPolicy: CanonicalHistoricalPolicy, selectionKind: CanonicalSelectionKind, readerVersion: CanonicalReaderVersion) throws -> CanonicalHistoricalAdmission {
        throw CanonicalUnimplemented.behavior("B36")
    }

    // B37 format_attribution — body INCOMPLETE.
    internal static func formatAttribution(station: CanonicalStation, releaseView: CanonicalReleaseView, commercialOnly: CanonicalCommercialOnly) throws -> CanonicalAttributionText {
        throw CanonicalUnimplemented.behavior("B37")
    }

    // B38 format_citation — body INCOMPLETE.
    internal static func formatCitation(publishedMetadata: CanonicalPublishedMetadata, citationStyle: CanonicalCitationStyle) throws -> CanonicalCitationText {
        throw CanonicalUnimplemented.behavior("B38")
    }

    // B39 parse_prediction_window — body INCOMPLETE.
    internal static func parsePredictionWindow(timeInputs: CanonicalTimeInputs, windowInputs: CanonicalWindowInputs, step: CanonicalStep, localTimeProfile: CanonicalLocalTimeProfile) throws -> CanonicalPredictionWindow {
        throw CanonicalUnimplemented.behavior("B39")
    }

    // B40 select_prediction_model — body INCOMPLETE.
    internal static func selectPredictionModel(stationRequest: CanonicalStationRequest, releaseView: CanonicalReleaseView, selectionOptions: CanonicalSelectionOptions, readerVersion: CanonicalReaderVersion) throws -> CanonicalSelectedPredictionModel {
        throw CanonicalUnimplemented.behavior("B40")
    }

    // B41 evaluate_astronomy — body INCOMPLETE.
    internal static func evaluateAstronomy(selectedPredictionModel: CanonicalSelectedPredictionModel, utcInstant: CanonicalUtcInstant) throws -> CanonicalAstronomicalTerms {
        throw CanonicalUnimplemented.behavior("B41")
    }

    // B42 evaluate_harmonic_height — body INCOMPLETE.
    internal static func evaluateHarmonicHeight(selectedPredictionModel: CanonicalSelectedPredictionModel, predictionInstants: CanonicalPredictionInstants, requestedDatum: CanonicalRequestedDatum) throws -> CanonicalHeightValues {
        throw CanonicalUnimplemented.behavior("B42")
    }

    // B43 find_tide_events — body INCOMPLETE.
    internal static func findTideEvents(selectedPredictionModel: CanonicalSelectedPredictionModel, predictionWindow: CanonicalPredictionWindow) throws -> CanonicalTideEvents {
        throw CanonicalUnimplemented.behavior("B43")
    }

    // B44 evaluate_direct_current — body INCOMPLETE.
    internal static func evaluateDirectCurrent(selectedPredictionModel: CanonicalSelectedPredictionModel, predictionWindow: CanonicalPredictionWindow, currentRequest: CanonicalCurrentRequest, currentOperation: CanonicalCurrentOperation) throws -> CanonicalDirectCurrentResult {
        throw CanonicalUnimplemented.behavior("B44")
    }

    // B45 evaluate_tide_offset — body INCOMPLETE.
    internal static func evaluateTideOffset(ownOffset: CanonicalOwnOffset, referencePath: CanonicalReferencePath, predictionWindow: CanonicalPredictionWindow, tideRequest: CanonicalTideRequest, readerVersion: CanonicalReaderVersion) throws -> CanonicalOffsetTideResult {
        throw CanonicalUnimplemented.behavior("B45")
    }

    // B46 fold_equal_tide_offset — body INCOMPLETE.
    internal static func foldEqualTideOffset(ownOffset: CanonicalOwnOffset, referenceModel: CanonicalReferenceModel, predictionInstants: CanonicalPredictionInstants, requestedDatum: CanonicalRequestedDatum) throws -> CanonicalFoldedHeightValues {
        throw CanonicalUnimplemented.behavior("B46")
    }

    // B47 evaluate_current_offset — body INCOMPLETE.
    internal static func evaluateCurrentOffset(ownCurrentOffsets: CanonicalOwnCurrentOffsets, referencePath: CanonicalReferencePath, predictionWindow: CanonicalPredictionWindow, currentRequest: CanonicalCurrentRequest, readerVersion: CanonicalReaderVersion) throws -> CanonicalOffsetCurrentResult {
        throw CanonicalUnimplemented.behavior("B47")
    }

    // B48 dispatch_auxiliary_result — body INCOMPLETE.
    internal static func dispatchAuxiliaryResult(auxiliaryKind: CanonicalAuxiliaryKind, auxiliaryOperation: CanonicalAuxiliaryOperation, sourceValues: CanonicalSourceValues, resultContext: CanonicalResultContext, localTimeProfile: CanonicalLocalTimeProfile, resultValues: CanonicalResultValues, utcResult: CanonicalUtcResult, selectionOptions: CanonicalSelectionOptions, readerVersion: CanonicalReaderVersion, auxiliaryMemberId: CanonicalAuxiliaryMemberId) throws -> CanonicalAuxiliaryResult {
        throw CanonicalUnimplemented.behavior("B48")
    }

    // B08.raw retain_raw_source_record — body INCOMPLETE.
    internal static func retainRawSourceRecord(sourceRecord: CanonicalSourceRecord, nativeProfile: CanonicalNativeProfile) throws -> CanonicalRawRecord {
        throw CanonicalUnimplemented.behavior("B08.raw")
    }

    // B08.origin check_station_origin — body INCOMPLETE.
    internal static func checkStationOrigin(station: CanonicalStation, releaseOrigin: CanonicalReleaseOrigin) throws -> CanonicalValidStation {
        throw CanonicalUnimplemented.behavior("B08.origin")
    }

    // B23.lock manage_cache_lock — body INCOMPLETE.
    internal static func manageCacheLock(lockRequest: CanonicalLockRequest, lockState: CanonicalLockState, clock: CanonicalClock) async throws -> CanonicalLockOutcome {
        throw CanonicalUnimplemented.behavior("B23.lock")
    }

    // B23.http request_http_resource — body INCOMPLETE.
    internal static func requestHttpResource(httpRequest: CanonicalHttpRequest, transportOptions: CanonicalTransportOptions) async throws -> CanonicalHttpResponse {
        throw CanonicalUnimplemented.behavior("B23.http")
    }

    // B35.stats count_release_statistics — body INCOMPLETE.
    internal static func countReleaseStatistics(releaseView: CanonicalReleaseView) throws -> CanonicalReleaseStatistics {
        throw CanonicalUnimplemented.behavior("B35.stats")
    }

    // B35.sets order_constant_sets — body INCOMPLETE.
    internal static func orderConstantSets(stationSets: CanonicalStationSets, originalRecommendation: CanonicalOriginalRecommendation, commercialOnly: CanonicalCommercialOnly, includeNoConstants: CanonicalIncludeNoConstants) throws -> CanonicalOrderedConstantSets {
        throw CanonicalUnimplemented.behavior("B35.sets")
    }

    // B48.aux read_auxiliary_model_value — body INCOMPLETE.
    internal static func readAuxiliaryModelValue(auxiliaryOperation: CanonicalAuxiliaryOperation, sourceValues: CanonicalSourceValues, selectionOptions: CanonicalSelectionOptions, readerVersion: CanonicalReaderVersion, auxiliaryMemberId: CanonicalAuxiliaryMemberId) throws -> CanonicalAuxiliaryModelValue {
        throw CanonicalUnimplemented.behavior("B48.aux")
    }

    // B48.context construct_prediction_result — body INCOMPLETE.
    internal static func constructPredictionResult(resultValues: CanonicalResultValues, resultContext: CanonicalResultContext) throws -> CanonicalPredictionResult {
        throw CanonicalUnimplemented.behavior("B48.context")
    }

    // B48.local convert_result_to_local_time — body INCOMPLETE.
    internal static func convertResultToLocalTime(utcResult: CanonicalUtcResult, localTimeProfile: CanonicalLocalTimeProfile) throws -> CanonicalLocalTimeResult {
        throw CanonicalUnimplemented.behavior("B48.local")
    }

    // B43.roots find_unrounded_tide_events — body INCOMPLETE.
    internal static func findUnroundedTideEvents(selectedPredictionModel: CanonicalSelectedPredictionModel, predictionWindow: CanonicalPredictionWindow) throws -> CanonicalUnroundedTideEvents {
        throw CanonicalUnimplemented.behavior("B43.roots")
    }

    // B44.roots find_unrounded_current_events — body INCOMPLETE.
    internal static func findUnroundedCurrentEvents(selectedPredictionModel: CanonicalSelectedPredictionModel, predictionWindow: CanonicalPredictionWindow, currentRequest: CanonicalCurrentRequest) throws -> CanonicalUnroundedCurrentEvents {
        throw CanonicalUnimplemented.behavior("B44.roots")
    }

    // B17.sidecar acquire_checksum_sidecar — body INCOMPLETE.
    internal static func acquireChecksumSidecar(acquisitionDescriptor: CanonicalAcquisitionDescriptor, effectiveOptions: CanonicalEffectiveOptions) async throws -> CanonicalChecksumBytes {
        throw CanonicalUnimplemented.behavior("B17.sidecar")
    }
}
