/*
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
				 errmsg("could not lock data directory \"%s\": %m", DataDir),
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

/*
 * Identify the huge page size to use, and compute the related mmap flags.
 *
 * Some Linux kernel versions have a bug causing mmap() to fail on requests
 * that are not a multiple of the hugepage size.  Versions without that bug
 * instead silently round the request up to the next hugepage multiple ---
 * and then munmap() fails when we give it a size different from that.
 * So we have to round our request up to a multiple of the actual hugepage
 * size to avoid trouble.
 *
 * Doing the round-up ourselves also lets us make use of the extra memory,
 * rather than just wasting it.  Currently, we just increase the available
 * space recorded in the shmem header, which will make the extra usable for
 * purposes such as additional locktable entries.  Someday, for very large
 * hugepage sizes, we might want to think about more invasive strategies,
 * such as increasing shared_buffers to absorb the extra space.
 *
 * Returns the (real, assumed or config provided) page size into
 * *hugepagesize, and the hugepage-related mmap flags to use into
 * *mmap_flags if requested by the caller.  If huge pages are not supported,
 * *hugepagesize and *mmap_flags are set to 0.
 */
void
GetHugePageSize(Size *hugepagesize, int *mmap_flags)
{
#ifdef MAP_HUGETLB

	Size		default_hugepagesize = 0;
	Size		hugepagesize_local = 0;
	int			mmap_flags_local = 0;

	/*
	 * System-dependent code to find out the default huge page size.
	 *
	 * On Linux, read /proc/meminfo looking for a line like "Hugepagesize:
	 * nnnn kB".  Ignore any failures, falling back to the preset default.
	 */
#ifdef __linux__

	{
		FILE	   *fp = AllocateFile("/proc/meminfo", "r");
		char		buf[128];
		unsigned int sz;
		char		ch;

		if (fp)
		{
			while (fgets(buf, sizeof(buf), fp))
			{
				if (sscanf(buf, "Hugepagesize: %u %c", &sz, &ch) == 2)
				{
					if (ch == 'k')
					{
						default_hugepagesize = sz * (Size) 1024;
						break;
					}
					/* We could accept other units besides kB, if needed */
				}
			}
			FreeFile(fp);
		}
	}
#endif							/* __linux__ */

	if (huge_page_size != 0)
	{
		/* If huge page size is requested explicitly, use that. */
		hugepagesize_local = (Size) huge_page_size * 1024;
	}
	else if (default_hugepagesize != 0)
	{
		/* Otherwise use the system default, if we have it. */
		hugepagesize_local = default_hugepagesize;
	}
	else
	{
		/*
		 * If we fail to find out the system's default huge page size, or no
		 * huge page size is requested explicitly, assume it is 2MB. This will
		 * work fine when the actual size is less.  If it's more, we might get
		 * mmap() or munmap() failures due to unaligned requests; but at this
		 * writing, there are no reports of any non-Linux systems being picky
		 * about that.
		 */
		hugepagesize_local = 2 * 1024 * 1024;
	}

	mmap_flags_local = MAP_HUGETLB;

	/*
	 * On recent enough Linux, also include the explicit page size, if
	 * necessary.
	 */
#if defined(MAP_HUGE_MASK) && defined(MAP_HUGE_SHIFT)
	if (hugepagesize_local != default_hugepagesize)
	{
		int			shift = pg_ceil_log2_64(hugepagesize_local);

		mmap_flags_local |= (shift & MAP_HUGE_MASK) << MAP_HUGE_SHIFT;
	}
#endif

	/* assign the results found */
	if (mmap_flags)
		*mmap_flags = mmap_flags_local;
	if (hugepagesize)
		*hugepagesize = hugepagesize_local;

#else

	if (hugepagesize)
		*hugepagesize = 0;
	if (mmap_flags)
		*mmap_flags = 0;

#endif							/* MAP_HUGETLB */
}

/*
 * GUC check_hook for huge_page_size
 */
bool
check_huge_page_size(int *newval, void **extra, GucSource source)
{
#if !(defined(MAP_HUGE_MASK) && defined(MAP_HUGE_SHIFT))
	/* Recent enough Linux only, for now.  See GetHugePageSize(). */
	if (*newval != 0)
	{
		GUC_check_errdetail("\"huge_page_size\" must be 0 on this platform.");
		return false;
	}
#endif
	return true;
}

/*
 * Creates an anonymous mmap()ed shared memory segment.
 *
 * Pass the requested size in *size.  This function will modify *size to the
 * actual size of the allocation, if it ends up allocating a segment that is
 * larger than requested.
 */
static void *
CreateAnonymousSegment(Size *size)
{
	Size		allocsize = *size;
	void	   *ptr = MAP_FAILED;
	int			mmap_errno = 0;

#ifndef MAP_HUGETLB
	/* PGSharedMemoryCreate should have dealt with this case */
	Assert(huge_pages != HUGE_PAGES_ON);
#else
	if (huge_pages == HUGE_PAGES_ON || huge_pages == HUGE_PAGES_TRY)
	{
		/*
		 * Round up the request size to a suitable large value.
		 */
		Size		hugepagesize;
		int			mmap_flags;

		GetHugePageSize(&hugepagesize, &mmap_flags);

		if (allocsize % hugepagesize != 0)
			allocsize += hugepagesize - (allocsize % hugepagesize);

		ptr = mmap(NULL, allocsize, PROT_READ | PROT_WRITE,
				   PG_MMAP_FLAGS | mmap_flags, -1, 0);
		mmap_errno = errno;
		if (huge_pages == HUGE_PAGES_TRY && ptr == MAP_FAILED)
			elog(DEBUG1, "mmap(%zu) with MAP_HUGETLB failed, huge pages disabled: %m",
				 allocsize);
	}
#endif

	/*
	 * Report whether huge pages are in use.  This needs to be tracked before
	 * the second mmap() call if attempting to use huge pages failed
	 * previously.
	 */
	SetConfigOption("huge_pages_status", (ptr == MAP_FAILED) ? "off" : "on",
					PGC_INTERNAL, PGC_S_DYNAMIC_DEFAULT);

	if (ptr == MAP_FAILED && huge_pages != HUGE_PAGES_ON)
	{
		/*
		 * Use the original size, not the rounded-up value, when falling back
		 * to non-huge pages.
		 */
		allocsize = *size;
		ptr = mmap(NULL, allocsize, PROT_READ | PROT_WRITE,
				   PG_MMAP_FLAGS, -1, 0);
		mmap_errno = errno;
	}

	if (ptr == MAP_FAILED)
	{
		errno = mmap_errno;
		ereport(FATAL,
				(errmsg("could not map anonymous shared memory: %m"),
				 (mmap_errno == ENOMEM) ?
				 errhint("This error usually means that PostgreSQL's request "
						 "for a shared memory segment exceeded available memory, "
						 "swap space, or huge pages. To reduce the request size "
						 "(currently %zu bytes), reduce PostgreSQL's shared "
						 "memory usage, perhaps by reducing \"shared_buffers\" or "
						 "\"max_connections\".",
						 allocsize) : 0));
	}

	*size = allocsize;
	return ptr;
}

/*
 * AnonymousShmemDetach --- detach from an anonymous mmap'd block
 * (called as an on_shmem_exit callback, hence funny argument list)
 */
static void
AnonymousShmemDetach(int status, Datum arg)
{
	/* Release anonymous shared memory block, if any. */
	if (AnonymousShmem != NULL)
	{
		if (munmap(AnonymousShmem, AnonymousShmemSize) < 0)
			elog(LOG, "munmap(%p, %zu) failed: %m",
				 AnonymousShmem, AnonymousShmemSize);
		AnonymousShmem = NULL;
	}
}

PGShmemHeader *
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
