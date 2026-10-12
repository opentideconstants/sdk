import Foundation
public final class OpenTideConstants {
    public private(set) var release:Release
    public private(set) var loadedFrom:LoadedFrom
    public private(set) var lastError:OpenTideConstantsError?
    public private(set) var newerFormatMajor:Int64?
    internal let cache:Cache
    internal let offline:Bool
    internal let pinned:Bool
    internal let baseUrl:URL
    internal let timeout:Double
    internal let userAgent:String?
    internal var opened:[URL]
    private init(release:Release,loadedFrom:LoadedFrom,cache:Cache,offline:Bool,pinned:Bool,baseUrl:URL,timeout:Double,userAgent:String?,opened:[URL]) { self.release=release;self.loadedFrom=loadedFrom;self.cache=cache;self.offline=offline;self.pinned=pinned;self.baseUrl=baseUrl;self.timeout=timeout;self.userAgent=userAgent;self.opened=opened }
    public static func open(release:String?=nil,file:String?=nil,cacheDir:String?=nil,offline:Bool?=nil,mode:Mode = .eager,baseUrl:String?=nil,timeout:Double?=nil,proxy:String?=nil,caFile:String?=nil,userAgent:String?=nil,onNetworkError:OnNetworkError?=nil,autoUpdate:Bool=false,updateInterval:Double=86400,logger:((String)->Void)?=nil,verifyOnOpen:Bool=false,commercialOnly:Bool=false,commercialBasis:String="strict",historicalOffsetsPolicy:String="fallback")async throws->OpenTideConstants {
        let env=ProcessInfo.processInfo.environment
        let offline=(offline ?? false) || ["1","true","yes","on"].contains((env["OPENTIDECONSTANTS_OFFLINE"] ?? "").trimmingCharacters(in:.whitespacesAndNewlines).lowercased())
        let base=baseUrl ?? env["OPENTIDECONSTANTS_BASE_URL"] ?? "https://data.opentideconstants.org/"
        guard let url=URL(string:base),["http","https"].contains(url.scheme ?? ""),url.host != nil,mode != .other,["strict","as_published_upstream"].contains(commercialBasis),["fallback","exclude"].contains(historicalOffsetsPolicy),timeout==nil || timeout!.isFinite && (0.001...1e6).contains(timeout!),updateInterval.isFinite,updateInterval>0 else { throw OpenTideConstantsError.invalidArgument("invalid option") }
        if let userAgent,userAgent.unicodeScalars.contains(where: { $0.value<32 || $0.value==127 }) { throw OpenTideConstantsError.invalidArgument("user_agent control character") }
        if let proxy,URL(string:proxy)?.host==nil { throw OpenTideConstantsError.invalidArgument("invalid proxy") }
        if let ca=caFile ?? env["SSL_CERT_FILE"],!FileManager.default.isReadableFile(atPath:ca) { throw OpenTideConstantsError.io("cannot read CA file",["path":.string(ca)]) }
        let cache=Cache(root:cacheDir.map { URL(fileURLWithPath:$0) } ?? Cache.defaultRoot)
        let selected=release ?? "latest"
        guard selected=="latest" || Cache.validStamp(selected) else { throw OpenTideConstantsError.invalidArgument("bad datestamp") }
        var path:URL,from:LoadedFrom
        if let file {
            guard release==nil,offline==false,onNetworkError==nil else { throw OpenTideConstantsError.invalidArgument("file with release/offline/on_network_error") }
            path=URL(fileURLWithPath:file)
            guard path.lastPathComponent.range(of:#"^OTC_[0-9]{8}(\.[2-9]|\.[1-9][0-9]{1,8})?\.(json|json.gz|jsonl)$"#,options:.regularExpression) != nil else { throw OpenTideConstantsError.invalidArgument("invalid filename") }
            from = .fileUnverified
        } else {
            let candidates=try cache.cached().filter { selected=="latest" || $0==selected }
            guard let d=candidates.first else { throw OpenTideConstantsError.offlineUnavailable("no cached readable release") }
            let dir=try cache.releaseDir(d)
            let names=mode == .stream ? ["jsonl","json","json.gz"]:["json","json.gz","jsonl"]
            guard let candidate=names.map({dir.appendingPathComponent("OTC_\(d).\($0)")}).first(where:{ FileManager.default.fileExists(atPath:$0.path) }) else { throw OpenTideConstantsError.offlineUnavailable("cache missing data") }
            path=candidate;from = .cache
        }
        let name=path.lastPathComponent
        let stamp=String(name.dropFirst(4)).components(separatedBy:".json")[0]
        let checksum=path.deletingLastPathComponent().appendingPathComponent("OTC_\(stamp).sha256")
        var opened=[path]
        if name.hasSuffix("jsonl") { opened.append(URL(fileURLWithPath:String(path.path.dropLast(6))+".meta.json")) }
        if FileManager.default.fileExists(atPath:checksum.path) {
            let rows=try Cache.checksums(checksum)
            for p in opened { guard let expected=rows[p.lastPathComponent] else { throw OpenTideConstantsError.checksumMismatch("not listed",["file":.string(p.path)]) };let actual=try SHA256.file(p);if actual != expected { throw OpenTideConstantsError.checksumMismatch("checksum mismatch",["file":.string(p.path),"expected":.string(expected),"actual":.string(actual)]) } }
            if from == .fileUnverified { from = .file }
        } else if verifyOnOpen { throw OpenTideConstantsError.checksumMismatch("no OTC_\(stamp).sha256 next to file") }
        let index=mode == .stream ? path.deletingLastPathComponent().appendingPathComponent("index-v1.json"):nil
        let loaded=try Reader.load(path,mode:mode,commercialOnly:commercialOnly,commercialBasis:commercialBasis,historicalOffsetsPolicy:historicalOffsetsPolicy,indexPath:index)
        return OpenTideConstants(release:loaded,loadedFrom:from,cache:cache,offline:offline,pinned:file != nil || selected != "latest",baseUrl:url,timeout:timeout ?? 60,userAgent:userAgent,opened:opened)
    }
    public func verify()throws->Bool {
        try release.checkOpen();guard let first=opened.first else { throw OpenTideConstantsError.checksumMismatch("no files") }
        let rows=try Cache.checksums(first.deletingLastPathComponent().appendingPathComponent("OTC_\(release.datestamp).sha256"))
        for path in opened { guard let expected=rows[path.lastPathComponent] else { throw OpenTideConstantsError.checksumMismatch("not listed") };let actual=try SHA256.file(path);if actual != expected { throw OpenTideConstantsError.checksumMismatch("checksum mismatch",["file":.string(path.path),"expected":.string(expected),"actual":.string(actual)]) } };return true
    }
    public func cachedReleases()throws->[String] { try release.checkOpen();return try cache.cached() }
    public func close() { release.close() }
    public func station(stationId:String)throws->Station? { try release.station(stationId:stationId) }
    public func requireStation(stationId:String)throws->Station { try release.requireStation(stationId:stationId) }
    public func tombstone(stationId:String)throws->Tombstone? { try release.tombstone(stationId:stationId) }
    public func stationByAlias(system:String,aliasId:String)throws->Station? { try release.stationByAlias(system:system,aliasId:aliasId) }
    public func stations(country:String?=nil,type:String?=nil,kind:String?=nil,source:String?=nil,sourceType:String?=nil,includeFlagged:Bool=false,includeFallback:Bool=false)throws->[Station] { try release.stations(country:country,type:type,kind:kind,source:source,sourceType:sourceType,includeFlagged:includeFlagged,includeFallback:includeFallback) }
    public func search(name:String,limit:Int64?=nil,match:String?=nil,country:String?=nil,type:String?=nil,kind:String?=nil,source:String?=nil,sourceType:String?=nil,includeFlagged:Bool=false,includeFallback:Bool=false)throws->[Station] { try release.search(name:name,limit:limit,match:match,country:country,type:type,kind:kind,source:source,sourceType:sourceType,includeFlagged:includeFlagged,includeFallback:includeFallback) }
}
