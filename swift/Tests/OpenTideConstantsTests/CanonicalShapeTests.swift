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
        let memberContract: CanonicalMemberContract = CanonicalMemberContract(member: .ClientOpen)
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
        let rawFields: CanonicalRawFields = .sourceJSON(.object([:]))
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
        let predictionWindow: CanonicalPredictionWindow = CanonicalPredictionWindow.span(start: 1.0, stop: 1.0, step: nil)
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
        let migrated = Set(["B01", "B02", "B03", "B04", "B07", "B08.raw", "B24", "B28", "B39", "B41", "B42", "B43.roots", "B44.roots"])
        do {
            _ = try await call()
            if !migrated.contains(callee) { XCTFail("\(id): incomplete body fabricated a successful value") }
        } catch CanonicalUnimplemented.behavior(let actual) {
            XCTAssertEqual(actual, callee)
            let evidence: JSONValue = .object(["id": .string(id), "callee": .string(actual), "arguments": arguments,
                "result_type": .string(resultType), "refusal": .string("CanonicalUnimplemented.behavior(\"\(actual)\")"),
                "result_presence": .string("absent"), "error_presence": .string("absent")])
            print("SW_SHAPE " + String(decoding: try evidence.data(), as: UTF8.self))
            try observationFile?.write(contentsOf: try evidence.data() + Data([10]))
        } catch let error as OpenTideConstantsError {
            // Inert construction inputs are only a type gate for migrated entries.
            // Real M1 value/error assertions use authenticated corpus receivers below.
            if !migrated.contains(callee) { throw error }
        }
    }
}

// M1 uses authenticated corpus inputs and already-working native references.
// Optional receiver fields are representation setup; bodies still refuse at RED.
extension CanonicalShapeTests {
    func testM1StationStageCustody() throws {
        let release = try m1Release("conformance/fixtures/good/OTC_20991231.2.json")
        let foreignRelease = try m1Release("conformance/fixtures/good/OTC_20991231.2.json")
        defer { release.close(); foreignRelease.close() }
        let foreign = try foreignRelease.requireStation(stationId: "OTC-T-0001")
        let owned = try release.requireStation(stationId: foreign.stationId)
        XCTAssertEqual(owned.raw, foreign.raw); XCTAssertNotEqual(owned.originToken, foreign.originToken)
        let start = try XCTUnwrap(parseTime("2099-01-01T00:00:00Z")), stop = start.addingTimeInterval(600)
        let controls: [(CanonicalMemberID, CanonicalOperation, CanonicalArguments, OpenTideConstantsError)] = [
            (.ReleaseHeights, .heights, .ReleaseHeights(CanonicalReleaseHeightsArguments(station: .object(foreign), start: start, stop: stop,
                stepS: 600, datum: nil, setId: nil, offsetId: nil)), try m1NativeError("invalid_argument") { try release.heights(station: foreign, start: start, stop: stop) }),
            (.ReleaseExtremes, .extremes, .ReleaseExtremes(CanonicalReleaseExtremesArguments(station: .object(foreign), start: start, stop: stop,
                datum: nil, setId: nil, offsetId: nil)), try m1NativeError("invalid_argument") { try release.extremes(station: foreign, start: start, stop: stop) }),
            (.ReleaseCurrents, .currents, .ReleaseCurrents(CanonicalReleaseCurrentsArguments(station: .object(foreign), start: start, stop: stop,
                stepS: 600, binNumber: nil, setId: nil)), try m1NativeError("invalid_argument") { try release.currents(station: foreign, start: start, stop: stop) })
        ]
        print("M1_SW_CUSTODY classification=CONSTRUCTION_REFINEMENT; genuine preparation replaces the prior explicitly injected custody fault control; no upstream defect or static-to-runtime flip claim")
        for (member, operation, arguments, expected) in controls {
            let stage = try CanonicalStationArgumentStage.prepare(member: member, release: release, request: .object(foreign))
            try m1Record("B01", fixture: "private custody fault control with real same-ID foreign Station " + member.rawValue, call: {
                try m1NativeError(expected.code) {
                    try Canonical.validateOperationArguments(operation: operation, arguments: arguments,
                        memberContract: CanonicalMemberContract(member: member, receiver: .release(release), stationStage: stage))
                }
            }, check: { XCTAssertEqual($0.message, expected.message); XCTAssertEqual($0.fields, expected.fields) })
        }
    }

    func testM1CurrentProjectionAndCacheShapes() throws {
        let jsonl = m1Root.appendingPathComponent("conformance/fixtures/predict/OTC_20991231.7.jsonl")
        XCTAssertEqual(try SHA256.file(jsonl), "3abcb5e7568b7dd77e522e66f642ea3fa9920687d6fa1d813992a36fad288c02")
        let nativeRelease = try m1Release("conformance/fixtures/predict/OTC_20991231.7.json")
        defer { nativeRelease.close() }
        var summaries: [JSONValue] = [], projections: [CanonicalStreamIndexStation] = []
        var branches: [String: Int] = [:]
        try eachLine(jsonl) { bytes, offset in
            let source = try JSONValue.parse(bytes)
            let native = IndexEntry.make(source, offset: offset, length: bytes.count)
            let span = CanonicalSourceByteSpan(offsetBytes: Int64(offset), lengthBytes: Int64(bytes.count))
            let projected = try Canonical.projectStationIndex(stationSourceRow: source, sourceByteSpan: span,
                projectionContract: CanonicalProjectionRules(scalarMembers: [.StationStationId, .StationAliases, .StationRaw],
                    modelType: .Station, preserveUnknownSourceFields: true))
            summaries.append(native.summary); projections.append(projected)
            if !source["current_offsets"].array.isEmpty { branches["current_offsets", default: 0] += 1 }
            if source["constant_sets"].array.contains(where: { !$0["current_bins"].array.isEmpty }) { branches["current_bins", default: 0] += 1 }
            if !source["subordinate_offsets"].isNull { branches["subordinate_offsets", default: 0] += 1 }
            if !source["aliases"].object.isEmpty { branches["aliases", default: 0] += 1 }
            try m1Record("B24", fixture: "actual source stream row including current projections " + native.id, call: { projected }, check: {
                XCTAssertEqual($0.stationId, native.id); XCTAssertEqual($0.status, native.status)
                XCTAssertEqual($0.offset, span.offsetBytes); XCTAssertEqual($0.length, span.lengthBytes)
            })
        }
        let digest = try SHA256.file(jsonl), size = Int64(try Data(contentsOf: jsonl).count)
        let actual = CanonicalStreamIndex(indexVersion: 1, discoveryIndexVersion: 1, datestamp: nativeRelease.datestamp,
            jsonl: jsonl.lastPathComponent, jsonlSha256: digest, jsonlSize: size, by: "opentideconstants-swift/0.1.0", stations: projections)
        let native: JSONValue = .object(["index_version": .integer(1), "discovery_index_version": .integer(1),
            "datestamp": .string(nativeRelease.datestamp), "jsonl": .string(jsonl.lastPathComponent), "jsonl_sha256": .string(digest),
            "jsonl_size": .integer(size), "by": .string("opentideconstants-swift/0.1.0"), "stations": .array(summaries)])
        try m1Record("B28", fixture: "exact original native writer index including current bins/offsets/raw subordinate fields", call: {
            try Canonical.encodeCacheJson(cacheDocument: .streamIndex(actual))
        }, check: {
            let expected = try encode_cache_json(native)
            XCTAssertEqual($0, expected)
            guard $0 == expected else { throw NSError(domain: "M1NativeCurrentIndexMismatch", code: 1) }
        })
        print("M1_SW_PROJECTION_BRANCHES \(branches)")
        XCTAssertGreaterThan(branches["current_offsets", default: 0], 0)
        XCTAssertGreaterThan(branches["current_bins", default: 0], 0)
        let source = try XCTUnwrap(summaries.first)
        let id = try XCTUnwrap(source["station_id"].string)
        let row = try nativeRelease.requireStation(stationId: id).raw
        for span in [CanonicalSourceByteSpan(offsetBytes: -1, lengthBytes: 1)] {
            XCTAssertThrowsError(try Canonical.projectStationIndex(stationSourceRow: row, sourceByteSpan: span,
                projectionContract: CanonicalProjectionRules(scalarMembers: [], modelType: .Station, preserveUnknownSourceFields: true))) {
                XCTAssertEqual(($0 as? OpenTideConstantsError)?.code, "invalid_release")
                XCTAssertEqual(($0 as? OpenTideConstantsError)?.message, "stale index span")
            }
        }
    }

    func testM1LifecycleAndPredictionOrder() async throws {
        let client = try await OpenTideConstants.open(file:
            "/Users/jpr5/.local/share/copilotkit/cr/otc-codex-takeover/execution/sdk-core-sync/canonical-behavior/holistic-reset/implementation-plan/M1-SW/public-fixtures/OTC_20261011.json")
        let release = client.release
        let foreignRelease = try m1Release("conformance/vectors/1.0/vectors-release.json")
        defer { client.close(); foreignRelease.close() }
        let foreign = try foreignRelease.requireStation(stationId: "OTC-V-NOAA-1820000")
        let owned = try release.requireStation(stationId: foreign.stationId)
        let valid = try XCTUnwrap(parseTime("2025-01-01T00:00:00Z"))
        for download in [
            CanonicalClientDownloadArguments(release: "bad", to: "unused", formats: [.jsonl], overwrite: false),
            CanonicalClientDownloadArguments(release: "latest", to: "", formats: [.jsonl], overwrite: false),
            CanonicalClientDownloadArguments(release: "latest", to: "unused", formats: [], overwrite: false),
            CanonicalClientDownloadArguments(release: "latest", to: "unused", formats: [.other], overwrite: false)
        ] {
            let native: OpenTideConstantsError
            do { _ = try await client.download(release: download.release, to: download.to, formats: download.formats); throw NSError(domain: "M1ExpectedNativeDownloadGuard", code: 1) }
            catch let error as OpenTideConstantsError { native = error }
            try m1Record("B01", fixture: "individual native live download primitive", call: {
                try m1NativeError(native.code) { try Canonical.validateOperationArguments(operation: .download, arguments: .ClientDownload(download),
                    memberContract: CanonicalMemberContract(member: .ClientDownload, receiver: .client(client))) }
            }, check: { XCTAssertEqual($0.message, native.message); XCTAssertEqual($0.fields, native.fields) })
        }
        for request in [CanonicalStationRequest.object(foreign), .id("absent")] {
            let stage = try m1StationStage(.ReleaseCurrents, release: release, request: request)
            guard case .failed(let expected) = stage.outcome else { return XCTFail("Expected genuine owner/resolution failure") }
            let arguments = CanonicalReleaseCurrentsArguments(station: request, start: valid, stop: valid.addingTimeInterval(600),
                stepS: 600, binNumber: 0, setId: nil)
            let native: OpenTideConstantsError
            switch request {
            case .object(let supplied): native = try m1NativeError(expected.code) { try release.currents(station: supplied, start: valid, stop: valid.addingTimeInterval(600), binNumber: 0) }
            case .id(let id): native = try m1NativeError(expected.code) { try release.currents(stationId: id, start: valid, stop: valid.addingTimeInterval(600), binNumber: 0) }
            }
            try m1Record("B01", fixture: "authentic request resolution/owner failure before invalid bin", call: {
                try m1NativeError(native.code) { try Canonical.validateOperationArguments(operation: .currents, arguments: .ReleaseCurrents(arguments),
                    memberContract: CanonicalMemberContract(member: .ReleaseCurrents, receiver: .release(release), stationStage: stage)) }
            }, check: { XCTAssertEqual($0.message, native.message); XCTAssertEqual($0.fields, native.fields) })
            let invalid = CanonicalReleaseCurrentsArguments(station: request, start: Date(timeIntervalSince1970: .nan), stop: valid,
                stepS: 0, binNumber: 0, setId: nil)
            let dateError = try m1NativeError("invalid_argument") { try Predict.window(invalid.start, invalid.stop, stepS: invalid.stepS) }
            try m1Record("B01", fixture: "native invalid window before prepared later owner error", call: {
                try m1NativeError(dateError.code) { try Canonical.validateOperationArguments(operation: .currents, arguments: .ReleaseCurrents(invalid),
                    memberContract: CanonicalMemberContract(member: .ReleaseCurrents, receiver: .release(release), stationStage: stage)) }
            }, check: { XCTAssertEqual($0.message, dateError.message); XCTAssertEqual($0.fields, dateError.fields) })
        }
        for bin: Int64 in [0, -1, 9007199254740992] {
            let native = try m1NativeError("invalid_argument") { try release.currents(station: owned, start: valid, stop: valid.addingTimeInterval(600), binNumber: bin) }
            let request = CanonicalReleaseCurrentsArguments(station: .object(owned), start: valid, stop: valid.addingTimeInterval(600), stepS: 600, binNumber: bin, setId: nil)
            let stage = try m1StationStage(.ReleaseCurrents, release: release, request: request.station)
            try m1Record("B01", fixture: "native bin bounds after resolved authentic owner " + String(bin), call: {
                try m1NativeError(native.code) { try Canonical.validateOperationArguments(operation: .currents, arguments: .ReleaseCurrents(request),
                    memberContract: CanonicalMemberContract(member: .ReleaseCurrents, receiver: .release(release), stationStage: stage)) }
            }, check: { XCTAssertEqual($0.message, native.message); XCTAssertEqual($0.fields, native.fields) })
        }
        let stage = try m1StationStage(.ReleaseCurrents, release: release, request: .object(owned))
        let request = CanonicalArguments.ReleaseCurrents(CanonicalReleaseCurrentsArguments(station: .object(owned), start: valid,
            stop: valid.addingTimeInterval(600), stepS: 600, binNumber: nil, setId: nil))
        for contract in [CanonicalMemberContract(member: .ReleaseCurrents, receiver: .release(release)),
            CanonicalMemberContract(member: .ReleaseCurrents, receiver: .release(foreignRelease), stationStage: stage)] {
            XCTAssertThrowsError(try Canonical.validateOperationArguments(operation: .currents, arguments: request, memberContract: contract)) {
                XCTAssertEqual($0 as? CanonicalUnimplemented, .behavior("B08.origin/B29"))
            }
        }
        XCTAssertThrowsError(try CanonicalStationArgumentStage.prepare(member: .ClientDownload, release: release, request: .object(owned))) {
            XCTAssertEqual($0 as? CanonicalUnimplemented, .behavior("B08.origin/B29"))
        }
        let differentRequest = CanonicalArguments.ReleaseCurrents(CanonicalReleaseCurrentsArguments(station: .id(owned.stationId),
            start: valid, stop: valid.addingTimeInterval(600), stepS: 600, binNumber: nil, setId: nil))
        XCTAssertThrowsError(try Canonical.validateOperationArguments(operation: .currents, arguments: differentRequest,
            memberContract: CanonicalMemberContract(member: .ReleaseCurrents, receiver: .release(release), stationStage: stage))) {
            XCTAssertEqual($0 as? CanonicalUnimplemented, .behavior("B08.origin/B29"))
        }
        release.close()
        let closed = try m1NativeError("io") { try client.checkOpen() }
        _ = try m1NativeError(closed.code) { try Canonical.validateOperationArguments(operation: .currents, arguments: request,
            memberContract: CanonicalMemberContract(member: .ReleaseCurrents, receiver: .release(release), stationStage: stage)) }
        let requests: [(CanonicalMemberID, CanonicalOperation, CanonicalArguments)] = [
            (.ClientReleases, .releases, .ClientReleases(CanonicalClientReleasesArguments())),
            (.ClientLatest, .latest, .ClientLatest(CanonicalClientLatestArguments())),
            (.ClientCheckForUpdate, .checkForUpdate, .ClientCheckForUpdate(CanonicalClientCheckForUpdateArguments())),
            (.ClientUpdate, .update, .ClientUpdate(CanonicalClientUpdateArguments())),
            (.ClientVerify, .verify, .ClientVerify(CanonicalClientVerifyArguments())),
            (.ClientCachedReleases, .cachedReleases, .ClientCachedReleases(CanonicalClientCachedReleasesArguments()))
        ]
        for (member, operation, arguments) in requests {
            do {
                switch member {
                case .ClientReleases: _ = try await client.releases()
                case .ClientLatest: _ = try await client.latest()
                case .ClientCheckForUpdate: _ = try await client.checkForUpdate()
                case .ClientUpdate: _ = try await client.update()
                case .ClientVerify: _ = try client.verify()
                case .ClientCachedReleases: _ = try client.cachedReleases()
                default: return XCTFail("Unexpected lifecycle fixture")
                }
                XCTFail("Original native closed receiver accepted")
            } catch let native as OpenTideConstantsError {
                XCTAssertEqual(native.code, closed.code); XCTAssertEqual(native.message, closed.message)
                try m1Record("B01", fixture: "original held Release closed with live Client " + member.rawValue, call: {
                    try m1NativeError(native.code) { try Canonical.validateOperationArguments(operation: operation, arguments: arguments,
                        memberContract: CanonicalMemberContract(member: member, receiver: .client(client))) }
                }, check: { XCTAssertEqual($0.message, native.message); XCTAssertEqual($0.fields, native.fields) })
            }
        }
        let stamp = release.datestamp
        XCTAssertEqual(client.release.datestamp, stamp)
        try m1Record("B01", fixture: "original idempotent close has no blanket closed guard", call: {
            try Canonical.validateOperationArguments(operation: .close, arguments: .ClientClose(CanonicalClientCloseArguments()),
                memberContract: CanonicalMemberContract(member: .ClientClose, receiver: .client(client)))
        }, check: { guard case .ClientClose = $0 else { throw NSError(domain: "M1WrongCloseArguments", code: 1) } })
        client.close(); client.close()
        XCTAssertEqual(client.release.datestamp, stamp)
    }

    func testM1RemainingPredictionLeaves() throws {
        let release = try m1Release("conformance/vectors/1.0/vectors-release.json")
        defer { release.close() }
        let station = try release.requireStation(stationId: "OTC-V-NOAA-1820000")
        let context = try Predict.context(release, supplied: station, quantity: .waterLevel, setId: nil, datum: "mean_level")
        let model = m1Model(context, release: release), total = try XCTUnwrap(context.total)
        let lower = context.table.validRange[0], upper = context.table.validRange[1]
        let middle = min(lower + 1, upper)
        let seconds = [yearStart(lower), yearStart(lower) + 1800, yearStart(middle) - 1,
            yearStart(middle), yearStart(upper) + 3600]
        for instant in seconds {
            let year = utcYear(instant), native = try total.yearData(utcYear(instant))
            let expected = native.1.map { term in
                JSONValue.object(["speed": .number(term.speed), "amplitude": .number(term.amplitude),
                    "argument": .number(term.argument), "omega": .number(term.omega)])
            }
            try m1Record("B41", fixture: "exact native astronomy terms/order/UTC epoch year " + String(year), call: {
                try Canonical.evaluateAstronomy(selectedPredictionModel: model, utcInstant: instant)
            }, check: {
                XCTAssertEqual($0.utcYear, year); XCTAssertEqual($0.constituentTerms, expected)
                XCTAssertEqual($0.epochHours, (instant - native.0) / 3600)
            })
        }
        for year in [lower - 1, upper + 1] {
            let native = try m1NativeError("time_out_of_range") { try total.yearData(year) }
            try m1Record("B41", fixture: "native year range refusal " + String(year), call: {
                try m1NativeError(native.code) {
                    try Canonical.evaluateAstronomy(selectedPredictionModel: model, utcInstant: yearStart(year))
                }
            }, check: { XCTAssertEqual($0.message, native.message); XCTAssertEqual($0.fields, native.fields) })
        }
        let unsupported = try m1NativeError("unsupported_constituent") { try context.table.row("not-a-constituent") }
        try m1Record("B41", fixture: "authentic unsupported row stays original native model prerequisite", call: {
            try m1NativeError(unsupported.code) { try HarmonicSum(context.table, [.object(["name": .string("not-a-constituent")])]) }
        }, check: { XCTAssertEqual($0.message, unsupported.message); XCTAssertEqual($0.fields, unsupported.fields) })
        let instants = [yearStart(middle) + 3600, yearStart(middle) - 1, yearStart(middle) + 3600]
        for datum in ["mean_level", "zero", "mllw", "not-a-datum"] {
            do {
                let native = try release.heightsAt(station: station, times: instants.map(Date.init(timeIntervalSince1970:)), datum: datum)
                try m1Record("B42", fixture: "actual native datum/cross-year/duplicate-order " + datum, call: {
                    try Canonical.evaluateHarmonicHeight(selectedPredictionModel: model, predictionInstants: instants, requestedDatum: datum)
                }, check: {
                    XCTAssertEqual($0.items.map(\.time), native.items.map(\.time))
                    XCTAssertEqual($0.items.map(\.heightM), native.items.map(\.heightM))
                })
            } catch let native as OpenTideConstantsError {
                try m1Record("B42", fixture: "native datum refusal " + datum, call: {
                    try m1NativeError(native.code) {
                        try Canonical.evaluateHarmonicHeight(selectedPredictionModel: model, predictionInstants: instants, requestedDatum: datum)
                    }
                }, check: { XCTAssertEqual($0.message, native.message); XCTAssertEqual($0.fields, native.fields) })
            }
        }
        try m1Record("B42", fixture: "actual empty instants no astronomy value lookup", call: {
            try Canonical.evaluateHarmonicHeight(selectedPredictionModel: model, predictionInstants: [], requestedDatum: "mean_level")
        }, check: { XCTAssertTrue($0.items.isEmpty) })
        let event = try m1Vector("OTC-V-NOAA-1820000/extremes/0")
        let start = try m1Date(event["args"]["start"]).timeIntervalSince1970
        let stop = try m1Date(event["args"]["stop"]).timeIntervalSince1970
        let first = try XCTUnwrap(unroundedHarmonicEvents(total, start: start, stop: stop).first)
        let windows = [(start, stop), (yearStart(middle) - 7200, yearStart(middle) + 7200),
            (first.time - 0.5, first.time + 0.5), (yearStart(lower - 1), yearStart(lower - 1))]
        for (a, b) in windows {
            let native = try unroundedHarmonicEvents(total, start: a, stop: b)
            try m1Record("B43.roots", fixture: "exact native unrounded tide roots/order including boundary and NewYear", call: {
                try Canonical.findUnroundedTideEvents(selectedPredictionModel: model, predictionWindow: .span(start: a, stop: b, step: nil))
            }, check: {
                XCTAssertEqual($0.count, native.count)
                for (index, pair) in zip($0, native).enumerated() {
                    XCTAssertEqual(pair.0.rootSeconds, pair.1.time); XCTAssertEqual(pair.0.heightM, pair.1.value)
                    XCTAssertEqual(pair.0.eventType.rawValue, pair.1.kind); XCTAssertEqual(pair.0.referenceOrder, Int64(index))
                }
            })
        }
        let current = try release.requireStation(stationId: "OTC-V-NOAA-ACT1591")
        let currentContext = try Predict.context(release, supplied: current, quantity: .current, setId: nil, binNumber: 1)
        let currentModel = m1Model(currentContext, release: release)
        let currentLower = currentContext.table.validRange[0], currentUpper = currentContext.table.validRange[1]
        let currentMiddle = min(currentLower + 1, currentUpper)
        let currentVector = try m1Vector("OTC-V-NOAA-ACT1591/events/1/0")
        let currentStart = try m1Date(currentVector["args"]["start"]), currentStop = try m1Date(currentVector["args"]["stop"])
        let request = CanonicalCurrentRequest.ReleaseCurrentEvents(CanonicalReleaseCurrentEventsArguments(station: .object(current),
            start: currentStart, stop: currentStop, binNumber: 1, setId: nil))
        XCTAssertEqual(currentModel.referenceBin, 1)
        for (a, b) in [(currentStart.timeIntervalSince1970, currentStop.timeIntervalSince1970),
            (yearStart(currentMiddle) - 7200, yearStart(currentMiddle) + 7200), (yearStart(currentLower - 1), yearStart(currentLower - 1))] {
            let native = try Predict.unroundedCurrentCandidates(currentContext, start: a, stop: b)
            try m1Record("B44.roots", fixture: "exact native signed peaks and zero slacks/order/NewYear", call: {
                try Canonical.findUnroundedCurrentEvents(selectedPredictionModel: currentModel, predictionWindow: .span(start: a, stop: b, step: nil), currentRequest: request)
            }, check: {
                XCTAssertEqual($0.count, native.count)
                for (index, pair) in zip($0, native).enumerated() {
                    XCTAssertEqual(pair.0.rootSeconds, pair.1.time); XCTAssertEqual(pair.0.velocityMS, pair.1.value)
                    XCTAssertEqual(pair.0.directionDeg, pair.1.direction); XCTAssertEqual(pair.0.eventType.rawValue, pair.1.kind)
                    XCTAssertEqual(pair.0.referenceOrder, Int64(index))
                    if pair.1.kind.hasPrefix("slack_") { XCTAssertEqual(pair.0.velocityMS, 0); XCTAssertNil(pair.0.directionDeg) }
                }
            })
        }
        for window in [CanonicalPredictionWindow.span(start: yearStart(upper + 1), stop: yearStart(upper + 1) + 600, step: nil)] {
            guard case .span(let a, let b, _) = window else { return XCTFail("Unexpected fixture shape") }
            let tideError = try m1NativeError("time_out_of_range") { try unroundedHarmonicEvents(total, start: a, stop: b) }
            let currentWindow = CanonicalPredictionWindow.span(start: yearStart(currentUpper + 1), stop: yearStart(currentUpper + 1) + 600, step: nil)
            let currentError = try m1NativeError("time_out_of_range") {
                try Predict.unroundedCurrentCandidates(currentContext, start: yearStart(currentUpper + 1), stop: yearStart(currentUpper + 1) + 600)
            }
            _ = try m1NativeError(tideError.code) { try Canonical.findUnroundedTideEvents(selectedPredictionModel: model, predictionWindow: window) }
            _ = try m1NativeError(currentError.code) { try Canonical.findUnroundedCurrentEvents(selectedPredictionModel: currentModel, predictionWindow: currentWindow, currentRequest: request) }
        }
        XCTAssertThrowsError(try Canonical.findUnroundedTideEvents(selectedPredictionModel: model, predictionWindow: .instants([]))) {
            XCTAssertEqual($0 as? CanonicalUnimplemented, .behavior("B43.roots"))
        }
        XCTAssertThrowsError(try Canonical.findUnroundedCurrentEvents(selectedPredictionModel: currentModel, predictionWindow: .instants([]), currentRequest: request)) {
            XCTAssertEqual($0 as? CanonicalUnimplemented, .behavior("B44.roots"))
        }
    }

    func testM1PrimitiveGuardBranches() throws {
        func open(release: String? = nil, file: String? = nil, offline: Bool? = nil, mode: Mode = .eager,
            baseUrl: String? = nil, timeout: Double? = nil, proxy: String? = nil, caFile: String? = nil,
            userAgent: String? = nil, onNetworkError: OnNetworkError? = nil, updateInterval: Double = 86400,
            commercialBasis: String = "strict", historicalOffsetsPolicy: String = "fallback") -> CanonicalClientOpenArguments {
            CanonicalClientOpenArguments(release: release, file: file, cacheDir: nil, offline: offline, mode: mode,
                baseUrl: baseUrl, timeout: timeout, proxy: proxy, caFile: caFile, userAgent: userAgent, onNetworkError: onNetworkError,
                autoUpdate: false, updateInterval: updateInterval, logger: nil, verifyOnOpen: false, commercialOnly: false,
                commercialBasis: commercialBasis, historicalOffsetsPolicy: historicalOffsetsPolicy)
        }
        let unreadable = m1Root.appendingPathComponent("conformance/fixtures/nonexistent-ca-m1").path
        let openCases: [(String, CanonicalClientOpenArguments)] = [
            ("URL scheme", open(baseUrl: "ftp://example.invalid/")), ("URL host", open(baseUrl: "https:/relative")),
            ("mode sentinel", open(mode: .other)), ("commercial policy", open(commercialBasis: "other")),
            ("historical policy", open(historicalOffsetsPolicy: "other")), ("timeout NaN", open(timeout: .nan)),
            ("timeout infinity", open(timeout: .infinity)), ("timeout lower range", open(timeout: 0.0009)),
            ("timeout upper range", open(timeout: 1000001)), ("update interval NaN", open(updateInterval: .nan)),
            ("update interval infinity", open(updateInterval: .infinity)), ("update interval zero", open(updateInterval: 0)),
            ("update interval negative", open(updateInterval: -1)), ("user agent control", open(userAgent: "a\u{0}b")),
            ("user agent DEL", open(userAgent: "a\u{7f}b")), ("proxy scheme", open(proxy: "https://proxy.invalid/")),
            ("proxy host", open(proxy: "http:/relative")), ("proxy low port", open(proxy: "http://proxy.invalid:0")),
            ("proxy high port", open(proxy: "http://proxy.invalid:65536")), ("network policy sentinel", open(onNetworkError: .other)),
            ("unreadable CA", open(caFile: unreadable)), ("datestamp", open(release: "bad")),
            ("file release", open(release: "20991231.2", file: "actual-file")), ("file offline", open(file: "actual-file", offline: true)),
            ("file error policy", open(file: "actual-file", onNetworkError: .raise)),
            ("combined option before user agent", open(mode: .other, userAgent: "\n")),
            ("combined user agent before proxy", open(proxy: "https://proxy.invalid", userAgent: "\n")),
            ("combined proxy before network policy", open(proxy: "https://proxy.invalid", onNetworkError: .other)),
            ("combined network policy before CA", open(caFile: unreadable, onNetworkError: .other)),
            ("combined CA before datestamp", open(release: "bad", caFile: unreadable)),
            ("combined datestamp before file", open(release: "bad", file: "actual-file", offline: true))
        ]
        for (name, request) in openCases {
            let native: OpenTideConstantsError
            do { _ = try OpenTideConstants.validatedOpenOptions(request, environment: ProcessInfo.processInfo.environment); throw NSError(domain: "M1ExpectedNativeOpenGuard", code: 1) }
            catch let error as OpenTideConstantsError { native = error }
            try m1Record("B01", fixture: "native preacquisition open primitive " + name, call: {
                try m1NativeError(native.code) {
                    try Canonical.validateOperationArguments(operation: .open, arguments: .ClientOpen(request), memberContract: CanonicalMemberContract(member: .ClientOpen))
                }
            }, check: { XCTAssertEqual($0.message, native.message); XCTAssertEqual($0.fields, native.fields) })
        }
        let release = try m1Release("conformance/fixtures/good/OTC_20991231.2.json")
        defer { release.close() }
        for (name, limit, match): (String, Int64?, String?) in [("", nil, nil), (" \n ", nil, nil), ("native", 0, nil), ("native", -1, nil), ("native", nil, "other")] {
            let native = try m1NativeError("invalid_argument") { try release.search(name: name, limit: limit, match: match) }
            let request = CanonicalReleaseSearchArguments(name: name, limit: limit, match: match, country: nil, type: nil,
                kind: nil, source: nil, sourceType: nil, includeFlagged: false, includeFallback: false)
            try m1Record("B01", fixture: "individual native search query/limit/match", call: {
                try m1NativeError(native.code) {
                    try Canonical.validateOperationArguments(operation: .search, arguments: .ReleaseSearch(request),
                        memberContract: CanonicalMemberContract(member: .ReleaseSearch, receiver: .release(release)))
                }
            }, check: { XCTAssertEqual($0.message, native.message); XCTAssertEqual($0.fields, native.fields) })
        }
        let geometry: [(Double, Double, Double, Int64?)] = [(.nan, 0, 1, nil), (.infinity, 0, 1, nil), (91, 0, 1, nil),
            (-91, 0, 1, nil), (0, .nan, 1, nil), (0, .infinity, 1, nil), (0, 181, 1, nil), (0, -181, 1, nil),
            (0, 0, -.infinity, nil), (0, 0, -1, nil), (0, 0, .nan, nil), (0, 0, 1, 0), (0, 0, 1, -1)]
        for (lat, lon, radius, limit) in geometry {
            let native = try m1NativeError("invalid_argument") { try release.near(lat: lat, lon: lon, radiusKm: radius, limit: limit) }
            let request = CanonicalReleaseNearArguments(lat: lat, lon: lon, radiusKm: radius, limit: limit,
                country: nil, type: nil, kind: nil, source: nil, sourceType: nil, includeFlagged: false, includeFallback: false)
            try m1Record("B01", fixture: "individual native near geometry/limit", call: {
                try m1NativeError(native.code) {
                    try Canonical.validateOperationArguments(operation: .near, arguments: .ReleaseNear(request),
                        memberContract: CanonicalMemberContract(member: .ReleaseNear, receiver: .release(release)))
                }
            }, check: { XCTAssertEqual($0.message, native.message); XCTAssertEqual($0.fields, native.fields) })
        }
        for at in [Date(timeIntervalSince1970: .nan), Date(timeIntervalSince1970: .infinity),
            Date(timeIntervalSince1970: -62135596801), Date(timeIntervalSince1970: 253402300800)] {
            let native = try m1NativeError("invalid_argument") { try predictionInstant(at) }
            for (member, operation, arguments) in [
                (CanonicalMemberID.AstroTableEquilibriumArgument, CanonicalOperation.equilibriumArgument,
                    CanonicalArguments.AstroTableEquilibriumArgument(CanonicalAstroTableEquilibriumArgumentArguments(name: "M2", at: at))),
                (.AstroTableNodeFactor, .nodeFactor, .AstroTableNodeFactor(CanonicalAstroTableNodeFactorArguments(name: "M2", at: at)))
            ] {
                try m1Record("B01", fixture: "actual finite/range Astro Date primitive " + member.rawValue, call: {
                    try m1NativeError(native.code) { try Canonical.validateOperationArguments(operation: operation, arguments: arguments, memberContract: CanonicalMemberContract(member: member)) }
                }, check: { XCTAssertEqual($0.message, native.message); XCTAssertEqual($0.fields, native.fields) })
            }
        }
    }

    func testM1WindowErrorPrecedence() throws {
        let release = try m1Release("conformance/fixtures/good/OTC_20991231.2.json")
        defer { release.close() }
        let station = try release.requireStation(stationId: "OTC-T-0001")
        let valid = try XCTUnwrap(parseTime("2099-01-01T00:00:00Z"))
        let pairs = [(Date(timeIntervalSince1970: .nan), valid), (valid, Date(timeIntervalSince1970: .infinity)),
            (valid.addingTimeInterval(600), valid)]
        for (start, stop) in pairs {
            let native = try m1NativeError("invalid_argument") { try release.heights(station: station, start: start, stop: stop) }
            let request = CanonicalArguments.ReleaseHeights(CanonicalReleaseHeightsArguments(station: .object(station),
                start: start, stop: stop, stepS: 600, datum: nil, setId: nil, offsetId: nil))
            try m1Record("B39", fixture: "native window failure precedes absent series cadence " + native.message, call: {
                try m1NativeError(native.code) {
                    try Canonical.parsePredictionWindow(timeInputs: request, windowInputs: request, step: nil,
                        localTimeProfile: CanonicalHeightSeriesToLocalArguments(tz: "station"))
                }
            }, check: {
                XCTAssertEqual($0.message, native.message); XCTAssertEqual($0.fields, native.fields)
                guard $0.message == native.message, $0.fields == native.fields else { throw NSError(domain: "M1NativeWindowOrderMismatch", code: 1) }
            })
        }
    }

    func testM1RemainingValueBranches() throws {
        let good = try m1Release("conformance/fixtures/good/OTC_20991231.2.json")
        let vectors = try m1Release("conformance/vectors/1.0/vectors-release.json")
        defer { good.close(); vectors.close() }
        let station = try good.requireStation(stationId: "OTC-T-0001")
        let origin = try m1Origin(station)
        let nativeMissing = try m1NativeError("station_not_found") { try good.requireStation(stationId: "absent") }
        let nativeForeign = try m1NativeError("invalid_argument") {
            try good.own(vectors.requireStation(stationId: "OTC-V-NOAA-1820000"))
        }
        let missing = CanonicalCanonicalError(code: .stationNotFound, structuredFields: .object(nativeMissing.fields), cause: nativeMissing)
        let foreign = CanonicalCanonicalError(code: .invalidArgument, structuredFields: .object(nativeForeign.fields), cause: nativeForeign)
        for failures in [[missing, foreign], [foreign, missing]] {
            let first = try XCTUnwrap(failures.first)
            try m1Record("B03", fixture: "authentic ordered native causes " + first.code.rawValue, call: {
                try Canonical.selectCanonicalError(operation: .station, orderedFailures: failures, cause: nativeForeign)
            }, check: {
                XCTAssertEqual($0.code, first.code); XCTAssertEqual($0.structuredFields, first.structuredFields)
                XCTAssertEqual(($0.cause as? OpenTideConstantsError)?.message, (first.cause as? OpenTideConstantsError)?.message)
            })
        }
        for fallback: Error? in [nativeForeign, nil] {
            let absentCause = CanonicalCanonicalError(code: missing.code, structuredFields: missing.structuredFields, cause: nil)
            try m1Record("B03", fixture: "authentic absent specific cause with optional fallback", call: {
                try Canonical.selectCanonicalError(operation: .station, orderedFailures: [absentCause, foreign], cause: fallback)
            }, check: { XCTAssertEqual(($0.cause as? OpenTideConstantsError)?.message, (fallback as? OpenTideConstantsError)?.message) })
        }
        XCTAssertThrowsError(try Canonical.selectCanonicalError(operation: .station, orderedFailures: [], cause: nil)) {
            XCTAssertEqual($0 as? CanonicalUnimplemented, .behavior("B03"))
        }
        for spelling in ["1", "true", "yes", "on", " ON \n", "TrUe", "false", "0", "off", "unknown", ""] {
            let environment = ["OPENTIDECONSTANTS_OFFLINE": spelling]
            let expected = OpenTideConstants.effectiveOpenOptions(m1Options(offline: false), environment: environment, platformDefaults: m1Options())
            try m1Record("B02", fixture: "native offline environment spelling " + spelling, call: {
                try Canonical.resolveEffectiveOptions(explicitOptions: m1Options(offline: false), environment: environment, platformDefaults: m1Options())
            }, check: { XCTAssertEqual($0.offline, expected.offline); XCTAssertEqual($0.onNetworkError, expected.onNetworkError) })
        }
        let defaults = CanonicalEffectiveOptions(release: "20991231.2", file: nil, cacheDir: "/native-platform", offline: true,
            mode: .stream, baseUrl: "https://platform.invalid/", timeout: 31, proxy: nil, caFile: "/platform-ca", userAgent: nil,
            onNetworkError: .raise, autoUpdate: true, updateInterval: 3, logger: nil, verifyOnOpen: true,
            commercialOnly: true, commercialBasis: "as_published_upstream", historicalOffsetsPolicy: "exclude")
        for environment in [[:], ["OPENTIDECONSTANTS_CACHE_DIR": "", "OPENTIDECONSTANTS_BASE_URL": "", "SSL_CERT_FILE": ""],
            ["OPENTIDECONSTANTS_CACHE_DIR": "/native-env", "OPENTIDECONSTANTS_BASE_URL": "https://environment.invalid/", "SSL_CERT_FILE": "/env-ca"]] {
            let expected = OpenTideConstants.effectiveOpenOptions(m1Options(), environment: environment, platformDefaults: defaults)
            try m1Record("B02", fixture: "native omitted environment and platform precedence", call: {
                try Canonical.resolveEffectiveOptions(explicitOptions: m1Options(), environment: environment, platformDefaults: defaults)
            }, check: {
                XCTAssertEqual($0.cacheDir, expected.cacheDir); XCTAssertEqual($0.baseUrl, expected.baseUrl)
                XCTAssertEqual($0.timeout, expected.timeout); XCTAssertEqual($0.caFile, expected.caFile)
                XCTAssertEqual($0.mode, .eager); XCTAssertEqual($0.offline, false); XCTAssertEqual($0.autoUpdate, false)
                XCTAssertEqual($0.updateInterval, 86400); XCTAssertEqual($0.verifyOnOpen, false); XCTAssertEqual($0.commercialOnly, false)
            })
        }
        try m1Record("B02", fixture: "explicit native values precede environment and platform defaults", call: {
            try Canonical.resolveEffectiveOptions(explicitOptions: defaults, environment: ["OPENTIDECONSTANTS_CACHE_DIR": "/env",
                "OPENTIDECONSTANTS_BASE_URL": "https://environment.invalid/", "SSL_CERT_FILE": "/env-ca"], platformDefaults: m1Options())
        }, check: {
            XCTAssertEqual($0.cacheDir, defaults.cacheDir); XCTAssertEqual($0.baseUrl, defaults.baseUrl)
            XCTAssertEqual($0.timeout, defaults.timeout); XCTAssertEqual($0.caFile, defaults.caFile)
            XCTAssertEqual($0.mode, defaults.mode); XCTAssertEqual($0.offline, defaults.offline)
            XCTAssertEqual($0.onNetworkError, defaults.onNetworkError); XCTAssertEqual($0.autoUpdate, defaults.autoUpdate)
            XCTAssertEqual($0.updateInterval, defaults.updateInterval); XCTAssertEqual($0.verifyOnOpen, defaults.verifyOnOpen)
            XCTAssertEqual($0.commercialOnly, defaults.commercialOnly); XCTAssertEqual($0.commercialBasis, defaults.commercialBasis)
            XCTAssertEqual($0.historicalOffsetsPolicy, defaults.historicalOffsetsPolicy)
        })
        try m1Record("B04", fixture: "present nonnull native Station value retains origin", call: {
            try Canonical.translateNativeBinding(canonicalResult: .ReleaseStation(station), canonicalError: nil, nativeProfile: .swift)
        }, check: {
            guard case .ReleaseStation(let actual) = $0 else { throw CanonicalUnimplemented.behavior("wrong member") }
            XCTAssertEqual(actual?.raw, station.raw); XCTAssertEqual(actual?.originToken, station.originToken)
        })
        XCTAssertThrowsError(try Canonical.translateNativeBinding(canonicalResult: nil, canonicalError: nil, nativeProfile: .swift)) {
            XCTAssertEqual($0 as? CanonicalUnimplemented, .behavior("B04"))
        }
        for profile in CanonicalNativeProfile.allCases where profile != .swift {
            XCTAssertThrowsError(try Canonical.translateNativeBinding(canonicalResult: .ReleaseStation(station), canonicalError: nil, nativeProfile: profile)) {
                XCTAssertEqual($0 as? CanonicalUnimplemented, .behavior("B04"))
            }
        }
        let noCause = CanonicalCanonicalError(code: .stationNotFound, structuredFields: .object(nativeMissing.fields), cause: nil)
        XCTAssertThrowsError(try Canonical.translateNativeBinding(canonicalResult: .ReleaseStation(station), canonicalError: noCause, nativeProfile: .swift)) {
            XCTAssertEqual($0 as? CanonicalUnimplemented, .behavior("B04"))
        }
        try m1Record("B08.raw", fixture: "retained source value copy preserves every field", call: {
            try Canonical.retainRawSourceRecord(sourceRecord: station.raw, nativeProfile: .swift)
        }, check: {
            XCTAssertEqual($0, station.raw)
            var modified = $0.object; modified["name"] = .string("caller copy")
            XCTAssertNotEqual(JSONValue.object(modified), station.raw)
            XCTAssertEqual(station.raw, try m1Document("conformance/fixtures/good/OTC_20991231.2.json")["stations"].array.first { $0["station_id"].string == station.stationId })
        })
        let contract = CanonicalFieldContract(modelType: .Station, members: [.StationRaw])
        XCTAssertThrowsError(try Canonical.materializeTypedModel(rawFields: .sourceJSON(station.raw), fieldContract: contract, origin: origin, modelType: .Station)) {
            XCTAssertEqual($0 as? CanonicalUnimplemented, .behavior("B07"))
        }
        for wrong in [CanonicalFieldContract(modelType: .Licence, members: [.LicenceRaw]),
            CanonicalFieldContract(modelType: .Station, members: [.LicenceRaw])] {
            XCTAssertThrowsError(try Canonical.materializeTypedModel(rawFields: .sourceJSON(station.raw), fieldContract: wrong, origin: origin, modelType: .Station)) {
                XCTAssertEqual($0 as? CanonicalUnimplemented, .behavior("B07"))
            }
        }
        let malformedTable = try m1Document("conformance/fixtures/good/OTC_20991231.2.json")["astro_tables"].array[0].object
        var invalid = malformedTable; invalid["first_year"] = .null
        let actualTableError = try m1NativeError("invalid_argument") { try AstroTable(.object(invalid)) }
        try m1Record("B07", fixture: "actual native AstroTable constructor refusal", call: {
            try m1NativeError(actualTableError.code) {
                try Canonical.materializeTypedModel(rawFields: .sourceJSON(.object(invalid)),
                    fieldContract: CanonicalFieldContract(modelType: .AstroTable, members: [.AstroTableValidRange]), origin: origin, modelType: .AstroTable)
            }
        }, check: { XCTAssertEqual($0.message, actualTableError.message); XCTAssertEqual($0.fields, actualTableError.fields) })
        var summaries: [JSONValue] = [], projections: [CanonicalStreamIndexStation] = []
        let jsonl = m1Root.appendingPathComponent("conformance/fixtures/good/OTC_20991231.2.jsonl")
        try eachLine(jsonl) { bytes, offset in
            let row = try JSONValue.parse(bytes)
            let native = IndexEntry.make(row, offset: offset, length: bytes.count)
            let span = CanonicalSourceByteSpan(offsetBytes: Int64(offset), lengthBytes: Int64(bytes.count))
            let projection = try Canonical.projectStationIndex(stationSourceRow: row, sourceByteSpan: span,
                projectionContract: CanonicalProjectionRules(scalarMembers: [.StationRaw], modelType: .Station, preserveUnknownSourceFields: false))
            try m1Record("B24", fixture: "full native JSONL row/span " + native.id, call: { projection }, check: {
                XCTAssertEqual($0.stationId, native.id); XCTAssertEqual($0.status, native.status)
                XCTAssertEqual($0.offset, span.offsetBytes); XCTAssertEqual($0.length, span.lengthBytes)
            })
            summaries.append(native.summary); projections.append(projection)
        }
        let digest = try SHA256.file(jsonl), size = Int64(try Data(contentsOf: jsonl).count)
        let index = CanonicalStreamIndex(indexVersion: 1, discoveryIndexVersion: 1, datestamp: good.datestamp,
            jsonl: jsonl.lastPathComponent, jsonlSha256: digest, jsonlSize: size, by: "opentideconstants-swift/0.1.0", stations: projections)
        let nativeIndex: JSONValue = .object(["index_version": .integer(1), "discovery_index_version": .integer(1),
            "datestamp": .string(good.datestamp), "jsonl": .string(jsonl.lastPathComponent), "jsonl_sha256": .string(digest),
            "jsonl_size": .integer(size), "by": .string("opentideconstants-swift/0.1.0"), "stations": .array(summaries)])
        try m1Record("B28", fixture: "native full streamIndex header and all closed projected fields", call: {
            try Canonical.encodeCacheJson(cacheDocument: .streamIndex(index))
        }, check: {
            let expected = try encode_cache_json(nativeIndex)
            XCTAssertEqual($0, expected); XCTAssertEqual(try JSONValue.parse($0), try JSONValue.parse(expected))
        })
        for value in [Double.nan, .infinity, -.infinity] {
            let expected = try m1NativeError("invalid_release") { try encode_cache_json(.number(value)) }
            try m1Record("B28", fixture: "native nonfinite number refusal", call: {
                try m1NativeError(expected.code) { try Canonical.encodeCacheJson(cacheDocument: .pointerOrCatalogue(.number(value))) }
            }, check: { XCTAssertEqual($0.message, expected.message); XCTAssertEqual($0.fields, expected.fields) })
        }
    }

    func testM1ChangedUpdateResult() async throws {
        let cache = FileManager.default.temporaryDirectory.appendingPathComponent("otc-m1-changed-update-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: cache, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: cache) }
        let rules = cache.appendingPathComponent("rules.json")
        let sourceRules: JSONValue = .array([.object(["match": .string("/good/OTC_latest-f1\\.json$"), "action": .string("json"),
            "file": .string("good/OTC_index.json"), "pointer": .string("/releases/1"), "times": .integer(1)])])
        try sourceRules.data().write(to: rules)
        let server = Process(), output = Pipe()
        server.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        server.arguments = ["-u", m1Root.appendingPathComponent("conformance/server.py").path,
            "--host", "127.0.0.1", "--port", "0", "--proxy-port", "0", "--rules", rules.path]
        server.standardOutput = output; server.standardError = FileHandle.standardError
        try server.run()
        defer { if server.isRunning { server.terminate() }; server.waitUntilExit() }
        let greeting = String(decoding: output.fileHandleForReading.availableData, as: UTF8.self)
        let endpoint = try XCTUnwrap(greeting.components(separatedBy: " ").first { $0.hasPrefix("http://") })
        let client = try await OpenTideConstants.open(cacheDir: cache.path, baseUrl: endpoint + "good/", timeout: 15)
        defer { client.close() }
        XCTAssertEqual(client.release.datestamp, "20991231")
        let retained = client.release
        let changed = try await client.update()
        XCTAssertTrue(changed.updated); XCTAssertEqual(changed.from, "20991231"); XCTAssertEqual(changed.to, "20991231.2")
        XCTAssertFalse(client.release === retained)
        XCTAssertNoThrow(try retained.requireStation(stationId: "OTC-T-0001"))
        let origin = try m1Origin(client.release.requireStation(stationId: "OTC-T-0001"))
        for result in [changed, try await client.update()] {
            let fields = CanonicalUpdateResultFields(updated: result.updated, from: result.from, to: result.to)
            try m1Record("B07", fixture: "actual changed/unchanged native update producer " + String(result.updated), call: {
                try Canonical.materializeTypedModel(rawFields: .UpdateResult(fields),
                    fieldContract: CanonicalFieldContract(modelType: .UpdateResult, members: [.UpdateResultUpdated, .UpdateResultFrom, .UpdateResultTo]),
                    origin: origin, modelType: .UpdateResult)
            }, check: {
                guard case .UpdateResult(let actual) = $0 else { throw NSError(domain: "M1WrongNativeUpdateModel", code: 1) }
                XCTAssertEqual(actual.updated, result.updated); XCTAssertEqual(actual.from, result.from); XCTAssertEqual(actual.to, result.to)
            })
        }
    }

    func testM1NativeBindingAndReceiptChannels() async throws {
        func typedReceipt(_ marker: JSONValue) throws -> CanonicalVerifiedReceipt {
            let fields = try marker["files"].object.mapValues { row in
                CanonicalVerifiedFile(sha256: try XCTUnwrap(row["sha256"].string), size: try XCTUnwrap(row["size"].integer), url: row["url"].string)
            }
            return CanonicalVerifiedReceipt(datestamp: try XCTUnwrap(marker["datestamp"].string), files: fields,
                formatVersion: try XCTUnwrap(marker["format_version"].string), minReaderVersion: try XCTUnwrap(marker["min_reader_version"].string),
                zenodoVersionDoi: marker["zenodo_version_doi"].string, verifiedAt: try XCTUnwrap(marker["verified_at"].string), by: try XCTUnwrap(marker["by"].string))
        }
        let server = Process(), output = Pipe()
        server.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        server.arguments = ["-u", m1Root.appendingPathComponent("conformance/server.py").path,
            "--host", "127.0.0.1", "--port", "0", "--proxy-port", "0"]
        server.standardOutput = output; server.standardError = FileHandle.standardError
        try server.run()
        defer { if server.isRunning { server.terminate() }; server.waitUntilExit() }
        let greeting = String(decoding: output.fileHandleForReading.availableData, as: UTF8.self)
        let endpoint = try XCTUnwrap(greeting.components(separatedBy: " ").first { $0.hasPrefix("http://") })
        let cache = FileManager.default.temporaryDirectory.appendingPathComponent("otc-m1-binding-" + UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: cache) }
        for stamp in ["20991231", "20991231.2"] {
            let client = try await OpenTideConstants.open(release: stamp == "20991231" ? stamp : nil, cacheDir: cache.path,
                offline: false, baseUrl: endpoint + "good/", timeout: 15)
            defer { client.close() }
            let published = try Data(contentsOf: cache.appendingPathComponent("v1/releases/" + stamp + "/.verified"))
            let produced = try JSONValue.parse(published)
            if let events = ProcessInfo.processInfo.environment["OTC_M1_SW_EVENTS"] {
                try published.write(to: URL(fileURLWithPath: events).deletingLastPathComponent().appendingPathComponent("native-receipt-" + stamp + ".json"))
            }
            let marker: JSONValue
            if let frozen = ProcessInfo.processInfo.environment["OTC_M1_SW_RECEIPT_INPUT_DIR"] {
                marker = try JSONValue.parse(Data(contentsOf: URL(fileURLWithPath: frozen).appendingPathComponent("native-receipt-" + stamp + ".json")))
                XCTAssertEqual(marker.object.keys.sorted(), produced.object.keys.sorted())
                XCTAssertEqual(marker["zenodo_version_doi"], produced["zenodo_version_doi"])
            } else { marker = produced }
            print("M1_SW_RECEIPT_INPUT " + String(decoding: try encode_cache_json(marker), as: UTF8.self))
            XCTAssertEqual(marker["datestamp"].string, stamp)
            XCTAssertEqual(marker["zenodo_version_doi"].string, stamp == "20991231" ? nil : "10.5072/zenodo.2")
            let receipt = try typedReceipt(marker)
            try m1Record("B28", fixture: "actual published native receipt optional DOI " + stamp, call: {
                try Canonical.encodeCacheJson(cacheDocument: .verifiedReceipt(receipt))
            }, check: {
                let expected = try encode_cache_json(marker)
                XCTAssertEqual($0, expected)
                guard $0 == expected else { throw NSError(domain: "M1NativeReceiptMismatch", code: 1) }
            })
        }
        let markerPath = cache.appendingPathComponent("v1/releases/20991231/.verified")
        var older = try JSONValue.parse(Data(contentsOf: markerPath)).object
        var olderFiles = older["files"]!.object, olderJSON = olderFiles["OTC_20991231.json"]!.object
        olderJSON.removeValue(forKey: "url")
        olderFiles["OTC_20991231.json"] = .object(olderJSON); older["files"] = .object(olderFiles)
        try Cache.atomic(JSONValue.object(older).data(), markerPath)
        let stream = try await OpenTideConstants.open(release: "20991231", cacheDir: cache.path, mode: .stream,
            baseUrl: endpoint + "good/", timeout: 15)
        defer { stream.close() }
        let mergedBytes = try Data(contentsOf: markerPath), producedMerged = try JSONValue.parse(mergedBytes)
        let merged: JSONValue
        if let frozen = ProcessInfo.processInfo.environment["OTC_M1_SW_RECEIPT_INPUT_DIR"],
            FileManager.default.fileExists(atPath: URL(fileURLWithPath: frozen).appendingPathComponent("native-receipt-url-absent.json").path) {
            merged = try JSONValue.parse(Data(contentsOf: URL(fileURLWithPath: frozen).appendingPathComponent("native-receipt-url-absent.json")))
            XCTAssertEqual(merged["files"].object.keys.sorted(), producedMerged["files"].object.keys.sorted())
            XCTAssertEqual(merged["files"]["OTC_20991231.json"]["url"], producedMerged["files"]["OTC_20991231.json"]["url"])
        } else { merged = producedMerged }
        print("M1_SW_RECEIPT_URL_INPUT " + String(decoding: try encode_cache_json(merged), as: UTF8.self))
        XCTAssertNil(merged["files"]["OTC_20991231.json"]["url"].string)
        if let events = ProcessInfo.processInfo.environment["OTC_M1_SW_EVENTS"] {
            try mergedBytes.write(to: URL(fileURLWithPath: events).deletingLastPathComponent().appendingPathComponent("native-receipt-url-absent.json"))
        }
        let mergedFields = try typedReceipt(merged)
        try m1Record("B28", fixture: "actual native other-mode merge retains older absent URL and nested file map", call: {
            try Canonical.encodeCacheJson(cacheDocument: .verifiedReceipt(mergedFields))
        }, check: {
            let expected = try encode_cache_json(merged)
            XCTAssertEqual($0, expected)
            guard $0 == expected else { throw NSError(domain: "M1NativeOptionalURLMismatch", code: 1) }
        })
        server.terminate(); server.waitUntilExit()
        let fallback = try await OpenTideConstants.open(cacheDir: cache.path, offline: false,
            baseUrl: endpoint + "good/", timeout: 1, onNetworkError: .useCache)
        defer { fallback.close() }
        XCTAssertEqual(fallback.loadedFrom, .cacheAfterError)
        let native = try XCTUnwrap(fallback.lastError)
        XCTAssertEqual(native.code, "network")
        let error = CanonicalCanonicalError(code: .network, structuredFields: .object(native.fields), cause: native)
        try m1Record("B04", fixture: "actual cache usable Client and retained network error", call: {
            try Canonical.translateNativeBinding(canonicalResult: .ClientOpen(fallback), canonicalError: error, nativeProfile: .swift)
        }, check: {
            guard case .ClientOpen(let actual) = $0, actual === fallback else { throw NSError(domain: "M1NativeClientIdentityMismatch", code: 1) }
            XCTAssertEqual(actual.lastError?.message, native.message); XCTAssertEqual(actual.lastError?.fields, native.fields)
            XCTAssertNotNil(try actual.release.station(stationId: "OTC-T-0001"))
        })
        for mismatch in [CanonicalCanonicalError(code: .io, structuredFields: error.structuredFields, cause: native),
            CanonicalCanonicalError(code: .network, structuredFields: .object([:]), cause: native)] {
            try m1Record("B04", fixture: "retained diagnostic mismatch takes native terminal channel", call: {
                try m1NativeError("network") {
                    try Canonical.translateNativeBinding(canonicalResult: .ClientOpen(fallback), canonicalError: mismatch, nativeProfile: .swift)
                }
            }, check: {
                XCTAssertEqual($0.message, native.message); XCTAssertEqual($0.fields, native.fields)
                guard $0.message == native.message, $0.fields == native.fields else { throw NSError(domain: "M1NativeCauseMismatch", code: 1) }
            })
        }
        fallback.close()
        try m1Record("B04", fixture: "native close successful declared no value", call: {
            try Canonical.translateNativeBinding(canonicalResult: .ClientClose, canonicalError: nil, nativeProfile: .swift)
        }, check: { guard case .ClientClose = $0 else { throw NSError(domain: "M1NativeNoValueMismatch", code: 1) } })
    }

    func testM1NativeUpdateResultFields() async throws {
        let server = Process(), output = Pipe()
        server.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        server.arguments = ["-u", m1Root.appendingPathComponent("conformance/server.py").path,
            "--host", "127.0.0.1", "--port", "0", "--proxy-port", "0"]
        server.standardOutput = output
        server.standardError = FileHandle.standardError
        try server.run()
        defer { if server.isRunning { server.terminate() }; server.waitUntilExit() }
        let greeting = String(decoding: output.fileHandleForReading.availableData, as: UTF8.self)
        let endpoint = try XCTUnwrap(greeting.components(separatedBy: " ").first { $0.hasPrefix("http://") })
        let cache = FileManager.default.temporaryDirectory.appendingPathComponent("otc-m1-update-" + UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: cache) }
        let client = try await OpenTideConstants.open(cacheDir: cache.path, offline: false,
            baseUrl: endpoint + "good/", timeout: 15)
        defer { client.close() }
        let result = try await client.update()
        XCTAssertFalse(result.updated)
        XCTAssertEqual(result.from, client.release.datestamp)
        XCTAssertEqual(result.to, client.release.datestamp)
        let station = try XCTUnwrap(client.release.stations(includeFlagged: true, includeFallback: true).first)
        let origin = try m1Origin(station)
        let fields = CanonicalUpdateResultFields(updated: result.updated, from: result.from, to: result.to)
        try m1Record("B07", fixture: "actual public update result from native HTTP/cache/latest pipeline", call: {
            try Canonical.materializeTypedModel(rawFields: .UpdateResult(fields),
                fieldContract: CanonicalFieldContract(modelType: .UpdateResult,
                    members: [.UpdateResultUpdated, .UpdateResultFrom, .UpdateResultTo]),
                origin: origin, modelType: .UpdateResult)
        }, check: {
            guard case .UpdateResult(let actual) = $0 else { return XCTFail("Wrong native UpdateResult variant") }
            XCTAssertEqual(actual.updated, result.updated)
            XCTAssertEqual(actual.from, result.from)
            XCTAssertEqual(actual.to, result.to)
        })
    }

    func testM1PreparedStreamOwnerControl() throws {
        let path = "/Users/jpr5/.local/share/copilotkit/cr/otc-codex-takeover/execution/sdk-core-sync/canonical-behavior/holistic-reset/implementation-plan/M1-SW/managed-stream-fixtures/OTC_20261011.jsonl"
        XCTAssertEqual(SHA256.digest(try Reader.read(URL(fileURLWithPath: path))),
            "d808385cce13adf08d0c2e8f92f08128d56a9d38bd68105eeed89d452c84ccf9")
        let reference = try Reader.load(URL(fileURLWithPath: path), mode: .stream,
            commercialOnly: false, commercialBasis: "strict", historicalOffsetsPolicy: "fallback")
        defer { reference.close() }
        let stationId = try XCTUnwrap(reference.entries.first { $0.status == "active" }).id
        let foreign = try reference.requireStation(stationId: stationId)
        let fields = try Release.prepareMaterialization(from: reference)
        let oldReader = try XCTUnwrap(Mirror(reflecting: reference).children.first { $0.label == "reader" }?.value as? FileHandle)
        let newReader = try XCTUnwrap(Mirror(reflecting: fields).children.first { $0.label == "reader" }?.value as? FileHandle)
        defer { try? newReader.close() }
        XCTAssertFalse(oldReader === newReader)
        XCTAssertNotEqual(oldReader.fileDescriptor, newReader.fileDescriptor)
        try m1Record("B07", fixture: "native stream reader transferred to fresh Release only", call: {
            try Canonical.materializeTypedModel(rawFields: .Release(fields),
                fieldContract: CanonicalFieldContract(modelType: .Release,
                    members: [.ReleaseStation, .ReleaseFiles, .ReleaseHistoricalOffsetsPolicy]),
                origin: fields.originToken, modelType: .Release)
        }, check: {
            guard case .Release(let actual) = $0 else { return XCTFail("Wrong native stream Release variant") }
            XCTAssertFalse(actual === reference)
            XCTAssertTrue((Mirror(reflecting: actual).children.first { $0.label == "reader" }?.value as? FileHandle) === newReader)
            let owned = try actual.requireStation(stationId: stationId)
            XCTAssertEqual(owned.raw, foreign.raw)
            XCTAssertEqual(owned.originToken, fields.originToken)
            XCTAssertNoThrow(try actual.own(owned))
            XCTAssertThrowsError(try actual.own(foreign))
            actual.close()
            XCTAssertThrowsError(try newReader.read(upToCount: 1))
            XCTAssertEqual(try reference.requireStation(stationId: stationId).raw, foreign.raw)
            XCTAssertNoThrow(try oldReader.seek(toOffset: 0))
        })
    }

    func testM1PreparedManagedModelFields() async throws {
        let reference = try m1Release("conformance/vectors/1.0/vectors-release.json")
        defer { reference.close() }
        let foreign = try reference.requireStation(stationId: "OTC-V-NOAA-1820000")
        let releaseFields = try Release.prepareMaterialization(from: reference)
        let cacheRoot = FileManager.default.temporaryDirectory.appendingPathComponent("otc-m1-managed-" + UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: cacheRoot) }
        let io = ClientIO(cache: Cache(root: cacheRoot), offline: true, mode: .eager,
            baseUrl: URL(string: defaultBaseUrl)!, timeout: 60, proxy: nil, caFile: nil,
            userAgent: nil, onNetworkError: .useCache, verifyOnOpen: false, commercialOnly: false,
            commercialBasis: "strict", historicalOffsetsPolicy: "fallback", logger: nil)
        let loaded = try await io.open("latest", file:
            "/Users/jpr5/.local/share/copilotkit/cr/otc-codex-takeover/execution/sdk-core-sync/canonical-behavior/holistic-reset/implementation-plan/M1-SW/public-fixtures/OTC_20261011.json")
        defer { loaded.release.close() }
        XCTAssertFalse(loaded.release === reference)
        let clientFields = OpenTideConstants.prepareMaterialization(loaded: loaded, io: io,
            pinned: true, autoUpdate: false, updateInterval: 86400)
        try m1Record("B07", fixture: "fresh independently owned native Client fields", call: {
            try Canonical.materializeTypedModel(rawFields: .Client(clientFields),
                fieldContract: CanonicalFieldContract(modelType: .Client,
                    members: [.ClientRelease, .ClientLoadedFrom, .ClientLastError, .ClientNewerFormatMajor]),
                origin: releaseFields.originToken, modelType: .Client)
        }, check: {
            guard case .Client(let actual) = $0 else { return XCTFail("Wrong native Client variant") }
            XCTAssertTrue(actual.release === loaded.release)
            XCTAssertEqual(actual.loadedFrom, loaded.from)
            XCTAssertNil(actual.lastError); XCTAssertNil(actual.newerFormatMajor)
            XCTAssertEqual(actual.cache.root, io.cache.root)
            XCTAssertEqual(actual.offline, io.offline); XCTAssertEqual(actual.pinned, clientFields.pinned)
            XCTAssertEqual(actual.baseUrl, io.baseUrl); XCTAssertEqual(actual.timeout, io.timeout)
            XCTAssertEqual(actual.userAgent, io.userAgent); XCTAssertEqual(actual.opened, loaded.paths)
            let fields = Mirror(reflecting: actual).children
            XCTAssertTrue((fields.first { $0.label == "lock" }?.value as? NSRecursiveLock) === clientFields.lock)
            XCTAssertEqual(fields.first { $0.label == "lastCheck" }?.value as? Double, clientFields.lastCheck)
            XCTAssertEqual(fields.first { $0.label == "autoUpdate" }?.value as? Bool, clientFields.autoUpdate)
            XCTAssertEqual(fields.first { $0.label == "updateInterval" }?.value as? Double, clientFields.updateInterval)
            XCTAssertEqual(fields.first { $0.label == "closed" }?.value as? Bool, false)
            XCTAssertEqual(fields.first { $0.label == "updating" }?.value as? Bool, false)
            actual.close()
            XCTAssertThrowsError(try loaded.release.checkOpen())
            XCTAssertNoThrow(try reference.requireStation(stationId: foreign.stationId))
        })
        try m1Record("B07", fixture: "fresh independently owned native eager Release fields", call: {
            try Canonical.materializeTypedModel(rawFields: .Release(releaseFields),
                fieldContract: CanonicalFieldContract(modelType: .Release,
                    members: [.ReleaseDatestamp, .ReleaseFiles, .ReleaseConventions, .ReleaseLicences]),
                origin: releaseFields.originToken, modelType: .Release)
        }, check: {
            guard case .Release(let actual) = $0 else { return XCTFail("Wrong native Release variant") }
            XCTAssertFalse(actual === reference)
            XCTAssertEqual(actual.meta, releaseFields.meta)
            XCTAssertEqual(actual.commercialOnly, releaseFields.commercialOnly)
            XCTAssertEqual(actual.commercialBasis, releaseFields.commercialBasis)
            XCTAssertEqual(actual.historicalOffsetsPolicy, releaseFields.historicalOffsetsPolicy)
            XCTAssertEqual(actual.convById, releaseFields.convById); XCTAssertEqual(actual.licById, releaseFields.licById)
            XCTAssertEqual(actual.entries.map(\.id), releaseFields.entries.map(\.id))
            XCTAssertEqual(actual.byId.keys.sorted(), releaseFields.byId.keys.sorted())
            XCTAssertEqual(actual.documents, releaseFields.documents)
            XCTAssertEqual(actual.jsonl, releaseFields.jsonl); XCTAssertEqual(actual.indexPath, releaseFields.indexPath)
            XCTAssertEqual(actual.files, releaseFields.files); XCTAssertEqual(actual.zenodoVersionDoi, releaseFields.zenodoVersionDoi)
            XCTAssertTrue(actual.astroCache.isEmpty); XCTAssertTrue(actual.lru.isEmpty); XCTAssertTrue(actual.lruOrder.isEmpty)
            XCTAssertFalse(actual.closed)
            let owned = try actual.requireStation(stationId: foreign.stationId)
            XCTAssertEqual(owned.originToken, releaseFields.originToken)
            XCTAssertNoThrow(try actual.own(owned))
            XCTAssertThrowsError(try actual.own(foreign)) {
                XCTAssertEqual(($0 as? OpenTideConstantsError)?.code, "invalid_argument")
            }
            actual.close()
            XCTAssertThrowsError(try actual.checkOpen())
            XCTAssertNoThrow(try reference.requireStation(stationId: foreign.stationId))
        })
    }

    func testM1PreparedResultModelFields() throws {
        let release = try m1Release("conformance/vectors/1.0/vectors-release.json")
        defer { release.close() }
        let station = try release.requireStation(stationId: "OTC-V-NOAA-1820000")
        let origin = try m1Origin(station)
        let heightVector = try m1Vector("OTC-V-NOAA-1820000/heights")
        let times = try heightVector["args"]["times"].array.map(m1Date)
        let heights = try release.heightsAt(station: station, times: times, datum: "mean_level").toLocal(tz: "UTC")
        let heightPoint = try XCTUnwrap(heights.items.first)
        let eventVector = try m1Vector("OTC-V-NOAA-1820000/extremes/0")
        let eventStart = try m1Date(eventVector["args"]["start"]), eventStop = try m1Date(eventVector["args"]["stop"])
        let extremes = try release.extremes(station: station, start: eventStart, stop: eventStop, datum: "mean_level").toLocal(tz: "UTC")
        let extreme = try XCTUnwrap(extremes.items.first)
        let currentVector = try m1Vector("OTC-V-NOAA-ACT1616/currents/1")
        let currentStart = try m1Date(currentVector["args"]["start"]), currentStop = try m1Date(currentVector["args"]["stop"])
        let currentStation = try release.requireStation(stationId: "OTC-V-NOAA-ACT1616")
        let currents = try release.currents(station: currentStation, start: currentStart, stop: currentStop,
            stepS: try XCTUnwrap(currentVector["args"]["step_s"].integer), binNumber: 1).toLocal(tz: "UTC")
        let currentPoint = try XCTUnwrap(currents.items.first)
        let currentEventVector = try m1Vector("OTC-V-NOAA-ACT1591/events/1/0")
        let currentEventStation = try release.requireStation(stationId: "OTC-V-NOAA-ACT1591")
        let currentEvents = try release.currentEvents(station: currentEventStation,
            start: m1Date(currentEventVector["args"]["start"]), stop: m1Date(currentEventVector["args"]["stop"]),
            binNumber: 1).toLocal(tz: "UTC")
        let currentEvent = try XCTUnwrap(currentEvents.items.first)
        let nearby = try XCTUnwrap(release.near(lat: station.lat, lon: station.lon, radiusKm: 0).first)
        let stats = try release.stats
        guard case .one(let optionalDatum) = try release.datums(station: station) else {
            return XCTFail("Actual native datum producer did not select one datum")
        }
        let datum = try XCTUnwrap(optionalDatum), level = try XCTUnwrap(datum.levels.first)
        let ranges = try release.ranges(station: station)
        XCTAssertEqual(heights.items.count, times.count)
        XCTAssertEqual(extremes.items.count, eventVector["expect"]["prediction"]["items"].array.count)
        XCTAssertEqual(currents.items.count, currentVector["expect"]["prediction"]["items"].array.count)
        XCTAssertEqual(currentEvents.items.count, currentEventVector["expect"]["prediction"]["items"].array.count)
            try m1Record("B07", fixture: "genuine prepared constructor fields HeightPoint", call: {
                try Canonical.materializeTypedModel(rawFields: .HeightPoint(CanonicalHeightPointFields(time: heightPoint.time, heightM: heightPoint.heightM, localTime: heightPoint.localTime, utcOffsetS: heightPoint.utcOffsetS)),
                    fieldContract: CanonicalFieldContract(modelType: .HeightPoint, members: [.HeightPointTime, .HeightPointHeightM, .HeightPointLocalTime, .HeightPointUtcOffsetS]),
                    origin: origin, modelType: .HeightPoint)
            }, check: {
                guard case .HeightPoint(let actual) = $0 else { return XCTFail("Wrong native HeightPoint variant") }
                    XCTAssertEqual(actual.time, heightPoint.time)
                    XCTAssertEqual(actual.heightM, heightPoint.heightM)
                    XCTAssertEqual(actual.localTime, heightPoint.localTime)
                    XCTAssertEqual(actual.utcOffsetS, heightPoint.utcOffsetS)
            })

            try m1Record("B07", fixture: "genuine prepared constructor fields Extreme", call: {
                try Canonical.materializeTypedModel(rawFields: .Extreme(CanonicalExtremeFields(time: extreme.time, type: extreme.type, heightM: extreme.heightM, localTime: extreme.localTime, utcOffsetS: extreme.utcOffsetS)),
                    fieldContract: CanonicalFieldContract(modelType: .Extreme, members: [.ExtremeTime, .ExtremeType, .ExtremeHeightM, .ExtremeLocalTime, .ExtremeUtcOffsetS]),
                    origin: origin, modelType: .Extreme)
            }, check: {
                guard case .Extreme(let actual) = $0 else { return XCTFail("Wrong native Extreme variant") }
                    XCTAssertEqual(actual.time, extreme.time)
                    XCTAssertEqual(actual.type, extreme.type)
                    XCTAssertEqual(actual.heightM, extreme.heightM)
                    XCTAssertEqual(actual.localTime, extreme.localTime)
                    XCTAssertEqual(actual.utcOffsetS, extreme.utcOffsetS)
            })

            try m1Record("B07", fixture: "genuine prepared constructor fields CurrentPoint", call: {
                try Canonical.materializeTypedModel(rawFields: .CurrentPoint(CanonicalCurrentPointFields(time: currentPoint.time, velocityMajorMs: currentPoint.velocityMajorMs, velocityMinorMs: currentPoint.velocityMinorMs, speedMs: currentPoint.speedMs, directionDeg: currentPoint.directionDeg, localTime: currentPoint.localTime, utcOffsetS: currentPoint.utcOffsetS)),
                    fieldContract: CanonicalFieldContract(modelType: .CurrentPoint, members: [.CurrentPointTime, .CurrentPointVelocityMajorMs, .CurrentPointVelocityMinorMs, .CurrentPointSpeedMs, .CurrentPointDirectionDeg, .CurrentPointLocalTime, .CurrentPointUtcOffsetS]),
                    origin: origin, modelType: .CurrentPoint)
            }, check: {
                guard case .CurrentPoint(let actual) = $0 else { return XCTFail("Wrong native CurrentPoint variant") }
                    XCTAssertEqual(actual.time, currentPoint.time)
                    XCTAssertEqual(actual.velocityMajorMs, currentPoint.velocityMajorMs)
                    XCTAssertEqual(actual.velocityMinorMs, currentPoint.velocityMinorMs)
                    XCTAssertEqual(actual.speedMs, currentPoint.speedMs)
                    XCTAssertEqual(actual.directionDeg, currentPoint.directionDeg)
                    XCTAssertEqual(actual.localTime, currentPoint.localTime)
                    XCTAssertEqual(actual.utcOffsetS, currentPoint.utcOffsetS)
            })

            try m1Record("B07", fixture: "genuine prepared constructor fields CurrentEvent", call: {
                try Canonical.materializeTypedModel(rawFields: .CurrentEvent(CanonicalCurrentEventFields(time: currentEvent.time, type: currentEvent.type, velocityMs: currentEvent.velocityMs, directionDeg: currentEvent.directionDeg, localTime: currentEvent.localTime, utcOffsetS: currentEvent.utcOffsetS)),
                    fieldContract: CanonicalFieldContract(modelType: .CurrentEvent, members: [.CurrentEventTime, .CurrentEventType, .CurrentEventVelocityMs, .CurrentEventDirectionDeg, .CurrentEventLocalTime, .CurrentEventUtcOffsetS]),
                    origin: origin, modelType: .CurrentEvent)
            }, check: {
                guard case .CurrentEvent(let actual) = $0 else { return XCTFail("Wrong native CurrentEvent variant") }
                    XCTAssertEqual(actual.time, currentEvent.time)
                    XCTAssertEqual(actual.type, currentEvent.type)
                    XCTAssertEqual(actual.velocityMs, currentEvent.velocityMs)
                    XCTAssertEqual(actual.directionDeg, currentEvent.directionDeg)
                    XCTAssertEqual(actual.localTime, currentEvent.localTime)
                    XCTAssertEqual(actual.utcOffsetS, currentEvent.utcOffsetS)
            })

            try m1Record("B07", fixture: "genuine prepared constructor fields HeightSeries", call: {
                try Canonical.materializeTypedModel(rawFields: .HeightSeries(CanonicalHeightSeriesFields(items: heights.items, stationId: heights.stationId, timezone: heights.timezone, method: heights.method, setId: heights.setId, conventionId: heights.conventionId, astroTableId: heights.astroTableId, referenceStationId: heights.referenceStationId, referenceBin: heights.referenceBin, datum: heights.datum, datumName: heights.datumName, datumKind: heights.datumKind, datumUncertaintyM: heights.datumUncertaintyM, tz: heights.tz, tzVersion: heights.tzVersion, release: heights.release, algorithm: heights.algorithm, offsetId: heights.offsetId, offsetSource: heights.offsetSource, offsetSourceVersion: heights.offsetSourceVersion, historicalOffsets: heights.historicalOffsets, currentValidity: heights.currentValidity, currentAccuracy: heights.currentAccuracy, referenceSetId: heights.referenceSetId, referenceSourceVersion: heights.referenceSourceVersion, reference2020Equivalence: heights.reference2020Equivalence, sourceNote: heights.sourceNote)),
                    fieldContract: CanonicalFieldContract(modelType: .HeightSeries, members: [.HeightSeriesItems, .HeightSeriesStationId, .HeightSeriesTimezone, .HeightSeriesMethod, .HeightSeriesSetId, .HeightSeriesConventionId, .HeightSeriesAstroTableId, .HeightSeriesReferenceStationId, .HeightSeriesReferenceBin, .HeightSeriesDatum, .HeightSeriesDatumName, .HeightSeriesDatumKind, .HeightSeriesDatumUncertaintyM, .HeightSeriesTz, .HeightSeriesTzVersion, .HeightSeriesRelease, .HeightSeriesAlgorithm, .HeightSeriesOffsetId, .HeightSeriesOffsetSource, .HeightSeriesOffsetSourceVersion, .HeightSeriesHistoricalOffsets, .HeightSeriesCurrentValidity, .HeightSeriesCurrentAccuracy, .HeightSeriesReferenceSetId, .HeightSeriesReferenceSourceVersion, .HeightSeriesReference2020Equivalence, .HeightSeriesSourceNote]),
                    origin: origin, modelType: .HeightSeries)
            }, check: {
                guard case .HeightSeries(let actual) = $0 else { return XCTFail("Wrong native HeightSeries variant") }
                    XCTAssertEqual(actual.items, heights.items)
                    XCTAssertEqual(actual.stationId, heights.stationId)
                    XCTAssertEqual(actual.timezone, heights.timezone)
                    XCTAssertEqual(actual.method, heights.method)
                    XCTAssertEqual(actual.setId, heights.setId)
                    XCTAssertEqual(actual.conventionId, heights.conventionId)
                    XCTAssertEqual(actual.astroTableId, heights.astroTableId)
                    XCTAssertEqual(actual.referenceStationId, heights.referenceStationId)
                    XCTAssertEqual(actual.referenceBin, heights.referenceBin)
                    XCTAssertEqual(actual.datum, heights.datum)
                    XCTAssertEqual(actual.datumName, heights.datumName)
                    XCTAssertEqual(actual.datumKind, heights.datumKind)
                    XCTAssertEqual(actual.datumUncertaintyM, heights.datumUncertaintyM)
                    XCTAssertEqual(actual.tz, heights.tz)
                    XCTAssertEqual(actual.tzVersion, heights.tzVersion)
                    XCTAssertEqual(actual.release, heights.release)
                    XCTAssertEqual(actual.algorithm, heights.algorithm)
                    XCTAssertEqual(actual.offsetId, heights.offsetId)
                    XCTAssertEqual(actual.offsetSource, heights.offsetSource)
                    XCTAssertEqual(actual.offsetSourceVersion, heights.offsetSourceVersion)
                    XCTAssertEqual(actual.historicalOffsets, heights.historicalOffsets)
                    XCTAssertEqual(actual.currentValidity, heights.currentValidity)
                    XCTAssertEqual(actual.currentAccuracy, heights.currentAccuracy)
                    XCTAssertEqual(actual.referenceSetId, heights.referenceSetId)
                    XCTAssertEqual(actual.referenceSourceVersion, heights.referenceSourceVersion)
                    XCTAssertEqual(actual.reference2020Equivalence, heights.reference2020Equivalence)
                    XCTAssertEqual(actual.sourceNote, heights.sourceNote)
            })

            try m1Record("B07", fixture: "genuine prepared constructor fields ExtremeList", call: {
                try Canonical.materializeTypedModel(rawFields: .ExtremeList(CanonicalExtremeListFields(items: extremes.items, stationId: extremes.stationId, timezone: extremes.timezone, method: extremes.method, setId: extremes.setId, conventionId: extremes.conventionId, astroTableId: extremes.astroTableId, referenceStationId: extremes.referenceStationId, referenceBin: extremes.referenceBin, datum: extremes.datum, datumName: extremes.datumName, datumKind: extremes.datumKind, datumUncertaintyM: extremes.datumUncertaintyM, tz: extremes.tz, tzVersion: extremes.tzVersion, release: extremes.release, algorithm: extremes.algorithm, offsetId: extremes.offsetId, offsetSource: extremes.offsetSource, offsetSourceVersion: extremes.offsetSourceVersion, historicalOffsets: extremes.historicalOffsets, currentValidity: extremes.currentValidity, currentAccuracy: extremes.currentAccuracy, referenceSetId: extremes.referenceSetId, referenceSourceVersion: extremes.referenceSourceVersion, reference2020Equivalence: extremes.reference2020Equivalence, sourceNote: extremes.sourceNote)),
                    fieldContract: CanonicalFieldContract(modelType: .ExtremeList, members: [.ExtremeListItems, .ExtremeListStationId, .ExtremeListTimezone, .ExtremeListMethod, .ExtremeListSetId, .ExtremeListConventionId, .ExtremeListAstroTableId, .ExtremeListReferenceStationId, .ExtremeListReferenceBin, .ExtremeListDatum, .ExtremeListDatumName, .ExtremeListDatumKind, .ExtremeListDatumUncertaintyM, .ExtremeListTz, .ExtremeListTzVersion, .ExtremeListRelease, .ExtremeListAlgorithm, .ExtremeListOffsetId, .ExtremeListOffsetSource, .ExtremeListOffsetSourceVersion, .ExtremeListHistoricalOffsets, .ExtremeListCurrentValidity, .ExtremeListCurrentAccuracy, .ExtremeListReferenceSetId, .ExtremeListReferenceSourceVersion, .ExtremeListReference2020Equivalence, .ExtremeListSourceNote]),
                    origin: origin, modelType: .ExtremeList)
            }, check: {
                guard case .ExtremeList(let actual) = $0 else { return XCTFail("Wrong native ExtremeList variant") }
                    XCTAssertEqual(actual.items, extremes.items)
                    XCTAssertEqual(actual.stationId, extremes.stationId)
                    XCTAssertEqual(actual.timezone, extremes.timezone)
                    XCTAssertEqual(actual.method, extremes.method)
                    XCTAssertEqual(actual.setId, extremes.setId)
                    XCTAssertEqual(actual.conventionId, extremes.conventionId)
                    XCTAssertEqual(actual.astroTableId, extremes.astroTableId)
                    XCTAssertEqual(actual.referenceStationId, extremes.referenceStationId)
                    XCTAssertEqual(actual.referenceBin, extremes.referenceBin)
                    XCTAssertEqual(actual.datum, extremes.datum)
                    XCTAssertEqual(actual.datumName, extremes.datumName)
                    XCTAssertEqual(actual.datumKind, extremes.datumKind)
                    XCTAssertEqual(actual.datumUncertaintyM, extremes.datumUncertaintyM)
                    XCTAssertEqual(actual.tz, extremes.tz)
                    XCTAssertEqual(actual.tzVersion, extremes.tzVersion)
                    XCTAssertEqual(actual.release, extremes.release)
                    XCTAssertEqual(actual.algorithm, extremes.algorithm)
                    XCTAssertEqual(actual.offsetId, extremes.offsetId)
                    XCTAssertEqual(actual.offsetSource, extremes.offsetSource)
                    XCTAssertEqual(actual.offsetSourceVersion, extremes.offsetSourceVersion)
                    XCTAssertEqual(actual.historicalOffsets, extremes.historicalOffsets)
                    XCTAssertEqual(actual.currentValidity, extremes.currentValidity)
                    XCTAssertEqual(actual.currentAccuracy, extremes.currentAccuracy)
                    XCTAssertEqual(actual.referenceSetId, extremes.referenceSetId)
                    XCTAssertEqual(actual.referenceSourceVersion, extremes.referenceSourceVersion)
                    XCTAssertEqual(actual.reference2020Equivalence, extremes.reference2020Equivalence)
                    XCTAssertEqual(actual.sourceNote, extremes.sourceNote)
            })

            try m1Record("B07", fixture: "genuine prepared constructor fields CurrentSeries", call: {
                try Canonical.materializeTypedModel(rawFields: .CurrentSeries(CanonicalCurrentSeriesFields(items: currents.items, stationId: currents.stationId, timezone: currents.timezone, method: currents.method, setId: currents.setId, conventionId: currents.conventionId, astroTableId: currents.astroTableId, referenceStationId: currents.referenceStationId, referenceBin: currents.referenceBin, datum: currents.datum, datumName: currents.datumName, datumKind: currents.datumKind, datumUncertaintyM: currents.datumUncertaintyM, tz: currents.tz, tzVersion: currents.tzVersion, release: currents.release, algorithm: currents.algorithm, binNumber: currents.binNumber)),
                    fieldContract: CanonicalFieldContract(modelType: .CurrentSeries, members: [.CurrentSeriesItems, .CurrentSeriesStationId, .CurrentSeriesTimezone, .CurrentSeriesMethod, .CurrentSeriesSetId, .CurrentSeriesConventionId, .CurrentSeriesAstroTableId, .CurrentSeriesReferenceStationId, .CurrentSeriesReferenceBin, .CurrentSeriesDatum, .CurrentSeriesDatumName, .CurrentSeriesDatumKind, .CurrentSeriesDatumUncertaintyM, .CurrentSeriesTz, .CurrentSeriesTzVersion, .CurrentSeriesRelease, .CurrentSeriesAlgorithm, .CurrentSeriesBinNumber]),
                    origin: origin, modelType: .CurrentSeries)
            }, check: {
                guard case .CurrentSeries(let actual) = $0 else { return XCTFail("Wrong native CurrentSeries variant") }
                    XCTAssertEqual(actual.items, currents.items)
                    XCTAssertEqual(actual.stationId, currents.stationId)
                    XCTAssertEqual(actual.timezone, currents.timezone)
                    XCTAssertEqual(actual.method, currents.method)
                    XCTAssertEqual(actual.setId, currents.setId)
                    XCTAssertEqual(actual.conventionId, currents.conventionId)
                    XCTAssertEqual(actual.astroTableId, currents.astroTableId)
                    XCTAssertEqual(actual.referenceStationId, currents.referenceStationId)
                    XCTAssertEqual(actual.referenceBin, currents.referenceBin)
                    XCTAssertEqual(actual.datum, currents.datum)
                    XCTAssertEqual(actual.datumName, currents.datumName)
                    XCTAssertEqual(actual.datumKind, currents.datumKind)
                    XCTAssertEqual(actual.datumUncertaintyM, currents.datumUncertaintyM)
                    XCTAssertEqual(actual.tz, currents.tz)
                    XCTAssertEqual(actual.tzVersion, currents.tzVersion)
                    XCTAssertEqual(actual.release, currents.release)
                    XCTAssertEqual(actual.algorithm, currents.algorithm)
                    XCTAssertEqual(actual.binNumber, currents.binNumber)
            })

            try m1Record("B07", fixture: "genuine prepared constructor fields CurrentEventList", call: {
                try Canonical.materializeTypedModel(rawFields: .CurrentEventList(CanonicalCurrentEventListFields(items: currentEvents.items, stationId: currentEvents.stationId, timezone: currentEvents.timezone, method: currentEvents.method, setId: currentEvents.setId, conventionId: currentEvents.conventionId, astroTableId: currentEvents.astroTableId, referenceStationId: currentEvents.referenceStationId, referenceBin: currentEvents.referenceBin, datum: currentEvents.datum, datumName: currentEvents.datumName, datumKind: currentEvents.datumKind, datumUncertaintyM: currentEvents.datumUncertaintyM, tz: currentEvents.tz, tzVersion: currentEvents.tzVersion, release: currentEvents.release, algorithm: currentEvents.algorithm, binNumber: currentEvents.binNumber, omittedEventTypes: currentEvents.omittedEventTypes)),
                    fieldContract: CanonicalFieldContract(modelType: .CurrentEventList, members: [.CurrentEventListItems, .CurrentEventListStationId, .CurrentEventListTimezone, .CurrentEventListMethod, .CurrentEventListSetId, .CurrentEventListConventionId, .CurrentEventListAstroTableId, .CurrentEventListReferenceStationId, .CurrentEventListReferenceBin, .CurrentEventListDatum, .CurrentEventListDatumName, .CurrentEventListDatumKind, .CurrentEventListDatumUncertaintyM, .CurrentEventListTz, .CurrentEventListTzVersion, .CurrentEventListRelease, .CurrentEventListAlgorithm, .CurrentEventListBinNumber, .CurrentEventListOmittedEventTypes]),
                    origin: origin, modelType: .CurrentEventList)
            }, check: {
                guard case .CurrentEventList(let actual) = $0 else { return XCTFail("Wrong native CurrentEventList variant") }
                    XCTAssertEqual(actual.items, currentEvents.items)
                    XCTAssertEqual(actual.stationId, currentEvents.stationId)
                    XCTAssertEqual(actual.timezone, currentEvents.timezone)
                    XCTAssertEqual(actual.method, currentEvents.method)
                    XCTAssertEqual(actual.setId, currentEvents.setId)
                    XCTAssertEqual(actual.conventionId, currentEvents.conventionId)
                    XCTAssertEqual(actual.astroTableId, currentEvents.astroTableId)
                    XCTAssertEqual(actual.referenceStationId, currentEvents.referenceStationId)
                    XCTAssertEqual(actual.referenceBin, currentEvents.referenceBin)
                    XCTAssertEqual(actual.datum, currentEvents.datum)
                    XCTAssertEqual(actual.datumName, currentEvents.datumName)
                    XCTAssertEqual(actual.datumKind, currentEvents.datumKind)
                    XCTAssertEqual(actual.datumUncertaintyM, currentEvents.datumUncertaintyM)
                    XCTAssertEqual(actual.tz, currentEvents.tz)
                    XCTAssertEqual(actual.tzVersion, currentEvents.tzVersion)
                    XCTAssertEqual(actual.release, currentEvents.release)
                    XCTAssertEqual(actual.algorithm, currentEvents.algorithm)
                    XCTAssertEqual(actual.binNumber, currentEvents.binNumber)
                    XCTAssertEqual(actual.omittedEventTypes, currentEvents.omittedEventTypes)
            })

            try m1Record("B07", fixture: "genuine prepared constructor fields DatumInfo", call: {
                try Canonical.materializeTypedModel(rawFields: .DatumInfo(CanonicalDatumInfoFields(setId: datum.setId, zero: datum.zero, zeroName: datum.zeroName, chartDatum: datum.chartDatum, mslOffsetM: datum.mslOffsetM, levels: datum.levels)),
                    fieldContract: CanonicalFieldContract(modelType: .DatumInfo, members: [.DatumInfoSetId, .DatumInfoZero, .DatumInfoZeroName, .DatumInfoChartDatum, .DatumInfoMslOffsetM, .DatumInfoLevels]),
                    origin: origin, modelType: .DatumInfo)
            }, check: {
                guard case .DatumInfo(let actual) = $0 else { return XCTFail("Wrong native DatumInfo variant") }
                    XCTAssertEqual(actual.setId, datum.setId)
                    XCTAssertEqual(actual.zero, datum.zero)
                    XCTAssertEqual(actual.zeroName, datum.zeroName)
                    XCTAssertEqual(actual.chartDatum, datum.chartDatum)
                    XCTAssertEqual(actual.mslOffsetM, datum.mslOffsetM)
                    XCTAssertEqual(actual.levels, datum.levels)
            })

            try m1Record("B07", fixture: "genuine prepared constructor fields DatumLevel", call: {
                try Canonical.materializeTypedModel(rawFields: .DatumLevel(CanonicalDatumLevelFields(key: level.key, valueM: level.valueM, aboveChartM: level.aboveChartM, kind: level.kind, method: level.method, sourceName: level.sourceName, epoch: level.epoch, dataSpan: level.dataSpan, controlStationId: level.controlStationId, controlSetId: level.controlSetId, controlSourceId: level.controlSourceId, uncertaintyM: level.uncertaintyM, uncertaintyBasis: level.uncertaintyBasis, flags: level.flags)),
                    fieldContract: CanonicalFieldContract(modelType: .DatumLevel, members: [.DatumLevelKey, .DatumLevelValueM, .DatumLevelAboveChartM, .DatumLevelKind, .DatumLevelMethod, .DatumLevelSourceName, .DatumLevelEpoch, .DatumLevelDataSpan, .DatumLevelControlStationId, .DatumLevelControlSetId, .DatumLevelControlSourceId, .DatumLevelUncertaintyM, .DatumLevelUncertaintyBasis, .DatumLevelFlags]),
                    origin: origin, modelType: .DatumLevel)
            }, check: {
                guard case .DatumLevel(let actual) = $0 else { return XCTFail("Wrong native DatumLevel variant") }
                    XCTAssertEqual(actual.key, level.key)
                    XCTAssertEqual(actual.valueM, level.valueM)
                    XCTAssertEqual(actual.aboveChartM, level.aboveChartM)
                    XCTAssertEqual(actual.kind, level.kind)
                    XCTAssertEqual(actual.method, level.method)
                    XCTAssertEqual(actual.sourceName, level.sourceName)
                    XCTAssertEqual(actual.epoch, level.epoch)
                    XCTAssertEqual(actual.dataSpan, level.dataSpan)
                    XCTAssertEqual(actual.controlStationId, level.controlStationId)
                    XCTAssertEqual(actual.controlSetId, level.controlSetId)
                    XCTAssertEqual(actual.controlSourceId, level.controlSourceId)
                    XCTAssertEqual(actual.uncertaintyM, level.uncertaintyM)
                    XCTAssertEqual(actual.uncertaintyBasis, level.uncertaintyBasis)
                    XCTAssertEqual(actual.flags, level.flags)
            })

            try m1Record("B07", fixture: "genuine prepared constructor fields Ranges", call: {
                try Canonical.materializeTypedModel(rawFields: .Ranges(CanonicalRangesFields(mn: ranges.mn, gt: ranges.gt, dhq: ranges.dhq, dlq: ranges.dlq)),
                    fieldContract: CanonicalFieldContract(modelType: .Ranges, members: [.RangesMn, .RangesGt, .RangesDhq, .RangesDlq]),
                    origin: origin, modelType: .Ranges)
            }, check: {
                guard case .Ranges(let actual) = $0 else { return XCTFail("Wrong native Ranges variant") }
                    XCTAssertEqual(actual.mn, ranges.mn)
                    XCTAssertEqual(actual.gt, ranges.gt)
                    XCTAssertEqual(actual.dhq, ranges.dhq)
                    XCTAssertEqual(actual.dlq, ranges.dlq)
            })

            try m1Record("B07", fixture: "genuine prepared constructor fields Nearby", call: {
                try Canonical.materializeTypedModel(rawFields: .Nearby(CanonicalNearbyFields(station: nearby.station, distanceKm: nearby.distanceKm)),
                    fieldContract: CanonicalFieldContract(modelType: .Nearby, members: [.NearbyStation, .NearbyDistanceKm]),
                    origin: origin, modelType: .Nearby)
            }, check: {
                guard case .Nearby(let actual) = $0 else { return XCTFail("Wrong native Nearby variant") }
                    XCTAssertEqual(actual.station, nearby.station)
                    XCTAssertEqual(actual.distanceKm, nearby.distanceKm)
            })

            try m1Record("B07", fixture: "genuine prepared constructor fields Stats", call: {
                try Canonical.materializeTypedModel(rawFields: .Stats(CanonicalStatsFields(type: stats.type, kind: stats.kind, country: stats.country, source: stats.source, qcStatus: stats.qcStatus)),
                    fieldContract: CanonicalFieldContract(modelType: .Stats, members: [.StatsType, .StatsKind, .StatsCountry, .StatsSource, .StatsQcStatus]),
                    origin: origin, modelType: .Stats)
            }, check: {
                guard case .Stats(let actual) = $0 else { return XCTFail("Wrong native Stats variant") }
                    XCTAssertEqual(actual.type, stats.type)
                    XCTAssertEqual(actual.kind, stats.kind)
                    XCTAssertEqual(actual.country, stats.country)
                    XCTAssertEqual(actual.source, stats.source)
                    XCTAssertEqual(actual.qcStatus, stats.qcStatus)
            })

    }

    func testM1ReceiverGuardOrder() async throws {
        func sameError(_ actual: OpenTideConstantsError, _ expected: OpenTideConstantsError) throws {
            XCTAssertEqual(actual.code, expected.code)
            XCTAssertEqual(actual.message, expected.message)
            XCTAssertEqual(actual.fields, expected.fields)
            guard actual.code == expected.code, actual.message == expected.message, actual.fields == expected.fields else {
                throw NSError(domain: "M1NativeGuardOrderMismatch", code: 1,
                    userInfo: [NSLocalizedDescriptionKey: "actual \(actual.code): \(actual.message); expected \(expected.code): \(expected.message)"])
            }
        }
        let path = "/Users/jpr5/.local/share/copilotkit/cr/otc-codex-takeover/execution/sdk-core-sync/canonical-behavior/holistic-reset/implementation-plan/M1-SW/public-fixtures/OTC_20261011.json"
        let client = try await OpenTideConstants.open(file: path)
        let release = client.release
        let foreignRelease = try m1Release("conformance/vectors/1.0/vectors-release.json")
        defer { client.close(); foreignRelease.close() }
        let foreign = try foreignRelease.requireStation(stationId: "OTC-V-NOAA-1820000")
        let start = try XCTUnwrap(parseTime("2025-01-01T00:00:00Z"))
        let stop = start.addingTimeInterval(600)
        let request = CanonicalReleaseCurrentsArguments(station: .object(foreign), start: start,
            stop: stop, stepS: 600, binNumber: 0, setId: nil)
        let ownerError = try m1NativeError("invalid_argument") { try release.own(foreign) }
        let nativeOwnerError = try m1NativeError("invalid_argument") {
            try release.currents(station: foreign, start: start, stop: stop, binNumber: 0)
        }
        XCTAssertEqual(nativeOwnerError.message, ownerError.message)
        try m1Record("B01", fixture: "authentic foreign station precedes invalid current bin", call: {
            try m1NativeError(ownerError.code) {
                try Canonical.validateOperationArguments(operation: .currents, arguments: .ReleaseCurrents(request),
                    memberContract: CanonicalMemberContract(member: .ReleaseCurrents, receiver: .release(release),
                        stationStage: try CanonicalStationArgumentStage.prepare(member: .ReleaseCurrents, release: release,
                            request: request.station)))
            }
        }, check: { try sameError($0, nativeOwnerError) })
        let owned = try release.requireStation(stationId: foreign.stationId)
        try release.own(owned)
        let exclusionRequest = CanonicalReleaseHeightsArguments(station: .object(owned), start: start,
            stop: stop, stepS: 600, datum: nil, setId: "selected", offsetId: "selected")
        let exclusion = try m1NativeError("invalid_argument") {
            try release.heights(station: owned, start: start, stop: stop, setId: "selected", offsetId: "selected")
        }
        XCTAssertEqual(exclusion.message, "set_id and offset_id are mutually exclusive")
        try m1Record("B01", fixture: "native resolved owner precedes mutually exclusive options", call: {
            try m1NativeError(exclusion.code) {
                try Canonical.validateOperationArguments(operation: .heights, arguments: .ReleaseHeights(exclusionRequest),
                    memberContract: CanonicalMemberContract(member: .ReleaseHeights, receiver: .release(release),
                        stationStage: try CanonicalStationArgumentStage.prepare(member: .ReleaseHeights, release: release,
                            request: exclusionRequest.station)))
            }
        }, check: { try sameError($0, exclusion) })
        client.close()
        let closed = try m1NativeError("io") { try client.checkOpen() }
        do { _ = try await client.download(release: "bad", to: "", formats: []); XCTFail("Closed download must fail") }
        catch let error as OpenTideConstantsError { XCTAssertEqual(error.message, closed.message); XCTAssertEqual(error.code, closed.code) }
        do { _ = try await client.prune(keep: -1); XCTFail("Closed prune must fail") }
        catch let error as OpenTideConstantsError { XCTAssertEqual(error.message, closed.message); XCTAssertEqual(error.code, closed.code) }
        let closedRequests: [(CanonicalMemberID, CanonicalOperation, CanonicalArguments, CanonicalArgumentReceiver)] = [
            (.ClientDownload, .download, .ClientDownload(CanonicalClientDownloadArguments(release: "bad", to: "", formats: [], overwrite: false)), .client(client)),
            (.ClientPrune, .prune, .ClientPrune(CanonicalClientPruneArguments(keep: -1)), .client(client)),
            (.ReleaseStation, .station, .ReleaseStation(CanonicalReleaseStationArguments(stationId: foreign.stationId)), .release(release)),
            (.ReleaseSearch, .search, .ReleaseSearch(CanonicalReleaseSearchArguments(name: "valid", limit: nil, match: nil, country: nil, type: nil, kind: nil, source: nil, sourceType: nil, includeFlagged: false, includeFallback: false)), .release(release)),
            (.ReleaseNear, .near, .ReleaseNear(CanonicalReleaseNearArguments(lat: 0, lon: 0, radiusKm: 0, limit: nil, country: nil, type: nil, kind: nil, source: nil, sourceType: nil, includeFlagged: false, includeFallback: false)), .release(release))
        ]
        _ = try m1NativeError("io") { try release.station(stationId: foreign.stationId) }
        _ = try m1NativeError("io") { try release.search(name: "valid") }
        _ = try m1NativeError("io") { try release.near(lat: 0, lon: 0, radiusKm: 0) }
        for (member, operation, arguments, receiver) in closedRequests {
            try m1Record("B01", fixture: "original closed native receiver " + member.rawValue, call: {
                try m1NativeError("io") {
                    try Canonical.validateOperationArguments(operation: operation, arguments: arguments,
                        memberContract: CanonicalMemberContract(member: member, receiver: receiver))
                }
            }, check: { try sameError($0, closed) })
        }
        let invalidSearch = try m1NativeError("invalid_argument") { try release.search(name: "", limit: 0, match: "bad") }
        let invalidNear = try m1NativeError("invalid_argument") { try release.near(lat: .nan, lon: .infinity, radiusKm: -1, limit: 0) }
        let primitiveFirst: [(CanonicalMemberID, CanonicalOperation, CanonicalArguments, OpenTideConstantsError)] = [
            (.ReleaseSearch, .search, .ReleaseSearch(CanonicalReleaseSearchArguments(name: "", limit: 0, match: "bad", country: nil, type: nil, kind: nil, source: nil, sourceType: nil, includeFlagged: false, includeFallback: false)), invalidSearch),
            (.ReleaseNear, .near, .ReleaseNear(CanonicalReleaseNearArguments(lat: .nan, lon: .infinity, radiusKm: -1, limit: 0, country: nil, type: nil, kind: nil, source: nil, sourceType: nil, includeFlagged: false, includeFallback: false)), invalidNear)
        ]
        for (member, operation, arguments, expected) in primitiveFirst {
            try m1Record("B01", fixture: "native primitive precedes closed receiver " + member.rawValue, call: {
                try m1NativeError(expected.code) {
                    try Canonical.validateOperationArguments(operation: operation, arguments: arguments,
                        memberContract: CanonicalMemberContract(member: member, receiver: .release(release)))
                }
            }, check: { try sameError($0, expected) })
        }
        XCTAssertEqual(release.datestamp, client.release.datestamp)
        XCTAssertNoThrow(client.close())
    }

    func testM1ClosedPredictionWindows() throws {
        let release = try m1Release("conformance/vectors/1.0/vectors-release.json")
        defer { release.close() }
        let station = try release.requireStation(stationId: "OTC-V-NOAA-1820000")
        let vector = try m1Vector("OTC-V-NOAA-1820000/heights")
        let times = try vector["args"]["times"].array.map(m1Date)
        let first = try XCTUnwrap(times.first)
        let profiles: [(String, [Date])] = [
            ("empty explicit instants", []),
            ("duplicate explicit instants", [first, first]),
            ("ordered corpus explicit instants", times)
        ]
        for (name, instants) in profiles {
            let arguments = CanonicalArguments.ReleaseHeightsAt(CanonicalReleaseHeightsAtArguments(
                station: .object(station), times: instants, datum: "mean_level", setId: nil, offsetId: nil))
            let native = try release.heightsAt(station: station, times: instants, datum: "mean_level")
            let expected = native.items.map { $0.time.timeIntervalSince1970 }
            XCTAssertEqual(expected.count, instants.count)
            try m1Record("B39", fixture: name, call: {
                try Canonical.parsePredictionWindow(timeInputs: arguments, windowInputs: arguments,
                    step: nil, localTimeProfile: CanonicalHeightSeriesToLocalArguments(tz: "station"))
            }, check: { XCTAssertEqual($0, .instants(expected)) })
        }
        let event = try m1Vector("OTC-V-NOAA-1820000/extremes/0")
        let start = try m1Date(event["args"]["start"]), stop = try m1Date(event["args"]["stop"])
        let spans: [(CanonicalArguments, Double?)] = [
            (.ReleaseHeights(CanonicalReleaseHeightsArguments(station: .object(station), start: start,
                stop: stop, stepS: 600, datum: nil, setId: nil, offsetId: nil)), 600),
            (.ReleaseCurrents(CanonicalReleaseCurrentsArguments(station: .id("OTC-V-NOAA-ACT1591"),
                start: start, stop: stop, stepS: 600, binNumber: 1, setId: nil)), 600),
            (.ReleaseExtremes(CanonicalReleaseExtremesArguments(station: .object(station), start: start,
                stop: stop, datum: nil, setId: nil, offsetId: nil)), nil),
            (.ReleaseCurrentEvents(CanonicalReleaseCurrentEventsArguments(station: .id("OTC-V-NOAA-ACT1591"),
                start: start, stop: stop, binNumber: 1, setId: nil)), nil)
        ]
        for (arguments, step) in spans {
            try m1Record("B39", fixture: "unchanged native span " + String(reflecting: arguments), call: {
                try Canonical.parsePredictionWindow(timeInputs: arguments, windowInputs: arguments,
                    step: step, localTimeProfile: CanonicalHeightSeriesToLocalArguments(tz: "station"))
            }, check: { XCTAssertEqual($0, .span(start: start.timeIntervalSince1970,
                stop: stop.timeIntervalSince1970, step: step)) })
        }
        let series = spans[0].0
        for step: Double? in [nil, 0, -1, 0.5] {
            XCTAssertThrowsError(try Canonical.parsePredictionWindow(timeInputs: series, windowInputs: series,
                step: step, localTimeProfile: CanonicalHeightSeriesToLocalArguments(tz: "station"))) {
                XCTAssertEqual(($0 as? OpenTideConstantsError)?.code, "invalid_argument")
            }
        }
    }

        func testM1AllArgumentSelectors() async throws {
            let release = try m1Release("conformance/vectors/1.0/vectors-release.json")
            let client = try await OpenTideConstants.open(file:
                "/Users/jpr5/.local/share/copilotkit/cr/otc-codex-takeover/execution/sdk-core-sync/canonical-behavior/holistic-reset/implementation-plan/M1-SW/public-fixtures/OTC_20261011.json")
            defer { release.close(); client.close() }
            let station = try release.requireStation(stationId: "OTC-V-NOAA-1820000")
            let constants = try XCTUnwrap(station.recommendedSet)
            let constituentName = try XCTUnwrap(constants.constituents.first).name
            let stationName = try XCTUnwrap(station.name)
            let aliasSystem = try XCTUnwrap(station.aliases.keys.sorted().first)
            let aliasId = try XCTUnwrap(station.aliases[aliasSystem]?.first)
            let events = try m1Vector("OTC-V-NOAA-1820000/extremes/0")
            let start = try m1Date(events["args"]["start"]), stop = try m1Date(events["args"]["stop"])
            let heights = try m1Vector("OTC-V-NOAA-1820000/heights")
            let times = try heights["args"]["times"].array.map(m1Date)
            let selectors: [(CanonicalMemberID, CanonicalOperation, CanonicalArguments)] = [
                (.ClientOpen, .open, .ClientOpen(CanonicalClientOpenArguments(release: nil, file: nil, cacheDir: nil, offline: nil, mode: .eager, baseUrl: nil, timeout: nil, proxy: nil, caFile: nil, userAgent: nil, onNetworkError: nil, autoUpdate: false, updateInterval: 86400, logger: nil, verifyOnOpen: false, commercialOnly: false, commercialBasis: "strict", historicalOffsetsPolicy: "fallback"))),
                (.ClientReleases, .releases, .ClientReleases(CanonicalClientReleasesArguments())),
                (.ClientLatest, .latest, .ClientLatest(CanonicalClientLatestArguments())),
                (.ClientCheckForUpdate, .checkForUpdate, .ClientCheckForUpdate(CanonicalClientCheckForUpdateArguments())),
                (.ClientUpdate, .update, .ClientUpdate(CanonicalClientUpdateArguments())),
                (.ClientDownload, .download, .ClientDownload(CanonicalClientDownloadArguments(release: "latest", to: m1Root.appendingPathComponent("unwritten-m1-download").path, formats: [.jsonl], overwrite: false))),
                (.ClientVerify, .verify, .ClientVerify(CanonicalClientVerifyArguments())),
                (.ClientCachedReleases, .cachedReleases, .ClientCachedReleases(CanonicalClientCachedReleasesArguments())),
                (.ClientPrune, .prune, .ClientPrune(CanonicalClientPruneArguments(keep: 3))),
                (.ClientClose, .close, .ClientClose(CanonicalClientCloseArguments())),
                (.ReleaseConvention, .convention, .ReleaseConvention(CanonicalReleaseConventionArguments(conventionId: constants.convention.conventionId))),
                (.ReleaseLicence, .licence, .ReleaseLicence(CanonicalReleaseLicenceArguments(licenceId: constants.licence.licenceId))),
                (.ReleaseStation, .station, .ReleaseStation(CanonicalReleaseStationArguments(stationId: station.stationId))),
                (.ReleaseRequireStation, .requireStation, .ReleaseRequireStation(CanonicalReleaseRequireStationArguments(stationId: station.stationId))),
                (.ReleaseTombstone, .tombstone, .ReleaseTombstone(CanonicalReleaseTombstoneArguments(stationId: station.stationId))),
                (.ReleaseStationByAlias, .stationByAlias, .ReleaseStationByAlias(CanonicalReleaseStationByAliasArguments(system: aliasSystem, aliasId: aliasId))),
                (.ReleaseStations, .stations, .ReleaseStations(CanonicalReleaseStationsArguments(country: nil, type: nil, kind: nil, source: nil, sourceType: nil, includeFlagged: false, includeFallback: false))),
                (.ReleaseIterStations, .iterStations, .ReleaseIterStations(CanonicalReleaseIterStationsArguments(country: nil, type: nil, kind: nil, source: nil, sourceType: nil, includeFlagged: false, includeFallback: false))),
                (.ReleaseSearch, .search, .ReleaseSearch(CanonicalReleaseSearchArguments(name: stationName, limit: nil, match: nil, country: nil, type: nil, kind: nil, source: nil, sourceType: nil, includeFlagged: false, includeFallback: false))),
                (.ReleaseNear, .near, .ReleaseNear(CanonicalReleaseNearArguments(lat: station.lat, lon: station.lon, radiusKm: 0, limit: nil, country: nil, type: nil, kind: nil, source: nil, sourceType: nil, includeFlagged: false, includeFallback: false))),
                (.ReleaseNearest, .nearest, .ReleaseNearest(CanonicalReleaseNearestArguments(lat: station.lat, lon: station.lon, maxKm: nil, country: nil, type: nil, kind: nil, source: nil, sourceType: nil, includeFlagged: false, includeFallback: false))),
                (.ReleaseReferenceStation, .referenceStation, .ReleaseReferenceStation(CanonicalReleaseReferenceStationArguments(station: .object(station)))),
                (.ReleaseSubordinatesOf, .subordinatesOf, .ReleaseSubordinatesOf(CanonicalReleaseSubordinatesOfArguments(station: .object(station)))),
                (.ReleaseAttribution, .attribution, .ReleaseAttribution(CanonicalReleaseAttributionArguments(stations: [station]))),
                (.ReleaseHeights, .heights, .ReleaseHeights(CanonicalReleaseHeightsArguments(station: .object(station), start: start, stop: stop, stepS: 600, datum: nil, setId: nil, offsetId: nil))),
                (.ReleaseHeightsAt, .heightsAt, .ReleaseHeightsAt(CanonicalReleaseHeightsAtArguments(station: .object(station), times: times, datum: nil, setId: nil, offsetId: nil))),
                (.ReleaseExtremes, .extremes, .ReleaseExtremes(CanonicalReleaseExtremesArguments(station: .object(station), start: start, stop: stop, datum: nil, setId: nil, offsetId: nil))),
                (.ReleaseCurrents, .currents, .ReleaseCurrents(CanonicalReleaseCurrentsArguments(station: .object(station), start: start, stop: stop, stepS: 600, binNumber: nil, setId: nil))),
                (.ReleaseCurrentEvents, .currentEvents, .ReleaseCurrentEvents(CanonicalReleaseCurrentEventsArguments(station: .object(station), start: start, stop: stop, binNumber: nil, setId: nil))),
                (.ReleaseDatums, .datums, .ReleaseDatums(CanonicalReleaseDatumsArguments(station: .object(station), setId: nil, allSets: false))),
                (.ReleaseRanges, .ranges, .ReleaseRanges(CanonicalReleaseRangesArguments(station: .object(station), setId: nil))),
                (.ReleaseAstroTable, .astroTable, .ReleaseAstroTable(CanonicalReleaseAstroTableArguments(id: nil))),
                (.StationConstantSets, .constantSets, .StationConstantSets(CanonicalStationConstantSetsArguments(includeNoConstants: false))),
                (.StationConstantSet, .constantSet, .StationConstantSet(CanonicalStationConstantSetArguments(setId: constants.setId))),
                (.ConstantSetConstituent, .constituent, .ConstantSetConstituent(CanonicalConstantSetConstituentArguments(name: constituentName))),
                (.AstroTableEquilibriumArgument, .equilibriumArgument, .AstroTableEquilibriumArgument(CanonicalAstroTableEquilibriumArgumentArguments(name: constituentName, at: start))),
                (.AstroTableNodeFactor, .nodeFactor, .AstroTableNodeFactor(CanonicalAstroTableNodeFactorArguments(name: constituentName, at: start))),
                (.AstroTableEquilibriumForYear, .equilibriumForYear, .AstroTableEquilibriumForYear(CanonicalAstroTableEquilibriumForYearArguments(name: constituentName, year: utcYear(start.timeIntervalSince1970)))),
                (.AstroTableNodeFactorForYear, .nodeFactorForYear, .AstroTableNodeFactorForYear(CanonicalAstroTableNodeFactorForYearArguments(name: constituentName, year: utcYear(start.timeIntervalSince1970)))),
                (.HeightPointLocalDatetime, .toLocal, .HeightPointLocalDatetime(CanonicalHeightPointLocalDatetimeArguments())),
                (.ExtremeLocalDatetime, .toLocal, .ExtremeLocalDatetime(CanonicalExtremeLocalDatetimeArguments())),
                (.CurrentPointLocalDatetime, .toLocal, .CurrentPointLocalDatetime(CanonicalCurrentPointLocalDatetimeArguments())),
                (.CurrentEventLocalDatetime, .toLocal, .CurrentEventLocalDatetime(CanonicalCurrentEventLocalDatetimeArguments())),
                (.HeightSeriesToLocal, .toLocal, .HeightSeriesToLocal(CanonicalHeightSeriesToLocalArguments(tz: "station"))),
                (.ExtremeListToLocal, .toLocal, .ExtremeListToLocal(CanonicalExtremeListToLocalArguments(tz: "station"))),
                (.CurrentSeriesToLocal, .toLocal, .CurrentSeriesToLocal(CanonicalCurrentSeriesToLocalArguments(tz: "station"))),
                (.CurrentEventListToLocal, .toLocal, .CurrentEventListToLocal(CanonicalCurrentEventListToLocalArguments(tz: "station")))
            ]
            XCTAssertEqual(selectors.count, 47)
            for (member, operation, arguments) in selectors {
                var contract = CanonicalMemberContract(member: member)
                if member.rawValue.hasPrefix("Client."), member != .ClientOpen { contract.receiver = .client(client) }
                if member.rawValue.hasPrefix("Release.") { contract.receiver = .release(release) }
                switch arguments {
                case .ReleaseHeights(let value): contract.stationStage = try m1StationStage(member, release: release, request: value.station)
                case .ReleaseHeightsAt(let value): contract.stationStage = try m1StationStage(member, release: release, request: value.station)
                case .ReleaseExtremes(let value): contract.stationStage = try m1StationStage(member, release: release, request: value.station)
                case .ReleaseCurrents(let value): contract.stationStage = try m1StationStage(member, release: release, request: value.station)
                case .ReleaseCurrentEvents(let value): contract.stationStage = try m1StationStage(member, release: release, request: value.station)
                default: break
                }
                try m1Record("B01", fixture: "actual native typed selector " + member.rawValue, call: {
                    try Canonical.validateOperationArguments(operation: operation, arguments: arguments, memberContract: contract)
                }, check: { XCTAssertEqual(String(reflecting: $0), String(reflecting: arguments)) })
            }
        }

    func testM1PreparedNativeModelOwners() throws {
        let path = "/Users/jpr5/.local/share/copilotkit/cr/otc-codex-takeover/execution/sdk-core-sync/proofs/S0/OTC_20261011.json"
        let bytes = try Reader.read(URL(fileURLWithPath: path))
        XCTAssertEqual(SHA256.digest(bytes), "77e40e2da9ff24a7357f54fdf75ec7ee7fb65b2856549cece7e076de95c58a7d")
        let release = try Reader.load(URL(fileURLWithPath: path), mode: .eager,
            commercialOnly: false, commercialBasis: "strict", historicalOffsetsPolicy: "fallback")
        defer { release.close() }
        let stations = try release.stations(includeFlagged: true, includeFallback: true)
        let station = try XCTUnwrap(stations.first { !$0.sourceRecords.isEmpty && !$0.constantSets(includeNoConstants: true).isEmpty })
        let origin = try m1Origin(station)
        let set = try XCTUnwrap(station.constantSets(includeNoConstants: true).first)
        let source = try XCTUnwrap(station.sourceRecords.first)
        let build = try XCTUnwrap(set.provenance.build)
        let fallback = try XCTUnwrap(stations.flatMap { $0.constantSets(includeNoConstants: true) }.compactMap(\.fallback).first)
        let offsets = try XCTUnwrap(stations.compactMap(\.subordinateOffsets).first { $0.vintage != nil && $0.provenance != nil })
        let vintage = try XCTUnwrap(offsets.vintage), provenance = try XCTUnwrap(offsets.provenance)
        let table = try XCTUnwrap(release.astroTable())
        let rows: [(CanonicalModelType, JSONValue, [CanonicalMemberID])] = [
            (.ConstantSet, set.raw, [.ConstantSetSetId, .ConstantSetRaw]),
            (.SourceRecord, source.raw, [.SourceRecordSourceRecordId, .SourceRecordRaw]),
            (.ProvenanceBuild, build.raw, [.ProvenanceBuildBuildCommit]),
            (.Fallback, fallback.raw, [.FallbackReason, .FallbackRaw]),
            (.HistoricalOffsetVintage, vintage.raw, [.HistoricalOffsetVintagePublicationYear]),
            (.HistoricalOffsetProvenance, provenance.raw, [.HistoricalOffsetProvenanceBook]),
            (.AstroTable, table.raw, [.AstroTableValidRange])
        ]
        for (type, raw, members) in rows {
            let context = CanonicalMaterializationContext(release: release, kind: station.kind,
                recommendation: station.recommendedSet?.setId, setValidation: set.validation, station: station)
            try m1Record("B07", fixture: "actual core prepared model " + type.rawValue, call: {
                try Canonical.materializeTypedModel(rawFields: .sourceJSON(raw),
                    fieldContract: CanonicalFieldContract(modelType: type, members: members, materialization: context),
                    origin: origin, modelType: type)
            }, check: { model in
                switch (type, model) {
                case (.ConstantSet, .ConstantSet(let value)): XCTAssertEqual(value, set)
                case (.SourceRecord, .SourceRecord(let value)): XCTAssertEqual(value, source)
                case (.ProvenanceBuild, .ProvenanceBuild(let value)): XCTAssertEqual(value, build)
                case (.Fallback, .Fallback(let value)): XCTAssertEqual(value, fallback)
                case (.HistoricalOffsetVintage, .HistoricalOffsetVintage(let value)): XCTAssertEqual(value, vintage)
                case (.HistoricalOffsetProvenance, .HistoricalOffsetProvenance(let value)): XCTAssertEqual(value, provenance)
                case (.AstroTable, .AstroTable(let value)): XCTAssertEqual(value, table)
                default: XCTFail("Wrong exact selected model or missing native owner")
                }
            })
        }
    }

    func testM1SelectedMembersAndRawModels() async throws {
        let good = try m1Release("conformance/fixtures/good/OTC_20991231.2.json")
        defer { good.close() }
        let station = try good.requireStation(stationId: "OTC-T-0001")
        let actualOrigin = try m1Origin(station)
        let nativeQueryFailure = try m1NativeError("invalid_argument") { try good.search(name: " ", limit: 0, match: "bad") }
        let query = CanonicalReleaseSearchArguments(name: " ", limit: 0, match: "bad", country: nil, type: nil,
            kind: nil, source: nil, sourceType: nil, includeFlagged: false, includeFallback: false)
        try m1Record("B01", fixture: "actual Release.search first native guard", call: {
            try m1NativeError("invalid_argument") { try Canonical.validateOperationArguments(operation: .search,
                arguments: .ReleaseSearch(query), memberContract: CanonicalMemberContract(member: .ReleaseSearch)) }
        }, check: { XCTAssertEqual($0.message, nativeQueryFailure.message) })
        let nativeNearFailure = try m1NativeError("invalid_argument") { try good.near(lat: 91, lon: 0, radiusKm: 1, limit: 0) }
        let near = CanonicalReleaseNearArguments(lat: 91, lon: 0, radiusKm: 1, limit: 0, country: nil, type: nil,
            kind: nil, source: nil, sourceType: nil, includeFlagged: false, includeFallback: false)
        try m1Record("B01", fixture: "actual Release.near first native guard", call: {
            try m1NativeError("invalid_argument") { try Canonical.validateOperationArguments(operation: .near,
                arguments: .ReleaseNear(near), memberContract: CanonicalMemberContract(member: .ReleaseNear)) }
        }, check: { XCTAssertEqual($0.message, nativeNearFailure.message) })
        let nearest = CanonicalReleaseNearestArguments(lat: 91, lon: 0, maxKm: 1, country: nil, type: nil,
            kind: nil, source: nil, sourceType: nil, includeFlagged: false, includeFallback: false)
        let nativeNearestFailure = try m1NativeError("invalid_argument") { try good.nearest(lat: 91, lon: 0, maxKm: 1) }
        try m1Record("B01", fixture: "actual Release.nearest delegated guard", call: {
            try m1NativeError("invalid_argument") { try Canonical.validateOperationArguments(operation: .nearest,
                arguments: .ReleaseNearest(nearest), memberContract: CanonicalMemberContract(member: .ReleaseNearest)) }
        }, check: { XCTAssertEqual($0.message, nativeNearestFailure.message) })
        let client = try await OpenTideConstants.open(file: m1Root.appendingPathComponent("conformance/fixtures/good/OTC_20991231.2.json").path)
        defer { client.close() }
        let download = CanonicalClientDownloadArguments(release: good.datestamp, to: "", formats: [.jsonl], overwrite: false)
        let nativeDownloadFailure: OpenTideConstantsError
        do { _ = try await client.download(release: good.datestamp, to: ""); return XCTFail("Native empty download destination accepted") }
        catch let error as OpenTideConstantsError { nativeDownloadFailure = error }
        try m1Record("B01", fixture: "actual Client.download before IO guard", call: {
            try m1NativeError("invalid_argument") { try Canonical.validateOperationArguments(operation: .download,
                arguments: .ClientDownload(download), memberContract: CanonicalMemberContract(member: .ClientDownload, receiver: .client(client))) }
        }, check: { XCTAssertEqual($0.message, nativeDownloadFailure.message) })
        let nativePruneFailure: OpenTideConstantsError
        do { _ = try await client.prune(keep: -1); return XCTFail("Native negative keep accepted") }
        catch let error as OpenTideConstantsError { nativePruneFailure = error }
        try m1Record("B01", fixture: "actual Client.prune before cache guard", call: {
            try m1NativeError("invalid_argument") { try Canonical.validateOperationArguments(operation: .prune,
                arguments: .ClientPrune(CanonicalClientPruneArguments(keep: -1)), memberContract: CanonicalMemberContract(member: .ClientPrune, receiver: .client(client))) }
        }, check: { XCTAssertEqual($0.message, nativePruneFailure.message) })

        let set = try XCTUnwrap(station.constantSets(includeNoConstants: true).first)
        let other = try XCTUnwrap(station.constantSets(includeNoConstants: true).first { $0.timeBase != nil })
        let catalogue = try m1Document("conformance/fixtures/good/OTC_index.json")
        let releaseInfo = ReleaseInfo(try XCTUnwrap(catalogue["releases"].array.first))
        let tombstone = try XCTUnwrap(good.tombstone(stationId: "OTC-T-0021"))
        let offsets = try XCTUnwrap(good.requireStation(stationId: "OTC-T-0003").subordinateOffsets)
        let rows: [(CanonicalModelType, JSONValue, [CanonicalMemberID])] = [
            (.ReleaseInfo, releaseInfo.raw, [.ReleaseInfoDatestamp, .ReleaseInfoFiles]),
            (.FileInfo, try XCTUnwrap(releaseInfo.files.first).raw, [.FileInfoName, .FileInfoSha256]),
            (.Tombstone, tombstone.raw, [.TombstoneStationId, .TombstoneRaw]),
            (.SubordinateOffsets, offsets.raw, [.SubordinateOffsetsReferenceStationId]),
            (.Constituent, try XCTUnwrap(set.constituents.first).raw, [.ConstituentName, .ConstituentRaw]),
            (.Convention, set.convention.raw, [.ConventionConventionId, .ConventionRaw]),
            (.Licence, set.licence.raw, [.LicenceLicenceId, .LicenceRaw]),
            (.Provenance, set.provenance.raw, [.ProvenanceRaw]),
            (.TimeBase, try XCTUnwrap(other.timeBase).raw, [.TimeBaseCode]),
            (.RecordSpan, try XCTUnwrap(set.recordSpan).raw, [.RecordSpanStart]),
            (.Datum, try XCTUnwrap(set.datum).raw, [.DatumMslOffsetM]),
            (.Validation, try XCTUnwrap(station.validation.first).raw, [.ValidationSetId]),
            (.DroppedConstituent, try XCTUnwrap(other.droppedConstituents.first).raw, [.DroppedConstituentName]),
            (.QcFlag, try XCTUnwrap(other.qcFlags.first).raw, [.QcFlagFlag])
        ]
        for (type, raw, members) in rows {
            try m1Record("B07", fixture: "authenticated good loaded native " + type.rawValue, call: {
                try Canonical.materializeTypedModel(rawFields: .sourceJSON(raw),
                    fieldContract: CanonicalFieldContract(modelType: type, members: members), origin: actualOrigin, modelType: type)
            }, check: { model in
                let result: JSONValue
                switch (type, model) {
                case (.ReleaseInfo, .ReleaseInfo(let value)): result = value.raw
                case (.FileInfo, .FileInfo(let value)): result = value.raw
                case (.Tombstone, .Tombstone(let value)): result = value.raw
                case (.SubordinateOffsets, .SubordinateOffsets(let value)): result = value.raw
                case (.Constituent, .Constituent(let value)): result = value.raw
                case (.Convention, .Convention(let value)): result = value.raw
                case (.Licence, .Licence(let value)): result = value.raw
                case (.Provenance, .Provenance(let value)): result = value.raw
                case (.TimeBase, .TimeBase(let value)): result = value.raw
                case (.RecordSpan, .RecordSpan(let value)): result = value.raw
                case (.Datum, .Datum(let value)): result = value.raw
                case (.Validation, .Validation(let value)): result = value.raw
                case (.DroppedConstituent, .DroppedConstituent(let value)): result = value.raw
                case (.QcFlag, .QcFlag(let value)): result = value.raw
                default: return XCTFail("Wrong selected native model")
                }
                XCTAssertEqual(result, raw)
            })
        }
    }

    private var m1Root: URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
    }

    private func m1Document(_ relative: String) throws -> JSONValue {
        try JSONValue.parse(Data(contentsOf: m1Root.appendingPathComponent(relative)))
    }

    private func m1Release(_ relative: String) throws -> Release {
        try Reader.load(m1Root.appendingPathComponent(relative), mode: .eager,
            commercialOnly: false, commercialBasis: "strict", historicalOffsetsPolicy: "fallback")
    }

    private func m1Options(release: String? = nil, file: String? = nil,
        offline: Bool? = nil) -> CanonicalEffectiveOptions {
        CanonicalEffectiveOptions(release: release, file: file, cacheDir: nil,
            offline: offline, mode: .eager, baseUrl: nil, timeout: nil, proxy: nil,
            caFile: nil, userAgent: nil, onNetworkError: nil, autoUpdate: false,
            updateInterval: 86400, logger: nil, verifyOnOpen: false,
            commercialOnly: false, commercialBasis: "strict", historicalOffsetsPolicy: "fallback")
    }

    private func m1OpenArguments(_ value: CanonicalEffectiveOptions) -> CanonicalArguments {
        .ClientOpen(CanonicalClientOpenArguments(release: value.release, file: value.file,
            cacheDir: value.cacheDir, offline: value.offline, mode: value.mode,
            baseUrl: value.baseUrl, timeout: value.timeout, proxy: value.proxy,
            caFile: value.caFile, userAgent: value.userAgent, onNetworkError: value.onNetworkError,
            autoUpdate: value.autoUpdate, updateInterval: value.updateInterval, logger: value.logger,
            verifyOnOpen: value.verifyOnOpen, commercialOnly: value.commercialOnly,
            commercialBasis: value.commercialBasis, historicalOffsetsPolicy: value.historicalOffsetsPolicy))
    }

    private func m1Origin(_ station: Station) throws -> UUID {
        // Baseline diagnostic access to the ACTUAL opaque producing identity.
        // Never used by production and never substituted with a fabricated UUID.
        for child in Mirror(reflecting: station).children where child.label == "originToken" {
            if let value = child.value as? UUID { return value }
            if let value = Mirror(reflecting: child.value).children.first?.value as? UUID { return value }
        }
        return try XCTUnwrap(Optional<UUID>.none, "Actual loaded station has no native producing identity")
    }

    private func m1StationStage(_ member: CanonicalMemberID, release: Release,
        request: CanonicalStationRequest) throws -> CanonicalStationArgumentStage {
        try CanonicalStationArgumentStage.prepare(member: member, release: release, request: request)
    }

    private func m1Model(_ context: PredictionContext, release: Release) -> CanonicalPredictionModel {
        CanonicalPredictionModel(station: context.station, releaseView: release,
            constantSet: context.constants, convention: context.constants.convention,
            astroTable: context.table.raw,
            requiredConstituents: context.currentBin.isNull
                ? context.constants.raw["constituents"].array : context.currentBin["constituents"].array,
            referenceBin: context.referenceBin ?? context.binNumber,
            meanTerm: context.total?.mean ?? 0, datumSource: context.constants.raw["datum"],
            nativeContext: context)
    }

    private func m1Vector(_ id: String) throws -> JSONValue {
        try XCTUnwrap(m1Document("conformance/vectors/1.0/vectors.json")["vectors"].array.first { $0["id"].string == id })
    }

    private func m1Date(_ value: JSONValue) throws -> Date {
        try XCTUnwrap(parseTime(value.string))
    }

    private func m1Record<Value>(_ id: String, fixture: String,
        call: () throws -> Value, check: (Value) throws -> Void) throws {
        let failures = testRun?.failureCount ?? 0
        var status = "GREEN"
        var detail = "actual native value and expected control assertions"
        do {
            try check(call())
            if (testRun?.failureCount ?? 0) > failures { status = "RED_VALUE" }
        } catch CanonicalUnimplemented.behavior(let target) {
            status = "RED_BODY_INCOMPLETE"
            detail = "CanonicalUnimplemented.behavior(\"\(target)\")"
            XCTFail("\(id): actual native call on \(fixture) still refuses: \(detail)")
        } catch {
            status = "RED_ERROR"
            detail = String(reflecting: error)
            XCTFail("\(id): actual native call failed: \(error)")
        }
        let event: JSONValue = .object(["id": .string(id), "fixture": .string(fixture),
            "status": .string(status), "detail": .string(detail)])
        let bytes = try event.data() + Data([10])
        print("M1_SW " + String(decoding: bytes, as: UTF8.self))
        if let path = ProcessInfo.processInfo.environment["OTC_M1_SW_EVENTS"] {
            if !FileManager.default.fileExists(atPath: path) {
                XCTAssertTrue(FileManager.default.createFile(atPath: path, contents: nil))
            }
            let handle = try FileHandle(forWritingTo: URL(fileURLWithPath: path))
            defer { try? handle.close() }
            try handle.seekToEnd(); try handle.write(contentsOf: bytes)
        }
    }

    private func m1NativeError<Value>(_ code: String, _ call: () throws -> Value) throws -> OpenTideConstantsError {
        do {
            _ = try call()
            XCTFail("Expected actual native \(code) refusal")
            throw NSError(domain: "M1MissingExpectedNativeRefusal", code: 1)
        } catch let error as OpenTideConstantsError {
            XCTAssertEqual(error.code, code)
            return error
        }
    }

    func testM1RealLeafCells() async throws {
        let goodPath = "conformance/fixtures/good/OTC_20991231.2.json"
        let good = try m1Release(goodPath)
        let vectors = try m1Release("conformance/vectors/1.0/vectors-release.json")
        let prediction = try m1Release("conformance/fixtures/predict/OTC_20991231.7.json")
        defer { good.close(); vectors.close(); prediction.close() }
        let goodStation = try good.requireStation(stationId: "OTC-T-0001")
        let source = try XCTUnwrap(m1Document(goodPath)["stations"].array.first { $0["station_id"].string == goodStation.stationId })
        XCTAssertEqual(goodStation.raw, source)
        let actualOrigin = try m1Origin(goodStation)
        let path = m1Root.appendingPathComponent(goodPath).path
        let nativeFailure: OpenTideConstantsError
        do {
            _ = try await OpenTideConstants.open(file: path, offline: true)
            return XCTFail("Authentic file+offline case must refuse before acquisition")
        } catch let error as OpenTideConstantsError {
            XCTAssertEqual(error.code, "invalid_argument")
            nativeFailure = error
        }
        let failure = CanonicalCanonicalError(code: .invalidArgument,
            structuredFields: .object(nativeFailure.fields), cause: nativeFailure)
        for options in [m1Options(file: path, offline: true), m1Options(release: "20991231.2", file: path)] {
            try m1Record("B01", fixture: "rules/pk07/file-offline-or-release", call: {
                try m1NativeError("invalid_argument") {
                    try Canonical.validateOperationArguments(operation: .open,
                        arguments: m1OpenArguments(options), memberContract: CanonicalMemberContract(member: .ClientOpen))
                }
            }, check: { XCTAssertEqual($0.code, nativeFailure.code) })
        }
        try m1Record("B02", fixture: "net/offline-env-wins-over-option", call: {
            try Canonical.resolveEffectiveOptions(explicitOptions: m1Options(offline: false),
                environment: ["OPENTIDECONSTANTS_OFFLINE": "On"], platformDefaults: m1Options())
        }, check: { XCTAssertEqual($0.offline, true); XCTAssertEqual($0.mode, .eager) })
        try m1Record("B03", fixture: "rules/pk07/file-offline actual native cause", call: {
            try Canonical.selectCanonicalError(operation: .open, orderedFailures: [failure], cause: nativeFailure)
        }, check: {
            XCTAssertEqual($0.code, failure.code); XCTAssertEqual($0.structuredFields, failure.structuredFields)
            XCTAssertEqual(($0.cause as? OpenTideConstantsError)?.message, nativeFailure.message)
        })
        try m1Record("B04", fixture: "rules/pk07/file-offline error-only", call: {
            try m1NativeError("invalid_argument") {
                try Canonical.translateNativeBinding(canonicalResult: nil, canonicalError: failure, nativeProfile: .swift)
            }
        }, check: { XCTAssertEqual($0.message, nativeFailure.message); XCTAssertEqual($0.fields, nativeFailure.fields) })
        try m1Record("B04", fixture: "actual absent station nullable return", call: {
            let actual = try good.station(stationId: "not-a-station")
            return try Canonical.translateNativeBinding(canonicalResult: .ReleaseStation(actual), canonicalError: nil, nativeProfile: .swift)
        }, check: { guard case .ReleaseStation(let value) = $0 else { return XCTFail("Wrong exact member result") }; XCTAssertNil(value) })
        let fields = CanonicalFieldContract(modelType: .Station,
            members: [.StationStationId, .StationName, .StationLat, .StationRaw],
            materialization: CanonicalMaterializationContext(release: good,
                kind: goodStation.kind, recommendation: goodStation.recommendedSet?.setId))
        try m1Record("B07", fixture: goodPath + " OTC-T-0001", call: {
            try Canonical.materializeTypedModel(rawFields: .sourceJSON(source), fieldContract: fields,
                origin: actualOrigin, modelType: .Station)
        }, check: {
            guard case .Station(let station) = $0 else { return XCTFail("Wrong typed model") }
            XCTAssertEqual(station, goodStation); XCTAssertEqual(station.raw, source)
            XCTAssertTrue(station.hasOrigin(actualOrigin)); try good.own(station)
        })
        try m1Record("B08.raw", fixture: goodPath + " actual source row", call: {
            try Canonical.retainRawSourceRecord(sourceRecord: goodStation.raw, nativeProfile: .swift)
        }, check: { XCTAssertEqual($0, source) })
        var row: JSONValue?
        var span: CanonicalSourceByteSpan?
        try eachLine(m1Root.appendingPathComponent("conformance/fixtures/good/OTC_20991231.2.jsonl")) { bytes, offset in
            let value = try JSONValue.parse(bytes)
            if value["station_id"].string == goodStation.stationId {
                row = value; span = CanonicalSourceByteSpan(offsetBytes: Int64(offset), lengthBytes: Int64(bytes.count))
            }
        }
        let actualRow = try XCTUnwrap(row), actualSpan = try XCTUnwrap(span)
        try m1Record("B24", fixture: "actual OTC-T-0001 JSONL bytes/span", call: {
            try Canonical.projectStationIndex(stationSourceRow: actualRow, sourceByteSpan: actualSpan,
                projectionContract: CanonicalProjectionRules(scalarMembers: [.StationStationId, .StationName],
                    modelType: .Station, preserveUnknownSourceFields: true))
        }, check: {
            let native = IndexEntry.make(actualRow, offset: UInt64(actualSpan.offsetBytes), length: Int(actualSpan.lengthBytes))
            XCTAssertEqual($0.stationId, native.id); XCTAssertEqual($0.nameFolded, native.summary["name_folded"].string)
            XCTAssertEqual($0.offset, actualSpan.offsetBytes); XCTAssertEqual($0.length, actualSpan.lengthBytes)
            XCTAssertEqual($0.sets.count, native.sets.count)
        })
        let golden = try m1Document("conformance/canonical/cache-golden.json")
        for specimen in golden["cases"].array {
            let input: JSONValue
            if let hex = specimen["binary64_hex"].string {
                input = .number(Double(bitPattern: try XCTUnwrap(UInt64(hex, radix: 16))))
            } else { input = specimen["input"] }
            try m1Record("B28", fixture: "cache-golden/" + (specimen["id"].string ?? ""), call: {
                try Canonical.encodeCacheJson(cacheDocument: .pointerOrCatalogue(input))
            }, check: { XCTAssertEqual(String(decoding: $0, as: UTF8.self), specimen["expected"].string) })
        }
        let tideVector = try m1Vector("OTC-V-NOAA-1820000/extremes/0")
        let currentVector = try m1Vector("OTC-V-NOAA-ACT1591/events/1/0")
        let tideStart = try m1Date(tideVector["args"]["start"]), tideStop = try m1Date(tideVector["args"]["stop"])
        let tideStation = try vectors.requireStation(stationId: "OTC-V-NOAA-1820000")
        let tideContext = try Predict.context(vectors, supplied: tideStation, quantity: .waterLevel, setId: nil, datum: "mean_level")
        let tideModel = m1Model(tideContext, release: vectors)
        let emptyStart = try XCTUnwrap(parseTime("2031-01-01T00:00:00Z"))
        let empty = CanonicalReleaseExtremesArguments(station: .id("OTC-P-0001"), start: emptyStart,
            stop: emptyStart, datum: nil, setId: nil, offsetId: nil)
        try m1Record("B39", fixture: "predict-empty-window-out-of-range", call: {
            try Canonical.parsePredictionWindow(timeInputs: .ReleaseExtremes(empty), windowInputs: .ReleaseExtremes(empty),
                step: nil, localTimeProfile: CanonicalHeightSeriesToLocalArguments(tz: "station"))
        }, check: { XCTAssertEqual($0, .span(start: emptyStart.timeIntervalSince1970, stop: emptyStart.timeIntervalSince1970, step: nil)) })
        let astroStation = try prediction.requireStation(stationId: "OTC-P-0001")
        let astroContext = try Predict.context(prediction, supplied: astroStation, quantity: .waterLevel, setId: nil)
        let astroModel = m1Model(astroContext, release: prediction)
        let astroInstant = try XCTUnwrap(parseTime("2015-06-01T12:34:56Z"))
        try m1Record("B41", fixture: "predict-astro-values exact native table/year", call: {
            try Canonical.evaluateAstronomy(selectedPredictionModel: astroModel, utcInstant: astroInstant.timeIntervalSince1970)
        }, check: { XCTAssertEqual($0.utcYear, 2015); XCTAssertTrue($0.epochHours.isFinite); XCTAssertEqual($0.constituentTerms.count, astroModel.requiredConstituents.count) })
        let heights = try m1Vector("OTC-V-NOAA-1820000/heights")
        let instants = try heights["args"]["times"].array.map { try m1Date($0).timeIntervalSince1970 }
        try m1Record("B42", fixture: "OTC-V-NOAA-1820000/heights", call: {
            try Canonical.evaluateHarmonicHeight(selectedPredictionModel: tideModel, predictionInstants: instants, requestedDatum: "mean_level")
        }, check: {
            let expected = heights["expect"]["prediction"]["items"].array
            XCTAssertEqual($0.items.count, expected.count)
            for (actual, wanted) in zip($0.items, expected) {
                XCTAssertEqual(actual.time, try m1Date(wanted["time"]))
                XCTAssertEqual(actual.heightM, try XCTUnwrap(wanted["height_m"].number), accuracy: 1e-5)
            }
        })
        let firstOracle = try m1Date(try XCTUnwrap(tideVector["expect"]["prediction"]["items"].array.first)["time"]).timeIntervalSince1970
        let boundary = CanonicalPredictionWindow.span(start: firstOracle + 1, stop: firstOracle + 3601, step: nil)
        try m1Record("B43.roots", fixture: "authentic tide model/oracle-derived boundary window", call: {
            try Canonical.findUnroundedTideEvents(selectedPredictionModel: tideModel, predictionWindow: boundary)
        }, check: {
            XCTAssertFalse($0.isEmpty)
            XCTAssertTrue($0.contains { floor($0.rootSeconds + 0.5) < firstOracle + 1 })
            XCTAssertTrue($0.allSatisfy { $0.rootSeconds.isFinite && $0.heightM.isFinite })
        })
        let currentStation = try vectors.requireStation(stationId: "OTC-V-NOAA-ACT1591")
        let currentContext = try Predict.context(vectors, supplied: currentStation, quantity: .current, setId: nil, binNumber: 1)
        let currentModel = m1Model(currentContext, release: vectors)
        let currentStart = try m1Date(currentVector["args"]["start"]), currentStop = try m1Date(currentVector["args"]["stop"])
        let request = CanonicalCurrentRequest.ReleaseCurrentEvents(CanonicalReleaseCurrentEventsArguments(station: .object(currentStation),
            start: currentStart, stop: currentStop, binNumber: 1, setId: nil))
        try m1Record("B44.roots", fixture: "OTC-V-NOAA-ACT1591/events/1/0 actual selected reference bin", call: {
            try Canonical.findUnroundedCurrentEvents(selectedPredictionModel: currentModel,
                predictionWindow: CanonicalPredictionWindow.span(start: currentStart.timeIntervalSince1970, stop: currentStop.timeIntervalSince1970, step: nil),
                currentRequest: request)
        }, check: {
            XCTAssertFalse($0.isEmpty); XCTAssertTrue($0.allSatisfy { $0.velocityMS.isFinite && $0.rootSeconds.isFinite })
            XCTAssertTrue($0.contains { $0.eventType == .slackBeforeFlood || $0.eventType == .slackBeforeEbb })
        })
        // Keep authentic public model/source controls distinct from private results.
        XCTAssertEqual(try vectors.extremes(station: tideStation, start: tideStart, stop: tideStop, datum: "mean_level").items.count,
            tideVector["expect"]["prediction"]["items"].array.count)
    }
}
