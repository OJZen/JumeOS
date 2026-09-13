import Darwin
import Foundation

public struct CommandResult: Equatable, Sendable {
    public let status: Int32
    public let output: String
}

public final class CommandRunner: @unchecked Sendable {
    public init() {}

    public func run(
        _ executable: String,
        arguments: [String],
        timeout: TimeInterval = 60,
        cancelled: (() -> Bool)? = nil
    ) throws -> CommandResult {
        guard timeout > 0 else {
            throw R46HError.invalidArgument("command timeout must be positive")
        }
        let process = Process()
        let pipe = Pipe()
        process.executableURL = URL(fileURLWithPath: executable)
        process.arguments = arguments
        process.environment = [
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "LC_ALL": "C",
            "LANG": "C",
            "HOME": "/var/empty",
        ]
        process.standardOutput = pipe
        process.standardError = pipe
        process.standardInput = FileHandle.nullDevice
        do {
            try process.run()
        } catch {
            throw R46HError.system("launch \(executable): \(error.localizedDescription)")
        }
        let outputLock = NSLock()
        var output = Data()
        var readFailure: Error?
        var outputExceeded = false
        let reader = DispatchGroup()
        reader.enter()
        DispatchQueue.global(qos: .utility).async {
            defer { reader.leave() }
            do {
                while let chunk = try pipe.fileHandleForReading.read(upToCount: 64 * 1024), !chunk.isEmpty {
                    outputLock.lock()
                    if output.count > 16 * 1024 * 1024 - chunk.count {
                        outputExceeded = true
                        outputLock.unlock()
                        _ = kill(process.processIdentifier, SIGKILL)
                        continue
                    }
                    output.append(chunk)
                    outputLock.unlock()
                }
            } catch {
                outputLock.lock()
                readFailure = error
                outputLock.unlock()
            }
        }

        let deadline = Date().addingTimeInterval(timeout)
        var cancellationTriggered = false
        var timeoutTriggered = false
        while process.isRunning {
            if cancelled?() == true {
                cancellationTriggered = true
                _ = kill(process.processIdentifier, SIGKILL)
            } else if Date() >= deadline {
                timeoutTriggered = true
                _ = kill(process.processIdentifier, SIGKILL)
            }
            usleep(100_000)
        }
        process.waitUntilExit()
        reader.wait()

        outputLock.lock()
        let finalOutput = output
        let finalReadFailure = readFailure
        let finalOutputExceeded = outputExceeded
        outputLock.unlock()
        if cancellationTriggered {
            throw R46HError.cancelled("command cancelled: \(executable)")
        }
        if timeoutTriggered {
            throw R46HError.system("command timed out after \(Int(timeout)) seconds: \(executable)")
        }
        if let finalReadFailure {
            throw R46HError.system("read command output: \(finalReadFailure.localizedDescription)")
        }
        guard !finalOutputExceeded else {
            throw R46HError.invalidData("command output exceeds 16 MiB")
        }
        return CommandResult(
            status: process.terminationStatus,
            output: String(decoding: finalOutput, as: UTF8.self)
        )
    }
}

public struct DiskInfo: Equatable, Sendable {
    public let raw: String
    public let fields: [String: String]

    public init(raw: String) {
        self.raw = raw
        var parsed: [String: String] = [:]
        for line in raw.split(separator: "\n", omittingEmptySubsequences: false) {
            guard let colon = line.firstIndex(of: ":") else { continue }
            let key = line[..<colon].trimmingCharacters(in: .whitespaces)
            let value = line[line.index(after: colon)...].trimmingCharacters(in: .whitespaces)
            if !key.isEmpty, parsed[key] == nil {
                parsed[key] = value
            }
        }
        self.fields = parsed
    }

    public init(plistData: Data) throws {
        var format = PropertyListSerialization.PropertyListFormat.xml
        let object = try PropertyListSerialization.propertyList(
            from: plistData,
            options: [],
            format: &format
        )
        guard let values = object as? [String: Any],
              let identifier = values["DeviceIdentifier"] as? String,
              let whole = (values["WholeDisk"] as? NSNumber)?.boolValue,
              let content = values["Content"] as? String,
              let size = (values["Size"] as? NSNumber)?.uint64Value,
              let blockSize = (values["DeviceBlockSize"] as? NSNumber)?.uint64Value else {
            throw R46HError.invalidData("diskutil plist is missing required identity fields")
        }

        var parsed: [String: String] = [
            "Device Identifier": identifier,
            "Whole": whole ? "Yes" : "No",
            "Content (IOContent)": content,
            "Disk Size": "(\(size) Bytes)",
            "Device Block Size": "\(blockSize) Bytes",
        ]
        if let protocolName = values["BusProtocol"] as? String {
            parsed["Protocol"] = protocolName
        }
        if let internalMedia = (values["Internal"] as? NSNumber)?.boolValue {
            parsed["Device Location"] = internalMedia ? "Internal" : "External"
        }
        if let removable = (values["RemovableMedia"] as? NSNumber)?.boolValue {
            parsed["Removable Media"] = removable ? "Removable" : "Fixed"
        }
        if let physical = values["VirtualOrPhysical"] as? String {
            parsed["Virtual"] = physical == "Physical" ? "No" : "Yes"
        }
        if let parent = values["ParentWholeDisk"] as? String {
            parsed["Parent Whole Disk"] = parent
        }
        if let offset = (values["PartitionMapPartitionOffset"] as? NSNumber)?.uint64Value {
            parsed["Partition Offset"] = "\(offset) Bytes"
        }
        if let uuid = values["VolumeUUID"] as? String, !uuid.isEmpty {
            parsed["Volume UUID"] = uuid
        }
        let mountPoint = (values["MountPoint"] as? String) ?? ""
        if mountPoint.isEmpty {
            parsed["Mounted"] = "No"
            parsed["Volume Read-Only"] = "Not applicable (not mounted)"
        } else {
            guard let writable = (values["WritableVolume"] as? NSNumber)?.boolValue else {
                throw R46HError.invalidData("mounted diskutil plist is missing WritableVolume")
            }
            parsed["Mounted"] = "Yes"
            parsed["Mount Point"] = mountPoint
            parsed["Volume Read-Only"] = writable ? "No" : "Yes (read-only mount flag set)"
        }
        self.raw = String(decoding: plistData, as: UTF8.self)
        self.fields = parsed
    }

    public subscript(_ key: String) -> String? { fields[key] }

    public func bytes(in key: String) -> UInt64? {
        guard let value = fields[key] else { return nil }
        let pattern = #"\(([0-9]+) Bytes\)"#
        guard let range = value.range(of: pattern, options: .regularExpression) else { return nil }
        let matched = value[range]
        guard let token = matched.split(whereSeparator: { !$0.isNumber }).first else { return nil }
        return UInt64(token)
    }

    public func leadingUInt(in key: String) -> UInt64? {
        guard let value = fields[key], let token = value.split(separator: " ").first else { return nil }
        return UInt64(token)
    }
}

public struct CardSnapshot: Equatable, Sendable {
    public let whole: DiskInfo
    public let boot: DiskInfo
    public let root: DiskInfo
    public let easyroms: DiskInfo
    public let prefixSHA256: String

    public var allUnmounted: Bool {
        [boot, root, easyroms].allSatisfy {
            $0["Mounted"] == "No" || $0["Mounted"]?.hasPrefix("Not applicable") == true
        }
    }

    public var summaryItems: [[String: String]] {
        [
            item(name: "whole", info: whole),
            item(name: "boot", info: boot),
            item(name: "root", info: root),
            item(name: "easyroms", info: easyroms),
        ]
    }

    private func item(name: String, info: DiskInfo) -> [String: String] {
        [
            "name": name,
            "identifier": info["Device Identifier"] ?? "unknown",
            "mounted": info["Mounted"] ?? "unknown",
            "mount_point": info["Mount Point"] ?? "-",
            "read_only": info["Volume Read-Only"] ?? "unknown",
            "size": info["Disk Size"] ?? "unknown",
        ]
    }
}
