import Darwin
import Foundation
import R46HCardCore

final class UnixServer {
    private let configuration: AgentConfiguration
    private let state: SessionState
    private let card: CardDevice
    private let writePlan: WritePlan?
    private let cardLock = NSLock()
    private let handlers = DispatchGroup()
    private let handlerQueue = DispatchQueue(label: "r46h-card-agent.clients", attributes: .concurrent)
    private var listenDescriptor: Int32 = -1
    private var lockDescriptor: Int32 = -1
    private var token = ""
    private var signalSources: [DispatchSourceSignal] = []

    init(
        configuration: AgentConfiguration,
        state: SessionState,
        card: CardDevice,
        writePlan: WritePlan?
    ) {
        self.configuration = configuration
        self.state = state
        self.card = card
        self.writePlan = writePlan
    }

    func run() throws {
        signal(SIGPIPE, SIG_IGN)
        try prepareEndpoint()
        installSignalHandlers()
        defer {
            handlers.wait()
            cleanEndpoint()
            signalSources.forEach { $0.cancel() }
        }

        state.record(
            level: "ok",
            message: "agent ready; connected processes and commands will appear here"
        )

        while !state.isStopping {
            var descriptor = pollfd(fd: listenDescriptor, events: Int16(POLLIN), revents: 0)
            let result = poll(&descriptor, 1, 500)
            if result < 0 {
                if errno == EINTR { continue }
                throw R46HError.system("poll control socket: \(posixMessage())")
            }
            if result == 0 { continue }
            if descriptor.revents & Int16(POLLIN) != 0 {
                let client = accept(listenDescriptor, nil, nil)
                if client < 0 {
                    if errno == EINTR { continue }
                    throw R46HError.system("accept control socket: \(posixMessage())")
                }
                configureClientSocket(client)
                handlers.enter()
                handlerQueue.async { [self] in
                    defer {
                        close(client)
                        handlers.leave()
                    }
                    handleClient(client)
                }
            }
        }

        handlers.wait()
    }

    private func handleClient(_ descriptor: Int32) {
        let connectionID = UUID().uuidString.lowercased()
        var requestID = "invalid"
        var command = ""
        var connected = false
        do {
            let peer = try peerIdentity(descriptor)
            guard peer.uid == configuration.ownerUID else {
                throw R46HError.unauthorized("peer UID does not match the invoking user")
            }
            state.connect(ClientActivity(
                connectionID: connectionID,
                pid: peer.pid,
                uid: peer.uid,
                processPath: peer.path,
                connectedAt: Date(),
                command: "",
                state: "connected",
                progress: ""
            ))
            connected = true

            let data = try Wire.readLine(from: descriptor)
            let request = try Wire.decodeRequest(data)
            requestID = request.id
            command = request.command
            guard constantTimeEqual(request.token, token) else {
                throw R46HError.unauthorized("session token mismatch")
            }
            state.setCommand(connectionID: connectionID, command: command, state: "running")
            let response = try dispatch(
                request,
                descriptor: descriptor,
                connectionID: connectionID
            )
            try Wire.write(response, to: descriptor)
            state.finish(connectionID: connectionID, ok: response.ok, message: response.message)
            connected = false
        } catch {
            let message = String(describing: error)
            let verifiedWrite = state.isWriteVerified(connectionID: connectionID)
            let response = AgentMessage(
                id: requestID,
                kind: "result",
                ok: verifiedWrite,
                message: verifiedWrite
                    ? "card write was fully verified, but result publication or delivery failed: \(message)"
                    : message
            )
            try? Wire.write(response, to: descriptor)
            if connected {
                if !command.isEmpty {
                    state.setCommand(
                        connectionID: connectionID,
                        command: command,
                        state: verifiedWrite ? "verified+warning" : "failed"
                    )
                }
                state.finish(
                    connectionID: connectionID,
                    ok: verifiedWrite,
                    message: verifiedWrite ? response.message : message
                )
            }
        }
    }

    private func dispatch(
        _ request: AgentRequest,
        descriptor: Int32,
        connectionID: String
    ) throws -> AgentMessage {
        switch request.command {
        case "help":
            try requireArguments(request, exactly: [])
            return AgentMessage(
                id: request.id,
                kind: "result",
                ok: true,
                message: "fixed command allowlist",
                items: commandHelp
            )
        case "status":
            try requireArguments(request, exactly: [])
            return AgentMessage(
                id: request.id,
                kind: "result",
                ok: true,
                message: "agent is \(state.isStopping ? "stopping" : "running")",
                details: [
                    "mode": configuration.mode.rawValue,
                    "device": configuration.device,
                    "session": state.sessionDirectory,
                    "write_active": state.hasActiveWrite ? "yes" : "no",
                ],
                items: state.clientItems()
            )
        case "clients":
            try requireArguments(request, exactly: [])
            return AgentMessage(
                id: request.id,
                kind: "result",
                ok: true,
                message: "connected clients",
                items: state.clientItems()
            )
        case "stop":
            try requireArguments(request, exactly: [])
            state.requestStop(reason: "stop requested by client")
            return AgentMessage(
                id: request.id,
                kind: "result",
                ok: true,
                message: state.hasActiveWrite
                    ? "shutdown requested; waiting for write and readback verification"
                    : "shutdown requested"
            )
        default:
            guard !state.isStopping else {
                throw R46HError.cancelled("agent is stopping")
            }
            return try withCardLock {
                try dispatchCardCommand(
                    request,
                    descriptor: descriptor,
                    connectionID: connectionID
                )
            }
        }
    }

    private func dispatchCardCommand(
        _ request: AgentRequest,
        descriptor: Int32,
        connectionID: String
    ) throws -> AgentMessage {
        switch request.command {
        case "card-info":
            try requireArguments(request, exactly: [])
            let snapshot = try card.snapshot(cancelled: { self.state.isStopping })
            return AgentMessage(
                id: request.id,
                kind: "result",
                ok: true,
                message: "card identity verified",
                details: [
                    "prefix_sha256": snapshot.prefixSHA256,
                    "all_unmounted": snapshot.allUnmounted ? "yes" : "no",
                ],
                items: snapshot.summaryItems
            )
        case "unmount":
            try requireArguments(request, exactly: [])
            let snapshot = try card.unmount(cancelled: { self.state.isStopping })
            return AgentMessage(
                id: request.id,
                kind: "result",
                ok: true,
                message: "card identity verified and all partitions unmounted",
                details: ["prefix_sha256": snapshot.prefixSHA256]
            )
        case "mount-readonly":
            try requireArguments(request, exactly: ["volume"])
            guard let raw = request.arguments["volume"], let volume = VolumeTarget(rawValue: raw) else {
                throw R46HError.invalidArgument("volume must be boot or easyroms")
            }
            let snapshot = try card.mountReadOnly(
                volume,
                cancelled: { self.state.isStopping }
            )
            let info = volume == .boot ? snapshot.boot : snapshot.easyroms
            return AgentMessage(
                id: request.id,
                kind: "result",
                ok: true,
                message: "\(volume.rawValue) mounted read-only",
                details: ["mount_point": info["Mount Point"] ?? "unknown"]
            )
        case "hash-raw":
            try requireArguments(request, exactly: ["target"])
            guard let raw = request.arguments["target"], let target = CardTarget(rawValue: raw) else {
                throw R46HError.invalidArgument("target must be prefix, boot, root, or easyroms")
            }
            let result = try card.hashRaw(
                target: target,
                progress: progressSender(
                    requestID: request.id,
                    descriptor: descriptor,
                    connectionID: connectionID,
                    writeTransaction: false
                ),
                cancelled: { self.state.isStopping }
            )
            return AgentMessage(
                id: request.id,
                kind: "result",
                ok: true,
                message: "raw SHA-256 complete",
                details: ["target": target.rawValue, "bytes": String(result.bytes), "sha256": result.sha256]
            )
        case "clone":
            try requireArguments(request, required: ["target", "name"], optional: ["offset", "length"])
            guard let raw = request.arguments["target"], let target = CardTarget(rawValue: raw),
                  let name = request.arguments["name"] else {
                throw R46HError.invalidArgument("clone requires a valid target and name")
            }
            let offset = try optionalUInt64(request.arguments["offset"], name: "offset")
            let length = try optionalUInt64(request.arguments["length"], name: "length")
            let result = try card.cloneRaw(
                target: target,
                outputName: name,
                offset: offset,
                length: length,
                progress: progressSender(
                    requestID: request.id,
                    descriptor: descriptor,
                    connectionID: connectionID,
                    writeTransaction: false
                ),
                cancelled: { self.state.isStopping }
            )
            return AgentMessage(
                id: request.id,
                kind: "result",
                ok: true,
                message: "raw clone complete",
                details: ["path": result.path, "bytes": String(result.bytes), "sha256": result.sha256]
            )
        case "hash-file":
            try requireArguments(request, exactly: ["volume", "path"])
            let (volume, path) = try volumeAndPath(request)
            let result = try card.hashVolumeFile(
                volume: volume,
                relativePath: path,
                progress: progressSender(
                    requestID: request.id,
                    descriptor: descriptor,
                    connectionID: connectionID,
                    writeTransaction: false
                ),
                cancelled: { self.state.isStopping }
            )
            return AgentMessage(
                id: request.id,
                kind: "result",
                ok: true,
                message: "volume file SHA-256 complete",
                details: ["volume": volume.rawValue, "path": path, "bytes": String(result.1), "sha256": result.0]
            )
        case "list-dir":
            try requireArguments(request, exactly: ["volume", "path"])
            let (volume, path) = try volumeAndPath(request)
            let items = try card.listVolumeDirectory(
                volume: volume,
                relativePath: path,
                cancelled: { self.state.isStopping }
            )
            return AgentMessage(
                id: request.id,
                kind: "result",
                ok: true,
                message: "volume directory listed",
                details: ["volume": volume.rawValue, "path": path],
                items: items
            )
        case "fsck-exfat":
            try requireArguments(request, exactly: [])
            let result = try card.fsckExFATReadOnly(cancelled: { self.state.isStopping })
            return AgentMessage(
                id: request.id,
                kind: "result",
                ok: true,
                message: "read-only exFAT check complete",
                details: ["exit_status": String(result.0), "log": result.1]
            )
        case "execute-write":
            try requireArguments(request, exactly: ["operation_id"])
            return try executeWrite(request, descriptor: descriptor, connectionID: connectionID)
        default:
            throw R46HError.invalidArgument("command is not in the fixed allowlist")
        }
    }

    private func executeWrite(
        _ request: AgentRequest,
        descriptor: Int32,
        connectionID: String
    ) throws -> AgentMessage {
        guard configuration.mode == .deploy, let writePlan else {
            throw R46HError.unauthorized("agent is running in audit mode")
        }
        guard let operationID = request.arguments["operation_id"],
              let operation = writePlan.operations.first(where: { $0.id == operationID }) else {
            throw R46HError.invalidArgument("operation_id is not present in the pinned write plan")
        }
        guard state.reserveWriteIfRunning(operationID) else {
            throw R46HError.unauthorized("agent is stopping, another write is active, or this operation was already attempted")
        }

        state.setCommand(connectionID: connectionID, command: request.command, state: "staging+hashing")
        defer { state.finishWriteTransaction() }
        let started = ISO8601DateFormatter().string(from: Date())
        var statusPath = ""
        let details = try card.executeWrite(
            operation: operation,
            inputRoot: configuration.inputRoot,
            stagingProgress: progressSender(
                requestID: request.id,
                descriptor: descriptor,
                connectionID: connectionID,
                writeTransaction: true
            ),
            writeProgress: { completed, total in
                self.state.updateProgress(connectionID: connectionID, completed: completed, total: total)
            },
            cancelled: { self.state.isStopping },
            writeStarted: {
                guard self.state.promoteReservedWriteIfRunning() else {
                    throw R46HError.cancelled("write cancelled before the card was modified")
                }
                statusPath = try self.state.createWriteStatus(
                    operationID: operation.id,
                    object: [
                        "format_version": 1,
                        "state": "WRITE_IN_PROGRESS",
                        "safe_to_boot": "no",
                        "device": self.configuration.device,
                        "profile_id": self.card.profile.profileID,
                        "operation_id": operation.id,
                        "partition": operation.partition.rawValue,
                        "source_sha256": operation.sourceSHA256,
                        "target_sha256_before": operation.targetSHA256Before,
                        "started_at": started,
                    ]
                )
                self.state.setCommand(
                    connectionID: connectionID,
                    command: request.command,
                    state: "writing+verifying"
                )
            }
        )
        let finished = ISO8601DateFormatter().string(from: Date())
        state.markWriteVerified(connectionID: connectionID)
        state.record(
            level: "ok",
            message: "write \(operation.id) fully read back and verified; publishing completion evidence"
        )
        statusPath = try state.completeWriteStatus(
            operationID: operation.id,
            object: [
                "format_version": 1,
                "state": "WRITE_COMPLETE",
                "safe_to_boot": "yes",
                "device": configuration.device,
                "profile_id": card.profile.profileID,
                "operation_id": operation.id,
                "partition": operation.partition.rawValue,
                "started_at": started,
                "finished_at": finished,
                "proof": details,
            ]
        )
        let receiptName = "write-\(operation.id)-receipt.json"
        let receipt = try state.writeReceipt(
            name: receiptName,
            object: [
                "format_version": 1,
                "profile_id": card.profile.profileID,
                "device": configuration.device,
                "mode": configuration.mode.rawValue,
                "started_at": started,
                "finished_at": finished,
                "operation": [
                    "id": operation.id,
                    "description": operation.description,
                    "partition": operation.partition.rawValue,
                    "source_path": operation.sourcePath,
                    "source_size": operation.sourceSize,
                    "source_sha256": operation.sourceSHA256,
                    "target_sha256_before": operation.targetSHA256Before,
                ],
                "proof": details,
            ],
            ownerGID: configuration.ownerGID
        )
        var responseDetails = details
        responseDetails["receipt"] = receipt
        responseDetails["write_status"] = statusPath
        return AgentMessage(
            id: request.id,
            kind: "result",
            ok: true,
            message: "partition write and full readback verification complete",
            details: responseDetails
        )
    }

    private func progressSender(
        requestID: String,
        descriptor: Int32,
        connectionID: String,
        writeTransaction: Bool
    ) -> CardDevice.Progress {
        var lastBytes: UInt64 = 0
        var lastTime = Date.distantPast
        return { completed, total in
            self.state.updateProgress(connectionID: connectionID, completed: completed, total: total)
            let now = Date()
            guard completed == total || completed - lastBytes >= 64 * 1024 * 1024 || now.timeIntervalSince(lastTime) >= 1 else {
                return
            }
            lastBytes = completed
            lastTime = now
            let message = AgentMessage(
                id: requestID,
                kind: "progress",
                ok: true,
                message: "operation in progress",
                details: ["completed": String(completed), "total": String(total)]
            )
            do {
                if writeTransaction, self.state.hasActiveWrite { return }
                try Wire.write(message, to: descriptor)
            } catch {
                if !self.state.hasActiveWrite {
                    throw R46HError.cancelled("client disconnected during read operation")
                }
            }
        }
    }

    private func withCardLock<T>(_ body: () throws -> T) throws -> T {
        guard cardLock.try() else {
            throw R46HError.invalidData("another card operation is active")
        }
        defer { cardLock.unlock() }
        return try body()
    }

    private func requireArguments(_ request: AgentRequest, exactly keys: Set<String>) throws {
        guard Set(request.arguments.keys) == keys else {
            throw R46HError.invalidArgument("unexpected or missing command arguments")
        }
    }

    private func requireArguments(
        _ request: AgentRequest,
        required: Set<String>,
        optional: Set<String>
    ) throws {
        let keys = Set(request.arguments.keys)
        guard required.isSubset(of: keys), keys.isSubset(of: required.union(optional)) else {
            throw R46HError.invalidArgument("unexpected or missing command arguments")
        }
    }

    private func volumeAndPath(_ request: AgentRequest) throws -> (VolumeTarget, String) {
        guard let raw = request.arguments["volume"], let volume = VolumeTarget(rawValue: raw),
              let path = request.arguments["path"] else {
            throw R46HError.invalidArgument("volume must be boot or easyroms and path is required")
        }
        return (volume, path)
    }

    private func optionalUInt64(_ value: String?, name: String) throws -> UInt64? {
        guard let value else { return nil }
        guard !value.isEmpty, value.allSatisfy(\.isNumber), let number = UInt64(value) else {
            throw R46HError.invalidArgument("\(name) must be an unsigned decimal integer")
        }
        return number
    }

    private func prepareEndpoint() throws {
        let directory = (state.socketPath as NSString).deletingLastPathComponent
        if mkdir(directory, 0o711) != 0, errno != EEXIST {
            throw R46HError.system("mkdir control directory: \(posixMessage())")
        }
        var directoryStatus = stat()
        guard lstat(directory, &directoryStatus) == 0,
              (directoryStatus.st_mode & S_IFMT) == S_IFDIR,
              directoryStatus.st_uid == 0,
              (directoryStatus.st_mode & 0o022) == 0 else {
            throw R46HError.unsafePath("control directory identity or permissions are unsafe")
        }
        guard chmod(directory, 0o711) == 0 else {
            throw R46HError.system("chmod control directory: \(posixMessage())")
        }

        try acquireInstanceLock(directory: directory)
        try removeStaleEndpointIfNeeded()
        token = randomToken()
        try createTokenFile()
        do {
            listenDescriptor = try createListeningSocket()
        } catch {
            unlink(state.tokenPath)
            throw error
        }
    }

    private func createListeningSocket() throws -> Int32 {
        let descriptor = Darwin.socket(AF_UNIX, SOCK_STREAM, 0)
        guard descriptor >= 0 else {
            throw R46HError.system("create control socket: \(posixMessage())")
        }
        var keep = false
        defer { if !keep { close(descriptor) } }
        setCloseOnExec(descriptor)
        var one: Int32 = 1
        _ = setsockopt(descriptor, SOL_SOCKET, SO_NOSIGPIPE, &one, socklen_t(MemoryLayout.size(ofValue: one)))
        let result = try withUnixAddress(path: state.socketPath) { address, length in
            bind(descriptor, address, length)
        }
        guard result == 0 else {
            throw R46HError.system("bind control socket: \(posixMessage())")
        }
        guard chown(state.socketPath, configuration.ownerUID, configuration.ownerGID) == 0,
              chmod(state.socketPath, 0o600) == 0 else {
            unlink(state.socketPath)
            throw R46HError.system("secure control socket: \(posixMessage())")
        }
        guard listen(descriptor, 16) == 0 else {
            unlink(state.socketPath)
            throw R46HError.system("listen control socket: \(posixMessage())")
        }
        keep = true
        return descriptor
    }

    private func removeStaleEndpointIfNeeded() throws {
        var status = stat()
        if lstat(state.socketPath, &status) == 0 {
            guard (status.st_mode & S_IFMT) == S_IFSOCK,
                  status.st_uid == configuration.ownerUID else {
                throw R46HError.unsafePath("existing control socket has an unsafe identity")
            }
            let probe = Darwin.socket(AF_UNIX, SOCK_STREAM, 0)
            guard probe >= 0 else {
                throw R46HError.system("create stale-socket probe: \(posixMessage())")
            }
            defer { close(probe) }
            let connected = try withUnixAddress(path: state.socketPath) { address, length in
                connect(probe, address, length)
            }
            if connected == 0 {
                throw R46HError.invalidData("another R46H Card Agent is already running")
            }
            guard errno == ECONNREFUSED || errno == ENOENT else {
                throw R46HError.system("probe existing control socket: \(posixMessage())")
            }
            guard unlink(state.socketPath) == 0 else {
                throw R46HError.system("remove stale control socket: \(posixMessage())")
            }
        } else if errno != ENOENT {
            throw R46HError.system("inspect control socket: \(posixMessage())")
        }

        if lstat(state.tokenPath, &status) == 0 {
            guard (status.st_mode & S_IFMT) == S_IFREG,
                  status.st_uid == configuration.ownerUID else {
                throw R46HError.unsafePath("existing token file has an unsafe identity")
            }
            guard unlink(state.tokenPath) == 0 else {
                throw R46HError.system("remove stale token file: \(posixMessage())")
            }
        } else if errno != ENOENT {
            throw R46HError.system("inspect token file: \(posixMessage())")
        }
    }

    private func createTokenFile() throws {
        let descriptor = open(
            state.tokenPath,
            O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW,
            0o600
        )
        guard descriptor >= 0 else {
            throw R46HError.system("create token file: \(posixMessage())")
        }
        var keep = false
        defer {
            close(descriptor)
            if !keep { unlink(state.tokenPath) }
        }
        let data = Data((token + "\n").utf8)
        try data.withUnsafeBytes { bytes in
            var offset = 0
            while offset < bytes.count {
                let result = Darwin.write(descriptor, bytes.baseAddress!.advanced(by: offset), bytes.count - offset)
                if result < 0 {
                    if errno == EINTR { continue }
                    throw R46HError.system("write token file: \(posixMessage())")
                }
                guard result > 0 else { throw R46HError.system("write token made no progress") }
                offset += result
            }
        }
        guard fchown(descriptor, configuration.ownerUID, configuration.ownerGID) == 0,
              fchmod(descriptor, 0o600) == 0,
              fsync(descriptor) == 0 else {
            throw R46HError.system("secure token file: \(posixMessage())")
        }
        keep = true
    }

    private func cleanEndpoint() {
        if listenDescriptor >= 0 {
            close(listenDescriptor)
            listenDescriptor = -1
        }
        unlink(state.socketPath)
        unlink(state.tokenPath)
        if lockDescriptor >= 0 {
            _ = flock(lockDescriptor, LOCK_UN)
            close(lockDescriptor)
            lockDescriptor = -1
        }
    }

    private func configureClientSocket(_ descriptor: Int32) {
        setCloseOnExec(descriptor)
        var timeout = timeval(tv_sec: 5, tv_usec: 0)
        _ = setsockopt(descriptor, SOL_SOCKET, SO_RCVTIMEO, &timeout, socklen_t(MemoryLayout.size(ofValue: timeout)))
        _ = setsockopt(descriptor, SOL_SOCKET, SO_SNDTIMEO, &timeout, socklen_t(MemoryLayout.size(ofValue: timeout)))
        var one: Int32 = 1
        _ = setsockopt(descriptor, SOL_SOCKET, SO_NOSIGPIPE, &one, socklen_t(MemoryLayout.size(ofValue: one)))
    }

    private func acquireInstanceLock(directory: String) throws {
        let path = directory + "/agent.lock"
        let descriptor = open(path, O_RDWR | O_CREAT | O_CLOEXEC | O_NOFOLLOW, 0o600)
        guard descriptor >= 0 else {
            throw R46HError.system("open instance lock: \(posixMessage())")
        }
        var status = stat()
        guard fstat(descriptor, &status) == 0,
              (status.st_mode & S_IFMT) == S_IFREG,
              status.st_uid == 0,
              (status.st_mode & 0o077) == 0 else {
            close(descriptor)
            throw R46HError.unsafePath("instance lock identity or permissions are unsafe")
        }
        guard fchmod(descriptor, 0o600) == 0 else {
            close(descriptor)
            throw R46HError.system("secure instance lock: \(posixMessage())")
        }
        guard flock(descriptor, LOCK_EX | LOCK_NB) == 0 else {
            let code = errno
            close(descriptor)
            if code == EWOULDBLOCK {
                throw R46HError.invalidData("another R46H Card Agent is already running")
            }
            throw R46HError.system("lock agent instance: \(posixMessage(code))")
        }
        lockDescriptor = descriptor
    }

    private func installSignalHandlers() {
        for number in [SIGINT, SIGTERM, SIGHUP] {
            signal(number, SIG_IGN)
            let source = DispatchSource.makeSignalSource(signal: number, queue: .global(qos: .userInitiated))
            source.setEventHandler { [state] in
                state.requestStop(reason: "signal \(number) received")
            }
            source.resume()
            signalSources.append(source)
        }
    }

    private func peerIdentity(_ descriptor: Int32) throws -> (uid: uid_t, pid: pid_t, path: String) {
        var uid = uid_t.max
        var gid = gid_t.max
        guard getpeereid(descriptor, &uid, &gid) == 0 else {
            throw R46HError.system("getpeereid: \(posixMessage())")
        }
        var pid: pid_t = 0
        var length = socklen_t(MemoryLayout.size(ofValue: pid))
        guard getsockopt(descriptor, SOL_LOCAL, LOCAL_PEERPID, &pid, &length) == 0,
              pid > 0 else {
            throw R46HError.system("read peer PID: \(posixMessage())")
        }
        var buffer = [CChar](repeating: 0, count: 4 * Int(MAXPATHLEN))
        let count = proc_pidpath(pid, &buffer, UInt32(buffer.count))
        let path = count > 0 ? String(cString: buffer) : "<unavailable>"
        return (uid, pid, path)
    }

    private func randomToken() -> String {
        var bytes = [UInt8](repeating: 0, count: 32)
        bytes.withUnsafeMutableBytes { arc4random_buf($0.baseAddress, $0.count) }
        return bytes.map { String(format: "%02x", $0) }.joined()
    }

    private func setCloseOnExec(_ descriptor: Int32) {
        _ = fcntl(descriptor, F_SETFD, FD_CLOEXEC)
    }

    private func withUnixAddress<T>(
        path: String,
        _ body: (UnsafePointer<sockaddr>, socklen_t) throws -> T
    ) throws -> T {
        let bytes = Array(path.utf8)
        var address = sockaddr_un()
        let capacity = MemoryLayout.size(ofValue: address.sun_path)
        guard bytes.count + 1 <= capacity else {
            throw R46HError.invalidArgument("control socket path is too long")
        }
        address.sun_family = sa_family_t(AF_UNIX)
        address.sun_len = UInt8(MemoryLayout<sockaddr_un>.size)
        withUnsafeMutableBytes(of: &address.sun_path) { destination in
            destination.initializeMemory(as: UInt8.self, repeating: 0)
            destination.copyBytes(from: bytes)
        }
        return try withUnsafePointer(to: &address) { pointer in
            try pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) {
                try body($0, socklen_t(MemoryLayout<sockaddr_un>.size))
            }
        }
    }

    private func constantTimeEqual(_ lhs: String, _ rhs: String) -> Bool {
        let left = Array(lhs.utf8)
        let right = Array(rhs.utf8)
        guard left.count == right.count else { return false }
        var difference: UInt8 = 0
        for index in left.indices { difference |= left[index] ^ right[index] }
        return difference == 0
    }

    private var commandHelp: [[String: String]] {
        [
            ["command": "status", "arguments": "-", "effect": "agent/session status"],
            ["command": "clients", "arguments": "-", "effect": "connected PID/UID/process/command"],
            ["command": "card-info", "arguments": "-", "effect": "verify card and report mount state"],
            ["command": "unmount", "arguments": "-", "effect": "verify then unmount all card partitions"],
            ["command": "mount-readonly", "arguments": "volume=boot|easyroms", "effect": "read-only mount"],
            ["command": "hash-raw", "arguments": "target=prefix|boot|root|easyroms", "effect": "raw SHA-256"],
            ["command": "clone", "arguments": "target,name[,offset,length]", "effect": "clone into this session directory"],
            ["command": "hash-file", "arguments": "volume,path", "effect": "hash a regular file on a read-only mount"],
            ["command": "list-dir", "arguments": "volume,path", "effect": "list a directory on a read-only mount"],
            ["command": "fsck-exfat", "arguments": "-", "effect": "read-only EASYROMS check"],
            ["command": "execute-write", "arguments": "operation_id", "effect": "deploy mode: run one pinned full-partition write"],
            ["command": "stop", "arguments": "-", "effect": "stop agent safely"],
        ]
    }
}
