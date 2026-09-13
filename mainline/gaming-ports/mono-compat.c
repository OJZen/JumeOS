/* Private Mono compatibility: isolate Mesa LLVM and report deliberate game self-exit. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <unistd.h>
#include <sys/syscall.h>

static void *(*system_dlopen)(const char *, int);
static void *mesa_provider;
static pthread_once_t resolve_once = PTHREAD_ONCE_INIT;

static void resolve_dlopen(void)
{
    system_dlopen = dlsym(RTLD_NEXT, "dlopen");
}

__attribute__((constructor)) static void preload_mesa_provider(void)
{
    const char *provider = getenv("R46H_MESA_PROVIDER");
    if (!provider || !*provider)
        provider = "/usr/lib/aarch64-linux-gnu/libgallium-25.0.7-2+deb13u1.so";
    if (access(provider, R_OK))
        return;
    pthread_once(&resolve_once, resolve_dlopen);
    mesa_provider = system_dlopen ? system_dlopen(provider, RTLD_NOW | RTLD_LOCAL | RTLD_DEEPBIND) : NULL;
    fputs(mesa_provider ? "R46H_MESA_PROVIDER_SCOPE\n" : "R46H_MESA_PROVIDER_SCOPE_FAILED\n", stderr);
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
