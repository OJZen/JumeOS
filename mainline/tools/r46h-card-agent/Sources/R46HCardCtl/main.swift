import Darwin
import Foundation
import R46HCardCore

struct ClientArguments {
    let command: String
    let arguments: [String: String]
    let json: Bool

    static func parse(_ rawArguments: [String]) throws -> ClientArguments {
        var values = rawArguments
        let json = values.firstIndex(of: "--json").map { values.remove(at: $0); return true } ?? false
        guard let command = values.first else {
            throw R46HError.invalidArgument(usage)
        }
        let positionals = Array(values.dropFirst())
        let arguments: [String: String]
        switch command {
        case "help", "status", "clients", "card-info", "unmount", "fsck-exfat", "stop":
            guard positionals.isEmpty else { throw R46HError.invalidArgument("\(command) takes no arguments") }
            arguments = [:]
        case "mount-readonly":
            guard positionals.count == 1 else { throw R46HError.invalidArgument("mount-readonly requires VOLUME") }
            arguments = ["volume": positionals[0]]
        case "hash-raw":
            guard positionals.count == 1 else { throw R46HError.invalidArgument("hash-raw requires TARGET") }
            arguments = ["target": positionals[0]]
        case "clone":
            guard (2...4).contains(positionals.count) else {
                throw R46HError.invalidArgument("clone requires TARGET NAME [OFFSET LENGTH]")
            }
            var parsed = ["target": positionals[0], "name": positionals[1]]
            if positionals.count >= 3 { parsed["offset"] = positionals[2] }
            if positionals.count == 4 { parsed["length"] = positionals[3] }
            arguments = parsed
        case "hash-file", "list-dir":
            guard positionals.count == 2 else {
                throw R46HError.invalidArgument("\(command) requires VOLUME RELATIVE_PATH")
            }
            arguments = ["volume": positionals[0], "path": positionals[1]]
        case "execute-write":
            guard positionals.count == 1 else { throw R46HError.invalidArgument("execute-write requires OPERATION_ID") }
            arguments = ["operation_id": positionals[0]]
        default:
            throw R46HError.invalidArgument("unknown command: \(command)")
        }
        return ClientArguments(command: command, arguments: arguments, json: json)
    }

    static let usage = """
    usage: r46h-cardctl [--json] COMMAND [ARGUMENTS]

      help
      status | clients | card-info | unmount | fsck-exfat | stop
      mount-readonly boot|easyroms
      hash-raw prefix|boot|root|easyroms
      clone TARGET NAME [OFFSET LENGTH]
      hash-file VOLUME RELATIVE_PATH
      list-dir VOLUME RELATIVE_PATH
      execute-write OPERATION_ID
    """
}

func secureToken(path: String, ownerUID: uid_t) throws -> String {
    let descriptor = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW)
    guard descriptor >= 0 else {
        throw R46HError.system("open agent token: \(posixMessage())")
    }
    defer { close(descriptor) }
    var status = stat()
    guard fstat(descriptor, &status) == 0,
          (status.st_mode & S_IFMT) == S_IFREG,
          status.st_uid == ownerUID,
          (status.st_mode & 0o077) == 0,
          status.st_size > 0,
          status.st_size <= 128 else {
        throw R46HError.unsafePath("agent token identity or permissions are unsafe")
    }
    let data = try Wire.readLine(from: descriptor)
    let token = String(decoding: data, as: UTF8.self)
    guard isSHA256(token) else { throw R46HError.invalidData("agent token is malformed") }
    return token
}

func validateControlDirectory(_ path: String) throws {
    var directory = stat()
    guard lstat(path, &directory) == 0,
          (directory.st_mode & S_IFMT) == S_IFDIR,
          directory.st_uid == 0,
          (directory.st_mode & 0o022) == 0 else {
        throw R46HError.unsafePath("agent control directory is not root-owned and protected")
    }
    var lock = stat()
    guard lstat(path + "/agent.lock", &lock) == 0,
          (lock.st_mode & S_IFMT) == S_IFREG,
          lock.st_uid == 0,
          (lock.st_mode & 0o077) == 0 else {
        throw R46HError.unsafePath("agent instance lock identity or permissions are unsafe")
    }
}

func connectToAgent(path: String, ownerUID: uid_t) throws -> Int32 {
    var status = stat()
    guard lstat(path, &status) == 0,
          (status.st_mode & S_IFMT) == S_IFSOCK,
          status.st_uid == ownerUID,
          (status.st_mode & 0o077) == 0 else {
        throw R46HError.unsafePath("agent socket identity or permissions are unsafe")
    }
    let descriptor = Darwin.socket(AF_UNIX, SOCK_STREAM, 0)
    guard descriptor >= 0 else { throw R46HError.system("create client socket: \(posixMessage())") }
    var keep = false
    defer { if !keep { close(descriptor) } }
    _ = fcntl(descriptor, F_SETFD, FD_CLOEXEC)
    var one: Int32 = 1
    _ = setsockopt(descriptor, SOL_SOCKET, SO_NOSIGPIPE, &one, socklen_t(MemoryLayout.size(ofValue: one)))
    let result = try withUnixAddress(path: path) { address, length in
        Darwin.connect(descriptor, address, length)
    }
    guard result == 0 else { throw R46HError.system("connect to agent: \(posixMessage())") }
    keep = true
    return descriptor
}

func withUnixAddress<T>(
    path: String,
    _ body: (UnsafePointer<sockaddr>, socklen_t) throws -> T
) throws -> T {
    let bytes = Array(path.utf8)
    var address = sockaddr_un()
    let capacity = MemoryLayout.size(ofValue: address.sun_path)
    guard bytes.count + 1 <= capacity else { throw R46HError.invalidArgument("agent socket path is too long") }
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

func printMessage(_ message: AgentMessage, json: Bool) throws {
    if json {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        let data = try encoder.encode(message)
        print(String(decoding: data, as: UTF8.self))
        return
    }
    if message.kind == "progress" {
        let completed = UInt64(message.details["completed"] ?? "") ?? 0
        let total = UInt64(message.details["total"] ?? "") ?? 0
        let percent = total == 0 ? 0 : Double(completed) / Double(total) * 100
        print(String(format: "progress: %5.1f%% (%llu/%llu bytes)", percent, completed, total))
        return
    }
    print(message.ok ? "PASS: \(message.message)" : "ERROR: \(message.message)")
    for key in message.details.keys.sorted() {
        print("\(key)=\(message.details[key]!)")
    }
    for item in message.items {
        print(item.keys.sorted().map { "\($0)=\(item[$0]!)" }.joined(separator: "  "))
    }
}

do {
    signal(SIGPIPE, SIG_IGN)
    let rawArguments = Array(CommandLine.arguments.dropFirst())
    if rawArguments == ["--help"] || rawArguments == ["-h"] {
        print(ClientArguments.usage)
        exit(EXIT_SUCCESS)
    }
    let parsed = try ClientArguments.parse(rawArguments)
    let uid = geteuid()
    guard uid > 0 else { throw R46HError.unauthorized("r46h-cardctl must run as the invoking user, not root") }
    let directory = "/private/tmp/r46h-card-agent-\(uid)"
    try validateControlDirectory(directory)
    let token = try secureToken(path: directory + "/token", ownerUID: uid)
    let descriptor = try connectToAgent(path: directory + "/control.sock", ownerUID: uid)
    defer { close(descriptor) }
    let request = AgentRequest(token: token, command: parsed.command, arguments: parsed.arguments)
    try Wire.write(request, to: descriptor)
    while true {
        let message = try Wire.decodeMessage(Wire.readLine(from: descriptor))
        guard message.version == AgentRequest.currentVersion, message.id == request.id else {
            throw R46HError.invalidData("agent response does not match this request")
        }
        try printMessage(message, json: parsed.json)
        if message.kind == "result" {
            exit(message.ok ? EXIT_SUCCESS : EXIT_FAILURE)
        }
    }
} catch {
    fputs("ERROR: \(error)\n", stderr)
    fputs(ClientArguments.usage + "\n", stderr)
    exit(EX_USAGE)
}
