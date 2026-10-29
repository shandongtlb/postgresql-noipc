#!/usr/bin/env python3
"""Run as an unprivileged user; every child inherits the no-SysV filter."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

bindir = Path(sys.argv[1]).resolve() / 'bin'
work = Path(sys.argv[2]).resolve()
work.mkdir(parents=True, exist_ok=True)
data, sock = work / 'data', work / 'socket'
sock.mkdir(exist_ok=True)
port = sys.argv[3]
env = dict(os.environ, PGHOST=str(sock), PGPORT=port, PGUSER='pgbuild',
           PGDATABASE='postgres', LC_ALL='C')
results = []
victim = None

def cmd(name, *args, check=True, timeout=180, **kwargs):
    r = subprocess.run([str(bindir / name), *map(str, args)], env=env,
                       text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       timeout=timeout, **kwargs)
    if check and r.returncode:
        raise RuntimeError(f'{name} failed ({r.returncode}): {r.stdout}')
    return r

def sql(s, **kwargs):
    return cmd('psql', '-XAt', '-v', 'ON_ERROR_STOP=1', '-c', s, **kwargs).stdout.strip()

def passed(s):
    results.append(s)
    print('PASS:', s, flush=True)

def wait_ready():
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        r = cmd('psql', '-XAt', '-c', 'SELECT 1', check=False, timeout=10)
        if r.returncode == 0:
            return
        time.sleep(0.25)
    raise RuntimeError('database did not become ready')

def start():
    cmd('pg_ctl', '-D', data, '-l', work / 'server.log', '-w', '-t', '90', 'start')
    wait_ready()

def fail_start():
    r = cmd('postgres', '-D', data, '-c', 'port='+str(int(port)+100), check=False)
    assert r.returncode != 0 and 'could not lock data directory' in r.stdout, r.stdout

try:
    cmd('initdb', '-D', data, '-U', 'pgbuild', '--locale=C', '--encoding=UTF8',
        '--auth-local=trust', '--auth-host=scram-sha-256', '--no-instructions')
    with (data / 'postgresql.conf').open('a') as f:
        f.write(f"\nlisten_addresses=''\nport={port}\nunix_socket_directories='{sock}'\n"
                "shared_buffers=32MB\nmax_connections=30\nmax_parallel_workers=4\n"
                "huge_pages=off\nlogging_collector=on\n")
    start()
    assert sql('SHOW shared_memory_type') == 'mmap'
    assert sql('SHOW dynamic_shared_memory_type') == 'mmap'
    passed('initdb/startup with SysV shared memory and semaphores disabled')
    fail_start()
    passed('second server rejected by directory lock')

    # Removing the PID file must not bypass the inode-based interlock.
    pidfile = data / 'postmaster.pid'
    pidtext = pidfile.read_text()
    pidfile.unlink()
    try:
        fail_start()
        assert not pidfile.exists(), 'rejected server must not create a PID file'
    finally:
        pidfile.write_text(pidtext)
    passed('directory remains protected when postmaster.pid is removed')

    sql('CREATE TABLE proof AS SELECT i, md5(i::text) AS value FROM generate_series(1,200000) i; ANALYZE proof')
    assert sql('SELECT count(*),sum(i) FROM proof') == '200000|20000100000'
    passed('SQL create/insert/read and checksums')
    plan = sql("SET max_parallel_workers_per_gather=2; SET min_parallel_table_scan_size=0; "
               "SET parallel_setup_cost=0; SET parallel_tuple_cost=0; "
               "EXPLAIN (ANALYZE) SELECT sum(i) FROM proof")
    assert 'Workers Launched: 2' in plan, plan
    (work / 'parallel-plan.txt').write_text(plan+'\n')
    passed('parallel query launches 2 workers using mmap dynamic shared memory')
    cmd('pgbench', '-i', '-s', '1')
    bench = cmd('pgbench', '-c', '4', '-j', '2', '-t', '25').stdout
    assert 'number of failed transactions: 0' in bench, bench
    (work / 'pgbench.txt').write_text(bench)
    passed('100 concurrent pgbench transactions, zero failures')
    cmd('pg_dump', '-Fc', '-f', work / 'dump.pgdump')
    cmd('createdb', 'restored')
    cmd('pg_restore', '-d', 'restored', '--exit-on-error', work / 'dump.pgdump')
    assert cmd('psql', '-XAt', '-d', 'restored', '-c', 'SELECT count(*),sum(i) FROM proof').stdout.strip() == '200000|20000100000'
    passed('pg_dump/pg_restore round trip')

    # A backend crash must allow postmaster shmem reset without dropping lock.
    sleeper = subprocess.Popen([str(bindir/'psql'), '-XAt', '-c', 'SELECT pg_sleep(300)'],
                              env=dict(env, PGAPPNAME='crash-test'),
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    victim = None
    for _ in range(100):
        v = sql("SELECT pid FROM pg_stat_activity WHERE application_name='crash-test'")
        if v:
            victim = int(v)
            break
        time.sleep(0.1)
    assert victim
    os.kill(victim, signal.SIGKILL)
    sleeper.wait(timeout=30)
    wait_ready()
    assert sql('SELECT count(*) FROM proof') == '200000'
    fail_start()
    passed('backend SIGKILL recovery retains directory lock and committed data')

    sleeper = subprocess.Popen([str(bindir/'psql'), '-XAt', '-c', 'SELECT pg_sleep(300)'],
                              env=dict(env, PGAPPNAME='orphan-test'),
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    victim = None
    for _ in range(100):
        v = sql("SELECT pid FROM pg_stat_activity WHERE application_name='orphan-test'")
        if v:
            victim = int(v)
            break
        time.sleep(0.1)
    assert victim
    os.kill(victim, signal.SIGSTOP)
    postmaster = int(pidfile.read_text().splitlines()[0])
    os.kill(postmaster, signal.SIGKILL)
    time.sleep(1)
    fail_start()
    passed('orphan backend retains lock after postmaster SIGKILL')
    os.kill(victim, signal.SIGKILL)
    sleeper.wait(timeout=30)
    # Other children, including syslogger, must exit and release inherited FDs.
    deadline = time.monotonic()+30
    import fcntl
    while True:
        probe = os.open(data, os.O_RDONLY | os.O_DIRECTORY)
        try:
            fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.monotonic() > deadline:
                raise RuntimeError('orphan or logger still holds directory lock')
            time.sleep(0.25)
        finally:
            os.close(probe)
    victim = None
    start()
    assert sql('SELECT count(*),sum(i) FROM proof') == '200000|20000100000'
    passed('restart after all orphan processes exit; WAL crash recovery preserves data')
    single = cmd('postgres', '--single', '-D', data, 'postgres',
                 input='SELECT 1;\n', check=False)
    assert single.returncode != 0 and 'could not lock data directory' in single.stdout, single.stdout
    passed('single-user mode cannot bypass running server interlock')
    for _ in range(3):
        cmd('pg_ctl', '-D', data, '-m', 'fast', '-w', 'stop')
        start()
        assert sql('SELECT count(*) FROM proof') == '200000'
    passed('3 clean stop/start cycles preserve committed data')
    cmd('pg_ctl', '-D', data, '-m', 'fast', '-w', 'stop')
    single = cmd('postgres', '--single', '-D', data, 'postgres',
                 input='SELECT count(*) FROM proof;\n')
    assert '200000' in single.stdout, single.stdout
    passed('standalone single-user access succeeds after shutdown')
    print(f'ALL {len(results)} integration checks passed', flush=True)
finally:
    if victim:
        try:
            os.kill(victim, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if (data/'postmaster.pid').exists():
        cmd('pg_ctl', '-D', data, '-m', 'immediate', '-w', 'stop', check=False)
    (work/'results.json').write_text(json.dumps(results, indent=2)+'\n')
