# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

A workspace for rebuilding a Streamlit e-commerce profit/loss dashboard (Thai shops: TikTok/Shopee/Lazada/JST exports) as a **Django application**. The Django project does **not exist yet** — it is to be scaffolded as `shopboard/` at the repo root, following the two plan documents:

- **`DJANGO_MIGRATION_PLAN.md`** — the single source of truth: target architecture, data models, the SQL-first fact layer, exact business-logic formulas (§5), implementation phases, and a pitfalls checklist (§12). The "Decisions already made" table in §1 is final — do not re-litigate stack choices (Django 5.x + PostgreSQL 15+, Django templates + HTMX + Alpine.js, ECharts, email-OTP auth, Docker Compose).
- **`UX_REDESIGN_PLAN.md`** — the UX spec: design system (dark theme, semantic metric colors, Sarabun/Prompt fonts), global filter bar, per-page wireframe specs. Do **not** port the Streamlit screens 1:1.

All user-facing UI strings are **Thai**. Timezone is Asia/Bangkok.

Decisions confirmed by the owner on 2026-06-10 (in addition to the plan's own decision table):

- **Development runs in Docker Compose from day one** (postgres 15 + web), not native venv — local Python is 3.14, ahead of Django 5.x's tested range. Compose postgres publishes on host port **5433** to avoid the pre-existing local server on 5432.
- **OTP policy**: per-user 2FA flag (`User.otp_enabled`) + 30-day remember-this-device signed cookie — the UX plan §4.4 version, not OTP-on-every-login.
- Implementation choices: Django 5.2 LTS, psycopg 3, hand-written CSS design tokens (no Tailwind), ECharts, WhiteNoise for static + nginx for media, console email backend in dev.
- **Test/Live channels** (owner requirement, 2026-06-10): two strictly separated workspaces. `channel` (LIVE/TEST) on Shop and MasterItem (master unique per (channel, sku)); channel-select screen after login; TEST gets a distinct color palette; Google Sheet import and FixCost are LIVE-only; no graduation migration — launching a test product = registering a new LIVE product. Details in DJANGO_MIGRATION_PLAN.md §13.

## The legacy reference app

`shop_dashboard_Streamlit_Sample/` is the existing Streamlit app, kept as the behavioral reference plus real sample data. Treat it as read-only reference — new work goes in the Django project.

- `app.py` — entry point and sidebar routing to the 10 pages in `views/`
- `modules/processing.py` — **the business-logic source of truth** (pandas). The half-built SQL view in `modules/database.py` (`view_processed_sales`) is unused and has known bugs (missing `/100` on COD percent and commissions) — never replicate it.
- `modules/data_loader.py` — Excel parsing, Thai column maps, Google Sheet master import
- `modules/tags.py`, `modules/auth.py`, `modules/otp2.py` — tag CRUD, shared-password auth (being dropped), email OTP sending
- `local_data/` — 374 real Excel files under per-shop folders (`Tiktok1/`, `Shopee1/`, `Lazada1/`, `JST/`; legacy root `sales/` and `ads/`). Used for the `import_legacy` migration and parity testing.

Running the legacy app (only needed for parity comparison):
```powershell
cd shop_dashboard_Streamlit_Sample
python init_db.py        # creates schema in PostgreSQL db "shop_dashboard"
streamlit run app.py
```
It expects a local PostgreSQL with credentials in `.streamlit/secrets.toml` (fallback: `postgres:postgres@localhost:5432/shop_dashboard`). There is no requirements file; deps are streamlit, pandas, sqlalchemy, psycopg2, openpyxl, gspread, toml.

## Critical business rules (full detail in plan §5)

These are the rules most likely to be silently broken — verified against the pandas code:

- **Two-stage aggregation**: box_cost and delivery_cost are **MAX per order, then SUM per day** — never sum them at line grain. Order count = distinct orders per (date, sku_root, shop).
- **Percent columns store numbers like `3` meaning 3%** — divide by 100 in COD (`amount_paid * pct/100 * 1.07` VAT) and commission math.
- Cancelled orders (`สถานะคำสั่งซื้อ == 'ยกเลิก'`) are excluded from everything.
- Order IDs are strings; strip Excel's trailing `.0`.
- SKU matching: exact `sku_norm` first, then `sku_root` (text before first `-`) fallback; both normalized by stripping spaces. Reports group by `sku_root`.
- Ads rows whose campaign name has no `[SKU]` token keep their cost (bucket as 'ไม่ระบุ SKU', don't drop).
- `ProductTag.sku` stays a plain string (no FK) so master re-imports never cascade-delete tags.

## Validation gate

Each migration phase ends runnable (plan §10). The key gate is **numeric parity**: for sample months, daily totals (revenue, each cost column, net profit) from the Django fact layer must exactly match the Streamlit `process_data` output.

## Secrets

`shop_dashboard_Streamlit_Sample/.streamlit/secrets.toml` and `.env` contain real credentials (PostgreSQL, Gmail SMTP, Google service account). If/when this directory is made a git repository, gitignore them before the first commit.
