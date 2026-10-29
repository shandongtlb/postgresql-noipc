#!/usr/bin/env python3
"""Solve real archive packages with APT against isolated ARM64 installed states."""
import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from update import records

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('repository', type=Path)
parser.add_argument('--rootfs', type=Path, required=True,
                    help='marked Kali root providing real installed dependency metadata')
args = parser.parse_args()
rootfs = args.rootfs.resolve()
if not (rootfs / '.noipc-kali-rootfs').is_file():
    raise SystemExit('A marked Kali root is required; it will only be read')
repository = args.repository.resolve()
packages = list(records((repository / 'dists/stable/main/binary-arm64/Packages').read_text()))
keyring = next(p for p in packages if p['Package'] == 'postgresql-noipc-archive-keyring')
core = [p for p in packages if p['Package'] != keyring['Package']]
names = {p['Package'] for p in packages}
installed = list(records((rootfs / 'var/lib/dpkg/status').read_text()))

def stanza(fields):
    return '\n'.join(key + ': ' + value.replace('\n', '\n ') for key, value in fields.items()) + '\n\n'

def status_record(package):
    return {**{k: v for k, v in package.items() if k not in
               ('Filename', 'Size', 'SHA256', 'SHA512', 'MD5sum')}, 'Status': 'install ok installed'}

with tempfile.TemporaryDirectory(prefix='noipc-dist-upgrade-') as tmp:
    root = Path(tmp)
    root.chmod(0o755)
    for name in ('empty', 'lists/partial', 'cache/archives/partial', 'state', 'log'):
        (root / name).mkdir(parents=True, exist_ok=True)
    subprocess.run(['dpkg-deb', '-x', repository / 'postgresql-noipc-archive-keyring_all.deb',
                    root / 'bootstrap'], check=True)
    key = rootfs / 'usr/share/keyrings/kali-archive-keyring.gpg'
    (root / 'sources.list').write_text(
        f'deb [trusted=yes arch=arm64] {repository.as_uri()} stable main\n'
        f'deb [arch=arm64 signed-by={key}] https://http.kali.org/kali kali-rolling main\n')
    (root / 'apt.conf').write_text(f'''
Dir::Etc::main "{root}/absent";
Dir::Etc::parts "{root}/empty";
Dir::Etc::sourcelist "{root}/sources.list";
Dir::Etc::sourceparts "{root}/empty";
Dir::Etc::preferences "{root}/absent";
Dir::Etc::preferencesparts "{root}/bootstrap/etc/apt/preferences.d";
Dir::State "{root}/state";
Dir::State::status "{root}/status";
Dir::State::lists "{root}/lists";
Dir::Cache "{root}/cache";
Dir::Log "{root}/log";
APT::Architecture "arm64";
APT::Architectures {{ "arm64"; }};
APT::Sandbox::User "root";
''')
    env = dict(os.environ, APT_CONFIG=str(root / 'apt.conf'), LC_ALL='C')
    def apt(*argv):
        result = subprocess.run(list(argv), env=env, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        if result.returncode:
            raise RuntimeError(' '.join(argv) + '\n' + result.stdout)
        return result.stdout
    # Reuse trusted Kali lists where possible; apt verifies any refreshed lists.
    for p in (rootfs / 'var/lib/apt/lists').glob('*kali*'):
        if p.is_file():
            shutil.copy2(p, root / 'lists' / p.name)
    (root / 'status').touch()
    apt('apt-get', '-o', 'APT::Update::Error-Mode=any', 'update')
    baseline = ''.join(stanza(p) for p in installed if p['Package'] not in names)
    scenarios = ('stock-official-version', 'previous-build', 'keyring-already-upgraded',
                 'legacy-metapackage-layout', 'up-to-date')
    for scenario in scenarios:
        status = baseline
        old_versions = {}
        version_map = {}
        for package in core:
            version = package['Version']
            if scenario == 'stock-official-version':
                version = re.sub(r'\+noipc[0-9]+', '', version)
            elif scenario != 'up-to-date':
                version = re.sub(r'\+noipc([0-9]+)', lambda m: '+noipc'+str(int(m[1])-1), version)
            version_map[package['Version']] = version
        for package in core:
            p = status_record(package)
            p['Version'] = version_map[p['Version']]
            for current, old in version_map.items():
                p['Depends'] = p['Depends'].replace(current, old)
            if scenario == 'stock-official-version':
                p['Depends'] = ', '.join(d.strip() for d in p['Depends'].split(',')
                                         if not d.strip().startswith('postgresql-noipc-archive-keyring '))
                p.pop('Postgresql-Noipc', None)
                p.pop('PostgreSQL-NoIPC', None)
            elif scenario != 'up-to-date':
                p['Depends'] = p['Depends'].replace(keyring['Version'], '0')
            if scenario == 'legacy-metapackage-layout' and p['Package'] in ('postgresql','postgresql-client'):
                p['Version'] = '18+noipc1'
            old_versions[p['Package']] = p['Version']
            status += stanza(p)
        p = status_record(keyring)
        if scenario in ('stock-official-version', 'previous-build', 'legacy-metapackage-layout'):
            p['Version'] = '0'
        status += stanza(p)
        (root / 'status').write_text(status)
        for tool in ('apt', 'apt-get'):
            plan = apt(tool, '-s', 'dist-upgrade')
            selected = set(re.findall(r'^Inst ([^ :]+)', plan, re.M)) & names
            expected = set() if scenario == 'up-to-date' else {p['Package'] for p in core}
            if scenario in ('stock-official-version', 'previous-build', 'legacy-metapackage-layout'):
                expected.add(keyring['Package'])
            assert selected == expected, scenario + '\n' + plan
            assert not re.search(r'^Remv (?:' + '|'.join(map(re.escape, names)) + r')\b', plan, re.M), plan
            for package in core:
                if package['Package'] in selected:
                    assert re.search(r'^Inst ' + re.escape(package['Package']) + r' \[' +
                                     re.escape(old_versions[package['Package']]) + r'\] \(' +
                                     re.escape(package['Version']) + r' PostgreSQL NoIPC:', plan, re.M), plan
            print(f'PASS: {tool} dist-upgrade: {scenario}: {len(selected)} archive packages selected with standard package revisions')
print('All 10 real APT resolver checks passed; no fixture packages were installed.')
