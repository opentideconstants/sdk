import Foundation

public indirect enum JSONValue: Codable, Sendable, Equatable {
    case null, bool(Bool), integer(Int64), number(Double), string(String)
    case array([JSONValue]), object([String: JSONValue])
    public init(from decoder: any Decoder) throws {
        let c = try decoder.singleValueContainer()
        if c.decodeNil() { self = .null }
        else if let v = try? c.decode(Bool.self) { self = .bool(v) }
        else if let v = try? c.decode(Int64.self) { self = .integer(v) }
        else if let v = try? c.decode(Double.self) {
            guard v.isFinite else { throw OpenTideConstantsError.invalidRelease("non-finite JSON number") }
            self = .number(v)
        } else if let v = try? c.decode(String.self) { self = .string(v) }
        else if let v = try? c.decode([JSONValue].self) { self = .array(v) }
        else { self = .object(try c.decode([String: JSONValue].self)) }
    }
    public func encode(to encoder: any Encoder) throws {
        var c = encoder.singleValueContainer()
        switch self {
        case .null: try c.encodeNil()
        case .bool(let v): try c.encode(v)
        case .integer(let v): try c.encode(v)
        case .number(let v): try c.encode(v)
        case .string(let v): try c.encode(v)
        case .array(let v): try c.encode(v)
        case .object(let v): try c.encode(v)
        }
    }
    public subscript(key: String) -> JSONValue { object[key] ?? .null }
    public var object: [String: JSONValue] { if case .object(let v) = self { return v }; return [:] }
    public var array: [JSONValue] { if case .array(let v) = self { return v }; return [] }
    public var string: String? { if case .string(let v) = self { return v }; return nil }
    public var bool: Bool? { if case .bool(let v) = self { return v }; return nil }
    public var number: Double? { switch self { case .number(let v): return v; case .integer(let v): return Double(v); default: return nil } }
    public var integer: Int64? {
        if case .integer(let v) = self { return v }
        if case .number(let v) = self, v.rounded(.towardZero) == v, v >= Double(Int64.min), v < Double(Int64.max) { return Int64(v) }
        return nil
    }
    public var isNull: Bool { self == .null }
    internal static func parse(_ data: Data) throws -> JSONValue {
        var parser = JSONParser(bytes: Array(data))
        return try parser.parse()
    }
    internal func data() throws -> Data { try encode_cache_json(self) }
}

internal func parseTime(_ s: String?) throws -> Date? {
    guard let s else { return nil }
    let pattern = #"^([0-9]{4})-([0-9]{2})-([0-9]{2})[Tt ]([0-9]{2}):([0-9]{2}):([0-9]{2})(\.[0-9]+)?([Zz]|[+-][0-9]{2}:?[0-9]{2})?$"#
    let r = try NSRegularExpression(pattern: pattern)
    guard let m = r.firstMatch(in: s, range: NSRange(s.startIndex..., in: s)), m.range.length == s.utf16.count else { throw OpenTideConstantsError.invalidRelease("not ISO8601: \(s)") }
    func part(_ n: Int) -> String { guard let r = Range(m.range(at: n), in: s) else { return "" }; return String(s[r]) }
    let values = (1...6).map { Int(part($0))! }
    guard values[0] >= 1, values[3] < 24, values[4] < 60, values[5] < 60 else { throw OpenTideConstantsError.invalidRelease("invalid calendar time: \(s)") }
    var cal = Calendar(identifier: .gregorian); cal.timeZone = TimeZone(secondsFromGMT: 0)!
    let c = DateComponents(year: values[0], month: values[1], day: values[2], hour: values[3], minute: values[4], second: values[5])
    guard let date = cal.date(from: c), cal.dateComponents([.year,.month,.day,.hour,.minute,.second], from: date) == c else { throw OpenTideConstantsError.invalidRelease("invalid calendar: \(s)") }
    var offset = 0
    let zone = part(8)
    if zone.hasPrefix("+") || zone.hasPrefix("-") {
        let digits = zone.dropFirst().replacingOccurrences(of: ":", with: "")
        let h = Int(digits.prefix(2))!, m = Int(digits.suffix(2))!
        guard h < 24, m < 60 else { throw OpenTideConstantsError.invalidRelease("invalid offset") }
        offset = (h * 3600 + m * 60) * (zone.hasPrefix("-") ? -1 : 1)
    }
    let fraction = Double("0" + part(7)) ?? 0
    let instant = date.addingTimeInterval(fraction - Double(offset))
    // as in the other SDKs, an offset that moves the time out of years 1 to 9999 in UTC is not a valid time
    guard cal.component(.era, from: instant) == 1, cal.component(.year, from: instant) <= 9999 else { throw OpenTideConstantsError.invalidRelease("time out of range: \(s)") }
    return instant
}

// Native token parsing keeps temporary storage bounded to one JSONL record. The
// immutable value tree contains no Foundation collection or mutable-object escape.
private struct JSONParser {
    let bytes:[UInt8]
    var pos=0
    mutating func parse()throws->JSONValue { let result=try value(0);space();guard pos==bytes.count else { throw invalid() };return result }
    func invalid()->OpenTideConstantsError { .invalidRelease("invalid JSON at byte \(pos)") }
    mutating func space() { while pos<bytes.count && [UInt8(32),9,10,13].contains(bytes[pos]) { pos+=1 } }
    mutating func consume(_ byte:UInt8)->Bool { space();if pos<bytes.count && bytes[pos]==byte { pos+=1;return true };return false }
    mutating func literal(_ token:String,_ result:JSONValue)throws->JSONValue { let b=Array(token.utf8);guard pos+b.count<=bytes.count,Array(bytes[pos..<pos+b.count])==b else { throw invalid() };pos+=b.count;return result }
    mutating func value(_ depth:Int)throws->JSONValue {
        guard depth<=1000 else { throw invalid() };space();guard pos<bytes.count else { throw invalid() }
        switch bytes[pos] {
        case 34:return .string(try string())
        case 116:return try literal("true",.bool(true))
        case 102:return try literal("false",.bool(false))
        case 110:return try literal("null",.null)
        case 91:
            pos+=1;var result:[JSONValue]=[]
            if consume(93) { return .array(result) }
            repeat { result.append(try value(depth+1));if consume(93) { return .array(result) };guard consume(44) else { throw invalid() } } while true
        case 123:
            pos+=1;var result:[String:JSONValue]=[:]
            if consume(125) { return .object(result) }
            repeat { space();let k=try string();guard consume(58) else { throw invalid() };result[k]=try value(depth+1);if consume(125) { return .object(result) };guard consume(44) else { throw invalid() } } while true
        default:return try number()
        }
    }
    mutating func string()throws->String {
        guard pos<bytes.count,bytes[pos]==34 else { throw invalid() };pos+=1
        var start=pos,result=[UInt8]()
        while pos<bytes.count {
            let c=bytes[pos]
            if c==34 {
                result.append(contentsOf:bytes[start..<pos]);pos+=1
                guard let value=String(bytes:result,encoding:.utf8) else { throw invalid() };return value
            }
            if c<32 { throw invalid() }
            if c != 92 { pos+=1;continue }
            result.append(contentsOf:bytes[start..<pos]);pos+=1;guard pos<bytes.count else { throw invalid() }
            let escape=bytes[pos];pos+=1
            switch escape {
            case 34,47,92:result.append(escape)
            case 98:result.append(8)
            case 102:result.append(12)
            case 110:result.append(10)
            case 114:result.append(13)
            case 116:result.append(9)
            case 117:
                let first=try hex();var scalar=first
                if (0xD800...0xDBFF).contains(first) {
                    guard pos+2<=bytes.count,bytes[pos]==92,bytes[pos+1]==117 else { throw invalid() };pos+=2
                    let low=try hex();guard (0xDC00...0xDFFF).contains(low) else { throw invalid() };scalar=0x10000+(first-0xD800)*1024+(low-0xDC00)
                } else if (0xDC00...0xDFFF).contains(first) { throw invalid() }
                guard let unicode=UnicodeScalar(scalar) else { throw invalid() };result.append(contentsOf:String(unicode).utf8)
            default:throw invalid()
            }
            start=pos
        }
        throw invalid()
    }
    mutating func hex()throws->UInt32 {
        guard pos+4<=bytes.count else { throw invalid() };var result:UInt32=0
        for _ in 0..<4 { let c=bytes[pos];pos+=1;let n:UInt32
            switch c { case 48...57:n=UInt32(c-48);case 65...70:n=UInt32(c-55);case 97...102:n=UInt32(c-87);default:throw invalid() }
            result=result*16+n
        };return result
    }
    mutating func number()throws->JSONValue {
        let start=pos
        if pos<bytes.count,bytes[pos]==45 { pos+=1 }
        guard pos<bytes.count else { throw invalid() }
        if bytes[pos]==48 { pos+=1 } else {
            guard (49...57).contains(bytes[pos]) else { throw invalid() }
            while pos<bytes.count,(48...57).contains(bytes[pos]) { pos+=1 }
        }
        var fractional=false
        if pos<bytes.count,bytes[pos]==46 {
            fractional=true;pos+=1;let from=pos
            while pos<bytes.count,(48...57).contains(bytes[pos]) { pos+=1 };guard pos>from else { throw invalid() }
        }
        if pos<bytes.count,[UInt8(101),69].contains(bytes[pos]) {
            fractional=true;pos+=1;if pos<bytes.count,[UInt8(43),45].contains(bytes[pos]) { pos+=1 };let from=pos
            while pos<bytes.count,(48...57).contains(bytes[pos]) { pos+=1 };guard pos>from else { throw invalid() }
        }
        let text=String(decoding:bytes[start..<pos],as:UTF8.self)
        if !fractional,let n=Int64(text) { return .integer(n) }
        guard let n=Double(text),n.isFinite else { throw invalid() };return .number(n)
    }
}
