#!/usr/bin/env bash
# Installs Odoo 20 and PostgreSQL on a Linux host without root.
# Follows the pip route of https://www.odoo.com/documentation/20.0/administration/on_premise/source.html
# Odoo's source, Python, PostgreSQL and all data go in .native/ in this repo. Safe to run again.
set -euo pipefail

ODOO_BRANCH=20.0
PYTHON_VERSION=3.12
POSTGRES_VERSION=16

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NATIVE="$REPO/.native"
CONF="$NATIVE/odoo.conf"

log() { printf '\n==> %s\n' "$*"; }
die() { printf 'Error: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -ne 0 ] || die "run this as a normal user, because PostgreSQL refuses to run as root."
for tool in conda curl git; do
    command -v "$tool" >/dev/null || die "$tool is required. Ask your administrator to install it."
done
# Some of Odoo's pinned packages only come prebuilt for x86_64.
[ "$(uname -m)" = x86_64 ] || command -v cc >/dev/null || die "on $(uname -m), a C compiler and python3-dev are required."

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

log "Setting up PostgreSQL $POSTGRES_VERSION"
if [ ! -x "$NATIVE/pg/bin/pg_ctl" ]; then
    conda create --quiet --yes --prefix "$NATIVE/pg" --override-channels -c conda-forge "postgresql=$POSTGRES_VERSION" >/dev/null
fi
if [ ! -f "$NATIVE/pgdata/PG_VERSION" ]; then
    "$NATIVE/pg/bin/initdb" -D "$NATIVE/pgdata" -U odoo -E UTF8 --locale=C --auth-local=trust --auth-host=reject >/dev/null
    # Unix socket only, in a folder only you can open, so nobody else on the machine can connect.
    install -d -m 700 "$NATIVE/run"
    cat >> "$NATIVE/pgdata/postgresql.conf" <<EOF
listen_addresses = ''
unix_socket_directories = '$NATIVE/run'
unix_socket_permissions = 0700
EOF
fi
"$REPO/scripts/start-postgres.sh"

if [ ! -f "$CONF" ]; then
    log "Writing $CONF"
    admin_passwd="$("$NATIVE/venv/bin/python" -c 'import secrets; print(secrets.token_hex(16))')"
    (umask 077; cat > "$CONF" <<EOF
[options]
addons_path = $NATIVE/odoo/addons,$REPO/addons
data_dir = $NATIVE/data
db_host = $NATIVE/run
db_user = odoo
admin_passwd = $admin_passwd
; Change to 0.0.0.0 to accept connections from other computers.
http_interface = 127.0.0.1
http_port = 8069
dev_mode = xml
EOF
    )
fi

printf '\nDone. Next, start Odoo:\n    scripts/odoo-native.sh\n'
printf 'Then open http://localhost:8069. The master password is admin_passwd in %s\n' "$CONF"
