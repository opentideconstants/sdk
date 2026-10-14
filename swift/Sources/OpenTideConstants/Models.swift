import Foundation

public struct ReleaseInfo: Sendable, Equatable {
    public let raw: JSONValue
    internal init(_ raw: JSONValue) { self.raw = raw }
    public var datestamp: String { raw["datestamp"].string ?? "" }
    public var formatVersion: String { raw["format_version"].string ?? "" }
    public var conceptDoi: String? { raw["concept_doi"].string }
    public var zenodoVersionDoi: String? { raw["zenodo_version_doi"].string }
    public var contentSha256: String { raw["content_sha256"].string ?? "" }
    public var files: [FileInfo] { raw["files"].array.map { FileInfo($0) } }
}

public struct FileInfo: Sendable, Equatable {
    public let raw: JSONValue
    internal init(_ raw: JSONValue) { self.raw = raw }
    public var name: String { raw["name"].string ?? "" }
    public var url: String? { raw["url"].string }
    public var size: Int64? { raw["size"].integer }
    public var sha256: String? { raw["sha256"].string }
}

public struct Tombstone: Sendable, Equatable {
    public let raw: JSONValue
    internal init(_ raw: JSONValue) { self.raw = raw }
    public var stationId: String { raw["station_id"].string ?? "" }
    public var name: String? { raw["name"].string }
    public var status: StationStatus { StationStatus(value: raw["status"]) }
    public var removedIn: String { raw["removed_in"].string ?? "" }
    public var removedReason: RemovedReason { RemovedReason(value: raw["removed_reason"]) }
    public var mergedInto: String { raw["merged_into"].string ?? "" }
    public var detail: String? { raw["detail"].string }
}

public struct Constituent: Sendable, Equatable {
    public let raw: JSONValue
    internal init(_ raw: JSONValue) { self.raw = raw }
    public var name: String { raw["name"].string ?? "" }
    public var sourceName: String? { raw["source_name"].string }
    public var doodson: String? { raw["doodson"].string }
    public var speedDegPerHour: Double { raw["speed_deg_per_hour"].number ?? .nan }
    public var amplitudeM: Double { raw["amplitude_m"].number ?? .nan }
    public var phaseDeg: Double { raw["phase_deg"].number ?? .nan }
    public var ampUncertaintyM: Double? { raw["amp_uncertainty_m"].number }
    public var phaseUncertaintyDeg: Double? { raw["phase_uncertainty_deg"].number }
    public var keptReason: String? { raw["kept_reason"].string }
}

public struct Convention: Sendable, Equatable {
    public let raw: JSONValue
    internal init(_ raw: JSONValue) { self.raw = raw }
    public var conventionId: String { raw["convention_id"].string ?? "" }
    public var phaseReference: PhaseReference { PhaseReference(value: raw["phase_reference"]) }
    public var utcOffsetHours: Double? { raw["utc_offset_hours"].number }
    public var v0Model: String { raw["v0_model"].string ?? "" }
    public var nodalHandling: NodalHandling { NodalHandling(value: raw["nodal_handling"]) }
    public var nodalFormulaIds: JSONValue? { raw["nodal_formula_ids"].isNull ? nil : raw["nodal_formula_ids"] }
    public var constituentTableVersion: String { raw["constituent_table_version"].string ?? "" }
    public var tablesSha256: String? { raw["tables_sha256"].string }
    public var canary: JSONValue? { raw["canary"].isNull ? nil : raw["canary"] }
}

public struct Licence: Sendable, Equatable {
    public let raw: JSONValue
    internal init(_ raw: JSONValue) { self.raw = raw }
    public var licenceId: String { raw["licence_id"].string ?? "" }
    public var spdx: String { raw["spdx"].string ?? "" }
    public var provider: String { raw["provider"].string ?? "" }
    public var citation: String? { raw["citation"].string }
    public var attribution: String { raw["attribution"].string ?? "" }
    public var url: String? { raw["url"].string }
    public var commercialUse: Bool { raw["commercial_use"].bool ?? false }
    public var restriction: String? { raw["restriction"].string }
    public var termsUrl: String? { raw["terms_url"].string }
}

public struct Provenance: Sendable, Equatable {
    public let raw: JSONValue
    internal init(_ raw: JSONValue) { self.raw = raw }
    public var adapterVersion: String? { raw["adapter_version"].string }
    public var inputSha256: [String]? { raw["input_sha256"].isNull ? nil : raw["input_sha256"].array.compactMap(\.string) }
    public var selectionReason: String? { raw["selection_reason"].string }
    public var decision: JSONValue? { raw["decision"].isNull ? nil : raw["decision"] }
    public var build: ProvenanceBuild? { raw["build"].isNull ? nil : ProvenanceBuild(raw["build"]) }
    public var carriedFromRelease: String? { raw["carried_from_release"].string }
}

public struct ProvenanceBuild: Sendable, Equatable {
    public let raw: JSONValue
    internal init(_ raw: JSONValue) { self.raw = raw }
    public var buildCommit: String { raw["build_commit"].string ?? "" }
    public var builtAt: Date? { try? parseTime(raw["built_at"].string) }
    public var fetchedAt: Date? { try? parseTime(raw["fetched_at"].string) }
    public var runId: String? { raw["run_id"].string }
    public var toolVersions: JSONValue? { raw["tool_versions"].isNull ? nil : raw["tool_versions"] }
}

public struct TimeBase: Sendable, Equatable {
    public let raw: JSONValue
    internal init(_ raw: JSONValue) { self.raw = raw }
    public var code: TimeBaseCode { TimeBaseCode(value: raw["code"]) }
    public var reason: String { raw["reason"].string ?? "" }
    public var declared: String { raw["declared"].string ?? "" }
    public var published: String { raw["published"].string ?? "" }
    public var correction: JSONValue? { raw["correction"].isNull ? nil : raw["correction"] }
    public var monthsDropped: [String] { raw["months_dropped"].array.compactMap(\.string) }
    public var decidedIn: String { raw["decided_in"].string ?? "" }
    public var decidedBuildCommit: String? { raw["decided_build_commit"].string }
    public var evidence: JSONValue { raw["evidence"].isNull ? .array([]) : raw["evidence"] }
}

public struct QcFlag: Sendable, Equatable {
    public let raw: JSONValue
    internal init(_ raw: JSONValue) { self.raw = raw }
    public var flag: QcFlagName { QcFlagName(value: raw["flag"]) }
    public var reason: String { raw["reason"].string ?? "" }
    public var values: JSONValue? { raw["values"].isNull ? nil : raw["values"] }
}

public struct DroppedConstituent: Sendable, Equatable {
    public let raw: JSONValue
    internal init(_ raw: JSONValue) { self.raw = raw }
    public var name: String { raw["name"].string ?? "" }
    public var droppedReason: DroppedReason { DroppedReason(value: raw["dropped_reason"]) }
    public var detail: String? { raw["detail"].string }
}

public struct Validation: Sendable, Equatable {
    public let raw: JSONValue
    internal init(_ raw: JSONValue) { self.raw = raw }
    public var setId: String { raw["set_id"].string ?? "" }
    public var referenceSource: String { raw["reference_source"].string ?? "" }
    public var referenceStation: String? { raw["reference_station"].string }
    public var referenceDistanceKm: Double? { raw["reference_distance_km"].number }
    public var window: String { raw["window"].string ?? "" }
    public var timeMaeMin: Double { raw["time_mae_min"].number ?? .nan }
    public var timeP95Min: Double? { raw["time_p95_min"].number }
    public var timeBiasMin: Double? { raw["time_bias_min"].number }
    public var heightMaeM: Double { raw["height_mae_m"].number ?? .nan }
    public var rangeErrorM: Double? { raw["range_error_m"].number }
    public var missedEvents: Int64? { raw["missed_events"].integer }
    public var extraEvents: Int64? { raw["extra_events"].integer }
    public var previousRelease: JSONValue? { raw["previous_release"].isNull ? nil : raw["previous_release"] }
}

public struct SubordinateOffsets: Sendable, Equatable {
    public let raw: JSONValue
    internal init(_ raw: JSONValue) { self.raw = raw }
    public var referenceStationId: String { raw["reference_station_id"].string ?? "" }
    public var timeOffsetHighMin: Double? { raw["time_offset_high_min"].number }
    public var timeOffsetLowMin: Double? { raw["time_offset_low_min"].number }
    public var heightOffsetHigh: Double? { raw["height_offset_high"].number }
    public var heightOffsetLow: Double? { raw["height_offset_low"].number }
    public var heightAdjustedType: HeightAdjustedType { HeightAdjustedType(value: raw["height_adjusted_type"]) }
    public var licenceId: String? { raw["licence_id"].string }
    public var offsetId: String? { raw["offset_id"].string }
    public var source: String? { raw["source"].string }
    public var sourceType: SourceType? { raw["source_type"].isNull ? nil : SourceType(value: raw["source_type"]) }
    public var sourceVersion: String? { raw["source_version"].string }
    public var sourceRecordId: String? { raw["source_record_id"].string }
    public var qcStatus: QcStatus? { raw["qc_status"].isNull ? nil : QcStatus(value: raw["qc_status"]) }
    public var qcFlags: [QcFlag] { raw["qc_flags"].array.map { QcFlag($0) } }
    public var fallback: Fallback? { raw["fallback"].isNull ? nil : Fallback(raw["fallback"]) }
    public var vintage: HistoricalOffsetVintage? { raw["vintage"].isNull ? nil : HistoricalOffsetVintage(raw["vintage"]) }
    public var provenance: HistoricalOffsetProvenance? { raw["provenance"].isNull ? nil : HistoricalOffsetProvenance(raw["provenance"]) }
}

public struct RecordSpan: Sendable, Equatable {
    public let raw: JSONValue
    internal init(_ raw: JSONValue) { self.raw = raw }
    public var start: Date? { try? parseTime(raw["start"].string) }
    public var end: Date? { try? parseTime(raw["end"].string) }
    public var goodSamples: Int64? { raw["good_samples"].integer }
}

public struct Datum: Sendable, Equatable {
    public let raw: JSONValue
    internal init(_ raw: JSONValue) { self.raw = raw }
    public var mslOffsetM: Double? { raw["msl_offset_m"].number }
    public var named: JSONValue? { raw["named"].isNull ? nil : raw["named"] }
}

public struct Fallback: Sendable, Equatable {
    public let raw: JSONValue
    internal init(_ raw: JSONValue) { self.raw = raw }
    public var reason: FallbackReason { FallbackReason(value: raw["reason"]) }
    public var basis: String { raw["basis"].string ?? "" }
    public var otcFinding: String { raw["otc_finding"].string ?? "" }
    public var preferredSetId: String? { raw["preferred_set_id"].string }
}

public struct HistoricalOffsetVintage: Sendable, Equatable {
    public let raw: JSONValue
    internal init(_ raw: JSONValue) { self.raw = raw }
    public var publicationYear: Double { raw["publication_year"].number ?? .nan }
    public var sourceLifecycle: String { raw["source_lifecycle"].string ?? "" }
    public var removalEvents: JSONValue { raw["removal_events"] }
    public var currentValidity: String { raw["current_validity"].string ?? "" }
    public var currentAccuracy: String { raw["current_accuracy"].string ?? "" }
    public var reference2020Equivalence: String { raw["reference_2020_equivalence"].string ?? "" }
    public var reference2020EquivalenceSha256: String? { raw["reference_2020_equivalence_sha256"].string }
}

public struct HistoricalOffsetProvenance: Sendable, Equatable {
    public let raw: JSONValue
    internal init(_ raw: JSONValue) { self.raw = raw }
    public var sourceManifestSha256: String { raw["source_manifest_sha256"].string ?? "" }
    public var inputSha256: [String] { raw["input_sha256"].array.compactMap(\.string) }
    public var book: String { raw["book"].string ?? "" }
    public var annualTableRow: Double { raw["annual_table_row"].number ?? .nan }
    public var printedPage: Double { raw["printed_page"].number ?? .nan }
    public var pdfPage: Double { raw["pdf_page"].number ?? .nan }
    public var rawRowText: String { raw["raw_row_text"].string ?? "" }
    public var rawValuesJson: String { raw["raw_values_json"].string ?? "" }
    public var idCrosswalk: JSONValue { raw["id_crosswalk"] }
    public var referenceBinding: JSONValue { raw["reference_binding"] }
    public var acceptanceReportSha256: String { raw["acceptance_report_sha256"].string ?? "" }
}

public struct SourceRecord: Sendable, Equatable {
    public let raw: JSONValue
    public let licence: Licence?
    public let upstreamLicence: Licence?
    public var source: String { raw["source"].string! }
    public var sourceVersion: String { raw["source_version"].string! }
    public var sourceRecordId: String { raw["source_record_id"].string! }
    public var role: SourceRole { SourceRole(value: raw["role"]) }
    public var disposition: SourceDisposition { SourceDisposition(value: raw["disposition"]) }
    public var detail: String { raw["detail"].string! }
    public var licenceId: String? { raw["licence_id"].string }
    public var upstreamLicenceId: String? { raw["upstream_licence_id"].string }
    public var publishedSetIds: [String] { raw["published_set_ids"].array.compactMap(\.string) }
    public var provenance: JSONValue { raw["provenance"] }
    public var originalMetadata: JSONValue { raw["original_metadata"].isNull ? .object([:]) : raw["original_metadata"] }
    public var originalHarmonics: JSONValue? { raw["original_harmonics"].isNull ? nil : raw["original_harmonics"] }
}
public struct ConstantSet: Sendable, Equatable {
    public let raw: JSONValue
    public let convention: Convention
    public let licence: Licence
    public let isRecommended: Bool
    public let validation: [Validation]
    public var setId: String { raw["set_id"].string! }
    public var source: String? { raw["source"].string }
    public var sourceType: SourceType { SourceType(value: raw["source_type"]) }
    public var quantity: Quantity { Quantity(value: raw["quantity"]) }
    public var sourceRecordId: String? { raw["source_record_id"].string }
    public var sourceVersion: String? { raw["source_version"].string }
    public var recordSpan: RecordSpan? { raw["record_span"].isNull ? nil : RecordSpan(raw["record_span"]) }
    public var datum: Datum? { raw["datum"].isNull ? nil : Datum(raw["datum"]) }
    public var qcStatus: QcStatus { QcStatus(value: raw["qc_status"]) }
    public var qcFlags: [QcFlag] { raw["qc_flags"].array.map(QcFlag.init) }
    public var droppedConstituents: [DroppedConstituent] { raw["dropped_constituents"].array.map(DroppedConstituent.init) }
    public var timeBase: TimeBase? { raw["time_base"].isNull ? nil : TimeBase(raw["time_base"]) }
    public var provenance: Provenance { Provenance(raw["provenance"]) }
    public var constituents: [Constituent] { raw["constituents"].array.map(Constituent.init) }
    public func constituent(name: String) -> Constituent? { constituents.first { $0.name == name } }
    public var fallback: Fallback? { raw["fallback"].isNull ? nil : Fallback(raw["fallback"]) }
}
public struct Station: Sendable, Equatable {
    internal private(set) var originToken: UUID?
    public let raw: JSONValue
    public let kind: Kind?
    public let recommendedSet: ConstantSet?
    public let sourceRecords: [SourceRecord]
    internal let sets: [ConstantSet]
    internal init(raw: JSONValue, kind: Kind?, recommendedSet: ConstantSet?, sourceRecords: [SourceRecord], sets: [ConstantSet]) {
        self.raw=raw;self.kind=kind;self.recommendedSet=recommendedSet;self.sourceRecords=sourceRecords;self.sets=sets
    }
    internal func withOrigin(_ token: UUID) -> Station {
        var station=self
        station.originToken=token
        return station
    }
    internal func hasOrigin(_ token: UUID) -> Bool { originToken==token }
    public static func == (lhs: Station, rhs: Station) -> Bool {
        lhs.raw==rhs.raw && lhs.kind==rhs.kind && lhs.recommendedSet==rhs.recommendedSet && lhs.sourceRecords==rhs.sourceRecords && lhs.sets==rhs.sets
    }
    public var stationId: String { raw["station_id"].string! }
    public var name: String? { raw["name"].string }
    public var country: String? { raw["country"].string }
    public var lat: Double { raw["lat"].number! }
    public var lon: Double { raw["lon"].number! }
    public var type: StationType { StationType(value: raw["type"]) }
    public var timezone: String? { raw["timezone"].string }
    public var aliases: [String: [String]] { raw["aliases"].object.mapValues { $0.string.map { [$0] } ?? $0.array.compactMap(\.string) } }
    public var status: StationStatus { raw["status"].isNull ? .active : StationStatus(value: raw["status"]) }
    public var isReference: Bool { type == .reference }
    public var isSubordinate: Bool { type == .subordinate }
    public var isTide: Bool { kind == .tide }
    public var isCurrent: Bool { kind == .current }
    public var subordinateOffsets: SubordinateOffsets? { raw["subordinate_offsets"].isNull ? nil : SubordinateOffsets(raw["subordinate_offsets"]) }
    public var validation: [Validation] { raw["validation"].array.map(Validation.init).sorted { $0.window < $1.window } }
    public var recommendedIsFallback: Bool? { raw["recommended_is_fallback"].bool }
    public func constantSets(includeNoConstants: Bool = false) -> [ConstantSet] { sets.filter { includeNoConstants || [.ok,.flagged].contains($0.qcStatus) } }
    public func constantSet(setId: String) -> ConstantSet? { sets.first { $0.setId == setId } }
}
public struct Nearby: Sendable, Equatable { public let station: Station; public let distanceKm: Double }
public struct Stats: Sendable, Equatable {
    public let type: [String: Int64]; public let kind: [String: Int64]; public let country: [String: Int64]
    public let source: [String: Int64]; public let qcStatus: [String: Int64]
}
public struct UpdateResult: Sendable, Equatable { public let updated: Bool; public let from: String?; public let to: String? }
