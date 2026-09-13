import DiskArbitration
import Foundation

private final class ClaimResultBox {
    let semaphore = DispatchSemaphore(value: 0)
    private let lock = NSLock()
    private var failureStatus: DAReturn?

    func finish(_ dissenter: DADissenter?) {
        lock.lock()
        if let dissenter { failureStatus = DADissenterGetStatus(dissenter) }
        lock.unlock()
        semaphore.signal()
    }

    var status: DAReturn? {
        lock.lock()
        defer { lock.unlock() }
        return failureStatus
    }
}

private let claimCompleted: DADiskClaimCallback = { _, dissenter, context in
    guard let context else { return }
    let box = Unmanaged<ClaimResultBox>.fromOpaque(context).takeRetainedValue()
    box.finish(dissenter)
}

private let denyClaimRelease: DADiskClaimReleaseCallback = { _, _ in
    Unmanaged.passRetained(
        DADissenterCreate(
            kCFAllocatorDefault,
            DAReturn(kDAReturnBusy),
            "R46H partition write is active" as CFString
        )
    )
}

public final class WholeDiskClaim: @unchecked Sendable {
    private let session: DASession
    private let disk: DADisk
    private let queue: DispatchQueue
    private let lock = NSLock()
    private var claimed = false

    public init(
        device: String,
        timeout: TimeInterval = 30,
        cancelled: (() -> Bool)? = nil
    ) throws {
        try Validation.validateDevicePath(device)
        guard timeout > 0 else {
            throw R46HError.invalidArgument("Disk Arbitration claim timeout must be positive")
        }
        guard let session = DASessionCreate(kCFAllocatorDefault) else {
            throw R46HError.system("create Disk Arbitration session")
        }
        let disk = device.withCString {
            DADiskCreateFromBSDName(kCFAllocatorDefault, session, $0)
        }
        guard let disk else {
            throw R46HError.invalidData("Disk Arbitration could not resolve \(device)")
        }
        let queue = DispatchQueue(label: "r46h-card-agent.disk-claim")
        self.session = session
        self.disk = disk
        self.queue = queue
        DASessionSetDispatchQueue(session, queue)

        let result = ClaimResultBox()
        let context = Unmanaged.passRetained(result).toOpaque()
        DADiskClaim(
            disk,
            DADiskClaimOptions(kDADiskClaimOptionDefault),
            denyClaimRelease,
            nil,
            claimCompleted,
            context
        )
        let deadline = Date().addingTimeInterval(timeout)
        while result.semaphore.wait(timeout: .now() + .milliseconds(100)) != .success {
            if cancelled?() == true {
                DADiskUnclaim(disk)
                DASessionSetDispatchQueue(session, nil)
                throw R46HError.cancelled("Disk Arbitration claim cancelled")
            }
            guard Date() < deadline else {
                DADiskUnclaim(disk)
                DASessionSetDispatchQueue(session, nil)
                throw R46HError.system("Disk Arbitration claim timed out")
            }
        }
        if let status = result.status {
            DASessionSetDispatchQueue(session, nil)
            throw R46HError.unauthorized("Disk Arbitration claim was denied: status=\(status)")
        }
        guard DADiskIsClaimed(disk) else {
            DASessionSetDispatchQueue(session, nil)
            throw R46HError.invalidData("Disk Arbitration did not retain the whole-disk claim")
        }
        claimed = true
    }

    public func release() {
        lock.lock()
        guard claimed else {
            lock.unlock()
            return
        }
        claimed = false
        lock.unlock()
        DADiskUnclaim(disk)
        DASessionSetDispatchQueue(session, nil)
    }

    deinit {
        release()
    }
}
