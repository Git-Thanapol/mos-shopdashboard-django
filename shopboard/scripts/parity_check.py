"""Phase-4 parity gate: legacy pandas pipeline vs analytics_fact_daily.

Re-runs the EXACT legacy computation (modules/processing.py:process_data with
streamlit removed) over /legacy_data shop folders, then compares every
(date, sku_root, shop) measure against the matview. Tolerance 0.01 (satang).

Run: docker compose exec -T web sh -c "python manage.py shell < scripts/parity_check.py"
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path("/legacy_data")
TOL = 0.01

# ---------------------------------------------------------------- legacy load
def safe_float(val):
    if pd.isna(val) or val == "" or val is None:
        return 0.0
    s = str(val).strip().replace(",", "").replace("฿", "").replace(" ", "")
    if s in ["-", "nan", "NaN", "None"]:
        return 0.0
    try:
        if "%" in s:
            return float(s.replace("%", "")) / 100
        return float(s)
    except Exception:
        return 0.0


def safe_date(val):
    try:
        return pd.to_datetime(val).date()
    except Exception:
        return None


def safe_float_pct(val):
    """Percent-intent mode: '4.00%' means 4 (percent), not 0.04.

    The legacy safe_float turns '4.00%' into 0.04 and the commission/COD
    formulas divide by 100 AGAIN — a double division that under-counted those
    costs ×100. The new system fixes this (documented legacy bug); this helper
    lets the parity check validate everything else exactly.
    """
    if pd.isna(val) or val == "" or val is None:
        return 0.0
    s = str(val).strip().replace(",", "").replace("฿", "").replace(" ", "").replace("%", "")
    if s in ["-", "nan", "NaN", "None"]:
        return 0.0
    try:
        return float(s)
    except Exception:
        return 0.0


def normalize_courier_name(courier):
    if pd.isna(courier) or courier == "":
        return "Standard Delivery - ส่งธรรมดาในประเทศ"
    courier = str(courier).strip()
    mapping = {
        "J&T Express": "J&T Express", "J&T": "J&T Express",
        "Flash Express": "Flash Express", "Flash": "Flash Express",
        "Kerry Express": "Kerry Express", "Kerry": "Kerry Express",
        "Thailand Post": "ThailandPost", "ThailandPost": "ThailandPost",
        "DHL Domestic": "DHL_1", "DHL": "DHL_1",
        "Shopee Express": "SPX Express", "SPX Express": "SPX Express",
        "Lazada Express": "LEX TH", "LEX": "LEX TH",
    }
    return mapping.get(courier, courier)


shop_dirs = [d for d in sorted(ROOT.iterdir()) if d.is_dir() and d.name not in ("sales", "ads")]

sales_frames, ads_frames = [], []
for shop_dir in shop_dirs:
    for f in sorted((shop_dir / "sales").glob("*")) if (shop_dir / "sales").exists() else []:
        if f.suffix.lower() in (".csv", ".xlsx", ".xls"):
            df = pd.read_csv(f, dtype=str) if f.suffix.lower() == ".csv" else pd.read_excel(f, dtype=str)
            if "หมายเลขคำสั่งซื้อออนไลน์" in df.columns:
                df["หมายเลขคำสั่งซื้อออนไลน์"] = (
                    df["หมายเลขคำสั่งซื้อออนไลน์"].astype(str).str.replace(r"\.0$", "", regex=True)
                )
            df["Shop"] = shop_dir.name
            sales_frames.append(df)
    for f in sorted((shop_dir / "ads").glob("*")) if (shop_dir / "ads").exists() else []:
        if f.suffix.lower() in (".csv", ".xlsx", ".xls"):
            df = pd.read_csv(f) if f.suffix.lower() == ".csv" else pd.read_excel(f)
            df["shop_name"] = shop_dir.name
            ads_frames.append(df)

df_data = pd.concat(sales_frames, ignore_index=True)
df_ads_raw = pd.concat(ads_frames, ignore_index=True) if ads_frames else pd.DataFrame()
df_master = pd.read_excel(ROOT / "master_item.xlsx")  # first sheet (Sheet1)

# ------------------------------------------------- legacy process_data (verbatim)
df_master.columns = df_master.columns.astype(str).str.strip()
if "ทุน" in df_master.columns:
    df_master.rename(columns={"ทุน": "ต้นทุน"}, inplace=True)
if "ชื่อสินค้า" not in df_master.columns and len(df_master.columns) >= 2:
    df_master.rename(columns={df_master.columns[1]: "ชื่อสินค้า"}, inplace=True)
if "Type" not in df_master.columns:
    df_master["Type"] = "กลุ่ม ปกติ"
df_master["Type"] = df_master["Type"].fillna("กลุ่ม ปกติ").astype(str).str.strip()

cols = [c for c in ["หมายเลขคำสั่งซื้อออนไลน์", "สถานะคำสั่งซื้อ", "บริษัทขนส่ง", "เวลาสั่งซื้อ",
                    "รูปแบบสินค้า", "จำนวน", "รายละเอียดยอดที่ชำระแล้ว", "ผู้สร้างคำสั่งซื้อ",
                    "วิธีการชำระเงิน", "ชื่อสินค้า", "ประเภทการทำงาน", "Shop"] if c in df_data.columns]
df = df_data[cols].copy()
if "สถานะคำสั่งซื้อ" in df.columns:
    df = df[~df["สถานะคำสั่งซื้อ"].isin(["ยกเลิก"])]
df["Date"] = df["เวลาสั่งซื้อ"].apply(safe_date)
df = df.dropna(subset=["Date"])
df["SKU_Main"] = df["รูปแบบสินค้า"].astype(str).str.split("-").str[0].str.strip()

master_cols = [c for c in ["SKU", "ชื่อสินค้า", "Type", "ต้นทุน", "ราคากล่อง", "ค่าส่งเฉลี่ย",
                           "ค่าคอมมิชชั่น Admin", "ค่าคอมมิชชั่น Telesale", "J&T Express",
                           "Flash Express", "ThailandPost", "DHL_1", "LEX TH", "SPX Express",
                           "Express Delivery - ส่งด่วน", "Standard Delivery - ส่งธรรมดาในประเทศ"]
               if c in df_master.columns]
df_master_filtered = df_master[master_cols].drop_duplicates("SKU")

df["SKU_Raw"] = df["รูปแบบสินค้า"].astype(str).str.strip()
df["SKU_Norm"] = df["SKU_Raw"].str.replace(" ", "", regex=False)
df["SKU_Norm_Root"] = df["SKU_Norm"].str.split("-").str[0]

df_master_filtered["SKU_Norm"] = df_master_filtered["SKU"].astype(str).str.strip().str.replace(" ", "", regex=False)
df_merged = pd.merge(df, df_master_filtered, on="SKU_Norm", how="left")
if "ชื่อสินค้า_y" in df_merged.columns:
    df_merged.rename(columns={"ชื่อสินค้า_y": "ชื่อสินค้า_Master"}, inplace=True)
if "ชื่อสินค้า_x" in df_merged.columns:
    df_merged.rename(columns={"ชื่อสินค้า_x": "ชื่อสินค้า"}, inplace=True)

df_root_lookup = pd.merge(df[["SKU_Norm_Root"]], df_master_filtered,
                          left_on="SKU_Norm_Root", right_on="SKU_Norm", how="left")
for col in ["ต้นทุน", "ราคากล่อง", "ค่าส่งเฉลี่ย", "ค่าคอมมิชชั่น Admin", "ค่าคอมมิชชั่น Telesale", "Type"]:
    if col in df_merged.columns and col in df_root_lookup.columns:
        df_merged[col] = df_merged[col].combine_first(df_root_lookup[col])

for col in ["จำนวน", "รายละเอียดยอดที่ชำระแล้ว", "ต้นทุน", "ราคากล่อง", "ค่าส่งเฉลี่ย"]:
    if col in df_merged.columns:
        df_merged[col] = df_merged[col].apply(safe_float)

df_merged["CAL_COST"] = df_merged["จำนวน"] * df_merged["ต้นทุน"]
df_merged["BOX_COST_PER_LINE"] = df_merged["ราคากล่อง"].fillna(0)
df_merged["DELIV_COST_PER_LINE"] = df_merged["ค่าส่งเฉลี่ย"].fillna(0)


def get_shipping_percent(row):
    normalized = normalize_courier_name(str(row.get("บริษัทขนส่ง", "")).strip())
    if normalized in row:
        return safe_float_pct(row[normalized])
    return safe_float_pct(row.get("Standard Delivery - ส่งธรรมดาในประเทศ", 0))


df_merged["SHIP_PERCENT"] = df_merged.apply(get_shipping_percent, axis=1)


def calculate_cod_cost(row):
    payment = str(row.get("วิธีการชำระเงิน", "")).lower()
    if any(t in payment for t in ["cod", "ปลายทาง"]) and row["SHIP_PERCENT"] > 0:
        return row["รายละเอียดยอดที่ชำระแล้ว"] * (row["SHIP_PERCENT"] / 100) * 1.07
    return 0


df_merged["CAL_COD_COST"] = df_merged.apply(calculate_cod_cost, axis=1)


def calculate_role(row):
    wt = str(row.get("ประเภทการทำงาน", "")).lower()
    cr = str(row.get("ผู้สร้างคำสั่งซื้อ", "")).lower()
    if "admin" in wt or "แอดมิน" in wt or "admin" in cr:
        return "Admin"
    if "tele" in wt or "เทเล" in wt or "tele" in cr:
        return "Telesale"
    return "Unknown"


df_merged["Calculated_Role"] = df_merged.apply(calculate_role, axis=1)
com_admin = df_merged.get("ค่าคอมมิชชั่น Admin", 0).fillna(0).apply(safe_float_pct) / 100
com_tele = df_merged.get("ค่าคอมมิชชั่น Telesale", 0).fillna(0).apply(safe_float_pct) / 100
df_merged["CAL_COM_ADMIN"] = np.where(df_merged["Calculated_Role"] == "Admin",
                                      df_merged["รายละเอียดยอดที่ชำระแล้ว"] * com_admin, 0)
df_merged["CAL_COM_TELESALE"] = np.where(df_merged["Calculated_Role"] == "Telesale",
                                         df_merged["รายละเอียดยอดที่ชำระแล้ว"] * com_tele, 0)
df_merged["SKU_Main"] = df_merged["SKU_Norm_Root"]

order_agg = {"Date": "first", "SKU_Main": "first", "Shop": "first", "จำนวน": "sum",
             "รายละเอียดยอดที่ชำระแล้ว": "sum", "CAL_COST": "sum", "BOX_COST_PER_LINE": "max",
             "DELIV_COST_PER_LINE": "max", "CAL_COD_COST": "sum", "CAL_COM_ADMIN": "sum",
             "CAL_COM_TELESALE": "sum"}
df_order = df_merged.groupby("หมายเลขคำสั่งซื้อออนไลน์").agg(order_agg).reset_index()
df_order.rename(columns={"BOX_COST_PER_LINE": "BOX_COST", "DELIV_COST_PER_LINE": "DELIV_COST"}, inplace=True)

df_ads_agg = pd.DataFrame(columns=["Date", "SKU_Main", "Shop", "Ads_Amount"])
dropped_ads_cost = 0.0
if not df_ads_raw.empty:
    col_cost = next((c for c in ["จำนวนเงินที่ใช้จ่ายไป (THB)", "Cost", "Amount"] if c in df_ads_raw.columns), None)
    col_date = next((c for c in ["วัน", "Date"] if c in df_ads_raw.columns), None)
    col_camp = next((c for c in ["ชื่อแคมเปญ", "Campaign"] if c in df_ads_raw.columns), None)
    if col_cost and col_date and col_camp:
        df_ads_raw["Date"] = df_ads_raw[col_date].apply(safe_date)
        df_ads_raw = df_ads_raw.dropna(subset=["Date"])
        df_ads_raw[col_cost] = df_ads_raw[col_cost].apply(safe_float)
        df_ads_raw["SKU_Extracted"] = df_ads_raw[col_camp].astype(str).str.extract(r"\[(.*?)\]")
        df_ads_raw["SKU_Main"] = df_ads_raw["SKU_Extracted"].str.replace(" ", "", regex=False)
        dropped_ads_cost = df_ads_raw.loc[df_ads_raw["SKU_Main"].isna(), col_cost].sum()
        df_ads_agg = (df_ads_raw.groupby(["Date", "SKU_Main", "shop_name"])[col_cost]
                      .sum().reset_index(name="Ads_Amount").rename(columns={"shop_name": "Shop"}))

daily_agg = {"จำนวนออเดอร์": "count", "จำนวน": "sum", "รายละเอียดยอดที่ชำระแล้ว": "sum",
             "CAL_COST": "sum", "BOX_COST": "sum", "DELIV_COST": "sum", "CAL_COD_COST": "sum",
             "CAL_COM_ADMIN": "sum", "CAL_COM_TELESALE": "sum"}
df_order_renamed = df_order.rename(columns={"หมายเลขคำสั่งซื้อออนไลน์": "จำนวนออเดอร์"})
df_daily = df_order_renamed.groupby(["Date", "SKU_Main", "Shop"]).agg(daily_agg).reset_index()
df_daily = pd.merge(df_daily, df_ads_agg, on=["Date", "SKU_Main", "Shop"], how="outer")
df_daily = df_daily.fillna(0)
df_daily["Net_Profit"] = (df_daily["รายละเอียดยอดที่ชำระแล้ว"] - df_daily["CAL_COST"]
                          - df_daily["BOX_COST"] - df_daily["DELIV_COST"] - df_daily["CAL_COD_COST"]
                          - df_daily["CAL_COM_ADMIN"] - df_daily["CAL_COM_TELESALE"] - df_daily["Ads_Amount"])

legacy = df_daily.rename(columns={
    "SKU_Main": "sku_root", "Shop": "shop", "Date": "date", "จำนวนออเดอร์": "orders",
    "จำนวน": "quantity", "รายละเอียดยอดที่ชำระแล้ว": "revenue", "CAL_COST": "product_cost",
    "BOX_COST": "box_cost", "DELIV_COST": "delivery_cost", "CAL_COD_COST": "cod_cost",
    "CAL_COM_ADMIN": "com_admin", "CAL_COM_TELESALE": "com_tele", "Ads_Amount": "ads_amount",
    "Net_Profit": "net_profit"})
legacy["date"] = pd.to_datetime(legacy["date"]).dt.date

# --------------------------------------------------------------- matview side
from django.db import connection

q = """
SELECT f.date, f.sku_root, s.name AS shop, f.orders, f.quantity, f.revenue, f.product_cost,
       f.box_cost, f.delivery_cost, f.cod_cost, f.com_admin, f.com_tele, f.ads_amount, f.net_profit
FROM analytics_fact_daily f JOIN ingest_shop s ON s.id = f.shop_id
WHERE f.channel = 'LIVE'
"""
new = pd.read_sql(q, connection)
new["date"] = pd.to_datetime(new["date"]).dt.date
bucket = new[new["sku_root"] == "ไม่ระบุ SKU"]
new_cmp = new[new["sku_root"] != "ไม่ระบุ SKU"]

measures = ["orders", "quantity", "revenue", "product_cost", "box_cost", "delivery_cost",
            "cod_cost", "com_admin", "com_tele", "ads_amount", "net_profit"]
key = ["date", "sku_root", "shop"]
merged = pd.merge(legacy, new_cmp, on=key, how="outer", suffixes=("_old", "_new"), indicator=True)

print(f"legacy rows: {len(legacy)} | matview rows (ex bucket): {len(new_cmp)} | joined: {len(merged)}")
print("only in legacy:", (merged["_merge"] == "left_only").sum(),
      "| only in matview:", (merged["_merge"] == "right_only").sum())

fail = False
for m in measures:
    a = merged[f"{m}_old"].astype(float).fillna(0)
    b = merged[f"{m}_new"].astype(float).fillna(0)
    diff = (a - b).abs()
    bad = diff > TOL
    status = "OK " if not bad.any() else "FAIL"
    if bad.any():
        fail = True
    print(f"{status} {m:14s} max_diff={diff.max():.6f} rows_off={bad.sum()} "
          f"sum_old={a.sum():,.2f} sum_new={b.sum():,.2f}")
    if bad.any():
        cols = key + [f"{m}_old", f"{m}_new"]
        print(merged.loc[bad, cols].head(8).to_string())

print(f"\nads without [SKU] token: legacy dropped {dropped_ads_cost:,.2f} | "
      f"matview bucket 'ไม่ระบุ SKU' = {float(bucket['ads_amount'].sum()):,.2f} "
      f"({len(bucket)} rows) — intentional improvement (plan §5.8)")
print("\nPARITY:", "FAILED" if fail else "PASSED")
