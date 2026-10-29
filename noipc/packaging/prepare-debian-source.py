#!/usr/bin/env python3
"""Prepare the genuine Debian package source with the NoIPC patch appended."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import urllib.request

base = Path(__file__).resolve().parents[1]
manifest = json.loads((base / 'packaging/manifest.json').read_text())
if manifest['noipc_version'] != manifest['debian_version']:
    raise SystemExit('PostgreSQL versions must exactly match the official Debian/Kali version')
parser = argparse.ArgumentParser()
parser.add_argument('output', type=Path, help='parent directory for unpacked source and orig tarball')
args = parser.parse_args()
functional_files = {
    'src/backend/port/sysv_shmem.c', 'src/backend/utils/init/miscinit.c',
    'src/backend/utils/misc/guc_tables.c', 'src/bin/initdb/initdb.c',
    'src/include/storage/dsm_impl.h', 'src/include/storage/pg_shmem.h',
}
# This recipe is pinned to a release. Refuse to silently omit later upstream
# changes when a maintainer pulls new commits but has not updated packaging.
changed = set(subprocess.check_output(
    ['git', 'diff', '--name-only', 'REL_' + manifest['upstream_version'].replace('.', '_'), '--', '.',
     ':(exclude)noipc/**', ':(exclude).github/README.md'],
    cwd=base.parent, text=True).splitlines())
if changed - functional_files:
    raise SystemExit('Update the pinned Debian packaging recipe for these source changes: '
                     + ', '.join(sorted(changed - functional_files)))
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=True)
cache = base / 'packaging/upstream'
cache.mkdir(exist_ok=True)
for name, expected in manifest['files'].items():
    archive = cache / name
    if not archive.exists():
        # Existing verified release-tar downloads can be reused by callers.
        urllib.request.urlretrieve(manifest['source_base_url'] + name, archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
        raise SystemExit(f'SHA256 mismatch: {archive}')
    shutil.copy2(archive, out / name)

source = out / f"postgresql-{manifest['upstream_version']}"
if source.exists():
    raise SystemExit(f'Refusing to overwrite existing source: {source}')
orig = next(name for name in manifest['files'] if '.orig.tar.' in name)
debian_tar = next(name for name in manifest['files'] if '.debian.tar.' in name)
subprocess.run(['tar', '-xf', str(out / orig),
                '-C', str(out)], check=True)
subprocess.run(['tar', '-xf', str(out / debian_tar),
                '-C', str(source)], check=True)
debian = source / 'debian'
patch = debian / 'patches/noipc-linux-mmap-directory-lock.patch'
patch.write_bytes(subprocess.check_output(
    ['git', 'diff', '--binary', 'REL_' + manifest['upstream_version'].replace('.', '_'),
     '--', *sorted(functional_files)], cwd=base.parent))
if not patch.stat().st_size:
    raise SystemExit('The NoIPC source delta is empty')
with (debian / 'patches/series').open('a') as f:
    f.write('\nnoipc-linux-mmap-directory-lock.patch\n')
subprocess.run(['dpkg-source', '--before-build', str(source)], check=True)

# A new Debian revision keeps the standard binary package names and lifecycle.
stamp = (datetime.fromtimestamp(int(os.environ['SOURCE_DATE_EPOCH']), timezone.utc)
         if 'SOURCE_DATE_EPOCH' in os.environ else datetime.now(timezone.utc))
now = stamp.strftime('%a, %d %b %Y %H:%M:%S +0000')
entry = (f"postgresql-18 ({manifest['noipc_version']}) kali-rolling; urgency=medium\n\n"
         '  * Rebuild with the NoIPC Linux mmap and inherited-directory-lock port.\n'
         '  * Keep Debian/Kali package layout, postgresql-common maintscripts,\n'
         '    systemd/SysV integration, and the official runtime feature set.\n\n'
         f' -- SDTLB <40312509+shandongtlb@users.noreply.github.com>  {now}\n\n')
changelog = debian / 'changelog'
changelog.write_text(entry + changelog.read_text())
control = debian / 'control'
text = control.read_text().replace(
    'Maintainer: Debian PostgreSQL Maintainers <team+postgresql@tracker.debian.org>',
    'Maintainer: SDTLB <40312509+shandongtlb@users.noreply.github.com>\n'
    'XSBC-Original-Maintainer: Debian PostgreSQL Maintainers <team+postgresql@tracker.debian.org>')
text = text.replace('Source: postgresql-18\n', 'Source: postgresql-18\nXB-PostgreSQL-NoIPC: yes\n', 1)
if 'XB-PostgreSQL-NoIPC: yes' not in text:
    raise SystemExit('Could not add the NoIPC binary marker to Debian control')
control.write_text(text)

for name in functional_files:
    if (source / name).read_bytes() != (base.parent / name).read_bytes():
        raise SystemExit(f'Debian-prepared source differs from this Git checkout: {name}')
(source / 'debian/noipc-build-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
# Create source artifacts while the tree is clean, before autoreconf/make add
# generated files. This is also the normal Debian source-before-binary order.
subprocess.run(['dpkg-source', '--build', source.name], cwd=out, check=True)
binary_version = manifest.get('binary_version', manifest['debian_version'])
if binary_version != manifest['debian_version']:
    import re
    if not re.fullmatch(re.escape(manifest['debian_version']) + r'\+b[0-9]+', binary_version):
        raise SystemExit('Unsupported official binary-only revision')
    binary_entry = (f"postgresql-18 ({binary_version}) kali-rolling; urgency=medium, binary-only=yes\n\n"
                    '  * Match the official Kali arm64 binary-only rebuild revision.\n\n'
                    f' -- SDTLB <40312509+shandongtlb@users.noreply.github.com>  {now}\n\n')
    changelog.write_text(binary_entry + changelog.read_text())
print(source)
