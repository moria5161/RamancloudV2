# 旧版嵌入式 AI 对话

本文记录旧版嵌入式对话的实现和兼容接口。当前右侧助手运行在六个分析工作区，聊天保留在当前会话。智能光谱处理页还支持上传光谱、生成预处理方案和一键预处理。[当前 AI 助手](QA_ASSISTANT.md) · [部署配置](DEPLOYMENT.md#ai-and-algorithm-models)

## 来源与范围

对话引擎、算法命令规范化和光谱诊断指标移植自同学提供的
`Ramancloud_optimize-main.zip`，对应源码仓库为
https://github.com/fzu-luoyonghui/Ramancloud_optimize 。
原 RamancloudV2 的算法与示例数据仍保留原作者贡献。

保留当前项目的用户管理、项目和数据管理、分析历史、结果版本与智能光谱处理流程。
没有覆盖登录路由，也没有移植同学版本中共享浏览器 localStorage 的分析会话。
高光谱页面已移除 AI 对话入口及其前端调用，只保留算法控制面板。
文件工具页的对话、智能光谱处理以及已有对话记录不受影响；后端保留原有兼容接口。

## 运行与配置

后端依赖已固定为本机验证过的版本，当前验证环境为 Python 3.8、Node.js 24。
新的对话功能没有额外的 Python 或 npm 依赖。不保证任意新版 Python 都兼容
原有的 Pydantic 1.9.2；更换运行时后需要重新执行测试。

1. 按 README 安装依赖并启动前后端，或在 Windows 双击 `run_project.bat`。
2. 注册并登录自己的平台账号。
3. 在文件工具页面使用对话面板；单条和批量光谱通过「智能光谱处理」处理。高光谱页面不再提供 AI 对话。
4. 默认不发送数据给外部模型，使用明确标注的本地规则和诊断摘要。

### Ollama（默认，对话与智能光谱处理共用）

安装 [Ollama](https://ollama.com/download/windows)，下载 `ollama pull qwen3:4b-instruct-2507-q4_K_M` 并确保后台服务运行。
默认接口 `http://127.0.0.1:11434`，无需密钥和充值。模型运行在后端所在电脑上，
不是在每个网站访问者的浏览器中运行。模型权重不随源码上传，首次运行需要自行下载。

两种 AI 功能共用 `backend/ai_config.json`；公开模板已改为 Ollama。默认不使用云服务。
配置与状态检查、数据授权、规则回退说明见 [AI_WORKFLOW.md](AI_WORKFLOW.md)。
本地模型不收 API 费用，但占用电脑资源；不要选择 Ollama 的 `cloud` 型号。

### DeepSeek（可选）

复制公开模板 `backend/ai_config.example.json` 为 `backend/ai_config.json`，
在自己的电脑或服务器上填入自己的密钥。这个私有文件已加入 `.gitignore`。
也可以设置 `DEEPSEEK_API_KEY` 等操作系统环境变量。

对话和智能光谱处理共用同一配置，不能将此文件当作前端配置发布。
在面板勾选允许发送数据后，后端才会调用模型。发送内容包含对话文字、
算法参数、诊断指标等摘要，不包括原始文件、完整数组、用户名和账户密钥。
费用和额度由模型服务商决定；余额不足、限流、超时或格式错误时会回退本地规则。
本地规则不是训练模型，也不能代替自由问答。

### Ollama 环境变量

也可在启动后端前设置以下环境变量覆盖私有文件：

```powershell
$env:RAMANCLOUD_AI_PROVIDER = 'ollama'
$env:OLLAMA_BASE_URL = 'http://127.0.0.1:11434'
$env:OLLAMA_MODEL = 'qwen3:4b-instruct-2507-q4_K_M'
cd backend
python app.py
```

公开模板见 `backend/.env.assistant.example`。后端不自动加载 `.env` 文件。
仅接受后端本机回环地址；未安装或未启动会回退规则。`RAMANCLOUD_ASSISTANT_PROVIDER=ollama`
仍兼容旧的仅对话覆盖方式，正常部署不必额外设置。

## 数据、确认与保存

- 对话存储在后端 `assistant_conversations` 表，可使用现有 SQLite/MySQL 适配器。
- 对话按账号和数据源隔离；相同账号重新加载同一份单光谱数据可恢复对话。
- 保留的高光谱对话兼容接口仍按数据集 ID 隔离，当前页面不再创建或加载这些对话。
- 模型只产生回答或待确认方案，不直接运行代码，也不会自动更改数据。
- 命令经过算法白名单、数值范围和裁剪后长度校验，确认前展示最终参数。
- 执行使用已有处理 API，结果进入分析历史；记录与原始数据、参数核对后才标记为已执行。
- 高光谱通过控制面板手动运行整个数据集的处理；平均谱不代表每个像素。
- 热图波数切片不一致时不直接比较；噪声、SNR 和峰匹配均属于启发式指标。
- 数据或参数变化后，旧的待确认建议失效；切换账号不会显示上一账号的对话。

对话服务限制为 4 个并发请求，同一对话不能同时发送多次，单对话最多 100 轮。
光谱输入限制为 8～20000 个有限数值点，预览矩阵最多 20000 个数值。
公网部署还应增加反向代理限流、请求体大小限制、HTTPS 和数据库备份。

## 验证

在仓库根目录运行后端集成测试：

```bash
python -m unittest discover -s backend/tests -p test_ai_workflow.py -v
```

在 `frontend` 目录运行：

```bash
node --test tests/auth-errors.test.mjs
npm ci
npm run build
```

可选浏览器测试使用 Playwright 和已启动的前后端：

```bash
node tests/assistant.e2e.cjs
```

测试调用模拟模型或关闭外发授权，不消耗模型余额。示例数据和配置模板随源码发布，
真实密钥、账户数据库、用户上传文件、日志、依赖目录和构建产物不发布。
GitHub 上传不等于网站部署；私有仓库只有拥有访问权限的人才能克隆。
