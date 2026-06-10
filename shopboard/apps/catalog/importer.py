"""Master-item import from Excel upload or the legacy Google Sheet (LIVE-only).

Column mapping mirrors the legacy loader (data_loader.py:save_master_to_db);
'ทุน' and 'ต้นทุน' both mean cost (plan §5.11). Percent columns keep their
percent-as-number semantics (3 = 3%).
"""
import re
from decimal import Decimal, InvalidOperation

import pandas as pd

from apps.core.channels import Channel

from .models import MasterItem

COLUMN_MAP = {
    "SKU": "sku",
    "ชื่อสินค้า": "name",
    "Type": "type",
    "ทุน": "cost",
    "ต้นทุน": "cost",
    "ราคากล่อง": "box_cost",
    "ค่าส่งเฉลี่ย": "delivery_cost",
    "ค่าคอมมิชชั่น Admin": "com_admin_pct",
    "ค่าคอมมิชชั่น Telesale": "com_tele_pct",
    "J&T Express": "p_jnt",
    "Flash Express": "p_flash",
    "Kerry Express": "p_kerry",
    "ThailandPost": "p_thai_post",
    "DHL_1": "p_dhl",
    "SPX Express": "p_spx",
    "LEX TH": "p_lex",
    "Standard Delivery - ส่งธรรมดาในประเทศ": "p_std",
}

NUMERIC_FIELDS = [
    "cost", "box_cost", "delivery_cost", "com_admin_pct", "com_tele_pct",
    "p_jnt", "p_flash", "p_kerry", "p_thai_post", "p_dhl", "p_spx", "p_lex", "p_std",
]


def _clean_number(value) -> Decimal:
    s = str(value).strip().replace(",", "").replace("%", "").replace("฿", "")
    if s in ("", "-", "nan", "None", "NaN"):
        return Decimal(0)
    try:
        return Decimal(s)
    except InvalidOperation:
        return Decimal(0)


def normalize_sku(value) -> str:
    return re.sub(r"\s+", "", str(value).strip())


def import_master_dataframe(df: pd.DataFrame, channel: str, user=None) -> dict:
    """Upsert master items by (channel, sku). Returns counts."""
    df = df.rename(columns={c: COLUMN_MAP.get(str(c).strip(), str(c).strip()) for c in df.columns})
    keep = ["sku", "name", "type"] + NUMERIC_FIELDS
    df = df[[c for c in df.columns if c in keep]]
    if "sku" not in df.columns:
        raise ValueError("ไม่พบคอลัมน์ SKU ในไฟล์")

    added = updated = skipped = 0
    seen: set[str] = set()
    existing = {m.sku: m for m in MasterItem.objects.filter(channel=channel)}

    for _, row in df.iterrows():
        sku = normalize_sku(row.get("sku", ""))
        if not sku or sku.lower() == "nan" or sku in seen:
            skipped += 1
            continue
        seen.add(sku)

        fields = {
            "name": str(row.get("name", "") or "").strip(),
            "type": str(row.get("type", "") or "").strip() or "กลุ่ม ปกติ",
        }
        for f in NUMERIC_FIELDS:
            if f in df.columns:
                fields[f] = _clean_number(row.get(f))

        obj = existing.get(sku)
        if obj is None:
            MasterItem.objects.create(channel=channel, sku=sku, updated_by=user, **fields)
            added += 1
        else:
            for k, v in fields.items():
                setattr(obj, k, v)
            obj.updated_by = user
            obj.save()
            updated += 1

    return {"added": added, "updated": updated, "skipped": skipped}


def import_master_xlsx(file_obj, channel: str, user=None) -> dict:
    sheets = pd.read_excel(file_obj, sheet_name=None, dtype=str)
    df = sheets.get("MASTER_ITEM")
    if df is None:
        df = next(iter(sheets.values()))  # legacy local file uses "Sheet1"
    return import_master_dataframe(df, channel, user)


def import_master_google_sheet(user=None) -> dict:
    """LIVE-only one-way import from the legacy Google Sheet (plan §7)."""
    from django.conf import settings

    if not settings.GOOGLE_SERVICE_ACCOUNT_FILE or not settings.SHEET_MASTER_URL:
        raise RuntimeError("ยังไม่ได้ตั้งค่า Google Sheet (GOOGLE_APPLICATION_CREDENTIALS / SHEET_MASTER_URL)")

    import gspread

    gc = gspread.service_account(filename=settings.GOOGLE_SERVICE_ACCOUNT_FILE)
    sh = gc.open_by_url(settings.SHEET_MASTER_URL)
    df = pd.DataFrame(sh.worksheet("MASTER_ITEM").get_all_records())
    result = import_master_dataframe(df, Channel.LIVE, user)

    # FIX_COST sheet → FixCost rows (best effort; sheet may be absent)
    try:
        fix_df = None
        for ws_name in ("FIX_COST", "FIXED_COST"):
            try:
                fix_df = pd.DataFrame(sh.worksheet(ws_name).get_all_records())
                break
            except gspread.WorksheetNotFound:
                continue
        if fix_df is not None and not fix_df.empty:
            result["fixcost_rows"] = _import_fixcost_dataframe(fix_df)
    except Exception:
        result["fixcost_rows"] = 0
    return result


def _import_fixcost_dataframe(df: pd.DataFrame) -> int:
    from .models import FixCost

    col_year = next((c for c in df.columns if str(c).strip().lower() in ("year", "ปี")), None)
    col_month = next((c for c in df.columns if str(c).strip().lower() in ("month", "เดือน")), None)
    col_label = next((c for c in df.columns if str(c).strip().lower() in ("label", "รายการ", "ชื่อ")), None)
    col_amount = next((c for c in df.columns if str(c).strip().lower() in ("amount", "จำนวนเงิน", "ค่าใช้จ่าย")), None)
    if not (col_year and col_month and col_amount):
        return 0
    count = 0
    for _, row in df.iterrows():
        try:
            year = int(_clean_number(row[col_year]))
            month = int(_clean_number(row[col_month]))
            if year > 2400:  # พ.ศ. → ค.ศ.
                year -= 543
            FixCost.objects.update_or_create(
                year=year,
                month=month,
                label=str(row.get(col_label, "") or "ค่าใช้จ่ายคงที่").strip(),
                defaults={"amount": _clean_number(row[col_amount])},
            )
            count += 1
        except (ValueError, KeyError):
            continue
    return count
