#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <linux/gpio.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/utsname.h>
#include <time.h>
#include <unistd.h>

#define EXPECTED_RELEASE "6.12.99-r46h-mainline-v0.8-bootloader-handoff"
#define GPIO_CHIP_PATH "/dev/gpiochip0"
#define DC_DETECT_OFFSET 11U
#define SAMPLE_COUNT 5U
#define SAMPLE_INTERVAL_MS 20U

#define CHARGER_ROOT "/sys/class/power_supply/rk817-charger"
#define BATTERY_ROOT "/sys/class/power_supply/rk817-battery"
#define CHARGER_DT_ROOT                                                     \
    "/sys/firmware/devicetree/base/i2c@ff180000/pmic@20/charger"

static volatile sig_atomic_t caught_signal;

struct power_snapshot {
    long long charger_online;
    long long charger_voltage_uv;
    long long battery_present;
    long long battery_capacity;
    long long battery_voltage_uv;
    long long battery_current_ua;
    char charger_usb_type[64];
    char battery_status[64];
};

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

static int open_bound_path(const char *path, mode_t expected_type)
{
    struct stat path_stat;
    struct stat fd_stat;
    int fd;

    if (lstat(path, &path_stat) < 0)
        return -1;
    if ((path_stat.st_mode & S_IFMT) != expected_type) {
        errno = ENODEV;
        return -1;
    }
    fd = open(path, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0)
        return -1;
    if (fstat(fd, &fd_stat) < 0) {
        int saved_errno = errno;

        close(fd);
        errno = saved_errno;
        return -1;
    }
    if ((fd_stat.st_mode & S_IFMT) != expected_type ||
        path_stat.st_dev != fd_stat.st_dev ||
        path_stat.st_ino != fd_stat.st_ino ||
        (expected_type == S_IFCHR && path_stat.st_rdev != fd_stat.st_rdev)) {
        close(fd);
        errno = ESTALE;
        return -1;
    }
    return fd;
}

static int read_small_file(const char *path, char *buffer, size_t capacity)
{
    ssize_t count;
    size_t used = 0U;
    int fd;

    if (capacity < 2U) {
        errno = EINVAL;
        return -1;
    }
    fd = open_bound_path(path, S_IFREG);
    if (fd < 0)
        return -1;
    for (;;) {
        count = read(fd, buffer + used, capacity - 1U - used);
        if (count < 0 && errno == EINTR && caught_signal == 0)
            continue;
        if (count < 0) {
            int saved_errno = errno;

            close(fd);
            errno = saved_errno;
            return -1;
        }
        if (count == 0)
            break;
        used += (size_t)count;
        if (used == capacity - 1U) {
            char extra;

            do {
                count = read(fd, &extra, 1U);
            } while (count < 0 && errno == EINTR && caught_signal == 0);
            if (count != 0) {
                int saved_errno = count < 0 ? errno : EOVERFLOW;

                close(fd);
                errno = saved_errno;
                return -1;
            }
            break;
        }
    }
    if (close(fd) < 0)
        return -1;
    while (used > 0U && (buffer[used - 1U] == '\n' ||
                         buffer[used - 1U] == '\r'))
        used--;
    if (used == 0U || memchr(buffer, '\0', used) != NULL) {
        errno = EPROTO;
        return -1;
    }
    buffer[used] = '\0';
    return 0;
}

static int read_integer(const char *path, long long *value)
{
    char buffer[64];
    char *end;
    long long parsed;

    if (read_small_file(path, buffer, sizeof(buffer)) < 0)
        return -1;
    errno = 0;
    parsed = strtoll(buffer, &end, 10);
    if (errno != 0 || end == buffer || *end != '\0') {
        errno = EPROTO;
        return -1;
    }
    *value = parsed;
    return 0;
}

static int read_snapshot(struct power_snapshot *snapshot)
{
    if (read_integer(CHARGER_ROOT "/online", &snapshot->charger_online) < 0 ||
        read_integer(CHARGER_ROOT "/voltage_avg",
                     &snapshot->charger_voltage_uv) < 0 ||
        read_small_file(CHARGER_ROOT "/usb_type", snapshot->charger_usb_type,
                        sizeof(snapshot->charger_usb_type)) < 0 ||
        read_integer(BATTERY_ROOT "/present", &snapshot->battery_present) < 0 ||
        read_integer(BATTERY_ROOT "/capacity", &snapshot->battery_capacity) < 0 ||
        read_integer(BATTERY_ROOT "/voltage_avg",
                     &snapshot->battery_voltage_uv) < 0 ||
        read_integer(BATTERY_ROOT "/current_avg",
                     &snapshot->battery_current_ua) < 0 ||
        read_small_file(BATTERY_ROOT "/status", snapshot->battery_status,
                        sizeof(snapshot->battery_status)) < 0)
        return -1;
    if ((snapshot->charger_online != 0 && snapshot->charger_online != 1) ||
        snapshot->charger_voltage_uv < 0 ||
        snapshot->battery_present != 1 ||
        snapshot->battery_capacity < 0 || snapshot->battery_capacity > 100 ||
        snapshot->battery_voltage_uv < 3000000 ||
        snapshot->battery_voltage_uv > 5000000 ||
        snapshot->battery_current_ua < -10000000 ||
        snapshot->battery_current_ua > 10000000) {
        errno = ERANGE;
        return -1;
    }
    return 0;
}

static int critical_snapshot_equal(const struct power_snapshot *left,
                                   const struct power_snapshot *right)
{
    return left->charger_online == right->charger_online &&
           left->charger_voltage_uv == right->charger_voltage_uv &&
           left->battery_present == right->battery_present &&
           left->battery_capacity == right->battery_capacity &&
           strcmp(left->charger_usb_type, right->charger_usb_type) == 0 &&
           strcmp(left->battery_status, right->battery_status) == 0;
}

static int require_exact_blob(const char *path, const unsigned char *expected,
                              size_t expected_size)
{
    unsigned char buffer[128];
    unsigned char extra;
    size_t used = 0U;
    ssize_t count;
    int fd;

    if (expected_size > sizeof(buffer)) {
        errno = EOVERFLOW;
        return -1;
    }
    fd = open_bound_path(path, S_IFREG);
    if (fd < 0)
        return -1;
    while (used < expected_size) {
        count = read(fd, buffer + used, expected_size - used);
        if (count < 0 && errno == EINTR && caught_signal == 0)
            continue;
        if (count <= 0) {
            int saved_errno = count < 0 ? errno : EPROTO;

            close(fd);
            errno = saved_errno;
            return -1;
        }
        used += (size_t)count;
    }
    do {
        count = read(fd, &extra, 1U);
    } while (count < 0 && errno == EINTR && caught_signal == 0);
    if (count != 0) {
        int saved_errno = count < 0 ? errno : EOVERFLOW;

        close(fd);
        errno = saved_errno;
        return -1;
    }
    if (close(fd) < 0)
        return -1;
    if (memcmp(buffer, expected, expected_size) != 0) {
        errno = ENODEV;
        return -1;
    }
    return 0;
}

static int require_exact_target(void)
{
    static const unsigned char expected_model[] = "GameConsole R46H";
    static const unsigned char expected_compatible[] =
        "rockchip,rk3326-r46h-linux\0rockchip,rk3326";
    static const char *const absent_properties[] = {
        CHARGER_DT_ROOT "/dc-det-gpios",
        CHARGER_DT_ROOT "/dc_det_gpio",
        CHARGER_DT_ROOT "/extcon",
    };
    struct utsname uts;
    struct stat path_stat;
    size_t index;

    if (uname(&uts) < 0)
        return -1;
    if (strcmp(uts.release, EXPECTED_RELEASE) != 0) {
        errno = ENODEV;
        return -1;
    }

    if (require_exact_blob("/proc/device-tree/model", expected_model,
                           sizeof(expected_model)) < 0)
        return -1;
    if (require_exact_blob("/proc/device-tree/compatible", expected_compatible,
                           sizeof(expected_compatible)) < 0)
        return -1;

    if (lstat(CHARGER_DT_ROOT, &path_stat) < 0 ||
        !S_ISDIR(path_stat.st_mode)) {
        errno = ENODEV;
        return -1;
    }
    for (index = 0U;
         index < sizeof(absent_properties) / sizeof(absent_properties[0]);
         index++) {
        if (lstat(absent_properties[index], &path_stat) == 0) {
            errno = EEXIST;
            return -1;
        }
        if (errno != ENOENT)
            return -1;
    }
    return 0;
}

static int observe_dc_line(unsigned int *observed_level,
                           struct gpiochip_info *chip_info)
{
    struct gpio_v2_line_request request;
    struct gpio_v2_line_info line_info;
    struct gpio_v2_line_values values;
    unsigned int level = 0U;
    unsigned int sample;
    int chip_fd = -1;
    int line_fd = -1;
    int result = -1;

    chip_fd = open_bound_path(GPIO_CHIP_PATH, S_IFCHR);
    if (chip_fd < 0)
        goto cleanup;
    memset(chip_info, 0, sizeof(*chip_info));
    if (ioctl(chip_fd, GPIO_GET_CHIPINFO_IOCTL, chip_info) < 0)
        goto cleanup;
    if (chip_info->lines <= DC_DETECT_OFFSET || chip_info->name[0] == '\0') {
        errno = ENODEV;
        goto cleanup;
    }

    memset(&line_info, 0, sizeof(line_info));
    line_info.offset = DC_DETECT_OFFSET;
    if (ioctl(chip_fd, GPIO_V2_GET_LINEINFO_IOCTL, &line_info) < 0)
        goto cleanup;
    if ((line_info.flags & GPIO_V2_LINE_FLAG_USED) != 0U) {
        errno = EBUSY;
        goto cleanup;
    }

    memset(&request, 0, sizeof(request));
    request.offsets[0] = DC_DETECT_OFFSET;
    request.num_lines = 1U;
    request.config.flags = GPIO_V2_LINE_FLAG_INPUT;
    memcpy(request.consumer, "r46h-dc-observe",
           sizeof("r46h-dc-observe"));
    if (ioctl(chip_fd, GPIO_V2_GET_LINE_IOCTL, &request) < 0)
        goto cleanup;
    line_fd = request.fd;
    if (line_fd < 0 || fcntl(line_fd, F_GETFD) < 0)
        goto cleanup;

    for (sample = 0U; sample < SAMPLE_COUNT; sample++) {
        memset(&values, 0, sizeof(values));
        values.mask = UINT64_C(1);
        if (ioctl(line_fd, GPIO_V2_LINE_GET_VALUES_IOCTL, &values) < 0)
            goto cleanup;
        if (sample == 0U)
            level = (values.bits & UINT64_C(1)) != 0U ? 1U : 0U;
        else if (((values.bits & UINT64_C(1)) != 0U ? 1U : 0U) != level) {
            errno = EAGAIN;
            goto cleanup;
        }
        if (sample + 1U < SAMPLE_COUNT) {
            int sleep_result = sleep_ms(SAMPLE_INTERVAL_MS);

            if (sleep_result != 0) {
                if (sleep_result > 0)
                    errno = EINTR;
                goto cleanup;
            }
        }
    }
    *observed_level = level;
    result = 0;

cleanup:
    if (line_fd >= 0 && close(line_fd) < 0)
        result = -1;
    if (chip_fd >= 0 && close(chip_fd) < 0)
        result = -1;
    return result;
}

int main(int argc, char **argv)
{
    struct power_snapshot before;
    struct power_snapshot after;
    struct gpiochip_info chip_info;
    unsigned int expected_level;
    unsigned int observed_level = 0U;
    const char *phase;

    if (argc != 2 ||
        (strcmp(argv[1], "--expect-connected-mismatch") != 0 &&
         strcmp(argv[1], "--expect-disconnected") != 0)) {
        fprintf(stderr,
                "usage: %s --expect-connected-mismatch|--expect-disconnected\n",
                argv[0]);
        return 64;
    }
    phase = strcmp(argv[1], "--expect-connected-mismatch") == 0 ?
                "connected-mismatch" : "disconnected";
    expected_level = strcmp(phase, "connected-mismatch") == 0 ? 1U : 0U;

    if (geteuid() != 0) {
        fprintf(stderr, "ERROR: probe must run as root\n");
        return 77;
    }
    if (install_signal_handlers() < 0) {
        fprintf(stderr, "ERROR: install signal handlers: %s\n",
                strerror(errno));
        return 1;
    }
    if (require_exact_target() < 0) {
        fprintf(stderr, "ERROR: exact target identity: %s\n", strerror(errno));
        return 1;
    }
    if (read_snapshot(&before) < 0) {
        fprintf(stderr, "ERROR: read power state before probe: %s\n",
                strerror(errno));
        return 1;
    }
    if (caught_signal != 0)
        return 128 + caught_signal;

    memset(&chip_info, 0, sizeof(chip_info));
    if (observe_dc_line(&observed_level, &chip_info) < 0) {
        fprintf(stderr, "ERROR: observe GPIO0_B3: %s\n", strerror(errno));
        return 1;
    }
    if (caught_signal != 0)
        return 128 + caught_signal;
    if (read_snapshot(&after) < 0) {
        fprintf(stderr, "ERROR: read power state after probe: %s\n",
                strerror(errno));
        return 1;
    }
    if (!critical_snapshot_equal(&before, &after)) {
        fprintf(stderr, "ERROR: power state changed during bounded observation\n");
        return 1;
    }
    if (observed_level != expected_level) {
        fprintf(stderr,
                "ERROR: USB-DC detect level mismatch expected=%u observed=%u\n",
                expected_level, observed_level);
        return 1;
    }
    if (before.charger_online != 0 || before.charger_voltage_uv != 0 ||
        strcmp(before.battery_status, "Discharging") != 0) {
        fprintf(stderr,
                "ERROR: mainline offline mismatch is not present "
                "online=%lld voltage_uv=%lld status=%s\n",
                before.charger_online, before.charger_voltage_uv,
                before.battery_status);
        return 1;
    }

    printf("R46H_CHARGER_OBSERVE identity=pass release=%s "
           "gpiochip=%s label=%s line=GPIO0_B3 offset=%u samples=%u\n",
           EXPECTED_RELEASE, chip_info.name, chip_info.label,
           DC_DETECT_OFFSET, SAMPLE_COUNT);
    printf("R46H_CHARGER_OBSERVE phase=%s dc_gpio_level=%u "
           "charger_online=%lld charger_voltage_uv=%lld usb_type=%s "
           "battery_status=%s battery_capacity=%lld "
           "battery_voltage_uv=%lld battery_current_ua=%lld\n",
           phase, observed_level, before.charger_online,
           before.charger_voltage_uv, before.charger_usb_type,
           before.battery_status, before.battery_capacity,
           before.battery_voltage_uv, before.battery_current_ua);
    printf("R46H_CHARGER_OBSERVE result=pass phase=%s "
           "finding=vendor-dc-detect-not-consumed-by-mainline "
           "drive_output=no persistent_change=no cleanup=pass\n",
           phase);
    return 0;
}
