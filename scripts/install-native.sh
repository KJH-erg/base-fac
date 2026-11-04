#!/usr/bin/env bash
# Installs Odoo 20 directly on a Debian or Ubuntu host, with PostgreSQL in Docker.
# Odoo and its Python packages go in .native/ in this repo; build libraries are
# installed system-wide with apt. Safe to run again.
set -euo pipefail

ODOO_BRANCH=20.0

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NATIVE="$REPO/.native"
CONF="$NATIVE/odoo.conf"

log() { printf '\n==> %s\n' "$*"; }
die() { printf 'Error: %s\n' "$*" >&2; exit 1; }

command -v apt-get >/dev/null || die "this script supports Debian and Ubuntu only."
docker compose version >/dev/null 2>&1 || die "Docker with Compose v2 is required for PostgreSQL."
docker ps >/dev/null 2>&1 || die "can't talk to Docker. Check that it's running and that your user can use it."

if [ "$(id -u)" -eq 0 ]; then
    as_root() { "$@"; }
else
    command -v sudo >/dev/null || die "run this as root, or install sudo."
    as_root() { sudo "$@"; }
fi
export DEBIAN_FRONTEND=noninteractive

log "Installing system packages"
as_root -E apt-get update -qq
as_root -E apt-get install -y -qq --no-install-recommends \
    build-essential ca-certificates curl git libffi-dev libjpeg-dev libldap2-dev libpq-dev \
    libsasl2-dev libssl-dev libxml2-dev libxslt1-dev openssl postgresql-client tzdata zlib1g-dev >/dev/null
# Only needed for PDF reports, and not packaged on every release.
as_root -E apt-get install -y -qq --no-install-recommends wkhtmltopdf >/dev/null 2>&1 \
    || echo "Note: wkhtmltopdf is not available from apt, so PDF reports won't work."

log "Starting PostgreSQL in Docker"
"$REPO/scripts/start-postgres.sh"
published="$(docker compose -f "$REPO/docker-compose.yml" port db 5432)"
pg_port="${published##*:}"

mkdir -p "$NATIVE"

log "Getting Odoo $ODOO_BRANCH source"
if [ -d "$NATIVE/odoo/.git" ]; then
    git -C "$NATIVE/odoo" pull --quiet --ff-only
else
    git clone --quiet --depth 1 --branch "$ODOO_BRANCH" https://github.com/odoo/odoo.git "$NATIVE/odoo"
fi

log "Creating the Python environment"
if [ ! -x "$NATIVE/venv/bin/python" ]; then
    if python3 -c 'import sys; sys.exit(not (3, 12) <= sys.version_info[:2] < (3, 15))' 2>/dev/null; then
        as_root -E apt-get install -y -qq python3-dev python3-venv >/dev/null
        python3 -m venv "$NATIVE/venv"
    else
        # This release's Python is too old. Fetch 3.12 into .native/ and leave the system's alone.
        echo "System Python is older than 3.12, so downloading Python 3.12 into .native/"
        curl -fsSL https://astral.sh/uv/install.sh \
            | env UV_INSTALL_DIR="$NATIVE/uv" UV_NO_MODIFY_PATH=1 sh >/dev/null
        UV_PYTHON_INSTALL_DIR="$NATIVE/python" "$NATIVE/uv/uv" venv --quiet --seed --python 3.12 "$NATIVE/venv"
    fi
fi
"$NATIVE/venv/bin/python" -m pip install --quiet --upgrade pip
"$NATIVE/venv/bin/python" -m pip install --quiet -r "$NATIVE/odoo/requirements.txt"

if [ ! -f "$CONF" ]; then
    log "Writing $CONF"
    (umask 077; cat > "$CONF" <<EOF
[options]
addons_path = $NATIVE/odoo/addons,$REPO/addons
data_dir = $NATIVE/data
db_host = 127.0.0.1
db_port = $pg_port
db_user = odoo
db_password = odoo
admin_passwd = $(openssl rand -hex 16)
; Change to 0.0.0.0 to accept connections from other computers.
http_interface = 127.0.0.1
http_port = 8069
dev_mode = xml
EOF
    )
else
    # DB_PORT in .env may have changed since the last run.
    sed -i "s/^db_port = .*/db_port = $pg_port/" "$CONF"
fi

printf '\nDone. Next, start Odoo:\n    scripts/odoo-native.sh\n'
printf 'Then open http://localhost:8069. The master password is admin_passwd in %s\n' "$CONF"
