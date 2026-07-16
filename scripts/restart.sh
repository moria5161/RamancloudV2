#!/usr/bin/env bash
set -euo pipefail

sudo systemctl restart ramancloud-preprocess-backend.service
sudo /www/server/nginx/sbin/nginx -t
sudo /www/server/nginx/sbin/nginx -s reload

/media/ramancloud_rebuild/scripts/healthcheck.sh
