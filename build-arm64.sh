#!/bin/bash
# Cross-build using the verified Debian arm64 sysroot and aarch64-cc wrapper.
# The toolchain/sysroot manifest records the exact Debian packages used.
set -euo pipefail
PG_PROJECT_DIR=$(cd -- "$(dirname -- "$0")" && pwd)
PG_JOBS=${PG_JOBS:-$(getconf _NPROCESSORS_ONLN)}
cd "$PG_PROJECT_DIR"
mkdir -p build/arm64 logs src
bash "$PG_PROJECT_DIR/prepare-source.sh"
test -d "$PG_PROJECT_DIR/toolchain/sysroot/usr/include"
cd "$PG_PROJECT_DIR/build/arm64"
# Autoconf skips the runtime export-dynamic probe when cross compiling. GNU ld
# supports it, and PostgreSQL needs exported backend symbols for its modules.
pgac_cv_prog_cc_LDFLAGS_EX_BE__Wl___export_dynamic=yes \
../../src/postgresql-18.6/configure --build="$(gcc -dumpmachine)" \
  --host=aarch64-linux-gnu --prefix=/opt/pgsql-18-no-sysvipc \
  CC="$PG_PROJECT_DIR/toolchain/aarch64-cc" AR=aarch64-linux-gnu-ar \
  RANLIB=aarch64-linux-gnu-ranlib STRIP=aarch64-linux-gnu-strip \
  CFLAGS='-O2 -march=armv8-a -mno-outline-atomics' LDFLAGS='-static-libgcc' \
  --without-icu --without-readline --without-zlib --without-liburing \
  > ../../logs/configure-arm64.log 2>&1
make -j"$PG_JOBS" > ../../logs/build-arm64.log 2>&1
make install DESTDIR="$PG_PROJECT_DIR/stage-arm64" > ../../logs/install-arm64.log 2>&1
