"""Filter-bar layout checks: daily page embeds day-controls, hides from/to."""
import re

from django.contrib.auth import get_user_model
from django.test import Client

u = get_user_model().objects.get(username="admin")
c = Client()
c.force_login(u)
s = c.session
s["channel"] = "LIVE"
s.save()

# daily page: day controls live inside the filter form; from/to are hidden inputs
r = c.get("/reports/daily/?from=2026-01-01&to=2026-01-31&date=2026-01-15")
b = r.content.decode()
form = re.search(r'<form method="get" class="card filter-bar".*?</form>', b, re.S).group(0)
print("daily status:", r.status_code)
print("day-controls in filter bar:", 'class="filter-group day-controls"' in form)
print("date input in form:", 'name="date" value="2026-01-15"' in form)
print("from/to hidden:", 'type="hidden" name="from"' in form and 'type="hidden" name="to"' in form)
print("no visible from/to:", 'type="date" name="from"' not in form and 'type="date" name="to"' not in form)
print("no presets on daily:", "preset-chip" not in form)
print("prev/next links:", "date=2026-01-14" in form and "date=2026-01-16" in form)
print("old header form gone:", "inline-form" not in b)

# monthly page: unchanged — presets + visible from/to, no day controls
r = c.get("/reports/monthly/?from=2026-01-01&to=2026-01-31")
b = r.content.decode()
form = re.search(r'<form method="get" class="card filter-bar".*?</form>', b, re.S).group(0)
print("monthly status:", r.status_code)
print("monthly presets:", "preset-chip" in form)
print("monthly visible from/to:", 'type="date" name="from"' in form and 'type="date" name="to"' in form)
print("monthly no day-controls:", "day-controls" not in form)
print("FILTER BAR CHECK DONE")
