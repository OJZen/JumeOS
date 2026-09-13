#define _GNU_SOURCE

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <linux/input.h>
#include <linux/uinput.h>
#include <poll.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#define BRIDGE_VERSION "r46h-gaming-input-bridge-v0.5"
#define VIRTUAL_NAME "R46H Combined Gamepad"
#define SYS_INPUT_ROOT "/sys/class/input"
#define DEV_INPUT_ROOT "/dev/input"
#define UINPUT_NODE "/dev/uinput"
#define DIAGNOSTICS_PATH "/run/r46h-input-bridge/diagnostics"
#define ARRAY_SIZE(values) (sizeof(values) / sizeof((values)[0]))
#define BITS_PER_LONG (sizeof(unsigned long) * 8U)
#define BIT_WORD(bit) ((unsigned int)(bit) / BITS_PER_LONG)
#define BIT_MASK(bit) (1UL << ((unsigned int)(bit) % BITS_PER_LONG))
#define BIT_ARRAY_SIZE(maximum) (BIT_WORD(maximum) + 1U)

static const unsigned short required_keys[] = {
	BTN_SOUTH,
	BTN_EAST,
	BTN_NORTH,
	BTN_WEST,
	BTN_TL,
	BTN_TR,
	BTN_TL2,
	BTN_TR2,
	BTN_SELECT,
	BTN_START,
	BTN_DPAD_UP,
	BTN_DPAD_DOWN,
	BTN_DPAD_LEFT,
	BTN_DPAD_RIGHT,
	BTN_TRIGGER_HAPPY3,
	BTN_TRIGGER_HAPPY4,
	BTN_TRIGGER_HAPPY5,
};

static const char *const required_key_names[] = {
	"BTN_SOUTH",
	"BTN_EAST",
	"BTN_NORTH",
	"BTN_WEST",
	"BTN_TL",
	"BTN_TR",
	"BTN_TL2",
	"BTN_TR2",
	"BTN_SELECT",
	"BTN_START",
	"BTN_DPAD_UP",
	"BTN_DPAD_DOWN",
	"BTN_DPAD_LEFT",
	"BTN_DPAD_RIGHT",
	"BTN_TRIGGER_HAPPY3",
	"BTN_TRIGGER_HAPPY4",
	"BTN_TRIGGER_HAPPY5",
};

static const unsigned short required_axes[] = {
	ABS_X,
	ABS_Y,
	ABS_RX,
	ABS_RY,
};

static const char *const required_axis_names[] = {
	"ABS_X",
	"ABS_Y",
	"ABS_RX",
	"ABS_RY",
};

struct key_diagnostic {
	unsigned int source_presses;
	unsigned int source_releases;
	unsigned int source_other;
	unsigned int emitted_presses;
	unsigned int emitted_releases;
	unsigned int emitted_other;
	int source_last;
	int emitted_last;
};

struct axis_diagnostic {
	unsigned int source_samples;
	unsigned int emitted_samples;
	int source_min;
	int source_max;
	int source_last;
	int emitted_last;
};

struct bridge_diagnostics {
	struct key_diagnostic keys[ARRAY_SIZE(required_keys)];
	struct axis_diagnostic axes[ARRAY_SIZE(required_axes)];
	unsigned int source_syn_reports;
	unsigned int emitted_syn_reports;
	unsigned int uinput_write_failures;
	int failed_type;
	int failed_code;
	int failed_value;
};

_Static_assert(ARRAY_SIZE(required_keys) == ARRAY_SIZE(required_key_names),
	       "key diagnostics name table mismatch");
_Static_assert(ARRAY_SIZE(required_axes) == ARRAY_SIZE(required_axis_names),
	       "axis diagnostics name table mismatch");

struct source_device {
	const char *name;
	char path[128];
	int fd;
	bool grabbed;
};

static volatile sig_atomic_t stop_requested;

static void handle_signal(int signal_number)
{
	(void)signal_number;
	stop_requested = 1;
}

static void fail_errno(const char *operation, const char *path)
{
	fprintf(stderr, "ERROR: %s %s: %s\n", operation, path, strerror(errno));
}

static bool event_entry(const char *name)
{
	const unsigned char *cursor;

	if (strncmp(name, "event", 5) != 0 || name[5] == '\0')
		return false;
	for (cursor = (const unsigned char *)name + 5; *cursor != '\0'; cursor++) {
		if (*cursor < '0' || *cursor > '9')
			return false;
	}
	return true;
}

static int read_device_name(const char *event, char *name, size_t name_size)
{
	char path[256];
	FILE *input;
	size_t length;

	if (snprintf(path, sizeof(path), "%s/%s/device/name", SYS_INPUT_ROOT,
		     event) >= (int)sizeof(path))
		return -1;
	input = fopen(path, "re");
	if (input == NULL)
		return -1;
	if (fgets(name, (int)name_size, input) == NULL) {
		fclose(input);
		return -1;
	}
	if (fclose(input) != 0)
		return -1;
	length = strlen(name);
	while (length > 0 && (name[length - 1] == '\n' || name[length - 1] == '\r'))
		name[--length] = '\0';
	return length > 0 ? 0 : -1;
}

static int discover_source(struct source_device *source)
{
	DIR *directory;
	struct dirent *entry;
	char found[128] = "";
	unsigned int matches = 0;

	directory = opendir(SYS_INPUT_ROOT);
	if (directory == NULL) {
		fail_errno("cannot open", SYS_INPUT_ROOT);
		return -1;
	}
	for (;;) {
		char name[UINPUT_MAX_NAME_SIZE];

		errno = 0;
		entry = readdir(directory);
		if (entry == NULL)
			break;
		if (!event_entry(entry->d_name))
			continue;
		if (read_device_name(entry->d_name, name, sizeof(name)) != 0)
			continue;
		if (strcmp(name, source->name) != 0)
			continue;
		matches++;
		if (snprintf(found, sizeof(found), "%s/%s", DEV_INPUT_ROOT,
			     entry->d_name) >= (int)sizeof(found)) {
			closedir(directory);
			fprintf(stderr, "ERROR: discovered input path is too long\n");
			return -1;
		}
	}
	if (errno != 0) {
		fail_errno("cannot enumerate", SYS_INPUT_ROOT);
		closedir(directory);
		return -1;
	}
	if (closedir(directory) != 0) {
		fail_errno("cannot close", SYS_INPUT_ROOT);
		return -1;
	}
	if (matches != 1) {
		fprintf(stderr, "ERROR: expected exactly one %s event node, found %u\n",
			source->name, matches);
		return -1;
	}
	memcpy(source->path, found, strlen(found) + 1);
	return 0;
}

static int open_source(struct source_device *source)
{
	struct stat metadata;
	char live_name[UINPUT_MAX_NAME_SIZE];

	if (lstat(source->path, &metadata) != 0) {
		fail_errno("cannot stat", source->path);
		return -1;
	}
	if (!S_ISCHR(metadata.st_mode)) {
		fprintf(stderr, "ERROR: source is not a character device: %s\n",
			source->path);
		return -1;
	}
	source->fd = open(source->path, O_RDONLY | O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW);
	if (source->fd < 0) {
		fail_errno("cannot open", source->path);
		return -1;
	}
	memset(live_name, 0, sizeof(live_name));
	if (ioctl(source->fd, EVIOCGNAME(sizeof(live_name)), live_name) < 0) {
		fail_errno("cannot read evdev name from", source->path);
		return -1;
	}
	if (strcmp(live_name, source->name) != 0) {
		fprintf(stderr, "ERROR: evdev identity changed for %s\n", source->path);
		return -1;
	}
	return 0;
}

static bool bit_is_set(const unsigned long *bits, unsigned int bit)
{
	return (bits[BIT_WORD(bit)] & BIT_MASK(bit)) != 0;
}

static int require_event_type(int fd, unsigned int type, const char *name)
{
	unsigned long bits[BIT_ARRAY_SIZE(EV_MAX)] = {0};

	if (ioctl(fd, EVIOCGBIT(0, sizeof(bits)), bits) < 0) {
		fail_errno("cannot read event capabilities from", name);
		return -1;
	}
	if (!bit_is_set(bits, type)) {
		fprintf(stderr, "ERROR: %s does not advertise event type %u\n", name, type);
		return -1;
	}
	return 0;
}

static int require_keys(int fd, const char *name)
{
	unsigned long bits[BIT_ARRAY_SIZE(KEY_MAX)] = {0};
	size_t index;

	if (require_event_type(fd, EV_KEY, name) != 0)
		return -1;
	if (ioctl(fd, EVIOCGBIT(EV_KEY, sizeof(bits)), bits) < 0) {
		fail_errno("cannot read key capabilities from", name);
		return -1;
	}
	for (index = 0; index < ARRAY_SIZE(required_keys); index++) {
		if (!bit_is_set(bits, required_keys[index])) {
			fprintf(stderr, "ERROR: %s is missing key code %u\n", name,
				required_keys[index]);
			return -1;
		}
	}
	return 0;
}

static int read_axes(int fd, const char *name, struct input_absinfo *axes)
{
	unsigned long bits[BIT_ARRAY_SIZE(ABS_MAX)] = {0};
	size_t index;

	if (require_event_type(fd, EV_ABS, name) != 0)
		return -1;
	if (ioctl(fd, EVIOCGBIT(EV_ABS, sizeof(bits)), bits) < 0) {
		fail_errno("cannot read axis capabilities from", name);
		return -1;
	}
	for (index = 0; index < ARRAY_SIZE(required_axes); index++) {
		if (!bit_is_set(bits, required_axes[index])) {
			fprintf(stderr, "ERROR: %s is missing axis code %u\n", name,
				required_axes[index]);
			return -1;
		}
		if (ioctl(fd, EVIOCGABS(required_axes[index]), &axes[index]) < 0) {
			fail_errno("cannot read axis state from", name);
			return -1;
		}
		if (axes[index].minimum != 0 || axes[index].maximum != 1023 ||
		    axes[index].flat != 10 || axes[index].fuzz != 10) {
			fprintf(stderr,
				"ERROR: axis %u has unexpected min/max/fuzz/flat %d/%d/%d/%d\n",
				required_axes[index], axes[index].minimum,
				axes[index].maximum, axes[index].fuzz, axes[index].flat);
			return -1;
		}
	}
	return 0;
}

static bool allowed_code(const unsigned short *codes, size_t count,
			 unsigned short code)
{
	size_t index;

	for (index = 0; index < count; index++) {
		if (codes[index] == code)
			return true;
	}
	return false;
}

static int code_index(const unsigned short *codes, size_t count,
		      unsigned short code)
{
	size_t index;

	for (index = 0; index < count; index++) {
		if (codes[index] == code)
			return (int)index;
	}
	return -1;
}

static void initialize_diagnostics(struct bridge_diagnostics *diagnostics)
{
	size_t index;

	memset(diagnostics, 0, sizeof(*diagnostics));
	diagnostics->failed_type = -1;
	diagnostics->failed_code = -1;
	diagnostics->failed_value = -1;
	for (index = 0; index < ARRAY_SIZE(diagnostics->keys); index++) {
		diagnostics->keys[index].source_last = -1;
		diagnostics->keys[index].emitted_last = -1;
	}
	for (index = 0; index < ARRAY_SIZE(diagnostics->axes); index++) {
		diagnostics->axes[index].source_last = -1;
		diagnostics->axes[index].emitted_last = -1;
	}
}

static void observe_key(struct key_diagnostic *diagnostic, int value, bool emitted)
{
	unsigned int *presses = emitted ? &diagnostic->emitted_presses :
					 &diagnostic->source_presses;
	unsigned int *releases = emitted ? &diagnostic->emitted_releases :
					  &diagnostic->source_releases;
	unsigned int *other = emitted ? &diagnostic->emitted_other :
				       &diagnostic->source_other;
	int *last = emitted ? &diagnostic->emitted_last : &diagnostic->source_last;

	if (value == 1)
		(*presses)++;
	else if (value == 0)
		(*releases)++;
	else
		(*other)++;
	*last = value;
}

static void observe_axis(struct axis_diagnostic *diagnostic, int value,
			 bool emitted)
{
	if (emitted) {
		diagnostic->emitted_samples++;
		diagnostic->emitted_last = value;
		return;
	}
	if (diagnostic->source_samples == 0) {
		diagnostic->source_min = value;
		diagnostic->source_max = value;
	} else {
		if (value < diagnostic->source_min)
			diagnostic->source_min = value;
		if (value > diagnostic->source_max)
			diagnostic->source_max = value;
	}
	diagnostic->source_samples++;
	diagnostic->source_last = value;
}

static FILE *open_diagnostics(void)
{
	struct stat metadata;
	int fd;
	FILE *output;

	fd = open(DIAGNOSTICS_PATH,
		  O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC | O_NOFOLLOW, 0600);
	if (fd < 0) {
		fail_errno("cannot create", DIAGNOSTICS_PATH);
		return NULL;
	}
	if (fchmod(fd, 0600) != 0 || fstat(fd, &metadata) != 0) {
		fail_errno("unsafe diagnostics file", DIAGNOSTICS_PATH);
		close(fd);
		return NULL;
	}
	if (!S_ISREG(metadata.st_mode) || metadata.st_nlink != 1 ||
	    metadata.st_uid != 0 || metadata.st_gid != 0 ||
	    (metadata.st_mode & 0777) != 0600) {
		errno = EPERM;
		fail_errno("unsafe diagnostics file", DIAGNOSTICS_PATH);
		close(fd);
		return NULL;
	}
	output = fdopen(fd, "w");
	if (output == NULL) {
		fail_errno("cannot stream", DIAGNOSTICS_PATH);
		close(fd);
		return NULL;
	}
	(void)setvbuf(output, NULL, _IOLBF, 0);
	return output;
}

static int emit_diagnostics(FILE *output,
			    const struct bridge_diagnostics *diagnostics,
			    int bridge_status)
{
	size_t index;

	if (fprintf(output,
		    "R46H_INPUT_BRIDGE_DIAGNOSTIC kind=header version=%s bridge_status=%s "
		    "uinput_write_failures=%u failed_type=%d failed_code=%d failed_value=%d\n",
		    BRIDGE_VERSION, bridge_status == 0 ? "pass" : "fail",
		    diagnostics->uinput_write_failures, diagnostics->failed_type,
		    diagnostics->failed_code, diagnostics->failed_value) < 0)
		return -1;
	for (index = 0; index < ARRAY_SIZE(required_keys); index++) {
		const struct key_diagnostic *key = &diagnostics->keys[index];

		if (fprintf(output,
			    "R46H_INPUT_BRIDGE_DIAGNOSTIC kind=key code=%s "
			    "source_presses=%u source_releases=%u source_other=%u "
			    "source_last=%d emitted_presses=%u emitted_releases=%u "
			    "emitted_other=%u emitted_last=%d\n",
			    required_key_names[index], key->source_presses,
			    key->source_releases, key->source_other, key->source_last,
			    key->emitted_presses, key->emitted_releases,
			    key->emitted_other, key->emitted_last) < 0)
			return -1;
	}
	for (index = 0; index < ARRAY_SIZE(required_axes); index++) {
		const struct axis_diagnostic *axis = &diagnostics->axes[index];

		if (fprintf(output,
			    "R46H_INPUT_BRIDGE_DIAGNOSTIC kind=axis code=%s "
			    "source_samples=%u source_min=%d source_max=%d source_last=%d "
			    "emitted_samples=%u emitted_last=%d\n",
			    required_axis_names[index], axis->source_samples,
			    axis->source_min, axis->source_max, axis->source_last,
			    axis->emitted_samples, axis->emitted_last) < 0)
			return -1;
	}
	if (fprintf(output,
		    "R46H_INPUT_BRIDGE_DIAGNOSTIC kind=syn source_reports=%u emitted_reports=%u\n",
		    diagnostics->source_syn_reports,
		    diagnostics->emitted_syn_reports) < 0 || fflush(output) != 0)
		return -1;
	return 0;
}

static int emit_event(int fd, unsigned short type, unsigned short code, int value,
		      struct bridge_diagnostics *diagnostics)
{
	struct input_event event;
	ssize_t written;

	memset(&event, 0, sizeof(event));
	event.type = type;
	event.code = code;
	event.value = value;
	written = write(fd, &event, sizeof(event));
	if (written != (ssize_t)sizeof(event)) {
		diagnostics->uinput_write_failures++;
		if (diagnostics->uinput_write_failures == 1) {
			diagnostics->failed_type = type;
			diagnostics->failed_code = code;
			diagnostics->failed_value = value;
		}
		if (written >= 0)
			errno = EIO;
		fail_errno("cannot write to", UINPUT_NODE);
		return -1;
	}
	return 0;
}

static int configure_virtual_device(int fd, const struct input_absinfo *axes)
{
	struct uinput_setup setup;
	size_t index;

	if (ioctl(fd, UI_SET_EVBIT, EV_KEY) < 0 || ioctl(fd, UI_SET_EVBIT, EV_ABS) < 0) {
		fail_errno("cannot enable event types on", UINPUT_NODE);
		return -1;
	}
	for (index = 0; index < ARRAY_SIZE(required_keys); index++) {
		if (ioctl(fd, UI_SET_KEYBIT, required_keys[index]) < 0) {
			fail_errno("cannot enable key on", UINPUT_NODE);
			return -1;
		}
	}
	for (index = 0; index < ARRAY_SIZE(required_axes); index++) {
		struct uinput_abs_setup axis_setup;

		if (ioctl(fd, UI_SET_ABSBIT, required_axes[index]) < 0) {
			fail_errno("cannot enable axis on", UINPUT_NODE);
			return -1;
		}
		memset(&axis_setup, 0, sizeof(axis_setup));
		axis_setup.code = required_axes[index];
		axis_setup.absinfo = axes[index];
		if (ioctl(fd, UI_ABS_SETUP, &axis_setup) < 0) {
			fail_errno("cannot configure axis on", UINPUT_NODE);
			return -1;
		}
	}
	memset(&setup, 0, sizeof(setup));
	setup.id.bustype = BUS_VIRTUAL;
	setup.id.vendor = 0x5246;
	setup.id.product = 0x0048;
	setup.id.version = 1;
	memcpy(setup.name, VIRTUAL_NAME, sizeof(VIRTUAL_NAME));
	if (ioctl(fd, UI_DEV_SETUP, &setup) < 0 || ioctl(fd, UI_DEV_CREATE) < 0) {
		fail_errno("cannot create virtual device on", UINPUT_NODE);
		return -1;
	}
	return 0;
}

static int emit_initial_state(int uinput_fd, int key_fd,
			      const struct input_absinfo *axes,
			      struct bridge_diagnostics *diagnostics)
{
	unsigned long keys[BIT_ARRAY_SIZE(KEY_MAX)] = {0};
	size_t index;

	if (ioctl(key_fd, EVIOCGKEY(sizeof(keys)), keys) < 0) {
		fail_errno("cannot read initial key state from", "gpio-keys");
		return -1;
	}
	for (index = 0; index < ARRAY_SIZE(required_keys); index++) {
		if (emit_event(uinput_fd, EV_KEY, required_keys[index],
			       bit_is_set(keys, required_keys[index]) ? 1 : 0,
			       diagnostics) != 0)
			return -1;
	}
	for (index = 0; index < ARRAY_SIZE(required_axes); index++) {
		if (emit_event(uinput_fd, EV_ABS, required_axes[index],
			       axes[index].value, diagnostics) != 0)
			return -1;
	}
	return emit_event(uinput_fd, EV_SYN, SYN_REPORT, 0, diagnostics);
}

static int mirror_events(int uinput_fd, struct source_device *keys,
			 struct source_device *axes,
			 struct bridge_diagnostics *diagnostics)
{
	struct pollfd poll_fds[2] = {
		{ .fd = keys->fd, .events = POLLIN },
		{ .fd = axes->fd, .events = POLLIN },
	};

	while (!stop_requested) {
		int ready = poll(poll_fds, ARRAY_SIZE(poll_fds), -1);
		size_t source_index;

		if (ready < 0) {
			if (errno == EINTR)
				continue;
			fail_errno("poll failed for", "physical inputs");
			return -1;
		}
		for (source_index = 0; source_index < ARRAY_SIZE(poll_fds); source_index++) {
			struct input_event events[32];
			ssize_t bytes;
			size_t count;
			size_t event_index;

			if ((poll_fds[source_index].revents & (POLLERR | POLLHUP | POLLNVAL)) != 0) {
				fprintf(stderr, "ERROR: physical input disconnected\n");
				return -1;
			}
			if ((poll_fds[source_index].revents & POLLIN) == 0)
				continue;
			bytes = read(poll_fds[source_index].fd, events, sizeof(events));
			if (bytes < 0 && (errno == EAGAIN || errno == EINTR))
				continue;
			if (bytes <= 0 || bytes % (ssize_t)sizeof(events[0]) != 0) {
				if (bytes >= 0)
					errno = EIO;
				fail_errno("cannot read from", source_index == 0 ? keys->path : axes->path);
				return -1;
			}
			count = (size_t)bytes / sizeof(events[0]);
			for (event_index = 0; event_index < count; event_index++) {
				const struct input_event *event = &events[event_index];
				int index;

				if (event->type == EV_SYN && event->code == SYN_DROPPED) {
					fprintf(stderr, "ERROR: physical input reported SYN_DROPPED\n");
					return -1;
				}
				if (event->type == EV_SYN && event->code == SYN_REPORT) {
					diagnostics->source_syn_reports++;
					if (emit_event(uinput_fd, EV_SYN, SYN_REPORT, 0,
						       diagnostics) != 0)
						return -1;
					diagnostics->emitted_syn_reports++;
				} else if (source_index == 0 && event->type == EV_KEY &&
					   allowed_code(required_keys, ARRAY_SIZE(required_keys),
							event->code)) {
					index = code_index(required_keys, ARRAY_SIZE(required_keys),
							   event->code);
					if (index < 0)
						return -1;
					observe_key(&diagnostics->keys[index], event->value, false);
					if (emit_event(uinput_fd, EV_KEY, event->code, event->value,
						       diagnostics) != 0)
						return -1;
					observe_key(&diagnostics->keys[index], event->value, true);
				} else if (source_index == 1 && event->type == EV_ABS &&
					   allowed_code(required_axes, ARRAY_SIZE(required_axes),
							event->code)) {
					index = code_index(required_axes, ARRAY_SIZE(required_axes),
							   event->code);
					if (index < 0)
						return -1;
					observe_axis(&diagnostics->axes[index], event->value, false);
					if (emit_event(uinput_fd, EV_ABS, event->code, event->value,
						       diagnostics) != 0)
						return -1;
					observe_axis(&diagnostics->axes[index], event->value, true);
				}
			}
		}
	}
	return 0;
}

static void cleanup_source(struct source_device *source)
{
	if (source->fd < 0)
		return;
	if (source->grabbed)
		(void)ioctl(source->fd, EVIOCGRAB, 0);
	(void)close(source->fd);
	source->fd = -1;
	source->grabbed = false;
}

static int run_bridge(bool check_only, bool diagnostics_enabled)
{
	struct source_device keys = { .name = "gpio-keys", .fd = -1 };
	struct source_device axes = { .name = "adc-joystick", .fd = -1 };
	struct input_absinfo axis_info[ARRAY_SIZE(required_axes)];
	struct bridge_diagnostics diagnostics;
	struct sigaction action;
	FILE *diagnostics_output = NULL;
	int uinput_fd = -1;
	bool virtual_created = false;
	int status = 1;

	memset(axis_info, 0, sizeof(axis_info));
	initialize_diagnostics(&diagnostics);
	if (discover_source(&keys) != 0 || discover_source(&axes) != 0 ||
	    open_source(&keys) != 0 || open_source(&axes) != 0 ||
	    require_keys(keys.fd, keys.name) != 0 ||
	    read_axes(axes.fd, axes.name, axis_info) != 0)
		goto cleanup;
	uinput_fd = open(UINPUT_NODE, O_WRONLY | O_NONBLOCK | O_CLOEXEC | O_NOFOLLOW);
	if (uinput_fd < 0) {
		fail_errno("cannot open", UINPUT_NODE);
		goto cleanup;
	}
	if (check_only) {
		printf("R46H_INPUT_BRIDGE result=pass mode=check keys=%s axes=%s uinput=%s\n",
		       keys.path, axes.path, UINPUT_NODE);
		status = 0;
		goto cleanup;
	}
	if (diagnostics_enabled) {
		diagnostics_output = open_diagnostics();
		if (diagnostics_output == NULL)
			goto cleanup;
	}
	if (ioctl(keys.fd, EVIOCGRAB, 1) < 0) {
		fail_errno("cannot grab", keys.path);
		goto cleanup;
	}
	keys.grabbed = true;
	if (ioctl(axes.fd, EVIOCGRAB, 1) < 0) {
		fail_errno("cannot grab", axes.path);
		goto cleanup;
	}
	axes.grabbed = true;
	if (configure_virtual_device(uinput_fd, axis_info) != 0)
		goto cleanup;
	virtual_created = true;
	if (emit_initial_state(uinput_fd, keys.fd, axis_info, &diagnostics) != 0)
		goto cleanup;

	memset(&action, 0, sizeof(action));
	action.sa_handler = handle_signal;
	sigemptyset(&action.sa_mask);
	if (sigaction(SIGINT, &action, NULL) != 0 ||
	    sigaction(SIGTERM, &action, NULL) != 0 ||
	    sigaction(SIGHUP, &action, NULL) != 0) {
		fail_errno("cannot install signal handler for", BRIDGE_VERSION);
		goto cleanup;
	}
	printf("R46H_INPUT_BRIDGE result=ready version=%s keys=%s axes=%s virtual=%s grab=yes\n",
	       BRIDGE_VERSION, keys.path, axes.path, VIRTUAL_NAME);
	fflush(stdout);
	status = mirror_events(uinput_fd, &keys, &axes, &diagnostics) == 0 ? 0 : 1;

cleanup:
	if (diagnostics_output != NULL) {
		if (emit_diagnostics(diagnostics_output, &diagnostics, status) != 0) {
			fail_errno("cannot write", DIAGNOSTICS_PATH);
			status = 1;
		}
		if (fclose(diagnostics_output) != 0) {
			fail_errno("cannot close", DIAGNOSTICS_PATH);
			status = 1;
		}
	}
	if (virtual_created)
		(void)ioctl(uinput_fd, UI_DEV_DESTROY);
	if (uinput_fd >= 0)
		(void)close(uinput_fd);
	cleanup_source(&axes);
	cleanup_source(&keys);
	if (!check_only)
		printf("R46H_INPUT_BRIDGE result=%s version=%s cleanup=complete\n",
		       status == 0 ? "pass" : "fail", BRIDGE_VERSION);
	return status;
}

static void usage(FILE *output)
{
	fprintf(output,
		"usage: r46h-input-bridge [--check|--diagnostics|--version]\n");
}

int main(int argc, char **argv)
{
	if (argc == 2 && strcmp(argv[1], "--version") == 0) {
		printf("%s\n", BRIDGE_VERSION);
		return 0;
	}
	if (argc == 2 && strcmp(argv[1], "--check") == 0)
		return run_bridge(true, false);
	if (argc != 1 && !(argc == 2 && strcmp(argv[1], "--diagnostics") == 0)) {
		usage(stderr);
		return 2;
	}
	if (geteuid() != 0) {
		fprintf(stderr, "ERROR: root is required\n");
		return 1;
	}
	return run_bridge(false, argc == 2);
}
