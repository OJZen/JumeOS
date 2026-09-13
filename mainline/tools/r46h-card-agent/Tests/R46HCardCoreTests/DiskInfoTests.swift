import XCTest
@testable import R46HCardCore

final class DiskInfoTests: XCTestCase {
    func testPlistParserMapsStructuredDiskIdentityAndReadOnlyMount() throws {
        let object: [String: Any] = [
            "DeviceIdentifier": "disk4s1",
            "WholeDisk": false,
            "Content": "DOS_FAT_32",
            "Size": 117_440_512,
            "DeviceBlockSize": 512,
            "Internal": false,
            "RemovableMedia": true,
            "VirtualOrPhysical": "Physical",
            "BusProtocol": "USB",
            "ParentWholeDisk": "disk4",
            "PartitionMapPartitionOffset": 16_777_216,
            "VolumeUUID": "BOOT-UUID",
            "MountPoint": "/Volumes/BOOT",
            "WritableVolume": false,
        ]
        let data = try PropertyListSerialization.data(
            fromPropertyList: object,
            format: .xml,
            options: 0
        )

        let info = try DiskInfo(plistData: data)

        XCTAssertEqual(info["Device Identifier"], "disk4s1")
        XCTAssertEqual(info["Protocol"], "USB")
        XCTAssertEqual(info["Device Location"], "External")
        XCTAssertEqual(info["Removable Media"], "Removable")
        XCTAssertEqual(info["Virtual"], "No")
        XCTAssertEqual(info["Mounted"], "Yes")
        XCTAssertTrue(info["Volume Read-Only"]?.hasPrefix("Yes") == true)
        XCTAssertEqual(info.bytes(in: "Disk Size"), 117_440_512)
        XCTAssertEqual(info.leadingUInt(in: "Partition Offset"), 16_777_216)
    }

    func testBytesParsesDiskutilExactlySuffix() {
        let info = DiskInfo(raw: """
           Device Identifier:        disk4
           Disk Size:                31.9 GB (31914983424 Bytes) (exactly 62333952 512-Byte-Units)
           Partition Offset:         16.8 MB (16777216 Bytes) (exactly 32768 512-Byte-Units)
           Device Block Size:        512 Bytes
        """)

        XCTAssertEqual(info.bytes(in: "Disk Size"), 31_914_983_424)
        XCTAssertEqual(info.bytes(in: "Partition Offset"), 16_777_216)
        XCTAssertNil(info.bytes(in: "Device Block Size"))
        XCTAssertEqual(info.leadingUInt(in: "Device Block Size"), 512)
    }

    func testMountedPlistRequiresExplicitWritableVolumeField() throws {
        let object: [String: Any] = [
            "DeviceIdentifier": "disk4s1",
            "WholeDisk": false,
            "Content": "DOS_FAT_32",
            "Size": 117_440_512,
            "DeviceBlockSize": 512,
            "Internal": false,
            "RemovableMedia": true,
            "VirtualOrPhysical": "Physical",
            "BusProtocol": "USB",
            "MountPoint": "/Volumes/BOOT",
        ]
        let data = try PropertyListSerialization.data(
            fromPropertyList: object,
            format: .xml,
            options: 0
        )

        XCTAssertThrowsError(try DiskInfo(plistData: data)) { error in
            XCTAssertEqual(
                error as? R46HError,
                .invalidData("mounted diskutil plist is missing WritableVolume")
            )
        }
    }

    func testPartitionPlistMayOmitWholeDiskTransportFields() throws {
        let object: [String: Any] = [
            "DeviceIdentifier": "disk4s2",
            "WholeDisk": false,
            "Content": "Linux",
            "Size": 10_716_877_312,
            "DeviceBlockSize": 512,
            "PartitionMapPartitionOffset": 134_217_728,
            "MountPoint": "",
        ]
        let data = try PropertyListSerialization.data(
            fromPropertyList: object,
            format: .xml,
            options: 0
        )

        let info = try DiskInfo(plistData: data)

        XCTAssertEqual(info["Device Identifier"], "disk4s2")
        XCTAssertEqual(info.leadingUInt(in: "Partition Offset"), 134_217_728)
        XCTAssertEqual(info["Mounted"], "No")
        XCTAssertNil(info["Protocol"])
        XCTAssertNil(info["Device Location"])
    }

    func testParserKeepsFirstDuplicateFieldAndIgnoresMalformedLines() {
        let info = DiskInfo(raw: """
        Mounted: No
        this line has no separator
        Mounted: Yes
        : no-key
        """)

        XCTAssertEqual(info["Mounted"], "No")
        XCTAssertNil(info[""])
    }

    func testCardSnapshotUnmountedAllowsNotApplicable() {
        func info(_ mounted: String) -> DiskInfo {
            DiskInfo(raw: "Mounted: \(mounted)\nDevice Identifier: disk4s1")
        }
        let snapshot = CardSnapshot(
            whole: info("Not applicable (no file system)"),
            boot: info("No"),
            root: info("No"),
            easyroms: info("Not applicable (no file system)"),
            prefixSHA256: Fixtures.digestA
        )

        XCTAssertTrue(snapshot.allUnmounted)
        XCTAssertEqual(snapshot.summaryItems.count, 4)
        XCTAssertEqual(snapshot.summaryItems[1]["name"], "boot")
    }

    func testCardSnapshotDetectsMountedPartition() {
        func info(_ mounted: String) -> DiskInfo { DiskInfo(raw: "Mounted: \(mounted)") }
        let snapshot = CardSnapshot(
            whole: info("No"),
            boot: info("Yes"),
            root: info("No"),
            easyroms: info("No"),
            prefixSHA256: Fixtures.digestA
        )

        XCTAssertFalse(snapshot.allUnmounted)
    }
}
