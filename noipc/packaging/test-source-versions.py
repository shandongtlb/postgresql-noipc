#!/usr/bin/env python3
"""Use real dpkg tools to check official source and binary-only revision handling."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from update import CORE,records

repo=Path(__file__).resolve().parents[2]
manifest=json.loads((repo/'noipc/packaging/manifest.json').read_text())
with tempfile.TemporaryDirectory(prefix='noipc-source-version-') as tmp:
    test=Path(tmp)/'repo';out=Path(tmp)/'source'
    subprocess.run(['git','clone','--quiet','--shared','--no-checkout',str(repo),str(test)],check=True)
    subprocess.run(['git','-C',str(test),'checkout','--quiet','--detach','HEAD'],check=True)
    for name in CORE:
        shutil.copy2(repo/name,test/name)
    for filename in ('prepare-debian-source.py',):
        shutil.copy2(repo/'noipc/packaging'/filename,test/'noipc/packaging'/filename)
    cache=test/'noipc/packaging/upstream';cache.mkdir(exist_ok=True)
    for filename in manifest['files']:
        shutil.copy2(repo/'noipc/packaging/upstream'/filename,cache/filename)
    manifest['binary_version']=manifest['debian_version']+'+b1'
    (test/'noipc/packaging/manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    subprocess.run(['python3',str(test/'noipc/packaging/prepare-debian-source.py'),str(out)],check=True)
    dsc=next(out.glob('*.dsc'))
    assert next(records(dsc.read_text()))['Version']==manifest['debian_version']
    source=out/('postgresql-'+manifest['upstream_version'])
    control=subprocess.check_output(['dpkg-gencontrol','-ppostgresql-18','-O'],cwd=source,text=True)
    fields=next(records(control))
    assert fields['Version']==manifest['binary_version'],control
    assert fields['Source']=='postgresql-18 ('+manifest['debian_version']+')',control
    assert fields['Postgresql-Noipc']=='yes',control
    print('PASS: the generated .dsc keeps the exact official source version')
    print('PASS: binary-only +bN builds keep the official binary version and original Source version')
