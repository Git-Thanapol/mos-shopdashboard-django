"""Global report filter state — parsed from the querystring (URL = shareable
state), with the last-used set kept in the session so filters follow the user
across pages (UX plan §4.1)."""
from dataclasses import dataclass, field
from datetime import date, timedelta

from django.utils import timezone

SESSION_KEY = "report_filters"

MODES = ("moving", "all", "profit", "loss")  # มีการเคลื่อนไหว / ทั้งหมด / กำไร / ขาดทุน


def _parse_date(s, default):
    try:
        return date.fromisoformat(s)
    except (TypeError, ValueError):
        return default


def _parse_float(s):
    try:
        return float(s) if s not in (None, "") else None
    except ValueError:
        return None


@dataclass
class FilterState:
    date_from: date
    date_to: date
    shops: list[str] = field(default_factory=list)  # shop names; empty = all
    skus: list[str] = field(default_factory=list)   # explicit sku_root picks; empty = auto
    category: str = ""
    tag: int | None = None
    mode: str = "moving"
    pmin: float | None = None
    pmax: float | None = None
    amin: float | None = None
    amax: float | None = None

    @classmethod
    def from_request(cls, request):
        today = timezone.localdate()
        month_start = today.replace(day=1)

        if any(k in request.GET for k in ("from", "to", "shop", "sku", "cat", "tag", "mode")):
            src = request.GET
            state = cls(
                date_from=_parse_date(src.get("from"), month_start),
                date_to=_parse_date(src.get("to"), today),
                shops=[s for s in src.getlist("shop") if s],
                skus=[s for s in src.getlist("sku") if s],
                category=src.get("cat", ""),
                tag=int(src["tag"]) if src.get("tag", "").isdigit() else None,
                mode=src.get("mode") if src.get("mode") in MODES else "moving",
                pmin=_parse_float(src.get("pmin")),
                pmax=_parse_float(src.get("pmax")),
                amin=_parse_float(src.get("amin")),
                amax=_parse_float(src.get("amax")),
            )
        elif SESSION_KEY in request.session:
            d = request.session[SESSION_KEY]
            state = cls(
                date_from=_parse_date(d.get("from"), month_start),
                date_to=_parse_date(d.get("to"), today),
                shops=d.get("shops", []),
                skus=d.get("skus", []),
                category=d.get("cat", ""),
                tag=d.get("tag"),
                mode=d.get("mode", "moving"),
                pmin=d.get("pmin"),
                pmax=d.get("pmax"),
                amin=d.get("amin"),
                amax=d.get("amax"),
            )
        else:
            state = cls(date_from=month_start, date_to=today)

        request.session[SESSION_KEY] = {
            "from": state.date_from.isoformat(),
            "to": state.date_to.isoformat(),
            "shops": state.shops,
            "skus": state.skus,
            "cat": state.category,
            "tag": state.tag,
            "mode": state.mode,
            "pmin": state.pmin,
            "pmax": state.pmax,
            "amin": state.amin,
            "amax": state.amax,
        }
        return state

    @property
    def advanced_count(self) -> int:
        return sum(
            1 for v in (self.category, self.tag, self.pmin, self.pmax, self.amin, self.amax)
            if v not in ("", None)
        ) + (1 if self.mode != "moving" else 0)

    def querystring(self, **overrides) -> str:
        from urllib.parse import urlencode

        params = [("from", self.date_from.isoformat()), ("to", self.date_to.isoformat())]
        params += [("shop", s) for s in self.shops]
        params += [("sku", s) for s in self.skus]
        if self.category:
            params.append(("cat", self.category))
        if self.tag:
            params.append(("tag", str(self.tag)))
        if self.mode != "moving":
            params.append(("mode", self.mode))
        for k in ("pmin", "pmax", "amin", "amax"):
            v = getattr(self, k)
            if v is not None:
                params.append((k, str(v)))
        for k, v in overrides.items():
            params = [(pk, pv) for pk, pv in params if pk != k]
            params.append((k, str(v)))
        return urlencode(params)

    def presets(self):
        today = timezone.localdate()
        return [
            ("วันนี้", today, today),
            ("7 วัน", today - timedelta(days=6), today),
            ("เดือนนี้", today.replace(day=1), today),
            ("เดือนที่แล้ว",
             (today.replace(day=1) - timedelta(days=1)).replace(day=1),
             today.replace(day=1) - timedelta(days=1)),
            ("ปีนี้", today.replace(month=1, day=1), today),
        ]
