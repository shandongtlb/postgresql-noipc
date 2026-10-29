#!/usr/bin/python3
"""Keep the signed NoIPC source first when its versions equal the distribution."""
import argparse
import os
import stat
from pathlib import Path
import tempfile
from urllib.parse import urlsplit

parser=argparse.ArgumentParser()
parser.add_argument('--url', default=Path('/usr/share/postgresql-noipc/archive-url').read_text().strip()
                    if Path('/usr/share/postgresql-noipc/archive-url').exists() else '')
parser.add_argument('--remove', action='store_true')
args=parser.parse_args()
path=Path('/etc/apt/sources.list').resolve()
prior=path.stat() if path.exists() else None
begin='# BEGIN PostgreSQL NoIPC managed source'
end='# END PostgreSQL NoIPC managed source'
old=path.read_text() if path.exists() else ''
lines=[]
inside=False
for line in old.splitlines():
    if line==begin:
        if inside: raise SystemExit('Nested NoIPC source block')
        inside=True
    elif line==end:
        if not inside: raise SystemExit('Unmatched NoIPC source block')
        inside=False
    elif not inside: lines.append(line)
if inside: raise SystemExit('Unterminated NoIPC source block')
text='\n'.join(lines).lstrip('\n')
if not args.remove:
    url=args.url.rstrip('/')+'/'
    parsed=urlsplit(url)
    if parsed.scheme not in ('http','https') or not parsed.netloc or any(c.isspace() for c in url):
        raise SystemExit('Invalid archive URL')
    options='[arch=arm64 signed-by=/usr/share/keyrings/postgresql-noipc-archive-keyring.gpg]'
    text=f'{begin}\ndeb {options} {url} stable main\ndeb-src {options} {url} stable main\n{end}\n'+text
path.parent.mkdir(parents=True,exist_ok=True)
with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,delete=False) as temp:
    temp.write(text.rstrip('\n')+'\n')
    name=temp.name
os.chmod(name,stat.S_IMODE(prior.st_mode) if prior else 0o644)
if prior: os.chown(name,prior.st_uid,prior.st_gid)
os.replace(name,path)
