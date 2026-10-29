#!/bin/bash
# Native build inside an arm64/glibc Kali chroot, or any Linux build host.
set -euo pipefail
PG_PROJECT_DIR=$(cd -- "$(dirname -- "$0")" && pwd)
cd "$PG_PROJECT_DIR"
PG_VERSION=18.6
PG_INSTALL_PREFIX=${PG_INSTALL_PREFIX:-"$PG_PROJECT_DIR/install"}
PG_JOBS=${PG_JOBS:-$(getconf _NPROCESSORS_ONLN)}
mkdir -p downloads src build/local logs
bash "$PG_PROJECT_DIR/prepare-source.sh"
cd build/local
../../src/postgresql-$PG_VERSION/configure --prefix="$PG_INSTALL_PREFIX" \
  --without-icu --without-readline --without-zlib --without-liburing \
  > ../../logs/configure-local.log 2>&1
make -j"$PG_JOBS" > ../../logs/build-local.log 2>&1
make install > ../../logs/install-local.log 2>&1
printf 'Installed: %s\n' "$PG_INSTALL_PREFIX"
