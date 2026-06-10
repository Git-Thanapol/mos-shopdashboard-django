#!/bin/sh
set -e

echo "Applying database migrations..."
python manage.py migrate --noinput

echo "Ensuring superuser exists..."
python manage.py ensure_superuser

echo "Collecting static files..."
python manage.py collectstatic --noinput

if [ "$DJANGO_DEBUG" = "1" ]; then
    echo "Starting Django dev server (DEBUG)..."
    exec python manage.py runserver 0.0.0.0:8000
else
    echo "Starting gunicorn..."
    exec gunicorn config.wsgi:application -w 3 -b 0.0.0.0:8000 --access-logfile -
fi
