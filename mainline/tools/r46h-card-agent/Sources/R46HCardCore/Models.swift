import Foundation

public enum AgentMode: String, Codable, CaseIterable, Sendable {
    case audit
    case deploy
}

public enum CardTarget: String, Codable, CaseIterable, Sendable {
    case prefix
    case boot
    case root
    case easyroms

    public var partitionNumber: Int? {
        switch self {
        case .prefix: return nil
        case .boot: return 1
        case .root: return 2
        case .easyroms: return 3
        }
    }
}

public enum VolumeTarget: String, Codable, CaseIterable, Sendable {
    case boot
    case easyroms
}

public struct AgentRequest: Codable, Equatable, Sendable {
    public static let currentVersion = 1

    public let version: Int
    public let id: String
    public let token: String
    public let command: String
    public let arguments: [String: String]

    public init(
        version: Int = AgentRequest.currentVersion,
        id: String = UUID().uuidString.lowercased(),
        token: String,
        command: String,
        arguments: [String: String] = [:]
    ) {
        self.version = version
        self.id = id
        self.token = token
        self.command = command
        self.arguments = arguments
    }
}

public struct AgentMessage: Codable, Equatable, Sendable {
    public let version: Int
    public let id: String
    public let kind: String
    public let ok: Bool
    public let message: String
    public let details: [String: String]
    public let items: [[String: String]]

    public init(
        id: String,
        kind: String,
        ok: Bool,
        message: String,
        details: [String: String] = [:],
        items: [[String: String]] = []
    ) {
        self.version = AgentRequest.currentVersion
        self.id = id
        self.kind = kind
        self.ok = ok
        self.message = message
        self.details = details
        self.items = items
    }
}

public struct CardProfile: Codable, Equatable, Sendable {
    public let formatVersion: Int
    public let profileID: String
    public let target: String
    public let card: Card

    enum CodingKeys: String, CodingKey {
        case formatVersion = "format_version"
        case profileID = "profile_id"
        case target
        case card
    }

    public struct Card: Codable, Equatable, Sendable {
        public let wholeSize: UInt64
        public let sectorSize: UInt64
        public let partitionScheme: String
        public let boot: Partition
        public let root: Partition
        public let easyroms: Partition
        public let g92PrefixSize: UInt64
        public let g92PrefixSHA256: String

        enum CodingKeys: String, CodingKey {
            case wholeSize = "whole_size"
            case sectorSize = "sector_size"
            case partitionScheme = "partition_scheme"
            case boot
            case root
            case easyroms
            case g92PrefixSize = "g92_prefix_size"
            case g92PrefixSHA256 = "g92_prefix_sha256"
        }
    }

    public struct Partition: Codable, Equatable, Sendable {
        public let number: Int
        public let offset: UInt64
        public let size: UInt64
        public let volumeUUID: String?
        public let partUUID: String?

        enum CodingKeys: String, CodingKey {
            case number
            case offset
            case size
            case volumeUUID = "volume_uuid"
            case partUUID = "partuuid"
        }
    }

    public func partition(for target: CardTarget) -> Partition? {
        switch target {
        case .prefix: return nil
        case .boot: return card.boot
        case .root: return card.root
        case .easyroms: return card.easyroms
        }
    }
}

public struct WritePlan: Codable, Equatable, Sendable {
    public let formatVersion: Int
    public let profileID: String
    public let device: String
    public let operations: [Operation]

    enum CodingKeys: String, CodingKey {
        case formatVersion = "format_version"
        case profileID = "profile_id"
        case device
        case operations
    }

    public struct Operation: Codable, Equatable, Sendable {
        public let id: String
        public let description: String
        public let partition: CardTarget
        public let sourcePath: String
        public let sourceSize: UInt64
        public let sourceSHA256: String
        public let targetSHA256Before: String

        enum CodingKeys: String, CodingKey {
            case id
            case description
            case partition
            case sourcePath = "source_path"
            case sourceSize = "source_size"
            case sourceSHA256 = "source_sha256"
            case targetSHA256Before = "target_sha256_before"
        }
    }
}

public struct AgentConfiguration: Equatable, Sendable {
    public let mode: AgentMode
    public let ownerUID: uid_t
    public let ownerGID: gid_t
    public let device: String
    public let profilePath: String
    public let profileSHA256: String
    public let outputRoot: String
    public let inputRoot: String
    public let writePlanPath: String?
    public let writePlanSHA256: String?
    public let useTUI: Bool

    public init(
        mode: AgentMode,
        ownerUID: uid_t,
        ownerGID: gid_t,
        device: String,
        profilePath: String,
        profileSHA256: String,
        outputRoot: String,
        inputRoot: String,
        writePlanPath: String?,
        writePlanSHA256: String?,
        useTUI: Bool
    ) {
        self.mode = mode
        self.ownerUID = ownerUID
        self.ownerGID = ownerGID
        self.device = device
        self.profilePath = profilePath
        self.profileSHA256 = profileSHA256
        self.outputRoot = outputRoot
        self.inputRoot = inputRoot
        self.writePlanPath = writePlanPath
        self.writePlanSHA256 = writePlanSHA256
        self.useTUI = useTUI
    }
}

public enum R46HError: Error, CustomStringConvertible, Equatable {
    case invalidArgument(String)
    case invalidData(String)
    case unauthorized(String)
    case unsafePath(String)
    case system(String)
    case cancelled(String)

    public var description: String {
        switch self {
        case .invalidArgument(let value): return "invalid argument: \(value)"
        case .invalidData(let value): return "invalid data: \(value)"
        case .unauthorized(let value): return "unauthorized: \(value)"
        case .unsafePath(let value): return "unsafe path: \(value)"
        case .system(let value): return "system error: \(value)"
        case .cancelled(let value): return "cancelled: \(value)"
        }
    }
}
