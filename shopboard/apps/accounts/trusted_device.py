"""30-day remember-this-device cookie: a signed user pk, checked at login.

If the cookie is present and valid for the authenticating user, the email-OTP
step is skipped (UX plan §4.4).
"""
from django.conf import settings
from django.core import signing

SALT = "accounts.trusted-device"


def is_trusted(request, user) -> bool:
    raw = request.COOKIES.get(settings.TRUSTED_DEVICE_COOKIE)
    if not raw:
        return False
    try:
        payload = signing.loads(raw, salt=SALT, max_age=settings.TRUSTED_DEVICE_MAX_AGE)
    except signing.BadSignature:
        return False
    return payload.get("u") == user.pk


def mark_trusted(response, user):
    response.set_cookie(
        settings.TRUSTED_DEVICE_COOKIE,
        signing.dumps({"u": user.pk}, salt=SALT),
        max_age=settings.TRUSTED_DEVICE_MAX_AGE,
        httponly=True,
        samesite="Lax",
    )
