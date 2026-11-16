#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/media/ramancloud_rebuild"
STATIC_DIR="/www/wwwroot/219.229.100.24/ramancloud"
PROXY_INCLUDE="/www/server/panel/vhost/nginx/proxy/219.229.100.24/df2757e2069346b5e29bb639873573ce_219.229.100.24.conf"
BACKEND_SERVICE="/etc/systemd/system/ramancloud-preprocess-backend.service"
HTTP_SECURITY="/www/server/panel/vhost/nginx/00.ramancloud-security.conf"
BROWSER_SECURITY="/www/server/nginx/conf/ramancloud-security-headers.conf"

cd "$APP_DIR"

python3.11 -m venv "$APP_DIR/backend/.venv"
"$APP_DIR/backend/.venv/bin/python" -m pip install -r "$APP_DIR/backend/requirements.txt"

cd "$APP_DIR/frontend"
npm ci
npm run build
sudo mkdir -p "$STATIC_DIR/assets"
sudo cp -a "$APP_DIR/frontend/dist/assets/." "$STATIC_DIR/assets/"
for entry in "$APP_DIR/frontend/dist/"*; do
    case "$(basename "$entry")" in assets|index.html) continue ;; esac
    sudo cp -a "$entry" "$STATIC_DIR/"
done
sudo cp "$APP_DIR/frontend/dist/index.html" "$STATIC_DIR/index.html"

mkdir -p "$APP_DIR/backend/runtime"
if [[ ! -s "$APP_DIR/backend/runtime/session-secret" ]]; then
    (umask 077; openssl rand -hex 32 > "$APP_DIR/backend/runtime/session-secret")
fi
chmod 600 "$APP_DIR/backend/runtime/session-secret"

sudo install -m 0644 "$APP_DIR/deploy/ramancloud-preprocess-backend.service" "$BACKEND_SERVICE"
sudo systemctl daemon-reload
sudo systemctl enable --now ramancloud-preprocess-backend.service
sudo systemctl restart ramancloud-preprocess-backend.service

sudo cp "$PROXY_INCLUDE" "$PROXY_INCLUDE.bak.$(date +%Y%m%d%H%M%S)"
sudo install -m 0644 "$APP_DIR/deploy/nginx-http-security.conf" "$HTTP_SECURITY"
sudo install -m 0644 "$APP_DIR/deploy/nginx-browser-security.conf" "$BROWSER_SECURITY"
sudo install -m 0644 "$APP_DIR/deploy/nginx-preprocessing-proxy.conf" "$PROXY_INCLUDE"
sudo /www/server/nginx/sbin/nginx -t
sudo /www/server/nginx/sbin/nginx -s reload

"$APP_DIR/scripts/healthcheck.sh"
