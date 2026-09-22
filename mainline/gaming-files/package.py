#!/usr/bin/env python3
"""Relocatable Qt Files runtime, retaining the accepted Qt base and GPU stack."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile

out=Path('/out');code=Path('/mainline/gaming-files')
base=Path('/mainline/out/.cache/r46h-shell/r46h-shell-preview-arm64.tar.gz')
BASE='dcb9e9fda1e3fe144cad9931c3ed341b3dacaf5919d63436497ae4d02bb6918f'
def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()
if not Path('/.dockerenv').exists() or digest(base)!=BASE:
    raise SystemExit('Use the pinned SDK and retained Qt runtime')
with tempfile.TemporaryDirectory(prefix='files-package-',dir=out) as temporary:
    stage=Path(temporary);stage.chmod(0o755)
    with tarfile.open(base) as archive:
        members=[m for m in archive.getmembers() if m.name.startswith(('./usr/lib/aarch64-linux-gnu','./usr/share/fonts','./usr/share/doc')) or m.name=='./usr/bin/qt.conf']
        archive.extractall(stage,members=members,filter='data')
    (stage/'usr/bin').mkdir(parents=True,exist_ok=True)
    shutil.copy2(out/'build/jume-files',stage/'usr/bin/jume-files')
    subprocess.run(['strip','--strip-unneeded',str(stage/'usr/bin/jume-files')],check=True)
    shutil.copy2(code/'files-client.sh',stage/'files-client.sh');(stage/'files-client.sh').chmod(0o755)
    share=stage/'usr/share/jume-files';share.mkdir(parents=True)
    for name in ('transfer_server.py','transfer.html','transfer.js','transfer.css'):
        shutil.copy2(code/name,share/name)
    (stage/'storage').mkdir()
    for name in ('storage-policy.sh','49-jume-removable.rules'):
        shutil.copy2(code/name,stage/'storage'/name)
    lib=stage/'usr/lib/aarch64-linux-gnu';plugins=lib/'qt6/plugins';packages=set()
    if plugins.exists():shutil.rmtree(plugins) # Candidate-local extraction, not the retained base.
    def license(path):
        result=subprocess.run(['dpkg-query','-S',str(path.resolve())],text=True,capture_output=True,check=True).stdout.splitlines()[0]
        package=result.split(': ')[0].split(':')[0];packages.add(package)
        source=Path('/usr/share/doc')/package/'copyright'
        if not source.is_file():raise RuntimeError('Missing license: '+package)
        target=stage/'usr/share/doc'/package;target.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target/'copyright')
    shutil.copy2('/usr/bin/pulseaudio',stage/'usr/bin/pulseaudio');license(Path('/usr/bin/pulseaudio'))
    audio=lib/'jume-audio';audio.mkdir(parents=True)
    for name in ('libalsa-util.so','libprotocol-native.so','module-alsa-sink.so','module-native-protocol-unix.so','module-null-sink.so'):
        source=Path('/usr/lib/pulse-17.0+dfsg1/modules')/name;shutil.copy2(source,audio/name);license(source)
    for group in ('multimedia','imageformats','platforms','wayland-shell-integration','wayland-graphics-integration-client','wayland-decoration-client'):
        source=Path('/usr/lib/aarch64-linux-gnu/qt6/plugins')/group
        for path in source.glob('*.so'):
            if group=='platforms' and 'wayland' not in path.name and path.name!='libqoffscreen.so':continue
            if group=='imageformats' and path.name not in ('libqjpeg.so','libqgif.so','libqwebp.so','libqico.so'):continue
            target=plugins/group/path.name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target);license(path)
    environment=dict(os.environ,LD_LIBRARY_PATH=str(lib)+':'+str(lib/'libproxy'))
    # Target libc/C++ and GPU dispatch/driver ABI stay external. Everything else
    # newly referenced is copied with its Debian license; existing Qt wins.
    system=re.compile(r'^(?:ld-linux|libc\.|libm\.|libpthread\.|libdl\.|librt\.|libresolv\.|libstdc\+\+\.|libgcc_s\.|libEGL\.|libGLES|libGL(?:\.|X|dispatch)|libgbm\.|libdrm|libvulkan\.)')
    external=set();pending=[stage/'usr/bin/jume-files',stage/'usr/bin/pulseaudio']+list(plugins.rglob('*.so'))+list(audio.glob('*.so'));seen=set();needed={p.resolve() for p in pending}
    while pending:
        path=pending.pop()
        if path in seen:continue
        seen.add(path)
        result=subprocess.run(['ldd',str(path)],env=environment,text=True,capture_output=True,check=True).stdout
        if 'not found' in result:raise RuntimeError(result)
        direct=set(re.findall(r'\(NEEDED\).*?\[(.*?)\]',subprocess.check_output(['readelf','-d',str(path)],text=True)))
        for name,resolved in re.findall(r'^\s*(\S+) => (/\S+)',result,re.M):
            if name not in direct:continue
            source=Path(resolved)
            if source.is_relative_to(stage):needed.add(source.resolve());pending.append(source);continue
            if system.match(name):external.add(name);continue
            target=lib/name
            if not target.exists():shutil.copy2(source.resolve(),target);license(source);pending.append(target)
            needed.add(target.resolve())
    # The app uses Widgets, not the launcher's QML/Python/virtual-keyboard tree.
    # Keep only the actual ELF closure and selected dynamically loaded plugins.
    for path in sorted(lib.rglob('*'),reverse=True):
        if path.is_file() or path.is_symlink():
            if path.resolve() not in needed:path.unlink()
        elif path.is_dir() and not any(path.iterdir()):path.rmdir()
    source_files=list(code.glob('*'))+[Path('/mainline/gaming-shell/input.cpp'),Path('/mainline/gaming-shell/input.h')]
    receipt={'status':'HOST_CANDIDATE_R46H_UNTESTED','base_sha256':BASE,'packages':sorted(packages),'system_dependencies':sorted(external),
             'sources':{str(p.relative_to('/mainline')):digest(p) for p in source_files if p.is_file()}}
    (stage/'BUILD-INFO.json').write_text(json.dumps(receipt,indent=2)+'\n')
    files=sorted(p for p in stage.rglob('*') if p.is_file() and not p.is_symlink())
    (stage/'SHA256SUMS').write_text(''.join(f'{digest(p)}  {p.relative_to(stage)}\n' for p in files))
    target=out/'jume-files-arm64.tar.gz';incoming=target.with_suffix('.incoming')
    with incoming.open('wb') as stream:
        tar=subprocess.Popen(['tar','--sort=name','--mtime=@0','--owner=0','--group=0','--numeric-owner','-C',str(stage),'-cf','-','.'],stdout=subprocess.PIPE)
        gzip=subprocess.run(['gzip','-n'],stdin=tar.stdout,stdout=stream);tar.stdout.close()
        if tar.wait()!=0 or gzip.returncode!=0:raise RuntimeError('Archive failed')
    incoming.replace(target)
    receipt['runtime_sha256']=digest(target);receipt['runtime_bytes']=target.stat().st_size
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    (out/'runtime.sha256').write_text(receipt['runtime_sha256']+'\n')
    print(json.dumps(receipt,indent=2))
