import json
from datetime import date, timedelta

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.catalog.models import FixCost, MasterItem, ProductTag
from apps.core import channels
from apps.core.decorators import channel_required
from apps.core.thai import THAI_MONTHS, thai_date

from . import queries
from .filters import FilterState


@login_required
def channel_select(request):
    return render(request, "analytics/channel_select.html", {"channels": channels.Channel})


@login_required
@require_POST
def channel_activate(request):
    value = request.POST.get("channel", "")
    if value in channels.Channel.values:
        channels.activate(request, value)
        return redirect("analytics:home")
    return redirect("analytics:channel_select")


# ---------------------------------------------------------------- shared ctx
def _base_ctx(request):
    channel = channels.current(request)
    f = FilterState.from_request(request)
    ids = queries.shop_ids(channel, f.shops)
    skus, totals = queries.resolve_skus(channel, f, ids)
    names = queries.sku_names(channel)
    skus_all = sorted(set(names) | set(totals))
    return {
        "skus_all": [(s, names.get(s, "")) for s in skus_all],
        "channel": channel,
        "f": f,
        "shop_ids": ids,
        "skus": skus,
        "sku_totals": totals,
        "names": names,
        "all_shops": queries.shops(channel),
        "categories": queries.category_options(channel),
        "freshness": queries.freshness(channel),
        "tag_groups": _tag_groups(),
    }


def _tag_groups():
    from apps.catalog.models import TagGroup

    return TagGroup.objects.filter(is_visible=True).prefetch_related("tags")


def _fmt_rows(rows, names):
    out = []
    for r in rows:
        d = {k: float(v) if v is not None and not isinstance(v, (str, date)) else v for k, v in r.items()}
        rev = d.get("revenue", 0)
        d["profit_pct"] = d.get("net_profit", 0) / rev * 100 if rev else 0
        d["ads_pct"] = d.get("ads_amount", 0) / rev * 100 if rev else 0
        d["roas"] = rev / d["ads_amount"] if d.get("ads_amount") else 0
        if "sku_root" in d:
            d["name"] = names.get(d["sku_root"], "")
        out.append(d)
    return out


# ------------------------------------------------------------------- pages
@channel_required
def home(request):
    ctx = _base_ctx(request)
    channel, ids = ctx["channel"], ctx["shop_ids"]
    today = timezone.localdate()

    class Today:
        date_from = today
        date_to = today

    class Yesterday:
        date_from = today - timedelta(days=1)
        date_to = today - timedelta(days=1)

    class Last30:
        date_from = today - timedelta(days=29)
        date_to = today

    class ThisMonth:
        date_from = today.replace(day=1)
        date_to = today

    all_skus = sorted(set(queries.sku_totals(channel, Last30, ids)))
    k_today = queries.kpis(channel, Today, ids, all_skus or [""])
    k_yda = queries.kpis(channel, Yesterday, ids, all_skus or [""])
    series = queries.per_day(channel, Last30, ids, all_skus or [""])

    month_rows = _fmt_rows(queries.per_sku(channel, ThisMonth, ids, all_skus or [""]), ctx["names"])
    top_profit = [r for r in month_rows if r["net_profit"] > 0][:10]
    top_loss = sorted([r for r in month_rows if r["net_profit"] < 0], key=lambda r: r["net_profit"])[:10]

    # alerts
    loss_count = sum(1 for r in month_rows if r["net_profit"] < 0)
    master_skus = set(MasterItem.objects.filter(channel=channel).values_list("sku", flat=True))
    missing_master = [r["sku_root"] for r in month_rows
                      if r["sku_root"] not in master_skus and r["sku_root"] != queries.NO_SKU_BUCKET]

    chart = {
        "dates": [r["date"].isoformat() for r in series],
        "revenue": [float(r["revenue"]) for r in series],
        "profit": [float(r["net_profit"]) for r in series],
    }
    ctx.update(
        today_label=thai_date(today),
        k_today=k_today,
        k_yda=k_yda,
        top_profit=top_profit,
        top_loss=top_loss,
        loss_count=loss_count,
        missing_master=missing_master[:10],
        missing_master_count=len(missing_master),
        chart_json=json.dumps(chart),
    )
    return render(request, "analytics/home.html", ctx)


@channel_required
def report_monthly(request):
    ctx = _base_ctx(request)
    channel, f, ids, skus = ctx["channel"], ctx["f"], ctx["shop_ids"], ctx["skus"]
    skus = skus or [""]
    ctx["kpi"] = queries.kpis(channel, f, ids, skus)
    day_rows = {r["date"]: r for r in queries.per_day(channel, f, ids, skus)}
    cell = queries.per_day_sku_net(channel, f, ids, skus)

    matrix = []
    d = f.date_from
    while d <= f.date_to:
        r = day_rows.get(d)
        rev = float(r["revenue"]) if r else 0
        net = float(r["net_profit"]) if r else 0
        ads = float(r["ads_amount"]) if r else 0
        matrix.append({
            "date": d,
            "orders": int(r["orders"]) if r else 0,
            "revenue": rev,
            "net": net,
            "p_pct": net / rev * 100 if rev else 0,
            "ads": ads,
            "a_pct": ads / rev * 100 if rev else 0,
            "cells": [cell.get((d, s), 0) for s in ctx["skus"]],
        })
        d += timedelta(days=1)

    footer = {r["sku_root"]: r for r in _fmt_rows(queries.per_sku(channel, f, ids, skus), ctx["names"])}
    ctx["matrix"] = matrix
    ctx["sku_headers"] = [(s, ctx["names"].get(s, "")) for s in ctx["skus"]]

    # 6-row footer block (legacy report_month.py:248-359): per-SKU totals with
    # (% of that SKU's sales); ops = box+delivery+COD, com = admin+telesale
    cells = []
    for s in ctx["skus"]:
        d = footer.get(s)
        sales = d["revenue"] if d else 0
        ops = (d["box_cost"] + d["delivery_cost"] + d["cod_cost"]) if d else 0
        com = (d["com_admin"] + d["com_tele"]) if d else 0
        cost = d["product_cost"] if d else 0
        ads = d["ads_amount"] if d else 0
        net = d["net_profit"] if d else 0

        def _pct(v):
            return v / sales * 100 if sales else 0

        cells.append({
            "sales": sales, "cost": cost, "ads": ads, "ops": ops, "com": com, "net": net,
            "net_pct": _pct(net), "cost_pct": _pct(cost), "ads_pct": _pct(ads),
            "ops_pct": _pct(ops), "com_pct": _pct(com),
        })
    ctx["footer_cells"] = cells
    return render(request, "analytics/report_monthly.html", ctx)


@channel_required
def report_daily(request):
    ctx = _base_ctx(request)
    channel, f, ids, skus = ctx["channel"], ctx["f"], ctx["shop_ids"], ctx["skus"]
    try:
        day = date.fromisoformat(request.GET.get("date", ""))
    except ValueError:
        day = min(timezone.localdate(), f.date_to)

    rows = _fmt_rows(queries.per_sku(channel, f, ids, skus or [""], day=day), ctx["names"])

    sort = request.GET.get("sort", "net_profit")
    direction = request.GET.get("dir", "desc")
    if rows and sort in rows[0]:
        rows.sort(key=lambda r: (r[sort] is None, r[sort]), reverse=(direction == "desc"))

    class DayRange:
        date_from = day
        date_to = day

    ctx.update(
        day=day,
        day_label=thai_date(day, short=False),
        prev_day=day - timedelta(days=1),
        next_day=day + timedelta(days=1),
        rows=rows,
        kpi=queries.kpis(channel, DayRange, ids, skus or [""]),
        sort=sort,
        dir=direction,
    )
    return render(request, "analytics/report_daily.html", ctx)


@channel_required
def report_ads(request):
    ctx = _base_ctx(request)
    channel, f, ids, skus = ctx["channel"], ctx["f"], ctx["shop_ids"], ctx["skus"]
    rows = [r for r in _fmt_rows(queries.per_sku(channel, f, ids, skus or [""]), ctx["names"])
            if r["ads_amount"] or r["revenue"]]
    rows.sort(key=lambda r: r["ads_amount"], reverse=True)
    total_ads = sum(r["ads_amount"] for r in rows)
    total_rev = sum(r["revenue"] for r in rows)
    campaigns = queries.ads_campaigns(channel, f, ids)
    master_skus = set(MasterItem.objects.filter(channel=channel).values_list("sku", flat=True))
    ctx.update(
        rows=rows,
        kpi=queries.kpis(channel, f, ids, skus or [""]),
        total_ads=total_ads,
        avg_roas=total_rev / total_ads if total_ads else 0,
        campaigns=campaigns,
        n_campaigns=len({c["campaign_name"] for c in campaigns}),
        master_skus=master_skus,
        tab=request.GET.get("tab", "sku"),
    )
    return render(request, "analytics/report_ads.html", ctx)


@channel_required
def product_graph(request):
    ctx = _base_ctx(request)
    channel, f, ids = ctx["channel"], ctx["f"], ctx["shop_ids"]
    metric = request.GET.get("metric", "revenue")
    skus = ctx["skus"][:12]  # cap series for readability (UX plan §5.5)
    ts = queries.timeseries(channel, f, ids, skus or [""], metric)
    series = [{"name": s, "data": ts["series"].get(s, [])} for s in skus]
    totals = _fmt_rows(queries.per_sku(channel, f, ids, skus or [""]), ctx["names"])
    ctx.update(
        metric=metric,
        capped=len(ctx["skus"]) > 12,
        graph_json=json.dumps({"dates": ts["dates"], "series": series}),
        bar_json=json.dumps({
            "skus": [r["sku_root"] for r in totals],
            "revenue": [r["revenue"] for r in totals],
            "quantity": [r["quantity"] for r in totals],
        }),
        metric_options=[
            ("revenue", "ยอดขาย"), ("net_profit", "กำไร"),
            ("ads_amount", "ค่าแอด"), ("orders", "ออเดอร์"),
        ],
    )
    return render(request, "analytics/product_graph.html", ctx)


def _pnl_ctx(request, year, months):
    ctx = _base_ctx(request)
    channel, ids = ctx["channel"], ctx["shop_ids"]
    rows = {r["month"]: r for r in queries.per_month(channel, ids, year)}
    fix = {}
    if channel == channels.Channel.LIVE:  # FixCost is LIVE-only (plan §13)
        for fc in FixCost.objects.filter(year=year, month__in=months):
            fix[fc.month] = fix.get(fc.month, 0) + float(fc.amount)

    table = []
    for m in months:
        r = rows.get(m)
        if not r:
            continue
        d = {k: float(v or 0) for k, v in r.items()}
        d["month_label"] = THAI_MONTHS[m - 1]
        d["fix_cost"] = fix.get(m, 0)
        d["gross"] = d["revenue"] - d["product_cost"]
        d["net_after_fix"] = d["net_profit"] - d["fix_cost"]
        table.append(d)

    total = {k: sum(r[k] for r in table) for k in table[0] if k != "month_label"} if table else {}
    if total:
        total["month_label"] = "รวม"
    ctx.update(year=year, table=table, total=total,
               years=queries.years_available(channel) or [year])
    return ctx


@channel_required
def pnl_yearly(request):
    year = int(request.GET.get("year", timezone.localdate().year))
    ctx = _pnl_ctx(request, year, list(range(1, 13)))
    ctx["chart_json"] = json.dumps({
        "months": [r["month_label"] for r in ctx["table"]],
        "revenue": [r["revenue"] for r in ctx["table"]],
        "profit": [r["net_after_fix"] for r in ctx["table"]],
    })
    t = ctx["total"]
    ctx["donut_json"] = json.dumps([
        {"name": "ทุนสินค้า", "value": t.get("product_cost", 0)},
        {"name": "ค่าดำเนินการ", "value": t.get("box_cost", 0) + t.get("delivery_cost", 0) + t.get("cod_cost", 0)},
        {"name": "ค่าคอมมิชชั่น", "value": t.get("com_admin", 0) + t.get("com_tele", 0)},
        {"name": "ค่าโฆษณา", "value": t.get("ads_amount", 0)},
        {"name": "ค่าใช้จ่ายคงที่", "value": t.get("fix_cost", 0)},
    ]) if t else "[]"
    return render(request, "analytics/pnl_yearly.html", ctx)


@channel_required
def pnl_monthly(request):
    today = timezone.localdate()
    year = int(request.GET.get("year", today.year))
    month = int(request.GET.get("month", today.month))
    ctx = _pnl_ctx(request, year, [month])
    ctx.update(month=month, month_label=THAI_MONTHS[month - 1], months=list(enumerate(THAI_MONTHS, 1)))
    row = ctx["table"][0] if ctx["table"] else None
    ctx["row"] = row
    if row and ctx["channel"] == channels.Channel.LIVE:
        ctx["fixcosts"] = FixCost.objects.filter(year=year, month=month)
    return render(request, "analytics/pnl_monthly.html", ctx)


@channel_required
def commission(request):
    ctx = _base_ctx(request)
    channel, f, ids = ctx["channel"], ctx["f"], ctx["shop_ids"]
    role = request.GET.get("role", "all")
    rows = queries.commission_rows(channel, f, ids)
    out = []
    for r in rows:
        d = {k: float(v) if k not in ("sku_root",) else v for k, v in r.items()}
        d["name"] = ctx["names"].get(d["sku_root"], "")
        d["month_label"] = THAI_MONTHS[int(d["month"]) - 1]
        d["total"] = d["com_admin"] + d["com_tele"]
        if role == "admin" and not d["com_admin"]:
            continue
        if role == "tele" and not d["com_tele"]:
            continue
        out.append(d)
    total_admin = sum(r["com_admin"] for r in out)
    total_tele = sum(r["com_tele"] for r in out)
    total_rev = sum(r["revenue"] for r in out)
    ctx.update(rows=out, role=role, total_admin=total_admin, total_tele=total_tele,
               com_pct=(total_admin + total_tele) / total_rev * 100 if total_rev else 0)
    return render(request, "analytics/commission.html", ctx)


@channel_required
def sku_detail(request, sku):
    ctx = _base_ctx(request)
    channel, f, ids = ctx["channel"], ctx["f"], ctx["shop_ids"]
    rows = _fmt_rows(queries.per_sku(channel, f, ids, [sku]), ctx["names"])
    if not rows and not MasterItem.objects.filter(channel=channel, sku=sku).exists():
        raise Http404
    ts = queries.timeseries(channel, f, ids, [sku], "revenue")
    ts_net = queries.timeseries(channel, f, ids, [sku], "net_profit")
    ctx.update(
        sku=sku,
        name=ctx["names"].get(sku, sku),
        summary=rows[0] if rows else None,
        master=MasterItem.objects.filter(channel=channel, sku=sku).first(),
        tags=list(
            ProductTag.objects.filter(channel=channel, sku=sku).select_related("tag", "tag__group")
        ),
        chart_json=json.dumps({
            "dates": ts["dates"],
            "revenue": ts["series"].get(sku, []),
            "profit": [ts_net["series"].get(sku, [0] * len(ts_net["dates"]))[i]
                       for i in range(len(ts_net["dates"]))],
        }),
    )
    return render(request, "analytics/sku_detail.html", ctx)
