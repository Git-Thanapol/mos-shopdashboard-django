# UX Redesign Plan — Shop Analytics Dashboard (Django Rebuild)

> **Audience:** the implementing agent building the Django + HTMX + Alpine.js replacement for
> `shop_dashboard_Streamlit_Sample/` (Streamlit). This document specifies the **user experience**: information
> architecture, design system, global interaction patterns, and wireframe-level specs per page.
> It complements the technical migration plan (Django models / SQL-first processing / Docker).
> **Do not port the Streamlit screens 1:1** — they have structural UX problems listed below.
>
> **UI language: Thai** (per CLAUDE.md). All labels in this doc shown in Thai are the actual
> strings to use. Code, URLs, and CSS identifiers are English.

---

## 1. Why the current UX fails (observed in the Streamlit code)

| # | Problem | Evidence |
|---|---------|----------|
| 1 | **Filter wall repeated per page** — ~12 controls (year, month, date start/end, fast-filter mode, category, tag, SKU multiselect, 4× %-range inputs, 2 clear buttons, run button) rebuilt on every report page | `views/report_month.py:79-119`, `views/report_daily.py`, `views/report_ads.py`, `views/product_graph.py:51-70` |
| 2 | **Full-page rerun on every click** — changing one dropdown re-renders the whole app and reprocesses data | Streamlit architecture; `app.py` routing |
| 3 | **No URLs** — sidebar buttons + `st.session_state.current_page`; nothing bookmarkable/shareable, back button broken | `app.py:39-62` |
| 4 | **No per-user identity** — everyone is "Admin"; auth state stored in a query param (`?auth=success`) which is trivially forgeable and ugly | `app.py:68`, `modules/auth.py:60` |
| 5 | **Hand-rolled HTML tables** built by f-string concatenation; inconsistent styling (daily table is light-themed inside a dark app), no sorting, no pagination, no export | `views/report_daily.py:187-246`, `modules/ui_components.py:88-192` |
| 6 | **Inconsistent visual language** — three header styles (`header-bar`, `header-gradient-pnl`, plain markdown), two fonts (Sarabun/Prompt), mixed light/dark tables, sticky-column CSS with hardcoded pixel offsets | `modules/ui_components.py` |
| 7 | **Upload flow is opaque** — upload files → separate "🚀 Fetch Data to Database" button → full TRUNCATE+reload, no per-file validation feedback | `views/file_manager.py:144-160`, `modules/data_loader.py:181-288` |
| 8 | **Errors swallowed** — bare `except: pass` everywhere; users see nothing or a generic "Error Loading Data" | `app.py:161-166`, `modules/data_loader.py` |

---

## 2. Design principles

1. **Answer first, controls second.** Every page renders sensible data immediately (current month, all shops) — never an empty page waiting for a "ประมวลผล" click.
2. **Filters are shared state, not per-page furniture.** One global filter bar; selections persist across pages and live in the URL.
3. **Partial updates only.** A filter change swaps the table/chart fragment via HTMX (`hx-get` + `hx-target`), never reloads the shell.
4. **Everything addressable.** Every view, filtered or not, is a copyable URL.
5. **Progressive disclosure.** The 20%-use controls (%-range filters, fast-filter modes) collapse behind a "ตัวกรองขั้นสูง" toggle.
6. **One design system.** One card, one table, one chart container, one number format, one color semantics — defined once in §3, reused everywhere.
7. **Color = meaning.** Keep the existing, learned metric palette (users already associate cyan=sales, green=profit, etc.). Red is reserved for negative values and destructive actions only.

---

## 3. Design system

### 3.1 Theme & typography

- **Dark theme** (preserve user familiarity): page `#111318`, surface/card `#1c1f26`, raised surface `#262a33`, border `#333a45`.
- A **light theme is out of scope** for v1 (current app mixes both inconsistently — that's a bug, not a feature; the daily report's light table is dropped).
- Font: **Sarabun** (body, tables) with **Prompt** for page titles/KPI numbers. Self-host the fonts (on-premise target — no Google Fonts CDN at runtime).
- Numbers: tabular figures (`font-variant-numeric: tabular-nums`), right-aligned in tables, `1,234,567` format, `-` for zero/null (matches current `fmt()` behavior in `report_daily.py:154`).

### 3.2 Semantic metric colors (keep — users know these)

| Token | Hex | Meaning (Thai label) |
|-------|-----|----------------------|
| `--c-sales` | `#33FFFF` | ยอดขายรวม |
| `--c-ops` | `#3498db` | ค่าดำเนินการ (กล่อง+ส่ง+COD) |
| `--c-com` | `#FFD700` | ค่าคอมมิชชั่น |
| `--c-cost` | `#A020F0` | ทุนสินค้า |
| `--c-ads` | `#FF6633` | ค่าโฆษณา |
| `--c-profit` | `#7CFC00` | กำไรสุทธิ |
| `--c-neg` | `#FF4D4D` | ค่าติดลบ / ขาดทุน (soften from pure `#FF0000`) |

### 3.3 Core components (build once as Django template partials)

| Component | Template partial | Notes |
|-----------|-----------------|-------|
| **KPI card row** | `components/kpi_row.html` | 6 cards (ยอดขาย, ค่าดำเนินการ, ค่าคอม, ทุนสินค้า, ค่าแอด, กำไรสุทธิ), value + % of sales, colored left border. Replaces `render_metric_row()` (`ui_components.py:216`). Responsive: 6-up ≥1400px, 3×2 ≥768px, 2×3 below. Skeleton-shimmer state while HTMX swap is in flight. |
| **Global filter bar** | `components/filter_bar.html` | See §4.1. |
| **Data table** | `components/data_table.html` | Server-rendered `<table>`: sticky header, sticky first column (SKU), sticky TOTAL footer row, click-to-sort column headers (HTMX `hx-get` with `?sort=`), negative cells in `--c-neg` bold, row hover, zebra rows. CSV/Excel export button (server-side, same filter querystring). For >200 rows: server pagination (100/page) with a "แสดงทั้งหมด" option. |
| **Chart card** | `components/chart_card.html` | Dark `chart-box` container + title pill + an **ECharts** instance. ECharts over Altair/Chart.js: built-in Thai-friendly tooltips, dataZoom (drag to zoom date ranges), toolbox (save as image), good dark theme, no build step (one static JS file — fits HTMX). Chart receives data as JSON in a `<script type="application/json">` block; a small Alpine/vanilla helper re-inits on `htmx:afterSwap`. |
| **Toast / inline alert** | `components/toast.html` | Success/warn/error toasts via HTMX `HX-Trigger` response header. Replaces silent `except: pass` — every failed action shows a Thai message with detail. |
| **Modal / slide-over** | `components/modal.html` | Alpine-controlled `<dialog>`; used for SKU drill-down, file detail, confirm-delete. |
| **Empty state** | `components/empty.html` | Icon + Thai message + the action that fixes it (e.g. "ยังไม่มีข้อมูล — ไปที่ จัดการไฟล์ เพื่ออัปโหลด"). |

---

## 4. Global UX patterns

### 4.1 Persistent global filter bar (the single biggest UX change)

One sticky bar under the top nav, shared by all report pages, replacing the per-page filter walls:

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ 📅 [เดือนนี้ ▾]  01/06/2026 – 10/06/2026 │ 🏪 ร้านค้า: ทั้งหมด ▾ │ 🔍 ค้นหา SKU/ชื่อสินค้า │ ⚙️ ตัวกรองขั้นสูง ▾ │
└──────────────────────────────────────────────────────────────────────────────┘
```

- **Date range**: preset chips (วันนี้ / 7 วัน / เดือนนี้ / เดือนที่แล้ว / ปีนี้ / กำหนดเอง) + two date inputs. Replaces the year+month+start+end 4-control cluster (`report_month.py:80-85`).
- **Shop**: multi-select checklist dropdown with "เลือกทั้งหมด" (replaces sidebar multiselect in `app.py:122-132`).
- **SKU search**: type-ahead combobox (server-side search over SKU + ชื่อสินค้า, debounced HTMX) supporting multiple chips. Replaces the giant pre-loaded multiselect of every SKU label.
- **ตัวกรองขั้นสูง** (collapsed panel): หมวดหมู่สินค้า, แท็กสินค้า, Fast Filter (ทั้งหมด/มีการเคลื่อนไหว/กำไร/ขาดทุน), กำไร% min–max, แอด% min–max, ปุ่มล้างตัวกรอง. A count badge ("⚙️ ตัวกรองขั้นสูง • 2") shows how many advanced filters are active.
- **State**: every control writes to the querystring (`?from=2026-06-01&to=2026-06-10&shop=Tiktok1,JST&tag=...&cat=...&min_profit_pct=10`); the server also stores the last-used filter set per user (Django session) so navigating between report pages keeps context. **No "ประมวลผล" button** — changes apply on input (HTMX swap of the page's content region, 300ms debounce on text inputs).
- Active filters render as removable chips below the bar: `[Tiktok1 ✕] [แท็ก: หน้าร้อน ✕] [กำไร% ≥ 10 ✕]`.

### 4.2 Navigation & URLs

Top horizontal nav (not a sidebar — frees horizontal space for the wide tables) with grouped items:

```
LOGO │ 🏠 ภาพรวม │ 📊 รายงาน ▾ │ 📈 งบกำไรขาดทุน ▾ │ ⚙️ ตั้งค่า ▾ │        👤 ชื่อผู้ใช้ ▾
       (home)      ├ รายงานรายเดือน        ├ รายปี              ├ จัดการไฟล์/นำเข้าข้อมูล    ├ โปรไฟล์
                   ├ รายงานรายวัน          └ รายเดือน           ├ ตั้งค่าสินค้า (Master)     └ ออกจากระบบ
                   ├ รายงานค่าโฆษณา                             ├ จัดการแท็กสินค้า
                   ├ กราฟสินค้า                                  └ ผู้ใช้งาน (admin only)
                   └ ค่าคอมมิชชั่น
```

URL map:

| URL | Page |
|-----|------|
| `/` | Dashboard home (new, §5.1) |
| `/reports/monthly` | สรุปยอดขายรายเดือน |
| `/reports/daily` | รายงานรายวัน |
| `/reports/ads` | รายงานค่าโฆษณา |
| `/reports/products/graph` | กราฟสินค้า |
| `/reports/commission` | ค่าคอมมิชชั่น |
| `/pnl/yearly`, `/pnl/monthly` | งบกำไรขาดทุน |
| `/data/files`, `/data/imports` | จัดการไฟล์ + ประวัตินำเข้า |
| `/settings/master-items` | ตั้งค่าสินค้า |
| `/settings/tags` | จัดการแท็กสินค้า |
| `/products/<sku>/` | SKU drill-down (new, §5.9) |

Mobile (<768px): nav collapses to a hamburger; filter bar collapses to a "🔍 ตัวกรอง" button opening a full-screen sheet. Report tables scroll horizontally with the SKU column sticky. Phone-first pages: dashboard home and daily report (owners check numbers from phones).

### 4.3 Loading, errors, freshness

- HTMX swaps show a skeleton (KPI cards) or a thin top progress bar (tables); never a blank screen.
- Every page footer shows data freshness: "ข้อมูลล่าสุด: 10 มิ.ย. 2026 14:32 • นำเข้าโดย max" (from the import-history table). Replaces the global "🔄 รีเฟรชข้อมูลล่าสุด" cache-clear button — with SQL-first reporting there is no stale cache to clear.
- Errors: inline alert in the swapped region with a Thai message + "ลองอีกครั้ง" button. No silent failures.

### 4.4 Login (replaces `modules/auth.py`)

Three steps → **one screen**: email + password (Django auth) on a single centered card, then OTP entry on a second card *only if* the account has 2FA enabled (per the migration decision: Django users + email OTP). 6 separate OTP digit boxes with auto-advance, "ส่งรหัสอีกครั้ง (60s)" cooldown link, remember-this-device checkbox (30-day signed cookie skips OTP). Drop the shared password `Mos2025` and the `?auth=success` query param entirely.

---

## 5. Page-by-page specs

### 5.1 `/` Dashboard home — **NEW**

The current app drops users into the monthly report; instead give a landing page answering "วันนี้เป็นยังไง" in 5 seconds:

```
┌ ภาพรวมวันนี้ (10 มิ.ย. 2569)  ─ เทียบกับเมื่อวาน ─────────────────────────┐
│ [ยอดขาย 123,456 ▲12%] [ออเดอร์ 312 ▲5%] [ค่าแอด 23,000 ▼3%] [กำไรสุทธิ 41,200 ▲18%] │
├──────────────────────────────────┬───────────────────────────────────────┤
│ 📈 ยอดขาย & กำไร 30 วันล่าสุด      │ ⚠️ ต้องดู (Alerts)                     │
│ (bar+line, ECharts)              │ • 5 SKU ขาดทุนเดือนนี้ → ดูรายการ        │
│                                  │ • 3 SKU ไม่มีต้นทุนใน Master → แก้ไข    │
│                                  │ • ไม่มีไฟล์ Ads ของ Shopee1 หลัง 8 มิ.ย.│
├──────────────────────────────────┼───────────────────────────────────────┤
│ 🏆 Top 10 สินค้าทำกำไร (เดือนนี้)   │ 💸 Top 10 สินค้าขาดทุน (เดือนนี้)        │
│ มินิเทเบิล รายการ → คลิกไป SKU page │ same                                  │
└──────────────────────────────────┴───────────────────────────────────────┘
```

Alerts are computed by simple SQL checks (loss-making SKUs, SKUs missing master cost, shops with sales but no recent ads file / vice versa). Each alert links to the filtered page that fixes it.

### 5.2 `/reports/monthly` — สรุปยอดขายรายเดือน (port of `report_month.py`)

- Global filter bar (§4.1) replaces lines 79–119 wholesale.
- KPI row on top, then the **SKU × day matrix table**: sticky left block (SKU, ชื่อสินค้า, ออเดอร์, ยอดขาย, กำไร, %กำไร, %แอด) + one column per day — keep this layout, users rely on it, but implement sticky columns with `position: sticky` on semantic classes instead of hardcoded pixel offsets (`ui_components.py:137-143`).
- Day columns: heat-tint cell background by value (light green→deep green for profit; red tint for negative) — the matrix becomes scannable.
- Row click → SKU drill-down slide-over (§5.9). TOTAL footer sticky (keep).
- Column-day header click → jumps to `/reports/daily?date=...`.
- Export: Excel of the visible (filtered) matrix.

### 5.3 `/reports/daily` — รายงานรายวัน (port of `report_daily.py`)

- Date defaults to today; ◀ ▶ arrows + date picker to step days (no rerun cost now).
- KPI row + the per-SKU detail table (`report_daily.py:166-185` columns kept: SKU, ชื่อสินค้า, ออเดอร์, ยอดขาย, ต้นทุน, ค่ากล่อง, ค่าส่ง, COD, Admin, Tele, ค่า Ads, กำไร, ROAS, and the five % columns).
- **Dark-theme the table** (drop the special light `daily-table` styling — it clashes and the CSS fights itself with `!important`, `ui_components.py:97-134`).
- Sortable columns server-side; default sort กำไร desc (current behavior).
- % columns get subtle in-cell bar fills (CSS gradient) so outliers pop.

### 5.4 `/reports/ads` — รายงานค่าโฆษณา (port of `report_ads.py`)

- Same shell. Main table: SKU × ค่าแอดรายวัน + ROAS. Add a summary strip: ค่าแอดรวม, ROAS เฉลี่ย, จำนวนแคมเปญ.
- Secondary tab "รายแคมเปญ": campaign-level table (campaign name, SKU extracted, spend, date range) — currently campaign detail is lost in aggregation; surface it since `raw_ads.campaign_name` is stored.
- Flag rows where ad spend exists but no matching SKU in master (badge "ไม่พบ SKU") — silently dropped today.

### 5.5 `/reports/products/graph` — กราฟสินค้า (port of `product_graph.py`)

- Filter bar + SKU combobox (chips). Charts in chart cards:
  1. แนวโน้มยอดขายรายวัน — multi-series line, ECharts `dataZoom` slider for date brushing, legend click to isolate series.
  2. ยอดขายรวม + จำนวนชิ้น — two bars side by side (keep).
- Add a metric toggle above chart 1: `ยอดขาย | กำไร | ค่าแอด | ออเดอร์` (radio chips) — same chart, different y metric; today users can only see sales.
- Cap visible series at ~12 with a notice; selecting "ทั้งหมด" with 500 SKUs currently produces an unreadable chart.

### 5.6 `/pnl/yearly` and `/pnl/monthly` — งบกำไรขาดทุน (port of `yearly_pnl.py`, `monthly_pnl.py`)

- Keep the structure users like: KPI row → two chart cards (ยอดขาย&กำไรรายเดือน bar+line; donut สัดส่วนค่าใช้จ่าย) → formal P&L statement table (`yearly_pnl.py:126-142`).
- P&L table upgrades: collapsible sub-items (ค่าใช้จ่ายในการขาย ▾), a "% ของยอดขาย" column, and a YoY/MoM comparison column ("เทียบช่วงก่อนหน้า", green/red delta).
- Wire **Fix Cost** in for real: the current code hardcodes 0 (`yearly_pnl.py:43-44` — a latent bug). New Django model `FixCost(year, month, label, amount)` editable inline on this page (admin-permission users), shown as its own P&L line "หัก ค่าใช้จ่ายคงที่".
- Print stylesheet: the P&L statement must print/PDF cleanly on A4 (accountants will want this).

### 5.7 `/reports/commission` — ค่าคอมมิชชั่น (port of `commission.py`)

- KPI row scoped to commissions: รวมค่าคอม Admin, รวมค่าคอม Telesale, % ของยอดขาย.
- Table by SKU and by month (current behavior) + a role toggle `Admin | Telesale | ทั้งหมด`.
- Note for implementer: role attribution comes from `work_type`/`creator` heuristics (`processing.py:160-167`); show "Unknown" rows explicitly with a warning count instead of hiding them.

### 5.8 `/data/files` — จัดการไฟล์/นำเข้าข้อมูล (redesign of `file_manager.py`)

The current page is 4 numbered manual steps; redesign into two tabs:

**Tab 1 — อัปโหลด:**
```
┌ ร้านค้า: [Tiktok1 ▾] [+ เพิ่มร้านค้า]                                        ┐
│ ┌──────────────── 🛒 ไฟล์ยอดขาย ───────────────┐ ┌──────── 📢 ไฟล์โฆษณา ──────┐ │
│ │   ลากไฟล์มาวางที่นี่ หรือ คลิกเลือกไฟล์          │ │   (same dropzone)         │ │
│ └───────────────────────────────────────────────┘ └───────────────────────────┘ │
│ ไฟล์ที่อัปโหลดแล้ว (ตาราง): ชื่อไฟล์ │ ขนาด │ แถว │ ช่วงวันที่ │ สถานะ │ 🗑️        │
└──────────────────────────────────────────────────────────────────────────────┘
```
- Dropzone uploads immediately; each file is parsed and ingested **on upload** (no separate "Fetch" step) with a per-file status chip: ⏳ กำลังประมวลผล → ✅ นำเข้าแล้ว 1,234 แถว / ⚠️ นำเข้าบางส่วน / ❌ ล้มเหลว (คลิกดูรายละเอียด).
- Failure detail modal lists unmatched columns / bad rows — replaces today's silent `print()` + full TRUNCATE reload.
- Deleting a file deletes its rows (requires the per-file ingest design from the migration plan: file registry + `file_id` on rows — incremental, not TRUNCATE).
- Master Item section: upload `master_item.xlsx` **or** "🔄 ดึงจาก Google Sheet" button (the "Both" decision), plus link to edit in-app at `/settings/master-items`.

**Tab 2 — ประวัติการนำเข้า (`/data/imports`):** audit table — เวลา, ผู้ใช้, ร้านค้า, ไฟล์, แถว, สถานะ. This also feeds the freshness footer (§4.3).

### 5.9 `/products/<sku>/` — SKU drill-down — **NEW**

Opened as a slide-over from any table row (and addressable as a full page). Header: SKU, ชื่อสินค้า, หมวดหมู่, tag chips (click to add/remove inline). Body: KPI row scoped to the SKU + filter dates; trend chart (sales/profit/ads); master cost panel (ต้นทุน, ราคากล่อง, ค่าส่ง, % คอมมิชชั่น — edit-in-place for admins); recent orders table. This kills the current workflow of re-filtering an entire report page to inspect one product.

### 5.10 `/settings/master-items` — ตั้งค่าสินค้า (redesign of `master_item.py`)

- Server-paginated editable grid (search by SKU/ชื่อ, filter by หมวดหมู่/มีต้นทุน-ไม่มีต้นทุน). Inline cell editing (HTMX PATCH per row), new-row form, import from xlsx / Google Sheet with a **diff preview** ("จะเพิ่ม 12, แก้ไข 30, ลบ 3 — ยืนยัน?") instead of today's blind TRUNCATE+replace (`data_loader.py:339-342`).
- Badge for SKUs that appear in sales but missing here (the silent-zero-cost trap) — count surfaced on the dashboard alerts too.

### 5.11 `/settings/tags` — จัดการแท็กสินค้า (port of `tag_management.py`)

- Two-pane: left = tag groups (drag to reorder — keep, it's the one thing `streamlit-sortables` did well), right = tags in group (color chip, rename inline, delete with usage count warning "ใช้กับสินค้า 14 รายการ").
- Bulk assignment: pick a tag → searchable SKU checklist with "เลือกตามหมวดหมู่" shortcut.

---

## 6. Accessibility & quality bar

- All interactive elements keyboard-reachable; focus rings visible on dark theme.
- Color is never the only signal: negative numbers get a `-` sign and bold weight, not just red.
- Contrast: verify the metric colors on `#1c1f26` (the current cyan/gold pass; pure `#7CFC00` on white would not — we stay dark).
- Thai date display: พ.ศ. years in UI labels where the current app uses them (e.g. file names use 69 = 2569), ค.ศ. in URLs/ISO everywhere in code.
- Target: report page interactive < 1s on LAN (SQL-first aggregates make this realistic); HTMX fragment swaps < 300ms perceived.

## 7. Build order (UX increments, aligns with the technical migration phases)

1. **Shell**: base template, top nav, dark theme tokens, login (§4.4), toast system.
2. **Global filter bar + KPI row + data table components** — everything else composes these.
3. **Daily report** (simplest full page, validates table component) → **Monthly matrix** (hardest table) → **Ads**.
4. **Dashboard home + SKU drill-down** (new pages, high user value).
5. **Charts**: product graph + P&L pages.
6. **Data management**: file manager redesign + import history; master items; tags.
7. Parity walkthrough against the Streamlit app with real data, then cutover.
