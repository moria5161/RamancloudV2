# RamanCloud V2

RamanCloud 是面向拉曼光谱的在线分析平台，集成光谱预处理、高光谱处理、分峰拟合、混合物解析、库匹配和光谱到结构。

优化版源码位于 `alpha` 分支。在线站点使用 `/rc/`，登录后可从侧栏进入各工作区与教程。首次访问默认英文，登录后按账号记住语言选择。

[打开 RamanCloud](https://ramancloud.xmu.edu.cn/rc/) · [在线教程](https://ramancloud.xmu.edu.cn/rc/tutorial) · [更新记录](CHANGELOG.md) · [部署说明](DEPLOYMENT.md)

## 功能与使用说明

| 工作区 | 可完成的工作 |
| --- | --- |
| [智能光谱处理](AI_WORKFLOW.md) | 导入单光谱或文件夹，设置波段，执行去鬼峰、降噪和基线校正，预览并保存处理版本 |
| [高光谱处理](TSHI.md) | 分析成像或时间序列数据，查看成像、平均光谱和单像素光谱，配置处理流程 |
| [分峰拟合](PEAK_FITTING.md) | 对已校正基线的单谱设置多峰初值和约束，检查总拟合、各分峰与残差 |
| [混合物解析](MIXTURE_ANALYSIS.md) | 从标准谱训练 SSnet 模型，复用已完成的模型从混合谱中提取目标信号 |
| [库匹配](LIBRARY_MATCHING.md) | 使用 PeakNet 对固定物质库排序，对比参考光谱 |
| [光谱到结构](STRUCTURE_GENERATION.md) | 使用 Vib2Mol 从拉曼光谱生成候选分子结构，查看和导出候选 |

分析记录汇总各工作区的任务、结果、算法和参数。已完成的分析可从记录重新打开，按模块查看输入与结果图表，并导出或共享至项目。[分析记录与共享](RECORDS_WORKFLOW.md) · [项目数据仓库](HISTORY_WAREHOUSE.md) · [项目权限](PROJECT_COLLABORATION.md)

首页提供各工作区入口与组内论文。教程涵盖仪器文件格式、分析操作、附加工具及常见问题，并提供用户反馈入口。[仪器格式](INSTRUMENT_FORMATS.md) · [反馈说明](FEEDBACK.md)

## 目录

```text
RamancloudV2/
├── backend
│   ├── app.py              # FastAPI 后端
│   ├── requirements.txt    # 后端依赖
│   └── samples             # 从原 RamanCloud 复用的示例数据
└── frontend
    ├── src                 # React + Vite + Plotly 前端
    ├── vite.config.js      # 本地开发默认使用 /preprocessing/
    └── dist                # npm run build 产物
```

## 本地运行

前端使用 Node.js 24。手动安装后端可使用 Python 3.11，依赖见 `backend/requirements.txt`。各模型的运行环境和权重按 [模型准备说明](DEPLOYMENT.md#ai-and-algorithm-models) 安装。

先下载源码：

```bash
git clone --branch alpha https://github.com/moria5161/RamancloudV2.git
cd RamancloudV2
```

Windows 用户可以双击仓库根目录的 `run_project.bat` 安装依赖并启动前后端。该脚本选择 Python 3.8–3.10。如果使用 Python 3.11，按下文手动启动。

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

本地前端地址为 `http://localhost:5173/preprocessing/`。生产构建和上线配置见 [服务器部署](DEPLOYMENT.md)。

## 协作与更新代码

已经通过 `git clone` 获取项目的同学，在项目根目录更新：

```bash
git status
git switch alpha
git pull --ff-only origin alpha
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

## 光谱到结构

光谱到结构使用官方 Vib2Mol Raman 模型，支持上传或使用已保存预处理版本、真实候选生成、匹配重排、二维结构、SMILES、JSON/CSV/SDF 导出及分析历史。
当前模型要求完整覆盖 400–4000 cm⁻¹，适配为 1024 点；分子式可选，仅用于生成后筛选。
两份官方权重共约 1.26 GB，使用独立环境。[光谱到结构的安装与输入要求](STRUCTURE_GENERATION.md)
可选安装 `vib2mol_agent.zip`，在页面切换“Agent 知识增强（实验）”，查看知识检索资料与候选辅助排序。该扩展包未包含新权重，目前使用官方模型及本地规则，不调用外部大语言模型。

## 高光谱 TSHI

上传已接入统一的内容识别与校验，默认自动识别常见文本结构、MAT、XLSX、
单谱 JCAMP-DX 和受支持的 Renishaw WDF。具体结构、限制、嘉庚实验室设备调研和
待验收范围见 [INSTRUMENT_FORMATS.md](INSTRUMENT_FORMATS.md)，不代表所有品牌原始格式均可直接读取。

高光谱工作区支持 MAT（`cube`、`x`）上传及 TSHI / IIALRMA 去噪。
可调整中心波数、波段范围和平滑区域/SVD 参数，查看中心成像与诊断，
下载含尺寸信息的 MAT 结果。BM3D 为默认关闭的可选依赖，仅限非商业用途。
数据布局、使用流程、参数与限制见 [TSHI.md](TSHI.md)。

## AI 问答与预处理

六个分析工作区提供 AI 助手。点击“发送”可询问页面操作、当前结果和光谱知识。在智能光谱处理页，选择工作区光谱或上传助手附件，填写要求后点击“生成预处理方案”，即可直接查看和调整算法与参数，再确认运行。

“一键预处理”按顺序使用 despike 去鬼峰、F2P 降噪和 AirNet 基线校正。其他分析工作区通过本页的操作控件导入数据并运行，右侧助手用于问答。右侧聊天保留在当前会话，处理结果保存至分析记录。[AI 助手说明](QA_ASSISTANT.md) · [方案使用说明](QA_ACTIONS.md)

Ollama 运行在后端所在机器，模型可按环境配置。自主部署时可安装模型或配置兼容服务，预处理推荐也可选用本地规则。[模型配置](DEPLOYMENT.md#ai-and-algorithm-models)

## 数据库与文件存储

线上优化版使用 MySQL 保存账号、项目、文件索引、分析记录和反馈。上传文件与部分分析产物由后端文件存储管理。本地开发时，未配置 MySQL 的后端使用 SQLite。

自建部署请先创建专用数据库，再按公开模板在服务端配置应用账号，启动时后端初始化表结构。数据库和模型凭据保存在服务端的私有配置中。[MySQL 配置模板](backend/.env.mysql.example) · [数据与管理员配置](DEPLOYMENT.md#data-and-administrative-accounts)

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

## 本地检查

启动前后端后，可检查后端和 Vite 代理的健康接口。响应中 `data.database` 表示当前使用的数据库类型。

```bash
curl http://127.0.0.1:5000/api/health
curl http://127.0.0.1:5173/api/health
cd frontend
npm run build
```

## 处理算法

去鬼峰（`despike`）已接入用户指定的 Raman_Preprocessing 核心算法。新建默认预处理按“裁剪 → 去鬼峰 → 降噪 → 基线校正”执行；去鬼峰不需要选择算法，可启用或跳过，支持高级阈值设置、候选位置标记、前后曲线对比和批量处理。原始文件保留，算法来源和边界见 [backend/preprocessing/README.md](backend/preprocessing/README.md)。

- 降噪方法包括 Savitzky–Golay、WTD、PEER 和 F2P。多谱还可使用 TSVD，高光谱成像支持 TSHI/IIALRMA。
- 基线校正方法包括 AirNet、AirPLS、AABS、IModPoly 和 SNIP。

F2P 与 AirNet 需要相应模型权重，以功能页面显示的可用状态为准。[算法目录与模型说明](LEGACY_ALGORITHM_AUDIT.md)

## API

下列路径使用本地后端的 `/api` 前缀。线上网关的前缀为 `/rc/ramancloud-api`，例如 [线上健康检查](https://ramancloud.xmu.edu.cn/rc/ramancloud-api/health)。

- `GET /api/health`
- `GET /api/demo/{name}`，`name=bacteria|ulf|tutorial`
- `POST /api/upload`，multipart key: `files`
- `GET /api/demo-hyperspectral/{name}`，支持 `timeseries_horiba`、`timeseries_nanophoton`、`imaging_horiba`、`imaging_nanophoton`
- `POST /api/upload-hyperspectral`，multipart key: `file`，form: `instrument`、`mode`
- `POST /api/process`
- `POST /api/process-hyperspectral`
- `POST /api/download`

本地 `POST /api/process` 请求体示例：

```json
{
  "wavenumber": [400, 401, 402, 403, 404, 405, 406, 407],
  "intensity": [12, 15, 13, 14, 16, 15, 14, 13],
  "steps": [
    { "type": "denoise", "method": "sg", "params": { "window_size": 7, "order": 3 } }
  ]
}
```

## 生产部署

线上前端按 `/rc/` 构建，API 通过同域的 `/rc/ramancloud-api/` 转发。前端构建、路由配置与上线检查见 [部署说明](DEPLOYMENT.md#publish-the-frontend-at-rc)。

## 智能光谱处理

上传支持“单个数据（文件）/ 批量数据（文件夹，含子文件夹）”。批量模式可将当前方案应用到勾选光谱，逐项显示进度、独立记录结果和版本，支持停止待执行项及下载批量结果 ZIP。单个文件不兼容或失败不影响其他文件。应用侧每批上限 100 个文件、40 MB，单个文件上限 4 MB。任务与批次从“分析记录”重新打开，运行中的任务不能删除。

智能光谱处理采用“上传数据 → 光谱处理 → 查看结果”。完成后自动记录，结果区提供继续调整、导出和项目共享。预览并应用修改可生成新版本，也可将已完成的版本带入分峰拟合、混合物解析、库匹配或光谱到结构。[操作说明](AI_WORKFLOW.md)

已登录用户可从侧栏切换账号。[登录](https://ramancloud.xmu.edu.cn/rc/login) · [注册](https://ramancloud.xmu.edu.cn/rc/register)
