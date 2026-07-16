#!/usr/bin/env bash
set -euo pipefail

curl -fsS http://127.0.0.1:5000/api/health >/dev/null
curl -fsSk https://ramancloud.xmu.edu.cn/preprocessing/api/health >/dev/null
curl -fsSk https://ramancloud.xmu.edu.cn/preprocessing/ >/dev/null

echo "RamanCloud V2 preprocessing is healthy."
