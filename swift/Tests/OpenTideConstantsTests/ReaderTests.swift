import XCTest
@testable import OpenTideConstants
final class ReaderTests: XCTestCase {
    func testCreatedTypeActualFormats() throws {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("conformance/fixtures/bad/created-not-string")
        for (name, mode) in [("OTC_20991231.json", Mode.eager), ("OTC_20991231.json.gz", .eager), ("OTC_20991231.jsonl", .eager), ("OTC_20991231.jsonl", .stream)] {
            XCTAssertThrowsError(try Reader.load(root.appendingPathComponent(name), mode: mode, commercialOnly: false, commercialBasis: "strict", historicalOffsetsPolicy: "fallback"), "\(name) \(mode)") { error in
                guard let native = error as? OpenTideConstantsError else { return XCTFail("unexpected error \(error)") }
                XCTAssertEqual(native.code, "invalid_release")
                XCTAssertEqual(native.message, "created has the wrong type")
                print("CREATED_TYPE name=\(name) mode=\(mode) code=\(native.code)")
            }
        }
    }
    func testDuplicateConventionActualFormats() throws {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("conformance/fixtures/bad/duplicate-convention-id")
        for (name, mode) in [("OTC_20991231.json", Mode.eager), ("OTC_20991231.json.gz", .eager), ("OTC_20991231.jsonl", .eager), ("OTC_20991231.jsonl", .stream)] {
            XCTAssertThrowsError(try Reader.load(root.appendingPathComponent(name), mode: mode, commercialOnly: false, commercialBasis: "strict", historicalOffsetsPolicy: "fallback"), "\(name) \(mode)") { error in
                guard let native = error as? OpenTideConstantsError else { return XCTFail("unexpected error \(error)") }
                XCTAssertEqual(native.code, "invalid_release")
                XCTAssertEqual(native.message, "duplicate convention")
                print("DUPLICATE_CONVENTION name=\(name) mode=\(mode) code=\(native.code)")
            }
        }
    }
    func testDuplicateConventionUnchangedSourceControls() throws {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("conformance/fixtures")
        let good = root.appendingPathComponent("good")
        let document = try JSONValue.parse(Data(contentsOf: good.appendingPathComponent("OTC_20991231.json")))
        let sourceConventions = document["conventions"].array
        let sourceStations = document["stations"].array
        for (name, mode) in [("OTC_20991231.json", Mode.eager), ("OTC_20991231.json.gz", .eager), ("OTC_20991231.jsonl", .eager), ("OTC_20991231.jsonl", .stream)] {
            let release = try Reader.load(good.appendingPathComponent(name), mode: mode, commercialOnly: false, commercialBasis: "strict", historicalOffsetsPolicy: "fallback")
            defer { release.close() }
            XCTAssertEqual(release.meta["conventions"], document["conventions"])
            if mode == .stream {
                XCTAssertEqual(release.documents.count, 0)
                XCTAssertEqual(release.lruOrder.count, 0)
            }
            for source in sourceStations {
                let id = try XCTUnwrap(source["station_id"].string)
                guard source["status"].string != "removed" else { continue }
                let station = try XCTUnwrap(release.station(stationId: id))
                XCTAssertEqual(station.raw, source)
                XCTAssertEqual(station.raw["source_records"], source["source_records"])
                for set in station.constantSets(includeNoConstants: true) {
                    let convention = try XCTUnwrap(set.convention)
                    XCTAssertEqual(convention.raw, sourceConventions.first { $0["convention_id"].string == set.raw["convention_id"].string })
                }
            }
            print("CONVENTION_SOURCE_CONTROL name=\(name) mode=\(mode) raw_and_provenance_equal=true")
        }
        for fixture in ["convention-without-id", "unresolved-convention"] {
            for (name, mode) in [("OTC_20991231.json", Mode.eager), ("OTC_20991231.json.gz", .eager), ("OTC_20991231.jsonl", .eager), ("OTC_20991231.jsonl", .stream)] {
                XCTAssertThrowsError(try Reader.load(root.appendingPathComponent("bad/\(fixture)/\(name)"), mode: mode, commercialOnly: false, commercialBasis: "strict", historicalOffsetsPolicy: "fallback")) { error in
                    guard let native = error as? OpenTideConstantsError else { return XCTFail("unexpected error \(error)") }
                    XCTAssertEqual(native.code, "invalid_release")
                    print("CONVENTION_REFUSAL_CONTROL fixture=\(fixture) name=\(name) mode=\(mode) code=\(native.code)")
                }
            }
        }
    }
    func testActualReaderFileInfoHandoff() throws {
        let fixtureRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("conformance/fixtures/good")
        let index = try JSONValue.parse(Data(contentsOf: fixtureRoot.appendingPathComponent("OTC_index.json")))
        let metadata = try XCTUnwrap(index["releases"].array.first { $0["datestamp"].string == "20991231" })
        let names = ["OTC_20991231.json", "OTC_20991231.jsonl", "OTC_20991231.meta.json"]
        let authenticated = metadata["files"].array.filter { names.contains($0["name"].string ?? "") }.map(FileInfo.init)
        XCTAssertEqual(authenticated.map(\.name), names)
        let manifest = try String(contentsOf: fixtureRoot.appendingPathComponent("OTC_20991231.sha256"), encoding: .utf8)
        for record in authenticated {
            let bytes = try Data(contentsOf: fixtureRoot.appendingPathComponent(record.name))
            XCTAssertEqual(record.size, Int64(bytes.count), record.name)
            XCTAssertEqual(record.sha256, SHA256.digest(bytes), record.name)
            XCTAssertTrue(manifest.split(separator: "\n").contains { $0 == "\(SHA256.digest(bytes))  \(record.name)" }, record.name)
            XCTAssertFalse(record.raw.object.isEmpty, record.name)
        }
        let source = fixtureRoot.appendingPathComponent(names[0])
        var release: Release? = try Reader.load(source, mode: .eager, commercialOnly: false, commercialBasis: "strict", historicalOffsetsPolicy: "fallback", files: authenticated)
        weak let weakRelease = release
        let defaultRelease = try Reader.load(source, mode: .eager, commercialOnly: false, commercialBasis: "strict", historicalOffsetsPolicy: "fallback")
        defer { release?.close(); defaultRelease.close() }
        XCTAssertEqual(defaultRelease.files, [])
        XCTAssertEqual(release?.meta, defaultRelease.meta)
        XCTAssertEqual(release?.entries.map(\.summary), defaultRelease.entries.map(\.summary))
        XCTAssertEqual(release?.documents, defaultRelease.documents)
        XCTAssertEqual(try release?.stationCount, try defaultRelease.stationCount)
        XCTAssertEqual(release?.commercialOnly, defaultRelease.commercialOnly)
        XCTAssertEqual(release?.commercialBasis, defaultRelease.commercialBasis)
        XCTAssertEqual(release?.historicalOffsetsPolicy, defaultRelease.historicalOffsetsPolicy)
        let retained = try XCTUnwrap(release).files
        XCTAssertEqual(retained, authenticated, "exact authenticated order and complete raw metadata")
        for expected in authenticated {
            let actual = retained.first { $0.name == expected.name }
            XCTAssertNotNil(actual, "authenticated record lost: \(expected.name)")
            if let actual {
                XCTAssertFalse(actual.raw.object.isEmpty, expected.name)
                XCTAssertEqual(actual.raw, expected.raw, expected.name)
                XCTAssertEqual(actual.name, expected.name, expected.name)
                XCTAssertEqual(actual.url, expected.url, expected.name)
                XCTAssertEqual(actual.size, expected.size, expected.name)
                XCTAssertEqual(actual.sha256, expected.sha256, expected.name)
            }
            print("READER_FILES_VALUE name=\(expected.name) size=\(expected.size ?? -1) sha256=\(expected.sha256 ?? "missing") url=\(expected.url ?? "missing") actual=\(actual == nil ? "missing" : "present") raw_equal=\(actual?.raw == expected.raw)")
        }
        release?.close()
        release = nil
        XCTAssertNil(weakRelease, "retained immutable file metadata must not retain Release or its parser backing")
        XCTAssertEqual(retained, authenticated, "all file metadata remains readable after close and deallocation")
        print("READER_FILES_DEFAULT files=\(defaultRelease.files.count) source_equal=true policy_equal=true station_count=\(try defaultRelease.stationCount)")
        print("READER_FILES_LIFETIME retained=\(retained.count) release_deallocated=\(weakRelease == nil)")
        // Compatibility control: retain real producer metadata beyond FileInfo's known projections.
        let sourceMetadata = try JSONValue.parse(Data(contentsOf: source))["release"]
        let extended = authenticated.map { record in
            var raw = metadata.object.merging(record.raw.object) { _, fileValue in fileValue }
            raw["source_versions"] = sourceMetadata["source_versions"]
            return FileInfo(.object(raw))
        }
        let extendedRelease = try Reader.load(source, mode: .eager, commercialOnly: false, commercialBasis: "strict", historicalOffsetsPolicy: "fallback", files: extended)
        extendedRelease.close()
        XCTAssertEqual(extendedRelease.files, extended, "unknown producer keys, content hash, and sources survive unchanged")
        print("READER_FILES_UNKNOWN complete_raw_equal=\(extendedRelease.files == extended) producer_sources=\(sourceMetadata["source_versions"].object.count)")
        XCTAssertThrowsError(try Reader.load(source, mode: .eager, commercialOnly: false, commercialBasis: "invalid", historicalOffsetsPolicy: "fallback", files: authenticated)) { error in
            guard case OpenTideConstantsError.invalidArgument(let message, let details) = error else {
                XCTFail("unexpected private Reader error: \(error)"); return
            }
            XCTAssertEqual(message, "invalid policy")
            XCTAssertEqual(details, [:])
        }
        print("READER_FILES_ERROR invalid_policy=invalid_argument")
    }
    func testActualNullableProvenance() throws {
        guard let directory = ProcessInfo.processInfo.environment["OTC_PROVENANCE_CONTROLS"] else {
            throw OpenTideConstantsError.invalidArgument("real provenance controls environment required")
        }
        let root = URL(fileURLWithPath: directory)
        let identities = [
            ("OTC-000180a3", "OTC-000180a3/gesla-fit/idsl_panormos-ids-grc-cmems"),
            ("OTC-000cb5d3", "OTC-000cb5d3/ticon-4/funafuti-67440-tuv-bom"),
            ("OTC-03cf7f34", "OTC-03cf7f34/jma/B3")
        ]
        var originals: [String: JSONValue] = [:]
        try eachLine(root.appendingPathComponent("original.jsonl")) { data, _ in
            let row = try JSONValue.parse(data)
            if let id = row["station_id"].string { originals[id] = row }
        }
        for state in ["present", "absent", "null", "empty", "newer-minor"] {
            let url = root.appendingPathComponent("\(state).jsonl")
            var sourceRows: [String: JSONValue] = [:]
            try eachLine(url) { data, _ in
                let row = try JSONValue.parse(data)
                if let id = row["station_id"].string { sourceRows[id] = row }
            }
            let release = try Reader.load(url, mode: .stream, commercialOnly: false, commercialBasis: "strict", historicalOffsetsPolicy: "fallback")
            defer { release.close() }
            if state == "newer-minor" { XCTAssertEqual(release.formatVersion, "1.99") }
            var retained: [(Station, Provenance, JSONValue, JSONValue)] = []
            for (stationId, setId) in identities {
                let label = "\(stationId)/\(setId) state=\(state)"
                let original = try XCTUnwrap(originals[stationId])
                let source = try XCTUnwrap(sourceRows[stationId])
                let originalSet = try XCTUnwrap(original["constant_sets"].array.first { $0["set_id"].string == setId })
                let sourceSet = try XCTUnwrap(source["constant_sets"].array.first { $0["set_id"].string == setId })
                let station = try XCTUnwrap(release.station(stationId: stationId))
                let set = try XCTUnwrap(station.constantSet(setId: setId))
                let provenance = try XCTUnwrap(set.provenance)
                XCTAssertEqual(station.raw, source, label)
                XCTAssertEqual(set.raw, sourceSet, label)
                XCTAssertEqual(provenance.raw, sourceSet["provenance"], label)
                switch state {
                case "absent":
                    XCTAssertNil(provenance.raw.object["input_sha256"], label)
                    XCTAssertNil(provenance.inputSha256, "\(label): absent input_sha256 must project to nil")
                case "null":
                    XCTAssertEqual(provenance.raw.object["input_sha256"], .null, label)
                    XCTAssertNil(provenance.inputSha256, "\(label): null input_sha256 must project to nil")
                case "empty":
                    XCTAssertEqual(provenance.raw["input_sha256"], .array([]), label)
                    XCTAssertEqual(try XCTUnwrap(provenance.inputSha256), [], label)
                default:
                    let expected = originalSet["provenance"]["input_sha256"].array.compactMap(\.string)
                    XCTAssertFalse(expected.isEmpty, label)
                    XCTAssertEqual(provenance.inputSha256, expected, label)
                }
                var restoredSets = source["constant_sets"].array
                let setIndex = try XCTUnwrap(restoredSets.firstIndex { $0["set_id"].string == setId })
                var restoredProvenance = provenance.raw.object
                restoredProvenance["input_sha256"] = originalSet["provenance"]["input_sha256"]
                if state == "newer-minor" {
                    let unknown: JSONValue = .object(["null": .null, "ordered": .array([.bool(true), .integer(9007199254740991), .string("retained")])])
                    XCTAssertEqual(provenance.raw["s0_n_unknown"], unknown, label)
                    restoredProvenance.removeValue(forKey: "s0_n_unknown")
                }
                var restoredSet = restoredSets[setIndex].object
                restoredSet["provenance"] = .object(restoredProvenance)
                restoredSets[setIndex] = .object(restoredSet)
                var restoredStation = station.raw.object
                restoredStation["constant_sets"] = .array(restoredSets)
                XCTAssertEqual(JSONValue.object(restoredStation), original, "\(label): all unrelated original raw keys and numbers must survive")
                print("PROVENANCE_VALUE \(label) projection=\(String(describing: provenance.inputSha256)) raw_key=\(provenance.raw.object["input_sha256"] == nil ? "missing" : provenance.raw["input_sha256"].isNull ? "null" : "array") raw_equal=\(station.raw == source) original_restored=\(JSONValue.object(restoredStation) == original)")
                retained.append((station, provenance, source, sourceSet["provenance"]))
            }
            release.close()
            for (station, provenance, source, sourceProvenance) in retained {
                XCTAssertEqual(station.raw, source, "\(state): station survives close")
                XCTAssertEqual(provenance.raw, sourceProvenance, "\(state): provenance survives close")
                if state == "absent" || state == "null" { XCTAssertNil(provenance.inputSha256, "\(state): nil projection survives close") }
            }
            print("PROVENANCE_LIFETIME state=\(state) retained=\(retained.count) raw_preserved=true")
        }
    }
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
