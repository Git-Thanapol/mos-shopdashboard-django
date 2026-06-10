"""SQL-first fact layer (plan §4).

- analytics_fact_lines: plain view, SalesLine ⟕ MasterItem (same channel),
  per-line costs. Master lookup: exact sku_norm, then sku_root fallback —
  EXCEPT the courier %-columns, which legacy only takes from the exact match
  (processing.py:113-114 cols_to_fill omits them). Do not "fix" this without
  re-running the parity check.
- analytics_fact_daily: materialized view, two-stage aggregation (§5.9):
  order grain first (box/delivery = MAX per order), then (channel, date,
  sku_root, shop) grain, FULL OUTER JOIN ads. Ads rows without a [SKU] token
  get the 'ไม่ระบุ SKU' bucket instead of being dropped (§5.8).
"""
from django.db import migrations

FACT_LINES = """
CREATE VIEW analytics_fact_lines AS
SELECT
    base.*,
    CASE WHEN base.is_cod AND base.ship_percent > 0
         THEN base.amount_paid * (base.ship_percent / 100) * 1.07
         ELSE 0 END AS cod_cost,
    CASE WHEN base.role = 'Admin'
         THEN base.amount_paid * (base.com_admin_pct / 100)
         ELSE 0 END AS com_admin,
    CASE WHEN base.role = 'Telesale'
         THEN base.amount_paid * (base.com_tele_pct / 100)
         ELSE 0 END AS com_tele
FROM (
    SELECT
        s.id,
        s.channel,
        s.file_id,
        s.shop_id,
        s.order_id,
        s.date,
        s.sku_norm,
        s.sku_root,
        s.quantity,
        s.amount_paid,
        s.role,
        s.is_cod,
        s.courier_norm,
        (m.id IS NOT NULL OR mr.id IS NOT NULL) AS master_matched,
        COALESCE(m.cost, mr.cost, 0) AS unit_cost,
        s.quantity * COALESCE(m.cost, mr.cost, 0) AS product_cost,
        COALESCE(m.box_cost, mr.box_cost, 0) AS box_cost_line,
        COALESCE(m.delivery_cost, mr.delivery_cost, 0) AS delivery_cost_line,
        COALESCE(m.com_admin_pct, mr.com_admin_pct, 0) AS com_admin_pct,
        COALESCE(m.com_tele_pct, mr.com_tele_pct, 0) AS com_tele_pct,
        -- courier %: exact-match master row ONLY (legacy parity; see docstring)
        CASE s.courier_norm
            WHEN 'J&T Express' THEN COALESCE(m.p_jnt, 0)
            WHEN 'Flash Express' THEN COALESCE(m.p_flash, 0)
            WHEN 'Kerry Express' THEN COALESCE(m.p_kerry, 0)
            WHEN 'ThailandPost' THEN COALESCE(m.p_thai_post, 0)
            WHEN 'DHL_1' THEN COALESCE(m.p_dhl, 0)
            WHEN 'SPX Express' THEN COALESCE(m.p_spx, 0)
            WHEN 'LEX TH' THEN COALESCE(m.p_lex, 0)
            ELSE COALESCE(m.p_std, 0)
        END AS ship_percent,
        COALESCE(NULLIF(m.name, ''), NULLIF(mr.name, ''), s.product_name) AS display_name,
        COALESCE(NULLIF(m.type, ''), NULLIF(mr.type, '')) AS product_type
    FROM ingest_salesline s
    LEFT JOIN catalog_masteritem m
        ON m.channel = s.channel AND m.sku = s.sku_norm
    LEFT JOIN catalog_masteritem mr
        ON mr.channel = s.channel AND mr.sku = s.sku_root
    WHERE s.status <> 'ยกเลิก'
      AND s.date IS NOT NULL
) base
"""

FACT_DAILY = """
CREATE MATERIALIZED VIEW analytics_fact_daily AS
WITH order_grain AS (
    SELECT
        channel,
        order_id,
        (array_agg(date ORDER BY id))[1] AS date,
        (array_agg(sku_root ORDER BY id))[1] AS sku_root,
        (array_agg(shop_id ORDER BY id))[1] AS shop_id,
        (array_agg(display_name ORDER BY id))[1] AS name,
        (array_agg(product_type ORDER BY id))[1] AS type,
        SUM(quantity) AS quantity,
        SUM(amount_paid) AS revenue,
        SUM(product_cost) AS product_cost,
        MAX(box_cost_line) AS box_cost,          -- box/delivery charged once per order (§5.9)
        MAX(delivery_cost_line) AS delivery_cost,
        SUM(cod_cost) AS cod_cost,
        SUM(com_admin) AS com_admin,
        SUM(com_tele) AS com_tele
    FROM analytics_fact_lines
    GROUP BY channel, order_id
),
sales_daily AS (
    SELECT
        channel, date, sku_root, shop_id,
        COUNT(*) AS orders,
        SUM(quantity) AS quantity,
        SUM(revenue) AS revenue,
        SUM(product_cost) AS product_cost,
        SUM(box_cost) AS box_cost,
        SUM(delivery_cost) AS delivery_cost,
        SUM(cod_cost) AS cod_cost,
        SUM(com_admin) AS com_admin,
        SUM(com_tele) AS com_tele,
        (array_agg(name ORDER BY order_id))[1] AS name,
        (array_agg(type ORDER BY order_id))[1] AS type
    FROM order_grain
    GROUP BY channel, date, sku_root, shop_id
),
ads_daily AS (
    SELECT
        channel, date,
        COALESCE(sku_root, 'ไม่ระบุ SKU') AS sku_root,
        shop_id,
        SUM(cost) AS ads_amount
    FROM ingest_adspend
    GROUP BY channel, date, COALESCE(sku_root, 'ไม่ระบุ SKU'), shop_id
)
SELECT
    j.*,
    (j.box_cost + j.delivery_cost + j.cod_cost + j.com_admin + j.com_tele) AS other_costs,
    (j.product_cost + j.box_cost + j.delivery_cost + j.cod_cost
        + j.com_admin + j.com_tele + j.ads_amount) AS total_cost,
    (j.revenue - j.product_cost - j.box_cost - j.delivery_cost - j.cod_cost
        - j.com_admin - j.com_tele - j.ads_amount) AS net_profit
FROM (
    SELECT
        COALESCE(s.channel, a.channel) AS channel,
        COALESCE(s.date, a.date) AS date,
        COALESCE(s.sku_root, a.sku_root) AS sku_root,
        COALESCE(s.shop_id, a.shop_id) AS shop_id,
        s.name,
        s.type,
        COALESCE(s.orders, 0) AS orders,
        COALESCE(s.quantity, 0) AS quantity,
        COALESCE(s.revenue, 0) AS revenue,
        COALESCE(s.product_cost, 0) AS product_cost,
        COALESCE(s.box_cost, 0) AS box_cost,
        COALESCE(s.delivery_cost, 0) AS delivery_cost,
        COALESCE(s.cod_cost, 0) AS cod_cost,
        COALESCE(s.com_admin, 0) AS com_admin,
        COALESCE(s.com_tele, 0) AS com_tele,
        COALESCE(a.ads_amount, 0) AS ads_amount
    FROM sales_daily s
    FULL OUTER JOIN ads_daily a
        ON a.channel = s.channel AND a.date = s.date
       AND a.sku_root = s.sku_root AND a.shop_id = s.shop_id
) j
"""

UNIQUE_INDEX = """
CREATE UNIQUE INDEX uniq_fact_daily_key
    ON analytics_fact_daily (channel, date, sku_root, shop_id)
"""

HELPER_INDEXES = """
CREATE INDEX idx_fact_daily_channel_date ON analytics_fact_daily (channel, date);
CREATE INDEX idx_fact_daily_sku ON analytics_fact_daily (channel, sku_root);
"""


class Migration(migrations.Migration):
    dependencies = [
        ("ingest", "0001_initial"),
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(FACT_LINES, "DROP VIEW IF EXISTS analytics_fact_lines"),
        migrations.RunSQL(FACT_DAILY, "DROP MATERIALIZED VIEW IF EXISTS analytics_fact_daily"),
        migrations.RunSQL(UNIQUE_INDEX, "DROP INDEX IF EXISTS uniq_fact_daily_key"),
        migrations.RunSQL(HELPER_INDEXES, "DROP INDEX IF EXISTS idx_fact_daily_channel_date; DROP INDEX IF EXISTS idx_fact_daily_sku"),
    ]
