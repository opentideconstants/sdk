import Foundation
public let supportedFormatMajors:[Int] = [1]
public let supportedFormatVersion:String = "1.0"
public let defaultBaseUrl:String = "https://data.opentideconstants.org/"
public let cacheLayoutVersion:String = "v1"
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
    private let io:ClientIO
    private let autoUpdate:Bool
    private let updateInterval:Double
    private let lock=NSRecursiveLock()
    private var lastCheck=ProcessInfo.processInfo.systemUptime
    private var closed=false
    private var updating=false
    private final class Held { weak var release:Release?;init(_ release:Release) { self.release=release } }
    private var held:[Held]
    private init(loaded:ClientIO.Loaded,io:ClientIO,pinned:Bool,autoUpdate:Bool,updateInterval:Double) {
        release=loaded.release;loadedFrom=loaded.from;lastError=loaded.error;opened=loaded.paths
        self.io=io;cache=io.cache;offline=io.offline;self.pinned=pinned;baseUrl=io.baseUrl;timeout=io.timeout;userAgent=io.userAgent
        self.autoUpdate=autoUpdate;self.updateInterval=updateInterval;held=[Held(loaded.release)]
    }
    public static func open(release:String?=nil,file:String?=nil,cacheDir:String?=nil,offline:Bool?=nil,mode:Mode = .eager,baseUrl:String?=nil,timeout:Double?=nil,proxy:String?=nil,caFile:String?=nil,userAgent:String?=nil,onNetworkError:OnNetworkError?=nil,autoUpdate:Bool=false,updateInterval:Double=86400,logger:((String)->Void)?=nil,verifyOnOpen:Bool=false,commercialOnly:Bool=false,commercialBasis:String="strict",historicalOffsetsPolicy:String="fallback")async throws->OpenTideConstants {
        let env=ProcessInfo.processInfo.environment
        let requestedOffline=offline ?? false
        let offline=(offline ?? false) || ["1","true","yes","on"].contains((env["OPENTIDECONSTANTS_OFFLINE"] ?? "").trimmingCharacters(in:.whitespacesAndNewlines).lowercased())
        let base=baseUrl ?? env["OPENTIDECONSTANTS_BASE_URL"] ?? "https://data.opentideconstants.org/"
        guard let url=URL(string:base),["http","https"].contains(url.scheme ?? ""),url.host != nil,mode != .other,["strict","as_published_upstream"].contains(commercialBasis),["fallback","exclude"].contains(historicalOffsetsPolicy),timeout==nil || timeout!.isFinite && (0.001...1e6).contains(timeout!),updateInterval.isFinite,updateInterval>0 else { throw OpenTideConstantsError.invalidArgument("invalid option") }
        if let userAgent,userAgent.unicodeScalars.contains(where: { $0.value<32 || $0.value==127 }) { throw OpenTideConstantsError.invalidArgument("user_agent control character") }
        if let proxy { guard let p=URL(string:proxy),p.scheme=="http",p.host != nil,p.port==nil || (1...65535).contains(p.port!) else { throw OpenTideConstantsError.invalidArgument("invalid proxy") } }
        guard onNetworkError != .other else { throw OpenTideConstantsError.invalidArgument("invalid on_network_error") }
        if let ca=caFile ?? env["SSL_CERT_FILE"],!FileManager.default.isReadableFile(atPath:ca) { throw OpenTideConstantsError.io("cannot read CA file",["path":.string(ca)]) }
        let cache=Cache(root:cacheDir.map { URL(fileURLWithPath:$0) } ?? Cache.defaultRoot)
        let selected=release ?? "latest"
        guard selected=="latest" || Cache.validStamp(selected) else { throw OpenTideConstantsError.invalidArgument("bad datestamp") }
        if file != nil { guard release==nil,!requestedOffline,onNetworkError==nil else { throw OpenTideConstantsError.invalidArgument("file with release/offline/on_network_error") } }
        let normalized=URL(string:url.absoluteString.hasSuffix("/") ? url.absoluteString:url.absoluteString+"/")!
        let io=ClientIO(cache:cache,offline:offline,mode:mode,baseUrl:normalized,timeout:timeout ?? 60,proxy:proxy,caFile:caFile ?? env["SSL_CERT_FILE"],userAgent:userAgent,onNetworkError:onNetworkError ?? .useCache,verifyOnOpen:verifyOnOpen,commercialOnly:commercialOnly,commercialBasis:commercialBasis,historicalOffsetsPolicy:historicalOffsetsPolicy,logger:logger)
        return OpenTideConstants(loaded:try await io.open(selected,file:file),io:io,pinned:file != nil || selected != "latest",autoUpdate:autoUpdate,updateInterval:updateInterval)
    }
    public func verify()throws->Bool {
        try state {
            try checkOpen();guard let first=opened.first else { throw OpenTideConstantsError.checksumMismatch("no files") }
            let name="OTC_\(release.datestamp).sha256",sha=first.deletingLastPathComponent().appendingPathComponent(name)
            guard FileManager.default.fileExists(atPath:sha.path) else { throw OpenTideConstantsError.checksumMismatch("no \(name) next to file",["file":.string(first.path)]) }
            let bytes=try Reader.read(sha)
            if loadedFrom != .file && loadedFrom != .fileUnverified {
                for pointer in ["OTC_latest-f1.json","OTC_latest.json"] {
                    guard let doc=try? JSONValue.parse(Data(contentsOf:cache.pointer(pointer))),doc["datestamp"].string==release.datestamp else { continue }
                    if let expected=doc["files"].array.first(where:{ $0["name"].string==name })?["sha256"].string,SHA256.digest(bytes) != expected.lowercased() { throw OpenTideConstantsError.checksumMismatch("checksum file differs from cached pointer",["file":.string(sha.path),"expected":.string(expected),"actual":.string(SHA256.digest(bytes))]) }
                }
            }
            let rows=try Cache.checksums(bytes)
            for path in opened { try io.check(path,sha:rows[path.lastPathComponent]) }
            return true
        }
    }
    public func cachedReleases()throws->[String] { try release.checkOpen();return try cache.cached() }
    private func state<Value>(_ body:()throws->Value)rethrows->Value { lock.lock();defer { lock.unlock() };return try body() }
    private func checkOpen()throws { try state { guard !closed else { throw OpenTideConstantsError.io("the release is closed") };try release.checkOpen() } }
    public func releases()async throws->[ReleaseInfo] {
        try checkOpen()
        do { return try await io.index().map(ReleaseInfo.init) }
        catch let error as OpenTideConstantsError {
            guard error.code=="network",io.onNetworkError == .useCache,let doc=try? JSONValue.parse(Data(contentsOf:cache.pointer("OTC_index.json"))),case .array=doc["releases"] else { throw error }
            return try doc["releases"].array.map { ReleaseInfo(try io.entry($0,source:baseUrl.appendingPathComponent("OTC_index.json"))) }.sorted { Cache.newer($0.datestamp,$1.datestamp) }
        }
    }
    public func latest()async throws->ReleaseInfo {
        try checkOpen()
        do { let entry=try await io.resolveLatest();state { lastError=nil };return ReleaseInfo(entry) }
        catch let error as OpenTideConstantsError { if ["unsupported_format","reader_too_old"].contains(error.code) { state { lastError=nil } };throw error }
    }
    public func checkForUpdate()async throws->ReleaseInfo? {
        try checkOpen()
        do {
            let latest=try await latest()
            await checkNewerFormat()
            return Cache.newer(latest.datestamp,release.datestamp) ? latest:nil
        } catch let error as OpenTideConstantsError { if ["unsupported_format","reader_too_old"].contains(error.code) { await checkNewerFormat() };throw error }
    }
    private func checkNewerFormat()async {
        do {
            let doc=try await io.pointer("OTC_latest.json")
            if doc==nil { state { newerFormatMajor=nil };return }
            guard let version=doc?["format_version"].string,let major=Int64(version.split(separator:".").first ?? "") else { return }
            state { newerFormatMajor=major>1 ? major:nil }
        } catch { io.logger?("opentideconstants: cannot check newer format") }
    }
    private func takeUpdate()throws->Bool {
        try state { try checkOpen();if updating { return false };updating=true;return true }
    }
    public func update()async throws->UpdateResult {
        try checkOpen()
        guard !pinned else { throw OpenTideConstantsError.pinnedRelease("the client is pinned") }
        guard !offline else { throw OpenTideConstantsError.offlineUnavailable("update needs the latest pointer") }
        while try !takeUpdate() { try await Task.sleep(nanoseconds:10_000_000) }
        defer { state { updating=false } }
        let from=release.datestamp,entry=try await io.resolveLatest(),to=entry["datestamp"].string!
        state { lastError=nil }
        guard Cache.newer(to,from) else { state { lastCheck=ProcessInfo.processInfo.systemUptime };return UpdateResult(updated:false,from:from,to:from) }
        let loaded:ClientIO.Loaded
        if let cached=try io.usableCached(to) { loaded=cached } else { loaded=try await io.fetch(to,entry:entry) }
        return try state {
            guard !closed else { loaded.release.close();throw OpenTideConstantsError.io("the release is closed") }
            held=held.filter { $0.release != nil };held.append(Held(loaded.release))
            release=loaded.release;loadedFrom=loaded.from;opened=loaded.paths;lastError=nil;lastCheck=ProcessInfo.processInfo.systemUptime
            return UpdateResult(updated:true,from:from,to:to)
        }
    }
    public func download(release:String="latest",to:String,formats:[Format]=[.jsonl],overwrite:Bool=false)async throws->[String] {
        try checkOpen()
        guard release=="latest" || Cache.validStamp(release),!to.isEmpty,!formats.isEmpty,!formats.contains(.other) else { throw OpenTideConstantsError.invalidArgument("invalid download option") }
        return try await io.download(release,to:URL(fileURLWithPath:to),formats:formats,overwrite:overwrite)
    }
    public func prune(keep:Int64=3)async throws->[String] {
        try checkOpen();guard keep>=0 else { throw OpenTideConstantsError.invalidArgument("invalid keep") }
        let protected=state { pinned && loadedFrom == .file || loadedFrom == .fileUnverified ? Set<String>():Set(held.compactMap { $0.release?.datestamp }) }
        let directory=cache.base.appendingPathComponent("releases")
        guard FileManager.default.fileExists(atPath:directory.path) else { return [] }
        let candidates=try FileManager.default.contentsOfDirectory(at:directory,includingPropertiesForKeys:nil).map(\.lastPathComponent).filter(Cache.validStamp).sorted(by:Cache.newer)
        let retain=Set(try cache.cached().prefix(Int(min(keep,Int64(Int.max)))))
        var removed:[String]=[]
        for stamp in candidates where !protected.contains(stamp) && !retain.contains(stamp) {
            do {
                let path=try cache.releaseDir(stamp),token=try await cache.takeLock(path,wait:false)
                guard token != nil else { continue }
                defer { cache.releaseLock(path,token) }
                let verified=FileManager.default.fileExists(atPath:path.appendingPathComponent(".verified").path)
                for child in try FileManager.default.contentsOfDirectory(at:path,includingPropertiesForKeys:nil) where child.lastPathComponent != ".lock" { try FileManager.default.removeItem(at:child) }
                cache.releaseLock(path,token);try? FileManager.default.removeItem(at:path)
                if verified { removed.append(stamp) }
            } catch {
                var fields=(error as? OpenTideConstantsError)?.fields ?? [:]
                fields["removed"] = .array(removed.map(JSONValue.string))
                throw OpenTideConstantsError.cache("cannot prune \(stamp)",fields)
            }
        }
        return removed
    }
    private final class QueryResult:@unchecked Sendable {
        let client:OpenTideConstants
        var error:Error?
        init(_ client:OpenTideConstants) { self.client=client }
    }
    private func queryRelease()throws->Release {
        try checkOpen()
        let due=state { ()->Bool in
            guard autoUpdate,!pinned,!offline,ProcessInfo.processInfo.systemUptime-lastCheck>=updateInterval else { return false }
            lastCheck=ProcessInfo.processInfo.systemUptime;return true
        }
        if due {
            let semaphore=DispatchSemaphore(value:0),result=QueryResult(self)
            Task.detached {
                do { _=try await result.client.update() }
                catch let error as OpenTideConstantsError { result.client.state { result.client.lastError=error };result.client.io.logger?("opentideconstants: automatic update failed") }
                catch { result.error=error }
                semaphore.signal()
            }
            semaphore.wait()
            if let error=result.error { throw error }
        }
        return try state { try checkOpen();return release }
    }
    public func close() { lock.lock();defer { lock.unlock() };guard !closed else { return };closed=true;for value in held { value.release?.close() };release.close() }
    public func station(stationId:String)throws->Station? { try queryRelease().station(stationId:stationId) }
    public func requireStation(stationId:String)throws->Station { try queryRelease().requireStation(stationId:stationId) }
    public func tombstone(stationId:String)throws->Tombstone? { try queryRelease().tombstone(stationId:stationId) }
    public func stationByAlias(system:String,aliasId:String)throws->Station? { try queryRelease().stationByAlias(system:system,aliasId:aliasId) }
    public func stations(country:String?=nil,type:String?=nil,kind:String?=nil,source:String?=nil,sourceType:String?=nil,includeFlagged:Bool=false,includeFallback:Bool=false)throws->[Station] { try queryRelease().stations(country:country,type:type,kind:kind,source:source,sourceType:sourceType,includeFlagged:includeFlagged,includeFallback:includeFallback) }
    public func search(name:String,limit:Int64?=nil,match:String?=nil,country:String?=nil,type:String?=nil,kind:String?=nil,source:String?=nil,sourceType:String?=nil,includeFlagged:Bool=false,includeFallback:Bool=false)throws->[Station] { try queryRelease().search(name:name,limit:limit,match:match,country:country,type:type,kind:kind,source:source,sourceType:sourceType,includeFlagged:includeFlagged,includeFallback:includeFallback) }
    public func iterStations(country:String?=nil,type:String?=nil,kind:String?=nil,source:String?=nil,sourceType:String?=nil,includeFlagged:Bool=false,includeFallback:Bool=false)throws->(()throws->Station?) { try queryRelease().iterStations(country:country,type:type,kind:kind,source:source,sourceType:sourceType,includeFlagged:includeFlagged,includeFallback:includeFallback) }
    public func near(lat:Double,lon:Double,radiusKm:Double,limit:Int64?=nil,country:String?=nil,type:String?=nil,kind:String?=nil,source:String?=nil,sourceType:String?=nil,includeFlagged:Bool=false,includeFallback:Bool=false)throws->[Nearby] { try queryRelease().near(lat:lat,lon:lon,radiusKm:radiusKm,limit:limit,country:country,type:type,kind:kind,source:source,sourceType:sourceType,includeFlagged:includeFlagged,includeFallback:includeFallback) }
    public func nearest(lat:Double,lon:Double,maxKm:Double?=nil,country:String?=nil,type:String?=nil,kind:String?=nil,source:String?=nil,sourceType:String?=nil,includeFlagged:Bool=false,includeFallback:Bool=false)throws->Nearby? { try queryRelease().nearest(lat:lat,lon:lon,maxKm:maxKm,country:country,type:type,kind:kind,source:source,sourceType:sourceType,includeFlagged:includeFlagged,includeFallback:includeFallback) }
    public func referenceStation(station:Station)throws->Station? { try queryRelease().referenceStation(station:station) }
    public func subordinatesOf(station:Station)throws->[Station] { try queryRelease().subordinatesOf(station:station) }
    public func attribution(stations:[Station]?=nil)throws->String { try queryRelease().attribution(stations:stations) }
    public func heights(station:Station,start:Date,stop:Date,stepS:Int64=600,datum:String?=nil,setId:String?=nil,offsetId:String?=nil)throws->HeightSeries { try queryRelease().heights(station:station,start:start,stop:stop,stepS:stepS,datum:datum,setId:setId,offsetId:offsetId) }
    public func heights(stationId:String,start:Date,stop:Date,stepS:Int64=600,datum:String?=nil,setId:String?=nil,offsetId:String?=nil)throws->HeightSeries { try queryRelease().heights(stationId:stationId,start:start,stop:stop,stepS:stepS,datum:datum,setId:setId,offsetId:offsetId) }
    public func heightsAt(station:Station,times:[Date],datum:String?=nil,setId:String?=nil,offsetId:String?=nil)throws->HeightSeries { try queryRelease().heightsAt(station:station,times:times,datum:datum,setId:setId,offsetId:offsetId) }
    public func heightsAt(stationId:String,times:[Date],datum:String?=nil,setId:String?=nil,offsetId:String?=nil)throws->HeightSeries { try queryRelease().heightsAt(stationId:stationId,times:times,datum:datum,setId:setId,offsetId:offsetId) }
    public func extremes(station:Station,start:Date,stop:Date,datum:String?=nil,setId:String?=nil,offsetId:String?=nil)throws->ExtremeList { try queryRelease().extremes(station:station,start:start,stop:stop,datum:datum,setId:setId,offsetId:offsetId) }
    public func extremes(stationId:String,start:Date,stop:Date,datum:String?=nil,setId:String?=nil,offsetId:String?=nil)throws->ExtremeList { try queryRelease().extremes(stationId:stationId,start:start,stop:stop,datum:datum,setId:setId,offsetId:offsetId) }
    public func currents(station:Station,start:Date,stop:Date,stepS:Int64=600,binNumber:Int64?=nil,setId:String?=nil)throws->CurrentSeries { try queryRelease().currents(station:station,start:start,stop:stop,stepS:stepS,binNumber:binNumber,setId:setId) }
    public func currents(stationId:String,start:Date,stop:Date,stepS:Int64=600,binNumber:Int64?=nil,setId:String?=nil)throws->CurrentSeries { try queryRelease().currents(stationId:stationId,start:start,stop:stop,stepS:stepS,binNumber:binNumber,setId:setId) }
    public func currentEvents(station:Station,start:Date,stop:Date,binNumber:Int64?=nil,setId:String?=nil)throws->CurrentEventList { try queryRelease().currentEvents(station:station,start:start,stop:stop,binNumber:binNumber,setId:setId) }
    public func currentEvents(stationId:String,start:Date,stop:Date,binNumber:Int64?=nil,setId:String?=nil)throws->CurrentEventList { try queryRelease().currentEvents(stationId:stationId,start:start,stop:stop,binNumber:binNumber,setId:setId) }
    public func datums(station:Station,setId:String?=nil,allSets:Bool=false)throws->DatumsResult { try queryRelease().datums(station:station,setId:setId,allSets:allSets) }
    public func datums(stationId:String,setId:String?=nil,allSets:Bool=false)throws->DatumsResult { try queryRelease().datums(stationId:stationId,setId:setId,allSets:allSets) }
    public func ranges(station:Station,setId:String?=nil)throws->Ranges { try queryRelease().ranges(station:station,setId:setId) }
    public func ranges(stationId:String,setId:String?=nil)throws->Ranges { try queryRelease().ranges(stationId:stationId,setId:setId) }
    public func astroTable(id:String?=nil)throws->AstroTable? { try queryRelease().astroTable(id:id) }
}

private struct ClientIO:@unchecked Sendable {
    struct Loaded { let release:Release;let from:LoadedFrom;let paths:[URL];var error:OpenTideConstantsError?=nil }
    let cache:Cache
    let offline:Bool
    let mode:Mode
    let baseUrl:URL
    let timeout:Double
    let proxy:String?
    let caFile:String?
    let userAgent:String?
    let onNetworkError:OnNetworkError
    let verifyOnOpen:Bool
    let commercialOnly:Bool
    let commercialBasis:String
    let historicalOffsetsPolicy:String
    let logger:((String)->Void)?

    func read(_ path:URL,files:[FileInfo],from:LoadedFrom)throws->Loaded {
        var paths=[path]
        if path.lastPathComponent.hasSuffix(".jsonl") { paths.append(URL(fileURLWithPath:String(path.path.dropLast(6))+".meta.json")) }
        let release=try Reader.load(path,mode:mode,commercialOnly:commercialOnly,commercialBasis:commercialBasis,historicalOffsetsPolicy:historicalOffsetsPolicy,indexPath:mode == .stream ? path.deletingLastPathComponent().appendingPathComponent("index-v1.json"):nil,files:files,logger:logger)
        return Loaded(release:release,from:from,paths:paths)
    }
    func file(_ file:String)throws->Loaded {
        let path=URL(fileURLWithPath:file),name=path.lastPathComponent
        guard name.range(of:#"^OTC_[0-9]{8}(\.[2-9]|\.[1-9][0-9]{1,8})?\.(json|json.gz|jsonl)$"#,options:.regularExpression)?.upperBound==name.endIndex else { throw OpenTideConstantsError.invalidArgument("invalid filename") }
        let stamp=String(name.dropFirst(4)).components(separatedBy:".json")[0]
        let directory=path.deletingLastPathComponent(),sha=directory.appendingPathComponent("OTC_\(stamp).sha256")
        let names=name.hasSuffix(".jsonl") ? [name,"OTC_\(stamp).meta.json"]:[name]
        let rows=FileManager.default.fileExists(atPath:sha.path) ? try Cache.checksums(sha):nil
        if let rows {
            for name in names { try check(directory.appendingPathComponent(name),sha:rows[name]) }
        } else if verifyOnOpen { throw OpenTideConstantsError.checksumMismatch("no OTC_\(stamp).sha256 next to file") }
        let metadataNames=rows.map { Array($0.keys) } ?? names
        let metadata=metadataNames.sorted().map { name -> FileInfo in
            let p=directory.appendingPathComponent(name)
            let size=((try? FileManager.default.attributesOfItem(atPath:p.path)[.size]) as? NSNumber)?.int64Value
            return FileInfo(.object(["name":.string(name),"url":.null,"size":size.map(JSONValue.integer) ?? .null,"sha256":rows?[name].map(JSONValue.string) ?? .null]))
        }
        return try read(path,files:metadata,from:rows==nil ? .fileUnverified:.file)
    }
    func check(_ path:URL,sha:String?,size:Int64?=nil,hash:Bool=true)throws {
        guard let sha else { throw OpenTideConstantsError.checksumMismatch("not listed",["file":.string(path.path)]) }
        if let size,(try FileManager.default.attributesOfItem(atPath:path.path)[.size] as? NSNumber)?.int64Value != size { throw OpenTideConstantsError.checksumMismatch("size mismatch",["file":.string(path.path),"expected":.string(sha),"actual":.null]) }
        if hash { let actual=try SHA256.file(path);guard actual==sha.lowercased() else { throw OpenTideConstantsError.checksumMismatch("checksum mismatch",["file":.string(path.path),"expected":.string(sha),"actual":.string(actual)]) } }
    }
    func cached(_ stamp:String,files:[FileInfo]?=nil)throws->Loaded? {
        guard let marker=try cache.verified(stamp) else { return nil }
        let directory=try cache.releaseDir(stamp)
        let choices=mode == .stream ? [["OTC_\(stamp).jsonl","OTC_\(stamp).meta.json"]]:[["OTC_\(stamp).json"],["OTC_\(stamp).jsonl","OTC_\(stamp).meta.json"]]
        guard let names=choices.first(where:{ $0.allSatisfy { marker["files"][$0].object.isEmpty==false && FileManager.default.fileExists(atPath:directory.appendingPathComponent($0).path) } }) else { return nil }
        for name in names {
            let row=marker["files"][name]
            try check(directory.appendingPathComponent(name),sha:row["sha256"].string,size:row["size"].integer,hash:verifyOnOpen)
        }
        let metadata=files ?? marker["files"].object.keys.sorted().map { name -> FileInfo in var row=marker["files"][name].object;row["name"] = .string(name);return FileInfo(.object(row)) }
        let path=directory.appendingPathComponent(names[0])
        do {
            let loaded=try read(path,files:metadata,from:.cache)
            loaded.release.zenodoVersionDoi=marker["zenodo_version_doi"].string
            return loaded
        } catch let error as OpenTideConstantsError {
            if error.code=="invalid_release",mode == .eager,path.pathExtension=="json",error.fields["file"]==nil {
                var fields=error.fields;fields["file"] = .string(path.path)
                throw OpenTideConstantsError.invalidRelease(error.message,fields)
            }
            throw error
        }
    }
    func usableCached(_ stamp:String)throws->Loaded? {
        do { return try cached(stamp) }
        catch let error as OpenTideConstantsError {
            if ["checksum_mismatch","invalid_release"].contains(error.code) { try cache.heal(stamp,error);if !offline { return nil } }
            throw error
        }
    }
    func newestCached()throws->Loaded? {
        for stamp in try cache.cached() {
            do { if let loaded=try cached(stamp) { return loaded } }
            catch let error as OpenTideConstantsError {
                if ["checksum_mismatch","invalid_release"].contains(error.code) { try cache.heal(stamp,error) }
                else if !["unsupported_format","reader_too_old"].contains(error.code) { throw error }
            }
        }
        return nil
    }
    func open(_ selected:String,file:String?)async throws->Loaded {
        if let file { return try self.file(file) }
        if selected != "latest" {
            if let loaded=try usableCached(selected) { return loaded }
            guard !offline else { throw OpenTideConstantsError.offlineUnavailable("release \(selected) is not cached") }
            return try await fetch(selected,entry:nil)
        }
        if offline { guard let loaded=try newestCached() else { throw OpenTideConstantsError.offlineUnavailable("no cached readable release") };return loaded }
        do {
            let entry=try await resolveLatest()
            if let loaded=try usableCached(entry["datestamp"].string!) { return loaded }
            return try await fetch(entry["datestamp"].string!,entry:entry)
        } catch let error as OpenTideConstantsError {
            guard error.code=="network",onNetworkError == .useCache,let loaded=try newestCached() else { throw error }
            return Loaded(release:loaded.release,from:.cacheAfterError,paths:loaded.paths,error:error)
        }
    }
    func pointerShape(_ name:String,_ value:JSONValue)->Bool {
        guard case .object=value else { return false }
        if name=="OTC_index.json" { if case .array=value["releases"] { return true };return false }
        if case .array=value["files"] { return value.object.keys.contains("datestamp") };return false
    }
    func pointer(_ name:String)async throws->JSONValue? {
        let path=cache.pointer(name),url=baseUrl.appendingPathComponent(name)
        func readTag()->Data? {
            guard let bytes=try? Data(contentsOf:path.appendingPathExtension("etag")),(1...256).contains(bytes.count),bytes.allSatisfy({ (32...126).contains($0) }) else { return nil }
            return bytes
        }
        let firstTag=readTag()
        let candidate=(try? JSONValue.parse(Data(contentsOf:path)))
        let stored=candidate.flatMap { pointerShape(name,$0) ? $0:nil }
        let secondTag=readTag()
        let etag=stored != nil && firstTag != nil && firstTag==secondTag ? String(data:firstTag!,encoding:.ascii):nil
        if offline { guard let stored else { throw OpenTideConstantsError.offlineUnavailable("\(name) not cached") };return stored }
        var response=try await HTTP.response(url,timeout:timeout,userAgent:userAgent,proxy:proxy,caFile:caFile,etag:etag)
        if response.status==304,stored==nil { response=try await HTTP.response(url,timeout:timeout,userAgent:userAgent,proxy:proxy,caFile:caFile) }
        if response.status==404 { return nil }
        if response.status==304,let stored { return stored }
        guard response.status==200 else { throw OpenTideConstantsError.network("HTTP\(response.status)",["url":.string(url.absoluteString),"status":.integer(Int64(response.status))]) }
        let doc:JSONValue
        do { doc=try JSONValue.parse(response.bytes) }
        catch { throw OpenTideConstantsError.network("HTTP200 pointer is not JSON",["url":.string(url.absoluteString),"status":.integer(200)]) }
        guard pointerShape(name,doc) else { throw OpenTideConstantsError.network("HTTP200 pointer has wrong shape",["url":.string(url.absoluteString),"status":.integer(200)]) }
        do {
            let directory=path.deletingLastPathComponent(),token=try await cache.takeLock(directory)
            defer { cache.releaseLock(directory,token) }
            let tagPath=path.appendingPathExtension("etag")
            if FileManager.default.fileExists(atPath:tagPath.path) { try FileManager.default.removeItem(at:tagPath) }
            try Cache.atomic(response.bytes,path)
            if let etag=response.etag,(1...256).contains(etag.utf8.count),etag.utf8.allSatisfy({ (32...126).contains($0) }) { try Cache.atomic(Data(etag.utf8),path.appendingPathExtension("etag")) }
            else { try? FileManager.default.removeItem(at:path.appendingPathExtension("etag")) }
        } catch { logger?("opentideconstants: cannot cache \(name)") }
        return doc
    }
    func entry(_ value:JSONValue,source:URL)throws->JSONValue {
        guard case .object=value,let stamp=value["datestamp"].string,Cache.validStamp(stamp) else { throw OpenTideConstantsError.invalidRelease("bad pointer datestamp") }
        for key in ["format_version","min_reader_version"] {
            if key=="min_reader_version",value[key].isNull { continue }
            guard let version=value[key].string,version.range(of:#"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"#,options:.regularExpression)?.upperBound==version.endIndex else { throw OpenTideConstantsError.invalidRelease("bad \(key)") }
        }
        var result=value.object,files:[JSONValue]=[],names=Set<String>()
        if !value["files"].isNull { guard case .array=value["files"] else { throw OpenTideConstantsError.invalidRelease("bad pointer files") } }
        for file in value["files"].array {
            guard let name=file["name"].string,!name.contains("/"),!name.contains("\\"),name != ".",name != "..",names.insert(name).inserted,let sha=file["sha256"].string,sha.range(of:#"^[a-fA-F0-9]{64}$"#,options:.regularExpression)?.upperBound==sha.endIndex,let size=file["size"].integer,size>=0,file["url"].isNull || file["url"].string != nil else { throw OpenTideConstantsError.invalidRelease("malformed pointer file") }
            var row=file.object
            if let ref=file["url"].string { guard let url=URL(string:ref,relativeTo:source)?.absoluteURL,["http","https"].contains(url.scheme ?? ""),url.host != nil else { throw OpenTideConstantsError.invalidRelease("bad file URL") };row["url"] = .string(url.absoluteString) }
            row["sha256"] = .string(sha.lowercased());files.append(.object(row))
        }
        result["files"] = .array(files.sorted { $0["name"].string!<$1["name"].string! })
        return .object(result)
    }
    func index()async throws->[JSONValue] {
        guard let doc=try await pointer("OTC_index.json") else { throw OpenTideConstantsError.releaseNotFound("index missing") }
        return try doc["releases"].array.map { try entry($0,source:baseUrl.appendingPathComponent("OTC_index.json")) }.sorted { Cache.newer($0["datestamp"].string!,$1["datestamp"].string!) }
    }
    func readable(_ value:JSONValue)->Bool {
        let format=value["format_version"].string ?? ""
        let version=value["min_reader_version"].string ?? "1.0"
        let parts=version.split(separator:".").compactMap { Int64($0) }
        return format.split(separator:".").first=="1" && parts.count==2 && (parts[0]<1 || parts[0]==1 && parts[1]==0)
    }
    func resolveLatest()async throws->JSONValue {
        guard !offline else { throw OpenTideConstantsError.offlineUnavailable("latest pointer unavailable offline") }
        var latest:JSONValue?
        for name in ["OTC_latest-f1.json","OTC_latest.json"] {
            if let doc=try await pointer(name) { latest=try entry(doc,source:baseUrl.appendingPathComponent(name));break }
        }
        guard let latest else { throw OpenTideConstantsError.releaseNotFound("latest pointer missing") }
        if readable(latest) { return latest }
        let values=try await index()
        if let supported=values.first(where:readable) { return supported }
        if ([latest]+values).contains(where:{ ($0["format_version"].string ?? "").split(separator:".").first=="1" }) { throw OpenTideConstantsError.readerTooOld("no readable release") }
        throw OpenTideConstantsError.unsupportedFormat("no supported format")
    }
    func url(_ name:String,entry:JSONValue?)->URL {
        if let ref=entry?["files"].array.first(where:{ $0["name"].string==name })?["url"].string,let url=URL(string:ref) { return url }
        return baseUrl.appendingPathComponent(name)
    }
    func sha(_ stamp:String,entry:JSONValue?)async throws->([String:String],Data) {
        let name="OTC_\(stamp).sha256",url=url(name,entry:entry)
        let bytes=try await HTTP.get(url,timeout:timeout,userAgent:userAgent,proxy:proxy,caFile:caFile)
        guard String(data:bytes,encoding:.utf8)?.range(of:#"(?m)^\s*[a-fA-F0-9]{64}[ \t]+\*?\S"#,options:.regularExpression) != nil else { throw OpenTideConstantsError.network("HTTP200 checksum body has no checksum row",["url":.string(url.absoluteString),"status":.integer(200)]) }
        if let file=entry?["files"].array.first(where:{ $0["name"].string==name }),let expected=file["sha256"].string,SHA256.digest(bytes) != expected { throw OpenTideConstantsError.checksumMismatch("checksum file differs from pointer",["file":.string(name),"expected":.string(expected),"actual":.string(SHA256.digest(bytes))]) }
        let rows=try Cache.checksums(bytes)
        try agreement(rows,entry:entry,stamp:stamp)
        return (rows,bytes)
    }
    func agreement(_ rows:[String:String],entry:JSONValue?,stamp:String)throws {
        guard let entry,!entry["files"].array.isEmpty else { return }
        let listed=entry["files"].array.filter { $0["name"].string != "OTC_\(stamp).sha256" }
        for file in listed { let name=file["name"].string!;guard rows[name]==file["sha256"].string else { throw OpenTideConstantsError.checksumMismatch("pointer/checksum disagreement",["file":.string(name),"expected":file["sha256"],"actual":rows[name].map(JSONValue.string) ?? .null]) } }
        guard Set(rows.keys)==Set(listed.compactMap { $0["name"].string }) else { throw OpenTideConstantsError.checksumMismatch("checksum lists extra file") }
    }
    func checked(_ stamp:String,name:String,rows:[String:String],entry:JSONValue?,to path:URL)async throws->Int64 {
        guard let expected=rows[name] else { throw OpenTideConstantsError.checksumMismatch("\(name) not listed",["file":.string(name)]) }
        let file=entry?["files"].array.first(where:{ $0["name"].string==name })
        try await HTTP.file(url(name,entry:entry),to:path,timeout:timeout,userAgent:userAgent,proxy:proxy,caFile:caFile)
        let actual=try SHA256.file(path),size=(try FileManager.default.attributesOfItem(atPath:path.path)[.size] as? NSNumber)?.int64Value ?? -1
        guard actual==expected,file?["size"].integer==nil || file?["size"].integer==size else { throw OpenTideConstantsError.checksumMismatch("size or checksum mismatch",["file":.string(name),"expected":.string(expected),"actual":.string(actual)]) }
        return size
    }
    func fetch(_ stamp:String,entry:JSONValue?)async throws->Loaded {
        let directory=try cache.releaseDir(stamp),token=try await cache.takeLock(directory)
        defer { cache.releaseLock(directory,token) }
        if let loaded=try usableCached(stamp) { return loaded }
        let (rows,shaBytes)=try await sha(stamp,entry:entry)
        let json="OTC_\(stamp).json",gz=json+".gz",jsonl="OTC_\(stamp).jsonl",meta="OTC_\(stamp).meta.json"
        let names=mode == .stream ? [jsonl,meta]:[json]
        for name in names { guard rows[name] != nil else { throw OpenTideConstantsError.checksumMismatch("\(name) not listed",["file":.string(name)]) } }
        try Cache.atomic(shaBytes,directory.appendingPathComponent("OTC_\(stamp).sha256"))
        let previous=try cache.verified(stamp)
        var verified:[String:JSONValue]=(previous?["files"].object ?? [:]).filter { name,_ in
            name != "OTC_\(stamp).sha256" && FileManager.default.fileExists(atPath:directory.appendingPathComponent(name).path)
        }.mapValues { row in
            .object(["sha256":.string(row["sha256"].string!.lowercased()),"size":row["size"],"url":row["url"]])
        }
        for name in names {
            let temporary=directory.appendingPathComponent(".tmp-\(UUID().uuidString)")
            defer { try? FileManager.default.removeItem(at:temporary) }
            let size:Int64
            if name==json,rows[gz] != nil {
                let compressed=directory.appendingPathComponent(".tmp-\(UUID().uuidString).gz")
                defer { try? FileManager.default.removeItem(at:compressed) }
                _=try await checked(stamp,name:gz,rows:rows,entry:entry,to:compressed)
                try Cache.gunzip(compressed,to:temporary)
                guard try SHA256.file(temporary)==rows[json] else { throw OpenTideConstantsError.checksumMismatch("decompressed checksum mismatch",["file":.string(json)]) }
                size=(try FileManager.default.attributesOfItem(atPath:temporary.path)[.size] as? NSNumber)?.int64Value ?? -1
            } else { size=try await checked(stamp,name:name,rows:rows,entry:entry,to:temporary) }
            try Cache.install(temporary,directory.appendingPathComponent(name))
            verified[name] = .object(["sha256":.string(rows[name]!),"size":.integer(size),"url":.string(url(name,entry:entry).absoluteString)])
        }
        let doc=try JSONValue.parse(Reader.read(directory.appendingPathComponent(mode == .stream ? meta:json)))
        let doi=entry?["zenodo_version_doi"].string ?? previous?["zenodo_version_doi"].string
        let marker:[String:JSONValue]=["files":.object(verified),"datestamp":.string(stamp),"by":.string("opentideconstants-swift/0.1.0"),"verified_at":.string(ISO8601DateFormatter().string(from:Date())),"format_version":doc["format_version"],"min_reader_version":doc["release"]["min_reader_version"].string.map(JSONValue.string) ?? .string("1.0"),"zenodo_version_doi":doi.map(JSONValue.string) ?? .null]
        try Cache.atomic(JSONValue.object(marker).data(),directory.appendingPathComponent(".verified"))
        guard let loaded=try cached(stamp,files:entry.map { $0["files"].array.map(FileInfo.init) }) else { throw OpenTideConstantsError.cache("download left cache") }
        return Loaded(release:loaded.release,from:.download,paths:loaded.paths)
    }
    func download(_ selected:String,to destination:URL,formats:[Format],overwrite:Bool)async throws->[String] {
        var selectedEntry:JSONValue?
        let stamp:String
        if selected=="latest" {
            if offline {
                guard let newest=try cache.cached().first(where:{ stamp in
                    guard let marker=try cache.verified(stamp) else { return false }
                    return marker["format_version"].isNull || readable(marker)
                }) else { throw OpenTideConstantsError.offlineUnavailable("no readable cached release") }
                stamp=newest
            } else {
                do { let resolved=try await resolveLatest();selectedEntry=resolved;stamp=resolved["datestamp"].string! }
                catch let error as OpenTideConstantsError {
                    guard error.code=="network",onNetworkError == .useCache,let newest=try cache.cached().first else { throw error };stamp=newest
                }
            }
        } else { stamp=selected }
        let directory=try cache.releaseDir(stamp),marker=try cache.verified(stamp),shaName="OTC_\(stamp).sha256"
        let shaPath=directory.appendingPathComponent(shaName)
        var cachedSHA:([String:String],Data)?
        if marker != nil,FileManager.default.fileExists(atPath:shaPath.path) {
            do {
                let bytes=try Reader.read(shaPath),rows=try Cache.checksums(bytes)
                if let row=selectedEntry?["files"].array.first(where:{ $0["name"].string==shaName }),row["sha256"].string != SHA256.digest(bytes) { throw OpenTideConstantsError.checksumMismatch("cached checksum differs from pointer") }
                try agreement(rows,entry:selectedEntry,stamp:stamp);cachedSHA=(rows,bytes)
            } catch { logger?("opentideconstants: cannot use cached checksum") }
        }
        let rows:[String:String],shaBytes:Data
        if let cachedSHA { (rows,shaBytes)=cachedSHA }
        else { guard !offline else { throw OpenTideConstantsError.offlineUnavailable("checksum not cached") };(rows,shaBytes)=try await sha(stamp,entry:selectedEntry) }
        var names:[String]=[]
        for format in [Format.json,.jsonGz,.jsonl] where formats.contains(format) { names.append("OTC_\(stamp).\(format.rawValue)") }
        names.append("OTC_\(stamp).meta.json")
        for name in names where rows[name]==nil {
            if name=="OTC_\(stamp).json" { throw OpenTideConstantsError.checksumMismatch("\(name) not listed",["file":.string(name)]) }
            throw OpenTideConstantsError.releaseNotFound("\(name) not published")
        }
        names.append(shaName)
        do { try FileManager.default.createDirectory(at:destination,withIntermediateDirectories:true) }
        catch { throw OpenTideConstantsError.io("cannot create \(destination.path)",["path":.string(destination.path)]) }
        var todo:[String]=[]
        for name in names {
            let path=destination.appendingPathComponent(name),expected=name==shaName ? SHA256.digest(shaBytes):rows[name]!
            if FileManager.default.fileExists(atPath:path.path) {
                if try SHA256.file(path)==expected { continue }
                guard overwrite else { throw OpenTideConstantsError.fileExists("file exists with different content",["path":.string(path.path)]) }
            }
            todo.append(name)
        }
        var staged:[(URL,URL)]=[]
        defer { for (temporary,_) in staged { try? FileManager.default.removeItem(at:temporary) } }
        for name in todo {
            let temporary=destination.appendingPathComponent(".tmp-\(UUID().uuidString)"),final=destination.appendingPathComponent(name)
            staged.append((temporary,final))
            do {
                if name==shaName { try shaBytes.write(to:temporary) }
                else {
                    let source=directory.appendingPathComponent(name)
                    if let row=marker?["files"][name],try cache.fileOK(stamp,name,row),row["sha256"].string==rows[name],try SHA256.file(source)==rows[name] {
                        try FileManager.default.copyItem(at:source,to:temporary)
                    } else {
                        guard !offline else { throw OpenTideConstantsError.offlineUnavailable("\(name) is not cached") }
                        _=try await checked(stamp,name:name,rows:rows,entry:selectedEntry,to:temporary)
                    }
                }
                let handle=try FileHandle(forWritingTo:temporary);defer { try? handle.close() };try handle.synchronize()
            } catch let error as OpenTideConstantsError { throw error }
            catch { throw OpenTideConstantsError.io("cannot stage \(final.path)",["path":.string(final.path)]) }
        }
        var backups:[(URL,URL)]=[],placed:[URL]=[]
        do {
            for (_,final) in staged where FileManager.default.fileExists(atPath:final.path) {
                let backup=destination.appendingPathComponent(".tmp-bak-\(UUID().uuidString)")
                try FileManager.default.moveItem(at:final,to:backup);backups.append((backup,final))
            }
            for (temporary,final) in staged { try FileManager.default.moveItem(at:temporary,to:final);placed.append(final) }
        } catch {
            var changed:[String]=[]
            for path in placed.reversed() { do { try FileManager.default.removeItem(at:path) } catch { changed.append(path.path) } }
            for (backup,path) in backups { do { try FileManager.default.moveItem(at:backup,to:path) } catch { changed.append(path.path) } }
            throw OpenTideConstantsError.io("cannot install download",["changed":.array(changed.map(JSONValue.string))])
        }
        for (backup,_) in backups { do { try FileManager.default.removeItem(at:backup) } catch { logger?("opentideconstants: cannot remove replaced download backup") } }
        return staged.map { $0.1.path }
    }
}
