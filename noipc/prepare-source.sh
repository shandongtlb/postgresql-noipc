#!/bin/bash
# Locate the upstream-layout source tree containing this helper directory.
set -euo pipefail
PG_SOURCE_ROOT=$(cd -- "$(dirname -- "$0")/.." && pwd)
if [[ ! -f $PG_SOURCE_ROOT/configure || ! -f $PG_SOURCE_ROOT/src/backend/port/sysv_shmem.c ]]; then
  echo 'Run this helper from a complete clone of postgresql-noipc.' >&2
  exit 1
fi
printf '%s\n' "$PG_SOURCE_ROOT"
