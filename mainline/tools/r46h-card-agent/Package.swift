// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "R46HCardAgent",
    platforms: [
        .macOS(.v13),
    ],
    products: [
        .library(name: "R46HCardCore", targets: ["R46HCardCore"]),
        .executable(name: "r46h-card-agent", targets: ["R46HCardAgent"]),
        .executable(name: "r46h-cardctl", targets: ["R46HCardCtl"]),
    ],
    targets: [
        .target(
            name: "R46HCardCore",
            dependencies: ["R46HDiskIO"]
        ),
        .target(
            name: "R46HDiskIO",
            publicHeadersPath: "include"
        ),
        .executableTarget(
            name: "R46HCardAgent",
            dependencies: ["R46HCardCore"]
        ),
        .executableTarget(
            name: "R46HCardCtl",
            dependencies: ["R46HCardCore"]
        ),
        .testTarget(
            name: "R46HCardCoreTests",
            dependencies: ["R46HCardCore", "R46HDiskIO"]
        ),
    ],
    swiftLanguageModes: [.v5]
)
