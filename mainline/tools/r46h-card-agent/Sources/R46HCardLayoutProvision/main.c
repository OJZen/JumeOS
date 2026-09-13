#include <CommonCrypto/CommonDigest.h>
#include <DiskArbitration/DiskArbitration.h>
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/disk.h>
#include <sys/ioctl.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

#define BUFFER_SIZE (4U * 1024U * 1024U)
#define PROGRESS_INTERVAL (512ULL * 1024ULL * 1024ULL)
#define SHA256_HEX_SIZE (CC_SHA256_DIGEST_LENGTH * 2U + 1U)
#define QUICK_EXFAT_BOOT_OFFSET 0ULL
#define QUICK_EXFAT_BOOT_SIZE 12288ULL
#define QUICK_EXFAT_FAT_PREFIX_OFFSET 1048576ULL
#define QUICK_EXFAT_FAT_PREFIX_SIZE 17840ULL
#define QUICK_EXFAT_ROOT_PREFIX_OFFSET 8650752ULL
#define QUICK_EXFAT_ROOT_PREFIX_SIZE 512ULL
#define QUICK_EXFAT_PAYLOAD_OFFSET 8683520ULL
#define QUICK_EXFAT_PAYLOAD_SIZE 145784832ULL
#define QUICK_EASYROMS_SIZE 51683880448ULL
#define QUICK_EASYROMS_HEAD_SIZE 268435456ULL

static volatile sig_atomic_t stop_requested = 0;
static DASessionRef claim_session = NULL;
static DADiskRef claimed_disk = NULL;
static CFRunLoopRef claim_run_loop = NULL;
static volatile sig_atomic_t active_child_pgid = 0;

struct claim_state {
    int completed;
    int denied;
    DAReturn status;
};

static void fail_errno(const char *operation);
static void fail_data(const char *message);

struct source {
    const char *label;
    const char *path;
    const char *expected_hash;
    uint64_t expected_size;
    uint64_t hash_size;
    int descriptor;
    char initial_hash[SHA256_HEX_SIZE];
};

static void request_stop(int signal_number) {
    stop_requested = 1;
    if (active_child_pgid > 0) {
        kill(-(pid_t)active_child_pgid, signal_number);
    }
}

static void release_disk_claim(void) {
    if (claimed_disk != NULL) {
        if (DADiskIsClaimed(claimed_disk)) {
            DADiskUnclaim(claimed_disk);
        }
    }
    if (claim_session != NULL) {
        if (claim_run_loop != NULL) {
            DASessionUnscheduleFromRunLoop(
                claim_session,
                claim_run_loop,
                kCFRunLoopDefaultMode
            );
        }
    }
    if (claimed_disk != NULL) {
        CFRelease(claimed_disk);
        claimed_disk = NULL;
    }
    if (claim_session != NULL) {
        CFRelease(claim_session);
        claim_session = NULL;
        claim_run_loop = NULL;
    }
}

static void claim_completed(
    DADiskRef disk,
    DADissenterRef dissenter,
    void *context
) {
    (void)disk;
    struct claim_state *state = context;
    if (dissenter != NULL) {
        state->denied = 1;
        state->status = DADissenterGetStatus(dissenter);
    }
    state->completed = 1;
}

static void eject_completed(
    DADiskRef disk,
    DADissenterRef dissenter,
    void *context
) {
    claim_completed(disk, dissenter, context);
}

static DADissenterRef deny_claim_release(DADiskRef disk, void *context) {
    (void)disk;
    (void)context;
    return DADissenterCreate(
        kCFAllocatorDefault,
        kDAReturnBusy,
        CFSTR("R46H pinned media operation is active")
    );
}

static void claim_whole_disk(const char *raw_device_path) {
    static const char raw_prefix[] = "/dev/rdisk";
    char block_device_path[64];

    if (strncmp(raw_device_path, raw_prefix, strlen(raw_prefix)) != 0) {
        fail_data("raw device path is malformed");
    }
    const char *suffix = raw_device_path + strlen(raw_prefix);
    if (*suffix == '\0') {
        fail_data("raw device path is malformed");
    }
    for (const char *cursor = suffix; *cursor != '\0'; cursor++) {
        if (*cursor < '0' || *cursor > '9') {
            fail_data("raw device path is malformed");
        }
    }
    int result = snprintf(
        block_device_path,
        sizeof(block_device_path),
        "/dev/disk%s",
        suffix
    );
    if (result < 0 || (size_t)result >= sizeof(block_device_path)) {
        fail_data("block device path is too long");
    }

    claim_session = DASessionCreate(kCFAllocatorDefault);
    if (claim_session == NULL) {
        fail_data("create Disk Arbitration session");
    }
    claimed_disk = DADiskCreateFromBSDName(
        kCFAllocatorDefault,
        claim_session,
        block_device_path
    );
    if (claimed_disk == NULL) {
        fail_data("Disk Arbitration could not resolve target");
    }
    claim_run_loop = CFRunLoopGetCurrent();
    DASessionScheduleWithRunLoop(
        claim_session,
        claim_run_loop,
        kCFRunLoopDefaultMode
    );

    struct claim_state state = {0};
    DADiskClaim(
        claimed_disk,
        kDADiskClaimOptionDefault,
        deny_claim_release,
        NULL,
        claim_completed,
        &state
    );
    CFAbsoluteTime deadline = CFAbsoluteTimeGetCurrent() + 30.0;
    while (!state.completed) {
        if (stop_requested) {
            fail_data("Disk Arbitration claim cancelled");
        }
        if (CFAbsoluteTimeGetCurrent() >= deadline) {
            fail_data("Disk Arbitration claim timed out");
        }
        CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.1, true);
    }
    if (state.denied) {
        fprintf(stderr, "ERROR: Disk Arbitration claim denied: status=%d\n", state.status);
        exit(77);
    }
    if (!DADiskIsClaimed(claimed_disk)) {
        fail_data("Disk Arbitration did not retain whole-disk claim");
    }
    printf("R46H_LAYOUT stage=disk-claimed device=%s\n", block_device_path);
}

static void eject_claimed_disk(const char *raw_device_path) {
    if (claimed_disk == NULL || claim_session == NULL || claim_run_loop == NULL ||
        !DADiskIsClaimed(claimed_disk)) {
        fail_data("cannot eject without an active whole-disk claim");
    }
    struct claim_state state = {0};
    DADiskEject(
        claimed_disk,
        kDADiskEjectOptionDefault,
        eject_completed,
        &state
    );
    CFAbsoluteTime deadline = CFAbsoluteTimeGetCurrent() + 30.0;
    while (!state.completed) {
        if (CFAbsoluteTimeGetCurrent() >= deadline) {
            fail_data("Disk Arbitration eject timed out");
        }
        CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.1, true);
    }
    if (state.denied) {
        fprintf(stderr, "ERROR: Disk Arbitration eject denied: status=%d\n", state.status);
        exit(77);
    }

    char block_device_path[64];
    int result = snprintf(
        block_device_path,
        sizeof(block_device_path),
        "/dev/%s",
        raw_device_path + strlen("/dev/r")
    );
    if (result < 0 || (size_t)result >= sizeof(block_device_path)) {
        fail_data("block device path is too long");
    }
    for (unsigned int attempt = 0; attempt < 100; attempt++) {
        struct stat ignored;
        errno = 0;
        int raw_status = stat(raw_device_path, &ignored);
        int raw_errno = errno;
        errno = 0;
        int block_status = stat(block_device_path, &ignored);
        int block_errno = errno;
        if (raw_status != 0 && raw_errno == ENOENT &&
            block_status != 0 && block_errno == ENOENT) {
            printf("R46H_MEDIA_AUDIT stage=ejected device=%s\n", block_device_path);
            return;
        }
        usleep(100000);
    }
    fail_data("device nodes remained after eject");
}

static void fail_errno(const char *operation) {
    fprintf(stderr, "ERROR: %s: %s\n", operation, strerror(errno));
    exit(74);
}

static void fail_data(const char *message) {
    fprintf(stderr, "ERROR: %s\n", message);
    exit(65);
}

static uint64_t parse_u64(const char *value, const char *label) {
    char *end = NULL;
    if (*value == '\0') {
        fprintf(stderr, "ERROR: invalid %s\n", label);
        exit(64);
    }
    for (const char *cursor = value; *cursor != '\0'; cursor++) {
        if (*cursor < '0' || *cursor > '9') {
            fprintf(stderr, "ERROR: invalid %s\n", label);
            exit(64);
        }
    }
    errno = 0;
    unsigned long long parsed = strtoull(value, &end, 10);
    if (errno != 0 || end == value || *end != '\0' || parsed == 0) {
        fprintf(stderr, "ERROR: invalid %s\n", label);
        exit(64);
    }
    return (uint64_t)parsed;
}

static uint64_t parse_u64_or_zero(const char *value, const char *label) {
    if (strcmp(value, "0") == 0) {
        return 0;
    }
    return parse_u64(value, label);
}

static int is_lower_hex_sha256(const char *value) {
    if (strlen(value) != CC_SHA256_DIGEST_LENGTH * 2U) {
        return 0;
    }
    for (size_t index = 0; index < CC_SHA256_DIGEST_LENGTH * 2U; index++) {
        char byte = value[index];
        if (!((byte >= '0' && byte <= '9') || (byte >= 'a' && byte <= 'f'))) {
            return 0;
        }
    }
    return 1;
}

static void digest_to_hex(const unsigned char *digest, char output[SHA256_HEX_SIZE]) {
    static const char alphabet[] = "0123456789abcdef";
    for (size_t index = 0; index < CC_SHA256_DIGEST_LENGTH; index++) {
        output[index * 2U] = alphabet[digest[index] >> 4U];
        output[index * 2U + 1U] = alphabet[digest[index] & 0x0fU];
    }
    output[CC_SHA256_DIGEST_LENGTH * 2U] = '\0';
}

static void hash_range(
    int descriptor,
    uint64_t offset,
    uint64_t length,
    char output[SHA256_HEX_SIZE],
    const char *stage,
    const char *label
) {
    unsigned char *buffer = malloc(BUFFER_SIZE);
    if (buffer == NULL) {
        fail_errno("allocate hash buffer");
    }

    CC_SHA256_CTX context;
    if (CC_SHA256_Init(&context) != 1) {
        free(buffer);
        fail_data("initialize SHA-256");
    }

    uint64_t completed = 0;
    uint64_t next_report = PROGRESS_INTERVAL;
    while (completed < length) {
        if (stop_requested) {
            free(buffer);
            fail_data("operation interrupted");
        }
        size_t request = (size_t)((length - completed) < BUFFER_SIZE
            ? (length - completed)
            : BUFFER_SIZE);
        ssize_t count = pread(descriptor, buffer, request, (off_t)(offset + completed));
        if (count < 0) {
            free(buffer);
            fail_errno("read for SHA-256");
        }
        if (count == 0) {
            free(buffer);
            fail_data("unexpected EOF while hashing");
        }
        if (CC_SHA256_Update(&context, buffer, (CC_LONG)count) != 1) {
            free(buffer);
            fail_data("update SHA-256");
        }
        completed += (uint64_t)count;
        if (stage != NULL && label != NULL &&
            (completed >= next_report || completed == length)) {
            printf("R46H_LAYOUT stage=%s source=%s bytes=%llu/%llu\n",
                stage,
                label,
                (unsigned long long)completed,
                (unsigned long long)length);
            while (next_report <= completed &&
                   next_report <= UINT64_MAX - PROGRESS_INTERVAL) {
                next_report += PROGRESS_INTERVAL;
            }
        }
    }

    unsigned char digest[CC_SHA256_DIGEST_LENGTH];
    if (CC_SHA256_Final(digest, &context) != 1) {
        free(buffer);
        fail_data("finalize SHA-256");
    }
    free(buffer);
    digest_to_hex(digest, output);
}

struct hash_segment {
    uint64_t offset;
    uint64_t length;
};

static void hash_segments(
    int descriptor,
    uint64_t base_offset,
    uint64_t containing_length,
    uint32_t block_size,
    const struct hash_segment *segments,
    size_t segment_count,
    char output[SHA256_HEX_SIZE],
    const char *stage,
    const char *label
) {
    if (block_size == 0 || block_size > BUFFER_SIZE ||
        BUFFER_SIZE > SIZE_MAX - block_size) {
        fail_data("segmented hash block size is invalid");
    }
    unsigned char *buffer = malloc(BUFFER_SIZE + block_size);
    if (buffer == NULL) {
        fail_errno("allocate segmented hash buffer");
    }

    CC_SHA256_CTX context;
    if (CC_SHA256_Init(&context) != 1) {
        free(buffer);
        fail_data("initialize segmented SHA-256");
    }

    uint64_t total_length = 0;
    for (size_t index = 0; index < segment_count; index++) {
        if (segments[index].length == 0 ||
            segments[index].offset > containing_length ||
            segments[index].length > containing_length - segments[index].offset ||
            total_length > UINT64_MAX - segments[index].length) {
            free(buffer);
            fail_data("segmented hash range is invalid");
        }
        total_length += segments[index].length;
    }

    uint64_t completed_total = 0;
    uint64_t next_report = PROGRESS_INTERVAL;
    for (size_t index = 0; index < segment_count; index++) {
        uint64_t completed_segment = 0;
        while (completed_segment < segments[index].length) {
            if (stop_requested) {
                free(buffer);
                fail_data("operation interrupted");
            }
            uint64_t remaining = segments[index].length - completed_segment;
            size_t desired = (size_t)(remaining < BUFFER_SIZE ? remaining : BUFFER_SIZE);
            uint64_t relative_offset = segments[index].offset + completed_segment;
            if (base_offset > UINT64_MAX - relative_offset) {
                free(buffer);
                fail_data("segmented hash offset overflow");
            }
            uint64_t absolute_offset = base_offset + relative_offset;
            uint64_t aligned_offset = absolute_offset - (absolute_offset % block_size);
            size_t leading = (size_t)(absolute_offset - aligned_offset);
            if (desired > SIZE_MAX - leading ||
                leading + desired > SIZE_MAX - (block_size - 1U)) {
                free(buffer);
                fail_data("segmented hash request overflow");
            }
            size_t aligned_request = leading + desired;
            aligned_request =
                ((aligned_request + block_size - 1U) / block_size) * block_size;
            if (aligned_request > BUFFER_SIZE + block_size ||
                aligned_offset > base_offset + containing_length ||
                aligned_request > base_offset + containing_length - aligned_offset) {
                free(buffer);
                fail_data("segmented hash aligned request is invalid");
            }
            ssize_t count = pread(
                descriptor,
                buffer,
                aligned_request,
                (off_t)aligned_offset
            );
            if (count < 0) {
                free(buffer);
                fail_errno("read for segmented SHA-256");
            }
            if ((size_t)count != aligned_request) {
                free(buffer);
                fail_data("short aligned read while hashing segments");
            }
            if (CC_SHA256_Update(&context, buffer + leading, (CC_LONG)desired) != 1) {
                free(buffer);
                fail_data("update segmented SHA-256");
            }
            completed_segment += (uint64_t)desired;
            completed_total += (uint64_t)desired;
            if (stage != NULL && label != NULL &&
                (completed_total >= next_report || completed_total == total_length)) {
                printf("R46H_LAYOUT stage=%s source=%s bytes=%llu/%llu\n",
                    stage,
                    label,
                    (unsigned long long)completed_total,
                    (unsigned long long)total_length);
                while (next_report <= completed_total &&
                       next_report <= UINT64_MAX - PROGRESS_INTERVAL) {
                    next_report += PROGRESS_INTERVAL;
                }
            }
        }
    }

    unsigned char digest[CC_SHA256_DIGEST_LENGTH];
    if (CC_SHA256_Final(digest, &context) != 1) {
        free(buffer);
        fail_data("finalize segmented SHA-256");
    }
    free(buffer);
    digest_to_hex(digest, output);
}

static void require_quick_immutable_hash(
    int descriptor,
    uint64_t easyroms_offset,
    uint64_t easyroms_size,
    uint32_t block_size,
    const char *expected_hash,
    char actual_hash[SHA256_HEX_SIZE],
    const char *stage
) {
    static const struct hash_segment segments[] = {
        { QUICK_EXFAT_BOOT_OFFSET, QUICK_EXFAT_BOOT_SIZE },
        { QUICK_EXFAT_FAT_PREFIX_OFFSET, QUICK_EXFAT_FAT_PREFIX_SIZE },
        { QUICK_EXFAT_ROOT_PREFIX_OFFSET, QUICK_EXFAT_ROOT_PREFIX_SIZE },
        { QUICK_EXFAT_PAYLOAD_OFFSET, QUICK_EXFAT_PAYLOAD_SIZE },
    };
    if (!is_lower_hex_sha256(expected_hash)) {
        fail_data("quick immutable SHA-256 is malformed");
    }
    hash_segments(
        descriptor,
        easyroms_offset,
        easyroms_size,
        block_size,
        segments,
        sizeof(segments) / sizeof(segments[0]),
        actual_hash,
        stage,
        "easyroms-immutable"
    );
    if (strcmp(actual_hash, expected_hash) != 0) {
        fprintf(stderr, "ERROR: easyroms immutable payload SHA-256 mismatch\n");
        exit(65);
    }
    printf("R46H_MEDIA_AUDIT stage=%s range=easyroms-immutable bytes=%llu sha256=%s\n",
        stage == NULL ? "unspecified" : stage,
        (unsigned long long)(
            QUICK_EXFAT_BOOT_SIZE +
            QUICK_EXFAT_FAT_PREFIX_SIZE +
            QUICK_EXFAT_ROOT_PREFIX_SIZE +
            QUICK_EXFAT_PAYLOAD_SIZE
        ),
        actual_hash);
}

static void open_source(struct source *source) {
    struct stat metadata;

    if (!is_lower_hex_sha256(source->expected_hash)) {
        fail_data("source SHA-256 is malformed");
    }
    source->descriptor = open(source->path, O_RDONLY | O_NOFOLLOW);
    if (source->descriptor < 0) {
        fail_errno("open source");
    }
    if (fstat(source->descriptor, &metadata) != 0) {
        fail_errno("stat source");
    }
    if (!S_ISREG(metadata.st_mode) || metadata.st_nlink != 1 ||
        (uint64_t)metadata.st_size != source->expected_size ||
        source->hash_size == 0 || source->hash_size > source->expected_size) {
        fail_data("source identity mismatch");
    }

    hash_range(
        source->descriptor,
        0,
        source->hash_size,
        source->initial_hash,
        "source-hash-before",
        source->label
    );
    if (strcmp(source->initial_hash, source->expected_hash) != 0) {
        fprintf(stderr, "ERROR: %s source SHA-256 mismatch\n", source->label);
        exit(65);
    }
    printf("R46H_LAYOUT source=%s bytes=%llu sha256=%s\n",
        source->label,
        (unsigned long long)source->hash_size,
        source->initial_hash);
}

static void write_source_range(
    const struct source *source,
    int target,
    uint64_t source_offset,
    uint64_t target_offset,
    uint64_t length,
    const char *phase
) {
    if (length == 0 || source_offset > source->hash_size ||
        length > source->hash_size - source_offset) {
        fail_data("source write range is invalid");
    }
    unsigned char *buffer = malloc(BUFFER_SIZE);
    if (buffer == NULL) {
        fail_errno("allocate write buffer");
    }

    uint64_t completed = 0;
    uint64_t next_report = PROGRESS_INTERVAL;
    while (completed < length) {
        size_t request = (size_t)((length - completed) < BUFFER_SIZE
            ? (length - completed)
            : BUFFER_SIZE);
        ssize_t count = pread(
            source->descriptor,
            buffer,
            request,
            (off_t)(source_offset + completed)
        );
        if (count < 0) {
            free(buffer);
            fail_errno("read source for write");
        }
        if (count == 0) {
            free(buffer);
            fail_data("unexpected source EOF during write");
        }

        size_t written = 0;
        while (written < (size_t)count) {
            ssize_t result = pwrite(
                target,
                buffer + written,
                (size_t)count - written,
                (off_t)(target_offset + completed + written)
            );
            if (result < 0) {
                free(buffer);
                fail_errno("write target");
            }
            if (result == 0) {
                free(buffer);
                fail_data("short target write");
            }
            written += (size_t)result;
        }
        completed += (uint64_t)count;
        if (completed >= next_report || completed == length) {
            printf("R46H_LAYOUT stage=write source=%s phase=%s bytes=%llu/%llu\n",
                source->label,
                phase,
                (unsigned long long)completed,
                (unsigned long long)length);
            while (next_report <= completed &&
                   next_report <= UINT64_MAX - PROGRESS_INTERVAL) {
                next_report += PROGRESS_INTERVAL;
            }
        }
    }
    free(buffer);
}

static void write_source(
    const struct source *source,
    int target,
    uint64_t target_offset
) {
    write_source_range(
        source,
        target,
        0,
        target_offset,
        source->hash_size,
        "full"
    );
}

static void synchronize_target(int target, const char *phase) {
    if (fsync(target) != 0) {
        fail_errno("fsync raw target");
    }
    if (ioctl(target, DKIOCSYNCHRONIZECACHE) != 0) {
        fail_errno("DKIOCSYNCHRONIZECACHE raw target");
    }
    printf("R46H_LAYOUT stage=cache-synchronized phase=%s\n", phase);
}

static void zero_range(int target, uint64_t offset, uint64_t length) {
    unsigned char *buffer = calloc(1, BUFFER_SIZE);
    if (buffer == NULL) {
        fail_errno("allocate zero buffer");
    }

    uint64_t completed = 0;
    while (completed < length) {
        size_t request = (size_t)((length - completed) < BUFFER_SIZE
            ? (length - completed)
            : BUFFER_SIZE);
        size_t written = 0;
        while (written < request) {
            ssize_t result = pwrite(
                target,
                buffer + written,
                request - written,
                (off_t)(offset + completed + written)
            );
            if (result < 0) {
                free(buffer);
                fail_errno("zero target range");
            }
            if (result == 0) {
                free(buffer);
                fail_data("short zero write");
            }
            written += (size_t)result;
        }
        completed += request;
    }
    free(buffer);
    printf("R46H_LAYOUT stage=zero-range bytes=%llu/%llu\n",
        (unsigned long long)length,
        (unsigned long long)length);
}

static void verify_zero_range(int target, uint64_t offset, uint64_t length) {
    unsigned char *buffer = malloc(BUFFER_SIZE);
    if (buffer == NULL) {
        fail_errno("allocate zero verification buffer");
    }

    uint64_t completed = 0;
    while (completed < length) {
        size_t request = (size_t)((length - completed) < BUFFER_SIZE
            ? (length - completed)
            : BUFFER_SIZE);
        ssize_t count = pread(target, buffer, request, (off_t)(offset + completed));
        if (count < 0) {
            free(buffer);
            fail_errno("read zero verification range");
        }
        if ((size_t)count != request) {
            free(buffer);
            fail_data("short zero verification read");
        }
        for (size_t index = 0; index < request; index++) {
            if (buffer[index] != 0) {
                free(buffer);
                fail_data("EASYROMS cleared range is not zero");
            }
        }
        completed += request;
    }
    free(buffer);
}

static void verify_source_unchanged(struct source *source) {
    char current_hash[SHA256_HEX_SIZE];
    hash_range(
        source->descriptor,
        0,
        source->hash_size,
        current_hash,
        "source-hash-after",
        source->label
    );
    if (strcmp(current_hash, source->initial_hash) != 0) {
        fprintf(stderr, "ERROR: %s source changed during provisioning\n", source->label);
        exit(65);
    }
}

static void verify_target_hash(
    int target,
    const struct source *source,
    uint64_t target_offset
) {
    char current_hash[SHA256_HEX_SIZE];
    hash_range(
        target,
        target_offset,
        source->hash_size,
        current_hash,
        "readback",
        source->label
    );
    if (strcmp(current_hash, source->initial_hash) != 0) {
        fprintf(stderr, "ERROR: %s target readback SHA-256 mismatch\n", source->label);
        exit(65);
    }
    printf("R46H_LAYOUT readback=%s sha256=%s\n", source->label, current_hash);
}

static void install_interrupt_handlers(void) {
    struct sigaction action = {0};
    action.sa_handler = request_stop;
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGINT, &action, NULL) != 0 ||
        sigaction(SIGTERM, &action, NULL) != 0 ||
        sigaction(SIGHUP, &action, NULL) != 0) {
        fail_errno("install signal handlers");
    }
}

static uint32_t verify_raw_geometry(
    int descriptor,
    uint64_t expected_whole_size
) {
    uint32_t block_size = 0;
    uint64_t block_count = 0;
    if (ioctl(descriptor, DKIOCGETBLOCKSIZE, &block_size) != 0 ||
        ioctl(descriptor, DKIOCGETBLOCKCOUNT, &block_count) != 0 ||
        block_size != 512 || block_count > UINT64_MAX / block_size ||
        block_count * block_size != expected_whole_size) {
        fail_data("raw target geometry mismatch");
    }
    return block_size;
}

static void verify_raw_identity(
    int descriptor,
    const char *device_path,
    const struct stat *identity_before
) {
    struct stat descriptor_after;
    struct stat path_after;
    if (fstat(descriptor, &descriptor_after) != 0 ||
        stat(device_path, &path_after) != 0 ||
        !S_ISCHR(descriptor_after.st_mode) ||
        !S_ISCHR(path_after.st_mode) ||
        identity_before->st_rdev != descriptor_after.st_rdev ||
        identity_before->st_rdev != path_after.st_rdev) {
        fail_data("raw target identity changed during operation");
    }
}

static void require_expected_hash(
    int descriptor,
    uint64_t offset,
    uint64_t length,
    const char *expected_hash,
    const char *label,
    char actual_hash[SHA256_HEX_SIZE]
) {
    if (!is_lower_hex_sha256(expected_hash)) {
        fail_data("audit SHA-256 is malformed");
    }
    hash_range(
        descriptor,
        offset,
        length,
        actual_hash,
        "audit-read",
        label
    );
    if (strcmp(actual_hash, expected_hash) != 0) {
        fprintf(stderr, "ERROR: %s audit SHA-256 mismatch\n", label);
        exit(65);
    }
    printf("R46H_MEDIA_AUDIT range=%s bytes=%llu sha256=%s\n",
        label,
        (unsigned long long)length,
        actual_hash);
}

static int is_uuid_string(const char *value) {
    if (strlen(value) != 36) {
        return 0;
    }
    for (size_t index = 0; index < 36; index++) {
        if (index == 8 || index == 13 || index == 18 || index == 23) {
            if (value[index] != '-') {
                return 0;
            }
            continue;
        }
        char byte = value[index];
        if (!((byte >= '0' && byte <= '9') ||
              (byte >= 'a' && byte <= 'f') ||
              (byte >= 'A' && byte <= 'F'))) {
            return 0;
        }
    }
    return 1;
}

static void require_no_target_mounts(const char *expected_identifier) {
    char partition[3][64];
    for (unsigned int index = 0; index < 3; index++) {
        int result = snprintf(
            partition[index],
            sizeof(partition[index]),
            "/dev/%ss%u",
            expected_identifier,
            index + 1
        );
        if (result < 0 || (size_t)result >= sizeof(partition[index])) {
            fail_data("partition mount identity is too long");
        }
    }
    struct statfs *mounts = NULL;
    int count = getmntinfo(&mounts, MNT_NOWAIT);
    if (count <= 0 || mounts == NULL) {
        fail_errno("enumerate mounted filesystems");
    }
    for (int index = 0; index < count; index++) {
        for (unsigned int partition_index = 0; partition_index < 3;
             partition_index++) {
            if (strcmp(mounts[index].f_mntfromname,
                       partition[partition_index]) == 0) {
                fail_data("target partition remained mounted during audit");
            }
        }
    }
}

static void create_snapshot(
    int target,
    uint64_t target_offset,
    uint64_t copied_size,
    uint64_t logical_size,
    const char *path,
    const char *expected_hash,
    const char *label
) {
    int output = open(
        path,
        O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW | O_CLOEXEC,
        0600
    );
    if (output < 0) {
        fail_errno("create audit snapshot");
    }
    if (ftruncate(output, (off_t)logical_size) != 0) {
        close(output);
        fail_errno("size audit snapshot");
    }

    unsigned char *buffer = malloc(BUFFER_SIZE);
    if (buffer == NULL) {
        close(output);
        fail_errno("allocate snapshot buffer");
    }
    uint64_t completed = 0;
    uint64_t next_report = PROGRESS_INTERVAL;
    while (completed < copied_size) {
        if (stop_requested) {
            free(buffer);
            close(output);
            fail_data("audit snapshot interrupted");
        }
        size_t request = (size_t)((copied_size - completed) < BUFFER_SIZE
            ? (copied_size - completed)
            : BUFFER_SIZE);
        ssize_t count = pread(
            target,
            buffer,
            request,
            (off_t)(target_offset + completed)
        );
        if (count < 0) {
            free(buffer);
            close(output);
            fail_errno("read target for audit snapshot");
        }
        if ((size_t)count != request) {
            free(buffer);
            close(output);
            fail_data("short target read for audit snapshot");
        }
        size_t written = 0;
        while (written < request) {
            ssize_t result = pwrite(
                output,
                buffer + written,
                request - written,
                (off_t)(completed + written)
            );
            if (result < 0) {
                free(buffer);
                close(output);
                fail_errno("write audit snapshot");
            }
            if (result == 0) {
                free(buffer);
                close(output);
                fail_data("short audit snapshot write");
            }
            written += (size_t)result;
        }
        completed += request;
        if (completed >= next_report || completed == copied_size) {
            printf("R46H_MEDIA_AUDIT stage=snapshot label=%s bytes=%llu/%llu\n",
                label,
                (unsigned long long)completed,
                (unsigned long long)copied_size);
            while (next_report <= completed &&
                   next_report <= UINT64_MAX - PROGRESS_INTERVAL) {
                next_report += PROGRESS_INTERVAL;
            }
        }
    }
    free(buffer);
    if (fsync(output) != 0 || close(output) != 0) {
        fail_errno("flush audit snapshot");
    }

    int input = open(path, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (input < 0) {
        fail_errno("reopen audit snapshot");
    }
    struct stat metadata;
    if (fstat(input, &metadata) != 0 ||
        !S_ISREG(metadata.st_mode) ||
        metadata.st_uid != 0 ||
        (metadata.st_mode & 0777) != 0600 ||
        metadata.st_nlink != 1 ||
        (uint64_t)metadata.st_size != logical_size) {
        close(input);
        fail_data("audit snapshot identity mismatch");
    }
    char actual_hash[SHA256_HEX_SIZE];
    hash_range(
        input,
        0,
        copied_size,
        actual_hash,
        "snapshot-hash",
        label
    );
    if (strcmp(actual_hash, expected_hash) != 0) {
        close(input);
        fail_data("audit snapshot SHA-256 mismatch");
    }
    if (close(input) != 0) {
        fail_errno("close audit snapshot");
    }
}

static void verify_probe_source(
    const char *path,
    uint64_t expected_size,
    const char *expected_hash
) {
    if (!is_lower_hex_sha256(expected_hash)) {
        fail_data("probe SHA-256 is malformed");
    }
    int descriptor = open(path, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (descriptor < 0) {
        fail_errno("open filesystem probe");
    }
    struct stat metadata;
    if (fstat(descriptor, &metadata) != 0 ||
        !S_ISREG(metadata.st_mode) ||
        metadata.st_uid != 0 ||
        (metadata.st_mode & 0777) != 0700 ||
        metadata.st_nlink != 1 ||
        (uint64_t)metadata.st_size != expected_size) {
        close(descriptor);
        fail_data("filesystem probe identity mismatch");
    }
    char actual_hash[SHA256_HEX_SIZE];
    hash_range(
        descriptor,
        0,
        expected_size,
        actual_hash,
        "probe-hash",
        "filesystem-probe"
    );
    if (strcmp(actual_hash, expected_hash) != 0) {
        close(descriptor);
        fail_data("filesystem probe SHA-256 mismatch");
    }
    if (close(descriptor) != 0) {
        fail_errno("close filesystem probe");
    }
}

static void verify_probe_result(
    const char *path,
    const char *boot_uuid,
    const char *easyroms_uuid
) {
    char expected[256];
    int expected_length = snprintf(
        expected,
        sizeof(expected),
        "R46H_FILESYSTEM_PROBE result=pass boot_uuid=%s easyroms_uuid=%s\n",
        boot_uuid,
        easyroms_uuid
    );
    if (expected_length < 0 || (size_t)expected_length >= sizeof(expected)) {
        fail_data("filesystem probe result is too long");
    }
    int descriptor = open(path, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (descriptor < 0) {
        fail_errno("open filesystem probe result");
    }
    struct stat metadata;
    char actual[256];
    ssize_t count = read(descriptor, actual, sizeof(actual));
    if (count < 0) {
        close(descriptor);
        fail_errno("read filesystem probe result");
    }
    if (fstat(descriptor, &metadata) != 0 ||
        !S_ISREG(metadata.st_mode) ||
        metadata.st_uid != 0 ||
        (metadata.st_mode & 0777) != 0600 ||
        metadata.st_nlink != 1 ||
        count != expected_length ||
        memcmp(actual, expected, (size_t)expected_length) != 0) {
        close(descriptor);
        fail_data("filesystem probe result mismatch");
    }
    char extra;
    if (read(descriptor, &extra, 1) != 0) {
        close(descriptor);
        fail_data("filesystem probe result has trailing data");
    }
    if (close(descriptor) != 0) {
        fail_errno("close filesystem probe result");
    }
}

static void run_filesystem_probe(
    const char *probe_path,
    const char *expected_identifier,
    const char *boot_snapshot,
    const char *easyroms_snapshot,
    uint64_t easyroms_size,
    const char *easyroms_policy,
    const char *boot_uuid,
    const char *easyroms_uuid,
    const char *receipt_dir,
    const char *result_path
) {
    pid_t child = fork();
    if (child < 0) {
        fail_errno("fork filesystem probe");
    }
    if (child == 0) {
        if (setpgid(0, 0) != 0) {
            _exit(126);
        }
        char easyroms_size_text[32];
        int size_length = snprintf(
            easyroms_size_text,
            sizeof(easyroms_size_text),
            "%llu",
            (unsigned long long)easyroms_size
        );
        if (size_length < 1 || (size_t)size_length >= sizeof(easyroms_size_text)) {
            _exit(126);
        }
        char *const arguments[] = {
            "/bin/bash",
            (char *)probe_path,
            (char *)expected_identifier,
            (char *)boot_snapshot,
            (char *)easyroms_snapshot,
            easyroms_size_text,
            (char *)easyroms_policy,
            (char *)boot_uuid,
            (char *)easyroms_uuid,
            (char *)receipt_dir,
            (char *)result_path,
            NULL,
        };
        char *const environment[] = {
            "PATH=/usr/bin:/bin:/usr/sbin:/sbin",
            "LC_ALL=C",
            "LANG=C",
            NULL,
        };
        execve("/bin/bash", arguments, environment);
        _exit(127);
    }
    if (setpgid(child, child) != 0 && errno != EACCES && errno != ESRCH) {
        kill(child, SIGKILL);
        waitpid(child, NULL, 0);
        fail_errno("isolate filesystem probe process group");
    }
    active_child_pgid = child;

    int status = 0;
    unsigned int stop_waits = 0;
    for (;;) {
        pid_t result = waitpid(child, &status, WNOHANG);
        if (result == child) {
            break;
        }
        if (result < 0 && errno != EINTR) {
            kill(-child, SIGKILL);
            waitpid(child, NULL, 0);
            active_child_pgid = 0;
            fail_errno("wait for filesystem probe");
        }
        if (stop_requested) {
            kill(-child, SIGTERM);
            stop_waits++;
            if (stop_waits >= 50) {
                kill(-child, SIGKILL);
            }
        }
        usleep(100000);
    }
    active_child_pgid = 0;
    errno = 0;
    if (kill(-child, 0) == 0 || errno != ESRCH) {
        kill(-child, SIGKILL);
        fail_data("filesystem probe left a process-group descendant");
    }
    if (stop_requested) {
        fail_data("filesystem probe interrupted");
    }
    if (!WIFEXITED(status) || WEXITSTATUS(status) != 0) {
        fail_data("filesystem probe failed");
    }
    verify_probe_result(result_path, boot_uuid, easyroms_uuid);
}

static int run_media_audit(int argc, char **argv) {
    if (argc != 30) {
        fprintf(stderr,
            "usage: r46h-card-layout-provision audit RAW WHOLE_SIZE "
            "PREFIX_SIZE PREFIX_SHA BOOT_OFFSET BOOT_SIZE BOOT_IMAGE_SHA "
            "ROOT_OFFSET ROOT_SIZE ROOT_SHA EASYROMS_OFFSET EASYROMS_SIZE "
            "EASYROMS_SHA EASYROMS_HEAD_SIZE EASYROMS_POLICY PROBE PROBE_SIZE PROBE_SHA BOOT_SNAPSHOT "
            "EASYROMS_SNAPSHOT IDENTIFIER BOOT_UUID EASYROMS_UUID RECEIPT_DIR "
            "PROBE_RESULT EASYROMS_HEAD_SHA AUDIT_LEVEL QUICK_IMMUTABLE_SHA\n");
        return 64;
    }
    const char *device_path = argv[2];
    uint64_t expected_whole_size = parse_u64(argv[3], "whole size");
    uint64_t prefix_size = parse_u64(argv[4], "prefix size");
    const char *prefix_sha = argv[5];
    uint64_t boot_offset = parse_u64(argv[6], "BOOT offset");
    uint64_t boot_size = parse_u64(argv[7], "BOOT size");
    const char *boot_image_sha = argv[8];
    uint64_t root_offset = parse_u64(argv[9], "root offset");
    uint64_t root_size = parse_u64(argv[10], "root size");
    const char *root_sha = argv[11];
    uint64_t easyroms_offset = parse_u64(argv[12], "EASYROMS offset");
    uint64_t easyroms_size = parse_u64(argv[13], "EASYROMS size");
    const char *easyroms_sha = argv[14];
    uint64_t easyroms_head_size = parse_u64(argv[15], "EASYROMS head size");
    const char *easyroms_policy = argv[16];
    const char *probe_path = argv[17];
    uint64_t probe_size = parse_u64(argv[18], "probe size");
    const char *probe_sha = argv[19];
    const char *boot_snapshot = argv[20];
    const char *easyroms_snapshot = argv[21];
    const char *expected_identifier = argv[22];
    const char *boot_uuid = argv[23];
    const char *easyroms_uuid = argv[24];
    const char *receipt_dir = argv[25];
    const char *probe_result = argv[26];
    const char *easyroms_head_sha = argv[27];
    const char *audit_level = argv[28];
    const char *quick_immutable_sha = argv[29];

    int audit_is_full = strcmp(audit_level, "full") == 0;
    int audit_is_quick = strcmp(audit_level, "quick") == 0;
    int audit_is_compact_head = strcmp(audit_level, "compact-head") == 0;

    char expected_raw_path[64];
    int path_length = snprintf(
        expected_raw_path,
        sizeof(expected_raw_path),
        "/dev/r%s",
        expected_identifier
    );
    if (path_length < 0 || (size_t)path_length >= sizeof(expected_raw_path) ||
        strcmp(device_path, expected_raw_path) != 0 ||
        !is_lower_hex_sha256(boot_image_sha) ||
        (!is_lower_hex_sha256(easyroms_head_sha) &&
         !(audit_is_compact_head && strcmp(easyroms_head_sha, "-") == 0)) ||
        (audit_is_quick && !is_lower_hex_sha256(quick_immutable_sha)) ||
        (!audit_is_quick && strcmp(quick_immutable_sha, "-") != 0) ||
        (!audit_is_full && !audit_is_quick && !audit_is_compact_head) ||
        (audit_is_full && !is_lower_hex_sha256(easyroms_sha)) ||
        ((audit_is_quick || audit_is_compact_head) && strcmp(easyroms_sha, "-") != 0) ||
        (audit_is_quick && strcmp(easyroms_policy, "three-payloads") != 0) ||
        (audit_is_quick &&
         (easyroms_size != QUICK_EASYROMS_SIZE ||
          easyroms_head_size != QUICK_EASYROMS_HEAD_SIZE)) ||
        (audit_is_compact_head && strcmp(easyroms_policy, "blank") != 0) ||
        (strcmp(easyroms_policy, "blank") != 0 &&
         strcmp(easyroms_policy, "three-payloads") != 0) ||
        !is_uuid_string(boot_uuid) ||
        !is_uuid_string(easyroms_uuid) ||
        prefix_size != boot_offset ||
        boot_offset > expected_whole_size ||
        boot_size > expected_whole_size - boot_offset ||
        boot_offset + boot_size != root_offset ||
        root_offset > expected_whole_size ||
        root_size > expected_whole_size - root_offset ||
        root_offset + root_size != easyroms_offset ||
        easyroms_offset > expected_whole_size ||
        easyroms_size != expected_whole_size - easyroms_offset ||
        easyroms_head_size > easyroms_size) {
        fail_data("audit layout arguments are inconsistent");
    }

    verify_probe_source(probe_path, probe_size, probe_sha);
    install_interrupt_handlers();
    claim_whole_disk(device_path);
    int target = open(device_path, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (target < 0) {
        fail_errno("open raw audit target");
    }
    struct stat target_before;
    if (fstat(target, &target_before) != 0 ||
        !S_ISCHR(target_before.st_mode)) {
        fail_data("raw audit target is not a character device");
    }
    uint32_t block_size = verify_raw_geometry(target, expected_whole_size);
    require_no_target_mounts(expected_identifier);

    char prefix_actual[SHA256_HEX_SIZE];
    char boot_actual[SHA256_HEX_SIZE];
    char root_actual[SHA256_HEX_SIZE];
    char easyroms_actual[SHA256_HEX_SIZE];
    char easyroms_head_actual[SHA256_HEX_SIZE];
    char quick_immutable_actual[SHA256_HEX_SIZE];
    char repeated[SHA256_HEX_SIZE];
    require_expected_hash(
        target, 0, prefix_size, prefix_sha, "prefix", prefix_actual
    );
    hash_range(
        target,
        boot_offset,
        boot_size,
        boot_actual,
        "audit-read",
        "boot"
    );
    require_expected_hash(
        target, root_offset, root_size, root_sha, "root", root_actual
    );
    int verify_full_easyroms = is_lower_hex_sha256(easyroms_sha);
    if (verify_full_easyroms) {
        require_expected_hash(
            target,
            easyroms_offset,
            easyroms_size,
            easyroms_sha,
            "easyroms",
            easyroms_actual
        );
    } else {
        strcpy(easyroms_actual, "not-verified");
    }
    if (is_lower_hex_sha256(easyroms_head_sha) && !audit_is_quick) {
        require_expected_hash(
            target,
            easyroms_offset,
            easyroms_head_size,
            easyroms_head_sha,
            "easyroms-head",
            easyroms_head_actual
        );
    } else {
        hash_range(
            target,
            easyroms_offset,
            easyroms_head_size,
            easyroms_head_actual,
            "audit-read",
            "easyroms-head"
        );
    }
    if (audit_is_quick) {
        require_quick_immutable_hash(
            target,
            easyroms_offset,
            easyroms_size,
            block_size,
            quick_immutable_sha,
            quick_immutable_actual,
            "audit-read"
        );
    } else {
        strcpy(quick_immutable_actual, "not-verified");
    }

    create_snapshot(
        target,
        boot_offset,
        boot_size,
        boot_size,
        boot_snapshot,
        boot_actual,
        "boot"
    );
    create_snapshot(
        target,
        easyroms_offset,
        easyroms_head_size,
        easyroms_size,
        easyroms_snapshot,
        easyroms_head_actual,
        "easyroms"
    );
    run_filesystem_probe(
        probe_path,
        expected_identifier,
        boot_snapshot,
        easyroms_snapshot,
        easyroms_size,
        easyroms_policy,
        boot_uuid,
        easyroms_uuid,
        receipt_dir,
        probe_result
    );

    require_expected_hash(
        target, boot_offset, boot_size, boot_actual, "boot-repeat", repeated
    );
    if (!audit_is_quick) {
        require_expected_hash(
            target, root_offset, root_size, root_sha, "root-repeat", repeated
        );
    }
    require_expected_hash(
        target, 0, prefix_size, prefix_sha, "prefix-repeat", repeated
    );
    if (verify_full_easyroms) {
        require_expected_hash(
            target,
            easyroms_offset,
            easyroms_size,
            easyroms_sha,
            "easyroms-repeat",
            repeated
        );
    }
    require_expected_hash(
        target,
        easyroms_offset,
        easyroms_head_size,
        easyroms_head_actual,
        "easyroms-head-repeat",
        repeated
    );
    if (audit_is_quick) {
        require_quick_immutable_hash(
            target,
            easyroms_offset,
            easyroms_size,
            block_size,
            quick_immutable_sha,
            repeated,
            "audit-repeat"
        );
    }
    if (verify_raw_geometry(target, expected_whole_size) != block_size) {
        fail_data("raw audit geometry changed");
    }
    require_no_target_mounts(expected_identifier);
    verify_raw_identity(target, device_path, &target_before);
    if (stop_requested) {
        fail_data("audit stopped before eject");
    }
    if (close(target) != 0) {
        fail_errno("close raw audit target");
    }
    eject_claimed_disk(device_path);
    if (stop_requested) {
        fail_data("audit stopped during eject");
    }
    int p1_matches = strcmp(boot_actual, boot_image_sha) == 0;
    uint64_t raw_bytes_read =
        prefix_size * 2 +
        boot_size * 3 +
        root_size * (audit_is_quick ? 1 : 2) +
        easyroms_head_size * 3 +
        (audit_is_quick ? 2ULL * (
            QUICK_EXFAT_BOOT_SIZE +
            QUICK_EXFAT_FAT_PREFIX_SIZE +
            QUICK_EXFAT_ROOT_PREFIX_SIZE +
            QUICK_EXFAT_PAYLOAD_SIZE
        ) : 0ULL) +
        (audit_is_full ? easyroms_size * 2 : 0);
    printf(
        "R46H_MEDIA_AUDIT result=pass device=%s whole_size=%llu "
        "block_size=%u prefix_sha256=%s p1_sha256=%s "
        "p1_matches_write_image=%s p2_sha256=%s p3_sha256=%s p3_head_sha256=%s "
        "p3_quick_immutable_sha256=%s "
        "boot_uuid=%s easyroms_uuid=%s audit_level=%s p3_full_verified=%s "
        "raw_bytes_read=%llu card_state=ejected\n",
        device_path,
        (unsigned long long)expected_whole_size,
        block_size,
        prefix_actual,
        boot_actual,
        p1_matches ? "true" : "false",
        root_actual,
        easyroms_actual,
        easyroms_head_actual,
        quick_immutable_actual,
        boot_uuid,
        easyroms_uuid,
        audit_level,
        audit_is_full ? "true" : "false",
        (unsigned long long)raw_bytes_read
    );
    return 0;
}

static void usage(void) {
    fprintf(stderr,
        "usage: r46h-card-layout-provision RAW WHOLE_SIZE PREFIX PREFIX_SIZE PREFIX_SHA "
        "BOOT BOOT_OFFSET BOOT_SIZE BOOT_SHA ROOT ROOT_OFFSET ROOT_SIZE ROOT_SHA "
        "EASYROMS EASYROMS_OFFSET "
        "EASYROMS_SIZE EASYROMS_DATA_SIZE EASYROMS_DATA_SHA EASYROMS_ZERO_SIZE "
        "TARGET_PREFIX_BEFORE_SHA\n");
    exit(64);
}

int main(int argc, char **argv) {
    setvbuf(stdout, NULL, _IOLBF, 0);
    if (atexit(release_disk_claim) != 0) {
        fail_data("register Disk Arbitration cleanup");
    }
    if (argc >= 2 && strcmp(argv[1], "audit") == 0) {
        return run_media_audit(argc, argv);
    }
    if (argc != 21) {
        usage();
    }

    const char *device_path = argv[1];
    uint64_t expected_whole_size = parse_u64(argv[2], "whole size");
    uint64_t boot_offset = parse_u64(argv[7], "BOOT offset");
    uint64_t root_offset = parse_u64(argv[11], "root offset");
    uint64_t easyroms_offset = parse_u64(argv[15], "EASYROMS offset");
    uint64_t easyroms_zero_size = parse_u64_or_zero(
        argv[19], "EASYROMS zero size"
    );
    const char *expected_target_prefix_before_hash = argv[20];

    struct source prefix = {
        .label = "prefix",
        .path = argv[3],
        .expected_hash = argv[5],
        .expected_size = parse_u64(argv[4], "prefix size"),
        .hash_size = parse_u64(argv[4], "prefix size"),
        .descriptor = -1,
    };
    struct source boot = {
        .label = "boot",
        .path = argv[6],
        .expected_hash = argv[9],
        .expected_size = parse_u64(argv[8], "BOOT size"),
        .hash_size = parse_u64(argv[8], "BOOT size"),
        .descriptor = -1,
    };
    struct source root = {
        .label = "root",
        .path = argv[10],
        .expected_hash = argv[13],
        .expected_size = parse_u64(argv[12], "root size"),
        .hash_size = parse_u64(argv[12], "root size"),
        .descriptor = -1,
    };
    struct source easyroms = {
        .label = "easyroms-metadata",
        .path = argv[14],
        .expected_hash = argv[18],
        .expected_size = parse_u64(argv[16], "EASYROMS size"),
        .hash_size = parse_u64(argv[17], "EASYROMS data size"),
        .descriptor = -1,
    };

    if (strncmp(device_path, "/dev/rdisk", 10) != 0 ||
        !is_lower_hex_sha256(expected_target_prefix_before_hash) ||
        prefix.expected_size != boot_offset ||
        boot_offset > expected_whole_size ||
        boot.expected_size > expected_whole_size - boot_offset ||
        boot_offset + boot.expected_size != root_offset ||
        root_offset > expected_whole_size ||
        root.expected_size > expected_whole_size - root_offset ||
        root_offset + root.expected_size != easyroms_offset ||
        easyroms_offset > expected_whole_size ||
        easyroms.expected_size != expected_whole_size - easyroms_offset ||
        !((easyroms_zero_size == 0 &&
           easyroms.hash_size == easyroms.expected_size) ||
          (easyroms_zero_size >= easyroms.hash_size &&
           easyroms_zero_size <= easyroms.expected_size)) ||
        prefix.expected_size <= 512 ||
        prefix.expected_size % 512 != 0 ||
        boot_offset % 512 != 0 ||
        boot.expected_size % 512 != 0 ||
        root_offset % 512 != 0 ||
        root.expected_size % 512 != 0 ||
        easyroms_offset % 512 != 0 ||
        easyroms.expected_size % 512 != 0 ||
        easyroms.hash_size % 512 != 0 ||
        easyroms_zero_size % 512 != 0) {
        fail_data("layout arguments are inconsistent");
    }

    open_source(&prefix);
    open_source(&boot);
    open_source(&root);
    open_source(&easyroms);

    install_interrupt_handlers();

    claim_whole_disk(device_path);
    const char *expected_identifier = device_path + strlen("/dev/r");
    require_no_target_mounts(expected_identifier);

    int target = open(device_path, O_RDWR | O_NOFOLLOW);
    if (target < 0) {
        fail_errno("open raw target");
    }

    struct stat target_before;
    if (fstat(target, &target_before) != 0 || !S_ISCHR(target_before.st_mode)) {
        fail_data("raw target is not a character device");
    }
    uint32_t block_size = verify_raw_geometry(target, expected_whole_size);
    if (ioctl(target, DKIOCSYNCHRONIZECACHE) != 0) {
        fail_errno("preflight DKIOCSYNCHRONIZECACHE");
    }
    char target_prefix_before_hash[SHA256_HEX_SIZE];
    hash_range(
        target,
        0,
        prefix.expected_size,
        target_prefix_before_hash,
        "target-hash-before",
        "prefix"
    );
    if (strcmp(target_prefix_before_hash, expected_target_prefix_before_hash) != 0) {
        fail_data("raw target changed after wrapper preflight");
    }
    if (stop_requested) {
        fail_data("stopped before first write");
    }

    if (signal(SIGINT, SIG_IGN) == SIG_ERR ||
        signal(SIGTERM, SIG_IGN) == SIG_ERR ||
        signal(SIGHUP, SIG_IGN) == SIG_ERR ||
        signal(SIGPIPE, SIG_IGN) == SIG_ERR) {
        fail_errno("ignore write-phase signals");
    }
    if (stop_requested) {
        fail_data("stopped at write-phase transition");
    }
    printf("R46H_LAYOUT stage=write-started safe_to_boot=no whole_size=%llu block_size=%u\n",
        (unsigned long long)expected_whole_size,
        block_size);

    write_source(&boot, target, boot_offset);
    write_source(&root, target, root_offset);
    if (easyroms_zero_size > 0) {
        zero_range(target, easyroms_offset, easyroms_zero_size);
    }
    write_source(&easyroms, target, easyroms_offset);
    synchronize_target(target, "partition-payloads-before-prefix");

    write_source_range(
        &prefix,
        target,
        512,
        512,
        prefix.hash_size - 512,
        "prefix-tail"
    );
    synchronize_target(target, "prefix-tail-before-mbr");

    write_source_range(&prefix, target, 0, 0, 512, "mbr-sector-last");
    synchronize_target(target, "mbr-commit");

    verify_target_hash(target, &prefix, 0);
    verify_target_hash(target, &boot, boot_offset);
    verify_target_hash(target, &root, root_offset);
    verify_target_hash(target, &easyroms, easyroms_offset);
    if (easyroms_zero_size > easyroms.hash_size) {
        verify_zero_range(
            target,
            easyroms_offset + easyroms.hash_size,
            easyroms_zero_size - easyroms.hash_size
        );
    }
    verify_source_unchanged(&prefix);
    verify_source_unchanged(&boot);
    verify_source_unchanged(&root);
    verify_source_unchanged(&easyroms);

    require_no_target_mounts(expected_identifier);
    verify_raw_identity(target, device_path, &target_before);

    if (close(target) != 0) {
        fail_errno("close raw target");
    }
    close(prefix.descriptor);
    close(boot.descriptor);
    close(root.descriptor);
    close(easyroms.descriptor);
    eject_claimed_disk(device_path);

    printf("R46H_LAYOUT result=pass state=MEDIA_WRITE_COMPLETE safe_to_boot=no "
           "card_state=ejected next=reinsert-and-audit\n");
    return 0;
}
