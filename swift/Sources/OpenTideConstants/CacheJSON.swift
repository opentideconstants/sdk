import Foundation

// This binding is for generated cache documents. Codable and retained source
// bodies keep their existing representation.
internal func encode_cache_json(_ cache_document: JSONValue) throws -> Data {
    Data(try cacheJSONText(cache_document).utf8)
}

private func cacheJSONText(_ value: JSONValue) throws -> String {
    switch value {
    case .null: return "null"
    case .bool(let value): return value ? "true" : "false"
    case .integer(let value): return String(value)
    case .number(let value): return try cacheJSONNumber(value)
    case .string(let value): return cacheJSONString(value)
    case .array(let values): return "[" + (try values.map(cacheJSONText)).joined(separator: ",") + "]"
    case .object(let values):
        let keys = values.keys.sorted {
            $0.unicodeScalars.lexicographicallyPrecedes($1.unicodeScalars) { $0.value < $1.value }
        }
        return "{" + (try keys.map { key in
            cacheJSONString(key) + ":" + (try cacheJSONText(values[key]!))
        }).joined(separator: ",") + "}"
    }
}

private func cacheJSONString(_ value: String) -> String {
    var result = "\""
    for scalar in value.unicodeScalars {
        switch scalar.value {
        case 0..<32:
            let hex = String(scalar.value, radix: 16)
            result += "\\u" + String(repeating: "0", count: 4 - hex.count) + hex
        case 34: result += "\\\""
        case 92: result += "\\\\"
        default: result.unicodeScalars.append(scalar)
        }
    }
    return result + "\""
}

private func cacheJSONNumber(_ value: Double) throws -> String {
    guard value.isFinite else { throw OpenTideConstantsError.invalidRelease("non-finite cache JSON number") }
    if value == 0 { return "0" }
    // Swift's native description supplies the closest shortest round-trip
    // digits. Only the approved notation and exponent spelling change here.
    let absolute = abs(value)
    let parts = String(absolute).lowercased().split(separator: "e")
    let mantissa = parts[0].split(separator: ".")
    var digits = mantissa.joined()
    var point = mantissa[0].count + (parts.count == 2 ? Int(parts[1])! : 0)
    while digits.first == "0" { digits.removeFirst(); point -= 1 }
    while digits.last == "0" { digits.removeLast() }
    let text: String
    if absolute >= 1e-6 && absolute < 1e21 {
        if point <= 0 { text = "0." + String(repeating: "0", count: -point) + digits }
        else if point >= digits.count { text = digits + String(repeating: "0", count: point - digits.count) }
        else {
            let split = digits.index(digits.startIndex, offsetBy: point)
            text = digits[..<split] + "." + digits[split...]
        }
    } else {
        text = String(digits.prefix(1)) + (digits.count > 1 ? "." + digits.dropFirst() : "") + "e" + String(point - 1)
    }
    return value < 0 ? "-" + text : text
}
