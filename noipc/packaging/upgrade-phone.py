#!/usr/bin/python3
"""Reinstall the same official versions, including already-installed core modules."""
import argparse
import subprocess

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('-y','--yes',action='store_true')
parser.add_argument('--no-update',action='store_true')
args=parser.parse_args()
if not args.no_update:
    subprocess.run(['apt-get','-o','APT::Update::Error-Mode=any','update'],check=True)
installed=subprocess.check_output(['dpkg-query','-W','-f=${binary:Package}\t${source:Package}\t${db:Status-Status}\n'],text=True)
supported={'libecpg-compat3','libecpg-dev','libecpg6','libpgtypes3','libpq-dev','libpq-oauth','libpq5',
           'postgresql-18-jit','postgresql-18','postgresql-client-18','postgresql-plperl-18',
           'postgresql-plpython3-18','postgresql-pltcl-18','postgresql-server-dev-18'}
native=subprocess.check_output(['dpkg','--print-architecture'],text=True).strip()
packages={'postgresql','postgresql-client','postgresql-18','postgresql-client-18','libpq5'}
for line in installed.splitlines():
    name,source,status=line.split('\t')
    if ':' in name and name.split(':',1)[1] != native: continue
    name=name.split(':',1)[0]
    if status=='installed' and (name.split(':')[0] in supported or name in ('postgresql','postgresql-client','postgresql-noipc')):
        packages.add(name)
command=['apt-get','--allow-downgrades','--reinstall']
if args.yes: command.append('-y')
subprocess.run(command+['install',*sorted(packages)],check=True)
