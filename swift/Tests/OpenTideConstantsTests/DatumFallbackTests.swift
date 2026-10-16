import XCTest
@testable import OpenTideConstants

final class DatumFallbackTests: XCTestCase {
    private func check(_ info: DatumInfo, datum: JSONValue, label: String) throws {
        let named = datum["named"].object
        let chart = datum["chart_datum"].string.flatMap { named[$0]?.number }
        XCTAssertEqual(info.zero, datum["zero"].string, label)
        XCTAssertEqual(info.zeroName, datum["zero_name"].string, label)
        XCTAssertEqual(info.chartDatum, datum["chart_datum"].string, label)
        XCTAssertEqual(info.mslOffsetM, datum["msl_offset_m"].number, label)
        XCTAssertEqual(info.levels.compactMap(\.key), named.keys.sorted(), label)
        for level in info.levels {
            let key = try XCTUnwrap(level.key)
            let basis = datum["basis"][key]
            let expected = basis.object["fallback"].flatMap { $0.isNull ? nil : $0 }
            XCTAssertEqual(level.fallback, expected, "\(label) \(key): complete fallback")
            XCTAssertEqual(level.valueM, named[key]?.number, label)
            XCTAssertEqual(level.aboveChartM, chart.map { level.valueM - $0 }, label)
            XCTAssertEqual(level.kind, basis["kind"].string, label)
            XCTAssertEqual(level.method, basis["method"].string, label)
            XCTAssertEqual(level.sourceName, basis["source_name"].string, label)
            XCTAssertEqual(level.epoch, basis["epoch"], label)
            XCTAssertEqual(level.dataSpan, basis["data_span"], label)
            XCTAssertEqual(level.controlStationId, basis["control"]["station_id"].string, label)
            XCTAssertEqual(level.controlSetId, basis["control"]["set_id"].string, label)
            XCTAssertEqual(level.controlSourceId, basis["control"]["source_id"].string, label)
            XCTAssertEqual(level.uncertaintyM, basis["uncertainty_m"].number, label)
            XCTAssertEqual(level.uncertaintyBasis, basis["uncertainty_basis"].string, label)
            XCTAssertEqual(level.flags, basis["flags"].array.compactMap(\.string), label)
        }
    }

    func testProjectionPreservesCompleteFallbackAndAbsentMetadata() throws {
        let metadata: JSONValue = .object([
            "reason": .string("datum_gate_failed"), "basis": .string("calibrated"),
            "otc_finding": .string("acceptance unestablished"),
            "details": .object(["checks": .array([.bool(false), .integer(7)])])
        ])
        let datum: JSONValue = .object([
            "named": .object(["otc_lat": .number(-1.4), "lat": .number(-1.2), "hat": .number(1.7)]),
            "basis": .object([
                "otc_lat": .object(["kind": .string("computed"), "fallback": metadata]),
                "lat": .object(["kind": .string("published")]),
                "hat": .object(["kind": .string("published"), "fallback": .null])
            ])
        ])
        try check(Predict.datumInfo(setId: "test", raw: datum), datum: datum, label: "projection")
    }

    func testExistingInitializerDefaultsToNoFallback() {
        let level = DatumLevel(key: "lat", valueM: -1.2, aboveChartM: nil, kind: "published", method: "source", sourceName: "LAT", epoch: .null, dataSpan: .null, controlStationId: nil, controlSetId: nil, controlSourceId: nil, uncertaintyM: nil, uncertaintyBasis: nil, flags: [])
        XCTAssertNil(level.fallback)
    }

    func testActualThreeNativeDatums() throws {
        guard let source = ProcessInfo.processInfo.environment["OTC_DATUM_FALLBACK_CONTRACT"] else {
            throw XCTSkip("Set OTC_DATUM_FALLBACK_CONTRACT to run the actual three native release cases")
        }
        let contract = try JSONValue.parse(Data(contentsOf: URL(fileURLWithPath: source)))
        XCTAssertEqual(contract["cases"].array.count, 3)
        let fixture = contract["release_fixture"]
        var unlabelled = fixture.object
        unlabelled["stations"] = .array(fixture["stations"].array.map { station in
            var row = station.object
            row["constant_sets"] = .array(station["constant_sets"].array.map { constants in
                var set = constants.object
                if !constants["datum"].isNull {
                    var datum = constants["datum"].object
                    datum["basis"] = .object(constants["datum"]["basis"].object.mapValues { basis in
                        var fields = basis.object
                        fields.removeValue(forKey: "fallback")
                        return .object(fields)
                    })
                    set["datum"] = .object(datum)
                }
                return .object(set)
            })
            return .object(row)
        })
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let file = directory.appendingPathComponent("OTC_20261011.json")
        let originalFile = directory.appendingPathComponent("unlabelled/OTC_20261011.json")
        try FileManager.default.createDirectory(at: originalFile.deletingLastPathComponent(), withIntermediateDirectories: true)
        try fixture.data().write(to: file)
        try JSONValue.object(unlabelled).data().write(to: originalFile)
        let release = try Reader.load(file, mode: .eager, commercialOnly: false, commercialBasis: "strict", historicalOffsetsPolicy: "fallback")
        let original = try Reader.load(originalFile, mode: .eager, commercialOnly: false, commercialBasis: "strict", historicalOffsetsPolicy: "fallback")
        defer { release.close(); original.close() }
        let times = try ["2026-01-01T00:00:00Z", "2026-06-01T12:00:00Z"].map { try XCTUnwrap(parseTime($0)) }
        for entry in contract["cases"].array {
            let id = try XCTUnwrap(entry["station_id"].string)
            let setId = try XCTUnwrap(entry["set_id"].string)
            let station = try release.requireStation(stationId: id)
            let before = try original.requireStation(stationId: id)
            XCTAssertEqual(station.recommendedSet?.setId, entry["recommended_set_id"].string)
            XCTAssertEqual(station.recommendedSet?.setId, before.recommendedSet?.setId)
            XCTAssertEqual(station.constantSets(includeNoConstants: true).map(\.setId), before.constantSets(includeNoConstants: true).map(\.setId))
            guard case .one(let selected) = try release.datums(stationId: id), let info = selected else {
                XCTFail("\(id): missing public selected datums"); continue
            }
            XCTAssertEqual(info.setId, setId)
            try check(info, datum: entry["datum"], label: id)
            XCTAssertEqual(try release.datums(station: station, setId: setId), .one(info))
            XCTAssertEqual(try release.datums(stationId: id, setId: setId), .one(info))
            guard case .all(let all) = try release.datums(station: station, allSets: true) else {
                XCTFail("\(id): missing public all-set datums"); continue
            }
            XCTAssertEqual(all.map(\.setId), station.constantSets(includeNoConstants: true).map(\.setId))
            XCTAssertEqual(try release.datums(stationId: id, allSets: true), .all(all))
            for item in all {
                let constants = try XCTUnwrap(station.constantSets(includeNoConstants: true).first { $0.setId == item.setId })
                try check(item, datum: constants.raw["datum"], label: "\(id) allSets")
            }
            let heights = try release.heightsAt(stationId: id, times: times)
            XCTAssertEqual(heights, try original.heightsAt(stationId: id, times: times))
            let computed = info.levels.filter { $0.kind == "computed" }
            XCTAssertEqual(computed.count, 2)
            print("DATUM_FALLBACK station=\(id) set=\(info.setId ?? "nil") metadata=\(computed.filter { $0.fallback != nil }.count)/2 values=\(info.levels.map { "\($0.key ?? "nil"):\($0.valueM)" }.joined(separator: ",")) heights=\(heights.items.map(\.heightM)) existing_fields=checked ranking=unchanged predictions=unchanged")
        }
    }
}
