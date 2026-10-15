import Foundation
import Security

internal enum HTTP {
    struct Response { let bytes:Data;let status:Int;let etag:String? }
    private static func redact(_ value:String)->String {
        value.replacingOccurrences(of:#"([A-Za-z][A-Za-z0-9+.\-]*://)[^/?#\s'"<>]*@"#,with:"$1***@",options:.regularExpression)
    }
    private static func proxyURL(_ url:URL,option:String?)->URL? {
        if let option { return URL(string:option) }
        let env=ProcessInfo.processInfo.environment
        let value=url.scheme=="https" ? env["https_proxy"] ?? env["HTTPS_PROXY"]:env["http_proxy"] ?? (env["REQUEST_METHOD"]==nil ? env["HTTP_PROXY"]:nil)
        guard let value,!value.isEmpty else { return nil }
        let host=(url.host ?? "").lowercased(),port=url.port ?? (url.scheme=="https" ? 443:80)
        for raw in (env["no_proxy"] ?? env["NO_PROXY"] ?? "").split(separator:",") {
            var token=raw.trimmingCharacters(in:.whitespaces).lowercased()
            if token=="*" { return nil }
            if let colon=token.lastIndex(of:":"),let excludedPort=Int(token[token.index(after:colon)...]) {
                if excludedPort != port { continue }
                token=String(token[..<colon])
            }
            if token.hasPrefix(".") { token.removeFirst() }
            if !token.isEmpty && (host==token || host.hasSuffix("."+token)) { return nil }
        }
        return URL(string:value.contains("://") ? value:"http://"+value)
    }
    private static func retryDelay(_ header:String?,attempt:Int)->UInt64 {
        var seconds=Double(attempt+1)
        if let header {
            let value=header.trimmingCharacters(in:.whitespaces)
            if let integer=Int(value),integer>=0 { seconds=max(seconds,Double(min(integer,60))) }
            else {
                let formatter=DateFormatter()
                formatter.locale=Locale(identifier:"en_US_POSIX");formatter.timeZone=TimeZone(secondsFromGMT:0)
                formatter.dateFormat="EEE, dd MMM yyyy HH:mm:ss 'GMT'";formatter.isLenient=false
                if let date=formatter.date(from:value),formatter.string(from:date)==value { seconds=max(seconds,min(max(0,ceil(date.timeIntervalSinceNow)),60)) }
            }
        }
        return UInt64(seconds*1_000_000_000)
    }
    final class Delegate:NSObject,URLSessionTaskDelegate,@unchecked Sendable {
        let anchors:[SecCertificate]
        private let lock=NSLock()
        private var redirects=0
        private var failure:OpenTideConstantsError?
        init(caFile:String?)throws {
            if let caFile {
                let text:String
                do { text=try String(contentsOfFile:caFile,encoding:.utf8) }
                catch { throw OpenTideConstantsError.io("cannot read CA file",["path":.string(caFile)]) }
                anchors=text.components(separatedBy:"-----BEGIN CERTIFICATE-----").dropFirst().compactMap { part in
                    guard let pem=part.components(separatedBy:"-----END CERTIFICATE-----").first,let data=Data(base64Encoded:pem,options:.ignoreUnknownCharacters) else { return nil }
                    return SecCertificateCreateWithData(nil,data as CFData)
                }
                guard !anchors.isEmpty else { throw OpenTideConstantsError.io("invalid CA file",["path":.string(caFile)]) }
            } else { anchors=[] }
        }
        func urlSession(_ session:URLSession,task:URLSessionTask,willPerformHTTPRedirection response:HTTPURLResponse,newRequest request:URLRequest,completionHandler:@escaping(URLRequest?)->Void) {
            lock.lock();redirects+=1
            let invalid=redirects>5 || !["http","https"].contains(request.url?.scheme ?? "") || request.url?.host==nil || (response.url?.scheme=="https" && request.url?.scheme != "https")
            if invalid { failure = .network("redirect refused",["url":.string(HTTP.redact(response.url?.absoluteString ?? ""))]) }
            lock.unlock()
            guard !invalid else { completionHandler(nil);return }
            var redirected=request
            if response.url?.host != request.url?.host || response.url?.port != request.url?.port || response.url?.scheme != request.url?.scheme { redirected.setValue(nil,forHTTPHeaderField:"Authorization") }
            completionHandler(redirected)
        }
        func urlSession(_ session:URLSession,task:URLSessionTask,didReceive challenge:URLAuthenticationChallenge,completionHandler:@escaping(URLSession.AuthChallengeDisposition,URLCredential?)->Void) {
            guard challenge.protectionSpace.authenticationMethod==NSURLAuthenticationMethodServerTrust,let trust=challenge.protectionSpace.serverTrust,!anchors.isEmpty else { completionHandler(.performDefaultHandling,nil);return }
            SecTrustSetAnchorCertificates(trust,anchors as CFArray)
            SecTrustSetAnchorCertificatesOnly(trust,true)
            SecTrustSetPolicies(trust,SecPolicyCreateSSL(true,challenge.protectionSpace.host as CFString))
            var trustError:CFError?
            if SecTrustEvaluateWithError(trust,&trustError) { completionHandler(.useCredential,URLCredential(trust:trust)) }
            else {
                lock.lock();failure = .network("TLS certificate rejected",["reason":.string(trustError.map { String(describing:$0) } ?? "trust evaluation failed")]);lock.unlock()
                completionHandler(.cancelAuthenticationChallenge,nil)
            }
        }
        func redirectError()->OpenTideConstantsError? { lock.lock();defer { lock.unlock() };return failure }
    }
    static func response(_ url:URL,timeout:Double,userAgent:String?,proxy:String?=nil,caFile:String?=nil,etag:String?=nil)async throws->Response {
        guard ["http","https"].contains(url.scheme ?? ""),url.host != nil else { throw OpenTideConstantsError.invalidArgument("not absolute HTTP URL") }
        let configuration=URLSessionConfiguration.ephemeral
        configuration.urlCache=nil
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        configuration.timeoutIntervalForRequest=timeout
        configuration.timeoutIntervalForResource=timeout
        if let p=proxyURL(url,option:proxy),let host=p.host {
            let port=p.port ?? 80
            configuration.connectionProxyDictionary=["HTTPEnable":1,"HTTPProxy":host,"HTTPPort":port,"HTTPSEnable":1,"HTTPSProxy":host,"HTTPSPort":port]
        }
        for attempt in 0..<3 {
            let delegate=try Delegate(caFile:caFile)
            let session=URLSession(configuration:configuration,delegate:delegate,delegateQueue:nil)
            defer { session.invalidateAndCancel() }
            var request=URLRequest(url:url)
            request.timeoutInterval=timeout
            request.setValue("opentideconstants-swift/0.1.0 (+https://opentideconstants.org)"+(userAgent.map { " "+$0 } ?? ""),forHTTPHeaderField:"User-Agent")
            request.setValue(url.path.hasSuffix(".jsonl") || url.path.hasSuffix(".json") ? "gzip":"identity",forHTTPHeaderField:"Accept-Encoding")
            if let etag { request.setValue(etag,forHTTPHeaderField:"If-None-Match") }
            do {
                let (bytes,response)=try await session.data(for:request)
                if let error=delegate.redirectError() { throw error }
                guard let response=response as? HTTPURLResponse else { throw OpenTideConstantsError.network("not HTTP response",["url":.string(redact(url.absoluteString))]) }
                if [408,429,500,502,503,504].contains(response.statusCode),attempt<2 { try await Task.sleep(nanoseconds:retryDelay(response.value(forHTTPHeaderField:"Retry-After"),attempt:attempt));continue }
                if response.statusCode != 304,let length=response.value(forHTTPHeaderField:"Content-Length"),let expected=Int(length),response.value(forHTTPHeaderField:"Content-Encoding")==nil,expected != bytes.count { throw OpenTideConstantsError.network("short body",["url":.string(redact(url.absoluteString))]) }
                return Response(bytes:bytes,status:response.statusCode,etag:response.value(forHTTPHeaderField:"ETag"))
            } catch let error as OpenTideConstantsError { throw error }
            catch {
                if let error=delegate.redirectError() { throw error }
                if attempt<2 { try await Task.sleep(nanoseconds:retryDelay(nil,attempt:attempt));continue }
                throw OpenTideConstantsError.network(redact("\(error)"),["url":.string(redact(url.absoluteString))])
            }
        }
        throw OpenTideConstantsError.network("request failed",["url":.string(redact(url.absoluteString))])
    }
    static func get(_ url:URL,timeout:Double,userAgent:String?,proxy:String?=nil,caFile:String?=nil,listed:Bool=false)async throws->Data {
        let response=try await response(url,timeout:timeout,userAgent:userAgent,proxy:proxy,caFile:caFile)
        guard response.status==200 else {
            if response.status==404 && !listed { throw OpenTideConstantsError.releaseNotFound("HTTP404",["url":.string(redact(url.absoluteString))]) }
            throw OpenTideConstantsError.network("HTTP\(response.status)"+(response.status==404 && listed ? ": listed file missing on the server":""),["url":.string(redact(url.absoluteString)),"status":.integer(Int64(response.status))])
        }
        return response.bytes
    }
    /// Downloads url to path. Returns true when URLSession removed a Content-Encoding (a CDN that sends a .gz file with
    /// Content-Encoding: gzip): the file then holds the decoded bytes, because URLSession cannot return the stored ones.
    @discardableResult
    static func file(_ url:URL,to path:URL,timeout:Double,userAgent:String?,proxy:String?=nil,caFile:String?=nil,listed:Bool=true)async throws->Bool {
        let configuration=URLSessionConfiguration.ephemeral
        configuration.urlCache=nil;configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        configuration.timeoutIntervalForRequest=timeout;configuration.timeoutIntervalForResource=timeout
        if let p=proxyURL(url,option:proxy),let host=p.host { let port=p.port ?? 80;configuration.connectionProxyDictionary=["HTTPEnable":1,"HTTPProxy":host,"HTTPPort":port,"HTTPSEnable":1,"HTTPSProxy":host,"HTTPSPort":port] }
        for attempt in 0..<3 {
            let delegate=try Delegate(caFile:caFile),session=URLSession(configuration:configuration,delegate:delegate,delegateQueue:nil)
            defer { session.invalidateAndCancel() }
            var request=URLRequest(url:url);request.timeoutInterval=timeout
            request.setValue("opentideconstants-swift/0.1.0 (+https://opentideconstants.org)"+(userAgent.map { " "+$0 } ?? ""),forHTTPHeaderField:"User-Agent")
            request.setValue(url.path.hasSuffix(".jsonl") || url.path.hasSuffix(".json") ? "gzip":"identity",forHTTPHeaderField:"Accept-Encoding")
            let temporary:URL,response:URLResponse
            do { (temporary,response)=try await session.download(for:request) }
            catch {
                if let error=delegate.redirectError() { throw error }
                if attempt<2 { try await Task.sleep(nanoseconds:retryDelay(nil,attempt:attempt));continue }
                throw OpenTideConstantsError.network(redact("\(error)"),["url":.string(redact(url.absoluteString))])
            }
            defer { try? FileManager.default.removeItem(at:temporary) }
            if let error=delegate.redirectError() { throw error }
            guard let response=response as? HTTPURLResponse else { throw OpenTideConstantsError.network("not HTTP response") }
            if [408,429,500,502,503,504].contains(response.statusCode),attempt<2 { try await Task.sleep(nanoseconds:retryDelay(response.value(forHTTPHeaderField:"Retry-After"),attempt:attempt));continue }
            guard response.statusCode==200 else {
                if response.statusCode==404 && !listed { throw OpenTideConstantsError.releaseNotFound("HTTP404",["url":.string(redact(url.absoluteString))]) }
                throw OpenTideConstantsError.network("HTTP\(response.statusCode)"+(response.statusCode==404 && listed ? ": listed file missing on the server":""),["url":.string(redact(url.absoluteString)),"status":.integer(Int64(response.statusCode))])
            }
            do {
                let size=(try FileManager.default.attributesOfItem(atPath:temporary.path)[.size] as? NSNumber)?.int64Value
                if let length=response.value(forHTTPHeaderField:"Content-Length"),let expected=Int64(length),response.value(forHTTPHeaderField:"Content-Encoding")==nil,expected != size { throw OpenTideConstantsError.network("short body",["url":.string(redact(url.absoluteString))]) }
                try FileManager.default.moveItem(at:temporary,to:path)
                let encoding=(response.value(forHTTPHeaderField:"Content-Encoding") ?? "").trimmingCharacters(in:.whitespaces).lowercased()
                return ["gzip","x-gzip","deflate","br"].contains(encoding)
            } catch let error as OpenTideConstantsError { throw error }
            catch { throw OpenTideConstantsError.io("cannot write \(path.path): \(error)",["path":.string(path.path)]) }
        }
        throw OpenTideConstantsError.network("request failed",["url":.string(redact(url.absoluteString))])
    }
}
