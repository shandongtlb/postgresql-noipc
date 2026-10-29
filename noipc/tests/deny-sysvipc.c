/* Execute a command with System V shared-memory, semaphore and message queues disabled.
 * The filter survives exec and fork, just like a kernel without CONFIG_SYSVIPC.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <stddef.h>
#include <stdio.h>
#include <unistd.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <linux/filter.h>
#include <linux/seccomp.h>

#define DENY(n) BPF_JUMP(BPF_JMP|BPF_JEQ|BPF_K, __NR_##n, 0, 1), \
				BPF_STMT(BPF_RET|BPF_K, SECCOMP_RET_ERRNO|ENOSYS)
int main(int argc, char **argv)
{
	struct sock_filter filter[] = {
		BPF_STMT(BPF_LD|BPF_W|BPF_ABS, offsetof(struct seccomp_data, nr)),
		DENY(shmget), DENY(shmat), DENY(shmdt), DENY(shmctl),
		DENY(semget), DENY(semop), DENY(semtimedop), DENY(semctl),
		DENY(msgget), DENY(msgsnd), DENY(msgrcv), DENY(msgctl),
		BPF_STMT(BPF_RET|BPF_K, SECCOMP_RET_ALLOW)
	};
	struct sock_fprog prog = { sizeof(filter)/sizeof(filter[0]), filter };
	if (argc < 2) return 2;
	if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) ||
		prctl(PR_SET_SECCOMP, SECCOMP_MODE_FILTER, &prog))
	{ perror("seccomp"); return 1; }
	execvp(argv[1], argv+1);
	perror("execvp");
	return 1;
}
