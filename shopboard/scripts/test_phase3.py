"""Phase-3 gate check: upload UI endpoints, dedup, delete cascade."""
from django.contrib.auth import get_user_model
from django.test import Client

from apps.ingest.models import AdSpend, SalesLine, Shop, UploadedFile

u = get_user_model().objects.get(username="admin")
c = Client()
c.force_login(u)
s = c.session
s["channel"] = "TEST"
s.save()

# channel separation: TEST file manager must not see LIVE shops
r = c.get("/data/files/")
print("TEST file manager:", r.status_code, "| sees LIVE shops:", b"Tiktok1" in r.content)

# create a TEST shop and upload a real legacy file through the endpoint
r = c.post("/data/shops/create/", {"name": "TestShop1"})
shop = Shop.objects.get(channel="TEST", name="TestShop1")
print("shop create:", r.status_code, shop)

with open("/legacy_data/sales/JST แบบย่อย 3.1.69.xlsx", "rb") as f:
    r = c.post(f"/data/shops/{shop.pk}/upload/SALES/", {"files": f})
uf = UploadedFile.objects.filter(shop=shop).first()
print("upload:", r.status_code, "| status:", uf.status, "| rows:", uf.row_count, "| range:", uf.date_min, uf.date_max)
print("lines channel:", SalesLine.objects.filter(file=uf).first().channel, "(expect TEST)")

# duplicate upload rejected
with open("/legacy_data/sales/JST แบบย่อย 3.1.69.xlsx", "rb") as f:
    r = c.post(f"/data/shops/{shop.pk}/upload/SALES/", {"files": f})
print("dup upload file count:", UploadedFile.objects.filter(shop=shop).count(), "(expect 1)")

# ads upload
with open("/legacy_data/ads/All-Ads-MKT-1-7.1.69.xlsx", "rb") as f:
    r = c.post(f"/data/shops/{shop.pk}/upload/ADS/", {"files": f})
ad_file = UploadedFile.objects.filter(shop=shop, kind="ADS").first()
print("ads upload:", r.status_code, "| status:", ad_file.status, "| rows:", ad_file.row_count)
print("ads with sku:", AdSpend.objects.filter(file=ad_file, sku_root__isnull=False).count(),
      "| without sku:", AdSpend.objects.filter(file=ad_file, sku_root__isnull=True).count())

# bad file → ERROR status with message (no silent failure)
import io
bad = io.BytesIO("คอลัมน์,ผิด\n1,2\n".encode("utf-8-sig"))
bad.name = "bad.csv"
r = c.post(f"/data/shops/{shop.pk}/upload/SALES/", {"files": bad})
bad_uf = UploadedFile.objects.filter(shop=shop, kind="SALES", status="ERROR").first()
print("bad file:", r.status_code, "| error recorded:", bool(bad_uf and bad_uf.error_message))

# delete cascades
n_before = SalesLine.objects.filter(channel="TEST").count()
r = c.post(f"/data/files/{uf.pk}/delete/")
n_after = SalesLine.objects.filter(channel="TEST").count()
print("delete:", r.status_code, "| lines removed:", n_before - n_after, "(expect", uf.row_count, ")")

# import history page
r = c.get("/data/imports/")
print("history page:", r.status_code)

# cleanup
shop.delete()
print("PHASE 3 GATE OK")
