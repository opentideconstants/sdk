import XCTest
@testable import OpenTideConstants
final class ReaderTests: XCTestCase {
    func testActualIteratorClosedError() throws {
        guard let path = ProcessInfo.processInfo.environment["OTC_CORE_NATIVE_JSONL"] else {
            throw OpenTideConstantsError.invalidArgument("real subset environment required")
        }
        let url = URL(fileURLWithPath: path)
        for (label, flagged, fallback) in [("default", false, false), ("includeFlagged", true, false), ("includeFallback", false, true)] {
            let release = try Reader.load(url, mode: .stream, commercialOnly: false, commercialBasis: "strict", historicalOffsetsPolicy: "fallback")
            let expected = try release.filteredEntries(includeFlagged: flagged, includeFallback: fallback).map(\.id)
            let steps = try release.iterStations(includeFlagged: flagged, includeFallback: fallback)
            XCTAssertEqual(release.lruOrder.count, 0, "factory must decode zero stations")
            let advance: () throws -> Station? = { try steps() }
            let first = try XCTUnwrap(advance())
            XCTAssertEqual(first.stationId, expected.first)
            XCTAssertEqual(release.lruOrder.count, 1, "one advance must decode one station")
            var sourceRaw: JSONValue?
            try eachLine(url) { data, _ in
                let raw = try JSONValue.parse(data)
                if raw["station_id"].string == first.stationId { sourceRaw = raw }
            }
            XCTAssertEqual(first.raw, sourceRaw)
            print("ITERATOR_VALUE \(label) selected=\(expected.count) first=\(first.stationId) source_records=\(first.sourceRecords.count) raw_equal=\(first.raw == sourceRaw)")
            release.close()
            XCTAssertThrowsError(try advance(), "\(label): closed iterator must throw io") { error in
                guard let native = error as? OpenTideConstantsError else { return XCTFail("unexpected error \(error)") }
                XCTAssertEqual(native.code, "io")
                XCTAssertEqual(native.message, "the release is closed")
                print("ITERATOR_CLOSED \(label) code=\(native.code) message=\(native.message)")
            }
            XCTAssertEqual(first.raw, sourceRaw, "yielded station survives release close")
        }
    }
    func testActualIteratorSelectionAndExhaustion() throws {
        guard let path = ProcessInfo.processInfo.environment["OTC_CORE_NATIVE_JSONL"] else {
            throw OpenTideConstantsError.invalidArgument("real subset environment required")
        }
        let url = URL(fileURLWithPath: path)
        for (label, flagged, fallback) in [("default", false, false), ("includeFlagged", true, false), ("includeFallback", false, true)] {
            let reference = try Reader.load(url, mode: .stream, commercialOnly: false, commercialBasis: "strict", historicalOffsetsPolicy: "fallback")
            let expected = try reference.stations(includeFlagged: flagged, includeFallback: fallback)
            let release = try Reader.load(url, mode: .stream, commercialOnly: false, commercialBasis: "strict", historicalOffsetsPolicy: "fallback")
            let steps = try release.iterStations(includeFlagged: flagged, includeFallback: fallback)
            let advance: () throws -> Station? = { try steps() }
            XCTAssertEqual(release.lruOrder.count, 0)
            for (index, station) in expected.enumerated() {
                let actual = try XCTUnwrap(advance())
                XCTAssertEqual(actual.stationId, station.stationId)
                XCTAssertEqual(actual.raw, station.raw)
                XCTAssertEqual(release.lruOrder.count, min(index + 1, 256), "advance must decode only its selected station")
            }
            XCTAssertNil(try advance(), "open exhausted cursor returns nil")
            XCTAssertNil(try advance(), "repeated open exhaustion returns nil")
            release.close()
            XCTAssertThrowsError(try advance(), "closed exhausted cursor must throw io") { error in
                guard let native = error as? OpenTideConstantsError else { return XCTFail("unexpected error \(error)") }
                XCTAssertEqual(native.code, "io")
                XCTAssertEqual(native.message, "the release is closed")
            }
            print("ITERATOR_SELECTION \(label) count=\(expected.count) ids_and_raw_equal=true first=\(expected.first!.stationId) last=\(expected.last!.stationId)")
            reference.close()
        }
    }
    func testActualIteratorDecodeErrorAndRetry() throws {
        guard let path = ProcessInfo.processInfo.environment["OTC_CORE_NATIVE_JSONL"] else {
            throw OpenTideConstantsError.invalidArgument("real subset environment required")
        }
        let original = URL(fileURLWithPath: path)
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let local = directory.appendingPathComponent(original.lastPathComponent)
        try FileManager.default.copyItem(at: original, to: local)
        try FileManager.default.copyItem(at: original.deletingPathExtension().appendingPathExtension("meta.json"), to: local.deletingPathExtension().appendingPathExtension("meta.json"))
        let release = try Reader.load(local, mode: .stream, commercialOnly: false, commercialBasis: "strict", historicalOffsetsPolicy: "fallback")
        defer { release.close() }
        let entry = try XCTUnwrap(release.filteredEntries().first)
        let offset = try XCTUnwrap(entry.offset)
        let steps = try release.iterStations()
        let advance: () throws -> Station? = { try steps() }
        XCTAssertEqual(release.lruOrder.count, 0)
        let handle = try FileHandle(forUpdating: local)
        defer { try? handle.close() }
        try handle.seek(toOffset: offset)
        let originalByte = try XCTUnwrap(handle.read(upToCount: 1))
        try handle.seek(toOffset: offset)
        try handle.write(contentsOf: Data("!".utf8))
        for _ in 0..<2 {
            XCTAssertThrowsError(try advance(), "real damaged indexed line must propagate its decode error") { error in
                guard let native = error as? OpenTideConstantsError else { return XCTFail("unexpected error \(error)") }
                XCTAssertEqual(native.code, "invalid_release")
                print("ITERATOR_DECODE_ERROR id=\(entry.id) code=\(native.code) message=\(native.message)")
            }
            XCTAssertEqual(release.lruOrder.count, 0, "failed decode must not prefetch or cache another station")
        }
        try handle.seek(toOffset: offset)
        try handle.write(contentsOf: originalByte)
        XCTAssertEqual(try advance()?.stationId, entry.id, "failed advance must preserve the cursor for retry")
        XCTAssertEqual(release.lruOrder.count, 1)
        print("ITERATOR_RETRY id=\(entry.id) decoded=\(release.lruOrder.count)")
    }
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
