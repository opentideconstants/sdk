import XCTest
@testable import OpenTideConstants

final class PredictTests: XCTestCase {
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
