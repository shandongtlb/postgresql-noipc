# PostgreSQL NoIPC APT archive

Packages are rebuilt from Debian/Kali postgresql-18 18.6-3 with the NoIPC patch.
This branch is a signed static APT archive for **Kali rolling arm64**.
Only the current release is retained. This branch is published as a single Git
snapshot; the source branch retains upstream history. PostgreSQL keeps the official
upstream version and standard package names. Debian package versions add +noipcN;
each rebuild advances N so ordinary apt update && apt dist-upgrade installs updates.

Inside the phone's Kali chroot, as root:

```sh
curl -fLO https://raw.githubusercontent.com/shandongtlb/postgresql-noipc/apt/postgresql-noipc-archive-keyring_all.deb
apt install ./postgresql-noipc-archive-keyring_all.deb
apt update
apt dist-upgrade
apt install postgresql postgresql-client
systemctl enable --now postgresql
systemctl status postgresql@18-main --no-pager
pg_lsclusters
```

The standard `postgresql` and `postgresql-client` metapackages select the NoIPC 18 packages.
`postgresql-18` and all versioned binary package names also match the distribution names.
`postgresql-noipc` remains available as a compatibility alias; it uses the same server package.
Debian package revisions are newer than the corresponding Kali packages. The managed first source and pre-install marker guard
ensure unmarked stock packages cannot replace this build. Other stock core versions are
pinned to -1. Use `apt update && apt dist-upgrade` for stock-package migration and all updates. Shared `postgresql-common` infrastructure and
independently packaged extensions remain available from Kali. Existing clusters are not deleted.
To update an installation bootstrapped with version 2026.10.29.1, run
`apt update && apt dist-upgrade`. Historical +noipc trial versions also migrate this way;
when using -y for that one-time downgrade, add --allow-downgrades.
Official `postgresql-common` provides cluster management, systemd/SysV service files, logging,
and upgrade scripts. The target NetHunter chroot runs systemd, so enabling the service starts
the database whenever that chroot's systemd boots. Other chroots without init can use `service`.

Archive signing fingerprint: `8404657F5B03D8A975D4572BD95D2C6AD8196DBD`.
Installation, scheduled updates and maintenance: https://github.com/shandongtlb/postgresql-noipc/blob/main/noipc/packaging/MAINTENANCE.zh-CN.md
