import Foundation
internal struct IndexEntry: Sendable {
    var summary:JSONValue
    let offset:UInt64?
    let length:Int?
    var presence:IndexPresence? = nil
    var id:String { summary["station_id"].string! }
    var status:String { summary["status"].string ?? "active" }
    var sets:[JSONValue] { summary["sets"].array }
    var kind:Kind? { summary["kind"].isNull ? nil : Kind(value:summary["kind"]) }
    static func make(_ d:JSONValue,offset:UInt64?=nil,length:Int?=nil)->IndexEntry {
        let sid=d["station_id"],off=d["subordinate_offsets"],rid=d["recommended_set_id"]
        let sets=d["constant_sets"].array.map { cs -> JSONValue in
            var s:[String:JSONValue]=[:]
            for k in ["set_id","source","source_type","quantity","qc_status","convention_id","licence_id","fallback"] { s[k]=cs[k] }
            s["constituents"] = .array(cs["constituents"].array.map { $0["name"] }.filter { $0.string != nil })
            s["current_bins"] = .array(cs["current_bins"].array.map { $0["bin"] })
            return .object(s)
        }
        var kind:JSONValue = .null
        if !rid.isNull,let cs=sets.first(where: { $0["set_id"]==rid }) { kind = .string(cs["quantity"].string=="water_level" ? "tide":cs["quantity"].string=="current" ? "current":"other") }
        return IndexEntry(summary:.object(["station_id":sid,"status":d["status"].isNull ? .string("active"):d["status"],"name":d["name"],"name_folded":d["name"].string.map { .string(NameFold.fold($0)) } ?? .null,"country":d["country"],"type":d["type"],"lat":d["lat"],"lon":d["lon"],"kind":kind,"aliases":.object(d["aliases"].object.mapValues { $0.string.map { .array([.string($0)]) } ?? $0 }),"reference_station_id":off["reference_station_id"],"offsets_licence_id":off["licence_id"],"subordinate_offsets":off,"recommended_set_id":rid,"sets":.array(sets),"current_offsets":.array(d["current_offsets"].array.map { co in .object(["bin":co["bin"],"reference_bin":co["reference_bin"],"reference_station_id":co["reference_station_id"],"licence_id":co["licence_id"]]) }),"offset":offset.map { .integer(Int64($0)) } ?? .null,"length":length.map { .integer(Int64($0)) } ?? .null]),offset:offset,length:length)
    }
}
internal struct IndexPresence: Sendable {
    let subordinateOffsets:Bool
    let fallback:Bool
    let currentBins:Bool
    let privateFields:Bool
    let fullCurrentOffsets:Bool
}
internal func asciiWhitespace(_ byte:UInt8)->Bool { byte==32 || (9...13).contains(byte) }
internal func indexValueMatches(_ left:JSONValue,_ right:JSONValue)->Bool {
    switch (left,right) {
    case (.integer(let integer),.number(let number)),(.number(let number),.integer(let integer)):
        return Int64(exactly:number)==integer
    case (.array(let left),.array(let right)):
        return left.count==right.count && zip(left,right).allSatisfy(indexValueMatches)
    case (.object(let left),.object(let right)):
        return left.count==right.count && left.allSatisfy { key,value in right[key].map { indexValueMatches(value,$0) }==true }
    default:return left==right
    }
}
internal func eachLine(_ url:URL,_ body:(Data,UInt64)throws->Void)throws {
    let f:FileHandle
    do { f=try FileHandle(forReadingFrom:url) } catch { throw OpenTideConstantsError.io("cannot open \(url.path)") }
    defer { try? f.close() }
    var pending=Data(),offset:UInt64=0
    while let chunk=try autoreleasepool(invoking: { try f.read(upToCount:65536) }),!chunk.isEmpty {
        pending.append(chunk)
        while let e=pending.firstIndex(of:10) {
            var line=Data(pending[..<e]);let bytes=pending.distance(from:pending.startIndex,to:e)+1
            if line.last==13 { line.removeLast() }
            if !line.allSatisfy(asciiWhitespace) { try autoreleasepool { try body(line,offset) } }
            offset += UInt64(bytes);pending.removeFirst(bytes)
        }
        if pending.isEmpty { pending=Data() }
        else if pending.startIndex != 0 { pending=pending.withUnsafeBytes { Data(bytes:$0.baseAddress!,count:$0.count) } }
    }
    if !pending.allSatisfy(asciiWhitespace) { try autoreleasepool { try body(pending,offset) } }
}
internal extension Reader {
    static func authenticate_station_index(_ doc:JSONValue,url:URL,meta:JSONValue,digest:String,size:Int64)throws->[IndexEntry] {
        func require(_ condition:Bool)throws { if !condition { throw OpenTideConstantsError.invalidRelease("stale index-v1.json") } }
        let top=["index_version","datestamp","jsonl","jsonl_sha256","jsonl_size","by","stations"]
        try require(top.allSatisfy { doc.object.keys.contains($0) })
        try require(doc["index_version"].integer==1 && doc["datestamp"]==meta["release"]["datestamp"] && doc["jsonl"].string==url.lastPathComponent && doc["jsonl_sha256"].string==digest && doc["jsonl_size"].integer==size && doc["by"].string != nil)
        if doc.object.keys.contains("discovery_index_version") { try require(doc["discovery_index_version"].integer==1) }
        try require({ if case .array=doc["stations"] { return true };return false }())
        let rows=doc["stations"].array,sets=rows.flatMap { $0["sets"].array }
        let triples=["source_record_id","source_version","datum"]
        let counts=sets.map { set in triples.filter { set.object.keys.contains($0) }.count }
        try require(counts.allSatisfy { $0==0 } || counts.allSatisfy { $0==3 })
        let hasBins=sets.contains { $0.object.keys.contains("current_bins") }
        try require(!hasBins || sets.allSatisfy { $0.object.keys.contains("current_bins") })
        let ownOffsets=rows.contains { $0.object.keys.contains("subordinate_offsets") }
        let hasFallback=sets.contains { $0.object.keys.contains("fallback") }
        let adjustments=["time_adj_max_flood_min","time_adj_max_ebb_min","time_adj_slack_before_flood_min","time_adj_slack_before_ebb_min","flood_amp_ratio","ebb_amp_ratio"]
        var fullOffsets:Bool?
        for row in rows {
            let mandatory=["station_id","status","name","name_folded","country","type","lat","lon","kind","aliases","reference_station_id","offsets_licence_id","recommended_set_id","sets","offset","length"]
            try require(mandatory.allSatisfy { row.object.keys.contains($0) })
            try check(row,["station_id":"T","status":"T","name":"T","name_folded":"T","country":"T","type":"T","kind":"T","lat":"N","lon":"N","aliases":"O","reference_station_id":"T","offsets_licence_id":"T","recommended_set_id":"T","sets":"L","offset":"I","length":"I"],"index entry")
            try require(row["station_id"].string != nil && row["status"].string != nil)
            try require(row["name_folded"]==(row["name"].string.map { .string(NameFold.fold($0)) } ?? .null))
            if row["status"].string=="active" { try require(row["lat"].number.map { abs($0)<=90 }==true && row["lon"].number.map { abs($0)<=180 }==true) }
            try require({ if case .object=row["aliases"],case .array=row["sets"] { return true };return false }())
            for aliases in row["aliases"].object.values { try require({ if case .array=aliases { return aliases.array.allSatisfy { $0.string != nil } };return false }()) }
            if row.object.keys.contains("subordinate_offsets") {
                if !row["subordinate_offsets"].isNull { try check(row["subordinate_offsets"],_offset_types,"indexed offsets");try historical(row["subordinate_offsets"]) }
                try require(row["reference_station_id"]==row["subordinate_offsets"]["reference_station_id"] && row["offsets_licence_id"]==row["subordinate_offsets"]["licence_id"])
            } else if ownOffsets { try require(row["reference_station_id"].isNull && row["offsets_licence_id"].isNull) }
            for set in row["sets"].array {
                let keys=["set_id","source","source_type","quantity","qc_status","convention_id","licence_id","constituents"]
                try require(keys.allSatisfy { set.object.keys.contains($0) })
                try check(set,["set_id":"T","source":"T","source_type":"T","quantity":"T","qc_status":"T","convention_id":"T","licence_id":"T","constituents":"S","source_record_id":"T","source_version":"T","datum":"O"],"indexed set")
                try require({ if case .array=set["constituents"] { return true };return false }())
                try require(Set(set["constituents"].array.compactMap(\.string)).count==set["constituents"].array.count)
                if !set["datum"].isNull { try check(set["datum"],_datum_types,"indexed datum") }
                if set.object.keys.contains("fallback"),!set["fallback"].isNull { try check(set["fallback"],_fallback_types,"indexed fallback") }
                if set.object.keys.contains("current_bins") { try require({ if case .array=set["current_bins"] { return set["current_bins"].array.allSatisfy { ($0.integer ?? 0)>=1 && ($0.integer ?? Int64.max)<=9007199254740991 } };return false }()) }
            }
            if row.object.keys.contains("current_offsets") {
                try require({ if case .array=row["current_offsets"] { return true };return false }())
                for offset in row["current_offsets"].array {
                    try require(["bin","reference_bin","reference_station_id","licence_id"].allSatisfy { offset.object.keys.contains($0) })
                    try check(offset,["bin":"I","reference_bin":"I","reference_station_id":"T","licence_id":"T"],"indexed current offsets")
                    try require(["bin","reference_bin"].allSatisfy { (offset[$0].integer ?? 0)>=1 && (offset[$0].integer ?? Int64.max)<=9007199254740991 })
                    let count=adjustments.filter { offset.object.keys.contains($0) }.count
                    try require(count==0 || count==6)
                    if let fullOffsets { try require(fullOffsets==(count==6)) } else { fullOffsets=count==6 }
                    if count==6 { try check(offset,Dictionary(uniqueKeysWithValues:adjustments.map { ($0,"N") }),"indexed current adjustments") }
                }
            }
        }
        let presence=IndexPresence(subordinateOffsets:ownOffsets,fallback:hasFallback,currentBins:hasBins,privateFields:counts.contains(3),fullCurrentOffsets:fullOffsets==true)
        var entries:[IndexEntry]=[]
        for row in rows {
            guard let offset=row["offset"].integer,let length=row["length"].integer else { throw OpenTideConstantsError.invalidRelease("stale index span") }
            try require(offset>=0 && length>=1 && offset<=9007199254740991 && length<=9007199254740991 && offset<=size && length<=size-offset)
            entries.append(IndexEntry(summary:row,offset:UInt64(offset),length:Int(length),presence:presence))
        }
        let active=Dictionary(entries.filter { $0.status=="active" }.map { ($0.id,$0) },uniquingKeysWith:{ a,_ in a })
        for entry in entries {
            var current=entry,seen:Set<String>=[entry.id],kind:JSONValue = .null
            for depth in 0...16 {
                if let rid=current.summary["recommended_set_id"].string,let set=current.sets.first(where:{ $0["set_id"].string==rid }) { kind = .string(set["quantity"].string=="water_level" ? "tide":set["quantity"].string=="current" ? "current":"other");break }
                guard depth<16,current.summary["type"].string=="subordinate",let id=current.summary["reference_station_id"].string,seen.insert(id).inserted,let reference=active[id] else { break }
                current=reference
            }
            try require(entry.summary["kind"]==kind)
        }
        let handle=try FileHandle(forReadingFrom:url);defer { try? handle.close() }
        var end:UInt64=0
        for entry in entries.sorted(by:{ $0.offset!<$1.offset! }) {
            let start=entry.offset!,length=entry.length!
            try require(start>=end)
            try handle.seek(toOffset:end)
            var gap=start-end
            while gap>0 {
                let data=try handle.read(upToCount:Int(min(gap,65536))) ?? Data()
                try require(!data.isEmpty && data.allSatisfy(asciiWhitespace));gap-=UInt64(data.count)
            }
            if entry.status != "active" {
                let body=try handle.read(upToCount:length) ?? Data()
                try require(body.count==length)
                let actual=try JSONValue.parse(body)
                try require(actual["station_id"].string==entry.id && (actual["status"].string ?? "active")==entry.status)
            }
            end=start+UInt64(length)
        }
        try handle.seek(toOffset:end)
        while let data=try handle.read(upToCount:65536),!data.isEmpty { try require(data.allSatisfy(asciiWhitespace)) }
        return entries
    }
}
