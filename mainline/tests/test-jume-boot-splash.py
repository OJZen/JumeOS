#!/usr/bin/env python3
"""Boot framebuffer ownership, bounded handoff and failure cleanup; no real device."""
import gzip
import importlib.util
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, call, patch

REPO = Path(__file__).resolve().parents[2]
CODE = REPO / 'mainline/gaming-wayland'
spec = importlib.util.spec_from_file_location('boot_splash', CODE / 'boot-splash.py')
splash = importlib.util.module_from_spec(spec)
spec.loader.exec_module(splash)


class SplashTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=REPO / 'mainline/out/.cache', prefix='splash-test-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.marker = self.root / 'tty1-owned'
        self.asset = self.root / 'image.gz'
        self.fb = SimpleNamespace(KDGETMODE=0x4B3B, KDSETMODE=0x4B3A, KD_TEXT=0, KD_GRAPHICS=1,
                                  fb_mode=Mock(), write_all_at=Mock(), read_exact_at=Mock(return_value=b'pixels'))
        patches = [patch.multiple(splash, MARKER=self.marker, ASSET=self.asset, STOP=False),
                   patch.object(splash, 'boot_id', return_value='current-boot')]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def run_show(self, *, tty=None, clocks=None):
        with patch.object(splash, 'active_tty', side_effect=tty or ['tty1', 'tty2', 'tty2']), \
             patch.object(Path, 'read_text', return_value='rockchipdrmfb'), \
             patch.object(splash, 'picture', return_value=b'pixels'), \
             patch.object(splash.os, 'open', side_effect=[10, 11]), \
             patch.object(splash.os, 'close'), \
             patch.object(splash.os, 'fstat', return_value=SimpleNamespace(st_mode=stat.S_IFCHR)), \
             patch.object(splash.fcntl, 'ioctl'), \
             patch.object(splash.signal, 'signal'), \
             patch.object(splash, 'ready') as ready, \
             patch.object(splash, 'restore') as restore, \
             patch.object(splash.time, 'monotonic', side_effect=clocks or [0]):
            try:
                splash.show(self.fb)
            finally:
                restore.assert_called_once_with(self.fb)
            ready.assert_called_once()

    def test_handoff_reads_back_image_and_restores_only_tty1(self):
        self.run_show()
        self.fb.fb_mode.assert_called_once_with(11)
        self.fb.write_all_at.assert_called_once_with(11, b'pixels', 0)
        self.fb.read_exact_at.assert_called_once_with(11, splash.BYTES, 0)

    def test_write_failure_restores_console(self):
        self.fb.write_all_at.side_effect = OSError('write failed')
        with self.assertRaises(OSError):
            self.run_show()

    def test_bad_readback_restores_console(self):
        self.fb.read_exact_at.return_value = b'wrong'
        with self.assertRaisesRegex(ValueError, 'readback'):
            self.run_show()

    def test_missing_frontend_has_bounded_wait(self):
        self.run_show(tty=['tty1', 'tty1', 'tty1'], clocks=[0, 145])

    def test_live_frontend_is_never_touched(self):
        with patch.object(splash, 'active_tty', return_value='tty2'), \
             patch.object(splash, 'ready'), patch.object(splash.os, 'open') as opened:
            splash.show(self.fb)
            opened.assert_not_called()
        self.assertFalse(self.marker.exists())

    def test_stop_post_restores_receipt_and_rejects_foreign_boot(self):
        self.marker.write_text('old-boot')
        self.marker.chmod(0o600)
        with patch.object(splash.os, 'open', return_value=12) as opened, \
             patch.object(splash.os, 'close'), patch.object(splash.fcntl, 'ioctl') as ioctl:
            with self.assertRaisesRegex(ValueError, 'receipt'):
                splash.restore(self.fb)
            opened.assert_not_called()
            self.marker.write_text('current-boot')
            splash.restore(self.fb)
            self.assertEqual(opened.call_args.args[0], '/dev/tty1')
            self.assertEqual(ioctl.call_args_list, [call(12, splash.VT_SETMODE, splash.VT_AUTO),
                                                   call(12, self.fb.KDSETMODE, self.fb.KD_TEXT)])
        self.assertFalse(self.marker.exists())

    def test_vt_release_acknowledges_handoff_without_switching_back_to_text(self):
        with patch.object(splash.fcntl, 'ioctl') as ioctl:
            splash.vt_signal(10, splash.signal.SIGUSR1)
            splash.vt_signal(10, splash.signal.SIGUSR2)
        self.assertEqual(ioctl.call_args_list, [call(10, splash.VT_RELDISP, 1),
                                               call(10, splash.VT_RELDISP, 2)])

    def test_image_size_is_bounded_and_exact(self):
        for length in (splash.BYTES - 1, splash.BYTES, splash.BYTES + 1):
            self.asset.write_bytes(gzip.compress(b'\0' * length))
            if length == splash.BYTES:
                self.assertEqual(len(splash.picture()), length)
            else:
                with self.assertRaisesRegex(ValueError, 'size'):
                    splash.picture()


if __name__ == '__main__':
    unittest.main()
