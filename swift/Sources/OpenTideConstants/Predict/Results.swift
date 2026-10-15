import Foundation

public struct HeightPoint: Sendable, Equatable {
    public let time: Date
    public let heightM: Double
    public let localTime: String?
    public let utcOffsetS: Int64?
    public init(time: Date, heightM: Double, localTime: String? = nil, utcOffsetS: Int64? = nil) {
        self.time = time
        self.heightM = heightM
        self.localTime = localTime
        self.utcOffsetS = utcOffsetS
    }
    public func localDatetime() -> Date? { localTime == nil ? nil : time }
}

public struct Extreme: Sendable, Equatable {
    public let time: Date
    public let type: ExtremeType
    public let heightM: Double
    public let localTime: String?
    public let utcOffsetS: Int64?
    public init(time: Date, type: ExtremeType, heightM: Double, localTime: String? = nil, utcOffsetS: Int64? = nil) {
        self.time = time
        self.type = type
        self.heightM = heightM
        self.localTime = localTime
        self.utcOffsetS = utcOffsetS
    }
    public func localDatetime() -> Date? { localTime == nil ? nil : time }
}

public struct CurrentPoint: Sendable, Equatable {
    public let time: Date
    public let velocityMajorMs: Double
    public let velocityMinorMs: Double
    public let speedMs: Double
    public let directionDeg: Double?
    public let localTime: String?
    public let utcOffsetS: Int64?
    public init(time: Date, velocityMajorMs: Double, velocityMinorMs: Double, speedMs: Double, directionDeg: Double?, localTime: String? = nil, utcOffsetS: Int64? = nil) {
        self.time = time
        self.velocityMajorMs = velocityMajorMs
        self.velocityMinorMs = velocityMinorMs
        self.speedMs = speedMs
        self.directionDeg = directionDeg
        self.localTime = localTime
        self.utcOffsetS = utcOffsetS
    }
    public func localDatetime() -> Date? { localTime == nil ? nil : time }
}

public struct CurrentEvent: Sendable, Equatable {
    public let time: Date
    public let type: CurrentEventType
    public let velocityMs: Double
    public let directionDeg: Double?
    public let localTime: String?
    public let utcOffsetS: Int64?
    public init(time: Date, type: CurrentEventType, velocityMs: Double, directionDeg: Double?, localTime: String? = nil, utcOffsetS: Int64? = nil) {
        self.time = time
        self.type = type
        self.velocityMs = velocityMs
        self.directionDeg = directionDeg
        self.localTime = localTime
        self.utcOffsetS = utcOffsetS
    }
    public func localDatetime() -> Date? { localTime == nil ? nil : time }
}

public struct HeightSeries: Sendable, Equatable {
    public let items: [HeightPoint]
    public let stationId: String?
    public let timezone: String?
    public let method: PredictionMethod?
    public let setId: String?
    public let conventionId: String?
    public let astroTableId: String?
    public let referenceStationId: String?
    public let referenceBin: Int64?
    public let datum: String?
    public let datumName: String?
    public let datumKind: String?
    public let datumUncertaintyM: Double?
    public let tz: String?
    public let tzVersion: String?
    public let release: String?
    public let algorithm: String?
    public let offsetId: String?
    public let offsetSource: String?
    public let offsetSourceVersion: String?
    public let historicalOffsets: Bool
    public let currentValidity: String?
    public let currentAccuracy: String?
    public let referenceSetId: String?
    public let referenceSourceVersion: String?
    public let reference2020Equivalence: String?
    public let sourceNote: String?
    public init(items: [HeightPoint], stationId: String? = nil, timezone: String? = nil, method: PredictionMethod? = nil, setId: String? = nil, conventionId: String? = nil, astroTableId: String? = nil, referenceStationId: String? = nil, referenceBin: Int64? = nil, datum: String? = nil, datumName: String? = nil, datumKind: String? = nil, datumUncertaintyM: Double? = nil, tz: String? = nil, tzVersion: String? = nil, release: String? = nil, algorithm: String? = nil, offsetId: String? = nil, offsetSource: String? = nil, offsetSourceVersion: String? = nil, historicalOffsets: Bool = false, currentValidity: String? = nil, currentAccuracy: String? = nil, referenceSetId: String? = nil, referenceSourceVersion: String? = nil, reference2020Equivalence: String? = nil, sourceNote: String? = nil) {
        self.items = items
        self.stationId = stationId
        self.timezone = timezone
        self.method = method
        self.setId = setId
        self.conventionId = conventionId
        self.astroTableId = astroTableId
        self.referenceStationId = referenceStationId
        self.referenceBin = referenceBin
        self.datum = datum
        self.datumName = datumName
        self.datumKind = datumKind
        self.datumUncertaintyM = datumUncertaintyM
        self.tz = tz
        self.tzVersion = tzVersion
        self.release = release
        self.algorithm = algorithm
        self.offsetId = offsetId
        self.offsetSource = offsetSource
        self.offsetSourceVersion = offsetSourceVersion
        self.historicalOffsets = historicalOffsets
        self.currentValidity = currentValidity
        self.currentAccuracy = currentAccuracy
        self.referenceSetId = referenceSetId
        self.referenceSourceVersion = referenceSourceVersion
        self.reference2020Equivalence = reference2020Equivalence
        self.sourceNote = sourceNote
    }
    public func toLocal(tz: String = "station") throws -> HeightSeries {
        try localize(self, tz: tz)
    }
}

public struct ExtremeList: Sendable, Equatable {
    public let items: [Extreme]
    public let stationId: String?
    public let timezone: String?
    public let method: PredictionMethod?
    public let setId: String?
    public let conventionId: String?
    public let astroTableId: String?
    public let referenceStationId: String?
    public let referenceBin: Int64?
    public let datum: String?
    public let datumName: String?
    public let datumKind: String?
    public let datumUncertaintyM: Double?
    public let tz: String?
    public let tzVersion: String?
    public let release: String?
    public let algorithm: String?
    public let offsetId: String?
    public let offsetSource: String?
    public let offsetSourceVersion: String?
    public let historicalOffsets: Bool
    public let currentValidity: String?
    public let currentAccuracy: String?
    public let referenceSetId: String?
    public let referenceSourceVersion: String?
    public let reference2020Equivalence: String?
    public let sourceNote: String?
    public init(items: [Extreme], stationId: String? = nil, timezone: String? = nil, method: PredictionMethod? = nil, setId: String? = nil, conventionId: String? = nil, astroTableId: String? = nil, referenceStationId: String? = nil, referenceBin: Int64? = nil, datum: String? = nil, datumName: String? = nil, datumKind: String? = nil, datumUncertaintyM: Double? = nil, tz: String? = nil, tzVersion: String? = nil, release: String? = nil, algorithm: String? = nil, offsetId: String? = nil, offsetSource: String? = nil, offsetSourceVersion: String? = nil, historicalOffsets: Bool = false, currentValidity: String? = nil, currentAccuracy: String? = nil, referenceSetId: String? = nil, referenceSourceVersion: String? = nil, reference2020Equivalence: String? = nil, sourceNote: String? = nil) {
        self.items = items
        self.stationId = stationId
        self.timezone = timezone
        self.method = method
        self.setId = setId
        self.conventionId = conventionId
        self.astroTableId = astroTableId
        self.referenceStationId = referenceStationId
        self.referenceBin = referenceBin
        self.datum = datum
        self.datumName = datumName
        self.datumKind = datumKind
        self.datumUncertaintyM = datumUncertaintyM
        self.tz = tz
        self.tzVersion = tzVersion
        self.release = release
        self.algorithm = algorithm
        self.offsetId = offsetId
        self.offsetSource = offsetSource
        self.offsetSourceVersion = offsetSourceVersion
        self.historicalOffsets = historicalOffsets
        self.currentValidity = currentValidity
        self.currentAccuracy = currentAccuracy
        self.referenceSetId = referenceSetId
        self.referenceSourceVersion = referenceSourceVersion
        self.reference2020Equivalence = reference2020Equivalence
        self.sourceNote = sourceNote
    }
    public func toLocal(tz: String = "station") throws -> ExtremeList {
        try localize(self, tz: tz)
    }
}

public struct CurrentSeries: Sendable, Equatable {
    public let items: [CurrentPoint]
    public let stationId: String?
    public let timezone: String?
    public let method: PredictionMethod?
    public let setId: String?
    public let conventionId: String?
    public let astroTableId: String?
    public let referenceStationId: String?
    public let referenceBin: Int64?
    public let datum: String?
    public let datumName: String?
    public let datumKind: String?
    public let datumUncertaintyM: Double?
    public let tz: String?
    public let tzVersion: String?
    public let release: String?
    public let algorithm: String?
    public let binNumber: Int64?
    public init(items: [CurrentPoint], stationId: String? = nil, timezone: String? = nil, method: PredictionMethod? = nil, setId: String? = nil, conventionId: String? = nil, astroTableId: String? = nil, referenceStationId: String? = nil, referenceBin: Int64? = nil, datum: String? = nil, datumName: String? = nil, datumKind: String? = nil, datumUncertaintyM: Double? = nil, tz: String? = nil, tzVersion: String? = nil, release: String? = nil, algorithm: String? = nil, binNumber: Int64? = nil) {
        self.items = items
        self.stationId = stationId
        self.timezone = timezone
        self.method = method
        self.setId = setId
        self.conventionId = conventionId
        self.astroTableId = astroTableId
        self.referenceStationId = referenceStationId
        self.referenceBin = referenceBin
        self.datum = datum
        self.datumName = datumName
        self.datumKind = datumKind
        self.datumUncertaintyM = datumUncertaintyM
        self.tz = tz
        self.tzVersion = tzVersion
        self.release = release
        self.algorithm = algorithm
        self.binNumber = binNumber
    }
    public func toLocal(tz: String = "station") throws -> CurrentSeries {
        try localize(self, tz: tz)
    }
}

public struct CurrentEventList: Sendable, Equatable {
    public let items: [CurrentEvent]
    public let stationId: String?
    public let timezone: String?
    public let method: PredictionMethod?
    public let setId: String?
    public let conventionId: String?
    public let astroTableId: String?
    public let referenceStationId: String?
    public let referenceBin: Int64?
    public let datum: String?
    public let datumName: String?
    public let datumKind: String?
    public let datumUncertaintyM: Double?
    public let tz: String?
    public let tzVersion: String?
    public let release: String?
    public let algorithm: String?
    public let binNumber: Int64?
    public let omittedEventTypes: [CurrentEventType]?
    public init(items: [CurrentEvent], stationId: String? = nil, timezone: String? = nil, method: PredictionMethod? = nil, setId: String? = nil, conventionId: String? = nil, astroTableId: String? = nil, referenceStationId: String? = nil, referenceBin: Int64? = nil, datum: String? = nil, datumName: String? = nil, datumKind: String? = nil, datumUncertaintyM: Double? = nil, tz: String? = nil, tzVersion: String? = nil, release: String? = nil, algorithm: String? = nil, binNumber: Int64? = nil, omittedEventTypes: [CurrentEventType]? = nil) {
        self.items = items
        self.stationId = stationId
        self.timezone = timezone
        self.method = method
        self.setId = setId
        self.conventionId = conventionId
        self.astroTableId = astroTableId
        self.referenceStationId = referenceStationId
        self.referenceBin = referenceBin
        self.datum = datum
        self.datumName = datumName
        self.datumKind = datumKind
        self.datumUncertaintyM = datumUncertaintyM
        self.tz = tz
        self.tzVersion = tzVersion
        self.release = release
        self.algorithm = algorithm
        self.binNumber = binNumber
        self.omittedEventTypes = omittedEventTypes
    }
    public func toLocal(tz: String = "station") throws -> CurrentEventList {
        try localize(self, tz: tz)
    }
}

public struct DatumLevel: Sendable, Equatable {
    public let key: String?
    public let valueM: Double
    public let aboveChartM: Double?
    public let kind: String?
    public let method: String?
    public let sourceName: String?
    public let epoch: JSONValue
    public let dataSpan: JSONValue
    public let controlStationId: String?
    public let controlSetId: String?
    public let controlSourceId: String?
    public let uncertaintyM: Double?
    public let uncertaintyBasis: String?
    public let flags: [String]
}
public struct DatumInfo: Sendable, Equatable {
    public let setId: String?
    public let zero: String?
    public let zeroName: String?
    public let chartDatum: String?
    public let mslOffsetM: Double?
    public let levels: [DatumLevel]
}
public struct Ranges: Sendable, Equatable {
    public let mn: Double?
    public let gt: Double?
    public let dhq: Double?
    public let dlq: Double?
}

public enum DatumsResult: Sendable, Equatable {
    case one(DatumInfo?)
    case all([DatumInfo])
}
