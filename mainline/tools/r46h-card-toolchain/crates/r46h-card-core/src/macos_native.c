#include <CoreFoundation/CoreFoundation.h>
#include <DiskArbitration/DiskArbitration.h>
#include <errno.h>
#include <fcntl.h>
#include <IOKit/IOKitLib.h>
#include <IOKit/storage/IOMedia.h>
#include <limits.h>
#include <pthread.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/disk.h>
#include <sys/ioctl.h>
#include <sys/mount.h>
#include <sys/stat.h>
#include <unistd.h>

#ifndef DKIOCGETBASE
#define DKIOCGETBASE _IOR('d', 73, uint64_t)
#endif

#define R46H_PATH_CAPACITY 128
#define R46H_TEXT_CAPACITY 128

struct r46h_macos_candidate {
    char attachment_id[R46H_TEXT_CAPACITY];
    char physical_store_id[R46H_TEXT_CAPACITY];
    char display_path[R46H_PATH_CAPACITY];
    char raw_path[R46H_PATH_CAPACITY];
    char transport[R46H_TEXT_CAPACITY];
    uint64_t registry_entry_id;
    uint64_t physical_registry_entry_id;
    uint64_t device_number;
    uint64_t size;
    uint32_t sector_size;
    uint8_t whole;
    uint8_t internal;
    uint8_t removable;
    uint8_t ejectable;
    uint8_t writable;
    uint8_t system_disk;
};

struct r46h_macos_partition {
    uint32_t number;
    uint64_t offset;
    uint64_t size;
    char filesystem[R46H_TEXT_CAPACITY];
    char volume_uuid[R46H_TEXT_CAPACITY];
};

struct r46h_da_result {
    int completed;
    int denied;
    int abandoned;
    int unclaim_if_abandoned;
    int32_t status;
};

struct r46h_macos_session {
    DASessionRef da_session;
    DADiskRef disk;
    CFRunLoopRef run_loop;
    int raw_fd;
    dev_t device_number;
    uint64_t registry_entry_id;
    uint64_t size;
    uint32_t sector_size;
    char display_path[R46H_PATH_CAPACITY];
    char raw_path[R46H_PATH_CAPACITY];
    int claimed;
    int unmounted;
    int ejected;
    struct r46h_da_result *eject_result;
    int eject_pending;
    int raw_close_error;
    int signals_installed;
    struct sigaction old_hup;
    struct sigaction old_int;
    struct sigaction old_term;
};

int r46h_macos_discover(
    struct r46h_macos_candidate *candidates,
    size_t capacity,
    size_t *count
);
int r46h_macos_path_whole_registry_id(const char *path, uint64_t *registry_entry_id);
int r46h_macos_path_whole_bsd_name(const char *path, char *bsd_name, size_t capacity);
struct r46h_macos_session *r46h_macos_claim_readonly(
    const struct r46h_macos_candidate *expected
);
int r46h_macos_read_at(
    struct r46h_macos_session *session,
    uint64_t offset,
    void *buffer,
    size_t length
);
int r46h_macos_partition_observation(
    struct r46h_macos_session *session,
    const struct r46h_macos_candidate *candidate,
    uint32_t partition_number,
    struct r46h_macos_partition *observation
);
int r46h_macos_eject(struct r46h_macos_session *session);
int r46h_macos_revalidate(struct r46h_macos_session *session);
void r46h_macos_session_free(struct r46h_macos_session *session);

static pthread_mutex_t r46h_signal_lock = PTHREAD_MUTEX_INITIALIZER;
static int r46h_signal_session_active = 0;
static volatile sig_atomic_t r46h_stop_signal = 0;

static void request_stop(int signal_number) {
    r46h_stop_signal = signal_number;
}

static int install_signal_handlers(struct r46h_macos_session *session) {
    if (pthread_mutex_lock(&r46h_signal_lock) != 0) {
        errno = EBUSY;
        return -1;
    }
    if (r46h_signal_session_active) {
        pthread_mutex_unlock(&r46h_signal_lock);
        errno = EBUSY;
        return -1;
    }
    r46h_signal_session_active = 1;
    pthread_mutex_unlock(&r46h_signal_lock);

    struct sigaction action;
    memset(&action, 0, sizeof(action));
    action.sa_handler = request_stop;
    sigemptyset(&action.sa_mask);
    r46h_stop_signal = 0;
    if (sigaction(SIGHUP, &action, &session->old_hup) != 0) {
        goto fail;
    }
    if (sigaction(SIGINT, &action, &session->old_int) != 0) {
        sigaction(SIGHUP, &session->old_hup, NULL);
        goto fail;
    }
    if (sigaction(SIGTERM, &action, &session->old_term) != 0) {
        sigaction(SIGINT, &session->old_int, NULL);
        sigaction(SIGHUP, &session->old_hup, NULL);
        goto fail;
    }
    session->signals_installed = 1;
    return 0;

fail:
    pthread_mutex_lock(&r46h_signal_lock);
    r46h_signal_session_active = 0;
    pthread_mutex_unlock(&r46h_signal_lock);
    return -1;
}

static void restore_signal_handlers(struct r46h_macos_session *session) {
    if (session == NULL || !session->signals_installed) {
        return;
    }
    sigaction(SIGTERM, &session->old_term, NULL);
    sigaction(SIGINT, &session->old_int, NULL);
    sigaction(SIGHUP, &session->old_hup, NULL);
    session->signals_installed = 0;
    r46h_stop_signal = 0;
    pthread_mutex_lock(&r46h_signal_lock);
    r46h_signal_session_active = 0;
    pthread_mutex_unlock(&r46h_signal_lock);
}

static int stop_requested(void) {
    if (r46h_stop_signal == 0) {
        return 0;
    }
    errno = ECANCELED;
    return 1;
}

static int finish_signal_window(struct r46h_macos_session *session) {
    sigset_t blocked;
    sigset_t previous;
    sigset_t pending;
    sigemptyset(&blocked);
    sigaddset(&blocked, SIGHUP);
    sigaddset(&blocked, SIGINT);
    sigaddset(&blocked, SIGTERM);
    if (pthread_sigmask(SIG_BLOCK, &blocked, &previous) != 0) {
        errno = EBUSY;
        return -1;
    }
    int cancelled = r46h_stop_signal != 0;
    if (sigpending(&pending) == 0 &&
        (sigismember(&pending, SIGHUP) || sigismember(&pending, SIGINT) ||
         sigismember(&pending, SIGTERM))) {
        cancelled = 1;
    }
    restore_signal_handlers(session);
    int mask_status = pthread_sigmask(SIG_SETMASK, &previous, NULL);
    if (cancelled) {
        errno = ECANCELED;
        return -1;
    }
    if (mask_status != 0) {
        errno = EBUSY;
        return -1;
    }
    return 0;
}

static int copy_text(char *destination, size_t capacity, const char *source) {
    size_t length = strlen(source);
    if (length == 0 || length >= capacity) {
        return -1;
    }
    memcpy(destination, source, length + 1);
    return 0;
}

static int make_device_paths(
    const char *bsd_name,
    char block[R46H_PATH_CAPACITY],
    char raw[R46H_PATH_CAPACITY]
) {
    if (bsd_name == NULL || strncmp(bsd_name, "disk", 4) != 0) {
        return -1;
    }
    for (const char *cursor = bsd_name + 4; *cursor != '\0'; cursor++) {
        if (*cursor < '0' || *cursor > '9') {
            return -1;
        }
    }
    int block_length = snprintf(block, R46H_PATH_CAPACITY, "/dev/%s", bsd_name);
    int raw_length = snprintf(raw, R46H_PATH_CAPACITY, "/dev/r%s", bsd_name);
    return block_length > 0 && block_length < R46H_PATH_CAPACITY &&
                   raw_length > 0 && raw_length < R46H_PATH_CAPACITY
               ? 0
               : -1;
}

static int cf_boolean(CFDictionaryRef dictionary, CFStringRef key, int *value) {
    CFTypeRef item = CFDictionaryGetValue(dictionary, key);
    if (item == NULL || CFGetTypeID(item) != CFBooleanGetTypeID()) {
        return -1;
    }
    *value = CFBooleanGetValue(item) ? 1 : 0;
    return 0;
}

static int cf_u64(CFDictionaryRef dictionary, CFStringRef key, uint64_t *value) {
    CFTypeRef item = CFDictionaryGetValue(dictionary, key);
    if (item == NULL || CFGetTypeID(item) != CFNumberGetTypeID()) {
        return -1;
    }
    return CFNumberGetValue((CFNumberRef)item, kCFNumberSInt64Type, value) ? 0 : -1;
}

static int cf_u32(CFDictionaryRef dictionary, CFStringRef key, uint32_t *value) {
    uint64_t wide = 0;
    if (cf_u64(dictionary, key, &wide) != 0 || wide > UINT32_MAX) {
        return -1;
    }
    *value = (uint32_t)wide;
    return 0;
}

static int cf_string(
    CFDictionaryRef dictionary,
    CFStringRef key,
    char *value,
    size_t capacity,
    int optional
) {
    if (capacity > (size_t)LONG_MAX) {
        return -1;
    }
    CFTypeRef item = CFDictionaryGetValue(dictionary, key);
    if (item == NULL && optional) {
        value[0] = '\0';
        return 0;
    }
    if (item == NULL || CFGetTypeID(item) != CFStringGetTypeID()) {
        return -1;
    }
    return CFStringGetCString(
               (CFStringRef)item,
               value,
               (CFIndex)capacity,
               kCFStringEncodingUTF8
           )
               ? 0
               : -1;
}

static int cf_uuid(
    CFDictionaryRef dictionary,
    CFStringRef key,
    char *value,
    size_t capacity,
    int optional
) {
    if (capacity > (size_t)LONG_MAX) {
        return -1;
    }
    CFTypeRef item = CFDictionaryGetValue(dictionary, key);
    if (item == NULL && optional) {
        value[0] = '\0';
        return 0;
    }
    if (item == NULL || CFGetTypeID(item) != CFUUIDGetTypeID()) {
        return -1;
    }
    CFStringRef string = CFUUIDCreateString(kCFAllocatorDefault, (CFUUIDRef)item);
    if (string == NULL) {
        return -1;
    }
    int result = CFStringGetCString(
                     string,
                     value,
                     (CFIndex)capacity,
                     kCFStringEncodingUTF8
                 )
        ? 0
        : -1;
    CFRelease(string);
    return result;
}

static int media_registry_id(DADiskRef disk, uint64_t *registry_entry_id) {
    io_service_t media = DADiskCopyIOMedia(disk);
    if (media == IO_OBJECT_NULL) {
        return -1;
    }
    kern_return_t status = IORegistryEntryGetRegistryEntryID(media, registry_entry_id);
    IOObjectRelease(media);
    return status == KERN_SUCCESS && *registry_entry_id != 0 ? 0 : -1;
}

static int media_top_store_registry_id(DADiskRef disk, uint64_t *registry_entry_id) {
    io_registry_entry_t current = DADiskCopyIOMedia(disk);
    if (current == IO_OBJECT_NULL) {
        return -1;
    }
    uint64_t selected = 0;
    if (IORegistryEntryGetRegistryEntryID(current, &selected) != KERN_SUCCESS || selected == 0) {
        IOObjectRelease(current);
        return -1;
    }
    for (;;) {
        io_registry_entry_t parent = IO_OBJECT_NULL;
        kern_return_t status = IORegistryEntryGetParentEntry(
            current,
            kIOServicePlane,
            &parent
        );
        if (status != KERN_SUCCESS || parent == IO_OBJECT_NULL) {
            break;
        }
        if (IOObjectConformsTo(parent, kIOMediaClass)) {
            uint64_t parent_id = 0;
            if (IORegistryEntryGetRegistryEntryID(parent, &parent_id) != KERN_SUCCESS ||
                parent_id == 0) {
                IOObjectRelease(parent);
                IOObjectRelease(current);
                return -1;
            }
            selected = parent_id;
        }
        IOObjectRelease(current);
        current = parent;
    }
    IOObjectRelease(current);
    *registry_entry_id = selected;
    return 0;
}

static int valid_mounted_device_path(const char *path) {
    const char prefix[] = "/dev/disk";
    if (strncmp(path, prefix, sizeof(prefix) - 1) != 0) {
        return 0;
    }
    const char *cursor = path + sizeof(prefix) - 1;
    for (;;) {
        const char *digits = cursor;
        while (*cursor >= '0' && *cursor <= '9') {
            cursor++;
        }
        if (cursor == digits) {
            return 0;
        }
        if (*cursor == '\0') {
            return 1;
        }
        if (*cursor != 's') {
            return 0;
        }
        cursor++;
    }
}

static DADiskRef path_whole_disk(DASessionRef session, const char *path) {
    struct statfs filesystem;
    if (statfs(path, &filesystem) != 0) {
        return NULL;
    }
    if (!valid_mounted_device_path(filesystem.f_mntfromname)) {
        errno = ENODEV;
        return NULL;
    }
    DADiskRef volume = DADiskCreateFromBSDName(
        kCFAllocatorDefault,
        session,
        filesystem.f_mntfromname
    );
    if (volume == NULL) {
        errno = ENODEV;
        return NULL;
    }
    DADiskRef whole = DADiskCopyWholeDisk(volume);
    CFRelease(volume);
    if (whole == NULL) {
        errno = ENODEV;
    }
    return whole;
}

static int volume_whole_registry_id(
    DASessionRef session,
    const char *path,
    uint64_t *registry_entry_id
) {
    DADiskRef whole = path_whole_disk(session, path);
    if (whole == NULL) {
        return -1;
    }
    int result = media_top_store_registry_id(whole, registry_entry_id);
    CFRelease(whole);
    return result;
}

static int volume_whole_bsd_name(
    DASessionRef session,
    const char *path,
    char *bsd_name,
    size_t capacity
) {
    DADiskRef whole = path_whole_disk(session, path);
    if (whole == NULL) {
        return -1;
    }
    const char *name = DADiskGetBSDName(whole);
    int result = name == NULL ? -1 : copy_text(bsd_name, capacity, name);
    CFRelease(whole);
    return result;
}

static int candidate_from_disk(DADiskRef disk, struct r46h_macos_candidate *candidate) {
    CFDictionaryRef description = DADiskCopyDescription(disk);
    if (description == NULL) {
        return -1;
    }
    char bsd_name[R46H_TEXT_CAPACITY] = {0};
    int whole = 0;
    int internal = 0;
    int removable = 0;
    int ejectable = 0;
    int writable = 0;
    int result = cf_string(
                     description,
                     kDADiskDescriptionMediaBSDNameKey,
                     bsd_name,
                     sizeof(bsd_name),
                     0
                 ) ||
        cf_u64(description, kDADiskDescriptionMediaSizeKey, &candidate->size) ||
        cf_u32(description, kDADiskDescriptionMediaBlockSizeKey, &candidate->sector_size) ||
        cf_boolean(description, kDADiskDescriptionMediaWholeKey, &whole) ||
        cf_boolean(description, kDADiskDescriptionDeviceInternalKey, &internal) ||
        cf_boolean(description, kDADiskDescriptionMediaRemovableKey, &removable) ||
        cf_boolean(description, kDADiskDescriptionMediaEjectableKey, &ejectable) ||
        cf_boolean(description, kDADiskDescriptionMediaWritableKey, &writable) ||
        cf_string(
            description,
            kDADiskDescriptionDeviceProtocolKey,
            candidate->transport,
            sizeof(candidate->transport),
            0
        ) ||
        make_device_paths(bsd_name, candidate->display_path, candidate->raw_path) ||
        media_registry_id(disk, &candidate->registry_entry_id);
    CFRelease(description);
    if (result != 0 || candidate->sector_size == 0 || candidate->size == 0) {
        return -1;
    }
    if (!whole || internal || !removable || !ejectable ||
        strcasecmp(candidate->transport, "USB") != 0) {
        return 1;
    }
    struct stat metadata;
    if (lstat(candidate->display_path, &metadata) != 0 || !S_ISBLK(metadata.st_mode)) {
        return -1;
    }
    candidate->device_number = (uint64_t)metadata.st_rdev;
    candidate->whole = (uint8_t)whole;
    candidate->internal = (uint8_t)internal;
    candidate->removable = (uint8_t)removable;
    candidate->ejectable = (uint8_t)ejectable;
    candidate->writable = (uint8_t)writable;
    if (media_top_store_registry_id(disk, &candidate->physical_registry_entry_id) != 0 ||
        snprintf(
            candidate->attachment_id,
            sizeof(candidate->attachment_id),
            "macos-iomedia-v1:%016llx:%016llx",
            (unsigned long long)candidate->registry_entry_id,
            (unsigned long long)candidate->device_number
        ) >= (int)sizeof(candidate->attachment_id) ||
        snprintf(
            candidate->physical_store_id,
            sizeof(candidate->physical_store_id),
            "macos-iomedia-v1:%016llx",
            (unsigned long long)candidate->physical_registry_entry_id
        ) >= (int)sizeof(candidate->physical_store_id)) {
        return -1;
    }
    return 0;
}

static void da_completed(DADiskRef disk, DADissenterRef dissenter, void *context) {
    (void)disk;
    struct r46h_da_result *result = context;
    if (result->abandoned) {
        if (result->unclaim_if_abandoned && DADiskIsClaimed(disk)) {
            DADiskUnclaim(disk);
        }
        free(result);
        return;
    }
    if (dissenter != NULL) {
        result->denied = 1;
        result->status = (int32_t)DADissenterGetStatus(dissenter);
    }
    result->completed = 1;
}

static void free_da_result(struct r46h_da_result *result) {
    if (result == NULL) {
        return;
    }
    free(result);
}

static DADissenterRef deny_release(DADiskRef disk, void *context) {
    (void)disk;
    (void)context;
    return DADissenterCreate(
        kCFAllocatorDefault,
        kDAReturnBusy,
        CFSTR("R46H read-only media audit is active")
    );
}

static int wait_for_da(struct r46h_da_result *result, unsigned int tenths) {
    for (unsigned int attempt = 0; attempt < tenths && !result->completed; attempt++) {
        CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.1, true);
    }
    if (!result->completed) {
        result->abandoned = 1;
        errno = ETIMEDOUT;
        return -1;
    }
    if (result->denied) {
        errno = EBUSY;
        return -1;
    }
    return 0;
}

static int wait_for_retryable_da(struct r46h_da_result *result, unsigned int tenths) {
    for (unsigned int attempt = 0; attempt < tenths && !result->completed; attempt++) {
        CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.1, true);
    }
    if (!result->completed) {
        errno = ETIMEDOUT;
        return -1;
    }
    if (result->denied) {
        errno = EBUSY;
        return -1;
    }
    return 0;
}

static int require_unmounted(const char *whole_device_path) {
    struct statfs *mounts = NULL;
    int count = getmntinfo(&mounts, MNT_NOWAIT);
    if (count < 0 || (count > 0 && mounts == NULL)) {
        errno = EIO;
        return -1;
    }
    size_t prefix_length = strlen(whole_device_path);
    for (int index = 0; index < count; index++) {
        const char *source = mounts[index].f_mntfromname;
        if (strcmp(source, whole_device_path) == 0) {
            errno = EBUSY;
            return -1;
        }
        if (strncmp(source, whole_device_path, prefix_length) == 0) {
            const char *cursor = source + prefix_length;
            int valid_partition_path = 0;
            while (*cursor == 's') {
                cursor++;
                const char *digits = cursor;
                while (*cursor >= '0' && *cursor <= '9') {
                    cursor++;
                }
                if (cursor == digits) {
                    valid_partition_path = 0;
                    break;
                }
                valid_partition_path = 1;
            }
            if (valid_partition_path && *cursor == '\0') {
                errno = EBUSY;
                return -1;
            }
        }
    }
    return 0;
}

static void release_session(struct r46h_macos_session *session) {
    if (session == NULL) {
        return;
    }
    int saved_error = errno;
    if (session->raw_fd >= 0) {
        close(session->raw_fd);
        session->raw_fd = -1;
    }
    if (session->eject_result != NULL) {
        if (session->eject_pending && !session->eject_result->completed) {
            session->eject_result->abandoned = 1;
        } else {
            free_da_result(session->eject_result);
        }
        session->eject_result = NULL;
        session->eject_pending = 0;
    }
    if (session->disk != NULL && DADiskIsClaimed(session->disk)) {
        DADiskUnclaim(session->disk);
    }
    if (session->da_session != NULL && session->run_loop != NULL) {
        DASessionUnscheduleFromRunLoop(
            session->da_session,
            session->run_loop,
            kCFRunLoopDefaultMode
        );
    }
    if (session->disk != NULL) {
        CFRelease(session->disk);
    }
    if (session->da_session != NULL) {
        CFRelease(session->da_session);
    }
    restore_signal_handlers(session);
    free(session);
    errno = saved_error;
}

static int eject_session(struct r46h_macos_session *session);

static void fail_claim_cleanup(struct r46h_macos_session *session, int primary_error) {
    if (session == NULL) {
        return;
    }
    int cleanup_error = 0;
    if (session->unmounted && session->eject_result != NULL) {
        for (unsigned int attempt = 0; attempt < 2 && !session->ejected; attempt++) {
            if (eject_session(session) == 0) {
                break;
            }
            cleanup_error = errno == 0 ? EIO : errno;
        }
    }
    release_session(session);
    errno = cleanup_error == 0 ? primary_error : cleanup_error;
}

int r46h_macos_discover(
    struct r46h_macos_candidate *candidates,
    size_t capacity,
    size_t *count
) {
    if (candidates == NULL || count == NULL || capacity == 0) {
        errno = EINVAL;
        return -1;
    }
    *count = 0;
    DASessionRef da_session = DASessionCreate(kCFAllocatorDefault);
    if (da_session == NULL) {
        errno = EIO;
        return -1;
    }
    uint64_t system_registry_entry_id = 0;
    if (volume_whole_registry_id(da_session, "/", &system_registry_entry_id) != 0) {
        CFRelease(da_session);
        errno = EIO;
        return -1;
    }
    CFMutableDictionaryRef matching = IOServiceMatching(kIOMediaClass);
    io_iterator_t iterator = IO_OBJECT_NULL;
    if (matching == NULL || IOServiceGetMatchingServices(kIOMainPortDefault, matching, &iterator) !=
                                KERN_SUCCESS) {
        CFRelease(da_session);
        errno = EIO;
        return -1;
    }
    int status = 0;
    io_service_t media;
    while ((media = IOIteratorNext(iterator)) != IO_OBJECT_NULL) {
        DADiskRef disk = DADiskCreateFromIOMedia(kCFAllocatorDefault, da_session, media);
        IOObjectRelease(media);
        if (disk == NULL) {
            continue;
        }
        struct r46h_macos_candidate candidate = {0};
        if (candidate_from_disk(disk, &candidate) == 0 && candidate.whole) {
            candidate.system_disk =
                candidate.physical_registry_entry_id == system_registry_entry_id ? 1 : 0;
            if (*count >= capacity) {
                status = -1;
                errno = EOVERFLOW;
                CFRelease(disk);
                break;
            }
            candidates[*count] = candidate;
            (*count)++;
        }
        CFRelease(disk);
    }
    IOObjectRelease(iterator);
    CFRelease(da_session);
    return status;
}

int r46h_macos_path_whole_registry_id(const char *path, uint64_t *registry_entry_id) {
    if (path == NULL || registry_entry_id == NULL || path[0] != '/') {
        errno = EINVAL;
        return -1;
    }
    DASessionRef session = DASessionCreate(kCFAllocatorDefault);
    if (session == NULL) {
        errno = EIO;
        return -1;
    }
    int result = volume_whole_registry_id(session, path, registry_entry_id);
    CFRelease(session);
    if (result != 0) {
        errno = EIO;
    }
    return result;
}

int r46h_macos_path_whole_bsd_name(const char *path, char *bsd_name, size_t capacity) {
    if (path == NULL || bsd_name == NULL || capacity == 0 || path[0] != '/') {
        errno = EINVAL;
        return -1;
    }
    DASessionRef session = DASessionCreate(kCFAllocatorDefault);
    if (session == NULL) {
        errno = EIO;
        return -1;
    }
    int result = volume_whole_bsd_name(session, path, bsd_name, capacity);
    CFRelease(session);
    if (result != 0) {
        errno = EIO;
    }
    return result;
}

struct r46h_macos_session *r46h_macos_claim_readonly(
    const struct r46h_macos_candidate *expected
) {
    if (expected == NULL) {
        errno = EINVAL;
        return NULL;
    }
    struct r46h_macos_session *session = calloc(1, sizeof(*session));
    if (session == NULL) {
        return NULL;
    }
    session->raw_fd = -1;
    if (install_signal_handlers(session) != 0) {
        release_session(session);
        return NULL;
    }
    session->da_session = DASessionCreate(kCFAllocatorDefault);
    if (session->da_session == NULL) {
        release_session(session);
        errno = EIO;
        return NULL;
    }
    session->disk = DADiskCreateFromBSDName(
        kCFAllocatorDefault,
        session->da_session,
        expected->display_path
    );
    if (session->disk == NULL) {
        release_session(session);
        errno = ENODEV;
        return NULL;
    }
    struct r46h_macos_candidate actual = {0};
    if (candidate_from_disk(session->disk, &actual) != 0 ||
        strcmp(expected->attachment_id, actual.attachment_id) != 0 ||
        strcmp(expected->physical_store_id, actual.physical_store_id) != 0 ||
        strcmp(expected->display_path, actual.display_path) != 0 || expected->size != actual.size ||
        expected->sector_size != actual.sector_size) {
        release_session(session);
        errno = ESTALE;
        return NULL;
    }
    session->run_loop = CFRunLoopGetCurrent();
    DASessionScheduleWithRunLoop(
        session->da_session,
        session->run_loop,
        kCFRunLoopDefaultMode
    );
    struct r46h_da_result *claim = calloc(1, sizeof(*claim));
    if (claim == NULL) {
        release_session(session);
        return NULL;
    }
    claim->unclaim_if_abandoned = 1;
    DADiskClaim(
        session->disk,
        kDADiskClaimOptionDefault,
        deny_release,
        NULL,
        da_completed,
        claim
    );
    if (wait_for_da(claim, 300) != 0) {
        DADiskUnclaim(session->disk);
        int completed = claim->completed;
        if (completed) {
            free_da_result(claim);
        }
        release_session(session);
        return NULL;
    }
    free_da_result(claim);
    if (!DADiskIsClaimed(session->disk)) {
        release_session(session);
        errno = EBUSY;
        return NULL;
    }
    session->claimed = 1;
    session->device_number = (dev_t)actual.device_number;
    session->registry_entry_id = actual.registry_entry_id;
    session->size = actual.size;
    session->sector_size = actual.sector_size;
    if (copy_text(session->display_path, sizeof(session->display_path), actual.display_path) != 0 ||
        copy_text(session->raw_path, sizeof(session->raw_path), actual.raw_path) != 0) {
        release_session(session);
        errno = EOVERFLOW;
        return NULL;
    }
    session->eject_result = calloc(1, sizeof(*session->eject_result));
    if (session->eject_result == NULL) {
        release_session(session);
        return NULL;
    }
    struct r46h_da_result *unmount = calloc(1, sizeof(*unmount));
    if (unmount == NULL) {
        release_session(session);
        return NULL;
    }
    if (stop_requested()) {
        free_da_result(unmount);
        release_session(session);
        return NULL;
    }
    DADiskUnmount(
        session->disk,
        kDADiskUnmountOptionWhole,
        da_completed,
        unmount
    );
    if (wait_for_da(unmount, 300) != 0) {
        int completed = unmount->completed;
        if (completed) {
            free_da_result(unmount);
        }
        int unmount_error = errno;
        if (require_unmounted(actual.display_path) == 0) {
            session->unmounted = 1;
            fail_claim_cleanup(session, unmount_error);
        } else {
            release_session(session);
            errno = unmount_error;
        }
        return NULL;
    }
    free_da_result(unmount);
    session->unmounted = 1;
    if (stop_requested()) {
        int primary_error = errno == 0 ? ECANCELED : errno;
        fail_claim_cleanup(session, primary_error);
        return NULL;
    }
    if (require_unmounted(actual.display_path) != 0) {
        session->unmounted = 0;
        int primary_error = errno == 0 ? EBUSY : errno;
        release_session(session);
        errno = primary_error;
        return NULL;
    }
    session->raw_fd = open(actual.raw_path, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (session->raw_fd < 0) {
        int primary_error = errno == 0 ? EIO : errno;
        fail_claim_cleanup(session, primary_error);
        return NULL;
    }
    struct stat metadata;
    uint32_t block_size = 0;
    uint64_t block_count = 0;
    uint64_t base = UINT64_MAX;
    if (fstat(session->raw_fd, &metadata) != 0 || !S_ISCHR(metadata.st_mode) ||
        (uint64_t)metadata.st_rdev != actual.device_number ||
        ioctl(session->raw_fd, DKIOCGETBASE, &base) != 0 ||
        ioctl(session->raw_fd, DKIOCGETBLOCKSIZE, &block_size) != 0 ||
        ioctl(session->raw_fd, DKIOCGETBLOCKCOUNT, &block_count) != 0 || base != 0 ||
        block_size != actual.sector_size || block_count > UINT64_MAX / block_size ||
        block_count * block_size != actual.size) {
        fail_claim_cleanup(session, ESTALE);
        return NULL;
    }
    return session;
}

int r46h_macos_read_at(
    struct r46h_macos_session *session,
    uint64_t offset,
    void *buffer,
    size_t length
) {
    if (session == NULL || session->raw_fd < 0 || buffer == NULL ||
        offset > INT64_MAX || length > (size_t)(INT64_MAX - offset)) {
        errno = EINVAL;
        return -1;
    }
    if (stop_requested()) {
        return -1;
    }
    size_t completed = 0;
    while (completed < length) {
        ssize_t count = pread(
            session->raw_fd,
            (unsigned char *)buffer + completed,
            length - completed,
            (off_t)(offset + completed)
        );
        if (count < 0 && errno == EINTR) {
            if (stop_requested()) {
                return -1;
            }
            continue;
        }
        if (count <= 0) {
            if (count == 0) {
                errno = EIO;
            }
            return -1;
        }
        completed += (size_t)count;
    }
    return 0;
}

static int revalidate_session(
    struct r46h_macos_session *session,
    int honor_stop,
    int require_raw_geometry
) {
    if (session == NULL || session->raw_fd < 0 || !session->claimed ||
        session->disk == NULL || !DADiskIsClaimed(session->disk)) {
        errno = EINVAL;
        return -1;
    }
    if (honor_stop && stop_requested()) {
        return -1;
    }
    struct stat metadata;
    uint64_t registry_entry_id = 0;
    uint64_t base = UINT64_MAX;
    uint64_t block_count = 0;
    uint32_t block_size = 0;
    if (fstat(session->raw_fd, &metadata) != 0) {
        return -1;
    }
    if (!S_ISCHR(metadata.st_mode) || metadata.st_rdev != session->device_number) {
        errno = ESTALE;
        return -1;
    }
    if (media_registry_id(session->disk, &registry_entry_id) != 0) {
        errno = EIO;
        return -1;
    }
    if (registry_entry_id != session->registry_entry_id) {
        errno = ESTALE;
        return -1;
    }
    if (require_raw_geometry) {
        if (ioctl(session->raw_fd, DKIOCGETBASE, &base) != 0 ||
            ioctl(session->raw_fd, DKIOCGETBLOCKSIZE, &block_size) != 0 ||
            ioctl(session->raw_fd, DKIOCGETBLOCKCOUNT, &block_count) != 0) {
            return -1;
        }
        if (base != 0 || block_size != session->sector_size ||
            block_count > UINT64_MAX / block_size || block_count * block_size != session->size) {
            errno = ESTALE;
            return -1;
        }
    }
    if (require_unmounted(session->display_path) != 0) {
        return -1;
    }
    return 0;
}

static int revalidate_eject_identity(struct r46h_macos_session *session) {
    if (session == NULL || session->disk == NULL || !session->unmounted) {
        errno = EINVAL;
        return -1;
    }
    uint64_t registry_entry_id = 0;
    if (media_registry_id(session->disk, &registry_entry_id) != 0) {
        errno = EIO;
        return -1;
    }
    if (registry_entry_id != session->registry_entry_id) {
        errno = ESTALE;
        return -1;
    }
    struct stat metadata;
    if (lstat(session->display_path, &metadata) != 0) {
        if (errno == 0) {
            errno = ESTALE;
        }
        return -1;
    }
    if (!S_ISBLK(metadata.st_mode) || metadata.st_rdev != session->device_number) {
        errno = ESTALE;
        return -1;
    }
    if (require_unmounted(session->display_path) != 0) {
        return -1;
    }
    return 0;
}

static int nodes_are_gone(struct r46h_macos_session *session) {
    struct stat ignored;
    errno = 0;
    int block_status = lstat(session->display_path, &ignored);
    int block_error = errno;
    errno = 0;
    int raw_status = lstat(session->raw_path, &ignored);
    int raw_error = errno;
    if (block_status != 0 && block_error == ENOENT && raw_status != 0 &&
        raw_error == ENOENT) {
        return 1;
    }
    if ((block_status != 0 && block_error != ENOENT) ||
        (raw_status != 0 && raw_error != ENOENT)) {
        errno = EIO;
        return -1;
    }
    return 0;
}

static int eject_session(struct r46h_macos_session *session) {
    if (session != NULL && session->ejected) {
        return 0;
    }
    if (session == NULL || session->disk == NULL || session->eject_result == NULL ||
        !session->unmounted) {
        errno = EINVAL;
        return -1;
    }
    if (!session->eject_pending) {
        if (revalidate_eject_identity(session) != 0) {
            return -1;
        }
        if (session->raw_fd >= 0) {
            if (close(session->raw_fd) != 0) {
                session->raw_close_error = errno == 0 ? EIO : errno;
            }
            session->raw_fd = -1;
        }
        memset(session->eject_result, 0, sizeof(*session->eject_result));
        session->eject_pending = 1;
        DADiskEject(
            session->disk,
            kDADiskEjectOptionDefault,
            da_completed,
            session->eject_result
        );
    }
    if (!session->eject_result->completed) {
        int wait_status = wait_for_retryable_da(session->eject_result, 300);
        if (wait_status != 0 && !session->eject_result->completed) {
            return -1;
        }
    }
    if (session->eject_result->denied) {
        session->eject_pending = 0;
        memset(session->eject_result, 0, sizeof(*session->eject_result));
        errno = EBUSY;
        return -1;
    }
    for (unsigned int attempt = 0; attempt < 100; attempt++) {
        int node_status = nodes_are_gone(session);
        if (node_status < 0) {
            return -1;
        }
        if (node_status > 0) {
            session->ejected = 1;
            session->eject_pending = 0;
            free_da_result(session->eject_result);
            session->eject_result = NULL;
            int signal_status = finish_signal_window(session);
            if (session->raw_close_error != 0) {
                errno = session->raw_close_error;
                return -1;
            }
            if (signal_status != 0) {
                return -1;
            }
            return 0;
        }
        usleep(100000);
    }
    errno = EBUSY;
    return -1;
}

int r46h_macos_partition_observation(
    struct r46h_macos_session *session,
    const struct r46h_macos_candidate *candidate,
    uint32_t partition_number,
    struct r46h_macos_partition *observation
) {
    if (session == NULL || candidate == NULL || observation == NULL || partition_number == 0 ||
        partition_number > 99) {
        errno = EINVAL;
        return -1;
    }
    if (revalidate_session(session, 1, 1) != 0) {
        return -1;
    }
    if (candidate->registry_entry_id != session->registry_entry_id ||
        candidate->device_number != (uint64_t)session->device_number ||
        candidate->size != session->size || candidate->sector_size != session->sector_size ||
        strcmp(candidate->display_path, session->display_path) != 0) {
        errno = ESTALE;
        return -1;
    }
    const char *bsd_name = strrchr(candidate->display_path, '/');
    if (bsd_name == NULL) {
        errno = EINVAL;
        return -1;
    }
    bsd_name++;
    char partition_path[R46H_PATH_CAPACITY];
    char partition_raw_path[R46H_PATH_CAPACITY];
    int block_length = snprintf(
        partition_path,
        sizeof(partition_path),
        "/dev/%ss%u",
        bsd_name,
        partition_number
    );
    int raw_length = snprintf(
        partition_raw_path,
        sizeof(partition_raw_path),
        "/dev/r%ss%u",
        bsd_name,
        partition_number
    );
    if (block_length <= 0 || block_length >= (int)sizeof(partition_path) || raw_length <= 0 ||
        raw_length >= (int)sizeof(partition_raw_path)) {
        errno = EINVAL;
        return -1;
    }
    int descriptor = open(partition_raw_path, O_RDONLY | O_NOFOLLOW | O_CLOEXEC);
    if (descriptor < 0) {
        if (errno == ENOENT || errno == ENXIO) {
            return 1;
        }
        return -1;
    }
    int saved_error = 0;
    struct stat partition_metadata;
    uint64_t base = 0;
    uint64_t block_count = 0;
    uint32_t block_size = 0;
    if (fstat(descriptor, &partition_metadata) != 0) {
        saved_error = errno == 0 ? EIO : errno;
        goto fail_descriptor;
    }
    if (!S_ISCHR(partition_metadata.st_mode)) {
        saved_error = ESTALE;
        goto fail_descriptor;
    }
    if (ioctl(descriptor, DKIOCGETBASE, &base) != 0 ||
        ioctl(descriptor, DKIOCGETBLOCKSIZE, &block_size) != 0 ||
        ioctl(descriptor, DKIOCGETBLOCKCOUNT, &block_count) != 0) {
        saved_error = errno == 0 ? EIO : errno;
        goto fail_descriptor;
    }
    if (block_size != session->sector_size || block_count > UINT64_MAX / block_size) {
        saved_error = ESTALE;
        goto fail_descriptor;
    }
    unsigned char boot_sector[512];
    unsigned char ext4_magic[2] = {0};
    ssize_t boot_count = pread(descriptor, boot_sector, sizeof(boot_sector), 0);
    if (boot_count != (ssize_t)sizeof(boot_sector)) {
        saved_error = boot_count < 0 && errno != 0 ? errno : EIO;
        goto fail_descriptor;
    }
    if (stop_requested()) {
        saved_error = ECANCELED;
        goto fail_descriptor;
    }
    const char *filesystem = NULL;
    if (boot_count == (ssize_t)sizeof(boot_sector) &&
        memcmp(boot_sector + 3, "EXFAT   ", 8) == 0 && boot_sector[510] == 0x55 &&
        boot_sector[511] == 0xaa) {
        filesystem = "exfat";
    } else if (boot_count == (ssize_t)sizeof(boot_sector) &&
               memcmp(boot_sector + 82, "FAT32   ", 8) == 0 && boot_sector[510] == 0x55 &&
               boot_sector[511] == 0xaa) {
        filesystem = "fat32";
    } else {
        ssize_t ext4_count = pread(descriptor, ext4_magic, sizeof(ext4_magic), 1080);
        if (ext4_count != (ssize_t)sizeof(ext4_magic)) {
            saved_error = ext4_count < 0 && errno != 0 ? errno : EIO;
            goto fail_descriptor;
        }
        if (ext4_magic[0] == 0x53 && ext4_magic[1] == 0xef) {
            filesystem = "ext4";
        } else {
            saved_error = EFTYPE;
            goto fail_descriptor;
        }
    }
    if (close(descriptor) != 0) {
        return -1;
    }

    DADiskRef disk = DADiskCreateFromBSDName(
        kCFAllocatorDefault,
        session->da_session,
        partition_path
    );
    CFDictionaryRef description = disk == NULL ? NULL : DADiskCopyDescription(disk);
    if (description == NULL) {
        if (disk != NULL) {
            CFRelease(disk);
        }
        errno = EIO;
        return -1;
    }
    DADiskRef whole = DADiskCopyWholeDisk(disk);
    uint64_t whole_registry_id = 0;
    if (whole == NULL || media_registry_id(whole, &whole_registry_id) != 0 ||
        whole_registry_id != session->registry_entry_id) {
        if (whole != NULL) {
            CFRelease(whole);
        }
        CFRelease(description);
        CFRelease(disk);
        errno = ESTALE;
        return -1;
    }
    CFRelease(whole);
    observation->number = partition_number;
    observation->offset = base;
    observation->size = block_count * block_size;
    int result = copy_text(
                     observation->filesystem,
                     sizeof(observation->filesystem),
                     filesystem
                 ) ||
        cf_uuid(
            description,
            kDADiskDescriptionVolumeUUIDKey,
            observation->volume_uuid,
            sizeof(observation->volume_uuid),
            1
        );
    CFRelease(description);
    CFRelease(disk);
    if (result != 0) {
        errno = EIO;
        return -1;
    }
    if (revalidate_session(session, 1, 1) != 0) {
        return -1;
    }
    return 0;

fail_descriptor:
    if (close(descriptor) != 0 && saved_error == 0) {
        saved_error = errno;
    }
    errno = saved_error == 0 ? EIO : saved_error;
    return -1;
}

int r46h_macos_eject(struct r46h_macos_session *session) {
    return eject_session(session);
}

int r46h_macos_revalidate(struct r46h_macos_session *session) {
    return revalidate_session(session, 1, 1);
}

void r46h_macos_session_free(struct r46h_macos_session *session) {
    if (session != NULL && session->unmounted && !session->ejected) {
        eject_session(session);
    }
    release_session(session);
}
