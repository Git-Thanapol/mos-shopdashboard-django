#!/usr/bin/env bash
# Redeploy Shop Dashboard on the server after the first setup_ubuntu.sh run.
# Pulls the latest code, installs deps, migrates, collects static, restarts gunicorn.
#
# Usage (as root, e.g. via sudo):  ./deploy.sh
set -euo pipefail

APP_ROOT=/srv/shopboard
APP_DIR=$APP_ROOT/app
PROJ_DIR=$APP_DIR/shopboard
VENV=$APP_ROOT/venv

[ "$(id -u)" -eq 0 ] || { echo "run as root (sudo)"; exit 1; }

# manage.py defaults to dev settings — production commands must force prod
manage() {
    sudo -u shopboard env DJANGO_SETTINGS_MODULE=config.settings.prod \
        "$VENV/bin/python" "$PROJ_DIR/manage.py" "$@"
}

if [ -d "$APP_DIR/.git" ]; then
    echo "==> git pull"
    # pull as root (mixed file ownership otherwise trips git's dubious-ownership
    # check), then hand everything back to the service user
    git config --global --get-all safe.directory 2>/dev/null | grep -qx "$APP_DIR" \
        || git config --global --add safe.directory "$APP_DIR"
    git -C "$APP_DIR" pull --ff-only
    chown -R shopboard:www-data "$APP_DIR"
else
    echo "==> no git repo at $APP_DIR — assuming code was uploaded manually (rsync/scp)"
fi

echo "==> dependencies"
"$VENV/bin/pip" install -q -r "$PROJ_DIR/requirements.txt"

echo "==> migrate + collectstatic"
manage migrate --noinput
manage collectstatic --noinput

echo "==> restart gunicorn"
systemctl restart shopboard
systemctl --no-pager --lines=5 status shopboard

echo "DONE."
