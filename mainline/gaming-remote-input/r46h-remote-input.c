#define _GNU_SOURCE

#include <errno.h>
#include <fcntl.h>
#include <linux/input.h>
#include <linux/uinput.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <sys/file.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#define VERSION "r46h-gaming-remote-input-v0.1"
#define UINPUT_NODE "/dev/uinput"
#define LOCK_PATH "/run/r46h-remote-input.lock"
#define DEVICE_NAME "R46H Remote Keyboard"
#ifndef KEY_HOLD_MILLISECONDS
#define KEY_HOLD_MILLISECONDS 100
#endif
#define ARRAY_SIZE(values) (sizeof(values) / sizeof((values)[0]))

struct action {
	const char *name;
	unsigned short code;
};

static const struct action actions[] = {
	{ "up", KEY_UP },
	{ "down", KEY_DOWN },
	{ "left", KEY_LEFT },
	{ "right", KEY_RIGHT },
	{ "a", KEY_ENTER },
	{ "b", KEY_BACKSPACE },
	{ "x", KEY_DELETE },
	{ "y", KEY_INSERT },
	{ "select", KEY_F1 },
	{ "start", KEY_ESC },
	{ "l1", KEY_PAGEUP },
	{ "r1", KEY_PAGEDOWN },
	{ "l2", KEY_HOME },
	{ "r2", KEY_END },
	{ "l3", KEY_F2 },
	{ "r3", KEY_F3 },
};

static void fail_errno(const char *operation, const char *path)
{
	fprintf(stderr, "ERROR: %s %s: %s\n", operation, path, strerror(errno));
}

static const struct action *find_action(const char *name)
{
	size_t index;

	for (index = 0; index < ARRAY_SIZE(actions); index++) {
		if (strcmp(actions[index].name, name) == 0)
			return &actions[index];
	}
	return NULL;
}

static int self_test(void)
{
	return ARRAY_SIZE(actions) == 16 && find_action("up") != NULL &&
	       find_action("r3") != NULL && find_action("") == NULL &&
	       find_action("up down") == NULL ? 0 : 1;
}

static int sleep_milliseconds(long milliseconds)
{
	struct timespec remaining = {
		.tv_sec = milliseconds / 1000,
		.tv_nsec = (milliseconds % 1000) * 1000000L,
	};

	while (nanosleep(&remaining, &remaining) != 0) {
		if (errno != EINTR)
			return -1;
	}
	return 0;
}

static int acquire_lock(void)
{
	struct stat metadata;
	int fd;

	fd = open(LOCK_PATH, O_RDWR | O_CREAT | O_CLOEXEC | O_NOFOLLOW, 0600);
	if (fd < 0) {
		fail_errno("cannot open", LOCK_PATH);
		return -1;
	}
	if (fchmod(fd, 0600) != 0 || fstat(fd, &metadata) != 0 ||
	    !S_ISREG(metadata.st_mode) || metadata.st_nlink != 1 ||
	    metadata.st_uid != 0 || metadata.st_gid != 0 ||
	    (metadata.st_mode & 0777) != 0600) {
		errno = EPERM;
		fail_errno("unsafe lock", LOCK_PATH);
		close(fd);
		return -1;
	}
	if (flock(fd, LOCK_EX | LOCK_NB) != 0) {
		fail_errno("remote input is busy at", LOCK_PATH);
		close(fd);
		return -1;
	}
	return fd;
}

static int open_uinput(void)
{
	struct stat before;
	struct stat after;
	int fd;

	if (lstat(UINPUT_NODE, &before) != 0 || !S_ISCHR(before.st_mode)) {
		fail_errno("cannot validate", UINPUT_NODE);
		return -1;
	}
	fd = open(UINPUT_NODE, O_WRONLY | O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW);
	if (fd < 0) {
		fail_errno("cannot open", UINPUT_NODE);
		return -1;
	}
	if (fstat(fd, &after) != 0 || !S_ISCHR(after.st_mode) ||
	    before.st_dev != after.st_dev || before.st_ino != after.st_ino ||
	    before.st_rdev != after.st_rdev) {
		errno = EPERM;
		fail_errno("identity changed for", UINPUT_NODE);
		close(fd);
		return -1;
	}
	return fd;
}

static int configure_keyboard(int fd)
{
	static const unsigned short extended_keys[] = {
		KEY_F1, KEY_F2, KEY_F3, KEY_HOME, KEY_UP, KEY_PAGEUP,
		KEY_LEFT, KEY_RIGHT, KEY_END, KEY_DOWN, KEY_PAGEDOWN,
		KEY_INSERT, KEY_DELETE,
	};
	struct uinput_setup setup;
	unsigned int code;
	size_t index;

	if (ioctl(fd, UI_SET_EVBIT, EV_KEY) != 0)
		return -1;
	/* The normal alphanumeric block makes udev/SDL classify this as a keyboard. */
	for (code = KEY_ESC; code <= KEY_SPACE; code++) {
		if (ioctl(fd, UI_SET_KEYBIT, code) != 0)
			return -1;
	}
	for (index = 0; index < ARRAY_SIZE(extended_keys); index++) {
		if (ioctl(fd, UI_SET_KEYBIT, extended_keys[index]) != 0)
			return -1;
	}
	memset(&setup, 0, sizeof(setup));
	setup.id.bustype = BUS_VIRTUAL;
	setup.id.vendor = 0x5246;
	setup.id.product = 0x0049;
	setup.id.version = 1;
	memcpy(setup.name, DEVICE_NAME, sizeof(DEVICE_NAME));
	return ioctl(fd, UI_DEV_SETUP, &setup) == 0 &&
	       ioctl(fd, UI_DEV_CREATE) == 0 ? 0 : -1;
}

static int write_event(int fd, unsigned short type, unsigned short code, int value)
{
	struct input_event event;
	ssize_t written;

	memset(&event, 0, sizeof(event));
	event.type = type;
	event.code = code;
	event.value = value;
	written = write(fd, &event, sizeof(event));
	if (written == (ssize_t)sizeof(event))
		return 0;
	if (written >= 0)
		errno = EIO;
	return -1;
}

static int emit_key(int fd, unsigned short code)
{
	if (write_event(fd, EV_KEY, code, 1) != 0 ||
	    write_event(fd, EV_SYN, SYN_REPORT, 0) != 0 ||
	    sleep_milliseconds(KEY_HOLD_MILLISECONDS) != 0 ||
	    write_event(fd, EV_KEY, code, 0) != 0 ||
	    write_event(fd, EV_SYN, SYN_REPORT, 0) != 0 ||
	    sleep_milliseconds(50) != 0)
		return -1;
	return 0;
}

static int run_action(const struct action *action)
{
	int lock_fd = -1;
	int uinput_fd = -1;
	bool device_created = false;
	int status = 1;

	lock_fd = acquire_lock();
	if (lock_fd < 0)
		goto cleanup;
	uinput_fd = open_uinput();
	if (uinput_fd < 0)
		goto cleanup;
	if (configure_keyboard(uinput_fd) != 0) {
		fail_errno("cannot create keyboard on", UINPUT_NODE);
		goto cleanup;
	}
	device_created = true;
	if (sleep_milliseconds(250) != 0 || emit_key(uinput_fd, action->code) != 0) {
		fail_errno("cannot emit action through", UINPUT_NODE);
		goto cleanup;
	}
	status = 0;

cleanup:
	if (device_created)
		(void)ioctl(uinput_fd, UI_DEV_DESTROY);
	if (uinput_fd >= 0)
		(void)close(uinput_fd);
	if (lock_fd >= 0)
		(void)close(lock_fd);
	return status;
}

static void usage(FILE *output)
{
	fprintf(output, "usage: r46h-remote-input ACTION\n");
}

int main(int argc, char **argv)
{
	const struct action *action;

	if (argc == 2 && strcmp(argv[1], "--version") == 0) {
		printf("%s\n", VERSION);
		return 0;
	}
	if (argc == 2 && strcmp(argv[1], "--self-test") == 0)
		return self_test();
	if (argc != 2 || (action = find_action(argv[1])) == NULL) {
		usage(stderr);
		return 2;
	}
	if (geteuid() != 0) {
		fprintf(stderr, "ERROR: root is required\n");
		return 1;
	}
	if (run_action(action) != 0)
		return 1;
	printf("R46H_REMOTE_INPUT result=pass action=%s\n", action->name);
	return 0;
}
