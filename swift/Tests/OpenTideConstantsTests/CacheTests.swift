import XCTest
@testable import OpenTideConstants
final class CacheTests:XCTestCase {
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
}
