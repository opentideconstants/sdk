import Foundation
internal enum NameFold {
    private static let mapping: [UInt32: String] = {
        guard let url = Bundle.module.url(forResource: "name_fold", withExtension: "json"), let data = try? Data(contentsOf: url), let doc = try? JSONValue.parse(data) else { preconditionFailure("packaged fold table missing") }
        return Dictionary(uniqueKeysWithValues: doc["map"].object.compactMap { k,v in guard let n = UInt32(k, radix:16), let s = v.string else { return nil }; return (n,s) })
    }()
    static func fold(_ s: String) -> String {
        let result = s.unicodeScalars.map { mapping[$0.value] ?? String($0) }.joined()
        return result.components(separatedBy: CharacterSet(charactersIn: " \t\n\r\u{000c}\u{000b}")).filter { !$0.isEmpty }.joined(separator: " ")
    }
}
