import Foundation
internal struct Cache {
    let root:URL
    var base:URL { root.appendingPathComponent("v1") }
    static func validStamp(_ s:String)->Bool { s.range(of:#"^[0-9]{8}(\.[2-9]|\.[1-9][0-9]{1,8})?$"#,options:.regularExpression)?.upperBound==s.endIndex }
    static var defaultRoot:URL { if let p=ProcessInfo.processInfo.environment["OPENTIDECONSTANTS_CACHE_DIR"],!p.isEmpty { return URL(fileURLWithPath:p) };return FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Caches/opentideconstants") }
    func releaseDir(_ s:String)throws->URL { guard Self.validStamp(s) else { throw OpenTideConstantsError.invalidRelease("invalid datestamp") };return base.appendingPathComponent("releases").appendingPathComponent(s) }
    static func atomic(_ data:Data,_ path:URL)throws {
        do { try FileManager.default.createDirectory(at:path.deletingLastPathComponent(),withIntermediateDirectories:true);try data.write(to:path,options:.atomic) } catch { throw OpenTideConstantsError.cache("cannot write \(path.path): \(error)") }
    }
    func cached()throws->[String] {
        let dir=base.appendingPathComponent("releases")
        if !FileManager.default.fileExists(atPath:dir.path) { return [] }
        let names=try FileManager.default.contentsOfDirectory(at:dir,includingPropertiesForKeys:nil).filter { Self.validStamp($0.lastPathComponent) && FileManager.default.fileExists(atPath:$0.appendingPathComponent(".verified").path) }.map(\.lastPathComponent)
        return names.sorted { a,b in let aa=a.split(separator:"."),bb=b.split(separator:".");return (String(aa[0]),aa.count>1 ? Int(aa[1])! : 1) > (String(bb[0]),bb.count>1 ? Int(bb[1])! : 1) }
    }
    static func checksums(_ path:URL)throws->[String:String] {
        let data=try Reader.read(path);guard let text=String(data:data,encoding:.utf8) else { throw OpenTideConstantsError.invalidRelease("checksum file not UTF8") }
        var result:[String:String]=[:]
        for line in text.split(separator:"\n") {
            let bits=line.split(maxSplits:1,whereSeparator:{ $0==" " || $0=="\t" });if bits.count != 2 { continue }
            let digest=String(bits[0]),name=String(bits[1]).trimmingCharacters(in:.whitespaces).trimmingCharacters(in:CharacterSet(charactersIn:"*"))
            guard digest.range(of:"^[a-fA-F0-9]{64}$",options:.regularExpression) != nil,!name.contains("/"),result[name]==nil else { throw OpenTideConstantsError.invalidRelease("invalid/duplicate checksum row") };result[name]=digest.lowercased()
        }
        guard !result.isEmpty else { throw OpenTideConstantsError.invalidRelease("no valid checksum rows") };return result
    }
}
