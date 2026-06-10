"""TEST/LIVE channel separation (migration plan §13).

The active channel is chosen on the post-login channel-select screen, kept in
the session, and strictly scopes every shop/product/report query.
"""
from django.db import models

SESSION_KEY = "channel"


class Channel(models.TextChoices):
    LIVE = "LIVE", "ร้านค้าจริง"
    TEST = "TEST", "สินค้าทดสอบ"


def current(request) -> str | None:
    value = request.session.get(SESSION_KEY)
    return value if value in Channel.values else None


def activate(request, value: str) -> None:
    if value not in Channel.values:
        raise ValueError(f"invalid channel: {value}")
    request.session[SESSION_KEY] = value
