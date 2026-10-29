# Kali NetHunter arm64 APT build verification

Target: current Kali rolling arm64 NetHunter chroot with systemd. Build date: 2026-10-29.
Upstream: PostgreSQL 18.6; official Debian/Kali packaging: 18.6-3; rebuild: 18.6-3+noipc1.

The six functional source files in the Debian-prepared source were compared byte-for-byte with this Git checkout. The clean modified source package was produced before the binary build. The build used the official PostgreSQL packaging rules and full optional runtime features. The `nocheck nodoc` profiles skip build-time tests and the standalone documentation package; they do not disable runtime features. Integration tests were run separately.

Results: all 12 APT/package checks and all 4 systemd/IPC checks passed. The existing 200,000-row table survived package reinstall, remove/reinstall and a fresh systemd boot. Two further public-archive checks passed after publishing branch `apt` (initial archive commit `3d45d5c`): real APT signature/candidate resolution and authenticated server/metapackage/bootstrap downloads from raw.githubusercontent.com.

Evidence:

- `apt-build-config.txt`: actual ARM64 `pg_config` output and feature flags.
- `apt-deb-audit.json`: 14 ARM64 packages, 137 AArch64 ELF files, no imports of the 12 SysV shared-memory/semaphore/message-queue functions. Server dependency and highest required GLIBC version: 2.43.
- `apt-artifact-sha256.txt`: exact binary/source/build metadata checksums.
- `apt-install.log`: signed local HTTP APT installation and package integration results.
- `apt-systemd.log`: boot, service lifecycle and real package maintscript restart results.
- `apt-public-source.log`: public GitHub archive signature verification and package candidate.

The archive contains 14 rebuilt binary packages, an archive key/source configuration package, a PostgreSQL NoIPC metapackage, and the matching modified source package. Its InRelease/Release signatures use the scoped archive key with fingerprint `8404657F5B03D8A975D4572BD95D2C6AD8196DBD`.

## Test environment and limits

Tests use an isolated Kali rolling ARM64 userspace on an x86_64 Linux host, with ARM64 executables running under QEMU user emulation. A seccomp filter inherited by the entire container returns ENOSYS for all 12 SysV IPC syscalls. ARM64 Python checks that shared-memory, semaphore and message-queue syscalls really fail with ENOSYS.

ARM64 systemd under QEMU started the initial database and passed TLS, parallel-query, PL language and JIT checks, but became unresponsive during a later daemon-reload. To complete service tests, the test container uses the host's native x86_64 systemd manager, executor and their libraries through read-only mounts. PostgreSQL, its clients, package scripts, cluster tools and all database modules remain ARM64. The distribution's PostgreSQL service units are unchanged. Six infrastructure service overrides clear ImportCredential for QEMU compatibility; none change PostgreSQL services.

The disposable test root is copied from the build root. The build-only policy-rc.d initially suppressed maintscript starts during an early reinstall. It was removed before remove/reinstall and the separate systemd boot test; the latter additionally verifies a genuine maintscript-driven instance restart by comparing systemd InvocationID across reinstall. No such policy or emulation override is shipped in the packages.

These are emulation and package/service integration results, not a claim of physical-phone or native ARM64 systemd validation. Installation in the user's actual NetHunter chroot remains to be checked there.
