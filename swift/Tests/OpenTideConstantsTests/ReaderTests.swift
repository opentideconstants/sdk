import XCTest
@testable import OpenTideConstants
final class ReaderTests: XCTestCase {
    func testJSONValueKindsAndImmutableCopy() throws {
        let v = try JSONValue.parse(Data(#"{"a":true,"b":12,"c":null,"d":["original\nfit",1.25]}"#.utf8))
        XCTAssertEqual(v["a"].bool, true); XCTAssertNil(v["a"].number)
        XCTAssertEqual(v["b"].integer, 12); XCTAssertTrue(v["c"].isNull)
        var copy = v.object; copy["a"] = .null; XCTAssertEqual(v["a"].bool, true)
        XCTAssertEqual(try JSONValue.parse(v.data()), v)
    }
    func testTimesAndFold() throws {
        XCTAssertEqual(try parseTime("2020-01-01T00:00:00+0100"), try parseTime("2019-12-31T23:00:00Z"))
        XCTAssertThrowsError(try parseTime("2020-02-30T00:00:00Z"))
        XCTAssertThrowsError(try parseTime("2020-01-01T24:00:00Z"))
        XCTAssertEqual(NameFold.fold("  São\tPaulo "), "sao paulo")
    }
    func testActualStreamDecoderMemory() throws {
        guard let path=ProcessInfo.processInfo.environment["OTC_CORE_NATIVE_JSONL"] else { throw OpenTideConstantsError.invalidArgument("real subset environment required") }
        let url=URL(fileURLWithPath:path)
        for _ in 0..<20 {
            let r=try Reader.load(url,mode:.stream,commercialOnly:false,commercialBasis:"strict",historicalOffsetsPolicy:"fallback")
            XCTAssertEqual(try r.stationCount,8)
        }
        print("BOUNDED_MEMORY: 20 repeated real 8-record subset loads; not full-release evidence")
    }
    func testJSONSyntaxAndUnicode() throws {
        XCTAssertEqual(try JSONValue.parse(Data(#"{"a":"\uD83D\uDE00","b":-1.25e2,"c":[null,false,true]}"#.utf8))["a"].string,"😀")
        for text in [#""\uD800""#, #"[1,]"#, #"{"a":1,}"#, "01", "1e999", "true false", "\"\n\""] { XCTAssertThrowsError(try JSONValue.parse(Data(text.utf8))) }
        XCTAssertThrowsError(try JSONValue.parse(Data([34,255,34])))
    }
    func testActualDiscoveryMemory() throws {
        guard let path=ProcessInfo.processInfo.environment["OTC_CORE_NATIVE_JSONL"] else { throw OpenTideConstantsError.invalidArgument("real subset environment required") }
        let url=URL(fileURLWithPath:path)
        for _ in 0..<40 {
            let r=try Reader.load(url,mode:.stream,commercialOnly:false,commercialBasis:"strict",historicalOffsetsPolicy:"fallback")
            XCTAssertEqual(try r.stations().count,5)
            XCTAssertEqual(try r.stations(includeFlagged:true).count,7)
            XCTAssertEqual(try r.stations(includeFallback:true).count,7)
            XCTAssertEqual(try r.stations(includeFlagged:true,includeFallback:true).count,8)
        }
        print("BOUNDED_DISCOVERY:40 repeated real8record public-query groups; not full acceptance")
    }
}
