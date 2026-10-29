#!/usr/bin/env python3
"""Use real dpkg tools to check official source and binary-only revision handling."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from update import CORE,records
from versions import package_versions

repo=Path(__file__).resolve().parents[2]
manifest=json.loads((repo/'noipc/packaging/manifest.json').read_text())
with tempfile.TemporaryDirectory(prefix='noipc-source-version-') as tmp:
    test=Path(tmp)/'repo';out=Path(tmp)/'source'
    subprocess.run(['git','clone','--quiet','--shared','--no-checkout',str(repo),str(test)],check=True)
    subprocess.run(['git','-C',str(test),'checkout','--quiet','--detach','HEAD'],check=True)
    for name in CORE:
        shutil.copy2(repo/name,test/name)
    for filename in ('prepare-debian-source.py','versions.py'):
        shutil.copy2(repo/'noipc/packaging'/filename,test/'noipc/packaging'/filename)
    cache=test/'noipc/packaging/upstream';cache.mkdir(exist_ok=True)
    for filename in manifest['files']:
        shutil.copy2(repo/'noipc/packaging/upstream'/filename,cache/filename)
    manifest['binary_version']=manifest['debian_version']+'+b1'
    versions=package_versions(manifest)
    (test/'noipc/packaging/manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    subprocess.run(['python3',str(test/'noipc/packaging/prepare-debian-source.py'),str(out)],check=True)
    dsc=next(out.glob('*.dsc'))
    assert next(records(dsc.read_text()))['Version']==versions['source']
    source=out/('postgresql-'+manifest['upstream_version'])
    control=subprocess.check_output(['dpkg-gencontrol','-ppostgresql-18','-O'],cwd=source,text=True)
    fields=next(records(control))
    assert fields['Version']==versions['binary'],control
    assert fields['Source']=='postgresql-18 ('+versions['source']+')',control
    assert fields['Postgresql-Noipc']=='yes',control
    assert f"postgresql-noipc-archive-keyring (>= {manifest['archive_keyring_version']})" in fields['Depends'],control
    print('PASS: the generated .dsc uses the local +noipcN source revision')
    print('PASS: official binary-only +bN is retained after the local revision and references its correct Source version')
    print('PASS: real dpkg-gencontrol emits the build-specific archive dependency')

# Normal APT upgrades require the actual Debian ordering to advance for both
# binaries and metapackages, even when the official metapackage stays unchanged.
for label, official_source, official_binary in (
        ('another rebuild', manifest['debian_version'], manifest['binary_version']),
        ('a new upstream release', '18.999-1', '18.999-1')):
    later = dict(manifest, debian_version=official_source, binary_version=official_binary,
                 noipc_revision=manifest['noipc_revision'] + 1,
                 noipc_version=official_source + '+noipc' + str(manifest['noipc_revision'] + 1))
    following = package_versions(later)
    for kind in ('binary', 'meta'):
        subprocess.run(['dpkg', '--compare-versions', following[kind], 'gt', versions[kind]], check=True)
    print(f'PASS: {label} advances binary and metapackage versions under real dpkg ordering')
