import XCTest
@testable import OpenTideConstants

final class PredictTests: XCTestCase {
    func testHistoricalReferenceDeclaredTableHashCompatibility() throws {
        let source = try XCTUnwrap(ProcessInfo.processInfo.environment["OTC_PRED_HISTORICAL"])
        let original = try JSONValue.parse(Data(contentsOf: URL(fileURLWithPath: source)))
        let target = try XCTUnwrap(original["stations"].array.first { $0["subordinate_offsets"]["offset_id"].string != nil })
        let stationId = try XCTUnwrap(target["station_id"].string)
        let reference = try XCTUnwrap(original["stations"].array.first {
            $0["station_id"] == target["subordinate_offsets"]["reference_station_id"]
        })
        let constants = try XCTUnwrap(reference["constant_sets"].array.first {
            $0["source"].string == "noaa" && $0["quantity"].string == "water_level"
        })
        let conventionIndex = try XCTUnwrap(original["conventions"].array.firstIndex {
            $0["convention_id"] == constants["convention_id"]
        })
        let tableIndex = try XCTUnwrap(original["astro_tables"].array.firstIndex {
            $0["astro_table_id"] == original["conventions"].array[conventionIndex]["astro_table_id"]
        })
        let start = try XCTUnwrap(parseTime("2026-10-11T00:00:00Z"))
        let stop = try XCTUnwrap(parseTime("2026-10-12T00:00:00Z"))
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        var expected: [Extreme]?
        for mode in [Mode.eager, .stream] {
            for fault in ["valid", "matching_hash", "null_hash", "wrong_convention_hash", "wrong_table_hash"] {
                var document = original.object
                var conventions = original["conventions"].array
                var tables = original["astro_tables"].array
                var convention = conventions[conventionIndex].object
                var table = tables[tableIndex].object
                if fault == "matching_hash" || fault == "wrong_table_hash" {
                    convention["tables_sha256"] = table["tables_sha256"]
                }
                if fault == "null_hash" { convention["tables_sha256"] = .null }
                if fault == "wrong_convention_hash" { convention["tables_sha256"] = .string(String(repeating: "0", count: 64)) }
                if fault == "wrong_table_hash" { table["tables_sha256"] = .string(String(repeating: "0", count: 64)) }
                conventions[conventionIndex] = .object(convention)
                tables[tableIndex] = .object(table)
                document["conventions"] = .array(conventions)
                document["astro_tables"] = .array(tables)
                let local = directory.appendingPathComponent("\(mode)-\(fault)")
                try FileManager.default.createDirectory(at: local, withIntermediateDirectories: true)
                let file = local.appendingPathComponent("OTC_20261011." + (mode == .eager ? "json" : "jsonl"))
                if mode == .eager {
                    try JSONValue.object(document).data().write(to: file)
                } else {
                    var lines = Data()
                    for station in original["stations"].array {
                        lines.append(try station.data())
                        lines.append(10)
                    }
                    try lines.write(to: file)
                    document.removeValue(forKey: "stations")
                    try JSONValue.object(document).data().write(to: local.appendingPathComponent("OTC_20261011.meta.json"))
                }
                let release = try Reader.load(file, mode: mode, commercialOnly: false,
                                              commercialBasis: "strict", historicalOffsetsPolicy: "fallback")
                defer { release.close() }
                let listed = try release.stations().contains { $0.stationId == stationId }
                let label = "\(mode) \(fault)"
                if fault.hasPrefix("wrong_") {
                    XCTAssertFalse(listed, label)
                    XCTAssertThrowsError(try release.extremes(stationId: stationId, start: start, stop: stop, datum: "chart"), label) { error in
                        XCTAssertEqual((error as? OpenTideConstantsError)?.code, "unsupported_convention", label)
                        XCTAssertEqual((error as? OpenTideConstantsError)?.fields, [:], label)
                    }
                } else {
                    XCTAssertTrue(listed, label)
                    let actual = try release.extremes(stationId: stationId, start: start, stop: stop, datum: "chart")
                    XCTAssertEqual(actual.items.count, 4, label)
                    if let expected { XCTAssertEqual(actual.items, expected, label) }
                    else { expected = actual.items }
                }
            }
        }
    }

    func testHistoricalTableModelMismatchRefusesPrediction() throws {
        let root = try XCTUnwrap(ProcessInfo.processInfo.environment["OTC_HISTORY_SW_PROOF_ROOT"])
        let instant = try XCTUnwrap(parseTime("2026-10-11T00:00:00Z"))
        for mode in [Mode.eager, .stream] {
            let suffix = mode == .eager ? "json" : "jsonl"
            let file = URL(fileURLWithPath: root + "/inputs/model_mismatch/OTC_20261011." + suffix)
            let release = try Reader.load(file, mode: mode, commercialOnly: false,
                                          commercialBasis: "strict", historicalOffsetsPolicy: "fallback")
            defer { release.close() }
            for id in ["OTC-28c56e20", "OTC-541f1a73"] {
                XCTAssertThrowsError(try release.extremes(stationId: id, start: instant, stop: instant, datum: "chart")) { error in
                    XCTAssertEqual((error as? OpenTideConstantsError)?.code, "unsupported_convention")
                }
            }
        }
    }

    func testActualThreeNativePredictionCells() throws {
        let source = try XCTUnwrap(ProcessInfo.processInfo.environment["OTC_SWIFT_VECTOR_JSON"])
        let r = try Reader.load(URL(fileURLWithPath: source), mode: .eager, commercialOnly: false, commercialBasis: "strict", historicalOffsetsPolicy: "fallback")
        let start = try XCTUnwrap(parseTime("2026-01-01T00:00:00Z"))
        let stop = try XCTUnwrap(parseTime("2026-01-02T00:00:00Z"))
        let heights = try r.heightsAt(stationId: "OTC-V-NOAA-1820000", times: [start])
        XCTAssertEqual(heights.items.count, 1)
        let currents = try r.currents(stationId: "OTC-V-NOAA-BOS1101", start: start, stop: stop, binNumber: 15)
        XCTAssertEqual(currents.items.count, 144)
        let events = try r.currentEvents(stationId: "OTC-V-NOAA-ACT1591", start: start, stop: stop, binNumber: 1)
        XCTAssertFalse(events.items.isEmpty)
        XCTAssertEqual(events.referenceStationId, "OTC-V-NOAA-ACT1616")
    }
}
