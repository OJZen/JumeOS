import Darwin
import Foundation
import XCTest
@testable import R46HCardCore

final class SHA256Tests: XCTestCase {
    func testKnownFileDigests() throws {
        let directory = try TestDirectory()
        let empty = try directory.file("empty", data: Data())
        let abc = try directory.file("abc", data: Data("abc".utf8))

        XCTAssertEqual(
            try SHA256.file(at: empty.path),
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        )
        XCTAssertEqual(
            try SHA256.file(at: abc.path),
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        )
    }

    func testDescriptorHashHonorsOffsetLengthAndProgress() throws {
        let directory = try TestDirectory()
        let file = try directory.file("digits", data: Data("0123456789".utf8))
        let descriptor = open(file.path, O_RDONLY | O_CLOEXEC)
        XCTAssertGreaterThanOrEqual(descriptor, 0)
        defer { close(descriptor) }
        var progress: [UInt64] = []

        let digest = try SHA256.descriptorHash(
            descriptor,
            offset: 2,
            length: 4,
            progress: { progress.append($0) }
        )

        XCTAssertEqual(digest, "38083c7ee9121e17401883566a148aa5c2e2d55dc53bc4a94a026517dbff3c6b")
        XCTAssertEqual(progress.last, 4)
    }

    func testDescriptorHashRejectsShortRead() throws {
        let directory = try TestDirectory()
        let file = try directory.file("short", data: Data("abc".utf8))
        let descriptor = open(file.path, O_RDONLY | O_CLOEXEC)
        XCTAssertGreaterThanOrEqual(descriptor, 0)
        defer { close(descriptor) }

        assertR46HError(try SHA256.descriptorHash(descriptor, length: 4)) {
            if case .invalidData(let message) = $0 {
                return message.contains("unexpected EOF") && message.contains("expected 4")
            }
            return false
        }
    }

    func testDescriptorHashHonorsCancellationBeforeReading() throws {
        let directory = try TestDirectory()
        let file = try directory.file("cancel", data: Data("abc".utf8))
        let descriptor = open(file.path, O_RDONLY | O_CLOEXEC)
        XCTAssertGreaterThanOrEqual(descriptor, 0)
        defer { close(descriptor) }

        assertR46HError(try SHA256.descriptorHash(descriptor, cancelled: { true })) {
            if case .cancelled(let message) = $0 { return message == "operation cancelled" }
            return false
        }
    }

    func testStreamCannotBeUsedAfterFinalization() throws {
        let stream = SHA256Stream()
        XCTAssertEqual(
            try stream.finalize(),
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        )
        assertR46HError(try stream.finalize()) {
            if case .invalidData(let message) = $0 { return message.contains("already finalized") }
            return false
        }
        assertR46HError(try Data("x".utf8).withUnsafeBytes { try stream.update($0) }) {
            if case .invalidData(let message) = $0 { return message.contains("already finalized") }
            return false
        }
    }

    func testSHA256ShapeRequiresLowercaseHex() {
        XCTAssertTrue(isSHA256(String(repeating: "0123456789abcdef", count: 4)))
        XCTAssertFalse(isSHA256(String(repeating: "A", count: 64)))
        XCTAssertFalse(isSHA256(String(repeating: "a", count: 63)))
        XCTAssertFalse(isSHA256(String(repeating: "g", count: 64)))
    }
}
