"""Phase-5 gate: every report page renders with real data (LIVE) and in TEST."""
from django.contrib.auth import get_user_model
from django.test import Client

u = get_user_model().objects.get(username="admin")
c = Client()
c.force_login(u)
s = c.session
s["channel"] = "LIVE"
s.save()

# data is January 2026 — point filters there
qs = "?from=2026-01-01&to=2026-01-31"
pages = [
    ("/", ""),
    ("/reports/monthly/", qs),
    ("/reports/daily/", qs + "&date=2026-01-10"),
    ("/reports/ads/", qs),
    ("/reports/ads/", qs + "&tab=campaign"),
    ("/reports/products/graph/", qs),
    ("/reports/commission/", qs),
    ("/pnl/yearly/", "?year=2026"),
    ("/pnl/monthly/", "?year=2026&month=1"),
]
for path, q in pages:
    r = c.get(path + q)
    body = r.content.decode()
    err = "Traceback" in body or r.status_code != 200
    print(("FAIL" if err else "OK  "), path + q, r.status_code, f"{len(body):,}B")

# sku drill-down for a real SKU
from apps.ingest.models import SalesLine
sku = SalesLine.objects.filter(channel="LIVE").exclude(sku_root="").first().sku_root
r = c.get(f"/products/{sku}/{qs}")
print("OK  " if r.status_code == 200 else "FAIL", f"/products/{sku}/", r.status_code)

# spot check: daily report totals for one day must equal matview sums
from django.db import connection
cur = connection.cursor()
cur.execute("""SELECT SUM(revenue), SUM(net_profit) FROM analytics_fact_daily
               WHERE channel='LIVE' AND date='2026-01-10'""")
rev, net = cur.fetchone()
r = c.get("/reports/daily/" + qs + "&date=2026-01-10&mode=all")
body = r.content.decode()
print("daily page contains matview revenue total:", f"{float(rev):,.0f}" in body,
      f"(expect True; rev={float(rev):,.0f} net={float(net):,.0f})")

# TEST channel renders empty-but-working pages
s["channel"] = "TEST"
s.save()
for path in ["/", "/reports/monthly/", "/pnl/yearly/"]:
    r = c.get(path)
    print(("OK  " if r.status_code == 200 else "FAIL"), "[TEST]", path, r.status_code)

print("PHASE 5 PAGE CHECK DONE")
