#!/usr/bin/env python3
"""Check the real guard against marked core, stock core and independent packages."""
from pathlib import Path
import subprocess
import tempfile

base=Path(__file__).resolve().parent
with tempfile.TemporaryDirectory(prefix='noipc-guard-test-') as tmp:
    for name,source,marker,accepted in (
        ('postgresql-18','postgresql-18',False,False),
        ('postgresql-99','postgresql-99',False,False),
        ('postgresql','postgresql-common',False,False),
        ('libpq5','postgresql-18',False,False),
        ('postgresql-18','postgresql-18',True,True),
        ('postgresql-common','postgresql-common',False,True),
        ('postgresql-18-pgvector','postgresql-pgvector',False,True)):
        root=Path(tmp)/'package'
        (root/'DEBIAN').mkdir(parents=True,exist_ok=True)
        (root/'DEBIAN/control').write_text(f'Package: {name}\nSource: {source}\nVersion: 18.6-3\nArchitecture: arm64\nMaintainer: Test <test@example.invalid>\nDescription: guard fixture\n'+('PostgreSQL-NoIPC: yes\n' if marker else ''))
        deb=Path(tmp)/'test.deb'
        subprocess.run(['dpkg-deb','--build',str(root),str(deb)],check=True,stdout=subprocess.DEVNULL)
        result=subprocess.run(['python3',str(base/'verify-packages.py')],input=str(deb)+'\n',text=True,capture_output=True)
        assert (result.returncode==0)==accepted, result.stderr
        print(f'PASS: {name}, source={source}, marker={marker}: '+('accepted' if accepted else 'rejected'))
print('All 7 real package guard checks passed; no fixture package was installed.')
