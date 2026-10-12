import Foundation
import OpenTideConstants
// Foundation consumer only. Final shared-manifest and prediction registration belongs to S1/G0.
@main struct CheckAPI {
    static func main()async throws {
        guard let path=ProcessInfo.processInfo.environment["OTC_CORE_NATIVE_JSON"] else { throw OpenTideConstantsError.invalidArgument("actual artifact environment required") }
        let c=try await OpenTideConstants.open(file:path)
        let counts=try c.release.stationCount
        let found=try c.search(name:"Otaru",includeFallback:true)
        guard !found.isEmpty,let first=found.first else { throw OpenTideConstantsError.invalidRelease("actual Otaru absent") }
        let source:SourceRecord?=first.sourceRecords.first
        let licence:Licence?=source?.licence
        let _:JSONValue?=source?.originalHarmonics
        let _:Fallback?=first.recommendedSet?.fallback
        let _:Convention?=first.recommendedSet?.convention
        let _:Provenance?=first.recommendedSet?.provenance
        let _:HistoricalOffsetVintage?=first.subordinateOffsets?.vintage
        print("FOUNDATION_CONSUMER station_count=\(counts) otaru_sources=\(first.sourceRecords.count) resolved_licence=\(licence != nil)")
        c.close()
        do { _=try c.station(stationId:first.stationId);throw OpenTideConstantsError.invalidRelease("closed release accepted query") } catch let e as OpenTideConstantsError { guard e.code=="io" else { throw e } }
        print("FOUNDATION_ONLY: final 99-name/API/vector activation pending S1/G0")
    }
}
