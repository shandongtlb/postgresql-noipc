#!/usr/bin/env python3
"""Check signed Kali source metadata, rebuild released PG18, test and publish."""
import argparse
from datetime import datetime,timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
from versions import package_versions

CORE=('src/backend/port/sysv_shmem.c','src/backend/utils/init/miscinit.c',
      'src/backend/utils/misc/guc_tables.c','src/bin/initdb/initdb.c',
      'src/include/storage/dsm_impl.h','src/include/storage/pg_shmem.h')

def run(argv,**kw):
    print('+ '+' '.join(map(str,argv)),flush=True)
    return subprocess.run(list(map(str,argv)),check=True,**kw)

def output(argv,**kw):
    return subprocess.check_output(list(map(str,argv)),text=True,**kw).strip()

def fingerprint(repo):
    paths=[repo/p for p in CORE]+[repo/'noipc/tests/deny-sysvipc.c']+sorted((repo/'noipc/packaging').glob('*.py'))+sorted((repo/'noipc/packaging').glob('*.sh'))
    digest=hashlib.sha256()
    for path in paths:
        digest.update(str(path.relative_to(repo)).encode()+b'\0'+path.read_bytes())
    return digest.hexdigest()

def records(text):
    for paragraph in text.strip().split('\n\n'):
        result={};key=None
        for line in paragraph.splitlines():
            if line.startswith((' ','\t')) and key: result[key]+='\n'+line.strip()
            elif ': ' in line or line.endswith(':'):
                key,value=line.split(':',1);result[key]=value.strip()
        if result: yield result

def discover(root):
    if not (root/'.noipc-kali-rootfs').is_file(): raise RuntimeError('Build root is not bootstrapped/marked')
    p=root/'etc/apt/sources.list.d/noipc-build-sources.list'
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text('deb-src https://http.kali.org/kali kali-rolling main\n')
    run(['chroot',root,'apt-get','-o','APT::Update::Error-Mode=any','update'])
    candidates=list(records(output(['chroot',root,'apt-cache','showsrc','--only-source','postgresql-18'])))
    candidate=None
    for record in candidates:
        if record.get('Package')!='postgresql-18': continue
        if candidate is None or subprocess.run(['dpkg','--compare-versions',record['Version'],'gt',candidate['Version']]).returncode==0:
            candidate=record
    if not candidate: raise RuntimeError('No signed Kali postgresql-18 source record')
    binary=next(records(output(['chroot',root,'apt-cache','show','--no-all-versions','postgresql-18'])))
    meta=next(records(output(['chroot',root,'apt-cache','show','--no-all-versions','postgresql'])))['Version']
    if not meta.startswith('18+'):
        raise RuntimeError('Kali default major changed; review PG18 metapackages manually')
    version=candidate['Version']
    if not re.fullmatch(re.escape(version)+r'(?:\+b[0-9]+)?', binary['Version']):
        raise RuntimeError('Source/binary versions disagree; review Kali metadata')
    if not re.fullmatch(r'18\.\d+-[0-9A-Za-z.+~]+',version): raise RuntimeError(f'Unsupported official version: {version}')
    sums={}
    for line in candidate['Checksums-Sha256'].strip().splitlines():
        digest,size,name=line.split()
        if '/' in name or not re.fullmatch('[a-f0-9]{64}',digest): raise RuntimeError('Invalid signed source record')
        sums[name]=digest
    files={name:digest for name,digest in sums.items() if '.orig.tar.' in name or '.debian.tar.' in name}
    if len(files)!=2: raise RuntimeError('Expected one orig archive and one Debian archive')
    return {'upstream_version':version.rsplit('-',1)[0],'debian_version':version,
            'source_base_url':'https://http.kali.org/kali/'+candidate['Directory'].strip('/')+'/',
            'binary_version':binary['Version'],'official_binary_sha256':binary['SHA256'],
            'metapackage_version':meta,
            'files':files,'dsc_sha256':next(value for name,value in sums.items() if name.endswith('.dsc'))}

def pool_hashes(repo):
    return {str(p.relative_to(repo)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((repo/'pool').rglob('*')) if p.is_file()}

def snapshot(archive,target):
    if target.exists(): shutil.rmtree(target)
    target.mkdir(parents=True)
    run(['rsync','-a','--exclude=.git',str(archive)+'/',str(target)+'/'])
    run(['git','init','-b','apt',target],stdout=subprocess.DEVNULL)
    for key,value in (('user.name','SDTLB'),('user.email','40312509+shandongtlb@users.noreply.github.com')):
        run(['git','-C',target,'config',key,value])
    run(['git','-C',target,'add','.'])
    run(['git','-C',target,'commit','-m','Current signed PostgreSQL NoIPC APT snapshot'],stdout=subprocess.DEVNULL)
    return output(['git','-C',target,'rev-parse','HEAD'])

def publish(repo,archive,state,expected_main,expected_apt):
    candidate=state/'snapshot'
    apt_commit=snapshot(archive,candidate)
    run(['git','-C',repo,'fetch','--no-tags',candidate,'+refs/heads/apt:refs/noipc/apt-candidate'])
    run(['git','-C',repo,'merge-base','--is-ancestor',expected_main,'HEAD'])
    run(['git','-C',repo,'push','--atomic',f'--force-with-lease=refs/heads/apt:{expected_apt}',
         f'--force-with-lease=refs/heads/main:{expected_main}','origin',
         'HEAD:refs/heads/main','refs/noipc/apt-candidate:refs/heads/apt'])
    return apt_commit

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=Path(__file__).resolve().parents[2])
    parser.add_argument('--state',type=Path,default=Path('/var/lib/postgresql-noipc-update'))
    parser.add_argument('--rootfs',type=Path)
    parser.add_argument('--signing-home',type=Path)
    parser.add_argument('--check',action='store_true')
    parser.add_argument('--rebuild',action='store_true')
    args=parser.parse_args()
    repo=args.repo.resolve();state=args.state.resolve()
    if os.geteuid()!=0: raise RuntimeError('Run on the root-enabled build machine')
    state.mkdir(parents=True,exist_ok=True)
    marker=state/'.noipc-update-state'
    if not marker.exists() and any(state.iterdir()): raise RuntimeError('Refusing an unmarked nonempty update state directory')
    marker.write_text('PostgreSQL NoIPC managed build/update state\n')
    lock=(state/'run.lock').open('w')
    try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        print('An update is already running');return
    status={'started':datetime.now(timezone.utc).isoformat(),'status':'running'}
    def save():
        temp=state/'last-run.json.tmp';temp.write_text(json.dumps(status,indent=2)+'\n');temp.replace(state/'last-run.json')
    save()
    try:
        root=args.rootfs or repo/'noipc/build/packaging/kali-arm64-rootfs'
        keys=args.signing_home or repo/'noipc/keys-private/apt'
        expected_key='8404657F5B03D8A975D4572BD95D2C6AD8196DBD'
        listed=output(['gpg','--homedir',keys,'--batch','--with-colons','--list-secret-keys',expected_key])
        if not any(line.startswith('fpr:') and line.split(':')[9]==expected_key for line in listed.splitlines()):
            raise RuntimeError('Existing archive signing key is missing; automatic key replacement is forbidden')
        run(['git','-C',repo,'fetch','origin','main'])
        start=output(['git','-C',repo,'rev-parse','origin/main'])
        apt_ref=output(['git','-C',repo,'ls-remote','--heads','origin','apt']).split()[0]
        run(['git','-C',repo,'fetch','upstream','+refs/heads/REL_18_STABLE:refs/remotes/upstream/REL_18_STABLE'])
        manifest=json.loads(output(['git','-C',repo,'show',f'{start}:noipc/packaging/manifest.json']))
        previous=json.loads(output(['git','-C',repo,'show',f'{start}:noipc/packaging/published.json']))
        official=discover(root)
        tag='REL_'+official['upstream_version'].replace('.','_')
        if subprocess.run(['git','-C',repo,'rev-parse','--verify',f'refs/tags/{tag}'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
            run(['git','-C',repo,'fetch','upstream','tag',tag])
        run(['git','-C',repo,'merge-base','--is-ancestor',tag,'upstream/REL_18_STABLE'])
        work=state/'worktree'
        if work.exists(): run(['git','-C',repo,'worktree','remove','--force',work])
        run(['git','-C',repo,'worktree','add','--detach',work,start],stdout=subprocess.DEVNULL)
        current_fingerprint=fingerprint(work)
        changed=args.rebuild or official['debian_version']!=manifest['debian_version'] or official['files']!=manifest['files'] or official['binary_version']!=manifest.get('binary_version',manifest['debian_version']) or official['metapackage_version']!=manifest['metapackage_version'] or official['official_binary_sha256']!=manifest.get('official_binary_sha256') or current_fingerprint!=previous['recipe_fingerprint']
        status.update(official_version=official['debian_version'],upstream_release=tag,update_available=bool(changed))
        if args.check or not changed:
            status['status']='update-available' if changed else 'up-to-date';save();print(json.dumps(status,indent=2));return
        if subprocess.run(['dpkg','--compare-versions',official['binary_version'],'lt',manifest.get('binary_version',manifest['debian_version'])]).returncode==0:
            raise RuntimeError('Refusing an upstream archive rollback')
        run(['git','-C',work,'merge','--no-edit',tag])
        revision=previous.get('noipc_revision',1)+1
        manifest.update(official,noipc_revision=revision,
                        noipc_version=official['debian_version']+f'+noipc{revision}')
        keyring_version=datetime.now(timezone.utc).strftime('%Y.%m.%d.%H%M%S')
        if subprocess.run(['dpkg','--compare-versions',keyring_version,'gt',previous['archive_keyring_version']]).returncode:
            raise RuntimeError('Clock/version mismatch while advancing the archive build revision')
        manifest['archive_keyring_version']=keyring_version
        meta=official['metapackage_version']
        manifest['metapackage_version']=meta
        versions=package_versions(manifest)
        for candidate,previous_version in (
                (versions['binary'],previous.get('noipc_binary_version',previous['binary_version'])),
                (versions['meta'],previous.get('noipc_metapackage_version',previous['metapackage_version']))):
            if subprocess.run(['dpkg','--compare-versions',candidate,'gt',previous_version]).returncode:
                raise RuntimeError(f'Local package version must advance: {previous_version} -> {candidate}')
        (work/'noipc/packaging/manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        artifacts=state/'artifacts'
        if artifacts.exists(): shutil.rmtree(artifacts)
        artifacts.mkdir()
        env=dict(os.environ,PG_BUILD_ROOTFS=str(root),PG_BUILD_OUTPUT=str(artifacts),PG_NOIPC_FRESH_SOURCE='1')
        run(['bash',work/'noipc/packaging/build-debs.sh'],env=env)
        archive=state/'repository'
        if archive.exists(): shutil.rmtree(archive)
        def create_archive():
            run(['python3',work/'noipc/packaging/create-apt-repository.py','--packages',artifacts,
                 '--output',archive,'--signing-home',keys,'--metapackage-version',meta,
                 '--keyring-version',keyring_version])
        create_archive()
        bootstrap=archive/'postgresql-noipc-archive-keyring_all.deb'
        for test in ('test-apt-policy.py','test-install-guard.py','test-source-versions.py'):
            command=['python3',work/'noipc/packaging'/test]
            if test=='test-apt-policy.py': command.append(archive)
            target={'test-apt-policy.py':'apt-policy.log','test-install-guard.py':'apt-install-guard.log',
                    'test-source-versions.py':'source-version-tests.log'}[test]
            with (work/'noipc/verification'/target).open('w') as log:
                run(command,stdout=log,stderr=subprocess.STDOUT)
        with (work/'noipc/verification/apt-deb-audit.json').open('w') as log:
            run(['python3',work/'noipc/packaging/audit-debs.py',artifacts],stdout=log)
        prior_root=state/'tests/testroot'
        upgrade_result=None
        if (prior_root/'.noipc-kali-rootfs').is_file():
            run(['python3',work/'noipc/packaging/test-packages.py','--rootfs',root,
                 '--repository',archive,'--state',state/'upgrade-tests','--upgrade-root',prior_root])
            upgrade_result=json.loads((state/'upgrade-tests/result.json').read_text())
        run(['python3',work/'noipc/packaging/test-packages.py','--rootfs',root,'--repository',archive,'--state',state/'tests'])
        with (work/'noipc/verification/apt-dist-upgrade.log').open('w') as log:
            run(['python3',work/'noipc/packaging/test-dist-upgrade.py',archive,
                 '--rootfs',state/'tests/testroot'],stdout=log,stderr=subprocess.STDOUT)
        tests=json.loads((state/'tests/result.json').read_text())
        if upgrade_result: tests.update(installed_upgrade_checks=upgrade_result['installed_upgrade_checks'])
        for filename in ('apt-install.log','apt-systemd.log','core-integration.log'):
            text=(state/'tests'/filename).read_text()
            (work/'noipc/verification'/filename).write_text('\n'.join(
                line for line in text.splitlines() if line.startswith(('PASS:','ALL ','All ')))+'\n')
        new={'debian_version':manifest['debian_version'],'binary_version':manifest['binary_version'],'metapackage_version':meta,
             'noipc_revision':revision,'noipc_version':versions['source'],
             'noipc_binary_version':versions['binary'],'noipc_metapackage_version':versions['meta'],
             'recipe_fingerprint':fingerprint(work),'upstream_tag':tag,
             'published_at':datetime.now(timezone.utc).isoformat(),'package_hashes':pool_hashes(archive),
             'archive_keyring_version':keyring_version,
             'archive_keyring_sha256':hashlib.sha256(bootstrap.read_bytes()).hexdigest()}
        (work/'noipc/packaging/published.json').write_text(json.dumps(new,indent=2)+'\n')
        (work/'noipc/verification/package-revision-provenance.json').write_text(json.dumps(
            {'kind':'full source build in Kali ARM64','source_version':versions['source'],
             'binary_version':versions['binary'],'upstream_tag':tag},indent=2)+'\n')
        (work/'noipc/verification/latest-update.json').write_text(json.dumps(dict(new,tests=tests),indent=2)+'\n')
        run(['git','-C',work,'add','noipc/packaging/manifest.json','noipc/packaging/published.json',
             'noipc/verification/apt-deb-audit.json','noipc/verification/latest-update.json',
             'noipc/verification/apt-policy.log','noipc/verification/apt-install-guard.log',
             'noipc/verification/apt-install.log','noipc/verification/apt-systemd.log',
             'noipc/verification/core-integration.log','noipc/verification/source-version-tests.log',
             'noipc/verification/apt-dist-upgrade.log','noipc/verification/package-revision-provenance.json'])
        run(['git','-C',work,'diff','--cached','--check'])
        run(['git','-C',work,'commit','-m',f'Publish PostgreSQL NoIPC {versions["binary"]}'])
        status['apt_commit']=publish(work,archive,state,start,apt_ref)
        status['status']='published';save()
    except Exception as error:
        status.update(status='failed',error=str(error));save();raise

if __name__=='__main__':
    def stopped(signum, frame):
        raise InterruptedError('Update stopped by a signal')
    signal.signal(signal.SIGTERM, stopped)
    main()
