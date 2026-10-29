#!/usr/bin/env python3
"""Audit actual Debian package payloads and metadata without running them."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument('packages', type=Path)
args = parser.parse_args()
report = []
for deb in sorted(args.packages.glob('*.deb')):
    def field(name):
        return subprocess.check_output(['dpkg-deb', '-f', str(deb), name], text=True).strip()
    architecture = field('Architecture')
    assert architecture in ('arm64', 'all'), (deb, architecture)
    package = {'package': field('Package'), 'version': field('Version'),
               'architecture': architecture, 'depends': field('Depends'), 'elf': []}
    assert '+noipc' in package['version'], package
    with tempfile.TemporaryDirectory(prefix='noipc-deb-audit-') as temp:
        root = Path(temp)
        subprocess.run(['dpkg-deb', '-R', str(deb), str(root)], check=True)
        if package['package'] == 'postgresql-18':
            maintscript = (root / 'DEBIAN/postinst').read_text()
            assert '/usr/share/postgresql-common/maintscripts-functions' in maintscript
            assert 'configure_version' in maintscript
        for p in sorted(root.rglob('*')):
            if p.is_symlink() or not p.is_file():
                continue
            with p.open('rb') as f:
                if f.read(4) != b'\x7fELF':
                    continue
            def readelf(option):
                return subprocess.check_output(['readelf', option, str(p)], text=True,
                                               stderr=subprocess.DEVNULL)
            assert 'AArch64' in readelf('-h'), p
            symbols = readelf('-Ws')
            forbidden = [line for line in symbols.splitlines() if ' UND ' in line and
                         re.search(r'\b(shmget|shmat|shmdt|shmctl|semget|semop|semctl|semtimedop|msgget|msgsnd|msgrcv|msgctl)\b', line)]
            assert not forbidden, (p, forbidden)
            versions = sorted(set(re.findall(r'GLIBC_(\d+\.\d+)', readelf('-V'))),
                              key=lambda x: tuple(map(int, x.split('.'))))
            needed = re.findall(r'\(NEEDED\).*\[(.*?)\]', readelf('-d'))
            package['elf'].append({'path': str(p.relative_to(root)),
                                   'max_glibc': versions[-1] if versions else None,
                                   'needed': needed})
    report.append(package)
assert any(x['package'] == 'postgresql-18' for x in report), 'server package is missing'
assert any(x['package'] == 'postgresql-client-18' for x in report), 'client package is missing'
print(json.dumps(report, indent=2))
