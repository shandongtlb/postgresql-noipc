# Official package names and stock-core exclusion

Date: 2026-10-29. Core binaries remain 18.6-3+noipc1, byte-for-byte identical to the previous release.
New metapackages: `postgresql` and `postgresql-client`, both version 18+noipc1.
Archive configuration update: `postgresql-noipc-archive-keyring` 2026.10.29.2. Archive commit: `6312152`. Exact new package checksums are in `apt-policy-artifact-sha256.txt`.

The standard metapackages depend on the existing standard-named `postgresql-18` / `postgresql-client-18` packages and the new archive configuration. The old `postgresql-noipc` alias continues to refer to exactly those same binaries; it does not install another server or create another cluster.

The shipped preferences assign priority 1001 to this archive's rebuilt packages and standard metapackages. A second record assigns -1 to other versions of PostgreSQL core source packages and the two standard metapackages. The core-source regular expression is bounded to numeric major/version names, so a separately packaged extension whose source is named `postgresql-18-special` is still allowed. `postgresql-common` / `postgresql-client-common` are separate source packages and continue to receive normal Kali updates.

This uses standard [APT preferences](https://manpages.debian.org/unstable/apt/apt_preferences.5.en.html). It controls default candidate selection. It does not remove existing other-major clusters or erase data, and it does not replace an administrator's ability to explicitly override APT policy. Future patched releases still require maintainer builds and publication.

All 16 isolated policy checks, 5 ARM64 migration/final-policy checks and 2 public-archive checks passed.

## Evidence

- `apt-policy.log`: all 16 real-APT checks pass in an isolated state directory using the exact preferences extracted from the final bootstrap .deb and the actual NoIPC Packages index. Synthetic stock indices offer higher 18.x versions, a future major 99, legacy 9.6, amd64 libpq, newer common packages and independent extensions. They check normal selection, a Kali target-release preference, refusal of stock-only core installation, and no stock fallback when the NoIPC archive is absent. No synthetic package is installed. Reproduce with `python3 noipc/packaging/test-apt-policy.py noipc/repository`.
- `apt-policy-upgrade.log`: actual ARM64 Kali APT upgrades the old 2026.10.29.1 bootstrap, installs the standard metapackages, retains exactly one installed server and one cluster, preserves the server's SHA256 and start timestamp, retains all 200,000 committed rows, and simulates a clean ordinary upgrade. A subsequent reinstall verifies the final bounded-source policy payload.
- `apt-policy-public.log`: after publication, actual ARM64 Kali APT authenticates the public GitHub archive, resolves both standard names to the NoIPC metapackages, shows stock packages at -1 and common packages at 500, and downloads the public bootstrap/metapackages.

The ARM64 package migration uses the same QEMU/native-systemd test setup and no-SysV seccomp filter described in `apt-verification.md`. Runtime core binaries and service units are unchanged, so the prior runtime integration results continue to apply. Physical-phone validation is still pending.
