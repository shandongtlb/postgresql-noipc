# Source this file from Bash before invoking tools directly.
PG_MOBILE_PREFIX=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
export PATH="$PG_MOBILE_PREFIX/bin:$PATH"
export LD_LIBRARY_PATH="$PG_MOBILE_PREFIX/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export PGDATA=${PGDATA:-"$PG_MOBILE_PREFIX/var/data"}
export PGHOST=${PGHOST:-"$PG_MOBILE_PREFIX/var/run"}
export PGPORT=${PGPORT:-5432}
