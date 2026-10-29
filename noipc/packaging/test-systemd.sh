#!/bin/bash
# Run inside an isolated systemd test container with arm64 PostgreSQL after the APT tests.
set -euo pipefail
[[ -f /.noipc-kali-rootfs ]] || { echo 'Disposable build-root marker is required.' >&2; exit 1; }
[[ ! -e /usr/sbin/policy-rc.d ]] || { echo 'Remove the build-only service policy from this disposable test root.' >&2; exit 1; }
[[ $(cat /proc/1/comm) == systemd ]] || { echo 'systemd must be PID 1.' >&2; exit 1; }
python3 - <<'PY'
import ctypes,errno
c=ctypes.CDLL(None,use_errno=True)
assert c.shmget(0,4096,0o600)==-1 and ctypes.get_errno()==errno.ENOSYS
assert c.semget(0,1,0o600)==-1 and ctypes.get_errno()==errno.ENOSYS
assert c.msgget(0,0o600)==-1 and ctypes.get_errno()==errno.ENOSYS
print('PASS: systemd container processes inherit the no-SysV kernel simulation')
PY
systemctl is-enabled postgresql
# Observe boot activation without starting the service from the test.
for attempt in {1..60}; do
  systemctl is-active --quiet postgresql@18-main && break
  sleep 1
done
systemctl is-active postgresql@18-main
runuser -u postgres -- pg_isready
[[ $(runuser -u postgres -- psql -XAt -d postgres -c 'SELECT count(*) FROM noipc_package_test') == 200000 ]]
echo 'PASS: official enabled service automatically started the existing 18/main cluster on systemd boot'
systemctl restart postgresql@18-main
systemctl is-active postgresql@18-main
systemctl reload postgresql@18-main
systemctl stop postgresql@18-main
[[ $(systemctl is-active postgresql@18-main || true) == inactive ]]
systemctl start postgresql@18-main
[[ $(runuser -u postgres -- psql -XAt -d postgres -c 'SELECT count(*) FROM noipc_package_test') == 200000 ]]
echo 'PASS: official systemd start/stop/restart/reload and data persistence'
# Check real maintscript restart behavior with no build-time policy override.
previous_invocation=$(systemctl show --value -p InvocationID postgresql@18-main)
DEBIAN_FRONTEND=noninteractive apt-get -y --reinstall --no-install-recommends install postgresql-18
systemctl is-active postgresql@18-main
[[ $(systemctl show --value -p InvocationID postgresql@18-main) != "$previous_invocation" ]]
[[ $(runuser -u postgres -- psql -XAt -d postgres -c 'SELECT count(*) FROM noipc_package_test') == 200000 ]]
echo 'PASS: official package maintscripts restart the systemd instance during reinstall and preserve committed data'
systemctl --no-pager status postgresql@18-main
