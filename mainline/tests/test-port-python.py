#!/usr/bin/env python3
"""Run with the packaged interpreter in isolated mode, without system stdlib."""
import bz2
import ctypes
import hashlib
import json
import lzma
from pathlib import Path
import sqlite3
import ssl
import sys
import urllib.request
import zipfile

prefix = Path(sys.executable).resolve().parent.parent
assert sys.flags.isolated and sys.dont_write_bytecode
assert Path(sys.prefix).resolve() == prefix, (sys.prefix, prefix)
for path in sys.path:
    assert Path(path).resolve().is_relative_to(prefix), path
for module in (bz2, ctypes, json, lzma, sqlite3, ssl, urllib.request, zipfile):
    assert Path(module.__file__).resolve().is_relative_to(prefix), module.__file__
sample = b'R46H private Python'
assert bz2.decompress(bz2.compress(sample)) == lzma.decompress(lzma.compress(sample)) == sample
assert len(hashlib.sha256(sample).digest()) == 32
assert ssl.create_default_context().verify_mode == ssl.CERT_REQUIRED
with sqlite3.connect(':memory:') as db:
    assert db.execute('select 46').fetchone() == (46,)
print('PORT_PRIVATE_PYTHON_PASS', sys.version.split()[0])
