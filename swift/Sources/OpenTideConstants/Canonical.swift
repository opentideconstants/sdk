import Foundation

internal enum CanonicalUnimplemented: Error, Equatable {
    case behavior(String)
}

// These isolated entries refuse before effects. They are inactive from public routes.
internal enum Canonical {
    private static func projectIndexSummary(_ row: JSONValue) throws -> CanonicalStreamIndexStation {
        guard let id = row["station_id"].string, let offset = row["offset"].integer, let length = row["length"].integer else {
            throw OpenTideConstantsError.invalidRelease("stale index span")
        }
        return CanonicalStreamIndexStation(stationId: id, status: row["status"].string ?? "active",
            name: row["name"].string, nameFolded: row["name_folded"].string, country: row["country"].string,
            type: row["type"].string, kind: row["kind"].string, referenceStationId: row["reference_station_id"].string,
            offsetsLicenceId: row["offsets_licence_id"].string, recommendedSetId: row["recommended_set_id"].string,
            lat: row["lat"].number, lon: row["lon"].number, offset: offset, length: length,
            aliases: row["aliases"].object.mapValues { $0.array.compactMap(\.string) },
            sets: row["sets"].array.map { set in
                CanonicalStreamIndexSet(setId: set["set_id"].string, source: set["source"].string,
                    sourceType: set["source_type"].string, quantity: set["quantity"].string,
                    qcStatus: set["qc_status"].string, conventionId: set["convention_id"].string,
                    licenceId: set["licence_id"].string, constituents: set["constituents"].array.compactMap(\.string),
                    fallback: set["fallback"].isNull ? nil:Fallback(set["fallback"]),
                    currentBins: set["current_bins"].array.compactMap(\.integer))
            }, subordinateOffsets: row["subordinate_offsets"].isNull ? nil:SubordinateOffsets(row["subordinate_offsets"]),
            currentOffsets: row["current_offsets"].array.map { value in
                CanonicalStreamIndexCurrentOffset(bin: value["bin"].integer!, referenceBin: value["reference_bin"].integer!,
                    referenceStationId: value["reference_station_id"].string, licenceId: value["licence_id"].string)
            })
    }

    private static func cacheIndexStation(_ station: CanonicalStreamIndexStation) -> JSONValue {
        func text(_ value: String?) -> JSONValue { value.map(JSONValue.string) ?? .null }
        func number(_ value: Double?) -> JSONValue { value.map(JSONValue.number) ?? .null }
        return .object(["station_id": .string(station.stationId), "status": .string(station.status),
            "name": text(station.name), "name_folded": text(station.nameFolded), "country": text(station.country),
            "type": text(station.type), "kind": text(station.kind), "reference_station_id": text(station.referenceStationId),
            "offsets_licence_id": text(station.offsetsLicenceId), "recommended_set_id": text(station.recommendedSetId),
            "lat": number(station.lat), "lon": number(station.lon), "offset": .integer(station.offset), "length": .integer(station.length),
            "aliases": .object(station.aliases.mapValues { .array($0.map(JSONValue.string)) }),
            "sets": .array(station.sets.map { set in
                .object(["set_id": text(set.setId), "source": text(set.source), "source_type": text(set.sourceType),
                    "quantity": text(set.quantity), "qc_status": text(set.qcStatus), "convention_id": text(set.conventionId),
                    "licence_id": text(set.licenceId), "constituents": .array(set.constituents.map(JSONValue.string)),
                    "fallback": set.fallback?.raw ?? .null, "current_bins": .array(set.currentBins.map(JSONValue.integer))])
            }), "subordinate_offsets": station.subordinateOffsets?.raw ?? .null,
            "current_offsets": .array(station.currentOffsets.map { offset in
                .object(["bin": .integer(offset.bin), "reference_bin": .integer(offset.referenceBin),
                    "reference_station_id": text(offset.referenceStationId), "licence_id": text(offset.licenceId)])
            })])
    }

    private static func cacheIndexDocument(_ index: CanonicalStreamIndex) -> JSONValue {
        .object(["index_version": .integer(index.indexVersion), "discovery_index_version": .integer(index.discoveryIndexVersion),
            "datestamp": .string(index.datestamp), "jsonl": .string(index.jsonl), "jsonl_sha256": .string(index.jsonlSha256),
            "jsonl_size": .integer(index.jsonlSize), "by": .string(index.by), "stations": .array(index.stations.map(cacheIndexStation))])
    }

    // B01 validate_operation_arguments — native typed member guards.
    internal static func validateOperationArguments(operation: CanonicalOperation, arguments: CanonicalArguments, memberContract: CanonicalMemberContract) throws -> CanonicalValidatedArguments {
        // Closed typed records enforce required, nullable and primitive parameter shapes.
        // Only the selected member pair is valid; owners and derived values are later leaves.
        func client() throws -> OpenTideConstants {
            guard case .client(let receiver) = memberContract.receiver else { throw CanonicalUnimplemented.behavior("B01") }
            return receiver
        }
        func release() throws -> Release {
            guard case .release(let receiver) = memberContract.receiver else { throw CanonicalUnimplemented.behavior("B01") }
            return receiver
        }
        func stationPhase(_ request: CanonicalStationRequest) throws {
            let receiver = try release()
            guard let stage = memberContract.stationStage, stage.member == memberContract.member,
                stage.release === receiver else { throw CanonicalUnimplemented.behavior("B08.origin/B29") }
            switch (request, stage.request) {
            case (.id(let requested), .id(let prepared)) where requested == prepared: break
            case (.object(let requested), .object(let prepared))
                where requested.originToken == prepared.originToken && requested.raw == prepared.raw: break
            default: throw CanonicalUnimplemented.behavior("B08.origin/B29")
            }
            switch stage.outcome {
            case .failed(let error): throw error
            case .resolved(let station):
                let id: String
                switch request { case .id(let value): id = value; case .object(let value): id = value.stationId }
                guard station.stationId == id else {
                    throw CanonicalUnimplemented.behavior("B08.origin/B29")
                }
            }
        }
        switch (operation, memberContract.member, arguments) {
        case (.open, .ClientOpen, .ClientOpen(let request)):
            _ = try OpenTideConstants.validatedOpenOptions(request, environment: ProcessInfo.processInfo.environment)
        case (.releases, .ClientReleases, .ClientReleases(_)):
            try client().checkOpen()
        case (.latest, .ClientLatest, .ClientLatest(_)):
            try client().checkOpen()
        case (.checkForUpdate, .ClientCheckForUpdate, .ClientCheckForUpdate(_)):
            try client().checkOpen()
        case (.update, .ClientUpdate, .ClientUpdate(_)):
            try client().checkOpen()
        case (.download, .ClientDownload, .ClientDownload(let request)):
            try client().checkOpen()
            try OpenTideConstants.validateDownloadArguments(release: request.release, to: request.to, formats: request.formats)
        case (.verify, .ClientVerify, .ClientVerify(_)):
            try client().checkOpen()
        case (.cachedReleases, .ClientCachedReleases, .ClientCachedReleases(_)):
            try client().release.checkOpen()
        case (.prune, .ClientPrune, .ClientPrune(let request)):
            try client().checkOpen()
            try OpenTideConstants.validatePruneArguments(keep: request.keep)
        case (.close, .ClientClose, .ClientClose(_)):
            break
        case (.convention, .ReleaseConvention, .ReleaseConvention(_)):
            try release().checkOpen()
        case (.licence, .ReleaseLicence, .ReleaseLicence(_)):
            try release().checkOpen()
        case (.station, .ReleaseStation, .ReleaseStation(_)):
            try release().checkOpen()
        case (.requireStation, .ReleaseRequireStation, .ReleaseRequireStation(_)):
            try release().checkOpen()
        case (.tombstone, .ReleaseTombstone, .ReleaseTombstone(_)):
            try release().checkOpen()
        case (.stationByAlias, .ReleaseStationByAlias, .ReleaseStationByAlias(_)):
            try release().checkOpen()
        case (.stations, .ReleaseStations, .ReleaseStations(_)):
            try release().checkOpen()
        case (.iterStations, .ReleaseIterStations, .ReleaseIterStations(_)):
            try release().checkOpen()
        case (.search, .ReleaseSearch, .ReleaseSearch(let request)):
            _ = try Release.validatedSearchQuery(name: request.name, limit: request.limit, match: request.match)
            try release().checkOpen()
        case (.near, .ReleaseNear, .ReleaseNear(let request)):
            try Release.validateNearArguments(lat: request.lat, lon: request.lon, radiusKm: request.radiusKm, limit: request.limit)
            try release().checkOpen()
        case (.bbox, .ReleaseBbox, .ReleaseBbox(let request)):
            try Release.validateBboxArguments(south: request.south, west: request.west, north: request.north, east: request.east, limit: request.limit)
            try release().checkOpen()
        case (.nearest, .ReleaseNearest, .ReleaseNearest(let request)):
            try Release.validateNearArguments(lat: request.lat, lon: request.lon, radiusKm: request.maxKm ?? .infinity, limit: 1)
            try release().checkOpen()
        case (.referenceStation, .ReleaseReferenceStation, .ReleaseReferenceStation(_)):
            try release().checkOpen()
        case (.subordinatesOf, .ReleaseSubordinatesOf, .ReleaseSubordinatesOf(_)):
            try release().checkOpen()
        case (.attribution, .ReleaseAttribution, .ReleaseAttribution(_)):
            try release().checkOpen()
        case (.heights, .ReleaseHeights, .ReleaseHeights(let request)):
            try release().checkOpen()
            try validatePredictionUnits(request.units, height: true)
            _ = try Predict.window(request.start, request.stop, stepS: request.stepS)
            try stationPhase(request.station)
            try Predict.options(nil)
            try Predict.optionExclusion(setId: request.setId, offsetId: request.offsetId)
        case (.heightsAt, .ReleaseHeightsAt, .ReleaseHeightsAt(let request)):
            try release().checkOpen()
            try validatePredictionUnits(request.units, height: true)
            _ = try request.times.map(predictionInstant)
            try stationPhase(request.station)
            try Predict.options(nil)
            try Predict.optionExclusion(setId: request.setId, offsetId: request.offsetId)
        case (.extremes, .ReleaseExtremes, .ReleaseExtremes(let request)):
            try release().checkOpen()
            try validatePredictionUnits(request.units, height: true)
            _ = try Predict.window(request.start, request.stop)
            try stationPhase(request.station)
            try Predict.options(nil)
            try Predict.optionExclusion(setId: request.setId, offsetId: request.offsetId)
        case (.currents, .ReleaseCurrents, .ReleaseCurrents(let request)):
            try release().checkOpen()
            try validatePredictionUnits(request.units, height: false)
            _ = try Predict.window(request.start, request.stop, stepS: request.stepS)
            try stationPhase(request.station)
            try Predict.options(request.binNumber)
        case (.currentEvents, .ReleaseCurrentEvents, .ReleaseCurrentEvents(let request)):
            try release().checkOpen()
            try validatePredictionUnits(request.units, height: false)
            _ = try Predict.window(request.start, request.stop)
            try stationPhase(request.station)
            try Predict.options(request.binNumber)
        case (.datums, .ReleaseDatums, .ReleaseDatums(_)):
            try release().checkOpen()
        case (.ranges, .ReleaseRanges, .ReleaseRanges(_)):
            try release().checkOpen()
        case (.astroTable, .ReleaseAstroTable, .ReleaseAstroTable(_)):
            try release().checkOpen()
        case (.constantSets, .StationConstantSets, .StationConstantSets(_)):
            break
        case (.constantSet, .StationConstantSet, .StationConstantSet(_)):
            break
        case (.constituent, .ConstantSetConstituent, .ConstantSetConstituent(_)):
            break
        case (.equilibriumArgument, .AstroTableEquilibriumArgument, .AstroTableEquilibriumArgument(let request)):
            _ = try predictionInstant(request.at)
        case (.nodeFactor, .AstroTableNodeFactor, .AstroTableNodeFactor(let request)):
            _ = try predictionInstant(request.at)
        case (.equilibriumForYear, .AstroTableEquilibriumForYear, .AstroTableEquilibriumForYear(_)):
            break
        case (.nodeFactorForYear, .AstroTableNodeFactorForYear, .AstroTableNodeFactorForYear(_)):
            break
        case (.toLocal, .HeightPointLocalDatetime, .HeightPointLocalDatetime(_)):
            break
        case (.toLocal, .ExtremeLocalDatetime, .ExtremeLocalDatetime(_)):
            break
        case (.toLocal, .CurrentPointLocalDatetime, .CurrentPointLocalDatetime(_)):
            break
        case (.toLocal, .CurrentEventLocalDatetime, .CurrentEventLocalDatetime(_)):
            break
        case (.toLocal, .HeightSeriesToLocal, .HeightSeriesToLocal(_)):
            break
        case (.toLocal, .ExtremeListToLocal, .ExtremeListToLocal(_)):
            break
        case (.toLocal, .CurrentSeriesToLocal, .CurrentSeriesToLocal(_)):
            break
        case (.toLocal, .CurrentEventListToLocal, .CurrentEventListToLocal(_)):
            break
        default: throw CanonicalUnimplemented.behavior("B01")
        }
        return arguments
    }

    // B02 resolve_effective_options — body INCOMPLETE.
    internal static func resolveEffectiveOptions(explicitOptions: CanonicalExplicitOptions, environment: CanonicalEnvironment, platformDefaults: CanonicalPlatformDefaults) throws -> CanonicalEffectiveOptions {
        OpenTideConstants.effectiveOpenOptions(explicitOptions, environment: environment, platformDefaults: platformDefaults)
    }

    // B03 select_canonical_error — body INCOMPLETE.
    internal static func selectCanonicalError(operation: CanonicalOperation, orderedFailures: CanonicalOrderedFailures, cause: CanonicalCause) throws -> CanonicalCanonicalError {
        guard let failure = orderedFailures.first else { throw CanonicalUnimplemented.behavior("B03") }
        return CanonicalCanonicalError(code: failure.code, structuredFields: failure.structuredFields, cause: failure.cause ?? cause)
    }

    // B04 translate_native_binding — body INCOMPLETE.
    internal static func translateNativeBinding(canonicalResult: CanonicalCanonicalResult?, canonicalError: CanonicalCanonicalError?, nativeProfile: CanonicalNativeProfile) throws -> CanonicalNativeResult {
        guard nativeProfile == .swift else { throw CanonicalUnimplemented.behavior("B04") }
        if let error = canonicalError {
            // A usable client retains its own acquisition diagnostic; it is not an exception return.
            if case .ClientOpen(let client) = canonicalResult,
                client.lastError?.code == error.code.rawValue,
                .object(client.lastError?.fields ?? [:]) == error.structuredFields {
                return .ClientOpen(client)
            }
            guard let cause = error.cause else { throw CanonicalUnimplemented.behavior("B04") }
            throw cause
        }
        guard let result = canonicalResult else { throw CanonicalUnimplemented.behavior("B04") }
        return result
    }

    // B05 decode_release_document — selected native phase available.
    internal static func decodeReleaseDocument(sourceBytes: CanonicalSourceBytes, readerVersion: CanonicalReaderVersion, documentKind: CanonicalDocumentKind) throws -> CanonicalParsedDocument {
        switch sourceBytes {
        case .bytes(let bytes): return try Reader.decodeDocument(bytes,readerVersion:readerVersion,kind:documentKind)
        case .metadata(let context): return try context.decode(documentKind)
        }
    }

    // B06 validate_release_links — selected native phase available.
    internal static func validateReleaseLinks(parsedDocument: CanonicalParsedDocument, requiredLinks: CanonicalRequiredLinks) throws -> CanonicalValidatedReleaseGraph {
        guard case .release(let document)=parsedDocument else { throw CanonicalUnimplemented.behavior("B06.release_document") }
        return try Reader.validateDocumentLinks(document)
    }

    // B07 materialize_typed_model — body INCOMPLETE.
    internal static func materializeTypedModel(rawFields: CanonicalRawFields, fieldContract: CanonicalFieldContract, origin: CanonicalOrigin, modelType: CanonicalModelType) throws -> CanonicalTypedModel {
        guard fieldContract.modelType == modelType,
            fieldContract.members.allSatisfy({ $0.rawValue.hasPrefix(modelType.rawValue + ".") }) else {
            throw CanonicalUnimplemented.behavior("B07")
        }
        switch (modelType, rawFields) {
        case (.Client, .Client(let fields)):
            return .Client(OpenTideConstants(prepared: fields))
        case (.Release, .Release(let fields)):
            return .Release(Release(prepared: fields))
        case (.UpdateResult, .UpdateResult(let fields)):
            return .UpdateResult(UpdateResult(updated: fields.updated, from: fields.from, to: fields.to))
        case (.HeightPoint, .HeightPoint(let fields)):
            return .HeightPoint(HeightPoint(time: fields.time, heightM: fields.heightM, localTime: fields.localTime, utcOffsetS: fields.utcOffsetS, units: fields.units))
        case (.Extreme, .Extreme(let fields)):
            return .Extreme(Extreme(time: fields.time, type: fields.type, heightM: fields.heightM, localTime: fields.localTime, utcOffsetS: fields.utcOffsetS, units: fields.units))
        case (.CurrentPoint, .CurrentPoint(let fields)):
            return .CurrentPoint(CurrentPoint(time: fields.time, velocityMajorMs: fields.velocityMajorMs, velocityMinorMs: fields.velocityMinorMs, speedMs: fields.speedMs, directionDeg: fields.directionDeg, localTime: fields.localTime, utcOffsetS: fields.utcOffsetS, units: fields.units))
        case (.CurrentEvent, .CurrentEvent(let fields)):
            return .CurrentEvent(CurrentEvent(time: fields.time, type: fields.type, velocityMs: fields.velocityMs, directionDeg: fields.directionDeg, localTime: fields.localTime, utcOffsetS: fields.utcOffsetS, units: fields.units))
        case (.HeightSeries, .HeightSeries(let fields)):
            return .HeightSeries(HeightSeries(items: fields.items, stationId: fields.stationId, timezone: fields.timezone, method: fields.method, setId: fields.setId, conventionId: fields.conventionId, astroTableId: fields.astroTableId, referenceStationId: fields.referenceStationId, referenceBin: fields.referenceBin, datum: fields.datum, datumName: fields.datumName, datumKind: fields.datumKind, datumUncertaintyM: fields.datumUncertaintyM, tz: fields.tz, tzVersion: fields.tzVersion, release: fields.release, algorithm: fields.algorithm, offsetId: fields.offsetId, offsetSource: fields.offsetSource, offsetSourceVersion: fields.offsetSourceVersion, historicalOffsets: fields.historicalOffsets, currentValidity: fields.currentValidity, currentAccuracy: fields.currentAccuracy, referenceSetId: fields.referenceSetId, referenceSourceVersion: fields.referenceSourceVersion, reference2020Equivalence: fields.reference2020Equivalence, sourceNote: fields.sourceNote, units: fields.units))
        case (.ExtremeList, .ExtremeList(let fields)):
            return .ExtremeList(ExtremeList(items: fields.items, stationId: fields.stationId, timezone: fields.timezone, method: fields.method, setId: fields.setId, conventionId: fields.conventionId, astroTableId: fields.astroTableId, referenceStationId: fields.referenceStationId, referenceBin: fields.referenceBin, datum: fields.datum, datumName: fields.datumName, datumKind: fields.datumKind, datumUncertaintyM: fields.datumUncertaintyM, tz: fields.tz, tzVersion: fields.tzVersion, release: fields.release, algorithm: fields.algorithm, offsetId: fields.offsetId, offsetSource: fields.offsetSource, offsetSourceVersion: fields.offsetSourceVersion, historicalOffsets: fields.historicalOffsets, currentValidity: fields.currentValidity, currentAccuracy: fields.currentAccuracy, referenceSetId: fields.referenceSetId, referenceSourceVersion: fields.referenceSourceVersion, reference2020Equivalence: fields.reference2020Equivalence, sourceNote: fields.sourceNote, units: fields.units))
        case (.CurrentSeries, .CurrentSeries(let fields)):
            return .CurrentSeries(CurrentSeries(items: fields.items, stationId: fields.stationId, timezone: fields.timezone, method: fields.method, setId: fields.setId, conventionId: fields.conventionId, astroTableId: fields.astroTableId, referenceStationId: fields.referenceStationId, referenceBin: fields.referenceBin, datum: fields.datum, datumName: fields.datumName, datumKind: fields.datumKind, datumUncertaintyM: fields.datumUncertaintyM, tz: fields.tz, tzVersion: fields.tzVersion, release: fields.release, algorithm: fields.algorithm, binNumber: fields.binNumber, units: fields.units))
        case (.CurrentEventList, .CurrentEventList(let fields)):
            return .CurrentEventList(CurrentEventList(items: fields.items, stationId: fields.stationId, timezone: fields.timezone, method: fields.method, setId: fields.setId, conventionId: fields.conventionId, astroTableId: fields.astroTableId, referenceStationId: fields.referenceStationId, referenceBin: fields.referenceBin, datum: fields.datum, datumName: fields.datumName, datumKind: fields.datumKind, datumUncertaintyM: fields.datumUncertaintyM, tz: fields.tz, tzVersion: fields.tzVersion, release: fields.release, algorithm: fields.algorithm, binNumber: fields.binNumber, omittedEventTypes: fields.omittedEventTypes, units: fields.units))
        case (.DatumInfo, .DatumInfo(let fields)):
            return .DatumInfo(DatumInfo(setId: fields.setId, zero: fields.zero, zeroName: fields.zeroName, chartDatum: fields.chartDatum, mslOffsetM: fields.mslOffsetM, levels: fields.levels))
        case (.DatumLevel, .DatumLevel(let fields)):
            return .DatumLevel(DatumLevel(key: fields.key, valueM: fields.valueM, aboveChartM: fields.aboveChartM, kind: fields.kind, method: fields.method, sourceName: fields.sourceName, epoch: fields.epoch, dataSpan: fields.dataSpan, controlStationId: fields.controlStationId, controlSetId: fields.controlSetId, controlSourceId: fields.controlSourceId, uncertaintyM: fields.uncertaintyM, uncertaintyBasis: fields.uncertaintyBasis, flags: fields.flags))
        case (.Ranges, .Ranges(let fields)):
            return .Ranges(Ranges(mn: fields.mn, gt: fields.gt, dhq: fields.dhq, dlq: fields.dlq))
        case (.Nearby, .Nearby(let fields)):
            return .Nearby(Nearby(station: fields.station, distanceKm: fields.distanceKm))
        case (.Stats, .Stats(let fields)):
            return .Stats(Stats(type: fields.type, kind: fields.kind, country: fields.country, source: fields.source, qcStatus: fields.qcStatus))
        default: break
        }
        guard case .sourceJSON(let rawFields) = rawFields else {
            throw CanonicalUnimplemented.behavior("B07")
        }
        switch modelType {
        case .ReleaseInfo: return .ReleaseInfo(ReleaseInfo(rawFields))
        case .FileInfo: return .FileInfo(FileInfo(rawFields))
        case .Tombstone: return .Tombstone(Tombstone(rawFields))
        case .SubordinateOffsets: return .SubordinateOffsets(SubordinateOffsets(rawFields))
        case .Constituent: return .Constituent(Constituent(rawFields))
        case .Convention: return .Convention(Convention(rawFields))
        case .Licence: return .Licence(try Reader.licence(rawFields))
        case .Provenance: return .Provenance(Provenance(rawFields))
        case .TimeBase: return .TimeBase(TimeBase(rawFields))
        case .RecordSpan: return .RecordSpan(RecordSpan(rawFields))
        case .Datum: return .Datum(Datum(rawFields))
        case .Validation: return .Validation(Validation(rawFields))
        case .DroppedConstituent: return .DroppedConstituent(DroppedConstituent(rawFields))
        case .QcFlag: return .QcFlag(QcFlag(rawFields))
        case .ProvenanceBuild: return .ProvenanceBuild(ProvenanceBuild(rawFields))
        case .Fallback: return .Fallback(Fallback(rawFields))
        case .HistoricalOffsetVintage: return .HistoricalOffsetVintage(HistoricalOffsetVintage(rawFields))
        case .HistoricalOffsetProvenance: return .HistoricalOffsetProvenance(HistoricalOffsetProvenance(rawFields))
        case .AstroTable: return .AstroTable(try AstroTable(rawFields))
        case .ConstantSet:
            guard let context = fieldContract.materialization, let validation = context.setValidation else {
                throw CanonicalUnimplemented.behavior("B07")
            }
            guard let id = rawFields["set_id"].string,
                let convention = context.release.convById[rawFields["convention_id"].string ?? ""],
                let licence = context.release.licById[rawFields["licence_id"].string ?? ""] else {
                throw OpenTideConstantsError.invalidRelease("set identity/reference unresolved")
            }
            return .ConstantSet(ConstantSet(raw: rawFields, convention: convention, licence: licence,
                isRecommended: id == context.recommendation, validation: validation))
        case .SourceRecord:
            guard let context = fieldContract.materialization else { throw CanonicalUnimplemented.behavior("B07") }
            return .SourceRecord(SourceRecord(raw: rawFields,
                licence: rawFields["licence_id"].string.flatMap { context.release.licById[$0] },
                upstreamLicence: rawFields["upstream_licence_id"].string.flatMap { context.release.licById[$0] }))
        default: break
        }
        if modelType == .Station, fieldContract.modelType == .Station, let context = fieldContract.materialization {
            let station = try Reader.station(rawFields, conventions: context.release.convById,
                licences: context.release.licById, kind: context.kind, recommended: context.recommendation).withOrigin(origin)
            try context.release.own(station)
            return .Station(station)
        }
        throw CanonicalUnimplemented.behavior("B07")
    }

    // B08 access_raw_record — exact selected raw or producing-owner branch.
    internal static func accessRawRecord(accessKind: CanonicalAccessKind, sourceRecord: CanonicalSourceRecord, station: CanonicalStation, releaseOrigin: CanonicalReleaseOrigin, nativeProfile: CanonicalNativeProfile) throws -> CanonicalRawRecordOrValidStation {
        switch accessKind {
        case .rawRecord: return .JsonValue(try retainRawSourceRecord(sourceRecord:sourceRecord,nativeProfile:nativeProfile))
        case .stationObject: return .Station(try checkStationOrigin(station:station,releaseOrigin:releaseOrigin))
        }
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

    // B15 enforce_resource_lifetime — borrowed actual owning resources.
    internal static func enforceResourceLifetime(resourceState: CanonicalResourceState, lifetimeAction: CanonicalLifetimeAction) throws -> CanonicalResourceStateOrError {
        switch resourceState {
        case .clientState(let context): try context.enforce(lifetimeAction);return .clientState(context)
        case .Release(let release):
            if lifetimeAction=="close" { release.close() }
            else if lifetimeAction != "retained_metadata" { try release.checkOpen() }
            return .Release(release)
        case .streamReader(let context): try context.enforce(lifetimeAction);return .streamReader(context)
        }
    }

    // B16 bind_checksum_manifest — selected native phase available.
    internal static func bindChecksumManifest(checksumBytes: CanonicalChecksumBytes, pointerDigests: CanonicalPointerDigests, requiredFiles: CanonicalRequiredFiles) throws -> CanonicalBoundChecksums {
        try ClientIO.bindManifest(checksumBytes,pointerDigests:pointerDigests,requiredFiles:requiredFiles)
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

    // B20 native verification available; generic B16 argument composition remains INCOMPLETE.
    internal static func verifyReleaseFiles(releaseFiles: CanonicalReleaseFiles, trustedCachedPointer: CanonicalTrustedCachedPointer) throws -> CanonicalVerificationResult {
        try releaseFiles.verify(trustedPointer:trustedCachedPointer)
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
        let entry = IndexEntry.make(stationSourceRow, offset: UInt64(exactly: sourceByteSpan.offsetBytes),
            length: Int(exactly: sourceByteSpan.lengthBytes))
        return try projectIndexSummary(entry.summary)
    }

    // B25 authenticate_station_index — selected native phase available.
    internal static func authenticateStationIndex(sourceFiles: CanonicalSourceFiles, suppliedIndex: CanonicalSuppliedIndex, indexPresence: CanonicalIndexPresence, readerVersion: CanonicalReaderVersion) throws -> CanonicalAuthenticatedIndex {
        let meta=try JSONValue.parse(Reader.read(sourceFiles.meta))
        try Reader.validateHeader(meta,readerVersion:readerVersion)
        let (conventions,licences)=try Reader.documentLookupTables(meta)
        let files=[FileInfo(.object(["name":.string(sourceFiles.jsonl.lastPathComponent),"sha256":.string(sourceFiles.jsonlSha256),"size":.integer(sourceFiles.jsonlSize)])),
            FileInfo(.object(["name":.string(sourceFiles.meta.lastPathComponent),"sha256":.string(sourceFiles.metaSha256),"size":.integer(sourceFiles.metaSize)]))]
        return try Reader.prepareStreamIndex(sourceFiles.jsonl,meta:meta,conventions:conventions,licences:licences,
            indexPath:sourceFiles.indexPath,files:files,commercialOnly:false,commercialBasis:"strict",historicalOffsetsPolicy:"fallback",logger:nil,supplied:suppliedIndex)
    }

    // B26 compare_station_source — selected native phase available.
    internal static func compareStationSource(indexEntry: CanonicalIndexEntry, stationSourceRow: CanonicalStationSourceRow, indexPresence: CanonicalIndexPresence) throws -> CanonicalComparedStationRow {
        try indexEntry.compare(stationSourceRow)
    }

    // B27 read_station_lazily — selected native phase available.
    internal static func readStationLazily(streamReader: CanonicalStreamReader, stationId: CanonicalStationId, releaseOrigin: CanonicalReleaseOrigin, readerVersion: CanonicalReaderVersion) throws -> CanonicalStationSourceRow {
        _ = try enforceResourceLifetime(resourceState:.streamReader(streamReader),lifetimeAction:"station_read")
        guard releaseOrigin.belongs(to:streamReader) else { throw OpenTideConstantsError.invalidArgument("foreign station") }
        return try streamReader.read(stationId)
    }

    // B28 encode_cache_json — body INCOMPLETE.
    internal static func encodeCacheJson(cacheDocument: CanonicalCacheDocument) throws -> CanonicalCacheBytes {
        switch cacheDocument {
        case .pointerOrCatalogue(let document): return try encode_cache_json(document)
        case .streamIndex(let index): return try encode_cache_json(cacheIndexDocument(index))
        case .verifiedReceipt(let receipt):
            var document: [String: JSONValue] = ["datestamp": .string(receipt.datestamp),
                "files": .object(receipt.files.mapValues { file in
                    let fields: [String: JSONValue] = ["sha256": .string(file.sha256), "size": .integer(file.size),
                        "url": file.url.map(JSONValue.string) ?? .null]
                    return .object(fields)
                }), "format_version": .string(receipt.formatVersion), "min_reader_version": .string(receipt.minReaderVersion),
                "verified_at": .string(receipt.verifiedAt), "by": .string(receipt.by)]
            document["zenodo_version_doi"] = receipt.zenodoVersionDoi.map(JSONValue.string) ?? .null
            return try encode_cache_json(.object(document))
        }
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
    internal static func parsePredictionWindow(timeInputs: CanonicalTimeInputs, windowInputs: CanonicalWindowInputs, step: CanonicalStep?, localTimeProfile: CanonicalLocalTimeProfile) throws -> CanonicalPredictionWindow {
        let start: Date, stop: Date, series: Bool
        switch windowInputs {
        case .ReleaseHeights(let request): start = request.start; stop = request.stop; series = true
        case .ReleaseCurrents(let request): start = request.start; stop = request.stop; series = true
        case .ReleaseExtremes(let request): start = request.start; stop = request.stop; series = false
        case .ReleaseCurrentEvents(let request): start = request.start; stop = request.stop; series = false
        case .ReleaseHeightsAt(let request):
            return .instants(try request.times.map(predictionInstant))
        default: throw CanonicalUnimplemented.behavior("B39")
        }
        let stepS = series ? step.flatMap { Int64(exactly: $0) } : nil
        let window = try Predict.window(start, stop, stepS: stepS)
        if series && stepS == nil { throw OpenTideConstantsError.invalidArgument("step_s must be a positive integer") }
        return .span(start: window.0, stop: window.1, step: stepS.map(Double.init))
    }

    // B40 select_prediction_model — body INCOMPLETE.
    internal static func selectPredictionModel(stationRequest: CanonicalStationRequest, releaseView: CanonicalReleaseView, selectionOptions: CanonicalSelectionOptions, readerVersion: CanonicalReaderVersion) throws -> CanonicalSelectedPredictionModel {
        throw CanonicalUnimplemented.behavior("B40")
    }

    // B41 evaluate_astronomy — body INCOMPLETE.
    internal static func evaluateAstronomy(selectedPredictionModel: CanonicalSelectedPredictionModel, utcInstant: CanonicalUtcInstant) throws -> CanonicalAstronomicalTerms {
        guard let total = selectedPredictionModel.nativeContext?.total else { throw CanonicalUnimplemented.behavior("B41") }
        let year = utcYear(utcInstant)
        let (origin, terms) = try total.yearData(year)
        return CanonicalAstronomicalTerms(utcYear: year, constituentTerms: terms.map { term in
            .object(["speed": .number(term.speed), "amplitude": .number(term.amplitude),
                "argument": .number(term.argument), "omega": .number(term.omega)])
        }, epochHours: (utcInstant - origin) / 3600.0)
    }

    // B42 evaluate_harmonic_height — body INCOMPLETE.
    internal static func evaluateHarmonicHeight(selectedPredictionModel: CanonicalSelectedPredictionModel, predictionInstants: CanonicalPredictionInstants, requestedDatum: CanonicalRequestedDatum) throws -> CanonicalHeightValues {
        guard var context = selectedPredictionModel.nativeContext, let total = context.total else { throw CanonicalUnimplemented.behavior("B42") }
        let datum = try Predict.datum(selectedPredictionModel.datumSource ?? .null, requested: requestedDatum, context: &context)
        let evaluation = total.mean == datum ? total:try HarmonicSum(context.table,
            context.constants.raw["constituents"].array, mean: datum)
        let items = try predictionInstants.map { instant -> HeightPoint in
            let terms = try evaluateAstronomy(selectedPredictionModel: selectedPredictionModel, utcInstant: instant)
            let value = try evaluation.value(instant, year: terms.utcYear)
            return HeightPoint(time: Date(timeIntervalSince1970: instant), heightM: value)
        }
        return HeightSeries(items: items)
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
        sourceRecord
    }

    // B08.origin check_station_origin — selected native phase available.
    internal static func checkStationOrigin(station: CanonicalStation, releaseOrigin: CanonicalReleaseOrigin) throws -> CanonicalValidStation {
        try releaseOrigin.check(station)
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
        guard let total = selectedPredictionModel.nativeContext?.total else { throw CanonicalUnimplemented.behavior("B43.roots") }
        guard case .span(let start, let stop, _) = predictionWindow else { throw CanonicalUnimplemented.behavior("B43.roots") }
        return try unroundedHarmonicEvents(total, start: start, stop: stop).enumerated().map { index, event in
            CanonicalUnroundedTideEvent(rootSeconds: event.time, eventType: CanonicalUnroundedTideEventEventType(rawValue: event.kind)!, heightM: event.value, referenceOrder: Int64(index))
        }
    }

    // B44.roots find_unrounded_current_events — body INCOMPLETE.
    internal static func findUnroundedCurrentEvents(selectedPredictionModel: CanonicalSelectedPredictionModel, predictionWindow: CanonicalPredictionWindow, currentRequest: CanonicalCurrentRequest) throws -> CanonicalUnroundedCurrentEvents {
        guard let context = selectedPredictionModel.nativeContext else { throw CanonicalUnimplemented.behavior("B44.roots") }
        guard case .span(let start, let stop, _) = predictionWindow else { throw CanonicalUnimplemented.behavior("B44.roots") }
        return try Predict.unroundedCurrentCandidates(context, start: start, stop: stop).enumerated().map { index, event in
            CanonicalUnroundedCurrentEvent(rootSeconds: event.time, eventType: CanonicalUnroundedCurrentEventEventType(rawValue: event.kind)!, velocityMS: event.value, directionDeg: event.direction, referenceOrder: Int64(index))
        }
    }

    // B17.sidecar acquire_checksum_sidecar — body INCOMPLETE.
    internal static func acquireChecksumSidecar(acquisitionDescriptor: CanonicalAcquisitionDescriptor, effectiveOptions: CanonicalEffectiveOptions) async throws -> CanonicalChecksumBytes {
        throw CanonicalUnimplemented.behavior("B17.sidecar")
    }
}
