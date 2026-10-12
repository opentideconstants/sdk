import Foundation
internal enum HTTP {
    static func get(_ url:URL,timeout:Double,userAgent:String?)async throws->Data {
        guard ["http","https"].contains(url.scheme ?? ""),url.host != nil else { throw OpenTideConstantsError.invalidArgument("not absolute HTTP URL") }
        var req=URLRequest(url:url);req.timeoutInterval=timeout
        req.setValue("opentideconstants-swift/0.1.0 (+https://opentideconstants.org)"+(userAgent.map { " "+$0 } ?? ""),forHTTPHeaderField:"User-Agent")
        do {
            let (bytes,response)=try await URLSession.shared.data(for:req)
            guard let r=response as? HTTPURLResponse else { throw OpenTideConstantsError.network("not HTTP response",["url":.string(url.absoluteString)]) }
            guard (200..<300).contains(r.statusCode) else { if r.statusCode==404 { throw OpenTideConstantsError.releaseNotFound("HTTP404") };throw OpenTideConstantsError.network("HTTP\(r.statusCode)",["url":.string(url.absoluteString),"status":.integer(Int64(r.statusCode))]) }
            if let value=r.value(forHTTPHeaderField:"Content-Length"),let expected=Int(value),r.value(forHTTPHeaderField:"Content-Encoding")==nil,expected != bytes.count { throw OpenTideConstantsError.network("short body") }
            return bytes
        } catch let e as OpenTideConstantsError { throw e } catch { throw OpenTideConstantsError.network("\(error)",["url":.string(url.absoluteString)]) }
    }
}
