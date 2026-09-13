import Darwin
import R46HDiskIO
import XCTest

final class DiskIOTests: XCTestCase {
    func testSynchronizeCacheRejectsNonDiskDescriptor() throws {
        let descriptor = open("/dev/null", O_RDONLY | O_CLOEXEC)
        guard descriptor >= 0 else {
            return XCTFail("failed to open /dev/null")
        }
        defer { close(descriptor) }

        errno = 0
        XCTAssertEqual(r46h_disk_synchronize_cache(descriptor), -1)
        XCTAssertTrue([ENODEV, ENOTTY].contains(errno), "unexpected errno: \(errno)")
    }
}
