import Foundation
import XCTest
@testable import R46HCardCore

final class TestDirectory {
    let url: URL

    init(function: StaticString = #function) throws {
        let safeName = String(describing: function)
            .replacingOccurrences(of: "[^A-Za-z0-9._-]", with: "-", options: .regularExpression)
        url = URL(fileURLWithPath: NSTemporaryDirectory(), isDirectory: true)
            .appendingPathComponent("r46h-card-agent-tests", isDirectory: true)
            .appendingPathComponent("\(safeName)-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
    }

    deinit {
        try? FileManager.default.removeItem(at: url)
    }

    func directory(_ name: String) throws -> URL {
        let child = url.appendingPathComponent(name, isDirectory: true)
        try FileManager.default.createDirectory(at: child, withIntermediateDirectories: true)
        return child
    }

    @discardableResult
    func file(_ name: String, data: Data) throws -> URL {
        let child = url.appendingPathComponent(name)
        try data.write(to: child, options: .atomic)
        return child
    }

    @discardableResult
    func file(_ name: String, bytes: Int, fill: UInt8 = 0) throws -> URL {
        try file(name, data: Data(repeating: fill, count: bytes))
    }
}

enum Fixtures {
    static let digestA = String(repeating: "a", count: 64)
    static let legacyProfileID = "hl-r46h-v22-g92-v1"
    static let compactProfileID = "hl-r46h-v22-g92-31719424000-v1"
    static let recoveredCompactProfileID = "hl-r46h-v22-g92-31719424000-p3-recovery-v1"
    static let fastCardProfileID = "hl-r46h-v22-g92-62534975488-v1"

    static func profileObject(
        profileID: String = legacyProfileID,
        wholeSize: UInt64 = 4_096,
        bootNumber: Int = 1,
        bootOffset: UInt64 = 512,
        bootSize: UInt64 = 512,
        rootNumber: Int = 2,
        rootOffset: UInt64 = 1_024,
        rootSize: UInt64 = 1_024,
        easyromsNumber: Int = 3,
        easyromsOffset: UInt64 = 2_048,
        easyromsSize: UInt64 = 2_048,
        extraCardFields: [String: Any] = [:]
    ) -> [String: Any] {
        var card: [String: Any] = [
            "whole_size": wholeSize,
            "sector_size": 512,
            "partition_scheme": "FDisk_partition_scheme",
            "g92_prefix_size": 512,
            "g92_prefix_sha256": digestA,
            "boot": partition(
                number: bootNumber,
                offset: bootOffset,
                size: bootSize,
                volumeUUID: "BOOT-UUID"
            ),
            "root": partition(
                number: rootNumber,
                offset: rootOffset,
                size: rootSize,
                partUUID: "ROOT-PARTUUID"
            ),
            "easyroms": partition(
                number: easyromsNumber,
                offset: easyromsOffset,
                size: easyromsSize,
                volumeUUID: "EASYROMS-UUID"
            ),
        ]
        for (key, value) in extraCardFields {
            card[key] = value
        }
        return [
            "format_version": 1,
            "profile_id": profileID,
            "target": "HL-R46H-V22",
            "card": card,
        ]
    }

    static func auditedProfileObject(
        profileID: String = legacyProfileID
    ) -> [String: Any] {
        let easyromsSize: UInt64
        let easyromsUUID: String
        let wholeSize: UInt64
        let prefixSHA256: String
        switch profileID {
        case legacyProfileID:
            wholeSize = 31_914_983_424
            easyromsSize = 21_063_888_384
            easyromsUUID = "2D584C38-94B7-38C2-B369-6A7A82C72CC2"
            prefixSHA256 = "91a1f0d5f84e9589843ebf1eb0889669a5da64632fd258ef872f890b446a998b"
        case compactProfileID:
            wholeSize = 31_719_424_000
            easyromsSize = 20_868_328_960
            easyromsUUID = "E1F5295C-4B12-A54A-ACB7-317194240001"
            prefixSHA256 = "97ede10075b3257c638a04b3044c9dda2d8dd9adc6f6fee3be7b004a31fb135e"
        case recoveredCompactProfileID:
            wholeSize = 31_719_424_000
            easyromsSize = 20_868_328_960
            easyromsUUID = "5C29F5E1-124B-4AA5-ACB7-317194240001"
            prefixSHA256 = "97ede10075b3257c638a04b3044c9dda2d8dd9adc6f6fee3be7b004a31fb135e"
        case fastCardProfileID:
            wholeSize = 62_534_975_488
            easyromsSize = 51_683_880_448
            easyromsUUID = "75495362-8048-4A4A-ACB7-625349754881"
            prefixSHA256 = "3fe2feb9cc89ce5f01603199bfc8b715875708a9acc61bfc68b4821e1d8a5da3"
        default:
            preconditionFailure("unsupported audited test profile: \(profileID)")
        }

        return [
            "format_version": 1,
            "profile_id": profileID,
            "target": "HL-R46H-V22",
            "card": [
                "whole_size": wholeSize,
                "sector_size": 512,
                "partition_scheme": "FDisk_partition_scheme",
                "g92_prefix_size": 16_777_216,
                "g92_prefix_sha256": prefixSHA256,
                "boot": partition(
                    number: 1,
                    offset: 16_777_216,
                    size: 117_440_512,
                    volumeUUID: "575BC58C-96FA-3E4F-958B-7A30D5210C3D"
                ),
                "root": partition(
                    number: 2,
                    offset: 134_217_728,
                    size: 10_716_877_312,
                    partUUID: "c9f931c9-02"
                ),
                "easyroms": partition(
                    number: 3,
                    offset: 10_851_095_040,
                    size: easyromsSize,
                    volumeUUID: easyromsUUID
                ),
            ],
        ]
    }

    static func profileData(_ object: [String: Any] = profileObject()) throws -> Data {
        try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
    }

    static func decodeProfile(_ object: [String: Any] = profileObject()) throws -> CardProfile {
        try JSONDecoder().decode(CardProfile.self, from: profileData(object))
    }

    static func writePlanObject(
        profileID: String = "hl-r46h-v22-g92-v1",
        device: String = "/dev/disk4",
        operations: [[String: Any]]
    ) -> [String: Any] {
        [
            "format_version": 1,
            "profile_id": profileID,
            "device": device,
            "operations": operations,
        ]
    }

    static func operation(
        id: String = "write-boot",
        partition: String = "boot",
        sourcePath: String,
        sourceSize: UInt64 = 512,
        sourceSHA256: String = digestA,
        targetSHA256Before: String = digestA,
        extraFields: [String: Any] = [:]
    ) -> [String: Any] {
        var value: [String: Any] = [
            "id": id,
            "description": "test operation",
            "partition": partition,
            "source_path": sourcePath,
            "source_size": sourceSize,
            "source_sha256": sourceSHA256,
            "target_sha256_before": targetSHA256Before,
        ]
        for (key, extraValue) in extraFields {
            value[key] = extraValue
        }
        return value
    }

    private static func partition(
        number: Int,
        offset: UInt64,
        size: UInt64,
        volumeUUID: String? = nil,
        partUUID: String? = nil
    ) -> [String: Any] {
        var value: [String: Any] = [
            "number": number,
            "offset": offset,
            "size": size,
        ]
        if let volumeUUID { value["volume_uuid"] = volumeUUID }
        if let partUUID { value["partuuid"] = partUUID }
        return value
    }
}

func writeJSONObject(_ object: Any, to url: URL) throws -> String {
    let data = try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys])
    try data.write(to: url, options: .atomic)
    return try SHA256.file(at: url.path)
}

func assertR46HError(
    _ expression: @autoclosure () throws -> some Any,
    file: StaticString = #filePath,
    line: UInt = #line,
    _ predicate: (R46HError) -> Bool
) {
    do {
        _ = try expression()
        XCTFail("expected R46HError", file: file, line: line)
    } catch let error as R46HError {
        XCTAssertTrue(predicate(error), "unexpected error: \(error)", file: file, line: line)
    } catch {
        XCTFail("unexpected error type: \(error)", file: file, line: line)
    }
}
