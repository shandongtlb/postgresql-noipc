#!/bin/bash
# Install on the root-enabled build machine, never in the phone chroot.
set -euo pipefail
[[ $(id -u) == 0 ]] || { echo 'Run as root on the build machine.' >&2; exit 1; }
PG_MAINTAINER_REPO=$(git -C "$(dirname "$0")" rev-parse --show-toplevel)
for PG_TOOL in systemd-nspawn machinectl mmdebstrap rsync cc gpg apt-ftparchive; do
  command -v "$PG_TOOL" >/dev/null || { echo "Missing build-machine tool: $PG_TOOL" >&2; exit 1; }
done
[[ -d $PG_MAINTAINER_REPO/noipc/keys-private/apt ]] || { echo 'Restore the existing private archive key first.' >&2; exit 1; }
python3 - "$PG_MAINTAINER_REPO" <<'PYCONFIG'
from pathlib import Path
import sys
repo=Path(sys.argv[1])
if any(c.isspace() for c in str(repo)): raise SystemExit('Use a build checkout path without whitespace')
service=f'''[Unit]
Description=Build, verify and publish released PostgreSQL 18 NoIPC updates
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
User=root
WorkingDirectory={repo}
ExecStart=/usr/bin/python3 {repo}/noipc/packaging/update.py --repo {repo}
Environment=PG_JOBS=6
StateDirectory=postgresql-noipc-update
StateDirectoryMode=0700
TimeoutStartSec=12h
Nice=10
StandardOutput=journal
StandardError=journal
'''
Path('/etc/systemd/system/postgresql-noipc-update.service').write_text(service)
Path('/etc/systemd/system/postgresql-noipc-update.timer').write_text('''[Unit]
Description=Daily released PostgreSQL 18 NoIPC update check

[Timer]
OnCalendar=*-*-* 03:30:00 UTC
RandomizedDelaySec=15min
Persistent=true
Unit=postgresql-noipc-update.service

[Install]
WantedBy=timers.target
''')
PYCONFIG
systemd-analyze verify /etc/systemd/system/postgresql-noipc-update.service /etc/systemd/system/postgresql-noipc-update.timer
systemctl daemon-reload
systemctl enable --now postgresql-noipc-update.timer
systemctl list-timers postgresql-noipc-update.timer --no-pager
