#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <linux/videodev2.h>
#include <poll.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#define WIDTH 96U
#define HEIGHT 32U

struct mapped_buffer {
    void *address[VIDEO_MAX_PLANES];
    size_t length[VIDEO_MAX_PLANES];
    unsigned int plane_count;
};

static int xioctl(int fd, unsigned long request, void *arg)
{
    int rc;

    do {
        rc = ioctl(fd, request, arg);
    } while (rc < 0 && errno == EINTR);
    return rc;
}

static int validate_encoder_identity(int fd, const char *path)
{
    struct stat path_stat;
    struct stat fd_stat;
    struct v4l2_capability capability;
    uint32_t active_caps;

    if (lstat(path, &path_stat) < 0)
        return -1;
    if (!S_ISCHR(path_stat.st_mode)) {
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
    memset(&capability, 0, sizeof(capability));
    if (xioctl(fd, VIDIOC_QUERYCAP, &capability) < 0)
        return -1;
    active_caps = (capability.capabilities & V4L2_CAP_DEVICE_CAPS) != 0U ?
                  capability.device_caps : capability.capabilities;
    if (strcmp((const char *)capability.driver, "hantro-vpu") != 0 ||
        strcmp((const char *)capability.card, "rockchip,px30-vpu-enc") != 0 ||
        strcmp((const char *)capability.bus_info,
               "platform:ff442000.video-codec") != 0 ||
        (active_caps & V4L2_CAP_STREAMING) == 0U ||
        (active_caps & V4L2_CAP_VIDEO_M2M_MPLANE) == 0U) {
        errno = ENODEV;
        return -1;
    }
    printf("R46H_HANTRO_IDENTITY driver=%s card=%s bus=%s active_caps=0x%08x\n",
           capability.driver, capability.card, capability.bus_info,
           active_caps);
    return 0;
}

static int set_format(int fd, enum v4l2_buf_type type, uint32_t pixelformat,
                      struct v4l2_format *format)
{
    memset(format, 0, sizeof(*format));
    format->type = type;
    format->fmt.pix_mp.width = WIDTH;
    format->fmt.pix_mp.height = HEIGHT;
    format->fmt.pix_mp.pixelformat = pixelformat;
    format->fmt.pix_mp.field = V4L2_FIELD_NONE;
    format->fmt.pix_mp.colorspace = V4L2_COLORSPACE_SRGB;
    if (xioctl(fd, VIDIOC_S_FMT, format) < 0)
        return -1;
    if (format->fmt.pix_mp.width != WIDTH ||
        format->fmt.pix_mp.height != HEIGHT ||
        format->fmt.pix_mp.pixelformat != pixelformat ||
        format->fmt.pix_mp.num_planes == 0 ||
        format->fmt.pix_mp.num_planes > VIDEO_MAX_PLANES) {
        errno = EPROTO;
        return -1;
    }
    return 0;
}

static int map_buffer(int fd, enum v4l2_buf_type type,
                      unsigned int plane_count, struct mapped_buffer *mapped)
{
    struct v4l2_requestbuffers request;
    struct v4l2_buffer buffer;
    struct v4l2_plane planes[VIDEO_MAX_PLANES];

    memset(mapped, 0, sizeof(*mapped));
    memset(&request, 0, sizeof(request));
    request.count = 2;
    request.type = type;
    request.memory = V4L2_MEMORY_MMAP;
    if (xioctl(fd, VIDIOC_REQBUFS, &request) < 0 || request.count < 1) {
        fprintf(stderr, "ERROR: VIDIOC_REQBUFS type=%u count=%u: %s\n",
                type, request.count, strerror(errno));
        return -1;
    }
    fprintf(stderr, "R46H_HANTRO_REQBUFS type=%u count=%u\n",
            type, request.count);

    memset(&buffer, 0, sizeof(buffer));
    memset(planes, 0, sizeof(planes));
    buffer.type = type;
    buffer.memory = V4L2_MEMORY_MMAP;
    buffer.index = 0;
    buffer.length = VIDEO_MAX_PLANES;
    buffer.m.planes = planes;
    if (xioctl(fd, VIDIOC_QUERYBUF, &buffer) < 0) {
        fprintf(stderr, "ERROR: VIDIOC_QUERYBUF type=%u: %s\n",
                type, strerror(errno));
        return -1;
    }
    fprintf(stderr, "R46H_HANTRO_QUERYBUF type=%u plane_capacity=%u expected_planes=%u\n",
            type, buffer.length, plane_count);
    if (buffer.length < plane_count) {
        errno = EPROTO;
        return -1;
    }
    mapped->plane_count = plane_count;
    for (unsigned int i = 0; i < plane_count; ++i) {
        mapped->length[i] = planes[i].length;
        mapped->address[i] = mmap(NULL, planes[i].length,
                                  PROT_READ | PROT_WRITE, MAP_SHARED, fd,
                                  (off_t)planes[i].m.mem_offset);
        if (mapped->address[i] == MAP_FAILED) {
            mapped->address[i] = NULL;
            fprintf(stderr,
                    "ERROR: mmap type=%u plane=%u length=%u offset=%u: %s\n",
                    type, i, planes[i].length, planes[i].m.mem_offset,
                    strerror(errno));
            return -1;
        }
    }
    return 0;
}

static int unmap_buffer(struct mapped_buffer *mapped)
{
    int failures = 0;

    for (unsigned int i = 0; i < mapped->plane_count; ++i) {
        if (mapped->address[i] != NULL &&
            munmap(mapped->address[i], mapped->length[i]) < 0)
            ++failures;
    }
    memset(mapped, 0, sizeof(*mapped));
    return failures == 0 ? 0 : -1;
}

static int queue_buffer(int fd, enum v4l2_buf_type type,
                        const struct mapped_buffer *mapped,
                        const size_t bytes_used[VIDEO_MAX_PLANES])
{
    struct v4l2_buffer buffer;
    struct v4l2_plane planes[VIDEO_MAX_PLANES];

    memset(&buffer, 0, sizeof(buffer));
    memset(planes, 0, sizeof(planes));
    buffer.type = type;
    buffer.memory = V4L2_MEMORY_MMAP;
    buffer.index = 0;
    buffer.length = mapped->plane_count;
    buffer.m.planes = planes;
    for (unsigned int i = 0; i < mapped->plane_count; ++i)
        planes[i].length = (uint32_t)mapped->length[i];
    for (unsigned int i = 0; i < mapped->plane_count; ++i)
        planes[i].bytesused = (uint32_t)bytes_used[i];
    return xioctl(fd, VIDIOC_QBUF, &buffer);
}

static int dequeue_capture(int fd, unsigned int plane_count,
                           struct v4l2_buffer *buffer,
                           struct v4l2_plane planes[VIDEO_MAX_PLANES])
{
    struct pollfd poll_fd;
    struct timespec start;

    memset(&poll_fd, 0, sizeof(poll_fd));
    poll_fd.fd = fd;
    poll_fd.events = POLLIN | POLLERR;
    if (clock_gettime(CLOCK_MONOTONIC, &start) < 0)
        return -1;
    for (;;) {
        struct timespec now;
        long elapsed_ms;
        int rc;

        memset(buffer, 0, sizeof(*buffer));
        memset(planes, 0, sizeof(struct v4l2_plane) * VIDEO_MAX_PLANES);
        buffer->type = V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;
        buffer->memory = V4L2_MEMORY_MMAP;
        buffer->length = plane_count;
        buffer->m.planes = planes;
        if (xioctl(fd, VIDIOC_DQBUF, buffer) == 0)
            return 0;
        if (errno != EAGAIN)
            return -1;
        rc = poll(&poll_fd, 1, 1000);
        if (rc < 0 && errno != EINTR)
            return -1;
        if (clock_gettime(CLOCK_MONOTONIC, &now) < 0)
            return -1;
        elapsed_ms = (now.tv_sec - start.tv_sec) * 1000L +
                     (now.tv_nsec - start.tv_nsec) / 1000000L;
        if (elapsed_ms >= 10000L) {
            errno = ETIMEDOUT;
            return -1;
        }
    }
}

static uint64_t fnv1a64(const uint8_t *bytes, size_t length)
{
    uint64_t hash = UINT64_C(14695981039346656037);

    for (size_t i = 0; i < length; ++i) {
        hash ^= bytes[i];
        hash *= UINT64_C(1099511628211);
    }
    return hash;
}

static int emit_base64(const uint8_t *bytes, size_t length)
{
    static const char alphabet[] =
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    unsigned int column = 0;

    printf("R46H_HANTRO_JPEG_BASE64_BEGIN\n");
    for (size_t i = 0; i < length; i += 3U) {
        size_t remaining = length - i;
        uint32_t value = (uint32_t)bytes[i] << 16;
        char encoded[4];

        if (remaining > 1U)
            value |= (uint32_t)bytes[i + 1U] << 8;
        if (remaining > 2U)
            value |= bytes[i + 2U];
        encoded[0] = alphabet[(value >> 18) & 0x3fU];
        encoded[1] = alphabet[(value >> 12) & 0x3fU];
        encoded[2] = remaining > 1U ? alphabet[(value >> 6) & 0x3fU] : '=';
        encoded[3] = remaining > 2U ? alphabet[value & 0x3fU] : '=';
        for (unsigned int j = 0; j < 4; ++j) {
            if (putchar(encoded[j]) == EOF) {
                errno = EIO;
                return -1;
            }
            if (++column == 76U) {
                if (putchar('\n') == EOF) {
                    errno = EIO;
                    return -1;
                }
                column = 0;
            }
        }
    }
    if (column != 0U && putchar('\n') == EOF) {
        errno = EIO;
        return -1;
    }
    printf("R46H_HANTRO_JPEG_BASE64_END\n");
    if (ferror(stdout)) {
        errno = EIO;
        return -1;
    }
    return 0;
}

static int validate_jpeg(const uint8_t *bytes, size_t length)
{
    int saw_baseline = 0;
    int saw_scan = 0;
    size_t position = 2;

    if (length < 16 || bytes[0] != 0xffU || bytes[1] != 0xd8U ||
        bytes[length - 2U] != 0xffU || bytes[length - 1U] != 0xd9U ||
        memcmp(bytes + 6, "JFIF\0", 5) != 0) {
        errno = EPROTO;
        return -1;
    }
    while (position + 1U < length) {
        uint8_t marker;
        size_t segment_length;

        if (bytes[position] != 0xffU) {
            errno = EPROTO;
            return -1;
        }
        while (position < length && bytes[position] == 0xffU)
            ++position;
        if (position >= length)
            break;
        marker = bytes[position++];
        if (marker == 0xd9U)
            break;
        if (marker == 0xdaU) {
            saw_scan = 1;
            break;
        }
        if (marker == 0x01U || (marker >= 0xd0U && marker <= 0xd8U))
            continue;
        if (position + 2U > length) {
            errno = EPROTO;
            return -1;
        }
        segment_length = ((size_t)bytes[position] << 8) | bytes[position + 1U];
        if (segment_length < 2U || position + segment_length > length) {
            errno = EPROTO;
            return -1;
        }
        if (marker == 0xc0U) {
            if (segment_length < 8U || bytes[position + 2U] != 8U ||
                (((unsigned int)bytes[position + 3U] << 8) |
                 bytes[position + 4U]) != HEIGHT ||
                (((unsigned int)bytes[position + 5U] << 8) |
                 bytes[position + 6U]) != WIDTH) {
                errno = EPROTO;
                return -1;
            }
            saw_baseline = 1;
        }
        position += segment_length;
    }
    if (!saw_baseline || !saw_scan) {
        errno = EPROTO;
        return -1;
    }
    return 0;
}

static int fill_yuv420m(const struct mapped_buffer *mapped,
                        const struct v4l2_format *format)
{
    uint8_t *luma = (uint8_t *)mapped->address[0];
    uint8_t *blue = (uint8_t *)mapped->address[1];
    uint8_t *red = (uint8_t *)mapped->address[2];
    size_t luma_stride = format->fmt.pix_mp.plane_fmt[0].bytesperline;
    size_t blue_stride = format->fmt.pix_mp.plane_fmt[1].bytesperline;
    size_t red_stride = format->fmt.pix_mp.plane_fmt[2].bytesperline;

    if (luma_stride < WIDTH || blue_stride < WIDTH / 2U ||
        red_stride < WIDTH / 2U ||
        luma_stride > SIZE_MAX / HEIGHT ||
        blue_stride > SIZE_MAX / (HEIGHT / 2U) ||
        red_stride > SIZE_MAX / (HEIGHT / 2U) ||
        mapped->length[0] < luma_stride * HEIGHT ||
        mapped->length[1] < blue_stride * (HEIGHT / 2U) ||
        mapped->length[2] < red_stride * (HEIGHT / 2U)) {
        errno = EPROTO;
        return -1;
    }
    memset(luma, 16, mapped->length[0]);
    memset(blue, 128, mapped->length[1]);
    memset(red, 128, mapped->length[2]);

    for (unsigned int y = 0; y < HEIGHT; ++y) {
        for (unsigned int x = 0; x < WIDTH; ++x)
            luma[(size_t)y * luma_stride + x] =
                (uint8_t)(16U + (x * 219U) / (WIDTH - 1U));
    }
    for (unsigned int y = 0; y < HEIGHT / 2U; ++y) {
        for (unsigned int x = 0; x < WIDTH / 2U; ++x) {
            blue[(size_t)y * blue_stride + x] = (uint8_t)(96U + y * 4U);
            red[(size_t)y * red_stride + x] = (uint8_t)(160U - y * 4U);
        }
    }
    return 0;
}

int main(int argc, char **argv)
{
    const enum v4l2_buf_type output_type = V4L2_BUF_TYPE_VIDEO_OUTPUT_MPLANE;
    const enum v4l2_buf_type capture_type = V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;
    struct v4l2_format output_format;
    struct v4l2_format capture_format;
    struct mapped_buffer output_map;
    struct mapped_buffer capture_map;
    struct v4l2_buffer capture_buffer;
    struct v4l2_plane capture_planes[VIDEO_MAX_PLANES];
    size_t output_bytes[VIDEO_MAX_PLANES] = {0};
    size_t capture_bytes[VIDEO_MAX_PLANES] = {0};
    size_t raw_bytes = (size_t)WIDTH * HEIGHT * 3U / 2U;
    size_t jpeg_bytes = 0;
    uint64_t jpeg_fnv = 0;
    int fd = -1;
    int output_streaming = 0;
    int capture_streaming = 0;
    int cleanup_failed = 0;
    int should_emit_base64 = 0;
    int result = 1;

    memset(&output_map, 0, sizeof(output_map));
    memset(&capture_map, 0, sizeof(capture_map));
    if (argc == 3 && strcmp(argv[2], "--emit-base64") == 0)
        should_emit_base64 = 1;
    else if (argc != 2) {
        fprintf(stderr, "usage: %s ENCODER [--emit-base64]\n", argv[0]);
        return 64;
    }
    fd = open(argv[1], O_RDWR | O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) {
        fprintf(stderr, "ERROR: open encoder: %s\n", strerror(errno));
        goto cleanup;
    }
    if (validate_encoder_identity(fd, argv[1]) < 0) {
        fprintf(stderr, "ERROR: encoder identity: %s\n", strerror(errno));
        goto cleanup;
    }
    if (set_format(fd, output_type, V4L2_PIX_FMT_YUV420M, &output_format) < 0) {
        fprintf(stderr, "ERROR: set output YM12: %s\n", strerror(errno));
        goto cleanup;
    }
    if (set_format(fd, capture_type, V4L2_PIX_FMT_JPEG, &capture_format) < 0) {
        fprintf(stderr, "ERROR: set capture JPEG: %s\n", strerror(errno));
        goto cleanup;
    }
    if (output_format.fmt.pix_mp.num_planes != 3 ||
        capture_format.fmt.pix_mp.num_planes != 1 ||
        output_format.fmt.pix_mp.plane_fmt[0].sizeimage < WIDTH * HEIGHT ||
        output_format.fmt.pix_mp.plane_fmt[1].sizeimage < WIDTH * HEIGHT / 4U ||
        output_format.fmt.pix_mp.plane_fmt[2].sizeimage < WIDTH * HEIGHT / 4U) {
        errno = EPROTO;
        fprintf(stderr, "ERROR: unexpected negotiated planes or size\n");
        goto cleanup;
    }
    printf("R46H_HANTRO_NEGOTIATED width=%u height=%u raw_sizeimages=%u,%u,%u jpeg_sizeimage=%u\n",
           output_format.fmt.pix_mp.width, output_format.fmt.pix_mp.height,
           output_format.fmt.pix_mp.plane_fmt[0].sizeimage,
           output_format.fmt.pix_mp.plane_fmt[1].sizeimage,
           output_format.fmt.pix_mp.plane_fmt[2].sizeimage,
           capture_format.fmt.pix_mp.plane_fmt[0].sizeimage);
    if (map_buffer(fd, output_type, 3, &output_map) < 0 ||
        map_buffer(fd, capture_type, 1, &capture_map) < 0) {
        fprintf(stderr, "ERROR: map buffers: %s\n", strerror(errno));
        goto cleanup;
    }
    for (unsigned int i = 0; i < 3; ++i) {
        output_bytes[i] = output_format.fmt.pix_mp.plane_fmt[i].sizeimage;
        if (output_map.length[i] < output_bytes[i]) {
            errno = ENOSPC;
            fprintf(stderr, "ERROR: output plane %u too small\n", i);
            goto cleanup;
        }
    }
    if (fill_yuv420m(&output_map, &output_format) < 0) {
        fprintf(stderr, "ERROR: fill YM12 input: %s\n", strerror(errno));
        goto cleanup;
    }
    memset(capture_map.address[0], 0, capture_map.length[0]);
    if (queue_buffer(fd, capture_type, &capture_map, capture_bytes) < 0 ||
        queue_buffer(fd, output_type, &output_map, output_bytes) < 0) {
        fprintf(stderr, "ERROR: queue buffers: %s\n", strerror(errno));
        goto cleanup;
    }
    if (xioctl(fd, VIDIOC_STREAMON, (void *)&capture_type) < 0) {
        fprintf(stderr, "ERROR: stream on capture: %s\n", strerror(errno));
        goto cleanup;
    }
    capture_streaming = 1;
    if (xioctl(fd, VIDIOC_STREAMON, (void *)&output_type) < 0) {
        fprintf(stderr, "ERROR: stream on output: %s\n", strerror(errno));
        goto cleanup;
    }
    output_streaming = 1;
    if (dequeue_capture(fd, 1, &capture_buffer, capture_planes) < 0) {
        fprintf(stderr, "ERROR: dequeue capture: %s\n", strerror(errno));
        goto cleanup;
    }
    jpeg_bytes = capture_planes[0].bytesused;
    if ((capture_buffer.flags & V4L2_BUF_FLAG_ERROR) != 0U ||
        capture_buffer.index != 0 || jpeg_bytes > capture_map.length[0]) {
        errno = EPROTO;
        fprintf(stderr, "ERROR: invalid capture result flags=0x%x index=%u bytes=%zu\n",
                capture_buffer.flags, capture_buffer.index, jpeg_bytes);
        goto cleanup;
    }
    if (validate_jpeg((const uint8_t *)capture_map.address[0], jpeg_bytes) < 0) {
        fprintf(stderr, "ERROR: validate JPEG: %s\n", strerror(errno));
        goto cleanup;
    }
    jpeg_fnv = fnv1a64((const uint8_t *)capture_map.address[0], jpeg_bytes);
    if (should_emit_base64 &&
        emit_base64((const uint8_t *)capture_map.address[0], jpeg_bytes) < 0) {
        fprintf(stderr, "ERROR: emit JPEG base64: %s\n", strerror(errno));
        goto cleanup;
    }
    result = 0;

cleanup:
    if (fd >= 0 && output_streaming &&
        xioctl(fd, VIDIOC_STREAMOFF, (void *)&output_type) < 0)
        cleanup_failed = 1;
    if (fd >= 0 && capture_streaming &&
        xioctl(fd, VIDIOC_STREAMOFF, (void *)&capture_type) < 0)
        cleanup_failed = 1;
    if (unmap_buffer(&output_map) < 0 || unmap_buffer(&capture_map) < 0)
        cleanup_failed = 1;
    if (fd >= 0 && close(fd) < 0)
        cleanup_failed = 1;
    if (cleanup_failed)
        result = 1;
    if (result == 0) {
        if (printf("R46H_HANTRO_JPEG result=pass width=%u height=%u raw_bytes=%zu jpeg_bytes=%zu fnv1a64=%016llx cleanup=pass\n",
                   WIDTH, HEIGHT, raw_bytes, jpeg_bytes,
                   (unsigned long long)jpeg_fnv) < 0)
            result = 1;
    } else {
        printf("R46H_HANTRO_JPEG result=fail cleanup=%s\n",
               cleanup_failed ? "fail" : "pass");
    }
    return result;
}
