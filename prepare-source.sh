#!/bin/bash
# Use the committed patched source, or prepare it from the pinned release.
set -euo pipefail
PG_PROJECT_DIR=$(cd -- "$(dirname -- "$0")" && pwd)
cd "$PG_PROJECT_DIR"
PG_SOURCE_DIR=src/postgresql-18.6
if [[ -f $PG_SOURCE_DIR/.no-sysvipc-patched ]]; then
  exit 0
fi
if [[ -e $PG_SOURCE_DIR ]]; then
  echo "Unmarked source directory exists: $PG_SOURCE_DIR; refusing to overwrite it." >&2
  exit 1
fi
mkdir -p downloads src
if [[ ! -f downloads/postgresql-18.6.tar.bz2 ]]; then
  curl -fL --retry 3 -o downloads/postgresql-18.6.tar.bz2 \
    https://ftp.postgresql.org/pub/source/v18.6/postgresql-18.6.tar.bz2
fi
printf '%s  %s\n' \
  555610c24d53e4316da5b7d3fc25c279d96856d5e0e23ee308c328c5fa881d9f \
  downloads/postgresql-18.6.tar.bz2 | sha256sum -c -
tar -xjf downloads/postgresql-18.6.tar.bz2 -C src
patch -d "$PG_SOURCE_DIR" -p1 < postgresql-18.6-no-sysvipc.patch
touch "$PG_SOURCE_DIR/.no-sysvipc-patched"
