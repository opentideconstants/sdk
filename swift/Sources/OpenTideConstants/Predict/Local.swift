import Foundation

internal func localZone(_ timezone: String?, _ requested: String) throws -> (String, TimeZone, String?) {
    let zone = requested == "station" ? timezone : requested
    guard let zone, zone.utf8.count <= 255,
          zone.range(of: #"^[A-Za-z0-9_+-]+(?:/[A-Za-z0-9_+-]+)*$"#, options: .regularExpression) != nil,
          !zone.hasPrefix("posix/"), !zone.hasPrefix("right/"),
          !["posixrules", "localtime", "Factory"].contains(zone),
          let rules = TimeZone(identifier: zone) else {
        throw OpenTideConstantsError.unknownTimeZone("unknown time zone", ["zone": zone.map(JSONValue.string) ?? .null])
    }
    var version: String?
    for path in ["/usr/share/zoneinfo/tzdata.zi", "/usr/share/zoneinfo/+VERSION"] {
        if let contents = try? String(contentsOfFile: path, encoding: .utf8), let first = contents.split(separator: "\n").first {
            version = first.hasPrefix("# version ") ? String(first.dropFirst(10)) : String(first)
            break
        }
    }
    return (zone, rules, version)
}
internal func localFields(_ time: Date, _ zone: TimeZone) -> (String, Int64) {
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = zone
    let c = calendar.dateComponents([.year, .month, .day, .hour, .minute, .second], from: time)
    let offset = zone.secondsFromGMT(for: time)
    let n = abs(offset)
    var suffix = String(format: "%@%02d:%02d", offset >= 0 ? "+" : "-", n / 3600, n % 3600 / 60)
    if n % 60 != 0 { suffix += String(format: ":%02d", n % 60) }
    return (String(format: "%04d-%02d-%02dT%02d:%02d:%02d", c.year!, c.month!, c.day!, c.hour!, c.minute!, c.second!) + suffix, Int64(offset))
}
internal func localize(_ result: HeightSeries, tz: String) throws -> HeightSeries {
    let (name, zone, version) = try localZone(result.timezone, tz)
    let items = result.items.map { item in
        let (stamp, offset) = localFields(item.time, zone)
        return HeightPoint(time: item.time, heightM: item.heightM, localTime: stamp, utcOffsetS: offset, units: item.units)
    }
    return HeightSeries(items: items, stationId: result.stationId, timezone: result.timezone, method: result.method, setId: result.setId, conventionId: result.conventionId, astroTableId: result.astroTableId, referenceStationId: result.referenceStationId, referenceBin: result.referenceBin, datum: result.datum, datumName: result.datumName, datumKind: result.datumKind, datumUncertaintyM: result.datumUncertaintyM, tz: name, tzVersion: version, release: result.release, algorithm: result.algorithm, offsetId: result.offsetId, offsetSource: result.offsetSource, offsetSourceVersion: result.offsetSourceVersion, historicalOffsets: result.historicalOffsets, currentValidity: result.currentValidity, currentAccuracy: result.currentAccuracy, referenceSetId: result.referenceSetId, referenceSourceVersion: result.referenceSourceVersion, reference2020Equivalence: result.reference2020Equivalence, sourceNote: result.sourceNote, units: result.units)
}

internal func localize(_ result: ExtremeList, tz: String) throws -> ExtremeList {
    let (name, zone, version) = try localZone(result.timezone, tz)
    let items = result.items.map { item in
        let (stamp, offset) = localFields(item.time, zone)
        return Extreme(time: item.time, type: item.type, heightM: item.heightM, localTime: stamp, utcOffsetS: offset, units: item.units)
    }
    return ExtremeList(items: items, stationId: result.stationId, timezone: result.timezone, method: result.method, setId: result.setId, conventionId: result.conventionId, astroTableId: result.astroTableId, referenceStationId: result.referenceStationId, referenceBin: result.referenceBin, datum: result.datum, datumName: result.datumName, datumKind: result.datumKind, datumUncertaintyM: result.datumUncertaintyM, tz: name, tzVersion: version, release: result.release, algorithm: result.algorithm, offsetId: result.offsetId, offsetSource: result.offsetSource, offsetSourceVersion: result.offsetSourceVersion, historicalOffsets: result.historicalOffsets, currentValidity: result.currentValidity, currentAccuracy: result.currentAccuracy, referenceSetId: result.referenceSetId, referenceSourceVersion: result.referenceSourceVersion, reference2020Equivalence: result.reference2020Equivalence, sourceNote: result.sourceNote, units: result.units)
}

internal func localize(_ result: CurrentSeries, tz: String) throws -> CurrentSeries {
    let (name, zone, version) = try localZone(result.timezone, tz)
    let items = result.items.map { item in
        let (stamp, offset) = localFields(item.time, zone)
        return CurrentPoint(time: item.time, velocityMajorMs: item.velocityMajorMs, velocityMinorMs: item.velocityMinorMs, speedMs: item.speedMs, directionDeg: item.directionDeg, localTime: stamp, utcOffsetS: offset, units: item.units)
    }
    return CurrentSeries(items: items, stationId: result.stationId, timezone: result.timezone, method: result.method, setId: result.setId, conventionId: result.conventionId, astroTableId: result.astroTableId, referenceStationId: result.referenceStationId, referenceBin: result.referenceBin, datum: result.datum, datumName: result.datumName, datumKind: result.datumKind, datumUncertaintyM: result.datumUncertaintyM, tz: name, tzVersion: version, release: result.release, algorithm: result.algorithm, binNumber: result.binNumber, units: result.units)
}

internal func localize(_ result: CurrentEventList, tz: String) throws -> CurrentEventList {
    let (name, zone, version) = try localZone(result.timezone, tz)
    let items = result.items.map { item in
        let (stamp, offset) = localFields(item.time, zone)
        return CurrentEvent(time: item.time, type: item.type, velocityMs: item.velocityMs, directionDeg: item.directionDeg, localTime: stamp, utcOffsetS: offset, units: item.units)
    }
    return CurrentEventList(items: items, stationId: result.stationId, timezone: result.timezone, method: result.method, setId: result.setId, conventionId: result.conventionId, astroTableId: result.astroTableId, referenceStationId: result.referenceStationId, referenceBin: result.referenceBin, datum: result.datum, datumName: result.datumName, datumKind: result.datumKind, datumUncertaintyM: result.datumUncertaintyM, tz: name, tzVersion: version, release: result.release, algorithm: result.algorithm, binNumber: result.binNumber, omittedEventTypes: result.omittedEventTypes, units: result.units)
}

