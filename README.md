# RamanCloud Preprocessing

Repository: `git@github.com:moria5161/RamancloudV2.git`

这是 RamanCloud 的新预处理站点，独立于仍在运行的 `/media/ramancloud` Streamlit 版本。新站点聚焦：

- 单条光谱 cut、denoising、baseline correcting
- 时间序列谱 cut、denoising、baseline correcting
- 高光谱 mapping cut、denoising、baseline correcting
- 用户自定义 pipeline 顺序，添加的步骤按界面中的顺序执行

## 目录

```text
/media/ramancloud_rebuild
├── backend
│   ├── app.py              # FastAPI 后端
│   ├── requirements.txt    # 后端依赖
│   └── samples             # 从原 RamanCloud 复用的示例数据
└── frontend
    ├── src                 # React + Vite + Plotly 前端
    ├── vite.config.js      # 已配置 base=/preprocessing/
    └── dist                # npm run build 产物
```

## 本地运行

后端：

```bash
cd /media/ramancloud_rebuild/backend
pip install -r requirements.txt
python app.py
```

后端地址：`http://127.0.0.1:5000`

前端：

```bash
cd /media/ramancloud_rebuild/frontend
npm install
npm run dev -- --host 0.0.0.0
```

前端地址：

- `http://localhost:5173/preprocessing/`
- `http://219.229.100.24:5173/preprocessing/`

## 已验证

```bash
curl http://127.0.0.1:5000/api/health
curl http://127.0.0.1:5173/api/health
cd /media/ramancloud_rebuild/frontend && npm run build
```

当前验证结果：FastAPI 健康检查正常，Vite 代理正常，前端生产构建成功。

## 处理算法

Denoising：

- `sg`: Savitzky-Golay filter
- `wtd`: Wavelet transform denoising
- `peer`: 本地轻量 PEER-like 平滑保峰实现
- `tsvd`: 批量谱矩阵 TSVD
- `skip`

Baseline correcting：

- `airpls` / `aspls` / `aabs` / `irsqr`: Whittaker/asymmetric least-squares 类本地实现
- `imodpoly` / `penalizedpoly` / `airpls_old`: 多项式基线估计
- `rollingball` / `mormol` / `snip`: rolling-minimum 类基线估计
- `skip`

说明：为了保证当前 Python 3.6 环境能直接运行，新后端没有强制依赖 `pybaselines` 或 `torch`。原页面中的深度学习 F2P/AirNet 可以后续在升级 Python 后作为可选插件式算法加回。

## API

基础路径：`/api`

- `GET /api/health`
- `GET /api/demo/{name}`，`name=bacteria|ulf|tutorial`
- `POST /api/upload`，multipart key: `files`
- `GET /api/demo-hyperspectral/{name}`，支持 `timeseries_horiba`、`timeseries_nanophoton`、`imaging_horiba`、`imaging_nanophoton`
- `POST /api/upload-hyperspectral`，multipart key: `file`，form: `instrument`、`mode`
- `POST /api/process`
- `POST /api/process-hyperspectral`
- `POST /api/download`

Pipeline 示例：

```json
{
  "wavenumber": [400, 401, 402],
  "intensity": [12, 15, 13],
  "steps": [
    { "type": "denoise", "method": "sg", "params": { "window_size": 7, "order": 3 } },
    { "type": "cut", "method": "cut", "params": { "start": 500, "end": 1800 } },
    { "type": "baseline", "method": "airpls", "params": { "lam": 1000000, "diff_order": 2 } }
  ]
}
```

## 生产部署到 `/preprocessing`

构建前端：

```bash
cd /media/ramancloud_rebuild/frontend
npm run build
```

建议用 systemd 管理后端：

```ini
[Unit]
Description=RamanCloud Preprocessing FastAPI
After=network.target

[Service]
Type=simple
User=room
WorkingDirectory=/media/ramancloud_rebuild/backend
ExecStart=/home/room/intel/intelpython3/bin/python /media/ramancloud_rebuild/backend/app.py
Restart=always

[Install]
WantedBy=multi-user.target
```

Nginx 反向代理示例：

```nginx
location /preprocessing/api/ {
    proxy_pass http://127.0.0.1:5000/api/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_read_timeout 600s;
}

location /preprocessing/ {
    alias /media/ramancloud_rebuild/frontend/dist/;
    try_files $uri $uri/ /preprocessing/index.html;
}
```

旧站点 `https://ramancloud.xmu.edu.cn/` 不需要改变；只新增 `/preprocessing/` 路由即可。
