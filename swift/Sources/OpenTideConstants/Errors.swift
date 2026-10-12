import Foundation
public enum OpenTideConstantsError: Error, Sendable {
    case network(String, [String: JSONValue] = [:])
    case releaseNotFound(String, [String: JSONValue] = [:])
    case offlineUnavailable(String, [String: JSONValue] = [:])
    case checksumMismatch(String, [String: JSONValue] = [:])
    case unsupportedFormat(String, [String: JSONValue] = [:])
    case readerTooOld(String, [String: JSONValue] = [:])
    case invalidRelease(String, [String: JSONValue] = [:])
    case stationNotFound(String, [String: JSONValue] = [:])
    case stationRemoved(String, [String: JSONValue] = [:])
    case pinnedRelease(String, [String: JSONValue] = [:])
    case cache(String, [String: JSONValue] = [:])
    case fileExists(String, [String: JSONValue] = [:])
    case io(String, [String: JSONValue] = [:])
    case invalidArgument(String, [String: JSONValue] = [:])
    case noConstants(String, [String: JSONValue] = [:])
    case quantityMismatch(String, [String: JSONValue] = [:])
    case unsupportedConvention(String, [String: JSONValue] = [:])
    case noAstroTable(String, [String: JSONValue] = [:])
    case unsupportedConstituent(String, [String: JSONValue] = [:])
    case timeOutOfRange(String, [String: JSONValue] = [:])
    case datumUnavailable(String, [String: JSONValue] = [:])
    case binNotFound(String, [String: JSONValue] = [:])
    case extremesOnly(String, [String: JSONValue] = [:])
    case localTimeUnavailable(String, [String: JSONValue] = [:])
    case unknownTimeZone(String, [String: JSONValue] = [:])
    case referenceUnavailable(String, [String: JSONValue] = [:])
    case historicalOffsetsExcluded(String, [String: JSONValue] = [:])
    public var code: String { switch self {
    case .network: return "network"
    case .releaseNotFound: return "release_not_found"
    case .offlineUnavailable: return "offline_unavailable"
    case .checksumMismatch: return "checksum_mismatch"
    case .unsupportedFormat: return "unsupported_format"
    case .readerTooOld: return "reader_too_old"
    case .invalidRelease: return "invalid_release"
    case .stationNotFound: return "station_not_found"
    case .stationRemoved: return "station_removed"
    case .pinnedRelease: return "pinned_release"
    case .cache: return "cache"
    case .fileExists: return "file_exists"
    case .io: return "io"
    case .invalidArgument: return "invalid_argument"
    case .noConstants: return "no_constants"
    case .quantityMismatch: return "quantity_mismatch"
    case .unsupportedConvention: return "unsupported_convention"
    case .noAstroTable: return "no_astro_table"
    case .unsupportedConstituent: return "unsupported_constituent"
    case .timeOutOfRange: return "time_out_of_range"
    case .datumUnavailable: return "datum_unavailable"
    case .binNotFound: return "bin_not_found"
    case .extremesOnly: return "extremes_only"
    case .localTimeUnavailable: return "local_time_unavailable"
    case .unknownTimeZone: return "unknown_time_zone"
    case .referenceUnavailable: return "reference_unavailable"
    case .historicalOffsetsExcluded: return "historical_offsets_excluded"
    } }
    public var message: String { switch self {
    case .network(let message, _): return message
    case .releaseNotFound(let message, _): return message
    case .offlineUnavailable(let message, _): return message
    case .checksumMismatch(let message, _): return message
    case .unsupportedFormat(let message, _): return message
    case .readerTooOld(let message, _): return message
    case .invalidRelease(let message, _): return message
    case .stationNotFound(let message, _): return message
    case .stationRemoved(let message, _): return message
    case .pinnedRelease(let message, _): return message
    case .cache(let message, _): return message
    case .fileExists(let message, _): return message
    case .io(let message, _): return message
    case .invalidArgument(let message, _): return message
    case .noConstants(let message, _): return message
    case .quantityMismatch(let message, _): return message
    case .unsupportedConvention(let message, _): return message
    case .noAstroTable(let message, _): return message
    case .unsupportedConstituent(let message, _): return message
    case .timeOutOfRange(let message, _): return message
    case .datumUnavailable(let message, _): return message
    case .binNotFound(let message, _): return message
    case .extremesOnly(let message, _): return message
    case .localTimeUnavailable(let message, _): return message
    case .unknownTimeZone(let message, _): return message
    case .referenceUnavailable(let message, _): return message
    case .historicalOffsetsExcluded(let message, _): return message
    } }
    public var fields: [String: JSONValue] { switch self {
    case .network(_, let fields): return fields
    case .releaseNotFound(_, let fields): return fields
    case .offlineUnavailable(_, let fields): return fields
    case .checksumMismatch(_, let fields): return fields
    case .unsupportedFormat(_, let fields): return fields
    case .readerTooOld(_, let fields): return fields
    case .invalidRelease(_, let fields): return fields
    case .stationNotFound(_, let fields): return fields
    case .stationRemoved(_, let fields): return fields
    case .pinnedRelease(_, let fields): return fields
    case .cache(_, let fields): return fields
    case .fileExists(_, let fields): return fields
    case .io(_, let fields): return fields
    case .invalidArgument(_, let fields): return fields
    case .noConstants(_, let fields): return fields
    case .quantityMismatch(_, let fields): return fields
    case .unsupportedConvention(_, let fields): return fields
    case .noAstroTable(_, let fields): return fields
    case .unsupportedConstituent(_, let fields): return fields
    case .timeOutOfRange(_, let fields): return fields
    case .datumUnavailable(_, let fields): return fields
    case .binNotFound(_, let fields): return fields
    case .extremesOnly(_, let fields): return fields
    case .localTimeUnavailable(_, let fields): return fields
    case .unknownTimeZone(_, let fields): return fields
    case .referenceUnavailable(_, let fields): return fields
    case .historicalOffsetsExcluded(_, let fields): return fields
    } }
}
