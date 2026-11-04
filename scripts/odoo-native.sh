#!/usr/bin/env bash
# Runs the Odoo installed by install-native.sh. Takes the same arguments as odoo-bin.
#   scripts/odoo-native.sh                                Start the server
#   scripts/odoo-native.sh -d mydb -i my_addon --stop-after-init
#   scripts/odoo-native.sh shell -d mydb
#   scripts/odoo-native.sh scaffold my_addon addons
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NATIVE="$REPO/.native"
[ -f "$NATIVE/odoo.conf" ] || { echo "Run scripts/install-native.sh first." >&2; exit 1; }

# Odoo calls pg_dump and psql for database backups and restores.
export PATH="$NATIVE/pg/bin:$PATH"
odoo=("$NATIVE/venv/bin/python" "$NATIVE/odoo/odoo-bin")

case "${1:-}" in
    scaffold)
        exec "${odoo[@]}" "$@"
        ;;
    -*|"")
        "$REPO/scripts/start-postgres.sh"
        exec "${odoo[@]}" -c "$NATIVE/odoo.conf" "$@"
        ;;
    *)
        "$REPO/scripts/start-postgres.sh"
        subcommand="$1"; shift
        exec "${odoo[@]}" "$subcommand" -c "$NATIVE/odoo.conf" "$@"
        ;;
esac
