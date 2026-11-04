#!/usr/bin/env bash
# Starts the PostgreSQL container and checks that this shell can reach it.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compose=(docker compose -f "$REPO/docker-compose.yml")

"${compose[@]}" up -d --wait db

published="$("${compose[@]}" port db 5432)"
port="${published##*:}"
if ! timeout 3 bash -c "exec 3<>/dev/tcp/127.0.0.1/$port" 2>/dev/null; then
    cat >&2 <<EOF
Error: PostgreSQL is running, but this shell can't reach it at 127.0.0.1:$port.
Docker publishes that port where the Docker daemon runs. If this shell is in a container
using another machine's or the outer host's Docker, that is a different 127.0.0.1.
EOF
    exit 1
fi
