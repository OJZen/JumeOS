#!/usr/bin/env python3
"""Private HarbourMaster adapter. Packages and runtimes never share original/save paths."""
import argparse
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import stat
import sys
import tempfile
import time
import uuid
import zipfile

CATALOG = 'https://github.com/PortsMaster/PortMaster-New/releases/latest/download/ports.json'
MAX_ARCHIVE = 512 * 1024 * 1024
MAX_UNPACKED = 2 * 1024 * 1024 * 1024
RESERVE = 64 * 1024 * 1024
cancelled = False


def emit(**value):
    print(json.dumps(value, ensure_ascii=False, separators=(',', ':')), flush=True)


def private_dir(path):
    if any(item.is_symlink() for item in [path, *path.parents]):
        raise ValueError('管理目录包含链接，未写入')
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise ValueError('管理目录权限不正确')
    return path


def read_json(path, default=None):
    if not path.exists() and not path.is_symlink():
        return default
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o022 or info.st_size > 16 * 1024 * 1024:
        raise ValueError('配置文件不可安全读取，原文件已保留')
    return json.loads(path.read_text())


class PublishedWriteError(OSError):
    """The new file is visible, but its directory could not be durably synced."""


def atomic_json(path, value):
    if path.exists() or path.is_symlink():
        read_json(path)  # Refuse to replace a malformed or unsafe existing record.
    fd, name = tempfile.mkstemp(prefix='.json-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        try:
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        except OSError as error:
            raise PublishedWriteError('记录已更新，但未能确认持久保存；文件已保留，请检查存储后刷新。') from error
    finally:
        if os.path.exists(name):
            os.unlink(name)


def digest(path, algorithm='sha256'):
    value = hashlib.new(algorithm)
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(data)
    return value.hexdigest()


def package_id(name):
    if not isinstance(name, str) or not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{0,110}\.zip', name) or name in ('portmaster.zip',) or name.endswith('.theme.zip'):
        raise ValueError('无效的游戏标识')
    return name[:-4]


def validate_archive(path):
    if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_ARCHIVE:
        raise ValueError('安装包不可用或超过 512 MiB')
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        if len(entries) > 50000 or sum(entry.file_size for entry in entries) > MAX_UNPACKED:
            raise ValueError('安装包展开后超过本次上限')
        seen = set()
        for entry in entries:
            name = entry.filename
            item = PurePosixPath(name)
            mode = entry.external_attr >> 16
            if not name or item.is_absolute() or '..' in item.parts or '\\' in name or ':' in name or any(ord(c) < 32 for c in name) or item.as_posix() in seen:
                raise ValueError('安装包包含不安全或重复路径')
            if stat.S_IFMT(mode) not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise ValueError('安装包包含链接或设备文件')
            seen.add(item.as_posix())
        if shutil.disk_usage(path.parent).free < sum(entry.file_size for entry in entries) + RESERVE:
            raise ValueError('剩余空间不足，现有安装未改动')


def load_backend(runtime, root):
    if sys.version_info < (3, 10):
        raise ValueError('PortMaster 后端需要 Python 3.10 或更新版本')
    python = runtime / 'python'
    if not (python / 'harbourmaster/harbour.py').is_file():
        raise ValueError('PortMaster 后端尚未准备')
    sys.path.insert(0, str(python))
    # Keep upstream's import-time path defaults and home probes inside this private workspace.
    os.environ['HOME'] = str(root)
    for key in ('HM_TOOLS_DIR', 'HM_PORTS_DIR', 'HM_SCRIPTS_DIR', 'XDG_DATA_HOME'):
        os.environ[key] = str(root)
    os.chdir(root)
    import requests
    class PublicSession(requests.Session):
        def __init__(self):
            super().__init__()
            self.trust_env = False  # No host .netrc, proxy credentials or environment auth.
    requests.sessions.Session = requests.Session = PublicSession
    from loguru import logger
    logger.remove()
    import utility
    utility.do_cprint_output(sys.stderr)
    from harbourmaster import harbour, source
    harbour.PORTMASTER_DEBUG = False  # Normally supplied by the upstream CLI entry point.
    from harbourmaster.platform import PlatformBase
    from harbourmaster.util import Callback, CancelEvent

    # A target filter, not a claim that this host is an R46H or can launch its games.
    harbour.device_info = lambda: {'name': 'r46h-mainline', 'device': 'r46h', 'primary_arch': 'aarch64',
                                  'glibc': '2.41', 'capabilities': ['aarch64', 'analog_0', 'analog_1', 'analog_2', 'gles2', 'gles3', '1024x768', '4:3', 'hires']}

    class Progress(Callback):
        def __init__(self):
            super().__init__()
            self.last = 0

        def progress(self, message, amount, total=None, fmt=None):
            if cancelled:
                self.was_cancelled = True
                raise CancelEvent('已取消')
            if fmt == 'data' and (amount > MAX_ARCHIVE or shutil.disk_usage(root).free < RESERVE):
                raise CancelEvent('下载超出大小或空间上限')
            now = time.monotonic()
            if now - self.last >= .15 or amount == total:
                self.last = now
                value = amount / total if isinstance(amount, (int, float)) and isinstance(total, (int, float)) and total > 0 else -1
                emit(event='progress', progress=max(-1, min(1, value)))

        def message(self, message):
            if cancelled:
                raise CancelEvent('已取消')

        def message_box(self, message, **kwargs):
            return False

    class CatalogSource(source.PortMasterV3):
        def _update(self):
            # ponytail: no bulk image cache; selected-game artwork can be fetched on demand.
            pass

        def _load_images(self):
            self.images = {}

        def save(self):
            atomic_json(self._file_name, self._config)

    source.HM_SOURCE_APIS['PortMasterV3'] = CatalogSource

    class Manager(harbour.HarbourMaster):
        def save_config(self):
            atomic_json(self.cfg_file, self.cfg_data)
            atomic_json(self.runtimes_file, self.runtimes_info)

        def load_ports(self):
            # Each installed package has an isolated release; never scan or repair /roms.
            self.installed_ports, self.broken_ports, self.unknown_ports = {}, {}, []

        def _fix_permissions(self, path_check=None):
            path = path_check or self.ports_dir
            if path.is_symlink() or not path.resolve().is_relative_to(self.ports_dir.resolve()):
                raise ValueError('安装权限范围不正确')
            for entry in [path, *path.rglob('*')] if path.is_dir() else [path]:
                if entry.is_symlink():
                    raise ValueError('安装目录包含链接')
                executable = entry.suffix == '.sh'
                if entry.is_file():
                    with entry.open('rb') as stream:
                        prefix = stream.read(4)
                    executable |= prefix.startswith((b'\x7fELF', b'#!'))
                entry.chmod(0o700 if entry.is_dir() or executable else 0o600)

        def _install_port(self, download_info, do_delete=False):
            validate_archive(download_info['zip_file'])
            from harbourmaster.captain import check_port
            self.package_info = check_port(download_info['name'], download_info['zip_file'])
            if not self.match_requirements(self.package_info):
                raise ValueError('尚未确认此安装包的运行条件')
            return super()._install_port(download_info, do_delete)

        def check_runtime(self, runtime, port_name=None, in_install=False):
            runtime = runtime if runtime.endswith('.squashfs') else runtime + '.squashfs'
            if not re.fullmatch(r'[A-Za-z0-9_.-]+\.squashfs', runtime):
                raise ValueError('无效的运行库名称')
            remote = self.runtimes_info.get(runtime, {}).get('remote', {}).get('aarch64')
            if not remote or remote.get('size', MAX_ARCHIVE + 1) > MAX_ARCHIVE:
                raise ValueError('没有适用的 AArch64 运行库，未切换版本')
            cached = getattr(self, 'runtime_cache', {}).get(runtime)
            if cached and cached['md5'] == remote['md5']:
                path = self.runtime_pool / cached['sha256']
                if path.is_file() and not path.is_symlink() and digest(path) == cached['sha256']:
                    self.used_runtimes[runtime] = cached
                    return 0
            result = super().check_runtime(runtime, port_name, in_install)
            path = self.libs_dir / runtime
            if result != 0 or not path.is_file() or path.is_symlink() or digest(path, 'md5') != remote['md5']:
                raise ValueError('运行库下载或校验失败，未切换版本')
            self.used_runtimes[runtime] = {'sha256': digest(path), 'md5': remote['md5'], 'bytes': path.stat().st_size}
            return 0

    def create(tools, ports, temp, offline=True):
        config = private_dir(tools / 'PortMaster/config')
        config_file = config / 'config.json'
        if not config_file.exists():
            atomic_json(config_file, {'version': 2, 'first-run': False, 'gamelist_update': False})
        source_file = config / '020_portmaster.source.json'
        if not source_file.exists():
            atomic_json(source_file, {'prefix': 'pm', 'api': 'PortMasterV3', 'name': 'PortMaster', 'url': CATALOG,
                                      'last_checked': None, 'version': 2, 'data': {}})
        elif read_json(source_file)['url'] != CATALOG:
            raise ValueError('未配置的目录来源')
        if list(config.glob('*.source.json')) != [source_file]:
            raise ValueError('管理目录存在额外来源，请先核对')
        instance = Manager({'no-check': True, 'offline': offline, 'quiet': True}, tools_dir=tools,
                           ports_dir=ports, scripts_dir=ports, temp_dir=temp, callback=Progress())
        instance.platform = PlatformBase(instance)
        return instance
    return create


class Store:
    def __init__(self, state, runtime):
        self.root = private_dir(state / 'tools/portmaster')
        self.packages = private_dir(self.root / 'packages')
        self.operations = private_dir(self.root / 'operations')
        self.runtime_files = private_dir(self.root / 'runtimes')
        self.make_manager = load_backend(runtime, self.root)
        self.manager = self.make_manager(self.root / 'registry', private_dir(self.root / 'inspection'), self.operations)
        self.index_path = self.root / 'installed.json'
        self.index = read_json(self.index_path, {'version': 1, 'packages': {}})
        if not isinstance(self.index, dict) or self.index.get('version') != 1 or not isinstance(self.index.get('packages'), dict) or not isinstance(self.index.get('runtimes', {}), dict):
            raise ValueError('安装记录无效，原文件已保留')
        self.index.setdefault('runtimes', {})
        for name, record in self.index['packages'].items():
            package_id(name)
            if not isinstance(record, dict) or not re.fullmatch(r'[0-9a-f]{32}', str(record.get('generation', ''))):
                raise ValueError('安装版本记录无效')
        for record in self.index['runtimes'].values():
            if not isinstance(record, dict) or not re.fullmatch(r'[0-9a-f]{64}', str(record.get('sha256', ''))) or not re.fullmatch(r'[0-9a-f]{32}', str(record.get('md5', ''))):
                raise ValueError('运行库记录无效')
        self.collect_runtimes()

    def collect_runtimes(self):
        referenced = set()
        for record in self.index['packages'].values():
            for version in (record, record.get('previous')):
                if version:
                    runtimes = version.get('runtimes', {})
                    if not isinstance(runtimes, dict) or any(not re.fullmatch(r'[0-9a-f]{64}', str(token)) for token in runtimes.values()):
                        raise ValueError('运行库引用记录无效')
                    referenced.update(runtimes.values())
        cache = {name: item for name, item in self.index['runtimes'].items() if item['sha256'] in referenced}
        if cache != self.index['runtimes']:
            self.index['runtimes'] = cache
            atomic_json(self.index_path, self.index)
        # This private content-addressed pool contains downloaded runtimes only.
        for path in self.runtime_files.iterdir():
            if path.name not in referenced and re.fullmatch(r'[0-9a-f]{64}', path.name) and path.is_file() and not path.is_symlink():
                path.unlink()

    def catalog(self, query='', offset=0, limit=50, installed_only=False):
        source = self.manager.sources['pm']
        result = []
        names = list(self.index['packages']) if installed_only else source.ports
        for name in names:
            info = source.port_info(name) or {'attr': self.index['packages'][name].get('info', {})}
            title = info.get('attr', {}).get('title', name)
            if query.casefold() not in (title + ' ' + name).casefold():
                continue
            package_id(name)
            result.append({'id': name, 'title': title, 'installed': name in self.index['packages'],
                           'bytes': source.port_download_size(name, False), 'compatible': self.manager.match_requirements(info)})
        result.sort(key=lambda entry: (entry['title'].casefold(), entry['id']))
        return {'ports': result[offset:offset + limit], 'total': len(result), 'offset': offset}

    def refresh(self):
        source = self.manager.sources['pm']
        source.update()
        if not source._did_update:
            raise ValueError('目录刷新失败，已保留上次结果')
        return self.catalog()

    def details(self, name):
        package_id(name)
        source = self.manager.sources['pm']
        info = source.port_info(name)
        if not info and name in self.index['packages']:
            info = {'attr': self.index['packages'][name].get('info', {})}
        if not info:
            raise ValueError('目录中没有这个游戏')
        attr = info.get('attr', {})
        installed = self.index['packages'].get(name)
        return {'id': name, 'title': attr.get('title', name), 'description': attr.get('desc', ''),
                'instructions': attr.get('inst', ''), 'readyToRun': bool(attr.get('rtr', False)), 'runtime': attr.get('runtime', []),
                'bytes': source.port_download_size(name), 'compatible': self.manager.match_requirements(info),
                'installed': bool(installed), 'rollbackAvailable': bool(installed and installed.get('previous')), 'updateAvailable': bool(installed and info.get('source', {}).get('md5') and installed['md5'] != info['source']['md5'])}

    def install(self, name, archive=None):
        slug = package_id(name)
        package = private_dir(self.packages / slug)
        with tempfile.TemporaryDirectory(prefix='install-', dir=self.operations) as directory:
            stage = Path(directory)
            if archive is None:
                source = self.manager.sources['pm']
                if name not in source.ports or source.port_download_size(name, False) > MAX_ARCHIVE:
                    raise ValueError('安装包不存在或超过大小上限')
                if not self.manager.match_requirements(source.port_info(name)):
                    raise ValueError('此安装包不符合当前设备配置')
                download_info = source.download(name, temp_dir=stage)
                if not download_info:
                    raise ValueError('下载或校验失败，已有安装未改动')
            else:
                validate_archive(archive)
                local = stage / name
                shutil.copyfile(archive, local)
                from harbourmaster.info import port_info_load
                download_info = port_info_load({})
                download_info.update({'name': name, 'zip_file': local, 'status': {'source': 'local', 'md5': digest(local, 'md5'), 'status': 'downloaded'}})
            validate_archive(download_info['zip_file'])
            manager = self.make_manager(stage / 'tools', private_dir(stage / 'content'), stage, offline=False)
            manager.runtimes_info = copy.deepcopy(self.manager.runtimes_info)
            manager.runtime_cache = self.index['runtimes']
            manager.runtime_pool = self.runtime_files
            manager.used_runtimes = {}
            # Download runtimes only into the transaction. Never update a shared live file.
            result = manager._install_port(download_info)
            if result != 0 or cancelled:
                raise ValueError('安装未完成，已有安装和存档已保留')
            runtime_paths = {name: data['sha256'] for name, data in manager.used_runtimes.items()}
            for runtime_name, runtime_data in manager.used_runtimes.items():
                destination = self.runtime_files / runtime_data['sha256']
                downloaded = manager.libs_dir / runtime_name
                # A verified download also repairs an existing corrupt file or link.
                if downloaded.is_file():
                    downloaded.replace(destination)
            generation = uuid.uuid4().hex
            destination = package / generation
            (stage / 'content').replace(destination)
            old = self.index['packages'].get(name)
            previous = {key: value for key, value in old.items() if key != 'previous'} if old else None
            before = copy.deepcopy(self.index)
            record = {'generation': generation, 'previous': previous,
                      'md5': download_info['status']['md5'], 'runtimes': runtime_paths,
                      'info': {key: manager.package_info.get('attr', {}).get(key, '') for key in ['title', 'desc', 'inst', 'runtime', 'rtr']}}
            self.index['packages'][name] = record
            self.index['runtimes'].update(manager.used_runtimes)
            try:
                atomic_json(self.index_path, self.index)
            except PublishedWriteError:
                # The visible index already refers to this generation and its runtimes.
                # Retain both versions while durability is uncertain, and report failure.
                raise
            except Exception:
                self.index = before
                shutil.rmtree(destination)
                self.collect_runtimes()
                raise
            keep = {record['generation'], previous['generation'] if previous else None}
            for path in package.iterdir():
                if path.name not in keep and re.fullmatch(r'[0-9a-f]{32}', path.name) and path.is_dir() and not path.is_symlink():
                    shutil.rmtree(path)
            self.collect_runtimes()
            return {'id': name, 'installed': True, 'launchReady': False}

    def rollback(self, name):
        slug = package_id(name)
        record = self.index['packages'].get(name, {})
        previous = record.get('previous')
        if not isinstance(previous, dict) or not re.fullmatch(r'[0-9a-f]{32}', str(previous.get('generation', ''))):
            raise ValueError('没有可回退的版本')
        path = self.packages / slug / previous['generation']
        if not path.is_dir() or path.is_symlink():
            raise ValueError('上一版本文件不可用')
        self.index['packages'][name] = {**previous, 'previous': {key: value for key, value in record.items() if key != 'previous'}}
        atomic_json(self.index_path, self.index)
        return {'id': name, 'rolledBack': True}

    def uninstall(self, name):
        slug = package_id(name)
        package = self.packages / slug
        if name not in self.index['packages'] and not package.exists():
            raise ValueError('该游戏尚未安装')
        if package.is_symlink():
            raise ValueError('安装目录包含链接，未删除')
        # Only package code lives here; original data and managed saves are elsewhere.
        self.index['packages'].pop(name, None)
        atomic_json(self.index_path, self.index)
        if package.exists():
            shutil.rmtree(package)
        self.collect_runtimes()
        return {'id': name, 'installed': False, 'savesPreserved': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('action', choices=['catalog', 'refresh', 'details', 'install', 'uninstall', 'rollback'])
    parser.add_argument('--id', default='')
    parser.add_argument('--query', default='')
    parser.add_argument('--offset', type=int, default=0)
    parser.add_argument('--installed', action='store_true')
    parser.add_argument('--archive', type=Path, help='Explicit local package; never an original launcher')
    args = parser.parse_args()
    if not args.runtime.is_absolute() or not args.state.is_absolute() or not 0 <= args.offset <= 20000 or len(args.query) > 80 or (args.archive is not None and not args.archive.is_absolute()):
        parser.error('Invalid path, query or offset')
    os.umask(0o077)
    root = private_dir(args.state / 'tools/portmaster')
    lock = os.open(root / '.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        store = Store(args.state, args.runtime)
        if args.action == 'catalog':
            result = store.catalog(args.query, args.offset, installed_only=args.installed)
        elif args.action == 'refresh':
            result = store.refresh()
        elif args.action == 'details':
            result = store.details(args.id)
        elif args.action == 'install':
            result = store.install(args.id, args.archive)
        elif args.action == 'rollback':
            result = store.rollback(args.id)
        else:
            result = store.uninstall(args.id)
        emit(event='result', ok=True, **result)
        return 0
    except Exception as error:
        emit(event='result', ok=False, message='已取消' if cancelled else str(error)[:240])
        return 1
    finally:
        os.close(lock)


if __name__ == '__main__':
    def cancel(signum, frame):
        global cancelled
        cancelled = True
    signal.signal(signal.SIGTERM, cancel)
    signal.signal(signal.SIGINT, cancel)
    sys.exit(main())
