// SPDX-License-Identifier: MIT
// Bounded, read-only evdev probe for the R46H RK817 headphone-detect input.

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

#define PROBE_ID "r46h-audio-jack-probe-v0.1"
#define EXPECTED_RELEASE "6.12.99-r46h-mainline-v0.10-adc-full-range"
#define EXPECTED_MODEL "GameConsole R46H"
#define EXPECTED_NAME "rk817_int Headphones"
#define OBSERVE_SECONDS 30
#define INPUT_MAJOR 13
#define ARRAY_SIZE(array) (sizeof(array) / sizeof((array)[0]))
#define BITS_PER_LONG (sizeof(unsigned long) * 8U)
#define BITS_TO_LONGS(count) (((count) + BITS_PER_LONG - 1U) / BITS_PER_LONG)

struct observation {
	int initial_state;
	int last_state;
	int final_state;
	unsigned int insertions;
	unsigned int removals;
	unsigned int syn_dropped;
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

static void emit_result(const char *result, const char *reason,
			const struct observation *observation)
{
	printf("R46H_AUDIO_JACK_PROBE id=%s result=%s reason=%s "
	       "initial=%d insertions=%u removals=%u final=%d syn_dropped=%u\n",
	       PROBE_ID, result, reason, observation->initial_state,
	       observation->insertions, observation->removals,
	       observation->final_state, observation->syn_dropped);
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

static int query_headphone_state(int fd)
{
	unsigned long states[BITS_TO_LONGS(SW_MAX + 1U)];

	memset(states, 0, sizeof(states));
	if (ioctl(fd, EVIOCGSW(sizeof(states)), states) < 0)
		return -1;
	return bit_is_set(states, SW_HEADPHONE_INSERT) ? 1 : 0;
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

static int process_event(const struct input_event *event,
			 struct observation *observation)
{
	int state;

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
	state = event->value;
	if (state == observation->last_state)
		return 0;
	if (state == 1) {
		observation->insertions++;
		printf("R46H_AUDIO_JACK_EVENT state=inserted count=%u\n",
		       observation->insertions);
	} else {
		observation->removals++;
		printf("R46H_AUDIO_JACK_EVENT state=removed count=%u\n",
		       observation->removals);
	}
	observation->last_state = state;
	return 0;
}

static int run_observation(void)
{
	char path[128] = "unknown";
	struct observation observation = {
		.initial_state = -1,
		.last_state = -1,
		.final_state = -1,
	};
	struct sigaction action;
	int64_t deadline;
	int fd = -1;
	int status = EXIT_FAILURE;
	const char *reason = "internal-error";

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
	observation.initial_state = query_headphone_state(fd);
	if (observation.initial_state < 0) {
		reason = "initial-state-unreadable";
		goto finish;
	}
	observation.last_state = observation.initial_state;
	observation.final_state = observation.initial_state;
	if (observation.initial_state != 0) {
		reason = "headphones-must-start-removed";
		goto finish;
	}

	deadline = monotonic_milliseconds();
	if (deadline < 0) {
		reason = "clock-failed";
		goto finish;
	}
	deadline += OBSERVE_SECONDS * 1000;
	printf("R46H_AUDIO_JACK_OBSERVATION phase=start device=%s seconds=%d "
	       "action=insert-once-then-remove-once\n", path, OBSERVE_SECONDS);
	fflush(stdout);

	while (!stop_signal) {
		struct pollfd descriptor = { .fd = fd, .events = POLLIN };
		struct input_event events[32];
		int64_t now = monotonic_milliseconds();
		int timeout;
		int poll_status;
		ssize_t bytes;
		size_t index;

		if (now < 0) {
			reason = "clock-failed";
			goto finish;
		}
		if (now >= deadline)
			break;
		timeout = (int)(deadline - now);
		if (timeout > 250)
			timeout = 250;
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
		bytes = read(fd, events, sizeof(events));
		if (bytes < 0) {
			if (errno == EAGAIN || errno == EINTR)
				continue;
			reason = "read-failed";
			goto finish;
		}
		if (bytes == 0 || bytes % (ssize_t)sizeof(events[0]) != 0) {
			reason = "invalid-event-frame";
			goto finish;
		}
		for (index = 0; index < (size_t)bytes / sizeof(events[0]); index++) {
			if (process_event(&events[index], &observation) != 0) {
				reason = "invalid-switch-event";
				goto finish;
			}
		}
		if (observation.insertions >= 1 && observation.removals >= 1 &&
		    observation.last_state == 0)
			break;
	}
	if (stop_signal) {
		reason = "operator-signal";
		status = 128 + stop_signal;
		goto finish;
	}
	observation.final_state = query_headphone_state(fd);
	if (observation.final_state < 0) {
		reason = "final-state-unreadable";
		goto finish;
	}
	if (observation.insertions < 1 || observation.removals < 1) {
		reason = "required-transitions-missing";
		goto finish;
	}
	if (observation.final_state != 0) {
		reason = "headphones-not-removed";
		goto finish;
	}
	if (observation.final_state != observation.last_state) {
		reason = "switch-state-inconsistent";
		goto finish;
	}
	if (observation.syn_dropped != 0) {
		reason = "syn-dropped";
		goto finish;
	}
	reason = "insert-remove-observed";
	status = EXIT_SUCCESS;

finish:
	if (fd >= 0)
		close(fd);
	emit_result(status == EXIT_SUCCESS ? "pass" : "fail", reason, &observation);
	return status;
}

static int run_self_test(void)
{
	struct observation observation = {
		.initial_state = 0,
		.last_state = 0,
		.final_state = 0,
	};
	struct input_event events[] = {
		{ .type = EV_SYN, .code = SYN_REPORT, .value = 0 },
		{ .type = EV_SW, .code = SW_HEADPHONE_INSERT, .value = 1 },
		{ .type = EV_SW, .code = SW_HEADPHONE_INSERT, .value = 1 },
		{ .type = EV_SW, .code = SW_HEADPHONE_INSERT, .value = 0 },
	};
	size_t index;

	for (index = 0; index < ARRAY_SIZE(events); index++) {
		if (process_event(&events[index], &observation) != 0)
			return EXIT_FAILURE;
	}
	if (observation.insertions != 1 || observation.removals != 1 ||
	    observation.last_state != 0 || observation.syn_dropped != 0)
		return EXIT_FAILURE;
	printf("R46H_AUDIO_JACK_SELFTEST result=pass\n");
	return EXIT_SUCCESS;
}

static void usage(FILE *stream)
{
	fprintf(stream,
		"usage: r46h-audio-jack-probe --observe | --self-test | --help\n"
		"\n"
		"--observe reads exactly one uniquely named RK817 headphone evdev "
		"device for at most 30 seconds. Insert the headphones once, then "
		"remove them once. A complete cycle ends the observation early. "
		"The probe never grabs the device or changes audio state.\n");
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
