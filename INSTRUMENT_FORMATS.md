# 仪器数据兼容与嘉庚实验室调研

## 三类原生仪器样本（2026-11-04）

本批 `光谱/三大仪器` 的检查结果及新增支持：

| 仪器文件 | 本批读取结果 | 智能光谱处理 |
| --- | --- | --- |
| Renishaw `.wxd` | 原有读取器可读，2280 点 | 查看转换预览后确认导入 |
| Horiba `.l6m` | 新增 LabSpec6 SpIm 读取器，10×14 个位置，每谱 1600 点 | 在预览中选择一条位置光谱后确认，不自动平均 |
| Nanophoton `.npg` | 新增 MultiGraph v2 单点读取器，1340 点 | 使用文件内激发波长换算拉曼位移，预览后确认 |

Horiba 原始 float32 波数、强度和 X/Y 坐标完整读取；公共数据布局为行=Y、列=X，
原文件的采集顺序为 X 外层、Y 内层。高光谱处理可直接打开本批 `.l6m`，
单谱的三个分析模块也沿用位置选择。多谱文件在文件夹批量导入时标为需单独选择，
不会默认取第一条；可先在“附加工具 → 拆分 Mapping”下载整组 TXT，再批量处理。
拆分入口与标准双列转换共用读取器，原生 L6M 无需先手动转成 TXT；默认自动识别，
仪器选项用于补充无表头文本的布局。单谱文件提示无需拆分，可使用标准双列转换。

NPG 本批结构内部存的是波长 nm；读取文件内激发波长（约 532 nm），按
`RamanShift = 1e7 × (1 / laser_nm − 1 / wavelength_nm)` 转换。确认页显示此次单位换算，
强度不做平滑或归一化。仪器记录了横轴未校准，页面保留该实际提示。
常规 nm 文本仍拒绝，不根据仪器名称猜测激发波长。

附加工具的“拆分 Mapping”和“标准双列转换”输出 ZIP：每条谱一份 `spectrum_XXXXXX.txt`，
`manifest.json` 记录条数、坐标、转换来源和单位换算。转换不创建分析任务或保存上传。
原始文件保留策略不变；单谱确认导入后可分别下载原件和标准双列，数值以双精度完整导出。

支持范围限定为本批验证结构；其他 LabSpec6 工程、NPG 多图/成像与 WXD 成像不据此视为支持。
新增读取器通过长度、类型、单位、数组尺寸和数值合法性检查拒绝不兼容文件。
目前完成容器字段交叉检查和导出数值回读；Horiba/Nanophoton 尚无同文件的厂商 TXT，
尚未完成仪器软件导出值的逐点对照。读取器由本地样本结构独立实现，原始实验文件不发布。
格式背景可参考 [nirs4all 的 LabSpec6 格式说明](https://nirs4all-formats.readthedocs.io/en/latest/formats/horiba-labspec.html)。

无新增依赖，重启后端并刷新前端即可；生产部署需要重新构建前端。

## 既有格式与调研范围

核对日期：2026-10-18。范围为 RamanCloud 的拉曼单谱、序列与二维成像上传，
不是将电镜、XRD、质谱、核磁、荧光或红外数据一律作为拉曼处理。
“品牌有此导出功能”“此结构可解析”“某台仪器的实际文件已验证”是不同结论。
当前没有用户提供的嘉庚真实文件，不能宣称兼容该实验室所有机型和软件版本。

## 嘉庚与厦大公开依据

| 公开设备/资料 | 可用入口 | 本项目状态 |
| --- | --- | --- |
| 嘉庚共享平台 LabRAM HR Evolution（原位共聚焦拉曼） | 操作规程明确单谱 TXT，mapping 原文件为 L6M、显微图像 L6V | 通用双列和 Horiba 行矩阵已测试；L6M/L6V 原生读取未实现，需另导出带坐标数值表；真实机台文件待验收 |
| 同平台 Renishaw 倒置式共聚焦拉曼 | WiRE WDF 或带轴文本 | 官方读取库已接入，单谱、公共轴序列、完整二维坐标图测试通过；真实机台文件待验收 |
| 同平台 Nanophoton 激光共聚焦拉曼 | Wavenumber + x列_y行 像素列，交替波数/强度列 | 项目现有示例与合成文件已测试；实际导出版本待验收 |
| 同平台 WITec 快速成像拉曼 | ASCII 单谱/带表头矩阵、MAT 公共轴立方体 | 适配上述结构；WIP 原工程未支持，分离 X/Y 文件必须先合成带轴数据 |
| 同平台 HORIBA XploRA | 带波数轴 TXT | 走通用单谱或 Horiba 矩阵；真实版本待验收 |
| 同平台 IDSPEC Arctic 等自研仪器 | 明确波数/强度列的文本 | 仅结构匹配时支持，不凭型号猜列；需要原始样例 |

公开来源：
- [嘉庚材料表征共享平台首页](https://ikkem-cfc.xmu.edu.cn/)
- [LabRAM HR Evolution 设备页](https://ikkem-cfc.xmu.edu.cn/instrument/detail-56.html)
- [LabRAM 操作规程，明确光谱保存为 TXT](https://ikkem-cfc.xmu.edu.cn/upload/file/20240820/1724145435476701.pdf)
- [共享仪器列表，包含 Renishaw、Nanophoton、WITec、XploRA、IDSPEC](https://ikkem-cfc.xmu.edu.cn/mobile/instrument/list?modal=182&num=100001)
- [厦大任斌课题组仪器照片/名称](https://bren.xmu.edu.cn/Lab_tour.htm)

共享网站也列出厦大其他所属单位的设备，不能据此认定全部设备都属于嘉庚实验室。
网页公开资料仅用于确认设备及导出路线，不是实际样本文件或完整格式规范。

## 市场常见导出路线

| 品牌/软件 | 官方资料中的交换格式 | 当前使用建议 |
| --- | --- | --- |
| HORIBA / LabSpec | 以嘉庚公开规程的 TXT 为优先依据 | 导出带波数的数值表，不上传图片或仅强度文件 |
| Renishaw / WiRE | WDF、Galactic SPC、文本 | 优先 WDF 或完整坐标文本；SPC 目前拒绝并提示转出 |
| WITec / Suite SEVEN | ASCII、JCAMP-DX、SPC、MATLAB、CZI、HDF5 | ASCII/MAT；JCAMP 仅当前支持的单条 Raman 子集，不支持 WIP/CZI/HDF5 原工程 |
| Bruker / OPUS | ASCII、JCAMP，3D 可导出 ASCII/MATLAB | 仅拉曼数据按支持结构导入；OPUS 原生 .0 等未支持 |
| Thermo / OMNIC | 各版本有 SPA/SPG/SPC/JCAMP/文本等交换路线 | 参考对应版本文档导出数值 CSV/TSV；SPA/SPG/NGS 未支持 |
| Metrohm / B&W Tek BWSpec | BWSpec/Simple TXT，原始/LIMS/Simple CSV | 优先 Simple TXT/CSV（Raman Shift + 强度）；其他多列不能默认选最后一列 |
| Ocean Optics / OceanView | ASCII，通常含波长轴 | 仅明确转换为 Raman Shift 的光谱可直接进入当前 Raman 流程；nm 不自动当 cm⁻¹ |

厂商/规范来源：
- [Renishaw WiRE 软件说明](https://www.renishaw.com/en/raman-software--9450)
- [Renishaw WDF 官方 Python 包，Apache-2.0](https://pypi.org/project/renishaw-wdf/)
- [WITec Suite SEVEN 导出格式](https://raman.oxinst.com/products/software/suite-seven)
- [Bruker OPUS 基础包](https://www.bruker.com/en/products-and-solutions/infrared-and-raman/opus-spectroscopy-software/base-package.html)
- [Thermo OMNIC 导入导出](https://knowledge1.thermofisher.com/Molecular_Spectroscopy/Molecular_Spectroscopy_Software/OMNIC_Family/OMNIC_Paradigm_Software/OMNIC_Paradigm_Operator_Manuals/Latest_OMNIC_Paradigm_User_Guide/Import_and_export_data)
- [Thermo OMNIC 宏示例，含 SPG 转 CSV](https://knowledge1.thermofisher.com/Molecular_Spectroscopy/Molecular_Spectroscopy_Software/OMNIC_Family/OMNIC_Family_Knowledge/Macro_Examples_for_use_with_OMNIC_Software)
- [BWSpec 官方手册](https://www.metrohm.com/content/dam/metrohm/shared/documents/technical-specifications/290020235-P.pdf)
- [OceanView 官方手册](https://www.oceanoptics.com/wp-content/uploads/2024/05/oceanviewioperation-manual.pdf)
- [IUPAC JCAMP-DX](https://iupac.org/what-we-do/digital-standards/jcamp-dx/)

## 已验证的教学型与海洋光学导出样例

本仓库 `光谱/` 下的两份用户样例已实际解析并通过 HTTP 上传及界面检查：

- `MG 1mg L（教学型拉曼）.txt`：表头为 EduRaman Pro，1024 点。文件同时提供 pixel、wavelength、wavenumber、ramanshift、intensity；优先提取第 4 列 ramanshift 和第 5 列 intensity，不将绝对波数列用于拉曼位移。
- `100um，900ms，100mw（海洋光学usb2000）.txt`：2048 点、两列有效数值，允许末尾空列。作为双列谱直接导入；文件的 `RamanShift:203` 标记未明确给出单位，保留轴单位待核对提示，不据此猜激光波长或校准参数。仪器型号来自用户的文件名标注。

上述结论仅覆盖这两份导出结构，不代表所有仪器原生格式或全部软件版本已兼容。

智能光谱分析上传需要整理的多列文本、XLSX、WDF 等格式时，先返回列映射和前 5 点预览，点击“确认转换并导入”后创建任务。批量上传同样先确认，其中无效文件独立标记失败。取消确认不创建任务、不保存本次上传。项目中的已保存文件在新建分析时也经过相同确认；内置示例可直接载入。

转换仅整理格式，不裁剪、重采样、归一化或更改点数；标准横轴为拉曼位移 cm⁻¹。原始文件按字节保留，导入后可分别下载原文件和标准双列 TXT（`RamanShift(cm^-1)`、`Intensity`）。标准双列以 17 位有效数字导出，保持浮点数往返一致；诊断中记录原文件与标准文件的 SHA-256、源列位置及确认状态。

上传接口未确认时返回 `requires_confirmation: true` 的预览，不含任务 ID。确认请求需重新提交文件并设置 `confirm_conversion=true`，实际导入会重新验证该文件。双列数据可直接导入。标准双列下载为 `GET /api/ai-workflows/{id}/download?kind=standardized`，无须先创建处理方案；原始文件下载仍为 `kind=original`。

## Renishaw WXD 单谱导入（2026-10-31）

已接入用户提供的 `reinshaw-xplora.zip` 中 **17 个 WXD 单谱文件**，每条 574 点；其中
10 组与配套 WiRE TXT 逐点核对，两列按 TXT 导出时的 6 位有效数字舍入后全部一致。
这一结论只覆盖本批已验证的保存结构，不代表所有 Renishaw 仪器、WiRE 版本或 WXD 文件。

在智能光谱处理选择 `.wxd` 文件，系统显示“Renishaw WXD 单谱”、点数、波段和前 5 点预览，
点击“确认转换并导入”后再创建任务。可分别下载原始 WXD 和标准双列 TXT。
批量上传和项目文件转入分析也经过同样的确认；取消不创建本次分析任务。
沿用平台现有导入与下载权限、原件存储和 SHA-256 记录，无需安装新依赖。

读取器位于 `backend/wxd_single.py`：检查本批容器头尾、受限 zlib 解压、类型化双精度数组、
拉曼位移单位、单次采集及完成状态。相同数值快照可去重；若出现多个不同结果则拒绝猜选。
只读取文件中存储的光谱，不运行文件内嵌脚本，也不重新执行仪器处理算法。
标准化保留原始点数、递减轴顺序及双精度值，不裁剪、插值、归一化或按 TXT 精度提前舍入。

当前不支持 WXD 成像、多谱序列、不同结果快照的选择及其他保存结构。解析不确定、损坏、
单位不符或超出 4 MB 时明确拒绝，提示由 WiRE 导出 TXT 或受支持的 WDF；WXD 与 WDF 的读取规则独立。
ZIP 中普通双列 TXT 继续直接导入；本次不改变非标准文件后缀的处理规则。
本批实验原件、压缩包和转换产物不纳入 Git，避免将实验数据随源码发布。

自动测试使用合成的格式片段验证损坏、单位、单谱范围和歧义拒绝，以及 HTTP 确认、原件保存、
精度和权限；不将合成数据当作厂商原生文件验收。拥有原始 ZIP 时可额外运行真实样例核对：

```powershell
$env:RAMANCLOUD_WXD_FIXTURE_ZIP = '自己的路径\reinshaw-xplora.zip'
& .\.venv\Scripts\python.exe -m unittest discover -s backend/tests -p test_wxd_single.py -v
```

## 当前实际支持的结构

混合物解析、库匹配、结构生成沿用这里的解析与转换确认规则，但输入记录和原始文件按模块分别保存；不会为每次上传创建智能预处理任务。各自的“本模块上传记录”和原件/标准双列下载见 [MODULE_RECORDS.md](MODULE_RECORDS.md)。

核心入口：`backend/spectral_formats.py`，由高光谱、单谱上传、智能分析单个/批量导入、
项目数据格式检查共用。文件工具原有拆分/转换逻辑不是通用转换器，本次没有改写。

- TXT/CSV/TSV/DAT/ASC/XY/PRN：UTF-8/BOM、带 BOM 的 UTF-16、GB18030；Tab、逗号、分号、空白分隔；科学计数法与 D 指数。
- 双列单谱；有明确表头的多列单谱，包括教学仪器的 `A_wavenumber`、`A_intensity` 列。
- Nanophoton 的 `Wavenumber + x0_y0 ...`；交替 `wn(...) / 强度` 时间序列。
- Horiba 第一行公共波数、后续坐标+光谱行矩阵；支持递增和递减轴。
- `X,Y,Raman shift,Intensity` 成像长表；`Time,Raman shift,Intensity` 序列长表。
- 无表头 Renishaw 风格长表，必须手动指定；公共轴行/列矩阵也保留手动布局入口。
- MAT 沿用 `cube`、`x` 约定，支持的 MAT 版本与限制见 TSHI.md。
- XLSX：单工作表、纯数值数据；无宏、不执行公式、不使用不确定的公式缓存；不支持旧 XLS。
- JCAMP-DX：通过 `jcamp` 库读取单条 RAMAN SPECTRUM，必须有有效 NPOINTS 与 cm⁻¹ 轴；多块、NTUPLES、其他谱种拒绝。不是完整 JCAMP 标准认证。
- WDF：通过 Renishaw 官方库读取公共轴单谱、序列和完整二维坐标图；拒绝未采集完成、多轨/独立横轴、多 Z 层、非 RamanShift 轴和损坏的数据块。
- WXD：本批已验证保存结构的 Renishaw WiRE 单谱，需确认后转换为标准双列；详见上节，不支持 WXD 成像与序列。

SPC、WIP、LabSpec 工程、OPUS、SPA/SPG/NGS、CZI 等未实现原生读取。
对这些格式提示厂商软件导出路线，不用文件扩展名伪装成兼容。

## 自动识别与错误处理

默认“文件格式”和“解析结构”均为自动识别。先检查容器内容特征，再识别表头、
坐标和矩阵结构。MAT/WDF/XLSX 有内容识别；文本不根据文件名猜仪器型号。
明确的像素表头优先于遗留的仪器选择，因此旧界面选择错误不会再把 Wavenumber 当数字。
歧义多列表不会任意选最后一列，需用户指定结构或重新导出明确表头。

波数须严格单调且不重复，所有必要数值须有限；坐标重复、网格缺失、
各像素波数不一致均拒绝，不静默补零、平均、删行、插值或排序。
单位未声明时显示待确认警告；明确的 nm、像素或能量轴拒绝，不猜激光波长。
数值合法不等于数据来自真实实验，更不代表仪器校准合格。

高光谱单文件 128 MB、3～20000 波段、最多 8000 万个数值；
智能单谱仍为每文件 4 MB、8～20000 点；批量仍为 100 文件/总 40 MB。
Excel 另有解压大小/单工作表约束；JCAMP 限单文件 4 MB。
成像坐标统一为行=Y、列=X，记录原坐标；不改变源文件。
项目数据管理可保留未解析文件，但明确标记失败，不能把“已保存”当成“已兼容”。
智能分析与项目数据管理保存原始文件字节；高光谱上传仍沿用临时数据集缓存，
不因这次格式适配变成永久原文件存储。

## 安装与验收

新增依赖固定在 `backend/requirements.txt`：openpyxl 3.1.5、jcamp 1.2.2、renishaw-wdf 1.3.1。
WDF 1.4.0 在本机 Python 3.8 实测存在导入问题，未使用该版本。
本机 Python 3.8 下测试通过不代表任意新版 Python 和任意厂商版本已验证。
更新依赖后重启后端。

测试包含现有仪器示例、合成结构、实际格式库、HTTP 上传、权限、批量混合格式、
原始文件字节保留及错误数据。合成 WDF 不是嘉庚机台实测文件。
最终设备级验收请提供：品牌/型号、软件版本、单谱与 mapping 原始样本、
仪器软件中的同一像素/波数截图；检查轴单位、像素位置、谱条数和数值逐一一致。
