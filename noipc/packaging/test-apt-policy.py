#!/usr/bin/env python3
"""Exercise the shipped pin policy with real APT and isolated future-version indices."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument('repository', type=Path)
args = parser.parse_args()
repository = args.repository.resolve()
index = (repository / 'dists/stable/main/binary-arm64/Packages').read_text()
def package_version(name):
    for paragraph in index.strip().split('\n\n'):
        fields = dict(line.split(': ',1) for line in paragraph.splitlines() if ': ' in line and not line.startswith(' '))
        if fields.get('Package') == name: return fields['Version']
    raise RuntimeError('Missing package: '+name)
core_version = package_version('postgresql-18')
meta_version = package_version('postgresql')
passed = 0
with tempfile.TemporaryDirectory(prefix='noipc-apt-policy-') as temp:
    root = Path(temp)
    root.chmod(0o755)
    subprocess.run(['dpkg-deb', '-x', str(repository / 'postgresql-noipc-archive-keyring_all.deb'),
                    str(root / 'bootstrap')], check=True)
    for name in ('empty', 'lists/partial', 'cache/archives/partial', 'state', 'log'):
        (root / name).mkdir(parents=True, exist_ok=True)
    (root / 'status').touch()
    custom, stock = root / 'noipc', root / 'stock'
    custom.mkdir()
    stock.mkdir()
    (custom / 'Packages').write_bytes((repository / 'dists/stable/main/binary-arm64/Packages').read_bytes())
    fixtures = [
        ('postgresql', '99+999', 'postgresql-common', 'all'),
        ('postgresql-client', '99+999', 'postgresql-common', 'all'),
        ('postgresql-18', core_version, 'postgresql-18', 'arm64'),
        ('postgresql-18', '18.9999-1', 'postgresql-18', 'arm64'),
        ('postgresql-99', '99.0-1', 'postgresql-99', 'arm64'),
        ('postgresql-9.6', '9.6.24-1', 'postgresql-9.6', 'arm64'),
        ('postgresql-client-99', '99.0-1', 'postgresql-99', 'arm64'),
        ('libpq5', '99.0-1', 'postgresql-99', 'arm64'),
        ('libpq5', '99.0-1', 'postgresql-99', 'amd64'),
        ('postgresql-common', '999', 'postgresql-common', 'all'),
        ('postgresql-client-common', '999', 'postgresql-common', 'all'),
        ('postgresql-18-pgvector', '0.99-1', 'postgresql-pgvector', 'arm64'),
        ('postgresql-18-special', '1-1', 'postgresql-18-special', 'arm64'),
    ]
    (stock / 'Packages').write_text(''.join(
        f'Package: {name}\nVersion: {version}\nSource: {source}\nArchitecture: {arch}\n'
        f'Maintainer: Test <test@example.invalid>\nFilename: pool/{name}_{version}_{arch}.deb\n'
        'Size: 1\nSHA256: ' + '0' * 64 + '\nDescription: isolated policy fixture\n\n'
        for name, version, source, arch in fixtures))
    for path, origin, suite in ((custom, 'PostgreSQL-NoIPC', 'noipc'), (stock, 'Kali', 'kali-rolling')):
        release = subprocess.check_output(['apt-ftparchive',
            '-o', f'APT::FTPArchive::Release::Origin={origin}',
            '-o', f'APT::FTPArchive::Release::Suite={suite}', 'release', '.'], cwd=path)
        (path / 'Release').write_bytes(release)
    sources = root / 'sources.list'
    def write_sources(include_noipc=True):
        sources.write_text((f'deb [trusted=yes] {custom.as_uri()} ./\n' if include_noipc else '')
                           + f'deb [trusted=yes] {stock.as_uri()} ./\n')
    write_sources()
    config = root / 'apt.conf'
    config.write_text(f'''
Dir::Etc::main "{root}/absent";
Dir::Etc::parts "{root}/empty";
Dir::Etc::sourcelist "{sources}";
Dir::Etc::sourceparts "{root}/empty";
Dir::Etc::preferences "{root}/absent";
Dir::Etc::preferencesparts "{root}/bootstrap/etc/apt/preferences.d";
Dir::State "{root}/state";
Dir::State::status "{root}/status";
Dir::State::lists "{root}/lists";
Dir::Cache "{root}/cache";
Dir::Log "{root}/log";
APT::Architecture "arm64";
APT::Architectures {{ "arm64"; "amd64"; }};
''')
    env = dict(os.environ, APT_CONFIG=str(config), LC_ALL='C')
    def apt(tool, *argv, check=True):
        return subprocess.run([tool, *argv], env=env, text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, check=check)
    apt('apt-get', '-o', 'APT::Update::Error-Mode=any', 'update')
    def verify(name, expected, *options):
        global passed
        policy = apt('apt-cache', *options, 'policy', name).stdout
        candidate = re.search(r'Candidate: (.+)', policy).group(1)
        assert candidate == expected, policy
        print(f'PASS: {name}: candidate {candidate}')
        passed += 1
        return policy
    for name in ('postgresql', 'postgresql-client'):
        policy = verify(name, meta_version)
        assert re.search(r'99\+999 -1\b', policy), policy
    for name in ('postgresql-18', 'libpq5'):
        policy = verify(name, core_version)
        assert '1001' in policy and re.search(r'(18\.9999-1|99\.0-1) -1\b', policy), policy
    for name in ('postgresql-99', 'postgresql-9.6', 'postgresql-client-99', 'libpq5:amd64'):
        verify(name, '(none)')
        failure = apt('apt-get', '-s', 'install', name, check=False)
        assert failure.returncode != 0 and 'no installation candidate' in failure.stdout, failure.stdout
    for name in ('postgresql-common', 'postgresql-client-common'):
        verify(name, '999')
    verify('postgresql-18-pgvector', '0.99-1')
    verify('postgresql-18-special', '1-1')
    verify('postgresql-18', core_version, '-o', 'APT::Default-Release=kali-rolling')
    chosen = apt('apt-get', '--print-uris', 'download', 'postgresql-18').stdout
    assert str(custom/'pool') in chosen, chosen
    print('PASS: an identical official version downloads from the first NoIPC source')
    passed += 1
    # Absence of the NoIPC archive must never select a stock core fallback.
    write_sources(include_noipc=False)
    apt('apt-get', '-o', 'APT::Update::Error-Mode=any', 'update')
    verify('postgresql-18', '(none)')
    verify('postgresql', '(none)')
    verify('postgresql-common', '999')
print(f'All {passed} isolated APT policy checks passed; fixture packages were never installed.')
