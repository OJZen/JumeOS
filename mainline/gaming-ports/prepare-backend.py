#!/usr/bin/env python3
"""Assemble the pinned, private HarbourMaster Python runtime; never install globally."""
import argparse
import hashlib
import gzip
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import tempfile
import urllib.request
import zipfile


def prepare(output):
    output.mkdir(parents=True, exist_ok=True)
    destination = output / 'runtime'
    if destination.exists() and not (destination / 'SOURCE.json').is_file():
        raise ValueError('Refusing to replace an unrecognized runtime directory')
    downloads = output / 'downloads'
    downloads.mkdir(exist_ok=True)
    lock = json.loads(Path(__file__).with_name('backend-lock.json').read_text())
    with tempfile.TemporaryDirectory(prefix='package-', dir=output) as directory:
        stage = Path(directory)
        python = stage / 'python'
        python.mkdir()
        for entry in lock['files']:
            cached = downloads / Path(entry['name']).name
            if not cached.exists():
                with urllib.request.urlopen(entry['url'], timeout=30) as response:
                    data = response.read(entry['bytes'] + 1)
                if len(data) != entry['bytes'] or hashlib.sha256(data).hexdigest() != entry['sha256']:
                    raise ValueError('Downloaded dependency does not match the lock: ' + entry['name'])
                cached.write_bytes(data)
            data = cached.read_bytes()
            if len(data) != entry['bytes'] or hashlib.sha256(data).hexdigest() != entry['sha256']:
                raise ValueError('Cached dependency does not match the lock: ' + entry['name'])
            if entry['name'].endswith('.whl'):
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    for member in archive.infolist():
                        path = PurePosixPath(member.filename)
                        if path.is_absolute() or '..' in path.parts or '\\' in member.filename or (member.external_attr >> 16) & 0o170000 == 0o120000:
                            raise ValueError('Unsafe wheel path')
                    archive.extractall(python)
            else:
                name = entry['name'].removeprefix('PortMaster/pylibs/')
                target = python / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
        (stage / 'SOURCE.json').write_text(json.dumps(lock, indent=2) + '\n')
        # Python code and license metadata only; no entry point is registered.
        with (output / 'portmaster-backend.tar.gz.incoming').open('wb') as compressed, gzip.GzipFile(filename='', mode='wb', fileobj=compressed, mtime=0) as stream, tarfile.open(fileobj=stream, mode='w') as archive:
            for path in sorted(stage.rglob('*')):
                if not path.is_file():
                    continue
                info = archive.gettarinfo(path, str(path.relative_to(stage)))
                info.uid = info.gid = info.mtime = 0
                info.uname = info.gname = ''
                info.mode = 0o644
                with path.open('rb') as content:
                    archive.addfile(info, content)
        (output / 'portmaster-backend.tar.gz.incoming').replace(output / 'portmaster-backend.tar.gz')
        destination = output / 'runtime'
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(stage, destination)
    artifact = output / 'portmaster-backend.tar.gz'
    receipt = {'status': 'BACKEND_RUNTIME_PREPARED', 'upstream_commit': lock['upstream_commit'],
               'lock_sha256': hashlib.sha256(Path(__file__).with_name('backend-lock.json').read_bytes()).hexdigest(),
               'bytes': artifact.stat().st_size, 'sha256': hashlib.sha256(artifact.read_bytes()).hexdigest()}
    (output / 'runtime.sha256').write_text(receipt['sha256'] + '\n')
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(receipt))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if not args.output.is_absolute():
        parser.error('output must be an absolute external workspace path')
    prepare(args.output)
