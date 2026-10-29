#!/bin/bash
# Build genuine Debian/Kali packages in an isolated arm64 Kali filesystem.
set -euo pipefail
PG_NOIPC_DIR=$(cd -- "$(dirname -- "$0")/.." && pwd)
PG_ROOTFS=${PG_BUILD_ROOTFS:-"$PG_NOIPC_DIR/build/packaging/kali-arm64-rootfs"}
PG_CACHE="$PG_NOIPC_DIR/packaging/upstream"
PG_LOGS="$PG_NOIPC_DIR/logs/packaging"
PG_OUTPUT=${PG_BUILD_OUTPUT:-"$PG_NOIPC_DIR/artifacts/debian-arm64"}
PG_JOBS=${PG_JOBS:-6}
PG_UPSTREAM_VERSION=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["upstream_version"])' "$PG_NOIPC_DIR/packaging/manifest.json")
PG_PACKAGE_SOURCE="/build/postgresql-$PG_UPSTREAM_VERSION"
if [[ $(id -u) != 0 ]]; then
  echo 'Run as root; the build uses mmdebstrap and chroot.' >&2; exit 1
fi
for PG_TOOL in mmdebstrap gpg dpkg-source curl chroot mountpoint; do
  command -v "$PG_TOOL" >/dev/null || { echo "Missing build tool: $PG_TOOL" >&2; exit 1; }
done
mkdir -p "$PG_CACHE" "$PG_LOGS" "$PG_OUTPUT"
exec 9>"$PG_ROOTFS.lock"
flock -n 9 || { echo 'Another package build holds this rootfs.' >&2; exit 1; }
if [[ ! -e $PG_ROOTFS/.noipc-kali-rootfs ]]; then
  if [[ -e $PG_ROOTFS ]]; then
    echo "Unmarked rootfs exists: $PG_ROOTFS; refusing to replace it." >&2; exit 1
  fi
  curl -fL --retry 3 -o "$PG_CACHE/kali-archive-keyring.gpg" https://archive.kali.org/archive-keyring.gpg
  gpg --show-keys --with-colons "$PG_CACHE/kali-archive-keyring.gpg" \
    | python3 -c 'import sys; assert "827C8569F2518CC677FECA1AED65462EC8D5E4C5" in sys.stdin.read()'
  mmdebstrap --architectures=arm64 --variant=minbase \
    --keyring="$PG_CACHE/kali-archive-keyring.gpg" \
    --include=ca-certificates,kali-archive-keyring,build-essential,devscripts,equivs,debhelper,dh-exec,eatmydata \
    kali-rolling "$PG_ROOTFS" 'deb https://http.kali.org/kali kali-rolling main' \
    > "$PG_LOGS/bootstrap-arm64.log" 2>&1
  printf 'kali-rolling arm64\n' > "$PG_ROOTFS/.noipc-kali-rootfs"
fi
install -d "$PG_ROOTFS/build"
if [[ ${PG_NOIPC_FRESH_SOURCE:-0} == 1 ]]; then
  python3 - "$PG_ROOTFS" <<'PYCLEAN'
from pathlib import Path
import shutil,sys
root=Path(sys.argv[1])
assert (root/'.noipc-kali-rootfs').is_file()
for p in (root/'build').glob('postgresql-*'):
    if p.is_dir() and (p/'debian/control').is_file(): shutil.rmtree(p)
for p in (root/'build').iterdir():
    if p.is_file() and p.name.endswith(('.deb','.dsc','.changes','.buildinfo','.xz','.bz2','.gz')):
        p.unlink()
PYCLEAN
fi
if [[ ! -d $PG_ROOTFS$PG_PACKAGE_SOURCE ]]; then
  python3 "$PG_NOIPC_DIR/packaging/prepare-debian-source.py" "$PG_ROOTFS/build" \
    > "$PG_LOGS/prepare-source.log" 2>&1
fi
# Reusing a rootfs must never silently build an older patch or manifest.
python3 - "$PG_NOIPC_DIR" "$PG_ROOTFS$PG_PACKAGE_SOURCE" <<'PYVERIFY'
import json,sys
from pathlib import Path
noipc,source=map(Path,sys.argv[1:])
assert json.loads((noipc/'packaging/manifest.json').read_text()) == json.loads(
    (source/'debian/noipc-build-manifest.json').read_text()), 'Stale build manifest; prepare a fresh source tree'
for name in ('src/backend/port/sysv_shmem.c', 'src/backend/utils/init/miscinit.c',
             'src/backend/utils/misc/guc_tables.c', 'src/bin/initdb/initdb.c',
             'src/include/storage/dsm_impl.h', 'src/include/storage/pg_shmem.h'):
    assert (source/name).read_bytes() == (noipc.parent/name).read_bytes(), f'Stale build source: {name}'
PYVERIFY
cat > "$PG_ROOTFS/usr/sbin/policy-rc.d" <<'EOF'
#!/bin/sh
# A package build must not start services in its build chroot.
exit 101
EOF
chmod 0755 "$PG_ROOTFS/usr/sbin/policy-rc.d"
install -m 0755 "$PG_NOIPC_DIR/packaging/build-in-chroot.sh" "$PG_ROOTFS/build/build-in-chroot.sh"
PG_MOUNTED_PROC=0
if ! mountpoint -q "$PG_ROOTFS/proc"; then
  mount -t proc proc "$PG_ROOTFS/proc"
  PG_MOUNTED_PROC=1
fi
trap 'if [[ $PG_MOUNTED_PROC == 1 ]]; then umount "$PG_ROOTFS/proc"; fi' EXIT
chroot "$PG_ROOTFS" /usr/bin/eatmydata /usr/bin/env PG_JOBS="$PG_JOBS" \
  /bin/bash /build/build-in-chroot.sh "$PG_PACKAGE_SOURCE" > "$PG_LOGS/build-debian-arm64.log" 2>&1
python3 - "$PG_ROOTFS/build" "$PG_OUTPUT" <<'PY'
from pathlib import Path
import shutil,sys
source,output=map(Path,sys.argv[1:])
for f in source.iterdir():
    if f.is_file() and f.name.endswith(('.deb','.dsc','.changes','.buildinfo','.xz','.bz2','.gz')):
        shutil.copy2(f,output/f.name)
PY
printf 'Debian arm64 packages: %s\n' "$PG_OUTPUT"
