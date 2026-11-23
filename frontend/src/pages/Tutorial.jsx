import { systemText } from '../locale.js';
import React, { useEffect, useRef } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ArrowRight, Atom, BookOpen, Database, FileCheck2, FolderKanban, GitBranch, HelpCircle, Layers, LineChart, MessageCircle, Sparkles, Wrench } from 'lucide-react';
import { usePreferences } from '../i18n';
import { useAuth } from '../auth';
import { ANALYSIS_GUIDES, ASSISTANT_GUIDE_TITLE, EXTRA_TOOL_GUIDES, GUIDE_SECTIONS, localize } from '../content/platformGuide';
import FeedbackForm from '../components/FeedbackForm';
import './LearningPages.css';

const ICONS = { sparkles: Sparkles, branches: GitBranch, database: Database, atom: Atom, layers: Layers, 'line-chart': LineChart };

function Section({ id, title, icon: Icon, tag, children }) {
  return <section id={id} className="guide-section" tabIndex={-1} aria-labelledby={`${id}-title`}>
    <div className="guide-section-heading"><Icon size={21} /><h2 id={`${id}-title`}>{systemText(title)}</h2>{tag && <span className="learning-tag">{tag}</span>}</div>
    {children}
  </section>;
}

export default function Tutorial() {
  const { language } = usePreferences();
  const { user } = useAuth();
  const { hash } = useLocation();
  const scrollRef = useRef(null);
  const text = value => localize(value, language);
  const txt = (zh, en) => text([zh, en]);
  const currentSection = hash === '#reading-requirements' ? 'import' : hash.slice(1) || 'quick-start';

  // The app scrolls inside its workspace, not the browser window.
  // Explicit hash handling supports homepage links, reloads and back/forward navigation.
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      const target = hash && document.getElementById(hash.slice(1));
      if (target && scrollRef.current?.contains(target)) {
        target.scrollIntoView({ block: 'start' });
        target.focus({ preventScroll: true });
      } else {
        scrollRef.current?.scrollTo({ top: 0 });
      }
    });
    return () => cancelAnimationFrame(frame);
  }, [hash]);

  const faq = [
    [
      ['如何用助手生成预处理方案？', 'How do I draft a preprocessing plan?'],
      ['在智能光谱处理页，选用工作区中的光谱，或在助手内上传光谱。填写要求后点击“生成预处理方案”，即可在卡片上调整算法与参数。', 'In Intelligent Spectrum Processing, select the spectrum in the workspace or upload one to the assistant. Describe what to do and click Draft preprocessing plan, then adjust the algorithms and parameters on the card.'],
    ],
    [
      ['“一键运行”在哪里？', 'Where is One-click run?'],
      ['“一键运行”在智能光谱处理的方案卡片里。检查数据、步骤和参数，按提示确认单位或文件转换后运行。', 'One-click run is on the plan card in Intelligent Spectrum Processing. Review the data, steps and parameters, and confirm units or file conversion if prompted.'],
    ],
    [
      ['上传成功了，为什么分析按钮还是点不了？', 'Why is an analysis button disabled after a successful upload?'],
      ["请检查单位确认、波段范围和模型状态。库匹配需 220–1800 cm⁻¹，光谱到结构需 400–4000 cm⁻¹，SSnet 按所选模型检查。", "Check units, range and model status. Library matching requires 220–1800 cm⁻¹, Spectrum to Structure 400–4000 cm⁻¹, and SSnet the selected model’s range."],
    ],
    [
      ['为什么有的仪器文件不用确认转换？', 'Why do some instrument files need no conversion confirmation?'],
      ['已经识别出波数、强度两列时可直接导入；需要提取列或读取原生仪器格式时，先核对转换预览。', 'Recognized Raman-shift/intensity columns can import directly. Check the preview when columns must be extracted or a native instrument format is read.'],
    ],
    [
      ['必须打开 AI 才能做预处理吗？', 'Do I need AI to preprocess a spectrum?'],
      ["不需要，预处理可使用本地规则并手动调参。AI 问答需要模型服务。", "No. Preprocessing supports local rules and manual editing. AI Q&A needs a model service."],
    ],
    [
      ['混合物里有什么都不知道，可以直接用 SSnet 找全吗？', 'Can SSnet discover all components of an unknown mixture?'],
      ["不能。当前需要候选物的标准谱和训练模型，只对指定目标进行提取。", "No. Standards and a trained model are needed for each target you want to extract."],
    ],
    [
      ['为什么第一次运行或本机 AI 会等很久？', 'Why can a first run or local AI take a long time?'],
      ['首次运行需加载权重，速度也受硬件和输入长度影响。SSnet 训练可在标准品模型记录中查看进度；AI 回答较长时可停止或继续回答。', 'First runs load weights; hardware and input length affect speed. Follow SSnet training in Standard model records. You can stop AI generation or continue a truncated answer.'],
    ],
    [
      ['保存结果后，其他项目成员就能看到了吗？', 'Are saved results automatically shared with project members?'],
      ['不会。完成的结果自动进入分析记录；点击“共享到项目”后，成员才能在项目的“共享结果”中看到。', 'No. Completed results enter Analysis Records automatically. Use Share to project to make them visible under the project’s Shared results.'],
    ],
    [
      ['库匹配示例为什么能得到接近 100% 的得分？', 'Why can the library example score close to 100%?'],
      ['内置乙醇示例来自库内缓存，用来检查流程。得分是固定类别中的模型输出，不是物质鉴定概率，也不能代表独立实验样品的准确率。', 'The built-in ethanol example comes from the library cache and checks the workflow. Scores rank fixed classes; they are not identification probabilities or accuracy on independent experimental samples.'],
    ],
    [
      ['仪器文件都需要拆分 Mapping 吗？', 'Do all instrument files need mapping splitting?'],
      ['高光谱处理可直接导入已支持的 Mapping 文件。需要为每个位置保存一份单谱时，在附加工具中使用“拆分 Mapping”。', 'Import supported mapping files directly in Hyperspectral Processing. To save a single spectrum for each position, use Split Mapping in Extra Tools.'],
    ],
    [
      ['切换页面后，怎样继续之前的分析？', 'How do I resume an analysis after switching pages?'],
      ['本次打开的网站会保留各分析页面。刷新后从“分析记录”找回已上传任务或已保存结果；开始另一份数据时点击“新建分析”。', 'Analysis pages retain their state while navigating in the current session. After a refresh, reopen uploaded tasks or saved results from Analysis Records. Choose New analysis for another dataset.'],
    ],
  ];

  return <div className="learning-page guide-page" ref={scrollRef}>
    <div className="learning-container guide-container animate-fade-in">
      <header className="guide-header"><div><p className="learning-eyebrow"><BookOpen size={15} />{txt('RamanCloud 使用指南', 'RamanCloud user guide')}</p><h1>{txt('从第一条光谱开始', 'Start with your first spectrum')}</h1><p className="learning-muted">{txt("按步骤完成导入、处理与分析。", "Follow the steps to import, process and analyze spectra.")}</p></div><Link to="/ai-analysis" className="learning-button">{txt('打开处理工作区', 'Open preprocessing')}<ArrowRight size={15} /></Link></header>

      <div className="guide-layout">
        <nav className="guide-toc" aria-label={txt('教程目录', 'Guide contents')}><p>{txt('按任务查看', 'Jump to a workflow')}</p><ol>{GUIDE_SECTIONS.map(section => <li key={section.id}><Link to={`/tutorial#${section.id}`} aria-current={currentSection === section.id ? 'location' : undefined}>{text(section.title)}</Link></li>)}</ol></nav>
        <div className="guide-body">
          <Section id="quick-start" title={txt('第一次使用', 'First run')} icon={BookOpen}>
            <p>{txt('先用内置示例走通预处理，不必一开始就准备实验文件。', 'Try a built-in example to learn preprocessing before preparing your own files.')}</p>
            <ol className="guide-steps">
              <li>{txt("打开“智能光谱处理”，选择一条示例，查看曲线与格式检查。", "Open Intelligent spectrum processing and select an example to inspect its curve and format.")}</li>
              <li>{txt('点击“生成预处理方案”，检查去鬼峰、降噪、基线校正，再点“开始处理”。', 'Generate a preprocessing plan, review despiking, denoising and baseline correction, then choose Start processing.')}</li>
              <li>{txt('结果自动记录。对比曲线后，可“导出”TXT / PNG、“继续调整”或进入后续分析。', 'Results are recorded automatically. Compare curves, export TXT / PNG, refine or continue to analysis.')}</li>
            </ol>
            <div className="learning-actions"><Link to="/ai-analysis" className="learning-primary">{txt('用示例开始', 'Try an example')}<ArrowRight size={14} /></Link><Link to="/tutorial#import" className="learning-text-link">{txt('我有自己的数据', 'I have my own data')}<ArrowRight size={14} /></Link></div>
          </Section>

          <Section id="import" title={txt('数据导入与转换', 'Import & conversion')} icon={FileCheck2}>
            <p>{txt("单谱为两列：拉曼位移（cm⁻¹）和强度。横轴请勿使用波长、像素或绝对波数。", "A spectrum has two columns: Raman shift (cm⁻¹) and intensity. Do not use wavelength, pixels or absolute wavenumber as Raman shift.")}</p>
            <pre className="guide-code" aria-label={txt('标准双列示例', 'Standard two-column example')}>{'RamanShift(cm^-1)\tIntensity\n400.0\t125.6\n401.0\t128.2\n402.0\t126.9'}</pre>
            <p>{txt("单谱需 8–20000 个点，每文件不超过 4 MB；波数严格单调且无重复，数值须有效。", "Use 8–20000 points, up to 4 MB per file, with a strictly monotonic, nonrepeating axis and finite values.")}</p>
            <ul className="guide-format-list">
              <li>{txt("文本：TXT / CSV / TSV / DAT / ASC / XY / PRN；支持双列及可识别的仪器多列表。", "Text: TXT / CSV / TSV / DAT / ASC / XY / PRN; two-column spectra and recognized instrument tables.")}</li>
              <li>{txt('表格与交换格式：XLSX、JCAMP-DX（JDX / DX）、WDF。MAT 数据立方体在“高光谱处理”中打开。', 'Tables and exchange formats: XLSX, JCAMP-DX (JDX / DX) and WDF. Open MAT cubes in Hyperspectral processing.')}</li>
              <li>{txt('原生仪器格式包括已验证的 Horiba L6M、Nanophoton NPG 和 Renishaw WXD。L6M 多点数据可导入高光谱处理。导入单谱时，可从多点文件选择一个位置。', 'Verified native instrument formats include Horiba L6M, Nanophoton NPG and Renishaw WXD. Import multi-position L6M data in Hyperspectral Processing. To import one spectrum, select a position from the file.')}</li>
            </ul>
            <p>{txt('按预览确认提取列与单位，原件和标准双列均可下载。NPG 使用文件内激发波长换算拉曼位移；其他波长数据需提供明确的换算依据。兼容范围以实际文件结构为准。', 'Check extracted columns and units in the preview; both originals and two-column data can be downloaded. NPG uses the recorded excitation wavelength to calculate Raman shift. Other wavelength data need an explicit conversion basis. Compatibility depends on file structure.')}</p>
            <div id="reading-requirements" tabIndex={-1} className="guide-subsection">
              <h3>{txt('各分析模块的输入要求', 'Input requirements by workflow')}</h3>
              <div className="guide-requirements">
                <table>
                  <thead><tr><th scope="col">{txt('模块', 'Module')}</th><th scope="col">{txt('当前输入要求', 'Current input requirement')}</th></tr></thead>
                  <tbody>{ANALYSIS_GUIDES.map(guide => (
                    <tr key={guide.id}>
                      <th scope="row"><Link to={`/tutorial#${guide.id}`}>{text(guide.title)}</Link></th>
                      <td>{text(guide.requirement)}</td>
                    </tr>
                  ))}</tbody>
                </table>
              </div>
              <div className="guide-notes"><p>{txt('当前不自动补齐缺失波段；已截断的版本可返回原始数据重新处理。质量检查仅标记疑似异常，不修改原始数据。', 'Missing ranges are not filled automatically. Reprocess the original if a version was cropped. Quality checks only flag potential issues; they do not alter the original data.')}</p></div>
            </div>
          </Section>

          {ANALYSIS_GUIDES.map(guide => <Section key={guide.id} id={guide.id} title={text(guide.title)} icon={ICONS[guide.icon]} tag={text(guide.tag)}>
            <p>{text(guide.description)}</p><p className="guide-requirement">{text(guide.requirement)}</p>
            <ol className="guide-steps">{guide.steps.map((step, index) => <li key={index}>{text(step)}</li>)}</ol>
            <div className="guide-notes">{guide.notes.map((note, index) => <p key={index}>{text(note)}</p>)}</div>
            {guide.id === 'preprocessing' && <details className="guide-subsection"><summary>{txt('当前算法与参数怎么理解？', 'How do the current algorithms and parameters work?')}</summary><p>{txt('去鬼峰：自动检测疑似窄尖峰并插值修复，半高宽阈值以数据点为单位，处理后应核对真实窄峰。SG：窗口为奇数且须大于拟合阶数；增大窗口可能削弱真实峰。小波和峰保护平滑也需检查峰形变化。', 'Despiking detects narrow spike candidates and repairs them by interpolation; the width threshold is measured in data points. Inspect real narrow peaks afterward. SG needs an odd window larger than its polynomial order; large windows may weaken real peaks. Check shapes after wavelet or peak-preserving smoothing too.')}</p><p>{txt('助手生成的方案优先使用可用的 F2P 降噪和 AirNet 基线校正。基线算法也可在卡片上改用 AirPLS、SNIP 等，具体选项以算法与参数区为准。', 'Assistant-drafted plans prefer F2P denoising and AirNet baseline correction when available. Choose alternatives such as AirPLS or SNIP in the card’s algorithm and parameter settings.')}</p></details>}
            {guide.id === 'hyperspectral' && <details className="guide-subsection"><summary>{txt('成像数据如何使用 TSHI / IIALRMA？', 'How do I use TSHI / IIALRMA on imaging data?')}</summary><p>{txt('添加降噪步骤，选择 TSHI / IIALRMA，设置中心波数、波段半宽和空间参数。中心波数是实际 cm⁻¹，不是数组索引。运行后打开“TSHI 结果”，检查中心图像、奇异值、所选成分及实际处理范围，并下载 MAT 保留完整数据。', 'Add a denoising step, choose TSHI / IIALRMA and set the center shift, band half-width and spatial parameters. The center is a physical shift in cm⁻¹, not an array index. After running, inspect TSHI results for center images, singular values, selected components and the actual processed range. Download MAT to retain the full data.')}</p><p>{txt('TSHI 仅适用于成像数据，并只重建选定波段；不用于时间序列或单谱。BM3D 是可选的中心图像处理，需要额外依赖，不代表整张光谱立方体都经过 BM3D。', 'TSHI works on imaging data and reconstructs only the selected bands; it is not for time series or single spectra. Optional BM3D processes the center image and requires an additional dependency; it does not process the entire spectral cube.')}</p></details>}
            <div className="learning-actions"><Link to={guide.to} className="learning-button">{txt('打开', 'Open')} {text(guide.title)}<ArrowRight size={14} /></Link>{guide.id === 'hyperspectral' && <Link to="/extra-tools" className="learning-text-link">{txt('打开附加工具', 'Open Extra Tools')}<ArrowRight size={14} /></Link>}</div>
          </Section>)}

          <Section id="extra-tools" title={txt('附加工具', 'Extra Tools')} icon={Wrench}>
            <p>{txt('选择工具、上传文件，点击“运行工具”下载结果。', 'Choose a tool, upload files and select Run tool to download the result.')}</p>
            <div className="guide-requirements"><table><thead><tr><th scope="col">{txt('工具', 'Tool')}</th><th scope="col">{txt('上传什么', 'Input')}</th><th scope="col">{txt('得到什么', 'Output')}</th></tr></thead><tbody>{EXTRA_TOOL_GUIDES.map(tool => <tr key={tool.title[1]}><th scope="row">{text(tool.title)}</th><td>{text(tool.input)}</td><td>{text(tool.output)}</td></tr>)}</tbody></table></div>
            <details className="guide-subsection"><summary>{txt('Mapping 和单谱怎么区分？', 'How do mappings differ from single spectra?')}</summary><p>{txt('Mapping 包含多个位置的光谱。例如已验证的 Horiba L6M 样例有 10×14 个位置，每谱 1600 点；NPG、WXD 样例分别只有一条 1340、2280 点的谱。', 'A mapping contains spectra at multiple positions. The verified Horiba L6M example has 10×14 positions with 1600 points each; the NPG and WXD examples each contain one spectrum with 1340 and 2280 points respectively.')}</p><p>{txt('合并要求波数轴一致；合并表不含空间坐标。格式转换仅互换文本布局，不校正不同仪器的响应，当前会保留 1 位小数。', 'Merging requires matching spectral axes; the merged table has no spatial coordinates. Layout conversion does not calibrate different instruments and currently rounds values to one decimal place.')}</p></details>
            <div className="learning-actions"><Link to="/extra-tools" className="learning-button">{txt('打开附加工具', 'Open Extra Tools')}<ArrowRight size={14} /></Link></div>
          </Section>

          <Section id="records" title={txt('分析记录、导出与共享', 'Records, exports & sharing')} icon={FolderKanban}>
            <p>{txt('分析记录保存个人任务和结果；项目与数据用于团队协作。', 'Analysis Records holds your tasks and results. Projects & data is for collaboration.')}</p>
            <ol className="guide-steps">
              <li>{txt('在“分析记录”选择功能类型。单光谱先分“单个处理 / 批量处理”，再筛选“已处理 / 未处理”；点批次前的三角可展开文件。', 'Select a workflow in Analysis Records. For single spectra, choose Individual or Batch processing, then Processed or Unprocessed. Expand the triangle beside a batch to view its files.')}</li>
              <li>{txt('未处理任务可继续，已处理结果可查看、切换版本或重新分析。SSnet 标准品模型在混合物解析中管理。', 'Continue unfinished tasks or view, switch versions and reanalyze completed results. SSnet standard models are managed in Mixture analysis.')}</li>
              <li>{txt('点击“导出”下载当前结果。单光谱批处理支持勾选并“批量导出”TXT / PNG ZIP，也可“批量删除”。', 'Export the current result. Single-spectrum batches also support selected TXT / PNG ZIP exports and bulk deletion.')}</li>
              <li>{txt('需要团队查看时点击“共享到项目”，成员在项目的“共享结果”中查看。个人记录不会自动共享。', 'Choose Share to project for team access under Shared results. Personal records are not shared automatically.')}</li>
            </ol>
            <details className="guide-subsection"><summary>{txt('切换页面与新建分析', 'Navigation and new analyses')}</summary><p>{txt('切换功能后再返回，会保留当前输入、参数和结果。点击“新建分析”开始另一份数据；刷新后可从分析记录找回已上传任务和已保存结果。', 'Navigating between workflows preserves the current inputs, parameters and results. Choose New analysis for another dataset. After a refresh, reopen uploaded tasks and saved results from Analysis Records.')}</p></details>
            <div className="learning-actions"><Link to="/projects" className="learning-button">{txt('项目与数据', 'Projects & data')}<ArrowRight size={14} /></Link><Link to="/analysis-history" className="learning-text-link">{txt('查看分析记录', 'View Analysis Records')}<ArrowRight size={14} /></Link></div>
          </Section>

          <Section id="assistant" title={text(ASSISTANT_GUIDE_TITLE)} icon={MessageCircle}>
            <p>{txt('在分析页使用右侧助手。手机端点击“AI 问答”展开。', 'Use the assistant on an analysis page. On mobile, tap AI Q&A to open it.')}</p>
            <ol className="guide-steps">
              <li>{txt('在高光谱处理、分峰拟合、混合物解析、库匹配和光谱到结构中，从各自的工作区导入数据。开启“跟随当前页面”，点击“发送”提问或解读结果。', 'In Hyperspectral Processing, Peak Fitting, Mixture Analysis, Library Matching and Spectrum to Structure, import data in the workspace. Enable Follow current page and click Send to ask about the page or its results.')}</li>
              <li>{txt('智能光谱处理的助手可以使用工作区选中的光谱或助手附件。输入“去掉尖刺，再扣背景”等要求，点击“生成预处理方案”，在卡片上调整算法与参数后运行。', 'In Intelligent Spectrum Processing, use a spectrum selected in the workspace or attached to the assistant. Describe the steps, click Draft preprocessing plan and adjust algorithms and parameters on the card before running.')}</li>
              <li>{txt('智能光谱处理的“一键预处理”依次执行 despike 去鬼峰、F2P 降噪和 AirNet 基线校正。需要确认单位或文件转换时，按卡片提示操作。', 'Quick preprocessing in Intelligent Spectrum Processing runs despike, F2P denoising and AirNet baseline correction in order. Follow any prompts to confirm units or file conversion.')}</li>
            </ol>
            <details className="guide-subsection"><summary>{txt('问答会读取什么？', 'What does the assistant read?')}</summary><p>{txt('助手读取本次问题。开启“跟随当前页面”后，助手也会读取当前任务、结果和图表摘要。在智能光谱处理页，助手还可读取你主动上传给它的光谱。对话仅在本次会话中保留。', 'The assistant reads your question. With Follow current page enabled, it also reads task, result and chart summaries. In Intelligent Spectrum Processing, it can also read spectra you upload to the assistant. Conversations stay in the current session.')}</p></details>
          </Section>

          <Section id="faq" title={txt('常见问题', 'Common questions')} icon={HelpCircle}>{faq.map(([question, answer], index) => <details className="guide-faq" key={index}><summary>{text(question)}</summary><p>{text(answer)}</p></details>)}<div className="guide-feedback">{user?.role === 'admin' ? <Link to="/feedback" className="learning-button">{txt('查看与处理用户反馈', 'Review user feedback')}<ArrowRight size={14} /></Link> : <><h3>{txt('还有问题或建议？', 'Have another issue or suggestion?')}</h3><FeedbackForm /></>}</div></Section>
        </div>
      </div>
      <footer className="learning-footer guide-footer"><Link to="/tutorial#quick-start" className="learning-text-link">{txt('回到快速开始', 'Back to first run')}</Link></footer>
    </div>
  </div>;
}
