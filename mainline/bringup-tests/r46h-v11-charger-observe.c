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

#define EXPECTED_RELEASE "6.12.99-r46h-mainline-v0.11-usb-dc-detect"
#define GPIO_CHIP_PATH "/dev/gpiochip0"
#define DC_DETECT_OFFSET 11U
#define SAMPLE_COUNT 5U
#define SAMPLE_INTERVAL_MS 100U

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
    while (used > 0U &&
           (buffer[used - 1U] == '\n' || buffer[used - 1U] == '\r'))
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

static int require_claimed_dc_line(char *consumer, size_t consumer_size)
{
    struct gpio_v2_line_info line_info;
    struct gpiochip_info chip_info;
    int chip_fd;
    int result = -1;

    chip_fd = open_bound_path(GPIO_CHIP_PATH, S_IFCHR);
    if (chip_fd < 0)
        return -1;
    memset(&chip_info, 0, sizeof(chip_info));
    if (ioctl(chip_fd, GPIO_GET_CHIPINFO_IOCTL, &chip_info) < 0)
        goto cleanup;
    if (strcmp(chip_info.name, "gpiochip0") != 0 ||
        strcmp(chip_info.label, "gpio0") != 0 ||
        chip_info.lines <= DC_DETECT_OFFSET) {
        errno = ENODEV;
        goto cleanup;
    }

    memset(&line_info, 0, sizeof(line_info));
    line_info.offset = DC_DETECT_OFFSET;
    if (ioctl(chip_fd, GPIO_V2_GET_LINEINFO_IOCTL, &line_info) < 0)
        goto cleanup;
    if ((line_info.flags & GPIO_V2_LINE_FLAG_USED) == 0U ||
        strcmp(line_info.consumer, "rk817-dc-det") != 0) {
        errno = ENODEV;
        goto cleanup;
    }
    if (strlen(line_info.consumer) + 1U > consumer_size) {
        errno = EOVERFLOW;
        goto cleanup;
    }
    memcpy(consumer, line_info.consumer, strlen(line_info.consumer) + 1U);
    result = 0;

cleanup:
    if (close(chip_fd) < 0)
        result = -1;
    return result;
}

static int require_exact_target(void)
{
    static const unsigned char expected_model[] = "GameConsole R46H";
    static const unsigned char expected_compatible[] =
        "rockchip,rk3326-r46h-linux\0rockchip,rk3326";
    static const unsigned char expected_dc_det[] = {
        0x00, 0x00, 0x00, 0x50, 0x00, 0x00,
        0x00, 0x0b, 0x00, 0x00, 0x00, 0x00,
    };
    struct utsname uts;
    struct stat module_stat;

    if (uname(&uts) < 0)
        return -1;
    if (strcmp(uts.release, EXPECTED_RELEASE) != 0) {
        errno = ENODEV;
        return -1;
    }
    if (require_exact_blob("/proc/device-tree/model", expected_model,
                           sizeof(expected_model)) < 0 ||
        require_exact_blob("/proc/device-tree/compatible", expected_compatible,
                           sizeof(expected_compatible)) < 0 ||
        require_exact_blob(CHARGER_DT_ROOT "/dc-det-gpios", expected_dc_det,
                           sizeof(expected_dc_det)) < 0)
        return -1;
    if (lstat("/sys/module/rk817_charger", &module_stat) < 0 ||
        !S_ISDIR(module_stat.st_mode)) {
        errno = ENODEV;
        return -1;
    }
    return 0;
}

static int read_dc_irq_count(unsigned long long *count)
{
    FILE *stream;
    char *line = NULL;
    size_t capacity = 0U;
    int found = 0;
    int result = -1;

    stream = fopen("/proc/interrupts", "re");
    if (stream == NULL)
        return -1;
    while (getline(&line, &capacity, stream) >= 0) {
        char *cursor;
        char *end;
        unsigned long long total = 0U;

        if (strstr(line, "rk817_dc_det") == NULL)
            continue;
        if (found != 0) {
            errno = EEXIST;
            goto cleanup;
        }
        cursor = strchr(line, ':');
        if (cursor == NULL) {
            errno = EPROTO;
            goto cleanup;
        }
        cursor++;
        for (;;) {
            unsigned long long value;

            while (*cursor == ' ' || *cursor == '\t')
                cursor++;
            if (*cursor < '0' || *cursor > '9')
                break;
            errno = 0;
            value = strtoull(cursor, &end, 10);
            if (errno != 0 || end == cursor || UINT64_MAX - total < value) {
                errno = EPROTO;
                goto cleanup;
            }
            total += value;
            cursor = end;
        }
        *count = total;
        found = 1;
    }
    if (ferror(stream) != 0)
        goto cleanup;
    if (found == 0) {
        errno = ENOENT;
        goto cleanup;
    }
    result = 0;

cleanup:
    free(line);
    if (fclose(stream) != 0)
        result = -1;
    return result;
}

int main(int argc, char **argv)
{
    struct power_snapshot snapshot;
    unsigned long long irq_count;
    long long expected_online;
    char consumer[GPIO_MAX_NAME_SIZE];
    const char *phase;
    unsigned int sample;

    if (argc == 2 && strcmp(argv[1], "--help") == 0) {
        printf("usage: %s --expect-disconnected|--expect-connected\n", argv[0]);
        return 0;
    }
    if (argc != 2 ||
        (strcmp(argv[1], "--expect-disconnected") != 0 &&
         strcmp(argv[1], "--expect-connected") != 0)) {
        fprintf(stderr,
                "usage: %s --expect-disconnected|--expect-connected\n",
                argv[0]);
        return 64;
    }
    phase = strcmp(argv[1], "--expect-connected") == 0 ?
                "connected" : "disconnected";
    expected_online = strcmp(phase, "connected") == 0 ? 1 : 0;

    if (geteuid() != 0) {
        fprintf(stderr, "ERROR: observer must run as root\n");
        return 77;
    }
    if (install_signal_handlers() < 0) {
        fprintf(stderr, "ERROR: install signal handlers: %s\n",
                strerror(errno));
        return 1;
    }
    if (require_exact_target() < 0) {
        fprintf(stderr, "ERROR: exact v0.11 target identity: %s\n",
                strerror(errno));
        return 1;
    }
    memset(consumer, 0, sizeof(consumer));
    if (require_claimed_dc_line(consumer, sizeof(consumer)) < 0) {
        fprintf(stderr, "ERROR: GPIO0_B3 charger ownership: %s\n",
                strerror(errno));
        return 1;
    }

    memset(&snapshot, 0, sizeof(snapshot));
    for (sample = 0U; sample < SAMPLE_COUNT; sample++) {
        if (read_snapshot(&snapshot) < 0) {
            fprintf(stderr, "ERROR: read power state sample %u: %s\n",
                    sample + 1U, strerror(errno));
            return 1;
        }
        if (snapshot.charger_online != expected_online) {
            fprintf(stderr,
                    "ERROR: charger online mismatch phase=%s expected=%lld "
                    "observed=%lld sample=%u\n",
                    phase, expected_online, snapshot.charger_online,
                    sample + 1U);
            return 1;
        }
        if (caught_signal != 0)
            return 128 + caught_signal;
        if (sample + 1U < SAMPLE_COUNT &&
            sleep_ms(SAMPLE_INTERVAL_MS) != 0)
            return caught_signal != 0 ? 128 + caught_signal : 1;
    }
    if (read_dc_irq_count(&irq_count) < 0) {
        fprintf(stderr, "ERROR: read rk817_dc_det interrupt count: %s\n",
                strerror(errno));
        return 1;
    }

    printf("R46H_V11_CHARGER identity=pass release=%s "
           "gpio=GPIO0_B3 consumer=%s samples=%u\n",
           EXPECTED_RELEASE, consumer, SAMPLE_COUNT);
    printf("R46H_V11_CHARGER phase=%s charger_online=%lld "
           "charger_voltage_uv=%lld usb_type=%s battery_status=%s "
           "battery_capacity=%lld battery_voltage_uv=%lld "
           "battery_current_ua=%lld dc_irq_count=%llu\n",
           phase, snapshot.charger_online, snapshot.charger_voltage_uv,
           snapshot.charger_usb_type, snapshot.battery_status,
           snapshot.battery_capacity, snapshot.battery_voltage_uv,
           snapshot.battery_current_ua, irq_count);
    printf("R46H_V11_CHARGER result=pass phase=%s "
           "online-contract=pass charge-current-safety=not-proved "
           "persistent-write=no\n",
           phase);
    return 0;
}
