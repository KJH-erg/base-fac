# Odoo 20 addon base

Odoo 20 Community and PostgreSQL 16 running directly on a Linux machine, without Docker. Everything you write goes in `addons/`. You don't need `sudo` or root.

You need `git`, `curl` and `conda`.

## Install

```bash
scripts/install-native.sh
```

This follows the pip route of Odoo's [source install guide](https://www.odoo.com/documentation/20.0/administration/on_premise/source.html), with PostgreSQL from conda-forge. It's safe to run again.

- **Everything** goes in `.native/` in this repo, which git ignores: Odoo's source, Python 3.12, its packages, PostgreSQL, your databases and uploaded files. Nothing is installed system-wide.
- **PostgreSQL** only accepts connections through a private socket in `.native/run`, so nobody else on the machine can connect to it.

Installing without root leaves out two things:

- **PDF reports:** these need wkhtmltopdf, which isn't installed. Ask your administrator for version 0.12.6 if you need them.
- **LDAP login:** the `auth_ldap` addon won't work, because its Python package needs system libraries.

## Start the server

```bash
scripts/odoo-native.sh
```

This also starts PostgreSQL if needed. Press `Ctrl+C` to stop Odoo. It also stops when you close the terminal, so use `tmux` or `screen` to keep it running after you log out.

Odoo ignores the hangup signal that `tmux kill-session` sends, so killing the session leaves the server running and holding port 8069. Stop it by PID instead:

```bash
pkill -TERM -f "odoo-bi[n] -c"
```

The brackets keep the pattern from matching the `pkill` command itself.

Open http://localhost:8069 and create a database. The master password is `admin_passwd` in `.native/odoo.conf`, generated randomly for your install. The email and password you enter on that page become your login.

**From another computer:** Odoo only listens on the server itself, so use an SSH tunnel from your computer, then open http://localhost:8069 there:

```bash
ssh -L 8069:localhost:8069 user@server
```

The tunnel needs SSH access to the machine Odoo runs on, and `localhost` in that command means that machine, not your own. If Odoo runs inside a container, SSH to the container, not to its host: a tunnel to the host reaches the host's own port 8069, where nothing listens.

If you reach the container through VS Code's Remote-SSH, its **PORTS** panel forwards 8069 over the connection you already have, with no tunnel to set up. Failing both, set `http_interface` to `0.0.0.0` in `.native/odoo.conf` and reach the container on its own address. That also opens Odoo to anything that can route to it, so set a real password first if you share the machine.

PostgreSQL keeps running after Odoo stops. To stop it, which keeps your data:

```bash
.native/pg/bin/pg_ctl -D .native/pgdata stop
```

To back up a database, use the database manager at http://localhost:8069/web/database/manager.

## Add an addon

### 1. Create it

Every folder in `addons/` that has a `__manifest__.py` is an addon. Generate one:

```bash
scripts/odoo-native.sh scaffold my_addon addons
```

Or copy `addons/example_addon`, the smallest working reference, and rename the folder.

### 2. Fix what the scaffold gets wrong

`odoo scaffold` still generates files from older Odoo versions, and its sample code is commented out:

- **Model:** uncomment the class in `models/models.py`, or write your own. Its `_name` is what you put in `model_id` below. The scaffold's sample is named `my_addon.my_addon`.
- **Access rights:** Odoo 20 replaced `ir.model.access` with `ir.access`. Installing the old file fails with `KeyError: 'ir.model.access'`. Delete `security/ir.model.access.csv` and create `security/ir.access.csv`, with one row for each model:

  ```csv
  id,name,model_id,group_id/id,operation,domain
  access_my_addon_user,my.addon.user,my_addon.my_addon,base.group_user,crud,
  ```

  `operation` is any combination of the letters `c`, `r`, `u`, `d`.
- **Manifest:** in `__manifest__.py`, set `version` to `20.0.1.0.0`, and replace the commented `security/ir.model.access.csv` line under `data` with `'security/ir.access.csv',`.

### 3. Install it

Replace `mydb` with your database name, then restart the server.

```bash
scripts/odoo-native.sh -d mydb -i my_addon --stop-after-init --no-http
```

Installing through `-i` on a new database also creates the login `admin` / `admin`, so change it if others can reach the server.

To install from the browser instead, turn on developer mode (add `?debug=1` to the URL), open **Apps → Update Apps List**, then search for the addon. Remove the default `Apps` filter to see addons that aren't marked as applications.

### 4. Apply your changes

| What changed | What to do |
|---|---|
| XML views | Refresh the browser (`dev_mode = xml`) |
| Python method bodies | Restart the server |
| Model fields, data files, access rights, manifest | Upgrade, then restart (below) |
| JavaScript or other assets | Refresh the browser, with an upgrade if you added a new file |

```bash
scripts/odoo-native.sh -d mydb -u my_addon --stop-after-init --no-http
```

## Other commands

```bash
# Run one addon's tests in a throwaway database
scripts/odoo-native.sh -d test_my_addon -i my_addon --test-enable --test-tags /my_addon --stop-after-init --no-http
.native/pg/bin/dropdb -h "$PWD/.native/run" -U odoo test_my_addon

# Open an interactive ORM shell
scripts/odoo-native.sh shell -d mydb --no-http
```

## MES addons

Five addons built on Odoo's standard Manufacturing and Inventory apps. Lines are `mrp.workcenter` records, products are `product.product`, and lots are `stock.lot`.

| Addon | What it does | Menu |
|---|---|---|
| `mes_routing` | Reusable process routes: steps, lines, setup and cycle times. Can be applied to a BoM. | MES → Configuration → Routings |
| `mes_planning` | Production plans by day and line, with line load, deadline warnings, and manufacturing order creation. | MES → Operations → Production Plans |
| `mes_production_result` | Good and defect quantities and times by step and shift, compared with the plan. | MES → Operations → Production Results |
| `mes_lot_trace` | Traces a lot backward to its sources and forward to what it went into. | MES → Operations → Lot Trace |
| `mes_kpi` | OEE, plan achievement, defect rate and downtime by line and period. | MES → Reporting |

Install all five, then restart the server. Dependencies such as `mrp` come along automatically:

```bash
scripts/odoo-native.sh -d mydb -i mes_kpi,mes_lot_trace --stop-after-init --no-http
```

Users need a Manufacturing role to see the MES menu. **User** can create and edit plans and results; **Administrator** can also edit routings and delete records.

### Korean

All five addons include Korean translations in `i18n/ko.po`. They load automatically once Korean is active in the database. To activate it from the command line, then restart the server:

```bash
scripts/odoo-native.sh -d mydb --load-language=ko_KR --stop-after-init --no-http
```

Then click your avatar (top right), open **My Preferences** (내 추가 설정), and choose Korean as your language.

After editing a `ko.po` file, upgrade the addon with `-u` to reload it. Labels on the dashboard come from the browser's translation cache, so hard-refresh the page if they don't change.

### How the numbers work

- **Output:** when a plan has a routing, only results on the routing's last step count as finished output, so a unit isn't counted once per step. Defects count at every step.
- **Availability:** run minutes ÷ elapsed minutes. Downtime is what operators enter on results; Odoo's work order time logs aren't included.
- **Performance:** standard minutes ÷ run minutes. It only covers results with a step, because the standard time comes from the step, and it can exceed 100%.
- **Quality:** good quantity ÷ (good + defect).
- **OEE:** availability × performance × quality. It shows `—` until results with a step exist.
- **Dashboard ratios:** calculated from summed quantities, not by averaging daily percentages.
- **Plan and result status:** only confirmed plans and confirmed results count in KPIs.

### Limits

- Lot trace follows completed manufacturing orders only. A component without lot tracking ends the chain, and enabling lot tracking is a per-product setting in Odoo.
- Applying a routing to a BoM copies cycle times only, because Odoo has no setup time per operation. Setup time is still used for line load.
- Line capacity comes from the line's working calendar (`hours_per_day`). A plan without a routing adds no load.

## Troubleshooting

| Problem | Fix |
|---|---|
| Odoo is running but nothing answers on 8069 | It can't bind the port, usually because an older Odoo still holds it. Odoo logs this as `CRITICAL` and `Address already in use`, drops only its HTTP thread, and keeps running its cron threads, so the process looks healthy while it serves nothing. A healthy start logs `HTTP service running on …:8069`; search Odoo's output for that line and for `Address already in use`. Then stop every instance with the `pkill` above and start one. |
| `could not translate host name ".native/run" to address` | `db_host` has to be an absolute path for PostgreSQL to read it as a socket directory. Pass the full path to `psql -h`. |
| The install finishes but Odoo uses the wrong database | Older installs kept their own `.native/odoo.conf`. The install rewrites `db_host` in place now; if yours still points elsewhere, delete the file and install again to get a fresh one. |

## Not for production

This setup is for development. Remove `dev_mode` and add proper backups before deploying this anywhere.
