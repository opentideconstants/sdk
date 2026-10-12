import Foundation
internal struct IndexEntry: Sendable {
    var summary:JSONValue
    let offset:UInt64?
    let length:Int?
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
            if !line.isEmpty { try autoreleasepool { try body(line,offset) } }
            offset += UInt64(bytes);pending.removeFirst(bytes)
        }
        if pending.isEmpty { pending=Data() }
        else if pending.startIndex != 0 { pending=pending.withUnsafeBytes { Data(bytes:$0.baseAddress!,count:$0.count) } }
    }
    if !pending.isEmpty { try autoreleasepool { try body(pending,offset) } }
}
