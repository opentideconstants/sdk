import Foundation

internal func requireHistoricalOffset(_ offsets: JSONValue, release: Release, reference: ConstantSet, betterPath: Bool, explicit: Bool) throws {
    try Reader.historical(offsets)
    guard let ownId = offsets["licence_id"].string, let ownLicence = release.licById[ownId], ownLicence.licenceId == ownId else {
        throw OpenTideConstantsError.invalidRelease("historical own licence does not resolve")
    }
    let selection = explicit ? "explicit" : "auto"
    func refuse() -> OpenTideConstantsError {
        .noConstants("historical offsets are ineligible", ["policy": .string(release.historicalOffsetsPolicy), "selection": .string(selection)])
    }
    if release.historicalOffsetsPolicy == "exclude" || (!explicit && betterPath) { throw refuse() }
    let binding = offsets["provenance"]["reference_binding"]
    guard reference.setId.hasPrefix((offsets["reference_station_id"].string ?? "") + "/"),
          reference.source == "noaa", reference.sourceRecordId == binding["noaa_id"].string,
          reference.quantity == .waterLevel, reference.qcStatus == .ok, reference.fallback == nil else { throw refuse() }
    guard let referenceLicence = release.licById[reference.licence.licenceId], referenceLicence == reference.licence else {
        throw OpenTideConstantsError.invalidRelease("historical reference licence does not resolve")
    }
    if release.commercialOnly && (!ownLicence.commercialUse || !referenceLicence.commercialUse) { throw refuse() }
    let datum = reference.raw["datum"]
    guard reference.convention.v0Model == "schureman_tcd", reference.convention.nodalHandling == .fUAtPrediction,
          datum["chart_datum"].string == "mllw", datum["msl_offset_m"].number != nil,
          datum["named"]["mllw"].number == 0.0, datum["basis"]["mllw"]["kind"].string == "published" else { throw refuse() }
}
