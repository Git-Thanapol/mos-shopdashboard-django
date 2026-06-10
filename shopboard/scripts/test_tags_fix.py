"""Tag creation fix checks: group/tag create succeed, random colors assigned."""
from django.contrib.auth import get_user_model
from django.test import Client

from apps.catalog.forms import TAG_PALETTE, TagForm, TagGroupForm
from apps.catalog.models import Tag, TagGroup

u = get_user_model().objects.get(username="admin")
c = Client()
c.force_login(u)
s = c.session
s["channel"] = "LIVE"
s.save()

TagGroup.objects.filter(name__startswith="ทดสอบแท็ก").delete()

# exactly what the page form posts: name + color only (no sort_order)
r = c.post("/settings/tags/groups/create/", {"name": "ทดสอบแท็ก A", "color": "#3498db"}, follow=True)
g = TagGroup.objects.filter(name="ทดสอบแท็ก A").first()
print("group create:", r.status_code, "| created:", g is not None,
      "| sort_order default:", g.sort_order if g else "-", "| visible:", g.is_visible if g else "-")

# duplicate name now reports a real error and does not crash
r = c.post("/settings/tags/groups/create/", {"name": "ทดสอบแท็ก A", "color": "#3498db"}, follow=True)
print("dup group blocked:", TagGroup.objects.filter(name="ทดสอบแท็ก A").count() == 1,
      "| error shown:", "เพิ่มกลุ่มไม่สำเร็จ" in r.content.decode())

# tag create inside the group
r = c.post(f"/settings/tags/groups/{g.pk}/tags/create/", {"name": "ฤดูร้อน", "color": "#e84393"}, follow=True)
t = Tag.objects.filter(group=g, name="ฤดูร้อน").first()
print("tag create:", r.status_code, "| created:", t is not None, "| color:", t.color if t else "-")

# random color initials come from the palette and vary
colors = {TagGroupForm().initial.get("color") for _ in range(12)}
print("group form random colors from palette:", colors.issubset(set(TAG_PALETTE)), "| distinct in 12 draws:", len(colors) > 1)
colors_t = {TagForm().initial.get("color") for _ in range(12)}
print("tag form random colors from palette:", colors_t.issubset(set(TAG_PALETTE)))

# page renders with the new group selected
r = c.get(f"/settings/tags/?group={g.pk}")
print("tags page:", r.status_code)

TagGroup.objects.filter(name__startswith="ทดสอบแท็ก").delete()
print("TAGS FIX CHECK DONE")
