#!/usr/bin/env bash
set -euo pipefail

export PATH="/opt/shelfserve/venv/bin:${PATH}"
export SHELFSERVE_DATA_DIR="${SHELFSERVE_DATA_DIR:-/data}"
export SHELFSERVE_PORT="${SHELFSERVE_PORT:-8099}"

LOG_LEVEL="${SHELFSERVE_LOG_LEVEL:-info}"
OPTIONS_FILE="${SHELFSERVE_DATA_DIR}/options.json"
if [[ -f "${OPTIONS_FILE}" ]]; then
  LOG_LEVEL="$(python3 - "${OPTIONS_FILE}" "${LOG_LEVEL}" <<'PY'
import json
import sys

options_file = sys.argv[1]
default = sys.argv[2]

try:
    with open(options_file, encoding="utf-8") as handle:
        value = json.load(handle).get("log_level", default)
except Exception:
    value = default

print(str(value).lower())
PY
)"
fi

case "${LOG_LEVEL}" in
  trace|debug)
    export SHELFSERVE_LOG_LEVEL="debug"
    GUNICORN_LOG_LEVEL="debug"
    ;;
  notice|info)
    export SHELFSERVE_LOG_LEVEL="info"
    GUNICORN_LOG_LEVEL="info"
    ;;
  warning)
    export SHELFSERVE_LOG_LEVEL="warning"
    GUNICORN_LOG_LEVEL="warning"
    ;;
  error)
    export SHELFSERVE_LOG_LEVEL="error"
    GUNICORN_LOG_LEVEL="error"
    ;;
  fatal)
    export SHELFSERVE_LOG_LEVEL="fatal"
    GUNICORN_LOG_LEVEL="critical"
    ;;
  *)
    export SHELFSERVE_LOG_LEVEL="info"
    GUNICORN_LOG_LEVEL="info"
    ;;
esac

# Read server_port from options
SERVER_PORT="$(python3 - "${SHELFSERVE_PORT}" <<'PY'
import json
import sys
default = sys.argv[1]
try:
    with open("/data/options.json", encoding="utf-8") as f:
        value = json.load(f).get("server_port", default)
except Exception:
    value = default
if value is None:
    value = default
print(value)
PY
)"
export SHELFSERVE_PORT="${SERVER_PORT}"

mkdir -p "${SHELFSERVE_DATA_DIR}/media" "${SHELFSERVE_DATA_DIR}/static"

cd /opt/shelfserve/app

python manage.py migrate --noinput
python manage.py collectstatic --noinput --clear

exec gunicorn shelfserve.wsgi:application \
  --bind "0.0.0.0:${SHELFSERVE_PORT}" \
  --workers 2 \
  --threads 4 \
  --timeout 120 \
  --log-level "${GUNICORN_LOG_LEVEL}" \
  --access-logfile - \
  --error-logfile -
