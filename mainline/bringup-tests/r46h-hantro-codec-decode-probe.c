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
#define MAX_FRAME_COUNT 240U
#define REFERENCE_TIMESTAMP_NS UINT64_C(1000000000)

enum codec_mode {
    CODEC_H264,
    CODEC_VP8,
    CODEC_H264_REFERENCE,
    CODEC_VP8_REFERENCE,
};

struct mapped_buffer {
    void *address;
    size_t length;
    enum v4l2_buf_type type;
    int allocated;
};

static volatile sig_atomic_t stop_requested;

/* One Annex-B IDR slice from the pinned constrained-baseline fixture. */
static const uint8_t h264_slice_data[] = {
    0x00, 0x00, 0x01, 0x65, 0x88, 0x84, 0x3a, 0x26, 0x28, 0x00, 0x0c, 0x4c,
    0xc9, 0xde, 0x28, 0x00, 0x0a, 0xd8, 0x49, 0xd7, 0x5d, 0x75, 0xd6, 0x28,
    0x00, 0x0d, 0xc1, 0x5f, 0x78, 0xa0, 0x00, 0x2b, 0x61, 0x7d, 0x75, 0xd7,
    0x5e,
};

/* IDR then P slices from the pinned two-frame constrained-baseline stream. */
static const uint8_t h264_reference_idr_data[] = {
    0x00, 0x00, 0x01, 0x65, 0x88, 0x84, 0x3a, 0x26, 0x28, 0x00, 0x0c, 0x4c,
    0xc9, 0xc9, 0x8a, 0x00, 0x02, 0xb6, 0x12, 0x75, 0xd7, 0x5d, 0x75, 0x8a,
    0x00, 0x03, 0x70, 0x57, 0xde, 0x28, 0x00, 0x0a, 0xd8, 0x5f, 0x5d, 0x75,
    0xd7, 0x80,
};

static const uint8_t h264_reference_p_data[] = {
    0x00, 0x00, 0x00, 0x01, 0x41, 0x9a, 0x22, 0x82, 0x30,
};

/* One complete keyframe from the pinned VP8 IVF fixture (container removed). */
static const uint8_t vp8_frame_data[] = {
    0x10, 0x03, 0x00, 0x9d, 0x01, 0x2a, 0x40, 0x00, 0x40, 0x00, 0x00, 0x47,
    0x08, 0x85, 0x85, 0x88, 0x85, 0x84, 0x88, 0x02, 0x02, 0x00, 0x07, 0x30,
    0xb3, 0xcd, 0x18, 0x81, 0xcc, 0x7f, 0x60, 0x81, 0xea, 0x00, 0xfe, 0xff,
    0x80, 0xe2, 0x9f, 0x5c, 0x35, 0xbe, 0x9c, 0x40, 0x00,
};

/* The second frame in the pinned IVF is an inter frame using all key refs. */
static const uint8_t vp8_inter_frame_data[] = {
    0xd1, 0x01, 0x00, 0x05, 0x10, 0xac, 0x00, 0x18, 0x00,
    0x18, 0x58, 0x2f, 0xf4, 0x00, 0x08, 0x8e, 0x80, 0x00,
};

/* RFC 6386 default coefficient probabilities, flattened in V4L2 order. */
static const char vp8_default_coeff_probs_hex[] =
    "808080808080808080808080808080808080808080808080808080808080808080fd88feffe4db8080808080bd81f2ff"
    "e3d5ffdb8080806a7ee3fcd6d1ffff8080800162f8ffece2ffff808080b585eefeddeaff9a8080804e86caf7c6b4ffdb"
    "80808001b9f9fff3ff8080808080b896f7ffece080808080804d6ed8ffece680808080800165fbfff1ff8080808080aa"
    "8bf1fcecd1ffff8080802574c4f3e4ffffff80808001ccfefff5ff8080808080cfa0faffee8080808080806667e7ffd3"
    "ab80808080800198fcfff0ff8080808080b187f3ffeae180808080805081d3ffc2e080808080800101ff808080808080"
    "8080f601ff8080808080808080ff80808080808080808080c623eddfc1bba2a0919b3e832dc6ddacb0dc9dfcdd01442f"
    "92d095a7dda2ffdf800195f1ffdde0ffff808080b88deafddedcffc78080805163b5f2b0bef9caffff800181e8fdd6c5"
    "f2c4ffff806379d2fac9c6ffca808080175ba3f2aabbf7d2ffff8001c8f6ffeaff80808080806db2f1ffe7f5ffff8080"
    "802c82c9fdcdc0ffff8080800184effbdbd1ffa58080805e88e1fbdabeffff8080801664aef5baa1ffc780808001b6f9"
    "ffe8eb80808080807c8ff1ffe3ea8080808080234db5fbc1d3ffcd808080019df7ffece7ffff808080798debffe1e3ff"
    "ff8080802d63bcfbc3d9ffe08080800101fbffd5ff8080808080cb01f8ffff8080808080808901b1ffe0ff8080808080"
    "fd09f8fbcfd0ffc0808080af0de0f3c1b9f9c6ffff804911abdda1b3eca7ffea80015ff7fdd4b7ffff808080ef5af4fa"
    "d3d1ffff8080809b4dc3f8bcc3ffff8080800118effbdadbffcd808080c933dbffc4ba8080808080452ebeefc9daffe4"
    "80808001bffbffff808080808080dfa5f9ffd5ff80808080808d7cf8ffff8080808080800110f8ffff808080808080be"
    "24e6ffecff80808080809501ff808080808080808001e2ff8080808080808080f7c0ff8080808080808080f080ff8080"
    "8080808080800186fcffff808080808080d53efaffff808080808080375dff8080808080808080808080808080808080"
    "808080808080808080808080808080808080808080808080ca18d5ebbabfdca0f0afff7e26b6e8a9b8e4aeffbb803d2e"
    "8adb97b2f0aaffd8800170e6fac7bff79fffff80a66de4fcd3d7ffae808080274da2e8acb4f5b2ffff800134dcf6c6c7"
    "f9dcffff807c4abff3b7c1faddffff80184782db9aaaf3b6ffff8001b6e1f9dbf0ffe08080809596e2fcd8cdffab8080"
    "801c6caaf2b7c2fedfffff800151e6fccccbffc08080807b66d1f7bcc4ffe9808080145f99f3a4adffcb80808001def8"
    "ffd8d58080808080a8aff6fcebcdffff8080802f74d7ffd3d4ffff8080800179ecfdd4d6ffff8080808d54d5fcc9caff"
    "db8080802a50a0f0a2b9ffcd8080800101ff8080808080808080f401ff8080808080808080ee01ff8080808080808080";

static const uint8_t vp8_default_mv_probs[2][19] = {
    {162, 128, 225, 146, 172, 147, 214, 39, 156, 128,
     129, 132, 75, 145, 178, 206, 239, 254, 254},
    {164, 128, 204, 170, 119, 235, 140, 230, 228, 128,
     130, 130, 74, 148, 180, 203, 236, 254, 254},
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
                            int require_requests, uint32_t count,
                            struct mapped_buffer *mapped)
{
    struct v4l2_requestbuffers request;

    if (count == 0U || count > 2U) {
        errno = EINVAL;
        return -1;
    }
    memset(mapped, 0, sizeof(*mapped) * count);
    memset(&request, 0, sizeof(request));
    request.count = count;
    request.type = type;
    request.memory = V4L2_MEMORY_MMAP;
    if (xioctl(fd, VIDIOC_REQBUFS, &request) < 0)
        return -1;
    mapped[0].allocated = 1;
    mapped[0].type = type;
    if (request.count < count) {
        errno = ENOMEM;
        return -1;
    }
    if ((request.capabilities & V4L2_BUF_CAP_SUPPORTS_MMAP) == 0U ||
        (require_requests &&
         (request.capabilities & V4L2_BUF_CAP_SUPPORTS_REQUESTS) == 0U)) {
        errno = ENOTSUP;
        return -1;
    }

    for (uint32_t index = 0; index < count; ++index) {
        struct v4l2_buffer buffer;
        struct v4l2_plane planes[VIDEO_MAX_PLANES];

        mapped[index].type = type;
        memset(&buffer, 0, sizeof(buffer));
        memset(planes, 0, sizeof(planes));
        buffer.type = type;
        buffer.memory = V4L2_MEMORY_MMAP;
        buffer.index = index;
        buffer.length = VIDEO_MAX_PLANES;
        buffer.m.planes = planes;
        if (xioctl(fd, VIDIOC_QUERYBUF, &buffer) < 0 || buffer.length != 1U) {
            errno = EPROTO;
            return -1;
        }
        mapped[index].length = planes[0].length;
        mapped[index].address =
            mmap(NULL, mapped[index].length, PROT_READ | PROT_WRITE,
                 MAP_SHARED, fd, (off_t)planes[0].m.mem_offset);
        if (mapped[index].address == MAP_FAILED) {
            mapped[index].address = NULL;
            return -1;
        }
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

static int hex_nibble(char value)
{
    if (value >= '0' && value <= '9')
        return value - '0';
    if (value >= 'a' && value <= 'f')
        return value - 'a' + 10;
    return -1;
}

static int decode_hex(const char *hex, uint8_t *output, size_t output_size)
{
    for (size_t i = 0; i < output_size; ++i) {
        int high = hex_nibble(hex[i * 2U]);
        int low = hex_nibble(hex[i * 2U + 1U]);

        if (high < 0 || low < 0) {
            errno = EINVAL;
            return -1;
        }
        output[i] = (uint8_t)((high << 4) | low);
    }
    if (hex[output_size * 2U] != '\0') {
        errno = EOVERFLOW;
        return -1;
    }
    return 0;
}

static int is_h264_mode(enum codec_mode mode)
{
    return mode == CODEC_H264 || mode == CODEC_H264_REFERENCE;
}

static int is_reference_mode(enum codec_mode mode)
{
    return mode == CODEC_H264_REFERENCE || mode == CODEC_VP8_REFERENCE;
}

static void fill_h264_sps(struct v4l2_ctrl_h264_sps *sps,
                          int reference_mode)
{
    memset(sps, 0, sizeof(*sps));
    sps->profile_idc = 66U;
    sps->constraint_set_flags = V4L2_H264_SPS_CONSTRAINT_SET0_FLAG |
                                V4L2_H264_SPS_CONSTRAINT_SET1_FLAG;
    sps->level_idc = 10U;
    sps->chroma_format_idc = 1U;
    sps->pic_order_cnt_type = 2U;
    sps->max_num_ref_frames = reference_mode ? 1U : 0U;
    sps->pic_width_in_mbs_minus1 = 3U;
    sps->pic_height_in_map_units_minus1 = 3U;
    sps->flags = V4L2_H264_SPS_FLAG_FRAME_MBS_ONLY |
                 V4L2_H264_SPS_FLAG_DIRECT_8X8_INFERENCE;
}

static void fill_h264_pps(struct v4l2_ctrl_h264_pps *pps)
{
    memset(pps, 0, sizeof(*pps));
    pps->pic_init_qp_minus26 = -16;
    pps->chroma_qp_index_offset = -2;
    pps->second_chroma_qp_index_offset = -2;
    pps->flags = V4L2_H264_PPS_FLAG_DEBLOCKING_FILTER_CONTROL_PRESENT;
}

static void fill_h264_scaling(
    struct v4l2_ctrl_h264_scaling_matrix *scaling)
{
    memset(scaling, 16, sizeof(*scaling));
}

static void fill_h264_decode(struct v4l2_ctrl_h264_decode_params *decode,
                             int reference_mode, uint32_t frame_index)
{
    memset(decode, 0, sizeof(*decode));
    if (!reference_mode || frame_index == 0U) {
        decode->nal_ref_idc = 3U;
        decode->dec_ref_pic_marking_bit_size = 2U;
        decode->flags = V4L2_H264_DECODE_PARAM_FLAG_IDR_PIC;
        return;
    }
    decode->nal_ref_idc = 2U;
    decode->frame_num = 1U;
    decode->top_field_order_cnt = 2;
    decode->bottom_field_order_cnt = 2;
    decode->dec_ref_pic_marking_bit_size = 1U;
    decode->flags = V4L2_H264_DECODE_PARAM_FLAG_PFRAME;
    decode->dpb[0].reference_ts = REFERENCE_TIMESTAMP_NS;
    decode->dpb[0].pic_num = 0U;
    decode->dpb[0].frame_num = 0U;
    decode->dpb[0].fields = V4L2_H264_FRAME_REF;
    decode->dpb[0].top_field_order_cnt = 0;
    decode->dpb[0].bottom_field_order_cnt = 0;
    decode->dpb[0].flags = V4L2_H264_DPB_ENTRY_FLAG_VALID |
                           V4L2_H264_DPB_ENTRY_FLAG_ACTIVE;
}

static int fill_vp8_keyframe(struct v4l2_ctrl_vp8_frame *frame)
{
    static const uint8_t keyframe_y_mode_probs[4] = {145, 156, 163, 128};
    static const uint8_t keyframe_uv_mode_probs[3] = {142, 114, 183};

    _Static_assert(sizeof(frame->entropy.coeff_probs) == 1056U,
                   "unexpected VP8 coefficient table size");
    memset(frame, 0, sizeof(*frame));
    frame->segment.flags = V4L2_VP8_SEGMENT_FLAG_DELTA_VALUE_MODE;
    frame->lf.ref_frm_delta[0] = 2;
    frame->lf.ref_frm_delta[2] = -2;
    frame->lf.ref_frm_delta[3] = -2;
    frame->lf.mb_mode_delta[0] = 4;
    frame->lf.mb_mode_delta[1] = -2;
    frame->lf.mb_mode_delta[2] = 2;
    frame->lf.mb_mode_delta[3] = 4;
    frame->lf.level = 1U;
    frame->lf.flags = V4L2_VP8_LF_ADJ_ENABLE | V4L2_VP8_LF_DELTA_UPDATE;
    frame->quant.y_ac_qi = 4U;
    if (decode_hex(vp8_default_coeff_probs_hex,
                   &frame->entropy.coeff_probs[0][0][0][0],
                   sizeof(frame->entropy.coeff_probs)) < 0)
        return -1;
    memcpy(frame->entropy.y_mode_probs, keyframe_y_mode_probs,
           sizeof(keyframe_y_mode_probs));
    memcpy(frame->entropy.uv_mode_probs, keyframe_uv_mode_probs,
           sizeof(keyframe_uv_mode_probs));
    memcpy(frame->entropy.mv_probs, vp8_default_mv_probs,
           sizeof(vp8_default_mv_probs));
    frame->coder_state.range = 192U;
    frame->coder_state.value = 22U;
    frame->coder_state.bit_count = 3U;
    frame->width = WIDTH;
    frame->height = HEIGHT;
    frame->prob_skip_false = 48U;
    frame->num_dct_parts = 1U;
    frame->first_part_size = 24U;
    frame->first_part_header_bits = 109U;
    frame->dct_part_sizes[0] = 11U;
    frame->last_frame_ts = UINT32_MAX;
    frame->golden_frame_ts = UINT32_MAX;
    frame->alt_frame_ts = UINT32_MAX;
    frame->flags = V4L2_VP8_FRAME_FLAG_KEY_FRAME |
                   V4L2_VP8_FRAME_FLAG_SHOW_FRAME |
                   V4L2_VP8_FRAME_FLAG_MB_NO_SKIP_COEFF;
    return 0;
}

static int fill_vp8_inter_frame(struct v4l2_ctrl_vp8_frame *frame)
{
    static const uint8_t inter_y_mode_probs[4] = {112, 86, 140, 37};
    static const uint8_t inter_uv_mode_probs[3] = {162, 101, 204};

    _Static_assert(sizeof(frame->entropy.coeff_probs) == 1056U,
                   "unexpected VP8 coefficient table size");
    memset(frame, 0, sizeof(*frame));
    frame->segment.flags = V4L2_VP8_SEGMENT_FLAG_DELTA_VALUE_MODE;
    frame->lf.ref_frm_delta[0] = 2;
    frame->lf.ref_frm_delta[2] = -2;
    frame->lf.ref_frm_delta[3] = -2;
    frame->lf.mb_mode_delta[0] = 4;
    frame->lf.mb_mode_delta[1] = -2;
    frame->lf.mb_mode_delta[2] = 2;
    frame->lf.mb_mode_delta[3] = 4;
    frame->lf.level = 5U;
    frame->lf.flags = V4L2_VP8_LF_ADJ_ENABLE;
    frame->quant.y_ac_qi = 43U;
    if (decode_hex(vp8_default_coeff_probs_hex,
                   &frame->entropy.coeff_probs[0][0][0][0],
                   sizeof(frame->entropy.coeff_probs)) < 0)
        return -1;
    memcpy(frame->entropy.y_mode_probs, inter_y_mode_probs,
           sizeof(inter_y_mode_probs));
    memcpy(frame->entropy.uv_mode_probs, inter_uv_mode_probs,
           sizeof(inter_uv_mode_probs));
    memcpy(frame->entropy.mv_probs, vp8_default_mv_probs,
           sizeof(vp8_default_mv_probs));
    frame->coder_state.range = 177U;
    frame->coder_state.value = 2U;
    frame->coder_state.bit_count = 2U;
    frame->width = WIDTH;
    frame->height = HEIGHT;
    frame->prob_skip_false = 1U;
    frame->prob_intra = 1U;
    frame->prob_last = 255U;
    frame->prob_gf = 128U;
    frame->num_dct_parts = 1U;
    frame->first_part_size = 14U;
    frame->first_part_header_bits = 86U;
    frame->dct_part_sizes[0] = 1U;
    frame->last_frame_ts = REFERENCE_TIMESTAMP_NS;
    frame->golden_frame_ts = REFERENCE_TIMESTAMP_NS;
    frame->alt_frame_ts = REFERENCE_TIMESTAMP_NS;
    frame->flags = V4L2_VP8_FRAME_FLAG_SHOW_FRAME |
                   V4L2_VP8_FRAME_FLAG_MB_NO_SKIP_COEFF;
    return 0;
}

static int set_initial_controls(int video_fd, enum codec_mode mode)
{
    struct v4l2_ctrl_h264_sps sps;
    struct v4l2_ctrl_vp8_frame vp8;
    struct v4l2_ext_control controls_array[3];
    struct v4l2_ext_controls controls;

    memset(controls_array, 0, sizeof(controls_array));
    if (is_h264_mode(mode)) {
        fill_h264_sps(&sps, is_reference_mode(mode));
        controls_array[0].id = V4L2_CID_STATELESS_H264_DECODE_MODE;
        controls_array[0].value = V4L2_STATELESS_H264_DECODE_MODE_FRAME_BASED;
        controls_array[1].id = V4L2_CID_STATELESS_H264_START_CODE;
        controls_array[1].value = V4L2_STATELESS_H264_START_CODE_ANNEX_B;
        controls_array[2].id = V4L2_CID_STATELESS_H264_SPS;
        controls_array[2].size = sizeof(sps);
        controls_array[2].ptr = &sps;
    } else {
        if (fill_vp8_keyframe(&vp8) < 0)
            return -1;
        controls_array[0].id = V4L2_CID_STATELESS_VP8_FRAME;
        controls_array[0].size = sizeof(vp8);
        controls_array[0].ptr = &vp8;
    }

    memset(&controls, 0, sizeof(controls));
    controls.which = V4L2_CTRL_WHICH_CUR_VAL;
    controls.count = is_h264_mode(mode) ? 3U : 1U;
    controls.controls = controls_array;
    return xioctl(video_fd, VIDIOC_S_EXT_CTRLS, &controls);
}

static int set_request_controls(int video_fd, int request_fd,
                                enum codec_mode mode, uint32_t frame_index)
{
    struct v4l2_ctrl_h264_sps sps;
    struct v4l2_ctrl_h264_pps pps;
    struct v4l2_ctrl_h264_scaling_matrix scaling;
    struct v4l2_ctrl_h264_decode_params decode;
    struct v4l2_ctrl_vp8_frame vp8;
    struct v4l2_ext_control controls_array[4];
    struct v4l2_ext_controls controls;

    memset(controls_array, 0, sizeof(controls_array));
    if (is_h264_mode(mode)) {
        fill_h264_sps(&sps, is_reference_mode(mode));
        fill_h264_pps(&pps);
        fill_h264_scaling(&scaling);
        fill_h264_decode(&decode, is_reference_mode(mode), frame_index);
        controls_array[0].id = V4L2_CID_STATELESS_H264_SPS;
        controls_array[0].size = sizeof(sps);
        controls_array[0].ptr = &sps;
        controls_array[1].id = V4L2_CID_STATELESS_H264_PPS;
        controls_array[1].size = sizeof(pps);
        controls_array[1].ptr = &pps;
        controls_array[2].id = V4L2_CID_STATELESS_H264_SCALING_MATRIX;
        controls_array[2].size = sizeof(scaling);
        controls_array[2].ptr = &scaling;
        controls_array[3].id = V4L2_CID_STATELESS_H264_DECODE_PARAMS;
        controls_array[3].size = sizeof(decode);
        controls_array[3].ptr = &decode;
    } else {
        if (mode == CODEC_VP8_REFERENCE && frame_index == 1U) {
            if (fill_vp8_inter_frame(&vp8) < 0)
                return -1;
        } else if (fill_vp8_keyframe(&vp8) < 0) {
            return -1;
        }
        controls_array[0].id = V4L2_CID_STATELESS_VP8_FRAME;
        controls_array[0].size = sizeof(vp8);
        controls_array[0].ptr = &vp8;
    }

    memset(&controls, 0, sizeof(controls));
    controls.which = V4L2_CTRL_WHICH_REQUEST_VAL;
    controls.request_fd = request_fd;
    controls.count = is_h264_mode(mode) ? 4U : 1U;
    controls.controls = controls_array;
    return xioctl(video_fd, VIDIOC_S_EXT_CTRLS, &controls);
}

static int queue_capture(int fd, uint32_t index,
                         const struct mapped_buffer *mapped)
{
    struct v4l2_buffer buffer;
    struct v4l2_plane plane;

    memset(&buffer, 0, sizeof(buffer));
    memset(&plane, 0, sizeof(plane));
    buffer.type = V4L2_BUF_TYPE_VIDEO_CAPTURE_MPLANE;
    buffer.memory = V4L2_MEMORY_MMAP;
    buffer.index = index;
    buffer.length = 1;
    buffer.m.planes = &plane;
    plane.length = (uint32_t)mapped->length;
    return xioctl(fd, VIDIOC_QBUF, &buffer);
}

static int queue_output(int fd, int request_fd, uint32_t frame_index,
                        const struct mapped_buffer *mapped,
                        size_t payload_size)
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
    buffer.timestamp.tv_sec = (time_t)frame_index + 1;
    plane.length = (uint32_t)mapped->length;
    if (payload_size > UINT32_MAX) {
        errno = EOVERFLOW;
        return -1;
    }
    plane.bytesused = (uint32_t)payload_size;
    return xioctl(fd, VIDIOC_QBUF, &buffer);
}

static int validate_reference_capture(const struct v4l2_buffer *buffer,
                                      uint32_t expected_index,
                                      uint32_t frame_index)
{
    const time_t expected_seconds = (time_t)frame_index + 1;

    if (buffer->index != expected_index ||
        buffer->timestamp.tv_sec != expected_seconds ||
        buffer->timestamp.tv_usec != 0) {
        errno = EPROTO;
        return -1;
    }
    if (frame_index == 0U &&
        ((uint64_t)buffer->timestamp.tv_sec * UINT64_C(1000000000) +
         (uint64_t)buffer->timestamp.tv_usec * UINT64_C(1000)) !=
            REFERENCE_TIMESTAMP_NS) {
        errno = EPROTO;
        return -1;
    }
    return 0;
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
    struct mapped_buffer capture_buffers[2];
    struct v4l2_format output_format;
    struct v4l2_format capture_format;
    struct v4l2_buffer dequeued_capture;
    struct v4l2_buffer dequeued_output;
    struct v4l2_plane capture_plane;
    struct v4l2_plane output_plane;
    enum codec_mode mode;
    const uint8_t *payload;
    const char *codec_name;
    size_t payload_size;
    size_t payload_bytes_total = 0U;
    uint32_t output_fourcc;
    uint32_t capture_buffer_count = 1U;
    uint32_t requested_frames = 1U;
    uint32_t verified_frames = 0U;
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
    memset(capture_buffers, 0, sizeof(capture_buffers));
    if (argc != 4 && argc != 5) {
        fprintf(stderr,
                "usage: %s h264|vp8|h264-ref|vp8-ref /dev/videoN /dev/mediaN [frames]\n",
                argv[0]);
        return 64;
    }
    if (argc == 5) {
        char *end = NULL;
        unsigned long value;

        errno = 0;
        value = strtoul(argv[4], &end, 10);
        if (errno != 0 || end == argv[4] || *end != '\0' || value < 1UL ||
            value > MAX_FRAME_COUNT) {
            fprintf(stderr, "ERROR: frames must be an integer from 1 to %u\n",
                    MAX_FRAME_COUNT);
            return 64;
        }
        requested_frames = (uint32_t)value;
    }
    if (strcmp(argv[1], "h264") == 0) {
        mode = CODEC_H264;
        codec_name = "h264";
        output_fourcc = V4L2_PIX_FMT_H264_SLICE;
        payload = h264_slice_data;
        payload_size = sizeof(h264_slice_data);
    } else if (strcmp(argv[1], "vp8") == 0) {
        mode = CODEC_VP8;
        codec_name = "vp8";
        output_fourcc = V4L2_PIX_FMT_VP8_FRAME;
        payload = vp8_frame_data;
        payload_size = sizeof(vp8_frame_data);
    } else if (strcmp(argv[1], "h264-ref") == 0) {
        if (argc != 4) {
            fprintf(stderr, "ERROR: h264-ref always decodes exactly two frames\n");
            return 64;
        }
        mode = CODEC_H264_REFERENCE;
        codec_name = "h264-ref";
        output_fourcc = V4L2_PIX_FMT_H264_SLICE;
        payload = h264_reference_idr_data;
        payload_size = sizeof(h264_reference_idr_data);
        requested_frames = 2U;
        capture_buffer_count = 2U;
    } else if (strcmp(argv[1], "vp8-ref") == 0) {
        if (argc != 4) {
            fprintf(stderr, "ERROR: vp8-ref always decodes exactly two frames\n");
            return 64;
        }
        mode = CODEC_VP8_REFERENCE;
        codec_name = "vp8-ref";
        output_fourcc = V4L2_PIX_FMT_VP8_FRAME;
        payload = vp8_frame_data;
        payload_size = sizeof(vp8_frame_data);
        requested_frames = 2U;
        capture_buffer_count = 2U;
    } else {
        fprintf(stderr, "ERROR: codec must be h264, vp8, h264-ref or vp8-ref\n");
        return 64;
    }
    setvbuf(stdout, NULL, _IOLBF, 0);
    if (install_signal_handlers() < 0) {
        fprintf(stderr, "ERROR: install signal handlers: %s\n", strerror(errno));
        return 1;
    }

    video_fd = open(argv[2], O_RDWR | O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW);
    if (video_fd < 0) {
        fprintf(stderr, "ERROR: open decoder: %s\n", strerror(errno));
        operation_failed = 1;
        goto cleanup;
    }
    media_fd = open(argv[3], O_RDWR | O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW);
    if (media_fd < 0) {
        fprintf(stderr, "ERROR: open media request device: %s\n", strerror(errno));
        operation_failed = 1;
        goto cleanup;
    }
    if (validate_decoder_identity(video_fd, argv[2]) < 0 ||
        validate_media_identity(media_fd, argv[3]) < 0) {
        fprintf(stderr, "ERROR: validate Hantro identities: %s\n", strerror(errno));
        operation_failed = 1;
        goto cleanup;
    }
    if (has_format(video_fd, output_type, output_fourcc) != 1 ||
        has_format(video_fd, capture_type, V4L2_PIX_FMT_NV12) != 1 ||
        frame_size_supported(video_fd, output_fourcc) != 1) {
        fprintf(stderr,
                "ERROR: required %s/NV12 format is unavailable: %s\n",
                codec_name, strerror(errno));
        operation_failed = 1;
        goto cleanup;
    }
    if (set_format(video_fd, output_type, output_fourcc, &output_format) < 0 ||
        set_initial_controls(video_fd, mode) < 0 ||
        set_format(video_fd, capture_type, V4L2_PIX_FMT_NV12,
                   &capture_format) < 0) {
        fprintf(stderr, "ERROR: negotiate %s/NV12 formats: %s\n",
                codec_name, strerror(errno));
        operation_failed = 1;
        goto cleanup;
    }
    printf("R46H_HANTRO_CODEC_FORMAT codec=%s width=%u height=%u output_size=%u capture_stride=%u capture_size=%u\n",
           codec_name, output_format.fmt.pix_mp.width,
           output_format.fmt.pix_mp.height,
           output_format.fmt.pix_mp.plane_fmt[0].sizeimage,
           capture_format.fmt.pix_mp.plane_fmt[0].bytesperline,
           capture_format.fmt.pix_mp.plane_fmt[0].sizeimage);
    if (output_format.fmt.pix_mp.plane_fmt[0].sizeimage < payload_size ||
        capture_format.fmt.pix_mp.plane_fmt[0].sizeimage < LOGICAL_NV12_SIZE) {
        errno = EOVERFLOW;
        fprintf(stderr, "ERROR: negotiated buffers are too small: %s\n",
                strerror(errno));
        operation_failed = 1;
        goto cleanup;
    }
    if (allocate_and_map(video_fd, output_type, 1, 1U, &output_buffer) < 0 ||
        allocate_and_map(video_fd, capture_type, 0, capture_buffer_count,
                         capture_buffers) < 0) {
        fprintf(stderr, "ERROR: allocate decoder buffers: %s\n", strerror(errno));
        operation_failed = 1;
        goto cleanup;
    }
    if (payload_size > output_buffer.length) {
        errno = EOVERFLOW;
        operation_failed = 1;
        goto cleanup;
    }
    if (xioctl(media_fd, MEDIA_IOC_REQUEST_ALLOC, &request_fd) < 0 ||
        request_fd < 0) {
        fprintf(stderr, "ERROR: allocate decoder request: %s\n", strerror(errno));
        operation_failed = 1;
        goto cleanup;
    }

    for (uint32_t frame_index = 0; frame_index < requested_frames;
         ++frame_index) {
        uint32_t capture_index = is_reference_mode(mode) ? frame_index : 0U;
        struct mapped_buffer *capture_buffer = &capture_buffers[capture_index];

        if (mode == CODEC_H264_REFERENCE) {
            if (frame_index == 0U) {
                payload = h264_reference_idr_data;
                payload_size = sizeof(h264_reference_idr_data);
            } else {
                payload = h264_reference_p_data;
                payload_size = sizeof(h264_reference_p_data);
            }
        } else if (mode == CODEC_VP8_REFERENCE) {
            if (frame_index == 0U) {
                payload = vp8_frame_data;
                payload_size = sizeof(vp8_frame_data);
            } else {
                payload = vp8_inter_frame_data;
                payload_size = sizeof(vp8_inter_frame_data);
            }
        }
        if (payload_size > output_buffer.length) {
            errno = EOVERFLOW;
            operation_failed = 1;
            goto cleanup;
        }
        if (frame_index > 0U &&
            xioctl(request_fd, MEDIA_REQUEST_IOC_REINIT, NULL) < 0) {
            fprintf(stderr, "ERROR: reinitialize decoder request at frame %u: %s\n",
                    frame_index + 1U, strerror(errno));
            operation_failed = 1;
            goto cleanup;
        }
        memset(output_buffer.address, 0, output_buffer.length);
        memcpy(output_buffer.address, payload, payload_size);
        memset(capture_buffer->address, 0x5a, capture_buffer->length);
        if (set_request_controls(video_fd, request_fd, mode, frame_index) < 0 ||
            queue_capture(video_fd, capture_index, capture_buffer) < 0 ||
            queue_output(video_fd, request_fd, frame_index, &output_buffer,
                         payload_size) < 0) {
            fprintf(stderr, "ERROR: prepare decoder request at frame %u: %s\n",
                    frame_index + 1U, strerror(errno));
            operation_failed = 1;
            goto cleanup;
        }
        if (frame_index == 0U) {
            if (stream_change(video_fd, capture_type, 1) < 0) {
                fprintf(stderr, "ERROR: start decoder capture queue: %s\n",
                        strerror(errno));
                operation_failed = 1;
                goto cleanup;
            }
            capture_streaming = 1;
            if (stream_change(video_fd, output_type, 1) < 0) {
                fprintf(stderr, "ERROR: start decoder output queue: %s\n",
                        strerror(errno));
                operation_failed = 1;
                goto cleanup;
            }
            output_streaming = 1;
        }
        if (xioctl(request_fd, MEDIA_REQUEST_IOC_QUEUE, NULL) < 0 ||
            wait_for_request(request_fd) < 0 ||
            dequeue_buffer(video_fd, capture_type, &dequeued_capture,
                           &capture_plane) < 0 ||
            dequeue_buffer(video_fd, output_type, &dequeued_output,
                           &output_plane) < 0) {
            fprintf(stderr, "ERROR: execute decoder request at frame %u: %s\n",
                    frame_index + 1U, strerror(errno));
            operation_failed = 1;
            goto cleanup;
        }
        if ((dequeued_capture.flags & V4L2_BUF_FLAG_ERROR) != 0U ||
            (dequeued_output.flags & V4L2_BUF_FLAG_ERROR) != 0U) {
            errno = EIO;
            fprintf(stderr, "ERROR: decoder returned an error buffer at frame %u\n",
                    frame_index + 1U);
            operation_failed = 1;
            goto cleanup;
        }
        if (is_reference_mode(mode) &&
            validate_reference_capture(&dequeued_capture, capture_index,
                                       frame_index) < 0) {
            fprintf(stderr,
                    "ERROR: reference capture identity changed at frame %u: %s\n",
                    frame_index + 1U, strerror(errno));
            operation_failed = 1;
            goto cleanup;
        }
        if (validate_nv12(capture_buffer, &capture_format, &capture_plane,
                          &decoded_hash) < 0) {
            fprintf(stderr, "ERROR: validate decoded NV12 at frame %u: %s\n",
                    frame_index + 1U, strerror(errno));
            operation_failed = 1;
            goto cleanup;
        }
        payload_bytes_total += payload_size;
        verified_frames = frame_index + 1U;
        if (verified_frames == requested_frames || verified_frames % 30U == 0U)
            printf("R46H_HANTRO_CODEC_PROGRESS codec=%s frames_verified=%u frames_requested=%u\n",
                   codec_name, verified_frames, requested_frames);
    }
    if (validate_decoder_identity(video_fd, argv[2]) < 0 ||
        validate_media_identity(media_fd, argv[3]) < 0) {
        fprintf(stderr, "ERROR: Hantro identity changed during decode: %s\n",
                strerror(errno));
        operation_failed = 1;
        goto cleanup;
    }

cleanup:
    if (stop_requested && !operation_failed) {
        errno = ECANCELED;
        operation_failed = 1;
    }
    saved_errno = errno;
    if (output_streaming && stream_change(video_fd, output_type, 0) < 0)
        cleanup_failed = 1;
    if (capture_streaming && stream_change(video_fd, capture_type, 0) < 0)
        cleanup_failed = 1;
    if (request_fd >= 0 && close(request_fd) < 0)
        cleanup_failed = 1;
    if (video_fd >= 0) {
        for (uint32_t index = capture_buffer_count; index > 0U; --index) {
            if (release_buffer(video_fd, &capture_buffers[index - 1U]) < 0)
                cleanup_failed = 1;
        }
        if (release_buffer(video_fd, &output_buffer) < 0)
            cleanup_failed = 1;
    }
    if (media_fd >= 0 && close(media_fd) < 0)
        cleanup_failed = 1;
    if (video_fd >= 0 && close(video_fd) < 0)
        cleanup_failed = 1;
    errno = saved_errno;

    if (!operation_failed && !cleanup_failed) {
        printf("R46H_HANTRO_CODEC_DECODE result=pass codec=%s width=%u height=%u payload_bytes=%zu payload_bytes_total=%zu frames_verified=%u reference_frames=%s nv12_bytes=%u fnv1a64=%016llx cleanup=pass\n",
               codec_name, WIDTH, HEIGHT, payload_size, payload_bytes_total,
               verified_frames, is_reference_mode(mode) ? "verified" : "none",
               LOGICAL_NV12_SIZE, (unsigned long long)decoded_hash);
        return 0;
    }
    printf("R46H_HANTRO_CODEC_DECODE result=fail codec=%s cleanup=%s\n",
           codec_name, cleanup_failed ? "fail" : "pass");
    return 1;
}
