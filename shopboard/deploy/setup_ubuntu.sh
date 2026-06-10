#!/usr/bin/env bash
# One-time provisioning of an Ubuntu server for Shop Dashboard
# (nginx + gunicorn + PostgreSQL). Safe to re-run: every step is idempotent.
#
# Usage (as root, e.g. via sudo):
#   ./setup_ubuntu.sh <server_name> [repo_url]
#
#   server_name  domain or IP nginx should answer on (e.g. dashboard.example.com)
#   repo_url     git URL to clone. Omit if the code is already at /srv/shopboard/app
#                (e.g. uploaded with rsync/scp).
#
# After it finishes: edit /srv/shopboard/app/shopboard/.env (SMTP, admin password),
# then run deploy/deploy.sh. Full walkthrough in DEPLOY.md.
set -euo pipefail

SERVER_NAME="${1:?usage: setup_ubuntu.sh <server_name> [repo_url]}"
REPO_URL="${2:-}"

APP_ROOT=/srv/shopboard
APP_DIR=$APP_ROOT/app            # repo checkout
PROJ_DIR=$APP_DIR/shopboard      # Django project (manage.py lives here)
VENV=$APP_ROOT/venv
ENV_FILE=$PROJ_DIR/.env

[ "$(id -u)" -eq 0 ] || { echo "run as root (sudo)"; exit 1; }

# manage.py defaults to dev settings — production commands must force prod
manage() {
    sudo -u shopboard env DJANGO_SETTINGS_MODULE=config.settings.prod \
        "$VENV/bin/python" "$PROJ_DIR/manage.py" "$@"
}

echo "==> Installing system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip git nginx postgresql

echo "==> Creating service user"
id shopboard >/dev/null 2>&1 || useradd --system --create-home --home-dir $APP_ROOT --shell /usr/sbin/nologin shopboard
mkdir -p $APP_ROOT

echo "==> Fetching code"
if [ ! -d "$APP_DIR/.git" ]; then
    if [ -d "$PROJ_DIR" ]; then
        echo "    code already present at $APP_DIR (no git repo) — leaving as is"
    elif [ -n "$REPO_URL" ]; then
        git clone "$REPO_URL" "$APP_DIR"
    else
        echo "ERROR: no code at $APP_DIR and no repo_url given."
        echo "Either pass a git URL or upload the repo to $APP_DIR first."
        exit 1
    fi
fi

echo "==> Python virtualenv + dependencies"
[ -d "$VENV" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -r "$PROJ_DIR/requirements.txt"

echo "==> PostgreSQL role + database"
DB_PASS_FILE=$APP_ROOT/.db_password
if [ ! -f "$DB_PASS_FILE" ]; then
    openssl rand -hex 24 > "$DB_PASS_FILE"
    chmod 600 "$DB_PASS_FILE"
fi
DB_PASS=$(cat "$DB_PASS_FILE")
sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='shopboard'" | grep -q 1 \
    || sudo -u postgres psql -c "CREATE ROLE shopboard LOGIN PASSWORD '$DB_PASS'"
sudo -u postgres psql -c "ALTER ROLE shopboard PASSWORD '$DB_PASS'"
sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='shopboard'" | grep -q 1 \
    || sudo -u postgres createdb -O shopboard shopboard

echo "==> .env"
if [ ! -f "$ENV_FILE" ]; then
    SECRET=$(openssl rand -hex 32)
    ADMIN_PASS=$(openssl rand -base64 18 | tr -d '/+=')
    cat > "$ENV_FILE" <<EOF
DJANGO_SETTINGS_MODULE=config.settings.prod
DJANGO_DEBUG=0
SECRET_KEY=$SECRET
ALLOWED_HOSTS=$SERVER_NAME
DATABASE_URL=postgres://shopboard:$DB_PASS@127.0.0.1:5432/shopboard
CSRF_TRUSTED_ORIGINS=https://$SERVER_NAME
# USE_HTTPS=1   # uncomment after certbot

DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_EMAIL=admin@example.com
DJANGO_SUPERUSER_PASSWORD=$ADMIN_PASS

# SMTP for OTP mail — FILL THESE IN
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=1
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
DEFAULT_FROM_EMAIL=Shop Dashboard <noreply@$SERVER_NAME>

# Optional Google Sheet master import
GOOGLE_APPLICATION_CREDENTIALS=
SHEET_MASTER_URL=
EOF
    chmod 600 "$ENV_FILE"
    echo "    generated $ENV_FILE — admin password: $ADMIN_PASS  (CHANGE THE EMAIL SETTINGS)"
else
    echo "    $ENV_FILE already exists — left untouched"
fi

echo "==> Permissions"
mkdir -p "$PROJ_DIR/media" "$PROJ_DIR/staticfiles"
chown -R shopboard:www-data "$APP_ROOT"

echo "==> Migrate / collectstatic / superuser"
manage migrate --noinput
manage collectstatic --noinput
manage ensure_superuser

echo "==> systemd service"
cp "$PROJ_DIR/deploy/gunicorn.service" /etc/systemd/system/shopboard.service
systemctl daemon-reload
systemctl enable --now shopboard
systemctl restart shopboard

echo "==> nginx site"
sed "s/SERVER_NAME/$SERVER_NAME/" "$PROJ_DIR/deploy/nginx-shopboard.conf" > /etc/nginx/sites-available/shopboard
ln -sf /etc/nginx/sites-available/shopboard /etc/nginx/sites-enabled/shopboard
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

echo
echo "DONE. Next steps:"
echo "  1. Fill SMTP credentials in $ENV_FILE, then: systemctl restart shopboard"
echo "  2. Open http://$SERVER_NAME/ and log in as 'admin'"
echo "  3. (recommended) TLS: apt install certbot python3-certbot-nginx && certbot --nginx -d $SERVER_NAME"
echo "     then set USE_HTTPS=1 in .env and: systemctl restart shopboard"
