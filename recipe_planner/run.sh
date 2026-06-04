#!/usr/bin/env bash
set -euo pipefail

export PATH="/opt/shelfserve/venv/bin:${PATH}"
export SHELFSERVE_DATA_DIR="${SHELFSERVE_DATA_DIR:-/data}"
export SHELFSERVE_PORT="${SHELFSERVE_PORT:-8099}"

mkdir -p "${SHELFSERVE_DATA_DIR}/media" "${SHELFSERVE_DATA_DIR}/static"

cd /opt/shelfserve/app

python manage.py migrate --noinput
python manage.py collectstatic --noinput --clear

exec gunicorn shelfserve.wsgi:application \
  --bind "0.0.0.0:${SHELFSERVE_PORT}" \
  --workers 2 \
  --threads 4 \
  --timeout 120 \
  --access-logfile - \
  --error-logfile -
