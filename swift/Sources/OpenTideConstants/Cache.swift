import Foundation
import CZlib
internal struct Cache {
    let root:URL
    var base:URL { root.appendingPathComponent("v1") }
    static func validStamp(_ s:String)->Bool { s.range(of:#"^[0-9]{8}(\.[2-9]|\.[1-9][0-9]{1,8})?$"#,options:.regularExpression)?.upperBound==s.endIndex }
    static var defaultRoot:URL { if let p=ProcessInfo.processInfo.environment["OPENTIDECONSTANTS_CACHE_DIR"],!p.isEmpty { return URL(fileURLWithPath:p) };return FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Caches/opentideconstants") }
    func releaseDir(_ s:String)throws->URL { guard Self.validStamp(s) else { throw OpenTideConstantsError.invalidRelease("invalid datestamp") };return base.appendingPathComponent("releases").appendingPathComponent(s) }
    static func atomic(_ data:Data,_ path:URL)throws {
        let temporary=path.deletingLastPathComponent().appendingPathComponent(".tmp-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at:temporary) }
        do { try FileManager.default.createDirectory(at:path.deletingLastPathComponent(),withIntermediateDirectories:true);try data.write(to:temporary);try install(temporary,path) } catch let error as OpenTideConstantsError { throw error } catch { throw OpenTideConstantsError.cache("cannot write \(path.path): \(error)") }
    }
    static func install(_ temporary:URL,_ path:URL)throws {
        do {
            let handle=try FileHandle(forWritingTo:temporary);defer { try? handle.close() };try handle.synchronize()
            if rename(temporary.path,path.path) != 0 { throw POSIXError(POSIXErrorCode(rawValue:errno) ?? .EIO) }
        } catch { throw OpenTideConstantsError.cache("cannot write \(path.path): \(error)") }
    }
    static func gunzip(_ compressed:URL,to path:URL)throws {
        guard let input=gzopen(compressed.path,"rb") else { throw OpenTideConstantsError.checksumMismatch("cannot open gzip",["file":.string(compressed.path)]) }
        defer { gzclose(input) }
        do { try Data().write(to:path) } catch { throw OpenTideConstantsError.cache("cannot create \(path.path): \(error)") }
        let output:FileHandle
        do { output=try FileHandle(forWritingTo:path) } catch { throw OpenTideConstantsError.cache("cannot open \(path.path): \(error)") }
        defer { try? output.close() }
        var buffer=[UInt8](repeating:0,count:65536)
        do {
            while true {
                let count=buffer.withUnsafeMutableBytes { gzread(input,$0.baseAddress,UInt32($0.count)) }
                guard count>=0 else { throw OpenTideConstantsError.checksumMismatch("invalid gzip",["file":.string(compressed.path)]) }
                if count==0 { break }
                try output.write(contentsOf:Data(buffer.prefix(Int(count))))
            }
            try output.synchronize()
        } catch let error as OpenTideConstantsError { throw error }
        catch { throw OpenTideConstantsError.cache("cannot decompress into \(path.path): \(error)") }
    }
    func cached()throws->[String] {
        let dir=base.appendingPathComponent("releases")
        if !FileManager.default.fileExists(atPath:dir.path) { return [] }
        do {
            let names=try FileManager.default.contentsOfDirectory(at:dir,includingPropertiesForKeys:nil).map(\.lastPathComponent).filter(Self.validStamp).filter { try verified($0) != nil }
            return names.sorted(by:Self.newer)
        } catch let error as OpenTideConstantsError { throw error }
        catch { throw OpenTideConstantsError.cache("cannot list \(dir.path): \(error)") }
    }
    static func checksums(_ path:URL)throws->[String:String] {
        try checksums(Reader.read(path))
    }
    static func checksums(_ data:Data)throws->[String:String] {
        guard let text=String(data:data,encoding:.utf8) else { throw OpenTideConstantsError.invalidRelease("checksum file not UTF8") }
        var result:[String:String]=[:]
        for line in text.components(separatedBy:"\n") {
            if line.utf8.allSatisfy(asciiWhitespace) { continue }
            let bits=line.split(maxSplits:1,whereSeparator:{ $0==" " || $0=="\t" });guard bits.count==2 else { throw OpenTideConstantsError.invalidRelease("invalid checksum row") }
            let digest=String(bits[0]),name=String(bits[1]).trimmingCharacters(in:.whitespacesAndNewlines).trimmingCharacters(in:CharacterSet(charactersIn:"*"))
            guard digest.range(of:"^[a-fA-F0-9]{64}$",options:.regularExpression) != nil,!name.contains("/"),result[name]==nil else { throw OpenTideConstantsError.invalidRelease("invalid/duplicate checksum row") };result[name]=digest.lowercased()
        }
        guard !result.isEmpty else { throw OpenTideConstantsError.invalidRelease("no valid checksum rows") };return result
    }
    static func newer(_ a:String,_ b:String)->Bool {
        let aa=a.split(separator:"."),bb=b.split(separator:".")
        return (String(aa[0]),aa.count>1 ? Int(aa[1]) ?? 1:1) > (String(bb[0]),bb.count>1 ? Int(bb[1]) ?? 1:1)
    }
    func pointer(_ name:String)->URL { base.appendingPathComponent("pointer").appendingPathComponent(name) }
    func verified(_ stamp:String)throws->JSONValue? {
        let path=try releaseDir(stamp).appendingPathComponent(".verified")
        guard FileManager.default.fileExists(atPath:path.path) else { return nil }
        do {
            let value=try JSONValue.parse(Data(contentsOf:path))
            return Self.validVerified(value,stamp:stamp) ? value:nil
        } catch let error as OpenTideConstantsError { if error.code=="invalid_release" { return nil };throw error }
        catch { throw OpenTideConstantsError.cache("cannot read \(path.path): \(error)") }
    }
    static func validVerified(_ value:JSONValue,stamp:String)->Bool {
        guard case .object=value,case .object=value["files"] else { return false }
        var pending:[(JSONValue,Int)]=[(value,1)]
        while let (node,depth)=pending.popLast() {
            switch node {
            case .array(let children):
                guard depth<=64 else { return false }
                pending.append(contentsOf:children.map { ($0,depth+1) })
            case .object(let children):
                guard depth<=64 else { return false }
                pending.append(contentsOf:children.values.map { ($0,depth+1) })
            default:break
            }
        }
        for row in value["files"].object.values {
            guard case .object=row,let size=row["size"].integer,(0...9_007_199_254_740_991).contains(size),row["url"].isNull || row["url"].string != nil else { return false }
            if !row["sha256"].isNull {
                guard let sha=row["sha256"].string,sha.range(of:#"^[a-fA-F0-9]{64}$"#,options:.regularExpression)?.upperBound==sha.endIndex else { return false }
            }
        }
        if !value["datestamp"].isNull && value["datestamp"].string != stamp { return false }
        for key in ["format_version","min_reader_version"] where !value[key].isNull {
            guard let version=value[key].string,version.range(of:#"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"#,options:.regularExpression)?.upperBound==version.endIndex else { return false }
        }
        for key in ["zenodo_version_doi","verified_at","by"] where !value[key].isNull {
            guard value[key].string != nil else { return false }
        }
        return true
    }
    func fileOK(_ stamp:String,_ name:String,_ row:JSONValue)throws->Bool {
        let path=try releaseDir(stamp).appendingPathComponent(name)
        guard let expected=row["size"].integer,expected>=0,row["sha256"].string != nil,FileManager.default.fileExists(atPath:path.path) else { return false }
        do { return (try FileManager.default.attributesOfItem(atPath:path.path)[.size] as? NSNumber)?.int64Value==expected }
        catch { throw OpenTideConstantsError.cache("cannot stat \(path.path): \(error)") }
    }
    func heal(_ stamp:String,_ error:OpenTideConstantsError)throws {
        let directory=try releaseDir(stamp)
        try? FileManager.default.removeItem(at:directory.appendingPathComponent(".verified"))
        if let path=error.fields["file"]?.string { try? FileManager.default.removeItem(at:directory.appendingPathComponent(URL(fileURLWithPath:path).lastPathComponent)) }
    }
    // Directory locks are shared with the other SDKs. Only the token owner releases one.
    func takeLock(_ directory:URL,wait:Bool=true,beforeMkdir:(()->Void)?=nil)async throws->String? {
        do { try FileManager.default.createDirectory(at:directory,withIntermediateDirectories:true) }
        catch { throw OpenTideConstantsError.cache("cannot create \(directory.path): \(error)") }
        let lock=directory.appendingPathComponent(".lock"),start=ProcessInfo.processInfo.systemUptime
        var failures=0
        while true {
            do { beforeMkdir?();try FileManager.default.createDirectory(at:lock,withIntermediateDirectories:false) }
            catch {
                guard FileManager.default.fileExists(atPath:lock.path) else { throw OpenTideConstantsError.cache("cannot take lock \(lock.path): \(error)") }
                let owner=(try? JSONValue.parse(Data(contentsOf:lock.appendingPathComponent("owner.json")))) ?? .null
                let date=owner["started_at"].string.flatMap { ISO8601DateFormatter().date(from:$0) } ?? ((try? FileManager.default.attributesOfItem(atPath:lock.path)[.modificationDate]) as? Date)
                if let date,Date().timeIntervalSince(date)>=120,(!wait || ProcessInfo.processInfo.systemUptime-start>=120) {
                    do { try FileManager.default.removeItem(at:lock) }
                    catch { failures+=1;if failures>=3 { throw OpenTideConstantsError.cache("cannot remove stale lock \(lock.path)") } }
                    continue
                }
                if !wait { return nil }
                try await Task.sleep(nanoseconds:500_000_000)
                continue
            }
            let token=UUID().uuidString
            do { try Self.atomic(JSONValue.object(["pid":.integer(Int64(ProcessInfo.processInfo.processIdentifier)),"host":.string(ProcessInfo.processInfo.hostName),"sdk":.string("opentideconstants-swift/0.1.0"),"started_at":.string(ISO8601DateFormatter().string(from:Date())),"token":.string(token)]).data(),lock.appendingPathComponent("owner.json")) }
            catch { try? FileManager.default.removeItem(at:lock);throw error }
            return token
        }
    }
    func releaseLock(_ directory:URL,_ token:String?) {
        guard let token else { return }
        let lock=directory.appendingPathComponent(".lock")
        guard let owner=try? JSONValue.parse(Data(contentsOf:lock.appendingPathComponent("owner.json"))),owner["token"].string==token else { return }
        try? FileManager.default.removeItem(at:lock.appendingPathComponent("owner.json"))
        try? FileManager.default.removeItem(at:lock)
    }
}
