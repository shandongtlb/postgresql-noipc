#!/usr/bin/python3
"""APT pre-install guard: stock PostgreSQL core must never reach dpkg."""
import re
import subprocess
import sys

for line in sys.stdin:
    path=line.rstrip('\n')
    if not path: continue
    def field(name):
        return subprocess.check_output(['dpkg-deb','-f',path,name],text=True).strip()
    package=field('Package')
    source=(field('Source') or package).split()[0]
    core=(re.fullmatch(r'postgresql-[0-9]+(?:\.[0-9]+)*',source)
          or source=='postgresql' or package in ('postgresql','postgresql-client'))
    if core and field('PostgreSQL-NoIPC')!='yes':
        print(f'NoIPC policy refuses stock PostgreSQL package: {package} ({path}).\n'
              'Restore the managed NoIPC source at the start of /etc/apt/sources.list, '
              'then run apt update and apt dist-upgrade.',file=sys.stderr)
        sys.exit(1)
