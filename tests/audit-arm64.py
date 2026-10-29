#!/usr/bin/env python3
"""Check architecture, ABI version floor, dependency list and SysV IPC imports."""
from pathlib import Path
import json
import re
import subprocess
import sys

root = Path(sys.argv[1])
report = []
for p in sorted(root.rglob('*')):
    if not p.is_file() or p.is_symlink():
        continue
    with p.open('rb') as f:
        if f.read(4) != b'\x7fELF':
            continue
    def readelf(flag):
        return subprocess.check_output(['aarch64-linux-gnu-readelf', flag, str(p)], text=True)
    assert 'AArch64' in readelf('-h'), p
    syms = readelf('-Ws')
    bad = [line for line in syms.splitlines()
           if ' UND ' in line and re.search(r'\b(shmget|shmat|shmdt|shmctl|semget|semop|semctl|semtimedop)\b',line)]
    assert not bad, (p,bad)
    versions = sorted(set(re.findall(r'GLIBC_(\d+\.\d+)',readelf('-V'))),
                      key=lambda s:tuple(map(int,s.split('.'))))
    assert all(tuple(map(int,v.split('.'))) <= (2,36) for v in versions), (p,versions)
    libs = re.findall(r'\(NEEDED\).*\[(.*?)\]',readelf('-d'))
    assert set(libs) <= {'libc.so.6','libm.so.6','libpq.so.5','libpgtypes.so.3',
                         'libecpg.so.6','libecpg_compat.so.3','libpthread.so.0',
                         'libdl.so.2','librt.so.1','ld-linux-aarch64.so.1'}, (p,libs)
    report.append({'file':str(p.relative_to(root)), 'max_glibc': versions[-1] if versions else None, 'needed':libs})
assert report
print(json.dumps(report,indent=2))
