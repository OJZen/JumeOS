import Darwin
import Foundation
import R46HCardCore

struct ClientActivity: Sendable {
    let connectionID: String
    let pid: pid_t
    let uid: uid_t
    let processPath: String
    let connectedAt: Date
    var command: String
    var state: String
    var progress: String
}

struct SessionEvent: Codable, Sendable {
    let timestamp: String
    let level: String
    let pid: Int32?
    let command: String?
    let message: String
}

final class SessionState: @unchecked Sendable {
    let sessionID: String
    let sessionDirectory: String
    let mode: AgentMode
    let ownerUID: uid_t
    let socketPath: String
    let tokenPath: String

    private let lock = NSLock()
    private let directoryDescriptor: Int32
    private let eventDescriptor: Int32
    private let useTUI: Bool
    private let ignoresOwnership: Bool
    private let encoder: JSONEncoder
    private let eventQueue = DispatchQueue(label: "r46h-card-agent.events")
    private let renderQueue = DispatchQueue(label: "r46h-card-agent.tui")
    private var activities: [String: ClientActivity] = [:]
    private var recentEvents: [SessionEvent] = []
    private var stopping = false
    private var writeReserved = false
    private var writeActive = false
    private var consumedWriteIDs = Set<String>()
    private var verifiedWriteConnectionIDs = Set<String>()
    private var renderScheduled = false
    private var sealed = false

    init(
        outputRoot: String,
        mode: AgentMode,
        ownerUID: uid_t,
        ownerGID: gid_t,
        useTUI: Bool
    ) throws {
        let root = try Validation.canonicalDirectory(outputRoot)
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "yyyyMMdd'T'HHmmss'Z'"
        let rootDescriptor = open(root, O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW)
        guard rootDescriptor >= 0 else {
            throw R46HError.system("open output root: \(posixMessage())")
        }
        defer { close(rootDescriptor) }
        var rootStatus = stat()
        guard fstat(rootDescriptor, &rootStatus) == 0 else {
            throw R46HError.system("fstat output root: \(posixMessage())")
        }
        var filesystemStatus = statfs()
        guard fstatfs(rootDescriptor, &filesystemStatus) == 0 else {
            throw R46HError.system("fstatfs output root: \(posixMessage())")
        }
        let ignoresOwnership = (filesystemStatus.f_flags & UInt32(MNT_IGNORE_OWNERSHIP)) != 0
        guard (rootStatus.st_mode & S_IFMT) == S_IFDIR,
              (rootStatus.st_uid == ownerUID || ignoresOwnership),
              (rootStatus.st_mode & 0o022) == 0 else {
            let permissions = String(rootStatus.st_mode & 0o777, radix: 8)
            throw R46HError.unsafePath(
                "output root identity mismatch: expected uid=\(ownerUID) mode without group/world write; " +
                "actual uid=\(rootStatus.st_uid) mode=\(permissions) " +
                "ignores_ownership=\(ignoresOwnership ? "yes" : "no")"
            )
        }
        let identifier = "session-\(formatter.string(from: Date()))-\(getpid())-\(UUID().uuidString.lowercased())"
        let directory = root + "/" + identifier
        guard mkdirat(rootDescriptor, identifier, 0o700) == 0 else {
            throw R46HError.system("mkdir session: \(posixMessage())")
        }
        let sessionDescriptor = openat(
            rootDescriptor,
            identifier,
            O_RDONLY | O_DIRECTORY | O_CLOEXEC | O_NOFOLLOW
        )
        guard sessionDescriptor >= 0 else {
            _ = unlinkat(rootDescriptor, identifier, AT_REMOVEDIR)
            throw R46HError.system("open session directory: \(posixMessage())")
        }
        var keep = false
        defer {
            if !keep {
                close(sessionDescriptor)
                _ = unlinkat(rootDescriptor, identifier, AT_REMOVEDIR)
            }
        }
        var sessionStatus = stat()
        guard fstat(sessionDescriptor, &sessionStatus) == 0 else {
            throw R46HError.system("fstat session directory: \(posixMessage())")
        }
        guard (sessionStatus.st_mode & S_IFMT) == S_IFDIR else {
            throw R46HError.unsafePath("created session object is not a directory")
        }
        if !ignoresOwnership {
            guard sessionStatus.st_uid == 0 else {
                throw R46HError.unsafePath(
                    "new session directory owner mismatch: expected root, actual uid=\(sessionStatus.st_uid)"
                )
            }
            guard fchown(sessionDescriptor, ownerUID, ownerGID) == 0 else {
                throw R46HError.system("chown session directory: \(posixMessage())")
            }
        }
        guard fchmod(sessionDescriptor, 0o700) == 0 else {
            throw R46HError.system("chmod session directory: \(posixMessage())")
        }

        let descriptor = openat(
            sessionDescriptor,
            "events.jsonl",
            O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW,
            0o600
        )
        guard descriptor >= 0 else {
            throw R46HError.system("create event log: \(posixMessage())")
        }
        if !ignoresOwnership, fchown(descriptor, ownerUID, ownerGID) != 0 {
            close(descriptor)
            _ = unlinkat(sessionDescriptor, "events.jsonl", 0)
            throw R46HError.system("chown event log: \(posixMessage())")
        }
        guard fchmod(descriptor, 0o600) == 0 else {
            close(descriptor)
            _ = unlinkat(sessionDescriptor, "events.jsonl", 0)
            throw R46HError.system("chmod event log: \(posixMessage())")
        }

        self.sessionID = identifier
        self.sessionDirectory = directory
        self.mode = mode
        self.ownerUID = ownerUID
        self.socketPath = "/private/tmp/r46h-card-agent-\(ownerUID)/control.sock"
        self.tokenPath = "/private/tmp/r46h-card-agent-\(ownerUID)/token"
        self.directoryDescriptor = sessionDescriptor
        self.eventDescriptor = descriptor
        self.useTUI = useTUI && isatty(STDOUT_FILENO) == 1
        self.ignoresOwnership = ignoresOwnership
        self.encoder = JSONEncoder()
        self.encoder.outputFormatting = [.sortedKeys]
        keep = true
    }

    deinit {
        close(eventDescriptor)
        close(directoryDescriptor)
    }

    var isStopping: Bool {
        lock.withLock { stopping }
    }

    var hasActiveWrite: Bool {
        lock.withLock { writeActive }
    }

    func connect(_ activity: ClientActivity) {
        lock.withLock {
            activities[activity.connectionID] = activity
            appendEventLocked(level: "info", pid: activity.pid, command: nil, message: "client connected: \(activity.processPath)")
            scheduleRenderLocked()
        }
    }

    func setCommand(connectionID: String, command: String, state: String) {
        lock.withLock {
            guard var activity = activities[connectionID] else { return }
            activity.command = command
            activity.state = state
            activities[connectionID] = activity
            appendEventLocked(level: "info", pid: activity.pid, command: command, message: state)
            scheduleRenderLocked()
        }
    }

    func updateProgress(connectionID: String, completed: UInt64, total: UInt64) {
        guard lock.try() else { return }
        defer { lock.unlock() }
        guard var activity = activities[connectionID] else { return }
        let percent = total == 0 ? 0 : (Double(completed) / Double(total)) * 100
        activity.progress = String(format: "%.1f%% (%@ / %@)", percent, formatBytes(completed), formatBytes(total))
        activities[connectionID] = activity
        scheduleRenderLocked()
    }

    func finish(connectionID: String, ok: Bool, message: String) {
        lock.withLock {
            guard let activity = activities.removeValue(forKey: connectionID) else { return }
            verifiedWriteConnectionIDs.remove(connectionID)
            appendEventLocked(
                level: ok ? "ok" : "error",
                pid: activity.pid,
                command: activity.command.isEmpty ? nil : activity.command,
                message: message
            )
            scheduleRenderLocked()
        }
    }

    func requestStop(reason: String) {
        lock.withLock {
            guard !stopping else { return }
            stopping = true
            appendEventLocked(
                level: "warning",
                pid: nil,
                command: nil,
                message: writeActive
                    ? "\(reason); shutdown deferred until the write transaction is verified"
                    : (writeReserved ? "\(reason); staging will cancel before card write" : reason)
            )
            scheduleRenderLocked()
        }
    }

    func reserveWriteIfRunning(_ id: String) -> Bool {
        lock.withLock {
            guard !stopping,
                  !writeReserved,
                  !writeActive,
                  consumedWriteIDs.insert(id).inserted else {
                return false
            }
            writeReserved = true
            scheduleRenderLocked()
            return true
        }
    }

    func promoteReservedWriteIfRunning() -> Bool {
        lock.withLock {
            guard writeReserved, !stopping, !writeActive else { return false }
            writeActive = true
            scheduleRenderLocked()
            return true
        }
    }

    func finishWriteTransaction() {
        lock.withLock {
            writeActive = false
            writeReserved = false
            scheduleRenderLocked()
        }
    }

    func markWriteVerified(connectionID: String) {
        _ = lock.withLock {
            verifiedWriteConnectionIDs.insert(connectionID)
        }
    }

    func isWriteVerified(connectionID: String) -> Bool {
        lock.withLock { verifiedWriteConnectionIDs.contains(connectionID) }
    }

    func duplicateDirectoryDescriptor() throws -> Int32 {
        let result = dup(directoryDescriptor)
        guard result >= 0 else {
            throw R46HError.system("duplicate session directory FD: \(posixMessage())")
        }
        _ = fcntl(result, F_SETFD, FD_CLOEXEC)
        return result
    }

    func clientItems() -> [[String: String]] {
        lock.withLock {
            activities.values.sorted(by: { $0.connectedAt < $1.connectedAt }).map {
                [
                    "pid": String($0.pid),
                    "uid": String($0.uid),
                    "process": $0.processPath,
                    "command": $0.command.isEmpty ? "-" : $0.command,
                    "state": $0.state,
                    "progress": $0.progress.isEmpty ? "-" : $0.progress,
                ]
            }
        }
    }

    func record(level: String, message: String) {
        lock.withLock {
            appendEventLocked(level: level, pid: nil, command: nil, message: message)
            scheduleRenderLocked()
        }
    }

    func seal() {
        let clearTUI = lock.withLock {
            sealed = true
            return useTUI
        }
        eventQueue.sync {
            _ = fsync(eventDescriptor)
        }
        let prefix = clearTUI ? "\u{001B}[2J\u{001B}[H" : ""
        let line = "\(prefix)R46H Card Agent stopped. Session: \(sessionDirectory)\n"
        writeBestEffort(STDOUT_FILENO, data: Data(line.utf8))
    }

    func writeReceipt(name: String, object: [String: Any], ownerGID: gid_t) throws -> String {
        try Validation.validateOutputName(name)
        let data = try JSONSerialization.data(withJSONObject: object, options: [.prettyPrinted, .sortedKeys])
        let path = sessionDirectory + "/" + name
        let descriptor = openat(
            directoryDescriptor,
            name,
            O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW,
            0o600
        )
        guard descriptor >= 0 else {
            throw R46HError.system("create receipt: \(posixMessage())")
        }
        var keep = false
        defer {
            close(descriptor)
            if !keep { _ = unlinkat(directoryDescriptor, name, 0) }
        }
        try data.withUnsafeBytes { bytes in
            var offset = 0
            while offset < bytes.count {
                let result = Darwin.write(
                    descriptor,
                    bytes.baseAddress!.advanced(by: offset),
                    bytes.count - offset
                )
                if result < 0 {
                    if errno == EINTR { continue }
                    throw R46HError.system("write receipt: \(posixMessage())")
                }
                guard result > 0 else {
                    throw R46HError.system("write receipt made no progress")
                }
                offset += result
            }
        }
        if !ignoresOwnership, fchown(descriptor, ownerUID, ownerGID) != 0 {
            throw R46HError.system("chown receipt: \(posixMessage())")
        }
        guard fsync(descriptor) == 0 else {
            throw R46HError.system("seal receipt: \(posixMessage())")
        }
        keep = true
        return path
    }

    func createWriteStatus(operationID: String, object: [String: Any]) throws -> String {
        let name = "WRITE-STATUS-\(operationID).json"
        try Validation.validateOutputName(name)
        try writeRootStatus(name: name, object: object, replace: false)
        return sessionDirectory + "/" + name
    }

    func completeWriteStatus(operationID: String, object: [String: Any]) throws -> String {
        let name = "WRITE-STATUS-\(operationID).json"
        try Validation.validateOutputName(name)
        try writeRootStatus(name: name, object: object, replace: true)
        return sessionDirectory + "/" + name
    }

    private func appendEventLocked(level: String, pid: pid_t?, command: String?, message: String) {
        let event = SessionEvent(
            timestamp: ISO8601DateFormatter().string(from: Date()),
            level: level,
            pid: pid,
            command: command,
            message: message
        )
        recentEvents.append(event)
        if recentEvents.count > 14 { recentEvents.removeFirst(recentEvents.count - 14) }
        if let data = try? encoder.encode(event) {
            let shouldSynchronize = level == "error" || level == "warning" || level == "ok"
            var record = data
            record.append(10)
            eventQueue.async { [eventDescriptor] in
                writeBestEffort(eventDescriptor, data: record)
                if shouldSynchronize {
                    _ = fsync(eventDescriptor)
                }
            }
        }
        if !useTUI {
            let pidText = pid.map { " pid=\($0)" } ?? ""
            let commandText = command.map { " command=\($0)" } ?? ""
            let line = "[\(event.timestamp)] [\(level)]\(pidText)\(commandText) \(sanitized(message))\n"
            let data = Data(line.utf8)
            renderQueue.async {
                writeBestEffort(STDOUT_FILENO, data: data)
            }
        }
    }

    private func renderDataLocked() -> Data? {
        guard useTUI, !sealed else { return nil }
        var lines: [String] = [
            "\u{001B}[2J\u{001B}[H\u{001B}[1mR46H Card Agent\u{001B}[0m",
            "Session : \(sessionID)",
            "Mode    : \(mode.rawValue.uppercased())\(writeActive ? "  [WRITE IN PROGRESS - shutdown deferred]" : "")",
            "Socket  : \(socketPath)",
            "State   : \(stopping ? "stopping" : "running")",
            "",
            "Active clients",
            "PID      UID      STATE          COMMAND                 PROGRESS                PROCESS",
        ]
        let sorted = activities.values.sorted(by: { $0.connectedAt < $1.connectedAt })
        if sorted.isEmpty {
            lines.append("-        -        idle           -                       -                       -")
        } else {
            for item in sorted {
                lines.append(String(format: "%-8d %-8u %-14@ %-23@ %-23@ %@",
                                    Int32(item.pid),
                                    UInt32(item.uid),
                                    clipped(item.state, 14),
                                    clipped(item.command.isEmpty ? "-" : item.command, 23),
                                    clipped(item.progress.isEmpty ? "-" : item.progress, 23),
                                    sanitized(item.processPath)))
            }
        }
        lines.append("")
        lines.append("Recent events")
        for event in recentEvents {
            let time = event.timestamp.count >= 19
                ? String(event.timestamp.dropFirst(11).prefix(8))
                : event.timestamp
            let pid = event.pid.map { "pid=\($0) " } ?? ""
            let command = event.command.map { "\($0): " } ?? ""
            lines.append("\(time) [\(event.level)] \(pid)\(command)\(sanitized(event.message))")
        }
        lines.append("")
        lines.append(writeActive
            ? "Ctrl+C requests shutdown after the current write and readback proof finish."
            : "Press Ctrl+C at any time to stop; active read operations are cancelled safely.")
        return Data((lines.joined(separator: "\n") + "\n").utf8)
    }

    private func scheduleRenderLocked() {
        guard useTUI, !sealed, !renderScheduled else { return }
        renderScheduled = true
        renderQueue.asyncAfter(deadline: .now() + .milliseconds(100)) { [weak self] in
            guard let self else { return }
            let data = self.lock.withLock {
                self.renderScheduled = false
                return self.renderDataLocked()
            }
            if let data {
                writeBestEffort(STDOUT_FILENO, data: data)
            }
        }
    }

    private func clipped(_ value: String, _ length: Int) -> NSString {
        let clean = sanitized(value)
        if clean.count <= length { return clean as NSString }
        return (String(clean.prefix(max(1, length - 1))) + "…") as NSString
    }

    private func formatBytes(_ bytes: UInt64) -> String {
        let units = ["B", "KiB", "MiB", "GiB"]
        var value = Double(bytes)
        var index = 0
        while value >= 1024, index < units.count - 1 {
            value /= 1024
            index += 1
        }
        return String(format: index == 0 ? "%.0f %@" : "%.1f %@", value, units[index])
    }

    private func writeRootStatus(name: String, object: [String: Any], replace: Bool) throws {
        let data = try JSONSerialization.data(withJSONObject: object, options: [.prettyPrinted, .sortedKeys])
        let temporary = ".status-\(UUID().uuidString.lowercased())"
        let descriptor = openat(
            directoryDescriptor,
            temporary,
            O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW,
            0o444
        )
        guard descriptor >= 0 else {
            throw R46HError.system("create write status: \(posixMessage())")
        }
        var keepTemporary = true
        defer {
            close(descriptor)
            if keepTemporary { _ = unlinkat(directoryDescriptor, temporary, 0) }
        }
        try data.withUnsafeBytes { bytes in
            var offset = 0
            while offset < bytes.count {
                let result = Darwin.write(
                    descriptor,
                    bytes.baseAddress!.advanced(by: offset),
                    bytes.count - offset
                )
                if result < 0 {
                    if errno == EINTR { continue }
                    throw R46HError.system("write status: \(posixMessage())")
                }
                guard result > 0 else { throw R46HError.system("write status made no progress") }
                offset += result
            }
        }
        guard fchmod(descriptor, 0o444) == 0,
              fsync(descriptor) == 0 else {
            throw R46HError.system("seal write status: \(posixMessage())")
        }
        if !replace {
            var existing = stat()
            guard fstatat(directoryDescriptor, name, &existing, AT_SYMLINK_NOFOLLOW) != 0,
                  errno == ENOENT else {
                throw R46HError.unsafePath("write status already exists")
            }
        }
        guard renameat(directoryDescriptor, temporary, directoryDescriptor, name) == 0,
              fsync(directoryDescriptor) == 0 else {
            throw R46HError.system("publish write status: \(posixMessage())")
        }
        keepTemporary = false
    }

    private func sanitized(_ value: String) -> String {
        value.unicodeScalars.map { scalar in
            let code = scalar.value
            return (code < 0x20 || code == 0x7f || code == 0x1b) ? "?" : String(scalar)
        }.joined()
    }
}

private func writeBestEffort(_ descriptor: Int32, data: Data) {
    data.withUnsafeBytes { bytes in
        guard let baseAddress = bytes.baseAddress else { return }
        var offset = 0
        while offset < bytes.count {
            let result = Darwin.write(
                descriptor,
                baseAddress.advanced(by: offset),
                bytes.count - offset
            )
            if result < 0 {
                if errno == EINTR { continue }
                return
            }
            guard result > 0 else { return }
            offset += result
        }
    }
}

private extension NSLock {
    func withLock<T>(_ body: () throws -> T) rethrows -> T {
        lock()
        defer { unlock() }
        return try body()
    }
}
