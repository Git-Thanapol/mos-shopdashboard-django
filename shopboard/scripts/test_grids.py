"""AG Grid conversion checks: pages render, payloads are real JSON objects."""
import json
import re

from django.contrib.auth import get_user_model
from django.test import Client

u = get_user_model().objects.get(username="admin")
c = Client()
c.force_login(u)
s = c.session
s["channel"] = "LIVE"
s.save()

qs = "?from=2026-01-01&to=2026-01-31"


def payload(body, el_id):
    m = re.search(rf'<script id="{el_id}" type="application/json">(.*?)</script>', body, re.S)
    return json.loads(m.group(1)) if m else None


checks = [
    ("/reports/monthly/" + qs, "grid-monthly-data"),
    ("/reports/daily/" + qs + "&date=2026-01-10", "grid-daily-data"),
    ("/reports/ads/" + qs, "grid-ads-data"),
    ("/reports/ads/" + qs + "&tab=campaign", "grid-campaigns-data"),
    ("/reports/commission/" + qs, "grid-com-data"),
]
for path, el in checks:
    r = c.get(path)
    body = r.content.decode()
    p = payload(body, el)
    ok = r.status_code == 200 and isinstance(p, dict) and p.get("columns") and isinstance(p.get("rows"), list)
    print("OK  " if ok else "FAIL", path, "| cols:", len(p["columns"]) if p else "-",
          "| rows:", len(p["rows"]) if p else "-", "| footer:", len(p.get("footer", [])) if p else "-")

# monthly grid specifics: 7 pinned + sku cols, 6 footer rows with rtypes
r = c.get("/reports/monthly/" + qs)
p = payload(r.content.decode(), "grid-monthly-data")
rtypes = [f["rtype"] for f in p["footer"]]
print("monthly footer rtypes:", rtypes, "(expect total/sales/cost/ads/ops/com)")
print("monthly pinned cols:", sum(1 for col in p["columns"] if col.get("pinned")), "(expect 7)")
print("sku col has sub name:", bool(p["columns"][7].get("sub") is not None))
tot = p["footer"][0]
print("footer total sales:", tot["sales"], "| sku cell sample:", p["footer"][0].get("k0"))

# chart payloads are objects too (json_script double-encoding fix)
r = c.get("/")
p = payload(r.content.decode(), "chart-data")
print("home chart payload is dict:", isinstance(p, dict), "| keys:", sorted(p.keys()) if isinstance(p, dict) else "-")
r = c.get("/pnl/yearly/?year=2026")
body = r.content.decode()
print("pnl chart dict:", isinstance(payload(body, "pnl-data"), dict),
      "| donut list:", isinstance(payload(body, "donut-data"), list))
print("GRID CHECK DONE")
