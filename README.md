# tableau-olist

Automation + assets for a **four-dashboard Tableau workbook** — "Olist Marketplace Analytics" —
built on the Olist dbt marts (`OLIST.DBT_DEMO` in Snowflake). The BI layer on top of the
[`dbt-olist`](https://github.com/lynkai-test-projects/dbt-olist) project and the Lynk semantic
layer in `olist-demo`.

> **Not a "Tableau pulls from git" integration.** Tableau does not read this repo. This is plain
> version control for the automation code + the workbook, which is pushed to Tableau Cloud via the
> REST API (`publish/`). The dashboards embed a **`.hyper` extract** (a point-in-time snapshot of
> the marts) — no live Snowflake connection, so nothing to authenticate at view time.

Every panel visualizes a metric that is **also governed in the Lynk semantic layer**, so the
dashboard and Lynk Ask reconcile on the same definitions (delivered-only GMV, gross margin on
product revenue, conversion from the synthetic clickstream, etc.). That's the demo story: *your
dbt models + your Tableau dashboards, one governed semantic layer, everything agrees.*

## The four dashboards
| Dashboard | Panels | Datasource tables |
|-----------|--------|-------------------|
| **Executive Overview** | 6 KPIs (GMV, Gross Margin %, Orders, AOV, Avg Review, Conversion), GMV trend, GMV by category (treemap), GMV by state | Orders, MonthlyTrend, Category, FunnelDaily |
| **Growth & Funnel** | page-view → purchase funnel, conversion by device, conversion by traffic source, conversion trend | FunnelSteps, FunnelDaily |
| **Delivery Operations** | late rate by shipping distance, review score by delay bucket, late-rate trend | Orders |
| **Seller & Customer 360** | seller quality scatter, cohort-retention heatmap, customers by value segment, GMV by seller state | Sellers, Cohort, CustomerSeg |

Headline (live to the reveal date): **R$13.8M delivered GMV · 86k orders · R$160 AOV · 34% gross
margin · 13-day avg delivery · ~4.6% session→purchase**. Synthetic funnel / margin panels are
footnoted on each dashboard.

## Contents
| Path | Purpose |
|------|---------|
| `publish/build_extract.py` | Query `OLIST.DBT_DEMO` marts → one `.hyper` with 8 grain-aligned tables |
| `publish/build_workbook.py` | Generate the `.twb` XML (4 dashboards, 20 worksheets, 8 datasources) and package `workbooks/olist_marketplace.twbx` |
| `publish/publish_workbook.py` | Sign in with a PAT, publish the `.twbx` (raw REST — no `tableauserverclient`) |
| `publish/export_dashboard.py` | Export the live dashboards → PNG gallery + `index.html` for GitHub Pages |
| `publish/config.example.toml` | Copy to `config.toml` and edit site/project/workbook |
| `docs/tableau_extension_prompts.md` | Prompts for the Tableau Cloud **Chrome extension** — UI polish + build-from-scratch fallback |
| `workbooks/olist_marketplace.twbx` | The built workbook (packaged `.twb` + `.hyper`) |

## Rebuild + publish
```bash
pip install -r publish/requirements.txt          # tableauhyperapi, snowflake-connector-python
cp publish/config.example.toml publish/config.toml   # edit if needed

# 1) snapshot the marts into a .hyper (key-pair Snowflake auth)
python publish/build_extract.py                  # -> build/olist_marketplace.hyper

# 2) generate + package the workbook (validates the XML, then zips the .twbx)
python publish/build_workbook.py build/olist_marketplace.hyper workbooks/olist_marketplace.twbx

# 3) publish to Tableau Cloud
export TABLEAU_PAT_NAME=...        # never commit the PAT
export TABLEAU_PAT_SECRET=...
python publish/publish_workbook.py
```

The generator produces a **complete, well-formed, referentially-consistent** workbook (XML is
validated and every dashboard zone / window / datasource reference is checked). Final visual
polish — tooltip wording, dual-axis GMV+margin, color legends, mark sizing — is easiest in the
Tableau UI; `docs/tableau_extension_prompts.md` has copy-paste prompts for the Chrome extension.

## Public dashboards on GitHub Pages (auto-deploy)
`.github/workflows/deploy-pages.yml` exports whatever is **live on Tableau Cloud** via
`publish/export_dashboard.py` into a PNG gallery and publishes it to GitHub Pages
(`https://lynkai-test-projects.github.io/tableau-olist/`) on relevant pushes, **nightly** (to
catch UI edits), and on demand. See the workflow header for one-time setup (public repo, Pages
source = GitHub Actions, repo secrets `TABLEAU_PAT_NAME` / `TABLEAU_PAT_SECRET`).

## Notes
- **Snowflake auth for the extract** uses key-pair (same key the Snowflake MCP uses); needs
  `SELECT` on `OLIST.DBT_DEMO`. Run `dbt build` in `dbt-olist` first if the marts changed.
- The corporate proxy MITM-intercepts TLS, so `build_extract.py` points OpenSSL at the combined
  CA bundle (`win_ca_bundle.pem`); override with `SNOWFLAKE_CA_BUNDLE` / `TABLEAU_CA_BUNDLE`.
- To refresh after a mart change: re-run steps 1→3, then the Pages deploy picks it up.
