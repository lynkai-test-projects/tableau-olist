# tableau-olist

Automation + assets for putting the Olist dbt marts (`OLIST.DBT_DEMO` in Snowflake)
onto a **Tableau** executive dashboard — the BI layer on top of the
[`dbt-olist`](https://github.com/lynkai-test-projects/dbt-olist) project and the
Lynk semantic layer in `olist-demo`.

> **Not a "Tableau pulls from git" integration.** Tableau does not read this repo.
> This is plain version control for the automation code + the workbook, which is
> pushed to Tableau Cloud via the REST API (`publish/`). The dashboard embeds a
> **`.hyper` extract** (a point-in-time snapshot of the marts) — no live Snowflake
> connection, so nothing to authenticate from Tableau and nothing that can break
> at view time.

## What it builds — "Olist Marketplace Overview"

A CEO / head-of-finance overview, Lynk-branded (purple `#6749F4`):

- **KPI tiles**: Total GMV (R$), Orders, Customers, Avg Review
- **GMV by Month** — the growth trend across the ~2 years of data
- **GMV by Customer State** — geographic concentration (São Paulo dominates)
- **Late Rate by Distance** — late-delivery rate rises with seller→customer distance
- **Orders by Season** — Southern-Hemisphere seasonality (Autumn peak)

Every panel aggregates a single embedded order-level table, so the workbook has
one datasource and is easy to extend.

## Contents
| Path | Purpose |
|------|---------|
| `publish/build_extract.py` | Query `OLIST.DBT_DEMO` + curated views → one order-level `.hyper` extract |
| `publish/build_workbook.py` | Generate the `.twb` XML and package `workbooks/olist_overview.twbx` |
| `publish/publish_workbook.py` | Sign in with a PAT, publish the `.twbx`, and export a PNG/PDF preview (raw REST — no `tableauserverclient` needed) |
| `publish/config.example.toml` | Copy to `config.toml` and edit site/project/workbook |
| `workbooks/olist_overview.twbx` | The built workbook (packaged `.twb` + `.hyper`) |
| `build/` | Intermediate `.hyper` + exported previews (gitignored) |

## Rebuild + publish
```bash
pip install -r publish/requirements.txt      # tableauhyperapi
cp publish/config.example.toml publish/config.toml   # edit if needed

# 1) snapshot the marts into a .hyper (key-pair Snowflake auth)
python publish/build_extract.py

# 2) generate + package the workbook
python publish/build_workbook.py build/olist_orders.hyper workbooks/olist_overview.twbx

# 3) publish to Tableau Cloud + export a preview PNG
export TABLEAU_PAT_NAME=...          # never commit the PAT
export TABLEAU_PAT_SECRET=...
python publish/publish_workbook.py
```

## Notes
- **Snowflake auth for the extract** uses key-pair (the same key the Snowflake MCP
  uses); it only needs `SELECT` on `OLIST.DBT_DEMO` + the `OLIST.PUBLIC` `V_*` views.
- The corporate proxy MITM-intercepts TLS, so both scripts point OpenSSL at the
  combined CA bundle (`win_ca_bundle.pem`); override with `SNOWFLAKE_CA_BUNDLE` /
  `TABLEAU_CA_BUNDLE` if yours lives elsewhere.
- To refresh the dashboard after a mart change: re-run steps 1→3.
- Teammates collaborate on the **code** here via GitHub; editing in the Tableau
  site itself depends on Tableau licensing.
