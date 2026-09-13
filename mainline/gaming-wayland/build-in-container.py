#!/usr/bin/env python3
"""Repackage the pinned preview with a relocatable Weston experiment runtime."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tarfile
import tempfile

PROJECT = Path('/project')
OUT = Path('/out')
LIB = Path('usr/lib/aarch64-linux-gnu')
BASE = PROJECT / 'out/.cache/r46h-shell/evidence/before-stream-management-v9/r46h-shell-preview-arm64.tar.gz'
BASE_SHA = 'bc2b089e71ced6a7028482d8b4c5194b98cc97738f8daf0f6fb2f8166b7e8b31'
CLOSURE = PROJECT / 'out/.cache/r46h-shell/manual-20260907T131502Z/closure/metadata/elf-closure.json'
CLOSURE_SHA = '3d9e63b79f2653fbb410b583f966e6140511ec145af1c3665f10fefddf4dac28'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def capture(*args, **kwargs):
    return subprocess.check_output(args, text=True, **kwargs)


def provider_record(reference):
    return {**reference, 'container_version': capture(
        'dpkg-query', '-W', '-f=${Version}', reference['package']).strip()}


def seal_payload(root):
    for path in root.rglob('*'):
        if not path.is_symlink():
            path.chmod(path.stat().st_mode & ~0o022)


def build():
    assert digest(BASE) == BASE_SHA and digest(CLOSURE) == CLOSURE_SHA
    known = json.loads(CLOSURE.read_text())['system_dependencies']
    with tempfile.TemporaryDirectory(prefix='package.', dir=OUT) as temporary:
        stage = Path(temporary)
        # The whole archive is an exact retained input, not an uploaded arbitrary tar.
        subprocess.run(['tar', '-xzf', str(BASE), '-C', str(stage)], check=True)
        for name in ('probe-r46h.sh', 'shell-client.sh'):
            (stage / name).unlink()
        license_packages = set()

        def license_for(path):
            candidates = [str(path), str(path).replace('/usr/lib/', '/lib/', 1)]
            for candidate in candidates:
                result = subprocess.run(['dpkg-query', '-S', candidate], text=True, capture_output=True)
                if result.returncode == 0:
                    for line in result.stdout.splitlines():
                        package, _, owned = line.partition(': ')
                        if owned == candidate:
                            license_packages.add(package.split(':')[0])
                            return
            raise RuntimeError(f'No package provenance for {path}')

        def copy(path, relative=None):
            path = Path(path)
            destination = stage / (relative or path.relative_to('/'))
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() or destination.is_symlink():
                return
            if path.is_symlink():
                real = path.resolve()
                copy(real, destination.parent.relative_to(stage) / real.name)
                destination.symlink_to(real.name)
            else:
                shutil.copy2(path, destination)
            license_for(path)

        selected = [Path('/usr/bin/weston'), Path('/usr/libexec/weston-desktop-shell'),
                    Path('/usr/libexec/weston-keyboard'), Path('/usr/sbin/seatd')]
        for pattern in ('libweston-14.so*', 'libseat.so*', 'libQt6WaylandClient.so*',
                        'libQt6WaylandEglClientHwIntegration.so*', 'weston/libexec_weston.so*',
                        'weston/desktop-shell.so', 'libweston-14/headless-backend.so',
                        'libweston-14/drm-backend.so', 'libweston-14/gl-renderer.so'):
            selected.extend((Path('/') / LIB).glob(pattern))
        plugins = Path('/') / LIB / 'qt6/plugins'
        for pattern in ('platforms/libqwayland*.so', 'wayland-shell-integration/libxdg-shell.so',
                        'wayland-graphics-integration-client/libqt-plugin-wayland-egl.so',
                        'wayland-decoration-client/libbradient.so'):
            selected.extend(plugins.glob(pattern))
        for path in selected:
            copy(path)
        shutil.copytree('/usr/share/weston', stage / 'usr/share/weston', dirs_exist_ok=True)
        environment = dict(os.environ, LD_LIBRARY_PATH=':'.join(str(stage / p) for p in
                           (LIB, LIB / 'weston', LIB / 'libproxy')))
        system = {}
        # ldd reports the transitive closure. Never copy libc, Qt or Mesa over the baseline.
        for path in list(stage.rglob('*')):
            if not path.is_file() or path.is_symlink() or path.open('rb').read(4) != b'\x7fELF':
                continue
            output = capture('ldd', str(path), env=environment)
            assert 'not found' not in output, (path, output)
            for name, resolved in re.findall(r'^\s*(\S+) => (/\S+)', output, re.M):
                target = Path(resolved).resolve()
                if target.is_relative_to(stage):
                    continue
                provider = next((v for k, v in known.items() if Path(k).name == name or Path(k).name.startswith(name + '.')), None)
                if provider is not None:
                    system[str(target)] = provider_record(provider)
                elif name == 'libGLESv2.so.2':
                    assert 'libgles2' in (PROJECT / 'rootfs-debian13/packages.graphics.txt').read_text().splitlines()
                    system[str(target)] = provider_record({'package': 'libgles2', 'target_version': None,
                                           'basis': 'base graphics package contract; recheck on device'})
                else:
                    if re.match(r'(libc\.|ld-linux|libQt6|libEGL|libGLES|libgbm|libGL)', name):
                        raise RuntimeError(f'Unreviewed baseline replacement: {name}')
                    copy(target, LIB / target.name)
                    alias = stage / LIB / name
                    if not alias.exists():
                        alias.symlink_to(target.name)
        for package in sorted(license_packages):
            source = Path('/usr/share/doc') / package / 'copyright'
            destination = stage / 'usr/share/doc' / package / 'copyright'
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        for name in ('session.sh', 'clients.sh', 'probe-r46h.sh'):
            shutil.copyfile(PROJECT / 'gaming-wayland' / name, stage / name)
            (stage / name).chmod(0o755)
        # Inherited Qt license files can be group-writable; the target rejects them.
        seal_payload(stage)
        (OUT / 'evidence/system-dependencies.json').write_text(json.dumps(system, indent=2) + '\n')
        manifest = ''.join(f'{digest(f)}  {f.relative_to(stage)}\n' for f in sorted(stage.rglob('*'))
                           if f.is_file() and not f.is_symlink())
        (stage / 'SHA256SUMS').write_text(manifest)
        # Hide installed Weston and Wayland plugins to catch accidental SDK/system fallback.
        hidden = [Path('/usr/lib/aarch64-linux-gnu/libweston-14'),
                  Path('/usr/lib/aarch64-linux-gnu/weston'),
                  Path('/usr/share/weston'),
                  Path('/usr/libexec/weston-desktop-shell'), Path('/usr/libexec/weston-keyboard'),
                  plugins / 'platforms/libqwayland-egl.so', plugins / 'platforms/libqwayland-generic.so']
        try:
            for path in hidden:
                path.rename(str(path) + '.r46h-hidden')
            check = Path(tempfile.mkdtemp(prefix='headless.', dir=OUT / 'evidence'))
            process = subprocess.Popen([str(stage / 'session.sh'), 'headless', str(check)], start_new_session=True)
            try:
                assert process.wait(timeout=45) == 0
            finally:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    process.wait(timeout=3)
                except ProcessLookupError:
                    pass
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
        finally:
            for path in hidden:
                hidden_path = Path(str(path) + '.r46h-hidden')
                if hidden_path.exists():
                    hidden_path.rename(path)
        archive = OUT / 'r46h-wayland-preview-arm64.tar.gz'
        incoming = archive.with_name(archive.name + '.incoming')
        with incoming.open('wb') as stream:
            tar = subprocess.Popen(['tar', '--sort=name', '--mtime=@0', '--owner=0', '--group=0',
                                    '--numeric-owner', '-C', str(stage), '-cf', '-', '.'], stdout=subprocess.PIPE)
            gzip = subprocess.run(['gzip', '-n'], stdin=tar.stdout, stdout=stream)
            tar.stdout.close()
            assert tar.wait() == 0 and gzip.returncode == 0
        incoming.replace(archive)
        receipt = {'schema': 1, 'status': 'HOST_HEADLESS_PASS_R46H_UNTESTED',
                   'base_sha256': BASE_SHA, 'manifest_sha256': digest(stage / 'SHA256SUMS'),
                   'payload_sha256': digest(archive), 'payload_bytes': archive.stat().st_size,
                   'weston': '14.0.2-1', 'qt_wayland': '6.8.2-4', 'seatd': '0.9.1-1',
                   'sources': {str(f.relative_to(PROJECT)): digest(f) for f in
                               sorted((PROJECT / 'gaming-wayland').glob('*')) if f.is_file()},
                   'debs': {f.name: digest(f) for f in sorted((OUT / 'deb-cache').glob('*.deb'))},
                   'headless_evidence': str(check.relative_to(OUT)),
                   'boundary': 'Software headless client coexistence only; no DRM, Hantro, overlay or input-isolation proof.'}
        (OUT / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
        print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    build()
