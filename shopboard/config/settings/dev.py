from .base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ["*"]

# Real SMTP when credentials are configured; otherwise OTP codes print to the
# web container logs (docker compose logs web)
if not (EMAIL_HOST_USER and EMAIL_HOST_PASSWORD):  # noqa: F405
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Manifest storage breaks when static files change without collectstatic in dev
STORAGES["staticfiles"] = {  # noqa: F405
    "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
}
