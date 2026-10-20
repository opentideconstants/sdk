import Foundation
import OpenTideConstants

/// Public compiler declarations and actual SDK calls, checked against the shared manifest.
@main struct CheckAPI {
    struct Failure: Error, CustomStringConvertible { let description: String }

    static func require(_ condition: Bool, _ message: String) throws {
        if !condition { throw Failure(description: message) }
    }
    static func camel(_ name: String) -> String {
        let words = name.split { !$0.isLetter && !$0.isNumber }.map { String($0).lowercased() }
        return (words.first?.lowercased() ?? "") + words.dropFirst().map { $0.prefix(1).uppercased() + $0.dropFirst() }.joined()
    }
    static func enumName(_ name: String) -> String {
        if name == "qc_flag" { return "QcFlagName" }
        let lower = camel(name)
        return lower.prefix(1).uppercased() + lower.dropFirst()
    }
    static func spelling(_ fragments: JSONValue) -> String { fragments.array.compactMap { $0["spelling"].string }.joined() }
    static func compact(_ text: String) -> String { text.filter { !$0.isWhitespace && $0 != "`" }.replacingOccurrences(of: "Void", with: "()") }
    static func applicable(_ row: JSONValue) -> Bool { row["languages"].isNull || row["languages"].array.contains(.string("swift")) }
    static func type(_ canonical: String, enumType: String? = nil) -> String {
        if canonical.hasSuffix("|null") { return type(String(canonical.dropLast(5)), enumType: enumType) + "?" }
        if canonical.hasSuffix("[]") { return "[" + type(String(canonical.dropLast(2)), enumType: enumType) + "]" }
        if canonical.hasPrefix("enum:") { return enumName(String(canonical.dropFirst(5))) }
        if canonical == "enum", let enumType { return enumName(enumType) }
        switch canonical {
        case "Client": return "OpenTideConstants"
        case "Error": return "OpenTideConstantsError"
        case "boolean": return "Bool"
        case "number", "seconds": return "Double"
        case "integer": return "Int64"
        case "instant", "time", "datetime", "Time": return "Date"
        case "string", "path", "url", "datestamp", "datestamp_or_latest": return "String"
        case "Iterator<Station>": return "() throws -> Station?"
        case "DatumInfo|DatumInfo[]": return "DatumsResult"
        case "[integer, integer]": return "[Int64]"
        case "object", "any", "map<string,any>": return "JSONValue"
        case "logger": return "((String) -> Void)?"
        default:
            if canonical.hasPrefix("map<string,"), canonical.hasSuffix(">") { return "[String:" + type(String(canonical.dropFirst(11).dropLast())) + "]" }
            return canonical
        }
    }
    static func defaultExpression(_ argument: JSONValue) throws -> String {
        if let native = argument["swift_default"].string { return native }
        let value = argument["default"]
        if value.isNull { return "nil" }
        if let boolean = value.bool { return boolean ? "true" : "false" }
        if let integer = value.integer { return String(integer) }
        if let number = value.number { return String(number) }
        if let string = value.string {
            if argument["type"].string == "enum" { return "." + camel(string) }
            return String(decoding: try JSONEncoder().encode(JSONValue.string(string)), as: UTF8.self)
        }
        if case .array = value { return "[" + value.array.map { "." + camel($0.string ?? "") }.joined(separator: ",") + "]" }
        throw Failure(description: "unprojected argument default \(argument)")
    }

    /// Parameter fragments omit defaults; full compiler declarations retain them.
    static func parameterDeclarations(_ symbol: JSONValue) -> [String: String] {
        let fragments = symbol["declarationFragments"].array
        let starts = fragments.indices.filter { fragments[$0]["kind"].string == "externalParam" }
        var result: [String: String] = [:]
        for (index, start) in starts.enumerated() {
            guard let label = fragments[start]["spelling"].string else { continue }
            let end = index + 1 < starts.count ? starts[index + 1] : fragments.count
            var text = fragments[(start + 1)..<end].compactMap { $0["spelling"].string }.joined()
            if index + 1 < starts.count {
                if text.hasSuffix(", ") { text = String(text.dropLast(2)) }
            } else {
                for suffix in [") async", ") throws", ") ->"] {
                    if let range = text.range(of: suffix) { text = String(text[..<range.lowerBound]); break }
                }
                if text.hasSuffix(")") { text.removeLast() }
            }
            result[label] = text
        }
        return result
    }
    static func sealedParameterType(_ label: String, member: JSONValue) -> String? {
        let escaped = NSRegularExpression.escapedPattern(for: label)
        guard let regex = try? NSRegularExpression(pattern: "(?:\\(|,\\s*)" + escaped + ": ([^=,]+?)(?: = |,|\\))") else { return nil }
        for value in member["swift_declarations"].array {
            guard let declaration = value.string,
                  let match = regex.firstMatch(in: declaration, range: NSRange(declaration.startIndex..., in: declaration)),
                  let range = Range(match.range(at: 1), in: declaration) else { continue }
            return String(declaration[range]).trimmingCharacters(in: .whitespaces)
        }
        return nil
    }

    static func surfaceProblems(_ api: JSONValue, _ graph: JSONValue) throws -> (problems: [String], rows: Int, names: Int) {
        try require(graph["module"]["name"].string == "OpenTideConstants", "not an OpenTideConstants compiler symbol graph")
        let symbols = graph["symbols"].array
        try require(!symbols.isEmpty, "compiler symbol graph has zero symbols")
        let pending = api["pending_port"]["swift"]
        try require(!pending.isNull, "manifest has no pending_port.swift")
        for key in ["objects", "members", "enums", "errors"] { try require(pending[key].array.isEmpty, "unaccepted pending Swift names in \(key)") }
        var problems: [String] = []
        var rows = 0
        let forwarded = api["objects"]["Release"]["members"].array.filter { $0["forwarded_to_client"].bool == true || $0["swift_forwarded_to_client"].bool == true }
        for (canonical, object) in api["objects"].object.sorted(by: { $0.key < $1.key }) {
            let owner = object["swift"].string ?? canonical
            if !symbols.contains(where: { $0["pathComponents"].array == [.string(owner)] }) { problems.append("missing public type \(owner)") }
            let members = (object["members"].array + (canonical == "Client" ? forwarded : []) + api["swift_public_support"][canonical].array).filter(applicable)
            let expectedNames = Set(members.compactMap { $0["swift"].string })
            let actual = symbols.filter { $0["pathComponents"].array.count == 2 && $0["pathComponents"].array.first == .string(owner) }
            for member in members {
                rows += 1
                guard let name = member["swift"].string else { problems.append("no Swift projection for \(canonical).\(member["name"])"); continue }
                let found = actual.filter { $0["pathComponents"].array.last?.string?.split(separator: "(").first.map(String.init) == name }
                let qualified = owner + "." + name
                if found.isEmpty { problems.append("missing public member \(qualified)"); continue }
                let method = member["kind"].string == "method"
                let arguments = member["args"].array + (member["filters"].bool == true ? api["filters"].array : [])
                let labels = arguments.map { $0["swift"].string ?? camel($0["name"].string ?? "") }
                var expectedLabels = [labels]
                if arguments.first?["type"].string == "Station|string" { var ids = labels; ids[0] = "stationId"; expectedLabels.append(ids) }
                if found.count != expectedLabels.count { problems.append("\(qualified): expected \(expectedLabels.count) native overloads, got \(found.count)") }
                for overload in expectedLabels {
                    guard let symbol = found.first(where: { $0["functionSignature"]["parameters"].array.compactMap { $0["name"].string } == overload }) else { problems.append("\(qualified): argument labels \(overload) absent"); continue }
                    let kind = symbol["kind"]["identifier"].string ?? ""
                    if method != kind.contains("method") { problems.append("\(qualified): method/property kind mismatch \(kind)") }
                    let declaration = spelling(symbol["declarationFragments"])
                    let sealedDeclarations = member["swift_declarations"].array.compactMap { $0.string }
                    if !sealedDeclarations.isEmpty && !sealedDeclarations.contains(where: { compact($0) == compact(declaration) }) { problems.append("\(qualified): sealed native declaration mismatch") }
                    let isAsync = symbol["declarationFragments"].array.contains { $0["kind"].string == "keyword" && $0["spelling"].string == "async" }
                    if isAsync != (member["swift_async"].bool ?? false) { problems.append("\(qualified): async projection mismatch") }
                    if method && declaration.hasPrefix("static ") != (member["static"].bool ?? false) { problems.append("\(qualified): static projection mismatch") }
                    let expectedReturn = member["swift_returns"].string ?? member["swift_type"].string ?? type(member["returns"].string ?? member["type"].string ?? "Void", enumType: member["enum"].string) + (member["nullable"].bool == true ? "?" : "")
                    let actualReturn = method ? spelling(symbol["functionSignature"]["returns"]) : declaration.components(separatedBy: ": ").dropFirst().joined(separator: ": ").components(separatedBy: " {").first ?? ""
                    if compact(actualReturn) != compact(expectedReturn) { problems.append("\(qualified): type \(actualReturn), manifest \(expectedReturn)") }
                    let parameters = symbol["functionSignature"]["parameters"].array
                    let declared = parameterDeclarations(symbol)
                    for (index, argument) in arguments.enumerated() {
                        guard index < parameters.count else { continue }
                        let label = overload[index]
                        let actualType = spelling(parameters[index]["declarationFragments"]).components(separatedBy: ": ").dropFirst().joined(separator: ": ")
                        let expectedType: String
                        if argument["type"].string == "Station|string" { expectedType = label == "stationId" ? "String" : "Station" }
                        else { expectedType = argument["swift_type"].string ?? sealedParameterType(label, member: member) ?? type(argument["type"].string ?? "", enumType: argument["enum"].string) + (argument["default"].isNull && argument["required"].bool != true && argument["type"].string != "logger" ? "?" : "") }
                        if compact(actualType) != compact(expectedType) { problems.append("\(qualified)(\(label)): type \(actualType), manifest \(expectedType)") }
                        let parts = (declared[label] ?? "").components(separatedBy: " = ")
                        if argument["required"].bool == true { if parts.count != 1 { problems.append("\(qualified)(\(label)): required argument has default") } }
                        else {
                            let expectedDefault = try defaultExpression(argument)
                            if parts.count != 2 || compact(parts[1]) != compact(expectedDefault) { problems.append("\(qualified)(\(label)): default \(parts.dropFirst().joined()), manifest \(expectedDefault)") }
                        }
                    }
                }
            }
            for symbol in actual {
                let name = symbol["pathComponents"].array.last?.string?.split(separator: "(").first.map(String.init) ?? ""
                // "==" is the Equatable witness (Station spells it out so that its origin token is not compared), not API.
                if !expectedNames.contains(name) && name != "init" && name != "init?" && name != "==" { problems.append("extra public member \(owner).\(name)") }
            }
        }
        for (name, values) in api["enums"].object.sorted(by: { $0.key < $1.key }) {
            let owner = enumName(name)
            let want = Set(values.array.compactMap { $0.string }.map(camel) + ["other"])
            let got = Set(symbols.filter { $0["pathComponents"].array.count == 2 && $0["pathComponents"].array.first == .string(owner) && $0["kind"]["identifier"].string == "swift.enum.case" }.compactMap { $0["pathComponents"].array.last?.string })
            if got != want { problems.append("enum \(owner): missing \(want.subtracting(got).sorted()), extra \(got.subtracting(want).sorted())") }
        }
        let errors = api["errors"].array.filter(applicable)
        let wantErrors = Set(errors.filter { !$0["class"].isNull }.compactMap { $0["swift"].string })
        let gotErrors = Set(symbols.filter { $0["pathComponents"].array.first == .string("OpenTideConstantsError") && $0["kind"]["identifier"].string == "swift.enum.case" }.compactMap { $0["pathComponents"].array.last?.string?.split(separator: "(").first.map(String.init) })
        if wantErrors != gotErrors { problems.append("error cases: missing \(wantErrors.subtracting(gotErrors).sorted()), extra \(gotErrors.subtracting(wantErrors).sorted())") }
        for (name, row) in api["constants"].object where name != "c_only" && applicable(row) {
            let native = row["swift"].string ?? camel(name)
            if let symbol = symbols.first(where: { $0["pathComponents"].array == [.string(native)] }) {
                let declaration = spelling(symbol["declarationFragments"])
                let expectedType = row["value"].array.isEmpty ? "String" : "[Int]"
                if !declaration.hasPrefix("let ") || compact(declaration.components(separatedBy: ": ").dropFirst().joined(separator: ": ")) != compact(expectedType) { problems.append("constant \(native): immutable \(expectedType) declaration required") }
            } else { problems.append("missing public constant \(native)") }
        }
        let expectedTop = Set(api["objects"].object.map { $0.value["swift"].string ?? $0.key } + api["enums"].object.keys.map(enumName) + ["OpenTideConstantsError", "JSONValue", "DatumsResult"] + api["constants"].object.filter { $0.key != "c_only" && applicable($0.value) }.map { $0.value["swift"].string ?? camel($0.key) })
        let actualTop = Set(symbols.filter { $0["pathComponents"].array.count == 1 }.compactMap { $0["pathComponents"].array.first?.string })
        for extra in actualTop.subtracting(expectedTop).sorted() { problems.append("extra public name \(extra)") }
        let names = api["objects"].object.count + api["enums"].object.count + errors.count + api["constants"].object.filter { $0.key != "c_only" && applicable($0.value) }.count + 1
        return (problems, rows, names)
    }

    static func rawEnums() -> [String: [String]] {
        ["kind": Kind.allCases.map(\.rawValue), "station_type": StationType.allCases.map(\.rawValue), "station_status": StationStatus.allCases.map(\.rawValue), "removed_reason": RemovedReason.allCases.map(\.rawValue), "source_type": SourceType.allCases.map(\.rawValue), "quantity": Quantity.allCases.map(\.rawValue), "qc_status": QcStatus.allCases.map(\.rawValue), "loaded_from": LoadedFrom.allCases.map(\.rawValue), "phase_reference": PhaseReference.allCases.map(\.rawValue), "nodal_handling": NodalHandling.allCases.map(\.rawValue), "canary_status": CanaryStatus.allCases.map(\.rawValue), "height_adjusted_type": HeightAdjustedType.allCases.map(\.rawValue), "dropped_reason": DroppedReason.allCases.map(\.rawValue), "qc_flag": QcFlagName.allCases.map(\.rawValue), "time_base_code": TimeBaseCode.allCases.map(\.rawValue), "decision_tier": DecisionTier.allCases.map(\.rawValue), "decision_outcome": DecisionOutcome.allCases.map(\.rawValue), "alias_system": AliasSystem.allCases.map(\.rawValue), "mode": Mode.allCases.map(\.rawValue), "on_network_error": OnNetworkError.allCases.map(\.rawValue), "format": Format.allCases.map(\.rawValue), "match": Match.allCases.map(\.rawValue), "extreme_type": ExtremeType.allCases.map(\.rawValue), "current_event_type": CurrentEventType.allCases.map(\.rawValue), "prediction_method": PredictionMethod.allCases.map(\.rawValue), "fallback_reason": FallbackReason.allCases.map(\.rawValue), "source_role": SourceRole.allCases.map(\.rawValue), "source_disposition": SourceDisposition.allCases.map(\.rawValue)]
    }
    static func errorValues() -> [String: OpenTideConstantsError] {
        ["network": .network("checker"), "release_not_found": .releaseNotFound("checker"), "offline_unavailable": .offlineUnavailable("checker"), "checksum_mismatch": .checksumMismatch("checker"), "unsupported_format": .unsupportedFormat("checker"), "reader_too_old": .readerTooOld("checker"), "invalid_release": .invalidRelease("checker"), "station_not_found": .stationNotFound("checker"), "station_removed": .stationRemoved("checker"), "pinned_release": .pinnedRelease("checker"), "cache": .cache("checker"), "file_exists": .fileExists("checker"), "io": .io("checker"), "invalid_argument": .invalidArgument("checker"), "no_constants": .noConstants("checker"), "quantity_mismatch": .quantityMismatch("checker"), "unsupported_convention": .unsupportedConvention("checker"), "no_astro_table": .noAstroTable("checker"), "unsupported_constituent": .unsupportedConstituent("checker"), "time_out_of_range": .timeOutOfRange("checker"), "datum_unavailable": .datumUnavailable("checker"), "bin_not_found": .binNotFound("checker"), "extremes_only": .extremesOnly("checker"), "local_time_unavailable": .localTimeUnavailable("checker"), "unknown_time_zone": .unknownTimeZone("checker"), "reference_unavailable": .referenceUnavailable("checker"), "historical_offsets_excluded": .historicalOffsetsExcluded("checker")]
    }

    static func canonicalValueProblems(_ api: JSONValue, owner: String, value: JSONValue, path: String) -> [String] {
        guard case .object(let fields) = value else { return ["canonical shape \(path): expected \(owner) object"] }
        var problems: [String] = []
        for member in api["objects"][owner]["members"].array where applicable(member) && member["kind"].string != "method" {
            let name = member["name"].string ?? ""
            guard let actual = fields[name] else { problems.append("canonical field \(path).\(name): absent"); continue }
            let expected = member["returns"].string ?? member["type"].string ?? ""
            let nullable = member["nullable"].bool == true || expected.hasSuffix("|null")
            if actual.isNull {
                if !nullable { problems.append("canonical nonnull \(path).\(name)") }
            } else {
                problems += shapeProblems(api, expected: expected, enumType: member["enum"].string, value: actual, path: path + "." + name)
            }
        }
        return problems
    }
    static func shapeProblems(_ api: JSONValue, expected: String, enumType: String?, value: JSONValue, path: String) -> [String] {
        if expected.hasSuffix("|null") {
            if value.isNull { return [] }
            return shapeProblems(api, expected: String(expected.dropLast(5)), enumType: enumType, value: value, path: path)
        }
        if expected.hasSuffix("[]") {
            guard case .array(let values) = value else { return ["canonical shape \(path): expected \(expected)"] }
            return values.enumerated().flatMap { shapeProblems(api, expected: String(expected.dropLast(2)), enumType: enumType, value: $0.element, path: path + "[\($0.offset)]") }
        }
        if expected.hasPrefix("map<string,"), expected.hasSuffix(">") {
            guard case .object(let values) = value else { return ["canonical shape \(path): expected \(expected)"] }
            let element = String(expected.dropFirst(11).dropLast())
            return values.sorted(by: { $0.key < $1.key }).flatMap { shapeProblems(api, expected: element, enumType: enumType, value: $0.value, path: path + "." + $0.key) }
        }
        if expected.contains("|") {
            let alternatives = expected.split(separator: "|").map(String.init)
            if alternatives.contains(where: { shapeProblems(api, expected: $0, enumType: enumType, value: value, path: path).isEmpty }) { return [] }
            return ["canonical shape \(path): expected \(expected)"]
        }
        if api["objects"].object[expected] != nil { return canonicalValueProblems(api, owner: expected, value: value, path: path) }
        let valid: Bool
        switch expected {
        case "null": valid = value.isNull
        case "any": valid = true
        case "object": if case .object = value { valid = true } else { valid = false }
        case "boolean": valid = value.bool != nil
        case "integer": valid = value.integer != nil
        case "number", "seconds": valid = value.number?.isFinite == true
        case "string", "path", "url", "datestamp", "instant", "time", "datetime", "Time": valid = value.string != nil
        case "enum": valid = value.string.map { api["enums"][enumType ?? ""].array.contains(.string($0)) || $0 == "other" } ?? false
        default:
            if expected.hasPrefix("enum:") { valid = value.string.map { api["enums"][String(expected.dropFirst(5))].array.contains(.string($0)) || $0 == "other" } ?? false }
            else { valid = false }
        }
        return valid ? [] : ["canonical shape \(path): expected \(expected), got \(value)"]
    }
    static func canonicalCoverage(_ api: JSONValue, owner: String, value: JSONValue) -> Set<String> {
        var covered: Set<String> = []
        for member in api["objects"][owner]["members"].array where applicable(member) && member["kind"].string != "method" {
            let name = member["name"].string ?? ""
            guard let actual = value.object[name] else { continue }
            if member["nullable"].bool == false && member["swift_returns"].string?.hasSuffix("?") == true { covered.insert(owner + "." + name) }
            let rawType = member["returns"].string ?? member["type"].string ?? ""
            let expected = rawType.hasSuffix("|null") ? String(rawType.dropLast(5)) : rawType
            if api["objects"].object[expected] != nil && !actual.isNull { covered.formUnion(canonicalCoverage(api, owner: expected, value: actual)) }
            if expected.hasSuffix("[]") {
                let child = String(expected.dropLast(2))
                if api["objects"].object[child] != nil { for item in actual.array { covered.formUnion(canonicalCoverage(api, owner: child, value: item)) } }
            }
        }
        return covered
    }

    static func valueProblems(_ api: JSONValue, path: String) async throws -> [String] {
        var problems: [String] = []
        var coveredNonnull: Set<String> = []
        var valueCount = 0
        func check(_ condition: Bool, _ cell: String) {
            valueCount += 1
            print("VALUE \(cell) \(condition ? "PASS" : "FAIL")")
            if !condition { problems.append("value \(cell)") }
        }
        func inspect(owner: String, value: JSONValue, path: String) {
            problems += canonicalValueProblems(api, owner: owner, value: value, path: path)
            coveredNonnull.formUnion(canonicalCoverage(api, owner: owner, value: value))
        }
        do {
        let rawEnums = rawEnums(), errors = errorValues()
        let constants: [String: JSONValue] = ["SUPPORTED_FORMAT_MAJORS": try native(supportedFormatMajors), "SUPPORTED_FORMAT_VERSION": try native(supportedFormatVersion), "DEFAULT_BASE_URL": try native(defaultBaseUrl), "CACHE_LAYOUT_VERSION": try native(cacheLayoutVersion)]
        for (name, row) in api["constants"].object where name != "c_only" && applicable(row) { check(constants[name] == row["value"], "constant.\(name).actualValue") }
        for (name, values) in api["enums"].object.sorted(by: { $0.key < $1.key }) { check(Set(rawEnums[name] ?? []) == Set(values.array.compactMap { $0.string } + ["other"]), "enum.\(name).rawValues") }
        for error in api["errors"].array.filter({ applicable($0) && !$0["class"].isNull }) {
            let code = error["code"].string ?? ""
            check(errors[code]?.code == code && errors[code]?.message == "checker", "error.\(code).code")
        }
        let raw = try JSONDecoder().decode(JSONValue.self, from: Data(contentsOf: URL(fileURLWithPath: path)))
        let client = try await OpenTideConstants.open(file: path)
        defer { client.close() }
        let release = client.release, count = try client.release.stationCount
        check(try client.station(stationId: "OTC-checker-unknown") == nil, "not_found.nativeNullLookup")
        inspect(owner: "Release", value: try native(release), path: "Release")
        check(count == raw["stations"].array.filter { $0["status"].string != "removed" }.count, "Release.stationCount")
        let explicit = try await OpenTideConstants.open(file: path, mode: .eager, autoUpdate: false, updateInterval: 86400, verifyOnOpen: false, commercialOnly: false, commercialBasis: "strict", historicalOffsetsPolicy: "fallback")
        defer { explicit.close() }
        check(try explicit.release.stationCount == count && explicit.loadedFrom == client.loadedFrom, "Client.open.defaults")
        let ordinary = try client.stations(), complete = try client.stations(includeFlagged: true, includeFallback: true)
        let clientBox: [Station] = try client.bbox(south: -90, west: -180, north: 90, east: 180)
        let releaseBox: [Station] = try release.bbox(south: -90, west: -180, north: 90, east: 180, limit: 1)
        check(clientBox.map(\.stationId) == ordinary.map(\.stationId), "Client.bbox.filterDefaults")
        check(releaseBox.map(\.stationId) == Array(ordinary.prefix(1)).map(\.stationId), "Release.bbox.limit")
        for station in complete {
            inspect(owner: "Station", value: try native(station), path: "Station[\(station.stationId)]")
            for set in station.constantSets(includeNoConstants: true) {
                inspect(owner: "ConstantSet", value: try native(set), path: "ConstantSet[\(set.setId)]")
            }
        }
        check(ordinary.map(\.stationId) == (try client.stations(country: nil, type: nil, kind: nil, source: nil, sourceType: nil, includeFlagged: false, includeFallback: false)).map(\.stationId), "Client.stations.filterDefaults")
        try require(!ordinary.isEmpty && !complete.isEmpty, "native fixture has no eligible stations")
        for station in ordinary { check(try client.station(stationId: station.stationId)?.raw == station.raw && release.requireStation(stationId: station.stationId).raw == station.raw, "Station.lookup.\(station.stationId)") }
        guard let otaru = try client.search(name: "Otaru", includeFallback: true).first else { throw Failure(description: "actual Otaru absent") }
        check(otaru.sourceRecords.contains { $0.licence != nil } && otaru.sourceRecords.allSatisfy { $0.raw["source_record_id"].string == $0.sourceRecordId }, "SourceRecord.actualValues/licence")
        let found = try client.search(name: "San")
        check(found.map(\.stationId) == (try client.search(name: "San", limit: nil, match: nil, includeFlagged: false, includeFallback: false)).map(\.stationId), "Client.search.defaults")
        let iterate = try client.iterStations()
        var iterated: [String] = []
        while let station = try iterate() { iterated.append(station.stationId) }
        check(iterated == ordinary.map(\.stationId), "Client.iterStations.syncClosure")
        guard let discriminating = complete.first(where: { $0.constantSets(includeNoConstants: true).contains { $0.qcStatus == .noConstants } }) else { throw Failure(description: "native fixture must contain a no_constants set for discriminating default proof") }
        let selected = discriminating.constantSets(includeNoConstants: false)
        check(discriminating.constantSets().map(\.setId) == selected.map(\.setId), "Station.constantSets.includeNoConstants=false")
        try require(discriminating.constantSets(includeNoConstants: true).count > selected.count, "constant_sets probe does not discriminate")
        guard let tide = ordinary.first(where: { $0.isTide && $0.recommendedSet?.source == "noaa" }) else { throw Failure(description: "native fixture must contain an actual NOAA reference for Date/prediction default proof") }
        let start = Date(timeIntervalSince1970: 1577836800.75), stop = Date(timeIntervalSince1970: 1577838600.75)
        let heights = try client.heights(station: tide, start: start, stop: stop)
        inspect(owner: "HeightSeries", value: try native(heights), path: "HeightSeries")
        let step = try client.heights(station: tide, start: start, stop: stop, stepS: 600, datum: nil, setId: nil, offsetId: nil)
        let byId = try client.heights(stationId: tide.stationId, start: start, stop: stop)
        check(heights == step && heights == byId && heights.items.count == 3, "Client.heights.stepS=600/StationId/Date")
        check(heights.items.map { $0.time.timeIntervalSince1970 } == [1577836800, 1577837400, 1577838000], "HeightSeries.Date.floor")
        let negative = Date(timeIntervalSince1970: -0.25)
        let at = try client.heightsAt(station: tide, times: [negative]), atId = try release.heightsAt(stationId: tide.stationId, times: [Date(timeIntervalSince1970: -1)])
        check(at.items.first?.time.timeIntervalSince1970 == -1 && at == atId, "heightsAt.negativeDate.floor")
        let one = try client.datums(station: tide), oneId = try release.datums(stationId: tide.stationId, setId: nil, allSets: false), all = try client.datums(stationId: tide.stationId, allSets: true)
        if case .one(let info) = one {
            check(info != nil && one == oneId, "Client.datums.allSets=false/one")
            if let info { inspect(owner: "DatumInfo", value: try native(info), path: "DatumInfo.one") }
        }
        else { check(false, "Client.datums.allSets=false/one") }
        if case .all(let info) = all {
            check(info.count == tide.constantSets(includeNoConstants: true).count, "Client.datums.allSets=true/all")
            for (index, value) in info.enumerated() { inspect(owner: "DatumInfo", value: try native(value), path: "DatumInfo.all[\(index)]") }
        }
        else { check(false, "Client.datums.allSets=true/all") }
        check(try client.ranges(station: tide) == release.ranges(stationId: tide.stationId, setId: nil), "Client.ranges.defaults")
        inspect(owner: "Ranges", value: try native(client.ranges(station: tide)), path: "Ranges")
        let extremes = try client.extremes(station: tide, start: start, stop: start.addingTimeInterval(86400))
        check(try extremes == release.extremes(stationId: tide.stationId, start: start, stop: start.addingTimeInterval(86400), datum: nil, setId: nil, offsetId: nil), "Client.extremes.defaults/StationId")
        try require(!extremes.items.isEmpty, "actual extremes sample must contain events")
        inspect(owner: "ExtremeList", value: try native(extremes), path: "ExtremeList")
        do {
            guard let vectors = ProcessInfo.processInfo.environment["OTC_SWIFT_VECTOR_JSON"] else { throw Failure(description: "OTC_SWIFT_VECTOR_JSON must name the existing real NOAA tide/current vector source for required current/result metadata checks") }
            let vectorClient = try await OpenTideConstants.open(file: vectors)
            defer { vectorClient.close() }
            guard let current = try vectorClient.stations(includeFlagged: true, includeFallback: true).first(where: { $0.isCurrent && $0.isReference && $0.recommendedSet?.source == "noaa-currents" }) else { throw Failure(description: "real NOAA current reference absent; synthetic/empty current results cannot count") }
            let currents = try vectorClient.currents(station: current, start: start, stop: stop)
            check(try currents == vectorClient.currents(stationId: current.stationId, start: start, stop: stop, stepS: 600, binNumber: nil, setId: nil) && currents.items.count == 3, "Client.currents.defaults/StationId")
            inspect(owner: "CurrentSeries", value: try native(currents), path: "CurrentSeries")
            let events = try vectorClient.currentEvents(station: current, start: start, stop: start.addingTimeInterval(86400))
            check(try events == vectorClient.currentEvents(stationId: current.stationId, start: start, stop: start.addingTimeInterval(86400), binNumber: nil, setId: nil), "Client.currentEvents.defaults/StationId")
            try require(!events.items.isEmpty, "actual current events sample must contain events")
            inspect(owner: "CurrentEventList", value: try native(events), path: "CurrentEventList")
        } catch { problems.append("required current value proof failed: \(error)") }
        let localized = try heights.toLocal()
        inspect(owner: "HeightSeries", value: try native(localized), path: "localized.HeightSeries")
        check(try localized == heights.toLocal(tz: "station") && localized.items.allSatisfy { $0.localTime != nil && $0.utcOffsetS != nil && $0.localDatetime() != nil }, "HeightSeries.toLocal.defaults/Date")
        guard let astro = try client.astroTable() else { throw Failure(description: "actual native astro table absent") }
        check(try astro.equilibriumArgument(name: "M2", at: negative) == astro.equilibriumArgument(name: "M2", at: Date(timeIntervalSince1970: -1)), "AstroTable.Date/argumentLabels")
        do { _ = try await client.update(); check(false, "Client.update.pinnedRelease") }
        catch let error as OpenTideConstantsError { check(error.code == "pinned_release", "Client.update.pinnedRelease") }
        let held = try client.iterStations()
        client.close()
        let closed: [(String, () throws -> Void)] = [
            ("Client.station", { _ = try client.station(stationId: tide.stationId) }), ("Release.stats", { _ = try release.stats }),
            ("iterator.step", { _ = try held() }), ("Client.heights", { _ = try client.heights(station: tide, start: start, stop: stop) }),
            ("Client.cachedReleases", { _ = try client.cachedReleases() }), ("Client.verify", { _ = try client.verify() })
        ]
        for (name, body) in closed {
            do { try body(); check(false, "closed.\(name)") }
            catch let error as OpenTideConstantsError { check(error.code == "io" && error.message == "the release is closed", "closed.\(name)") }
        }
        do { _ = try await client.prune(); check(false, "closed.Client.prune") } catch let error as OpenTideConstantsError { check(error.code == "io", "closed.Client.prune") }
        do { _ = try await client.download(to: NSTemporaryDirectory()); check(false, "closed.Client.download") } catch let error as OpenTideConstantsError { check(error.code == "io", "closed.Client.download") }
        do { _ = try await client.latest(); check(false, "closed.Client.latest") } catch let error as OpenTideConstantsError { check(error.code == "io", "closed.Client.latest") }
        do { _ = try await client.releases(); check(false, "closed.Client.releases") } catch let error as OpenTideConstantsError { check(error.code == "io", "closed.Client.releases") }
        do { _ = try await client.checkForUpdate(); check(false, "closed.Client.checkForUpdate") } catch let error as OpenTideConstantsError { check(error.code == "io", "closed.Client.checkForUpdate") }
        check(release.datestamp == raw["release"]["datestamp"].string, "closed.metadata.readable")
        let requiredNonnull = Set(api["objects"].object.flatMap { owner, object in object["members"].array.filter { applicable($0) && $0["nullable"].bool == false && $0["swift_returns"].string?.hasSuffix("?") == true }.compactMap { $0["name"].string.map { owner + "." + $0 } } })
        let missingNonnull = requiredNonnull.subtracting(coveredNonnull).sorted()
        if !missingNonnull.isEmpty { problems.append("required canonical nonnull rows not sampled: \(missingNonnull)") }
        print("native value checks: \(valueCount); projected canonical nonnull rows sampled: \(requiredNonnull.intersection(coveredNonnull).count)/\(requiredNonnull.count); unsampled: \(missingNonnull.count)")
        return problems
        } catch {
            problems.append("native value proof failed after \(valueCount) checks: \(error)")
            return problems
        }
    }

    static func process(_ command: [String], directory: URL? = nil, environment: [String: String]? = nil) throws -> (Int32, String) {
        let process = Process(); process.executableURL = URL(fileURLWithPath: "/usr/bin/env"); process.arguments = command
        process.currentDirectoryURL = directory; process.environment = environment
        let pipe = Pipe(); process.standardOutput = pipe; process.standardError = pipe
        try process.run()
        let output = String(decoding: pipe.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self)
        process.waitUntilExit()
        try require(process.terminationReason == .exit, "process terminated by signal: \(command)\n\(output)")
        return (process.terminationStatus, output)
    }
    static func compilerGraph(root: URL, executable: URL) throws -> JSONValue {
        if let supplied = ProcessInfo.processInfo.environment["OTC_SWIFT_API_SYMBOLGRAPH"] { return try JSONDecoder().decode(JSONValue.self, from: Data(contentsOf: URL(fileURLWithPath: supplied))) }
        let scratch = FileManager.default.temporaryDirectory.appendingPathComponent("otc-symbolgraph-" + UUID().uuidString)
        try FileManager.default.createDirectory(at: scratch, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: scratch) }
        let (sdkCode, sdk) = try process(["xcrun", "--show-sdk-path"])
        try require(sdkCode == 0, "cannot locate Swift SDK: \(sdk)")
        #if arch(arm64)
        let target = "arm64-apple-macosx13.0"
        #else
        let target = "x86_64-apple-macosx13.0"
        #endif
        let bin = executable.deletingLastPathComponent()
        // The extractor must come from the toolchain that built the module. xcrun gives the selected Xcode's, which
        // can be an older Swift (the CI job builds with swiftly 6.4), so the job names its own in this variable.
        let extractor = ProcessInfo.processInfo.environment["OTC_SWIFT_SYMBOLGRAPH_EXTRACT"].map { [$0] } ?? ["xcrun", "swift-symbolgraph-extract"]
        let (code, output) = try process(extractor + ["-sdk", sdk.trimmingCharacters(in: .whitespacesAndNewlines), "-module-name", "OpenTideConstants", "-I", bin.path, "-I", bin.appendingPathComponent("Modules").path, "-I", root.appendingPathComponent("swift/Sources/CZlib").path, "-target", target, "-minimum-access-level", "public", "-skip-synthesized-members", "-output-dir", scratch.path])
        try require(code == 0, "compiler symbol extraction failed: \(output)")
        return try JSONDecoder().decode(JSONValue.self, from: Data(contentsOf: scratch.appendingPathComponent("OpenTideConstants.symbols.json")))
    }
    /// Mutate private copies of the real SDK, compile each one, then run this checker.
    /// A compiler error or checker crash never counts as a caught API mutation.
    static func selfTest(root: URL, manifest: String, native: String) throws {
        let fm = FileManager.default
        let scratch = fm.temporaryDirectory.appendingPathComponent("otc-api-mutants-" + UUID().uuidString)
        try fm.createDirectory(at: scratch.appendingPathComponent("swift"), withIntermediateDirectories: true)
        defer { try? fm.removeItem(at: scratch) }
        for name in ["Package.swift", "Sources"] { try fm.copyItem(at: root.appendingPathComponent("swift/" + name), to: scratch.appendingPathComponent("swift/" + name)) }
        let package = "conformance/runners/otc-swift"
        try fm.createDirectory(at: scratch.appendingPathComponent(package), withIntermediateDirectories: true)
        for name in ["Package.swift", "Sources"] { try fm.copyItem(at: root.appendingPathComponent(package + "/" + name), to: scratch.appendingPathComponent(package + "/" + name)) }
        let mutations: [(String, String, String, String, String?)] = [
            ("missing-member", "Release.swift", "public func convention(conventionId:String)", "public func removedConvention(conventionId:String)", "missing public member Release.convention"),
            ("extra-member", "Release.swift", "public var buildCommit:", "public var extraCheckerMember:Bool { true };public var buildCommit:", "extra public member Release.extraCheckerMember"),
            ("height-default", "Client.swift", "stepS:Int64=600", "stepS:Int64=300", "value Client.heights.stepS=600/StationId/Date"),
            ("sets-default", "Models.swift", "constantSets(includeNoConstants: Bool = false)", "constantSets(includeNoConstants: Bool = true)", "value Station.constantSets.includeNoConstants=false"),
            ("datums-default", "Client.swift", "allSets:Bool=false", "allSets:Bool=true", "value Client.datums.allSets=false/one"),
            ("enum-value", "Enums.swift", "case `tide` = \"tide\"", "case `tide` = \"wrong_tide\"", "value enum.kind.rawValues"),
            ("error-code", "Errors.swift", "case .pinnedRelease: return \"pinned_release\"", "case .pinnedRelease: return \"wrong_pinned_release\"", "value error.pinned_release.code"),
            ("argument-label", "Client.swift", "public func prune(keep:Int64=3)", "public func prune(preserve keep:Int64=3)", "OpenTideConstants.prune: argument labels"),
            ("lifecycle", "Release.swift", "internal func checkOpen()throws { if closed", "internal func checkOpen()throws { if false", "value closed.Release.stats"),
            ("nonnull", "Models.swift", "public var name: String? { raw[\"name\"].string }", "public var name: String? { nil }", "canonical nonnull Station["),
            ("json-shape", "Models.swift", "public var originalMetadata: JSONValue { raw[\"original_metadata\"].isNull ? .object([:]) : raw[\"original_metadata\"] }", "public var originalMetadata: JSONValue { .array([]) }", "canonical shape Station["),
            ("harmless-control", "Release.swift", "import Foundation", "import Foundation\n// Harmless native API mutation control.", nil)
        ]
        let original = Dictionary(uniqueKeysWithValues: try Set(mutations.map { $0.1 }).map { file in (file, try String(contentsOf: scratch.appendingPathComponent("swift/Sources/OpenTideConstants/" + file), encoding: .utf8)) })
        var env = ProcessInfo.processInfo.environment
        env["OTC_SWIFT_API_SYMBOLGRAPH"] = nil
        env["OTC_SWIFT_API_MANIFEST"] = manifest
        env["OTC_CORE_NATIVE_JSON"] = native
        env["OTC_SWIFT_API_SOURCE_ROOT"] = scratch.path
        for (name, file, from, to, expected) in mutations {
            for (leaf, bytes) in original { try bytes.write(to: scratch.appendingPathComponent("swift/Sources/OpenTideConstants/" + leaf), atomically: true, encoding: .utf8) }
            let source = original[file] ?? ""
            try require(source.contains(from), "self-test \(name): actual source mutation absent")
            try source.replacingOccurrences(of: from, with: to).write(to: scratch.appendingPathComponent("swift/Sources/OpenTideConstants/" + file), atomically: true, encoding: .utf8)
            print("SELF-TEST \(name) compiling actual private SDK")
            let (buildCode, buildOutput) = try process(["swift", "build", "--package-path", package, "--product", "CheckAPI", "--jobs", "2", "-Xswiftc", "-warnings-as-errors"], directory: scratch)
            try require(buildCode == 0, "self-test \(name): invalid compiled mutant (never a rejection)\n\(buildOutput)")
            let (pathCode, bin) = try process(["swift", "build", "--package-path", package, "--show-bin-path"], directory: scratch)
            try require(pathCode == 0, "self-test \(name): binary path unavailable")
            let (code, output) = try process([bin.trimmingCharacters(in: .whitespacesAndNewlines) + "/CheckAPI", "--no-self-test"], directory: scratch, environment: env)
            if let expected { try require(code == 1 && output.contains("PROBLEM " + expected), "self-test \(name): expected real rejection absent\n\(output)") }
            else { try require(code == 0, "self-test harmless control rejected\n\(output)") }
            print("SELF-TEST \(name) compiled=true exit=\(code) \(expected == nil ? "CONTROL PASS" : "CAUGHT")")
        }
        print("self-test: 11 actual compiled SDK mutations caught (9 API/default/lifecycle; 2 canonical nonnull/shape); 1 harmless compiled control passed; 0 skipped")
    }
    static func main() async {
        do {
            let env = ProcessInfo.processInfo.environment
            var root = URL(fileURLWithPath: #filePath)
            for _ in 0..<6 { root.deleteLastPathComponent() }
            if let supplied = env["OTC_SWIFT_API_SOURCE_ROOT"] { root = URL(fileURLWithPath: supplied) }
            let manifest = env["OTC_SWIFT_API_MANIFEST"] ?? root.appendingPathComponent("conformance/api.json").path
            // The value proof and the self-test need the private small Otaru/NOAA/no_constants fixture. Without it,
            // only the API surface is checked, and the output says that the other two did not run.
            let native = env["OTC_CORE_NATIVE_JSON"]
            let api = try JSONDecoder().decode(JSONValue.self, from: Data(contentsOf: URL(fileURLWithPath: manifest)))
            let graph = try compilerGraph(root: root, executable: URL(fileURLWithPath: CommandLine.arguments[0]).standardizedFileURL)
            let surface = try surfaceProblems(api, graph)
            var problems = surface.problems
            if let native {
                do { problems += try await valueProblems(api, path: native) } catch { problems.append("native value proof failed: \(error)") }
            } else {
                print("SKIP native value proof and self-test: OTC_CORE_NATIVE_JSON is not set (it names the private small Otaru/NOAA/no_constants fixture)")
            }
            for problem in problems { print("PROBLEM " + problem) }
            print("API manifest check (suite \(api["suite_version"].string ?? "unknown")): \(surface.names) applicable canonical public names; \(surface.rows) native member rows; \(problems.count) problems")
            if !problems.isEmpty { exit(1) }
            if let native, !CommandLine.arguments.contains("--no-self-test") { try selfTest(root: root, manifest: manifest, native: native) }
        } catch { print("PROBLEM \(error)"); exit(1) }
    }
}

// Typed projections read real native getters. Optional and JSONValue wrappers
// retain null, so canonical nonnull checks cannot disappear into Swift metadata.
private protocol APINativeValue {
    func apiValue() throws -> JSONValue
}
extension String: APINativeValue { fileprivate func apiValue() throws -> JSONValue { .string(self) } }
extension Bool: APINativeValue { fileprivate func apiValue() throws -> JSONValue { .bool(self) } }
extension Int: APINativeValue { fileprivate func apiValue() throws -> JSONValue { .integer(Int64(self)) } }
extension Int64: APINativeValue { fileprivate func apiValue() throws -> JSONValue { .integer(self) } }
extension Double: APINativeValue { fileprivate func apiValue() throws -> JSONValue { .number(self) } }
extension JSONValue: APINativeValue { fileprivate func apiValue() throws -> JSONValue { self } }
extension Date: APINativeValue {
    fileprivate func apiValue() throws -> JSONValue {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return .string(formatter.string(from: self))
    }
}
extension Optional: APINativeValue where Wrapped: APINativeValue {
    fileprivate func apiValue() throws -> JSONValue { try self?.apiValue() ?? .null }
}
extension Array: APINativeValue where Element: APINativeValue {
    fileprivate func apiValue() throws -> JSONValue { .array(try map { try $0.apiValue() }) }
}
extension Dictionary: APINativeValue where Key == String, Value: APINativeValue {
    fileprivate func apiValue() throws -> JSONValue { .object(try mapValues { try $0.apiValue() }) }
}
private extension CheckAPI {
    static func native<T: APINativeValue>(_ value: T) throws -> JSONValue { try value.apiValue() }
}
extension Kind: APINativeValue { fileprivate func apiValue() throws -> JSONValue { .string(rawValue) } }
extension StationType: APINativeValue { fileprivate func apiValue() throws -> JSONValue { .string(rawValue) } }
extension StationStatus: APINativeValue { fileprivate func apiValue() throws -> JSONValue { .string(rawValue) } }
extension RemovedReason: APINativeValue { fileprivate func apiValue() throws -> JSONValue { .string(rawValue) } }
extension SourceType: APINativeValue { fileprivate func apiValue() throws -> JSONValue { .string(rawValue) } }
extension Quantity: APINativeValue { fileprivate func apiValue() throws -> JSONValue { .string(rawValue) } }
extension QcStatus: APINativeValue { fileprivate func apiValue() throws -> JSONValue { .string(rawValue) } }
extension LoadedFrom: APINativeValue { fileprivate func apiValue() throws -> JSONValue { .string(rawValue) } }
extension PhaseReference: APINativeValue { fileprivate func apiValue() throws -> JSONValue { .string(rawValue) } }
extension NodalHandling: APINativeValue { fileprivate func apiValue() throws -> JSONValue { .string(rawValue) } }
extension CanaryStatus: APINativeValue { fileprivate func apiValue() throws -> JSONValue { .string(rawValue) } }
extension HeightAdjustedType: APINativeValue { fileprivate func apiValue() throws -> JSONValue { .string(rawValue) } }
extension DroppedReason: APINativeValue { fileprivate func apiValue() throws -> JSONValue { .string(rawValue) } }
extension QcFlagName: APINativeValue { fileprivate func apiValue() throws -> JSONValue { .string(rawValue) } }
extension TimeBaseCode: APINativeValue { fileprivate func apiValue() throws -> JSONValue { .string(rawValue) } }
extension DecisionTier: APINativeValue { fileprivate func apiValue() throws -> JSONValue { .string(rawValue) } }
extension DecisionOutcome: APINativeValue { fileprivate func apiValue() throws -> JSONValue { .string(rawValue) } }
extension AliasSystem: APINativeValue { fileprivate func apiValue() throws -> JSONValue { .string(rawValue) } }
extension Mode: APINativeValue { fileprivate func apiValue() throws -> JSONValue { .string(rawValue) } }
extension OnNetworkError: APINativeValue { fileprivate func apiValue() throws -> JSONValue { .string(rawValue) } }
extension Format: APINativeValue { fileprivate func apiValue() throws -> JSONValue { .string(rawValue) } }
extension Match: APINativeValue { fileprivate func apiValue() throws -> JSONValue { .string(rawValue) } }
extension ExtremeType: APINativeValue { fileprivate func apiValue() throws -> JSONValue { .string(rawValue) } }
extension CurrentEventType: APINativeValue { fileprivate func apiValue() throws -> JSONValue { .string(rawValue) } }
extension PredictionMethod: APINativeValue { fileprivate func apiValue() throws -> JSONValue { .string(rawValue) } }
extension FallbackReason: APINativeValue { fileprivate func apiValue() throws -> JSONValue { .string(rawValue) } }
extension SourceRole: APINativeValue { fileprivate func apiValue() throws -> JSONValue { .string(rawValue) } }
extension SourceDisposition: APINativeValue { fileprivate func apiValue() throws -> JSONValue { .string(rawValue) } }
extension Release: APINativeValue {
    fileprivate func apiValue() throws -> JSONValue {
        .object([
            "datestamp": try CheckAPI.native(self.datestamp),
            "created": try CheckAPI.native(self.created),
            "format_version": try CheckAPI.native(self.formatVersion),
            "zenodo_version_doi": try CheckAPI.native(self.zenodoVersionDoi),
            "concept_doi": try CheckAPI.native(self.conceptDoi),
            "source_versions": try CheckAPI.native(self.sourceVersions),
            "build_commit": try CheckAPI.native(self.buildCommit),
            "changelog_url": try CheckAPI.native(self.changelogUrl),
            "files": try CheckAPI.native(self.files),
            "conventions": try CheckAPI.native(self.conventions),
            "licences": try CheckAPI.native(self.licences),
            "constituent_names": try CheckAPI.native(self.constituentNames),
            "stats": try CheckAPI.native(self.stats),
            "station_count": try CheckAPI.native(self.stationCount),
            "tombstone_count": try CheckAPI.native(self.tombstoneCount),
            "citation": try CheckAPI.native(self.citation),
            "historical_offsets_policy": try CheckAPI.native(self.historicalOffsetsPolicy)
        ])
    }
}
extension ReleaseInfo: APINativeValue {
    fileprivate func apiValue() throws -> JSONValue {
        .object([
            "datestamp": try CheckAPI.native(self.datestamp),
            "format_version": try CheckAPI.native(self.formatVersion),
            "concept_doi": try CheckAPI.native(self.conceptDoi),
            "zenodo_version_doi": try CheckAPI.native(self.zenodoVersionDoi),
            "content_sha256": try CheckAPI.native(self.contentSha256),
            "files": try CheckAPI.native(self.files)
        ])
    }
}
extension FileInfo: APINativeValue {
    fileprivate func apiValue() throws -> JSONValue {
        .object([
            "name": try CheckAPI.native(self.name),
            "url": try CheckAPI.native(self.url),
            "size": try CheckAPI.native(self.size),
            "sha256": try CheckAPI.native(self.sha256)
        ])
    }
}
extension Station: APINativeValue {
    fileprivate func apiValue() throws -> JSONValue {
        .object([
            "station_id": try CheckAPI.native(self.stationId),
            "name": try CheckAPI.native(self.name),
            "country": try CheckAPI.native(self.country),
            "lat": try CheckAPI.native(self.lat),
            "lon": try CheckAPI.native(self.lon),
            "type": try CheckAPI.native(self.type),
            "kind": try CheckAPI.native(self.kind),
            "timezone": try CheckAPI.native(self.timezone),
            "aliases": try CheckAPI.native(self.aliases),
            "status": try CheckAPI.native(self.status),
            "is_reference": try CheckAPI.native(self.isReference),
            "is_subordinate": try CheckAPI.native(self.isSubordinate),
            "is_tide": try CheckAPI.native(self.isTide),
            "is_current": try CheckAPI.native(self.isCurrent),
            "recommended_set": try CheckAPI.native(self.recommendedSet),
            "subordinate_offsets": try CheckAPI.native(self.subordinateOffsets),
            "validation": try CheckAPI.native(self.validation),
            "raw": try CheckAPI.native(self.raw),
            "recommended_is_fallback": try CheckAPI.native(self.recommendedIsFallback),
            "source_records": try CheckAPI.native(self.sourceRecords)
        ])
    }
}
extension Tombstone: APINativeValue {
    fileprivate func apiValue() throws -> JSONValue {
        .object([
            "station_id": try CheckAPI.native(self.stationId),
            "name": try CheckAPI.native(self.name),
            "status": try CheckAPI.native(self.status),
            "removed_in": try CheckAPI.native(self.removedIn),
            "removed_reason": try CheckAPI.native(self.removedReason),
            "merged_into": try CheckAPI.native(self.mergedInto),
            "detail": try CheckAPI.native(self.detail),
            "raw": try CheckAPI.native(self.raw)
        ])
    }
}
extension ConstantSet: APINativeValue {
    fileprivate func apiValue() throws -> JSONValue {
        .object([
            "set_id": try CheckAPI.native(self.setId),
            "source": try CheckAPI.native(self.source),
            "source_type": try CheckAPI.native(self.sourceType),
            "quantity": try CheckAPI.native(self.quantity),
            "source_record_id": try CheckAPI.native(self.sourceRecordId),
            "source_version": try CheckAPI.native(self.sourceVersion),
            "record_span": try CheckAPI.native(self.recordSpan),
            "datum": try CheckAPI.native(self.datum),
            "qc_status": try CheckAPI.native(self.qcStatus),
            "qc_flags": try CheckAPI.native(self.qcFlags),
            "dropped_constituents": try CheckAPI.native(self.droppedConstituents),
            "time_base": try CheckAPI.native(self.timeBase),
            "is_recommended": try CheckAPI.native(self.isRecommended),
            "convention": try CheckAPI.native(self.convention),
            "licence": try CheckAPI.native(self.licence),
            "provenance": try CheckAPI.native(self.provenance),
            "validation": try CheckAPI.native(self.validation),
            "constituents": try CheckAPI.native(self.constituents),
            "raw": try CheckAPI.native(self.raw),
            "fallback": try CheckAPI.native(self.fallback)
        ])
    }
}
extension Constituent: APINativeValue {
    fileprivate func apiValue() throws -> JSONValue {
        .object([
            "name": try CheckAPI.native(self.name),
            "source_name": try CheckAPI.native(self.sourceName),
            "doodson": try CheckAPI.native(self.doodson),
            "speed_deg_per_hour": try CheckAPI.native(self.speedDegPerHour),
            "amplitude_m": try CheckAPI.native(self.amplitudeM),
            "phase_deg": try CheckAPI.native(self.phaseDeg),
            "amp_uncertainty_m": try CheckAPI.native(self.ampUncertaintyM),
            "phase_uncertainty_deg": try CheckAPI.native(self.phaseUncertaintyDeg),
            "kept_reason": try CheckAPI.native(self.keptReason),
            "raw": try CheckAPI.native(self.raw)
        ])
    }
}
extension Convention: APINativeValue {
    fileprivate func apiValue() throws -> JSONValue {
        .object([
            "convention_id": try CheckAPI.native(self.conventionId),
            "phase_reference": try CheckAPI.native(self.phaseReference),
            "utc_offset_hours": try CheckAPI.native(self.utcOffsetHours),
            "v0_model": try CheckAPI.native(self.v0Model),
            "nodal_handling": try CheckAPI.native(self.nodalHandling),
            "nodal_formula_ids": try CheckAPI.native(self.nodalFormulaIds),
            "constituent_table_version": try CheckAPI.native(self.constituentTableVersion),
            "tables_sha256": try CheckAPI.native(self.tablesSha256),
            "canary": try CheckAPI.native(self.canary),
            "raw": try CheckAPI.native(self.raw)
        ])
    }
}
extension Licence: APINativeValue {
    fileprivate func apiValue() throws -> JSONValue {
        .object([
            "licence_id": try CheckAPI.native(self.licenceId),
            "spdx": try CheckAPI.native(self.spdx),
            "provider": try CheckAPI.native(self.provider),
            "citation": try CheckAPI.native(self.citation),
            "attribution": try CheckAPI.native(self.attribution),
            "url": try CheckAPI.native(self.url),
            "commercial_use": try CheckAPI.native(self.commercialUse),
            "restriction": try CheckAPI.native(self.restriction),
            "terms_url": try CheckAPI.native(self.termsUrl),
            "raw": try CheckAPI.native(self.raw)
        ])
    }
}
extension Provenance: APINativeValue {
    fileprivate func apiValue() throws -> JSONValue {
        .object([
            "adapter_version": try CheckAPI.native(self.adapterVersion),
            "input_sha256": try CheckAPI.native(self.inputSha256),
            "selection_reason": try CheckAPI.native(self.selectionReason),
            "decision": try CheckAPI.native(self.decision),
            "build": try CheckAPI.native(self.build),
            "carried_from_release": try CheckAPI.native(self.carriedFromRelease),
            "raw": try CheckAPI.native(self.raw)
        ])
    }
}
extension ProvenanceBuild: APINativeValue {
    fileprivate func apiValue() throws -> JSONValue {
        .object([
            "build_commit": try CheckAPI.native(self.buildCommit),
            "built_at": try CheckAPI.native(self.builtAt),
            "fetched_at": try CheckAPI.native(self.fetchedAt),
            "run_id": try CheckAPI.native(self.runId),
            "tool_versions": try CheckAPI.native(self.toolVersions)
        ])
    }
}
extension TimeBase: APINativeValue {
    fileprivate func apiValue() throws -> JSONValue {
        .object([
            "code": try CheckAPI.native(self.code),
            "reason": try CheckAPI.native(self.reason),
            "declared": try CheckAPI.native(self.declared),
            "published": try CheckAPI.native(self.published),
            "correction": try CheckAPI.native(self.correction),
            "months_dropped": try CheckAPI.native(self.monthsDropped),
            "decided_in": try CheckAPI.native(self.decidedIn),
            "decided_build_commit": try CheckAPI.native(self.decidedBuildCommit),
            "evidence": try CheckAPI.native(self.evidence)
        ])
    }
}
extension QcFlag: APINativeValue {
    fileprivate func apiValue() throws -> JSONValue {
        .object([
            "flag": try CheckAPI.native(self.flag),
            "reason": try CheckAPI.native(self.reason),
            "values": try CheckAPI.native(self.values)
        ])
    }
}
extension DroppedConstituent: APINativeValue {
    fileprivate func apiValue() throws -> JSONValue {
        .object([
            "name": try CheckAPI.native(self.name),
            "dropped_reason": try CheckAPI.native(self.droppedReason),
            "detail": try CheckAPI.native(self.detail)
        ])
    }
}
extension Validation: APINativeValue {
    fileprivate func apiValue() throws -> JSONValue {
        .object([
            "set_id": try CheckAPI.native(self.setId),
            "reference_source": try CheckAPI.native(self.referenceSource),
            "reference_station": try CheckAPI.native(self.referenceStation),
            "reference_distance_km": try CheckAPI.native(self.referenceDistanceKm),
            "window": try CheckAPI.native(self.window),
            "time_mae_min": try CheckAPI.native(self.timeMaeMin),
            "time_p95_min": try CheckAPI.native(self.timeP95Min),
            "time_bias_min": try CheckAPI.native(self.timeBiasMin),
            "height_mae_m": try CheckAPI.native(self.heightMaeM),
            "range_error_m": try CheckAPI.native(self.rangeErrorM),
            "missed_events": try CheckAPI.native(self.missedEvents),
            "extra_events": try CheckAPI.native(self.extraEvents),
            "previous_release": try CheckAPI.native(self.previousRelease)
        ])
    }
}
extension SubordinateOffsets: APINativeValue {
    fileprivate func apiValue() throws -> JSONValue {
        .object([
            "reference_station_id": try CheckAPI.native(self.referenceStationId),
            "time_offset_high_min": try CheckAPI.native(self.timeOffsetHighMin),
            "time_offset_low_min": try CheckAPI.native(self.timeOffsetLowMin),
            "height_offset_high": try CheckAPI.native(self.heightOffsetHigh),
            "height_offset_low": try CheckAPI.native(self.heightOffsetLow),
            "height_adjusted_type": try CheckAPI.native(self.heightAdjustedType),
            "licence_id": try CheckAPI.native(self.licenceId),
            "offset_id": try CheckAPI.native(self.offsetId),
            "source": try CheckAPI.native(self.source),
            "source_type": try CheckAPI.native(self.sourceType),
            "source_version": try CheckAPI.native(self.sourceVersion),
            "source_record_id": try CheckAPI.native(self.sourceRecordId),
            "qc_status": try CheckAPI.native(self.qcStatus),
            "qc_flags": try CheckAPI.native(self.qcFlags),
            "fallback": try CheckAPI.native(self.fallback),
            "vintage": try CheckAPI.native(self.vintage),
            "provenance": try CheckAPI.native(self.provenance)
        ])
    }
}
extension Nearby: APINativeValue {
    fileprivate func apiValue() throws -> JSONValue {
        .object([
            "station": try CheckAPI.native(self.station),
            "distance_km": try CheckAPI.native(self.distanceKm)
        ])
    }
}
extension UpdateResult: APINativeValue {
    fileprivate func apiValue() throws -> JSONValue {
        .object([
            "updated": try CheckAPI.native(self.updated),
            "from": try CheckAPI.native(self.from),
            "to": try CheckAPI.native(self.to)
        ])
    }
}
extension RecordSpan: APINativeValue {
    fileprivate func apiValue() throws -> JSONValue {
        .object([
            "start": try CheckAPI.native(self.start),
            "end": try CheckAPI.native(self.end),
            "good_samples": try CheckAPI.native(self.goodSamples)
        ])
    }
}
extension Datum: APINativeValue {
    fileprivate func apiValue() throws -> JSONValue {
        .object([
            "msl_offset_m": try CheckAPI.native(self.mslOffsetM),
            "named": try CheckAPI.native(self.named)
        ])
    }
}
extension Stats: APINativeValue {
    fileprivate func apiValue() throws -> JSONValue {
        .object([
            "type": try CheckAPI.native(self.type),
            "kind": try CheckAPI.native(self.kind),
            "country": try CheckAPI.native(self.country),
            "source": try CheckAPI.native(self.source),
            "qc_status": try CheckAPI.native(self.qcStatus)
        ])
    }
}
extension HeightPoint: APINativeValue {
    fileprivate func apiValue() throws -> JSONValue {
        .object([
            "units": try CheckAPI.native(self.units),
            "height": try CheckAPI.native(self.height),
            "time": try CheckAPI.native(self.time),
            "height_m": try CheckAPI.native(self.heightM),
            "local_time": try CheckAPI.native(self.localTime),
            "utc_offset_s": try CheckAPI.native(self.utcOffsetS)
        ])
    }
}
extension Extreme: APINativeValue {
    fileprivate func apiValue() throws -> JSONValue {
        .object([
            "units": try CheckAPI.native(self.units),
            "height": try CheckAPI.native(self.height),
            "time": try CheckAPI.native(self.time),
            "type": try CheckAPI.native(self.type),
            "height_m": try CheckAPI.native(self.heightM),
            "local_time": try CheckAPI.native(self.localTime),
            "utc_offset_s": try CheckAPI.native(self.utcOffsetS)
        ])
    }
}
extension CurrentPoint: APINativeValue {
    fileprivate func apiValue() throws -> JSONValue {
        .object([
            "units": try CheckAPI.native(self.units),
            "velocity_major": try CheckAPI.native(self.velocityMajor),
            "velocity_minor": try CheckAPI.native(self.velocityMinor),
            "speed": try CheckAPI.native(self.speed),
            "time": try CheckAPI.native(self.time),
            "velocity_major_ms": try CheckAPI.native(self.velocityMajorMs),
            "velocity_minor_ms": try CheckAPI.native(self.velocityMinorMs),
            "speed_ms": try CheckAPI.native(self.speedMs),
            "direction_deg": try CheckAPI.native(self.directionDeg),
            "local_time": try CheckAPI.native(self.localTime),
            "utc_offset_s": try CheckAPI.native(self.utcOffsetS)
        ])
    }
}
extension CurrentEvent: APINativeValue {
    fileprivate func apiValue() throws -> JSONValue {
        .object([
            "units": try CheckAPI.native(self.units),
            "velocity": try CheckAPI.native(self.velocity),
            "time": try CheckAPI.native(self.time),
            "type": try CheckAPI.native(self.type),
            "velocity_ms": try CheckAPI.native(self.velocityMs),
            "direction_deg": try CheckAPI.native(self.directionDeg),
            "local_time": try CheckAPI.native(self.localTime),
            "utc_offset_s": try CheckAPI.native(self.utcOffsetS)
        ])
    }
}
extension HeightSeries: APINativeValue {
    fileprivate func apiValue() throws -> JSONValue {
        .object([
            "units": try CheckAPI.native(self.units),
            "items": try CheckAPI.native(self.items),
            "station_id": try CheckAPI.native(self.stationId),
            "timezone": try CheckAPI.native(self.timezone),
            "method": try CheckAPI.native(self.method),
            "set_id": try CheckAPI.native(self.setId),
            "convention_id": try CheckAPI.native(self.conventionId),
            "astro_table_id": try CheckAPI.native(self.astroTableId),
            "reference_station_id": try CheckAPI.native(self.referenceStationId),
            "reference_bin": try CheckAPI.native(self.referenceBin),
            "datum": try CheckAPI.native(self.datum),
            "datum_name": try CheckAPI.native(self.datumName),
            "datum_kind": try CheckAPI.native(self.datumKind),
            "datum_uncertainty_m": try CheckAPI.native(self.datumUncertaintyM),
            "tz": try CheckAPI.native(self.tz),
            "tz_version": try CheckAPI.native(self.tzVersion),
            "release": try CheckAPI.native(self.release),
            "algorithm": try CheckAPI.native(self.algorithm),
            "offset_id": try CheckAPI.native(self.offsetId),
            "offset_source": try CheckAPI.native(self.offsetSource),
            "offset_source_version": try CheckAPI.native(self.offsetSourceVersion),
            "historical_offsets": try CheckAPI.native(self.historicalOffsets),
            "current_validity": try CheckAPI.native(self.currentValidity),
            "current_accuracy": try CheckAPI.native(self.currentAccuracy),
            "reference_set_id": try CheckAPI.native(self.referenceSetId),
            "reference_source_version": try CheckAPI.native(self.referenceSourceVersion),
            "reference_2020_equivalence": try CheckAPI.native(self.reference2020Equivalence),
            "source_note": try CheckAPI.native(self.sourceNote)
        ])
    }
}
extension ExtremeList: APINativeValue {
    fileprivate func apiValue() throws -> JSONValue {
        .object([
            "units": try CheckAPI.native(self.units),
            "items": try CheckAPI.native(self.items),
            "station_id": try CheckAPI.native(self.stationId),
            "timezone": try CheckAPI.native(self.timezone),
            "method": try CheckAPI.native(self.method),
            "set_id": try CheckAPI.native(self.setId),
            "convention_id": try CheckAPI.native(self.conventionId),
            "astro_table_id": try CheckAPI.native(self.astroTableId),
            "reference_station_id": try CheckAPI.native(self.referenceStationId),
            "reference_bin": try CheckAPI.native(self.referenceBin),
            "datum": try CheckAPI.native(self.datum),
            "datum_name": try CheckAPI.native(self.datumName),
            "datum_kind": try CheckAPI.native(self.datumKind),
            "datum_uncertainty_m": try CheckAPI.native(self.datumUncertaintyM),
            "tz": try CheckAPI.native(self.tz),
            "tz_version": try CheckAPI.native(self.tzVersion),
            "release": try CheckAPI.native(self.release),
            "algorithm": try CheckAPI.native(self.algorithm),
            "offset_id": try CheckAPI.native(self.offsetId),
            "offset_source": try CheckAPI.native(self.offsetSource),
            "offset_source_version": try CheckAPI.native(self.offsetSourceVersion),
            "historical_offsets": try CheckAPI.native(self.historicalOffsets),
            "current_validity": try CheckAPI.native(self.currentValidity),
            "current_accuracy": try CheckAPI.native(self.currentAccuracy),
            "reference_set_id": try CheckAPI.native(self.referenceSetId),
            "reference_source_version": try CheckAPI.native(self.referenceSourceVersion),
            "reference_2020_equivalence": try CheckAPI.native(self.reference2020Equivalence),
            "source_note": try CheckAPI.native(self.sourceNote)
        ])
    }
}
extension CurrentSeries: APINativeValue {
    fileprivate func apiValue() throws -> JSONValue {
        .object([
            "units": try CheckAPI.native(self.units),
            "items": try CheckAPI.native(self.items),
            "station_id": try CheckAPI.native(self.stationId),
            "timezone": try CheckAPI.native(self.timezone),
            "method": try CheckAPI.native(self.method),
            "set_id": try CheckAPI.native(self.setId),
            "convention_id": try CheckAPI.native(self.conventionId),
            "astro_table_id": try CheckAPI.native(self.astroTableId),
            "reference_station_id": try CheckAPI.native(self.referenceStationId),
            "reference_bin": try CheckAPI.native(self.referenceBin),
            "datum": try CheckAPI.native(self.datum),
            "datum_name": try CheckAPI.native(self.datumName),
            "datum_kind": try CheckAPI.native(self.datumKind),
            "datum_uncertainty_m": try CheckAPI.native(self.datumUncertaintyM),
            "bin_number": try CheckAPI.native(self.binNumber),
            "tz": try CheckAPI.native(self.tz),
            "tz_version": try CheckAPI.native(self.tzVersion),
            "release": try CheckAPI.native(self.release),
            "algorithm": try CheckAPI.native(self.algorithm)
        ])
    }
}
extension CurrentEventList: APINativeValue {
    fileprivate func apiValue() throws -> JSONValue {
        .object([
            "units": try CheckAPI.native(self.units),
            "items": try CheckAPI.native(self.items),
            "station_id": try CheckAPI.native(self.stationId),
            "timezone": try CheckAPI.native(self.timezone),
            "method": try CheckAPI.native(self.method),
            "set_id": try CheckAPI.native(self.setId),
            "convention_id": try CheckAPI.native(self.conventionId),
            "astro_table_id": try CheckAPI.native(self.astroTableId),
            "reference_station_id": try CheckAPI.native(self.referenceStationId),
            "reference_bin": try CheckAPI.native(self.referenceBin),
            "datum": try CheckAPI.native(self.datum),
            "datum_name": try CheckAPI.native(self.datumName),
            "datum_kind": try CheckAPI.native(self.datumKind),
            "datum_uncertainty_m": try CheckAPI.native(self.datumUncertaintyM),
            "bin_number": try CheckAPI.native(self.binNumber),
            "omitted_event_types": try CheckAPI.native(self.omittedEventTypes),
            "tz": try CheckAPI.native(self.tz),
            "tz_version": try CheckAPI.native(self.tzVersion),
            "release": try CheckAPI.native(self.release),
            "algorithm": try CheckAPI.native(self.algorithm)
        ])
    }
}
extension DatumInfo: APINativeValue {
    fileprivate func apiValue() throws -> JSONValue {
        .object([
            "set_id": try CheckAPI.native(self.setId),
            "zero": try CheckAPI.native(self.zero),
            "zero_name": try CheckAPI.native(self.zeroName),
            "chart_datum": try CheckAPI.native(self.chartDatum),
            "msl_offset_m": try CheckAPI.native(self.mslOffsetM),
            "levels": try CheckAPI.native(self.levels)
        ])
    }
}
extension DatumLevel: APINativeValue {
    fileprivate func apiValue() throws -> JSONValue {
        .object([
            "key": try CheckAPI.native(self.key),
            "value_m": try CheckAPI.native(self.valueM),
            "above_chart_m": try CheckAPI.native(self.aboveChartM),
            "kind": try CheckAPI.native(self.kind),
            "method": try CheckAPI.native(self.method),
            "source_name": try CheckAPI.native(self.sourceName),
            "epoch": try CheckAPI.native(self.epoch),
            "data_span": try CheckAPI.native(self.dataSpan),
            "control_station_id": try CheckAPI.native(self.controlStationId),
            "control_set_id": try CheckAPI.native(self.controlSetId),
            "control_source_id": try CheckAPI.native(self.controlSourceId),
            "uncertainty_m": try CheckAPI.native(self.uncertaintyM),
            "uncertainty_basis": try CheckAPI.native(self.uncertaintyBasis),
            "flags": try CheckAPI.native(self.flags),
            "fallback": try CheckAPI.native(self.fallback)
        ])
    }
}
extension Ranges: APINativeValue {
    fileprivate func apiValue() throws -> JSONValue {
        .object([
            "mn": try CheckAPI.native(self.mn),
            "gt": try CheckAPI.native(self.gt),
            "dhq": try CheckAPI.native(self.dhq),
            "dlq": try CheckAPI.native(self.dlq)
        ])
    }
}
extension Fallback: APINativeValue {
    fileprivate func apiValue() throws -> JSONValue {
        .object([
            "reason": try CheckAPI.native(self.reason),
            "basis": try CheckAPI.native(self.basis),
            "otc_finding": try CheckAPI.native(self.otcFinding),
            "preferred_set_id": try CheckAPI.native(self.preferredSetId),
            "raw": try CheckAPI.native(self.raw)
        ])
    }
}
extension SourceRecord: APINativeValue {
    fileprivate func apiValue() throws -> JSONValue {
        .object([
            "source": try CheckAPI.native(self.source),
            "source_version": try CheckAPI.native(self.sourceVersion),
            "source_record_id": try CheckAPI.native(self.sourceRecordId),
            "role": try CheckAPI.native(self.role),
            "disposition": try CheckAPI.native(self.disposition),
            "detail": try CheckAPI.native(self.detail),
            "licence_id": try CheckAPI.native(self.licenceId),
            "upstream_licence_id": try CheckAPI.native(self.upstreamLicenceId),
            "published_set_ids": try CheckAPI.native(self.publishedSetIds),
            "provenance": try CheckAPI.native(self.provenance),
            "original_metadata": try CheckAPI.native(self.originalMetadata),
            "original_harmonics": try CheckAPI.native(self.originalHarmonics),
            "licence": try CheckAPI.native(self.licence),
            "upstream_licence": try CheckAPI.native(self.upstreamLicence),
            "raw": try CheckAPI.native(self.raw)
        ])
    }
}
extension HistoricalOffsetVintage: APINativeValue {
    fileprivate func apiValue() throws -> JSONValue {
        .object([
            "publication_year": try CheckAPI.native(self.publicationYear),
            "source_lifecycle": try CheckAPI.native(self.sourceLifecycle),
            "removal_events": try CheckAPI.native(self.removalEvents),
            "current_validity": try CheckAPI.native(self.currentValidity),
            "current_accuracy": try CheckAPI.native(self.currentAccuracy),
            "reference_2020_equivalence": try CheckAPI.native(self.reference2020Equivalence),
            "reference_2020_equivalence_sha256": try CheckAPI.native(self.reference2020EquivalenceSha256)
        ])
    }
}
extension HistoricalOffsetProvenance: APINativeValue {
    fileprivate func apiValue() throws -> JSONValue {
        .object([
            "source_manifest_sha256": try CheckAPI.native(self.sourceManifestSha256),
            "input_sha256": try CheckAPI.native(self.inputSha256),
            "book": try CheckAPI.native(self.book),
            "annual_table_row": try CheckAPI.native(self.annualTableRow),
            "printed_page": try CheckAPI.native(self.printedPage),
            "pdf_page": try CheckAPI.native(self.pdfPage),
            "raw_row_text": try CheckAPI.native(self.rawRowText),
            "raw_values_json": try CheckAPI.native(self.rawValuesJson),
            "id_crosswalk": try CheckAPI.native(self.idCrosswalk),
            "reference_binding": try CheckAPI.native(self.referenceBinding),
            "acceptance_report_sha256": try CheckAPI.native(self.acceptanceReportSha256)
        ])
    }
}
