# 结构生成：官方 Vib2Mol 本地推理

页面 `/preprocessing/structure-generation` 支持：输入光谱 → 检查适配 → 生成 → RDKit 检查、去重 → 可选分子式筛选 → 匹配重排 → 导出和历史。
支持官方原版及学姐提供的 `vib2mol_agent.zip` 扩展。扩展包没有 `.pth` / `.pt` / `.safetensors` 等模型权重，包含调度、知识索引、重排与历史实验结果；基础模型仍使用官方权重。后续可按契约替换真正的微调 checkpoint。

## 使用

1. 上传单条拉曼光谱，或选择已保存的预处理版本。处理结果页也可点击“用于结构生成”。仪器文件沿用现有转换确认，原文件保留。
2. 确认横轴为拉曼位移 cm⁻¹。当前网站适配器要求完整覆盖 **400–4000 cm⁻¹**。建议先去鬼峰、降噪、基线校正，并保留完整波段。这是当前模式的输入校验策略；局部谱适配未验证，不代表缺少高波数段在原理上绝对不能生成结构。
   上传或选择版本后，页面立即列出当前模型范围及缺失实测波段；按钮旁也会显示具体禁用原因，不必先确认单位才能发现范围不足。此规则按波数范围判断，与仪器品牌、文件名无关。
3. 页面预览实际模型输入：在物理波数轴上线性插值为 1024 点，除以正的最大强度。降序轴会反转；原数据不覆盖，缺失波段不外推、不补零。点击生成即确认该适配方式。
4. 选择“原版”或“Agent 知识增强（实验）”，选择 Top 3/5/10，按需开启匹配重排。已知分子式可留空；本版分子式仅用于**生成后筛选**，不作为该 checkpoint 输入，可能筛掉全部候选。
5. 点击“生成候选结构”。首次运行加载权重；离开页面任务继续。通过“生成记录”或分析历史可重新打开。
6. 查看二维结构、canonical SMILES、分子式、InChIKey 和匹配得分，导出 JSON / CSV / SDF。不足 Top-k 时显示实际数量，没有有效候选时明确提示。
7. 可填写结果名称并“保存分析结果”，以后从本模块“已保存分析”恢复输入、设置及完整候选。上传原件独立保存，不再创建智能预处理任务；需要预处理时通过明确的复制操作进入。见 [MODULE_RECORDS.md](MODULE_RECORDS.md)。

固定布局示例与真实结果分开，示例不写入生成历史。“导出输入草稿”不执行模型，保留 `inference_performed=false`。

## 安装与启动

新电脑需要 Git 和 Python 3.11 或 3.12，推荐 3.12。模型使用独立环境，不要求把现有网站后端环境改成 3.12。建议预留至少 5 GB：两份权重共 1,259,535,838 字节，约 1.26 GB；本机独立环境约 1.71 GB，合计约 3 GB，不含安装缓存。
**不必下载整个权重仓库或训练数据集。**

项目根目录运行：

```powershell
py -3.12 scripts/setup_vib2mol.py
# 需要代理时，填写本机实际代理端口，仅作用于本次安装
py -3.12 scripts/setup_vib2mol.py --proxy http://127.0.0.1:你的代理端口
```

没有 `py` 启动器时，可用本机 Python 3.12 的真实可执行文件路径替代 `py -3.12`。不要直接复制开发者电脑上的绝对路径。
安装器校验固定源码提交与权重 SHA-256，创建 `.venv-vib2mol` 并安装 CPU PyTorch 与依赖，保留预处理的 `.venv`。
要启用学姐提供的 Agent，运行以下命令；它会自动取得仓库提供的精简运行包，无需单独传文件或下载原始大 ZIP：

```powershell
py -3.12 scripts/setup_vib2mol_agent.py
# 需要代理时同样支持 --proxy http://127.0.0.1:实际端口
```

安装器把代码解压到 `.runtime/vib2mol/source/vib2mol_agent`，即官方代码根目录的下面；不需要手工挪动目录。
原压缩包 SHA-256 为 `690107b695ac8f3d1a9fe2f23a326542a2e71e57d2fdd4fcd6ad9aa4196f0e76`，发布的约 4 MB 精简包 SHA-256 为 `7b512455e34a6ab1218c54611320d11b5b5b7aaf25018db351b951580737867f`。两种包都支持安装，解压后的 195 个运行文件内容一致；精简包省去历史 runs、PDF、媒体与缓存，保留运行所需的 evaluation Python helper。
安装时验证路径和文件 hash，保留已有本地修改不覆盖；生成时再次核对实际代码/索引 hash。两份官方权重和 Agent 精简包现已通过 Git LFS 放入 `model-assets/`，运行解压目录仍不进入 Git。总安装入口为 `py -3.12 scripts/setup_all_models.py`。
安装后照常启动前后端，无需模型终端：

```powershell
# 终端一，从项目根目录开始
cd backend
& ..\.venv\Scripts\python.exe app.py
```

```powershell
# 终端二，从项目根目录开始
cd frontend
npm run dev
```

打开 `http://127.0.0.1:5173/preprocessing/structure-generation`。
旧后端已经运行时，在其终端 Ctrl+C 后再启动。worker 首次生成时自动启动、缓存模型，后端关闭时退出；日志为 `logs/vib2mol-worker.log`。

## 固定来源与模型契约

- [官方源码](https://github.com/X1nyuLu/vib2mol)，Apache-2.0，提交 `732806b99abf4aedac07cf56ac34fd670948e338`。
- [官方权重](https://huggingface.co/xinyulu/vib2mol)，revision `5c0a1aa60009ac9921e80da3e0019c8ec64abd58`。
- 上游 `scripts/configs/generation.yaml` 的 `mols_raman` 组合，架构 `vib2mol`，Raman 单通道。
- 生成路径：`mols/raman-kekule_smiles/vib2mol/2025-07-10-07-46-68d484/epoch999.pth`；SHA-256 `3c418ce5709eea6047f479b54b8f334d6a4eeeda31f7a7b82834b821c418f167`。
- 匹配路径：`mols/raman-kekule_smiles/vib2mol/2025-07-08-02-56-69bd7e/epoch999.pth`；SHA-256 `75c6b17399f105dd9a7ab99c1d3f49f37d0b507ea54565dbdb1cb782d3516eee`。
- 每份 629,767,919 字节；worker 初次加载时校验 SHA，`torch.load(weights_only=True)` 并严格加载，不忽略形状不匹配。
- 配套 tokenizer 来自固定源码的 `models/MolTokenizer`，离线加载。beam size 10，temperature 3.5，上限 128 tokens；没有 EOS 的截断输出丢弃。
- 400–4000 cm⁻¹ / 1024 点参考上游 `figures.ipynb` Raman 网格与[论文](https://arxiv.org/html/2503.07014v4)补充材料；最大值归一化参考论文实验光谱处理。本适配策略会记录，但尚未对不同仪器完成准确性验收。

网页调用纯推理方法 `beam_infer_lm`、`matching`，不调用依赖测试集和真实 SMILES 的评测脚本。
匹配类 softmax 输出仅用于排序，**不是鉴定正确的置信度**。化学有效不代表识别正确；实验背景、仪器、混合物及训练分布差异均会影响结果。
源码、tokenizer 和权重位于 `.runtime/vib2mol`，独立环境位于 `.venv-vib2mol`，均被 Git 忽略。

## 接口、保存与权限

React → FastAPI（现有登录和权限）→ 独立 Python worker。worker 仅监听随机回环地址，使用临时令牌，不直接对浏览器开放。

| 接口 | 功能 |
| --- | --- |
| GET `/api/structure-generation/config` | 安装状态与模型 profile；安装状态不等于模型已经加载 |
| POST `/api/structure-generation/validate` | 所属版本、单位、波段及适配预览 |
| POST `/api/structure-generation/jobs` | 创建冻结输入的异步任务 |
| GET `/api/structure-generation/jobs` | 当前用户最近 30 个任务 |
| GET `/api/structure-generation/jobs/{id}` | queued / running / completed / failed、输入与结果 |
| GET `/api/structure-generation/jobs/{id}/download?format=json` | json / csv / sdf 导出 |

创建字段：`workflow_id`、可选 `version_id`、`unit_confirmed`、`formula`、`top_k`、`rerank`、`engine`（`official` / `agent`）。配置接口可加 `?engine=agent`。未安装扩展时保留原版可用；扩展已安装时新页面默认选择 Agent，打开旧记录则恢复其原模式。
后端重新从服务端读取输入，验证所有者、项目成员资格和完成状态，不信任浏览器提供的数组。
可用 `reuse_job_id` 复用本人历史任务的输入快照；原工作流删除后仍可使用快照。
新生成使用**当前配置模型**，旧任务保留原 profile，比较时核对版本与 hash。

记录原输入、版本引用、实际模型输入、SHA-256、适配参数、模型提交与权重 hash、生成条件、候选、剔除计数与分数。
真实结果同时写入 `analysis_type=structure_generation` 的分析历史；历史摘要省略图片，生成记录保留完整结构图与 SDF。
生成记录仅本人可查看和下载，关联项目权限在创建、读取、完成时重查；分析历史沿用既有显式项目发布。
CPU 串行执行，最多 3 个排队/执行任务。服务重启会将中断任务标为失败，不自动重跑。

## Agent 适配边界

使用提供代码中的 `Vib2MolAgent`、`RulePlanner`、严格分子式过滤、BookRAG、`apply_confidence_second_rerank` 及 `sdbs_raman` 的 Raman 证据规则。
该知识规则 profile 与模型训练数据集分开记录：基础权重仍为 MOLS；Raman 证据规则没有证明在当前仪器样本上提升准确率。
网页使用本站严格校验的生成/匹配工具桥接 Agent，避免包中旧路径 `from infer_generation import ...` 与上游现有 `scripts/infer_generation.py` 不一致，以及原工具 `strict=False` 加载权重的问题。不读取测试集，不传目标 SMILES，不从历史 runs 当作预测结果。
Agent 最大解码长度 256，原版保持 128；都使用 beam 10、temperature 3.5。公式只在生成后严格筛选，不以不匹配候选填满 Top-k。
已有有效候选先由匹配模型排序，Agent 在条件触发时检索知识并辅助重排。只有一个候选时不进行二次重排，仍可展示参考资料；零候选不编造结构。
保留原匹配得分，单独保存知识判断和重排是否发生，网页不把内部启发式 confidence 当作鉴定概率。参考资料展示来源、页码和短摘录，用户仍需实验核实。
仅启用本地规则与文本检索；不启动 Qwen、不调用外部 LLM API。候选库检索、局部结构补全、自然语言多轮 Agent 及 Qwen 解释没有开放，这些需要额外模型、数据或页面设计。

## 微调模型替换

可创建被忽略的 `backend/structure_config.json`，以 `profile`、`paths` 覆盖 `backend/structure_profiles.py` 的配置。
`paths` 支持 `python`、`source`、`generation`、`matching`；更换时必须设置新 profile id 和真实 SHA，重启后端。
该适配器支持单通道 Raman、1024 点、最大值归一化、生成后公式筛选。
新模型如果要求公式条件、不同词表、IR 联合输入或不同归一化，必须同步修改适配器，不能只换权重文件名。

## 验证

前端 19 项测试及生产构建通过；后端 79 项 HTTP 集成测试通过，覆盖权限隔离、输入范围、历史、导出、快照复用和 worker 失败持久化。
新增 4 项 Agent 适配测试通过（独立环境执行 `python -m unittest discover -s services/vib2mol -p 'test_*.py' -v`），覆盖候选池不扩增、保留模型匹配分数、严格公式过滤、空候选、关闭重排，以及物理峰位与参考资料。测试的合成输入只用于验证行为，不作为识别效果证明。
Agent 使用海洋样本实际试跑约 6.4 秒，返回候选及 4 条带页码的知识资料；这只证明调用链路可用，不代表已完成实验识别验收。
独立 QA 页面验证了真实 Agent 任务、结构图、SMILES、JSON 导出、历史保存与恢复（网页任务约 7.4 秒）。390px 视口无横向溢出。测试服务使用独立数据库与测试账号。
在本机 16 GB RAM、无 NVIDIA GPU 的 CPU 环境使用官方权重进行了实际推理。由于本机 torch 2.4 多线程归约计算出现重复输入不一致，默认使用单线程，连续两次推理的候选与分数完全一致。首次约 5.2 秒、模型加载后约 1 秒，海洋样本返回 1 个有效候选，匹配得分很低。这是链路验证，不能作为化学识别准确性证明。
教学型样本不足完整模型波段，会提示范围不足；海洋光学样本可通过输入适配。
