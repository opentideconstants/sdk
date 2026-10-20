import XCTest
@testable import OpenTideConstants

final class PredictTests: XCTestCase {
    func testMixedCurrentBinsSelectOffsetsAndPreserveHarmonics() throws {
        let repository = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        let original = try JSONValue.parse(Data(contentsOf: repository.appendingPathComponent("conformance/vectors/1.0/vectors-release.json")))
        let template = try XCTUnwrap(original["stations"].array.first { $0["station_id"].string == "OTC-V-NOAA-ACT1616" })
        let stationId = try XCTUnwrap(template["station_id"].string)
        let setId = try XCTUnwrap(template["recommended_set_id"].string)
        // These are the four exact NOAA offset tuples. Harmonics remain the existing
        // ACT1616 fixture; full ACT8851/ACT8856 predictions are checked by the native proof.
        let cases: [(String, Int64, [Double], Double, Double, Double, Double)] = [
            ("ACT8851", 1, [15, 2, 5, 17], 1.0, 1.1, 272, 91),
            ("ACT8851", 3, [-1, -3, -13, -18], 0.8, 0.9, 274, 94),
            ("ACT8856", 1, [7, -16, -1, 9], 1.0, 1.1, 295, 125),
            ("ACT8856", 3, [-11, 17, -8, -32], 0.8, 0.6, 306, 115)
        ]
        let start = try XCTUnwrap(parseTime("2027-01-01T08:00:00Z"))
        let stop = try XCTUnwrap(parseTime("2027-01-03T08:00:00Z"))
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        for (source, offsetBin, shifts, floodRatio, ebbRatio, floodDirection, ebbDirection) in cases {
            var station = template.object
            var constants = template["constant_sets"].array[0].object
            var harmonicBin = constants["current_bins"]!.array[0].object
            harmonicBin["bin"] = .number(2)
            constants["current_bins"] = .array([.object(harmonicBin)])
            station["constant_sets"] = .array([.object(constants)])
            station["default_current_bin"] = .number(2)
            let entry: JSONValue = .object([
                "bin": .number(Double(offsetBin)), "reference_station_id": .string(stationId),
                "reference_bin": .number(2), "licence_id": .string("noaa-public-domain"),
                "time_adj_max_flood_min": .number(shifts[0]), "time_adj_slack_before_ebb_min": .number(shifts[1]),
                "time_adj_max_ebb_min": .number(shifts[2]), "time_adj_slack_before_flood_min": .number(shifts[3]),
                "flood_amp_ratio": .number(floodRatio), "ebb_amp_ratio": .number(ebbRatio),
                "mean_flood_dir_deg": .number(floodDirection), "mean_ebb_dir_deg": .number(ebbDirection)
            ])
            station["current_offsets"] = .array([entry])
            var document = original.object
            document["stations"] = .array([.object(station)])
            let file = directory.appendingPathComponent("\(source)-\(offsetBin).json")
            try JSONValue.object(document).data().write(to: file)
            let release = try Reader.load(file, mode: .eager, commercialOnly: false,
                                          commercialBasis: "strict", historicalOffsetsPolicy: "fallback")
            defer { release.close() }
            let harmonic = try release.currentEvents(stationId: stationId, start: start, stop: stop, binNumber: 2)
            let defaultEvents = try release.currentEvents(stationId: stationId, start: start, stop: stop)
            XCTAssertEqual(harmonic.method, .harmonic)
            XCTAssertEqual(defaultEvents.items, harmonic.items)
            let series = try release.currents(stationId: stationId, start: start, stop: stop, binNumber: 2)
            XCTAssertEqual(series.method, .harmonic)
            XCTAssertEqual(try release.currents(stationId: stationId, start: start, stop: stop).items, series.items)
            XCTAssertThrowsError(try release.currentEvents(stationId: stationId, start: start, stop: stop, binNumber: offsetBin, setId: setId)) {
                XCTAssertEqual(($0 as? OpenTideConstantsError)?.code, "bin_not_found")
            }
            XCTAssertThrowsError(try release.currents(stationId: stationId, start: start, stop: stop, binNumber: offsetBin)) {
                XCTAssertEqual(($0 as? OpenTideConstantsError)?.code, "extremes_only")
            }
            let actual = try release.currentEvents(stationId: stationId, start: start, stop: stop, binNumber: offsetBin)
            XCTAssertEqual(actual.method, .offsets)
            XCTAssertEqual(actual.binNumber, offsetBin)
            XCTAssertEqual(actual.referenceStationId, stationId)
            XCTAssertEqual(actual.referenceBin, 2)
            XCTAssertEqual(actual.setId, setId)
            XCTAssertFalse(actual.items.isEmpty)
            let expanded = try release.currentEvents(stationId: stationId, start: start.addingTimeInterval(-7200), stop: stop.addingTimeInterval(7200), binNumber: 2)
            let expected = expanded.items.compactMap { event -> CurrentEvent? in
                let index: Int
                switch event.type {
                case .maxFlood: index = 0
                case .slackBeforeEbb: index = 1
                case .maxEbb: index = 2
                case .slackBeforeFlood: index = 3
                case .other: XCTFail("Unexpected harmonic event type"); return nil
                }
                let time = event.time.addingTimeInterval(shifts[index] * 60)
                guard start <= time && time < stop else { return nil }
                return CurrentEvent(time: time, type: event.type,
                                    velocityMs: index == 0 ? event.velocityMs * floodRatio : index == 2 ? event.velocityMs * ebbRatio : 0,
                                    directionDeg: index == 0 ? floodDirection : index == 2 ? ebbDirection : nil)
            }.sorted { $0.time < $1.time }
            XCTAssertEqual(actual.items.count, expected.count)
            for (event, wanted) in zip(actual.items, expected) {
                XCTAssertEqual(event.time, wanted.time)
                XCTAssertEqual(event.type, wanted.type)
                XCTAssertEqual(event.directionDeg, wanted.directionDeg)
                XCTAssertEqual(event.velocityMs, wanted.velocityMs, accuracy: 1e-9)
            }
        }
    }

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
