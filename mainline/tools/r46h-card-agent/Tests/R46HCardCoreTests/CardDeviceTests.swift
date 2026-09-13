import Darwin
import Foundation
import XCTest
@testable import R46HCardCore

final class CardDeviceTests: XCTestCase {
    func testTargetBaselineHashPrecedesWriteStartedAndPartitionWrite() throws {
        let sourceURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Sources/R46HCardCore/CardDevice.swift")
        let source = try String(contentsOf: sourceURL, encoding: .utf8)
        let executeStart = try XCTUnwrap(source.range(of: "public func executeWrite("))
        let executeSource = String(source[executeStart.lowerBound...])
        let baseline = try XCTUnwrap(
            executeSource.range(of: "Self.verifyTargetBaseline(")
        )
        let writeStarted = try XCTUnwrap(executeSource.range(of: "try writeStarted?()"))
        let write = try XCTUnwrap(
            executeSource.range(of: "input: stage,\n            output: target")
        )

        XCTAssertLessThan(baseline.lowerBound, writeStarted.lowerBound)
        XCTAssertLessThan(writeStarted.lowerBound, write.lowerBound)
    }

    func testTargetBaselineMismatchThrowsBeforeWriteStartedAndPreservesBytes() throws {
        let temporary = try TestDirectory()
        let target = temporary.url.appendingPathComponent("target.img")
        let original = Data(repeating: 0x5a, count: 4096)
        try original.write(to: target)
        let descriptor = open(target.path, O_RDWR | O_CLOEXEC | O_NOFOLLOW)
        guard descriptor >= 0 else {
            return XCTFail("failed to open target fixture")
        }
        defer { close(descriptor) }

        var writeStartedCallCount = 0
        assertR46HError(
            try {
                _ = try CardDevice.verifyTargetBaseline(
                    descriptor: descriptor,
                    length: UInt64(original.count),
                    expectedSHA256: String(repeating: "0", count: 64)
                )
                writeStartedCallCount += 1
            }()
        ) { error in
            guard case let .invalidData(message) = error else { return false }
            return message == "target partition SHA-256 no longer matches the write-plan baseline"
        }

        XCTAssertEqual(writeStartedCallCount, 0)
        XCTAssertEqual(try Data(contentsOf: target), original)
    }

    func testWriteStatusAndReceiptRecordTargetBaselineHash() throws {
        let sourceURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Sources/R46HCardAgent/UnixServer.swift")
        let source = try String(contentsOf: sourceURL, encoding: .utf8)
        let binding = "\"target_sha256_before\": operation.targetSHA256Before"
        XCTAssertEqual(source.components(separatedBy: binding).count - 1, 2)
    }

    func testRejectsSessionDirectoryWithBroadPermissions() throws {
        let temporary = try TestDirectory()
        let session = try temporary.directory("session")
        try FileManager.default.setAttributes(
            [.posixPermissions: NSNumber(value: 0o755)],
            ofItemAtPath: session.path
        )
        let descriptor = open(session.path, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW)
        guard descriptor >= 0 else {
            return XCTFail("failed to open test session directory")
        }

        assertR46HError(
            try CardDevice(
                device: "/dev/disk4",
                profile: Fixtures.decodeProfile(),
                ownerUID: getuid(),
                ownerGID: getgid(),
                sessionDirectory: session.path,
                sessionDirectoryDescriptor: descriptor
            )
        ) { error in
            guard case let .unsafePath(message) = error else { return false }
            return message == "session directory FD permissions must be 0700"
        }
    }
}
