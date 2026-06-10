"""Shared Thai date helpers (plan §5.11)."""

THAI_MONTHS = [
    "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
    "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม",
]

THAI_MONTHS_SHORT = [
    "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
    "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค.",
]


def thai_month_name(month: int, short: bool = False) -> str:
    names = THAI_MONTHS_SHORT if short else THAI_MONTHS
    return names[month - 1]


def thai_date(d, short: bool = True, buddhist_era: bool = True) -> str:
    """10 มิ.ย. 2569 — พ.ศ. in UI labels, ค.ศ. stays in URLs/ISO (UX plan §6)."""
    year = d.year + 543 if buddhist_era else d.year
    return f"{d.day} {thai_month_name(d.month, short)} {year}"
