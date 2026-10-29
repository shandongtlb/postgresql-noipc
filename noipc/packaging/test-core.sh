#!/bin/bash
# Exercise crash recovery and inherited directory locks using installed binaries.
set -euo pipefail
[[ -f /.noipc-kali-rootfs ]]
install -d -o postgres -g postgres -m 0700 /tmp/noipc-core-integration
runuser -u postgres -- python3 /opt/noipc-tests/integration.py \
  /usr/lib/postgresql/18 /tmp/noipc-core-integration 55433
