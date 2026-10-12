// swift-tools-version: 6.4
import PackageDescription
let package = Package(name:"OTCConformanceSwift",dependencies:[.package(name:"OpenTideConstants",path:"../../../swift")],targets:[.executableTarget(name:"Runner",dependencies:[.product(name:"OpenTideConstants",package:"OpenTideConstants")]),.executableTarget(name:"CheckAPI",dependencies:[.product(name:"OpenTideConstants",package:"OpenTideConstants")])])
