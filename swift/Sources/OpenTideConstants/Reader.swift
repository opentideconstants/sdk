import Foundation
import CZlib

internal enum Reader {
    static let _station_types: [String:String] = ["name": "T", "country": "T", "timezone": "T", "type": "T", "recommended_set_id": "T", "status": "T",
                  "constant_sets": "L", "validation": "L", "subordinate_offsets": "O", "current_offsets": "A",
                  "recommended_is_fallback": "B", "source_records": "L"]
    static let _offset_types: [String:String] = ["reference_station_id": "T", "licence_id": "T", "height_adjusted_type": "T",
                 "time_offset_high_min": "N", "time_offset_low_min": "N", "height_offset_high": "N", "height_offset_low": "N",
                 "offset_id": "T", "source": "T", "source_type": "T", "source_version": "T", "source_record_id": "T",
                 "qc_status": "T", "qc_flags": "L", "fallback": "O", "vintage": "O", "provenance": "O"]
    static let _validation_types: [String:String] = ["set_id": "T", "reference_source": "T", "reference_station": "T", "window": "T",
                     "reference_distance_km": "N", "time_mae_min": "N", "time_p95_min": "N", "time_bias_min": "N",
                     "height_mae_m": "N", "range_error_m": "N", "missed_events": "I", "extra_events": "I",
                     "previous_release": "O"]
    static let _set_types: [String:String] = ["set_id": "T", "source": "T", "source_type": "T", "quantity": "T", "source_record_id": "T",
              "source_version": "T", "convention_id": "T", "licence_id": "T", "qc_status": "T", "constituents": "L",
              "dropped_constituents": "L", "qc_flags": "L", "record_span": "O", "datum": "O", "time_base": "O",
              "provenance": "O", "current_bins": "A", "fallback": "O"]
    static let _fallback_types: [String:String] = ["reason": "T", "basis": "T", "otc_finding": "T", "preferred_set_id": "T"]
    static let _span_types: [String:String] = ["good_samples": "I"]
    static let _datum_types: [String:String] = ["msl_offset_m": "N", "named": "O"]
    static let _constituent_types: [String:String] = ["name": "T", "source_name": "T", "doodson": "T", "kept_reason": "T", "speed_deg_per_hour": "N",
                      "amplitude_m": "N", "phase_deg": "N", "amp_uncertainty_m": "N", "phase_uncertainty_deg": "N"]
    static let _qc_flag_types: [String:String] = ["flag": "T", "reason": "T", "values": "O"]
    static let _dropped_types: [String:String] = ["name": "T", "dropped_reason": "T", "detail": "T"]
    static let _time_base_types: [String:String] = ["code": "T", "reason": "T", "declared": "T", "published": "T", "decided_in": "T",
                    "decided_build_commit": "T", "correction": "O", "months_dropped": "S", "evidence": "L"]
    static let _correction_types: [String:String] = ["from": "T", "to": "T"]
    static let _evidence_types: [String:String] = ["comparator_kind": "T", "comparator_id": "T", "detail": "T", "distance_km": "N", "lag_min": "N"]
    static let _provenance_types: [String:String] = ["adapter_version": "T", "carried_from_release": "T", "selection_reason": "T",
                     "input_sha256": "S", "decision": "O"]
    static let _source_record_types: [String:String] = ["source": "T", "source_version": "T", "source_record_id": "T", "role": "T",
                        "disposition": "T", "detail": "T", "licence_id": "T", "upstream_licence_id": "T",
                        "published_set_ids": "S", "provenance": "O", "original_metadata": "O", "original_harmonics": "O"]
    static let _source_provenance_types: [String:String] = ["input_sha256": "S", "inventory_sha256": "T"]
    static let _original_harmonic_types: [String:String] = ["format": "T", "columns": "S", "rows": "A", "annotations": "L",
                           "amplitude_unit": "T", "amplitude_unit_basis": "T", "phase_unit": "T",
                           "phase_convention": "T", "amplitude_uncertainty_unit": "T",
                           "amplitude_uncertainty_unit_basis": "T"]
}
internal extension Reader {
    struct ValidatedReleaseDocument {
        let document:JSONValue
        let links:Release.ValidatedLinks
        fileprivate init(document:JSONValue,links:Release.ValidatedLinks) { self.document=document;self.links=links }
    }
    static func decodeDocument(_ bytes:Data,readerVersion:CanonicalReaderVersion,kind:CanonicalDocumentKind)throws->CanonicalParsedDocument {
        let doc=try JSONValue.parse(bytes)
        switch kind {
        case .release:
            guard case .array=doc["stations"] else { throw OpenTideConstantsError.invalidRelease("stations missing") }
            try validateHeader(doc,readerVersion:readerVersion)
            return .release(doc)
        case .stationRow: try check(doc,_station_types,"station");return .stationRow(doc)
        case .cache: return .cache(doc)
        case .pointer,.catalogue: throw CanonicalUnimplemented.behavior("B05.metadata_source")
        }
    }
    static func validateDocumentLinks(_ doc:JSONValue)throws->ValidatedReleaseDocument {
        let (meta,entries,documents)=try releaseRows(doc)
        let (conventions,licences)=try documentLookupTables(meta)
        for row in documents.values { try validateSourceStation(row,conventions:conventions,licences:licences) }
        return ValidatedReleaseDocument(document:doc,links:try Release.validateLinks(meta:meta,entries:entries,commercialBasis:"strict",historicalOffsetsPolicy:"fallback"))
    }
    static func releaseRows(_ doc:JSONValue)throws->(JSONValue,[IndexEntry],[String:JSONValue]) {
        guard case .array=doc["stations"] else { throw OpenTideConstantsError.invalidRelease("stations missing") }
        var entries:[IndexEntry]=[],documents:[String:JSONValue]=[:]
        for row in doc["stations"].array {
            guard let id=row["station_id"].string else { throw OpenTideConstantsError.invalidRelease("station_id missing") }
            entries.append(IndexEntry.make(row));documents[id]=row
        }
        var fields=doc.object;fields.removeValue(forKey:"stations");let meta=JSONValue.object(fields)
        return (meta,entries,documents)
    }
    static func check(_ raw: JSONValue, _ fields: [String:String], _ what: String) throws {
        guard case .object = raw else { throw OpenTideConstantsError.invalidRelease("\(what): not object") }
        for (k,t) in fields {
            let v = raw[k]; if v.isNull { continue }
            let valid: Bool
            switch t {
            case "T": valid = v.string != nil
            case "N": valid = v.number?.isFinite == true
            case "I": valid = v.integer != nil
            case "B": valid = v.bool != nil
            case "O": if case .object = v { valid = true } else { valid = false }
            case "L": if case .array(let rows) = v { valid = rows.allSatisfy { if case .object = $0 { return true }; return false } } else { valid = false }
            case "S": if case .array(let rows) = v { valid = rows.allSatisfy { $0.string != nil } } else { valid = false }
            default: if case .array = v { valid = true } else { valid = false }
            }
            if !valid { throw OpenTideConstantsError.invalidRelease("\(what): \(k) wrong type") }
        }
    }
    static func licence(_ raw: JSONValue) throws -> Licence {
        try check(raw,["licence_id":"T","attribution":"T","provider":"T","commercial_use":"B","spdx":"T","restriction":"T","terms_url":"T"],"licence")
        guard raw["licence_id"].string != nil, raw["attribution"].string != nil, let commercial = raw["commercial_use"].bool else { throw OpenTideConstantsError.invalidRelease("licence needs id/attribution/commercial_use") }
        for k in ["restriction","terms_url"] { if raw.object.keys.contains(k) && raw[k].string == nil { throw OpenTideConstantsError.invalidRelease("licence \(k) not string") } }
        if !commercial && ["restriction","terms_url","spdx"].contains(where: { raw[$0].string == nil }) { throw OpenTideConstantsError.invalidRelease("noncommercial licence missing terms") }
        return Licence(raw)
    }
    static func station(_ d: JSONValue, conventions: [String:Convention], licences: [String:Licence], kind: Kind?, recommended: String?) throws -> Station {
        try check(d,_station_types,"station")
        guard d["station_id"].string != nil, let lat=d["lat"].number, let lon=d["lon"].number, abs(lat)<=90,abs(lon)<=180 else { throw OpenTideConstantsError.invalidRelease("station id or coordinates invalid") }
        var sources: [SourceRecord] = []
        if d.object.keys.contains("source_records") && d["source_records"].array.isEmpty { throw OpenTideConstantsError.invalidRelease("source_records must be nonempty") }
        for src in d["source_records"].array {
            try check(src,_source_record_types,"source record")
            guard ["source","source_version","source_record_id","role","disposition","detail"].allSatisfy({ src[$0].string?.isEmpty == false }),src.object.keys.contains("licence_id"), case .array = src["published_set_ids"],case .object = src["provenance"] else { throw OpenTideConstantsError.invalidRelease("source record required fields") }
            try check(src["provenance"],_source_provenance_types,"source provenance")
            guard case .array = src["provenance"]["input_sha256"],src["provenance"]["inventory_sha256"].string != nil else { throw OpenTideConstantsError.invalidRelease("source provenance missing hashes") }
            if src.object.keys.contains("original_metadata"), case .object = src["original_metadata"] {} else if src.object.keys.contains("original_metadata") { throw OpenTideConstantsError.invalidRelease("source metadata not object") }
            if !src["original_harmonics"].isNull {
                try check(src["original_harmonics"],_original_harmonic_types,"original harmonics")
                let h=src["original_harmonics"]
                if h.object.keys.contains("rows") && !h["rows"].array.allSatisfy({ if case .array(let r) = $0 { return r.allSatisfy { $0.string != nil } }; return false }) { throw OpenTideConstantsError.invalidRelease("original rows must be strings") }
                for a in h["annotations"].array { try check(a,["row":"I","reason":"T","detail":"T"],"annotation") }
            }
            let l=src["licence_id"].string, u=src["upstream_licence_id"].string
            if (l != nil && licences[l!] == nil) || (u != nil && licences[u!] == nil) { throw OpenTideConstantsError.invalidRelease("source licence unresolved") }
            sources.append(SourceRecord(raw:src,licence:l.flatMap { licences[$0] },upstreamLicence:u.flatMap { licences[$0] }))
        }
        let validation=d["validation"].array.map(Validation.init)
        for v in d["validation"].array { try check(v,_validation_types,"validation") }
        var sets:[ConstantSet]=[]
        for cs in d["constant_sets"].array {
            try check(cs,_set_types,"constant set")
            guard let id=cs["set_id"].string,let conv=conventions[cs["convention_id"].string ?? ""],let lic=licences[cs["licence_id"].string ?? ""] else { throw OpenTideConstantsError.invalidRelease("set identity/reference unresolved") }
            for (k,table) in [("record_span",_span_types),("datum",_datum_types),("time_base",_time_base_types),("provenance",_provenance_types),("fallback",_fallback_types)] where !cs[k].isNull { try check(cs[k],table,k) }
            for (k,table) in [("constituents",_constituent_types),("qc_flags",_qc_flag_types),("dropped_constituents",_dropped_types)] { for row in cs[k].array { try check(row,table,k) } }
            let names=cs["constituents"].array.compactMap { $0["name"].string }
            guard names.count == cs["constituents"].array.count,Set(names).count==names.count else { throw OpenTideConstantsError.invalidRelease("constituent names absent/duplicate") }
            if cs["datum"]["named"].object.values.contains(where: { $0.number == nil }) { throw OpenTideConstantsError.invalidRelease("datum value nonnumeric") }
            for q in cs["qc_flags"].array { if q["values"].object.values.contains(where: { !$0.isNull && $0.number == nil }) { throw OpenTideConstantsError.invalidRelease("qc value nonnumeric") } }
            _ = try parseTime(cs["record_span"]["start"].string); _ = try parseTime(cs["record_span"]["end"].string)
            if cs["fallback"]["reason"].string == "historical_offsets" || cs["qc_flags"].array.contains(where: { $0["flag"].string == "fallback:historical_offsets" }) { throw OpenTideConstantsError.invalidRelease("historical label belongs to offsets") }
            sets.append(ConstantSet(raw:cs,convention:conv,licence:lic,isRecommended:id==recommended,validation:validation.filter { $0.setId==id }.sorted { $0.window < $1.window }))
        }
        if let rid=d["recommended_set_id"].string, !sets.contains(where: { $0.setId==rid }) { throw OpenTideConstantsError.invalidRelease("recommended set unresolved") }
        for alias in d["aliases"].object.values { if alias.string == nil && !( { if case .array(let values) = alias { return values.allSatisfy { $0.string != nil } }; return false }() ) { throw OpenTideConstantsError.invalidRelease("malformed aliases") } }
        if !d["subordinate_offsets"].isNull {
            try historical(d["subordinate_offsets"])
            if let lid=d["subordinate_offsets"]["licence_id"].string,licences[lid]==nil { throw OpenTideConstantsError.invalidRelease("offset licence unresolved") }
        }
        return Station(raw:d,kind:kind,recommendedSet:sets.first { $0.isRecommended },sourceRecords:sources,sets:sets.sorted { ($0.isRecommended ? "" : $0.setId) < ($1.isRecommended ? "" : $1.setId) })
    }
}
internal extension Reader {
    static func historical(_ d: JSONValue) throws {
        try check(d,_offset_types,"offsets")
        let marked=d.object.keys.contains("offset_id") || d["fallback"]["reason"].string == "historical_offsets" || d["qc_flags"].array.contains { $0["flag"].string == "fallback:historical_offsets" }
        guard marked else { return }
        func require(_ ok: Bool, _ field: String) throws { if !ok { throw OpenTideConstantsError.invalidRelease("invalid historical \(field)") } }
        let atlantic=d["offset_id"].string == "noaa-2020-atlantic-table2-2513"
        try require(atlantic || d["offset_id"].string == "noaa-2020-pacific-table2-517","offset_id")
        let book=atlantic ? "atlantic":"pacific",row=atlantic ? 2513:517
        let expected:[String:JSONValue] = ["source":.string("noaa"),"source_type":.string("official"),"source_version":.string("annual-tide-tables-2020"),"source_record_id":.string("annual-tide-tables-2020/\(book)/Table2/\(row)"),"qc_status":.string("flagged"),"reference_station_id":.string(atlantic ? "OTC-a6c00a3f":"OTC-ee4593cd"),"height_adjusted_type":.string(atlantic ? "R":"A")]
        for (k,v) in expected { try require(d[k]==v,k) }
        for (k,v) in [("time_offset_high_min",atlantic ? 4.0 : -35.0),("time_offset_low_min",atlantic ? 15.0 : -31.0),("height_offset_high",atlantic ? 0.84 : -0.06096),("height_offset_low",atlantic ? 1.0 : 0.0)] { try require(d[k].number == v,k) }
        func text(_ v:JSONValue) -> Bool { v.string?.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty == false }
        func digest(_ v:JSONValue) -> Bool { v.string?.range(of:"^[a-f0-9]{64}$",options:.regularExpression) != nil }
        func hashes(_ v:JSONValue) -> Bool { !v.array.isEmpty && v.array.allSatisfy(digest) && Set(v.array.compactMap(\.string)).count==v.array.count }
        try require(text(d["licence_id"]),"licence_id")
        try require(d["qc_flags"].array.count==1 && d["qc_flags"].array[0]["flag"].string=="fallback:historical_offsets" && text(d["qc_flags"].array[0]["reason"]),"qc_flags")
        let f=d["fallback"]
        try require(f["reason"].string=="historical_offsets" && text(f["basis"]) && text(f["otc_finding"]) && !f.object.keys.contains("preferred_set_id"),"fallback")
        let datum:JSONValue = .object(["zero":.string("chart_datum"),"chart_datum":.string("mllw"),"named":.object(["mllw":.number(0)]),"basis":.object(["mllw":.object(["kind":.string("published"),"method":.string("source"),"source_name":.string("MLLW")])])])
        try require(d["datum"]["zero"]==datum["zero"] && d["datum"]["chart_datum"]==datum["chart_datum"] && d["datum"]["named"]["mllw"].number==0 && d["datum"]["named"].object.count==1 && d["datum"]["basis"]==datum["basis"] && d["datum"].object.count==4,"datum")
        let v=d["vintage"]
        try require(v["publication_year"].number==2020 && v["source_lifecycle"].string=="retired" && v["current_validity"].string=="unestablished" && v["current_accuracy"].string=="unverified","vintage")
        let removals:[(String,String)] = atlantic ? [("2026-02-18T14:09:46","Lockwoods Folly Inlet (r)")] : [("2026-02-18T14:09:50","San Francisco Bar (r)"),("2026-07-06T11:17:37","San Francisco Bar")]
        let er=removals.map { t,n in JSONValue.object(["source_clock_timestamp":.string(t),"name":.string(n),"operation":.string("Removed"),"source_timezone":.null,"evidence_sha256":.string("c100d0fbc5482ec24f5c99d912be73306bd2dea079690f08edc5f58a821bcd61")]) }
        try require(v["removal_events"] == .array(er),"removal_events")
        let eq=v["reference_2020_equivalence"].string ?? ""
        try require(["not_checked","matched_at_publisher_precision","disagrees"].contains(eq),"equivalence")
        try require(eq=="not_checked" ? !v.object.keys.contains("reference_2020_equivalence_sha256") : digest(v["reference_2020_equivalence_sha256"]),"equivalence digest")
        let p=d["provenance"]
        try require(p["source_manifest_sha256"].string=="667eec5b3fd25f99d46f24864766726094961d7db5fa104ca12450f3ecd0fdf7" && p["book"].string==book && p["annual_table_row"].number==Double(row) && p["printed_page"].number==Double(atlantic ? 345:284) && p["pdf_page"].number==Double(atlantic ? 351:302),"source binding")
        let rawRow=atlantic ? "  2513     Lockwoods Folly Inlet . . . . . . . . . . . . . . . . . . . . . . .         33° 55'     78° 14'     +0 04      +0 15     *0.84     *1.00    4.2    4.8     2.3" : "   517     San Francisco Bar . . . . . . . . . . . . . . . . . . . . . . . . .         37° 46'     122° 38'     -0 35       -0 31      -0.2        0.0    3.9    5.6     3.0"
        try require(p["raw_row_text"].string==rawRow && hashes(p["input_sha256"]) && digest(p["acceptance_report_sha256"]),"source hashes/row")
        let cross=p["id_crosswalk"],ref=p["reference_binding"]
        try require(cross["legacy_id"].string==(atlantic ? "TEC2869":"TWC0509") && cross["status"].string=="inferred" && cross["modern_alias_verified"].bool==false && hashes(cross["evidence_sha256"]),"crosswalk")
        try require(ref["noaa_id"].string==(atlantic ? "8661070":"9414290") && ref["station_id"]==d["reference_station_id"] && ref["mapping_status"].string=="primary_name_position" && hashes(ref["evidence_sha256"]),"reference binding")
        guard let raw=p["raw_values_json"].string,let parsed=try? JSONValue.parse(Data(raw.utf8)),case .object=parsed else { throw OpenTideConstantsError.invalidRelease("historical raw_values_json not object") }
    }
    static func read(_ path:URL) throws -> Data {
        do { return try Data(contentsOf:path) } catch { throw OpenTideConstantsError.io("cannot read \(path.path): \(error)",["path":.string(path.path)]) }
    }
    static func gunzip(_ data:Data) throws -> Data {
        var stream=z_stream(); guard inflateInit2_(&stream,31,ZLIB_VERSION,Int32(MemoryLayout<z_stream>.size))==Z_OK else { throw OpenTideConstantsError.invalidRelease("gzip initialization failed") }
        defer { inflateEnd(&stream) }
        return try data.withUnsafeBytes { input in
            stream.next_in=UnsafeMutablePointer(mutating:input.bindMemory(to:Bytef.self).baseAddress); stream.avail_in=uInt(data.count)
            var result=Data(); var status:Int32=Z_OK
            repeat {
                var chunk=[UInt8](repeating:0,count:65536)
                status=chunk.withUnsafeMutableBufferPointer { out in stream.next_out=out.baseAddress;stream.avail_out=uInt(out.count);return inflate(&stream,Z_NO_FLUSH) }
                result.append(contentsOf:chunk.prefix(chunk.count-Int(stream.avail_out)))
                guard status==Z_OK || status==Z_STREAM_END else { throw OpenTideConstantsError.invalidRelease("invalid gzip") }
            } while status != Z_STREAM_END
            return result
        }
    }
}
internal extension Reader {
    static func validateHeader(_ meta:JSONValue,readerVersion:CanonicalReaderVersion=CanonicalReaderVersion(major:1,minor:0))throws {
        let created = meta["release"]["created"]
        guard created.isNull || created.string != nil else {
            throw OpenTideConstantsError.invalidRelease("created has the wrong type")
        }
        let fv=meta["format_version"].string ?? ""
        guard fv.range(of:#"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"#,options:.regularExpression) != nil else { throw OpenTideConstantsError.invalidRelease("invalid format version") }
        guard fv.split(separator:".").first=="1" else { throw OpenTideConstantsError.unsupportedFormat("unsupported format \(fv)") }
        do {
            guard let mr=meta["release"]["min_reader_version"].string else { throw OpenTideConstantsError.invalidRelease("min_reader_version missing or wrong type") }
            guard mr.range(of:#"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$"#,options:.regularExpression) != nil else { throw OpenTideConstantsError.invalidRelease("invalid min_reader_version") }
            let parts=mr.split(separator:".").compactMap { Int64($0) }
            guard parts.count==2,parts[0]<readerVersion.major || parts[0]==readerVersion.major && parts[1]<=readerVersion.minor else { throw OpenTideConstantsError.readerTooOld("needs reader \(mr); SDK reads \(readerVersion.major).\(readerVersion.minor)") }
        }
    }
    static func documentLookupTables(_ meta:JSONValue)throws->([String:Convention],[String:Licence]) {
        var conventions: [String: Convention] = [:]
        for row in meta["conventions"].array {
            guard let id = row["convention_id"].string else { continue }
            guard conventions[id] == nil else {
                throw OpenTideConstantsError.invalidRelease("duplicate convention")
            }
            conventions[id] = Convention(row)
        }
        var licences:[String:Licence]=[:];for row in meta["licences"].array { let l=try licence(row);if licences[l.licenceId] != nil { throw OpenTideConstantsError.invalidRelease("duplicate licence") };licences[l.licenceId]=l }
        return (conventions,licences)
    }
    static func validateSourceStation(_ d:JSONValue,conventions:[String:Convention],licences:[String:Licence])throws {
        guard d["station_id"].string != nil else { throw OpenTideConstantsError.invalidRelease("station_id missing") }
        let status=d["status"].string ?? "active"
        if !d["status"].isNull && d["status"].string==nil { throw OpenTideConstantsError.invalidRelease("invalid station status") }
        if status=="active" { _ = try station(d,conventions:conventions,licences:licences,kind:nil,recommended:d["recommended_set_id"].string) }
    }
    struct SuppliedStationIndex {
        fileprivate let bytes:Data
        fileprivate init(_ bytes:Data) { self.bytes=bytes }
    }
    static func prepareSuppliedStationIndex(_ bytes:Data)->SuppliedStationIndex { SuppliedStationIndex(bytes) }
    struct AuthenticatedStationIndex {
        let release:Release
        let document:JSONValue
        var nativeEntries:[IndexEntry] { release.entries }
        fileprivate init(release:Release,document:JSONValue) {
            self.release=release;self.document=document
        }
    }
    // Existing stream index source checks, admission, one-pass rebuild and publication.
    static func prepareStreamIndex(_ url:URL,meta:JSONValue,conventions:[String:Convention],licences:[String:Licence],indexPath:URL?,files:[FileInfo],commercialOnly:Bool,commercialBasis:String,historicalOffsetsPolicy:String,logger:((String)->Void)?,supplied:SuppliedStationIndex?=nil)throws->AuthenticatedStationIndex {
        var digest:String?,size:Int64?
        digest=try SHA256.file(url)
        size=(try FileManager.default.attributesOfItem(atPath:url.path)[.size] as? NSNumber)?.int64Value
        let metaURL=URL(fileURLWithPath:String(url.path.dropLast(6))+".meta.json")
        for source in [url,metaURL] {
            guard let declared=files.first(where:{ $0.name==source.lastPathComponent }) else { continue }
            let actualSize=(try FileManager.default.attributesOfItem(atPath:source.path)[.size] as? NSNumber)?.int64Value
            let actualHash=source==url ? digest:try SHA256.file(source)
            if (declared.size != nil && declared.size != actualSize) || (declared.sha256 != nil && declared.sha256?.lowercased() != actualHash) {
                if let indexPath { try? FileManager.default.removeItem(at:indexPath) }
                throw OpenTideConstantsError.checksumMismatch("checksum mismatch",["file":.string(source.path),"expected":declared.sha256.map(JSONValue.string) ?? .null,"actual":actualHash.map(JSONValue.string) ?? .null])
            }
        }
        if supplied != nil || indexPath.map({ FileManager.default.fileExists(atPath:$0.path) })==true {
            do {
                let doc=try JSONValue.parse(supplied?.bytes ?? read(indexPath!))
                let admitted=try authenticate_station_index(doc,url:url,meta:meta,digest:digest!,size:size!)
                let release=try Release(meta:meta,entries:admitted,documents:[:],jsonl:url,indexPath:indexPath,files:files,commercialOnly:commercialOnly,commercialBasis:commercialBasis,historicalOffsetsPolicy:historicalOffsetsPolicy)
                return AuthenticatedStationIndex(release:release,document:doc)
            } catch {
                if let indexPath { try? FileManager.default.removeItem(at:indexPath) }
            }
        }
        var entries:[IndexEntry]=[]
        try eachLine(url) { line,offset in
            let d=try JSONValue.parse(line)
            try validateSourceStation(d,conventions:conventions,licences:licences)
            entries.append(IndexEntry.make(d,offset:offset,length:line.count))
        }
        let release=try Release(meta:meta,entries:entries,documents:[:],jsonl:url,indexPath:indexPath,files:files,commercialOnly:commercialOnly,commercialBasis:commercialBasis,historicalOffsetsPolicy:historicalOffsetsPolicy)
        let document:JSONValue = .object(["index_version":.integer(1),"discovery_index_version":.integer(1),"datestamp":.string(release.datestamp),"jsonl":.string(url.lastPathComponent),"jsonl_sha256":.string(digest!),"jsonl_size":.integer(size!),"by":.string("opentideconstants-swift/0.1.0"),"stations":.array(entries.map { release.byId[$0.id]!.summary })])
        if let indexPath {
            do { try Cache.atomic(document.data(),indexPath) }
            catch { logger?("opentideconstants: cannot cache index-v1.json") }
        }
        return AuthenticatedStationIndex(release:release,document:document)
    }
    static func load(_ url:URL,mode:Mode,commercialOnly:Bool,commercialBasis:String,historicalOffsetsPolicy:String,indexPath:URL?=nil,files:[FileInfo]=[],logger:((String)->Void)?=nil)throws->Release {
        let isLines=url.lastPathComponent.hasSuffix(".jsonl")
        var meta:JSONValue,entries:[IndexEntry]=[],docs:[String:JSONValue]=[:]
        if isLines { meta=try JSONValue.parse(read(URL(fileURLWithPath:String(url.path.dropLast(6))+".meta.json"))) }
        else {
            var bytes=try read(url);if url.lastPathComponent.hasSuffix(".gz") { bytes=try gunzip(bytes) }
            (meta,entries,docs)=try releaseRows(JSONValue.parse(bytes))
        }
        try validateHeader(meta)
        let (conventions,licences)=try documentLookupTables(meta)
        if isLines,mode == .stream {
            let index=try prepareStreamIndex(url,meta:meta,conventions:conventions,licences:licences,indexPath:indexPath,files:files,commercialOnly:commercialOnly,commercialBasis:commercialBasis,historicalOffsetsPolicy:historicalOffsetsPolicy,logger:logger)
            return index.release
        }
        func consume(_ d:JSONValue,_ offset:UInt64?,_ length:Int?)throws {
            try validateSourceStation(d,conventions:conventions,licences:licences)
            let id=d["station_id"].string!
            if isLines { entries.append(IndexEntry.make(d,offset:offset,length:length));if mode != .stream { docs[id]=d } }
        }
        if isLines { try eachLine(url) { line,offset in try consume(JSONValue.parse(line),offset,line.count) } }
        else { for d in docs.values { try consume(d,nil,nil) } }
        let release=try Release(meta:meta,entries:entries,documents:docs,jsonl:isLines && mode == .stream ? url:nil,indexPath:indexPath,files:files,commercialOnly:commercialOnly,commercialBasis:commercialBasis,historicalOffsetsPolicy:historicalOffsetsPolicy)
        return release
    }
}
