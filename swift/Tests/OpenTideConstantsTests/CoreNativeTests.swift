import XCTest
@testable import OpenTideConstants
final class CoreNativeTests:XCTestCase {
    func testActualHTTPCredentialRedaction() async throws {
        let cache=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at:cache) }
        do {
            let client=try await OpenTideConstants.open(cacheDir:cache.path,baseUrl:"http://otcpk12user:Pk12S3cretPW@127.0.0.1:1/good/",onNetworkError:.raise)
            client.close();XCTFail("the existing refused-connection fixture must fail")
        } catch let error as OpenTideConstantsError {
            XCTAssertEqual(error.code,"network")
            for value in [error.message,error.fields["url"]?.string ?? ""] {
                XCTAssertFalse(value.contains("otcpk12user"));XCTAssertFalse(value.contains("Pk12S3cretPW"))
            }
            XCTAssertTrue(error.fields["url"]?.string?.contains("://***@127.0.0.1:1/good/") == true)
        }
    }
    func testActualHTTPRetryAfter() async throws {
        let root=try path("OTC_HTTP_NATIVE_REPO_ROOT"),proof=try path("OTC_HTTP_NATIVE_PROOF_ROOT")
        let directory=URL(fileURLWithPath:proof).appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at:directory,withIntermediateDirectories:true)
        let rules=directory.appendingPathComponent("rules.json")
        // Private status control on the unchanged, real conformance server and release fixture.
        try Data("[{\"match\":\"/good/OTC_latest-f1\\\\.json$\",\"action\":\"status\",\"status\":429,\"headers\":{\"Retry-After\":\"2\"},\"times\":1}]".utf8).write(to:rules)
        let server=Process(),log=directory.appendingPathComponent("server.stdout"),errors=directory.appendingPathComponent("server.stderr")
        FileManager.default.createFile(atPath:log.path,contents:Data());FileManager.default.createFile(atPath:errors.path,contents:Data())
        let output=try FileHandle(forWritingTo:log),error=try FileHandle(forWritingTo:errors)
        defer { try? output.close();try? error.close() }
        server.executableURL=URL(fileURLWithPath:try path("OTC_HTTP_NATIVE_PYTHON"))
        server.arguments=["-u",root+"/conformance/server.py","--port","0","--proxy-port","0","--rules",rules.path]
        server.environment=ProcessInfo.processInfo.environment.merging(["PYTHONDONTWRITEBYTECODE":"1"]) { _,value in value }
        server.standardOutput=output;server.standardError=error
        try server.run()
        defer { if server.isRunning { server.interrupt() };server.waitUntilExit() }
        let deadline=Date().addingTimeInterval(10)
        var base:String?
        while server.isRunning,Date()<deadline {
            let text=(try? String(contentsOf:log,encoding:.utf8)) ?? ""
            if let line=text.components(separatedBy:"\n").first(where: { $0.hasPrefix("fixture server http://") }) {
                base=line.components(separatedBy:" ")[2]+"good/";break
            }
            try await Task.sleep(nanoseconds:10_000_000)
        }
        let url=try XCTUnwrap(base,"existing native fixture did not start")
        let start=ProcessInfo.processInfo.systemUptime
        let client=try await OpenTideConstants.open(cacheDir:directory.appendingPathComponent("cache").path,baseUrl:url,onNetworkError:.raise)
        defer { client.close() }
        XCTAssertEqual(client.loadedFrom,.download);XCTAssertEqual(client.release.datestamp,"20991231.2")
        XCTAssertGreaterThanOrEqual(ProcessInfo.processInfo.systemUptime-start,1.9,"real Retry-After2 must delay the native request")
    }
    func testHistoricalDiscoveryUsesSelectedReferenceTable() async throws {
        // Private invalid table controls retain the genuine historical station rows.
        let fixtures=try path("OTC_HISTORY_SW_PROOF_ROOT")
        let directory=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at:directory) }
        let instant=try XCTUnwrap(parseTime("2026-10-11T00:00:00Z"))
        let targets=["OTC-28c56e20","OTC-541f1a73"]
        for label in ["valid","missing_m2","missing_s2","missing_n2","model_mismatch"] {
            let local=directory.appendingPathComponent(label)
            try FileManager.default.createDirectory(at:local,withIntermediateDirectories:true)
            for suffix in ["json","jsonl","meta.json","sha256"] {
                let name="OTC_20261011."+suffix
                try FileManager.default.copyItem(at:URL(fileURLWithPath:fixtures+"/inputs/"+label+"/"+name),to:local.appendingPathComponent(name))
            }
            for mode in [Mode.eager,Mode.stream] {
                let file=local.appendingPathComponent("OTC_20261011."+(mode == .eager ? "json":"jsonl"))
                for pass in 0...1 {
                    let client=try await OpenTideConstants.open(file:file.path,cacheDir:directory.appendingPathComponent("cache").path,mode:mode)
                    let release=client.release
                    defer { client.close() }
                    XCTAssertTrue(release.lruOrder.isEmpty)
                    let clientCursor=try client.iterStations(includeFlagged:true,includeFallback:true)
                    let releaseCursor=try release.iterStations(includeFlagged:true,includeFallback:true)
                    XCTAssertTrue(release.lruOrder.isEmpty,"historical admission must not materialize reference Stations")
                    var clientIds=[String](),releaseIds=[String]()
                    while let station=try clientCursor() { clientIds.append(station.stationId) }
                    while let station=try releaseCursor() { releaseIds.append(station.stationId) }
                    let discovered=try client.stations(includeFlagged:true,includeFallback:true).map(\.stationId)
                    XCTAssertEqual(clientIds,releaseIds)
                    XCTAssertEqual(discovered,clientIds)
                    XCTAssertEqual(try release.stations(includeFlagged:true,includeFallback:true).map(\.stationId),discovered)
                    for id in targets {
                        XCTAssertEqual(discovered.contains(id),label=="valid","\(label) \(mode.rawValue) pass=\(pass) \(id)")
                        let station=try client.requireStation(stationId:id)
                        let original=station.raw
                        XCTAssertEqual(try release.requireStation(stationId:id).raw,original)
                        if label=="valid" {
                            XCTAssertTrue(try client.extremes(stationId:id,start:instant,stop:instant,datum:"chart").historicalOffsets)
                        } else {
                            for call in [
                                { try client.extremes(stationId:id,start:instant,stop:instant,datum:"chart") },
                                { try release.extremes(stationId:id,start:instant,stop:instant,datum:"chart") }
                            ] {
                                XCTAssertThrowsError(try call()) { error in
                                    let value=error as? OpenTideConstantsError
                                    XCTAssertEqual(value?.code,label=="model_mismatch" ? "unsupported_convention":"unsupported_constituent")
                                    if label.hasPrefix("missing_") { XCTAssertEqual(value?.fields["constituent"]?.string,String(label.dropFirst(8)).uppercased()) }
                                }
                            }
                        }
                        XCTAssertEqual(station.raw,original)
                        print("HISTORY_DISCOVERY label=\(label) mode=\(mode.rawValue) pass=\(pass) station=\(id) advertised=\(discovered.contains(id)) identity=preserved prediction_guard=preserved")
                    }
                    if mode == .stream { XCTAssertTrue(FileManager.default.fileExists(atPath:local.appendingPathComponent("index-v1.json").path)) }
                }
            }
        }
    }
    func testEffectiveTypedQuantityControls() async throws {
        // Private injected controls derived from retained source rows; not upstream defects.
        let fixtures=try path("OTC_QUANTITY_CONTROLS")
        let cache=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at:cache) }
        let original=try JSONValue.parse(Data(contentsOf:URL(fileURLWithPath:fixtures+"/authentic/OTC_20261011.json")))
        for mode in [Mode.eager,Mode.stream] {
            for label in ["authentic","null_both","absent_both","unknown_pair","unknown_candidate_null","known_distinct","known_same","ok_before_flagged"] {
                let url=URL(fileURLWithPath:fixtures+"/"+label+"/OTC_20261011.json")
                let document=try JSONValue.parse(Data(contentsOf:url))
                let client=try await OpenTideConstants.open(file:url.path,cacheDir:cache.path,mode:mode,commercialOnly:true)
                defer { client.close() }
                for raw in document["stations"].array {
                    let id=try XCTUnwrap(raw["station_id"].string)
                    let source=try XCTUnwrap(original["stations"].array.first { $0["station_id"].string==id })
                    let station=try client.requireStation(stationId:id)
                    let expected:String?
                    if ["null_both","absent_both","unknown_candidate_null","known_distinct"].contains(label) { expected=nil }
                    else if label=="authentic" { expected=raw["recommended_set_id"].string }
                    else { expected=source["constant_sets"].array.first?["set_id"].string }
                    XCTAssertEqual(station.recommendedSet?.setId,expected,"\(label) \(mode.rawValue) \(id)")
                    XCTAssertEqual(station.raw,raw)
                    XCTAssertEqual(station.sourceRecords.map(\.raw),source["source_records"].array)
                    let originalSet=try XCTUnwrap(station.constantSet(setId:raw["recommended_set_id"].string!))
                    if label.hasPrefix("unknown") || ["null_both","absent_both"].contains(label) { XCTAssertEqual(originalSet.quantity,.other) }
                    print("QUANTITY_CONTROL label=\(label) mode=\(mode.rawValue) station=\(id) recommended=\(station.recommendedSet?.setId ?? "null") expected=\(expected ?? "null") raw=preserved source=preserved")
                }
            }
            do {
                _=try await OpenTideConstants.open(file:fixtures+"/wrong_primitive/OTC_20261011.json",cacheDir:cache.path,mode:mode,commercialOnly:true)
                XCTFail("wrong quantity primitive must fail during load")
            } catch {
                XCTAssertEqual((error as? OpenTideConstantsError)?.code,"invalid_release")
                XCTAssertEqual((error as? OpenTideConstantsError)?.message,"constant set: quantity wrong type")
            }
        }
    }
    func testForeignStationOwnershipWithEqualRaw() async throws {
        let fixtures=try path("OTC_MD6_FIXTURES")
        let cache=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at:cache) }
        for mode in [Mode.eager,Mode.stream] {
            let old=try await OpenTideConstants.open(file:fixtures+"/OTC_20991231.jsonl",cacheDir:cache.path,mode:mode)
            let current=try await OpenTideConstants.open(file:fixtures+"/OTC_20991231.2.jsonl",cacheDir:cache.path,mode:mode)
            defer { old.close();current.close() }
            XCTAssertEqual(old.release.datestamp,"20991231");XCTAssertEqual(current.release.datestamp,"20991231.2")
            for id in ["OTC-T-0001","OTC-T-0002","OTC-T-0003"] {
                let foreign=try old.requireStation(stationId:id),own=try current.requireStation(stationId:id)
                XCTAssertEqual(foreign.raw,own.raw);XCTAssertEqual(foreign,own)
                let expected=try current.attribution(stations:[own])
                XCTAssertFalse(expected.isEmpty)
                var code:String?
                do { _=try current.attribution(stations:[foreign]) } catch { code=(error as? OpenTideConstantsError)?.code }
                print("MD6_VALUE mode=\(mode.rawValue) station=\(id) raw_equal=\(foreign.raw==own.raw) value_equal=\(foreign==own) own=pass foreign_code=\(code ?? "accepted")")
                XCTAssertEqual(code,"invalid_argument")
                current.release.lru.removeAll();current.release.lruOrder.removeAll()
                let rematerialized=try current.requireStation(stationId:id)
                XCTAssertEqual(rematerialized,own);XCTAssertEqual(rematerialized.raw,own.raw)
                XCTAssertEqual(try current.attribution(stations:[own]),expected)
                XCTAssertEqual(try current.attribution(stations:[rematerialized]),expected)
                XCTAssertEqual(try current.station(stationId:id),own)
                XCTAssertEqual(rematerialized.sourceRecords,own.sourceRecords)
                XCTAssertEqual(rematerialized.constantSets(includeNoConstants:true),own.constantSets(includeNoConstants:true))
            }
            let retained=try current.requireStation(stationId:"OTC-T-0001")
            current.close()
            XCTAssertThrowsError(try current.attribution(stations:[retained])) { error in XCTAssertEqual((error as? OpenTideConstantsError)?.code,"io") }
            XCTAssertEqual(retained.stationId,"OTC-T-0001")
        }
        weak var weakRelease:Release?
        func detached() async throws -> Station {
            let client=try await OpenTideConstants.open(file:fixtures+"/OTC_20991231.2.jsonl",cacheDir:cache.path,mode:.stream)
            weakRelease=client.release
            let station=try client.requireStation(stationId:"OTC-T-0001")
            client.close()
            return station
        }
        let retained=try await detached()
        XCTAssertNil(weakRelease,"Station ownership must not retain Release or Reader data")
        XCTAssertEqual(retained.stationId,"OTC-T-0001")
        print("MD6_CONTROL same_release_lru=pass raw_values=pass source_provenance=pass id_api=pass closed=io retained_release=none equality=unchanged hash=not_Hashable")
    }
func phase(_ value:String) { FileHandle.standardError.write(Data(("PHASE " + value + "\n").utf8)) }
func count(_ phaseName:String,_ call:()throws->[Station]) rethrows -> Int {
    phase(phaseName + "_begin")
    let value=try call().count
    phase(phaseName + "_end")
    return value
}
    func path(_ key:String)throws->String { guard let p=ProcessInfo.processInfo.environment[key] else { throw OpenTideConstantsError.invalidArgument("required real artifact environment \(key) absent") };return p }
    func testActualSourceDataAndFilters()throws {
        let url=URL(fileURLWithPath:try path("OTC_CORE_NATIVE_JSONL"))
        phase("stream_load_begin");let r=try Reader.load(url,mode:.stream,commercialOnly:false,commercialBasis:"strict",historicalOffsetsPolicy:"fallback",indexPath:ProcessInfo.processInfo.environment["OTC_CORE_NATIVE_INDEX"].map { URL(fileURLWithPath:$0) })
        phase("stream_load_end");var sources=0,strings=0,fits=0
        try eachLine(url) { data,_ in
            let raw=try JSONValue.parse(data)
            guard (raw["status"].string ?? "active")=="active" else { return }
            let s=try r.requireStation(stationId:raw["station_id"].string!)
            XCTAssertEqual(s.raw,raw)
            XCTAssertEqual(s.sourceRecords.map(\.raw),raw["source_records"].array)
            for src in s.sourceRecords {
                sources+=1
                for row in src.originalHarmonics?["rows"].array ?? [] { strings+=row.array.count;XCTAssertTrue(row.array.allSatisfy { $0.string != nil }) }
                func docs(_ v:JSONValue) {
                    switch v { case .string(let s): if s.contains("\n") && s.count>500 { fits+=1 };case .array(let a):a.forEach(docs);case .object(let o):o.values.forEach(docs);default:break }
                }
                docs(src.originalMetadata)
            }
        }
        phase("raw_audit_end");let noaa=try r.entries.filter { $0.summary["subordinate_offsets"]["offset_id"].string != nil }.map { try r.requireStation(stationId:$0.id) }
        XCTAssertEqual(noaa.count,2)
        phase("default_discovery_begin");let discovered=Set(try r.stations().map(\.stationId))
        for s in noaa { XCTAssertTrue(discovered.contains(s.stationId));XCTAssertEqual(s.subordinateOffsets?.vintage?.currentAccuracy,"unverified");XCTAssertEqual(s.subordinateOffsets?.vintage?.reference2020Equivalence,"disagrees") }
        phase("default_discovery_end");let restricted=try Reader.load(url,mode:.stream,commercialOnly:false,commercialBasis:"strict",historicalOffsetsPolicy:"exclude")
        phase("strict_load_end");let strictIds=Set(try restricted.stations(includeFlagged:true,includeFallback:true).map(\.stationId))
        for s in noaa { XCTAssertFalse(strictIds.contains(s.stationId));XCTAssertNotNil(try restricted.station(stationId:s.stationId)) }
        phase("strict_discovery_end");let base=try count("default_count") { try r.stations() },flagged=try count("flagged_count") { try r.stations(includeFlagged:true) },fallback=try count("fallback_count") { try r.stations(includeFallback:true) },both=try count("both_count") { try r.stations(includeFlagged:true,includeFallback:true) }
        XCTAssertLessThanOrEqual(base,flagged);XCTAssertLessThanOrEqual(base,fallback);XCTAssertLessThanOrEqual(flagged,both)
        phase("four_discovery_counts_end");print("NATIVE_VALUE sources=\(sources) original_string_cells=\(strings) fit_text_documents=\(fits) counts=\(base)/\(flagged)/\(fallback)/\(both)")
        if ProcessInfo.processInfo.environment["OTC_CORE_NATIVE_FULL"]=="1" { XCTAssertEqual(sources,27372);XCTAssertEqual(strings,4354200);XCTAssertEqual(try r.stationCount,16038);XCTAssertEqual([base,flagged,fallback,both],[6715,9528,9549,10002]) };let retained=noaa[0];phase("close_begin");r.close();restricted.close();phase("close_end");XCTAssertThrowsError(try r.station(stationId:retained.stationId));XCTAssertEqual(retained.subordinateOffsets?.vintage?.currentValidity,"unestablished");phase("retained_book_station_read_after_close")
    }
    func testHistoricalMalformedOwnAndSourceControls()throws {
        let url=URL(fileURLWithPath:try path("OTC_CORE_NATIVE_JSONL"));let r=try Reader.load(url,mode:.stream,commercialOnly:false,commercialBasis:"strict",historicalOffsetsPolicy:"fallback")
        let s=try r.entries.first { $0.summary["subordinate_offsets"]["offset_id"].string != nil }.map { try r.requireStation(stationId:$0.id) }!
        for key in ["qc_status","source_record_id","reference_station_id","height_offset_high"] {
            var d=s.raw.object,o=d["subordinate_offsets"]!.object;o[key] = .bool(true);d["subordinate_offsets"] = .object(o)
            XCTAssertThrowsError(try Reader.station(.object(d),conventions:r.convById,licences:r.licById,kind:s.kind,recommended:nil))
        }
        var d=s.raw.object;d["source_records"] = .array([])
        XCTAssertThrowsError(try Reader.station(.object(d),conventions:r.convById,licences:r.licById,kind:s.kind,recommended:nil))
        XCTAssertThrowsError(try r.near(lat:.nan,lon:0,radiusKm:1))
        XCTAssertThrowsError(try r.search(name:"   "))
    }
func testActualIndexFirstQueries() throws {
    let url=URL(fileURLWithPath:try path("OTC_CORE_NATIVE_JSONL"))
    func load() throws -> Release { try Reader.load(url,mode:.stream,commercialOnly:false,commercialBasis:"strict",historicalOffsetsPolicy:"fallback") }
    let search=try load()
    let found=try search.search(name:"Lockwoods Folly",limit:1)
    XCTAssertEqual(found.count,1);XCTAssertEqual(found[0].stationId,"OTC-28c56e20");XCTAssertEqual(found[0].subordinateOffsets?.offsetId,"noaa-2020-atlantic-table2-2513")
    XCTAssertEqual(search.lruOrder.count,1,"limit1 search must decode only its actual winner")
    phase("index_search_decoded_\(search.lruOrder.count)_id_\(found[0].stationId)")
    let near=try load()
    let target=try near.entries.first { $0.summary["subordinate_offsets"]["offset_id"].string=="noaa-2020-pacific-table2-517" }.map { try near.requireStation(stationId:$0.id) }!
    near.lru.removeAll();near.lruOrder.removeAll()
    let winner=try near.nearest(lat:target.lat,lon:target.lon)
    XCTAssertEqual(winner?.station.stationId,"OTC-541f1a73");XCTAssertEqual(winner?.station.stationId,target.stationId);XCTAssertEqual(winner?.distanceKm,0)
    XCTAssertEqual(near.lruOrder.count,1,"nearest must decode only its actual winner")
    phase("index_nearest_decoded_\(near.lruOrder.count)_id_\(winner!.station.stationId)")
    let iterator=try load()
    let sequence=try iterator.iterStations()
    XCTAssertEqual(iterator.lruOrder.count,0,"constructing iterator must not decode stations")
    let steps=sequence;let first=try steps()
    XCTAssertNotNil(first);if try iterator.stationCount==1008 { XCTAssertEqual(first?.stationId,"OTC-000d594d") };XCTAssertEqual(iterator.lruOrder.count,1,"first iterator step must decode one station")
    phase("index_iterator_decoded_\(iterator.lruOrder.count)_id_\(first!.stationId)")
}
func testActualReleaseLifetimeObservation() throws {
    let url=URL(fileURLWithPath:try path("OTC_CORE_NATIVE_JSONL"))
    func observe(_ label:String) { phase(label);Thread.sleep(forTimeInterval:0.15) }
    func workload(_ label:String) throws {
        weak var weakRelease:Release?
        func scope() throws {
            let release=try Reader.load(url,mode:.stream,commercialOnly:false,commercialBasis:"strict",historicalOffsetsPolicy:"fallback")
            weakRelease=release
            observe(label + "_loaded")
            let all=try release.stations(includeFlagged:true,includeFallback:true)
            XCTAssertEqual(all.count,504)
            observe(label + "_all_results_held")
            let defaults=try release.stations()
            XCTAssertEqual(defaults.count,223)
            observe(label + "_two_result_arrays_held")
            let rawSources=all.reduce(0) { $0 + $1.sourceRecords.count }
            release.close()
            XCTAssertEqual(all.count,504);XCTAssertEqual(defaults.count,223)
            XCTAssertTrue(all.flatMap(\.sourceRecords).allSatisfy { !$0.raw.isNull })
            observe(label + "_closed_with_result_arrays_held")
            print("LIFETIME_VALUE \(label) all=\(all.count) defaults=\(defaults.count) source_records=\(rawSources)")
            withExtendedLifetime((all,defaults)) {}
        }
        try scope()
        XCTAssertNil(weakRelease,"released result scopes must not retain Release by an ARC cycle")
        observe(label + "_release_and_arrays_scope_exited")
    }
    for run in 0..<2 {
        try workload("normal_\(run)")
        try autoreleasepool { try workload("pool_control_\(run)") }
        observe("pool_control_\(run)_drained")
    }
    weak var weakIteratorRelease:Release?
    var sequence:(()throws->Station?)?
    do {
        let release=try Reader.load(url,mode:.stream,commercialOnly:false,commercialBasis:"strict",historicalOffsetsPolicy:"fallback")
        weakIteratorRelease=release
        sequence=try release.iterStations();release.close()
    }
    XCTAssertNotNil(weakIteratorRelease,"lazy sequence legitimately owns its Release")
    XCTAssertThrowsError(try sequence?()) { error in
        guard let native=error as? OpenTideConstantsError else { return XCTFail("unexpected error \(error)") }
        XCTAssertEqual(native.code,"io");XCTAssertEqual(native.message,"the release is closed")
    }
    observe("closed_release_retained_by_iterator")
    sequence=nil
    XCTAssertNil(weakIteratorRelease,"dropping iterator must release owned Release")
    observe("iterator_dropped_release_deallocated")
}
func testActualSingleReleaseMobileBaseline() throws {
    let loadPoolControl=ProcessInfo.processInfo.environment["OTC_MOBILE_LOAD_POOL_CONTROL"]=="1"
    let profileControl=ProcessInfo.processInfo.environment["OTC_MOBILE_PROFILE_CONTROL"]=="1"
    func observe(_ label:String) {
        phase("mobile_" + label)
        if (loadPoolControl && ["before_open","load_returned_inside_pool","after_load_pool_exit","end","release_scope_exited"].contains(label)) || (profileControl && ["before_open","after_open","end","release_scope_exited"].contains(label)) {
            XCTAssertEqual(FileHandle.standardInput.readData(ofLength:1).count,1)
        } else { Thread.sleep(forTimeInterval:0.3) }
    }
    weak var weakRelease:Release?
    func scope() throws {
        let url=URL(fileURLWithPath:try path("OTC_CORE_NATIVE_JSONL"))
        observe("before_open")
        let release:Release
        if loadPoolControl {
            release=try autoreleasepool {
                let value=try Reader.load(url,mode:.stream,commercialOnly:false,commercialBasis:"strict",historicalOffsetsPolicy:"fallback",indexPath:nil)
                observe("load_returned_inside_pool")
                return value
            }
            observe("after_load_pool_exit")
        } else {
            release=try Reader.load(url,mode:.stream,commercialOnly:false,commercialBasis:"strict",historicalOffsetsPolicy:"fallback",indexPath:nil)
        }
        weakRelease=release
        observe("after_open")
        let found=try release.search(name:"Springmaid Pier, Myrtle beach",limit:1,match:"exact")
        XCTAssertEqual(found.count,1);XCTAssertEqual(found[0].stationId,"OTC-a6c00a3f")
        observe("after_search")
        let nearest=try XCTUnwrap(release.nearest(lat:33.654998779296875,lon:-78.91829681396484))
        XCTAssertEqual(nearest.station.stationId,"OTC-a6c00a3f");XCTAssertEqual(nearest.distanceKm,0)
        observe("after_nearest")
        let selected=try XCTUnwrap(release.station(stationId:"OTC-a6c00a3f"))
        XCTAssertEqual(selected.name,"Springmaid Pier, Myrtle beach");XCTAssertEqual(selected.country,"USA")
        XCTAssertEqual(selected.type,.reference);XCTAssertEqual(selected.kind,.tide)
        XCTAssertEqual(selected.timezone,"America/New_York");XCTAssertEqual(selected.recommendedSet?.setId,"OTC-a6c00a3f/noaa/8661070")
        observe("after_selected_station")
        let values:JSONValue = .object(["search_id":.string(found[0].stationId),"nearest_id":.string(nearest.station.stationId),"nearest_distance_km":.number(nearest.distanceKm),"station_id":.string(selected.stationId),"name":.string(selected.name!),"country":.string(selected.country!),"type":.string(selected.type.rawValue),"kind":.string(selected.kind!.rawValue),"timezone":.string(selected.timezone!),"recommended_set_id":.string(selected.recommendedSet!.setId)])
        print("MOBILE_VALUE " + String(data:try values.data(),encoding:.utf8)!)
        observe("end")
        withExtendedLifetime((release,found,nearest,selected)) {}
    }
    try scope()
    XCTAssertNil(weakRelease)
    observe("release_scope_exited")
}
func testActualBufferedLineReaderControls() throws {
    let original=URL(fileURLWithPath:try path("OTC_CORE_NATIVE_JSONL"))
    var rows:[Data]=[]
    try eachLine(original) { data,_ in rows.append(data) }
    XCTAssertEqual(rows.count,8)
    let expected=try rows.map(JSONValue.parse)
    let directory=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(at:directory,withIntermediateDirectories:true)
    defer { try? FileManager.default.removeItem(at:directory) }
    var bytes=Data([10]),offsets:[UInt64]=[],lineBytes:[Data]=[],unicodeBoundary:Int?
    for row in rows {
        var line=row
        if unicodeBoundary==nil,let index=row.firstIndex(where: { $0>=0xC0 }) {
            let relative=row.distance(from:row.startIndex,to:index)
            let padding=(65535-(bytes.count+relative)%65536+65536)%65536
            line=Data(repeating:32,count:padding);line.append(row)
            unicodeBoundary=bytes.count+padding+relative
        }
        offsets.append(UInt64(bytes.count));lineBytes.append(line);bytes.append(line)
        if offsets.count<rows.count { bytes.append(contentsOf:[13,10,13,10]) }
    }
    XCTAssertEqual(try XCTUnwrap(unicodeBoundary)%65536,65535)
    XCTAssertNotEqual(bytes.last,10)
    let fixture=directory.appendingPathComponent("actual-boundaries.jsonl")
    try bytes.write(to:fixture)
    func verify(_ url:URL) throws {
        var index=0
        try eachLine(url) { data,offset in
            XCTAssertLessThan(index,expected.count)
            guard index<expected.count else { return XCTFail("unexpected extra line") }
            XCTAssertEqual(offset,offsets[index]);XCTAssertEqual(data,lineBytes[index])
            XCTAssertEqual(try JSONValue.parse(data),expected[index]);index+=1
        }
        XCTAssertEqual(index,expected.count)
    }
    try verify(fixture)
    let fifo=directory.appendingPathComponent("actual-short-reads.fifo")
    let createFIFO=Process();createFIFO.executableURL=URL(fileURLWithPath:"/usr/bin/mkfifo");createFIFO.arguments=[fifo.path]
    try createFIFO.run();createFIFO.waitUntilExit();XCTAssertEqual(createFIFO.terminationStatus,0)
    let writer=Process();writer.executableURL=URL(fileURLWithPath:"/usr/local/rbenv/versions/3.2.2/bin/ruby")
    writer.arguments=[try path("OTC_CORE_NATIVE_FIFO_WRITER"),fifo.path,fixture.path]
    try writer.run();try verify(fifo);writer.waitUntilExit();XCTAssertEqual(writer.terminationStatus,0)
    XCTAssertThrowsError(try eachLine(directory.appendingPathComponent("absent.jsonl")) { _,_ in })
    XCTAssertThrowsError(try eachLine(directory) { _,_ in })
    struct BodyProbeError:Error {}
    XCTAssertThrowsError(try eachLine(fixture) { _,_ in throw BodyProbeError() }) { error in XCTAssertTrue(error is BodyProbeError) }
    print("BUFFER_VALUE actual_rows=\(rows.count) offsets=exact raw=exact utf8_split=\(unicodeBoundary!) crlf=pass blank=pass final_no_newline=pass native_fifo_short_writes=pass missing_file=pass read_error=pass body_error=pass")
}
}
