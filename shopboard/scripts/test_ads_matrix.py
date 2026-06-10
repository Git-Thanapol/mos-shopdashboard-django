"""Ads day×SKU matrix checks (legacy report_ads.py parity)."""
import json
import re

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client

u = get_user_model().objects.get(username="admin")
c = Client()
c.force_login(u)
s = c.session
s["channel"] = "LIVE"
s.save()

r = c.get("/reports/ads/?from=2026-01-01&to=2026-01-31&mode=moving")
body = r.content.decode()
m = re.search(r'<script id="grid-ads-matrix-data" type="application/json">(.*?)</script>', body, re.S)
p = json.loads(m.group(1))
print("status:", r.status_code, "| default tab is day matrix:", m is not None)
print("cols:", len(p["columns"]), "(2 pinned + SKUs) | rows:", len(p["rows"]), "(expect 31 days)")
print("pinned:", [c0["field"] for c0 in p["columns"] if c0.get("pinned")])

# day total column == sum of sku cells for that day
row0 = p["rows"][9]  # 10 Jan
sku_keys = [c0["field"] for c0 in p["columns"] if c0["field"].startswith("k")]
cell_sum = sum(row0[k] for k in sku_keys)
print("day ads == sum of cells:", abs(row0["ads"] - cell_sum) < 0.01, f"({row0['ads']:.2f})")

# footer total == matview ads sum for the period
cur = connection.cursor()
cur.execute("""SELECT SUM(ads_amount) FROM analytics_fact_daily
               WHERE channel='LIVE' AND date BETWEEN '2026-01-01' AND '2026-01-31'""")
db_total = float(cur.fetchone()[0])
foot = p["footer"][0]
print("footer rtype:", foot["rtype"], "| total:", f"{foot['ads']:.2f}",
      "| matches matview:", abs(foot["ads"] - db_total) < 0.01, f"(db={db_total:.2f})")

# other tabs still render
for tab in ("sku", "campaign"):
    r = c.get(f"/reports/ads/?from=2026-01-01&to=2026-01-31&tab={tab}")
    print(f"tab {tab}:", r.status_code)
print("ADS MATRIX CHECK DONE")
