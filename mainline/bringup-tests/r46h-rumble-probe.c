#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <linux/input.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#define RUMBLE_DURATION_MS 750U
#define RUMBLE_MAGNITUDE UINT16_C(0x8000)
#define BITS_PER_LONG (sizeof(unsigned long) * 8U)
#define BITS_TO_LONGS(count) (((count) + BITS_PER_LONG - 1U) / BITS_PER_LONG)

static volatile sig_atomic_t caught_signal;

static void handle_signal(int signal_number)
{
    caught_signal = signal_number;
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
    return 0;
}

static int bit_is_set(const unsigned long *bits, unsigned int bit)
{
    return (bits[bit / BITS_PER_LONG] &
            (1UL << (bit % BITS_PER_LONG))) != 0UL;
}

static int write_event(int fd, uint16_t code, int32_t value)
{
    struct input_event event;
    ssize_t written;

    memset(&event, 0, sizeof(event));
    event.type = EV_FF;
    event.code = code;
    event.value = value;
    do {
        written = write(fd, &event, sizeof(event));
    } while (written < 0 && errno == EINTR && caught_signal == 0);
    if (written != (ssize_t)sizeof(event)) {
        if (written >= 0)
            errno = EIO;
        return -1;
    }
    return 0;
}

static int sleep_ms(unsigned int duration_ms)
{
    struct timespec remaining;

    remaining.tv_sec = duration_ms / 1000U;
    remaining.tv_nsec = (long)(duration_ms % 1000U) * 1000000L;
    while (nanosleep(&remaining, &remaining) < 0) {
        if (errno != EINTR)
            return -1;
        if (caught_signal != 0)
            return 1;
    }
    return 0;
}

static int validate_identity(int fd, const char *path, int *effect_slots)
{
    struct stat path_stat;
    struct stat fd_stat;
    struct input_id id;
    char name[128];
    unsigned long event_bits[BITS_TO_LONGS(EV_MAX + 1U)];
    unsigned long ff_bits[BITS_TO_LONGS(FF_MAX + 1U)];

    if (lstat(path, &path_stat) < 0)
        return -1;
    if (!S_ISCHR(path_stat.st_mode)) {
        errno = ENODEV;
        return -1;
    }
    if (fstat(fd, &fd_stat) < 0)
        return -1;
    if (!S_ISCHR(fd_stat.st_mode) ||
        path_stat.st_dev != fd_stat.st_dev ||
        path_stat.st_ino != fd_stat.st_ino ||
        path_stat.st_rdev != fd_stat.st_rdev) {
        errno = ESTALE;
        return -1;
    }

    memset(name, 0, sizeof(name));
    if (ioctl(fd, EVIOCGNAME(sizeof(name)), name) < 0)
        return -1;
    name[sizeof(name) - 1U] = '\0';
    if (strcmp(name, "pwm-vibrator") != 0) {
        errno = ENODEV;
        return -1;
    }

    memset(&id, 0, sizeof(id));
    if (ioctl(fd, EVIOCGID, &id) < 0)
        return -1;
    if (id.bustype != BUS_HOST || id.vendor != 0U || id.product != 0U ||
        id.version != 0U) {
        errno = ENODEV;
        return -1;
    }

    memset(event_bits, 0, sizeof(event_bits));
    memset(ff_bits, 0, sizeof(ff_bits));
    if (ioctl(fd, EVIOCGBIT(0, sizeof(event_bits)), event_bits) < 0 ||
        ioctl(fd, EVIOCGBIT(EV_FF, sizeof(ff_bits)), ff_bits) < 0 ||
        ioctl(fd, EVIOCGEFFECTS, effect_slots) < 0)
        return -1;
    if (!bit_is_set(event_bits, EV_FF) || !bit_is_set(ff_bits, FF_RUMBLE) ||
        *effect_slots < 1) {
        errno = ENOTSUP;
        return -1;
    }

    printf("R46H_RUMBLE_IDENTITY name=%s bustype=0x%04x effects=%d "
           "event_inode=%llu event_rdev=%llu\n",
           name, id.bustype, *effect_slots,
           (unsigned long long)fd_stat.st_ino,
           (unsigned long long)fd_stat.st_rdev);
    return 0;
}

int main(int argc, char **argv)
{
    struct ff_effect effect;
    int effect_slots = 0;
    int effect_uploaded = 0;
    int effect_started = 0;
    int cleanup_failed = 0;
    int sleep_result;
    int fd = -1;
    int result = 1;

    if (argc != 2) {
        fprintf(stderr, "usage: %s PWM_VIBRATOR_EVENT\n", argv[0]);
        return 64;
    }
    if (install_signal_handlers() < 0) {
        fprintf(stderr, "ERROR: install signal handlers: %s\n",
                strerror(errno));
        return 1;
    }

    fd = open(argv[1], O_RDWR | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) {
        fprintf(stderr, "ERROR: open vibrator: %s\n", strerror(errno));
        goto cleanup;
    }
    if (validate_identity(fd, argv[1], &effect_slots) < 0) {
        fprintf(stderr, "ERROR: vibrator identity: %s\n", strerror(errno));
        goto cleanup;
    }
    if (caught_signal != 0)
        goto cleanup;

    memset(&effect, 0, sizeof(effect));
    effect.type = FF_RUMBLE;
    effect.id = -1;
    effect.replay.length = RUMBLE_DURATION_MS;
    effect.replay.delay = 0;
    effect.u.rumble.strong_magnitude = RUMBLE_MAGNITUDE;
    effect.u.rumble.weak_magnitude = 0;
    if (ioctl(fd, EVIOCSFF, &effect) < 0) {
        fprintf(stderr, "ERROR: upload rumble effect: %s\n", strerror(errno));
        goto cleanup;
    }
    effect_uploaded = 1;
    if (effect.id < 0 || effect.id >= effect_slots) {
        errno = EPROTO;
        fprintf(stderr, "ERROR: invalid uploaded effect id=%d slots=%d\n",
                effect.id, effect_slots);
        goto cleanup;
    }
    if (caught_signal != 0)
        goto cleanup;
    if (write_event(fd, (uint16_t)effect.id, 1) < 0) {
        fprintf(stderr, "ERROR: start rumble effect: %s\n", strerror(errno));
        goto cleanup;
    }
    effect_started = 1;
    printf("R46H_RUMBLE_STARTED effect_id=%d duration_ms=%u magnitude=%u\n",
           effect.id, RUMBLE_DURATION_MS, RUMBLE_MAGNITUDE);
    fflush(stdout);

    sleep_result = sleep_ms(RUMBLE_DURATION_MS + 100U);
    if (sleep_result < 0) {
        fprintf(stderr, "ERROR: wait for rumble: %s\n", strerror(errno));
        goto cleanup;
    }
    if (sleep_result > 0 || caught_signal != 0)
        goto cleanup;
    result = 0;

cleanup:
    if (fd >= 0 && effect_started &&
        write_event(fd, (uint16_t)effect.id, 0) < 0)
        cleanup_failed = 1;
    if (fd >= 0 && effect_started && sleep_ms(50U) < 0)
        cleanup_failed = 1;
    if (fd >= 0 && effect_uploaded && ioctl(fd, EVIOCRMFF, effect.id) < 0)
        cleanup_failed = 1;
    if (fd >= 0 && close(fd) < 0)
        cleanup_failed = 1;
    if (cleanup_failed)
        result = 1;

    if (result == 0) {
        if (printf("R46H_RUMBLE result=pass duration_ms=%u magnitude=%u "
                   "cleanup=pass operator_observation=required\n",
                   RUMBLE_DURATION_MS, RUMBLE_MAGNITUDE) < 0)
            return 1;
        return 0;
    }
    if (caught_signal != 0) {
        printf("R46H_RUMBLE result=fail reason=signal-%d cleanup=%s\n",
               caught_signal, cleanup_failed ? "fail" : "pass");
        return 128 + caught_signal;
    }
    printf("R46H_RUMBLE result=fail reason=probe-error cleanup=%s\n",
           cleanup_failed ? "fail" : "pass");
    return 1;
}
