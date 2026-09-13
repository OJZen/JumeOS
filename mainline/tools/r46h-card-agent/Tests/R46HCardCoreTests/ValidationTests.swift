import Darwin
import Foundation
import XCTest
@testable import R46HCardCore

final class ValidationTests: XCTestCase {
    func testDevicePathAcceptsOnlyWholeNonzeroDisk() throws {
        XCTAssertNoThrow(try Validation.validateDevicePath("/dev/disk4"))
        XCTAssertNoThrow(try Validation.validateDevicePath("/dev/disk123"))

        for invalid in [
            "/dev/disk0", "/dev/disk4s1", "/dev/rdisk4", "disk4", "/dev/disk-1", "/dev/disk04",
        ] {
            assertR46HError(try Validation.validateDevicePath(invalid)) {
                if case .invalidArgument = $0 { return true }
                return false
            }
        }
    }

    func testRelativeVolumePathNormalizesNothingAndRejectsTraversal() throws {
        XCTAssertEqual(
            try Validation.validateRelativeVolumePath("r46h-v0.5/payload/kernel.img"),
            "r46h-v0.5/payload/kernel.img"
        )
        XCTAssertEqual(try Validation.validateRelativeVolumePath("."), ".")
        for invalid in ["", "/absolute", "..", "a/../b", "a/./b", "a//b", "a/", "nul\0byte"] {
            assertR46HError(try Validation.validateRelativeVolumePath(invalid)) {
                if case .unsafePath = $0 { return true }
                return false
            }
        }
    }

    func testOutputNameAllowlist() throws {
        for valid in ["clone.img", "p2-audit_01", "A"] {
            XCTAssertNoThrow(try Validation.validateOutputName(valid))
        }
        for invalid in ["", ".", "..", "with/slash", "with space", "-leading", String(repeating: "a", count: 129)] {
            assertR46HError(try Validation.validateOutputName(invalid)) {
                if case .invalidArgument = $0 { return true }
                return false
            }
        }
    }

    func testLoadProfileRequiresPinnedDigest() throws {
        let directory = try TestDirectory()
        let path = directory.url.appendingPathComponent("profile.json")
        let expected = try writeJSONObject(Fixtures.auditedProfileObject(), to: path)

        let profile = try Validation.loadProfile(path: path.path, expectedSHA256: expected)

        XCTAssertEqual(profile.card.wholeSize, 31_914_983_424)
        XCTAssertEqual(profile.partition(for: .boot)?.size, 117_440_512)
        assertR46HError(
            try Validation.loadProfile(path: path.path, expectedSHA256: Fixtures.digestA)
        ) {
            if case .invalidData(let message) = $0 { return message.contains("SHA-256 mismatch") }
            return false
        }
    }

    func testProfileIdentityAllowlistContainsExactlyTheFourAuditedCards() throws {
        let auditedProfileIDs: Set<String> = [
            Fixtures.legacyProfileID,
            Fixtures.compactProfileID,
            Fixtures.recoveredCompactProfileID,
            Fixtures.fastCardProfileID,
        ]
        XCTAssertEqual(Validation.supportedProfileIDs, auditedProfileIDs)

        for profileID in auditedProfileIDs {
            XCTAssertNoThrow(
                try Validation.validate(
                    profile: Fixtures.decodeProfile(
                        Fixtures.auditedProfileObject(profileID: profileID)
                    )
                )
            )
        }

        for profileID in [
            "hl-r46h-v22-g92-v2",
            "hl-r46h-v22-g92-31719424000-v2",
            "HL-R46H-V22",
        ] {
            assertR46HError(
                try Validation.validate(
                    profile: Fixtures.decodeProfile(
                        Fixtures.profileObject(profileID: profileID)
                    )
                )
            ) {
                if case .invalidData(let message) = $0 {
                    return message.contains("target mismatch")
                }
                return false
            }
        }
    }

    func testCheckedInAuditedProfilesMatchCoreIdentityExactly() throws {
        let testSource = URL(fileURLWithPath: #filePath)
        let packageRoot = testSource
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let profileRoot = packageRoot
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("deploy/profiles", isDirectory: true)

        for profileID in [
            Fixtures.legacyProfileID,
            Fixtures.compactProfileID,
            Fixtures.recoveredCompactProfileID,
            Fixtures.fastCardProfileID,
        ] {
            let profileURL = profileRoot.appendingPathComponent("\(profileID).json")
            let profile = try Validation.loadProfile(
                path: profileURL.path,
                expectedSHA256: try SHA256.file(at: profileURL.path)
            )
            XCTAssertEqual(profile.profileID, profileID)
        }
    }

    func testProfileIdentityCannotBeMixedBetweenAuditedProfileIDs() throws {
        var legacyGeometryWithCompactID = Fixtures.auditedProfileObject(
            profileID: Fixtures.legacyProfileID
        )
        legacyGeometryWithCompactID["profile_id"] = Fixtures.compactProfileID
        assertProfileIdentityRejected(legacyGeometryWithCompactID)

        var compactGeometryWithLegacyID = Fixtures.auditedProfileObject(
            profileID: Fixtures.compactProfileID
        )
        compactGeometryWithLegacyID["profile_id"] = Fixtures.legacyProfileID
        assertProfileIdentityRejected(compactGeometryWithLegacyID)

        var compactGeometryWithRecoveredID = Fixtures.auditedProfileObject(
            profileID: Fixtures.compactProfileID
        )
        compactGeometryWithRecoveredID["profile_id"] = Fixtures.recoveredCompactProfileID
        assertProfileIdentityRejected(compactGeometryWithRecoveredID)

        var recoveredGeometryWithCompactID = Fixtures.auditedProfileObject(
            profileID: Fixtures.recoveredCompactProfileID
        )
        recoveredGeometryWithCompactID["profile_id"] = Fixtures.compactProfileID
        assertProfileIdentityRejected(recoveredGeometryWithCompactID)

        var fastGeometryWithRecoveredID = Fixtures.auditedProfileObject(
            profileID: Fixtures.fastCardProfileID
        )
        fastGeometryWithRecoveredID["profile_id"] = Fixtures.recoveredCompactProfileID
        assertProfileIdentityRejected(fastGeometryWithRecoveredID)
    }

    func testProfileIdentityRejectsEverySingleCardIdentityFieldMutation() throws {
        typealias Mutation = (String, (inout [String: Any]) -> Void)
        let mutations: [Mutation] = [
            ("whole size", { $0["whole_size"] = UInt64(31_719_424_512) }),
            ("sector size", { $0["sector_size"] = UInt64(4_096) }),
            ("partition scheme", { $0["partition_scheme"] = "GUID_partition_scheme" }),
            ("prefix size", { $0["g92_prefix_size"] = UInt64(16_776_704) }),
            ("prefix digest", { $0["g92_prefix_sha256"] = Fixtures.digestA }),
            ("boot number", { Self.mutatePartition("boot", in: &$0) { $0["number"] = 4 } }),
            ("boot offset", { Self.mutatePartition("boot", in: &$0) { $0["offset"] = UInt64(16_777_728) } }),
            ("boot size", { Self.mutatePartition("boot", in: &$0) { $0["size"] = UInt64(117_440_000) } }),
            ("boot UUID", { Self.mutatePartition("boot", in: &$0) { $0["volume_uuid"] = "WRONG-BOOT-UUID" } }),
            ("boot unexpected PARTUUID", { Self.mutatePartition("boot", in: &$0) { $0["partuuid"] = "c9f931c9-01" } }),
            ("root number", { Self.mutatePartition("root", in: &$0) { $0["number"] = 4 } }),
            ("root offset", { Self.mutatePartition("root", in: &$0) { $0["offset"] = UInt64(134_218_240) } }),
            ("root size", { Self.mutatePartition("root", in: &$0) { $0["size"] = UInt64(10_716_876_800) } }),
            ("root PARTUUID", { Self.mutatePartition("root", in: &$0) { $0["partuuid"] = "c9f931c9-99" } }),
            ("root unexpected UUID", { Self.mutatePartition("root", in: &$0) { $0["volume_uuid"] = "WRONG-ROOT-UUID" } }),
            ("EASYROMS number", { Self.mutatePartition("easyroms", in: &$0) { $0["number"] = 4 } }),
            ("EASYROMS offset", { Self.mutatePartition("easyroms", in: &$0) { $0["offset"] = UInt64(10_851_095_552) } }),
            ("EASYROMS size", { Self.mutatePartition("easyroms", in: &$0) { $0["size"] = UInt64(20_868_328_448) } }),
            ("EASYROMS UUID", { Self.mutatePartition("easyroms", in: &$0) { $0["volume_uuid"] = "WRONG-EASYROMS-UUID" } }),
            ("EASYROMS unexpected PARTUUID", { Self.mutatePartition("easyroms", in: &$0) { $0["partuuid"] = "c9f931c9-03" } }),
        ]

        for (name, mutate) in mutations {
            for profileID in [
                Fixtures.compactProfileID,
                Fixtures.recoveredCompactProfileID,
                Fixtures.fastCardProfileID,
            ] {
                var object = Fixtures.auditedProfileObject(profileID: profileID)
                var card = try XCTUnwrap(object["card"] as? [String: Any])
                mutate(&card)
                object["card"] = card
                assertProfileIdentityRejected(object, mutation: "\(profileID): \(name)")
            }
        }
    }

    func testProfileRejectsOverlapDuplicateNumbersAndOutOfBounds() throws {
        let overlap = try Fixtures.decodeProfile(
            Fixtures.profileObject(rootOffset: 900)
        )
        assertR46HError(try Validation.validate(profile: overlap)) {
            if case .invalidData(let message) = $0 { return message.contains("overlap") }
            return false
        }

        let duplicate = try Fixtures.decodeProfile(
            Fixtures.profileObject(rootNumber: 1)
        )
        assertR46HError(try Validation.validate(profile: duplicate)) {
            if case .invalidData(let message) = $0 { return message.contains("p1/p2/p3") }
            return false
        }

        let outOfBounds = try Fixtures.decodeProfile(
            Fixtures.profileObject(wholeSize: 3_000)
        )
        assertR46HError(try Validation.validate(profile: outOfBounds)) {
            if case .invalidData(let message) = $0 { return message.contains("exceed") }
            return false
        }
    }

    func testProfileRejectsWrongIdentityAndPrefixGeometry() throws {
        var wrongIdentity = Fixtures.profileObject()
        wrongIdentity["profile_id"] = "some-other-device"
        assertR46HError(try Validation.validate(profile: Fixtures.decodeProfile(wrongIdentity))) {
            if case .invalidData(let message) = $0 { return message.contains("target mismatch") }
            return false
        }

        let badPrefix = try Fixtures.decodeProfile(
            Fixtures.profileObject(extraCardFields: ["g92_prefix_size": 513])
        )
        assertR46HError(try Validation.validate(profile: badPrefix)) {
            if case .invalidData(let message) = $0 { return message.contains("geometry") }
            return false
        }
    }

    func testLoadWritePlanAcceptsSmallFullPartitionImage() throws {
        let fixture = try makeWritePlanFixture()

        let plan = try Validation.loadWritePlan(
            path: fixture.plan.path,
            expectedSHA256: fixture.digest,
            profile: fixture.profile,
            device: "/dev/disk4",
            inputRoot: fixture.inputRoot.path
        )

        XCTAssertEqual(plan.operations.count, 1)
        XCTAssertEqual(plan.operations[0].partition, .boot)
        XCTAssertEqual(plan.operations[0].sourceSize, 512)
    }

    func testWritePlanRejectsUnknownKeysBeforeDecoding() throws {
        let fixture = try makeWritePlanFixture(extraOperationFields: ["surprise": true])

        assertR46HError(
            try Validation.loadWritePlan(
                path: fixture.plan.path,
                expectedSHA256: fixture.digest,
                profile: fixture.profile,
                device: "/dev/disk4",
                inputRoot: fixture.inputRoot.path
            )
        ) {
            if case .invalidData(let message) = $0 { return message.contains("unknown or missing keys") }
            return false
        }
    }

    func testWritePlanRequiresExactTopLevelAndOperationKeySets() throws {
        let directory = try TestDirectory()
        let inputRoot = try directory.directory("input")
        let source = inputRoot.appendingPathComponent("boot.img")
        try Data(repeating: 0, count: 512).write(to: source)
        let profile = try Fixtures.decodeProfile()

        var extraTopLevel = Fixtures.writePlanObject(
            operations: [Fixtures.operation(sourcePath: source.path)]
        )
        extraTopLevel["comment"] = "not allowed"
        try assertRejectedKeySet(
            extraTopLevel,
            directory: directory,
            inputRoot: inputRoot,
            profile: profile
        )

        var missingTopLevel = Fixtures.writePlanObject(
            operations: [Fixtures.operation(sourcePath: source.path)]
        )
        missingTopLevel.removeValue(forKey: "device")
        try assertRejectedKeySet(
            missingTopLevel,
            directory: directory,
            inputRoot: inputRoot,
            profile: profile
        )

        var missingOperationKey = Fixtures.operation(sourcePath: source.path)
        missingOperationKey.removeValue(forKey: "description")
        try assertRejectedKeySet(
            Fixtures.writePlanObject(operations: [missingOperationKey]),
            directory: directory,
            inputRoot: inputRoot,
            profile: profile
        )
    }

    func testWritePlanRejectsOutsideRootAndSymlinkSources() throws {
        let directory = try TestDirectory()
        let inputRoot = try directory.directory("input")
        let outside = try directory.file("outside.img", bytes: 512)
        let profile = try Fixtures.decodeProfile()

        try assertRejectedSource(
            outside.path,
            directory: directory,
            inputRoot: inputRoot,
            profile: profile
        )

        let link = inputRoot.appendingPathComponent("link.img")
        XCTAssertEqual(symlink(outside.path, link.path), 0)
        try assertRejectedSource(
            link.path,
            directory: directory,
            inputRoot: inputRoot,
            profile: profile
        )
    }

    func testWritePlanRejectsPartialPartitionAndPrefixTargets() throws {
        let partial = try makeWritePlanFixture(sourceSize: 511)
        assertInvalidWritePlan(partial, messageFragment: "not a full-partition image")

        let prefix = try makeWritePlanFixture(partition: "prefix")
        assertInvalidWritePlan(prefix, messageFragment: "not a full-partition image")
    }

    func testWritePlanRejectsDuplicateIDsWrongHeaderAndBadPinnedDigest() throws {
        let directory = try TestDirectory()
        let inputRoot = try directory.directory("input")
        let source = inputRoot.appendingPathComponent("boot.img")
        try Data(repeating: 0, count: 512).write(to: source)
        let profile = try Fixtures.decodeProfile()
        let operation = Fixtures.operation(sourcePath: source.path)
        let planURL = directory.url.appendingPathComponent("plan.json")
        let digest = try writeJSONObject(
            Fixtures.writePlanObject(operations: [operation, operation]),
            to: planURL
        )

        assertR46HError(
            try Validation.loadWritePlan(
                path: planURL.path,
                expectedSHA256: digest,
                profile: profile,
                device: "/dev/disk4",
                inputRoot: inputRoot.path
            )
        ) {
            if case .invalidData(let message) = $0 { return message.contains("duplicated") }
            return false
        }

        let wrongHeader = try makeWritePlanFixture(device: "/dev/disk5")
        assertInvalidWritePlan(wrongHeader, messageFragment: "header mismatch")

        let valid = try makeWritePlanFixture()
        assertR46HError(
            try Validation.loadWritePlan(
                path: valid.plan.path,
                expectedSHA256: Fixtures.digestA,
                profile: valid.profile,
                device: "/dev/disk4",
                inputRoot: valid.inputRoot.path
            )
        ) {
            if case .invalidData(let message) = $0 { return message.contains("SHA-256 mismatch") }
            return false
        }
    }

    func testCanonicalHelpersRejectSymlinksAndDirectoryPrefixConfusion() throws {
        let directory = try TestDirectory()
        let root = try directory.directory("input")
        let sibling = try directory.directory("input-evil")
        let siblingFile = sibling.appendingPathComponent("image")
        try Data([1]).write(to: siblingFile)
        let identity = try Validation.canonicalRegularFile(siblingFile.path)

        XCTAssertFalse(Validation.isDescendant(identity, of: root.path))

        let link = directory.url.appendingPathComponent("root-link")
        XCTAssertEqual(symlink(root.path, link.path), 0)
        assertR46HError(try Validation.canonicalDirectory(link.path)) {
            if case .unsafePath = $0 { return true }
            return false
        }
    }

    private struct WritePlanFixture {
        let directory: TestDirectory
        let inputRoot: URL
        let profile: CardProfile
        let plan: URL
        let digest: String
    }

    private func makeWritePlanFixture(
        device: String = "/dev/disk4",
        partition: String = "boot",
        sourceSize: UInt64 = 512,
        extraOperationFields: [String: Any] = [:]
    ) throws -> WritePlanFixture {
        let directory = try TestDirectory()
        let inputRoot = try directory.directory("input")
        let source = inputRoot.appendingPathComponent("source.img")
        try Data(repeating: 0x5a, count: Int(sourceSize)).write(to: source)
        let operation = Fixtures.operation(
            partition: partition,
            sourcePath: source.path,
            sourceSize: sourceSize,
            sourceSHA256: try SHA256.file(at: source.path),
            extraFields: extraOperationFields
        )
        let plan = directory.url.appendingPathComponent("plan.json")
        let digest = try writeJSONObject(
            Fixtures.writePlanObject(device: device, operations: [operation]),
            to: plan
        )
        return WritePlanFixture(
            directory: directory,
            inputRoot: inputRoot,
            profile: try Fixtures.decodeProfile(),
            plan: plan,
            digest: digest
        )
    }

    private func assertInvalidWritePlan(
        _ fixture: WritePlanFixture,
        messageFragment: String,
        file: StaticString = #filePath,
        line: UInt = #line
    ) {
        assertR46HError(
            try Validation.loadWritePlan(
                path: fixture.plan.path,
                expectedSHA256: fixture.digest,
                profile: fixture.profile,
                device: "/dev/disk4",
                inputRoot: fixture.inputRoot.path
            ),
            file: file,
            line: line
        ) {
            if case .invalidData(let message) = $0 { return message.contains(messageFragment) }
            return false
        }
    }

    func testWritePlanRejectsMalformedTargetPreWriteHash() throws {
        let fixture = try makeWritePlanFixture(
            extraOperationFields: ["target_sha256_before": "not-a-sha256"]
        )
        assertInvalidWritePlan(fixture, messageFragment: "not a full-partition image")
    }

    private static func mutatePartition(
        _ name: String,
        in card: inout [String: Any],
        mutation: (inout [String: Any]) -> Void
    ) {
        guard var partition = card[name] as? [String: Any] else {
            XCTFail("missing \(name) partition fixture")
            return
        }
        mutation(&partition)
        card[name] = partition
    }

    private func assertProfileIdentityRejected(
        _ object: [String: Any],
        mutation: String = "mixed profile identity",
        file: StaticString = #filePath,
        line: UInt = #line
    ) {
        do {
            try Validation.validate(profile: Fixtures.decodeProfile(object))
            XCTFail("accepted invalid profile mutation: \(mutation)", file: file, line: line)
        } catch let error as R46HError {
            guard case .invalidData = error else {
                XCTFail("unexpected error for \(mutation): \(error)", file: file, line: line)
                return
            }
        } catch {
            XCTFail("unexpected error type for \(mutation): \(error)", file: file, line: line)
        }
    }

    private func assertRejectedSource(
        _ sourcePath: String,
        directory: TestDirectory,
        inputRoot: URL,
        profile: CardProfile,
        file: StaticString = #filePath,
        line: UInt = #line
    ) throws {
        let plan = directory.url.appendingPathComponent("plan-\(UUID().uuidString).json")
        let digest = try writeJSONObject(
            Fixtures.writePlanObject(operations: [Fixtures.operation(sourcePath: sourcePath)]),
            to: plan
        )
        assertR46HError(
            try Validation.loadWritePlan(
                path: plan.path,
                expectedSHA256: digest,
                profile: profile,
                device: "/dev/disk4",
                inputRoot: inputRoot.path
            ),
            file: file,
            line: line
        ) {
            if case .unsafePath = $0 { return true }
            return false
        }
    }

    private func assertRejectedKeySet(
        _ object: [String: Any],
        directory: TestDirectory,
        inputRoot: URL,
        profile: CardProfile,
        file: StaticString = #filePath,
        line: UInt = #line
    ) throws {
        let plan = directory.url.appendingPathComponent("keys-\(UUID().uuidString).json")
        let digest = try writeJSONObject(object, to: plan)
        assertR46HError(
            try Validation.loadWritePlan(
                path: plan.path,
                expectedSHA256: digest,
                profile: profile,
                device: "/dev/disk4",
                inputRoot: inputRoot.path
            ),
            file: file,
            line: line
        ) {
            if case .invalidData(let message) = $0 { return message.contains("unknown or missing") }
            return false
        }
    }
}
