#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Please run as root: sudo bash /media/ramancloud_rebuild/fix_preprocessing_nginx.sh" >&2
  exit 1
fi

SITE_CONF="/www/server/panel/vhost/nginx/219.229.100.24.conf"
PROXY_DIR="/www/server/panel/vhost/nginx/proxy/219.229.100.24"
NGINX_BIN="/www/server/nginx/sbin/nginx"

echo "== Listening processes =="
ss -ltnp | grep -E ':(80|443|5000|5173|8501)\b' || true

echo
echo "== Direct service checks =="
curl --noproxy '*' --max-time 5 -s http://127.0.0.1:5000/api/health | head -c 160 || true
echo
curl --noproxy '*' --max-time 5 -s http://127.0.0.1:5173/preprocessing/api/health | head -c 160 || true
echo

if [[ ! -f "${SITE_CONF}" ]]; then
  echo "Site config not found: ${SITE_CONF}" >&2
  exit 1
fi

backup="${SITE_CONF}.bak.$(date +%Y%m%d%H%M%S)"
cp -a "${SITE_CONF}" "${backup}"
echo "Backed up ${SITE_CONF} -> ${backup}"

python3 - <<'PY'
from pathlib import Path

path = Path("/www/server/panel/vhost/nginx/219.229.100.24.conf")
text = path.read_text()

block = r'''
    # ===== RamanCloud preprocessing platform =====
    location = /preprocessing {
        return 301 /preprocessing/;
    }

    location ^~ /preprocessing/api/ {
        proxy_pass http://127.0.0.1:5000/api/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 600s;
    }

    location ^~ /preprocessing/ {
        proxy_pass http://127.0.0.1:5173/preprocessing/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

'''

start = text.find("    # ===== RamanCloud preprocessing platform =====")
if start != -1:
    next_marker = text.find("\n\t\t#CERT-APPLY-CHECK--START", start)
    if next_marker == -1:
        next_marker = text.find("\n    #CERT-APPLY-CHECK--START", start)
    if next_marker == -1:
        next_marker = text.find("\n\t#引用重定向规则", start)
    if next_marker == -1:
        raise SystemExit("Could not locate insertion boundary after existing preprocessing block.")
    text = text[:start] + block + text[next_marker + 1:]
else:
    markers = [
        "include /www/server/panel/vhost/nginx/proxy/219.229.100.24/*.conf;",
        "#CERT-APPLY-CHECK--START",
        "#SSL-START",
    ]
    inserted = False
    for marker in markers:
        idx = text.find(marker)
        if idx != -1:
            line_start = text.rfind("\n", 0, idx) + 1
            text = text[:line_start] + block + text[line_start:]
            inserted = True
            break
    if not inserted:
        raise SystemExit("Could not find a safe insertion point.")

path.write_text(text)
PY

echo
echo "== Relevant live config after patch =="
"${NGINX_BIN}" -T 2>&1 | grep -nE 'RamanCloud preprocessing|preprocessing|proxy_pass http://127.0.0.1:(5000|5173)|proxy_pass http://.*8501' || true

echo
echo "== Testing nginx config =="
"${NGINX_BIN}" -t

echo
echo "== Reloading nginx =="
"${NGINX_BIN}" -s reload

sleep 1

echo
echo "== Public checks =="
curl --noproxy '*' --max-time 10 -k -s -D - https://ramancloud.xmu.edu.cn/preprocessing/api/health -o /tmp/raman_preprocessing_health.txt | sed -n '1,40p'
echo "--- body ---"
head -c 500 /tmp/raman_preprocessing_health.txt
echo

curl --noproxy '*' --max-time 10 -k -s -D - https://ramancloud.xmu.edu.cn/preprocessing/ -o /tmp/raman_preprocessing_page.html | sed -n '1,40p'
echo "--- page head ---"
head -c 300 /tmp/raman_preprocessing_page.html
echo
