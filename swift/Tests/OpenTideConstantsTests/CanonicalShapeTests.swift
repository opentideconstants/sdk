import Foundation
import XCTest
@testable import OpenTideConstants

final class CanonicalShapeTests: XCTestCase {
    private var observationFile: FileHandle?
    func testRequiredPrivateDecodeSeam() throws {
        let bytes = Data("{}".utf8)
        let version = CanonicalReaderVersion(major: 1, minor: 0)
        do {
            let _: CanonicalParsedDocument = try Canonical.decodeReleaseDocument(
                sourceBytes: bytes, readerVersion: version, documentKind: .release)
            XCTFail("Construction skeleton must honestly refuse before acquisition or parsing")
        } catch CanonicalUnimplemented.behavior(let id) {
            XCTAssertEqual(id, "B05")
        }
    }
// Calls are independent construction observations. Guards select fixtures;
// refusal is not an execution of the owning catalog workflow/algorithm.
func testAllRuntimeAndOrderedCallActionEntries() async throws {
    if let path = ProcessInfo.processInfo.environment["OTC_SW_SHAPE_OBSERVATIONS"] {
        XCTAssertTrue(FileManager.default.createFile(atPath: path, contents: nil))
        observationFile = try FileHandle(forWritingTo: URL(fileURLWithPath: path))
    }
    defer { try? observationFile?.close(); observationFile = nil }
    let meta: JSONValue = .object([
        "format_version": .string("1.0"),
        "release": .object(["datestamp": .string("20991231"),
            "created": .string("2099-12-31T00:00:00Z"), "source_versions": .object([:])])
    ])
    let release = try Release(meta: meta, entries: [], documents: [:], jsonl: nil,
        indexPath: nil, files: [], commercialOnly: false, commercialBasis: "strict",
        historicalOffsetsPolicy: "fallback")
    defer { release.close() }
    let convention = Convention(.object([:]))
    let licence = Licence(.object([:]))
    let nativeConstantSet = ConstantSet(raw: .object([:]), convention: convention,
        licence: licence, isRecommended: false, validation: [])
    let nativeStation = Station(raw: .object(["station_id": .string("shape-only")]),
        kind: .tide, recommendedSet: nil, sourceRecords: [], sets: [])
        let operation: CanonicalOperation = .open
        let arguments: CanonicalArguments = .ClientOpen(CanonicalClientOpenArguments(release: nil, file: nil, cacheDir: nil, offline: nil, mode: .eager, baseUrl: nil, timeout: nil, proxy: nil, caFile: nil, userAgent: nil, onNetworkError: nil, autoUpdate: false, updateInterval: 1.0, logger: nil, verifyOnOpen: false, commercialOnly: false, commercialBasis: "shape-only", historicalOffsetsPolicy: "shape-only"))
        let memberContract: CanonicalMemberContract = .ClientOpen
        let explicitOptions: CanonicalExplicitOptions = CanonicalEffectiveOptions(release: nil, file: nil, cacheDir: nil, offline: nil, mode: .eager, baseUrl: nil, timeout: nil, proxy: nil, caFile: nil, userAgent: nil, onNetworkError: nil, autoUpdate: false, updateInterval: 1.0, logger: nil, verifyOnOpen: false, commercialOnly: false, commercialBasis: "shape-only", historicalOffsetsPolicy: "shape-only")
        let environment: CanonicalEnvironment = [:]
        let platformDefaults: CanonicalPlatformDefaults = CanonicalEffectiveOptions(release: nil, file: nil, cacheDir: nil, offline: nil, mode: .eager, baseUrl: nil, timeout: nil, proxy: nil, caFile: nil, userAgent: nil, onNetworkError: nil, autoUpdate: false, updateInterval: 1.0, logger: nil, verifyOnOpen: false, commercialOnly: false, commercialBasis: "shape-only", historicalOffsetsPolicy: "shape-only")
        let orderedFailures: CanonicalOrderedFailures = []
        let cause: CanonicalCause = nil
        let canonicalResult: CanonicalCanonicalResult = .ReleaseStation(nil)
        let canonicalError: CanonicalCanonicalError = CanonicalCanonicalError(code: .invalidArgument, structuredFields: .object([:]), cause: nil)
        XCTAssertEqual(canonicalError.code, .invalidArgument)
        let nativeProfile: CanonicalNativeProfile = .swift
        let sourceBytes: CanonicalSourceBytes = Data("{}".utf8)
        let readerVersion: CanonicalReaderVersion = CanonicalReaderVersion(major: 1, minor: 1)
        let documentKind: CanonicalDocumentKind = .release
        let parsedDocument: CanonicalParsedDocument = .stationRow(.object([:]))
        let requiredLinks: CanonicalRequiredLinks = CanonicalLinkTable(stationIds: [], constantSetIds: [], conventionIds: [], licenceIds: [], astroTableIds: [], sourceRecordIds: [])
        let rawFields: CanonicalRawFields = .object([:])
        let fieldContract: CanonicalFieldContract = CanonicalFieldContract(modelType: .Client, members: [])
        let origin: CanonicalOrigin = UUID(uuidString: "00000000-0000-0000-0000-000000000001")!
        let modelType: CanonicalModelType = .Client
        let accessKind: CanonicalAccessKind = .rawRecord
        let sourceRecord: CanonicalSourceRecord = .object([:])
        let station: CanonicalStation = nativeStation
        let releaseOrigin: CanonicalReleaseOrigin = UUID(uuidString: "00000000-0000-0000-0000-000000000001")!
        let cacheState: CanonicalCacheState = CanonicalCacheState(cacheRoot: URL(fileURLWithPath: "/shape-only/inert"), releaseCandidates: [], pointerCache: nil, lockState: CanonicalLockState(cacheRoot: URL(fileURLWithPath: "/shape-only/inert"), owner: nil, heldToken: nil))
        let clock: CanonicalClock = 1.0
        let releaseRequest: CanonicalReleaseRequest = .latest(.latest)
        let effectiveOptions: CanonicalEffectiveOptions = CanonicalEffectiveOptions(release: nil, file: nil, cacheDir: nil, offline: nil, mode: .eager, baseUrl: nil, timeout: nil, proxy: nil, caFile: nil, userAgent: nil, onNetworkError: nil, autoUpdate: false, updateInterval: 1.0, logger: nil, verifyOnOpen: false, commercialOnly: false, commercialBasis: "shape-only", historicalOffsetsPolicy: "shape-only")
        let metadataRequest: CanonicalMetadataRequest = CanonicalMetadataRequest(requestUrl: "shape-only", documentKind: "shape-only")
        let trustedCache: CanonicalTrustedCache = nil
        let transportOptions: CanonicalTransportOptions = CanonicalTransportOptions(offline: nil, baseUrl: nil, timeout: nil, proxy: nil, caFile: nil, userAgent: nil)
        let clientState: CanonicalClientState = CanonicalClientState(currentRelease: release, effectiveOptions: CanonicalEffectiveOptions(release: nil, file: nil, cacheDir: nil, offline: nil, mode: .eager, baseUrl: nil, timeout: nil, proxy: nil, caFile: nil, userAgent: nil, onNetworkError: nil, autoUpdate: false, updateInterval: 1.0, logger: nil, verifyOnOpen: false, commercialOnly: false, commercialBasis: "shape-only", historicalOffsetsPolicy: "shape-only"), cacheState: CanonicalCacheState(cacheRoot: URL(fileURLWithPath: "/shape-only/inert"), releaseCandidates: [], pointerCache: nil, lockState: CanonicalLockState(cacheRoot: URL(fileURLWithPath: "/shape-only/inert"), owner: nil, heldToken: nil)), lastError: nil, lastUpdateCheck: nil, closed: false)
        let updateRequest: CanonicalUpdateRequest = CanonicalMetadataRequest(requestUrl: "shape-only", documentKind: "shape-only")
        let queryKind: CanonicalQueryKind = .stations
        let heldRelease: CanonicalHeldRelease = release
        let queryArguments: CanonicalQueryArguments = .ReleaseStations(CanonicalReleaseStationsArguments(country: nil, type: nil, kind: nil, source: nil, sourceType: nil, includeFlagged: false, includeFallback: false))
        let resourceState: CanonicalResourceState = .clientState(CanonicalClientState(currentRelease: release, effectiveOptions: CanonicalEffectiveOptions(release: nil, file: nil, cacheDir: nil, offline: nil, mode: .eager, baseUrl: nil, timeout: nil, proxy: nil, caFile: nil, userAgent: nil, onNetworkError: nil, autoUpdate: false, updateInterval: 1.0, logger: nil, verifyOnOpen: false, commercialOnly: false, commercialBasis: "shape-only", historicalOffsetsPolicy: "shape-only"), cacheState: CanonicalCacheState(cacheRoot: URL(fileURLWithPath: "/shape-only/inert"), releaseCandidates: [], pointerCache: nil, lockState: CanonicalLockState(cacheRoot: URL(fileURLWithPath: "/shape-only/inert"), owner: nil, heldToken: nil)), lastError: nil, lastUpdateCheck: nil, closed: false))
        let lifetimeAction: CanonicalLifetimeAction = "shape-only"
        let checksumBytes: CanonicalChecksumBytes = Data("{}".utf8)
        let pointerDigests: CanonicalPointerDigests = [:]
        let requiredFiles: CanonicalRequiredFiles = []
        let acquisitionDescriptor: CanonicalAcquisitionDescriptor = CanonicalReleaseDescriptor(datestamp: "shape-only", files: [], checksumBytes: nil, pointerDigests: [:], requiredFileRequest: nil, metadata: .object([:]))
        let loadMode: CanonicalLoadMode = .eager
        let lockedCacheState: CanonicalLockedCacheState = CanonicalCacheState(cacheRoot: URL(fileURLWithPath: "/shape-only/inert"), releaseCandidates: [], pointerCache: nil, lockState: CanonicalLockState(cacheRoot: URL(fileURLWithPath: "/shape-only/inert"), owner: nil, heldToken: nil))
        let verifiedFileRows: CanonicalVerifiedFileRows = []
        let releaseMetadata: CanonicalReleaseMetadata = .object([:])
        let releaseCandidates: CanonicalReleaseCandidates = []
        let releaseFiles: CanonicalReleaseFiles = []
        let trustedCachedPointer: CanonicalTrustedCachedPointer = nil
        let destination: CanonicalDestination = URL(fileURLWithPath: "/shape-only/inert")
        let formatSelection: CanonicalFormatSelection = CanonicalFormatSelection(formats: [], requiredFiles: [])
        let overwritePolicy: CanonicalOverwritePolicy = CanonicalClientDownloadArguments(release: "shape-only", to: "shape-only", formats: [], overwrite: false)
        let inventoryAction: CanonicalInventoryAction = .list
        let keep: CanonicalKeep = 1
        let currentCacheDirectory: CanonicalCurrentCacheDirectory = URL(fileURLWithPath: "/shape-only/inert")
        let ioKind: CanonicalIoKind = .lock
        let ioRequest: CanonicalIoRequest = .lock(CanonicalLockRequest(directory: URL(fileURLWithPath: "/shape-only/inert"), operation: .take, token: nil))
        let ioOptions: CanonicalIoOptions = .lock(CanonicalLockState(cacheRoot: URL(fileURLWithPath: "/shape-only/inert"), owner: nil, heldToken: nil))
        let stationSourceRow: CanonicalStationSourceRow = .object([:])
        let sourceByteSpan: CanonicalSourceByteSpan = CanonicalSourceByteSpan(offsetBytes: 1, lengthBytes: 1)
        let projectionContract: CanonicalProjectionContract = CanonicalProjectionRules(scalarMembers: [], modelType: .Client, preserveUnknownSourceFields: false)
        let sourceFiles: CanonicalSourceFiles = CanonicalSourceFiles(jsonl: URL(fileURLWithPath: "/shape-only/inert"), meta: URL(fileURLWithPath: "/shape-only/inert"), jsonlSha256: "shape-only", jsonlSize: 1, metaSha256: "shape-only", metaSize: 1)
        let suppliedIndex: CanonicalSuppliedIndex = nil
        let indexPresence: CanonicalIndexPresence = [:]
        let indexEntry: CanonicalIndexEntry = CanonicalStreamIndexStation(stationId: "shape-only", status: "shape-only", name: nil, nameFolded: nil, country: nil, type: nil, kind: nil, referenceStationId: nil, offsetsLicenceId: nil, recommendedSetId: nil, lat: nil, lon: nil, offset: 1, length: 1, aliases: [:], sets: [], subordinateOffsets: nil, currentOffsets: [])
        let streamReader: CanonicalStreamReader = CanonicalStreamReader(releaseView: release, fileDescriptor: 1, index: .object([:]), indexPresence: .object([:]), stationLru: .object([:]), closed: false)
        let stationId: CanonicalStationId = "shape-only"
        let cacheDocument: CanonicalCacheDocument = .streamIndex(CanonicalStreamIndex(indexVersion: 1, discoveryIndexVersion: 1, datestamp: "shape-only", jsonl: "shape-only", jsonlSha256: "shape-only", jsonlSize: 1, by: "shape-only", stations: []))
        let releaseView: CanonicalReleaseView = release
        let identityQuery: CanonicalIdentityQuery = .String("shape-only")
        let stationSets: CanonicalStationSets = []
        let originalRecommendation: CanonicalOriginalRecommendation = nil
        let commercialOnly: CanonicalCommercialOnly = false
        let candidatePath: CanonicalCandidatePath = .direct(CanonicalCandidatePathDirect(station: nativeStation, constantSet: nativeConstantSet, releaseView: release))
        let includeFlagged: CanonicalIncludeFlagged = false
        let includeFallback: CanonicalIncludeFallback = false
        let commercialBasis: CanonicalCommercialBasis = .strict
        let pathRequest: CanonicalPathRequest = "shape-only"
        let queryOptions: CanonicalQueryOptions = .ReleaseStations(CanonicalReleaseStationsArguments(country: nil, type: nil, kind: nil, source: nil, sourceType: nil, includeFlagged: false, includeFallback: false))
        let summaryKind: CanonicalSummaryKind = .stats
        let summaryOptions: CanonicalSummaryOptions = CanonicalSummaryOptions(originalRecommendation: nil, commercialOnly: false, includeNoConstants: false)
        let ownOffset: CanonicalOwnOffset = nil
        let referencePath: CanonicalReferencePath = CanonicalReferencePath(station: nativeStation, releaseView: release, constantSet: nil, ownOffset: nil, referenceBin: nil)
        let historicalPolicy: CanonicalHistoricalPolicy = .fallback
        let selectionKind: CanonicalSelectionKind = .discovery
        let publishedMetadata: CanonicalPublishedMetadata = CanonicalPublishedMetadata(contributors: .object([:]), year: 1, conceptDoi: nil, zenodoVersionDoi: nil, datasetUrl: "shape-only")
        let citationStyle: CanonicalCitationStyle = "shape-only"
        let timeInputs: CanonicalTimeInputs = .ClientOpen(CanonicalClientOpenArguments(release: nil, file: nil, cacheDir: nil, offline: nil, mode: .eager, baseUrl: nil, timeout: nil, proxy: nil, caFile: nil, userAgent: nil, onNetworkError: nil, autoUpdate: false, updateInterval: 1.0, logger: nil, verifyOnOpen: false, commercialOnly: false, commercialBasis: "shape-only", historicalOffsetsPolicy: "shape-only"))
        let windowInputs: CanonicalWindowInputs = .ClientOpen(CanonicalClientOpenArguments(release: nil, file: nil, cacheDir: nil, offline: nil, mode: .eager, baseUrl: nil, timeout: nil, proxy: nil, caFile: nil, userAgent: nil, onNetworkError: nil, autoUpdate: false, updateInterval: 1.0, logger: nil, verifyOnOpen: false, commercialOnly: false, commercialBasis: "shape-only", historicalOffsetsPolicy: "shape-only"))
        let step: CanonicalStep = 1.0
        let localTimeProfile: CanonicalLocalTimeProfile = CanonicalHeightSeriesToLocalArguments(tz: "shape-only")
        let stationRequest: CanonicalStationRequest = .object(nativeStation)
        let selectionOptions: CanonicalSelectionOptions = CanonicalSelectionOptions(setId: nil, binNumber: nil, commercialOnly: false, offsetId: nil, datum: nil)
        let selectedPredictionModel: CanonicalSelectedPredictionModel = CanonicalPredictionModel(station: nativeStation, releaseView: release, constantSet: nativeConstantSet, convention: Convention(.object([:])), astroTable: .object([:]), requiredConstituents: [], referenceBin: nil, meanTerm: 1.0, datumSource: nil)
        let utcInstant: CanonicalUtcInstant = 1.0
        let predictionInstants: CanonicalPredictionInstants = []
        let requestedDatum: CanonicalRequestedDatum = "shape-only"
        let predictionWindow: CanonicalPredictionWindow = CanonicalPredictionWindow(start: 1.0, stop: 1.0, step: nil, instants: nil)
        let currentRequest: CanonicalCurrentRequest = .ReleaseCurrents(CanonicalReleaseCurrentsArguments(station: .object(nativeStation), start: Date(timeIntervalSince1970: 0), stop: Date(timeIntervalSince1970: 0), stepS: 1, binNumber: nil, setId: nil))
        let currentOperation: CanonicalCurrentOperation = .currents
        let tideRequest: CanonicalTideRequest = .ReleaseHeights(CanonicalReleaseHeightsArguments(station: .object(nativeStation), start: Date(timeIntervalSince1970: 0), stop: Date(timeIntervalSince1970: 0), stepS: 1, datum: nil, setId: nil, offsetId: nil))
        let referenceModel: CanonicalReferenceModel = CanonicalPredictionModel(station: nativeStation, releaseView: release, constantSet: nativeConstantSet, convention: Convention(.object([:])), astroTable: .object([:]), requiredConstituents: [], referenceBin: nil, meanTerm: 1.0, datumSource: nil)
        let ownCurrentOffsets: CanonicalOwnCurrentOffsets = nil
        let auxiliaryKind: CanonicalAuxiliaryKind = .modelAccess
        let auxiliaryOperation: CanonicalAuxiliaryOperation = .astroTable
        let sourceValues: CanonicalSourceValues = .requiresModel(CanonicalAuxiliaryValuesRequiresModel(stationRequest: .Station(nativeStation), releaseView: release, selectionOptions: CanonicalSelectionOptions(setId: nil, binNumber: nil, commercialOnly: false, offsetId: nil, datum: nil), utcInstant: nil))
        let resultContext: CanonicalResultContext = CanonicalResultContext(stationId: "shape-only", setId: nil, referenceStationId: nil, binNumber: nil, datum: nil, releaseDatestamp: "shape-only", algorithm: "shape-only")
        let resultValues: CanonicalResultValues = .ReleaseStation(nil)
        let utcResult: CanonicalUtcResult = .ReleaseStation(nil)
        let auxiliaryMemberId: CanonicalAuxiliaryMemberId = .ReleaseAstroTable
        let lockRequest: CanonicalLockRequest = CanonicalLockRequest(directory: URL(fileURLWithPath: "/shape-only/inert"), operation: .take, token: nil)
        let lockState: CanonicalLockState = CanonicalLockState(cacheRoot: URL(fileURLWithPath: "/shape-only/inert"), owner: nil, heldToken: nil)
        let httpRequest: CanonicalHttpRequest = CanonicalHttpRequest(url: "shape-only", conditionalEtag: nil)
        let includeNoConstants: CanonicalIncludeNoConstants = false
        // B01
        try await observe("B01", callee: "B01", resultType: "CanonicalValidatedArguments", arguments: .object(["operation": .string(String(reflecting: operation)), "arguments": .string(String(reflecting: arguments)), "member_contract": .string(String(reflecting: memberContract))])) {
            let value: CanonicalValidatedArguments = try Canonical.validateOperationArguments(operation: operation, arguments: arguments, memberContract: memberContract)
            return value
        }
        // B02
        try await observe("B02", callee: "B02", resultType: "CanonicalEffectiveOptions", arguments: .object(["explicit_options": .string(String(reflecting: explicitOptions)), "environment": .string(String(reflecting: environment)), "platform_defaults": .string(String(reflecting: platformDefaults))])) {
            let value: CanonicalEffectiveOptions = try Canonical.resolveEffectiveOptions(explicitOptions: explicitOptions, environment: environment, platformDefaults: platformDefaults)
            return value
        }
        // B03
        try await observe("B03", callee: "B03", resultType: "CanonicalCanonicalError", arguments: .object(["operation": .string(String(reflecting: operation)), "ordered_failures": .string(String(reflecting: orderedFailures)), "cause": .string(String(reflecting: cause))])) {
            let value: CanonicalCanonicalError = try Canonical.selectCanonicalError(operation: operation, orderedFailures: orderedFailures, cause: cause)
            return value
        }
        // B04
        try await observe("B04", callee: "B04", resultType: "CanonicalNativeResult", arguments: .object(["canonical_result": .string(String(reflecting: canonicalResult)), "canonical_error": .string(String(reflecting: Optional<CanonicalCanonicalError>.none)), "native_profile": .string(String(reflecting: nativeProfile))])) {
            let value: CanonicalNativeResult = try Canonical.translateNativeBinding(canonicalResult: canonicalResult, canonicalError: nil, nativeProfile: nativeProfile)
            return value
        }
        // B05
        try await observe("B05", callee: "B05", resultType: "CanonicalParsedDocument", arguments: .object(["source_bytes": .string(String(reflecting: sourceBytes)), "reader_version": .string(String(reflecting: readerVersion)), "document_kind": .string(String(reflecting: documentKind))])) {
            let value: CanonicalParsedDocument = try Canonical.decodeReleaseDocument(sourceBytes: sourceBytes, readerVersion: readerVersion, documentKind: documentKind)
            return value
        }
        // B06
        try await observe("B06", callee: "B06", resultType: "CanonicalValidatedReleaseGraph", arguments: .object(["parsed_document": .string(String(reflecting: parsedDocument)), "required_links": .string(String(reflecting: requiredLinks))])) {
            let value: CanonicalValidatedReleaseGraph = try Canonical.validateReleaseLinks(parsedDocument: parsedDocument, requiredLinks: requiredLinks)
            return value
        }
        // B07
        try await observe("B07", callee: "B07", resultType: "CanonicalTypedModel", arguments: .object(["raw_fields": .string(String(reflecting: rawFields)), "field_contract": .string(String(reflecting: fieldContract)), "origin": .string(String(reflecting: origin)), "model_type": .string(String(reflecting: modelType))])) {
            let value: CanonicalTypedModel = try Canonical.materializeTypedModel(rawFields: rawFields, fieldContract: fieldContract, origin: origin, modelType: modelType)
            return value
        }
        // B08
        try await observe("B08", callee: "B08", resultType: "CanonicalRawRecordOrValidStation", arguments: .object(["access_kind": .string(String(reflecting: accessKind)), "source_record": .string(String(reflecting: sourceRecord)), "station": .string(String(reflecting: station)), "release_origin": .string(String(reflecting: releaseOrigin)), "native_profile": .string(String(reflecting: nativeProfile))])) {
            let value: CanonicalRawRecordOrValidStation = try Canonical.accessRawRecord(accessKind: accessKind, sourceRecord: sourceRecord, station: station, releaseOrigin: releaseOrigin, nativeProfile: nativeProfile)
            return value
        }
        // B09
        try await observe("B09", callee: "B09", resultType: "CanonicalClientAndRelease", arguments: .object(["arguments": .string(String(reflecting: arguments)), "environment": .string(String(reflecting: environment)), "platform_defaults": .string(String(reflecting: platformDefaults)), "cache_state": .string(String(reflecting: cacheState)), "clock": .string(String(reflecting: clock)), "native_profile": .string(String(reflecting: nativeProfile)), "reader_version": .string(String(reflecting: readerVersion))])) {
            let value: CanonicalClientAndRelease = try await Canonical.openClientRelease(arguments: arguments, environment: environment, platformDefaults: platformDefaults, cacheState: cacheState, clock: clock, nativeProfile: nativeProfile, readerVersion: readerVersion)
            return value
        }
        // B10
        try await observe("B10", callee: "B10", resultType: "CanonicalLoadedRelease", arguments: .object(["release_request": .string(String(reflecting: releaseRequest)), "effective_options": .string(String(reflecting: effectiveOptions)), "cache_state": .string(String(reflecting: cacheState)), "clock": .string(String(reflecting: clock)), "reader_version": .string(String(reflecting: readerVersion))])) {
            let value: CanonicalLoadedRelease = try await Canonical.resolveReleaseRequest(releaseRequest: releaseRequest, effectiveOptions: effectiveOptions, cacheState: cacheState, clock: clock, readerVersion: readerVersion)
            return value
        }
        // B11
        try await observe("B11", callee: "B11", resultType: "CanonicalValidatedMetadata", arguments: .object(["metadata_request": .string(String(reflecting: metadataRequest)), "trusted_cache": .string(String(reflecting: trustedCache)), "transport_options": .string(String(reflecting: transportOptions)), "cache_state": .string(String(reflecting: cacheState)), "clock": .string(String(reflecting: clock)), "reader_version": .string(String(reflecting: readerVersion))])) {
            let value: CanonicalValidatedMetadata = try await Canonical.exchangeReleaseMetadata(metadataRequest: metadataRequest, trustedCache: trustedCache, transportOptions: transportOptions, cacheState: cacheState, clock: clock, readerVersion: readerVersion)
            return value
        }
        // B12
        try await observe("B12", callee: "B12", resultType: "CanonicalUpdatedClientState", arguments: .object(["client_state": .string(String(reflecting: clientState)), "update_request": .string(String(reflecting: updateRequest)), "clock": .string(String(reflecting: clock)), "reader_version": .string(String(reflecting: readerVersion))])) {
            let value: CanonicalUpdatedClientState = try await Canonical.updateClientRelease(clientState: clientState, updateRequest: updateRequest, clock: clock, readerVersion: readerVersion)
            return value
        }
        // B13
        try await observe("B13", callee: "B13", resultType: "CanonicalQueryClientState", arguments: .object(["client_state": .string(String(reflecting: clientState)), "query_kind": .string(String(reflecting: queryKind)), "clock": .string(String(reflecting: clock)), "reader_version": .string(String(reflecting: readerVersion))])) {
            let value: CanonicalQueryClientState = try await Canonical.refreshClientIfDue(clientState: clientState, queryKind: queryKind, clock: clock, readerVersion: readerVersion)
            return value
        }
        // B14
        try await observe("B14", callee: "B14", resultType: "CanonicalHeldReleaseResult", arguments: .object(["held_release": .string(String(reflecting: heldRelease)), "query_arguments": .string(String(reflecting: queryArguments))])) {
            let value: CanonicalHeldReleaseResult = try Canonical.forwardHeldRelease(heldRelease: heldRelease, queryArguments: queryArguments)
            return value
        }
        // B15
        try await observe("B15", callee: "B15", resultType: "CanonicalResourceStateOrError", arguments: .object(["resource_state": .string(String(reflecting: resourceState)), "lifetime_action": .string(String(reflecting: lifetimeAction))])) {
            let value: CanonicalResourceStateOrError = try Canonical.enforceResourceLifetime(resourceState: resourceState, lifetimeAction: lifetimeAction)
            return value
        }
        // B16
        try await observe("B16", callee: "B16", resultType: "CanonicalBoundChecksums", arguments: .object(["checksum_bytes": .string(String(reflecting: checksumBytes)), "pointer_digests": .string(String(reflecting: pointerDigests)), "required_files": .string(String(reflecting: requiredFiles))])) {
            let value: CanonicalBoundChecksums = try Canonical.bindChecksumManifest(checksumBytes: checksumBytes, pointerDigests: pointerDigests, requiredFiles: requiredFiles)
            return value
        }
        // B17
        try await observe("B17", callee: "B17", resultType: "CanonicalLoadedRelease", arguments: .object(["acquisition_descriptor": .string(String(reflecting: acquisitionDescriptor)), "effective_options": .string(String(reflecting: effectiveOptions)), "load_mode": .string(String(reflecting: loadMode)), "cache_state": .string(String(reflecting: cacheState)), "clock": .string(String(reflecting: clock)), "reader_version": .string(String(reflecting: readerVersion))])) {
            let value: CanonicalLoadedRelease = try await Canonical.acquireReleaseFiles(acquisitionDescriptor: acquisitionDescriptor, effectiveOptions: effectiveOptions, loadMode: loadMode, cacheState: cacheState, clock: clock, readerVersion: readerVersion)
            return value
        }
        // B18
        try await observe("B18", callee: "B18", resultType: "CanonicalMergedReceipt", arguments: .object(["locked_cache_state": .string(String(reflecting: lockedCacheState)), "verified_file_rows": .string(String(reflecting: verifiedFileRows)), "release_metadata": .string(String(reflecting: releaseMetadata))])) {
            let value: CanonicalMergedReceipt = try Canonical.mergeCacheReceipt(lockedCacheState: lockedCacheState, verifiedFileRows: verifiedFileRows, releaseMetadata: releaseMetadata)
            return value
        }
        // B19
        try await observe("B19", callee: "B19", resultType: "CanonicalUsableCachedReleaseOrError", arguments: .object(["release_candidates": .string(String(reflecting: releaseCandidates)), "effective_options": .string(String(reflecting: effectiveOptions)), "cache_state": .string(String(reflecting: cacheState)), "clock": .string(String(reflecting: clock))])) {
            let value: CanonicalUsableCachedReleaseOrError = try Canonical.selectCachedRelease(releaseCandidates: releaseCandidates, effectiveOptions: effectiveOptions, cacheState: cacheState, clock: clock)
            return value
        }
        // B20
        try await observe("B20", callee: "B20", resultType: "CanonicalVerificationResult", arguments: .object(["release_files": .string(String(reflecting: releaseFiles)), "trusted_cached_pointer": .string(String(reflecting: trustedCachedPointer))])) {
            let value: CanonicalVerificationResult = try Canonical.verifyReleaseFiles(releaseFiles: releaseFiles, trustedCachedPointer: trustedCachedPointer)
            return value
        }
        // B21
        try await observe("B21", callee: "B21", resultType: "CanonicalDownloadResult", arguments: .object(["destination": .string(String(reflecting: destination)), "format_selection": .string(String(reflecting: formatSelection)), "overwrite_policy": .string(String(reflecting: overwritePolicy)), "release_files": .string(String(reflecting: releaseFiles)), "checksum_bytes": .string(String(reflecting: checksumBytes)), "pointer_digests": .string(String(reflecting: pointerDigests))])) {
            let value: CanonicalDownloadResult = try Canonical.publishDownload(destination: destination, formatSelection: formatSelection, overwritePolicy: overwritePolicy, releaseFiles: releaseFiles, checksumBytes: checksumBytes, pointerDigests: pointerDigests)
            return value
        }
        // B22
        try await observe("B22", callee: "B22", resultType: "CanonicalCacheInventoryResult", arguments: .object(["inventory_action": .string(String(reflecting: inventoryAction)), "cache_state": .string(String(reflecting: cacheState)), "keep": .string(String(reflecting: keep)), "current_cache_directory": .string(String(reflecting: currentCacheDirectory)), "clock": .string(String(reflecting: clock))])) {
            let value: CanonicalCacheInventoryResult = try await Canonical.manageCacheInventory(inventoryAction: inventoryAction, cacheState: cacheState, keep: keep, currentCacheDirectory: currentCacheDirectory, clock: clock)
            return value
        }
        // B23
        try await observe("B23", callee: "B23", resultType: "CanonicalIoResult", arguments: .object(["io_kind": .string(String(reflecting: ioKind)), "io_request": .string(String(reflecting: ioRequest)), "io_options": .string(String(reflecting: ioOptions)), "clock": .string(String(reflecting: clock))])) {
            let value: CanonicalIoResult = try await Canonical.performGuardedIo(ioKind: ioKind, ioRequest: ioRequest, ioOptions: ioOptions, clock: clock)
            return value
        }
        // B24
        try await observe("B24", callee: "B24", resultType: "CanonicalStationIndexEntry", arguments: .object(["station_source_row": .string(String(reflecting: stationSourceRow)), "source_byte_span": .string(String(reflecting: sourceByteSpan)), "projection_contract": .string(String(reflecting: projectionContract))])) {
            let value: CanonicalStationIndexEntry = try Canonical.projectStationIndex(stationSourceRow: stationSourceRow, sourceByteSpan: sourceByteSpan, projectionContract: projectionContract)
            return value
        }
        // B25
        try await observe("B25", callee: "B25", resultType: "CanonicalAuthenticatedIndex", arguments: .object(["source_files": .string(String(reflecting: sourceFiles)), "supplied_index": .string(String(reflecting: suppliedIndex)), "index_presence": .string(String(reflecting: indexPresence)), "reader_version": .string(String(reflecting: readerVersion))])) {
            let value: CanonicalAuthenticatedIndex = try Canonical.authenticateStationIndex(sourceFiles: sourceFiles, suppliedIndex: suppliedIndex, indexPresence: indexPresence, readerVersion: readerVersion)
            return value
        }
        // B26
        try await observe("B26", callee: "B26", resultType: "CanonicalComparedStationRow", arguments: .object(["index_entry": .string(String(reflecting: indexEntry)), "station_source_row": .string(String(reflecting: stationSourceRow)), "index_presence": .string(String(reflecting: indexPresence))])) {
            let value: CanonicalComparedStationRow = try Canonical.compareStationSource(indexEntry: indexEntry, stationSourceRow: stationSourceRow, indexPresence: indexPresence)
            return value
        }
        // B27
        try await observe("B27", callee: "B27", resultType: "CanonicalStationSourceRow", arguments: .object(["stream_reader": .string(String(reflecting: streamReader)), "station_id": .string(String(reflecting: stationId)), "release_origin": .string(String(reflecting: releaseOrigin)), "reader_version": .string(String(reflecting: readerVersion))])) {
            let value: CanonicalStationSourceRow = try Canonical.readStationLazily(streamReader: streamReader, stationId: stationId, releaseOrigin: releaseOrigin, readerVersion: readerVersion)
            return value
        }
        // B28
        try await observe("B28", callee: "B28", resultType: "CanonicalCacheBytes", arguments: .object(["cache_document": .string(String(reflecting: cacheDocument))])) {
            let value: CanonicalCacheBytes = try Canonical.encodeCacheJson(cacheDocument: cacheDocument)
            return value
        }
        // B29
        try await observe("B29", callee: "B29", resultType: "CanonicalStationOrTombstoneOrNull", arguments: .object(["release_view": .string(String(reflecting: releaseView)), "identity_query": .string(String(reflecting: identityQuery)), "reader_version": .string(String(reflecting: readerVersion))])) {
            let value: CanonicalStationOrTombstoneOrNull = try Canonical.lookupStationIdentity(releaseView: releaseView, identityQuery: identityQuery, readerVersion: readerVersion)
            return value
        }
        // B30
        try await observe("B30", callee: "B30", resultType: "CanonicalEffectiveRecommendation", arguments: .object(["station_sets": .string(String(reflecting: stationSets)), "original_recommendation": .string(String(reflecting: originalRecommendation)), "commercial_only": .string(String(reflecting: commercialOnly))])) {
            let value: CanonicalEffectiveRecommendation = try Canonical.selectEffectiveRecommendation(stationSets: stationSets, originalRecommendation: originalRecommendation, commercialOnly: commercialOnly)
            return value
        }
        // B31
        try await observe("B31", callee: "B31", resultType: "CanonicalQualityAdmission", arguments: .object(["candidate_path": .string(String(reflecting: candidatePath)), "include_flagged": .string(String(reflecting: includeFlagged)), "include_fallback": .string(String(reflecting: includeFallback))])) {
            let value: CanonicalQualityAdmission = try Canonical.admitQualityPath(candidatePath: candidatePath, includeFlagged: includeFlagged, includeFallback: includeFallback)
            return value
        }
        // B32
        try await observe("B32", callee: "B32", resultType: "CanonicalCommercialAdmission", arguments: .object(["candidate_path": .string(String(reflecting: candidatePath)), "commercial_only": .string(String(reflecting: commercialOnly)), "commercial_basis": .string(String(reflecting: commercialBasis))])) {
            let value: CanonicalCommercialAdmission = try Canonical.admitCommercialPath(candidatePath: candidatePath, commercialOnly: commercialOnly, commercialBasis: commercialBasis)
            return value
        }
        // B33
        try await observe("B33", callee: "B33", resultType: "CanonicalSelectedReferencePath", arguments: .object(["station_source_row": .string(String(reflecting: stationSourceRow)), "path_request": .string(String(reflecting: pathRequest)), "release_view": .string(String(reflecting: releaseView))])) {
            let value: CanonicalSelectedReferencePath = try Canonical.resolveReferencePath(stationSourceRow: stationSourceRow, pathRequest: pathRequest, releaseView: releaseView)
            return value
        }
        // B34
        try await observe("B34", callee: "B34", resultType: "CanonicalOrderedStationResults", arguments: .object(["release_view": .string(String(reflecting: releaseView)), "query_kind": .string(String(reflecting: queryKind)), "query_options": .string(String(reflecting: queryOptions)), "reader_version": .string(String(reflecting: readerVersion))])) {
            let value: CanonicalOrderedStationResults = try Canonical.executeDiscoveryQuery(releaseView: releaseView, queryKind: queryKind, queryOptions: queryOptions, readerVersion: readerVersion)
            return value
        }
        // B35
        try await observe("B35", callee: "B35", resultType: "CanonicalStationSummary", arguments: .object(["summary_kind": .string(String(reflecting: summaryKind)), "release_view": .string(String(reflecting: releaseView)), "station_sets": .string(String(reflecting: stationSets)), "summary_options": .string(String(reflecting: summaryOptions))])) {
            let value: CanonicalStationSummary = try Canonical.summarizeStationSets(summaryKind: summaryKind, releaseView: releaseView, stationSets: stationSets, summaryOptions: summaryOptions)
            return value
        }
        // B36
        try await observe("B36", callee: "B36", resultType: "CanonicalHistoricalAdmission", arguments: .object(["own_offset": .string(String(reflecting: ownOffset)), "reference_path": .string(String(reflecting: referencePath)), "historical_policy": .string(String(reflecting: historicalPolicy)), "selection_kind": .string(String(reflecting: selectionKind)), "reader_version": .string(String(reflecting: readerVersion))])) {
            let value: CanonicalHistoricalAdmission = try Canonical.admitHistoricalOffset(ownOffset: ownOffset, referencePath: referencePath, historicalPolicy: historicalPolicy, selectionKind: selectionKind, readerVersion: readerVersion)
            return value
        }
        // B37
        try await observe("B37", callee: "B37", resultType: "CanonicalAttributionText", arguments: .object(["station": .string(String(reflecting: station)), "release_view": .string(String(reflecting: releaseView)), "commercial_only": .string(String(reflecting: commercialOnly))])) {
            let value: CanonicalAttributionText = try Canonical.formatAttribution(station: station, releaseView: releaseView, commercialOnly: commercialOnly)
            return value
        }
        // B38
        try await observe("B38", callee: "B38", resultType: "CanonicalCitationText", arguments: .object(["published_metadata": .string(String(reflecting: publishedMetadata)), "citation_style": .string(String(reflecting: citationStyle))])) {
            let value: CanonicalCitationText = try Canonical.formatCitation(publishedMetadata: publishedMetadata, citationStyle: citationStyle)
            return value
        }
        // B39
        try await observe("B39", callee: "B39", resultType: "CanonicalPredictionWindow", arguments: .object(["time_inputs": .string(String(reflecting: timeInputs)), "window_inputs": .string(String(reflecting: windowInputs)), "step": .string(String(reflecting: step)), "local_time_profile": .string(String(reflecting: localTimeProfile))])) {
            let value: CanonicalPredictionWindow = try Canonical.parsePredictionWindow(timeInputs: timeInputs, windowInputs: windowInputs, step: step, localTimeProfile: localTimeProfile)
            return value
        }
        // B40
        try await observe("B40", callee: "B40", resultType: "CanonicalSelectedPredictionModel", arguments: .object(["station_request": .string(String(reflecting: stationRequest)), "release_view": .string(String(reflecting: releaseView)), "selection_options": .string(String(reflecting: selectionOptions)), "reader_version": .string(String(reflecting: readerVersion))])) {
            let value: CanonicalSelectedPredictionModel = try Canonical.selectPredictionModel(stationRequest: stationRequest, releaseView: releaseView, selectionOptions: selectionOptions, readerVersion: readerVersion)
            return value
        }
        // B41
        try await observe("B41", callee: "B41", resultType: "CanonicalAstronomicalTerms", arguments: .object(["selected_prediction_model": .string(String(reflecting: selectedPredictionModel)), "utc_instant": .string(String(reflecting: utcInstant))])) {
            let value: CanonicalAstronomicalTerms = try Canonical.evaluateAstronomy(selectedPredictionModel: selectedPredictionModel, utcInstant: utcInstant)
            return value
        }
        // B42
        try await observe("B42", callee: "B42", resultType: "CanonicalHeightValues", arguments: .object(["selected_prediction_model": .string(String(reflecting: selectedPredictionModel)), "prediction_instants": .string(String(reflecting: predictionInstants)), "requested_datum": .string(String(reflecting: requestedDatum))])) {
            let value: CanonicalHeightValues = try Canonical.evaluateHarmonicHeight(selectedPredictionModel: selectedPredictionModel, predictionInstants: predictionInstants, requestedDatum: requestedDatum)
            return value
        }
        // B43
        try await observe("B43", callee: "B43", resultType: "CanonicalTideEvents", arguments: .object(["selected_prediction_model": .string(String(reflecting: selectedPredictionModel)), "prediction_window": .string(String(reflecting: predictionWindow))])) {
            let value: CanonicalTideEvents = try Canonical.findTideEvents(selectedPredictionModel: selectedPredictionModel, predictionWindow: predictionWindow)
            return value
        }
        // B44
        try await observe("B44", callee: "B44", resultType: "CanonicalDirectCurrentResult", arguments: .object(["selected_prediction_model": .string(String(reflecting: selectedPredictionModel)), "prediction_window": .string(String(reflecting: predictionWindow)), "current_request": .string(String(reflecting: currentRequest)), "current_operation": .string(String(reflecting: currentOperation))])) {
            let value: CanonicalDirectCurrentResult = try Canonical.evaluateDirectCurrent(selectedPredictionModel: selectedPredictionModel, predictionWindow: predictionWindow, currentRequest: currentRequest, currentOperation: currentOperation)
            return value
        }
        // B45
        try await observe("B45", callee: "B45", resultType: "CanonicalOffsetTideResult", arguments: .object(["own_offset": .string(String(reflecting: ownOffset)), "reference_path": .string(String(reflecting: referencePath)), "prediction_window": .string(String(reflecting: predictionWindow)), "tide_request": .string(String(reflecting: tideRequest)), "reader_version": .string(String(reflecting: readerVersion))])) {
            let value: CanonicalOffsetTideResult = try Canonical.evaluateTideOffset(ownOffset: ownOffset, referencePath: referencePath, predictionWindow: predictionWindow, tideRequest: tideRequest, readerVersion: readerVersion)
            return value
        }
        // B46
        try await observe("B46", callee: "B46", resultType: "CanonicalFoldedHeightValues", arguments: .object(["own_offset": .string(String(reflecting: ownOffset)), "reference_model": .string(String(reflecting: referenceModel)), "prediction_instants": .string(String(reflecting: predictionInstants)), "requested_datum": .string(String(reflecting: requestedDatum))])) {
            let value: CanonicalFoldedHeightValues = try Canonical.foldEqualTideOffset(ownOffset: ownOffset, referenceModel: referenceModel, predictionInstants: predictionInstants, requestedDatum: requestedDatum)
            return value
        }
        // B47
        try await observe("B47", callee: "B47", resultType: "CanonicalOffsetCurrentResult", arguments: .object(["own_current_offsets": .string(String(reflecting: ownCurrentOffsets)), "reference_path": .string(String(reflecting: referencePath)), "prediction_window": .string(String(reflecting: predictionWindow)), "current_request": .string(String(reflecting: currentRequest)), "reader_version": .string(String(reflecting: readerVersion))])) {
            let value: CanonicalOffsetCurrentResult = try Canonical.evaluateCurrentOffset(ownCurrentOffsets: ownCurrentOffsets, referencePath: referencePath, predictionWindow: predictionWindow, currentRequest: currentRequest, readerVersion: readerVersion)
            return value
        }
        // B48
        try await observe("B48", callee: "B48", resultType: "CanonicalAuxiliaryResult", arguments: .object(["auxiliary_kind": .string(String(reflecting: auxiliaryKind)), "auxiliary_operation": .string(String(reflecting: auxiliaryOperation)), "source_values": .string(String(reflecting: sourceValues)), "result_context": .string(String(reflecting: resultContext)), "local_time_profile": .string(String(reflecting: localTimeProfile)), "result_values": .string(String(reflecting: resultValues)), "utc_result": .string(String(reflecting: utcResult)), "selection_options": .string(String(reflecting: selectionOptions)), "reader_version": .string(String(reflecting: readerVersion)), "auxiliary_member_id": .string(String(reflecting: auxiliaryMemberId))])) {
            let value: CanonicalAuxiliaryResult = try Canonical.dispatchAuxiliaryResult(auxiliaryKind: auxiliaryKind, auxiliaryOperation: auxiliaryOperation, sourceValues: sourceValues, resultContext: resultContext, localTimeProfile: localTimeProfile, resultValues: resultValues, utcResult: utcResult, selectionOptions: selectionOptions, readerVersion: readerVersion, auxiliaryMemberId: auxiliaryMemberId)
            return value
        }
        // B08.raw
        try await observe("B08.raw", callee: "B08.raw", resultType: "CanonicalRawRecord", arguments: .object(["source_record": .string(String(reflecting: sourceRecord)), "native_profile": .string(String(reflecting: nativeProfile))])) {
            let value: CanonicalRawRecord = try Canonical.retainRawSourceRecord(sourceRecord: sourceRecord, nativeProfile: nativeProfile)
            return value
        }
        // B08.origin
        try await observe("B08.origin", callee: "B08.origin", resultType: "CanonicalValidStation", arguments: .object(["station": .string(String(reflecting: station)), "release_origin": .string(String(reflecting: releaseOrigin))])) {
            let value: CanonicalValidStation = try Canonical.checkStationOrigin(station: station, releaseOrigin: releaseOrigin)
            return value
        }
        // B23.lock
        try await observe("B23.lock", callee: "B23.lock", resultType: "CanonicalLockOutcome", arguments: .object(["lock_request": .string(String(reflecting: lockRequest)), "lock_state": .string(String(reflecting: lockState)), "clock": .string(String(reflecting: clock))])) {
            let value: CanonicalLockOutcome = try await Canonical.manageCacheLock(lockRequest: lockRequest, lockState: lockState, clock: clock)
            return value
        }
        // B23.http
        try await observe("B23.http", callee: "B23.http", resultType: "CanonicalHttpResponse", arguments: .object(["http_request": .string(String(reflecting: httpRequest)), "transport_options": .string(String(reflecting: transportOptions))])) {
            let value: CanonicalHttpResponse = try await Canonical.requestHttpResource(httpRequest: httpRequest, transportOptions: transportOptions)
            return value
        }
        // B35.stats
        try await observe("B35.stats", callee: "B35.stats", resultType: "CanonicalReleaseStatistics", arguments: .object(["release_view": .string(String(reflecting: releaseView))])) {
            let value: CanonicalReleaseStatistics = try Canonical.countReleaseStatistics(releaseView: releaseView)
            return value
        }
        // B35.sets
        try await observe("B35.sets", callee: "B35.sets", resultType: "CanonicalOrderedConstantSets", arguments: .object(["station_sets": .string(String(reflecting: stationSets)), "original_recommendation": .string(String(reflecting: originalRecommendation)), "commercial_only": .string(String(reflecting: commercialOnly)), "include_no_constants": .string(String(reflecting: includeNoConstants))])) {
            let value: CanonicalOrderedConstantSets = try Canonical.orderConstantSets(stationSets: stationSets, originalRecommendation: originalRecommendation, commercialOnly: commercialOnly, includeNoConstants: includeNoConstants)
            return value
        }
        // B48.aux
        try await observe("B48.aux", callee: "B48.aux", resultType: "CanonicalAuxiliaryModelValue", arguments: .object(["auxiliary_operation": .string(String(reflecting: auxiliaryOperation)), "source_values": .string(String(reflecting: sourceValues)), "selection_options": .string(String(reflecting: selectionOptions)), "reader_version": .string(String(reflecting: readerVersion)), "auxiliary_member_id": .string(String(reflecting: auxiliaryMemberId))])) {
            let value: CanonicalAuxiliaryModelValue = try Canonical.readAuxiliaryModelValue(auxiliaryOperation: auxiliaryOperation, sourceValues: sourceValues, selectionOptions: selectionOptions, readerVersion: readerVersion, auxiliaryMemberId: auxiliaryMemberId)
            return value
        }
        // B48.context
        try await observe("B48.context", callee: "B48.context", resultType: "CanonicalPredictionResult", arguments: .object(["result_values": .string(String(reflecting: resultValues)), "result_context": .string(String(reflecting: resultContext))])) {
            let value: CanonicalPredictionResult = try Canonical.constructPredictionResult(resultValues: resultValues, resultContext: resultContext)
            return value
        }
        // B48.local
        try await observe("B48.local", callee: "B48.local", resultType: "CanonicalLocalTimeResult", arguments: .object(["utc_result": .string(String(reflecting: utcResult)), "local_time_profile": .string(String(reflecting: localTimeProfile))])) {
            let value: CanonicalLocalTimeResult = try Canonical.convertResultToLocalTime(utcResult: utcResult, localTimeProfile: localTimeProfile)
            return value
        }
        // B43.roots
        try await observe("B43.roots", callee: "B43.roots", resultType: "CanonicalUnroundedTideEvents", arguments: .object(["selected_prediction_model": .string(String(reflecting: selectedPredictionModel)), "prediction_window": .string(String(reflecting: predictionWindow))])) {
            let value: CanonicalUnroundedTideEvents = try Canonical.findUnroundedTideEvents(selectedPredictionModel: selectedPredictionModel, predictionWindow: predictionWindow)
            return value
        }
        // B44.roots
        try await observe("B44.roots", callee: "B44.roots", resultType: "CanonicalUnroundedCurrentEvents", arguments: .object(["selected_prediction_model": .string(String(reflecting: selectedPredictionModel)), "prediction_window": .string(String(reflecting: predictionWindow)), "current_request": .string(String(reflecting: currentRequest))])) {
            let value: CanonicalUnroundedCurrentEvents = try Canonical.findUnroundedCurrentEvents(selectedPredictionModel: selectedPredictionModel, predictionWindow: predictionWindow, currentRequest: currentRequest)
            return value
        }
        // B17.sidecar
        try await observe("B17.sidecar", callee: "B17.sidecar", resultType: "CanonicalChecksumBytes", arguments: .object(["acquisition_descriptor": .string(String(reflecting: acquisitionDescriptor)), "effective_options": .string(String(reflecting: effectiveOptions))])) {
            let value: CanonicalChecksumBytes = try await Canonical.acquireChecksumSidecar(acquisitionDescriptor: acquisitionDescriptor, effectiveOptions: effectiveOptions)
            return value
        }
        // B08.S1.A1 guard: access_kind = raw_record
        try await observe("B08.S1.A1", callee: "B08.raw", resultType: "CanonicalRawRecord", arguments: .object(["source_record": .string(String(reflecting: sourceRecord)), "native_profile": .string(String(reflecting: nativeProfile))])) {
            let value: CanonicalRawRecord = try Canonical.retainRawSourceRecord(sourceRecord: sourceRecord, nativeProfile: nativeProfile)
            return value
        }
        // B08.S1.A2 guard: access_kind = station_object
        try await observe("B08.S1.A2", callee: "B08.origin", resultType: "CanonicalValidStation", arguments: .object(["station": .string(String(reflecting: station)), "release_origin": .string(String(reflecting: releaseOrigin))])) {
            let value: CanonicalValidStation = try Canonical.checkStationOrigin(station: station, releaseOrigin: releaseOrigin)
            return value
        }
        // B09.S1.A3 guard: always
        try await observe("B09.S1.A3", callee: "B01", resultType: "CanonicalValidatedArguments", arguments: .object(["operation": .string(String(reflecting: operation)), "arguments": .string(String(reflecting: arguments)), "member_contract": .string(String(reflecting: memberContract))])) {
            let value: CanonicalValidatedArguments = try Canonical.validateOperationArguments(operation: operation, arguments: arguments, memberContract: memberContract)
            return value
        }
        // B09.S1.A4 guard: always
        try await observe("B09.S1.A4", callee: "B02", resultType: "CanonicalEffectiveOptions", arguments: .object(["explicit_options": .string(String(reflecting: explicitOptions)), "environment": .string(String(reflecting: environment)), "platform_defaults": .string(String(reflecting: platformDefaults))])) {
            let value: CanonicalEffectiveOptions = try Canonical.resolveEffectiveOptions(explicitOptions: explicitOptions, environment: environment, platformDefaults: platformDefaults)
            return value
        }
        // B09.S1.A5 guard: release-request branch
        try await observe("B09.S1.A5", callee: "B10", resultType: "CanonicalLoadedRelease", arguments: .object(["release_request": .string(String(reflecting: releaseRequest)), "effective_options": .string(String(reflecting: effectiveOptions)), "cache_state": .string(String(reflecting: cacheState)), "clock": .string(String(reflecting: clock)), "reader_version": .string(String(reflecting: readerVersion))])) {
            let value: CanonicalLoadedRelease = try await Canonical.resolveReleaseRequest(releaseRequest: releaseRequest, effectiveOptions: effectiveOptions, cacheState: cacheState, clock: clock, readerVersion: readerVersion)
            return value
        }
        // B09.S2.A4 guard: local checksum sidecar required or supplied
        try await observe("B09.S2.A4", callee: "B16", resultType: "CanonicalBoundChecksums", arguments: .object(["checksum_bytes": .string(String(reflecting: checksumBytes)), "pointer_digests": .string(String(reflecting: pointerDigests)), "required_files": .string(String(reflecting: requiredFiles))])) {
            let value: CanonicalBoundChecksums = try Canonical.bindChecksumManifest(checksumBytes: checksumBytes, pointerDigests: pointerDigests, requiredFiles: requiredFiles)
            return value
        }
        // B09.S2.A9 guard: local-file branch
        try await observe("B09.S2.A9", callee: "B05", resultType: "CanonicalParsedDocument", arguments: .object(["source_bytes": .string(String(reflecting: sourceBytes)), "reader_version": .string(String(reflecting: readerVersion)), "document_kind": .string(String(reflecting: documentKind))])) {
            let value: CanonicalParsedDocument = try Canonical.decodeReleaseDocument(sourceBytes: sourceBytes, readerVersion: readerVersion, documentKind: documentKind)
            return value
        }
        // B09.S2.A11 guard: local-file branch
        try await observe("B09.S2.A11", callee: "B06", resultType: "CanonicalValidatedReleaseGraph", arguments: .object(["parsed_document": .string(String(reflecting: parsedDocument)), "required_links": .string(String(reflecting: requiredLinks))])) {
            let value: CanonicalValidatedReleaseGraph = try Canonical.validateReleaseLinks(parsedDocument: parsedDocument, requiredLinks: requiredLinks)
            return value
        }
        // B10.S1.A2 guard: pinned cache attempt
        try await observe("B10.S1.A2", callee: "B19", resultType: "CanonicalUsableCachedReleaseOrError", arguments: .object(["release_candidates": .string(String(reflecting: releaseCandidates)), "effective_options": .string(String(reflecting: effectiveOptions)), "cache_state": .string(String(reflecting: cacheState)), "clock": .string(String(reflecting: clock))])) {
            let value: CanonicalUsableCachedReleaseOrError = try Canonical.selectCachedRelease(releaseCandidates: releaseCandidates, effectiveOptions: effectiveOptions, cacheState: cacheState, clock: clock)
            return value
        }
        // B10.S1.A5 guard: pinned cache missing and online
        try await observe("B10.S1.A5", callee: "B17", resultType: "CanonicalLoadedRelease", arguments: .object(["acquisition_descriptor": .string(String(reflecting: acquisitionDescriptor)), "effective_options": .string(String(reflecting: effectiveOptions)), "load_mode": .string(String(reflecting: loadMode)), "cache_state": .string(String(reflecting: cacheState)), "clock": .string(String(reflecting: clock)), "reader_version": .string(String(reflecting: readerVersion))])) {
            let value: CanonicalLoadedRelease = try await Canonical.acquireReleaseFiles(acquisitionDescriptor: acquisitionDescriptor, effectiveOptions: effectiveOptions, loadMode: loadMode, cacheState: cacheState, clock: clock, readerVersion: readerVersion)
            return value
        }
        // B10.S2.A1 guard: latest offline
        try await observe("B10.S2.A1", callee: "B19", resultType: "CanonicalUsableCachedReleaseOrError", arguments: .object(["release_candidates": .string(String(reflecting: releaseCandidates)), "effective_options": .string(String(reflecting: effectiveOptions)), "cache_state": .string(String(reflecting: cacheState)), "clock": .string(String(reflecting: clock))])) {
            let value: CanonicalUsableCachedReleaseOrError = try Canonical.selectCachedRelease(releaseCandidates: releaseCandidates, effectiveOptions: effectiveOptions, cacheState: cacheState, clock: clock)
            return value
        }
        // B10.S3.A4 guard: latest online
        try await observe("B10.S3.A4", callee: "B11", resultType: "CanonicalValidatedMetadata", arguments: .object(["metadata_request": .string(String(reflecting: metadataRequest)), "trusted_cache": .string(String(reflecting: trustedCache)), "transport_options": .string(String(reflecting: transportOptions)), "cache_state": .string(String(reflecting: cacheState)), "clock": .string(String(reflecting: clock)), "reader_version": .string(String(reflecting: readerVersion))])) {
            let value: CanonicalValidatedMetadata = try await Canonical.exchangeReleaseMetadata(metadataRequest: metadataRequest, trustedCache: trustedCache, transportOptions: transportOptions, cacheState: cacheState, clock: clock, readerVersion: readerVersion)
            return value
        }
        // B10.S3.A6 guard: latest online metadata selected a release
        try await observe("B10.S3.A6", callee: "B17", resultType: "CanonicalLoadedRelease", arguments: .object(["acquisition_descriptor": .string(String(reflecting: acquisitionDescriptor)), "effective_options": .string(String(reflecting: effectiveOptions)), "load_mode": .string(String(reflecting: loadMode)), "cache_state": .string(String(reflecting: cacheState)), "clock": .string(String(reflecting: clock)), "reader_version": .string(String(reflecting: readerVersion))])) {
            let value: CanonicalLoadedRelease = try await Canonical.acquireReleaseFiles(acquisitionDescriptor: acquisitionDescriptor, effectiveOptions: effectiveOptions, loadMode: loadMode, cacheState: cacheState, clock: clock, readerVersion: readerVersion)
            return value
        }
        // B10.S4.A1 guard: network failure and use_cache
        try await observe("B10.S4.A1", callee: "B19", resultType: "CanonicalUsableCachedReleaseOrError", arguments: .object(["release_candidates": .string(String(reflecting: releaseCandidates)), "effective_options": .string(String(reflecting: effectiveOptions)), "cache_state": .string(String(reflecting: cacheState)), "clock": .string(String(reflecting: clock))])) {
            let value: CanonicalUsableCachedReleaseOrError = try Canonical.selectCachedRelease(releaseCandidates: releaseCandidates, effectiveOptions: effectiveOptions, cacheState: cacheState, clock: clock)
            return value
        }
        // B11.S2.A2 guard: a network request is permitted
        try await observe("B11.S2.A2", callee: "B23.http", resultType: "CanonicalHttpResponse", arguments: .object(["http_request": .string(String(reflecting: httpRequest)), "transport_options": .string(String(reflecting: transportOptions))])) {
            let value: CanonicalHttpResponse = try await Canonical.requestHttpResource(httpRequest: httpRequest, transportOptions: transportOptions)
            return value
        }
        // B11.S3.A5 guard: a fresh response or candidate cached body exists
        try await observe("B11.S3.A5", callee: "B05", resultType: "CanonicalParsedDocument", arguments: .object(["source_bytes": .string(String(reflecting: sourceBytes)), "reader_version": .string(String(reflecting: readerVersion)), "document_kind": .string(String(reflecting: documentKind))])) {
            let value: CanonicalParsedDocument = try Canonical.decodeReleaseDocument(sourceBytes: sourceBytes, readerVersion: readerVersion, documentKind: documentKind)
            return value
        }
        // B11.S5.A2 guard: publish conditional body/tag
        try await observe("B11.S5.A2", callee: "B23.lock", resultType: "CanonicalLockOutcome", arguments: .object(["lock_request": .string(String(reflecting: lockRequest)), "lock_state": .string(String(reflecting: lockState)), "clock": .string(String(reflecting: clock))])) {
            let value: CanonicalLockOutcome = try await Canonical.manageCacheLock(lockRequest: lockRequest, lockState: lockState, clock: clock)
            return value
        }
        // B11.S5.A4 guard: publish valid metadata body
        try await observe("B11.S5.A4", callee: "B28", resultType: "CanonicalCacheBytes", arguments: .object(["cache_document": .string(String(reflecting: cacheDocument))])) {
            let value: CanonicalCacheBytes = try Canonical.encodeCacheJson(cacheDocument: cacheDocument)
            return value
        }
        // B12.S1.A3 guard: always
        try await observe("B12.S1.A3", callee: "B15", resultType: "CanonicalResourceStateOrError", arguments: .object(["resource_state": .string(String(reflecting: resourceState)), "lifetime_action": .string(String(reflecting: lifetimeAction))])) {
            let value: CanonicalResourceStateOrError = try Canonical.enforceResourceLifetime(resourceState: resourceState, lifetimeAction: lifetimeAction)
            return value
        }
        // B12.S1.A7 guard: update restrictions pass
        try await observe("B12.S1.A7", callee: "B11", resultType: "CanonicalValidatedMetadata", arguments: .object(["metadata_request": .string(String(reflecting: metadataRequest)), "trusted_cache": .string(String(reflecting: trustedCache)), "transport_options": .string(String(reflecting: transportOptions)), "cache_state": .string(String(reflecting: cacheState)), "clock": .string(String(reflecting: clock)), "reader_version": .string(String(reflecting: readerVersion))])) {
            let value: CanonicalValidatedMetadata = try await Canonical.exchangeReleaseMetadata(metadataRequest: metadataRequest, trustedCache: trustedCache, transportOptions: transportOptions, cacheState: cacheState, clock: clock, readerVersion: readerVersion)
            return value
        }
        // B12.S2.A2 guard: a new candidate exists
        try await observe("B12.S2.A2", callee: "B10", resultType: "CanonicalLoadedRelease", arguments: .object(["release_request": .string(String(reflecting: releaseRequest)), "effective_options": .string(String(reflecting: effectiveOptions)), "cache_state": .string(String(reflecting: cacheState)), "clock": .string(String(reflecting: clock)), "reader_version": .string(String(reflecting: readerVersion))])) {
            let value: CanonicalLoadedRelease = try await Canonical.resolveReleaseRequest(releaseRequest: releaseRequest, effectiveOptions: effectiveOptions, cacheState: cacheState, clock: clock, readerVersion: readerVersion)
            return value
        }
        // B13.S3.A2 guard: eligible open accessor or query
        try await observe("B13.S3.A2", callee: "B12", resultType: "CanonicalUpdatedClientState", arguments: .object(["client_state": .string(String(reflecting: clientState)), "update_request": .string(String(reflecting: updateRequest)), "clock": .string(String(reflecting: clock)), "reader_version": .string(String(reflecting: readerVersion))])) {
            let value: CanonicalUpdatedClientState = try await Canonical.updateClientRelease(clientState: clientState, updateRequest: updateRequest, clock: clock, readerVersion: readerVersion)
            return value
        }
        // B14.S2.A2 guard: always
        try await observe("B14.S2.A2", callee: "B15", resultType: "CanonicalResourceStateOrError", arguments: .object(["resource_state": .string(String(reflecting: resourceState)), "lifetime_action": .string(String(reflecting: lifetimeAction))])) {
            let value: CanonicalResourceStateOrError = try Canonical.enforceResourceLifetime(resourceState: resourceState, lifetimeAction: lifetimeAction)
            return value
        }
        // B17.S1.A2 guard: always
        try await observe("B17.S1.A2", callee: "B23.lock", resultType: "CanonicalLockOutcome", arguments: .object(["lock_request": .string(String(reflecting: lockRequest)), "lock_state": .string(String(reflecting: lockState)), "clock": .string(String(reflecting: clock))])) {
            let value: CanonicalLockOutcome = try await Canonical.manageCacheLock(lockRequest: lockRequest, lockState: lockState, clock: clock)
            return value
        }
        // B17.S1.A3 guard: recheck under owned lock
        try await observe("B17.S1.A3", callee: "B19", resultType: "CanonicalUsableCachedReleaseOrError", arguments: .object(["release_candidates": .string(String(reflecting: releaseCandidates)), "effective_options": .string(String(reflecting: effectiveOptions)), "cache_state": .string(String(reflecting: cacheState)), "clock": .string(String(reflecting: clock))])) {
            let value: CanonicalUsableCachedReleaseOrError = try Canonical.selectCachedRelease(releaseCandidates: releaseCandidates, effectiveOptions: effectiveOptions, cacheState: cacheState, clock: clock)
            return value
        }
        // B17.S2.A1 guard: always under owned release acquisition lock before data acquisition
        try await observe("B17.S2.A1", callee: "B17.sidecar", resultType: "CanonicalChecksumBytes", arguments: .object(["acquisition_descriptor": .string(String(reflecting: acquisitionDescriptor)), "effective_options": .string(String(reflecting: effectiveOptions))])) {
            let value: CanonicalChecksumBytes = try await Canonical.acquireChecksumSidecar(acquisitionDescriptor: acquisitionDescriptor, effectiveOptions: effectiveOptions)
            return value
        }
        // B17.S2.A3 guard: before acquisition
        try await observe("B17.S2.A3", callee: "B16", resultType: "CanonicalBoundChecksums", arguments: .object(["checksum_bytes": .string(String(reflecting: checksumBytes)), "pointer_digests": .string(String(reflecting: pointerDigests)), "required_files": .string(String(reflecting: requiredFiles))])) {
            let value: CanonicalBoundChecksums = try Canonical.bindChecksumManifest(checksumBytes: checksumBytes, pointerDigests: pointerDigests, requiredFiles: requiredFiles)
            return value
        }
        // B17.S2.A6 guard: a required data file is missing and online
        try await observe("B17.S2.A6", callee: "B23.http", resultType: "CanonicalHttpResponse", arguments: .object(["http_request": .string(String(reflecting: httpRequest)), "transport_options": .string(String(reflecting: transportOptions))])) {
            let value: CanonicalHttpResponse = try await Canonical.requestHttpResource(httpRequest: httpRequest, transportOptions: transportOptions)
            return value
        }
        // B17.S4.A2 guard: checked data files are published
        try await observe("B17.S4.A2", callee: "B18", resultType: "CanonicalMergedReceipt", arguments: .object(["locked_cache_state": .string(String(reflecting: lockedCacheState)), "verified_file_rows": .string(String(reflecting: verifiedFileRows)), "release_metadata": .string(String(reflecting: releaseMetadata))])) {
            let value: CanonicalMergedReceipt = try Canonical.mergeCacheReceipt(lockedCacheState: lockedCacheState, verifiedFileRows: verifiedFileRows, releaseMetadata: releaseMetadata)
            return value
        }
        // B17.S5.A4 guard: stream mode
        try await observe("B17.S5.A4", callee: "B25", resultType: "CanonicalAuthenticatedIndex", arguments: .object(["source_files": .string(String(reflecting: sourceFiles)), "supplied_index": .string(String(reflecting: suppliedIndex)), "index_presence": .string(String(reflecting: indexPresence)), "reader_version": .string(String(reflecting: readerVersion))])) {
            let value: CanonicalAuthenticatedIndex = try Canonical.authenticateStationIndex(sourceFiles: sourceFiles, suppliedIndex: suppliedIndex, indexPresence: indexPresence, readerVersion: readerVersion)
            return value
        }
        // B18.S4.A2 guard: publish merged receipt
        try await observe("B18.S4.A2", callee: "B28", resultType: "CanonicalCacheBytes", arguments: .object(["cache_document": .string(String(reflecting: cacheDocument))])) {
            let value: CanonicalCacheBytes = try Canonical.encodeCacheJson(cacheDocument: cacheDocument)
            return value
        }
        // B19.S3.A2 guard: a corrupt candidate is eligible for heal
        try await observe("B19.S3.A2", callee: "B23.lock", resultType: "CanonicalLockOutcome", arguments: .object(["lock_request": .string(String(reflecting: lockRequest)), "lock_state": .string(String(reflecting: lockState)), "clock": .string(String(reflecting: clock))])) {
            let value: CanonicalLockOutcome = try await Canonical.manageCacheLock(lockRequest: lockRequest, lockState: lockState, clock: clock)
            return value
        }
        // B20.S2.A2 guard: checksum binding exists
        try await observe("B20.S2.A2", callee: "B16", resultType: "CanonicalBoundChecksums", arguments: .object(["checksum_bytes": .string(String(reflecting: checksumBytes)), "pointer_digests": .string(String(reflecting: pointerDigests)), "required_files": .string(String(reflecting: requiredFiles))])) {
            let value: CanonicalBoundChecksums = try Canonical.bindChecksumManifest(checksumBytes: checksumBytes, pointerDigests: pointerDigests, requiredFiles: requiredFiles)
            return value
        }
        // B21.S2.A1 guard: before download publication
        try await observe("B21.S2.A1", callee: "B16", resultType: "CanonicalBoundChecksums", arguments: .object(["checksum_bytes": .string(String(reflecting: checksumBytes)), "pointer_digests": .string(String(reflecting: pointerDigests)), "required_files": .string(String(reflecting: requiredFiles))])) {
            let value: CanonicalBoundChecksums = try Canonical.bindChecksumManifest(checksumBytes: checksumBytes, pointerDigests: pointerDigests, requiredFiles: requiredFiles)
            return value
        }
        // B22.S4.A2 guard: prune deletion or partial sweep
        try await observe("B22.S4.A2", callee: "B23.lock", resultType: "CanonicalLockOutcome", arguments: .object(["lock_request": .string(String(reflecting: lockRequest)), "lock_state": .string(String(reflecting: lockState)), "clock": .string(String(reflecting: clock))])) {
            let value: CanonicalLockOutcome = try await Canonical.manageCacheLock(lockRequest: lockRequest, lockState: lockState, clock: clock)
            return value
        }
        // B23.S1.A5 guard: io_kind = lock
        try await observe("B23.S1.A5", callee: "B23.lock", resultType: "CanonicalLockOutcome", arguments: .object(["lock_request": .string(String(reflecting: lockRequest)), "lock_state": .string(String(reflecting: lockState)), "clock": .string(String(reflecting: clock))])) {
            let value: CanonicalLockOutcome = try await Canonical.manageCacheLock(lockRequest: lockRequest, lockState: lockState, clock: clock)
            return value
        }
        // B23.S1.A7 guard: io_kind = http
        try await observe("B23.S1.A7", callee: "B23.http", resultType: "CanonicalHttpResponse", arguments: .object(["http_request": .string(String(reflecting: httpRequest)), "transport_options": .string(String(reflecting: transportOptions))])) {
            let value: CanonicalHttpResponse = try await Canonical.requestHttpResource(httpRequest: httpRequest, transportOptions: transportOptions)
            return value
        }
        // B25.S4.A4 guard: stale or absent index requires one source pass
        try await observe("B25.S4.A4", callee: "B24", resultType: "CanonicalStationIndexEntry", arguments: .object(["station_source_row": .string(String(reflecting: stationSourceRow)), "source_byte_span": .string(String(reflecting: sourceByteSpan)), "projection_contract": .string(String(reflecting: projectionContract))])) {
            let value: CanonicalStationIndexEntry = try Canonical.projectStationIndex(stationSourceRow: stationSourceRow, sourceByteSpan: sourceByteSpan, projectionContract: projectionContract)
            return value
        }
        // B25.S4.A6 guard: publish rebuilt index
        try await observe("B25.S4.A6", callee: "B28", resultType: "CanonicalCacheBytes", arguments: .object(["cache_document": .string(String(reflecting: cacheDocument))])) {
            let value: CanonicalCacheBytes = try Canonical.encodeCacheJson(cacheDocument: cacheDocument)
            return value
        }
        // B27.S1.A1 guard: always
        try await observe("B27.S1.A1", callee: "B15", resultType: "CanonicalResourceStateOrError", arguments: .object(["resource_state": .string(String(reflecting: resourceState)), "lifetime_action": .string(String(reflecting: lifetimeAction))])) {
            let value: CanonicalResourceStateOrError = try Canonical.enforceResourceLifetime(resourceState: resourceState, lifetimeAction: lifetimeAction)
            return value
        }
        // B27.S4.A3 guard: LRU miss and row was not in the LRU
        try await observe("B27.S4.A3", callee: "B05", resultType: "CanonicalParsedDocument", arguments: .object(["source_bytes": .string(String(reflecting: sourceBytes)), "reader_version": .string(String(reflecting: readerVersion)), "document_kind": .string(String(reflecting: documentKind))])) {
            let value: CanonicalParsedDocument = try Canonical.decodeReleaseDocument(sourceBytes: sourceBytes, readerVersion: readerVersion, documentKind: documentKind)
            return value
        }
        // B27.S4.A7 guard: LRU miss and index supplied the positional row
        try await observe("B27.S4.A7", callee: "B26", resultType: "CanonicalComparedStationRow", arguments: .object(["index_entry": .string(String(reflecting: indexEntry)), "station_source_row": .string(String(reflecting: stationSourceRow)), "index_presence": .string(String(reflecting: indexPresence))])) {
            let value: CanonicalComparedStationRow = try Canonical.compareStationSource(indexEntry: indexEntry, stationSourceRow: stationSourceRow, indexPresence: indexPresence)
            return value
        }
        // B29.S4.A4 guard: stream-backed selected station
        try await observe("B29.S4.A4", callee: "B27", resultType: "CanonicalStationSourceRow", arguments: .object(["stream_reader": .string(String(reflecting: streamReader)), "station_id": .string(String(reflecting: stationId)), "release_origin": .string(String(reflecting: releaseOrigin)), "reader_version": .string(String(reflecting: readerVersion))])) {
            let value: CanonicalStationSourceRow = try Canonical.readStationLazily(streamReader: streamReader, stationId: stationId, releaseOrigin: releaseOrigin, readerVersion: readerVersion)
            return value
        }
        // B29.S4.A8 guard: selected station exists
        try await observe("B29.S4.A8", callee: "B07", resultType: "CanonicalTypedModel", arguments: .object(["raw_fields": .string(String(reflecting: rawFields)), "field_contract": .string(String(reflecting: fieldContract)), "origin": .string(String(reflecting: origin)), "model_type": .string(String(reflecting: modelType))])) {
            let value: CanonicalTypedModel = try Canonical.materializeTypedModel(rawFields: rawFields, fieldContract: fieldContract, origin: origin, modelType: modelType)
            return value
        }
        // B34.S1.A1 guard: query entry and each iterator step
        try await observe("B34.S1.A1", callee: "B15", resultType: "CanonicalResourceStateOrError", arguments: .object(["resource_state": .string(String(reflecting: resourceState)), "lifetime_action": .string(String(reflecting: lifetimeAction))])) {
            let value: CanonicalResourceStateOrError = try Canonical.enforceResourceLifetime(resourceState: resourceState, lifetimeAction: lifetimeAction)
            return value
        }
        // B34.S2.A4 guard: direct constant-set candidate
        try await observe("B34.S2.A4", callee: "B30", resultType: "CanonicalEffectiveRecommendation", arguments: .object(["station_sets": .string(String(reflecting: stationSets)), "original_recommendation": .string(String(reflecting: originalRecommendation)), "commercial_only": .string(String(reflecting: commercialOnly))])) {
            let value: CanonicalEffectiveRecommendation = try Canonical.selectEffectiveRecommendation(stationSets: stationSets, originalRecommendation: originalRecommendation, commercialOnly: commercialOnly)
            return value
        }
        // B34.S2.A6 guard: candidate uses offsets
        try await observe("B34.S2.A6", callee: "B33", resultType: "CanonicalSelectedReferencePath", arguments: .object(["station_source_row": .string(String(reflecting: stationSourceRow)), "path_request": .string(String(reflecting: pathRequest)), "release_view": .string(String(reflecting: releaseView))])) {
            let value: CanonicalSelectedReferencePath = try Canonical.resolveReferencePath(stationSourceRow: stationSourceRow, pathRequest: pathRequest, releaseView: releaseView)
            return value
        }
        // B34.S3.A3 guard: a direct candidate with effective recommendation or a resolved offset candidate exists
        try await observe("B34.S3.A3", callee: "B31", resultType: "CanonicalQualityAdmission", arguments: .object(["candidate_path": .string(String(reflecting: candidatePath)), "include_flagged": .string(String(reflecting: includeFlagged)), "include_fallback": .string(String(reflecting: includeFallback))])) {
            let value: CanonicalQualityAdmission = try Canonical.admitQualityPath(candidatePath: candidatePath, includeFlagged: includeFlagged, includeFallback: includeFallback)
            return value
        }
        // B34.S3.A4 guard: quality admission passed
        try await observe("B34.S3.A4", callee: "B32", resultType: "CanonicalCommercialAdmission", arguments: .object(["candidate_path": .string(String(reflecting: candidatePath)), "commercial_only": .string(String(reflecting: commercialOnly)), "commercial_basis": .string(String(reflecting: commercialBasis))])) {
            let value: CanonicalCommercialAdmission = try Canonical.admitCommercialPath(candidatePath: candidatePath, commercialOnly: commercialOnly, commercialBasis: commercialBasis)
            return value
        }
        // B34.S3.A8 guard: candidate path is historical and earlier gates pass
        try await observe("B34.S3.A8", callee: "B36", resultType: "CanonicalHistoricalAdmission", arguments: .object(["own_offset": .string(String(reflecting: ownOffset)), "reference_path": .string(String(reflecting: referencePath)), "historical_policy": .string(String(reflecting: historicalPolicy)), "selection_kind": .string(String(reflecting: selectionKind)), "reader_version": .string(String(reflecting: readerVersion))])) {
            let value: CanonicalHistoricalAdmission = try Canonical.admitHistoricalOffset(ownOffset: ownOffset, referencePath: referencePath, historicalPolicy: historicalPolicy, selectionKind: selectionKind, readerVersion: readerVersion)
            return value
        }
        // B35.S1.A1 guard: summary_kind = stats
        try await observe("B35.S1.A1", callee: "B35.stats", resultType: "CanonicalReleaseStatistics", arguments: .object(["release_view": .string(String(reflecting: releaseView))])) {
            let value: CanonicalReleaseStatistics = try Canonical.countReleaseStatistics(releaseView: releaseView)
            return value
        }
        // B35.S1.A2 guard: summary_kind = constant_sets
        try await observe("B35.S1.A2", callee: "B35.sets", resultType: "CanonicalOrderedConstantSets", arguments: .object(["station_sets": .string(String(reflecting: stationSets)), "original_recommendation": .string(String(reflecting: originalRecommendation)), "commercial_only": .string(String(reflecting: commercialOnly)), "include_no_constants": .string(String(reflecting: includeNoConstants))])) {
            let value: CanonicalOrderedConstantSets = try Canonical.orderConstantSets(stationSets: stationSets, originalRecommendation: originalRecommendation, commercialOnly: commercialOnly, includeNoConstants: includeNoConstants)
            return value
        }
        // B36.S7.A2 guard: own-offset and policy gates pass
        try await observe("B36.S7.A2", callee: "B40", resultType: "CanonicalSelectedPredictionModel", arguments: .object(["station_request": .string(String(reflecting: stationRequest)), "release_view": .string(String(reflecting: releaseView)), "selection_options": .string(String(reflecting: selectionOptions)), "reader_version": .string(String(reflecting: readerVersion))])) {
            let value: CanonicalSelectedPredictionModel = try Canonical.selectPredictionModel(stationRequest: stationRequest, releaseView: releaseView, selectionOptions: selectionOptions, readerVersion: readerVersion)
            return value
        }
        // B37.S1.A2 guard: Station argument supplied
        try await observe("B37.S1.A2", callee: "B08.origin", resultType: "CanonicalValidStation", arguments: .object(["station": .string(String(reflecting: station)), "release_origin": .string(String(reflecting: releaseOrigin))])) {
            let value: CanonicalValidStation = try Canonical.checkStationOrigin(station: station, releaseOrigin: releaseOrigin)
            return value
        }
        // B37.S2.A3 guard: commercial direct-source attribution
        try await observe("B37.S2.A3", callee: "B30", resultType: "CanonicalEffectiveRecommendation", arguments: .object(["station_sets": .string(String(reflecting: stationSets)), "original_recommendation": .string(String(reflecting: originalRecommendation)), "commercial_only": .string(String(reflecting: commercialOnly))])) {
            let value: CanonicalEffectiveRecommendation = try Canonical.selectEffectiveRecommendation(stationSets: stationSets, originalRecommendation: originalRecommendation, commercialOnly: commercialOnly)
            return value
        }
        // B37.S2.A5 guard: commercial approved offset-source attribution
        try await observe("B37.S2.A5", callee: "B33", resultType: "CanonicalSelectedReferencePath", arguments: .object(["station_source_row": .string(String(reflecting: stationSourceRow)), "path_request": .string(String(reflecting: pathRequest)), "release_view": .string(String(reflecting: releaseView))])) {
            let value: CanonicalSelectedReferencePath = try Canonical.resolveReferencePath(stationSourceRow: stationSourceRow, pathRequest: pathRequest, releaseView: releaseView)
            return value
        }
        // B40.S1.A2 guard: Station object supplied
        try await observe("B40.S1.A2", callee: "B08.origin", resultType: "CanonicalValidStation", arguments: .object(["station": .string(String(reflecting: station)), "release_origin": .string(String(reflecting: releaseOrigin))])) {
            let value: CanonicalValidStation = try Canonical.checkStationOrigin(station: station, releaseOrigin: releaseOrigin)
            return value
        }
        // B40.S1.A3 guard: station ID supplied
        try await observe("B40.S1.A3", callee: "B29", resultType: "CanonicalStationOrTombstoneOrNull", arguments: .object(["release_view": .string(String(reflecting: releaseView)), "identity_query": .string(String(reflecting: identityQuery)), "reader_version": .string(String(reflecting: readerVersion))])) {
            let value: CanonicalStationOrTombstoneOrNull = try Canonical.lookupStationIdentity(releaseView: releaseView, identityQuery: identityQuery, readerVersion: readerVersion)
            return value
        }
        // B40.S2.A4 guard: no explicit set selected
        try await observe("B40.S2.A4", callee: "B30", resultType: "CanonicalEffectiveRecommendation", arguments: .object(["station_sets": .string(String(reflecting: stationSets)), "original_recommendation": .string(String(reflecting: originalRecommendation)), "commercial_only": .string(String(reflecting: commercialOnly))])) {
            let value: CanonicalEffectiveRecommendation = try Canonical.selectEffectiveRecommendation(stationSets: stationSets, originalRecommendation: originalRecommendation, commercialOnly: commercialOnly)
            return value
        }
        // B42.S1.A2 guard: for each instant; never for an empty input
        try await observe("B42.S1.A2", callee: "B41", resultType: "CanonicalAstronomicalTerms", arguments: .object(["selected_prediction_model": .string(String(reflecting: selectedPredictionModel)), "utc_instant": .string(String(reflecting: utcInstant))])) {
            let value: CanonicalAstronomicalTerms = try Canonical.evaluateAstronomy(selectedPredictionModel: selectedPredictionModel, utcInstant: utcInstant)
            return value
        }
        // B43.S1.A1 guard: always after model/window checks
        try await observe("B43.S1.A1", callee: "B43.roots", resultType: "CanonicalUnroundedTideEvents", arguments: .object(["selected_prediction_model": .string(String(reflecting: selectedPredictionModel)), "prediction_window": .string(String(reflecting: predictionWindow))])) {
            let value: CanonicalUnroundedTideEvents = try Canonical.findUnroundedTideEvents(selectedPredictionModel: selectedPredictionModel, predictionWindow: predictionWindow)
            return value
        }
        // B44.S1.A1 guard: current_operation = current_events
        try await observe("B44.S1.A1", callee: "B44.roots", resultType: "CanonicalUnroundedCurrentEvents", arguments: .object(["selected_prediction_model": .string(String(reflecting: selectedPredictionModel)), "prediction_window": .string(String(reflecting: predictionWindow)), "current_request": .string(String(reflecting: currentRequest))])) {
            let value: CanonicalUnroundedCurrentEvents = try Canonical.findUnroundedCurrentEvents(selectedPredictionModel: selectedPredictionModel, predictionWindow: predictionWindow, currentRequest: currentRequest)
            return value
        }
        // B45.S2.A3 guard: historical own offset
        try await observe("B45.S2.A3", callee: "B36", resultType: "CanonicalHistoricalAdmission", arguments: .object(["own_offset": .string(String(reflecting: ownOffset)), "reference_path": .string(String(reflecting: referencePath)), "historical_policy": .string(String(reflecting: historicalPolicy)), "selection_kind": .string(String(reflecting: selectionKind)), "reader_version": .string(String(reflecting: readerVersion))])) {
            let value: CanonicalHistoricalAdmission = try Canonical.admitHistoricalOffset(ownOffset: ownOffset, referencePath: referencePath, historicalPolicy: historicalPolicy, selectionKind: selectionKind, readerVersion: readerVersion)
            return value
        }
        // B45.S3.A2 guard: reference exists and admission passes
        try await observe("B45.S3.A2", callee: "B40", resultType: "CanonicalSelectedPredictionModel", arguments: .object(["station_request": .string(String(reflecting: stationRequest)), "release_view": .string(String(reflecting: releaseView)), "selection_options": .string(String(reflecting: selectionOptions)), "reader_version": .string(String(reflecting: readerVersion))])) {
            let value: CanonicalSelectedPredictionModel = try Canonical.selectPredictionModel(stationRequest: stationRequest, releaseView: releaseView, selectionOptions: selectionOptions, readerVersion: readerVersion)
            return value
        }
        // B45.S6.A2 guard: extrema request after reference science, datum and ratio guards pass
        try await observe("B45.S6.A2", callee: "B43.roots", resultType: "CanonicalUnroundedTideEvents", arguments: .object(["selected_prediction_model": .string(String(reflecting: selectedPredictionModel)), "prediction_window": .string(String(reflecting: predictionWindow))])) {
            let value: CanonicalUnroundedTideEvents = try Canonical.findUnroundedTideEvents(selectedPredictionModel: selectedPredictionModel, predictionWindow: predictionWindow)
            return value
        }
        // B45.S7.A3 guard: exact equal offsets and a full-curve request
        try await observe("B45.S7.A3", callee: "B46", resultType: "CanonicalFoldedHeightValues", arguments: .object(["own_offset": .string(String(reflecting: ownOffset)), "reference_model": .string(String(reflecting: referenceModel)), "prediction_instants": .string(String(reflecting: predictionInstants)), "requested_datum": .string(String(reflecting: requestedDatum))])) {
            let value: CanonicalFoldedHeightValues = try Canonical.foldEqualTideOffset(ownOffset: ownOffset, referenceModel: referenceModel, predictionInstants: predictionInstants, requestedDatum: requestedDatum)
            return value
        }
        // B46.S3.A2 guard: folded model and valid target instants
        try await observe("B46.S3.A2", callee: "B42", resultType: "CanonicalHeightValues", arguments: .object(["selected_prediction_model": .string(String(reflecting: selectedPredictionModel)), "prediction_instants": .string(String(reflecting: predictionInstants)), "requested_datum": .string(String(reflecting: requestedDatum))])) {
            let value: CanonicalHeightValues = try Canonical.evaluateHarmonicHeight(selectedPredictionModel: selectedPredictionModel, predictionInstants: predictionInstants, requestedDatum: requestedDatum)
            return value
        }
        // B47.S2.A2 guard: actual reference entry exists
        try await observe("B47.S2.A2", callee: "B40", resultType: "CanonicalSelectedPredictionModel", arguments: .object(["station_request": .string(String(reflecting: stationRequest)), "release_view": .string(String(reflecting: releaseView)), "selection_options": .string(String(reflecting: selectionOptions)), "reader_version": .string(String(reflecting: readerVersion))])) {
            let value: CanonicalSelectedPredictionModel = try Canonical.selectPredictionModel(stationRequest: stationRequest, releaseView: releaseView, selectionOptions: selectionOptions, readerVersion: readerVersion)
            return value
        }
        // B47.S4.A3 guard: current-offset event request after reference science passes
        try await observe("B47.S4.A3", callee: "B44.roots", resultType: "CanonicalUnroundedCurrentEvents", arguments: .object(["selected_prediction_model": .string(String(reflecting: selectedPredictionModel)), "prediction_window": .string(String(reflecting: predictionWindow)), "current_request": .string(String(reflecting: currentRequest))])) {
            let value: CanonicalUnroundedCurrentEvents = try Canonical.findUnroundedCurrentEvents(selectedPredictionModel: selectedPredictionModel, predictionWindow: predictionWindow, currentRequest: currentRequest)
            return value
        }
        // B48.S1.A1 guard: auxiliary_kind = model_access
        try await observe("B48.S1.A1", callee: "B48.aux", resultType: "CanonicalAuxiliaryModelValue", arguments: .object(["auxiliary_operation": .string(String(reflecting: auxiliaryOperation)), "source_values": .string(String(reflecting: sourceValues)), "selection_options": .string(String(reflecting: selectionOptions)), "reader_version": .string(String(reflecting: readerVersion)), "auxiliary_member_id": .string(String(reflecting: auxiliaryMemberId))])) {
            let value: CanonicalAuxiliaryModelValue = try Canonical.readAuxiliaryModelValue(auxiliaryOperation: auxiliaryOperation, sourceValues: sourceValues, selectionOptions: selectionOptions, readerVersion: readerVersion, auxiliaryMemberId: auxiliaryMemberId)
            return value
        }
        // B48.S1.A2 guard: auxiliary_kind = result_context
        try await observe("B48.S1.A2", callee: "B48.context", resultType: "CanonicalPredictionResult", arguments: .object(["result_values": .string(String(reflecting: resultValues)), "result_context": .string(String(reflecting: resultContext))])) {
            let value: CanonicalPredictionResult = try Canonical.constructPredictionResult(resultValues: resultValues, resultContext: resultContext)
            return value
        }
        // B48.S1.A3 guard: auxiliary_kind = local_time
        try await observe("B48.S1.A3", callee: "B48.local", resultType: "CanonicalLocalTimeResult", arguments: .object(["utc_result": .string(String(reflecting: utcResult)), "local_time_profile": .string(String(reflecting: localTimeProfile))])) {
            let value: CanonicalLocalTimeResult = try Canonical.convertResultToLocalTime(utcResult: utcResult, localTimeProfile: localTimeProfile)
            return value
        }
        // B35.sets.S1.A1 guard: always
        try await observe("B35.sets.S1.A1", callee: "B30", resultType: "CanonicalEffectiveRecommendation", arguments: .object(["station_sets": .string(String(reflecting: stationSets)), "original_recommendation": .string(String(reflecting: originalRecommendation)), "commercial_only": .string(String(reflecting: commercialOnly))])) {
            let value: CanonicalEffectiveRecommendation = try Canonical.selectEffectiveRecommendation(stationSets: stationSets, originalRecommendation: originalRecommendation, commercialOnly: commercialOnly)
            return value
        }
        // B48.aux.S2.A1 guard: copied auxiliary contract requires model selection
        try await observe("B48.aux.S2.A1", callee: "B40", resultType: "CanonicalSelectedPredictionModel", arguments: .object(["station_request": .string(String(reflecting: stationRequest)), "release_view": .string(String(reflecting: releaseView)), "selection_options": .string(String(reflecting: selectionOptions)), "reader_version": .string(String(reflecting: readerVersion))])) {
            let value: CanonicalSelectedPredictionModel = try Canonical.selectPredictionModel(stationRequest: stationRequest, releaseView: releaseView, selectionOptions: selectionOptions, readerVersion: readerVersion)
            return value
        }
        // B48.aux.S2.A2 guard: auxiliary_operation requires astronomy and successful model selection
        try await observe("B48.aux.S2.A2", callee: "B41", resultType: "CanonicalAstronomicalTerms", arguments: .object(["selected_prediction_model": .string(String(reflecting: selectedPredictionModel)), "utc_instant": .string(String(reflecting: utcInstant))])) {
            let value: CanonicalAstronomicalTerms = try Canonical.evaluateAstronomy(selectedPredictionModel: selectedPredictionModel, utcInstant: utcInstant)
            return value
        }
        // B43.roots.S1.A2 guard: for each grid or root-search evaluation instant
        try await observe("B43.roots.S1.A2", callee: "B41", resultType: "CanonicalAstronomicalTerms", arguments: .object(["selected_prediction_model": .string(String(reflecting: selectedPredictionModel)), "utc_instant": .string(String(reflecting: utcInstant))])) {
            let value: CanonicalAstronomicalTerms = try Canonical.evaluateAstronomy(selectedPredictionModel: selectedPredictionModel, utcInstant: utcInstant)
            return value
        }
        // B44.roots.S2.A2 guard: for each current evaluation instant
        try await observe("B44.roots.S2.A2", callee: "B41", resultType: "CanonicalAstronomicalTerms", arguments: .object(["selected_prediction_model": .string(String(reflecting: selectedPredictionModel)), "utc_instant": .string(String(reflecting: utcInstant))])) {
            let value: CanonicalAstronomicalTerms = try Canonical.evaluateAstronomy(selectedPredictionModel: selectedPredictionModel, utcInstant: utcInstant)
            return value
        }
        // B17.sidecar.S1.A3 guard: descriptor has no usable local checksum bytes and online acquisition is permitted
        try await observe("B17.sidecar.S1.A3", callee: "B23.http", resultType: "CanonicalHttpResponse", arguments: .object(["http_request": .string(String(reflecting: httpRequest)), "transport_options": .string(String(reflecting: transportOptions))])) {
            let value: CanonicalHttpResponse = try await Canonical.requestHttpResource(httpRequest: httpRequest, transportOptions: transportOptions)
            return value
        }
    }

    private func observe<Result>(_ id: String, callee: String, resultType: String, arguments: JSONValue,
        _ call: () async throws -> Result) async throws {
        do {
            _ = try await call()
            XCTFail("\(id): incomplete body fabricated a successful value")
        } catch CanonicalUnimplemented.behavior(let actual) {
            XCTAssertEqual(actual, callee)
            let evidence: JSONValue = .object(["id": .string(id), "callee": .string(actual), "arguments": arguments,
                "result_type": .string(resultType), "refusal": .string("CanonicalUnimplemented.behavior(\"\(actual)\")"),
                "result_presence": .string("absent"), "error_presence": .string("absent")])
            print("SW_SHAPE " + String(decoding: try evidence.data(), as: UTF8.self))
            try observationFile?.write(contentsOf: try evidence.data() + Data([10]))
        }
    }
}
