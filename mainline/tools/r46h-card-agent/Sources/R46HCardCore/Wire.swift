import Darwin
import Foundation

public enum Wire {
    public static let maximumMessageBytes = 1024 * 1024

    public static func decodeRequest(_ data: Data) throws -> AgentRequest {
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              Set(object.keys) == ["version", "id", "token", "command", "arguments"],
              let arguments = object["arguments"] as? [String: String],
              arguments.count <= 16 else {
            throw R46HError.invalidData("request contains unknown, missing, or invalid fields")
        }
        let request = try JSONDecoder().decode(AgentRequest.self, from: data)
        guard request.version == AgentRequest.currentVersion,
              request.id.range(of: "^[a-z0-9-]{1,64}$", options: .regularExpression) != nil,
              isSHA256(request.token),
              request.command.range(of: "^[a-z][a-z0-9-]{0,63}$", options: .regularExpression) != nil,
              arguments.allSatisfy({ key, value in
                  key.range(of: "^[a-z][a-z0-9_]{0,63}$", options: .regularExpression) != nil &&
                  value.utf8.count <= 4096 &&
                  !value.contains("\0") && !value.contains("\n") && !value.contains("\r")
              }) else {
            throw R46HError.invalidData("request values are malformed")
        }
        return request
    }

    public static func decodeMessage(_ data: Data) throws -> AgentMessage {
        try JSONDecoder().decode(AgentMessage.self, from: data)
    }

    public static func readLine(from descriptor: Int32) throws -> Data {
        var data = Data()
        var byte: UInt8 = 0
        while data.count <= maximumMessageBytes {
            let count = Darwin.read(descriptor, &byte, 1)
            if count < 0 {
                if errno == EINTR { continue }
                throw R46HError.system("socket read: \(posixMessage())")
            }
            if count == 0 {
                throw R46HError.invalidData("socket closed before newline")
            }
            if byte == 10 { return data }
            data.append(byte)
        }
        throw R46HError.invalidData("wire message exceeds one MiB")
    }

    public static func write<T: Encodable>(_ value: T, to descriptor: Int32) throws {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        var data = try encoder.encode(value)
        guard data.count <= maximumMessageBytes else {
            throw R46HError.invalidData("wire response exceeds one MiB")
        }
        data.append(10)
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
                    throw R46HError.system("socket write: \(posixMessage())")
                }
                if count == 0 {
                    throw R46HError.system("socket write made no progress")
                }
                written += count
            }
        }
    }
}
