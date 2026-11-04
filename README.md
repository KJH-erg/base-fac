# Odoo 20 addon base

Odoo 20 Community running directly on a Linux machine, with PostgreSQL 16 in Docker. Everything you write goes in `addons/`. You don't need `sudo` or root.

You need `git`, `curl`, and Docker with Compose v2. Check that Docker works for your user:

```bash
docker compose version
docker ps
```

## Install

```bash
scripts/install-native.sh
```

This follows the pip route of Odoo's [source install guide](https://www.odoo.com/documentation/20.0/administration/on_premise/source.html), except that PostgreSQL runs in Docker. It's safe to run again.

- **Odoo's source, Python 3.12, its packages and uploaded files** all go in `.native/` in this repo, which git ignores. Nothing is installed system-wide.
- **PostgreSQL** runs in the `db` container, published on `127.0.0.1:5433`. If that port is taken, run `cp .env.example .env`, change `DB_PORT`, and run the install again.

Installing without root leaves out a few things:

- **PDF reports:** these need wkhtmltopdf, which isn't installed. Ask your administrator for version 0.12.6 if you need them.
- **Backups:** the database manager's backup and restore need PostgreSQL's client tools on the host. Use this instead, which saves the database but not uploaded files in `.native/data`:

  ```bash
  docker compose exec -T db pg_dump -U odoo mydb > mydb.sql
  ```

- **LDAP login:** the `auth_ldap` addon won't work, because its Python package needs system libraries.

## Start the server

```bash
scripts/odoo-native.sh
```

This also starts the `db` container if needed. Press `Ctrl+C` to stop Odoo. It also stops when you close the terminal, so use `tmux` or `screen` to keep it running after you log out.

Open http://localhost:8069 and create a database. The master password is `admin_passwd` in `.native/odoo.conf`, generated randomly for your install. The email and password you enter on that page become your login.

**From another computer:** Odoo only listens on the server itself, so use an SSH tunnel from your computer, then open http://localhost:8069 there:

```bash
ssh -L 8069:localhost:8069 user@server
```

The tunnel needs SSH access to the machine Odoo runs on. If your shell is inside a container whose port 8069 isn't published, nothing outside can reach it: publish the port in the platform's settings, or run this on the real host.

To stop PostgreSQL:

```bash
docker compose down
```

This keeps your data. Adding `-v` also deletes all databases.

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
docker compose exec db dropdb -U odoo test_my_addon

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
| `docker: 'compose' is not a docker command` | Install the Compose plugin: `docker-compose-plugin` from Docker's own repository, or `docker-compose-v2` from Ubuntu's |
| `permission denied` on `/var/run/docker.sock` | Run `sudo usermod -aG docker $USER`, then log out and back in |
| `this shell can't reach it at 127.0.0.1:5433` | Docker publishes that port where its daemon runs. If your shell is in a container using another machine's Docker, Odoo can't reach the database at that address. |
| `localhost:8069` doesn't open from another computer | Use the SSH tunnel under [Start the server](#start-the-server) |

## Not for production

The passwords here are throwaway and the ports only listen on localhost. Change the database credentials and remove `dev_mode` before deploying this anywhere.
