#!/usr/bin/env bash
# Starts the PostgreSQL container and checks that this shell can reach it.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compose=(docker compose -f "$REPO/docker-compose.yml")

"${compose[@]}" up -d --wait db

published="$("${compose[@]}" port db 5432)"
host="${published%:*}"
port="${published##*:}"
if ! timeout 3 bash -c "exec 3<>/dev/tcp/$host/$port" 2>/dev/null; then
    # /proc/net/route holds the default gateway as little-endian hex.
    hex="$(awk '$2 == "00000000" { print $3; exit }' /proc/net/route)"
    gateway="$(printf '%d.%d.%d.%d' "0x${hex:6:2}" "0x${hex:4:2}" "0x${hex:2:2}" "0x${hex:0:2}")"
    cat >&2 <<EOF
Error: PostgreSQL is running, but this shell can't reach it at $host:$port.
Docker publishes that port where the Docker daemon runs. If this shell is in a container
using the outer host's Docker, try the address of that host, which is often the gateway:
    echo DB_BIND=$gateway >> $REPO/.env
Then run scripts/install-native.sh again.
EOF
    exit 1
fi
