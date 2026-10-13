import XCTest
@testable import OpenTideConstants

final class PredictTests: XCTestCase {
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
