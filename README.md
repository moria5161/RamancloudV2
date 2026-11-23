# RamanCloud Preprocessing

2026-11-17：智能光谱和高光谱统一沿用原项目去噪、基线算法与参数，不并列旧版标识，高光谱保留TSHI。F2P与AirNet已接通真实权重。安装和剩余遗漏项见 [算法核查](LEGACY_ALGORITHM_AUDIT.md)。

服务器测试版使用此仓库的 `alpha` 分支。[Alpha 部署与模型准备](DEPLOYMENT.md)

2026-11-19：新增独立“分峰拟合”模块，位于高光谱处理下方。支持已校正基线的上传光谱及已完成处理版本，手动设置多峰初值、约束和峰形，查看总拟合/分峰/残差，自动保存分析记录并导出参数、曲线、PNG和完整ZIP；中英文与深浅模式同步。无新依赖，重启后端自动建表，生产前端重新构建。见 [分峰拟合说明](PEAK_FITTING.md)。

2026-11-15：首次访问默认英文；登录后语言选择按账号保存在数据库，刷新、重新登录或更换浏览器后恢复，访客选择保存在当前浏览器。补齐助手界面、分析记录、图表、导入警告、参数与导出窗口的英文。AI 回答和用户输入保持原文；物质库没有核验英文名的条目在英文界面使用原类别编号，中文原名和模型映射保留。无新依赖，重启后端自动建立 `user_preferences` 表，生产前端重新构建。

2026-11-15：首页与教程已同步当前流程，补齐原生 L6M / NPG / WXD、四项附加工具、批量记录与导出，以及“发送目标并完成回答 → 生成运行方案 → 一键运行”。移除旧截图教程和手动保存说法；普通用户可在常见问题提交反馈，管理员从反馈管理处理。仅前端内容与文档更新，无新增依赖；开发前端刷新，生产前端重新构建。

2026-11-11：右侧助手新增跨模块“讨论目标 → 生成运行方案 → 检查参数 → 一键运行”，复用已有处理和模型接口，支持组合流程、进度、结果入口与文件下载。无新依赖，重启后端自动建表；生产前端重新构建。使用与限制见 [QA_ACTIONS.md](QA_ACTIONS.md)。

统一分析记录、导出共享、仪器原生格式、去鬼峰窄峰保护和 AI 问答的变更见 [更新日志](CHANGELOG.md)。

六个分析工作区独立管理输入，切换页面保留当前分析。处理完成后自动进入“分析记录”，未完成任务和批次也从这里继续；单光谱记录按单个/批量、已处理/未处理筛选，支持批量导出与删除。需要团队访问时“共享到项目”。使用与升级见 [统一记录流程](RECORDS_WORKFLOW.md)。

登录后电脑端助手常驻右侧，手机端点击“AI 问答”展开。可结合当前任务、记录或单谱附件提问，支持流式显示、停止、复制和方案执行。新版使用结构化数据替代截图按钮，沿用现有模型。使用及数据范围见 [QA_ASSISTANT.md](QA_ASSISTANT.md)。

## 分析历史与项目仓库改造（2026-10-30）

分析历史改为结果图、处理步骤与文件下载；项目页分为原始数据仓库、处理后数据仓库及活动。支持项目文件预览、单个/批量处理、标准化导出、分析结果入库和权限检查。新增 PDF 报告与图像导出依赖，更新后安装 `backend/requirements.txt` 并重启后端。使用方式、存储与旧记录限制见 [HISTORY_WAREHOUSE.md](HISTORY_WAREHOUSE.md)。

## 三项算法功能集成（2026-10-29）

新增混合物解析（SSnet 定向提取）、库匹配（PeakNet/AirNet）、结构生成（Vib2Mol + 可选 Agent），原预处理结果可携带保存版本进入三个页面。

部署时按 [模型准备说明](DEPLOYMENT.md#ai-and-algorithm-models) 安装各算法的运行环境。组内模型包和权重从服务器的私有目录配置。SSnet 标准品模型须用实验标准谱训练。

- [版本新增内容与边界](CHANGELOG.md)
- [服务器配置、安装和验证](DEPLOYMENT.md)
- [混合物解析使用说明](MIXTURE_ANALYSIS.md)、[库匹配使用说明](LIBRARY_MATCHING.md)、[结构生成使用说明](STRUCTURE_GENERATION.md)

站内首页 `/preprocessing/` 提供分析模块、记录、项目、附加工具和 AI 教程入口；教程 `/preprocessing/tutorial` 覆盖格式转换确认、单个与批量预处理、三项模型分析、高光谱、附加工具、记录导出、项目共享和 AI 方案执行。首页的“操作教程”可直接跳转到对应章节。模型是否安装以各功能页面的实际状态为准。

首页已加入原始 V2 收录的课题组论文；教程常见问题末尾可提交用户反馈。用户从“我的反馈”查看状态和回复，系统管理员从“反馈管理”集中处理。更新后重启后端自动建表，生产前端需重新构建，无新增依赖。使用与维护见 [反馈与论文区说明](FEEDBACK.md)。

本项目基于 RamancloudV2 改进，原始源码仓库：
https://github.com/moria5161/RamancloudV2

这是 RamanCloud 的新预处理站点，独立于仍在运行的 `/media/ramancloud` Streamlit 版本。新站点聚焦：

- 单条光谱 cut、denoising、baseline correcting
- 时间序列谱 cut、denoising、baseline correcting
- 高光谱 mapping cut、denoising、baseline correcting
- 高光谱支持自定义 pipeline；智能单谱按去鬼峰、降噪、基线校正设置，可分别跳过

混合物解析已接入 SSnet 本地实验版，支持标准品建模、后台训练与停止、模型复用、混合谱提取及任务导出。详见 [MIXTURE_ANALYSIS.md](MIXTURE_ANALYSIS.md)。

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

当前主后端已在 Python 3.9、Node.js 24 环境验证，依赖以 `backend/requirements.txt` 为准。
三个模型使用独立环境，首次安装按各模型安装说明执行；已能运行上一版的环境无需因本次更新更换 Python 或重下模型。

先下载源码：

```bash
git clone https://github.com/hzh040518/Ramancloud.git
cd Ramancloud
```

Windows 用户安装 Python 和 Node.js/npm 后，可以双击仓库根目录的
`run_project.bat`。该脚本安装依赖并启动前后端；也可以在 VS Code 中打开
仓库文件夹，运行任务 `RamanCloud: Run All`。

如需手动启动，在仓库根目录分别打开两个终端，执行下面的后端和前端命令。
无需复制他人的数据库；首次启动会自动创建表，随后注册自己的平台账号。

默认不配置数据库环境变量时，后端会使用本地 SQLite：

```text
backend/data/ramancloud.db
```

后端：

```bash
cd backend
python -m pip install -r requirements.txt
python app.py
```

后端地址：`http://127.0.0.1:5000`

前端：

```bash
cd frontend
npm ci
npm run dev -- --host 0.0.0.0
```

前端地址：

- `http://localhost:5173/preprocessing/`

GitHub 仓库只发布源码，不会自动部署在线网站。公网部署请配置服务器、
MySQL 和文件存储；`DEPLOYMENT.md` 中的域名和绝对路径是原平台的部署示例，
不是此仓库已经部署成功的说明。

真实 AI 密钥、数据库、用户上传文件和运行日志不会随源码发布。
`backend/ai_config.example.json` 和 `backend/.env.mysql.example` 是公开配置模板；
没有 AI 密钥时仍可使用明确标注的本地规则推荐。

## 协作与更新代码

已经通过 `git clone` 获取项目的同学，在项目根目录更新：

```bash
git status
git switch main
git pull --ff-only origin main
```

先提交或暂存自己尚未完成的改动，再拉取代码。若提示分支已分叉，需先合并双方的提交，
不要使用强制推送或清空本地改动。通过 ZIP 下载的目录需要先连接 Git 历史；新电脑建议直接使用上方的 `git clone`。

更新后重启后端并刷新前端；若依赖文件有变化，重新执行 `python -m pip install -r backend/requirements.txt`，
并在 `frontend` 目录执行 `npm ci`。各自的 Python 环境、数据库、上传文件和私有配置保存在本机，
不通过 Git 同步。

## 单光谱格式识别与转换

新增已验证结构的 **Renishaw WXD 单谱**导入：预览并确认后转换为标准双列，原 WXD 与标准 TXT 可分别下载。
已核对所提供的 17 个 WXD 和其中 10 组配套 TXT；仅支持该批保存结构，暂不支持 WXD 成像、序列及其他版本。
无需新增依赖；使用与范围见 [仪器格式说明](INSTRUMENT_FORMATS.md#renishaw-wxd-单谱导入2026-10-31)。

智能光谱分析已支持本仓库“光谱”目录内的教学型 EduRaman Pro 和海洋光学 USB2000 导出样例。双列光谱直接导入；多列仪器导出先预览所选拉曼位移、强度列，用户确认后转换。保留全部原始点数和数值，导入后可分别下载原始文件和标准双列 TXT。单个及批量上传均支持；详细规则见 [INSTRUMENT_FORMATS.md](INSTRUMENT_FORMATS.md)。

## 库匹配

库匹配已接入提供的 PeakNet 2805 类模型，支持上传或选择已保存预处理结果、AirNet＋PEER 可选处理、Top 3/5/10、参考缓存曲线叠加、导出和分析历史。
输入需覆盖 220–1800 cm⁻¹，模型使用 750 点。得分为固定类别集的模型排序分数，不是鉴定概率；其他仪器和库外样本需要独立验证。
安装及使用见 [库匹配说明](LIBRARY_MATCHING.md)。

## 结构生成

结构生成已接入官方 Vib2Mol Raman 模型，支持上传或使用已保存预处理版本、真实候选生成、匹配重排、二维结构、SMILES、JSON/CSV/SDF 导出及分析历史。
当前模型要求完整覆盖 400–4000 cm⁻¹，适配为 1024 点；分子式可选，仅用于生成后筛选。
两份官方权重共约 1.26 GB，使用独立环境；安装、启动、输入限制和微调模型替换见 [结构生成说明](STRUCTURE_GENERATION.md)。
可选安装 `vib2mol_agent.zip`，在页面切换“Agent 知识增强（实验）”，查看知识检索资料与候选辅助排序。该扩展包未包含新权重，目前使用官方模型及本地规则，不调用外部大语言模型。

## 高光谱 TSHI

上传已接入统一的内容识别与校验，默认自动识别常见文本结构、MAT、XLSX、
单谱 JCAMP-DX 和受支持的 Renishaw WDF。具体结构、限制、嘉庚实验室设备调研和
待验收范围见 [INSTRUMENT_FORMATS.md](INSTRUMENT_FORMATS.md)，不代表所有品牌原始格式均可直接读取。

高光谱工作区支持 MAT（`cube`、`x`）上传及 TSHI / IIALRMA 去噪。
可调整中心波数、波段范围和平滑区域/SVD 参数，查看中心成像与诊断，
下载含尺寸信息的 MAT 结果。BM3D 为默认关闭的可选依赖，仅限非商业用途。
数据布局、使用流程、参数与限制见 [TSHI.md](TSHI.md)。

## AI 对话

文件工具页保留 AI 对话，用于格式转换等问答；高光谱工作区只保留处理控制面板，
不再提供 AI 对话入口。「智能光谱处理」继续提供单条和批量光谱的目标驱动流程。

默认使用本机 Ollama `qwen3:4b-instruct-2507-q4_K_M`，与智能光谱处理共用配置，不需要 API 密钥。先安装 Ollama 并执行 `ollama pull qwen3:4b-instruct-2507-q4_K_M`；未授权模型读取摘要时使用明确标注的本地规则。
可以为对话单独选择 Ollama。对话按账号和数据源保存到后端数据库，
不会共用不同用户的浏览器会话。配置、来源与限制见 [AI_CHAT.md](AI_CHAT.md)。

## MySQL 数据库配置

如果要让项目以在线网站形式部署，建议使用 MySQL 保存用户、项目、数据文件索引、分析历史和版本记录。后端会根据环境变量自动选择数据库：

- 未配置 MySQL：使用本地 SQLite，适合本机演示
- 配置 `DATABASE_URL` 或 `MYSQL_HOST`：使用 MySQL，适合公网部署

推荐使用 `DATABASE_URL`：

```bash
DATABASE_URL="mysql+pymysql://ramancloud_user:数据库密码@数据库地址:3306/ramancloud?charset=utf8mb4"
python app.py
```

也可以拆成多个环境变量：

```bash
MYSQL_HOST=127.0.0.1
MYSQL_PORT=3306
MYSQL_USER=ramancloud_user
MYSQL_PASSWORD=数据库密码
MYSQL_DATABASE=ramancloud
MYSQL_CHARSET=utf8mb4
python app.py
```

MySQL 数据库需要先创建，表结构会在后端启动时自动初始化：

```sql
CREATE DATABASE ramancloud CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'ramancloud_user'@'%' IDENTIFIED BY '数据库密码';
GRANT ALL PRIVILEGES ON ramancloud.* TO 'ramancloud_user'@'%';
FLUSH PRIVILEGES;
```

可以访问健康检查确认当前数据库类型：

```bash
curl http://127.0.0.1:5000/api/health
```

返回中的 `data.database` 为 `mysql` 时，说明后端正在使用 MySQL；`data.storage` 为 `s3` 时，说明上传文件正在使用对象存储。

## 上传文件存储配置

数据库保存的是文件索引和元数据，上传的光谱文件默认仍保存在后端本地目录：

```text
backend/data/stored_files
```

生产部署时可以把文件存储目录改到服务器挂载盘或共享存储：

```bash
RAMANCLOUD_STORAGE_DIR="/data/ramancloud_uploads"
python app.py
```

如果要让公网用户上传的数据不依赖某台服务器本地硬盘，可以启用 S3 兼容对象存储。支持 AWS S3、Cloudflare R2、MinIO 以及兼容 S3 API 的云存储服务：

```bash
RAMANCLOUD_STORAGE_BACKEND=s3
RAMANCLOUD_S3_BUCKET=ramancloud-uploads
RAMANCLOUD_S3_PREFIX=ramancloud/uploads
RAMANCLOUD_S3_REGION=ap-east-1
RAMANCLOUD_S3_ENDPOINT_URL=https://example-account-id.r2.cloudflarestorage.com
RAMANCLOUD_S3_ACCESS_KEY_ID=对象存储AccessKey
RAMANCLOUD_S3_SECRET_ACCESS_KEY=对象存储SecretKey
python app.py
```

使用 AWS S3 时可以不配置 `RAMANCLOUD_S3_ENDPOINT_URL`。使用 Cloudflare R2、MinIO 或其他 S3 兼容服务时，需要填写服务商提供的 endpoint。

启用 S3 后，新上传文件会保存到对象存储，数据库中的 `data_assets.storage_path` 会保存为：

```text
s3://bucket-name/ramancloud/uploads/项目ID/文件ID_文件名
```

旧的本地文件路径仍然兼容，可以继续下载和删除。

## 用户管理

平台已加入基础用户管理模块：

- 支持注册、登录、退出登录和修改密码
- 注册仅创建普通用户，不能自行注册为系统管理员
- 系统管理员可以在「个人空间」中查看用户列表、调整系统角色、启用或停用账号
- 用户数据默认保存在 `backend/data/ramancloud.db`；配置 MySQL 后会保存到 MySQL

系统角色为普通用户、系统管理员；项目内另设项目管理员、项目成员，两者独立。已有管理员账号保留；全新部署可在后端目录运行 `python bootstrap_admin.py`，交互式创建首位系统管理员。协作使用、权限及迁移说明见 [PROJECT_COLLABORATION.md](PROJECT_COLLABORATION.md)。

## 项目和数据管理

平台已加入项目和数据管理模块：

- 支持创建项目，将同一实验的数据放在同一个项目中
- 支持把上传文件保存到项目，后续无需重新上传
- 支持数据重命名、删除、下载、搜索和分类
- 支持区分原始数据和处理后的数据
- 项目创建者自动成为所有者和项目管理员，可邀请已注册用户加入项目
- 项目邀请支持接受、拒绝、撤销和七天有效期；成员加入前无法访问项目
- 项目管理员可管理成员与项目资料，所有者可转让项目；系统管理员身份不自动授予项目数据访问权
- 项目成员共享项目文件，处理任务保持个人私有；已保存结果经作者确认“保存到处理后仓库”后才向项目成员开放
- 项目内可查看最近活动；成员退出或被移除后，不能继续访问该项目的数据、结果和任务
- 暂不提供回收站：仅上传者可删除自己未被分析引用的数据，仅所有者可删除空项目；入库结果须从仓库移除后才能由作者删除历史

数据文件默认保存在 `backend/data/stored_files`，也可以通过 `RAMANCLOUD_STORAGE_DIR` 改到挂载盘或共享存储，或通过 `RAMANCLOUD_STORAGE_BACKEND=s3` 保存到对象存储。项目和数据索引默认保存在 `backend/data/ramancloud.db`；配置 MySQL 后，项目和数据索引会保存到 MySQL。

## 分析历史和结果保存

平台已加入分析历史和结果保存模块：

- 运行单光谱或高光谱处理流程后，会自动保存分析历史
- 历史记录保存处理方法、参数、运行结果摘要和版本信息
- 支持原始版本、处理版本和结果版本标记
- 单光谱历史支持结果下载和一键复现
- 历史记录支持读取参数并回填到处理页面重新运行

## 已验证

```bash
curl http://127.0.0.1:5000/api/health
curl http://127.0.0.1:5173/api/health
cd /media/ramancloud_rebuild/frontend && npm run build
```

当前验证结果：FastAPI 健康检查正常，Vite 代理正常，前端生产构建成功。

## 处理算法

去鬼峰（`despike`）已接入用户指定的 Raman_Preprocessing 核心算法。新建默认预处理按“裁剪 → 去鬼峰 → 降噪 → 基线校正”执行；去鬼峰不需要选择算法，可启用或跳过，支持高级阈值设置、候选位置标记、前后曲线对比和批量处理。原始文件保留，算法来源和边界见 [backend/preprocessing/README.md](backend/preprocessing/README.md)。

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

智能预处理目前使用上述轻量数值实现，尚未接入 F2P 或 AirNet 深度模型。库匹配中的 PEER/AirNet 通过独立模型环境运行，不能与智能预处理中的兼容算法名称混淆。实际实现与边界见 [PREPROCESSING_ALGORITHMS.md](PREPROCESSING_ALGORITHMS.md)。

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

## 智能光谱处理

上传支持“单个数据（文件）/ 批量数据（文件夹，含子文件夹）”。批量模式可将当前方案应用到勾选光谱，逐项显示进度、独立记录结果和版本，支持停止待执行项及下载批量结果 ZIP。单个文件不兼容或失败不影响其他文件。每批上限 100 个文件、40 MB，单个文件上限 4 MB。任务与批次从“分析记录”重新打开，运行中的任务不能删除。

智能光谱处理采用“上传数据 → 光谱处理 → 查看结果”。完成后自动记录，结果区提供继续调整、统一导出和项目共享；调整先预览，再应用修改生成新版本。波段、参数和候选比较按需展开，旧版本保留，只复用有效且未变化的连续前缀。候选评分为启发式辅助，不能保证科学最优。Ollama、DeepSeek 和硅基流动沿用原有配置，模型不可用时明确使用本地规则推荐，不会转用收费模型。处理结果可携带所选完成版本进入混合物解析、库匹配和结构生成。详细配置、权限和边界见 [AI_WORKFLOW.md](AI_WORKFLOW.md)。

登录页：`/preprocessing/login`，注册页：`/preprocessing/register`。已登录用户可从侧栏“切换账号”返回登录界面。
