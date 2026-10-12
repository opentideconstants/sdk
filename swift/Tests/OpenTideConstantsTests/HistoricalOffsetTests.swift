import XCTest
@testable import OpenTideConstants

final class HistoricalOffsetTests: XCTestCase {
    func testActualHistoricalProfiles() throws {
        let source = try XCTUnwrap(ProcessInfo.processInfo.environment["OTC_CORE_NATIVE_JSONL"])
        let r = try Reader.load(URL(fileURLWithPath: source), mode: .stream, commercialOnly: false, commercialBasis: "strict", historicalOffsetsPolicy: "fallback")
        let start = try XCTUnwrap(parseTime("2020-01-01T00:00:00Z"))
        let stop = try XCTUnwrap(parseTime("2020-01-02T00:00:00Z"))
        for id in ["OTC-28c56e20", "OTC-541f1a73"] {
            let station = try r.requireStation(stationId: id)
            let original = station.raw
            let result = try r.extremes(station: station, start: start, stop: stop)
            XCTAssertFalse(result.items.isEmpty)
            XCTAssertTrue(result.historicalOffsets)
            XCTAssertEqual(result.offsetId, station.subordinateOffsets?.offsetId)
            XCTAssertEqual(result.currentValidity, "unestablished")
            XCTAssertEqual(result.currentAccuracy, "unverified")
            XCTAssertEqual(result.reference2020Equivalence, "disagrees")
            XCTAssertEqual(result.offsetSource, "noaa")
            XCTAssertEqual(result.offsetSourceVersion, "annual-tide-tables-2020")
            XCTAssertNil(result.setId)
            XCTAssertNotNil(result.referenceSetId)
            XCTAssertNotNil(result.referenceSourceVersion)
            XCTAssertEqual(result.sourceNote, "OTC historical-offset calculation using NOAA2020 parameters; retired NOAA profile; current validity unestablished; current accuracy unverified.")
            let explicit = try r.extremes(stationId: id, start: start, stop: stop, offsetId: station.subordinateOffsets?.offsetId)
            XCTAssertEqual(result, explicit)
            let offsets = try XCTUnwrap(station.subordinateOffsets)
            let reference = try r.extremes(stationId: offsets.referenceStationId, start: start.addingTimeInterval(-7200), stop: stop.addingTimeInterval(7200), datum: "chart")
            for type in [ExtremeType.high, .low] {
                let point = try XCTUnwrap(result.items.first { $0.type == type })
                let minutes = type == .high ? offsets.timeOffsetHighMin! : offsets.timeOffsetLowMin!
                let adjustment = type == .high ? offsets.heightOffsetHigh! : offsets.heightOffsetLow!
                let source = try XCTUnwrap(reference.items.first { $0.type == type && $0.time.addingTimeInterval(minutes * 60) == point.time })
                let expected = offsets.heightAdjustedType == .r ? source.heightM * adjustment : source.heightM + adjustment
                XCTAssertEqual(point.heightM, expected, accuracy: 1e-12)
                print("HISTORICAL_VALUE \(id) \(type.rawValue) source=\(source.heightM) adjustment=\(adjustment) minutes=\(minutes) result=\(point.heightM) time=\(point.time.timeIntervalSince1970)")
            }
            XCTAssertEqual(station.raw, original)
            XCTAssertThrowsError(try r.heights(station: station, start: start, stop: stop)) { error in
                XCTAssertEqual((error as? OpenTideConstantsError)?.code, "extremes_only")
            }
        }
        let contemporary = try r.extremes(stationId: "OTC-a6c00a3f", start: start, stop: stop)
        XCTAssertEqual(contemporary.items.count, 4)
        XCTAssertFalse(contemporary.historicalOffsets)
        XCTAssertEqual(contemporary.items[0].heightM, 0.3850561469775751, accuracy: 1e-12)
        print("H4_VALUE OTC-a6c00a3f first=\(contemporary.items[0].heightM) events=\(contemporary.items.count)")
        let strict = try Reader.load(URL(fileURLWithPath: source), mode: .stream, commercialOnly: false, commercialBasis: "strict", historicalOffsetsPolicy: "exclude")
        for id in ["OTC-28c56e20", "OTC-541f1a73"] {
            let station = try strict.requireStation(stationId: id)
            for flagged in [false, true] {
                for fallback in [false, true] {
                    XCTAssertTrue(try strict.search(name: station.name!, match: "exact", includeFlagged: flagged, includeFallback: fallback).allSatisfy { $0.stationId != id })
                }
            }
            for offset in [nil, station.subordinateOffsets?.offsetId] {
                XCTAssertThrowsError(try strict.extremes(stationId: id, start: start, stop: stop, offsetId: offset)) { error in
                    XCTAssertEqual((error as? OpenTideConstantsError)?.code, "historical_offsets_excluded")
                }
            }
        }
        XCTAssertEqual(try strict.extremes(stationId: "OTC-a6c00a3f", start: start, stop: stop), contemporary)
    }
}
