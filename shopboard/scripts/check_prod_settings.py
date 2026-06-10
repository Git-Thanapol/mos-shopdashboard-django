import os

os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.prod"
import django  # noqa: E402

django.setup()
from django.conf import settings  # noqa: E402

print("prod loads OK")
print("DEBUG:", settings.DEBUG)
print("CSRF_TRUSTED_ORIGINS:", settings.CSRF_TRUSTED_ORIGINS)
print("SESSION_COOKIE_SECURE:", getattr(settings, "SESSION_COOKIE_SECURE", False))
