"""Phase-2 gate check, run via: manage.py shell < scripts/test_phase2.py"""
from django.contrib.auth import get_user_model
from django.test import Client

from apps.catalog import importer
from apps.catalog.models import MasterItem, ProductTag, Tag, TagGroup
from apps.core.channels import Channel

u = get_user_model().objects.get(username="admin")
c = Client()
c.force_login(u)
s = c.session
s["channel"] = "LIVE"
s.save()

r = c.get("/settings/master-items/")
print("GET master page:", r.status_code)

with open("/legacy_data/master_item.xlsx", "rb") as f:
    res = importer.import_master_xlsx(f, Channel.LIVE, u)
print("xlsx import:", res, "| db count:", MasterItem.objects.filter(channel="LIVE").count())

r = c.get("/settings/master-items/")
print("GET master page after import:", r.status_code, "| has 799:", ("799" in r.content.decode()))

r = c.post("/settings/master-items/create/", {"sku": "TESTSKU-01", "name": "สินค้าทดลองสร้าง", "cost": "12.5"})
print("POST create:", r.status_code, "| exists:", MasterItem.objects.filter(channel="LIVE", sku="TESTSKU-01").exists())

item = MasterItem.objects.get(channel="LIVE", sku="TESTSKU-01")
r = c.post(f"/settings/master-items/{item.pk}/edit/", {"sku": "TESTSKU-01", "name": "แก้ไขแล้ว", "cost": "99"})
item.refresh_from_db()
print("POST edit:", r.status_code, "| name:", item.name, "| cost:", item.cost)

r = c.post(f"/settings/master-items/{item.pk}/delete/")
print("POST delete:", r.status_code, "| removed:", not MasterItem.objects.filter(pk=item.pk).exists())

# TEST channel separation: same SKU can exist independently
s["channel"] = "TEST"
s.save()
r = c.get("/settings/master-items/")
print("TEST channel master page:", r.status_code, "| empty:", ("ไม่พบสินค้า" in r.content.decode()), "(expect True — strict separation)")
c.post("/settings/master-items/create/", {"sku": "DUPSKU", "name": "test ch"})
s["channel"] = "LIVE"
s.save()
c.post("/settings/master-items/create/", {"sku": "DUPSKU", "name": "live ch"})
print("same SKU in both channels:", MasterItem.objects.filter(sku="DUPSKU").count() == 2)
MasterItem.objects.filter(sku="DUPSKU").delete()

# tags
r = c.post("/settings/tags/groups/create/", {"name": "กลุ่มทดสอบ", "color": "#ff8800", "sort_order": 0, "is_visible": "on"})
g = TagGroup.objects.get(name="กลุ่มทดสอบ")
c.post(f"/settings/tags/groups/{g.pk}/tags/create/", {"name": "หน้าร้อน", "color": ""})
t = Tag.objects.get(name="หน้าร้อน")
sku0 = MasterItem.objects.filter(channel="LIVE").first().sku
r = c.post(f"/settings/tags/{t.pk}/toggle-sku/", {"sku": sku0, "checked": "true"})
print("tag toggle:", r.status_code, r.content.decode()[:40], "| assigned:", ProductTag.objects.filter(tag=t).count())
r = c.get(f"/settings/tags/?group={g.pk}&tag={t.pk}")
print("GET tags page:", r.status_code)
print("PHASE 2 GATE OK")

