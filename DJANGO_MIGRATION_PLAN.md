# Shop Dashboard → Django Migration Plan

> **Audience:** the implementing agent/developer. This document is the single source of truth
> for rebuilding `shop_dashboard_Streamlit_Sample` (Streamlit) as a Django application. Read the
> "Business Logic Reference" section carefully — it encodes behavior currently buried in
> pandas code, including known inconsistencies you must NOT blindly copy.

---

## 1. Context & Goals

The current app (`shop_dashboard_Streamlit_Sample/`, ~4,000 lines of Streamlit) is an e-commerce
profit/loss analytics dashboard for Thai shops (TikTok/Shopee/Lazada, JST exports).
It has hit Streamlit's limits:

- **Slow full-page reruns** — every widget click re-executes the script; all report math is
  done in pandas on the full dataset per run (`modules/processing.py:process_data`, cached only 10 min).
- **Multi-user limits** — one shared password (`Mos2025`, hardcoded in `modules/auth.py:12`),
  no per-user identity, session state is fragile.
- **UI/UX limitations** — layout hacks with raw HTML/CSS injection, no proper tables/filters.
- **Hard to extend** — no background jobs, APIs, permissions, or audit trail.

### Decisions already made (do not re-litigate)

| Topic | Decision |
|---|---|
| Backend | Django 5.x (LTS preferred) + PostgreSQL 15+ |
| Frontend | Django templates + **HTMX** + **Alpine.js** (no SPA) |
| Charts | ECharts (or Chart.js) rendered client-side from JSON endpoints |
| Processing | **SQL-first**: compute facts in PostgreSQL; pandas only for Excel/CSV parsing at ingest |
| Auth | Django users + **email OTP second step** (per-user accounts, admin-created) |
| Master Item | **In-app CRUD is the source of truth**, with optional one-way import from the existing Google Sheet |
| Deployment | Docker Compose: nginx + gunicorn (Django) + postgres (+ worker later if needed) |
| Scope | `shop_dashboard_Streamlit_Sample` only now; structure the project so `profit_income` and `stock_jst` can be added as Django apps later |
| UI language | **All user-facing strings in Thai** (same as today) |

---

## 2. Target Architecture

```
shopboard/                      # new top-level Django project (sibling of shop_dashboard_Streamlit_Sample/)
├── manage.py
├── pyproject.toml / requirements.txt
├── docker-compose.yml          # nginx, web (gunicorn), db (postgres 15)
├── Dockerfile
├── nginx/
│   └── shopboard.conf
├── config/                     # Django project package
│   ├── settings/ (base.py, dev.py, prod.py)
│   ├── urls.py
│   └── wsgi.py
├── apps/
│   ├── accounts/               # users, email-OTP login flow
│   ├── catalog/                # master items, tag groups/tags/product-tags, Google Sheet import
│   ├── ingest/                 # shops, file uploads, parsing, sales/ads line storage
│   └── analytics/              # SQL views/materialized views, report pages, chart JSON endpoints
├── templates/                  # base layout (dark theme), per-app templates, HTMX partials
└── static/                     # Tailwind (standalone CLI) or minimal CSS, Alpine.js, ECharts, htmx.min.js
```

### Request flow for a report page

1. Full page request renders the filter bar + empty results shell.
2. Filter changes / "ประมวลผล" button issue HTMX GET to a partial endpoint with query params.
3. Partial endpoint runs **one SQL aggregate query** against the fact layer (Section 4),
   renders a table partial; chart data served as JSON to ECharts.
4. No full-page reloads; state lives in the URL query string (shareable/bookmarkable).

### Why this is faster than today

Today every interaction re-reads `raw_sales` into pandas, re-joins master, recomputes every
cost column for all history, then filters (`modules/processing.py:41-293`). The new design
computes facts **once at ingest** (and on master-item change), so report queries are indexed
`GROUP BY` over a pre-joined fact source — milliseconds, not seconds, regardless of history size.

---

## 3. Data Model (Django models → PostgreSQL)

Keep a **new clean schema** (new database `shopboard`); a one-off management command migrates
existing data (Section 8). Don't reuse the old tables in place — the old app stays runnable
in parallel until cutover.

### 3.1 `ingest` app

```python
Shop(models.Model):
    name        # unique; today shops are folders under local_data/ (e.g. Tiktok1, JST)
    is_active   # bool, default True

UploadedFile(models.Model):
    shop        # FK Shop
    kind        # choices: SALES / ADS
    file        # FileField (MEDIA_ROOT/uploads/<shop>/<kind>/)
    original_name
    sha256      # unique together with shop+kind → skip duplicate uploads
    status      # PENDING / PROCESSED / ERROR (+ error_message text)
    row_count
    uploaded_by # FK user
    uploaded_at

SalesLine(models.Model):        # one row per file line, RAW values preserved + normalized columns
    file        # FK UploadedFile (CASCADE → deleting a file removes its rows)
    shop        # FK Shop (denormalized for query speed)
    order_id    # str, indexed
    status      # str  (cancelled = 'ยกเลิก')
    courier_raw / courier_norm
    order_time  # datetime;  date = order_time::date (indexed)
    sku_raw     # 'รูปแบบสินค้า' as-is
    sku_norm    # spaces stripped
    sku_root    # sku_norm before first '-'  (this is "SKU_Main" everywhere in reports)
    quantity    # int
    amount_paid # numeric
    creator / payment_method / work_type
    product_name
    role        # computed at ingest: Admin / Telesale / Unknown (rules in §5.6)
    is_cod      # computed at ingest (rules in §5.5)

AdSpend(models.Model):
    file        # FK UploadedFile (CASCADE)
    shop        # FK Shop
    date
    campaign_name
    sku_root    # extracted from campaign name (rules in §5.8); nullable
    cost        # numeric
```

**Key improvement over today:** the current app does `TRUNCATE raw_sales, raw_ads` and re-reads
*all 374+ files* on every "Fetch Data" click (`modules/data_loader.py:181-288`). The new model is
**incremental**: each file ingests once (dedup by sha256), deleting a file deletes its rows,
and only affected dates need fact refresh.

### 3.2 `catalog` app

```python
MasterItem(models.Model):
    sku         # unique, normalized (spaces stripped)
    name, type  # type default 'กลุ่ม ปกติ'
    cost, box_cost, delivery_cost          # numeric, default 0
    com_admin_pct, com_tele_pct            # stored as PERCENT (e.g. 3 = 3%) — see §5.7
    p_jnt, p_flash, p_kerry, p_thai_post, p_dhl, p_spx, p_lex, p_std
                                           # courier COD % (e.g. 3 = 3%) — see §5.5
    updated_at, updated_by

TagGroup(name unique, color, sort_order, is_visible)
Tag(group FK, name, color, sort_order; unique (group, name))
ProductTag(sku str — intentionally NOT an FK, tag FK; unique (sku, tag))
FixCost(models.Model):
    year, month       # unique together
    label / category  # mirror columns of the FIX_COST sheet (inspect sheet during migration)
    amount
```

The tag schema mirrors the existing one (`modules/database.py:126-150`) — port `modules/tags.py`
(450 lines of psycopg SQL) to the Django ORM.

### 3.3 `accounts` app

- Standard `User` (use `AbstractUser` from day one — cheap now, painful later).
- `EmailOTP(user FK, code, created_at, expires_at, used)` — 6-digit code, 5-min expiry,
  invalidated on use. Reuse SMTP settings currently in `.streamlit/secrets.toml [gmail]`;
  sending logic reference: `modules/otp2.py`.
- Login flow: username+password → if valid, email OTP → verify → session login.
  Rate-limit OTP attempts (e.g. 5 tries / lockout 10 min).
- Admin creates users in Django admin. The old shared-password flow is **dropped**.

---

## 4. SQL-First Fact Layer (the performance core)

Costs depend on `MasterItem`, which users edit — so facts must be derivable. Use a
**plain SQL view for line-level facts** + a **materialized view for the daily grain**:

### 4.1 `analytics_fact_lines` (regular view)

Join `SalesLine` ↔ `MasterItem` and compute per-line costs. Lookup order for master match
(replicates pandas fallback at `modules/processing.py:95-128`):

1. exact: `sales.sku_norm = master.sku`
2. fallback: `sales.sku_root = master.sku`
3. else: costs = 0, name = file's product_name

Computed columns (exact formulas in §5): `unit_cost`, `product_cost = quantity * unit_cost`,
`ship_percent` (by courier_norm), `cod_cost`, `com_admin`, `com_tele`, `display_name`, `product_type`.
Excludes rows with `status = 'ยกเลิก'`.

### 4.2 `analytics_fact_daily` (MATERIALIZED VIEW, the workhorse)

Two-stage aggregation — **this is subtle, do not flatten it** (see §5.9):

- Stage 1 — collapse to **order** grain (`GROUP BY order_id`):
  `SUM(quantity, amount_paid, product_cost, cod_cost, com_admin, com_tele)`,
  but `MAX(box_cost)`, `MAX(delivery_cost)` — box & delivery are charged **once per order**,
  not per line. `Date/sku_root/shop/name/type` = first.
- Stage 2 — collapse orders to **(date, sku_root, shop)** grain:
  `COUNT(orders)`, `SUM(...)` everything, box/delivery now SUM.
- `FULL OUTER JOIN` ads aggregated to the same grain
  (`SELECT date, sku_root, shop, SUM(cost) FROM ad_spend GROUP BY 1,2,3`).
- Final columns: `orders, quantity, revenue, product_cost, box_cost, delivery_cost,
  cod_cost, com_admin, com_tele, ads_amount, other_costs, total_cost, net_profit`
  (formulas in §5.10). Unique index on `(date, sku_root, shop)` so
  `REFRESH MATERIALIZED VIEW CONCURRENTLY` works.

### 4.3 Refresh triggers

`REFRESH MATERIALIZED VIEW CONCURRENTLY analytics_fact_daily` after:
- any file ingest / file delete,
- any MasterItem save (debounce: refresh once per request, not per row),
- Google Sheet import.

Data volume is small (~6.6 MB of files today); a full concurrent refresh will take well under
a second for years of data. **Do not** build incremental fact maintenance yet — revisit only if
refresh ever exceeds a few seconds. Run refresh synchronously in the request; no Celery/worker
needed at current scale (leave a `worker` service stub commented out in compose).

### 4.4 Report queries

Every report page is then `SELECT ... FROM analytics_fact_daily WHERE date BETWEEN ... AND shop IN (...)
[AND sku_root IN (...)] GROUP BY <page grain>`. Map it with a thin unmanaged Django model or raw SQL
+ dataclasses — implementer's choice, but keep all report SQL in `apps/analytics/queries.py`.

---

## 5. Business Logic Reference (port EXACTLY, with noted fixes)

Source of truth = the **pandas path** (`modules/processing.py`), NOT the half-built SQL view in
`modules/database.py:157-244` — that view is unused and has two known bugs (missing `/100` on
COD percent and commissions). Verified behaviors to replicate:

### 5.1 Numeric parsing (`safe_float`, processing.py:11-18)
Strip `,` `฿` spaces; `'-', 'nan', 'None', ''` → 0; `'x%'` → `x/100`; unparseable → 0.
Apply at **ingest** (pandas), so DB columns are clean numerics.

### 5.2 Order-ID cleanup (data_loader.py:62-63)
Read as string; strip trailing `.0` (Excel float artifact): `str.replace(r'\.0$', '')`.

### 5.3 SKU normalization (processing.py:79, 91-93)
`sku_norm = sku_raw.strip().replace(' ', '')`; `sku_root = sku_norm.split('-')[0]`.
Master SKUs normalized the same way before matching.

### 5.4 Courier normalization (processing.py:24-38)
Map to canonical names: J&T Express, Flash Express, Kerry Express, ThailandPost, DHL_1,
SPX Express (incl. "Shopee Express"), LEX TH (incl. "Lazada Express"). Null/empty →
`'Standard Delivery - ส่งธรรมดาในประเทศ'`. Unknown values pass through (→ falls to `p_std`).

### 5.5 COD cost (processing.py:142-158)
- `is_cod` = payment_method contains `cod` (case-insensitive) or `ปลายทาง`.
- `ship_percent` = master column matching the normalized courier (`p_jnt`…), else `p_std`.
- `cod_cost = amount_paid * (ship_percent / 100) * 1.07` (1.07 = VAT). **Note the `/100`**:
  master stores `3` meaning 3%. Keep storing percent-as-number (matches the Google Sheet and
  master UI), divide in SQL.

### 5.6 Role detection (processing.py:160-167)
work_type or creator contains `admin`/`แอดมิน` → `Admin`; `tele`/`เทเล` → `Telesale`;
else `Unknown`. (Admin checked first wins.)

### 5.7 Commissions (processing.py:169-175)
`com_admin = amount_paid * (com_admin_pct / 100)` only when role == Admin; analogous for
Telesale. Again: stored as percent-number, divide by 100 in SQL.

### 5.8 Ads SKU extraction (processing.py:200-219)
From campaign name: regex `\[(.*?)\]` (first bracketed token), then strip spaces → `sku_root`.
Rows without a match keep cost but `sku_root = NULL` (they currently aggregate under NaN;
decide: show them as 'ไม่ระบุ SKU' bucket — better than silently dropping ad spend).
Ads column detection at ingest: cost = first of `['จำนวนเงินที่ใช้จ่ายไป (THB)', 'Cost', 'Amount']`,
date = `['วัน', 'Date']`, campaign = `['ชื่อแคมเปญ', 'Campaign']`.

### 5.9 Two-stage aggregation (processing.py:180-241) — CRITICAL
Box cost & delivery cost are **MAX per order** then **SUM per day**. A 3-line order with
box_cost 5 contributes 5, not 15. Order count = distinct orders per (date, sku_root, shop).
An order's date/sku attribution = first line's values.

### 5.10 Final daily measures (processing.py:248-251)
```
other_costs = box_cost + delivery_cost + cod_cost + com_admin + com_tele
total_cost  = product_cost + other_costs + ads_amount
net_profit  = revenue - total_cost
```

### 5.11 Misc
- Cancelled orders (`สถานะคำสั่งซื้อ == 'ยกเลิก'`) excluded from everything (processing.py:73-74).
- Thai month names list (processing.py:8-9) — make a shared util; all date pickers/labels use them.
- Default product type `'กลุ่ม ปกติ'`; category filter options = distinct master types (processing.py:287-291).
- Sales-file Thai column map → field names: see `modules/data_loader.py:220-232` (the `col_map` dict).
- Master sheet columns `ทุน`/`ต้นทุน` both mean cost (processing.py:50-51).

---

## 6. Pages to Build (parity list)

Same sidebar structure, Thai labels, dark theme. Global filters on every report page:
date range (with year/month quick-set), shop multi-select, SKU multi-select
(`"SKU : ชื่อสินค้า"` labels), category (Type), tag, fast-filter mode
(มีการเคลื่อนไหว / กำไร / ขาดทุน / ทั้งหมด), and min/max %กำไร และ %แอด range filters
(see `views/report_month.py:87-119` for current semantics).

| # | Page (Thai menu label) | Current file | Core content |
|---|---|---|---|
| 1 | 📊 รายงานภาพรวม | `views/report_month.py` | Per-SKU monthly table: revenue, costs breakdown, ads, net profit, %กำไร, %แอด + metric cards |
| 2 | 📢 รายงานค่าโฆษณา | `views/report_ads.py` | Ads spend vs revenue per SKU/day |
| 3 | 📅 รายงานรายวัน | `views/report_daily.py` | Day-grain table for selected range |
| 4 | 📈 กราฟสินค้า | `views/product_graph.py` | Time-series chart per selected SKUs (ECharts line) |
| 5 | 📈 งบกำไรขาดทุน (ปี) | `views/yearly_pnl.py` | Yearly P&L incl. FixCost rows |
| 6 | 📅 งบกำไรขาดทุน (เดือน) | `views/monthly_pnl.py` | Monthly P&L incl. FixCost |
| 7 | 💰 ค่าคอมมิชชั่น | `views/commission.py` | Admin/Telesale commission summaries |
| 8 | 📂 จัดการไฟล์ | `views/file_manager.py` | Shop CRUD, per-shop sales/ads upload, file list w/ status & delete, re-ingest |
| 9 | 🔧 ตั้งค่าสินค้า (Master) | `views/master_item.py` | MasterItem CRUD table (inline edit), Google Sheet import button |
| 10 | 🏷️ จัดการแท็กสินค้า | `views/tag_management.py` | Tag groups/tags CRUD, assign tags to SKUs |

Read each current view before building its replacement — they contain small per-page rules
(column orders, footer totals, % formulas) not repeated here. Improve UX where Streamlit was
the constraint (server-side pagination/sort on tables, sticky filter bar, URL-encoded state),
but keep the numbers identical.

---

## 7. Google Sheet Import (Master Item)

- Source of truth = the in-app MasterItem table.
- "นำเข้าจาก Google Sheet" button on the Master page: one-way import from
  `SHEET_MASTER_URL` worksheet `MASTER_ITEM` (and `FIX_COST` / `FIXED_COST` for FixCost),
  same column mapping as `modules/data_loader.py:290-346`. Upsert by SKU; show a diff
  preview (added/updated counts) before commit if cheap to build, else just import + report.
- Service-account JSON moves from `.streamlit/secrets.toml` to env vars / a mounted
  `service_account.json` referenced by `GOOGLE_APPLICATION_CREDENTIALS`.
- If the Sheet/credentials are absent the app must work fully (on-premise mode).

---

## 8. Migration of Existing Data

Management command `import_legacy`:
1. Create `Shop` rows from `local_data/<ShopName>/` folders (skip legacy root `sales/`, `ads/`).
2. Register & ingest every file under each shop's `sales/` and `ads/` via the normal pipeline
   (so history gets full computed columns + file provenance).
3. Import `local_data/master_item.xlsx` (or the Google Sheet) into MasterItem/FixCost.
4. Copy tag tables (`tag_groups`, `tags`, `product_tags`) from the old `shop_dashboard_Streamlit_Sample` database.
5. Refresh materialized view; print row counts per table for verification.

---

## 9. Deployment (Docker Compose)

```yaml
services:
  db:        postgres:15-alpine, volume pgdata_shopboard, healthcheck pg_isready
  web:       build ., gunicorn config.wsgi -w 3, env: DATABASE_URL/SECRET_KEY/SMTP_*/ALLOWED_HOSTS
             volumes: media (uploads), depends_on db healthy
             entrypoint runs: migrate → ensure matviews → collectstatic → gunicorn
  nginx:     serves /static + /media, proxies to web, port 80 (TLS later)
```

- Settings via `django-environ`; `.env` file gitignored, `.env.example` committed.
- `MEDIA_ROOT` volume holds uploaded files (replaces `local_data/`).
- Timezone `Asia/Bangkok`; `LANGUAGE_CODE = 'th'` (UI strings written directly in Thai;
  no i18n framework needed).
- WhiteNoise acceptable instead of nginx static if it simplifies; nginx still fronts uploads
  (client_max_body_size ≥ 50M for Excel batches).

---

## 10. Implementation Phases (each ends runnable & testable)

1. **Scaffold** — project layout, settings, Docker Compose, base template (dark theme,
   Thai sidebar), accounts app with email-OTP login. ✔ Gate: login works in Docker.
2. **Catalog** — MasterItem/FixCost/Tag models + admin + CRUD pages + Google Sheet import.
   ✔ Gate: master data visible/editable.
3. **Ingest** — Shop/UploadedFile/SalesLine/AdSpend, upload UI (HTMX progress), parser
   (pandas, §5.1-5.8 normalizations), dedup, file delete. ✔ Gate: `import_legacy` ingests all
   374 existing files; row counts match old `raw_sales`/`raw_ads`.
4. **Fact layer** — `analytics_fact_lines` view + `analytics_fact_daily` matview as a Django
   migration (`RunSQL`), refresh hooks. ✔ Gate: **parity test** — for 2-3 sample months, daily
   totals (revenue, each cost, net profit) match the Streamlit app's numbers exactly
   (write a comparison script against old `process_data` output).
5. **Reports** — pages 1-7 in §6, one at a time, table partials + ECharts. ✔ Gate: visual +
   numeric parity per page.
6. **Cutover** — run both apps in parallel ≥1 week, user validates, then retire Streamlit
   (keep `shop_dashboard_Streamlit_Sample/` code until profit_income/stock_jst migrations are planned).

## 11. Non-goals (for now)
- No DRF/public API, no Celery/Redis, no SPA, no incremental matview maintenance,
  no migration of `profit_income` / `stock_jst` (but: keep `apps/` namespacing and the
  shared postgres container ready for them).

## 12. Known pitfalls checklist for the implementer
- [ ] Use pandas semantics, not the buggy `view_processed_sales` (missing `/100` twice).
- [ ] Box/delivery cost = MAX per order, then SUM (§5.9).
- [ ] Percent columns stored as numbers like `3` (= 3%); divide by 100 in COD & commission SQL.
- [ ] Order IDs are strings; strip Excel's trailing `.0`.
- [ ] Cancelled (`ยกเลิก`) orders excluded everywhere.
- [ ] Ads rows with no `[SKU]` in campaign name must not lose their cost.
- [ ] SKU master matching: exact `sku_norm` first, then `sku_root` fallback.
- [ ] All UI strings in Thai; Thai month names from the shared util.
- [ ] Matview needs a UNIQUE index for `REFRESH ... CONCURRENTLY`.
- [ ] `ProductTag.sku` stays a plain string (no FK) so master re-imports never cascade-delete tags.

---

## 13. ADDENDUM (2026-06-10): Test/Live channels — owner requirement

The owner requires two **completely separated workspaces** ("channels"): **LIVE** (real store)
and **TEST** (products being trialed, not actually sold in the store yet).

- `Channel` enum `LIVE | TEST`. Add `channel` to **Shop** and **MasterItem**;
  denormalize onto `SalesLine`/`AdSpend` at ingest (a file inherits its shop's channel).
- `MasterItem` uniqueness becomes **(channel, sku)** — when a test product launches, the user
  registers a NEW live product; test history stays in TEST forever (no graduation migration).
- Fact layer: carry `channel`; master join must match within the same channel. All report
  queries are strictly channel-scoped.
- UI: after login show a **channel-select screen** (2 cards). Channel persists in session with
  a nav switcher. TEST uses a distinct color palette (amber/violet accents) on the same layout
  so the separation is visually obvious.
- Feature gating: Google Sheet master import is LIVE-only (TEST products are hand-registered).
  FixCost / fixed-cost P&L lines are LIVE-only.
- `import_legacy`: all existing shops/files/master rows → LIVE.
