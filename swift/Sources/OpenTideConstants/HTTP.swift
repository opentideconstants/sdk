import Foundation
import Security

internal enum HTTP {
    struct Response { let bytes:Data;let status:Int;let etag:String? }
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
            let invalid=redirects>5 || (response.url?.scheme=="https" && request.url?.scheme != "https")
            if invalid { failure = .network("redirect refused",["url":.string(response.url?.absoluteString ?? "")]) }
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
        if let proxy,let p=URL(string:proxy),let host=p.host {
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
            request.setValue("identity",forHTTPHeaderField:"Accept-Encoding")
            if let etag { request.setValue(etag,forHTTPHeaderField:"If-None-Match") }
            do {
                let (bytes,response)=try await session.data(for:request)
                if let error=delegate.redirectError() { throw error }
                guard let response=response as? HTTPURLResponse else { throw OpenTideConstantsError.network("not HTTP response",["url":.string(url.absoluteString)]) }
                if [408,429,500,502,503,504].contains(response.statusCode),attempt<2 { try await Task.sleep(nanoseconds:UInt64(100_000_000*(attempt+1)));continue }
                if response.statusCode != 304,let length=response.value(forHTTPHeaderField:"Content-Length"),let expected=Int(length),response.value(forHTTPHeaderField:"Content-Encoding")==nil,expected != bytes.count { throw OpenTideConstantsError.network("short body",["url":.string(url.absoluteString)]) }
                return Response(bytes:bytes,status:response.statusCode,etag:response.value(forHTTPHeaderField:"ETag"))
            } catch let error as OpenTideConstantsError { throw error }
            catch {
                if let error=delegate.redirectError() { throw error }
                if attempt<2 { try await Task.sleep(nanoseconds:UInt64(100_000_000*(attempt+1)));continue }
                throw OpenTideConstantsError.network("\(error)",["url":.string(url.absoluteString)])
            }
        }
        throw OpenTideConstantsError.network("request failed",["url":.string(url.absoluteString)])
    }
    static func get(_ url:URL,timeout:Double,userAgent:String?,proxy:String?=nil,caFile:String?=nil,listed:Bool=false)async throws->Data {
        let response=try await response(url,timeout:timeout,userAgent:userAgent,proxy:proxy,caFile:caFile)
        guard response.status==200 else {
            if response.status==404 && !listed { throw OpenTideConstantsError.releaseNotFound("HTTP404",["url":.string(url.absoluteString)]) }
            throw OpenTideConstantsError.network("HTTP\(response.status)"+(response.status==404 && listed ? ": listed file missing on the server":""),["url":.string(url.absoluteString),"status":.integer(Int64(response.status))])
        }
        return response.bytes
    }
    static func file(_ url:URL,to path:URL,timeout:Double,userAgent:String?,proxy:String?=nil,caFile:String?=nil,listed:Bool=true)async throws {
        let configuration=URLSessionConfiguration.ephemeral
        configuration.urlCache=nil;configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        configuration.timeoutIntervalForRequest=timeout;configuration.timeoutIntervalForResource=timeout
        if let proxy,let p=URL(string:proxy),let host=p.host { let port=p.port ?? 80;configuration.connectionProxyDictionary=["HTTPEnable":1,"HTTPProxy":host,"HTTPPort":port,"HTTPSEnable":1,"HTTPSProxy":host,"HTTPSPort":port] }
        for attempt in 0..<3 {
            let delegate=try Delegate(caFile:caFile),session=URLSession(configuration:configuration,delegate:delegate,delegateQueue:nil)
            defer { session.invalidateAndCancel() }
            var request=URLRequest(url:url);request.timeoutInterval=timeout
            request.setValue("opentideconstants-swift/0.1.0 (+https://opentideconstants.org)"+(userAgent.map { " "+$0 } ?? ""),forHTTPHeaderField:"User-Agent")
            request.setValue("identity",forHTTPHeaderField:"Accept-Encoding")
            let temporary:URL,response:URLResponse
            do { (temporary,response)=try await session.download(for:request) }
            catch {
                if attempt<2 { try await Task.sleep(nanoseconds:UInt64(100_000_000*(attempt+1)));continue }
                throw OpenTideConstantsError.network("\(error)",["url":.string(url.absoluteString)])
            }
            defer { try? FileManager.default.removeItem(at:temporary) }
            if let error=delegate.redirectError() { throw error }
            guard let response=response as? HTTPURLResponse else { throw OpenTideConstantsError.network("not HTTP response") }
            if [408,429,500,502,503,504].contains(response.statusCode),attempt<2 { try await Task.sleep(nanoseconds:UInt64(100_000_000*(attempt+1)));continue }
            guard response.statusCode==200 else {
                if response.statusCode==404 && !listed { throw OpenTideConstantsError.releaseNotFound("HTTP404",["url":.string(url.absoluteString)]) }
                throw OpenTideConstantsError.network("HTTP\(response.statusCode)"+(response.statusCode==404 && listed ? ": listed file missing on the server":""),["url":.string(url.absoluteString),"status":.integer(Int64(response.statusCode))])
            }
            do {
                let size=(try FileManager.default.attributesOfItem(atPath:temporary.path)[.size] as? NSNumber)?.int64Value
                if let length=response.value(forHTTPHeaderField:"Content-Length"),let expected=Int64(length),response.value(forHTTPHeaderField:"Content-Encoding")==nil,expected != size { throw OpenTideConstantsError.network("short body",["url":.string(url.absoluteString)]) }
                try FileManager.default.moveItem(at:temporary,to:path)
                return
            } catch let error as OpenTideConstantsError { throw error }
            catch { throw OpenTideConstantsError.io("cannot write \(path.path): \(error)",["path":.string(path.path)]) }
        }
    }
}
