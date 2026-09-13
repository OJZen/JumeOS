// SPDX-License-Identifier: MIT
// Bounded, read-only vendor-kernel GPIO control for R46H jack detection.

#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/reboot.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <sys/utsname.h>
#include <time.h>
#include <unistd.h>

#define PROBE_ID "r46h-audio-jack-vendor-control-v0.2"
#define EXPECTED_RELEASE "4.4.189"
#define EXPECTED_MODEL "GameConsole R46H"
#define EXPECTED_EXECUTABLE "/init"
#define GPIO_DEBUG_PATH "/sys/kernel/debug/gpio"
#define GPIO_LINE_NAME "Headphone detection"
#define GPIO_NUMBER_TEXT "gpio-86"
#define OBSERVE_SECONDS 30
#define GPIO_SAMPLE_MILLISECONDS 20
#define GPIO_BUFFER_SIZE 65536

struct gpio_observation {
	int initial_raw;
	int last_raw;
	int final_raw;
	unsigned int insertions;
	unsigned int removals;
	unsigned int samples;
};

static volatile sig_atomic_t stop_signal;

static bool has_exact_gpio_number(const char *line)
{
	size_t length = strlen(GPIO_NUMBER_TEXT);

	while (*line == ' ' || *line == '\t')
		line++;
	if (strlen(line) <= length)
		return false;
	return strncmp(line, GPIO_NUMBER_TEXT, length) == 0 &&
	       (line[length] == ' ' || line[length] == '\t');
}

static void handle_signal(int signum)
{
	stop_signal = signum;
}

static int64_t monotonic_milliseconds(void)
{
	struct timespec value;

	if (clock_gettime(CLOCK_MONOTONIC, &value) != 0)
		return -1;
	return (int64_t)value.tv_sec * 1000 + value.tv_nsec / 1000000;
}

static int sleep_milliseconds(long milliseconds)
{
	struct timespec remaining = {
		.tv_sec = milliseconds / 1000,
		.tv_nsec = (milliseconds % 1000) * 1000000,
	};

	while (nanosleep(&remaining, &remaining) != 0) {
		if (errno != EINTR)
			return -1;
		if (stop_signal)
			return 0;
	}
	return 0;
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
	fd = open("/sys/firmware/devicetree/base/model",
		  O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
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

static int require_executable_identity(void)
{
	struct stat path_metadata;
	struct stat self_metadata;

	if (lstat(EXPECTED_EXECUTABLE, &path_metadata) != 0)
		return -1;
	if (!S_ISREG(path_metadata.st_mode) || path_metadata.st_uid != 0 ||
	    path_metadata.st_gid != 0 || path_metadata.st_nlink != 1 ||
	    (path_metadata.st_mode & 07777) != 0700) {
		errno = ESTALE;
		return -1;
	}
	if (stat("/proc/self/exe", &self_metadata) != 0)
		return -1;
	if (self_metadata.st_dev != path_metadata.st_dev ||
	    self_metadata.st_ino != path_metadata.st_ino) {
		errno = ESTALE;
		return -1;
	}
	return 0;
}

static int parse_gpio_line(const char *line, bool *has_irq)
{
	const char *state = strstr(line, " in ");
	bool is_high;
	bool is_low;

	if (!has_exact_gpio_number(line) || state == NULL) {
		errno = EPROTO;
		return -1;
	}
	state += 4;
	while (*state == ' ' || *state == '\t')
		state++;
	is_high = strncmp(state, "hi", 2) == 0 &&
		(state[2] == '\0' || state[2] == ' ' || state[2] == '\t');
	is_low = strncmp(state, "lo", 2) == 0 &&
		(state[2] == '\0' || state[2] == ' ' || state[2] == '\t');
	if (is_high == is_low) {
		errno = EPROTO;
		return -1;
	}
	state += 2;
	while (*state == ' ' || *state == '\t')
		state++;
	*has_irq = false;
	if (strncmp(state, "IRQ", 3) == 0 &&
	    (state[3] == '\0' || state[3] == ' ' || state[3] == '\t')) {
		*has_irq = true;
		state += 3;
		while (*state == ' ' || *state == '\t')
			state++;
	}
	if (*state != '\0') {
		errno = EPROTO;
		return -1;
	}
	return is_high ? 1 : 0;
}

static int parse_gpio_buffer(char *buffer, bool *has_irq)
{
	char *cursor;
	unsigned int matches = 0;
	bool line_has_irq = false;
	int raw = -1;

	for (cursor = buffer; *cursor != '\0';) {
		char *end = strchr(cursor, '\n');
		char saved = '\0';

		if (end != NULL) {
			saved = *end;
			*end = '\0';
		}
		if (strstr(cursor, GPIO_LINE_NAME) != NULL) {
			matches++;
			raw = parse_gpio_line(cursor, &line_has_irq);
			if (raw < 0) {
				if (end != NULL)
					*end = saved;
				return -1;
			}
		}
		if (end == NULL)
			break;
		*end = saved;
		cursor = end + 1;
	}
	if (matches != 1) {
		errno = matches == 0 ? ENODEV : EEXIST;
		return -1;
	}
	*has_irq = line_has_irq;
	return raw;
}

static int query_gpio_raw(bool *has_irq, const char **failure_stage)
{
	char buffer[GPIO_BUFFER_SIZE];
	struct stat metadata;
	ssize_t total = 0;
	int raw;
	int fd;

	*failure_stage = "open";
	fd = open(GPIO_DEBUG_PATH, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
	if (fd < 0)
		return -1;
	*failure_stage = "metadata";
	if (fstat(fd, &metadata) != 0)
		goto fail;
	if (!S_ISREG(metadata.st_mode)) {
		errno = ESTALE;
		goto fail;
	}
	*failure_stage = "read";
	while (total < (ssize_t)sizeof(buffer) - 1) {
		ssize_t bytes = read(fd, buffer + total,
				     sizeof(buffer) - 1U - (size_t)total);

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
	*failure_stage = "close";
	if (close(fd) != 0)
		return -1;
	buffer[total] = '\0';
	*failure_stage = "parse";
	raw = parse_gpio_buffer(buffer, has_irq);
	if (raw < 0)
		return -1;
	*failure_stage = "none";
	return raw;

fail:
	{
		int saved_errno = errno;

		close(fd);
		errno = saved_errno;
	}
	return -1;
}

static void emit_gpio_read_error(const char *phase, const char *stage)
{
	int saved_errno = errno;

	printf("R46H_AUDIO_JACK_VENDOR_CONTROL_GPIO_READ phase=%s stage=%s "
	       "result=fail errno=%d\n", phase, stage, saved_errno);
	fflush(stdout);
	errno = saved_errno;
}

static void emit_gpio_line_identity(int raw, bool has_irq)
{
	printf("R46H_AUDIO_JACK_VENDOR_CONTROL_GPIO_LINE gpio=%s "
	       "consumer=Headphone_detection direction=input raw=%s irq=%s\n",
	       GPIO_NUMBER_TEXT, raw == 1 ? "high" : "low",
	       has_irq ? "present" : "absent");
	fflush(stdout);
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
		printf("R46H_AUDIO_JACK_VENDOR_CONTROL_GPIO raw=low "
		       "logical=inserted count=%u\n", observation->insertions);
	} else {
		observation->removals++;
		printf("R46H_AUDIO_JACK_VENDOR_CONTROL_GPIO raw=high "
		       "logical=removed count=%u\n", observation->removals);
	}
	observation->last_raw = raw;
	fflush(stdout);
}

static bool complete_gpio_cycle(const struct gpio_observation *observation)
{
	return observation->insertions >= 1 && observation->removals >= 1 &&
	       observation->last_raw == 1;
}

static void classify(const struct gpio_observation *observation,
		     const char **result, const char **reason,
		     const char **localization)
{
	*result = "fail";
	if (complete_gpio_cycle(observation)) {
		*result = "pass";
		*reason = "vendor-gpio-cycle-observed";
		*localization = "mainline-specific-path-suspect";
	} else {
		*reason = "vendor-gpio-transitions-missing";
		*localization = "shared-electrical-socket-or-common-pin-state";
	}
}

static void emit_result(const char *result, const char *reason,
			const char *localization,
			const struct gpio_observation *observation)
{
	struct utsname system_name;
	const char *release = "unavailable";

	if (uname(&system_name) == 0)
		release = system_name.release;
	printf("R46H_AUDIO_JACK_VENDOR_CONTROL id=%s kernel=%s result=%s "
	       "reason=%s localization=%s initial_raw=%d insertions=%u "
	       "removals=%u final_raw=%d samples=%u\n",
	       PROBE_ID, release, result, reason, localization,
	       observation->initial_raw, observation->insertions,
	       observation->removals, observation->final_raw,
	       observation->samples);
}

static int run_observation(void)
{
	struct gpio_observation observation = {
		.initial_raw = -1,
		.last_raw = -1,
		.final_raw = -1,
	};
	struct sigaction action;
	int64_t deadline;
	bool initial_has_irq = false;
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
	if (require_executable_identity() != 0) {
		reason = "executable-identity-mismatch";
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
	{
		const char *failure_stage = "internal";
		int raw = query_gpio_raw(&initial_has_irq, &failure_stage);

		if (raw < 0) {
			emit_gpio_read_error("initial", failure_stage);
			reason = "initial-gpio-state-unreadable";
			goto finish;
		}
		process_gpio_sample(raw, &observation);
		emit_gpio_line_identity(raw, initial_has_irq);
	}
	if (observation.initial_raw != 1) {
		reason = "headphones-must-start-removed";
		localization = "precondition";
		goto finish;
	}
	deadline = monotonic_milliseconds();
	if (deadline < 0) {
		reason = "clock-failed";
		goto finish;
	}
	deadline += OBSERVE_SECONDS * 1000;
	printf("R46H_AUDIO_JACK_VENDOR_CONTROL_OBSERVATION phase=start "
	       "gpio=%s seconds=%d sample_ms=%d "
	       "action=insert-once-then-remove-once\n",
	       GPIO_NUMBER_TEXT, OBSERVE_SECONDS, GPIO_SAMPLE_MILLISECONDS);
	fflush(stdout);

	while (!stop_signal) {
		int64_t now = monotonic_milliseconds();
		bool has_irq = false;
		const char *failure_stage = "internal";
		int raw;

		if (now < 0) {
			reason = "clock-failed";
			goto finish;
		}
		if (now >= deadline || complete_gpio_cycle(&observation))
			break;
		if (sleep_milliseconds(GPIO_SAMPLE_MILLISECONDS) != 0) {
			reason = "sleep-failed";
			goto finish;
		}
		if (stop_signal)
			break;
		raw = query_gpio_raw(&has_irq, &failure_stage);
		if (raw < 0) {
			emit_gpio_read_error("sample", failure_stage);
			reason = "gpio-state-unreadable";
			goto finish;
		}
		if (has_irq != initial_has_irq) {
			errno = ESTALE;
			emit_gpio_read_error("sample", "identity");
			reason = "gpio-line-identity-changed";
			goto finish;
		}
		process_gpio_sample(raw, &observation);
	}
	if (stop_signal) {
		reason = "operator-signal";
		status = 128 + stop_signal;
		goto finish;
	}
	{
		bool has_irq = false;
		const char *failure_stage = "internal";
		int raw = query_gpio_raw(&has_irq, &failure_stage);

		if (raw < 0) {
			emit_gpio_read_error("final", failure_stage);
			reason = "final-gpio-state-unreadable";
			goto finish;
		}
		if (has_irq != initial_has_irq) {
			errno = ESTALE;
			emit_gpio_read_error("final", "identity");
			reason = "gpio-line-identity-changed";
			goto finish;
		}
		process_gpio_sample(raw, &observation);
	}
	if (observation.final_raw != 1) {
		reason = "headphones-not-removed";
		localization = "precondition";
		goto finish;
	}
	classify(&observation, &result, &reason, &localization);
	status = strcmp(result, "pass") == 0 ? EXIT_SUCCESS : EXIT_FAILURE;

finish:
	emit_result(result, reason, localization, &observation);
	return status;
}

static int run_self_test(void)
{
	char high_line[] =
		"gpiochip2: GPIOs 64-95, parent: platform/ff240000.gpio:\n"
		" gpio-86  (                    |Headphone detection ) in  hi "
		"IRQ\n";
	char low_without_irq[] =
		" gpio-86 (consumer|Headphone detection) in lo    \n";
	char wrong_line[] =
		" gpio-85 (consumer|Headphone detection) in hi IRQ\n";
	char output_line[] =
		" gpio-86 (consumer|Headphone detection) out hi IRQ\n";
	char extra_token_line[] =
		" gpio-86 (consumer|Headphone detection) in hi IRQ unexpected\n";
	char duplicate_lines[] =
		" gpio-86 (consumer|Headphone detection) in hi IRQ\n"
		" gpio-86 (consumer|Headphone detection) in hi IRQ\n";
	struct gpio_observation observation = {
		.initial_raw = -1,
		.last_raw = -1,
		.final_raw = -1,
	};
	const char *result;
	const char *reason;
	const char *localization;
	bool has_irq = false;

	if (parse_gpio_buffer(high_line, &has_irq) != 1 || !has_irq)
		return EXIT_FAILURE;
	if (parse_gpio_buffer(low_without_irq, &has_irq) != 0 || has_irq)
		return EXIT_FAILURE;
	if (parse_gpio_buffer(wrong_line, &has_irq) >= 0 ||
	    parse_gpio_buffer(output_line, &has_irq) >= 0 ||
	    parse_gpio_buffer(extra_token_line, &has_irq) >= 0 ||
	    parse_gpio_buffer(duplicate_lines, &has_irq) >= 0)
		return EXIT_FAILURE;
	process_gpio_sample(1, &observation);
	process_gpio_sample(0, &observation);
	process_gpio_sample(1, &observation);
	classify(&observation, &result, &reason, &localization);
	if (strcmp(result, "pass") != 0 ||
	    strcmp(reason, "vendor-gpio-cycle-observed") != 0 ||
	    strcmp(localization, "mainline-specific-path-suspect") != 0)
		return EXIT_FAILURE;
	observation.insertions = 0;
	observation.removals = 0;
	classify(&observation, &result, &reason, &localization);
	if (strcmp(result, "fail") != 0 ||
	    strcmp(reason, "vendor-gpio-transitions-missing") != 0 ||
	    strcmp(localization,
		   "shared-electrical-socket-or-common-pin-state") != 0)
		return EXIT_FAILURE;
	printf("R46H_AUDIO_JACK_VENDOR_CONTROL_SELFTEST result=pass\n");
	return EXIT_SUCCESS;
}

static int require_or_create_directory(const char *path, mode_t mode)
{
	struct stat metadata;

	if (mkdir(path, mode) != 0 && errno != EEXIST)
		return -1;
	if (lstat(path, &metadata) != 0 || !S_ISDIR(metadata.st_mode) ||
	    metadata.st_uid != 0 || metadata.st_gid != 0) {
		errno = ESTALE;
		return -1;
	}
	return 0;
}

static int run_init_mode(void)
{
	struct gpio_observation empty_observation = {
		.initial_raw = -1,
		.last_raw = -1,
		.final_raw = -1,
	};
	struct stat console_metadata;
	bool dev_mounted = false;
	bool proc_mounted = false;
	bool sys_mounted = false;
	bool debug_mounted = false;
	int console_fd = -1;
	int status = EXIT_FAILURE;

	if (getpid() != 1 || geteuid() != 0) {
		fprintf(stderr, "ERROR: no-argument mode is reserved for initramfs PID 1\n");
		return 2;
	}
	if (require_or_create_directory("/dev", 0755) != 0)
		goto setup_failed;
	if (mount("devtmpfs", "/dev", "devtmpfs", MS_NOSUID | MS_NOEXEC,
		  "mode=0755") != 0)
		goto setup_failed;
	dev_mounted = true;
	console_fd = open("/dev/console",
			  O_RDWR | O_NOCTTY | O_CLOEXEC | O_NOFOLLOW);
	if (console_fd < 0)
		goto setup_failed;
	if (fstat(console_fd, &console_metadata) != 0 ||
	    !S_ISCHR(console_metadata.st_mode) ||
	    major(console_metadata.st_rdev) != 5 ||
	    minor(console_metadata.st_rdev) != 1) {
		errno = ESTALE;
		goto console_failed;
	}
	if (dup2(console_fd, STDIN_FILENO) < 0)
		goto console_failed;
	if (dup2(console_fd, STDOUT_FILENO) < 0)
		goto console_failed;
	if (dup2(console_fd, STDERR_FILENO) < 0)
		goto console_failed;
	if (console_fd > STDERR_FILENO) {
		int close_status = close(console_fd);

		console_fd = -1;
		if (close_status != 0)
			goto console_failed;
	} else {
		console_fd = -1;
	}
	if (!isatty(STDIN_FILENO) || !isatty(STDOUT_FILENO) ||
	    !isatty(STDERR_FILENO)) {
		errno = ENOTTY;
		goto console_failed;
	}
	if (require_or_create_directory("/proc", 0555) != 0 ||
	    require_or_create_directory("/sys", 0555) != 0)
		goto setup_failed;
	if (mount("proc", "/proc", "proc",
		  MS_RDONLY | MS_NOSUID | MS_NODEV | MS_NOEXEC, NULL) != 0)
		goto setup_failed;
	proc_mounted = true;
	if (mount("sysfs", "/sys", "sysfs",
		  MS_RDONLY | MS_NOSUID | MS_NODEV | MS_NOEXEC, NULL) != 0)
		goto setup_failed;
	sys_mounted = true;
	if (require_or_create_directory("/sys/kernel/debug", 0700) != 0)
		goto setup_failed;
	if (mount("debugfs", "/sys/kernel/debug", "debugfs",
		  MS_RDONLY | MS_NOSUID | MS_NODEV | MS_NOEXEC, NULL) != 0)
		goto setup_failed;
	debug_mounted = true;
	printf("R46H_AUDIO_JACK_VENDOR_CONTROL_INIT phase=ready "
	       "persistent_storage_mounted=no normal_userspace_started=no\n");
	fflush(stdout);
	status = run_observation();
	printf("R46H_AUDIO_JACK_VENDOR_CONTROL_COMMAND status=%d\n", status);
	fflush(stdout);
	goto poweroff;

console_failed:
	{
		int saved_errno = errno;

		if (console_fd > STDERR_FILENO) {
			close(console_fd);
			console_fd = -1;
		}
		errno = saved_errno;
	}

setup_failed:
	emit_result("fail", "initramfs-setup-failed", "none",
		    &empty_observation);
	printf("R46H_AUDIO_JACK_VENDOR_CONTROL_COMMAND status=%d\n", status);
	fflush(stdout);

poweroff:
	if (debug_mounted && umount2("/sys/kernel/debug", MNT_DETACH) != 0)
		status = EXIT_FAILURE;
	if (sys_mounted && umount2("/sys", MNT_DETACH) != 0)
		status = EXIT_FAILURE;
	if (proc_mounted && umount2("/proc", MNT_DETACH) != 0)
		status = EXIT_FAILURE;
	if (dev_mounted && umount2("/dev", MNT_DETACH) != 0)
		status = EXIT_FAILURE;
	sync();
	printf("R46H_AUDIO_JACK_VENDOR_CONTROL_POWEROFF status=%d\n", status);
	fflush(stdout);
	/* Keep the console bound so a failed reboot call can still report why. */
	if (reboot(RB_POWER_OFF) != 0) {
		fprintf(stderr, "ERROR: poweroff failed: %s\n", strerror(errno));
		fflush(stderr);
	}
	close(STDERR_FILENO);
	close(STDOUT_FILENO);
	close(STDIN_FILENO);
	for (;;)
		pause();
}

static void usage(FILE *stream)
{
	fprintf(stream,
		"usage: r46h-audio-jack-vendor-control "
		"--self-test | --help\n"
		"\n"
		"With no arguments as initramfs PID 1, this control mounts only "
		"devtmpfs, procfs, sysfs and debugfs, binds the exact console, "
		"and samples the vendor 4.4.189 kernel's "
		"already-requested active-low gpio-86 input line for at most "
		"30 seconds. It reports whether the BSP marks that exact line "
		"as an IRQ, then powers off. It does not request a GPIO, mount "
		"persistent storage, change pinctrl, start normal userspace, "
		"touch a mixer, or play audio.\n");
}

int main(int argc, char **argv)
{
	if (argc == 1)
		return run_init_mode();
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
	usage(stderr);
	return 2;
}
