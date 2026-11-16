#!/usr/bin/env bash
set -euo pipefail

curl -fsS http://127.0.0.1:5000/api/health >/dev/null
curl -fsS https://ramancloud.xmu.edu.cn/ramancloud-api/health >/dev/null
curl -fsS https://ramancloud.xmu.edu.cn/ >/dev/null

echo "RamanCloud is healthy."
