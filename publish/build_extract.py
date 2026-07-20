"""Build the Tableau .hyper extract from the Olist dbt marts in Snowflake (OLIST.DBT_DEMO).

Writes ONE .hyper with a table per dashboard need. All grains come straight from governed
dbt marts, so every Tableau number reconciles with what Lynk Ask returns for the same question:

  Extract.Orders        one row per DELIVERED order  (fct_orders)            -> Exec Overview + Delivery Ops
  Extract.MonthlyTrend  one row per month            (mart_gmv_monthly)      -> Exec Overview trend
  Extract.Category      one row per category         (mart_category_performance) -> Exec Overview treemap
  Extract.FunnelSteps   step x device x source       (mart_funnel_daily, unpivoted) -> Growth funnel
  Extract.FunnelDaily   day x device x source x utm  (mart_funnel_daily)     -> Growth conversion trend
  Extract.Sellers       one row per seller (>=10 ord)(mart_seller_performance) -> Seller & Customer 360
  Extract.Cohort        cohort x months-since        (mart_customer_cohort)  -> Seller & Customer 360
  Extract.CustomerSeg   value segment x state        (mart_customer_value)   -> Seller & Customer 360

The data is embedded in the workbook, so there is no live Snowflake connection at view time.
Connection uses key-pair auth (same key the Snowflake MCP uses). The corporate network
MITM-intercepts TLS, so point OpenSSL at the combined CA bundle before importing the connector.

Usage:  python publish/build_extract.py [output.hyper]
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from pathlib import Path

_CA_BUNDLE = os.environ.get(
    "SNOWFLAKE_CA_BUNDLE", "C:/Users/USUARIO/snowflake-mcp/win_ca_bundle.pem"
)
if os.path.exists(_CA_BUNDLE):
    os.environ.setdefault("SSL_CERT_FILE", _CA_BUNDLE)
    os.environ.setdefault("REQUESTS_CA_BUNDLE", _CA_BUNDLE)

import snowflake.connector
from tableauhyperapi import (
    Connection,
    CreateMode,
    HyperProcess,
    Inserter,
    Nullability,
    SqlType,
    TableDefinition,
    TableName,
    Telemetry,
)

# --- helpers to declare a column once (hyper type + how to coerce the Snowflake value) -------
NULL = Nullability.NULLABLE
NOTNULL = Nullability.NOT_NULLABLE


def _text(v):
    return None if v is None else str(v)


def _double(v):
    return None if v is None else float(v)


def _int(v):
    return None if v is None else int(v)


def _date(v):
    # snowflake-connector returns datetime.date for DATE columns already
    if v is None:
        return None
    return v if isinstance(v, dt.date) else dt.date.fromisoformat(str(v)[:10])


_KIND = {
    "text": (SqlType.text, _text),
    "double": (SqlType.double, _double),
    "int": (SqlType.int, _int),
    "bigint": (SqlType.big_int, _int),
    "date": (SqlType.date, _date),
}


class Col:
    __slots__ = ("name", "kind", "nullable")

    def __init__(self, name, kind, nullable=NULL):
        self.name, self.kind, self.nullable = name, kind, nullable


class Spec:
    def __init__(self, table, query, cols):
        self.tname = table
        self.table = TableName("Extract", table)
        self.query = query
        self.cols = cols

    def definition(self):
        return TableDefinition(self.table, [
            TableDefinition.Column(c.name, _KIND[c.kind][0](), c.nullable) for c in self.cols
        ])

    def coerce(self, rows):
        fns = [_KIND[c.kind][1] for c in self.cols]
        return [[fn(cell) for fn, cell in zip(fns, row)] for row in rows]


# ------------------------------------------------------------------ table specs (grain-aligned)
SPECS = [
    Spec(
        "Orders",
        """
        SELECT ORDER_ID, ORDER_MONTH, ORDER_YEAR, IFF(IS_COMPLETE_MONTH, 1, 0) AS is_complete_month,
               CUSTOMER_ID, CUSTOMER_STATE, COALESCE(PRIMARY_CATEGORY, 'Unknown') AS primary_category,
               GMV_BRL, PRODUCT_REVENUE_BRL, FREIGHT_BRL, COGS_BRL, GROSS_PROFIT_BRL,
               REVIEW_SCORE,
               IFF(IS_LATE IS NULL, NULL, IFF(IS_LATE, 1, 0)) AS is_late,
               DELIVERY_DAYS, DELAY_BUCKET,
               MAX_DISTANCE_KM AS distance_km, DISTANCE_BUCKET,
               CASE DISTANCE_BUCKET WHEN '0-50km' THEN 1 WHEN '50-200km' THEN 2 WHEN '200-500km' THEN 3
                    WHEN '500-1000km' THEN 4 WHEN '1000km+' THEN 5 END AS distance_order,
               COALESCE(PRIMARY_PAYMENT_TYPE, 'unknown') AS payment_type, PAYMENT_INSTALLMENTS,
               BRAZILIAN_SEASON, IFF(IS_BLACK_FRIDAY, 1, 0) AS is_black_friday
        FROM OLIST.DBT_DEMO.FCT_ORDERS
        WHERE IS_DELIVERED
        """,
        [
            Col("ORDER_ID", "text", NOTNULL), Col("ORDER_MONTH", "date", NOTNULL),
            Col("ORDER_YEAR", "int", NOTNULL), Col("IS_COMPLETE_MONTH", "int", NOTNULL),
            Col("CUSTOMER_ID", "text", NOTNULL), Col("CUSTOMER_STATE", "text"),
            Col("PRIMARY_CATEGORY", "text", NOTNULL), Col("GMV_BRL", "double"),
            Col("PRODUCT_REVENUE_BRL", "double"), Col("FREIGHT_BRL", "double"),
            Col("COGS_BRL", "double"), Col("GROSS_PROFIT_BRL", "double"),
            Col("REVIEW_SCORE", "double"), Col("IS_LATE", "int"),
            Col("DELIVERY_DAYS", "double"), Col("DELAY_BUCKET", "text"),
            Col("DISTANCE_KM", "double"), Col("DISTANCE_BUCKET", "text"),
            Col("DISTANCE_ORDER", "int"), Col("PAYMENT_TYPE", "text"),
            Col("PAYMENT_INSTALLMENTS", "int"), Col("BRAZILIAN_SEASON", "text"),
            Col("IS_BLACK_FRIDAY", "int"),
        ],
    ),
    Spec(
        "MonthlyTrend",
        """
        SELECT ORDER_MONTH, ORDER_YEAR, IFF(IS_COMPLETE_MONTH, 1, 0) AS is_complete_month,
               ORDERS, CUSTOMERS, GMV_BRL, PRODUCT_REVENUE_BRL, GROSS_PROFIT_BRL,
               GROSS_MARGIN_PCT, AOV_BRL, AVG_REVIEW_SCORE, LATE_RATE
        FROM OLIST.DBT_DEMO.MART_GMV_MONTHLY
        """,
        [
            Col("ORDER_MONTH", "date", NOTNULL), Col("ORDER_YEAR", "int", NOTNULL),
            Col("IS_COMPLETE_MONTH", "int", NOTNULL), Col("ORDERS", "bigint"),
            Col("CUSTOMERS", "bigint"), Col("GMV_BRL", "double"),
            Col("PRODUCT_REVENUE_BRL", "double"), Col("GROSS_PROFIT_BRL", "double"),
            Col("GROSS_MARGIN_PCT", "double"), Col("AOV_BRL", "double"),
            Col("AVG_REVIEW_SCORE", "double"), Col("LATE_RATE", "double"),
        ],
    ),
    Spec(
        "Category",
        """
        SELECT PRODUCT_CATEGORY, ITEMS, ORDERS, GMV_BRL, GROSS_PROFIT_BRL,
               GROSS_MARGIN_PCT, AVG_ITEM_PRICE_BRL
        FROM OLIST.DBT_DEMO.MART_CATEGORY_PERFORMANCE
        """,
        [
            Col("PRODUCT_CATEGORY", "text", NOTNULL), Col("ITEMS", "bigint"),
            Col("ORDERS", "bigint"), Col("GMV_BRL", "double"),
            Col("GROSS_PROFIT_BRL", "double"), Col("GROSS_MARGIN_PCT", "double"),
            Col("AVG_ITEM_PRICE_BRL", "double"),
        ],
    ),
    Spec(
        "FunnelSteps",
        """
        SELECT step_name, step_order, DEVICE_TYPE, TRAFFIC_SOURCE, SUM(cnt) AS sessions
        FROM (
            SELECT DEVICE_TYPE, TRAFFIC_SOURCE, '1 - Sessions'    AS step_name, 1 AS step_order, SESSIONS             AS cnt FROM OLIST.DBT_DEMO.MART_FUNNEL_DAILY
            UNION ALL SELECT DEVICE_TYPE, TRAFFIC_SOURCE, '2 - Product view', 2, VIEW_ITEM_SESSIONS   FROM OLIST.DBT_DEMO.MART_FUNNEL_DAILY
            UNION ALL SELECT DEVICE_TYPE, TRAFFIC_SOURCE, '3 - Add to cart',  3, ADD_TO_CART_SESSIONS FROM OLIST.DBT_DEMO.MART_FUNNEL_DAILY
            UNION ALL SELECT DEVICE_TYPE, TRAFFIC_SOURCE, '4 - Purchase',     4, PURCHASE_SESSIONS    FROM OLIST.DBT_DEMO.MART_FUNNEL_DAILY
        )
        GROUP BY step_name, step_order, DEVICE_TYPE, TRAFFIC_SOURCE
        """,
        [
            Col("STEP_NAME", "text", NOTNULL), Col("STEP_ORDER", "int", NOTNULL),
            Col("DEVICE_TYPE", "text"), Col("TRAFFIC_SOURCE", "text"),
            Col("SESSIONS", "bigint"),
        ],
    ),
    Spec(
        "FunnelDaily",
        """
        SELECT EVENT_DATE, DATE_TRUNC('MONTH', EVENT_DATE)::DATE AS event_month,
               DEVICE_TYPE, TRAFFIC_SOURCE, UTM_CAMPAIGN,
               SESSIONS, ADD_TO_CART_SESSIONS, ABANDON_CART_SESSIONS, PURCHASE_SESSIONS
        FROM OLIST.DBT_DEMO.MART_FUNNEL_DAILY
        """,
        [
            Col("EVENT_DATE", "date", NOTNULL), Col("EVENT_MONTH", "date", NOTNULL),
            Col("DEVICE_TYPE", "text"), Col("TRAFFIC_SOURCE", "text"),
            Col("UTM_CAMPAIGN", "text"), Col("SESSIONS", "bigint"),
            Col("ADD_TO_CART_SESSIONS", "bigint"), Col("ABANDON_CART_SESSIONS", "bigint"),
            Col("PURCHASE_SESSIONS", "bigint"),
        ],
    ),
    Spec(
        "Sellers",
        """
        SELECT SELLER_ID, SELLER_STATE, PRIMARY_CATEGORY, GMV_BRL, ORDER_COUNT, DELIVERED_ORDERS,
               CUSTOMER_COUNT, AVG_DELIVERY_DAYS, AVG_REVIEW_SCORE, LATE_DELIVERY_RATE, REVIEW_COUNT
        FROM OLIST.DBT_DEMO.MART_SELLER_PERFORMANCE
        WHERE ORDER_COUNT >= 10
        """,
        [
            Col("SELLER_ID", "text", NOTNULL), Col("SELLER_STATE", "text"),
            Col("PRIMARY_CATEGORY", "text"), Col("GMV_BRL", "double"),
            Col("ORDER_COUNT", "bigint"), Col("DELIVERED_ORDERS", "bigint"),
            Col("CUSTOMER_COUNT", "bigint"), Col("AVG_DELIVERY_DAYS", "double"),
            Col("AVG_REVIEW_SCORE", "double"), Col("LATE_DELIVERY_RATE", "double"),
            Col("REVIEW_COUNT", "bigint"),
        ],
    ),
    Spec(
        "Cohort",
        """
        SELECT COHORT_MONTH, MONTHS_SINCE, COHORT_SIZE, ACTIVE_CUSTOMERS, RETENTION_PCT
        FROM OLIST.DBT_DEMO.MART_CUSTOMER_COHORT
        """,
        [
            Col("COHORT_MONTH", "date", NOTNULL), Col("MONTHS_SINCE", "int", NOTNULL),
            Col("COHORT_SIZE", "bigint"), Col("ACTIVE_CUSTOMERS", "bigint"),
            Col("RETENTION_PCT", "double"),
        ],
    ),
    Spec(
        "CustomerSeg",
        """
        SELECT VALUE_SEGMENT, CUSTOMER_STATE,
               COUNT(*) AS customers,
               COUNT(IFF(IS_REPEAT_CUSTOMER, 1, NULL)) AS repeat_customers,
               ROUND(SUM(LIFETIME_GMV_BRL), 2) AS total_gmv_brl,
               ROUND(AVG(AVG_ORDER_VALUE_BRL), 2) AS avg_order_value_brl
        FROM OLIST.DBT_DEMO.MART_CUSTOMER_VALUE
        GROUP BY VALUE_SEGMENT, CUSTOMER_STATE
        """,
        [
            Col("VALUE_SEGMENT", "text", NOTNULL), Col("CUSTOMER_STATE", "text"),
            Col("CUSTOMERS", "bigint"), Col("REPEAT_CUSTOMERS", "bigint"),
            Col("TOTAL_GMV_BRL", "double"), Col("AVG_ORDER_VALUE_BRL", "double"),
        ],
    ),
]


def _connect():
    return snowflake.connector.connect(
        account=os.environ.get("SNOWFLAKE_ACCOUNT", "a5628485664271-lynkai_partner"),
        user=os.environ.get("SNOWFLAKE_USER", "LAILA"),
        authenticator="snowflake_jwt",
        private_key_file=os.environ.get(
            "SNOWFLAKE_PRIVATE_KEY_FILE", "C:/Users/USUARIO/.snowflake/keys/rsa_key.p8"
        ),
        role=os.environ.get("SNOWFLAKE_ROLE", "ACCOUNTADMIN"),
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
        database="OLIST",
        schema="DBT_DEMO",
    )


def fetch():
    conn = _connect()
    data = {}
    try:
        cur = conn.cursor()
        for spec in SPECS:
            cur.execute(spec.query)
            data[spec.tname] = spec.coerce(cur.fetchall())
    finally:
        conn.close()
    return data


def write_hyper(data, hyper_path: Path) -> None:
    hyper_path.parent.mkdir(parents=True, exist_ok=True)
    if hyper_path.exists():
        hyper_path.unlink()

    with HyperProcess(Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hyper:
        with Connection(hyper.endpoint, str(hyper_path), CreateMode.CREATE_AND_REPLACE) as conn:
            conn.catalog.create_schema("Extract")
            for spec in SPECS:
                defn = spec.definition()
                conn.catalog.create_table(defn)
                rows = data[spec.tname]
                if rows:
                    with Inserter(conn, defn) as ins:
                        ins.add_rows(rows)
                        ins.execute()
                n = conn.execute_scalar_query(f"SELECT COUNT(*) FROM {spec.table}")
                print(f"  {spec.tname:<14} {n:>8,} rows")
    print(f"Wrote {hyper_path}")


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("build/olist_marketplace.hyper")
    data = fetch()
    orders = data["Orders"]
    gmv = sum(r[7] for r in orders if r[7] is not None)  # GMV_BRL is column index 7
    print(f"Fetched {len(orders):,} delivered orders (GMV R$ {gmv:,.0f}); writing {len(SPECS)} tables.")
    write_hyper(data, out)


if __name__ == "__main__":
    main()
