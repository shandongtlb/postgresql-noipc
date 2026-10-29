#!/bin/bash
# Run only in an already-installed, disposable systemd/ARM64 test root.
set -euo pipefail
[[ -f /.noipc-kali-rootfs && ! -e /usr/sbin/policy-rc.d ]]
PG_APT_TEST_URI=${PG_APT_TEST_URI:?set the candidate archive URL}
PGPORT=$(pg_lsclusters --no-header 18 main | awk '{print $3}')
export PGPORT
systemctl start postgresql@18-main
sql() { runuser -u postgres -- psql -XAt -v ON_ERROR_STOP=1 -d postgres "$@"; }
[[ $(sql -c 'SELECT count(*),sum(i) FROM noipc_package_test') == '200000|20000100000' ]]
[[ $(sql -c 'SHOW log_min_duration_statement') == 1234ms ]]
old_version=$(dpkg-query -W -f='${Version}' postgresql-18)
old_invocation=$(systemctl show --value -p InvocationID postgresql@18-main)
/usr/lib/postgresql-noipc/configure-source --url "$PG_APT_TEST_URI"
apt update
candidate=$(apt-cache policy postgresql-18 | sed -n 's/^  Candidate: //p')
apt -s dist-upgrade > /tmp/noipc-dist-upgrade-before.txt
cat /tmp/noipc-dist-upgrade-before.txt
grep -F "Inst postgresql-18 [$old_version] ($candidate " /tmp/noipc-dist-upgrade-before.txt
echo 'PASS: plain apt update and dist-upgrade select the candidate server replacement'
DEBIAN_FRONTEND=noninteractive apt -y dist-upgrade
[[ $(dpkg-query -W -f='${Version}' postgresql-18) == "$candidate" ]]
new_archive=$(dpkg-query -W -f='${Version}' postgresql-noipc-archive-keyring)
dpkg-query -W -f='${Depends}' postgresql-18 | grep -F "postgresql-noipc-archive-keyring (>= $new_archive)"
echo "PASS: ordinary ARM64 apt dist-upgrade installed the new build: $old_version -> $candidate"
systemctl is-active postgresql@18-main
[[ $(systemctl show --value -p InvocationID postgresql@18-main) != "$old_invocation" ]]
[[ $(sql -c 'SELECT count(*),sum(i) FROM noipc_package_test') == '200000|20000100000' ]]
[[ $(sql -c 'SHOW log_min_duration_statement') == 1234ms ]]
[[ $(pg_lsclusters --no-header | wc -l) == 1 ]]
echo 'PASS: upgrade restarted the official service and preserved 200000 rows, configuration and the single existing cluster'
# The upgraded configuration package restores the canonical public URL. Point
# this disposable fixture back to the candidate when checking convergence.
/usr/lib/postgresql-noipc/configure-source --url "$PG_APT_TEST_URI"
apt update
apt -s dist-upgrade > /tmp/noipc-dist-upgrade-after.txt
cat /tmp/noipc-dist-upgrade-after.txt
if grep -E '^Inst (postgresql|libpq|libecpg|libpgtypes)' /tmp/noipc-dist-upgrade-after.txt; then
  echo 'Current PostgreSQL packages would be installed again' >&2
  exit 1
fi
echo 'PASS: another ordinary dist-upgrade does not reinstall the current PostgreSQL build'
