"""Build a Tableau .hyper extract from the Olist dbt marts + curated views in Snowflake.

Writes TWO tables into one .hyper:
  - Extract.Extract : one row per order (order-level fact) — powers the KPI tiles,
    monthly GMV trend, GMV-by-state map, category treemap, and late-rate-by-distance.
  - Extract.Seller  : one row per seller (from the seller-performance mart) — powers
    the seller scatter (delivery time vs review, colored by late rate, sized by GMV).

Extract approach: the data is embedded in the workbook, so no live Snowflake
connection is needed at view time. Connection uses key-pair auth (same key the
Snowflake MCP uses). The corporate network MITM-intercepts TLS, so point OpenSSL
at the combined CA bundle before importing snowflake.connector.

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

# One row per order. is_complete_month flags whether the order's month is fully
# elapsed (so the monthly-trend line can exclude the partial current month).
ORDERS_QUERY = """
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
    IFF(DATE_TRUNC('MONTH', o.ORDER_PURCHASE_TIMESTAMP)
          < DATE_TRUNC('MONTH', CURRENT_DATE()), 1, 0)      AS is_complete_month,
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

SELLER_QUERY = """
SELECT SELLER_ID, SELLER_STATE, PRIMARY_CATEGORY,
       GMV_BRL, ORDER_COUNT, DELIVERED_ORDERS,
       AVG_DELIVERY_DAYS, AVG_REVIEW_SCORE, LATE_DELIVERY_RATE, REVIEW_COUNT
FROM OLIST.DBT_DEMO.MART_SELLER_PERFORMANCE
WHERE ORDER_COUNT >= 10   -- meaningful sellers only, for a clean scatter
"""

ORDERS_TABLE = TableName("Extract", "Extract")
SELLER_TABLE = TableName("Extract", "Seller")


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
        schema="PUBLIC",
    )


def fetch():
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(ORDERS_QUERY)
        orders = cur.fetchall()
        cur.execute(SELLER_QUERY)
        sellers = cur.fetchall()
    finally:
        conn.close()

    o_norm = []
    for (oid, cid, omonth, oyear, complete, gmv, cat, cstate, status, late, ddays,
         rscore, dist, dbucket, dorder, season) in orders:
        o_norm.append([
            str(oid), str(cid), omonth, int(oyear), int(complete),
            None if gmv is None else float(gmv), str(cat),
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

    s_norm = []
    for (sid, sstate, cat, gmv, ocount, dorders, adays, arev, lrate, rcount) in sellers:
        s_norm.append([
            str(sid),
            None if sstate is None else str(sstate),
            None if cat is None else str(cat),
            None if gmv is None else float(gmv),
            None if ocount is None else int(ocount),
            None if dorders is None else int(dorders),
            None if adays is None else float(adays),
            None if arev is None else float(arev),
            None if lrate is None else float(lrate),
            None if rcount is None else int(rcount),
        ])
    return o_norm, s_norm


def write_hyper(orders, sellers, hyper_path: Path) -> None:
    hyper_path.parent.mkdir(parents=True, exist_ok=True)
    if hyper_path.exists():
        hyper_path.unlink()

    def col(name, sqltype, nullable=Nullability.NULLABLE):
        return TableDefinition.Column(name, sqltype, nullable)

    orders_def = TableDefinition(ORDERS_TABLE, [
        col("ORDER_ID", SqlType.text(), Nullability.NOT_NULLABLE),
        col("CUSTOMER_ID", SqlType.text(), Nullability.NOT_NULLABLE),
        col("ORDER_MONTH", SqlType.date(), Nullability.NOT_NULLABLE),
        col("ORDER_YEAR", SqlType.int(), Nullability.NOT_NULLABLE),
        col("IS_COMPLETE_MONTH", SqlType.int(), Nullability.NOT_NULLABLE),
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
    ])
    seller_def = TableDefinition(SELLER_TABLE, [
        col("SELLER_ID", SqlType.text(), Nullability.NOT_NULLABLE),
        col("SELLER_STATE", SqlType.text()),
        col("PRIMARY_CATEGORY", SqlType.text()),
        col("GMV_BRL", SqlType.double()),
        col("ORDER_COUNT", SqlType.big_int()),
        col("DELIVERED_ORDERS", SqlType.big_int()),
        col("AVG_DELIVERY_DAYS", SqlType.double()),
        col("AVG_REVIEW_SCORE", SqlType.double()),
        col("LATE_DELIVERY_RATE", SqlType.double()),
        col("REVIEW_COUNT", SqlType.big_int()),
    ])

    with HyperProcess(Telemetry.DO_NOT_SEND_USAGE_DATA_TO_TABLEAU) as hyper:
        with Connection(hyper.endpoint, str(hyper_path), CreateMode.CREATE_AND_REPLACE) as conn:
            conn.catalog.create_schema("Extract")
            conn.catalog.create_table(orders_def)
            conn.catalog.create_table(seller_def)
            with Inserter(conn, orders_def) as ins:
                ins.add_rows(orders)
                ins.execute()
            with Inserter(conn, seller_def) as ins:
                ins.add_rows(sellers)
                ins.execute()
            no = conn.execute_scalar_query(f"SELECT COUNT(*) FROM {ORDERS_TABLE}")
            ns = conn.execute_scalar_query(f"SELECT COUNT(*) FROM {SELLER_TABLE}")
    print(f"Wrote {no} orders + {ns} sellers -> {hyper_path}")


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("build/olist_orders.hyper")
    orders, sellers = fetch()
    gmv = sum(r[5] for r in orders if r[5] is not None)
    print(f"Fetched {len(orders)} orders (GMV R$ {gmv:,.0f}) + {len(sellers)} sellers.")
    write_hyper(orders, sellers, out)


if __name__ == "__main__":
    main()
