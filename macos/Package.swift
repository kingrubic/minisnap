// swift-tools-version:5.9
// Manifest stays at tools 5.9 so it is accepted by Xcode 15 (Swift 5.9) as well as
// Xcode 26 (Swift 6.2). The code is compiled in Swift 5 language mode on both.
import PackageDescription

let package = Package(
    name: "MiniSnap",
    platforms: [
        .macOS(.v14)
    ],
    targets: [
        .executableTarget(
            name: "MiniSnap",
            path: "Sources/MiniSnap",
            linkerSettings: [
                .linkedFramework("AppKit"),
                .linkedFramework("Carbon"),
                .linkedFramework("ScreenCaptureKit"),
                .linkedFramework("AVFoundation"),
                .linkedFramework("CoreMedia"),
                .linkedFramework("CoreVideo"),
                .linkedFramework("Vision"),
                .linkedFramework("QuickLookThumbnailing"),
                .linkedFramework("ServiceManagement"),
                .linkedFramework("UserNotifications"),
                .linkedFramework("UniformTypeIdentifiers"),
                .linkedFramework("CryptoKit")
            ]
        )
    ],
    swiftLanguageVersions: [.v5]
)
