import Darwin
import Foundation
import XCTest
@testable import R46HCardCore

final class WireTests: XCTestCase {
    private let token = String(repeating: "a", count: 64)

    func testValidRequestRoundTripsThroughNewlineWire() throws {
        let request = AgentRequest(
            id: "request-42",
            token: token,
            command: "hash-file",
            arguments: ["path": "payload/kernel.img", "volume": "easyroms"]
        )
        var descriptors = [Int32](repeating: -1, count: 2)
        XCTAssertEqual(pipe(&descriptors), 0)
        defer {
            close(descriptors[0])
            close(descriptors[1])
        }

        try Wire.write(request, to: descriptors[1])
        let data = try Wire.readLine(from: descriptors[0])

        XCTAssertEqual(try Wire.decodeRequest(data), request)
    }

    func testStrictRequestRejectsUnknownAndMissingFields() throws {
        var valid = validRequestObject()
        valid["unexpected"] = true
        assertInvalidRequest(valid)

        valid = validRequestObject()
        valid.removeValue(forKey: "arguments")
        assertInvalidRequest(valid)
    }

    func testStrictRequestRejectsMalformedEnvelopeValues() throws {
        let mutations: [(String, Any)] = [
            ("version", AgentRequest.currentVersion + 1),
            ("id", "contains spaces"),
            ("id", String(repeating: "a", count: 65)),
            ("token", String(repeating: "A", count: 64)),
            ("token", "too-short"),
            ("command", "Hash-Raw"),
            ("command", "bad_command"),
        ]
        for (key, value) in mutations {
            var object = validRequestObject()
            object[key] = value
            assertInvalidRequest(object)
        }
    }

    func testStrictRequestRejectsUnsafeArguments() throws {
        let invalidArguments: [[String: Any]] = [
            ["BadKey": "value"],
            ["path": "line1\nline2"],
            ["path": "line1\rline2"],
            ["path": "nul\0byte"],
            ["path": String(repeating: "x", count: 4_097)],
            Dictionary(uniqueKeysWithValues: (0..<17).map { ("key\($0)", "value") }),
        ]
        for arguments in invalidArguments {
            var object = validRequestObject()
            object["arguments"] = arguments
            assertInvalidRequest(object)
        }

        var wrongType = validRequestObject()
        wrongType["arguments"] = ["path": 7]
        assertInvalidRequest(wrongType)
    }

    func testReadLineRejectsEOFBeforeNewline() throws {
        var descriptors = [Int32](repeating: -1, count: 2)
        XCTAssertEqual(pipe(&descriptors), 0)
        let payload = Data("not-terminated".utf8)
        payload.withUnsafeBytes { bytes in
            XCTAssertEqual(Darwin.write(descriptors[1], bytes.baseAddress, bytes.count), bytes.count)
        }
        close(descriptors[1])
        defer { close(descriptors[0]) }

        assertR46HError(try Wire.readLine(from: descriptors[0])) {
            if case .invalidData(let message) = $0 { return message.contains("before newline") }
            return false
        }
    }

    func testWriteRejectsResponseLargerThanOneMiB() throws {
        struct LargeValue: Encodable { let value: String }
        let descriptor = open("/dev/null", O_WRONLY | O_CLOEXEC)
        XCTAssertGreaterThanOrEqual(descriptor, 0)
        defer { close(descriptor) }

        assertR46HError(
            try Wire.write(
                LargeValue(value: String(repeating: "x", count: Wire.maximumMessageBytes + 1)),
                to: descriptor
            )
        ) {
            if case .invalidData(let message) = $0 { return message.contains("exceeds one MiB") }
            return false
        }
    }

    private func validRequestObject() -> [String: Any] {
        [
            "version": AgentRequest.currentVersion,
            "id": "request-1",
            "token": token,
            "command": "card-info",
            "arguments": [String: String](),
        ]
    }

    private func assertInvalidRequest(
        _ object: [String: Any],
        file: StaticString = #filePath,
        line: UInt = #line
    ) {
        do {
            let data = try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
            _ = try Wire.decodeRequest(data)
            XCTFail("request should have been rejected", file: file, line: line)
        } catch is R46HError {
            // Expected.
        } catch {
            XCTFail("unexpected error type: \(error)", file: file, line: line)
        }
    }
}
