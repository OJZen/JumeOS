/* Private Mono compatibility: isolate Mesa LLVM and report deliberate game self-exit. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <pthread.h>
#include <stdio.h>
#include <string.h>
#include <signal.h>
#include <unistd.h>
#include <sys/syscall.h>

static void *(*system_dlopen)(const char *, int);
static pthread_once_t resolve_once = PTHREAD_ONCE_INIT;

static void resolve_dlopen(void)
{
    system_dlopen = dlsym(RTLD_NEXT, "dlopen");
}

void *dlopen(const char *filename, int flags)
{
    pthread_once(&resolve_once, resolve_dlopen);
    if (!system_dlopen)
        return NULL;
    const char *name = filename ? strrchr(filename, '/') : NULL;
    name = name ? name + 1 : filename;
    size_t length = name ? strlen(name) : 0;
    if (name && (!strcmp(name, "libGLX_mesa.so.0") || !strcmp(name, "libEGL_mesa.so.0") ||
                 !strcmp(name, "libgbm.so.1") || (length >= 7 && !strcmp(name + length - 7, "_dri.so")))) {
        flags |= RTLD_DEEPBIND;
        fputs("R46H_MESA_SYMBOL_SCOPE\n", stderr);
    }
    return system_dlopen(filename, flags);
}

int kill(pid_t pid, int signal_number)
{
    if (pid == getpid() && signal_number == SIGKILL) {
        static const char marker[] = "R46H_PORT_SELF_EXIT\n";
        (void)write(STDERR_FILENO, marker, sizeof(marker) - 1);
    }
    return (int)syscall(SYS_kill, pid, signal_number);
}
