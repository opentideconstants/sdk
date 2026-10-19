import Foundation

internal struct PredictionContext {
    let station: Station
    let constants: ConstantSet
    let table: AstroTable
    var method: PredictionMethod = .harmonic
    var reference: Station?
    var referenceBin: Int64?
    var binNumber: Int64?
    var offsets: JSONValue = .null
    var total: HarmonicSum?
    var minor: HarmonicSum?
    var currentBin: JSONValue = .null
    var sigma: Double = 1.0
    var datumName: String?
    var datumKind: String?
    var datumUncertainty: Double?
    var omitted: [CurrentEventType]?
}

internal enum Predict {
    static func window(_ start: Date, _ stop: Date, stepS: Int64? = nil) throws -> (Double, Double) {
        let start = try predictionInstant(start), stop = try predictionInstant(stop)
        guard start <= stop else { throw OpenTideConstantsError.invalidArgument("start must not be after stop") }
        if let stepS, stepS <= 0 { throw OpenTideConstantsError.invalidArgument("step_s must be a positive integer") }
        return (start, stop)
    }
    static func options(_ binNumber: Int64?) throws {
        if let binNumber, !(1...9007199254740991).contains(binNumber) {
            throw OpenTideConstantsError.invalidArgument("bin_number must be an integer from 1 to 2^53 - 1")
        }
    }
    static func optionExclusion(setId: String?, offsetId: String?) throws {
        if offsetId != nil && setId != nil { throw OpenTideConstantsError.invalidArgument("set_id and offset_id are mutually exclusive") }
    }
    static func chosen(_ release: Release, station: Station, setId: String?) throws -> ConstantSet? {
        guard let setId else { return station.recommendedSet }
        guard let constants = station.constantSet(setId: setId) else {
            throw OpenTideConstantsError.invalidArgument("set_id \(setId) is not a set of \(station.stationId)")
        }
        if release.commercialOnly && !constants.licence.commercialUse {
            throw OpenTideConstantsError.invalidArgument("commercial_only refuses set_id \(setId)")
        }
        return constants
    }
    static func table(_ release: Release, constants: ConstantSet) throws -> AstroTable {
        let convention = constants.convention
        guard convention.v0Model == "schureman_tcd", convention.nodalHandling == .fUAtPrediction else {
            throw OpenTideConstantsError.unsupportedConvention("unsupported convention \(convention.conventionId)")
        }
        let id = convention.raw["astro_table_id"].string ?? ""
        guard let table = try release.astroTable(id: id) else {
            throw OpenTideConstantsError.noAstroTable("release \(release.datestamp) has no astro table \"\(id)\" for convention \"\(convention.conventionId)\". Format 1.0 requires astro_tables when a convention uses f_u_at_prediction (since the schema revision of site PR #45); this file was written before that revision or is invalid.")
        }
        return table
    }
    static func historicalReferenceTable(_ release: Release, constants: ConstantSet) throws -> AstroTable {
        let selected = try table(release, constants: constants)
        guard selected.raw["v0_model"].string == constants.convention.v0Model,
              constants.convention.tablesSha256 == nil || selected.raw["tables_sha256"].string == constants.convention.tablesSha256 else {
            throw OpenTideConstantsError.unsupportedConvention("unsupported convention \(constants.convention.conventionId)")
        }
        for constituent in constants.raw["constituents"].array {
            _ = try selected.row(constituent["name"].string ?? "")
        }
        return selected
    }
    static func unavailable(_ missing: String?) -> OpenTideConstantsError {
        .datumUnavailable("datum is missing \(missing ?? "None")", ["missing": missing.map(JSONValue.string) ?? .null])
    }
    static func datum(_ raw: JSONValue, requested: String?, context: inout PredictionContext, published: Bool = false) throws -> Double {
        let requested = requested ?? "mean_level"
        if requested == "mean_level" && !published {
            context.datumName = requested
            return 0.0
        }
        let msl: Double
        if raw["zero"].string == "harmonic_mean" && !published {
            msl = 0.0
        } else {
            guard let offset = raw["msl_offset_m"].number else { throw unavailable("msl_offset_m") }
            msl = offset
        }
        if requested == "zero" && !published {
            context.datumName = raw["zero_name"].string ?? raw["zero"].string ?? "unknown"
            return msl
        }
        let key = requested == "chart" ? raw["chart_datum"].string : requested
        if requested == "chart" && key == nil { throw unavailable("chart_datum") }
        guard let key, let named = raw["named"][key].number else { throw unavailable(key) }
        let basis = raw["basis"][key]
        if published && basis["kind"].string != "published" { throw unavailable("published chart datum") }
        context.datumName = key
        context.datumKind = basis["kind"].string
        context.datumUncertainty = basis["uncertainty_m"].number
        return msl - named
    }
    static func subordinateDatum(_ offsets: JSONValue, requested: String?, context: inout PredictionContext) throws -> Double {
        let datum = offsets["datum"], chart = datum["chart_datum"].string
        let key = requested == nil || requested == "chart" ? chart : requested
        let term: Double
        if requested == nil || requested == "chart" { term = 0.0 }
        else if let key, let named = datum["named"][key].number {
            term = (chart.flatMap { datum["named"][$0].number } ?? 0.0) - named
        } else { throw unavailable(requested) }
        let basis = key.map { datum["basis"][$0] } ?? .null
        context.datumName = key
        context.datumKind = basis["kind"].string
        context.datumUncertainty = basis["uncertainty_m"].number
        return term
    }
    static func reference(_ release: Release, offsets: JSONValue, quantity: Quantity, binNumber: Int64? = nil) throws -> (Station, ConstantSet) {
        let id = offsets["reference_station_id"].string ?? ""
        guard let station = try release.station(stationId: id), let constants = station.constantSets(includeNoConstants: true).first(where: { cs in
            cs.quantity == quantity && [.ok, .flagged].contains(cs.qcStatus) && (quantity == .waterLevel ? cs.source == "noaa" : cs.raw["current_bins"].array.contains { $0["bin"].integer == binNumber })
        }) else { throw OpenTideConstantsError.referenceUnavailable("reference \(id) has no usable set", ["reference_station_id": .string(id)]) }
        if release.commercialOnly {
            for licenceId in [offsets["licence_id"].string, constants.licence.licenceId] {
                if let licenceId, release.licById[licenceId]?.commercialUse != true {
                    throw OpenTideConstantsError.referenceUnavailable("commercial_only refuses reference licence \(licenceId)", ["reference_station_id": .string(id)])
                }
            }
        }
        return (station, constants)
    }
    static func bin(_ station: Station, bins: [JSONValue], requested: Int64?) throws -> JSONValue {
        let chosen = requested ?? station.raw["default_current_bin"].integer ?? bins.compactMap { $0["bin"].integer }.min()
        guard let row = bins.first(where: { $0["bin"].integer == chosen }) else {
            throw OpenTideConstantsError.binNotFound("bin_number \(chosen.map(String.init) ?? "None") is not available")
        }
        return row
    }
    static func current(_ context: inout PredictionContext, row: JSONValue) throws {
        context.currentBin = row
        let azimuth = row["azimuth_deg"].number ?? 0.0, flood = row["mean_flood_dir_deg"].number
        context.sigma = flood == nil || cos((azimuth - flood!) * predictionRAD) >= 0 ? 1.0 : -1.0
        context.total = try HarmonicSum(context.table, row["constituents"].array, amplitude: "major_amplitude_ms", phase: "major_phase_deg", mean: row["mean_major_ms"].number ?? 0.0)
        context.minor = try HarmonicSum(context.table, row["constituents"].array, amplitude: "minor_amplitude_ms", phase: "minor_phase_deg", mean: row["mean_minor_ms"].number ?? 0.0)
    }
    static func context(_ release: Release, supplied: Station, quantity: Quantity, setId: String?, datum: String? = nil, binNumber: Int64? = nil, series: Bool = false, offsetId: String? = nil) throws -> PredictionContext {
        try release.checkOpen()
        try release.own(supplied)
        let station = try release.requireStation(stationId: supplied.stationId)
        try options(binNumber)
        try optionExclusion(setId: setId, offsetId: offsetId)
        let selected = try chosen(release, station: station, setId: setId)
        var usable = selected.map { [.ok, .flagged].contains($0.qcStatus) } ?? false
        let tideOffsets = station.raw["subordinate_offsets"], currentOffsets = station.raw["current_offsets"].array
        let historical = tideOffsets["offset_id"].string != nil
        if let offsetId {
            guard historical, tideOffsets["offset_id"].string == offsetId else {
                throw OpenTideConstantsError.invalidArgument("offset_id \(offsetId) is not a profile of \(station.stationId)")
            }
            usable = false
        }
        let blockedBetter = historical && offsetId == nil && release.betterHistoricalPath(release.byId[station.stationId]!)
        if setId == nil && !usable && station.type == .subordinate && ((!tideOffsets.isNull && !blockedBetter) || !currentOffsets.isEmpty) {
            if !tideOffsets.isNull {
                guard quantity == .waterLevel else { throw OpenTideConstantsError.quantityMismatch("tide offsets need water_level") }
                let kind = tideOffsets["height_adjusted_type"].string
                guard kind == "R" || kind == "A" else { throw OpenTideConstantsError.invalidArgument("height_adjusted_type \(kind ?? "None") is not R or A") }
                if historical && release.historicalOffsetsPolicy == "exclude" {
                    throw OpenTideConstantsError.historicalOffsetsExcluded("historical_offsets_policy=exclude refuses historical prediction")
                }
                let (reference, constants) = try reference(release, offsets: tideOffsets, quantity: quantity)
                if historical { try requireHistoricalOffset(tideOffsets, release: release, reference: constants, betterPath: blockedBetter, explicit: offsetId != nil) }
                let table = try historical
                    ? historicalReferenceTable(release, constants: constants)
                    : table(release, constants: constants)
                var context = PredictionContext(station: station, constants: constants, table: table, reference: reference, offsets: tideOffsets)
                if !historical { _ = try HarmonicSum(table, constants.raw["constituents"].array) }
                var referenceContext = PredictionContext(station: reference, constants: constants, table: table)
                let referenceTerm = try self.datum(constants.raw["datum"], requested: "chart", context: &referenceContext, published: true)
                let subordinateTerm = try subordinateDatum(tideOffsets, requested: datum, context: &context)
                let highTime = tideOffsets["time_offset_high_min"].number ?? 0.0, lowTime = tideOffsets["time_offset_low_min"].number ?? 0.0
                let identity = kind == "R" ? 1.0 : 0.0
                let highHeight = tideOffsets["height_offset_high"].number ?? identity, lowHeight = tideOffsets["height_offset_low"].number ?? identity
                if kind == "R" && (highHeight <= 0 || lowHeight <= 0) { throw OpenTideConstantsError.invalidArgument("height_offset ratio must be positive") }
                if highTime == lowTime && highHeight == lowHeight {
                    context.method = .foldedOffsets
                    let multiplier = kind == "R" ? highHeight : 1.0, add = kind == "A" ? highHeight : 0.0
                    context.total = try HarmonicSum(table, constants.raw["constituents"].array, mean: multiplier * referenceTerm + add + subordinateTerm, multiplier: multiplier, shiftHours: highTime / 60.0)
                } else {
                    context.method = .offsets
                    context.total = try HarmonicSum(table, constants.raw["constituents"].array, mean: referenceTerm)
                    var offsets = tideOffsets.object
                    offsets["_subterm"] = .number(subordinateTerm)
                    context.offsets = .object(offsets)
                    if series { throw OpenTideConstantsError.extremesOnly("high and low water offsets differ, so the station has no exact curve") }
                }
                return context
            }
            guard quantity == .current else { throw OpenTideConstantsError.quantityMismatch("current offsets need current") }
            let entry = try bin(station, bins: currentOffsets, requested: binNumber)
            let (reference, constants) = try reference(release, offsets: entry, quantity: quantity, binNumber: entry["reference_bin"].integer)
            let table = try table(release, constants: constants)
            var context = PredictionContext(station: station, constants: constants, table: table, method: .offsets, reference: reference, referenceBin: entry["reference_bin"].integer, binNumber: entry["bin"].integer, offsets: entry)
            let row = try bin(reference, bins: constants.raw["current_bins"].array, requested: context.referenceBin)
            try current(&context, row: row)
            if series { throw OpenTideConstantsError.extremesOnly("subordinate currents provide events only") }
            return context
        }
        guard usable, let constants = selected else {
            throw OpenTideConstantsError.noConstants("no usable constants: \(selected?.qcStatus.rawValue ?? "None")" + (release.commercialOnly ? " (commercial_only)" : ""))
        }
        guard constants.quantity == quantity else { throw OpenTideConstantsError.quantityMismatch("\(quantity.rawValue) requires that quantity of constants") }
        let table = try table(release, constants: constants)
        var context = PredictionContext(station: station, constants: constants, table: table)
        if quantity == .waterLevel {
            context.total = try HarmonicSum(table, constants.raw["constituents"].array)
            context.total!.mean = try self.datum(constants.raw["datum"], requested: datum, context: &context)
        } else {
            let row = try bin(station, bins: constants.raw["current_bins"].array, requested: binNumber)
            context.binNumber = row["bin"].integer
            try current(&context, row: row)
        }
        return context
    }
}

internal extension Predict {
    static func extremes(_ release: Release, context: PredictionContext, start: Double, stop: Double, datum: String?) throws -> ExtremeList {
        var candidates: [HarmonicEvent]
        if context.method == .offsets && start != stop {
            let offsets = context.offsets
            let margin = max(120.0, max(abs(offsets["time_offset_high_min"].number ?? 0.0), abs(offsets["time_offset_low_min"].number ?? 0.0)) + 60.0) * 60.0
            candidates = try harmonicEvents(context.total!, start: start - margin, stop: stop + margin)
            candidates = candidates.map { candidate in
                let time = candidate.time + (offsets["time_offset_" + candidate.kind + "_min"].number ?? 0.0) * 60.0
                let height = offsets["height_offset_" + candidate.kind].number
                let value = offsets["height_adjusted_type"].string == "R" ? candidate.value * (height ?? 1.0) : candidate.value + (height ?? 0.0)
                return HarmonicEvent(time: time, kind: candidate.kind, value: value + offsets["_subterm"].number!)
            }.enumerated().sorted { a, b in
                let first = floor(a.element.time + 0.5), second = floor(b.element.time + 0.5)
                return first == second ? a.offset < b.offset : first < second
            }.map(\.element)
        } else { candidates = try harmonicEvents(context.total!, start: start, stop: stop) }
        let items = candidates.filter { start <= floor($0.time + 0.5) && floor($0.time + 0.5) < stop }.map {
            Extreme(time: Date(timeIntervalSince1970: floor($0.time + 0.5)), type: ExtremeType(rawValue: $0.kind)!, heightM: $0.value)
        }
        return extremeList(release, context: context, items: items, datum: datum)
    }
    struct CurrentCandidate {
        let time: Double
        let kind: String
        let value: Double
        let direction: Double?
    }
    static func currentCandidates(_ context: PredictionContext, start: Double, stop: Double) throws -> [CurrentCandidate] {
        try currentCandidates(context, start: start, stop: stop, events: harmonicEvents)
    }
    static func unroundedCurrentCandidates(_ context: PredictionContext, start: Double, stop: Double) throws -> [CurrentCandidate] {
        try currentCandidates(context, start: start, stop: stop, events: unroundedHarmonicEvents)
    }
    private static func currentCandidates(_ context: PredictionContext, start: Double, stop: Double, events: (HarmonicSum, Double, Double, Bool) throws -> [HarmonicEvent]) throws -> [CurrentCandidate] {
        let row = context.currentBin
        let total = try HarmonicSum(context.table, row["constituents"].array, amplitude: "major_amplitude_ms", phase: "major_phase_deg", mean: context.sigma * (row["mean_major_ms"].number ?? 0.0), multiplier: context.sigma)
        var candidates: [CurrentCandidate] = []
        for event in try events(total, start, stop, false) {
            if event.kind == "high" && event.value > 0 {
                candidates.append(CurrentCandidate(time: event.time, kind: "max_flood", value: event.value, direction: row["mean_flood_dir_deg"].number))
            } else if event.kind == "low" && event.value < 0 {
                candidates.append(CurrentCandidate(time: event.time, kind: "max_ebb", value: event.value, direction: row["mean_ebb_dir_deg"].number))
            }
        }
        for event in try events(total, start, stop, true) {
            candidates.append(CurrentCandidate(time: event.time, kind: event.kind, value: 0.0, direction: nil))
        }
        return candidates.enumerated().sorted { a, b in
            a.element.time == b.element.time ? a.offset < b.offset : a.element.time < b.element.time
        }.map(\.element)
    }
    static func currents(_ release: Release, context: PredictionContext, start: Double, stop: Double, stepS: Int64) throws -> CurrentSeries {
        let theta = (context.currentBin["azimuth_deg"].number ?? 0.0) * predictionRAD
        var items: [CurrentPoint] = []
        var time = start
        while time < stop {
            let major = try context.total!.value(time), minor = try context.minor!.value(time)
            let east = major * sin(theta) + minor * sin(theta + Double.pi / 2.0)
            let north = major * cos(theta) + minor * cos(theta + Double.pi / 2.0)
            let speed = hypot(east, north)
            let direction = speed < 1e-9 ? nil : reducedAngle(atan2(east, north) / predictionRAD)
            items.append(CurrentPoint(time: Date(timeIntervalSince1970: time), velocityMajorMs: context.sigma * major, velocityMinorMs: context.sigma * minor, speedMs: speed, directionDeg: direction))
            time += Double(stepS)
        }
        return currentSeries(release, context: context, items: items)
    }
    static func currentEvents(_ release: Release, context original: PredictionContext, start: Double, stop: Double) throws -> CurrentEventList {
        var context = original
        let candidates: [CurrentCandidate]
        if context.method == .offsets {
            let entry = context.offsets
            let kinds = ["max_flood", "max_ebb", "slack_before_flood", "slack_before_ebb"]
            let kept = kinds.filter { kind in
                entry["time_adj_" + kind + "_min"].number != nil && (kind.hasPrefix("slack") || entry[kind == "max_flood" ? "flood_amp_ratio" : "ebb_amp_ratio"].number != nil)
            }
            context.omitted = kinds.filter { !kept.contains($0) }.map { CurrentEventType(rawValue: $0)! }
            let margin = max(120.0, (kept.map { abs(entry["time_adj_" + $0 + "_min"].number!) }.max() ?? 0.0) + 60.0) * 60.0
            let original = start == stop ? [] : try currentCandidates(context, start: start - margin, stop: stop + margin)
            var shifted: [CurrentCandidate] = []
            for candidate in original where kept.contains(candidate.kind) {
                let time = candidate.time + entry["time_adj_" + candidate.kind + "_min"].number! * 60.0
                var value = candidate.value, direction = candidate.direction
                if candidate.kind == "max_flood" || candidate.kind == "max_ebb" {
                    value *= entry[candidate.kind == "max_flood" ? "flood_amp_ratio" : "ebb_amp_ratio"].number!
                    direction = entry[candidate.kind == "max_flood" ? "mean_flood_dir_deg" : "mean_ebb_dir_deg"].number
                }
                shifted.append(CurrentCandidate(time: time, kind: candidate.kind, value: value, direction: direction))
            }
            candidates = shifted.enumerated().sorted { a, b in
                let first = floor(a.element.time + 0.5), second = floor(b.element.time + 0.5)
                return first == second ? a.offset < b.offset : first < second
            }.map(\.element)
        } else { candidates = try currentCandidates(context, start: start, stop: stop) }
        let items = candidates.filter { start <= floor($0.time + 0.5) && floor($0.time + 0.5) < stop }.map {
            CurrentEvent(time: Date(timeIntervalSince1970: floor($0.time + 0.5)), type: CurrentEventType(rawValue: $0.kind)!, velocityMs: $0.value, directionDeg: $0.direction)
        }
        return currentEventList(release, context: context, items: items)
    }
    static func datumInfo(setId: String?, raw: JSONValue) -> DatumInfo {
        let named = raw["named"].object, basis = raw["basis"]
        let chart = raw["chart_datum"].string.flatMap { named[$0]?.number }
        let levels = named.keys.sorted().map { key in
            let b = basis[key], control = b["control"], value = named[key]!.number!
            return DatumLevel(key: key, valueM: value, aboveChartM: chart.map { value - $0 }, kind: b["kind"].string, method: b["method"].string, sourceName: b["source_name"].string, epoch: b["epoch"], dataSpan: b["data_span"], controlStationId: control["station_id"].string, controlSetId: control["set_id"].string, controlSourceId: control["source_id"].string, uncertaintyM: b["uncertainty_m"].number, uncertaintyBasis: b["uncertainty_basis"].string, flags: b["flags"].array.compactMap(\.string), fallback: b["fallback"].isNull ? nil : b["fallback"])
        }
        return DatumInfo(setId: setId, zero: raw["zero"].string, zeroName: raw["zero_name"].string, chartDatum: raw["chart_datum"].string, mslOffsetM: raw["msl_offset_m"].number, levels: levels)
    }
    static func ranges(_ info: DatumInfo?) -> Ranges {
        let levels = Dictionary(uniqueKeysWithValues: (info?.levels ?? []).compactMap { level in level.key.map { ($0, level) } })
        func difference(_ first: String, _ second: String) -> Double? {
            guard let high = levels[first], let low = levels[second], high.kind != nil, high.kind == low.kind, high.epoch == low.epoch else { return nil }
            return high.valueM - low.valueM
        }
        return Ranges(mn: difference("mhw", "mlw"), gt: difference("mhhw", "mllw"), dhq: difference("mhhw", "mhw"), dlq: difference("mlw", "mllw"))
    }
}

internal extension Predict {
    static func heightSeries(_ release: Release, context: PredictionContext, items: [HeightPoint], datum: String?) -> HeightSeries {
        let offsets = context.offsets
        let historical = offsets["offset_id"].string != nil
        return HeightSeries(items: items, stationId: context.station.stationId, timezone: context.station.timezone, method: context.method, setId: historical ? nil : context.constants.setId, conventionId: context.constants.convention.conventionId, astroTableId: context.table.raw["astro_table_id"].string, referenceStationId: context.reference?.stationId, referenceBin: context.referenceBin, datum: datum, datumName: context.datumName, datumKind: context.datumKind, datumUncertaintyM: context.datumUncertainty, release: release.datestamp, algorithm: "otc-predict-1", offsetId: offsets["offset_id"].string, offsetSource: offsets["source"].string, offsetSourceVersion: offsets["source_version"].string, historicalOffsets: historical, currentValidity: offsets["vintage"]["current_validity"].string, currentAccuracy: offsets["vintage"]["current_accuracy"].string, referenceSetId: historical ? context.constants.setId : nil, referenceSourceVersion: historical ? context.constants.sourceVersion : nil, reference2020Equivalence: offsets["vintage"]["reference_2020_equivalence"].string, sourceNote: historical ? "OTC historical-offset calculation using NOAA2020 parameters; retired NOAA profile; current validity unestablished; current accuracy unverified." : nil)
    }
    static func extremeList(_ release: Release, context: PredictionContext, items: [Extreme], datum: String?) -> ExtremeList {
        let offsets = context.offsets
        let historical = offsets["offset_id"].string != nil
        return ExtremeList(items: items, stationId: context.station.stationId, timezone: context.station.timezone, method: context.method, setId: historical ? nil : context.constants.setId, conventionId: context.constants.convention.conventionId, astroTableId: context.table.raw["astro_table_id"].string, referenceStationId: context.reference?.stationId, referenceBin: context.referenceBin, datum: datum, datumName: context.datumName, datumKind: context.datumKind, datumUncertaintyM: context.datumUncertainty, release: release.datestamp, algorithm: "otc-predict-1", offsetId: offsets["offset_id"].string, offsetSource: offsets["source"].string, offsetSourceVersion: offsets["source_version"].string, historicalOffsets: historical, currentValidity: offsets["vintage"]["current_validity"].string, currentAccuracy: offsets["vintage"]["current_accuracy"].string, referenceSetId: historical ? context.constants.setId : nil, referenceSourceVersion: historical ? context.constants.sourceVersion : nil, reference2020Equivalence: offsets["vintage"]["reference_2020_equivalence"].string, sourceNote: historical ? "OTC historical-offset calculation using NOAA2020 parameters; retired NOAA profile; current validity unestablished; current accuracy unverified." : nil)
    }
    static func currentSeries(_ release: Release, context: PredictionContext, items: [CurrentPoint]) -> CurrentSeries {
        return CurrentSeries(items: items, stationId: context.station.stationId, timezone: context.station.timezone, method: context.method, setId: context.constants.setId, conventionId: context.constants.convention.conventionId, astroTableId: context.table.raw["astro_table_id"].string, referenceStationId: context.reference?.stationId, referenceBin: context.referenceBin, datum: nil, datumName: context.datumName, datumKind: context.datumKind, datumUncertaintyM: context.datumUncertainty, release: release.datestamp, algorithm: "otc-predict-1", binNumber: context.binNumber)
    }
    static func currentEventList(_ release: Release, context: PredictionContext, items: [CurrentEvent]) -> CurrentEventList {
        return CurrentEventList(items: items, stationId: context.station.stationId, timezone: context.station.timezone, method: context.method, setId: context.constants.setId, conventionId: context.constants.convention.conventionId, astroTableId: context.table.raw["astro_table_id"].string, referenceStationId: context.reference?.stationId, referenceBin: context.referenceBin, datum: nil, datumName: context.datumName, datumKind: context.datumKind, datumUncertaintyM: context.datumUncertainty, release: release.datestamp, algorithm: "otc-predict-1", binNumber: context.binNumber, omittedEventTypes: context.omitted)
    }
}
