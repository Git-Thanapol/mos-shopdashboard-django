"""All report SQL lives here (plan §4.4). Every query is strictly channel-scoped."""
from collections import defaultdict
from datetime import date

from django.db import connection

from apps.catalog.models import MasterItem, ProductTag
from apps.ingest.models import Shop

NO_SKU_BUCKET = "ไม่ระบุ SKU"


def _rows(sql, params) -> list[dict]:
    with connection.cursor() as cur:
        cur.execute(sql, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def shops(channel) -> list[Shop]:
    return list(Shop.objects.filter(channel=channel, is_active=True))


def shop_ids(channel, names: list[str]) -> list[int]:
    qs = Shop.objects.filter(channel=channel, is_active=True)
    if names:
        qs = qs.filter(name__in=names)
    return list(qs.values_list("id", flat=True))


def sku_names(channel) -> dict[str, str]:
    """sku_root → display name (master wins over fact-layer name)."""
    names: dict[str, str] = {}
    for r in _rows(
        "SELECT DISTINCT sku_root, name FROM analytics_fact_daily WHERE channel = %s AND name IS NOT NULL",
        [channel],
    ):
        names[r["sku_root"]] = r["name"]
    for sku, name in MasterItem.objects.filter(channel=channel).values_list("sku", "name"):
        if name:
            names[sku] = name
    return names


def sku_types(channel) -> dict[str, str]:
    types = {}
    for r in _rows(
        "SELECT DISTINCT sku_root, type FROM analytics_fact_daily WHERE channel = %s AND type IS NOT NULL",
        [channel],
    ):
        types[r["sku_root"]] = r["type"]
    for sku, t in MasterItem.objects.filter(channel=channel).exclude(type="").values_list("sku", "type"):
        types[sku] = t
    return types


def category_options(channel) -> list[str]:
    return sorted({t for t in sku_types(channel).values() if t and t.strip() not in ("", "nan")})


# ------------------------------------------------------------- SKU selection
def sku_totals(channel, f, ids) -> dict[str, dict]:
    """Per-SKU totals over the filtered range — drives mode/% filters."""
    rows = _rows(
        """
        SELECT sku_root, SUM(revenue) AS revenue, SUM(ads_amount) AS ads, SUM(net_profit) AS net
        FROM analytics_fact_daily
        WHERE channel = %s AND date BETWEEN %s AND %s AND shop_id = ANY(%s)
        GROUP BY sku_root
        """,
        [channel, f.date_from, f.date_to, ids],
    )
    return {r["sku_root"]: r for r in rows}


def resolve_skus(channel, f, ids) -> tuple[list[str], dict[str, dict]]:
    """Replicates the legacy SKU-selection pipeline (report_month.py:124-158):
    mode → explicit picks → category → tag → %-range filters."""
    totals = sku_totals(channel, f, ids)

    if f.skus:
        selected = [s for s in f.skus]
    elif f.mode == "profit":
        selected = [s for s, t in totals.items() if t["net"] > 0]
    elif f.mode == "loss":
        selected = [s for s, t in totals.items() if t["net"] < 0]
    elif f.mode == "all":
        selected = sorted(set(totals) | set(sku_names(channel)))
    else:  # moving
        selected = [s for s, t in totals.items() if t["revenue"] > 0 or t["ads"] > 0]

    if f.category:
        types = sku_types(channel)
        selected = [s for s in selected if types.get(s, "") == f.category]
    if f.tag:
        tagged = set(
            ProductTag.objects.filter(channel=channel, tag_id=f.tag).values_list("sku", flat=True)
        )
        selected = [s for s in selected if s in tagged or s.split("-")[0] in tagged]

    if any(v is not None for v in (f.pmin, f.pmax, f.amin, f.amax)):
        kept = []
        for s in selected:
            t = totals.get(s)
            rev = float(t["revenue"]) if t else 0.0
            p_pct = (float(t["net"]) / rev * 100) if t and rev else 0.0
            a_pct = (float(t["ads"]) / rev * 100) if t and rev else 0.0
            if f.pmin is not None and p_pct < f.pmin:
                continue
            if f.pmax is not None and p_pct > f.pmax:
                continue
            if f.amin is not None and a_pct < f.amin:
                continue
            if f.amax is not None and a_pct > f.amax:
                continue
            kept.append(s)
        selected = kept

    return sorted(selected), totals


# ------------------------------------------------------------------ measures
MEASURES = """
    SUM(orders) AS orders, SUM(quantity) AS quantity, SUM(revenue) AS revenue,
    SUM(product_cost) AS product_cost, SUM(box_cost) AS box_cost,
    SUM(delivery_cost) AS delivery_cost, SUM(cod_cost) AS cod_cost,
    SUM(com_admin) AS com_admin, SUM(com_tele) AS com_tele,
    SUM(ads_amount) AS ads_amount, SUM(other_costs) AS other_costs,
    SUM(total_cost) AS total_cost, SUM(net_profit) AS net_profit
"""


def kpis(channel, f, ids, skus) -> dict:
    rows = _rows(
        f"""
        SELECT {MEASURES} FROM analytics_fact_daily
        WHERE channel = %s AND date BETWEEN %s AND %s AND shop_id = ANY(%s) AND sku_root = ANY(%s)
        """,
        [channel, f.date_from, f.date_to, ids, skus],
    )
    r = {k: float(v or 0) for k, v in rows[0].items()}
    r["ops_cost"] = r["box_cost"] + r["delivery_cost"] + r["cod_cost"]
    r["com_cost"] = r["com_admin"] + r["com_tele"]
    rev = r["revenue"]
    r["profit_pct"] = r["net_profit"] / rev * 100 if rev else 0
    r["ads_pct"] = r["ads_amount"] / rev * 100 if rev else 0
    r["cost_pct"] = r["product_cost"] / rev * 100 if rev else 0
    r["ops_pct"] = r["ops_cost"] / rev * 100 if rev else 0
    r["com_pct"] = r["com_cost"] / rev * 100 if rev else 0
    return r


def per_day(channel, f, ids, skus) -> list[dict]:
    return _rows(
        f"""
        SELECT date, {MEASURES} FROM analytics_fact_daily
        WHERE channel = %s AND date BETWEEN %s AND %s AND shop_id = ANY(%s) AND sku_root = ANY(%s)
        GROUP BY date ORDER BY date
        """,
        [channel, f.date_from, f.date_to, ids, skus],
    )


def per_day_sku_net(channel, f, ids, skus) -> dict[tuple, float]:
    rows = _rows(
        """
        SELECT date, sku_root, SUM(net_profit) AS net FROM analytics_fact_daily
        WHERE channel = %s AND date BETWEEN %s AND %s AND shop_id = ANY(%s) AND sku_root = ANY(%s)
        GROUP BY date, sku_root
        """,
        [channel, f.date_from, f.date_to, ids, skus],
    )
    return {(r["date"], r["sku_root"]): float(r["net"]) for r in rows}


def per_sku(channel, f, ids, skus, day: date | None = None) -> list[dict]:
    d_from, d_to = (day, day) if day else (f.date_from, f.date_to)
    return _rows(
        f"""
        SELECT sku_root, {MEASURES} FROM analytics_fact_daily
        WHERE channel = %s AND date BETWEEN %s AND %s AND shop_id = ANY(%s) AND sku_root = ANY(%s)
        GROUP BY sku_root ORDER BY SUM(net_profit) DESC
        """,
        [channel, d_from, d_to, ids, skus],
    )


def timeseries(channel, f, ids, skus, metric: str) -> dict:
    """Per-SKU daily series for the product graph. metric ∈ revenue|net_profit|ads_amount|orders|quantity."""
    allowed = {"revenue", "net_profit", "ads_amount", "orders", "quantity"}
    if metric not in allowed:
        metric = "revenue"
    rows = _rows(
        f"""
        SELECT date, sku_root, SUM({metric}) AS v FROM analytics_fact_daily
        WHERE channel = %s AND date BETWEEN %s AND %s AND shop_id = ANY(%s) AND sku_root = ANY(%s)
        GROUP BY date, sku_root ORDER BY date
        """,
        [channel, f.date_from, f.date_to, ids, skus],
    )
    dates = sorted({r["date"] for r in rows})
    by_sku: dict[str, dict] = defaultdict(dict)
    for r in rows:
        by_sku[r["sku_root"]][r["date"]] = float(r["v"])
    return {
        "dates": [d.isoformat() for d in dates],
        "series": {s: [vals.get(d, 0) for d in dates] for s, vals in by_sku.items()},
    }


def per_month(channel, ids, year: int) -> list[dict]:
    return _rows(
        f"""
        SELECT EXTRACT(MONTH FROM date)::int AS month, {MEASURES}
        FROM analytics_fact_daily
        WHERE channel = %s AND EXTRACT(YEAR FROM date) = %s AND shop_id = ANY(%s)
        GROUP BY 1 ORDER BY 1
        """,
        [channel, year, ids],
    )


def commission_rows(channel, f, ids) -> list[dict]:
    return _rows(
        """
        SELECT sku_root, EXTRACT(YEAR FROM date)::int AS year, EXTRACT(MONTH FROM date)::int AS month,
               SUM(revenue) AS revenue, SUM(com_admin) AS com_admin, SUM(com_tele) AS com_tele
        FROM analytics_fact_daily
        WHERE channel = %s AND date BETWEEN %s AND %s AND shop_id = ANY(%s)
        GROUP BY 1, 2, 3
        HAVING SUM(com_admin) <> 0 OR SUM(com_tele) <> 0
        ORDER BY 2, 3, SUM(com_admin) + SUM(com_tele) DESC
        """,
        [channel, f.date_from, f.date_to, ids],
    )


def ads_campaigns(channel, f, ids) -> list[dict]:
    return _rows(
        """
        SELECT campaign_name, sku_root, COUNT(*) AS rows, SUM(cost) AS cost,
               MIN(date) AS date_min, MAX(date) AS date_max
        FROM ingest_adspend
        WHERE channel = %s AND date BETWEEN %s AND %s AND shop_id = ANY(%s)
        GROUP BY campaign_name, sku_root ORDER BY SUM(cost) DESC LIMIT 500
        """,
        [channel, f.date_from, f.date_to, ids],
    )


def years_available(channel) -> list[int]:
    rows = _rows(
        "SELECT DISTINCT EXTRACT(YEAR FROM date)::int AS y FROM analytics_fact_daily WHERE channel = %s ORDER BY 1 DESC",
        [channel],
    )
    return [r["y"] for r in rows]


def freshness(channel):
    from apps.ingest.models import UploadedFile

    return (
        UploadedFile.objects.filter(shop__channel=channel, status="PROCESSED")
        .select_related("uploaded_by")
        .order_by("-uploaded_at")
        .first()
    )
