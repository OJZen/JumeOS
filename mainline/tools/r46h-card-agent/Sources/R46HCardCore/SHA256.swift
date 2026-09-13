import CommonCrypto
import Darwin
import Foundation

public final class SHA256Stream {
    private var context = CC_SHA256_CTX()
    private var finished = false

    public init() {
        CC_SHA256_Init(&context)
    }

    public func update(_ bytes: UnsafeRawBufferPointer) throws {
        guard !finished else {
            throw R46HError.invalidData("SHA-256 stream is already finalized")
        }
        guard bytes.count <= Int(CC_LONG.max) else {
            throw R46HError.invalidData("SHA-256 update is too large")
        }
        if bytes.count > 0 {
            CC_SHA256_Update(&context, bytes.baseAddress, CC_LONG(bytes.count))
        }
    }

    public func finalize() throws -> String {
        guard !finished else {
            throw R46HError.invalidData("SHA-256 stream is already finalized")
        }
        finished = true
        var digest = [UInt8](repeating: 0, count: Int(CC_SHA256_DIGEST_LENGTH))
        CC_SHA256_Final(&digest, &context)
        return digest.map { String(format: "%02x", $0) }.joined()
    }
}

public enum SHA256 {
    public static func data(_ data: Data) throws -> String {
        let hasher = SHA256Stream()
        try data.withUnsafeBytes { try hasher.update($0) }
        return try hasher.finalize()
    }

    public static func file(at path: String) throws -> String {
        let descriptor = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW)
        guard descriptor >= 0 else {
            throw R46HError.system("open \(path): \(posixMessage())")
        }
        defer { close(descriptor) }
        return try descriptorHash(descriptor)
    }

    public static func descriptorHash(
        _ descriptor: Int32,
        offset: UInt64 = 0,
        length: UInt64? = nil,
        progress: ((UInt64) throws -> Void)? = nil,
        cancelled: (() -> Bool)? = nil
    ) throws -> String {
        guard offset <= UInt64(Int64.max) else {
            throw R46HError.invalidArgument("offset exceeds off_t")
        }
        if lseek(descriptor, off_t(offset), SEEK_SET) < 0 {
            throw R46HError.system("lseek: \(posixMessage())")
        }

        let hasher = SHA256Stream()
        let bufferSize = 4 * 1024 * 1024
        let buffer = UnsafeMutableRawPointer.allocate(
            byteCount: bufferSize,
            alignment: MemoryLayout<UInt64>.alignment
        )
        defer { buffer.deallocate() }

        var total: UInt64 = 0
        while length == nil || total < length! {
            if cancelled?() == true {
                throw R46HError.cancelled("operation cancelled")
            }
            let remaining = length.map { $0 - total }
            let request = Int(min(UInt64(bufferSize), remaining ?? UInt64(bufferSize)))
            let count = read(descriptor, buffer, request)
            if count < 0 {
                if errno == EINTR { continue }
                throw R46HError.system("read: \(posixMessage())")
            }
            if count == 0 {
                if let length, total != length {
                    throw R46HError.invalidData("unexpected EOF at \(total), expected \(length)")
                }
                break
            }
            try hasher.update(UnsafeRawBufferPointer(start: buffer, count: count))
            total += UInt64(count)
            try progress?(total)
        }
        return try hasher.finalize()
    }
}

public func isSHA256(_ value: String) -> Bool {
    value.count == 64 && value.utf8.allSatisfy {
        ($0 >= 48 && $0 <= 57) || ($0 >= 97 && $0 <= 102)
    }
}

public func posixMessage(_ code: Int32 = errno) -> String {
    String(cString: strerror(code))
}
