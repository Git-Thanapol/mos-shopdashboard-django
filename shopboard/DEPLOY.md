# Deploying Shop Dashboard — Ubuntu + nginx + gunicorn

Production layout (native, no Docker):

```
internet ──> nginx :80/:443 ──> gunicorn (unix socket) ──> Django (config.settings.prod)
                 │                                              │
                 ├── /static/  → /srv/shopboard/app/shopboard/staticfiles/
                 ├── /media/   → /srv/shopboard/app/shopboard/media/
                 └──                                       PostgreSQL (localhost)
```

| What | Where |
|---|---|
| Code (repo checkout) | `/srv/shopboard/app` |
| Django project | `/srv/shopboard/app/shopboard` |
| Virtualenv | `/srv/shopboard/venv` |
| Environment / secrets | `/srv/shopboard/app/shopboard/.env` (chmod 600) |
| gunicorn service | `systemctl {status,restart} shopboard` |
| gunicorn socket | `/run/shopboard/gunicorn.sock` |
| nginx site | `/etc/nginx/sites-available/shopboard` |
| DB password | `/srv/shopboard/.db_password` (generated) |

Tested target: Ubuntu 22.04/24.04 LTS (PostgreSQL 14/16 — the app needs 15+ features
only via standard SQL, both work; prefer 24.04).

## 1. First-time setup

On the server, as a sudo-capable user:

```bash
# A) code from a git remote:
wget https://<your-repo-host>/.../setup_ubuntu.sh   # or scp shopboard/deploy/setup_ubuntu.sh
sudo bash setup_ubuntu.sh dashboard.example.com https://github.com/you/Django_ShopDashboard.git

# B) no git remote — upload the repo first, then run the script from it:
#    (from your Windows machine)
#    scp -r C:\Users\Thana\GitHub\Django_ShopDashboard user@server:/tmp/app
#    (on the server)
sudo mkdir -p /srv/shopboard && sudo mv /tmp/app /srv/shopboard/app
sudo bash /srv/shopboard/app/shopboard/deploy/setup_ubuntu.sh dashboard.example.com
```

`setup_ubuntu.sh` is idempotent (safe to re-run) and does, in order: apt packages
(python3, git, nginx, postgresql) → `shopboard` system user → clone/keep code →
venv + `pip install -r requirements.txt` → PostgreSQL role+db with a generated
password → generate `.env` (SECRET_KEY, DB URL, random admin password — **printed
once, save it**) → migrate, collectstatic, `ensure_superuser` → install + start
the `shopboard` systemd service → install + reload the nginx site.

## 2. After setup (required)

1. **SMTP for OTP mail** — edit `/srv/shopboard/app/shopboard/.env`:
   `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` (Gmail app password) and
   `DEFAULT_FROM_EMAIL`. Then `sudo systemctl restart shopboard`.
2. **Log in** at `http://<server_name>/` with `admin` + the printed password;
   change it in Django admin (`/admin/`).
3. **TLS (strongly recommended** — OTP codes and passwords travel over this):
   ```bash
   sudo apt install certbot python3-certbot-nginx
   sudo certbot --nginx -d dashboard.example.com
   ```
   then set `USE_HTTPS=1` in `.env` and `sudo systemctl restart shopboard`.
   (`USE_HTTPS` turns on secure cookies + HSTS; leave it off while serving plain HTTP,
   otherwise login breaks.)

## 3. Importing the legacy Excel data (optional, one-time)

Upload the legacy files and run the importer:

```bash
# from Windows
scp -r shop_dashboard_Streamlit_Sample/local_data user@server:/tmp/legacy_data
# on the server
sudo chown -R shopboard /tmp/legacy_data
sudo -u shopboard env DJANGO_SETTINGS_MODULE=config.settings.prod \
    /srv/shopboard/venv/bin/python \
    /srv/shopboard/app/shopboard/manage.py import_legacy --data-dir /tmp/legacy_data
sudo rm -rf /tmp/legacy_data   # real business data — don't leave it in /tmp
```

## 4. Updating to a new version

```bash
sudo bash /srv/shopboard/app/shopboard/deploy/deploy.sh
```

(git pull → pip install → migrate → collectstatic → restart gunicorn.
If there is no git remote, rsync the repo to `/srv/shopboard/app` first;
the script skips the pull when no `.git` is present.)

## 5. Operations cheat-sheet

```bash
sudo systemctl status shopboard          # gunicorn state
sudo journalctl -u shopboard -f          # app logs (gunicorn access+error)
sudo systemctl restart shopboard         # after editing .env
sudo nginx -t && sudo systemctl reload nginx
sudo -u postgres pg_dump shopboard | gzip > /srv/shopboard/backup_$(date +%F).sql.gz   # DB backup
```

Uploaded Excel files live in the database **and** `/srv/shopboard/app/shopboard/media/`
— include both in backups.

## 6. Troubleshooting

| Symptom | Check |
|---|---|
| 502 Bad Gateway | `systemctl status shopboard`; socket exists at `/run/shopboard/gunicorn.sock` |
| CSRF error on login | `ALLOWED_HOSTS` + `CSRF_TRUSTED_ORIGINS` in `.env` match the domain (with `https://` prefix for the latter) |
| Login loops / cookie not set | `USE_HTTPS=1` set while still on plain HTTP — remove it |
| OTP mail not arriving | `journalctl -u shopboard` for SMTP errors; Gmail requires an app password |
| Static files 404 | re-run `collectstatic` via `deploy.sh`; nginx alias path ends with `/` |
| Thai dates wrong | server timezone irrelevant — app pins `Asia/Bangkok`; check `TIME_ZONE` untouched |
