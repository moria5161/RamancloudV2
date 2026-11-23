# 预处理算法标准与核查

以用户提供的 RamancloudV2-main（自身版本2.2.0）的算法实现和参数为准。智能单谱、高光谱界面统一使用算法名称，不再并列展示旧版或兼容实现。高光谱新增TSHI保留，去鬼峰和现有任务、数据、结果管理流程保留。

## 统一算法

去噪：Savitzky–Golay、Wavelet/WTD、PEER、F2P。多谱/高光谱另有TSVD，高光谱成像保留TSHI/IIALRMA。

基线校正：AirNet、AirPLS、AABS、IModPoly、SNIP。

SG使用原代码局部多项式滤波；WTD使用db1–db9和原阈值公式。PEER使用原峰提取保留算法。AirPLS使用pybaselines.airpls自适应重加权，不再用AsLS代替。SNIP为迭代削峰，不是滚动最小值。AABS使用Ln/Lb原算法，IModPoly使用pybaselines.imodpoly。TSVD按log1p奇异值二阶差分曲率筛选，只适合对齐多谱，单谱不推荐。参数及数据长度的有效性仍会检查。

## 模型已接通

AirNet使用原有backend/baseline_cor/model_pt/0925RU_statedict.pth，严格匹配ResUNet_2500全部233项state_dict，已完成真实推理。

F2P使用作者公开的Fast2PeakRPE权重，严格加载并完成真实推理。未强行使用不兼容的95项F2P_ps16_dp8_mr0.25.pth。

作者代码：https://github.com/moria5161/fast2peak
作者权重：https://huggingface.co/moria5161/fast2peak
固定修订：140d056f342ebccb66b6ae052150821acc207c87
文件：checkpoints/f2p/best_checkpoint.pth
SHA-256：965cec230ea52a7094a068629b9f32a2ef3efeb6342729d47e7f7a02c7899293

F2P与原始config.yaml存放在被Git忽略的.runtime/preprocessing-models/f2p。安装时从作者原地址获取并验证哈希，不把模型重新分发到普通Git。权重许可独立于代码许可，公开服务或再分发前需核实作者的适用条款。

## 安装和使用

当前本机已准备依赖与两个模型。更新后重启新版后端，刷新开发前端；生产前端重新构建。旧项目运行目录不变。

其他电脑用Python3.11/3.12执行：

```powershell
py -3.12 scripts/setup_legacy_algorithms.py
# 有需要时添加 --proxy http://127.0.0.1:实际端口
```

setup_all_models.py也包含该步骤。脚本复用独立.venv-vib2mol，安装科学计算依赖与CPU PyTorch，下载并校验F2P，检查仓库中AirNet权重。可通过RAMANCLOUD_LEGACY_PYTHON、RAMANCLOUD_F2P_MODEL、RAMANCLOUD_AIRNET_MODEL指定自定义位置。

初始预处理默认由本地规则生成，也可切换大模型，依据所选波段的成对光谱采样、噪声、峰宽和背景特征推荐算法与参数。320点以内传送完整所选光谱，长光谱保留均匀点、分段极值及强峰邻域；执行仍使用完整数据。随后可以更换统一目录中的算法，改参数、预览并运行。高光谱在去噪或基线步骤中选择；TSHI沿用现有成像限制和参数。

SG/WTD直接使用原算法，其余方法通过独立环境按矩阵执行。失败会明确提示，不自动换算法。AirPLS在特定数据和参数下可能数值求解失败，可减小lambda或差分阶数。算法可运行不代表适用于所有数据，也不等于科学准确性验收。

TSVD 按执行到该步骤时的矩阵检查规模，估算量为光谱条数 × 波数点数 × 两者中的较小值。后端默认上限为 200 亿，可通过 `RAMANCLOUD_TSVD_MAX_WORK` 按服务器压测结果调整。超限时可先在 TSVD 前裁剪波段。

## 历史与来源

历史结果数组和图像不批量重写；新生成方案按统一标准执行。步骤内部记录实现版本，避免把旧算法缓存当成新计算。旧方案若含已移除的AsLS参数quantile等，需重新生成方案以获得合法参数，不能无声当作AirPLS参数。

原始算法快照位于backend/vendor/legacy_v2，附许可证和SOURCE.json校验清单。兼容已保存内部引用的映射不作为前端独立算法选项。

## 独立核对结果（2026-11-17）

以本机独立目录 `C:\Users\hongzihan\Desktop\RamancloudV2-main` 为对照，逐文件核对算法源码与配置，逐项核对10种算法的默认参数和数值范围。对同一份256点测试光谱及3条光谱矩阵，分别调用原项目和当前项目真实处理流水线，同时核对校正结果和基线数组。所有核对通过。

| 算法 | 单条与矩阵输出的最大绝对误差 |
| --- | --- |
| SG | 8.53×10⁻¹⁴ |
| WTD、PEER、TSVD、F2P、AirNet、AirPLS、AABS、IModPoly、SNIP | 0 |

F2P和AirNet均使用真实权重推理，没有模拟模型或替换为其他算法。TSVD的单行数值也做了核对，但智能单谱界面不提供TSVD；它保留在多谱/高光谱算法选择中。TSHI作为新增算法保留，另外通过12项测试（含原公式数值回归、MAT导入导出、波段与中心图像检查）。这些结果确认实现一致和测试数据可运行，不代表每种算法适合任何仪器数据或任意参数。

核对脚本：`scripts/verify_original_algorithms.py`，报告输出到 `logs/original-algorithm-parity.json`。重跑命令：

```powershell
python scripts/verify_original_algorithms.py --original "C:\Users\hongzihan\Desktop\RamancloudV2-main"
```

脚本需要当前后端依赖，以及前文所述独立科学计算环境和模型权重。

## 范围外遗漏项

旧版“分子结构预测光谱”尚未迁移，需XYZ/SMILES输入、Hessian与极化率导数预测及三份独立模型权重，依赖Open Babel和PyTorch Geometric等。新版Vib2Mol的“由光谱生成候选结构”方向相反，不能视为同一功能。
