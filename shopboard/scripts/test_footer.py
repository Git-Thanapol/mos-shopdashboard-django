"""Verify the monthly-report footer block matches the matview grand totals."""
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client

u = get_user_model().objects.get(username="admin")
c = Client()
c.force_login(u)
s = c.session
s["channel"] = "LIVE"
s.save()

r = c.get("/reports/monthly/?from=2026-01-01&to=2026-01-31&mode=moving")
body = r.content.decode()
print("status:", r.status_code)
for label in [">รวม<", "รวมยอดขาย", "รวมทุนสินค้า", "รวมค่าแอด", "รวมค่าดำเนินการ", "รวมค่าคอมมิชชั่น"]:
    print(label, "->", label in body)

cur = connection.cursor()
cur.execute(
    """SELECT SUM(revenue), SUM(product_cost),
              SUM(box_cost)+SUM(delivery_cost)+SUM(cod_cost),
              SUM(com_admin)+SUM(com_tele), SUM(ads_amount), SUM(net_profit)
       FROM analytics_fact_daily WHERE channel='LIVE'
         AND date BETWEEN '2026-01-01' AND '2026-01-31'"""
)
rev, cost, ops, com, ads, net = [float(x) for x in cur.fetchone()]
for name, v in [("sales", rev), ("cost", cost), ("ops", ops), ("com", com), ("ads", ads), ("net", net)]:
    txt = f"{v:,.0f}"
    print(f"grand {name} = {txt} in page:", txt in body)
