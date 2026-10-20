import Foundation

public struct HeightPoint: Sendable, Equatable {
    public let units: String
    public let time: Date
    public let heightM: Double
    public let localTime: String?
    public let utcOffsetS: Int64?
    public init(time: Date, heightM: Double, localTime: String? = nil, utcOffsetS: Int64? = nil, units: String = "meters") {
        self.units = units
        self.time = time
        self.heightM = heightM
        self.localTime = localTime
        self.utcOffsetS = utcOffsetS
    }
    public func localDatetime() -> Date? { localTime == nil ? nil : time }
    public var height: Double { units == "feet" ? heightM / 0.3048 : heightM }
    internal func withUnits(_ units: String) -> HeightPoint {
        HeightPoint(time: time, heightM: heightM, localTime: localTime, utcOffsetS: utcOffsetS, units: units)
    }
}

public struct Extreme: Sendable, Equatable {
    public let units: String
    public let time: Date
    public let type: ExtremeType
    public let heightM: Double
    public let localTime: String?
    public let utcOffsetS: Int64?
    public init(time: Date, type: ExtremeType, heightM: Double, localTime: String? = nil, utcOffsetS: Int64? = nil, units: String = "meters") {
        self.units = units
        self.time = time
        self.type = type
        self.heightM = heightM
        self.localTime = localTime
        self.utcOffsetS = utcOffsetS
    }
    public func localDatetime() -> Date? { localTime == nil ? nil : time }
    public var height: Double { units == "feet" ? heightM / 0.3048 : heightM }
    internal func withUnits(_ units: String) -> Extreme {
        Extreme(time: time, type: type, heightM: heightM, localTime: localTime, utcOffsetS: utcOffsetS, units: units)
    }
}

public struct CurrentPoint: Sendable, Equatable {
    public let units: String
    public let time: Date
    public let velocityMajorMs: Double
    public let velocityMinorMs: Double
    public let speedMs: Double
    public let directionDeg: Double?
    public let localTime: String?
    public let utcOffsetS: Int64?
    public init(time: Date, velocityMajorMs: Double, velocityMinorMs: Double, speedMs: Double, directionDeg: Double?, localTime: String? = nil, utcOffsetS: Int64? = nil, units: String = "m/s") {
        self.units = units
        self.time = time
        self.velocityMajorMs = velocityMajorMs
        self.velocityMinorMs = velocityMinorMs
        self.speedMs = speedMs
        self.directionDeg = directionDeg
        self.localTime = localTime
        self.utcOffsetS = utcOffsetS
    }
    public func localDatetime() -> Date? { localTime == nil ? nil : time }
    public var velocityMajor: Double { units == "knots" ? velocityMajorMs / (1852.0 / 3600.0) : velocityMajorMs }
    public var velocityMinor: Double { units == "knots" ? velocityMinorMs / (1852.0 / 3600.0) : velocityMinorMs }
    public var speed: Double { units == "knots" ? speedMs / (1852.0 / 3600.0) : speedMs }
    internal func withUnits(_ units: String) -> CurrentPoint {
        CurrentPoint(time: time, velocityMajorMs: velocityMajorMs, velocityMinorMs: velocityMinorMs, speedMs: speedMs, directionDeg: directionDeg, localTime: localTime, utcOffsetS: utcOffsetS, units: units)
    }
}

public struct CurrentEvent: Sendable, Equatable {
    public let units: String
    public let time: Date
    public let type: CurrentEventType
    public let velocityMs: Double
    public let directionDeg: Double?
    public let localTime: String?
    public let utcOffsetS: Int64?
    public init(time: Date, type: CurrentEventType, velocityMs: Double, directionDeg: Double?, localTime: String? = nil, utcOffsetS: Int64? = nil, units: String = "m/s") {
        self.units = units
        self.time = time
        self.type = type
        self.velocityMs = velocityMs
        self.directionDeg = directionDeg
        self.localTime = localTime
        self.utcOffsetS = utcOffsetS
    }
    public func localDatetime() -> Date? { localTime == nil ? nil : time }
    public var velocity: Double { units == "knots" ? velocityMs / (1852.0 / 3600.0) : velocityMs }
    internal func withUnits(_ units: String) -> CurrentEvent {
        CurrentEvent(time: time, type: type, velocityMs: velocityMs, directionDeg: directionDeg, localTime: localTime, utcOffsetS: utcOffsetS, units: units)
    }
}

public struct HeightSeries: Sendable, Equatable {
    public let units: String
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
    public init(items: [HeightPoint], stationId: String? = nil, timezone: String? = nil, method: PredictionMethod? = nil, setId: String? = nil, conventionId: String? = nil, astroTableId: String? = nil, referenceStationId: String? = nil, referenceBin: Int64? = nil, datum: String? = nil, datumName: String? = nil, datumKind: String? = nil, datumUncertaintyM: Double? = nil, tz: String? = nil, tzVersion: String? = nil, release: String? = nil, algorithm: String? = nil, offsetId: String? = nil, offsetSource: String? = nil, offsetSourceVersion: String? = nil, historicalOffsets: Bool = false, currentValidity: String? = nil, currentAccuracy: String? = nil, referenceSetId: String? = nil, referenceSourceVersion: String? = nil, reference2020Equivalence: String? = nil, sourceNote: String? = nil, units: String = "meters") {
        self.units = units
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
    internal func withUnits(_ units: String) -> HeightSeries {
        HeightSeries(items: items.map { $0.withUnits(units) }, stationId: stationId, timezone: timezone, method: method, setId: setId, conventionId: conventionId, astroTableId: astroTableId, referenceStationId: referenceStationId, referenceBin: referenceBin, datum: datum, datumName: datumName, datumKind: datumKind, datumUncertaintyM: datumUncertaintyM, tz: tz, tzVersion: tzVersion, release: release, algorithm: algorithm, offsetId: offsetId, offsetSource: offsetSource, offsetSourceVersion: offsetSourceVersion, historicalOffsets: historicalOffsets, currentValidity: currentValidity, currentAccuracy: currentAccuracy, referenceSetId: referenceSetId, referenceSourceVersion: referenceSourceVersion, reference2020Equivalence: reference2020Equivalence, sourceNote: sourceNote, units: units)
    }
}

public struct ExtremeList: Sendable, Equatable {
    public let units: String
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
    public init(items: [Extreme], stationId: String? = nil, timezone: String? = nil, method: PredictionMethod? = nil, setId: String? = nil, conventionId: String? = nil, astroTableId: String? = nil, referenceStationId: String? = nil, referenceBin: Int64? = nil, datum: String? = nil, datumName: String? = nil, datumKind: String? = nil, datumUncertaintyM: Double? = nil, tz: String? = nil, tzVersion: String? = nil, release: String? = nil, algorithm: String? = nil, offsetId: String? = nil, offsetSource: String? = nil, offsetSourceVersion: String? = nil, historicalOffsets: Bool = false, currentValidity: String? = nil, currentAccuracy: String? = nil, referenceSetId: String? = nil, referenceSourceVersion: String? = nil, reference2020Equivalence: String? = nil, sourceNote: String? = nil, units: String = "meters") {
        self.units = units
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
    internal func withUnits(_ units: String) -> ExtremeList {
        ExtremeList(items: items.map { $0.withUnits(units) }, stationId: stationId, timezone: timezone, method: method, setId: setId, conventionId: conventionId, astroTableId: astroTableId, referenceStationId: referenceStationId, referenceBin: referenceBin, datum: datum, datumName: datumName, datumKind: datumKind, datumUncertaintyM: datumUncertaintyM, tz: tz, tzVersion: tzVersion, release: release, algorithm: algorithm, offsetId: offsetId, offsetSource: offsetSource, offsetSourceVersion: offsetSourceVersion, historicalOffsets: historicalOffsets, currentValidity: currentValidity, currentAccuracy: currentAccuracy, referenceSetId: referenceSetId, referenceSourceVersion: referenceSourceVersion, reference2020Equivalence: reference2020Equivalence, sourceNote: sourceNote, units: units)
    }
}

public struct CurrentSeries: Sendable, Equatable {
    public let units: String
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
    public init(items: [CurrentPoint], stationId: String? = nil, timezone: String? = nil, method: PredictionMethod? = nil, setId: String? = nil, conventionId: String? = nil, astroTableId: String? = nil, referenceStationId: String? = nil, referenceBin: Int64? = nil, datum: String? = nil, datumName: String? = nil, datumKind: String? = nil, datumUncertaintyM: Double? = nil, tz: String? = nil, tzVersion: String? = nil, release: String? = nil, algorithm: String? = nil, binNumber: Int64? = nil, units: String = "m/s") {
        self.units = units
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
    internal func withUnits(_ units: String) -> CurrentSeries {
        CurrentSeries(items: items.map { $0.withUnits(units) }, stationId: stationId, timezone: timezone, method: method, setId: setId, conventionId: conventionId, astroTableId: astroTableId, referenceStationId: referenceStationId, referenceBin: referenceBin, datum: datum, datumName: datumName, datumKind: datumKind, datumUncertaintyM: datumUncertaintyM, tz: tz, tzVersion: tzVersion, release: release, algorithm: algorithm, binNumber: binNumber, units: units)
    }
}

public struct CurrentEventList: Sendable, Equatable {
    public let units: String
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
    public init(items: [CurrentEvent], stationId: String? = nil, timezone: String? = nil, method: PredictionMethod? = nil, setId: String? = nil, conventionId: String? = nil, astroTableId: String? = nil, referenceStationId: String? = nil, referenceBin: Int64? = nil, datum: String? = nil, datumName: String? = nil, datumKind: String? = nil, datumUncertaintyM: Double? = nil, tz: String? = nil, tzVersion: String? = nil, release: String? = nil, algorithm: String? = nil, binNumber: Int64? = nil, omittedEventTypes: [CurrentEventType]? = nil, units: String = "m/s") {
        self.units = units
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
    internal func withUnits(_ units: String) -> CurrentEventList {
        CurrentEventList(items: items.map { $0.withUnits(units) }, stationId: stationId, timezone: timezone, method: method, setId: setId, conventionId: conventionId, astroTableId: astroTableId, referenceStationId: referenceStationId, referenceBin: referenceBin, datum: datum, datumName: datumName, datumKind: datumKind, datumUncertaintyM: datumUncertaintyM, tz: tz, tzVersion: tzVersion, release: release, algorithm: algorithm, binNumber: binNumber, omittedEventTypes: omittedEventTypes, units: units)
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
    public let fallback: JSONValue?
    public init(key: String?, valueM: Double, aboveChartM: Double?, kind: String?, method: String?, sourceName: String?, epoch: JSONValue, dataSpan: JSONValue, controlStationId: String?, controlSetId: String?, controlSourceId: String?, uncertaintyM: Double?, uncertaintyBasis: String?, flags: [String], fallback: JSONValue? = nil) {
        self.key = key
        self.valueM = valueM
        self.aboveChartM = aboveChartM
        self.kind = kind
        self.method = method
        self.sourceName = sourceName
        self.epoch = epoch
        self.dataSpan = dataSpan
        self.controlStationId = controlStationId
        self.controlSetId = controlSetId
        self.controlSourceId = controlSourceId
        self.uncertaintyM = uncertaintyM
        self.uncertaintyBasis = uncertaintyBasis
        self.flags = flags
        self.fallback = fallback
    }
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

internal func validatePredictionUnits(_ units: String, height: Bool) throws {
    guard (height ? ["meters", "feet"] : ["m/s", "knots"]).contains(units) else {
        throw OpenTideConstantsError.invalidArgument("unsupported prediction units")
    }
}
