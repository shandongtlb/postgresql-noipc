#!/bin/bash
# Native build of the checked-out upstream-layout source tree.
set -euo pipefail
PG_PROJECT_DIR=$(cd -- "$(dirname -- "$0")" && pwd)
cd "$PG_PROJECT_DIR"
PG_SOURCE_ROOT=$(bash "$PG_PROJECT_DIR/prepare-source.sh")
PG_INSTALL_PREFIX=${PG_INSTALL_PREFIX:-"$PG_PROJECT_DIR/install"}
PG_JOBS=${PG_JOBS:-$(getconf _NPROCESSORS_ONLN)}
mkdir -p build/native logs
cd build/native
"$PG_SOURCE_ROOT/configure" --prefix="$PG_INSTALL_PREFIX" \
  --without-icu --without-readline --without-zlib --without-liburing \
  > ../../logs/configure-native.log 2>&1
make -j"$PG_JOBS" > ../../logs/build-native.log 2>&1
make install > ../../logs/install-native.log 2>&1
printf 'Installed: %s\n' "$PG_INSTALL_PREFIX"
