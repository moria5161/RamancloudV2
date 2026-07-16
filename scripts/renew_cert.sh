#!/usr/bin/env bash
set -euo pipefail

DOMAIN="ramancloud.xmu.edu.cn"
LIVE_DIR="/etc/letsencrypt/live/${DOMAIN}"
TARGET_DIRS=(
  "/www/server/panel/vhost/cert/219.229.100.24"
  "/www/server/panel/vhost/cert/${DOMAIN}"
  "/www/server/panel/vhost/ssl/${DOMAIN}"
)

if [[ ! -r "${LIVE_DIR}/fullchain.pem" || ! -r "${LIVE_DIR}/privkey.pem" ]]; then
  echo "Missing Let's Encrypt certificate files under ${LIVE_DIR}" >&2
  exit 1
fi

for target in "${TARGET_DIRS[@]}"; do
  mkdir -p "${target}"
  install -m 0644 "${LIVE_DIR}/fullchain.pem" "${target}/fullchain.pem"
  install -m 0600 "${LIVE_DIR}/privkey.pem" "${target}/privkey.pem"
done

/www/server/nginx/sbin/nginx -t
/www/server/nginx/sbin/nginx -s reload

openssl x509 -in "${LIVE_DIR}/fullchain.pem" -noout -subject -issuer -dates
