#!/bin/bash

# Sourced by the promotion tools after their owning payload or staging
# directory has been authenticated.  Input is an unmodified dmesg stream.

r46h_storage_health_from_log() {
  awk '
    {
      line = tolower($0)
      sub(/\r$/, "", line)

      if (line ~ /mmc0: (error|timeout)|mmcblk[0-9]+: error|buffer i\/o error|blk_update_request: i\/o error|ext4-fs error/) {
        faults++
      }
      if (line ~ /mmc_host mmc0: bus speed \(slot 0\) = 400000hz \(slot req 400000hz, actual 400000hz div = 0\)$/) {
        speed_400_count++
        speed_400_line = NR
      }
      if (line ~ /mmc0: error -84 whilst initialising sd card$/) {
        init_error_count++
        init_error_line = NR
      }
      if (line ~ /mmc_host mmc0: bus speed \(slot 0\) = 300000hz \(slot req 300000hz, actual 300000hz div = 0\)$/) {
        speed_300_count++
        speed_300_line = NR
      }
      if (line ~ /mmc_host mmc0: bus speed \(slot 0\) = 150000000hz \(slot req 150000000hz, actual 150000000hz div = 0\)$/) {
        speed_150m_count++
        speed_150m_line = NR
      }
      if (line ~ /mmc0: new ultra high speed sdr104 sdxc card at address 0001$/) {
        card_count++
        card_line = NR
      }
      if (line ~ /mmcblk0: mmc0:0001 sd 58\.2 gib$/) {
        disk_count++
        disk_line = NR
      }
      if (line ~ /[[:space:]]mmcblk0: p1 p2 p3$/) {
        partitions_count++
        partitions_line = NR
      }
      if (line ~ /ext4-fs \(mmcblk0p2\): mounted filesystem [0-9a-f-]+ r\/w with ordered data mode\. quota mode: none\.$/) {
        root_mount_count++
        root_mount_line = NR
      }
    }
    END {
      if (faults == 0) {
        print "clean"
        exit 0
      }
      if (faults == 1 && init_error_count == 1 &&
          speed_400_count == 1 && speed_300_count == 1 &&
          speed_150m_count == 1 && card_count == 1 && disk_count == 1 &&
          partitions_count == 1 && root_mount_count == 1 &&
          speed_400_line < init_error_line &&
          init_error_line < speed_300_line &&
          speed_300_line < speed_150m_line &&
          speed_150m_line < card_line && card_line < disk_line &&
          disk_line < partitions_line && partitions_line < root_mount_line) {
        print "recovered-known-open"
        exit 0
      }
      print "fault"
      exit 1
    }
  '
}

r46h_storage_health_current() {
  dmesg --color=never | r46h_storage_health_from_log
}
