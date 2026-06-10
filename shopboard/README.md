# Shopboard — Shop Analytics Dashboard (Django)

Django rebuild of the legacy Streamlit `shop_dashboard`. E-commerce profit/loss
analytics for Thai shops with strictly separated **🏪 Live / 🧪 Test** channels.

## Run (Docker, recommended)

```powershell
cd shopboard
copy .env.example .env     # then edit SECRET_KEY / DJANGO_SUPERUSER_* etc.
docker compose up -d --build
```

- App (dev server): http://localhost:8000 — nginx: http://localhost:8080
- Postgres publishes on host port **5433** (5432 is used by the legacy DB container)
- On boot the web container runs migrate → ensure_superuser → collectstatic automatically.
- Login: `DJANGO_SUPERUSER_USERNAME` / `DJANGO_SUPERUSER_PASSWORD` from `.env`.
  In dev the OTP email is printed in `docker compose logs web` (console backend).
- Set `DJANGO_DEBUG=0` + `DJANGO_SETTINGS_MODULE=config.settings.prod` for gunicorn/prod.

## Production deployment (Ubuntu + nginx + gunicorn)

See **[DEPLOY.md](DEPLOY.md)** — one-command provisioning via `deploy/setup_ubuntu.sh`,
updates via `deploy/deploy.sh`, systemd unit and nginx site in `deploy/`.

## One-off legacy data import

The compose file mounts `../shop_dashboard_Streamlit_Sample/local_data` at `/legacy_data`:

```powershell
docker compose exec web python manage.py import_legacy
```

Imports every shop-folder sales/ads file (188 files) into the **LIVE** channel plus
`master_item.xlsx` (798 products), then refreshes the fact matview.

## Verification scripts

```powershell
docker compose exec -T web sh -c "python manage.py shell < scripts/parity_check.py"   # numeric parity vs legacy pandas
docker compose exec -T web sh -c "python manage.py shell < scripts/test_phase5.py"    # page rendering checks
```

⚠️ **Known intentional difference from the old app**: the legacy Streamlit app
under-counted commission and COD costs ×100 (percent double-division bug — see
`DJANGO_MIGRATION_PLAN.md` §14). The new numbers are correct; old reports showed
higher profit than reality.

## Architecture (short)

- `apps/accounts` — users + email-OTP 2FA (per-user flag, 30-day trusted device)
- `apps/core` — TEST/LIVE channel session state, Thai helpers, format tags
- `apps/catalog` — MasterItem (unique per channel+SKU), tags, FixCost, xlsx/Google-Sheet import
- `apps/ingest` — shops, file uploads (sha256 dedup, cascade delete), pandas parsers (`parsers.py` = exact legacy normalizations)
- `apps/analytics` — SQL fact layer (`migrations/0001_fact_layer.py`: `analytics_fact_lines` view + `analytics_fact_daily` matview), all report SQL in `queries.py`, filter state in `filters.py`

Reports are indexed `GROUP BY` over the matview — refresh runs after every ingest,
file delete, and master change (`apps/analytics/facts.py`).
