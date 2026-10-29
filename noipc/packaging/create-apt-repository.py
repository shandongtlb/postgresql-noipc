#!/usr/bin/env python3
"""Create a signed, static arm64 APT archive, including its bootstrap package."""
import argparse
from datetime import datetime, timezone
import email.utils
import gzip
import hashlib
import json
import lzma
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

base = Path(__file__).resolve().parents[1]
manifest = json.loads((base / 'packaging/manifest.json').read_text())
parser = argparse.ArgumentParser()
parser.add_argument('--packages', type=Path, required=True)
parser.add_argument('--output', type=Path, default=base / 'repository')
parser.add_argument('--signing-home', type=Path, default=base / 'keys-private/apt')
parser.add_argument('--base-url', default='https://raw.githubusercontent.com/shandongtlb/postgresql-noipc/apt/')
parser.add_argument('--keyring-version', default='2026.10.29.2')
parser.add_argument('--metapackage-version', default='18+noipc1')
args = parser.parse_args()
repository = args.output.resolve()
keyhome = args.signing_home.resolve()
if keyhome == repository or keyhome.is_relative_to(repository):
    raise SystemExit('The private signing-key directory must be outside the public repository')
repository.mkdir(parents=True, exist_ok=True)
keyhome.mkdir(parents=True, mode=0o700, exist_ok=True)
keyhome.chmod(0o700)
gpg = ['gpg', '--homedir', str(keyhome), '--batch']
listed = subprocess.check_output(gpg + ['--with-colons', '--list-secret-keys'], text=True)
if not any(line.startswith('sec:') for line in listed.splitlines()):
    subprocess.run(gpg + ['--passphrase', '', '--quick-generate-key',
                         'PostgreSQL NoIPC APT <40312509+shandongtlb@users.noreply.github.com>',
                         'ed25519', 'sign', '2y'], check=True)
    listed = subprocess.check_output(gpg + ['--with-colons', '--list-secret-keys'], text=True)
fingerprint = next(line.split(':')[9] for line in listed.splitlines() if line.startswith('fpr:'))
public_key = subprocess.check_output(gpg + ['--export', fingerprint])
public_ascii = subprocess.check_output(gpg + ['--armor', '--export', fingerprint])
(repository / 'postgresql-noipc-archive-keyring.gpg').write_bytes(public_key)
(repository / 'postgresql-noipc-archive-keyring.asc').write_bytes(public_ascii)
(repository / 'SIGNING-KEY-FINGERPRINT').write_text(fingerprint + '\n')

def install_immutable(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if hashlib.sha256(source.read_bytes()).digest() != hashlib.sha256(target.read_bytes()).digest():
            raise SystemExit(f'Existing package changed without a version bump: {target.name}')
    else:
        shutil.copy2(source, target)

pool = repository / 'pool/main/p/postgresql-18'
pool.mkdir(parents=True, exist_ok=True)
packages = sorted(args.packages.resolve().glob('*.deb'))
if not packages:
    raise SystemExit('No .deb files found')
provided = set()
for package in packages:
    def field(name):
        return subprocess.check_output(['dpkg-deb', '-f', str(package), name], text=True).strip()
    if field('Version') != manifest['noipc_version'] or field('Architecture') not in ('arm64', 'all'):
        raise SystemExit(f'Unexpected package version or architecture: {package.name}')
    provided.add(field('Package'))
if not {'postgresql-18', 'postgresql-client-18'} <= provided:
    raise SystemExit('Both the NoIPC server and client packages are required')
if not list(args.packages.resolve().glob('*.dsc')):
    raise SystemExit('The clean modified .dsc source package is required')
for source in sorted(args.packages.resolve().iterdir()):
    if source.name.endswith(('.deb', '.dsc', '.debian.tar.xz', '.orig.tar.bz2')):
        install_immutable(source, pool / source.name)

version = manifest['noipc_version']
# Exact binary names give the signed rebuild precedence over the fallback deny.
# Source matching below covers future upstream majors without blocking extensions
# or the separate postgresql-common service-management source package.
pin_names = ' '.join(name + ':any' for name in sorted(provided | {
    'postgresql', 'postgresql-client', 'postgresql-noipc',
    'postgresql-noipc-archive-keyring'}))
source_config = (f'Types: deb deb-src\nURIs: {args.base_url.rstrip("/")}/\n'
                 'Suites: stable\nComponents: main\nArchitectures: arm64\n'
                 'Signed-By: /usr/share/keyrings/postgresql-noipc-archive-keyring.gpg\n')
pin = ('Explanation: Prefer the signed NoIPC rebuild, using official binary package names.\n'
       f'Package: {pin_names}\nPin: release o=PostgreSQL-NoIPC\nPin-Priority: 1001\n\n'
       'Explanation: Reject stock PostgreSQL core packages, including future major versions.\n'
       'Explanation: Keep postgresql-common and independently packaged extensions available.\n'
       'Package: src:/^postgresql-[0-9]+([.][0-9]+)*$/:any src:postgresql:any postgresql:any postgresql-client:any\n'
       'Pin: version *\nPin-Priority: -1\n')
# Fixed timestamps make bootstrap/meta packages reproducible across index rebuilds.
epoch = int(datetime.strptime(args.keyring_version.rsplit('.', 1)[0], '%Y.%m.%d').replace(tzinfo=timezone.utc).timestamp())
env = dict(os.environ, SOURCE_DATE_EPOCH=str(epoch))
date = email.utils.format_datetime(datetime.fromtimestamp(epoch, timezone.utc))

def auxiliary_deb(name, package_version, description, depends, payload):
    with tempfile.TemporaryDirectory(prefix='noipc-deb-') as tmp:
        stage = Path(tmp) / name
        (stage / 'DEBIAN').mkdir(parents=True)
        control = (f'Package: {name}\nVersion: {package_version}\nArchitecture: all\n'
                   'Maintainer: SDTLB <40312509+shandongtlb@users.noreply.github.com>\n'
                   'Section: database\nPriority: optional\n'
                   f'Depends: {depends}\nHomepage: https://github.com/shandongtlb/postgresql-noipc\n'
                   f'Description: {description}\n')
        (stage / 'DEBIAN/control').write_text(control)
        conffiles = []
        for filename, data in payload.items():
            p = stage / filename
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data if isinstance(data, bytes) else data.encode())
            if filename.startswith('etc/'):
                conffiles.append('/' + filename)
        if conffiles:
            (stage / 'DEBIAN/conffiles').write_text('\n'.join(conffiles) + '\n')
        docs = stage / 'usr/share/doc' / name
        docs.mkdir(parents=True, exist_ok=True)
        shutil.copy2(base.parent / 'COPYRIGHT', docs / 'copyright')
        changelog = (f'{name} ({package_version}) stable; urgency=medium\n\n'
                     '  * Publish the signed PostgreSQL NoIPC archive.\n\n'
                     f' -- SDTLB <40312509+shandongtlb@users.noreply.github.com>  {date}\n')
        (docs / 'changelog.Debian.gz').write_bytes(gzip.compress(changelog.encode(), mtime=0))
        dest = Path(tmp) / f'{name}_{package_version}_all.deb'
        subprocess.run(['dpkg-deb', '--root-owner-group', '-Zxz', '--build', str(stage), str(dest)],
                       env=env, check=True)
        target = repository / 'pool/main/p' / name / dest.name
        install_immutable(dest, target)
        return target

bootstrap = auxiliary_deb(
    'postgresql-noipc-archive-keyring', args.keyring_version,
    'signing key and APT source for the PostgreSQL NoIPC rebuild', 'ca-certificates',
    {'usr/share/keyrings/postgresql-noipc-archive-keyring.gpg': public_key,
     'etc/apt/sources.list.d/postgresql-noipc.sources': source_config,
     'etc/apt/preferences.d/postgresql-noipc': pin})
auxiliary_deb('postgresql', args.metapackage_version,
              'PostgreSQL database server with the NoIPC kernel compatibility patch',
              f'postgresql-18 (>= {version}), '
              f'postgresql-noipc-archive-keyring (>= {args.keyring_version})', {})
auxiliary_deb('postgresql-client', args.metapackage_version,
              'front-end programs for the PostgreSQL NoIPC rebuild',
              f'postgresql-client-18 (>= {version}), '
              f'postgresql-noipc-archive-keyring (>= {args.keyring_version})', {})
# Retain the already published alias byte-for-byte for existing installations.
auxiliary_deb('postgresql-noipc', version,
              'PostgreSQL 18 rebuilt for Linux kernels without SysV IPC',
              f'postgresql-18 (>= {version}), postgresql-client-18 (>= {version})', {})
shutil.copy2(bootstrap, repository / 'postgresql-noipc-archive-keyring_all.deb')

component = repository / 'dists/stable/main'
indices = []
for kind, relative in [('packages', 'binary-arm64/Packages'), ('sources', 'source/Sources')]:
    content = subprocess.check_output(['apt-ftparchive', kind, 'pool'], cwd=repository)
    path = component / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    for file, data in [(path, content), (Path(str(path)+'.gz'), gzip.compress(content, mtime=0)),
                       (Path(str(path)+'.xz'), lzma.compress(content))]:
        file.write_bytes(data)
        indices.append(file)
        for algorithm in ['SHA256', 'SHA512']:
            digest = hashlib.new(algorithm.lower(), data).hexdigest()
            by_hash = file.parent / 'by-hash' / algorithm / digest
            by_hash.parent.mkdir(parents=True, exist_ok=True)
            if not by_hash.exists():
                by_hash.write_bytes(data)

release_dir = repository / 'dists/stable'
now = email.utils.format_datetime(datetime.now(timezone.utc))
release = ('Origin: PostgreSQL-NoIPC\nLabel: PostgreSQL NoIPC\nSuite: stable\nCodename: noipc\n'
           f'Date: {now}\nArchitectures: arm64\nComponents: main\nAcquire-By-Hash: yes\n'
           'Description: PostgreSQL 18 NoIPC rebuilds for Kali arm64\n')
for label, algorithm in [('MD5Sum', 'md5'), ('SHA256', 'sha256'), ('SHA512', 'sha512')]:
    release += label + ':\n'
    for index in sorted(indices):
        data = index.read_bytes()
        release += f' {hashlib.new(algorithm, data).hexdigest()} {len(data):16d} {index.relative_to(release_dir)}\n'
(release_dir / 'Release').write_text(release)
for mode, output in [('--clearsign', 'InRelease'), ('--detach-sign', 'Release.gpg')]:
    subprocess.run(gpg + ['--yes', '--armor', '--local-user', fingerprint, '--digest-algo', 'SHA256',
                         '--output', str(release_dir / output), mode, str(release_dir / 'Release')], check=True)

readme = f'''# PostgreSQL NoIPC APT archive

Packages are rebuilt from Debian/Kali postgresql-18 {manifest['debian_version']} with the NoIPC patch.
This branch is a signed static APT archive for **Kali rolling arm64**.

Inside the phone's Kali chroot, as root:

```sh
curl -fLO {args.base_url.rstrip('/')}/postgresql-noipc-archive-keyring_all.deb
apt install ./postgresql-noipc-archive-keyring_all.deb
apt update
apt install postgresql postgresql-client
systemctl enable --now postgresql
systemctl status postgresql@18-main --no-pager
pg_lsclusters
```

The standard `postgresql` and `postgresql-client` metapackages select the NoIPC 18 packages.
`postgresql-18` and all versioned binary package names also match the distribution names.
`postgresql-noipc` remains available as a compatibility alias; it uses the same server package.
The archive preference gives NoIPC packages priority 1001 and stock PostgreSQL core packages
priority -1, including future major versions. Shared `postgresql-common` infrastructure and
independently packaged extensions remain available from Kali. Existing clusters are not deleted.
To update an installation bootstrapped with version 2026.10.29.1, run
`apt update && apt install postgresql-noipc-archive-keyring && apt install postgresql postgresql-client`.
Official `postgresql-common` provides cluster management, systemd/SysV service files, logging,
and upgrade scripts. The target NetHunter chroot runs systemd, so enabling the service starts
the database whenever that chroot's systemd boots. Other chroots without init can use `service`.

Archive signing fingerprint: `{fingerprint}`.
Source and build scripts: https://github.com/shandongtlb/postgresql-noipc/tree/main/noipc/packaging
'''
(repository / 'README.md').write_text(readme)
checks = []
for p in sorted(repository.rglob('*')):
    if p.is_file() and '.git' not in p.relative_to(repository).parts and p.name != 'SHA256SUMS':
        checks.append(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + str(p.relative_to(repository)))
(repository / 'SHA256SUMS').write_text('\n'.join(checks) + '\n')
print('APT archive:', repository)
print('Public signing fingerprint:', fingerprint)
print('Signing key remains local:', keyhome)
