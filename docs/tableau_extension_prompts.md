# Tableau Cloud Chrome-extension prompts — Olist Marketplace Analytics

Copy-paste prompts for driving the Tableau Cloud **Chrome extension** (the AI agent that operates
the Tableau web-authoring UI). Two tracks:

- **Track A — Polish** the workbook that `build_workbook.py` already generated and
  `publish_workbook.py` pushed to Cloud. This is the recommended path.
- **Track B — Build from scratch** in the UI (fallback, if you'd rather not run the Python
  generator, or a panel needs a rebuild).

Everything below uses the **governed Lynk metric definitions** so the dashboard reconciles with
Lynk Ask. Brand color is **Lynk purple `#6749F4`**; secondary ink `#171717`; muted `#78737D`.

The published workbook is **Olist Marketplace Analytics** with four dashboards: *Executive
Overview*, *Growth & Funnel*, *Delivery Operations*, *Seller & Customer 360*. Its datasources are
hyper tables named `Orders`, `MonthlyTrend`, `Category`, `FunnelSteps`, `FunnelDaily`, `Sellers`,
`Cohort`, `CustomerSeg` (captions "Olist Orders (dbt)", etc.).

> **Metric definitions to embed in tooltips / captions** (match Lynk exactly):
> - **GMV** = SUM(price + freight) on **delivered** orders (BRL). ~R$13.8M.
> - **Gross Margin %** = SUM(price − cost) / SUM(price) — *cost is SYNTHETIC/illustrative*. ~34%.
> - **AOV** = GMV / distinct delivered orders. ~R$160.
> - **Late-Delivery Rate** = delivered orders arriving after the estimated date ÷ delivered orders.
> - **Conversion %** = sessions ending in purchase ÷ all sessions — *SYNTHETIC clickstream*. ~4.6%.
> - **Repeat rate** = customers with >1 delivered order (~3% — acquisition-heavy marketplace).
> - Money is BRL (R$); reviews are 1–5; rates are shown 0–100%.

---

## Track A — Polish the generated workbook

### A0. Global branding (run once)
> Open the workbook **Olist Marketplace Analytics**. Set a consistent theme across all four
> dashboards: title bars filled Lynk purple `#6749F4` with white bold text; all single-color bar
> and line marks use `#6749F4`; worksheet titles hidden except where noted; gridlines light gray
> `#E5E5E5`; font Tableau Book. Format all BRL measures as `R$ #,##0` and all percentage measures
> with one decimal and a `%` suffix. Do not multiply rate fields by 100 — they are already 0–100.

### A1. Executive Overview
> On the **Executive Overview** dashboard: arrange the six KPI tiles (Total GMV, Gross Margin,
> Orders, AOV, Avg Review, Conversion) in a single row of equal-width cards with a small gray
> caption above each big purple number. Under them, make **GMV Trend** a full-width line; add a
> light reference band for the current partial month and a tooltip "Delivered GMV, R$". Put **GMV
> by Category** (treemap) and **GMV by State** (bar, sorted desc) side by side below. Add a footer
> note: "Delivered-only GMV · gross margin on product revenue (COGS synthetic) · governed by the
> Lynk semantic layer." For the GMV Trend, add a dual axis showing **Gross Margin %** as a thin
> secondary line so growth and profitability read together.

### A2. Growth & Funnel
> On **Growth & Funnel**: make **Funnel** a horizontal bar sorted by step order (Sessions →
> Product view → Add to cart → Purchase) with data labels showing the count and the step-to-step
> drop-off %. Place **Conversion by Device** and **Conversion by Source** as sorted bars on the
> right, and **Conversion Trend** as a line below them. Add a prominent disclosure banner:
> "SYNTHETIC clickstream (session_event) — illustrative funnel." Color the funnel bars in a purple
> sequential ramp so the drop-off is visually obvious.

### A3. Delivery Operations
> On **Delivery Operations**: **Late Rate by Distance** as bars ordered 0-50km → 1000km+ (color
> ink `#171717`), **Review by Delay** as bars ordered on_time → late_>7d with the average review
> score labeled, and **Late Rate Trend** as a full-width line below. Add a callout text box:
> "Late deliveries and low review scores both rise with seller→customer distance — the headline
> operations insight." Format late rate as a percentage.

### A4. Seller & Customer 360
> On **Seller & Customer 360**: **Seller Scatter** — x = Avg Delivery Days, y = Avg Review, size =
> Seller GMV, color = Late Rate (diverging, purple=low/red=high); add a tooltip with seller state
> and category. **Cohort Retention** — a heatmap with cohort month on rows, months-since on
> columns, cells colored by Retention % (purple sequential) with the % labeled. **Customers by
> Segment** — bars for high/mid/low value. **GMV by Seller State** — sorted bars. Footer:
> "Sellers with ≥10 orders · ~3% of customers reorder, so month-0 retention is 100% by design."

---

## Track B — Build a panel from scratch (fallback)

Use these if a specific worksheet needs rebuilding. Connect to the published datasource named in
each prompt (they already exist in the workbook), then:

> **GMV Trend** — Using "Olist Monthly (dbt)": put `ORDER_MONTH` (continuous month) on Columns and
> `SUM(GMV_BRL)` on Rows as a purple line. Filter `IS_COMPLETE_MONTH = 1` to drop the partial
> current month. Title "GMV by Month (delivered, R$)".

> **Funnel** — Using "Olist Funnel Steps (dbt)": `STEP_NAME` on Rows sorted ascending by
> `AVG(STEP_ORDER)`, `SUM(SESSIONS)` on Columns as horizontal bars. Label each bar with its value.
> Title "Acquisition funnel (synthetic)".

> **Conversion by Device** — Using "Olist Funnel Daily (dbt)": create a calc
> `Conversion % = SUM([PURCHASE_SESSIONS]) / SUM([SESSIONS])` formatted as a percentage. Put
> `DEVICE_TYPE` on Rows, the calc on Columns as bars sorted desc.

> **Late Rate by Distance** — Using "Olist Orders (dbt)": create `Late Rate = AVG([IS_LATE])`
> formatted p1%. Put `DISTANCE_BUCKET` on Rows sorted by `AVG(DISTANCE_ORDER)` ascending, the calc
> on Columns as bars (ink `#171717`).

> **Cohort Retention** — Using "Olist Cohorts (dbt)": `COHORT_MONTH` (discrete) on Rows,
> `MONTHS_SINCE` (discrete) on Columns, mark = Square, color and label = `SUM(RETENTION_PCT)`,
> purple sequential palette. Title "Monthly acquisition-cohort retention (%)".

> **Seller Scatter** — Using "Olist Sellers (dbt)": `AVG(AVG_DELIVERY_DAYS)` on Columns,
> `AVG(AVG_REVIEW_SCORE)` on Rows, `SELLER_ID` on Detail, `AVG(LATE_DELIVERY_RATE)` on Color,
> `SUM(GMV_BRL)` on Size, mark = Circle. Title "Seller quality (delivery vs. review)".

---

---

## Track C — One-shot polish pass (paste after publishing)

The generated `.twb` gets the data, layout, and branding right, but Tableau's server render
ignores number formats and mark-label settings expressed in the XML. This single prompt applies
the remaining visual polish in the UI (2-click operations for the extension):

> Open the workbook **Olist Marketplace Analytics** and apply this formatting across all four
> dashboards, then save:
>
> 1. **Number formats.** Format every GMV / AOV / revenue field as currency `R$ #,##0` (e.g.
>    `R$ 13,801,111`). Format **Gross Margin**, **Conversion %**, **Late-Delivery Rate**, and
>    **Retention %** as a number with one decimal and a trailing `%` (the values are already on a
>    0–100 scale, so do NOT multiply by 100 again — just add the `%` suffix). Apply these to the
>    KPI tiles, axis ticks, and tooltips.
> 2. **Treemap labels.** On **GMV by Category**, turn on mark labels showing the category name and
>    its GMV (`R$ #,##0`), white text, centered; hide labels that don't fit.
> 3. **Cohort heatmap.** On **Cohort Retention**, add a thin white cell border, show the Retention %
>    label inside each cell (0 decimals), and set the color to a purple sequential ramp from white
>    (0%) to `#6749F4` (100%). Optionally filter Months Since to 0–6 so the grid is compact.
> 4. **Bar value labels.** On **GMV by State**, **GMV by Seller State**, **Customers by Segment**,
>    **Conversion by Device**, and **Conversion by Source**, show the value at the end of each bar
>    (currency or `%` as appropriate).
> 5. **Tooltips.** Give every worksheet a clean tooltip that states the metric definition, e.g.
>    "Delivered GMV (product + freight), R$" or "Conversion = purchasing sessions / all sessions
>    (synthetic)".
>
> Keep the Lynk purple `#6749F4` theme and white background throughout.

---

## Notes
- The extension edits the **live Cloud** copy. To keep the git repo the source of truth, mirror
  any structural change back into `publish/build_workbook.py`; UI-only polish can live in Cloud
  and will be picked up by the nightly Pages export.
- If a generated worksheet fails to render, rebuild just that one with its Track B prompt — the
  datasource is already there, so it's a 30-second fix.
