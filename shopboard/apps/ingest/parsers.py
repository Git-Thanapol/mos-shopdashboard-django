"""Sales/Ads file parsing — exact port of the legacy pandas normalizations
(modules/processing.py + modules/data_loader.py; plan §5.1-5.8).

The fact layer depends on these computed columns being identical to the
legacy pipeline, so be careful changing anything here.
"""
import hashlib
import re
from decimal import Decimal
from zoneinfo import ZoneInfo

import pandas as pd

TZ = ZoneInfo("Asia/Bangkok")

# --- sales file Thai columns (data_loader.py col_map) ---
SALES_COLUMNS = {
    "order_id": "หมายเลขคำสั่งซื้อออนไลน์",
    "status": "สถานะคำสั่งซื้อ",
    "courier": "บริษัทขนส่ง",
    "order_time": "เวลาสั่งซื้อ",
    "sku": "รูปแบบสินค้า",
    "quantity": "จำนวน",
    "amount_paid": "รายละเอียดยอดที่ชำระแล้ว",
    "creator": "ผู้สร้างคำสั่งซื้อ",
    "payment_method": "วิธีการชำระเงิน",
    "product_name": "ชื่อสินค้า",
    "work_type": "ประเภทการทำงาน",
}

ADS_COST_COLUMNS = ["จำนวนเงินที่ใช้จ่ายไป (THB)", "Cost", "Amount"]
ADS_DATE_COLUMNS = ["วัน", "Date"]
ADS_CAMPAIGN_COLUMNS = ["ชื่อแคมเปญ", "Campaign"]

COURIER_MAP = {
    "J&T Express": "J&T Express", "J&T": "J&T Express",
    "Flash Express": "Flash Express", "Flash": "Flash Express",
    "Kerry Express": "Kerry Express", "Kerry": "Kerry Express",
    "Thailand Post": "ThailandPost", "ThailandPost": "ThailandPost",
    "DHL Domestic": "DHL_1", "DHL": "DHL_1",
    "Shopee Express": "SPX Express", "SPX Express": "SPX Express",
    "Lazada Express": "LEX TH", "LEX": "LEX TH",
}
COURIER_DEFAULT = "Standard Delivery - ส่งธรรมดาในประเทศ"


def safe_float(val) -> float:
    """processing.py:11-18, verbatim semantics."""
    if val is None or (isinstance(val, float) and pd.isna(val)) or val == "":
        return 0.0
    if pd.isna(val):
        return 0.0
    s = str(val).strip().replace(",", "").replace("฿", "").replace(" ", "")
    if s in ["-", "nan", "NaN", "None"]:
        return 0.0
    try:
        if "%" in s:
            return float(s.replace("%", "")) / 100
        return float(s)
    except (ValueError, TypeError):
        return 0.0


def safe_date(val):
    try:
        d = pd.to_datetime(val)
        if pd.isna(d):
            return None
        return d
    except (ValueError, TypeError):
        return None


def normalize_courier(courier) -> str:
    if courier is None or pd.isna(courier) or str(courier) == "":
        return COURIER_DEFAULT
    return COURIER_MAP.get(str(courier).strip(), str(courier).strip())


def detect_role(work_type: str, creator: str) -> str:
    """processing.py:160-167 — Admin wins; Thai terms only checked in work_type."""
    wt, cr = str(work_type).lower(), str(creator).lower()
    if "admin" in wt or "แอดมิน" in wt or "admin" in cr:
        return "Admin"
    if "tele" in wt or "เทเล" in wt or "tele" in cr:
        return "Telesale"
    return "Unknown"


def detect_cod(payment_method: str) -> bool:
    p = str(payment_method).lower()
    return any(term in p for term in ["cod", "ปลายทาง"])


def extract_ads_sku(campaign_name: str) -> str | None:
    """First [bracketed] token, spaces stripped (processing.py:211-212)."""
    m = re.search(r"\[(.*?)\]", str(campaign_name))
    if not m:
        return None
    return m.group(1).replace(" ", "")


def _read_table(path_or_buffer, suffix: str) -> pd.DataFrame:
    if suffix == ".csv":
        return pd.read_csv(path_or_buffer, dtype=str)
    return pd.read_excel(path_or_buffer, dtype=str)


def _clean(value) -> str:
    if value is None or pd.isna(value):
        return ""
    s = str(value)
    return "" if s == "nan" else s


def parse_sales(path_or_buffer, suffix: str) -> list[dict]:
    """Returns a list of SalesLine field dicts (without file/shop/channel)."""
    df = _read_table(path_or_buffer, suffix)
    df.columns = [str(c).strip() for c in df.columns]

    c = SALES_COLUMNS
    if c["order_id"] not in df.columns or c["order_time"] not in df.columns:
        raise ValueError(
            f"ไม่พบคอลัมน์ที่จำเป็น ({c['order_id']} / {c['order_time']}) — ไฟล์นี้ไม่ใช่ไฟล์ยอดขายที่รองรับ"
        )

    rows = []
    for _, r in df.iterrows():
        order_id = re.sub(r"\.0$", "", _clean(r.get(c["order_id"])))  # Excel float artifact (§5.2)
        if not order_id:
            continue

        order_time = safe_date(r.get(c["order_time"]))
        sku_raw = _clean(r.get(c["sku"])).strip()
        sku_norm = sku_raw.replace(" ", "")
        sku_root = sku_norm.split("-")[0]
        courier_raw = _clean(r.get(c["courier"])).strip()
        work_type = _clean(r.get(c["work_type"]))
        creator = _clean(r.get(c["creator"]))
        payment = _clean(r.get(c["payment_method"]))

        rows.append(
            {
                "order_id": order_id,
                "status": _clean(r.get(c["status"])).strip(),
                "courier_raw": courier_raw,
                "courier_norm": normalize_courier(courier_raw),
                # file times are Thai local; date is taken from the naive value
                # (same as legacy safe_date) before attaching the timezone
                "order_time": order_time.to_pydatetime().replace(tzinfo=TZ) if order_time is not None else None,
                "date": order_time.date() if order_time is not None else None,
                "sku_raw": sku_raw,
                "sku_norm": sku_norm,
                "sku_root": sku_root,
                "quantity": Decimal(str(safe_float(r.get(c["quantity"])))),
                "amount_paid": Decimal(str(round(safe_float(r.get(c["amount_paid"])), 2))),
                "creator": creator,
                "payment_method": payment,
                "work_type": work_type,
                "product_name": _clean(r.get(c["product_name"])),
                "role": detect_role(work_type, creator),
                "is_cod": detect_cod(payment),
            }
        )
    return rows


def parse_ads(path_or_buffer, suffix: str) -> list[dict]:
    """Returns a list of AdSpend field dicts (without file/shop/channel)."""
    if suffix == ".csv":
        df = pd.read_csv(path_or_buffer)
    else:
        df = pd.read_excel(path_or_buffer)
    df.columns = [str(c).strip() for c in df.columns]

    col_cost = next((x for x in ADS_COST_COLUMNS if x in df.columns), None)
    col_date = next((x for x in ADS_DATE_COLUMNS if x in df.columns), None)
    col_camp = next((x for x in ADS_CAMPAIGN_COLUMNS if x in df.columns), None)
    if not (col_cost and col_date):
        raise ValueError("ไม่พบคอลัมน์วันที่/จำนวนเงิน — ไฟล์นี้ไม่ใช่ไฟล์โฆษณาที่รองรับ")

    rows = []
    for _, r in df.iterrows():
        d = safe_date(r.get(col_date))
        if d is None:
            continue
        campaign = _clean(r.get(col_camp)) if col_camp else ""
        rows.append(
            {
                "date": d.date(),
                "campaign_name": campaign,
                "sku_root": extract_ads_sku(campaign) if col_camp else None,
                "cost": Decimal(str(safe_float(r.get(col_cost)))),
            }
        )
    return rows


def file_sha256(django_file) -> str:
    h = hashlib.sha256()
    for chunk in django_file.chunks():
        h.update(chunk)
    return h.hexdigest()
