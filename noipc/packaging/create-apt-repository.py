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
from versions import package_versions

base = Path(__file__).resolve().parents[1]
manifest = json.loads((base / 'packaging/manifest.json').read_text())
versions = package_versions(manifest)
parser = argparse.ArgumentParser()
parser.add_argument('--packages', type=Path, required=True)
parser.add_argument('--output', type=Path, default=base / 'repository')
parser.add_argument('--signing-home', type=Path, default=base / 'keys-private/apt')
parser.add_argument('--base-url', default='https://raw.githubusercontent.com/shandongtlb/postgresql-noipc/apt/')
parser.add_argument('--keyring-version', default=manifest['archive_keyring_version'])
parser.add_argument('--metapackage-version', default=manifest.get('metapackage_version', '18+293'))
args = parser.parse_args()
if args.metapackage_version != manifest['metapackage_version']:
    raise SystemExit('Official metapackage version must match the build manifest')
if args.keyring_version != manifest['archive_keyring_version']:
    raise SystemExit('Archive configuration version must match the build manifest')
repository = args.output.resolve()
keyhome = args.signing_home.resolve()
if keyhome == repository or keyhome.is_relative_to(repository):
    raise SystemExit('The private signing-key directory must be outside the public repository')
repository.mkdir(parents=True, exist_ok=True)
keyhome.mkdir(parents=True, mode=0o700, exist_ok=True)
keyhome.chmod(0o700)
gpg = ['gpg', '--homedir', str(keyhome), '--batch']
public_listing = subprocess.check_output(
    ['gpg', '--batch', '--with-colons', '--show-keys',
     str(base / 'packaging/postgresql-noipc-archive-keyring.asc')], text=True)
fingerprint = next(line.split(':')[9] for line in public_listing.splitlines() if line.startswith('fpr:'))
listed = subprocess.check_output(gpg + ['--with-colons', '--list-secret-keys', fingerprint], text=True)
if not any(line.startswith('sec:') for line in listed.splitlines()):
    raise SystemExit('Restore the existing archive private key; automatic key replacement is forbidden')
public_key = subprocess.check_output(gpg + ['--export', fingerprint])
public_ascii = subprocess.check_output(gpg + ['--armor', '--export', fingerprint])
(repository / 'postgresql-noipc-archive-keyring.gpg').write_bytes(public_key)
(repository / 'postgresql-noipc-archive-keyring.asc').write_bytes(public_ascii)
(repository / 'SIGNING-KEY-FINGERPRINT').write_text(fingerprint + '\n')

def install_immutable(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if hashlib.sha256(source.read_bytes()).digest() != hashlib.sha256(target.read_bytes()).digest():
            raise SystemExit(f'Existing content-addressed file changed: {target.name}')
    else:
        shutil.copy2(source, target)

cohort = hashlib.sha256(''.join(
    p.name + ':' + hashlib.sha256(p.read_bytes()).hexdigest()
    for p in sorted(args.packages.resolve().iterdir())
    if p.is_file() and p.name.endswith(('.deb', '.dsc'))).encode()).hexdigest()[:20]
pool = repository / 'pool/main/p/postgresql-18' / cohort
pool.mkdir(parents=True, exist_ok=True)
packages = sorted(args.packages.resolve().glob('*.deb'))
if not packages:
    raise SystemExit('No .deb files found')
provided = set()
for package in packages:
    def field(name):
        return subprocess.check_output(['dpkg-deb', '-f', str(package), name], text=True).strip()
    if field('PostgreSQL-NoIPC') != 'yes' or field('Version') != versions['binary'] or field('Architecture') not in ('arm64', 'all'):
        raise SystemExit(f'Unexpected package version or architecture: {package.name}')
    if f'postgresql-noipc-archive-keyring (>= {args.keyring_version})' not in field('Depends'):
        raise SystemExit(f'Missing current archive dependency: {package.name}')
    provided.add(field('Package'))
if not {'postgresql-18', 'postgresql-client-18'} <= provided:
    raise SystemExit('Both the NoIPC server and client packages are required')
if not list(args.packages.resolve().glob('*.dsc')):
    raise SystemExit('The clean modified .dsc source package is required')
active_pool_files = set()
for source in sorted(args.packages.resolve().iterdir()):
    if source.name.endswith(('.deb', '.dsc', '.debian.tar.xz', '.debian.tar.gz',
                             '.orig.tar.bz2', '.orig.tar.gz', '.orig.tar.xz')):
        target = pool / source.name
        install_immutable(source, target)
        active_pool_files.add(target)

version = versions['binary']
# Exact binary names give the signed rebuild precedence over the fallback deny.
# Source matching below covers future upstream majors without blocking extensions
# or the separate postgresql-common service-management source package.
pin_names = ' '.join(name + ':any' for name in sorted(provided | {
    'postgresql', 'postgresql-client', 'postgresql-noipc',
    'postgresql-noipc-archive-keyring'}))

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

def auxiliary_deb(name, package_version, description, depends, payload, maintscripts=None):
    with tempfile.TemporaryDirectory(prefix='noipc-deb-') as tmp:
        stage = Path(tmp) / name
        (stage / 'DEBIAN').mkdir(parents=True)
        control = (f'Package: {name}\nVersion: {package_version}\nArchitecture: all\n'
                   'Maintainer: SDTLB <40312509+shandongtlb@users.noreply.github.com>\n'
                   'Section: database\nPriority: optional\n'
                   f'Depends: {depends}\nHomepage: https://github.com/shandongtlb/postgresql-noipc\n'
                   f'PostgreSQL-NoIPC: yes\nDescription: {description}\n')
        (stage / 'DEBIAN/control').write_text(control)
        for script, body in (maintscripts or {}).items():
            dest = stage / 'DEBIAN' / script
            dest.write_text(body)
            dest.chmod(0o755)
        conffiles = []
        for filename, data in payload.items():
            p = stage / filename
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(data if isinstance(data, bytes) else data.encode())
            if filename.startswith(('usr/lib/postgresql-noipc/', 'usr/sbin/')):
                p.chmod(0o755)
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
        target = repository / 'pool/main/p' / name / hashlib.sha256(dest.read_bytes()).hexdigest()[:20] / dest.name
        install_immutable(dest, target)
        active_pool_files.add(target)
        return target

source_manager = (base / 'packaging/configure-source.py').read_text()
legacy = ('dpkg-maintscript-helper rm_conffile /etc/apt/sources.list.d/postgresql-noipc.sources '
          '2026.10.29.3~ -- "$@"\n')
import shlex
bootstrap_scripts = {
    'preinst': '#!/bin/sh\nset -e\n' + legacy,
    'postinst': '#!/bin/sh\nset -e\n' + legacy +
                '[ "$1" != configure ] || /usr/lib/postgresql-noipc/configure-source\n',
    'postrm': '#!/bin/sh\nset -e\n' + legacy +
              'case "$1" in remove|purge) /usr/bin/python3 -c ' + shlex.quote(source_manager) + ' --remove ;; esac\n'}
bootstrap = auxiliary_deb(
    'postgresql-noipc-archive-keyring', args.keyring_version,
    'signing key, guarded APT source and policy for PostgreSQL NoIPC', 'ca-certificates, python3',
    {'usr/share/keyrings/postgresql-noipc-archive-keyring.gpg': public_key,
     'usr/share/postgresql-noipc/archive-url': args.base_url.rstrip('/') + '/\n',
     'usr/lib/postgresql-noipc/configure-source': source_manager,
     'usr/lib/postgresql-noipc/verify-packages': (base / 'packaging/verify-packages.py').read_bytes(),
     'usr/sbin/postgresql-noipc-upgrade': (base / 'packaging/upgrade-phone.py').read_bytes(),
     'etc/apt/apt.conf.d/99-postgresql-noipc':
         'DPkg::Pre-Install-Pkgs {"/usr/lib/postgresql-noipc/verify-packages";};\n'
         'DPkg::Tools::Options::/usr/lib/postgresql-noipc/verify-packages::Version "1";\n',
     'etc/apt/preferences.d/postgresql-noipc': pin}, bootstrap_scripts)
auxiliary_deb('postgresql', versions['meta'],
              'PostgreSQL database server with the NoIPC kernel compatibility patch',
              f'postgresql-18 (>= {version}), '
              f'postgresql-noipc-archive-keyring (>= {args.keyring_version})',
              {})
auxiliary_deb('postgresql-client', versions['meta'],
              'front-end programs for the PostgreSQL NoIPC rebuild',
              f'postgresql-client-18 (>= {version}), '
              f'postgresql-noipc-archive-keyring (>= {args.keyring_version})',
              {})
# Keep the compatibility alias pointing at the same standard packages.
auxiliary_deb('postgresql-noipc', version,
              'PostgreSQL 18 rebuilt for Linux kernels without SysV IPC',
              f'postgresql-18 (>= {version}), postgresql-client-18 (>= {version}), '
              f'postgresql-noipc-archive-keyring (>= {args.keyring_version})',
              {})
shutil.copy2(bootstrap, repository / 'postgresql-noipc-archive-keyring_all.deb')
# Keep only this release; every package revision has a content-addressed path.
for path in sorted((repository / 'pool').rglob('*'), reverse=True):
    if path.is_file() and path not in active_pool_files:
        path.unlink()
    elif path.is_dir() and not any(path.iterdir()):
        path.rmdir()

component = repository / 'dists/stable/main'
indices = []
active_hashes = set()
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
            active_hashes.add(by_hash)
for path in component.rglob('by-hash/*/*'):
    if path.is_file() and path not in active_hashes:
        path.unlink()

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
Only the current release is retained. This branch is published as a single Git
snapshot; the source branch retains upstream history. PostgreSQL keeps the official
upstream version and standard package names. Debian package versions add +noipcN;
each rebuild advances N so ordinary apt update && apt dist-upgrade installs updates.

Inside the phone's Kali chroot, as root:

```sh
curl -fLO {args.base_url.rstrip('/')}/postgresql-noipc-archive-keyring_all.deb
apt install ./postgresql-noipc-archive-keyring_all.deb
apt update
apt dist-upgrade
apt install postgresql postgresql-client
systemctl enable --now postgresql
systemctl status postgresql@18-main --no-pager
pg_lsclusters
```

The standard `postgresql` and `postgresql-client` metapackages select the NoIPC 18 packages.
`postgresql-18` and all versioned binary package names also match the distribution names.
`postgresql-noipc` remains available as a compatibility alias; it uses the same server package.
Debian package revisions are newer than the corresponding Kali packages. The managed first source and pre-install marker guard
ensure unmarked stock packages cannot replace this build. Other stock core versions are
pinned to -1. Use `apt update && apt dist-upgrade` for stock-package migration and all updates. Shared `postgresql-common` infrastructure and
independently packaged extensions remain available from Kali. Existing clusters are not deleted.
To update an installation bootstrapped with version 2026.10.29.1, run
`apt update && apt dist-upgrade`. Historical +noipc trial versions also migrate this way;
when using -y for that one-time downgrade, add --allow-downgrades.
Official `postgresql-common` provides cluster management, systemd/SysV service files, logging,
and upgrade scripts. The target NetHunter chroot runs systemd, so enabling the service starts
the database whenever that chroot's systemd boots. Other chroots without init can use `service`.

Archive signing fingerprint: `{fingerprint}`.
Installation, scheduled updates and maintenance: https://github.com/shandongtlb/postgresql-noipc/blob/main/noipc/packaging/MAINTENANCE.zh-CN.md
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
