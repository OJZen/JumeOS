#!/usr/bin/env python3
"""Exercise ELF symbol isolation and explicit self-exit reporting on Linux."""
import argparse
import os
from pathlib import Path
import selectors
import signal
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--library', type=Path, required=True)
args = parser.parse_args()
with tempfile.TemporaryDirectory(prefix='mono-compat-', dir=os.environ.get('TMPDIR')) as directory:
    root = Path(directory)
    (root / 'dependency.c').write_text('int collision(void) { return 2; }\n')
    (root / 'provider.c').write_text('extern int collision(void); int value(void) { return collision(); }\n')
    (root / 'main.c').write_text('''#include <dlfcn.h>
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
int collision(void) { return 1; }
int main(int argc, char **argv) {
 if(argc != 2) return 2;
 if(!strcmp(argv[1], "kill")) return kill(getpid(), SIGKILL);
 if(!strcmp(argv[1], "wait")) { puts("ready"); fflush(stdout); pause(); return 0; }
 void *library = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
 if(!library) return 3;
 int (*value)(void) = dlsym(library, "value");
 if(!value) return 4;
 printf("%d\\n", value()); dlclose(library); return 0;
}
''')
    subprocess.run(['gcc', '-shared', '-fPIC', str(root / 'dependency.c'), '-o', str(root / 'libdep.so')], check=True)
    providers = ('libGLX_mesa.so.0', 'libEGL_mesa.so.0', 'libgbm.so.1', 'panfrost_dri.so')
    for name in (*providers, 'unrelated.so'):
        subprocess.run(['gcc', '-shared', '-fPIC', str(root / 'provider.c'), '-L' + str(root), '-ldep', '-Wl,-rpath,$ORIGIN', '-o', str(root / name)], check=True)
    binary = root / 'fixture'
    subprocess.run(['gcc', '-rdynamic', str(root / 'main.c'), '-ldl', '-o', str(binary)], check=True)
    env = {**os.environ, 'LD_PRELOAD': str(args.library.resolve())}
    for name in (*providers, 'unrelated.so'):
        baseline = subprocess.run([str(binary), str(root / name)], capture_output=True, timeout=3)
        patched = subprocess.run([str(binary), str(root / name)], env=env, capture_output=True, timeout=3)
        assert baseline.returncode == patched.returncode == 0
        assert baseline.stdout == b'1\n'
        assert patched.stdout == (b'2\n' if name in providers else b'1\n')
    self_exit = subprocess.run([str(binary), 'kill'], env=env, capture_output=True, timeout=3)
    assert self_exit.returncode == -signal.SIGKILL and b'R46H_PORT_SELF_EXIT' in self_exit.stderr
    child = subprocess.Popen([str(binary), 'wait'], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        with selectors.DefaultSelector() as watcher:
            watcher.register(child.stdout, selectors.EVENT_READ)
            assert watcher.select(3) and child.stdout.readline() == b'ready\n'
        child.kill()
        _, errors = child.communicate(timeout=3)
        assert child.returncode == -signal.SIGKILL and b'R46H_PORT_SELF_EXIT' not in errors
    finally:
        if child.poll() is None:
            child.kill(); child.wait()
print('MONO_COMPAT_PASS: provider-local ELF symbols, unrelated lookup unchanged, deliberate versus external kill distinguished')
