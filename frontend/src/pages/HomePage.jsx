import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, Atom, BookOpen, Database, FileCheck2, FolderKanban, GitBranch, Github, History, Layers, LineChart, Mail, MessageCircle, Sparkles, Wrench } from 'lucide-react';
import { usePreferences } from '../i18n';
import { ANALYSIS_GUIDES, ASSISTANT_GUIDE_TITLE, localize } from '../content/platformGuide';
import RecentResearch from '../components/RecentResearch';
import './LearningPages.css';

const ICONS = { sparkles: Sparkles, branches: GitBranch, database: Database, atom: Atom, layers: Layers, 'line-chart': LineChart };
const ANALYSIS_DESTINATIONS = ANALYSIS_GUIDES.filter(guide => guide.id !== 'preprocessing');

export default function HomePage() {
  const { language } = usePreferences();
  const text = value => localize(value, language);
  const txt = (zh, en) => text([zh, en]);

  return (
    <div className="learning-page home-page">
      <div className="learning-container home-container animate-fade-in">
        <header className="home-hero">
          <div className="home-intro">
            <p className="learning-eyebrow"><Sparkles size={15} />{txt('拉曼光谱分析工作台', 'Your Raman analysis workspace')}</p>
            <h1>RamanCloud</h1>
            <p className="home-tagline">{txt('光谱导入、处理与解析。', 'Import, process and analyze spectra.')}</p>

            <div className="learning-actions">
              <Link to="/ai-analysis" className="learning-primary">{txt('开始处理光谱', 'Process a spectrum')}<ArrowRight size={16} /></Link>
              <Link to="/tutorial#quick-start" className="learning-button"><BookOpen size={16} />{txt('查看使用教程', 'Read the guide')}</Link>
            </div>
          </div>
          <div className="home-workflow" aria-label={txt('光谱分析流程', 'Spectral analysis workflow')}>
            <div className="home-flow-step"><span className="learning-number">01</span><div><strong>{txt('导入与检查', 'Import & check')}</strong><p>{txt("识别格式 · 确认单位", "Detect format · Check units")}</p></div><FileCheck2 size={20} /></div>
            <div className="home-flow-step"><span className="learning-number">02</span><div><strong>{txt('光谱预处理', 'Preprocess')}</strong><p>{txt('去鬼峰 → 降噪 → 基线校正', 'Despike → Denoise → Correct baseline')}</p></div><Sparkles size={20} /></div>
            <div className="home-flow-step home-flow-branch">
              <span className="learning-number">03</span>
              <div>
                <strong>{txt('按目标选择分析', 'Choose an analysis')}</strong>
                <div className="home-branch-links">
                  {ANALYSIS_DESTINATIONS.map(guide => <Link key={guide.id} to={guide.to}>{text(guide.title)}<ArrowRight size={12} /></Link>)}
                </div>
              </div>
            </div>

          </div>
        </header>

        <section className="home-modules" aria-labelledby="home-modules-title">
          <div className="learning-section-heading"><div><h2 id="home-modules-title">{txt('选择需要的功能', 'Choose a workflow')}</h2></div><Link to="/tutorial#reading-requirements" className="learning-text-link">{txt('先了解输入要求', 'Check input requirements')}<ArrowRight size={14} /></Link></div>
          <div className="home-module-grid">
            {ANALYSIS_GUIDES.map(guide => {
              const Icon = ICONS[guide.icon];
              return <article key={guide.id} className={`home-module ${guide.id === 'preprocessing' ? 'home-module-featured' : ''}`}>
                <div className="home-module-top"><span className="learning-icon"><Icon size={22} /></span><span className="learning-tag">{text(guide.tag)}</span></div>
                <h3><Link to={guide.to}>{text(guide.title)}</Link></h3>
                <p className="learning-muted">{text(guide.description)}</p>
                <p className="home-module-requirement">{text(guide.requirement)}</p>
                <div className="home-module-actions"><Link to={guide.to} className="learning-text-link">{txt('进入功能', 'Open workflow')}<ArrowRight size={15} /></Link><Link to={`/tutorial#${guide.id}`} className="learning-text-link learning-secondary-link">{txt('操作教程', 'How to use')}</Link></div>
              </article>;
            })}
          </div>

        </section>

        <section className="home-data-section" aria-labelledby="home-data-title">
          <div className="learning-section-heading"><div><h2 id="home-data-title">{txt('记录与常用工具', 'Records & useful tools')}</h2></div></div>
          <div className="home-resource-grid">
            <Link to="/projects" className="home-resource"><FolderKanban size={22} /><div><h3>{txt('项目与数据', 'Projects & data')}</h3><p>{txt("管理实验数据，共享项目结果。", "Manage data and share project results.")}</p></div><ArrowRight size={16} /></Link>
            <Link to="/analysis-history" className="home-resource"><History size={22} /><div><h3>{txt('分析记录', 'Analysis records')}</h3><p>{txt('继续任务、查看结果，单个或批量导出。', 'Resume tasks, review results and export individually or in batches.')}</p></div><ArrowRight size={16} /></Link>
            <Link to="/extra-tools" className="home-resource"><Wrench size={22} /><div><h3>{txt('附加工具', 'Extra Tools')}</h3><p>{txt('拆分 Mapping、合并光谱与格式转换。', 'Split mappings, merge spectra and convert formats.')}</p></div><ArrowRight size={16} /></Link>
            <Link to="/tutorial#assistant" className="home-resource"><MessageCircle size={22} /><div><h3>{text(ASSISTANT_GUIDE_TITLE)}</h3><p>{txt('在分析页询问结果。在智能光谱处理使用一键预处理或定制方案。', 'Ask about results on analysis pages. Use quick preprocessing or draft a custom plan in Intelligent Spectrum Processing.')}</p></div><ArrowRight size={16} /></Link>
          </div>
          <div className="home-format-strip"><FileCheck2 size={20} /><div><strong>{txt('不同仪器，统一波数—强度', 'Instrument data, standardized axes')}</strong><p>{txt('TXT · CSV · XLSX · JCAMP · WDF · WXD · L6M · NPG', 'TXT · CSV · XLSX · JCAMP · WDF · WXD · L6M · NPG')}</p></div><Link to="/tutorial#import" className="learning-text-link">{txt('导入说明', 'Import guide')}<ArrowRight size={14} /></Link></div>
        </section>

        <RecentResearch />
        <footer className="learning-footer"><p>Ren Research Group · Xiamen University</p><div><a href="mailto:xinyulu@stu.xmu.edu.cn" aria-label={txt('邮件联系', 'Contact by email')}><Mail size={17} /></a><a href="https://github.com/hzh040518/Ramancloud" target="_blank" rel="noopener noreferrer" aria-label={txt('RamanCloud 当前代码仓库', 'Current RamanCloud repository')}><Github size={17} /><span>GitHub</span></a></div></footer>
      </div>
    </div>
  );
}
