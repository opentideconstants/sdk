import Foundation

internal func predictionInstant(_ value: Date) throws -> Double {
    let seconds = value.timeIntervalSince1970
    guard seconds.isFinite, seconds >= -62135596800, seconds < 253402300800 else {
        throw OpenTideConstantsError.invalidArgument("an instant must be a finite Date in years 1 through 9999")
    }
    return floor(seconds)
}
internal func utcYear(_ seconds: Double) -> Int64 {
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = TimeZone(secondsFromGMT: 0)!
    return Int64(calendar.component(.year, from: Date(timeIntervalSince1970: seconds)))
}
internal func yearStart(_ year: Int64) -> Double {
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = TimeZone(secondsFromGMT: 0)!
    return calendar.date(from: DateComponents(year: Int(year), month: 1, day: 1))!.timeIntervalSince1970
}
internal func reducedAngle(_ value: Double) -> Double {
    let reduced = value - 360.0 * floor(value / 360.0)
    return reduced == 360.0 ? 0.0 : reduced
}

public struct AstroTable: Sendable, Equatable {
    internal let raw: JSONValue
    internal let first: Int64
    internal let last: Int64
    public var validRange: [Int64] { [first, last] }
    internal init(_ raw: JSONValue) throws {
        let id = raw["astro_table_id"].string ?? ""
        func bad(_ detail: String) -> OpenTideConstantsError {
            .invalidArgument("astro table \"\(id)\" \(detail)")
        }
        guard let first = raw["first_year"].integer, let last = raw["last_year"].integer, first <= last else {
            throw bad("first_year and last_year must be ordered integers")
        }
        guard case .object(let rows) = raw["constituents"] else { throw bad("constituents must be an object") }
        let (width, overflow) = last.subtractingReportingOverflow(first)
        guard !overflow, width < Int64.max else { throw bad("year range is too large") }
        for (name, row) in rows {
            guard case .object = row else { throw bad("row \"\(name)\": must be an object") }
            for key in ["v0u_deg", "f"] {
                guard case .array(let values) = row[key], Int64(values.count) == width + 1,
                      values.allSatisfy({ $0.number?.isFinite == true }) else {
                    throw bad("row \"\(name)\": \(key) must contain \(width + 1) numbers")
                }
            }
            if !row["speed_deg_per_hour"].isNull {
                guard let speed = row["speed_deg_per_hour"].number, speed.isFinite, speed >= 0 else {
                    throw bad("row \"\(name)\": speed_deg_per_hour must be a nonnegative number")
                }
            }
        }
        self.raw = raw
        self.first = first
        self.last = last
    }
    internal func index(_ year: Int64) throws -> Int {
        guard first <= year, year <= last else {
            throw OpenTideConstantsError.timeOutOfRange("year \(year) is outside the astro table", ["first_year": .integer(first), "last_year": .integer(last)])
        }
        return Int(year - first)
    }
    internal func row(_ name: String) throws -> JSONValue {
        let row = raw["constituents"][name]
        guard !row.isNull, row["speed_deg_per_hour"].number != nil else {
            throw OpenTideConstantsError.unsupportedConstituent("unsupported constituent \(name)", ["constituent": .string(name)])
        }
        return row
    }
    public func equilibriumArgument(name: String, at: Date) throws -> Double {
        let seconds = try predictionInstant(at)
        let row = try row(name)
        let year = utcYear(seconds)
        let i = try index(year)
        return reducedAngle(row["v0u_deg"].array[i].number! + row["speed_deg_per_hour"].number! * ((seconds - yearStart(year)) / 3600.0))
    }
    public func nodeFactor(name: String, at: Date) throws -> Double {
        let seconds = try predictionInstant(at)
        let row = try row(name)
        return try row["f"].array[index(utcYear(seconds))].number!
    }
    public func equilibriumForYear(name: String, year: Int64) throws -> Double {
        let row = try row(name)
        return try row["v0u_deg"].array[index(year)].number!
    }
    public func nodeFactorForYear(name: String, year: Int64) throws -> Double {
        let row = try row(name)
        return try row["f"].array[index(year)].number!
    }
}
