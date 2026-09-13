#define _GNU_SOURCE

#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <grp.h>
#include <linux/dma-buf.h>
#include <pwd.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#include <zlib.h>

#if __BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__
#error "R46H scanout capture requires little-endian pixels"
#endif

#define ARRAY_SIZE(value) (sizeof(value) / sizeof((value)[0]))
#define DRM_DISPLAY_MODE_LEN 32
#define DRM_CLOEXEC 0x01U
#define DRM_RDWR 0x02U
#define DRM_FORMAT_XRGB8888 0x34325258U
#define DRM_FORMAT_ARGB8888 0x34325241U
#define EXPECTED_WIDTH 1024U
#define EXPECTED_HEIGHT 768U
#define MAX_BUFFER_BYTES (64U * 1024U * 1024U)
#define ARK_UID 1000U
#define ARK_GID 1000U

typedef struct {
    int count_fbs;
    uint32_t *fbs;
    int count_crtcs;
    uint32_t *crtcs;
    int count_connectors;
    uint32_t *connectors;
    int count_encoders;
    uint32_t *encoders;
    uint32_t min_width;
    uint32_t max_width;
    uint32_t min_height;
    uint32_t max_height;
} drm_mode_res;

typedef struct {
    uint32_t clock;
    uint16_t hdisplay;
    uint16_t hsync_start;
    uint16_t hsync_end;
    uint16_t htotal;
    uint16_t hskew;
    uint16_t vdisplay;
    uint16_t vsync_start;
    uint16_t vsync_end;
    uint16_t vtotal;
    uint16_t vscan;
    uint32_t vrefresh;
    uint32_t flags;
    uint32_t type;
    char name[DRM_DISPLAY_MODE_LEN];
} drm_mode_info;

typedef struct {
    uint32_t crtc_id;
    uint32_t buffer_id;
    uint32_t x;
    uint32_t y;
    uint32_t width;
    uint32_t height;
    int mode_valid;
    drm_mode_info mode;
    int gamma_size;
} drm_mode_crtc;

typedef struct {
    uint32_t fb_id;
    uint32_t width;
    uint32_t height;
    uint32_t pixel_format;
    uint64_t modifier;
    uint32_t flags;
    uint32_t handles[4];
    uint32_t pitches[4];
    uint32_t offsets[4];
} drm_mode_fb2;

typedef drm_mode_res *(*get_resources_fn)(int);
typedef void (*free_resources_fn)(drm_mode_res *);
typedef drm_mode_crtc *(*get_crtc_fn)(int, uint32_t);
typedef void (*free_crtc_fn)(drm_mode_crtc *);
typedef drm_mode_fb2 *(*get_fb2_fn)(int, uint32_t);
typedef void (*free_fb2_fn)(drm_mode_fb2 *);
typedef int (*prime_handle_to_fd_fn)(int, uint32_t, uint32_t, int *);
typedef int (*map_dumb_buffer_fn)(int, uint32_t, uint64_t *);

static void fail(const char *message)
{
    fprintf(stderr, "ERROR: r46h DRM capture: %s\n", message);
    exit(EXIT_FAILURE);
}

static void fail_errno(const char *message)
{
    fprintf(stderr, "ERROR: r46h DRM capture: %s: %s\n", message, strerror(errno));
    exit(EXIT_FAILURE);
}

static void *checked_malloc(size_t bytes)
{
    void *result;

    if (bytes == 0U || bytes > MAX_BUFFER_BYTES)
        fail("allocation is outside the bound");
    result = malloc(bytes);
    if (result == NULL)
        fail_errno("allocation failed");
    return result;
}

static void load_symbol(void *library, const char *name, void *destination,
                        size_t destination_size)
{
    void *symbol;
    const char *error;

    dlerror();
    symbol = dlsym(library, name);
    error = dlerror();
    if (error != NULL || symbol == NULL)
        fail("required libdrm symbol is unavailable");
    if (destination_size != sizeof(symbol))
        fail("unexpected function-pointer size");
    memcpy(destination, &symbol, sizeof(symbol));
}

static void require_invocation_identity(void)
{
    const char *sudo_gid = getenv("SUDO_GID");
    const char *sudo_uid = getenv("SUDO_UID");
    const char *sudo_user = getenv("SUDO_USER");
    struct stat executable;
    struct stat output;

    if (getuid() != 0U || geteuid() != 0U || getgid() != 0U || getegid() != 0U)
        fail("root execution is required");
    if (sudo_user == NULL || strcmp(sudo_user, "ark") != 0 || sudo_uid == NULL ||
        strcmp(sudo_uid, "1000") != 0 || sudo_gid == NULL || strcmp(sudo_gid, "1000") != 0)
        fail("the fixed ark sudo identity is required");
    if (stat("/proc/self/exe", &executable) != 0)
        fail_errno("cannot inspect the capture executable");
    if (executable.st_uid != 0U || executable.st_gid != 0U || executable.st_nlink != 1U ||
        (executable.st_mode & (S_IWGRP | S_IWOTH)) != 0U)
        fail("capture executable identity is unsafe");
    if (fstat(STDOUT_FILENO, &output) != 0)
        fail_errno("cannot inspect capture output");
    if (!S_ISREG(output.st_mode) || output.st_uid != ARK_UID || output.st_gid != ARK_GID ||
        output.st_nlink != 1U || (output.st_mode & 0777U) != 0600U || output.st_size != 0)
        fail("capture output must be one empty private ark file");
}

static void drop_to_ark(void)
{
    struct passwd *account = getpwnam("ark");

    if (account == NULL || account->pw_uid != ARK_UID || account->pw_gid != ARK_GID)
        fail("ark account identity is unexpected");
    if (setgroups(0U, NULL) != 0)
        fail_errno("cannot clear supplementary groups");
    if (setgid(ARK_GID) != 0 || setuid(ARK_UID) != 0)
        fail_errno("cannot drop capture privileges");
    if (prctl(PR_SET_NO_NEW_PRIVS, 1L, 0L, 0L, 0L) != 0)
        fail_errno("cannot lock capture privileges");
    if (getuid() != ARK_UID || geteuid() != ARK_UID || getgid() != ARK_GID ||
        getegid() != ARK_GID)
        fail("capture privileges did not drop completely");
}

static void write_all(const void *data, size_t bytes)
{
    const uint8_t *cursor = data;

    while (bytes > 0U) {
        ssize_t written = write(STDOUT_FILENO, cursor, bytes);
        if (written < 0) {
            if (errno == EINTR)
                continue;
            fail_errno("PNG write failed");
        }
        if (written == 0)
            fail("PNG write made no progress");
        cursor += (size_t)written;
        bytes -= (size_t)written;
    }
}

static void encode_u32_be(uint8_t output[4], uint32_t value)
{
    output[0] = (uint8_t)(value >> 24U);
    output[1] = (uint8_t)(value >> 16U);
    output[2] = (uint8_t)(value >> 8U);
    output[3] = (uint8_t)value;
}

static void write_png_chunk(const char type[4], const uint8_t *data, uint32_t bytes)
{
    uint8_t encoded[4];
    uLong checksum;

    encode_u32_be(encoded, bytes);
    write_all(encoded, sizeof(encoded));
    write_all(type, 4U);
    if (bytes > 0U)
        write_all(data, bytes);
    checksum = crc32(0L, Z_NULL, 0U);
    checksum = crc32(checksum, (const Bytef *)type, 4U);
    if (bytes > 0U)
        checksum = crc32(checksum, data, bytes);
    encode_u32_be(encoded, (uint32_t)checksum);
    write_all(encoded, sizeof(encoded));
}

static void write_png(const uint8_t *rgb, uint32_t width, uint32_t height)
{
    static const uint8_t signature[8] = {0x89U, 'P', 'N', 'G', 0x0dU, 0x0aU, 0x1aU, 0x0aU};
    uint8_t ihdr[13] = {0};
    uLongf compressed_bytes;
    uLongf compressed_bound;
    size_t row_bytes = (size_t)width * 3U + 1U;
    size_t raw_bytes = row_bytes * (size_t)height;
    uint8_t *filtered = checked_malloc(raw_bytes);
    uint8_t *compressed;

    for (uint32_t row = 0U; row < height; ++row) {
        uint8_t *destination = filtered + (size_t)row * row_bytes;
        destination[0] = 0U;
        memcpy(destination + 1U, rgb + (size_t)row * (size_t)width * 3U,
               (size_t)width * 3U);
    }
    compressed_bound = compressBound((uLong)raw_bytes);
    if (compressed_bound == 0U || compressed_bound > MAX_BUFFER_BYTES)
        fail("compressed PNG bound is invalid");
    compressed = checked_malloc((size_t)compressed_bound);
    compressed_bytes = compressed_bound;
    if (compress2(compressed, &compressed_bytes, filtered, (uLong)raw_bytes,
                  Z_BEST_SPEED) != Z_OK)
        fail("PNG compression failed");
    if (compressed_bytes == 0U || compressed_bytes > UINT32_MAX)
        fail("compressed PNG size is invalid");

    encode_u32_be(&ihdr[0], width);
    encode_u32_be(&ihdr[4], height);
    ihdr[8] = 8U;
    ihdr[9] = 2U;
    write_all(signature, sizeof(signature));
    write_png_chunk("IHDR", ihdr, sizeof(ihdr));
    write_png_chunk("IDAT", compressed, (uint32_t)compressed_bytes);
    write_png_chunk("IEND", NULL, 0U);
    if (fsync(STDOUT_FILENO) != 0)
        fail_errno("cannot synchronize PNG output");
    free(compressed);
    free(filtered);
}

int main(int argc, char **argv)
{
    void *library;
    get_resources_fn get_resources = NULL;
    free_resources_fn free_resources = NULL;
    get_crtc_fn get_crtc = NULL;
    free_crtc_fn free_crtc = NULL;
    get_fb2_fn get_fb2 = NULL;
    free_fb2_fn free_fb2 = NULL;
    prime_handle_to_fd_fn prime_handle_to_fd = NULL;
    map_dumb_buffer_fn map_dumb_buffer = NULL;
    drm_mode_res *resources;
    drm_mode_crtc *active = NULL;
    drm_mode_fb2 *framebuffer;
    struct dma_buf_sync sync = {.flags = DMA_BUF_SYNC_START | DMA_BUF_SYNC_READ};
    struct stat dma_buffer;
    uint8_t *mapping;
    uint8_t *rgb;
    uint32_t active_count = 0U;
    uint32_t framebuffer_handle;
    uint32_t framebuffer_offset;
    uint32_t framebuffer_pitch;
    uint64_t dumb_offset = 0U;
    size_t mapped_bytes;
    size_t required_bytes;
    int card;
    int dma_sync_active = 0;
    int mapping_fd;
    int prime_fd = -1;

    (void)argv;
    if (argc != 1)
        fail("arguments are forbidden");
    require_invocation_identity();
    card = open("/dev/dri/card0", O_RDWR | O_CLOEXEC);
    if (card < 0)
        fail_errno("cannot open the display DRM card");
    library = dlopen("/usr/lib/aarch64-linux-gnu/libdrm.so.2", RTLD_NOW | RTLD_LOCAL);
    if (library == NULL)
        fail("cannot load libdrm.so.2");
    load_symbol(library, "drmModeGetResources", &get_resources, sizeof(get_resources));
    load_symbol(library, "drmModeFreeResources", &free_resources, sizeof(free_resources));
    load_symbol(library, "drmModeGetCrtc", &get_crtc, sizeof(get_crtc));
    load_symbol(library, "drmModeFreeCrtc", &free_crtc, sizeof(free_crtc));
    load_symbol(library, "drmModeGetFB2", &get_fb2, sizeof(get_fb2));
    load_symbol(library, "drmModeFreeFB2", &free_fb2, sizeof(free_fb2));
    load_symbol(library, "drmPrimeHandleToFD", &prime_handle_to_fd, sizeof(prime_handle_to_fd));
    load_symbol(library, "drmModeMapDumbBuffer", &map_dumb_buffer, sizeof(map_dumb_buffer));

    resources = get_resources(card);
    if (resources == NULL || resources->count_crtcs < 1 || resources->count_crtcs > 8)
        fail("DRM CRTC resources are invalid");
    for (int index = 0; index < resources->count_crtcs; ++index) {
        drm_mode_crtc *candidate = get_crtc(card, resources->crtcs[index]);
        if (candidate == NULL)
            fail("cannot query a DRM CRTC");
        if (candidate->mode_valid != 0 && candidate->buffer_id != 0U) {
            ++active_count;
            if (active == NULL)
                active = candidate;
            else
                free_crtc(candidate);
        } else {
            free_crtc(candidate);
        }
    }
    free_resources(resources);
    if (active_count != 1U || active == NULL)
        fail("expected exactly one active DRM CRTC");
    if (active->width != EXPECTED_WIDTH || active->height != EXPECTED_HEIGHT)
        fail("active DRM mode has unexpected dimensions");
    framebuffer = get_fb2(card, active->buffer_id);
    free_crtc(active);
    if (framebuffer == NULL)
        fail("cannot query the active DRM framebuffer");
    if (framebuffer->width != EXPECTED_WIDTH || framebuffer->height != EXPECTED_HEIGHT ||
        (framebuffer->pixel_format != DRM_FORMAT_XRGB8888 &&
         framebuffer->pixel_format != DRM_FORMAT_ARGB8888) ||
        framebuffer->modifier != 0U ||
        framebuffer->handles[0] == 0U || framebuffer->handles[1] != 0U ||
        framebuffer->pitches[0] < EXPECTED_WIDTH * 4U ||
        framebuffer->pitches[0] > EXPECTED_WIDTH * 8U)
        fail("active DRM framebuffer layout is unsupported");
    required_bytes = (size_t)framebuffer->offsets[0] +
                     (size_t)framebuffer->pitches[0] * (size_t)framebuffer->height;
    if (required_bytes == 0U || required_bytes > MAX_BUFFER_BYTES)
        fail("active DRM framebuffer size is invalid");
    framebuffer_handle = framebuffer->handles[0];
    if (prime_handle_to_fd(card, framebuffer_handle, DRM_CLOEXEC | DRM_RDWR,
                           &prime_fd) != 0 || prime_fd < 0) {
        if (prime_fd >= 0)
            close(prime_fd);
        prime_fd = -1;
        if (prime_handle_to_fd(card, framebuffer_handle, DRM_CLOEXEC, &prime_fd) != 0 ||
            prime_fd < 0) {
            if (prime_fd >= 0)
                close(prime_fd);
            prime_fd = -1;
        }
    }
    framebuffer_offset = framebuffer->offsets[0];
    framebuffer_pitch = framebuffer->pitches[0];
    free_fb2(framebuffer);
    if (prime_fd >= 0) {
        if (fstat(prime_fd, &dma_buffer) != 0)
            fail_errno("cannot inspect the DMA buffer");
        if (dma_buffer.st_size <= 0 || (uint64_t)dma_buffer.st_size < required_bytes ||
            (uint64_t)dma_buffer.st_size > MAX_BUFFER_BYTES)
            fail("DMA buffer size is invalid");
        mapped_bytes = (size_t)dma_buffer.st_size;
        mapping_fd = prime_fd;
    } else {
        if (map_dumb_buffer(card, framebuffer_handle, &dumb_offset) != 0)
            fail_errno("cannot map or export the active DRM framebuffer");
        mapped_bytes = required_bytes;
        mapping_fd = card;
    }
    mapping = mmap(NULL, mapped_bytes, PROT_READ, MAP_SHARED, mapping_fd,
                   (off_t)dumb_offset);
    if (mapping == MAP_FAILED)
        fail_errno("cannot map the active DRM framebuffer");
    if (prime_fd >= 0) {
        if (ioctl(prime_fd, DMA_BUF_IOCTL_SYNC, &sync) != 0)
            fail_errno("cannot begin DMA buffer CPU access");
        dma_sync_active = 1;
    }
    rgb = checked_malloc((size_t)EXPECTED_WIDTH * (size_t)EXPECTED_HEIGHT * 3U);
    for (uint32_t row = 0U; row < EXPECTED_HEIGHT; ++row) {
        const uint8_t *source = mapping + (size_t)framebuffer_offset +
                                (size_t)row * (size_t)framebuffer_pitch;
        uint8_t *destination = rgb + (size_t)row * (size_t)EXPECTED_WIDTH * 3U;
        for (uint32_t column = 0U; column < EXPECTED_WIDTH; ++column) {
            destination[(size_t)column * 3U] = source[(size_t)column * 4U + 2U];
            destination[(size_t)column * 3U + 1U] = source[(size_t)column * 4U + 1U];
            destination[(size_t)column * 3U + 2U] = source[(size_t)column * 4U];
        }
    }
    if (dma_sync_active != 0) {
        sync.flags = DMA_BUF_SYNC_END | DMA_BUF_SYNC_READ;
        if (ioctl(prime_fd, DMA_BUF_IOCTL_SYNC, &sync) != 0)
            fail_errno("cannot end DMA buffer CPU access");
    }
    if (munmap(mapping, mapped_bytes) != 0)
        fail_errno("cannot unmap the active DRM framebuffer");
    if (prime_fd >= 0)
        close(prime_fd);
    close(card);
    dlclose(library);

    drop_to_ark();
    write_png(rgb, EXPECTED_WIDTH, EXPECTED_HEIGHT);
    free(rgb);
    return EXIT_SUCCESS;
}
