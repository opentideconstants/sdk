import XCTest
@testable import OpenTideConstants
final class CacheTests:XCTestCase {
    func testCanonicalGeneratedCacheBytes()throws {
        let root=URL(fileURLWithPath:#filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        let golden=try JSONValue.parse(Data(contentsOf:root.appendingPathComponent("conformance/canonical/cache-golden.json")))
        let output=ProcessInfo.processInfo.environment["OTC_ENC_PROOF_DIR"].map { URL(fileURLWithPath:$0) }
        if let output { try FileManager.default.createDirectory(at:output,withIntermediateDirectories:true) }
        func input(_ vector:JSONValue)throws->JSONValue {
            if let hex=vector["binary64_hex"].string {
                return .number(Double(bitPattern:try XCTUnwrap(UInt64(hex,radix:16))))
            }
            return vector["input"]
        }
        for vector in golden["cases"].array {
            let id=try XCTUnwrap(vector["id"].string)
            let actual=try input(vector).data(),expected=Data(try XCTUnwrap(vector["expected"].string).utf8)
            if let output { try Cache.atomic(actual,output.appendingPathComponent(id+".json")) }
            print("ENC-SW \(id) actual_hex=\(actual.map { String(format:"%02x",$0) }.joined()) expected_hex=\(expected.map { String(format:"%02x",$0) }.joined()) match=\(actual==expected)")
            XCTAssertEqual(actual,expected,id)
        }
        for vector in golden["refusals"].array {
            let id=try XCTUnwrap(vector["id"].string)
            if let hex=vector["raw_json_hex"].string {
                let bytes=stride(from:0,to:hex.count,by:2).map { position in
                    UInt8(hex.dropFirst(position).prefix(2),radix:16)!
                }
                XCTAssertThrowsError(try JSONValue.parse(Data(bytes)),id)
            } else { XCTAssertThrowsError(try input(vector).data(),id) }
            print("ENC-SW refusal \(id)")
        }
    }
    private final class NativeFixture {
        let directory:URL
        let process=Process()
        let input=Pipe()
        let exited=DispatchSemaphore(value:0)
        let ready:JSONValue
        init(controls:JSONValue = .object([:]))throws {
            let environment=ProcessInfo.processInfo.environment
            guard let root=environment["OTC_SIO_REPO_ROOT"],let host=environment["OTC_SIO_FIXTURE_HOST"],let ruby=environment["OTC_SIO_RUBY"],let proof=environment["OTC_SIO_PROOF_DIR"] else { throw OpenTideConstantsError.invalidArgument("native fixture environment absent") }
            directory=URL(fileURLWithPath:proof).appendingPathComponent(UUID().uuidString)
            try FileManager.default.createDirectory(at:directory,withIntermediateDirectories:true)
            try controls.data().write(to:directory.appendingPathComponent("controls.json"),options:.atomic)
            process.executableURL=URL(fileURLWithPath:ruby)
            process.arguments=[host,directory.path]
            process.currentDirectoryURL=URL(fileURLWithPath:root)
            process.environment=environment
            process.standardInput=input
            process.terminationHandler={ [exited] _ in exited.signal() }
            process.standardOutput=try FileHandle(forWritingTo:directory.appendingPathComponent("stdout.log").creatingEmptyFile())
            process.standardError=try FileHandle(forWritingTo:directory.appendingPathComponent("stderr.log").creatingEmptyFile())
            try process.run()
            let path=directory.appendingPathComponent("ready.json"),deadline=Date().addingTimeInterval(10)
            while !FileManager.default.fileExists(atPath:path.path),process.isRunning,Date()<deadline { Thread.sleep(forTimeInterval:0.01) }
            guard FileManager.default.fileExists(atPath:path.path) else { try input.fileHandleForWriting.close();_ = exited.wait(timeout:.now()+10);throw OpenTideConstantsError.io("fixture failed to start: \(try String(contentsOf:directory.appendingPathComponent("stderr.log")))") }
            ready=try JSONValue.parse(Data(contentsOf:path))
        }
        var base:String { ready["base_url"].string! }
        var proxy:String { ready["proxy_url"].string! }
        var cache:String { directory.appendingPathComponent("cache").path }
        func control(_ value:JSONValue)throws { try value.data().write(to:directory.appendingPathComponent("controls.json"),options:.atomic) }
        func finish()throws->JSONValue {
            try input.fileHandleForWriting.close()
            guard exited.wait(timeout:.now()+10) == .success else { throw OpenTideConstantsError.io("fixture teardown timed out") }
            XCTAssertEqual(process.terminationStatus,0)
            let requests=try JSONValue.parse(Data(contentsOf:directory.appendingPathComponent("requests.json")))
            XCTAssertEqual(requests["errors"].array,[])
            return requests
        }
        deinit { if process.isRunning { try? input.fileHandleForWriting.close();_ = exited.wait(timeout:.now()+10) } }
    }
    private func assertNativeReceipt(_ fixture:NativeFixture,doi:String?=nil)throws {
        let directory=URL(fileURLWithPath:fixture.cache).appendingPathComponent("v1/releases/20991231.2")
        let bytes=try Data(contentsOf:directory.appendingPathComponent(".verified")),marker=try JSONValue.parse(bytes)
        XCTAssertEqual(Set(marker.object.keys),Set(["datestamp","files","format_version","min_reader_version","zenodo_version_doi","verified_at","by"]))
        XCTAssertEqual(marker["zenodo_version_doi"],doi.map(JSONValue.string) ?? .null)
        XCTAssertEqual(marker["format_version"],.string("1.0"));XCTAssertEqual(marker["min_reader_version"],.string("1.0"))
        XCTAssertEqual(bytes,try marker.data())
        let original=URL(fileURLWithPath:fixture.ready["fixture_root"].string!)
        for (name,row) in marker["files"].object {
            XCTAssertEqual(Set(row.object.keys),Set(["sha256","size","url"]))
            let path=directory.appendingPathComponent(name),data=try Data(contentsOf:path)
            XCTAssertEqual(data,try Data(contentsOf:original.appendingPathComponent(name)))
            XCTAssertEqual(row["sha256"],.string(SHA256.digest(data)))
            XCTAssertEqual(row["size"],.integer(Int64(data.count)))
            XCTAssertFalse(name.hasSuffix(".sha256"))
        }
        XCTAssertEqual(try Data(contentsOf:directory.appendingPathComponent("OTC_20991231.2.sha256")),try Data(contentsOf:original.appendingPathComponent("OTC_20991231.2.sha256")))
        XCTAssertFalse(try FileManager.default.contentsOfDirectory(atPath:directory.path).contains { $0.hasPrefix(".tmp-") || $0==".lock" })
    }
    func testNativeReceiptAcquisitionAndOtherModeMerge()async throws {
        for mode in [Mode.eager,.stream] {
            let fixture=try NativeFixture()
            let client=try await OpenTideConstants.open(release:"20991231.2",cacheDir:fixture.cache,mode:mode,baseUrl:fixture.base,verifyOnOpen:true)
            XCTAssertEqual(client.loadedFrom,.download);XCTAssertNotNil(try client.station(stationId:"OTC-T-0001"));client.close()
            try assertNativeReceipt(fixture)
            if mode == .eager {
                let receipt=URL(fileURLWithPath:fixture.cache).appendingPathComponent("v1/releases/20991231.2/.verified")
                var old=try JSONValue.parse(Data(contentsOf:receipt)).object,row=old["files"]!["OTC_20991231.2.json"].object
                old["zenodo_version_doi"] = .string("10.5072/zenodo.9")
                row.removeValue(forKey:"url");row["future_private"] = .bool(true)
                row["sha256"] = .string(row["sha256"]!.string!.uppercased())
                old["files"] = .object(["OTC_20991231.2.json":.object(row)])
                try Cache.atomic(JSONValue.object(old).data(),receipt)
                let stream=try await OpenTideConstants.open(release:"20991231.2",cacheDir:fixture.cache,mode:.stream,baseUrl:fixture.base,verifyOnOpen:true)
                XCTAssertEqual(stream.loadedFrom,.download);XCTAssertEqual(stream.release.zenodoVersionDoi,"10.5072/zenodo.9");stream.close()
                try assertNativeReceipt(fixture,doi:"10.5072/zenodo.9")
                let marker=try JSONValue.parse(Data(contentsOf:receipt))
                XCTAssertEqual(marker["files"].object.count,3);XCTAssertEqual(marker["files"]["OTC_20991231.2.json"]["url"],.null)
            }
            for cachedMode in [Mode.eager,.stream] where mode == .stream || cachedMode == .eager || FileManager.default.fileExists(atPath:URL(fileURLWithPath:fixture.cache).appendingPathComponent("v1/releases/20991231.2/OTC_20991231.2.jsonl").path) {
                let cached=try await OpenTideConstants.open(release:"20991231.2",cacheDir:fixture.cache,offline:true,mode:cachedMode,verifyOnOpen:true)
                XCTAssertEqual(cached.loadedFrom,.cache);XCTAssertNotNil(try cached.station(stationId:"OTC-T-0001"));cached.close()
            }
            _=try fixture.finish()
        }
    }
    func testNativeReceiptLockedReread()async throws {
        for state in ["valid","malformed","absent"] {
            let fixture=try NativeFixture(),cache=Cache(root:URL(fileURLWithPath:fixture.cache))
            let eager=try await OpenTideConstants.open(release:"20991231.2",cacheDir:fixture.cache,baseUrl:fixture.base);eager.close()
            let directory=try cache.releaseDir("20991231.2"),receipt=directory.appendingPathComponent(".verified")
            let original=try JSONValue.parse(Data(contentsOf:receipt))
            let token=try await cache.takeLock(directory)
            let cachePath=fixture.cache,base=fixture.base
            let task=Task {
                let client=try await OpenTideConstants.open(release:"20991231.2",cacheDir:cachePath,mode:.stream,baseUrl:base,verifyOnOpen:true)
                defer { client.close() }
                return (client.loadedFrom.rawValue,try client.station(stationId:"OTC-T-0001") != nil)
            }
            try await Task.sleep(nanoseconds:600_000_000)
            XCTAssertEqual(try Data(contentsOf:receipt),try original.data())
            if state == "valid" {
                var current=original.object;current["zenodo_version_doi"] = .string("10.5072/zenodo.8")
                try Cache.atomic(JSONValue.object(current).data(),receipt)
            } else if state == "malformed" { try Cache.atomic(Data("malformed".utf8),receipt) }
            else { try FileManager.default.removeItem(at:receipt) }
            cache.releaseLock(directory,token)
            let result=try await task.value
            XCTAssertEqual(result.0,"download");XCTAssertTrue(result.1)
            try assertNativeReceipt(fixture,doi:state == "valid" ? "10.5072/zenodo.8":nil)
            let marker=try JSONValue.parse(Data(contentsOf:receipt))
            XCTAssertEqual(marker["files"].object.count,state == "valid" ? 3:2)
            print("RECEIPT-SW locked reread \(state): rows=\(marker["files"].object.count) DOI=\(String(describing:marker["zenodo_version_doi"].string))")
            _=try fixture.finish()
        }
    }
    func testNativeDownloadThenOfflineCache()async throws {
        let fixture=try NativeFixture()
        let client=try await OpenTideConstants.open(cacheDir:fixture.cache,baseUrl:fixture.base,userAgent:"native-io-proof",verifyOnOpen:true)
        XCTAssertEqual(client.loadedFrom,.download)
        XCTAssertEqual(client.release.datestamp,"20991231.2")
        XCTAssertEqual(client.release.files.count,5)
        XCTAssertTrue(try client.verify())
        let offline=try await OpenTideConstants.open(cacheDir:fixture.cache,offline:true,baseUrl:fixture.base)
        XCTAssertEqual(offline.loadedFrom,.cache)
        XCTAssertEqual(offline.release.files.map(\.name),["OTC_20991231.2.json"])
        XCTAssertEqual(offline.release.files.first,client.release.files.first)
        XCTAssertEqual(try offline.release.stationCount,try client.release.stationCount)
        let destination=fixture.directory.appendingPathComponent("download")
        let paths=try await client.download(to:destination.path)
        XCTAssertEqual(paths.map { URL(fileURLWithPath:$0).lastPathComponent },["OTC_20991231.2.jsonl","OTC_20991231.2.meta.json","OTC_20991231.2.sha256"])
        for path in paths { XCTAssertEqual(try Data(contentsOf:URL(fileURLWithPath:path)),try Data(contentsOf:URL(fileURLWithPath:fixture.ready["fixture_root"].string!).appendingPathComponent(URL(fileURLWithPath:path).lastPathComponent))) }
        let identical=try await client.download(to:destination.path)
        XCTAssertEqual(identical,[])
        let local=try await OpenTideConstants.open(file:paths[0],mode:.stream,commercialBasis:"as_published_upstream",historicalOffsetsPolicy:"exclude")
        XCTAssertEqual(local.loadedFrom,.file)
        XCTAssertEqual(local.release.files.map(\.name),["OTC_20991231.2.json","OTC_20991231.2.json.gz","OTC_20991231.2.jsonl","OTC_20991231.2.meta.json"])
        XCTAssertTrue(local.release.files.allSatisfy { $0.url==nil && $0.sha256 != nil })
        XCTAssertEqual(local.release.files.compactMap(\.size),[25929,3974])
        let original=try await OpenTideConstants.open(file:URL(fileURLWithPath:fixture.ready["fixture_root"].string!).appendingPathComponent("OTC_20991231.2.jsonl").path)
        XCTAssertEqual(original.release.files.compactMap(\.size),[29916,4498,25929,3974])
        original.close()
        try Data("changed".utf8).write(to:destination.appendingPathComponent("OTC_20991231.2.jsonl"))
        do { _=try await client.download(to:destination.path);XCTFail("different existing content must be refused") }
        catch let error as OpenTideConstantsError { XCTAssertEqual(error.code,"file_exists") }
        let replaced=try await client.download(to:destination.path,overwrite:true)
        XCTAssertEqual(replaced.map { URL(fileURLWithPath:$0).lastPathComponent },["OTC_20991231.2.jsonl"])
        let refused=fixture.directory.appendingPathComponent("refused")
        try fixture.control(.object(["file_status":.object(["OTC_20991231.2.meta.json":.integer(404)])]))
        do { _=try await client.download(to:refused.path);XCTFail("listed 404 must fail before installation") }
        catch let error as OpenTideConstantsError { XCTAssertEqual(error.code,"network");XCTAssertEqual(error.fields["status"],.integer(404)) }
        XCTAssertEqual(try FileManager.default.contentsOfDirectory(atPath:refused.path),[])
        try fixture.control(.object([:]))
        XCTAssertEqual(local.release.commercialBasis,"as_published_upstream")
        XCTAssertEqual(local.release.historicalOffsetsPolicy,"exclude")
        local.close()
        client.close();offline.close()
        let requests=try fixture.finish()
        XCTAssertTrue(requests["http"].array.contains(.string("/OTC_latest-f1.json")))
    }
    func testNativeUpdateRetainsHeldRelease()async throws {
        let fixture=try NativeFixture(controls:.object(["latest":.string("20991231")]))
        let client=try await OpenTideConstants.open(cacheDir:fixture.cache,mode:.stream,baseUrl:fixture.base,commercialBasis:"as_published_upstream",historicalOffsetsPolicy:"exclude")
        XCTAssertEqual(client.loadedFrom,.download)
        XCTAssertEqual(client.release.datestamp,"20991231")
        XCTAssertEqual(client.release.files.count,5)
        XCTAssertTrue(try client.verify())
        let held=client.release,oldCount=try held.stationCount
        try fixture.control(.object(["latest":.string("20991231.2")]))
        let result=try await client.update()
        XCTAssertTrue(result.updated)
        XCTAssertEqual(result.from,"20991231");XCTAssertEqual(result.to,"20991231.2")
        XCTAssertEqual(try held.stationCount,oldCount)
        XCTAssertEqual(client.release.datestamp,"20991231.2")
        XCTAssertEqual(client.release.commercialBasis,"as_published_upstream")
        XCTAssertEqual(client.release.historicalOffsetsPolicy,"exclude")
        let pruned=try await client.prune(keep:0)
        XCTAssertEqual(pruned,[])
        client.close()
        XCTAssertThrowsError(try held.stationCount) { XCTAssertEqual(($0 as? OpenTideConstantsError)?.code,"io") }
        XCTAssertEqual(held.files.count,5)
        try fixture.control(.object(["latest":.string("20991231")]))
        let automatic=try await OpenTideConstants.open(cacheDir:fixture.directory.appendingPathComponent("auto-cache").path,baseUrl:fixture.base,autoUpdate:true,updateInterval:0.01)
        let beforeAutomatic=automatic.release
        XCTAssertNotNil(try beforeAutomatic.station(stationId:"OTC-T-0021"))
        try fixture.control(.object(["latest":.string("20991231.2")]))
        try await Task.sleep(nanoseconds:20_000_000)
        XCTAssertNil(try automatic.station(stationId:"OTC-T-0021"))
        XCTAssertEqual(automatic.release.datestamp,"20991231.2")
        XCTAssertNotNil(try beforeAutomatic.station(stationId:"OTC-T-0021"))
        try fixture.control(.object(["status":.integer(500)]))
        try await Task.sleep(nanoseconds:20_000_000)
        XCTAssertNotNil(try automatic.station(stationId:"OTC-T-0001"))
        XCTAssertEqual(automatic.lastError?.code,"network")
        try fixture.control(.object([:]))
        try await Task.sleep(nanoseconds:20_000_000)
        XCTAssertNotNil(try automatic.station(stationId:"OTC-T-0001"))
        XCTAssertNil(automatic.lastError)
        XCTAssertEqual(automatic.loadedFrom,.download)
        automatic.close()
        let requests=try fixture.finish()
        XCTAssertTrue(requests["http"].array.contains(.string("/OTC_20991231.sha256")))
    }
    func testNativeProxyAndNetworkErrorPrecedence()async throws {
        let fixture=try NativeFixture()
        let client=try await OpenTideConstants.open(cacheDir:fixture.cache,baseUrl:"http://fixture.invalid/",proxy:fixture.proxy)
        XCTAssertEqual(client.loadedFrom,.download)
        XCTAssertEqual(client.release.files.count,5)
        XCTAssertTrue(try client.verify())
        try fixture.control(.object(["status":.integer(500)]))
        let fallback=try await OpenTideConstants.open(cacheDir:fixture.cache,baseUrl:fixture.base)
        XCTAssertEqual(fallback.loadedFrom,.cacheAfterError)
        XCTAssertEqual(fallback.lastError?.code,"network")
        fallback.close()
        do { _=try await OpenTideConstants.open(cacheDir:fixture.cache,baseUrl:fixture.base,onNetworkError:.raise);XCTFail("raise must preserve network failure") }
        catch let error as OpenTideConstantsError { XCTAssertEqual(error.code,"network") }
        let corrupt=URL(fileURLWithPath:fixture.cache).appendingPathComponent("v1/releases/20991231.2/OTC_20991231.2.json")
        try Data("corrupt".utf8).write(to:corrupt)
        do { _=try await OpenTideConstants.open(cacheDir:fixture.cache,baseUrl:fixture.base);XCTFail("corrupt fallback must retain the original network error") }
        catch let error as OpenTideConstantsError { XCTAssertEqual(error.code,"network") }
        try fixture.control(.object([:]))
        let tls=try await OpenTideConstants.open(cacheDir:fixture.directory.appendingPathComponent("tls-cache").path,baseUrl:fixture.ready["tls_url"].string!,caFile:fixture.ready["ca_file"].string!)
        XCTAssertEqual(tls.loadedFrom,.download);tls.close()
        do { _=try await OpenTideConstants.open(cacheDir:fixture.directory.appendingPathComponent("untrusted-cache").path,baseUrl:fixture.ready["tls_url"].string!);XCTFail("untrusted CA must be refused") }
        catch let error as OpenTideConstantsError { XCTAssertEqual(error.code,"network") }
        let wrong=try NativeFixture(controls:.object(["wrong_san":.bool(true)]))
        do { _=try await OpenTideConstants.open(cacheDir:wrong.cache,baseUrl:wrong.ready["tls_url"].string!,caFile:wrong.ready["ca_file"].string!);XCTFail("wrong SAN must be refused") }
        catch let error as OpenTideConstantsError { XCTAssertEqual(error.code,"network") }
        let wrongRequests=try wrong.finish()
        XCTAssertTrue(wrongRequests["tls"].array.isEmpty)
        try fixture.control(.object(["downgrade":.bool(true)]))
        do { _=try await OpenTideConstants.open(cacheDir:fixture.directory.appendingPathComponent("downgrade-cache").path,baseUrl:fixture.ready["tls_url"].string!,caFile:fixture.ready["ca_file"].string!);XCTFail("HTTPS downgrade must be refused") }
        catch let error as OpenTideConstantsError { XCTAssertEqual(error.code,"network") }
        client.close()
        let requests=try fixture.finish()
        XCTAssertFalse(requests["proxy"].array.isEmpty)
        XCTAssertFalse(requests["tls"].array.isEmpty)
    }
    func testDigestAndDatestampGrammar()throws {
        XCTAssertEqual(SHA256.digest(Data("abc".utf8)),"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
        XCTAssertTrue(Cache.validStamp("20261011.10"));XCTAssertFalse(Cache.validStamp("20261011.1"));XCTAssertFalse(Cache.validStamp("20261011\n"));XCTAssertFalse(Cache.validStamp("../20261011"))
    }
    func testActualIndexTamperRebuild()throws {
        guard let path=ProcessInfo.processInfo.environment["OTC_CORE_NATIVE_JSONL"] else { throw OpenTideConstantsError.invalidArgument("real data environment absent") }
        let source=URL(fileURLWithPath:path),dir=FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at:dir,withIntermediateDirectories:true);defer { try? FileManager.default.removeItem(at:dir) }
        let data=dir.appendingPathComponent(source.lastPathComponent),meta=URL(fileURLWithPath:String(source.path.dropLast(6))+".meta.json")
        try FileManager.default.copyItem(at:source,to:data);try FileManager.default.copyItem(at:meta,to:dir.appendingPathComponent(meta.lastPathComponent))
        let index=dir.appendingPathComponent("index-v1.json")
        let r=try Reader.load(data,mode:.stream,commercialOnly:false,commercialBasis:"strict",historicalOffsetsPolicy:"fallback",indexPath:index)
        var doc=try JSONValue.parse(Data(contentsOf:index)).object;doc["stations"] = .array([]);try Cache.atomic(JSONValue.object(doc).data(),index)
        let rebuilt=try Reader.load(data,mode:.stream,commercialOnly:false,commercialBasis:"strict",historicalOffsetsPolicy:"fallback",indexPath:index)
        XCTAssertEqual(try rebuilt.stationCount,try r.stationCount)
        XCTAssertEqual(try JSONValue.parse(Data(contentsOf:index))["stations"].array.count,r.entries.count)
    }
    // A partial release entry that is a symlink is not a cache directory: prune must not lock, empty or remove
    // what it points to, whatever .verified marker the target holds.
    func testPrunePreservesExternalDataBehindPartialReleaseSymlinks()async throws {
        let repo=URL(fileURLWithPath:#filePath).deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        let file=repo.appendingPathComponent("conformance/fixtures/good/OTC_20991231.2.json").path
        let fm=FileManager.default
        for (label,marker) in [("empty-marker","{}" as String?),("broken-json","{broken json"),("absent-marker",nil)] {
            let root=fm.temporaryDirectory.appendingPathComponent("otc-swift-test-"+UUID().uuidString)
            defer { try? fm.removeItem(at:root) }
            let external=root.appendingPathComponent("external-user-data"),releases=root.appendingPathComponent("cache/v1/releases")
            try fm.createDirectory(at:external,withIntermediateDirectories:true);try fm.createDirectory(at:releases,withIntermediateDirectories:true)
            try Data("external record and provenance \(label)\n".utf8).write(to:external.appendingPathComponent("source-record-original"))
            if let marker { try Data(marker.utf8).write(to:external.appendingPathComponent(".verified")) }
            let link=releases.appendingPathComponent("20991231.30")
            try fm.createSymbolicLink(atPath:link.path,withDestinationPath:"../../../external-user-data")
            let old=Date().addingTimeInterval(-300)
            try fm.setAttributes([.modificationDate:old],ofItemAtPath:external.path)
            // An old link: age alone does not protect it.
            var times=[timeval(tv_sec:Int(old.timeIntervalSince1970),tv_usec:0),timeval(tv_sec:Int(old.timeIntervalSince1970),tv_usec:0)]
            XCTAssertEqual(lutimes(link.path,&times),0,label)
            let originalMtime=try fm.attributesOfItem(atPath:external.path)[.modificationDate] as? Date
            var originals:[String:Data]=[:]
            for name in try fm.contentsOfDirectory(atPath:external.path) { originals[name]=try Data(contentsOf:external.appendingPathComponent(name)) }
            let client=try await OpenTideConstants.open(file:file,cacheDir:root.appendingPathComponent("cache").path)
            defer { client.close() }
            let originalRaw=try XCTUnwrap(client.station(stationId:"OTC-T-0001")).raw.data()

            let pruned=try await client.prune(keep:0)
            XCTAssertEqual(pruned,[],label)
            XCTAssertEqual(try fm.contentsOfDirectory(atPath:external.path).sorted(),originals.keys.sorted(),label)
            for (name,bytes) in originals { XCTAssertEqual(try Data(contentsOf:external.appendingPathComponent(name)),bytes,label) }
            XCTAssertEqual(try fm.attributesOfItem(atPath:external.path)[.modificationDate] as? Date,originalMtime,label)
            XCTAssertEqual(try fm.attributesOfItem(atPath:link.path)[.type] as? FileAttributeType,.typeSymbolicLink,label)
            XCTAssertEqual(try fm.destinationOfSymbolicLink(atPath:link.path),"../../../external-user-data",label)
            XCTAssertFalse(fm.fileExists(atPath:external.appendingPathComponent(".lock").path),label)
            XCTAssertEqual(try XCTUnwrap(client.station(stationId:"OTC-T-0001")).raw.data(),originalRaw,label)
        }
    }
}
private extension URL {
    func creatingEmptyFile()throws->URL { try Data().write(to:self);return self }
}
