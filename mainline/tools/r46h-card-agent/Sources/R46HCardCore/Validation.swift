import Darwin
import Foundation

public enum Validation {
    private static let auditedCardsByProfileID: [String: CardProfile.Card] = [
        "hl-r46h-v22-g92-v1": CardProfile.Card(
            wholeSize: 31_914_983_424,
            sectorSize: 512,
            partitionScheme: "FDisk_partition_scheme",
            boot: CardProfile.Partition(
                number: 1,
                offset: 16_777_216,
                size: 117_440_512,
                volumeUUID: "575BC58C-96FA-3E4F-958B-7A30D5210C3D",
                partUUID: nil
            ),
            root: CardProfile.Partition(
                number: 2,
                offset: 134_217_728,
                size: 10_716_877_312,
                volumeUUID: nil,
                partUUID: "c9f931c9-02"
            ),
            easyroms: CardProfile.Partition(
                number: 3,
                offset: 10_851_095_040,
                size: 21_063_888_384,
                volumeUUID: "2D584C38-94B7-38C2-B369-6A7A82C72CC2",
                partUUID: nil
            ),
            g92PrefixSize: 16_777_216,
            g92PrefixSHA256: "91a1f0d5f84e9589843ebf1eb0889669a5da64632fd258ef872f890b446a998b"
        ),
        "hl-r46h-v22-g92-31719424000-v1": CardProfile.Card(
            wholeSize: 31_719_424_000,
            sectorSize: 512,
            partitionScheme: "FDisk_partition_scheme",
            boot: CardProfile.Partition(
                number: 1,
                offset: 16_777_216,
                size: 117_440_512,
                volumeUUID: "575BC58C-96FA-3E4F-958B-7A30D5210C3D",
                partUUID: nil
            ),
            root: CardProfile.Partition(
                number: 2,
                offset: 134_217_728,
                size: 10_716_877_312,
                volumeUUID: nil,
                partUUID: "c9f931c9-02"
            ),
            easyroms: CardProfile.Partition(
                number: 3,
                offset: 10_851_095_040,
                size: 20_868_328_960,
                volumeUUID: "E1F5295C-4B12-A54A-ACB7-317194240001",
                partUUID: nil
            ),
            g92PrefixSize: 16_777_216,
            g92PrefixSHA256: "97ede10075b3257c638a04b3044c9dda2d8dd9adc6f6fee3be7b004a31fb135e"
        ),
        "hl-r46h-v22-g92-31719424000-p3-recovery-v1": CardProfile.Card(
            wholeSize: 31_719_424_000,
            sectorSize: 512,
            partitionScheme: "FDisk_partition_scheme",
            boot: CardProfile.Partition(
                number: 1,
                offset: 16_777_216,
                size: 117_440_512,
                volumeUUID: "575BC58C-96FA-3E4F-958B-7A30D5210C3D",
                partUUID: nil
            ),
            root: CardProfile.Partition(
                number: 2,
                offset: 134_217_728,
                size: 10_716_877_312,
                volumeUUID: nil,
                partUUID: "c9f931c9-02"
            ),
            easyroms: CardProfile.Partition(
                number: 3,
                offset: 10_851_095_040,
                size: 20_868_328_960,
                volumeUUID: "5C29F5E1-124B-4AA5-ACB7-317194240001",
                partUUID: nil
            ),
            g92PrefixSize: 16_777_216,
            g92PrefixSHA256: "97ede10075b3257c638a04b3044c9dda2d8dd9adc6f6fee3be7b004a31fb135e"
        ),
        "hl-r46h-v22-g92-62534975488-v1": CardProfile.Card(
            wholeSize: 62_534_975_488,
            sectorSize: 512,
            partitionScheme: "FDisk_partition_scheme",
            boot: CardProfile.Partition(
                number: 1,
                offset: 16_777_216,
                size: 117_440_512,
                volumeUUID: "575BC58C-96FA-3E4F-958B-7A30D5210C3D",
                partUUID: nil
            ),
            root: CardProfile.Partition(
                number: 2,
                offset: 134_217_728,
                size: 10_716_877_312,
                volumeUUID: nil,
                partUUID: "c9f931c9-02"
            ),
            easyroms: CardProfile.Partition(
                number: 3,
                offset: 10_851_095_040,
                size: 51_683_880_448,
                volumeUUID: "75495362-8048-4A4A-ACB7-625349754881",
                partUUID: nil
            ),
            g92PrefixSize: 16_777_216,
            g92PrefixSHA256: "3fe2feb9cc89ce5f01603199bfc8b715875708a9acc61bfc68b4821e1d8a5da3"
        ),
    ]
    static let supportedProfileIDs = Set(auditedCardsByProfileID.keys)

    public static func loadProfile(path: String, expectedSHA256: String) throws -> CardProfile {
        guard isSHA256(expectedSHA256) else {
            throw R46HError.invalidArgument("profile SHA-256 is malformed")
        }
        let data = try readPinnedFile(path: path, maximumBytes: 1024 * 1024)
        let actual = try SHA256.data(data)
        guard actual == expectedSHA256 else {
            throw R46HError.invalidData("profile SHA-256 mismatch")
        }
        let profile = try JSONDecoder().decode(CardProfile.self, from: data)
        try validate(profile: profile)
        return profile
    }

    public static func validate(profile: CardProfile) throws {
        guard profile.formatVersion == 1 else {
            throw R46HError.invalidData("unsupported profile format")
        }
        guard profile.target == "HL-R46H-V22",
              let auditedCard = auditedCardsByProfileID[profile.profileID] else {
            throw R46HError.invalidData("profile target mismatch")
        }
        guard profile.card.wholeSize > 0,
              profile.card.sectorSize == 512,
              profile.card.partitionScheme == "FDisk_partition_scheme",
              profile.card.g92PrefixSize > 0,
              profile.card.g92PrefixSize <= profile.card.boot.offset,
              isSHA256(profile.card.g92PrefixSHA256) else {
            throw R46HError.invalidData("profile card geometry is invalid")
        }

        let partitions = [profile.card.boot, profile.card.root, profile.card.easyroms]
        guard profile.card.boot.number == 1,
              profile.card.root.number == 2,
              profile.card.easyroms.number == 3 else {
            throw R46HError.invalidData("profile partition roles must be p1/p2/p3")
        }
        var end: UInt64 = 0
        for partition in partitions.sorted(by: { $0.offset < $1.offset }) {
            guard partition.number > 0,
                  partition.offset >= end,
                  partition.size > 0,
                  partition.offset <= profile.card.wholeSize,
                  partition.size <= profile.card.wholeSize - partition.offset else {
                throw R46HError.invalidData("profile partitions overlap or exceed the card")
            }
            end = partition.offset + partition.size
        }
        guard profile.card == auditedCard else {
            throw R46HError.invalidData("profile card identity does not match the audited profile")
        }
    }

    public static func loadWritePlan(
        path: String,
        expectedSHA256: String,
        profile: CardProfile,
        device: String,
        inputRoot: String
    ) throws -> WritePlan {
        guard isSHA256(expectedSHA256) else {
            throw R46HError.invalidArgument("write-plan SHA-256 is malformed")
        }
        let data = try readPinnedFile(path: path, maximumBytes: 1024 * 1024)
        guard try SHA256.data(data) == expectedSHA256 else {
            throw R46HError.invalidData("write-plan SHA-256 mismatch")
        }
        try validateWritePlanKeys(data)
        let plan = try JSONDecoder().decode(WritePlan.self, from: data)
        guard plan.formatVersion == 1,
              plan.profileID == profile.profileID,
              plan.device == device,
              !plan.operations.isEmpty else {
            throw R46HError.invalidData("write plan header mismatch")
        }

        let canonicalRoot = try canonicalDirectory(inputRoot)
        var ids = Set<String>()
        for operation in plan.operations {
            guard ids.insert(operation.id).inserted,
                  operation.id.range(of: "^[a-z0-9][a-z0-9._-]{0,63}$", options: .regularExpression) != nil else {
                throw R46HError.invalidData("write operation ID is invalid or duplicated")
            }
            guard operation.partition != .prefix,
                  let partition = profile.partition(for: operation.partition),
                  operation.sourceSize == partition.size,
                  isSHA256(operation.sourceSHA256),
                  isSHA256(operation.targetSHA256Before) else {
                throw R46HError.invalidData("write operation \(operation.id) is not a full-partition image")
            }
            let source = try canonicalRegularFile(operation.sourcePath)
            guard isDescendant(source, of: canonicalRoot), source.size == operation.sourceSize else {
                throw R46HError.unsafePath("write source is outside input root or has the wrong size")
            }
        }
        return plan
    }

    public static func validateDevicePath(_ path: String) throws {
        guard path.range(of: "^/dev/disk[1-9][0-9]*$", options: .regularExpression) != nil else {
            throw R46HError.invalidArgument("device must be /dev/diskN with N > 0")
        }
    }

    public static func validateOutputName(_ value: String) throws {
        guard value.range(of: "^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", options: .regularExpression) != nil,
              value != ".",
              value != ".." else {
            throw R46HError.invalidArgument("output name is unsafe")
        }
    }

    public static func validateRelativeVolumePath(_ value: String) throws -> String {
        if value == "." { return value }
        guard !value.isEmpty,
              !value.hasPrefix("/"),
              !value.contains("\0") else {
            throw R46HError.unsafePath("volume path must be relative")
        }
        let components = value.split(separator: "/", omittingEmptySubsequences: false)
        guard components.allSatisfy({ !$0.isEmpty && $0 != "." && $0 != ".." }) else {
            throw R46HError.unsafePath("volume path contains an unsafe component")
        }
        return components.joined(separator: "/")
    }

    public static func canonicalDirectory(_ path: String) throws -> String {
        var status = stat()
        guard lstat(path, &status) == 0 else {
            throw R46HError.system("lstat \(path): \(posixMessage())")
        }
        guard (status.st_mode & S_IFMT) == S_IFDIR,
              (status.st_mode & S_IFMT) != S_IFLNK else {
            throw R46HError.unsafePath("not a non-symlink directory: \(path)")
        }
        guard let resolved = realpath(path, nil) else {
            throw R46HError.system("realpath \(path): \(posixMessage())")
        }
        defer { free(resolved) }
        return String(cString: resolved)
    }

    public struct FileIdentity: Equatable, Sendable {
        public let path: String
        public let device: dev_t
        public let inode: ino_t
        public let owner: uid_t
        public let mode: mode_t
        public let size: UInt64
    }

    public static func regularFileIdentity(path: String) throws -> FileIdentity {
        var status = stat()
        guard lstat(path, &status) == 0 else {
            throw R46HError.system("lstat \(path): \(posixMessage())")
        }
        guard (status.st_mode & S_IFMT) == S_IFREG else {
            throw R46HError.unsafePath("not a regular non-symlink file: \(path)")
        }
        guard status.st_size >= 0 else {
            throw R46HError.invalidData("file has a negative size: \(path)")
        }
        return FileIdentity(
            path: path,
            device: status.st_dev,
            inode: status.st_ino,
            owner: status.st_uid,
            mode: status.st_mode,
            size: UInt64(status.st_size)
        )
    }

    public static func canonicalRegularFile(_ path: String) throws -> FileIdentity {
        let identity = try regularFileIdentity(path: path)
        guard let resolved = realpath(path, nil) else {
            throw R46HError.system("realpath \(path): \(posixMessage())")
        }
        defer { free(resolved) }
        return FileIdentity(
            path: String(cString: resolved),
            device: identity.device,
            inode: identity.inode,
            owner: identity.owner,
            mode: identity.mode,
            size: identity.size
        )
    }

    public static func isDescendant(_ file: FileIdentity, of directory: String) -> Bool {
        file.path.hasPrefix(directory.hasSuffix("/") ? directory : directory + "/")
    }

    private static func readPinnedFile(path: String, maximumBytes: UInt64) throws -> Data {
        let descriptor = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW)
        guard descriptor >= 0 else {
            throw R46HError.system("open pinned file \(path): \(posixMessage())")
        }
        defer { close(descriptor) }
        var before = stat()
        guard fstat(descriptor, &before) == 0,
              (before.st_mode & S_IFMT) == S_IFREG,
              before.st_size >= 0,
              UInt64(before.st_size) <= maximumBytes else {
            throw R46HError.unsafePath("pinned file is not a bounded regular file: \(path)")
        }

        let expected = Int(before.st_size)
        var data = Data(count: expected)
        try data.withUnsafeMutableBytes { bytes in
            var offset = 0
            while offset < expected {
                let result = Darwin.read(
                    descriptor,
                    bytes.baseAddress!.advanced(by: offset),
                    expected - offset
                )
                if result < 0 {
                    if errno == EINTR { continue }
                    throw R46HError.system("read pinned file \(path): \(posixMessage())")
                }
                guard result > 0 else {
                    throw R46HError.invalidData("pinned file became shorter while reading: \(path)")
                }
                offset += result
            }
        }
        var extra: UInt8 = 0
        while true {
            let result = Darwin.read(descriptor, &extra, 1)
            if result < 0, errno == EINTR { continue }
            guard result == 0 else {
                if result < 0 {
                    throw R46HError.system("finish pinned file read \(path): \(posixMessage())")
                }
                throw R46HError.invalidData("pinned file grew while reading: \(path)")
            }
            break
        }
        var after = stat()
        guard fstat(descriptor, &after) == 0,
              after.st_dev == before.st_dev,
              after.st_ino == before.st_ino,
              after.st_size == before.st_size else {
            throw R46HError.unsafePath("pinned file identity changed while reading: \(path)")
        }
        return data
    }

    private static func validateWritePlanKeys(_ data: Data) throws {
        guard let root = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              Set(root.keys) == ["format_version", "profile_id", "device", "operations"],
              let operations = root["operations"] as? [[String: Any]] else {
            throw R46HError.invalidData("write plan contains unknown or missing top-level keys")
        }
        let expected: Set<String> = [
            "id", "description", "partition", "source_path", "source_size", "source_sha256",
            "target_sha256_before",
        ]
        guard operations.allSatisfy({ Set($0.keys) == expected }) else {
            throw R46HError.invalidData("write plan operation contains unknown or missing keys")
        }
    }
}
