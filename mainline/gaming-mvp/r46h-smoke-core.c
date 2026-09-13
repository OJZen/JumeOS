#include <libretro-common/libretro.h>

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

#define WIDTH 320
#define HEIGHT 240
#define AUDIO_FRAMES 800

static retro_environment_t environment_callback;
static retro_video_refresh_t video_callback;
static retro_audio_sample_batch_t audio_batch_callback;
static retro_input_poll_t input_poll_callback;
static retro_input_state_t input_state_callback;
static uint32_t framebuffer[WIDTH * HEIGHT];
static int16_t audio_buffer[AUDIO_FRAMES * 2];
static uint64_t frame_number;
static uint32_t audio_phase;

unsigned retro_api_version(void) { return RETRO_API_VERSION; }

void retro_set_environment(retro_environment_t callback) {
    bool support_no_game = true;
    environment_callback = callback;
    callback(RETRO_ENVIRONMENT_SET_SUPPORT_NO_GAME, &support_no_game);
}

void retro_set_video_refresh(retro_video_refresh_t callback) {
    video_callback = callback;
}

void retro_set_audio_sample(retro_audio_sample_t callback) { (void)callback; }

void retro_set_audio_sample_batch(retro_audio_sample_batch_t callback) {
    audio_batch_callback = callback;
}

void retro_set_input_poll(retro_input_poll_t callback) {
    input_poll_callback = callback;
}

void retro_set_input_state(retro_input_state_t callback) {
    input_state_callback = callback;
}

void retro_init(void) {
    enum retro_pixel_format format = RETRO_PIXEL_FORMAT_XRGB8888;
    environment_callback(RETRO_ENVIRONMENT_SET_PIXEL_FORMAT, &format);
}

void retro_deinit(void) {}

void retro_get_system_info(struct retro_system_info *info) {
    memset(info, 0, sizeof(*info));
    info->library_name = "R46H Hardware Smoke";
    info->library_version = "1.1";
    info->need_fullpath = false;
    info->block_extract = false;
}

void retro_get_system_av_info(struct retro_system_av_info *info) {
    memset(info, 0, sizeof(*info));
    info->geometry.base_width = WIDTH;
    info->geometry.base_height = HEIGHT;
    info->geometry.max_width = WIDTH;
    info->geometry.max_height = HEIGHT;
    info->geometry.aspect_ratio = 4.0f / 3.0f;
    info->timing.fps = 60.0;
    info->timing.sample_rate = 48000.0;
}

void retro_set_controller_port_device(unsigned port, unsigned device) {
    (void)port;
    (void)device;
}

void retro_reset(void) {
    frame_number = 0;
    audio_phase = 0;
}

static bool pressed(unsigned id) {
    return input_state_callback != NULL &&
           input_state_callback(0, RETRO_DEVICE_JOYPAD, 0, id) != 0;
}

static int analog(unsigned index, unsigned id) {
    if (input_state_callback == NULL)
        return 0;
    return input_state_callback(0, RETRO_DEVICE_ANALOG, index, id);
}

static void render_frame(void) {
    static const uint32_t colors[8] = {
        0x00ffffff, 0x00ffff00, 0x0000ffff, 0x0000ff00,
        0x00ff00ff, 0x00ff0000, 0x000000ff, 0x00000000,
    };
    int marker_x = WIDTH / 2;
    int marker_y = 80;
    int left_x = WIDTH / 4 +
                 analog(RETRO_DEVICE_INDEX_ANALOG_LEFT,
                        RETRO_DEVICE_ID_ANALOG_X) * 50 / 32768;
    int left_y = 195 +
                 analog(RETRO_DEVICE_INDEX_ANALOG_LEFT,
                        RETRO_DEVICE_ID_ANALOG_Y) * 30 / 32768;
    int right_x = WIDTH * 3 / 4 +
                  analog(RETRO_DEVICE_INDEX_ANALOG_RIGHT,
                         RETRO_DEVICE_ID_ANALOG_X) * 50 / 32768;
    int right_y = 195 +
                  analog(RETRO_DEVICE_INDEX_ANALOG_RIGHT,
                         RETRO_DEVICE_ID_ANALOG_Y) * 30 / 32768;
    bool invert = pressed(RETRO_DEVICE_ID_JOYPAD_A);

    if (pressed(RETRO_DEVICE_ID_JOYPAD_LEFT))
        marker_x -= 70;
    if (pressed(RETRO_DEVICE_ID_JOYPAD_RIGHT))
        marker_x += 70;
    if (pressed(RETRO_DEVICE_ID_JOYPAD_UP))
        marker_y -= 50;
    if (pressed(RETRO_DEVICE_ID_JOYPAD_DOWN))
        marker_y += 50;

    for (int y = 0; y < HEIGHT; ++y) {
        for (int x = 0; x < WIDTH; ++x) {
            uint32_t color = colors[(unsigned)x * 8U / WIDTH];
            if (y >= 155)
                color = 0x00181818U;
            if (invert)
                color ^= 0x00ffffffU;
            if (x >= marker_x - 9 && x <= marker_x + 9 &&
                y >= marker_y - 9 && y <= marker_y + 9)
                color = ((frame_number / 15U) & 1U) ? 0x00ffffffU : 0x00000000U;
            if (x >= left_x - 7 && x <= left_x + 7 &&
                y >= left_y - 7 && y <= left_y + 7)
                color = 0x0000ffffU;
            if (x >= right_x - 7 && x <= right_x + 7 &&
                y >= right_y - 7 && y <= right_y + 7)
                color = 0x00ff00ffU;
            framebuffer[(size_t)y * WIDTH + (size_t)x] = color;
        }
    }
}

static void render_audio(void) {
    const uint32_t phase_step = 440U;
    for (size_t index = 0; index < AUDIO_FRAMES; ++index) {
        int16_t sample;
        audio_phase = (audio_phase + phase_step) % 48000U;
        sample = audio_phase < 24000U ? 5000 : -5000;
        audio_buffer[index * 2] = sample;
        audio_buffer[index * 2 + 1] = sample;
    }
}

void retro_run(void) {
    if (input_poll_callback != NULL)
        input_poll_callback();
    render_frame();
    render_audio();
    if (video_callback != NULL)
        video_callback(framebuffer, WIDTH, HEIGHT, WIDTH * sizeof(uint32_t));
    if (audio_batch_callback != NULL)
        audio_batch_callback(audio_buffer, AUDIO_FRAMES);
    ++frame_number;
}

size_t retro_serialize_size(void) { return 0; }
bool retro_serialize(void *data, size_t size) {
    (void)data;
    (void)size;
    return false;
}
bool retro_unserialize(const void *data, size_t size) {
    (void)data;
    (void)size;
    return false;
}
void retro_cheat_reset(void) {}
void retro_cheat_set(unsigned index, bool enabled, const char *code) {
    (void)index;
    (void)enabled;
    (void)code;
}
bool retro_load_game(const struct retro_game_info *game) { return game == NULL; }
bool retro_load_game_special(unsigned type, const struct retro_game_info *info,
                             size_t count) {
    (void)type;
    (void)info;
    (void)count;
    return false;
}
void retro_unload_game(void) {}
unsigned retro_get_region(void) { return RETRO_REGION_NTSC; }
void *retro_get_memory_data(unsigned id) {
    (void)id;
    return NULL;
}
size_t retro_get_memory_size(unsigned id) {
    (void)id;
    return 0;
}
