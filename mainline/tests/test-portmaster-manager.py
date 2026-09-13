#!/usr/bin/env python3
"""Real pinned HarbourMaster + disposable packages; no game/launcher execution."""
import argparse
import errno
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
from unittest.mock import patch
import zipfile

repo = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('portmanager', repo / 'mainline/gaming-ports/manager.py')
manager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manager)


def check(runtime):
    original_cwd = Path.cwd()
    original_home = os.environ.get('HOME')
    os.umask(0o077)
    with tempfile.TemporaryDirectory(prefix='portmaster-check-', dir=repo / 'mainline/out/.cache') as directory:
        root = Path(directory)
        state = root / 'state'
        original_save = root / 'original/save'
        original_save.parent.mkdir()
        original_save.write_text('original progress')
        managed_save = state / 'tools/ports/example/saves/save'
        managed_save.parent.mkdir(parents=True)
        managed_save.write_text('managed progress')
        host_home = root / 'host-home'
        host_home.mkdir()
        os.environ['HOME'] = str(host_home)

        def package(version, runtimes=None):
            path = root / f'example-{version}.zip'
            info = {'version': 4, 'name': 'example.zip', 'items': ['Example.sh', 'example/'],
                    'attr': {'title': 'Example', 'runtime': runtimes or [], 'reqs': [], 'arch': ['aarch64']}}
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('Example.sh', '#!/bin/sh\ntouch THIS_SCRIPT_MUST_NOT_RUN\n')
                archive.writestr('example/port.json', json.dumps(info))
                archive.writestr('example/game', b'\x7fELF' + version.encode())
            return path

        try:
            store = manager.Store(state, runtime)
            assert Path.home() == store.root and Path.home() != host_home
            from harbourmaster.util import CancelEvent
            import requests
            def private_credentials(*args, **kwargs):
                raise AssertionError('Host credentials must never be consulted')
            requests.sessions.get_netrc_auth = private_credentials
            session = requests.sessions.Session()
            assert session.trust_env is False
            request = session.prepare_request(requests.Request('GET', 'https://example.invalid/'))
            assert 'Authorization' not in request.headers
            assert store.catalog()['ports'] == []
            store.install('example.zip', package('v1'))
            record = store.index['packages']['example.zip']
            first = record['generation']
            assert (store.packages / 'example' / first / 'example/game').read_bytes() == b'\x7fELFv1'
            store.install('example.zip', package('v2'))
            second = store.index['packages']['example.zip']['generation']
            assert first != second and store.index['packages']['example.zip']['previous']['generation'] == first
            store.rollback('example.zip')
            assert store.index['packages']['example.zip']['generation'] == first
            before = store.index_path.read_bytes()

            def refused(archive):
                try:
                    store.install('example.zip', archive)
                except (ValueError, OSError, CancelEvent):
                    pass
                else:
                    raise AssertionError('Unsafe/failed package was accepted')
                assert store.index_path.read_bytes() == before
                assert not list(store.operations.iterdir()), 'transaction not cleaned'

            bad = root / 'bad.zip'
            for name in ['../escape', '/absolute', 'example/../../escape', 'C:/escape', 'example\\escape']:
                with zipfile.ZipFile(bad, 'w') as archive:
                    archive.writestr(name, 'must not extract')
                refused(bad)
            with zipfile.ZipFile(bad, 'w') as archive:
                info = zipfile.ZipInfo('example/link')
                info.external_attr = (0o120777 << 16)
                archive.writestr(info, str(original_save))
            refused(bad)
            refused(package('missing-runtime', ['missing.squashfs']))
            from harbourmaster import harbour
            download = harbour.download
            store.manager.runtimes_info['dummy.squashfs'] = {'name': 'dummy.squashfs', 'remote': {'aarch64':
                {'name': 'dummy.squashfs', 'md5': '098f6bcd4621d373cade4e832627b4f6', 'size': 4, 'url': 'https://example.invalid/runtime'}}}
            harbour.download = lambda *args, **kwargs: None
            refused(package('failed-runtime-download', ['dummy.squashfs']))
            def wrong_runtime(path, *args, **kwargs):
                path.write_bytes(b'wrong')
                return path
            harbour.download = wrong_runtime
            refused(package('bad-runtime-digest', ['dummy.squashfs']))
            harbour.download = download
            manager.cancelled = True
            refused(package('cancelled'))
            manager.cancelled = False

            atomic = manager.atomic_json
            def failed_commit(path, value):
                if path == store.index_path:
                    raise OSError('synthetic commit failure')
                atomic(path, value)
            manager.atomic_json = failed_commit
            refused(package('failed-save'))
            manager.atomic_json = atomic
            assert store.index['packages']['example.zip']['generation'] == first
            assert len(list((store.packages / 'example').iterdir())) == 2
            def good_runtime(path, *args, **kwargs):
                path.write_bytes(b'test')
                return path
            harbour.download = good_runtime
            fsync = os.fsync
            index_directory = store.index_path.parent.stat()
            def failed_directory_sync(fd):
                current = os.fstat(fd)
                if stat.S_ISDIR(current.st_mode) and (current.st_dev, current.st_ino) == (index_directory.st_dev, index_directory.st_ino):
                    raise OSError(errno.EIO, 'directory fsync failed after index publication')
                fsync(fd)
            with patch.object(os, 'fsync', side_effect=failed_directory_sync):
                try:
                    store.install('example.zip', package('published-before-fsync-failure', ['dummy.squashfs']))
                except OSError:
                    pass
                else:
                    raise AssertionError('Durability failure was reported as success')
            published = json.loads(store.index_path.read_text())
            assert store.index == published, 'Memory must follow the already-published index'
            current = published['packages']['example.zip']
            assert (store.packages / 'example' / current['generation'] / 'example/game').is_file()
            assert current['previous']['generation'] == first
            assert (store.packages / 'example' / first / 'example/game').is_file()
            for token in current['runtimes'].values():
                assert manager.digest(store.runtime_files / token) == token, 'Published runtime was deleted during cleanup'
            assert not list(store.operations.iterdir())
            store.install('example.zip', package('runtime-good', ['dummy.squashfs']))
            assert len(list(store.runtime_files.iterdir())) == 1
            def duplicate_download(*args, **kwargs):
                raise AssertionError('Verified runtime should be reused')
            harbour.download = duplicate_download
            store.install('example.zip', package('runtime-reuse', ['dummy.squashfs']))
            cached = store.runtime_files / store.index['runtimes']['dummy.squashfs']['sha256']
            cached.write_bytes(b'bad!')
            downloads = []
            def repair_runtime(path, *args, **kwargs):
                downloads.append(path)
                return good_runtime(path, *args, **kwargs)
            harbour.download = repair_runtime
            store.install('example.zip', package('runtime-repair', ['dummy.squashfs']))
            assert len(downloads) == 1 and cached.read_bytes() == b'test'
            assert manager.digest(cached) == cached.name
            # Replace the cache link itself, never the file it points at.
            cached.unlink(); cached.symlink_to(original_save)
            store.install('example.zip', package('runtime-link-repair', ['dummy.squashfs']))
            assert len(downloads) == 2 and not cached.is_symlink() and manager.digest(cached) == cached.name
            harbour.download = download
            store.uninstall('example.zip')
            assert not list(store.runtime_files.iterdir())
            assert not (store.packages / 'example').exists()
            assert original_save.read_text() == 'original progress'
            assert managed_save.read_text() == 'managed progress'
            assert not list(root.rglob('THIS_SCRIPT_MUST_NOT_RUN'))
            assert not list(store.operations.iterdir())
            outside = root / 'outside'; outside.mkdir()
            registry = root / 'linked-state/tools/portmaster/registry'; registry.parent.mkdir(parents=True)
            registry.symlink_to(outside, target_is_directory=True)
            try:
                manager.Store(root / 'linked-state', runtime)
            except ValueError:
                pass
            else:
                raise AssertionError('Linked registry accepted')
            assert not list(outside.iterdir())
            print('PORTMASTER_MANAGER_PASS: install/update/rollback, unsafe ZIP and runtime rejection, cancellation, pre/post-publication failure, corrupt/link cache repair, uninstall preserves both save locations; no launcher executed')
        finally:
            os.chdir(original_cwd)
            if original_home is None:
                os.environ.pop('HOME', None)
            else:
                os.environ['HOME'] = original_home


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    check(parser.parse_args().runtime.resolve())
