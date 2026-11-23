# 分模块输入、任务与结果保存

## 使用

- 四个单谱功能的上传仍各自独立，模型模块输入不会出现在预处理任务中。
- 预处理、库匹配、结构生成和新完成的 SSnet 混合谱解析自动进入“分析记录”；结果名称可修改，不再需要额外点击“保存分析结果”。
- 未完成任务从分析记录继续；SSnet 标准品训练模型仍在混合物模块管理。
- 通过“导出”下载结果，需要团队访问时才“共享到项目”。已有记录与接口继续兼容。
- 统一流程与更新方式见 [RECORDS_WORKFLOW.md](RECORDS_WORKFLOW.md)。

## 已有数据

已有预处理方案的任务继续属于智能光谱处理。各模块已经建立的输入记录、后台任务快照和已保存分析继续使用原有存储。

## 存储与权限

同一数据库中的独立表，不是另建四套数据库或账号系统：

| 模块 | 上传表 | 任务/结果 | 命名保存记录 | 新原件目录 |
| --- | --- | --- | --- | --- |
| 智能光谱处理 | `ai_workflows` | `ai_plan_versions` | 原有版本及分析历史 | `ai_<任务 ID>` |
| 混合物解析 | `ssnet_sources` | `ssnet_jobs` | `ssnet_saved_results` | `ssnet_inputs` |
| 库匹配 | `library_match_sources` | `library_match_jobs` | `library_match_saved_results` | `library_match_inputs` |
| 结构生成 | `structure_sources` | `structure_jobs` | `structure_saved_results` | `structure_inputs` |

目录相对于当前文件存储根目录；继续使用原存储适配器。命名记录关联模块自己的冻结任务，不复制或重新运行模型。
所有输入、原件、冻结任务及命名记录均检查当前用户和项目权限；相同文件名不合并，跨模块输入 ID 不能串用。

## 接口

模块前缀为 `/api/ssnet`、`/api/library-matching`、`/api/structure-generation`。

- `POST /sources/upload`：本模块上传，支持原有格式确认；`GET /sources` 和 `GET /sources/{id}`：重新选取输入。
- `GET /sources/{id}/download?kind=original|standardized`：原件/标准双列。
- `POST /sources/{id}/preprocess`：明确复制为一份新的预处理任务。
- 分析请求新增 `source_id`，与 `workflow_id/version_id` 二选一；仍兼容已保存任务原有的输入快照和旧请求。
- `POST /saved-results`：完成后命名保存，字段 `job_id`、`title`。
- `GET /saved-results?page=1&page_size=20`：本模块分页记录；`GET /saved-results/{id}`：记录与完整冻结任务。
- `GET /api/ai-workflows`：智能光谱处理的最近任务。

## 升级与验证

无新增依赖。重启后端自动创建各模块的表；开发前端刷新，生产前端重新构建部署。
本机验证使用隔离 SQLite 与本地文件，包含保存、权限、转换、快照及服务重启恢复；没有为这次存储改动重新进行完整 SSnet 训练或算法准确性验收。
