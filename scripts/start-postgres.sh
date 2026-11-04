#!/usr/bin/env bash
# Starts the PostgreSQL installed by install-native.sh, if it isn't already running.
set -euo pipefail

NATIVE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/.native"
pg_ctl="$NATIVE/pg/bin/pg_ctl"

"$pg_ctl" -D "$NATIVE/pgdata" status >/dev/null 2>&1 \
    || "$pg_ctl" -D "$NATIVE/pgdata" -l "$NATIVE/postgres.log" -w start >/dev/null
