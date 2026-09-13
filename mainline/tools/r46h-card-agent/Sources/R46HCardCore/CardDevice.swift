import Darwin
import Foundation
import R46HDiskIO

public final class CardDevice: @unchecked Sendable {
    public typealias Progress = (_ completed: UInt64, _ total: UInt64) throws -> Void

    public let device: String
    public let profile: CardProfile
    public let ownerUID: uid_t
    public let ownerGID: gid_t
    public let sessionDirectory: String
    private let sessionDirectoryDescriptor: Int32
    private let sessionIgnoresOwnership: Bool

    private let runner: CommandRunner
    private let rawDevice: String

    public init(
        device: String,
        profile: CardProfile,
        ownerUID: uid_t,
        ownerGID: gid_t,
        sessionDirectory: String,
        sessionDirectoryDescriptor: Int32,
        runner: CommandRunner = CommandRunner()
    ) throws {
        try Validation.validateDevicePath(device)
        var sessionStatus = stat()
        var filesystemStatus = statfs()
        guard fstat(sessionDirectoryDescriptor, &sessionStatus) == 0,
              fstatfs(sessionDirectoryDescriptor, &filesystemStatus) == 0,
              (sessionStatus.st_mode & S_IFMT) == S_IFDIR else {
            close(sessionDirectoryDescriptor)
            throw R46HError.unsafePath("session directory FD identity mismatch")
        }
        let ignoresOwnership = (filesystemStatus.f_flags & UInt32(MNT_IGNORE_OWNERSHIP)) != 0
        guard ignoresOwnership || sessionStatus.st_uid == ownerUID else {
            close(sessionDirectoryDescriptor)
            throw R46HError.unsafePath("session directory FD owner mismatch")
        }
        guard (sessionStatus.st_mode & 0o777) == 0o700 else {
            close(sessionDirectoryDescriptor)
            throw R46HError.unsafePath("session directory FD permissions must be 0700")
        }
        self.device = device
        self.profile = profile
        self.ownerUID = ownerUID
        self.ownerGID = ownerGID
        self.sessionDirectory = sessionDirectory
        self.sessionDirectoryDescriptor = sessionDirectoryDescriptor
        self.sessionIgnoresOwnership = ignoresOwnership
        self.runner = runner
        self.rawDevice = "/dev/r" + device.dropFirst("/dev/".count)
    }

    deinit {
        close(sessionDirectoryDescriptor)
    }

    public func snapshot(cancelled: (() -> Bool)? = nil) throws -> CardSnapshot {
        let whole = try diskInfo(device, cancelled: cancelled)
        let boot = try diskInfo(partitionPath(profile.card.boot.number), cancelled: cancelled)
        let root = try diskInfo(partitionPath(profile.card.root.number), cancelled: cancelled)
        let easyroms = try diskInfo(partitionPath(profile.card.easyroms.number), cancelled: cancelled)
        try verify(whole: whole, boot: boot, root: root, easyroms: easyroms)

        let descriptor = try openCharacterDevice(rawDevice, writable: false)
        defer { close(descriptor) }
        let prefixHash = try SHA256.descriptorHash(
            descriptor,
            length: profile.card.g92PrefixSize,
            cancelled: cancelled
        )
        guard prefixHash == profile.card.g92PrefixSHA256 else {
            throw R46HError.invalidData("g92 prefix SHA-256 mismatch")
        }
        return CardSnapshot(
            whole: whole,
            boot: boot,
            root: root,
            easyroms: easyroms,
            prefixSHA256: prefixHash
        )
    }

    public func unmount(cancelled: (() -> Bool)? = nil) throws -> CardSnapshot {
        _ = try snapshot(cancelled: cancelled)
        let result = try runner.run(
            "/usr/sbin/diskutil",
            arguments: ["unmountDisk", device],
            cancelled: cancelled
        )
        guard result.status == 0 else {
            throw R46HError.system("diskutil unmountDisk failed: \(trimmed(result.output))")
        }
        let resultSnapshot = try snapshot(cancelled: cancelled)
        guard resultSnapshot.allUnmounted else {
            throw R46HError.invalidData("one or more card partitions remain mounted")
        }
        return resultSnapshot
    }

    public func mountReadOnly(
        _ volume: VolumeTarget,
        cancelled: (() -> Bool)? = nil
    ) throws -> CardSnapshot {
        let current = try snapshot(cancelled: cancelled)
        guard current.allUnmounted else {
            throw R46HError.invalidData("all card partitions must be unmounted before a read-only mount")
        }
        let number = volume == .boot ? profile.card.boot.number : profile.card.easyroms.number
        let path = partitionPath(number)
        let result = try runner.run(
            "/usr/sbin/diskutil",
            arguments: ["mount", "readOnly", path],
            cancelled: cancelled
        )
        guard result.status == 0 else {
            throw R46HError.system("diskutil read-only mount failed: \(trimmed(result.output))")
        }
        let mounted = try snapshot(cancelled: cancelled)
        let info = volume == .boot ? mounted.boot : mounted.easyroms
        guard info["Mounted"] == "Yes",
              info["Volume Read-Only"]?.hasPrefix("Yes") == true,
              info["Mount Point"] != nil else {
            throw R46HError.invalidData("diskutil did not produce a proven read-only mount")
        }
        return mounted
    }

    public func hashRaw(
        target: CardTarget,
        progress: Progress? = nil,
        cancelled: (() -> Bool)? = nil
    ) throws -> (sha256: String, bytes: UInt64) {
        let current = try requireUnmounted(cancelled: cancelled)
        _ = current
        let (path, offset, length) = rawRange(for: target)
        let descriptor = try openCharacterDevice(path, writable: false)
        defer { close(descriptor) }
        let hash = try SHA256.descriptorHash(
            descriptor,
            offset: offset,
            length: length,
            progress: { try progress?($0, length) },
            cancelled: cancelled
        )
        return (hash, length)
    }

    public func cloneRaw(
        target: CardTarget,
        outputName: String,
        offset: UInt64? = nil,
        length: UInt64? = nil,
        progress: Progress? = nil,
        cancelled: (() -> Bool)? = nil
    ) throws -> (path: String, sha256: String, bytes: UInt64) {
        try Validation.validateOutputName(outputName)
        _ = try requireUnmounted(cancelled: cancelled)
        let range = rawRange(for: target)
        let requestedOffset = offset ?? 0
        let requestedLength = length ?? range.length
        guard requestedOffset <= range.length,
              requestedLength > 0,
              requestedLength <= range.length - requestedOffset else {
            throw R46HError.invalidArgument("clone range exceeds \(target.rawValue)")
        }
        if offset != nil || length != nil {
            guard requestedLength <= 64 * 1024 * 1024 else {
                throw R46HError.invalidArgument("samples are limited to 64 MiB")
            }
        }

        let input = try openCharacterDevice(range.path, writable: false)
        defer { close(input) }
        guard lseek(input, off_t(range.offset + requestedOffset), SEEK_SET) >= 0 else {
            throw R46HError.system("seek raw input: \(posixMessage())")
        }

        let outputPath = sessionDirectory + "/" + outputName
        let output = openat(
            sessionDirectoryDescriptor,
            outputName,
            O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW,
            0o600
        )
        guard output >= 0 else {
            throw R46HError.system("create \(outputPath): \(posixMessage())")
        }
        var keepOutput = false
        defer {
            close(output)
            if !keepOutput { _ = unlinkat(sessionDirectoryDescriptor, outputName, 0) }
        }

        let hash = try copyAndHash(
            input: input,
            output: output,
            length: requestedLength,
            progress: progress,
            cancelled: cancelled,
            cancellationAllowed: true
        )
        if !sessionIgnoresOwnership, fchown(output, ownerUID, ownerGID) != 0 {
            throw R46HError.system("chown clone: \(posixMessage())")
        }
        guard fsync(output) == 0 else {
            throw R46HError.system("fsync clone: \(posixMessage())")
        }
        keepOutput = true
        return (outputPath, hash, requestedLength)
    }

    public func hashVolumeFile(
        volume: VolumeTarget,
        relativePath: String,
        progress: Progress? = nil,
        cancelled: (() -> Bool)? = nil
    ) throws -> (String, UInt64) {
        let path = try secureVolumePath(
            volume: volume,
            relativePath: relativePath,
            expectedDirectory: false,
            cancelled: cancelled
        )
        let identity = try Validation.regularFileIdentity(path: path)
        let descriptor = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW)
        guard descriptor >= 0 else {
            throw R46HError.system("open read-only volume file: \(posixMessage())")
        }
        defer { close(descriptor) }
        var opened = stat()
        guard fstat(descriptor, &opened) == 0,
              opened.st_dev == identity.device,
              opened.st_ino == identity.inode,
              opened.st_size == off_t(identity.size) else {
            throw R46HError.unsafePath("volume file identity changed during open")
        }
        let hash = try SHA256.descriptorHash(
            descriptor,
            length: identity.size,
            progress: { try progress?($0, identity.size) },
            cancelled: cancelled
        )
        return (hash, identity.size)
    }

    public func listVolumeDirectory(
        volume: VolumeTarget,
        relativePath: String,
        cancelled: (() -> Bool)? = nil
    ) throws -> [[String: String]] {
        let path = try secureVolumePath(
            volume: volume,
            relativePath: relativePath,
            expectedDirectory: true,
            cancelled: cancelled
        )
        if cancelled?() == true {
            throw R46HError.cancelled("directory listing cancelled")
        }
        let descriptor = open(path, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW)
        guard descriptor >= 0 else {
            throw R46HError.system("open volume directory: \(posixMessage())")
        }
        var opened = stat()
        guard fstat(descriptor, &opened) == 0,
              (opened.st_mode & S_IFMT) == S_IFDIR else {
            close(descriptor)
            throw R46HError.unsafePath("volume directory identity changed during open")
        }
        guard let directory = fdopendir(descriptor) else {
            close(descriptor)
            throw R46HError.system("fdopendir volume directory: \(posixMessage())")
        }
        defer { closedir(directory) }

        var items: [[String: String]] = []
        while true {
            if cancelled?() == true {
                throw R46HError.cancelled("directory listing cancelled")
            }
            errno = 0
            guard let entry = readdir(directory) else {
                guard errno == 0 else {
                    throw R46HError.system("readdir volume directory: \(posixMessage())")
                }
                break
            }
            let name: String? = withUnsafePointer(to: entry.pointee.d_name) { pointer in
                pointer.withMemoryRebound(to: CChar.self, capacity: Int(MAXNAMLEN) + 1) {
                    String(validatingUTF8: $0)
                }
            }
            guard let name else {
                throw R46HError.invalidData("directory entry is not valid UTF-8")
            }
            if name == "." || name == ".." { continue }
            guard !name.unicodeScalars.contains(where: { $0.value < 0x20 || $0.value == 0x7f }) else {
                throw R46HError.invalidData("directory entry contains a control character")
            }
            guard items.count < 10_000 else {
                throw R46HError.invalidData("directory contains more than 10,000 entries")
            }
            var status = stat()
            let statusResult = name.withCString {
                fstatat(descriptor, $0, &status, AT_SYMLINK_NOFOLLOW)
            }
            guard statusResult == 0 else {
                throw R46HError.system("fstatat directory entry: \(posixMessage())")
            }
            let kind: String
            switch status.st_mode & S_IFMT {
            case S_IFREG: kind = "file"
            case S_IFDIR: kind = "directory"
            case S_IFLNK: kind = "symlink"
            default: kind = "special"
            }
            items.append([
                "name": name,
                "type": kind,
                "size": status.st_size >= 0 ? String(status.st_size) : "invalid",
            ])
        }
        return items.sorted { ($0["name"] ?? "") < ($1["name"] ?? "") }
    }

    public func fsckExFATReadOnly(
        outputName: String = "fsck-exfat-read-only.log",
        cancelled: (() -> Bool)? = nil
    ) throws -> (Int32, String) {
        try Validation.validateOutputName(outputName)
        _ = try requireUnmounted(cancelled: cancelled)
        let raw = rawPartitionPath(profile.card.easyroms.number)
        let result = try runner.run(
            "/sbin/fsck_exfat",
            arguments: ["-n", "-d", raw],
            timeout: 30 * 60,
            cancelled: cancelled
        )
        guard result.status == 0 else {
            throw R46HError.invalidData("fsck_exfat reported a non-clean result rc=\(result.status): \(trimmed(result.output))")
        }
        let outputPath = sessionDirectory + "/" + outputName
        try writeOwnedFile(Data(result.output.utf8), name: outputName)
        return (result.status, outputPath)
    }

    public func executeWrite(
        operation: WritePlan.Operation,
        inputRoot: String,
        stagingProgress: Progress? = nil,
        writeProgress: Progress? = nil,
        cancelled: (() -> Bool)? = nil,
        writeStarted: (() throws -> Void)? = nil
    ) throws -> [String: String] {
        guard operation.partition != .prefix,
              let partition = profile.partition(for: operation.partition),
              partition.size == operation.sourceSize else {
            throw R46HError.invalidData("write operation does not cover one exact partition")
        }
        let canonicalRoot = try Validation.canonicalDirectory(inputRoot)
        let sourceIdentity = try Validation.canonicalRegularFile(operation.sourcePath)
        guard Validation.isDescendant(sourceIdentity, of: canonicalRoot),
              sourceIdentity.size == operation.sourceSize else {
            throw R46HError.unsafePath("write source changed or left the allowed input root")
        }
        _ = try requireUnmounted(cancelled: cancelled)
        let diskClaim = try WholeDiskClaim(device: device, cancelled: cancelled)
        defer { diskClaim.release() }
        let source = open(sourceIdentity.path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW)
        guard source >= 0 else {
            throw R46HError.system("open write source: \(posixMessage())")
        }
        defer { close(source) }
        var openedIdentity = stat()
        guard fstat(source, &openedIdentity) == 0,
              openedIdentity.st_dev == sourceIdentity.device,
              openedIdentity.st_ino == sourceIdentity.inode,
              openedIdentity.st_size == off_t(operation.sourceSize) else {
            throw R46HError.unsafePath("write source identity changed after open")
        }
        let pinned = try openPinnedCard(writeTarget: operation.partition, cancelled: cancelled)
        defer { pinned.closeAll() }
        let prefixBefore = try SHA256.descriptorHash(
            pinned.whole,
            length: profile.card.g92PrefixSize,
            cancelled: cancelled
        )
        guard prefixBefore == profile.card.g92PrefixSHA256 else {
            throw R46HError.invalidData("pinned whole-device prefix SHA-256 mismatch")
        }
        let target = pinned.descriptor(for: operation.partition)
        if cancelled?() == true {
            throw R46HError.cancelled("write cancelled before the card was modified")
        }
        let targetHashBefore = try Self.verifyTargetBaseline(
            descriptor: target,
            length: operation.sourceSize,
            expectedSHA256: operation.targetSHA256Before,
            cancelled: cancelled
        )
        guard r46h_disk_synchronize_cache(target) == 0 else {
            throw R46HError.system("preflight DKIOCSYNCHRONIZECACHE target partition: \(posixMessage())")
        }
        if cancelled?() == true {
            throw R46HError.cancelled("write cancelled before the card was modified")
        }

        let stageName = ".write-stage-" + UUID().uuidString.lowercased()
        let stage = openat(
            sessionDirectoryDescriptor,
            stageName,
            O_RDWR | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW,
            0o600
        )
        guard stage >= 0 else {
            throw R46HError.system("create private write staging file: \(posixMessage())")
        }
        guard unlinkat(sessionDirectoryDescriptor, stageName, 0) == 0 else {
            close(stage)
            throw R46HError.system("unlink private write staging file: \(posixMessage())")
        }
        defer { close(stage) }
        let sourceHash = try copyAndHash(
            input: source,
            output: stage,
            length: operation.sourceSize,
            progress: stagingProgress,
            cancelled: cancelled,
            cancellationAllowed: true
        )
        guard sourceHash == operation.sourceSHA256 else {
            throw R46HError.invalidData("write source SHA-256 mismatch")
        }
        guard fsync(stage) == 0,
              fchmod(stage, 0o400) == 0,
              lseek(stage, 0, SEEK_SET) == 0 else {
            throw R46HError.system("seal private write staging file: \(posixMessage())")
        }

        try verifyPinnedCard(pinned)
        if cancelled?() == true {
            throw R46HError.cancelled("write cancelled before the card was modified")
        }
        try writeStarted?()
        let writeHash = try copyAndHash(
            input: stage,
            output: target,
            length: operation.sourceSize,
            progress: { completed, total in try? writeProgress?(completed, total) },
            cancelled: nil,
            cancellationAllowed: false
        )
        guard writeHash == operation.sourceSHA256 else {
            throw R46HError.invalidData("stream hash changed during partition write")
        }
        guard fsync(target) == 0 else {
            throw R46HError.system("fsync written partition: \(posixMessage())")
        }
        guard r46h_disk_synchronize_cache(target) == 0 else {
            throw R46HError.system("DKIOCSYNCHRONIZECACHE written partition: \(posixMessage())")
        }
        guard lseek(target, 0, SEEK_SET) == 0 else {
            throw R46HError.system("rewind written partition: \(posixMessage())")
        }
        let readbackHash = try SHA256.descriptorHash(
            target,
            length: operation.sourceSize,
            progress: { completed in try? writeProgress?(completed, operation.sourceSize) }
        )
        guard readbackHash == operation.sourceSHA256 else {
            throw R46HError.invalidData("partition readback SHA-256 mismatch")
        }
        try verifyPinnedCard(pinned)
        let prefixAfter = try SHA256.descriptorHash(
            pinned.whole,
            length: profile.card.g92PrefixSize
        )
        guard prefixAfter == prefixBefore else {
            throw R46HError.invalidData("g92 prefix or partition table changed during write")
        }
        let current = try snapshot()
        guard current.allUnmounted, current.prefixSHA256 == prefixBefore else {
            throw R46HError.invalidData("card path identity changed during write")
        }
        return [
            "operation_id": operation.id,
            "partition": operation.partition.rawValue,
            "bytes": String(operation.sourceSize),
            "source_sha256": sourceHash,
            "target_sha256_before": targetHashBefore,
            "readback_sha256": readbackHash,
            "prefix_sha256": prefixBefore,
        ]
    }

    static func verifyTargetBaseline(
        descriptor: Int32,
        length: UInt64,
        expectedSHA256: String,
        cancelled: (() -> Bool)? = nil
    ) throws -> String {
        let actual = try SHA256.descriptorHash(
            descriptor,
            length: length,
            cancelled: cancelled
        )
        guard actual == expectedSHA256 else {
            throw R46HError.invalidData(
                "target partition SHA-256 no longer matches the write-plan baseline"
            )
        }
        guard lseek(descriptor, 0, SEEK_SET) == 0 else {
            throw R46HError.system(
                "rewind target partition after baseline hash: \(posixMessage())"
            )
        }
        return actual
    }

    public func fdiskText() throws -> String {
        let result = try runner.run("/usr/sbin/fdisk", arguments: [device])
        guard result.status == 0 else {
            throw R46HError.system("fdisk failed: \(trimmed(result.output))")
        }
        return result.output
    }

    private func diskInfo(_ path: String, cancelled: (() -> Bool)? = nil) throws -> DiskInfo {
        let result = try runner.run(
            "/usr/sbin/diskutil",
            arguments: ["info", "-plist", path],
            cancelled: cancelled
        )
        guard result.status == 0 else {
            throw R46HError.system("diskutil info \(path) failed: \(trimmed(result.output))")
        }
        do {
            return try DiskInfo(plistData: Data(result.output.utf8))
        } catch {
            throw R46HError.invalidData("diskutil info \(path) plist is invalid: \(error)")
        }
    }

    private func verify(
        whole: DiskInfo,
        boot: DiskInfo,
        root: DiskInfo,
        easyroms: DiskInfo
    ) throws {
        let identifier = String(device.dropFirst("/dev/".count))
        guard whole["Device Identifier"] == identifier,
              whole["Whole"] == "Yes",
              whole["Content (IOContent)"] == profile.card.partitionScheme,
              whole["Protocol"] == "USB",
              whole["Device Location"] == "External",
              whole["Removable Media"] == "Removable",
              whole["Virtual"] == "No",
              whole.bytes(in: "Disk Size") == profile.card.wholeSize,
              whole.leadingUInt(in: "Device Block Size") == profile.card.sectorSize else {
            throw R46HError.invalidData("whole-card identity mismatch")
        }
        try verify(partition: boot, expected: profile.card.boot)
        try verify(partition: root, expected: profile.card.root)
        try verify(partition: easyroms, expected: profile.card.easyroms)
    }

    private func verify(partition info: DiskInfo, expected: CardProfile.Partition) throws {
        guard info["Device Identifier"] == String(device.dropFirst("/dev/".count)) + "s\(expected.number)",
              info.leadingUInt(in: "Partition Offset") == expected.offset,
              info.bytes(in: "Disk Size") == expected.size else {
            throw R46HError.invalidData("partition \(expected.number) geometry mismatch")
        }
        if let uuid = expected.volumeUUID,
           info["Volume UUID"] != uuid {
            throw R46HError.invalidData("partition \(expected.number) volume UUID mismatch")
        }
    }

    private func requireUnmounted(cancelled: (() -> Bool)? = nil) throws -> CardSnapshot {
        let current = try snapshot(cancelled: cancelled)
        guard current.allUnmounted else {
            throw R46HError.invalidData("raw operation requires all card partitions to be unmounted")
        }
        return current
    }

    private func rawRange(for target: CardTarget) -> (path: String, offset: UInt64, length: UInt64) {
        switch target {
        case .prefix:
            return (rawDevice, 0, profile.card.g92PrefixSize)
        case .boot:
            return (rawPartitionPath(profile.card.boot.number), 0, profile.card.boot.size)
        case .root:
            return (rawPartitionPath(profile.card.root.number), 0, profile.card.root.size)
        case .easyroms:
            return (rawPartitionPath(profile.card.easyroms.number), 0, profile.card.easyroms.size)
        }
    }

    private func partitionPath(_ number: Int) -> String { "\(device)s\(number)" }
    private func rawPartitionPath(_ number: Int) -> String { "\(rawDevice)s\(number)" }

    private func openCharacterDevice(_ path: String, writable: Bool) throws -> Int32 {
        var status = stat()
        guard lstat(path, &status) == 0,
              (status.st_mode & S_IFMT) == S_IFCHR else {
            throw R46HError.unsafePath("not a raw character device: \(path)")
        }
        let descriptor = open(
            path,
            (writable ? O_RDWR : O_RDONLY) | O_CLOEXEC | O_NOFOLLOW
        )
        guard descriptor >= 0 else {
            throw R46HError.system("open \(path): \(posixMessage())")
        }
        var opened = stat()
        guard fstat(descriptor, &opened) == 0,
              (opened.st_mode & S_IFMT) == S_IFCHR,
              opened.st_rdev == status.st_rdev else {
            close(descriptor)
            throw R46HError.unsafePath("raw device identity changed during open: \(path)")
        }
        return descriptor
    }

    private func prefixHash() throws -> String {
        let descriptor = try openCharacterDevice(rawDevice, writable: false)
        defer { close(descriptor) }
        return try SHA256.descriptorHash(descriptor, length: profile.card.g92PrefixSize)
    }

    private func secureVolumePath(
        volume: VolumeTarget,
        relativePath: String,
        expectedDirectory: Bool,
        cancelled: (() -> Bool)? = nil
    ) throws -> String {
        let relative = try Validation.validateRelativeVolumePath(relativePath)
        let current = try snapshot(cancelled: cancelled)
        let info = volume == .boot ? current.boot : current.easyroms
        guard info["Mounted"] == "Yes",
              info["Volume Read-Only"]?.hasPrefix("Yes") == true,
              let mountPoint = info["Mount Point"] else {
            throw R46HError.invalidData("requested volume is not proven read-only")
        }
        let root = try Validation.canonicalDirectory(mountPoint)
        let lexical = relative == "." ? root : root + "/" + relative
        var status = stat()
        guard lstat(lexical, &status) == 0 else {
            throw R46HError.system("lstat \(lexical): \(posixMessage())")
        }
        let type = status.st_mode & S_IFMT
        guard type == (expectedDirectory ? S_IFDIR : S_IFREG) else {
            throw R46HError.unsafePath("volume path has the wrong type")
        }
        guard let resolved = realpath(lexical, nil) else {
            throw R46HError.system("realpath \(lexical): \(posixMessage())")
        }
        defer { free(resolved) }
        let canonical = String(cString: resolved)
        guard canonical == lexical,
              (canonical == root || canonical.hasPrefix(root + "/")) else {
            throw R46HError.unsafePath("volume path traverses a symlink")
        }
        return canonical
    }

    private func copyAndHash(
        input: Int32,
        output: Int32,
        length: UInt64,
        progress: Progress?,
        cancelled: (() -> Bool)?,
        cancellationAllowed: Bool
    ) throws -> String {
        let bufferSize = 4 * 1024 * 1024
        let buffer = UnsafeMutableRawPointer.allocate(
            byteCount: bufferSize,
            alignment: MemoryLayout<UInt64>.alignment
        )
        defer { buffer.deallocate() }
        let hasher = SHA256Stream()
        var total: UInt64 = 0
        while total < length {
            if cancellationAllowed, cancelled?() == true {
                throw R46HError.cancelled("read operation cancelled")
            }
            let request = Int(min(UInt64(bufferSize), length - total))
            let count = Darwin.read(input, buffer, request)
            if count < 0 {
                if errno == EINTR { continue }
                throw R46HError.system("read transfer input: \(posixMessage())")
            }
            guard count > 0 else {
                throw R46HError.invalidData("unexpected EOF at \(total), expected \(length)")
            }
            var written = 0
            while written < count {
                let result = Darwin.write(output, buffer.advanced(by: written), count - written)
                if result < 0 {
                    if errno == EINTR { continue }
                    throw R46HError.system("write transfer output: \(posixMessage())")
                }
                guard result > 0 else {
                    throw R46HError.system("write transfer made no progress")
                }
                written += result
            }
            try hasher.update(UnsafeRawBufferPointer(start: buffer, count: count))
            total += UInt64(count)
            try progress?(total, length)
        }
        return try hasher.finalize()
    }

    private struct PinnedCard {
        let whole: Int32
        let boot: Int32
        let root: Int32
        let easyroms: Int32

        func descriptor(for target: CardTarget) -> Int32 {
            switch target {
            case .prefix: return whole
            case .boot: return boot
            case .root: return root
            case .easyroms: return easyroms
            }
        }

        func closeAll() {
            close(easyroms)
            close(root)
            close(boot)
            close(whole)
        }
    }

    private func openPinnedCard(
        writeTarget: CardTarget,
        cancelled: (() -> Bool)? = nil
    ) throws -> PinnedCard {
        _ = try requireUnmounted(cancelled: cancelled)
        var descriptors: [Int32] = []
        var keep = false
        defer {
            if !keep { descriptors.reversed().forEach { close($0) } }
        }

        func openPinned(_ path: String, writable: Bool) throws -> Int32 {
            let descriptor = try openCharacterDevice(path, writable: writable)
            descriptors.append(descriptor)
            return descriptor
        }

        let pinned = try PinnedCard(
            whole: openPinned(rawDevice, writable: false),
            boot: openPinned(rawPartitionPath(profile.card.boot.number), writable: writeTarget == .boot),
            root: openPinned(rawPartitionPath(profile.card.root.number), writable: writeTarget == .root),
            easyroms: openPinned(rawPartitionPath(profile.card.easyroms.number), writable: writeTarget == .easyroms)
        )
        try verifyPinnedCard(pinned)
        _ = try requireUnmounted(cancelled: cancelled)
        try verifyDescriptorPath(pinned.whole, path: rawDevice)
        try verifyDescriptorPath(pinned.boot, path: rawPartitionPath(profile.card.boot.number))
        try verifyDescriptorPath(pinned.root, path: rawPartitionPath(profile.card.root.number))
        try verifyDescriptorPath(pinned.easyroms, path: rawPartitionPath(profile.card.easyroms.number))
        keep = true
        return pinned
    }

    private func verifyPinnedCard(_ pinned: PinnedCard) throws {
        try verifyGeometry(
            descriptor: pinned.whole,
            expectedBase: 0,
            expectedSize: profile.card.wholeSize,
            label: "whole"
        )
        try verifyGeometry(descriptor: pinned.boot, expected: profile.card.boot, label: "boot")
        try verifyGeometry(descriptor: pinned.root, expected: profile.card.root, label: "root")
        try verifyGeometry(descriptor: pinned.easyroms, expected: profile.card.easyroms, label: "easyroms")
    }

    private func verifyGeometry(
        descriptor: Int32,
        expected: CardProfile.Partition,
        label: String
    ) throws {
        try verifyGeometry(
            descriptor: descriptor,
            expectedBase: expected.offset,
            expectedSize: expected.size,
            label: label
        )
    }

    private func verifyGeometry(
        descriptor: Int32,
        expectedBase: UInt64,
        expectedSize: UInt64,
        label: String
    ) throws {
        var base: UInt64 = 0
        var size: UInt64 = 0
        var blockSize: UInt32 = 0
        guard r46h_disk_geometry(descriptor, &base, &size, &blockSize) == 0 else {
            throw R46HError.system("read pinned \(label) geometry: \(posixMessage())")
        }
        guard base == expectedBase,
              size == expectedSize,
              UInt64(blockSize) == profile.card.sectorSize else {
            throw R46HError.invalidData("pinned \(label) geometry mismatch")
        }
    }

    private func verifyDescriptorPath(_ descriptor: Int32, path: String) throws {
        var opened = stat()
        var current = stat()
        guard fstat(descriptor, &opened) == 0,
              lstat(path, &current) == 0,
              (current.st_mode & S_IFMT) == S_IFCHR,
              opened.st_rdev == current.st_rdev else {
            throw R46HError.unsafePath("raw device path changed after pinning: \(path)")
        }
    }

    private func writeOwnedFile(_ data: Data, name: String) throws {
        try Validation.validateOutputName(name)
        let descriptor = openat(
            sessionDirectoryDescriptor,
            name,
            O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW,
            0o600
        )
        guard descriptor >= 0 else {
            throw R46HError.system("create \(name): \(posixMessage())")
        }
        var keep = false
        defer {
            close(descriptor)
            if !keep { _ = unlinkat(sessionDirectoryDescriptor, name, 0) }
        }
        try data.withUnsafeBytes { bytes in
            var written = 0
            while written < bytes.count {
                let count = Darwin.write(
                    descriptor,
                    bytes.baseAddress!.advanced(by: written),
                    bytes.count - written
                )
                if count < 0 {
                    if errno == EINTR { continue }
                    throw R46HError.system("write \(name): \(posixMessage())")
                }
                guard count > 0 else {
                    throw R46HError.system("write \(name) made no progress")
                }
                written += count
            }
        }
        if !sessionIgnoresOwnership, fchown(descriptor, ownerUID, ownerGID) != 0 {
            throw R46HError.system("chown \(name): \(posixMessage())")
        }
        guard fsync(descriptor) == 0 else {
            throw R46HError.system("seal \(name): \(posixMessage())")
        }
        keep = true
    }

    private func trimmed(_ value: String) -> String {
        let result = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return result.count <= 2000 ? result : String(result.prefix(2000)) + "..."
    }
}
