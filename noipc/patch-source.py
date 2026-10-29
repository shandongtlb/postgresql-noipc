#!/usr/bin/env python3
"""Apply the Linux/fork-only no-SysV port to pristine PostgreSQL 18.6."""
from pathlib import Path
import sys

root = Path(sys.argv[1])
p = root / 'src/backend/port/sysv_shmem.c'
old = p.read_text()
# Retain upstream anonymous mapping and huge-page handling verbatim.
helpers = old[old.index('/*\n * Identify the huge page size'):old.index('/*\n * PGSharedMemoryCreate\n')]
p.write_text('''/*
 * Linux fork-only shared memory port for kernels without CONFIG_SYSVIPC.
 * Main memory uses anonymous mmap; flock on the DataDir inode replaces the
 * SysV shim's orphan-process interlock. See README.zh-CN.md in the patch kit.
 * Portions Copyright (c) 1996-2025, PostgreSQL Global Development Group
 * Portions Copyright (c) 1994, Regents of the University of California
 * Distributed under the PostgreSQL License, as in the upstream COPYRIGHT file.
 */
#include "postgres.h"
#include <fcntl.h>
#include <unistd.h>
#include <sys/file.h>
#include <sys/mman.h>
#include <sys/stat.h>

#include "miscadmin.h"
#include "port/pg_bitutils.h"
#include "portability/mem.h"
#include "storage/fd.h"
#include "storage/ipc.h"
#include "storage/pg_shmem.h"
#include "utils/guc.h"
#include "utils/guc_hooks.h"
#include "utils/pidfile.h"

#if !defined(__linux__) || defined(EXEC_BACKEND)
#error "The no-SysV shared memory port requires Linux and fork backends"
#endif

unsigned long UsedShmemSegID = 0;
void *UsedShmemSegAddr = NULL;
static Size AnonymousShmemSize;
static void *AnonymousShmem = NULL;
static int DataDirLockFD = -1;

/*
 * Lock the directory inode, not a removable lock file. Acquire before touching
 * postmaster.pid, including in single-user mode. flock's open-file description
 * is inherited by fork, so an orphan backend keeps the lock after SIGKILL of
 * the postmaster. Never use LOCK_UN: that would unlock every inherited copy.
 * O_CLOEXEC prevents shell commands inheriting the lock. We deliberately keep
 * the postmaster FD until process exit, including across shmem crash resets.
 */
void
PGSharedMemoryLock(void)
{
    int save_errno;

    if (DataDirLockFD >= 0)
        return;
    DataDirLockFD = open(DataDir, O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    if (DataDirLockFD < 0)
        ereport(FATAL,
                (errcode_for_file_access(),
                 errmsg("could not open data directory for interlock: %m")));
    if (flock(DataDirLockFD, LOCK_EX | LOCK_NB) < 0)
    {
        save_errno = errno;
        close(DataDirLockFD);
        DataDirLockFD = -1;
        errno = save_errno;
        ereport(FATAL,
                (errcode(ERRCODE_LOCK_FILE_EXISTS),
                 errmsg("could not lock data directory \\"%s\\": %m", DataDir),
                 errhint("Another server or an orphan backend may still be using this data directory. The filesystem must support flock on directories.")));
    }
}

bool
PGSharedMemoryIsInUse(unsigned long id1, unsigned long id2)
{
    /* CreateDataDirLockFile already acquired the stronger directory lock. */
    Assert(DataDirLockFD >= 0);
    return false;
}

''' + helpers + '''PGShmemHeader *
PGSharedMemoryCreate(Size size, PGShmemHeader **shim)
{
    PGShmemHeader *hdr;
    struct stat statbuf;

    Assert(DataDirLockFD >= 0);
    Assert(size > MAXALIGN(sizeof(PGShmemHeader)));
    if (shared_memory_type != SHMEM_TYPE_MMAP)
        ereport(FATAL,
                (errcode(ERRCODE_FEATURE_NOT_SUPPORTED),
                 errmsg("this build requires shared_memory_type=mmap")));
#ifndef MAP_HUGETLB
    if (huge_pages == HUGE_PAGES_ON)
        ereport(ERROR,
                (errcode(ERRCODE_FEATURE_NOT_SUPPORTED),
                 errmsg("huge pages not supported on this platform")));
#endif
    if (fstat(DataDirLockFD, &statbuf) < 0)
        ereport(FATAL,
                (errcode_for_file_access(),
                 errmsg("could not stat locked data directory: %m")));
    AnonymousShmem = CreateAnonymousSegment(&size);
    AnonymousShmemSize = size;
    on_shmem_exit(AnonymousShmemDetach, (Datum) 0);
    hdr = (PGShmemHeader *) AnonymousShmem;
    hdr->creatorPID = getpid();
    hdr->magic = PGShmemMagic;
    hdr->dsm_control = 0;
    hdr->device = statbuf.st_dev;
    hdr->inode = statbuf.st_ino;
    hdr->totalsize = size;
    hdr->freeoffset = MAXALIGN(sizeof(PGShmemHeader));
    *shim = hdr;
    UsedShmemSegAddr = hdr;
    AddToDataDirLockFile(LOCK_FILE_LINE_SHMEM_KEY, "        0         0");
    return hdr;
}

void
PGSharedMemoryDetach(void)
{
    AnonymousShmemDetach(0, (Datum) 0);
    UsedShmemSegAddr = NULL;
    /* Children without shared memory (e.g. syslogger) must not pin the lock. */
    if (DataDirLockFD >= 0)
    {
        close(DataDirLockFD);
        DataDirLockFD = -1;
    }
}
''')

# Match PostgreSQL's four-column tab indentation in the replacement port.
lines = p.read_text().splitlines(keepends=True)
p.write_text(''.join(
    '\t' * ((len(line) - len(line.lstrip(' '))) // 4)
    + ' ' * ((len(line) - len(line.lstrip(' '))) % 4)
    + line.lstrip(' ')
    for line in lines
))

def replace(rel, before, after):
    p = root / rel
    text = p.read_text()
    assert text.count(before) == 1, (rel, before)
    p.write_text(text.replace(before, after))

replace('src/include/storage/pg_shmem.h',
        'extern void PGSharedMemoryDetach(void);',
        'extern void PGSharedMemoryLock(void);\nextern void PGSharedMemoryDetach(void);')
replace('src/backend/utils/init/miscinit.c',
        'CreateDataDirLockFile(bool amPostmaster)\n{',
        'CreateDataDirLockFile(bool amPostmaster)\n{\n\tPGSharedMemoryLock();')
replace('src/include/storage/dsm_impl.h',
        '#define DEFAULT_DYNAMIC_SHARED_MEMORY_TYPE\t\tDSM_IMPL_POSIX',
        '#define DEFAULT_DYNAMIC_SHARED_MEMORY_TYPE\t\tDSM_IMPL_MMAP')
replace('src/include/storage/dsm_impl.h', '#define USE_DSM_SYSV\n', '')
replace('src/include/storage/dsm_impl.h',
        '#define DEFAULT_DYNAMIC_SHARED_MEMORY_TYPE\t\tDSM_IMPL_SYSV',
        '#define DEFAULT_DYNAMIC_SHARED_MEMORY_TYPE\t\tDSM_IMPL_MMAP')
p = root / 'src/bin/initdb/initdb.c'
s = p.read_text()
start = s.index('choose_dsm_implementation(void)\n{')
end = s.index('\n}\n', start) + 3
s = s[:start] + 'choose_dsm_implementation(void)\n{\n\treturn "mmap";\n}\n' + s[end:]
p.write_text(s)
replace('src/backend/utils/misc/guc_tables.c',
        '\t{"sysv", SHMEM_TYPE_SYSV, false},\n', '')
