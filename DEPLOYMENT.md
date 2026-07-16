# RamanCloud V2 Deployment

RamanCloud V2 is deployed at:

```text
https://ramancloud.xmu.edu.cn/preprocessing/
```

The legacy Streamlit RamanCloud remains at:

```text
https://ramancloud.xmu.edu.cn/
```

## Runtime Model

- Nginx serves the built React frontend from `/www/wwwroot/219.229.100.24/preprocessing/`.
- `scripts/deploy.sh` builds `frontend/dist` and publishes it to that Nginx-readable directory.
- FastAPI runs as a systemd service on `127.0.0.1:5000`.
- The old Streamlit service remains managed by the existing `ramancloud.service` on port `8501`.

## System Files

Backend service:

```text
/etc/systemd/system/ramancloud-preprocess-backend.service
```

Nginx include installed from this repo:

```text
/media/ramancloud_rebuild/deploy/nginx-preprocessing-proxy.conf
```

Installed to the current BaoTa/Nginx include path:

```text
/www/server/panel/vhost/nginx/proxy/219.229.100.24/df2757e2069346b5e29bb639873573ce_219.229.100.24.conf
```

## Deploy

```bash
cd /media/ramancloud_rebuild
./scripts/deploy.sh
```

## Restart

```bash
cd /media/ramancloud_rebuild
./scripts/restart.sh
```

## Health Check

```bash
cd /media/ramancloud_rebuild
./scripts/healthcheck.sh
```

## Logs

Backend:

```bash
journalctl -u ramancloud-preprocess-backend.service -f
```

Nginx:

```bash
tail -f /www/wwwlogs/219.229.100.24.error.log
```
