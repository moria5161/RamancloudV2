// Shared descriptions keep the homepage and tutorial aligned with the actual workflows.
// These labels describe capabilities, not the installation state of a running server.
export const localize = (value, language) => value[language === 'zh' ? 0 : 1];
export const ASSISTANT_GUIDE_TITLE = ['AI 问答与预处理', 'AI Q&A and preprocessing'];

export const ANALYSIS_GUIDES = [
  // Keep the first five existing entries in their established homepage order.
  {
    id: 'preprocessing', to: '/ai-analysis', icon: 'sparkles',
    title: ['智能光谱处理', 'Intelligent spectrum processing'],
    tag: ['一键预处理 · 可编辑方案', 'Quick preprocessing · Editable plans'],
    description: ['去鬼峰、降噪与基线校正，结果自动记录。', 'Despike, denoise and correct baselines. Results are recorded automatically.'],
    requirement: ['单条光谱或文件夹批量', 'Single spectra or a folder batch'],
    steps: [
      ["上传光谱，或选择示例、项目数据；需要转换时确认预览。","Upload a spectrum or select an example or project file; confirm conversion if prompted."],
      ["设置处理波段，点击“生成预处理方案”。可选 AI 推荐或本地规则。","Set the range and generate a plan using AI or local rules."],
      ["检查去鬼峰、降噪、基线校正的顺序，按需调整算法与参数。","Review the despike, denoise and baseline steps; adjust methods and parameters as needed."],
      ["点击“开始处理”，对比处理前后的曲线；结果自动记录。","Start processing and compare the curves. Results are recorded automatically."],
      ['在结果页“导出”原始或处理后光谱的 TXT、PNG；点击“继续调整”可生成新版本。', 'Export original or processed spectra as TXT or PNG. Refine the result to create a new version.']
    ],
    notes: [
      ["候选评分仅供参考，请检查真实峰是否保留。","Candidate scores are advisory; check that real peaks are preserved."],
      ['批量处理：上传文件夹，在一条谱上确认方案后应用到所选文件；支持勾选结果批量导出 ZIP。上限为 100 个文件、总计 40 MB、每文件 4 MB。', 'For batches, upload a folder, review a plan on one spectrum and apply it to selected files. Export selected results as a ZIP. Limits: 100 files, 40 MB total, 4 MB per file.']
    ],
  },
  {
    id: 'mixture', to: '/spectral-unmixing', icon: 'branches',
    title: ['混合物解析', 'Mixture analysis'],
    tag: ['SSnet · 本地实验版', 'SSnet · Local experimental version'],
    description: ["训练标准品模型，提取混合谱中的目标信号。","Train a standard model to extract a target signal from mixture spectra."],
    requirement: ['混合谱须覆盖所选模型波段', 'Mixture must cover the selected model’s range'],
    steps: [
      ["在“建立标准品模型”填写物质名称，添加同一物质的标准谱或重复测量谱。","Under Train a standard model, name the substance and add its standard or replicate spectra."],
      ["确认单位，选择标准谱共同覆盖的训练波段和采样点数。","Confirm units, then choose a shared training range and grid size."],
      ['点击“开始训练并保存模型”，在“标准品模型记录”查看进度或停止训练。', 'Choose Train and save model. Follow progress or stop training in Standard model records.'],
      ["进入“解析混合谱”，选择已训练模型，上传覆盖其波段的混合谱并开始解析。","Under Extract from a mixture, select the trained model, upload a mixture covering its range and run extraction."],
      ["检查目标信号与 RF 得分，通过“导出”下载结果；完成的解析自动进入分析记录。","Inspect the target signal and RF score, then export results. Completed extractions appear in Analysis Records automatically."]
    ],
    notes: [
      ["每种目标物分别建模，模型可重复使用；不支持未知组分自动识别。","Train a reusable model for each target. Automatic unknown-component discovery is not supported."],
      ["RF 得分不代表浓度或检出限。CPU 训练可能较久，减少轮数仅适合试跑。","RF is not concentration or detection limit. CPU training can be slow; fewer epochs are for trial runs."]
    ],
  },
  {
    id: 'library', to: '/library-matching', icon: 'database',
    title: ['库匹配', 'Library matching'],
    tag: ['PeakNet · 固定 2805 类', 'PeakNet · 2805 fixed classes'],
    description: ["匹配库内物质，对比参考谱。","Find library candidates and compare reference spectra."],
    requirement: ['完整覆盖 220–1800 cm⁻¹', 'Full coverage of 220–1800 cm⁻¹'],
    steps: [
      ["上传光谱或选择预处理版本；也可载入乙醇示例。","Upload a spectrum, choose a preprocessing version or load the ethanol example."],
      ["确认单位及 220–1800 cm⁻¹ 波段覆盖。","Confirm Raman-shift units and full 220–1800 cm⁻¹ coverage."],
      ["选择是否预处理及候选数量，点击“开始库匹配”。","Choose preprocessing and candidate count, then start matching."],
      ["点击候选对比参考谱，通过“导出”下载结果；完成后可从分析记录重新打开。","Select a candidate to compare reference spectra, export results or reopen them from Analysis Records."]
    ],
    notes: [
      ['模型仅在固定 2805 类中排序，得分不代表鉴定概率。', 'The model ranks 2805 fixed classes; scores are not identification probabilities.'],
      ['乙醇示例来自库内缓存，用于验证流程，不能作为独立样品的准确率测试。', 'The ethanol example comes from the library cache. It checks the workflow, not accuracy on independent samples.']
    ],
  },
  {
    id: 'structure', to: '/structure-generation', icon: 'atom',
    title: ['光谱到结构', 'Spectrum to Structure'],
    tag: ['Vib2Mol · 候选结构', 'Vib2Mol · Candidate structures'],
    description: ["由拉曼光谱生成候选分子结构。","Generate candidate molecular structures from Raman spectra."],
    requirement: ['当前要求完整 400–4000 cm⁻¹', 'Currently requires full 400–4000 cm⁻¹'],
    steps: [
      ["上传单条光谱，或选择已保存的预处理版本。","Upload a spectrum or choose a saved preprocessing version."],
      ["确认单位，检查输入完整覆盖 400–4000 cm⁻¹。","Confirm units and full 400–4000 cm⁻¹ coverage."],
      ["选择生成模式、候选数量和匹配重排；已知分子式可选填。","Choose generation mode, candidate count and reranking. A known formula is optional."],
      ["点击“生成候选结构”，查看结构式与得分，通过“导出”下载 JSON/CSV/SDF；结果自动记录。","Generate candidates, inspect structures and scores, then export JSON/CSV/SDF. Results are recorded automatically."]
    ],
    notes: [
      ["分子式用于筛选候选。Agent 为知识增强模式，基础权重仍为官方原版。","The formula filters candidates. Agent adds knowledge support using the official base weights."],
      ['当前不补齐缺失波段；候选结构需结合实验确认。“查看结果布局示例”仅演示界面。', 'Missing ranges are not filled by the current implementation. Verify candidates experimentally. The result layout preview only demonstrates the interface.']
    ],
  },
  {
    id: 'hyperspectral', to: '/hyperspectral', icon: 'layers',
    title: ['高光谱处理', 'Hyperspectral processing'],
    tag: ['成像与时间序列', 'Imaging & time series'],
    description: ['查看成像光谱和时间序列，在底部配置处理步骤。', 'View spectral images and time series, and configure the workflow below the plots.'],
    requirement: ['Mapping / 时间序列 / MAT 数据立方体', 'Mapping / Time series / MAT cubes'],
    steps: [
      ['选择示例或上传数据。需要指定数据模式或空间布局时，展开“导入设置”。', 'Choose an example or upload data. Expand Import settings to specify the data mode or spatial layout.'],
      ["核对波数轴和数据尺寸，在热图选择像素或时间点查看曲线。","Check the spectral axis and dimensions; select a pixel or time point to inspect its curve."],
      ['在底部“处理设置”添加步骤，点击步骤展开参数。运行流程后，对比处理前后的平均谱和同一波数的成像。', 'Add steps under Processing settings below the plots. Select a step to open its parameters. Run the workflow and compare the mean spectra and images at the same Raman shift.'],
      ['从分析记录重新打开结果；导出 MAT 保留完整数据。', 'Reopen results from Analysis Records. Export MAT to retain the full data.']
    ],
    notes: [
      ['支持已验证的 Mapping 文本、MAT 立方体及 Horiba L6M 成像文件；当前 NPG、WXD 读取器仅支持单谱。', 'Supports verified mapping text, MAT cubes and Horiba L6M images. The current NPG and WXD readers support single spectra only.'],
      ["Mapping 拆分、单谱合并和仪器格式互转在“附加工具”中。","Use Extra Tools to split mappings, merge spectra or convert instrument layouts."]
    ],
  },
];

ANALYSIS_GUIDES.push({
  id:'peak-fitting', to:'/peak-fitting', icon:'line-chart',
  title:['分峰拟合','Peak fitting'], tag:['Voigt · 高斯 · 洛伦兹','Voigt · Gaussian · Lorentzian'],
  description:['在基线校正后的光谱上设置多峰，查看分峰、总拟合和残差。','Fit baseline-corrected spectra and inspect components, total fit and residuals.'],
  requirement:['单条光谱，先完成基线校正','One spectrum, with baseline correction completed'],
  steps:[
    ['上传已校正基线的光谱，或选择智能光谱处理的已完成版本；确认单位。','Upload a baseline-corrected spectrum or select a completed preprocessing version; confirm units.'],
    ['设置拟合区间，依据峰顶、肩峰、参考谱和文献添加分峰，填写初始峰位和宽度。','Set the fitting range and add peaks using maxima, shoulders, reference spectra and literature. Enter initial centers and widths.'],
    ['展开初值与约束，设置峰位、宽度、面积和η范围。相等的上下限与初值可固定参数；纯高斯和纯洛伦兹固定η。','Expand Initial values & bounds to set center, width, area and eta limits. Equal bounds and initial value fix a parameter; Gaussian and Lorentzian profiles fix eta.'],
    ['开始拟合，检查残差、约束边界及参数稳定性，按需改变初值或峰数重新比较。','Fit and inspect residuals, bound warnings and parameter stability. Change initial values or peak count and compare again.'],
    ['结果自动进入分析记录，可导出参数CSV、全部曲线TSV、拟合图PNG和完整ZIP。','Results are saved to Analysis Records. Export parameter CSV, all curves TSV, figure PNG or a complete ZIP.'],
  ],
  notes:[
    ['拟合不自动扣基线、归一化或插值。模拟三峰示例只用于操作演示。','Fitting does not subtract baselines, normalize or interpolate. The simulated three-peak example demonstrates the workflow only.'],
    ['宽度参数沿用原脚本的高斯／洛伦兹宽度分配，实际FWHM另行计算；高R²不代表分峰方案唯一。','The source width parameter distributes Gaussian/Lorentzian widths; actual FWHM is computed separately. High R² does not establish a unique decomposition.'],
  ],
});

export const EXTRA_TOOL_GUIDES = [
  { title: ['拆分 Mapping', 'Split Mapping'], input: ['多点 Mapping 文本或已支持的 Horiba L6M', 'Multi-position mapping text or supported Horiba L6M files'], output: ['每条谱一份 TXT，打包为 ZIP', 'One TXT per spectrum in a ZIP'] },
  { title: ['合并光谱', 'Merge spectra'], input: ['波数轴相同、无表头的双列 TXT / ASC / CSV', 'Headerless two-column TXT / ASC / CSV files with the same spectral axis'], output: ['第一列波数、后续各列强度的多谱表', 'A table with Raman shift followed by intensity columns'] },
  { title: ['格式转换', 'Convert layouts'], input: ['Horiba / Nanophoton 布局的 Mapping TXT', 'Mapping TXT in Horiba or Nanophoton layout'], output: ['另一种 Mapping 文本布局', 'The other mapping text layout'] },
  { title: ['标准双列转换', 'Standardize spectra'], input: ['受支持的仪器文件，如 L6M / NPG / WXD', 'Supported instrument files, such as L6M / NPG / WXD'], output: ['波数—强度 TXT 与来源说明 ZIP', 'A ZIP with Raman-shift/intensity TXT and source details'] },
];

export const GUIDE_SECTIONS = [
  { id: 'quick-start', title: ['第一次使用', 'First run'] },
  { id: 'import', title: ['数据导入与转换', 'Import & conversion'] },
  ...ANALYSIS_GUIDES.map(({ id, title }) => ({ id, title })),
  { id: 'extra-tools', title: ['附加工具', 'Extra Tools'] },
  { id: 'records', title: ['分析记录、导出与共享', 'Records, exports & sharing'] },
  { id: 'assistant', title: ASSISTANT_GUIDE_TITLE },
  { id: 'faq', title: ['常见问题', 'Common questions'] },
];
