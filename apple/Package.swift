// swift-tools-version: 5.9
import PackageDescription
let package = Package(
    name: "BoulderbatCore",
    platforms: [.iOS(.v17), .macOS(.v14), .watchOS(.v10), .visionOS(.v1)],
    products: [.library(name: "BoulderbatCore", targets: ["BoulderbatCore"])],
    targets: [
        .target(name: "BoulderbatCore", path: "Shared"),
        .testTarget(name: "BoulderbatCoreTests", dependencies: ["BoulderbatCore"], path: "Tests")
    ]
)
