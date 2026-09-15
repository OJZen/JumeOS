#!/usr/bin/env python3
"""Validate and install the pinned private Mesa runtime."""

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tarfile


LOCK = Path(__file__).with_name("source-lock.json")


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def normalized(name):
    while name.startswith("./"):
        name = name[2:]
    path = PurePosixPath(name.rstrip("/"))
    if not name or str(path) in {"", "."}:
        return ""
    if path.is_absolute() or ".." in path.parts or str(path) != name.rstrip("/"):
        raise ValueError("unsafe runtime member: " + name)
    return str(path)


def load_runtime():
    record = json.loads(LOCK.read_text(encoding="utf-8"))
    if record.get("schema") != 1:
        raise ValueError("unsupported Mesa lock schema")
    runtime = record["runtime"]
    files, links = runtime["files"], runtime["links"]
    if set(files) & set(links):
        raise ValueError("duplicate Mesa runtime path")
    for name in (*files, *links):
        if normalized(name) != name:
            raise ValueError("invalid Mesa runtime path: " + name)
    return record, runtime


def expected_directories(files, links):
    result = set()
    for name in (*files, *links):
        parent = PurePosixPath(name).parent
        while str(parent) != ".":
            result.add(str(parent))
            parent = parent.parent
    return result


def validate_archive(path):
    record, runtime = load_runtime()
    if not path.is_file() or path.is_symlink() or path.stat().st_size != runtime["bytes"] or digest(path) != runtime["sha256"]:
        raise ValueError("Mesa runtime archive identity mismatch")
    files, links = runtime["files"], runtime["links"]
    directories = expected_directories(files, links)
    seen = set()
    with tarfile.open(path, "r:gz") as archive:
        for member in archive:
            name = normalized(member.name)
            if not name:
                continue
            if name in seen:
                raise ValueError("duplicate Mesa runtime member: " + name)
            seen.add(name)
            if member.uid != 0 or member.gid != 0 or member.mtime != 0:
                raise ValueError("unsealed Mesa runtime member: " + name)
            if name in directories:
                if not member.isdir() or stat.S_IMODE(member.mode) != 0o755:
                    raise ValueError("invalid Mesa runtime directory: " + name)
            elif name in links:
                if not member.issym() or member.linkname != links[name]:
                    raise ValueError("invalid Mesa runtime link: " + name)
            elif name in files:
                expected = files[name]
                if not member.isfile() or member.size != expected["bytes"] or stat.S_IMODE(member.mode) != expected["mode"]:
                    raise ValueError("invalid Mesa runtime file: " + name)
                stream = archive.extractfile(member)
                if stream is None or hashlib.sha256(stream.read()).hexdigest() != expected["sha256"]:
                    raise ValueError("Mesa runtime file hash mismatch: " + name)
            else:
                raise ValueError("unexpected Mesa runtime member: " + name)
    expected = directories | set(files) | set(links)
    if seen != expected:
        raise ValueError("Mesa runtime member set mismatch")
    return record, runtime


def install(archive_path, destination):
    _record, runtime = validate_archive(archive_path)
    if not destination.is_dir() or destination.is_symlink():
        raise ValueError("Mesa destination must be an existing directory")
    paths = [destination / name for name in (*runtime["files"], *runtime["links"])]
    if any(path.exists() or path.is_symlink() for path in paths):
        raise ValueError("Mesa runtime would replace an existing file")
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
    with tarfile.open(archive_path, "r:gz") as archive:
        members = {}
        for member in archive:
            name = normalized(member.name)
            if name:
                members[name] = member
        for name, expected in runtime["files"].items():
            stream = archive.extractfile(members[name])
            if stream is None:
                raise ValueError("Mesa runtime file disappeared: " + name)
            target = destination / name
            with target.open("xb") as output:
                shutil.copyfileobj(stream, output)
            target.chmod(expected["mode"])
        for name, target in runtime["links"].items():
            os.symlink(target, destination / name)


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate-runtime")
    validate.add_argument("archive", type=Path)
    installer = commands.add_parser("install")
    installer.add_argument("archive", type=Path)
    installer.add_argument("destination", type=Path)
    args = parser.parse_args()
    record, _runtime = load_runtime()
    if args.command == "validate-runtime":
        validate_archive(args.archive)
    else:
        install(args.archive, args.destination)
    print(json.dumps({"status": "MESA_RUNTIME_PASS", "version": record["mesa"]["version"], "operation": args.command}))


if __name__ == "__main__":
    main()
