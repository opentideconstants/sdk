import Foundation
import XCTest
@testable import OpenTideConstants

final class BboxTests: XCTestCase {
    private var fixture: URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("conformance/fixtures/good/OTC_20991231.2.jsonl")
    }

    func testPublicBoundsFiltersAndLimit() async throws {
        for mode in [Mode.eager, .stream] {
            let cache = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
            defer { try? FileManager.default.removeItem(at: cache) }
            let client = try await OpenTideConstants.open(file: fixture.path, cacheDir: cache.path, mode: mode)
            defer { client.close() }
            let release = client.release
            let expected = ["OTC-T-0001", "OTC-T-0003", "OTC-T-0004"]
            XCTAssertEqual(try client.bbox(south: 37.665, west: -122.4659, north: 37.8063, east: -122.3).map(\.stationId), expected)
            XCTAssertEqual(try release.bbox(south: 37.665, west: -122.4659, north: 37.8063, east: -122.3).map(\.stationId), expected)
            XCTAssertEqual(try release.bbox(south: 37.665, west: -122.4659, north: 37.8063, east: -122.3, limit: 1, type: "subordinate").map(\.stationId), ["OTC-T-0003"])
            XCTAssertEqual(try client.bbox(south: 37.665, west: -122.4659, north: 37.8063, east: -122.3, includeFlagged: true).map(\.stationId), ["OTC-T-0001", "OTC-T-0002", "OTC-T-0003", "OTC-T-0004"])
            XCTAssertEqual(try client.bbox(south: -1, west: 179.8, north: 1, east: -179.8).map(\.stationId), ["OTC-T-0007", "OTC-T-0008"])
            XCTAssertEqual(try release.bbox(south: -1, west: 179.8, north: 1, east: -179.8).map(\.stationId), ["OTC-T-0007", "OTC-T-0008"])
            XCTAssertTrue(try release.bbox(south: 80, west: 0, north: 81, east: 1).isEmpty)
        }
    }

    func testInvalidBoundsAndLimit() async throws {
        let client = try await OpenTideConstants.open(file: fixture.path)
        defer { client.close() }
        for (south, west, north, east) in [(91.0, 0.0, 91.0, 1.0), (1, 0, 0, 1), (0, -181, 1, 1), (0, 0, 1, 181), (.nan, 0, 1, 1), (0, 0, .infinity, 1)] {
            XCTAssertThrowsError(try client.bbox(south: south, west: west, north: north, east: east)) {
                XCTAssertEqual(($0 as? OpenTideConstantsError)?.code, "invalid_argument")
            }
        }
        XCTAssertThrowsError(try client.release.bbox(south: 0, west: 0, north: 1, east: 1, limit: 0)) {
            XCTAssertEqual(($0 as? OpenTideConstantsError)?.code, "invalid_argument")
        }
    }

    func testLimitedBboxMaterializesOnlySelectedStation() async throws {
        for useClient in [true, false] {
            let cache = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
            defer { try? FileManager.default.removeItem(at: cache) }
            let client = try await OpenTideConstants.open(file: fixture.path, cacheDir: cache.path, mode: .stream)
            defer { client.close() }
            let release = client.release
            XCTAssertTrue(release.lru.isEmpty)
            let selected = useClient
                ? try client.bbox(south: 37.665, west: -122.4659, north: 37.8063, east: -122.3, limit: 1, type: "subordinate")
                : try release.bbox(south: 37.665, west: -122.4659, north: 37.8063, east: -122.3, limit: 1, type: "subordinate")
            XCTAssertEqual(selected.map(\.stationId), ["OTC-T-0003"])
            XCTAssertEqual(release.lru.keys.sorted(), ["OTC-T-0003"])
        }
    }
}
