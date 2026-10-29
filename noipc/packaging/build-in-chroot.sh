#!/bin/bash
# Run inside a Kali arm64 build chroot after prepare-debian-source.py.
set -euo pipefail
PG_PACKAGE_SOURCE=${1:-/build/postgresql-18.6}
cd "$PG_PACKAGE_SOURCE"
export DEBIAN_FRONTEND=noninteractive
export DEB_BUILD_PROFILES='nocheck nodoc'
export DEB_BUILD_OPTIONS="parallel=${PG_JOBS:-6} nocheck nodoc noautodbgsym"
PG_BUILD_ARGS=()
if [[ ${PG_NOIPC_RESUME:-0} == 1 ]]; then
  PG_BUILD_ARGS+=(--no-pre-clean)
else
  apt-get update
  apt-get -y --no-install-recommends build-dep .
fi
# The shared PostgreSQL rules call make directly; force the jobserver so those
# recursive makes also receive the requested parallelism.
dpkg-buildpackage "${PG_BUILD_ARGS[@]}" --build=any --no-sign --jobs-force="${PG_JOBS:-6}"
# The clean source package was already produced by prepare-debian-source.py.
