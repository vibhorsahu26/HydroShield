#!/bin/sh
set -eu


exec uvicorn app.main:app \
  --host "${HYDROSHIELD_HOST:-0.0.0.0}" \
  --port "${HYDROSHIELD_PORT:-8000}" \
  --workers 1 \
  --proxy-headers \
  --forwarded-allow-ips "${HYDROSHIELD_FORWARDED_ALLOW_IPS:-127.0.0.1}"
