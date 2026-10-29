#!/usr/bin/env python3
"""Fetch and verify the pinned Debian arm64 glibc sysroot for cross building."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import urllib.request

base = Path(__file__).resolve().parent
root = base/'toolchain/sysroot'
root.mkdir(parents=True, exist_ok=True)
(base/'downloads').mkdir(exist_ok=True)
for pkg in json.loads((base/'toolchain/sysroot-manifest.json').read_text()):
    dest = base/'downloads'/Path(pkg['Filename']).name
    if not dest.exists():
        urllib.request.urlretrieve('https://deb.debian.org/debian/'+pkg['Filename'], dest)
    assert hashlib.sha256(dest.read_bytes()).hexdigest() == pkg['SHA256'], dest
    subprocess.run(['dpkg-deb', '-x', str(dest), str(root)], check=True)
for p in root.rglob('*'):
    if p.is_symlink():
        target = os.readlink(p)
        if target.startswith('/'):
            p.unlink()
            p.symlink_to(os.path.relpath(root/target.lstrip('/'), p.parent))
print('Verified Debian arm64 sysroot:',root)
