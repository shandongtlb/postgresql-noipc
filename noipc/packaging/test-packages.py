#!/usr/bin/env python3
"""Run the actual ARM64 APT and official systemd integration suites."""
import argparse
from functools import partial
import http.server
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import threading
import time

parser=argparse.ArgumentParser()
parser.add_argument('--rootfs',type=Path,required=True)
parser.add_argument('--repository',type=Path,required=True)
parser.add_argument('--state',type=Path,required=True)
args=parser.parse_args()
base=Path(__file__).resolve().parents[1]
state=args.state.resolve();state.mkdir(parents=True,exist_ok=True)
root=state/'testroot';machine='postgresql-noipc-ci'
if not (args.rootfs/'.noipc-kali-rootfs').is_file(): raise SystemExit('Unmarked build root')
if subprocess.run(['machinectl','show',machine],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:
    raise SystemExit('The test machine is already running')
if root.exists():
    if not (root/'.noipc-kali-rootfs').is_file(): raise SystemExit('Unmarked test root')
    shutil.rmtree(root)
root.mkdir()
subprocess.run(['rsync','-a','--exclude=/build','--exclude=/proc/*','--exclude=/sys/*',
                '--exclude=/run/*',str(args.rootfs.resolve())+'/',str(root)+'/'],check=True)
# The minbase package-build root intentionally has no init or curl. Install
# test infrastructure while the build-only policy still prevents daemon starts.
with (state/'bootstrap-test-root.log').open('w') as log:
    subprocess.run(['mount','-t','proc','proc',str(root/'proc')],check=True)
    try:
        subprocess.run(['chroot',str(root),'/usr/bin/env','DEBIAN_FRONTEND=noninteractive',
                        'apt-get','-o','APT::Update::Error-Mode=any','update'],
                       stdout=log,stderr=subprocess.STDOUT,check=True,timeout=600)
        subprocess.run(['chroot',str(root),'/usr/bin/env','DEBIAN_FRONTEND=noninteractive',
                        'apt-get','-y','--no-install-recommends','install',
                        'systemd','systemd-sysv','dbus','curl','ssl-cert'],
                       stdout=log,stderr=subprocess.STDOUT,check=True,timeout=1800)
    finally:
        subprocess.run(['umount',str(root/'proc')],check=True)
(root/'usr/sbin/policy-rc.d').unlink(missing_ok=True)
# Only infrastructure credentials are overridden for QEMU. PG units are untouched.
if platform.machine()=='x86_64':
    for unit in ('systemd-journald','systemd-sysusers','systemd-tmpfiles-dev-early',
                 'systemd-tmpfiles-dev','systemd-tmpfiles','systemd-logind'):
        p=root/f'etc/systemd/system/{unit}.service.d/noipc-emulation.conf'
        p.parent.mkdir(parents=True,exist_ok=True);p.write_text('[Service]\nImportCredential=\n')
    p=root/'etc/systemd/system.conf.d/noipc-emulation.conf'
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text('[Manager]\nDefaultEnvironment=QEMU_CPU=cortex-a53\n')
helper=state/'deny-sysvipc'
subprocess.run(['cc','-O2','-Wall','-Wextra',str(base/'tests/deny-sysvipc.c'),'-o',str(helper)],check=True)
handler=partial(http.server.SimpleHTTPRequestHandler,directory=str(args.repository.resolve()))
http=http.server.ThreadingHTTPServer(('127.0.0.1',0),handler)
threading.Thread(target=http.serve_forever,daemon=True).start()
uri=f'http://127.0.0.1:{http.server_port}'
process=None;bootlog=None

def control(*argv,**kwargs):
    return subprocess.run(['systemctl',f'--machine={machine}',*argv],check=True,timeout=120,**kwargs)

def stop():
    global process,bootlog
    if process is None: return
    if process.poll() is None:
        try:
            # Wait specifically for instance stop; the aggregate unit may finish earlier.
            control('stop','postgresql@18-main')
            control('stop','postgresql')
        except Exception: pass
        leader=int(subprocess.check_output(['machinectl','show',machine,'-p','Leader','--value'],text=True))
        a=(root/'.noipc-kali-rootfs').stat();b=Path(f'/proc/{leader}/root/.noipc-kali-rootfs').stat()
        assert leader>1 and (a.st_dev,a.st_ino)==(b.st_dev,b.st_ino)
        assert os.readlink(f'/proc/{leader}/ns/pid')!=os.readlink('/proc/1/ns/pid')
        os.kill(leader,signal.SIGKILL)
    process.wait(timeout=30);process=None
    bootlog.close()

def boot(name):
    global process,bootlog
    cmd=[str(helper),'systemd-nspawn',f'--directory={root}','--boot',f'--machine={machine}',
         '--setenv=QEMU_CPU=cortex-a53','--capability=CAP_SYS_RESOURCE','--private-users=no',
         '--link-journal=no','--resolv-conf=copy-host','--console=pipe',
         f'--bind-ro={base / "packaging"}:/opt/noipc-packaging',
         f'--bind-ro={base / "tests"}:/opt/noipc-tests']
    if platform.machine()=='x86_64':
        (root/'usr/lib64').mkdir(exist_ok=True)
        link=root/'usr/lib64/ld-linux-x86-64.so.2'
        if not link.is_symlink(): link.symlink_to('../lib/x86_64-linux-gnu/ld-linux-x86-64.so.2')
        if not (root/'lib64').exists(): (root/'lib64').symlink_to('usr/lib64')
        cmd+=['--bind-ro=/usr/lib/x86_64-linux-gnu:/usr/lib/x86_64-linux-gnu']
        for binary in ('systemd','systemd-executor','systemd-shutdown'):
            cmd.append(f'--bind-ro=/usr/lib/systemd/{binary}:/usr/lib/systemd/{binary}')
    bootlog=(state/name).open('w')
    process=subprocess.Popen(cmd,stdout=bootlog,stderr=subprocess.STDOUT,
                             env=dict(os.environ,QEMU_CPU='cortex-a53'))
    for _ in range(120):
        if process.poll() is not None: raise RuntimeError('Test container failed to boot')
        result=subprocess.run(['systemctl',f'--machine={machine}','show','--property=Version'],
                              stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
        if result.returncode==0: return
        time.sleep(0.5)
    raise RuntimeError('Timed out waiting for the test manager')

def suite(script,filename,expected):
    path=state/filename
    with path.open('w') as log:
        subprocess.run(['systemd-run',f'--machine={machine}','--quiet','--wait','--pipe','--collect',
                        '/usr/bin/env',f'PG_APT_TEST_URI={uri}','/bin/bash',f'/opt/noipc-packaging/{script}'],
                       stdout=log,stderr=subprocess.STDOUT,check=True,timeout=3600)
    count=path.read_text().count('PASS:')
    if count!=expected: raise RuntimeError(f'{script}: expected {expected} checks; found {count}')
    print(f'PASS: {script}: {count} integration checks',flush=True)

def stopped(signum, frame):
    raise InterruptedError('Integration run stopped by a signal')
signal.signal(signal.SIGTERM, stopped)

try:
    boot('boot-install.log')
    suite('test-apt-install.sh','apt-install.log',12)
    suite('test-core.sh','core-integration.log',13)
    control('enable','postgresql')
    stop()
    boot('boot-restart.log')
    suite('test-systemd.sh','apt-systemd.log',4)
    result={'apt_checks':12,'core_crash_lock_checks':13,'systemd_ipc_checks':4,'postgresql_arch':'arm64',
            'controller_arch':platform.machine(),'sysv_ipc':'all 12 syscalls return ENOSYS',
            'physical_phone_tested':False}
    (state/'result.json').write_text(json.dumps(result,indent=2)+'\n')
finally:
    stop();http.shutdown();http.server_close()
