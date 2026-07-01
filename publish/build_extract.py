"""Build a Tableau .hyper extract from the Olist dbt marts + curated views in Snowflake.

Produces ONE order-level fact table (one row per order) that powers the whole
"Olist Marketplace Overview" executive dashboard — KPI tiles, monthly GMV/order
trend, GMV by category, on-time rate by shipping-distance band, GMV by customer
state, and orders by Brazilian season. Every panel is an aggregation over this
single embedded table, so the workbook needs just one datasource.

Grain: one row per order (all statuses). GMV is the sum of item price+freight;
primary_category / is_late / review_score / distance come from joins.

Connection uses key-pair auth (same key the Snowflake MCP uses); we only read
the key to authenticate. The corporate network MITM-intercepts TLS, so point
OpenSSL at the combined CA bundle before importing snowflake.connector.

Usage:  python publish/build_extract.py [output.hyper]
"""
from __future__ import annotations

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

# One row per order. GMV + primary category from order_items x products;
# is_late/status from the curated orders view; review score from reviews;
# distance from the dbt order-distance mart; season from the dbt calendar.
QUERY = """
WITH item_agg AS (
    SELECT oi.ORDER_ID,
           SUM(oi.TOTAL_VALUE_BRL)                          AS gmv_brl,
           MAX_BY(p.PRODUCT_CATEGORY, oi.TOTAL_VALUE_BRL)   AS primary_category
    FROM OLIST.PUBLIC.V_ORDER_ITEMS oi
    JOIN OLIST.PUBLIC.V_PRODUCTS p ON p.PRODUCT_ID = oi.PRODUCT_ID
    GROUP BY oi.ORDER_ID
),
rev AS (
    SELECT ORDER_ID, AVG(REVIEW_SCORE) AS review_score
    FROM OLIST.PUBLIC.V_REVIEWS
    GROUP BY ORDER_ID
)
SELECT
    o.ORDER_ID,
    o.CUSTOMER_ID,
    DATE_TRUNC('MONTH', o.ORDER_PURCHASE_TIMESTAMP)::DATE   AS order_month,
    YEAR(o.ORDER_PURCHASE_TIMESTAMP)                        AS order_year,
    ia.gmv_brl,
    COALESCE(ia.primary_category, 'Unknown')               AS primary_category,
    c.CUSTOMER_STATE,
    o.ORDER_STATUS,
    IFF(o.IS_LATE IS NULL, NULL, IFF(o.IS_LATE, 1, 0))      AS is_late,
    o.DELIVERY_DAYS,
    rev.review_score,
    od.MAX_DISTANCE_KM                                      AS distance_km,
    od.DISTANCE_BUCKET,
    CASE od.DISTANCE_BUCKET
         WHEN '0-50km' THEN 1 WHEN '50-200km' THEN 2 WHEN '200-500km' THEN 3
         WHEN '500-1000km' THEN 4 WHEN '1000km+' THEN 5 END                AS distance_order,
    cal.BRAZILIAN_SEASON
FROM OLIST.PUBLIC.V_ORDERS o
JOIN OLIST.PUBLIC.V_CUSTOMERS c ON c.CUSTOMER_ID = o.CUSTOMER_ID
LEFT JOIN item_agg ia ON ia.ORDER_ID = o.ORDER_ID
LEFT JOIN rev        ON rev.ORDER_ID = o.ORDER_ID
LEFT JOIN OLIST.DBT_DEMO.MART_ORDER_DISTANCE od ON od.ORDER_ID = o.ORDER_ID
LEFT JOIN OLIST.DBT_DEMO.DIM_CALENDAR cal ON cal.DATE_DAY = o.ORDER_PURCHASE_TIMESTAMP::DATE
"""

EXTRACT_TABLE = TableName("Extract", "Extract")


def fetch_rows():
    conn = snowflake.connector.connect(
        account=os.environ.get("SNOWFLAKE_ACCOUNT", "a5628485664271-lynkai_partner"),
        user=os.environ.get("SNOWFLAKE_USER", "LAILA"),
        authenticator="snowflake_jwt",
        private_key_file=os.environ.get(
            "SNOWFLAKE_PRIVATE_KEY_FILE", "C:/Users/USUARIO/.snowflake/keys/rsa_key.p8"
        ),
        role=os.environ.get("SNOWFLAKE_ROLE", "ACCOUNTADMIN"),
        warehouse=os.environ.get("SNOWFLAKE_WAREHOUSE", "COMPUTE_WH"),
        database="OLIST",
        schema="PUBLIC",
    )
    try:
        cur = conn.cursor()
        cur.execute(QUERY)
        rows = cur.fetchall()
    finally:
        conn.close()
    norm = []
    for (oid, cid, omonth, oyear, gmv, cat, cstate, status, late, ddays, rscore, dist, dbucket, dorder, season) in rows:
        norm.append([
            str(oid),
            str(cid),
            omonth,  # datetime.date
            int(oyear),
            None if gmv is None else float(gmv),
            str(cat),
            None if cstate is None else str(cstate),
            None if status is None else str(status),
            None if late is None else int(late),
            None if ddays is None else float(ddays),
            None if rscore is None else float(rscore),
            None if dist is None else float(dist),
            None if dbucket is None else str(dbucket),
            None if dorder is None else int(dorder),
            None if season is None else str(season),
        ])
    return norm


def write_hyper(rows, hyper_path: Path) -> None:
    hyper_path.parent.mkdir(parents=True, exist_ok=True)
    if hyper_path.exists():
        hyper_path.unlink()

    def col(name, sqltype, nullable=Nullability.NULLABLE):
        return TableDefinition.Column(name, sqltype, nullable)

    table_def = TableDefinition(
        EXTRACT_TABLE,
        [
            col("ORDER_ID", SqlType.text(), Nullability.NOT_NULLABLE),
            col("CUSTOMER_ID", SqlType.text(), Nullability.NOT_NULLABLE),
            col("ORDER_MONTH", SqlType.date(), Nullability.NOT_NULLABLE),
            col("ORDER_YEAR", SqlType.int(), Nullability.NOT_NULLABLE),
            col("GMV_BRL", SqlType.double()),
            col("PRIMARY_CATEGORY", SqlType.text(), Nullability.NOT_NULLABLE),
            col("CUSTOMER_STATE", SqlType.text()),
            col("ORDER_STATUS", SqlType.text()),
            col("IS_LATE", SqlType.int()),
            col("DELIVERY_DAYS", SqlType.double()),
            col("REVIEW_SCORE", SqlType.double()),
            col("DISTANCE_KM", SqlType.double()),
            col("DISTANCE_BUCKET", SqlType.text()),
            col("DISTANCE_ORDER", SqlType.int()),
            col("BRAZILIAN_SEASON", SqlType.text()),
        ],
    )

    with HyperProcess(Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hyper:
        with Connection(
            hyper.endpoint, str(hyper_path), CreateMode.CREATE_AND_REPLACE
        ) as conn:
            conn.catalog.create_schema("Extract")
            conn.catalog.create_table(table_def)
            with Inserter(conn, table_def) as inserter:
                inserter.add_rows(rows)
                inserter.execute()
            count = conn.execute_scalar_query(f"SELECT COUNT(*) FROM {EXTRACT_TABLE}")
    print(f"Wrote {count} rows -> {hyper_path}")


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("build/olist_orders.hyper")
    rows = fetch_rows()
    print(f"Fetched {len(rows)} rows from Snowflake.")
    if rows:
        gmv = sum(r[4] for r in rows if r[4] is not None)
        cats = sorted({r[5] for r in rows})
        print(f"Total GMV (BRL): {gmv:,.0f} | distinct categories: {len(cats)}")
        print("Sample:", rows[0])
    write_hyper(rows, out)


if __name__ == "__main__":
    main()
