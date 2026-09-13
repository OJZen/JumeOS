#include "R46HDiskIO.h"

#include <sys/disk.h>
#include <sys/ioctl.h>

#ifndef DKIOCGETBASE
#define DKIOCGETBASE _IOR('d', 73, uint64_t)
#endif

int r46h_disk_geometry(
    int descriptor,
    uint64_t *base,
    uint64_t *size,
    uint32_t *block_size
) {
    uint64_t block_count = 0;

    if (ioctl(descriptor, DKIOCGETBASE, base) != 0) {
        return -1;
    }
    if (ioctl(descriptor, DKIOCGETBLOCKSIZE, block_size) != 0) {
        return -1;
    }
    if (ioctl(descriptor, DKIOCGETBLOCKCOUNT, &block_count) != 0) {
        return -1;
    }
    if (*block_size == 0 || block_count > UINT64_MAX / *block_size) {
        return -1;
    }
    *size = block_count * *block_size;
    return 0;
}

int r46h_disk_synchronize_cache(int descriptor) {
    return ioctl(descriptor, DKIOCSYNCHRONIZECACHE);
}
