#!/usr/bin/env sh
set -e

until nc -z "$POSTGRES_HOST" "$POSTGRES_PORT"; do
  echo "Waiting for postgres..."
  sleep 1
done

python manage.py migrate --noinput
python manage.py collectstatic --noinput
python manage.py initialize_platform

exec gunicorn gadget_server.wsgi:application --bind 0.0.0.0:8000 --workers 2 --timeout 60
