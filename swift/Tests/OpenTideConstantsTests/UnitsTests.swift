import Foundation
import XCTest
@testable import OpenTideConstants

final class UnitsTests: XCTestCase {
    private var fixture: URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("conformance/fixtures/predict/OTC_20991231.7.json")
    }

    func testSelectedValuesDefaultsAndLocalization() throws {
        let time = Date(timeIntervalSince1970: 1267401600)
        let height = HeightPoint(time: time, heightM: -0.3048, units: "feet")
        XCTAssertEqual(height.height, -1)
        XCTAssertEqual(height.heightM, -0.3048)
        XCTAssertEqual(HeightPoint(time: time, heightM: 2).height, 2)
        XCTAssertEqual(HeightPoint(time: time, heightM: 2).units, "meters")
        let series = HeightSeries(items: [height], timezone: "America/New_York", units: "feet")
        let local = try series.toLocal()
        XCTAssertEqual(local.units, "feet")
        XCTAssertEqual(local.items[0].units, "feet")
        XCTAssertEqual(local.items[0].height, -1)
        XCTAssertEqual(local.items[0].time, time)
        let knot = 1852.0 / 3600.0
        let current = CurrentPoint(time: time, velocityMajorMs: -knot, velocityMinorMs: 0, speedMs: knot, directionDeg: 90, units: "knots")
        XCTAssertEqual(current.velocityMajor, -1)
        XCTAssertEqual(current.velocityMinor, 0)
        XCTAssertEqual(current.speed, 1)
        let currentLocal = try CurrentSeries(items: [current], timezone: "America/New_York", units: "knots").toLocal()
        XCTAssertEqual(currentLocal.units, "knots")
        XCTAssertEqual(currentLocal.items[0].velocityMajor, -1)
        let event = CurrentEvent(time: time, type: .maxEbb, velocityMs: -knot, directionDeg: 90, units: "knots")
        let events = try CurrentEventList(items: [event], timezone: "America/New_York", units: "knots").toLocal()
        XCTAssertEqual(events.items[0].velocity, -1)
        XCTAssertEqual(events.units, "knots")
        let extreme = Extreme(time: time, type: .high, heightM: 0.3048, units: "feet")
        let extremes = try ExtremeList(items: [extreme], timezone: "America/New_York", units: "feet").toLocal()
        XCTAssertEqual(extremes.items[0].height, 1)
        XCTAssertEqual(extremes.units, "feet")
    }

    func testPublicCallsAndOverloads() async throws {
        let client = try await OpenTideConstants.open(file: fixture.path)
        defer { client.close() }
        let release = client.release
        let start = Date(timeIntervalSince1970: 1267401600)
        let stop = start.addingTimeInterval(86400)
        let heightStation = try release.requireStation(stationId: "OTC-P-0001")
        let currentStation = try release.requireStation(stationId: "OTC-P-0016")
        let si = try release.heights(stationId: heightStation.stationId, start: start, stop: stop)
        let feet = try client.heights(station: heightStation, start: start, stop: stop, units: "feet")
        XCTAssertEqual(feet.items.map(\.heightM), si.items.map(\.heightM))
        XCTAssertEqual(feet.items.map(\.height), si.items.map { $0.heightM / 0.3048 })
        XCTAssertEqual(feet.units, "feet")
        XCTAssertEqual(try client.heights(stationId: heightStation.stationId, start: start, stop: stop, units: "feet"), feet)
        let at = try client.heightsAt(station: heightStation, times: [start], units: "feet")
        XCTAssertEqual(try client.heightsAt(stationId: heightStation.stationId, times: [start], units: "feet"), at)
        let extremes = try client.extremes(station: heightStation, start: start, stop: stop, units: "feet")
        XCTAssertEqual(try client.extremes(stationId: heightStation.stationId, start: start, stop: stop, units: "feet"), extremes)
        XCTAssertTrue(extremes.items.allSatisfy { $0.units == "feet" && $0.height == $0.heightM / 0.3048 })
        let currents = try client.currents(station: currentStation, start: start, stop: stop, units: "knots")
        XCTAssertEqual(try client.currents(stationId: currentStation.stationId, start: start, stop: stop, units: "knots"), currents)
        XCTAssertTrue(currents.items.allSatisfy { $0.units == "knots" && $0.speed == $0.speedMs / (1852.0 / 3600.0) })
        let events = try client.currentEvents(station: currentStation, start: start, stop: stop, units: "knots")
        XCTAssertEqual(try client.currentEvents(stationId: currentStation.stationId, start: start, stop: stop, units: "knots"), events)
        XCTAssertTrue(events.items.allSatisfy { $0.units == "knots" && $0.velocity == $0.velocityMs / (1852.0 / 3600.0) })
        XCTAssertEqual(si.units, "meters")
        XCTAssertEqual(si, try release.heights(station: heightStation, start: start, stop: stop, units: "meters"))
        XCTAssertThrowsError(try client.heightsAt(station: heightStation, times: [start], units: "knots")) { error in
            XCTAssertEqual((error as? OpenTideConstantsError)?.code, "invalid_argument")
        }
        XCTAssertThrowsError(try client.currents(station: currentStation, start: start, stop: stop, units: "feet")) { error in
            XCTAssertEqual((error as? OpenTideConstantsError)?.code, "invalid_argument")
        }
    }
    func testCanonicalUnitsRoundtrip() throws {
        let time = Date(timeIntervalSince1970: 1267401600)
        if case .HeightPoint(let actual) = try Canonical.materializeTypedModel(
            rawFields: .HeightPoint(CanonicalHeightPointFields(time: time, heightM: 0.3048, localTime: nil, utcOffsetS: nil, units: "feet")),
            fieldContract: CanonicalFieldContract(modelType: .HeightPoint, members: [.HeightPointUnits]),
            origin: UUID(), modelType: .HeightPoint
        ) {
            XCTAssertEqual(actual, HeightPoint(time: time, heightM: 0.3048, localTime: nil, utcOffsetS: nil, units: "feet"))
            XCTAssertEqual(actual.units, "feet")
        } else { XCTFail("wrong canonical HeightPoint variant") }
        if case .Extreme(let actual) = try Canonical.materializeTypedModel(
            rawFields: .Extreme(CanonicalExtremeFields(time: time, type: .high, heightM: 0.3048, localTime: nil, utcOffsetS: nil, units: "feet")),
            fieldContract: CanonicalFieldContract(modelType: .Extreme, members: [.ExtremeUnits]),
            origin: UUID(), modelType: .Extreme
        ) {
            XCTAssertEqual(actual, Extreme(time: time, type: .high, heightM: 0.3048, localTime: nil, utcOffsetS: nil, units: "feet"))
            XCTAssertEqual(actual.units, "feet")
        } else { XCTFail("wrong canonical Extreme variant") }
        if case .CurrentPoint(let actual) = try Canonical.materializeTypedModel(
            rawFields: .CurrentPoint(CanonicalCurrentPointFields(time: time, velocityMajorMs: 0.3048, velocityMinorMs: 0.3048, speedMs: 0.3048, directionDeg: nil, localTime: nil, utcOffsetS: nil, units: "knots")),
            fieldContract: CanonicalFieldContract(modelType: .CurrentPoint, members: [.CurrentPointUnits]),
            origin: UUID(), modelType: .CurrentPoint
        ) {
            XCTAssertEqual(actual, CurrentPoint(time: time, velocityMajorMs: 0.3048, velocityMinorMs: 0.3048, speedMs: 0.3048, directionDeg: nil, localTime: nil, utcOffsetS: nil, units: "knots"))
            XCTAssertEqual(actual.units, "knots")
        } else { XCTFail("wrong canonical CurrentPoint variant") }
        if case .CurrentEvent(let actual) = try Canonical.materializeTypedModel(
            rawFields: .CurrentEvent(CanonicalCurrentEventFields(time: time, type: .maxEbb, velocityMs: 0.3048, directionDeg: nil, localTime: nil, utcOffsetS: nil, units: "knots")),
            fieldContract: CanonicalFieldContract(modelType: .CurrentEvent, members: [.CurrentEventUnits]),
            origin: UUID(), modelType: .CurrentEvent
        ) {
            XCTAssertEqual(actual, CurrentEvent(time: time, type: .maxEbb, velocityMs: 0.3048, directionDeg: nil, localTime: nil, utcOffsetS: nil, units: "knots"))
            XCTAssertEqual(actual.units, "knots")
        } else { XCTFail("wrong canonical CurrentEvent variant") }
        if case .HeightSeries(let actual) = try Canonical.materializeTypedModel(
            rawFields: .HeightSeries(CanonicalHeightSeriesFields(items: [], stationId: nil, timezone: nil, method: nil, setId: nil, conventionId: nil, astroTableId: nil, referenceStationId: nil, referenceBin: nil, datum: nil, datumName: nil, datumKind: nil, datumUncertaintyM: nil, tz: nil, tzVersion: nil, release: nil, algorithm: nil, offsetId: nil, offsetSource: nil, offsetSourceVersion: nil, historicalOffsets: false, currentValidity: nil, currentAccuracy: nil, referenceSetId: nil, referenceSourceVersion: nil, reference2020Equivalence: nil, sourceNote: nil, units: "feet")),
            fieldContract: CanonicalFieldContract(modelType: .HeightSeries, members: [.HeightSeriesUnits]),
            origin: UUID(), modelType: .HeightSeries
        ) {
            XCTAssertEqual(actual, HeightSeries(items: [], stationId: nil, timezone: nil, method: nil, setId: nil, conventionId: nil, astroTableId: nil, referenceStationId: nil, referenceBin: nil, datum: nil, datumName: nil, datumKind: nil, datumUncertaintyM: nil, tz: nil, tzVersion: nil, release: nil, algorithm: nil, offsetId: nil, offsetSource: nil, offsetSourceVersion: nil, historicalOffsets: false, currentValidity: nil, currentAccuracy: nil, referenceSetId: nil, referenceSourceVersion: nil, reference2020Equivalence: nil, sourceNote: nil, units: "feet"))
            XCTAssertEqual(actual.units, "feet")
        } else { XCTFail("wrong canonical HeightSeries variant") }
        if case .ExtremeList(let actual) = try Canonical.materializeTypedModel(
            rawFields: .ExtremeList(CanonicalExtremeListFields(items: [], stationId: nil, timezone: nil, method: nil, setId: nil, conventionId: nil, astroTableId: nil, referenceStationId: nil, referenceBin: nil, datum: nil, datumName: nil, datumKind: nil, datumUncertaintyM: nil, tz: nil, tzVersion: nil, release: nil, algorithm: nil, offsetId: nil, offsetSource: nil, offsetSourceVersion: nil, historicalOffsets: false, currentValidity: nil, currentAccuracy: nil, referenceSetId: nil, referenceSourceVersion: nil, reference2020Equivalence: nil, sourceNote: nil, units: "feet")),
            fieldContract: CanonicalFieldContract(modelType: .ExtremeList, members: [.ExtremeListUnits]),
            origin: UUID(), modelType: .ExtremeList
        ) {
            XCTAssertEqual(actual, ExtremeList(items: [], stationId: nil, timezone: nil, method: nil, setId: nil, conventionId: nil, astroTableId: nil, referenceStationId: nil, referenceBin: nil, datum: nil, datumName: nil, datumKind: nil, datumUncertaintyM: nil, tz: nil, tzVersion: nil, release: nil, algorithm: nil, offsetId: nil, offsetSource: nil, offsetSourceVersion: nil, historicalOffsets: false, currentValidity: nil, currentAccuracy: nil, referenceSetId: nil, referenceSourceVersion: nil, reference2020Equivalence: nil, sourceNote: nil, units: "feet"))
            XCTAssertEqual(actual.units, "feet")
        } else { XCTFail("wrong canonical ExtremeList variant") }
        if case .CurrentSeries(let actual) = try Canonical.materializeTypedModel(
            rawFields: .CurrentSeries(CanonicalCurrentSeriesFields(items: [], stationId: nil, timezone: nil, method: nil, setId: nil, conventionId: nil, astroTableId: nil, referenceStationId: nil, referenceBin: nil, datum: nil, datumName: nil, datumKind: nil, datumUncertaintyM: nil, tz: nil, tzVersion: nil, release: nil, algorithm: nil, binNumber: nil, units: "knots")),
            fieldContract: CanonicalFieldContract(modelType: .CurrentSeries, members: [.CurrentSeriesUnits]),
            origin: UUID(), modelType: .CurrentSeries
        ) {
            XCTAssertEqual(actual, CurrentSeries(items: [], stationId: nil, timezone: nil, method: nil, setId: nil, conventionId: nil, astroTableId: nil, referenceStationId: nil, referenceBin: nil, datum: nil, datumName: nil, datumKind: nil, datumUncertaintyM: nil, tz: nil, tzVersion: nil, release: nil, algorithm: nil, binNumber: nil, units: "knots"))
            XCTAssertEqual(actual.units, "knots")
        } else { XCTFail("wrong canonical CurrentSeries variant") }
        if case .CurrentEventList(let actual) = try Canonical.materializeTypedModel(
            rawFields: .CurrentEventList(CanonicalCurrentEventListFields(items: [], stationId: nil, timezone: nil, method: nil, setId: nil, conventionId: nil, astroTableId: nil, referenceStationId: nil, referenceBin: nil, datum: nil, datumName: nil, datumKind: nil, datumUncertaintyM: nil, tz: nil, tzVersion: nil, release: nil, algorithm: nil, binNumber: nil, omittedEventTypes: nil, units: "knots")),
            fieldContract: CanonicalFieldContract(modelType: .CurrentEventList, members: [.CurrentEventListUnits]),
            origin: UUID(), modelType: .CurrentEventList
        ) {
            XCTAssertEqual(actual, CurrentEventList(items: [], stationId: nil, timezone: nil, method: nil, setId: nil, conventionId: nil, astroTableId: nil, referenceStationId: nil, referenceBin: nil, datum: nil, datumName: nil, datumKind: nil, datumUncertaintyM: nil, tz: nil, tzVersion: nil, release: nil, algorithm: nil, binNumber: nil, omittedEventTypes: nil, units: "knots"))
            XCTAssertEqual(actual.units, "knots")
        } else { XCTFail("wrong canonical CurrentEventList variant") }
    }
}
