import Foundation

public final class Release {
    private let originToken=UUID()
    internal let meta:JSONValue
    internal let commercialOnly:Bool
    internal let commercialBasis:String
    public let historicalOffsetsPolicy:String
    internal let convById:[String:Convention]
    internal let licById:[String:Licence]
    internal var entries:[IndexEntry]
    internal var byId:[String:IndexEntry]=[:]
    internal var documents:[String:JSONValue]
    internal let jsonl:URL?
    internal let indexPath:URL?
    private var reader:FileHandle?
    internal var astroCache:[String:AstroTable]=[:]
    internal var closed=false
    internal var lru:[String:Station]=[:]
    internal var lruOrder:[String]=[]
    public let files:[FileInfo]
    public var datestamp:String { meta["release"]["datestamp"].string! }
    public var created:Date? { try? parseTime(meta["release"]["created"].string) }
    public var formatVersion:String { meta["format_version"].string! }
    public var conceptDoi:String? { meta["release"]["concept_doi"].string }
    public internal(set) var zenodoVersionDoi:String?
    public var sourceVersions:[String:String] { meta["release"]["source_versions"].object.compactMapValues(\.string) }
    public var buildCommit:String? { meta["release"]["build_commit"].string }
    public var changelogUrl:String? { meta["release"]["changelog_url"].string }
    public var citation:String {
        let link=conceptDoi.flatMap { $0.isEmpty ? nil : "https://doi.org/\($0)" } ?? "https://data.opentideconstants.org/OTC_\(datestamp).json"
        let version=zenodoVersionDoi.flatMap { $0.isEmpty ? nil : " (version DOI: https://doi.org/\($0))" } ?? ""
        return "OpenTideConstants contributors (\(datestamp.prefix(4))). OpenTideConstants, release \(datestamp) [Data set]. \(link)\(version)"
    }
    internal init(meta:JSONValue,entries:[IndexEntry],documents:[String:JSONValue],jsonl:URL?,indexPath:URL?,files:[FileInfo],commercialOnly:Bool,commercialBasis:String,historicalOffsetsPolicy:String)throws {
        self.meta=meta;self.entries=entries;self.documents=documents;self.jsonl=jsonl;self.indexPath=indexPath;self.files=files;self.commercialOnly=commercialOnly;self.commercialBasis=commercialBasis;self.historicalOffsetsPolicy=historicalOffsetsPolicy
        guard ["strict","as_published_upstream"].contains(commercialBasis),["fallback","exclude"].contains(historicalOffsetsPolicy) else { throw OpenTideConstantsError.invalidArgument("invalid policy") }
        guard let stamp=meta["release"]["datestamp"].string,Cache.validStamp(stamp) else { throw OpenTideConstantsError.invalidRelease("invalid datestamp") }
        _ = try parseTime(meta["release"]["created"].string)
        guard meta["release"]["source_versions"].object.values.allSatisfy({ $0.string != nil }) else { throw OpenTideConstantsError.invalidRelease("source_versions wrong type") }
        var conv:[String:Convention]=[:],lic:[String:Licence]=[:]
        for row in meta["conventions"].array { guard let id=row["convention_id"].string,conv[id]==nil else { throw OpenTideConstantsError.invalidRelease("duplicate/missing convention") };conv[id]=Convention(row) }
        for row in meta["licences"].array { let l=try Reader.licence(row);guard lic[l.licenceId]==nil else { throw OpenTideConstantsError.invalidRelease("duplicate licence") };lic[l.licenceId]=l }
        convById=conv;licById=lic
        var seen:Set<String>=[],sets:Set<String>=[],aliases:Set<String>=[]
        for e in entries {
            guard seen.insert(e.id).inserted else { throw OpenTideConstantsError.invalidRelease("duplicate station id") }
            if e.status != "active" { continue }
            for cs in e.sets { guard let id=cs["set_id"].string,sets.insert(id).inserted,conv[cs["convention_id"].string ?? ""] != nil,lic[cs["licence_id"].string ?? ""] != nil else { throw OpenTideConstantsError.invalidRelease("set identity/reference invalid") } }
            for (sys,ids) in e.summary["aliases"].object { for alias in ids.array { guard let v=alias.string,aliases.insert(sys+"\u{0000}"+v).inserted else { throw OpenTideConstantsError.invalidRelease("duplicate alias") } } }
        }
        let active=Dictionary(uniqueKeysWithValues:entries.filter { $0.status=="active" }.map { ($0.id,$0) })
        for e in entries where e.status=="active" { if let ref=e.summary["reference_station_id"].string,active[ref]==nil { throw OpenTideConstantsError.invalidRelease("unresolved reference station") } }
        func resolve(_ e:IndexEntry,_ visited:Set<String>,_ depth:Int)->Kind? {
            if let k=e.kind { return k }
            guard depth<16,e.summary["type"].string=="subordinate",let id=e.summary["reference_station_id"].string,!visited.contains(id),let ref=active[id] else { return nil }
            return resolve(ref,visited.union([e.id]),depth+1)
        }
        self.entries=entries.map { e in var e=e;var s=e.summary.object;s["kind"]=resolve(e,[],0).map { .string($0.rawValue) } ?? .null;e.summary = .object(s);return e }.sorted { $0.id<$1.id }
        byId=Dictionary(uniqueKeysWithValues:self.entries.map { ($0.id,$0) })
        if let jsonl { reader=try FileHandle(forReadingFrom:jsonl) }
    }
    internal func checkOpen()throws { if closed { throw OpenTideConstantsError.io("the release is closed") } }
    public var conventions:[Convention] { get throws { try checkOpen();return meta["conventions"].array.map(Convention.init) } }
    public var licences:[Licence] { get throws { try checkOpen();return meta["licences"].array.compactMap { licById[$0["licence_id"].string ?? ""] } } }
    public func convention(conventionId:String)throws->Convention? { try checkOpen();return convById[conventionId] }
    public func licence(licenceId:String)throws->Licence? { try checkOpen();return licById[licenceId] }
    public var stationCount:Int { get throws { try checkOpen();return entries.filter { $0.status=="active" }.count } }
    public var tombstoneCount:Int { get throws { try checkOpen();return entries.filter { $0.status=="removed" }.count } }
    public var constituentNames:[String] { get throws { try checkOpen();return Set(entries.flatMap { $0.sets.flatMap { $0["constituents"].array.compactMap(\.string) } }).sorted() } }
    public var stats:Stats { get throws {
        try checkOpen();var type:[String:Int64]=[:],kind:[String:Int64]=[:],country:[String:Int64]=[:],source:[String:Int64]=[:],qc:[String:Int64]=[:]
        for e in entries where e.status=="active" {
            type[StationType(value:e.summary["type"]).rawValue,default:0]+=1
            if let k=e.kind { kind[k.rawValue,default:0]+=1 };if let c=e.summary["country"].string { country[c,default:0]+=1 }
            for cs in e.sets { let status=QcStatus(value:cs["qc_status"]);if [.ok,.flagged].contains(status),let s=cs["source"].string { source[s,default:0]+=1 };qc[status.rawValue,default:0]+=1 }
        }
        return Stats(type:type,kind:kind,country:country,source:source,qcStatus:qc)
    } }
    internal func effective(_ e:IndexEntry)->String? {
        guard let rid=e.summary["recommended_set_id"].string,let rec=e.sets.first(where: { $0["set_id"].string==rid }) else { return nil }
        if !commercialOnly || licById[rec["licence_id"].string ?? ""]?.commercialUse==true { return rid }
        guard !rec["quantity"].isNull else { return nil }
        let q=Quantity(value:rec["quantity"])
        for status in ["ok","flagged"] { if let cs=e.sets.first(where: { $0["qc_status"].string==status && !$0["quantity"].isNull && Quantity(value:$0["quantity"])==q && licById[$0["licence_id"].string ?? ""]?.commercialUse==true }) { return cs["set_id"].string } }
        return nil
    }
    internal func rawStation(_ e:IndexEntry)throws->JSONValue {
        if let d=documents[e.id] { return d }
        guard let reader,let offset=e.offset,let length=e.length else { throw OpenTideConstantsError.invalidRelease("no station data") }
        do {
            try reader.seek(toOffset:offset)
            guard let bytes=try reader.read(upToCount:length),bytes.count==length else { throw OpenTideConstantsError.invalidRelease("short indexed line") }
            let d=try JSONValue.parse(bytes)
            try compare_station_source(e,d)
            return d
        } catch {
            if let indexPath { try? FileManager.default.removeItem(at:indexPath) }
            throw error
        }
    }
    internal func compare_station_source(_ e:IndexEntry,_ d:JSONValue)throws {
        var actual=IndexEntry.make(d,offset:e.offset,length:e.length).summary.object
        if actual["kind"]?.isNull==true,actual["type"]?.string=="subordinate",let ref=actual["reference_station_id"]?.string { actual["kind"]=byId[ref]?.summary["kind"] ?? .null }
        func require(_ ok:Bool)throws { if !ok { throw OpenTideConstantsError.invalidRelease("index-v1.json does not match release") } }
        let common=["station_id","status","name","name_folded","country","type","lat","lon","kind","aliases","reference_station_id","offsets_licence_id","recommended_set_id"]
        try require(common.allSatisfy { indexValueMatches(e.summary[$0],actual[$0]!) })
        let sourceSets=d["constant_sets"].array,projected=actual["sets"]!.array
        try require(e.sets.count==projected.count)
        for (index,set) in e.sets.enumerated() {
            let common=["set_id","source","source_type","quantity","qc_status","convention_id","licence_id","constituents"]
            try require(common.allSatisfy { indexValueMatches(set[$0],projected[index][$0]) })
            for key in ["fallback","current_bins"] {
                if set.object.keys.contains(key) { try require(indexValueMatches(set[key],projected[index][key])) }
                else if key=="fallback",e.presence?.fallback==true { try require(projected[index][key].isNull) }
            }
            if e.presence?.privateFields==true {
                for key in ["source_record_id","source_version","datum"] { try require(indexValueMatches(set[key],sourceSets[index][key])) }
            }
        }
        if e.summary.object.keys.contains("subordinate_offsets") { try require(indexValueMatches(e.summary["subordinate_offsets"],actual["subordinate_offsets"]!)) }
        else if e.presence?.subordinateOffsets==true { try require(actual["subordinate_offsets"]!.isNull) }
        if e.summary.object.keys.contains("current_offsets") {
            let offsets=e.summary["current_offsets"].array,source=d["current_offsets"].array
            try require(offsets.count==source.count)
            let keys=["bin","reference_bin","reference_station_id","licence_id"] + (e.presence?.fullCurrentOffsets==true ? ["time_adj_max_flood_min","time_adj_max_ebb_min","time_adj_slack_before_flood_min","time_adj_slack_before_ebb_min","flood_amp_ratio","ebb_amp_ratio"]:[])
            for (index,row) in offsets.enumerated() { try require(keys.allSatisfy { indexValueMatches(row[$0],source[index][$0]) }) }
        } else { try require(d["current_offsets"].array.isEmpty) }
    }
    internal func hydratePolicy(stationId:String?=nil)throws {
        for index in entries.indices {
            let e=entries[index]
            guard e.status=="active",stationId==nil || stationId==e.id else { continue }
            let missing=e.presence != nil && (!e.summary.object.keys.contains("subordinate_offsets") || !e.summary.object.keys.contains("current_offsets") || e.sets.contains { !$0.object.keys.contains("fallback") || !$0.object.keys.contains("current_bins") })
            guard missing else { continue }
            let row=try rawStation(e)
            _ = try Reader.station(row,conventions:convById,licences:licById,kind:e.kind,recommended:e.summary["recommended_set_id"].string)
            var full=IndexEntry.make(row,offset:e.offset,length:e.length)
            var summary=full.summary.object;summary["kind"]=e.summary["kind"];full.summary = .object(summary)
            entries[index]=full;byId[e.id]=full
        }
    }
    public func station(stationId:String)throws->Station? {
        try checkOpen();try hydratePolicy(stationId:stationId)
        try checkOpen();guard let e=byId[stationId],e.status=="active" else { return nil }
        if let s=lru[stationId] { lruOrder.removeAll { $0==stationId };lruOrder.append(stationId);return s }
        let s=try autoreleasepool { try Reader.station(rawStation(e),conventions:convById,licences:licById,kind:e.kind,recommended:effective(e)).withOrigin(originToken) }
        lru[stationId]=s;lruOrder.append(stationId);if lruOrder.count>256 { lru.removeValue(forKey:lruOrder.removeFirst()) };return s
    }
    public func requireStation(stationId:String)throws->Station {
        if let s=try station(stationId:stationId) { return s }
        if let t=try tombstone(stationId:stationId) { throw OpenTideConstantsError.stationRemoved("station removed",["tombstone":t.raw]) }
        throw OpenTideConstantsError.stationNotFound("no station \(stationId)")
    }
    public func tombstone(stationId:String)throws->Tombstone? { try checkOpen();guard let e=byId[stationId],e.status=="removed" else { return nil };return Tombstone(try rawStation(e)) }
    public func stationByAlias(system:String,aliasId:String)throws->Station? { try checkOpen();guard let e=entries.first(where: { $0.status=="active" && $0.summary["aliases"][system].array.contains(.string(aliasId)) }) else { return nil };return try station(stationId:e.id) }
    internal func eligible(_ cs:JSONValue,flagged:Bool,fallback:Bool,offsetLicence:String?=nil)->Bool {
        guard ["ok","flagged"].contains(cs["qc_status"].string ?? "") else { return false }
        if !cs["fallback"].isNull { if !fallback { return false } } else if cs["qc_status"].string != "ok" && !flagged { return false }
        if let id=offsetLicence,licById[id]==nil { return false }
        if !commercialOnly { return true }
        if commercialBasis=="strict" && cs["fallback"]["reason"].string=="licence_reading" { return false }
        return licById[cs["licence_id"].string ?? ""]?.commercialUse==true && (offsetLicence==nil || licById[offsetLicence!]?.commercialUse==true)
    }
    internal func paths(_ e:IndexEntry,flagged:Bool,fallback:Bool,historical:Bool=true)->[JSONValue] {
        var out=e.sets.filter { eligible($0,flagged:flagged,fallback:fallback) };let off=e.summary["subordinate_offsets"]
        if off["offset_id"].string != nil {
            if historical && historicalEligible(e) { var x=off.object;x["quantity"] = .string("water_level");out.append(.object(x)) }
        } else if let ref=byId[e.summary["reference_station_id"].string ?? ""],let cs=ref.sets.first(where: { $0["source"].string=="noaa" && ["ok","flagged"].contains($0["qc_status"].string ?? "") && $0["quantity"].string=="water_level" }),eligible(cs,flagged:flagged,fallback:fallback,offsetLicence:e.summary["offsets_licence_id"].string) { out.append(cs) }
        for co in e.summary["current_offsets"].array {
            guard let n=co["reference_bin"].integer,n>=1,n<=9007199254740991,let own=co["bin"].integer,own>=1,own<=9007199254740991,let ref=byId[co["reference_station_id"].string ?? ""],let cs=ref.sets.first(where: { ["ok","flagged"].contains($0["qc_status"].string ?? "") && $0["quantity"].string=="current" && $0["current_bins"].array.contains(where: { $0.integer==n }) }),eligible(cs,flagged:flagged,fallback:fallback,offsetLicence:co["licence_id"].string) else { continue };out.append(cs)
        }
        return out
    }
internal func betterHistoricalPath(_ e:IndexEntry)->Bool {
    if let rid=effective(e),e.sets.contains(where: { $0["set_id"].string==rid && ["ok","flagged"].contains($0["qc_status"].string ?? "") }) { return true }
    return !paths(e,flagged:false,fallback:false,historical:false).isEmpty
}
internal func historicalEligible(_ e:IndexEntry)->Bool {
        guard historicalOffsetsPolicy=="fallback",let ref=byId[e.summary["reference_station_id"].string ?? ""] else { return false }
        if let rid=effective(e),e.sets.contains(where: { $0["set_id"].string==rid && ["ok","flagged"].contains($0["qc_status"].string ?? "") }) { return false }
        if !paths(e,flagged:false,fallback:false,historical:false).isEmpty { return false }
        let own=e.summary["subordinate_offsets"]
        guard let cs=ref.sets.first(where: { $0["source"].string=="noaa" && $0["quantity"].string=="water_level" && ["ok","flagged"].contains($0["qc_status"].string ?? "") }),cs["qc_status"].string=="ok",cs["fallback"].isNull else { return false }
        if commercialOnly && (licById[own["licence_id"].string ?? ""]?.commercialUse != true || licById[cs["licence_id"].string ?? ""]?.commercialUse != true) { return false }
        guard let doc=try? rawStation(ref),let selectedId=cs["set_id"].string,let full=doc["constant_sets"].array.first(where: { $0["set_id"].string==selectedId }),let conv=convById[full["convention_id"].string ?? ""],let lic=licById[full["licence_id"].string ?? ""] else { return false }
        let constants=ConstantSet(raw:full,convention:conv,licence:lic,isRecommended:effective(ref)==selectedId,validation:doc["validation"].array.map(Validation.init).filter { $0.setId==selectedId }.sorted { $0.window < $1.window })
        guard (try? Predict.historicalReferenceTable(self,constants:constants)) != nil else { return false }
        let datum=full["datum"]
        return full["set_id"].string?.hasPrefix(ref.id+"/")==true && full["source_record_id"]==own["provenance"]["reference_binding"]["noaa_id"] && datum["chart_datum"].string=="mllw" && datum["msl_offset_m"].number != nil && datum["named"]["mllw"].number==0 && datum["basis"]["mllw"]["kind"].string=="published"
    }
internal func filteredEntries(country:String?=nil,type:String?=nil,kind:String?=nil,source:String?=nil,sourceType:String?=nil,includeFlagged:Bool=false,includeFallback:Bool=false)throws->[IndexEntry] {
    try checkOpen()
    try hydratePolicy()
    return entries.filter { e in
        e.status=="active" && (country==nil || e.summary["country"].string==country) && (type==nil || StationType(value:e.summary["type"]).rawValue==type) && (kind==nil || e.kind?.rawValue==kind) && paths(e,flagged:includeFlagged,fallback:includeFallback).contains { (source==nil || $0["source"].string==source) && (sourceType==nil || SourceType(value:$0["source_type"]).rawValue==sourceType) }
    }
}
public func stations(country:String?=nil,type:String?=nil,kind:String?=nil,source:String?=nil,sourceType:String?=nil,includeFlagged:Bool=false,includeFallback:Bool=false)throws->[Station] {
    try filteredEntries(country:country,type:type,kind:kind,source:source,sourceType:sourceType,includeFlagged:includeFlagged,includeFallback:includeFallback).map { try requireStation(stationId:$0.id) }
}
public func iterStations(country:String?=nil,type:String?=nil,kind:String?=nil,source:String?=nil,sourceType:String?=nil,includeFlagged:Bool=false,includeFallback:Bool=false)throws->(()throws->Station?) {
    let selected=try filteredEntries(country:country,type:type,kind:kind,source:source,sourceType:sourceType,includeFlagged:includeFlagged,includeFallback:includeFallback)
    var i=0
    return {
        try self.checkOpen()
        guard i<selected.count else { return nil }
        let station=try self.requireStation(stationId:selected[i].id)
        i+=1
        return station
    }
}
public func search(name:String,limit:Int64?=nil,match:String?=nil,country:String?=nil,type:String?=nil,kind:String?=nil,source:String?=nil,sourceType:String?=nil,includeFlagged:Bool=false,includeFallback:Bool=false)throws->[Station] {
    let q=NameFold.fold(name)
    guard !q.isEmpty,(limit==nil || limit!>0),(match==nil || match=="exact") else { throw OpenTideConstantsError.invalidArgument("invalid query/limit/match") }
    func rank(_ e:IndexEntry)->Int { let n=e.summary["name_folded"].string ?? "";if n==q{return 0};if match != nil{return 4};if n.hasPrefix(q){return 1};if n.contains(" "+q){return 2};return n.contains(q) ? 3:4 }
    let selected=try filteredEntries(country:country,type:type,kind:kind,source:source,sourceType:sourceType,includeFlagged:includeFlagged,includeFallback:includeFallback).filter { rank($0)<4 }.sorted { (rank($0),$0.summary["name_folded"].string ?? "",$0.id)<(rank($1),$1.summary["name_folded"].string ?? "",$1.id) }
    let limited=limit.map { Array(selected.prefix(Int($0))) } ?? selected
    return try limited.map { try requireStation(stationId:$0.id) }
}
internal func distances(lat:Double,lon:Double,radiusKm:Double,country:String?,type:String?,kind:String?,source:String?,sourceType:String?,includeFlagged:Bool,includeFallback:Bool)throws->[(Double,IndexEntry)] {
    let selected=try filteredEntries(country:country,type:type,kind:kind,source:source,sourceType:sourceType,includeFlagged:includeFlagged,includeFallback:includeFallback)
    return selected.compactMap { e -> (Double,IndexEntry)? in
        guard let elat=e.summary["lat"].number,let elon=e.summary["lon"].number else { return nil }
        let p=lat*Double.pi/180,p2=elat*Double.pi/180,dl=(elon-lon)*Double.pi/180
        let a=pow(sin((p2-p)/2),2)+cos(p)*cos(p2)*pow(sin(dl/2),2)
        let distance=2*6371.0088*asin(min(1,sqrt(a)))
        return distance<=radiusKm ? (distance,e):nil
    }.sorted { ($0.0,$0.1.id)<($1.0,$1.1.id) }
}
public func near(lat:Double,lon:Double,radiusKm:Double,limit:Int64?=nil,country:String?=nil,type:String?=nil,kind:String?=nil,source:String?=nil,sourceType:String?=nil,includeFlagged:Bool=false,includeFallback:Bool=false)throws->[Nearby] {
    guard lat.isFinite,lon.isFinite,abs(lat)<=90,abs(lon)<=180,radiusKm>=0,!radiusKm.isNaN,(limit==nil || limit!>0) else { throw OpenTideConstantsError.invalidArgument("invalid geometry/limit") }
    let selected=try distances(lat:lat,lon:lon,radiusKm:radiusKm,country:country,type:type,kind:kind,source:source,sourceType:sourceType,includeFlagged:includeFlagged,includeFallback:includeFallback)
    let limited=limit.map { Array(selected.prefix(Int($0))) } ?? selected
    return try limited.map { Nearby(station:try requireStation(stationId:$0.1.id),distanceKm:$0.0) }
}
public func nearest(lat:Double,lon:Double,maxKm:Double?=nil,country:String?=nil,type:String?=nil,kind:String?=nil,source:String?=nil,sourceType:String?=nil,includeFlagged:Bool=false,includeFallback:Bool=false)throws->Nearby? {
    try near(lat:lat,lon:lon,radiusKm:maxKm ?? .infinity,limit:1,country:country,type:type,kind:kind,source:source,sourceType:sourceType,includeFlagged:includeFlagged,includeFallback:includeFallback).first
}
    internal func own(_ s:Station)throws { try checkOpen();guard s.hasOrigin(originToken),let actual=try station(stationId:s.stationId),actual.raw==s.raw else { throw OpenTideConstantsError.invalidArgument("foreign station") } }
    public func referenceStation(station:Station)throws->Station? { try checkOpen();try own(station);guard station.isSubordinate,let id=station.subordinateOffsets?.referenceStationId else { return nil };return try self.station(stationId:id) }
    public func subordinatesOf(station:Station)throws->[Station] { try checkOpen();try own(station);return try entries.filter { $0.status=="active" && $0.summary["type"].string=="subordinate" && $0.summary["reference_station_id"].string==station.stationId }.map { try requireStation(stationId:$0.id) } }
    private func tideSourceLicences(_ entry:IndexEntry)->[String] {
        if let setId=effective(entry),let selected=entry.sets.first(where: { $0["set_id"].string==setId }),let id=selected["licence_id"].string { return [id] }
        guard let reference=byId[entry.summary["reference_station_id"].string ?? ""],let selected=reference.sets.first(where: { $0["source"].string=="noaa" && $0["quantity"].string=="water_level" && ["ok","flagged"].contains($0["qc_status"].string ?? "") }),let id=selected["licence_id"].string else { return [] }
        var ids=[id]
        if let offsetsId=entry.summary["offsets_licence_id"].string { ids.append(offsetsId) }
        return ids.allSatisfy { licById[$0]?.commercialUse==true } ? ids : []
    }
    public func attribution(stations:[Station]?=nil)throws->String {
        try checkOpen();var ids=Set<String>()
        if stations?.isEmpty != false { ids=Set(licById.values.filter { !commercialOnly || $0.commercialUse }.map(\.licenceId)) }
        else { for s in stations! { try own(s);if commercialOnly { ids.formUnion(tideSourceLicences(byId[s.stationId]!));continue };if let rec=s.recommendedSet { ids.insert(rec.licence.licenceId) };var entry=byId[s.stationId]!,seen=Set<String>();for _ in 0..<16 { guard seen.insert(entry.id).inserted else { break };if let id=entry.summary["offsets_licence_id"].string { ids.insert(id) };guard let ref=byId[entry.summary["reference_station_id"].string ?? ""] else { break };if let rid=effective(ref),let cs=ref.sets.first(where: { $0["set_id"].string==rid }),let id=cs["licence_id"].string { ids.insert(id);break };entry=ref } } }
        if commercialOnly { ids=Set(ids.filter { licById[$0]?.commercialUse==true }) }
        var seen=Set<String>(),parts:[String]=[]
        for id in ids.sorted() { let l=licById[id]!;if let p=l.raw["provider"].string { if seen.insert(p).inserted { parts.append("\(p): \(l.attribution)") } } else { parts.append(l.attribution) } }
        let ident=conceptDoi.map { "doi:\($0)" } ?? "https://data.opentideconstants.org/OTC_\(datestamp).json"
        var text="Tidal constants: OpenTideConstants \(datestamp), \(ident), CC BY 4.0."
        if !parts.isEmpty { text += " Sources: "+parts.joined(separator:"; ") }
        let nc=ids.sorted().compactMap { licById[$0] }.filter { !$0.commercialUse }
        if !nc.isEmpty { text += ". Non-commercial use only: "+nc.map { "\($0.raw["provider"].string ?? $0.licenceId) (\($0.spdx), \($0.termsUrl ?? ""))" }.joined(separator:"; ") }
        return text
    }
    internal func close() { closed=true;try? reader?.close();reader=nil;lru.removeAll();lruOrder.removeAll() }
    deinit { try? reader?.close() }
}

public extension Release {
    func heights(station: Station, start: Date, stop: Date, stepS: Int64 = 600, datum: String? = nil, setId: String? = nil, offsetId: String? = nil) throws -> HeightSeries {
        try checkOpen()
        let (a, b) = try Predict.window(start, stop, stepS: stepS)
        let context = try Predict.context(self, supplied: station, quantity: .waterLevel, setId: setId, datum: datum, series: true, offsetId: offsetId)
        var items: [HeightPoint] = []
        var time = a
        while time < b {
            items.append(HeightPoint(time: Date(timeIntervalSince1970: time), heightM: try context.total!.value(time)))
            time += Double(stepS)
        }
        return Predict.heightSeries(self, context: context, items: items, datum: datum)
    }
    func heights(stationId: String, start: Date, stop: Date, stepS: Int64 = 600, datum: String? = nil, setId: String? = nil, offsetId: String? = nil) throws -> HeightSeries {
        try checkOpen()
        let (a, b) = try Predict.window(start, stop, stepS: stepS)
        let selectedStation = try requireStation(stationId: stationId)
        let context = try Predict.context(self, supplied: selectedStation, quantity: .waterLevel, setId: setId, datum: datum, series: true, offsetId: offsetId)
        var items: [HeightPoint] = []
        var time = a
        while time < b {
            items.append(HeightPoint(time: Date(timeIntervalSince1970: time), heightM: try context.total!.value(time)))
            time += Double(stepS)
        }
        return Predict.heightSeries(self, context: context, items: items, datum: datum)
    }
    func heightsAt(station: Station, times: [Date], datum: String? = nil, setId: String? = nil, offsetId: String? = nil) throws -> HeightSeries {
        try checkOpen()
        let seconds = try times.map(predictionInstant)
        let context = try Predict.context(self, supplied: station, quantity: .waterLevel, setId: setId, datum: datum, series: true, offsetId: offsetId)
        let items = try seconds.map { HeightPoint(time: Date(timeIntervalSince1970: $0), heightM: try context.total!.value($0)) }
        return Predict.heightSeries(self, context: context, items: items, datum: datum)
    }
    func heightsAt(stationId: String, times: [Date], datum: String? = nil, setId: String? = nil, offsetId: String? = nil) throws -> HeightSeries {
        try checkOpen()
        let seconds = try times.map(predictionInstant)
        let selectedStation = try requireStation(stationId: stationId)
        let context = try Predict.context(self, supplied: selectedStation, quantity: .waterLevel, setId: setId, datum: datum, series: true, offsetId: offsetId)
        let items = try seconds.map { HeightPoint(time: Date(timeIntervalSince1970: $0), heightM: try context.total!.value($0)) }
        return Predict.heightSeries(self, context: context, items: items, datum: datum)
    }
    func extremes(station: Station, start: Date, stop: Date, datum: String? = nil, setId: String? = nil, offsetId: String? = nil) throws -> ExtremeList {
        try checkOpen()
        let (a, b) = try Predict.window(start, stop)
        let context = try Predict.context(self, supplied: station, quantity: .waterLevel, setId: setId, datum: datum, offsetId: offsetId)
        return try Predict.extremes(self, context: context, start: a, stop: b, datum: datum)
    }
    func extremes(stationId: String, start: Date, stop: Date, datum: String? = nil, setId: String? = nil, offsetId: String? = nil) throws -> ExtremeList {
        try checkOpen()
        let (a, b) = try Predict.window(start, stop)
        let selectedStation = try requireStation(stationId: stationId)
        let context = try Predict.context(self, supplied: selectedStation, quantity: .waterLevel, setId: setId, datum: datum, offsetId: offsetId)
        return try Predict.extremes(self, context: context, start: a, stop: b, datum: datum)
    }
    func currents(station: Station, start: Date, stop: Date, stepS: Int64 = 600, binNumber: Int64? = nil, setId: String? = nil) throws -> CurrentSeries {
        try checkOpen()
        let (a, b) = try Predict.window(start, stop, stepS: stepS)
        let context = try Predict.context(self, supplied: station, quantity: .current, setId: setId, binNumber: binNumber, series: true)
        return try Predict.currents(self, context: context, start: a, stop: b, stepS: stepS)
    }
    func currents(stationId: String, start: Date, stop: Date, stepS: Int64 = 600, binNumber: Int64? = nil, setId: String? = nil) throws -> CurrentSeries {
        try checkOpen()
        let (a, b) = try Predict.window(start, stop, stepS: stepS)
        let selectedStation = try requireStation(stationId: stationId)
        let context = try Predict.context(self, supplied: selectedStation, quantity: .current, setId: setId, binNumber: binNumber, series: true)
        return try Predict.currents(self, context: context, start: a, stop: b, stepS: stepS)
    }
    func currentEvents(station: Station, start: Date, stop: Date, binNumber: Int64? = nil, setId: String? = nil) throws -> CurrentEventList {
        try checkOpen()
        let (a, b) = try Predict.window(start, stop)
        let context = try Predict.context(self, supplied: station, quantity: .current, setId: setId, binNumber: binNumber)
        return try Predict.currentEvents(self, context: context, start: a, stop: b)
    }
    func currentEvents(stationId: String, start: Date, stop: Date, binNumber: Int64? = nil, setId: String? = nil) throws -> CurrentEventList {
        try checkOpen()
        let (a, b) = try Predict.window(start, stop)
        let selectedStation = try requireStation(stationId: stationId)
        let context = try Predict.context(self, supplied: selectedStation, quantity: .current, setId: setId, binNumber: binNumber)
        return try Predict.currentEvents(self, context: context, start: a, stop: b)
    }
    func datums(station: Station, setId: String? = nil, allSets: Bool = false) throws -> DatumsResult {
        try checkOpen()
        try own(station)
        let actual = try requireStation(stationId: station.stationId)
        if allSets { return .all(actual.constantSets(includeNoConstants: true).map { Predict.datumInfo(setId: $0.setId, raw: $0.raw["datum"]) }) }
        if let constants = try Predict.chosen(self, station: actual, setId: setId) { return .one(Predict.datumInfo(setId: constants.setId, raw: constants.raw["datum"])) }
        let offsets = actual.raw["subordinate_offsets"]
        return .one(offsets.isNull ? nil : Predict.datumInfo(setId: nil, raw: offsets["datum"]))
    }
    func datums(stationId: String, setId: String? = nil, allSets: Bool = false) throws -> DatumsResult {
        try checkOpen()
        let selectedStation = try requireStation(stationId: stationId)
        try own(selectedStation)
        let actual = try requireStation(stationId: selectedStation.stationId)
        if allSets { return .all(actual.constantSets(includeNoConstants: true).map { Predict.datumInfo(setId: $0.setId, raw: $0.raw["datum"]) }) }
        if let constants = try Predict.chosen(self, station: actual, setId: setId) { return .one(Predict.datumInfo(setId: constants.setId, raw: constants.raw["datum"])) }
        let offsets = actual.raw["subordinate_offsets"]
        return .one(offsets.isNull ? nil : Predict.datumInfo(setId: nil, raw: offsets["datum"]))
    }
    func ranges(station: Station, setId: String? = nil) throws -> Ranges {
        try checkOpen()
        let result = try datums(station: station, setId: setId)
        guard case .one(let info) = result else { return Ranges(mn: nil, gt: nil, dhq: nil, dlq: nil) }
        return Predict.ranges(info)
    }
    func ranges(stationId: String, setId: String? = nil) throws -> Ranges {
        try checkOpen()
        let selectedStation = try requireStation(stationId: stationId)
        let result = try datums(station: selectedStation, setId: setId)
        guard case .one(let info) = result else { return Ranges(mn: nil, gt: nil, dhq: nil, dlq: nil) }
        return Predict.ranges(info)
    }
    func astroTable(id: String? = nil) throws -> AstroTable? {
        try checkOpen()
        let selected = id ?? meta["conventions"].array.compactMap { $0["astro_table_id"].string }.first
        guard let selected else { return nil }
        if let cached = astroCache[selected] { return cached }
        guard let raw = meta["astro_tables"].array.first(where: { $0["astro_table_id"].string == selected }) else { return nil }
        let table = try AstroTable(raw)
        astroCache[selected] = table
        return table
    }
}
