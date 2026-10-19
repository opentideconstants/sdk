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

    func testRealTiconHarmonicMeanNamedPredictions() throws {
        guard let source = ProcessInfo.processInfo.environment["OTC_TICON_NATIVE_FILE"] else {
            throw XCTSkip("Set OTC_TICON_NATIVE_FILE to the three actual retained TICON witnesses")
        }
        let witnesses = [
            ("OTC-666303b1", "OTC-666303b1/ticon-4/aberdeen-abe-gbr-bodc"),
            ("OTC-215da48c", "OTC-215da48c/ticon-4/acadia_cove-4170-can-meds/as-published"),
            ("OTC-52fc4ff5", "OTC-52fc4ff5/ticon-4/aero_trading-9338-can-meds")
        ]
        let times = try ["2026-10-11T00:00:00Z", "2026-10-11T12:00:00Z", "2026-10-11T23:00:00Z"].map { try XCTUnwrap(parseTime($0)) }
        for mode in [Mode.eager, Mode.stream] {
            let release = try Reader.load(URL(fileURLWithPath: source), mode: mode, commercialOnly: false, commercialBasis: "strict", historicalOffsetsPolicy: "fallback")
            defer { release.close() }
            for (id, setId) in witnesses {
                let mean = try release.heightsAt(stationId: id, times: times, datum: "mean_level", setId: setId)
                print("TICON_SWIFT mode=\(mode) station=\(id) set=\(mean.setId ?? "nil") mean=\(mean.items.map(\.heightM))")
                let station = try release.requireStation(stationId: id)
                let selected = try XCTUnwrap(station.constantSet(setId: setId))
                let rawDatum = selected.raw["datum"]
                if let originalSource = ProcessInfo.processInfo.environment["OTC_TICON_ORIGINAL_FILE"] {
                    let original = try Reader.load(URL(fileURLWithPath: originalSource), mode: mode, commercialOnly: false, commercialBasis: "strict", historicalOffsetsPolicy: "fallback")
                    defer { original.close() }
                    let before = try original.heightsAt(stationId: id, times: times, datum: "mean_level", setId: setId)
                    XCTAssertEqual(mean, before)
                    let beforeStation = try original.requireStation(stationId: id)
                    XCTAssertEqual(station.recommendedSet?.setId, beforeStation.recommendedSet?.setId)
                    let beforeSet = try XCTUnwrap(beforeStation.constantSet(setId: setId))
                    var withoutDatum = selected.raw.object
                    withoutDatum.removeValue(forKey: "datum")
                    var originalWithoutDatum = beforeSet.raw.object
                    originalWithoutDatum.removeValue(forKey: "datum")
                    XCTAssertEqual(withoutDatum, originalWithoutDatum)
                }
                let meanEvents = try release.extremes(stationId: id, start: times[0], stop: times[2], datum: "mean_level", setId: setId)
                for key in ["lat", "hat"] {
                    do {
                        let named = try release.heightsAt(stationId: id, times: times, datum: key, setId: setId)
                        XCTAssertEqual(named.setId, setId)
                        XCTAssertEqual(named.datumName, key)
                        let level = try XCTUnwrap(rawDatum["named"][key].number)
                        XCTAssertEqual(rawDatum["zero"].string, "harmonic_mean")
                        XCTAssertTrue(rawDatum["msl_offset_m"].isNull)
                        XCTAssertTrue(rawDatum["zero_name"].isNull)
                        XCTAssertNil(named.datumUncertaintyM)
                        XCTAssertEqual(named.datumKind, "computed")
                        for (point, baseline) in zip(named.items, mean.items) {
                            XCTAssertEqual(point.heightM - baseline.heightM, -level, accuracy: 1e-10)
                        }
                        let events = try release.extremes(stationId: id, start: times[0], stop: times[2], datum: key, setId: setId)
                        XCTAssertEqual(events.items.map(\.time), meanEvents.items.map(\.time))
                        XCTAssertEqual(events.items.map(\.type), meanEvents.items.map(\.type))
                        XCTAssertFalse(events.items.isEmpty)
                        for (event, baseline) in zip(events.items, meanEvents.items) {
                            XCTAssertEqual(event.heightM - baseline.heightM, -level, accuracy: 1e-10)
                        }
                        guard case .one(let info) = try release.datums(stationId: id, setId: setId) else {
                            XCTFail("Missing public datum metadata for \(id)"); continue
                        }
                        let metadata = try XCTUnwrap(info)
                        try check(metadata, datum: rawDatum, label: id)
                        XCTAssertEqual(metadata.levels.first { $0.key == key }?.fallback?["reason"].string, "datum_gate_failed")
                        let zero = try release.heightsAt(stationId: id, times: times, datum: "zero", setId: setId)
                        XCTAssertEqual(zero.items, mean.items)
                        XCTAssertEqual(zero.datumName, "harmonic_mean")
                        print("TICON_SWIFT_VALUE mode=\(mode) station=\(id) datum=\(key) shift=\(-level) events=\(events.items.count) times=unchanged sigma=absent metadata=preserved")
                        print("TICON_SWIFT mode=\(mode) station=\(id) datum=\(key) values=\(named.items.map(\.heightM))")
                    } catch {
                        print("TICON_SWIFT mode=\(mode) station=\(id) datum=\(key) error=\(error)")
                        XCTFail("\(id) \(key): \(error)")
                    }
                }
            }
        }
    }

    func testHarmonicMeanResolverKeepsAbsoluteAndMissingDatumErrors() throws {
        guard let source = ProcessInfo.processInfo.environment["OTC_TICON_ORIGINAL_FILE"] else {
            throw XCTSkip("Set OTC_TICON_ORIGINAL_FILE to exercise supplemental datum controls")
        }
        let release = try Reader.load(URL(fileURLWithPath: source), mode: .eager, commercialOnly: false, commercialBasis: "strict", historicalOffsetsPolicy: "fallback")
        defer { release.close() }
        let station = try release.requireStation(stationId: "OTC-666303b1")
        let original = try Predict.context(release, supplied: station, quantity: .waterLevel, setId: "OTC-666303b1/ticon-4/aberdeen-abe-gbr-bodc", datum: "mean_level")
        let relative: JSONValue = .object([
            "zero": .string("harmonic_mean"),
            "named": .object(["lat": .number(-1.2)]),
            "basis": .object(["lat": .object(["kind": .string("computed")])])
        ])
        var context = original
        XCTAssertEqual(try Predict.datum(relative, requested: "lat", context: &context), 1.2)
        XCTAssertEqual(context.datumName, "lat")
        XCTAssertEqual(context.datumKind, "computed")
        XCTAssertNil(context.datumUncertainty)
        context = original
        XCTAssertEqual(try Predict.datum(relative, requested: "zero", context: &context), 0)
        XCTAssertEqual(context.datumName, "harmonic_mean")
        for (raw, key, published, missing) in [
            (JSONValue.null, "lat", false, "msl_offset_m"),
            (relative, "hat", false, "hat"),
            (relative, "chart", false, "chart_datum"),
            (relative, "lat", true, "msl_offset_m")
        ] {
            context = original
            XCTAssertThrowsError(try Predict.datum(raw, requested: key, context: &context, published: published)) { error in
                XCTAssertEqual((error as? OpenTideConstantsError)?.code, "datum_unavailable")
                XCTAssertEqual((error as? OpenTideConstantsError)?.fields["missing"], .string(missing))
            }
        }
        let absolute: JSONValue = .object([
            "zero": .string("gauge_zero"), "zero_name": .string("STND"), "msl_offset_m": .number(2.5),
            "chart_datum": .string("lat"), "named": .object(["lat": .number(0.4)]),
            "basis": .object(["lat": .object(["kind": .string("published"), "uncertainty_m": .number(0.2)])])
        ])
        context = original
        XCTAssertEqual(try Predict.datum(absolute, requested: "zero", context: &context), 2.5)
        XCTAssertEqual(context.datumName, "STND")
        context = original
        XCTAssertEqual(try Predict.datum(absolute, requested: "chart", context: &context, published: true), 2.1)
        XCTAssertEqual(context.datumKind, "published")
        XCTAssertEqual(context.datumUncertainty, 0.2)
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
