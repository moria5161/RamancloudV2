#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/media/ramancloud_rebuild"
STATIC_DIR="/www/wwwroot/219.229.100.24/preprocessing"
PROXY_INCLUDE="/www/server/panel/vhost/nginx/proxy/219.229.100.24/df2757e2069346b5e29bb639873573ce_219.229.100.24.conf"
BACKEND_SERVICE="/etc/systemd/system/ramancloud-preprocess-backend.service"

cd "$APP_DIR"

git pull --ff-only

cd "$APP_DIR/frontend"
npm ci
npm run build
sudo rm -rf "$STATIC_DIR"
sudo mkdir -p "$STATIC_DIR"
sudo cp -a "$APP_DIR/frontend/dist/." "$STATIC_DIR/"
sudo chown -R www:www "$STATIC_DIR"

sudo install -m 0644 "$APP_DIR/deploy/ramancloud-preprocess-backend.service" "$BACKEND_SERVICE"
sudo systemctl daemon-reload
sudo systemctl enable --now ramancloud-preprocess-backend.service
sudo systemctl restart ramancloud-preprocess-backend.service

sudo cp "$PROXY_INCLUDE" "$PROXY_INCLUDE.bak.$(date +%Y%m%d%H%M%S)"
sudo install -m 0644 "$APP_DIR/deploy/nginx-preprocessing-proxy.conf" "$PROXY_INCLUDE"
sudo /www/server/nginx/sbin/nginx -t
sudo /www/server/nginx/sbin/nginx -s reload

"$APP_DIR/scripts/healthcheck.sh"
