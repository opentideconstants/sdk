// swift-tools-version: 6.4
import PackageDescription
let package = Package(name: "OpenTideConstants", products: [.library(name: "OpenTideConstants", targets: ["OpenTideConstants"])], targets: [.systemLibrary(name: "CZlib"), .target(name: "OpenTideConstants", dependencies: ["CZlib"], resources: [.process("Resources")]), .testTarget(name: "OpenTideConstantsTests", dependencies: ["OpenTideConstants"])])
