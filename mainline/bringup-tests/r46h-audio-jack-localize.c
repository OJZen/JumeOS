// SPDX-License-Identifier: MIT
// Bounded, read-only evdev/GPIO localization probe for R46H jack detection.

#define _GNU_SOURCE

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/input.h>
#include <poll.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <sys/utsname.h>
#include <time.h>
#include <unistd.h>

#define PROBE_ID "r46h-audio-jack-localize-v0.1"
#define EXPECTED_RELEASE "6.12.99-r46h-mainline-v0.10-adc-full-range"
#define EXPECTED_MODEL "GameConsole R46H"
#define EXPECTED_NAME "rk817_int Headphones"
#define GPIO_DEBUG_PATH "/sys/kernel/debug/gpio"
#define GPIO_LINE_NAME "Headphone detection"
#define GPIO_NUMBER_TEXT "gpio-86"
#define OBSERVE_SECONDS 30
#define GPIO_SAMPLE_MILLISECONDS 20
#define EVDEV_SETTLE_MILLISECONDS 500
#define INPUT_MAJOR 13
#define GPIO_BUFFER_SIZE 65536
#define ARRAY_SIZE(array) (sizeof(array) / sizeof((array)[0]))
#define BITS_PER_LONG (sizeof(unsigned long) * 8U)
#define BITS_TO_LONGS(count) (((count) + BITS_PER_LONG - 1U) / BITS_PER_LONG)

struct switch_observation {
	int initial_state;
	int last_state;
	int final_state;
	unsigned int insertions;
	unsigned int removals;
	unsigned int syn_dropped;
};

struct gpio_observation {
	int initial_raw;
	int last_raw;
	int final_raw;
	unsigned int insertions;
	unsigned int removals;
	unsigned int samples;
};

static volatile sig_atomic_t stop_signal;

static void handle_signal(int signum)
{
	stop_signal = signum;
}

static bool bit_is_set(const unsigned long *bits, unsigned int bit)
{
	return (bits[bit / BITS_PER_LONG] & (1UL << (bit % BITS_PER_LONG))) != 0;
}

static bool event_leaf_is_safe(const char *name)
{
	const char *cursor;

	if (strncmp(name, "event", 5) != 0 || name[5] == '\0')
		return false;
	for (cursor = name + 5; *cursor != '\0'; cursor++) {
		if (*cursor < '0' || *cursor > '9')
			return false;
	}
	return true;
}

static int require_runtime_identity(void)
{
	char model[sizeof(EXPECTED_MODEL) + 1U];
	struct utsname system_name;
	struct stat metadata;
	ssize_t bytes;
	int fd;

	if (uname(&system_name) != 0)
		return -1;
	if (strcmp(system_name.release, EXPECTED_RELEASE) != 0) {
		errno = ESTALE;
		return -1;
	}
	fd = open("/proc/device-tree/model", O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
	if (fd < 0)
		return -1;
	if (fstat(fd, &metadata) != 0 || !S_ISREG(metadata.st_mode)) {
		close(fd);
		errno = ESTALE;
		return -1;
	}
	memset(model, 0, sizeof(model));
	bytes = read(fd, model, sizeof(model));
	if (close(fd) != 0 && bytes >= 0)
		return -1;
	if (bytes != (ssize_t)sizeof(EXPECTED_MODEL) ||
	    memcmp(model, EXPECTED_MODEL, sizeof(EXPECTED_MODEL)) != 0) {
		errno = ESTALE;
		return -1;
	}
	return 0;
}

static int64_t monotonic_milliseconds(void)
{
	struct timespec value;

	if (clock_gettime(CLOCK_MONOTONIC, &value) != 0)
		return -1;
	return (int64_t)value.tv_sec * 1000 + value.tv_nsec / 1000000;
}

static int discover_headphone_event(char *selected_path, size_t path_size)
{
	DIR *directory;
	struct dirent *entry;
	int selected_fd = -1;

	directory = opendir("/dev/input");
	if (directory == NULL)
		return -1;
	for (;;) {
		char path[128];
		char input_name[256];
		struct stat before;
		struct stat after;
		int fd;
		int length;

		errno = 0;
		entry = readdir(directory);
		if (entry == NULL) {
			if (errno != 0)
				goto fail;
			break;
		}
		if (!event_leaf_is_safe(entry->d_name))
			continue;
		length = snprintf(path, sizeof(path), "/dev/input/%s", entry->d_name);
		if (length < 0 || (size_t)length >= sizeof(path)) {
			errno = ENAMETOOLONG;
			goto fail;
		}
		if (lstat(path, &before) != 0 || !S_ISCHR(before.st_mode) ||
		    major(before.st_rdev) != INPUT_MAJOR)
			continue;
		fd = open(path, O_RDONLY | O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW);
		if (fd < 0)
			continue;
		if (fstat(fd, &after) != 0 || !S_ISCHR(after.st_mode) ||
		    after.st_dev != before.st_dev || after.st_ino != before.st_ino ||
		    after.st_rdev != before.st_rdev) {
			close(fd);
			continue;
		}
		memset(input_name, 0, sizeof(input_name));
		if (ioctl(fd, EVIOCGNAME(sizeof(input_name)), input_name) < 0 ||
		    strcmp(input_name, EXPECTED_NAME) != 0) {
			close(fd);
			continue;
		}
		if (selected_fd >= 0) {
			close(fd);
			errno = ENOTUNIQ;
			goto fail;
		}
		if (strlen(path) + 1 > path_size) {
			close(fd);
			errno = ENAMETOOLONG;
			goto fail;
		}
		strcpy(selected_path, path);
		selected_fd = fd;
	}
	closedir(directory);
	if (selected_fd < 0)
		errno = ENODEV;
	return selected_fd;

fail:
	if (selected_fd >= 0)
		close(selected_fd);
	closedir(directory);
	return -1;
}

static int require_headphone_capability(int fd)
{
	unsigned long event_types[BITS_TO_LONGS(EV_MAX + 1U)];
	unsigned long switches[BITS_TO_LONGS(SW_MAX + 1U)];

	memset(event_types, 0, sizeof(event_types));
	if (ioctl(fd, EVIOCGBIT(0, sizeof(event_types)), event_types) < 0)
		return -1;
	if (!bit_is_set(event_types, EV_SYN) || !bit_is_set(event_types, EV_SW)) {
		errno = ENOTSUP;
		return -1;
	}
	memset(switches, 0, sizeof(switches));
	if (ioctl(fd, EVIOCGBIT(EV_SW, sizeof(switches)), switches) < 0)
		return -1;
	if (!bit_is_set(switches, SW_HEADPHONE_INSERT)) {
		errno = ENOTSUP;
		return -1;
	}
	return 0;
}

static int query_headphone_state(int fd)
{
	unsigned long states[BITS_TO_LONGS(SW_MAX + 1U)];

	memset(states, 0, sizeof(states));
	if (ioctl(fd, EVIOCGSW(sizeof(states)), states) < 0)
		return -1;
	return bit_is_set(states, SW_HEADPHONE_INSERT) ? 1 : 0;
}

static int process_switch_event(const struct input_event *event,
				struct switch_observation *observation)
{
	if (event->type == EV_SYN && event->code == SYN_DROPPED) {
		observation->syn_dropped++;
		return 0;
	}
	if (event->type != EV_SW || event->code != SW_HEADPHONE_INSERT)
		return 0;
	if (event->value != 0 && event->value != 1) {
		errno = EPROTO;
		return -1;
	}
	if (event->value == observation->last_state)
		return 0;
	if (event->value == 1) {
		observation->insertions++;
		printf("R46H_AUDIO_JACK_LOCALIZE_EVDEV state=inserted count=%u\n",
		       observation->insertions);
	} else {
		observation->removals++;
		printf("R46H_AUDIO_JACK_LOCALIZE_EVDEV state=removed count=%u\n",
		       observation->removals);
	}
	observation->last_state = event->value;
	fflush(stdout);
	return 0;
}

static int query_gpio_raw(void)
{
	char buffer[GPIO_BUFFER_SIZE];
	struct stat metadata;
	ssize_t total = 0;
	char *cursor;
	unsigned int matches = 0;
	int raw = -1;
	int fd;

	fd = open(GPIO_DEBUG_PATH, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
	if (fd < 0)
		return -1;
	if (fstat(fd, &metadata) != 0 || !S_ISREG(metadata.st_mode))
		goto fail;
	while (total < (ssize_t)sizeof(buffer) - 1) {
		ssize_t bytes = read(fd, buffer + total, sizeof(buffer) - 1U - (size_t)total);

		if (bytes < 0) {
			if (errno == EINTR)
				continue;
			goto fail;
		}
		if (bytes == 0)
			break;
		total += bytes;
	}
	if (total == (ssize_t)sizeof(buffer) - 1) {
		char extra;
		if (read(fd, &extra, 1) != 0) {
			errno = EOVERFLOW;
			goto fail;
		}
	}
	if (close(fd) != 0)
		return -1;
	buffer[total] = '\0';
	for (cursor = buffer; *cursor != '\0';) {
		char *end = strchr(cursor, '\n');
		char saved = '\0';

		if (end != NULL) {
			saved = *end;
			*end = '\0';
		}
		if (strstr(cursor, GPIO_LINE_NAME) != NULL) {
			bool is_high = strstr(cursor, " in  hi") != NULL;
			bool is_low = strstr(cursor, " in  lo") != NULL;

			matches++;
			if (strstr(cursor, GPIO_NUMBER_TEXT) == NULL ||
			    strstr(cursor, " IRQ ACTIVE LOW") == NULL || is_high == is_low) {
				errno = EPROTO;
				return -1;
			}
			raw = is_high ? 1 : 0;
		}
		if (end == NULL)
			break;
		*end = saved;
		cursor = end + 1;
	}
	if (matches != 1) {
		errno = matches == 0 ? ENODEV : ENOTUNIQ;
		return -1;
	}
	return raw;

fail:
	close(fd);
	return -1;
}

static void process_gpio_sample(int raw, struct gpio_observation *observation)
{
	observation->samples++;
	if (observation->initial_raw < 0) {
		observation->initial_raw = raw;
		observation->last_raw = raw;
		observation->final_raw = raw;
		return;
	}
	observation->final_raw = raw;
	if (raw == observation->last_raw)
		return;
	if (raw == 0) {
		observation->insertions++;
		printf("R46H_AUDIO_JACK_LOCALIZE_GPIO raw=low logical=inserted count=%u\n",
		       observation->insertions);
	} else {
		observation->removals++;
		printf("R46H_AUDIO_JACK_LOCALIZE_GPIO raw=high logical=removed count=%u\n",
		       observation->removals);
	}
	observation->last_raw = raw;
	fflush(stdout);
}

static bool complete_switch_cycle(const struct switch_observation *observation)
{
	return observation->insertions >= 1 && observation->removals >= 1 &&
	       observation->last_state == 0;
}

static bool complete_gpio_cycle(const struct gpio_observation *observation)
{
	return observation->insertions >= 1 && observation->removals >= 1 &&
	       observation->last_raw == 1;
}

static void classify(const struct switch_observation *evdev,
		     const struct gpio_observation *gpio, const char **result,
		     const char **reason, const char **localization)
{
	bool evdev_cycle = complete_switch_cycle(evdev);
	bool gpio_cycle = complete_gpio_cycle(gpio);

	*result = "fail";
	if (evdev_cycle && gpio_cycle) {
		*result = "pass";
		*reason = "both-paths-observed";
		*localization = "none";
	} else if (gpio_cycle) {
		*reason = "evdev-transitions-missing";
		*localization = "evdev-or-asoc-path";
	} else if (evdev_cycle) {
		*reason = "gpio-samples-inconsistent";
		*localization = "debug-gpio-path";
	} else {
		*reason = "gpio-transitions-missing";
		*localization = "gpio-mux-electrical-or-socket-path";
	}
}

static void emit_result(const char *result, const char *reason,
			const char *localization,
			const struct switch_observation *evdev,
			const struct gpio_observation *gpio)
{
	printf("R46H_AUDIO_JACK_LOCALIZE id=%s result=%s reason=%s localization=%s "
	       "evdev_initial=%d evdev_insertions=%u evdev_removals=%u "
	       "evdev_final=%d syn_dropped=%u gpio_initial_raw=%d "
	       "gpio_insertions=%u gpio_removals=%u gpio_final_raw=%d samples=%u\n",
	       PROBE_ID, result, reason, localization, evdev->initial_state,
	       evdev->insertions, evdev->removals, evdev->final_state,
	       evdev->syn_dropped, gpio->initial_raw, gpio->insertions,
	       gpio->removals, gpio->final_raw, gpio->samples);
}

static int run_observation(void)
{
	char path[128] = "unknown";
	struct switch_observation evdev = {
		.initial_state = -1,
		.last_state = -1,
		.final_state = -1,
	};
	struct gpio_observation gpio = {
		.initial_raw = -1,
		.last_raw = -1,
		.final_raw = -1,
	};
	struct sigaction action;
	int64_t deadline;
	int64_t next_gpio_sample;
	int64_t gpio_cycle_at = -1;
	int fd = -1;
	int status = EXIT_FAILURE;
	const char *result = "fail";
	const char *reason = "internal-error";
	const char *localization = "none";

	if (geteuid() != 0) {
		reason = "root-required";
		goto finish;
	}
	if (!isatty(STDIN_FILENO) || !isatty(STDOUT_FILENO) ||
	    !isatty(STDERR_FILENO)) {
		reason = "interactive-tty-required";
		goto finish;
	}
	if (require_runtime_identity() != 0) {
		reason = "runtime-identity-mismatch";
		goto finish;
	}
	memset(&action, 0, sizeof(action));
	action.sa_handler = handle_signal;
	sigemptyset(&action.sa_mask);
	if (sigaction(SIGINT, &action, NULL) != 0 ||
	    sigaction(SIGTERM, &action, NULL) != 0 ||
	    sigaction(SIGHUP, &action, NULL) != 0) {
		reason = "signal-handler-failed";
		goto finish;
	}
	fd = discover_headphone_event(path, sizeof(path));
	if (fd < 0) {
		reason = errno == ENOTUNIQ ? "ambiguous-device" : "device-not-found";
		goto finish;
	}
	if (require_headphone_capability(fd) != 0) {
		reason = "switch-capability-missing";
		goto finish;
	}
	evdev.initial_state = query_headphone_state(fd);
	if (evdev.initial_state < 0) {
		reason = "initial-evdev-state-unreadable";
		goto finish;
	}
	evdev.last_state = evdev.initial_state;
	evdev.final_state = evdev.initial_state;
	{
		int raw = query_gpio_raw();

		if (raw < 0) {
			reason = "initial-gpio-state-unreadable";
			goto finish;
		}
		process_gpio_sample(raw, &gpio);
	}
	if (gpio.initial_raw < 0) {
		reason = "initial-gpio-state-unreadable";
		goto finish;
	}
	if (evdev.initial_state != 0 || gpio.initial_raw != 1) {
		reason = "headphones-must-start-removed";
		goto finish;
	}
	deadline = monotonic_milliseconds();
	if (deadline < 0) {
		reason = "clock-failed";
		goto finish;
	}
	next_gpio_sample = deadline + GPIO_SAMPLE_MILLISECONDS;
	deadline += OBSERVE_SECONDS * 1000;
	printf("R46H_AUDIO_JACK_LOCALIZE_OBSERVATION phase=start device=%s "
	       "gpio=%s seconds=%d sample_ms=%d action=insert-once-then-remove-once\n",
	       path, GPIO_NUMBER_TEXT, OBSERVE_SECONDS, GPIO_SAMPLE_MILLISECONDS);
	fflush(stdout);

	while (!stop_signal) {
		struct pollfd descriptor = { .fd = fd, .events = POLLIN };
		struct input_event events[32];
		int64_t now = monotonic_milliseconds();
		int timeout;
		int poll_status;

		if (now < 0) {
			reason = "clock-failed";
			goto finish;
		}
		if (now >= deadline)
			break;
		if (now >= next_gpio_sample) {
			int raw = query_gpio_raw();

			if (raw < 0) {
				reason = "gpio-state-unreadable";
				goto finish;
			}
			process_gpio_sample(raw, &gpio);
			next_gpio_sample = now + GPIO_SAMPLE_MILLISECONDS;
			if (complete_gpio_cycle(&gpio) && gpio_cycle_at < 0)
				gpio_cycle_at = now;
		}
		if (complete_switch_cycle(&evdev) && complete_gpio_cycle(&gpio))
			break;
		if (gpio_cycle_at >= 0 && now - gpio_cycle_at >= EVDEV_SETTLE_MILLISECONDS)
			break;
		timeout = (int)(next_gpio_sample - now);
		if (timeout < 0)
			timeout = 0;
		if (timeout > GPIO_SAMPLE_MILLISECONDS)
			timeout = GPIO_SAMPLE_MILLISECONDS;
		poll_status = poll(&descriptor, 1, timeout);
		if (poll_status < 0) {
			if (errno == EINTR)
				continue;
			reason = "poll-failed";
			goto finish;
		}
		if (poll_status == 0)
			continue;
		if ((descriptor.revents & (POLLERR | POLLHUP | POLLNVAL)) != 0) {
			reason = "device-lost";
			goto finish;
		}
		for (;;) {
			ssize_t bytes = read(fd, events, sizeof(events));
			size_t index;

			if (bytes < 0 && (errno == EAGAIN || errno == EINTR))
				break;
			if (bytes <= 0 || bytes % (ssize_t)sizeof(events[0]) != 0) {
				reason = "invalid-event-frame";
				goto finish;
			}
			for (index = 0; index < (size_t)bytes / sizeof(events[0]); index++) {
				if (process_switch_event(&events[index], &evdev) != 0) {
					reason = "invalid-switch-event";
					goto finish;
				}
			}
			if ((size_t)bytes < sizeof(events))
				break;
		}
	}
	if (stop_signal) {
		reason = "operator-signal";
		status = 128 + stop_signal;
		goto finish;
	}
	evdev.final_state = query_headphone_state(fd);
	if (evdev.final_state < 0) {
		reason = "final-evdev-state-unreadable";
		goto finish;
	}
	{
		int raw = query_gpio_raw();

		if (raw < 0) {
			reason = "final-gpio-state-unreadable";
			goto finish;
		}
		process_gpio_sample(raw, &gpio);
	}
	if (evdev.final_state != 0 || gpio.final_raw != 1) {
		reason = "headphones-not-removed";
		goto finish;
	}
	if (evdev.syn_dropped != 0) {
		reason = "syn-dropped";
		goto finish;
	}
	classify(&evdev, &gpio, &result, &reason, &localization);
	status = strcmp(result, "pass") == 0 ? EXIT_SUCCESS : EXIT_FAILURE;

finish:
	if (fd >= 0)
		close(fd);
	emit_result(result, reason, localization, &evdev, &gpio);
	return status;
}

static int run_self_test(void)
{
	struct switch_observation evdev = {
		.initial_state = 0,
		.last_state = 0,
		.final_state = 0,
	};
	struct gpio_observation gpio = {
		.initial_raw = -1,
		.last_raw = -1,
		.final_raw = -1,
	};
	struct input_event events[] = {
		{ .type = EV_SW, .code = SW_HEADPHONE_INSERT, .value = 1 },
		{ .type = EV_SW, .code = SW_HEADPHONE_INSERT, .value = 0 },
	};
	const char *result;
	const char *reason;
	const char *localization;
	size_t index;

	for (index = 0; index < ARRAY_SIZE(events); index++) {
		if (process_switch_event(&events[index], &evdev) != 0)
			return EXIT_FAILURE;
	}
	process_gpio_sample(1, &gpio);
	process_gpio_sample(0, &gpio);
	process_gpio_sample(1, &gpio);
	classify(&evdev, &gpio, &result, &reason, &localization);
	if (strcmp(result, "pass") != 0 || strcmp(reason, "both-paths-observed") != 0 ||
	    strcmp(localization, "none") != 0)
		return EXIT_FAILURE;
	evdev.insertions = 0;
	evdev.removals = 0;
	classify(&evdev, &gpio, &result, &reason, &localization);
	if (strcmp(result, "fail") != 0 ||
	    strcmp(reason, "evdev-transitions-missing") != 0 ||
	    strcmp(localization, "evdev-or-asoc-path") != 0)
		return EXIT_FAILURE;
	printf("R46H_AUDIO_JACK_LOCALIZE_SELFTEST result=pass\n");
	return EXIT_SUCCESS;
}

static void usage(FILE *stream)
{
	fprintf(stream,
		"usage: r46h-audio-jack-localize --observe | --self-test | --help\n"
		"\n"
		"--observe samples the already-requested active-low gpio-86 line "
		"from debugfs while reading the unique RK817 headphone evdev device "
		"for at most 30 seconds. It does not request a GPIO, grab input, play "
		"audio, change pinctrl, or write persistent storage.\n");
}

int main(int argc, char **argv)
{
	if (argc != 2) {
		usage(stderr);
		return 2;
	}
	if (strcmp(argv[1], "--help") == 0) {
		usage(stdout);
		return EXIT_SUCCESS;
	}
	if (strcmp(argv[1], "--self-test") == 0)
		return run_self_test();
	if (strcmp(argv[1], "--observe") == 0)
		return run_observation();
	usage(stderr);
	return 2;
}
