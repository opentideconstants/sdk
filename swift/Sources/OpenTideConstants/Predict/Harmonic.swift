import Foundation

internal let predictionRAD = Double.pi / 180.0
internal let predictionEpsilon = pow(2.0, -52.0)

internal final class HarmonicSum {
    let table: AstroTable
    var mean: Double
    struct Term {
        let row: JSONValue
        let speed: Double
        let amplitude: Double
        let phase: Double
    }
    struct YearTerm {
        let speed: Double
        let amplitude: Double
        let argument: Double
        let omega: Double
    }
    private let terms: [Term]
    private var years: [Int64: (Double, [YearTerm])] = [:]

    init(_ table: AstroTable, _ constituents: [JSONValue], amplitude: String = "amplitude_m", phase: String = "phase_deg", mean: Double = 0.0, multiplier: Double = 1.0, shiftHours: Double = 0.0) throws {
        self.table = table
        self.mean = mean
        var terms: [Term] = []
        for constituent in constituents {
            let row = try table.row(constituent["name"].string ?? "")
            let speed = row["speed_deg_per_hour"].number!
            terms.append(Term(row: row, speed: speed, amplitude: multiplier * (constituent[amplitude].number ?? 0.0), phase: reducedAngle((constituent[phase].number ?? 0.0) + speed * shiftHours)))
        }
        self.terms = terms
    }
    internal func yearData(_ year: Int64) throws -> (Double, [YearTerm]) {
        if let data = years[year] { return data }
        let index = try table.index(year)
        let origin = yearStart(year)
        let data = (origin, terms.map { term in
            YearTerm(speed: term.speed, amplitude: term.row["f"].array[index].number! * term.amplitude, argument: term.row["v0u_deg"].array[index].number! - term.phase, omega: term.speed * predictionRAD)
        })
        years[year] = data
        return data
    }
    func value(_ seconds: Double, year: Int64? = nil, derivative: Bool = false) throws -> Double {
        let (origin, terms) = try yearData(year ?? utcYear(seconds))
        let delta = (seconds - origin) / 3600.0
        var value = 0.0
        for term in terms {
            let phase = reducedAngle(term.speed * delta + term.argument) * predictionRAD
            value += derivative ? -term.amplitude * term.omega * sin(phase) : term.amplitude * cos(phase)
        }
        return derivative ? value : value + mean
    }
    func bound(_ year: Int64, derivative: Bool) throws -> Double {
        var value = 0.0
        for term in try yearData(year).1 {
            value += abs(term.amplitude) * pow(term.omega, derivative ? 2.0 : 1.0)
        }
        return value
    }
    func error(_ year: Int64, a: Double, b: Double, derivative: Bool) throws -> Double {
        let (origin, terms) = try yearData(year)
        let deltaMax = max(abs(a - origin), abs(b - origin)) / 3600.0
        var value = 0.0
        for term in terms {
            value += abs(term.amplitude) * (derivative ? term.omega : 1.0) * (abs(term.omega * deltaMax) + 2.0 * Double.pi)
        }
        return 4.0 * predictionEpsilon * value
    }
}

internal struct HarmonicEvent: Equatable {
    var time: Double
    let kind: String
    var value: Double
}

internal func eventSurvivor(_ cluster: [HarmonicEvent], slack: Bool) -> HarmonicEvent? {
    if cluster.count % 2 == 0 { return nil }
    if slack { return cluster[2 * ((cluster.count - 1) / 4)] }
    let wanted = cluster[0].kind
    let candidates = cluster.filter { $0.kind == wanted }
    if wanted == "high" {
        return candidates.max { ($0.value, -$0.time) < ($1.value, -$1.time) }
    }
    return candidates.min { ($0.value, $0.time) < ($1.value, $1.time) }
}

internal func harmonicEvents(_ total: HarmonicSum, start: Double, stop: Double, slack: Bool = false) throws -> [HarmonicEvent] {
    try unroundedHarmonicEvents(total, start: start, stop: stop, slack: slack).filter { start <= floor($0.time + 0.5) && floor($0.time + 0.5) < stop }
}

internal func unroundedHarmonicEvents(_ total: HarmonicSum, start: Double, stop: Double, slack: Bool = false) throws -> [HarmonicEvent] {
    if start == stop { return [] }
    let first = floor(start / 360.0) * 360.0 - 3600.0
    let last = ceil((stop + 3600.0 - first) / 360.0) * 360.0 + first
    var point = first
    while point <= last {
        _ = try total.table.index(utcYear(point))
        point += 360.0
    }
    let derivative = !slack
    var roots: [HarmonicEvent] = []
    var left = first
    while left < last {
        let year = utcYear(left)
        let bound = try total.bound(year, derivative: derivative)
        func value(_ time: Double) throws -> Double { try total.value(time, year: year, derivative: derivative) }
        func subdivide(_ left: Double, _ right: Double, _ fa: Double, _ fb: Double, _ depth: Int) throws {
            var a = left, b = right
            let margin = try bound * ((b - a) / 3600.0) * (1.0 + 1e-9) + 2.0 * total.error(year, a: a, b: b, derivative: derivative) + 1e-12 * max(1.0, bound)
            if abs(fa) + abs(fb) > margin { return }
            if depth < 9 {
                let middle = (a + b) / 2.0
                let fm = try value(middle)
                try subdivide(a, middle, fa, fm, depth + 1)
                try subdivide(middle, b, fm, fb, depth + 1)
                return
            }
            let falling = fa > 0 && fb <= 0
            let rising = fa < 0 && fb >= 0
            if !(falling || rising) { return }
            while b - a > 0.01 {
                let middle = (a + b) / 2.0
                let fm = try value(middle)
                if (falling && fm > 0) || (rising && fm < 0) { a = middle } else { b = middle }
            }
            let root = (a + b) / 2.0
            let kind = slack ? (falling ? "slack_before_ebb" : "slack_before_flood") : (falling ? "high" : "low")
            roots.append(HarmonicEvent(time: root, kind: kind, value: slack ? 0.0 : try total.value(root, year: year)))
        }
        try subdivide(left, left + 360.0, value(left), value(left + 360.0), 0)
        left += 360.0
    }
    let firstYear = utcYear(first), lastYear = utcYear(last)
    if firstYear < lastYear {
        for year in (firstYear + 1)...lastYear {
            let boundary = yearStart(year)
            if !(first < boundary && boundary < last) { continue }
            let old = try total.value(boundary, year: year - 1, derivative: derivative)
            let new = try total.value(boundary, year: year, derivative: derivative)
            if old == 0 || new == 0 || (old > 0) == (new > 0) { continue }
            let left = roots.last { $0.time <= boundary }
            let right = roots.first { $0.time > boundary }
            if let left, let right, right.time - left.time < 3600.0 {
                let loser: HarmonicEvent
                if slack { loser = right }
                else { loser = eventSurvivor([left, right, left], slack: false) == left ? right : left }
                if let index = roots.firstIndex(of: loser) { roots.remove(at: index) }
            } else {
                let kind = slack ? (new > 0 ? "slack_before_flood" : "slack_before_ebb") : (old > 0 ? "high" : "low")
                roots.append(HarmonicEvent(time: boundary, kind: kind, value: slack ? 0.0 : try total.value(boundary, year: year)))
            }
            roots.sort { $0.time < $1.time }
        }
    }
    var kept: [HarmonicEvent] = [], cluster: [HarmonicEvent] = []
    for candidate in roots {
        if let previous = cluster.last, candidate.time - previous.time >= 1.0 {
            if let survivor = eventSurvivor(cluster, slack: slack) { kept.append(survivor) }
            cluster = []
        }
        cluster.append(candidate)
    }
    if !cluster.isEmpty, let survivor = eventSurvivor(cluster, slack: slack) { kept.append(survivor) }
    return kept
}
