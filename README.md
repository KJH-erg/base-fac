# Odoo 20 addon base

Local Odoo 20 Community + PostgreSQL 16 in Docker. Everything you write goes in `addons/`; Odoo itself comes from the `odoo:20.0` image.

You need Docker with Compose v2, and it must be running: [Docker Desktop](https://www.docker.com/products/docker-desktop/) on macOS or Windows, or Docker Engine on Linux (see [Linux notes](#linux-notes)).

## Start the server

```bash
docker compose up -d
```

Open http://localhost:8069 and create a database. The master password is `admin` (see `config/odoo.conf`). The email and password you enter on that page become your login.

If port 8069 is taken, for example by another Odoo project, run `cp .env.example .env`, change `ODOO_PORT`, and start again.

To stop the server:

```bash
docker compose down
```

This keeps your data. Adding `-v` also deletes all databases and uploaded files.

## Add an addon

### 1. Create it

Every folder in `addons/` that has a `__manifest__.py` is an addon. Generate one:

```bash
docker compose exec --user "$(id -u):$(id -g)" odoo odoo scaffold my_addon /mnt/extra-addons
chmod -R go-w addons/my_addon
```

The `--user` part makes the new files yours. Without it, Linux refuses with `PermissionError`, because Odoo runs as a different user inside the container. The `chmod` removes the world-write permission scaffold gives its files.

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

Replace `mydb` with your database name.

```bash
docker compose run --rm odoo odoo -d mydb -i my_addon --stop-after-init --no-http
docker compose restart odoo
```

To install from the browser instead, turn on developer mode (add `?debug=1` to the URL), open **Apps → Update Apps List**, then search for the addon. Remove the default `Apps` filter to see addons that aren't marked as applications.

### 4. Apply your changes

| What changed | What to do |
|---|---|
| XML views | Refresh the browser (`dev_mode = xml`) |
| Python method bodies | `docker compose restart odoo` |
| Model fields, data files, access rights, manifest | Upgrade, then restart (below) |
| JavaScript or other assets | Refresh the browser, with an upgrade if you added a new file |

```bash
docker compose run --rm odoo odoo -d mydb -u my_addon --stop-after-init --no-http
docker compose restart odoo
```

## Other commands

```bash
# Run one addon's tests in a throwaway database
docker compose run --rm odoo odoo -d test_my_addon -i my_addon --test-enable --test-tags /my_addon --stop-after-init --no-http
docker compose exec db dropdb -U odoo test_my_addon

# Follow the server log
docker compose logs -f odoo

# Open an interactive ORM shell
docker compose run --rm odoo odoo shell -d mydb --no-http
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

Install all five. Dependencies such as `mrp` come along automatically:

```bash
docker compose run --rm odoo odoo -d mydb -i mes_kpi,mes_lot_trace --stop-after-init --no-http
docker compose restart odoo
```

Users need a Manufacturing role to see the MES menu. **User** can create and edit plans and results; **Administrator** can also edit routings and delete records.

### Korean

All five addons include Korean translations in `i18n/ko.po`. They load automatically once Korean is active in the database. To activate it from the command line:

```bash
docker compose run --rm odoo odoo -d mydb --load-language=ko_KR --stop-after-init --no-http
docker compose restart odoo
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

## Linux notes

Check that Docker works without `sudo` and that Compose v2 is installed:

```bash
docker compose version
docker ps
```

| Problem | Fix |
|---|---|
| `docker: 'compose' is not a docker command` | Install the Compose plugin: `docker-compose-plugin` from Docker's own repository, or `docker-compose-v2` from Ubuntu's |
| `permission denied` on `/var/run/docker.sock` | Run `sudo usermod -aG docker $USER`, then log out and back in |
| `grep: /etc/odoo/odoo.conf: Permission denied`, or addons missing from Odoo | Odoo must be able to read your files. Run `chmod -R a+rX addons config` once. This happens when you clone with a strict `umask` such as `077`. |
| `localhost:8069` doesn't open from another computer | The port only listens on the server itself. Use an SSH tunnel: `ssh -L 8069:localhost:8069 user@server`, then open http://localhost:8069 on your own computer. |

## Not for production

The passwords here are throwaway and the port only listens on localhost. Change `admin_passwd` and the database credentials, and remove `dev_mode`, before deploying this anywhere.
