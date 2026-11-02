#!/usr/bin/env python3
"""Exercise the release-pinned fallback overlay against owned files and fake systemd calls."""
import fcntl
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
CODE = REPO / 'mainline/gaming-wayland'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fallback = load('jume_fallback', CODE / 'product-fallback.py')
product = load('jume_product', CODE / 'product-install.py')
load_installer = fallback.load_installer


class FallbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='jume-fallback-', dir=REPO / 'mainline/out/.cache')
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.root = root / 'product'
        self.release = self.root / 'releases' / fallback.RELEASE
        self.release.mkdir(parents=True)
        service = (CODE / 'jume-launcher.service').read_bytes()
        (self.release / 'jume-launcher.service').write_bytes(service)
        (self.root / 'current').symlink_to(self.release)
        self.unit = root / 'system/jume-launcher.service'
        self.base_dropin = root / 'system/esde.d/50-jume.conf'
        self.base_dropin.parent.mkdir(parents=True)
        self.unit.write_bytes(service)
        self.base_dropin.write_bytes(product.DROPIN_CONTENT)
        self.helper = self.root / 'esde-fallback.py'
        self.handler = root / 'system/jume-esde-fallback.service'
        self.dropin = root / 'system/jume.d/60-esde-fallback.conf'
        self.boot = root / 'run/esde.d/90-jume-fallback.conf'
        self.trial = root / 'run/trial'
        self.calls = []
        self.state = 'inactive'
        self.conditions = product.DROPIN_CONTENT.decode()
        original_sealed = product.sealed
        patches = [
            patch.multiple(fallback, ROOT=self.root, HELPER=self.helper, SERVICE=self.handler,
                           DROPIN=self.dropin, BOOT_OVERRIDE=self.boot),
            patch.multiple(product, ROOT=self.root, UNIT=self.unit, DROPIN=self.base_dropin, TRIAL=self.trial),
            patch.object(fallback, 'load_installer', return_value=product),
            patch.object(product, 'target'),
            patch.object(product, 'verify'),
            patch.object(product, 'sealed', side_effect=lambda path:
                         original_sealed(path, os.getuid()) if path == root or path.is_relative_to(root) else None),
            patch.object(product, 'unit_value', side_effect=lambda key: self.state if key == 'ActiveState' else 'disabled'),
            patch.object(product, 'clean_runtime'),
            patch.object(product, 'systemctl', side_effect=lambda *args: self.calls.append(args)),
            patch.object(fallback.subprocess, 'check_output', side_effect=lambda *a, **kw:
                         self.conditions + (fallback.BOOT_DATA.decode() if self.boot.exists() else '')),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def install(self):
        fallback.main(['--install'])
        self.assertEqual(self.dropin.read_bytes(), fallback.DROPIN_DATA)
        self.assertEqual(self.handler.read_bytes(), fallback.SERVICE_DATA)
        self.assertFalse((self.root / 'enabled').exists())
        self.assertFalse(self.boot.exists())
        self.calls.clear()

    def test_recovery_preserves_next_boot_and_user_data(self):
        self.install()
        (self.root / 'enabled').write_bytes(b'jume\n')
        save = self.root / 'save.fixture'
        save.write_bytes(b'unchanged progress')
        self.state = 'failed'
        fallback.main(['--recover'])
        product.clean_runtime.assert_called()
        self.assertEqual(self.boot.read_bytes(), fallback.BOOT_DATA)
        self.assertEqual(self.calls, [('daemon-reload',), ('start', 'r46h-gaming-frontend.service'),
                                     ('is-active', '--quiet', 'r46h-gaming-frontend.service')])
        self.assertEqual((self.root / 'enabled').read_bytes(), b'jume\n')
        self.assertEqual(save.read_bytes(), b'unchanged progress')
        self.assertEqual(self.base_dropin.read_bytes(), product.DROPIN_CONTENT)
        self.assertEqual(self.unit.read_bytes(), (self.release / 'jume-launcher.service').read_bytes())
        fallback.main(['--recover'])  # Owned runtime override is retryable.

    def test_cleanup_failure_never_unlocks_esde(self):
        self.install()
        self.state = 'failed'
        with patch.object(product, 'clean_runtime', side_effect=ValueError('lease still held')):
            with self.assertRaises(ValueError):
                fallback.main(['--recover'])
        self.assertFalse(self.boot.exists())
        self.assertEqual(self.calls, [])

    def test_normal_stop_and_active_session_do_not_trigger_fallback(self):
        self.install()
        for state in ('inactive', 'active', 'activating', 'deactivating'):
            self.state = state
            with self.assertRaises(ValueError):
                fallback.main(['--recover'])
            self.assertFalse(self.boot.exists())
        self.assertEqual(self.calls, [])
        self.assertNotIn(b'OnSuccess=', fallback.DROPIN_DATA)

    def test_foreign_files_and_conditions_are_preserved(self):
        self.install()
        for path in (self.helper, self.handler, self.dropin, self.boot):
            original = path.read_bytes() if path.exists() else None
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'foreign configuration')
            with self.assertRaises(ValueError):
                fallback.main(['--install'])
            self.assertEqual(path.read_bytes(), b'foreign configuration')
            if original is None:
                path.unlink()
            else:
                path.write_bytes(original)
        self.conditions += 'ConditionPathExists=/unrelated/guard\n'
        with self.assertRaises(ValueError):
            fallback.main(['--install'])
        self.assertEqual(self.calls, [])

    def test_wrong_release_and_concurrent_operation_refused(self):
        self.install()
        with (self.root / 'operation.lock').open('rb') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                fallback.main(['--install'])
        (self.root / 'current').unlink()
        (self.root / 'current').symlink_to(self.release.parent / ('a' * 64))
        with self.assertRaises(ValueError):
            fallback.main(['--recover'])
        self.assertEqual(self.calls, [])

    def test_recovery_waits_for_promotion_lock(self):
        self.install()
        self.state = 'failed'
        with (self.root / 'operation.lock').open('rb') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            release = threading.Timer(0.05, lambda: fcntl.flock(lock, fcntl.LOCK_UN))
            release.start()
            try:
                fallback.main(['--recover'])
            finally:
                release.join()
        self.assertTrue(self.boot.exists())

    def test_writable_or_symlink_config_refused(self):
        self.install()
        self.dropin.chmod(0o666)
        with self.assertRaises(ValueError):
            fallback.main(['--remove'])
        self.dropin.chmod(0o644)
        self.dropin.unlink()
        self.dropin.symlink_to(self.handler)
        with self.assertRaises(ValueError):
            fallback.main(['--install'])
        self.assertTrue(self.dropin.is_symlink())
        self.assertEqual(self.handler.read_bytes(), fallback.SERVICE_DATA)

    def test_install_requires_explicit_rollback(self):
        (self.root / 'enabled').write_text('jume\n')
        with self.assertRaises(ValueError):
            fallback.main(['--install'])
        self.assertFalse(self.helper.exists())
        self.assertEqual(self.calls, [])

    def test_nonregular_recovery_code_is_not_read(self):
        path = self.release / 'product-install.py'
        os.mkfifo(path)
        with self.assertRaisesRegex(ValueError, 'script type/size'):
            load_installer()

    def test_install_retry_and_remove_only_owned_files(self):
        self.install()
        self.install()
        keep = self.dropin.parent / 'operator-note.txt'
        keep.write_text('preserve')
        fallback.main(['--remove'])
        for path in (self.helper, self.handler, self.dropin, self.boot):
            self.assertFalse(path.exists())
        self.assertEqual(keep.read_text(), 'preserve')
        self.assertTrue(self.unit.exists())
        self.assertTrue(self.base_dropin.exists())

    def test_esde_start_failure_is_not_reported_as_recovered(self):
        self.install()
        self.state = 'failed'
        with patch.object(product, 'systemctl', side_effect=subprocess.CalledProcessError(1, 'systemctl')):
            with self.assertRaises(subprocess.CalledProcessError):
                fallback.main(['--recover'])
        self.assertTrue(self.boot.exists())  # Retain the owned override for diagnosis/retry.


if __name__ == '__main__':
    unittest.main()
