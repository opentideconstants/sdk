import Foundation
import OpenTideConstants

// External linking checks only the supported public contract. Internal shape
// fixtures execute through @testable package tests; this function is not run.
internal func canonicalPublicConsumer(release: Release, station: Station,
    client: OpenTideConstants, series: HeightSeries) throws {
    let held: Release = client.release
    let stationID: String = station.stationId
    let raw: JSONValue = station.raw
    let sets: [ConstantSet] = station.constantSets(includeNoConstants: true)
    let stationLookup: Station? = try release.station(stationId: stationID)
    let stations: [Station] = try release.stations()
    let iterator: () throws -> Station? = try release.iterStations()
    let stats: Stats = try release.stats
    let localized: HeightSeries = try series.toLocal(tz: "UTC")
    let objectHeights: (Station, Date, Date) throws -> HeightSeries = {
        try release.heights(station: $0, start: $1, stop: $2)
    }
    let idHeights: (String, Date, Date) throws -> HeightSeries = {
        try release.heights(stationId: $0, start: $1, stop: $2)
    }
    let metadata: () async throws -> [ReleaseInfo] = { try await client.releases() }
    withExtendedLifetime((held, raw, sets, stationLookup, stations, iterator,
        stats, localized, objectHeights, idHeights, metadata)) {}
}
