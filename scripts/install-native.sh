#!/usr/bin/env bash
# Installs Odoo 20 on a Linux host without root, with PostgreSQL in Docker.
# Follows the pip route of https://www.odoo.com/documentation/20.0/administration/on_premise/source.html
# Odoo's source, Python and its packages all go in .native/ in this repo. Safe to run again.
set -euo pipefail

ODOO_BRANCH=20.0
PYTHON_VERSION=3.12

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NATIVE="$REPO/.native"
CONF="$NATIVE/odoo.conf"

log() { printf '\n==> %s\n' "$*"; }
die() { printf 'Error: %s\n' "$*" >&2; exit 1; }

for tool in curl git; do
    command -v "$tool" >/dev/null || die "$tool is required. Ask your administrator to install it."
done
docker compose version >/dev/null 2>&1 || die "Docker with Compose v2 is required for PostgreSQL."
docker ps >/dev/null 2>&1 || die "can't talk to Docker. Check that it's running and that your user can use it."
# Some of Odoo's pinned packages only come prebuilt for x86_64.
[ "$(uname -m)" = x86_64 ] || command -v cc >/dev/null || die "on $(uname -m), a C compiler and python3-dev are required."

log "Starting PostgreSQL in Docker"
"$REPO/scripts/start-postgres.sh"
published="$(docker compose -f "$REPO/docker-compose.yml" port db 5432)"
pg_host="${published%:*}"
pg_port="${published##*:}"

mkdir -p "$NATIVE"

log "Getting Odoo $ODOO_BRANCH source"
if [ -d "$NATIVE/odoo/.git" ]; then
    git -C "$NATIVE/odoo" pull --quiet --ff-only
else
    git clone --quiet --depth 1 --branch "$ODOO_BRANCH" --single-branch https://github.com/odoo/odoo.git "$NATIVE/odoo"
fi

log "Creating the Python environment"
if [ ! -x "$NATIVE/venv/bin/python" ]; then
    # Doesn't rely on the system's Python, which may be too old or missing venv support.
    curl -fsSL https://astral.sh/uv/install.sh \
        | env UV_INSTALL_DIR="$NATIVE/uv" UV_NO_MODIFY_PATH=1 sh >/dev/null
    UV_PYTHON_INSTALL_DIR="$NATIVE/python" "$NATIVE/uv/uv" venv --quiet --seed --python "$PYTHON_VERSION" "$NATIVE/venv"
fi

log "Installing Odoo's Python packages"
# Without root there are no build libraries, so use the prebuilt psycopg2 and drop the LDAP
# client, which only auth_ldap needs. tzdata covers hosts without system time zone data.
sed -e 's/^psycopg2==/psycopg2-binary==/' -e '/^python-ldap==/d' "$NATIVE/odoo/requirements.txt" > "$NATIVE/requirements.txt"
echo tzdata >> "$NATIVE/requirements.txt"
"$NATIVE/venv/bin/python" -m pip install --quiet --upgrade pip
"$NATIVE/venv/bin/python" -m pip install --quiet -r "$NATIVE/requirements.txt"

# The database may be reachable by others on a shared network, so it gets a real password.
db_password="$(awk -F' = ' '$1 == "db_password" { print $2 }' "$CONF" 2>/dev/null || true)"
[ -n "$db_password" ] || db_password="$("$NATIVE/venv/bin/python" -c 'import secrets; print(secrets.token_hex(16))')"
# Sent on stdin so it doesn't show up in the host's process list.
echo "ALTER USER odoo PASSWORD '$db_password'" \
    | docker compose -f "$REPO/docker-compose.yml" exec -T db psql -q -U odoo -d postgres

if [ ! -f "$CONF" ]; then
    log "Writing $CONF"
    admin_passwd="$("$NATIVE/venv/bin/python" -c 'import secrets; print(secrets.token_hex(16))')"
    (umask 077; cat > "$CONF" <<EOF
[options]
addons_path = $NATIVE/odoo/addons,$REPO/addons
data_dir = $NATIVE/data
db_host = $pg_host
db_port = $pg_port
db_user = odoo
db_password = $db_password
admin_passwd = $admin_passwd
; Change to 0.0.0.0 to accept connections from other computers.
http_interface = 127.0.0.1
http_port = 8069
dev_mode = xml
EOF
    )
else
    # DB_BIND or DB_PORT in .env may have changed since the last run.
    sed -i -e "s/^db_host = .*/db_host = $pg_host/" -e "s/^db_port = .*/db_port = $pg_port/" "$CONF"
fi

printf '\nDone. Next, start Odoo:\n    scripts/odoo-native.sh\n'
printf 'Then open http://localhost:8069. The master password is admin_passwd in %s\n' "$CONF"
