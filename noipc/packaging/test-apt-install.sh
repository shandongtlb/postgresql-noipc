#!/bin/bash
# Execute only in the disposable Kali rootfs, under the host's deny-sysvipc filter.
set -euo pipefail
[[ -f /.noipc-kali-rootfs ]] || { echo 'Disposable build-root marker is required.' >&2; exit 1; }
[[ ! -e /usr/sbin/policy-rc.d ]] || { echo 'Remove the build-only service policy from this disposable test root.' >&2; exit 1; }
PG_APT_TEST_URI=${PG_APT_TEST_URI:?set the HTTP URL of the test archive}
export DEBIAN_FRONTEND=noninteractive
PG_APT_SOURCE=/etc/apt/sources.list
PG_TEST_RESULTS=/tmp/noipc-apt-test-results.txt
: > "$PG_TEST_RESULTS"
passed() { printf 'PASS: %s\n' "$1" | tee -a "$PG_TEST_RESULTS"; }
cleanup() { service postgresql stop >/dev/null 2>&1 || true; }
trap cleanup EXIT
stock_libpq_version=$(dpkg-query -W -f='${Version}' libpq5)
[[ $(dpkg-query -W -f='${Postgresql-Noipc}' libpq5) != yes ]]
curl -fL "$PG_APT_TEST_URI/postgresql-noipc-archive-keyring_all.deb" -o /tmp/postgresql-noipc-keyring.deb
apt-get -y --no-install-recommends install /tmp/postgresql-noipc-keyring.deb ssl-cert
/usr/lib/postgresql-noipc/configure-source --url "$PG_APT_TEST_URI"
apt-get update
passed 'APT verifies the signed archive with a scoped Signed-By keyring'
apt-cache policy postgresql-18
apt -y dist-upgrade
[[ $(dpkg-query -W -f='${Postgresql-Noipc}' libpq5) == yes ]]
dpkg --compare-versions "$(dpkg-query -W -f='${Version}' libpq5)" gt "$stock_libpq_version"
passed 'plain apt dist-upgrade replaces the installed stock libpq5 with a newer NoIPC package revision'
apt-get -y --no-install-recommends install postgresql postgresql-client postgresql-18-jit \
  postgresql-plperl-18 postgresql-plpython3-18 postgresql-pltcl-18 \
  libecpg-compat3 libecpg-dev libecpg6 libpgtypes3 libpq-dev libpq-oauth postgresql-server-dev-18
[[ $(dpkg-query -W -f='${Postgresql-Noipc}' postgresql-18) == yes ]]
[[ $(dpkg-query -W -f='${Postgresql-Noipc}' postgresql) == yes ]]
[[ $(dpkg-query -W -f='${Postgresql-Noipc}' postgresql-client) == yes ]]
grep -q '^Pin-Priority: -1$' /etc/apt/preferences.d/postgresql-noipc
[[ -f /etc/init.d/postgresql ]]
[[ -f /usr/lib/systemd/system/postgresql@.service || -f /lib/systemd/system/postgresql@.service ]]
[[ -f /etc/logrotate.d/postgresql-common ]]
[[ -f /etc/postgresql/18/main/postgresql.conf ]]
[[ -f /var/lib/postgresql/18/main/PG_VERSION ]]
passed 'standard package names, postgresql-common services, logrotate and automatic 18/main cluster creation'
service postgresql start
service postgresql status
PGPORT=$(pg_lsclusters --no-header 18 main | awk '{print $3}')
export PGPORT
pg_sql() { runuser -u postgres -- psql -XAt -v ON_ERROR_STOP=1 -d postgres "$@"; }
[[ $(pg_sql -c 'SHOW shared_memory_type') == mmap ]]
[[ $(pg_sql -c 'SHOW dynamic_shared_memory_type') == mmap ]]
passed 'official service starts the cluster with SysV IPC disabled'
for cluster in noipc-extra noipcextra; do
  if [[ -d /etc/postgresql/18/$cluster ]]; then pg_dropcluster --stop 18 "$cluster"; fi
done
pg_sql <<'SQL'
DROP TABLE IF EXISTS noipc_package_test;
DROP ROLE IF EXISTS noipc_smoke;
CREATE TABLE noipc_package_test AS SELECT i FROM generate_series(1,200000) i;
ANALYZE noipc_package_test;
CREATE ROLE noipc_smoke LOGIN PASSWORD 'noipc-service-test';
SQL
[[ $(pg_sql -c 'SELECT count(*),sum(i) FROM noipc_package_test') == '200000|20000100000' ]]
plan=$(pg_sql -c 'SET max_parallel_workers_per_gather=2; SET min_parallel_table_scan_size=0; SET parallel_setup_cost=0; SET parallel_tuple_cost=0; EXPLAIN (ANALYZE) SELECT sum(i) FROM noipc_package_test')
[[ $plan == *'Workers Launched: 2'* ]]
passed 'SQL and parallel query using the official installed layout'
[[ $(pg_sql -c 'SHOW ssl') == on ]]
[[ $(PGPASSWORD=noipc-service-test psql -XAt -v ON_ERROR_STOP=1 \
    "host=127.0.0.1 port=$PGPORT dbname=postgres user=noipc_smoke sslmode=require" \
    -c 'SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()') == t ]]
passed 'TLS connection and SCRAM password authentication'
pg_sql <<'SQL'
CREATE EXTENSION IF NOT EXISTS plpython3u;
CREATE OR REPLACE FUNCTION noipc_python() RETURNS integer LANGUAGE plpython3u AS 'return 42';
CREATE EXTENSION IF NOT EXISTS plperl;
CREATE OR REPLACE FUNCTION noipc_perl() RETURNS integer LANGUAGE plperl AS 'return 42;';
CREATE EXTENSION IF NOT EXISTS pltcl;
CREATE OR REPLACE FUNCTION noipc_tcl() RETURNS integer LANGUAGE pltcl AS 'return 42';
SQL
[[ $(pg_sql -c 'SELECT noipc_python(),noipc_perl(),noipc_tcl()') == '42|42|42' ]]
passed 'official Python, Perl and Tcl language packages'
jitplan=$(pg_sql -c 'SET jit_above_cost=0; EXPLAIN (ANALYZE) SELECT sum(i) FROM noipc_package_test')
[[ $jitplan == *'JIT:'* ]]
passed 'LLVM/JIT module loads and compiles a query'
pg_createcluster 18 noipcextra --start
pg_ctlcluster 18 noipcextra stop
pg_dropcluster 18 noipcextra
passed 'pg_createcluster/pg_ctlcluster/pg_dropcluster support a second cluster'
if runuser -u postgres -- /usr/lib/postgresql/18/bin/postgres -D /var/lib/postgresql/18/main \
    -c config_file=/etc/postgresql/18/main/postgresql.conf -p "$((PGPORT+100))" \
    > /tmp/noipc-second-server.log 2>&1; then
  echo 'Unexpected successful second server' >&2; exit 1
fi
grep -q 'could not lock data directory' /tmp/noipc-second-server.log
passed 'standard data directory remains protected against a second server'
pg_conftool 18 main set log_min_duration_statement 1234
pg_ctlcluster 18 main reload
[[ $(pg_sql -c 'SHOW log_min_duration_statement') == 1234ms ]]
apt-get -y --reinstall --no-install-recommends install postgresql-18
service postgresql restart
[[ $(pg_sql -c 'SELECT count(*) FROM noipc_package_test') == 200000 ]]
[[ $(pg_sql -c 'SHOW log_min_duration_statement') == 1234ms ]]
[[ -s /var/log/postgresql/postgresql-18-main.log ]]
passed 'package reinstall preserves data and configuration and supports normal restart/reload'
service postgresql stop
apt-get -y remove postgresql postgresql-18
[[ -f /var/lib/postgresql/18/main/PG_VERSION && -f /etc/postgresql/18/main/postgresql.conf ]]
apt-get -y --no-install-recommends install postgresql postgresql-client
service postgresql start
[[ $(pg_sql -c 'SELECT count(*) FROM noipc_package_test') == 200000 ]]
passed 'remove/reinstall retains the cluster and committed data'
pg_sql -c 'DROP ROLE noipc_smoke'
install -d -o _apt -g root -m 0755 /tmp/noipc-apt-source
cd /tmp/noipc-apt-source
apt-get --download-only source postgresql-18
passed 'authenticated deb-src source package download'
printf 'All %s APT/package integration checks passed\n' "$(wc -l < "$PG_TEST_RESULTS")"
