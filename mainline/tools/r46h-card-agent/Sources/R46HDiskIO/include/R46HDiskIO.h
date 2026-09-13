#ifndef R46H_DISK_IO_H
#define R46H_DISK_IO_H

#include <stdint.h>

int r46h_disk_geometry(
    int descriptor,
    uint64_t *base,
    uint64_t *size,
    uint32_t *block_size
);

int r46h_disk_synchronize_cache(int descriptor);

#endif
