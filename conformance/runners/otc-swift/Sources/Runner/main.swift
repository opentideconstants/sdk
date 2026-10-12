import Foundation
import OpenTideConstants

private enum HeldPrediction {
    case heights(HeightSeries), extremes(ExtremeList), currents(CurrentSeries), events(CurrentEventList)
    func encoded() -> JSONValue {
        switch self {
        case .heights(let value): return Runner.prediction(value)
        case .extremes(let value): return Runner.prediction(value)
        case .currents(let value): return Runner.prediction(value)
        case .events(let value): return Runner.prediction(value)
        }
    }
    func toLocal(_ tz: String) throws -> HeldPrediction {
        switch self {
        case .heights(let value): return .heights(try value.toLocal(tz: tz))
        case .extremes(let value): return .extremes(try value.toLocal(tz: tz))
        case .currents(let value): return .currents(try value.toLocal(tz: tz))
        case .events(let value): return .events(try value.toLocal(tz: tz))
        }
    }
}

@main struct Runner {
    static let predictionFields = ["station_id", "timezone", "method", "set_id", "convention_id", "astro_table_id", "reference_station_id", "reference_bin", "datum", "datum_name", "datum_kind", "datum_uncertainty_m", "bin_number", "omitted_event_types", "tz", "tz_version", "release", "algorithm"]
    static func emit(_ value: JSONValue) {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        if let data = try? encoder.encode(value), let line = String(data: data, encoding: .utf8) {
            print(line)
            fflush(nil)
        }
    }
    static func snake(_ value: String) -> String {
        value.replacingOccurrences(of: #"([a-z0-9])([A-Z])"#, with: "$1_$2", options: .regularExpression).lowercased()
    }
    static func plain<T>(_ value: T) -> JSONValue {
        if let value = value as? JSONValue { return value }
        let mirror = Mirror(reflecting: value)
        if mirror.displayStyle == .optional { return mirror.children.first.map { plain($0.value) } ?? .null }
        if let value = value as? String { return .string(value) }
        if let value = value as? Bool { return .bool(value) }
        if let value = value as? Int64 { return .integer(value) }
        if let value = value as? Int { return .integer(Int64(value)) }
        if let value = value as? Double { return value.isFinite ? .number(value) : .null }
        if let value = value as? Date {
            let formatter = ISO8601DateFormatter()
            formatter.timeZone = TimeZone(secondsFromGMT: 0)
            formatter.formatOptions = [.withInternetDateTime]
            return .string(formatter.string(from: value))
        }
        if let value = value as? any RawRepresentable, let raw = value.rawValue as? String { return .string(raw) }
        if mirror.displayStyle == .collection { return .array(mirror.children.map { plain($0.value) }) }
        var result: [String: JSONValue] = [:]
        for child in mirror.children { if let label = child.label { result[snake(label)] = plain(child.value) } }
        return .object(result)
    }
    static func prediction(_ value: Any) -> JSONValue {
        let raw = plain(value)
        var result = Dictionary(uniqueKeysWithValues: predictionFields.map { ($0, raw[$0]) })
        result["items"] = raw["items"]
        return .object(result)
    }
    static func instant(_ value: JSONValue) throws -> Date {
        guard let text = value.string else { throw OpenTideConstantsError.invalidArgument("an instant must be a timezone-aware timestamp") }
        let regex = try NSRegularExpression(pattern: #"^([0-9]{4})-([0-9]{2})-([0-9]{2})[Tt ]([0-9]{2}):([0-9]{2}):([0-9]{2})(\.[0-9]+)?([Zz]|[+-][0-9]{2}:?[0-9]{2})$"#)
        guard let match = regex.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)), match.range.length == text.utf16.count else { throw OpenTideConstantsError.invalidArgument("an instant must be a timezone-aware timestamp") }
        func part(_ n: Int) -> String { Range(match.range(at: n), in: text).map { String(text[$0]) } ?? "" }
        let values = (1...6).map { Int(part($0))! }
        guard values[0] >= 1, values[3] < 24, values[4] < 60, values[5] < 60 else { throw OpenTideConstantsError.invalidArgument("invalid calendar time") }
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(secondsFromGMT: 0)!
        let components = DateComponents(year: values[0], month: values[1], day: values[2], hour: values[3], minute: values[4], second: values[5])
        guard let date = calendar.date(from: components), calendar.dateComponents([.year, .month, .day, .hour, .minute, .second], from: date) == components else { throw OpenTideConstantsError.invalidArgument("invalid calendar time") }
        let zone = part(8)
        var offset = 0
        if zone.hasPrefix("+") || zone.hasPrefix("-") {
            let digits = zone.dropFirst().replacingOccurrences(of: ":", with: "")
            let hour = Int(digits.prefix(2))!, minute = Int(digits.suffix(2))!
            guard hour < 24, minute < 60 else { throw OpenTideConstantsError.invalidArgument("invalid timezone offset") }
            offset = (hour * 3600 + minute * 60) * (zone.hasPrefix("-") ? -1 : 1)
        }
        // Fractions are deliberately discarded before constructing Date; text never rounds into the next second.
        return date.addingTimeInterval(Double(-offset))
    }
    static func string(_ args: JSONValue, _ key: String) throws -> String? {
        guard !args[key].isNull else { return nil }
        guard let value = args[key].string else { throw OpenTideConstantsError.invalidArgument("\(key) must be a string") }
        return value
    }
    static func integer(_ args: JSONValue, _ key: String) throws -> Int64? {
        guard !args[key].isNull else { return nil }
        guard let value = args[key].integer, args[key].bool == nil else { throw OpenTideConstantsError.invalidArgument("\(key) must be an integer") }
        return value
    }
    static func boolean(_ args: JSONValue, _ key: String, default value: Bool = false) throws -> Bool {
        guard !args[key].isNull else { return value }
        guard let value = args[key].bool else { throw OpenTideConstantsError.invalidArgument("\(key) must be a boolean") }
        return value
    }
    static func station(_ station: Station?) -> JSONValue {
        guard let station else { return .null }
        var raw = station.raw.object
        raw["aliases"] = station.raw["aliases"].isNull ? .object([:]) : station.raw["aliases"]
        raw["kind"] = station.kind.map { .string($0.rawValue) } ?? .null
        raw["recommended_set_id"] = station.recommendedSet.map { .string($0.setId) } ?? .null
        raw["is_reference"] = .bool(station.isReference)
        raw["is_subordinate"] = .bool(station.isSubordinate)
        raw["is_tide"] = .bool(station.isTide)
        raw["is_current"] = .bool(station.isCurrent)
        let fields = ["station_id", "name", "country", "lat", "lon", "type", "kind", "timezone", "aliases", "status", "is_reference", "is_subordinate", "is_tide", "is_current", "recommended_set_id"]
        var result = Dictionary(uniqueKeysWithValues: fields.map { ($0, raw[$0] ?? .null) })
        if let fallback = station.recommendedIsFallback { result["recommended_is_fallback"] = .bool(fallback) }
        return .object(result)
    }
    static func releaseInfo(_ info: ReleaseInfo) -> JSONValue {
        .object(["datestamp": .string(info.datestamp), "format_version": .string(info.formatVersion), "concept_doi": plain(info.conceptDoi), "zenodo_version_doi": plain(info.zenodoVersionDoi), "content_sha256": .string(info.contentSha256), "files": .array(info.files.sorted { $0.name < $1.name }.map { file in .object(["name": .string(file.name), "url": plain(file.url), "size": plain(file.size), "sha256": plain(file.sha256)]) })])
    }
    static func main() async {
        emit(.object(["hello": .object(["runner": .string("swift"), "version": .string("0.1.0"), "features": .array(["fs", "fetch", "json", "eager", "stream", "predict", "localtime_module", "localtime"].map(JSONValue.string))])]))
        var client: OpenTideConstants?
        var held: [String: Release] = [:]
        var prediction: HeldPrediction?
        while let line = readLine() {
            do {
                let q = try JSONDecoder().decode(JSONValue.self, from: Data(line.utf8))
                let op = q["op"].string ?? "", args = q["args"]
                var result: JSONValue
                if op == "open" {
                    client = try await OpenTideConstants.open(release: try string(args, "release"), file: try string(args, "file"), cacheDir: try string(args, "cache_dir"), offline: args["offline"].bool, mode: Mode(rawValue: args["mode"].string ?? "eager") ?? .other, baseUrl: try string(args, "base_url"), timeout: args["timeout"].number, proxy: try string(args, "proxy"), caFile: try string(args, "ca_file"), userAgent: try string(args, "user_agent"), onNetworkError: args["on_network_error"].string.flatMap(OnNetworkError.init(rawValue:)), autoUpdate: try boolean(args, "auto_update"), updateInterval: args["update_interval"].number ?? 86400, verifyOnOpen: try boolean(args, "verify_on_open"), commercialOnly: try boolean(args, "commercial_only"), commercialBasis: args["commercial_basis"].string ?? "strict", historicalOffsetsPolicy: args["historical_offsets_policy"].string ?? "fallback")
                    result = .object(["datestamp": .string(client!.release.datestamp), "loaded_from": .string(client!.loadedFrom.rawValue), "format_version": .string(client!.release.formatVersion)])
                } else if op == "close" { client?.close(); result = .object([:]) }
                else {
                    guard let client else { throw OpenTideConstantsError.invalidArgument("not open") }
                    let r: Release
                    if let name = q["on"].string { guard let retained = held[name] else { throw OpenTideConstantsError.invalidArgument("unknown held release") }; r = retained }
                    else { r = client.release }
                    let id = args["station_id"].string ?? ""
                    switch op {
                    case "hold_release": held[args["name"].string ?? ""] = client.release; result = .object([:])
                    case "loaded_from": result = .object(["loaded_from": .string(client.loadedFrom.rawValue)])
                    case "last_error": result = .object(["code": client.lastError.map { .string($0.code) } ?? .null])
                    case "newer_format_major": result = .object(["newer_format_major": client.newerFormatMajor.map(JSONValue.integer) ?? .null])
                    case "releases": result = .object(["releases": .array(try await client.releases().map(releaseInfo))])
                    case "latest": result = .object(["release": releaseInfo(try await client.latest())])
                    case "check_for_update": result = .object(["release": try await client.checkForUpdate().map(releaseInfo) ?? .null])
                    case "update": result = plain(try await client.update())
                    case "download":
                        let formats: [Format]
                        if args.object.keys.contains("formats") {
                            guard case .array(let values) = args["formats"] else { throw OpenTideConstantsError.invalidArgument("formats must be an array") }
                            formats = try values.map { value in
                                guard let name = value.string else { throw OpenTideConstantsError.invalidArgument("formats must contain strings") }
                                return Format(rawValue: name) ?? .other
                            }
                        } else { formats = [.jsonl] }
                        let paths = try await client.download(release: string(args, "release") ?? "latest", to: string(args, "to") ?? "", formats: formats, overwrite: boolean(args, "overwrite"))
                        result = .object(["paths": .array(paths.map { URL(fileURLWithPath: $0).lastPathComponent }.sorted().map(JSONValue.string))])
                    case "verify": result = .object(["verified": .bool(try client.verify())])
                    case "cached_releases": result = .object(["datestamps": .array(try client.cachedReleases().map(JSONValue.string))])
                    case "prune": result = .object(["removed": .array(try await client.prune(keep: integer(args, "keep") ?? 3).map(JSONValue.string))])
                    case "station", "require_station":
                        let value: Station?
                        if q["on"].string == nil { value = op == "require_station" ? try client.requireStation(stationId: id) : try client.station(stationId: id) }
                        else { value = op == "require_station" ? try r.requireStation(stationId: id) : try r.station(stationId: id) }
                        result = .object(["station": station(value)])
                    case "tombstone": result = .object(["tombstone": try r.tombstone(stationId: id)?.raw ?? .null])
                    case "station_by_alias": result = .object(["station_id": try r.stationByAlias(system: args["system"].string ?? "", aliasId: args["alias_id"].string ?? "").map { .string($0.stationId) } ?? .null])
                    case "station_count": result = .object([op: .integer(Int64(try r.stationCount))])
                    case "tombstone_count": result = .object([op: .integer(Int64(try r.tombstoneCount))])
                    case "citation": result = .object([op: .string(r.citation)])
                    case "stats": result = .object([op: plain(try r.stats)])
                    case "constituent_names": result = .object(["names": .array(try r.constituentNames.map(JSONValue.string))])
                    case "release_files": result = .object(["files": .array(r.files.map { $0.raw })])
                    case "release_metadata": result = .object(["datestamp": .string(r.datestamp), "created": plain(r.created), "format_version": .string(r.formatVersion), "concept_doi": plain(r.conceptDoi), "zenodo_version_doi": plain(r.zenodoVersionDoi), "source_versions": .object(r.sourceVersions.mapValues(JSONValue.string)), "build_commit": plain(r.buildCommit), "changelog_url": plain(r.changelogUrl)])
                    case "conventions": result = .object([op: .array(try r.conventions.map { $0.raw })])
                    case "licences": result = .object([op: .array(try r.licences.map { $0.raw })])
                    case "convention": result = .object([op: try r.convention(conventionId: args["convention_id"].string ?? "")?.raw ?? .null])
                    case "licence": result = .object([op: try r.licence(licenceId: args["licence_id"].string ?? "")?.raw ?? .null])
                    case "attribution":
                        let stations: [Station]?
                        if args.object.keys.contains("station_ids") { stations = try args["station_ids"].array.map { value in guard let station = try r.station(stationId: value.string ?? "") else { throw OpenTideConstantsError.invalidArgument("invalid station") }; return station } }
                        else { stations = nil }
                        result = .object([op: .string(try r.attribution(stations: stations))])
                    case "reference_station", "subordinates_of":
                        let owner = args["station_on"].string.flatMap { held[$0] } ?? r
                        guard let station = try owner.station(stationId: id) else {
                            if args["station_id"].isNull || args["station_on"].string != nil { throw OpenTideConstantsError.invalidArgument("invalid station") }
                            result = .object([op == "reference_station" ? "station_id" : "station_ids": .null]); break
                        }
                        if op == "reference_station" { result = .object(["station_id": try r.referenceStation(station: station).map { .string($0.stationId) } ?? .null]) }
                        else { result = .object(["station_ids": .array(try r.subordinatesOf(station: station).map { .string($0.stationId) })]) }
                    case "stations", "iter_stations", "search", "near", "nearest":
                        let country = try string(args, "country"), type = try string(args, "type"), kind = try string(args, "kind"), source = try string(args, "source"), sourceType = try string(args, "source_type")
                        let flagged = try boolean(args, "include_flagged"), fallback = try boolean(args, "include_fallback")
                        if op == "stations" { result = .object(["station_ids": .array(try r.stations(country: country, type: type, kind: kind, source: source, sourceType: sourceType, includeFlagged: flagged, includeFallback: fallback).map { .string($0.stationId) })]) }
                        else if op == "iter_stations" {
                            let cursor = try r.iterStations(country: country, type: type, kind: kind, source: source, sourceType: sourceType, includeFlagged: flagged, includeFallback: fallback)
                            var ids: [JSONValue] = []
                            while let station = try cursor() { ids.append(.string(station.stationId)) }
                            result = .object(["station_ids": .array(ids)])
                        } else if op == "search" { result = .object(["station_ids": .array(try r.search(name: args["name"].string ?? "", limit: integer(args, "limit"), match: string(args, "match"), country: country, type: type, kind: kind, source: source, sourceType: sourceType, includeFlagged: flagged, includeFallback: fallback).map { .string($0.stationId) })]) }
                        else if op == "near" {
                            let values = try r.near(lat: args["lat"].number ?? .nan, lon: args["lon"].number ?? .nan, radiusKm: args["radius_km"].number ?? .nan, limit: integer(args, "limit"), country: country, type: type, kind: kind, source: source, sourceType: sourceType, includeFlagged: flagged, includeFallback: fallback)
                            result = .object(["station_ids": .array(values.map { .string($0.station.stationId) }), "distance_km": .array(values.map { .number($0.distanceKm) })])
                        } else {
                            let value = try r.nearest(lat: args["lat"].number ?? .nan, lon: args["lon"].number ?? .nan, maxKm: args["max_km"].number, country: country, type: type, kind: kind, source: source, sourceType: sourceType, includeFlagged: flagged, includeFallback: fallback)
                            result = .object(["station_id": value.map { .string($0.station.stationId) } ?? .null, "distance_km": value.map { .number($0.distanceKm) } ?? .null])
                        }
                    case "heights", "heights_at", "extremes", "currents", "current_events":
                        let datum = try string(args, "datum"), setId = try string(args, "set_id"), offsetId = try string(args, "offset_id")
                        let binNumber = try integer(args, "bin_number")
                        if op == "heights_at" {
                            guard case .array(let times) = args["times"] else { throw OpenTideConstantsError.invalidArgument("times must be an array of instants") }
                            prediction = .heights(try r.heightsAt(stationId: id, times: times.map(instant), datum: datum, setId: setId, offsetId: offsetId))
                        } else {
                            let start = try instant(args["start"]), stop = try instant(args["stop"])
                            if op == "heights" { prediction = .heights(try r.heights(stationId: id, start: start, stop: stop, stepS: integer(args, "step_s") ?? 600, datum: datum, setId: setId, offsetId: offsetId)) }
                            else if op == "extremes" { prediction = .extremes(try r.extremes(stationId: id, start: start, stop: stop, datum: datum, setId: setId, offsetId: offsetId)) }
                            else if op == "currents" { prediction = .currents(try r.currents(stationId: id, start: start, stop: stop, stepS: integer(args, "step_s") ?? 600, binNumber: binNumber, setId: setId)) }
                            else { prediction = .events(try r.currentEvents(stationId: id, start: start, stop: stop, binNumber: binNumber, setId: setId)) }
                        }
                        result = .object(["prediction": prediction!.encoded()])
                    case "to_local":
                        guard let previous = prediction else { throw OpenTideConstantsError.invalidArgument("no prediction result is held") }
                        prediction = try previous.toLocal(string(args, "tz") ?? "station")
                        result = .object(["prediction": prediction!.encoded()])
                    case "astro_table", "valid_range", "equilibrium_argument", "node_factor", "equilibrium_for_year", "node_factor_for_year":
                        let table = try r.astroTable(id: string(args, "id"))
                        if op == "astro_table" { result = .object([op: table.map { .object(["first_year": .integer($0.validRange[0]), "last_year": .integer($0.validRange[1])]) } ?? .null]) }
                        else {
                            guard let table else { throw OpenTideConstantsError.invalidArgument("astro table is unavailable") }
                            if op == "valid_range" { result = .object(["first_year": .integer(table.validRange[0]), "last_year": .integer(table.validRange[1])]) }
                            else {
                                let name = args["name"].string ?? "", value: Double
                                if op == "equilibrium_argument" { value = try table.equilibriumArgument(name: name, at: instant(args["at"])) }
                                else if op == "node_factor" { value = try table.nodeFactor(name: name, at: instant(args["at"])) }
                                else if op == "equilibrium_for_year" { guard let year = try integer(args, "year") else { throw OpenTideConstantsError.invalidArgument("year required") }; value = try table.equilibriumForYear(name: name, year: year) }
                                else { guard let year = try integer(args, "year") else { throw OpenTideConstantsError.invalidArgument("year required") }; value = try table.nodeFactorForYear(name: name, year: year) }
                                result = .object(["value": .number(value)])
                            }
                        }
                    case "datums":
                        switch try r.datums(stationId: id, setId: string(args, "set_id"), allSets: boolean(args, "all_sets")) {
                        case .one(let info): result = .object([op: info.map(plain) ?? .null])
                        case .all(let values): result = .object([op: .array(values.map(plain))])
                        }
                    case "ranges": result = .object([op: plain(try r.ranges(stationId: id, setId: string(args, "set_id")))])
                    case "raw":
                        let object = args["object"].string ?? ""
                        var raw: JSONValue = .null
                        if object == "station" { raw = try r.station(stationId: id)?.raw ?? .null }
                        else if object == "tombstone" { raw = try r.tombstone(stationId: id)?.raw ?? .null }
                        else if object == "convention" { raw = try r.convention(conventionId: args["convention_id"].string ?? "")?.raw ?? .null }
                        else if object == "licence" { raw = try r.licence(licenceId: args["licence_id"].string ?? "")?.raw ?? .null }
                        else if let station = try r.station(stationId: id) {
                            let set = args["set_id"].string.flatMap { station.constantSet(setId: $0) } ?? station.recommendedSet
                            if object == "set" { raw = set?.raw ?? .null }
                            else if object == "constituent" { raw = set?.constituent(name: args["name"].string ?? "")?.raw ?? .null }
                        }
                        result = .object(["raw": raw])
                    default: throw OpenTideConstantsError.invalidArgument("runner op \(op) awaits SIO/G0 registration")
                    }
                }
                emit(.object(["ok": .bool(true), "result": result]))
            } catch let error as OpenTideConstantsError {
                emit(.object(["ok": .bool(false), "error": .object(["code": .string(error.code), "message": .string(error.message), "fields": .object(error.fields)])]))
            } catch { emit(.object(["ok": .bool(false), "error": .object(["code": .string("uncaught"), "message": .string("\(error)")])])) }
        }
    }
}
