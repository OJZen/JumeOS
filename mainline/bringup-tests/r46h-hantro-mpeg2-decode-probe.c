#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <linux/media.h>
#include <linux/v4l2-controls.h>
#include <linux/videodev2.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#define WIDTH 64U
#define HEIGHT 64U
#define LOGICAL_NV12_SIZE (WIDTH * HEIGHT * 3U / 2U)
#define WAIT_TIMEOUT_MS 10000L

struct mapped_buffer {
    void *address;
    size_t length;
    enum v4l2_buf_type type;
    int allocated;
};

static volatile sig_atomic_t stop_requested;

/* Four MPEG-2 slices from the pinned 64x64 intra-only fixture. */
static const uint8_t slice_data[] = {
    0x00, 0x00, 0x01, 0x01, 0x13, 0xf8, 0xfd, 0x29, 0x48, 0x8b, 0x94, 0xa5,
    0x22, 0x2f, 0xe8, 0x14, 0xa5, 0x22, 0x2e, 0x52, 0x94, 0x88, 0x80,
    0x00, 0x00, 0x01, 0x02, 0x13, 0xf8, 0xfd, 0x29, 0x48, 0x8b, 0x94,
    0xa5, 0x22, 0x2f, 0xe8, 0x14, 0xa5, 0x22, 0x2e, 0x52, 0x94, 0x88,
    0x80, 0x00, 0x00, 0x01, 0x03, 0x13, 0xf4, 0x14, 0xa5, 0x22, 0x2e,
    0x52, 0x94, 0x88, 0xbf, 0xa0, 0x52, 0x94, 0x88, 0xb9, 0x4a, 0x52,
    0x22, 0x00, 0x00, 0x01, 0x04, 0x13, 0xf4, 0x14, 0xa5, 0x22, 0x2e,
    0x52, 0x94, 0x88, 0xbf, 0xa0, 0x52, 0x94, 0x88, 0xb9, 0x4a, 0x52,
    0x22,
};

/* ISO/IEC 13818-2 default intra matrix in zigzag order. */
static const uint8_t default_intra_quantiser_matrix[64] = {
    8, 16, 16, 19, 16, 19, 22, 22,
    22, 22, 22, 22, 26, 24, 26, 27,
    27, 27, 26, 26, 26, 26, 27, 27,
    27, 29, 29, 29, 34, 34, 34, 29,
    29, 29, 27, 27, 29, 29, 32, 32,
    34, 34, 37, 38, 37, 35, 35, 34,
    35, 38, 38, 40, 40, 40, 48, 48,
    46, 46, 56, 56, 58, 69, 69, 83,
};

static void handle_signal(int signal_number)
{
    (void)signal_number;
    stop_requested = 1;
}

static int install_signal_handlers(void)
{
    struct sigaction action;

    memset(&action, 0, sizeof(action));
    action.sa_handler = handle_signal;
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGINT, &action, NULL) < 0 ||
        sigaction(SIGTERM, &action, NULL) < 0 ||
        sigaction(SIGHUP, &action, NULL) < 0)
        return -1;
    signal(SIGPIPE, SIG_IGN);
    return 0;
}

static int xioctl(int fd, unsigned long request, void *argument)
{
    int rc;

    do {
        rc = ioctl(fd, request, argument);
    } while (rc < 0 && errno == EINTR && !stop_requested);
    if (rc < 0 && stop_requested)
        errno = ECANCELED;
    return rc;
}

static int path_matches_character_fd(const char *path, int fd)
{
    struct stat path_stat;
    struct stat fd_stat;

    if (lstat(path, &path_stat) < 0 || !S_ISCHR(path_stat.st_mode)) {
        errno = ENODEV;
        return -1;
    }
    if (fstat(fd, &fd_stat) < 0 || !S_ISCHR(fd_stat.st_mode) ||
        path_stat.st_dev != fd_stat.st_dev ||
        path_stat.st_ino != fd_stat.st_ino ||
        path_stat.st_rdev != fd_stat.st_rdev) {
        errno = ESTALE;
        return -1;
    }
    return 0;
}

static int validate_decoder_identity(int fd, const char *path)
{
    struct v4l2_capability capability;
    uint32_t active_caps;

    if (path_matches_character_fd(path, fd) < 0)
        return -1;
    memset(&capability, 0, sizeof(capability));
    if (xioctl(fd, VIDIOC_QUERYCAP, &capability) < 0)
        return -1;
    active_caps = (capability.capabilities & V4L2_CAP_DEVICE_CAPS) != 0U ?
                  capability.device_caps : capability.capabilities;
    if (strcmp((const char *)capability.driver, "hantro-vpu") != 0 ||
        strcmp((const char *)capability.card, "rockchip,px30-vpu-dec") != 0 ||
        strcmp((const char *)capability.bus_info,
               "platform:ff442000.video-codec") != 0 ||
        (active_caps & V4L2_CAP_STREAMING) == 0U ||
        (active_caps & V4L2_CAP_VIDEO_M2M_MPLANE) == 0U) {
        errno = ENODEV;
        return -1;
    }
    printf("R46H_HANTRO_DECODE_IDENTITY driver=%s card=%s bus=%s active_caps=0x%08x\n",
           capability.driver, capability.card, capability.bus_info,
           active_caps);
    return 0;
}

static int validate_media_identity(int fd, const char *path)
{
    struct media_device_info info;

    if (path_matches_character_fd(path, fd) < 0)
        return -1;
    memset(&info, 0, sizeof(info));
    if (xioctl(fd, MEDIA_IOC_DEVICE_INFO, &info) < 0)
        return -1;
    if (strcmp(info.driver, "hantro-vpu") != 0 ||
        strcmp(info.bus_info, "platform:ff442000.video-codec") != 0) {
        errno = ENODEV;
        return -1;
    }
    printf("R46H_HANTRO_MEDIA_IDENTITY driver=%s model=%s bus=%s\n",
           info.driver, info.model, info.bus_info);
    return 0;
}

static int has_format(int fd, enum v4l2_buf_type type, uint32_t fourcc)
{
    struct v4l2_fmtdesc description;

    memset(&description, 0, sizeof(description));
    description.type = type;
    for (description.index = 0;; ++description.index) {
        if (xioctl(fd, VIDIOC_ENUM_FMT, &description) < 0) {
            if (errno == EINVAL)
                break;
            return -1;
        }
        if (description.pixelformat == fourcc)
            return 1;
    }
    errno = ENOTSUP;
    return 0;
}

static int frame_size_supported(int fd, uint32_t fourcc)
{
    struct v4l2_frmsizeenum sizes;

    memset(&sizes, 0, sizeof(sizes));
    sizes.pixel_format = fourcc;
    for (sizes.index = 0;; ++sizes.index) {
        if (xioctl(fd, VIDIOC_ENUM_FRAMESIZES, &sizes) < 0) {
            if (errno == EINVAL)
                break;
            return -1;
        }
        if (sizes.type == V4L2_FRMSIZE_TYPE_DISCRETE &&
            sizes.discrete.width == WIDTH && sizes.discrete.height == HEIGHT)
            return 1;
        if (sizes.type == V4L2_FRMSIZE_TYPE_STEPWISE &&
            sizes.stepwise.step_width != 0U &&
            sizes.stepwise.step_height != 0U &&
            WIDTH >= sizes.stepwise.min_width &&
            WIDTH <= sizes.stepwise.max_width &&
            HEIGHT >= sizes.stepwise.min_height &&
            HEIGHT <= sizes.stepwise.max_height &&
            (WIDTH - sizes.stepwise.min_width) % sizes.stepwise.step_width == 0U &&
            (HEIGHT - sizes.stepwise.min_height) % sizes.stepwise.step_height == 0U)
            return 1;
    }
    errno = ENOTSUP;
    return 0;
}

static int set_format(int fd, enum v4l2_buf_type type, uint32_t fourcc,
                      struct v4l2_format *format)
{
    memset(format, 0, sizeof(*format));
    format->type = type;
    format->fmt.pix_mp.width = WIDTH;
    format->fmt.pix_mp.height = HEIGHT;
    format->fmt.pix_mp.pixelformat = fourcc;
    format->fmt.pix_mp.field = V4L2_FIELD_NONE;
    format->fmt.pix_mp.colorspace = V4L2_COLORSPACE_SMPTE170M;
    if (xioctl(fd, VIDIOC_S_FMT, format) < 0)
        return -1;
    if (format->fmt.pix_mp.width != WIDTH ||
        format->fmt.pix_mp.height != HEIGHT ||
        format->fmt.pix_mp.pixelformat != fourcc ||
        format->fmt.pix_mp.num_planes != 1U) {
        errno = EPROTO;
        return -1;
    }
    return 0;
}

static int allocate_and_map(int fd, enum v4l2_buf_type type,
                            int require_requests, struct mapped_buffer *mapped)
{
    struct v4l2_requestbuffers request;
    struct v4l2_buffer buffer;
    struct v4l2_plane planes[VIDEO_MAX_PLANES];

    memset(mapped, 0, sizeof(*mapped));
    mapped->type = type;
    memset(&request, 0, sizeof(request));
    request.count = 1;
    request.type = type;
    request.memory = V4L2_MEMORY_MMAP;
    if (xioctl(fd, VIDIOC_REQBUFS, &request) < 0 || request.count != 1U)
        return -1;
    mapped->allocated = 1;
    if ((request.capabilities & V4L2_BUF_CAP_SUPPORTS_MMAP) == 0U ||
        (require_requests &&
         (request.capabilities & V4L2_BUF_CAP_SUPPORTS_REQUESTS) == 0U)) {
        errno = ENOTSUP;
        return -1;
    }

    memset(&buffer, 0, sizeof(buffer));
    memset(planes, 0, sizeof(planes));
    buffer.type = type;
    buffer.memory = V4L2_MEMORY_MMAP;
    buffer.index = 0;
    buffer.length = VIDEO_MAX_PLANES;
    buffer.m.planes = planes;
    if (xioctl(fd, VIDIOC_QUERYBUF, &buffer) < 0 || buffer.length != 1U) {
        errno = EPROTO;
        return -1;
    }
    mapped->length = planes[0].length;
    mapped->address = mmap(NULL, mapped->length, PROT_READ | PROT_WRITE,
                           MAP_SHARED, fd, (off_t)planes[0].m.mem_offset);
    if (mapped->address == MAP_FAILED) {
        mapped->address = NULL;
        return -1;
    }
    return 0;
}

static int release_buffer(int fd, struct mapped_buffer *mapped)
{
    struct v4l2_requestbuffers request;
    int failed = 0;

    if (mapped->address != NULL &&
        munmap(mapped->address, mapped->length) < 0)
        failed = 1;
    mapped->address = NULL;
    if (mapped->allocated) {
        memset(&request, 0, sizeof(request));
        request.type = mapped->type;
        request.memory = V4L2_MEMORY_MMAP;
        request.count = 0;
        if (xioctl(fd, VIDIOC_REQBUFS, &request) < 0)
            failed = 1;
    }
    memset(mapped, 0, sizeof(*mapped));
    return failed ? -1 : 0;
}

static void fill_controls(struct v4l2_ctrl_mpeg2_sequence *sequence,
                          struct v4l2_ctrl_mpeg2_picture *picture,
                          struct v4l2_ctrl_mpeg2_quantisation *quantisation)
{
    memset(sequence, 0, sizeof(*sequence));
    sequence->horizontal_size = WIDTH;
    sequence->vertical_size = HEIGHT;
    sequence->vbv_buffer_size = 3U;
    sequence->profile_and_level_indication = 0x48U;
    sequence->chroma_format = 1U;
    sequence->flags = V4L2_MPEG2_SEQ_FLAG_PROGRESSIVE;

    memset(picture, 0, sizeof(*picture));
    for (unsigned int i = 0; i < 2U; ++i)
        for (unsigned int j = 0; j < 2U; ++j)
            picture->f_code[i][j] = 15U;
    picture->picture_coding_type = V4L2_MPEG2_PIC_CODING_TYPE_I;
    picture->picture_structure = V4L2_MPEG2_PIC_FRAME;
    picture->flags = V4L2_MPEG2_PIC_FLAG_FRAME_PRED_DCT |
                     V4L2_MPEG2_PIC_FLAG_PROGRESSIVE;

    memset(quantisation, 0, sizeof(*quantisation));
    memcpy(quantisation->intra_quantiser_matrix,
           default_intra_quantiser_matrix,
           sizeof(default_intra_quantiser_matrix));
    memcpy(quantisation->chroma_intra_quantiser_matrix,
           default_intra_quantiser_matrix,
           sizeof(default_intra_quantiser_matrix));
    memset(quantisation->non_intra_quantiser_matrix, 16,
           sizeof(quantisation->non_intra_quantiser_matrix));
    memset(quantisation->chroma_non_intra_quantiser_matrix, 16,
           sizeof(quantisation->chroma_non_intra_quantiser_matrix));
}

static int set_request_controls(int video_fd, int request_fd)
{
    struct v4l2_ctrl_mpeg2_sequence sequence;
    struct v4l2_ctrl_mpeg2_picture picture;
    struct v4l2_ctrl_mpeg2_quantisation quantisation;
    struct v4l2_ext_control controls_array[3];
    struct v4l2_ext_controls controls;

    fill_controls(&sequence, &picture, &quantisation);
    memset(controls_array, 0, sizeof(controls_array));
    controls_array[0].id = V4L2_CID_STATELESS_MPEG2_SEQUENCE;
    controls_array[0].size = sizeof(sequence);
    controls_array[0].ptr = &sequence;
    controls_array[1].id = V4L2_CID_STATELESS_MPEG2_PICTURE;
    controls_array[1].size = sizeof(picture);
    controls_array[1].ptr = &picture;
    controls_array[2].id = V4L2_CID_STATELESS_MPEG2_QUANTISATION;
    controls_array[2].size = sizeof(quantisation);
    controls_array[2].ptr = &quantisation;

    memset(&controls, 0, sizeof(controls));
    controls.which = V4L2_CTRL_WHICH_REQUEST_VAL;
    controls.request_fd = request_fd;
    controls.count = 3;
    controls.controls = controls_array;
    return xioctl(video_fd, VIDIOC_S_EXT_CTRLS, &controls);
}

static int queue_capture(int fd, const struct mapped_buffer *mapped)
{
    struct v4l2_buffer buffer;
    struct v4l2_plane plane;

    memset(&buffer, 0, sizeof(buffer));
    memset(&plane, 0, sizeof(plane));
    buffer.type = V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;
    buffer.memory = V4L2_MEMORY_MMAP;
    buffer.index = 0;
    buffer.length = 1;
    buffer.m.planes = &plane;
    plane.length = (uint32_t)mapped->length;
    return xioctl(fd, VIDIOC_QBUF, &buffer);
}

static int queue_output(int fd, int request_fd,
                        const struct mapped_buffer *mapped)
{
    struct v4l2_buffer buffer;
    struct v4l2_plane plane;

    memset(&buffer, 0, sizeof(buffer));
    memset(&plane, 0, sizeof(plane));
    buffer.type = V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE;
    buffer.memory = V4L2_MEMORY_MMAP;
    buffer.index = 0;
    buffer.length = 1;
    buffer.m.planes = &plane;
    buffer.flags = V4L2_BUF_FLAG_REQUEST_FD;
    buffer.request_fd = request_fd;
    buffer.timestamp.tv_sec = 1;
    plane.length = (uint32_t)mapped->length;
    plane.bytesused = (uint32_t)sizeof(slice_data);
    return xioctl(fd, VIDIOC_QBUF, &buffer);
}

static int stream_change(int fd, enum v4l2_buf_type type, int enable)
{
    return xioctl(fd, enable ? VIDIOC_STREAMON : VIDIOC_STREAMOFF, &type);
}

static long elapsed_ms(const struct timespec *start, const struct timespec *now)
{
    return (now->tv_sec - start->tv_sec) * 1000L +
           (now->tv_nsec - start->tv_nsec) / 1000000L;
}

static int wait_for_request(int request_fd)
{
    struct timespec start;

    if (clock_gettime(CLOCK_MONOTONIC, &start) < 0)
        return -1;
    for (;;) {
        struct pollfd poll_fd;
        struct timespec now;
        int rc;

        if (stop_requested) {
            errno = ECANCELED;
            return -1;
        }
        memset(&poll_fd, 0, sizeof(poll_fd));
        poll_fd.fd = request_fd;
        poll_fd.events = POLLPRI;
        rc = poll(&poll_fd, 1, 250);
        if (rc > 0) {
            if ((poll_fd.revents & POLLPRI) != 0)
                return 0;
            errno = EIO;
            return -1;
        }
        if (rc < 0 && errno != EINTR)
            return -1;
        if (clock_gettime(CLOCK_MONOTONIC, &now) < 0)
            return -1;
        if (elapsed_ms(&start, &now) >= WAIT_TIMEOUT_MS) {
            errno = ETIMEDOUT;
            return -1;
        }
    }
}

static int dequeue_buffer(int fd, enum v4l2_buf_type type,
                          struct v4l2_buffer *buffer,
                          struct v4l2_plane *plane)
{
    struct timespec start;

    if (clock_gettime(CLOCK_MONOTONIC, &start) < 0)
        return -1;
    for (;;) {
        struct pollfd poll_fd;
        struct timespec now;
        int rc;

        memset(buffer, 0, sizeof(*buffer));
        memset(plane, 0, sizeof(*plane));
        buffer->type = type;
        buffer->memory = V4L2_MEMORY_MMAP;
        buffer->length = 1;
        buffer->m.planes = plane;
        if (xioctl(fd, VIDIOC_DQBUF, buffer) == 0)
            return 0;
        if (errno != EAGAIN)
            return -1;
        if (stop_requested) {
            errno = ECANCELED;
            return -1;
        }
        memset(&poll_fd, 0, sizeof(poll_fd));
        poll_fd.fd = fd;
        poll_fd.events = type == V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE ?
                         POLLIN : POLLOUT;
        rc = poll(&poll_fd, 1, 250);
        if (rc < 0 && errno != EINTR)
            return -1;
        if (clock_gettime(CLOCK_MONOTONIC, &now) < 0)
            return -1;
        if (elapsed_ms(&start, &now) >= WAIT_TIMEOUT_MS) {
            errno = ETIMEDOUT;
            return -1;
        }
    }
}

static uint64_t fnv1a64_update(uint64_t hash, const uint8_t *bytes,
                               size_t length)
{
    for (size_t i = 0; i < length; ++i) {
        hash ^= bytes[i];
        hash *= UINT64_C(1099511628211);
    }
    return hash;
}

static int validate_nv12(const struct mapped_buffer *mapped,
                         const struct v4l2_format *format,
                         const struct v4l2_plane *plane,
                         uint64_t *diagnostic_hash)
{
    const uint32_t stride = format->fmt.pix_mp.plane_fmt[0].bytesperline;
    const size_t data_offset = plane->data_offset;
    const size_t y_bytes = (size_t)stride * HEIGHT;
    const size_t required = y_bytes + (size_t)stride * (HEIGHT / 2U);
    const uint8_t *base;
    uint64_t hash = UINT64_C(14695981039346656037);

    if (stride < WIDTH || data_offset > mapped->length ||
        required > mapped->length - data_offset) {
        errno = EOVERFLOW;
        return -1;
    }
    base = (const uint8_t *)mapped->address + data_offset;
    for (uint32_t y = 0; y < HEIGHT; ++y) {
        const uint8_t *row = base + (size_t)y * stride;
        for (uint32_t x = 0; x < WIDTH; ++x) {
            const uint8_t expected = y < HEIGHT / 2U ?
                                     (x < WIDTH / 2U ? 32U : 96U) :
                                     (x < WIDTH / 2U ? 160U : 224U);
            if (row[x] != expected) {
                fprintf(stderr,
                        "ERROR: decoded Y mismatch x=%u y=%u expected=%u actual=%u\n",
                        x, y, expected, row[x]);
                errno = EILSEQ;
                return -1;
            }
        }
        hash = fnv1a64_update(hash, row, WIDTH);
    }
    for (uint32_t y = 0; y < HEIGHT / 2U; ++y) {
        const uint8_t *row = base + y_bytes + (size_t)y * stride;
        for (uint32_t x = 0; x < WIDTH; ++x) {
            if (row[x] != 128U) {
                fprintf(stderr,
                        "ERROR: decoded UV mismatch x=%u y=%u expected=128 actual=%u\n",
                        x, y, row[x]);
                errno = EILSEQ;
                return -1;
            }
        }
        hash = fnv1a64_update(hash, row, WIDTH);
    }
    if (hash != UINT64_C(0x0833461a6e018325)) {
        errno = EILSEQ;
        return -1;
    }
    *diagnostic_hash = hash;
    return 0;
}

int main(int argc, char **argv)
{
    const enum v4l2_buf_type output_type =
        V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE;
    const enum v4l2_buf_type capture_type =
        V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;
    struct mapped_buffer output_buffer;
    struct mapped_buffer capture_buffer;
    struct v4l2_format output_format;
    struct v4l2_format capture_format;
    struct v4l2_buffer dequeued_capture;
    struct v4l2_buffer dequeued_output;
    struct v4l2_plane capture_plane;
    struct v4l2_plane output_plane;
    uint64_t decoded_hash = 0;
    int video_fd = -1;
    int media_fd = -1;
    int request_fd = -1;
    int output_streaming = 0;
    int capture_streaming = 0;
    int operation_failed = 0;
    int cleanup_failed = 0;
    int saved_errno = 0;

    memset(&output_buffer, 0, sizeof(output_buffer));
    memset(&capture_buffer, 0, sizeof(capture_buffer));
    if (argc != 3) {
        fprintf(stderr, "usage: %s /dev/videoN /dev/mediaN\n", argv[0]);
        return 64;
    }
    setvbuf(stdout, NULL, _IOLBF, 0);
    if (install_signal_handlers() < 0) {
        fprintf(stderr, "ERROR: install signal handlers: %s\n", strerror(errno));
        return 1;
    }

    video_fd = open(argv[1], O_RDWR | O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW);
    if (video_fd < 0) {
        fprintf(stderr, "ERROR: open decoder: %s\n", strerror(errno));
        operation_failed = 1;
        goto cleanup;
    }
    media_fd = open(argv[2], O_RDWR | O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW);
    if (media_fd < 0) {
        fprintf(stderr, "ERROR: open media request device: %s\n", strerror(errno));
        operation_failed = 1;
        goto cleanup;
    }
    if (validate_decoder_identity(video_fd, argv[1]) < 0 ||
        validate_media_identity(media_fd, argv[2]) < 0) {
        fprintf(stderr, "ERROR: validate Hantro identities: %s\n", strerror(errno));
        operation_failed = 1;
        goto cleanup;
    }
    if (has_format(video_fd, output_type, V4L2_PIX_FMT_MPEG2_SLICE) != 1 ||
        has_format(video_fd, capture_type, V4L2_PIX_FMT_NV12) != 1 ||
        frame_size_supported(video_fd, V4L2_PIX_FMT_MPEG2_SLICE) != 1) {
        fprintf(stderr, "ERROR: required MPEG-2/NV12 format is unavailable: %s\n",
                strerror(errno));
        operation_failed = 1;
        goto cleanup;
    }
    if (set_format(video_fd, output_type, V4L2_PIX_FMT_MPEG2_SLICE,
                   &output_format) < 0 ||
        set_format(video_fd, capture_type, V4L2_PIX_FMT_NV12,
                   &capture_format) < 0) {
        fprintf(stderr, "ERROR: negotiate MPEG-2/NV12 formats: %s\n",
                strerror(errno));
        operation_failed = 1;
        goto cleanup;
    }
    printf("R46H_HANTRO_DECODE_FORMAT width=%u height=%u output_size=%u capture_stride=%u capture_size=%u\n",
           output_format.fmt.pix_mp.width, output_format.fmt.pix_mp.height,
           output_format.fmt.pix_mp.plane_fmt[0].sizeimage,
           capture_format.fmt.pix_mp.plane_fmt[0].bytesperline,
           capture_format.fmt.pix_mp.plane_fmt[0].sizeimage);
    if (output_format.fmt.pix_mp.plane_fmt[0].sizeimage < sizeof(slice_data) ||
        capture_format.fmt.pix_mp.plane_fmt[0].sizeimage < LOGICAL_NV12_SIZE) {
        errno = EOVERFLOW;
        fprintf(stderr, "ERROR: negotiated buffers are too small: %s\n",
                strerror(errno));
        operation_failed = 1;
        goto cleanup;
    }
    if (allocate_and_map(video_fd, output_type, 1, &output_buffer) < 0 ||
        allocate_and_map(video_fd, capture_type, 0, &capture_buffer) < 0) {
        fprintf(stderr, "ERROR: allocate decoder buffers: %s\n", strerror(errno));
        operation_failed = 1;
        goto cleanup;
    }
    if (sizeof(slice_data) > output_buffer.length) {
        errno = EOVERFLOW;
        operation_failed = 1;
        goto cleanup;
    }
    memset(output_buffer.address, 0, output_buffer.length);
    memcpy(output_buffer.address, slice_data, sizeof(slice_data));
    memset(capture_buffer.address, 0x5a, capture_buffer.length);

    if (xioctl(media_fd, MEDIA_IOC_REQUEST_ALLOC, &request_fd) < 0 ||
        set_request_controls(video_fd, request_fd) < 0 ||
        queue_capture(video_fd, &capture_buffer) < 0 ||
        queue_output(video_fd, request_fd, &output_buffer) < 0 ||
        stream_change(video_fd, capture_type, 1) < 0) {
        fprintf(stderr, "ERROR: prepare decoder request: %s\n", strerror(errno));
        operation_failed = 1;
        goto cleanup;
    }
    capture_streaming = 1;
    if (stream_change(video_fd, output_type, 1) < 0) {
        fprintf(stderr, "ERROR: start decoder output queue: %s\n", strerror(errno));
        operation_failed = 1;
        goto cleanup;
    }
    output_streaming = 1;
    if (xioctl(request_fd, MEDIA_REQUEST_IOC_QUEUE, NULL) < 0 ||
        wait_for_request(request_fd) < 0 ||
        dequeue_buffer(video_fd, capture_type, &dequeued_capture,
                       &capture_plane) < 0 ||
        dequeue_buffer(video_fd, output_type, &dequeued_output,
                       &output_plane) < 0) {
        fprintf(stderr, "ERROR: execute decoder request: %s\n", strerror(errno));
        operation_failed = 1;
        goto cleanup;
    }
    if ((dequeued_capture.flags & V4L2_BUF_FLAG_ERROR) != 0U ||
        (dequeued_output.flags & V4L2_BUF_FLAG_ERROR) != 0U) {
        errno = EIO;
        fprintf(stderr, "ERROR: decoder returned an error buffer\n");
        operation_failed = 1;
        goto cleanup;
    }
    if (validate_nv12(&capture_buffer, &capture_format, &capture_plane,
                      &decoded_hash) < 0) {
        fprintf(stderr, "ERROR: validate decoded NV12: %s\n", strerror(errno));
        operation_failed = 1;
        goto cleanup;
    }
    if (validate_decoder_identity(video_fd, argv[1]) < 0 ||
        validate_media_identity(media_fd, argv[2]) < 0) {
        fprintf(stderr, "ERROR: Hantro identity changed during decode: %s\n",
                strerror(errno));
        operation_failed = 1;
        goto cleanup;
    }

cleanup:
    saved_errno = errno;
    if (output_streaming && stream_change(video_fd, output_type, 0) < 0)
        cleanup_failed = 1;
    if (capture_streaming && stream_change(video_fd, capture_type, 0) < 0)
        cleanup_failed = 1;
    if (request_fd >= 0 && close(request_fd) < 0)
        cleanup_failed = 1;
    if (video_fd >= 0) {
        if (release_buffer(video_fd, &capture_buffer) < 0)
            cleanup_failed = 1;
        if (release_buffer(video_fd, &output_buffer) < 0)
            cleanup_failed = 1;
    }
    if (media_fd >= 0 && close(media_fd) < 0)
        cleanup_failed = 1;
    if (video_fd >= 0 && close(video_fd) < 0)
        cleanup_failed = 1;
    errno = saved_errno;

    if (!operation_failed && !cleanup_failed) {
        printf("R46H_HANTRO_MPEG2_DECODE result=pass width=%u height=%u slice_bytes=%zu nv12_bytes=%u fnv1a64=%016llx cleanup=pass\n",
               WIDTH, HEIGHT, sizeof(slice_data), LOGICAL_NV12_SIZE,
               (unsigned long long)decoded_hash);
        return 0;
    }
    printf("R46H_HANTRO_MPEG2_DECODE result=fail cleanup=%s\n",
           cleanup_failed ? "fail" : "pass");
    return 1;
}
