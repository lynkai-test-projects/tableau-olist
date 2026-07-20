"""Assemble the "Olist Marketplace Analytics" .twbx — a FOUR-dashboard Tableau workbook —
from the multi-table .hyper extract (build_extract.py). Tableau has no headless authoring API,
so we hand-author the .twb XML. Lynk-branded (purple #6749F4 on white).

Every panel visualizes a metric that is also governed in the Lynk semantic layer, so the
dashboard and Lynk Ask reconcile on the same definitions (delivered-only GMV, gross margin on
product revenue, etc.). Synthetic funnel / margin panels are footnoted on each dashboard.

Dashboards:
  1. Executive Overview   — GMV / Gross Margin % / Orders / AOV / Avg Review / Conversion KPIs,
                            GMV trend, GMV by category (treemap), GMV by customer state.
  2. Growth & Funnel      — page-view -> purchase funnel, conversion by device & traffic source,
                            conversion trend. (SYNTHETIC clickstream.)
  3. Delivery Operations  — late rate by shipping distance, review score by delay bucket,
                            late-rate trend.
  4. Seller & Customer 360— seller quality scatter, cohort-retention heatmap, customers by value
                            segment, GMV by seller state.

Usage:  python publish/build_workbook.py <input.hyper> <output.twbx>
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

HYPER_REL = "Data/olist_marketplace.hyper"

ACCENT = "#6749F4"     # Lynk purple
INK = "#171717"
LABEL = "#78737D"
WHITE = "#FFFFFF"
GRIDLINE = "#E5E5E5"

BLANK_TITLE = ("<layout-options><title><formatted-text><run>&#160;</run>"
               "</formatted-text></title></layout-options>")

# ------------------------------------------------------------------ datasource column helpers
MONEY = "&quot;R$&quot;#,##0"


def _col(key, datatype, role, ttype, caption=None, fmt=None):
    cap = f" caption='{caption}'" if caption else ""
    f = f" default-format='{fmt}'" if fmt else ""
    return f"      <column datatype='{datatype}'{f}{cap} name='[{key}]' role='{role}' type='{ttype}' />"


def _map(key, rel):
    # The map VALUE is prefixed with the relation NAME (not the schema). With one table per
    # datasource the relation name is the hyper table name (Orders, MonthlyTrend, ...).
    return f"          <map key='[{key}]' value='[{rel}].[{key}]' />"


def datasource(dsname, hcname, table, caption, cols, extra=""):
    maps = "\n".join(_map(c[0], table) for c in cols)
    defs = "\n".join(_col(*c) for c in cols)
    return f"""    <datasource caption='{caption}' inline='true' name='{dsname}' version='18.1'>
      <connection class='federated'>
        <named-connections>
          <named-connection caption='{table.lower()}' name='{hcname}'>
            <connection class='hyper' dbname='{HYPER_REL}' default-settings='yes' schema='Extract' />
          </named-connection>
        </named-connections>
        <relation connection='{hcname}' name='{table}' table='[Extract].[{table}]' type='table' />
        <cols>
{maps}
        </cols>
      </connection>
{defs}
{extra}    </datasource>"""


# ------------------------------------------------------------------ dependency / instance helpers
_PFX = {"Sum": "sum", "Avg": "avg", "CountD": "ctd"}


def dmeas(col, deriv="Sum", datatype="real", caption=None, fmt=None):
    """measure column def + aggregated instance; returns (dep_xml, instance_token)."""
    inst = f"[{_PFX[deriv]}:{col}:qk]"
    if deriv == "CountD":
        cdef = f"<column datatype='string' name='[{col}]' role='dimension' type='nominal' />"
    else:
        cap = f" caption='{caption}'" if caption else ""
        f = f" default-format='{fmt}'" if fmt else ""
        cdef = f"<column datatype='{datatype}'{f}{cap} name='[{col}]' role='measure' type='quantitative' />"
    idef = f"<column-instance column='[{col}]' derivation='{deriv}' name='{inst}' pivot='key' type='quantitative' />"
    return cdef + "\n            " + idef, inst


def ddim(col, datatype="string", caption=None):
    inst = f"[none:{col}:nk]"
    cap = f" caption='{caption}'" if caption else ""
    cdef = f"<column datatype='{datatype}'{cap} name='[{col}]' role='dimension' type='nominal' />"
    idef = f"<column-instance column='[{col}]' derivation='None' name='{inst}' pivot='key' type='nominal' />"
    return cdef + "\n            " + idef, inst


def ddate(col, caption=None):
    """continuous date (for a trend axis)."""
    inst = f"[none:{col}:qk]"
    cap = f" caption='{caption}'" if caption else ""
    cdef = f"<column datatype='date'{cap} name='[{col}]' role='dimension' type='ordinal' />"
    idef = f"<column-instance column='[{col}]' derivation='None' name='{inst}' pivot='key' type='quantitative' />"
    return cdef + "\n            " + idef, inst


def ddisc(col, datatype="integer", caption=None):
    """discrete ordinal dimension (heatmap axes)."""
    inst = f"[none:{col}:ok]"
    cap = f" caption='{caption}'" if caption else ""
    cdef = f"<column datatype='{datatype}'{cap} name='[{col}]' role='dimension' type='ordinal' />"
    idef = f"<column-instance column='[{col}]' derivation='None' name='{inst}' pivot='key' type='ordinal' />"
    return cdef + "\n            " + idef, inst


# calculated fields (defined on their datasources, repeated in the worksheets that use them)
# Numeric calc fields (render in full on Text marks and on chart axes; string labels get
# clipped to the cell width, so we keep these numeric). Percentages are pre-scaled to 0-100
# and rounded; the tile captions carry the R$ / % units. Tableau's image export does not
# reliably apply a measure's default-format, so we round in the formula instead.
CALC = {
    "MARGIN_PCT": "<column caption='Gross Margin %' datatype='real' name='[MARGIN_PCT]' role='measure' type='quantitative'><calculation class='tableau' formula='ROUND(100 * SUM([GROSS_PROFIT_BRL]) / SUM([PRODUCT_REVENUE_BRL]), 1)' /></column>",
    "AOV": "<column caption='AOV (BRL)' datatype='real' name='[AOV]' role='measure' type='quantitative'><calculation class='tableau' formula='ROUND(SUM([GMV_BRL]) / COUNTD([ORDER_ID]), 0)' /></column>",
    "LATE_RATE": "<column caption='Late-Delivery Rate' datatype='real' name='[LATE_RATE]' role='measure' type='quantitative'><calculation class='tableau' formula='ROUND(100 * AVG([IS_LATE]), 1)' /></column>",
    "CONV": "<column caption='Conversion %' datatype='real' name='[CONV]' role='measure' type='quantitative'><calculation class='tableau' formula='ROUND(100 * SUM([PURCHASE_SESSIONS]) / SUM([SESSIONS]), 1)' /></column>",
}


def _indent(block):
    return "\n".join("            " + ln if ln.strip() else ln for ln in block.split("\n"))


# ------------------------------------------------------------------ worksheet builders
def enc(**kw):
    order = ["color", "size", "text", "lod"]
    inner = "".join(f"<{k} column='{kw[k]}' />" for k in order if k in kw)
    return f"<encodings>{inner}</encodings>" if inner else ""


def ws(name, ds, caption, deps, rows, cols, mark, encodings="", view_extra="", mark_color=None):
    style = "        <style />"
    if mark_color:
        style = (f"        <style><style-rule element='mark'>"
                 f"<format attr='mark-color' value='{mark_color}' /></style-rule></style>")
    return f"""    <worksheet name='{name}'>
      <table>
        <view>
          <datasources><datasource caption='{caption}' name='{ds}' /></datasources>
          <datasource-dependencies datasource='{ds}'>
            {deps}
          </datasource-dependencies>
{view_extra}        </view>
{style}
        <panes><pane selection-relaxation-option='selection-relaxation-allow'><view><breakdown value='auto' /></view><mark class='{mark}' />{encodings}</pane></panes>
        <rows>{rows}</rows>
        <cols>{cols}</cols>
      </table>
    </worksheet>
"""


def kpi(name, ds, caption, deps, ref):
    return f"""    <worksheet name='{name}'>
      {BLANK_TITLE}
      <table>
        <view>
          <datasources><datasource caption='{caption}' name='{ds}' /></datasources>
          <datasource-dependencies datasource='{ds}'>
            {deps}
          </datasource-dependencies>
        </view>
        <style><style-rule element='mark'><format attr='mark-color' value='{ACCENT}' /><format attr='font-size' value='24' /></style-rule></style>
        <panes><pane><view><breakdown value='auto' /></view><mark class='Text' /><encodings><text column='{ref}' /></encodings></pane></panes>
        <rows></rows>
        <cols></cols>
      </table>
    </worksheet>
"""


def sort(ds, dim_inst, meas_inst, direction="DESC"):
    return (f"          <sort class='computed' column='[{ds}].{dim_inst}' "
            f"direction='{direction}' using='[{ds}].{meas_inst}' />\n")


def complete_filter(ds):
    dep = ("<column datatype='integer' name='[IS_COMPLETE_MONTH]' role='dimension' type='ordinal' />\n"
           "            <column-instance column='[IS_COMPLETE_MONTH]' derivation='None' "
           "name='[none:IS_COMPLETE_MONTH:ok]' pivot='key' type='ordinal' />")
    filt = (f"          <filter class='categorical' column='[{ds}].[none:IS_COMPLETE_MONTH:ok]'>\n"
            f"            <groupfilter function='member' level='[none:IS_COMPLETE_MONTH:ok]' member='1' />\n"
            f"          </filter>\n")
    return dep, filt


def R(ds, tok):
    return f"[{ds}].{tok}"


def esc(s):
    """Escape an ampersand for use inside an XML attribute value (dashboard names)."""
    return s.replace("&", "&amp;")


# ================================================================== build the workbook
def build_twb() -> str:
    # ---- datasources -----------------------------------------------------------------
    orders_cols = [
        ("ORDER_ID", "string", "dimension", "nominal", None, None),
        ("ORDER_MONTH", "date", "dimension", "ordinal", "Order Month", None),
        ("ORDER_YEAR", "integer", "dimension", "ordinal", "Year", None),
        ("IS_COMPLETE_MONTH", "integer", "dimension", "ordinal", None, None),
        ("CUSTOMER_ID", "string", "dimension", "nominal", None, None),
        ("CUSTOMER_STATE", "string", "dimension", "nominal", "Customer State", None),
        ("PRIMARY_CATEGORY", "string", "dimension", "nominal", "Category", None),
        ("GMV_BRL", "real", "measure", "quantitative", "GMV (BRL)", MONEY),
        ("PRODUCT_REVENUE_BRL", "real", "measure", "quantitative", "Product Revenue (BRL)", MONEY),
        ("FREIGHT_BRL", "real", "measure", "quantitative", "Freight (BRL)", MONEY),
        ("COGS_BRL", "real", "measure", "quantitative", "COGS (BRL)", MONEY),
        ("GROSS_PROFIT_BRL", "real", "measure", "quantitative", "Gross Profit (BRL)", MONEY),
        ("REVIEW_SCORE", "real", "measure", "quantitative", "Review Score", "0.00"),
        ("IS_LATE", "integer", "measure", "quantitative", None, None),
        ("DELIVERY_DAYS", "real", "measure", "quantitative", "Delivery Days", "0.0"),
        ("DELAY_BUCKET", "string", "dimension", "nominal", "Delay Bucket", None),
        ("DISTANCE_KM", "real", "measure", "quantitative", "Distance (km)", "0.0"),
        ("DISTANCE_BUCKET", "string", "dimension", "nominal", "Distance Band", None),
        ("DISTANCE_ORDER", "integer", "measure", "quantitative", None, None),
        ("PAYMENT_TYPE", "string", "dimension", "nominal", "Payment Type", None),
        ("PAYMENT_INSTALLMENTS", "integer", "measure", "quantitative", "Installments", None),
        ("BRAZILIAN_SEASON", "string", "dimension", "nominal", "Season", None),
        ("IS_BLACK_FRIDAY", "integer", "measure", "quantitative", None, None),
    ]
    trend_cols = [
        ("ORDER_MONTH", "date", "dimension", "ordinal", "Order Month", None),
        ("ORDER_YEAR", "integer", "dimension", "ordinal", "Year", None),
        ("IS_COMPLETE_MONTH", "integer", "dimension", "ordinal", None, None),
        ("ORDERS", "integer", "measure", "quantitative", "Orders", None),
        ("CUSTOMERS", "integer", "measure", "quantitative", "Customers", None),
        ("GMV_BRL", "real", "measure", "quantitative", "GMV (BRL)", MONEY),
        ("PRODUCT_REVENUE_BRL", "real", "measure", "quantitative", "Product Revenue (BRL)", MONEY),
        ("GROSS_PROFIT_BRL", "real", "measure", "quantitative", "Gross Profit (BRL)", MONEY),
        ("GROSS_MARGIN_PCT", "real", "measure", "quantitative", "Gross Margin %", "0.0"),
        ("AOV_BRL", "real", "measure", "quantitative", "AOV (BRL)", MONEY),
        ("AVG_REVIEW_SCORE", "real", "measure", "quantitative", "Avg Review", "0.00"),
        ("LATE_RATE", "real", "measure", "quantitative", "Late Rate %", "0.0"),
    ]
    category_cols = [
        ("PRODUCT_CATEGORY", "string", "dimension", "nominal", "Category", None),
        ("ITEMS", "integer", "measure", "quantitative", "Items", None),
        ("ORDERS", "integer", "measure", "quantitative", "Orders", None),
        ("GMV_BRL", "real", "measure", "quantitative", "GMV (BRL)", MONEY),
        ("GROSS_PROFIT_BRL", "real", "measure", "quantitative", "Gross Profit (BRL)", MONEY),
        ("GROSS_MARGIN_PCT", "real", "measure", "quantitative", "Gross Margin %", "0.0"),
        ("AVG_ITEM_PRICE_BRL", "real", "measure", "quantitative", "Avg Item Price", MONEY),
    ]
    funnel_cols = [
        ("STEP_NAME", "string", "dimension", "nominal", "Funnel Step", None),
        ("STEP_ORDER", "integer", "measure", "quantitative", None, None),
        ("DEVICE_TYPE", "string", "dimension", "nominal", "Device", None),
        ("TRAFFIC_SOURCE", "string", "dimension", "nominal", "Traffic Source", None),
        ("SESSIONS", "integer", "measure", "quantitative", "Sessions", None),
    ]
    funneld_cols = [
        ("EVENT_DATE", "date", "dimension", "ordinal", "Event Date", None),
        ("EVENT_MONTH", "date", "dimension", "ordinal", "Event Month", None),
        ("DEVICE_TYPE", "string", "dimension", "nominal", "Device", None),
        ("TRAFFIC_SOURCE", "string", "dimension", "nominal", "Traffic Source", None),
        ("UTM_CAMPAIGN", "string", "dimension", "nominal", "Campaign", None),
        ("SESSIONS", "integer", "measure", "quantitative", "Sessions", None),
        ("ADD_TO_CART_SESSIONS", "integer", "measure", "quantitative", "Add-to-Cart", None),
        ("ABANDON_CART_SESSIONS", "integer", "measure", "quantitative", "Abandoned", None),
        ("PURCHASE_SESSIONS", "integer", "measure", "quantitative", "Purchases", None),
    ]
    sellers_cols = [
        ("SELLER_ID", "string", "dimension", "nominal", None, None),
        ("SELLER_STATE", "string", "dimension", "nominal", "Seller State", None),
        ("PRIMARY_CATEGORY", "string", "dimension", "nominal", "Category", None),
        ("GMV_BRL", "real", "measure", "quantitative", "Seller GMV (BRL)", MONEY),
        ("ORDER_COUNT", "integer", "measure", "quantitative", "Orders", None),
        ("DELIVERED_ORDERS", "integer", "measure", "quantitative", "Delivered", None),
        ("CUSTOMER_COUNT", "integer", "measure", "quantitative", "Customers", None),
        ("AVG_DELIVERY_DAYS", "real", "measure", "quantitative", "Avg Delivery Days", "0.0"),
        ("AVG_REVIEW_SCORE", "real", "measure", "quantitative", "Avg Review", "0.00"),
        ("LATE_DELIVERY_RATE", "real", "measure", "quantitative", "Late Rate %", "0.0"),
        ("REVIEW_COUNT", "integer", "measure", "quantitative", "Reviews", None),
    ]
    cohort_cols = [
        ("COHORT_MONTH", "date", "dimension", "ordinal", "Cohort Month", None),
        ("MONTHS_SINCE", "integer", "dimension", "ordinal", "Months Since", None),
        ("COHORT_SIZE", "integer", "measure", "quantitative", "Cohort Size", None),
        ("ACTIVE_CUSTOMERS", "integer", "measure", "quantitative", "Active", None),
        ("RETENTION_PCT", "real", "measure", "quantitative", "Retention %", "0.0"),
    ]
    custseg_cols = [
        ("VALUE_SEGMENT", "string", "dimension", "nominal", "Value Segment", None),
        ("CUSTOMER_STATE", "string", "dimension", "nominal", "Customer State", None),
        ("CUSTOMERS", "integer", "measure", "quantitative", "Customers", None),
        ("REPEAT_CUSTOMERS", "integer", "measure", "quantitative", "Repeat", None),
        ("TOTAL_GMV_BRL", "real", "measure", "quantitative", "Total GMV (BRL)", MONEY),
        ("AVG_ORDER_VALUE_BRL", "real", "measure", "quantitative", "AOV (BRL)", MONEY),
    ]

    orders_extra = f"      {CALC['MARGIN_PCT']}\n      {CALC['AOV']}\n      {CALC['LATE_RATE']}\n"
    funneld_extra = f"      {CALC['CONV']}\n"

    datasources = "\n".join([
        datasource("federated.orders", "hyper.orders", "Orders", "Olist Orders (dbt)", orders_cols, orders_extra),
        datasource("federated.trend", "hyper.trend", "MonthlyTrend", "Olist Monthly (dbt)", trend_cols),
        datasource("federated.category", "hyper.category", "Category", "Olist Category (dbt)", category_cols),
        datasource("federated.funnel", "hyper.funnel", "FunnelSteps", "Olist Funnel Steps (dbt)", funnel_cols),
        datasource("federated.funneld", "hyper.funneld", "FunnelDaily", "Olist Funnel Daily (dbt)", funneld_cols, funneld_extra),
        datasource("federated.sellers", "hyper.sellers", "Sellers", "Olist Sellers (dbt)", sellers_cols),
        datasource("federated.cohort", "hyper.cohort", "Cohort", "Olist Cohorts (dbt)", cohort_cols),
        datasource("federated.custseg", "hyper.custseg", "CustomerSeg", "Olist Segments (dbt)", custseg_cols),
    ])

    # ---- worksheets ------------------------------------------------------------------
    sheets = []

    # KPI tiles (Executive Overview) — numeric so the values render in full; units are in the captions.
    d, _ = dmeas("GMV_BRL", "Sum")
    sheets.append(kpi("KPI GMV", "federated.orders", "Olist Orders (dbt)", d, R("federated.orders", "[sum:GMV_BRL:qk]")))

    margin_dep = (dmeas("GROSS_PROFIT_BRL", "Sum")[0] + "\n            "
                  + dmeas("PRODUCT_REVENUE_BRL", "Sum")[0] + "\n            " + CALC["MARGIN_PCT"])
    sheets.append(kpi("KPI Margin", "federated.orders", "Olist Orders (dbt)", margin_dep, R("federated.orders", "[MARGIN_PCT]")))

    d, _ = dmeas("ORDER_ID", "CountD")
    sheets.append(kpi("KPI Orders", "federated.orders", "Olist Orders (dbt)", d, R("federated.orders", "[ctd:ORDER_ID:qk]")))

    aov_dep = (dmeas("GMV_BRL", "Sum")[0] + "\n            "
               + "<column datatype='string' name='[ORDER_ID]' role='dimension' type='nominal' />" + "\n            " + CALC["AOV"])
    sheets.append(kpi("KPI AOV", "federated.orders", "Olist Orders (dbt)", aov_dep, R("federated.orders", "[AOV]")))

    d, _ = dmeas("REVIEW_SCORE", "Avg", "real", "Review Score", "0.00")
    sheets.append(kpi("KPI Review", "federated.orders", "Olist Orders (dbt)", d, R("federated.orders", "[avg:REVIEW_SCORE:qk]")))

    conv_dep = (dmeas("PURCHASE_SESSIONS", "Sum", "integer")[0] + "\n            "
                + dmeas("SESSIONS", "Sum", "integer")[0] + "\n            " + CALC["CONV"])
    sheets.append(kpi("KPI Conversion", "federated.funneld", "Olist Funnel Daily (dbt)", conv_dep, R("federated.funneld", "[CONV]")))

    # 1. GMV Trend (monthly, complete months only)
    cdep, cfilt = complete_filter("federated.trend")
    mdep, mtok = dmeas("GMV_BRL", "Sum", "real", "GMV (BRL)", MONEY)
    ddep, dtok = ddate("ORDER_MONTH", "Order Month")
    sheets.append(ws("GMV Trend", "federated.trend", "Olist Monthly (dbt)",
                     f"{cdep}\n            {ddep}\n            {mdep}",
                     R("federated.trend", mtok), R("federated.trend", dtok),
                     "Line", view_extra=cfilt, mark_color=ACCENT))

    # 2. GMV by Category (treemap)
    dimdep, dimtok = ddim("PRODUCT_CATEGORY", caption="Category")
    mdep, mtok = dmeas("GMV_BRL", "Sum", "real", "GMV (BRL)", MONEY)
    sheets.append(ws("GMV by Category", "federated.category", "Olist Category (dbt)",
                     f"{dimdep}\n            {mdep}", "", "", "Square",
                     encodings=enc(color=R("federated.category", mtok), size=R("federated.category", mtok), text=R("federated.category", dimtok)),
                     view_extra=sort("federated.category", dimtok, mtok)))

    # 3. GMV by Customer State (bar)
    dimdep, dimtok = ddim("CUSTOMER_STATE", caption="Customer State")
    mdep, mtok = dmeas("GMV_BRL", "Sum", "real", "GMV (BRL)", MONEY)
    sheets.append(ws("GMV by State", "federated.orders", "Olist Orders (dbt)",
                     f"{dimdep}\n            {mdep}", R("federated.orders", dimtok), R("federated.orders", mtok),
                     "Bar", view_extra=sort("federated.orders", dimtok, mtok), mark_color=ACCENT))

    # 4. Funnel (bars by step)
    dimdep, dimtok = ddim("STEP_NAME", caption="Funnel Step")
    sdep, stok = dmeas("SESSIONS", "Sum", "integer", "Sessions")
    odep, otok = dmeas("STEP_ORDER", "Avg", "integer")
    sheets.append(ws("Funnel", "federated.funnel", "Olist Funnel Steps (dbt)",
                     f"{dimdep}\n            {sdep}\n            {odep}",
                     R("federated.funnel", dimtok), R("federated.funnel", stok),
                     "Bar", view_extra=sort("federated.funnel", dimtok, otok, "ASC"), mark_color=ACCENT))

    # numeric conversion dep for the charts (KPI uses the string K_CONV instead)
    conv_num_dep = (dmeas("PURCHASE_SESSIONS", "Sum", "integer")[0] + "\n            "
                    + dmeas("SESSIONS", "Sum", "integer")[0] + "\n            " + CALC["CONV"])

    # 5. Conversion by Device
    dimdep, dimtok = ddim("DEVICE_TYPE", caption="Device")
    sheets.append(ws("Conversion by Device", "federated.funneld", "Olist Funnel Daily (dbt)",
                     f"{dimdep}\n            {conv_num_dep}", R("federated.funneld", dimtok), R("federated.funneld", "[CONV]"),
                     "Bar", view_extra=sort("federated.funneld", dimtok, "[CONV]"), mark_color=ACCENT))

    # 6. Conversion by Traffic Source
    dimdep, dimtok = ddim("TRAFFIC_SOURCE", caption="Traffic Source")
    sheets.append(ws("Conversion by Source", "federated.funneld", "Olist Funnel Daily (dbt)",
                     f"{dimdep}\n            {conv_num_dep}", R("federated.funneld", dimtok), R("federated.funneld", "[CONV]"),
                     "Bar", view_extra=sort("federated.funneld", dimtok, "[CONV]"), mark_color=ACCENT))

    # 7. Conversion Trend (monthly)
    ddep, dtok = ddate("EVENT_MONTH", "Event Month")
    sheets.append(ws("Conversion Trend", "federated.funneld", "Olist Funnel Daily (dbt)",
                     f"{ddep}\n            {conv_num_dep}", R("federated.funneld", "[CONV]"), R("federated.funneld", dtok),
                     "Line", mark_color=ACCENT))

    # 8. Late Rate by Distance (bar, ink) with band filter
    dimdep, dimtok = ddim("DISTANCE_BUCKET", caption="Distance Band")
    odep, otok = dmeas("DISTANCE_ORDER", "Avg", "integer")
    late_dep = dmeas("IS_LATE", "Avg")[0] + "\n            " + CALC["LATE_RATE"]  # not used token; use calc
    late_full = (dimdep + "\n            " + odep + "\n            "
                 + "<column datatype='integer' name='[IS_LATE]' role='measure' type='quantitative' />"
                 + "\n            " + CALC["LATE_RATE"])
    band_filter = (f"          <filter class='categorical' column='[federated.orders].{dimtok}'>\n"
                   f"            <groupfilter function='union' user:ui-domain='database' user:ui-enumeration='inclusive' user:ui-marker='enter'>\n"
                   + "".join(f"              <groupfilter function='member' level='[none:DISTANCE_BUCKET:nk]' member='&quot;{b}&quot;' />\n"
                             for b in ["0-50km", "50-200km", "200-500km", "500-1000km", "1000km+"])
                   + "            </groupfilter>\n          </filter>\n")
    sheets.append(ws("Late Rate by Distance", "federated.orders", "Olist Orders (dbt)",
                     late_full, R("federated.orders", dimtok), R("federated.orders", "[LATE_RATE]"),
                     "Bar", view_extra=sort("federated.orders", dimtok, otok, "ASC") + band_filter, mark_color=INK))

    # 9. Review by Delay Bucket (bar)
    dimdep, dimtok = ddim("DELAY_BUCKET", caption="Delay Bucket")
    mdep, mtok = dmeas("REVIEW_SCORE", "Avg", "real", "Review Score", "0.00")
    sheets.append(ws("Review by Delay", "federated.orders", "Olist Orders (dbt)",
                     f"{dimdep}\n            {mdep}", R("federated.orders", dimtok), R("federated.orders", mtok),
                     "Bar", view_extra=sort("federated.orders", dimtok, mtok), mark_color=ACCENT))

    # 10. Late Rate Trend (monthly)
    cdep, cfilt = complete_filter("federated.orders")
    ddep, dtok = ddate("ORDER_MONTH", "Order Month")
    late_full = cdep + "\n            " + ddep + "\n            " + "<column datatype='integer' name='[IS_LATE]' role='measure' type='quantitative' />" + "\n            " + CALC["LATE_RATE"]
    sheets.append(ws("Late Rate Trend", "federated.orders", "Olist Orders (dbt)",
                     late_full, R("federated.orders", "[LATE_RATE]"), R("federated.orders", dtok),
                     "Line", view_extra=cfilt, mark_color=INK))

    # 11. Seller Scatter
    xdep, xtok = dmeas("AVG_DELIVERY_DAYS", "Avg", "real", "Avg Delivery Days", "0.0")
    ydep, ytok = dmeas("AVG_REVIEW_SCORE", "Avg", "real", "Avg Review", "0.00")
    czdep, cztok = dmeas("LATE_DELIVERY_RATE", "Avg", "real", "Late Rate %", "0.0")
    szdep, sztok = dmeas("GMV_BRL", "Sum", "real", "Seller GMV (BRL)", MONEY)
    iddep, idtok = ddim("SELLER_ID")
    sheets.append(ws("Seller Scatter", "federated.sellers", "Olist Sellers (dbt)",
                     f"{iddep}\n            {xdep}\n            {ydep}\n            {czdep}\n            {szdep}",
                     R("federated.sellers", ytok), R("federated.sellers", xtok),
                     "Circle", encodings=enc(color=R("federated.sellers", cztok), size=R("federated.sellers", sztok), lod=R("federated.sellers", idtok))))

    # 12. Cohort Retention (heatmap)
    rdep, rtok = ddisc("COHORT_MONTH", "date", "Cohort Month")
    mmdep, mmtok = ddisc("MONTHS_SINCE", "integer", "Months Since")
    vdep, vtok = dmeas("RETENTION_PCT", "Sum", "real", "Retention %", "0.0")
    sheets.append(ws("Cohort Retention", "federated.cohort", "Olist Cohorts (dbt)",
                     f"{rdep}\n            {mmdep}\n            {vdep}",
                     R("federated.cohort", rtok), R("federated.cohort", mmtok),
                     "Square", encodings=enc(color=R("federated.cohort", vtok), text=R("federated.cohort", vtok))))

    # 13. Customers by Value Segment (bar)
    dimdep, dimtok = ddim("VALUE_SEGMENT", caption="Value Segment")
    mdep, mtok = dmeas("CUSTOMERS", "Sum", "integer", "Customers")
    sheets.append(ws("Customers by Segment", "federated.custseg", "Olist Segments (dbt)",
                     f"{dimdep}\n            {mdep}", R("federated.custseg", dimtok), R("federated.custseg", mtok),
                     "Bar", view_extra=sort("federated.custseg", dimtok, mtok), mark_color=ACCENT))

    # 14. GMV by Seller State (bar)
    dimdep, dimtok = ddim("SELLER_STATE", caption="Seller State")
    mdep, mtok = dmeas("GMV_BRL", "Sum", "real", "Seller GMV (BRL)", MONEY)
    sheets.append(ws("GMV by Seller State", "federated.sellers", "Olist Sellers (dbt)",
                     f"{dimdep}\n            {mdep}", R("federated.sellers", dimtok), R("federated.sellers", mtok),
                     "Bar", view_extra=sort("federated.sellers", dimtok, mtok), mark_color=ACCENT))

    worksheets = "".join(sheets)

    # ---- dashboards ------------------------------------------------------------------
    def txt_zone(zid, x, y, w, h, text, bg=WHITE, fg=INK, fs=9, bold=False, pad_top=6, pad_left=10):
        b = " bold='true'" if bold else ""
        return f"""          <zone h='{h}' id='{zid}' type-v2='text' w='{w}' x='{x}' y='{y}'>
            <formatted-text><run{b} fontcolor='{fg}' fontsize='{fs}'>{text}</run></formatted-text>
            <zone-style><format attr='background-color' value='{bg}' /><format attr='background-opacity' value='1.0' /><format attr='border-style' value='none' /><format attr='padding-top' value='{pad_top}' /><format attr='padding-left' value='{pad_left}' /></zone-style>
          </zone>
"""

    def chart_zone(zid, name, x, y, w, h):
        return f"""          <zone h='{h}' id='{zid}' name='{name}' w='{w}' x='{x}' y='{y}'>
            <zone-style><format attr='border-style' value='none' /><format attr='margin' value='6' /></zone-style>
          </zone>
"""

    def num_zone(zid, name, x, y, w, h):
        return f"""          <zone h='{h}' id='{zid}' name='{name}' w='{w}' x='{x}' y='{y}'>
            <zone-style><format attr='border-color' value='{GRIDLINE}' /><format attr='border-style' value='solid' /><format attr='border-width' value='1' /><format attr='margin' value='4' /></zone-style>
          </zone>
"""

    def dashboard(name, w, h, banner_title, banner_sub, zones):
        return f"""    <dashboard name='{esc(name)}'>
      <style />
      <size maxheight='{h}' maxwidth='{w}' minheight='{h}' minwidth='{w}' />
      <zones>
        <zone h='100000' id='1' type-v2='layout-basic' w='100000' x='0' y='0'>
          <zone h='6000' id='900' type-v2='text' w='100000' x='0' y='0'>
            <formatted-text><run bold='true' fontcolor='{WHITE}' fontsize='20'>{banner_title}</run><run fontcolor='#E7E1FF' fontsize='11'>   {banner_sub}</run></formatted-text>
            <zone-style><format attr='background-color' value='{ACCENT}' /><format attr='background-opacity' value='1.0' /><format attr='border-style' value='none' /><format attr='padding-top' value='12' /><format attr='padding-left' value='16' /></zone-style>
          </zone>
{zones}        </zone>
      </zones>
    </dashboard>"""

    # Dashboard 1 — Executive Overview (6 KPIs + 3 charts)
    kpi_labels = ["TOTAL GMV (R$)", "GROSS MARGIN", "ORDERS", "AOV (R$)", "AVG REVIEW (1-5)", "CONVERSION"]
    kpi_names = ["KPI GMV", "KPI Margin", "KPI Orders", "KPI AOV", "KPI Review", "KPI Conversion"]
    z = ""
    xs = [0, 16666, 33332, 49998, 66664, 83330]
    ws_w = [16666, 16666, 16666, 16666, 16666, 16670]
    for i, (lbl, nm, x, wv) in enumerate(zip(kpi_labels, kpi_names, xs, ws_w)):
        z += txt_zone(100 + i, x, 6500, wv, 2600, lbl, fg=LABEL, fs=8, bold=True)
        z += num_zone(200 + i, nm, x, 9100, wv, 9000)
    z += chart_zone(40, "GMV Trend", 0, 19000, 100000, 27000)
    z += chart_zone(41, "GMV by Category", 0, 46500, 50000, 48000)
    z += chart_zone(42, "GMV by State", 50000, 46500, 50000, 48000)
    z += txt_zone(950, 0, 94800, 100000, 5200,
                  "Delivered-only GMV &#183; gross margin on product revenue (COGS is synthetic/illustrative) &#183; conversion from the synthetic clickstream. Built on OLIST.DBT_DEMO dbt marts; definitions governed by the Lynk semantic layer.",
                  fg=LABEL, fs=7, pad_top=8)
    dash1 = dashboard("Executive Overview", 1700, 2100,
                      "Olist Marketplace &#183; Executive Overview",
                      "Brazilian e-commerce marketplace &#183; delivered GMV, margin, growth", z)

    # Dashboard 2 — Growth & Funnel (funnel wide-left + 3 charts)
    z = ""
    z += chart_zone(50, "Funnel", 0, 6500, 50000, 88000)
    z += chart_zone(51, "Conversion by Device", 50000, 6500, 50000, 29000)
    z += chart_zone(52, "Conversion by Source", 50000, 35800, 50000, 29000)
    z += chart_zone(53, "Conversion Trend", 50000, 65100, 50000, 29500)
    z += txt_zone(951, 0, 94800, 100000, 5200,
                  "SYNTHETIC clickstream (session_event) &#183; funnel counts distinct sessions reaching each step &#183; conversion = purchasing sessions / all sessions. Illustrative data — disclose in demos.",
                  fg=LABEL, fs=7, pad_top=8)
    dash2 = dashboard("Growth & Funnel", 1700, 1900,
                      "Olist Marketplace &#183; Growth &amp; Funnel",
                      "Acquisition funnel and conversion (synthetic clickstream)", z)

    # Dashboard 3 — Delivery Operations (2 top + 1 wide bottom)
    z = ""
    z += chart_zone(60, "Late Rate by Distance", 0, 6500, 50000, 44000)
    z += chart_zone(61, "Review by Delay", 50000, 6500, 50000, 44000)
    z += chart_zone(62, "Late Rate Trend", 0, 51000, 100000, 43500)
    z += txt_zone(952, 0, 94800, 100000, 5200,
                  "Delivered orders only &#183; late = delivered after the estimated date &#183; distance is the worst-case seller&#8594;customer haversine km. The delay&#8594;review link is the headline satisfaction driver.",
                  fg=LABEL, fs=7, pad_top=8)
    dash3 = dashboard("Delivery Operations", 1700, 1750,
                      "Olist Marketplace &#183; Delivery Operations",
                      "Late deliveries, shipping distance, and satisfaction", z)

    # Dashboard 4 — Seller & Customer 360 (2x2)
    z = ""
    z += chart_zone(70, "Seller Scatter", 0, 6500, 50000, 44000)
    z += chart_zone(71, "Cohort Retention", 50000, 6500, 50000, 44000)
    z += chart_zone(72, "Customers by Segment", 0, 51000, 50000, 43500)
    z += chart_zone(73, "GMV by Seller State", 50000, 51000, 50000, 43500)
    z += txt_zone(953, 0, 94800, 100000, 5200,
                  "Two-sided marketplace &#183; sellers with &#8805;10 orders &#183; cohort = month of a customer's first delivered order. ~3% of customers reorder (acquisition-heavy) — month-0 retention is 100% by construction.",
                  fg=LABEL, fs=7, pad_top=8)
    dash4 = dashboard("Seller & Customer 360", 1700, 1850,
                      "Olist Marketplace &#183; Seller &amp; Customer 360",
                      "Merchant health and customer value / retention", z)

    dashboards = "\n".join([dash1, dash2, dash3, dash4])

    # ---- windows ---------------------------------------------------------------------
    all_sheets = [
        "KPI GMV", "KPI Margin", "KPI Orders", "KPI AOV", "KPI Review", "KPI Conversion",
        "GMV Trend", "GMV by Category", "GMV by State",
        "Funnel", "Conversion by Device", "Conversion by Source", "Conversion Trend",
        "Late Rate by Distance", "Review by Delay", "Late Rate Trend",
        "Seller Scatter", "Cohort Retention", "Customers by Segment", "GMV by Seller State",
    ]
    dash_sheets = {
        "Executive Overview": ["KPI GMV", "KPI Margin", "KPI Orders", "KPI AOV", "KPI Review", "KPI Conversion", "GMV Trend", "GMV by Category", "GMV by State"],
        "Growth & Funnel": ["Funnel", "Conversion by Device", "Conversion by Source", "Conversion Trend"],
        "Delivery Operations": ["Late Rate by Distance", "Review by Delay", "Late Rate Trend"],
        "Seller & Customer 360": ["Seller Scatter", "Cohort Retention", "Customers by Segment", "GMV by Seller State"],
    }
    win = "".join(f"    <window class='worksheet' name='{s}' />\n" for s in all_sheets)
    for dname, sl in dash_sheets.items():
        vps = "".join(f"        <viewpoint name='{s}' />\n" for s in sl)
        win += (f"    <window class='dashboard' name='{esc(dname)}'>\n      <viewpoints>\n{vps}"
                f"      </viewpoints>\n      <active id='-1' />\n    </window>\n")

    return f"""<?xml version='1.0' encoding='utf-8' ?>
<workbook source-build='2023.3' source-platform='win' version='18.1' xmlns:user='http://www.tableausoftware.com/xml/user'>
  <preferences>
    <preference name='ui.encoding.shelf.height' value='24' />
    <preference name='ui.shelf.height' value='26' />
  </preferences>
  <datasources>
{datasources}
  </datasources>
  <worksheets>
{worksheets}  </worksheets>
  <dashboards>
{dashboards}
  </dashboards>
  <windows source-height='30'>
{win}  </windows>
</workbook>
"""


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit("Usage: python publish/build_workbook.py <input.hyper> <output.twbx>")
    hyper_in = Path(sys.argv[1])
    twbx_out = Path(sys.argv[2])
    if not hyper_in.exists():
        sys.exit(f"Hyper not found: {hyper_in}")
    twbx_out.parent.mkdir(parents=True, exist_ok=True)

    twb = build_twb()
    import xml.dom.minidom as minidom
    minidom.parseString(twb)  # fail fast on malformed XML

    if twbx_out.exists():
        twbx_out.unlink()
    with zipfile.ZipFile(twbx_out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("olist_marketplace.twb", twb)
        z.write(hyper_in, HYPER_REL)
    print(f"Packaged {twbx_out} ({twbx_out.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
