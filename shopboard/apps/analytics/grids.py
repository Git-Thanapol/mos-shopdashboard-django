"""AG Grid config builders — one per report table.

Day/body cells stay numeric (the JS formatter renders them); the 6-row monthly
footer and other pinned rows ship preformatted strings via fmt_n/fmt_p
("12,345.00 (10.50%)", zero → "-"). All computed values use 2 decimals;
only counts (orders/quantity) stay whole numbers.
"""
from datetime import timedelta

THAI_WD = ["จ.", "อ.", "พ.", "พฤ.", "ศ.", "ส.", "อา."]


def fmt_n(v):
    return f"{v:,.2f}" if v else "-"


def fmt_p(v):
    return f"{v:,.2f}%" if v else "-"


def val_pct(v, base):
    pct = v / base * 100 if base else 0
    return f"{fmt_n(v)} ({fmt_p(pct)})"


def monthly_grid(f, day_rows, cell, skus, names, footer, kpi) -> dict:
    """Day rows × SKU columns + the legacy 6-row footer (report_month.py:248-359)."""
    columns = [
        {"field": "date", "header": "วันที่", "type": "text", "hdr": "slate", "pinned": True, "width": 120, "sortText": True},
        {"field": "sales", "header": "ยอดขาย", "type": "money", "hdr": "slate", "pinned": True, "width": 95, "color": "sales"},
        {"field": "orders", "header": "ออเดอร์", "type": "int", "hdr": "slate", "pinned": True, "width": 75},
        {"field": "profit", "header": "กำไร", "type": "money", "hdr": "green", "pinned": True, "width": 95, "posGreen": True},
        {"field": "ppct", "header": "%กำไร", "type": "pct", "hdr": "green", "pinned": True, "width": 75, "posGreen": True},
        {"field": "ads", "header": "ค่าแอด", "type": "money", "hdr": "orange", "pinned": True, "width": 95, "color": "ads"},
        {"field": "apct", "header": "%แอด", "type": "pct", "hdr": "orange", "pinned": True, "width": 70, "color": "ads"},
        {"field": "opct", "header": "%ค่าดำเนินการ", "type": "pct", "hdr": "purple", "pinned": True, "width": 95},
        {"field": "cpct", "header": "%ค่าคอม", "type": "pct", "hdr": "teal", "pinned": True, "width": 80},
        {"field": "tpct", "header": "%ทุน", "type": "pct", "hdr": "cost", "pinned": True, "width": 70},
    ]
    keys = {s: f"k{i}" for i, s in enumerate(skus)}
    for s in skus:
        columns.append({
            "field": keys[s], "header": s, "sub": names.get(s, ""),
            "type": "money", "hdr": "blue", "width": 105,
        })

    rows = []
    d = f.date_from
    while d <= f.date_to:
        r = day_rows.get(d)
        rev = float(r["revenue"]) if r else 0
        net = float(r["net_profit"]) if r else 0
        ads = float(r["ads_amount"]) if r else 0
        ops = float(r["box_cost"] + r["delivery_cost"] + r["cod_cost"]) if r else 0
        com = float(r["com_admin"] + r["com_tele"]) if r else 0
        cost = float(r["product_cost"]) if r else 0
        row = {
            "date": f"{THAI_WD[d.weekday()]} {d:%d/%m/%y}",
            "sales": rev,
            "orders": int(r["orders"]) if r else 0,
            "profit": net,
            "ppct": net / rev * 100 if rev else 0,
            "ads": ads,
            "apct": ads / rev * 100 if rev else 0,
            "opct": ops / rev * 100 if rev else 0,
            "cpct": com / rev * 100 if rev else 0,
            "tpct": cost / rev * 100 if rev else 0,
        }
        for s in skus:
            row[keys[s]] = cell.get((d, s), 0)
        rows.append(row)
        d += timedelta(days=1)

    def sku_vals(field, with_pct=True):
        out = {}
        for s in skus:
            fr = footer.get(s)
            v = fr[field] if fr else 0
            sales = fr["revenue"] if fr else 0
            out[keys[s]] = val_pct(v, sales) if with_pct else v
        return out

    def ops_of(fr):
        return fr["box_cost"] + fr["delivery_cost"] + fr["cod_cost"] if fr else 0

    def com_of(fr):
        return fr["com_admin"] + fr["com_tele"] if fr else 0

    footer_rows = [
        {
            "rtype": "total", "date": "รวม",
            "sales": kpi["revenue"], "orders": kpi["orders"],
            "profit": kpi["net_profit"], "ppct": kpi["profit_pct"],
            "ads": kpi["ads_amount"], "apct": kpi["ads_pct"],
            "opct": kpi["ops_pct"], "cpct": kpi["com_pct"], "tpct": kpi["cost_pct"],
            **sku_vals("net_profit"),
        },
        {"rtype": "sales", "date": "รวมยอดขาย", "sales": kpi["revenue"], **sku_vals("revenue", with_pct=False)},
        {"rtype": "cost", "date": "รวมทุนสินค้า", "sales": val_pct(kpi["product_cost"], kpi["revenue"]), **sku_vals("product_cost")},
        {"rtype": "ads", "date": "รวมค่าแอด", "sales": val_pct(kpi["ads_amount"], kpi["revenue"]), **sku_vals("ads_amount")},
        {"rtype": "ops", "date": "รวมค่าดำเนินการ", "sales": val_pct(kpi["ops_cost"], kpi["revenue"]),
         **{keys[s]: val_pct(ops_of(footer.get(s)), footer.get(s)["revenue"] if footer.get(s) else 0) for s in skus}},
        {"rtype": "com", "date": "รวมค่าคอมมิชชั่น", "sales": val_pct(kpi["com_cost"], kpi["revenue"]),
         **{keys[s]: val_pct(com_of(footer.get(s)), footer.get(s)["revenue"] if footer.get(s) else 0) for s in skus}},
    ]
    return {"columns": columns, "rows": rows, "footer": footer_rows}


DAILY_COLUMNS = [
    {"field": "sku", "header": "SKU", "type": "text", "hdr": "slate", "pinned": True, "width": 120, "link": True, "sortText": True},
    {"field": "name", "header": "ชื่อสินค้า", "type": "text", "hdr": "slate", "pinned": True, "width": 190, "sortText": True},
    {"field": "orders", "header": "ออเดอร์", "type": "int", "hdr": "slate", "width": 75},
    {"field": "sales", "header": "ยอดขาย", "type": "money", "hdr": "slate", "width": 95, "color": "sales"},
    {"field": "cost", "header": "ทุนสินค้า", "type": "money", "hdr": "cost", "width": 90},
    {"field": "box", "header": "ค่ากล่อง", "type": "money", "hdr": "purple", "width": 80},
    {"field": "ship", "header": "ค่าส่ง", "type": "money", "hdr": "purple", "width": 80},
    {"field": "cod", "header": "COD", "type": "money", "hdr": "purple", "width": 80},
    {"field": "com_a", "header": "คอม Admin", "type": "money", "hdr": "teal", "width": 90},
    {"field": "com_t", "header": "คอม Tele", "type": "money", "hdr": "teal", "width": 90},
    {"field": "ads", "header": "ค่าแอด", "type": "money", "hdr": "orange", "width": 90, "color": "ads"},
    {"field": "profit", "header": "กำไร", "type": "money", "hdr": "green", "width": 95, "posGreen": True},
    {"field": "roas", "header": "ROAS", "type": "money2", "hdr": "green", "width": 75},
    {"field": "ppct", "header": "%กำไร", "type": "pct", "hdr": "green", "width": 75, "posGreen": True},
    {"field": "apct", "header": "%แอด", "type": "pct", "hdr": "orange", "width": 70, "color": "ads"},
    {"field": "opct", "header": "%ค่าดำเนินการ", "type": "pct", "hdr": "purple", "width": 95},
    {"field": "cpct", "header": "%ค่าคอม", "type": "pct", "hdr": "teal", "width": 80},
    {"field": "tpct", "header": "%ทุน", "type": "pct", "hdr": "cost", "width": 70},
]


def daily_grid(rows, kpi) -> dict:
    def map_row(r):
        rev = r["revenue"]
        ops = r["box_cost"] + r["delivery_cost"] + r["cod_cost"]
        com = r["com_admin"] + r["com_tele"]
        return {
            "sku": r["sku_root"], "name": r["name"], "orders": r["orders"], "sales": r["revenue"],
            "cost": r["product_cost"], "box": r["box_cost"], "ship": r["delivery_cost"],
            "cod": r["cod_cost"], "com_a": r["com_admin"], "com_t": r["com_tele"],
            "ads": r["ads_amount"], "profit": r["net_profit"], "roas": r["roas"],
            "ppct": r["profit_pct"], "apct": r["ads_pct"],
            "opct": ops / rev * 100 if rev else 0,
            "cpct": com / rev * 100 if rev else 0,
            "tpct": r["product_cost"] / rev * 100 if rev else 0,
        }

    footer = [{
        "rtype": "grand", "sku": "รวม", "name": "",
        "orders": kpi["orders"], "sales": kpi["revenue"], "cost": kpi["product_cost"],
        "box": kpi["box_cost"], "ship": kpi["delivery_cost"], "cod": kpi["cod_cost"],
        "com_a": kpi["com_admin"], "com_t": kpi["com_tele"], "ads": kpi["ads_amount"],
        "profit": kpi["net_profit"], "roas": "", "ppct": kpi["profit_pct"], "apct": kpi["ads_pct"],
        "opct": kpi["ops_pct"], "cpct": kpi["com_pct"], "tpct": kpi["cost_pct"],
    }]
    return {"columns": DAILY_COLUMNS, "rows": [map_row(r) for r in rows], "footer": footer}


def ads_matrix_grid(f, skus, names, cell) -> dict:
    """Legacy ads layout (report_ads.py:105-154): day rows × SKU columns,
    pinned orange ค่าแอดรวม column, navy รวม footer in #FF6633."""
    keys = {s: f"k{i}" for i, s in enumerate(skus)}
    columns = [
        {"field": "date", "header": "วันที่", "type": "text", "hdr": "slate", "pinned": True, "width": 120, "sortText": True},
        {"field": "ads", "header": "ค่าแอดรวม", "type": "money", "hdr": "orange", "pinned": True, "width": 100, "color": "ads"},
    ]
    for s in skus:
        columns.append({
            "field": keys[s], "header": s, "sub": names.get(s, ""),
            "type": "money", "hdr": "blue", "width": 100,
            "color": "ads", "posOnly": True,  # legacy: orange only when > 0
        })

    rows = []
    sku_totals = dict.fromkeys(skus, 0.0)
    d = f.date_from
    while d <= f.date_to:
        row = {"date": f"{THAI_WD[d.weekday()]} {d:%d/%m/%y}"}
        day_total = 0.0
        for s in skus:
            v = cell.get((d, s), 0.0)
            row[keys[s]] = v
            day_total += v
            sku_totals[s] += v
        row["ads"] = day_total
        rows.append(row)
        d += timedelta(days=1)

    footer = [{
        "rtype": "total", "date": "รวม",
        "ads": sum(sku_totals.values()),
        **{keys[s]: sku_totals[s] for s in skus},
    }]
    return {"columns": columns, "rows": rows, "footer": footer}


def ads_sku_grid(rows, total_ads, total_rev, avg_roas, total_net) -> dict:
    columns = [
        {"field": "sku", "header": "SKU", "type": "text", "hdr": "slate", "pinned": True, "width": 130, "link": True, "sortText": True},
        {"field": "name", "header": "ชื่อสินค้า", "type": "text", "hdr": "slate", "width": 230, "sortText": True},
        {"field": "ads", "header": "ค่าแอด", "type": "money", "hdr": "orange", "width": 100, "color": "ads"},
        {"field": "sales", "header": "ยอดขาย", "type": "money", "hdr": "slate", "width": 100, "color": "sales"},
        {"field": "apct", "header": "%แอด", "type": "pct", "hdr": "orange", "width": 80, "color": "ads"},
        {"field": "roas", "header": "ROAS", "type": "money2", "hdr": "green", "width": 80},
        {"field": "profit", "header": "กำไร", "type": "money", "hdr": "green", "width": 100, "posGreen": True},
    ]
    grid_rows = [{
        "sku": r["sku_root"], "name": r["name"], "ads": r["ads_amount"], "sales": r["revenue"],
        "apct": r["ads_pct"], "roas": r["roas"], "profit": r["net_profit"],
    } for r in rows]
    footer = [{
        "rtype": "grand", "sku": "รวม", "name": "", "ads": total_ads, "sales": total_rev,
        "apct": total_ads / total_rev * 100 if total_rev else 0, "roas": avg_roas, "profit": total_net,
    }]
    return {"columns": columns, "rows": grid_rows, "footer": footer}


def ads_campaign_grid(campaigns, master_skus) -> dict:
    columns = [
        {"field": "campaign", "header": "แคมเปญ", "type": "text", "hdr": "slate", "width": 420, "sortText": True},
        {"field": "sku", "header": "SKU", "type": "text", "hdr": "slate", "width": 130, "sortText": True},
        {"field": "cost", "header": "ค่าใช้จ่าย", "type": "money2", "hdr": "orange", "width": 110, "color": "ads"},
        {"field": "range", "header": "ช่วงวันที่", "type": "text", "hdr": "slate", "width": 150},
    ]
    rows = []
    total = 0.0
    for c in campaigns:
        cost = float(c["cost"])
        total += cost
        sku = c["sku_root"]
        if not sku:
            sku = "⚠️ ไม่ระบุ SKU"
        elif sku not in master_skus:
            sku = f"{sku} (ไม่พบใน Master)"
        rows.append({
            "campaign": c["campaign_name"],
            "sku": sku,
            "cost": cost,
            "range": f"{c['date_min']:%d/%m/%y} – {c['date_max']:%d/%m/%y}",
        })
    footer = [{"rtype": "grand", "campaign": "รวม", "sku": "", "cost": total, "range": ""}]
    return {"columns": columns, "rows": rows, "footer": footer}


def commission_grid(rows, total_admin, total_tele, total_rev) -> dict:
    columns = [
        {"field": "month", "header": "เดือน", "type": "text", "hdr": "slate", "width": 120, "sortText": True},
        {"field": "sku", "header": "SKU", "type": "text", "hdr": "slate", "pinned": True, "width": 130, "link": True, "sortText": True},
        {"field": "name", "header": "ชื่อสินค้า", "type": "text", "hdr": "slate", "width": 230, "sortText": True},
        {"field": "sales", "header": "ยอดขาย", "type": "money", "hdr": "slate", "width": 100, "color": "sales"},
        {"field": "com_a", "header": "คอม Admin", "type": "money2", "hdr": "teal", "width": 110},
        {"field": "com_t", "header": "คอม Telesale", "type": "money2", "hdr": "teal", "width": 110},
        {"field": "total", "header": "รวม", "type": "money2", "hdr": "green", "width": 110, "posGreen": True},
    ]
    grid_rows = [{
        "month": f"{r['month_label']} {r['year']:.0f}", "sku": r["sku_root"], "name": r["name"],
        "sales": r["revenue"], "com_a": r["com_admin"], "com_t": r["com_tele"], "total": r["total"],
    } for r in rows]
    footer = [{
        "rtype": "grand", "month": "รวม", "sku": "", "name": "", "sales": total_rev,
        "com_a": total_admin, "com_t": total_tele, "total": total_admin + total_tele,
    }]
    return {"columns": columns, "rows": grid_rows, "footer": footer}
