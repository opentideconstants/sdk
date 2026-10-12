import Foundation
import OpenTideConstants
@main struct Runner {
    static func emit(_ value:JSONValue) { let encoder=JSONEncoder();encoder.outputFormatting=[.sortedKeys];if let data=try? encoder.encode(value),let line=String(data:data,encoding:.utf8) { print(line) } }
    static func main()async {
        emit(.object(["hello":.object(["runner":.string("swift"),"version":.string("0.1.0"),"features":.array(["fs","json","eager","stream"].map(JSONValue.string))])]))
        var client:OpenTideConstants?
        while let line=readLine() {
            do {
                let q=try JSONDecoder().decode(JSONValue.self,from:Data(line.utf8));let op=q["op"].string ?? "",args=q["args"]
                let result:JSONValue
                switch op {
                case "open":
                    client=try await OpenTideConstants.open(release:args["release"].string,file:args["file"].string,cacheDir:args["cache_dir"].string,offline:args["offline"].bool,mode:Mode(rawValue:args["mode"].string ?? "eager") ?? .other,baseUrl:args["base_url"].string,timeout:args["timeout"].number,onNetworkError:args["on_network_error"].string.flatMap(OnNetworkError.init(rawValue:)),commercialOnly:args["commercial_only"].bool ?? false,commercialBasis:args["commercial_basis"].string ?? "strict",historicalOffsetsPolicy:args["historical_offsets_policy"].string ?? "fallback")
                    result = .object(["datestamp":.string(client!.release.datestamp),"loaded_from":.string(client!.loadedFrom.rawValue)])
                case "station", "require_station":
                    guard let client else { throw OpenTideConstantsError.invalidArgument("not open") }
                    let id=args["station_id"].string ?? ""
                    let s = op=="require_station" ? try client.requireStation(stationId:id):try client.station(stationId:id)
                    result=s?.raw ?? .null
                case "close":client?.close();result = .null
                default:throw OpenTideConstantsError.invalidArgument("foundation runner op \(op) awaits S1/G0 registration")
                }
                emit(.object(["ok":.bool(true),"result":result]))
            } catch let e as OpenTideConstantsError { emit(.object(["ok":.bool(false),"error":.object(["code":.string(e.code),"message":.string(e.message)])])) }
            catch { emit(.object(["ok":.bool(false),"error":.object(["code":.string("uncaught"),"message":.string("\(error)")])])) }
        }
    }
}
