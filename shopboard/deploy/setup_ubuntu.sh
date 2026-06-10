#!/usr/bin/env bash
# One-time provisioning of an Ubuntu server for Shop Dashboard
# (nginx + gunicorn + PostgreSQL). Safe to re-run: every step is idempotent.
#
# Usage (as root, e.g. via sudo):
#   ./setup_ubuntu.sh <server_name> [repo_url] [url_prefix]
#
#   server_name  domain or IP nginx should answer on (e.g. dashboard.example.com)
#   repo_url     git URL to clone. Pass "" if the code is already at
#                /srv/shopboard/app (e.g. uploaded with rsync/scp).
#   url_prefix   optional sub-path to serve the app under, e.g. /new_shop
#                (the site then lives at http://server_name/new_shop/)
#
# After it finishes: edit /srv/shopboard/app/shopboard/.env (SMTP, admin password),
# then run deploy/deploy.sh. Full walkthrough in DEPLOY.md.
set -euo pipefail

SERVER_NAME="${1:?usage: setup_ubuntu.sh <server_name> [repo_url] [url_prefix]}"
REPO_URL="${2:-}"
URL_PREFIX="${3:-}"

if [ -n "$URL_PREFIX" ]; then
    case "$URL_PREFIX" in
        /*[!/]) ;;  # must start with / and not end with /
        *) echo "url_prefix must look like /new_shop (leading slash, no trailing slash)"; exit 1 ;;
    esac
fi

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

echo "==> PostgreSQL cluster port"
# Docker containers may already publish 5432/5433 (e.g. jst_db, profit_income_db),
# which prevents the system cluster from binding. Move it to the first free port.
PG_VER=$(pg_lsclusters --no-header | awk '{print $1; exit}')
PG_STATUS=$(pg_lsclusters --no-header | awk '{print $4; exit}')
DB_PORT=$(pg_lsclusters --no-header | awk '{print $3; exit}')
if [ "$PG_STATUS" != "online" ]; then
    DB_PORT=5432
    while ss -ltnH | awk '{print $4}' | grep -q ":$DB_PORT\$"; do
        DB_PORT=$((DB_PORT + 1))
    done
    echo "    cluster is down (port taken) — moving PostgreSQL $PG_VER/main to port $DB_PORT"
    pg_conftool "$PG_VER" main set port "$DB_PORT"
    systemctl restart postgresql
fi
for _ in $(seq 1 15); do
    pg_isready -q -h 127.0.0.1 -p "$DB_PORT" && break
    sleep 1
done
pg_isready -q -h 127.0.0.1 -p "$DB_PORT" || { echo "PostgreSQL did not come up on port $DB_PORT"; exit 1; }
echo "    system PostgreSQL listening on 127.0.0.1:$DB_PORT"

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
DATABASE_URL=postgres://shopboard:$DB_PASS@127.0.0.1:$DB_PORT/shopboard
CSRF_TRUSTED_ORIGINS=http://$SERVER_NAME,https://$SERVER_NAME
# USE_HTTPS=1   # uncomment after certbot
STATIC_URL=$URL_PREFIX/static/
MEDIA_URL=$URL_PREFIX/media/

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
    grep -q "127.0.0.1:$DB_PORT/" "$ENV_FILE" \
        || echo "    WARNING: DATABASE_URL in .env does not point at port $DB_PORT — update it manually"
    grep -q "^STATIC_URL=$URL_PREFIX/static/" "$ENV_FILE" \
        || echo "    WARNING: set STATIC_URL=$URL_PREFIX/static/ and MEDIA_URL=$URL_PREFIX/media/ in .env, then restart shopboard"
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
# don't fight a hand-managed config: if another enabled site already answers
# for this server_name (shared nginx with other apps), leave nginx alone
EXISTING=$(grep -rls "server_name $SERVER_NAME;" /etc/nginx/sites-enabled/ 2>/dev/null | grep -v '/shopboard$' || true)
if [ -n "$EXISTING" ]; then
    echo "    $EXISTING already serves $SERVER_NAME — skipping nginx config."
    echo "    Add the shopboard location blocks there yourself (see DEPLOY.md 'Shared nginx')."
else
    if [ -n "$URL_PREFIX" ]; then
        # gunicorn honors the SCRIPT_NAME header: Django strips the prefix from
        # PATH_INFO and prepends it to every reversed URL automatically
        SCRIPT_NAME_HEADER="proxy_set_header SCRIPT_NAME $URL_PREFIX;"
        PREFIX_REDIRECT="location = $URL_PREFIX { return 301 $URL_PREFIX/; }"
    else
        SCRIPT_NAME_HEADER=""
        PREFIX_REDIRECT=""
    fi
    cat > /etc/nginx/sites-available/shopboard <<EOF
server {
    listen 80;
    server_name $SERVER_NAME;
    client_max_body_size 50M;

    location $URL_PREFIX/static/ {
        alias $PROJ_DIR/staticfiles/;
        access_log off;
        expires 7d;
    }

    location $URL_PREFIX/media/ {
        alias $PROJ_DIR/media/;
    }

    $PREFIX_REDIRECT
    location $URL_PREFIX/ {
        proxy_pass http://unix:/run/shopboard/gunicorn.sock;
        $SCRIPT_NAME_HEADER
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
    }
}
EOF
    ln -sf /etc/nginx/sites-available/shopboard /etc/nginx/sites-enabled/shopboard
    rm -f /etc/nginx/sites-enabled/default
fi
nginx -t
systemctl reload nginx

echo
echo "DONE. Next steps:"
echo "  1. Fill SMTP credentials in $ENV_FILE, then: systemctl restart shopboard"
echo "  2. Open http://$SERVER_NAME$URL_PREFIX/ and log in as 'admin'"
echo "  3. (recommended) TLS: apt install certbot python3-certbot-nginx && certbot --nginx -d $SERVER_NAME"
echo "     then set USE_HTTPS=1 in .env and: systemctl restart shopboard"
